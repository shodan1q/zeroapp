"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import {
  Layers,
  Rocket,
  Code2,
  Lightbulb,
  Hammer,
  Clock,
  Activity,
  RefreshCw,
  AlertTriangle,
  Sparkles,
  Send,
  Play,
  Square,
  Loader2,
  Search,
  CheckCircle2,
  XCircle,
  Brain,
  TestTube,
  GitBranch,
} from "lucide-react";
import {
  fetchDashboard,
  fetchDemands,
  fetchBuilds,
  fetchRunnerStatus,
  fetchPipelineLogs,
  generateCustomApp,
  startPipeline,
  stopPipeline,
  fetchPipelineStatus,
  triggerPipeline,
} from "@/lib/api";
import type {
  DashboardSummary,
  DemandOut,
  BuildLogOut,
  RunnerStatus,
  PipelineStatusResponse,
} from "@/lib/types";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useI18n } from "@/lib/i18n";

/* ------------------------------------------------------------------ */
/*  Skeleton helpers                                                   */
/* ------------------------------------------------------------------ */

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <div className="mb-3 h-4 w-24 rounded bg-gray-200" />
      <div className="h-8 w-16 rounded bg-gray-200" />
    </div>
  );
}

function SkeletonRow() {
  return (
    <tr>
      {Array.from({ length: 4 }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-4 w-full animate-pulse rounded bg-gray-200" />
        </td>
      ))}
    </tr>
  );
}

/* ------------------------------------------------------------------ */
/*  Status badge                                                      */
/* ------------------------------------------------------------------ */

