"""Agents: catalog, normalised live traces and the model-routing lab. Every call runs on behalf of the signed-in user.

Supervisor ("Lochard Leadership Analyst") and Knowledge Assistant ("Iona Knowledge") are Agent Bricks endpoints that
speak the OpenAI Responses protocol. With stream=true they emit `response.output_item.done` per step (function_call,
sub-agent output, narration) and `response.output_text.delta` while text is generated. `stream_responses` turns
that into a small event vocabulary the UI renders as a trace:

  {"type": "step", "step": {...}}   one completed item (tool_call | tool_result | note | answer)
  {"type": "delta", "text": "..."}  text being generated right now
  {"type": "done", ...}             final answer, citations, latency

Genie Agents are driven through the Conversation API; their status transitions (FETCHING_METADATA → ASKING_AI →
EXECUTING_QUERY → COMPLETED) become the trace.
"""
from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Iterator

import requests

from . import config, genie

SUPERVISOR_ENDPOINT = os.environ.get("SUPERVISOR_ENDPOINT", "mas-14e8875b-endpoint")
KNOWLEDGE_ENDPOINT = os.environ.get("KNOWLEDGE_ENDPOINT", "ka-5d8cb9b9-endpoint")
SUPERVISOR_NAME = "Lochard Leadership Analyst"

TOOLS = {  # supervisor tool name -> (label, kind, catalog key)
    "exec_genie": ("Executive & Board Genie", "genie", "genie:executive"),
    "finance_genie": ("Finance Genie", "genie", "genie:finance"),
    "hse_genie": ("HSE Genie", "genie", "genie:hse"),
    "maintenance_genie": ("Maintenance Genie", "genie", "genie:maintenance"),
    "market_ops_genie": ("Gas Market & Iona Ops Genie", "genie", "genie:market"),
    "iona_knowledge": ("Iona Knowledge", "knowledge", "knowledge"),
}

TIERS = {  # key -> (UC model service, primary -> fallback, indicative USD per 1M tokens in/out)
    "economy": ("lochard_llm_economy", "Claude Haiku 4.5 → Gemini 3.8 Flash", (1.0, 5.0)),
    "standard": ("lochard_llm_standard", "Claude Sonnet 5 → GPT-5.5", (3.0, 15.0)),
    "premium": ("lochard_llm_premium", "Claude Opus 5.5 → GPT-6", (15.0, 75.0)),
}
ROUTE = {"LOOKUP": "economy", "ANALYTICAL": "standard", "STRATEGIC": "premium"}


