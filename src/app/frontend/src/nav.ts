// In-app navigation and role vocabulary shared by every page.
export type PageKey = "insights" | "market" | "boardpack" | "agents" | "dashboards" | "governance" | "about";
export type NavParams = { dashboard?: string; tab?: string; section?: string; [k: string]: string | undefined };

/** Switch page from anywhere, e.g. navigate("dashboards", { dashboard: "finance" }) for a drill-down. */
export const navigate = (page: PageKey, params: NavParams = {}) =>
  window.dispatchEvent(new CustomEvent("lochard:navigate", { detail: { page, params } }));

export const ROLE_LABEL: Record<string, string> = {
  LLT: "Leader", KPI_OWNER: "Manager / Analyst", BOARD: "Board director", ADMIN: "Administrator", OBSERVER: "Observer",
};
export const ROLE_BLURB: Record<string, string> = {
  LLT: "Reviews and approves commentary; sees the curated view.",
  KPI_OWNER: "Owns the numbers; drafts commentary and curates market signals.",
  BOARD: "Sees approved commentary and the finalised board pack.",
  ADMIN: "Full access, including configuration.",
  OBSERVER: "Read-only.",
};
