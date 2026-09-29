"""Calibration targets and reference data for the Lochard synthetic source systems.

Every number here is traceable to a supplied artefact:
  * PBI Finance "Function Details" screenshot (docs/Lochard Dashboard Information.docx, image1-4)
  * PBI HSE Observations screenshot (image5)
  * PBI Maintenance Dashboard screenshot (image6)
  * Tableau "Cumulative VIC demand (Table)" (docs/dashboard-ops.png)
  * Board scorecard slide (docs/fit-scorecard.png)
  * docs/Sample Data.xlsx (seed rows and value vocabularies)
"""
from datetime import date

SEED = 20260923
COMPANY = "Iona Ops Trust"
AS_OF = date(2026, 9, 23)            # "today" for the demo
FY_CURRENT = 2027                     # FY2027 = 1 Jul 2026 .. 30 Jun 2027
FY_FIRST_HISTORY = 2022               # full GL history FY2022..FY2026
FY27_YTD_END = date(2026, 8, 31)      # PBI snapshot: actuals posted through Aug-26

# ---------------------------------------------------------------------------------------------
# Finance – PBI "Function Details" matrix (K$). Budget & YEO are full-year FY2027; Actuals and
# Committed are YTD to Aug-26. Values transcribed from the screenshot.
# ---------------------------------------------------------------------------------------------
TEAMS = {
    #  team                               function                           budget  actual   yeo  committed
    "Employee Costs":                    ("Corporate",                        51059,   4300, 21196,     0),
    "Major Projects":                    ("Projects & Growth",                44565,    -85, 20808,  6838),
    "Finance, Risk and Digital":         ("Corporate",                        21044,    755,  7328,     0),
    "Asset Management":                  ("Operations",                       19645,    292,  6925,   702),
    "SIB Projects":                      ("Projects & Growth",                12435,    127,  6096,   847),
    "Operations":                        ("Operations",                        8278,    193,  3085,   529),
    "Maintenance":                       ("Operations",                        6894,     26,  1567,   118),
    "Growth":                            ("Projects & Growth",                 4375,   -232,  2068,  2183),
    "Opex Projects":                     ("Projects & Growth",                 3034,    -12,  1257,   572),
    "Reservoir Management":              ("Operations",                        2981,      4,   500,     0),
    "People, Safety and Sustainability": ("People, Safety & Sustainability",   2079,  -1707,  -879,     0),
    "Legal":                             ("Corporate",                         1749,     40,   633,     0),
    "Commercial":                        ("Corporate",                         1118,     55,   427,     0),
    "HSE":                               ("People, Safety & Sustainability",    953,     22,   323,    60),
}
# Donut "Budgeted vs Emergent" split of FY27 YTD actuals (≈ 3.5M / 0.2M / 0.1M)
COST_TYPE_CLASS_SHARE = {"(Blank)": 0.921, "Budgeted": 0.053, "Emergent": 0.026}
# FY27 monthly shape of YTD actuals (PBI "YTD (ACT + Committed) vs YEO": Jul ≈ +6.3M, Aug ≈ -2.5M)
FY27_ACTUAL_MONTH_SPLIT = {7: 1.66, 8: -0.66}
# FY27 YEO phasing by FY month (Jul=1). YEO only forecast through Dec in the PBI snapshot.
FY27_YEO_PHASING = {1: 0.07, 2: -0.035, 3: 0.24, 4: 0.235, 5: 0.235, 6: 0.225}
# HUGS drill-through: PRM-0021E YTD = -197,041.83 (Jul +1.5M, Aug -1.7M)
HUGS_CC = "PRM-0021E"
HUGS_YTD = {7: 1_503_000.00, 8: -1_700_041.83}
HUGS_P50_BUDGET = 112_400_000

