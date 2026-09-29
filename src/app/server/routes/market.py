"""Market Intelligence Hub API – weekly analyst briefs, multi-week syntheses, signals and the curated item feed.

Reads only the four lochard_semantic market views (docs/market_intelligence.md), on behalf of the viewer. Portal-side
state lives in Lakebase: analyst curation per item (pin, dismiss, note, importance override), cached multi-week
syntheses and – through the shared commentary workflow – the analyst's weekly commentary (scope 'market', subject
'brief', period 'W:YYYY-MM-DD').

What the viewer sees follows the effective app role:
  analyst  (KPI_OWNER, ADMIN)  every item, triage controls, writes the weekly commentary
  leader   (LLT)               curated feed: pinned first, dismissed hidden, analyst notes shown
  board    (BOARD, OBSERVER)   brief, approved commentary and pinned items only

Development: LOCHARD_MARKET_FIXTURE=1 serves server/fixtures/market_sample.json instead of the views.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Callable
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, config, db, llm, sql
from . import commentary
from .scorecard import _rows, me_dep

router = APIRouter(prefix="/api/market")
log = logging.getLogger("lochard.market")

MEL = ZoneInfo("Australia/Melbourne")
HORIZONS = (1, 4, 13, 26)
CONTEXT_WEEKS = 8                       # trend context shown for a single week
FIXTURE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "market_sample.json")
SIGNALS = ("Opportunity", "Threat", "Watch", "Neutral")
GROUPS = ("Lochard", "Customer", "Competitor", "Upstream supplier", "Regulator & market body", "Government & policy",
          "Industry & market")
TOPICS = ("Gas storage", "Supply & demand", "Prices & contracts", "Policy & regulation", "Projects & investment",
          "Corporate & M&A", "Operations & safety", "Energy transition")
SOURCE_TYPES = ("news", "web_research", "asx_announcement", "company_release", "regulator_release")
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
ITEM_COLS = ("item_id, published_at, published_date, week_start, title, source_name, source_type, url, content_depth, "
             "summary, why_it_matters, primary_entity, entities, entity_group, topic, signal, sentiment, importance, "
             "relevance")
BRIEF_COLS = ("week_start, week_end, headline, summary_md, developments_json, implications_json, watchlist_json, "
              "actions_json, sentiment_json, n_items, n_sources, model, tools_used, trace_id, generated_at")
ITEM_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


def _fixture_on() -> bool:
    return os.environ.get("LOCHARD_MARKET_FIXTURE") == "1"


class Unavailable(Exception):
    """The market views are missing (being built) or cannot be read."""

    def __init__(self, state: str, detail: str = ""):
        super().__init__(detail or state)
        self.state, self.detail = state, detail


def _unavailable(e: Unavailable) -> dict:
    msg = ("Market data is being prepared. The weekly brief and signals will appear here after the first collection run."
           if e.state == "preparing" else "Market data is temporarily unavailable. Please try again shortly.")
    return {"available": False, "state": e.state, "message": msg}


# ------------------------------------------------------------------------------------------------ dates & labels
def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def today() -> date:
    return datetime.now(MEL).date()


def current_week() -> date:
    return monday(today())


def _d(v: Any) -> date | None:
    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _fmt_d(d: date, year: bool = True) -> str:
    return f"{d.day} {MON[d.month - 1]}" + (f" {d.year}" if year else "")


def week_label(ws: date) -> str:
    return f"Week of {_fmt_d(ws)}"


def _range(a: date, b: date) -> str:
    if a.year != b.year:
        return f"{_fmt_d(a)} – {_fmt_d(b)}"
    if a.month != b.month:
        return f"{_fmt_d(a, False)} – {_fmt_d(b)}"
    return f"{a.day}–{b.day} {MON[b.month - 1]} {b.year}"


def window_label(ws: date, we: date, horizon: int) -> str:
    rng = _range(ws, we + timedelta(days=6))
    return f"Mon–Sun · {rng}" if horizon == 1 else f"{horizon} weeks · {rng}"


def _window(week: date, horizon: int) -> tuple[date, date]:
    return week - timedelta(weeks=horizon - 1), week


def _parse_week(week: str | None, fallback: date) -> date:
    d = _d(week) or fallback
    return min(monday(d), current_week())


def _horizon(h: int | None) -> int:
    return h if h in HORIZONS else 1


# ------------------------------------------------------------------------------------------------ value helpers
def _arr(v) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        try:
            out = json.loads(s)
            return out if isinstance(out, list) else [out]
        except ValueError:
            return [x.strip() for x in s.strip("[]").split(",") if x.strip()]
    return [v]


def _jload(v, default):
    if v is None or v == "":
        return default
    if isinstance(v, (list, dict)):
        return v
    try:
        out = json.loads(v)
        return out if isinstance(out, type(default)) else default
    except (ValueError, TypeError):
        log.warning("could not parse brief JSON column: %.80s", v)
        return default


def _f(v) -> float | None:
    try:
        return None if v is None else round(float(v), 3)
    except (TypeError, ValueError):
        return None


def _i(v) -> int | None:
    try:
        return None if v is None else int(float(v))
    except (TypeError, ValueError):
        return None


def _signal(v) -> str:
    return v if v in SIGNALS else "Neutral"


# ------------------------------------------------------------------------------------------------ small TTL cache
_cache: dict[tuple, tuple[float, Any]] = {}
_locks: dict[tuple, threading.Lock] = {}
_glock = threading.Lock()


def _cached(key: tuple, fn: Callable[[], Any], ttl: float = 120) -> Any:
    """Per-process cache; concurrent requests for the same key share one fetch. Failures are not cached."""
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    with _glock:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        val = fn()
        with _glock:
            _cache[key] = (time.time(), val)
            if len(_cache) > 300:                         # drop the oldest third (and their locks)
                for k, _ in sorted(list(_cache.items()), key=lambda kv: kv[1][0])[:100]:
                    _cache.pop(k, None)
                    if k != key:
                        _locks.pop(k, None)
        return val


# ------------------------------------------------------------------------------------------------ data sources
def _check(res: dict, what: str) -> list[dict]:
    if "error" in res:
        err = res["error"] or ""
        if "TABLE_OR_VIEW_NOT_FOUND" in err or "SCHEMA_NOT_FOUND" in err or "cannot be found" in err:
            raise Unavailable("preparing", f"{what}: {err[:160]}")
        raise Unavailable("error", f"{what}: {err[:160]}")
    return res["rows"]


def _parallel(token, queries: dict[str, tuple[str, dict | None]]) -> dict[str, dict]:
    with ThreadPoolExecutor(max_workers=max(1, len(queries))) as ex:
        futs = {k: ex.submit(sql.safe, token, q, p) for k, (q, p) in queries.items()}
        return {k: f.result() for k, f in futs.items()}


class _SqlSource:
    """The semantic views, queried as the viewer (Unity Catalog grants, row filters and masks apply)."""

    def __init__(self, token):
        self.token = token

    def run(self, queries: dict[str, tuple[str, dict | None]]) -> dict[str, list[dict]]:
        res = _parallel(self.token, queries)
        return {k: _check(v, k) for k, v in res.items()}

    @staticmethod
    def q_items(ws: date, we: date):
        return (f"SELECT {ITEM_COLS} FROM {sql.fq('v_market_intel_items')} WHERE week_start BETWEEN DATE(:ws) AND DATE(:we) "
                f"ORDER BY importance DESC, published_at DESC LIMIT 5000", {"ws": ws.isoformat(), "we": we.isoformat()})

    @staticmethod
    def q_briefs(ws: date, we: date):
        return (f"SELECT {BRIEF_COLS} FROM {sql.fq('v_market_intel_briefs')} WHERE week_start BETWEEN DATE(:ws) AND DATE(:we) "
                f"ORDER BY week_start", {"ws": ws.isoformat(), "we": we.isoformat()})

    @staticmethod
    def q_weekly(ws: date, we: date):
        return (f"""SELECT week_start, entity_group, SUM(n_items) AS n_items, SUM(n_threats) AS n_threats,
                           SUM(n_opportunities) AS n_opportunities,
                           SUM(avg_sentiment * n_items) / NULLIF(SUM(CASE WHEN avg_sentiment IS NOT NULL THEN n_items END), 0)
                             AS avg_sentiment,
                           MAX(max_importance) AS max_importance
                    FROM {sql.fq('v_market_intel_weekly')} WHERE week_start BETWEEN DATE(:ws) AND DATE(:we)
                    GROUP BY week_start, entity_group ORDER BY week_start""", {"ws": ws.isoformat(), "we": we.isoformat()})

    @staticmethod
    def q_weeks():
        return (f"""SELECT week_start, SUM(n_items) AS n_items, SUM(n_threats) AS n_threats,
                           SUM(n_opportunities) AS n_opportunities
                    FROM {sql.fq('v_market_intel_weekly')} GROUP BY week_start""", None)

    @staticmethod
    def q_brief_index():
        return (f"SELECT week_start, week_end, headline, n_items, generated_at FROM {sql.fq('v_market_intel_briefs')}", None)

    @staticmethod
    def q_entities():
        return (f"SELECT entity, entity_group, relationship, description, asx_code, website "
                f"FROM {sql.fq('v_market_intel_entities')}", None)

    @staticmethod
    def q_item(item_id: str):
        return (f"SELECT {ITEM_COLS}, excerpt, doc_path, ingested_at FROM {sql.fq('v_market_intel_items')} "
                f"WHERE item_id = :id LIMIT 1", {"id": item_id})

    @staticmethod
    def q_items_by_id(ids: list[str]):
        return (f"SELECT {ITEM_COLS} FROM {sql.fq('v_market_intel_items')} WHERE array_contains(split(:ids, ','), item_id)",
                {"ids": ",".join(ids)})


@lru_cache(maxsize=1)
def _fixture() -> dict:
    with open(FIXTURE_PATH) as f:
        return json.load(f)


class _FixtureSource:
    """Same shapes as the views, served from server/fixtures/market_sample.json (development only)."""

    def __init__(self, token=None):
        self.fx = _fixture()

    def run(self, queries: dict[str, tuple]) -> dict[str, list[dict]]:
        return {k: getattr(self, q[0])(*q[1:]) for k, q in queries.items()}

    @staticmethod
    def q_items(ws, we):
        return ("_items", ws, we)

    @staticmethod
    def q_briefs(ws, we):
        return ("_briefs", ws, we)

    @staticmethod
    def q_weekly(ws, we):
        return ("_weekly", ws, we)

    @staticmethod
    def q_weeks():
        return ("_weeks",)

    @staticmethod
    def q_brief_index():
        return ("_brief_index",)

    @staticmethod
    def q_entities():
        return ("_entities",)

    @staticmethod
    def q_item(item_id):
        return ("_item", item_id)

    @staticmethod
    def q_items_by_id(ids):
        return ("_items_by_id", ids)

    @staticmethod
    def _in(r, ws, we):
        return ws.isoformat() <= str(r["week_start"])[:10] <= we.isoformat()

    def _items(self, ws, we):
        cols = [c.strip() for c in ITEM_COLS.split(",")]
        rows = [{c: r.get(c) for c in cols} for r in self.fx["items"] if self._in(r, ws, we)]
        rows.sort(key=lambda r: r["published_at"] or "", reverse=True)
        return sorted(rows, key=lambda r: -(r["importance"] or 0))

    def _briefs(self, ws, we):
        return sorted((dict(b) for b in self.fx["briefs"] if self._in(b, ws, we)), key=lambda b: b["week_start"])

    def _weekly(self, ws, we):
        acc: dict[tuple, dict] = {}
        for r in self.fx["weekly"]:
            if not self._in(r, ws, we):
                continue
            a = acc.setdefault((r["week_start"], r["entity_group"]),
                               {"week_start": r["week_start"], "entity_group": r["entity_group"], "n_items": 0,
                                "n_threats": 0, "n_opportunities": 0, "_s": 0.0, "max_importance": 0})
            a["n_items"] += r["n_items"]
            a["n_threats"] += r["n_threats"]
            a["n_opportunities"] += r["n_opportunities"]
            a["_s"] += (r["avg_sentiment"] or 0) * r["n_items"]
            a["max_importance"] = max(a["max_importance"], r["max_importance"] or 0)
        out = []
        for a in acc.values():
            a["avg_sentiment"] = a.pop("_s") / a["n_items"] if a["n_items"] else None
            out.append(a)
        return sorted(out, key=lambda r: r["week_start"])

    def _weeks(self):
        acc: dict[str, dict] = {}
        for r in self.fx["weekly"]:
            a = acc.setdefault(r["week_start"], {"week_start": r["week_start"], "n_items": 0, "n_threats": 0,
                                                 "n_opportunities": 0})
            for k in ("n_items", "n_threats", "n_opportunities"):
                a[k] += r[k]
        return list(acc.values())

    def _brief_index(self):
        return [{k: b.get(k) for k in ("week_start", "week_end", "headline", "n_items", "generated_at")}
                for b in self.fx["briefs"]]

    def _entities(self):
        return [dict(e) for e in self.fx["entities"]]

    def _item(self, item_id):
        return [dict(r) for r in self.fx["items"] if r["item_id"] == item_id][:1]

    def _items_by_id(self, ids):
        s = set(ids)
        cols = [c.strip() for c in ITEM_COLS.split(",")]
        return [{c: r.get(c) for c in cols} for r in self.fx["items"] if r["item_id"] in s]


def _src(u: auth.User):
    return _FixtureSource() if _fixture_on() else _SqlSource(u.token)


def _ckey(u: auth.User, *parts) -> tuple:
    return ("fx" if _fixture_on() else "uc", u.email, *parts)


# ------------------------------------------------------------------------------------------------ normalisation
def _entities_dim(u: auth.User) -> dict[str, dict]:
    def load():
        try:
            rows = _src(u).run({"e": _src(u).q_entities()})["e"]
        except Unavailable:
            return {}
        return {r["entity"]: r for r in rows if r.get("entity")}
    return _cached(_ckey(u, "entities"), load, ttl=600)


def _labeller(dim: dict[str, dict]) -> Callable[[str | None], str | None]:
    """Canonical entity -> display name (slugs such as 'agl' become 'AGL Energy' via the watchlist description)."""
    def lbl(e):
        if not e:
            return e
        r = dim.get(e)
        if r and re.fullmatch(r"[a-z0-9_]+", e):
            head = re.split(r"\s[–-]\s", r.get("description") or "", maxsplit=1)[0].strip()
            return head or e.replace("_", " ").title()
        return e
    return lbl


def _norm_item(r: dict, lbl) -> dict:
    ents = [lbl(e) for e in _arr(r.get("entities")) if e]
    out = {
        "item_id": r.get("item_id"), "published_at": r.get("published_at"),
        "published_date": str(r.get("published_date") or "")[:10] or None, "week_start": str(r.get("week_start") or "")[:10],
        "title": r.get("title") or "(untitled)", "source_name": r.get("source_name"), "source_type": r.get("source_type"),
        "url": r.get("url"), "content_depth": r.get("content_depth"), "summary": r.get("summary"),
        "why_it_matters": r.get("why_it_matters"), "primary_entity": lbl(r.get("primary_entity")), "entities": ents,
        "entity_group": r.get("entity_group") or "Industry & market", "topic": r.get("topic"),
        "signal": _signal(r.get("signal")), "sentiment": _f(r.get("sentiment")), "importance": _i(r.get("importance")) or 1,
        "relevance": _i(r.get("relevance")),
    }
    for k in ("excerpt", "doc_path", "ingested_at"):
        if k in r:
            out[k] = r.get(k)
    return out


def _window_items(u: auth.User, ws: date, we: date) -> list[dict]:
    """All relevant items in the window (no excerpts), newest-important first; cached briefly per viewer + window."""
    def load():
        src = _src(u)
        rows = src.run({"items": src.q_items(ws, we)})["items"]
        lbl = _labeller(_entities_dim(u))
        return [_norm_item(r, lbl) for r in rows]
    return _cached(_ckey(u, "items", ws.isoformat(), we.isoformat()), load)


def _norm_brief(b: dict, lbl) -> dict:
    devs = []
    for d in _jload(b.get("developments_json"), []):
        if not isinstance(d, dict):
            continue
        devs.append({"title": d.get("title") or "", "detail": d.get("detail") or "", "signal": _signal(d.get("signal")),
                     "entity_group": d.get("entity_group"), "importance": _i(d.get("importance")) or 3,
                     "item_ids": [str(x) for x in _arr(d.get("item_ids")) if x]})
    devs.sort(key=lambda d: -d["importance"])
    watch = []
    for w in _jload(b.get("watchlist_json"), []):
        if isinstance(w, dict) and w.get("entity"):
            direction = w.get("direction") if w.get("direction") in ("up", "down", "flat") else "flat"
            watch.append({"entity": lbl(w["entity"]), "note": w.get("note") or "", "direction": direction})
    actions = []
    for a in _jload(b.get("actions_json"), []):
        if isinstance(a, dict) and a.get("action"):
            actions.append({"action": a["action"], "owner_role": a.get("owner_role") or ""})
        elif isinstance(a, str):
            actions.append({"action": a, "owner_role": ""})
    ws = _d(b.get("week_start"))
    return {
        "week_start": ws.isoformat() if ws else None, "week_end": str(b.get("week_end") or "")[:10] or None,
        "label": week_label(ws) if ws else "", "headline": b.get("headline") or "", "summary_md": b.get("summary_md") or "",
        "developments": devs, "implications": [str(x) for x in _jload(b.get("implications_json"), []) if x],
        "watchlist": watch, "actions": actions,
        "sentiment": {k: _f(v) for k, v in _jload(b.get("sentiment_json"), {}).items()},
        "n_items": _i(b.get("n_items")), "n_sources": _i(b.get("n_sources")), "generated_at": b.get("generated_at"),
        "week_to_date": bool(ws and ws + timedelta(days=6) >= today()),
    }


# ------------------------------------------------------------------------------------------------ curation (Lakebase)
def _mode(u: auth.User) -> str:
    if u.role in ("KPI_OWNER", "ADMIN"):
        return "analyst"
    if u.role == "LLT":
        return "leader"
    return "board"


def _annotations(u: auth.User, ids: list[str]) -> tuple[dict[str, dict], bool]:
    """Annotations for the given items, and whether curation could be read at all."""
    if not ids:
        return {}, True
    try:
        with db.tx(u.email, u.role) as cur:
            cur.execute("SELECT * FROM scorecard.market_item_annotation WHERE item_id = ANY(%s)", (list(ids),))
            return {r["item_id"]: r for r in _rows(cur.fetchall())}, True
    except Exception as e:  # noqa: BLE001 – the feed still works without curation
        log.warning("market annotations unavailable: %s", e)
        return {}, False


def _merge(it: dict, a: dict | None, mode: str) -> dict:
    a = a or {}
    ovr = _i(a.get("importance_override"))
    out = {**it, "importance_ai": it["importance"], "importance": ovr or it["importance"], "importance_override": ovr,
           "pinned": bool(a.get("pinned")), "dismissed": bool(a.get("dismissed")), "note": None, "note_by": None,
           "note_at": None}
    if mode != "board" and a.get("note"):          # notes are working notes for the leadership team, not board content
        out.update(note=a["note"], note_by=a.get("note_by"), note_at=a.get("note_at"))
    if mode == "analyst" and a:
        out["curated_by"], out["curated_at"] = a.get("updated_by_name") or a.get("updated_by"), a.get("updated_at")
    return out


def _curated(u: auth.User, items: list[dict]) -> tuple[list[dict], bool]:
    ann, ok = _annotations(u, [i["item_id"] for i in items])
    mode = _mode(u)
    return [_merge(i, ann.get(i["item_id"]), mode) for i in items], ok


def _role_visible(items: list[dict], mode: str, show_dismissed: bool = False) -> list[dict]:
    if mode == "board":
        return [i for i in items if i["pinned"]]
    if mode == "leader" or not show_dismissed:
        return [i for i in items if not i["dismissed"]]
    return items


def _sort(items: list[dict], sort: str, mode: str) -> list[dict]:
    out = sorted(items, key=lambda i: i.get("published_at") or "", reverse=True)
    if sort != "newest":
        out.sort(key=lambda i: -i["importance"])
    if mode != "analyst":                            # curated views: pinned items first
        out.sort(key=lambda i: not i["pinned"])
    return out


# ------------------------------------------------------------------------------------------------ aggregates
def _signal_counts(items: list[dict]) -> dict:
    c = Counter(i["signal"] for i in items)
    return {"total": len(items), **{s: c.get(s, 0) for s in SIGNALS}}


def _by_group(items: list[dict]) -> list[dict]:
    acc: dict[str, dict] = {}
    for i in items:
        g = acc.setdefault(i["entity_group"], {"entity_group": i["entity_group"], "n": 0, "_s": [], **{s: 0 for s in SIGNALS}})
        g["n"] += 1
        g[i["signal"]] += 1
        if i["sentiment"] is not None:
            g["_s"].append(i["sentiment"])
    out = []
    for g in acc.values():
        s = g.pop("_s")
        g["avg_sentiment"] = round(sum(s) / len(s), 3) if s else None
        out.append(g)
    order = {g: k for k, g in enumerate(GROUPS)}
    return sorted(out, key=lambda g: (order.get(g["entity_group"], 99)))


def _top_entities(items: list[dict], dim: dict, lbl, n: int = 8) -> list[dict]:
    by_label = {lbl(k): v for k, v in dim.items()}
    acc: dict[str, dict] = {}
    for i in items:
        ents = i["entities"] or ([i["primary_entity"]] if i["primary_entity"] and i["primary_entity"] != "Market" else [])
        for e in dict.fromkeys(ents):
            if not e or e == "Market":
                continue
            a = acc.setdefault(e, {"entity": e, "n": 0, "_s": [], "groups": Counter(), **{s: 0 for s in SIGNALS},
                                   "max_importance": 0})
            a["n"] += 1
            a[i["signal"]] += 1
            a["max_importance"] = max(a["max_importance"], i["importance"])
            if i["sentiment"] is not None:
                a["_s"].append(i["sentiment"])
            if i["primary_entity"] == e:
                a["groups"][i["entity_group"]] += 1
    out = []
    for a in sorted(acc.values(), key=lambda a: (-a["n"], -a["max_importance"], a["entity"]))[:n]:
        s, groups = a.pop("_s"), a.pop("groups")
        meta = by_label.get(a["entity"], {})
        a["avg_sentiment"] = round(sum(s) / len(s), 3) if s else None
        a["entity_group"] = meta.get("entity_group") or (groups.most_common(1)[0][0] if groups else None)
        a["relationship"] = meta.get("relationship")
        out.append(a)
    return out


def _facets(items: list[dict]) -> dict:
    return {k: dict(Counter(i.get(k) for i in items if i.get(k)).most_common())
            for k in ("entity_group", "topic", "signal", "source_type")}


def _week_series(weekly: list[dict], ws: date, we: date) -> dict:
    """Chart rows: items per week by entity group, and item-weighted average sentiment per week."""
    weeks = [(ws + timedelta(weeks=k)).isoformat() for k in range((we - ws).days // 7 + 1)]
    by_week: dict[str, list[dict]] = defaultdict(list)
    for r in weekly:
        by_week[str(r["week_start"])[:10]].append(r)
    items, sent = [], []
    for w in weeks:
        rows = by_week.get(w, [])
        for r in rows:
            items.append({"x": w, "series": r["entity_group"], "y": _i(r["n_items"]) or 0})
        n = sum(_i(r["n_items"]) or 0 for r in rows if r.get("avg_sentiment") is not None)
        if n:
            sent.append({"x": w, "series": "Average sentiment",
                         "y": round(sum((_f(r["avg_sentiment"]) or 0) * (_i(r["n_items"]) or 0) for r in rows
                                        if r.get("avg_sentiment") is not None) / n, 3)})
    totals = [{"week_start": w, "n_items": sum(_i(r["n_items"]) or 0 for r in by_week.get(w, [])),
               "n_threats": sum(_i(r["n_threats"]) or 0 for r in by_week.get(w, [])),
               "n_opportunities": sum(_i(r["n_opportunities"]) or 0 for r in by_week.get(w, []))} for w in weeks]
    return {"weeks": weeks, "items_by_group": items, "sentiment": sent, "totals": totals}


def _sum_weekly(weekly: list[dict], ws: date, we: date) -> dict:
    rows = [r for r in weekly if ws.isoformat() <= str(r["week_start"])[:10] <= we.isoformat()]
    return {k: sum(_i(r[k]) or 0 for r in rows) for k in ("n_items", "n_threats", "n_opportunities")}


# ------------------------------------------------------------------------------------------------ weeks
def _weeks_index(u: auth.User) -> dict:
    def load():
        src = _src(u)
        res = src.run({"weeks": src.q_weeks(), "briefs": src.q_brief_index()})
        idx: dict[str, dict] = {}
        for r in res["weeks"]:
            w = str(r["week_start"])[:10]
            idx[w] = {"week_start": w, "n_items": _i(r["n_items"]) or 0, "n_threats": _i(r["n_threats"]) or 0,
                      "n_opportunities": _i(r["n_opportunities"]) or 0, "has_brief": False, "headline": None}
        for b in res["briefs"]:
            w = str(b["week_start"])[:10]
            e = idx.setdefault(w, {"week_start": w, "n_items": _i(b.get("n_items")) or 0, "n_threats": 0,
                                   "n_opportunities": 0})
            e.update(has_brief=True, headline=b.get("headline"), brief_generated_at=b.get("generated_at"))
        weeks = sorted(idx.values(), key=lambda r: r["week_start"], reverse=True)
        for w in weeks:
            d = date.fromisoformat(w["week_start"])
            w.update(label=week_label(d), week_end=(d + timedelta(days=6)).isoformat())
        return weeks
    return _cached(_ckey(u, "weeks"), load, ttl=120)


def _default_week(weeks: list[dict]) -> date:
    """Latest completed week with items or a brief (its brief may still be being written); else any week with data;
    else this week."""
    cw = current_week()
    for cond in (lambda w: (w.get("has_brief") or w["n_items"] > 0) and date.fromisoformat(w["week_start"]) < cw,
                 lambda w: w.get("has_brief") or w["n_items"] > 0):
        for w in weeks:
            if cond(w):
                return date.fromisoformat(w["week_start"])
    return cw


@router.get("/weeks")
def weeks(u: auth.User = Depends(me_dep)):
    cw = current_week()
    try:
        idx = _weeks_index(u)
    except Unavailable as e:
        return {**_unavailable(e), "current_week": cw.isoformat(), "horizons": list(HORIZONS)}
    idx = [w for w in idx if w["week_start"] <= cw.isoformat()]
    latest_brief = next((w["week_start"] for w in idx if w.get("has_brief")), None)
    return {"available": True, "current_week": cw.isoformat(), "current_label": week_label(cw),
            "default_week": _default_week(idx).isoformat(), "latest_brief_week": latest_brief,
            "earliest_week": idx[-1]["week_start"] if idx else cw.isoformat(), "weeks": idx,
            "horizons": list(HORIZONS), "mode": _mode(u), "can_curate": _mode(u) == "analyst"}


# ------------------------------------------------------------------------------------------------ synthesis cache
def _brief_sig(briefs: list[dict]) -> str:
    raw = "|".join(f"{b['week_start']}@{b.get('generated_at') or ''}" for b in sorted(briefs, key=lambda b: b["week_start"]))
    return hashlib.sha1(raw.encode()).hexdigest()


def _cached_synthesis(u: auth.User, we: date, horizon: int) -> dict | None:
    try:
        with db.tx(u.email, u.role) as cur:
            cur.execute("SELECT * FROM scorecard.market_synthesis WHERE end_week = %s AND horizon = %s", (we, horizon))
            r = cur.fetchone()
        return _rows([r])[0] if r else None
    except Exception as e:  # noqa: BLE001
        log.warning("synthesis cache unavailable: %s", e)
        return None


def _synthesis_out(rec: dict | None, sig: str) -> dict | None:
    if not rec:
        return None
    body = rec["body"] if isinstance(rec["body"], dict) else _jload(rec["body"], {})
    return {**body, "generated_at": rec["generated_at"], "n_briefs": rec["n_briefs"], "stale": rec.get("source_sig") != sig,
            "generated_by": rec.get("generated_by")}


# ------------------------------------------------------------------------------------------------ view
def _load_window(u: auth.User, week: date, horizon: int) -> dict:
    ws, we = _window(week, horizon)
    ctx_s = min(ws, we - timedelta(weeks=CONTEXT_WEEKS - 1))
    prev_s = ws - timedelta(weeks=horizon)
    src = _src(u)
    rest_key = _ckey(u, "briefs+weekly", ws.isoformat(), we.isoformat(), min(ctx_s, prev_s).isoformat())
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_items = ex.submit(_window_items, u, ws, we)
        f_rest = ex.submit(_cached, rest_key, lambda: src.run({"briefs": src.q_briefs(ws, we),
                                                               "weekly": src.q_weekly(min(ctx_s, prev_s), we)}))
        f_dim = ex.submit(_entities_dim, u)
        items, rest, dim = f_items.result(), f_rest.result(), f_dim.result()
    return {"ws": ws, "we": we, "ctx_s": ctx_s, "prev_s": prev_s, "items": items, "briefs": rest["briefs"],
            "weekly": rest["weekly"], "dim": dim}


def _cite(i: dict) -> dict:
    return {k: i.get(k) for k in ("item_id", "title", "url", "source_name", "published_date", "signal", "entity_group",
                                  "importance", "pinned", "dismissed")}


@router.get("/view")
def view(week: str | None = None, horizon: int = 1, u: auth.User = Depends(me_dep)):
    h = _horizon(horizon)
    mode = _mode(u)
    try:
        wk = _parse_week(week, _default_week(_weeks_index(u)))
        d = _load_window(u, wk, h)
    except Unavailable as e:
        return _unavailable(e)
    ws, we, dim = d["ws"], d["we"], d["dim"]
    lbl = _labeller(dim)
    with ThreadPoolExecutor(max_workers=2) as ex:          # the two Lakebase reads are independent
        f_syn = ex.submit(_cached_synthesis, u, we, h) if h > 1 else None
        items, curation_ok = _curated(u, d["items"])
        syn_rec = f_syn.result() if f_syn else None
    by_id = {i["item_id"]: i for i in items}
    briefs = [_norm_brief(b, lbl) for b in d["briefs"]]

    brief = None
    if h == 1:
        brief = next((b for b in briefs if b["week_start"] == we.isoformat()), None)
        if brief:
            want = [x for dv in brief["developments"] for x in dv["item_ids"] if x not in by_id]
            if want:                                  # the agent may cite items published just outside the week
                try:
                    src = _src(u)
                    extra = src.run({"x": src.q_items_by_id(list(dict.fromkeys(want))[:50])})["x"]
                    extra_items, _ = _curated(u, [_norm_item(r, lbl) for r in extra])
                    by_id.update({i["item_id"]: i for i in extra_items})
                except Unavailable:
                    pass
            for dv in brief["developments"]:
                dv["items"] = [_cite(by_id[x]) for x in dv["item_ids"] if x in by_id]

    synthesis = _synthesis_out(syn_rec, _brief_sig(briefs)) if h > 1 else None

    visible = _role_visible(items, mode)
    highlights = [_cite(i) | {"why_it_matters": i.get("why_it_matters"), "topic": i.get("topic")}
                  for i in _sort(visible, "importance", "leader")[:5]] if h == 1 and not brief else []
    trend = _week_series(d["weekly"], d["ctx_s"] if h == 1 else ws, we)
    cur_tot = _sum_weekly(d["weekly"], ws, we)
    prev_tot = _sum_weekly(d["weekly"], d["prev_s"], ws - timedelta(weeks=1))
    out = {
        "available": True, "mode": mode, "can_curate": mode == "analyst", "curation_available": curation_ok,
        "week": {"week_start": we.isoformat(), "week_end": (we + timedelta(days=6)).isoformat(), "label": week_label(we),
                 "is_current": we == current_week(), "period_key": f"W:{we.isoformat()}"},
        "horizon": h,
        "window": {"start": ws.isoformat(), "end": (we + timedelta(days=6)).isoformat(), "label": window_label(ws, we, h),
                   "trend_start": trend["weeks"][0] if trend["weeks"] else ws.isoformat()},
        "brief": brief, "highlights": highlights,
        "briefs": [{k: b[k] for k in ("week_start", "label", "headline", "n_items", "n_sources", "generated_at",
                                      "week_to_date")} for b in briefs] if h > 1 else [],
        "synthesis": synthesis,
        "n_briefs": len(briefs),
        "curation": {"pinned": sum(i["pinned"] for i in items), "dismissed": sum(i["dismissed"] for i in items),
                     "notes": sum(bool(i["note"]) for i in items), "overrides": sum(bool(i["importance_override"]) for i in items)},
    }
    if mode != "board":
        out["stats"] = {
            "n_items": len(items), "n_sources": len({i["source_name"] for i in items if i["source_name"]}),
            "signals": _signal_counts(items), "by_group": _by_group(items),
            "avg_sentiment": round(sum(i["sentiment"] for i in items if i["sentiment"] is not None) /
                                   max(1, sum(i["sentiment"] is not None for i in items)), 3) if items else None,
            "prev": prev_tot if prev_tot["n_items"] else None, "window_weekly": cur_tot,
        }
        out["trend"] = trend
        out["top_entities"] = _top_entities(items, dim, lbl)
        out["facets"] = _facets(visible)
    return out


# ------------------------------------------------------------------------------------------------ item feed
@router.get("/items")
def items(week: str | None = None, horizon: int = 1, group: str | None = None, topic: str | None = None,
          signal: str | None = None, source_type: str | None = None, entity: str | None = None, q: str | None = None,
          sort: str = "importance", pinned_only: bool = False, show_dismissed: bool = False, offset: int = 0,
          limit: int = 30, u: auth.User = Depends(me_dep)):
    h = _horizon(horizon)
    mode = _mode(u)
    try:
        wk = _parse_week(week, _default_week(_weeks_index(u)))
        ws, we = _window(wk, h)
        rows = _window_items(u, ws, we)
    except Unavailable as e:
        return _unavailable(e)
    all_items, _ = _curated(u, rows)
    vis = _role_visible(all_items, mode, show_dismissed and mode == "analyst")
    hidden = sum(i["dismissed"] for i in all_items) if mode != "board" else 0
    f = vis
    if group:
        f = [i for i in f if i["entity_group"] == group]
    if topic:
        f = [i for i in f if i["topic"] == topic]
    if signal:
        f = [i for i in f if i["signal"] == signal]
    if source_type:
        f = [i for i in f if i["source_type"] == source_type]
    if entity:
        f = [i for i in f if i["primary_entity"] == entity or entity in i["entities"]]
    if pinned_only:
        f = [i for i in f if i["pinned"]]
    if q and q.strip():
        terms = q.lower().split()
        def hay(i):
            return " ".join(str(x or "") for x in (i["title"], i["summary"], i["why_it_matters"], i["source_name"],
                                                    i["primary_entity"], " ".join(i["entities"]), i["topic"],
                                                    i["note"])).lower()
        f = [i for i in f if all(t in hay(i) for t in terms)]
    f = _sort(f, sort, mode)
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    return {"available": True, "mode": mode, "total": len(f), "offset": offset, "limit": limit,
            "items": f[offset:offset + limit], "n_visible": len(vis), "n_all": len(all_items),
            "n_dismissed": hidden, "window": {"start": ws.isoformat(), "end": (we + timedelta(days=6)).isoformat()}}


@router.get("/items/{item_id}")
def item(item_id: str, u: auth.User = Depends(me_dep)):
    if not ITEM_ID.match(item_id):
        raise HTTPException(400, "invalid item id")
    try:
        src = _src(u)
        rows = src.run({"i": src.q_item(item_id)})["i"]
    except Unavailable as e:
        return _unavailable(e)
    if not rows:
        raise HTTPException(404, "item not found")
    dim = _entities_dim(u)
    lbl = _labeller(dim)
    it, _ = _curated(u, [_norm_item(rows[0], lbl)])
    out = it[0]
    by_label = {lbl(k): v for k, v in dim.items()}
    out["entity_meta"] = [{"entity": e, "entity_group": by_label.get(e, {}).get("entity_group"),
                           "relationship": by_label.get(e, {}).get("relationship")} for e in out["entities"]]
    out["archived"] = bool(out.pop("doc_path", None))
    out["available"] = True
    return out


# ------------------------------------------------------------------------------------------------ curation
class AnnotationIn(BaseModel):
    week_start: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    pinned: bool | None = None
    dismissed: bool | None = None
    note: str | None = Field(default=None, max_length=2000)
    importance_override: int | None = Field(default=None, ge=1, le=5)


@router.put("/items/{item_id}/annotation")
def annotate(item_id: str, body: AnnotationIn, u: auth.User = Depends(me_dep)):
    """Pin, dismiss, note or re-rank an item (managers / analysts). Only the fields sent are changed."""
    auth.require(u, "KPI_OWNER")
    if not ITEM_ID.match(item_id):
        raise HTTPException(400, "invalid item id")
    sent = body.model_fields_set
    with db.tx(u.email, u.role) as cur:
        cur.execute("SELECT * FROM scorecard.market_item_annotation WHERE item_id = %s FOR UPDATE", (item_id,))
        old = cur.fetchone() or {}
        new = {"pinned": bool(old.get("pinned")), "dismissed": bool(old.get("dismissed")), "note": old.get("note"),
               "importance_override": old.get("importance_override"), "note_by": old.get("note_by"),
               "note_at": old.get("note_at"), "week_start": old.get("week_start")}
        if "pinned" in sent and body.pinned is not None:
            new["pinned"] = body.pinned
            if body.pinned:
                new["dismissed"] = False
        if "dismissed" in sent and body.dismissed is not None:
            new["dismissed"] = body.dismissed
            if body.dismissed:
                new["pinned"] = False
        if "note" in sent:
            note = (body.note or "").strip() or None
            if note != new["note"]:
                new.update(note=note, note_by=u.name if note else None, note_at=datetime.now().astimezone() if note else None)
        if "importance_override" in sent:
            new["importance_override"] = body.importance_override
        if body.week_start:
            new["week_start"] = body.week_start
        cur.execute("""INSERT INTO scorecard.market_item_annotation (item_id, week_start, pinned, dismissed, note, note_by,
                           note_at, importance_override, updated_by, updated_by_name, updated_by_role)
                       VALUES (%(id)s, %(ws)s, %(p)s, %(d)s, %(n)s, %(nb)s, %(na)s, %(io)s, %(e)s, %(un)s, %(r)s)
                       ON CONFLICT (item_id) DO UPDATE SET week_start = EXCLUDED.week_start, pinned = EXCLUDED.pinned,
                           dismissed = EXCLUDED.dismissed, note = EXCLUDED.note, note_by = EXCLUDED.note_by,
                           note_at = EXCLUDED.note_at, importance_override = EXCLUDED.importance_override,
                           updated_by = EXCLUDED.updated_by, updated_by_name = EXCLUDED.updated_by_name,
                           updated_by_role = EXCLUDED.updated_by_role, updated_at = now()
                       RETURNING *""",
                    {"id": item_id, "ws": new["week_start"], "p": new["pinned"], "d": new["dismissed"], "n": new["note"],
                     "nb": new["note_by"], "na": new["note_at"], "io": new["importance_override"], "e": u.email,
                     "un": u.name, "r": u.role})
        return _rows([cur.fetchone()])[0]


# ------------------------------------------------------------------------------------------------ multi-week synthesis
SYNTH_SYSTEM = """You are the Market Intelligence Analyst for Lochard Energy, owner and operator of the Iona underground gas \
storage facility in south-west Victoria and proponent of the Heytesbury Underground Gas Storage (HUGS) expansion. You write \
for Lochard's leadership team and board.

