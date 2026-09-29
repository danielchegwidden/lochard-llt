# Lochard Energy — Databricks Data Intelligence Platform Build Plan

**Sections**
- 1 Context and verified facts
- ARCH Architecture
- B Repo and bundle layout
- P Pipelines and expectations
- DG Sample data
- M Gold model and KPIs
- D Dashboards
- S Scorecard spec
- Q AI Functions (answer: yes)
- G Governance
- N Genie Agents and Genie One
- F AI Gateway, models, agents, responsible AI
- A Board portal app
- R Risks
- **I Implementation phases**
- V Verification
- DEMO Run-sheet

## 1. Context

Lochard Energy runs the Iona Gas Storage Facility (Port Campbell, VIC). The HUGS and Queen growth projects are underway, and the operating entity is Iona Ops Trust. Today the reporting estate is split across three places:
- **PowerBI**: Finance (Function Details with drill-through to transactions), HSE Observations, Maintenance (weekly schedule compliance).
- **Tableau**: "INT091 Actual EDD vs VIC demand". It reads AEMO MIBB views (`AEMO_INT287_CUR_V`, `VSET_INT091_CUR_V`) from on-prem SQL Server `loc-sql02` / `EMDM_Datamart`.
- **PowerPoint**: the board scorecard (FY27 KPIs, owners, weights, status). It is compiled by hand every month.

The goal is to rebuild all of this on Databricks as though it were Lochard's production platform:
- governed medallion data built with Lakeflow Declarative Pipelines;
- AI/BI dashboards that replicate PBI and Tableau;
- Genie Agents per domain, plus Genie One for business users;
- a Lakebase-backed board portal app for scorecard scoring and commentary, trends and Q&A;
- Unity AI Gateway with a custom model, cost-tiered models and routing;
- ABAC governance and AI document processing.

Everything is serverless and deployed with Declarative Automation Bundles (DABs).

**Domain facts used for realism** (public sources, approximate; confirm with Lochard before real production use)
- **Iona**: about 24.4 PJ storage and about 570 TJ/d maximum withdrawal. HUGS Phase 1 adds about 1.8 PJ (to about 26.2 PJ) and takes withdrawal to about 615 TJ/d, with RFSU targeted around Jan 2027 (matching scorecard KPI 2.1).
- **Wells and sites**: Iona-1..7, Seamer, North Paaratte, Wallaby Creek. The sample GL text already references "Iona 7 wellhead" and "Seamer Access Track".
- **Market**: the plant is connected to the South West Pipeline (SWP) and trades in the AEMO DWGM. VIC demand is about 170 PJ/yr, peaking in winter.
- **EDD** is the AEMO weather-normalised heating index (INT091, daily). INT126 (DFS forecast EDD and demand) is an optional extra feed for the forecast page.

**Personas**: the scorecard owner initials (DA, BN, DS, DG, LLT) are kept exactly as they appear in the supplied slide and mapped to **role titles** (COO, GM Commercial, GM Project Delivery, GM Development, Leadership Team). All demo users, actionees and commentary authors are **fictitious**; no real staff names go into the data.

**Where each request is covered**

| Request | Deliverable | Section |
|---|---|---|
| 3 PBI dashboards (Finance, HSE, Maintenance) as AI/BI | D1–D3, including drill-through pages | D |
| Tableau dashboard-ops (INT091 EDD vs VIC demand) | D4, 5 pages including R² and forecast | D |
| Genie per domain | 5 Genie Agents with benchmarks | N |
| Genie One and responsible AI | Consumer-access homepage, RAI controls table, demo | N, F5 |
| Scorecard app with comments and scores for board reporting | `lochard-board-portal` on Lakebase with a workflow and export to the board pack | S, A |
| Dashboards embedded as iframes in the app | Dashboards tab with an allow-listed domain | A5 |
| Leadership trends and questions in the app | Insights page and Ask (Supervisor Agent / Genie) | A3, A5, F4 |
| Custom model in Unity AI Gateway, agents | `lochard_assistant`, `lochard_router`, `lochard_demand_forecaster`, Supervisor Agent, MCP agent | F |
| Cost management and intelligent routing | Tiered model services, smart routing, budgets, cost/quality experiment, D5 | F1, F3 |
| Governance: role, column, ABAC | Groups, grants, governed tags, ABAC policies, persona tests | G |
| Medallion + declarative pipelines + DQ expectations | 5 serverless SDP pipelines, expectations catalogue, D6 | P |
| Missing sample data | Calibrated generator seeded from Sample Data.xlsx, plus real AEMO | DG |
| DABs, serverless, Lakebase | Everything in one bundle, dev/prod targets | B, I |
| AI Functions for documents? | **Yes**: 4 use cases | Q |

**Target**: workspace `https://fevm-dc-demo-workspace-02.cloud.databricks.com` (AWS us-east-1, workspace id 7474643965495809), CLI profile `fevm-dc-demo-workspace-02`, CLI v1.6.0, catalog `dc_demo_workspace_02_catalog`. Every schema is prefixed `lochard_`.

**Decisions already made (from Q&A)**
- VIC demand data comes from the **real AEMO nemweb feeds** (INT091 EDD, INT287 gas used), pulled daily. History from 2014 to mid-2026 is **synthesised and calibrated** to the Tableau monthly PJ table. Real data overrides synthetic where they overlap.
- App stack is **FastAPI + React**, with Lakebase Autoscaling.
- The PowerBI screenshots were extracted and reviewed (`/tmp/lochard-docx/image1-6.png`) and the dashboard specs below follow them.

**Platform facts verified (read-only checks)**
- Workspace state: catalog `dc_demo_workspace_02_catalog` has only `ai` and `information_schema`. There is one SQL warehouse ("Serverless Starter Warehouse"). There are no apps, Lakebase, dashboards or Genie yet. The only groups are `users` and `admins`.
- 55 pay-per-token endpoints are READY, including `databricks-claude-opus-5-5`, `databricks-claude-sonnet-5`, `databricks-claude-haiku-4-5`, `databricks-gpt-6-sol`, `databricks-gpt-5-5`, `databricks-gemini-3-8-flash`, `databricks-gpt-oss-120b`, `databricks-qwen35-122b-a10b`, `databricks-meta-llama-3-3-70b-instruct` and `databricks-gte-large-en`.
- The CLI v1.6.0 bundle schema supports `dashboards` (`file_path`, `warehouse_id`, `embed_credentials`, `dataset_catalog`, `dataset_schema`), `genie_spaces` (`title`, `description`, `warehouse_id`, `file_path` or `serialized_space`) and `postgres_projects`, `postgres_branches`, `postgres_endpoints`, `postgres_databases` and `postgres_synced_tables`.
- App resources support `postgres: {branch, database, permission}`, `genie_space`, `serving_endpoint`, `sql_warehouse` and `uc_securable`, plus `user_api_scopes`.
- **`model_services` is not in the v1.6.0 schema.** The docs list it as Beta in newer CLIs, so Phase 0 upgrades the CLI and keeps a REST fallback.
- Public AEMO files `int091_v4_eddact_1.csv` (`edd_update, edd_date, edd_value, edd_type, current_date`) and `int287_v4_gas_consumption_1.csv` (`gas_date, total_gas_used [GJ], current_date`) are live on nemweb. They hold roughly 60 and 31 days respectively.
- Genie spaces are now called **Genie Agents**, and Databricks One is now **Genie One**. Genie One needs the **Consumer access** entitlement.
- ABAC `CREATE POLICY … ON SCHEMA` needs serverless or DBR 16.4+ and governed tags.
- Unity AI Gateway is GA, with model services, fallback/traffic split, smart routing, rate limits, spend controls, usage and inference tables. Its service policies (guardrails) are **Beta** and need account preview enablement.
- AI/BI supports **right-click "Drill to" page** from pivot tables and charts, with target-page filters auto-populated. It also supports URL filter params `f_<page>~<widget>=value`.

**Reusable local accelerators**
- `~/.claude/skills/databricks-demo-generator/resources/extract_brand.py`: pulls the real palette, fonts and logo from lochardenergy.com.au.
- `…/realism_critic.py`: an LLM data-realism gate on the generated data.
- `…/theme.py`: turns brand tokens into a theme.
- `~/.claude/plugins/cache/fe-vibe/fe-databricks-tools/1.2.4/skills/databricks-lakeview-dashboard/resources/lakeview_builder.py` and `example_dashboard.json`: a builder and reference for dashboard JSON.
- The `databricks-apps` skill patterns: psycopg pool with a per-connection OAuth token, `max_lifetime=2700`, calls through the AI Gateway URL only, and stripping `strict` from tool schemas for Claude.
- `~/.databrickscfg` has no account-console profile for account `05d08df7-ae03-43ad-bbae-14babb530ec0`, so account-admin rights are unconfirmed. Phase 0 checks them (see Risks).

---

## ARCH. Target architecture

```
 SOURCES (simulated as prod extracts)          LANDING (UC Volumes)            LAKEFLOW DECLARATIVE PIPELINES (serverless)                 SERVE
 ─────────────────────────────────────         ─────────────────────           ───────────────────────────────────────────────           ─────────────────────────────
 ERP GL (Business Central, "Iona Ops Trust") ─► /erp/gl_entries/*.json   ─┐    BRONZE  lochard_bronze  (Auto Loader, raw + _metadata)     AI/BI dashboards D1–D7
 ERP Budget + YEO versions (Excel/CSV)       ─► /erp/budget|yeo/*.csv    ─┤      │  expectations: schema, not-null keys, rescued data  Genie Agents ×5 → Genie One
 Maximo POs / WOs / weekly schedule snapshot ─► /maximo/*.json|csv       ─┤    SILVER  lochard_silver (clean, typed, dedup, SCD2 dims   Board portal app (Lakebase)
 External schedule-hours files (planner xlsx)─► /maximo/schedule_files/  ─┤      │   via AUTO CDC, conformed keys, quarantine tables) Supervisor Agent / KA
 HSE system (observations, investigations)   ─► /hse/*.json              ─┤    GOLD    lochard_gold (star schema facts/dims, MVs)      Unity AI Gateway model services
 AEMO nemweb INT091 / INT287 (REAL, daily)   ─► /aemo/int091|int287/*.csv─┤    SEMANTIC lochard_semantic (UC metric views, trusted   Custom model: demand forecaster
 Iona SCADA/historian daily (inj/wdl/inv)    ─► /ops/historian/*.parquet ─┤            SQL functions for Genie/agents)
 Documents (incident PDFs, invoices, manuals)─► /documents/**            ─┘    DOCS    ai_parse_document / ai_extract / ai_classify
                                                                                GOVERNANCE lochard_governance (UDFs, tags, ABAC, entitlements)
 Lakebase (scorecard OLTP) ──── nightly sync job ────────────────────────────►  lochard_gold.fact_board_scorecard
```

