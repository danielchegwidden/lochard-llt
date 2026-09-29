"""Commentary workflow shared by Leadership Insights, the Market Intelligence Hub and the board pack.

Managers / analysts draft (optionally from an AI draft, always labelled), then submit; leaders approve or return
with a note. Visibility follows the workflow: drafts stay with the managers, leaders see submitted and approved
text, the Board and observers see approved text only.

Other modules register a facts provider per scope, so AI drafts are grounded on the same governed numbers the
page shows:  commentary.register_facts("insights", fn)  where fn(user, subject, period_key) -> str.
"""
from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, config, db, llm
from .scorecard import _rows, me_dep

router = APIRouter(prefix="/api/commentary")

WRITERS = ("KPI_OWNER", "LLT")          # ADMIN is always allowed (auth.require)
REVIEWERS = ("LLT",)
VISIBLE = {"ADMIN": None, "KPI_OWNER": None, "LLT": ("SUBMITTED", "APPROVED", "RETURNED"),
           "BOARD": ("APPROVED",), "OBSERVER": ("APPROVED",)}
SCOPES = ("insights", "market", "boardpack")
_FACTS: dict[str, Callable[[auth.User, str, str], str]] = {}

SYSTEM = ("You draft short management commentary for Lochard Energy (owner of the Iona underground gas storage facility "
          "in Victoria) for its leadership team and board. Write 3-5 sentences in Australian English: what happened, why "
          "it matters and one next step. Use only the figures provided, keep the tone factual and neutral, never name "
          "individuals and never invent numbers or causes that the facts do not support. Plain prose only: no "
          "headings, bullet points or markdown.")


def register_facts(scope: str, fn: Callable[[auth.User, str, str], str]) -> None:
    _FACTS[scope] = fn


def _visible(u: auth.User, rec: dict) -> bool:
    allowed = VISIBLE.get(u.role, ("APPROVED",))
    own = rec["author_email"] == u.email and not u.real_role     # an admin's "view as" lens must not leak their drafts
    return allowed is None or rec["status"] in allowed or own


def _perms(u: auth.User) -> dict:
    return {"can_write": u.role in WRITERS or u.role == "ADMIN", "can_review": u.role in REVIEWERS or u.role == "ADMIN"}


def fetch(u: auth.User, scope: str, period_key: str, subjects: list[str] | None = None) -> dict[str, dict]:
    """Visible commentary for a period, keyed by subject (used by other routes, e.g. the board pack)."""
    with db.tx(u.email, u.role) as cur:
        cur.execute("""SELECT * FROM scorecard.commentary WHERE scope = %s AND period_key = %s
                       AND (%s::text[] IS NULL OR subject = ANY(%s::text[]))""", (scope, period_key, subjects, subjects))
        rows = _rows(cur.fetchall())
    return {r["subject"]: r for r in rows if _visible(u, r)}


@router.get("")
def list_commentary(scope: str, period_key: str, subject: str | None = None, u: auth.User = Depends(me_dep)):
    items = fetch(u, scope, period_key, [subject] if subject else None)
    return {"items": items, **_perms(u), "role": u.role}


class CommentaryIn(BaseModel):
    scope: str = Field(pattern="^(insights|market|boardpack)$")
    subject: str = Field(min_length=1, max_length=80)
    period_key: str = Field(min_length=3, max_length=40)
    body: str = Field(min_length=1, max_length=8000)
    ai_assisted: bool = False
    ai_model: str | None = None


