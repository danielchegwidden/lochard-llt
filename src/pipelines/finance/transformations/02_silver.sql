-- =====================================================================================================
-- Finance – SILVER - type, clean ('null' literals, 0 = no reversal), validate with expectations, quarantine the
-- rows we drop, then AUTO CDC (SCD1) so restated / re-sent lines collapse to the latest version.
-- =====================================================================================================

CREATE TEMPORARY VIEW gl_typed AS
SELECT
  cast(entry_no AS BIGINT)                                                    AS entry_no,
  nullif(trim(company_name), '')                                              AS company_name,
  gl_entry_key,
  to_date(date_key, 'yyyyMMdd')                                               AS posting_date,
  cast(date_key AS INT)                                                       AS date_key,
  trim(cost_centre_key)                                                       AS cost_centre_key,
  cast(account_key AS INT)                                                    AS account_key,
  nullif(nullif(trim(source_key), ''), 'null')                                AS source_key,
  nullif(nullif(trim(purchase_order_key), ''), 'null')                        AS purchase_order_key,
  nullif(nullif(trim(work_order_key), ''), 'null')                            AS work_order_key,
  split_part(nullif(nullif(trim(purchase_order_key), ''), 'null'), '|', 1)    AS po_number,
  split_part(nullif(nullif(trim(work_order_key), ''), 'null'), '|', 1)        AS wo_number,
  document_no,
  left(document_no, 3)                                                        AS document_type,
  external_document_no,
  description,
  cast(nullif(nullif(po_line_cost, ''), 'null') AS DECIMAL(18,2))             AS po_line_cost,
  cast(amount AS DECIMAL(18,2))                                               AS amount,
  cast(nullif(gst_amount, '') AS DECIMAL(18,2))                               AS gst_amount,
  lower(reversed) = 'true'                                                    AS reversed,
  nullif(cast(reversed_by_entry_no AS BIGINT), 0)                             AS reversed_by_entry_no,
  to_timestamp(updated_at)                                                    AS updated_at,
  _rescued_data, _source_file, _ingested_at
