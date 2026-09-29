import { useEffect, useState } from "react";
import { api, Evidence, fmt, Kpi, Me, Scorecard, STATUS_LABEL } from "../api";

const STATES = ["OPEN", "OWNER_SUBMITTED", "LLT_REVIEWED", "BOARD_ENDORSED", "LOCKED"];
const STATE_LABEL: Record<string, string> = {
  OPEN: "Owner updates", OWNER_SUBMITTED: "Submitted", LLT_REVIEWED: "LLT reviewed", BOARD_ENDORSED: "Board endorsed", LOCKED: "Locked",
};
const NEXT: Record<string, { to: string; label: string; roles: string[] }[]> = {
  OPEN: [{ to: "OWNER_SUBMITTED", label: "Submit to LLT", roles: ["KPI_OWNER", "LLT", "ADMIN"] }],
  OWNER_SUBMITTED: [{ to: "LLT_REVIEWED", label: "LLT review complete", roles: ["LLT", "ADMIN"] },
                    { to: "OPEN", label: "Return to owners", roles: ["LLT", "ADMIN"] }],
  LLT_REVIEWED: [{ to: "BOARD_ENDORSED", label: "Board endorse", roles: ["BOARD", "ADMIN"] },
                 { to: "OWNER_SUBMITTED", label: "Send back to LLT", roles: ["BOARD", "LLT", "ADMIN"] }],
  BOARD_ENDORSED: [{ to: "LOCKED", label: "Lock period", roles: ["BOARD", "ADMIN"] }],
  LOCKED: [],
};

type ScorecardProps = {
  me: Me;
  /** Inside the board pack: no page header or FY / period pickers – the pack chooses the period. */
  embedded?: boolean; fy?: string; period?: string;
  /** Called after the period workflow moves (so the pack can refresh its status). */
  onChanged?: () => void;
};

