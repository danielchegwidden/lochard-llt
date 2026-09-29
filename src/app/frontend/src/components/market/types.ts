// Market Intelligence Hub – API client, response types and shared vocabulary.
import { qs, req } from "../../api";

export type Signal = "Opportunity" | "Threat" | "Watch" | "Neutral";
export type Mode = "analyst" | "leader" | "board";

export type Unavailable = { available: false; state: "preparing" | "error"; message: string };

export type WeekInfo = {
  week_start: string; week_end: string; label: string; n_items: number; n_threats: number; n_opportunities: number;
  has_brief: boolean; headline: string | null; brief_generated_at?: string | null;
};
export type WeeksResp = {
  available: true; current_week: string; current_label: string; default_week: string; earliest_week: string;
  latest_brief_week: string | null;
  weeks: WeekInfo[]; horizons: number[]; mode: Mode; can_curate: boolean;
};

export type Cite = {
  item_id: string; title: string; url: string | null; source_name: string | null; published_date: string | null;
  signal: Signal; entity_group: string; importance: number; pinned: boolean; dismissed: boolean;
};
export type Development = {
  title: string; detail: string; signal: Signal; entity_group: string | null; importance: number; item_ids: string[];
  items?: Cite[];
};
export type WatchEntry = { entity: string; note: string; direction: "up" | "down" | "flat" };
export type Action = { action: string; owner_role: string };
export type Brief = {
  week_start: string; week_end: string; label: string; headline: string; summary_md: string; developments: Development[];
  implications: string[]; watchlist: WatchEntry[]; actions: Action[]; sentiment: Record<string, number | null>;
  n_items: number | null; n_sources: number | null; generated_at: string | null; week_to_date: boolean;
};
export type BriefHead = {
  week_start: string; label: string; headline: string; n_items: number | null; n_sources: number | null;
  generated_at: string | null; week_to_date: boolean;
};
export type Theme = {
  title: string; detail: string; signal: Signal; entity_groups: string[];
  trend: "building" | "easing" | "steady" | "new" | "resolved"; weeks: string[];
};
export type Synthesis = {
  headline: string; summary_md: string; themes: Theme[]; watchlist: WatchEntry[]; implications: string[]; actions: Action[];
  generated_at: string; n_briefs: number; stale: boolean; generated_by: string | null;
};

export type SynthesisJob = {
  available: true; status: "ready" | "running" | "error" | "missing"; synthesis?: Synthesis | null; error?: string | null;
};

export type Pt = { x: string; series: string; y: number };
export type GroupStat = { entity_group: string; n: number; avg_sentiment: number | null } & Record<Signal, number>;
export type TopEntity = {
  entity: string; n: number; avg_sentiment: number | null; entity_group: string | null; relationship: string | null;
  max_importance: number;
} & Record<Signal, number>;
export type Counts = { total: number } & Record<Signal, number>;
export type Totals = { n_items: number; n_threats: number; n_opportunities: number };

export type ViewResp = {
  available: true; mode: Mode; can_curate: boolean; curation_available: boolean;
  week: { week_start: string; week_end: string; label: string; is_current: boolean; period_key: string };
  horizon: number; window: { start: string; end: string; label: string; trend_start: string };
  brief: Brief | null; highlights: (Cite & { why_it_matters: string | null; topic: string | null })[];
  briefs: BriefHead[]; synthesis: Synthesis | null; n_briefs: number;
  curation: { pinned: number; dismissed: number; notes: number; overrides: number };
  stats?: {
    n_items: number; n_sources: number; signals: Counts; by_group: GroupStat[]; avg_sentiment: number | null;
    prev: Totals | null; window_weekly: Totals;
  };
  trend?: { weeks: string[]; items_by_group: Pt[]; sentiment: Pt[]; totals: ({ week_start: string } & Totals)[] };
  top_entities?: TopEntity[];
  facets?: Record<"entity_group" | "topic" | "signal" | "source_type", Record<string, number>>;
};

export type Item = {
  item_id: string; published_at: string | null; published_date: string | null; week_start: string; title: string;
  source_name: string | null; source_type: string | null; url: string | null; content_depth: string | null;
  summary: string | null; why_it_matters: string | null; primary_entity: string | null; entities: string[];
  entity_group: string; topic: string | null; signal: Signal; sentiment: number | null; importance: number;
  importance_ai: number; importance_override: number | null; relevance: number | null; pinned: boolean; dismissed: boolean;
  note: string | null; note_by: string | null; note_at: string | null; curated_by?: string | null; curated_at?: string | null;
  excerpt?: string | null; ingested_at?: string | null; archived?: boolean;
  entity_meta?: { entity: string; entity_group: string | null; relationship: string | null }[];
};
export type ItemsResp = {
  available: true; mode: Mode; total: number; offset: number; limit: number; items: Item[]; n_visible: number;
  n_all: number; n_dismissed: number;
};
export type Filters = {
  group?: string; topic?: string; signal?: string; source_type?: string; entity?: string; q?: string;
  sort: "importance" | "newest"; pinned_only?: boolean; show_dismissed?: boolean;
};
export type Annotation = Partial<{ pinned: boolean; dismissed: boolean; note: string | null; importance_override: number | null }>;

