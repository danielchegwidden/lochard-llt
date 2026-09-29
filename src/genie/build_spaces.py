"""Generate resources/genie.yml – five Genie Agents (formerly Genie spaces) with instructions, example SQL,
sample questions and benchmarks. serialized_space is emitted as a JSON string containing bundle interpolation
(${var.catalog}, ${resources.schemas.semantic.name}) so the same definition deploys to dev and prod.
IDs are deterministic 32-hex (md5) and every list is sorted by id, as the Genie API requires.

  python src/genie/build_spaces.py
"""
from __future__ import annotations

import hashlib
import json
import os

SEM = "${var.catalog}.${resources.schemas.semantic.name}"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")

COMMON = [
    "You are answering questions for Lochard Energy, operator of the Iona Gas Storage Facility (Port Campbell, VIC) "
    "through the entity Iona Ops Trust. Currency is AUD, amounts exclude GST.",
    "The Australian financial year runs 1 July to 30 June: FY2027 = 1 Jul 2026 to 30 Jun 2027. Quarters: Q1 = Jul-Sep, "
    "Q2 = Oct-Dec, Q3 = Jan-Mar, Q4 = Apr-Jun. 'This year' means FY2027 unless the user says calendar year.",
    "Never reveal or guess people's names. Person columns may be masked (PERSON-xxxx) by governance policy – say so "
    "rather than trying to work around it.",
    "If a question cannot be answered from the data, say so clearly and suggest the closest question that can be answered.",
]


def _id(*p) -> str:
    return hashlib.md5("|".join(p).encode()).hexdigest()


def space(key, title, description, tables, instructions, examples, samples, benchmarks, metric_views=()):
    ss = {
        "version": 2,
        "config": {"sample_questions": sorted([{"id": _id(key, "sq", q), "question": [q]} for q in samples],
                                              key=lambda x: x["id"])},
        "data_sources": {"tables": sorted([{"identifier": f"{SEM}.{t}"} for t in tables], key=lambda x: x["identifier"]),
                         **({"metric_views": sorted([{"identifier": f"{SEM}.{m}"} for m in metric_views],
                                                    key=lambda x: x["identifier"])} if metric_views else {})},
        "instructions": {
            "text_instructions": [{"id": _id(key, "ti"), "content": [l + "\n" for l in COMMON + instructions]}],
            "example_question_sqls": sorted([{"id": _id(key, "ex", q), "question": [q], "sql": [sql.replace("{S}", SEM)]}
                                             for q, sql in examples], key=lambda x: x["id"]),
        },
        "benchmarks": {"questions": sorted([{"id": _id(key, "bm", q), "question": [q],
                                             "answer": [{"format": "SQL", "content": [sql.replace("{S}", SEM)]}]}
                                            for q, sql in benchmarks], key=lambda x: x["id"])},
    }
    return key, {"title": title, "description": description, "warehouse_id": "${var.warehouse_id}",
                 "serialized_space": json.dumps(ss, ensure_ascii=False)}


