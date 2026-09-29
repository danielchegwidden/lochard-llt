"""Board pack – twelve slides per board reporting period, the slide workflow and finalised PDF versions.

Slides 1–10 are assembled from live data: the same governed numbers as Leadership Insights (read as the viewer, via
insights.domain_summary / domain_trends) plus a few pack-specific queries (HUGS, finance by team, market intelligence).
Slides 11 and 12 are prepared by their owners. Every slide carries commentary through the shared commentary workflow
(scope 'boardpack', subject = slide key, period = board period code, e.g. FY27-M02); a slide is Ready once its
commentary is approved. Leaders choose which slides go in the pack, then finalise: the slide data and the approved
commentary are frozen as a numbered version together with its PDF (scorecard.board_pack / board_pack_content).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import auth, boardpack_pdf, db, sql
from ..periods import Period, month_add, month_end
from . import commentary, insights
from .scorecard import _rows, load_scorecard, me_dep

log = logging.getLogger("lochard.boardpack")
router = APIRouter(prefix="/api/boardpack")

CRIMSON, ORANGE, GREY, SKY, PINK = "#A3194E", "#F47525", "#565150", "#52B2E5", "#F3E3E9"
FULL_MON = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
            "November", "December"]
STATE_LABEL = {"OPEN": "Owner updates open", "OWNER_SUBMITTED": "Submitted to the leadership team",
               "LLT_REVIEWED": "Reviewed by the leadership team", "BOARD_ENDORSED": "Endorsed by the Board",
               "LOCKED": "Locked"}
KPI_STATUS = {"ON_TRACK": "On Track", "AT_RISK": "At Risk", "OFF_TRACK": "Off Track", "COMPLETE": "Complete"}

# key, title, short tab label, kind (live = generated from data, owner = prepared by the owner), default owner,
# commentary heading, writing prompt
SLIDES = [
    ("cover", "Cover & agenda", "Cover", "live", "Company Secretary", "Covering note",
     "Purpose of this pack, what the Board is asked to note or approve, and any late changes…"),
    ("exec_summary", "Executive summary", "Summary", "live", "Chief Executive Officer", "Chief Executive's summary",
     "The three or four things the Board needs to know this month, and what happens next…"),
    ("scorecard", "{fy} Board scorecard", "Scorecard", "live", "Lochard Leadership Team", "Scorecard commentary",
     "Overall progress against the scorecard, movements since last month and KPIs needing attention…"),
    ("hse", "Safety & HSE", "Safety", "live", "GM People, Safety & Sustainability", "Commentary",
     "Safety performance this month and year to date, significant events and actions…"),
    ("operations", "Iona operations", "Operations", "live", "Chief Operating Officer", "Commentary",
     "Storage position, injections and withdrawals, customer deliveries and plant availability…"),
    ("market", "Gas market & demand", "Market", "live", "GM Commercial", "Commentary",
     "Victorian demand and weather, peak days and what they mean for storage customers…"),
    ("maintenance", "Maintenance & asset integrity", "Maintenance", "live", "Head of Maintenance", "Commentary",
     "Schedule compliance, safety-critical work and backlog, and the recovery plan…"),
    ("finance", "Financial performance", "Finance", "live", "Chief Financial Officer", "Commentary",
     "Spend against budget for the month and year to date, the year-end outlook and key variances…"),
    ("hugs", "Major projects – HUGS", "HUGS", "live", "GM Project Delivery", "Commentary",
     "Cost to complete against the revised P50, schedule to RFSU, key risks and mitigations…"),
    ("market_intel", "Market intelligence", "Intelligence", "live", "Commercial Analyst", "Commentary",
     "The developments from the last four weeks that matter most to Lochard, and our response…"),
    ("risks", "Key risks", "Risks", "owner", "GM Finance, Risk & Digital", "Key risks",
     "The top risks this month – rating, movement since last meeting, and mitigations…"),
    ("decisions", "Decisions & resolutions for the Board", "Decisions", "owner", "Company Secretary",
     "Decisions & resolutions",
     "Resolutions sought (e.g. “That the Board approves…”) and matters for noting…"),
]
KEYS = [s[0] for s in SLIDES]
REQUIRED = {"cover"}                     # always in the pack
CURATORS = ("LLT",)                      # include / owner / finalise / mark as sent (ADMIN always allowed)
SEES_WORKFLOW = ("KPI_OWNER", "LLT", "ADMIN")
DOWNLOADERS = ("BOARD", "LLT", "KPI_OWNER")
INSIGHTS_TITLES = {"finance": "Finance", "hse": "Safety & HSE", "maintenance": "Maintenance",
                   "operations": "Iona operations & market", "market": "Gas market"}


# ------------------------------------------------------------------------------------------------ formatting
def fv(v, kind: str) -> str:
    """Display value – the same text is used on screen and in the PDF."""
    if v is None:
        return "–"
    v = float(v)
    if kind == "money":
        a, s = abs(v), "-" if v < 0 else ""
        if a >= 1e9:
            return f"{s}${a / 1e9:.2f}B"
        if a >= 1e6:
            return f"{s}${a / 1e6:.1f}M"
        if a >= 1e3:
            return f"{s}${a / 1e3:.0f}K"
        return f"{s}${a:.0f}"
    if kind == "pct":
        return f"{v * 100:.1f}%"
    if kind == "count":
        return f"{v:,.0f}"
    if kind == "pj":
        return f"{v:,.1f} PJ"
    if kind == "tj":
        return f"{v:,.0f} TJ"
    if kind == "rate":
        return f"{v:.2f}"
    return f"{v:,.1f}"


def _signed(d: float, kind: str) -> str:
    s = "+" if d > 0 else "-" if d < 0 else "±"
    a = abs(d)
    if kind == "money":
        return s + fv(a, "money")
    if kind == "pct":
        return f"{s}{a * 100:.1f} pts"
    return s + fv(a, kind)


def cmp(v, p, kind: str, better: str | None) -> dict | None:
    if v is None or p is None:
        return None
    v, p = float(v), float(p)
    d = v - p
    if abs(d) < 1e-9:
        return {"text": "no change", "tone": None}
    txt = _signed(d, kind)
    if kind in ("money", "count", "pj", "tj", "num") and v >= 0 and p > 0 and abs(d) > 1e-9:
        txt += f" ({d / p * 100:+.0f}%)"
    tone = None
    if better and abs(d) > 1e-9:
        tone = "good" if (d > 0) == (better == "higher") else "bad"
    return {"text": txt, "tone": tone}


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _div(a, b):
    a, b = _num(a), _num(b)
    return None if a is None or not b else a / b


def _sub(a, b):
    a, b = _num(a), _num(b)
    return None if a is None or b is None else a - b


def _day(d) -> str:
    if not d:
        return ""
    y, m, dd = (int(x) for x in str(d)[:10].split("-"))
    return f"{dd} {FULL_MON[m - 1][:3]} {y}"


def metric(L: dict, label: str, kind: str, m=None, mp=None, y=None, yp=None, *, better: str | None = None,
           note: str | None = None, point: bool = False, vs: str | None = None, tone: str | None = None) -> dict:
    """One key number: the reporting month (or a point-in-time value) and FY to date, each against the prior
    corresponding period."""
    out = {"label": label, "kind": kind, "note": note, "point": point, "tone": tone,
           "m": {"v": _num(m), "t": fv(m, kind), "p": None if mp is None else fv(mp, kind),
                 "d": cmp(m, mp, kind, better), "vs": vs or ("a year earlier" if point else L["month_pcp"]),
                 "label": "Now" if point else L["month"]},
           "y": None}
    if not point:
        out["y"] = {"v": _num(y), "t": fv(y, kind), "p": None if yp is None else fv(yp, kind),
                    "d": cmp(y, yp, kind, better), "vs": L["fytd_pcp"], "label": L["fytd"]}
    return out


def _labels(per: dict) -> dict:
    a = date.fromisoformat(str(per["month_start"])[:10])
    pm, py = Period("month", a), Period("fytd", a)
    meeting = per.get("board_meeting")
    meeting = meeting if meeting and str(meeting)[:10] > str(per["period_end"])[:10] else None
    return {"code": per["period_code"], "fy_code": per["fy_code"], "label": per["label"], "state": per["state"],
            "state_label": STATE_LABEL.get(per["state"], per["state"]), "month_start": str(per["month_start"])[:10],
            "period_end": str(per["period_end"])[:10], "board_meeting": str(meeting)[:10] if meeting else None,
            "anchor": f"{a:%Y-%m}", "month": pm.label, "month_pcp": pm.pcp().label,
            "month_long": f"{FULL_MON[a.month - 1]} {a.year}", "fy": py.fy_short, "fytd": f"{py.fy_short} YTD",
            "fytd_pcp": f"{py.pcp().fy_short} YTD", "fytd_long": py.label, "fytd_pcp_long": py.pcp().label,
            "insights_key": pm.month_key, "month_end_label": _day(per["period_end"])}


def _slide_title(title: str, L: dict) -> str:
    return title.replace("{fy}", L.get("fy_code") or L.get("fy") or "")


# ------------------------------------------------------------------------------------------------ periods
def _period(cur, code: str) -> dict:
    cur.execute("SELECT * FROM scorecard.reporting_period WHERE period_code = %s", (code,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(404, f"unknown board reporting period {code}")
    return _rows([r])[0]


def _latest_closed(token: str | None = None) -> date:
    try:
        return insights._default_anchor(token)      # latest month with finance actuals, queried as the viewer
    except Exception:  # noqa: BLE001
        return date.today().replace(day=1)


def _default_code(cur, latest: date) -> str | None:
    """Latest board period with KPI updates whose month has closed (finance actuals posted)."""
    for q, p in (("""SELECT p.period_code FROM scorecard.reporting_period p WHERE p.month_start <= %s
                     AND EXISTS (SELECT 1 FROM scorecard.kpi_status_update u WHERE u.period_code = p.period_code)
                     ORDER BY p.month_start DESC LIMIT 1""", (latest,)),
                 ("""SELECT p.period_code FROM scorecard.reporting_period p
                     WHERE EXISTS (SELECT 1 FROM scorecard.kpi_status_update u WHERE u.period_code = p.period_code)
                     ORDER BY p.month_start DESC LIMIT 1""", None),
                 ("SELECT period_code FROM scorecard.reporting_period ORDER BY month_start DESC LIMIT 1", None)):
        cur.execute(q, p)
        r = cur.fetchone()
        if r:
            return r["period_code"]
    return None


@router.get("/periods")
def periods(u: auth.User = Depends(me_dep)):
    latest = _latest_closed(u.token)
    with db.tx(u.email, u.role) as cur:
        cur.execute("""
            SELECT p.period_code, p.fy_code, p.label, p.month_start, p.state,
                   EXISTS (SELECT 1 FROM scorecard.kpi_status_update s WHERE s.period_code = p.period_code) AS has_updates,
                   b.version, b.status AS pack_status, b.finalised_at, b.sent_at
            FROM scorecard.reporting_period p
            LEFT JOIN LATERAL (SELECT version, status, finalised_at, sent_at FROM scorecard.board_pack x
                               WHERE x.period_code = p.period_code ORDER BY version DESC LIMIT 1) b ON true
            ORDER BY p.month_start DESC""")
        rows = _rows(cur.fetchall())
        default = _default_code(cur, latest)
    return {"default": default, "periods": [r for r in rows if r["has_updates"] or r["version"]]}


# ------------------------------------------------------------------------------------------------ slide workflow state
def _settings(cur, code: str) -> dict[str, dict]:
    cur.execute("SELECT slide_key, included, owner, updated_by, updated_at FROM scorecard.board_pack_slide "
                "WHERE period_code = %s", (code,))
    return {r["slide_key"]: r for r in _rows(cur.fetchall())}


def _commentary_state(cur, code: str) -> dict[str, dict]:
    """Workflow status of every slide's commentary (status only – the text follows the commentary visibility rules)."""
    cur.execute("""SELECT subject, status, updated_at, submitted_at, reviewed_at FROM scorecard.commentary
                   WHERE scope = 'boardpack' AND period_key = %s""", (code,))
    return {r["subject"]: r for r in _rows(cur.fetchall())}


