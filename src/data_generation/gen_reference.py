"""Master data extracts: cost centres (with an SCD2-triggering re-org), accounts, projects, vendors,
assets, people. Emitted as CDC-style CSV extracts the way an ERP/Maximo interface would drop them."""
from __future__ import annotations

import zlib
from datetime import date

import numpy as np
import pandas as pd

import config as C
from common import Lander, rng, ts

FIRST_NAMES = ["James", "Olivia", "Liam", "Charlotte", "Noah", "Amelia", "Jack", "Isla", "William", "Mia",
               "Oliver", "Grace", "Thomas", "Chloe", "Lucas", "Ella", "Henry", "Zoe", "Ethan", "Ruby",
               "Harrison", "Sophie", "Cooper", "Matilda", "Riley", "Harper", "Lachlan", "Evie", "Hamish", "Ivy",
               "Declan", "Priya", "Arjun", "Mei", "Tuan", "Aroha", "Nikolai", "Sienna", "Kieran", "Tahlia"]
LAST_NAMES = ["Nguyen", "Smith", "Kelly", "O'Brien", "Walsh", "Patel", "Brennan", "Murphy", "Harris", "Clarke",
              "Fraser", "Mackenzie", "Rossi", "Papadopoulos", "Chen", "Wright", "Hughes", "Doyle", "Lawson", "Baxter",
              "McLeod", "Singh", "Kovac", "Ferreira", "Tan", "Gallagher", "Morrison", "Quinn", "Holt", "Barrett"]

VENDOR_NAMES = [
    ("Otway Mechanical Services Pty Ltd", "Contractors"), ("Southwest Scaffolding Pty Ltd", "Contractors"),
    ("Coastline Electrical Contracting", "Contractors"), ("Warrnambool Industrial Supplies", "Materials"),
    ("Western District Plumbing", "Contractors"), ("Portside Freight & Logistics", "Freight"),
    ("Compressor Solutions Australia", "OEM"), ("Gas Turbine & Engine Services", "OEM"),
    ("Precision Valve Services", "OEM"), ("Integrity NDT Inspections", "Inspection"),
    ("Apex Instrumentation Pty Ltd", "Materials"), ("SafeWork PPE Supplies", "Materials"),
    ("Pipeline Engineering Consultants", "Engineering"), ("Hive Legal", "Legal"),
    ("Mallee Legal Partners", "Legal"), ("Bassline Advisory", "Consulting"),
    ("Kinetic Project Delivery", "Engineering"), ("TerraGeo Reservoir Consulting", "Engineering"),
    ("Cloudwise IT Services", "IT"), ("Sentinel Cyber Security", "IT"), ("Pure Water Solutions", "Materials"),
    ("Heytesbury Civil Works", "Contractors"), ("Great Ocean Plant Hire", "Plant Hire"),
    ("Corangamite Waste Services", "Contractors"), ("National Insurance Brokers", "Insurance"),
    ("Swagelok Victoria", "Materials"), ("Rittal Australia", "Materials"), ("NuBolt Fasteners", "Materials"),
    ("Tork Hygiene Supplies", "Materials"), ("Victorian Energy Training", "Training"),
    ("Qantas Business Travel", "Travel"), ("Coastal Catering Co", "Services"), ("DrillCo Well Services", "OEM"),
    ("Hydrogen Futures Advisory", "Consulting"), ("Stonehaven Surveying", "Engineering"),
]


def cost_centres(g) -> pd.DataFrame:
    rows = []
    for k, (team, short, ctype, area) in C.COST_CENTRES.items():
        function = C.TEAMS[team][0]
        rows.append(dict(cost_centre_key=k, cost_centre_name=f"{short} – {area}", cc_short_name=short, team=team,
                         function=function, cost_type=ctype, plant_area=area, company_name=C.COMPANY,
                         cc_manager_email=None, is_active=True))
    return pd.DataFrame(rows)