FINANCE = space(
    "finance_genie", "Lochard Finance",
    "Budget vs Actuals vs Year End Outlook (YEO) vs Committed cost for Iona Ops Trust by Function, Team, cost centre, "
    "project and GL account. GL transaction and PO drill-down.",
    ["v_finance_monthly", "v_gl_transaction_detail", "v_po_transaction_detail"],
    ["Budget and YEO are full-year figures; Actuals and Committed are year-to-date. Always filter financial_year "
     "(e.g. financial_year = 'FY2027').",
     "Variance = Actual - Budget. Negative variance means under-spend against budget; positive means over-spend.",
     "YEO (Year End Outlook) is the latest approved reforecast for the financial year (yeo_amount in v_finance_monthly).",
     "Committed cost = open Maximo purchase-order value not yet invoiced (committed_amount).",
     "Hierarchy: function > team > cc_short_name > cost_centre_key; projects: HUGS = Heytesbury Underground Gas Storage, "
     "SIB = stay-in-business capital. HUGS revised P50 budget forecast is $112.4M.",
     "Use v_gl_transaction_detail for individual GL entries (entry_no, posting_date, description, amount) and "
     "v_po_transaction_detail for PO lines. document_type MXO = Maximo-originated, PPI = posted purchase invoice, GJ = journal.",
     "Show money rounded to thousands (K) or millions (M) with a $ sign."],
    [("What is the FY2027 budget, YTD actuals, YEO and committed cost by team?",
      "SELECT team, SUM(budget_amount) AS budget, SUM(actual_amount) AS actuals, SUM(yeo_amount) AS yeo, "
      "SUM(committed_amount) AS committed FROM {S}.v_finance_monthly WHERE financial_year = 'FY2027' GROUP BY team "
      "ORDER BY budget DESC"),
     ("Which cost centres have the largest YTD spend in FY2027?",
      "SELECT cost_centre_key, cc_short_name, team, SUM(amount) AS actuals FROM {S}.v_gl_transaction_detail "
      "WHERE financial_year = 'FY2027' GROUP BY ALL ORDER BY actuals DESC LIMIT 10"),
     ("Show the HUGS transactions posted in August 2026",
      "SELECT posting_date, cost_centre_key, wo_number, po_number, account_name, description, amount "
      "FROM {S}.v_gl_transaction_detail WHERE cc_short_name = 'HUGS' AND month_start = DATE'2026-08-01' "
      "ORDER BY posting_date"),
     ("Which teams are forecasting (YEO) furthest below budget in FY2027?",
      "SELECT team, SUM(yeo_amount) - SUM(budget_amount) AS yeo_vs_budget FROM {S}.v_finance_monthly "
      "WHERE financial_year = 'FY2027' GROUP BY team ORDER BY yeo_vs_budget")],
    ["How are we tracking against the FY2027 budget?", "Which teams have the biggest committed costs?",
     "Show open purchase orders for Major Projects", "What drove the negative actuals in August 2026?"],
    [("What is the total FY2027 budget?",
      "SELECT SUM(budget_amount) FROM {S}.v_finance_monthly WHERE financial_year = 'FY2027'"),
     ("What are FY2027 year-to-date actuals?",
      "SELECT SUM(actual_amount) FROM {S}.v_finance_monthly WHERE financial_year = 'FY2027'"),
     ("What is the FY2027 YEO for Major Projects?",
      "SELECT SUM(yeo_amount) FROM {S}.v_finance_monthly WHERE financial_year = 'FY2027' AND team = 'Major Projects'"),
     ("What is the committed cost for Growth in FY2027?",
      "SELECT SUM(committed_amount) FROM {S}.v_finance_monthly WHERE financial_year = 'FY2027' AND team = 'Growth'"),
     ("What is the FY2027 budget for the HUGS cost centre short name?",
      "SELECT SUM(budget_amount) FROM {S}.v_finance_monthly WHERE financial_year = 'FY2027' AND cc_short_name = 'HUGS'"),
     ("What are YTD actuals on cost centre PRM-0021E in FY2027?",
      "SELECT SUM(amount) FROM {S}.v_gl_transaction_detail WHERE financial_year = 'FY2027' AND cost_centre_key = 'PRM-0021E'"),
     ("What is the variance of actuals versus budget for Employee Costs in FY2027?",
      "SELECT SUM(actual_amount) - SUM(budget_amount) FROM {S}.v_finance_monthly WHERE financial_year = 'FY2027' "
      "AND team = 'Employee Costs'"),
     ("How much FY2027 spend is classified as Emergent?",
      "SELECT SUM(amount) FROM {S}.v_gl_transaction_detail WHERE financial_year = 'FY2027' AND spend_classification = 'Emergent'")],
    metric_views=["mv_finance"])

