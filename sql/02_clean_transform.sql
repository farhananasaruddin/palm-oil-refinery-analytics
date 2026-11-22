/* ============================================================================
   02_clean_transform.sql  -  CLEAN + TRANSFORM  (staging -> star schema)
   Dialect: SQLite 3.25+ (window functions, recursive CTEs)

   Every cleaning rule is logged to dq_log with the number of rows it touched,
   and every repaired batch carries a dq_flags audit string, so any number in
   the dashboard can be traced back to the raw file.
   ========================================================================== */

/* ---------------------------------------------------------------------------
   0. Master / reference data
   ------------------------------------------------------------------------- */
INSERT INTO dim_line VALUES
    ('A', 'Line A', 600, 2012),
    ('B', 'Line B', 600, 2016),
    ('C', 'Line C', 420, 2005);

INSERT INTO dim_supplier
SELECT trim(supplier_id),
       trim(supplier_name),
       trim(state),
       CASE WHEN trim(state) IN ('Sabah', 'Sarawak') THEN 'East Malaysia' ELSE 'Peninsular' END,
       trim(certification),
       CAST(distance_km AS REAL),
       date(substr(trim(contract_start), 1, 10))
FROM stg_suppliers;

-- Official names + every hand-typed variant found during profiling
INSERT INTO map_supplier_alias
SELECT upper(replace(replace(replace(supplier_name, ' ', ''), '.', ''), '-', '')), supplier_id
FROM dim_supplier;
INSERT INTO map_supplier_alias VALUES
    ('LADANGSGMASMILL', 'SUP01'),
    ('BUKITHIJAUPOM',   'SUP02'),
    ('KUALATERASSMILL', 'SUP03'),
    ('SRIMUTIARAMILL',  'SUP04'),
    ('TGEMASMILL',      'SUP05');

INSERT INTO fact_market_price
SELECT trim(month), CAST(cpo_price_myr_mt AS REAL), CAST(rbdpo_price_myr_mt AS REAL), CAST(pfad_price_myr_mt AS REAL)
FROM stg_market_prices;

/* ---------------------------------------------------------------------------
   1. Batch production: de-duplicate, standardise labels, parse dates, cast
   ------------------------------------------------------------------------- */
INSERT INTO dq_log
SELECT 1, 'stg_batch_production', 'Duplicate batch_id rows', 'Kept first occurrence',
       (SELECT COUNT(*) FROM stg_batch_production) - (SELECT COUNT(DISTINCT trim(batch_id)) FROM stg_batch_production);

