// Board pack slide canvases. Every slide renders from the same data shape, whether it is the live pack or a
// finalised (frozen) version, so what leaders review on screen is what the PDF shows.
import { ReactNode } from "react";
import Chart from "../Chart";
import { md } from "../../md";
import { navigate, ROLE_LABEL } from "../../nav";
import { ChartSpec, day, FrozenCommentary, Metric, PeriodLabels, SlideMeta, STATUS_TEXT } from "./api";

const two = (n: number) => String(n).padStart(2, "0");

export function SlideFrame({ slide, total, labels, sub, children, footNote }: {
  slide: SlideMeta; total: number; labels: PeriodLabels; sub?: ReactNode; children: ReactNode; footNote?: ReactNode;
}) {
  return (
    <article className="bp-slide" aria-label={`Slide ${slide.no}: ${slide.title}`}>
      <div className="bp-slide-in">
      <header className="bp-slide-head">
        <span className="bp-no">{two(slide.no)}</span>
        <div className="bp-slide-title">
          <h2>{slide.title}</h2>
          <div className="bp-slide-sub">{sub ?? <>Month {labels.month} <span>vs {labels.month_pcp}</span> · Year to date {labels.fytd_long} <span>vs {labels.fytd_pcp}</span></>}</div>
        </div>
        <div className="bp-slide-brand">
          <div>Board pack · {labels.month_long}</div>
          <div>Prepared by {slide.owner}</div>
        </div>
      </header>
      <div className="bp-slide-body">{children}</div>
      <footer className="bp-slide-foot">
        <b>BOARD-IN-CONFIDENCE</b><span>Lochard Energy · {labels.month_long} board pack</span>
        {footNote && <span className="bp-foot-note">{footNote}</span>}
        <span className="bp-foot-pg">{slide.no} / {total}</span>
      </footer>
      </div>
    </article>
  );
}

export function MetricTile({ m }: { m: Metric }) {
  const tone = (t?: string | null) => (t ? `bp-${t}` : "");
  return (
    <div className="bp-tile">
      <div className="bp-tile-l">{m.label}</div>
      <div className="bp-tile-v">{m.m.t}</div>
      {m.m.d ? <div className="bp-tile-d"><span className={tone(m.m.d.tone || m.tone)}>{m.m.d.text}</span> vs {m.m.vs}</div>
        : m.m.p ? <div className="bp-tile-d">{m.m.vs}: {m.m.p}</div> : null}
      {m.y && (
        <div className="bp-tile-y"><b>{m.y.label}</b> {m.y.t}
          {m.y.d && <> · <span className={tone(m.y.d.tone || m.tone)}>{m.y.d.text}</span></>}</div>
      )}
      {m.note && <div className="bp-tile-n">{m.note}</div>}
    </div>
  );
}

export function MetricGrid({ metrics }: { metrics: Metric[] }) {
  const cols = metrics.length === 4 ? 2 : metrics.length <= 3 ? metrics.length : 3;
  return <div className={`bp-tiles bp-c${cols}`}>{metrics.map((m) => <MetricTile key={m.label} m={m} />)}</div>;
}

export function SlideChart({ chart, height = 220 }: { chart?: ChartSpec; height?: number }) {
  if (!chart) return null;
  return (
    <div className="bp-chart">
      <div className="bp-chart-head"><b>{chart.title}</b><span>{chart.sub}</span></div>
      <Chart rows={chart.rows} kind={chart.kind} x={chart.x} y={chart.y} height={height} zero={chart.zero}
             colors={chart.colors} area={chart.area} dashed={chart.dashed} />
    </div>
  );
}

export function Loading({ what = "Loading the latest figures…" }: { what?: string }) {
  return (
    <div className="bp-loading">
      <div className="bp-tiles bp-c3">{[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="bp-tile bp-skel" />)}</div>
      <div className="note"><span className="spinner" /> {what}</div>
    </div>
  );
}

