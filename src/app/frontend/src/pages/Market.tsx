import { useCallback, useEffect, useRef, useState } from "react";
import { Me } from "../api";
import { navigate, NavParams } from "../nav";
import PageHead from "../components/PageHead";
import Chart from "../components/Chart";
import Commentary from "../components/Commentary";
import StackedBars from "../components/market/StackedBars";
import Feed, { ItemDrawer } from "../components/market/Feed";
import { BriefCard, SynthesisCard, WeeklyHeadlines } from "../components/market/Brief";
import { GroupTag, Importance, SignalChip } from "../components/market/bits";
import {
  addWeeks, dayLabel, Filters, fmtSent, GROUP_COLOR, GROUPS, HORIZONS, Item, marketApi, Mode, mondayOf, sentimentWord, SIGNALS,
  Synthesis, Unavailable, ViewResp, weekLabel, WeeksResp,
} from "../components/market/types";
import "./market.css";

const SS = { week: "mi.week", horizon: "mi.horizon" };
const ss = {
  get: (k: string) => { try { return sessionStorage.getItem(k) || ""; } catch { return ""; } },
  set: (k: string, v: string) => { try { sessionStorage.setItem(k, v); } catch { /* private mode */ } },
};
const isUnavailable = (r: any): r is Unavailable => r && r.available === false;

const BANNER: Record<Mode, [string, string]> = {
  analyst: ["Analyst view", "Curate this week's signals for the leadership team: pin what matters, dismiss noise, add notes and adjust importance – then write the weekly commentary and submit it for leader review."],
  leader: ["Leader view", "The analyst's curated selection: pinned items first, noise removed, analyst notes alongside. Review the weekly commentary and approve it or return it with a note."],
  board: ["Board view", "The weekly brief, the approved commentary and the items the analyst selected for the board."],
};

function ModeBanner({ mode, me, curation }: { mode: Mode; me: Me; curation?: ViewResp["curation"] }) {
  const [title, text] = BANNER[mode];
  return (
    <div className={`mi-banner mi-banner-${mode}`}>
      <b>{title}{me.role === "ADMIN" ? " (administrator)" : ""}</b><span>{text}</span>
      {mode === "analyst" && curation && (
        <span className="mi-banner-stats">{curation.pinned} pinned · {curation.dismissed} dismissed · {curation.notes} note{curation.notes === 1 ? "" : "s"}</span>)}
    </div>
  );
}

function About() {
  return (
    <details className="mi-about">
      <summary>About this data</summary>
      <p>Public sources only: news coverage of the companies and gas-market topics on Lochard's watchlist, ASX announcements
        from listed customers and suppliers, Lochard Energy's newsroom, releases from AEMO, the AER, the AEMC and the ACCC,
        and targeted research on publishers' websites.</p>
      <p>New items are collected every day at 07:00 (Melbourne time). Each item is summarised and rated by AI for relevance,
        signal (opportunity, threat, watch) and importance from Lochard's perspective, and the Market Intelligence Analyst
        agent writes the weekly brief. AI summaries can be wrong or incomplete – check the original before acting on an item.
        Only short excerpts are shown; links open the original publisher.</p>
    </details>
  );
}

