"""
OceanEye Backend v4 — Production
FastAPI + PostgreSQL + Claude AI + AIS Stream + Global Fishing Watch

Cambios respecto a v3:
- Elimina DEMO_VESSELS hardcodeados → todas las queries van a PostgreSQL
- Elimina /config (no se exponen API keys al cliente)
- CORS restrictivo: solo FRONTEND_URL
- Rate limiting via slowapi
- API Key auth opcional (dev) / obligatorio (prod)
- /health endpoint para Cloud Run
- /alerts endpoint para alertas en tiempo real
- Chat agent consulta DB real, no lista estática
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import anthropic
import asyncpg
from fastapi import FastAPI, HTTPException, Request, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GFW_API_TOKEN     = os.getenv("GFW_API_TOKEN", "")
DATABASE_URL      = os.getenv("DATABASE_URL", "").replace(
                        "postgresql+asyncpg://", "postgresql://"
                    )
FRONTEND_URL      = os.getenv("FRONTEND_URL", "https://oceaneye-three.vercel.app")
INTERNAL_API_KEY  = os.getenv("INTERNAL_API_KEY", "")
ENVIRONMENT       = os.getenv("ENVIRONMENT", "production")
GFW_BASE_URL      = "https://gateway.api.globalfishingwatch.org/v3"
PORT              = int(os.getenv("PORT", 8000))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("oceaneye")

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── Security ──────────────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(key: Optional[str] = Security(api_key_header)):
    """
    En development: sin restricciones.
    En production: requiere X-API-Key header válido si INTERNAL_API_KEY está configurado.
    """
    if ENVIRONMENT == "development":
        return True
    if not INTERNAL_API_KEY:
        return True
    if key != INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return True

# ── DB Pool ───────────────────────────────────────────────────────────────────
db_pool: Optional[asyncpg.Pool] = None

async def get_pool() -> asyncpg.Pool:
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable — check DATABASE_URL")
    return db_pool

# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="OceanEye API",
    description="Real-time maritime intelligence — IUU fishing detection — South Atlantic EEZ",
    version="4.0.0",
    docs_url="/docs" if ENVIRONMENT == "development" else None,
    redoc_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# ── Lifecycle ─────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    global db_pool
    if DATABASE_URL:
        try:
            db_pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=2,
                max_size=10,
                command_timeout=30,
            )
            logger.info("✅ PostgreSQL pool ready")
        except Exception as e:
            logger.error(f"DB connection failed: {e}")
    else:
        logger.warning("⚠️  DATABASE_URL not set — running without persistence")


@app.on_event("shutdown")
async def shutdown():
    if db_pool:
        await db_pool.close()


# ── Pydantic Models ───────────────────────────────────────────────────────────
class VesselData(BaseModel):
    mmsi: str
    name: str
    flag: str
    loitering_count: int = 0
    port_visits: int = 0
    ais_gaps: int = 0
    avg_speed: float = 0.0
    zone: str = "South Atlantic"

class AnalyzeRequest(BaseModel):
    vessel_data: VesselData

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    conversation_history: list[ChatMessage] = []

class ExportRequest(BaseModel):
    vessel_data: dict
    claude_report: dict


# ── Claude helper ─────────────────────────────────────────────────────────────
def get_claude() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="AI service not configured")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


SYSTEM_PROMPT = """You are OceanEye, a maritime intelligence analyst specializing in IUU fishing detection.
Monitored Area: South Atlantic — Argentina EEZ Border (200-220 nautical miles)

Key Context:
- Chinese fleet accounts for 66% of AIS gap events at the EEZ border
- +600,000 hours of unbroadcasted fishing documented annually (dark vessels)
- Gaps concentrated at miles 200-220 — deliberate EEZ evasion pattern
- Operation Mare Nostrum I active (Argentine Navy, 2025/2026)
- The Blue Hole (43-47S): maximum squid concentration zone

Rules: Always respond in English. Be direct. Use data. Never say "could be" — take a firm position."""

CHAT_SYSTEM_PROMPT = SYSTEM_PROMPT + """

