"""Unstructured documents for AI Functions: HSE incident reports (PDF), supplier invoices (PDF, 5 % deliberately
mismatched to the PO/GL), maintenance procedures & OEM manuals (multi-page PDF) and monthly board papers (DOCX).

Every document is rendered from the same structured records, so ai_parse_document / ai_extract output can be
scored against ground truth (ground truth manifest lands in raw/_manifests/documents.csv)."""
from __future__ import annotations

import io
from datetime import date, timedelta

import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import config as C
from common import Lander, rng

CRIMSON = colors.HexColor("#A3174F")
STY = getSampleStyleSheet()

PROCEDURES = [
    ("MP-CMP-001", "Reciprocating compressor K101–K105 – routine inspection and valve change-out", "Compression"),
    ("MP-CMP-002", "Compressor rod packing replacement", "Compression"),
    ("MP-DEH-001", "TEG dehydration unit – glycol quality sampling and filter change", "Dehydration"),
    ("MP-DEH-002", "Reboiler burner management system function test", "Dehydration"),
    ("MP-WEL-001", "Wellhead valve greasing and integrity check (Iona / Seamer / North Paaratte)", "Wells"),
    ("MP-WEL-002", "Wellhead bonnet maintenance – isolation and bleed-down", "Wells"),
    ("MP-MTR-001", "Custody transfer meter proving and gas chromatograph calibration", "Metering"),
    ("MP-SIS-001", "Safety instrumented system proof testing", "Safety Systems"),
    ("MP-FGS-001", "Fire & gas detector calibration", "Safety Systems"),
    ("MP-PL-001", "Pipeline pig launching and receiving", "Pipelines"),
    ("MP-ELE-001", "HV switchboard thermographic survey", "Electrical"),
    ("MP-UTL-001", "Nitrogen generation package maintenance", "Utilities"),
    ("OEM-CMP-K104", "OEM manual – Reciprocating compressor package (extract)", "Compression"),
    ("OEM-DEH-V324", "OEM manual – Contactor tower V-324 (extract)", "Dehydration"),
    ("PS-ISO-001", "Isolation standard – energy isolation and lock-out", "Site"),
    ("PS-PTW-001", "Permit to work standard", "Site"),
]


def _pdf(story) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    doc.build(story)
    return buf.getvalue()


def _h(text, size=16):
    s = STY["Heading1"].clone("h", fontSize=size, textColor=CRIMSON, spaceAfter=6)
    return Paragraph(text, s)


def _p(text):
    return Paragraph(text, STY["BodyText"])


