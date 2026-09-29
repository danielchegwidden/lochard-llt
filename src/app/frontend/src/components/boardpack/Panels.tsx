// Board pack controls: readiness, finalise dialog, finalised versions and the activity trail.
import { useState } from "react";
import { ROLE_LABEL } from "../../nav";
import { Activity, bp, day, PackMeta, SlideMeta, STATUS_TEXT, Version, VERSION_TEXT } from "./api";

export function readinessOf(slides: SlideMeta[]) {
  const inc = slides.filter((s) => s.included);
  const ready = inc.filter((s) => s.status === "READY");
  return { ready: ready.length, total: inc.length, notReady: inc.filter((s) => s.status !== "READY"),
           excluded: slides.filter((s) => !s.included) };
}

export function ReadinessBar({ slides, onGo }: { slides: SlideMeta[]; onGo: (k: string) => void }) {
  const r = readinessOf(slides);
  const all = r.total > 0 && r.ready === r.total;
  return (
    <div className="bp-ready">
      <div className="bp-ready-text"><b className={all ? "bp-good" : ""}>{r.ready} of {r.total}</b> slides ready
        {r.excluded.length > 0 && <span className="note"> · {r.excluded.length} not in this pack</span>}</div>
      <div className="bp-ready-bar" role="list">
        {slides.map((s) => (
          <button key={s.key} role="listitem" className={`bp-seg bp-st-${s.included ? s.status : "EXCLUDED"}`} onClick={() => onGo(s.key)}
                  title={`${s.no}. ${s.title} – ${s.included ? STATUS_TEXT[s.status || "NOT_STARTED"] : "not in this pack"}`} />
        ))}
      </div>
      <div className="bp-legend"><i className="bp-st-READY" />Ready<i className="bp-st-IN_DRAFT" />In draft<i className="bp-st-NOT_STARTED" />Not started</div>
    </div>
  );
}

export function StatusPill({ v }: { v: Version | null }) {
  if (!v) return <span className="bp-pill bp-pill-prep">In preparation</span>;
  return <span className={`bp-pill bp-pill-${v.status}`}>{v.status === "SENT" ? "Sent to the Board" : `Finalised · v${v.version}`}</span>;
}

export function FinaliseDialog({ meta, slides, onClose, onDone, onGo }: {
  meta: PackMeta; slides: SlideMeta[]; onClose: () => void; onDone: (v: Version) => void; onGo: (k: string) => void;
}) {
  const r = readinessOf(slides);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<Version | null>(null);
  const next = (meta.latest?.version || 0) + 1;
  const needReason = r.notReady.length > 0;
  const go = async () => {
    setBusy(true); setErr(null);
    try {
      const res = await bp.finalise(meta.period.code, needReason ? reason.trim() : undefined);
      setDone(res.version); onDone(res.version);
    } catch (e) { setErr(String(e).replace(/^Error: \d+: /, "")); } finally { setBusy(false); }
  };
  return (
    <>
      <div className="drawer-bg" onClick={busy ? undefined : onClose} />
      <div className="bp-dialog" role="dialog" aria-modal="true" aria-label="Finalise the board pack">
        {done ? (
          <>
            <h3>Version {done.version} finalised</h3>
            <p>The {meta.period.month_long} board pack is frozen as version {done.version} ({done.pdf_pages} pages).
              Board directors can now read and download it here.</p>
            <div className="bp-dialog-actions">
              <a href={bp.pdfUrl(meta.period.code, done.version)}><button className="primary">Download PDF</button></a>
              <div className="spacer" />
              <button onClick={onClose}>Close</button>
            </div>
          </>
        ) : (
          <>
            <h3>Finalise the {meta.period.month_long} board pack</h3>
            <p>This freezes the current figures and the approved commentary as <b>version {next}</b> and generates the PDF.
              Only approved commentary goes into the pack.</p>
            {meta.latest && meta.latest.status !== "SUPERSEDED" && (
              <div className="bp-callout">Version {meta.latest.version}
                {meta.latest.status === "SENT" ? ` was sent to the Board ${day(meta.latest.sent_at)}` : " is the current final version"}.
                It will be marked as superseded.</div>
            )}
            <div className={`bp-check ${needReason ? "bp-check-warn" : "bp-check-ok"}`}>
              <b>{r.ready} of {r.total}</b> included slides are ready.
              {r.excluded.length > 0 && <span className="note"> Not in this pack: {r.excluded.map((s) => s.title).join(", ")}.</span>}
            </div>
            {needReason && (
              <>
                <ul className="bp-notready">{r.notReady.map((s) => (
                  <li key={s.key}><button className="linkish" onClick={() => { onGo(s.key); onClose(); }}>{s.no}. {s.title}</button>
                    <span className={`bp-chip bp-st-${s.status}`}>{STATUS_TEXT[s.status || "NOT_STARTED"]}</span></li>))}</ul>
                <label className="bp-label">Reason for finalising before every slide is ready
                  <textarea value={reason} onChange={(e) => setReason(e.target.value)} disabled={busy}
                            placeholder="e.g. The decisions paper will be tabled at the meeting." /></label>
                <div className="note">The reason is recorded with the version and shown on its document-control page.</div>
              </>
            )}
            {err && <div className="err">{err}</div>}
            <div className="bp-dialog-actions">
              {busy && <span className="note"><span className="spinner" /> Freezing the figures and generating the PDF…</span>}
              <div className="spacer" />
              <button onClick={onClose} disabled={busy}>Cancel</button>
              <button className="crimson" disabled={busy || r.total === 0 || (needReason && !reason.trim())} onClick={go}>
                {busy ? "Finalising…" : `Finalise version ${next}`}</button>
            </div>
          </>
        )}
      </div>
    </>
  );
}

