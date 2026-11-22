/* ============================================================================
   03_analysis_queries.sql  -  Business questions answered in SQL
   Each query is tagged "-- @name: qNN_xxx"; python/03_run_sql_pipeline.py
   runs them and saves each result to outputs/sql_results/qNN_xxx.csv

   Techniques shown: CTEs, window functions (LAG, RANK, running SUM, moving
   AVG), conditional aggregation (pivot), CASE bucketing, z-score outlier
   detection, self-referencing benchmarks.
   ========================================================================== */

-- @name: q01_headline_kpis
-- Q: What did the refinery deliver over the 18 months?
SELECT
    COUNT(*)                                                     AS batches,
    ROUND(SUM(cpo_input_mt) / 1000, 1)                           AS cpo_processed_kt,
    ROUND(SUM(rbdpo_output_mt) / 1000, 1)                        AS rbdpo_produced_kt,
    ROUND(SUM(rbdpo_output_mt) / SUM(cpo_input_mt) * 100, 2)     AS refining_yield_pct,
    ROUND(AVG(is_off_spec) * 100, 2)                             AS off_spec_rate_pct,
    ROUND(SUM(steam_mt) / SUM(cpo_input_mt), 4)                  AS steam_t_per_t_cpo,
    ROUND(SUM(electricity_kwh) / SUM(cpo_input_mt), 1)           AS kwh_per_t_cpo,
    ROUND(SUM(gross_margin_myr) / 1e6, 2)                        AS gross_margin_myr_m,
    (SELECT ROUND(SUM(duration_min) / 60.0, 0) FROM fact_downtime) AS downtime_hours
FROM vw_batch_enriched;

-- @name: q02_monthly_trend_mom
-- Q: How is yield trending month on month, and what changed vs last month?
WITH m AS (
    SELECT year_month,
           SUM(cpo_input_mt)                                   AS cpo_mt,
           SUM(rbdpo_output_mt) / SUM(cpo_input_mt) * 100      AS yield_pct,
           SUM(cpo_input_mt * cpo_ffa_pct) / SUM(cpo_input_mt) AS cpo_ffa_pct,
           AVG(is_off_spec) * 100                              AS off_spec_pct
    FROM vw_batch_enriched GROUP BY year_month
)
SELECT year_month,
       ROUND(cpo_mt, 0)                                         AS cpo_processed_mt,
       ROUND(yield_pct, 2)                                      AS refining_yield_pct,
       ROUND(yield_pct - LAG(yield_pct) OVER (ORDER BY year_month), 2) AS yield_change_vs_prev_month,
       ROUND(cpo_ffa_pct, 2)                                    AS wtd_cpo_ffa_pct,
       ROUND(off_spec_pct, 2)                                   AS off_spec_rate_pct
FROM m ORDER BY year_month;

-- @name: q03_supplier_ranking
-- Q: Which mills supply the best crude oil, and what is each worth per tonne?
SELECT *,
       RANK() OVER (ORDER BY refining_yield_pct DESC) AS yield_rank,
       RANK() OVER (ORDER BY margin_myr_per_t DESC)   AS margin_rank
FROM vw_supplier_scorecard
ORDER BY yield_rank;

-- @name: q04_ffa_band_vs_yield
-- Q: How strongly does crude FFA drive refining yield? (data mining by banding)
SELECT
    CASE WHEN cpo_ffa_pct < 3.0 THEN '1) < 3.0 %'
         WHEN cpo_ffa_pct < 3.5 THEN '2) 3.0 - 3.5 %'
         WHEN cpo_ffa_pct < 4.0 THEN '3) 3.5 - 4.0 %'
         WHEN cpo_ffa_pct < 4.5 THEN '4) 4.0 - 4.5 %'
         WHEN cpo_ffa_pct < 5.0 THEN '5) 4.5 - 5.0 %'
         ELSE                        '6) >= 5.0 %' END                AS cpo_ffa_band,
    COUNT(*)                                                         AS batches,
    ROUND(SUM(rbdpo_output_mt) / SUM(cpo_input_mt) * 100, 2)         AS refining_yield_pct,
    ROUND(SUM(pfad_output_mt)  / SUM(cpo_input_mt) * 100, 2)         AS pfad_yield_pct,
    ROUND(SUM(gross_margin_myr) / SUM(cpo_input_mt), 1)              AS margin_myr_per_t
