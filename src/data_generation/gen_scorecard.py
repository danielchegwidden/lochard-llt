"""Board scorecard seed: FY27 KPIs transcribed from fit-scorecard.png plus a synthetic FY26 history
(12 monthly status updates, board scores at each board meeting, comment threads).

Output is a single JSON seed consumed by the board-portal Lakebase migration (and landed in the raw volume
for lineage). Directors and commentators are fictitious."""
from __future__ import annotations

import json
import os
from datetime import date

import numpy as np

import config as C
from common import Lander, fy_months, month_end, rng

DIRECTORS = [("Chair", "Board Chair"), ("Director A", "Non-executive Director"), ("Director B", "Non-executive Director"),
             ("Director C", "Non-executive Director"), ("Director D", "Non-executive Director"),
             ("Director E", "Shareholder Nominee"), ("Director F", "Shareholder Nominee")]
FY26_KPIS = [
    ("HSE & Iona Operations", "1.1", "HSE Performance", "DA", 20),
    ("HSE & Iona Operations", "1.2", "Operations & Maintenance Performance", "DA/BN", 15),
    ("HSE & Iona Operations", "1.3", "Data Utilisation Project – Phase 1", "LLT", 5),
    ("Growth Delivery", "2.1", "HUGS Delivery", "DA/DS", 15),
    ("Growth Delivery", "2.2", "Queen FEL1", "DS/DG", 15),
    ("Growth Delivery", "2.3", "Growth & Commercial Strategy", "DG/BN", 10),
    ("Financial", "3.1", "EBITDA excluding non-cash", "LLT", 15),
    ("Financial", "3.2", "Corporate Model", "LLT", 5),
]
STATUS_SCORE = {"ON_TRACK": 100, "AT_RISK": 50, "OFF_TRACK": 0, "COMPLETE": 100}
COMMENTS = {
    "1.1": ["HPE in August at Iona-3 wellhead needs a clear line of sight to the corrective actions – please bring the "
            "ICAM findings to the next meeting.", "Observation reporting is well up since the process upgrade; good leading indicator."],
    "2.1": ["EAC trending above the revised P50 of $112.4M. What are the levers to recover before RFSU?",
            "Please show the RFSU critical path and the commissioning resourcing risk."],
    "2.2": ["Turbine technology selection timing looks tight against the FEL2 gate.",
            "Support the approvals plan – ask management to keep the EAA conditions register visible."],
    "3.1": ["EBITDA on budget YTD; keep an eye on Employee Costs YEO phasing."],
    "1.2": ["Nominations within ±4% tolerance – two FY27 exceptions noted, no refunds payable."],
}