type Maybe<T> = T | Unavailable;

export const marketApi = {
  weeks: () => req<Maybe<WeeksResp>>("/api/market/weeks"),
  view: (week: string, horizon: number) => req<Maybe<ViewResp>>(`/api/market/view${qs({ week, horizon })}`),
  items: (week: string, horizon: number, f: Filters, offset = 0, limit = 30) =>
    req<Maybe<ItemsResp>>(`/api/market/items${qs({
      week, horizon, group: f.group, topic: f.topic, signal: f.signal, source_type: f.source_type, entity: f.entity, q: f.q,
      sort: f.sort, pinned_only: f.pinned_only ? "true" : undefined, show_dismissed: f.show_dismissed ? "true" : undefined,
      offset, limit,
    })}`),
  item: (id: string) => req<Maybe<Item>>(`/api/market/items/${encodeURIComponent(id)}`),
  annotate: (id: string, week_start: string, a: Annotation) =>
    req<any>(`/api/market/items/${encodeURIComponent(id)}/annotation`, { method: "PUT", body: JSON.stringify({ week_start, ...a }) }),
  // Generation runs in the background: POST starts it (or returns the current one), GET reports progress.
  synthesis: (week: string, horizon: number, force = false) =>
    req<Maybe<SynthesisJob>>("/api/market/synthesis", { method: "POST", body: JSON.stringify({ week, horizon, force }) }),
  synthesisStatus: (week: string, horizon: number) => req<Maybe<SynthesisJob>>(`/api/market/synthesis${qs({ week, horizon })}`),
};

// ---------------------------------------------------------------------------------------------- vocabulary
export const GROUPS = ["Lochard", "Customer", "Competitor", "Upstream supplier", "Regulator & market body",
  "Government & policy", "Industry & market"];
// Fixed categorical order (validated for colour-vision deficiency); colour follows the group, never its rank.
export const GROUP_COLOR: Record<string, string> = {
  "Lochard": "#A3194E", "Customer": "#F47525", "Competitor": "#52B2E5", "Upstream supplier": "#8E4737",
  "Regulator & market body": "#E0A800", "Government & policy": "#6D5BA8", "Industry & market": "#1E9E8A",
};
export const TOPICS = ["Gas storage", "Supply & demand", "Prices & contracts", "Policy & regulation", "Projects & investment",
  "Corporate & M&A", "Operations & safety", "Energy transition"];
export const SIGNALS: Signal[] = ["Opportunity", "Threat", "Watch", "Neutral"];
export const SIGNAL_ICON: Record<Signal, string> = { Opportunity: "▲", Threat: "▼", Watch: "◆", Neutral: "●" };
export const SOURCE_LABEL: Record<string, string> = {
  news: "News", web_research: "Web research", asx_announcement: "ASX announcement", company_release: "Company release",
  regulator_release: "Regulator release",
};
export const DEPTH_LABEL: Record<string, string> = {
  full_text: "Full text", summary: "Summary", headline: "Headline and snippet only",
};
// "1 week" rather than "This week": the window ends at the selected week, which is not always the current one.
export const HORIZONS: [number, string][] = [[1, "1 week"], [4, "4 weeks"], [13, "13 weeks"], [26, "26 weeks"]];

// ---------------------------------------------------------------------------------------------- dates
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const ymd = (s: string) => { const [y, m, d] = s.slice(0, 10).split("-").map(Number); return new Date(Date.UTC(y, m - 1, d)); };
export const iso = (d: Date) => d.toISOString().slice(0, 10);
export const addWeeks = (s: string, n: number) => { const d = ymd(s); d.setUTCDate(d.getUTCDate() + 7 * n); return iso(d); };
export const mondayOf = (s: string) => { const d = ymd(s); d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7)); return iso(d); };
export const dayLabel = (s?: string | null, year = true) => {
  if (!s) return "";
  const d = ymd(s);
  return `${d.getUTCDate()} ${MON[d.getUTCMonth()]}${year ? ` ${d.getUTCFullYear()}` : ""}`;
};
export const weekLabel = (s: string) => `Week of ${dayLabel(s)}`;
export const when = (ts?: string | null) => {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("en-AU", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Australia/Melbourne" });
};
export const sentimentWord = (v: number | null | undefined) =>
  v == null ? "–" : v >= 0.35 ? "Positive" : v >= 0.1 ? "Leaning positive" : v > -0.1 ? "Balanced" : v > -0.35 ? "Leaning negative" : "Negative";
// Sentiment is stored −1…+1; the page shows it as a −100…+100 score (clearer when weekly averages sit near zero).
export const score = (v: number | null | undefined) => (v == null ? null : Math.round(v * 100));
export const fmtSent = (v: number | null | undefined) => {
  const s = score(v);
  return s == null ? "–" : s === 0 ? "0" : `${s > 0 ? "+" : "−"}${Math.abs(s)}`;
};
