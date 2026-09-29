"""Cost vs quality experiment for Lochard's AI tiers (Unity AI Gateway model services) and intelligent routing.

The same grounded board / leadership questions run through every arm:
  premium | standard | economy | open (model services) | assistant (weighted gateway routing) | router (this file:
  economy model classifies complexity -> dispatches to economy / standard / premium).
Every call carries Databricks-Ai-Gateway-Request-Tags (app, arm, qid) so tokens / latency / routing land in
system.ai_gateway.usage; quality is scored 1-5 by an LLM judge (standard tier) against the reference facts.
Results -> <catalog>.<prefix>ai.model_cost_experiment (feeds the AI Cost & Quality dashboard).
"""
import argparse
import json
import time
import uuid

import requests
from databricks.sdk import WorkspaceClient
from pyspark.sql import SparkSession

PRICES = {"opus": (15.0, 75.0), "sonnet": (3.0, 15.0), "haiku": (1.0, 5.0), "gpt-6": (10.0, 40.0), "gpt-5-5": (1.25, 10.0),
          "gemini": (0.3, 2.5), "gpt-oss": (0.15, 0.6), "qwen": (0.2, 0.8)}   # indicative USD / 1M tokens (in, out)


def price(model: str, pin: int, pout: int) -> float:
    m = (model or "").lower()
    for k, (i, o) in PRICES.items():
        if k in m:
            return pin / 1e6 * i + pout / 1e6 * o
    return 0.0


class Gateway:
    def __init__(self, workspace_id: str, catalog: str, ai_schema: str):
        self.w = WorkspaceClient()
        self.url = f"https://{workspace_id}.ai-gateway.cloud.databricks.com/mlflow/v1/chat/completions"
        self.ns = f"{catalog}.{ai_schema}"

    def chat(self, service: str, messages, tags: dict, max_tokens=2000, temperature=None):  # reasoning tiers need headroom
        headers = self.w.config.authenticate()
        headers.update({"Content-Type": "application/json", "Databricks-Ai-Gateway-Request-Tags": json.dumps(tags)})
        t0 = time.time()
        for attempt in range(4):
            r = requests.post(self.url, headers=headers, timeout=180, json={
                "model": f"{self.ns}.{service}", "messages": messages, "max_tokens": max_tokens})
            # (no temperature: Opus 5.5 / Sonnet 5 reject it; tiers are compared at provider defaults)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** attempt * 3)
                continue
            break
        latency = int((time.time() - t0) * 1000)
        d = r.json()
        if "choices" not in d:
            return {"text": f"ERROR {r.status_code}: {str(d)[:200]}", "model": None, "pin": 0, "pout": 0, "latency_ms": latency}
        u = d.get("usage", {})
        content = d["choices"][0]["message"].get("content")
        if isinstance(content, list):  # reasoning models return content blocks (reasoning + text)
            content = "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") in ("text", "output_text"))
        return {"text": content or "", "model": d.get("model"), "pin": u.get("prompt_tokens", 0),
                "pout": u.get("completion_tokens", 0), "latency_ms": latency}


