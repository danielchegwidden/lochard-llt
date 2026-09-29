import { ReactNode, useEffect, useRef, useState } from "react";
import { api, Commentary as Rec, fmt, InsightPeriods, Me, PeriodInfo, req } from "../api";
import Chart from "../components/Chart";
import Commentary from "../components/Commentary";
import PageHead from "../components/PageHead";
import { navigate } from "../nav";
import "./insights.css";

// Leadership Insights – the portal's landing page. One reporting period (grain + anchor month) drives every tile,
// comparison and chart; commentary is kept per reporting month and follows the manager → leader workflow.

const K = { orange: "#F47525", sky: "#52B2E5", crimson: "#A3194E", grey: "#565150", stone: "#B9AFAC" };
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const GRAINS = [["month", "Month"], ["quarter", "Quarter"], ["fytd", "FY to date"], ["r12", "Rolling 12 months"]] as const;
type Grain = (typeof GRAINS)[number][0];
type Sel = { grain: Grain; anchor: string };           // anchor = reporting month "YYYY-MM"
type DomainKey = "finance" | "hse" | "maintenance" | "operations";
type Domain = { key: DomainKey; title: string; short: string; owner: string; dash: string; caption: string };

const DOMAINS: Domain[] = [
  { key: "finance", title: "Finance", short: "Finance", owner: "CFO", dash: "finance",
    caption: "Actuals against budget and the year-end outlook (YEO)" },
  { key: "hse", title: "Health, safety & environment", short: "HSE", owner: "HSE Manager", dash: "hse",
    caption: "Incident observations, high potential events and injury frequency" },
  { key: "maintenance", title: "Maintenance", short: "Maintenance", owner: "Maintenance Manager", dash: "maintenance",
    caption: "Iona planned maintenance – weekly Maximo schedule" },
  { key: "operations", title: "Iona operations & market", short: "Operations", owner: "Commercial Manager", dash: "ops",
    caption: "Iona storage, customer nominations and the Victorian gas market" },
];

// ------------------------------------------------------------------------------------------------ period arithmetic
// Mirrors server/periods.py so the label updates instantly while the figures load.
const ymOf = (a: string) => { const [y, m] = a.slice(0, 7).split("-").map(Number); return { y, m }; };
const ym = (y: number, m: number) => `${y}-${String(m).padStart(2, "0")}`;
const addM = (a: string, n: number) => { const { y, m } = ymOf(a); const t = y * 12 + m - 1 + n; return ym(Math.floor(t / 12), (t % 12) + 1); };
const fyOf = (a: string) => { const { y, m } = ymOf(a); return m >= 7 ? y + 1 : y; };
const fyQ = (a: string) => Math.floor(((ymOf(a).m - 7 + 12) % 12) / 3) + 1;
const fyShort = (a: string) => `FY${String(fyOf(a) % 100).padStart(2, "0")}`;
const monLabel = (a: string) => { const { y, m } = ymOf(a); return `${MON[m - 1]} ${y}`; };

function startOf(s: Sel): string {
  const fyStart = `${fyOf(s.anchor) - 1}-07`;
  if (s.grain === "quarter") return addM(fyStart, (fyQ(s.anchor) - 1) * 3);
  if (s.grain === "fytd") return fyStart;
  if (s.grain === "r12") return addM(s.anchor, -11);
  return s.anchor;
}

function labelOf(s: Sel): string {
  if (s.grain === "quarter") {
    const st = startOf(s), qEnd = addM(st, 2), full = `Q${fyQ(s.anchor)} ${fyShort(s.anchor)}`;
    return s.anchor >= qEnd ? `${full} (${MON[ymOf(st).m - 1]}–${MON[ymOf(qEnd).m - 1]} ${ymOf(qEnd).y})` : `${full} to ${monLabel(s.anchor)}`;
  }
  if (s.grain === "fytd") return ymOf(s.anchor).m === 6 ? `${fyShort(s.anchor)} full year` : `${fyShort(s.anchor)} YTD to ${monLabel(s.anchor)}`;
  if (s.grain === "r12") return `12 months to ${monLabel(s.anchor)}`;
  return monLabel(s.anchor);
}

const pcpOf = (s: Sel): Sel => ({ grain: s.grain, anchor: addM(s.anchor, -12) });
const keyOf = (s: Sel) => `${s.grain}:${s.anchor}`;

/** Previous / next period: months for Month, FYTD and R12; whole quarters for Quarter. Null when out of range. */
function stepSel(s: Sel, n: number, min: string, max: string): Sel | null {
  let t: Sel = s.grain === "quarter" ? { ...s, anchor: addM(startOf(s), 3 * n + 2) } : { ...s, anchor: addM(s.anchor, n) };
  if (t.anchor > max) {
    if (s.grain === "quarter" && startOf(t) <= max) t = { ...t, anchor: max };   // the current quarter, to date
    else return null;
  }
  return t.anchor < min || t.anchor === s.anchor ? null : t;
}