HSE = space(
    "hse_genie", "Lochard HSE",
    "HSE observations (hazards, incidents, near misses, safe acts), investigations, risk ranks, close-out and "
    "lagging indicators (TRIFR, LTIFR, High Potential Events) for the Iona facility.",
    ["v_observation_detail", "v_hse_monthly", "v_investigation_counts"],
    ["Observations are rows with classification = 'INCIDENT'; investigations are classification = 'INVESTIGATION'. "
     "Unless asked about investigations, count only classification = 'INCIDENT'.",
     "Open means status IN ('NEW','INPROG'); use is_open. Closed means status = 'CLOSED'.",
     "observation_type values: HAZARD, INCIDENT, NEARMISS, SAFEACT, HAZARD_REPORT (legacy form, retired 2020), Other.",
     "incident_category values: GENERAL SAFETY, PROCESS SAFETY, PRODUCTION, ENVIRONMENTAL, Other. Risk ranks: HIGH, MEDIUM, "
     "LOW, Unknown (actual_risk_rank = assessed outcome; potential_risk_rank = worst credible outcome).",
     "A High Potential Event (HPE) is is_high_potential_event = true. TRIFR = recordable injuries per million hours "
     "worked (rolling 12 months) from v_hse_monthly.",
     "Legally privileged investigation rows may be hidden by governance; v_investigation_counts gives safe totals."],
    [("How many observations are currently open by risk rank?",
      "SELECT actual_risk_rank, COUNT(*) AS open_observations FROM {S}.v_observation_detail "
      "WHERE classification = 'INCIDENT' AND is_open GROUP BY actual_risk_rank ORDER BY open_observations DESC"),
     ("How many observations were raised each month this financial year by type?",
      "SELECT month_start, observation_type, COUNT(*) AS observations FROM {S}.v_observation_detail "
      "WHERE classification = 'INCIDENT' AND financial_year = 'FY2027' GROUP BY ALL ORDER BY month_start"),
     ("What is the latest rolling 12 month TRIFR?",
      "SELECT month_start, trifr_rolling_12m FROM {S}.v_hse_monthly ORDER BY month_start DESC LIMIT 1")],
    ["How many open HIGH risk observations do we have?", "Were there any High Potential Events in FY2027?",
     "Which plant areas raise the most hazards?", "How long does it take to close observations on average?"],
    [("How many observations are there in total?",
      "SELECT COUNT(*) FROM {S}.v_observation_detail WHERE classification = 'INCIDENT'"),
     ("How many observations are open?",
      "SELECT COUNT(*) FROM {S}.v_observation_detail WHERE classification = 'INCIDENT' AND is_open"),
     ("How many investigations are open?",
      "SELECT COUNT(*) FROM {S}.v_observation_detail WHERE classification = 'INVESTIGATION' AND is_open"),
     ("How many open observations have a HIGH actual risk rank?",
      "SELECT COUNT(*) FROM {S}.v_observation_detail WHERE classification = 'INCIDENT' AND is_open AND actual_risk_rank = 'HIGH'"),
     ("What share of observations are GENERAL SAFETY?",
      "SELECT COUNT_IF(incident_category = 'GENERAL SAFETY') / COUNT(*) FROM {S}.v_observation_detail WHERE classification = 'INCIDENT'"),
     ("How many High Potential Events occurred in FY2027?",
      "SELECT COUNT(*) FROM {S}.v_observation_detail WHERE is_high_potential_event AND financial_year = 'FY2027'")],
    metric_views=["mv_hse"])

