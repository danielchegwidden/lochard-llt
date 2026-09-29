-- Governed KPI definitions (UC metric views, YAML v1.1) – one definition for dashboards, Genie, the app and agents.

CREATE OR REPLACE VIEW {semantic}.mv_finance
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
comment: "Lochard finance KPIs. Budget & YEO are full-year; actuals & committed are YTD. Variance = Actual - Budget (negative = under-spend)."
source: {gold}.fact_finance_monthly
fields:
  - {name: financial_year, expr: source.financial_year, comment: "FY runs 1 Jul - 30 Jun (FY2027 = Jul-26..Jun-27)"}
  - {name: financial_quarter, expr: source.financial_quarter}
  - {name: month_start, expr: source.month_start}
  - {name: month_label, expr: source.month_label}
  - {name: function, expr: source.function}
  - {name: team, expr: source.team}
  - {name: cc_short_name, expr: source.cc_short_name}
  - {name: cost_centre_key, expr: source.cost_centre_key}
  - {name: cost_type, expr: source.cost_type}
  - {name: project_name, expr: source.project_name}
  - {name: account_name, expr: source.account_name}
measures:
  - {name: budget, expr: SUM(source.budget_amount), comment: "Board-endorsed budget (SITEBUD)"}
  - {name: actuals, expr: SUM(source.actual_amount), comment: "Posted GL actuals excl. GST"}
  - {name: yeo, expr: SUM(source.yeo_amount), comment: "Year End Outlook - latest reforecast version"}
  - {name: committed_cost, expr: SUM(source.committed_amount), comment: "Open PO value not yet invoiced"}
  - {name: variance_act_vs_bud, expr: SUM(source.actual_amount) - SUM(source.budget_amount)}
  - {name: variance_yeo_vs_bud, expr: SUM(source.yeo_amount) - SUM(source.budget_amount)}
  - {name: actuals_plus_committed, expr: SUM(source.actual_amount) + SUM(source.committed_amount)}
  - {name: variance_act_incl_committed_vs_bud, expr: SUM(source.actual_amount) + SUM(source.committed_amount) - SUM(source.budget_amount)}
  - {name: variance_act_incl_committed_vs_yeo, expr: SUM(source.actual_amount) + SUM(source.committed_amount) - SUM(source.yeo_amount)}
$$;

CREATE OR REPLACE VIEW {semantic}.mv_hse
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
comment: "HSE observation KPIs. Open = status NEW or INPROG. Investigations = classification INVESTIGATION."
source: {gold}.fact_observation
fields:
  - {name: financial_year, expr: source.financial_year}
  - {name: month_start, expr: source.month_start}
  - {name: reported_date, expr: source.reported_date}
  - {name: classification, expr: source.classification}
  - {name: observation_type, expr: source.observation_type}
  - {name: incident_category, expr: source.incident_category}
  - {name: potential_risk_rank, expr: source.potential_risk_rank}
  - {name: actual_risk_rank, expr: source.actual_risk_rank}
  - {name: status, expr: source.status}
  - {name: plant_area, expr: source.plant_area}
measures:
  - {name: total_observations, expr: COUNT(1) FILTER (WHERE source.classification = 'INCIDENT')}
  - {name: open_observations, expr: COUNT(1) FILTER (WHERE source.classification = 'INCIDENT' AND source.is_open)}
  - {name: closed_observations, expr: COUNT(1) FILTER (WHERE source.classification = 'INCIDENT' AND NOT source.is_open)}
  - {name: high_potential_events, expr: COUNT(1) FILTER (WHERE source.is_high_potential_event)}
  - {name: avg_days_to_close, expr: AVG(source.days_open) FILTER (WHERE NOT source.is_open)}
$$;