Always call tools before answering. Cite MMSI, coordinates, risk scores.
Use markdown. Respond only in English."""


# ── GFW Enrichment ────────────────────────────────────────────────────────────
async def enrich_from_gfw(mmsi: str, gfw_id: str) -> dict:
    """Enriquece perfil con eventos reales de Global Fishing Watch"""
    if not GFW_API_TOKEN or not gfw_id or gfw_id.startswith("demo-"):
        return {}
    headers = {"Authorization": f"Bearer {GFW_API_TOKEN}"}
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{GFW_BASE_URL}/events",
                params={
                    "vessels[0]": gfw_id,
                    "datasets[0]": "public-global-loitering-events:latest",
                    "datasets[1]": "public-global-gaps-events:latest",
                    "datasets[2]": "public-global-fishing-events:latest",
                    "datasets[3]": "public-global-port-visits-events:latest",
                    "start-date": start_date,
                    "end-date": end_date,
                    "limit": 100,
                },
                headers=headers,
            )
            if resp.status_code == 200:
                events = resp.json().get("entries", [])
                return {
                    "loitering_count": sum(1 for e in events if e.get("type") == "LOITERING"),
                    "ais_gaps": sum(1 for e in events if e.get("type") == "GAP"),
                    "port_visits": sum(1 for e in events if e.get("type") == "PORT_VISIT"),
                    "gfw_enriched": True,
                }
    except Exception as e:
        logger.warning(f"GFW enrichment failed for {mmsi}: {e}")
    return {}


# ── Vessel trail from DB ───────────────────────────────────────────────────────
async def get_vessel_trail(pool: asyncpg.Pool, mmsi: str, limit: int = 15) -> list:
    rows = await pool.fetch(
        """
        SELECT lat, lon
        FROM vessel_positions
        WHERE mmsi = $1
        ORDER BY timestamp DESC
        LIMIT $2
        """,
        mmsi, limit,
    )
    return [{"lat": r["lat"], "lon": r["lon"]} for r in reversed(rows)]


# ── Chat tools — queries a DB real ────────────────────────────────────────────
async def execute_tool_db(
    tool_name: str, tool_input: dict, pool: Optional[asyncpg.Pool]
) -> str:
    if pool is None:
        return json.dumps({"error": "Database not available"})

    if tool_name == "get_vessels":
        rows = await pool.fetch(
            """
            SELECT mmsi, name, flag, vessel_type, gfw_id,
                   last_lat, last_lon, last_heading, last_speed,
                   loitering_count, port_visits, ais_gaps,
                   risk_score, risk_label, risk_color,
                   events_summary, zone, known_violations,
                   last_seen, updated_at
            FROM vessel_profiles
            ORDER BY risk_score DESC
            LIMIT 50
            """
        )
        vessels = []
        for r in rows:
            v = dict(r)
            try:
                v["known_violations"] = json.loads(v.get("known_violations") or "[]")
            except Exception:
                v["known_violations"] = []
            for k in ["last_seen", "updated_at"]:
                if isinstance(v.get(k), datetime):
                    v[k] = v[k].isoformat()
            vessels.append(v)
        return json.dumps(vessels, ensure_ascii=False, default=str)

    elif tool_name == "search_by_flag":
        flag = tool_input.get("flag", "").strip()
        rows = await pool.fetch(
            "SELECT * FROM vessel_profiles "
            "WHERE LOWER(flag) = LOWER($1) ORDER BY risk_score DESC",
            flag,
        )
        result = []
        for r in rows:
            v = dict(r)
            for k in ["last_seen", "updated_at"]:
                if isinstance(v.get(k), datetime):
                    v[k] = v[k].isoformat()
            result.append(v)
        return json.dumps(result, ensure_ascii=False, default=str)

    elif tool_name == "get_zone_summary":
        rows = await pool.fetch(
            "SELECT risk_score, flag, zone FROM vessel_profiles"
        )
        profiles = [dict(r) for r in rows]
        total = len(profiles)
        critical   = sum(1 for p in profiles if p["risk_score"] >= 75)
        suspicious = sum(1 for p in profiles if 50 <= p["risk_score"] < 75)
        normal     = sum(1 for p in profiles if p["risk_score"] < 50)
        avg = round(
            sum(p["risk_score"] for p in profiles) / total, 1
        ) if total else 0
        flags = list(set(p["flag"] for p in profiles if p["flag"]))
        return json.dumps({
            "zone": "South Atlantic – Argentina EEZ Region",
            "total_vessels_tracked": total,
            "threat_level": "HIGH" if critical >= 2 else "MODERATE",
            "critical_count": critical,
            "suspicious_count": suspicious,
            "normal_count": normal,
            "flags_present": flags,
            "avg_risk_score": avg,
            "data_source": "live_database",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False)

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


CHAT_TOOLS = [
    {
        "name": "get_vessels",
        "description": "Get all tracked vessels from live database: positions, risk scores, "
                       "loitering counts, AIS gaps, port visits.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_by_flag",
        "description": "Search vessels by flag state (ISO 3-letter code or country name). "
                       "E.g. 'CHN', 'VUT', 'ARG', 'China'.",
        "input_schema": {
            "type": "object",
            "properties": {"flag": {"type": "string"}},
            "required": ["flag"],
        },
    },
    {
        "name": "get_zone_summary",
        "description": "Get live threat assessment: risk distribution, vessel counts, "
                       "flags present, avg risk score from live database.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {
        "app": "OceanEye API",
        "version": "4.0",
        "status": "online",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health")
async def health():
    """Health check endpoint para Cloud Run y load balancers"""
    db_ok = db_pool is not None
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "ai": "configured" if ANTHROPIC_API_KEY else "missing",
        "gfw": "configured" if GFW_API_TOKEN else "missing",
        "ais_worker": "external_process",
        "version": "4.0.0",
    }


@app.get("/vessels")
@limiter.limit("60/minute")
async def get_vessels(
    request: Request,
    zone: str = "south_atlantic",
    pool: asyncpg.Pool = Depends(get_pool),
    _: bool = Depends(verify_api_key),
):
    """Retorna todos los barcos trackeados de la DB, ordenados por risk_score DESC"""
    rows = await pool.fetch(
        """
        SELECT vp.*
        FROM vessel_profiles vp
        ORDER BY risk_score DESC
        LIMIT 100
        """
    )
    vessels = []
    for row in rows:
        v = dict(row)
        try:
            v["known_violations"] = json.loads(v.get("known_violations") or "[]")
        except Exception:
            v["known_violations"] = []
        for k in ["last_seen", "updated_at"]:
            if isinstance(v.get(k), datetime):
                v[k] = v[k].isoformat()
        v["trail"] = await get_vessel_trail(pool, v["mmsi"], 10)
        # Normalizar nombres para compatibilidad con frontend existente
        v["lat"]      = v.pop("last_lat", 0.0)
        v["lon"]      = v.pop("last_lon", 0.0)
        v["heading"]  = v.pop("last_heading", 0)
        v["avg_speed"] = v.pop("last_speed", 0.0)
        vessels.append(v)

    return {
        "vessels": vessels,
        "total": len(vessels),
        "source": "live_database",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/vessel/{mmsi}/events")
@limiter.limit("20/minute")
async def get_vessel_events(
    request: Request,
    mmsi: str,
    pool: asyncpg.Pool = Depends(get_pool),
    _: bool = Depends(verify_api_key),
):
    """Retorna eventos reales de Global Fishing Watch para un barco específico"""
    row = await pool.fetchrow(
        "SELECT gfw_id FROM vessel_profiles WHERE mmsi=$1", mmsi
    )
    if not row:
        raise HTTPException(status_code=404, detail="Vessel not found")

    gfw_data = await enrich_from_gfw(mmsi, row["gfw_id"])
    return {
        "mmsi": mmsi,
        "gfw_enrichment": gfw_data,
        "source": "gfw_api" if gfw_data.get("gfw_enriched") else "not_available",
    }


@app.post("/analyze")
@limiter.limit("20/minute")
async def analyze_vessel(
    request: Request,
    body: AnalyzeRequest,
    _: bool = Depends(verify_api_key),
):
    """Claude AI risk analysis para un barco dado sus métricas"""
    v = body.vessel_data
    prompt = SYSTEM_PROMPT + f"""