// ------------------------------------------------------------------------------------------------ persistence
// The selection lives in the URL hash (#li=fytd:2026-08, shareable) and localStorage (survives a refresh).
const LS_KEY = "li.period";
const HASH_RE = /[#&]li=(month|quarter|fytd|r12):(\d{4}-\d{2})/;
function readSel(): Sel | null {
  const h = HASH_RE.exec(window.location.hash);
  if (h) return { grain: h[1] as Grain, anchor: h[2] };
  try {
    const v = JSON.parse(localStorage.getItem(LS_KEY) || "null");
    if (v && GRAINS.some((g) => g[0] === v.grain) && /^\d{4}-\d{2}$/.test(v.anchor)) return v;
  } catch { /* private mode */ }
  return null;
}
function writeSel(s: Sel) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(s)); } catch { /* private mode */ }
  try { window.history.replaceState(null, "", `#li=${keyOf(s)}`); } catch { /* sandboxed */ }
}
function clearHash() {
  if (HASH_RE.test(window.location.hash)) {
    try { window.history.replaceState(null, "", window.location.pathname + window.location.search); } catch { /* sandboxed */ }
  }
}
function validSel(s: Sel | null, p: InsightPeriods): Sel | null {
  return s && GRAINS.some((g) => g[0] === s.grain) && s.anchor >= p.min && s.anchor <= p.max ? s : null;
}

// ------------------------------------------------------------------------------------------------ data cache
// Summary and trends each run several warehouse queries (5–12 s cold); cache them for a few minutes so stepping back,
// switching the role lens or returning from a drill-down is instant.
const CACHE = new Map<string, { t: number; p: Promise<any> }>();
const TTL = 5 * 60_000;
function cached<T>(key: string, f: () => Promise<T>, keep: (v: T) => boolean = () => true): Promise<T> {
  const hit = CACHE.get(key);
  if (hit && Date.now() - hit.t < TTL) return hit.p;
  const p = f();
  CACHE.set(key, { t: Date.now(), p });
  p.then((v) => { if (!keep(v)) CACHE.delete(key); }, () => CACHE.delete(key));
  return p;
}

// ------------------------------------------------------------------------------------------------ formatting
const MONEY_K = (v: number) => fmt(v, "money");
function fv(v: number | null | undefined, kind: "money" | "count" | "pct" | "pj" | "num2"): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  if (kind === "money") return MONEY_K(v);
  if (kind === "pct") return `${(v * 100).toFixed(1)}%`;
  if (kind === "pj") return `${v.toFixed(1)} PJ`;
  if (kind === "num2") return v.toFixed(2);
  return Math.round(v).toLocaleString();
}
const isoParts = (d: string) => d.slice(0, 10).split("-").map(Number);
const dayMon = (d?: string | null) => { if (!d) return ""; const [, m, day] = isoParts(d); return `${day} ${MON[m - 1]}`; };
const monthEnd = (d: string) => { const [y, m] = isoParts(d); return new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10); };
const minIso = (a: string, b: string) => (a < b ? a : b);
const doy = (d: string) => { const [y, m, day] = isoParts(d); return Math.round((Date.UTC(y, m - 1, day) - Date.UTC(y, 0, 1)) / 864e5) + 1; };
const fyMonth = (d: string) => ((isoParts(d)[1] - 7 + 12) % 12) + 1;
const when = (s?: string | null) => (s ? new Date(s).toLocaleDateString("en-AU", { day: "numeric", month: "short" }) : "");

type Tone = "good" | "bad" | "neutral" | "muted";
type Delta = { arrow?: string; text: string; tone: Tone; vs?: string };

/** Change vs the prior corresponding period. `better` says which direction is good for the metric. */
function change(v: number | null | undefined, p: number | null | undefined, kind: Parameters<typeof fv>[1],
                better: "up" | "down" | "none"): Delta | null {
  if (v === null || v === undefined) return null;
  if (p === null || p === undefined) return { text: "no prior-year data", tone: "muted" };
  let text: string;
  if (kind === "pct") {
    const d = (v - p) * 100;
    if (Math.abs(d) < 0.05) return { arrow: "●", text: "no change", tone: "neutral", vs: fv(p, kind) };
    text = `${Math.abs(d).toFixed(1)} pts`;
  } else if (p === 0) {
    if (v === 0) return { arrow: "●", text: "no change", tone: "neutral", vs: fv(p, kind) };
    text = "from nil";
  } else {
    const r = ((v - p) / Math.abs(p)) * 100;
    if (Math.abs(r) < 0.05) return { arrow: "●", text: "no change", tone: "neutral", vs: fv(p, kind) };
    text = `${Math.abs(r).toFixed(Math.abs(r) >= 100 ? 0 : 1)}%`;
  }
  const up = v > p;
  const tone: Tone = better === "none" ? "neutral" : up === (better === "up") ? "good" : "bad";
  return { arrow: up ? "▲" : "▼", text, tone, vs: fv(p, kind) };
}

/** Actuals vs budget (or YEO vs budget): under budget is good. */
function vsBudget(v: number | null | undefined, b: number | null | undefined): Delta | null {
  if (v === null || v === undefined || !b) return null;
  const r = (v / b - 1) * 100;
  if (Math.abs(r) < 0.5) return { arrow: "●", text: "on budget", tone: "neutral" };
  return { arrow: r < 0 ? "▼" : "▲", text: `${Math.abs(r).toFixed(0)}% ${r < 0 ? "under" : "over"} budget`, tone: r < 0 ? "good" : "bad" };
}

// ------------------------------------------------------------------------------------------------ tiles
type TileSpec = { l: string; v: string | null; d?: Delta | null; s?: string; empty?: string; tone?: "good" | "bad"; tip?: string };