def facts(spark, cat, prefix) -> dict:
    sem = f"{cat}.{prefix}semantic"
    q = lambda s: [r.asDict() for r in spark.sql(s).collect()]
    return {
        "finance_fy27_by_team": q(f"SELECT team, round(sum(budget_amount)/1e6,2) budget_m, round(sum(actual_amount)/1e6,2) "
                                  f"ytd_actuals_m, round(sum(yeo_amount)/1e6,2) yeo_m, round(sum(committed_amount)/1e6,2) committed_m "
                                  f"FROM {sem}.v_finance_monthly WHERE financial_year='FY2027' GROUP BY team ORDER BY budget_m DESC"),
        "hse": q(f"SELECT count_if(classification='INCIDENT') total_obs, count_if(classification='INCIDENT' AND is_open) open_obs, "
                 f"count_if(classification='INCIDENT' AND is_open AND actual_risk_rank='HIGH') open_high, "
                 f"count_if(is_high_potential_event AND financial_year='FY2027') fy27_hpe, "
                 f"count_if(classification='INVESTIGATION' AND is_open) open_investigations FROM {sem}.v_observation_detail"),
        "maintenance": q(f"SELECT round(sum(schedule_compliant_count)/sum(scheduled_count),3) latest_week_compliance "
                         f"FROM {sem}.v_workorder_schedule_weekly WHERE is_latest_snapshot AND schedule_week_start = "
                         f"(SELECT max(schedule_week_start) FROM {sem}.v_workorder_schedule_weekly WHERE is_latest_snapshot)"),
        "vic_demand_pj_jan_aug": q(f"SELECT gas_year, round(sum(total_gas_used_pj),1) pj FROM {sem}.v_vic_gas_demand_daily "
                                   f"WHERE gas_month <= 8 AND gas_year >= 2021 GROUP BY gas_year ORDER BY gas_year"),
        "scorecard_fy27": "1.1 HSE Performance 20% At Risk (FY27 High Potential Event at Iona-3 wellhead); 1.2 Ops & "
                          "Maintenance 10% On Track; 1.3 FIT program 5% On Track; 2.1 HUGS Delivery 5% At Risk (EAC above "
                          "revised P50 $112.4M, RFSU Jan 2027); 2.2 Queen 20% On Track; 2.3 Growth & Commercial 10% On Track; "
                          "3.1 EBITDA 20% On Track; 3.2 TSR 10% On Track.",
    }


QUESTIONS = [
    ("lookup", "What is the FY2027 budget for Employee Costs?"),
    ("lookup", "How many HSE observations are currently open, and how many are HIGH risk?"),
    ("lookup", "What was the latest weekly scheduled maintenance compliance?"),
    ("lookup", "What were YTD actuals for Major Projects in FY2027?"),
    ("lookup", "How much VIC gas demand was there from January to August 2024 in PJ?"),
    ("lookup", "Which scorecard KPIs are At Risk?"),
    ("lookup", "What is the committed cost for Growth?"),
    ("lookup", "How many open HSE investigations are there?"),
    ("analytical", "Compare cumulative VIC gas demand (Jan-Aug) across 2021-2024 and explain the trend."),
    ("analytical", "Which three teams have the largest gap between YEO and budget, and what might that indicate?"),
    ("analytical", "Is the FY2027 weighted scorecard on track? Show the weighted status using On Track = 100%, At Risk = 50%."),
    ("analytical", "Relate the HSE KPI status to the underlying observation and HPE data."),
    ("analytical", "What does the gap between budget and YTD actuals for Employee Costs tell us two months into the year?"),
    ("analytical", "Summarise maintenance performance and where management should focus."),
    ("strategic", "Draft a three-sentence board summary of FY2027 performance to date across HSE, operations and finance."),
    ("strategic", "What are the top three risks the Board should discuss this month, with evidence?"),
    ("strategic", "Write the commentary for scorecard KPI 2.1 HUGS Delivery for the board paper (max 60 words)."),
    ("strategic", "How should Lochard position Iona given declining VIC gas demand? Keep it to 4 bullet points."),
]

