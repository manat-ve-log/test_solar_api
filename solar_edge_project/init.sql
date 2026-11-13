-- =====================================================
-- init.sql  (PostgreSQL)
-- Tables for storing data from the SolarEdge Mock API
-- =====================================================

CREATE SCHEMA IF NOT EXISTS "solarEdge";
SET search_path TO "solarEdge", public;   -- all tables below are created in "solarEdge"

-- -----------------------------
-- Site  <- GET /site/{site_id}/details
-- -----------------------------
CREATE TABLE IF NOT EXISTS sites (
    id                BIGINT PRIMARY KEY,                -- site_id (e.g. 1234567)
    name              VARCHAR(255)  NOT NULL,
    status            VARCHAR(50)   NOT NULL DEFAULT 'Active',
    peak_power_kw     NUMERIC(10,2),
    currency          VARCHAR(10),
    installation_date DATE,
    notes             TEXT,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- -----------------------------
-- Equipment  <- GET /equipment/{site_id}/list
-- -----------------------------
CREATE TABLE IF NOT EXISTS equipment (
    serial_number VARCHAR(50)   PRIMARY KEY,
    site_id       BIGINT        NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    name          VARCHAR(255)  NOT NULL,
    manufacturer  VARCHAR(100)  NOT NULL DEFAULT 'SolarEdge',
    model         VARCHAR(100),
    kwp           NUMERIC(10,2),
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_equipment_site ON equipment(site_id);

-- -----------------------------
-- Inverter telemetry  <- GET /equipment/{site_id}/{serial}/data
-- (5-minute samples)
-- -----------------------------
CREATE TABLE IF NOT EXISTS equipment_telemetry (
    id                        BIGSERIAL PRIMARY KEY,
    serial_number             VARCHAR(50) NOT NULL REFERENCES equipment(serial_number) ON DELETE CASCADE,
    recorded_at               TIMESTAMP   NOT NULL,        -- "date" field from API
    total_active_power        NUMERIC(12,1),               -- W
    dc_voltage                NUMERIC(8,1),                -- V
    ground_fault_resistance   NUMERIC(10,1),               -- kOhm
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_telemetry UNIQUE (serial_number, recorded_at)
);

CREATE INDEX IF NOT EXISTS idx_telemetry_time ON equipment_telemetry(recorded_at);

-- -----------------------------
-- Current power flow  <- GET /site/{site_id}/currentPowerFlow
-- (one row per poll)
-- -----------------------------
CREATE TABLE IF NOT EXISTS power_flow (
    id                    BIGSERIAL PRIMARY KEY,
    site_id               BIGINT      NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    recorded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    update_refresh_rate   INTEGER,
    unit                  VARCHAR(10) NOT NULL DEFAULT 'kW',

    pv_status             VARCHAR(20),
    pv_power              NUMERIC(10,2),

    grid_status           VARCHAR(20),
    grid_power            NUMERIC(10,2),

    load_status           VARCHAR(20),
    load_power            NUMERIC(10,2),

    storage_status        VARCHAR(20),
    storage_power         NUMERIC(10,2),
    storage_charge_level  SMALLINT CHECK (storage_charge_level BETWEEN 0 AND 100),
    storage_critical      BOOLEAN,

    connections           JSONB       NOT NULL DEFAULT '[]'::jsonb  -- [{"from":"PV","to":"Load"}, ...]
);

CREATE INDEX IF NOT EXISTS idx_power_flow_site_time ON power_flow(site_id, recorded_at DESC);

-- -----------------------------
-- Energy  <- GET /site/{site_id}/energy
-- -----------------------------
CREATE TABLE IF NOT EXISTS energy (
    id           BIGSERIAL PRIMARY KEY,
    site_id      BIGINT       NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    time_unit    VARCHAR(10)  NOT NULL CHECK (time_unit IN ('DAY','WEEK','MONTH','YEAR')),
    energy_date  DATE         NOT NULL,
    value_wh     NUMERIC(14,1),
    measured_by  VARCHAR(50)  NOT NULL DEFAULT 'INVERTER',
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_energy UNIQUE (site_id, time_unit, energy_date)
);

CREATE INDEX IF NOT EXISTS idx_energy_site_date ON energy(site_id, energy_date);

-- -----------------------------
-- Energy details  <- GET /site/{site_id}/energyDetails
-- -----------------------------
CREATE TABLE IF NOT EXISTS energy_details (
    id           BIGSERIAL PRIMARY KEY,
    site_id      BIGINT       NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    meter_type   VARCHAR(30)  NOT NULL DEFAULT 'Production',
    time_unit    VARCHAR(10)  NOT NULL CHECK (time_unit IN ('HOUR','DAY','MONTH','YEAR')),
    recorded_at  TIMESTAMP    NOT NULL,
    value_wh     NUMERIC(16,1),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_energy_details UNIQUE (site_id, meter_type, time_unit, recorded_at)
);

CREATE INDEX IF NOT EXISTS idx_energy_details_site_time ON energy_details(site_id, recorded_at);

-- =====================================================
-- Seed data (matches the mock API)
-- =====================================================
INSERT INTO sites (id, name, status, peak_power_kw, currency, installation_date, notes)
VALUES (1234567, 'Mock SolarEdge Site', 'Active', 33.0, 'THB', '2025-01-01', 'Mock site for testing')
ON CONFLICT (id) DO NOTHING;

INSERT INTO equipment (serial_number, site_id, name, manufacturer, model, kwp) VALUES
    ('SE12345678', 1234567, 'Inverter 1', 'SolarEdge', 'SE33.3K', 33.0),
    ('SE87654321', 1234567, 'Inverter 2', 'SolarEdge', 'SE27.6K', 27.6)
ON CONFLICT (serial_number) DO NOTHING;