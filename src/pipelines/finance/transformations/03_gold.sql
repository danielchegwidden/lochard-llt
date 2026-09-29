-- =====================================================================================================
-- Finance – GOLD star schema. Governed attributes (team, function, account_class) are denormalised onto every
-- fact so ABAC row filters / masks can match on tagged columns.
-- =====================================================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.bridge_cost_centre_project
COMMENT 'Cost centre -> project (HUGS – PRM-0021C = Concept Phase, other HUGS CCs = Execute Phase)'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'finance')
AS WITH proj AS (
  SELECT cc_short_name, min(project_name) AS project_name FROM ${lochard.gold}.dim_project GROUP BY cc_short_name
)
SELECT cc.cost_centre_key,
       CASE WHEN cc.cost_centre_key = 'PRM-0021C' THEN 'Heytesbury Underground Gas Storage (Concept Phase)'
            WHEN cc.cc_short_name = 'HUGS' THEN 'Heytesbury Underground Gas Storage (Execute Phase)'
            ELSE proj.project_name END AS project_name
FROM ${lochard.gold}.dim_cost_centre cc LEFT JOIN proj ON cc.cc_short_name = proj.cc_short_name;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_gl_transaction
COMMENT 'GL transaction detail (Actuals – Transaction Details drill-through). amount excl. GST, AUD.'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'finance')
AS WITH po AS (
  SELECT po_number, max(spend_classification) AS spend_classification FROM ${lochard.silver}.slv_po_lines GROUP BY po_number
)
SELECT
  g.entry_no, g.gl_entry_key, g.company_name, g.posting_date, g.date_key, d.financial_year, d.financial_quarter,
  d.fy_month_num, d.month_start, d.month_label,
  g.cost_centre_key, cc.cc_short_name, cc.team, cc.function, cc.cost_type, cc.plant_area,
  bp.project_name,
  g.account_key, a.account_name, a.account_group, a.capex_flag,
  CASE WHEN cc.team = 'Legal' OR g.account_key = 636100 THEN 'Legal'
       WHEN cc.team = 'Employee Costs' OR a.account_group = 'Employee Costs' THEN 'Employee Costs'
       ELSE 'General' END                                                AS account_class,
  g.source_key, v.vendor_name, v.is_employee_reimbursement,
  g.po_number, g.wo_number, g.document_no, g.document_type, g.external_document_no, g.description,
  g.po_line_cost, g.amount, g.gst_amount, g.reversed, g.reversed_by_entry_no,
  coalesce(po.spend_classification, '(Blank)')                            AS spend_classification,
  g.updated_at, g._source_file
FROM ${lochard.silver}.slv_gl_entries g
LEFT JOIN ${lochard.gold}.dim_cost_centre cc ON g.cost_centre_key = cc.cost_centre_key
LEFT JOIN ${lochard.gold}.dim_account a      ON g.account_key = a.account_key
LEFT JOIN ${lochard.gold}.dim_vendor v       ON g.source_key = v.source_key
LEFT JOIN ${lochard.gold}.dim_date d         ON g.date_key = d.date_key
LEFT JOIN ${lochard.gold}.bridge_cost_centre_project bp ON g.cost_centre_key = bp.cost_centre_key
LEFT JOIN po                                 ON g.po_number = po.po_number;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_budget
COMMENT 'Board-endorsed budget (SITEBUDyy) by month, cost centre and account'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'finance')
AS SELECT b.budget_entry_key, b.budget_name, b.financial_year, b.month_start, b.date_key, d.financial_quarter, d.fy_month_num,
          d.month_label, b.cost_centre_key, cc.cc_short_name, cc.team, cc.function, cc.cost_type, b.account_key, a.account_name,
          bp.project_name,
          CASE WHEN cc.team = 'Legal' THEN 'Legal' WHEN cc.team = 'Employee Costs' THEN 'Employee Costs' ELSE 'General' END AS account_class,
          b.amount
FROM ${lochard.silver}.slv_budget_entries b
LEFT JOIN ${lochard.gold}.dim_cost_centre cc ON b.cost_centre_key = cc.cost_centre_key
LEFT JOIN ${lochard.gold}.dim_account a      ON b.account_key = a.account_key
LEFT JOIN ${lochard.gold}.dim_date d         ON b.date_key = d.date_key
LEFT JOIN ${lochard.gold}.bridge_cost_centre_project bp ON b.cost_centre_key = bp.cost_centre_key;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_yeo
COMMENT 'Year End Outlook reforecasts by version; is_latest = most recent version in each financial year'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'finance')
AS SELECT y.yeo_entry_key, y.yeo_version, y.version_month, y.financial_year, y.month_start, y.date_key, d.financial_quarter,
          d.fy_month_num, d.month_label, y.cost_centre_key, cc.cc_short_name, cc.team, cc.function, cc.cost_type,
          y.account_key, a.account_name,
          bp.project_name,
          CASE WHEN cc.team = 'Legal' THEN 'Legal' WHEN cc.team = 'Employee Costs' THEN 'Employee Costs' ELSE 'General' END AS account_class,
          y.amount,
          y.version_month = max(y.version_month) OVER (PARTITION BY y.financial_year) AS is_latest
