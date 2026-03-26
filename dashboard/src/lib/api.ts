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
  RunnerStatus,
  GeneratedApp,
  RevisionResult,
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
  source?: string;
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

/* ------------------------------------------------------------------ */
/*  Pipeline Runner (auto-loop)                                        */
/* ------------------------------------------------------------------ */

const DEFAULT_RUNNER_STATUS: RunnerStatus = {
  running: false,
  current_run_id: null,
  started_at: null,
  cycles: 0,
  apps_generated: 0,
  apps_pushed: 0,
  errors: 0,
};

export async function startPipeline(): Promise<{ status: string }> {
  return (await request<{ status: string }>("/pipeline/start", { method: "POST" })) ?? { status: "error" };
}

export async function stopPipeline(): Promise<{ status: string }> {
  return (await request<{ status: string }>("/pipeline/stop", { method: "POST" })) ?? { status: "error" };
}

export async function fetchRunnerStatus(): Promise<RunnerStatus> {
  return (await request<RunnerStatus>("/pipeline/runner-status")) ?? DEFAULT_RUNNER_STATUS;
}

export async function fetchPipelineLogs(): Promise<{logs: Array<{time: string; message: string; type: string}>}> {
  return (await request<{logs: Array<{time: string; message: string; type: string}>}>("/pipeline/logs")) ?? {logs: []};
}

/* ------------------------------------------------------------------ */
/*  App Revision                                                       */
/* ------------------------------------------------------------------ */

export async function listGeneratedApps(): Promise<{apps: GeneratedApp[]}> {
  return (await request<{apps: GeneratedApp[]}>("/generated-apps")) ?? {apps: []};
}

/* ------------------------------------------------------------------ */
/*  Devices                                                            */
/* ------------------------------------------------------------------ */

export interface DeviceStatus {
  android: boolean;
  ios: boolean;
  ohos: boolean;
  android_device: string | null;
  ios_device: string | null;
  ohos_device: string | null;
}

export async function fetchDeviceStatus(): Promise<DeviceStatus> {
  return (await request<DeviceStatus>("/devices/status")) ?? {
    android: false, ios: false, ohos: false,
    android_device: null, ios_device: null, ohos_device: null,
  };
}

export async function runAppOnDevice(appDir: string, platform: string): Promise<{status: string; message: string}> {
  return (await request<{status: string; message: string}>("/apps/run", {
    method: "POST",
    body: JSON.stringify({ app_dir: appDir, platform }),
  })) ?? { status: "error", message: "请求失败" };
}

/* ------------------------------------------------------------------ */
/*  App Revision                                                       */
/* ------------------------------------------------------------------ */

export async function generateCustomApp(theme: string): Promise<{status: string; message: string}> {
  return (await request<{status: string; message: string}>("/pipeline/generate-custom", {
    method: "POST", body: JSON.stringify({ theme }),
  })) ?? { status: "error", message: "请求失败" };
}

export async function reviseApp(appDir: string, instruction: string): Promise<RevisionResult> {
  return (await request<RevisionResult>("/generated-apps/revise", {
    method: "POST",
    body: JSON.stringify({ app_dir: appDir, instruction: instruction }),
  })) ?? { status: "error", message: "Request failed", changes_made: [] };
}

export async function generateConcurrentApp(theme: string): Promise<{status: string; message: string; run_id?: string; concurrent_count?: number}> {
  return (await request<{status: string; message: string; run_id?: string; concurrent_count?: number}>("/pipeline/generate-concurrent", {
    method: "POST", body: JSON.stringify({ theme }),
  })) ?? { status: "error", message: "Request failed" };
}

/* ------------------------------------------------------------------ */
/*  Settings                                                           */
/* ------------------------------------------------------------------ */

export async function fetchSettings(): Promise<Record<string, unknown>> {
  return (await request<Record<string, unknown>>("/settings")) ?? {};
}

export async function saveSettings(settings: Record<string, unknown>): Promise<MessageResponse | null> {
  return request<MessageResponse>("/settings", {
    method: "POST",
    body: JSON.stringify(settings),
  });
}