def _approved(cur, code: str) -> dict[str, dict]:
    cur.execute("""SELECT subject, body, author_name, author_role, reviewer_name, reviewed_at, ai_assisted, version
                   FROM scorecard.commentary WHERE scope = 'boardpack' AND period_key = %s AND status = 'APPROVED'""",
                (code,))
    return {r.pop("subject"): r for r in _rows(cur.fetchall())}


def _slide_status(c: dict | None) -> str:
    if not c:
        return "NOT_STARTED"
    return "READY" if c["status"] == "APPROVED" else "IN_DRAFT"


def _slides(L: dict, settings: dict, cstate: dict, show_workflow: bool) -> list[dict]:
    out = []
    for i, (key, title, short, kind, owner, ctitle, prompt) in enumerate(SLIDES):
        st, c = settings.get(key, {}), cstate.get(key)
        out.append({"key": key, "no": i + 1, "title": _slide_title(title, L), "short": short, "kind": kind,
                    "owner": st.get("owner") or owner, "default_owner": owner, "commentary_title": ctitle,
                    "prompt": prompt, "required": key in REQUIRED,
                    "included": True if key in REQUIRED else st.get("included", True),
                    "status": _slide_status(c) if show_workflow else None,
                    "commentary_status": (c or {}).get("status") if show_workflow else None,
                    "updated_at": (c or {}).get("updated_at") if show_workflow else None})
    return out


def _readiness(slides: list[dict]) -> dict:
    inc = [s for s in slides if s["included"]]
    ready = [s for s in inc if s["status"] == "READY"]
    return {"ready": len(ready), "total": len(inc), "excluded": len(slides) - len(inc),
            "not_ready": [{"key": s["key"], "title": s["title"], "status": s["status"]}
                          for s in inc if s["status"] != "READY"]}


def _versions(cur, code: str) -> list[dict]:
    cur.execute(f"SELECT {_VERSION_COLS} FROM scorecard.board_pack WHERE period_code = %s ORDER BY version DESC", (code,))
    return _rows(cur.fetchall())


def _activity(cur, code: str) -> list[dict]:
    cur.execute("""
        SELECT a.id, a.at, a.action, a.entity, coalesce(r.display_name, a.actor_email) AS actor,
               coalesce(a.after, a.before) ->> 'subject' AS subject, coalesce(a.after, a.before) ->> 'slide_key' AS slide_key,
               a.after ->> 'status' AS status, a.before ->> 'status' AS before_status,
               a.after ->> 'included' AS included, a.before ->> 'included' AS before_included,
               a.after ->> 'owner' AS owner, a.before ->> 'owner' AS before_owner,
               coalesce(a.after, a.before) ->> 'version' AS version
        FROM scorecard.audit_log a LEFT JOIN scorecard.app_user_role r ON r.email = a.actor_email
        WHERE (a.entity = 'board_pack_slide' AND a.entity_id LIKE %(like)s)
           OR (a.entity = 'board_pack' AND coalesce(a.after, a.before) ->> 'period_code' = %(p)s)
           OR (a.entity = 'commentary' AND coalesce(a.after, a.before) ->> 'scope' = 'boardpack'
               AND coalesce(a.after, a.before) ->> 'period_key' = %(p)s)
        ORDER BY a.id DESC LIMIT 40""", {"p": code, "like": f"{code}:%"})
    titles = {s[0]: s[1].replace("{fy} ", "") for s in SLIDES}
    out = []
    for r in _rows(cur.fetchall()):
        what = None
        if r["entity"] == "board_pack":
            if r["action"] == "INSERT":
                what = f"Finalised version {r['version']} and generated the PDF"
            elif r["status"] == "SENT" and r["before_status"] != "SENT":
                what = f"Marked version {r['version']} as sent to the Board"
            elif r["status"] == "SUPERSEDED" and r["before_status"] != "SUPERSEDED":
                what = f"Version {r['version']} superseded"
        elif r["entity"] == "board_pack_slide":
            t = titles.get(r["slide_key"], r["slide_key"])
            if r["included"] != r["before_included"]:
                what = f"{'Included' if r['included'] == 'true' else 'Excluded'} “{t}” {'in' if r['included'] == 'true' else 'from'} the pack"
            elif r["owner"] != r["before_owner"]:
                what = f"Set the owner of “{t}” to {r['owner']}" if r["owner"] else f"Reset the owner of “{t}”"
        else:
            t = titles.get(r["subject"], r["subject"])
            if r["action"] == "INSERT" or (r["status"] == "DRAFT" and r["before_status"] != "DRAFT"):
                what = f"Started commentary for “{t}”"
            elif r["status"] == "SUBMITTED" and r["before_status"] != "SUBMITTED":
                what = f"Submitted “{t}” for review"
            elif r["status"] == "APPROVED" and r["before_status"] != "APPROVED":
                what = f"Approved “{t}”"
            elif r["status"] == "RETURNED" and r["before_status"] != "RETURNED":
                what = f"Returned “{t}” with a note"
            elif r["status"] == "DRAFT":
                what = f"Edited commentary for “{t}”"
        if what:
            out.append({"at": r["at"], "actor": r["actor"], "what": what})
    return out[:25]


