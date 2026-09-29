# Moving to Lochard's production workspace

This demo runs in `fevm-dc-demo-workspace-02` with catalog `dc_demo_workspace_02_catalog` and schemas `lochard_*`.
**When it moves to Lochard's production workspace, the catalog and schema names are likely to change.** Nothing
in the deployed code depends on today's names: every name is derived from bundle variables and passed to the
pipelines, jobs, SQL and app at deploy time. This page lists what to set, and what is workspace-specific.

## 1. Add a production target

Add a target to `databricks.yml` (or override on the command line with `--var`):

```yaml
targets:
  lochard_prod:
    mode: production
    workspace:
      host: https://<lochard-workspace>.cloud.databricks.com
    variables:
      catalog: <lochard_catalog>            # e.g. lochard_prod
      prefix: lochard_                      # schema prefix; schemas become <prefix>landing, <prefix>gold, ...
      workspace_id: "<numeric workspace id>"
      etl_sp: <application id of the ETL service principal>
      platform_admin: <admin user or group>
      notification_email: <ops mailbox>
      supervisor_endpoint: <Agent Bricks supervisor endpoint>   # after step 4
      knowledge_endpoint: <Agent Bricks knowledge endpoint>     # after step 4
```

## 2. Where the names flow

| Name | Bundle variable | Consumed by |
|---|---|---|
| Catalog | `catalog` | schemas, volumes, pipelines (`lochard.*` configuration), jobs (`--catalog`), dashboards (`dataset_catalog`), Genie, app (`LOCHARD_CATALOG`) |
| Schemas | `prefix` → `${resources.schemas.<x>.name}` | pipelines, jobs (`--prefix`), SQL layers (`{gold}`, `{semantic}`, `{ai}` … placeholders in `src/common/run_sql_dir.py`), app (`LOCHARD_SEMANTIC_SCHEMA`, `LOCHARD_GOVERNANCE_SCHEMA`) |
| UC model services | `${resources.model_services.*.id}` | app (`LLM_ECONOMY_MODEL`, `LLM_STANDARD_MODEL`) |
| Workspace id | `workspace_id` | AI Gateway URL, dashboard embed URLs, platform views filtering system tables, cost experiment |
| Agent Bricks endpoints | `supervisor_endpoint`, `knowledge_endpoint` | app (`SUPERVISOR_ENDPOINT`, `KNOWLEDGE_ENDPOINT`) |
| Foundation models | `economy_model`, `standard_model`, `premium_model`, `research_model`, … | AI Gateway model services, market-intel enrichment (`ai_query`), analyst agent, web research |
| SQL warehouse | `warehouse_id` (bundle resource) / `rt_warehouse_id` (lookup by name) | dashboards, Genie, app |
| Lakebase | `resources.postgres_projects.board_portal` | app (`ENDPOINT_NAME`, `LAKEBASE_DATABASE`; `PGHOST`/`PGUSER` are injected by Apps) |

Local-only defaults in `src/app/server/config.py`, `scripts/*.py` and the `--profile` flags exist for the developer
loop and are overridden in every deployed resource.

## 3. Things that are workspace-specific and must be recreated, not copied

- **Service principals and personas.** `etl_sp`, the persona test principals in `src/governance/05_grants.sql` and
  the rows in `lochard_governance.principal_persona` are demo identities. In production use account groups
  `lochard_<persona>` (the UDFs already honour them) and replace the principal ids in `05_grants.sql`.
- **Governed tag policies**: `src/governance/bootstrap_tag_policies.sh` (account-level; run once per account).
- **Agent Bricks** (Supervisor Agent and Knowledge Assistant) are not bundle resources yet: run
  `src/ai/agent_bricks/apply.sh` (edit its catalog/profile at the top), then set the two endpoint variables.
  Grant `CAN_QUERY` on both endpoints to the portal's user groups.
- **Lakehouse//RT warehouse**: `scripts/create_rt_warehouse.sh`, then the bundle looks it up by name.
- **Lakebase grants**: `scripts/lakebase_grants.py` after the first app start (app and ETL service principals).
- **Dashboard embedding**: allow-list the app domain under Settings → Security → Embed dashboards.
- **MLflow experiment for the market-intel agent**: `/Shared/lochard/lochard-market-intel-agent`; the ETL service
  principal needs CAN_MANAGE on `/Shared/lochard`.
- **Egress**: the AEMO and market-intelligence collectors need outbound HTTPS from serverless (nemweb.com.au,
  news.google.com, asx.api.markitdigital.com, cdn-api.markitdigital.com, lochardenergy.com.au and publisher sites
  found by web research). If serverless network policies restrict egress, allow-list these domains.
- **Data residency**: the demo workspace is `us-east-1`; Lochard production would run in `ap-southeast-2`.
  Check that the foundation models used (Claude, GPT with web search) are available there, or pick equivalents via
  the model variables.

## 4. Order of operations

1. `databricks bundle deploy -t lochard_prod` (schemas, volumes, pipelines, jobs, dashboards, Genie, AI Gateway,
   Lakebase, app).
2. `src/governance/bootstrap_tag_policies.sh`, then run `lochard-semantic-and-governance`.
3. Load real sources (replace the simulator job `lochard-generate-source-data` with Lakeflow Connect or file drops),
   then `lochard-daily-orchestrator`.
4. `src/ai/agent_bricks/apply.sh`; set `supervisor_endpoint` / `knowledge_endpoint`; redeploy the app.
5. `lochard-market-intel` with `mode=backfill` for history; it then runs daily at 07:00 AEST.
6. `scripts/lakebase_grants.py`; start the app (`databricks bundle run -t lochard_prod board_portal_app`).

## 5. Checks after the move

```sql
SHOW SCHEMAS IN <catalog> LIKE 'lochard_*';
SELECT count(*) FROM <catalog>.lochard_semantic.v_market_intel_items;
SELECT * FROM <catalog>.lochard_semantic.v_market_intel_briefs ORDER BY week_start DESC LIMIT 1;
```
In the portal, switch "Viewing as" between Leader, Manager / Analyst and Board and check that each page loads.
