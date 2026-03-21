/* ------------------------------------------------------------------ */
/*  Enums & constants                                                 */
/* ------------------------------------------------------------------ */

export type DemandStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "in_progress"
  | "done";

export type BuildStatus =
  | "queued"
  | "building"
  | "success"
  | "failed"
  | "cancelled";

export type PipelineStage =
  | "idle"
  | "demand_analysis"
  | "code_generation"
  | "build"
  | "test"
  | "deploy"
  | "done"
  | "error";

/* ------------------------------------------------------------------ */
/*  API models                                                        */
/* ------------------------------------------------------------------ */

export interface DashboardSummary {
  total_demands: number;
  pending_demands: number;
  total_apps: number;
  active_builds: number;
  success_rate: number;
  recent_builds: BuildLogOut[];
}

export interface DemandOut {
  id: number;
  title: string;
  status: DemandStatus;
  created_at: string;
  updated_at: string;
}

export interface DemandDetail extends DemandOut {
  description: string;
  requirements: string;
  app_id: number | null;
  rejection_reason: string | null;
}

export interface AppOut {
  id: number;
  name: string;
  status: string;
  demand_id: number;
  created_at: string;
  updated_at: string;
}

export interface AppDetail extends AppOut {
  description: string;
  repo_url: string | null;
  deploy_url: string | null;
  tech_stack: string[];
  builds: BuildLogOut[];
}

export interface BuildLogOut {
  id: number;
  app_id: number;
  app_name: string;
  status: BuildStatus;
  stage: string;
  started_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
  error_message: string | null;
}

export interface PipelineState {
  thread_id: string;
  stage: PipelineStage;
  demand_id: number | null;
  app_id: number | null;
  progress: number;
  message: string;
  started_at: string;
  updated_at: string;
}

export interface StatsPoint {
  date: string;
  builds: number;
  successes: number;
  failures: number;
}

/* ------------------------------------------------------------------ */
/*  API responses                                                     */
/* ------------------------------------------------------------------ */

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ApiError {
  detail: string;
}

/* ------------------------------------------------------------------ */
/*  WebSocket events                                                  */
/* ------------------------------------------------------------------ */

export type WsEventType =
  | "pipeline_update"
  | "build_update"
  | "demand_update"
  | "app_update"
  | "connected";

export interface WsEvent<T = unknown> {
  type: WsEventType;
  timestamp: string;
  data: T;
}

export interface PipelineUpdateData {
  thread_id: string;
  stage: PipelineStage;
  progress: number;
  message: string;
}

export interface BuildUpdateData {
  build_id: number;
  app_id: number;
  status: BuildStatus;
  stage: string;
  message: string;
}

export interface DemandUpdateData {
  demand_id: number;
  status: DemandStatus;
  title: string;
}

export interface AppUpdateData {
  app_id: number;
  name: string;
  status: string;
}
