#!/usr/bin/env python3
"""Local equivalent of src/common/run_sql_dir.py via the SQL warehouse (dev loop).
usage: scripts/apply_sql_dir.py <dir> [--only 01,02] [--var k=v ...]"""
import argparse, glob, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "common"))
from sql import run, warehouse_id  # noqa
import importlib.util
spec = importlib.util.spec_from_file_location("r", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "common", "run_sql_dir.py"))
ap = argparse.ArgumentParser(); ap.add_argument("dir"); ap.add_argument("--only"); ap.add_argument("--var", action="append", default=[])
ap.add_argument("--catalog", default="dc_demo_workspace_02_catalog"); ap.add_argument("--prefix", default="lochard_")
a = ap.parse_args()
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "common", "run_sql_dir.py")).read()
ns = {}; exec(src.split("def main")[0].replace("from pyspark.sql import SparkSession", ""), ns)
c, p = a.catalog, a.prefix
subs = {"catalog": c, "gold": f"{c}.{p}gold", "silver": f"{c}.{p}silver", "semantic": f"{c}.{p}semantic",
        "governance": f"{c}.{p}governance", "ai": f"{c}.{p}ai", "platform": f"{c}.{p}platform"}
subs.update(dict(v.split("=", 1) for v in a.var))
wh = warehouse_id(); bad = 0
for f in sorted(glob.glob(os.path.join(a.dir, "*.sql"))):
    if a.only and not any(os.path.basename(f).startswith(o) for o in a.only.split(",")): continue
    text = re.sub(r"\{(" + "|".join(subs) + r")\}", lambda m: subs[m.group(1)], open(f).read())
    for stmt in ns["statements"](text):
        if run(stmt, wh, quiet=True) is None: bad += 1
    print(os.path.basename(f), "done")
print("failures:", bad)
