"""
OceanEye — Supabase PostgreSQL Schema Migration & Seeder
"""
import os
import json
import asyncio
import asyncpg
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

DATABASE_URL = os.getenv("DATABASE_URL", "")

DDL_STATEMENTS = [
    # Extensiones
    "CREATE EXTENSION IF NOT EXISTS postgis;",

    # Tabla: vessel_positions (Posiciones AIS)
    """
    CREATE TABLE IF NOT EXISTS vessel_positions (
        id          BIGSERIAL,
        mmsi        VARCHAR(9)   NOT NULL,
        timestamp   TIMESTAMPTZ  NOT NULL,
        lat         DOUBLE PRECISION NOT NULL,
        lon         DOUBLE PRECISION NOT NULL,
        speed       FLOAT        DEFAULT 0,
        heading     SMALLINT     DEFAULT 0,
        ship_name   VARCHAR(100) DEFAULT '',
        ship_type   SMALLINT     DEFAULT 0,
        flag        VARCHAR(50)  DEFAULT '',
        source      VARCHAR(20)  DEFAULT 'aisstream',
        PRIMARY KEY (id, timestamp)
    );
    """,

    "CREATE INDEX IF NOT EXISTS ix_vp_mmsi_ts ON vessel_positions (mmsi, timestamp DESC);",
    "CREATE INDEX IF NOT EXISTS ix_vp_spatial_ts ON vessel_positions (timestamp DESC, lat, lon);",

    # Tabla: vessel_profiles (Perfiles acumulados de barcos)
    """
    CREATE TABLE IF NOT EXISTS vessel_profiles (
        mmsi            VARCHAR(9)   PRIMARY KEY,
        name            VARCHAR(100) DEFAULT '',
        flag            VARCHAR(50)  DEFAULT '',
        vessel_type     VARCHAR(50)  DEFAULT '',
        gfw_id          VARCHAR(100) DEFAULT '',
        last_lat        DOUBLE PRECISION DEFAULT 0,
        last_lon        DOUBLE PRECISION DEFAULT 0,
        last_heading    SMALLINT     DEFAULT 0,
        last_speed      FLOAT        DEFAULT 0,
        last_seen       TIMESTAMPTZ  DEFAULT NOW(),
        loitering_count INT          DEFAULT 0,
        ais_gaps        INT          DEFAULT 0,
        port_visits     INT          DEFAULT 0,
        risk_score      SMALLINT     DEFAULT 0,
        risk_label      VARCHAR(20)  DEFAULT 'unknown',
        risk_color      VARCHAR(10)  DEFAULT '#94a3b8',
        known_violations TEXT        DEFAULT '[]',
        events_summary  TEXT         DEFAULT '',
        zone            VARCHAR(100) DEFAULT 'South Atlantic',
        gfw_enriched    BOOLEAN      DEFAULT FALSE,
        updated_at      TIMESTAMPTZ  DEFAULT NOW()
    );
    """,

    # Tabla: alerts (Alertas y detecciones de pesca ilegal)
    """
    CREATE TABLE IF NOT EXISTS alerts (
        id          BIGSERIAL PRIMARY KEY,
        mmsi        VARCHAR(9)   NOT NULL,
        vessel_name VARCHAR(100) DEFAULT '',
        alert_type  VARCHAR(50)  NOT NULL,
        severity    VARCHAR(20)  DEFAULT 'medium',
        description TEXT         DEFAULT '',
        lat         DOUBLE PRECISION DEFAULT 0,
        lon         DOUBLE PRECISION DEFAULT 0,
        created_at  TIMESTAMPTZ  DEFAULT NOW(),
        acknowledged BOOLEAN     DEFAULT FALSE
    );
    """,

    "CREATE INDEX IF NOT EXISTS ix_alerts_mmsi ON alerts (mmsi);",
    "CREATE INDEX IF NOT EXISTS ix_alerts_created ON alerts (created_at DESC);"
]


async def run_migration():
    # Parse connection string
    db_url = DATABASE_URL
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    print(f"Connecting to database...")
    conn = await asyncpg.connect(db_url, timeout=10.0)
    print("Conectado exitosamente a PostgreSQL!")

    for ddl in DDL_STATEMENTS:
        try:
            await conn.execute(ddl)
        except Exception as e:
            print(f"Notice on statement: {e}")

    print("Tablas y extensiones creadas/verificadas con éxito.")

    # Seed con datos de la flota de la Patagonia
    json_path = os.path.join(os.path.dirname(__file__), "data", "real_patagonia_fleet_2026.json")
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            vessels = data.get("vessels", [])
            for v in vessels:
                mmsi = str(v.get("mmsi"))
                await conn.execute("""
                INSERT INTO vessel_profiles (
                    mmsi, name, flag, vessel_type, gfw_id, last_lat, last_lon,
                    last_heading, last_speed, loitering_count, ais_gaps, port_visits,
                    risk_score, risk_label, risk_color, known_violations, events_summary,
                    zone, gfw_enriched, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, NOW()
                ) ON CONFLICT (mmsi) DO UPDATE SET
                    name = EXCLUDED.name,
                    flag = EXCLUDED.flag,
                    vessel_type = EXCLUDED.vessel_type,
                    last_lat = EXCLUDED.last_lat,
                    last_lon = EXCLUDED.last_lon,
                    last_heading = EXCLUDED.last_heading,
                    last_speed = EXCLUDED.last_speed,
                    risk_score = EXCLUDED.risk_score,
                    risk_label = EXCLUDED.risk_label,
                    risk_color = EXCLUDED.risk_color,
                    known_violations = EXCLUDED.known_violations,
                    events_summary = EXCLUDED.events_summary,
                    zone = EXCLUDED.zone,
                    updated_at = NOW();
                """,
                mmsi,
                v.get("name", ""),
                v.get("flag", ""),
                v.get("vessel_type", ""),
                v.get("imo", ""),
                float(v.get("lat", 0)),
                float(v.get("lon", 0)),
                int(v.get("heading", 0)),
                float(v.get("live_speed", 0)),
                int(v.get("loitering_count", 0)),
                int(v.get("ais_gaps", 0)),
                int(v.get("port_visits", 0)),
                int(v.get("risk_score", 0)),
                v.get("risk_label", "unknown"),
                "#ef4444" if v.get("risk_score", 0) >= 75 else ("#f59e0b" if v.get("risk_score", 0) >= 50 else "#10b981"),
                json.dumps(v.get("known_violations", [])),
                v.get("events_summary", ""),
                v.get("zone", "South Atlantic"),
                True
                )
            print(f"Seed verificado: {len(vessels)} buques registrados en vessel_profiles.")

    # Reporte de tablas
    rows = await conn.fetch("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
          AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """)
    print("\nEstado actual de la base de datos (public schema):")
    for r in rows:
        tname = r["table_name"]
        cnt = await conn.fetchval(f"SELECT COUNT(*) FROM {tname};")
        print(f"  ● Tabla '{tname}': {cnt} registros")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