# Cost-centre master. Sample keys from Sample Data.xlsx are kept verbatim and mapped to teams.
# key: (team, cc_short_name, cost_type, plant_area)
COST_CENTRES = {
    # Maintenance (Iona plant)
    "ASM-36411-0002": ("Maintenance", "Iona Plant Maintenance", "Opex", "Compression"),
    "ASM-36411-0003": ("Maintenance", "Iona Plant Maintenance", "Opex", "Dehydration"),
    "ASM-36411-0004": ("Maintenance", "Iona Plant Maintenance", "Opex", "Metering"),
    "ASM-36412-0001": ("Maintenance", "Mechanical Maintenance", "Opex", "Compression"),
    "ASM-36412-0002": ("Maintenance", "Mechanical Maintenance", "Opex", "Wells"),
    "ASM-36412-0003": ("Maintenance", "Mechanical Maintenance", "Opex", "Utilities"),
    "ASM-36412-0004": ("Maintenance", "Mechanical Maintenance", "Opex", "Pipelines"),
    "ASM-36412-0005": ("Maintenance", "Electrical & Instrumentation", "Opex", "Control Systems"),
    "ASM-36412-0006": ("Maintenance", "Electrical & Instrumentation", "Opex", "Electrical"),
    "ASM-36412-0007": ("Maintenance", "Electrical & Instrumentation", "Opex", "Metering"),
    # Asset Management (integrity, reliability)
    "ASM-36421-0002": ("Asset Management", "Asset Integrity", "Opex", "Pipelines"),
    "ASM-36421-0003": ("Asset Management", "Asset Integrity", "Opex", "Wells"),
    "ASM-36421-0004": ("Asset Management", "Asset Integrity", "Opex", "Pressure Equipment"),
    "ASM-36421-0005": ("Asset Management", "Asset Integrity", "Opex", "Structures"),
    "ASM-36422-0001": ("Asset Management", "Reliability Engineering", "Opex", "Compression"),
    "ASM-36422-0002": ("Asset Management", "Reliability Engineering", "Opex", "Control Systems"),
    "ASM-36422-0003": ("Asset Management", "Reliability Engineering", "Opex", "Dehydration"),
    "ASM-36422-0004": ("Asset Management", "Reliability Engineering", "Opex", "Utilities"),
    "ASM-36451-0002": ("Asset Management", "Facilities & Site Services", "Opex", "Site"),
    "ASM-36451-0004": ("Asset Management", "Facilities & Site Services", "Opex", "Site"),
    "ASM-36452-0003": ("Asset Management", "Inspection & NDT", "Opex", "Pressure Equipment"),
    "ASM-36452-0006": ("Asset Management", "Inspection & NDT", "Opex", "Pipelines"),
    # SIB (stay-in-business) projects
    "ASM-36453-0002": ("SIB Projects", "SIB Plant Renewals", "SIB", "Site"),
    "ASM-36453-0003": ("SIB Projects", "SIB Plant Renewals", "SIB", "Compression"),
    "ASM-36453-0007": ("SIB Projects", "SIB Plant Renewals", "SIB", "Structures"),
    "ASM-36454-0002": ("SIB Projects", "SIB Control System Upgrade", "SIB", "Control Systems"),
    "ASM-36454-0003": ("SIB Projects", "SIB Control System Upgrade", "SIB", "Control Systems"),
    "ASM-36454-0004": ("SIB Projects", "SIB Wells Workover", "SIB", "Wells"),
    "ASM-36463-0001": ("SIB Projects", "SIB Wells Workover", "SIB", "Wells"),
    "ASM-36464-0001": ("SIB Projects", "SIB Fire & Gas", "SIB", "Safety Systems"),
    # Operations / production
    "PRD-36404-0003": ("Operations", "Iona Operations", "Opex", "Compression"),
    "PRD-36404-0004": ("Operations", "Iona Operations", "Opex", "Dehydration"),
    "PRD-36404-0006": ("Operations", "Iona Operations", "Opex", "Metering"),
    "PRD-36404-0008": ("Operations", "Control Room", "Opex", "Control Systems"),
    # Commercial (gas nominations, business)
    "GNB-36401-0001": ("Commercial", "Commercial Operations", "Opex", "Corporate"),
    "GNB-36402-0001": ("Commercial", "Commercial Operations", "Opex", "Corporate"),
    "GNB-36403-0001": ("Commercial", "Market & Regulatory", "Opex", "Corporate"),
    "GNB-36403-0004": ("Commercial", "Market & Regulatory", "Opex", "Corporate"),
    # Reservoir management
    "GAS-36820-0015": ("Reservoir Management", "Reservoir Engineering", "Opex", "Wells"),
    "GAS-36820-0021": ("Reservoir Management", "Subsurface Monitoring", "Opex", "Wells"),
    # Opex projects
    "PRC-0005": ("Opex Projects", "Data Utilisation Project", "Opex", "Corporate"),
    "PRC-003B": ("Opex Projects", "Spend Smarter", "Opex", "Corporate"),
    "PRC-0011": ("Opex Projects", "Project Flowbridge", "Opex", "Corporate"),
    # Major projects
    "PRM-0021E": ("Major Projects", "HUGS", "Capex", "HUGS"),
    "PRM-0021C": ("Major Projects", "HUGS", "Capex", "HUGS"),
    "PRM-0021": ("Major Projects", "HUGS", "Capex", "HUGS"),
    "PRM-0017": ("Major Projects", "Project Aegis", "Capex", "Compression"),
    "PRM-0030": ("Major Projects", "CAP", "Capex", "Site"),
    "PRM-0031": ("Major Projects", "PM and FGH", "Capex", "Site"),
    "PRM-0570": ("Major Projects", "Project 570", "Capex", "Pipelines"),
    # Growth
    "ZBD-0003": ("Growth", "Queen Development", "Capex", "Corporate"),
    "ZBD-0005": ("Growth", "Growth Pipeline", "Opex", "Corporate"),
    # Corporate
    "ZZZ-2000": ("Finance, Risk and Digital", "Corporate Overheads", "Opex", "Corporate"),
    "ZFR-0001": ("Finance, Risk and Digital", "Finance", "Opex", "Corporate"),
    "ZFR-0002": ("Finance, Risk and Digital", "Digital & Cyber", "Opex", "Corporate"),
    "ZSS-0003": ("People, Safety and Sustainability", "People & Culture", "Opex", "Corporate"),
    "ZSS-0005": ("People, Safety and Sustainability", "Sustainability", "Opex", "Corporate"),
    "ZHS-0001": ("HSE", "HSE Systems", "Opex", "Corporate"),
    "ZHS-0002": ("HSE", "Process Safety", "Opex", "Site"),
    "ZLG-0001": ("Legal", "Legal & Company Secretariat", "Opex", "Corporate"),
    "EMP-1000": ("Employee Costs", "Operations Employees", "Opex", "Site"),
    "EMP-2000": ("Employee Costs", "Corporate Employees", "Opex", "Corporate"),
    "EMP-3000": ("Employee Costs", "Projects Employees", "Opex", "Corporate"),
}