function StatusBadge({ status, t }: { status: string; t: (key: string) => string }) {
  const map: Record<string, string> = {
    pending: "bg-gray-100 text-gray-600",
    evaluating: "bg-yellow-50 text-yellow-700",
    approved: "bg-emerald-50 text-emerald-700",
    rejected: "bg-red-50 text-red-700",
    in_progress: "bg-purple-50 text-purple-700",
    done: "bg-blue-50 text-blue-700",
    running: "bg-blue-50 text-blue-700",
    success: "bg-emerald-50 text-emerald-700",
    failed: "bg-red-50 text-red-700",
    cancelled: "bg-gray-100 text-gray-500",
  };
  const labelKey: Record<string, string> = {
    pending: "status.pending",
    evaluating: "status.evaluating",
    approved: "status.approved",
    rejected: "status.rejected",
    in_progress: "status.in_progress",
    done: "status.done",
    running: "status.running",
    success: "status.success",
    failed: "status.failed",
    cancelled: "status.cancelled",
  };
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${map[status] ?? "bg-gray-100 text-gray-600"}`}
    >
      {labelKey[status] ? t(labelKey[status]) : status}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Pipeline stage helpers (merged from pipeline page)                 */
/* ------------------------------------------------------------------ */

interface StageConfig {
  key: string;
  labelKey: string;
  icon: React.ComponentType<{ className?: string }>;
}

const STAGES: StageConfig[] = [
  { key: "idle", labelKey: "stage.idle", icon: Clock },
  { key: "demand_analysis", labelKey: "stage.demand_analysis", icon: Brain },
  { key: "code_generation", labelKey: "stage.code_generation", icon: Code2 },
  { key: "build", labelKey: "stage.build", icon: Hammer },
  { key: "test", labelKey: "stage.test", icon: TestTube },
  { key: "deploy", labelKey: "stage.deploy", icon: Rocket },
  { key: "done", labelKey: "stage.done", icon: CheckCircle2 },
  { key: "error", labelKey: "stage.error", icon: XCircle },
];

function stageStatusStyle(
  stageKey: string,
  currentStage: string,
): { dot: string; card: string; text: string } {
  const stageOrder = [
    "idle",
    "demand_analysis",
    "code_generation",
    "build",
    "test",
    "deploy",
    "done",
  ];
  const currentIdx = stageOrder.indexOf(currentStage);
  const stageIdx = stageOrder.indexOf(stageKey);

  if (currentStage === "error") {
    return { dot: "bg-red-500", card: "border-red-200 bg-red-50", text: "text-red-700" };
  }
  if (stageKey === "error") {
    return { dot: "bg-gray-200", card: "border-gray-200 bg-white", text: "text-gray-400" };
  }
  if (stageKey === currentStage) {
    return { dot: "bg-blue-500 animate-pulse", card: "border-blue-200 bg-blue-50", text: "text-blue-700" };
  }
  if (stageIdx < currentIdx && currentIdx >= 0) {
    return { dot: "bg-emerald-500", card: "border-emerald-200 bg-emerald-50", text: "text-emerald-700" };
  }
  return { dot: "bg-gray-200", card: "border-gray-200 bg-white", text: "text-gray-400" };
}

function SkeletonStageCard() {
  return (
    <div className="animate-pulse rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-3 h-5 w-20 rounded bg-gray-200" />
      <div className="space-y-2">
        <div className="h-3 w-full rounded bg-gray-200" />
        <div className="h-3 w-2/3 rounded bg-gray-200" />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main page                                                         */
/* ------------------------------------------------------------------ */

export default function OverviewPage() {
  const { t } = useI18n();

  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [demands, setDemands] = useState<DemandOut[]>([]);
  const [builds, setBuilds] = useState<BuildLogOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [apiConnected, setApiConnected] = useState(true);
  const [runnerStatus, setRunnerStatus] = useState<RunnerStatus>({
    running: false,
    current_run_id: null,
    started_at: null,
    cycles: 0,
    apps_generated: 0,
    apps_pushed: 0,
    errors: 0,
  });
  const [pipelineTask, setPipelineTask] = useState("--");

  // Custom generation state
  const [customTheme, setCustomTheme] = useState("");
  const [customLoading, setCustomLoading] = useState(false);
  const [customResult, setCustomResult] = useState<{
    status: string;
    message: string;
  } | null>(null);

  // Pipeline control state (merged from pipeline page)
  const [runnerLoading, setRunnerLoading] = useState(false);
  const [pipelineLogs, setPipelineLogs] = useState<
    { time: string; message: string; type: string }[]
  >([]);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatusResponse | null>(null);
  const [threadId, setThreadId] = useState("");
  const [searchId, setSearchId] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [searchError, setSearchError] = useState("");

  const logRef = useRef<HTMLDivElement>(null);
  const { connected, lastEvent } = useWebSocket();

  /* ---------- Fetch data ---------------------------------------- */

  const loadData = useCallback(async () => {
    try {
      const [dash, demandsRes, buildsRes] = await Promise.all([
        fetchDashboard(),
        fetchDemands({ page: 1, page_size: 5 }),
        fetchBuilds({ limit: 5 }),
      ]);
      setSummary(dash);
      setDemands(demandsRes.items);
      setBuilds(buildsRes.items);
      const isDefault =
        dash.total_apps === 0 &&
        dash.total_demands === 0 &&
        demandsRes.items.length === 0 &&
        buildsRes.items.length === 0;
      setApiConnected(!isDefault || dash.total_apps !== undefined);
    } catch (err) {
      console.error("Failed to load dashboard data", err);
      setApiConnected(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const timer = setInterval(loadData, 30_000);
    return () => clearInterval(timer);
  }, [loadData]);

  /* ---------- Runner status polling ------------------------------ */

  const loadRunnerStatus = useCallback(async () => {
    const status = await fetchRunnerStatus();
    setRunnerStatus(status);
  }, []);

  /* ---------- Load pipeline logs --------------------------------- */

  const loadLogs = useCallback(async () => {
    const res = await fetchPipelineLogs();
    setPipelineLogs(
      res.logs.map((l) => ({
        time: new Date(l.time).toLocaleTimeString("zh-CN"),
        message: l.message,
        type: l.type,
      })),
    );
  }, []);

  useEffect(() => {
    loadRunnerStatus();
    loadLogs();
  }, [loadRunnerStatus, loadLogs]);

  useEffect(() => {
    const interval = runnerStatus.running ? 5_000 : 15_000;
    const timer = setInterval(() => {
      loadRunnerStatus();
      loadLogs();
    }, interval);
    return () => clearInterval(timer);
  }, [loadRunnerStatus, loadLogs, runnerStatus.running]);

  /* ---------- WebSocket updates --------------------------------- */

  useEffect(() => {
    if (!lastEvent) return;

    if (lastEvent.type === "stage_change") {
      const d = lastEvent.data as {
        stage: string;
        status: string;
        demand_id?: string;
        detail?: { message?: string };
      };
      if (d.detail?.message) {
        setPipelineTask(d.detail.message);
      }
      loadLogs();
      loadRunnerStatus();
    }

    if (lastEvent.type === "pipeline_update") {
      const d = lastEvent.data as {
        thread_id?: string;
        stage?: string;
        stats?: { message?: string };
        message?: string;
      };
      const m = d.stats?.message ?? d.message;
      if (m) {
        setPipelineTask(m);
      }
      if (d.thread_id && (!threadId || d.thread_id === threadId)) {
        setThreadId(d.thread_id);
        setPipelineStatus((prev) =>
          prev
            ? {
                ...prev,
                stage: d.stage ?? prev.stage,
                message: d.message ?? prev.message,
              }
            : {
                thread_id: d.thread_id!,
                status: "found",
                stage: d.stage ?? "idle",
                message: d.message,
              },
        );
      }
      loadLogs();
    }

    if (
      lastEvent.type === "build_update" ||
      lastEvent.type === "demand_update" ||
      lastEvent.type === "app_update"
    ) {
      loadData();
    }
  }, [lastEvent, loadData, loadLogs, loadRunnerStatus, threadId]);

  // Auto-scroll pipeline logs
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [pipelineLogs]);

  /* ---------- Custom generation handler -------------------------- */

  const handleCustomGenerate = useCallback(async () => {
    if (!customTheme.trim() || runnerStatus.running) return;
    setCustomLoading(true);
    setCustomResult(null);
    try {
      const result = await generateCustomApp(customTheme.trim());
      setCustomResult(result);
      if (result.status === "started") {
        setCustomTheme("");
        loadRunnerStatus();
      }
    } catch {
      setCustomResult({ status: "error", message: "Request failed" });
    } finally {
      setCustomLoading(false);
    }
  }, [customTheme, runnerStatus.running, loadRunnerStatus]);

  /* ---------- Pipeline control handlers -------------------------- */

  const handleStartPipeline = async () => {
    setRunnerLoading(true);
    await startPipeline();
    await loadRunnerStatus();
    setRunnerLoading(false);
  };

  const handleStopPipeline = async () => {
    setRunnerLoading(true);
    await stopPipeline();
    await loadRunnerStatus();
    setRunnerLoading(false);
  };

  const handleTrigger = async () => {
    setTriggering(true);
    setSearchError("");
    try {
      const res = await triggerPipeline();
      if (res) {
        setPipelineStatus({
          thread_id: String(res.run_id),
          status: res.status,
          message: res.message,
          stage: "idle",
        });
        setThreadId(String(res.run_id));
        setSearchId(String(res.run_id));
      }
    } catch {
      setSearchError("Trigger failed");
    } finally {
      setTriggering(false);
    }
  };

  const handleSearch = async () => {
    if (!searchId.trim()) return;
    setSearchLoading(true);
    setSearchError("");
    try {
      const res = await fetchPipelineStatus(searchId.trim());
      if (res) {
        setPipelineStatus(res);
        setThreadId(res.thread_id);
      } else {
        setSearchError("Not found");
        setPipelineStatus(null);
      }
    } catch {
      setSearchError("Not found");
      setPipelineStatus(null);
    } finally {
      setSearchLoading(false);
    }
  };

  const currentStage = pipelineStatus?.stage ?? "idle";

  /* ---------- Stats cards --------------------------------------- */

  const statsCards = [
    {
      labelKey: "overview.total_apps",
      value: summary?.total_apps ?? 0,
      icon: Layers,
      color: "text-blue-500",
      bg: "bg-blue-50",
    },
    {
      labelKey: "overview.live_apps",
      value: summary?.live_apps ?? 0,
      icon: Rocket,
      color: "text-emerald-500",
      bg: "bg-emerald-50",
    },
    {
      labelKey: "overview.developing",
      value: summary?.developing_apps ?? 0,
      icon: Code2,
      color: "text-purple-500",
      bg: "bg-purple-50",
    },
    {
      labelKey: "overview.total_demands",
      value: summary?.total_demands ?? 0,
      icon: Lightbulb,
      color: "text-amber-500",
      bg: "bg-amber-50",
    },
    {
      labelKey: "overview.today_builds",
      value: summary?.builds_today ?? 0,
      icon: Hammer,
      color: "text-indigo-500",
      bg: "bg-indigo-50",
    },
    {
      labelKey: "overview.pending",
      value: summary?.pending_demands ?? 0,
      icon: Clock,
      color: "text-gray-500",
      bg: "bg-gray-100",
    },
  ];

  /* ---------- Render -------------------------------------------- */

  return (
    <div className="space-y-6">
      {/* Page title */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">{t("overview.title")}</h1>
        <button
          onClick={loadData}
          className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-600 shadow-sm transition-colors hover:bg-gray-50"
        >
          <RefreshCw className="h-4 w-4" />
          {t("overview.refresh")}
        </button>
      </div>

      {/* Backend not connected warning */}
      {!loading && !apiConnected && (
        <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="h-5 w-5 flex-shrink-0 text-amber-500" />
          <span>{t("overview.backend_warning")}</span>
        </div>
      )}

      {/* A) Stats cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {loading
          ? Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)
          : statsCards.map((card) => {
              const Icon = card.icon;
              return (
                <div
                  key={card.labelKey}
                  className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`flex h-10 w-10 items-center justify-center rounded-lg ${card.bg}`}
                    >
                      <Icon className={`h-5 w-5 ${card.color}`} />
                    </div>
                    <div>
                      <p className="text-2xl font-semibold text-gray-900">
                        {card.value}
                      </p>
                      <p className="text-xs text-gray-500">{t(card.labelKey)}</p>
                    </div>
                  </div>
                </div>
              );
            })}
      </div>

      {/* B) Compact pipeline status indicator */}
      <div className="rounded-lg border border-gray-200 bg-white px-5 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            {runnerStatus.running ? (
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
              </span>
            ) : (
              <span className="inline-flex h-2.5 w-2.5 rounded-full bg-gray-300" />
            )}
            <span className="text-sm font-medium text-gray-700">
              {runnerStatus.running ? t("overview.pipeline_running") : t("overview.pipeline_stopped")}
            </span>
          </div>
          <span className="text-gray-300">|</span>
          <span className="truncate text-sm text-gray-500">
            {t("overview.current_task")}: {runnerStatus.current_run_id ?? pipelineTask}
          </span>
          <span className="ml-auto shrink-0 text-xs text-gray-400">
            {t("overview.cycles")} {runnerStatus.cycles} / {t("overview.generated")} {runnerStatus.apps_generated} / {t("overview.pushed")} {runnerStatus.apps_pushed}
          </span>
        </div>
      </div>

      {/* C) Custom generation card */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <Sparkles className="h-5 w-5 text-indigo-500" />
          <h2 className="text-base font-semibold text-gray-900">{t("overview.custom_gen")}</h2>
        </div>
        <p className="mb-4 text-sm text-gray-500">
          {t("overview.custom_gen_desc")}
        </p>
        <div className="flex gap-3">
          <input
            type="text"
            value={customTheme}
            onChange={(e) => setCustomTheme(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCustomGenerate()}
            disabled={runnerStatus.running || customLoading}
            placeholder={t("overview.custom_gen_placeholder")}
            className="flex-1 rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-700 placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-50 disabled:text-gray-400"
          />
          <button
            onClick={handleCustomGenerate}
            disabled={!customTheme.trim() || runnerStatus.running || customLoading}
            className="flex shrink-0 items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
            {customLoading ? t("overview.submitting") : t("overview.start_gen")}
          </button>
        </div>
        {runnerStatus.running && (
          <p className="mt-2 text-xs text-amber-600">
            {t("overview.pipeline_busy")}
          </p>
        )}
        {customResult && (
          <p
            className={`mt-2 text-sm ${customResult.status === "started" ? "text-emerald-600" : "text-red-600"}`}
          >
            {customResult.message}
          </p>
        )}
      </div>

      {/* D) Pipeline control panel (merged from pipeline page) */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              {runnerStatus.running ? (
                <span className="relative flex h-3 w-3">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-3 w-3 rounded-full bg-emerald-500" />
                </span>
              ) : (
                <span className="inline-flex h-3 w-3 rounded-full bg-gray-300" />
              )}
              <h2 className="text-lg font-semibold text-gray-900">
                {t("overview.pipeline_control")}
              </h2>
            </div>
            {runnerStatus.started_at && (
              <span className="text-sm text-gray-500">
                {t("overview.started_at") + " " + new Date(runnerStatus.started_at).toLocaleString("zh-CN")}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleTrigger}
              disabled={triggering}
              className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 disabled:opacity-50"
            >
              {triggering ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {t("overview.trigger_single")}
            </button>
            {runnerStatus.running ? (
              <button
                onClick={handleStopPipeline}
                disabled={runnerLoading}
                className="flex items-center gap-2 rounded-lg bg-red-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-red-700 disabled:opacity-50"
              >
                <Square className="h-4 w-4" />
                {runnerLoading ? t("overview.processing") : t("overview.stop_pipeline")}
              </button>
            ) : (
              <button
                onClick={handleStartPipeline}
                disabled={runnerLoading}
                className="flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-emerald-700 disabled:opacity-50"
              >
                <Play className="h-4 w-4" />
                {runnerLoading ? t("overview.processing") : t("overview.start_pipeline")}
              </button>
            )}
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 border-t border-gray-100 pt-4 sm:grid-cols-5">
          <div>
            <p className="text-xs text-gray-500">{t("overview.cycles")}</p>
            <p className="text-xl font-semibold text-gray-900">{runnerStatus.cycles}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">{t("overview.generated_apps")}</p>
            <p className="text-xl font-semibold text-gray-900">{runnerStatus.apps_generated}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">{t("overview.pushed_github")}</p>
            <p className="text-xl font-semibold text-gray-900">{runnerStatus.apps_pushed}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">{t("overview.error_count")}</p>
            <p className={`text-xl font-semibold ${runnerStatus.errors > 0 ? "text-red-600" : "text-gray-900"}`}>
              {runnerStatus.errors}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">{t("overview.current_task")}</p>
            <p className="text-sm font-medium text-gray-700">
              {runnerStatus.current_run_id ?? "--"}
            </p>
          </div>
        </div>
      </div>

      {/* E) Thread search */}
      <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <label className="mb-2 block text-sm font-medium text-gray-700">
          {t("overview.query_pipeline")}
        </label>
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder={t("overview.query_placeholder")}
              value={searchId}
              onChange={(e) => setSearchId(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              className="w-full rounded-lg border border-gray-200 bg-white py-2 pl-9 pr-3 text-sm text-gray-700 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={searchLoading}
            className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 disabled:opacity-50"
          >
            {searchLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              t("overview.query")
            )}
          </button>
        </div>
        {searchError && <p className="mt-2 text-sm text-red-500">{searchError}</p>}
      </div>

      {/* F) Pipeline stage visualization */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-5 text-sm font-semibold text-gray-700">
          {t("overview.pipeline_stages")}
          {pipelineStatus && (
            <span className="ml-3 text-xs font-normal text-gray-400">
              Thread: {pipelineStatus.thread_id}
            </span>
          )}
        </h2>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {pipelineStatus === null && !searchLoading
            ? STAGES.filter((s) => s.key !== "error").map((s) => (
                <SkeletonStageCard key={s.key} />
              ))
            : STAGES.filter((s) => s.key !== "error" || currentStage === "error").map(
                (stage) => {
                  const style = stageStatusStyle(stage.key, currentStage);
                  const Icon = stage.icon;
                  const isActive = stage.key === currentStage;
                  return (
                    <div
                      key={stage.key}
                      className={`rounded-lg border p-4 shadow-sm transition-all ${style.card}`}
                    >
                      <div className="mb-3 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div className={`h-2.5 w-2.5 rounded-full ${style.dot}`} />
                          <span className={`text-sm font-semibold ${style.text}`}>
                            {t(stage.labelKey)}
                          </span>
                        </div>
                        <Icon className={`h-5 w-5 ${style.text}`} />
                      </div>
                      <div className="space-y-1.5 text-xs text-gray-500">
                        <p>
                          {isActive
                            ? t("stage.running")
                            : stageStatusStyle(stage.key, currentStage).dot.includes("emerald")
                              ? t("stage.completed")
                              : t("stage.waiting")}
                        </p>
                        {isActive && pipelineStatus?.message && (
                          <p className="truncate">{pipelineStatus.message}</p>
                        )}
                      </div>
                    </div>
                  );
                },
              )}
        </div>

        {pipelineStatus && (
          <div className="mt-4 flex flex-wrap gap-6 border-t border-gray-100 pt-4 text-sm text-gray-500">
            <span>
              Thread ID:{" "}
              <span className="font-medium text-gray-700">{pipelineStatus.thread_id}</span>
            </span>
            <span>
              Status:{" "}
              <span className="font-medium text-gray-700">{pipelineStatus.status}</span>
            </span>
          </div>
        )}
      </div>

      {/* G) Pipeline logs */}
      <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="flex items-center gap-2 border-b border-gray-100 px-5 py-4">
          <Activity className="h-4 w-4 text-gray-400" />
          <h2 className="text-sm font-semibold text-gray-700">{t("overview.pipeline_logs")}</h2>
          <button
            onClick={loadLogs}
            className="ml-auto flex items-center gap-1.5 text-xs text-gray-400 transition-colors hover:text-gray-600"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {t("overview.refresh")}
          </button>
          {connected && (
            <span className="flex items-center gap-1.5 text-xs text-emerald-600">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
              {t("overview.realtime")}
            </span>
          )}
        </div>
        <div
          ref={logRef}
          className="max-h-72 overflow-y-auto px-5 py-3 font-mono text-xs leading-relaxed text-gray-600"
        >
          {pipelineLogs.length === 0 ? (
            <p className="py-6 text-center text-gray-400">
              {t("overview.no_logs")}
            </p>
          ) : (
            pipelineLogs.map((entry, i) => {
              const badgeColor: Record<string, string> = {
                stage_change: "bg-blue-100 text-blue-700",
                error: "bg-red-100 text-red-700",
                pipeline_update: "bg-emerald-100 text-emerald-700",
                build_update: "bg-amber-100 text-amber-700",
                info: "bg-gray-100 text-gray-600",
              };
              const badge = entry.type
                ? badgeColor[entry.type] ?? "bg-gray-100 text-gray-600"
                : "bg-gray-100 text-gray-600";
              return (
                <div key={i} className="py-0.5 flex items-start gap-1.5">
                  <span className="text-gray-400 shrink-0">{entry.time}</span>
                  <span
                    className={`inline-block rounded px-1 py-0 text-[10px] font-medium shrink-0 ${badge}`}
                  >
                    {entry.type}
                  </span>
                  <span className={entry.type === "error" ? "text-red-600" : ""}>{entry.message}</span>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* H) Two-column tables */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Recent demands */}
        <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-100 px-5 py-4">
            <h2 className="text-sm font-semibold text-gray-700">{t("overview.recent_demands")}</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                  <th className="px-4 py-3 font-medium">{t("demands.id")}</th>
                  <th className="px-4 py-3 font-medium">{t("demands.name")}</th>
                  <th className="px-4 py-3 font-medium">{t("demands.status")}</th>
                  <th className="px-4 py-3 font-medium">{t("demands.time")}</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <SkeletonRow key={i} />
                  ))
                ) : demands.length === 0 ? (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-8 text-center text-gray-400"
                    >
                      {t("overview.no_data")}
                    </td>
                  </tr>
                ) : (
                  demands.map((d) => (
                    <tr
                      key={d.demand_id}
                      className="border-b border-gray-50 transition-colors hover:bg-gray-50"
                    >
                      <td className="px-4 py-3 text-gray-500">#{d.demand_id}</td>
                      <td className="max-w-[200px] truncate px-4 py-3 font-medium text-gray-900">
                        {d.title}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={d.status} t={t} />
                      </td>
                      <td className="px-4 py-3 text-gray-500">
                        {new Date(d.created_at).toLocaleDateString("zh-CN")}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent builds */}
        <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-100 px-5 py-4">
            <h2 className="text-sm font-semibold text-gray-700">{t("overview.recent_builds")}</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                  <th className="px-4 py-3 font-medium">{t("demands.id")}</th>
                  <th className="px-4 py-3 font-medium">{t("builds.step")}</th>
                  <th className="px-4 py-3 font-medium">{t("demands.status")}</th>
                  <th className="px-4 py-3 font-medium">{t("demands.time")}</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <SkeletonRow key={i} />
                  ))
                ) : builds.length === 0 ? (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-8 text-center text-gray-400"
                    >
                      {t("overview.no_data")}
                    </td>
                  </tr>
                ) : (
                  builds.map((b) => (
                    <tr
                      key={b.build_id}
                      className="border-b border-gray-50 transition-colors hover:bg-gray-50"
                    >
                      <td className="px-4 py-3 text-gray-500">#{b.build_id}</td>
                      <td className="max-w-[200px] truncate px-4 py-3 font-medium text-gray-900">
                        {b.step}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={b.status} t={t} />
                      </td>
                      <td className="px-4 py-3 text-gray-500">
                        {new Date(b.created_at).toLocaleDateString("zh-CN")}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
