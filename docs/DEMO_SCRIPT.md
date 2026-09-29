# Lochard Energy – Demo Run-sheet (about 60 minutes)

Present as `daniel.chegwidden@databricks.com`. The presenter's persona starts as **platform_admin**; switch it
live for the governance section.
App: <https://lochard-board-portal-7474659469579329.aws.databricksapps.com>

## Links

| Dashboard | |
|---|---|
| Lochard – Finance – Function Details | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/dashboardsv3/01f1b751698513628ca0177b181fe58c/published?o=7474659469579329) |
| Lochard – HSE Observations | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/dashboardsv3/01f1b7516979131f87d45c020c688981/published?o=7474659469579329) |
| Lochard – Maintenance Dashboard | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/dashboardsv3/01f1b75169c216a2836cb6772d3979ba/published?o=7474659469579329) |
| Lochard – Ops – Cumulative VIC Demand & EDD | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/dashboardsv3/01f1b751697b1c21bedc4b2eba8f9492/published?o=7474659469579329) |
| Lochard – Market Intelligence | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/dashboardsv3/01f1bbb0ee1f145383c30f395d7dcfc6/published?o=7474659469579329) |
| Lochard – Platform – AI Cost & Quality | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/dashboardsv3/01f1b75f46a01046a3b1270d8af1a029/published?o=7474659469579329) |
| Lochard – Platform – Data Quality & Pipelines | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/dashboardsv3/01f1b75f46c01f529bc609ea2d3d051f/published?o=7474659469579329) |
| Lochard – Platform – Governance & Audit | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/dashboardsv3/01f1b75f46b01a08b122a21085c96aa6/published?o=7474659469579329) |

| Genie Agent | |
|---|---|
| Lochard Executive & Board | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/genie/rooms/01f1b75d8a881ad4a93d042a6b2cb6ea?o=7474659469579329) |
| Lochard Finance | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/genie/rooms/01f1b7566e4b1c889809275efa7e108e?o=7474659469579329) |
| Lochard HSE | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/genie/rooms/01f1b7566e5c1fa8bb8606066a7613cb?o=7474659469579329) |
| Lochard Maintenance | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/genie/rooms/01f1b7566e451cb3a2631fac3756dae0?o=7474659469579329) |
| Lochard Gas Market & Iona Ops | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/genie/rooms/01f1b7566e551c779fe97ca7f903218c?o=7474659469579329) |

| Pipeline | |
|---|---|
| lochard-market-intel-medallion | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/pipelines/337a4aad-596a-4b45-8f25-6654668d22fd?o=7474659469579329) |
| lochard-documents-medallion | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/pipelines/c248c724-d38b-4d26-bfb7-7e6373eff005?o=7474659469579329) |
| lochard-finance-medallion | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/pipelines/d18bddff-61f0-43eb-9a0b-4960708dd1e5?o=7474659469579329) |
| lochard-hse-medallion | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/pipelines/f22fc3c9-5b18-453b-9827-d72d5a9c16ad?o=7474659469579329) |
| lochard-maintenance-medallion | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/pipelines/1c4a8c9a-f4a6-4966-bde6-15c655a5e2f1?o=7474659469579329) |
| lochard-market-ops-medallion | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/pipelines/6b66f034-3550-46b1-8095-ff8a1e4c5fac?o=7474659469579329) |
| lochard-shared-medallion | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/pipelines/aa7d5010-a273-4fca-8a14-e3f84d4ec008?o=7474659469579329) |