**Schemas** (all in `dc_demo_workspace_02_catalog`). The prefix is a bundle variable: prod `lochard_`, dev `lochard_dev_`.

| Schema | Holds |
|---|---|
| `lochard_landing` | Volumes `raw` (source extracts), `documents`, `checkpoints` (for non-SDP jobs) |
| `lochard_bronze` | `brz_*` streaming tables |
| `lochard_silver` | `slv_*` tables, `quarantine_*` tables |
| `lochard_gold` | `dim_*`, `fact_*`, aggregate MVs |
| `lochard_semantic` | Metric views `mv_*`, thin consumer views `v_*` over gold, trusted SQL functions. This is the only schema that board and dashboards read. |
| `lochard_governance` | Mask/filter UDFs, `team_entitlements`, audit views |
| `lochard_ai` | Registered models, model services, inference/payload tables, eval sets, cost experiment, parsed docs, vector index |
| `lochard_ops` | Pipeline event-log views, DQ metrics, freshness SLAs (feeds D6) |

**Serverless everywhere**
- **Compute**: SDP `serverless: true`; jobs use serverless environments (`environment_version`).
- **SQL**: a dedicated serverless warehouse `lochard-serverless-wh`, size Small, auto-stop 10 minutes.
- **AI**: serverless model serving, serverless Vector Search, Apps, and Lakebase Autoscaling.
- **Cost tagging**: a **serverless budget policy** `lochard-platform` tags all spend (`project=lochard`, `env=dev|prod`, `use_case=…`).

---

## B. Repo and bundle layout (`/Users/daniel.chegwidden/Code/demos/lochard-llt`)

```
lochard-llt/
├── databricks.yml                     # bundle, variables, targets dev/prod, include resources/**
├── PLAN.md                            # this plan
├── docs/                              # inputs (unchanged) + RUNBOOK.md, DEMO_SCRIPT.md, adr/
├── resources/
│   ├── schemas.yml  volumes.yml  warehouse.yml
│   ├── pipelines/{finance,hse,maintenance,market_ops,documents}.yml
│   ├── jobs/{generate_data,aemo_ingest,daily_orchestrator,semantic_deploy,governance_setup,
│   │         train_forecaster,forecast_batch,scorecard_sync,genie_benchmarks,cost_explorer}.yml
│   ├── dashboards.yml   genie.yml   alerts.yml
│   ├── ai_gateway.yml   serving.yml   vector_search.yml
│   └── lakebase.yml     app.yml
├── src/
│   ├── data_generation/   ingest/   pipelines/<domain>/{bronze,silver,gold}.sql|py, expectations.py
│   ├── semantic/mv_*.yaml, functions.sql
│   ├── governance/00_identities.py … 06_classic_row_filters.sql
│   ├── dashboards/build/*.py, *.lvdash.json
│   ├── genie/build_space.py, *.json
│   ├── ml/train_forecaster.py   ai/{setup_model_services.py,router/,cost_explorer.py}   agents/ops_agent/
│   └── app/  (app.yaml, app.py, server/, frontend/)
└── tests/ {data,sql,governance,ai,app}/
```

**YAML sketches** (field names checked against the CLI v1.6.0 bundle schema; `model_services` follows the docs example)

```yaml
# databricks.yml
bundle: { name: lochard-data-platform }
include: [resources/**/*.yml]
variables:
  catalog: { default: dc_demo_workspace_02_catalog }
  prefix:  { default: lochard_dev_ }
  warehouse_id: { default: "${resources.sql_warehouses.lochard_wh.id}" }  # bundle-managed warehouse, no lookup chicken-and-egg
targets:
  dev:  { mode: development, default: true, workspace: { profile: fevm-dc-demo-workspace-02 } }
  prod:
    mode: production
    variables: { prefix: lochard_ }
    run_as: { service_principal_name: <sp-lochard-pipelines-app-id> }
    presets: { tags: { project: lochard, env: prod } }

# resources/warehouse.yml
resources:
  sql_warehouses:
    lochard_wh: { name: lochard-serverless-wh, warehouse_type: PRO, enable_serverless_compute: true,
                  cluster_size: Small, auto_stop_mins: 10, max_num_clusters: 2,
                  tags: { custom_tags: [ { key: project, value: lochard } ] } }

# resources/pipelines/finance.yml
resources:
  pipelines:
    lochard_finance:
      name: lochard-finance
      catalog: ${var.catalog}
      schema: ${var.prefix}bronze          # default; silver/gold use fully-qualified names
      serverless: true
      channel: CURRENT
      configuration: { catalog: ${var.catalog}, prefix: ${var.prefix} }
      libraries: [ { glob: { include: ../../src/pipelines/finance/** } } ]
      event_log: { catalog: ${var.catalog}, schema: "${var.prefix}ops", name: finance_event_log }

# resources/jobs/generate_data.yml (serverless job with environment)
resources:
  jobs:
    lochard_generate_data:
      name: lochard-generate-data
      parameters: [ { name: mode, default: incremental } ]
      environments:
        - environment_key: gen
          spec: { environment_version: "4", dependencies: [polars, mimesis, openpyxl, reportlab, python-docx] }
      tasks:
        - task_key: generate
          environment_key: gen
          spark_python_task: { python_file: ../../src/data_generation/main.py, parameters: ["--mode", "{{job.parameters.mode}}"] }

# resources/dashboards.yml
resources:
  dashboards:
    finance_function_details:
      display_name: "Lochard – Finance: Function Details"
      file_path: ../src/dashboards/finance_function_details.lvdash.json
      warehouse_id: ${var.warehouse_id}
      embed_credentials: false
      dataset_catalog: ${var.catalog}
      permissions: [ { group_name: lochard_finance, level: CAN_RUN }, { group_name: lochard_board, level: CAN_RUN } ]

# resources/genie.yml
resources:
  genie_spaces:
    finance_genie:
      title: "Lochard Finance"
      description: "Budget, actuals, YEO and commitments (FY Jul–Jun)"
      warehouse_id: ${var.warehouse_id}
      file_path: ../src/genie/finance.json
      permissions: [ { group_name: lochard_finance, level: CAN_RUN } ]

# resources/lakebase.yml
resources:
  postgres_projects:
    board_portal: { project_id: lochard-board-portal, display_name: "Lochard Board Portal", pg_version: 17,
                    custom_tags: [ { key: project, value: lochard } ] }
  postgres_branches:
    board_portal_dev: { parent: projects/lochard-board-portal, branch_id: dev,
                        source_branch: projects/lochard-board-portal/branches/production }
  postgres_endpoints:
    board_portal_prod_rw: { parent: projects/lochard-board-portal/branches/production, endpoint_id: primary,
                            endpoint_type: ENDPOINT_TYPE_READ_WRITE,   # enum value to confirm via bundle schema
                            autoscaling_limit_min_cu: 0.5, autoscaling_limit_max_cu: 4 }
  postgres_databases:
    board_portal_db: { parent: projects/lochard-board-portal/branches/production, database_id: board_portal }

# resources/app.yml
resources:
  apps:
    board_portal:
      name: lochard-board-portal
      source_code_path: ../src/app
      user_api_scopes: [sql, genie, ai-gateway, model-serving]
      resources:
        - name: lakebase
          postgres: { branch: projects/lochard-board-portal/branches/production,
                      database: projects/lochard-board-portal/branches/production/databases/board_portal,
                      permission: CAN_CONNECT_AND_CREATE }
        - name: warehouse
          sql_warehouse: { id: ${var.warehouse_id}, permission: CAN_USE }
        - name: exec-genie
          genie_space: { name: exec, space_id: ${resources.genie_spaces.exec_genie.id}, permission: CAN_RUN }
      permissions: [ { group_name: lochard_board, level: CAN_USE }, { group_name: lochard_leadership, level: CAN_USE } ]

# resources/ai_gateway.yml (after CLI upgrade; else src/ai/setup_model_services.py)
resources:
  model_services:
    lochard_assistant:
      parent: schemas/${var.catalog}.${var.prefix}ai
      model_service_id: lochard_assistant
      comment: "Lochard governed assistant – tiered routing with fallback"
      config:
        routing:
          destinations:
            - { name: standard, destination_type: DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL,
                pay_per_token_config: { model: models/system.ai.databricks-claude-sonnet-5 }, traffic_percentage: 70 }
            - { name: economy,  destination_type: DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL,
                pay_per_token_config: { model: models/system.ai.databricks-claude-haiku-4-5 }, traffic_percentage: 20 }
            - { name: premium,  destination_type: DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL,
                pay_per_token_config: { model: models/system.ai.databricks-claude-opus-5-5 }, traffic_percentage: 10 }
        # + fallback / smart-routing / rate-limit / guardrail / inference-table blocks per current API (confirm in Phase 7)
```

---

## P. Medallion pipelines (Lakeflow Spark Declarative Pipelines, serverless)

There is one pipeline per domain, so each has its own schedule, owner and failure isolation.
- **Publishing**: each pipeline publishes to multiple schemas, `catalog: dc_demo_workspace_02_catalog`, default `schema: ${var.prefix}bronze`. Silver and gold tables use fully qualified names.
- **Settings**: `serverless: true`, `channel: CURRENT`, `photon` implicit, `continuous: false` (triggered by the orchestrator).
- **Event logs**: published to `lochard_ops.<pipeline>_event_log` for D6.