// ---------------------------------------------------------------------------------------------- week navigator
function WeekNav({ weeks, week, horizon, onWeek, onHorizon, windowLabel, loading }: {
  weeks: WeeksResp; week: string; horizon: number; onWeek: (w: string) => void; onHorizon: (h: number) => void;
  windowLabel?: string; loading: boolean;
}) {
  const opts = new Map<string, string>();
  const cw = weeks.current_week;
  opts.set(cw, `${weeks.current_label} (this week)`);
  weeks.weeks.forEach((w) => opts.set(w.week_start, `${w.label} · ${w.n_items} item${w.n_items === 1 ? "" : "s"}${w.has_brief ? "" : " · no brief"}`));
  if (!opts.has(week)) opts.set(week, weekLabel(week));
  const sorted = [...opts.entries()].sort((a, b) => b[0].localeCompare(a[0]));
  const earliest = weeks.earliest_week < cw ? weeks.earliest_week : cw;
  return (
    <div className="mi-nav">
      <div className="mi-weeknav" role="group" aria-label="Week">
        <button className="mi-arrow" aria-label="Previous week" title="Previous week" disabled={week <= earliest}
                onClick={() => onWeek(addWeeks(week, -1))}>‹</button>
        <select value={week} onChange={(e) => onWeek(e.target.value)} aria-label="Choose a week">
          {sorted.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <button className="mi-arrow" aria-label="Next week" title="Next week" disabled={week >= cw}
                onClick={() => onWeek(addWeeks(week, 1))}>›</button>
        <button className="mi-this" disabled={week === cw} onClick={() => onWeek(cw)}>This week</button>
      </div>
      <div className="mi-horizon">
        <span className="note">Horizon</span>
        <div className="seg" role="group" aria-label="Horizon">
          {HORIZONS.map(([h, l]) => <button key={h} className={horizon === h ? "on" : ""} onClick={() => onHorizon(h)}>{l}</button>)}
        </div>
      </div>
      <div className="mi-window">{windowLabel}{loading && <span className="spinner" style={{ marginLeft: 8 }} />}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- signals
function Delta({ now, prev, label }: { now: number; prev?: number | null; label: string }) {
  if (prev == null) return null;
  const d = now - prev;
  return <span className="mi-delta" title={`${label}: ${prev}`}>{d === 0 ? "same as" : `${d > 0 ? "+" : "−"}${Math.abs(d)} vs`} prior period</span>;
}

function SignalsCard({ v, onFilter }: { v: ViewResp; onFilter: (p: Partial<Filters>) => void }) {
  const s = v.stats!;
  const prev = s.prev;
  const maxN = Math.max(1, ...s.by_group.map((g) => g.n));
  return (
    <section className="card mi-signals">
      <div className="mi-sec-head"><h3>Signals at a glance</h3>
        <span className="note">{s.n_items} items · {s.n_sources} sources</span></div>
      <div className="mi-sigtiles">
        {SIGNALS.map((k) => (
          <button key={k} className={`mi-sigtile mi-sigtile-${k}`} onClick={() => onFilter({ signal: k })} title={`Show ${k.toLowerCase()} items`}>
            <SignalChip s={k} small /><b>{s.signals[k]}</b>
            {k === "Threat" && <Delta now={s.window_weekly.n_threats} prev={prev?.n_threats} label="Prior period" />}
            {k === "Opportunity" && <Delta now={s.window_weekly.n_opportunities} prev={prev?.n_opportunities} label="Prior period" />}
          </button>
        ))}
      </div>
      <div className="mi-sent">Average sentiment for Lochard: <b>{sentimentWord(s.avg_sentiment)}</b> <span className="note">(score {fmtSent(s.avg_sentiment)} on a −100 to +100 scale)</span></div>
      <table className="mi-gtable">
        <thead><tr><th>Entity group</th><th>Items</th><th title="Opportunities">▲</th><th title="Threats">▼</th><th title="Watch">◆</th><th>Sentiment</th></tr></thead>
        <tbody>{s.by_group.map((g) => (
          <tr key={g.entity_group} onClick={() => onFilter({ group: g.entity_group })} title={`Show ${g.entity_group} items`}>
            <td><GroupTag g={g.entity_group} /></td>
            <td><span className="mi-bar"><i style={{ width: `${(g.n / maxN) * 100}%`, background: GROUP_COLOR[g.entity_group] }} /></span>{g.n}</td>
            <td>{g.Opportunity || ""}</td><td>{g.Threat || ""}</td><td>{g.Watch || ""}</td>
            <td className={g.avg_sentiment != null && g.avg_sentiment < -0.1 ? "mi-neg" : g.avg_sentiment != null && g.avg_sentiment > 0.1 ? "mi-pos" : ""}>{fmtSent(g.avg_sentiment)}</td>
          </tr>
        ))}</tbody>
      </table>
    </section>
  );
}

function TrendCards({ v, onWeek, onFilter }: { v: ViewResp; onWeek: (w: string) => void; onFilter: (p: Partial<Filters>) => void }) {
  const t = v.trend!;
  const ctx = v.horizon === 1 ? `last ${t.weeks.length} weeks · selected week highlighted` : v.window.label;
  const maxE = Math.max(1, ...(v.top_entities || []).map((e) => e.n));
  return (
    <div className="mi-trends">
      <section className="card">
        <div className="chart-head"><div><b>Items per week by entity group</b><span className="note"> · {ctx}</span></div></div>
        <StackedBars rows={t.items_by_group} series={GROUPS} colors={GROUP_COLOR} highlight={v.week.week_start} onSelect={onWeek} />
      </section>
      <section className="card">
        <div className="chart-head"><div><b>Average sentiment for Lochard</b><span className="note"> · score by week, −100 to +100</span></div></div>
        <Chart rows={t.sentiment.map((p) => ({ ...p, series: "Sentiment score", y: Math.round(p.y * 1000) / 10 }))} x="week" y="num"
               colors={{ "Sentiment score": "#A3194E" }} height={228} />
      </section>
      <section className="card mi-entities">
        <div className="chart-head"><div><b>Most mentioned</b><span className="note"> · {v.horizon === 1 ? "this week" : "in the window"}</span></div></div>
        {!v.top_entities?.length ? <div className="chart-empty">No entities mentioned.</div> : (
          <ol>{v.top_entities.map((e) => (
            <li key={e.entity}>
              <button onClick={() => onFilter({ entity: e.entity })} title={e.relationship || `Show items mentioning ${e.entity}`}>
                <span className="mi-ent-name"><i style={{ background: GROUP_COLOR[e.entity_group || ""] || "#B9AFAC" }} />{e.entity}</span>
                <span className="mi-bar"><i style={{ width: `${(e.n / maxE) * 100}%`, background: GROUP_COLOR[e.entity_group || ""] || "#B9AFAC" }} /></span>
                <span className="mi-ent-n">{e.n}</span>
                <span className="mi-ent-sig">
                  {e.Opportunity ? <span className="mi-c-Opportunity">▲{e.Opportunity}</span> : null}
                  {e.Threat ? <span className="mi-c-Threat">▼{e.Threat}</span> : null}
                  {e.Watch ? <span className="mi-c-Watch">◆{e.Watch}</span> : null}
                </span>
              </button>
            </li>
          ))}</ol>
        )}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- brief area
function NoBrief({ v, latest, onWeek, onOpen }: { v: ViewResp; latest: string | null; onWeek: (w: string) => void; onOpen: (id: string) => void }) {
  const n = v.stats?.n_items;
  const items = n && v.mode !== "board" ? ` ${n} item${n === 1 ? " has" : "s have"} been collected${v.week.is_current ? " so far" : ""}.` : "";
  return (
    <div className="card mi-brief mi-nobrief">
      <div className="mi-by"><span className="mi-agent"><span aria-hidden>✦</span>Market Intelligence Analyst</span><span>Weekly brief · {v.week.label}</span>
        <span className="mi-wtd">Being prepared</span></div>
      <p>{v.week.is_current ? "The analyst agent writes this week's brief as the week's news is collected (daily at 07:00)."
        : "The analyst agent has not finished this week's brief yet."}{items}</p>
      {v.highlights.length > 0 && (
        <div className="mi-block">
          <h3>{v.mode === "board" ? "Selected by the analyst" : "Top signals so far"}</h3>
          <ol className="mi-devs">{v.highlights.map((h) => (
            <li key={h.item_id} className={`mi-dev mi-dev-${h.signal}`}>
              <div className="mi-dev-top"><SignalChip s={h.signal} small /><GroupTag g={h.entity_group} />
                {h.pinned && <span className="mi-pin-badge">📌 Pinned</span>}<Importance v={h.importance} /></div>
              <div className="mi-dev-title">{h.title}</div>
              {h.why_it_matters && <p>{h.why_it_matters}</p>}
              <div className="mi-cites"><span className="mi-cite">
                <button className="linkish" onClick={() => onOpen(h.item_id)}>{h.source_name || "Source"} · {dayLabel(h.published_date, false)}</button>
                {h.url && <a href={h.url} target="_blank" rel="noreferrer" title="Open the original">↗</a>}</span></div>
            </li>
          ))}</ol>
        </div>
      )}
      {latest && latest !== v.week.week_start && (
        <button onClick={() => onWeek(latest)}>Open the latest brief ({weekLabel(latest)})</button>)}
    </div>
  );
}

function SynthesisArea({ v, onWeek }: { v: ViewResp; onWeek: (w: string) => void }) {
  const [s, setS] = useState<Synthesis | null>(v.synthesis);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const tried = useRef("");
  const canRegen = v.mode === "analyst";
  const key = `${v.week.week_start}:${v.horizon}`;
  const run = useCallback(async (force: boolean) => {
    const wk = v.week.week_start, h = v.horizon;
    setBusy(true); setErr(null);
    try {
      let r = await marketApi.synthesis(wk, h, force);
      const t0 = Date.now();
      while (!isUnavailable(r) && r.status === "running" && Date.now() - t0 < 300000) {   // poll the background job
        await new Promise((ok) => setTimeout(ok, 4000));
        if (tried.current !== `${wk}:${h}`) return;                                        // the user moved on
        r = await marketApi.synthesisStatus(wk, h);
      }
      if (isUnavailable(r)) setErr(r.message);
      else if (r.status === "ready" && r.synthesis) setS(r.synthesis);
      else setErr(r.error || "The synthesis is taking longer than expected – please check back shortly.");
    } catch (e) {
      const m = String(e).replace(/^Error:\s*/, "").replace(/^\d{3}:\s*/, "");
      setErr(m || "The synthesis could not be generated just now.");
    } finally { setBusy(false); }
  }, [v.week.week_start, v.horizon]);
  useEffect(() => { setS(v.synthesis); }, [v]);
  useEffect(() => {                      // generated on demand: first view of the window, or when its briefs changed
    if ((!v.synthesis || v.synthesis.stale) && v.n_briefs > 0 && tried.current !== key) { tried.current = key; run(false); }
  }, [key, v.synthesis, v.n_briefs, run]);

  if (v.n_briefs === 0) return <div className="card mi-brief mi-nobrief"><p>No weekly briefs in this window yet.</p></div>;
  if (!s) return (
    <div className="card mi-brief mi-nobrief">
      <div className="mi-by"><span className="mi-agent"><span aria-hidden>✦</span>Market Intelligence Analyst</span><span>Multi-week synthesis · {v.window.label}</span></div>
      {busy ? <p><span className="spinner" /> The analyst agent is synthesising {v.n_briefs} weekly brief{v.n_briefs === 1 ? "" : "s"} – this can take a minute or two…</p>
        : err ? <><div className="err">{err}</div><button onClick={() => run(false)}>Try again</button></> : null}
    </div>
  );
  return (<>
    {err && <div className="err">{err}</div>}
    <SynthesisCard s={s} windowLabel={v.window.label} canRegenerate={canRegen} busy={busy}
                   onRegenerate={() => { tried.current = key; run(true); }} onWeek={onWeek} />
  </>);
}

// ---------------------------------------------------------------------------------------------- page
export default function MarketPage({ me, params }: { me: Me; params?: NavParams }) {
  const [weeks, setWeeks] = useState<WeeksResp | Unavailable | null>(null);
  const [week, setWeek] = useState<string | null>(params?.week ? mondayOf(params.week) : ss.get(SS.week) || null);
  const [horizon, setHorizon] = useState<number>(Number(params?.horizon || ss.get(SS.horizon)) || 1);
  const [view, setView] = useState<ViewResp | Unavailable | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>({ sort: "importance" });
  const [feedKey, setFeedKey] = useState(0);
  const seq = useRef(0);

  useEffect(() => {
    marketApi.weeks().then((w) => {
      setWeeks(w);
      if (!isUnavailable(w)) {
        setWeek((cur) => (cur && cur <= w.current_week ? cur : w.default_week));
        if (!HORIZONS.some(([h]) => h === horizon)) setHorizon(1);
      }
    }).catch((e) => setErr(String(e)));
  }, []);

  const loadView = useCallback(() => {
    if (!week) return;
    const n = ++seq.current;
    setLoading(true); setErr(null);
    marketApi.view(week, horizon).then((v) => { if (n === seq.current) setView(v); })
      .catch((e) => { if (n === seq.current) setErr(String(e)); })
      .finally(() => { if (n === seq.current) setLoading(false); });
  }, [week, horizon]);
  useEffect(() => { loadView(); if (week) { ss.set(SS.week, week); ss.set(SS.horizon, String(horizon)); } }, [loadView]);

  // curation changes: adjust the banner counts locally (the feed updates its own cards)
  const onCurated = (b: Item, a: Item) => setView((p) => {
    if (!p || isUnavailable(p)) return p;
    const d = (f: (i: Item) => boolean) => Number(f(a)) - Number(f(b));
    const c = p.curation;
    return { ...p, curation: { pinned: c.pinned + d((i) => i.pinned), dismissed: c.dismissed + d((i) => i.dismissed),
                                notes: c.notes + d((i) => !!i.note), overrides: c.overrides + d((i) => i.importance_override != null) } };
  });

  const goWeek = (w: string, h = 1) => { setWeek(w); setHorizon(h); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const filterFeed = (p: Partial<Filters>) => {
    setFilters((f) => ({ sort: f.sort, show_dismissed: f.show_dismissed, ...p }));
    setTimeout(() => document.getElementById("mi-feed")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  };

  const drill = <button className="mi-drill" onClick={() => navigate("dashboards", { dashboard: "market" })}>Open detailed dashboard →</button>;
  const head = <PageHead title="Market Intelligence" me={me} right={drill}
                         sub="What moved this week for Lochard, its customers, competitors, suppliers, regulators and the east-coast gas market." />;

  if (err && !view) return <div>{head}<div className="err">{err}</div></div>;
  if (!weeks || (!view && !isUnavailable(weeks))) return <div>{head}<div className="card note">Loading market intelligence…</div></div>;
  if (isUnavailable(weeks) || isUnavailable(view)) {
    const u = (isUnavailable(weeks) ? weeks : view) as Unavailable;
    return (
      <div>{head}
        <div className="card mi-preparing"><div className="mi-prep-icon" aria-hidden>◉</div>
          <div><h3>{u.state === "preparing" ? "Market data is being prepared" : "Market data is unavailable"}</h3><p>{u.message}</p></div></div>
        <About />
      </div>
    );
  }
  const v = view as ViewResp;
  const mode = v.mode;
  const brief = v.horizon === 1
    ? (v.brief ? <BriefCard brief={v.brief} onOpenItem={setOpenId} />
      : <NoBrief v={v} latest={(weeks as WeeksResp).latest_brief_week} onWeek={(w) => goWeek(w, 1)} onOpen={setOpenId} />)
    : <SynthesisArea v={v} onWeek={(w) => goWeek(w, 1)} />;
  const commentary = (
    <section className="card mi-comm">
      <Commentary me={me} scope="market" subject="brief" periodKey={v.week.period_key} periodLabel={v.week.label}
                  title={mode === "analyst" ? "Your commentary for the leadership team" : "Analyst commentary"}
                  placeholder={`What matters for Lochard in the ${v.week.label.replace(/^Week/, "week")}, why, and what we should do next…`} />
      {mode === "analyst" && <div className="note mi-comm-hint">Draft with AI starts from the agent's brief and your pinned items and notes. A leader approves it before the board sees it.</div>}
      {v.horizon > 1 && <div className="note mi-comm-hint">Commentary is written weekly – this is the commentary for the last week in the window.</div>}
    </section>
  );

  return (
    <div className={`mi-page${loading ? " mi-loading" : ""}`}>
      {head}
      <ModeBanner mode={mode} me={me} curation={v.curation} />
      <WeekNav weeks={weeks as WeeksResp} week={v.week.week_start} horizon={v.horizon} windowLabel={v.window.label} loading={loading}
               onWeek={(w) => setWeek(w)} onHorizon={(h) => setHorizon(h)} />
      {err && <div className="err">{err}</div>}

      <div className="mi-top">
        <div className="mi-main">
          {brief}
          {v.horizon > 1 && <WeeklyHeadlines briefs={v.briefs} onWeek={(w) => goWeek(w, 1)} />}
        </div>
        <div className="mi-side">
          {commentary}
          {mode !== "board" && v.stats && <SignalsCard v={v} onFilter={filterFeed} />}
        </div>
      </div>

      {mode !== "board" && v.trend && <TrendCards v={v} onWeek={(w) => goWeek(w, 1)} onFilter={filterFeed} />}

      <Feed week={v.week.week_start} horizon={v.horizon} mode={mode} facets={v.facets} f={filters} setF={setFilters}
            onChanged={onCurated} onOpen={setOpenId} refresh={feedKey} />
      <About />
      {openId && <ItemDrawer id={openId} mode={mode} onClose={() => setOpenId(null)}
                             onSaved={(b, a) => { setFeedKey((k) => k + 1); onCurated(b, a); }} />}
    </div>
  );
}

