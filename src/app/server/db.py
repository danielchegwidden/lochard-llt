"""Lakebase (Postgres) connection pool – fresh OAuth token per physical connection, recycled before expiry."""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config


class OAuthConnection(psycopg.Connection):
    @classmethod
    def connect(cls, conninfo="", **kwargs):
        cred = config.app_client().postgres.generate_database_credential(endpoint=config.LAKEBASE_ENDPOINT)
        kwargs["password"] = cred.token
        return super().connect(conninfo, **kwargs)


def _pg_user() -> str:
    # Apps inject PGUSER (the app service principal's client id) when a Lakebase resource is attached
    if os.environ.get("PGUSER"):
        return os.environ["PGUSER"]
    if config.IS_APP:
        return os.environ.get("DATABRICKS_CLIENT_ID", "")
    return config.app_client().current_user.me().user_name


pool = ConnectionPool(
    conninfo=f"dbname={config.PGDATABASE} user={_pg_user()} host={config.PGHOST} port={config.PGPORT} sslmode={config.PGSSLMODE}",
    connection_class=OAuthConnection,
    kwargs={"row_factory": dict_row},
    min_size=1, max_size=10,
    max_lifetime=2700,        # 45 min – recycle before the 1 h token expires
    max_idle=240,             # drop idle connections before Lakebase scale-to-zero / restarts terminate them
    check=ConnectionPool.check_connection,  # validate on checkout; a server-terminated connection is replaced, not returned
    open=False,
)


@contextmanager
def tx(user_email: str | None = None, user_role: str | None = None):
    """Transaction with the end user's identity set for audit triggers and row-level security."""
    with pool.connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.user_email', %s, true), set_config('app.user_role', %s, true)",
                            (user_email or "", user_role or ""))
                yield cur