DROP TABLE IF EXISTS tmp_batch;
CREATE TABLE tmp_batch AS
WITH ranked AS (
    SELECT s.*,
           ROW_NUMBER() OVER (PARTITION BY trim(batch_id) ORDER BY _source_row) AS rn,
           trim(production_date) AS d
    FROM stg_batch_production s
)
SELECT
    trim(r.batch_id) AS batch_id,
    -- three date formats arrive from different plant PCs
    CASE
        WHEN d GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN d
        WHEN d GLOB '[0-9][0-9]/[0-9][0-9]/[0-9][0-9][0-9][0-9]'
             THEN substr(d, 7, 4) || '-' || substr(d, 4, 2) || '-' || substr(d, 1, 2)
        WHEN d GLOB '[0-9][0-9]-[A-Za-z][A-Za-z][A-Za-z]-[0-9][0-9][0-9][0-9]'
             THEN substr(d, 8, 4) || '-'
                  || printf('%02d', (instr('JANFEBMARAPRMAYJUNJULAUGSEPOCTNOVDEC', upper(substr(d, 4, 3))) + 2) / 3)
                  || '-' || substr(d, 1, 2)
    END AS production_date,
    CASE upper(trim(r.shift))
        WHEN 'MORNING' THEN 'Morning' WHEN 'AM' THEN 'Morning'
        WHEN 'EVENING' THEN 'Evening' WHEN 'PM' THEN 'Evening'
        WHEN 'NIGHT'   THEN 'Night'   WHEN 'NIGHT SHIFT' THEN 'Night'
    END AS shift,
    substr(upper(trim(r.line)), -1) AS line_code,          -- 'Line A' / 'LINE-A' / 'a' -> 'A'
    m.supplier_id,
    trim(r.operator_id) AS operator_id,
    CASE WHEN trim(cpo_input_mt)    IN ('', 'N/A', '-') THEN NULL ELSE CAST(cpo_input_mt AS REAL)    END AS cpo_input_mt,
    CASE WHEN trim(cpo_ffa_pct)     IN ('', 'N/A', '-') THEN NULL ELSE CAST(cpo_ffa_pct AS REAL)     END AS cpo_ffa_pct,
    CASE WHEN trim(cpo_dobi)        IN ('', 'N/A', '-') THEN NULL ELSE CAST(cpo_dobi AS REAL)        END AS cpo_dobi,
    CAST(cpo_moisture_pct AS REAL)    AS cpo_moisture_pct,
    CAST(bleaching_earth_pct AS REAL) AS bleaching_earth_pct,
    CAST(phosphoric_acid_pct AS REAL) AS phosphoric_acid_pct,
    CASE WHEN trim(deo_temp_c)      IN ('', 'N/A', '-') THEN NULL ELSE CAST(deo_temp_c AS REAL)      END AS deo_temp_c,
    CAST(deo_vacuum_mbar AS REAL)     AS deo_vacuum_mbar,
    CASE WHEN trim(rbdpo_output_mt) IN ('', 'N/A', '-') THEN NULL ELSE CAST(rbdpo_output_mt AS REAL) END AS rbdpo_output_mt,
    CAST(pfad_output_mt AS REAL)      AS pfad_output_mt,
    ''  AS dq_flags,
    trim(r.production_date) AS raw_date,
    trim(r.line)            AS raw_line,
    trim(r.shift)           AS raw_shift,
    r.supplier              AS raw_supplier
FROM ranked r
LEFT JOIN map_supplier_alias m
       ON m.alias_key = upper(replace(replace(replace(trim(r.supplier), ' ', ''), '.', ''), '-', ''))
WHERE r.rn = 1;

INSERT INTO dq_log SELECT 2, 'stg_batch_production', 'Non-ISO date formats (DD/MM/YYYY, DD-Mon-YYYY)', 'Parsed to YYYY-MM-DD',
    COUNT(*) FROM tmp_batch WHERE raw_date <> production_date;
INSERT INTO dq_log SELECT 3, 'stg_batch_production', 'Unparseable dates', 'Row excluded',
    COUNT(*) FROM tmp_batch WHERE production_date IS NULL;
INSERT INTO dq_log SELECT 4, 'stg_batch_production', 'Inconsistent line labels (LINE-A, line a, A)', 'Standardised to A/B/C',
    COUNT(*) FROM tmp_batch WHERE raw_line NOT IN ('Line A', 'Line B', 'Line C');
INSERT INTO dq_log SELECT 5, 'stg_batch_production', 'Inconsistent shift labels (AM, PM, NIGHT SHIFT)', 'Standardised to Morning/Evening/Night',
    COUNT(*) FROM tmp_batch WHERE raw_shift NOT IN ('Morning', 'Evening', 'Night');
INSERT INTO dq_log SELECT 6, 'stg_batch_production', 'Supplier name typos / abbreviations / casing', 'Mapped to supplier_id via alias table',
    COUNT(*) FROM tmp_batch t JOIN dim_supplier s ON s.supplier_id = t.supplier_id WHERE t.raw_supplier <> s.supplier_name;
INSERT INTO dq_log SELECT 7, 'stg_batch_production', 'Unmapped supplier names', 'Left NULL - add to alias table',
    COUNT(*) FROM tmp_batch WHERE supplier_id IS NULL;

/* ---------------------------------------------------------------------------
   2. Batch production: repair values using engineering rules
   ------------------------------------------------------------------------- */