function Tile({ t, compare }: { t: TileSpec; compare: string }) {
  const title = [t.tip, t.d?.vs ? `${compare}: ${t.d.vs}` : ""].filter(Boolean).join("\n") || undefined;
  return (
    <div className="li-tile" title={title}>
      <div className="li-tl">{t.l}</div>
      {t.v !== null ? <div className={`li-tv ${t.tone ?? ""}`}>{t.v}</div> : <div className="li-tv li-na">{t.empty ?? "–"}</div>}
      <div className="li-td">
        {t.d ? <><span className={`li-d ${t.d.tone}`}>{t.d.arrow ? `${t.d.arrow} ` : ""}{t.d.text}</span>
          {t.d.vs && <span className="li-vs"> vs {t.d.vs}</span>}</> : " "}
      </div>
      {t.s && <div className="li-ts">{t.s}</div>}
    </div>
  );
}
const SkeletonTiles = () => <>{[0, 1, 2, 3].map((i) => <div key={i} className="li-tile li-skel"><i /><i /><i /></div>)}</>;

function financeTiles(f: any, p: PeriodInfo): TileSpec[] {
  const actualsTo = f.actuals_to ? minIso(p.end, monthEnd(f.actuals_to)) : null;
  const posted = f.actuals !== null && f.actuals !== undefined && !!actualsTo && actualsTo >= p.start;
  const partial = posted && actualsTo! < p.end;
  const actualsSub = posted ? `to ${dayMon(actualsTo)}${partial ? ` · ${MON[isoParts(p.end)[1] - 1]} not yet posted` : ""}` : "month not yet closed";
  const fy = `FY${String(Number(p.fy.slice(2)) % 100).padStart(2, "0")}`;
  return [
    { l: "Actuals", v: posted ? fv(f.actuals, "money") : null, empty: "Not yet posted", s: actualsSub,
      d: posted ? change(f.actuals, f.actuals_pcp, "money", "none") : null },
    { l: "Budget, same months", v: posted ? fv(f.budget, "money") : null, s: posted ? actualsSub : undefined,
      d: posted ? vsBudget(f.actuals, f.budget) : null, tip: "Actuals compared with the budget for the months posted" },
    { l: `${fy} year-end outlook`, v: fv(f.yeo_fy, "money"), d: vsBudget(f.yeo_fy, f.budget_fy),
      s: `budget ${fv(f.budget_fy, "money")}`, tip: `${fy} full-year budget ${fv(f.budget_fy, "money")}` },
    { l: "Open commitments", v: fv(f.committed, "money"), s: "open purchase orders" },
  ];
}

function hseTiles(h: any, p: PeriodInfo): TileSpec[] {
  const to = `to ${dayMon(h.data_to ? minIso(p.end, h.data_to) : p.end)}`;
  const trifrM = h.trifr_month ? `${MON[isoParts(h.trifr_month)[1] - 1]} ${isoParts(h.trifr_month)[0]}` : "";
  return [
    { l: "Observations reported", v: fv(h.obs, "count"), d: change(h.obs, h.obs_pcp, "count", "down"), s: to },
    { l: "HIGH risk observations", v: fv(h.high, "count"), d: change(h.high, h.high_pcp, "count", "down"), s: to },
    { l: "High potential events", v: fv(h.hpe, "count"), d: change(h.hpe, h.hpe_pcp, "count", "down"), s: "target: nil",
      tone: h.hpe ? "bad" : h.hpe === 0 ? "good" : undefined },
    { l: "TRIFR", v: h.trifr == null ? null : fv(h.trifr, "num2"), d: change(h.trifr, h.trifr_pcp, "num2", "down"),
      s: `rolling 12 months`, tip: `Total recordable injury frequency rate per million hours worked, rolling 12 months${trifrM ? ` to ${trifrM}` : ""}` },
  ];
}

function maintenanceTiles(m: any, p: PeriodInfo): TileSpec[] {
  const snap = m.snapshot_date ? `as at ${dayMon(m.snapshot_date)} snapshot` : "no snapshot in period";
  const hasWeeks = (m.weeks ?? 0) > 0 && m.compliance !== null;
  const comp: TileSpec = hasWeeks
    ? { l: "Schedule compliance", v: fv(m.compliance, "pct"), d: change(m.compliance, m.compliance_pcp, "pct", "up"),
        s: `${m.weeks} week${m.weeks === 1 ? "" : "s"} to w/c ${dayMon(m.compliance_latest_week)}` }
    : m.compliance_latest !== null && m.compliance_latest !== undefined
      ? { l: "Schedule compliance", v: fv(m.compliance_latest, "pct"), s: `latest week w/c ${dayMon(m.compliance_latest_week)}`,
          d: { text: "no weeks in period", tone: "muted" },
          tip: `No schedule weeks fall in ${p.label}; showing the latest week available` }
      : { l: "Schedule compliance", v: null, s: "no schedule data" };
  return [
    comp,
    { l: "Overdue safety-critical", v: m.overdue_sc == null ? null : fv(m.overdue_sc, "count"),
      d: change(m.overdue_sc, m.overdue_sc_pcp, "count", "down"), s: snap, tone: m.overdue_sc ? "bad" : undefined },
    { l: "Backlog excl. PMs", v: m.backlog_ex_pm == null ? null : fv(m.backlog_ex_pm, "count"),
      d: change(m.backlog_ex_pm, m.backlog_ex_pm_pcp, "count", "down"), s: snap, tip: "Open corrective work orders, excluding preventive maintenance" },
    { l: "Open P2 excl. PMs", v: m.open_p2 == null ? null : fv(m.open_p2, "count"),
      d: change(m.open_p2, m.open_p2_pcp, "count", "down"), s: snap },
  ];
}