| Pipeline | Bronze (Auto Loader `read_files` / `cloudFiles`) | Silver | Gold |
|---|---|---|---|
| `lochard_finance` | `brz_gl_entries` (json), `brz_budget` (csv), `brz_yeo` (csv), `brz_purchase_orders` (json), `brz_cost_centres` and `brz_accounts` and `brz_vendors` (csv, CDC feeds) | `slv_gl_entries` (typed, dedup on gl_entry_key, reversal pairing), `slv_budget`, `slv_yeo`, `slv_po_lines`; **AUTO CDC → SCD2** `slv_dim_cost_centre`, `slv_dim_vendor`; `quarantine_gl_entries` | `dim_*`, `fact_actuals`, `fact_budget`, `fact_yeo`, `fact_commitments`, `fact_purchase_order_lines`, MV `agg_finance_team_month` |
| `lochard_hse` | `brz_observations`, `brz_investigations`, `brz_hse_hours` | `slv_observations` (standardised enums, 'Unknown' fill, PII tag), `slv_investigations` | `fact_observations`, `fact_investigations`, `fact_hse_lagging`, MV `agg_observations_daily` (matches the sample shape) |
| `lochard_maintenance` | `brz_workorders` (json), `brz_schedule_snapshot` (csv), `brz_schedule_hours_files` (the planner's "files outside the system", read as **Excel** via `read_files format => 'excel'`, which is Beta; CSV fallback) | `slv_workorders` (SCD1 via AUTO CDC on wonum), `slv_schedule_snapshot` + hours joined | `fact_workorder`, `fact_workorder_schedule_weekly`, `dim_asset` |
| `lochard_market_ops` | `brz_aemo_int091`, `brz_aemo_int287` (csv; real + synthetic files are both just files), `brz_historian_daily` (parquet) | `slv_edd_daily`, `slv_vic_demand_daily`: AUTO CDC keyed on date, sequenced by `(source_priority, current_date)` so AEMO beats SYNTHETIC | `fact_edd_daily`, `fact_vic_gas_demand_daily`, `fact_iona_operations_daily`, MV `mv_cumulative_demand` |
| `lochard_documents` | `brz_documents` (binaryFile) | `slv_documents_parsed` (`ai_parse_document`), `slv_incident_reports_extracted`, `slv_invoices_extracted` (`ai_extract` / `ai_classify`) | `gold.hse_incident_reports`, `gold.invoice_three_way_match`, `gold.doc_chunks` (→ Vector Search delta-sync index) |

### Expectations catalogue (examples; the full list lives in `src/pipelines/<domain>/expectations.py` as a reusable dict)

| Table | Rule | Action |
|---|---|---|
| `brz_*` | `_rescued_data IS NULL` | warn |
| `slv_gl_entries` | `gl_entry_key IS NOT NULL AND entry_no IS NOT NULL` | **drop** |
| `slv_gl_entries` | `date_key BETWEEN 20140101 AND 20311231` | drop → quarantine |
| `slv_gl_entries` | `cost_centre_key IN dim_cost_centre` (orphan check via left join flag) | warn + quarantine |
| `slv_gl_entries` | `abs(gst_amount) <= abs(amount) * 0.11` | warn |
| `slv_gl_entries` | `NOT (reversed AND reversed_by_entry_no = 0)` | warn |
| `slv_budget` | `amount IS NOT NULL AND budget_type IN ('Budget')` | drop |
| `fact_budget` | one budget version per FY (aggregate check MV) | **fail** |
| `slv_observations` | `observation_type IN (…6…) AND status IN ('NEW','INPROG','CLOSED')` | drop |
| `slv_observations` | `closed_date IS NULL OR closed_date >= reported_date` | warn |
| `slv_schedule_snapshot` | `schedule_compliant_count <= scheduled_count` | drop |
| `slv_schedule_snapshot` | `est_dur_scheduled >= 0` | drop |
| `slv_vic_demand_daily` | `total_gas_used BETWEEN 100000 AND 2000000` (GJ/day) | warn |
| `slv_vic_demand_daily` | `gas_date <= current_date()` | fail |
| `slv_vic_demand_daily` | `gas_date < current_file_date` (a **real defect**: the live INT287 file includes the partial current gas day, e.g. 62,935 GJ on 23-Sep-2026) | drop, then reprocess on the next file |
| `slv_edd_daily` | `edd_value BETWEEN 0 AND 30` | warn |
| `slv_documents_parsed` | `parse_error IS NULL` | warn (plus a ≥ 98% success check in D6) |
| `slv_invoices_extracted` | `abs(total - (subtotal + gst)) <= 0.05` | quarantine |

The generator deliberately injects about 0.5–2% defects so every expectation has real hits in D6: null keys, orphan cost centres, duplicated GL lines, negative hours, a future gas date, and a malformed CSV row.

---

## DG. Sample data generation (`src/data_generation/`, serverless job `lochard_generate_data`)

- **Seeding**: the 400 provided rows (`docs/Sample Data.xlsx`) are loaded first as "golden" rows. Generators then learn the distributions from them: cost-centre and account mix, description vocabulary, craft mix, status mix. They expand to full scale with Polars + Mimesis, fixed seed.
- **Pseudonymisation**: the 42 sample `actionee` values (e.g. `JIM.MATTHEWS_LOC`) could be real staff, so they are replaced with consistent fictitious `FIRST.LAST_LOC` values during seeding.
- **Historical backfill**: written once as partitioned source-format files in `/Volumes/…/lochard_landing/raw/<system>/<entity>/load_date=YYYY-MM-DD/`.
- **Daily increments**: the job has an `--incremental` mode that writes today's files, to show Auto Loader incremental processing and late or restated records (GL reversals, re-forecast YEO version, snapshot rebuilds).

| Entity | Scale | Calibration targets |
|---|---|---|
| GL entries (FY22–FY27 YTD) | ~350k lines | FY27 budget by Team exactly as in PBI (Employee Costs 51,059K … HSE 953K; total **180.2M**, matching the cumulative budget line). FY27 YTD (Jul–Aug-26) actuals total **3.78M** (the matrix sum), which matches the donut (3.5M Blank + 0.2M Budgeted + 0.1M Emergent). HUGS PRM-0021E has accrual reversals giving YTD −197K (Jul +1.5M, Aug −1.7M). Pareto on vendors, and month-end spikes. |
| FY27 YEO | Sum of Team YEOs **71.3M** | Matches the Cumulative YEO chart top of ~72M. Team YEOs as in PBI (Employee Costs 21,196K, Major Projects 20,808K, …, People Safety & Sustainability −879K). |
| Budget | FY17 sample + FY22–FY27 | Monthly phasing (Opex flat, Capex back-loaded) |
| YEO | 12 versions per FY | Drift between −15% and +5% of budget per Team; cumulative YEO steps as in the PBI chart |
| PO lines and commitments | ~40k lines | Committed ≈ PBI figures (Major Projects 6,838K, Growth 2,183K, …) |
| Observations | ~5,200 rows since Jul-2014 | Totals 5,132 / 321 open. Category mix 72/11/10.5/5.5. Open by risk 7/34/35/245. 140 investigations, 7 open. Winter uplift, and an upward trend after the "HSE process upgrade" (KPI 1.1). |
| Work orders + weekly snapshots | ~60k WOs, 70 weekly snapshots (Jan-25 → Aug-26) | 13-week compliance series as in the PBI chart; latest week 84.4%. Overdue SC 25, P1 4, P2 excl PM 635, backlog excl PM 5,328. Type mix PM 67%. |
| AEMO EDD + demand | Daily 2014-01-01 → today−61d (synthetic) + real nemweb | Monthly PJ sums within ±1% of the Tableau table for 2021–2024 (e.g. 2021: 9.6/9.0/10.2/15.2/22.7/28.0/29.5/24.8). Demand ≈ a + b·EDD + weekday effect + noise, so R² ≈ 0.85–0.9 like the Tableau R² sheets. |
| Iona operations | Daily since 2018, per well/site | Injection in summer and withdrawal in winter. Inventory ≤ 24.4 PJ (26.2 PJ after HUGS from 2027), withdrawal ≤ 570 TJ/d (the injection cap is a config parameter). Nominations delivered within ±4% on ≥ 99% of days, with a few exceptions (KPI 1.2). Compressor availability is about 95–98%. |
| Scorecard | FY26 (history) + FY27 Jul–Aug | FY27 statuses as in the image. FY26 full-year for trend. Seed comments from "LLT" and "Board". |
| Documents | ~300 incident reports, ~1,500 invoices, ~40 manuals and procedures, 12 board papers | Generated with reportlab/python-docx from the structured data, so extraction can be scored against the truth |

**Realism gate**: `realism_critic.py` runs over the generated parquet and must PASS. **Calibration gate**: `tests/data/test_calibration.py` asserts the PBI and Tableau totals above.

---

## M. Data model (gold) and KPI definitions

### Conformed dimensions
- **`dim_date`** (2014-01-01..2031-12-31)
  - Columns: `date_key` int yyyymmdd, `date`, `fy` ('FY2027'), `fy_num`, `fy_quarter` ('Q1' = Jul–Sep), `fy_month_num` (Jul = 1), `month_label` ('Jul-26'), `iso_week_start`, `schedule_week` (Monday), `is_weekend`, `vic_public_holiday`, `gas_day`.
  - Key 19000101 is the "Unscheduled" member.
- **`dim_cost_centre`** (SCD2)
  - Columns: `cost_centre_key` (e.g. `ASM-36451-0004`, `PRM-0021E`), `cc_short_name` (HUGS, Project Aegis, CAP, PM and FGH, Project 570, …), `team` (the 14 PBI teams), `function` (Operations, Projects & Growth, Corporate, People Safety & Sustainability), `cost_type` (Opex / Capex / SIB), `plant_area`, `is_active`, `valid_from`/`valid_to`.
  - Prefixes map to areas: ASM = asset maintenance, PRD = production, GNB = general business, GAS = gas ops, PRC/PRM = projects, ZZZ/ZBD/ZSS = corporate.
- **`dim_account`**
  - Columns: `account_key` (623000, 625250, 636100, 161150 'AUC: Gas Storage Plant & Equip', …), `account_name`, `account_group`, `pl_bs`, `capex_flag`.
- **`dim_project`**
  - Columns: `project_key`, `project_name` (Heytesbury Underground Gas Storage (Execute Phase) / (Concept Phase), Queen FEL2, Project Flowbridge, Data Utilisation Project, …), `phase`, `p50_budget` (HUGS $112.4M), `rfsu_target`.
- **`dim_vendor`**
  - Columns: `source_key` `V_101713`, `vendor_name`, `abn` (PII-tagged), `bank_account` (PII-tagged), `category`.
- **`dim_asset`**
  - Iona plant hierarchy: site → area (wells Iona-1..n, compression, dehydration, metering, pipelines/SWP interface, HUGS) → equipment tag, with a `safety_critical` flag.
- **`dim_person`**
  - Columns: `actionee` `JIM.MATTHEWS_LOC`, display name, team. PII-tagged.

### Finance facts
- **`fact_actuals`**: the sample schema plus `posting_date`, `fy`, `team`, `cost_type_class` (Budgeted / Emergent / Blank), and `is_reversal_pair`.
- **`fact_budget`**: budget_name `SITEBUD22..SITEBUD27`, monthly.
- **`fact_yeo`**: `yeo_version` (e.g. `FY27_YEO_M02`), `is_latest`, monthly by CC/account/project.
- **`fact_commitments`**: open PO value = `po_line_cost − received − invoiced`, by PO line, CC and project.
- **`fact_purchase_order_lines`**: the PO drill-through.

**Finance formulas** (these match the PBI columns)
- Variance (ACT vs BUD) = Actuals − Budget
- Variance (YEO vs BUD) = YEO − Budget
- Actuals + Committed = Actuals + Committed Cost
- Variance incl. committed vs BUD = (Act + Committed) − Budget
- Variance incl. committed vs YEO = (Act + Committed) − YEO

Budget and YEO are **full-year** figures for the FY filter. Actuals and Committed are **YTD** to the selected date range. The PBI values confirm this: Budget 51,059K vs Actuals 4,300K for Employee Costs.

### HSE facts
- **`fact_observations`**: one row per observation. It carries observation_type, incident_category, classification, potential/actual risk rank, status, actionee, `reported_date`, `closed_date`, `plant_area` and `description` (free text). The aggregated sample shape is recreated as MV `agg_observations_daily`.
- **`fact_investigations`**.
- **`fact_hse_lagging`**: recordable injuries, hours worked, TRIFR and High Potential Events, for scorecard KPI 1.1.

**HSE formulas**
- Open = status IN ('NEW', 'INPROG')
- Investigations = classification = 'INVESTIGATION'
- Trend = rolling 12-month count by observation_type

### Maintenance facts
- **`fact_workorder`**: Maximo detail.
- **`fact_workorder_schedule_weekly`**: the snapshot grain of the sample, `snapshot_date_key × schedule_week × priority × work_type × wo_class × status × lead_craft`, with all sample measures.

**Maintenance formulas**
- **Current Scheduled Compliance %** = Σ`schedule_compliant_count` / Σ`scheduled_count` for the latest schedule week, from the latest snapshot.
- **Overdue Safety Critical** = Σ`overdue_safety_critical_count` in the latest snapshot.
- **Open P1** = Σ`workorder_count` where priority = P1 and status not in (CLOSE, COMP, CAN, CLOSED).
- **Open P2 excl PMs** is the same with priority = P2 and work_type ≠ PM.
- **Backlog excl PMs** = Σ`backlog_count` where work_type ≠ PM.
- **Scheduled hours** = Σ`est_dur_scheduled`; **Completed hours** = Σ`est_dur_compliant`.

### Market and ops facts
- **`fact_vic_gas_demand_daily`**: `gas_date`, `total_gas_used_gj`, `tj`, `pj`, `data_source` (AEMO / SYNTHETIC), `load_ts`.
- **`fact_edd_daily`**: `edd_date`, `edd_value`, `edd_type`, `edd_update`, `data_source`.
- **`fact_iona_operations_daily`**: injection_tj, withdrawal_tj, inventory_pj, nominations_tj, delivered_tj, `within_tolerance` (|delivered − nominated| ≤ 4%), compressor availability %.
- **`fact_vic_demand_forecast`**.
- **MV `mv_cumulative_demand`**: day-of-year cumulative sums by year, the Tableau `RUNNING_SUM`.

### Board facts
- **`fact_board_scorecard`**: synced from Lakebase; KPI × period × status × weighted scores.

### Metric views (`lochard_semantic`, YAML, one per domain)
The same definitions power dashboards, Genie, the app and agents.

| Metric view | Measures |
|---|---|
| `mv_finance` | budget, actuals, yeo, committed and the 5 variances; dims FY, quarter, month, function, team, cc_short_name, cost_type, project, account |
| `mv_hse` | open/closed/total observations and investigations, trifr, hpe_count |
| `mv_maintenance` | scheduled_compliance_pct, overdue_safety_critical, open_p1, open_p2_excl_pm, backlog_excl_pm, sched_hours, completed_hours |
| `mv_market` | demand_pj, demand_tj, edd, cumulative_demand_pj, forecast_error_pct, nominations_within_tolerance_pct, inventory_pj |
| `mv_board` | weighted_board_score, status_index, kpis_at_risk |

Example (YAML v1.1 syntax, verified against the docs):
```sql
CREATE OR REPLACE VIEW dc_demo_workspace_02_catalog.lochard_semantic.mv_maintenance
WITH METRICS LANGUAGE YAML AS $$
  version: 1.1
  comment: "Maintenance weekly schedule KPIs (Maximo snapshot)"
  source: dc_demo_workspace_02_catalog.lochard_gold.fact_workorder_schedule_weekly
  filter: source.is_latest_snapshot
  fields:
    - { name: schedule_week, expr: source.schedule_week_start, comment: "Monday of the schedule week" }
    - { name: priority,      expr: source.priority_bucket }
    - { name: work_type,     expr: source.work_type }
    - { name: status,        expr: source.status }
    - { name: lead_craft,    expr: source.lead_craft }
  measures:
    - name: scheduled_compliance_pct
      expr: SUM(source.schedule_compliant_count) / NULLIF(SUM(source.scheduled_count), 0)
      comment: "Current Scheduled Compliance % (PBI) – filter to latest schedule_week"
    - name: backlog_excl_pm
      expr: SUM(source.backlog_count) FILTER (WHERE source.work_type <> 'PM')
    - name: open_p2_excl_pm
      expr: SUM(source.workorder_count) FILTER (WHERE source.priority_bucket = 'P2' AND source.work_type <> 'PM'
                                                AND source.status NOT IN ('CLOSE','COMP','CAN','CLOSED'))
    - name: overdue_safety_critical
      expr: SUM(source.overdue_safety_critical_count)
$$;
```

---

## D. Dashboard specifications (replicas)

All four are AI/BI dashboards in the bundle (`resources/dashboards.yml` → `src/dashboards/*.lvdash.json`).

**Common settings**
- **Theme**: Lochard palette, set in the dashboard's `uiSettings.theme`.
- **Header**: a logo image widget top-left (logo served from the app's `/static`, or a public URL), a title and subtitle text widget, and a "Last refreshed" counter from `max(_ingested_at)`.
- **Data**: datasets read only from `lochard_semantic`, which holds metric views plus thin `v_*` views over gold (e.g. `v_finance_transactions` for drill-through). There is one dataset per visual family and business logic lives in SQL. Board and leadership then only need SELECT on `lochard_semantic`. The ABAC masks and row filters on the underlying gold tables are still evaluated as the *viewer*, because `is_account_group_member()` resolves to the invoking user through views.
- **Credentials**: `embed_credentials: false`, so each viewer's own UC permissions apply and ABAC is visible in the dashboards.

**Build workflow**
1. Generate the JSON with an extended `lakeview_builder.py`. It needs new pivot, combo, image, drill-target and theme helpers.
2. `bundle deploy`.
3. Polish in the UI.
4. `databricks bundle generate dashboard --resource <key> --force` to pull the UI changes back into git.

### D1. Finance: "Function Details" (PBI replica)

**Page 1, Function Details**
- **Filters** (global, and they cascade): Function, Team, CC Short Name, Cost Type, Financial Year (default FY2027), Financial Quarter, and a Date Range (default 1/07/2026 to 30/06/2027).
- **Row 1**
  - Donut "Budgeted vs Emergent", split into Blank / Budgeted / Emergent.
  - Combo "Cumulative YEO vs Cumulative Budget", by FY month Jul to Jun. Cumulative YEO is drawn as a stepped area or bar, and Cumulative Budget as a dashed line.
  - Combo "YTD (ACT + Committed Costs) vs YEO": stacked bars for Actuals (grey-brown) and Committed (yellow), with YEO as a dashed line.
- **Row 2**: a pivot table.
  - Rows: Team → CC Short Name → Project Name → Account Name, with subtotals.
  - Columns: Budget, Actuals, Variance (ACT vs BUD), YEO, Variance (YEO vs BUD), Committed Cost, Actuals + Committed Costs, Variance (ACT incl committed vs BUD), Variance (ACT incl committed vs YEO).
  - Values are in K$, and negative variance is shown in red.

**Page 2, Actuals – Transaction Details** (drill-through target)
- Filters: cost centre, team, project and account.
- "YTD ACT by Month" bar chart.
- GL table with Cost Centre Code, WO num, PO num, GL Account Name, GL Account No, Posting Date, Description, Amount, and a total.

**Page 3, PO Transaction Details** (drill-through target)
- PO header and line detail: PO no, vendor, line cost, received, invoiced, and open commitment.

Right-clicking the pivot or a chart and choosing **Drill to** opens page 2 or page 3 with the filters pre-set. This replaces PBI drill-through.

### D2. HSE: "HSE Observations"

- **Subtitle**: "Daily Report To drive timely close-out of hazards and incidents before they escalate".
- **Filters**: Potential Risk Rank, Actual Risk Rank, Class (default INCIDENT), Observation Type, a Date range (1/07/2014 onwards), FY, Quarter, Month.
- **Counters** (6): Open, Closed and Total Investigations; Open, Closed and Total Observations.
  - Calibration targets: 7 / 133 / 140 investigations and 321 / 4,811 / 5,132 observations.
- **Charts**
  - "Total Observations Monthly Trend": lines per observation type showing a rolling 12-month total.
  - Pie "by Incident Category". Calibration targets: General Safety 72.2%, Process Safety 11.0%, Production 10.5%, Environmental 5.5%, Other.
  - Pivot heatmap "By Risk Rank and Reported To": risk rank × CLOSED / INPROG / NEW.
  - Horizontal bar "Open Observations by Risk Rank". Calibration targets: HIGH 7, MEDIUM 34, LOW 35, Unknown 245.

### D3. Maintenance: "Maintenance Dashboard"

- **Header** shows the current Schedule Week and the Data Last Refreshed date.
- **Filters**: Priority, Status, Work Order Type, Schedule Week.
- **Counters** (5). Calibration targets: Current Scheduled Compliance 84%, Overdue Safety Critical WOs 25, Open P1 4, Open P2 excl PMs 635, Backlog excl PMs 5,328.
- **Charts**
  - Combo "Schedule Compliance Trend": bars for Scheduled WO Count and Scheduled Completed, and a line for Completion % on a secondary axis. It shows the last 13 schedule weeks, calibrated to 73.5%, 91.7%, 92.9%, 88.0%, 75.9%, 81.9%, 82.0%, 75.4%, 86.4%, 86.2%, 74.3%, 86.4%, 84.4%.
  - Donut "Scheduled Workorders by type". Calibration targets: PM 67%, GPC 12%, DM 11%, CBM 7%, and so on.
  - Table "Scheduled Workorder Hours by Lead Craft".
  - Clustered bar "Total Scheduled vs Completed Hours by Schedule Week".

### D4. Ops: "Cumulative VIC Demand & EDD" (Tableau replica)

- **Page 1, Cumulative VIC demand**
  - Filters: Year (default 2021–2024 plus the current year) and Month (default 1–8).
  - Line chart: x is the day of year ("date without year", `make_date(year(current_date()), month(gas_date), day(gas_date))`), y is `sum(total_gas_used) over (partition by year order by gas_date)/1e6` in PJ, and colour is the year.
  - Pivot of Month × Year in PJ, to 1 decimal place.
- **Page 2, Cumulative EDD**: the same layout for EDD.
- **Page 3, EDD vs Demand**: a scatter of daily EDD against demand (TJ), coloured weekday/weekend. It adds the regression line and an R² counter per segment. A Day-of-week parameter (Sun..Sat, default Sat) replicates Tableau `Parameter 1`.
- **Page 4, Actual VIC demand**: monthly bars in PJ plus a daily TJ detail table.
- **Page 5, Actual vs Forecast**: actual demand against the custom `vic_gas_demand_forecaster` predictions (section F).

### D5–D7. Platform dashboards (new, production hygiene)

- **D5 "AI Cost & Quality"**: spend by model or tier, route mix, cost per answer, latency, and quality score.
- **D6 "Data Quality & Pipelines"**: expectation pass/fail from the pipeline event logs, freshness and row counts.
- **D7 "Governance & Access Audit"**: `system.access.audit`, policy hits and Genie usage.

---

## S. Board scorecard spec (replica of `fit-scorecard.png`, "2. Scorecard", BPR August 2026)

**Layout**
- A crimson header row with the columns: FY27 Key Performance Indicators | FY27 Deliverables | Owner | Weight | Status.
- Pillars appear as merged row groups on a light-pink band.
- Status pills: On Track (green `#A6E07C`), At Risk (amber `#FFD966`), Off Track (red) and Complete (blue).
- Footnote: "The Board retains full discretion to amend the KPIs and/or FY27 outcome for material events during the year".

**Seed content** (FY27, from the image)

| Pillar | # | KPI | Owner | Weight | Aug-26 status |
|---|---|---|---|---|---|
| HSE & Iona Operations | 1.1 | HSE Performance | DA | 20% | At Risk |
| | 1.2 | Operations & Maintenance Performance | DA/BN | 10% | On Track |
| | 1.3 | Delivery of key FIT program initiatives | LLT | 5% | On Track |
| Growth Delivery | 2.1 | HUGS Delivery | DA/DS | 5% | At Risk |
| | 2.2 | Queen Delivery | DS/DG | 20% | On Track |
| | 2.3 | Growth & Commercial Strategy | DG/BN | 10% | On Track |
| Financial | 3.1 | EBITDA excluding non-cash | LLT | 20% | On Track |
| | 3.2 | TSR per Lochard Corporate Model | LLT | 10% | On Track |

Weights sum to 100%. Every deliverable bullet from the image is stored as a `deliverable` row, so each can be tracked separately.

**Linked evidence**
Where data exists, each KPI links to live metrics in gold:
- **1.1**: TRIFR, High Potential Events and open HIGH-risk observations, from HSE.
- **1.2**: nominations delivered within ±4% (from Iona ops) and schedule compliance (from Maintenance).
- **1.3**: O&M savings against the $250k target, from Finance.
- **2.1**: HUGS actuals and YEO against the $112.4M P50, from Finance.
- **3.1**: EBITDA against budget, from Finance.

---

## Q. "Should we also have AI Functions for document processing?" Yes, recommended

It is the natural fourth leg of the story: unstructured documents become governed tables that feed the same dashboards, Genie and agents. It is cheap (batch SQL on serverless) and shows responsible AI (confidence scores, human review queue). It is built as its own declarative pipeline, `lochard_documents`, with four use cases, each tied to an existing dashboard or scorecard KPI:

| # | Documents (synthetic PDFs/DOCX generated in Phase 1) | AI Functions | Output → consumer |
|---|---|---|---|
| 1 | HSE incident and investigation reports (about 300) | `ai_parse_document` → `ai_extract` (date, location/plant area, equipment tag, injury type, immediate cause, root cause, corrective actions) → `ai_classify` (incident category, potential risk rank) → `ai_mask` (names) | `lochard_silver.hse_incident_reports_parsed`. Where the AI-suggested risk rank differs from the one logged, the report goes to a **human review queue** in the HSE Genie and the app. This also tidies the "Unknown" risk-rank backlog (4,387 rows in the PBI matrix). |
| 2 | Supplier invoices and PO documents (about 1,500) | `ai_parse_document` → `ai_extract` (vendor, ABN, invoice no, PO no, line items, GST, total) | `lochard_gold.invoice_three_way_match`: invoice vs PO vs GL `fact_actuals`, with exceptions shown on the Finance drill-through |
| 3 | Maintenance procedures and OEM manuals (compressor, dehydration, wellhead) | `ai_parse_document` → chunking → Vector Search (serverless) | The **Knowledge Assistant** "Iona Maintenance Advisor", used by the Supervisor Agent |
| 4 | Monthly KPI owner updates and board papers | `ai_summarize` / `ai_query` (economy tier via Gateway) | Draft scorecard commentary in the app, marked "AI draft". It is published only after the KPI owner **accepts or edits** it (human-in-the-loop). |

**Quality controls**
- **Expectations**:
  - parse success ≥ 98%;
  - `ai_extract` required fields not null (warn);
  - invoice total = sum(lines) + GST ± $0.05 (quarantine).
- **Evaluation**: a hand-labelled sample of 50 documents in `lochard_ai.doc_eval_labels`, used to report extraction accuracy.

---

## G. Governance design (RBAC + row/column + ABAC)

### Personas and groups
These are account-level groups; see Risk R1 for the fallback if we cannot create them.

| Group | Who | Sees |
|---|---|---|
| `lochard_data_engineers` | Platform team | Owns bronze and silver. Can MODIFY in gold. |
| `lochard_finance` | Finance team | All finance gold, unmasked |
| `lochard_hse` | HSE team | All HSE data including investigations and actionee names |
| `lochard_maintenance` | Maintenance planners | Maintenance gold. Finance only for maintenance cost centres. |
| `lochard_operations` | Control room / Ops | Market and ops gold; maintenance gold |
| `lochard_leadership` | LLT | All gold and semantic data. PII masked except for their own domain. |
| `lochard_board` | Directors | `lochard_semantic` metric views, dashboards, Genie and the app only. PII always masked. No investigation detail. |
| `lochard_team_<team>` (e.g. `lochard_team_major_projects`) | Budget holders | Finance rows for their Team only |
| `sp-lochard-app`, `sp-lochard-pipelines` | Service principals | App runtime; prod `run_as` |

**Genie One access**: `lochard_board` and `lochard_leadership` are given the **Consumer access** entitlement only, so they land on the Genie One homepage.

### RBAC grants
- **Catalog**: `USE CATALOG` for all `lochard_*` groups.
- **`lochard_bronze` and `lochard_silver`**: engineers only.
- **`lochard_gold`**: SELECT for the domain groups, each on its own tables (the table-level grants are in `src/governance/02_grants.sql`).
- **`lochard_semantic`**: SELECT and EXECUTE for all consumer groups including leadership and board. This is the **only** schema the board can read. Dashboards, the Executive Genie and the app all query it.
- **`lochard_ai`**: EXECUTE on the model services for the app SP and leadership; engineers get MANAGE.

### Governed tags
These are account-level tag policies with fixed allowed values:
- `lochard_domain`: finance / hse / maintenance / market / board
- `lochard_sensitivity`: internal / confidential / board_confidential
- `lochard_pii`: person_name / email / phone / bank
- `lochard_rls`: team / investigation. This is a *table* tag that turns a row policy on.
- `lochard_key`: team / hse_classification / cost_centre. This is a *column* tag that tells the policy which column to filter on.

Tags go on tables and columns in `src/governance/03_tags.sql`. UC **Data Classification** also runs on the catalog to auto-detect PII, and its detections are reconciled with our tags.

### ABAC policies
These are defined on the schemas and hold UDFs from `lochard_governance`. The syntax is verified against the docs.

```sql
-- Mask person names (HSE actionee, WO owner, GL "employee" descriptions) for everyone except HSE/Finance owners
CREATE FUNCTION lochard_governance.mask_person(v STRING) RETURNS STRING
  RETURN concat(left(v,1), '***_LOC');   -- policy EXCEPT clause decides who bypasses
CREATE POLICY pii_person_mask ON SCHEMA dc_demo_workspace_02_catalog.lochard_gold
  COLUMN MASK lochard_governance.mask_person
  TO `account users` EXCEPT `lochard_hse`, `lochard_data_engineers`
  FOR TABLES MATCH COLUMNS has_tag_value('lochard_pii','person_name') AS c ON COLUMN c;

-- Budget holders see only their Team's rows (entitlement table maps group -> team).
-- Finance, LLT and Board see all teams (board still gets confidential descriptions masked).
CREATE FUNCTION lochard_governance.rls_team(p_team STRING) RETURNS BOOLEAN
  RETURN EXISTS (SELECT 1 FROM lochard_governance.team_entitlements e
                 WHERE e.team = p_team AND is_account_group_member(e.group_name));
CREATE POLICY finance_team_rls ON SCHEMA dc_demo_workspace_02_catalog.lochard_gold
  ROW FILTER lochard_governance.rls_team
  TO `account users` EXCEPT `lochard_finance`, `lochard_leadership`, `lochard_board`, `lochard_data_engineers`
  FOR TABLES WHEN has_tag_value('lochard_rls','team')
  MATCH COLUMNS has_tag_value('lochard_key','team') AS t USING COLUMNS (t);

-- HSE investigation rows hidden outside HSE/LLT. Row filters also apply through views, so the
-- board's investigation COUNTS come from untagged aggregate gold.agg_hse_investigation_counts (no row detail).
CREATE FUNCTION lochard_governance.rls_investigation(p_class STRING) RETURNS BOOLEAN
  RETURN p_class <> 'INVESTIGATION';
CREATE POLICY hse_investigation_rls ON SCHEMA dc_demo_workspace_02_catalog.lochard_gold
  ROW FILTER lochard_governance.rls_investigation
  TO `account users` EXCEPT `lochard_hse`, `lochard_leadership`, `lochard_data_engineers`
  FOR TABLES WHEN has_tag_value('lochard_rls','investigation')
  MATCH COLUMNS has_tag_value('lochard_key','hse_classification') AS c USING COLUMNS (c);
```

We also add **column masks** for:
- `dim_vendor.bank_account` and `abn` (`lochard_pii=bank`), visible to Finance only;
- `fact_actuals.description` and `amount` on Legal and Employee Costs rows (`lochard_sensitivity=confidential`), for anyone outside `lochard_finance` and `lochard_leadership`.

We also add classic table-level `ROW FILTER` / `MASK` examples on one table, to contrast them with ABAC.

### Verification
`tests/governance/test_personas.py` runs the same queries under one **service principal per persona** (OAuth M2M, secret scope `lochard-governance-test`). It asserts:
- row counts, e.g. `lochard_team_major_projects` sees only the Major Projects rows;
- masked values, e.g. `actionee LIKE '%***%'`;
- that investigations are absent.

These tests also run as a CI job after every deploy. For a live demo, the presenter adds or removes themselves from a group and re-runs the dashboard, Genie or the app.

---

## N. Genie Agents (formerly Genie spaces) + Genie One

There are five Genie Agents, all in the bundle (`resources/genie.yml` → `src/genie/*.json`, `serialized_space` **version 2**).
- Authoring rules: arrays sorted, 32-hex IDs, and `join_specs` with a relationship annotation.
- Each agent has: `data_sources` (gold tables and metric views only), text instructions, `example_question_sqls`, `sql_snippets` (measures/filters), `sql_functions` (trusted UC functions) and `benchmarks` (≥ 25 questions with ground-truth SQL).

| Genie Agent | Data | Example instructions and trusted assets |
|---|---|---|
| **Lochard Finance** | fact_actuals, fact_budget, fact_yeo, fact_commitments, dims, `mv_finance` | "FY runs 1 Jul–30 Jun (FY2027 = Jul-26..Jun-27)". "Variance = Actual − Budget; negative = under-spend". "YEO = latest Year End Outlook version". Trusted fn `finance_variance(team, fy)` |
| **Lochard HSE** | fact_observations, fact_investigations, parsed incident reports, `mv_hse` | "Open = status IN ('NEW','INPROG')". "Investigations = classification='INVESTIGATION'". Rolling 12-month definitions |
| **Lochard Maintenance** | fact_workorder_schedule_weekly, fact_workorder, dim_asset, `mv_maintenance` | Schedule compliance formula, "Backlog excludes PMs", P1/P2 definitions |
| **Lochard Gas Market & Iona Ops** | fact_vic_gas_demand_daily, fact_edd_daily, fact_iona_operations_daily, forecasts, `mv_market` | GJ→TJ→PJ conversions, gas day, EDD meaning, weekday/weekend |
| **Lochard Executive & Board** | `lochard_semantic` metric views across domains + fact_board_scorecard (synced from Lakebase) | "Summarise at KPI level; never show individual names". Used by the app and Genie One |

**Genie One demo steps**
1. Grant **Consumer access** to `lochard_board` and `lochard_leadership`.
2. Customise the Genie One homepage (welcome text, pinned: the 4 dashboards, the Executive Genie Agent, the board portal app).
3. Show a board member asking cross-domain questions ("How are we tracking against the FY27 scorecard and what's driving HSE At Risk?").
4. Show that answers respect ABAC: names are masked and no investigation rows appear.
5. Show citations/SQL and thumbs feedback.

Benchmarks run in CI with a target of **≥ 90% "good"** before prod deploy.

---

## F. AI: Unity AI Gateway, custom models, routing, cost, agents, responsible AI

### F1. Model services (UC securables in `lochard_ai`; bundle `model_services` after the CLI upgrade, otherwise REST)
Every service has usage tracking and an inference table (`lochard_ai.<service>_payload`), budget-policy tags `project=lochard` and `use_case=…`, rate limits and guardrails.

| Service | Destinations (all confirmed READY on the workspace today, 55 endpoints) | Purpose |
|---|---|---|
| `lochard_llm_premium` | `databricks-claude-opus-5-5` (primary 100%) → fallback `databricks-gpt-6-sol` | Complex reasoning, board narrative |
| `lochard_llm_standard` | `databricks-claude-sonnet-5` → fallback `databricks-gpt-5-5` | Default for agents and Q&A |
| `lochard_llm_economy` | `databricks-claude-haiku-4-5` → fallback `databricks-gemini-3-8-flash` | Classification, summaries, AI Functions |
| `lochard_llm_open` | `databricks-gpt-oss-120b` / `databricks-qwen35-122b-a10b` / `databricks-meta-llama-3-3-70b-instruct` | Open-weights tier for the cost comparison |
| **`lochard_assistant`** ("the custom model") | **Smart routing** across the three tiers if the workspace has it. Otherwise a 70/20/10 traffic split plus a fallback chain. | Single governed endpoint the app, agents and notebooks call |
| `lochard_router` | Destination = **custom served model** `lochard_ai.lochard_router_agent` (MLflow pyfunc). The economy tier classifies complexity/intent, then the request is sent to the right tier, and the route plus the reason are returned. | Explainable, code-level routing to contrast with Gateway smart routing |
| `lochard_demand_forecaster` | Destination = serving endpoint for UC model `lochard_ai.vic_gas_demand_forecaster` (serverless CPU, scale-to-zero) | Custom ML model governed by the same Gateway |

**Controls**
- **Rate limits**:
  - per user 30 QPM on premium;
  - `lochard_board` 60 QPM on `lochard_assistant`;
  - app SP 300 QPM.
- **Spend controls**: premium has a monthly budget (e.g. USD 500) with alerts at 50/80/100% and a hard cap. When the cap is hit, `lochard_assistant` falls back to standard.
- **Guardrails** (service policies, Beta):
  - PII detect-and-mask on requests and responses;
  - prompt-injection block;
  - unsafe-content block;
  - custom "board-confidential" deny on export-style requests.

### F2. Custom ML model: `vic_gas_demand_forecaster`
- **Approach**: this echoes the Tableau R² sheets. Features are EDD, weekday/weekend, public holiday, month and lagged demand. Models are a LightGBM model and a linear EDD regression baseline, trained on `lochard_gold` history.
- **MLflow and UC**: runs are logged in MLflow 3, registered in UC with a `@champion` alias, and have a model card in the UC comment/tags.
- **Serving**: `model_serving_endpoints` in the bundle, served through Gateway.
- **Scoring**: a batch job writes `lochard_gold.fact_vic_demand_forecast` with `ai_query`, for dashboard D4 page 5.
- **Tool use**: the same model is exposed to agents as UC function `lochard_semantic.forecast_vic_demand(start_date, days)`.

### F3. Cost-management and routing experiment (`src/ai/cost_explorer.py`, a job and notebook)
1. Build a 60-question set from the Genie benchmarks plus board-style questions, stored in `lochard_ai.eval_questions`.
2. Run the set through premium / standard / economy / `lochard_assistant` (smart) / `lochard_router` (custom).
3. Score quality with MLflow GenAI judges: Correctness (vs expected), Guidelines ("AUD, FY terms, no names"), Safety and RelevanceToQuery.
4. Collect tokens, latency and cost from the Gateway usage/inference tables and `system.billing.usage` joined to `system.billing.list_prices`.
5. Write `lochard_ai.model_cost_experiment` and show it in D5 as a **cost vs quality frontier**. Hypothesis to test: routed ≥ 95% of premium quality at ≤ 40% of premium cost. The actual numbers are reported as measured.

### F4. Agents
- **Supervisor Agent "Lochard Leadership Analyst"** (Agent Bricks), used by the app's Ask panel:
  - sub-agents: the 5 Genie Agents;
  - the Knowledge Assistant **"Iona Knowledge"** over parsed procedures, OEM manuals, board papers and policies (Vector Search);
  - UC function tools: `forecast_vic_demand`, `get_scorecard(period)`, `finance_variance`;
  - the model is `lochard_assistant`.
- **Code-first agent (exploration)**: `src/agents/ops_agent/` uses MLflow `ResponsesAgent` with Databricks **managed MCP servers** (Genie, UC functions, Vector Search) over `lochard_assistant`. It is deployed via `agents.deploy`, and its traces go to MLflow experiment `/Shared/lochard/agents`. This shows how agents are built, governed (`mcp_service` in Gateway) and evaluated.

### F5. Responsible AI (demo-able controls)

| Principle | Control on Databricks | Where it is shown |
|---|---|---|
| Only governed data | Genie, agents and the app use OBO user identity, so UC ABAC applies to every answer | A board member sees masked names |
| Transparency | Genie shows generated SQL and citations; the app labels "AI draft"; agents return sources | App Ask panel, Genie One |
| Human in the loop | Scores and status are only ever human-entered. AI commentary needs explicit accept/edit. AI-vs-logged risk-rank mismatches go to a review queue. | Scorecard, HSE |
| Safety guardrails | Gateway PII, prompt-injection and unsafe-content policies | A live blocked injection attempt |
| Evaluation before release | Genie benchmarks ≥ 90%; MLflow judge thresholds in CI | D5, CI job |
| Monitoring and feedback | Inference tables, usage tables, app thumbs → MLflow assessments → new benchmarks | D5, D7 |
| Cost accountability | Tiering, routing, budgets and hard caps, tags on all serverless spend | D5 |
| Auditability | Lakebase `audit_log`, `system.access.audit`, UC lineage from source to dashboard, Genie and model | D7, Catalog Explorer |

---

## A. Board portal app: `lochard-board-portal` (FastAPI + React + Lakebase Autoscaling)

### A1. Lakebase (bundle `postgres_projects`, `postgres_branches`, `postgres_endpoints`, `postgres_databases`)
- **Project**: `lochard-board-portal`, pg 17, with `custom_tags` `project=lochard`.
- **Branches**:
  - `production`, which is protected;
  - `dev`, branched from production, used by the dev target. Schema migrations are tested on the branch first (Lakebase branching shown as a feature).
- **Endpoint**: autoscaling 0.5–4 CU with scale-to-zero on dev. The database is `board_portal`.
- **App binding**: `postgres: {branch, database, permission: CAN_CONNECT_AND_CREATE}`. The app SP connects with an OAuth token through a psycopg pool with `max_lifetime=2700` (skill pattern).
- **Migrations**: Alembic is `src/app/server/migrations/` and runs at app startup under an advisory lock.

### A2. Postgres schema `scorecard` (DDL outline)
```
fiscal_year(fy_code PK 'FY27', start_date, end_date, status)
pillar(pillar_id PK, fy_code FK, name, sort)                             -- HSE & Iona Operations | Growth Delivery | Financial
kpi(kpi_id PK, fy_code, pillar_id, code '1.1', name, owner_initials, owner_email, weight_pct, footnote, metric_binding jsonb)
deliverable(deliverable_id PK, kpi_id, seq, text, target, measure_type)  -- each bullet in the image
reporting_period(period_id PK 'FY27-M02', fy_code, month_start, board_meeting_date, state)  -- OPEN|OWNER_SUBMITTED|LLT_REVIEWED|BOARD_ENDORSED|LOCKED
kpi_status_update(update_id PK, kpi_id, period_id, status enum(ON_TRACK,AT_RISK,OFF_TRACK,COMPLETE), owner_score 0-5, achievement_pct,
                  commentary, ai_draft_commentary, ai_draft_accepted bool, submitted_by, submitted_at, version)
board_score(score_id PK, kpi_id, period_id, director_email, score 0-5, rationale, created_at)     -- individual director scores
comment(comment_id PK, kpi_id, period_id, parent_id, author_email, author_role, body, visibility enum(ALL,BOARD_ONLY,LLT_ONLY), created_at, edited_at, resolved)
approval(approval_id PK, period_id, stage, approver_email, decision, note, decided_at)
audit_log(id PK, actor_email, action, entity, entity_id, before jsonb, after jsonb, at)          -- append-only via trigger
app_user_role(email PK, role enum(BOARD,LLT,KPI_OWNER,ADMIN), display_name)                        -- seeded from UC groups
genie_conversation(id PK, user_email, space_id, conversation_id, title, created_at)                -- Ask history
```
- **Weighted score per period**: `Σ(weight_pct × avg(board_score)/5)`. Status points are On Track = 1.0, At Risk = 0.5, Off Track = 0, Complete = 1.0, giving a status-weighted index. Both are shown so the board can compare its own judgement with the owners' self-assessments.
- **Row visibility**: `BOARD_ONLY` comments are enforced in the API layer by role.

### A3. Backend API (FastAPI, `src/app/server/routes/`)
- **Scorecard**
  - `GET /api/scorecard/{fy}/{period}`: the full grid with status, weights and latest comments.
  - `POST /api/kpi/{id}/status` (owner).
  - `POST /api/kpi/{id}/score` (board).
  - `POST /api/kpi/{id}/comments`, `PATCH /api/comments/{id}`.
  - `POST /api/period/{id}/advance` (workflow; checks role), `GET /api/period/{id}/history`.
  - `POST /api/kpi/{id}/ai-draft`: builds commentary from linked gold metrics through `lochard_llm_economy` and returns an unsaved draft.
  - `GET /api/export/{period}.pptx|pdf`: the board-pack slide in the same layout as the image.
- **Insights** (OBO → SQL warehouse → `lochard_semantic` metric views)
  - `GET /api/insights/trends?domain=`: KPI time series and sparklines;
  - `GET /api/insights/highlights`: anomaly callouts;
  - `GET /api/kpi/{id}/evidence`: live metrics bound to the KPI.
- **Ask** (OBO): `POST /api/ask` streams from the Supervisor Agent via Gateway, or goes to the Genie Conversation API for the Executive Genie Agent (toggle). `POST /api/ask/feedback` sends MLflow assessments.
- **Embed**: `GET /api/dashboards` lists the dashboard ids and embed URLs, taken from bundle variables and env.
- **Admin**: `GET /api/admin/ai-cost` (D5 data), `GET /api/me` (roles from SCIM groups).

### A4. Auth split
- **User authorization (OBO)**, `user_api_scopes: [sql, genie, ai-gateway, model-serving]`. This covers all analytics, Genie, agent and Gateway calls, so ABAC and row filters and audit apply to the real person.
- **App SP**: Lakebase reads and writes only (the scorecard is the app's own data), plus the startup migrations.
- **In-app roles**: mapped from UC groups (`lochard_board` → BOARD, `lochard_leadership` → LLT, KPI owner by email in `kpi.owner_email`, `admins` → ADMIN).

### A5. Frontend (React + Vite + TypeScript, Lochard theme from `extract_brand.py` evidence)

**Working palette** until `extract_brand.py` confirms the site CSS:
- crimson `#A3174F` (the scorecard header; primary);
- pink band `#F3E3E9`;
- warm grey-brown `#5E5552` (PBI table headers);
- orange `#E8650A`, yellow `#FFC000`, sky `#4FB3E8`;
- status green `#A6E07C` and amber `#FFD966`;
- text `#1E1E1E` on `#F5F5F5`.

The logo swirl (orange, yellow, blue) is taken from the site and not redrawn.
- **Scorecard**: a pixel-faithful replica of the slide grid.
  - Clicking a KPI opens a drawer with deliverables, evidence metrics, the status update form, director scoring, a threaded comment box, and history.
  - A period switcher and a workflow stepper sit at the top.
- **Leadership Insights**: KPI tiles with sparklines per domain (Finance YEO vs Budget, HSE open HIGH risks and TRIFR, Maintenance compliance and backlog, Iona inventory and nominations ±4%, cumulative VIC demand vs prior years). An "Ask a question" panel shows the answer, SQL and sources, with thumbs up/down.
- **Dashboards**: tabs with the 4 replica dashboards embedded as **iframes** (basic embedding, viewer's own identity). There is also an "Open in Genie One" button.
  - Prerequisites: a workspace admin allow-lists the app domain (`*.databricksapps.com`, or the exact app URL) under Settings → Security → Embed dashboards. Viewers need third-party cookies enabled for `*.databricks.com`.
  - A banner with a fallback link is shown if the iframe fails to load.
- **AI Cost** (admin): the D5 dashboard embedded, plus the live routing log.
- **About / Architecture**: a medallion + governance + AI diagram, and a list of the deployed objects.

### A6. Lakebase → Delta
The job `lochard_scorecard_sync` runs nightly and when a period is LOCKED. It reads Lakebase (psycopg, SP) and MERGEs into `lochard_gold.fact_board_scorecard` and `lochard_gold.fact_board_comments_summary` (names are tagged PII). The Executive Genie and Genie One can then trend scorecard history. We avoid registering Lakebase as a UC catalog because that adds a second catalog, and the brief is a single catalog. It stays as an optional variant, named `lochard_board_portal_pg`, alongside Lakebase **synced tables** that push gold KPIs into Postgres for sub-10 ms reads.

---

## R. Risks, unknowns and mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Account-admin rights unknown.** UC grants and ABAC need *account* groups, and governed tags need account-level tag policies. | Phase 0 runs `databricks auth login --host https://accounts.cloud.databricks.com --account-id 05d08df7-…` and then `account groups list`. If we are not admin: (a) create groups in the workspace admin UI, which in identity-federated workspaces creates account groups, and verify with `SELECT is_account_group_member('lochard_hse')`; (b) otherwise ask the FEVM owner; (c) as a last resort, row filters and masks key off `current_user()` via the `lochard_governance.user_entitlements` table, with plain (non-governed) tags plus table-level row filters and masks. |
| R2 | Gateway **service policies (Beta)** and **smart routing** may not be enabled | Ask the account admin to enable the Unity Gateway preview. Without it, fall back to traffic-split plus fallback routing and the custom `lochard_router` model (which works regardless). Guardrails are then shown via AI Gateway on serving endpoints (safety/PII) if available. |
| R3 | `model_services` is not in the CLI v1.6.0 bundle schema | Upgrade the CLI (`brew upgrade databricks`) and re-check `bundle schema`. Fallback: `src/ai/setup_model_services.py`, which creates or updates idempotently via the UC REST API, run as a job task after deploy. |
| R4 | Serverless egress to `nemweb.com.au` blocked by a network policy | Check with a one-off job run in Phase 1. Fallback: download locally and `databricks fs cp` to the volume, or use a serverless egress policy allow-list. The synthetic history makes the demo work regardless. |
| R5 | Iframe embedding needs the app domain allow-listed and third-party cookies | Workspace admin setting in Phase 8. The app shows a fallback "open in Genie One" link. |
| R6 | The `genie_spaces` `serialized_space` format is strict (sorted arrays, IDs) | Generate it with `src/genie/build_space.py` (sort and ID helpers) and validate with a dry-run create in dev. After tuning in the UI, round-trip with `databricks bundle generate genie-space --key <k> --existing-… --bind`, which is available in CLI v1.6.0. |
| R7 | Data residency: the workspace is **us-east-1**, and Lochard's real production must be **ap-southeast-2 (Sydney)** | Record this in the ADR. The bundle is region-agnostic; only the target host changes. |
| R8 | Endpoint names and versions change (new Claude/GPT releases) | Bundle variables per tier; `serving-endpoints list` check in Phase 0. |
| R9 | Real AEMO data is only ~30–60 days, so there is a synthetic/real seam | Calibrate the synthetic last 90 days to real levels. The MERGE prefers `source='AEMO'`, and a `data_source` column is shown in D4. |
| R10 | Genie / FMAPI rate limits (a 429 was seen on this workspace today for gpt-5-mini) | Tiered models, retries with backoff in the app, and pre-warmed demo questions. |
| R11 | ABAC policy support on **pipeline-managed** gold tables (MVs and streaming tables) may be limited | Test in Phase 4 on one MV first. Fallback: declare `ROW FILTER` / `MASK` in the SDP table definitions, or publish consumer gold as plain Delta tables written by a final pipeline sink. The governance story is unchanged. |
| R12 | Row filters flow through views and metric views, so aggregates for restricted personas shrink (e.g. the board's investigation count) | Provide untagged aggregate tables for counts the board is allowed to see (`agg_hse_investigation_counts`). Persona tests assert both row hiding and correct aggregates. |
| R13 | The Supervisor Agent may call its Genie sub-agents as the endpoint identity rather than the end user, which would bypass per-user ABAC | Enable on-behalf-of-user auth for the Supervisor and Genie tools and verify with persona tests. Fallback: the app's Ask toggle calls the Genie Conversation API directly with the OBO token, which always respects the user. |

---

## I. Implementation phases (ordered; each ends with a verification gate)

Every phase ends with `databricks bundle validate -t dev && databricks bundle deploy -t dev`. Prod promotion is `-t prod`, which runs as `sp-lochard-pipelines`.

**Phase 0: Foundations (bundle skeleton, access checks)**
1. Copy this plan to `lochard-llt/PLAN.md`. Run `git init` with a `.gitignore` covering `node_modules`, `.venv`, `__pycache__`, `.databricks` and `/tmp`.
2. `brew upgrade databricks`, then confirm that `bundle schema` contains `model_services` (R3).
3. Access checks: account admin (R1), the Unity Gateway preview (R2), Genie One enabled, and Consumer access available.
4. Create `databricks.yml`:
   - bundle `lochard-data-platform`;
   - variables `catalog`, `prefix`, `warehouse_id`, `app_name`, `premium_model`/`standard_model`/`economy_model`, `nemweb_base_url`;
   - targets `dev` (`mode: development`, `prefix: lochard_dev_`) and `prod` (`mode: production`, `prefix: lochard_`, `run_as` SP, `presets.tags`);
   - `include: resources/**/*.yml`.
5. Create `resources/schemas.yml` (the 8 schemas), `resources/volumes.yml` (`raw`, `documents`, `checkpoints`), `resources/warehouse.yml` (serverless `lochard-serverless-wh`) and the budget policy (workspace setting, referenced by id).
6. Groups and service principals: `src/governance/00_identities.py`, idempotent via SDK/SCIM, with the R1 fallback.
- **Verify**: `bundle deploy -t dev`; `SHOW SCHEMAS IN dc_demo_workspace_02_catalog LIKE 'lochard*'` returns 8; the volumes exist; the groups resolve.

**Phase 1: Sample data + AEMO ingestion**
1. `src/data_generation/` contains `config.py` (calibration targets), `seed_from_excel.py`, `gen_finance.py`, `gen_hse.py`, `gen_maintenance.py`, `gen_market_ops.py`, `gen_scorecard.py`, `gen_documents.py` and `writer.py` (source-format files into volumes).
2. Job `resources/jobs/generate_data.yml` runs on serverless with an environment that includes `polars`, `mimesis`, `openpyxl`, `reportlab` and `python-docx`. It has `mode=backfill|incremental` parameters.
3. `src/ingest/aemo_nemweb.py` downloads `int091_v4_eddact_1.csv` and `int287_v4_gas_consumption_1.csv` to `/Volumes/…/raw/aemo/<report>/load_date=…/`, keeping the original filename plus a timestamp. The job `resources/jobs/aemo_ingest.yml` runs daily at 15:00 AEST (INT091 publishes ~14:00).
- **Verify**: file counts per entity; `realism_critic.py` passes; the calibration tests pass; an AEMO file lands (R4).

**Phase 2: Bronze → Silver → Gold pipelines**
1. `src/pipelines/{finance,hse,maintenance,market_ops,documents}/`. Bronze, silver and gold go in separate SQL or Python files per layer, plus `expectations.py`.
2. `resources/pipelines/*.yml` (serverless, multi-schema publishing).
3. Orchestrator job `resources/jobs/daily_orchestrator.yml`:
   - `aemo_ingest` → `generate_data(incremental)`;
   - then pipeline tasks for finance, hse, maintenance and market_ops in parallel;
   - then `documents`, `forecast_batch`, `scorecard_sync` and `dq_checks`;
   - it has failure email and SQL **alerts** (`resources/alerts.yml`) for DQ breach and freshness.
- **Verify**:
  - all pipelines are green;
  - the expectation metrics in the event log show the injected defects caught;
  - UC lineage runs from bronze to gold;
  - the gold row counts and KPI queries match the PBI calibration numbers (a test SQL suite in `tests/sql/`).

**Phase 3: Semantic layer**
1. `src/semantic/mv_*.yaml` metric views, created by `CREATE VIEW … WITH METRICS LANGUAGE YAML`.
2. The trusted functions `finance_variance`, `forecast_vic_demand` and `get_scorecard`.
3. A job task `semantic_deploy` runs after the pipelines. It uses SQL files, because metric views are not bundle resources.
4. Two objects are deferred until their inputs exist: `mv_board` in Phase 8, after `fact_board_scorecard`, and `forecast_vic_demand` in Phase 7, after the forecaster endpoint.
- **Verify**: `SELECT MEASURE(scheduled_compliance_pct) FROM mv_maintenance WHERE schedule_week = '2026-07-27'` returns 84.4%.

**Phase 4: Governance**
1. `src/governance/01_tag_policies.sql|py`, `02_grants.sql`, `03_tags.sql`, `04_udfs.sql`, `05_abac_policies.sql` and `06_classic_row_filters.sql`.
2. Run as job `governance_setup` after the semantic layer, so it is idempotent: `CREATE OR REPLACE`, `DROP POLICY IF EXISTS`.
3. Enable UC Data Classification on the catalog.
- **Verify**: `tests/governance/test_personas.py` runs per-persona SP queries and asserts the row counts and masked values.

**Phase 5: Dashboards**
1. `src/dashboards/build/*.py` (the extended `lakeview_builder.py`) creates `src/dashboards/{finance_function_details,hse_observations,maintenance,ops_vic_demand_edd,ai_cost_quality,data_quality,governance_audit}.lvdash.json`.
2. `resources/dashboards.yml` sets `warehouse_id`, `embed_credentials: false` and permissions (CAN_RUN for domain groups and board).
3. Lochard theme and drill-through pages.
4. Subscriptions (a weekly Maintenance PDF to planners, a daily HSE report). These are not bundle fields, so `src/dashboards/post_deploy.py` creates them through the Lakeview schedules API.
- **Verify**:
  - a side-by-side screenshot comparison with the PBI and Tableau images using chrome-devtools;
  - the counter values equal the calibration targets;
  - drill-through works;
  - a board persona sees masked names.

**Phase 6: Genie Agents + Genie One**
1. `src/genie/build_space.py` generates `src/genie/*.json` (serialized_space v2), and `resources/genie.yml` defines the 5 `genie_spaces`.
2. Benchmarks are included. The job `genie_benchmarks` runs them via API and fails the job if accuracy is below 90%.
3. Genie One setup: Consumer entitlement for the board and leadership groups, homepage customisation (a documented manual admin step), and pinned assets.
- **Verify**: benchmark score; 10 scripted demo questions per space answered correctly as the board persona.

**Phase 7: AI — Gateway, custom models, documents, agents**
1. `resources/ai_gateway.yml` holds the model services from F1, or `src/ai/setup_model_services.py` as the fallback. Configure rate limits, spend budget and alerts, guardrails, and inference tables.
2. Forecaster:
   - `src/ml/train_forecaster.py` → a UC registered model with alias `@champion`;
   - `resources/serving.yml` for the serverless endpoint;
   - the batch-scoring task.
3. `lochard_router_agent`: `src/ai/router/` (MLflow pyfunc) → registered → served → a `lochard_router` model service.
4. Documents pipeline live. Knowledge Assistant "Iona Knowledge" over `gold.doc_chunks` (Vector Search endpoint in the bundle, `databricks-gte-large-en` embeddings). Supervisor Agent "Lochard Leadership Analyst", created with an API script because Agent Bricks is not a bundle resource.
5. `src/agents/ops_agent/` code-first agent using managed MCP, plus MLflow evaluation.
6. `src/ai/cost_explorer.py` experiment → `lochard_ai.model_cost_experiment` → D5.
- **Verify**:
  - the Gateway usage and inference tables populate;
  - a spend alert fires on a test budget;
  - the guardrail blocks the red-team prompts in `tests/ai/redteam.jsonl`;
  - MLflow evaluation meets its thresholds;
  - the forecaster MAPE is below 8% on holdout.

**Phase 8: Lakebase + board portal app**
1. `resources/lakebase.yml`: project, `production` + `dev` branches, endpoint, database.
2. `resources/app.yml`:
   - `source_code_path: ../src/app`, `user_api_scopes`;
   - resources: postgres (CAN_CONNECT_AND_CREATE), sql_warehouse (CAN_USE), serving endpoints and genie spaces (CAN_RUN), plus permissions.
3. `src/app/` contains `app.yaml`, `app.py`, `pyproject.toml`, `server/{config,db,llm,genie,sql,auth}.py`, `server/routes/*` and `server/migrations/`, and `frontend/` (React + Vite + TS, built `dist/` committed).
4. The workspace admin allow-lists the app domain for dashboard embedding (R5).
5. Seed data: `src/app/server/seed/fy27_scorecard.yaml`, transcribed from `fit-scorecard.png` (pillars, KPIs, every deliverable bullet, owners, weights, the Jul/Aug-26 statuses). `gen_scorecard.py` adds FY26 history and fictitious comments. Both load through the migration seed step.
6. Job `scorecard_sync`, then create `mv_board` (the deferred step from Phase 3).
- **Verify** with the web-devloop-tester agent and chrome-devtools:
  - the scorecard renders like the image;
  - an owner can submit status, a director can score and comment, and the workflow advances;
  - the audit log is written;
  - the embedded dashboards load;
  - Ask answers with SQL shown;
  - OBO identity is respected (masked for board);
  - after the sync, Delta `fact_board_scorecard` has the rows.

**Phase 9: CI/CD, ops and handover**
1. GitHub Actions `.github/workflows/{validate,deploy-dev,deploy-prod}.yml` run `bundle validate` / `deploy`, unit tests (generators, KPI SQL), governance tests and Genie benchmarks. Prod is gated on approvals.
2. Runbook `docs/RUNBOOK.md` (SLAs, failure handling, backfill, rotating nemweb), ADRs `docs/adr/*.md` (e.g. data residency R7, the Lakebase-vs-Delta split, one pipeline per domain), and the demo run-sheet `docs/DEMO_SCRIPT.md`.

---

## V. End-to-end verification checklist

1. `databricks bundle validate -t dev` shows no warnings. `bundle deploy -t dev` then `bundle run daily_orchestrator -t dev` succeeds end-to-end on serverless only: no classic clusters appear in `system.compute.clusters`.
2. The KPI test suite (`tests/sql/kpi_calibration.sql`) matches:
   - FY27 Budget 180.2M, YTD Actuals 3.78M, YEO 71.3M;
   - HSE 5,132 / 321 / 140 / 7;
   - Maintenance 84% / 25 / 4 / 635 / 5,328;
   - Tableau monthly PJ (±1%).
3. D6 shows every expectation with hits, the quarantine tables are populated, and freshness is under 24 hours.
4. Persona tests pass: finance-team RLS, PII masks and investigation hiding across SQL, dashboards, Genie and the app.
5. The dashboard replicas pass a visual check against `docs/*.png` and `/tmp/lochard-docx/*.png`.
6. Genie benchmarks reach ≥ 90% on all 5 agents, and Genie One shows the pinned assets for the board persona.
7. Gateway checks: the usage table has rows for every service, a routing decision is visible, the spend alert is tested, and the guardrail block is demonstrated.
8. App checks: a full scorecard cycle (Draft → Locked); the export to PPTX/PDF matches the slide layout; iframes load; Ask is streamed with OBO.
9. The cost experiment is shown in D5 with a quality-vs-cost frontier.

## DEMO. Run-sheet outline (about 60 min)

1. **Architecture and lineage** (5 min): UC lineage from AEMO nemweb to the Ops dashboard.
2. **Declarative pipelines and DQ** (7): the expectations dashboard and a quarantine example.
3. **Dashboards replicas** (10): PBI Finance drill-through, HSE, Maintenance, and the Tableau cumulative demand.
4. **Governance** (8): the same dashboard as Finance and as the Board persona (ABAC masks and RLS), and the policy definitions.
5. **Genie Agents and Genie One** (8): a business-user question with SQL transparency and feedback.
6. **Board portal** (10): the scorecard cycle, director scoring and comments, the AI-draft commentary with human approval, the embedded dashboards, and leadership trends with Ask.
7. **AI Gateway and agents** (8): the custom `lochard_assistant`, routing, the cost/quality frontier, budgets, a guardrail block, and the Supervisor Agent answering a cross-domain question using the forecaster.
8. **AI Functions** (4): an incident PDF becomes an extracted row, and a review queue item is created.

