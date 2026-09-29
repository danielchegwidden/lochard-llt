-- =====================================================================================================
-- Shared master data – SILVER. Typed + validated, then AUTO CDC into SCD2 (cost centres) / SCD1 (the rest).
-- =====================================================================================================

-- Cost centres - validated change feed -> SCD Type 2 history (FY26 re-org keeps prior short names)
CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_cost_centre_changes (
  CONSTRAINT key_present      EXPECT (cost_centre_key IS NOT NULL)            ON VIOLATION DROP ROW,
  CONSTRAINT team_present     EXPECT (team IS NOT NULL)                       ON VIOLATION DROP ROW,
  CONSTRAINT valid_cost_type  EXPECT (cost_type IN ('Opex', 'Capex', 'SIB')),
  CONSTRAINT no_rescued_data  EXPECT (_rescued_data IS NULL)
)
COMMENT 'Validated cost-centre change records (feeds SCD2)'
AS SELECT
  trim(cost_centre_key) AS cost_centre_key, cost_centre_name, cc_short_name, team, function, cost_type,
  plant_area, company_name, cc_manager_email, cast(is_active AS BOOLEAN) AS is_active,
  cast(`_seq` AS INT) AS change_seq, to_timestamp(updated_at) AS updated_at, _rescued_data, _source_file
FROM STREAM(${lochard.bronze}.brz_cost_centres);

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_dim_cost_centre
COMMENT 'Cost-centre dimension, SCD Type 2 (__START_AT/__END_AT)';

CREATE FLOW cost_centre_scd2 AS AUTO CDC INTO ${lochard.silver}.slv_dim_cost_centre
FROM STREAM(${lochard.silver}.slv_cost_centre_changes)
KEYS (cost_centre_key)
SEQUENCE BY STRUCT(updated_at, change_seq)
COLUMNS * EXCEPT (_rescued_data, _source_file)
STORED AS SCD TYPE 2;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.silver}.slv_dim_account (
  CONSTRAINT key_numeric EXPECT (account_key IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT 'GL account dimension (typed)'
AS SELECT cast(account_key AS INT) AS account_key, account_name, account_group, cast(capex_flag AS BOOLEAN) AS capex_flag,
          pl_bs, to_timestamp(updated_at) AS updated_at
FROM ${lochard.bronze}.brz_accounts
QUALIFY row_number() OVER (PARTITION BY account_key ORDER BY updated_at DESC) = 1;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.silver}.slv_dim_project
COMMENT 'Project dimension (typed)'
AS SELECT project_key, project_name, cc_short_name, phase, cast(p50_budget AS DECIMAL(18,2)) AS p50_budget,
          to_date(rfsu_target) AS rfsu_target, to_timestamp(updated_at) AS updated_at
FROM ${lochard.bronze}.brz_projects
QUALIFY row_number() OVER (PARTITION BY project_key ORDER BY updated_at DESC) = 1;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.silver}.slv_dim_vendor (
  CONSTRAINT key_format EXPECT (source_key RLIKE '^V_[0-9]+$') ON VIOLATION DROP ROW
)
COMMENT 'Vendor dimension incl. ABN / bank details (PII – masked by ABAC in gold)'
AS SELECT source_key, vendor_name, vendor_category, abn, bank_bsb, bank_account,
          cast(payment_terms_days AS INT) AS payment_terms_days, cast(is_active AS BOOLEAN) AS is_active,
          vendor_category = 'Employee' AS is_employee_reimbursement, to_timestamp(updated_at) AS updated_at
FROM ${lochard.bronze}.brz_vendors
QUALIFY row_number() OVER (PARTITION BY source_key ORDER BY updated_at DESC) = 1;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.silver}.slv_dim_person (
  CONSTRAINT username_format EXPECT (username RLIKE '^[A-Z]+\\.[A-Z]+_LOC$')
)
COMMENT 'People directory (PII)'
AS SELECT username, display_name, email, team, site, cast(is_contractor AS BOOLEAN) AS is_contractor,
          to_timestamp(updated_at) AS updated_at
FROM ${lochard.bronze}.brz_people
QUALIFY row_number() OVER (PARTITION BY username ORDER BY updated_at DESC) = 1;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.silver}.slv_dim_asset
COMMENT 'Maximo asset register (typed)'
AS SELECT asset_num, asset_description, site_id, plant_area, cast(safety_critical AS BOOLEAN) AS safety_critical,
          cast(criticality AS INT) AS criticality, to_timestamp(updated_at) AS updated_at
FROM ${lochard.bronze}.brz_assets
QUALIFY row_number() OVER (PARTITION BY asset_num ORDER BY updated_at DESC) = 1;
