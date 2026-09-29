-- =====================================================================================================
-- Market & Iona Ops – GOLD (replaces the Tableau EMDM_Datamart views AEMO_INT287_CUR_V / VSET_INT091_CUR_V)
-- =====================================================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_vic_gas_demand_daily
COMMENT 'Daily VIC gas demand joined to actual EDD (Tableau – INT287 LEFT JOIN INT091 ON gas_date = edd_date). GJ, TJ, PJ.'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'market')
AS SELECT d.gas_date, cast(date_format(d.gas_date, 'yyyyMMdd') AS INT) AS date_key, year(d.gas_date) AS gas_year,
          month(d.gas_date) AS gas_month, date_format(d.gas_date, 'MMMM') AS gas_month_name, dayofyear(d.gas_date) AS day_of_year,
          dd.date_without_year, dd.weekday_num, dd.day_name, dd.is_weekend, dd.financial_year,
          d.total_gas_used AS total_gas_used_gj, d.total_gas_used / 1e3 AS total_gas_used_tj,
          d.total_gas_used / 1e6 AS total_gas_used_pj, e.edd_value, e.edd_type, e.edd_update,
          d.data_source AS demand_source, e.data_source AS edd_source
FROM ${lochard.silver}.slv_vic_demand_daily d
LEFT JOIN ${lochard.silver}.slv_edd_daily e ON d.gas_date = e.edd_date
LEFT JOIN ${lochard.gold}.dim_date dd       ON cast(date_format(d.gas_date, 'yyyyMMdd') AS INT) = dd.date_key;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_edd_daily
COMMENT 'Daily actual EDD with cumulative EDD by calendar year (Tableau Cumulative EDD sheets)'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'market')
AS SELECT e.edd_date, year(e.edd_date) AS edd_year, month(e.edd_date) AS edd_month, dayofyear(e.edd_date) AS day_of_year,
          dd.date_without_year, e.edd_value, e.data_source,
          sum(e.edd_value) OVER (PARTITION BY year(e.edd_date) ORDER BY e.edd_date) AS cumulative_edd
FROM ${lochard.silver}.slv_edd_daily e
LEFT JOIN ${lochard.gold}.dim_date dd ON cast(date_format(e.edd_date, 'yyyyMMdd') AS INT) = dd.date_key;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.mv_cumulative_vic_demand
COMMENT 'Cumulative VIC demand by day of year per year (Tableau RUNNING_SUM(SUM(TOTAL_GAS_USED))) in PJ'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'market')
AS SELECT gas_date, gas_year, gas_month, gas_month_name, day_of_year, date_without_year, total_gas_used_pj, edd_value,
          sum(total_gas_used_pj) OVER (PARTITION BY gas_year ORDER BY gas_date) AS cumulative_pj,
          sum(edd_value) OVER (PARTITION BY gas_year ORDER BY gas_date) AS cumulative_edd, demand_source
FROM ${lochard.gold}.fact_vic_gas_demand_daily;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_iona_operations_daily
COMMENT 'Iona daily operations – injection / withdrawal (TJ), working inventory (PJ), compressor availability, real AEMO INT313 Iona flows where available'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'operations')
AS WITH aemo AS (
  SELECT gas_date, sum(energy_flow_gj) FILTER (WHERE flow_direction = 'Injection') / 1e3 AS aemo_injection_tj,
         sum(energy_flow_gj) FILTER (WHERE flow_direction = 'Withdrawal') / 1e3 AS aemo_withdrawal_tj
  FROM ${lochard.silver}.slv_aemo_site_flows WHERE is_iona GROUP BY gas_date
)
SELECT o.gas_date, o.injection_tj, o.withdrawal_tj, o.withdrawal_tj - o.injection_tj AS net_withdrawal_tj,
       o.inventory_tj / 1e3 AS inventory_pj,
       o.inventory_tj / 1e3 / CASE WHEN o.gas_date >= DATE'2027-01-31' THEN 26.2 ELSE 24.4 END AS inventory_fill_pct,
       o.compressor_availability, a.aemo_injection_tj, a.aemo_withdrawal_tj,
       p.price_gst_ex AS market_price_gj, v.total_gas_used_tj AS vic_demand_tj, v.edd_value
FROM ${lochard.silver}.slv_iona_ops_daily o
LEFT JOIN aemo a ON o.gas_date = a.gas_date
LEFT JOIN ${lochard.silver}.slv_market_price p ON o.gas_date = p.gas_date AND p.demand_type_name = 'Normal'
LEFT JOIN ${lochard.gold}.fact_vic_gas_demand_daily v ON o.gas_date = v.gas_date;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_nomination
COMMENT 'Customer nominations vs delivered; within_tolerance = |delivered/nominated - 1| <= 4% (scorecard KPI 1.2)'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'operations')
AS SELECT n.*, d.financial_year, abs(n.delivered_tj / n.nominated_tj - 1) AS deviation_pct,
          abs(n.delivered_tj / n.nominated_tj - 1) <= 0.04 AS within_tolerance
FROM ${lochard.silver}.slv_nominations n
LEFT JOIN ${lochard.gold}.dim_date d ON cast(date_format(n.gas_date, 'yyyyMMdd') AS INT) = d.date_key;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_aemo_demand_forecast
COMMENT 'AEMO INT153 daily demand forecast (GJ) for comparison with the Lochard forecaster'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'market')
AS SELECT forecast_date, version_id, forecast_demand_gj, forecast_demand_gj / 1e3 AS forecast_demand_tj
FROM ${lochard.silver}.slv_demand_forecast;