FROM STREAM(${lochard.bronze}.brz_gl_entries);

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_gl_entries_validated (
  CONSTRAINT entry_key_present   EXPECT (entry_no IS NOT NULL AND company_name IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_posting_date  EXPECT (posting_date BETWEEN DATE'2014-07-01' AND date_add(current_date(), 31)) ON VIOLATION DROP ROW,
  CONSTRAINT amount_present      EXPECT (amount IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT known_company       EXPECT (company_name = 'Iona Ops Trust'),
  CONSTRAINT gst_ratio_10pct     EXPECT (coalesce(gst_amount, 0) = 0 OR abs(gst_amount / nullif(amount, 0) - 0.1) < 0.005),
  CONSTRAINT reversal_consistent EXPECT (NOT reversed OR reversed_by_entry_no IS NOT NULL),
  CONSTRAINT po_key_format       EXPECT (po_number IS NULL OR po_number RLIKE '^[0-9]{9}$'),
  CONSTRAINT wo_key_format       EXPECT (wo_number IS NULL OR wo_number RLIKE '^36[0-9]{8}$'),
  CONSTRAINT no_rescued_data     EXPECT (_rescued_data IS NULL)
)
COMMENT 'GL entries – typed and validated (append-only change feed)'
TBLPROPERTIES ('lochard.layer' = 'silver')
AS SELECT * FROM STREAM(gl_typed);

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_gl_entries_quarantine
COMMENT 'GL rows rejected by DROP expectations (null keys, bad dates, missing amounts) for data-steward review'
TBLPROPERTIES ('lochard.layer' = 'silver', 'lochard.quarantine' = 'true')
AS SELECT *, concat_ws(', ',
            CASE WHEN entry_no IS NULL OR company_name IS NULL THEN 'entry_key_present' END,
            CASE WHEN NOT coalesce(posting_date BETWEEN DATE'2014-07-01' AND date_add(current_date(), 31), false) THEN 'valid_posting_date' END,
            CASE WHEN amount IS NULL THEN 'amount_present' END) AS failed_rules
FROM STREAM(gl_typed)
WHERE entry_no IS NULL OR company_name IS NULL OR amount IS NULL
   OR NOT coalesce(posting_date BETWEEN DATE'2014-07-01' AND date_add(current_date(), 31), false);

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_gl_entries
COMMENT 'GL entries – current version per (company, entry_no) via AUTO CDC SCD1'
TBLPROPERTIES ('lochard.layer' = 'silver');

CREATE FLOW gl_entries_scd1 AS AUTO CDC INTO ${lochard.silver}.slv_gl_entries
FROM STREAM(${lochard.silver}.slv_gl_entries_validated)
KEYS (company_name, entry_no)
SEQUENCE BY updated_at
COLUMNS * EXCEPT (_rescued_data)
STORED AS SCD TYPE 1;

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_budget_entries (
  CONSTRAINT key_present       EXPECT (budget_entry_key IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT month_start       EXPECT (day(month_start) = 1) ON VIOLATION DROP ROW,
  CONSTRAINT amount_present    EXPECT (amount IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT version_pattern   EXPECT (budget_name RLIKE '^SITEBUD[0-9]{2}$'),
  CONSTRAINT known_type        EXPECT (budget_type = 'Budget')
)
COMMENT 'Budget entries (SITEBUD17 sample + SITEBUD22..27), typed and validated'
TBLPROPERTIES ('lochard.layer' = 'silver')
AS SELECT cast(budget_entry_key AS BIGINT) AS budget_entry_key, to_date(date_key, 'yyyyMMdd') AS month_start,
          cast(date_key AS INT) AS date_key, trim(cost_centre_key) AS cost_centre_key, cast(account_key AS INT) AS account_key,
          cast(entry_no AS BIGINT) AS entry_no, budget_name, budget_type, cast(amount AS DECIMAL(18,2)) AS amount,
          concat('FY20', substr(budget_name, 8, 2)) AS financial_year, to_timestamp(updated_at) AS updated_at, _source_file
FROM STREAM(${lochard.bronze}.brz_budget_entries);

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_yeo_entries (
  CONSTRAINT key_present     EXPECT (yeo_entry_key IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT month_start     EXPECT (day(month_start) = 1) ON VIOLATION DROP ROW,
  CONSTRAINT version_pattern EXPECT (yeo_version RLIKE '^FY[0-9]{2}_YEO_M[0-9]{2}$')
)
COMMENT 'Year End Outlook reforecast entries by version (FYyy_YEO_Mnn = forecast after month nn close)'
TBLPROPERTIES ('lochard.layer' = 'silver')
AS SELECT cast(yeo_entry_key AS BIGINT) AS yeo_entry_key, yeo_version, cast(fy AS INT) AS fy_num,
          concat('FY', fy) AS financial_year, cast(substr(yeo_version, -2) AS INT) AS version_month,
          to_date(date_key, 'yyyyMMdd') AS month_start, cast(date_key AS INT) AS date_key,
          trim(cost_centre_key) AS cost_centre_key, cast(account_key AS INT) AS account_key,
          cast(amount AS DECIMAL(18,2)) AS amount, to_timestamp(updated_at) AS updated_at, _source_file
FROM STREAM(${lochard.bronze}.brz_yeo_entries);

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_po_lines_validated (
  CONSTRAINT po_present         EXPECT (po_number IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT line_cost_positive EXPECT (line_cost >= 0),
  CONSTRAINT not_over_invoiced  EXPECT (invoiced_amount <= line_cost * 1.05 OR line_cost <= 0),
  CONSTRAINT valid_status       EXPECT (po_status IN ('APPR', 'CLOSE', 'COMP', 'CAN', 'WAPPR'))
)
COMMENT 'Maximo PO lines – typed and validated'
AS SELECT purchase_order_key, po_number, cast(po_line AS INT) AS po_line, site_id, nullif(source_key, '') AS source_key,
          cost_centre_key, cast(account_key AS INT) AS account_key,
          nullif(nullif(work_order_key, ''), 'null') AS work_order_key, description,
          cast(line_cost AS DECIMAL(18,2)) AS line_cost, cast(received_amount AS DECIMAL(18,2)) AS received_amount,
          cast(invoiced_amount AS DECIMAL(18,2)) AS invoiced_amount, to_date(order_date) AS order_date,
          to_date(need_by_date) AS need_by_date, po_status, nullif(spend_classification, '') AS spend_classification,
          to_timestamp(updated_at) AS updated_at
FROM STREAM(${lochard.bronze}.brz_po_lines);

CREATE OR REFRESH STREAMING TABLE ${lochard.silver}.slv_po_lines
COMMENT 'Maximo PO lines – current state per PO line (AUTO CDC SCD1)';

CREATE FLOW po_lines_scd1 AS AUTO CDC INTO ${lochard.silver}.slv_po_lines
FROM STREAM(${lochard.silver}.slv_po_lines_validated)
KEYS (po_number, po_line)
SEQUENCE BY updated_at
STORED AS SCD TYPE 1;
