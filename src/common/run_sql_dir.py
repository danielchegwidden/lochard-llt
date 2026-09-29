"""Apply a folder of templated SQL (semantic layer, governance) as an idempotent job task. Metric views, UDFs, tags
and ABAC policies are not bundle resources, so they are deployed from git by this runner after the pipelines.
Usage: run_sql_dir.py --dir <folder> --catalog <c> --prefix lochard_ [--var etl_sp=<id>] [--only 01,02]"""
import argparse
import glob
import os
import re
import sys

from pyspark.sql import SparkSession


def statements(text: str):
    # split on ';' at end of line, but keep $$...$$ YAML bodies intact
    parts, buf, in_yaml = [], [], False
    for line in text.splitlines():
        if line.strip().startswith("--") and not in_yaml:
            continue
        in_yaml ^= line.count("$$") % 2 == 1
        buf.append(line)
        if not in_yaml and line.rstrip().endswith(";"):
            parts.append("\n".join(buf).rstrip().rstrip(";"))
            buf = []
    if "".join(buf).strip():
        parts.append("\n".join(buf))
    return [p for p in parts if p.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--dir", default=None)
    ap.add_argument("--only", default=None, help="comma list of file name prefixes to run")
    ap.add_argument("--var", action="append", default=[], help="extra {key} substitutions, key=value")
    a, _ = ap.parse_known_args()
    here = a.dir or os.path.dirname(os.path.abspath(sys.argv[0]))
    spark = SparkSession.builder.getOrCreate()
    subs = {"catalog": a.catalog, "gold": f"{a.catalog}.{a.prefix}gold", "silver": f"{a.catalog}.{a.prefix}silver",
            "semantic": f"{a.catalog}.{a.prefix}semantic", "governance": f"{a.catalog}.{a.prefix}governance",
            "ai": f"{a.catalog}.{a.prefix}ai", "platform": f"{a.catalog}.{a.prefix}platform"}
    subs.update(dict(v.split("=", 1) for v in a.var))
    files = sorted(glob.glob(os.path.join(here, "*.sql")))
    if a.only:
        files = [f for f in files if any(os.path.basename(f).startswith(o) for o in a.only.split(","))]
    n = 0
    for f in files:
        text = open(f).read()
        text = re.sub(r"\{(" + "|".join(subs) + r")\}", lambda m: subs[m.group(1)], text)
        for stmt in statements(text):
            spark.sql(stmt)
            n += 1
        print(f"{os.path.basename(f)}: ok")
    print(f"applied {n} statements")


if __name__ == "__main__":
    main()
