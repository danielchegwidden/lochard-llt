"""Agents page: catalog, live traces (server-sent events), the model-routing lab and run history."""
from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import agents, auth, config, db
from .scorecard import me_dep

router = APIRouter(prefix="/api/agents")
log = logging.getLogger("lochard.agents")
_state: dict = {"t": 0, "v": {}}


def _endpoint_states() -> dict:
    """READY / NOT_READY for the Agent Bricks endpoints (app identity, cached 60 s)."""
    if time.time() - _state["t"] < 60:
        return _state["v"]
    out = {}
    for name in (agents.SUPERVISOR_ENDPOINT, agents.KNOWLEDGE_ENDPOINT):
        try:
            e = config.app_client().serving_endpoints.get(name)
            out[name] = e.state.ready.value if e.state and e.state.ready else "UNKNOWN"
        except Exception:  # noqa: BLE001
            out[name] = "UNKNOWN"
    _state.update(t=time.time(), v=out)
    return out


@router.get("")
def list_agents(u: auth.User = Depends(me_dep)):
    states = _endpoint_states()
    cat = agents.catalog()
    for a in cat:
        if a.get("endpoint"):
            a["state"] = states.get(a["endpoint"], "UNKNOWN")
    stats = {}
    try:
        with db.tx(u.email, u.role) as cur:
            cur.execute("""SELECT agent, count(*) AS runs, round(avg(latency_ms)) AS avg_ms,
                                  count(*) FILTER (WHERE rating = 1) AS up, count(*) FILTER (WHERE rating = -1) AS down
                           FROM scorecard.agent_run GROUP BY agent""")
            stats = {r["agent"]: r for r in cur.fetchall()}
    except Exception as e:  # noqa: BLE001 – history is optional (table created by migration V002)
        log.info("agent stats unavailable: %s", e)
    return {"agents": cat, "stats": stats, "workspace": config.host()}


class Turn(BaseModel):
    role: str
    content: str


class RunIn(BaseModel):
    agent: str
    question: str = Field(min_length=3, max_length=2000)
    history: list[Turn] = []          # previous turns (supervisor / knowledge are stateless – we replay context)
    conversation_id: str | None = None  # Genie keeps its own conversation state


def _log_run(u: auth.User, agent: str, question: str, done: dict, steps: list[dict], detail: dict | None = None):
    try:
        with db.tx(u.email, u.role) as cur:
            cur.execute("""INSERT INTO scorecard.agent_run (user_email, agent, question, tools_used, n_steps, n_citations,
                                                            latency_ms, status, answer, detail)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING run_id""",
                        (u.email, agent, question, done.get("tools_used") or [], len(steps),
                         len(done.get("citations") or []), done.get("latency_ms"),
                         "FAILED" if done.get("error") else "COMPLETED", (done.get("answer") or "")[:8000],
                         json.dumps(detail or {})))
            return cur.fetchone()["run_id"]
    except Exception as e:  # noqa: BLE001
        log.info("agent run not logged: %s", e)
        return None


@router.post("/stream")
def stream(body: RunIn, u: auth.User = Depends(me_dep)):
    if body.agent in ("supervisor", "knowledge"):
        msgs = [t.model_dump() for t in body.history[-8:]] + [{"role": "user", "content": body.question}]
        gen = agents.stream_responses(u.token, body.agent, msgs)
    elif body.agent.startswith("genie:"):
        gen = agents.stream_genie(u.token, body.agent.split(":", 1)[1], body.question, body.conversation_id)
    else:
        raise HTTPException(400, f"unknown agent {body.agent}")

    def sse():
        steps: list[dict] = []
        for ev in gen:
            if ev["type"] == "step":
                steps.append(ev["step"])
            if ev["type"] in ("done", "error"):
                done = ev if ev["type"] == "done" else {"error": ev["error"], "latency_ms": None}
                ev = {**ev, "run_id": _log_run(u, body.agent, body.question, done, steps,
                                               {k: ev.get(k) for k in ("conversation_id", "message_id", "space_id")})}
            yield f"data: {json.dumps(ev, default=str)}\n\n"

    return StreamingResponse(sse(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _scorecard_facts(u: auth.User) -> str:
    """Latest reported FY27 period from Lakebase – the grounding for the routing lab (fast, no warehouse)."""
    with db.tx(u.email, u.role) as cur:
        cur.execute("""SELECT p.label, k.code, k.name, k.weight_pct, s.status, s.commentary
                       FROM scorecard.kpi_status_update s JOIN scorecard.kpi k USING (kpi_id)
                       JOIN scorecard.reporting_period p USING (period_code)
                       WHERE p.period_code = (SELECT max(period_code) FROM scorecard.kpi_status_update
                                              WHERE period_code LIKE 'FY27%%')
                       ORDER BY k.code""")
        rows = cur.fetchall()
        cur.execute("""SELECT * FROM scorecard.v_period_summary WHERE period_code =
                       (SELECT max(period_code) FROM scorecard.kpi_status_update WHERE period_code LIKE 'FY27%%')""")
        summ = cur.fetchone() or {}
    lines = [f"Period {rows[0]['label'] if rows else '?'}; status index {summ.get('status_index_pct')}% "
             f"(On Track = 100%, At Risk = 50%, Off Track = 0%); KPIs at risk {summ.get('kpis_at_risk')}."]
    lines += [f"{r['code']} {r['name']} (weight {float(r['weight_pct']):.0f}%): {r['status']} – {r['commentary'] or ''}"
              for r in rows]
    return "\n".join(lines)


class LabIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    compare: bool = True


@router.post("/lab")
def lab(body: LabIn, u: auth.User = Depends(me_dep)):
    try:
        facts = _scorecard_facts(u)
    except Exception as e:  # noqa: BLE001
        facts = f"(scorecard unavailable: {e})"
    out = agents.routing_lab(u.token, body.question, facts, body.compare)
    chosen = next((a for a in out["arms"] if a["chosen"]), {})
    out["facts"] = facts
    out["run_id"] = _log_run(u, "router", body.question,
                             {"answer": chosen.get("text"), "latency_ms": out["latency_ms"], "tools_used": [out["chosen"]]},
                             out["arms"], {"label": out["label"], "arms": [{k: a.get(k) for k in (
                                 "tier", "served_model", "latency_ms", "input_tokens", "output_tokens", "est_cost_usd")}
                                 for a in out["arms"]]})
    return out


class RateIn(BaseModel):
    positive: bool


@router.post("/runs/{run_id}/rating")
def rate(run_id: int, body: RateIn, u: auth.User = Depends(me_dep)):
    with db.tx(u.email, u.role) as cur:
        cur.execute("UPDATE scorecard.agent_run SET rating = %s WHERE run_id = %s AND user_email = %s",
                    (1 if body.positive else -1, run_id, u.email))
    return {"ok": True}


@router.get("/runs")
def runs(u: auth.User = Depends(me_dep)):
    with db.tx(u.email, u.role) as cur:
        cur.execute("""SELECT run_id, agent, question, tools_used, n_steps, n_citations, latency_ms, status, rating, created_at
                       FROM scorecard.agent_run WHERE user_email = %s ORDER BY created_at DESC LIMIT 25""", (u.email,))
        return {"runs": cur.fetchall()}
