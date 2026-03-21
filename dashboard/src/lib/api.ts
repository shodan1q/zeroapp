import type {
  DashboardSummary,
  DemandOut,
  DemandDetail,
  AppOut,
  AppDetail,
  BuildLogOut,
  PipelineState,
  StatsPoint,
  PaginatedResponse,
} from "./types";

const API_BASE = "/api";

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

class ApiRequestError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiRequestError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiRequestError(res.status, body.detail ?? res.statusText);
  }

  return res.json() as Promise<T>;
}

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const entries = Object.entries(params).filter(
    (entry): entry is [string, string | number | boolean] => entry[1] !== undefined,
  );
  if (entries.length === 0) return "";
  return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}

/* ------------------------------------------------------------------ */
/*  Dashboard                                                         */
/* ------------------------------------------------------------------ */

export async function fetchDashboard(): Promise<DashboardSummary> {
  return request<DashboardSummary>("/dashboard");
}

/* ------------------------------------------------------------------ */
/*  Demands                                                           */
/* ------------------------------------------------------------------ */

export async function fetchDemands(params?: {
  page?: number;
  page_size?: number;
  status?: string;
}): Promise<PaginatedResponse<DemandOut>> {
  return request<PaginatedResponse<DemandOut>>(`/demands${qs(params ?? {})}`);
}

export async function fetchDemandDetail(id: number): Promise<DemandDetail> {
  return request<DemandDetail>(`/demands/${id}`);
}

export async function approveDemand(id: number): Promise<DemandDetail> {
  return request<DemandDetail>(`/demands/${id}/approve`, { method: "POST" });
}

export async function rejectDemand(
  id: number,
  reason?: string,
): Promise<DemandDetail> {
  return request<DemandDetail>(`/demands/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

/* ------------------------------------------------------------------ */
/*  Apps                                                              */
/* ------------------------------------------------------------------ */

export async function fetchApps(params?: {
  page?: number;
  page_size?: number;
  status?: string;
}): Promise<PaginatedResponse<AppOut>> {
  return request<PaginatedResponse<AppOut>>(`/apps${qs(params ?? {})}`);
}

export async function fetchAppDetail(id: number): Promise<AppDetail> {
  return request<AppDetail>(`/apps/${id}`);
}

export async function rebuildApp(id: number): Promise<{ build_id: number }> {
  return request<{ build_id: number }>(`/apps/${id}/rebuild`, { method: "POST" });
}

/* ------------------------------------------------------------------ */
/*  Builds                                                            */
/* ------------------------------------------------------------------ */

export async function fetchBuilds(params?: {
  limit?: number;
  offset?: number;
  status?: string;
}): Promise<BuildLogOut[]> {
  return request<BuildLogOut[]>(`/builds${qs(params ?? {})}`);
}

/* ------------------------------------------------------------------ */
/*  Stats                                                             */
/* ------------------------------------------------------------------ */

export async function fetchStats(days?: number): Promise<StatsPoint[]> {
  return request<StatsPoint[]>(`/stats${qs({ days })}`);
}

/* ------------------------------------------------------------------ */
/*  Pipeline                                                          */
/* ------------------------------------------------------------------ */

export async function triggerPipeline(): Promise<PipelineState> {
  return request<PipelineState>("/pipeline/trigger", { method: "POST" });
}

export async function fetchPipelineStatus(
  threadId: string,
): Promise<PipelineState> {
  return request<PipelineState>(`/pipeline/${threadId}`);
}