# Projects (CC short name -> project names). Screenshot shows HUGS Execute/Concept phases.
PROJECTS = {
    "HUGS": ["Heytesbury Underground Gas Storage (Execute Phase)", "Heytesbury Underground Gas Storage (Concept Phase)"],
    "Project Aegis": ["Project Aegis – Compressor Upgrade"],
    "CAP": ["Control & Automation Program"],
    "PM and FGH": ["PM and Fuel Gas Heater Replacement"],
    "Project 570": ["Project 570 – Withdrawal Capacity"],
    "Queen Development": ["Queen FEL2"],
    "Data Utilisation Project": ["Data Utilisation Project – Phase 2"],
    "Project Flowbridge": ["Project Flowbridge"],
    "Spend Smarter": ["Spend Smarter"],
}

# GL accounts (key: name, group, capex_flag). Sample accounts kept verbatim.
ACCOUNTS = {
    161150: ("AUC: Gas Storage Plant & Equip", "Assets Under Construction", True),
    161160: ("AUC: Wells & Reservoir", "Assets Under Construction", True),
    161170: ("AUC: Pipelines", "Assets Under Construction", True),
    610100: ("Salaries & Wages", "Employee Costs", False),
    610200: ("Superannuation", "Employee Costs", False),
    610300: ("Payroll Tax", "Employee Costs", False),
    610400: ("Leave Provisions", "Employee Costs", False),
    615800: ("Training & Development", "Employee Costs", False),
    623000: ("R&M – Materials & Spares", "Repairs & Maintenance", False),
    623510: ("R&M – Freight", "Repairs & Maintenance", False),
    625250: ("R&M – Contractors", "Repairs & Maintenance", False),
    626900: ("Consumables & PPE", "Operating Costs", False),
    635900: ("Consulting Fees", "Professional Services", False),
    636100: ("Legal Fees", "Professional Services", False),
    649900: ("Plant & Equipment Hire", "Operating Costs", False),
    650200: ("IT Software & Licences", "IT & Digital", False),
    651050: ("Insurance", "Corporate Costs", False),
    655000: ("Travel & Accommodation", "Corporate Costs", False),
    660100: ("Fuel Gas & Utilities", "Operating Costs", False),
    670000: ("Lease Payments", "Corporate Costs", False),
}

