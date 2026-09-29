"""Finance source systems: Business Central G/L entries, SITEBUD budgets, YEO reforecasts and Maximo PO lines.

Calibration (FY2027, see config.TEAMS): team budgets / YEO exact to the K$, YTD (Jul–Aug-26) actuals exact
to the K$, committed (open PO) exact to the K$, HUGS PRM-0021E drill-through lines as in the PBI screenshot.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import pandas as pd

import config as C
from common import Lander, date_key, fy_months, month_end, rng, split_amount, ts, weighted_choice

SITE = "S3620"
MATERIAL_ACCOUNTS = {623000, 623510, 626900}
CONTRACT_ACCOUNTS = {625250}
MAXIMO_ACCOUNTS = MATERIAL_ACCOUNTS | CONTRACT_ACCOUNTS
AVG_LINE = {  # typical GL line size by team ($) – drives line counts
    "Employee Costs": 60000, "Major Projects": 45000, "Finance, Risk and Digital": 6000, "Asset Management": 2500,
    "SIB Projects": 9000, "Operations": 2200, "Maintenance": 1100, "Growth": 12000, "Opex Projects": 9000,
    "Reservoir Management": 6000, "People, Safety and Sustainability": 3500, "Legal": 7000, "Commercial": 3000,
    "HSE": 1600,
}
# FY-month phasing (Jul..Jun). June accrual spike, July reversal, Dec/Jan shutdown dip.
PHASE = {
    "Opex": [0.75, 1, 1, 1.02, 1.05, 0.9, 0.8, 1, 1.05, 1, 1, 1.43],
    "Capex": [0.45, 0.55, 0.7, 0.8, 0.9, 0.85, 0.8, 1.05, 1.2, 1.3, 1.45, 1.95],
    "SIB": [0.4, 0.6, 0.8, 1.0, 1.25, 1.2, 0.9, 1.05, 1.1, 1.1, 1.2, 1.4],
    "Employee": [1, 1, 1, 1, 1, 1.5, 1, 1, 1, 1, 1, 0.5],   # 3-pay month in Dec, accrual true-up in Jun
}
MATERIAL_TEMPLATES = [
    "GASKET,SPIRAL WOUND, {s} MM, CLASS {c}, I/RING SS", "VALVE, BALL, {i}\" CL{c}, A105, FULL BORE",
    "FILTER ELEMENT, COALESCER, P/N {p}", "BEARING, ROLLER, TAPERED, P/N {p}", "SEAL KIT, COMPRESSOR ROD PACKING, {p}",
    "O-RING, VITON, {s}MM ID, BOX 50", "BOLT, STUD, B7, {i}\" X {s}MM, HDG", "GLOVES,SAFETY, NITRILE, SIZE {i}",
    "CABLE GLAND, EX, {s}MM, SWA", "LAMP, LED, EX-RATED, 40W", "TRANSMITTER, PRESSURE, 0-{c} KPA, HART",
    "OIL, COMPRESSOR, SYNTHETIC, 205L DRUM", "GLYCOL, TEG, 1000L IBC", "PAPER, TOWEL ROLL, CTN 16",
]
CONTRACT_TEMPLATES = [
    "Scaffold for {a} {t}", "Replace corroded {x} at {a}", "{t} of {a} – call-out", "NDT inspection {a} pressure vessel",
    "Insulation and cladding repair {a}", "Electrical testing & tagging – {a}", "Compressor overhaul support {a}",
    "Wellhead maintenance {a}", "Civil works – access track {x}", "Waste removal and disposal", "Fire system service {a}",
]
PROF_TEMPLATES = {
    635900: ["Consulting – {t}", "Engineering study – {t}", "Advisory services – {t}", "Independent review – {t}"],
    636100: ["Legal Fees - {t}", "Legal advice – {t}"],
    650200: ["Software subscription – {t}", "IT managed services – {t}", "Cyber security services – {t}"],
    651050: ["Insurance premium instalment – {t}"],
    655000: ["Travel & accommodation – {t}", "Flights MEL-Port Campbell – {t}"],
    660100: ["Fuel gas & electricity – Iona site", "Electricity charges – Primmer house"],
    670000: ["Lease payments – {t}"],
    649900: ["Plant hire – {t}", "Crane hire – {t}"],
    615800: ["Training – {t}", "Competency assessment – {t}"],
    626900: ["PPE issue – {t}", "Consumables – {t}"],
    161150: ["Progress claim – {t}", "Construction services – {t}", "Equipment supply – {t}"],
    161160: ["Well services – {t}", "Drilling services – {t}"],
    161170: ["Pipeline construction – {t}", "Pipeline engineering – {t}"],
}
TOPICS = ["gas storage tariff review", "AEMO market rule change", "HUGS gathering line", "Queen FEL2 turbines",
          "SWP expansion", "reservoir modelling", "AESCSF uplift", "Project Flowbridge", "MSP transition",
          "HSE incident management system", "process safety review", "domestic gas reservation", "insurance renewal",
          "payroll system", "board papers", "Iona site", "Melbourne office", "trust determinations", "Gas inquiry",
          "contract re-negotiation", "customer nominations", "compressor K104", "wellhead integrity", "FEL2 gate"]
ASSETS = ["Iona 7 wellhead", "E-403 fan", "V-324", "compressor K102", "compressor K104", "dehydration unit",
          "LIT-1707 slug catcher", "Seamer-2 wellpad", "North Paaratte-4", "metering skid", "comp building",
          "Primmer house", "control room", "fuel gas heater"]


class Counter:
    def __init__(self, start: int):
        self.n = start

    def take(self, k: int) -> np.ndarray:
        out = np.arange(self.n, self.n + k)
        self.n += k
        return out


def _fy_team_targets(fy: int, g) -> dict[str, dict[str, float]]:
    """Full-year budget/actual/yeo/committed ($) per team for a fiscal year."""
    out = {}
    for team, (_, bud, act, yeo, com) in C.TEAMS.items():
        if fy == C.FY_CURRENT:
            out[team] = dict(budget=bud * 1e3, actual=act * 1e3, yeo=yeo * 1e3, committed=com * 1e3)
            continue
        growth = 0.955 ** (C.FY_CURRENT - fy)
        b = bud * 1e3 * growth * g.uniform(0.95, 1.05)
        a = b * (g.uniform(0.97, 1.01) if team == "Employee Costs" else g.uniform(0.86, 1.05))
        out[team] = dict(budget=b, actual=a, yeo=a * g.uniform(0.99, 1.01), committed=0.0)
    if fy < C.FY_CURRENT:  # Major Projects history is dominated by HUGS from FY24
        hugs = {2024: 14.2e6, 2025: 41.3e6, 2026: 46.0e6}.get(fy, 0)
        mp = out["Major Projects"]
        mp["actual"] = max(mp["actual"] * 0.35, 4e6) + hugs
        mp["budget"] = mp["actual"] * g.uniform(0.95, 1.08)
    return out


def _cc_weights(cc: pd.DataFrame, team: str, fy: int) -> dict[str, float]:
    sub = cc[cc.team == team]
    if team == "Major Projects":
        split = {2022: {"Project 570": .6, "PM and FGH": .4}, 2023: {"Project 570": .3, "PM and FGH": .3, "CAP": .4},
                 2024: {"HUGS": .75, "CAP": .1, "Project Aegis": .15}, 2025: {"HUGS": .9, "Project Aegis": .07, "CAP": .03},
                 2026: {"HUGS": .88, "Project Aegis": .1, "PM and FGH": .02}}.get(fy, {"HUGS": .6, "Project Aegis": .38, "CAP": .02})
        w = {}
        for short, share in split.items():
            keys = sub[sub.cc_short_name == short].cost_centre_key.tolist()
            if short == "HUGS":
                keys = ["PRM-0021C"] if fy == 2024 else ["PRM-0021E"]
            for k in keys:
                w[k] = share / len(keys)
        return w
    keys = sub.cost_centre_key.tolist()
    base = np.linspace(1.6, 0.6, len(keys))  # skewed – first CCs carry most spend
    return dict(zip(keys, base / base.sum()))


def _describe(acc: int, g, vocab: dict[int, list[str]], people_names: list[str]) -> str:
    if acc in MATERIAL_ACCOUNTS and g.random() < 0.55 and vocab.get(623000):
        return str(g.choice(vocab[623000]))
    if acc in MATERIAL_ACCOUNTS:
        t = str(g.choice(MATERIAL_TEMPLATES))
        return t.format(s=int(g.choice([10, 20, 25, 50, 80, 150, 350])), c=int(g.choice([150, 300, 600, 900])),
                        i=int(g.choice([1, 2, 3, 4, 6, 8, 10])), p=f"{g.integers(1000, 99999)}-{g.integers(10, 99)}")[:50]
    if acc in CONTRACT_ACCOUNTS:
        if g.random() < 0.3 and vocab.get(625250):
            return str(g.choice(vocab[625250]))
        return str(g.choice(CONTRACT_TEMPLATES)).format(a=g.choice(ASSETS), t=g.choice(["service", "repair", "inspection",
                                                        "replacement", "shutdown works"]), x=g.choice(["roof sections",
                                                        "handrail", "pipe supports", "grating", "fence"]))
    if acc in (610100, 610200, 610300, 610400):
        return {610100: "Payroll journal – salaries & wages", 610200: "Payroll journal – superannuation",
                610300: "Payroll tax – monthly return", 610400: "Leave provision movement"}[acc]
    t = PROF_TEMPLATES.get(acc, ["{t}"])
    d = str(g.choice(t)).format(t=g.choice(TOPICS))
    if acc == 655000 and g.random() < 0.25:  # free-text with a person name (PII) – masked by ABAC
        d = f"{d} – {g.choice(people_names)}"
    return d


def _post_dates(month: date, n: int, g, last_day: date | None = None) -> list[date]:
    end = min(month_end(month), last_day) if last_day else month_end(month)
    days = pd.bdate_range(month, end)
    if len(days) == 0:
        days = pd.date_range(month, end)
    p = np.ones(len(days))
    p[-2:] *= 6  # month-end spike
    idx = g.choice(len(days), size=n, p=p / p.sum())
    return [days[i].date() for i in idx]


def build(L: Lander, refs: dict, seed: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    g = rng(10)
    cc = refs["cost_centres"]
    vendors = refs["vendors"]
    vend_by_cat = vendors.groupby("vendor_category").source_key.apply(list).to_dict()
    people_names = refs["people"].display_name.tolist()
    vocab = {}
    sa = seed["fact_actuals"]
    for acc, grp in sa.groupby("account_key"):
        vocab[int(acc)] = sorted(set(grp["description"].astype(str)))
    entry = Counter(300000)  # sample golden rows occupy 298398..299313
    doc = {"MXO": Counter(50000), "PPI": Counter(6000), "GJ": Counter(10000), "EXP": Counter(3000)}
    po_seq, wo_seq = defaultdict(lambda: 19000), defaultdict(lambda: 9000)
    gl_rows, bud_rows, yeo_rows = [], [], []
    targets_by_fy = {}

    for fy in range(C.FY_FIRST_HISTORY, C.FY_CURRENT + 1):
        T = _fy_team_targets(fy, g)
        targets_by_fy[fy] = T
        months = fy_months(fy)
        yy = (fy - 1) % 100
        for team, t in T.items():
            ccw = _cc_weights(cc, team, fy)
            accw = C.TEAM_ACCOUNTS[team]
            ctype = "Employee" if team == "Employee Costs" else cc[cc.team == team].cost_type.iloc[0]
            phase = np.array(PHASE[ctype if ctype in PHASE else "Opex"], dtype=float)
            phase = phase / phase.sum()
            # ------------------------------------------------ budget (SITEBUDyy)
            for m_i, m in enumerate(months):
                for k, wk in ccw.items():
                    for acc, wa in accw.items():
                        bud_rows.append((fy, date_key(m), k, acc, t["budget"] * phase[m_i] * wk * wa))
            # ------------------------------------------------ actual targets per month
            if fy == C.FY_CURRENT:
                ytd = t["actual"]
                if team == "Major Projects":
                    month_t = {7: 0.0, 8: 0.0}  # HUGS handled explicitly; remainder below
                else:
                    jul = 0.978 * ytd if ytd > 0 else abs(ytd) * 0.3
                    month_t = {7: jul, 8: ytd - jul}
                act_months = [(m, month_t[m.month]) for m in months if m.month in (7, 8)]
            else:
                act_months = [(m, t["actual"] * phase[i]) for i, m in enumerate(months)]
            hugs_fy = {2024: 14.2e6, 2025: 41.3e6, 2026: 46.0e6}.get(fy, 0) if team == "Major Projects" else 0
            if hugs_fy:  # HUGS spend is pinned per FY (EAC ≈ actuals + FY27 YEO ≈ $115M vs revised P50 $112.4M)
                hugs_cc = {"PRM-0021C": 1.0} if fy == 2024 else {"PRM-0021E": 1.0}
                other_cc = {k: v for k, v in ccw.items() if k not in ("PRM-0021C", "PRM-0021E")} or {"PRM-0017": 1.0}
                tot = sum(v for _, v in act_months) or 1.0
                for m, amt in act_months:
                    gl_rows.extend(_lines_for(team, fy, m, hugs_fy * amt / tot, hugs_cc, accw, g, vend_by_cat, vocab,
                                              people_names, yy, po_seq, wo_seq))
                    gl_rows.extend(_lines_for(team, fy, m, amt * (1 - hugs_fy / tot), other_cc, accw, g, vend_by_cat,
                                              vocab, people_names, yy, po_seq, wo_seq))
            else:
                for m, amt in act_months:
                    gl_rows.extend(_lines_for(team, fy, m, amt, ccw, accw, g, vend_by_cat, vocab, people_names, yy,
                                              po_seq, wo_seq))
            # ------------------------------------------------ YEO versions
            versions = ["M01", "M02"] if fy == C.FY_CURRENT else ["M03", "M06", "M09", "M12"]
            for v in versions:
                if fy == C.FY_CURRENT:
                    total = t["yeo"] * (1.0 if v == "M02" else g.uniform(0.97, 1.04))
                    ph = np.array([C.FY27_YEO_PHASING.get(i + 1, 0.0) for i in range(12)])
                else:
                    drift = {"M03": g.uniform(0.9, 1.08), "M06": g.uniform(0.95, 1.05), "M09": g.uniform(0.98, 1.02),
                             "M12": 1.0}[v]
                    total = t["actual"] * drift
                    ph = phase
                yeo_ccw = ccw
                if fy == C.FY_CURRENT and team == "Major Projects":
                    yeo_ccw = {"PRM-0021E": 13740 / 20808, "PRM-0017": 6243 / 20808, "PRM-0030": 825 / 20808}
                for m_i, m in enumerate(months):
                    if ph[m_i] == 0:
                        continue
                    for k, wk in yeo_ccw.items():
                        for acc, wa in accw.items():
                            yeo_rows.append((fy, f"FY{fy % 100:02d}_YEO_{v}", date_key(m), k, acc, total * ph[m_i] * wk * wa))
    # FY27 budget for Major Projects follows the PBI CC split exactly (HUGS 26,560K / Aegis 17,100K / CAP 905K)
    bud = pd.DataFrame(bud_rows, columns=["fy", "date_key", "cost_centre_key", "account_key", "amount"])
    mp27 = bud.fy.eq(C.FY_CURRENT) & bud.cost_centre_key.isin(_cc_weights(cc, "Major Projects", C.FY_CURRENT))
    bud = bud[~mp27]
    mp_rows = []
    for k, amt, acc in [("PRM-0021E", 26_560_000, 161150), ("PRM-0017", 17_100_000, 161150), ("PRM-0030", 905_000, 161150)]:
        ph = np.array(PHASE["Capex"]) / sum(PHASE["Capex"])
        for i, m in enumerate(fy_months(C.FY_CURRENT)):
            mp_rows.append((C.FY_CURRENT, date_key(m), k, acc, amt * ph[i]))
    bud = pd.concat([bud, pd.DataFrame(mp_rows, columns=bud.columns)], ignore_index=True)
    bud["amount"] = bud.amount.round(2)
    bud = _reconcile(bud, "amount", {tm: v["budget"] for tm, v in targets_by_fy[C.FY_CURRENT].items()}, cc,
                     bud.fy.eq(C.FY_CURRENT))

    gl = pd.DataFrame(gl_rows)
    gl = pd.concat([gl, _hugs_fy27(g, po_seq, wo_seq), _major_projects_fy27_other(g)], ignore_index=True)
    gl = _reconcile(gl, "amount", {tm: v["actual"] for tm, v in targets_by_fy[C.FY_CURRENT].items()}, cc,
                    gl.posting_date.ge(date(2026, 7, 1)) & ~gl.cost_centre_key.eq(C.HUGS_CC))
    gl = _add_reversal_pairs(gl, g)
    gl = gl.sort_values(["posting_date", "cost_centre_key"]).reset_index(drop=True)
    gl["entry_no"] = entry.take(len(gl))
    gl["document_no"] = [f"{p}{doc[p].take(1)[0]:06d}" for p in gl.doc_prefix]
    gl = _finalise_gl(gl, seed["fact_actuals"], g)

    po = _po_lines(gl, targets_by_fy[C.FY_CURRENT], cc, vend_by_cat, g, po_seq)
    gl = _classify_spend(gl, po)
    line_cost = po.assign(k=po.po_number.astype(float)).set_index("k").line_cost
    gen = ~gl["_seed"].astype(bool)
    gl.loc[gen, "po_line_cost"] = gl.loc[gen, "maximo_po_no"].map(line_cost)
    gl.loc[gen & gl.po_line_cost.isna(), "po_line_cost"] = "null"   # source emits literal 'null'

    # ------------------------------------------------------------------ write
    for (y, m), grp in gl.groupby([gl.posting_date.map(lambda d: d.year), gl.posting_date.map(lambda d: d.month)]):
        if date(y, m, 1) >= date(2026, 7, 1):   # current FY lands as daily interface files
            for d, dgrp in grp.groupby("posting_date"):
                L.csv(f"erp/gl_entries/load_date={d + timedelta(days=1)}/gl_entries_{d:%Y%m%d}.csv", dgrp[GL_COLS])
        else:
            L.csv(f"erp/gl_entries/load_date={month_end(date(y, m, 1)) + timedelta(days=3)}/gl_entries_{y}{m:02d}.csv",
                  grp[GL_COLS])
    budget = _budget_extract(bud, seed["fact_budget"])
    for bname, grp in budget.groupby("budget_name"):
        L.csv(f"erp/budget/load_date={grp.load_date.iloc[0]}/budget_{bname}.csv", grp.drop(columns=["load_date"]))
    yeo = pd.DataFrame(yeo_rows, columns=["fy", "yeo_version", "date_key", "cost_centre_key", "account_key", "amount"])
    yeo = _reconcile(yeo, "amount", {tm: v["yeo"] for tm, v in targets_by_fy[C.FY_CURRENT].items()}, cc,
                     yeo.yeo_version.eq("FY27_YEO_M02"))
    yeo["amount"] = yeo.amount.round(2)
    yeo["yeo_entry_key"] = np.arange(1, len(yeo) + 1)
    for v, grp in yeo.groupby("yeo_version"):
        fy = int(grp.fy.iloc[0]); mnum = int(v[-2:])
        load = fy_months(fy)[mnum - 1]
        load = month_end(load) + timedelta(days=12)
        grp = grp.assign(yeo_type="YEO", updated_at=ts(load), is_latest=False)
        L.csv(f"erp/yeo/load_date={load}/yeo_{v}.csv", grp)
    for (y, m), grp in po.groupby([po.order_date.map(lambda d: d.year), po.order_date.map(lambda d: d.month)]):
        L.csv(f"maximo/purchase_orders/load_date={month_end(date(y, m, 1)) + timedelta(days=1)}/po_lines_{y}{m:02d}.csv", grp)
    return dict(gl=gl, budget=budget, yeo=yeo, po=po)


GL_COLS = ["gl_entry_key", "date_key", "cost_centre_key", "account_key", "source_key", "purchase_order_key",
           "work_order_key", "entry_no", "company_name", "document_no", "external_document_no", "description",
           "maximo_po_no", "maximo_wo_no", "po_line_cost", "amount", "gst_amount", "reversed", "reversed_by_entry_no",
           "updated_at"]


def _lines_for(team, fy, month, amount, ccw, accw, g, vend_by_cat, vocab, people_names, yy, po_seq, wo_seq):
    if abs(amount) < 1:
        return []
    last_day = C.FY27_YTD_END if fy == C.FY_CURRENT else None
    rows = []
    if amount < 0:  # net-negative month: some normal spend plus a large accrual reversal / credit
        pos = abs(amount) * g.uniform(0.2, 0.5)
        rows += _lines_for(team, fy, month, pos, ccw, accw, g, vend_by_cat, vocab, people_names, yy, po_seq, wo_seq)
        k = max(ccw, key=ccw.get)
        acc = max(accw, key=accw.get)
        rows.append(dict(team=team, cost_centre_key=k, account_key=acc, posting_date=date(month.year, month.month, 1),
                         amount=round(amount - pos, 2), doc_prefix="GJ", source_key=None, po=None, wo=None,
                         description=f"Reverse FY{fy - 1 - 2000:02d} year-end accrual – {team}", gst=0.0,
                         ext=f"JNL-{month:%Y%m}-ACCR"))
        return rows
    n = int(np.clip(amount / AVG_LINE[team] * g.uniform(0.8, 1.2), 3, 2500))
    amts = split_amount(amount, n, g, sigma=1.1)
    ks = weighted_choice(g, ccw, n)
    accs = weighted_choice(g, accw, n)
    dates = _post_dates(month, n, g, last_day)
    for i in range(n):
        acc = int(accs[i])
        if team == "Employee Costs":
            prefix, src, po, wo = "GJ", None, None, None
            ext = f"PAY-{dates[i]:%Y%m%d}"
        elif acc in MAXIMO_ACCOUNTS:
            prefix = "MXO"
            cat = "Materials" if acc in MATERIAL_ACCOUNTS else "Contractors"
            src = str(g.choice(vend_by_cat[cat]))
            if g.random() < 0.18:  # WO-only issue from store (no PO)
                po = None
            else:
                po_seq[yy] += int(g.integers(0, 3))
                po = f"{yy:02d}36{po_seq[yy]:05d}"
            wo_seq[yy] += int(g.integers(0, 2))
            wo = f"36{yy:02d}{wo_seq[yy]:06d}"
            ext = f"PO {po}" if po else f"WO {wo}"
        elif acc == 655000 and g.random() < 0.4:
            prefix, src, po, wo = "EXP", str(g.choice(vend_by_cat["Employee"])), None, None
            ext = f"{g.integers(80000, 89999)}"
        else:
            prefix, po, wo = "PPI", None, None
            cats = {636100: "Legal", 650200: "IT", 651050: "Insurance", 655000: "Travel", 649900: "Plant Hire",
                    615800: "Training"}.get(acc, "Engineering" if acc in (161150, 161160, 161170, 635900) else "Consulting")
            src = str(g.choice(vend_by_cat.get(cats, vend_by_cat["Consulting"])))
            ext = f"{g.integers(100000, 10999999)}"
        gst = round(float(amts[i]) * 0.1, 2) if prefix == "PPI" else 0.0
        rows.append(dict(team=team, cost_centre_key=ks[i], account_key=acc, posting_date=dates[i], amount=float(amts[i]),
                         doc_prefix=prefix, source_key=src, po=po, wo=wo,
                         description=_describe(acc, g, vocab, people_names), gst=gst, ext=ext))
    return rows


def _hugs_fy27(g, po_seq, wo_seq) -> pd.DataFrame:
    """PRM-0021E lines exactly as the PBI 'Actuals – Transaction Details' drill-through, plus balancing lines."""
    wo = "3624011199"
    shown = [
        (date(2026, 7, 2), None, "Credit Refresh Pure Water - Returned IBC,s", -3360.00, "PPI"),
        (date(2026, 7, 17), None, "Groceries / Meals", 487.01, "EXP"),
        (date(2026, 7, 17), None, "Uber / Parking / Carwash", 143.43, "EXP"),
        (date(2026, 7, 31), None, "Hive Legal Advice on approval pathway for HUGS gathering line modifications", 23000.00, "PPI"),
        (date(2026, 7, 31), None, "Travel Card recharges PRM-0021E Jul26", 3870.90, "GJ"),
        (date(2026, 8, 1), None, "Hive Legal Advice on approval pathway for HUGS gathering line modifications", -23000.00, "GJ"),
        (date(2026, 7, 31), "243611118", "ATA-02 - Provide Project Delivery Services", 93882.87, "MXO"),
        (date(2026, 7, 31), "253611792", "ATA-02 - Engagement of Sam Ferreira (Completions/Commissioning Support)", 54387.91, "MXO"),
        (date(2026, 7, 1), "263610190", "ATA-01 Provision of Pipeline Engineering and Consu", -28700.00, "MXO"),
        (date(2026, 7, 6), "263610190", "ATA-01 Provision of Pipeline Engineering and Consultancy Services for HUGS.", 28700.00, "MXO"),
        (date(2026, 7, 31), "263610190", "ATA-01 Provision of Pipeline Engineering and Consultancy Services for HUGS.", 29110.00, "MXO"),
        (date(2026, 8, 1), "263610190", "ATA-01 Provision of Pipeline Engineering and Consultancy Services for HUGS.", -29110.00, "MXO"),
        (date(2026, 8, 5), "263610190", "ATA-01 Provision of Pipeline Engineering and Consultancy Services for HUGS.", 29110.00, "MXO"),
        (date(2026, 7, 31), "263610714", "Project Regulatory Support – 33k Groundwater Monitoring", 16720.00, "MXO"),
    ]
    rows = []
    for d, po, desc, amt, pre in shown:
        rows.append(dict(team="Major Projects", cost_centre_key=C.HUGS_CC, account_key=161150, posting_date=d, amount=amt,
                         doc_prefix=pre, source_key="V_101600" if pre != "EXP" else "V_999013100", po=po,
                         wo=wo if po else None, description=desc, gst=round(amt * .1, 2) if pre == "PPI" else 0.0,
                         ext=f"PO {po}" if po else ("JNL-202608-HUGS" if pre == "GJ" else f"{g.integers(80000, 99999)}")))
    # balancing: construction progress claims in Jul, Stage 1 capitalisation transfer in Aug
    for mth, target in C.HUGS_YTD.items():
        cur = sum(r["amount"] for r in rows if r["posting_date"].month == mth)
        gap = round(target - cur, 2)
        if mth == 7:
            parts = split_amount(gap, 9, g, 0.6)
            for p in parts:
                rows.append(dict(team="Major Projects", cost_centre_key=C.HUGS_CC, account_key=161150,
                                 posting_date=_post_dates(date(2026, 7, 1), 1, g)[0], amount=float(p), doc_prefix="MXO",
                                 source_key="V_101896", po=f"2436{g.integers(11000, 11999)}", wo=wo,
                                 description=str(g.choice(["HUGS progress claim – wellsite civil works",
                                                           "HUGS progress claim – 300mm gathering line",
                                                           "HUGS mechanical completion services",
                                                           "HUGS electrical & instrumentation installation"])),
                                 gst=0.0, ext="PO HUGS"))
        else:
            claim = 520_000.00
            rows.append(dict(team="Major Projects", cost_centre_key=C.HUGS_CC, account_key=161150,
                             posting_date=date(2026, 8, 20), amount=claim, doc_prefix="MXO", source_key="V_101896",
                             po="243611502", wo=wo, description="HUGS progress claim – wellsite civil works", gst=0.0,
                             ext="PO 243611502"))
            rows.append(dict(team="Major Projects", cost_centre_key=C.HUGS_CC, account_key=161150,
                             posting_date=date(2026, 8, 31), amount=round(gap - claim, 2), doc_prefix="GJ",
                             source_key=None, po=None, wo=None,
                             description="Capitalisation transfer – HUGS Stage 1 assets to PP&E (AUC clearing)",
                             gst=0.0, ext="JNL-202608-CAPX"))
    return pd.DataFrame(rows)


def _major_projects_fy27_other(g) -> pd.DataFrame:
    """Project Aegis YTD +112K (Jul/Aug); CAP 0K."""
    rows = []
    for mth, amt in [(7, 64_310.00), (8, 47_690.00)]:
        for p in split_amount(amt, 6, g, 0.7):
            rows.append(dict(team="Major Projects", cost_centre_key="PRM-0017", account_key=161150,
                             posting_date=_post_dates(date(2026, mth, 1), 1, g)[0], amount=float(p), doc_prefix="PPI",
                             source_key="V_101896", po=None, wo=None,
                             description="Project Aegis – compressor upgrade engineering", gst=round(float(p) * .1, 2),
                             ext=f"{g.integers(100000, 999999)}"))
    return pd.DataFrame(rows)


def _reconcile(df, col, team_totals, cc, mask):
    """Scale rows under `mask` so each team's total equals its target exactly (largest row absorbs rounding)."""
    team_of = cc.set_index("cost_centre_key").team
    df = df.copy()
    teams = df.cost_centre_key.map(team_of)
    for team, target in team_totals.items():
        m = mask & teams.eq(team)
        if not m.any():
            continue
        if team == "Major Projects" and col == "amount" and "posting_date" in df.columns:
            continue  # set explicitly (HUGS + Aegis)
        cur = df.loc[m, col].sum()
        if abs(cur) > 1e-6:
            pos = m & (df[col] > 0) if target * cur > 0 else m
            df.loc[pos, col] = (df.loc[pos, col] * (1 + (target - cur) / df.loc[pos, col].sum())).round(2)
        resid = round(target - df.loc[m, col].sum(), 2)
        idx = df.loc[m, col].abs().idxmax()
        df.loc[idx, col] = round(df.loc[idx, col] + resid, 2)
    return df


