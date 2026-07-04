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
    <div className="glass animate-pulse p-5">
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 shrink-0 rounded-xl bg-gray-200 dark:bg-[#161d45]" />
        <div className="flex-1">
          <div className="mb-2 h-6 w-12 rounded bg-gray-200 dark:bg-[#161d45]" />
          <div className="h-3 w-16 rounded bg-gray-200 dark:bg-[#161d45]" />
        </div>
      </div>
    </div>
  );
}

function SkeletonRow() {
  return (
    <tr>
      {Array.from({ length: 4 }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-4 w-full animate-pulse rounded bg-gray-200 dark:bg-[#161d45]" />
        </td>
      ))}
    </tr>
  );
}

/* ------------------------------------------------------------------ */
/*  Status badge                                                      */
/* ------------------------------------------------------------------ */

function StatusBadge({ status, t }: { status: string; t: (key: string) => string }) {
  const neutral =
    "inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-2.5 py-0.5 text-xs font-medium text-gray-600 dark:border-[#1e2756] dark:bg-[#161d45] dark:text-slate-300";
  const map: Record<string, string> = {
    pending: neutral,
    evaluating: "badge-warning",
    approved: "badge-success",
    rejected: "badge-error",
    in_progress:
      "inline-flex items-center rounded-full border border-purple-200 bg-purple-50 px-2.5 py-0.5 text-xs font-medium text-purple-700 dark:border-purple-500/35 dark:bg-purple-900/30 dark:text-purple-300",
    done: "badge-info",
    running: "badge-info",
    success: "badge-success",
    failed: "badge-error",
    cancelled: neutral,
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
    <span className={map[status] ?? neutral}>
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
    return { dot: "bg-red-500", card: "border-red-200 dark:border-red-800 bg-red-50/80 dark:bg-red-900/20", text: "text-red-700 dark:text-red-400" };
  }
  if (stageKey === "error") {
    return { dot: "bg-gray-200 dark:bg-gray-600", card: "border-gray-200 dark:border-[#1e2756] bg-white/60 dark:bg-[#111738]/60", text: "text-gray-400" };
  }
  if (stageKey === currentStage) {
    return { dot: "bg-blue-500 animate-pulse", card: "border-blue-200 dark:border-blue-800 bg-blue-50/80 dark:bg-blue-900/20", text: "text-blue-700 dark:text-blue-400" };
  }
  if (stageIdx < currentIdx && currentIdx >= 0) {
    return { dot: "bg-emerald-500", card: "border-emerald-200 dark:border-emerald-800 bg-emerald-50/80 dark:bg-emerald-900/20", text: "text-emerald-700 dark:text-emerald-400" };
  }
  return { dot: "bg-gray-200 dark:bg-gray-600", card: "border-gray-200 dark:border-[#1e2756] bg-white/60 dark:bg-[#111738]/60", text: "text-gray-400" };
}

