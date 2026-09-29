"""Collect public market intelligence for Lochard Energy into the market_intel UC Volume.

Sources
  news           Google News RSS search for every watchlist entity and topic, per week (headline + publisher)
  web_research   a web-search agent (Responses API + hosted web_search tool) that finds dated articles per theme and
                 week; each article is then fetched and its readable text extracted
  asx            ASX announcements of listed watchlist companies; relevant PDFs are landed for ai_parse_document
  lochard        dated items from Lochard's newsroom page

Output (one JSON object per line):
  <root>/items/source=<source>/week=<monday>/<run>.jsonl
  <root>/documents/asx/<code>/<documentKey>.pdf
  <root>/reference/watchlist.json
  <root>/_state/seen.json                      item ids already landed (idempotent re-runs)

Usage
  collect.py --root /Volumes/<catalog>/<prefix>landing/market_intel --mode daily
  collect.py --root ... --mode backfill --weeks 26 [--sources news,web_research,asx,lochard]
Runs as a serverless job task (writes through the /Volumes FUSE mount) or locally (writes through the Files API).
"""
from __future__ import annotations

import argparse
import email.utils
import hashlib
import html
import io
import json
import os
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser

import requests
import yaml

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36 lochard-market-intel/1.0")
HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or sys.argv[0]))   # serverless tasks have no __file__
ASX_LIST = "https://asx.api.markitdigital.com/asx-research/1.0/companies/{code}/announcements"
ASX_PDF = ("https://cdn-api.markitdigital.com/apiman-gateway/ASX/asx-research/1.0/file/{key}"
           "?access_token=83ff96335c2d45a094df02a206a39ff4")
ASX_SKIP = re.compile(r"appendix\s*3|substantial hold|unquoted securities|cessation of securities|director'?s? interest|"
                      r"change of director|application for quotation|proposed issue|dividend|distribution|cleansing|"
                      r"security holder|buy-back|notice of (annual )?general meeting|becoming a substantial|tax return|appendix 4|"
                      r"corporate governance|date of agm|annual meeting|proxy form|annual report to shareholders|"
                      r"investor presentation -? ?replacement|trading halt|pause in trading|reinstatement", re.I)
RELEVANT = re.compile(r"\bgas\b|lng|storage|pipeline|energy|electricit|power|aemo|\baer\b|aemc|accc|hydrogen|carbon|"
                      r"emission|retail|tariff|supply|otway|gippsland|bass strait|iona|lochard|heytesbury|reservoir|"
                      r"well|drill|terminal|regas|fsru|winter|shortfall|price|contract|acquisition|merger|results|"
                      r"quarterly|guidance|outlook|project|approval|policy|reservation", re.I)
MON_RE = re.compile(r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|"
                    r"December)\s+(20\d\d)\b")


# ------------------------------------------------------------------------------------------------ storage
class Store:
    """Write to a UC Volume: plain files on Databricks (FUSE mount), the Files API elsewhere."""

    def __init__(self, root: str):
        self.root = root.rstrip("/")
        self.fuse = os.path.isdir("/Volumes") and root.startswith("/Volumes")
        self.local = not root.startswith("/Volumes")
        self.w = None
        if not self.fuse and not self.local:
            from databricks.sdk import WorkspaceClient
            self.w = WorkspaceClient(profile=os.environ.get("DATABRICKS_PROFILE", "fevm-dc-demo-workspace-02"))

    def write(self, rel: str, data: bytes):
        path = f"{self.root}/{rel}"
        if self.w:
            self.w.files.upload(path, io.BytesIO(data), overwrite=True)
            return path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def read(self, rel: str) -> bytes | None:
        path = f"{self.root}/{rel}"
        try:
            if self.w:
                return self.w.files.download(path).contents.read()
            with open(path, "rb") as f:
                return f.read()
        except Exception:  # noqa: BLE001 – first run
            return None


# ------------------------------------------------------------------------------------------------ helpers
def sha(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def canon_url(u: str) -> str:
    p = urllib.parse.urlsplit(u.strip())
    q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/",
                                    urllib.parse.urlencode(q), ""))


def get(url: str, timeout=25, **kw) -> requests.Response | None:
    try:
        return requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en-AU,en;q=0.8"}, timeout=timeout, **kw)
    except requests.RequestException as e:
        print(f"  ! {url[:90]}: {e.__class__.__name__}")
        return None