# Account mix per team (weights)
TEAM_ACCOUNTS = {
    "Employee Costs": {610100: .78, 610200: .1, 610300: .05, 610400: .05, 615800: .02},
    "Major Projects": {161150: .7, 161160: .15, 161170: .1, 635900: .05},
    "Finance, Risk and Digital": {650200: .4, 635900: .2, 651050: .25, 670000: .1, 655000: .05},
    "Asset Management": {625250: .5, 623000: .3, 635900: .15, 626900: .05},
    "SIB Projects": {161150: .6, 625250: .3, 623000: .1},
    "Operations": {660100: .4, 626900: .2, 625250: .2, 623000: .15, 649900: .05},
    "Maintenance": {625250: .45, 623000: .4, 623510: .05, 626900: .05, 649900: .05},
    "Growth": {635900: .7, 636100: .1, 655000: .2},
    "Opex Projects": {635900: .6, 650200: .4},
    "Reservoir Management": {625250: .5, 635900: .5},
    "People, Safety and Sustainability": {615800: .5, 635900: .3, 655000: .2},
    "Legal": {636100: 1.0},
    "Commercial": {635900: .6, 655000: .4},
    "HSE": {626900: .6, 635900: .4},
}

# ---------------------------------------------------------------------------------------------
# HSE – PBI HSE Observations (Class = INCIDENT, all dates)
# ---------------------------------------------------------------------------------------------
HSE_TOTAL_OBSERVATIONS = 5132
HSE_OPEN_OBSERVATIONS = 321          # NEW 279 + INPROG 42
HSE_STATUS = {"CLOSED": 4811, "INPROG": 42, "NEW": 279}
HSE_INVESTIGATIONS_TOTAL = 140
HSE_INVESTIGATIONS_OPEN = 7
HSE_CATEGORY_SHARE = {"GENERAL SAFETY": .722, "PROCESS SAFETY": .110, "PRODUCTION": .105,
                      "ENVIRONMENTAL": .055, "Other": .008}
# Risk rank (actual) x status matrix from PBI
HSE_RISK_STATUS = {
    "HIGH":    {"CLOSED": 14,   "INPROG": 0,  "NEW": 7},
    "MEDIUM":  {"CLOSED": 145,  "INPROG": 6,  "NEW": 28},
    "LOW":     {"CLOSED": 510,  "INPROG": 5,  "NEW": 30},
    "Unknown": {"CLOSED": 4142, "INPROG": 31, "NEW": 214},
}
HSE_TYPE_SHARE = {"SAFEACT": .385, "HAZARD": .292, "INCIDENT": .128, "HAZARD_REPORT": .066,
                  "NEARMISS": .058, "Other": .005}  # approximates the rolling-12M line heights
HSE_FIRST_DATE = date(2014, 7, 1)

# ---------------------------------------------------------------------------------------------
# Maintenance – PBI Maintenance Dashboard (Schedule Week 27/07/2026, refreshed 04/08/2026)
# ---------------------------------------------------------------------------------------------
MX_WEEKS = ["2026-05-04", "2026-05-11", "2026-05-18", "2026-05-25", "2026-06-01", "2026-06-08",
            "2026-06-15", "2026-06-22", "2026-06-29", "2026-07-06", "2026-07-13", "2026-07-20", "2026-07-27"]