def _add_reversal_pairs(gl, g) -> pd.DataFrame:
    """~2.5% of postings were first keyed in error and reversed (same month) before the correct line posted.
    The erroneous line and its reversal net to zero, so calibrated totals are unchanged."""
    cand = gl[(gl.doc_prefix != "GJ") & (gl.amount > 50)].sample(frac=0.025, random_state=7)
    err = cand.copy()
    err["posting_date"] = [max(month_start, d - timedelta(days=int(g.integers(1, 4))))
                           for d, month_start in zip(err.posting_date, err.posting_date.map(lambda d: d.replace(day=1)))]
    rev = err.copy()
    rev["amount"] = -rev["amount"]
    rev["gst"] = -rev["gst"]
    rev["posting_date"] = [min(d + timedelta(days=int(g.integers(0, 3))), month_end(d)) for d in rev.posting_date]
    err = err.assign(_pair=np.arange(len(err)), _is_rev=False)
    rev = rev.assign(_pair=np.arange(len(rev)), _is_rev=True)
    return pd.concat([gl, err, rev], ignore_index=True)


def _finalise_gl(gl, seed_actuals, g) -> pd.DataFrame:
    gl = gl.copy()
    gl["company_name"] = C.COMPANY
    gl["gl_entry_key"] = gl.entry_no.astype(str) + "|" + C.COMPANY
    gl["date_key"] = gl.posting_date.map(date_key)
    gl["purchase_order_key"] = [f"{p}|{SITE}" if p else "null" for p in gl.po]
    gl["work_order_key"] = [f"{w}|{SITE}" if w else "null" for w in gl.wo]
    gl["maximo_po_no"] = [float(p) if p else None for p in gl.po]
    gl["maximo_wo_no"] = [float(w) if w else None for w in gl.wo]
    gl["external_document_no"] = gl.ext
    gl["gst_amount"] = gl.gst.round(2)
    gl["amount"] = gl.amount.round(2)
    # reversal pairing
    gl["reversed"] = False
    gl["reversed_by_entry_no"] = 0
    if "_pair" in gl.columns:
        pairs = gl.dropna(subset=["_pair"])
        o = pairs[~pairs._is_rev.astype(bool)].set_index("_pair").entry_no
        r = pairs[pairs._is_rev.astype(bool)].set_index("_pair").entry_no
        gl.loc[pairs.index, "reversed"] = True
        gl.loc[pairs[~pairs._is_rev.astype(bool)].index, "reversed_by_entry_no"] = pairs[~pairs._is_rev.astype(bool)]._pair.map(r).values
        gl.loc[pairs[pairs._is_rev.astype(bool)].index, "reversed_by_entry_no"] = pairs[pairs._is_rev.astype(bool)]._pair.map(o).values
    # late postings: 4% updated up to 10 days after month end
    lag = g.integers(0, 3, len(gl))
    late = g.random(len(gl)) < 0.04
    lag[late] = g.integers(5, 14, late.sum())
    gl["updated_at"] = [ts(d + timedelta(days=int(l))) for d, l in zip(gl.posting_date, lag)]
    gl["po_line_cost"] = None
    # golden rows: the 100 supplied lines, verbatim (FY22 July 2021)
    seed = seed_actuals.copy()
    seed["posting_date"] = pd.to_datetime(seed.date_key.astype(str)).dt.date
    seed["team"] = None
    seed["_seed"] = True
    gl = pd.concat([gl, seed], ignore_index=True)
    gl["_seed"] = gl["_seed"].fillna(False)
    return gl


