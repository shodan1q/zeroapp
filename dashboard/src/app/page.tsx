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
} from "lucide-react";
import {
  fetchDashboard,
  fetchDemands,
  fetchBuilds,
  fetchRunnerStatus,
  fetchPipelineLogs,
  generateCustomApp,
} from "@/lib/api";
import type {
  DashboardSummary,
  DemandOut,
  BuildLogOut,
  RunnerStatus,
} from "@/lib/types";
import { useWebSocket } from "@/hooks/useWebSocket";

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

function StatusBadge({ status }: { status: string }) {
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
  const label: Record<string, string> = {
    pending: "待处理",
    evaluating: "评估中",
    approved: "已通过",
    rejected: "已拒绝",
    in_progress: "开发中",
    done: "已完成",
    running: "运行中",
    success: "成功",
    failed: "失败",
    cancelled: "已取消",
  };
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${map[status] ?? "bg-gray-100 text-gray-600"}`}
    >
      {label[status] ?? status}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Main page                                                         */
/* ------------------------------------------------------------------ */

export default function OverviewPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [demands, setDemands] = useState<DemandOut[]>([]);
  const [builds, setBuilds] = useState<BuildLogOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [apiConnected, setApiConnected] = useState(true);
  const [activityLog, setActivityLog] = useState<
    { time: string; message: string; type?: string }[]
  >([]);
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

  const logRef = useRef<HTMLDivElement>(null);
  const { connected, lastEvent } = useWebSocket();

  /* ---------- Fetch data ---------------------------------------- */

  const loadData = useCallback(async () => {
    try {
      const [dash, demandsRes, buildsRes, logsRes] = await Promise.all([
        fetchDashboard(),
        fetchDemands({ page: 1, page_size: 5 }),
        fetchBuilds({ limit: 5 }),
        fetchPipelineLogs(),
      ]);
      setSummary(dash);
      setDemands(demandsRes.items);
      setBuilds(buildsRes.items);
      if (logsRes.logs.length > 0) {
        setActivityLog((prev) => {
          const serverLogs = logsRes.logs.map((l) => ({
            time: new Date(l.time).toLocaleTimeString("zh-CN"),
            message: l.message,
            type: l.type,
          }));
          if (prev.length > serverLogs.length) {
            return [...serverLogs, ...prev.slice(serverLogs.length)];
          }
          return serverLogs;
        });
      }
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

  useEffect(() => {
    loadRunnerStatus();
    const interval = runnerStatus.running ? 5_000 : 15_000;
    const timer = setInterval(loadRunnerStatus, interval);
    return () => clearInterval(timer);
  }, [loadRunnerStatus, runnerStatus.running]);

  /* ---------- WebSocket updates --------------------------------- */

  useEffect(() => {
    if (!lastEvent) return;

    const ts = new Date(lastEvent.timestamp).toLocaleTimeString("zh-CN");
    const msg =
      typeof lastEvent.data === "object" && lastEvent.data !== null
        ? (lastEvent.data as { message?: string }).message ??
          JSON.stringify(lastEvent.data)
        : String(lastEvent.data);

    setActivityLog((prev) => [
      ...prev.slice(-199),
      { time: ts, message: msg, type: lastEvent.type },
    ]);

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
    }

    if (lastEvent.type === "pipeline_update") {
      const d = lastEvent.data as {
        stats?: { message?: string };
        message?: string;
      };
      const m = d.stats?.message ?? d.message;
      if (m) {
        setPipelineTask(m);
      }
    }

    if (
      lastEvent.type === "build_update" ||
      lastEvent.type === "demand_update" ||
      lastEvent.type === "app_update"
    ) {
      loadData();
    }
  }, [lastEvent, loadData]);

  // Auto-scroll activity log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [activityLog]);

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
      setCustomResult({ status: "error", message: "请求失败，请重试" });
    } finally {
      setCustomLoading(false);
    }
  }, [customTheme, runnerStatus.running, loadRunnerStatus]);

  /* ---------- Stats cards --------------------------------------- */

  const statsCards = [
    {
      label: "总应用数",
      value: summary?.total_apps ?? 0,
      icon: Layers,
      color: "text-blue-500",
      bg: "bg-blue-50",
    },
    {
      label: "已上架",
      value: summary?.live_apps ?? 0,
      icon: Rocket,
      color: "text-emerald-500",
      bg: "bg-emerald-50",
    },
    {
      label: "开发中",
      value: summary?.developing_apps ?? 0,
      icon: Code2,
      color: "text-purple-500",
      bg: "bg-purple-50",
    },
    {
      label: "总需求数",
      value: summary?.total_demands ?? 0,
      icon: Lightbulb,
      color: "text-amber-500",
      bg: "bg-amber-50",
    },
    {
      label: "今日构建",
      value: summary?.builds_today ?? 0,
      icon: Hammer,
      color: "text-indigo-500",
      bg: "bg-indigo-50",
    },
    {
      label: "待处理",
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
        <h1 className="text-2xl font-semibold text-gray-900">概览</h1>
        <button
          onClick={loadData}
          className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-600 shadow-sm transition-colors hover:bg-gray-50"
        >
          <RefreshCw className="h-4 w-4" />
          刷新
        </button>
      </div>

      {/* Backend not connected warning */}
      {!loading && !apiConnected && (
        <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle className="h-5 w-5 flex-shrink-0 text-amber-500" />
          <span>后端服务未连接，当前显示为空数据。请检查后端是否已启动。</span>
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
                  key={card.label}
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
                      <p className="text-xs text-gray-500">{card.label}</p>
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
              {runnerStatus.running ? "流水线运行中" : "流水线已停止"}
            </span>
          </div>
          <span className="text-gray-300">|</span>
          <span className="truncate text-sm text-gray-500">
            当前任务: {runnerStatus.current_run_id ?? pipelineTask}
          </span>
          <span className="ml-auto shrink-0 text-xs text-gray-400">
            周期 {runnerStatus.cycles} / 已生成 {runnerStatus.apps_generated} / 已推送 {runnerStatus.apps_pushed}
          </span>
        </div>
      </div>

      {/* C) Custom generation card */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-2">
          <Sparkles className="h-5 w-5 text-indigo-500" />
          <h2 className="text-base font-semibold text-gray-900">自定义生成</h2>
        </div>
        <p className="mb-4 text-sm text-gray-500">
          输入你的 App 主题或需求描述，系统将自动生成完整的 Flutter 应用
        </p>
        <div className="flex gap-3">
          <input
            type="text"
            value={customTheme}
            onChange={(e) => setCustomTheme(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCustomGenerate()}
            disabled={runnerStatus.running || customLoading}
            placeholder="例如：一个带有星空动画背景的冥想计时器..."
            className="flex-1 rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-700 placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-gray-50 disabled:text-gray-400"
          />
          <button
            onClick={handleCustomGenerate}
            disabled={!customTheme.trim() || runnerStatus.running || customLoading}
            className="flex shrink-0 items-center gap-2 rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
            {customLoading ? "提交中..." : "开始生成"}
          </button>
        </div>
        {runnerStatus.running && (
          <p className="mt-2 text-xs text-amber-600">
            流水线运行中，请等待完成后再生成
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

      {/* D) Two-column tables */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Recent demands */}
        <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-100 px-5 py-4">
            <h2 className="text-sm font-semibold text-gray-700">最近需求</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                  <th className="px-4 py-3 font-medium">ID</th>
                  <th className="px-4 py-3 font-medium">标题</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium">时间</th>
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
                      暂无数据
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
                        <StatusBadge status={d.status} />
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
            <h2 className="text-sm font-semibold text-gray-700">最近构建</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                  <th className="px-4 py-3 font-medium">ID</th>
                  <th className="px-4 py-3 font-medium">步骤</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium">时间</th>
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
                      暂无数据
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
                        <StatusBadge status={b.status} />
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

      {/* E) Activity log */}
      <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="flex items-center gap-2 border-b border-gray-100 px-5 py-4">
          <Activity className="h-4 w-4 text-gray-400" />
          <h2 className="text-sm font-semibold text-gray-700">活动日志</h2>
          {connected && (
            <span className="ml-auto flex items-center gap-1.5 text-xs text-emerald-600">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
              实时
            </span>
          )}
        </div>
        <div
          ref={logRef}
          className="max-h-48 overflow-y-auto px-5 py-3 font-mono text-xs leading-relaxed text-gray-600"
        >
          {activityLog.length === 0 ? (
            <p className="py-6 text-center text-gray-400">暂无活动记录</p>
          ) : (
            activityLog.map((entry, i) => {
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
                  {entry.type && (
                    <span
                      className={`inline-block rounded px-1 py-0 text-[10px] font-medium shrink-0 ${badge}`}
                    >
                      {entry.type}
                    </span>
                  )}
                  <span className={entry.type === "error" ? "text-red-600" : ""}>{entry.message}</span>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