| Job | |
|---|---|
| lochard-aemo-nemweb-ingest | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/jobs/824822087003213?o=7474659469579329) |
| lochard-market-intel | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/jobs/1000969745344943?o=7474659469579329) |
| lochard-ai-cost-quality-experiment | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/jobs/889614366948114?o=7474659469579329) |
| lochard-daily-orchestrator | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/jobs/99176403819890?o=7474659469579329) |
| lochard-generate-source-data | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/jobs/191724118570760?o=7474659469579329) |
| lochard-scorecard-sync | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/jobs/623938414498666?o=7474659469579329) |
| lochard-semantic-and-governance | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/jobs/1001448006273872?o=7474659469579329) |
| lochard-train-vic-demand-forecaster | [open](https://fevm-dc-demo-workspace-02.cloud.databricks.com/jobs/1082764660712091?o=7474659469579329) |

Agent Bricks:
- Supervisor Agent **Lochard Leadership Analyst** (endpoint `mas-14e8875b-endpoint`).
- Knowledge Assistant **Iona Knowledge** (endpoint `ka-5d8cb9b9-endpoint`).
Both are under *Agents* in the workspace.

## 0. The leadership flow in the portal (10 min)
Use **Viewing as** (bottom of the navigation) to switch between Leader, Manager / Analyst and Board.

1. **Leadership Insights**, as Leader:
   - Start on FY27 YTD to Aug 2026. Step back a month with ‹, then switch to Quarter and Rolling 12 months to show the prior-year comparisons and the shaded chart periods.
   - Click **Open detailed dashboard →** on Maintenance to drill into the AI/BI dashboard.
2. Switch to **Manager / Analyst**:
   - Write the Maintenance commentary with **Draft with AI**, edit it and **Submit for review**.
   - Switch back to **Leader**: the "For your review" card shows it. **Return with note**, or **Approve**.
3. **Market Intelligence**:
   - As Leader, open the week of 21 Sep: the agent's brief, key developments with their sources, implications, actions and watchlist.
   - Step to other weeks, then widen the horizon to 13 weeks (a multi-week synthesis).
   - As Manager / Analyst, pin and dismiss items, add a note and submit the weekly commentary.
   - As Board, only the brief, approved commentary and pinned items remain.
   - **Open detailed dashboard →** for the Market Intelligence dashboard.
4. **Board Pack** (Aug 2026):
   - Walk the 12 tabs: the scorecard tab is the live scorecard, and slide 10 carries the market briefs.
   - As Leader, press **Finalise & generate PDF** and open the PDF.
   - As Board, only the finalised pack is available to download.
5. The **Ask Lochard** button (bottom right) suggests questions for the page you are on. Try "What were the most important market developments for Lochard last week?"
6. **Architecture** holds the process flows for this section: agents, market intelligence, commentary and board reporting, identity and roles.

## 1. Architecture and lineage (5 min)
- In the app, open **Architecture → Platform overview**. Walk the flow: sources → landing volumes → bronze / silver / gold → semantic → dashboards, Genie and the app, with Lakebase alongside and the AI Gateway on top.
- In Catalog Explorer, open `lochard_gold.fact_vic_gas_demand_daily` → **Lineage**. Follow it from the AEMO nemweb files through bronze and silver to gold, the semantic view, the Ops dashboard and Genie.
- Show `databricks.yml` and `resources/`: one bundle, serverless everywhere, dev and prod targets.

## 2. Declarative pipelines and data quality (7 min)
- Open the **lochard-finance-medallion** graph: Auto Loader bronze → validated silver with expectations → AUTO CDC SCD1 → gold star schema.
- Open **Platform – Data Quality & Pipelines** and show real expectation hits:
  - `complete_gas_day` dropped the partial current day in the live AEMO INT287 file;
  - `status_canonical` flagged legacy `CLOSED` versus `CLOSE`;
  - `gst_ratio_10pct` flagged GST anomalies.
- Show `lochard_silver.slv_gl_entries_quarantine` and the SCD2 cost-centre history (the FY26 re-org).

## 3. Replica dashboards (10 min)
- **Finance – Function Details**:
  - FY2027 filters; the pivot drills Team → CC Short Name → Project → Account;
  - Major Projects → HUGS −$197K → right-click **Drill to** *Actuals – Transaction Details*.
- **HSE Observations**:
  - counters 7 / 133 / 140 / 321 / 4,811 / 5,132;
  - the cumulative trend by type, the risk × status matrix, and open by risk rank.
- **Maintenance Dashboard** (on Lakehouse//RT): 84% / 25 / 4 / 635 / 5,328, the 13-week compliance combo chart (dual axis), and hours by craft.
- **Ops – Cumulative VIC Demand & EDD**:
  - the Tableau cumulative lines for 2021–2024 and the monthly PJ table;
  - EDD vs demand scatter with R²;
  - the *Data source* filter separates AEMO (real) from SYNTHETIC.

## 4. Governance: RBAC, row, column, ABAC (8 min)
1. Show the ABAC policies on `lochard_gold` (Catalog Explorer → schema → Policies; source `src/governance/04_policies.sql`) and the governed tags on `fact_gl_transaction` and `fact_observation`.
2. In the app, go to **AI & Governance → switch persona to Board**. Reload the HSE dashboard: actionee becomes `PERSON-xxxx`. In Finance, Legal and Employee Costs descriptions show `[restricted – …]`.
3. Switch to **budget_holder (Maintenance)**: the Finance dashboard shows only the Maintenance team. Then switch back to **platform_admin**.
4. **Platform – Governance & Audit**: tagged columns and the audit trail.

## 5. Genie Agents and Genie One (8 min)
- **Lochard HSE**: "How many observations are open by actual risk rank?" gives 245 / 35 / 34 / 7 with the SQL shown.
- **Lochard Executive & Board**: "Which FY27 scorecard KPIs are at risk and why?" uses the `mv_board` metric view.
- Show the **Benchmarks** tab: ground-truth questions and eval runs. This is the responsible AI release gate.
- **Genie One**:
  - The workspace admin gives the board / LLT users **Consumer access**.
  - Customise the homepage: welcome text; pin the 4 replica dashboards, the Executive Genie Agent and the board portal.
  - As a business user, ask across domains and show the citations and thumbs feedback.

## 6. Board portal (10 min)
- **Scorecard**: the FY27 Board Scorecard (the slide layout, rebuilt as a live grid).
  - FY27 Aug-26 (BOARD_ENDORSED); status index 87.5%, board score 78%.
- **KPI drawer**, for 2.1 HUGS Delivery:
  - evidence (HUGS YEO vs P50 $112.4M);
  - **Generate AI draft**: labelled, and needs accept or edit;
  - director score and board-only comment;
  - history and audit.
- **Workflow**: advance a period; an illegal transition returns 409. Export the board-pack PPTX.
- **Leadership Insights**:
  - Live governed tiles (OBO).
  - Charts: FY27 cumulative budget vs YEO vs actuals; monthly observations; weekly schedule compliance; cumulative VIC demand by year, which toggles to Iona inventory. Hover a chart for exact values.
  - **Ask about this** on each card opens the **Ask Lochard** chat pre-filled for that domain's Genie Agent.
  - **Ask a question** (or the floating **Ask Lochard** button on any page) opens the Leadership Analyst with its live trace.
- **Dashboards** tab: embedded AI/BI iframes. This needs third-party cookies; the app domain is already allow-listed.
- **Agents** (the "how do the agents work" moment):
  - The flow strip shows You (OBO token) → Leadership Analyst → Genie Agents / Iona Knowledge → Unity AI Gateway. Nodes light up while the agent calls them.
  - **Leadership Analyst**: "Why is HSE Performance At Risk and what do our procedures say about isolation before compressor work?"
    - The trace streams live: the plan, a call to the Executive & Board Genie (with the exact sub-question), its result table, a call to Iona Knowledge, and the cited answer (about 45 s).
    - Sources link to the procedure PDFs in the documents volume.
  - **Genie Agent** (e.g. Maintenance): the trace shows Genie's stages (selecting tables, writing SQL, running as you) and the generated SQL and result. Follow-up chips continue the same Genie conversation.
  - **Iona Knowledge**: every sentence carries a numbered citation.
  - **Model routing lab**:
    - "Which scorecard KPIs are At Risk?" is classified LOOKUP and routed to economy, about 96% cheaper than premium with the same facts.
    - "Draft a three-sentence board summary…" is classified STRATEGIC and routed to premium.
    - All three tiers are shown side by side with latency, tokens and cost. The calls are tagged `feature=routing_lab` in `system.ai_gateway.usage`.
  - Every run is logged to Lakebase (`scorecard.agent_run`) with 👍/👎. The cards show runs, average latency and ratings.

## 7. Unity AI Gateway, cost and routing, agents (8 min)
- Catalog Explorer → `lochard_ai` → model services:
  - tiers with fallbacks, rate limits, inference tables and grants;
  - `lochard_assistant` = weighted routing 70/20/10 plus fallback.
- **Platform – AI Cost & Quality**:
  - usage, tokens, cost, latency and fallback rate;
  - experiment quality vs cost per arm (premium / standard / economy / open / assistant / router).
- Routing: the economy model classifies each question (lookup / analytical / strategic) and dispatches to the cheapest adequate tier.
- **Supervisor Agent** (Agents UI): its tools, plus traces in MLflow.
- **Forecaster**: the MLflow experiment `/Shared/lochard/vic_gas_demand_forecaster` (baseline vs GBT), with scores in `lochard_ai.vic_demand_forecast`.

## 8. AI Functions and responsible AI (4 min)
- `lochard_gold.hse_incident_report_review`:
  - `ai_parse_document` + `ai_extract` + `ai_classify` over incident PDFs;
  - reports flagged for human review where the AI category disagrees with the logged category.
- `lochard_gold.invoice_three_way_match`: invoices vs GL; amount mismatches surfaced.
- Responsible AI controls:
  - OBO means answers respect ABAC;
  - SQL and sources are always shown;
  - humans own every score and status;
  - benchmarks gate Genie;
  - inference and usage tables for audit;
  - rate limits and tiering for cost.