MAINT = space(
    "maintenance_genie", "Lochard Maintenance",
    "Maximo work orders and the weekly schedule snapshot: schedule compliance, backlog, P1/P2 open work, overdue "
    "safety-critical work, scheduled vs completed hours by lead craft.",
    ["v_workorder_schedule_weekly", "v_workorder_detail"],
    ["For current KPIs always filter v_workorder_schedule_weekly to is_latest_snapshot = true.",
     "Scheduled compliance % = SUM(schedule_compliant_count) / SUM(scheduled_count) for the schedule week in question "
     "(schedule_week_start is the Monday). 'Current' compliance = the latest schedule_week_start in the latest snapshot.",
     "Backlog excluding PMs = SUM(backlog_count) WHERE work_type <> 'PM'. Open = is_open. Open P2 excl PMs = SUM(workorder_count) "
     "WHERE priority_bucket = 'P2' AND work_type <> 'PM' AND is_open.",
     "Overdue safety critical = SUM(overdue_safety_critical_count) in the latest snapshot.",
     "Work types: PM preventive, CBM condition-based, DM defect/breakdown, GPC general plant care, MOD modification, "
     "EM emergency. Scheduled hours = est_dur_scheduled; completed hours = est_dur_compliant."],
    [("What is the schedule compliance for each of the last 13 weeks?",
      "SELECT schedule_week_start, SUM(schedule_compliant_count) / SUM(scheduled_count) AS compliance_pct "
      "FROM {S}.v_workorder_schedule_weekly WHERE is_latest_snapshot AND schedule_week_start IS NOT NULL "
      "GROUP BY schedule_week_start ORDER BY schedule_week_start"),
     ("What is the backlog excluding PMs by priority?",
      "SELECT priority_bucket, SUM(backlog_count) AS backlog FROM {S}.v_workorder_schedule_weekly "
      "WHERE is_latest_snapshot AND work_type <> 'PM' GROUP BY priority_bucket ORDER BY priority_bucket")],
    ["What is our current schedule compliance?", "How many overdue safety critical work orders are there?",
     "Which lead crafts have the most scheduled hours?", "How has compliance trended over the last quarter?"],
    [("What is the current scheduled compliance percentage?",
      "SELECT SUM(schedule_compliant_count) / SUM(scheduled_count) FROM {S}.v_workorder_schedule_weekly WHERE "
      "is_latest_snapshot AND schedule_week_start = (SELECT max(schedule_week_start) FROM {S}.v_workorder_schedule_weekly "
      "WHERE is_latest_snapshot)"),
     ("How many overdue safety critical work orders are there?",
      "SELECT SUM(overdue_safety_critical_count) FROM {S}.v_workorder_schedule_weekly WHERE is_latest_snapshot"),
     ("How many open P1 work orders are there?",
      "SELECT SUM(workorder_count) FROM {S}.v_workorder_schedule_weekly WHERE is_latest_snapshot AND priority_bucket = 'P1' AND is_open"),
     ("What is the backlog excluding PMs?",
      "SELECT SUM(backlog_count) FROM {S}.v_workorder_schedule_weekly WHERE is_latest_snapshot AND work_type <> 'PM'"),
     ("How many PM work orders were scheduled across the last 13 weeks?",
      "SELECT SUM(scheduled_count) FROM {S}.v_workorder_schedule_weekly WHERE is_latest_snapshot AND work_type = 'PM'")],
    metric_views=["mv_maintenance"])

