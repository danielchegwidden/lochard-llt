#!/usr/bin/env python3
"""Run SQL on the Lochard serverless warehouse via the Statement Execution API (dev helper).

Usage: scripts/sql.py "SELECT 1"   |   scripts/sql.py -f file.sql  (statements split on ';' at line end)
"""
import json, subprocess, sys, time, argparse, re

PROFILE = "fevm-dc-demo-workspace-02"


def warehouse_id():
    out = subprocess.run(["databricks", "-p", PROFILE, "warehouses", "list", "-o", "json"],
                         capture_output=True, text=True, check=True).stdout
    return next(w["id"] for w in json.loads(out) if w["name"] == "lochard-serverless-wh")


def run(stmt, wh, quiet=False):
    body = {"statement": stmt, "warehouse_id": wh, "wait_timeout": "50s", "on_wait_timeout": "CONTINUE",
            "format": "JSON_ARRAY", "disposition": "INLINE"}
    r = json.loads(subprocess.run(["databricks", "-p", PROFILE, "api", "post", "/api/2.0/sql/statements",
                                   "--json", json.dumps(body)], capture_output=True, text=True).stdout or "{}")
    while r.get("status", {}).get("state") in ("PENDING", "RUNNING"):
        time.sleep(2)
        r = json.loads(subprocess.run(["databricks", "-p", PROFILE, "api", "get",
                                       f"/api/2.0/sql/statements/{r['statement_id']}"],
                                      capture_output=True, text=True).stdout)
    state = r.get("status", {}).get("state")
    if state != "SUCCEEDED":
        print(f"!! {state}: {r.get('status', {}).get('error', {}).get('message', r)[:600]}\n   SQL: {stmt[:200]}")
        return None
    cols = [c["name"] for c in r.get("manifest", {}).get("schema", {}).get("columns", [])]
    rows = r.get("result", {}).get("data_array", []) or []
    if not quiet and cols:
        print(" | ".join(cols))
        for row in rows[:200]:
            print(" | ".join("" if v is None else str(v) for v in row))
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sql", nargs="?")
    ap.add_argument("-f", "--file")
    a = ap.parse_args()
    wh = warehouse_id()
    text = open(a.file).read() if a.file else a.sql
    stmts = [s.strip() for s in re.split(r";\s*\n", text) if s.strip() and not s.strip().startswith("--") or ("\n" in s.strip())]
    for s in stmts:
        s = s.strip().rstrip(";")
        if s and not all(l.strip().startswith("--") or not l.strip() for l in s.splitlines()):
            run(s, wh)
