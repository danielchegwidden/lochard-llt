"""Generate the Lochard AI/BI dashboards (replicas of the PBI Finance / HSE / Maintenance reports and the Tableau
INT091 workbook) as .lvdash.json files for the bundle.   Run:  python src/dashboards/build/build_dashboards.py"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lv import LOCHARD as K, Dashboard, agg, col, fmt_money, fmt_num, fmt_pct, s  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
M = fmt_money(1)          # $51.1M style
M0 = fmt_money(0)


# ============================================================================================ Finance
def finance() -> Dashboard:
    d = Dashboard("finance")
    fin = d.dataset("fin", "Finance cube", """
SELECT financial_year, financial_quarter, month_start, month_label, fy_month_num, function, team, cc_short_name,
       cost_centre_key, cost_type, coalesce(project_name, '(No project)') AS project_name, account_name,
       budget_amount, actual_amount, yeo_amount, committed_amount
FROM v_finance_monthly""")
    cum = d.dataset("fin_cum", "Finance cumulative (as-of month)", """
SELECT f.financial_year, f.financial_quarter, f.function, f.team, f.cc_short_name, f.cost_type, f.month_start,
       m.month_start AS as_of_month, f.budget_amount, f.yeo_amount
FROM v_finance_monthly f
JOIN (SELECT DISTINCT financial_year, month_start FROM v_finance_monthly) m
  ON f.financial_year = m.financial_year AND f.month_start <= m.month_start""")
    gl = d.dataset("gl", "GL transactions", """
SELECT financial_year, financial_quarter, month_start, month_label, function, team, cc_short_name, cost_centre_key,
       cost_type, coalesce(project_name, '(No project)') AS project_name, account_name, account_key, wo_number, po_number,
       document_no, posting_date, description, vendor_name, amount, spend_classification
FROM v_gl_transaction_detail""")
    po = d.dataset("po", "PO lines", """
SELECT po_number, po_line, vendor_name, function, team, cc_short_name, cost_centre_key, cost_type, account_name,
       wo_number, description, line_cost, invoiced_amount, committed_amount, order_date, need_by_date,
       need_by_financial_year AS financial_year, need_by_month, po_status, spend_classification