/** Read-only commentary: as frozen in a finalised version, or (live) the approved text shown to Board directors. */
export function Frozen({ c, title, live }: { c: FrozenCommentary; title: string; live?: boolean }) {
  return (
    <div className="bp-frozen">
      <div className="cm-head"><b>{title}</b>{c && <span className="cm-pill cm-approved">Approved</span>}</div>
      {c ? (
        <>
          <div className="cm-body">{c.body.split(/\n{2,}/).map((p, i) => <p key={i}>{p}</p>)}</div>
          <div className="cm-meta">
            {c.author_name}{c.author_role ? ` · ${ROLE_LABEL[c.author_role] || c.author_role}` : ""}
            {c.reviewer_name && <> · approved by {c.reviewer_name} {day(c.reviewed_at)}</>}
            {c.ai_assisted && <> · drafted with AI assistance</>}
          </div>
        </>
      ) : <div className="note">{live ? "Commentary for this slide has not been approved yet."
        : "No commentary had been approved for this slide when the version was finalised."}</div>}
    </div>
  );
}

function Partial({ on }: { on?: boolean }) {
  return on ? <div className="bp-partial">Some figures could not be loaded just now – use Refresh figures to try again.</div> : null;
}

// ------------------------------------------------------------------------------------------------ slide bodies
export function MetricSlide({ d, commentary, extra }: { d: any; commentary: ReactNode; extra?: ReactNode }) {
  return (
    <div className="bp-2col">
      <div className="bp-main">
        <MetricGrid metrics={d.metrics || []} />
        <SlideChart chart={d.chart} height={extra ? 190 : 230} />
        {extra}
        <Partial on={d.partial} />
      </div>
      <aside className="bp-side">{commentary}</aside>
    </div>
  );
}

