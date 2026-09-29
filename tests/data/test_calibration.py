"""Calibration tests: the generated source extracts must reproduce the PBI / Tableau numbers.

Run after a local backfill:  .venv/bin/python -m pytest tests/data -q   (LOCHARD_OUT defaults to out/raw)
"""
import glob
import os
import sys
from datetime import date

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src", "data_generation"))
import config as C  # noqa: E402

OUT = os.environ.get("LOCHARD_OUT", "out/raw")


def _read(pattern, **kw):
    files = sorted(glob.glob(os.path.join(OUT, pattern), recursive=True))
    if not files:
        pytest.skip(f"no files for {pattern}")
    return pd.concat([pd.read_csv(f, low_memory=False, **kw) for f in files], ignore_index=True)


@pytest.fixture(scope="module")
def cc():
    return _read("erp/cost_centres/**/*.csv").drop_duplicates("cost_centre_key", keep="last").set_index("cost_centre_key")


@pytest.fixture(scope="module")
def gl(cc):
    g = _read("erp/gl_entries/**/*.csv")
    g["team"] = g.cost_centre_key.map(cc.team)
    g["posting_date"] = pd.to_datetime(g.date_key.astype(str))
    return g


def test_fy27_budget_by_team(cc):
    b = _read("erp/budget/**/*.csv")
    b = b[b.budget_name == "SITEBUD27"]
    got = (b.groupby(b.cost_centre_key.map(cc.team)).amount.sum() / 1e3).round(0)
    for team, v in C.TEAMS.items():
        assert got[team] == pytest.approx(v[1], abs=1), team
    assert got.sum() == pytest.approx(180_209, abs=2)


def test_fy27_ytd_actuals_by_team(gl):
    ytd = gl[(gl.posting_date >= "2026-07-01") & (gl.posting_date <= "2026-08-31")]
    got = (ytd.groupby("team").amount.sum() / 1e3).round(0)
    for team, v in C.TEAMS.items():
        assert got[team] == pytest.approx(v[2], abs=1), team
    assert ytd.amount.sum() / 1e6 == pytest.approx(3.778, abs=0.01)


def test_hugs_drill_through(gl):
    h = gl[(gl.cost_centre_key == C.HUGS_CC) & (gl.posting_date >= "2026-07-01")]
    assert round(h.amount.sum(), 2) == pytest.approx(-197_041.83, abs=0.01)
    by_m = h.groupby(h.posting_date.dt.month).amount.sum()
    assert by_m[7] == pytest.approx(1_503_000, abs=1) and by_m[8] == pytest.approx(-1_700_041.83, abs=1)


def test_fy27_yeo_by_team(cc):
    y = _read("erp/yeo/**/yeo_FY27_YEO_M02.csv")
    got = (y.groupby(y.cost_centre_key.map(cc.team)).amount.sum() / 1e3).round(0)
    for team, v in C.TEAMS.items():
        assert got[team] == pytest.approx(v[3], abs=1), team


def test_committed_by_team(cc):
    po = _read("maximo/purchase_orders/**/*.csv")
    op = po[po.po_status == "APPR"]
    got = ((op.line_cost - op.invoiced_amount).groupby(op.cost_centre_key.map(cc.team)).sum() / 1e3).round(0)
    for team, v in C.TEAMS.items():
        if v[4]:
            assert got.get(team, 0) == pytest.approx(v[4], abs=2), team


def test_golden_rows_present(gl):
    seed = pd.read_excel("docs/Sample Data.xlsx", sheet_name="fact_actuals", keep_default_na=False)
    assert set(seed.entry_no).issubset(set(gl.entry_no))
    assert gl.entry_no.is_unique


def test_hse_counters():
    o = pd.concat([pd.read_json(f, lines=True) for f in glob.glob(f"{OUT}/hse/observations/**/*.json", recursive=True)])
    inc, inv = o[o.classification == "INCIDENT"], o[o.classification == "INVESTIGATION"]
    assert len(inc) == 5132 and (inc.status != "CLOSED").sum() == 321 and (inc.status == "CLOSED").sum() == 4811
    assert len(inv) == 140 and (inv.status != "CLOSED").sum() == 7
    open_ = inc[inc.status != "CLOSED"].actual_risk_rank.value_counts().to_dict()
    assert open_ == {"Unknown": 245, "LOW": 35, "MEDIUM": 34, "HIGH": 7}
    share = inc.incident_category.value_counts(normalize=True).round(3).to_dict()
    assert share["GENERAL SAFETY"] == pytest.approx(0.722, abs=0.001)


def test_maintenance_kpis_latest_snapshot():
    s = pd.read_csv(f"{OUT}/maximo/schedule_snapshot/snapshot_date=2026-08-04/scheduled_workorders_20260804.csv",
                    na_values=["null"])
    closed = {"CLOSE", "COMP", "CAN", "CLOSED", "SRCAN"}
    op = s[~s.status.isin(closed)]
    assert s[s.work_type != "PM"].backlog_count.sum() == 5328
    assert op[op.priority_bucket == "P1"].workorder_count.sum() == 4
    assert op[(op.priority_bucket == "P2") & (op.work_type != "PM")].workorder_count.sum() == 635
    assert s.overdue_safety_critical_count.sum() == 25
    w = s[s.schedule_week_date_key != 19000101].groupby("schedule_week_date_key")
    pct = (100 * w.schedule_compliant_count.sum() / w.scheduled_count.sum()).round(1).tolist()
    assert len(pct) == 13 and pct[-1] == pytest.approx(84.4, abs=0.2)
    for got, exp in zip(pct, C.MX_COMPLIANCE_PCT):
        assert got == pytest.approx(exp, abs=1.2)
    types = s[s.schedule_week_date_key != 19000101].groupby("work_type").scheduled_count.sum()
    assert types["PM"] == 575 and types["GPC"] == 105 and types["DM"] == 92 and types["CBM"] == 59


def test_vic_demand_monthly_pj():
    d = pd.concat([pd.read_csv(f) for f in glob.glob(f"{OUT}/aemo/int287/synthetic/*.csv")], ignore_index=True)
    d["gd"] = pd.to_datetime(d.gas_date, format="%d %b %Y")
    for y, months in C.VIC_MONTHLY_PJ.items():
        for m, pj in enumerate(months, 1):
            got = d[(d.gd.dt.year == y) & (d.gd.dt.month == m)].total_gas_used.sum() / 1e6
            assert got == pytest.approx(pj, abs=0.05), (y, m)
