export type Me = {
  email: string; name: string; role: string; real_role: string; view_as: string | null; can_view_as: boolean;
  personas: string[]; persona_team: string | null; workspace_admin: boolean; can_switch_persona: boolean; obo: boolean;
};

// Admins can preview the portal as another role; the choice travels with every API call.
const VIEW_KEY = "viewAs";
export const getViewAs = (): string => { try { return localStorage.getItem(VIEW_KEY) || ""; } catch { return ""; } };
export const setViewAs = (role: string) => { try { role ? localStorage.setItem(VIEW_KEY, role) : localStorage.removeItem(VIEW_KEY); } catch { /* private mode */ } };
const viewHeader = (): Record<string, string> => (getViewAs() ? { "x-lochard-view-as": getViewAs() } : {});
export type Deliverable = { seq: number; text: string };
export type Kpi = {
  kpi_id: string; code: string; name: string; owner_initials: string; owner_role: string; weight_pct: number;
  preamble: string | null; pillar: string; status: string | null; owner_score: number | null; commentary: string | null;
  ai_draft_accepted: boolean | null; avg_board_score: number | null; n_scores: number; my_score: number | null;
  n_comments: number; deliverables: Deliverable[];
};
export type Scorecard = {
  fy: string; period: { period_code: string; label: string; state: string; fy_code: string };
  pillars: { name: string; pillar_no: number; kpis: Kpi[] }[];
  summary: { status_index_pct?: number; weighted_board_score_pct?: number; kpis_at_risk?: number };
  trend: { period_code: string; status_index_pct: number; weighted_board_score_pct: number | null }[];
  weights_total: number; footnote: string;
};
export type Evidence = { label: string; value: number | null; kind: string; target: string | null; error?: string };

export async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { ...init, headers: { "content-type": "application/json", ...viewHeader(), ...(init?.headers || {}) } });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* ignore */ }
    throw new Error(`${r.status}: ${detail}`);
  }
  return r.json() as Promise<T>;
}

export const api = {
  me: () => req<Me>("/api/me"),
  fiscalYears: () => req<{ fiscal_years: any[]; periods: any[] }>("/api/fiscal-years"),
  scorecard: (fy: string, period?: string) => req<Scorecard>(`/api/scorecard/${fy}${period ? `?period=${period}` : ""}`),
  kpi: (id: string, period: string) => req<any>(`/api/kpi/${id}?period=${period}`),
  evidence: (id: string) => req<{ evidence: Evidence[] }>(`/api/kpi/${id}/evidence`),
  setStatus: (id: string, body: any) => req<any>(`/api/kpi/${id}/status`, { method: "POST", body: JSON.stringify(body) }),
  score: (id: string, body: any) => req<any>(`/api/kpi/${id}/score`, { method: "POST", body: JSON.stringify(body) }),
  comment: (id: string, body: any) => req<any>(`/api/kpi/${id}/comments`, { method: "POST", body: JSON.stringify(body) }),
  resolveComment: (cid: number, resolved: boolean) =>
    req<any>(`/api/comments/${cid}`, { method: "PATCH", body: JSON.stringify({ resolved }) }),
  aiDraft: (id: string, body: any) => req<any>(`/api/kpi/${id}/ai-draft`, { method: "POST", body: JSON.stringify(body) }),
  advance: (period: string, to_state: string, note?: string) =>
    req<any>(`/api/period/${period}/advance`, { method: "POST", body: JSON.stringify({ to_state, note }) }),
  periodHistory: (period: string) => req<any>(`/api/period/${period}/history`),
  insightPeriods: () => req<InsightPeriods>("/api/insights/periods"),
  summary: (grain?: string, anchor?: string) => req<any>(`/api/insights/summary${qs({ grain, anchor })}`),
  trends: (grain?: string, anchor?: string) => req<any>(`/api/insights/trends${qs({ grain, anchor })}`),
  commentary: (scope: string, period_key: string, subject?: string) =>
    req<CommentaryList>(`/api/commentary${qs({ scope, period_key, subject })}`),
  saveCommentary: (body: { scope: string; subject: string; period_key: string; body: string; ai_assisted?: boolean; ai_model?: string }) =>
    req<Commentary>("/api/commentary", { method: "PUT", body: JSON.stringify(body) }),
  submitCommentary: (id: number) => req<Commentary>(`/api/commentary/${id}/submit`, { method: "POST" }),
  reviewCommentary: (id: number, decision: "APPROVE" | "RETURN", note?: string) =>
    req<Commentary>(`/api/commentary/${id}/review`, { method: "POST", body: JSON.stringify({ decision, note }) }),
  draftCommentary: (scope: string, subject: string, period_key: string, hint?: string) =>
    req<{ draft: string; model: string; facts: string }>("/api/commentary/ai-draft", { method: "POST", body: JSON.stringify({ scope, subject, period_key, hint }) }),
  spaces: () => req<Record<string, { space_id: string; title: string }>>("/api/ask/spaces"),
  ask: (question: string, space?: string, conversation_id?: string) =>
    req<any>("/api/ask", { method: "POST", body: JSON.stringify({ question, space, conversation_id }) }),
  feedback: (body: any) => req<any>("/api/ask/feedback", { method: "POST", body: JSON.stringify(body) }),
  dashboards: () => req<any[]>("/api/dashboards"),
  persona: () => req<any>("/api/admin/persona"),
  setPersona: (persona: string, team?: string) =>
    req<any>("/api/admin/persona", { method: "POST", body: JSON.stringify({ persona, team }) }),
  govCheck: () => req<any>("/api/admin/governance-check"),
  agents: () => req<AgentCatalog>("/api/agents"),
  agentRuns: () => req<{ runs: any[] }>("/api/agents/runs"),
  rateRun: (id: number, positive: boolean) =>
    req<any>(`/api/agents/runs/${id}/rating`, { method: "POST", body: JSON.stringify({ positive }) }),
  routingLab: (question: string, compare = true) =>
    req<any>("/api/agents/lab", { method: "POST", body: JSON.stringify({ question, compare }) }),
};

