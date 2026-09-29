import { useEffect, useMemo, useRef, useState } from "react";
import { AgentCatalog, AgentEvent, AgentInfo, api, Me, streamAgent } from "../api";
import { md } from "../md";
import { navigate } from "../nav";
import "./agents.css";

type Step = { kind: string; [k: string]: any };
type Turn = {
  q: string; agent: string; steps: Step[]; live: string; answer: string | null; citations: any[];
  latency_ms?: number; tools_used?: string[]; run_id?: number | null; error?: string; busy: boolean;
  suggested?: string[]; rated?: boolean; conversation_id?: string;
};

const KIND_ICON: Record<string, string> = { "Supervisor Agent": "🧭", "Knowledge Assistant": "📚", "Genie Agent": "💬",
  "Unity AI Gateway": "🔀" };
const TOOL_NODE: Record<string, string> = { exec_genie: "genie:executive", finance_genie: "genie:finance", hse_genie: "genie:hse",
  maintenance_genie: "genie:maintenance", market_ops_genie: "genie:market", iona_knowledge: "knowledge" };

type AgentGroup = { label: string; agents: AgentInfo[] };

// Plain-language "good for" line per assistant (the catalog summary is more technical).
const GOOD_FOR: Record<string, string> = {
  supervisor: "Any leadership question – combines numbers and documents into one answer.",
  "genie:executive": "Scorecard, board scores and headline KPIs, plus market news.",
  "genie:finance": "Budget, actuals, year-end outlook and commitments.",
  "genie:hse": "Observations, investigations, risk and injury rates.",
  "genie:maintenance": "Schedule compliance, backlog and safety-critical work.",
  "genie:market": "VIC gas demand, weather (EDD) and Iona storage flows.",
  knowledge: "Procedures, OEM manuals and board papers – with citations.",
  router: "Compare answer quality, speed and cost across model tiers.",
};

function groupAgents(agents: AgentInfo[]): AgentGroup[] {
  return [
    { label: "Ask anything", agents: agents.filter((a) => a.key === "supervisor") },
    { label: "Specialists", agents: agents.filter((a) => a.key.startsWith("genie:")) },
    { label: "Documents", agents: agents.filter((a) => a.key === "knowledge") },
    { label: "Advanced", agents: agents.filter((a) => a.key === "router") },
  ].filter((g) => g.agents.length > 0);
}

