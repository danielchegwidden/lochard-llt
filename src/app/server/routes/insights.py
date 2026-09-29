"""Leadership Insights – KPI tiles, comparisons and trends for any reporting period, plus per-KPI evidence.
Everything is read from lochard_semantic on behalf of the viewer, so Unity Catalog row filters and masks apply."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from fastapi import APIRouter, Depends

from .. import auth, db, sql
from ..periods import Period, month_add
from . import commentary
from .scorecard import me_dep

router = APIRouter(prefix="/api")
FY = "FY2027"
HUGS_P50 = 112_400_000
DOMAINS = ("finance", "hse", "maintenance", "operations")
EARLIEST = date(2021, 7, 1)          # first month with finance actuals


def _v(name):
    return sql.fq(name)


# ------------------------------------------------------------------------------------------------ period tiles
# Named parameters: :s/:e = period start/end, :ps/:pe = prior corresponding period, :fy = FY of the anchor month.
TILES = {
    "finance": f"""
        WITH f AS (SELECT * FROM {_v('v_finance_monthly')}),
             last_actual AS (SELECT max(month_start) AS m FROM f WHERE actual_amount <> 0)
        SELECT CASE WHEN DATE(:s) <= (SELECT m FROM last_actual)          -- NULL until the first month is posted
                    THEN SUM(CASE WHEN month_start BETWEEN DATE(:s) AND DATE(:e) THEN actual_amount END) END AS actuals,
               SUM(CASE WHEN month_start BETWEEN DATE(:s) AND least(DATE(:e), (SELECT m FROM last_actual))
                        THEN budget_amount END) AS budget,
               -- like for like: the prior year only over the months that are posted this year
               SUM(CASE WHEN month_start BETWEEN DATE(:ps) AND least(DATE(:pe), add_months((SELECT m FROM last_actual), -12))
                        THEN actual_amount END) AS actuals_pcp,
               SUM(CASE WHEN financial_year = :fy THEN budget_amount END) AS budget_fy,
               SUM(CASE WHEN financial_year = :fy THEN yeo_amount END) AS yeo_fy,
               SUM(CASE WHEN financial_year = :fy THEN committed_amount END) AS committed,
               (SELECT m FROM last_actual) AS actuals_to
        FROM f WHERE month_start BETWEEN least(DATE(:ps), add_months(DATE(:s), -12)) AND add_months(DATE(:e), 12)""",
    "hse": f"""
        WITH d AS (SELECT * FROM {_v('v_observation_detail')}),
             -- a month still in progress is compared with the same days a year earlier
             lim AS (SELECT least(DATE(:pe), add_months(max(reported_date), -12)) AS pe FROM d)
        SELECT COUNT_IF(classification = 'INCIDENT' AND reported_date BETWEEN DATE(:s) AND DATE(:e)) AS obs,
               COUNT_IF(classification = 'INCIDENT' AND reported_date BETWEEN DATE(:ps) AND lim.pe) AS obs_pcp,
               COUNT_IF(classification = 'INCIDENT' AND actual_risk_rank = 'HIGH'
                        AND reported_date BETWEEN DATE(:s) AND DATE(:e)) AS high,
               COUNT_IF(classification = 'INCIDENT' AND actual_risk_rank = 'HIGH'
                        AND reported_date BETWEEN DATE(:ps) AND lim.pe) AS high_pcp,
               COUNT_IF(is_high_potential_event AND reported_date BETWEEN DATE(:s) AND DATE(:e)) AS hpe,
               COUNT_IF(is_high_potential_event AND reported_date BETWEEN DATE(:ps) AND lim.pe) AS hpe_pcp,
               COUNT_IF(classification = 'INCIDENT' AND is_open) AS open_now,
               COUNT_IF(classification = 'INCIDENT' AND is_open AND actual_risk_rank = 'HIGH') AS open_high_now,
               COUNT_IF(classification = 'INVESTIGATION' AND is_open) AS open_investigations,
               max(reported_date) AS data_to
        FROM d CROSS JOIN lim""",
    "hse_trifr": f"""
        SELECT max_by(trifr_rolling_12m, month_start) FILTER (WHERE month_start <= DATE(:e)) AS trifr,
               max_by(trifr_rolling_12m, month_start) FILTER (WHERE month_start <= DATE(:pe)) AS trifr_pcp,
               max(month_start) FILTER (WHERE month_start <= DATE(:e)) AS trifr_month
        FROM {_v('v_hse_monthly')}""",
    "maintenance": f"""
        WITH w AS (SELECT *, max(snapshot_date) OVER (PARTITION BY schedule_week_start) AS last_snap
                   FROM {_v('v_workorder_schedule_weekly')} WHERE schedule_week_start IS NOT NULL),
             wk AS (SELECT schedule_week_start AS wk, SUM(schedule_compliant_count) AS c, SUM(scheduled_count) AS n
                    FROM w WHERE snapshot_date = last_snap GROUP BY 1),
             snaps AS (SELECT max(snapshot_date) FILTER (WHERE snapshot_date <= DATE(:e)) AS cur,
                              max(snapshot_date) FILTER (WHERE snapshot_date <= DATE(:pe)) AS pcp
                       FROM {_v('v_workorder_schedule_weekly')}),
             s AS (SELECT v.*, v.snapshot_date = (SELECT cur FROM snaps) AS is_cur
                   FROM {_v('v_workorder_schedule_weekly')} v
                   WHERE v.snapshot_date IN ((SELECT cur FROM snaps), (SELECT pcp FROM snaps)))
        SELECT (SELECT SUM(c) / SUM(n) FROM wk WHERE wk BETWEEN DATE(:s) AND DATE(:e)) AS compliance,
               (SELECT SUM(c) / SUM(n) FROM wk WHERE wk BETWEEN DATE(:ps) AND DATE(:pe)) AS compliance_pcp,
               (SELECT max_by(c / n, wk) FROM wk WHERE wk <= DATE(:e)) AS compliance_latest,
               (SELECT max(wk) FROM wk WHERE wk <= DATE(:e)) AS compliance_latest_week,
               (SELECT count(*) FROM wk WHERE wk BETWEEN DATE(:s) AND DATE(:e)) AS weeks,
               SUM(CASE WHEN is_cur THEN overdue_safety_critical_count END) AS overdue_sc,
               SUM(CASE WHEN NOT is_cur THEN overdue_safety_critical_count END) AS overdue_sc_pcp,
               SUM(CASE WHEN is_cur AND work_type <> 'PM' THEN backlog_count END) AS backlog_ex_pm,
               SUM(CASE WHEN NOT is_cur AND work_type <> 'PM' THEN backlog_count END) AS backlog_ex_pm_pcp,
               SUM(CASE WHEN is_cur AND priority_bucket = 'P2' AND work_type <> 'PM' AND is_open
                        THEN workorder_count END) AS open_p2,
               SUM(CASE WHEN NOT is_cur AND priority_bucket = 'P2' AND work_type <> 'PM' AND is_open
                        THEN workorder_count END) AS open_p2_pcp,
               (SELECT cur FROM snaps) AS snapshot_date
        FROM s""",
    "operations": f"""
        WITH io AS (SELECT * FROM {_v('v_iona_operations_daily')}),
             vd AS (SELECT * FROM {_v('v_vic_gas_demand_daily')}),
             lim AS (SELECT least(DATE(:e), (SELECT max(gas_date) FROM vd)) AS e,
                            add_months(least(DATE(:e), (SELECT max(gas_date) FROM vd)), -12) AS pe),
             io_to AS (SELECT max(gas_date) AS d FROM io WHERE gas_date <= DATE(:e))
        SELECT (SELECT max_by(inventory_pj, gas_date) FROM io WHERE gas_date <= DATE(:e)) AS inventory_pj,
               (SELECT max_by(inventory_pj, gas_date) FROM io
                  WHERE gas_date <= (SELECT add_months(d, -12) FROM io_to)) AS inventory_pcp,
               (SELECT max(gas_date) FROM io WHERE gas_date <= DATE(:e)) AS as_of,
               (SELECT max_by(inventory_fill_pct, gas_date) FROM io WHERE gas_date <= DATE(:e)) AS fill_pct,
               (SELECT SUM(withdrawal_tj) / 1000 FROM io WHERE gas_date BETWEEN DATE(:s) AND DATE(:e)) AS withdrawals_pj,
               (SELECT SUM(injection_tj) / 1000 FROM io WHERE gas_date BETWEEN DATE(:s) AND DATE(:e)) AS injections_pj,
               (SELECT AVG(CASE WHEN within_tolerance THEN 1 ELSE 0 END) FROM {_v('v_nominations')}
                  WHERE gas_date BETWEEN DATE(:s) AND DATE(:e)) AS noms_within_tol,
               (SELECT AVG(CASE WHEN within_tolerance THEN 1 ELSE 0 END) FROM {_v('v_nominations')}
                  WHERE gas_date BETWEEN DATE(:ps) AND (SELECT pe FROM lim)) AS noms_within_tol_pcp,
               (SELECT SUM(total_gas_used_pj) FROM vd WHERE gas_date BETWEEN DATE(:s) AND (SELECT e FROM lim)) AS vic_demand_pj,
               (SELECT SUM(total_gas_used_pj) FROM vd WHERE gas_date BETWEEN DATE(:ps) AND (SELECT pe FROM lim)) AS vic_demand_pcp_pj,
               (SELECT e FROM lim) AS demand_to""",
}


def _trend_sql(p: Period) -> dict[str, tuple[str, dict]]:
    """Chart series for the period: the selected months are highlighted inside a wider context window."""
    par = p.params()
    r12 = p.grain == "r12"
    ws12, we = p.window(12)
    wsx, _ = p.window(24 if r12 else 12)        # rolling 12 months: show the year before too, so the highlight means something
    ws13w = wsx if r12 else min(p.start, month_add(p.anchor, -3))
    fin_cumulative = not r12
    out = {
        "finance": (f"""
            WITH m AS (SELECT fy_month_num, date_format(min(month_start), 'MMM') AS mon, SUM(budget_amount) AS b,
                              SUM(yeo_amount) AS yeo, SUM(actual_amount) AS a
                       FROM {_v('v_finance_monthly')} WHERE financial_year = :fy GROUP BY fy_month_num)
            SELECT fy_month_num AS x, mon AS label, 'Budget' AS series, SUM(b) OVER (ORDER BY fy_month_num) AS y FROM m
            UNION ALL SELECT fy_month_num, mon, 'YEO', SUM(yeo) OVER (ORDER BY fy_month_num) FROM m
            UNION ALL SELECT x, label, 'Actuals', y FROM (
                SELECT fy_month_num AS x, mon AS label, a, SUM(a) OVER (ORDER BY fy_month_num) AS y FROM m) WHERE a <> 0
            ORDER BY x""", {"fy": par["fy"]}) if fin_cumulative else (f"""
            SELECT month_start AS x, 'Actuals' AS series, SUM(actual_amount) AS y FROM {_v('v_finance_monthly')}
            WHERE month_start BETWEEN DATE(:s) AND DATE(:e) GROUP BY ALL HAVING SUM(actual_amount) <> 0
            UNION ALL SELECT month_start, 'Budget', SUM(budget_amount) FROM {_v('v_finance_monthly')}
            WHERE month_start BETWEEN DATE(:s) AND DATE(:e) GROUP BY ALL ORDER BY x""", {"s": wsx.isoformat(), "e": par["e"]}),
        "hse": (f"""
            SELECT month_start AS x, 'Observations' AS series, COUNT(*) AS y FROM {_v('v_observation_detail')}
            WHERE classification = 'INCIDENT' AND month_start BETWEEN DATE(:ws) AND DATE(:we) GROUP BY ALL ORDER BY x""",
                {"ws": wsx.isoformat(), "we": we.isoformat()}),
        "maintenance": (f"""
            WITH w AS (SELECT *, max(snapshot_date) OVER (PARTITION BY schedule_week_start) AS last_snap
                       FROM {_v('v_workorder_schedule_weekly')} WHERE schedule_week_start IS NOT NULL)
            SELECT schedule_week_start AS x, 'Compliance %' AS series, SUM(schedule_compliant_count) / SUM(scheduled_count) AS y
            FROM w WHERE snapshot_date = last_snap AND schedule_week_start BETWEEN DATE(:ws) AND DATE(:we)
            GROUP BY ALL ORDER BY x""", {"ws": ws13w.isoformat(), "we": we.isoformat()}),
        "market": (f"""
            SELECT month_start AS x, series, y FROM (
              SELECT trunc(gas_date, 'MM') AS month_start, 'This year' AS series, SUM(total_gas_used_pj) AS y
              FROM {_v('v_vic_gas_demand_daily')} WHERE gas_date BETWEEN DATE(:ws) AND DATE(:we) GROUP BY ALL
              UNION ALL
              SELECT add_months(trunc(gas_date, 'MM'), 12), 'Prior year', SUM(total_gas_used_pj)
              FROM {_v('v_vic_gas_demand_daily')}
              WHERE gas_date BETWEEN add_months(DATE(:ws), -12)          -- a month in progress: same days last year
                    AND add_months(least(DATE(:we), (SELECT max(gas_date) FROM {_v('v_vic_gas_demand_daily')})), -12)
              GROUP BY ALL)
            ORDER BY x, series""", {"ws": ws12.isoformat(), "we": we.isoformat()}),
        "operations": (f"""
            SELECT CAST(date_trunc('WEEK', gas_date) AS DATE) AS x, 'Inventory (PJ)' AS series, AVG(inventory_pj) AS y
            FROM {_v('v_iona_operations_daily')} WHERE gas_date BETWEEN DATE(:ws) AND DATE(:we) GROUP BY ALL ORDER BY x""",
                       {"ws": wsx.isoformat(), "we": we.isoformat()}),
        "cumulative": (f"""
            SELECT day_of_year AS x, CAST(gas_year AS STRING) AS series, cumulative_pj AS y
            FROM {_v('v_cumulative_vic_demand')}
            WHERE gas_year BETWEEN year(DATE(:e)) - 3 AND year(DATE(:e)) AND day_of_year % 7 = 0 ORDER BY series, x""",
                       {"e": par["e"]}),
    }
    return out


def _run_many(token, items: dict[str, tuple[str, dict | None] | str]) -> dict:
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {k: ex.submit(sql.safe, token, *(q if isinstance(q, tuple) else (q, None))) for k, q in items.items()}
        return {k: f.result() for k, f in futs.items()}


def _default_anchor(token: str | None = None) -> date:
    """Latest closed reporting month = latest month with finance actuals. Queried as the viewer (the app's own identity
    cannot read the semantic layer); only a successful answer is cached, for 10 minutes."""
    if _anchor_cache and time.time() - _anchor_cache[0] < 600:
        return _anchor_cache[1]
    r = sql.safe(token, f"SELECT max(month_start) AS m FROM {_v('v_finance_monthly')} WHERE actual_amount <> 0")
    m = (r["rows"] or [{}])[0].get("m")
    if not m:
        return month_add(date.today().replace(day=1), -1)       # fall back to last month, uncached
    _anchor_cache[:] = [time.time(), date.fromisoformat(str(m)[:10])]
    return _anchor_cache[1]


_anchor_cache: list = []


def period_from(grain: str | None, anchor: str | None, token: str | None = None) -> Period:
    return Period.parse(grain, anchor, _default_anchor(token))


def domain_summary(token, p: Period) -> dict:
    """Tiles for every domain for one period (also used by the board pack and AI drafting)."""
    par = p.params()
    res = _run_many(token, {k: (q, par) for k, q in TILES.items()})
    out = {k: (v["rows"][0] if v["rows"] else {}) for k, v in res.items()}
    out["hse"] = {**out.get("hse", {}), **out.pop("hse_trifr", {})}
    return {"tiles": out, "errors": {k: v["error"] for k, v in res.items() if "error" in v}}


def domain_trends(token, p: Period) -> dict:
    res = _run_many(token, _trend_sql(p))
    return {k: {"rows": v["rows"], "error": v.get("error")} for k, v in res.items()}


def _scorecard_strip(u: auth.User, p: Period) -> dict | None:
    """Board scorecard status for the anchor month, when it is a board reporting period."""
    try:
        with db.tx(u.email, u.role) as cur:
            cur.execute("""SELECT r.period_code, r.label, r.state, r.fy_code, s.status_index_pct, s.kpis_at_risk,
                                  s.kpis_off_track, s.kpis, s.weighted_board_score_pct
                           FROM scorecard.reporting_period r LEFT JOIN scorecard.v_period_summary s USING (period_code)
                           WHERE r.month_start = %s""", (p.anchor,))
            r = cur.fetchone()
        return {k: (float(v) if hasattr(v, "is_finite") else v) for k, v in r.items()} if r else None
    except Exception:  # noqa: BLE001 – the strip is optional
        return None


@router.get("/insights/periods")
def periods(u: auth.User = Depends(me_dep)):
    latest = _default_anchor(u.token)
    today = date.today().replace(day=1)
    months, m = [], today
    while m >= EARLIEST:
        months.append(f"{m:%Y-%m}")
        m = month_add(m, -1)
    return {"default": {"grain": "fytd", "anchor": f"{latest:%Y-%m}"}, "latest_closed": f"{latest:%Y-%m}",
            "min": f"{EARLIEST:%Y-%m}", "max": f"{today:%Y-%m}", "months": months,
            "grains": [{"key": "month", "label": "Month"}, {"key": "quarter", "label": "Quarter"},
                       {"key": "fytd", "label": "FY to date"}, {"key": "r12", "label": "Rolling 12 months"}]}


@router.get("/insights/summary")
def summary(grain: str | None = None, anchor: str | None = None, u: auth.User = Depends(me_dep)):
    p = period_from(grain, anchor, u.token)
    out = domain_summary(u.token, p)
    return {**out, "period": p.as_dict(), "scorecard": _scorecard_strip(u, p)}


@router.get("/insights/trends")
def trends(grain: str | None = None, anchor: str | None = None, u: auth.User = Depends(me_dep)):
    p = period_from(grain, anchor, u.token)
    return {**domain_trends(u.token, p), "period": p.as_dict()}


# ------------------------------------------------------------------------------------------------ facts for AI drafts
def _m(v):
    return "n/a" if v is None else f"${float(v) / 1e6:,.2f}M"


def _pct(v):
    return "n/a" if v is None else f"{float(v) * 100:.1f}%"


def _n(v, d=0):
    return "n/a" if v is None else f"{float(v):,.{d}f}"


def facts_text(domain: str, t: dict, p: Period) -> str:
    head = f"Lochard Energy – {domain} – {p.label} (compared with {p.pcp().label}). Financial year {p.fy} (Jul–Jun)."
    if domain == "finance":
        body = [f"Actuals in period {_m(t.get('actuals'))}; budget for the same months {_m(t.get('budget'))}; "
                f"actuals in the prior corresponding period {_m(t.get('actuals_pcp'))}.",
                f"{p.fy} full-year budget {_m(t.get('budget_fy'))}; year-end outlook (YEO) {_m(t.get('yeo_fy'))}; "
                f"open commitments {_m(t.get('committed'))}. Actuals are posted to {str(t.get('actuals_to'))[:7]}."]
    elif domain == "hse":
        body = [f"Incident observations reported {_n(t.get('obs'))} (prior {_n(t.get('obs_pcp'))}); HIGH actual risk "
                f"{_n(t.get('high'))} (prior {_n(t.get('high_pcp'))}); high potential events {_n(t.get('hpe'))} "
                f"(prior {_n(t.get('hpe_pcp'))}).",
                f"Currently open observations {_n(t.get('open_now'))} of which HIGH risk {_n(t.get('open_high_now'))}; "
                f"open investigations {_n(t.get('open_investigations'))}; TRIFR rolling 12 months {_n(t.get('trifr'), 2)} "
                f"(prior {_n(t.get('trifr_pcp'), 2)})."]
    elif domain == "maintenance":
        body = [f"Schedule compliance in period {_pct(t.get('compliance'))} over {_n(t.get('weeks'))} weeks "
                f"(prior {_pct(t.get('compliance_pcp'))}; latest week {_pct(t.get('compliance_latest'))}).",
                f"As at the {str(t.get('snapshot_date'))[:10]} Maximo snapshot: overdue safety-critical work orders "
                f"{_n(t.get('overdue_sc'))} (prior {_n(t.get('overdue_sc_pcp'))}), backlog excluding PMs "
                f"{_n(t.get('backlog_ex_pm'))} (prior {_n(t.get('backlog_ex_pm_pcp'))}), open P2 excluding PMs "
                f"{_n(t.get('open_p2'))}."]
    else:
        body = [f"Iona inventory {_n(t.get('inventory_pj'), 1)} PJ at {str(t.get('as_of'))[:10]} (a year earlier "
                f"{_n(t.get('inventory_pcp'), 1)} PJ); withdrawals {_n(t.get('withdrawals_pj'), 1)} PJ and injections "
                f"{_n(t.get('injections_pj'), 1)} PJ in the period.",
                f"Customer nominations delivered within ±4% {_pct(t.get('noms_within_tol'))} (prior "
                f"{_pct(t.get('noms_within_tol_pcp'))}). Victorian gas demand {_n(t.get('vic_demand_pj'), 1)} PJ vs "
                f"{_n(t.get('vic_demand_pcp_pj'), 1)} PJ a year earlier (to {str(t.get('demand_to'))[:10]})."]
    return head + "\n" + "\n".join(body)


def _insights_facts(u: auth.User, subject: str, period_key: str) -> str:
    anchor = period_key.split(":", 1)[-1]
    p = Period.parse("month", anchor, _default_anchor(u.token))
    ytd = Period("fytd", p.anchor)
    t_m = domain_summary(u.token, p)["tiles"].get(subject, {})
    t_y = domain_summary(u.token, ytd)["tiles"].get(subject, {})
    return facts_text(subject, t_m, p) + "\n\nYear to date:\n" + facts_text(subject, t_y, ytd)


commentary.register_facts("insights", _insights_facts)


# ------------------------------------------------------------------------------------------------ KPI evidence (scorecard drawer)
EVIDENCE = {
    "1.1": [
        ("High Potential Events (FY27)", "count", f"SELECT COUNT_IF(is_high_potential_event AND financial_year = '{FY}') AS v FROM {_v('v_observation_detail')}", "lower"),
        ("Open HIGH risk observations", "count", f"SELECT COUNT_IF(classification = 'INCIDENT' AND is_open AND actual_risk_rank = 'HIGH') AS v FROM {_v('v_observation_detail')}", "lower"),
        ("Open observations", "count", f"SELECT COUNT_IF(classification = 'INCIDENT' AND is_open) AS v FROM {_v('v_observation_detail')}", "lower"),
        ("TRIFR (rolling 12 months)", "number", f"SELECT trifr_rolling_12m AS v FROM {_v('v_hse_monthly')} ORDER BY month_start DESC LIMIT 1", "lower"),
        ("Recordable injuries FY27", "count", f"SELECT SUM(recordable_injuries) AS v FROM {_v('v_hse_monthly')} WHERE financial_year = '{FY}'", "lower"),
    ],
    "1.2": [
        ("Nominations within ±4% (FY27)", "pct", f"SELECT AVG(CASE WHEN within_tolerance THEN 1 ELSE 0 END) AS v FROM {_v('v_nominations')} WHERE financial_year = '{FY}'", "higher"),
        ("Deliveries outside tolerance (FY27)", "count", f"SELECT COUNT_IF(NOT within_tolerance) AS v FROM {_v('v_nominations')} WHERE financial_year = '{FY}'", "lower"),
        ("Refunds payable (FY27)", "count", f"SELECT COUNT_IF(refund_payable) AS v FROM {_v('v_nominations')} WHERE financial_year = '{FY}'", "lower"),
        ("Current schedule compliance", "pct", f"""WITH s AS (SELECT * FROM {_v('v_workorder_schedule_weekly')} WHERE is_latest_snapshot)
               SELECT SUM(schedule_compliant_count) / SUM(scheduled_count) AS v FROM s
               WHERE schedule_week_start = (SELECT max(schedule_week_start) FROM s)""", "higher"),
    ],
    "1.3": [
        ("Opex Projects actuals FY27 YTD", "money", f"SELECT SUM(actual_amount) AS v FROM {_v('v_finance_monthly')} WHERE financial_year = '{FY}' AND team = 'Opex Projects'", None),
        ("Opex Projects YEO FY27", "money", f"SELECT SUM(yeo_amount) AS v FROM {_v('v_finance_monthly')} WHERE financial_year = '{FY}' AND team = 'Opex Projects'", None),
        ("Data Utilisation Project YEO", "money", f"SELECT SUM(yeo_amount) AS v FROM {_v('v_finance_monthly')} WHERE financial_year = '{FY}' AND cc_short_name = 'Data Utilisation Project'", None),
    ],
    "2.1": [
        ("HUGS actuals to date (all FYs)", "money", f"SELECT SUM(actual_amount) AS v FROM {_v('v_finance_monthly')} WHERE cc_short_name = 'HUGS'", None),
        ("HUGS FY27 YEO", "money", f"SELECT SUM(yeo_amount) AS v FROM {_v('v_finance_monthly')} WHERE cc_short_name = 'HUGS' AND financial_year = '{FY}'", None),
        ("HUGS estimate at completion", "money", f"""SELECT SUM(CASE WHEN financial_year < '{FY}' THEN actual_amount ELSE 0 END) +
                 SUM(CASE WHEN financial_year = '{FY}' THEN yeo_amount ELSE 0 END) AS v FROM {_v('v_finance_monthly')} WHERE cc_short_name = 'HUGS'""", f"<={HUGS_P50}"),
        ("Revised P50 budget", "money", f"SELECT {HUGS_P50} AS v", None),
        ("HUGS open commitments", "money", f"SELECT SUM(committed_amount) AS v FROM {_v('v_finance_monthly')} WHERE cc_short_name = 'HUGS'", None),
    ],
    "2.2": [
        ("Growth (Queen) actuals FY27 YTD", "money", f"SELECT SUM(actual_amount) AS v FROM {_v('v_finance_monthly')} WHERE financial_year = '{FY}' AND team = 'Growth'", None),
        ("Growth YEO vs budget FY27", "money", f"SELECT SUM(yeo_amount) - SUM(budget_amount) AS v FROM {_v('v_finance_monthly')} WHERE financial_year = '{FY}' AND team = 'Growth'", None),
        ("Growth open commitments", "money", f"SELECT SUM(committed_amount) AS v FROM {_v('v_finance_monthly')} WHERE financial_year = '{FY}' AND team = 'Growth'", None),
    ],
    "2.3": [
        ("Commercial actuals FY27 YTD", "money", f"SELECT SUM(actual_amount) AS v FROM {_v('v_finance_monthly')} WHERE financial_year = '{FY}' AND team = 'Commercial'", None),
        ("VIC demand YTD (PJ)", "number", f"SELECT SUM(total_gas_used_pj) AS v FROM {_v('v_vic_gas_demand_daily')} WHERE gas_year = year(current_date())", None),
    ],
    "3.1": [
        ("FY27 actuals YTD", "money", f"SELECT SUM(actual_amount) AS v FROM {_v('v_finance_monthly')} WHERE financial_year = '{FY}'", None),
        ("FY27 budget YTD", "money", f"""SELECT SUM(budget_amount) AS v FROM {_v('v_finance_monthly')} WHERE financial_year = '{FY}'
               AND month_start <= (SELECT max(month_start) FROM {_v('v_finance_monthly')} WHERE financial_year = '{FY}' AND actual_amount <> 0)""", None),
        ("FY27 YEO vs full-year budget", "money", f"SELECT SUM(yeo_amount) - SUM(budget_amount) AS v FROM {_v('v_finance_monthly')} WHERE financial_year = '{FY}'", None),
    ],
    "3.2": [],
}


def evidence_for(token, code: str) -> list[dict]:
    items = EVIDENCE.get(code, [])
    res = _run_many(token, {label: q for label, _, q, _ in items}) if items else {}
    out = []
    for label, kind, _, good in items:
        r = res[label]
        v = r["rows"][0].get("v") if r["rows"] else None
        out.append({"label": label, "value": v, "kind": kind, "target": good, "error": r.get("error")})
    return out


@router.get("/kpi/{kpi_id}/evidence")
def kpi_evidence(kpi_id: str, u: auth.User = Depends(me_dep)):
    code = kpi_id.split("-", 1)[-1]
    return {"kpi_id": kpi_id, "evidence": evidence_for(u.token, code)}