class _Text(HTMLParser):
    """Readable text from an article page: paragraphs and headings inside <article>/<main> when present."""
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "figure", "button"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.stack: list[str] = []
        self.blocks: list[tuple[bool, str]] = []   # (inside article/main, text)
        self.buf: list[str] = []
        self.in_article = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag in ("article", "main"):
            self.in_article += 1
        if tag in ("p", "h1", "h2", "h3", "li", "blockquote"):
            self.buf = []
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag in ("article", "main") and self.in_article:
            self.in_article -= 1
        if self.stack and tag == self.stack[-1]:
            self.stack.pop()
            t = re.sub(r"\s+", " ", "".join(self.buf)).strip()
            if len(t) > 30 or (tag.startswith("h") and len(t) > 8):
                self.blocks.append((self.in_article > 0, t))
            self.buf = []

    def handle_data(self, data):
        if not self.skip and self.stack:
            self.buf.append(data)


def extract_text(page: str) -> str:
    p = _Text()
    try:
        p.feed(page)
    except Exception:  # noqa: BLE001
        return ""
    inside = [t for a, t in p.blocks if a]
    blocks = inside if sum(len(t) for t in inside) > 400 else [t for _, t in p.blocks]
    junk = re.compile(r"cookie|subscribe|sign up|newsletter|all rights reserved|advertisement|share this", re.I)
    return "\n".join(t for t in blocks if not junk.search(t))[:20000]


def page_date(page: str) -> str | None:
    for pat in (r'"datePublished"\s*:\s*"([^"]+)"', r'property="article:published_time"\s+content="([^"]+)"',
                r'name="(?:pubdate|publish-date|date)"\s+content="([^"]+)"'):
        m = re.search(pat, page)
        if m:
            return m.group(1)
    return None


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_when(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        pass
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone(timedelta(hours=10)))
    except ValueError:
        return None


def item(source_type: str, source_name: str, title: str, url: str | None, published: datetime, depth: str,
         text: str = "", **extra) -> dict:
    title = html.unescape(re.sub(r"\s+", " ", title)).strip()
    key = canon_url(url) if url and "news.google.com" not in url else f"{title.lower()}|{source_name.lower()}|{published:%Y-%m-%d}"
    return {"item_id": sha(key), "source_type": source_type, "source_name": source_name, "title": title, "url": url,
            "published_at": iso(published), "content_depth": depth, "text": text[:20000],
            "collected_at": iso(datetime.now(timezone.utc)), **extra}


# ------------------------------------------------------------------------------------------------ sources
def google_news(queries: list[tuple[str, str | None]], weeks: list[date], per_query: int) -> list[dict]:
    """Headline items per (query, week). Links are Google redirects, so content_depth = headline."""
    out = []

    def one(q: str, entity: str | None, wk: date) -> list[dict]:
        qq = f"{q} after:{wk - timedelta(days=1):%Y-%m-%d} before:{wk + timedelta(days=7):%Y-%m-%d}"
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(qq)}&hl=en-AU&gl=AU&ceid=AU:en"
        r = get(url)
        if not r or r.status_code != 200:
            return []
        rows = []
        for m in re.finditer(r"<item>(.*?)</item>", r.text, re.S):
            x = m.group(1)
            title = html.unescape(re.sub(r"<[^>]+>", "", (re.search(r"<title>(.*?)</title>", x, re.S) or [None, ""])[1]))
            src = html.unescape((re.search(r"<source[^>]*>(.*?)</source>", x, re.S) or [None, "Google News"])[1]).strip()
            link = (re.search(r"<link>(.*?)</link>", x, re.S) or [None, None])[1]
            when = parse_when((re.search(r"<pubDate>(.*?)</pubDate>", x, re.S) or [None, None])[1])
            if not title or not when or not (wk <= when.astimezone(timezone(timedelta(hours=10))).date() < wk + timedelta(days=7)):
                continue
            if src and title.endswith(f" - {src}"):
                title = title[: -len(src) - 3]
            if not RELEVANT.search(title):
                continue
            rows.append(item("news", src, title, link, when, "headline", title, query=q, watch_entity=entity))
            if len(rows) >= per_query:
                break
        return rows

    jobs = [(q, e, wk) for wk in weeks for q, e in queries]
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(one, *j) for j in jobs]
        for f in as_completed(futs):
            out += f.result()
    print(f"news: {len(out)} items from {len(jobs)} searches")
    return out


def _host_headers():
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient() if os.environ.get("DATABRICKS_RUNTIME_VERSION") else \
        WorkspaceClient(profile=os.environ.get("DATABRICKS_PROFILE", "fevm-dc-demo-workspace-02"))
    h = w.config.authenticate()
    h["Content-Type"] = "application/json"
    return w.config.host.rstrip("/"), h


