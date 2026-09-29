"""Shared helpers: RNG, fiscal calendar, and writers that land files like a real source extract."""
from __future__ import annotations

import io
import json
import os
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from config import SEED

AEST = timezone(timedelta(hours=10))
RNG = np.random.default_rng(SEED)


def rng(offset: int = 0) -> np.random.Generator:
    """Independent, reproducible stream per generator."""
    return np.random.default_rng(SEED + offset)


# ------------------------------------------------------------------ fiscal calendar (Jul–Jun)
def fy_of(d: date) -> int:
    return d.year + 1 if d.month >= 7 else d.year


def fy_start(fy: int) -> date:
    return date(fy - 1, 7, 1)


def fy_months(fy: int) -> list[date]:
    """First-of-month dates Jul..Jun for a fiscal year."""
    s = fy_start(fy)
    return [date(s.year + (s.month + i - 1) // 12, (s.month + i - 1) % 12 + 1, 1) for i in range(12)]


def month_end(d: date) -> date:
    nxt = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def date_key(d: date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def business_days(start: date, end: date) -> list[date]:
    days = pd.bdate_range(start, end)
    return [x.date() for x in days]


def ts(d: date | datetime, hour: int = 6, minute: int = 5) -> str:
    if isinstance(d, datetime):
        return d.astimezone(AEST).isoformat(timespec="milliseconds")
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=AEST).isoformat(timespec="milliseconds")


# ------------------------------------------------------------------ writers
class Lander:
    """Writes files into a landing root (local folder or /Volumes/<cat>/<schema>/raw)."""

    def __init__(self, root: str):
        self.root = root.rstrip("/")
        self.counts: dict[str, int] = {}

    def _path(self, rel: str) -> str:
        p = f"{self.root}/{rel}"
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def _count(self, rel: str, n: int):
        key = rel.split("/")[0] + "/" + rel.split("/")[1]
        self.counts[key] = self.counts.get(key, 0) + n

    def jsonl(self, rel: str, df: pd.DataFrame):
        p = self._path(rel)
        df.to_json(p, orient="records", lines=True, date_format="iso", force_ascii=False)
        self._count(rel, len(df))

    def csv(self, rel: str, df: pd.DataFrame, **kw):
        p = self._path(rel)
        df.to_csv(p, index=False, **kw)
        self._count(rel, len(df))

    # UC Volumes (FUSE) don't support seek-on-write, so zip/columnar formats are built in memory first
    def parquet(self, rel: str, df: pd.DataFrame):
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        self.bytes(rel, buf.getvalue())
        self._count(rel, len(df))

    def xlsx(self, rel: str, df: pd.DataFrame, sheet: str = "Sheet1"):
        buf = io.BytesIO()
        df.to_excel(buf, index=False, sheet_name=sheet)
        self.bytes(rel, buf.getvalue())
        self._count(rel, len(df))

    def bytes(self, rel: str, data: bytes):
        with open(self._path(rel), "wb") as f:
            f.write(data)

    def text(self, rel: str, content: str):
        p = self._path(rel)
        with open(p, "w") as f:
            f.write(content)

    def json(self, rel: str, obj):
        p = self._path(rel)
        with open(p, "w") as f:
            json.dump(obj, f, indent=2, default=str)

    def path(self, rel: str) -> str:
        return self._path(rel)


def split_amount(total: float, n: int, g: np.random.Generator, sigma: float = 1.0) -> np.ndarray:
    """Split a total into n log-normally distributed parts that sum exactly (2 dp)."""
    if n <= 0:
        return np.array([])
    w = g.lognormal(0, sigma, n)
    parts = np.round(total * w / w.sum(), 2)
    parts[-1] = round(total - parts[:-1].sum(), 2)
    return parts


def weighted_choice(g: np.random.Generator, options: dict, n: int):
    keys = list(options.keys())
    p = np.array(list(options.values()), dtype=float)
    return g.choice(keys, size=n, p=p / p.sum())