-- 2a. FFA keyed as a fraction (0.038) instead of percent (3.8). CPO FFA is never < 1 %.
INSERT INTO dq_log SELECT 8, 'stg_batch_production', 'CPO FFA entered as fraction (< 1)', 'Multiplied by 100',
    COUNT(*) FROM tmp_batch WHERE cpo_ffa_pct < 1;
UPDATE tmp_batch SET cpo_ffa_pct = cpo_ffa_pct * 100, dq_flags = dq_flags || 'FFA_FRACTION;' WHERE cpo_ffa_pct < 1;

-- 2b. Deodorizer temperature with lost decimal point (2625 -> 262.5). Physical range 230-280 C.
INSERT INTO dq_log SELECT 9, 'stg_batch_production', 'Deodorizer temp > 1000 C (decimal lost)', 'Divided by 10',
    COUNT(*) FROM tmp_batch WHERE deo_temp_c > 1000;
UPDATE tmp_batch SET deo_temp_c = deo_temp_c / 10, dq_flags = dq_flags || 'TEMP_DECIMAL;' WHERE deo_temp_c > 1000;

-- 2c. Deodorizer temperature missing (sensor offline) -> impute with that line's mean
INSERT INTO dq_log SELECT 10, 'stg_batch_production', 'Deodorizer temp missing (blank / N/A / -)', 'Imputed with line average',
    COUNT(*) FROM tmp_batch WHERE deo_temp_c IS NULL;
UPDATE tmp_batch
SET deo_temp_c = (SELECT ROUND(AVG(t2.deo_temp_c), 1) FROM tmp_batch t2
                  WHERE t2.line_code = tmp_batch.line_code AND t2.deo_temp_c IS NOT NULL),
    dq_flags   = dq_flags || 'TEMP_IMPUTED;'
WHERE deo_temp_c IS NULL;

-- 2d. Negative CPO input (sign error on weighbridge entry)
INSERT INTO dq_log SELECT 11, 'stg_batch_production', 'Negative CPO input tonnage', 'Absolute value taken',
    COUNT(*) FROM tmp_batch WHERE cpo_input_mt < 0;
UPDATE tmp_batch SET cpo_input_mt = ABS(cpo_input_mt), dq_flags = dq_flags || 'INPUT_SIGN;' WHERE cpo_input_mt < 0;

-- 2e. Missing CPO input or RBDPO output -> close the MASS BALANCE.
--     CPO in = RBDPO + PFAD + losses (spent earth, gums, moisture). Typical loss
--     is the median of complete batches (computed here, ~1.4 %).
DROP TABLE IF EXISTS tmp_loss;
CREATE TABLE tmp_loss AS
WITH l AS (
    SELECT 100.0 - (rbdpo_output_mt + pfad_output_mt) / cpo_input_mt * 100 AS loss_pct,
           ROW_NUMBER() OVER (ORDER BY 100.0 - (rbdpo_output_mt + pfad_output_mt) / cpo_input_mt * 100) AS rn,
           COUNT(*) OVER () AS n
    FROM tmp_batch
    WHERE cpo_input_mt IS NOT NULL AND rbdpo_output_mt IS NOT NULL
)
SELECT ROUND(AVG(loss_pct), 3) AS median_loss_pct FROM l WHERE rn IN ((n + 1) / 2, (n + 2) / 2);

INSERT INTO dq_log SELECT 12, 'stg_batch_production', 'CPO input missing', 'Back-calculated from mass balance',
    COUNT(*) FROM tmp_batch WHERE cpo_input_mt IS NULL AND rbdpo_output_mt IS NOT NULL;
UPDATE tmp_batch
SET cpo_input_mt = ROUND((rbdpo_output_mt + pfad_output_mt) / (1 - (SELECT median_loss_pct FROM tmp_loss) / 100), 2),
    dq_flags     = dq_flags || 'INPUT_MASS_BALANCE;'
WHERE cpo_input_mt IS NULL AND rbdpo_output_mt IS NOT NULL;

INSERT INTO dq_log SELECT 13, 'stg_batch_production', 'RBDPO output missing', 'Back-calculated from mass balance',
    COUNT(*) FROM tmp_batch WHERE rbdpo_output_mt IS NULL AND cpo_input_mt IS NOT NULL;