def people(g, n: int = 140) -> pd.DataFrame:
    """Fictitious staff directory (actionees, WO owners, KPI owners). Usernames follow FIRST.LAST_LOC."""
    seen, rows = set(), []
    while len(rows) < n:
        f, l = g.choice(FIRST_NAMES), g.choice(LAST_NAMES)
        u = f"{f}.{l}".upper().replace("'", "") + "_LOC"
        if u in seen:
            continue
        seen.add(u)
        team = g.choice(["Operations", "Maintenance", "Asset Management", "HSE", "Reservoir Management",
                         "Major Projects", "Commercial", "Finance, Risk and Digital"],
                        p=[.25, .25, .12, .08, .05, .1, .07, .08])
        rows.append(dict(username=u, display_name=f"{f} {l}", email=f"{f}.{l}".lower().replace("'", "")
                         + "@example-lochard.com.au", team=team, site=g.choice(["Iona", "Melbourne"], p=[.75, .25]),
                         is_contractor=bool(g.random() < 0.15)))
    return pd.DataFrame(rows)


def vendors(g) -> pd.DataFrame:
    rows = []
    for i, (name, cat) in enumerate(VENDOR_NAMES):
        rows.append(dict(source_key=f"V_{101600 + i * 37}", vendor_name=name, vendor_category=cat,
                         abn=f"{g.integers(10, 99)} {g.integers(100, 999)} {g.integers(100, 999)} {g.integers(100, 999)}",
                         bank_bsb=f"{g.integers(0, 999):03d}-{g.integers(0, 999):03d}",
                         bank_account=f"{g.integers(10_000_000, 99_999_999)}", payment_terms_days=int(g.choice([14, 30, 45])),
                         is_active=True))
    # sample vendor keys from Sample Data.xlsx become extra vendors so every seed row resolves
    for k in ["V_101713", "V_101837", "V_200070", "V_200013", "V_109222", "V_107329", "V_102865", "V_109144",
              "V_101736", "V_109441", "V_102109", "V_102420", "V_101778", "V_101658", "V_200002", "V_109358",
              "V_200140", "V_109385", "V_101617", "V_104414", "V_102687", "V_107323", "V_109453", "V_102666",
              "V_109486", "V_109461", "V_200010"]:
        name, cat = VENDOR_NAMES[int(k[2:]) % len(VENDOR_NAMES)]
        rows.append(dict(source_key=k, vendor_name=f"{name.split(' Pty')[0]} ({k[-3:]})", vendor_category=cat,
                         abn=f"{g.integers(10, 99)} {g.integers(100, 999)} {g.integers(100, 999)} {g.integers(100, 999)}",
                         bank_bsb=f"{g.integers(0, 999):03d}-{g.integers(0, 999):03d}",
                         bank_account=f"{g.integers(10_000_000, 99_999_999)}", payment_terms_days=30, is_active=True))
    # employee reimbursement "vendors" (V_9990xxxxx) – PII
    for i in range(12):
        rows.append(dict(source_key=f"V_9990{13100 + i * 25}", vendor_name="EMPLOYEE REIMBURSEMENT", vendor_category="Employee",
                         abn=None, bank_bsb=f"{g.integers(0, 999):03d}-{g.integers(0, 999):03d}",
                         bank_account=f"{g.integers(10_000_000, 99_999_999)}", payment_terms_days=7, is_active=True))
    return pd.DataFrame(rows)


def accounts() -> pd.DataFrame:
    return pd.DataFrame([dict(account_key=k, account_name=v[0], account_group=v[1], capex_flag=v[2],
                              pl_bs="BS" if v[2] else "PL") for k, v in C.ACCOUNTS.items()])