export function qs(params: Record<string, string | number | undefined | null>): string {
  const p = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return p.length ? `?${p.join("&")}` : "";
}

export type InsightPeriods = {
  default: { grain: string; anchor: string }; latest_closed: string; min: string; max: string; months: string[];
  grains: { key: string; label: string }[];
};
export type PeriodInfo = {
  grain: string; anchor: string; key: string; month_key: string; label: string; start: string; end: string; months: number; fy: string;
  compare: { label: string; start: string; end: string };
};
export type Commentary = {
  commentary_id: number; scope: string; subject: string; period_key: string; body: string;
  status: "DRAFT" | "SUBMITTED" | "APPROVED" | "RETURNED"; author_email: string; author_name: string | null; author_role: string | null;
  ai_assisted: boolean; ai_model: string | null; submitted_at: string | null; reviewer_name: string | null; review_note: string | null;
  reviewed_at: string | null; updated_at: string; version: number;
};
export type CommentaryList = { items: Record<string, Commentary>; can_write: boolean; can_review: boolean; role: string };

export type AgentInfo = {
  key: string; name: string; kind: string; product: string; endpoint?: string; state?: string; summary: string;
  tools: string[]; identity: string; examples: string[];
};
export type AgentCatalog = { agents: AgentInfo[]; stats: Record<string, { runs: number; avg_ms: number; up: number; down: number }>; workspace: string };
export type AgentEvent = { type: "start" | "step" | "delta" | "done" | "error"; [k: string]: any };

/** POST + server-sent events: calls onEvent for every `data:` frame until the stream closes. */
export async function streamAgent(body: any, onEvent: (e: AgentEvent) => void, signal?: AbortSignal) {
  const r = await fetch("/api/agents/stream", { method: "POST", headers: { "content-type": "application/json", ...viewHeader() },
                                                 body: JSON.stringify(body), signal });
  if (!r.ok || !r.body) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* ignore */ }
    throw new Error(`${r.status}: ${detail}`);
  }
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let k;
    while ((k = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, k); buf = buf.slice(k + 2);
      const data = frame.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trim()).join("");
      if (data) { try { onEvent(JSON.parse(data)); } catch { /* partial frame */ } }
    }
  }
}

export const STATUS_LABEL: Record<string, string> = {
  ON_TRACK: "On Track", AT_RISK: "At Risk", OFF_TRACK: "Off Track", COMPLETE: "Complete",
};

export function fmt(v: number | null | undefined, kind: string): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  if (kind === "money") {
    const a = Math.abs(v);
    const s = a >= 1e9 ? `${(a / 1e9).toFixed(2)}B` : a >= 1e6 ? `${(a / 1e6).toFixed(1)}M` : a >= 1e3 ? `${(a / 1e3).toFixed(0)}K` : a.toFixed(0);
    return `${v < 0 ? "-" : ""}$${s}`;
  }
  if (kind === "pct") return `${(v * 100).toFixed(1)}%`;
  if (kind === "count") return Math.round(v).toLocaleString();
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