FROM vw_batch_enriched
GROUP BY 1 ORDER BY 1;

-- @name: q05_dobi_band_vs_bleaching
-- Q: Does poor bleachability (low DOBI) cost us bleaching earth and colour?
SELECT
    CASE WHEN cpo_dobi < 2.0 THEN '1) < 2.0 (poor)'
         WHEN cpo_dobi < 2.3 THEN '2) 2.0 - 2.3 (fair)'
         WHEN cpo_dobi < 2.6 THEN '3) 2.3 - 2.6 (good)'
         ELSE                     '4) >= 2.6 (excellent)' END        AS dobi_band,
    COUNT(*)                                                         AS batches,
    ROUND(AVG(bleaching_earth_pct), 3)                               AS avg_bleaching_earth_pct,
    ROUND(AVG(color_red), 2)                                         AS avg_color_red,
    ROUND(100.0 * SUM(CASE WHEN color_red > 3.0 THEN 1 ELSE 0 END) / COUNT(color_red), 2) AS dark_colour_rate_pct
FROM fact_batch
WHERE cpo_dobi IS NOT NULL
GROUP BY 1 ORDER BY 1;

-- @name: q06_offspec_line_by_shift
-- Q: Where do off-spec batches happen? (pivot with conditional aggregation)
SELECT line_code,
       ROUND(100.0 * AVG(CASE WHEN shift = 'Morning' THEN is_off_spec END), 2) AS morning_pct,
       ROUND(100.0 * AVG(CASE WHEN shift = 'Evening' THEN is_off_spec END), 2) AS evening_pct,
       ROUND(100.0 * AVG(CASE WHEN shift = 'Night'   THEN is_off_spec END), 2) AS night_pct,
       ROUND(100.0 * AVG(is_off_spec), 2)                                       AS all_shifts_pct,
       SUM(is_off_spec)                                                         AS off_spec_batches
FROM fact_batch
GROUP BY line_code ORDER BY line_code;

-- @name: q07_deo_conditions_vs_ffa
-- Q: What deodorizer temperature keeps RBDPO FFA in spec (<= 0.10 %)?
SELECT
    CAST(deo_temp_c / 2 AS INTEGER) * 2 || '-' || (CAST(deo_temp_c / 2 AS INTEGER) * 2 + 2) || ' C' AS deo_temp_band,
    COUNT(*)                                                        AS batches,
    ROUND(AVG(deo_vacuum_mbar), 2)                                  AS avg_vacuum_mbar,
    ROUND(AVG(rbdpo_ffa_pct), 3)                                    AS avg_rbdpo_ffa_pct,
    ROUND(100.0 * AVG(CASE WHEN rbdpo_ffa_pct > 0.10 THEN 1.0 ELSE 0 END), 2) AS high_ffa_rate_pct,
    ROUND(AVG(steam_per_mt_cpo), 4)                                 AS steam_t_per_t
FROM fact_batch
WHERE has_lab_result = 1
GROUP BY CAST(deo_temp_c / 2 AS INTEGER)
HAVING COUNT(*) >= 20
ORDER BY MIN(deo_temp_c);

-- @name: q08_downtime_pareto
-- Q: Which 20 % of causes drive 80 % of lost time? (running total window)
SELECT * FROM vw_downtime_pareto ORDER BY hours DESC;

-- @name: q09_downtime_by_line
-- Q: Is the old Line C really less reliable? Lost hours per 1000 t processed
WITH dt AS (SELECT line_code, COUNT(*) AS events, SUM(duration_min) / 60.0 AS hours
            FROM fact_downtime WHERE is_planned = 0 GROUP BY line_code),
     pr AS (SELECT line_code, SUM(cpo_input_mt) AS cpo_mt FROM fact_batch GROUP BY line_code)
SELECT l.line_code, l.commissioned_year,
       dt.events                                        AS unplanned_events,
       ROUND(dt.hours, 1)                               AS unplanned_hours,
       ROUND(dt.hours / (pr.cpo_mt / 1000), 2)          AS hours_per_kt_cpo,
       ROUND(24.0 * 547 / NULLIF(dt.events, 0), 0)      AS mtbf_hours      -- mean time between failures (18 months)
FROM dim_line l
JOIN dt ON dt.line_code = l.line_code
JOIN pr ON pr.line_code = l.line_code
ORDER BY l.line_code;