def catalog() -> list[dict]:
    """What each agent is, what it can reach and how it is governed (static facts, rendered by the Agents page)."""
    g = config.GENIE_SPACES
    genie_desc = {
        "executive": "Cross-domain board view: scorecard (synced from this portal), finance, HSE, maintenance and market metric views.",
        "finance": "Budget, actuals, YEO and commitments by team / cost centre / project. FY = Jul–Jun.",
        "hse": "Observations, investigations, risk ranks and lagging indicators (TRIFR, HPE).",
        "maintenance": "Maximo weekly schedule snapshot: compliance, P1/P2, backlog, craft hours.",
        "market": "AEMO VIC demand and EDD (real nemweb data), Iona injections / withdrawals / inventory, forecasts.",
    }
    genie_examples = {
        "executive": ["Which scorecard KPIs are At Risk this month and why?", "Summarise FY27 performance across HSE, maintenance and finance"],
        "finance": ["Which teams have the largest gap between YEO and budget?", "What are HUGS actuals by month in FY27?"],
        "hse": ["How many open HIGH risk observations are there by plant area?", "Show the monthly observation trend for the last 12 months"],
        "maintenance": ["What is schedule compliance for the last 13 weeks?", "Which lead crafts have the most overdue safety critical work?"],
        "market": ["Compare Jan–Aug VIC demand across 2021–2024 in PJ", "What was Iona's inventory at the end of last month?"],
    }
    out = [
        {"key": "supervisor", "name": SUPERVISOR_NAME, "kind": "Supervisor Agent", "product": "Agent Bricks",
         "endpoint": SUPERVISOR_ENDPOINT,
         "summary": "Plans the question, calls the right specialists (Genie Agents for governed numbers, Iona Knowledge for "
                    "documents) and composes one board-ready answer with sources.",
         "tools": [v[0] for v in TOOLS.values()], "identity": "On behalf of you – every Genie sub-call runs with your Unity Catalog permissions.",
         "examples": ["Why is HSE Performance At Risk and what do our procedures say about isolation before compressor work?",
                      "Give me a board summary of maintenance performance and the HUGS project cost position",
                      "How does VIC demand this winter compare with last year, and what does that mean for Iona?"]},
        {"key": "knowledge", "name": "Iona Knowledge", "kind": "Knowledge Assistant", "product": "Agent Bricks",
         "endpoint": KNOWLEDGE_ENDPOINT,
         "summary": "Retrieval-augmented answers over Iona maintenance procedures, OEM manuals, isolation / permit standards "
                    "and board papers, parsed by ai_parse_document in the documents pipeline. Every sentence is cited.",
         "tools": ["Vector Search over lochard_landing.documents (maintenance_procedures, board_papers)"],
         "identity": "Answers only from indexed documents; never invents torque values or pressures.",
         "examples": ["What are the isolation steps before compressor maintenance?",
                      "Summarise the safety controls in the wellhead maintenance procedure",
                      "What did the August 2026 board report say about HUGS?"]},
    ]
    for k, (_, title) in g.items():
        out.append({"key": f"genie:{k}", "name": title, "kind": "Genie Agent", "product": "AI/BI Genie",
                    "summary": genie_desc.get(k, ""), "tools": ["Text-to-SQL over UC metric views and gold tables",
                                                               "Trusted example SQL + benchmarks"],
                    "identity": "Runs SQL as you on the serverless warehouse – ABAC row filters and masks apply.",
                    "examples": genie_examples.get(k, [])})
    out.append({"key": "router", "name": "Model routing lab", "kind": "Unity AI Gateway", "product": "Model services",
                "summary": "The economy tier classifies the question (LOOKUP / ANALYTICAL / STRATEGIC) and routes it to the "
                           "cheapest adequate tier. Compare all three tiers side by side on cost, latency and answer.",
                "tools": [f"{v[0]} ({v[1]})" for v in TIERS.values()],
                "identity": "Rate limits, fallbacks, usage tracking and inference tables on every call.",
                "examples": ["Which scorecard KPIs are At Risk?", "Is the FY27 weighted scorecard on track overall?",
                             "Draft a three-sentence board summary of this month's scorecard"]})
    return out


# ------------------------------------------------------------------------------------------ Responses-API agents
_NAME = re.compile(r"^\s*<name>(.+?)</name>\s*$", re.S)
_FOOTDEF = re.compile(r"^\[\^([\w-]+)\]:\s*(.*?)\s*\[([^\]]+)\]\((\S+?)\)\s*$", re.M)
_FOOTREF = re.compile(r"\[\^([\w-]+)\]")


def _citations_from_footnotes(text: str, cites: list[dict]) -> str:
    """Supervisor sub-agent output carries markdown footnotes; lift them into numbered citations."""
    defs = {m.group(1): (m.group(2), m.group(3), m.group(4)) for m in _FOOTDEF.finditer(text)}
    if not defs:
        return text
    body = _FOOTDEF.sub("", text).rstrip()
    idx: dict[str, int] = {}
    for ref, (quote, title, url) in defs.items():
        cites.append({"n": len(cites) + 1, "title": title, "url": url, "quote": quote})
        idx[ref] = len(cites)
    return _FOOTREF.sub(lambda m: f"[{idx[m.group(1)]}]" if m.group(1) in idx else "", body)


