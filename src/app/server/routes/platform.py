"""Dashboards (embed URLs), live persona switch for the ABAC demo, and health."""
from __future__ import annotations

import os
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import auth, config, db, sql
from .scorecard import me_dep

router = APIRouter(prefix="/api")
PERSONAS = ["platform_admin", "board", "leadership", "finance", "budget_holder", "hse", "hse_investigator",
            "maintenance", "operations"]
_dash_cache: dict = {"t": 0, "rows": []}


@router.get("/dashboards")
def dashboards(u: auth.User = Depends(me_dep)):
    if time.time() - _dash_cache["t"] < 300 and _dash_cache["rows"]:
        return _dash_cache["rows"]
    by_name = {}
    if not all(os.environ.get(env) for env, _, _ in config.DASHBOARDS.values()):
        try:
            by_name = {d.display_name: d.dashboard_id for d in config.user_client(u.token).lakeview.list()}
        except Exception:  # noqa: BLE001
            by_name = {}
    host = config.host()
    rows = []
    for key, (env, name, tab) in config.DASHBOARDS.items():
        did = os.environ.get(env) or by_name.get(name)
        rows.append({"key": key, "title": tab, "dashboard_id": did,
                     "embed_url": f"{host}/embed/dashboardsv3/{did}?o={config.WORKSPACE_ID}" if did else None,
                     "open_url": f"{host}/dashboardsv3/{did}/published?o={config.WORKSPACE_ID}" if did else None})
    _dash_cache.update(t=time.time(), rows=rows)
    return rows


@router.get("/admin/persona")
def get_persona(u: auth.User = Depends(me_dep)):
    return {"email": u.email, "personas": u.personas, "team": u.persona_team, "role": u.role,
            "can_switch": u.can_switch_persona, "available": PERSONAS, "source": u.persona_source}


class PersonaIn(BaseModel):
    persona: str
    team: str | None = None


@router.post("/admin/persona")
def set_persona(body: PersonaIn, u: auth.User = Depends(me_dep)):
    """Switch the CURRENT user's UC persona – every dashboard, Genie answer and app query re-evaluates ABAC."""
    if not u.can_switch_persona:
        raise HTTPException(403, "only platform admins can switch persona")
    if body.persona not in PERSONAS:
        raise HTTPException(400, f"unknown persona {body.persona}")
    t = f"{config.CATALOG}.{config.GOVERNANCE}.principal_persona"
    try:
        sql.query(u.token, f"DELETE FROM {t} WHERE principal = current_user()")
        sql.query(u.token, f"INSERT INTO {t} (principal, persona, team, display, updated_at) "
                           f"SELECT current_user(), :persona, :team, 'switched in board portal', current_timestamp()",
                  {"persona": body.persona, "team": body.team})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"could not update persona: {e}") from e
    auth.invalidate(u.email)
    return {"email": u.email, "persona": body.persona, "team": body.team}


@router.get("/admin/governance-check")
def governance_check(u: auth.User = Depends(me_dep)):
    """Show the effect of the current persona on governed data (masked actionee, finance teams visible)."""
    q = {
        "actionee_sample": f"SELECT actionee FROM {sql.fq('v_observation_detail')} WHERE actionee IS NOT NULL LIMIT 3",
        "finance_teams_visible": f"SELECT COUNT(DISTINCT team) AS n FROM {sql.fq('v_finance_monthly')}",
        "legal_description_sample": f"SELECT description FROM {sql.fq('v_gl_transaction_detail')} "
                                    f"WHERE account_class = 'Legal' LIMIT 2",
    }
    return {k: sql.safe(u.token, v) for k, v in q.items()}


@router.get("/healthz")
def healthz():
    ok = True
    try:
        with db.tx() as cur:
            cur.execute("SELECT 1")
    except Exception:  # noqa: BLE001
        ok = False
    return {"ok": ok}
