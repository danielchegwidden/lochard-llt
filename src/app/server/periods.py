"""Reporting periods for Leadership Insights and the board pack.

A period is a grain plus an anchor month (the reporting month). Lochard's financial year runs July to June
(FY2027 = Jul-26 .. Jun-27), so quarters are Q1 Jul–Sep, Q2 Oct–Dec, Q3 Jan–Mar, Q4 Apr–Jun.
  month    the anchor month
  quarter  FY quarter containing the anchor, to the anchor month (quarter to date when the quarter is still open)
  fytd     1 July to the end of the anchor month
  r12      the 12 months ending with the anchor month
Comparisons use the prior corresponding period (same months, one year earlier).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

GRAINS = ("month", "quarter", "fytd", "r12")
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def month_add(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def month_end(d: date) -> date:
    return month_add(date(d.year, d.month, 1), 1) - timedelta(days=1)


def fy_of(d: date) -> int:
    return d.year + 1 if d.month >= 7 else d.year


def fy_start(fy: int) -> date:
    return date(fy - 1, 7, 1)


def fy_quarter(d: date) -> int:
    return (d.month - 7) % 12 // 3 + 1


def _mon(d: date) -> str:
    return f"{MON[d.month - 1]} {d.year}"


@dataclass(frozen=True)
class Period:
    grain: str
    anchor: date                    # first day of the anchor (reporting) month

    @staticmethod
    def parse(grain: str | None, anchor: str | None, default_anchor: date) -> "Period":
        g = grain if grain in GRAINS else "fytd"
        try:
            y, m = (int(x) for x in (anchor or "")[:7].split("-"))
            a = date(y, m, 1)
        except ValueError:
            a = default_anchor
        return Period(g, a)

    @property
    def start(self) -> date:
        a = self.anchor
        if self.grain == "quarter":
            return month_add(fy_start(fy_of(a)), (fy_quarter(a) - 1) * 3)
        if self.grain == "fytd":
            return fy_start(fy_of(a))
        if self.grain == "r12":
            return month_add(a, -11)
        return a

    @property
    def end(self) -> date:
        return month_end(self.anchor)

    @property
    def months(self) -> int:
        return (self.anchor.year - self.start.year) * 12 + self.anchor.month - self.start.month + 1

    @property
    def fy(self) -> str:
        return f"FY{fy_of(self.anchor)}"

    @property
    def fy_short(self) -> str:
        return f"FY{fy_of(self.anchor) % 100:02d}"

    @property
    def month_key(self) -> str:
        """Commentary is kept per reporting month, whatever grain is on screen."""
        return f"M:{self.anchor:%Y-%m}"

    @property
    def key(self) -> str:
        return f"{self.grain}:{self.anchor:%Y-%m}"

    @property
    def label(self) -> str:
        a = self.anchor
        if self.grain == "quarter":
            q_end = month_add(self.start, 2)
            full = f"Q{fy_quarter(a)} {self.fy_short}"
            span = f"{MON[self.start.month - 1]}–{MON[q_end.month - 1]} {q_end.year}"
            return f"{full} ({span})" if a >= q_end else f"{full} to {_mon(a)}"
        if self.grain == "fytd":
            return f"{self.fy_short} full year" if a.month == 6 else f"{self.fy_short} YTD to {_mon(a)}"
        if self.grain == "r12":
            return f"12 months to {_mon(a)}"
        return _mon(a)

    @property
    def compare_label(self) -> str:
        return f"vs {self.pcp().label}"

    def pcp(self) -> "Period":
        return Period(self.grain, month_add(self.anchor, -12))

    def shift(self, n: int) -> "Period":
        if self.grain == "quarter":      # last month of the quarter n steps away
            return Period(self.grain, month_add(self.start, 3 * n + 2))
        return Period(self.grain, month_add(self.anchor, n))

    def window(self, min_months: int) -> tuple[date, date]:
        """Chart window: the period itself, widened to at least `min_months` months ending at the anchor."""
        return (min(self.start, month_add(self.anchor, -(min_months - 1))), self.end)

    def params(self) -> dict:
        p = self.pcp()
        return {"s": self.start.isoformat(), "e": self.end.isoformat(), "ps": p.start.isoformat(),
                "pe": p.end.isoformat(), "fy": self.fy}

    def as_dict(self) -> dict:
        p = self.pcp()
        return {"grain": self.grain, "anchor": f"{self.anchor:%Y-%m}", "key": self.key, "month_key": self.month_key,
                "label": self.label, "start": self.start.isoformat(), "end": self.end.isoformat(),
                "months": self.months, "fy": self.fy, "compare": {"label": p.label, "start": p.start.isoformat(),
                                                                  "end": p.end.isoformat()}}
