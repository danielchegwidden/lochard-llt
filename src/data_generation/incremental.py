"""Daily incremental drops (what the interfaces send each morning): today's GL postings, new HSE observations,
yesterday's historian/nominations day. Used by the daily orchestrator to demonstrate incremental Auto Loader
processing; deterministic per business date."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

import config as C
import gen_reference
from common import Lander, date_key, rng, ts


def run(L: Lander, d: date):
    g = rng(int(d.strftime("%Y%m%d")) % 100000)
    cc = gen_reference.cost_centres(g)
    people = gen_reference.people(rng(1))
    vendors = gen_reference.vendors(rng(1))
    # ---- GL: 20–60 postings for business day d (entry numbers in a date-derived range → idempotent re-runs)
    if d.weekday() < 5:
        n = int(g.integers(20, 60))
        base = 900_000_000 + (d - date(2026, 1, 1)).days * 1000
        ops_cc = cc[cc.team.isin(["Maintenance", "Asset Management", "Operations", "SIB Projects"])].cost_centre_key.tolist()
        rows = []
        for i in range(n):
            amt = round(float(g.lognormal(6.2, 1.1)), 2)
            k = str(g.choice(ops_cc))
            po = f"2636{int(g.integers(20000, 29999)):05d}"
            wo = f"3626{int(g.integers(100000, 199999)):06d}"
            rows.append(dict(gl_entry_key=f"{base + i}|{C.COMPANY}", date_key=date_key(d), cost_centre_key=k,
                             account_key=int(g.choice([623000, 625250, 626900])),
                             source_key=str(g.choice(vendors.source_key[:30])), purchase_order_key=f"{po}|S3620",
                             work_order_key=f"{wo}|S3620", entry_no=base + i, company_name=C.COMPANY,
                             document_no=f"MXO{9_000_000 + (base + i) % 1_000_000:07d}", external_document_no=f"PO {po}",
                             description=str(g.choice(["Scaffold for compressor K104 service", "GASKET,SPIRAL WOUND, 50 MM, CLASS 600",
                                                       "Fire system service DCS-01", "FILTER ELEMENT, COALESCER",
                                                       "Wellhead maintenance Seamer-2 wellpad"])),
                             maximo_po_no=float(po), maximo_wo_no=float(wo), po_line_cost=round(amt * 1.2, 2),
                             amount=amt, gst_amount=0.0, reversed=False, reversed_by_entry_no=0, updated_at=ts(d, 6, 5)))
        # a malformed / defect row now and then (null key) – caught by silver expectations
        if g.random() < 0.3:
            bad = dict(rows[0]); bad.update(entry_no=None, gl_entry_key="null"); rows.append(bad)
        L.csv(f"erp/gl_entries/load_date={d + timedelta(days=1)}/gl_entries_{d:%Y%m%d}.csv", pd.DataFrame(rows))
    # ---- HSE: 1–6 new observations
    k = int(g.integers(1, 7))
    obs = pd.DataFrame(dict(
        observation_type=g.choice(["SAFEACT", "HAZARD", "INCIDENT", "NEARMISS"], k, p=[.45, .35, .1, .1]),
        reported_date=[d] * k, observation_id=[f"OBS-{int(d.strftime('%y%m%d'))}{i:02d}" for i in range(k)],
        classification="INCIDENT", incident_category=g.choice(list(C.HSE_CATEGORY_SHARE), k, p=list(C.HSE_CATEGORY_SHARE.values())),
        status="NEW", actual_risk_rank="Unknown", potential_risk_rank=g.choice(["LOW", "MEDIUM", "Unknown"], k),
        plant_area=g.choice(["Compression", "Wells", "Dehydration", "Workshop"], k),
        description=[f"New observation raised at {a}" for a in g.choice(["Compression", "Wells", "Workshop"], k)],
        actionee=g.choice(people.username, k), reported_by=g.choice(people.username, k),
        due_date=[d + timedelta(days=14)] * k, closed_date=None, is_high_potential_event=False, investigation_id=None,
        updated_at=ts(d, 16, 0)))
    L.jsonl(f"hse/observations/load_date={d}/observations_{d:%Y%m%d}.json", obs)
    # ---- historian + nominations for gas day d-1
    gd = d - timedelta(days=1)
    wdl = float(np.clip(g.normal(80, 40), 0, 570))
    hist = pd.DataFrame([dict(gas_date=gd, injection_tj=0.0, withdrawal_tj=round(wdl, 1), inventory_tj=10_500.0,
                              vic_demand_tj=round(float(g.normal(520, 60)), 1),
                              compressor_availability=round(float(np.clip(g.normal(.965, .02), .7, 1)), 4),
                              updated_at=ts(d, 7, 0))])
    L.parquet(f"ops/historian_daily/year={gd.year}/iona_daily_{gd:%Y%m%d}.parquet", hist)
