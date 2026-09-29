#!/usr/bin/env python3
"""Postgres grants on the board portal DB (run as the DB owner / admin after migrations):
   app SP -> read/write scorecard; ETL SP -> read-only for the Lakebase -> Delta sync."""
import json, os, subprocess, psycopg
P = "fevm-dc-demo-workspace-02"; EP = "projects/lochard-board-portal/branches/production/endpoints/primary"
APP_SP, ETL_SP = "9ddae195-908a-4746-9e2b-e73405898a9f", "96d74e8e-856f-400f-9f26-c6a49cbd9131"
tok = json.loads(subprocess.run(["databricks", "-p", P, "postgres", "generate-database-credential", EP, "-o", "json"],
                                capture_output=True, text=True).stdout)["token"]
host = json.loads(subprocess.run(["databricks", "-p", P, "postgres", "get-endpoint", EP, "-o", "json"],
                                 capture_output=True, text=True).stdout)["status"]["hosts"]["host"]
me = json.loads(subprocess.run(["databricks", "-p", P, "current-user", "me", "-o", "json"], capture_output=True, text=True).stdout)["userName"]
with psycopg.connect(host=host, dbname="board_portal", user=me, password=tok, sslmode="require", autocommit=True) as c:
    for s in [f'GRANT USAGE, CREATE ON SCHEMA scorecard TO "{APP_SP}"',
              f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA scorecard TO "{APP_SP}"',
              f'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA scorecard TO "{APP_SP}"',
              # later migrations run as the app SP and add foreign keys to these tables (e.g. board_pack -> reporting_period)
              f'GRANT REFERENCES ON ALL TABLES IN SCHEMA scorecard TO "{APP_SP}"',
              f'ALTER DEFAULT PRIVILEGES IN SCHEMA scorecard GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{APP_SP}"',
              f'GRANT USAGE ON SCHEMA scorecard TO "{ETL_SP}"',
              f'GRANT SELECT ON ALL TABLES IN SCHEMA scorecard TO "{ETL_SP}"',
              f'ALTER DEFAULT PRIVILEGES IN SCHEMA scorecard GRANT SELECT ON TABLES TO "{ETL_SP}"']:
        c.execute(s); print("ok:", s[:80])
