"""Board scorecard API – KPIs, owner status updates, director scores, threaded comments, approval workflow."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .. import auth, db

router = APIRouter(prefix="/api")

STATES = ["OPEN", "OWNER_SUBMITTED", "LLT_REVIEWED", "BOARD_ENDORSED", "LOCKED"]
# (from, to) -> roles allowed (ADMIN always allowed)
TRANSITIONS = {
    ("OPEN", "OWNER_SUBMITTED"): {"KPI_OWNER", "LLT"},
    ("OWNER_SUBMITTED", "LLT_REVIEWED"): {"LLT"},
    ("OWNER_SUBMITTED", "OPEN"): {"LLT"},            # returned for rework
    ("LLT_REVIEWED", "BOARD_ENDORSED"): {"BOARD"},
    ("LLT_REVIEWED", "OWNER_SUBMITTED"): {"BOARD", "LLT"},
    ("BOARD_ENDORSED", "LOCKED"): {"BOARD"},
}
STATUS_POINTS = {"ON_TRACK": 1.0, "COMPLETE": 1.0, "AT_RISK": 0.5, "OFF_TRACK": 0.0}
VISIBLE = {"ALL": {"BOARD", "LLT", "KPI_OWNER", "ADMIN", "OBSERVER"}, "LLT_ONLY": {"LLT", "BOARD", "ADMIN"},
           "BOARD_ONLY": {"BOARD", "ADMIN"}}


def _j(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _rows(rows):
    return [{k: _j(v) for k, v in r.items()} for r in rows]


def me_dep(request: Request) -> auth.User:
    return auth.current_user(request)


@router.get("/me")
def me(u: auth.User = Depends(me_dep)):
    return u.as_dict()


@router.get("/fiscal-years")
def fiscal_years(u: auth.User = Depends(me_dep)):
    with db.tx(u.email, u.role) as cur:
        cur.execute("SELECT fy_code, start_date, end_date, status FROM scorecard.fiscal_year ORDER BY fy_code")
        fys = _rows(cur.fetchall())
        cur.execute("""SELECT p.period_code, p.fy_code, p.label, p.month_start, p.state,
                              EXISTS (SELECT 1 FROM scorecard.kpi_status_update u WHERE u.period_code = p.period_code) AS has_updates
                       FROM scorecard.reporting_period p ORDER BY p.month_start""")
        periods = _rows(cur.fetchall())
    return {"fiscal_years": fys, "periods": periods}


def _default_period(cur, fy: str) -> str:
    cur.execute("""SELECT p.period_code FROM scorecard.reporting_period p
                   WHERE p.fy_code = %s AND EXISTS (SELECT 1 FROM scorecard.kpi_status_update u WHERE u.period_code = p.period_code)
                   ORDER BY p.month_start DESC LIMIT 1""", (fy,))
    r = cur.fetchone()
    if r:
        return r["period_code"]
    cur.execute("SELECT period_code FROM scorecard.reporting_period WHERE fy_code = %s ORDER BY month_start LIMIT 1", (fy,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(404, f"no periods for {fy}")
    return r["period_code"]


def load_scorecard(u: auth.User, fy: str, period: str | None) -> dict:
    with db.tx(u.email, u.role) as cur:
        period = period or _default_period(cur, fy)
        cur.execute("SELECT * FROM scorecard.reporting_period WHERE period_code = %s AND fy_code = %s", (period, fy))
        per = cur.fetchone()
        if not per:
            raise HTTPException(404, f"unknown period {period} for {fy}")
        cur.execute("""
            SELECT k.kpi_id, k.code, k.name, k.owner_initials, k.owner_role, k.weight_pct, k.preamble, p.name AS pillar,
                   p.pillar_no, u.status, u.owner_score, u.commentary, u.ai_draft_accepted, u.submitted_by, u.submitted_at,
                   (SELECT avg(b.score) FROM scorecard.board_score b WHERE b.kpi_id = k.kpi_id AND b.period_code = %(p)s) AS avg_board_score,
                   (SELECT count(*) FROM scorecard.board_score b WHERE b.kpi_id = k.kpi_id AND b.period_code = %(p)s) AS n_scores,
                   (SELECT b.score FROM scorecard.board_score b WHERE b.kpi_id = k.kpi_id AND b.period_code = %(p)s
                      AND b.director_email = %(e)s) AS my_score,
                   (SELECT count(*) FROM scorecard.comment c WHERE c.kpi_id = k.kpi_id AND c.period_code = %(p)s) AS n_comments
            FROM scorecard.kpi k JOIN scorecard.pillar p ON p.pillar_id = k.pillar_id
            LEFT JOIN scorecard.kpi_status_update u ON u.kpi_id = k.kpi_id AND u.period_code = %(p)s
            WHERE k.fy_code = %(fy)s ORDER BY p.pillar_no, k.sort_order""", {"p": period, "fy": fy, "e": u.email})
        kpis = _rows(cur.fetchall())
        cur.execute("""SELECT d.kpi_id, d.seq, d.text FROM scorecard.deliverable d JOIN scorecard.kpi k USING (kpi_id)
                       WHERE k.fy_code = %s ORDER BY d.kpi_id, d.seq""", (fy,))
        dels = {}
        for r in cur.fetchall():
            dels.setdefault(r["kpi_id"], []).append({"seq": r["seq"], "text": r["text"]})
        cur.execute("SELECT * FROM scorecard.v_period_summary WHERE period_code = %s", (period,))
        summary = cur.fetchone() or {}
        cur.execute("""SELECT period_code, status_index_pct, weighted_board_score_pct, kpis_at_risk FROM scorecard.v_period_summary
                       WHERE fy_code = %s ORDER BY period_code""", (fy,))
        trend = _rows(cur.fetchall())
    pillars = []
    for k in kpis:
        k["deliverables"] = dels.get(k["kpi_id"], [])
        if not pillars or pillars[-1]["name"] != k["pillar"]:
            pillars.append({"name": k["pillar"], "pillar_no": k["pillar_no"], "kpis": []})
        pillars[-1]["kpis"].append(k)
    return {"fy": fy, "period": _rows([per])[0], "pillars": pillars,
            "summary": {k: _j(v) for k, v in summary.items()}, "trend": trend,
            "weights_total": sum(k["weight_pct"] for k in kpis),
            "footnote": "The Board retains full discretion to amend the KPIs and/or FY27 outcome for material events during the year"}


@router.get("/scorecard/{fy}")
def scorecard(fy: str, period: str | None = None, u: auth.User = Depends(me_dep)):
    return load_scorecard(u, fy, period)


@router.get("/kpi/{kpi_id}")
def kpi_detail(kpi_id: str, period: str, u: auth.User = Depends(me_dep)):
    with db.tx(u.email, u.role) as cur:
        cur.execute("SELECT k.*, p.name AS pillar FROM scorecard.kpi k JOIN scorecard.pillar p USING (pillar_id) WHERE kpi_id = %s",
                    (kpi_id,))
        k = cur.fetchone()
        if not k:
            raise HTTPException(404, "unknown KPI")
        cur.execute("SELECT seq, text FROM scorecard.deliverable WHERE kpi_id = %s ORDER BY seq", (kpi_id,))
        dels = _rows(cur.fetchall())
        cur.execute("SELECT * FROM scorecard.kpi_status_update WHERE kpi_id = %s AND period_code = %s", (kpi_id, period))
        upd = cur.fetchone()
        cur.execute("""SELECT director_name, director_email, score, rationale, updated_at FROM scorecard.board_score
                       WHERE kpi_id = %s AND period_code = %s ORDER BY director_name""", (kpi_id, period))
        scores = _rows(cur.fetchall())
        cur.execute("""SELECT comment_id, parent_id, author_name, author_email, author_role, body, visibility, created_at,
                              edited_at, resolved FROM scorecard.comment WHERE kpi_id = %s AND period_code = %s
                       ORDER BY created_at""", (kpi_id, period))
        comments = [c for c in _rows(cur.fetchall())
                    if u.role in VISIBLE[c["visibility"]] or c["author_email"] == u.email]
        cur.execute("""SELECT u.period_code, p.label, u.status, u.owner_score, u.commentary,
                              (SELECT avg(score) FROM scorecard.board_score b WHERE b.kpi_id = u.kpi_id
                                 AND b.period_code = u.period_code) AS avg_board_score
                       FROM scorecard.kpi_status_update u JOIN scorecard.reporting_period p USING (period_code)
                       WHERE u.kpi_id = %s ORDER BY p.month_start""", (kpi_id,))
        history = _rows(cur.fetchall())
        cur.execute("""SELECT actor_email, action, entity, at, after ->> 'status' AS status, after ->> 'score' AS score
                       FROM scorecard.audit_log WHERE (after ->> 'kpi_id' = %s OR before ->> 'kpi_id' = %s)
                       ORDER BY at DESC LIMIT 25""", (kpi_id, kpi_id))
        audit = _rows(cur.fetchall())
    # directors see individual scores; everyone else sees the average only
    if u.role not in ("BOARD", "ADMIN"):
        scores = [{"score": s["score"], "director_name": "Director", "mine": s["director_email"] == u.email} for s in scores]
    return {"kpi": _rows([k])[0], "deliverables": dels, "status": _rows([upd])[0] if upd else None, "board_scores": scores,
            "comments": comments, "history": history, "audit": audit}


def _period_state(cur, period: str) -> str:
    cur.execute("SELECT state FROM scorecard.reporting_period WHERE period_code = %s FOR UPDATE", (period,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(404, "unknown period")
    return r["state"]


class StatusIn(BaseModel):
    period: str
    status: str = Field(pattern="^(ON_TRACK|AT_RISK|OFF_TRACK|COMPLETE)$")
    owner_score: int | None = Field(default=None, ge=0, le=5)
    commentary: str | None = Field(default=None, max_length=4000)
    ai_draft_commentary: str | None = None
    ai_draft_accepted: bool | None = None
    ai_model: str | None = None


@router.post("/kpi/{kpi_id}/status")
def update_status(kpi_id: str, body: StatusIn, u: auth.User = Depends(me_dep)):
    auth.require(u, "KPI_OWNER", "LLT")
    with db.tx(u.email, u.role) as cur:
        state = _period_state(cur, body.period)
        if state not in ("OPEN", "OWNER_SUBMITTED"):
            raise HTTPException(409, f"period is {state} – status updates are closed")
        cur.execute("""INSERT INTO scorecard.kpi_status_update (kpi_id, period_code, status, owner_score, commentary,
                           ai_draft_commentary, ai_draft_accepted, ai_model, submitted_by)
                       VALUES (%(k)s, %(p)s, %(s)s, %(o)s, %(c)s, %(d)s, %(a)s, %(m)s, %(e)s)
                       ON CONFLICT (kpi_id, period_code) DO UPDATE SET status = EXCLUDED.status,
                           owner_score = EXCLUDED.owner_score, commentary = EXCLUDED.commentary,
                           ai_draft_commentary = coalesce(EXCLUDED.ai_draft_commentary, scorecard.kpi_status_update.ai_draft_commentary),
                           ai_draft_accepted = coalesce(EXCLUDED.ai_draft_accepted, scorecard.kpi_status_update.ai_draft_accepted),
                           ai_model = coalesce(EXCLUDED.ai_model, scorecard.kpi_status_update.ai_model),
                           submitted_by = EXCLUDED.submitted_by, submitted_at = now(),
                           version = scorecard.kpi_status_update.version + 1
                       RETURNING *""",
                    {"k": kpi_id, "p": body.period, "s": body.status, "o": body.owner_score, "c": body.commentary,
                     "d": body.ai_draft_commentary, "a": body.ai_draft_accepted, "m": body.ai_model, "e": u.email})
        return _rows([cur.fetchone()])[0]


class ScoreIn(BaseModel):
    period: str
    score: int = Field(ge=0, le=5)
    rationale: str | None = Field(default=None, max_length=2000)


@router.post("/kpi/{kpi_id}/score")
def board_score(kpi_id: str, body: ScoreIn, u: auth.User = Depends(me_dep)):
    auth.require(u, "BOARD")
    with db.tx(u.email, u.role) as cur:
        state = _period_state(cur, body.period)
        if state == "LOCKED":
            raise HTTPException(409, "period is LOCKED – scores are final")
        cur.execute("""INSERT INTO scorecard.board_score (kpi_id, period_code, director_email, director_name, score, rationale)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (kpi_id, period_code, director_email) DO UPDATE
                       SET score = EXCLUDED.score, rationale = EXCLUDED.rationale, updated_at = now() RETURNING *""",
                    (kpi_id, body.period, u.email, u.name, body.score, body.rationale))
        return _rows([cur.fetchone()])[0]


class CommentIn(BaseModel):
    period: str
    body: str = Field(min_length=1, max_length=4000)
    visibility: str = Field(default="ALL", pattern="^(ALL|BOARD_ONLY|LLT_ONLY)$")
    parent_id: int | None = None


@router.post("/kpi/{kpi_id}/comments")
def add_comment(kpi_id: str, body: CommentIn, u: auth.User = Depends(me_dep)):
    auth.require(u, "BOARD", "LLT", "KPI_OWNER")
    if u.role not in VISIBLE[body.visibility]:
        raise HTTPException(403, f"{u.role} cannot post {body.visibility} comments")
    with db.tx(u.email, u.role) as cur:
        if _period_state(cur, body.period) == "LOCKED":
            raise HTTPException(409, "period is LOCKED")
        cur.execute("""INSERT INTO scorecard.comment (kpi_id, period_code, parent_id, author_email, author_name, author_role,
                           body, visibility) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (kpi_id, body.period, body.parent_id, u.email, u.name, u.role, body.body, body.visibility))
        return _rows([cur.fetchone()])[0]


