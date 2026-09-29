"""Iona historian / nominations extracts: daily injection, withdrawal and inventory, per-site well flows,
customer nominations vs delivered (±4 % tolerance – scorecard KPI 1.2) and compressor availability."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

import config as C
from common import Lander, rng, ts

CUSTOMERS = ["Retailer A", "Retailer B", "Generator C", "Trader D", "Retailer E"]
SHARE = [0.34, 0.26, 0.18, 0.12, 0.10]
SITES = {"Iona": 0.62, "North Paaratte": 0.14, "Wallaby Creek": 0.12, "Seamer": 0.12}
COMPRESSORS = ["CMP-K101", "CMP-K102", "CMP-K103", "CMP-K104", "CMP-K105"]


def build(L: Lander, market: dict | None) -> dict[str, pd.DataFrame]:
    g = rng(50)
    m = market["daily"].copy() if market else None
    m = m[m.gas_date >= date(2018, 1, 1)].reset_index(drop=True)
    dem_tj = m.total_gas_used.values / 1000
    wdl = np.clip((dem_tj - 560) * 0.62 + g.normal(0, 18, len(m)), 0, C.IONA_MAX_WITHDRAWAL_TJ)
    inj = np.clip((470 - dem_tj) * 0.55 + g.normal(0, 10, len(m)), 0, C.IONA_MAX_INJECTION_TJ)
    inj[wdl > 5] = 0
    inv = np.zeros(len(m))
    cap = np.where(m.gas_date >= date(2027, 1, 31), C.IONA_CAPACITY_PJ_POST_HUGS, C.IONA_CAPACITY_PJ) * 1000
    level = 17_500.0
    for i in range(len(m)):
        if level + inj[i] > cap[i]:
            inj[i] = max(cap[i] - level, 0)
        if level - wdl[i] < 1500:            # keep a working-gas floor
            wdl[i] = max(level - 1500, 0)
        level = level + inj[i] - wdl[i]
        inv[i] = level
    ops = pd.DataFrame(dict(gas_date=m.gas_date, injection_tj=inj.round(1), withdrawal_tj=wdl.round(1),
                            inventory_tj=inv.round(0), vic_demand_tj=dem_tj.round(1)))
    comp_avail = np.clip(g.normal(0.965, 0.025, len(m)), 0.7, 1.0)
    outage = g.random(len(m)) < 0.01                      # ~1 % of days lose a compressor unit
    comp_avail[outage] = g.uniform(0.55, 0.8, outage.sum())
    ops["compressor_availability"] = comp_avail.round(4)
    ops["updated_at"] = [ts(d + timedelta(days=1), 7, 0) for d in ops.gas_date]
    # per-site well flows
    site_rows = []
    for s, sh in SITES.items():
        f = g.normal(1, 0.05, len(ops))
        site_rows.append(pd.DataFrame(dict(gas_date=ops.gas_date, site=s, injection_tj=(ops.injection_tj * sh * f).round(2),
                                           withdrawal_tj=(ops.withdrawal_tj * sh * f).round(2))))
    sites = pd.concat(site_rows, ignore_index=True)
    # nominations vs delivered: tolerance breaches are rare; FY27 has 2 breaches with no refunds payable
    nom_rows = []
    for c, sh in zip(CUSTOMERS, SHARE):
        nom = (ops.withdrawal_tj + ops.injection_tj) * sh * g.normal(1, 0.03, len(ops))
        dev = g.normal(0, 0.012, len(ops))
        breach = g.random(len(ops)) < 0.0015
        dev[breach] = g.choice([-1, 1], breach.sum()) * g.uniform(0.045, 0.08, breach.sum())
        nom_rows.append(pd.DataFrame(dict(gas_date=ops.gas_date, customer=c, nominated_tj=nom.round(2),
                                          delivered_tj=(nom * (1 + dev)).round(2))))
    noms = pd.concat(nom_rows, ignore_index=True)
    noms = noms[noms.nominated_tj > 0.5]
    fy27 = noms.gas_date >= date(2026, 7, 1)
    noms.loc[fy27, "delivered_tj"] = np.where(
        (noms.loc[fy27, "delivered_tj"] / noms.loc[fy27, "nominated_tj"] - 1).abs() > 0.04,
        noms.loc[fy27, "nominated_tj"] * 1.01, noms.loc[fy27, "delivered_tj"])
    b = noms[fy27 & noms.customer.eq("Generator C")].index[[12, 31]]   # two FY27 breaches, no refund payable
    noms.loc[b, "delivered_tj"] = (noms.loc[b, "nominated_tj"] * 0.952).round(2)
    noms["refund_payable"] = False
    noms["updated_at"] = [ts(d + timedelta(days=1), 7, 30) for d in noms.gas_date]
    for y, grp in ops.groupby(ops.gas_date.map(lambda d: d.year)):
        L.parquet(f"ops/historian_daily/year={y}/iona_daily_{y}.parquet", grp)
    for y, grp in sites.groupby(sites.gas_date.map(lambda d: d.year)):
        L.parquet(f"ops/site_flows/year={y}/site_flows_{y}.parquet", grp)
    for y, grp in noms.groupby(noms.gas_date.map(lambda d: d.year)):
        L.csv(f"ops/nominations/year={y}/nominations_{y}.csv", grp)
    return dict(ops=ops, sites=sites, noms=noms)