def _message_text(item: dict, cites: list[dict]) -> str:
    """Join output_text parts; url_citation annotations (Knowledge Assistant) become [n] markers."""
    parts = []
    for c in item.get("content") or []:
        t = c.get("text") or ""
        marks = []
        for a in c.get("annotations") or []:
            if a.get("type") == "url_citation":
                hit = next((x for x in cites if x["url"] == a.get("url")), None)
                if not hit:
                    hit = {"n": len(cites) + 1, "title": a.get("title") or "source", "url": a.get("url"), "quote": t.strip()}
                    cites.append(hit)
                marks.append(f"[{hit['n']}]")
        parts.append(t + "".join(marks))
    return "".join(parts)


def _md_table(text: str) -> dict | None:
    """Genie tool output arrives as a pandas-style markdown table (leading index column)."""
    lines = [l for l in text.strip().splitlines() if l.strip().startswith("|")]
    if len(lines) < 3 or not re.match(r"^\|[\s:|-]+\|?$", lines[1].strip()):
        return None
    def split(l: str) -> list[str]:  # one outer pipe each side – "||a|b|" keeps its empty index header
        l = l.strip()
        l = l[1:] if l.startswith("|") else l
        l = l[:-1] if l.endswith("|") else l
        return [c.strip() for c in l.split("|")]
    cols = split(lines[0])
    rows = [split(l) for l in lines[2:]]
    if cols and cols[0] == "":  # drop the pandas index
        cols, rows = cols[1:], [r[1:] for r in rows]
    return {"columns": cols, "rows": rows[:100]}


def _auth_headers(user_token: str | None) -> dict:
    h = config.user_client(user_token).config.authenticate()
    h["Content-Type"] = "application/json"
    return h


def stream_responses(user_token: str | None, agent: str, messages: list[dict]) -> Iterator[dict]:
    endpoint = SUPERVISOR_ENDPOINT if agent == "supervisor" else KNOWLEDGE_ENDPOINT
    t0 = time.time()
    yield {"type": "start", "agent": agent, "endpoint": endpoint}
    try:
        r = requests.post(f"{config.host()}/serving-endpoints/{endpoint}/invocations", headers=_auth_headers(user_token),
                          json={"input": messages, "stream": True}, stream=True, timeout=(20, 300))
    except requests.RequestException as e:
        yield {"type": "error", "error": str(e)[:300]}
        return
    if r.status_code != 200:
        yield {"type": "error", "error": f"{r.status_code}: {r.text[:300]}"}
        return
    speaker = SUPERVISOR_NAME if agent == "supervisor" else "Iona Knowledge"
    cites: list[dict] = []
    steps: list[dict] = []
    pending_call: dict | None = None
    for raw in r.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        payload = raw[5:].strip()
        if payload == "[DONE]":
            break
        try:
            ev = json.loads(payload)
        except ValueError:
            continue
        et = ev.get("type")
        if et == "response.output_text.delta":
            yield {"type": "delta", "text": ev.get("delta", ""), "speaker": speaker}
            continue
        if et != "response.output_item.done":
            continue
        item = ev.get("item") or {}
        ms = int((time.time() - t0) * 1000)
        if item.get("type") == "function_call":
            label, kind, key = TOOLS.get(item.get("name"), (item.get("name"), "tool", None))
            try:
                args = json.loads(item.get("arguments") or "{}")
            except ValueError:
                args = {"raw": item.get("arguments")}
            query = next((v for v in args.values() if isinstance(v, str)), None)
            pending_call = {"kind": "tool_call", "tool": item.get("name"), "label": label, "tool_kind": kind,
                            "catalog_key": key, "query": query, "arguments": args, "at_ms": ms}
            steps.append(pending_call)
            yield {"type": "step", "step": pending_call}
            continue
        if item.get("type") != "message":
            continue
        text = _message_text(item, cites)
        m = _NAME.match(text)
        if m:
            speaker = m.group(1).strip()
            continue
        if not text.strip():
            continue
        if agent == "supervisor" and speaker != SUPERVISOR_NAME:
            body = _citations_from_footnotes(text, cites)
            step = {"kind": "tool_result", "agent": TOOLS.get(speaker, (speaker,))[0], "tool": (pending_call or {}).get("tool"),
                    "text": body.strip(), "table": _md_table(body), "at_ms": ms,
                    "elapsed_ms": ms - (pending_call or {}).get("at_ms", ms)}
        else:
            step = {"kind": "note", "agent": speaker, "text": _citations_from_footnotes(text, cites).strip(), "at_ms": ms}
        steps.append(step)
        yield {"type": "step", "step": step}
    if agent == "knowledge" and cites:
        docs = list(dict.fromkeys(c["title"] for c in cites))
        step = {"kind": "retrieval", "text": f"Retrieved {len(cites)} cited passages from {len(docs)} document"
                                              f"{'s' if len(docs) > 1 else ''}: {', '.join(docs[:6])}",
                "at_ms": int((time.time() - t0) * 1000)}
        steps.insert(0, step)
        yield {"type": "step", "step": step}
    # the last narration from the top-level agent is the answer
    answer = next((s for s in reversed(steps) if s["kind"] == "note"), None)
    if answer:
        answer["kind"] = "answer"
    yield {"type": "done", "answer": answer["text"] if answer else None, "citations": cites,
           "latency_ms": int((time.time() - t0) * 1000),
           "tools_used": list(dict.fromkeys(s["tool"] for s in steps if s["kind"] == "tool_call"))}