export default function AgentsPage({ me }: { me: Me }) {
  const [cat, setCat] = useState<AgentCatalog | null>(null);
  const [sel, setSel] = useState("supervisor");
  const [err, setErr] = useState<string | null>(null);
  const [runsTick, setRunsTick] = useState(0);
  const reload = () => { setRunsTick((n) => n + 1); return api.agents().then(setCat).catch((e) => setErr(String(e))); };
  useEffect(() => { reload(); }, []);
  const agent = cat?.agents.find((a) => a.key === sel);
  const groups = cat ? groupAgents(cat.agents) : [];

  return (
    <div className="ag-workspace">
      <h1 className="page">Agents</h1>
      <p className="sub">Work with Lochard's AI assistants. Ask questions about business data, specialist topics, documents, and model routing performance.</p>
      {err && <div className="err">{err}</div>}
      <div className="ag-layout">
        {/* Left rail: assistant picker */}
        <nav className="ag-rail">
          {!cat ? <div className="ag-loading">Loading assistants…</div> : (
            <>
              {groups.map((grp) => (
                <div key={grp.label} className="ag-section">
                  <div className="ag-section-label">{grp.label}</div>
                  {grp.agents.map((a) => {
                    const st = cat.stats[a.key];
                    return (
                      <button key={a.key} className={`ag-item ${sel === a.key ? "active" : ""}`} onClick={() => setSel(a.key)}>
                        <div className="ag-item-top">
                          <span className="ag-item-icon">{KIND_ICON[a.kind] || "🤖"}</span>
                          <span className="ag-item-name">{a.name.replace(/^Lochard /, "")}</span>
                          {a.state && a.state !== "READY"
                            ? <span className="ag-dot warn" title="Starting up" />
                            : <span className="ag-dot ok" title="Available" />}
                        </div>
                        <div className="ag-item-desc">{GOOD_FOR[a.key] || a.summary.split(".")[0] + "."}</div>
                      </button>
                    );
                  })}
                </div>
              ))}
            </>
          )}
        </nav>
        {/* Main panel: chat */}
        <main className="ag-main">
          {agent && (agent.key === "router"
            ? <RoutingLab key="router" agent={agent} onDone={reload} />
            : <Chat key={agent.key} agent={agent} onDone={reload} workspace={cat?.workspace} />)}
        </main>
      </div>
      {/* Recent runs */}
      <RecentRuns tick={runsTick} />
      <div className="ag-footer">
        <button className="linkish" onClick={() => navigate("about", { section: "agents" })}>How our agents work</button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ chat with live trace */
type ChatProps = {
  agent: AgentInfo; onFlow?: (a: Set<string>, d: Set<string>) => void; onDone?: () => void; workspace?: string;
  compact?: boolean;                       // popup mode: no header card, examples only before the first question
  pending?: { q: string; id: number };     // ask this question as soon as it changes (e.g. "Ask about this" buttons)
};

export function Chat({ agent, onFlow = () => {}, onDone = () => {}, workspace, compact, pending }: ChatProps) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [q, setQ] = useState("");
  const [lastStep, setLastStep] = useState<string>("");
  const abort = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement | null>(null);
  const busy = turns.some((t) => t.busy);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [turns.length, lastStep]);
  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => { if (pending?.q) send(pending.q); }, [pending?.id]);

  const send = async (question = q) => {
    if (!question.trim() || busy) return;
    setQ("");
    const history = turns.filter((t) => t.answer).flatMap((t) => [{ role: "user", content: t.q }, { role: "assistant", content: t.answer! }]);
    const conv = [...turns].reverse().find((t) => t.conversation_id)?.conversation_id;
    const idx = turns.length;
    setTurns((ts) => [...ts, { q: question, agent: agent.key, steps: [], live: "", answer: null, citations: [], busy: true }]);
    const upd = (f: (t: Turn) => Turn) => setTurns((ts) => ts.map((t, i) => (i === idx ? f(t) : t)));
    const act = new Set<string>([agent.key]); const fin = new Set<string>();
    onFlow(new Set(act), new Set(fin));
    abort.current = new AbortController();
    try {
      await streamAgent({ agent: agent.key, question, history, conversation_id: agent.key.startsWith("genie:") ? conv : undefined },
        (e: AgentEvent) => {
          if (e.type === "delta") upd((t) => ({ ...t, live: t.live + e.text }));
          else if (e.type === "step") {
            const s = e.step as Step;
            if (s.kind === "tool_call" && TOOL_NODE[s.tool]) { act.add(TOOL_NODE[s.tool]); setLastStep(s.label || ""); onFlow(new Set(act), new Set(fin)); }
            if (s.kind === "tool_result" && TOOL_NODE[s.tool]) { act.delete(TOOL_NODE[s.tool]); fin.add(TOOL_NODE[s.tool]); onFlow(new Set(act), new Set(fin)); }
            upd((t) => ({ ...t, steps: [...t.steps, s], live: "" }));
          } else if (e.type === "done") {
            upd((t) => ({ ...t, busy: false, live: "", answer: e.answer, citations: e.citations || [], latency_ms: e.latency_ms,
                           tools_used: e.tools_used, run_id: e.run_id, suggested: e.suggested, conversation_id: e.conversation_id,
                           error: e.error || undefined,
                           steps: t.steps.map((s, i, arr) => (s.kind === "note" && i === arr.map((x) => x.kind).lastIndexOf("note") ? { ...s, kind: "answer" } : s)) }));
          } else if (e.type === "error") upd((t) => ({ ...t, busy: false, error: e.error, run_id: e.run_id }));
        }, abort.current.signal);
    } catch (e) {
      upd((t) => ({ ...t, busy: false, error: String(e) }));
    } finally {
      upd((t) => (t.busy ? { ...t, busy: false } : t));
      fin.add(agent.key); onFlow(new Set(), fin); onDone();
    }
  };

  const composer = (
    <div className="ask" style={{ marginTop: compact ? 0 : 10 }}>
      <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()}
             placeholder={turns.length ? "Ask a follow-up…" : `Ask ${agent.name}…`} disabled={busy} />
      <button className="primary" disabled={!q.trim() || busy} onClick={() => send()}>{busy ? "Working…" : "Ask"}</button>
      {busy && <button onClick={() => abort.current?.abort()}>Stop</button>}
    </div>
  );
  if (compact) return (
    <div className="chat compact">
      <div className="thread">
        {turns.length === 0 && (<>
          <div className="empty">{agent.summary}</div>
          <div className="chips">{agent.examples.map((e) => <button key={e} onClick={() => send(e)}>{e}</button>)}</div>
        </>)}
        {turns.map((t, i) => <TurnView key={i} t={t} onAsk={send} lastStep={lastStep} />)}
        <div ref={end} />
      </div>
      <div className="chat-foot">
        {composer}
        {turns.length > 0 && !busy && <button className="linkish" onClick={() => setTurns([])}>New conversation</button>}
      </div>
    </div>
  );

  return (
    <div className="ag-chat">
      <div className="ag-chat-head">
        <h2>{agent.name}</h2>
        <p className="note">{agent.summary}</p>
      </div>
      <div className="thread">
        {turns.length === 0 && (
          <div className="ag-empty">
            <div className="ag-empty-t">Try one of these</div>
            <div className="ag-examples">{agent.examples.map((e) => (
              <button key={e} className="ag-example" onClick={() => send(e)}><span>✦</span>{e}</button>))}</div>
          </div>
        )}
        {turns.map((t, i) => <TurnView key={i} t={t} onAsk={send} lastStep={lastStep} />)}
        <div ref={end} />
      </div>
      <div className="ag-composer">
        {composer}
        {turns.length > 0 && !busy && <button className="linkish" onClick={() => setTurns([])}>Clear</button>}
      </div>
    </div>
  );
}

