/* ============================================================================
   01_schema.sql  -  Star schema for the refinery analytics model
   Dialect: SQLite (portable ANSI SQL; see README for SQL Server / MySQL notes)

            dim_date ─┐
            dim_line ─┼──<  fact_batch   (grain: 1 row per refining batch)
        dim_supplier ─┘
            dim_line ────<  fact_downtime (grain: 1 row per stoppage event)
                            fact_market_price (grain: 1 row per month)
   ========================================================================== */

DROP TABLE IF EXISTS dim_line;
DROP TABLE IF EXISTS dim_supplier;
DROP TABLE IF EXISTS map_supplier_alias;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS fact_batch;
DROP TABLE IF EXISTS fact_downtime;
DROP TABLE IF EXISTS fact_market_price;
DROP TABLE IF EXISTS dq_log;

CREATE TABLE dim_line (
    line_code            TEXT PRIMARY KEY,          -- 'A', 'B', 'C'
    line_name            TEXT NOT NULL,
    design_capacity_tpd  REAL NOT NULL,             -- tonnes CPO per day
    commissioned_year    INTEGER NOT NULL
);

CREATE TABLE dim_supplier (
    supplier_id     TEXT PRIMARY KEY,
    supplier_name   TEXT NOT NULL,
    state           TEXT,
    region          TEXT,                            -- Peninsular / East Malaysia
    certification   TEXT,
    distance_km     REAL,
    contract_start  DATE
);

-- Operators type mill names by hand; this table maps every spelling we have
-- seen (normalised: upper-case, no spaces/dots/dashes) to the master ID.
CREATE TABLE map_supplier_alias (
    alias_key    TEXT PRIMARY KEY,
    supplier_id  TEXT NOT NULL REFERENCES dim_supplier(supplier_id)
);

CREATE TABLE dim_date (
    date_key      DATE PRIMARY KEY,
    year          INTEGER,
    quarter       TEXT,
    month_no      INTEGER,
    month_name    TEXT,
    year_month    TEXT,
    week_of_year  INTEGER,
    day_name      TEXT,
    is_weekend    INTEGER,
    crop_season   TEXT                               -- 'Peak' (Sep-Nov) / 'Normal'
);

CREATE TABLE fact_batch (
    batch_id              TEXT PRIMARY KEY,
    production_date       DATE NOT NULL REFERENCES dim_date(date_key),
    shift                 TEXT NOT NULL,
    line_code             TEXT NOT NULL REFERENCES dim_line(line_code),
    supplier_id           TEXT REFERENCES dim_supplier(supplier_id),
    operator_id           TEXT,
    -- feedstock (CPO) quality
    cpo_input_mt          REAL,
    cpo_ffa_pct           REAL,
    cpo_dobi              REAL,
    cpo_moisture_pct      REAL,
    -- process conditions
    bleaching_earth_pct   REAL,
    phosphoric_acid_pct   REAL,
    deo_temp_c            REAL,
    deo_vacuum_mbar       REAL,
    -- outputs
    rbdpo_output_mt       REAL,
    pfad_output_mt        REAL,
    refining_yield_pct    REAL,      -- RBDPO / CPO * 100
    pfad_yield_pct        REAL,      -- PFAD  / CPO * 100
    refining_loss_pct     REAL,      -- 100 - RBDPO% - PFAD%  (spent earth, gums, moisture)
    -- product quality (latest LIMS result)
    rbdpo_ffa_pct         REAL,
    color_red             REAL,
    rbdpo_moisture_pct    REAL,
    peroxide_value        REAL,
    has_lab_result        INTEGER,
    is_off_spec           INTEGER,
    off_spec_reason       TEXT,
    -- utilities
    steam_mt              REAL,
    electricity_kwh       REAL,
    steam_per_mt_cpo      REAL,
    kwh_per_mt_cpo        REAL,
    -- data quality audit trail
    dq_flags              TEXT
);

CREATE TABLE fact_downtime (
    event_id        TEXT PRIMARY KEY,
    line_code       TEXT REFERENCES dim_line(line_code),
    area            TEXT,
    event_date      DATE REFERENCES dim_date(date_key),   -- production day (07:00 -> 07:00)
    shift           TEXT,
    start_time      DATETIME,
    end_time        DATETIME,
    duration_min    REAL,
    category        TEXT,
    description     TEXT,
    is_planned      INTEGER,
    dq_flags        TEXT
);

CREATE TABLE fact_market_price (
    year_month          TEXT PRIMARY KEY,
    cpo_price_myr_mt    REAL,
    rbdpo_price_myr_mt  REAL,
    pfad_price_myr_mt   REAL
);

CREATE TABLE dq_log (
    step_no      INTEGER,
    source_table TEXT,
    rule         TEXT,
    action       TEXT,
    rows_affected INTEGER
);