FROM v_po_transaction_detail""")

    p = d.page("function_details", "Function Details")
    p.header("Function Details", "Detailed financial breakdown by Team and Cost Centre. Drill into variances, committed "
             "costs and cumulative forecast by Function. *Right-click the table or a chart → Drill to transaction pages.*",
             right="**Iona Ops Trust**  \nAUD, excl. GST")
    all_ds = [fin, cum, gl]
    p.filter("multi", "function", "Function", all_ds)
    p.filter("multi", "team", "Team", all_ds)
    p.filter("multi", "cc_short_name", "CC Short Name", all_ds)
    p.filter("multi", "cost_type", "Cost Type", all_ds)
    p.filter("single", "financial_year", "Financial Year", all_ds, default=["FY2027"])
    p.filter("multi", "financial_quarter", "Financial Quarter", all_ds)
    p.filter("date", "month_start", "Date Range", [fin, gl], w=2, default=("2026-07-01", "2027-06-30"))
    p.counter(fin, s("budget_amount", "Budget", M), "Budget (FY)")
    p.counter(fin, s("actual_amount", "Actuals", M), "Actuals (YTD)")
    p.counter(fin, s("yeo_amount", "YEO", M), "YEO (latest)")
    p.counter(fin, s("committed_amount", "Committed", M), "Committed Cost")
    p.pie(gl, s("amount", "Actuals", M), col("spend_classification", "Spend type"), "Budgeted vs Emergent", w=2, h=6,
          color_map={"(Blank)": K["crimson"], "Budgeted": K["grey"], "Emergent": K["lgrey"]})
    p.combo(cum, agg("monthly(as_of_month)", 'DATE_TRUNC("MONTH", `as_of_month`)', "Month"),
            [s("yeo_amount", "Cumulative YEO", M)], [s("budget_amount", "Cumulative Budget", M)],
            "Cumulative YEO vs Cumulative Budget", w=2, h=6, x_type="temporal")
    p.combo(fin, agg("monthly(month_start)", 'DATE_TRUNC("MONTH", `month_start`)', "Month"),
            [s("actual_amount", "Actuals", M), s("committed_amount", "Committed Cost", M)],
            [s("yeo_amount", "YEO", M)], "YTD (ACT + Committed Costs) vs YEO", w=2, h=6, x_type="temporal")
    cells = [
        s("budget_amount", "Budget", M), s("actual_amount", "Actuals", M),
        agg("var_act_bud", "SUM(`actual_amount`) - SUM(`budget_amount`)", "Variance (ACT vs BUD)", M),
        s("yeo_amount", "YEO", M),
        agg("var_yeo_bud", "SUM(`yeo_amount`) - SUM(`budget_amount`)", "Variance (YEO vs BUD)", M),
        s("committed_amount", "Committed Cost", M),
        agg("act_plus_com", "SUM(`actual_amount`) + SUM(`committed_amount`)", "Actuals + Committed Costs", M),
        agg("var_actc_bud", "SUM(`actual_amount`) + SUM(`committed_amount`) - SUM(`budget_amount`)",
            "Variance (ACT incl committed vs BUD)", M),
        agg("var_actc_yeo", "SUM(`actual_amount`) + SUM(`committed_amount`) - SUM(`yeo_amount`)",
            "Variance (ACT incl committed cost vs YEO)", M),
    ]
    p.pivot(fin, [col("team", "Team"), col("cc_short_name", "CC Short Name"), col("project_name", "Project Name"),
                  col("account_name", "Account Name")], cells, "Budget, Actuals, YEO and Committed by Team", h=10)

    # ---- drill-through target: Actuals – Transaction Details
    t = d.page("actuals_transactions", "Actuals – Transaction Details")
    t.header("Actuals – Transaction Details", "Transaction-level GL entries for the selected cost centre or function. "
             "Verify individual entry numbers and amounts for audit and reconciliation purposes.")
    for f, title in [("team", "Team"), ("cc_short_name", "CC Short Name"), ("project_name", "Project Name"),
                     ("account_name", "Account Name"), ("financial_year", "Financial Year")]:
        t.filter("multi" if f != "financial_year" else "single", f, title, [fin, gl],
                 default=["FY2027"] if f == "financial_year" else None)
    t.filter("multi", "cost_centre_key", "Cost Centre Code", [fin, gl])
    t.chart("bar", gl, agg("monthly(month_start)", 'DATE_TRUNC("MONTH", `month_start`)', "Month"),
            [s("amount", "Actuals", M)], "YTD ACT by Month", w=6, h=5, x_type="temporal", colors=[K["grey"]], labels=True)
    t.table(gl, [("cost_centre_key", "Cost Centre Code"), ("wo_number", "WO num"), ("po_number", "PO num"),
                 ("account_name", "GL Account Name"), ("account_key", "GL Account No"), ("posting_date", "Posting Date"),
                 ("description", "Description"), ("vendor_name", "Vendor"), ("amount", "Amount")],
            "GL transactions", h=10)

    # ---- drill-through target: PO Transaction Details
    q = d.page("po_transactions", "PO Transaction Details")
    q.header("PO Transaction Details", "Maximo purchase-order lines linked to the spend: line cost, invoiced to date and "
             "open commitment by need-by month.")
    for f, title in [("team", "Team"), ("cc_short_name", "CC Short Name"), ("cost_centre_key", "Cost Centre Code"),
                     ("financial_year", "Financial Year")]:
        q.filter("multi" if f != "financial_year" else "single", f, title, [fin, po],
                 default=["FY2027"] if f == "financial_year" else None)
    q.filter("multi", "po_status", "PO Status", [po], w=2)
    q.chart("bar", po, agg("monthly(need_by_month)", 'DATE_TRUNC("MONTH", `need_by_month`)', "Need-by month"),
            [s("committed_amount", "Committed", M)], "Open commitments by need-by month", w=6, h=5, x_type="temporal",
            colors=[K["amber"]])
    q.table(po, [("po_number", "PO num"), ("po_line", "Line"), ("vendor_name", "Vendor"), ("cost_centre_key", "Cost Centre"),
                 ("wo_number", "WO num"), ("description", "Description"), ("line_cost", "Line cost"),
                 ("invoiced_amount", "Invoiced"), ("committed_amount", "Committed"), ("need_by_date", "Need by"),
                 ("po_status", "Status"), ("spend_classification", "Budgeted / Emergent")], "PO lines", h=10)
    return d


# ============================================================================================ HSE
def hse() -> Dashboard:
    d = Dashboard("hse")
    base_cols = """observation_id, classification, observation_type, incident_category, status, is_open,
       potential_risk_rank, actual_risk_rank, reported_date, financial_year, financial_quarter,
       date_format(reported_date, 'MMM') AS month, plant_area, actionee, description, days_open,
       -- severity order for charts (AI/BI sorts categories alphabetically; leading spaces sort first and render invisibly)
       CASE actual_risk_rank WHEN 'HIGH' THEN '   HIGH' WHEN 'MEDIUM' THEN '  MEDIUM' WHEN 'LOW' THEN ' LOW'
            ELSE actual_risk_rank END AS risk_rank_ordered"""
    obs = d.dataset("obs", "Observations", f"SELECT {base_cols} FROM v_observation_detail")
    inv = d.dataset("inv", "Investigations", """
SELECT observation_id, status, is_open, potential_risk_rank, actual_risk_rank, reported_date, financial_year,
       financial_quarter, date_format(reported_date, 'MMM') AS month
FROM v_observation_detail WHERE classification = 'INVESTIGATION'""")
    cum = d.dataset("obs_cum", "Observations cumulative by month", f"""
SELECT o.observation_type, o.classification, o.incident_category, o.potential_risk_rank, o.actual_risk_rank,
       o.financial_year, m.month_start AS as_of_month
