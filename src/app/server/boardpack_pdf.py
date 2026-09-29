"""Board pack PDF – a Lochard-branded, landscape A4 pack rendered (reportlab) from a finalised snapshot.

Page 1 is the cover and agenda, then one page per included slide (key numbers, a chart and the approved commentary;
long commentary continues on a following page), and a closing document-control page. Every page carries the
Board-in-confidence footer, the version and page numbers.
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

from reportlab.graphics import renderPDF
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Frame, KeepInFrame, Paragraph, Table, TableStyle

W, H = landscape(A4)
MX = 32                                   # side margin
TOP = H - 92                              # top of the content area (below header + sub line)
BOTTOM = 44                               # bottom of the content area (above footer)
CRIMSON, ORANGE, GREY, PINK = HexColor("#A3194E"), HexColor("#F47525"), HexColor("#565150"), HexColor("#F3E3E9")
TEXT, MUTED, LINE, PANEL = HexColor("#1E1E1E"), HexColor("#7A7372"), HexColor("#E4DEDC"), HexColor("#FBF6F8")
GOOD, BAD = HexColor("#2E7D32"), HexColor("#B3261E")
STATUS_FILL = {"ON_TRACK": HexColor("#A6E07C"), "AT_RISK": HexColor("#FFD966"), "OFF_TRACK": HexColor("#F28B82"),
               "COMPLETE": HexColor("#9DC3E6"), None: HexColor("#E6E1DF")}
ROLE = {"LLT": "Leader", "KPI_OWNER": "Manager / Analyst", "BOARD": "Board director", "ADMIN": "Administrator"}
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ------------------------------------------------------------------------------------------------ text helpers
_MAP = {"−": "-", "≤": "<=", "≥": ">=", "→": "->", "←": "<-", "✨": "", "✦": "", "Δ": "change ", "≈": "~",
        " ": " ", " ": " ", " ": " "}


def clean(s) -> str:
    """Standard PDF fonts cover Windows-1252; map or drop anything else (emoji, maths symbols)."""
    s = str(s if s is not None else "")
    for a, b in _MAP.items():
        s = s.replace(a, b)
    return s.encode("cp1252", "ignore").decode("cp1252")


def _inline(s: str) -> str:
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escape(clean(s)))


def style(size=9.5, color=TEXT, font="Helvetica", leading=None, after=None, align=0) -> ParagraphStyle:
    return ParagraphStyle(f"s{size}{font}", fontName=font, fontSize=size, leading=leading or size * 1.36,
                          textColor=color, spaceAfter=size * 0.5 if after is None else after, alignment=align)


def P(text, st: ParagraphStyle) -> Paragraph:
    return Paragraph(_inline(text).replace("\n", "<br/>"), st)


def paras(text: str, size: float, color=TEXT) -> list:
    """Commentary text -> paragraphs; '- ' / '1. ' lines become bullets."""
    st, out = style(size, color), []
    bl = ParagraphStyle("bl", parent=st, leftIndent=11, bulletIndent=0, spaceAfter=size * 0.3)
    for block in re.split(r"\n\s*\n", clean(text).strip()):
        lines = [x for x in block.split("\n") if x.strip()]
        if lines and all(re.match(r"^\s*([-*•]|\d+[.)])\s+", x) for x in lines):
            for x in lines:
                m = re.match(r"^\s*([-*•]|\d+[.)])\s+(.*)$", x)
                out.append(Paragraph(_inline(m.group(2)), bl, bulletText="•" if m.group(1) in "-*•" else m.group(1)))
        elif lines:
            out.append(Paragraph("<br/>".join(_inline(x) for x in lines), st))
    return out


def fit(text: str, w: float, h: float, sizes=(10, 9.5, 9, 8.5, 8, 7.5), color=TEXT) -> tuple[list, bool]:
    for s in sizes:
        ps = paras(text, s, color)
        if sum(p.wrap(w, h)[1] + p.getSpaceAfter() for p in ps) <= h:
            return ps, True
    return paras(text, sizes[-1], color), False


def flow(c, ps: list, x: float, y: float, w: float, h: float) -> list:
    """Draw paragraphs into a frame (bottom-left x, y); returns what did not fit."""
    f = Frame(x, y, w, h, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0)
    rest = list(ps)
    while rest:
        if f.add(rest[0], c):
            rest.pop(0)
            continue
        parts = f.split(rest[0], c)
        if len(parts) >= 2 and f.add(parts[0], c):
            rest = list(parts[1:]) + rest[1:]
        break
    return rest


def top_draw(c, fl: list, x: float, ytop: float, w: float, h: float):
    """Draw flowables top-aligned in a box, shrinking them if they do not fit."""
    k = KeepInFrame(w, h, fl, mode="shrink")
    _, kh = k.wrapOn(c, w, h)
    k.drawOn(c, x, ytop - kh)


def when(iso: str | None, with_time=False) -> str:
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return str(iso)[:10]
    if d.tzinfo:
        try:
            from zoneinfo import ZoneInfo
            d = d.astimezone(ZoneInfo("Australia/Melbourne"))
            tz = d.tzname() or "AEST"
        except Exception:  # noqa: BLE001 – no tz database: fixed AEST
            d, tz = d.astimezone(timezone(timedelta(hours=10))), "AEST"
    else:
        tz = ""
    s = f"{d.day} {MON[d.month - 1]} {d.year}"
    return f"{s}, {d:%H:%M} {tz}".rstrip() if with_time else s


# ------------------------------------------------------------------------------------------------ charts
def _xkey(v) -> str:
    return str(v)[:10] if v is not None else ""


def _fmt_x(k: str, kind: str, label: str | None) -> str:
    if kind == "cat":
        return label or k
    if kind == "doy":
        d = datetime(2021, 1, 1) + timedelta(days=int(float(k)) - 1)
        return MON[d.month - 1]
    try:
        y, m, d = (int(p) for p in k[:10].split("-"))
    except ValueError:
        return k
    return f"{d} {MON[m - 1]}" if kind == "week" else f"{MON[m - 1]} {str(y)[2:]}"


def _fmt_y(v: float, kind: str) -> str:
    a, s = abs(v), "-" if v < 0 else ""
    if kind == "money":
        if a >= 1e9:
            return f"{s}${a / 1e9:.1f}B"
        if a >= 1e6:
            return f"{s}${a / 1e6:.0f}M" if a >= 1e7 or float(a / 1e6).is_integer() else f"{s}${a / 1e6:.1f}M"
        if a >= 1e3:
            return f"{s}${a / 1e3:.0f}K"
        return f"{s}${a:.0f}"
    if kind == "pct":
        return f"{v * 100:.0f}%"
    if kind == "count":
        return f"{v:,.0f}"
    if kind == "pj":
        return f"{v:.0f}" if a >= 10 or float(v).is_integer() else f"{v:.1f}"
    return f"{v:,.1f}"


def chart_drawing(ch: dict, w: float, h: float) -> Drawing | None:
    rows = ch.get("rows") or []
    if not rows:
        return None
    keys = {_xkey(r["x"]) for r in rows}
    numeric = all(re.match(r"^-?\d+(\.\d+)?$", k) for k in keys)
    xs = sorted(keys, key=(lambda k: float(k)) if numeric else None)
    labels = {}
    for r in rows:
        labels.setdefault(_xkey(r["x"]), r.get("label"))
    series = list(dict.fromkeys(r["series"] for r in rows))
    if all(re.match(r"^\d{4}$", s) for s in series):
        series.sort()
    data = {s: {} for s in series}
    for r in rows:
        if r.get("y") is not None:
            data[r["series"]][_xkey(r["x"])] = float(r["y"])
    palette = [ORANGE, HexColor("#52B2E5"), CRIMSON, GREY, HexColor("#FFC000")]
    cols = {s: HexColor(ch.get("colors", {}).get(s)) if ch.get("colors", {}).get(s) else palette[i % 5]
            for i, s in enumerate(series)}
    d = Drawing(w, h)
    legend_h = 14 if len(series) > 1 else 0
    if legend_h:                                   # legend above the plot, like the web chart
        lx = 44
        for s in series:
            if s in ch.get("dashed", []):
                d.add(Line(lx, h - 6, lx + 14, h - 6, strokeColor=cols[s], strokeWidth=1.8, strokeDashArray=(3, 2)))
            else:
                d.add(Rect(lx, h - 7.5, 14, 3, fillColor=cols[s], strokeColor=None))
            d.add(String(lx + 18, h - 9, clean(s), fontName="Helvetica", fontSize=7.5, fillColor=GREY))
            lx += 26 + len(s) * 4.2
    vals = [v for s in series for v in data[s].values()]
    lo, hi = min(vals), max(vals)
    c = VerticalBarChart() if ch.get("kind") == "bar" else HorizontalLineChart()
    c.x, c.y, c.width, c.height = 44, 22, w - 54, h - 30 - legend_h
    c.data = [[data[s].get(k) for k in xs] for s in series]
    step = max(1, -(-len(xs) // max(2, int(c.width // 58))))
    c.categoryAxis.categoryNames = [_fmt_x(k, ch.get("x", "cat"), labels.get(k)) if i % step == 0 else ""
                                    for i, k in enumerate(xs)]
    c.categoryAxis.labels.fontName, c.categoryAxis.labels.fontSize = "Helvetica", 7
    c.categoryAxis.labels.fillColor = MUTED
    c.categoryAxis.strokeColor = LINE
    c.categoryAxis.tickDown = 0
    va = c.valueAxis
    va.labels.fontName, va.labels.fontSize, va.labels.fillColor = "Helvetica", 7, MUTED
    va.strokeColor = None
    va.visibleGrid, va.gridStrokeColor, va.gridStrokeWidth = 1, HexColor("#EEE9E8"), 0.6
    va.labelTextFormat = lambda v, k=ch.get("y", "num"): _fmt_y(v, k)
    if ch.get("zero", True):
        va.valueMin = min(0, lo)
        va.valueMax = max(0, hi) * 1.05 or 1
    else:
        pad = (hi - lo) * 0.15 or abs(hi) * 0.1 or 1
        va.valueMin, va.valueMax = lo - pad, hi + pad
    if isinstance(c, VerticalBarChart):
        c.barSpacing, c.groupSpacing = 1, 6
        for i, s in enumerate(series):
            c.bars[i].fillColor, c.bars[i].strokeColor = cols[s], None
    else:
        c.joinedLines = 1
        for i, s in enumerate(series):
            c.lines[i].strokeColor, c.lines[i].strokeWidth = cols[s], 1.8
            if s in ch.get("dashed", []):
                c.lines[i].strokeDashArray = (4, 3)
    d.add(c)
    return d


# ------------------------------------------------------------------------------------------------ canvas with deferred footers
class _Canvas(canvas.Canvas):
    def __init__(self, *a, footer=None, **k):
        super().__init__(*a, **k)
        self._pages: list[dict] = []
        self._footer = footer
        self.page_kind = "slide"

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()
        self.page_kind = "slide"

    def save(self):
        n = len(self._pages)
        for i, st in enumerate(self._pages):
            self.__dict__.update(st)
            self._footer(self, i + 1, n)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)


# ------------------------------------------------------------------------------------------------ the pack
class _Pack:
    def __init__(self, snap: dict, pages: dict | None):
        self.s, self.L, self.D = snap, snap["period"], snap.get("data") or {}
        self.pages = pages or {}
        self.page_of: dict[str, int] = {}
        self.buf = io.BytesIO()
        self.c = _Canvas(self.buf, pagesize=(W, H), footer=self.footer)
        v = snap.get("version")
        self.c.setTitle(clean(f"Lochard Energy board pack – {self.L['month_long']} (version {v})"))
        self.c.setAuthor("Lochard Energy")
        self.c.setSubject("Board-in-confidence")
        # the issued pack numbers its slides in order (excluded slides leave no gaps)
        self.included = [{**sl, "no": i + 1} for i, sl in enumerate(x for x in snap["slides"] if x["included"])]

    # --- chrome
    def footer(self, c, n: int, total: int):
        if c.page_kind == "cover":
            return
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.line(MX, 30, W - MX, 30)
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(CRIMSON)
        c.drawString(MX, 18, "BOARD-IN-CONFIDENCE")
        f = self.s["finalised"]
        c.setFont("Helvetica", 7.5)
        c.setFillColor(MUTED)
        c.drawString(MX + 92, 18, clean(f"Lochard Energy board pack – {self.L['month_long']}   ·   Version "
                                        f"{self.s['version']} (final)   ·   finalised {when(f['at'])} by {f['name']}"))
        c.drawRightString(W - MX, 18, f"Page {n} of {total}")

    def header(self, no: int | None, title: str, owner: str | None = None, sub: str | None = None):
        c = self.c
        c.setFillColor(CRIMSON)
        c.rect(0, H - 58, W, 58, fill=1, stroke=0)
        c.setFillColor(ORANGE)
        c.rect(0, H - 61, W, 3, fill=1, stroke=0)
        x = MX
        if no:
            c.setFillColor(white)
            c.roundRect(x, H - 42, 26, 22, 4, fill=1, stroke=0)
            c.setFillColor(CRIMSON)
            c.setFont("Helvetica-Bold", 11)
            c.drawCentredString(x + 13, H - 35, f"{no:02d}")
            x += 36
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 19)
        c.drawString(x, H - 38, clean(title))
        c.setFont("Helvetica", 8.5)
        c.setFillColor(PINK)
        c.drawRightString(W - MX, H - 30, clean(f"Board pack · {self.L['month_long']}"))
        c.drawRightString(W - MX, H - 42, clean(f"{self.L['fy']} · {self.L['code']}"))
        c.setFont("Helvetica", 8)
        c.setFillColor(MUTED)
        c.drawString(MX, H - 78, clean(sub if sub is not None else
                                       f"Month: {self.L['month']} (vs {self.L['month_pcp']})   ·   Year to date: "
                                       f"{self.L['fytd_long']} (vs {self.L['fytd_pcp']})"))
        if owner:
            c.drawRightString(W - MX, H - 78, clean(f"Prepared by: {owner}"))

    def new_page(self, key: str | None = None):
        if key and key not in self.page_of:
            self.page_of[key] = self.c.getPageNumber()

    def end_page(self):
        self.c.showPage()

    # --- building blocks
    def tile(self, x, ytop, w, h, mt: dict):
        c = self.c
        c.setFillColor(white)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.7)
        c.roundRect(x, ytop - h, w, h, 5, fill=1, stroke=1)
        m, y = mt["m"], mt.get("y")
        tone_col = lambda t: "#2E7D32" if t == "good" else "#B3261E" if t == "bad" else "#7A7372"  # noqa: E731
        fl = [P(mt["label"], style(7, MUTED, "Helvetica-Bold", after=1.5)),
              P(m["t"], style(15, GREY, "Helvetica-Bold", leading=17, after=1))]
        if m.get("d"):
            fl.append(Paragraph(f'<font color="{tone_col(m["d"].get("tone") or mt.get("tone"))}">'
                                f'{_inline(m["d"]["text"])}</font> {_inline("vs " + m["vs"])}', style(7, MUTED, after=1)))
        elif m.get("p"):
            fl.append(P(f"{m['vs']}: {m['p']}", style(7, MUTED, after=1)))
        if y:
            t = f"<b>{_inline(y['label'])}</b> {_inline(y['t'])}"
            if y.get("d"):
                t += f' · <font color="{tone_col(y["d"].get("tone") or mt.get("tone"))}">{_inline(y["d"]["text"])}</font>'
            fl.append(Paragraph(t, style(7, GREY, after=1)))
        if mt.get("note"):
            fl.append(P(mt["note"], style(6.5, MUTED, "Helvetica-Oblique", after=0)))
        top_draw(c, fl, x + 7, ytop - 6, w - 14, h - 11)

    def tiles(self, metrics: list, x, ytop, w, cols=None, h=74, gap=8) -> float:
        n = len(metrics)
        cols = cols or (3 if n in (5, 6) or n > 6 else 2 if n == 4 else max(1, n))
        tw = (w - gap * (cols - 1)) / cols
        rows = -(-n // cols)
        for i, mt in enumerate(metrics):
            r, cc = divmod(i, cols)
            self.tile(x + cc * (tw + gap), ytop - r * (h + gap), tw, h, mt)
        return ytop - rows * (h + gap) + gap

    def chart(self, ch: dict | None, x, ytop, w, h):
        if not ch:
            return
        c = self.c
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(GREY)
        c.drawString(x, ytop - 10, clean(ch.get("title", "")))
        tw = c.stringWidth(clean(ch.get("title", "")), "Helvetica-Bold", 9)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(MUTED)
        c.drawString(x + tw + 6, ytop - 10, clean(ch.get("sub", "")))
        d = chart_drawing(ch, w, h - 16)
        if d is None:
            c.drawString(x, ytop - 40, "No data for this period.")
            return
        renderPDF.draw(d, c, x, ytop - h)

    def commentary_box(self, slide: dict, x, y, w, h, title: str | None = None, sizes=(10, 9.5, 9, 8.5, 8, 7.5)) -> list:
        """Approved commentary in a panel; returns paragraphs that did not fit (for a continuation page)."""
        c = self.c
        c.setFillColor(PANEL)
        c.setStrokeColor(HexColor("#EAD3DC"))
        c.roundRect(x, y, w, h, 6, fill=1, stroke=1)
        c.setFillColor(CRIMSON)
        c.rect(x, y + h - 3, w, 3, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 10.5)
        c.drawString(x + 12, y + h - 20, clean(title or slide.get("commentary_title") or "Commentary"))
        cm = slide.get("commentary")
        pad = 12
        if not cm or not (cm.get("body") or "").strip():
            c.setFont("Helvetica-Oblique", 9)
            c.setFillColor(MUTED)
            c.drawString(x + pad, y + h - 40, "Not approved when the pack was finalised – see document control.")
            return []
        meta = f"{cm.get('author_name') or ''}" + (f" ({ROLE.get(cm.get('author_role'), cm.get('author_role'))})"
                                                   if cm.get("author_role") else "")
        if cm.get("reviewer_name"):
            meta += f" · approved by {cm['reviewer_name']} {when(cm.get('reviewed_at'))}"
        if cm.get("ai_assisted"):
            meta += " · drafted with AI assistance"
        mp = P(meta, style(7, MUTED, after=0))
        _, mh = mp.wrap(w - 2 * pad, 40)
        mp.drawOn(c, x + pad, y + 8)
        ps, _ = fit(cm["body"], w - 2 * pad, h - 44 - mh, sizes)
        return flow(c, ps, x + pad, y + 14 + mh, w - 2 * pad, h - 44 - mh)

    def continuation(self, slide: dict, rest: list, title: str):
        while rest:
            self.end_page()
            self.header(slide["no"], f"{title} (continued)", slide.get("owner"), sub="")
            rest = flow(self.c, rest, MX, BOTTOM, W - 2 * MX, TOP - BOTTOM - 8)

    def two_col(self) -> tuple[float, float, float]:
        lw = (W - 2 * MX) * 0.62
        return lw, MX + lw + 16, W - 2 * MX - lw - 16

    # --- pages
    def cover(self):
        c, L, s = self.c, self.L, self.s
        c.page_kind = "cover"
        self.new_page("cover")
        pw = 300
        c.setFillColor(CRIMSON)
        c.rect(0, 0, pw, H, fill=1, stroke=0)
        c.setFillColor(ORANGE)
        c.rect(pw, 0, 5, H, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 30)
        c.drawString(40, H - 80, "lochard")
        c.setFillColor(PINK)
        c.setFont("Helvetica", 30)
        c.drawString(40 + c.stringWidth("lochard", "Helvetica-Bold", 30) + 6, H - 80, "energy")
        c.setFillColor(ORANGE)
        c.rect(40, H - 96, 46, 3, fill=1, stroke=0)
        c.setFillColor(PINK)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, H - 190, "BOARD PACK")
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 30)
        c.drawString(40, H - 226, clean(L["month_long"]))
        c.setFont("Helvetica", 11)
        c.setFillColor(PINK)
        c.drawString(40, H - 246, clean(f"{L['fy']} reporting period · {L['code']}"))
        if L.get("board_meeting"):
            c.drawString(40, H - 262, clean(f"Board meeting {when(L['board_meeting'])}"))
        f = s["finalised"]
        c.setFillColor(HexColor("#8C1543"))
        c.roundRect(40, 92, pw - 80, 92, 6, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(54, 162, f"Version {s['version']} · Final")
        c.setFont("Helvetica", 8.5)
        c.setFillColor(PINK)
        c.drawString(54, 146, clean(f"Finalised {when(f['at'], True)}"))
        c.drawString(54, 133, clean(f"by {f['name']} ({ROLE.get(f['role'], f['role'])})"))
        rd = s.get("readiness") or {}
        c.drawString(54, 120, clean(f"{rd.get('ready', 0)} of {rd.get('total', 0)} slides ready at finalisation"))
        if s.get("override_reason"):
            c.drawString(54, 107, "Finalised with open items – see document control")
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(40, 56, "BOARD-IN-CONFIDENCE")
        c.setFont("Helvetica", 7.5)
        c.setFillColor(PINK)
        c.drawString(40, 43, "Lochard Energy · Iona Gas Storage Facility, Victoria")
        c.drawString(40, 32, "Not for distribution beyond the Board and the Lochard Leadership Team.")
        # agenda
        x0, x1 = pw + 44, W - 44
        c.setFillColor(CRIMSON)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(x0, H - 72, "Agenda")
        y = H - 104
        items = [sl for sl in self.included if sl["key"] != "cover"] + [{"key": "_control", "no": None,
                                                                        "title": "Document control"}]
        rh = 21 if len(items) <= 12 else 17
        for sl in items:
            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(ORANGE)
            c.drawString(x0, y, f"{sl['no']:02d}" if sl.get("no") else "")
            c.setFillColor(TEXT)
            c.setFont("Helvetica", 10.5)
            c.drawString(x0 + 28, y, clean(sl["title"]))
            pg = self.pages.get(sl["key"])
            if pg:
                c.setFillColor(MUTED)
                c.drawRightString(x1, y, str(pg))
            c.setStrokeColor(LINE)
            c.setLineWidth(0.5)
            c.line(x0, y - 7, x1, y - 7)
            y -= rh
        cover = next((sl for sl in self.included if sl["key"] == "cover"), None)
        if cover and cover.get("commentary") and y - 40 > 60:
            box_h = y - 40 - 40
            rest = self.commentary_box(cover, x0, 40, x1 - x0, box_h, f"Covering note – {cover.get('owner') or ''}",
                                       sizes=(9.5, 9, 8.5, 8, 7.5))
            if rest:
                self.continuation(cover, rest, "Covering note")
        self.end_page()

    def metrics_page(self, sl: dict, extra=None):
        d = self.D.get(sl["key"]) or {}
        self.new_page(sl["key"])
        self.header(sl["no"], sl["title"], sl.get("owner"))
        lw, rx, rw = self.two_col()
        y = self.tiles(d.get("metrics", []), MX, TOP, lw)
        bottom = BOTTOM
        if extra:
            bottom = extra(MX, y, lw)
        self.chart(d.get("chart"), MX, y - 10, lw, (y - 10) - bottom)
        if d.get("partial"):
            self.c.setFont("Helvetica-Oblique", 7)
            self.c.setFillColor(MUTED)
            self.c.drawString(MX, BOTTOM - 8, "Some figures were unavailable when the pack was finalised.")
        rest = self.commentary_box(sl, rx, BOTTOM, rw, TOP - BOTTOM)
        self.continuation(sl, rest, sl["title"])
        self.end_page()

    def finance_extra(self, x, ytop, w) -> float:
        t = (self.D.get("finance") or {}).get("table") or {}
        rows = t.get("rows") or []
        if not rows:
            return BOTTOM
        st, sb = style(7, TEXT, after=0), style(7, white, "Helvetica-Bold", after=0)
        data = [[P("Team", sb), P("Actual", sb), P("Budget", sb), P("Variance", sb), P(f"{self.L['fy']} budget", sb),
                 P("Outlook", sb)]]
        for r in rows:
            col = "#2E7D32" if r.get("tone") == "good" else "#B3261E" if r.get("tone") == "bad" else "#1E1E1E"
            data.append([P(r["team"], st), P(r["actual"], st), P(r["budget"], st),
                         Paragraph(f'<font color="{col}">{_inline(r["variance"])}</font>', st), P(r["fy_budget"], st),
                         P(r["fy_yeo"], st)])
        tb = Table(data, colWidths=[w * 0.34] + [w * 0.132] * 5)
        tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), GREY), ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
                                ("TOPPADDING", (0, 0), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6)]))
        _, th = tb.wrapOn(self.c, w, 200)
        self.c.setFont("Helvetica-Bold", 9)
        self.c.setFillColor(GREY)
        self.c.drawString(x, BOTTOM + th + 5, clean(t.get("title", "")))
        tb.drawOn(self.c, x, BOTTOM)
        return BOTTOM + th + 22

    def hugs_extra(self, x, ytop, w) -> float:
        k = (self.D.get("hugs") or {}).get("kpi")
        if not k:
            return BOTTOM
        txt = f"<b>Board scorecard KPI {_inline(k['code'])} {_inline(k['name'])}: {_inline(k['status_label'])}.</b> "
        if k.get("update"):
            txt += _inline(k["update"][:420])
        p = Paragraph(txt, style(7.5, TEXT, after=0))
        _, ph = p.wrap(w - 16, 80)
        ph = min(ph, 70)
        self.c.setFillColor(STATUS_FILL.get(k.get("status"), STATUS_FILL[None]))
        self.c.roundRect(x, BOTTOM, 6, ph + 10, 2, fill=1, stroke=0)
        flow(self.c, [p], x + 14, BOTTOM + 5, w - 16, ph)
        return BOTTOM + ph + 18

    def exec_page(self, sl: dict):
        d = self.D.get("exec_summary") or {}
        self.new_page(sl["key"])
        self.header(sl["no"], sl["title"], sl.get("owner"))
        c = self.c
        heads = d.get("headlines", [])
        gap, cols, th = 8, 4, 58
        tw = (W - 2 * MX - gap * (cols - 1)) / cols
        for i, hd in enumerate(heads):
            r, cc = divmod(i, cols)
            x, yt = MX + cc * (tw + gap), TOP - r * (th + gap)
            c.setFillColor(white)
            c.setStrokeColor(LINE)
            c.roundRect(x, yt - th, tw, th, 5, fill=1, stroke=1)
            col = "#2E7D32" if hd.get("tone") == "good" else "#B3261E" if hd.get("tone") == "bad" else "#7A7372"
            fl = [P(hd["label"], style(7, MUTED, "Helvetica-Bold", after=1.5)),
                  P(hd["value"], style(15, GREY, "Helvetica-Bold", leading=17, after=1)),
                  Paragraph(f'<font color="{col}">{_inline(hd.get("sub") or "")}</font>', style(7, MUTED, after=0))]
            top_draw(c, fl, x + 7, yt - 6, tw - 14, th - 11)
        rows = -(-len(heads) // cols)
        y = TOP - rows * (th + gap) - 6
        lw2 = (W - 2 * MX) * 0.5
        rx, rw = MX + lw2 + 16, W - 2 * MX - lw2 - 16
        # scorecard + leadership commentary (left)
        sc = d.get("scorecard") or {}
        fl = [P("Board scorecard", style(9.5, CRIMSON, "Helvetica-Bold", after=2)),
              P(f"Status index {sc.get('status_index') or '–'} · weighted board score {sc.get('board_score') or '–'} · "
                f"{sc.get('at_risk', 0)} at risk · {sc.get('off_track', 0)} off track of {sc.get('kpis', 0)} KPIs"
                + (f" · {d.get('scorecard_state')}" if d.get("scorecard_state") else ""), style(8, TEXT, after=3))]
        for a in d.get("attention", [])[:5]:
            fl.append(P(f"• KPI {a['code']} {a['name']}: {a['status_label']}", style(8, TEXT, after=1)))
        dc = d.get("domain_commentary") or []
        head = style(9.5, CRIMSON, "Helvetica-Bold", after=2)
        head.spaceBefore = 8
        fl.append(P("From the leadership team", head))
        if not dc:
            fl.append(P("No approved management commentary for the month.", style(8, MUTED, "Helvetica-Oblique")))
        for cm in dc:
            body = cm["body"] if len(cm["body"]) < 420 else cm["body"][:400].rsplit(" ", 1)[0] + "…"
            fl.append(Paragraph(f"<b>{_inline(cm['title'])}.</b> {_inline(body)}", style(8, TEXT, after=3)))
        top_draw(c, fl, MX, y - 4, lw2, y - 4 - BOTTOM)
        rest = self.commentary_box(sl, rx, BOTTOM, rw, y - BOTTOM)
        self.continuation(sl, rest, sl["title"])
        self.end_page()

    def scorecard_page(self, sl: dict):
        d = self.D.get("scorecard") or {}
        self.new_page(sl["key"])
        self.header(sl["no"], sl["title"], sl.get("owner"),
                    sub=f"{self.L['label']} reporting period · {d.get('state_label') or ''}")
        c = self.c
        s = d.get("summary") or {}
        if not d.get("available"):
            c.setFont("Helvetica-Oblique", 10)
            c.setFillColor(MUTED)
            c.drawString(MX, TOP - 20, "The scorecard was not available when the pack was finalised.")
        else:
            chips = [("Status index", s.get("status_index") or "–"), ("Weighted board score", s.get("board_score") or "–"),
                     ("KPIs at risk", str(s.get("at_risk", 0))), ("KPIs off track", str(s.get("off_track", 0))),
                     ("KPIs reported", f"{s.get('reported', 0)} of {s.get('kpis', 0)}")]
            cw = 120
            for i, (lab, val) in enumerate(chips):
                x = MX + i * (cw + 8)
                c.setFillColor(white)
                c.setStrokeColor(LINE)
                c.roundRect(x, TOP - 36, cw, 36, 5, fill=1, stroke=1)
                c.setFont("Helvetica-Bold", 6.5)
                c.setFillColor(MUTED)
                c.drawString(x + 8, TOP - 12, lab.upper())
                c.setFont("Helvetica-Bold", 13)
                c.setFillColor(GREY)
                c.drawString(x + 8, TOP - 29, clean(val))
            hd, cs = style(7.5, white, "Helvetica-Bold", after=0), style(7, TEXT, after=0)
            data = [[P("Pillar", hd), P("#", hd), P("KPI", hd), P("Owner", hd), P("Weight", hd), P("Status", hd),
                     P("Board", hd), P("Owner update", hd)]]
            ts = [("BACKGROUND", (0, 0), (-1, 0), CRIMSON), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                  ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#D8D2D0")), ("TOPPADDING", (0, 0), (-1, -1), 2),
                  ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
            r = 1
            for p in d.get("pillars", []):
                n = len(p["kpis"])
                for j, k in enumerate(p["kpis"]):
                    upd = (k.get("update") or "")
                    upd = upd if len(upd) <= 230 else upd[:220].rsplit(" ", 1)[0] + "…"
                    data.append([P(p["name"], style(7.5, TEXT, "Helvetica-Bold", after=0, align=1)) if j == 0 else "",
                                 P(k["code"], style(7.5, CRIMSON, "Helvetica-Bold", after=0, align=1)),
                                 P(k["name"], style(7.5, CRIMSON, "Helvetica-Bold", after=0)),
                                 P(k["owner"], style(7, TEXT, after=0, align=1)),
                                 P(k["weight"], style(7, TEXT, after=0, align=1)),
                                 P(k["status_label"], style(7, TEXT, "Helvetica-Bold", after=0, align=1)),
                                 P(k.get("board") or "–", style(7, TEXT, after=0, align=1)), P(upd, cs)])
                    ts.append(("BACKGROUND", (5, r + j), (5, r + j), STATUS_FILL.get(k.get("status"), STATUS_FILL[None])))
                    ts += [("BACKGROUND", (1, r + j), (1, r + j), PINK)]
                ts += [("SPAN", (0, r), (0, r + n - 1)), ("BACKGROUND", (0, r), (0, r + n - 1), PINK)]
                r += n
            tw = W - 2 * MX
            tb = Table(data, colWidths=[tw * x for x in (0.1, 0.035, 0.15, 0.06, 0.055, 0.075, 0.055, 0.47)])
            tb.setStyle(TableStyle(ts))
            _, th = tb.wrapOn(c, tw, TOP - 50 - BOTTOM)
            tb.drawOn(c, MX, TOP - 46 - th)
            y = TOP - 46 - th - 8
            if d.get("footnote"):
                c.setFont("Helvetica-Oblique", 6.5)
                c.setFillColor(MUTED)
                c.drawString(MX, y, clean(f"The Board retains full discretion to amend the KPIs and/or the {self.L['fy']} "
                                          "outcome for material events during the year."))
                y -= 8
            if y - BOTTOM > 70:
                rest = self.commentary_box(sl, MX, BOTTOM, W - 2 * MX, y - 4 - BOTTOM, sizes=(9, 8.5, 8, 7.5))
                self.continuation(sl, rest, sl["title"])
                self.end_page()
                return
        self.end_page()
        self.header(sl["no"], f"{sl['title']} – commentary", sl.get("owner"), sub="")
        rest = self.commentary_box(sl, MX, BOTTOM, W - 2 * MX, TOP - BOTTOM)
        self.continuation(sl, rest, sl["title"])
        self.end_page()

    def intel_page(self, sl: dict):
        d = self.D.get("market_intel") or {}
        self.new_page(sl["key"])
        self.header(sl["no"], sl["title"], sl.get("owner"), sub=(d.get("window") or {}).get("label", ""))
        c = self.c
        lw, rx, rw = self.two_col()
        if not d.get("available") or not (d.get("briefs") or d.get("items")):
            c.setFillColor(PANEL)
            c.roundRect(MX, TOP - 90, lw, 90, 6, fill=1, stroke=0)
            c.setFont("Helvetica-Bold", 11)
            c.setFillColor(GREY)
            c.drawString(MX + 14, TOP - 34, "Market briefs not available yet" if not d.get("available")
                         else "No market briefs for these four weeks")
            c.setFont("Helvetica", 8.5)
            c.setFillColor(MUTED)
            c.drawString(MX + 14, TOP - 52, "Weekly briefs from the Market Intelligence Hub will appear here once published.")
        else:
            fl = []
            sig = d.get("signals") or {}
            if sig:
                fl.append(P("   ·   ".join(f"{k}: {v}" for k, v in sig.items()) + " (items in the four weeks)",
                            style(7.5, MUTED, after=5)))
            for b in d.get("briefs", []):
                fl.append(P(b["week_label"], style(7.5, ORANGE, "Helvetica-Bold", after=1)))
                fl.append(P(b.get("headline") or "", style(9.5, CRIMSON, "Helvetica-Bold", after=2)))
                summ = re.sub(r"[*_`#>]", "", b.get("summary") or "")
                fl.append(P(summ if len(summ) < 520 else summ[:500].rsplit(" ", 1)[0] + "…", style(8, TEXT, after=6)))
            if d.get("items"):
                fl.append(P("Most important items", style(9.5, CRIMSON, "Helvetica-Bold", after=3)))
                for it in d["items"]:
                    fl.append(Paragraph(f"<b>{_inline(it.get('title') or '')}</b> – {_inline(it.get('source') or '')}, "
                                        f"{_inline(it.get('date') or '')} · <i>{_inline(it.get('signal') or '')}</i>"
                                        + (f"<br/>{_inline(it['why'])}" if it.get("why") else ""), style(7.5, TEXT, after=3)))
            top_draw(c, fl, MX, TOP, lw, TOP - BOTTOM)
        rest = self.commentary_box(sl, rx, BOTTOM, rw, TOP - BOTTOM)
        self.continuation(sl, rest, sl["title"])
        self.end_page()

    def owner_page(self, sl: dict):
        self.new_page(sl["key"])
        self.header(sl["no"], sl["title"], sl.get("owner"), sub=f"{self.L['month_long']} board meeting papers")
        rest = self.commentary_box(sl, MX, BOTTOM, W - 2 * MX, TOP - BOTTOM, sizes=(11, 10.5, 10, 9.5, 9, 8.5))
        self.continuation(sl, rest, sl["title"])
        self.end_page()

    def control_page(self):
        s, c = self.s, self.c
        self.new_page("_control")
        self.header(None, "Document control", None, sub="")
        f, rd = s["finalised"], s.get("readiness") or {}
        k, v = style(8.5, MUTED, "Helvetica-Bold", after=0), style(8.5, TEXT, after=0)
        excluded = [sl["title"] for sl in s["slides"] if not sl["included"]]
        rows = [("Board pack", f"{self.L['month_long']} ({self.L['code']}, {self.L['fy']})"),
                ("Version", f"{s['version']} – final"),
                ("Finalised", f"{when(f['at'], True)} by {f['name']} ({ROLE.get(f['role'], f['role'])})"),
                ("Figures as at", when(s.get("data_as_at"), True)),
                ("Slides", f"{len(self.included)} included" + (f"; excluded: {', '.join(excluded)}" if excluded else "")),
                ("Readiness", f"{rd.get('ready', 0)} of {rd.get('total', 0)} included slides had approved commentary")]
        if rd.get("not_ready"):
            lab = {"IN_DRAFT": "in draft", "NOT_STARTED": "not started"}
            rows.append(("Not ready at finalisation",
                         "; ".join(f"{x['title']} ({lab.get(x['status'], x['status'])})" for x in rd["not_ready"])))
        if s.get("override_reason"):
            rows.append(("Reason for finalising", s["override_reason"]))
        hist = [h for h in s.get("history") or [] if h["version"] != s["version"]]
        if hist:
            rows.append(("Supersedes", "; ".join(
                f"version {h['version']} finalised {when(h['finalised_at'])} by {h.get('finalised_name') or ''}"
                + (f", sent {when(h['sent_at'])}" if h.get("sent_at") else "") for h in hist)))
        rows.append(("Content fingerprint", (s.get("fingerprint") or "")[:32]))
        rows.append(("Distribution", "Board-in-confidence. For the Board and the Lochard Leadership Team only. "
                                     "Commentary is included once approved by a member of the leadership team."))
        tb = Table([[P(a, k), P(b, v)] for a, b in rows], colWidths=[170, W - 2 * MX - 170])
        tb.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        _, th = tb.wrapOn(c, W - 2 * MX, TOP - BOTTOM)
        tb.drawOn(c, MX, TOP - th)
        self.end_page()

    def build(self) -> bytes:
        self.cover()
        for sl in self.included:
            k = sl["key"]
            if k == "cover":
                continue
            if k == "exec_summary":
                self.exec_page(sl)
            elif k == "scorecard":
                self.scorecard_page(sl)
            elif k == "market_intel":
                self.intel_page(sl)
            elif k in ("risks", "decisions"):
                self.owner_page(sl)
            elif k == "finance":
                self.metrics_page(sl, self.finance_extra)
            elif k == "hugs":
                self.metrics_page(sl, self.hugs_extra)
            else:
                self.metrics_page(sl)
        self.control_page()
        self.n_pages = len(self.c._pages)
        self.c.save()
        return self.buf.getvalue()


def render(snapshot: dict) -> tuple[bytes, int]:
    """Two passes: the first finds each slide's page number for the agenda on the cover."""
    first = _Pack(snapshot, None)
    first.build()
    second = _Pack(snapshot, first.page_of)
    pdf = second.build()
    return pdf, second.n_pages