function TurnView({ t, onAsk, lastStep }: { t: Turn; onAsk: (q: string) => void; lastStep?: string }) {
  const [open, setOpen] = useState(false);
  const [rated, setRated] = useState<string | null>(null);
  useEffect(() => { if (!t.busy && t.answer) setOpen(false); }, [t.busy]);
  const trace = [...t.steps.filter((s) => s.kind === "retrieval"), ...t.steps.filter((s) => s.kind !== "answer" && s.kind !== "retrieval")];
  const answer = t.answer ?? t.steps.find((s) => s.kind === "answer")?.text;
  return (
    <div className="turn">
      <div className="bubble q">{t.q}</div>
      <div className="bubble a">
        {t.busy && (
          <div className="trace-compact">
            <span className="spinner" /> {lastStep ? `Asking ${lastStep}…` : "Working…"}
          </div>
        )}
        {!t.busy && <div className="trace-head" onClick={() => setOpen(!open)}>
          <span className="ag-caret">{open ? "▾" : "▸"}</span>
          <b>Show how this answer was produced</b>
          <span className="note">{trace.length} step{trace.length !== 1 ? "s" : ""}{t.latency_ms != null ? ` · ${(t.latency_ms / 1000).toFixed(1)}s` : ""}</span>
        </div>}
        {open && !t.busy && <ol className="trace">
          {trace.map((s, i) => <StepView key={i} s={s} />)}
        </ol>}
        {t.error && <div className="err">{t.error}</div>}
        {answer && <div className="md answer-md" dangerouslySetInnerHTML={{ __html: md(answer) }} />}
        {t.citations.length > 0 && (
          <div className="cites"><b>Sources</b>
            <ol>{dedupe(t.citations).map((c) => <li key={c.n} value={c.n}><a href={c.url} target="_blank" rel="noreferrer">{c.title}</a>
              {c.quote && <span className="note"> - "{c.quote.slice(0, 140)}"</span>}</li>)}</ol></div>)}
        {t.suggested && t.suggested.length > 0 && <div className="chips">{t.suggested.map((s) => <button key={s} onClick={() => onAsk(s)}>{s}</button>)}</div>}
        {!t.busy && t.run_id && (
          <div className="turn-foot">
            {rated ? <span className="note">{rated}</span> : <>
              <button onClick={() => api.rateRun(t.run_id!, true).then(() => setRated("Thanks"))}>👍</button>
              <button onClick={() => api.rateRun(t.run_id!, false).then(() => setRated("Flagged"))}>👎</button></>}
          </div>)}
      </div>
    </div>
  );
}

