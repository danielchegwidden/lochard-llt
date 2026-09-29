import { useEffect, useState } from "react";
import { api, Me } from "../api";
import PageHead from "../components/PageHead";
import { ROLE_BLURB, ROLE_LABEL } from "../nav";

// Plain-language names for the data personas (the access profiles the data platform enforces).
const PERSONA: Record<string, [string, string]> = {
  platform_admin: ["Platform owner", "Everything, nothing hidden"],
  board: ["Board", "All teams; people's names hidden; legal and employee detail restricted; no privileged investigations"],
  leadership: ["Leadership team", "All teams and ledger detail; people's names hidden"],
  finance: ["Finance", "All finance detail, including supplier bank details"],
  budget_holder: ["Budget holder", "Finance figures for one team only"],
  hse: ["HSE", "People's names visible; privileged investigations hidden"],
  hse_investigator: ["HSE investigator", "Privileged investigations visible"],
  maintenance: ["Maintenance planner", "Maintenance and operations data"],
  operations: ["Control room / operations", "Operations and market data"],
};
const TEAMS = ["Maintenance", "Asset Management", "Operations", "Major Projects", "HSE", "Legal"];
const ROLES = ["LLT", "KPI_OWNER", "BOARD", "ADMIN"];
const personaName = (p: string) => PERSONA[p]?.[0] ?? p;

export default function GovernancePage({ me, onPersonaChange }: { me: Me; onPersonaChange: () => void }) {
  const [p, setP] = useState<any>(null);
  const [chk, setChk] = useState<any>(null);
  const [team, setTeam] = useState("Maintenance");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const check = () => { setChk(null); api.govCheck().then(setChk).catch(() => setChk({ failed: true })); };
  const load = () => { api.persona().then(setP).catch((e) => setErr(String(e))); check(); };
  useEffect(load, []);
  const switchTo = async (persona: string) => {
    setBusy(true); setErr(null);
    try { await api.setPersona(persona, persona === "budget_holder" ? team : undefined); load(); onPersonaChange(); }
    catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  const personas: string[] = p?.personas ?? me.personas ?? [];
  const current = personas.length ? personas.map(personaName).join(", ") : "none assigned";
  const team_ = p?.team ?? me.persona_team;
  const rows = (x: any, f: (r: any) => string) => x?.error ? "not available" : (x?.rows || []).map(f).filter(Boolean).join(" · ") || "nothing visible";

  return (
    <div>
      <PageHead title="AI & Governance" me={me}
                sub="What decides what you can do in the portal, what data you can see, and how AI is used." />
      {err && <div className="err" style={{ marginBottom: 10 }}>{err}</div>}

      <div className="grid g2" style={{ marginBottom: 14 }}>
        <div className="card">
          <div className="note" style={{ textTransform: "uppercase", letterSpacing: ".4px", fontWeight: 700 }}>Portal role · what you can do</div>
          <h3 style={{ margin: "4px 0 6px", color: "var(--crimson)" }}>{ROLE_LABEL[me.role] || me.role}</h3>
          <p style={{ margin: "0 0 8px" }}>Your role decides which actions the portal offers you: who writes commentary, who approves it and who
            sees the finished board pack.</p>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.5 }}>
            {ROLES.map((r) => <li key={r}><b>{ROLE_LABEL[r]}</b> – {ROLE_BLURB[r]}</li>)}
          </ul>
          {me.can_view_as && <p className="note" style={{ marginBottom: 0 }}>As an administrator you can preview the portal as another role with
            <b> Viewing as</b> in the navigation. It changes what the portal lets you do, not the data you can see.</p>}
        </div>
        <div className="card">
          <div className="note" style={{ textTransform: "uppercase", letterSpacing: ".4px", fontWeight: 700 }}>Data persona · what you can see</div>
          <h3 style={{ margin: "4px 0 6px", color: "var(--crimson)" }}>{current}{team_ ? ` (${team_})` : ""}</h3>
          <p style={{ margin: "0 0 8px" }}>Your persona decides which rows and columns of data you can see – for example whether people's
            names are shown, or only your own team's budget. The data platform enforces it for every figure, dashboard and AI answer,
            wherever you look, so the portal can never show you more than you are allowed to see.</p>
          <p className="note" style={{ margin: 0 }}>Signed in as {me.email}.</p>
        </div>
      </div>

      <div className="grid g2">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Try another data persona</h3>
          {me.can_switch_persona ? (<>
            <p className="note">For demonstrations: switch your own persona, then open a dashboard or ask a question to see names hidden and
              rows filtered. It takes effect within a few seconds.</p>
            <div className="grid" style={{ gap: 6 }}>
              {(p?.available || []).map((x: string) => (
                <button key={x} disabled={busy} className={personas.includes(x) ? "crimson" : ""} style={{ textAlign: "left" }} onClick={() => switchTo(x)}>
                  <b>{personaName(x)}</b> – <span className="note" style={{ color: "inherit" }}>{PERSONA[x]?.[1] ?? ""}</span></button>))}
              {!p && <span className="note">Loading…</span>}
            </div>
            <label className="note" style={{ display: "inline-block", marginTop: 8 }}>Budget holder team&nbsp;
              <select value={team} onChange={(e) => setTeam(e.target.value)}>{TEAMS.map((t) => <option key={t}>{t}</option>)}</select></label>
          </>) : <p className="note">Only platform administrators can switch persona.</p>}
        </div>

        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ margin: 0 }}>What you can see right now</h3>
            <button className="linkish" onClick={check}>Check again</button>
          </div>
          {!chk ? <p className="note">Checking…</p> : chk.failed ? <p className="note">The live check is unavailable right now.</p> : (
            <div style={{ fontSize: 13.5 }}>
              <p><b>People's names in HSE actions:</b> {rows(chk.actionee_sample, (r) => r.actionee)}</p>
              <p><b>Finance teams you can see:</b> {chk.finance_teams_visible?.error ? "not available" : chk.finance_teams_visible?.rows?.[0]?.n ?? "–"}</p>
              <p><b>Legal ledger descriptions:</b> {rows(chk.legal_description_sample, (r) => r.description)}</p>
            </div>
          )}
          <h3>Responsible AI in this portal</h3>
          <ul style={{ fontSize: 13.5, lineHeight: 1.5, paddingLeft: 18 }}>
            <li><b>Your access, not more.</b> AI answers and drafts run as you, so they only use data you are allowed to see.</li>
            <li><b>People decide.</b> AI drafts are labelled; a manager edits and submits them and a leader approves. KPI statuses and
              board scores are always entered by people.</li>
            <li><b>Show the working.</b> Answers cite their sources and the query behind each number.</li>
            <li><b>Controlled and recorded.</b> AI use goes through one gateway with usage limits and guardrails, and every change is logged.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
