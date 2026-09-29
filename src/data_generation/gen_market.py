"""Synthetic AEMO MIBB history in the exact nemweb file formats (INT091 Actual EDD, INT287 gas consumption).

Real nemweb files only hold the last ~30–60 days; the aemo_ingest job lands them daily and they win on
overlap (silver AUTO CDC sequences AEMO over SYNTHETIC). Calibration: monthly PJ totals for Jan–Aug 2021–2024
equal the Tableau "Cumulative VIC demand (Table)"; demand ≈ a + b·EDD with a weekday effect so the R² sheets
(weekday vs weekend) reproduce (R² ≈ 0.85–0.9).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

import config as C
from common import Lander, rng

YEAR_SCALE = {2014: 1.06, 2015: 1.06, 2016: 1.05, 2017: 1.05, 2018: 1.04, 2019: 1.03, 2020: 1.01, 2021: 1.0,
              2022: 1.0, 2023: 0.9, 2024: 0.88, 2025: 0.8, 2026: 0.72}
# VIC public holidays (subset, fixed-date + Easter approximations are fine for load shape)
FIXED_HOL = [(1, 1), (1, 26), (4, 25), (12, 25), (12, 26)]


def _aemo_date(d: date) -> str:
    return d.strftime("%d %b %Y")


def _aemo_ts(dt: datetime) -> str:
    return dt.strftime("%d %b %Y %H:%M:%S")


def build(L: Lander) -> dict[str, pd.DataFrame]:
    g = rng(40)
    days = pd.date_range(C.MARKET_FIRST_DATE, C.AS_OF - timedelta(days=1), freq="D")
    doy = days.dayofyear.values
    clim = np.clip(6.9 - 6.3 * np.cos(2 * np.pi * (doy - 15) / 365.25), 0.2, None)
    noise = np.zeros(len(days))
    for i in range(1, len(days)):
        noise[i] = 0.62 * noise[i - 1] + g.normal(0, 1.7)
    edd = np.clip(clim + noise, 0, 24).round(2)
    wd = days.weekday.values
    hol = np.array([(d.month, d.day) in FIXED_HOL for d in days])
    wk_factor = np.where(wd >= 5, 0.87, 1.0) * np.where(hol, 0.86, 1.0)
    scale = np.array([YEAR_SCALE[y] for y in days.year])
    demand = scale * (292_000 + 49_500 * edd) * wk_factor * g.normal(1, 0.035, len(days))
    df = pd.DataFrame(dict(gas_date=days.date, edd=edd, demand=demand))
    # exact monthly calibration to the Tableau table (PJ, 1 dp)
    for y, months in C.VIC_MONTHLY_PJ.items():
        for m, pj in enumerate(months, start=1):
            sel = (days.year == y) & (days.month == m)
            df.loc[sel, "demand"] *= pj * 1e6 / df.loc[sel, "demand"].sum()
    df["total_gas_used"] = df.demand.round(0).astype("int64")
    # ---------------------------------------------------------------- land in AEMO format, yearly files
    for y, grp in df.groupby(days.year):
        i091 = pd.DataFrame(dict(
            edd_update=[_aemo_ts(datetime.combine(d + timedelta(days=1), datetime.min.time()) + timedelta(hours=14, minutes=2))
                        for d in grp.gas_date],
            edd_date=[_aemo_date(d) for d in grp.gas_date], edd_value=grp.edd.map(lambda v: f"{v:.2f}"), edd_type=1,
            current_date=_aemo_ts(datetime(2026, 9, 22, 18, 0, 5))))
        i287 = pd.DataFrame(dict(gas_date=[_aemo_date(d) for d in grp.gas_date], total_gas_used=grp.total_gas_used,
                                 current_date=_aemo_ts(datetime(2026, 9, 22, 9, 0, 11))))
        L.csv(f"aemo/int091/synthetic/int091_v4_eddact_synthetic_{y}.csv", i091)
        L.csv(f"aemo/int287/synthetic/int287_v4_gas_consumption_synthetic_{y}.csv", i287)
    return dict(daily=df)