def _po_lines(gl, t27, cc, vend_by_cat, g, po_seq) -> pd.DataFrame:
    """Maximo PO lines: closed/received lines derived from GL, plus FY27 open commitments (exact per team)."""
    has_po = gl[gl.purchase_order_key.ne("null") & gl.maximo_po_no.notna()]
    grp = has_po.groupby("maximo_po_no").agg(cost_centre_key=("cost_centre_key", "first"),
                                            account_key=("account_key", "first"), source_key=("source_key", "first"),
                                            work_order_key=("work_order_key", "first"),
                                            description=("description", "first"), invoiced=("amount", "sum"),
                                            first_post=("posting_date", "min")).reset_index()
    grp["po_number"] = grp.maximo_po_no.astype("int64").astype(str)
    # historical POs close with a small un-invoiced tail; FY27 lines already invoiced are complete (no open value)
    hist = grp.first_post < date(2026, 7, 1)
    grp["line_cost"] = np.where(hist, (grp.invoiced.clip(lower=0) * g.uniform(1.0, 1.15, len(grp))).round(2),
                                grp.invoiced.round(2))
    grp["received_amount"] = grp.invoiced.clip(lower=0)
    grp["order_date"] = grp.first_post.map(lambda d: d - timedelta(days=int(g.integers(5, 45))))
    grp["need_by_date"] = grp.first_post
    grp["po_status"] = np.where(hist, "CLOSE", "COMP")
    rows = [grp]
    # open commitments per team (committed = line_cost - invoiced)
    open_rows = []
    for team, t in t27.items():
        target = t["committed"]
        if target <= 0:
            continue
        keys = cc[cc.team == team].cost_centre_key.tolist()
        if team == "Major Projects":
            keys = ["PRM-0021E", "PRM-0017"]
        n = int(np.clip(target / 18000, 4, 400))
        amts = split_amount(target, n, g, 1.0)
        for a in amts:
            po_seq[26] += 1
            k = str(g.choice(keys))
            acc = 161150 if team in ("Major Projects", "SIB Projects") else int(g.choice([625250, 623000]))
            need = date(2026, 9, 1) + timedelta(days=int(g.integers(0, 300)))
            open_rows.append(dict(maximo_po_no=float(f"2636{po_seq[26]:05d}"), po_number=f"2636{po_seq[26]:05d}",
                                  cost_centre_key=k, account_key=acc,
                                  source_key=str(g.choice(vend_by_cat["Contractors"] + vend_by_cat["Engineering"])),
                                  work_order_key="null", description=f"{team} – open order {po_seq[26]}",
                                  invoiced=0.0, line_cost=float(a), received_amount=0.0,
                                  order_date=date(2026, 7, 1) + timedelta(days=int(g.integers(0, 60))),
                                  need_by_date=need, po_status="APPR", first_post=None))
    po = pd.concat(rows + [pd.DataFrame(open_rows)], ignore_index=True)
    po["po_line"] = 1
    po["purchase_order_key"] = po.po_number + "|" + SITE
    po["invoiced_amount"] = po.invoiced.round(2)
    po["site_id"] = SITE
    po["updated_at"] = po.order_date.map(ts)
    po["spend_classification"] = None
    return po[["purchase_order_key", "po_number", "po_line", "site_id", "source_key", "cost_centre_key", "account_key",
               "work_order_key", "description", "line_cost", "received_amount", "invoiced_amount", "order_date",
               "need_by_date", "po_status", "spend_classification", "updated_at"]]