export default function ScorecardPage({ me, embedded, fy: fyProp, period: periodProp, onChanged }: ScorecardProps) {
  const [fyState, setFy] = useState(fyProp || "FY27");
  const fy = embedded && fyProp ? fyProp : fyState;
  const [periods, setPeriods] = useState<any[]>([]);
  const [period, setPeriod] = useState<string | undefined>();
  const [sc, setSc] = useState<Scorecard | null>(null);
  const [open, setOpen] = useState<Kpi | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = (p?: string) => api.scorecard(fy, p).then((d) => { setSc(d); setPeriod(d.period.period_code); setErr(null); })
    .catch((e) => setErr(String(e)));
  useEffect(() => { if (!embedded) api.fiscalYears().then((d) => setPeriods(d.periods)); }, [embedded]);
  useEffect(() => { setPeriod(undefined); load(embedded ? periodProp : undefined); }, [fy, embedded, periodProp]);

  const advance = async (to: string) => {
    if (!sc) return;
    const note = window.prompt(`Note for moving ${sc.period.label} to ${STATE_LABEL[to]} (optional)`) ?? undefined;
    setBusy(true);
    try { await api.advance(sc.period.period_code, to, note); await load(sc.period.period_code); onChanged?.(); }
    catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };

  if (!sc) return <div className="card">{err ? <div className="err">{err}</div> : "Loading scorecard…"}</div>;
  const idx = STATES.indexOf(sc.period.state);
  const fyPeriods = periods.filter((p) => p.fy_code === fy);
  return (
    <div className={embedded ? "bp-sc-embedded" : undefined}>
      {!embedded && <>
        <h1 className="page">{fy} Board Scorecard</h1>
        <p className="sub">{sc.period.label} reporting period · Iona Ops Trust · click a KPI to update status, score or comment</p>
      </>}
      <div className="toolbar">
        {!embedded && <>
          <select value={fy} onChange={(e) => setFy(e.target.value)}>
            <option value="FY27">FY27</option><option value="FY26">FY26</option>
          </select>
          <select value={period} onChange={(e) => load(e.target.value)}>
            {fyPeriods.map((p) => <option key={p.period_code} value={p.period_code}>{p.label} – {STATE_LABEL[p.state]}</option>)}
          </select>
        </>}
        <span className="stat"><span>Status index</span><b>{sc.summary.status_index_pct ?? "–"}%</b></span>
        <span className="stat"><span>Weighted board score</span><b>{sc.summary.weighted_board_score_pct ?? "–"}%</b></span>
        <span className={`stat ${sc.summary.kpis_at_risk ? "warn" : ""}`}><span>KPIs at risk</span><b>{sc.summary.kpis_at_risk ?? 0}</b></span>
        <div className="spacer" />
        {NEXT[sc.period.state]?.filter((n) => n.roles.includes(me.role)).map((n) => (
          <button key={n.to} className={n.to === "LOCKED" || n.to === "BOARD_ENDORSED" ? "crimson" : "primary"} disabled={busy}
                  onClick={() => advance(n.to)}>{n.label}</button>
        ))}
        <a href={`/api/export/${fy}/${sc.period.period_code}.pptx`}><button>Export board slide (PPTX)</button></a>
      </div>
      <div className="stepper">
        {STATES.map((s, i) => <div key={s} className={`step ${i < idx ? "done" : i === idx ? "current" : ""}`}>{STATE_LABEL[s]}</div>)}
      </div>
      {err && <div className="err" style={{ marginBottom: 10 }}>{err}</div>}
      {sc.weights_total !== 100 && <div className="err">KPI weights total {sc.weights_total}% – must equal 100% before endorsement.</div>}
      <table className="sc">
        <thead>
          <tr><th colSpan={3}>{fy} Key Performance Indicators<sup>1</sup></th><th>{fy} Deliverables</th><th>Owner</th>
              <th>Weight</th><th>Status</th><th>Board</th></tr>
        </thead>
        <tbody>
          {sc.pillars.map((p) => p.kpis.map((k, i) => (
            <tr key={k.kpi_id} className="kpi-row" onClick={() => setOpen(k)}>
              {i === 0 && <td className="pillar" rowSpan={p.kpis.length} onClick={(e) => e.stopPropagation()}>{p.name}</td>}
              <td className="code">{k.code}</td>
              <td className="kname">{k.name}</td>
              <td className="dels">
                {k.preamble && <div>{k.preamble}</div>}
                <ol>{k.deliverables.map((d) => <li key={d.seq}>{d.text}</li>)}</ol>
              </td>
              <td className="owner">{k.owner_initials}</td>
              <td className="weight">{k.weight_pct.toFixed(0)}%</td>
              <td className={`status st-${k.status || "none"}`}>{k.status ? STATUS_LABEL[k.status] : "Not reported"}
                {k.ai_draft_accepted && <div className="mini"><span className="badge-ai">AI-assisted</span></div>}</td>
              <td className="board">{k.avg_board_score != null ? `${k.avg_board_score.toFixed(1)}/5` : "–"}
                <div className="mini">{k.n_scores} scores · {k.n_comments} 💬</div></td>
            </tr>
          )))}
        </tbody>
      </table>
      <div className="sc-foot"><span><sup>1</sup>{sc.footnote}</span></div>
      {open && <KpiDrawer me={me} kpi={open} sc={sc} onClose={() => setOpen(null)} onSaved={() => load(sc.period.period_code)} />}
    </div>
  );
}