def _kv(rows):
    t = Table(rows, colWidths=[50 * mm, 120 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3E3E9")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    return t


def build(D: Lander, L: Lander, out: dict):
    g = rng(70)
    manifest = []
    manifest += _incident_reports(D, g, out["hse"]["observations"], out["hse"]["investigations"])
    manifest += _invoices(D, g, out["finance"]["gl"], out["refs"]["vendors"])
    manifest += _procedures(D, g)
    manifest += _board_papers(D, g, out.get("scorecard"))
    L.csv("_manifests/documents/documents_manifest.csv", pd.DataFrame(manifest))


def _write(D: Lander, rel: str, data: bytes):
    with open(D.path(rel), "wb") as f:
        f.write(data)


def _incident_reports(D, g, obs, inv, n=200):
    pick = obs[obs.observation_type.isin(["INCIDENT", "NEARMISS"]) & (obs.reported_date >= date(2024, 7, 1))]
    pick = pd.concat([pick[pick.is_high_potential_event], pick.sample(min(n - 1, len(pick)), random_state=4)]).drop_duplicates("observation_id")
    rows = []
    for _, o in pick.iterrows():
        injury = "Laceration to left hand – first aid" if "laceration" in o.description.lower() else (
            "Strain – lower back (medical treatment)" if "strain" in o.description.lower() else "No injury")
        cause = str(g.choice(["Inadequate isolation", "Worn seal / equipment degradation", "Procedure not followed",
                              "Poor housekeeping", "Inadequate supervision", "Unexpected process condition"]))
        story = [_h("LOCHARD ENERGY – HSE INCIDENT / NEAR MISS REPORT"),
                 _kv([["Report No.", o.observation_id], ["Date of event", str(o.reported_date)],
                      ["Location / plant area", f"Iona Gas Storage Facility – {o.plant_area}"],
                      ["Event type", o.observation_type], ["Reported by", o.reported_by.replace("_LOC", "").replace(".", " ").title()],
                      ["Actionee", o.actionee.replace("_LOC", "").replace(".", " ").title()]]),
                 Spacer(1, 6), _h("Description of event", 12), _p(o.description + ". " + str(g.choice([
                     "The crew immediately stopped work and made the area safe.",
                     "Area was barricaded and the supervisor notified.",
                     "The control room initiated the site emergency response and the release was isolated within minutes."]))),
                 _h("Injury / damage", 12), _p(injury),
                 _h("Immediate actions", 12), _p("Area made safe; toolbox talk held with the crew; equipment tagged out."),
                 _h("Suspected cause", 12), _p(cause),
                 _h("Potential severity (reporter's assessment)", 12), _p(str(o.potential_risk_rank).title())]
        rel = f"hse_incident_reports/{o.reported_date:%Y/%m}/{o.observation_id}.pdf"
        _write(D, rel, _pdf(story))
        rows.append(dict(doc_family="hse_incident_report", path=rel, ref_id=o.observation_id,
                         truth_category=o.incident_category, truth_potential_risk=o.potential_risk_rank,
                         truth_injury=injury, truth_cause=cause))
    return rows


def _invoices(D, g, gl, vendors, n=300):
    ppi = gl[(gl.document_no.astype(str).str.startswith("PPI")) & (gl.amount > 500) &
             (pd.to_datetime(gl.date_key.astype(str)) >= "2025-07-01")]
    pick = ppi.sample(min(n, len(ppi)), random_state=9)
    vend = vendors.set_index("source_key")
    rows = []
    for _, r in pick.iterrows():
        v = vend.loc[r.source_key] if r.source_key in vend.index else vend.iloc[0]
        total_ex = float(r.amount)
        mismatch = g.random() < 0.05
        billed = round(total_ex * (1 + g.choice([0.08, 0.12, -0.1])), 2) if mismatch else total_ex
        k = int(g.integers(1, 4))
        lines = np.round(np.diff(np.concatenate([[0], np.sort(g.uniform(0, billed, k - 1)), [billed]])), 2)
        lines[-1] = round(billed - lines[:-1].sum(), 2)
        gst = round(billed * 0.1, 2)
        inv_no = str(r.external_document_no)
        post = pd.to_datetime(str(r.date_key)).date()
        inv_date = post - timedelta(days=int(g.integers(1, 20)))
        tbl = [["Line", "Description", "Amount (ex GST)"]] + [[str(i + 1), str(r.description)[:60] if i == 0 else "Additional services",
                                                              f"${a:,.2f}"] for i, a in enumerate(lines)]
        tbl += [["", "Subtotal", f"${billed:,.2f}"], ["", "GST 10%", f"${gst:,.2f}"], ["", "TOTAL", f"${billed + gst:,.2f}"]]
        t = Table(tbl, colWidths=[15 * mm, 110 * mm, 40 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5E5552")),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
        story = [_h(f"TAX INVOICE – {v.vendor_name}"), _p(f"ABN {v.abn or 'N/A'}"),
                 _kv([["Invoice number", inv_no], ["Invoice date", str(inv_date)], ["Bill to", "Iona Ops Trust, 285 Waarre Road, Port Campbell VIC 3269"],
                      ["Customer reference", f"Cost centre {r.cost_centre_key}"], ["Payment terms", f"{int(v.payment_terms_days)} days"]]),
                 Spacer(1, 8), t, Spacer(1, 8), _p(f"Remit to BSB {v.bank_bsb} Account {v.bank_account}")]
        rel = f"invoices/{post:%Y/%m}/INV_{r.source_key}_{inv_no}.pdf"
        _write(D, rel, _pdf(story))
        rows.append(dict(doc_family="supplier_invoice", path=rel, ref_id=int(r.entry_no), truth_invoice_no=inv_no,
                         truth_vendor=v.vendor_name, truth_subtotal=billed, truth_gst=gst, truth_total=round(billed + gst, 2),
                         truth_gl_amount=total_ex, truth_mismatch=mismatch))
    return rows


def _procedures(D, g):
    rows = []
    for code, title, area in PROCEDURES:
        story = [_h(f"{code} – {title}"), _kv([["Document", code], ["Revision", f"Rev {int(g.integers(1, 9))}"],
                                               ["Plant area", area], ["Owner", "Maintenance Superintendent"],
                                               ["Review date", str(date(2026, int(g.integers(1, 12)), 1))]])]
        for sec, body in [
            ("1. Purpose", f"This procedure defines the minimum requirements for {title.lower()} at the Iona Gas Storage Facility."),
            ("2. Hazards and controls", "Hazards include stored energy, hydrocarbon release, hot surfaces and noise. "
             "Apply the isolation standard PS-ISO-001 and obtain a permit under PS-PTW-001 before commencing. "
             "Continuous gas monitoring is mandatory; stop work if LEL exceeds 10%."),
            ("3. Tools and spares", "Calibrated torque wrench, gas detector, spill kit, manufacturer spare kit as per the Maximo job plan."),
            ("4. Procedure steps", " ".join(f"Step {i}: " + str(g.choice([
                "Confirm isolation points and verify zero energy.", "Bleed down to atmospheric pressure and purge with nitrogen.",
                "Inspect for wear, corrosion and damage; record findings in Maximo.", "Replace seals and gaskets with new OEM parts.",
                "Torque fasteners to the values in Table 1 in a star pattern.", "Leak test at 110% of operating pressure for 15 minutes.",
                "Remove isolations in reverse order and return to service under the control room's direction."])) for i in range(1, 11))),
            ("5. Acceptance criteria", "No leaks detected; vibration below 7.1 mm/s RMS; parameters within the operating envelope."),
            ("6. Records", "Complete the Maximo work order, attach test sheets and update the equipment history."),
        ]:
            story += [_h(sec, 12), _p(body)]
        story += [PageBreak(), _h("Table 1 – Torque values", 12),
                  Table([["Bolt size", "Torque (Nm)"]] + [[f"M{s}", str(int(s * s * 1.3))] for s in (12, 16, 20, 24, 30)])]
        rel = f"maintenance_procedures/{code}.pdf"
        _write(D, rel, _pdf(story))
        rows.append(dict(doc_family="maintenance_procedure", path=rel, ref_id=code, truth_area=area))
    return rows


def _board_papers(D, g, score):
    """Monthly Board Performance Reports that quote the scorecard seed, so documents and scorecard never disagree."""
    from docx import Document
    rows = []
    upd = {(u["kpi_id"], u["period_code"]): u for u in (score or {}).get("status_updates", [])}
    months = pd.period_range("2025-09", "2026-08", freq="M")
    for m in months:
        fy = m.year + 1 if m.month >= 7 else m.year
        pc = f"FY{fy % 100:02d}-M{(m.month - 7) % 12 + 1:02d}"
        ups = {k["code"]: upd.get((f"FY{fy % 100:02d}-{k['code']}", pc)) for k in C.SCORECARD_FY27}
        at_risk = [c for c, u in ups.items() if u and u["status"] in ("AT_RISK", "OFF_TRACK")]
        d = Document()
        d.add_heading(f"Board Performance Report – {m.strftime('%B %Y')}", 0)
        d.add_paragraph(f"Iona Ops Trust | FY{fy % 100:02d} period {pc[-3:]} | Prepared by the Lochard Leadership Team | Board confidential")
        d.add_heading("1. CEO summary", 1)
        summary = ("Winter withdrawal season performing strongly; customer nominations met." if m.month in (5, 6, 7, 8)
                   else "Safe and reliable operations continued through the month with customer nominations met.")
        if pc == "FY27-M02":
            summary = ("A High Potential Event (gas release at the Iona-3 wellhead) is under ICAM investigation; no injuries "
                       "resulted. HUGS commissioning planning is under way with EAC above the revised P50.")
        d.add_paragraph(summary + (f" KPIs requiring Board attention: {', '.join(at_risk)}." if at_risk else
                                   " All scorecard KPIs are On Track."))
        d.add_heading("2. Scorecard commentary", 1)
        for k in C.SCORECARD_FY27:
            u = ups.get(k["code"])
            status = u["status"].replace("_", " ").title() if u else "Not reported"
            text = (u or {}).get("commentary") or "No update submitted."
            text = text.split("] ", 1)[-1]
            d.add_paragraph(f"{k['code']} {k['name']} ({k['owner']}, {k['weight']}%) – {status}: {text}", style="List Bullet")
        d.add_heading("3. Financial performance", 1)
        d.add_paragraph("EBITDA excluding non-cash items is in line with budget. YEO has been updated for the month's reforecast.")
        d.add_heading("4. Major projects", 1)
        hugs = (ups.get("2.1") or {}).get("commentary", "").split("] ", 1)[-1].removeprefix("HUGS ")
        hugs = hugs or "EAC is being reviewed against the revised P50 budget forecast ($112.4M)."
        d.add_paragraph(f"HUGS: {hugs}" + ("" if "RFSU" in hugs else " RFSU targeted January 2027."))
        rel = f"board_papers/BPR_{m.strftime('%Y_%m')}.docx"
        buf = io.BytesIO()
        d.save(buf)
        _write(D, rel, buf.getvalue())
        rows.append(dict(doc_family="board_paper", path=rel, ref_id=str(m)))
    return rows
