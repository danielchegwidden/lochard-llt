"""Market Intelligence Analyst – a tool-calling agent that writes Lochard's weekly market brief.

For each week the agent works like an analyst: it lists the week's enriched items, reads the important ones in full,
checks how often entities have featured in recent weeks, looks at last week's brief for continuity and at Lochard's
own position (Iona inventory, Victorian demand, HUGS cost), then submits a structured brief through `submit_brief`.
Only items it has actually seen may be cited; counts and sentiment are computed from the data, not by the model.

Output: {catalog}.{prefix}ai.market_intel_brief (MERGE on week_start), read by lochard_semantic.v_market_intel_briefs.
Traces: MLflow experiment (--experiment), one trace per brief; the trace id is stored with the brief.

Usage (job task or locally with a CLI profile):
  analyst_agent.py --catalog <c> --prefix lochard_ --mode daily|backfill --weeks 26 [--week 2026-09-21] [--force]
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import requests

AEST = timezone(timedelta(hours=10))
GROUPS = ["Lochard", "Customer", "Competitor", "Upstream supplier", "Regulator & market body", "Government & policy",
          "Industry & market"]
SIGNALS = ["Opportunity", "Threat", "Watch", "Neutral"]
MAX_STEPS = 16


# ------------------------------------------------------------------------------------------------ SQL (Spark or warehouse)
class Sql:
    def __init__(self, profile: str | None):
        self.spark = None
        try:
            from pyspark.sql import SparkSession
            if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
                self.spark = SparkSession.builder.getOrCreate()
        except ImportError:
            pass
        from databricks.sdk import WorkspaceClient
        self.w = WorkspaceClient() if os.environ.get("DATABRICKS_RUNTIME_VERSION") else WorkspaceClient(profile=profile)
        self.wh = None

    def q(self, stmt: str, params: dict | None = None) -> list[dict]:
        if self.spark is not None:
            return [r.asDict(recursive=True) for r in self.spark.sql(stmt, args=params or {}).collect()]
        from databricks.sdk.service.sql import StatementParameterListItem, StatementState
        if not self.wh:
            self.wh = next(w.id for w in self.w.warehouses.list() if w.name == "lochard-serverless-wh")
        r = self.w.statement_execution.execute_statement(
            statement=stmt, warehouse_id=self.wh, wait_timeout="50s",
            parameters=[StatementParameterListItem(name=k, value=None if v is None else str(v)) for k, v in (params or {}).items()] or None)
        while r.status.state in (StatementState.PENDING, StatementState.RUNNING):
            time.sleep(2)
            r = self.w.statement_execution.get_statement(r.statement_id)
        if r.status.state != StatementState.SUCCEEDED:
            raise RuntimeError(r.status.error.message if r.status.error else str(r.status))
        cols = [c.name for c in (r.manifest.schema.columns or [])] if r.manifest and r.manifest.schema else []
        return [dict(zip(cols, row)) for row in ((r.result.data_array if r.result else None) or [])]


# ------------------------------------------------------------------------------------------------ tools
class Tools:
    def __init__(self, sql: Sql, cat: str, prefix: str, week: date):
        self.sql, self.week, self.end = sql, week, week + timedelta(days=6)
        self.gold, self.sem, self.silver = f"{cat}.{prefix}gold", f"{cat}.{prefix}semantic", f"{cat}.{prefix}silver"
        self.seen: set[str] = set()
        self.used: list[str] = []

    SPECS = [
        {"name": "list_items", "description": "List this week's market intelligence items (most important first). "
         "Returns id, date, title, publisher, entity group, primary entity, topic, signal, importance and a one-line summary.",
         "parameters": {"type": "object", "properties": {
             "entity_group": {"type": "string", "enum": GROUPS}, "topic": {"type": "string"},
             "min_importance": {"type": "integer", "minimum": 1, "maximum": 5}, "limit": {"type": "integer", "maximum": 60}}}},
        {"name": "read_item", "description": "Read one item in full: summary, why it matters, entities and up to 4,000 characters of source text.",
         "parameters": {"type": "object", "properties": {"item_id": {"type": "string"}}, "required": ["item_id"]}},
        {"name": "search_items", "description": "Keyword search over titles and summaries of items from this week and the three weeks before.",
         "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
        {"name": "entity_trend", "description": "How often an entity featured, and its average sentiment, in each of the last 8 weeks.",
         "parameters": {"type": "object", "properties": {"entity": {"type": "string"}}, "required": ["entity"]}},
        {"name": "prior_brief", "description": "Last week's brief (headline, key developments, watchlist) for continuity.",
         "parameters": {"type": "object", "properties": {}}},
        {"name": "internal_context", "description": "Lochard's own position this week: Iona inventory and fill, withdrawals and "
         "injections, Victorian gas demand vs the same week last year, and HUGS project cost vs the revised P50 budget.",
         "parameters": {"type": "object", "properties": {}}},
        {"name": "submit_brief", "description": "Submit the finished weekly brief. Call exactly once, at the end.",
         "parameters": {"type": "object", "required": ["headline", "summary_md", "developments", "implications", "watchlist", "actions"],
                        "properties": {
             "headline": {"type": "string", "description": "at most 15 words"},
             "summary_md": {"type": "string", "description": "3-6 sentence executive summary for Lochard's leaders"},
             "developments": {"type": "array", "minItems": 1, "maxItems": 6, "items": {"type": "object",
                              "required": ["title", "detail", "signal", "entity_group", "importance", "item_ids"],
                              "properties": {"title": {"type": "string"}, "detail": {"type": "string"},
                                             "signal": {"type": "string", "enum": SIGNALS},
                                             "entity_group": {"type": "string", "enum": GROUPS},
                                             "importance": {"type": "integer", "minimum": 1, "maximum": 5},
                                             "item_ids": {"type": "array", "items": {"type": "string"}}}}},
             "implications": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
             "watchlist": {"type": "array", "maxItems": 5, "items": {"type": "object", "required": ["entity", "note", "direction"],
                           "properties": {"entity": {"type": "string"}, "note": {"type": "string"},
                                          "direction": {"type": "string", "enum": ["up", "down", "flat"]}}}},
             "actions": {"type": "array", "maxItems": 4, "items": {"type": "object", "required": ["action", "owner_role"],
                         "properties": {"action": {"type": "string"}, "owner_role": {"type": "string"}}}}}}},
    ]

    def _p(self):
        return {"ws": self.week.isoformat(), "we": self.end.isoformat()}

    def list_items(self, entity_group=None, topic=None, min_importance=1, limit=40):
        rows = self.sql.q(f"""SELECT item_id, CAST(published_date AS STRING) AS d, title, source_name AS publisher, entity_group,
                                     primary_entity, topic, signal, importance, summary
                              FROM {self.gold}.fact_market_intel_item
                              WHERE week_start = DATE(:ws) AND relevance >= 1 AND importance >= :mi
                                AND (:g IS NULL OR entity_group = :g) AND (:t IS NULL OR topic = :t)
                              ORDER BY importance DESC, relevance DESC, published_at DESC LIMIT {int(min(limit or 40, 60))}""",
                          {**self._p(), "mi": int(min_importance or 1), "g": entity_group, "t": topic})
        self.seen.update(r["item_id"] for r in rows)
        return rows

    def read_item(self, item_id):
        rows = self.sql.q(f"""SELECT f.item_id, f.title, f.source_name, f.source_type, f.url, CAST(f.published_date AS STRING) AS d,
                                     f.summary, f.why_it_matters, f.entities, f.entity_group, f.topic, f.signal, f.sentiment,
                                     f.importance, left(coalesce(s.body, f.excerpt), 4000) AS text
                              FROM {self.gold}.fact_market_intel_item f
                              LEFT JOIN {self.silver}.slv_mi_items_enriched s ON s.item_id = f.item_id
                              WHERE f.item_id = :id LIMIT 1""", {"id": item_id})
        if rows:
            self.seen.add(item_id)
        return rows[0] if rows else {"error": "unknown item_id"}

    def search_items(self, query):
        rows = self.sql.q(f"""SELECT item_id, CAST(published_date AS STRING) AS d, title, source_name AS publisher, signal, importance
                              FROM {self.gold}.fact_market_intel_item
                              WHERE week_start BETWEEN date_sub(DATE(:ws), 21) AND DATE(:ws) AND relevance >= 1
                                AND (lower(title) LIKE lower(:q) OR lower(summary) LIKE lower(:q))
                              ORDER BY published_at DESC LIMIT 25""", {**self._p(), "q": f"%{query}%"})
        self.seen.update(r["item_id"] for r in rows if r["d"] >= self.week.isoformat())
        return rows

    def entity_trend(self, entity):
        return self.sql.q(f"""SELECT CAST(week_start AS STRING) AS week, count(*) AS items, round(avg(sentiment), 2) AS avg_sentiment,
                                     count_if(signal = 'Threat') AS threats, count_if(signal = 'Opportunity') AS opportunities
                              FROM {self.gold}.fact_market_intel_item
                              WHERE relevance >= 1 AND array_contains(entities, :e)
                                AND week_start BETWEEN date_sub(DATE(:ws), 49) AND DATE(:ws)
                              GROUP BY week_start ORDER BY week_start""", {**self._p(), "e": entity})

    def prior_brief(self):
        rows = self.sql.q(f"""SELECT CAST(week_start AS STRING) AS week, headline, developments_json, watchlist_json
                              FROM {self.sem}.v_market_intel_briefs WHERE week_start = date_sub(DATE(:ws), 7)""", self._p())
        return rows[0] if rows else {"note": "no brief for the previous week"}

    def internal_context(self):
        s = self.sem
        rows = self.sql.q(f"""
            SELECT (SELECT max_by(inventory_pj, gas_date) FROM {s}.v_iona_operations_daily WHERE gas_date <= DATE(:we)) AS iona_inventory_pj,
                   (SELECT max_by(inventory_fill_pct, gas_date) FROM {s}.v_iona_operations_daily WHERE gas_date <= DATE(:we)) AS iona_fill_pct,
                   (SELECT round(SUM(withdrawal_tj), 1) FROM {s}.v_iona_operations_daily WHERE gas_date BETWEEN DATE(:ws) AND DATE(:we)) AS iona_withdrawals_tj,
                   (SELECT round(SUM(injection_tj), 1) FROM {s}.v_iona_operations_daily WHERE gas_date BETWEEN DATE(:ws) AND DATE(:we)) AS iona_injections_tj,
                   (SELECT round(SUM(total_gas_used_pj), 2) FROM {s}.v_vic_gas_demand_daily WHERE gas_date BETWEEN DATE(:ws) AND DATE(:we)) AS vic_demand_pj,
                   (SELECT round(SUM(total_gas_used_pj), 2) FROM {s}.v_vic_gas_demand_daily
                      WHERE gas_date BETWEEN add_months(DATE(:ws), -12) AND add_months(DATE(:we), -12)) AS vic_demand_same_week_last_year_pj,
                   (SELECT round(avg(market_price_gj), 2) FROM {s}.v_iona_operations_daily WHERE gas_date BETWEEN DATE(:ws) AND DATE(:we)) AS avg_market_price_gj,
                   (SELECT round((SUM(CASE WHEN financial_year < 'FY2027' THEN actual_amount ELSE 0 END)
                                  + SUM(CASE WHEN financial_year = 'FY2027' THEN yeo_amount ELSE 0 END)) / 1e6, 1)
                      FROM {s}.v_finance_monthly WHERE cc_short_name = 'HUGS') AS hugs_estimate_at_completion_aud_millions,
                   112.4 AS hugs_revised_p50_budget_aud_millions""", self._p())
        out = rows[0] if rows else {}
        out["note"] = ("All money is Australian dollars (AUD). Operational data may lag the market news by a few days; "
                       "inventory_pj is petajoules, flows are terajoules (TJ).")
        return out


def _call(tools: Tools, name: str, args: dict):
    fn = getattr(tools, name, None)
    if not fn or name == "submit_brief":
        return {"error": f"unknown tool {name}"}
    try:
        return fn(**args)
    except Exception as e:  # noqa: BLE001 – report tool errors back to the model
        return {"error": str(e)[:300]}


# ------------------------------------------------------------------------------------------------ model
class Model:
    def __init__(self, sql: Sql, endpoint: str):
        self.w, self.endpoint = sql.w, endpoint

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        h = self.w.config.authenticate()
        h["Content-Type"] = "application/json"
        body = {"messages": messages, "max_tokens": 4000,
                "tools": [{"type": "function", "function": t} for t in tools]}
        for attempt in range(4):
            r = requests.post(f"{self.w.config.host.rstrip('/')}/serving-endpoints/{self.endpoint}/invocations",
                              headers=h, json=body, timeout=300)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(10 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return {}


def _text(content) -> str:
    if isinstance(content, list):   # reasoning models return content blocks
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") in ("text", "output_text"))
    return content or ""


SYSTEM = """You are the Market Intelligence Analyst for Lochard Energy, owner and operator of the Iona underground gas
storage facility near Port Campbell, Victoria. Lochard is delivering the Heytesbury Underground Gas Storage (HUGS)
project (more inventory and withdrawal capacity from 2027) and plans a further Iona expansion. Storage is most valuable
when east-coast winter supply is tight; LNG import terminals and other storage compete for the same winter peak role;
South West Pipeline capacity constrains growth. Known Iona storage customers include AGL and Snowy Hydro.

