import { useEffect, useState } from "react";
import Diagram, { Box, Frame, Link } from "../components/arch/Diagram";
import "./architecture.css";

// Architecture tab: every process flow and technical explanation lives here, so the business pages stay clean.
type Section = "platform" | "agents" | "market" | "commentary" | "governance" | "technical";
const SECTIONS: { id: Section; label: string }[] = [
  { id: "platform", label: "Platform overview" },
  { id: "agents", label: "How the agents work" },
  { id: "market", label: "Market intelligence flow" },
  { id: "commentary", label: "Commentary & board reporting" },
  { id: "governance", label: "Identity, roles & governance" },
  { id: "technical", label: "Technical notes" },
];
const C = { src: "#5F5856", pipe: "#F47525", ai: "#ED6D05", uc: "#A3194E", uc2: "#7E0F3A", use: "#52B2E5", app: "#565150",
            pg: "#8E4737", gw: "#1E1E1E" };

export default function AboutPage({ section }: { section?: string }) {
  const [active, setActive] = useState<Section>(SECTIONS.some((s) => s.id === section) ? (section as Section) : "platform");
  useEffect(() => { if (section && SECTIONS.some((s) => s.id === section)) setActive(section as Section); }, [section]);
  return (
    <div className="arch-page">
      <div>
        <h1 className="page">Architecture</h1>
        <p className="sub">How the Lochard data intelligence platform and this portal work, end to end. Everything is serverless and
          deployed from one Declarative Automation Bundle.</p>
      </div>
      <nav className="arch-nav">
        {SECTIONS.map((s) => (
          <button key={s.id} className={`arch-nav-item ${active === s.id ? "active" : ""}`} onClick={() => setActive(s.id)}>{s.label}</button>
        ))}
      </nav>
      <div className="arch-content" key={active}>
        {active === "platform" && <Platform />}
        {active === "agents" && <Agents />}
        {active === "market" && <Market />}
        {active === "commentary" && <Commentary />}
        {active === "governance" && <Governance />}
        {active === "technical" && <Technical />}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------------------------------ 1. platform */
function Platform() {
  const boxes: Box[] = [
    { id: "s1", x: 10, y: 40, w: 200, h: 112, title: "Enterprise systems", fill: C.src,
      lines: ["Business Central (finance)", "Maximo (maintenance)", "HSE system · Iona historian", "Planner Excel files"] },
    { id: "s2", x: 10, y: 166, w: 200, h: 112, title: "Market & public data", fill: C.src,
      lines: ["AEMO nemweb (VicGas reports)", "News search · web research", "ASX announcements", "Lochard newsroom"] },
    { id: "s3", x: 10, y: 292, w: 200, h: 84, title: "Documents", fill: C.src,
      lines: ["Procedures · OEM manuals", "Board papers · invoices"] },
    { id: "p1", x: 250, y: 40, w: 200, h: 168, title: "Lakeflow pipelines", fill: C.pipe,
      lines: ["Auto Loader → bronze", "Expectations, quarantine", "AUTO CDC / SCD2 → silver", "Star schemas → gold", "7 serverless pipelines",
              "Daily orchestration jobs"] },
    { id: "p2", x: 250, y: 222, w: 200, h: 112, title: "AI Functions", fill: C.ai,
      lines: ["ai_parse_document", "ai_query enrichment (JSON)", "ai_extract · ai_classify", "each row processed once"] },
    { id: "u1", x: 490, y: 40, w: 210, h: 126, title: "Semantic layer", fill: C.uc,
      lines: ["lochard_semantic views", "UC metric views (KPIs)", "Market intelligence views", "Lineage and audit"] },
    { id: "u2", x: 490, y: 190, w: 210, h: 112, title: "Governance (ABAC)", fill: C.uc2,
      lines: ["Governed tags", "Row filters · column masks", "Persona entitlements", "applied to every query"] },
    { id: "c1", x: 740, y: 40, w: 200, h: 70, title: "AI/BI dashboards", fill: C.use, lines: ["Finance · HSE · Maintenance", "Ops · Market intelligence"] },
    { id: "c2", x: 740, y: 124, w: 200, h: 70, title: "Genie agents", fill: C.use, lines: ["5 domain agents", "text-to-SQL on metric views"] },
    { id: "c3", x: 740, y: 208, w: 200, h: 70, title: "Agent Bricks", fill: C.use, lines: ["Leadership Analyst (supervisor)", "Iona Knowledge (documents)"] },
    { id: "c4", x: 740, y: 292, w: 200, h: 70, title: "Market Intelligence Analyst", fill: C.use, lines: ["tool-calling agent", "writes the weekly brief"] },
    { id: "a1", x: 980, y: 40, w: 170, h: 180, title: "Leadership Portal", fill: C.app,
      lines: ["Leadership Insights", "Market Intelligence", "Board Pack · PDF", "Agents · Dashboards", "Role-based views", "(this app)"] },
    { id: "a2", x: 980, y: 240, w: 170, h: 112, title: "Lakebase", fill: C.pg,
      lines: ["Scorecard · scores", "Commentary workflow", "Board packs · audit", "synced nightly to Delta"] },
    { id: "g1", x: 250, y: 400, w: 900, h: 50, title: "Unity AI Gateway – model services: economy · standard · premium · routed assistant",
      fill: C.gw, lines: ["fallbacks, rate limits, usage tracking and inference tables for every LLM call"] },
  ];
  const links: Link[] = [
    { from: "s1", to: "p1" }, { from: "s2", to: "p1" }, { from: "s3", to: "p2" }, { from: "s2", to: "p2" },
    { from: "p1", to: "u1" }, { from: "p2", to: "u1" }, { from: "u2", to: "u1", out: "t", in: "b" },
    { from: "u1", to: "c1" }, { from: "u1", to: "c2" }, { from: "u1", to: "c3" }, { from: "u1", to: "c4" },
    { from: "c1", to: "a1" }, { from: "c2", to: "a1" }, { from: "c3", to: "a1" }, { from: "c4", to: "a1" },
    { from: "a1", to: "a2", out: "b", in: "t" },
    { from: "p2", to: "g1", out: "b", in: "t", straight: true }, { from: "c4", to: "g1", out: "b", in: "t", straight: true },
    { from: "a2", to: "g1", out: "b", in: "t", straight: true, dashed: true },
  ];
  return (
    <section className="arch-section">
      <h2>Platform overview</h2>
      <p>Operational, market and document data land in Unity Catalog volumes, flow through serverless Lakeflow pipelines into a governed
        semantic layer, and are consumed by dashboards, Genie agents, AI agents and this portal. The portal keeps its own workflow data
        (scorecard, commentary, board packs) in Lakebase, a serverless Postgres database, and syncs it back to Delta nightly.</p>
      <Diagram id="platform" w={1160} h={500} boxes={boxes} links={links}
               frames={[{ x: 480, y: 26, w: 230, h: 290, title: "", tone: "pink" }]}
               caption="Data flows left to right; every consumer reads the same governed semantic layer." />
      <div className="arch-band">Unity Catalog – one governance model for data, dashboards, Genie, apps and AI</div>
      <div className="arch-cols">
        <div><h3>Ingest & transform</h3><ul>
          <li>Seven serverless Lakeflow Spark Declarative Pipelines: shared dimensions, finance, HSE, maintenance, market &amp; operations, documents, market intelligence.</li>
          <li>Data quality expectations, quarantine tables and SCD2 history are recorded in each pipeline's event log.</li>
          <li>Real AEMO nemweb data (INT091, INT287, INT313, INT037b, INT153) lands daily at 15:30 AEST.</li></ul></div>
        <div><h3>Serve</h3><ul>
          <li>Dashboards, Genie and the portal read only <code>lochard_semantic</code>, so a metric is defined once.</li>
          <li>Ungoverned dashboards run on a Lakehouse//RT warehouse; governed ones stay on serverless PRO so row filters and masks apply.</li>
          <li>All AI calls go through Unity AI Gateway model services with cost tiers.</li></ul></div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------------------------------------ 2. agents */
function Agents() {
  const boxes: Box[] = [
    { id: "u", x: 10, y: 150, w: 160, h: 84, title: "You", fill: C.uc, outline: true, lines: ["leader, manager or", "board director", "(signed-in identity)"] },
    { id: "sup", x: 210, y: 140, w: 220, h: 104, title: "Leadership Analyst", fill: C.uc,
      lines: ["Supervisor Agent (Agent Bricks)", "plans the question, calls", "specialists, composes one", "answer with sources"] },
    { id: "g", x: 490, y: 46, w: 330, h: 104, title: "Genie agents", fill: C.use,
      lines: ["Executive & Board · Finance · HSE", "Maintenance · Gas Market & Iona Ops", "text-to-SQL on UC metric views,", "trusted example SQL and benchmarks"] },
    { id: "k", x: 490, y: 170, w: 330, h: 90, title: "Iona Knowledge", fill: C.use,
      lines: ["Knowledge Assistant: procedures, OEM", "manuals, board papers – every claim cited"] },
    { id: "r", x: 490, y: 280, w: 330, h: 90, title: "Model routing lab", fill: C.app,
      lines: ["economy tier classifies the question", "(lookup / analytical / strategic) and", "routes it; all three tiers compared"] },
    { id: "w", x: 880, y: 56, w: 270, h: 84, title: "SQL warehouse (as you)", fill: C.pipe, lines: ["serverless; ABAC row filters", "and masks apply to each answer"] },
    { id: "v", x: 880, y: 176, w: 270, h: 70, title: "Vector Search", fill: C.pipe, lines: ["index over parsed documents"] },
    { id: "gw", x: 880, y: 280, w: 270, h: 90, title: "Unity AI Gateway", fill: C.gw,
      lines: ["economy · standard · premium tiers", "fallbacks · rate limits", "usage and inference tables"] },
    { id: "lb", x: 210, y: 300, w: 220, h: 70, title: "Lakebase – agent runs", fill: C.pg, lines: ["question, tools, latency, rating"] },
  ];
  const links: Link[] = [
    { from: "u", to: "sup" }, { from: "sup", to: "g" }, { from: "sup", to: "k" },
    { from: "g", to: "w", label: "SQL" }, { from: "k", to: "v" }, { from: "r", to: "gw" },
    { from: "sup", to: "lb", out: "b", in: "t", label: "trace" },
  ];
  return (
    <section className="arch-section">
      <h2>How the agents work</h2>
      <p>The <b>Ask Lochard</b> button and the Agents page talk to the same assistants. A question to the Leadership Analyst is planned by
        an Agent Bricks Supervisor Agent, which calls the specialists it needs as tools and composes one board-ready answer.</p>
      <Diagram id="agents" w={1160} h={390} boxes={boxes} links={links}
               frames={[{ x: 474, y: 22, w: 362, h: 360, title: "Specialists (called as tools)", tone: "sky" }]}
               caption="Each step is streamed to the page as it happens and can be expanded under the answer." />
      <div className="arch-cols">
        <div><h3>Identity</h3><ul>
          <li>Every call runs on behalf of the signed-in user (OBO token), so Genie SQL and document retrieval respect that person's Unity Catalog permissions, row filters and masks.</li>
          <li>Viewers other than workspace admins need <code>CAN_QUERY</code> on the two Agent Bricks endpoints.</li></ul></div>
        <div><h3>Tracing and feedback</h3><ul>
          <li>The stream is normalised into steps: tool call (with the exact sub-question), sub-agent result (a Genie table, or cited text), narration and the final answer.</li>
          <li>Each run and its 👍/👎 rating is stored in Lakebase (<code>scorecard.agent_run</code>).</li>
          <li>The routing lab tags gateway requests <code>feature=routing_lab</code>, visible in <code>system.ai_gateway.usage</code>.</li></ul></div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------------------------------------ 3. market intelligence */
function Market() {
  const boxes: Box[] = [
    { id: "n1", x: 10, y: 30, w: 200, h: 70, title: "News search", fill: C.src, lines: ["every watchlist entity + topic", "headline and publisher"] },
    { id: "n2", x: 10, y: 114, w: 200, h: 84, title: "Web research agent", fill: C.src, lines: ["hosted web search per theme", "and week → article URLs", "→ full article text"] },
    { id: "n3", x: 10, y: 212, w: 200, h: 70, title: "ASX announcements", fill: C.src, lines: ["AGL · ORG · APA · BPT · AEL", "STO · WDS · VEA (PDFs)"] },
    { id: "n4", x: 10, y: 296, w: 200, h: 56, title: "Lochard newsroom", fill: C.src, lines: ["dated releases"] },
    { id: "col", x: 250, y: 130, w: 170, h: 98, title: "Collector job", fill: C.pg, lines: ["daily 07:00 AEST", "watchlist.yml", "idempotent re-runs"] },
    { id: "vol", x: 450, y: 130, w: 170, h: 98, title: "UC Volume", fill: C.app, lines: ["market_intel/items", "…/documents (PDF)", "…/reference"] },
    { id: "b", x: 670, y: 56, w: 140, h: 84, title: "Bronze", fill: C.pipe, lines: ["Auto Loader", "items + PDFs"] },
    { id: "s1", x: 830, y: 56, w: 150, h: 84, title: "ai_parse_document", small: true, fill: C.ai, lines: ["PDF → text"] },
    { id: "s2", x: 830, y: 160, w: 150, h: 100, title: "ai_query enrichment", small: true, fill: C.ai,
      lines: ["relevance · entities", "topic · signal", "sentiment · importance", "summary · why it matters"] },
    { id: "gold", x: 1000, y: 56, w: 150, h: 204, title: "Gold", fill: C.uc2,
      lines: ["one row per story", "(duplicates merged)", "weekly aggregates", "watchlist"] },
    { id: "ag", x: 650, y: 300, w: 280, h: 128, title: "Market Intelligence Analyst", fill: C.uc,
      lines: ["tool-calling agent (Claude Sonnet)", "list_items · read_item · search_items", "entity_trend · prior_brief", "internal_context (Iona, VIC demand)", "submit_brief – cited item ids checked"] },
    { id: "br", x: 960, y: 300, w: 190, h: 70, title: "Weekly brief (Delta)", fill: C.app, lines: ["MLflow trace per brief"] },
    { id: "sem", x: 960, y: 388, w: 190, h: 56, title: "Semantic views", fill: C.uc, lines: ["v_market_intel_*"] },
    { id: "hub", x: 250, y: 470, w: 230, h: 60, title: "Market Intelligence Hub", fill: C.use, lines: ["brief · signals · item feed"] },
    { id: "dash", x: 510, y: 470, w: 200, h: 60, title: "AI/BI dashboard", fill: C.use, lines: ["trends · item explorer"] },
    { id: "bp", x: 740, y: 470, w: 200, h: 60, title: "Board Pack", fill: C.use, lines: ["market slide"] },
    { id: "lb", x: 10, y: 470, w: 210, h: 60, title: "Lakebase", fill: C.pg, lines: ["pins · notes · commentary"] },
  ];
  const links: Link[] = [
    { from: "n1", to: "col" }, { from: "n2", to: "col" }, { from: "n3", to: "col" }, { from: "n4", to: "col" },
    { from: "col", to: "vol" }, { from: "vol", to: "b" }, { from: "b", to: "s1" }, { from: "s1", to: "s2", out: "b", in: "t" },
    { from: "b", to: "s2", out: "b", in: "l" }, { from: "s2", to: "gold" },
    { from: "gold", to: "ag", out: "b", in: "t" }, { from: "ag", to: "br" }, { from: "br", to: "sem", out: "b", in: "t" },
    { from: "sem", to: "hub", out: "b", in: "t" }, { from: "sem", to: "dash", out: "b", in: "t" }, { from: "sem", to: "bp", out: "b", in: "t" },
    { from: "lb", to: "hub", dashed: true },
  ];
  return (
    <section className="arch-section">
      <h2>Market intelligence flow</h2>
      <p>Every morning a collector gathers public information about Lochard, its customers, competitors, upstream suppliers, regulators
        and the east-coast gas market. A Lakeflow pipeline parses the documents and classifies every item with AI, and the Market
        Intelligence Analyst agent reads the week's items and writes a brief. Analysts curate the result in the portal; leaders see the
        curated view.</p>
      <Diagram id="market" w={1160} h={545} boxes={boxes} links={links}
               frames={[{ x: 655, y: 26, w: 505, h: 250, title: "Pipeline lochard-market-intel-medallion", tone: "sand" }]}
               caption="Streaming tables mean each document is parsed, and each item enriched, exactly once." />
      <div className="arch-cols">
        <div><h3>What gets collected</h3><ul>
          <li>Watchlist in <code>src/market_intel/watchlist.yml</code>: 23 entities in six groups (customers, competitors, upstream suppliers, regulators, governments and Lochard), plus topics such as underground storage, LNG imports, winter supply and gas policy. Items about none of them are grouped as Industry &amp; market.</li>
          <li>News search yields headlines; the web research agent returns dated publisher articles, whose text is fetched; ASX PDFs are parsed in the pipeline.</li>
          <li>The portal shows only AI summaries, short excerpts and links to the original sources.</li></ul></div>
        <div><h3>How the brief is written</h3><ul>
          <li>The agent must use tools to see items before it can cite them; unknown ids are removed before the brief is saved.</li>
          <li>Counts, publishers and sentiment by group are computed from the data, not by the model.</li>
          <li>The current and previous week are refreshed daily; older weeks are written once (backfill: <code>mode=backfill</code>).</li></ul></div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------------------------------------ 4. commentary */
function Commentary() {
  const frames: Frame[] = [
    { x: 10, y: 14, w: 1140, h: 104, title: "Manager / Analyst", tone: "sky" },
    { x: 10, y: 128, w: 1140, h: 104, title: "Leader", tone: "sand" },
    { x: 10, y: 242, w: 1140, h: 96, title: "Board", tone: "pink" },
  ];
  const boxes: Box[] = [
    { id: "m1", x: 150, y: 40, w: 220, h: 64, title: "Draft commentary", fill: C.use, outline: true, lines: ["per domain, week or slide", "optional AI draft, always labelled"] },
    { id: "m2", x: 420, y: 40, w: 180, h: 64, title: "Submit for review", fill: C.use, outline: true, lines: ["locks the text for review"] },
    { id: "l1", x: 420, y: 154, w: 180, h: 64, title: "Review", fill: C.pipe, outline: true, lines: ["approve, or return", "with a note"] },
    { id: "l2", x: 650, y: 154, w: 150, h: 64, title: "Approved", fill: C.pipe, outline: true, lines: ["visible to the Board"] },
    { id: "l3", x: 840, y: 154, w: 140, h: 64, title: "Board Pack", fill: C.pipe, outline: true, lines: ["12 slides", "readiness"] },
    { id: "l4", x: 1010, y: 154, w: 130, h: 64, title: "Finalise", fill: C.pipe, outline: true, lines: ["versioned", "snapshot + PDF"] },
    { id: "b1", x: 1010, y: 266, w: 130, h: 60, title: "Board pack PDF", fill: C.uc, outline: true, lines: ["download, sent"] },
    { id: "b2", x: 650, y: 266, w: 330, h: 60, title: "Scorecard scoring", fill: C.uc, outline: true, lines: ["directors score each KPI 0–5 and comment"] },
    { id: "st1", x: 10, y: 372, w: 170, h: 48, title: "Owner updates", small: true, fill: C.app },
    { id: "st2", x: 220, y: 372, w: 170, h: 48, title: "Submitted", small: true, fill: C.app },
    { id: "st3", x: 430, y: 372, w: 170, h: 48, title: "LLT reviewed", small: true, fill: C.app },
    { id: "st4", x: 640, y: 372, w: 170, h: 48, title: "Board endorsed", small: true, fill: C.app },
    { id: "st5", x: 850, y: 372, w: 120, h: 48, title: "Locked", small: true, fill: C.app },
    { id: "sy", x: 1000, y: 372, w: 150, h: 48, title: "Nightly sync", small: true, fill: C.pg, lines: ["Lakebase → gold"] },
  ];
  const links: Link[] = [
    { from: "m1", to: "m2" }, { from: "m2", to: "l1", out: "b", in: "t" }, { from: "l1", to: "m1", out: "l", in: "b", dashed: true, label: "returned" },
    { from: "l1", to: "l2" }, { from: "l2", to: "l3" }, { from: "l3", to: "l4" }, { from: "l4", to: "b1", out: "b", in: "t" },
    { from: "st1", to: "st2" }, { from: "st2", to: "st3" }, { from: "st3", to: "st4" }, { from: "st4", to: "st5" }, { from: "st5", to: "sy", dashed: true },
  ];
  return (
    <section className="arch-section">
      <h2>Commentary & board reporting</h2>
      <p>Commentary is written once and reused: a manager's approved commentary on Leadership Insights, the analyst's weekly market
        commentary and each slide's text all flow into the Board Pack, which a leader finalises into a versioned PDF for the Board.</p>
      <Diagram id="commentary" w={1160} h={430} boxes={boxes} links={links} frames={frames}
               caption="Top: the commentary workflow (shared by every page). Bottom: the monthly scorecard period workflow." />
      <div className="arch-cols">
        <div><h3>Rules</h3><ul>
          <li>Any edit returns commentary to draft, so changed text is always reviewed again.</li>
          <li>Drafts stay with managers; leaders see submitted and approved text; the Board sees approved text only.</li>
          <li>AI drafts are grounded on the same governed numbers the page shows, labelled, and must be accepted and edited by a person.</li></ul></div>
        <div><h3>Records</h3><ul>
          <li>Commentary, scores, approvals and board-pack versions are stored in Lakebase with an append-only audit log.</li>
          <li>A finalised pack is a frozen snapshot; the PDF is generated from it, so later data changes do not alter what the Board received.</li>
          <li>The scorecard is synced nightly to <code>lochard_gold.fact_board_*</code> for Genie and dashboards.</li></ul></div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------------------------------------ 5. identity */
function Governance() {
  const boxes: Box[] = [
    { id: "u", x: 10, y: 110, w: 160, h: 70, title: "Signed-in user", fill: C.uc, outline: true, lines: ["Databricks single sign-on"] },
    { id: "p", x: 210, y: 110, w: 190, h: 70, title: "Databricks Apps proxy", fill: C.app, lines: ["forwards the user's token", "and email to the app"] },
    { id: "be", x: 440, y: 96, w: 210, h: 98, title: "Portal backend", fill: C.app,
      lines: ["resolves the portal role", "Leader · Manager · Board · Admin", "admin 'view as' lens"] },
    { id: "uc", x: 780, y: 20, w: 200, h: 100, title: "Unity Catalog (as user)", fill: C.uc,
      lines: ["SQL · Genie · Agent Bricks", "ABAC row filters, masks", "persona: principal_persona"] },
    { id: "lb", x: 780, y: 170, w: 200, h: 100, title: "Lakebase (as the app)", fill: C.pg,
      lines: ["portal roles · commentary", "scorecard · board packs", "row-level security on comments"] },
    { id: "ui", x: 1010, y: 96, w: 140, h: 98, title: "What you see", fill: C.use, lines: ["role-based pages", "and actions; only", "data you may see"] },
  ];
  const links: Link[] = [
    { from: "u", to: "p" }, { from: "p", to: "be" }, { from: "be", to: "uc", label: "user token" }, { from: "be", to: "lb", label: "app identity" },
    { from: "uc", to: "ui" }, { from: "lb", to: "ui" },
  ];
  return (
    <section className="arch-section">
      <h2>Identity, roles & governance</h2>
      <p>Two independent controls decide what a person gets. The <b>portal role</b> decides what they can do in the portal; the
        <b> data persona</b> decides which rows and columns they can see anywhere on the platform.</p>
      <Diagram id="identity" w={1160} h={290} boxes={boxes} links={links} caption="Data access is always evaluated for the real user, even when an admin uses the 'view as' lens." />
      <div className="arch-cols">
        <div><h3>Portal roles</h3><ul>
          <li><b>Leader</b> reviews and approves commentary, finalises the Board Pack.</li>
          <li><b>Manager / Analyst</b> owns the numbers: drafts commentary, curates market signals.</li>
          <li><b>Board director</b> sees approved commentary and finalised packs; scores KPIs.</li>
          <li><b>Administrator</b> can preview any role with "Viewing as" (it only narrows portal permissions).</li>
          <li>Role precedence: explicit portal role, then the Unity Catalog persona, then observer.</li></ul></div>
        <div><h3>Data personas (ABAC)</h3><ul>
          <li>Governed tags <code>lochard_pii</code>, <code>lochard_rls</code>, <code>lochard_domain</code>, <code>lochard_sensitivity</code> drive seven ABAC policies on <code>lochard_gold</code>.</li>
          <li>Personas come from <code>lochard_governance.principal_persona</code> (account groups <code>lochard_&lt;persona&gt;</code> once they exist) and can be switched on the AI &amp; Governance page.</li>
          <li>Dashboards are embedded without shared credentials, so each viewer queries as themselves.</li></ul></div>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------------------------------------ 6. technical notes */
function Technical() {
  return (
    <section className="arch-section">
      <h2>Technical notes</h2>
      <div className="arch-callout">
        <b>Moving to Lochard's production workspace.</b> Catalog and schema names (currently <code>dc_demo_workspace_02_catalog</code> and
        <code> lochard_*</code>) are bundle variables (<code>catalog</code>, <code>prefix</code>) and may change; the app and jobs receive
        them as parameters or environment variables. Workspace-specific settings – AI Gateway URL and workspace id, Agent Bricks
        endpoint names, warehouse ids, service principals and the Lakebase project – are configured per bundle target. See
        <code> docs/PROD_MIGRATION.md</code>.
      </div>
      <div className="arch-cols">
        <div><h3>Data in the portal</h3><ul>
          <li>Every number on Leadership Insights, the Market Hub and the Board Pack is queried live from <code>lochard_semantic</code> as the viewer, on the serverless SQL warehouse.</li>
          <li>Periods follow the July–June financial year; comparisons use the prior corresponding period.</li>
          <li>Freshness: finance to the last closed month; HSE, operations and AEMO data daily; maintenance from weekly Maximo snapshots; market intelligence daily at 07:00 AEST.</li></ul></div>
        <div><h3>Embedded dashboards</h3><ul>
          <li>The browser must allow third-party cookies for <code>*.databricks.com</code>.</li>
          <li>A workspace admin must allow-list the portal's domain under Settings → Security → Embed dashboards.</li>
          <li>"Open in Databricks" always works as a fallback.</li></ul></div>
        <div><h3>AI</h3><ul>
          <li>Model services: <code>lochard_llm_premium</code>, <code>_standard</code>, <code>_economy</code>, <code>_open</code> and the routed <code>lochard_assistant</code>, with rate limits and inference tables.</li>
          <li>Commentary drafts use the economy tier; the market brief uses Claude Sonnet; enrichment uses Claude Haiku via <code>ai_query</code>.</li>
          <li>Cost-vs-quality experiment: <code>lochard-ai-cost-quality-experiment</code> (results in <code>lochard_ai.model_cost_experiment</code>).</li></ul></div>
        <div><h3>Operations</h3><ul>
          <li>One bundle (<code>databricks bundle deploy -t prod</code>) deploys schemas, volumes, pipelines, jobs, dashboards, Genie, AI Gateway, Lakebase and the app.</li>
          <li>The portal applies Lakebase migrations at start-up under an advisory lock.</li>
          <li>Agent Bricks (Supervisor and Knowledge Assistant) are created by <code>src/ai/agent_bricks/apply.sh</code>.</li></ul></div>
      </div>
    </section>
  );
}
