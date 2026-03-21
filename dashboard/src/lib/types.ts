/* ------------------------------------------------------------------ */
/*  Enums & constants                                                 */
/* ------------------------------------------------------------------ */

export type DemandStatus =
  | "pending"
  | "evaluating"
  | "approved"
  | "rejected"
  | "in_progress"
  | "done";

export type BuildStatus =
  | "pending"
  | "running"
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
/*  API models  (aligned with backend schemas.py)                      */
/* ------------------------------------------------------------------ */

export interface DashboardSummary {
  total_apps: number;
  live_apps: number;
  reviewing_apps: number;
  developing_apps: number;
  total_demands: number;
  pending_demands: number;
  approved_today: number;
  rejected_today: number;
  builds_today: number;
}

export interface DemandOut {
  demand_id: number;
  title: string;
  description: string;
  source: string | null;
  source_url: string | null;
  category: string | null;
  status: string;
  overall_score: number | null;
  trend_score: number | null;
  created_at: string;
  updated_at: string;
}

export interface DemandDetail extends DemandOut {
  target_users: string | null;
  core_features: string | null;
  monetization: string | null;
  complexity: string | null;
  competition_score: number | null;
  feasibility_score: number | null;
  monetization_score: number | null;
}

export interface AppOut {
  app_id: number;
  app_name: string;
  package_name: string;
  status: string;
  category: string | null;
  google_play_url: string | null;
  total_downloads: number;
  revenue_usd: number;
  rating: number | null;
  created_at: string;
  updated_at: string;
}

export interface AppDetail extends AppOut {
  demand_id: number;
  description: string;
  flutter_version: string | null;
  project_path: string | null;
  build_attempts: number;
  fix_iterations: number;
  code_gen_cost_usd: number;
  published_at: string | null;
  build_logs: BuildLogOut[];
}

export interface BuildLogOut {
  build_id: number;
  step: string;
  status: string;
  output: string | null;
  error_message: string | null;
  attempt: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface PipelineState {
  run_id: number;
  status: string;
  message: string;
}

export interface PipelineStatusResponse {
  thread_id: string;
  status: string;
  stage?: string;
  message?: string;
  values?: Record<string, unknown>;
}

export interface StatsResponse {
  apps_per_day: DailyStat[];
  total_revenue_usd: number;
  ratings_distribution: RatingBucket[];
}

export interface DailyStat {
  date: string;
  apps_created: number;
  revenue_usd: number;
}

export interface RatingBucket {
  rating_range: string;
  count: number;
}

export interface MessageResponse {
  message: string;
}

/* ------------------------------------------------------------------ */
/*  API responses                                                     */
/* ------------------------------------------------------------------ */

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface BuildListResponse {
  items: BuildLogOut[];
  total: number;
}

export interface ApiError {
  detail: string;
}

export interface GeneratedApp {
  id: string;
  name: string;
  path: string;
  created_at: string;
}

export interface RevisionResult {
  status: string;
  message?: string;
  changes_made: string[];
  analyze_ok?: boolean;
  analyze_output?: string;
  instruction?: string;
}

export interface RunnerStatus {
  running: boolean;
  current_run_id: string | null;
  started_at: string | null;
  cycles: number;
  apps_generated: number;
  apps_pushed: number;
  errors: number;
  stage_timings?: Record<string, number>;
}

/* ------------------------------------------------------------------ */
/*  WebSocket events                                                  */
/* ------------------------------------------------------------------ */

export type WsEventType =
  | "pipeline_update"
  | "build_update"
  | "demand_update"
  | "app_update"
  | "stage_change"
  | "error"
  | "metrics_update"
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