FROM v_observation_detail o
JOIN (SELECT explode(sequence(DATE'2025-05-01', trunc(current_date(), 'MM'), INTERVAL 1 MONTH)) AS month_start) m
  ON o.reported_date < add_months(m.month_start, 1)""")
    p = d.page("hse_observations", "HSE Observations")
    p.header("HSE Observations", "Daily Report To drive timely close-out of hazards and incidents before they escalate")
    ds3 = [obs, cum]
    p.filter("multi", "potential_risk_rank", "Potential Risk Rank", ds3 + [inv])
    p.filter("multi", "actual_risk_rank", "Actual Risk Rank", ds3 + [inv])
    p.filter("single", "classification", "Class", ds3, default=["INCIDENT"])
    p.filter("multi", "observation_type", "Observation Type", ds3)
    p.filter("multi", "financial_year", "FY", ds3 + [inv])
    p.filter("multi", "financial_quarter", "Quarter", [obs, inv])
    p.filter("date", "reported_date", "Date Filter", [obs, inv], w=3)
    p.filter("multi", "month", "Month", [obs, inv], w=3)
    cnt = lambda n, e, t: agg(n, e, t, fmt_num(0))
    p.counter(inv, cnt("open_inv", "COUNT_IF(`is_open`)", "Open Investigations"), "Open Investigations")
    p.counter(inv, cnt("closed_inv", "COUNT_IF(NOT `is_open`)", "Closed Investigations"), "Closed Investigations")
    p.counter(inv, cnt("total_inv", "COUNT(`observation_id`)", "Total Investigations"), "Total Investigations")
    p.counter(obs, cnt("open_obs", "COUNT_IF(`is_open`)", "Open Observations"), "Open Observations")
    p.counter(obs, cnt("closed_obs", "COUNT_IF(NOT `is_open`)", "Closed Observations"), "Closed Observations")
    p.counter(obs, cnt("total_obs", "COUNT(`observation_id`)", "Total Observations"), "Total Observations")
    type_colors = {"HAZARD": "#6E6E6E", "HAZARD_REPORT": "#BDBDBD", "INCIDENT": "#E8175D", "NEARMISS": "#6A2C91",
                   "Other": K["dorange"], "SAFEACT": K["sky"]}
    p.chart("line", cum, agg("monthly(as_of_month)", 'DATE_TRUNC("MONTH", `as_of_month`)', "Month"),
            [agg("count(*)", "COUNT(`*`)", "Observations (cumulative)")], "Total Observations Monthly Trend", w=3, h=6,
            x_type="temporal", color=col("observation_type", "Observation type"), color_map=type_colors)
    p.pie(obs, agg("count(observation_id)", "COUNT(`observation_id`)", "Observations"),
          col("incident_category", "Incident Category"), "Total Observations by Incident Category", w=3, h=6,
          color_map={"GENERAL SAFETY": "#BDBDBD", "PROCESS SAFETY": "#E8175D", "PRODUCTION": "#6A2C91",
                     "ENVIRONMENTAL": "#00AEEF", "Other": K["dorange"]})
    p.pivot(obs, [col("risk_rank_ordered", "Risk Rank")], [agg("count(observation_id)", "COUNT(`observation_id`)", "Count")],
            "Observations By Risk Rank and Reported To", columns=[col("status", "Status")], w=3, h=6, heat=True)
    p.chart("bar", obs, col("risk_rank_ordered", "Actual risk rank"),
            [agg("open_obs2", "COUNT_IF(`is_open`)", "Open observations", fmt_num(0))], "Open Observations By Risk Rank",
            w=3, h=6, colors=[K["dorange"]], labels=True)
    p.table(obs, [("observation_id", "Observation"), ("reported_date", "Reported"), ("observation_type", "Type"),
                  ("incident_category", "Category"), ("status", "Status"), ("actual_risk_rank", "Risk rank"),
                  ("plant_area", "Area"), ("actionee", "Actionee"), ("days_open", "Days open"),
                  ("description", "Description")], "Observation register", h=8)
    return d


# ============================================================================================ Maintenance
def maintenance() -> Dashboard:
    d = Dashboard("maintenance")
    snap = d.dataset("snap", "Latest weekly snapshot", """
SELECT snapshot_date, schedule_week_start, priority_bucket, work_type, wo_class, status, is_open, lead_craft,
       workorder_count, scheduled_count, schedule_compliant_count, est_dur_scheduled, est_dur_compliant,
       overdue_safety_critical_count, backlog_count,
       CASE WHEN priority_bucket = 'P1' AND is_open THEN workorder_count ELSE 0 END AS open_p1_count,
       CASE WHEN priority_bucket = 'P2' AND work_type <> 'PM' AND is_open THEN workorder_count ELSE 0 END AS open_p2_ex_pm_count,
       CASE WHEN work_type <> 'PM' THEN backlog_count ELSE 0 END AS backlog_ex_pm_count
FROM v_workorder_schedule_weekly WHERE is_latest_snapshot""")
    sched = d.dataset("sched", "Scheduled work (13 weeks)", """
SELECT schedule_week_start, priority_bucket, work_type, status, lead_craft, scheduled_count, schedule_compliant_count,
       NULLIF(scheduled_count, 0) AS scheduled_count_nz,             -- ratio denominator: never divides by zero
       CAST(est_dur_scheduled AS DECIMAL(14, 2)) AS est_dur_scheduled,   -- exact sums (no float noise in labels)
       CAST(est_dur_compliant AS DECIMAL(14, 2)) AS est_dur_compliant
FROM v_workorder_schedule_weekly WHERE is_latest_snapshot AND schedule_week_start IS NOT NULL""")
    cur = d.dataset("snap_curweek", "Current schedule week", """
SELECT priority_bucket, work_type, status, schedule_week_start, scheduled_count, schedule_compliant_count,
       NULLIF(scheduled_count, 0) AS scheduled_count_nz
