"""Databricks SQL on behalf of the signed-in user (UC governance applies to every row the app shows)."""
from __future__ import annotations

import logging
import time

from databricks.sdk.service.sql import Disposition, Format, StatementParameterListItem, StatementState

from . import config

log = logging.getLogger("lochard.sql")


class SqlError(RuntimeError):
    pass


def query(user_token: str | None, statement: str, params: dict | None = None, timeout_s: int = 60) -> list[dict]:
    w = config.user_client(user_token)
    p = [StatementParameterListItem(name=k, value=None if v is None else str(v)) for k, v in (params or {}).items()]
    r = w.statement_execution.execute_statement(
        statement=statement, warehouse_id=config.WAREHOUSE_ID, catalog=config.CATALOG, schema=config.SEMANTIC,
        parameters=p or None, wait_timeout="30s", disposition=Disposition.INLINE, format=Format.JSON_ARRAY,
        row_limit=5000)
    deadline = time.time() + timeout_s
    while r.status and r.status.state in (StatementState.PENDING, StatementState.RUNNING):
        if time.time() > deadline:
            raise SqlError("query timed out")
        time.sleep(1)
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.state != StatementState.SUCCEEDED:
        msg = r.status.error.message if r.status and r.status.error else str(r.status)
        raise SqlError(msg)
    cols = [c.name for c in (r.manifest.schema.columns or [])] if r.manifest and r.manifest.schema else []
    types = [c.type_name.value if c.type_name else "STRING" for c in (r.manifest.schema.columns or [])] if cols else []
    rows = (r.result.data_array if r.result and r.result.data_array else []) or []
    return [{c: _cast(v, t) for c, v, t in zip(cols, row, types)} for row in rows]


def _cast(v, t):
    if v is None:
        return None
    if t in ("INT", "LONG", "SHORT", "BYTE"):
        return int(v)
    if t in ("DOUBLE", "FLOAT", "DECIMAL"):
        return float(v)
    if t == "BOOLEAN":
        return v in ("true", True)
    return v


def safe(user_token, statement, params=None) -> dict:
    """Return {'rows': [...]} or {'rows': [], 'error': ...} – the semantic layer may be refreshing."""
    try:
        return {"rows": query(user_token, statement, params)}
    except Exception as e:  # noqa: BLE001
        log.warning("sql failed: %s", e)
        return {"rows": [], "error": str(e)[:300]}


def fq(view: str) -> str:
    return f"{config.CATALOG}.{config.SEMANTIC}.{view}"
