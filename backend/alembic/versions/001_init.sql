-- Ejecutar una vez en tu instancia de PostgreSQL (con TimescaleDB extension o Supabase SQL Editor)

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

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
    flag        VARCHAR(3)   DEFAULT '',
    source      VARCHAR(20)  DEFAULT 'aisstream',
    PRIMARY KEY (id, timestamp)
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable('vessel_positions', 'timestamp', if_not_exists => TRUE);
        PERFORM add_retention_policy('vessel_positions', INTERVAL '90 days', if_not_exists => TRUE);
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'TimescaleDB hypertable creation skipped or managed by PostgreSQL';
END $$;

-- Índice para queries por barco e índice espacio-temporal compuesto
CREATE INDEX IF NOT EXISTS ix_vp_mmsi_ts ON vessel_positions (mmsi, timestamp DESC);
CREATE INDEX IF NOT EXISTS ix_vp_spatial_ts ON vessel_positions (timestamp DESC, lat, lon);

CREATE TABLE IF NOT EXISTS vessel_profiles (
    mmsi            VARCHAR(9)   PRIMARY KEY,
    name            VARCHAR(100) DEFAULT '',
    flag            VARCHAR(3)   DEFAULT '',
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

CREATE INDEX IF NOT EXISTS ix_alerts_mmsi ON alerts (mmsi);
CREATE INDEX IF NOT EXISTS ix_alerts_created ON alerts (created_at DESC);