function dedupe(c: any[]) {
  const seen = new Set<string>();
  return c.filter((x) => { const k = x.title + (x.quote || ""); if (seen.has(k)) return false; seen.add(k); return true; });
}

function StepView({ s }: { s: Step }) {
  const t = (ms?: number) => (ms != null ? <span className="ms">{(ms / 1000).toFixed(1)}s</span> : null);
  if (s.kind === "tool_call") return (
    <li className="tstep call"><span className="si">🔧</span><div>
      <div className="st">Calls <b>{s.label}</b> {t(s.at_ms)}</div>
      {s.query && <div className="query">"{s.query}"</div>}</div></li>);
  if (s.kind === "tool_result") return (
    <li className="tstep result"><span className="si">{s.tool === "iona_knowledge" ? "📚" : "📊"}</span><div>
      <div className="st"><b>{s.agent}</b> returned {s.table ? `${s.table.rows.length} row${s.table.rows.length === 1 ? "" : "s"}` : "an answer"}
        {s.elapsed_ms != null && <span className="ms">{(s.elapsed_ms / 1000).toFixed(1)}s</span>}</div>
      {s.table ? <MiniTable t={s.table} /> : <div className="md small" dangerouslySetInnerHTML={{ __html: md(s.text) }} />}</div></li>);
  if (s.kind === "retrieval") return (
    <li className="tstep"><span className="si">🔎</span><div>
      <div className="st"><b>Vector Search</b> over the documents volume {t(s.at_ms)}</div><div className="note">{s.text}</div></div></li>);
  if (s.kind === "status") return (
    <li className="tstep status"><span className="si">{s.status === "COMPLETED" ? "✅" : "⏳"}</span><div>
      <div className="st">{s.text} {t(s.at_ms)}</div><div className="note">{s.status}</div></div></li>);
  if (s.kind === "sql") return (
    <li className="tstep sql"><span className="si">🧮</span><div>
      <div className="st">Generated SQL {t(s.at_ms)}</div>{s.text && <div className="note">{s.text}</div>}
      <details><summary className="note">Show SQL</summary><pre>{s.sql}</pre></details>
      {s.table && <MiniTable t={s.table} />}</div></li>);
  return (
    <li className="tstep note-step"><span className="si">🧭</span><div>
      <div className="st"><b>{s.agent}</b> {t(s.at_ms)}</div><div className="md small" dangerouslySetInnerHTML={{ __html: md(s.text) }} /></div></li>);
}

function MiniTable({ t }: { t: { columns: string[]; rows: any[][] } }) {
  const fmtCell = (v: any) => {
    const n = Number(v);
    if (v === null || v === undefined || v === "") return "-";
    if (!Number.isNaN(n) && String(v).includes(".") && Math.abs(n) < 1 && n !== 0) return `${(n * 100).toFixed(1)}%`;
    if (!Number.isNaN(n) && String(v).length > 8) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
    return String(v);
  };
  return (
    <div className="mini-table"><table className="res">
      <thead><tr>{t.columns.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}</tr></thead>
      <tbody>{t.rows.slice(0, 12).map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{fmtCell(v)}</td>)}</tr>)}</tbody>
    </table>{t.rows.length > 12 && <div className="note">+ {t.rows.length - 12} more rows</div>}</div>
  );
}