def _classify_spend(gl, po) -> pd.DataFrame:
    """Maximo 'Budgeted' / 'Emergent' flag on FY27 POs so the PBI donut (≈3.5M / 0.2M / 0.1M) reproduces."""
    fy27 = gl[(gl.posting_date >= date(2026, 7, 1)) & gl.maximo_po_no.notna() & (gl.amount > 0)]
    by_po = fy27.groupby("maximo_po_no").amount.sum().sort_values()
    budgeted, emergent, b, e = [], [], 0.0, 0.0
    for p, amt in by_po.items():
        if b < 200_000:
            budgeted.append(p); b += amt
        elif e < 100_000:
            emergent.append(p); e += amt
    cls = {**{p: "Budgeted" for p in budgeted}, **{p: "Emergent" for p in emergent}}
    po["spend_classification"] = po.po_number.astype(float).map(cls)
    return gl


def _budget_extract(bud, seed_budget) -> pd.DataFrame:
    bud = bud[bud.amount.abs() >= 0.01].copy().reset_index(drop=True)
    bud["budget_name"] = bud.fy.map(lambda fy: f"SITEBUD{fy % 100:02d}")
    bud["budget_type"] = "Budget"
    bud["budget_entry_key"] = np.arange(10_000, 10_000 + len(bud))
    bud["entry_no"] = bud.budget_entry_key
    bud["load_date"] = bud.fy.map(lambda fy: str(date(fy - 1, 6, 15)))
    bud["updated_at"] = bud.fy.map(lambda fy: ts(date(fy - 1, 6, 15)))
    sb = seed_budget.copy()
    sb["fy"] = 2017
    sb["load_date"] = "2016-06-15"
    cols = ["budget_entry_key", "date_key", "cost_centre_key", "account_key", "entry_no", "budget_name", "budget_type",
            "amount", "updated_at", "load_date"]
    return pd.concat([sb[cols], bud[cols]], ignore_index=True)