MARKET = space(
    "market_ops_genie", "Lochard Gas Market & Iona Ops",
    "Victorian gas demand (AEMO INT287) and effective degree days (INT091), cumulative demand by year, Iona injection / "
    "withdrawal / inventory, market price and customer nominations vs the ±4% delivery tolerance.",
    ["v_vic_gas_demand_daily", "v_cumulative_vic_demand", "v_iona_operations_daily", "v_nominations"],
    ["Units: total_gas_used_gj is GJ per gas day; 1 TJ = 1,000 GJ; 1 PJ = 1,000 TJ. Present demand in TJ/day or PJ.",
     "EDD (effective degree days) is AEMO's weather index for heating demand – higher EDD = colder = more gas demand.",
     "demand_source / edd_source = 'AEMO' for real nemweb data (recent days) and 'SYNTHETIC' for backfilled history.",
     "Iona: working inventory in PJ (capacity ~24.4 PJ, 26.2 PJ after HUGS), withdrawal up to ~570 TJ/day. "
     "net_withdrawal_tj = withdrawal - injection.",
     "Nominations: within_tolerance = |delivered / nominated - 1| <= 4% (scorecard KPI 1.2)."],
    [("What was total VIC gas demand by month in 2024 in PJ?",
      "SELECT gas_month, SUM(total_gas_used_pj) AS demand_pj FROM {S}.v_vic_gas_demand_daily WHERE gas_year = 2024 "
      "GROUP BY gas_month ORDER BY gas_month"),
     ("How well does EDD explain demand on weekdays vs weekends?",
      "SELECT is_weekend, POWER(CORR(edd_value, total_gas_used_tj), 2) AS r_squared FROM {S}.v_vic_gas_demand_daily "
      "GROUP BY is_weekend"),
     ("What share of nominations were delivered within tolerance in FY2027?",
      "SELECT AVG(CASE WHEN within_tolerance THEN 1 ELSE 0 END) FROM {S}.v_nominations WHERE financial_year = 'FY2027'")],
    ["How does cumulative VIC demand this year compare to 2021-2024?", "What is Iona's current inventory?",
     "What was the peak Iona withdrawal day this winter?", "How much real AEMO data do we have?"],
    [("What was total VIC demand from January to August 2021 in PJ?",
      "SELECT SUM(total_gas_used_pj) FROM {S}.v_vic_gas_demand_daily WHERE gas_year = 2021 AND gas_month <= 8"),
     ("What was VIC demand in July 2022 in PJ?",
      "SELECT SUM(total_gas_used_pj) FROM {S}.v_vic_gas_demand_daily WHERE gas_year = 2022 AND gas_month = 7"),
     ("What is the latest Iona inventory in PJ?",
      "SELECT inventory_pj FROM {S}.v_iona_operations_daily ORDER BY gas_date DESC LIMIT 1"),
     ("How many nomination deliveries were outside tolerance in FY2027?",
      "SELECT COUNT_IF(NOT within_tolerance) FROM {S}.v_nominations WHERE financial_year = 'FY2027'")],
    metric_views=["mv_market", "mv_iona_ops"])