/* ------------------------------------------------------------------ routing lab */
function RoutingLab({ agent, onDone }: { agent: AgentInfo; onDone: () => void }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async (question = q) => {
    if (!question.trim()) return;
    setQ(question); setBusy(true); setErr(null); setRes(null);
    try { setRes(await api.routingLab(question)); onDone(); } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  const maxCost = useMemo(() => Math.max(...(res?.arms || []).map((a: any) => a.est_cost_usd || 0), 1e-9), [res]);
  const premium = res?.arms?.find((a: any) => a.tier === "premium");
  const chosen = res?.arms?.find((a: any) => a.chosen);
  return (
    <div className="card chat">
      <div className="chat-head">
        <div><div className="ac-kind">🔀 {agent.kind} - {agent.product}</div><h2>{agent.name}</h2><div className="note">{agent.summary}</div></div>
        <div className="chat-meta"><div><b>Model services</b></div><ul>{agent.tools.map((t) => <li key={t}>{t}</li>)}</ul>
          <div className="note">Identity: runs with your Databricks account permissions.</div></div>
      </div>
      <div className="ask">
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && run()} placeholder="Ask a board question…" />
        <button className="primary" disabled={!q.trim() || busy} onClick={() => run()}>{busy ? "Comparing…" : "Compare tiers"}</button>
      </div>
      <div className="chips">{agent.examples.map((e) => <button key={e} disabled={busy} onClick={() => run(e)}>{e}</button>)}</div>
      {err && <div className="err" style={{ marginTop: 10 }}>{err}</div>}
      {busy && <div className="route-steps"><span className="spinner" /> Economy tier is classifying the question, then all three tiers answer in parallel…</div>}
      {res && (<>
        <div className="route-steps">
          <div className="rs"><span className="si">1</span><div><b>Classify</b> with economy tier ({(res.classifier.latency_ms / 1000).toFixed(1)}s, ${res.classifier_cost_usd.toFixed(5)})
            <div><span className={`lbl lbl-${res.label}`}>{res.label}</span> <span className="note">{res.reason}</span></div></div></div>
          <div className="rs"><span className="si">2</span><div><b>Route</b> to <span className={`tier-pill t-${res.chosen}`}>{res.chosen}</span> tier
            {premium && chosen && premium.est_cost_usd && chosen.est_cost_usd != null && (chosen.tier === "premium"
              ? <span className="note"> - judgement question, so premium is justified (routing adds ${res.classifier_cost_usd.toFixed(5)})</span>
              : <span className="note"> - {(100 * (1 - (chosen.est_cost_usd + res.classifier_cost_usd) / premium.est_cost_usd)).toFixed(0)}% cheaper than always using premium, including the classifier call</span>)}</div></div>
          <div className="rs"><span className="si">3</span><div><b>Compare</b> all tiers on the same grounded prompt (tagged feature=routing_lab)</div></div>
        </div>
        <div className="arms">{res.arms.map((a: any) => (
          <div key={a.tier} className={`arm ${a.chosen ? "chosen" : ""}`}>
            <div className="arm-head"><span className={`tier-pill t-${a.tier}`}>{a.tier}</span>{a.chosen && <span className="lbl lbl-ok">routed here</span>}</div>
            <div className="note">{a.chain}</div>
            {a.error ? <div className="err">{a.error}</div> : <>
              <div className="arm-stats">
                <div><span>Latency</span><b>{(a.latency_ms / 1000).toFixed(1)}s</b></div>
                <div><span>Tokens</span><b>{a.input_tokens}+{a.output_tokens}</b></div>
                <div><span>Est. cost</span><b>${a.est_cost_usd?.toFixed(5)}</b></div>
              </div>
              <div className="costbar"><div style={{ width: `${Math.max(2, 100 * (a.est_cost_usd || 0) / maxCost)}%` }} /></div>
              <div className="note">served by {a.served_model}</div>
              <div className="md small" dangerouslySetInnerHTML={{ __html: md(a.text) }} /></>}
          </div>))}</div>
        <details style={{ marginTop: 8 }}><summary className="note">Grounding facts sent to every tier</summary><pre>{res.facts}</pre></details>
      </>)}
    </div>
  );
}

/* ------------------------------------------------------------------ history */
function RecentRuns({ tick }: { tick: number }) {
  const [runs, setRuns] = useState<any[] | null>(null);
  useEffect(() => { api.agentRuns().then((r) => setRuns(r.runs)).catch(() => setRuns([])); }, [tick]);
  if (!runs?.length) return null;
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h3 style={{ marginTop: 0, color: "var(--crimson)" }}>Your recent questions</h3>
      <table className="hist"><thead><tr><th>When</th><th>Agent</th><th>Question</th></tr></thead>
        <tbody>{runs.map((r) => <tr key={r.run_id}><td>{new Date(r.created_at).toLocaleString()}</td><td>{r.agent}</td><td>{r.question}</td></tr>)}</tbody></table>
    </div>
  );
}
