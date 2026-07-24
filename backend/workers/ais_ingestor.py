"""
OceanEye — Worker AIS Stream 24/7
Consume el WebSocket de aisstream.io y persiste posiciones en PostgreSQL.

Correr como proceso separado:
    python -m workers.ais_ingestor

O como Cloud Run Job:
    gcloud run jobs create oceaneye-ais-worker \\
      --image gcr.io/PROJECT/oceaneye-backend \\
      --command "python" \\
      --args "-m,workers.ais_ingestor"
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone

import websockets
import asyncpg
from dotenv import load_dotenv
from tenacity import retry, wait_exponential, stop_never, before_sleep_log

load_dotenv()

AIS_STREAM_KEY = os.getenv("AIS_STREAM_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "").replace(
    "postgresql+asyncpg://", "postgresql://"
)

# Bounding box: ZEE Argentina + zona de amortiguación
BOUNDING_BOX = [[-60.0, -75.0], [-30.0, -45.0]]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [AIS-WORKER] %(levelname)s %(message)s",
)
logger = logging.getLogger("ais_ingestor")


def classify_zone(lat: float, lon: float) -> str:
    if -55 <= lat <= -35 and -68 <= lon <= -52:
        return "Argentina EEZ"
    if -50 <= lat <= -40 and -65 <= lon <= -55:
        return "South Atlantic – Agujero Azul"
    if -55 <= lat <= -48 and -70 <= lon <= -55:
        return "Patagonian Shelf"
    return "South Atlantic – High Seas"


def calculate_risk_heuristic(profile: dict) -> tuple[int, str, str]:
    """
    Risk score heurístico offline (sin llamar a Claude).
    Claude se invoca solo cuando el operador abre el panel de un barco en la UI.
    """
    score = 0
    loitering = profile.get("loitering_count", 0)
    ports = profile.get("port_visits", 0)
    gaps = profile.get("ais_gaps", 0)
    speed = profile.get("last_speed", 5.0)

    score += min(loitering * 2, 40)
    score += 30 if ports == 0 else 0
    score += min(gaps * 5, 20)
    score += 10 if speed < 2.0 else 0
    score = min(score, 100)

    if score >= 75:
        return score, "critical", "#ef4444"
    if score >= 50:
        return score, "suspicious", "#f97316"
    if score >= 25:
        return score, "moderate", "#f59e0b"
    return score, "normal", "#22c55e"


async def upsert_vessel(pool: asyncpg.Pool, msg: dict) -> None:
    """Parsea mensaje AIS y hace upsert en vessel_positions + vessel_profiles"""
    try:
        meta = msg.get("MetaData", {})
        pos = msg.get("Message", {}).get("PositionReport", {})
        static = msg.get("Message", {}).get("ShipStaticData", {})

        mmsi = str(meta.get("MMSI", "")).strip()
        if not mmsi or len(mmsi) > 9:
            return

        lat = float(pos.get("Latitude") or meta.get("latitude_dd") or 0.0)
        lon = float(pos.get("Longitude") or meta.get("longitude_dd") or 0.0)
        speed = float(pos.get("SpeedOverGround") or 0.0)
        heading = int(pos.get("TrueHeading") or pos.get("CourseOverGround") or 0)
        ship_name = (static.get("Name", "") or meta.get("ShipName", "")).strip()
        ship_type = int(static.get("Type") or 0)
        flag = str(static.get("Flag") or "")[:3]
        ts = datetime.now(timezone.utc)
        zone = classify_zone(lat, lon)

        async with pool.acquire() as conn:
            # 1. Insertar posición cruda
            await conn.execute(
                """
                INSERT INTO vessel_positions
                    (mmsi, timestamp, lat, lon, speed, heading,
                     ship_name, ship_type, flag, source)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'aisstream')
                ON CONFLICT DO NOTHING
                """,
                mmsi, ts, lat, lon, speed, heading,
                ship_name, ship_type, flag,
            )

            # 2. Leer perfil actual para acumular métricas
            row = await conn.fetchrow(
                "SELECT loitering_count, ais_gaps, port_visits, last_seen, risk_score "
                "FROM vessel_profiles WHERE mmsi=$1",
                mmsi,
            )
            current = dict(row) if row else {}

            loitering_count = current.get("loitering_count", 0)
            ais_gaps = current.get("ais_gaps", 0)
            port_visits = current.get("port_visits", 0)

            if speed < 1.5:
                loitering_count += 1

            last_seen = current.get("last_seen")
            if last_seen:
                delta_h = (ts - last_seen.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                if delta_h > 6:
                    ais_gaps += 1

            profile_snap = {
                "loitering_count": loitering_count,
                "ais_gaps": ais_gaps,
                "port_visits": port_visits,
                "last_speed": speed,
            }
            risk_score, risk_label, risk_color = calculate_risk_heuristic(profile_snap)

            # 3. Upsert perfil del barco
            await conn.execute(
                """
                INSERT INTO vessel_profiles
                    (mmsi, name, flag, last_lat, last_lon, last_heading, last_speed,
                     last_seen, loitering_count, ais_gaps, port_visits,
                     risk_score, risk_label, risk_color, zone, updated_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                ON CONFLICT (mmsi) DO UPDATE SET
                    name            = EXCLUDED.name,
                    flag            = EXCLUDED.flag,
                    last_lat        = EXCLUDED.last_lat,
                    last_lon        = EXCLUDED.last_lon,
                    last_heading    = EXCLUDED.last_heading,
                    last_speed      = EXCLUDED.last_speed,
                    last_seen       = EXCLUDED.last_seen,
                    loitering_count = EXCLUDED.loitering_count,
                    ais_gaps        = EXCLUDED.ais_gaps,
                    risk_score      = EXCLUDED.risk_score,
                    risk_label      = EXCLUDED.risk_label,
                    risk_color      = EXCLUDED.risk_color,
                    zone            = EXCLUDED.zone,
                    updated_at      = EXCLUDED.updated_at
                """,
                mmsi, ship_name, flag, lat, lon, heading, speed,
                ts, loitering_count, ais_gaps, port_visits,
                risk_score, risk_label, risk_color, zone, ts,
            )

            # 4. Generar alerta si el barco acaba de volverse crítico
            prev_score = current.get("risk_score", 0)
            if risk_score >= 75 and prev_score < 75:
                await conn.execute(
                    """
                    INSERT INTO alerts
                        (mmsi, vessel_name, alert_type, severity, description, lat, lon)
                    VALUES ($1,$2,'high_risk','critical',$3,$4,$5)
                    """,
                    mmsi, ship_name,
                    f"Vessel {ship_name} ({mmsi}) reached critical risk score "
                    f"{risk_score}/100 in {zone}",
                    lat, lon,
                )
                logger.warning(
                    f"🚨 ALERT: {ship_name} MMSI:{mmsi} "
                    f"score:{risk_score} zone:{zone}"
                )

    except Exception as e:
        logger.error(f"upsert error MMSI={msg.get('MetaData',{}).get('MMSI','?')}: {e}")


@retry(
    wait=wait_exponential(multiplier=2, min=5, max=120),
    stop=stop_never,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
async def run_ais_stream(pool: asyncpg.Pool) -> None:
    """Conecta al WebSocket AIS y procesa mensajes indefinidamente"""
    url = "wss://stream.aisstream.io/v0/stream"
    subscribe_msg = json.dumps({
        "APIKey": AIS_STREAM_KEY,
        "BoundingBoxes": [BOUNDING_BOX],
        "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
    })

    logger.info(f"Connecting to {url} ...")
    async with websockets.connect(
        url,
        ping_interval=30,
        ping_timeout=15,
        close_timeout=10,
        max_size=2 ** 20,
    ) as ws:
        await ws.send(subscribe_msg)
        logger.info("✅ Connected — South Atlantic bounding box active")
        count = 0
        async for raw in ws:
            try:
                msg = json.loads(raw)
                await upsert_vessel(pool, msg)
                count += 1
                if count % 500 == 0:
                    logger.info(f"📡 {count} messages processed")
            except json.JSONDecodeError:
                pass


async def main():
    if not AIS_STREAM_KEY:
        raise RuntimeError("AIS_STREAM_KEY not configured")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not configured")

    logger.info("🌊 Starting OceanEye AIS Ingestor Worker...")
    pool = await asyncpg.create_pool(
        DATABASE_URL, min_size=2, max_size=5, command_timeout=30
    )
    logger.info("✅ PostgreSQL pool ready")

    try:
        await run_ais_stream(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