def _perms(u: auth.User) -> dict:
    curator = u.role in CURATORS or u.role == "ADMIN"
    return {"can_curate": curator, "can_finalise": curator, "can_mark_sent": curator,
            "can_download": u.role in DOWNLOADERS or u.role == "ADMIN", "sees_workflow": u.role in SEES_WORKFLOW,
            "can_write": u.role in commentary.WRITERS or u.role == "ADMIN",
            "can_review": u.role in commentary.REVIEWERS or u.role == "ADMIN"}


_VERSION_COLS = ("board_pack_id, version, status, slides_included, slides_ready, slides_total, not_ready, override_reason, "
                 "finalised_by, finalised_name, finalised_role, finalised_at, sent_by, sent_name, sent_at, superseded_at, "
                 "pdf_bytes, pdf_pages")


def _state(cur, code: str) -> tuple[dict, dict, dict, list]:
    """Period, slide settings, commentary workflow state and versions in one round trip."""
    cur.execute(f"""
        SELECT (SELECT to_jsonb(p) FROM scorecard.reporting_period p WHERE p.period_code = %(p)s) AS period,
               (SELECT coalesce(jsonb_agg(to_jsonb(s)), '[]'::jsonb) FROM (
                  SELECT slide_key, included, owner, updated_by, updated_at FROM scorecard.board_pack_slide
                  WHERE period_code = %(p)s) s) AS settings,
               (SELECT coalesce(jsonb_agg(to_jsonb(c)), '[]'::jsonb) FROM (
                  SELECT subject, status, updated_at, submitted_at, reviewed_at FROM scorecard.commentary
                  WHERE scope = 'boardpack' AND period_key = %(p)s) c) AS cstate,
               (SELECT coalesce(jsonb_agg(to_jsonb(v) ORDER BY v.version DESC), '[]'::jsonb) FROM (
                  SELECT {_VERSION_COLS} FROM scorecard.board_pack WHERE period_code = %(p)s) v) AS versions""", {"p": code})
    r = cur.fetchone()
    if not r or not r["period"]:
        raise HTTPException(404, f"unknown board reporting period {code}")
    return (r["period"], {x["slide_key"]: x for x in r["settings"]}, {x["subject"]: x for x in r["cstate"]},
            r["versions"])


def _meta(u: auth.User, code: str) -> dict:
    perms = _perms(u)
    with db.tx(u.email, u.role) as cur:
        per, settings, cstate, versions = _state(cur, code)
        activity = _activity(cur, code) if perms["can_curate"] else []
        # Readers (Board, observers) get approved text only, whoever wrote it – also when an admin previews the Board view
        approved = None if perms["sees_workflow"] else _approved(cur, code)
    L = _labels(per)
    slides = _slides(L, settings, cstate, perms["sees_workflow"])
    return {"period": L, "role": u.role, "perms": perms, "slides": slides,
            "readiness": _readiness(slides) if perms["sees_workflow"] else None,
            "versions": versions, "latest": versions[0] if versions else None, "activity": activity,
            "approved": approved, "_row": per}


@router.get("/{code}")
def pack(code: str, u: auth.User = Depends(me_dep)):
    m = _meta(u, code)
    m.pop("_row")
    return m


# ------------------------------------------------------------------------------------------------ live slide data
def _run(token, items: dict[str, tuple[str, dict]]) -> dict:
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {k: ex.submit(sql.safe, token, q, p) for k, (q, p) in items.items()}
        return {k: f.result() for k, f in futs.items()}


def _intel_window(anchor: date) -> tuple[date, date]:
    """The four weeks to when the pack is prepared: up to the end of the following month, never past today."""
    end = min(date.today(), month_end(month_add(anchor, 1)))
    return end - timedelta(days=27), end


def _extra_sql(pm: Period, py: Period, win: tuple[date, date]) -> dict[str, tuple[str, dict]]:
    fin, vd, io = sql.fq("v_finance_monthly"), sql.fq("v_vic_gas_demand_daily"), sql.fq("v_iona_operations_daily")
    p = {"s": pm.start.isoformat(), "e": pm.end.isoformat(), "ps": pm.pcp().start.isoformat(),
         "pe": pm.pcp().end.isoformat(), "ys": py.start.isoformat(), "pys": py.pcp().start.isoformat(), "fy": py.fy}

    def rng(col, agg, a, b, name):
        return f"{agg}(CASE WHEN {col[0]} BETWEEN DATE(:{a}) AND DATE(:{b}) THEN {col[1]} END) AS {name}"

    def four(col, agg, name):              # month, month a year earlier, FY to date, FY to date a year earlier
        return ",\n".join(rng(col, agg, a, b, n) for a, b, n in
                          (("s", "e", f"{name}_m"), ("ps", "pe", f"{name}_m_pcp"), ("ys", "e", f"{name}_y"),
                           ("pys", "pe", f"{name}_y_pcp")))

    ws, we = win
    intel = {"ws": (ws - timedelta(days=6)).isoformat(), "we": we.isoformat(), "is": ws.isoformat()}
    return {
        "hugs": (f"""
            SELECT {four(('month_start', 'actual_amount'), 'SUM', 'actual')},
                   {rng(('month_start', 'budget_amount'), 'SUM', 's', 'e', 'budget_m')},
                   {rng(('month_start', 'budget_amount'), 'SUM', 'ys', 'e', 'budget_y')},
                   SUM(CASE WHEN month_start <= DATE(:e) THEN actual_amount END) AS to_date,
                   SUM(CASE WHEN month_start <= DATE(:pe) THEN actual_amount END) AS to_date_pcp,
                   SUM(CASE WHEN financial_year = :fy THEN budget_amount END) AS fy_budget,
                   SUM(CASE WHEN financial_year = :fy THEN yeo_amount END) AS fy_yeo,
                   SUM(CASE WHEN financial_year < :fy THEN actual_amount ELSE 0 END)
                     + SUM(CASE WHEN financial_year = :fy THEN yeo_amount ELSE 0 END) AS eac,
                   SUM(committed_amount) AS committed
            FROM {fin} WHERE cc_short_name = 'HUGS'""", p),
        "hugs_chart": (f"""
            WITH m AS (SELECT month_start, SUM(actual_amount) AS a FROM {fin}
                       WHERE cc_short_name = 'HUGS' AND month_start <= DATE(:e) GROUP BY ALL)
            SELECT month_start AS x, SUM(a) OVER (ORDER BY month_start) AS y FROM m ORDER BY x""", p),
        "fin_teams": (f"""
            SELECT team, {rng(('month_start', 'actual_amount'), 'SUM', 'ys', 'e', 'actual')},
                   {rng(('month_start', 'budget_amount'), 'SUM', 'ys', 'e', 'budget')},
                   SUM(budget_amount) AS fy_budget, SUM(yeo_amount) AS fy_yeo
            FROM {fin} WHERE financial_year = :fy GROUP BY team ORDER BY fy_budget DESC LIMIT 7""", p),
        "market": (f"""
            SELECT {four(('gas_date', 'total_gas_used_tj'), 'MAX', 'peak')},
                   {four(('gas_date', 'edd_value'), 'AVG', 'edd')},
                   max(gas_date) AS data_to
            FROM {vd} WHERE gas_date BETWEEN DATE(:pys) AND DATE(:e)""", p),
        "ops": (f"""
            SELECT {four(('gas_date', 'withdrawal_tj / 1000'), 'SUM', 'wd')},
                   {four(('gas_date', 'injection_tj / 1000'), 'SUM', 'inj')},
                   {four(('gas_date', 'compressor_availability'), 'AVG', 'ca')}
            FROM {io} WHERE gas_date BETWEEN DATE(:pys) AND DATE(:e)""", p),
        "intel_briefs": (f"""
            SELECT week_start, week_end, headline, summary_md, n_items, n_sources
            FROM {sql.fq('v_market_intel_briefs')} WHERE week_start BETWEEN DATE(:ws) AND DATE(:we)
            ORDER BY week_start DESC LIMIT 4""", intel),
        "intel_items": (f"""
            SELECT title, source_name, published_date, url, summary, why_it_matters, entity_group, topic, signal,
                   importance
            FROM {sql.fq('v_market_intel_items')} WHERE published_date BETWEEN DATE(:is) AND DATE(:we)
            ORDER BY importance DESC, published_at DESC LIMIT 6""", intel),
        "intel_signals": (f"""
            SELECT signal, COUNT(*) AS n FROM {sql.fq('v_market_intel_items')}
            WHERE published_date BETWEEN DATE(:is) AND DATE(:we) GROUP BY signal""", intel),
    }


