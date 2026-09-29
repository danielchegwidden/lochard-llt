// Board pack API client and types (backend: server/routes/boardpack.py).
import { qs, req } from "../../api";
import type { Pt, XType, YFmt } from "../Chart";

export type Tone = "good" | "bad" | null;
export type Delta = { text: string; tone: Tone } | null;
export type MetricPart = { v: number | null; t: string; p: string | null; d: Delta; vs: string; label: string };
export type Metric = {
  label: string; kind: string; note: string | null; point: boolean; tone: Tone; m: MetricPart; y: MetricPart | null;
};
export type ChartSpec = {
  title: string; sub: string; kind: "line" | "bar"; x: XType; y: YFmt; rows: Pt[]; colors: Record<string, string>;
  dashed: string[]; zero: boolean; area: boolean;
};
export type PeriodLabels = {
  code: string; fy_code: string; label: string; state: string; state_label: string; month_start: string; period_end: string;
  board_meeting: string | null; anchor: string; month: string; month_pcp: string; month_long: string; fy: string; fytd: string;
  fytd_pcp: string; fytd_long: string; fytd_pcp_long: string; insights_key: string; month_end_label: string;
};
export type SlideStatus = "NOT_STARTED" | "IN_DRAFT" | "READY";
export type SlideMeta = {
  key: string; no: number; title: string; short: string; kind: "live" | "owner"; owner: string; default_owner: string;
  commentary_title: string; prompt: string; required: boolean; included: boolean; status: SlideStatus | null;
  commentary_status: string | null; updated_at: string | null;
};
export type Readiness = { ready: number; total: number; excluded: number; not_ready: { key: string; title: string; status: SlideStatus }[] };
export type Version = {
  board_pack_id: number; version: number; status: "FINAL" | "SENT" | "SUPERSEDED"; slides_included: string[];
  slides_ready: number; slides_total: number; not_ready: { key: string; title: string; status: SlideStatus }[];
  override_reason: string | null; finalised_by: string; finalised_name: string | null; finalised_role: string | null;
  finalised_at: string; sent_by: string | null; sent_name: string | null; sent_at: string | null; superseded_at: string | null;
  pdf_bytes: number; pdf_pages: number | null;
};
export type Perms = {
  can_curate: boolean; can_finalise: boolean; can_mark_sent: boolean; can_download: boolean; sees_workflow: boolean;
  can_write: boolean; can_review: boolean;
};
export type Activity = { at: string; actor: string; what: string };
export type PackMeta = {
  period: PeriodLabels; role: string; perms: Perms; slides: SlideMeta[]; readiness: Readiness | null; versions: Version[];
  latest: Version | null; activity: Activity[];
  /** Board / observers only: approved commentary per slide. */
  approved: Record<string, FrozenCommentary> | null;
};
export type SlidesData = Record<string, any>;
export type PackData = { period: PeriodLabels; generated_at: string; slides: SlidesData };
export type FrozenCommentary = {
  body: string; author_name: string | null; author_role: string | null; reviewer_name: string | null;
  reviewed_at: string | null; ai_assisted: boolean; version: number;
} | null;
export type Snapshot = {
  version: number; period: PeriodLabels; data_as_at: string; finalised: { by: string; name: string; role: string; at: string };
  override_reason: string | null; readiness: Readiness; slides: (SlideMeta & { commentary: FrozenCommentary })[];
  data: SlidesData; fingerprint?: string;
};
export type BoardPeriod = {
  period_code: string; fy_code: string; label: string; month_start: string; state: string; has_updates: boolean;
  version: number | null; pack_status: Version["status"] | null; finalised_at: string | null; sent_at: string | null;
};

const base = (code: string) => `/api/boardpack/${encodeURIComponent(code)}`;

export const bp = {
  periods: () => req<{ default: string | null; periods: BoardPeriod[] }>("/api/boardpack/periods"),
  meta: (code: string) => req<PackMeta>(base(code)),
  data: (code: string, refresh = false) => req<PackData>(`${base(code)}/data${qs({ refresh: refresh ? 1 : undefined })}`),
  setSlide: (code: string, key: string, body: { included?: boolean; owner?: string }) =>
    req<any>(`${base(code)}/slides/${key}`, { method: "PUT", body: JSON.stringify(body) }),
  finalise: (code: string, override_reason?: string) =>
    req<{ version: Version; versions: Version[] }>(`${base(code)}/finalise`, { method: "POST", body: JSON.stringify({ override_reason }) }),
  version: (code: string, v: number) => req<{ version: Version; snapshot: Snapshot }>(`${base(code)}/versions/${v}`),
  markSent: (code: string, v: number) =>
    req<{ version: Version; versions: Version[] }>(`${base(code)}/versions/${v}/sent`, { method: "POST" }),
  pdfUrl: (code: string, v: number) => `${base(code)}/versions/${v}/pdf`,
};

export const STATUS_TEXT: Record<SlideStatus, string> = { NOT_STARTED: "Not started", IN_DRAFT: "In draft", READY: "Ready" };
export const VERSION_TEXT: Record<Version["status"], string> = { FINAL: "Final", SENT: "Sent to the Board", SUPERSEDED: "Superseded" };

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function day(iso?: string | null, withTime = false): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10);
  const s = `${d.getDate()} ${MON[d.getMonth()]} ${d.getFullYear()}`;
  return withTime ? `${s}, ${d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}` : s;
}