FROM ${lochard.silver}.slv_yeo_entries y
LEFT JOIN ${lochard.gold}.dim_cost_centre cc ON y.cost_centre_key = cc.cost_centre_key
LEFT JOIN ${lochard.gold}.dim_account a      ON y.account_key = a.account_key
LEFT JOIN ${lochard.gold}.dim_date d         ON y.date_key = d.date_key
LEFT JOIN ${lochard.gold}.bridge_cost_centre_project bp ON y.cost_centre_key = bp.cost_centre_key;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_po_line
COMMENT 'Maximo PO lines with committed (open) value = line_cost - invoiced (PO Transaction Details drill-through)'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'finance')
AS SELECT p.po_number, p.po_line, p.purchase_order_key, p.site_id, p.source_key, v.vendor_name, p.cost_centre_key,
          cc.cc_short_name, cc.team, cc.function, cc.cost_type, p.account_key, a.account_name,
          CASE WHEN cc.team = 'Legal' THEN 'Legal' WHEN cc.team = 'Employee Costs' THEN 'Employee Costs' ELSE 'General' END AS account_class,
          split_part(p.work_order_key, '|', 1) AS wo_number, p.description, p.line_cost, p.received_amount, p.invoiced_amount,
          CASE WHEN p.po_status IN ('APPR', 'WAPPR') THEN greatest(p.line_cost - p.invoiced_amount, 0) ELSE 0 END AS committed_amount,
          p.order_date, p.need_by_date, d.financial_year AS need_by_financial_year, d.month_start AS need_by_month,
          p.po_status, coalesce(p.spend_classification, '(Blank)') AS spend_classification, p.updated_at
FROM ${lochard.silver}.slv_po_lines p
LEFT JOIN ${lochard.gold}.dim_cost_centre cc ON p.cost_centre_key = cc.cost_centre_key
LEFT JOIN ${lochard.gold}.dim_account a      ON p.account_key = a.account_key
LEFT JOIN ${lochard.gold}.dim_vendor v       ON p.source_key = v.source_key
LEFT JOIN ${lochard.gold}.dim_date d         ON cast(date_format(p.need_by_date, 'yyyyMMdd') AS INT) = d.date_key;

CREATE OR REFRESH MATERIALIZED VIEW ${lochard.gold}.fact_finance_monthly
COMMENT 'Finance cube – Budget / Actuals / YEO (latest) / Committed by FY month x cost centre x account x project – drives Function Details'
TBLPROPERTIES ('lochard.layer' = 'gold', 'lochard.domain' = 'finance')
AS WITH u AS (
  SELECT financial_year, month_start, cost_centre_key, account_key, project_name, amount AS budget_amount,
         0 AS actual_amount, 0 AS yeo_amount, 0 AS committed_amount FROM ${lochard.gold}.fact_budget
  UNION ALL
  SELECT financial_year, month_start, cost_centre_key, account_key, project_name, 0, amount, 0, 0
  FROM ${lochard.gold}.fact_gl_transaction
  UNION ALL
  SELECT financial_year, month_start, cost_centre_key, account_key, project_name, 0, 0, amount, 0
  FROM ${lochard.gold}.fact_yeo WHERE is_latest
  UNION ALL
  SELECT p.need_by_financial_year, p.need_by_month, p.cost_centre_key, p.account_key, bp.project_name, 0, 0, 0, p.committed_amount
  FROM ${lochard.gold}.fact_po_line p
  LEFT JOIN ${lochard.gold}.bridge_cost_centre_project bp ON p.cost_centre_key = bp.cost_centre_key
  WHERE p.committed_amount > 0
)
SELECT u.financial_year, u.month_start, d.month_label, d.financial_quarter, d.fy_month_num,
       u.cost_centre_key, cc.cc_short_name, cc.team, cc.function, cc.cost_type,
       u.account_key, a.account_name, u.project_name,
       CASE WHEN cc.team = 'Legal' THEN 'Legal' WHEN cc.team = 'Employee Costs' THEN 'Employee Costs' ELSE 'General' END AS account_class,
       sum(budget_amount) AS budget_amount, sum(actual_amount) AS actual_amount,
       sum(yeo_amount) AS yeo_amount, sum(committed_amount) AS committed_amount
FROM u
LEFT JOIN ${lochard.gold}.dim_cost_centre cc ON u.cost_centre_key = cc.cost_centre_key
LEFT JOIN ${lochard.gold}.dim_account a      ON u.account_key = a.account_key
LEFT JOIN ${lochard.gold}.dim_date d         ON cast(date_format(u.month_start, 'yyyyMMdd') AS INT) = d.date_key
GROUP BY ALL;
