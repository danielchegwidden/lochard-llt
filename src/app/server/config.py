"""Runtime configuration and dual-mode auth (Databricks App vs local CLI profile)."""
from __future__ import annotations

import os
from functools import lru_cache

from databricks.sdk import WorkspaceClient

IS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))
PROFILE = os.environ.get("DATABRICKS_PROFILE", "fevm-dc-demo-workspace-02")

CATALOG = os.environ.get("LOCHARD_CATALOG", "dc_demo_workspace_02_catalog")
SEMANTIC = os.environ.get("LOCHARD_SEMANTIC_SCHEMA", "lochard_semantic")
GOVERNANCE = os.environ.get("LOCHARD_GOVERNANCE_SCHEMA", "lochard_governance")
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "a795ab84a55b5468")
WORKSPACE_ID = os.environ.get("DATABRICKS_WORKSPACE_ID", "7474659469579329")

LAKEBASE_ENDPOINT = os.environ.get("ENDPOINT_NAME",
                                   "projects/lochard-board-portal/branches/production/endpoints/primary")
PGHOST = os.environ.get("PGHOST", "ep-morning-tree-d2buts5k.database.us-east-1.cloud.databricks.com")
PGDATABASE = os.environ.get("LAKEBASE_DATABASE") or os.environ.get("PGDATABASE") or "board_portal"
PGPORT = os.environ.get("PGPORT", "5432")
PGSSLMODE = os.environ.get("PGSSLMODE", "require")

AI_GATEWAY_URL = os.environ.get("AI_GATEWAY_URL", f"https://{WORKSPACE_ID}.ai-gateway.cloud.databricks.com/mlflow/v1")
# Unity AI Gateway only serves Unity Catalog model services (raw FM endpoint names are rejected on the Gateway URL)
LLM_ECONOMY_MODEL = os.environ.get("LLM_ECONOMY_MODEL", f"{CATALOG}.lochard_ai.lochard_llm_economy")
LLM_STANDARD_MODEL = os.environ.get("LLM_STANDARD_MODEL", f"{CATALOG}.lochard_ai.lochard_assistant")
LLM_FALLBACK_ENDPOINT = os.environ.get("LLM_FALLBACK_ENDPOINT", "databricks-claude-haiku-4-5")  # legacy /serving-endpoints

DASHBOARDS = {  # key -> (env var, display name used for discovery fallback, tab title)
    "finance": ("DASHBOARD_FINANCE_ID", "Lochard | Finance – Function Details", "Finance – Function Details"),
    "hse": ("DASHBOARD_HSE_ID", "Lochard | HSE Observations", "HSE Observations"),
    "maintenance": ("DASHBOARD_MAINTENANCE_ID", "Lochard | Maintenance Dashboard", "Maintenance"),
    "ops": ("DASHBOARD_OPS_ID", "Lochard | Ops – Cumulative VIC Demand & EDD", "Ops – VIC Demand & EDD"),
    "market": ("DASHBOARD_MARKET_ID", "Lochard | Market Intelligence", "Market Intelligence"),
}
GENIE_SPACES = {  # key -> (env var, title used for discovery fallback)
    "executive": ("GENIE_EXEC_SPACE_ID", "Lochard Executive & Board"),
    "finance": ("GENIE_FINANCE_SPACE_ID", "Lochard Finance"),
    "hse": ("GENIE_HSE_SPACE_ID", "Lochard HSE"),
    "maintenance": ("GENIE_MAINTENANCE_SPACE_ID", "Lochard Maintenance"),
    "market": ("GENIE_MARKET_SPACE_ID", "Lochard Gas Market & Iona Ops"),
}


def host() -> str:
    h = os.environ.get("DATABRICKS_HOST", "")
    if h:
        return h if h.startswith("http") else f"https://{h}"
    return app_client().config.host.rstrip("/")


@lru_cache(maxsize=1)
def app_client() -> WorkspaceClient:
    """Identity of the app itself (service principal in Apps, CLI profile locally)."""
    return WorkspaceClient() if IS_APP else WorkspaceClient(profile=PROFILE)


def user_client(user_token: str | None) -> WorkspaceClient:
    """On-behalf-of-user client. In Apps the forwarded user token carries the viewer's identity, so Unity Catalog
    ABAC policies, row filters and masks apply to everything this client reads."""
    if user_token:
        return WorkspaceClient(host=host(), token=user_token, auth_type="pat")
    return app_client()        # local development: the developer's CLI identity