RESEARCH_PROMPT = """You research the Australian gas market for Lochard Energy, owner of the Iona underground gas storage
facility in Victoria. Search the web for news articles, media releases and regulator publications about:

{theme}

Only include items PUBLISHED between {start} and {end} (inclusive). Prefer primary and reputable sources (company and
regulator media releases, AFR, The Australian, ABC, Reuters, RenewEconomy, Energy News Bulletin, Utility Magazine,
EnergyQuest, government sites). Every item must be a specific dated article with its own URL (not a homepage or a
search page). Return ONLY a JSON array (no prose) of up to 8 objects:
[{{"title": "...", "publisher": "...", "date": "YYYY-MM-DD", "url": "https://...", "summary": "two factual sentences"}}]
Return [] if nothing relevant was published in that window."""


def web_research(themes: list[str], weeks: list[date], model: str) -> list[dict]:
    host, headers = _host_headers()
    out = []

    def one(theme: str, wk: date) -> list[dict]:
        end = min(wk + timedelta(days=6), date.today())
        body = {"model": model, "input": RESEARCH_PROMPT.format(theme=theme, start=f"{wk:%d %B %Y}", end=f"{end:%d %B %Y}"),
                "tools": [{"type": "web_search", "user_location": {"type": "approximate", "country": "AU"}}],
                "reasoning": {"effort": "low"}}
        for attempt in range(3):
            try:
                r = requests.post(f"{host}/serving-endpoints/responses", headers=headers, json=body, timeout=240)
            except requests.RequestException as e:
                print(f"  ! research {wk} {e.__class__.__name__}")
                time.sleep(5)
                continue
            if r.status_code == 429:
                time.sleep(15 * (attempt + 1))
                continue
            break
        else:
            return []
        if r.status_code != 200:
            print(f"  ! research {wk}: {r.status_code} {r.text[:160]}")
            return []
        text = "".join(c.get("text", "") for o in r.json().get("output", []) if o.get("type") == "message"
                       for c in o.get("content", []))
        m = re.search(r"\[.*\]", text, re.S)
        try:
            found = json.loads(m.group(0)) if m else []
        except ValueError:
            found = []
        rows = []
        for f in found:
            try:
                d = date.fromisoformat(str(f.get("date"))[:10])
            except ValueError:
                continue
            url = str(f.get("url") or "")
            if not (wk - timedelta(days=1) <= d <= wk + timedelta(days=7)) or not url.startswith("http"):
                continue
            rows.append({"title": f.get("title") or "", "publisher": f.get("publisher") or urllib.parse.urlsplit(url).netloc,
                         "date": d, "url": url, "summary": f.get("summary") or "", "theme": theme})
        return rows

    jobs = [(t, wk) for wk in weeks for t in themes]
    with ThreadPoolExecutor(max_workers=6) as ex:
        found = [r for f in as_completed([ex.submit(one, *j) for j in jobs]) for r in f.result()]
    print(f"web_research: {len(found)} candidate articles from {len(jobs)} searches")

    def fetch(f: dict) -> dict | None:
        r = get(f["url"], timeout=20)
        if r is not None and r.status_code in (404, 410):
            return None                                   # dead or invented link – drop it
        text, depth = f["summary"], "summary"
        pub = datetime(f["date"].year, f["date"].month, f["date"].day, 9, tzinfo=timezone(timedelta(hours=10)))
        if r is not None and r.status_code == 200 and "html" in r.headers.get("content-type", ""):
            body = extract_text(r.text)
            if len(body) > 600:
                text, depth = body, "full_text"
            pd_ = parse_when(page_date(r.text))
            if pd_ and abs((pd_.date() - f["date"]).days) <= 3:
                pub = pd_
        return item("web_research", f["publisher"], f["title"], f["url"], pub, depth, text,
                    research_summary=f["summary"], query=f["theme"])

    with ThreadPoolExecutor(max_workers=8) as ex:
        out = [x for x in ex.map(fetch, found) if x]
    print(f"web_research: {len(out)} articles kept ({sum(1 for x in out if x['content_depth'] == 'full_text')} with full text)")
    return out


def asx(entities: list[dict], store: Store, since: date) -> list[dict]:
    out = []
    for e in entities:
        code = e.get("asx")
        if not code:
            continue
        r = get(ASX_LIST.format(code=code.lower()))
        if not r or r.status_code != 200:
            continue
        for a in (r.json().get("data") or {}).get("items", []):
            when = parse_when(a.get("date"))
            head = a.get("headline") or ""
            if not when or when.date() < since or ASX_SKIP.search(head):
                continue
            key = a.get("documentKey")
            pdf = get(ASX_PDF.format(key=key), timeout=60)
            doc_path = None
            if pdf is not None and pdf.status_code == 200 and pdf.content[:4] == b"%PDF":
                doc_path = store.write(f"documents/asx/{code}/{key}.pdf", pdf.content)
            out.append(item("asx_announcement", f"ASX: {code}", head, ASX_PDF.format(key=key), when,   # one URL per document
                            "full_text" if doc_path else "headline", head, doc_path=doc_path, asx_code=code,
                            document_key=key, price_sensitive=bool(a.get("isPriceSensitive")), watch_entity=e["name"]))
            time.sleep(0.3)
    print(f"asx: {len(out)} announcements ({sum(1 for x in out if x.get('doc_path'))} PDFs)")
    return out


