"""Lochard synthetic source-system generator.

Writes files into the landing volume exactly as the upstream interfaces would drop them
(Business Central GL/budget/YEO, Maximo POs/WOs/schedule snapshots, HSE system, historian,
AEMO-format market files, documents). Serverless job entry point and local CLI.

  python main.py --mode backfill --out /Volumes/<catalog>/<prefix>landing/raw --docs /Volumes/.../documents
  python main.py --mode incremental --date 2026-09-24 --out ...
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date

def _code_dir() -> str:
    # serverless spark_python_task exec()s the file, so __file__ may be undefined
    if "--code-dir" in sys.argv:
        return sys.argv[sys.argv.index("--code-dir") + 1]
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.path.dirname(os.path.abspath(sys.argv[0]))


sys.path.insert(0, _code_dir())

import config as C  # noqa: E402
import seed as S  # noqa: E402
from common import Lander  # noqa: E402

STEPS = ["reference", "finance", "hse", "maintenance", "market", "ops", "scorecard", "documents"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["backfill", "incremental"], default="backfill")
    ap.add_argument("--out", required=True, help="landing root (raw volume)")
    ap.add_argument("--docs", default=None, help="documents volume root")
    ap.add_argument("--date", default=None, help="incremental business date (YYYY-MM-DD)")
    ap.add_argument("--steps", default=",".join(STEPS))
    ap.add_argument("--sample-xlsx", default=None)
    ap.add_argument("--code-dir", default=None)
    a, _ = ap.parse_known_args(argv)
    if a.sample_xlsx:
        os.environ["LOCHARD_SAMPLE_XLSX"] = a.sample_xlsx
    steps = [s.strip() for s in a.steps.split(",") if s.strip()]
    L = Lander(a.out)
    D = Lander(a.docs or os.path.join(a.out, "_documents"))
    t0 = time.time()

    if a.mode == "incremental":
        import incremental
        incremental.run(L, date.fromisoformat(a.date) if a.date else C.AS_OF)
        _report(L, t0)
        return

    seed = S.load()
    import gen_reference
    refs = gen_reference.write_all(L, C.AS_OF)
    out = {"refs": refs}
    if "finance" in steps:
        import gen_finance
        out["finance"] = gen_finance.build(L, refs, seed)
        print(f"finance done {time.time() - t0:.0f}s", flush=True)
    if "hse" in steps:
        import gen_hse
        out["hse"] = gen_hse.build(L, refs, seed)
        print(f"hse done {time.time() - t0:.0f}s", flush=True)
    if "maintenance" in steps:
        import gen_maintenance
        out["maintenance"] = gen_maintenance.build(L, refs, seed)
        print(f"maintenance done {time.time() - t0:.0f}s", flush=True)
    if "market" in steps:
        import gen_market
        out["market"] = gen_market.build(L)
        print(f"market done {time.time() - t0:.0f}s", flush=True)
    if "ops" in steps:
        import gen_ops
        out["ops"] = gen_ops.build(L, out.get("market"))
        print(f"ops done {time.time() - t0:.0f}s", flush=True)
    if "scorecard" in steps:
        import gen_scorecard
        out["scorecard"] = gen_scorecard.build(L, refs)
        print(f"scorecard done {time.time() - t0:.0f}s", flush=True)
    if "documents" in steps:
        import gen_documents
        gen_documents.build(D, L, out)
        print(f"documents done {time.time() - t0:.0f}s", flush=True)
    _report(L, t0)
    return out


def _report(L: Lander, t0: float):
    print(f"Wrote to {L.root} in {time.time() - t0:.0f}s")
    for k, v in sorted(L.counts.items()):
        print(f"  {k:45s} {v:>9,d} rows")


if __name__ == "__main__":
    main()
