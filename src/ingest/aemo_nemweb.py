"""Land the public AEMO Victorian gas (DWGM MIBB) reports from nemweb into the raw volume.

Reports: INT091 actual EDD, INT287 total gas used (the two feeds behind the Tableau workbook), INT313 allocated
injections/withdrawals (includes Iona MIRNs), INT037b indicative market price, INT153 demand forecast.
Files are content-hashed so re-runs are idempotent; Auto Loader picks up only new files.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

REPORTS = {
    "int091": "int091_v4_eddact_1.csv",
    "int287": "int287_v4_gas_consumption_1.csv",
    "int313": "int313_v4_allocated_injections_withdrawals_1.csv",
    "int037b": "int037b_v4_indicative_mkt_price_1.csv",
    "int153": "int153_v4_demand_forecast_rpt_1.csv",
}
AEST = timezone(timedelta(hours=10))


def fetch(base: str, name: str) -> bytes:
    req = urllib.request.Request(f"{base}/{name}", headers={"User-Agent": "lochard-data-platform/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="https://nemweb.com.au/Reports/Current/VicGas")
    ap.add_argument("--out", required=True, help="raw volume root, e.g. /Volumes/<cat>/lochard_landing/raw")
    ap.add_argument("--reports", default=",".join(REPORTS))
    a, _ = ap.parse_known_args(argv)
    now = datetime.now(AEST)
    ok, failed = 0, []
    for code in [r.strip() for r in a.reports.split(",") if r.strip()]:
        name = REPORTS[code]
        try:
            data = fetch(a.base_url, name)
        except Exception as e:  # keep going – one missing report must not block the others
            failed.append(f"{code}: {e}")
            continue
        h = hashlib.sha256(data).hexdigest()[:12]
        folder = f"{a.out}/aemo/{code}/current/load_date={now:%Y-%m-%d}"
        os.makedirs(folder, exist_ok=True)
        path = f"{folder}/{name.replace('.csv', '')}_{now:%Y%m%dT%H%M}_{h}.csv"
        if any(f.endswith(f"_{h}.csv") for f in os.listdir(folder)):
            print(f"{code}: unchanged ({h})")
            continue
        with open(path, "wb") as f:
            f.write(data)
        ok += 1
        print(f"{code}: {len(data):,} bytes -> {path}")
    print(f"landed {ok} file(s); failures: {failed or 'none'}")
    if failed and len(failed) == len(REPORTS):
        sys.exit(f"all AEMO downloads failed (serverless egress?): {failed}")


if __name__ == "__main__":
    main()