FROM v_workorder_schedule_weekly
WHERE is_latest_snapshot AND schedule_week_start = (SELECT max(schedule_week_start) FROM v_workorder_schedule_weekly
                                                    WHERE is_latest_snapshot)""")
    p = d.page("maintenance_dashboard", "Maintenance Dashboard")
    p.header("Maintenance Dashboard", "Weekly maintenance performance reporting. Maximo schedule snapshot and planner "
             "schedule-hours files.", right="**Site S3620** – Iona Gas Storage Facility")
    p.filter("multi", "priority_bucket", "Priority", [snap, cur, sched])
    p.filter("multi", "status", "Status", [snap, cur, sched])
    p.filter("multi", "work_type", "Work Order Type", [snap, cur, sched])
    p.filter("multi", "schedule_week_start", "Schedule Week", [snap, sched], w=2)
    p.filter("multi", "lead_craft", "Lead Craft", [snap, sched])
    p.counter(cur, agg("compliance", "SUM(`schedule_compliant_count`) / SUM(`scheduled_count_nz`)",
                       "Current Scheduled Compliance %", fmt_pct(0)), "Current Scheduled Compliance %", w=2)
    p.counter(snap, agg("overdue_sc", "SUM(`overdue_safety_critical_count`)", "Overdue Safety Critical WO's", fmt_num()),
              "Overdue Safety Critical WO's")
    p.counter(snap, s("open_p1_count", "Open P1 Workorders", fmt_num()), "Open P1 Workorders")
    p.counter(snap, s("open_p2_ex_pm_count", "Open P2 (excl. PMs)", fmt_num()), "Open P2 Workorders (excluding PMs)")
    p.counter(snap, s("backlog_ex_pm_count", "Backlog (excl. PMs)", fmt_num()), "Backlog Workorders (excluding PMs)")
    wk = agg("weekly(schedule_week_start)", 'DATE_TRUNC("WEEK", `schedule_week_start`)', "Schedule Week")
    p.combo(sched, wk, [s("scheduled_count", "Scheduled WO Count"), s("schedule_compliant_count", "Scheduled Completed WO Count")],
            [agg("sched_pct", "SUM(`schedule_compliant_count`) * 100 / SUM(`scheduled_count_nz`)",  # widget exprs: no ROUND/try_divide
                 "Scheduled Completion %", fmt_num(1))], "Schedule Compliance Trend", w=3, h=6, x_type="temporal", labels=True, dual=True, grouped=True)
    p.pie(sched, s("scheduled_count", "Scheduled WOs"), col("work_type", "Work type"), "Scheduled Workorders by type", w=3, h=6,
          color_map={"PM": K["dorange"], "GPC": "#F4A6A6", "DM": "#E8175D", "CBM": "#F7C59F", "MOD": K["amber"],
                     "ADMIN": K["sand"], "EM": K["sky"], "HSE": "#B7D9F4", "MAINT": "#1F77B4", "OPS": "#D9A6B9",
                     "TRA": "#2CB9A8", "Unknown": K["grey"]})
    p.pivot(sched, [col("lead_craft", "Lead Craft")],
            [s("scheduled_count", "Scheduled WOs", fmt_num()), s("est_dur_scheduled", "Total Scheduled Hours", fmt_num(1)),
             s("est_dur_compliant", "Total Completed Hours", fmt_num(1))], "Scheduled Workorder Hours by Lead Craft",
            w=3, h=6)
    p.chart("bar", sched, wk, [s("est_dur_scheduled", "Total Scheduled Hours", fmt_num(0)),
                              s("est_dur_compliant", "Total Completed Hours", fmt_num(0))],
            "Total Scheduled Hours and Total Completed Hours by Schedule Week", w=3, h=6, x_type="temporal",
            colors=[K["dorange"], K["sky"]], labels=True)
    return d


# ============================================================================================ Market Intelligence
def market_intelligence() -> Dashboard:
    d = Dashboard("market_intel")
    sig = {"Opportunity": K["green"], "Threat": K["red"], "Watch": K["amber"], "Neutral": K["lgrey"]}
    items = d.dataset("items", "Market intelligence items", """
SELECT item_id, week_start, published_date, title, source_name, source_type, entity_group, primary_entity, topic, signal,
       sentiment, importance, relevance, summary, why_it_matters, url
FROM v_market_intel_items""")
    ments = d.dataset("mentions", "Entity mentions", """
SELECT i.week_start, i.published_date, i.entity, coalesce(e.entity_group, i.entity_group) AS entity_group, i.signal,
       i.sentiment, i.importance, i.title, i.source_name, i.url
FROM (SELECT v.*, x.entity FROM v_market_intel_items v LATERAL VIEW explode(v.entities) x AS entity) i
LEFT JOIN v_market_intel_entities e ON e.entity = i.entity""")
    briefs = d.dataset("briefs", "Weekly briefs", """
SELECT week_start, week_end, headline, summary_md, n_items, n_sources, generated_at FROM v_market_intel_briefs""")
    watch = d.dataset("watch", "Watchlist", """