From the weekly briefs provided, write ONE synthesis of the whole period: which themes persisted, built, eased or were \
resolved; what changed for customers, competitors, upstream suppliers, regulators, government and the east-coast gas \
market; and what it means for Lochard. Australian English, factual and concise. Use only information in the briefs – never \
invent facts, figures, dates or quotes, and never name individuals.

Be concise: the whole JSON must stay under about 900 words. Inside string values never use the double-quote character
(write single quotes instead). Return ONLY a JSON object (no markdown fences) with exactly these keys:
  "headline": one line (max 120 characters),
  "summary_md": 4-6 sentence executive summary (markdown allowed, no headings),
  "themes": 3-5 objects {"title", "detail" (at most 2 sentences), "signal": "Opportunity"|"Threat"|"Watch"|"Neutral",
            "entity_groups": [...], "trend": "building"|"easing"|"steady"|"new"|"resolved",
            "weeks": [week_start dates (YYYY-MM-DD) of the briefs where it featured]},
  "watchlist": up to 5 objects {"entity", "note" (one short sentence), "direction": "up"|"down"|"flat"},
  "implications": 3-5 strings,
  "actions": 2-4 objects {"action", "owner_role"}"""



def _brief_text(b: dict, compact: bool = False) -> str:
    lines = [f"## {b['label']} ({b.get('n_items') or 0} items, {b.get('n_sources') or 0} sources)"
             + (" – week to date" if b.get("week_to_date") else ""),
             f"Headline: {b['headline']}", f"Summary: {b['summary_md']}"]
    if b["developments"]:
        lines.append("Developments:")
        devs = b["developments"][:4] if compact else b["developments"]
        lines += [f"- [{dv['signal']} · {dv.get('entity_group') or 'Market'} · importance {dv['importance']}] "
                  f"{dv['title']}: {dv['detail'][:200 if compact else 320]}" for dv in devs]
    if b["implications"]:
        lines.append("Implications: " + " | ".join(b["implications"]))
    if b["watchlist"]:
        lines.append("Watchlist: " + " | ".join(f"{w['entity']} ({w['direction']}): {w['note']}" for w in b["watchlist"]))
    if b["actions"]:
        lines.append("Actions: " + " | ".join(f"{a['action']} [{a['owner_role']}]" for a in b["actions"]))
    return "\n".join(lines)


def _parse_obj(text: str) -> dict:
    t = re.sub(r"^\s*```(?:json)?|```\s*$", "", text.strip())
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("no JSON object in response")
    return json.loads(t[i:j + 1], strict=False)       # tolerate raw newlines inside strings


def _clean_synthesis(o: dict, weeks: set[str], ent_group: dict[str, str] | None = None) -> dict:
    ent_group = ent_group or {}

    def groups(v) -> list[str]:
        out = []
        for g in _arr(v):
            g = g if g in GROUPS else ent_group.get(str(g))
            if g and g not in out:
                out.append(g)
        return out[:4]

    themes = []
    for t in o.get("themes") or []:
        if not isinstance(t, dict) or not t.get("title"):
            continue
        themes.append({"title": str(t["title"]), "detail": str(t.get("detail") or ""), "signal": _signal(t.get("signal")),
                       "entity_groups": groups(t.get("entity_groups")),
                       "trend": t.get("trend") if t.get("trend") in ("building", "easing", "steady", "new", "resolved")
                       else "steady",
                       "weeks": sorted({str(w)[:10] for w in _arr(t.get("weeks")) if str(w)[:10] in weeks})})
    watch = [{"entity": str(w["entity"]), "note": str(w.get("note") or ""),
              "direction": w.get("direction") if w.get("direction") in ("up", "down", "flat") else "flat"}
             for w in (o.get("watchlist") or []) if isinstance(w, dict) and w.get("entity")][:6]
    actions = [{"action": str(a["action"]), "owner_role": str(a.get("owner_role") or "")}
               for a in (o.get("actions") or []) if isinstance(a, dict) and a.get("action")][:4]
    out = {"headline": str(o.get("headline") or "").strip(), "summary_md": str(o.get("summary_md") or "").strip(),
           "themes": themes, "watchlist": watch, "implications": [str(x) for x in (o.get("implications") or []) if x][:5],
           "actions": actions}
    if not out["headline"] or not out["summary_md"]:
        raise ValueError("synthesis is missing a headline or summary")
    return out


_synth_jobs: dict[tuple, dict] = {}         # (end_week, horizon) -> {"status": running|error, "error", "started"}


def _generate_synthesis(u: auth.User, ws: date, we: date, h: int, briefs: list[dict], weekly_rows: list[dict],
                        ent_group: dict[str, str], sig: str) -> None:
    """Runs in a background thread: one LLM call (standard tier, economy as fallback), then cache in Lakebase."""
    key = (we, h)
    try:
        weekly = [t for t in _week_series(weekly_rows, ws, we)["totals"] if t["n_items"]]
        activity = "; ".join(f"{week_label(date.fromisoformat(t['week_start']))}: {t['n_items']} items "
                             f"({t['n_threats']} threats, {t['n_opportunities']} opportunities)" for t in weekly)
        coverage = (f"Weekly briefs exist for {len(briefs)} of the {h} weeks, from "
                    f"{week_label(date.fromisoformat(briefs[0]['week_start']))}. Weeks without a brief are outside the "
                    "collection history – do not describe them as quiet or draw conclusions about them.")
        compact = h >= 13                          # keep long windows within a comfortable prompt size
        prompt = (f"Period: {window_label(ws, we, h)}.\n{coverage}\nWeekly activity: {activity}\n\n"
                  + "\n\n".join(_brief_text(b, compact) for b in briefs) + "\n\nWrite the synthesis JSON.")
        t0, last, body_out = time.time(), None, None
        for model in (config.LLM_STANDARD_MODEL, config.LLM_ECONOMY_MODEL):
            try:
                text, used, route = llm.chat([{"role": "system", "content": SYNTH_SYSTEM},
                                              {"role": "user", "content": prompt}], model=model, max_tokens=4500,
                                             user=u.email, timeout_s=240)
                body_out = _clean_synthesis(_parse_obj(text), {b["week_start"] for b in briefs}, ent_group)
                break
            except Exception as e:  # noqa: BLE001 – try the next tier, then give up with a friendly message
                log.warning("synthesis with %s failed: %s", model, e)
                last = e
        if body_out is None:
            raise RuntimeError(f"synthesis failed: {last}")
        log.info("market synthesis %s h=%s via %s/%s in %.1fs", we, h, used, route, time.time() - t0)
        with db.tx(u.email, u.role) as cur:
            cur.execute("""INSERT INTO scorecard.market_synthesis (end_week, horizon, body, source_sig, n_briefs, model,
                               generated_by)
                           VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s)
                           ON CONFLICT (end_week, horizon) DO UPDATE SET body = EXCLUDED.body,
                               source_sig = EXCLUDED.source_sig, n_briefs = EXCLUDED.n_briefs, model = EXCLUDED.model,
                               generated_by = EXCLUDED.generated_by, generated_at = now()""",
                        (we, h, json.dumps(body_out), sig, len(briefs), used, u.name))
        with _glock:
            _synth_jobs.pop(key, None)
    except Exception as e:  # noqa: BLE001
        log.warning("market synthesis %s h=%s failed: %s", we, h, e)
        with _glock:
            _synth_jobs[key] = {"status": "error", "error": "The synthesis could not be generated just now – please try again.",
                                "started": _synth_jobs.get(key, {}).get("started")}


def _synthesis_window(u: auth.User, week: str, horizon: int):
    if horizon not in HORIZONS or horizon == 1:
        raise HTTPException(400, "horizon must be 4, 13 or 26 weeks")
    wk = _parse_week(week, current_week())
    ws, we = _window(wk, horizon)
    src = _src(u)
    dim = _entities_dim(u)
    res = src.run({"briefs": src.q_briefs(ws, we), "weekly": src.q_weekly(ws, we)})
    lbl = _labeller(dim)
    briefs = [_norm_brief(b, lbl) for b in res["briefs"]]
    return ws, we, briefs, res["weekly"], {lbl(k): v.get("entity_group") for k, v in dim.items()}, _brief_sig(briefs)


class SynthesisIn(BaseModel):
    week: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    horizon: int
    force: bool = False


@router.post("/synthesis")
def synthesis(body: SynthesisIn, u: auth.User = Depends(me_dep)):
    """Multi-week synthesis from the weekly briefs in the window, cached per end week + horizon. Anyone viewing the window
    starts generation when there is no synthesis yet or the briefs behind it have changed; forcing a fresh one while it
    is current ("Regenerate") is for managers / analysts. Generation runs in the background (it can take a minute or
    two): the response is {status: "ready", synthesis} or {status: "running"} – poll GET /synthesis."""
    if body.force:
        auth.require(u, "KPI_OWNER")
    try:
        ws, we, briefs, weekly, ent_group, sig = _synthesis_window(u, body.week, body.horizon)
    except Unavailable as e:
        return _unavailable(e)
    if not briefs:
        raise HTTPException(409, "There are no weekly briefs in this window yet.")
    key = (we, body.horizon)
    rec = _cached_synthesis(u, we, body.horizon)
    if rec and not body.force and rec.get("source_sig") == sig:
        return {"available": True, "status": "ready", "synthesis": _synthesis_out(rec, sig)}
    with _glock:
        job = _synth_jobs.get(key)
        if not job or job["status"] != "running":
            _synth_jobs[key] = {"status": "running", "error": None, "started": datetime.now().astimezone().isoformat()}
            threading.Thread(target=_generate_synthesis, name=f"synthesis-{we}-{body.horizon}", daemon=True,
                             args=(u, ws, we, body.horizon, briefs, weekly, ent_group, sig)).start()
    return {"available": True, "status": "running", "n_briefs": len(briefs),
            "synthesis": _synthesis_out(rec, sig) if rec else None}


@router.get("/synthesis")
def synthesis_status(week: str, horizon: int, u: auth.User = Depends(me_dep)):
    """Status of the synthesis for a window: ready (with the synthesis), running, error or missing."""
    wk = _parse_week(week, current_week())
    _, we = _window(wk, horizon if horizon in HORIZONS else 4)
    with _glock:
        job = dict(_synth_jobs.get((we, horizon)) or {})
    if job.get("status") == "running":
        return {"available": True, "status": "running", "started": job.get("started")}
    rec = _cached_synthesis(u, we, horizon)
    if job.get("status") == "error" and not rec:
        return {"available": True, "status": "error", "error": job.get("error")}
    if not rec:
        return {"available": True, "status": "missing"}
    body = rec["body"] if isinstance(rec["body"], dict) else _jload(rec["body"], {})
    out = {**body, "generated_at": rec["generated_at"], "n_briefs": rec["n_briefs"], "stale": False,
           "generated_by": rec.get("generated_by")}
    return {"available": True, "status": "error" if job.get("status") == "error" else "ready", "synthesis": out,
            "error": job.get("error")}


# ------------------------------------------------------------------------------------------------ pulse (other pages)
@router.get("/pulse")
def pulse(weeks: int = 1, week: str | None = None, u: auth.User = Depends(me_dep)):
    """Compact summary for other pages (Leadership Insights, board pack): latest week (or `week`), headline, signal
    counts over the last `weeks` weeks, top 3 items (curated per role) and the visible weekly commentary."""
    n = max(1, min(weeks, 26))
    mode = _mode(u)
    try:
        idx = _weeks_index(u)
        wk = _parse_week(week, _default_week([w for w in idx if w["week_start"] <= current_week().isoformat()]))
        ws, we = _window(wk, n)
        src = _src(u)
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_items = ex.submit(_window_items, u, ws, we)
            f_brief = ex.submit(src.run, {"b": src.q_briefs(we, we)})
            rows, brows = f_items.result(), f_brief.result()["b"]
    except Unavailable as e:
        return _unavailable(e)
    lbl = _labeller(_entities_dim(u))
    brief = _norm_brief(brows[0], lbl) if brows else None
    items_c, _ = _curated(u, rows)
    top = _sort(_role_visible(items_c, mode), "importance", "leader")[:3]
    key = f"W:{we.isoformat()}"
    try:
        c = commentary.fetch(u, "market", key, ["brief"]).get("brief")
    except Exception:  # noqa: BLE001
        c = None
    return {
        "available": True, "mode": mode, "weeks": n, "week_start": we.isoformat(),
        "week_end": (we + timedelta(days=6)).isoformat(), "label": week_label(we),
        "window": {"start": ws.isoformat(), "end": (we + timedelta(days=6)).isoformat(), "label": window_label(ws, we, n)},
        "has_brief": bool(brief), "headline": brief["headline"] if brief else None,
        "summary_md": brief["summary_md"] if brief else None, "brief_generated_at": brief["generated_at"] if brief else None,
        "week_to_date": we == current_week(),
        "counts": _signal_counts(items_c), "n_sources": len({i["source_name"] for i in items_c if i["source_name"]}),
        "top_items": [{k: i.get(k) for k in ("item_id", "title", "url", "source_name", "source_type", "published_date",
                                             "signal", "entity_group", "topic", "importance", "summary", "why_it_matters",
                                             "pinned", "note")} for i in top],
        "period_key": key,
        "commentary": {k: c.get(k) for k in ("status", "body", "author_name", "submitted_at", "reviewer_name",
                                             "reviewed_at")} if c else None,
    }


# ------------------------------------------------------------------------------------------------ facts for AI drafts
def _market_facts(u: auth.User, subject: str, period_key: str) -> str:
    wk = _parse_week(period_key.split(":", 1)[-1], current_week())
    try:
        d = _load_window(u, wk, 1)
    except Unavailable as e:
        raise HTTPException(409, _unavailable(e)["message"]) from e
    lbl = _labeller(d["dim"])
    items_c, _ = _curated(u, d["items"])
    brief = next((_norm_brief(b, lbl) for b in d["briefs"]), None)
    vis = _sort(_role_visible(items_c, "leader"), "importance", "leader")
    c = _signal_counts(items_c)
    end = wk + timedelta(days=6)
    out = [f"Lochard Energy – Market Intelligence – {week_label(wk)} (Mon {_fmt_d(wk, False)} – Sun {_fmt_d(end)}).",
           f"{c['total']} relevant public items from {len({i['source_name'] for i in items_c})} sources: "
           f"{c['Opportunity']} opportunities, {c['Threat']} threats, {c['Watch']} to watch, {c['Neutral']} neutral."]
    if brief:
        out += [f"Analyst agent brief – headline: {brief['headline']}", f"Summary: {brief['summary_md']}"]
        if brief["developments"]:
            out.append("Key developments:")
            out += [f"- [{dv['signal']}, {dv.get('entity_group') or 'Market'}, importance {dv['importance']}/5] "
                    f"{dv['title']}: {dv['detail']}" for dv in brief["developments"]]
        if brief["implications"]:
            out.append("Implications for Lochard: " + " ".join(brief["implications"]))
        if brief["actions"]:
            out.append("Recommended actions: " + "; ".join(f"{a['action']} ({a['owner_role']})" for a in brief["actions"]))
    else:
        out.append("No analyst brief has been written for this week yet.")
    if vis:
        out.append("Top items (analyst-pinned first, dismissed items excluded):")
        for i in vis[:8]:
            line = (f"- {'[PINNED] ' if i['pinned'] else ''}{i['title']} ({i['source_name']}, {i['published_date']}; "
                    f"{i['signal']}; {i['entity_group']}; importance {i['importance']}/5) – {i['why_it_matters'] or i['summary']}")
            if i.get("note"):
                line += f" Analyst note: {i['note']}"
            out.append(line)
    return "\n".join(out)


commentary.register_facts("market", _market_facts)