function operationsTiles(o: any, p: PeriodInfo): TileSpec[] {
  const fill = o.fill_pct != null ? ` · ${(o.fill_pct * 100).toFixed(0)}% full` : "";
  const to = `to ${dayMon(o.demand_to || p.end)}`;
  return [
    { l: "Iona inventory", v: o.inventory_pj == null ? null : fv(o.inventory_pj, "pj"),
      d: change(o.inventory_pj, o.inventory_pcp, "pj", "none"), s: o.as_of ? `as at ${dayMon(o.as_of)}${fill}` : undefined },
    { l: "Nominations within ±4%", v: o.noms_within_tol == null ? null : fv(o.noms_within_tol, "pct"),
      d: change(o.noms_within_tol, o.noms_within_tol_pcp, "pct", "up"), s: "of customer deliveries", tip: "Daily customer deliveries within ±4% of nomination",
      empty: "No nominations" },
    { l: "Victorian gas demand", v: o.vic_demand_pj == null ? null : fv(o.vic_demand_pj, "pj"),
      d: change(o.vic_demand_pj, o.vic_demand_pcp_pj, "pj", "none"), s: to },
    { l: "Iona withdrawals", v: o.withdrawals_pj == null ? null : fv(o.withdrawals_pj, "pj"),
      s: `injections ${fv(o.injections_pj, "pj")}` },
  ];
}

// ------------------------------------------------------------------------------------------------ market pulse
// GET /api/market/pulse is owned by the Market Intelligence hub; read it defensively and hide the card on any doubt.
type Pulse = { headline: string; week?: string; weekLabel?: string; items: { title: string; signal?: string; source?: string }[];
               counts?: { total?: number; Threat?: number; Opportunity?: number; Watch?: number } };
const str = (v: any) => (typeof v === "string" && v.trim() ? v.trim() : "");
function parsePulse(d: any): Pulse | null {
  if (!d || typeof d !== "object" || d.available === false) return null;
  const b = d.brief && typeof d.brief === "object" ? d.brief : d;
  const asList = (v: any) => { if (typeof v === "string") { try { v = JSON.parse(v); } catch { return null; } } return Array.isArray(v) ? v : null; };
  const raw = [d.items, d.top, d.top_items, d.highlights, d.signals, d.headlines, b.developments, b.developments_json].map(asList).find((x) => x?.length) || [];
  const items = raw.map((x: any) => typeof x === "string" ? { title: x }
    : { title: str(x?.title) || str(x?.headline) || str(x?.text), signal: str(x?.signal), source: str(x?.source_name) || str(x?.source) })
    .filter((x: any) => x.title).slice(0, 3);
  const headline = str(b.headline) || str(d.headline) || str(b.title) || str(d.summary);
  if (!headline && !items.length) return null;
  const week = str(d.week_start) || str(b.week_start);
  const counts = d.counts && typeof d.counts === "object" ? d.counts : undefined;
  return { headline, week, weekLabel: str(d.label), items, counts };
}

function MarketCard({ p }: { p: Pulse }) {
  return (
    <button className="card li-mkt" onClick={() => navigate("market")}>
      <div className="li-mkt-h"><b>Market this week</b>
        {(p.weekLabel || p.week) && <span className="note">{p.weekLabel || `w/c ${dayMon(p.week)}`}</span>}</div>
      {p.headline && <div className="li-mkt-hl">{p.headline}</div>}
      {!!p.counts?.total && <div className="note">{p.counts.total} signals · {p.counts.Threat ?? 0} threats · {p.counts.Opportunity ?? 0} opportunities
        {p.counts.Watch ? ` · ${p.counts.Watch} to watch` : ""}</div>}
      {p.items.length > 0 && <ul>{p.items.map((it, i) => (
        <li key={i}>{it.signal && <span className={`li-sig s-${it.signal.toLowerCase()}`}>{it.signal}</span>}{it.title}</li>))}</ul>}
      <span className="li-link">Open Market Intelligence →</span>
    </button>
  );
}

// ------------------------------------------------------------------------------------------------ board scorecard
const WF = [["OPEN", "Open"], ["OWNER_SUBMITTED", "Owners submitted"], ["LLT_REVIEWED", "Leadership reviewed"],
            ["BOARD_ENDORSED", "Board endorsed"], ["LOCKED", "Locked"]];