UPDATE tmp_batch
SET rbdpo_output_mt = ROUND(cpo_input_mt * (1 - (SELECT median_loss_pct FROM tmp_loss) / 100) - pfad_output_mt, 2),
    dq_flags        = dq_flags || 'OUTPUT_MASS_BALANCE;'
WHERE rbdpo_output_mt IS NULL AND cpo_input_mt IS NOT NULL;

INSERT INTO dq_log SELECT 14, 'stg_batch_production', 'CPO DOBI missing', 'Left NULL (excluded from DOBI analysis only)',
    COUNT(*) FROM tmp_batch WHERE cpo_dobi IS NULL;
UPDATE tmp_batch SET dq_flags = dq_flags || 'DOBI_MISSING;' WHERE cpo_dobi IS NULL;

/* ---------------------------------------------------------------------------
   3. Lab results (LIMS): keep the latest re-test, parse text values
   ------------------------------------------------------------------------- */
INSERT INTO dq_log SELECT 15, 'stg_lab_results', 'Re-tests (multiple samples per batch)', 'Kept latest test result',
    COUNT(*) - COUNT(DISTINCT trim(batch_ref)) FROM stg_lab_results;
INSERT INTO dq_log SELECT 16, 'stg_lab_results', 'FFA below detection limit ("<0.03")', 'Set to detection limit 0.03',
    COUNT(*) FROM stg_lab_results WHERE trim(rbdpo_ffa_pct) LIKE '<%';
INSERT INTO dq_log SELECT 17, 'stg_lab_results', 'Colour recorded with unit suffix ("2.8R")', 'Suffix stripped, cast to number',
    COUNT(*) FROM stg_lab_results WHERE upper(trim(color_lovibond_red)) LIKE '%R';
INSERT INTO dq_log SELECT 18, 'stg_lab_results', 'Moisture result blank', 'Left NULL',
    COUNT(*) FROM stg_lab_results WHERE trim(moisture_pct) = '';

DROP TABLE IF EXISTS tmp_lab;
CREATE TABLE tmp_lab AS
WITH ranked AS (
    SELECT l.*, ROW_NUMBER() OVER (PARTITION BY trim(batch_ref) ORDER BY test_datetime DESC) AS rn
    FROM stg_lab_results l
)
SELECT trim(batch_ref) AS batch_id,
       CASE WHEN trim(rbdpo_ffa_pct) LIKE '<%' THEN CAST(substr(trim(rbdpo_ffa_pct), 2) AS REAL)
            ELSE CAST(rbdpo_ffa_pct AS REAL) END                         AS rbdpo_ffa_pct,
       CAST(rtrim(upper(trim(color_lovibond_red)), 'R') AS REAL)         AS color_red,
       CASE WHEN trim(moisture_pct) = '' THEN NULL ELSE CAST(moisture_pct AS REAL) END AS rbdpo_moisture_pct,
       CAST(peroxide_value AS REAL)                                      AS peroxide_value
FROM ranked WHERE rn = 1;

/* ---------------------------------------------------------------------------
   4. Energy meters: harmonise units
   ------------------------------------------------------------------------- */
INSERT INTO dq_log SELECT 19, 'stg_energy_readings', 'Electricity reported in MWh', 'Converted to kWh (x1000)',
    COUNT(*) FROM stg_energy_readings WHERE trim(electricity_unit) = 'MWh';

DROP TABLE IF EXISTS tmp_energy;
CREATE TABLE tmp_energy AS
SELECT trim(batch_id) AS batch_id,
       CAST(steam_mt AS REAL) AS steam_mt,
       CASE WHEN trim(electricity_unit) = 'MWh' THEN CAST(electricity AS REAL) * 1000
            ELSE CAST(electricity AS REAL) END AS electricity_kwh
FROM stg_energy_readings;

/* ---------------------------------------------------------------------------
   5. Build fact_batch  (batch + lab + energy, with derived KPIs)
   ------------------------------------------------------------------------- */
