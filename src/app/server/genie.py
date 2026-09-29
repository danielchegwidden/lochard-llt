"""Genie Agents (formerly Genie spaces) via the Conversation API, on behalf of the user (answers respect ABAC)."""
from __future__ import annotations

import os
import time

from . import config

_space_cache: dict = {"t": 0, "spaces": {}}


def spaces(user_token: str | None) -> dict[str, dict]:
    """key -> {space_id, title}. Env vars win; otherwise discover Lochard Genie Agents by title."""
    if time.time() - _space_cache["t"] < 300 and _space_cache["spaces"]:
        return _space_cache["spaces"]
    found = {}
    try:
        listing = {s.title: s.space_id for s in config.user_client(user_token).genie.list_spaces().spaces or []}
    except Exception:  # noqa: BLE001
        listing = {}
    for key, (env, title) in config.GENIE_SPACES.items():
        sid = os.environ.get(env) or listing.get(title)
        if sid:
            found[key] = {"space_id": sid, "title": title}
    _space_cache.update(t=time.time(), spaces=found)
    return found


def ask(user_token: str | None, space_id: str, question: str, conversation_id: str | None = None,
        timeout_s: int = 120) -> dict:
    w = config.user_client(user_token)
    if conversation_id:
        msg = w.genie.create_message(space_id, conversation_id, question).response
    else:
        msg = w.genie.start_conversation(space_id, question).response
    conv_id, msg_id = msg.conversation_id, (msg.message_id or msg.id)
    deadline, delay = time.time() + timeout_s, 1.0
    while True:
        m = w.genie.get_message(space_id, conv_id, msg_id)
        st = m.status.value if m.status else ""
        if st in ("COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED") or time.time() > deadline:
            break
        time.sleep(delay)
        delay = min(delay * 1.5, 5)
    return ask_result(w, space_id, conv_id, msg_id, m)


def ask_result(w, space_id: str, conv_id: str, msg_id: str, m) -> dict:
    """Text, SQL, result rows and suggested follow-ups from a finished Genie message."""
    st = m.status.value if m.status else ""
    out = {"conversation_id": conv_id, "message_id": msg_id, "status": st, "text": None, "sql": None,
           "description": None, "columns": [], "rows": [], "suggested": []}
    if m.error:
        out["error"] = getattr(m.error, "error", None) or str(m.error)
    for a in m.attachments or []:
        if a.text and a.text.content:
            out["text"] = a.text.content
        if a.query:
            out["sql"] = a.query.query
            out["description"] = a.query.description
            try:
                r = w.genie.get_message_attachment_query_result(space_id, conv_id, msg_id, a.attachment_id)
                sr = r.statement_response
                if sr and sr.manifest and sr.manifest.schema:
                    out["columns"] = [c.name for c in sr.manifest.schema.columns or []]
                if sr and sr.result and sr.result.data_array:
                    out["rows"] = sr.result.data_array[:200]
            except Exception as e:  # noqa: BLE001
                out["result_error"] = str(e)[:200]
        if getattr(a, "suggested_questions", None) and a.suggested_questions.questions:
            out["suggested"] = list(a.suggested_questions.questions)
    return out


def feedback(user_token: str | None, space_id: str, conversation_id: str, message_id: str, positive: bool):
    from databricks.sdk.service.dashboards import GenieFeedbackRating
    w = config.user_client(user_token)
    w.genie.send_message_feedback(space_id, conversation_id, message_id,
                                  GenieFeedbackRating.POSITIVE if positive else GenieFeedbackRating.NEGATIVE)


SUPERVISOR_ENDPOINT = os.environ.get("SUPERVISOR_ENDPOINT", "")


def ask_supervisor(user_token: str | None, question: str, timeout_s: int = 240) -> dict:
    """Agent Bricks Supervisor Agent ("Lochard Leadership Analyst") on behalf of the user: it routes to the domain
    Genie Agents + Iona Knowledge and composes a board-ready answer. Returns the same shape as ask()."""
    import requests
    w = config.user_client(user_token)
    headers = w.config.authenticate()
    headers["Content-Type"] = "application/json"
    r = requests.post(f"{config.host()}/serving-endpoints/{SUPERVISOR_ENDPOINT}/invocations", headers=headers,
                      json={"input": [{"role": "user", "content": question}]}, timeout=timeout_s)
    out = {"conversation_id": None, "message_id": None, "status": "COMPLETED", "text": None, "sql": None,
           "description": None, "columns": [], "rows": [], "suggested": [], "tools": []}
    if r.status_code != 200:
        out.update(status="FAILED", error=r.text[:300])
        return out
    texts = []
    for o in r.json().get("output", []):
        if o.get("type") == "function_call":
            out["tools"].append(o.get("name"))
        elif o.get("type") == "message":
            for c in o.get("content", []):
                if c.get("type") == "output_text" and not c.get("text", "").startswith("<name>"):
                    texts.append(c["text"])
    out["text"] = texts[-1] if texts else None
    out["description"] = ("Routed to: " + ", ".join(dict.fromkeys(out["tools"]))) if out["tools"] else None
    return out
