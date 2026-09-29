"""Board-pack export – the board scorecard slide rebuilt from live Lakebase data (python-pptx)."""
from __future__ import annotations

import io
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

from .. import auth
from .scorecard import load_scorecard, me_dep

router = APIRouter(prefix="/api")
CRIMSON = RGBColor(0xA3, 0x19, 0x4E)
PINK = RGBColor(0xF3, 0xE3, 0xE9)
GREY = RGBColor(0x56, 0x51, 0x50)
STATUS = {"ON_TRACK": ("On Track", RGBColor(0xA6, 0xE0, 0x7C)), "AT_RISK": ("At Risk", RGBColor(0xFF, 0xD9, 0x66)),
          "OFF_TRACK": ("Off Track", RGBColor(0xF2, 0x8B, 0x82)), "COMPLETE": ("Complete", RGBColor(0x9D, 0xC3, 0xE6)),
          None: ("Not reported", RGBColor(0xE0, 0xE0, 0xE0))}


def _cell(cell, text, size=9, bold=False, color=RGBColor(0x1E, 0x1E, 0x1E), fill=None, align=PP_ALIGN.LEFT):
    cell.text = ""
    tf = cell.text_frame
    tf.word_wrap = True
    lines = text if isinstance(text, list) else [text]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = line
        r.font.size, r.font.bold, r.font.color.rgb = Pt(size), bold, color
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    cell.margin_left = cell.margin_right = Emu(50000)
    cell.margin_top = cell.margin_bottom = Emu(20000)
    if fill is not None:
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill


def build_pptx(sc: dict) -> bytes:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    s = prs.slides.add_slide(prs.slide_layouts[6])
    tb = s.shapes.add_textbox(Inches(0.1), Inches(0.05), Inches(8), Inches(0.7)).text_frame
    r = tb.paragraphs[0].add_run()
    r.text, r.font.size, r.font.color.rgb = f"{sc['fy']} Board Scorecard – {sc['period']['label']}", Pt(32), CRIMSON
    kpis = [k for p in sc["pillars"] for k in p["kpis"]]
    rows, cols = len(kpis) + 1, 7
    shape = s.shapes.add_table(rows, cols, Inches(0.1), Inches(0.85), Inches(13.1), Inches(6.0))
    t = shape.table
    for i, w in enumerate([1.1, 0.45, 1.5, 7.5, 0.8, 0.75, 1.0]):
        t.columns[i].width = Inches(w)
    fy = sc["fy"]
    head = [f"{fy} Key Performance Indicators", "", "", f"{fy} Deliverables", "Owner", "Weight", "Status"]
    for c, h in enumerate(head):
        _cell(t.cell(0, c), h, 10, True, RGBColor(0xFF, 0xFF, 0xFF), CRIMSON)
    t.cell(0, 0).merge(t.cell(0, 2))
    r0 = 1
    for p in sc["pillars"]:
        n = len(p["kpis"])
        _cell(t.cell(r0, 0), p["name"], 10, True, fill=PINK, align=PP_ALIGN.CENTER)
        if n > 1:
            t.cell(r0, 0).merge(t.cell(r0 + n - 1, 0))
        for j, k in enumerate(p["kpis"]):
            rr = r0 + j
            _cell(t.cell(rr, 1), k["code"], 9, True, CRIMSON, PINK)
            _cell(t.cell(rr, 2), k["name"], 9, True, CRIMSON)
            dl = ([k["preamble"]] if k.get("preamble") else []) + [f"{d['seq']}. {d['text']}" for d in k["deliverables"]]
            _cell(t.cell(rr, 3), dl, 8)
            _cell(t.cell(rr, 4), k["owner_initials"], 9, align=PP_ALIGN.CENTER)
            _cell(t.cell(rr, 5), f"{k['weight_pct']:.0f}%", 9, align=PP_ALIGN.CENTER)
            label, fill = STATUS.get(k.get("status"), STATUS[None])
            _cell(t.cell(rr, 6), label, 9, fill=fill, align=PP_ALIGN.CENTER)
        r0 += n
    foot = s.shapes.add_textbox(Inches(0.1), Inches(6.95), Inches(13), Inches(0.4)).text_frame
    fr = foot.paragraphs[0].add_run()
    summ = sc.get("summary") or {}
    fr.text = (f"¹ The Board retains full discretion to amend the KPIs and/or {fy} outcome for material events during "
               f"the year.   Status index {summ.get('status_index_pct', '–')}%   ·   {sc['period']['label']}   ·   "
               f"generated {date.today():%d %b %Y} from the Lochard Board Portal")
    fr.font.size, fr.font.color.rgb, fr.font.italic = Pt(9), GREY, True
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


@router.get("/export/{fy}/{period}.pptx")
def export_pptx(fy: str, period: str, u: auth.User = Depends(me_dep)):
    data = build_pptx(load_scorecard(u, fy, period))
    return StreamingResponse(io.BytesIO(data), headers={"Content-Disposition": f'attachment; filename="Lochard_Scorecard_{period}.pptx"'},
                             media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
