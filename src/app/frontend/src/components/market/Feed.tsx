import { useEffect, useRef, useState } from "react";
import { GroupTag, Importance, SignalChip } from "./bits";
import {
  Annotation, dayLabel, DEPTH_LABEL, Filters, fmtSent, GROUPS, Item, ItemsResp, marketApi, Mode, sentimentWord, SIGNALS,
  SOURCE_LABEL, TOPICS, when,
} from "./types";

type Facets = Record<"entity_group" | "topic" | "signal" | "source_type", Record<string, number>> | undefined;

// ---------------------------------------------------------------------------------------------- triage controls
function useAnnotate(item: Item, onSaved: (it: Item) => void) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const save = async (a: Annotation) => {
    setBusy(true); setErr(null);
    try {
      const r = await marketApi.annotate(item.item_id, item.week_start, a);
      const ovr = r.importance_override ?? null;
      onSaved({ ...item, pinned: r.pinned, dismissed: r.dismissed, note: r.note, note_by: r.note_by, note_at: r.note_at,
                importance_override: ovr, importance: ovr ?? item.importance_ai });
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  return { busy, err, save };
}

function NoteEditor({ initial, busy, onSave, onCancel }: { initial: string; busy: boolean; onSave: (t: string) => void; onCancel: () => void }) {
  const [t, setT] = useState(initial);
  return (
    <div className="mi-note-edit" onClick={(e) => e.stopPropagation()}>
      <textarea value={t} onChange={(e) => setT(e.target.value)} maxLength={2000} autoFocus
                placeholder="Why this matters for the leadership team, what to watch, who should know…" />
      <div className="mi-row">
        <span className="note">{t.length}/2000</span><div className="spacer" />
        <button className="linkish" onClick={onCancel}>Cancel</button>
        {initial && <button disabled={busy} onClick={() => onSave("")}>Remove note</button>}
        <button className="primary" disabled={busy || t.trim() === initial.trim()} onClick={() => onSave(t)}>{busy ? "Saving…" : "Save note"}</button>
      </div>
    </div>
  );
}

function Triage({ item, onSaved }: { item: Item; onSaved: (it: Item) => void }) {
  const { busy, err, save } = useAnnotate(item, onSaved);
  const [noting, setNoting] = useState(false);
  return (
    <div className="mi-triage" onClick={(e) => e.stopPropagation()}>
      <div className="mi-row">
        <button className={`mi-tbtn${item.pinned ? " on" : ""}`} disabled={busy} onClick={() => save({ pinned: !item.pinned })}
                title={item.pinned ? "Remove from the leadership selection" : "Select for the leadership team and board"}>
          📌 {item.pinned ? "Pinned" : "Pin"}</button>
        <button className="mi-tbtn" disabled={busy} onClick={() => save({ dismissed: !item.dismissed })}
                title={item.dismissed ? "Show this item to leaders again" : "Hide from the leadership view (noise or not relevant)"}>
          {item.dismissed ? "↺ Restore" : "✕ Dismiss"}</button>
        <button className={`mi-tbtn${item.note ? " on" : ""}`} disabled={busy} onClick={() => setNoting((v) => !v)}>
          ✎ {item.note ? "Edit note" : "Add note"}</button>
        <label className="mi-ovr" title="Override the agent's importance rating">
          Importance
          <select value={item.importance_override ?? ""} disabled={busy}
                  onChange={(e) => save({ importance_override: e.target.value ? Number(e.target.value) : null })}>
            <option value="">Agent: {item.importance_ai}</option>
            {[5, 4, 3, 2, 1].map((v) => <option key={v} value={v}>{v}{v === 5 ? " – critical" : v === 1 ? " – minor" : ""}</option>)}
          </select>
        </label>
        {busy && <span className="spinner" />}
      </div>
      {noting && <NoteEditor initial={item.note || ""} busy={busy}
                             onSave={async (t) => { await save({ note: t || null }); setNoting(false); }}
                             onCancel={() => setNoting(false)} />}
      {err && <div className="err">{err}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- card
export function ItemCard({ item, mode, onOpen, onSaved, showDismissed }: {
  item: Item; mode: Mode; onOpen: () => void; onSaved: (it: Item) => void; showDismissed?: boolean;
}) {
  const { busy, save } = useAnnotate(item, onSaved);
  if (mode === "analyst" && item.dismissed && !showDismissed) {   // just dismissed: collapse, with undo
    return (
      <div className="mi-card mi-card-dismissed">
        <span className="note">Dismissed · hidden from leaders</span><b>{item.title}</b>
        <button className="linkish" disabled={busy} onClick={() => save({ dismissed: false })}>Undo</button>
      </div>
    );
  }
  return (
    <div className={`mi-card${item.pinned ? " mi-pinned" : ""}${item.dismissed ? " mi-dim" : ""}`} onClick={onOpen}
         role="button" tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter" && e.target === e.currentTarget) onOpen(); }}>
      <div className="mi-card-top">
        <SignalChip s={item.signal} small /><GroupTag g={item.entity_group} />
        {item.topic && <span className="mi-topic">{item.topic}</span>}
        <div className="spacer" />
        {item.pinned && <span className="mi-pin-badge" title="Selected by the analyst">📌 Pinned</span>}
        <Importance v={item.importance} ai={item.importance_ai} override={item.importance_override} />
      </div>
      <div className="mi-card-title">
        {item.url ? <a href={item.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>{item.title}<span className="mi-ext">↗</span></a>
          : item.title}
      </div>
      <div className="mi-card-meta">
        <b>{item.source_name}</b> · {dayLabel(item.published_date)} · {SOURCE_LABEL[item.source_type || ""] || item.source_type}
        {item.content_depth === "headline" && <span className="mi-depth" title="The AI summary is based on the headline and snippet only">headline only</span>}
      </div>
      {item.summary && <p className="mi-card-sum">{item.summary}</p>}
      {item.why_it_matters && <p className="mi-why"><b>Why it matters · </b>{item.why_it_matters}</p>}
      {item.note && (
        <div className="mi-note"><b>Analyst note{item.note_by ? ` · ${item.note_by}` : ""}</b>{item.note}</div>
      )}
      {mode === "analyst" && <Triage item={item} onSaved={onSaved} />}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- drawer
export function ItemDrawer({ id, mode, onClose, onSaved }: {
  id: string; mode: Mode; onClose: () => void; onSaved: (before: Item, after: Item) => void;
}) {
  const [it, setIt] = useState<Item | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setIt(null); setErr(null);
    marketApi.item(id).then((r) => ("available" in r && r.available === false ? setErr(r.message) : setIt(r as Item)))
      .catch((e) => setErr(String(e)));
  }, [id]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  const saved = (x: Item) => { if (it) onSaved(it, x); setIt((p) => (p ? { ...p, ...x, excerpt: p.excerpt, entity_meta: p.entity_meta } : x)); };

  return (
    <>
      <div className="drawer-bg" onClick={onClose} />
      <aside className="drawer mi-drawer" role="dialog" aria-label="Item details">
        <header>
          <button className="close" onClick={onClose}>Close ✕</button>
          <div className="mi-dr-kicker">{it ? `${it.source_name} · ${dayLabel(it.published_date)}` : "Loading…"}</div>
          <h2>{it?.title || ""}</h2>
        </header>
        {err && <section><div className="err">{err}</div></section>}
        {it && (
          <>
            <section>
              <div className="mi-card-top">
                <SignalChip s={it.signal} /><GroupTag g={it.entity_group} />{it.topic && <span className="mi-topic">{it.topic}</span>}
                <div className="spacer" /><Importance v={it.importance} ai={it.importance_ai} override={it.importance_override} />
              </div>
              {it.summary && <p className="mi-dr-sum">{it.summary}</p>}
              {it.why_it_matters && <p className="mi-why"><b>Why it matters · </b>{it.why_it_matters}</p>}
              {it.note && <div className="mi-note"><b>Analyst note{it.note_by ? ` · ${it.note_by}` : ""}{it.note_at ? ` · ${when(it.note_at)}` : ""}</b>{it.note}</div>}
              {mode === "analyst" && <Triage item={it} onSaved={saved} />}
            </section>
            <section>
              <h3>From the source</h3>
              <blockquote className="mi-excerpt">{it.excerpt || "No excerpt is available for this item."}</blockquote>
              <div className="note">
                {DEPTH_LABEL[it.content_depth || ""] ? `The AI read: ${DEPTH_LABEL[it.content_depth || ""].toLowerCase()}.` : ""}
                {" "}Only a short excerpt is shown here – read the full document at the source.
              </div>
              {it.url && <p><a className="mi-open" href={it.url} target="_blank" rel="noreferrer">Open the original at {it.source_name} ↗</a></p>}
            </section>
            <section>
              <h3>Details</h3>
              <dl className="mi-dl">
                <dt>Publisher</dt><dd>{it.source_name} ({SOURCE_LABEL[it.source_type || ""] || it.source_type})</dd>
                <dt>Published</dt><dd>{dayLabel(it.published_date)}</dd>
                <dt>Main entity</dt><dd>{it.primary_entity || "–"}</dd>
                <dt>Mentions</dt><dd>{it.entity_meta?.length ? it.entity_meta.map((e) => (
                  <div key={e.entity}><b>{e.entity}</b>{e.relationship && e.relationship !== "Self" ? <span className="note"> – {e.relationship}</span> : null}</div>)) : "–"}</dd>
                <dt>Sentiment for Lochard</dt><dd>{sentimentWord(it.sentiment)} (score {fmtSent(it.sentiment)} of ±100)</dd>
                <dt>Relevance</dt><dd>{it.relevance ? `${it.relevance} of 3` : "–"}</dd>
                <dt>Importance</dt><dd>{it.importance}/5{it.importance_override ? ` (set by the analyst; agent rated ${it.importance_ai}/5)` : ""}</dd>
                <dt>Collected</dt><dd>{when(it.ingested_at) || "–"}</dd>
              </dl>
            </section>
          </>
        )}
      </aside>
    </>
  );
}

// ---------------------------------------------------------------------------------------------- feed
const opts = (vals: string[], facet?: Record<string, number>, label?: (v: string) => string) =>
  vals.filter((v) => !facet || facet[v]).map((v) => <option key={v} value={v}>{label ? label(v) : v}{facet?.[v] ? ` (${facet[v]})` : ""}</option>);

export default function Feed({ week, horizon, mode, facets, f, setF, onChanged, onOpen, refresh }: {
  week: string; horizon: number; mode: Mode; facets: Facets; f: Filters; setF: (u: (p: Filters) => Filters) => void;
  onChanged: (before: Item, after: Item) => void; onOpen: (id: string) => void; refresh: number;
}) {
  const [q, setQ] = useState(f.q || "");
  const entity = f.entity;
  const [items, setItems] = useState<Item[] | null>(null);
  const [meta, setMeta] = useState({ total: 0, n_dismissed: 0, n_visible: 0 });
  const [err, setErr] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  const seq = useRef(0);
  const PAGE = 25;
  const filters: Filters = { ...f, entity, q: q.trim() || undefined };
  const key = JSON.stringify([week, horizon, filters, refresh]);

  useEffect(() => {
    const t = setTimeout(() => {
      const n = ++seq.current;
      setErr(null);
      marketApi.items(week, horizon, filters, 0, PAGE).then((r) => {
        if (n !== seq.current) return;
        if ("available" in r && r.available === false) { setErr(r.message); setItems([]); return; }
        const d = r as ItemsResp;
        setItems(d.items);
        setMeta({ total: d.total, n_dismissed: d.n_dismissed, n_visible: d.n_visible });
      }).catch((e) => { if (n === seq.current) { setErr(String(e)); setItems([]); } });
    }, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [key]);

  const loadMore = async () => {
    setMore(true);
    try {
      const r = await marketApi.items(week, horizon, filters, items?.length || 0, PAGE);
      if ("items" in r) setItems((p) => [...(p || []), ...r.items]);
    } catch (e) { setErr(String(e)); } finally { setMore(false); }
  };
  const saved = (x: Item) => {
    const before = items?.find((i) => i.item_id === x.item_id);
    if (before) onChanged(before, x);
    setItems((p) => p?.map((i) => (i.item_id === x.item_id ? { ...i, ...x } : i)) || null);
  };
  const set = (k: keyof Filters, v: any) => setF((p) => ({ ...p, [k]: v || undefined }));
  const active = !!(f.group || f.topic || f.signal || f.source_type || entity || q.trim() || f.pinned_only);
  const reset = () => { setF((p) => ({ sort: p.sort, show_dismissed: p.show_dismissed })); setQ(""); };

  const title = mode === "board" ? "Items selected for the board" : mode === "leader" ? "Curated signals" : "All signals – triage";
  const sub = mode === "board" ? "Chosen by the analyst from this period's public sources."
    : mode === "leader" ? "Analyst-pinned items first; items the analyst dismissed as noise are hidden."
    : "Pin what the leadership team should see, dismiss noise, add a note or adjust importance.";

  return (
    <section className="card mi-feed" id="mi-feed">
      <div className="mi-sec-head">
        <div><h3>{title}</h3><div className="note">{sub}</div></div>
        <div className="note mi-count">{items ? `${meta.total} item${meta.total === 1 ? "" : "s"}` : ""}
          {mode === "leader" && meta.n_dismissed > 0 ? ` · ${meta.n_dismissed} dismissed by the analyst` : ""}</div>
      </div>
      {mode !== "board" && (
        <div className="mi-filters">
          <input className="mi-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search titles, summaries, notes…" aria-label="Search items" />
          <select value={f.group || ""} onChange={(e) => set("group", e.target.value)} aria-label="Entity group">
            <option value="">All groups</option>{opts(GROUPS, facets?.entity_group)}</select>
          <select value={f.topic || ""} onChange={(e) => set("topic", e.target.value)} aria-label="Topic">
            <option value="">All topics</option>{opts(TOPICS, facets?.topic)}</select>
          <select value={f.signal || ""} onChange={(e) => set("signal", e.target.value)} aria-label="Signal">
            <option value="">All signals</option>{opts(SIGNALS, facets?.signal)}</select>
          <select value={f.source_type || ""} onChange={(e) => set("source_type", e.target.value)} aria-label="Source type">
            <option value="">All sources</option>{opts(Object.keys(SOURCE_LABEL), facets?.source_type, (v) => SOURCE_LABEL[v])}</select>
          <div className="seg" role="group" aria-label="Sort">
            <button className={f.sort === "importance" ? "on" : ""} onClick={() => set("sort", "importance")}>Most important</button>
            <button className={f.sort === "newest" ? "on" : ""} onClick={() => set("sort", "newest")}>Newest</button>
          </div>
          <label className="mi-check"><input type="checkbox" checked={!!f.pinned_only} onChange={(e) => set("pinned_only", e.target.checked)} />Pinned only</label>
          {mode === "analyst" && (
            <label className="mi-check"><input type="checkbox" checked={!!f.show_dismissed} onChange={(e) => set("show_dismissed", e.target.checked)} />
              Show dismissed</label>)}
          {active && <button className="linkish" onClick={reset}>Clear filters</button>}
        </div>
      )}
      {entity && <div className="mi-entity-filter">Showing items mentioning <b>{entity}</b> <button className="linkish" onClick={() => set("entity", undefined)}>✕ clear</button></div>}
      {err && <div className="err">{err}</div>}
      {!items ? <div className="note mi-pad">Loading items…</div>
        : items.length === 0 ? (
          <div className="mi-empty">{mode === "board" ? "The analyst has not selected any items for this period yet."
            : active ? "No items match these filters." : "No items were collected for this period."}</div>
        ) : (
          <div className="mi-cards">{items.map((i) => (
            <ItemCard key={i.item_id} item={i} mode={mode} onOpen={() => onOpen(i.item_id)} onSaved={saved} showDismissed={!!f.show_dismissed} />
          ))}</div>
        )}
      {items && items.length < meta.total && (
        <div className="mi-more"><button disabled={more} onClick={loadMore}>{more ? "Loading…" : `Show more (${meta.total - items.length} more)`}</button></div>
      )}
    </section>
  );
}