def build(L: Lander, refs: dict) -> dict:
    g = rng(60)
    seed = {"fiscal_years": [], "pillars": [], "kpis": [], "deliverables": [], "periods": [], "status_updates": [],
            "board_scores": [], "comments": [], "directors": [{"name": n, "title": t, "email": f"{n.lower().replace(' ', '.')}@board.example-lochard.com.au"}
                                                             for n, t in DIRECTORS],
            "owner_roles": C.OWNER_ROLES, "footnote": C.SCORECARD_FOOTNOTE}
    for fy, kpis in [(2026, FY26_KPIS), (2027, [(k["pillar"], k["code"], k["name"], k["owner"], k["weight"]) for k in C.SCORECARD_FY27])]:
        code = f"FY{fy % 100}"
        seed["fiscal_years"].append({"fy_code": code, "start_date": str(date(fy - 1, 7, 1)), "end_date": str(date(fy, 6, 30)),
                                     "status": "CLOSED" if fy < C.FY_CURRENT else "ACTIVE"})
        pillars = list(dict.fromkeys(p for p, *_ in kpis))
        for i, p in enumerate(pillars, 1):
            seed["pillars"].append({"fy_code": code, "pillar_no": i, "name": p})
        months = fy_months(fy)
        n_periods = 12 if fy < C.FY_CURRENT else 3
        for i, m in enumerate(months[:n_periods], 1):
            state = "LOCKED" if fy < C.FY_CURRENT or i < 2 else ("BOARD_ENDORSED" if i == 2 else "OPEN")
            seed["periods"].append({"period_code": f"{code}-M{i:02d}", "fy_code": code, "month_start": str(m),
                                    "period_end": str(month_end(m)), "board_meeting": str(month_end(m).replace(day=1)),
                                    "label": m.strftime("%b %Y"), "state": state})
        for pillar, kcode, name, owner, weight in kpis:
            kid = f"{code}-{kcode}"
            src = next((k for k in C.SCORECARD_FY27 if k["code"] == kcode), None) if fy == C.FY_CURRENT else None
            seed["kpis"].append({"kpi_id": kid, "fy_code": code, "pillar": pillar, "code": kcode, "name": name,
                                 "owner_initials": owner, "owner_role": " / ".join(C.OWNER_ROLES.get(o, o) for o in owner.split("/")),
                                 "weight_pct": weight, "preamble": (src or {}).get("preamble")})
            dels = (src or {}).get("deliverables") or [f"{name} – deliverable {j}" for j in range(1, 3)]
            for j, d in enumerate(dels, 1):
                seed["deliverables"].append({"kpi_id": kid, "seq": j, "text": d})
            for i in range(1, n_periods + 1):
                pc = f"{code}-M{i:02d}"
                if fy == C.FY_CURRENT:
                    if i > 2:
                        continue
                    st = src["status"][pc]
                else:
                    st = str(g.choice(["ON_TRACK", "AT_RISK", "OFF_TRACK"], p=[.72, .22, .06]))
                    if i == 12:
                        st = "COMPLETE" if g.random() < 0.6 else st
                seed["status_updates"].append({"kpi_id": kid, "period_code": pc, "status": st,
                                               "owner_score": int(np.clip(round(STATUS_SCORE[st] / 20 + g.normal(0, .5)), 0, 5)),
                                               "commentary": _commentary(kcode, st, fy), "submitted_by": owner})
            # board meetings: every second month in FY26, Aug in FY27
            meets = [2, 4, 6, 8, 10, 12] if fy < C.FY_CURRENT else [2]
            for i in meets:
                pc = f"{code}-M{i:02d}"
                st = next(u["status"] for u in seed["status_updates"] if u["kpi_id"] == kid and u["period_code"] == pc)
                for dn, _ in DIRECTORS:
                    base = STATUS_SCORE[st] / 20
                    seed["board_scores"].append({"kpi_id": kid, "period_code": pc, "director": dn,
                                                 "score": int(np.clip(round(base + g.normal(-0.2, 0.7)), 0, 5)),
                                                 "rationale": None})
            for text in COMMENTS.get(kcode, []) if fy == C.FY_CURRENT else []:
                seed["comments"].append({"kpi_id": kid, "period_code": f"{code}-M02",
                                         "author": str(g.choice([d for d, _ in DIRECTORS])), "author_role": "BOARD",
                                         "visibility": "BOARD_ONLY" if "EAC" in text else "ALL", "body": text})
    L.json("board/seed/scorecard_seed.json", seed)
    # local runs also refresh the app's bundled seed (src/app/server/seed) – skipped on serverless
    app_seed = os.path.join("src", "app", "server", "seed", "scorecard_seed.json")
    if os.path.isdir("src/app"):
        os.makedirs(os.path.dirname(app_seed), exist_ok=True)
        with open(app_seed, "w") as f:
            json.dump(seed, f, indent=2)
    return seed