function KpiDrawer({ me, kpi, sc, onClose, onSaved }: { me: Me; kpi: Kpi; sc: Scorecard; onClose: () => void; onSaved: () => void }) {
  const period = sc.period.period_code;
  const [d, setD] = useState<any>(null);
  const [ev, setEv] = useState<Evidence[] | null>(null);
  const [status, setStatus] = useState(kpi.status || "ON_TRACK");
  const [ownerScore, setOwnerScore] = useState<number | null>(kpi.owner_score);
  const [commentary, setCommentary] = useState(kpi.commentary || "");
  const [draft, setDraft] = useState<any>(null);
  const [draftUsed, setDraftUsed] = useState(false);
  const [comment, setComment] = useState("");
  const [vis, setVis] = useState("ALL");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const reload = () => api.kpi(kpi.kpi_id, period).then(setD).catch((e) => setMsg(String(e)));
  useEffect(() => { reload(); api.evidence(kpi.kpi_id).then((r) => setEv(r.evidence)).catch(() => setEv([])); }, [kpi.kpi_id, period]);

  const canOwner = ["KPI_OWNER", "LLT", "ADMIN"].includes(me.role) && ["OPEN", "OWNER_SUBMITTED"].includes(sc.period.state);
  const canScore = ["BOARD", "ADMIN"].includes(me.role) && sc.period.state !== "LOCKED";
  const canComment = ["BOARD", "LLT", "KPI_OWNER", "ADMIN"].includes(me.role) && sc.period.state !== "LOCKED";
  const run = async (f: () => Promise<any>, ok: string) => {
    setBusy(true); setMsg(null);
    try { await f(); setMsg(ok); await reload(); onSaved(); } catch (e) { setMsg(String(e)); } finally { setBusy(false); }
  };
  const myScore = d?.board_scores?.find((s: any) => s.director_email === me.email || s.mine)?.score ?? kpi.my_score;

  return (
    <>
      <div className="drawer-bg" onClick={onClose} />
      <div className="drawer">
        <header>
          <button className="close" onClick={onClose}>Close</button>
          <div className="mini" style={{ color: "#F3E3E9" }}>{kpi.pillar} · {sc.period.label}</div>
          <h2>{kpi.code} {kpi.name}</h2>
          <div style={{ fontSize: 13 }}>Owner {kpi.owner_initials} ({kpi.owner_role}) · Weight {kpi.weight_pct}%</div>
        </header>
        {msg && <section><div className={msg.startsWith("4") || msg.startsWith("5") || msg.startsWith("Error") ? "err" : "card"}>{msg}</div></section>}
        <section>
          <h3>Deliverables</h3>
          {kpi.preamble && <div>{kpi.preamble}</div>}
          <ol>{kpi.deliverables.map((x) => <li key={x.seq}>{x.text}</li>)}</ol>
        </section>
        <section>
          <h3>Live evidence <span className="note">(latest figures from Lochard's operational and finance systems)</span></h3>
          {ev === null ? "Loading evidence…" : ev.length === 0 ? <div className="note">No live metrics bound to this KPI – qualitative milestone.</div> : (
            <div className="ev">{ev.map((e) => (
              <div className="tile" key={e.label}><div className="v">{e.error ? "n/a" : fmt(e.value, e.kind)}</div>
                <div className="l">{e.label}</div>{e.error && <div className="note">{e.error.slice(0, 80)}</div>}</div>))}</div>
          )}
        </section>
        <section>
          <h3>Owner status update</h3>
          <div className="toolbar">
            <select value={status} disabled={!canOwner} onChange={(e) => setStatus(e.target.value)}>
              {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <label>Self-assessment&nbsp;
              <select value={ownerScore ?? ""} disabled={!canOwner} onChange={(e) => setOwnerScore(e.target.value === "" ? null : +e.target.value)}>
                <option value="">–</option>{[0, 1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
              </select></label>
            <div className="spacer" />
            <button disabled={!canOwner || busy} onClick={() => run(async () => setDraft(await api.aiDraft(kpi.kpi_id, { period, status })), "AI draft ready – review before use.")}>
              ✨ Generate AI draft</button>
          </div>
          {draft && (
            <div className="card" style={{ background: "#FFF9E6", marginBottom: 8 }}>
              <div><span className="badge-ai">AI DRAFT</span> <span className="note">{draft.label || "Review and edit before you save."}</span></div>
              <p style={{ whiteSpace: "pre-wrap" }}>{draft.draft}</p>
              <button onClick={() => { setCommentary(draft.draft); setDraftUsed(true); }}>Use draft (edit below)</button>{" "}
              <button onClick={() => setDraft(null)}>Discard</button>
            </div>
          )}
          <textarea value={commentary} disabled={!canOwner} onChange={(e) => setCommentary(e.target.value)} placeholder="Commentary for the board" />
          <div className="toolbar">
            <button className="primary" disabled={!canOwner || busy} onClick={() => run(() => api.setStatus(kpi.kpi_id, {
              period, status, owner_score: ownerScore, commentary, ai_draft_commentary: draftUsed ? draft?.draft : undefined,
              ai_draft_accepted: draftUsed ? true : undefined, ai_model: draftUsed ? draft?.model : undefined,
            }), "Status saved.")}>Save status</button>
            {!canOwner && <span className="note">Owner updates are {["OPEN", "OWNER_SUBMITTED"].includes(sc.period.state) ? "limited to KPI owners / LLT" : `closed (period ${sc.period.state})`}.</span>}
          </div>
        </section>
        <section>
          <h3>Board scoring</h3>
          <div className="toolbar">
            <div className="scores">{[0, 1, 2, 3, 4, 5].map((n) => (
              <button key={n} className={myScore === n ? "sel" : ""} disabled={!canScore || busy}
                      onClick={() => run(() => api.score(kpi.kpi_id, { period, score: n }), `Your score ${n}/5 saved.`)}>{n}</button>))}</div>
            <span className="note">{canScore ? "Your score (0 = not achieved … 5 = exceeded)" : "Scoring is for directors"}</span>
          </div>
          {d?.board_scores?.length > 0 && (
            <table className="hist"><tbody>{d.board_scores.map((s: any, i: number) => (
              <tr key={i}><td>{s.director_name}</td><td>{s.score}/5</td><td className="note">{s.rationale || ""}</td></tr>))}</tbody></table>
          )}
        </section>
        <section>
          <h3>Comments</h3>
          {d?.comments?.map((c: any) => (
            <div className="comment" key={c.comment_id} style={{ opacity: c.resolved ? .6 : 1 }}>
              <div className="meta"><b>{c.author_name}</b><span>{c.author_role}</span><span className={`vis ${c.visibility}`}>{c.visibility}</span>
                <span>{new Date(c.created_at).toLocaleString()}</span>
                {(c.author_email === me.email || me.role === "ADMIN") &&
                  <button style={{ marginLeft: "auto", fontSize: 11 }} onClick={() => run(() => api.resolveComment(c.comment_id, !c.resolved), "Updated.")}>
                    {c.resolved ? "Reopen" : "Resolve"}</button>}</div>
              <div>{c.body}</div>
            </div>))}
          {canComment && (<>
            <textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Add a comment…" style={{ minHeight: 60 }} />
            <div className="toolbar">
              <select value={vis} onChange={(e) => setVis(e.target.value)}>
                <option value="ALL">Visible to all</option>
                {["LLT", "BOARD", "ADMIN"].includes(me.role) && <option value="LLT_ONLY">LLT & Board only</option>}
                {["BOARD", "ADMIN"].includes(me.role) && <option value="BOARD_ONLY">Board only</option>}
              </select>
              <button className="primary" disabled={!comment.trim() || busy}
                      onClick={() => run(async () => { await api.comment(kpi.kpi_id, { period, body: comment, visibility: vis }); setComment(""); }, "Comment posted.")}>Post</button>
            </div></>)}
        </section>
        <section>
          <h3>History</h3>
          <table className="hist"><thead><tr><th>Period</th><th>Status</th><th>Owner</th><th>Board avg</th><th>Commentary</th></tr></thead>
            <tbody>{d?.history?.map((h: any) => (
              <tr key={h.period_code}><td>{h.label}</td><td className={`st-${h.status}`}>{STATUS_LABEL[h.status]}</td><td>{h.owner_score ?? "–"}</td>
                <td>{h.avg_board_score != null ? h.avg_board_score.toFixed(1) : "–"}</td><td className="note">{(h.commentary || "").slice(0, 140)}</td></tr>))}</tbody></table>
          {d?.audit?.length > 0 && <><h3 style={{ marginTop: 14 }}>Audit trail</h3>
            <table className="hist"><tbody>{d.audit.map((a: any, i: number) => (
              <tr key={i}><td>{new Date(a.at).toLocaleString()}</td><td>{a.actor_email}</td><td>{a.action} {a.entity}</td>
                <td>{a.status || (a.score != null ? `score ${a.score}` : "")}</td></tr>))}</tbody></table></>}
        </section>
      </div>
    </>
  );
}