class CommentPatch(BaseModel):
    body: str | None = Field(default=None, max_length=4000)
    resolved: bool | None = None


@router.patch("/comments/{comment_id}")
def edit_comment(comment_id: int, body: CommentPatch, u: auth.User = Depends(me_dep)):
    with db.tx(u.email, u.role) as cur:
        cur.execute("SELECT author_email FROM scorecard.comment WHERE comment_id = %s", (comment_id,))
        c = cur.fetchone()
        if not c:
            raise HTTPException(404, "unknown comment")
        if c["author_email"] != u.email and u.role != "ADMIN":
            raise HTTPException(403, "only the author can edit a comment")
        cur.execute("""UPDATE scorecard.comment SET body = coalesce(%s, body), resolved = coalesce(%s, resolved),
                       edited_at = CASE WHEN %s IS NOT NULL THEN now() ELSE edited_at END
                       WHERE comment_id = %s RETURNING *""", (body.body, body.resolved, body.body, comment_id))
        return _rows([cur.fetchone()])[0]


class AdvanceIn(BaseModel):
    to_state: str
    note: str | None = None


@router.post("/period/{period}/advance")
def advance(period: str, body: AdvanceIn, u: auth.User = Depends(me_dep)):
    with db.tx(u.email, u.role) as cur:
        state = _period_state(cur, period)
        allowed = TRANSITIONS.get((state, body.to_state))
        if allowed is None:
            raise HTTPException(409, f"illegal transition {state} -> {body.to_state}")
        if u.role not in allowed and u.role != "ADMIN":
            raise HTTPException(403, f"{u.role} cannot move a period from {state} to {body.to_state}")
        if body.to_state == "OWNER_SUBMITTED":
            cur.execute("""SELECT count(*) AS missing FROM scorecard.kpi k JOIN scorecard.reporting_period p USING (fy_code)
                           WHERE p.period_code = %s AND NOT EXISTS (SELECT 1 FROM scorecard.kpi_status_update u
                             WHERE u.kpi_id = k.kpi_id AND u.period_code = p.period_code)""", (period,))
            if cur.fetchone()["missing"]:
                raise HTTPException(409, "every KPI needs a status update before submission")
        if body.to_state == "BOARD_ENDORSED":
            cur.execute("""SELECT sum(weight_pct) AS w FROM scorecard.kpi k JOIN scorecard.reporting_period p USING (fy_code)
                           WHERE p.period_code = %s""", (period,))
            if float(cur.fetchone()["w"] or 0) != 100:
                raise HTTPException(409, "KPI weights must total 100% before endorsement")
        cur.execute("UPDATE scorecard.reporting_period SET state = %s WHERE period_code = %s", (body.to_state, period))
        cur.execute("""INSERT INTO scorecard.approval (period_code, from_state, to_state, approver_email, approver_role, note)
                       VALUES (%s,%s,%s,%s,%s,%s)""", (period, state, body.to_state, u.email, u.role, body.note))
    return {"period": period, "from": state, "to": body.to_state}


@router.get("/period/{period}/history")
def period_history(period: str, u: auth.User = Depends(me_dep)):
    with db.tx(u.email, u.role) as cur:
        cur.execute("""SELECT from_state, to_state, approver_email, approver_role, note, decided_at FROM scorecard.approval
                       WHERE period_code = %s ORDER BY decided_at""", (period,))
        return {"approvals": _rows(cur.fetchall()), "states": STATES}


@router.get("/audit")
def audit(entity: str | None = None, limit: int = 100, u: auth.User = Depends(me_dep)):
    auth.require(u, "BOARD", "LLT")
    with db.tx(u.email, u.role) as cur:
        cur.execute("""SELECT id, actor_email, action, entity, entity_id, at FROM scorecard.audit_log
                       WHERE (%s::text IS NULL OR entity = %s) ORDER BY id DESC LIMIT %s""", (entity, entity, min(limit, 500)))
        return _rows(cur.fetchall())