-- @name: q10_energy_outliers_zscore
-- Q: Which batches used abnormally high steam? (z-score within each line)
WITH s AS (
    SELECT batch_id, production_date, line_code, shift, deo_temp_c, steam_per_mt_cpo,
           AVG(steam_per_mt_cpo) OVER (PARTITION BY line_code)                          AS mu,
           sqrt(AVG(steam_per_mt_cpo * steam_per_mt_cpo) OVER (PARTITION BY line_code)
                - power(AVG(steam_per_mt_cpo) OVER (PARTITION BY line_code), 2))        AS sigma
    FROM fact_batch WHERE steam_per_mt_cpo IS NOT NULL
)
SELECT batch_id, production_date, line_code, shift, deo_temp_c,
       ROUND(steam_per_mt_cpo, 4) AS steam_t_per_t,
       ROUND(mu, 4)               AS line_avg,
       ROUND((steam_per_mt_cpo - mu) / sigma, 2) AS z_score
FROM s
WHERE ABS((steam_per_mt_cpo - mu) / sigma) > 3
ORDER BY z_score DESC;

-- @name: q11_rolling_7day_yield
-- Q: Smooth out the daily noise - 7-day moving average yield for the plant
WITH d AS (
    SELECT production_date,
           SUM(rbdpo_output_mt) AS rbdpo, SUM(cpo_input_mt) AS cpo
    FROM fact_batch GROUP BY production_date
)
SELECT production_date,
       ROUND(rbdpo / cpo * 100, 2) AS daily_yield_pct,
       ROUND(SUM(rbdpo) OVER w / SUM(cpo) OVER w * 100, 2) AS yield_7d_avg_pct
FROM d
WINDOW w AS (ORDER BY production_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
ORDER BY production_date;

-- @name: q12_value_of_supplier_quality
-- Q: How much margin would we gain if every mill matched our best mill's yield?
WITH s AS (SELECT * FROM vw_supplier_scorecard),
     best AS (SELECT MAX(refining_yield_pct) AS best_yield FROM s),
     px AS (SELECT AVG(rbdpo_price_myr_mt) AS rbdpo_px FROM fact_market_price)
SELECT s.supplier_name, s.cpo_supplied_mt, s.refining_yield_pct, s.wtd_cpo_ffa_pct,
       ROUND(best.best_yield - s.refining_yield_pct, 2)                                   AS yield_gap_pts,
       ROUND((best.best_yield - s.refining_yield_pct) / 100 * s.cpo_supplied_mt, 0)       AS rbdpo_lost_mt,
       ROUND((best.best_yield - s.refining_yield_pct) / 100 * s.cpo_supplied_mt * px.rbdpo_px / 1e6, 2) AS opportunity_myr_m
FROM s, best, px
ORDER BY opportunity_myr_m DESC;

-- @name: q13_peak_vs_normal_season
-- Q: How much does the peak crop season hurt crude quality and yield?
SELECT crop_season,
       COUNT(*)                                                       AS batches,
       ROUND(SUM(cpo_input_mt * cpo_ffa_pct) / SUM(cpo_input_mt), 2)  AS wtd_cpo_ffa_pct,
       ROUND(SUM(rbdpo_output_mt) / SUM(cpo_input_mt) * 100, 2)       AS refining_yield_pct,
       ROUND(AVG(is_off_spec) * 100, 2)                               AS off_spec_rate_pct
FROM vw_batch_enriched
GROUP BY crop_season;

-- @name: q14_operator_offspec
-- Q: Are some crews struggling? (min 100 batches to be fair)
SELECT operator_id, COUNT(*) AS batches,
       ROUND(AVG(is_off_spec) * 100, 2) AS off_spec_rate_pct,
       ROUND(SUM(rbdpo_output_mt) / SUM(cpo_input_mt) * 100, 2) AS refining_yield_pct,
       NTILE(4) OVER (ORDER BY AVG(is_off_spec)) AS quartile_1_best
FROM fact_batch
GROUP BY operator_id
HAVING COUNT(*) >= 100
ORDER BY off_spec_rate_pct DESC;

-- @name: q15_data_quality_summary
-- Q: How clean is the final model? Batches touched by each repair rule
SELECT step_no, source_table, rule, action, rows_affected FROM dq_log ORDER BY step_no;