export function VersionsPanel({ meta, viewing, onView, onSent }: {
  meta: PackMeta; viewing: number | null; onView: (v: number | null) => void; onSent: (v: Version) => void;
}) {
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const markSent = async (v: Version) => {
    if (!window.confirm(`Record that version ${v.version} of the ${meta.period.month_long} pack has been sent to the Board?`)) return;
    setBusy(v.version); setErr(null);
    try { onSent((await bp.markSent(meta.period.code, v.version)).version); } catch (e) { setErr(String(e)); } finally { setBusy(null); }
  };
  if (!meta.versions.length) {
    return (
      <div className="card bp-versions">
        <h3>Finalised versions</h3>
        <div className="note">{meta.role === "BOARD" || meta.role === "OBSERVER"
          ? `The ${meta.period.month_long} pack has not been issued yet. It will appear here once the leadership team finalises it.`
          : "Nothing finalised yet. When the slides are ready, a leader finalises the pack to freeze it and generate the PDF."}</div>
      </div>
    );
  }
  return (
    <div className="card bp-versions">
      <h3>Finalised versions</h3>
      {err && <div className="err">{err}</div>}
      <table className="bp-table">
        <thead><tr><th>Version</th><th>Status</th><th>Finalised</th><th>Readiness</th><th>Sent to the Board</th><th /></tr></thead>
        <tbody>{meta.versions.map((v) => (
          <tr key={v.version} className={viewing === v.version ? "bp-row-on" : ""}>
            <td><b>v{v.version}</b></td>
            <td><span className={`bp-pill bp-pill-${v.status}`}>{VERSION_TEXT[v.status]}</span></td>
            <td>{day(v.finalised_at, true)}<div className="note">{v.finalised_name}{v.finalised_role ? ` · ${ROLE_LABEL[v.finalised_role] || v.finalised_role}` : ""}</div></td>
            <td>{v.slides_ready} of {v.slides_total} ready
              {v.override_reason && <div className="note" title={v.override_reason}>Finalised early: {v.override_reason}</div>}</td>
            <td>{v.sent_at ? <>{day(v.sent_at, true)}<div className="note">{v.sent_name}</div></> : "–"}</td>
            <td className="bp-actions">
              <button className={viewing === v.version ? "linkish bp-on" : "linkish"} onClick={() => onView(viewing === v.version ? null : v.version)}>
                {viewing === v.version ? "Viewing" : "View"}</button>
              {meta.perms.can_download && <a href={bp.pdfUrl(meta.period.code, v.version)}><button>PDF{v.pdf_pages ? ` · ${v.pdf_pages} pp` : ""}</button></a>}
              {meta.perms.can_mark_sent && v.status === "FINAL" && (
                <button className="primary" disabled={busy === v.version} onClick={() => markSent(v)}>
                  {busy === v.version ? "Recording…" : "Mark as sent to the Board"}</button>)}
            </td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export function ActivityPanel({ items }: { items: Activity[] }) {
  if (!items.length) return null;
  return (
    <div className="card bp-activity">
      <h3>Activity</h3>
      <ul>{items.map((a, i) => (
        <li key={i}><span className="note">{day(a.at, true)}</span><span>{a.what}</span><span className="note">{a.actor}</span></li>
      ))}</ul>
    </div>
  );
}
