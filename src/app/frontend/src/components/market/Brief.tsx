import { md } from "../../md";
import { AgentBadge, Direction, GroupTag, Importance, SignalChip } from "./bits";
import { Action, Brief, BriefHead, dayLabel, Synthesis, WatchEntry, weekLabel, when } from "./types";

function Implications({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="mi-block">
      <h3>Implications for Lochard</h3>
      <ul className="mi-list">{items.map((t, i) => <li key={i}>{t}</li>)}</ul>
    </div>
  );
}

function Actions({ items }: { items: Action[] }) {
  if (!items.length) return null;
  return (
    <div className="mi-block">
      <h3>Recommended actions</h3>
      <ol className="mi-actions">{items.map((a, i) => (
        <li key={i}><span>{a.action}</span>{a.owner_role && <span className="mi-owner" title="Suggested owner">{a.owner_role}</span>}</li>
      ))}</ol>
    </div>
  );
}

function Watchlist({ items }: { items: WatchEntry[] }) {
  if (!items.length) return null;
  return (
    <div className="mi-block">
      <h3>Watchlist movements</h3>
      <div className="mi-watch">{items.map((w, i) => (
        <div key={i} className="mi-watch-row"><Direction d={w.direction} /><b>{w.entity}</b><span>{w.note}</span></div>
      ))}</div>
    </div>
  );
}

export function BriefCard({ brief, onOpenItem }: { brief: Brief; onOpenItem: (id: string) => void }) {
  return (
    <article className="card mi-brief">
      <div className="mi-by">
        <AgentBadge />
        <span>Weekly brief · {brief.label}</span>
        {brief.week_to_date && <span className="mi-wtd" title="The brief is refreshed each morning while the week is in progress">Week to date</span>}
        <span className="mi-by-meta">
          {brief.n_items ?? 0} items from {brief.n_sources ?? 0} sources{brief.generated_at ? ` · prepared ${when(brief.generated_at)}` : ""}
        </span>
      </div>
      <h2 className="mi-headline">{brief.headline}</h2>
      <div className="md mi-summary" dangerouslySetInnerHTML={{ __html: md(brief.summary_md) }} />

      {brief.developments.length > 0 && (
        <div className="mi-block">
          <h3>Key developments</h3>
          <ol className="mi-devs">{brief.developments.map((d, i) => (
            <li key={i} className={`mi-dev mi-dev-${d.signal}`}>
              <div className="mi-dev-top">
                <SignalChip s={d.signal} small /><GroupTag g={d.entity_group} /><Importance v={d.importance} />
              </div>
              <div className="mi-dev-title">{d.title}</div>
              {d.detail && <p>{d.detail}</p>}
              {!!d.items?.length && (
                <div className="mi-cites">
                  <span className="note">Sources</span>
                  {d.items.map((c) => (
                    <span key={c.item_id} className="mi-cite">
                      <button className="linkish" onClick={() => onOpenItem(c.item_id)} title={c.title}>
                        {c.source_name || "Source"} · {dayLabel(c.published_date, false)}</button>
                      {c.url && <a href={c.url} target="_blank" rel="noreferrer" title="Open the original" aria-label={`Open ${c.title}`}>↗</a>}
                    </span>
                  ))}
                </div>
              )}
            </li>
          ))}</ol>
        </div>
      )}
      <div className="mi-brief-cols">
        <Implications items={brief.implications} />
        <Actions items={brief.actions} />
      </div>
      <Watchlist items={brief.watchlist} />
    </article>
  );
}

const TREND: Record<string, string> = { building: "Building", easing: "Easing", steady: "Steady", new: "New", resolved: "Resolved" };

export function SynthesisCard({ s, windowLabel, canRegenerate, busy, onRegenerate, onWeek }: {
  s: Synthesis; windowLabel: string; canRegenerate: boolean; busy: boolean; onRegenerate: () => void;
  onWeek: (w: string) => void;
}) {
  return (
    <article className="card mi-brief">
      <div className="mi-by">
        <AgentBadge />
        <span>Multi-week synthesis · {windowLabel}</span>
        <span className="mi-by-meta">from {s.n_briefs} weekly brief{s.n_briefs === 1 ? "" : "s"} · generated {when(s.generated_at)}</span>
      </div>
      {s.stale && (
        <div className="mi-stale">
          {busy ? <><span className="spinner" /> Weekly briefs have changed – updating the synthesis…</>
            : <>Weekly briefs have changed since this synthesis was generated.
              {canRegenerate && <button className="linkish" onClick={onRegenerate}>Regenerate now</button>}</>}
        </div>
      )}
      <h2 className="mi-headline">{s.headline}</h2>
      <div className="md mi-summary" dangerouslySetInnerHTML={{ __html: md(s.summary_md) }} />
      {s.themes.length > 0 && (
        <div className="mi-block">
          <h3>Themes across the period</h3>
          <ol className="mi-devs">{s.themes.map((t, i) => (
            <li key={i} className={`mi-dev mi-dev-${t.signal}`}>
              <div className="mi-dev-top">
                <SignalChip s={t.signal} small />
                <span className={`mi-trend mi-trend-${t.trend}`}>{TREND[t.trend] || t.trend}</span>
                {t.entity_groups.map((g) => <GroupTag key={g} g={g} />)}
              </div>
              <div className="mi-dev-title">{t.title}</div>
              {t.detail && <p>{t.detail}</p>}
              {t.weeks.length > 0 && (
                <div className="mi-cites"><span className="note">Featured in</span>
                  {t.weeks.map((w) => <button key={w} className="mi-weekchip" onClick={() => onWeek(w)} title={`Open the ${weekLabel(w)} brief`}>
                    {dayLabel(w, false)}</button>)}
                </div>
              )}
            </li>
          ))}</ol>
        </div>
      )}
      <div className="mi-brief-cols">
        <Implications items={s.implications} />
        <Actions items={s.actions} />
      </div>
      <Watchlist items={s.watchlist} />
      {canRegenerate && !s.stale && (
        <div className="mi-regen"><button className="linkish" disabled={busy} onClick={onRegenerate}>
          {busy ? "Regenerating…" : "↻ Regenerate synthesis"}</button></div>
      )}
    </article>
  );
}

export function WeeklyHeadlines({ briefs, onWeek }: { briefs: BriefHead[]; onWeek: (w: string) => void }) {
  if (!briefs.length) return null;
  return (
    <div className="card mi-timeline">
      <h3>Week by week</h3>
      <ol>{[...briefs].reverse().map((b) => (
        <li key={b.week_start}>
          <button className="mi-tl-week" onClick={() => onWeek(b.week_start)} title={`Open the ${b.label} brief`}>
            {dayLabel(b.week_start, false)}</button>
          <span className="mi-tl-head">{b.headline}</span>
          <span className="note">{b.n_items ?? 0} items{b.week_to_date ? " · week to date" : ""}</span>
        </li>
      ))}</ol>
    </div>
  );
}