MX_COMPLIANCE_PCT = [73.5, 91.7, 92.9, 88.0, 75.9, 81.9, 82.0, 75.4, 86.4, 86.2, 74.3, 86.4, 84.4]
MX_SCHEDULED_WO = [68, 48, 56, 92, 86, 72, 50, 65, 59, 65, 75, 44, 77]   # sums to 857 = donut total
MX_SCHED_HOURS = [529, 395, 401, 450, 520, 349, 1000, 557, 703, 701, 622, 578, 653]
MX_COMPLETED_HOURS = [418, 386, 392, 386, 379, 250, 813, 311, 538, 554, 459, 405, 469]
MX_LATEST_SNAPSHOT = "2026-08-04"
MX_OVERDUE_SAFETY_CRITICAL = 25
MX_OPEN_P1 = 4
MX_OPEN_P2_EXCL_PM = 635
MX_BACKLOG_EXCL_PM = 5328
MX_TYPE_SHARE_SCHEDULED = {"PM": .6709, "GPC": .1225, "DM": .1074, "CBM": .0688, "MOD": .012,
                           "ADMIN": .004, "EM": .005, "HSE": .004, "MAINT": .003, "OPS": .002,
                           "TRA": .001, "Unknown": .0004}
# exact 13-week scheduled mix from the PBI donut (PM 575 / GPC 105 / DM 92 / CBM 59 / ...)
MX_TYPE_COUNTS_13W = {"PM": 575, "GPC": 105, "DM": 92, "CBM": 59, "MOD": 10, "EM": 4, "ADMIN": 3, "HSE": 3,
                      "MAINT": 3, "OPS": 2, "TRA": 1}
MX_OPEN_STATUSES = ["APPR", "SCHED", "PLANUNDER", "ACKREC", "PLANCOMP", "WMATL", "WAPPR", "ENGREV",
                    "RESCHED", "OPEN", "WSCH", "WVENDOR"]
MX_CLOSED_STATUSES = ["CLOSE", "COMP", "CAN", "CLOSED", "SRCAN"]
MX_LEAD_CRAFTS = ["MECHTECH", "CONTRACT", "EITECH", "NDTTECH", "ELECTCONT", "COMPCONT", "CTRLTECH",
                  "INST", "BMAKER", "FEQINSP", "WELLCONT", "OPERATOR", "CALCONT", "PLUMBER",
                  "LOGISTICS", "ELECENG", "PAINTER", "ENGINEER", "FITTER", "GARDNER", "FIRESETN",
                  "ELECT", "CARPENTER", "PRODTECH", "CIVILWOR", "REFMECH", "CLADDER", "SCAFFOLD",
                  "ADMIN", "APERISA", "ASSIST", "CDELFORC", "CHEMIST", "CIVILENG", "CLEANER", "Unknown"]

# ---------------------------------------------------------------------------------------------
# Market – Tableau "Cumulative VIC demand (Table)", PJ per month (Jan..Aug)
# ---------------------------------------------------------------------------------------------
VIC_MONTHLY_PJ = {
    2021: [9.6, 9.0, 10.2, 15.2, 22.7, 28.0, 29.5, 24.8],
    2022: [8.5, 8.8, 10.3, 14.1, 23.6, 28.3, 30.2, 25.5],
    2023: [8.7, 8.7, 10.4, 12.9, 21.4, 22.9, 23.6, 21.3],
    2024: [8.0, 8.1, 9.0, 13.0, 19.5, 25.3, 27.1, 18.6],
}
MARKET_FIRST_DATE = date(2014, 1, 1)

# Iona facility (public, approximate)
IONA_CAPACITY_PJ = 24.4
IONA_CAPACITY_PJ_POST_HUGS = 26.2
IONA_MAX_WITHDRAWAL_TJ = 570
IONA_MAX_INJECTION_TJ = 155
IONA_WELLS = ["Iona-1", "Iona-2", "Iona-3", "Iona-4", "Iona-5", "Iona-7", "Seamer-2",
              "North Paaratte-4", "North Paaratte-5", "Wallaby Creek-2"]