SELECT entity, entity_group, relationship, description, asx_code, website FROM v_market_intel_entities""")
    n = agg("n", "COUNT(*)", "Items", fmt_num())

    p = d.page("overview", "Overview")
    p.header("Market Intelligence", "Public news, web research and ASX announcements about Lochard, customers, competitors, "
             "suppliers, regulators and the east-coast gas market – classified by AI and summarised weekly by the Market "
             "Intelligence Analyst agent.", right="**Updated daily 07:00 AEST**  \nWeeks run Monday–Sunday")
    p.filter("date", "week_start", "Weeks", [items, ments], w=2)
    p.filter("multi", "entity_group", "Entity group", [items, ments])
    p.filter("multi", "topic", "Topic", [items])
    p.filter("multi", "signal", "Signal", [items, ments])
    p.filter("multi", "source_type", "Source type", [items])
    p.counter(items, n, "Relevant items")
    p.counter(items, agg("thr", "COUNT_IF(`signal` = 'Threat')", "Threats", fmt_num()), "Threats")
    p.counter(items, agg("opp", "COUNT_IF(`signal` = 'Opportunity')", "Opportunities", fmt_num()), "Opportunities")
    p.counter(items, agg("hi", "COUNT_IF(`importance` >= 4)", "High importance", fmt_num()), "High importance (4–5)")
    p.counter(items, agg("sent", "AVG(`sentiment`)", "Avg sentiment", fmt_num(2)), "Average sentiment",
              desc="-1 (negative for Lochard) to +1 (positive)")
    p.counter(items, agg("src", "COUNT(DISTINCT `source_name`)", "Publishers", fmt_num()), "Publishers")
    p.chart("bar", items, col("week_start", "Week"), [n], "Items per week by entity group", w=4, h=6,
            color=col("entity_group", "Entity group"), x_type="temporal", stacked=True)
    p.chart("line", items, col("week_start", "Week"), [agg("s", "AVG(`sentiment`)", "Average sentiment", fmt_num(2))],
            "Average sentiment by week", w=2, h=6, x_type="temporal")
    p.chart("bar", items, col("topic", "Topic"), [n], "Items by topic and signal", w=3, h=6,
            color=col("signal", "Signal"), stacked=True, color_map=sig)
    p.chart("bar", ments, col("entity", "Entity"), [agg("m", "COUNT(*)", "Mentions", fmt_num())], "Most-mentioned entities",
            w=3, h=6, color=col("entity_group", "Entity group"), stacked=True)
    p.table(items, [("published_date", "Date"), ("importance", "Importance"), ("signal", "Signal"), ("entity_group", "Group"),
                    ("title", "Title"), ("why_it_matters", "Why it matters"), ("source_name", "Publisher"), ("url", "Link")],
            "Items (most recent first)", h=9)

    t = d.page("explorer", "Item explorer")
    t.header("Item explorer", "Every relevant item with its AI summary. Filter, then open the original source.")
    t.filter("date", "published_date", "Published", [items], w=2)
    for f, title in [("entity_group", "Entity group"), ("primary_entity", "Entity"), ("topic", "Topic"), ("signal", "Signal")]:
        t.filter("multi", f, title, [items])
    t.table(items, [("published_date", "Date"), ("title", "Title"), ("source_name", "Publisher"), ("source_type", "Source type"),
                    ("primary_entity", "Entity"), ("entity_group", "Group"), ("topic", "Topic"), ("signal", "Signal"),
                    ("importance", "Importance"), ("sentiment", "Sentiment"), ("summary", "Summary"), ("url", "Link")],
            "Market intelligence items", h=14)

    e = d.page("entities", "Entities")
    e.header("Entities", "How often each watchlist entity featured, and with what signal, week by week.")
    e.filter("multi", "entity", "Entity", [ments], w=2)
    e.filter("multi", "entity_group", "Entity group", [ments, watch])
    e.filter("date", "week_start", "Weeks", [ments], w=2)
    e.chart("bar", ments, col("week_start", "Week"), [agg("m", "COUNT(*)", "Mentions", fmt_num())], "Mentions per week by signal",
            w=4, h=6, color=col("signal", "Signal"), x_type="temporal", stacked=True, color_map=sig)
    e.chart("line", ments, col("week_start", "Week"), [agg("s", "AVG(`sentiment`)", "Average sentiment", fmt_num(2))],
            "Sentiment by week", w=2, h=6, x_type="temporal", color=col("entity_group", "Entity group"))
    e.table(ments, [("published_date", "Date"), ("entity", "Entity"), ("signal", "Signal"), ("importance", "Importance"),
                    ("title", "Title"), ("source_name", "Publisher"), ("url", "Link")], "Mentions", h=8)
    e.table(watch, [("entity", "Entity"), ("entity_group", "Group"), ("relationship", "Relationship to Lochard"),
                    ("asx_code", "ASX"), ("website", "Website")], "Watchlist", h=7)

    b = d.page("briefs", "Weekly briefs")
    b.header("Weekly briefs", "The Market Intelligence Analyst agent's brief for each week. The portal's Market Intelligence page "
             "shows the full brief with cited items and the analyst's commentary.")
    b.filter("date", "week_start", "Weeks", [briefs], w=2)
    b.chart("bar", briefs, col("week_start", "Week"), [s("n_items", "Items", fmt_num())], "Relevant items per brief", w=6, h=5,
            x_type="temporal")
    b.table(briefs, [("week_start", "Week starting"), ("headline", "Headline"), ("summary_md", "Summary"), ("n_items", "Items"),
                     ("n_sources", "Publishers"), ("generated_at", "Generated")], "Briefs", h=10)
    return d


# ============================================================================================ Ops (Tableau INT091)
def ops() -> Dashboard:
    d = Dashboard("ops")
    cum = d.dataset("cum", "Cumulative VIC demand & EDD", """
SELECT gas_date, cast(gas_year AS STRING) AS gas_year, gas_month, concat(lpad(cast(gas_month AS STRING), 2, '0'), ' ',
       gas_month_name) AS month_label, date_without_year, total_gas_used_pj, cumulative_pj, edd_value, cumulative_edd,
       demand_source
FROM v_cumulative_vic_demand""")
    daily = d.dataset("daily", "Daily VIC demand vs EDD", """
SELECT gas_date, cast(gas_year AS STRING) AS gas_year, gas_month, day_name, CASE WHEN is_weekend THEN 'Weekend'
       ELSE 'Weekday' END AS day_type, edd_value, total_gas_used_tj, total_gas_used_pj, demand_source