INSERT INTO fact_batch
SELECT
    b.batch_id, b.production_date, b.shift, b.line_code, b.supplier_id, b.operator_id,
    b.cpo_input_mt, b.cpo_ffa_pct, b.cpo_dobi, b.cpo_moisture_pct,
    b.bleaching_earth_pct, b.phosphoric_acid_pct, b.deo_temp_c, b.deo_vacuum_mbar,
    b.rbdpo_output_mt, b.pfad_output_mt,
    ROUND(b.rbdpo_output_mt / b.cpo_input_mt * 100, 3)                                        AS refining_yield_pct,
    ROUND(b.pfad_output_mt  / b.cpo_input_mt * 100, 3)                                        AS pfad_yield_pct,
    ROUND(100 - (b.rbdpo_output_mt + b.pfad_output_mt) / b.cpo_input_mt * 100, 3)            AS refining_loss_pct,
    l.rbdpo_ffa_pct, l.color_red, l.rbdpo_moisture_pct, l.peroxide_value,
    CASE WHEN l.batch_id IS NULL THEN 0 ELSE 1 END                                            AS has_lab_result,
    CASE WHEN l.batch_id IS NULL THEN NULL
         WHEN l.rbdpo_ffa_pct > 0.10 OR l.color_red > 3.0 OR l.rbdpo_moisture_pct > 0.10 THEN 1
         ELSE 0 END                                                                           AS is_off_spec,
    CASE WHEN l.batch_id IS NULL THEN 'No lab result'
         ELSE COALESCE(NULLIF(rtrim(
                CASE WHEN l.rbdpo_ffa_pct > 0.10      THEN 'High FFA, '   ELSE '' END ||
                CASE WHEN l.color_red > 3.0           THEN 'Dark colour, ' ELSE '' END ||
                CASE WHEN l.rbdpo_moisture_pct > 0.10 THEN 'High moisture, ' ELSE '' END, ', '), ''), 'In spec')
    END                                                                                       AS off_spec_reason,
    e.steam_mt, e.electricity_kwh,
    ROUND(e.steam_mt / b.cpo_input_mt, 4)                                                     AS steam_per_mt_cpo,
    ROUND(e.electricity_kwh / b.cpo_input_mt, 2)                                              AS kwh_per_mt_cpo,
    b.dq_flags || CASE WHEN l.batch_id IS NULL THEN 'NO_LAB;' ELSE '' END
               || CASE WHEN e.batch_id IS NULL THEN 'NO_ENERGY;' ELSE '' END                  AS dq_flags
FROM tmp_batch b
LEFT JOIN tmp_lab    l ON l.batch_id = b.batch_id
LEFT JOIN tmp_energy e ON e.batch_id = b.batch_id
WHERE b.production_date IS NOT NULL;

INSERT INTO dq_log SELECT 20, 'fact_batch', 'Batches with no LIMS result', 'Kept; excluded from quality KPIs',
    COUNT(*) FROM fact_batch WHERE has_lab_result = 0;
INSERT INTO dq_log SELECT 21, 'fact_batch', 'Refining yield outside 85-99 % (sanity check)', 'Flagged for review',
    COUNT(*) FROM fact_batch WHERE refining_yield_pct NOT BETWEEN 85 AND 99;
UPDATE fact_batch SET dq_flags = dq_flags || 'YIELD_OUT_OF_RANGE;' WHERE refining_yield_pct NOT BETWEEN 85 AND 99;

/* ---------------------------------------------------------------------------
   6. Downtime events (flattened CMMS JSON)
   ------------------------------------------------------------------------- */
INSERT INTO dq_log SELECT 22, 'stg_downtime_log', 'Category casing inconsistent (VACUUM SYSTEM, mechanical)', 'Standardised to Title Case',
    COUNT(*) FROM stg_downtime_log
    WHERE trim(cause_category) NOT IN ('Mechanical', 'Vacuum System', 'Filtration', 'Utilities', 'Electrical', 'Feedstock Shortage', 'Planned Maintenance');