def _intel_fixture(win: tuple[date, date]) -> dict:
    """Development only (LOCHARD_MARKET_FIXTURE=1, as for the Market Intelligence Hub): the same view shapes from
    server/fixtures/market_sample.json while the market views are being built."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "market_sample.json")
    try:
        with open(path) as f:
            fx = json.load(f)
    except (OSError, ValueError):
        return {}
    ws, we = win
    lo, hi, lo_b = ws.isoformat(), we.isoformat(), (ws - timedelta(days=6)).isoformat()
    briefs = sorted((b for b in fx.get("briefs", []) if lo_b <= str(b["week_start"])[:10] <= hi),
                    key=lambda b: b["week_start"], reverse=True)[:4]
    items = [i for i in fx.get("items", []) if lo <= str(i.get("published_date"))[:10] <= hi]
    top = sorted(items, key=lambda i: (i.get("importance") or 0, str(i.get("published_at"))), reverse=True)[:6]
    counts: dict[str, int] = {}
    for i in items:
        counts[i.get("signal")] = counts.get(i.get("signal"), 0) + 1
    return {"intel_briefs": {"rows": briefs}, "intel_items": {"rows": top},
            "intel_signals": {"rows": [{"signal": k, "n": v} for k, v in counts.items() if k]}}


def _safe_scorecard(u: auth.User, per: dict) -> dict | None:
    try:
        return load_scorecard(u, per["fy_code"], per["period_code"])
    except Exception as e:  # noqa: BLE001
        log.warning("scorecard for board pack failed: %s", e)
        return None


def _approved_insights(u: auth.User, key: str) -> list[dict]:
    try:
        items = commentary.fetch(u, "insights", key)
    except Exception as e:  # noqa: BLE001
        log.warning("insights commentary for board pack failed: %s", e)
        return []
    order = list(INSIGHTS_TITLES)
    out = [{"subject": s, "title": INSIGHTS_TITLES.get(s, s.replace("_", " ").title()), "body": r["body"],
            "author_name": r.get("author_name"), "reviewer_name": r.get("reviewer_name"),
            "reviewed_at": r.get("reviewed_at")}
           for s, r in items.items() if r.get("status") == "APPROVED"]
    return sorted(out, key=lambda r: order.index(r["subject"]) if r["subject"] in order else 99)


def _build(u: auth.User, per: dict) -> dict:
    L = _labels(per)
    anchor = date.fromisoformat(L["month_start"])
    pm, py = Period("month", anchor), Period("fytd", anchor)
    win = _intel_window(anchor)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=6) as ex:
        f_m = ex.submit(insights.domain_summary, u.token, pm)
        f_y = ex.submit(insights.domain_summary, u.token, py)
        f_t = ex.submit(insights.domain_trends, u.token, py)
        f_x = ex.submit(_run, u.token, _extra_sql(pm, py, win))
        f_sc = ex.submit(_safe_scorecard, u, per)
        f_ins = ex.submit(_approved_insights, u, L["insights_key"])
        sm, sy, tr, x, sc, ins = f_m.result(), f_y.result(), f_t.result(), f_x.result(), f_sc.result(), f_ins.result()
    if os.environ.get("LOCHARD_MARKET_FIXTURE") == "1" and x.get("intel_briefs", {}).get("error"):
        x.update(_intel_fixture(win))
    log.info("board pack data for %s built in %.1fs", per["period_code"], time.time() - t0)
    errors = {**{f"m.{k}": v for k, v in sm.get("errors", {}).items()},
              **{f"y.{k}": v for k, v in sy.get("errors", {}).items()},
              **{f"t.{k}": v["error"] for k, v in tr.items() if isinstance(v, dict) and v.get("error")},
              **{f"x.{k}": v["error"] for k, v in x.items() if v.get("error") and not k.startswith("intel")}}
    for k, v in errors.items():
        log.warning("board pack %s: %s failed: %s", per["period_code"], k, str(v)[:200])
    raw = {"m": sm["tiles"], "y": sy["tiles"], "x": {k: (v["rows"][0] if v["rows"] else {}) for k, v in x.items()
                                                      if k in ("hugs", "market", "ops")}}
    slides = _assemble(L, sm["tiles"], sy["tiles"], tr, x, sc, ins, win)
    partial = {"hse": ("m.hse", "y.hse", "t.hse"), "operations": ("m.operations", "y.operations", "x.ops", "t.operations"),
               "market": ("m.operations", "x.market", "t.market"), "maintenance": ("m.maintenance", "t.maintenance"),
               "finance": ("m.finance", "y.finance", "t.finance", "x.fin_teams"), "hugs": ("x.hugs", "x.hugs_chart")}
    for key, deps in partial.items():
        slides[key]["partial"] = any(d in errors for d in deps)
    return {"public": {"period": L, "generated_at": datetime.now(timezone.utc).isoformat(), "slides": slides},
            "raw": raw, "scorecard": sc}


def _chart(title, sub, kind, x, y, rows, colors, dashed=None, zero=True, area=False) -> dict:
    return {"title": title, "sub": sub, "kind": kind, "x": x, "y": y, "rows": rows or [], "colors": colors,
            "dashed": dashed or [], "zero": zero, "area": area}


def _assemble(L, m, y, tr, x, sc, ins, win) -> dict:
    g = lambda d, k: (d or {}).get(k)  # noqa: E731
    X = {k: (v["rows"][0] if v["rows"] else {}) for k, v in x.items() if k in ("hugs", "market", "ops")}
    T = lambda k: (tr.get(k) or {}).get("rows") or []  # noqa: E731
    mh, yh, mo, yo = m.get("hse", {}), y.get("hse", {}), m.get("operations", {}), y.get("operations", {})
    mm, ym, mf, yf = m.get("maintenance", {}), y.get("maintenance", {}), m.get("finance", {}), y.get("finance", {})
    ox, mx, hx = X.get("ops", {}), X.get("market", {}), X.get("hugs", {})
    S: dict[str, dict] = {}

    # --- safety
    S["hse"] = {
        "metrics": [
            metric(L, "Incident observations", "count", g(mh, "obs"), g(mh, "obs_pcp"), g(yh, "obs"), g(yh, "obs_pcp"),
                   note="reported in the period"),
            metric(L, "HIGH actual-risk incidents", "count", g(mh, "high"), g(mh, "high_pcp"), g(yh, "high"),
                   g(yh, "high_pcp"), better="lower"),
            metric(L, "High potential events", "count", g(mh, "hpe"), g(mh, "hpe_pcp"), g(yh, "hpe"), g(yh, "hpe_pcp"),
                   better="lower", note="target: nil"),
            metric(L, "TRIFR (rolling 12 months)", "rate", g(mh, "trifr"), g(mh, "trifr_pcp"), point=True,
                   better="lower", note="recordable injuries per million hours worked"),
            metric(L, "Open incident observations", "count", g(mh, "open_now"), point=True, vs="",
                   note=f"open today · {fv(g(mh, 'open_high_now'), 'count')} rated HIGH"),
            metric(L, "Open investigations", "count", g(mh, "open_investigations"), point=True, vs="", note="open today"),
        ],
        "chart": _chart("Incident observations reported", f"per month, 12 months to {L['month']}", "bar", "month",
                        "count", T("hse"), {"Observations": CRIMSON}),
    }

    # --- Iona operations
    fill = _num(g(mo, "fill_pct"))
    S["operations"] = {
        "metrics": [
            metric(L, "Iona inventory", "pj", g(mo, "inventory_pj"), g(mo, "inventory_pcp"), point=True,
                   note=(f"{fill * 100:.0f}% full · " if fill is not None else "") + f"at {_day(g(mo, 'as_of'))}"),
            metric(L, "Withdrawals", "pj", g(ox, "wd_m"), g(ox, "wd_m_pcp"), g(ox, "wd_y"), g(ox, "wd_y_pcp")),
            metric(L, "Injections", "pj", g(ox, "inj_m"), g(ox, "inj_m_pcp"), g(ox, "inj_y"), g(ox, "inj_y_pcp")),
            metric(L, "Nominations delivered within ±4%", "pct", g(mo, "noms_within_tol"), g(mo, "noms_within_tol_pcp"),
                   g(yo, "noms_within_tol"), g(yo, "noms_within_tol_pcp"), better="higher"),
            metric(L, "Compressor availability", "pct", g(ox, "ca_m"), g(ox, "ca_m_pcp"), g(ox, "ca_y"),
                   g(ox, "ca_y_pcp"), better="higher"),
        ],
        "chart": _chart("Iona storage inventory", f"PJ, weekly average, 12 months to {L['month']}", "line", "week",
                        "pj", [{**r, "series": "Inventory"} for r in T("operations")], {"Inventory": SKY}, zero=False,
                        area=True),
    }

    # --- gas market & demand
    share_m = _div(g(ox, "wd_m"), g(mo, "vic_demand_pj"))
    share_mp = _div(g(ox, "wd_m_pcp"), g(mo, "vic_demand_pcp_pj"))
    share_y = _div(g(ox, "wd_y"), g(yo, "vic_demand_pj"))
    share_yp = _div(g(ox, "wd_y_pcp"), g(yo, "vic_demand_pcp_pj"))
    S["market"] = {
        "metrics": [
            metric(L, "Victorian gas demand", "pj", g(mo, "vic_demand_pj"), g(mo, "vic_demand_pcp_pj"),
                   g(yo, "vic_demand_pj"), g(yo, "vic_demand_pcp_pj")),
            metric(L, "Peak day demand", "tj", g(mx, "peak_m"), g(mx, "peak_m_pcp"), g(mx, "peak_y"), g(mx, "peak_y_pcp")),
            metric(L, "Average effective degree days", "num", g(mx, "edd_m"), g(mx, "edd_m_pcp"), g(mx, "edd_y"),
                   g(mx, "edd_y_pcp"), note="higher = colder weather, more heating demand"),
            metric(L, "Iona withdrawals as share of demand", "pct", share_m, share_mp, share_y, share_yp),
        ],
        "chart": _chart("Victorian gas demand", f"PJ per month, 12 months to {L['month']} vs a year earlier", "line",
                        "month", "pj", T("market"), {"This year": ORANGE, "Prior year": GREY}, dashed=["Prior year"],
                        zero=False),
    }

    # --- maintenance
    latest_week = g(mm, "compliance_latest")
    comp_note = None
    if g(mm, "compliance") is None and latest_week is not None:
        comp_note = f"no weeks closed in {L['month']} yet · latest week {fv(latest_week, 'pct')} (w/c {_day(g(mm, 'compliance_latest_week'))})"
    snap = f"as at {_day(g(mm, 'snapshot_date'))}" if g(mm, "snapshot_date") else None
    S["maintenance"] = {
        "metrics": [
            metric(L, "Schedule compliance", "pct", g(mm, "compliance"), g(mm, "compliance_pcp"), g(ym, "compliance"),
                   g(ym, "compliance_pcp"), better="higher", note=comp_note or "completed ÷ scheduled work orders"),
            metric(L, "Overdue safety-critical work orders", "count", g(mm, "overdue_sc"), g(mm, "overdue_sc_pcp"),
                   point=True, better="lower", note=snap),
            metric(L, "Backlog excl. preventive maintenance", "count", g(mm, "backlog_ex_pm"),
                   g(mm, "backlog_ex_pm_pcp"), point=True, better="lower", note=snap),
            metric(L, "Open P2 work orders excl. PMs", "count", g(mm, "open_p2"), g(mm, "open_p2_pcp"), point=True,
                   better="lower", note=snap),
        ],
        "chart": _chart("Schedule compliance", f"completed ÷ scheduled work orders, 13 weeks to {L['month']}", "line",
                        "week", "pct", [{**r, "series": "Compliance"} for r in T("maintenance")],
                        {"Compliance": ORANGE}, zero=False, area=True),
    }

    # --- finance
    var_m, var_y = _sub(g(mf, "actuals"), g(mf, "budget")), _sub(g(yf, "actuals"), g(yf, "budget"))
    yeo_pct = _div(g(yf, "yeo_fy"), g(yf, "budget_fy"))
    teams = []
    for r in (x.get("fin_teams") or {}).get("rows") or []:
        v = _sub(r.get("actual"), r.get("budget"))
        teams.append({"team": r["team"], "actual": fv(r.get("actual"), "money"), "budget": fv(r.get("budget"), "money"),
                      "variance": fv(v, "money") if v is None or v <= 0 else "+" + fv(v, "money"),
                      "tone": None if v is None or abs(v) < 1 else "good" if v < 0 else "bad",
                      "fy_budget": fv(r.get("fy_budget"), "money"), "fy_yeo": fv(r.get("fy_yeo"), "money")})
    S["finance"] = {
        "metrics": [
            metric(L, "Actual expenditure", "money", g(mf, "actuals"), g(mf, "actuals_pcp"), g(yf, "actuals"),
                   g(yf, "actuals_pcp")),
            metric(L, "Budget", "money", g(mf, "budget"), None, g(yf, "budget"), None, note="same months"),
            metric(L, "Variance to budget", "money", var_m, None, var_y, None, note="negative = under budget",
                   tone=None if var_y is None else "good" if var_y <= 0 else "bad"),
            metric(L, f"{L['fy']} full-year budget", "money", g(yf, "budget_fy"), point=True, vs=""),
            metric(L, "Year-end outlook", "money", g(yf, "yeo_fy"), point=True, vs="",
                   note=f"{yeo_pct * 100:.0f}% of full-year budget" if yeo_pct is not None else None),
            metric(L, "Open commitments", "money", g(yf, "committed"), point=True, vs="", note="open purchase orders"),
        ],
        "chart": _chart("Cumulative budget, outlook and actuals", f"{L['fy']} by month", "line", "cat", "money",
                        T("finance"), {"Budget": SKY, "YEO": ORANGE, "Actuals": GREY}, dashed=["Budget"]),
        "table": {"title": f"{L['fytd']} by team (largest budgets)", "rows": teams},
    }

    # --- HUGS
    p50 = insights.HUGS_P50
    eac = _num(g(hx, "eac"))
    over = _sub(eac, p50)
    kpi = next((k for p in (sc or {}).get("pillars", []) for k in p["kpis"] if k["code"] == "2.1"), None)
    cum = [r for r in ((x.get("hugs_chart") or {}).get("rows") or []) if _num(r.get("y"))]
    hugs_rows = [{"x": r["x"], "series": "Spend to date", "y": r["y"]} for r in cum]
    for s_name, val in (("Revised P50", p50), ("Estimate at completion", eac)):
        if val is not None:
            hugs_rows += [{"x": r["x"], "series": s_name, "y": val} for r in cum]
    S["hugs"] = {
        "metrics": [
            metric(L, "Estimate at completion", "money", eac, p50, point=True, better="lower", vs="revised P50",
                   note=f"revised P50 budget {fv(p50, 'money')}"),
            metric(L, "Spend to date", "money", g(hx, "to_date"), g(hx, "to_date_pcp"), point=True,
                   note=f"all years, to {L['month_end_label']}"),
            metric(L, "Project spend", "money", g(hx, "actual_m"), g(hx, "actual_m_pcp"), g(hx, "actual_y"),
                   g(hx, "actual_y_pcp")),
            metric(L, "Project budget", "money", g(hx, "budget_m"), None, g(hx, "budget_y"), None, note="same months"),
            metric(L, f"{L['fy']} year-end outlook", "money", g(hx, "fy_yeo"), g(hx, "fy_budget"), point=True,
                   vs=f"{L['fy']} budget", better="lower"),
            metric(L, "Open commitments", "money", g(hx, "committed"), point=True, vs=""),
        ],
        "eac": {"eac": fv(eac, "money"), "p50": fv(p50, "money"),
                "variance": None if over is None else ("+" if over > 0 else "") + fv(over, "money"),
                "over": bool(over and over > 0),
                "pct_of_p50": None if eac is None else f"{eac / p50 * 100:.1f}%"},
        "kpi": {"code": kpi["code"], "name": kpi["name"], "status": kpi.get("status"),
                "status_label": KPI_STATUS.get(kpi.get("status") or "", "Not reported"),
                "update": kpi.get("commentary")} if kpi else None,
        "chart": _chart("HUGS spend to date against the revised P50", f"cumulative, to {L['month']}", "line", "month",
                        "money", hugs_rows, {"Spend to date": GREY, "Revised P50": CRIMSON,
                                             "Estimate at completion": ORANGE},
                        dashed=["Revised P50", "Estimate at completion"]),
    }

    # --- scorecard
    if sc:
        summ = sc.get("summary") or {}
        kpis = [k for p in sc["pillars"] for k in p["kpis"]]
        S["scorecard"] = {
            "available": True, "state": sc["period"]["state"], "state_label": STATE_LABEL.get(sc["period"]["state"]),
            "summary": {"status_index": None if summ.get("status_index_pct") is None else f"{summ['status_index_pct']:.1f}%",
                        "board_score": None if summ.get("weighted_board_score_pct") is None
                        else f"{summ['weighted_board_score_pct']:.1f}%",
                        "at_risk": int(summ.get("kpis_at_risk") or 0), "off_track": int(summ.get("kpis_off_track") or 0),
                        "kpis": len(kpis),
                        "reported": sum(1 for k in kpis if k.get("status"))},
            "pillars": [{"name": p["name"], "kpis": [{
                "code": k["code"], "name": k["name"], "owner": k["owner_initials"], "weight": f"{k['weight_pct']:.0f}%",
                "status": k.get("status"), "status_label": KPI_STATUS.get(k.get("status") or "", "Not reported"),
                "board": None if k.get("avg_board_score") is None else f"{k['avg_board_score']:.1f}/5",
                "update": k.get("commentary")} for k in p["kpis"]]} for p in sc["pillars"]],
            "footnote": sc.get("footnote"),
        }
    else:
        S["scorecard"] = {"available": False, "pillars": [], "summary": {}}

    # --- market intelligence
    ws, we = win
    b, it, sg = x.get("intel_briefs") or {}, x.get("intel_items") or {}, x.get("intel_signals") or {}
    S["market_intel"] = {
        "available": not b.get("error"),
        "window": {"start": ws.isoformat(), "end": we.isoformat(), "label": f"Four weeks to {_day(we)}"},
        "briefs": [{"week_start": r["week_start"], "week_end": r.get("week_end"),
                    "week_label": f"Week of {_day(r['week_start'])}", "headline": r.get("headline"),
                    "summary": r.get("summary_md"), "n_items": r.get("n_items"), "n_sources": r.get("n_sources")}
                   for r in b.get("rows") or []],
        "items": [{"title": r.get("title"), "source": r.get("source_name"), "date": _day(r.get("published_date")),
                   "url": r.get("url"), "summary": r.get("summary"), "why": r.get("why_it_matters"),
                   "signal": r.get("signal"), "group": r.get("entity_group"), "importance": r.get("importance")}
                  for r in (it.get("rows") or []) if not it.get("error")],
        "signals": {r["signal"]: int(r["n"]) for r in (sg.get("rows") or []) if r.get("signal")},
    }

    # --- executive summary (headline numbers across the pack + scorecard + approved Leadership Insights commentary)
    def head(slide, idx, use="m", label=None, slide_key=None):
        mt = S[slide]["metrics"][idx]
        part = mt["m"] if use == "m" or mt["y"] is None else mt["y"]
        sub = f"{part['d']['text']} vs {part['vs']}" if part.get("d") else (mt.get("note") or "")
        return {"label": label or mt["label"], "value": part["t"], "sub": sub,
                "tone": (part.get("d") or {}).get("tone") or mt.get("tone"), "slide": slide_key or slide,
                "period": part.get("label")}

    ex_heads = [
        head("hse", 3, label="TRIFR (rolling 12 months)"),
        head("hse", 2, "y", label=f"High potential events {L['fytd']}"),
        head("operations", 0),
        head("operations", 3, "y", label=f"Nominations within ±4% {L['fytd']}"),
        head("market", 0, "y", label=f"Victorian gas demand {L['fytd']}"),
        head("maintenance", 1),
        {"label": f"Expenditure {L['fytd']} vs budget", "value": fv(g(yf, "actuals"), "money"),
         "sub": (f"budget {fv(g(yf, 'budget'), 'money')} · "
                 f"{'under' if (var_y or 0) <= 0 else 'over'} by {fv(abs(var_y), 'money')}") if var_y is not None else "",
         "tone": S["finance"]["metrics"][2]["tone"], "slide": "finance", "period": L["fytd"]},
        {"label": "HUGS estimate at completion", "value": fv(eac, "money"),
         "sub": f"{S['hugs']['eac']['variance']} vs revised P50 {fv(p50, 'money')}" if over is not None else "",
         "tone": "bad" if over and over > 0 else "good" if over is not None else None, "slide": "hugs", "period": "Now"},
    ]
    sc_s = S["scorecard"]
    attention = [{"code": k["code"], "name": k["name"], "status": k["status"], "status_label": k["status_label"]}
                 for p in sc_s.get("pillars", []) for k in p["kpis"] if k["status"] in ("AT_RISK", "OFF_TRACK", None)]
    S["exec_summary"] = {"headlines": ex_heads, "scorecard": sc_s.get("summary") or {},
                         "scorecard_state": sc_s.get("state_label"), "attention": attention,
                         "domain_commentary": ins}

    # --- cover
    S["cover"] = {"month_long": L["month_long"], "board_meeting": L["board_meeting"], "fy": L["fy"],
                  "state_label": L["state_label"]}

    # --- owner-prepared slides: signals from the pack to help the owner (not printed)
    risks = [f"KPI {a['code']} {a['name']} is {a['status_label']}" for a in attention if a["status"]]
    if over is not None and over > 0:
        risks.append(f"HUGS estimate at completion {fv(eac, 'money')} is {fv(over, 'money')} above the revised P50 "
                     f"{fv(p50, 'money')}")
    if _num(g(mh, "open_high_now")):
        risks.append(f"{fv(g(mh, 'open_high_now'), 'count')} HIGH-risk incident observations are open")
    if _num(g(mm, "overdue_sc")):
        risks.append(f"{fv(g(mm, 'overdue_sc'), 'count')} safety-critical work orders are overdue ({snap})")
    if S["market_intel"]["signals"].get("Threat"):
        risks.append(f"{S['market_intel']['signals']['Threat']} market developments flagged as threats in the last four weeks")
    decisions = []
    st = (sc_s.get("state") or "")
    if st in ("OPEN", "OWNER_SUBMITTED", "LLT_REVIEWED"):
        decisions.append(f"Endorse the {L['fy_code']} scorecard for {L['label']} "
                         f"(currently: {STATE_LABEL.get(st, st).lower()})")
    elif st == "BOARD_ENDORSED":
        decisions.append(f"Scorecard for {L['label']} endorsed – lock the period once scoring is complete")
    if over is not None and over > 0:
        decisions.append(f"Note the HUGS estimate at completion of {fv(eac, 'money')} against the revised P50")
    decisions += ["Approve the minutes of the previous meeting", "Declarations of interest"]
    S["risks"] = {"signals": risks}
    S["decisions"] = {"signals": decisions}
    return S


_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_LOCK = threading.Lock()
TTL = 300


def live_data(u: auth.User, per: dict, fresh: bool = False) -> dict:
    """Slide data for one viewer and period. Cached per viewer for a few minutes (never shared between users)."""
    key = (u.email, per["period_code"])
    if not fresh:
        with _LOCK:
            hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
    data = _build(u, per)
    now = time.time()
    with _LOCK:
        for k in [k for k, (t, _) in _CACHE.items() if now - t > TTL]:
            _CACHE.pop(k, None)
        _CACHE[key] = (now, data)
    return data


@router.get("/{code}/data")
def pack_data(code: str, refresh: bool = False, u: auth.User = Depends(me_dep)):
    with db.tx(u.email, u.role) as cur:
        per = _period(cur, code)
    return live_data(u, per, fresh=refresh)["public"]


# ------------------------------------------------------------------------------------------------ AI draft facts
def _metric_lines(slide: dict) -> list[str]:
    out = []
    for mt in slide.get("metrics", []):
        m, y = mt["m"], mt.get("y")
        s = f"- {mt['label']}: {m['t']}" + (f" ({m['label']})" if m.get("label") and m["label"] != "Now" else "")
        if m.get("p"):
            s += f", compared with {m['p']} {m['vs']}".rstrip()
        if y:
            s += f"; {y['label']} {y['t']}" + (f", compared with {y['p']} {y['vs']}" if y.get("p") else "")
        if mt.get("note"):
            s += f" [{mt['note']}]"
        out.append(s)
    return out


def _facts(u: auth.User, subject: str, period_key: str) -> str:
    if subject not in KEYS:
        raise HTTPException(400, f"unknown board pack slide {subject}")
    with db.tx(u.email, u.role) as cur:
        per = _period(cur, period_key)
        settings = _settings(cur, period_key)
    d = live_data(u, per)
    L, S, raw = d["public"]["period"], d["public"]["slides"], d["raw"]
    a = date.fromisoformat(L["month_start"])
    pm, py = Period("month", a), Period("fytd", a)
    title = next(s for s in _slides(L, settings, {}, False) if s["key"] == subject)["title"]
    head = (f"Lochard Energy board pack – slide “{title}” – reporting month {L['month']} (compared with "
            f"{L['month_pcp']}), financial year to date {L['fytd_long']}. Financial year runs July to June.")
    body: list[str] = []
    if subject in ("hse", "maintenance", "finance", "operations"):
        body.append(insights.facts_text(subject, raw["m"].get(subject, {}), pm))
        body.append("Year to date:\n" + insights.facts_text(subject, raw["y"].get(subject, {}), py))
        if subject == "operations":
            body.append("\n".join(_metric_lines(S["operations"])[1:3] + _metric_lines(S["operations"])[4:]))
        if subject == "finance" and S["finance"].get("table", {}).get("rows"):
            body.append("Year to date by team (actual / budget / variance): " + "; ".join(
                f"{r['team']} {r['actual']} / {r['budget']} / {r['variance']}" for r in S["finance"]["table"]["rows"]))
    elif subject in ("market", "hugs"):
        body += _metric_lines(S[subject])
        if subject == "hugs":
            e = S["hugs"]["eac"]
            body.append(f"Estimate at completion {e['eac']} against the revised P50 budget {e['p50']} "
                        f"(variance {e['variance']}, {e['pct_of_p50']} of P50).")
            if S["hugs"].get("kpi"):
                k = S["hugs"]["kpi"]
                body.append(f"Board scorecard KPI {k['code']} {k['name']}: {k['status_label']}. Owner update: {k['update'] or 'none'}")
    elif subject == "scorecard":
        sc = S["scorecard"]
        s = sc.get("summary") or {}
        body.append(f"Scorecard status index {s.get('status_index')}, weighted board score {s.get('board_score')}, "
                    f"{s.get('at_risk')} KPIs at risk and {s.get('off_track')} off track of {s.get('kpis')}. "
                    f"Workflow: {sc.get('state_label')}.")
        for p in sc.get("pillars", []):
            for k in p["kpis"]:
                body.append(f"- {k['code']} {k['name']} ({p['name']}, weight {k['weight']}): {k['status_label']}; "
                            f"board average {k['board'] or 'not scored'}. Owner update: {(k['update'] or '')[:300]}")
    elif subject == "exec_summary":
        for h in S["exec_summary"]["headlines"]:
            body.append(f"- {h['label']}: {h['value']} ({h['sub']})")
        s = S["exec_summary"]["scorecard"]
        body.append(f"Board scorecard: status index {s.get('status_index')}, {s.get('at_risk')} KPIs at risk, "
                    f"{s.get('off_track')} off track.")
        for a2 in S["exec_summary"]["attention"]:
            body.append(f"- KPI {a2['code']} {a2['name']}: {a2['status_label']}")
        for c in S["exec_summary"]["domain_commentary"]:
            body.append(f"Approved management commentary – {c['title']}: {c['body']}")
    elif subject == "market_intel":
        mi = S["market_intel"]
        if not mi["available"] or not mi["briefs"]:
            body.append("No weekly market briefs are available for the last four weeks.")
        for b in mi["briefs"]:
            body.append(f"- {b['week_label']}: {b['headline']}. {b['summary'] or ''}")
        for i in mi["items"]:
            body.append(f"- {i['date']} {i['source']}: {i['title']} ({i['signal']}). {i['why'] or ''}")
    elif subject == "cover":
        inc = [s["title"] for s in _slides(L, settings, {}, False) if s["included"]]
        body.append(f"Board pack for {L['month_long']} ({L['fy']}). Scorecard workflow: {L['state_label']}. "
                    f"Agenda: {'; '.join(inc)}.")
        body.append("Write a short covering note: the purpose of the pack and what the Board is asked to note or approve.")
    elif subject in ("risks", "decisions"):
        sig = S[subject]["signals"]
        body.append(("Signals from this month's pack:\n" if sig else "") + "\n".join(f"- {s}" for s in sig))
        body.append("Summarise the key risks for the Board: rating, movement and mitigation." if subject == "risks"
                    else "List the decisions and resolutions sought from the Board and the matters for noting.")
    return head + "\n" + "\n".join(b for b in body if b)


commentary.register_facts("boardpack", _facts)


# ------------------------------------------------------------------------------------------------ curation
class SlideIn(BaseModel):
    included: bool | None = None
    owner: str | None = Field(default=None, max_length=80)


@router.put("/{code}/slides/{key}")
def set_slide(code: str, key: str, body: SlideIn, u: auth.User = Depends(me_dep)):
    auth.require(u, *CURATORS)
    if key not in KEYS:
        raise HTTPException(404, f"unknown slide {key}")
    if key in REQUIRED and body.included is False:
        raise HTTPException(400, "the cover is always part of the pack")
    owner_set = "owner" in body.model_fields_set
    owner = (body.owner or "").strip() or None
    with db.tx(u.email, u.role) as cur:
        _period(cur, code)
        cur.execute("""INSERT INTO scorecard.board_pack_slide (period_code, slide_key, included, owner, updated_by)
                       VALUES (%(p)s, %(k)s, coalesce(%(i)s, true), %(o)s, %(e)s)
                       ON CONFLICT (period_code, slide_key) DO UPDATE SET
                         included = coalesce(%(i)s, scorecard.board_pack_slide.included),
                         owner = CASE WHEN %(os)s THEN %(o)s ELSE scorecard.board_pack_slide.owner END,
                         updated_by = EXCLUDED.updated_by, updated_at = now()
                       RETURNING slide_key, included, owner, updated_by, updated_at""",
                    {"p": code, "k": key, "i": body.included, "o": owner if owner_set else None, "os": owner_set,
                     "e": u.email})
        return _rows([cur.fetchone()])[0]


# ------------------------------------------------------------------------------------------------ finalise / versions
class FinaliseIn(BaseModel):
    override_reason: str | None = Field(default=None, max_length=2000)


def _not_ready_msg(nr: list[dict]) -> str:
    names = ", ".join(s["title"] for s in nr[:6]) + ("…" if len(nr) > 6 else "")
    return (f"{len(nr)} included slide{'s are' if len(nr) != 1 else ' is'} not ready ({names}). "
            "Give a reason to finalise anyway.")


@router.post("/{code}/finalise")
def finalise(code: str, body: FinaliseIn, u: auth.User = Depends(me_dep)):
    auth.require(u, *CURATORS)
    reason = (body.override_reason or "").strip() or None
    m = _meta(u, code)
    if m["readiness"]["total"] == 0:
        raise HTTPException(409, "include at least one slide in the pack")
    if m["readiness"]["not_ready"] and not reason:
        raise HTTPException(409, _not_ready_msg(m["readiness"]["not_ready"]))
    data = live_data(u, m["_row"], fresh=True)          # freeze current numbers, not a cached copy
    with db.tx(u.email, u.role) as cur:
        cur.execute("SELECT period_code FROM scorecard.reporting_period WHERE period_code = %s FOR UPDATE", (code,))
        per = _period(cur, code)
        L = _labels(per)
        slides = _slides(L, _settings(cur, code), _commentary_state(cur, code), True)
        rd = _readiness(slides)
        if rd["not_ready"] and not reason:
            raise HTTPException(409, _not_ready_msg(rd["not_ready"]))
        approved = _approved(cur, code)
        cur.execute("SELECT coalesce(max(version), 0) + 1 AS v FROM scorecard.board_pack WHERE period_code = %s", (code,))
        version = cur.fetchone()["v"]
        now = datetime.now(timezone.utc)
        for s in slides:
            c = approved.get(s["key"])
            s["commentary"] = {k: c.get(k) for k in ("body", "author_name", "author_role", "reviewer_name",
                                                      "reviewed_at", "ai_assisted", "version")} if c else None
        snapshot = {"schema": 1, "period": L, "version": version, "data_as_at": data["public"]["generated_at"],
                    "finalised": {"by": u.email, "name": u.name, "role": u.role, "at": now.isoformat()},
                    "override_reason": reason if rd["not_ready"] else None, "readiness": rd, "slides": slides,
                    "data": data["public"]["slides"],
                    "history": [{"version": v["version"], "status": v["status"], "finalised_name": v["finalised_name"],
                                 "finalised_at": v["finalised_at"], "sent_at": v["sent_at"]} for v in m["versions"]]}
        snap_json = json.dumps(snapshot, default=str, sort_keys=True)
        snapshot["fingerprint"] = hashlib.sha256(snap_json.encode()).hexdigest()
        pdf, pages = boardpack_pdf.render(snapshot)
        cur.execute("""INSERT INTO scorecard.board_pack (period_code, version, status, slides_included, slides_ready,
                           slides_total, not_ready, override_reason, finalised_by, finalised_name, finalised_role,
                           finalised_at, pdf_sha256, pdf_bytes, pdf_pages, snapshot_sha256)
                       VALUES (%s, %s, 'FINAL', %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING board_pack_id""",
                    (code, version, [s["key"] for s in slides if s["included"]], rd["ready"], rd["total"],
                     json.dumps(rd["not_ready"]), snapshot["override_reason"], u.email, u.name, u.role, now,
                     hashlib.sha256(pdf).hexdigest(), len(pdf), pages, snapshot["fingerprint"]))
        pid = cur.fetchone()["board_pack_id"]
        cur.execute("INSERT INTO scorecard.board_pack_content (board_pack_id, snapshot, pdf) VALUES (%s, %s::jsonb, %s)",
                    (pid, json.dumps(snapshot, default=str), pdf))
        cur.execute("""UPDATE scorecard.board_pack SET status = 'SUPERSEDED', superseded_at = now()
                       WHERE period_code = %s AND version < %s AND status <> 'SUPERSEDED'""", (code, version))
        vs = _versions(cur, code)
    return {"version": vs[0], "versions": vs}


def _version_row(cur, code: str, version: int, lock: bool = False) -> dict:
    cur.execute(f"""SELECT board_pack_id, version, status, finalised_name, finalised_at, sent_at FROM scorecard.board_pack
                    WHERE period_code = %s AND version = %s{' FOR UPDATE' if lock else ''}""", (code, version))
    r = cur.fetchone()
    if not r:
        raise HTTPException(404, f"no finalised version {version} for {code}")
    return r


@router.get("/{code}/versions/{version}")
def get_version(code: str, version: int, u: auth.User = Depends(me_dep)):
    with db.tx(u.email, u.role) as cur:
        r = _version_row(cur, code, version)
        cur.execute("SELECT snapshot FROM scorecard.board_pack_content WHERE board_pack_id = %s", (r["board_pack_id"],))
        c = cur.fetchone()
        vs = _versions(cur, code)
    return {"version": next(v for v in vs if v["version"] == version), "snapshot": c["snapshot"] if c else None}


@router.get("/{code}/versions/{version}/pdf")
def get_pdf(code: str, version: int, u: auth.User = Depends(me_dep)):
    auth.require(u, *DOWNLOADERS)
    with db.tx(u.email, u.role) as cur:
        r = _version_row(cur, code, version)
        cur.execute("SELECT pdf FROM scorecard.board_pack_content WHERE board_pack_id = %s", (r["board_pack_id"],))
        c = cur.fetchone()
    if not c:
        raise HTTPException(404, "PDF not found")
    return Response(bytes(c["pdf"]), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="Lochard_Board_Pack_{code}_v{version}.pdf"',
                             "Cache-Control": "private, no-store"})


@router.post("/{code}/versions/{version}/sent")
def mark_sent(code: str, version: int, u: auth.User = Depends(me_dep)):
    auth.require(u, *CURATORS)
    with db.tx(u.email, u.role) as cur:
        r = _version_row(cur, code, version, lock=True)
        if r["status"] == "SUPERSEDED":
            raise HTTPException(409, f"version {version} has been superseded by a later version")
        if r["status"] == "SENT":
            raise HTTPException(409, f"version {version} was already marked as sent")
        cur.execute("""UPDATE scorecard.board_pack SET status = 'SENT', sent_by = %s, sent_name = %s, sent_at = now()
                       WHERE board_pack_id = %s""", (u.email, u.name, r["board_pack_id"]))
        vs = _versions(cur, code)
    return {"version": next(v for v in vs if v["version"] == version), "versions": vs}