CREATE OR REPLACE VIEW {semantic}.mv_maintenance
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
comment: "Maximo weekly schedule KPIs. Filter snapshot_date to the latest snapshot for current values."
source: {gold}.fact_workorder_schedule_weekly
fields:
  - {name: snapshot_date, expr: source.snapshot_date}
  - {name: is_latest_snapshot, expr: source.is_latest_snapshot}
  - {name: schedule_week, expr: source.schedule_week_start, comment: "Monday of the schedule week (NULL = unscheduled)"}
  - {name: priority, expr: source.priority_bucket}
  - {name: work_type, expr: source.work_type}
  - {name: status, expr: source.status}
  - {name: lead_craft, expr: source.lead_craft}
measures:
  - {name: scheduled_wo_count, expr: SUM(source.scheduled_count)}
  - {name: scheduled_completed_wo_count, expr: SUM(source.schedule_compliant_count)}
  - {name: scheduled_compliance_pct, expr: "SUM(source.schedule_compliant_count) / NULLIF(SUM(source.scheduled_count), 0)", comment: "Current Scheduled Compliance % (latest schedule week)"}
  - {name: overdue_safety_critical, expr: SUM(source.overdue_safety_critical_count)}
  - {name: open_p1, expr: SUM(source.workorder_count) FILTER (WHERE source.priority_bucket = 'P1' AND source.is_open)}
  - {name: open_p2_excl_pm, expr: SUM(source.workorder_count) FILTER (WHERE source.priority_bucket = 'P2' AND source.work_type <> 'PM' AND source.is_open)}
  - {name: backlog_excl_pm, expr: SUM(source.backlog_count) FILTER (WHERE source.work_type <> 'PM')}
  - {name: total_scheduled_hours, expr: SUM(source.est_dur_scheduled)}
  - {name: total_completed_hours, expr: SUM(source.est_dur_compliant)}
$$;

CREATE OR REPLACE VIEW {semantic}.mv_market
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
comment: "VIC gas demand (AEMO INT287, GJ/day) and effective degree days (INT091). 1 PJ = 1,000 TJ = 1,000,000 GJ."
source: {gold}.fact_vic_gas_demand_daily
fields:
  - {name: gas_date, expr: source.gas_date}
  - {name: gas_year, expr: source.gas_year}
  - {name: gas_month, expr: source.gas_month}
  - {name: gas_month_name, expr: source.gas_month_name}
  - {name: is_weekend, expr: source.is_weekend}
  - {name: day_name, expr: source.day_name}
  - {name: demand_source, expr: source.demand_source}
measures:
  - {name: demand_pj, expr: SUM(source.total_gas_used_pj)}
  - {name: demand_tj, expr: SUM(source.total_gas_used_tj)}
  - {name: avg_daily_demand_tj, expr: AVG(source.total_gas_used_tj)}
  - {name: total_edd, expr: SUM(source.edd_value)}
  - {name: avg_edd, expr: AVG(source.edd_value)}
  - {name: edd_demand_r2, expr: "POWER(CORR(source.edd_value, source.total_gas_used_tj), 2)", comment: "R-squared of daily demand vs EDD"}
$$;

CREATE OR REPLACE VIEW {semantic}.mv_iona_ops
WITH METRICS LANGUAGE YAML AS $$
version: 1.1
comment: "Iona Gas Storage Facility operations: injection / withdrawal (TJ), inventory (PJ), availability"
source: {gold}.fact_iona_operations_daily
fields:
  - {name: gas_date, expr: source.gas_date}
  - {name: gas_month, expr: "DATE_TRUNC('MONTH', source.gas_date)"}
  - {name: gas_year, expr: YEAR(source.gas_date)}
measures:
  - {name: total_injection_tj, expr: SUM(source.injection_tj)}
  - {name: total_withdrawal_tj, expr: SUM(source.withdrawal_tj)}
  - {name: peak_withdrawal_tj, expr: MAX(source.withdrawal_tj)}
  - {name: avg_inventory_pj, expr: AVG(source.inventory_pj)}
  - {name: avg_compressor_availability, expr: AVG(source.compressor_availability)}
$$;
