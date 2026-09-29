# Lochard Energy – Data Intelligence Platform (Databricks)

A production-style rebuild of Lochard Energy's reporting estate on Databricks: governed medallion data built with
Lakeflow Declarative Pipelines, AI/BI replicas of the PowerBI and Tableau reports, Genie Agents plus Genie One,
a Lakebase-backed Leadership Portal app, a market intelligence pipeline with an analyst agent, Unity AI Gateway
model services with cost tiers and routing, and ABAC governance. Everything is serverless and deployed from this
repo with one Declarative Automation Bundle. The design is in [`PLAN.md`](PLAN.md).

> **Moving to production:** the catalog (`dc_demo_workspace_02_catalog`) and schema names (`lochard_*`) are bundle
> variables and are expected to change in Lochard's production workspace. See [`docs/PROD_MIGRATION.md`](docs/PROD_MIGRATION.md).

- Workspace: `https://fevm-dc-demo-workspace-02.cloud.databricks.com` (profile `fevm-dc-demo-workspace-02`)
- Catalog: `dc_demo_workspace_02_catalog`. All schemas are prefixed `lochard_` (dev target: `lochard_dev_`).
- Leadership Portal: <https://lochard-board-portal-7474659469579329.aws.databricksapps.com>

## What is deployed (bundle `lochard-data-platform`, target `prod`)