FROM v_vic_gas_demand_daily WHERE edd_value IS NOT NULL
ORDER BY gas_date DESC""")
    yr_colors = {"2021": "#B5BD2A", "2022": "#8C564B", "2023": "#FF7F0E", "2024": "#1F77B4", "2025": K["crimson"],
                 "2026": K["grey"]}
    years = ["2021", "2022", "2023", "2024"]
    months = [str(m) for m in range(1, 9)]

    p = d.page("cum_demand", "Cumulative VIC demand")
    p.header("Cumulative VIC demand", "AEMO INT287 total gas used (VIC, GJ/day) – real nemweb data for recent days, "
             "history in the same format. Replaces Tableau *INT091 Actual EDD vs VIC demand*.")
    p.filter("multi", "gas_year", "Year of Gas Date", [cum], default=years, w=2)
    p.filter("multi", "gas_month", "Month of Gas Date", [cum], default=months, w=2)
    p.filter("multi", "demand_source", "Data source (AEMO real / history)", [cum], w=2)
    p.chart("line", cum, col("date_without_year", "Day of Date without Year"),
            [agg("max(cumulative_pj)", "MAX(`cumulative_pj`)", "Cumulative of total gas consumption (PJ)", fmt_num(1))],
            "Cumulative VIC demand", w=6, h=7, x_type="temporal", color=col("gas_year", "Year of Gas Date"),
            color_map=yr_colors)
    p.pivot(cum, [col("month_label", "Month of Gas Date")],
            [agg("sum(total_gas_used_pj)", "SUM(`total_gas_used_pj`)", "PJ", fmt_num(1))],
            "Cumulative VIC demand (Table)", columns=[col("gas_year", "Year")], w=6, h=6)

    e = d.page("cum_edd", "Cumulative EDD")
    e.header("Cumulative EDD", "AEMO INT091 actual effective degree days – the weather driver of VIC heating demand.")
    e.filter("multi", "gas_year", "Year", [cum], default=years, w=3)
    e.filter("multi", "gas_month", "Month", [cum], default=months, w=3)
    e.chart("line", cum, col("date_without_year", "Day of year"), [agg("max(cumulative_edd)", "MAX(`cumulative_edd`)",
            "Cumulative EDD", fmt_num(0))], "Cumulative EDD", w=6, h=7, x_type="temporal",
            color=col("gas_year", "Year"), color_map=yr_colors)
    e.pivot(cum, [col("month_label", "Month")], [agg("sum(edd_value)", "SUM(`edd_value`)", "EDD", fmt_num(0))],
            "Cumulative EDD (Table)", columns=[col("gas_year", "Year")], w=6, h=6)

    r = d.page("edd_vs_demand", "Actual EDD – VIC demand (R²)")
    r.header("Actual EDD vs VIC demand", "Daily demand against effective degree days. R² by weekday / weekend "
             "(Tableau R2 – Wk day Wk end / Any days / Consolidated).")
    r.filter("multi", "gas_year", "Year", [daily, "r2_segments"], default=["2021", "2022", "2023", "2024"], w=2)
    r.filter("multi", "gas_month", "Month", [daily])
    r.filter("multi", "day_name", "Days of the week", [daily], w=2)
    r.filter("multi", "day_type", "Weekday / Weekend", [daily])
    # R² per segment is computed in SQL (CORR); widget expressions can't evaluate CORR/POWER over filtered rows
    r2ds = d.dataset("r2_segments", "R² by year and day type", """
SELECT cast(gas_year AS STRING) AS gas_year, coalesce(day_type, 'All days') AS day_type,
       power(corr(edd_value, total_gas_used_tj), 2) AS r2, count(*) AS n_days
FROM (SELECT gas_year, CASE WHEN is_weekend THEN 'Weekend' ELSE 'Weekday' END AS day_type, edd_value, total_gas_used_tj
      FROM v_vic_gas_demand_daily WHERE edd_value IS NOT NULL)
GROUP BY GROUPING SETS ((gas_year, day_type), (gas_year))""")
    r.pivot(r2ds, [col("day_type", "Days")], [agg("max(r2)", "MAX(`r2`)", "R²", fmt_num(3))],
            "R² – EDD vs demand", columns=[col("gas_year", "Year")], w=2, h=3, totals=False)
    r.counter(daily, agg("avg_tj", "AVG(`total_gas_used_tj`)", "Avg daily demand (TJ)", fmt_num(0)), "Avg daily demand (TJ)",
              w=2, h=3)
    r.counter(daily, agg("avg_edd", "AVG(`edd_value`)", "Avg EDD", fmt_num(2)), "Avg EDD", w=2, h=3)
    r.chart("scatter", daily, col("edd_value", "EDD"), [agg("total_gas_used_tj", "`total_gas_used_tj`", "VIC demand (TJ)")],
            "Actual EDD – VIC demand", w=6, h=7, x_type="quantitative", color=col("day_type", "Day type"),
            color_map={"Weekday": K["sky"], "Weekend": K["orange"]})

    a = d.page("actual_demand", "Actual VIC demand")
    a.header("Actual VIC demand", "Monthly VIC demand (PJ) by year and daily detail (TJ).")
    a.filter("multi", "gas_year", "Year", [daily], default=["2023", "2024", "2025", "2026"], w=3)
    a.filter("multi", "gas_month", "Month", [daily], w=3)
    a.chart("bar", daily, col("gas_month", "Month"), [s("total_gas_used_pj", "PJ", fmt_num(1))], "Actual VIC demand",
            w=6, h=6, color=col("gas_year", "Year"), color_map=yr_colors, labels=False)
    a.table(daily, [("gas_date", "Gas date"), ("day_name", "Day"), ("edd_value", "EDD"),
                    ("total_gas_used_tj", "Demand (TJ)"), ("demand_source", "Source")], "Daily detail", h=8)
    return d


if __name__ == "__main__":
    for name, fn in [("finance_function_details", finance), ("hse_observations", hse),
                     ("maintenance_dashboard", maintenance), ("market_intelligence", market_intelligence),
                     ("ops_vic_demand_edd", ops)]:
        path = os.path.join(OUT, f"{name}.lvdash.json")
        fn().write(path)
        print("wrote", path)


# ============================================================================================ Platform dashboards
def ai_cost() -> Dashboard:
    d = Dashboard("ai_cost")
    use = d.dataset("usage", "AI Gateway usage", """
