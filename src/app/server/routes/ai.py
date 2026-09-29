"""AI features – draft KPI commentary (human-in-the-loop) and Genie Ask (OBO)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, config, db, genie, llm
from .insights import evidence_for
from .scorecard import me_dep

router = APIRouter(prefix="/api")

SYSTEM = ("You draft concise board-report commentary for Lochard Energy (Iona Gas Storage Facility, VIC). "
          "Write 2-4 sentences in Australian English, factual and neutral, citing the evidence figures provided. "
          "Do not invent numbers, do not name individuals, and do not state a status the owner has not chosen. "
          "Finish with one forward-looking action.")


class DraftIn(BaseModel):
    period: str
    status: str | None = None


def _fmt(e):
    v = e["value"]
    if v is None:
        return "n/a"
    if e["kind"] == "money":
        return f"${float(v) / 1e6:,.2f}M"
    if e["kind"] == "pct":
        return f"{float(v) * 100:.1f}%"
    return f"{float(v):,.2f}" if isinstance(v, float) and not float(v).is_integer() else f"{int(float(v)):,}"


@router.post("/kpi/{kpi_id}/ai-draft")
def ai_draft(kpi_id: str, body: DraftIn, u: auth.User = Depends(me_dep)):
    auth.require(u, "KPI_OWNER", "LLT")
    with db.tx(u.email, u.role) as cur:
        cur.execute("SELECT code, name, owner_role, weight_pct FROM scorecard.kpi WHERE kpi_id = %s", (kpi_id,))
        k = cur.fetchone()
        if not k:
            raise HTTPException(404, "unknown KPI")
        cur.execute("SELECT text FROM scorecard.deliverable WHERE kpi_id = %s ORDER BY seq", (kpi_id,))
        dels = [r["text"] for r in cur.fetchall()]
        cur.execute("""SELECT u.status, u.commentary FROM scorecard.kpi_status_update u
                       JOIN scorecard.reporting_period p USING (period_code)
                       WHERE u.kpi_id = %s AND p.month_start <= (SELECT month_start FROM scorecard.reporting_period
                                                                  WHERE period_code = %s)
                       ORDER BY p.month_start DESC LIMIT 1""", (kpi_id, body.period))
        prev = cur.fetchone()
    ev = evidence_for(u.token, k["code"])
    ev_txt = "\n".join(f"- {e['label']}: {_fmt(e)}" for e in ev if e["value"] is not None) or "- (no live metrics bound)"
    prompt = (f"KPI {k['code']} {k['name']} (owner: {k['owner_role']}, weight {float(k['weight_pct']):.0f}%).\n"
              f"Deliverables:\n" + "\n".join(f"{i + 1}. {d}" for i, d in enumerate(dels)) +
              f"\nOwner-selected status: {body.status or (prev or {}).get('status') or 'not yet set'}\n"
              f"Previous commentary: {(prev or {}).get('commentary') or 'none'}\nLive evidence:\n{ev_txt}\n\n"
              "Draft the commentary for this month's board scorecard.")
    try:
        text, model, route = llm.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                                      model=config.LLM_ECONOMY_MODEL, user=u.email)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"AI drafting unavailable: {e}") from e
    return {"draft": text.strip(), "model": model, "route": route, "evidence": ev,
            "label": "AI draft – review, edit and accept before it is saved. The status remains the owner's decision."}


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    space: str | None = None
    conversation_id: str | None = None


@router.get("/ask/spaces")
def ask_spaces(u: auth.User = Depends(me_dep)):
    sp = dict(genie.spaces(u.token))
    if genie.SUPERVISOR_ENDPOINT:
        sp = {"analyst": {"space_id": genie.SUPERVISOR_ENDPOINT, "title": "Leadership Analyst (all domains)"}, **sp}
    return sp


@router.post("/ask")
def ask(body: AskIn, u: auth.User = Depends(me_dep)):
    if body.space == "analyst" and genie.SUPERVISOR_ENDPOINT:
        out = genie.ask_supervisor(u.token, body.question)
        return {**out, "space": "analyst", "space_id": genie.SUPERVISOR_ENDPOINT,
                "space_title": "Leadership Analyst (Supervisor Agent)"}
    sp = genie.spaces(u.token)
    if not sp:
        raise HTTPException(503, "No Lochard Genie Agents are available yet")
    key = body.space if body.space in sp else ("executive" if "executive" in sp else next(iter(sp)))
    space_id = sp[key]["space_id"]
    try:
        out = genie.ask(u.token, space_id, body.question, body.conversation_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Genie error: {e}") from e
    with db.tx(u.email, u.role) as cur:
        cur.execute("""INSERT INTO scorecard.genie_conversation (user_email, space_id, conversation_id, message_id, question)
                       VALUES (%s,%s,%s,%s,%s)""", (u.email, space_id, out["conversation_id"], out["message_id"], body.question))
    return {**out, "space": key, "space_id": space_id, "space_title": sp[key]["title"]}


class FeedbackIn(BaseModel):
    space_id: str
    conversation_id: str
    message_id: str
    positive: bool
    comment: str | None = None


@router.post("/ask/feedback")
def ask_feedback(body: FeedbackIn, u: auth.User = Depends(me_dep)):
    sent = True
    try:
        genie.feedback(u.token, body.space_id, body.conversation_id, body.message_id, body.positive)
    except Exception:  # noqa: BLE001
        sent = False
    with db.tx(u.email, u.role) as cur:
        cur.execute("""INSERT INTO scorecard.ask_feedback (user_email, space_id, conversation_id, message_id, rating, comment)
                       VALUES (%s,%s,%s,%s,%s,%s)""", (u.email, body.space_id, body.conversation_id, body.message_id,
                                                      1 if body.positive else -1, body.comment))
    return {"recorded": True, "sent_to_genie": sent}
