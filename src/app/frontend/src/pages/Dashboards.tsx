import { useEffect, useState } from "react";
import { api } from "../api";
import PageHead from "../components/PageHead";
import { navigate } from "../nav";

// Where a drill-down from Leadership Insights came from (App passes the dashboard key as `initial`).
const FROM: Record<string, string> = {
  finance: "Finance", hse: "Health, safety & environment", maintenance: "Maintenance", ops: "Iona operations & market",
  market: "Market Intelligence",
};

export default function DashboardsPage({ initial }: { initial?: string }) {
  const [rows, setRows] = useState<any[] | null>(null);
  const [active, setActive] = useState<string>(initial || "finance");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api.dashboards().then(setRows).catch((e) => { setErr(String(e)); setRows([]); }); }, []);
  useEffect(() => { if (initial) setActive(initial); }, [initial]);
  const d = rows?.find((r) => r.key === active) ?? rows?.[0];
  const from = initial && FROM[initial];

  return (
    <div>
      <PageHead title="Dashboards" sub="The detailed Finance, HSE, Maintenance, Operations and Market Intelligence dashboards – showing the data you have access to." />
      {from && (
        <div className="crumb" style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, margin: "-6px 0 12px", color: "var(--muted)" }}>
          <button className="linkish" style={{ fontSize: 13 }} onClick={() => navigate("insights")}>← Leadership Insights</button>
          <span>›</span><span>Opened from the <b style={{ color: "var(--grey)" }}>{from}</b> card</span>
        </div>
      )}
      {err && <div className="err">{err}</div>}
      <div className="tabs">
        {(rows || []).map((r) => (
          <button key={r.key} className={d?.key === r.key ? "active" : ""} onClick={() => setActive(r.key)}>{r.title}</button>))}
        <div style={{ flex: 1 }} />
        {d?.open_url && <a href={d.open_url} target="_blank" rel="noreferrer"><button>Open in Databricks ↗</button></a>}
      </div>
      {rows === null ? <div className="card">Loading dashboards…</div>
        : d?.embed_url ? <iframe key={d.key} className="dash" src={d.embed_url} title={d.title} />
        : <div className="card">{d ? `${d.title} has not been published yet.` : "No dashboards are available."}</div>}
      {d?.open_url && (
        <p className="note">Trouble viewing? <a href={d.open_url} target="_blank" rel="noreferrer">Open in Databricks ↗</a></p>)}
    </div>
  );
}