# ------------------------------------------------------------------------------------------ Genie Agents
GENIE_STATUS = {
    "SUBMITTED": "Question received", "FILTERING_CONTEXT": "Selecting relevant tables and metric views",
    "FETCHING_METADATA": "Reading Unity Catalog metadata, instructions and trusted SQL",
    "ASKING_AI": "Writing SQL", "PENDING_WAREHOUSE": "Waiting for the SQL warehouse",
    "EXECUTING_QUERY": "Running SQL on the serverless warehouse (as you)", "COMPLETED": "Answer ready",
    "FAILED": "Failed", "CANCELLED": "Cancelled",
}


def stream_genie(user_token: str | None, key: str, question: str, conversation_id: str | None) -> Iterator[dict]:
    t0 = time.time()
    sp = genie.spaces(user_token)
    if key not in sp:
        yield {"type": "error", "error": f"Genie Agent '{key}' is not available to you"}
        return
    space_id = sp[key]["space_id"]
    yield {"type": "start", "agent": f"genie:{key}", "space_id": space_id}
    w = config.user_client(user_token)
    try:
        msg = (w.genie.create_message(space_id, conversation_id, question) if conversation_id
               else w.genie.start_conversation(space_id, question)).response
    except Exception as e:  # noqa: BLE001
        yield {"type": "error", "error": str(e)[:300]}
        return
    conv_id, msg_id = msg.conversation_id, (msg.message_id or msg.id)
    last, delay = None, 0.8
    while time.time() - t0 < 150:
        m = w.genie.get_message(space_id, conv_id, msg_id)
        st = m.status.value if m.status else ""
        if st in ("COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"):
            break
        if st != last:
            last = st
            yield {"type": "step", "step": {"kind": "status", "status": st, "text": GENIE_STATUS.get(st, st.title()),
                                            "at_ms": int((time.time() - t0) * 1000)}}
        time.sleep(delay)
        delay = min(delay * 1.4, 3)
    out = genie.ask_result(w, space_id, conv_id, msg_id, m)
    if out.get("sql"):
        yield {"type": "step", "step": {"kind": "sql", "text": out.get("description"), "sql": out["sql"],
                                        "table": {"columns": out["columns"], "rows": out["rows"][:100]} if out["columns"] else None,
                                        "at_ms": int((time.time() - t0) * 1000)}}
    yield {"type": "step", "step": {"kind": "status", "status": st, "text": GENIE_STATUS.get(st, st.title()),
                                    "at_ms": int((time.time() - t0) * 1000)}}
    yield {"type": "done", "answer": out.get("text") or out.get("description"), "citations": [],
           "conversation_id": conv_id, "message_id": msg_id, "space_id": space_id, "status": out["status"],
           "suggested": out.get("suggested", []), "error": out.get("error"),
           "latency_ms": int((time.time() - t0) * 1000)}