SELECT usage_date, event_time, model_service, destination_model, requester, status_code, latency_ms, input_tokens,
       output_tokens, total_tokens, experiment_arm, app, used_fallback, est_cost_usd,
       CASE WHEN used_fallback THEN 1 ELSE 0 END AS fallback_flag,      -- flags for rate counters (no CASE in widget exprs)
       CASE WHEN status_code >= 400 THEN 1 ELSE 0 END AS error_flag
FROM v_ai_cost WHERE model_service LIKE 'lochard%'""")
    fr = d.dataset("frontier", "Cost vs quality frontier", "SELECT * FROM v_ai_cost_frontier")
    ex = d.dataset("exp", "Experiment detail", "SELECT * FROM v_ai_cost_experiment")
    p = d.page("ai_cost", "AI Cost & Quality")
    p.header("AI Cost & Quality", "Unity AI Gateway – spend, tokens, latency and routing across Lochard model services, "
             "plus the cost-vs-quality experiment (same grounded board questions through every tier and the router).")
    p.filter("multi", "model_service", "Model service", [use])
    p.filter("date", "usage_date", "Date", [use], w=2)
    p.filter("multi", "arm", "Experiment arm", [ex, fr])
    p.newline()
    p.counter(use, agg("req", "COUNT(*)", "Requests", fmt_num()), "Requests")
    p.counter(use, agg("tok", "SUM(`total_tokens`)", "Tokens", fmt_num(1, True)), "Tokens")
    p.counter(use, agg("cost", "SUM(`est_cost_usd`)", "Est. cost (USD)", fmt_money(2, False)), "Est. AI cost (USD)")
    p.counter(use, agg("lat", "AVG(`latency_ms`)", "Avg latency (ms)", fmt_num()), "Avg latency (ms)")
    p.counter(use, agg("fb", "AVG(`fallback_flag`)", "Fallback rate", fmt_pct(1)), "Fallback rate")
    p.counter(use, agg("err", "AVG(`error_flag`)", "Error rate", fmt_pct(1)), "Error / throttled rate",
              desc="HTTP 4xx/5xx share. The 23-Sep spike is the first experiment run, when the reasoning tiers rejected "
                   "`temperature` (fixed; 100% success since).")
    p.chart("bar", fr, col("arm", "Arm"), [agg("q", "AVG(`avg_quality`)", "Avg quality (1-5)", fmt_num(2))],
            "Quality by arm (LLM judge, 1-5)", w=3, h=6, colors=[K["sky"]], labels=True)
    p.chart("bar", fr, col("arm", "Arm"), [agg("c", "AVG(`cost_per_100_answers_usd`)", "USD per 100 answers", fmt_money(3, False))],
            "Cost per 100 answers by arm", w=3, h=6, colors=[K["orange"]], labels=True)
    p.chart("scatter", fr, agg("c2", "`cost_per_100_answers_usd`", "USD per 100 answers"),
            [agg("q2", "`avg_quality`", "Avg quality")], "Cost vs quality frontier", w=3, h=6, x_type="quantitative",
            color=col("arm", "Arm"))
    p.chart("bar", use, agg("daily(usage_date)", 'DATE_TRUNC("DAY", `usage_date`)', "Day"),
            [agg("tok2", "SUM(`total_tokens`)", "Tokens")], "Tokens by day and model service", w=3, h=6, x_type="temporal",
            color=col("model_service", "Model service"), stacked=True)
    p.pivot(ex, [col("category", "Question type"), col("arm", "Arm")],
            [agg("aq", "AVG(`quality_score`)", "Quality", fmt_num(2)), agg("ac", "SUM(`est_cost_usd`)", "Cost (USD)", fmt_money(4, False)),
             agg("al", "AVG(`latency_ms`)", "Latency ms", fmt_num())], "Quality, cost and latency by question type", h=8)
    p.table(ex, [("qid", "Q"), ("category", "Type"), ("arm", "Arm"), ("routed_label", "Router label"),
                 ("served_model", "Served model"), ("quality_score", "Quality"), ("est_cost_usd", "Cost USD"),
                 ("latency_ms", "Latency"), ("question", "Question"), ("judge_reason", "Judge rationale")],
            "Experiment detail", h=8)
    return d


def data_quality() -> Dashboard:
    d = Dashboard("dq")
    ex = d.dataset("exp", "Expectations", """
SELECT *, concat(table_name, '.', expectation) AS rule_key, passed_records + failed_records AS total_records
FROM v_pipeline_expectations""")
    up = d.dataset("upd", "Pipeline updates", """
SELECT *, CASE WHEN final_state = 'COMPLETED' THEN 1 ELSE 0 END AS ok_flag,
       -- health KPI = outcome of each pipeline's most recent finished update (history stays in the table below)
       CASE WHEN row_number() OVER (PARTITION BY pipeline, final_state IS NOT NULL ORDER BY started_at DESC) = 1
                 AND final_state IS NOT NULL
            THEN CASE WHEN final_state = 'COMPLETED' THEN 1 ELSE 0 END END AS latest_ok_flag
