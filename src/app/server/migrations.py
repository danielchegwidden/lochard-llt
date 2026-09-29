"""Schema migrations (server/migrations/V*.sql) + idempotent seed of the FY26/FY27 scorecard.

Runs at app start-up under a Postgres advisory lock so multiple app instances never race."""
from __future__ import annotations

import glob
import json
import logging
import os

from . import db

log = logging.getLogger("lochard.migrations")
HERE = os.path.dirname(os.path.abspath(__file__))
LOCK_ID = 7_474_659_469  # arbitrary, stable


def migrate() -> list[str]:
    applied = []
    with db.pool.connection() as conn:
        conn.autocommit = True
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            conn.execute("CREATE SCHEMA IF NOT EXISTS scorecard")
            conn.execute("CREATE TABLE IF NOT EXISTS scorecard.schema_migrations (version text PRIMARY KEY, "
                         "applied_at timestamptz NOT NULL DEFAULT now())")
            done = {r["version"] for r in conn.execute("SELECT version FROM scorecard.schema_migrations").fetchall()}
            for path in sorted(glob.glob(os.path.join(HERE, "migrations", "V*.sql"))):
                version = os.path.basename(path).split("__")[0]
                if version in done:
                    continue
                with conn.transaction():
                    conn.execute(open(path).read())
                    conn.execute("INSERT INTO scorecard.schema_migrations (version) VALUES (%s)", (version,))
                applied.append(version)
                log.info("applied migration %s", version)
            try:  # only the owner (admin who ran the first migration) can grant; the app SP just needs to read/insert
                conn.execute("GRANT SELECT, INSERT ON scorecard.schema_migrations TO PUBLIC")
            except Exception as e:  # noqa: BLE001
                log.info("grant on schema_migrations skipped: %s", str(e).splitlines()[0])
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
    return applied


def seed() -> bool:
    """Load scorecard_seed.json once (fiscal years, KPIs, deliverables, periods, statuses, scores, comments)."""
    s = json.load(open(os.path.join(HERE, "seed", "scorecard_seed.json")))
    with db.pool.connection() as conn:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID + 1,))
            if conn.execute("SELECT count(*) AS n FROM scorecard.fiscal_year").fetchone()["n"]:
                return False
            conn.execute("SELECT set_config('app.seeding', 'on', true)")
            cur = conn.cursor()
            for fy in s["fiscal_years"]:
                cur.execute("INSERT INTO scorecard.fiscal_year VALUES (%s, %s, %s, %s)",
                            (fy["fy_code"], fy["start_date"], fy["end_date"], fy["status"]))
            pillar_ids = {}
            for p in s["pillars"]:
                cur.execute("INSERT INTO scorecard.pillar (fy_code, pillar_no, name) VALUES (%s, %s, %s) RETURNING pillar_id",
                            (p["fy_code"], p["pillar_no"], p["name"]))
                pillar_ids[(p["fy_code"], p["name"])] = cur.fetchone()["pillar_id"]
            for i, k in enumerate(s["kpis"]):
                cur.execute("""INSERT INTO scorecard.kpi (kpi_id, fy_code, pillar_id, code, name, owner_initials, owner_role,
                               weight_pct, preamble, metric_binding, sort_order) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (k["kpi_id"], k["fy_code"], pillar_ids[(k["fy_code"], k["pillar"])], k["code"], k["name"],
                             k["owner_initials"], k["owner_role"], k["weight_pct"], k.get("preamble"),
                             json.dumps({"evidence": k["code"]}), i))
            for d in s["deliverables"]:
                cur.execute("INSERT INTO scorecard.deliverable (kpi_id, seq, text) VALUES (%s, %s, %s)",
                            (d["kpi_id"], d["seq"], d["text"]))
            for p in s["periods"]:
                cur.execute("""INSERT INTO scorecard.reporting_period (period_code, fy_code, month_start, period_end,
                               board_meeting, label, state) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                            (p["period_code"], p["fy_code"], p["month_start"], p["period_end"], p["board_meeting"],
                             p["label"], p["state"]))
            for u in s["status_updates"]:
                cur.execute("""INSERT INTO scorecard.kpi_status_update (kpi_id, period_code, status, owner_score, commentary,
                               submitted_by) VALUES (%s,%s,%s,%s,%s,%s)""",
                            (u["kpi_id"], u["period_code"], u["status"], u["owner_score"], u["commentary"], u["submitted_by"]))
            directors = {d["name"]: d for d in s["directors"]}
            for b in s["board_scores"]:
                d = directors[b["director"]]
                cur.execute("""INSERT INTO scorecard.board_score (kpi_id, period_code, director_email, director_name, score,
                               rationale) VALUES (%s,%s,%s,%s,%s,%s)""",
                            (b["kpi_id"], b["period_code"], d["email"], d["name"], b["score"], b["rationale"]))
            for c in s["comments"]:
                d = directors.get(c["author"], {"email": "board@example-lochard.com.au", "name": c["author"]})
                cur.execute("""INSERT INTO scorecard.comment (kpi_id, period_code, author_email, author_name, author_role,
                               body, visibility) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                            (c["kpi_id"], c["period_code"], d["email"], d["name"], c["author_role"], c["body"], c["visibility"]))
            for d in s["directors"]:
                cur.execute("INSERT INTO scorecard.app_user_role (email, role, display_name, title) VALUES (%s,'BOARD',%s,%s) "
                            "ON CONFLICT (email) DO NOTHING", (d["email"], d["name"], d["title"]))
            for initials, role in s["owner_roles"].items():
                cur.execute("INSERT INTO scorecard.app_user_role (email, role, display_name, title, initials) "
                            "VALUES (%s,'LLT',%s,%s,%s) ON CONFLICT (email) DO NOTHING",
                            (f"{initials.lower()}@example-lochard.com.au", role, role, initials))
    log.info("seeded scorecard")
    return True