# ------------------------------------------------------------------------------------------ Model routing lab
def _gateway_chat(user_token: str | None, service: str, messages: list[dict], tags: dict, max_tokens=1500) -> dict:
    url = f"{config.AI_GATEWAY_URL.rstrip('/')}/chat/completions"
    body = {"model": f"{config.CATALOG}.lochard_ai.{service}", "messages": messages, "max_tokens": max_tokens}
    t0 = time.time()
    for token in ([user_token] if user_token else []) + [None]:  # user first (usage attributed to them), then app SP
        h = _auth_headers(token)
        h["Databricks-Ai-Gateway-Request-Tags"] = json.dumps(tags)
        try:
            r = requests.post(url, headers=h, json=body, timeout=120)
        except requests.RequestException as e:
            err = str(e)
            continue
        if r.status_code == 200:
            d = r.json()
            c = d["choices"][0]["message"].get("content")
            if isinstance(c, list):
                c = "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") in ("text", "output_text"))
            u = d.get("usage") or {}
            return {"text": c or "", "served_model": d.get("model"), "input_tokens": u.get("prompt_tokens", 0),
                    "output_tokens": u.get("completion_tokens", 0), "latency_ms": int((time.time() - t0) * 1000),
                    "identity": "you" if token else "app service principal"}
        err = f"{r.status_code}: {r.text[:200]}"
    return {"error": err, "latency_ms": int((time.time() - t0) * 1000)}


def _cost(tier: str, res: dict) -> float | None:
    if "error" in res:
        return None
    pin, pout = TIERS[tier][2]
    return round(res["input_tokens"] / 1e6 * pin + res["output_tokens"] / 1e6 * pout, 6)


LAB_SYSTEM = ("You are the Lochard Energy leadership analyst. Answer ONLY from the scorecard facts provided; if a fact is "
              "missing, say which Lochard Genie Agent would have it. Use AUD and the Australian financial year "
              "(FY2027 = Jul-26..Jun-27). Never name individuals. Be concise.")


def routing_lab(user_token: str | None, question: str, facts: str, compare: bool = True) -> dict:
    t0 = time.time()
    run = f"lab-{int(t0)}"
    cls = _gateway_chat(user_token, TIERS["economy"][0], [{"role": "user", "content":
                        "Classify this leadership question as LOOKUP (single fact), ANALYTICAL (compare / explain) or "
                        f"STRATEGIC (judgement / narrative). Reply with one word, then ' - ' and a reason of at most 12 words."
                        f"\n\n{question}"}], {"app": "board_portal", "feature": "routing_lab", "arm": "classifier", "run": run},
                        max_tokens=200)
    label = next((k for k in ROUTE if k in (cls.get("text") or "").upper()), "ANALYTICAL")
    chosen = ROUTE[label]
    msgs = [{"role": "system", "content": LAB_SYSTEM},
            {"role": "user", "content": f"SCORECARD FACTS:\n{facts}\n\nQUESTION: {question}"}]
    tiers = list(TIERS) if compare else [chosen]
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {t: ex.submit(_gateway_chat, user_token, TIERS[t][0], msgs,
                             {"app": "board_portal", "feature": "routing_lab", "arm": t, "run": run}) for t in tiers}
        res = {t: f.result() for t, f in futs.items()}
    cls_cost = _cost("economy", cls) or 0.0
    arms = [{"tier": t, "service": TIERS[t][0], "chain": TIERS[t][1], "chosen": t == chosen, **res[t],
             "est_cost_usd": _cost(t, res[t])} for t in tiers]
    return {"question": question, "label": label, "reason": (cls.get("text") or "").split("-", 1)[-1].strip()[:160],
            "chosen": chosen, "classifier": {k: cls.get(k) for k in ("served_model", "latency_ms", "input_tokens",
                                                                     "output_tokens", "error")},
            "classifier_cost_usd": round(cls_cost, 6), "arms": arms, "latency_ms": int((time.time() - t0) * 1000)}