export function FinanceTable({ t }: { t?: { title: string; rows: any[] } }) {
  if (!t?.rows?.length) return null;
  return (
    <div className="bp-table-wrap">
      <div className="bp-chart-head"><b>{t.title}</b></div>
      <table className="bp-table">
        <thead><tr><th>Team</th><th>Actual</th><th>Budget</th><th>Variance</th><th>Full-year budget</th><th>Outlook</th></tr></thead>
        <tbody>{t.rows.map((r) => (
          <tr key={r.team}><td>{r.team}</td><td>{r.actual}</td><td>{r.budget}</td>
            <td className={r.tone ? `bp-${r.tone}` : ""}>{r.variance}</td><td>{r.fy_budget}</td><td>{r.fy_yeo}</td></tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export function HugsKpi({ k, eac }: { k?: any; eac?: any }) {
  return (
    <div className="bp-hugs">
      {eac && (
        <div className={`bp-eac ${eac.over ? "bp-eac-over" : ""}`}>
          <div><span>Estimate at completion</span><b>{eac.eac}</b></div>
          <div><span>Revised P50</span><b>{eac.p50}</b></div>
          <div><span>Variance</span><b className={eac.over ? "bp-bad" : "bp-good"}>{eac.variance ?? "–"}</b></div>
          <div><span>Of P50</span><b>{eac.pct_of_p50 ?? "–"}</b></div>
        </div>
      )}
      {k && (
        <div className={`bp-kpi st-${k.status || "none"}`}>
          <b>Scorecard KPI {k.code} {k.name}: {k.status_label}.</b> {k.update}
        </div>
      )}
    </div>
  );
}

export function ExecSlide({ d, labels, commentary, onGo }: { d: any; labels: PeriodLabels; commentary: ReactNode; onGo: (k: string) => void }) {
  const sc = d.scorecard || {};
  return (
    <div className="bp-exec">
      <div className="bp-heads">
        {(d.headlines || []).map((h: any) => (
          <button key={h.label} className="bp-head" onClick={() => onGo(h.slide)} title="Open the slide">
            <span className="bp-tile-l">{h.label}</span>
            <span className="bp-tile-v">{h.value}</span>
            <span className={`bp-tile-d ${h.tone ? `bp-${h.tone}` : ""}`}>{h.sub}</span>
          </button>
        ))}
      </div>
      <div className="bp-2col bp-2col-even">
        <div className="bp-main">
          <section className="bp-block">
            <h4>Board scorecard</h4>
            <div className="bp-sc-strip">
              <span><b>{sc.status_index ?? "–"}</b> status index</span>
              <span><b>{sc.board_score ?? "–"}</b> weighted board score</span>
              <span className={sc.at_risk ? "bp-warn" : ""}><b>{sc.at_risk ?? 0}</b> at risk</span>
              <span className={sc.off_track ? "bp-warn" : ""}><b>{sc.off_track ?? 0}</b> off track</span>
            </div>
            {d.scorecard_state && <div className="note">{d.scorecard_state}</div>}
            {d.attention?.length > 0 && (
              <ul className="bp-attn">{d.attention.map((a: any) => (
                <li key={a.code}><span className={`bp-dot st-${a.status || "none"}`} />KPI {a.code} {a.name} – {a.status_label}</li>))}</ul>
            )}
          </section>
          <section className="bp-block">
            <h4>From the leadership team <span className="note">approved Leadership Insights commentary · {labels.month}</span></h4>
            {d.domain_commentary?.length ? d.domain_commentary.map((c: any) => (
              <div key={c.subject} className="bp-dc">
                <b>{c.title}.</b> {c.body}
                <div className="cm-meta">{c.author_name}{c.reviewer_name ? ` · approved by ${c.reviewer_name}` : ""}</div>
              </div>
            )) : (
              <div className="bp-empty-inline">
                No approved Leadership Insights commentary for {labels.month} yet.{" "}
                <button className="linkish" onClick={() => navigate("insights")}>Open Leadership Insights</button>
              </div>
            )}
          </section>
        </div>
        <aside className="bp-side">{commentary}</aside>
      </div>
    </div>
  );
}

export function IntelSlide({ d, commentary }: { d: any; commentary: ReactNode }) {
  const has = d?.available && (d.briefs?.length || d.items?.length);
  return (
    <div className="bp-2col">
      <div className="bp-main">
        {!has ? (
          <div className="bp-empty">
            <b>{d?.available === false ? "Market briefs not available yet" : "No market briefs for these four weeks"}</b>
            <p>Weekly briefs from the Market Intelligence Hub appear here once they are published for {d?.window?.label?.toLowerCase() || "the last four weeks"}.</p>
            <button onClick={() => navigate("market")}>Open Market Intelligence</button>
          </div>
        ) : (
          <>
            {Object.keys(d.signals || {}).length > 0 && (
              <div className="bp-signals">{Object.entries(d.signals).map(([k, v]) => (
                <span key={k} className={`bp-sig bp-sig-${k.toLowerCase()}`}>{k} <b>{String(v)}</b></span>))}</div>
            )}
            {d.briefs.map((b: any) => (
              <div key={b.week_start} className="bp-brief">
                <div className="bp-brief-wk">{b.week_label}{b.n_items ? ` · ${b.n_items} items` : ""}</div>
                <div className="bp-brief-h">{b.headline}</div>
                <div className="md small" dangerouslySetInnerHTML={{ __html: md(firstSentences(b.summary, 2)) }} />
              </div>
            ))}
            {d.items?.length > 0 && (
              <div className="bp-items">
                <h4>Most important items</h4>
                {d.items.map((it: any, i: number) => (
                  <div key={i} className="bp-item">
                    <span className={`bp-sig bp-sig-${String(it.signal || "neutral").toLowerCase()}`}>{it.signal || "Neutral"}</span>
                    <div>
                      {it.url ? <a href={it.url} target="_blank" rel="noreferrer">{it.title}</a> : <b>{it.title}</b>}
                      <div className="note">{it.source} · {it.date}</div>
                      {it.why && <div className="bp-item-why">{it.why}</div>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
      <aside className="bp-side">{commentary}</aside>
    </div>
  );
}

export function OwnerSlide({ slide, d, commentary, empty, signals }: {
  slide: SlideMeta; d: any; commentary: ReactNode; empty?: ReactNode; signals: boolean;
}) {
  return (
    <div className={signals && d?.signals?.length ? "bp-2col bp-owner" : "bp-owner"}>
      <div className="bp-main">
        {empty}
        {commentary}
      </div>
      {signals && d?.signals?.length > 0 && (
        <aside className="bp-side bp-helper">
          <h4>Signals from this month's pack</h4>
          <ul>{d.signals.map((s: string) => <li key={s}>{s}</li>)}</ul>
          <div className="note">Prompts for {slide.owner} while preparing the slide – not part of the pack.</div>
        </aside>
      )}
    </div>
  );
}

export function CoverSlide({ labels, slides, commentary, onGo, showStatus, stamp }: {
  labels: PeriodLabels; slides: SlideMeta[]; commentary: ReactNode; onGo: (k: string) => void; showStatus: boolean; stamp?: ReactNode;
}) {
  return (
    <div className="bp-cover">
      <div className="bp-cover-panel">
        <div className="bp-wordmark"><b>lochard</b> energy</div>
        <div className="bp-cover-kicker">Board pack</div>
        <div className="bp-cover-month">{labels.month_long}</div>
        <div className="bp-cover-fy">{labels.fy} reporting period · {labels.code}</div>
        {labels.board_meeting && <div className="bp-cover-fy">Board meeting {day(labels.board_meeting)}</div>}
        <div className="bp-cover-state">Scorecard: {labels.state_label}</div>
        {stamp && <div className="bp-cover-stamp">{stamp}</div>}
      </div>
      <div className="bp-cover-main">
        <h3>Agenda</h3>
        <ol className="bp-agenda">
          {slides.filter((s) => s.key !== "cover").map((s) => (
            <li key={s.key} className={s.included ? "" : "bp-excluded"}>
              <button onClick={() => onGo(s.key)}>
                <span className="bp-ag-no">{two(s.no)}</span><span className="bp-ag-t">{s.title}</span>
                {!s.included ? <span className="bp-ag-s">Not in pack</span>
                  : showStatus && s.status ? <span className={`bp-ag-s bp-st-${s.status}`}>{STATUS_TEXT[s.status]}</span>
                    : <span className="bp-ag-s">{s.owner}</span>}
              </button>
            </li>
          ))}
        </ol>
        <div className="bp-cover-note">{commentary}</div>
      </div>
    </div>
  );
}

const ST: Record<string, string> = { ON_TRACK: "On Track", AT_RISK: "At Risk", OFF_TRACK: "Off Track", COMPLETE: "Complete" };

/** The scorecard as it was when a version was finalised (read only). */
export function FrozenScorecard({ d }: { d: any }) {
  if (!d?.available) return <div className="bp-empty"><b>The scorecard was not available when this version was finalised.</b></div>;
  const s = d.summary || {};
  return (
    <div>
      <div className="bp-sc-strip">
        <span><b>{s.status_index ?? "–"}</b> status index</span><span><b>{s.board_score ?? "–"}</b> weighted board score</span>
        <span><b>{s.at_risk}</b> at risk</span><span><b>{s.off_track}</b> off track</span>
        <span><b>{s.reported} of {s.kpis}</b> reported</span><span className="note">{d.state_label}</span>
      </div>
      <table className="sc">
        <thead><tr><th colSpan={3}>Key Performance Indicators</th><th>Owner</th><th>Weight</th><th>Status</th><th>Board</th><th>Owner update</th></tr></thead>
        <tbody>{d.pillars.map((p: any) => p.kpis.map((k: any, i: number) => (
          <tr key={k.code}>
            {i === 0 && <td className="pillar" rowSpan={p.kpis.length}>{p.name}</td>}
            <td className="code">{k.code}</td><td className="kname">{k.name}</td><td className="owner">{k.owner}</td>
            <td className="weight">{k.weight}</td><td className={`status st-${k.status || "none"}`}>{k.status ? ST[k.status] : "Not reported"}</td>
            <td className="board">{k.board ?? "–"}</td><td className="bp-upd">{k.update}</td>
          </tr>)))}</tbody>
      </table>
    </div>
  );
}

/** Board slides carry the gist; the full weekly brief lives on the Market Intelligence page. */
function firstSentences(text: string | null | undefined, n: number): string {
  const t = (text || "").replace(/\s+/g, " ").trim();
  const parts = t.match(/[^.!?]+[.!?]+(\s|$)/g);
  return parts && parts.length > n ? parts.slice(0, n).join("").trim() : t;
}