SYSTEM = ("You are the Lochard Energy leadership analyst. Answer ONLY from the JSON facts provided; if a fact is missing "
          "say so. Use AUD, the Australian financial year (FY2027 = Jul-26..Jun-27) and never mention individual people.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--workspace-id", default="7474659469579329")
    a, _ = ap.parse_known_args()
    spark = SparkSession.builder.getOrCreate()
    gw = Gateway(a.workspace_id, a.catalog, f"{a.prefix}ai")
    ctx = json.dumps(facts(spark, a.catalog, a.prefix), default=str)
    run_id = str(uuid.uuid4())[:8]
    rows = []
    arms = {"premium": "lochard_llm_premium", "standard": "lochard_llm_standard", "economy": "lochard_llm_economy",
            "open": "lochard_llm_open", "assistant": "lochard_assistant"}
    tiers = {"lookup": "lochard_llm_economy", "analytical": "lochard_llm_standard", "strategic": "lochard_llm_premium"}
    for qi, (cat, q) in enumerate(QUESTIONS):
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"FACTS:\n{ctx}\n\nQUESTION: {q}"}]
        plan = []
        for arm, svc in arms.items():
            plan.append((arm, svc, None))
        # intelligent router: economy model classifies the question, then dispatches to the cheapest adequate tier
        cls = gw.chat("lochard_llm_economy", [{"role": "user", "content":
                      "Classify this leadership question as LOOKUP (single fact), ANALYTICAL (compare / explain) or "
                      f"STRATEGIC (judgement / narrative). Reply with one word.\n\n{q}"}],
                      {"app": "cost_experiment", "arm": "router_classifier", "qid": str(qi), "run": run_id}, max_tokens=200)
        label = next((k for k in tiers if k.upper() in cls["text"].upper()), "analytical")
        plan.append(("router", tiers[label], (label, cls)))
        for arm, svc, route in plan:
            res = gw.chat(svc, msgs, {"app": "cost_experiment", "arm": arm, "qid": str(qi), "run": run_id})
            extra_cost, extra_lat, extra_tok = 0.0, 0, 0
            if route:
                c = route[1]
                extra_cost, extra_lat, extra_tok = price(c["model"], c["pin"], c["pout"]), c["latency_ms"], c["pin"] + c["pout"]
            judge = gw.chat("lochard_llm_standard", [{"role": "user", "content":
                            f"FACTS:\n{ctx}\n\nQUESTION: {q}\n\nANSWER:\n{res['text']}\n\nScore the ANSWER 1-5 for factual "
                            "accuracy against FACTS, completeness and usefulness to a board. Reply with ONLY a JSON object, no prose: "
                            '{"score": <1-5>, "reason": "<short>"}'}],
                            {"app": "cost_experiment", "arm": "judge", "qid": str(qi), "run": run_id}, max_tokens=800)
            try:
                j = json.loads(judge["text"][judge["text"].find("{"): judge["text"].rfind("}") + 1])
            except Exception:
                j = {"score": None, "reason": judge["text"][:200]}
            rows.append(dict(run_id=run_id, qid=qi, category=cat, question=q, arm=arm, model_service=svc,
                             routed_label=route[0] if route else None, served_model=res["model"],
                             input_tokens=res["pin"], output_tokens=res["pout"], total_tokens=res["pin"] + res["pout"] + extra_tok,
                             latency_ms=res["latency_ms"] + extra_lat,
                             est_cost_usd=price(res["model"], res["pin"], res["pout"]) + extra_cost,
                             quality_score=float(j.get("score")) if j.get("score") is not None else None,
                             judge_reason=str(j.get("reason"))[:500], answer=res["text"][:4000]))
            print(qi, arm, res["model"], rows[-1]["est_cost_usd"], rows[-1]["quality_score"], flush=True)
    import pandas as pd
    pdf = pd.DataFrame(rows)
    for c in ["routed_label", "served_model", "judge_reason", "answer", "question", "category", "arm", "model_service"]:
        pdf[c] = pdf[c].astype("string").fillna("")
    for c in ["input_tokens", "output_tokens", "total_tokens", "latency_ms", "qid"]:
        pdf[c] = pdf[c].fillna(0).astype("int64")
    pdf["est_cost_usd"] = pdf["est_cost_usd"].astype(float)
    pdf["quality_score"] = pdf["quality_score"].astype(float)
    df = spark.createDataFrame(pdf).selectExpr("*", "current_timestamp() AS run_at")
    tbl = f"{a.catalog}.{a.prefix}ai.model_cost_experiment"
    df.write.mode("append").option("mergeSchema", "true").saveAsTable(tbl)
    spark.sql(f"COMMENT ON TABLE {tbl} IS 'Cost vs quality experiment across Unity AI Gateway tiers and routing (per question x arm)'")
    print("wrote", len(rows), "rows to", tbl)


if __name__ == "__main__":
    main()
