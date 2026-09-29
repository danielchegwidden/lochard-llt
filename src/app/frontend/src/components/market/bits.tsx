import { GROUP_COLOR, Signal, SIGNAL_ICON } from "./types";

export function SignalChip({ s, small }: { s: Signal; small?: boolean }) {
  return <span className={`mi-sig mi-sig-${s}${small ? " mi-sm" : ""}`} title={`Signal for Lochard: ${s}`}>
    <span aria-hidden>{SIGNAL_ICON[s]}</span>{s}</span>;
}

export function GroupTag({ g }: { g?: string | null }) {
  if (!g) return null;
  return <span className="mi-group"><i style={{ background: GROUP_COLOR[g] || "#B9AFAC" }} />{g}</span>;
}

export function Importance({ v, ai, override }: { v: number; ai?: number; override?: number | null }) {
  const title = override ? `Importance ${v}/5 – set by the analyst (agent rated ${ai}/5)` : `Importance ${v}/5`;
  return (
    <span className={`mi-imp${override ? " mi-imp-ovr" : ""}`} title={title} aria-label={title}>
      {[1, 2, 3, 4, 5].map((k) => <i key={k} className={k <= v ? "on" : ""} />)}
      {override ? <span className="mi-imp-note">analyst</span> : null}
    </span>
  );
}

export function Direction({ d }: { d: "up" | "down" | "flat" }) {
  const [icon, label] = d === "up" ? ["↑", "Rising"] : d === "down" ? ["↓", "Falling"] : ["→", "Steady"];
  return <span className={`mi-dir mi-dir-${d}`} title={label}>{icon}<span className="mi-sr">{label}</span></span>;
}

export function AgentBadge({ label = "Market Intelligence Analyst" }: { label?: string }) {
  return <span className="mi-agent"><span aria-hidden>✦</span>{label}</span>;
}
