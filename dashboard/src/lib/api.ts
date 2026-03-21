import type {
  DashboardSummary,
  DemandOut,
  DemandDetail,
  AppOut,
  AppDetail,
  BuildLogOut,
  PipelineState,
  PipelineStatusResponse,
  StatsResponse,
  MessageResponse,
  PaginatedResponse,
  BuildListResponse,
} from "./types";

const API_BASE = "/api";

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

async function request<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...init?.headers },
      ...init,
    });
    if (!res.ok) {
      console.warn(`API ${path}: ${res.status} ${res.statusText}`);
      return null;
    }
    return res.json() as Promise<T>;
  } catch (err) {
    console.warn(`API ${path}: connection failed`, err);
    return null;
  }
}

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const entries = Object.entries(params).filter(
    (entry): entry is [string, string | number | boolean] => entry[1] !== undefined,
  );
  if (entries.length === 0) return "";
  return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}

/* ------------------------------------------------------------------ */
/*  Default values                                                     */
/* ------------------------------------------------------------------ */

const DEFAULT_DASHBOARD: DashboardSummary = {
  total_apps: 0,
  live_apps: 0,
  reviewing_apps: 0,
  developing_apps: 0,
  total_demands: 0,
  pending_demands: 0,
  approved_today: 0,
  rejected_today: 0,
  builds_today: 0,
};

/* ------------------------------------------------------------------ */
/*  Dashboard                                                         */
/* ------------------------------------------------------------------ */

export async function fetchDashboard(): Promise<DashboardSummary> {
  const res = await request<DashboardSummary>("/dashboard");
  return res ?? DEFAULT_DASHBOARD;
}

/* ------------------------------------------------------------------ */
/*  Demands                                                           */
/* ------------------------------------------------------------------ */

export async function fetchDemands(params?: {
  page?: number;
  page_size?: number;
  status?: string;
}): Promise<PaginatedResponse<DemandOut>> {
  const res = await request<PaginatedResponse<DemandOut>>(`/demands${qs(params ?? {})}`);
  return res ?? { items: [], total: 0, page: 1, page_size: 20 };
}

export async function fetchDemandDetail(id: number): Promise<DemandDetail | null> {
  return request<DemandDetail>(`/demands/${id}`);
}

export async function approveDemand(id: number): Promise<MessageResponse | null> {
  return request<MessageResponse>(`/demands/${id}/approve`, { method: "POST" });
}

export async function rejectDemand(id: number): Promise<MessageResponse | null> {
  return request<MessageResponse>(`/demands/${id}/reject`, { method: "POST" });
}

/* ------------------------------------------------------------------ */
/*  Apps                                                              */
/* ------------------------------------------------------------------ */

export async function fetchApps(params?: {
  page?: number;
  page_size?: number;
  status?: string;
}): Promise<PaginatedResponse<AppOut>> {
  const res = await request<PaginatedResponse<AppOut>>(`/apps${qs(params ?? {})}`);
  return res ?? { items: [], total: 0, page: 1, page_size: 20 };
}

export async function fetchAppDetail(id: number): Promise<AppDetail | null> {
  return request<AppDetail>(`/apps/${id}`);
}

export async function rebuildApp(id: number): Promise<MessageResponse | null> {
  return request<MessageResponse>(`/apps/${id}/rebuild`, { method: "POST" });
}

/* ------------------------------------------------------------------ */
/*  Builds                                                            */
/* ------------------------------------------------------------------ */

export async function fetchBuilds(params?: {
  limit?: number;
}): Promise<BuildListResponse> {
  const res = await request<BuildListResponse>(`/builds${qs(params ?? {})}`);
  return res ?? { items: [], total: 0 };
}

/* ------------------------------------------------------------------ */
/*  Stats                                                             */
/* ------------------------------------------------------------------ */

export async function fetchStats(days?: number): Promise<StatsResponse> {
  const res = await request<StatsResponse>(`/stats${qs({ days })}`);
  return res ?? { apps_per_day: [], total_revenue_usd: 0, ratings_distribution: [] };
}

/* ------------------------------------------------------------------ */
/*  Pipeline                                                          */
/* ------------------------------------------------------------------ */

export async function triggerPipeline(): Promise<PipelineState | null> {
  return request<PipelineState>("/pipeline/trigger", { method: "POST" });
}

export async function fetchPipelineStatus(
  threadId: string,
): Promise<PipelineStatusResponse | null> {
  return request<PipelineStatusResponse>(`/pipeline/status/${threadId}`);
}
