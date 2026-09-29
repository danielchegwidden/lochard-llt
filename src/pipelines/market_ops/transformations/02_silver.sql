-- =====================================================================================================
-- Market & Iona Ops – SILVER. AEMO wins over SYNTHETIC on the same gas day (AUTO CDC sequenced by source priority
-- then report timestamp). The live INT287 file includes the partial current gas day – dropped by expectation.
-- =====================================================================================================

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_edd_validated (
  CONSTRAINT edd_date_parsed  EXPECT (edd_date IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT edd_range        EXPECT (edd_value BETWEEN 0 AND 30),
  CONSTRAINT edd_type_actual  EXPECT (edd_type = 1)
)
COMMENT 'INT091 EDD – typed'
AS SELECT to_date(edd_date, 'd MMM yyyy') AS edd_date, cast(edd_value AS DOUBLE) AS edd_value,
          cast(edd_type AS INT) AS edd_type, to_timestamp(edd_update, concat('d MMM yyyy HH', chr(58), 'mm', chr(58), 'ss')) AS edd_update,
          to_timestamp(`current_date`, concat('d MMM yyyy HH', chr(58), 'mm', chr(58), 'ss')) AS report_ts, data_source,
          CASE data_source WHEN 'AEMO' THEN 2 ELSE 1 END AS source_priority, _source_file
FROM STREAM(${lochard.bronze}.brz_aemo_int091);

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_edd_daily
COMMENT 'Daily actual EDD – one row per gas day, AEMO preferred over synthetic';

CREATE FLOW edd_daily_cdc AS AUTO CDC INTO ${lochard.silver}.slv_edd_daily
FROM STREAM(${lochard.silver}.slv_edd_validated)
KEYS (edd_date)
SEQUENCE BY STRUCT(source_priority, report_ts)
COLUMNS * EXCEPT (_source_file)
STORED AS SCD TYPE 1;

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_vic_demand_validated (
  CONSTRAINT gas_date_parsed    EXPECT (gas_date IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT complete_gas_day   EXPECT (gas_date < to_date(report_ts)) ON VIOLATION DROP ROW,
  CONSTRAINT not_future         EXPECT (gas_date <= current_date()) ON VIOLATION FAIL UPDATE,
  CONSTRAINT demand_range_gj    EXPECT (total_gas_used BETWEEN 150000 AND 1600000)
)
COMMENT 'INT287 VIC total gas used (GJ/day) – typed; partial current gas day dropped'
AS SELECT to_date(gas_date, 'd MMM yyyy') AS gas_date, cast(total_gas_used AS BIGINT) AS total_gas_used,
          to_timestamp(`current_date`, concat('d MMM yyyy HH', chr(58), 'mm', chr(58), 'ss')) AS report_ts, data_source,
          CASE data_source WHEN 'AEMO' THEN 2 ELSE 1 END AS source_priority, _source_file
FROM STREAM(${lochard.bronze}.brz_aemo_int287);

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_vic_demand_daily
COMMENT 'Daily VIC gas demand – one row per gas day, AEMO preferred over synthetic';

CREATE FLOW vic_demand_daily_cdc AS AUTO CDC INTO ${lochard.silver}.slv_vic_demand_daily
FROM STREAM(${lochard.silver}.slv_vic_demand_validated)
KEYS (gas_date)
SEQUENCE BY STRUCT(source_priority, report_ts)
COLUMNS * EXCEPT (_source_file)
STORED AS SCD TYPE 1;

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_aemo_site_flows (
  CONSTRAINT gas_date_parsed EXPECT (gas_date IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT flow_non_negative EXPECT (energy_flow_gj >= 0) ON VIOLATION DROP ROW
)
COMMENT 'INT313 allocated injections / withdrawals by site and gas hour (real AEMO)'
AS SELECT to_date(gas_date, 'd MMM yyyy') AS gas_date, gas_hour, site_company, phy_mirn,
          CASE inject_withdraw WHEN 'I' THEN 'Injection' WHEN 'W' THEN 'Withdrawal' ELSE inject_withdraw END AS flow_direction,
          cast(energy_flow_gj AS DOUBLE) AS energy_flow_gj, site_company ILIKE '%iona%' AS is_iona, _source_file
FROM STREAM(${lochard.bronze}.brz_aemo_int313);

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.silver}.slv_market_price (
  CONSTRAINT price_range EXPECT (price_gst_ex BETWEEN -1 AND 1000)
)
COMMENT 'INT037b indicative market price by gas date and schedule type'
AS SELECT to_date(gas_date, 'd MMM yyyy') AS gas_date, demand_type_name, cast(price_value_gst_ex AS DOUBLE) AS price_gst_ex,
          schedule_type_id, to_timestamp(approval_datetime, concat('d MMM yyyy HH', chr(58), 'mm', chr(58), 'ss')) AS approval_ts
FROM ${lochard.bronze}.brz_aemo_int037b
QUALIFY row_number() OVER (PARTITION BY gas_date, demand_type_name ORDER BY approval_datetime DESC) = 1;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.silver}.slv_demand_forecast
COMMENT 'INT153 AEMO demand forecast – daily total of the latest version per forecast date'
AS WITH f AS (
  SELECT to_date(forecast_date, 'd MMM yyyy') AS forecast_date, cast(version_id AS BIGINT) AS version_id,
         cast(forecast_demand_gj AS DOUBLE) AS forecast_demand_gj
  FROM ${lochard.bronze}.brz_aemo_int153
)
SELECT forecast_date, max(version_id) AS version_id,
       sum(forecast_demand_gj) FILTER (WHERE version_id = latest) AS forecast_demand_gj
FROM (SELECT *, max(version_id) OVER (PARTITION BY forecast_date) AS latest FROM f)
GROUP BY forecast_date;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.silver}.slv_iona_ops_daily (
  CONSTRAINT inventory_within_capacity EXPECT (inventory_tj BETWEEN 0 AND 26500),
  CONSTRAINT withdrawal_within_rating  EXPECT (withdrawal_tj <= 615),
  CONSTRAINT availability_ratio        EXPECT (compressor_availability BETWEEN 0 AND 1)
)
COMMENT 'Iona daily operations (historian)'
AS SELECT cast(gas_date AS DATE) AS gas_date, cast(injection_tj AS DOUBLE) AS injection_tj,
          cast(withdrawal_tj AS DOUBLE) AS withdrawal_tj, cast(inventory_tj AS DOUBLE) AS inventory_tj,
          cast(compressor_availability AS DOUBLE) AS compressor_availability, updated_at
FROM ${lochard.bronze}.brz_iona_historian_daily
QUALIFY row_number() OVER (PARTITION BY gas_date ORDER BY updated_at DESC) = 1;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.silver}.slv_nominations (
  CONSTRAINT nomination_positive EXPECT (nominated_tj > 0) ON VIOLATION DROP ROW
)
COMMENT 'Customer nominations vs delivered'
AS SELECT to_date(gas_date) AS gas_date, customer, cast(nominated_tj AS DOUBLE) AS nominated_tj,
          cast(delivered_tj AS DOUBLE) AS delivered_tj, lower(refund_payable) = 'true' AS refund_payable
FROM ${lochard.bronze}.brz_nominations;