@router.put("")
def save(body: CommentaryIn, u: auth.User = Depends(me_dep)):
    """Create or edit. Any edit returns the text to DRAFT, so a changed text is always reviewed again."""
    auth.require(u, *WRITERS)
    with db.tx(u.email, u.role) as cur:
        cur.execute("""INSERT INTO scorecard.commentary (scope, subject, period_key, body, author_email, author_name,
                           author_role, ai_assisted, ai_model)
                       VALUES (%(sc)s, %(su)s, %(p)s, %(b)s, %(e)s, %(n)s, %(r)s, %(ai)s, %(m)s)
                       ON CONFLICT (scope, subject, period_key) DO UPDATE SET body = EXCLUDED.body, status = 'DRAFT',
                           author_email = EXCLUDED.author_email, author_name = EXCLUDED.author_name,
                           author_role = EXCLUDED.author_role,
                           ai_assisted = scorecard.commentary.ai_assisted OR EXCLUDED.ai_assisted,
                           ai_model = coalesce(EXCLUDED.ai_model, scorecard.commentary.ai_model),
                           submitted_at = NULL, reviewer_email = NULL, reviewer_name = NULL, reviewed_at = NULL,
                           review_note = CASE WHEN scorecard.commentary.status = 'RETURNED'
                                              THEN scorecard.commentary.review_note END,
                           updated_at = now(), version = scorecard.commentary.version + 1
                       RETURNING *""",
                    {"sc": body.scope, "su": body.subject, "p": body.period_key, "b": body.body.strip(), "e": u.email,
                     "n": u.name, "r": u.role, "ai": body.ai_assisted, "m": body.ai_model})
        return _rows([cur.fetchone()])[0]


def _get(cur, cid: int) -> dict:
    cur.execute("SELECT * FROM scorecard.commentary WHERE commentary_id = %s FOR UPDATE", (cid,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(404, "unknown commentary")
    return r


@router.post("/{cid}/submit")
def submit(cid: int, u: auth.User = Depends(me_dep)):
    auth.require(u, *WRITERS)
    with db.tx(u.email, u.role) as cur:
        r = _get(cur, cid)
        if r["status"] not in ("DRAFT", "RETURNED"):
            raise HTTPException(409, f"commentary is {r['status']}")
        cur.execute("""UPDATE scorecard.commentary SET status = 'SUBMITTED', submitted_at = now(), updated_at = now()
                       WHERE commentary_id = %s RETURNING *""", (cid,))
        return _rows([cur.fetchone()])[0]


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(APPROVE|RETURN)$")
    note: str | None = Field(default=None, max_length=2000)


@router.post("/{cid}/review")
def review(cid: int, body: ReviewIn, u: auth.User = Depends(me_dep)):
    auth.require(u, *REVIEWERS)
    if body.decision == "RETURN" and not (body.note or "").strip():
        raise HTTPException(400, "add a note so the author knows what to change")
    with db.tx(u.email, u.role) as cur:
        r = _get(cur, cid)
        if r["status"] != "SUBMITTED" and not (u.role == "ADMIN" and r["status"] == "DRAFT"):
            raise HTTPException(409, f"only submitted commentary can be reviewed (this one is {r['status']})")
        cur.execute("""UPDATE scorecard.commentary SET status = %s, reviewer_email = %s, reviewer_name = %s,
                           review_note = %s, reviewed_at = now(), updated_at = now(),
                           submitted_at = coalesce(submitted_at, now())
                       WHERE commentary_id = %s RETURNING *""",
                    ("APPROVED" if body.decision == "APPROVE" else "RETURNED", u.email, u.name, body.note, cid))
        return _rows([cur.fetchone()])[0]


class DraftIn(BaseModel):
    scope: str = Field(pattern="^(insights|market|boardpack)$")
    subject: str
    period_key: str
    hint: str | None = Field(default=None, max_length=500)


@router.post("/ai-draft")
def ai_draft(body: DraftIn, u: auth.User = Depends(me_dep)):
    auth.require(u, *WRITERS)
    provider = _FACTS.get(body.scope)
    if not provider:
        raise HTTPException(400, f"no facts provider for {body.scope}")
    facts = provider(u, body.subject, body.period_key)
    prompt = f"{facts}\n\n" + (f"Author's note: {body.hint}\n\n" if body.hint else "") + "Draft the commentary."
    try:
        text, model, route = llm.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                                      model=config.LLM_ECONOMY_MODEL, user=u.email, max_tokens=700)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"AI drafting unavailable: {e}") from e
    return {"draft": text.strip(), "model": model, "route": route, "facts": facts}