INSERT INTO dq_log SELECT 23, 'stg_downtime_log', 'Event with no end time', 'Duration imputed with category average',
    COUNT(*) FROM stg_downtime_log WHERE trim(timing_end_time) = '';

INSERT INTO fact_downtime
SELECT
    trim(event_id),
    substr(upper(trim(asset_line)), -1),
    trim(asset_area),
    date(replace(timing_start_time, 'T', ' '), '-7 hours'),          -- production day starts 07:00
    CASE WHEN CAST(strftime('%H', replace(timing_start_time, 'T', ' ')) AS INTEGER) BETWEEN 7 AND 14 THEN 'Morning'
         WHEN CAST(strftime('%H', replace(timing_start_time, 'T', ' ')) AS INTEGER) BETWEEN 15 AND 22 THEN 'Evening'
         ELSE 'Night' END,
    replace(timing_start_time, 'T', ' '),
    NULLIF(replace(timing_end_time, 'T', ' '), ''),
    CASE WHEN trim(timing_end_time) = '' THEN NULL
         ELSE ROUND((julianday(replace(timing_end_time, 'T', ' ')) - julianday(replace(timing_start_time, 'T', ' '))) * 1440, 0) END,
    CASE upper(trim(cause_category))
        WHEN 'MECHANICAL'          THEN 'Mechanical'
        WHEN 'VACUUM SYSTEM'       THEN 'Vacuum System'
        WHEN 'FILTRATION'          THEN 'Filtration'
        WHEN 'UTILITIES'           THEN 'Utilities'
        WHEN 'ELECTRICAL'          THEN 'Electrical'
        WHEN 'FEEDSTOCK SHORTAGE'  THEN 'Feedstock Shortage'
        WHEN 'PLANNED MAINTENANCE' THEN 'Planned Maintenance'
        ELSE 'Other' END,
    trim(cause_description),
    CASE WHEN upper(trim(cause_category)) = 'PLANNED MAINTENANCE' THEN 1 ELSE 0 END,
    CASE WHEN trim(timing_end_time) = '' THEN 'DURATION_IMPUTED;' ELSE '' END
FROM stg_downtime_log;

UPDATE fact_downtime
SET duration_min = (SELECT ROUND(AVG(d2.duration_min), 0) FROM fact_downtime d2
                    WHERE d2.category = fact_downtime.category AND d2.duration_min IS NOT NULL),
    end_time     = NULL
WHERE duration_min IS NULL;

/* ---------------------------------------------------------------------------
   7. Date dimension (recursive CTE over the full data range)
   ------------------------------------------------------------------------- */
INSERT INTO dim_date
WITH RECURSIVE d(dt) AS (
    SELECT (SELECT MIN(production_date) FROM fact_batch)
    UNION ALL
    SELECT date(dt, '+1 day') FROM d WHERE dt < (SELECT MAX(production_date) FROM fact_batch)
)
SELECT dt,
       CAST(strftime('%Y', dt) AS INTEGER),
       'Q' || ((CAST(strftime('%m', dt) AS INTEGER) + 2) / 3),
       CAST(strftime('%m', dt) AS INTEGER),
       substr('JanFebMarAprMayJunJulAugSepOctNovDec', (CAST(strftime('%m', dt) AS INTEGER) - 1) * 3 + 1, 3),
       strftime('%Y-%m', dt),
       CAST(strftime('%W', dt) AS INTEGER),
       substr('SunMonTueWedThuFriSat', CAST(strftime('%w', dt) AS INTEGER) * 3 + 1, 3),
       CASE WHEN strftime('%w', dt) IN ('0', '6') THEN 1 ELSE 0 END,
       CASE WHEN CAST(strftime('%m', dt) AS INTEGER) BETWEEN 9 AND 11 THEN 'Peak' ELSE 'Normal' END
FROM d;

/* ---------------------------------------------------------------------------
   8. Tidy up
   ------------------------------------------------------------------------- */
DROP TABLE IF EXISTS tmp_batch;
DROP TABLE IF EXISTS tmp_lab;
DROP TABLE IF EXISTS tmp_energy;
DROP TABLE IF EXISTS tmp_loss;
