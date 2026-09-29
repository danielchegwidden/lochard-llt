import { useEffect, useState } from "react";
import { AgentInfo, api } from "../api";
import { Chat } from "../pages/Agents";

// Floating "Ask Lochard" chat, available on every page. Any page can open it (optionally with an agent and a question):
//   openAsk({ agent: "genie:finance", question: "…" })
export type AskRequest = { agent?: string; question?: string };
export const openAsk = (req: AskRequest = {}) => window.dispatchEvent(new CustomEvent<AskRequest>("lochard:ask", { detail: req }));

const ORDER = ["supervisor", "genie:executive", "genie:finance", "genie:hse", "genie:maintenance", "genie:market", "knowledge"];
// Starter questions for the Leadership Analyst that match the page the user is on.
const PAGE_EXAMPLES: Record<string, string[]> = {
  insights: ["Summarise FY27 year-to-date performance across finance, HSE, maintenance and operations",
             "Which teams have the largest gap between YEO and budget in FY27?",
             "How does VIC gas demand this winter compare with last year, and what does it mean for Iona?"],
  market: ["What were the most important market developments for Lochard last week?",
           "What have competitors and LNG import projects announced in the last month?",
           "How could the proposed gas reservation scheme affect gas storage?"],
  boardpack: ["Which scorecard KPIs are at risk this month and why?",
              "Draft three key messages for the board on HSE and maintenance",
              "What did the August 2026 board report say about HUGS?"],
  dashboards: ["What is schedule compliance for the last 13 weeks?", "How many open HIGH risk observations are there by plant area?"],
};

export default function AskPopup({ hidden, page }: { hidden?: boolean; page?: string }) {
  const [open, setOpen] = useState(false);
  const [wide, setWide] = useState(false);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [sel, setSel] = useState("supervisor");
  const [visited, setVisited] = useState<string[]>(["supervisor"]);
  const [pending, setPending] = useState<{ q: string; id: number } | undefined>();

  useEffect(() => {
    api.agents().then((c) => setAgents(c.agents.filter((a) => a.key !== "router")
      .sort((a, b) => ORDER.indexOf(a.key) - ORDER.indexOf(b.key)))).catch(() => setAgents([]));
  }, []);
  const choose = (k: string) => { setSel(k); setVisited((v) => (v.includes(k) ? v : [...v, k])); };
  useEffect(() => {
    const h = (e: Event) => {
      const d = (e as CustomEvent<AskRequest>).detail || {};
      setOpen(true);
      if (d.agent) choose(d.agent);
      setPending(d.question ? { q: d.question, id: Date.now() } : undefined);
    };
    window.addEventListener("lochard:ask", h);
    return () => window.removeEventListener("lochard:ask", h);
  }, []);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, []);

  const agent = agents.find((a) => a.key === sel);
  return (
    <>
      {!open && !hidden && (
        <button className="ask-fab" onClick={() => setOpen(true)} aria-label="Ask Lochard">
          <span className="spark">✦</span> Ask Lochard
        </button>
      )}
      <div className={`ask-pop ${open && !hidden ? "open" : ""} ${wide ? "wide" : ""}`} role="dialog" aria-label="Ask Lochard">
        <header>
          <div className="ap-title"><span className="spark">✦</span> Ask Lochard</div>
          <select value={sel} onChange={(e) => { setPending(undefined); choose(e.target.value); }}>
            {agents.map((a) => <option key={a.key} value={a.key}>{a.key === "supervisor" ? "Leadership Analyst (all domains)" : a.name}</option>)}
          </select>
          <button className="icon" title={wide ? "Narrow" : "Widen"} onClick={() => setWide(!wide)}>{wide ? "⇲" : "⇱"}</button>
          <button className="icon" title="Close (Esc)" onClick={() => setOpen(false)}>✕</button>
        </header>
        <div className="ap-sub">
          {agent ? <>{agent.kind} · answers run as you, so Unity Catalog governance applies</> : "Loading agents…"}
        </div>
        <div className="ap-body">
          {agents.length > 0 && visited.map((k) => {
            const a = agents.find((x) => x.key === k);
            return a ? (
              <div key={k} style={{ display: k === sel ? "contents" : "none" }}>
                <Chat agent={k === "supervisor" && page && PAGE_EXAMPLES[page] ? { ...a, examples: PAGE_EXAMPLES[page] } : a}
                      compact pending={k === sel ? pending : undefined} />
              </div>
            ) : null;
          })}
        </div>
      </div>
    </>
  );
}
