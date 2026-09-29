# Market Intelligence Hub – data contract

The Market Intelligence Hub (board portal) reads **only** the four semantic views below, on behalf of the viewer.
Everything upstream (collectors, pipeline, analyst agent) may change as long as these views keep their shape.

Names are shown for the `prod` target (`lochard_` prefix). Every name is built from the bundle variables
`catalog` and `prefix`, so nothing below is hard-coded in code (see `docs/PROD_MIGRATION.md`).

## `{catalog}.lochard_semantic.v_market_intel_items` – one row per relevant item

| column | type | notes |
|---|---|---|
| item_id | STRING | stable id: sha1 of the canonical URL (or of title + source + date when there is no URL) |
| published_at | TIMESTAMP | UTC |
| published_date | DATE | Australia/Melbourne local date |
| week_start | DATE | Monday of `published_date`'s week (weeks run Mon–Sun) |
| title | STRING | |
| source_name | STRING | publisher, e.g. `AFR`, `ASX: AGL`, `AEMO`, `Lochard Energy` |
| source_type | STRING | `news` · `web_research` · `asx_announcement` · `company_release` · `regulator_release` |
| url | STRING | link to the original |
| content_depth | STRING | `full_text` · `summary` · `headline` (how much source text the AI saw) |
| summary | STRING | AI, 1–2 sentences |
| why_it_matters | STRING | AI, one sentence on the implication for Lochard |
| primary_entity | STRING | canonical watchlist entity, or `Market` |
| entities | ARRAY<STRING> | canonical watchlist entities mentioned |
| entity_group | STRING | `Lochard` · `Customer` · `Competitor` · `Upstream supplier` · `Regulator & market body` · `Government & policy` · `Industry & market` |
| topic | STRING | `Gas storage` · `Supply & demand` · `Prices & contracts` · `Policy & regulation` · `Projects & investment` · `Corporate & M&A` · `Operations & safety` · `Energy transition` |
| signal | STRING | `Opportunity` · `Threat` · `Watch` · `Neutral` (from Lochard's perspective) |
| sentiment | DOUBLE | −1 … 1 from Lochard's perspective |
| importance | INT | 1 … 5 |
| relevance | INT | 1 … 3 (irrelevant items, relevance 0, are excluded from the view) |
| excerpt | STRING | up to ~1,500 characters of source text (or the feed snippet) |
| doc_path | STRING | UC Volume path of the landed source (PDF / JSON), when available |
| ingested_at | TIMESTAMP | |

## `{catalog}.lochard_semantic.v_market_intel_briefs` – one row per week, written by the analyst agent

| column | type | notes |
|---|---|---|
| week_start | DATE | Monday |
| week_end | DATE | Sunday |
| headline | STRING | one line |
| summary_md | STRING | 3–6 sentence executive summary (markdown) |
| developments_json | STRING | JSON array of `{title, detail, signal, entity_group, importance, item_ids: [item_id…]}` |
| implications_json | STRING | JSON array of strings: what it means for Lochard |
| watchlist_json | STRING | JSON array of `{entity, note, direction: "up" \| "down" \| "flat"}` |
| actions_json | STRING | JSON array of `{action, owner_role}` |
| sentiment_json | STRING | JSON object `{entity_group: average sentiment}` |
| n_items | INT | relevant items in the week |
| n_sources | INT | distinct publishers |
| model | STRING | model / service used |
| tools_used | ARRAY<STRING> | agent tools called while writing the brief |
| trace_id | STRING | MLflow trace id of the agent run |
| generated_at | TIMESTAMP | |

## `{catalog}.lochard_semantic.v_market_intel_weekly` – weekly aggregates

`week_start DATE, entity_group STRING, topic STRING, n_items BIGINT, n_threats BIGINT, n_opportunities BIGINT,
avg_sentiment DOUBLE, max_importance INT`

## `{catalog}.lochard_semantic.v_market_intel_entities` – the watchlist

`entity STRING, entity_group STRING, relationship STRING, description STRING, asx_code STRING, website STRING`

## Portal-side state (Lakebase, not Unity Catalog)

Analyst curation lives in the board portal's Lakebase database:
- item annotations: pin, dismiss, analyst note, importance override;
- the analyst's weekly commentary, submitted and approved through the shared commentary workflow;
- cached multi-week syntheses.

None of it is written back to the views above.

---

## How it works

Job **`lochard-market-intel`** runs daily at 07:00 Australia/Melbourne as the ETL service principal:

```
collect (serverless Python) → parse_and_enrich (pipeline lochard-market-intel-medallion) → weekly_brief (analyst agent)
```

### 1. Collect – `src/market_intel/collect.py`
The watchlist is `src/market_intel/watchlist.yml`: 23 entities in six groups, 10 topic searches and 6 research themes.
Relationships are stated only where they are public (e.g. AGL's 2015 storage agreement, Snowy Hydro's 2024 agreement).

| Source | What is landed | `source_type` / depth |
|---|---|---|
| Google News RSS, one search per entity/topic query and week (`after:`/`before:`) | headline, publisher, date (keyword pre-filter) | `news` / `headline` |
| Web research agent: `databricks-gpt-5-5` via the Responses API with the hosted `web_search` tool, one call per theme and week | dated publisher articles; each URL is fetched and its readable text extracted, 404s dropped | `web_research` / `full_text` or `summary` |
| ASX announcements (AGL, ORG, APA, BPT, AEL, STO, WDS, VEA), routine filings filtered out | the announcement PDF | `asx_announcement` / `full_text` after parsing |
| Lochard newsroom | dated releases | `company_release` |

Output goes to the `market_intel` volume in the landing schema:
- `items/source=<type>/week=<monday>/<run>.jsonl`
- `documents/asx/<code>/<key>.pdf`
- `reference/watchlist.json`

A `_state/seen.json` file of item ids keeps re-runs idempotent. `mode=daily` searches this week and last week;
`mode=backfill weeks=N` rebuilds history.

### 2. Parse and enrich – `src/pipelines/market_intel/transformations/`
| Layer | Table | Notes |
|---|---|---|
| bronze | `brz_mi_items`, `brz_mi_documents` | Auto Loader (JSON, binaryFile) |
| silver | `slv_mi_documents_parsed` | `ai_parse_document` on each PDF |
| silver | `slv_mi_items_enriched` | item + parsed document text → `ai_query('${economy_model}', …, responseFormat => JSON schema, failOnError => false)` returning relevance 0–3, entities, primary entity, entity group, topic, signal, sentiment, importance, summary and why it matters. Streaming table, so each item is enriched (and billed) once. |
| gold | `fact_market_intel_item` | one row per story: same headline in the same week merged, preferring the copy with most text |
| gold | `agg_market_intel_weekly`, `dim_market_entity` | weekly aggregates; the watchlist |
| ai | `market_intel_brief` | written by the agent (MERGE on `week_start`) |

The semantic views in `src/semantic/04_market_intel.sql` expose relevance ≥ 1 only. The Executive & Board Genie
agent can also answer market questions from these views.

### 3. Weekly brief – `src/market_intel/analyst_agent.py`
The Market Intelligence Analyst is a tool-calling agent on `databricks-claude-sonnet-5`:

| Tool | Purpose |
|---|---|
| `list_items` | the week's items, most important first, filterable by group and topic |
| `read_item` | full text of one item |
| `search_items` | keyword search over the week and the three weeks before |
| `entity_trend` | mentions and sentiment for one entity over 8 weeks |
| `prior_brief` | last week's brief, for continuity |
| `internal_context` | Iona inventory and flows, VIC demand vs last year, HUGS cost vs the revised P50 (AUD) |
| `submit_brief` | submit the structured brief |

Guards:
- the brief is rejected back to the model if it is incomplete;
- cited `item_ids` are checked against real items, and unknown ones are removed;
- counts, publishers and sentiment by group are computed from the data, not by the model.

Each brief is one MLflow trace in `/Shared/lochard/lochard-market-intel-agent`, and its id is stored with the brief.
The current and previous week are rewritten daily; missing weeks are filled. `--parallel N` writes weeks
concurrently, newest first.

### Observed volumes (26-week backfill, 29 Sep 2026)

**Collection** (about 25 minutes on serverless):
- 2,279 items: 2,055 news headlines, 220 web-research articles (127 with full text), ASX PDFs;
- 2,496 news searches and 156 web-research calls.

**Enrichment** (about 27 minutes):
- 0 errors;
- 686 items classified irrelevant; 1,550 relevant stories remain, 39–95 per week.

**Briefs**: about 2–3 minutes each, 5–10 tool steps. All 26 weeks were written.

Approximate model volume for the backfill (estimated from per-call sizes, not metered):
- web research: ~5M tokens (GPT-5.5);
- enrichment: ~6M tokens (Haiku);
- briefs: ~2M tokens (Sonnet).

A daily run is roughly 1/13 of that.

### Responsible use of public sources
- The portal and dashboard show AI summaries, short excerpts (≤ 1,500 characters) and links to the original. Full article text is used only for classification and analysis.
- News links are Google News redirect links. ASX links point to the announcement PDF.
- Relevance and signals are AI judgements. Analysts can pin, dismiss, re-rate and annotate items in the portal, and leaders see the curated view.

### Operate
```bash
databricks bundle deploy -t prod --select volumes.market_intel,pipelines.lochard_market_intel_medallion,jobs.lochard_market_intel,dashboards.market_intelligence
databricks jobs run-now --json '{"job_id": <lochard-market-intel id>, "job_parameters": {"mode": "backfill", "weeks": "26"}}'
scripts/apply_sql_dir.py src/semantic --only 04          # the semantic job also applies it
# regenerate one brief (locally, with a CLI profile)
DATABRICKS_CONFIG_PROFILE=fevm-dc-demo-workspace-02 src/app/.venv/bin/python src/market_intel/analyst_agent.py \
  --catalog dc_demo_workspace_02_catalog --prefix lochard_ --week 2026-09-21 --experiment /Shared/lochard/lochard-market-intel-agent
```

## When this moves to Lochard's production workspace
- Catalog and schema names come from the bundle variables `catalog` and `prefix`; nothing in the collector, pipeline, agent or views hard-codes them.
- Models are variables: `economy_model` (enrichment), `standard_model` (brief), `research_model` (web research). Check their availability in the target region.
- The ETL service principal needs:
  - write access to the landing volume;
  - query access to the three model endpoints;
  - CAN_MANAGE on `/Shared/lochard` for the MLflow experiment.
- Serverless egress must reach news.google.com, the ASX endpoints, lochardenergy.com.au and publisher sites.

See [`PROD_MIGRATION.md`](PROD_MIGRATION.md).