FROM v_pipeline_updates""")
    fr = d.dataset("fresh", "Freshness", """
SELECT table_name, latest_business_date, sla_days, datediff(current_date(), latest_business_date) AS age_days,
       datediff(current_date(), latest_business_date) <= sla_days AS within_sla,
       CASE WHEN datediff(current_date(), latest_business_date) <= sla_days THEN 1 ELSE 0 END AS sla_flag
FROM v_table_freshness""")
    p = d.page("dq", "Data Quality & Pipelines")
    p.header("Data Quality & Pipelines", "Lakeflow Declarative Pipelines – expectation results (warn / drop / fail), "
             "quarantined rows, update outcomes and data freshness for every Lochard domain.")
    p.filter("multi", "pipeline", "Pipeline", [ex, up])
    p.filter("multi", "layer", "Layer", [ex])
    p.newline()
    p.counter(ex, agg("rules", "COUNT(DISTINCT `rule_key`)", "Expectations", fmt_num()), "Expectations monitored")
    p.counter(ex, agg("failed", "SUM(`failed_records`)", "Failed records", fmt_num()), "Records failing a rule")
    p.counter(ex, agg("rate", "SUM(`failed_records`) / SUM(`total_records`)", "Failure rate", fmt_pct(2)),
              "Overall failure rate")
    p.counter(up, agg("ok", "AVG(`latest_ok_flag`)", "Pipelines healthy", fmt_pct(0)), "Pipelines healthy (latest update)",
              desc="Share of pipelines whose most recent update completed. Every update, including failures, is listed in Pipeline updates.")
    p.counter(fr, agg("sla", "AVG(`sla_flag`)", "Within freshness SLA", fmt_pct(0)), "Tables within SLA", w=2,
              desc="Finance (GL to 31-Aug) and Maintenance (snapshot 4-Aug) are pinned to the August 2026 board period; "
                   "they refresh when the paused daily orchestrator is resumed.")
    p.chart("bar", ex, col("expectation", "Expectation"), [s("failed_records", "Failed records")],
            "Failed records by expectation", w=3, h=7, color=col("pipeline", "Pipeline"), stacked=True)
    p.pivot(ex, [col("pipeline", "Pipeline"), col("table_name", "Table"), col("expectation", "Expectation")],
            [s("passed_records", "Passed", fmt_num()), s("failed_records", "Failed", fmt_num()),
             agg("fr", "SUM(`failed_records`) / SUM(`total_records`)", "Failure rate", fmt_pct(2))],
            "Expectation results", w=3, h=7)
    p.table(up, [("pipeline", "Pipeline"), ("update_id", "Update"), ("started_at", "Started"), ("duration_s", "Seconds"),
                 ("final_state", "State"), ("error_events", "Errors")], "Pipeline updates", w=3, h=6)
    p.table(fr, [("table_name", "Table"), ("latest_business_date", "Latest data"), ("age_days", "Age (days)"),
                 ("sla_days", "SLA (days)"), ("within_sla", "Within SLA")], "Freshness", w=3, h=6)
    return d


def governance() -> Dashboard:
    d = Dashboard("gov")
    au = d.dataset("audit", "Access audit", "SELECT * FROM v_access_audit")
    tg = d.dataset("tags", "Governed tags", "SELECT * FROM v_governance_policies")
    p = d.page("governance", "Governance & Audit")
    p.header("Governance & Audit", "Unity Catalog governed tags driving ABAC masks / row filters on lochard_gold, and the "
             "audit trail of data, Genie, dashboard, model serving and app access.")
    p.filter("multi", "service_name", "Service", [au])
    p.filter("date", "event_date", "Date", [au], w=2)
    p.newline()
    p.counter(tg, agg("cols", "COUNT(*)", "Governed columns", fmt_num()), "Governed (tagged) columns", w=2)
    p.counter(au, agg("ev", "COUNT(*)", "Audit events", fmt_num()), "Audit events", w=2)
    p.counter(au, agg("pr", "COUNT(DISTINCT `principal`)", "Principals", fmt_num()), "Distinct principals", w=2)
    p.pivot(tg, [col("tag_name", "Tag"), col("tag_value", "Value")], [agg("n", "COUNT(*)", "Columns", fmt_num())],
            "Governed tags (drive ABAC policies)", w=2, h=7)
    p.chart("bar", au, agg("daily(event_date)", 'DATE_TRUNC("DAY", `event_date`)', "Day"), [agg("n2", "COUNT(*)", "Events")],
            "Audit events by service", w=4, h=7, x_type="temporal", color=col("service_name", "Service"), stacked=True)
    p.table(tg, [("table_name", "Table"), ("column_name", "Column"), ("tag_name", "Tag"), ("tag_value", "Value")],
            "Tagged columns", w=3, h=7)
    p.table(au, [("event_time", "Time"), ("principal", "Principal"), ("service_name", "Service"), ("action_name", "Action"),
                 ("object_name", "Object"), ("status_code", "Status")], "Audit trail", w=3, h=7)
    return d


if __name__ == "__main__":
    for name, fn in [("platform_ai_cost_quality", ai_cost), ("platform_data_quality", data_quality),
                     ("platform_governance_audit", governance)]:
        path = os.path.join(OUT, f"{name}.lvdash.json")
        fn().write(path)
        print("wrote", path)