| Area | Assets |
|---|---|
| Schemas | `lochard_landing` (volumes `raw`, `documents`, `checkpoints`), `lochard_bronze`, `lochard_silver`, `lochard_gold`, `lochard_semantic`, `lochard_governance`, `lochard_ai`, `lochard_platform` |
| Sources | `lochard-generate-source-data` job (simulated Business Central, Maximo, HSE, historian, planner Excel files, documents; seeded from `docs/Sample Data.xlsx`) and `lochard-aemo-nemweb-ingest` job (**real** AEMO INT091, INT287, INT313, INT037b, INT153) |
| Pipelines (serverless SDP) | `lochard-shared` (conformed dims, SCD2), `lochard-finance`, `lochard-hse`, `lochard-maintenance`, `lochard-market-ops`, `lochard-documents` (AI Functions) |
| Semantic layer | 15 consumer views and 6 UC metric views (`mv_finance`, `mv_hse`, `mv_maintenance`, `mv_market`, `mv_iona_ops`, `mv_board`), deployed by `lochard-semantic-and-governance` |
| Governance | Governed tags `lochard_pii`, `lochard_rls`, `lochard_domain`, `lochard_sensitivity`; 7 ABAC policies on `lochard_gold`; persona entitlement table `lochard_governance.principal_persona`; persona test service principals |
| Market intelligence | `lochard-market-intel` job (daily 07:00 AEST): collector (Google News search, a web-research agent using hosted web search, ASX announcement PDFs, Lochard newsroom) → `lochard-market-intel-medallion` pipeline (Auto Loader, `ai_parse_document`, `ai_query` enrichment) → **Market Intelligence Analyst** tool-calling agent writing a weekly brief (MLflow traces) → `lochard_semantic.v_market_intel_*`. See [`docs/market_intelligence.md`](docs/market_intelligence.md) |
| Dashboards (AI/BI) | Finance – Function Details (with drill-through pages), HSE Observations, Maintenance Dashboard, Ops – Cumulative VIC Demand & EDD, Market Intelligence, Platform – AI Cost & Quality, Platform – Data Quality & Pipelines, Platform – Governance & Audit |
| Genie Agents | Lochard Finance, HSE, Maintenance, Gas Market & Iona Ops, Executive & Board (instructions, example SQL, metric views, benchmarks; Executive & Board also covers market intelligence) |
| Agent Bricks | Knowledge Assistant "Iona Knowledge" (procedures, OEM manuals, board papers) and Supervisor Agent "Lochard Leadership Analyst" (6 tools). Created by `src/ai/agent_bricks/apply.sh`, because they are not yet bundle resources. |
| Unity AI Gateway | Model services `lochard_llm_premium` (Opus 5.5 → GPT-6), `lochard_llm_standard` (Sonnet 5 → GPT-5.5), `lochard_llm_economy` (Haiku 4.5 → Gemini 3.8 Flash), `lochard_llm_open` (gpt-oss-120b → Qwen 3.5), and `lochard_assistant` (routed 70/20/10 with fallback). All have rate limits and inference tables. |
| AI / ML | VIC gas demand forecaster (MLflow, batch scored to `lochard_ai.vic_demand_forecast`); cost vs quality experiment `lochard-ai-cost-quality-experiment` → `lochard_ai.model_cost_experiment` |
| App + Lakebase | Lakebase Autoscaling project `lochard-board-portal` (branches `production` and `dev`, database `board_portal`); app `lochard-board-portal`, the **Leadership Portal** (FastAPI + React: Leadership Insights, Market Intelligence, Board Pack, Agents, Dashboards, AI & Governance, Architecture); `lochard-scorecard-sync` job (Lakebase → `lochard_gold.fact_board_*`, `fact_leadership_commentary`) |
| SQL warehouses | `lochard-serverless-wh` (PRO, serverless) and `lochard-rt-wh` (**Lakehouse//RT**, created by `scripts/create_rt_warehouse.sh`) for low-latency dashboards |
| Orchestration | `lochard-daily-orchestrator` (paused): AEMO → shared → 4 domains + scorecard sync → documents → semantic & governance; `lochard-market-intel` (daily, unpaused) |

## Calibration (the numbers match the supplied reports)

| Source report | Figure(s) reproduced exactly in gold |
|---|---|
| PBI Finance | FY2027 budget by team (total $180.2M), YTD actuals ($3.78M), YEO ($71.3M), committed ($11.8M); Budgeted/Emergent donut 3.47/0.20/0.11; HUGS PRM-0021E YTD −$197,041.83 |
| PBI HSE | 5,132 observations (321 open, 4,811 closed), 140 investigations (7 open), risk × status matrix, category mix 72.2/11.0/10.5/5.5 |
| PBI Maintenance | Compliance 84.4% (week 27-Jul-26), overdue safety-critical 25, open P1 4, open P2 excl. PM 635, backlog excl. PM 5,328, 13-week compliance series, PM 575 / GPC 105 / DM 92 / CBM 59 |
| Tableau INT091 | Jan–Aug monthly PJ 2021–2024 (e.g. 2021 = 9.6 / 9.0 / 10.2 / 15.2 / 22.7 / 28.0 / 29.5 / 24.8); EDD-vs-demand R² ≈ 0.85 |
| Board scorecard | FY27 KPIs, deliverables, owners and weights (sum 100%); Aug-26 statuses → weighted status index 87.5% |

Run `.venv/bin/python -m pytest tests/data` after a local backfill (`python src/data_generation/main.py --out out/raw --docs out/documents`).

## Deploy / operate

```bash
databricks bundle deploy -t prod                       # everything in resources/
databricks jobs run-now <lochard-generate-source-data> # one-off backfill (mode=backfill)
databricks bundle run -t prod lochard_daily_orchestrator
databricks bundle run -t prod board_portal_app         # deploy / restart the app
src/ai/agent_bricks/apply.sh                           # Knowledge Assistant + Supervisor Agent (idempotent)
src/app/.venv/bin/python scripts/lakebase_grants.py    # Postgres grants for the app + sync service principals
```

Generators that write bundle source:
- `python src/dashboards/build/build_dashboards.py` writes `src/dashboards/*.lvdash.json`.
- `python src/genie/build_spaces.py` writes `resources/genie.yml`.
- `scripts/apply_sql_dir.py src/{semantic,governance,platform}` is the local dev loop for the SQL layers.

## Leadership Portal (app `lochard-board-portal`)

The portal follows the monthly leadership rhythm:

1. **Leadership Insights** (the LT dashboard, landing page). Finance, HSE, maintenance and Iona operations & market
   for any period (month, FY quarter, FY to date, rolling 12 months), each compared with the prior corresponding
   period. Every card drills down to its AI/BI dashboard, and each domain has management commentary for the month.
2. **Market Intelligence.** What moved this week for Lochard, customers, competitors, suppliers, regulators and the
   gas market. Step back and forth through weeks or widen the horizon (4 / 13 / 26 weeks); the Market Intelligence
   Analyst agent's weekly brief sits alongside the analyst's commentary and the item feed, with a drill-down to the
   Market Intelligence dashboard.
3. **Board Pack.** Twelve slides as tabs (the FY27 scorecard is one), each with its own commentary and readiness.
   A leader finalises the pack into a versioned snapshot and a PDF for the Board.

Then come **Agents** (chat with the Leadership Analyst, the Genie agents and Iona Knowledge, plus the model routing
lab), **Dashboards** (embedded AI/BI), **AI & Governance** (persona switch for the ABAC demo) and **Architecture**
(every process flow and technical note). The **Ask Lochard** button (bottom right, on every page) opens the same
assistants, with starter questions for the page you are on.

**Roles.** What you can do in the portal:
- **Leader** (`LLT`): reviews commentary (approve, or return with a note) and finalises the Board Pack.
- **Manager / Analyst** (`KPI_OWNER`): drafts commentary (optionally from an AI draft, always labelled), submits it
  for review, and curates market signals (pin, dismiss, note, importance).
- **Board director** (`BOARD`): sees approved commentary and finalised packs, and scores KPIs.
- **Administrator**: can switch between these views with **Viewing as** in the navigation (header
  `x-lochard-view-as`). The lens only narrows portal permissions; data access is always evaluated as the real user.

The role comes from `scorecard.app_user_role`, then the UC persona, then observer.

Commentary uses one workflow everywhere (`scorecard.commentary`, migration V003):
- scope `insights`, `market` or `boardpack`;
- DRAFT → SUBMITTED → APPROVED, or RETURNED;
- any edit returns the text to draft;
- drafts are visible to managers only, submitted and approved text to leaders, approved text to the Board.

### Agents page

`/api/agents/stream` proxies the Agent Bricks Responses stream (`stream: true`) as server-sent events. Each
`response.output_item.done` becomes one trace step:
- a tool call, with the exact sub-question;
- a sub-agent result: a Genie table, or Knowledge Assistant text with its citations lifted from footnotes and annotations;
- narration;
- the final answer.

Genie Agents are traced through the Conversation API status transitions plus the generated SQL.

The **routing lab** (`/api/agents/lab`):
1. classifies the question with `lochard_llm_economy`;
2. routes it to economy, standard or premium;
3. runs all three tiers in parallel through the AI Gateway on the same Lakebase-grounded prompt, with request tags `feature=routing_lab`.

All calls use the viewer's OBO token. Runs are stored in `scorecard.agent_run` (migration V002).

For viewers other than workspace admins, the two Agent Bricks endpoints (`var.supervisor_endpoint`,
`var.knowledge_endpoint`) need `CAN_QUERY` for those users or groups. This is not granted by default.

### Local development

```bash
# throwaway copy-on-write Lakebase branch (never develop against production)
databricks postgres create-branch projects/lochard-board-portal localdev \
  --json '{"spec": {"source_branch": "projects/lochard-board-portal/branches/production", "ttl": "1209600s"}}'
source scripts/localdev.env.sh          # ENDPOINT_NAME / PGHOST of that branch
cd src/app && .venv/bin/python -m uvicorn app:app --port 8765 --reload
cd frontend && API_PORT=8765 npx vite   # http://localhost:5173
```

## Dashboards on Lakehouse//RT

Maintenance, Ops (VIC demand & EDD), AI Cost and Data Quality run on `lochard-rt-wh` (`warehouse_type: REALTIME`).
- RT does not yet support tables with row filters, column masks or ABAC policies. Finance, HSE and Governance therefore stay on the PRO serverless warehouse, so viewer-level ABAC keeps working.
- The API/CLI enum only lists CLASSIC/PRO, so the RT warehouse is looked up by name (`var.rt_warehouse_id`) rather than managed as a bundle resource.

## Governance demo (persona switch)

The workspace has no account-level groups, and they can't be created from the workspace. Personas therefore come
from `lochard_governance.principal_persona`, keyed on `current_user()`. The UDFs also honour account groups named
`lochard_<persona>` once those exist.

Switch the presenter's persona in the app (**AI & Governance → persona**), or run:

```sql
UPDATE dc_demo_workspace_02_catalog.lochard_governance.principal_persona
SET persona = 'board' WHERE principal = current_user();   -- then: platform_admin to restore
```

| Persona | Sees |
|---|---|
| board | pseudonymised people (`PERSON-xxxx`), `[restricted – Legal/Employee Costs]` GL text, masked bank details, no privileged investigations, BOARD_ONLY comments |
| budget_holder (team = Maintenance) | only Maintenance finance rows |
| hse / hse_investigator | real names / privileged investigations |
| finance | bank details, all GL text |

## AI cost and routing – first experiment result (18 grounded board questions × 6 arms, LLM judge)

| Arm | Quality (1–5) | USD per 100 answers | Avg latency |
|---|---|---|---|
| standard (Sonnet 5) | **4.41** | 1.16 | 6.5 s |
| assistant (70/20/10 weighted) | 4.17 | 1.83 | 6.2 s |
| premium (Opus 5.5) | 3.93 | 8.79 | 10.7 s |
| economy (Haiku 4.5) | 3.88 | **0.20** | 2.3 s |
| router (economy classifier → tier) | 3.88 | 3.06 | 7.4 s |
| open (gpt-oss-120b) | 3.59 | 0.05 | 2.6 s |

**Finding.** For fact-grounded board Q&A, premium costs about 7.6× standard for no quality gain. Recommended routing:
- lookup → economy;
- analytical and strategic → standard;
- keep premium for long-form board narrative only.

Update the tier map in `src/ai/cost_explorer.py` and re-run monthly. Seven of 108 judge replies failed to parse; the
rest are scored.

## Known deviations from the plan (environment constraints)

- **Account groups.** Groups can't be created from this workspace, so personas are driven by the entitlement table and by service principals (see above).
- **Custom model registration.** The shared FEVM metastore has hit its registered-model quota (5,000). The forecaster is logged in MLflow and batch-scored, and it registers to UC (`@champion`) automatically once quota frees up. Custom-model serving behind the Gateway is enabled at that point.
- **Model services and routing.**
  - Destinations can only be foundation models, so `lochard_assistant` uses weighted routing with fallback.
  - Complexity-based "intelligent" routing is implemented in the cost experiment.
- **Reasoning models.** Opus 5.5 and Sonnet 5 reject `temperature` and return content blocks, which both the app and the experiment handle.
- **Genie One.** The homepage customisation and Consumer-access entitlements for real users are workspace-admin UI steps. See `docs/DEMO_SCRIPT.md`.
- **Data residency.** The workspace is us-east-1; real Lochard production would run in ap-southeast-2.
