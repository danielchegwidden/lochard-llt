"""HSE system extracts: observation-level records, investigations, hours worked / injuries.

Calibration (PBI HSE Observations, Class = INCIDENT): 5,132 observations (321 open: NEW 279 / INPROG 42),
140 investigations (7 open), category mix 72.2/11.0/10.5/5.5/0.8, actual-risk × status matrix exact, cumulative
by type rising May-25 → Jul-26 after the HSE process upgrade (scorecard KPI 1.1).
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

import config as C
from common import Lander, date_key, rng, ts

TYPES_END = {"SAFEACT": 2180, "HAZARD": 1600, "INCIDENT": 697, "HAZARD_REPORT": 350, "NEARMISS": 295, "Other": 10}
TYPES_MAY25 = {"SAFEACT": 1500, "HAZARD": 1280, "INCIDENT": 580, "HAZARD_REPORT": 348, "NEARMISS": 200, "Other": 8}
UPGRADE = date(2025, 5, 1)          # HSE Incident/Observations process upgrade (KPI 1.1 deliverable)
AREAS = ["Compression", "Dehydration", "Metering", "Wells", "Control Room", "Workshop", "Warehouse", "Site Roads",
         "Pipelines", "HUGS Construction", "Melbourne Office", "Utilities"]
TEMPLATES = {
    "SAFEACT": ["Positive observation – correct isolation and lock-out applied at {a}",
                "Good housekeeping maintained in {a} during shutdown works",
                "Crew stopped work to re-assess lifting plan at {a}",
                "Correct PPE and gas monitor used for confined space entry at {a}",
                "Contractor completed JSA review before work on {a}"],
    "HAZARD": ["Trip hazard – loose grating near {a}", "Corroded handrail identified at {a}",
               "Unsecured gas cylinders stored at {a}", "Missing guard on rotating equipment at {a}",
               "Poor lighting on access stairs at {a}", "Vegetation encroaching fire break near {a}",
               "Oil leak from compressor skid at {a}"],
    "HAZARD_REPORT": ["Hazard report – damaged signage at {a}", "Hazard report – blocked emergency exit at {a}"],
    "NEARMISS": ["Dropped object (spanner) from scaffold at {a} – no one below",
                 "Vehicle reversed without spotter near {a}", "Gas detector alarm during valve maintenance at {a}",
                 "Pressure not fully bled down before breaking containment at {a}"],
    "INCIDENT": ["Minor hydrocarbon spill (<5 L) at {a}, contained and cleaned up",
                 "First aid – laceration to hand while handling pipe at {a}",
                 "Light vehicle minor damage in car park at {a}", "Small glycol release from pump seal at {a}",
                 "Short gas release from wellhead needle valve at {a}", "Contractor strain injury lifting at {a}"],
    "Other": ["General HSE feedback – {a}"],
}
INVESTIGATION_TITLES = ["Loss of containment – wellhead needle valve", "Dropped object from height",
                        "Vehicle interaction near wellpad", "Process safety event – relief valve lift",
                        "Hand injury during pipe handling", "Glycol release to bund"]


def _monthly_counts(g, start: date, end: date, total: int, ramp: float = 1.0, winter: float = 0.15) -> pd.Series:
    months = pd.period_range(start, end, freq="M")
    t = np.linspace(0, 1, len(months))
    w = (1 + (ramp - 1) * t) * (1 + winter * np.sin((months.month.values - 3) / 12 * 2 * np.pi))
    w = w * g.lognormal(0, 0.18, len(months))
    raw = total * w / w.sum()
    cnt = np.floor(raw).astype(int)
    cnt[np.argsort(raw - cnt)[::-1][: total - cnt.sum()]] += 1
    return pd.Series(cnt, index=months)


def build(L: Lander, refs: dict, seed: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    g = rng(20)
    people = refs["people"].username.tolist()
    rows = []
    for typ in TYPES_END:
        before = TYPES_MAY25[typ]
        after = TYPES_END[typ] - before
        for (s, e, n, ramp) in [(C.HSE_FIRST_DATE, UPGRADE - timedelta(days=1), before, 1.8 if typ != "HAZARD_REPORT" else 0.2),
                                (UPGRADE, C.AS_OF, after, 1.1)]:
            if n <= 0:
                continue
            if typ == "HAZARD_REPORT" and s == C.HSE_FIRST_DATE:
                e = date(2019, 12, 31)   # legacy form retired in 2020
            for per, k in _monthly_counts(g, s, e, n, ramp).items():
                if k == 0:
                    continue
                days = pd.date_range(max(per.start_time.date(), s), min(per.end_time.date(), e))
                for d in g.choice(len(days), size=k):
                    rows.append(dict(observation_type=typ, reported_date=days[d].date()))
    obs = pd.DataFrame(rows).sort_values("reported_date").reset_index(drop=True)
    n = len(obs)
    assert n == C.HSE_TOTAL_OBSERVATIONS, n
    obs["observation_id"] = [f"OBS-{100000 + i}" for i in range(n)]
    obs["classification"] = "INCIDENT"
    # category mix (exact largest-remainder)
    obs["incident_category"] = _exact_labels(g, n, C.HSE_CATEGORY_SHARE)
    # status + actual risk: open observations skew recent, matrix exact
    obs["status"], obs["actual_risk_rank"] = _status_and_rank(g, obs)
    obs["potential_risk_rank"] = _potential(g, obs.actual_risk_rank)
    obs["plant_area"] = g.choice(AREAS, size=n, p=_p([12, 8, 5, 12, 6, 9, 6, 8, 5, 14, 5, 10]))
    obs["description"] = [str(g.choice(TEMPLATES[t])).format(a=a) for t, a in zip(obs.observation_type, obs.plant_area)]
    obs["actionee"] = g.choice(people, size=n)
    obs["reported_by"] = g.choice(people, size=n)
    obs["due_date"] = obs.reported_date + pd.to_timedelta(g.integers(7, 45, n), unit="D")
    close_lag = pd.to_timedelta(np.clip(g.gamma(1.6, 9, n), 0, 200).astype(int), unit="D")
    obs["closed_date"] = np.where(obs.status.eq("CLOSED"), (pd.to_datetime(obs.reported_date) + close_lag).dt.date, None)
    obs["closed_date"] = [min(d, C.AS_OF) if d else None for d in obs.closed_date]
    obs["is_high_potential_event"] = False
    obs["investigation_id"] = None
    # FY27 High Potential Event (drives KPI 1.1 "At Risk")
    hpe_idx = obs.index[(obs.observation_type == "INCIDENT") & (obs.reported_date >= date(2026, 8, 1))
                        & (obs.reported_date <= date(2026, 8, 31))][:1]
    obs.loc[hpe_idx, ["incident_category", "potential_risk_rank", "is_high_potential_event", "plant_area"]] = \
        ["PROCESS SAFETY", "HIGH", True, "Wells"]
    obs.loc[hpe_idx, "description"] = "Uncontrolled gas release from Iona-3 wellhead flange during bonnet maintenance – HPE"

    inv = _investigations(g, obs, people)
    obs = obs.merge(inv[["observation_id", "investigation_id"]].rename(columns={"investigation_id": "inv"}),
                    on="observation_id", how="left")
    obs["investigation_id"] = obs.inv
    obs = obs.drop(columns=["inv"])
    obs["updated_at"] = [ts(c or r) for c, r in zip(obs.closed_date, obs.reported_date)]
    # investigation rows also appear in the observation feed with classification = INVESTIGATION
    inv_rows = inv.assign(classification="INVESTIGATION", observation_type="INCIDENT",
                          observation_id=inv.investigation_id)[obs.columns.intersection(inv.columns.union(
                              ["classification", "observation_type", "observation_id"]))]
    feed = pd.concat([obs, inv_rows], ignore_index=True)

    # land daily JSON extracts (history monthly, current month daily)
    feed["_load"] = [d if d >= date(2026, 9, 1) else date(d.year, d.month, 1) for d in feed.reported_date]
    for d, grp in feed.groupby("_load"):
        L.jsonl(f"hse/observations/load_date={d}/observations_{d:%Y%m%d}.json", grp.drop(columns=["_load"]))
    L.csv(f"hse/investigations/load_date={C.AS_OF}/investigations.csv", inv)
    hours = _hours(g)
    L.csv(f"hse/hours_worked/load_date={C.AS_OF}/hours_worked.csv", hours)
    # the supplied aggregate sample is kept verbatim (actionees pseudonymised) as the legacy summary extract
    import seed as S
    legacy = S.pseudonymise_actionees(seed["Observations"], refs["people"])
    L.csv("hse/legacy_summary/load_date=2026-04-02/observations_summary_20260401.csv", legacy)
    return dict(observations=obs, investigations=inv, hours=hours)


def _p(w):
    w = np.array(w, dtype=float)
    return w / w.sum()


def _exact_labels(g, n, share: dict) -> np.ndarray:
    raw = np.array(list(share.values())) * n
    cnt = np.floor(raw).astype(int)
    cnt[np.argsort(raw - cnt)[::-1][: n - cnt.sum()]] += 1
    labels = np.repeat(list(share.keys()), cnt)
    g.shuffle(labels)
    return labels


def _status_and_rank(g, obs):
    n = len(obs)
    status = np.array(["CLOSED"] * n, dtype=object)
    rank = np.array([None] * n, dtype=object)
    age = (pd.Timestamp(C.AS_OF) - pd.to_datetime(obs.reported_date)).dt.days.values
    # open observations: mostly last 9 months, a tail of older backlog
    w_open = np.where(age < 270, 6.0, np.where(age < 720, 0.8, 0.08))
    open_idx = g.choice(n, size=C.HSE_OPEN_OBSERVATIONS, replace=False, p=w_open / w_open.sum())
    open_idx = open_idx[np.argsort(age[open_idx])]            # youngest first → NEW, older → INPROG
    status[open_idx[: C.HSE_STATUS["NEW"]]] = "NEW"
    status[open_idx[C.HSE_STATUS["NEW"]:]] = "INPROG"
    for st in ["NEW", "INPROG", "CLOSED"]:
        idx = np.where(status == st)[0]
        labels = np.concatenate([[r] * C.HSE_RISK_STATUS[r][st] for r in C.HSE_RISK_STATUS])
        g.shuffle(labels)
        rank[idx] = labels
    return status, rank


def _potential(g, actual):
    order = ["LOW", "MEDIUM", "HIGH"]
    out = []
    for a in actual:
        if a == "Unknown":
            out.append(str(g.choice(["Unknown", "LOW", "MEDIUM", "HIGH"], p=[.55, .25, .14, .06])))
        else:
            i = order.index(a)
            out.append(order[min(2, i + int(g.random() < 0.35))])
    return out


def _investigations(g, obs, people):
    cand = obs[(obs.observation_type.isin(["INCIDENT", "NEARMISS"])) & obs.potential_risk_rank.isin(["HIGH", "MEDIUM"])]
    cand = cand.sort_values("reported_date")
    hpe = obs[obs.is_high_potential_event]
    pick = pd.concat([cand.sample(n=C.HSE_INVESTIGATIONS_TOTAL - len(hpe), random_state=3), hpe]).sort_values("reported_date")
    inv = pd.DataFrame({
        "investigation_id": [f"INV-{2000 + i}" for i in range(len(pick))],
        "observation_id": pick.observation_id.values,
        "reported_date": pick.reported_date.values,
        "incident_category": pick.incident_category.values,
        "potential_risk_rank": pick.potential_risk_rank.values,
        "actual_risk_rank": pick.actual_risk_rank.values,
        "plant_area": pick.plant_area.values,
        "title": g.choice(INVESTIGATION_TITLES, size=len(pick)),
        "lead_investigator": g.choice(people, size=len(pick)),
        "method": g.choice(["ICAM", "5 Whys", "TapRooT"], size=len(pick), p=[.6, .3, .1]),
        "is_privileged": g.random(len(pick)) < 0.25,          # legal privilege – hidden from non-investigators
    })
    inv["status"] = "CLOSED"
    inv.loc[inv.index[-C.HSE_INVESTIGATIONS_OPEN:], "status"] = "INPROG"
    inv["closed_date"] = [None if s != "CLOSED" else min(d + timedelta(days=int(g.integers(14, 90))), C.AS_OF)
                          for s, d in zip(inv.status, inv.reported_date)]
    inv["root_cause"] = np.where(inv.status.eq("CLOSED"), g.choice(
        ["Inadequate isolation procedure", "Equipment degradation (corrosion)", "Supervision / planning gap",
         "Human factors – fatigue", "Design deficiency", "Contractor competency"], size=len(inv)), None)
    inv["updated_at"] = [ts(c or r) for c, r in zip(inv.closed_date, inv.reported_date)]
    return inv


def _hours(g):
    months = pd.period_range(C.HSE_FIRST_DATE, C.AS_OF, freq="M")
    rows = []
    for m in months:
        emp = int(g.normal(10500, 600))
        con = int(g.normal(7000 if m.start_time.date() < date(2024, 7, 1) else 16000, 1500))  # HUGS construction
        rec = int(g.poisson(0.35 if m.start_time.date() < date(2026, 7, 1) else 0))           # nil recordables FY27 YTD
        lti = int(rec > 0 and g.random() < 0.3)
        rows.append(dict(month=str(m), employee_hours=emp, contractor_hours=max(con, 2000), recordable_injuries=rec,
                         lost_time_injuries=lti, updated_at=ts(m.end_time.date())))
    return pd.DataFrame(rows)
