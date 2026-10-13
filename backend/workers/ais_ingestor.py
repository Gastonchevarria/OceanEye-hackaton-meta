"""
OceanEye — Worker AIS Stream 24/7
Consume el WebSocket de aisstream.io y persiste en PostgreSQL / Supabase.
Correr como proceso separado: python -m workers.ais_ingestor
O como Cloud Run Job con restart-policy=always
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

# Bounding box: ZEE Argentina + zona buffer
BOUNDING_BOX = [[-60.0, -75.0], [-30.0, -45.0]]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [AIS-WORKER] %(levelname)s %(message)s",
)
logger = logging.getLogger("ais_ingestor")


MID_FLAGS = {
    "701": "🇦🇷 Argentina", "770": "🇦🇷 Argentina", "700": "🇦🇷 Argentina",
    "412": "🇨🇳 China", "413": "🇨🇳 China", "414": "🇨🇳 China",
    "416": "🇹🇼 Taiwán",
    "440": "🇰🇷 Corea del Sur", "441": "🇰🇷 Corea del Sur",
    "351": "🇵🇦 Panamá", "352": "🇵🇦 Panamá", "353": "🇵🇦 Panamá", "354": "🇵🇦 Panamá",
    "355": "🇵🇦 Panamá", "356": "🇵🇦 Panamá", "357": "🇵🇦 Panamá",
    "370": "🇵🇦 Panamá", "371": "🇵🇦 Panamá", "372": "🇵🇦 Panamá", "373": "🇵🇦 Panamá",
    "636": "🇱🇷 Liberia",
    "538": "🇲🇭 Islas Marshall",
    "710": "🇧🇷 Brasil",
    "725": "🇨🇱 Chile",
    "755": "🇵🇪 Perú",
    "720": "🇧🇴 Bolivia",
    "311": "🇧🇸 Bahamas",
    "257": "🇳🇴 Noruega", "258": "🇳🇴 Noruega", "259": "🇳🇴 Noruega",
    "219": "🇩🇰 Dinamarca", "220": "🇩🇰 Dinamarca",
    "304": "🇦🇬 Antigua y Barbuda", "305": "🇦🇬 Antigua y Barbuda",
    "319": "🇰🇾 Islas Caimán",
    "563": "🇸🇬 Singapur",
    "548": "🇵🇭 Filipinas",
    "477": "🇭🇰 Hong Kong",
    "645": "🇲🇺 Mauricio",
    "671": "🇹🇬 Togo",
    "253": "🇮🇸 Islandia",
    "405": "🇧🇩 Bangladesh",
    "224": "🇪🇸 España", "225": "🇪🇸 España",
    "226": "🇫🇷 Francia", "227": "🇫🇷 Francia", "228": "🇫🇷 Francia",
    "232": "🇬🇧 Reino Unido", "233": "🇬🇧 Reino Unido", "234": "🇬🇧 Reino Unido", "235": "🇬🇧 Reino Unido",
    "366": "🇺🇸 Estados Unidos", "367": "🇺🇸 Estados Unidos", "368": "🇺🇸 Estados Unidos", "369": "🇺🇸 Estados Unidos",
    "273": "🇷🇺 Rusia",
}

def resolve_vessel_flag(mmsi: str, existing_flag: str = "") -> str:
    if existing_flag and len(existing_flag) > 3 and not existing_flag.isdigit():
        return existing_flag
    prefix = str(mmsi)[:3]
    return MID_FLAGS.get(prefix, existing_flag or "🌐 Internacional")

def classify_zone(lat: float, lon: float) -> str:
    if -55 <= lat <= -35 and -68 <= lon <= -52:
        return "Argentina EEZ"
    if -50 <= lat <= -40 and -65 <= lon <= -55:
        return "South Atlantic – Agujero Azul"
    if -55 <= lat <= -48 and -70 <= lon <= -55:
        return "Patagonian Shelf"
    return "South Atlantic – High Seas"


def detect_loitering(speed: float, prev_positions: list) -> bool:
    """Loitering: speed < 2 kn sostenido por más de 3 posiciones consecutivas"""
    if speed > 2.0:
        return False
    if len(prev_positions) < 3:
        return False
    return all(p.get("speed", 99) < 2.0 for p in prev_positions[-3:])


def calculate_risk_heuristic(profile: dict) -> tuple[int, str, str]:
    """
    Risk score heurístico offline (sin llamar a NVIDIA AI).
    NVIDIA AI se llama al abrirse el panel del barco o en la chat UI.
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