EXEC = space(
    "exec_genie", "Lochard Executive & Board",
    "Board and Lochard Leadership Team view: FY27 scorecard (status, weights, board scores, commentary) with the governed "
    "headline KPIs for Finance, HSE, Maintenance, Gas Market and Iona operations, plus weekly market intelligence (public "
    "news and announcements about Lochard, customers, competitors, suppliers, regulators and the gas market).",
    ["v_board_scorecard", "v_board_comments", "v_investigation_counts", "v_hse_monthly", "v_nominations",
     "v_market_intel_items", "v_market_intel_briefs", "v_market_intel_entities"],
    ["Audience: Board directors and the Lochard Leadership Team (LLT). Lead with the answer, then 2-3 supporting facts "
     "with the period and source.",
     "Scorecard: v_board_scorecard has one row per KPI per reporting period (period_code e.g. FY27-M02 = August 2026). "
     "Status values ON_TRACK, AT_RISK, OFF_TRACK, COMPLETE. Weights sum to 100% per financial year.",
     "Weighted status index = SUM(weight_pct * status_points) / SUM(weight_pct) where On Track / Complete = 1, "
     "At Risk = 0.5, Off Track = 0. Board score = average director score (0-5).",
     "Owners are shown as role initials (DA = COO, BN = GM Commercial, DS = GM Project Delivery, DG = GM Development, "
     "LLT = Leadership Team). Never name individuals.",
     "For headline KPIs use the metric views: mv_finance (budget / actuals / YEO / committed), mv_hse (observations, HPEs), "
     "mv_maintenance (schedule compliance, backlog – filter is_latest_snapshot), mv_market (VIC demand, EDD), "
     "mv_iona_ops (inventory, flows) and mv_board (status index, board score, KPIs at risk).",
     "Investigation detail is restricted – use v_investigation_counts for counts.",
     "Market intelligence: v_market_intel_items has one row per public news item or announcement (week_start = Monday, "
     "entity_group in Lochard / Customer / Competitor / Upstream supplier / Regulator & market body / Government & policy / "
     "Industry & market; signal Opportunity / Threat / Watch / Neutral from Lochard's perspective; importance 1-5). "
     "v_market_intel_briefs has the weekly brief written by the Market Intelligence Analyst agent (headline, summary_md). "
     "'Last week' means the most recent complete Monday-Sunday week. Always include the title, publisher and url of items "
     "you cite, and say that the items are public sources summarised by AI."],
    [("What were the most important market developments last week?",
      "SELECT published_date, title, source_name, entity_group, signal, importance, why_it_matters, url FROM {S}.v_market_intel_items "
      "WHERE week_start = date_sub(date_trunc('WEEK', current_date()), 7) ORDER BY importance DESC, published_date DESC LIMIT 10"),
     ("What did competitors do in the last four weeks?",
      "SELECT published_date, primary_entity, title, signal, why_it_matters, url FROM {S}.v_market_intel_items "
      "WHERE entity_group = 'Competitor' AND week_start >= date_sub(date_trunc('WEEK', current_date()), 28) "
      "ORDER BY importance DESC, published_date DESC"),
     ("Which FY27 scorecard KPIs are at risk and why?",
      "SELECT kpi_code, kpi_name, weight_pct, status, commentary FROM {S}.v_board_scorecard WHERE fy_code = 'FY27' "
      "AND period_code = (SELECT max(period_code) FROM {S}.v_board_scorecard WHERE fy_code = 'FY27' AND status IS NOT NULL) "
      "AND status IN ('AT_RISK', 'OFF_TRACK') ORDER BY kpi_code"),
     ("What is the weighted scorecard status index by month in FY27?",
      "SELECT period_code, SUM(weight_pct * status_points) / SUM(weight_pct) AS status_index FROM {S}.v_board_scorecard "
      "WHERE fy_code = 'FY27' AND status IS NOT NULL GROUP BY period_code ORDER BY period_code"),
     ("How did FY26 finish on the scorecard?",
      "SELECT kpi_code, kpi_name, weight_pct, status, avg_board_score FROM {S}.v_board_scorecard WHERE period_code = 'FY26-M12' "
      "ORDER BY kpi_code")],
    ["How are we tracking on the FY27 scorecard?", "Which KPIs are at risk and what is the commentary?",
     "What were the key market developments for Lochard last week?",
     "How do board scores compare with management's status?", "What are the headline HSE and finance numbers this month?"],
    [("What is the FY27 weighted status index for August 2026?",
      "SELECT SUM(weight_pct * status_points) / SUM(weight_pct) FROM {S}.v_board_scorecard WHERE period_code = 'FY27-M02'"),
     ("How many FY27 KPIs are at risk in August 2026?",
      "SELECT COUNT(*) FROM {S}.v_board_scorecard WHERE period_code = 'FY27-M02' AND status = 'AT_RISK'"),
     ("What is the weight of the HSE Performance KPI in FY27?",
      "SELECT weight_pct FROM {S}.v_board_scorecard WHERE fy_code = 'FY27' AND kpi_code = '1.1' LIMIT 1"),
     ("What is the average board score for HUGS Delivery in August 2026?",
      "SELECT avg_board_score FROM {S}.v_board_scorecard WHERE period_code = 'FY27-M02' AND kpi_code = '2.1'")],
    metric_views=["mv_board", "mv_finance", "mv_hse", "mv_maintenance", "mv_market", "mv_iona_ops"])


def main():
    spaces = [FINANCE, HSE, MAINT, MARKET, EXEC]
    lines = ["# GENERATED by src/genie/build_spaces.py – Genie Agents (formerly Genie spaces). Do not edit by hand.",
             "resources:", "  genie_spaces:"]
    for key, spec in spaces:
        lines.append(f"    {key}:")
        for k in ["title", "description", "warehouse_id", "serialized_space"]:
            lines.append(f"      {k}: {json.dumps(spec[k], ensure_ascii=False)}")
        lines.append("      permissions:")
        lines.append("        - {group_name: users, level: CAN_RUN}")
    path = os.path.join(ROOT, "resources", "genie.yml")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote", path)


if __name__ == "__main__":
    main()