# ---------------------------------------------------------------------------------------------
# Board scorecard – FY27 (from fit-scorecard.png)
# ---------------------------------------------------------------------------------------------
SCORECARD_FY27 = [
    {"pillar": "HSE & Iona Operations", "code": "1.1", "name": "HSE Performance", "owner": "DA", "weight": 20,
     "status": {"FY27-M01": "AT_RISK", "FY27-M02": "AT_RISK"},
     "deliverables": ["No Critical or Major Incidents", "No High Potential Events", "Nil recordable injuries",
                      "Roll out the upgrade of the HSE Incident/Observations process",
                      "Deliver a step change in IMS & Process Safety compliance"]},
    {"pillar": "HSE & Iona Operations", "code": "1.2", "name": "Operations & Maintenance Performance",
     "owner": "DA/BN", "weight": 10, "status": {"FY27-M01": "ON_TRACK", "FY27-M02": "ON_TRACK"},
     "deliverables": ["100% of customer nominations delivered within the contractual delivery tolerance of ±4% "
                      "(or, if outside that tolerance, without any contractual refunds payable to customers)",
                      "Deliver a step change in maintenance delivery (including SIB)"]},
    {"pillar": "HSE & Iona Operations", "code": "1.3", "name": "Delivery of key FIT program initiatives",
     "owner": "LLT", "weight": 5, "status": {"FY27-M01": "ON_TRACK", "FY27-M02": "ON_TRACK"},
     "deliverables": ["Data driven insights – Implement the next phase of the Data Utilisation Project and roll out "
                      "the dashboards in line or ahead of the project plan",
                      "Spend Smarter – Deliver a target of $250k of recurring O&M savings in addition to the budget targets",
                      "Digital & Cyber – Complete Horizon 1 activities (incl. MSP implementation; Project Flowbridge and "
                      "address all FY26 AESCSF internal audit findings, with a Board-approved plan to reach SP2"]},
    {"pillar": "Growth Delivery", "code": "2.1", "name": "HUGS Delivery", "owner": "DA/DS", "weight": 5,
     "status": {"FY27-M01": "AT_RISK", "FY27-M02": "AT_RISK"},
     "deliverables": ["Project delivered on or under revised P50 budget forecast ($112.4M)",
                      "Project is handed over and RFSU in January 2027"]},
    {"pillar": "Growth Delivery", "code": "2.2", "name": "Queen Delivery", "owner": "DS/DG", "weight": 20,
     "status": {"FY27-M01": "ON_TRACK", "FY27-M02": "ON_TRACK"},
     "preamble": "Material progress on the development of:",
     "deliverables": ["Phase 1 & 2 of FEL2 in line with budget and schedule agreed post EAA",
                      "Technology selection complete and order ready to be paced for turbines",
                      "Regulatory approvals on track in line with schedule and Approvals Plan as at the FEL2 gate",
                      "The negotiation and finalisation of the AFO and LLI/Project Financing requirements",
                      "Project assurance plan endorsed by the Board",
                      "Approved progression through the end of FEL2 gate by the end of financial year by all key "
                      "project stakeholders"]},
    {"pillar": "Growth Delivery", "code": "2.3", "name": "Growth & Commercial Strategy", "owner": "DG/BN",
     "weight": 10, "status": {"FY27-M01": "ON_TRACK", "FY27-M02": "ON_TRACK"},
     "deliverables": ["Develop a commercial market model and customer re-contracting strategy, responding to changing "
                      "market dynamics, (eg SWP expansion and domestic gas reservation), that support material progress "
                      "on further Pillar 1 expansion opportunities, post 2030. Execute on Board agreed components of "
                      "the strategy in FY27",
                      "Develop a growth seriatim of opportunities, with a focus on Pillar 1 & 4, that Lochard has a "
                      "competitive advantage to deliver with (1) commercial viability and (2) potential for FID "
                      "within 3-4 years"]},
    {"pillar": "Financial", "code": "3.1", "name": "EBITDA excluding non-cash", "owner": "LLT", "weight": 20,
     "status": {"FY27-M01": "ON_TRACK", "FY27-M02": "ON_TRACK"},
     "deliverables": ["On budget, as per FY27 budget endorsed by Board"]},
    {"pillar": "Financial", "code": "3.2", "name": "TSR per Lochard Corporate Model", "owner": "LLT", "weight": 10,
     "status": {"FY27-M01": "ON_TRACK", "FY27-M02": "ON_TRACK"},
     "deliverables": ["Model endorsed by Board June '26 as starting point. Model endorsed by Board at end FY27 as end point"]},
]
SCORECARD_FOOTNOTE = ("The Board retains full discretion to amend the KPIs and/or FY27 outcome for material events "
                      "during the year")
OWNER_ROLES = {"DA": "Chief Operating Officer", "BN": "GM Commercial", "DS": "GM Project Delivery",
               "DG": "GM Development", "LLT": "Lochard Leadership Team"}