FY27_TEXT = {  # the Jul/Aug-26 commentary transcribed from the board slide context
    "1.1": "HSE observation reporting up post process upgrade; FY27 HPE (Iona-3 wellhead gas release, Aug-26) under ICAM investigation.",
    "1.2": "All nominations delivered within ±4% tolerance except two minor exceptions with no refunds payable; schedule compliance 84% for w/c 27-Jul.",
    "1.3": "Data Utilisation Project phase 2 dashboards migrated to Databricks AI/BI; Spend Smarter savings tracking at $95k recurring YTD.",
    "2.1": "HUGS EAC trending above revised P50 ($112.4M); RFSU January 2027 remains achievable with commissioning resource uplift.",
    "2.2": "FEL2 phase 1 on budget; turbine technology shortlist complete; EAA conditions register tracking on plan.",
    "2.3": "Commercial market model drafted; SWP expansion scenarios and domestic gas reservation impacts under review.",
    "3.1": "YTD EBITDA excluding non-cash in line with FY27 budget; Employee Costs YEO phasing under review.",
    "3.2": "Corporate model baseline endorsed June 2026; mid-year refresh scheduled for February board meeting.",
}
FY26_TEXT = {  # history: status-aware, no references to FY27 events
    "1.1": {"ON_TRACK": "No recordable injuries or HPEs in the month; observation close-out within target.",
            "AT_RISK": "Observation close-out backlog above target; corrective action plan in progress with contractors.",
            "OFF_TRACK": "Recordable injury during a contractor shutdown activity; ICAM complete and learnings shared.",
            "COMPLETE": "FY26 HSE targets achieved – no Critical or Major incidents for the year."},
    "1.2": {"ON_TRACK": "Customer nominations delivered within ±4% tolerance; maintenance schedule compliance above 85%.",
            "AT_RISK": "Two nominations outside tolerance (no refunds payable); compressor availability below plan.",
            "OFF_TRACK": "Nomination shortfall during an unplanned compressor outage; refund exposure under review.",
            "COMPLETE": "FY26 nominations target met; maintenance step-change plan approved for FY27."},
    "1.3": {"ON_TRACK": "FIT initiatives on plan; Data Utilisation Project phase 1 dashboards live.",
            "AT_RISK": "Project Flowbridge MSP transition behind schedule; recovery plan agreed with the vendor.",
            "OFF_TRACK": "AESCSF remediation milestones missed; additional cyber resourcing escalated to LLT.",
            "COMPLETE": "FY26 FIT program milestones delivered."},
    "2.1": {"ON_TRACK": "HUGS construction progressing to plan; EAC within the approved budget.",
            "AT_RISK": "HUGS EAC pressure from drilling and contractor rates; contingency drawdown under review.",
            "OFF_TRACK": "HUGS critical-path delay identified; re-baseline to be presented to the Board.",
            "COMPLETE": "HUGS FY26 execute-phase milestones complete."},
    "2.2": {"ON_TRACK": "Queen FEL1 activities on plan; EAA referral preparation progressing.",
            "AT_RISK": "Queen EAA referral timing at risk; stakeholder engagement intensified.",
            "OFF_TRACK": "Queen FEL1 gate deferred pending technical review of well concept.",
            "COMPLETE": "Queen FEL1 gate passed; FEL2 budget endorsed."},
    "2.3": {"ON_TRACK": "Re-contracting strategy on plan; customer term sheets in negotiation.",
            "AT_RISK": "Customer re-contracting slower than plan given market uncertainty.",
            "OFF_TRACK": "Key customer negotiation paused; alternative offtake options being assessed.",
            "COMPLETE": "FY26 growth strategy endorsed by the Board."},
    "3.1": {"ON_TRACK": "YTD EBITDA excluding non-cash in line with FY26 budget.",
            "AT_RISK": "YTD EBITDA below budget on lower withdrawal volumes; cost actions identified.",
            "OFF_TRACK": "EBITDA materially below budget; reforecast presented to the Board.",
            "COMPLETE": "FY26 EBITDA delivered on budget."},
    "3.2": {"ON_TRACK": "Corporate model refresh on plan for June 2026 endorsement.",
            "AT_RISK": "Corporate model inputs delayed pending the HUGS re-forecast.",
            "OFF_TRACK": "Corporate model refresh deferred to FY27.",
            "COMPLETE": "Corporate model endorsed by the Board in June 2026."},
}


def _commentary(code: str, status: str, fy: int) -> str:
    if fy < C.FY_CURRENT:
        txt = FY26_TEXT.get(code, {}).get(status, "Tracking to plan.")
    else:
        txt = FY27_TEXT.get(code, "Tracking to plan.")
    return f"[{status.replace('_', ' ').title()}] {txt}"
