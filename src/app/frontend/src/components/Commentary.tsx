import { useEffect, useState } from "react";
import { api, Commentary as Rec, Me } from "../api";
import { ROLE_LABEL } from "../nav";

// Manager / analyst commentary with a leader review step. The same component is used on Leadership Insights,
// the Market Intelligence Hub and the board pack. What it shows depends on the (effective) app role:
//   Manager / Analyst  – write, draft with AI, save, submit for review
//   Leader             – read submitted / approved text, approve or return with a note (and edit if needed)
//   Board / observer   – approved text only
export type CommentaryProps = {
  me: Me; scope: "insights" | "market" | "boardpack"; subject: string; periodKey: string; periodLabel: string;
  title?: string; owner?: string; placeholder?: string; compact?: boolean;
  onChange?: (rec: Rec | null) => void;
};

const STATUS: Record<string, [string, string]> = {
  DRAFT: ["Draft", "cm-draft"], SUBMITTED: ["Awaiting leader review", "cm-submitted"],
  APPROVED: ["Approved", "cm-approved"], RETURNED: ["Returned for changes", "cm-returned"],
};

const when = (s?: string | null) => (s ? new Date(s).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "");

export default function Commentary({ me, scope, subject, periodKey, periodLabel, title = "Commentary", owner, placeholder,
                                     compact, onChange }: CommentaryProps) {
  const [rec, setRec] = useState<Rec | null | undefined>(undefined);
  const [perm, setPerm] = useState({ can_write: false, can_review: false });
  const [text, setText] = useState("");
  const [editing, setEditing] = useState(false);
  const [ai, setAi] = useState<{ draft: string; model: string } | null>(null);
  const [aiUsed, setAiUsed] = useState(false);
  const [returning, setReturning] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const apply = (r: Rec | null) => { setRec(r); setText(r?.body ?? ""); setAiUsed(false); onChange?.(r); };
  const load = () => api.commentary(scope, periodKey, subject)
    .then((d) => { setPerm({ can_write: d.can_write, can_review: d.can_review }); apply(d.items[subject] ?? null); })
    .catch((e) => { setErr(String(e)); setRec(null); });
  useEffect(() => { setRec(undefined); setEditing(false); setAi(null); setErr(null); load(); }, [scope, subject, periodKey, me.role]);

  const run = async (label: string, f: () => Promise<Rec | void>) => {
    setBusy(label); setErr(null);
    try { const r = await f(); if (r) apply(r); } catch (e) { setErr(String(e)); } finally { setBusy(null); }
  };
  const save = () => api.saveCommentary({ scope, subject, period_key: periodKey, body: text, ai_assisted: aiUsed,
                                          ai_model: aiUsed ? ai?.model : undefined });
  const dirty = text.trim() !== (rec?.body ?? "").trim();

  const isWriterRole = me.role === "KPI_OWNER" || me.role === "ADMIN";
  // Managers land straight in the editor while the text is theirs to work on; everyone else opts in with "Edit".
  const showEditor = perm.can_write && (editing || (isWriterRole && (!rec || rec.status === "DRAFT" || rec.status === "RETURNED")));
  const st = rec ? STATUS[rec.status] : null;

  if (rec === undefined) return <div className={`cm ${compact ? "cm-compact" : ""}`}><div className="cm-head"><b>{title}</b></div><div className="note">Loading…</div></div>;

  return (
    <div className={`cm ${compact ? "cm-compact" : ""}`}>
      <div className="cm-head">
        <b>{title}</b><span className="note">{periodLabel}{owner ? ` · owner: ${owner}` : ""}</span>
        {st && <span className={`cm-pill ${st[1]}`}>{st[0]}</span>}
        {rec?.ai_assisted && <span className="cm-ai" title="Started from an AI draft, then edited and submitted by the author">AI-assisted</span>}
      </div>

      {rec?.status === "RETURNED" && rec.review_note && (
        <div className="cm-return"><b>{rec.reviewer_name || "Leader"}:</b> {rec.review_note}</div>)}

      {showEditor ? (
        <>
          {ai && (
            <div className="cm-aidraft">
              <div className="note"><span className="badge-ai">AI DRAFT</span> Review and edit before you submit.</div>
              <p>{ai.draft}</p>
              <button onClick={() => { setText(ai.draft); setAiUsed(true); setAi(null); }}>Use this draft</button>{" "}
              <button className="linkish" onClick={() => setAi(null)}>Discard</button>
            </div>
          )}
          <textarea value={text} onChange={(e) => setText(e.target.value)} disabled={!!busy}
                    placeholder={placeholder || `What happened in ${periodLabel}, why it matters, and what happens next…`} />
          <div className="cm-actions">
            <button disabled={!!busy} onClick={() => run("ai", async () => {
              const d = await api.draftCommentary(scope, subject, periodKey); setAi({ draft: d.draft, model: d.model });
            })}>{busy === "ai" ? "Drafting…" : "✨ Draft with AI"}</button>
            <div className="spacer" />
            {editing && !isWriterRole && <button className="linkish" onClick={() => { setEditing(false); setText(rec?.body ?? ""); }}>Cancel</button>}
            <button disabled={!!busy || !text.trim() || !dirty} onClick={() => run("save", save)}>{busy === "save" ? "Saving…" : "Save draft"}</button>
            <button className="primary" disabled={!!busy || !text.trim() || (!dirty && rec?.status === "SUBMITTED")}
                    onClick={() => run("submit", async () => {
                      const r = dirty || !rec ? await save() : rec;
                      const s = await api.submitCommentary(r.commentary_id); setEditing(false); return s;
                    })}>{busy === "submit" ? "Submitting…" : rec?.status === "SUBMITTED" && !dirty ? "Submitted" : "Submit for review"}</button>
          </div>
        </>
      ) : rec ? (
        <>
          <div className="cm-body">{rec.body.split(/\n{2,}/).map((p, i) => <p key={i}>{p}</p>)}</div>
          <div className="cm-meta">
            {rec.author_name || rec.author_email} · {ROLE_LABEL[rec.author_role || ""] || rec.author_role} · {when(rec.submitted_at || rec.updated_at)}
            {rec.status === "APPROVED" && rec.reviewer_name && <> · approved by {rec.reviewer_name} {when(rec.reviewed_at)}</>}
          </div>
          {perm.can_review && rec.status === "SUBMITTED" && (
            returning ? (
              <div className="cm-actions">
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="What should change?" style={{ flex: 1 }} />
                <button className="linkish" onClick={() => setReturning(false)}>Cancel</button>
                <button disabled={!note.trim() || !!busy} onClick={() => run("return", async () => {
                  const r = await api.reviewCommentary(rec.commentary_id, "RETURN", note); setReturning(false); setNote(""); return r;
                })}>Return to author</button>
              </div>
            ) : (
              <div className="cm-actions">
                <button className="primary" disabled={!!busy} onClick={() => run("approve", () => api.reviewCommentary(rec.commentary_id, "APPROVE"))}>
                  {busy === "approve" ? "Approving…" : "Approve"}</button>
                <button disabled={!!busy} onClick={() => setReturning(true)}>Return with note</button>
                <div className="spacer" />
                {perm.can_write && <button className="linkish" onClick={() => setEditing(true)}>Edit</button>}
              </div>
            ))}
          {perm.can_write && !(perm.can_review && rec.status === "SUBMITTED") && (
            <div className="cm-actions"><div className="spacer" />
              <button className="linkish" onClick={() => setEditing(true)} title="Editing returns the text to draft">
                {rec.status === "APPROVED" ? "Revise" : "Edit"}</button></div>)}
        </>
      ) : (
        <div className="cm-empty">
          {perm.can_write ? <button className="linkish" onClick={() => setEditing(true)}>+ Add commentary</button>
            : <span className="note">No commentary {me.role === "LLT" ? "submitted " : ""}for {periodLabel} yet.</span>}
        </div>
      )}
      {err && <div className="err" style={{ marginTop: 6 }}>{err}</div>}
    </div>
  );
}
