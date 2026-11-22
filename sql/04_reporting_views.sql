/* ============================================================================
   04_reporting_views.sql  -  Semantic layer consumed by Power BI / Excel
   ========================================================================== */

DROP VIEW IF EXISTS vw_batch_enriched;
DROP VIEW IF EXISTS vw_monthly_line_kpi;
DROP VIEW IF EXISTS vw_supplier_scorecard;
DROP VIEW IF EXISTS vw_downtime_pareto;

-- One row per batch with dimensions and the batch's gross refining margin.
-- Gross refining margin = product value (RBDPO + PFAD) - feedstock cost (CPO),
-- at that month's market prices. Processing costs (steam, power, chemicals,
-- labour) are excluded, so this is the value created by yield alone.
CREATE VIEW vw_batch_enriched AS
SELECT
    b.*,
    d.year, d.quarter, d.month_no, d.month_name, d.year_month, d.crop_season,
    l.line_name, l.commissioned_year,
    s.supplier_name, s.state AS supplier_state, s.region AS supplier_region, s.certification,
    p.cpo_price_myr_mt, p.rbdpo_price_myr_mt, p.pfad_price_myr_mt,
    ROUND(b.rbdpo_output_mt * p.rbdpo_price_myr_mt + b.pfad_output_mt * p.pfad_price_myr_mt, 0) AS product_value_myr,
    ROUND(b.cpo_input_mt * p.cpo_price_myr_mt, 0)                                               AS feedstock_cost_myr,
    ROUND(b.rbdpo_output_mt * p.rbdpo_price_myr_mt + b.pfad_output_mt * p.pfad_price_myr_mt
          - b.cpo_input_mt * p.cpo_price_myr_mt, 0)                                             AS gross_margin_myr
FROM fact_batch b
JOIN dim_date d          ON d.date_key   = b.production_date
JOIN dim_line l          ON l.line_code  = b.line_code
LEFT JOIN dim_supplier s ON s.supplier_id = b.supplier_id
LEFT JOIN fact_market_price p ON p.year_month = d.year_month;

-- Month x line KPIs. Ratios are recomputed from sums (never average of averages).
CREATE VIEW vw_monthly_line_kpi AS
SELECT
    year_month, line_code,
    COUNT(*)                                                         AS batches,
    ROUND(SUM(cpo_input_mt), 1)                                      AS cpo_processed_mt,
    ROUND(SUM(rbdpo_output_mt), 1)                                   AS rbdpo_produced_mt,
    ROUND(SUM(rbdpo_output_mt) / SUM(cpo_input_mt) * 100, 2)         AS refining_yield_pct,
    ROUND(SUM(cpo_input_mt * cpo_ffa_pct) / SUM(cpo_input_mt), 2)    AS wtd_cpo_ffa_pct,
    ROUND(AVG(is_off_spec) * 100, 2)                                 AS off_spec_rate_pct,
    ROUND(SUM(steam_mt) / SUM(cpo_input_mt), 4)                      AS steam_t_per_t,
    ROUND(SUM(electricity_kwh) / SUM(cpo_input_mt), 2)               AS kwh_per_t,
    ROUND(SUM(gross_margin_myr), 0)                                  AS gross_margin_myr
FROM vw_batch_enriched
GROUP BY year_month, line_code;

CREATE VIEW vw_supplier_scorecard AS
SELECT
    supplier_id, supplier_name, supplier_region, certification,
    COUNT(*)                                                         AS batches,
    ROUND(SUM(cpo_input_mt), 0)                                      AS cpo_supplied_mt,
    ROUND(SUM(cpo_input_mt * cpo_ffa_pct) / SUM(cpo_input_mt), 2)    AS wtd_cpo_ffa_pct,
    ROUND(AVG(cpo_dobi), 2)                                          AS avg_dobi,
    ROUND(AVG(bleaching_earth_pct), 2)                               AS avg_bleaching_earth_pct,
    ROUND(SUM(rbdpo_output_mt) / SUM(cpo_input_mt) * 100, 2)         AS refining_yield_pct,
    ROUND(AVG(is_off_spec) * 100, 2)                                 AS off_spec_rate_pct,
    ROUND(SUM(gross_margin_myr) / SUM(cpo_input_mt), 1)              AS margin_myr_per_t
FROM vw_batch_enriched
GROUP BY supplier_id, supplier_name, supplier_region, certification;

CREATE VIEW vw_downtime_pareto AS
WITH c AS (
    SELECT category, COUNT(*) AS events, SUM(duration_min) / 60.0 AS hours
    FROM fact_downtime GROUP BY category
)
SELECT category, events, ROUND(hours, 1) AS hours,
       ROUND(100.0 * hours / SUM(hours) OVER (), 1)                                              AS pct_of_total,
       ROUND(100.0 * SUM(hours) OVER (ORDER BY hours DESC ROWS UNBOUNDED PRECEDING) / SUM(hours) OVER (), 1) AS cumulative_pct
FROM c;