def projects() -> pd.DataFrame:
    rows = []
    for short, names in C.PROJECTS.items():
        for n in names:
            phase = "Execute" if "Execute" in n else ("Concept" if "Concept" in n else "Delivery")
            rows.append(dict(project_key=f"PRJ-{zlib.crc32(n.encode()) % 10000:04d}", project_name=n, cc_short_name=short,
                             phase=phase,
                             p50_budget=C.HUGS_P50_BUDGET if n.startswith("Heytesbury") and phase == "Execute" else None,
                             rfsu_target="2027-01-31" if n.startswith("Heytesbury") and phase == "Execute" else None))
    return pd.DataFrame(rows)


def assets(g) -> pd.DataFrame:
    areas = {
        "Wells": [f"WELL-{w.upper().replace(' ', '').replace('-', '')}" for w in C.IONA_WELLS],
        "Compression": ["CMP-K101", "CMP-K102", "CMP-K103", "CMP-K104", "CMP-K105"],
        "Dehydration": ["DEH-V301", "DEH-V324", "DEH-E403", "DEH-P310"],
        "Metering": ["MTR-FT601", "MTR-FT602", "MTR-GC610"],
        "Control Systems": ["DCS-01", "SIS-01", "RTU-NP", "RTU-WC"],
        "Safety Systems": ["FGS-01", "ESD-01", "FWP-01"],
        "Utilities": ["N2-01", "IA-01", "GEN-01", "FG-HTR-01"],
        "Pipelines": ["PL-SWP-INT", "PL-NP-IONA", "PL-WC-IONA", "PL-HUGS"],
        "Electrical": ["HV-SWB-01", "MCC-01", "UPS-01"],
        "Structures": ["BLDG-CTRL", "BLDG-WSHOP", "RACK-01"],
    }
    rows = []
    for area, tags in areas.items():
        for t in tags:
            rows.append(dict(asset_num=t, asset_description=f"{area} – {t}", site_id="S3620", plant_area=area,
                             safety_critical=area in ("Wells", "Safety Systems", "Compression", "Pipelines")
                             or g.random() < 0.2, criticality=int(g.choice([1, 2, 3], p=[.3, .5, .2]))))
    return pd.DataFrame(rows)


def write_all(L: Lander, load_date: date):
    g = rng(1)
    cc = cost_centres(g)
    stamp = ts(load_date)
    cc["_op"] = "UPSERT"; cc["_seq"] = 1; cc["updated_at"] = ts(date(2021, 7, 1))
    # SCD2 driver – FY26 re-org (2025-07-01): ZFR-0002 renamed "IT" -> "Digital & Cyber" and PRC-0011
    # (Project Flowbridge) re-issued, so silver keeps cost-centre history.
    reorg = cc[cc.cost_centre_key.isin(["ZFR-0002", "PRC-0011"])].copy()
    before = reorg.copy()
    before["cc_short_name"] = np.where(before.cost_centre_key == "ZFR-0002", "IT", before.cc_short_name)
    before["updated_at"] = ts(date(2021, 7, 1)); before["_seq"] = 0
    reorg["updated_at"] = ts(date(2025, 7, 1)); reorg["_seq"] = 2
    L.csv(f"erp/cost_centres/load_date=2021-07-01/cost_centres_20210701.csv",
          pd.concat([cc[~cc.cost_centre_key.isin(before.cost_centre_key)], before]))
    L.csv(f"erp/cost_centres/load_date=2025-07-01/cost_centres_20250701.csv", reorg)
    L.csv(f"erp/accounts/load_date={load_date}/accounts.csv", accounts().assign(updated_at=stamp))
    L.csv(f"erp/projects/load_date={load_date}/projects.csv", projects().assign(updated_at=stamp))
    v = vendors(g)
    L.csv(f"erp/vendors/load_date={load_date}/vendors.csv", v.assign(updated_at=stamp))
    p = people(g)
    L.csv(f"hse/people/load_date={load_date}/people.csv", p.assign(updated_at=stamp))
    a = assets(g)
    L.csv(f"maximo/assets/load_date={load_date}/assets.csv", a.assign(updated_at=stamp))
    return dict(cost_centres=cc, vendors=v, people=p, assets=a, accounts=accounts(), projects=projects())