Analyze this vessel and return a structured JSON intelligence report.

Vessel Data:
- MMSI: {v.mmsi} | Name: {v.name} | Flag: {v.flag}
- Loitering count: {v.loitering_count} | Port visits: {v.port_visits}
- AIS gaps: {v.ais_gaps} | Avg Speed: {v.avg_speed} kn | Zone: {v.zone}

Criteria: loitering>30=suspicious, ports=0=evasion, AIS gaps>3=dark vessel, speed<3kn=trawling.
If risk LOW (<40): summary MUST include "No signs of illegal activity detected."

Respond ONLY with valid JSON — no markdown, no extra text:
{{
  "risk_score": <0-100>,
  "risk_label": "<CRITICAL|HIGH|MEDIUM|LOW>",
  "risk_color": "<#ef4444|#f97316|#f59e0b|#22c55e>",
  "summary": "<2-3 english sentences>",
  "red_flags": ["<flag1>", "<flag2>", "<flag3>"],
  "most_suspicious": "<single finding>",
  "recommendation": "<action>"
}}"""

    def _call(content: str) -> str:
        client = get_claude()
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": content}],
        )
        t = msg.content[0].text.strip()
        if t.startswith("```"):
            t = t.split("```")[1]
            if t.startswith("json"):
                t = t[4:]
            t = t.strip()
        return t

    try:
        text = await asyncio.to_thread(_call, prompt)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            text2 = await asyncio.to_thread(
                _call, text + "\n\nError: return ONLY valid JSON, no extra text."
            )
            return json.loads(text2)
    except json.JSONDecodeError:
        return {
            "risk_score": 50, "risk_label": "MEDIUM", "risk_color": "#f59e0b",
            "summary": "Analysis parsing error — manual review required.",
            "red_flags": [], "most_suspicious": "Parse failure",
            "recommendation": "Manual review",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
@limiter.limit("30/minute")
async def chat_with_agent(
    request: Request,
    body: ChatRequest,
    pool: asyncpg.Pool = Depends(get_pool),
    _: bool = Depends(verify_api_key),
):
    """Conversational agent con acceso a datos reales de la DB"""
    try:
        history = [
            {"role": m.role, "content": m.content}
            for m in body.conversation_history[-8:]
        ]
        messages = history + [{"role": "user", "content": body.message}]
        client = get_claude()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=CHAT_SYSTEM_PROMPT,
            messages=messages,
            tools=CHAT_TOOLS,
        )

        tools_used = []
        for _ in range(3):
            if response.stop_reason != "tool_use":
                break
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tools_used.append({"name": block.name, "params": block.input})
                    result = await execute_tool_db(block.name, block.input, pool)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                system=CHAT_SYSTEM_PROMPT,
                tools=CHAT_TOOLS,
                messages=messages,
            )

        reply = "".join(b.text for b in response.content if b.type == "text")
        return {"reply": reply, "tools_used": tools_used or None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/export")
@limiter.limit("10/minute")
async def generate_export(
    request: Request,
    body: ExportRequest,
    _: bool = Depends(verify_api_key),
):
    v = body.vessel_data
    cr = body.claude_report
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    prompt = f"""Generate this exact plain text intelligence report:

OCEANEYE — MARITIME INTELLIGENCE REPORT
Generated: {now_utc}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VESSEL: {v.get('name')} | MMSI: {v.get('mmsi')} | FLAG: {v.get('flag')}
RISK SCORE: {v.get('risk_score', 0)}/100 — {str(v.get('risk_label', 'UNKNOWN')).upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANALYSIS: {cr.get('summary', '')}
RED FLAGS:
{chr(10).join(['- ' + str(rf) for rf in cr.get('red_flags', [])])}
MOST SUSPICIOUS: {cr.get('most_suspicious', '')}
RECOMMENDED ACTION: {cr.get('recommendation', '')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Source: OceanEye v4 | AIS Stream + Global Fishing Watch + Claude AI (Anthropic)
Real-time vessel tracking — South Atlantic EEZ Monitoring"""

    def _call():
        client = get_claude()
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()

    try:
        text = await asyncio.to_thread(_call)
        return {"report": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/briefing")
@limiter.limit("10/minute")
async def generate_briefing(
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
    _: bool = Depends(verify_api_key),
):
    """Daily intelligence briefing generado con datos reales de la DB"""
    zone_data = await execute_tool_db("get_zone_summary", {}, pool)
    prompt = SYSTEM_PROMPT + f"""

Generate a DAILY INTELLIGENCE BRIEFING based on LIVE database data.

Data: {zone_data}

Format:
1. THREAT LEVEL (1 line)
2. KEY FINDINGS (2-3 bullets)
3. IMMEDIATE ACTIONS (1-2 bullets)

Under 150 words. Authoritative tone. Markdown. No headers."""

    def _call():
        client = get_claude()
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()

    try:
        text = await asyncio.to_thread(_call)
        return {
            "briefing": text,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_source": "live_database",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/alerts")
@limiter.limit("30/minute")
async def get_alerts(
    request: Request,
    limit: int = 20,
    acknowledged: bool = False,
    pool: asyncpg.Pool = Depends(get_pool),
    _: bool = Depends(verify_api_key),
):
    """Retorna alertas automáticas generadas por el worker AIS"""
    rows = await pool.fetch(
        """
        SELECT id, mmsi, vessel_name, alert_type, severity,
               description, lat, lon, created_at, acknowledged
        FROM alerts
        WHERE acknowledged = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        acknowledged, limit,
    )
    alerts = []
    for r in rows:
        a = dict(r)
        if isinstance(a.get("created_at"), datetime):
            a["created_at"] = a["created_at"].isoformat()
        alerts.append(a)
    return {"alerts": alerts, "total": len(alerts)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