def lochard_newsroom(since: date) -> list[dict]:
    r = get("https://www.lochardenergy.com.au/news/")
    if not r or r.status_code != 200:
        return []
    out = []
    parts = re.split(r"<h[23][^>]*>", r.text)[1:]
    for p in parts:
        title = html.unescape(re.sub(r"<[^>]+>", "", p.split("</h", 1)[0])).strip()
        body = extract_text("<article>" + p.split("</h", 1)[-1][:8000] + "</article>")
        m = MON_RE.search(title + " " + body[:400])
        if not title or not m:
            continue
        d = datetime.strptime(" ".join(m.groups()), "%d %B %Y").replace(hour=9, tzinfo=timezone(timedelta(hours=10)))
        link = re.search(r'href="(https://www\.lochardenergy\.com\.au/[^"]+)"', p)
        if d.date() >= since:
            out.append(item("company_release", "Lochard Energy", title, link.group(1) if link else "https://www.lochardenergy.com.au/news/",
                            d, "full_text" if len(body) > 300 else "summary", body or title, watch_entity="Lochard Energy"))
    print(f"lochard: {len(out)} dated newsroom items")
    return out


# ------------------------------------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="/Volumes/<catalog>/<prefix>landing/market_intel (or a local dir)")
    ap.add_argument("--mode", choices=["daily", "backfill"], default="daily")
    ap.add_argument("--weeks", type=int, default=26, help="backfill depth in weeks (backfill mode)")
    ap.add_argument("--sources", default="news,web_research,asx,lochard")
    ap.add_argument("--research-model", default="databricks-gpt-5-5")
    ap.add_argument("--per-query", type=int, default=12)
    ap.add_argument("--watchlist", default=os.path.join(HERE, "watchlist.yml"))
    a, _ = ap.parse_known_args(argv)

    store = Store(a.root)
    wl = yaml.safe_load(open(a.watchlist))
    today = datetime.now(timezone(timedelta(hours=10))).date()
    this_week = monday(today)
    n = 2 if a.mode == "daily" else max(1, a.weeks)
    weeks = [this_week - timedelta(weeks=i) for i in range(n)]
    since = weeks[-1]
    sources = {s.strip() for s in a.sources.split(",") if s.strip()}
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    print(f"mode={a.mode} weeks={weeks[-1]}..{weeks[0]} sources={sorted(sources)} root={a.root}")

    store.write("reference/watchlist.json", "\n".join(json.dumps({
        "entity": e["name"], "entity_group": e["group"], "relationship": e.get("relationship"),
        "description": e.get("description"), "asx_code": e.get("asx"), "website": e.get("website"),
        "aliases": e.get("aliases") or []}) for e in wl["entities"]).encode())

    seen = set(json.loads(store.read("_state/seen.json") or b"[]"))
    items: list[dict] = []
    if "news" in sources:
        qs = [(q, e["name"]) for e in wl["entities"] for q in e.get("queries", [])] + [(t["query"], None) for t in wl["topics"]]
        items += google_news(qs, weeks, a.per_query)
    if "web_research" in sources:
        items += web_research(wl["research_themes"], weeks, a.research_model)
    if "asx" in sources:
        items += asx(wl["entities"], store, since)
    if "lochard" in sources:
        items += lochard_newsroom(since)

    fresh, by_key = [], {}
    for it in items:                       # one row per item id; prefer the richest copy
        prev = by_key.get(it["item_id"])
        rank = {"full_text": 2, "summary": 1, "headline": 0}
        if prev is None or rank[it["content_depth"]] > rank[prev["content_depth"]]:
            by_key[it["item_id"]] = it
    for iid, it in by_key.items():
        if iid not in seen:
            fresh.append(it)
            seen.add(iid)
    groups: dict[tuple[str, str], list[dict]] = {}
    for it in fresh:
        wk = monday(datetime.fromisoformat(it["published_at"].replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=10))).date())
        groups.setdefault((it["source_type"], f"{wk}"), []).append(it)
    for (src, wk), rows in groups.items():
        store.write(f"items/source={src}/week={wk}/{run}.jsonl", "\n".join(json.dumps(r) for r in rows).encode())
    store.write("_state/seen.json", json.dumps(sorted(seen)).encode())
    counts = {}
    for it in fresh:
        counts[it["source_type"]] = counts.get(it["source_type"], 0) + 1
    print(f"landed {len(fresh)} new items (of {len(by_key)} found) in {len(groups)} files: {counts}")


if __name__ == "__main__":
    main(sys.argv[1:])