Write the weekly market intelligence brief for Lochard's leadership team for the week {start} to {end}.
Work like an analyst:
1. list_items (start with min_importance 3, then scan the rest) – there are {n} relevant items this week;
2. read_item for the 4-8 items that matter most to Lochard;
3. entity_trend for entities that feature strongly, prior_brief for continuity, internal_context for Lochard's position;
4. submit_brief once.
Rules: cite only item_ids returned by your tools; never invent facts, dates or numbers; say plainly when the week is
quiet; group related items into one development; importance 5 = board-level for Lochard. Australian English, concise,
no hype. Actions must be practical and owned by a role (e.g. CEO, Commercial Manager, Head of Regulatory Affairs,
Operations Manager, Project Director HUGS)."""


def _clean_brief(args: dict) -> tuple[dict, str | None]:
    """Models occasionally send list fields as JSON-encoded strings; decode them and check the brief is complete."""
    b = dict(args)
    for k in ("developments", "implications", "watchlist", "actions"):
        v = b.get(k)
        if isinstance(v, str):
            try:
                b[k] = json.loads(v)
            except ValueError:
                return b, f"{k} must be a JSON array, not text"
        if not isinstance(b.get(k) or [], list):
            return b, f"{k} must be an array"
        b[k] = [x for x in (b.get(k) or []) if isinstance(x, (dict, str))]
    if not b.get("developments"):
        return b, "a brief needs at least one development citing item_ids you have seen"
    if not (b.get("headline") and b.get("summary_md")):
        return b, "headline and summary_md are required"
    return b, None


def write_brief(sql: Sql, cat: str, prefix: str, tools: Tools, model_name: str, trace_id: str | None, steps: int) -> dict:
    wk = tools.week
    b = tools.brief
    valid = {r["item_id"] for r in sql.q(f"SELECT item_id FROM {tools.gold}.fact_market_intel_item WHERE week_start BETWEEN "
                                         f"date_sub(DATE(:ws), 21) AND DATE(:ws) AND relevance >= 1", {"ws": wk.isoformat()})}
    for d in b.get("developments", []):
        d["item_ids"] = [i for i in (d.get("item_ids") or []) if i in valid][:8]
    stats = sql.q(f"""SELECT count(*) AS n, count(DISTINCT source_name) AS s FROM {tools.gold}.fact_market_intel_item
                      WHERE week_start = DATE(:ws) AND relevance >= 1""", {"ws": wk.isoformat()})[0]
    sent = {r["entity_group"]: round(float(r["v"]), 2) for r in sql.q(
        f"""SELECT entity_group, avg(sentiment) AS v FROM {tools.gold}.fact_market_intel_item
            WHERE week_start = DATE(:ws) AND relevance >= 1 GROUP BY entity_group""", {"ws": wk.isoformat()}) if r["v"] is not None}
    ai = f"{cat}.{prefix}ai.market_intel_brief"
    sql.q(f"""MERGE INTO {ai} t USING (SELECT DATE(:ws) AS week_start) s ON t.week_start = s.week_start
              WHEN MATCHED THEN UPDATE SET week_end = DATE(:we), headline = :h, summary_md = :sm, developments_json = :dev,
                   implications_json = :imp, watchlist_json = :wl, actions_json = :act, sentiment_json = :sent, n_items = CAST(:n AS INT),
                   n_sources = CAST(:ns AS INT), model = :m, tools_used = from_json(:tu, 'ARRAY<STRING>'), trace_id = :tr,
                   agent_steps = CAST(:st AS INT), generated_at = current_timestamp()
              WHEN NOT MATCHED THEN INSERT (week_start, week_end, headline, summary_md, developments_json, implications_json,
                   watchlist_json, actions_json, sentiment_json, n_items, n_sources, model, tools_used, trace_id, agent_steps, generated_at)
              VALUES (DATE(:ws), DATE(:we), :h, :sm, :dev, :imp, :wl, :act, :sent, CAST(:n AS INT), CAST(:ns AS INT), :m,
                      from_json(:tu, 'ARRAY<STRING>'), :tr, CAST(:st AS INT), current_timestamp())""",
          {"ws": wk.isoformat(), "we": tools.end.isoformat(), "h": b.get("headline", ""), "sm": b.get("summary_md", ""),
           "dev": json.dumps(b.get("developments", [])), "imp": json.dumps(b.get("implications", [])),
           "wl": json.dumps(b.get("watchlist", [])), "act": json.dumps(b.get("actions", [])), "sent": json.dumps(sent),
           "n": stats["n"], "ns": stats["s"], "m": model_name, "tu": json.dumps(sorted(set(tools.used))),
           "tr": trace_id, "st": steps})
    return {"week": wk.isoformat(), "items": stats["n"], "developments": len(b.get("developments", []))}


def run_week(sql: Sql, model: Model, cat: str, prefix: str, wk: date, n_items: int, tracer) -> dict:
    tools = Tools(sql, cat, prefix, wk)
    tools.brief = None
    msgs = [{"role": "system", "content": SYSTEM.format(start=f"{wk:%a %d %b %Y}", end=f"{wk + timedelta(days=6):%a %d %b %Y}", n=n_items)},
            {"role": "user", "content": f"Prepare the brief for the week starting {wk.isoformat()}."}]
    steps = 0
    with tracer.span(f"weekly_brief {wk}", "AGENT", {"week_start": wk.isoformat(), "items": n_items}) as root:
        while steps < MAX_STEPS and tools.brief is None:
            steps += 1
            with tracer.span("llm", "CHAT_MODEL", {"step": steps}):
                resp = model.chat(msgs, Tools.SPECS)
            msg = resp["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            msgs.append({"role": "assistant", "content": _text(msg.get("content")) or None, "tool_calls": calls} if calls
                        else {"role": "assistant", "content": _text(msg.get("content"))})
            if not calls:
                msgs.append({"role": "user", "content": "Use the tools, then call submit_brief with the finished brief."})
                continue
            for c in calls:
                name = c["function"]["name"]
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                tools.used.append(name)
                if name == "submit_brief":
                    brief, problem = _clean_brief(args)
                    if problem:                       # let the model fix it rather than saving a broken brief
                        result = {"status": "rejected", "error": problem}
                    else:
                        tools.brief = brief
                        result = {"status": "received"}
                else:
                    with tracer.span(name, "TOOL", args):
                        result = _call(tools, name, args)
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result, default=str)[:12000]})
        if tools.brief is None:
            raise RuntimeError(f"agent did not submit a brief for {wk} in {steps} steps")
        trace_id = tracer.trace_id(root)
    out = write_brief(sql, cat, prefix, tools, model.endpoint, trace_id, steps)
    out.update(steps=steps, tools=sorted(set(tools.used)), trace_id=trace_id)
    return out


class Tracer:
    """MLflow tracing when available (job environment); a no-op locally."""

    def __init__(self, experiment: str | None):
        self.m = None
        if not experiment:
            return
        try:
            import mlflow
            mlflow.set_tracking_uri("databricks")
            mlflow.set_experiment(experiment)
            self.m = mlflow
        except Exception as e:  # noqa: BLE001
            print(f"tracing disabled: {e}")

    @contextlib.contextmanager
    def span(self, name, kind, attrs=None):
        if not self.m:
            yield None
            return
        with self.m.start_span(name=name, span_type=kind) as s:
            with contextlib.suppress(Exception):
                s.set_inputs(attrs or {})
            yield s

    def trace_id(self, span) -> str | None:
        if span is None:
            return None
        return getattr(span, "trace_id", None) or getattr(span, "request_id", None)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--mode", choices=["daily", "backfill"], default="daily")
    ap.add_argument("--weeks", type=int, default=26)
    ap.add_argument("--week", help="only this week (YYYY-MM-DD, a Monday)")
    ap.add_argument("--force", action="store_true", help="regenerate briefs that already exist")
    ap.add_argument("--model", default="databricks-claude-sonnet-5")
    ap.add_argument("--experiment", default=None)
    ap.add_argument("--min-items", type=int, default=3)
    ap.add_argument("--parallel", type=int, default=4, help="weeks written concurrently (backfills)")
    ap.add_argument("--profile", default=os.environ.get("DATABRICKS_PROFILE", "fevm-dc-demo-workspace-02"))
    a, _ = ap.parse_known_args(argv)
    sql = Sql(a.profile)
    ai = f"{a.catalog}.{a.prefix}ai.market_intel_brief"
    sql.q(f"""CREATE TABLE IF NOT EXISTS {ai} (week_start DATE, week_end DATE, headline STRING, summary_md STRING,
                developments_json STRING, implications_json STRING, watchlist_json STRING, actions_json STRING,
                sentiment_json STRING, n_items INT, n_sources INT, model STRING, tools_used ARRAY<STRING>, trace_id STRING,
                agent_steps INT, generated_at TIMESTAMP)
              COMMENT 'Weekly market intelligence brief written by the Market Intelligence Analyst agent'""")
    this_week = (datetime.now(AEST).date() - timedelta(days=datetime.now(AEST).weekday()))
    counts = {r["w"]: int(r["n"]) for r in sql.q(
        f"""SELECT CAST(week_start AS STRING) AS w, count(*) AS n FROM {a.catalog}.{a.prefix}gold.fact_market_intel_item
            WHERE relevance >= 1 AND week_start >= date_sub(DATE(:t), :d) GROUP BY week_start""",
        {"t": this_week.isoformat(), "d": 7 * a.weeks})}
    have = {r["w"] for r in sql.q(f"SELECT CAST(week_start AS STRING) AS w FROM {ai}")}
    if a.week:
        todo = [date.fromisoformat(a.week)]
    else:
        weeks = [this_week - timedelta(weeks=i) for i in range(a.weeks)]
        always = set(weeks[:2]) if a.mode == "daily" else set()      # the current and last week keep changing
        todo = [w for w in weeks if counts.get(w.isoformat(), 0) >= a.min_items
                and (a.force or w in always or w.isoformat() not in have)]
    print(f"briefs to write: {[w.isoformat() for w in todo]}")
    model, tracer = Model(sql, a.model), Tracer(a.experiment)
    failed = []

    def one(wk: date):
        t0 = time.time()
        try:
            out = run_week(sql, model, a.catalog, a.prefix, wk, counts.get(wk.isoformat(), 0), tracer)
            print(f"{wk}: {out} in {time.time() - t0:.0f}s", flush=True)
        except Exception as e:  # noqa: BLE001 – one bad week must not stop the others
            failed.append(wk.isoformat())
            print(f"{wk}: FAILED {e}", flush=True)

    # newest weeks first so the current brief is available soonest; each week still reads the prior brief if present
    with ThreadPoolExecutor(max_workers=max(1, a.parallel)) as ex:
        list(ex.map(one, sorted(todo, reverse=True)))
    if failed and len(failed) == len(todo):
        sys.exit(f"every brief failed: {failed}")


if __name__ == "__main__":
    main(sys.argv[1:])
