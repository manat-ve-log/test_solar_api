CREATE SCHEMA IF NOT EXISTS solar;
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

CREATE TABLE IF NOT EXISTS solar.users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    systemcode VARCHAR(255) NOT NULL,
    xsrftoken VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS solar.stations (
    id SERIAL PRIMARY KEY,
    station_code VARCHAR(100) NOT NULL UNIQUE,
    user_id INT REFERENCES solar.users(id) ON DELETE CASCADE,
    install_date TIMESTAMP WITH TIME ZONE ,
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

CREATE TABLE IF NOT EXISTS solar.realtimedevicedata (
    recorded_at BIGINT NOT NULL,
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
SELECT create_hypertable('solar.realtimedevicedata', by_range('recorded_at'), if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_realtime_dev_time
    ON solar.realtimedevicedata(dev_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS solar.historydevicedata (
    recorded_at BIGINT NOT NULL,
    station_code VARCHAR(100) NOT NULL,
    use_power FLOAT,
    radiation_intensity FLOAT,
    reduction_total_co2 FLOAT,
    reduction_total_coal FLOAT,
    theory_power FLOAT,
    ongrid_power FLOAT,
    power_profit FLOAT,
    installed_capacity FLOAT,
    buyPower FLOAT,
    selfUsePower FLOAT,
    PVYield FLOAT,
    perpower_ratio FLOAT,
    inverter_power FLOAT,
    reduction_total_tree FLOAT,
    performance_ratio FLOAT,
    PRIMARY KEY (recorded_at, station_code)
);
SELECT create_hypertable('solar.historydevicedata', by_range('recorded_at'), if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_history_station_time
    ON solar.historydevicedata(station_code, recorded_at DESC);