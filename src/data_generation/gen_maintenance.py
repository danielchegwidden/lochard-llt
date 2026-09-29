"""Maximo extracts: work-order detail, weekly schedule snapshots (the PBI grain) and the planners'
external weekly schedule-hours spreadsheets ("files outside the system").

Calibration (PBI Maintenance Dashboard, snapshot 04/08/2026, schedule week 27/07/2026): 13-week scheduled /
compliant counts and hours exact, scheduled-type mix (PM 575 / GPC 105 / DM 92 / CBM 59 …), overdue safety
critical 25, open P1 4, open P2 excl PM 635, backlog excl PM 5,328.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

import config as C
from common import Lander, date_key, rng, ts

SNAP = date.fromisoformat(C.MX_LATEST_SNAPSHOT)            # Tuesday 2026-08-04
WEEKS13 = [date.fromisoformat(w) for w in C.MX_WEEKS]
HIST_FIRST_WEEK = date(2025, 1, 6)
POP_START = date(2019, 7, 1)
CLOSED = {"CLOSE", "COMP", "CAN", "CLOSED", "SRCAN"}
CRAFT_W = {"MECHTECH": 17, "CONTRACT": 8, "EITECH": 5, "NDTTECH": 5, "ELECTCONT": 4, "COMPCONT": 4, "CTRLTECH": 3,
           "INST": 3, "BMAKER": 3, "FEQINSP": 3, "WELLCONT": 3, "OPERATOR": 3, "CALCONT": 3, "PLUMBER": 2,
           "LOGISTICS": 2, "ELECENG": 2, "PAINTER": 1, "ENGINEER": 1, "FITTER": 1, "GARDNER": 1, "FIRESETN": 1,
           "ELECT": 1, "CARPENTER": 1, "PRODTECH": 1, "CIVILWOR": 1, "REFMECH": 1, "CLADDER": 1, "SCAFFOLD": 1,
           "ADMIN": .5, "CIVILENG": .5, "CHEMIST": .3, "CLEANER": .3, "Unknown": 18}
CONTRACT_CRAFTS = {"CONTRACT", "ELECTCONT", "COMPCONT", "WELLCONT", "CALCONT", "SCAFFOLD", "CLADDER", "PAINTER",
                   "CIVILWOR", "GARDNER", "CLEANER"}
TYPE_W_POP = {"PM": 34, "DM": 21, "CBM": 12, "GPC": 17, "MOD": 10, "MAINT": 1, "HSE": 1.5, "EM": 1, "TRA": .5,
              "ADMIN": .5, "OPS": .5, "Unknown": 1}
PRIO_W = {"P1": 1, "P2": 20, "P3": 36, "P4": 22, "P5": 17, "Unknown": 4}
OPEN_STATUS_W = {"APPR": 30, "WAPPR": 14, "PLANUNDER": 10, "PLANCOMP": 6, "WMATL": 9, "ENGREV": 5, "ACKREC": 6,
                 "RESCHED": 4, "OPEN": 6, "WSCH": 5, "WVENDOR": 5}
DESC = {"PM": "PM – {a} {f} routine", "CBM": "CBM – {a} condition check ({m})", "DM": "Breakdown – {a} {fault}",
        "GPC": "General plant care – {a}", "MOD": "Modification – {a} {mod}", "EM": "Emergency – {a} {fault}",
        "HSE": "HSE corrective action – {a}", "MAINT": "Maintenance support – {a}", "TRA": "Training – {a}",
        "ADMIN": "Admin – {a}", "OPS": "Operations request – {a}", "Unknown": "Work request – {a}"}


def _w(d: dict):
    k = list(d)
    p = np.array(list(d.values()), float)
    return k, p / p.sum()


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def build(L: Lander, refs: dict, seed: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    g = rng(30)
    assets = refs["assets"]
    wo = _population(g, assets)
    wo = _calibrate_latest(g, wo)
    wo["wonum"] = [f"36{d.year % 100:02d}{i:06d}" for i, d in zip(
        wo.groupby(wo.reported_date.map(lambda d: d.year)).cumcount().values + 10000, wo.reported_date)]
    wo["work_order_key"] = wo.wonum + "|S3620"
    wo["description"] = [DESC[t].format(a=a, f=g.choice(["weekly", "monthly", "quarterly", "6-monthly", "annual"]),
                                        m=g.choice(["vibration", "oil analysis", "thermography", "UT thickness"]),
                                        fault=g.choice(["seal leak", "trip on high temp", "loss of signal", "noisy bearing",
                                                        "valve passing", "motor fault"]),
                                        mod=g.choice(["pipework reroute", "instrument upgrade", "guard install", "access platform"]))
                         for t, a in zip(wo.work_type, wo.asset_num)]
    snaps = _snapshots(wo)
    # ---------------------------------------------------------------- land
    detail = wo.copy()
    detail["status"] = _status_at(wo, SNAP)
    for y, grp in detail.groupby(detail.reported_date.map(lambda d: d.year)):
        L.jsonl(f"maximo/workorders/load_date={SNAP + timedelta(days=1)}/workorders_{y}.json", grp)
    for sd, grp in snaps.groupby("snapshot_date_key"):
        s = date(sd // 10000, sd // 100 % 100, sd % 100)
        L.csv(f"maximo/schedule_snapshot/snapshot_date={s}/scheduled_workorders_{sd}.csv", grp)
    _schedule_files(L, wo, g)
    L.csv("maximo/legacy_sample/load_date=2026-07-08/scheduled_workorders_sample_20260707.csv",
          seed["scheduled_workorders"])
    return dict(workorders=detail, snapshots=snaps)


def _population(g, assets) -> pd.DataFrame:
    """Closed history 2019→ plus ordinary scheduled weeks since Jan-25 (the 13 PBI weeks are rebuilt later)."""
    n = 34000
    days = (SNAP - POP_START).days
    t = g.beta(1.6, 1.0, n)                                  # more WOs in recent years
    rep = [POP_START + timedelta(days=int(x * days)) for x in t]
    types, tp = _w(TYPE_W_POP)
    prios, pp = _w(PRIO_W)
    crafts, cp = _w(CRAFT_W)
    df = pd.DataFrame(dict(reported_date=rep, work_type=g.choice(types, n, p=tp), priority_bucket=g.choice(prios, n, p=pp),
                           lead_craft=g.choice(crafts, n, p=cp)))
    df.loc[df.work_type.eq("PM") & df.priority_bucket.isin(["P1"]), "priority_bucket"] = "P3"
    df["wo_class"] = g.choice(["WORKORDER", "ACTIVITY", "ACTTRACK", "MXREQUEST"], n, p=[.78, .19, .02, .01])
    a = assets.sample(n, replace=True, random_state=1).reset_index(drop=True)
    df["asset_num"] = a.asset_num.values
    df["plant_area"] = a.plant_area.values
    df["safety_critical"] = a.safety_critical.values & (g.random(n) < 0.35)
    df["pm_generated"] = df.work_type.eq("PM") | (df.work_type.eq("CBM") & (g.random(n) < 0.3))
    df["est_dur"] = np.round(np.clip(g.lognormal(1.3, 0.8, n), 0.25, 120), 2)
    sla = df.priority_bucket.map({"P1": 1, "P2": 7, "P3": 28, "P4": 60, "P5": 120, "Unknown": 90})
    df["target_finish"] = [r + timedelta(days=int(s)) for r, s in zip(df.reported_date, sla)]
    lag = np.clip(g.gamma(1.4, 14, n), 0, 400).astype(int)
    df["completed_date"] = [r + timedelta(days=int(l)) for r, l in zip(df.reported_date, lag)]
    df["closed_date"] = [c + timedelta(days=int(x)) for c, x in zip(df.completed_date, g.integers(1, 30, n))]
    cancel = g.random(n) < 0.06
    df["cancelled_date"] = [r + timedelta(days=int(x)) if c else None for r, x, c in zip(df.reported_date, g.integers(2, 90, n), cancel)]
    df.loc[cancel, ["completed_date", "closed_date"]] = None
    # anything completing after the snapshot would be open – history population is fully closed by SNAP
    late = df.completed_date.map(lambda d: d is not None and d > SNAP)
    df.loc[late, "completed_date"] = [SNAP - timedelta(days=int(x)) for x in g.integers(1, 20, late.sum())]
    df.loc[late, "closed_date"] = df.loc[late, "completed_date"]
    df["scheduled_week"] = None
    # ordinary schedule weeks Jan-25 .. Apr-26: 50–95 scheduled per week, compliance 72–93 %
    wk = HIST_FIRST_WEEK
    rows = []
    while wk < WEEKS13[0]:
        k = int(g.integers(45, 95))
        pct = float(np.clip(g.normal(0.83, 0.06), 0.68, 0.95))
        rows.append(_sched_week(g, wk, k, pct, float(k * g.uniform(6.5, 9.5)), assets))
        wk += timedelta(days=7)
    df = pd.concat([df] + rows, ignore_index=True)
    return df


def _sched_week(g, wk: date, k: int, pct: float, hours: float, assets, types=None, hours_c: float | None = None):
    tk, tp = _w(C.MX_TYPE_SHARE_SCHEDULED)
    types = types if types is not None else g.choice(tk, k, p=tp)
    crafts, cp = _w(CRAFT_W)
    a = assets.sample(k, replace=True, random_state=int(wk.toordinal() % 9973)).reset_index(drop=True)
    comp_n = int(round(k * pct))
    comp = np.zeros(k, bool)
    comp[g.choice(k, comp_n, replace=False)] = True
    est = np.clip(g.lognormal(1.3, 0.8, k), 0.25, 80)
    hc = hours_c if hours_c is not None else hours * pct * g.uniform(0.85, 1.0)
    est[comp] = est[comp] / est[comp].sum() * hc if comp.any() else est[comp]
    if (~comp).any():
        est[~comp] = est[~comp] / est[~comp].sum() * max(hours - hc, 0.25 * (~comp).sum())
    rep = [wk - timedelta(days=int(x)) for x in g.integers(7, 60, k)]
    prio = g.choice(["P2", "P3", "P4", "P5"], k, p=[.3, .45, .17, .08])
    completed = [wk + timedelta(days=int(g.integers(0, 5))) if c else
                 (wk + timedelta(days=int(g.integers(8, 40))) if g.random() < 0.7 else None) for c in comp]
    df = pd.DataFrame(dict(reported_date=rep, work_type=types, priority_bucket=prio,
                           lead_craft=g.choice(crafts, k, p=cp), wo_class="WORKORDER", asset_num=a.asset_num.values,
                           plant_area=a.plant_area.values, safety_critical=a.safety_critical.values & (g.random(k) < .4),
                           est_dur=np.round(est, 2), scheduled_week=wk, completed_date=completed))
    df["pm_generated"] = df.work_type.eq("PM")
    df["target_finish"] = wk + timedelta(days=6)
    df["closed_date"] = [c + timedelta(days=int(g.integers(1, 20))) if c else None for c in df.completed_date]
    df["cancelled_date"] = None
    return df


def _calibrate_latest(g, df) -> pd.DataFrame:
    """Rebuild the 13 PBI weeks exactly and size the open backlog to the PBI KPIs at the 04/08/2026 snapshot."""
    import gen_reference
    assets = gen_reference.assets(rng(1))
    # exact type allocation of the 857 scheduled WOs across the 13 weeks
    assert sum(C.MX_SCHEDULED_WO) == sum(C.MX_TYPE_COUNTS_13W.values())
    pool = np.repeat(list(C.MX_TYPE_COUNTS_13W), list(C.MX_TYPE_COUNTS_13W.values()))
    g.shuffle(pool)
    weeks, i = [], 0
    for wk, k, pct, h, hc in zip(WEEKS13, C.MX_SCHEDULED_WO, C.MX_COMPLIANCE_PCT, C.MX_SCHED_HOURS, C.MX_COMPLETED_HOURS):
        w = _sched_week(g, wk, k, pct / 100, float(h), assets, types=pool[i:i + k], hours_c=float(hc))
        i += k
        # non-compliant WOs of the last 3 weeks are mostly still open at the snapshot
        if wk >= WEEKS13[-3]:
            nc = w.completed_date.isna() | (w.completed_date.map(lambda d: d is not None and d > SNAP))
            w.loc[nc, ["completed_date", "closed_date"]] = None
        weeks.append(w)
    df = pd.concat([df] + weeks, ignore_index=True)
    # completions/closures after the snapshot don't exist yet
    for col in ["completed_date", "closed_date", "cancelled_date"]:
        df[col] = [d if (d is not None and not pd.isna(d) and d <= SNAP) else None for d in df[col]]
    # ---- open backlog sized to the KPIs
    st = _status_at(df, SNAP)
    is_open = ~st.isin(CLOSED)
    np_open = int((is_open & df.work_type.ne("PM")).sum())
    p2_open = int((is_open & df.work_type.ne("PM") & df.priority_bucket.eq("P2")).sum())
    p1_open = int((is_open & df.priority_bucket.eq("P1")).sum())
    need_np = C.MX_BACKLOG_EXCL_PM - np_open
    need_p2 = C.MX_OPEN_P2_EXCL_PM - p2_open
    need_p1 = C.MX_OPEN_P1 - p1_open
    assert need_np > 0 and need_p2 > 0 and need_p1 >= 0, (np_open, p2_open, p1_open)
    n_pm_open = 780
    n = need_np + n_pm_open
    types_np = [t for t in TYPE_W_POP if t != "PM"]
    tpn = np.array([TYPE_W_POP[t] for t in types_np], float)
    wt = np.concatenate([g.choice(types_np, need_np, p=tpn / tpn.sum()), np.repeat("PM", n_pm_open)])
    prio = np.array(["P3"] * n, dtype=object)
    others = g.choice(["P3", "P4", "P5", "Unknown"], n, p=[.42, .3, .22, .06])
    prio[:] = others
    idx_np = np.arange(need_np)
    prio[idx_np[:need_p1]] = "P1"
    prio[idx_np[need_p1:need_p1 + need_p2]] = "P2"
    age = np.clip(g.gamma(1.2, 220, n), 3, 2400).astype(int)
    rep = [SNAP - timedelta(days=int(x)) for x in age]
    crafts, cp = _w(CRAFT_W)
    a = assets.sample(n, replace=True, random_state=5).reset_index(drop=True)
    bl = pd.DataFrame(dict(reported_date=rep, work_type=wt, priority_bucket=prio, lead_craft=g.choice(crafts, n, p=cp),
                           wo_class=g.choice(["WORKORDER", "ACTIVITY", "MXREQUEST"], n, p=[.8, .18, .02]),
                           asset_num=a.asset_num.values, plant_area=a.plant_area.values, safety_critical=False,
                           est_dur=np.round(np.clip(g.lognormal(1.5, 0.9, n), 0.25, 200), 2), scheduled_week=None,
                           completed_date=None, closed_date=None, cancelled_date=None))
    bl["pm_generated"] = bl.work_type.eq("PM")
    sla = bl.priority_bucket.map({"P1": 1, "P2": 7, "P3": 28, "P4": 60, "P5": 120, "Unknown": 90})
    bl["target_finish"] = [r + timedelta(days=int(s)) for r, s in zip(bl.reported_date, sla)]
    # safety critical: exactly 25 overdue across all open WOs; other SC open WOs are not yet due
    df.loc[is_open & df.safety_critical, "target_finish"] = SNAP + timedelta(days=14)
    sc_idx = g.choice(n, 25 + 60, replace=False)
    bl.loc[sc_idx, "safety_critical"] = True
    bl.loc[sc_idx[:25], "target_finish"] = SNAP - timedelta(days=5)
    bl.loc[sc_idx[25:], "target_finish"] = SNAP + timedelta(days=21)
    bl.loc[sc_idx[:25], "reported_date"] = [min(r, SNAP - timedelta(days=12)) for r in bl.loc[sc_idx[:25], "reported_date"]]
    out = pd.concat([df, bl], ignore_index=True)
    out = out.sort_values("reported_date").reset_index(drop=True)
    return out


def _dt(col: pd.Series) -> np.ndarray:
    return pd.to_datetime(col, errors="coerce").values.astype("datetime64[D]")


def _status_at(df: pd.DataFrame, t: date) -> pd.Series:
    """Status each WO had at snapshot date t (deterministic from its date history)."""
    keys, p = _w(OPEN_STATUS_W)
    h = (pd.util.hash_pandas_object(df.reported_date.astype(str) + df.asset_num, index=False).values % 1000) / 1000
    open_st = np.array(keys)[np.searchsorted(np.cumsum(p), h, side="right").clip(0, len(keys) - 1)]
    T = np.datetime64(t, "D")
    le = lambda c: _dt(df[c]) <= T                          # NaT compares False
    sched = _dt(df.scheduled_week) <= T + np.timedelta64(6, "D")
    st = np.where(le("cancelled_date"), "CAN", np.where(le("closed_date"), "CLOSE",
         np.where(le("completed_date"), "COMP", np.where(sched, "SCHED", open_st))))
    # a small share of closures are recorded with the legacy 'CLOSED' code (DQ: CLOSE vs CLOSED)
    st = np.where((h > 0.985) & (st == "CLOSE"), "CLOSED", st)
    return pd.Series(st, index=df.index)


def _snapshots(wo: pd.DataFrame) -> pd.DataFrame:
    """Weekly Maximo schedule snapshot aggregate (Tuesday), same grain/columns as scheduled_workorders."""
    out = []
    t = date(2025, 1, 7)
    contract_all = wo.lead_craft.isin(CONTRACT_CRAFTS).values
    rep_all, sw_all, comp_all, tf_all = _dt(wo.reported_date), _dt(wo.scheduled_week), _dt(wo.completed_date), _dt(wo.target_finish)
    while t <= SNAP:
        T = np.datetime64(t, "D")
        present = rep_all <= T
        w = wo[present].copy()
        sw, comp, tf, ext = sw_all[present], comp_all[present], tf_all[present], contract_all[present]
        w["status"] = _status_at(w, t).values
        is_open = ~w.status.isin(CLOSED).values
        # only schedule weeks within the last 13 weeks are reported against a week; the rest roll up to 19000101
        sched = (sw <= T) & ((T - sw).astype(int) <= 13 * 7 + 1)   # snapshot is the Tuesday after the week
        wk_key = pd.to_datetime(sw).strftime("%Y%m%d")
        w["schedule_week_date_key"] = np.where(sched, pd.Series(wk_key).fillna("19000101").astype(int).values, 19000101)
        comp_in_week = sched & (comp <= sw + np.timedelta64(6, "D")) & (comp <= T)
        w["workorder_count"] = 1
        w["scheduled_count"] = sched.astype(int)
        w["schedule_compliant_count"] = comp_in_week.astype(int)
        w["schedule_non_compliant_count"] = (sched & ~comp_in_week).astype(int)
        w["est_dur_scheduled"] = np.where(sched, w.est_dur, np.nan)
        w["est_dur_compliant"] = np.where(comp_in_week, w.est_dur, np.nan)
        w["safety_critical_count"] = w.safety_critical.astype(int)
        overdue = is_open & w.safety_critical.values.astype(bool) & (tf < T)
        w["overdue_safety_critical_count"] = overdue.astype(int)
        w["backlog_count"] = is_open.astype(int)
        w["backlog_est_dur"] = np.where(is_open, w.est_dur, np.nan)
        w["backlog_est_int_lab_hrs"] = np.where(is_open & ~ext, w.est_dur, np.where(is_open, 0.0, np.nan))
        w["backlog_est_ext_lab_hrs"] = np.where(is_open & ext, w.est_dur, np.where(is_open, 0.0, np.nan))
        act = np.where(is_open, np.round(w.est_dur * 0.15, 2), np.nan)
        w["backlog_act_lab_hrs"] = act
        w["backlog_act_int_lab_hrs"] = np.where(is_open & ~ext, act, np.where(is_open, 0.0, np.nan))
        w["backlog_act_ext_lab_hrs"] = np.where(is_open & ext, act, np.where(is_open, 0.0, np.nan))
        w["pm_generated_count"] = w.pm_generated.astype(int)
        w["independently_raised_wo_count"] = (~w.pm_generated.astype(bool)).astype(int)
        keys = ["schedule_week_date_key", "priority_bucket", "work_type", "wo_class", "status", "lead_craft"]
        agg = w.groupby(keys, dropna=False).agg({c: "sum" for c in [
            "workorder_count", "scheduled_count", "schedule_compliant_count", "schedule_non_compliant_count",
            "safety_critical_count", "overdue_safety_critical_count", "backlog_count", "pm_generated_count",
            "independently_raised_wo_count"]} | {c: lambda s: s.sum(min_count=1) for c in [
            "est_dur_scheduled", "est_dur_compliant", "backlog_est_dur", "backlog_est_int_lab_hrs",
            "backlog_est_ext_lab_hrs", "backlog_act_lab_hrs", "backlog_act_int_lab_hrs", "backlog_act_ext_lab_hrs"]}).reset_index()
        agg.insert(0, "snapshot_date_key", date_key(t))
        out.append(agg)
        t += timedelta(days=7)
    snaps = pd.concat(out, ignore_index=True)
    cols = ["snapshot_date_key", "schedule_week_date_key", "priority_bucket", "work_type", "wo_class", "status",
            "lead_craft", "workorder_count", "scheduled_count", "schedule_compliant_count",
            "schedule_non_compliant_count", "est_dur_scheduled", "est_dur_compliant", "safety_critical_count",
            "overdue_safety_critical_count", "backlog_count", "backlog_est_dur", "backlog_est_int_lab_hrs",
            "backlog_est_ext_lab_hrs", "backlog_act_lab_hrs", "backlog_act_int_lab_hrs", "backlog_act_ext_lab_hrs",
            "pm_generated_count", "independently_raised_wo_count"]
    snaps = snaps[cols]
    for c in cols[11:]:
        if snaps[c].dtype.kind == "f":
            snaps[c] = snaps[c].round(2)
    return snaps.fillna({c: "null" for c in ["est_dur_scheduled", "est_dur_compliant", "backlog_est_dur",
                                             "backlog_est_int_lab_hrs", "backlog_est_ext_lab_hrs", "backlog_act_lab_hrs",
                                             "backlog_act_int_lab_hrs", "backlog_act_ext_lab_hrs"]})


def _schedule_files(L: Lander, wo: pd.DataFrame, g):
    """Planner spreadsheets: one xlsx per schedule week with the planned hours per WO."""
    sched = wo[wo.scheduled_week.map(lambda d: d is not None and not pd.isna(d))]
    planners = ["Iona Planner – Mechanical", "Iona Planner – E&I", "Iona Planner – Contracts"]
    for wk, grp in sched.groupby("scheduled_week"):
        f = pd.DataFrame(dict(schedule_week=str(wk), wonum=grp.wonum.values, lead_craft=grp.lead_craft.values,
                              planned_hours=grp.est_dur.values, planner=g.choice(planners, len(grp)),
                              exported_at=ts(wk - timedelta(days=3))))
        L.xlsx(f"maximo/schedule_files/week={wk}/iona_schedule_{wk:%Y%m%d}.xlsx", f, sheet="Schedule")