function SkeletonStageCard() {
  return (
    <div className="animate-pulse rounded-xl border border-gray-200 dark:border-[#1e2756] bg-white/60 dark:bg-[#111738]/60 p-4">
      <div className="mb-3 h-5 w-20 rounded bg-gray-200 dark:bg-[#161d45]" />
      <div className="space-y-2">
        <div className="h-3 w-full rounded bg-gray-200 dark:bg-[#161d45]" />
        <div className="h-3 w-2/3 rounded bg-gray-200 dark:bg-[#161d45]" />
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
  const [liveStage, setLiveStage] = useState<string>("idle");
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
    if (!status.running && liveStage !== "idle" && liveStage !== "done") {
      setLiveStage("idle");
    }
  }, [liveStage]);

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
      // Map runner stages to card stages
      const stageMap: Record<string, string> = {
        crawl: "demand_analysis",
        process: "demand_analysis",
        evaluate: "demand_analysis",
        decide: "demand_analysis",
        generate: "code_generation",
        build: "build",
        assets: "build",
        publish: "deploy",
        info: liveStage, // keep current for info events
      };
      const mapped = stageMap[d.stage] ?? liveStage;
      if (d.status === "completed" && d.stage === "publish") {
        setLiveStage("done");
      } else if (d.stage !== "info") {
        setLiveStage(mapped);
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

  const currentStage = runnerStatus.running
    ? liveStage
    : (pipelineStatus?.stage ?? "idle");

  /* ---------- Stats cards --------------------------------------- */

  const statsCards = [
    {
      labelKey: "overview.total_apps",
      value: summary?.total_apps ?? 0,
      icon: Layers,
      chip: "icon-chip-blue",
    },
    {
      labelKey: "overview.live_apps",
      value: summary?.live_apps ?? 0,
      icon: Rocket,
      chip: "icon-chip-green",
    },
    {
      labelKey: "overview.developing",
      value: summary?.developing_apps ?? 0,
      icon: Code2,
      chip: "icon-chip-purple",
    },
    {
      labelKey: "overview.total_demands",
      value: summary?.total_demands ?? 0,
      icon: Lightbulb,
      chip: "icon-chip-amber",
    },
    {
      labelKey: "overview.today_builds",
      value: summary?.builds_today ?? 0,
      icon: Hammer,
      chip: "icon-chip-rose",
    },
    {
      labelKey: "overview.pending",
      value: summary?.pending_demands ?? 0,
      icon: Clock,
      chip: "icon-chip-slate",
    },
  ];

  /* ---------- Render -------------------------------------------- */

  return (
    <div className="relative space-y-6">
      <div className="relative z-10 space-y-6">
      {/* Page title */}
      <div className="fade-in-up flex items-start justify-between gap-4">
        <div>
          <h1 className="page-title">{t("overview.title")}</h1>
          <p className="page-subtitle">{t("login.subtitle")}</p>
        </div>
        <button onClick={loadData} className="btn btn-secondary btn-sm shrink-0">
          <RefreshCw className="h-3.5 w-3.5" />
          {t("overview.refresh")}
        </button>
      </div>

      {/* Backend not connected warning */}
      {!loading && !apiConnected && (
        <div className="fade-in-up flex items-center gap-3 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50/80 dark:bg-amber-900/20 px-4 py-3 text-sm text-amber-800 dark:text-amber-300">
          <AlertTriangle className="h-5 w-5 flex-shrink-0 text-amber-500" />
          <span>{t("overview.backend_warning")}</span>
        </div>
      )}

      {/* A) Stats cards */}
      <div className="fade-in-up grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {loading
          ? Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)
          : statsCards.map((card) => {
              const Icon = card.icon;
              return (
                <div key={card.labelKey} className="glass glass-hover p-5">
                  <div className="flex items-center gap-3">
                    <div className={`icon-chip ${card.chip}`}>
                      <Icon className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-2xl font-bold tabular-nums text-gray-900 dark:text-slate-100">
                        {card.value}
                      </p>
                      <p className="truncate text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-slate-400">
                        {t(card.labelKey)}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
      </div>

      {/* B) Compact pipeline status indicator */}
      <div className="glass fade-in-up px-5 py-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            {runnerStatus.running ? (
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-500" />
              </span>
            ) : (
              <span className="inline-flex h-2.5 w-2.5 rounded-full bg-gray-300 dark:bg-gray-600" />
            )}
            <span className="text-sm font-medium text-gray-700 dark:text-slate-300">
              {runnerStatus.running ? t("overview.pipeline_running") : t("overview.pipeline_stopped")}
            </span>
          </div>
          <span className="text-gray-300 dark:text-gray-600">|</span>
          <span className="truncate text-sm text-gray-500 dark:text-slate-400">
            {t("overview.current_task")}: {runnerStatus.current_run_id ?? pipelineTask}
          </span>
          <span className="ml-auto shrink-0 text-xs tabular-nums text-gray-400 dark:text-slate-500">
            {t("overview.cycles")} {runnerStatus.cycles} / {t("overview.generated")} {runnerStatus.apps_generated} / {t("overview.pushed")} {runnerStatus.apps_pushed}
          </span>
        </div>
      </div>

      {/* C) Custom generation card */}
      <div className="glass fade-in-up p-5 ring-1 ring-indigo-500/20 dark:ring-indigo-400/20">
        <div className="mb-4 flex items-start gap-3">
          <div className="icon-chip icon-chip-purple">
            <Sparkles className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h2 className="section-title">{t("overview.custom_gen")}</h2>
            <p className="mt-0.5 text-sm text-gray-500 dark:text-slate-400">
              {t("overview.custom_gen_desc")}
            </p>
          </div>
        </div>
        <div className="flex gap-3">
          <input
            type="text"
            value={customTheme}
            onChange={(e) => setCustomTheme(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCustomGenerate()}
            disabled={runnerStatus.running || customLoading}
            placeholder={t("overview.custom_gen_placeholder")}
            className="input flex-1 disabled:cursor-not-allowed disabled:opacity-60"
          />
          <button
            onClick={handleCustomGenerate}
            disabled={!customTheme.trim() || runnerStatus.running || customLoading}
            className="btn btn-primary shrink-0"
          >
            <Send className="h-4 w-4" />
            {customLoading ? t("overview.submitting") : t("overview.start_gen")}
          </button>
        </div>
        {runnerStatus.running && (
          <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
            {t("overview.pipeline_busy")}
          </p>
        )}
        {customResult && (
          <p
            className={`mt-2 text-sm ${customResult.status === "started" ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}
          >
            {customResult.message}
          </p>
        )}
      </div>

      {/* D) Pipeline control panel (merged from pipeline page) */}
      <div className="glass fade-in-up p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2.5">
              {runnerStatus.running ? (
                <span className="relative flex h-3 w-3">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-3 w-3 animate-pulse rounded-full bg-emerald-500" />
                </span>
              ) : (
                <span className="inline-flex h-3 w-3 rounded-full bg-gray-300 dark:bg-gray-600" />
              )}
              <h2 className="section-title">{t("overview.pipeline_control")}</h2>
            </div>
            {runnerStatus.started_at && (
              <span className="text-sm text-gray-500 dark:text-slate-400">
                {t("overview.started_at") + " " + new Date(runnerStatus.started_at).toLocaleString("zh-CN")}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleTrigger}
              disabled={triggering}
              className="btn btn-secondary"
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
                className="btn btn-danger"
              >
                <Square className="h-4 w-4" />
                {runnerLoading ? t("overview.processing") : t("overview.stop_pipeline")}
              </button>
            ) : (
              <button
                onClick={handleStartPipeline}
                disabled={runnerLoading}
                className="btn btn-primary"
              >
                <Play className="h-4 w-4" />
                {runnerLoading ? t("overview.processing") : t("overview.start_pipeline")}
              </button>
            )}
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 border-t border-gray-100 dark:border-[#1e2756] pt-4 sm:grid-cols-5">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-slate-400">{t("overview.cycles")}</p>
            <p className="mt-1 text-xl font-bold tabular-nums text-gray-900 dark:text-slate-100">{runnerStatus.cycles}</p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-slate-400">{t("overview.generated_apps")}</p>
            <p className="mt-1 text-xl font-bold tabular-nums text-gray-900 dark:text-slate-100">{runnerStatus.apps_generated}</p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-slate-400">{t("overview.pushed_github")}</p>
            <p className="mt-1 text-xl font-bold tabular-nums text-gray-900 dark:text-slate-100">{runnerStatus.apps_pushed}</p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-slate-400">{t("overview.error_count")}</p>
            <p className={`mt-1 text-xl font-bold tabular-nums ${runnerStatus.errors > 0 ? "text-red-600 dark:text-red-400" : "text-gray-900 dark:text-slate-100"}`}>
              {runnerStatus.errors}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-slate-400">{t("overview.current_task")}</p>
            <p className="mt-1 truncate text-sm font-medium text-gray-700 dark:text-slate-300">
              {runnerStatus.current_run_id ?? "--"}
            </p>
          </div>
        </div>
      </div>

      {/* E) Thread search */}
      <div className="glass fade-in-up p-5">
        <label className="field-label">{t("overview.query_pipeline")}</label>
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 z-10 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder={t("overview.query_placeholder")}
              value={searchId}
              onChange={(e) => setSearchId(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              className="input pl-9"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={searchLoading}
            className="btn btn-secondary shrink-0"
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
      <div className="glass fade-in-up p-5">
        <div className="mb-5 flex items-baseline gap-3">
          <h2 className="section-title">
            <GitBranch className="h-4 w-4 text-gray-400 dark:text-slate-500" />
            {t("overview.pipeline_stages")}
          </h2>
          {pipelineStatus && (
            <span className="text-xs font-normal text-gray-400 dark:text-slate-500">
              Thread: {pipelineStatus.thread_id}
            </span>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {searchLoading
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
                      className={`rounded-xl border p-4 shadow-sm transition-all ${style.card}`}
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
                      <div className="space-y-1 text-xs text-gray-500 dark:text-slate-400">
                        <p>
                          {isActive
                            ? t("stage.running")
                            : stageStatusStyle(stage.key, currentStage).dot.includes("emerald")
                              ? t("stage.completed")
                              : t("stage.waiting")}
                        </p>
                        {isActive && pipelineTask && (
                          <p className="truncate">{pipelineTask}</p>
                        )}
                        {(() => {
                          const timingMap: Record<string, string> = {
                            demand_analysis: "crawl",
                            code_generation: "generate",
                            build: "build",
                            test: "test",
                            deploy: "publish",
                          };
                          const tk = timingMap[stage.key];
                          const secs = tk && runnerStatus.stage_timings?.[tk];
                          if (secs && secs > 0) {
                            return (
                              <p className="text-[10px] font-mono tabular-nums text-gray-400 dark:text-slate-500">
                                {secs >= 60 ? `${(secs / 60).toFixed(1)}min` : `${secs.toFixed(1)}s`}
                              </p>
                            );
                          }
                          return null;
                        })()}
                      </div>
                    </div>
                  );
                },
              )}
        </div>

        {pipelineStatus && (
          <div className="mt-4 flex flex-wrap gap-6 border-t border-gray-100 dark:border-[#1e2756] pt-4 text-sm text-gray-500 dark:text-slate-400">
            <span>
              Thread ID:{" "}
              <span className="font-medium text-gray-700 dark:text-slate-300">{pipelineStatus.thread_id}</span>
            </span>
            <span>
              Status:{" "}
              <span className="font-medium text-gray-700 dark:text-slate-300">{pipelineStatus.status}</span>
            </span>
          </div>
        )}
      </div>

      {/* G) Pipeline logs */}
      <div className="glass fade-in-up">
        <div className="flex items-center gap-2 border-b border-gray-100 dark:border-[#1e2756] px-5 py-4">
          <h2 className="section-title">
            <Activity className="h-4 w-4 text-gray-400 dark:text-slate-500" />
            {t("overview.pipeline_logs")}
          </h2>
          <button onClick={loadLogs} className="btn btn-ghost btn-sm ml-auto">
            <RefreshCw className="h-3.5 w-3.5" />
            {t("overview.refresh")}
          </button>
          {connected && (
            <span className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
              {t("overview.realtime")}
            </span>
          )}
        </div>
        <div className="p-3">
          <div
            ref={logRef}
            className="max-h-72 overflow-y-auto rounded-xl border border-gray-100 dark:border-[#1e2756]/60 bg-gray-50/80 dark:bg-[#0a0e27]/60 px-4 py-3 font-mono text-xs leading-relaxed text-gray-600 dark:text-slate-300"
          >
            {pipelineLogs.length === 0 ? (
              <p className="py-6 text-center text-gray-400 dark:text-slate-500">
                {t("overview.no_logs")}
              </p>
            ) : (
              pipelineLogs.map((entry, i) => {
                const badgeColor: Record<string, string> = {
                  stage_change: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400",
                  error: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400",
                  pipeline_update: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400",
                  build_update: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400",
                  info: "bg-gray-100 text-gray-600 dark:bg-[#161d45] dark:text-slate-400",
                };
                const badge = entry.type
                  ? badgeColor[entry.type] ?? "bg-gray-100 text-gray-600 dark:bg-[#161d45] dark:text-slate-400"
                  : "bg-gray-100 text-gray-600 dark:bg-[#161d45] dark:text-slate-400";
                return (
                  <div key={i} className="py-0.5 flex items-start gap-1.5">
                    <span className="text-gray-400 dark:text-slate-500 shrink-0 tabular-nums">{entry.time}</span>
                    <span
                      className={`inline-block rounded px-1 py-0 text-[10px] font-medium shrink-0 ${badge}`}
                    >
                      {entry.type}
                    </span>
                    <span className={entry.type === "error" ? "text-red-600 dark:text-red-400" : ""}>{entry.message}</span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* H) Two-column tables */}
      <div className="fade-in-up grid gap-6 lg:grid-cols-2">
        {/* Recent demands */}
        <div className="glass">
          <div className="border-b border-gray-100 dark:border-[#1e2756] px-5 py-4">
            <h2 className="section-title">{t("overview.recent_demands")}</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="table-head">
                <tr>
                  <th>{t("demands.id")}</th>
                  <th>{t("demands.name")}</th>
                  <th>{t("demands.status")}</th>
                  <th>{t("demands.time")}</th>
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
                      className="px-4 py-8 text-center text-gray-400 dark:text-slate-500"
                    >
                      {t("overview.no_data")}
                    </td>
                  </tr>
                ) : (
                  demands.map((d) => (
                    <tr key={d.demand_id} className="table-row">
                      <td className="text-gray-500 dark:text-slate-400">#{d.demand_id}</td>
                      <td className="max-w-[200px] truncate font-medium text-gray-900 dark:text-slate-200">
                        {d.title}
                      </td>
                      <td>
                        <StatusBadge status={d.status} t={t} />
                      </td>
                      <td className="text-gray-500 dark:text-slate-400">
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
        <div className="glass">
          <div className="border-b border-gray-100 dark:border-[#1e2756] px-5 py-4">
            <h2 className="section-title">{t("overview.recent_builds")}</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="table-head">
                <tr>
                  <th>{t("demands.id")}</th>
                  <th>{t("builds.step")}</th>
                  <th>{t("demands.status")}</th>
                  <th>{t("demands.time")}</th>
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
                      className="px-4 py-8 text-center text-gray-400 dark:text-slate-500"
                    >
                      {t("overview.no_data")}
                    </td>
                  </tr>
                ) : (
                  builds.map((b) => (
                    <tr key={b.build_id} className="table-row">
                      <td className="text-gray-500 dark:text-slate-400">#{b.build_id}</td>
                      <td className="max-w-[200px] truncate font-medium text-gray-900 dark:text-slate-200">
                        {b.step}
                      </td>
                      <td>
                        <StatusBadge status={b.status} t={t} />
                      </td>
                      <td className="text-gray-500 dark:text-slate-400">
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
    </div>
  );
}