async def upsert_vessel_position(pool: asyncpg.Pool, msg: dict) -> None:
    """Parsea el mensaje AIS y hace upsert en vessel_positions + vessel_profiles"""
    try:
        meta = msg.get("MetaData", {})
        pos = msg.get("Message", {}).get("PositionReport", {})
        static = msg.get("Message", {}).get("ShipStaticData", {})

        mmsi = str(meta.get("MMSI", "")).strip()
        if not mmsi or len(mmsi) > 9:
            return

        lat = pos.get("Latitude") or meta.get("latitude_dd", 0.0)
        lon = pos.get("Longitude") or meta.get("longitude_dd", 0.0)
        speed = pos.get("SpeedOverGround", 0.0)
        heading = int(pos.get("TrueHeading", 0) or pos.get("CourseOverGround", 0))
        ship_name = (
            static.get("Name", "")
            or meta.get("ShipName", "")
        ).strip()
        ship_type = int(static.get("Type", 0) or 0)
        flag = resolve_vessel_flag(mmsi, str(static.get("Flag", "") or ""))
        ts = datetime.now(timezone.utc)

        zone = classify_zone(lat, lon)

        async with pool.acquire() as conn:
            # 1. Insert posición
            await conn.execute(
                """
                INSERT INTO vessel_positions
                    (mmsi, timestamp, lat, lon, speed, heading, ship_name, ship_type, flag, source)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'aisstream')
                ON CONFLICT DO NOTHING
                """,
                mmsi, ts, lat, lon, speed, heading, ship_name, ship_type, flag,
            )

            # 2. Fetch profile actual
            row = await conn.fetchrow(
                "SELECT * FROM vessel_profiles WHERE mmsi=$1", mmsi
            )
            current = dict(row) if row else {}

            loitering_count = current.get("loitering_count", 0)
            ais_gaps = current.get("ais_gaps", 0)
            port_visits = current.get("port_visits", 0)

            # Detectar loitering (velocidad muy baja)
            if speed < 1.5:
                loitering_count += 1

            # Detectar gap AIS: si el último seen fue hace más de 6 horas
            last_seen = current.get("last_seen")
            if last_seen:
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                delta_hours = (ts - last_seen).total_seconds() / 3600
                if delta_hours > 6:
                    ais_gaps += 1

            profile_data = {
                "loitering_count": loitering_count,
                "ais_gaps": ais_gaps,
                "port_visits": port_visits,
                "last_speed": speed,
            }
            risk_score, risk_label, risk_color = calculate_risk_heuristic(profile_data)

            # 3. Upsert vessel_profile
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

            # 4. Generar alerta automática si riesgo crítico nuevo
            if risk_score >= 75 and current.get("risk_score", 0) < 75:
                await conn.execute(
                    """
                    INSERT INTO alerts (mmsi, vessel_name, alert_type, severity, description, lat, lon)
                    VALUES ($1,$2,'high_risk','critical',
                            $3,$4,$5)
                    """,
                    mmsi, ship_name,
                    f"Vessel {ship_name} ({mmsi}) reached critical risk score {risk_score}/100 in {zone}",
                    lat, lon,
                )
                logger.warning(f"🚨 ALERT generated for {ship_name} MMSI:{mmsi} score:{risk_score}")

    except Exception as e:
        logger.error(f"upsert error: {e}", exc_info=False)


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

    logger.info(f"Connecting to {url}...")
    async with websockets.connect(
        url,
        ping_interval=30,
        ping_timeout=15,
        close_timeout=10,
        max_size=2**20,
    ) as ws:
        await ws.send(subscribe_msg)
        logger.info("✅ AIS Stream connected — South Atlantic bounding box active")
        count = 0
        async for raw in ws:
            try:
                msg = json.loads(raw)
                await upsert_vessel_position(pool, msg)
                count += 1
                if count % 500 == 0:
                    logger.info(f"📡 {count} messages processed")
            except json.JSONDecodeError:
                pass


async def main():
    if not AIS_STREAM_KEY:
        raise RuntimeError("AIS_STREAM_KEY not set in environment")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set in environment")

    logger.info("Starting OceanEye AIS Ingestor Worker...")
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)
    logger.info("✅ PostgreSQL pool ready")

    try:
        await run_ais_stream(pool)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
