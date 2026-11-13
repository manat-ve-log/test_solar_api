import psycopg

DB_URL = "postgresql://postgres:postgres@db:5434/solar_db"

schema_sql = """
CREATE SCHEMA IF NOT EXISTS solar;

-- 1. Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

CREATE TABLE IF NOT EXISTS solar.users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    systemcode VARCHAR(255) NOT NULL,
    xrsftoken VARCHAR(100) ,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS solar.stations (
    id SERIAL PRIMARY KEY,
    station_code VARCHAR(100) NOT NULL UNIQUE,
    user_id INT REFERENCES solar.users(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_stations_user_id ON solar.stations(user_id);


CREATE TABLE IF NOT EXISTS solar.devices (
    dev_id           SERIAL PRIMARY KEY,
    station_id       INT REFERENCES solar.stations(id) ON DELETE CASCADE,
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    huawei_dev_id    BIGINT NOT NULL UNIQUE,
    dev_dn           TEXT NOT NULL,
    dev_name         TEXT NOT NULL,
    dev_type_id      INT NOT NULL,
    esn_code         TEXT,
    inv_type         TEXT,
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    model            TEXT NOT NULL,
    optimizer_number INT,
    software_version TEXT
);

CREATE INDEX IF NOT EXISTS ix_devices_station_id ON solar.devices(station_id);



-- 2. RealTimeDeviceData table for TimescaleDB
CREATE TABLE IF NOT EXISTS solar.RealTimeDeviceData (
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dev_id INT NOT NULL,
    temperature FLOAT,
    open_time FLOAT,
    inverter_state FLOAT,
    total_cap FLOAT,
    reactive_power FLOAT,
    power_factor FLOAT,
    active_power FLOAT,
    close_time FLOAT,
    day_cap FLOAT,
    efficiency FLOAT,
    PRIMARY KEY (recorded_at, dev_id)
);

-- Convert table into a TimescaleDB Hypertable partitioned by recorded_at
SELECT create_hypertable(
    'solar.RealTimeDeviceData', 
    by_range('recorded_at'), 
    if_not_exists => TRUE
);

-- Index for fast device queries sorted by timestamp
CREATE INDEX IF NOT EXISTS idx_realtime_dev_time 
    ON solar.RealTimeDeviceData(dev_id, recorded_at DESC);

-- 3. HistoryDeviceData table for TimescaleDB
CREATE TABLE IF NOT EXISTS solar.HistoryDeviceData (
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    station_code VARCHAR(100) NOT NULL,
    use_power FLOAT,
    radiation_intensity FLOAT,
    reduction_total_co2 FLOAT,
    reduction_total_coal FLOAT,
    theory_power FLOAT,
    ongrid_power FLOAT,
    power_profit FLOAT,
    installed_capacity FLOAT,
    perpower_ratio FLOAT,
    inverter_power FLOAT,
    reduction_total_tree FLOAT,
    performance_ratio FLOAT,
    PRIMARY KEY (recorded_at, station_code)
);

-- Convert history table into a TimescaleDB Hypertable
SELECT create_hypertable(
    'solar.HistoryDeviceData', 
    by_range('recorded_at'), 
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_history_station_time 
    ON solar.HistoryDeviceData(station_code, recorded_at DESC);
"""

try:
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
    print("TimescaleDB extension enabled and hypertables created successfully!")

except Exception as e:
    print(f"Error creating schema: {e}")