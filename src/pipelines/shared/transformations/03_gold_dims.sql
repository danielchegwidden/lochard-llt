-- =====================================================================================================
-- Shared master data – GOLD conformed dimensions (used by every domain star schema, Genie and dashboards)
-- =====================================================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.dim_date
COMMENT 'Calendar with Australian financial year (1 Jul – 30 Jun), schedule weeks (Mon) and VIC gas day. 19000101 = unscheduled.'
AS WITH d AS (
  SELECT explode(sequence(DATE'2014-01-01', DATE'2031-12-31', INTERVAL 1 DAY)) AS date
)
SELECT
  cast(date_format(date, 'yyyyMMdd') AS INT)                         AS date_key,
  date,
  year(date)                                                          AS calendar_year,
  month(date)                                                         AS calendar_month,
  date_format(date, 'MMMM')                                           AS month_name,
  date_format(date, 'MMM-yy')                                         AS month_label,
  CASE WHEN month(date) >= 7 THEN year(date) + 1 ELSE year(date) END  AS fy_num,
  concat('FY', CASE WHEN month(date) >= 7 THEN year(date) + 1 ELSE year(date) END) AS financial_year,
  concat('Q', CAST(floor(((month(date) + 5) % 12) / 3) + 1 AS INT))   AS financial_quarter,
  ((month(date) + 5) % 12) + 1                                        AS fy_month_num,
  CAST(date_trunc('MONTH', date) AS DATE)                              AS month_start,
  date_sub(date, (dayofweek(date) + 5) % 7)                           AS schedule_week_start,
  dayofweek(date) IN (1, 7)                                           AS is_weekend,
  date_format(date, 'EEEE')                                           AS day_name,
  dayofweek(date)                                                     AS weekday_num,
  make_date(year(current_date()), month(date), CASE WHEN month(date) = 2 AND day(date) = 29 THEN 28 ELSE day(date) END) AS date_without_year
FROM d
UNION ALL
SELECT 19000101, DATE'1900-01-01', 1900, 1, 'Unscheduled', 'Unscheduled', NULL, 'Unscheduled', NULL, NULL,
       DATE'1900-01-01', DATE'1900-01-01', false, NULL, NULL, NULL;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.dim_cost_centre
COMMENT 'Cost centre (current version) – Function > Team > CC Short Name > Cost Centre; cost type Opex/Capex/SIB'
AS SELECT cost_centre_key, cost_centre_name, cc_short_name, team, function, cost_type, plant_area, company_name, is_active,
          `__START_AT` AS valid_from
FROM ${lochard.silver}.slv_dim_cost_centre
WHERE `__END_AT` IS NULL;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.dim_cost_centre_history
COMMENT 'Cost centre SCD2 history (e.g. FY26 re-org – ZFR-0002 IT -> Digital & Cyber)'
AS SELECT cost_centre_key, cost_centre_name, cc_short_name, team, function, cost_type, plant_area,
          `__START_AT` AS valid_from, `__END_AT` AS valid_to, `__END_AT` IS NULL AS is_current
FROM ${lochard.silver}.slv_dim_cost_centre;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.dim_account
COMMENT 'GL account (Business Central chart of accounts)'
AS SELECT account_key, account_name, account_group, capex_flag, pl_bs FROM ${lochard.silver}.slv_dim_account;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.dim_project
COMMENT 'Projects (HUGS Execute/Concept, Project Aegis, Queen FEL2, Data Utilisation, Flowbridge ...)'
AS SELECT project_key, project_name, cc_short_name, phase, p50_budget, rfsu_target FROM ${lochard.silver}.slv_dim_project;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.dim_vendor
COMMENT 'Vendors. abn / bank_* are PII (lochard_pii) – masked by ABAC outside Finance'
AS SELECT source_key, vendor_name, vendor_category, abn, bank_bsb, bank_account, payment_terms_days,
          is_employee_reimbursement FROM ${lochard.silver}.slv_dim_vendor;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.dim_person
COMMENT 'People directory (fictitious). display_name / email are PII – masked outside HSE'
AS SELECT username, display_name, email, team, site, is_contractor FROM ${lochard.silver}.slv_dim_person;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.dim_asset
COMMENT 'Iona asset register (site S3620) – plant area, safety-critical flag, criticality'
AS SELECT asset_num, asset_description, site_id, plant_area, safety_critical, criticality FROM ${lochard.silver}.slv_dim_asset;
