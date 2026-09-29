-- Consumer views over gold. Dashboards, Genie Agents and the app read ONLY lochard_semantic.
-- ABAC row filters / masks on the gold tables still apply – they are evaluated for the querying user.

CREATE OR REPLACE VIEW {semantic}.v_finance_monthly
COMMENT 'Budget / Actuals / YEO / Committed by FY month, Function > Team > CC Short Name > Project > Account (AUD)'
AS SELECT * FROM {gold}.fact_finance_monthly;

CREATE OR REPLACE VIEW {semantic}.v_gl_transaction_detail
COMMENT 'Actuals – Transaction Details: GL entries with cost centre, WO, PO, account, posting date, description, amount'
AS SELECT entry_no, posting_date, financial_year, financial_quarter, month_start, month_label, function, team, cc_short_name,
          cost_centre_key, cost_type, project_name, account_key, account_name, account_class, wo_number, po_number,
          document_no, document_type, external_document_no, vendor_name, description, amount, gst_amount, reversed,
          spend_classification
FROM {gold}.fact_gl_transaction;

CREATE OR REPLACE VIEW {semantic}.v_po_transaction_detail
COMMENT 'PO Transaction Details: Maximo PO lines with invoiced and committed (open) value'
AS SELECT po_number, po_line, vendor_name, function, team, cc_short_name, cost_centre_key, cost_type, account_name, account_class,
          wo_number, description, line_cost, received_amount, invoiced_amount, committed_amount, order_date, need_by_date,
          need_by_financial_year, need_by_month, po_status, spend_classification
FROM {gold}.fact_po_line;

CREATE OR REPLACE VIEW {semantic}.v_observation_detail
COMMENT 'HSE observations and investigations (one row each); actionee masked outside HSE'
AS SELECT observation_id, classification, observation_type, incident_category, status, is_open, potential_risk_rank,
          actual_risk_rank, reported_date, financial_year, financial_quarter, month_start, month_label, due_date, closed_date,
          days_open, plant_area, description, actionee, actionee_team, is_high_potential_event, investigation_id, is_privileged
FROM {gold}.fact_observation;

CREATE OR REPLACE VIEW {semantic}.v_hse_monthly
COMMENT 'Monthly exposure hours, recordable injuries, TRIFR / LTIFR (rolling 12m) and High Potential Events'
AS SELECT * FROM {gold}.fact_hse_monthly;

CREATE OR REPLACE VIEW {semantic}.v_investigation_counts
COMMENT 'Investigation counts by FY (aggregate only – visible to the Board)'
AS SELECT * FROM {gold}.agg_hse_investigation_counts;

CREATE OR REPLACE VIEW {semantic}.v_workorder_schedule_weekly
COMMENT 'Maximo weekly schedule snapshot (PBI Maintenance grain)'
AS SELECT * FROM {gold}.fact_workorder_schedule_weekly;

CREATE OR REPLACE VIEW {semantic}.v_workorder_detail
COMMENT 'Maximo work orders (current state) with asset and overdue flags'
AS SELECT * FROM {gold}.fact_workorder;

CREATE OR REPLACE VIEW {semantic}.v_vic_gas_demand_daily
COMMENT 'Daily VIC gas demand (GJ/TJ/PJ) with actual EDD; demand_source AEMO (real nemweb) or SYNTHETIC (history)'
AS SELECT * FROM {gold}.fact_vic_gas_demand_daily;

CREATE OR REPLACE VIEW {semantic}.v_cumulative_vic_demand
COMMENT 'Cumulative VIC demand and EDD by day of year per year (Tableau Cumulative VIC demand)'
AS SELECT * FROM {gold}.mv_cumulative_vic_demand;

CREATE OR REPLACE VIEW {semantic}.v_iona_operations_daily
COMMENT 'Iona daily injection / withdrawal / inventory / compressor availability / price'
AS SELECT * FROM {gold}.fact_iona_operations_daily;

CREATE OR REPLACE VIEW {semantic}.v_nominations
COMMENT 'Customer nominations vs delivered and ±4% tolerance compliance'
AS SELECT * FROM {gold}.fact_nomination;