function ScorecardStrip({ sc }: { sc: any }) {
  const at = WF.findIndex((w) => w[0] === sc.state);
  const pct = (v: any) => (v === null || v === undefined ? "–" : `${Number(v).toFixed(1)}%`);
  return (
    <div className="card li-sc">
      <div className="li-sc-t"><span className="note">Board scorecard</span><b>{sc.label}</b></div>
      <div className="li-sc-stats">
        <div><span>Status index</span><b>{pct(sc.status_index_pct)}</b></div>
        <div className={sc.kpis_at_risk ? "warn" : ""}><span>KPIs at risk</span><b>{sc.kpis_at_risk ?? "–"}<small> of {sc.kpis ?? "–"}</small></b></div>
        <div className={sc.kpis_off_track ? "bad" : ""}><span>Off track</span><b>{sc.kpis_off_track ?? "–"}</b></div>
        {sc.weighted_board_score_pct !== null && sc.weighted_board_score_pct !== undefined &&
          <div><span>Board score</span><b>{pct(sc.weighted_board_score_pct)}</b></div>}
      </div>
      <div className="li-wf" title={`Workflow: ${WF[at]?.[1] ?? sc.state}`}>
        {WF.map(([k, l], i) => <span key={k} className={i < at ? "done" : i === at ? "on" : ""}><i />{i === at ? l : ""}</span>)}
      </div>
      <button className="li-link" onClick={() => navigate("boardpack", { period: sc.period_code })}>Open board pack →</button>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ role summaries
const ST_LABEL: Record<string, string> = { NONE: "Not started", DRAFT: "Draft", SUBMITTED: "With leader", APPROVED: "Approved", RETURNED: "Returned" };

function ReviewSummary({ items, loaded, month, jump }: { items: Record<string, Rec | null>; loaded: boolean; month: string; jump: (k: string) => void }) {
  const waiting = DOMAINS.filter((d) => items[d.key]?.status === "SUBMITTED");
  const approved = DOMAINS.filter((d) => items[d.key]?.status === "APPROVED").length;
  const returned = DOMAINS.filter((d) => items[d.key]?.status === "RETURNED").length;
  return (
    <div className={`li-role r-llt ${waiting.length ? "has" : ""}`}>
      <div className="li-role-n">{loaded ? waiting.length : "·"}</div>
      <div className="li-role-main">
        <div className="li-role-h"><b>For your review</b><span className="note">{month} commentary from the managers</span></div>
        {!loaded ? <span className="note">Checking…</span> : waiting.length ? (
          <div className="li-role-items">{waiting.map((d) => {
            const r = items[d.key]!;
            return <button key={d.key} className="li-chip" onClick={() => jump(d.key)}>
              <b>{d.short}</b><span>{r.author_name || r.author_email}{r.submitted_at ? ` · submitted ${when(r.submitted_at)}` : ""}</span>→</button>;
          })}</div>
        ) : <span className="note">Nothing is waiting for you. {approved} of 4 approved{returned ? `, ${returned} returned to the author` : ""}.</span>}
      </div>
    </div>
  );
}

function ProgressSummary({ items, loaded, month, jump, admin }: { items: Record<string, Rec | null>; loaded: boolean; month: string;
                                                                  jump: (k: string) => void; admin: boolean }) {
  const st = (k: string) => items[k]?.status ?? "NONE";
  const n = (s: string) => DOMAINS.filter((d) => st(d.key) === s).length;
  return (
    <div className="li-role r-mgr">
      <div className="li-role-main">
        <div className="li-role-h"><b>{admin ? "Commentary" : "Your commentary"} for {month}</b>
          {loaded && <span className="note">{n("APPROVED")} of 4 approved{admin && n("SUBMITTED") ? ` · ${n("SUBMITTED")} awaiting leader review` : ""}</span>}</div>
        <div className="li-prog">{DOMAINS.map((d) => (
          <button key={d.key} className={`li-seg-st st-${loaded ? st(d.key) : "LOADING"}`} onClick={() => jump(d.key)}
                  title={`${d.title} – ${ST_LABEL[st(d.key)]}`}>
            <span>{d.short}</span><b>{loaded ? ST_LABEL[st(d.key)] : "…"}</b></button>))}
        </div>
        {loaded && <div className="note li-counts">{n("DRAFT")} drafted · {n("SUBMITTED")} submitted · {n("APPROVED")} approved · {n("RETURNED")} returned
          {n("NONE") ? ` · ${n("NONE")} not started` : ""}</div>}
      </div>
    </div>
  );
}

/** Board / observer view: approved text only, no workflow chrome. */
function ApprovedNote({ rec, month, owner }: { rec: Rec | null | undefined; month: string; owner: string }) {
  if (rec === undefined) return null;
  return (
    <div className="li-note">
      <div className="li-note-h"><b>Management commentary</b><span className="note">{month}</span></div>
      {rec && rec.status === "APPROVED"
        ? <><div className="li-note-b">{rec.body.split(/\n{2,}/).map((p, i) => <p key={i}>{p}</p>)}</div>
            <div className="note">{rec.author_name || owner} · {owner}</div></>
        : <div className="note">No commentary for {month}.</div>}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ domain card
function DomainCard({ d, tiles, compare, tilesStale, chartStale, err, chartHead, chart, footer, commentary, flash }: {
  d: Domain; tiles: TileSpec[] | null; compare: string; tilesStale: boolean; chartStale: boolean; err: boolean;
  chartHead: ReactNode; chart: ReactNode; footer?: ReactNode; commentary: ReactNode; flash: boolean;
}) {
  return (
    <section id={`li-${d.key}`} className={`card li-card ${flash ? "li-flash" : ""}`}>
      <div className="li-card-h">
        <div><h3>{d.title}</h3><div className="note">{d.caption}</div></div>
        <button className="li-link" onClick={() => navigate("dashboards", { dashboard: d.dash })}>Open detailed dashboard →</button>
      </div>
      <div className={tilesStale ? "li-stale" : ""}>
        {err && <div className="li-warn">Some figures could not be loaded right now – try again shortly.</div>}
        <div className="li-tiles">{tiles ? tiles.map((t) => <Tile key={t.l} t={t} compare={compare} />) : <SkeletonTiles />}</div>
        {footer}
      </div>
      <div className={chartStale ? "li-stale" : ""}>
        <div className="li-chart-h">{chartHead}</div>
        {chart}
      </div>
      <div id={`li-${d.key}-cm`} className="li-cm">{commentary}</div>
    </section>
  );
}

const ChartSkel = () => <div className="li-chart-skel" />;
const NoData = ({ children }: { children: ReactNode }) => <div className="chart-empty">{children}</div>;
const Unavailable = () => <NoData>This chart is unavailable right now – try again shortly.</NoData>;

// ------------------------------------------------------------------------------------------------ page
export default function InsightsPage({ me }: { me: Me }) {
  const [periods, setPeriods] = useState<InsightPeriods | null>(null);
  const [sel, setSel] = useState<Sel | null>(() => readSel());
  const [sum, setSum] = useState<{ key: string; d: any } | null>(null);
  const [tr, setTr] = useState<{ key: string; d: any } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cm, setCm] = useState<{ key: string; items: Record<string, Rec | null>; loaded: boolean }>({ key: "", items: {}, loaded: false });
  const [pulse, setPulse] = useState<Pulse | null>(null);
  const [opsView, setOpsView] = useState<"demand" | "inventory" | "cumulative">("demand");
  const [flash, setFlash] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);   // period key whose figures could not be loaded
  const [retry, setRetry] = useState(0);
  const flashT = useRef<number>();

  const role = me.role;
  const reader = !["LLT", "KPI_OWNER", "ADMIN"].includes(role);          // Board, observers: approved text only
  const idKey = `${me.email}|${me.personas.join(",")}|${me.persona_team ?? ""}`;

  // Periods (and the default) – a stored selection starts loading straight away, then is validated.
  useEffect(() => {
    api.insightPeriods().then((p) => {
      setPeriods(p);
      setSel((s) => validSel(s, p) ?? (p.default as Sel));
    }).catch((e) => setErr(`Reporting periods unavailable (${e})`));
    req<any>("/api/market/pulse").then((d) => setPulse(parsePulse(d))).catch(() => setPulse(null));
    return () => { clearHash(); window.clearTimeout(flashT.current); };
  }, []);

  // Figures for the selected period: two parallel calls, previous period stays on screen (dimmed) until they land.
  useEffect(() => {
    if (!sel) return;
    writeSel(sel);
    const k = keyOf(sel);
    let live = true;
    setErr(null); setFailed(null);
    const t = window.setTimeout(() => {             // debounce rapid ‹ › clicks
      cached(`s|${idKey}|${role}|${k}`, () => api.summary(sel.grain, sel.anchor), (v: any) => !Object.keys(v?.errors || {}).length)
        .then((d) => { if (live) setSum({ key: k, d }); })
        .catch((e) => { if (live) { setErr(`The figures for ${labelOf(sel)} could not be loaded (${e instanceof Error ? e.message : e}).`); setFailed(k); } });
      cached(`t|${idKey}|${k}`, () => api.trends(sel.grain, sel.anchor),
             (v: any) => !Object.values(v || {}).some((x: any) => x?.error))
        .then((d) => { if (live) setTr({ key: k, d }); })
        .catch(() => { if (live) setTr({ key: k, d: {} }); });
    }, sum ? 220 : 0);
    return () => { live = false; window.clearTimeout(t); };
  }, [sel?.grain, sel?.anchor, retry]);

  // Commentary status for the reporting month (drives the role summaries; the editors load their own record).
  const monthKey = sel ? `M:${sel.anchor}` : "";
  const month = sel ? monLabel(sel.anchor) : "";
  useEffect(() => {
    if (!monthKey) return;
    let live = true;
    setCm((c) => (c.key === monthKey ? c : { key: monthKey, items: {}, loaded: false }));
    api.commentary("insights", monthKey)
      .then((d) => { if (live) setCm((c) => ({ key: monthKey, loaded: true, items: mergeItems(c.key === monthKey ? c.items : {}, d.items) })); })
      .catch(() => { if (live) setCm((c) => ({ ...c, key: monthKey, loaded: true })); });
    return () => { live = false; };
  }, [monthKey, role]);
  const onCm = (subject: string, mk: string) => (rec: Rec | null) =>
    setCm((c) => (c.key !== mk ? c : { ...c, items: mergeItems(c.items, { [subject]: rec }) }));

  const jump = (k: string) => {
    document.getElementById(`li-${k}-cm`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    setFlash(k); window.clearTimeout(flashT.current);
    flashT.current = window.setTimeout(() => setFlash(null), 1800);
  };

  if (!sel) {
    return <div><PageHead title="Leadership Insights" me={me} sub="Iona Ops Trust · all amounts AUD" />
      {err ? <div className="err">{err}</div> : <div className="li-bar li-skelbar" />}</div>;
  }

  const k = keyOf(sel);
  const label = labelOf(sel);
  const compare = `vs ${labelOf(pcpOf(sel))}`;
  const S = sum?.d, T = tr?.d;
  const sumStale = !!sum && sum.key !== k, trStale = !!tr && tr.key !== k;
  const loading = (!sum || !tr || sumStale || trStale) && failed !== k;
  const tryAgain = () => { CACHE.delete(`s|${idKey}|${role}|${k}`); CACHE.delete(`t|${idKey}|${k}`); setRetry((n) => n + 1); };
  const P: PeriodInfo | undefined = S?.period;               // the period the figures on screen belong to
  const TP: PeriodInfo | undefined = T?.period;
  const tl = S?.tiles || {};
  const errs = S?.errors || {};
  const prev = periods ? stepSel(sel, -1, periods.min, periods.max) : null;
  const next = periods ? stepSel(sel, 1, periods.min, periods.max) : null;
  const inProgress = !!periods && sel.anchor > periods.latest_closed;
  const hl = (p?: PeriodInfo): [string, string] | null => (p ? [p.start, p.end] : null);
  const hlLabel = TP?.label;
  const sc = S?.scorecard;

  // ---- charts
  const finCum = TP ? TP.grain !== "r12" : true;
  const finChart = !T ? <ChartSkel /> : T.finance?.error ? <Unavailable /> : !T.finance?.rows?.length ? <NoData>No finance data for this period.</NoData> : finCum
    ? <Chart rows={T.finance.rows} x="cat" y="money" colors={{ Budget: K.sky, YEO: K.orange, Actuals: K.grey }} dashed={["Budget"]}
             highlight={TP ? [fyMonth(TP.start), fyMonth(TP.end)] : null} highlightLabel={hlLabel} />
    : <Chart rows={T.finance.rows} x="month" y="money" colors={{ Budget: K.sky, Actuals: K.grey }} dashed={["Budget"]}
             highlight={hl(TP)} highlightLabel={hlLabel} />;
  const hseChart = !T ? <ChartSkel /> : T.hse?.error ? <Unavailable /> : !T.hse?.rows?.length ? <NoData>No observations in this window.</NoData>
    : <Chart rows={T.hse.rows} kind="bar" x="month" y="count" colors={{ Observations: K.crimson }} highlight={hl(TP)} highlightLabel={hlLabel} />;
  const mntChart = !T ? <ChartSkel /> : T.maintenance?.error ? <Unavailable /> : !T.maintenance?.rows?.length ? <NoData>No Maximo schedule data for this period.</NoData>
    : <Chart rows={T.maintenance.rows} x="week" y="pct" zero={false} area colors={{ "Compliance %": K.orange }}
             highlight={hl(TP)} highlightLabel={hlLabel} />;
  const years = Array.from(new Set((T?.cumulative?.rows || []).map((r: any) => String(r.series)))).sort().reverse() as string[];
  const yearColors = Object.fromEntries(years.map((y, i) => [y, [K.orange, K.crimson, K.sky, K.stone][i] ?? K.grey]));
  const cumHl: [number, number] | null = TP
    ? (TP.start.slice(0, 4) === TP.end.slice(0, 4) ? [doy(TP.start), doy(TP.end)] : [1, doy(TP.end)]) : null;
  const opsSeries = T ? (opsView === "demand" ? T.market : opsView === "inventory" ? T.operations : T.cumulative) : undefined;
  const opsRows = opsSeries?.rows;
  const opsChart = !T ? <ChartSkel /> : opsSeries?.error ? <Unavailable /> : !opsRows?.length ? <NoData>No data for this view.</NoData>
    : opsView === "demand"
      ? <Chart rows={opsRows} kind="bar" x="month" y="pj" colors={{ "This year": K.orange, "Prior year": K.stone }} highlight={hl(TP)} highlightLabel={hlLabel} />
      : opsView === "inventory"
        ? <Chart rows={opsRows} x="week" y="pj" area colors={{ "Inventory (PJ)": K.sky }} highlight={hl(TP)} highlightLabel={hlLabel} />
        : <Chart rows={opsRows} x="doy" y="pj" colors={yearColors} highlight={cumHl} highlightLabel={hlLabel} />;
  const demandPartial = S?.tiles?.operations?.demand_to && P && S.tiles.operations.demand_to < P.end;

  const m = tl.maintenance || {};
  const noWeeks = P && m && (m.weeks ?? 0) === 0 && m.compliance_latest_week;
  const h = tl.hse || {};

  const commentaryFor = (d: Domain) => reader
    ? <ApprovedNote rec={cm.loaded && cm.key === monthKey ? (cm.items[d.key] ?? null) : undefined} month={month} owner={d.owner} />
    : <Commentary me={me} scope="insights" subject={d.key} periodKey={monthKey} periodLabel={month} owner={d.owner} compact
                  title="Management commentary" onChange={onCm(d.key, monthKey)}
                  placeholder={`${d.short} in ${month}: what happened, why it matters and what happens next…`} />;

  const cards: { d: Domain; tiles: TileSpec[] | null; chartHead: ReactNode; chart: ReactNode; footer?: ReactNode }[] = [
    { d: DOMAINS[0], tiles: P && S ? financeTiles(tl.finance || {}, P) : null, chart: finChart,
      chartHead: <div><b>{finCum ? "Cumulative budget, YEO and actuals" : "Monthly actuals and budget"}</b>
        <span className="note"> · {finCum ? `${TP?.fy.replace("FY20", "FY") ?? ""} by month` : "24 months"}</span></div> },
    { d: DOMAINS[1], tiles: P && S ? hseTiles(h, P) : null, chart: hseChart,
      footer: S && h.open_now !== undefined && <div className="li-now">Open now: <b>{fv(h.open_now, "count")}</b> observations ·
        <b> {fv(h.open_high_now, "count")}</b> HIGH risk · <b>{fv(h.open_investigations, "count")}</b> investigations</div>,
      chartHead: <div><b>Observations reported</b><span className="note"> · per month</span></div> },
    { d: DOMAINS[2], tiles: P && S ? maintenanceTiles(m, P) : null, chart: mntChart,
      chartHead: <div><b>Schedule compliance</b><span className="note"> · completed ÷ scheduled work orders, by week
        {noWeeks ? ` · no schedule weeks in ${monLabel(P!.anchor)} yet` : ""}</span></div> },
    { d: DOMAINS[3], tiles: P && S ? operationsTiles(tl.operations || {}, P) : null, chart: opsChart,
      chartHead: <>
        <div className="seg li-ops-seg">
          {([["demand", "VIC demand vs prior year"], ["inventory", "Iona inventory"], ["cumulative", "Cumulative by year"]] as const).map(([v, l]) =>
            <button key={v} className={opsView === v ? "on" : ""} onClick={() => setOpsView(v)}>{l}</button>)}
        </div>
        <div><b>{opsView === "demand" ? "Victorian gas demand" : opsView === "inventory" ? "Iona inventory" : "Cumulative Victorian gas demand"}</b>
          <span className="note"> · {opsView === "demand" ? `PJ per month vs the same month a year earlier${demandPartial ? ` · ${monLabel(P!.anchor)} to ${dayMon(S.tiles.operations.demand_to)}, same days last year` : ""}`
            : opsView === "inventory" ? "PJ, weekly average" : "PJ by day of year, calendar years"}</span></div>
      </> },
  ];

  return (
    <div className="li">
      <PageHead title="Leadership Insights" me={me} sub={`Iona Ops Trust · ${label} · all amounts AUD`} />

      <div className="li-bar">
        <div className="li-grain" role="tablist" aria-label="Reporting period">
          {GRAINS.map(([g, l]) => (
            <button key={g} role="tab" aria-selected={sel.grain === g} className={sel.grain === g ? "on" : ""}
                    onClick={() => setSel({ ...sel, grain: g })}>{l}</button>))}
        </div>
        <div className="li-step">
          <button aria-label="Previous period" disabled={!prev} onClick={() => prev && setSel(prev)}>‹</button>
          <select aria-label="Reporting month" value={sel.anchor} onChange={(e) => setSel({ ...sel, anchor: e.target.value })}>
            {(periods?.months || [sel.anchor]).map((mo) => (
              <option key={mo} value={mo}>{monLabel(mo)}{periods && mo > periods.latest_closed ? " · in progress" : ""}
                {periods && mo === periods.latest_closed ? " · latest closed" : ""}</option>))}
          </select>
          <button aria-label="Next period" disabled={!next} onClick={() => next && setSel(next)}>›</button>
        </div>
        <button className="li-latest" disabled={!periods || sel.anchor === periods.latest_closed}
                onClick={() => periods && setSel({ ...sel, anchor: periods.latest_closed })}>Latest</button>
        <div className="li-label">
          <b>{label}</b><span>{compare}</span>
        </div>
        {inProgress && <span className="li-flag" title="Figures cover the days reported so far; finance actuals post after month end">Month in progress</span>}
        <div className="li-status">{loading && <><span className="spinner" /> {sum ? "Updating…" : "Loading…"}</>}</div>
      </div>

      {err && <div className="err" style={{ marginBottom: 10 }}>{err}{failed === k && <>{" "}
        <button className="linkish" style={{ fontSize: 13 }} onClick={tryAgain}>Try again</button></>}</div>}

      {role === "LLT" && <ReviewSummary items={cm.key === monthKey ? cm.items : {}} loaded={cm.key === monthKey && cm.loaded} month={month} jump={jump} />}
      {(role === "KPI_OWNER" || role === "ADMIN") &&
        <ProgressSummary items={cm.key === monthKey ? cm.items : {}} loaded={cm.key === monthKey && cm.loaded} month={month} jump={jump} admin={role === "ADMIN"} />}

      {(sc || pulse) && (
        <div className={`li-top ${sc && pulse ? "two" : ""} ${sumStale ? "li-stale" : ""}`}>
          {sc && <ScorecardStrip sc={sc} />}
          {pulse && <MarketCard p={pulse} />}
        </div>
      )}

      <div className="li-grid">
        {cards.map((c) => (
          <DomainCard key={c.d.key} d={c.d} tiles={c.tiles} compare={compare} tilesStale={sumStale} chartStale={trStale}
                      err={!!(errs[c.d.key] || (c.d.key === "hse" && errs.hse_trifr))}
                      chartHead={c.chartHead} chart={c.chart} footer={c.footer} flash={flash === c.d.key}
                      commentary={commentaryFor(c.d)} />
        ))}
      </div>
    </div>
  );
}

/** Keep the newer of two records per subject (the page list and the editors load independently). */
function mergeItems(a: Record<string, Rec | null>, b: Record<string, Rec | null>): Record<string, Rec | null> {
  const out = { ...a };
  for (const [s, r] of Object.entries(b)) {
    const cur = out[s];
    if (!cur || (r && (r.updated_at > cur.updated_at || r.version > cur.version))) out[s] = r ?? cur ?? null;
  }
  return out;
}
