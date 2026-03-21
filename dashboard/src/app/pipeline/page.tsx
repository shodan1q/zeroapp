"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  GitBranch,
  Search,
  Play,
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  Code2,
  Hammer,
  TestTube,
  Rocket,
  Brain,
  RefreshCw,
  Square,
  Activity,
} from "lucide-react";
import {
  fetchPipelineStatus,
  triggerPipeline,
  fetchBuilds,
  fetchRunnerStatus,
  fetchPipelineLogs,
  startPipeline,
  stopPipeline,
} from "@/lib/api";
import type { PipelineStatusResponse, BuildLogOut, RunnerStatus } from "@/lib/types";
import { useWebSocket } from "@/hooks/useWebSocket";

/* ------------------------------------------------------------------ */
/*  Stage definitions                                                  */
/* ------------------------------------------------------------------ */

interface StageConfig {
  key: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const STAGES: StageConfig[] = [
  { key: "idle", label: "空闲", icon: Clock },
  { key: "demand_analysis", label: "需求分析", icon: Brain },
  { key: "code_generation", label: "代码生成", icon: Code2 },
  { key: "build", label: "构建", icon: Hammer },
  { key: "test", label: "测试", icon: TestTube },
  { key: "deploy", label: "部署", icon: Rocket },
  { key: "done", label: "完成", icon: CheckCircle2 },
  { key: "error", label: "错误", icon: XCircle },
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
    return {
      dot: "bg-red-500",
      card: "border-red-200 bg-red-50",
      text: "text-red-700",
    };
  }
  if (stageKey === "error") {
    return {
      dot: "bg-gray-200",
      card: "border-gray-200 bg-white",
      text: "text-gray-400",
    };
  }
  if (stageKey === currentStage) {
    return {
      dot: "bg-blue-500 animate-pulse",
      card: "border-blue-200 bg-blue-50",
      text: "text-blue-700",
    };
  }
  if (stageIdx < currentIdx && currentIdx >= 0) {
    return {
      dot: "bg-emerald-500",
      card: "border-emerald-200 bg-emerald-50",
      text: "text-emerald-700",
    };
  }
  return {
    dot: "bg-gray-200",
    card: "border-gray-200 bg-white",
    text: "text-gray-400",
  };
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
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function PipelinePage() {
  const [threadId, setThreadId] = useState("");
  const [searchId, setSearchId] = useState("");
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatusResponse | null>(null);
  const [history, setHistory] = useState<BuildLogOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState("");

  // Runner status
  const [runnerStatus, setRunnerStatus] = useState<RunnerStatus>({
    running: false,
    current_run_id: null,
    started_at: null,
    cycles: 0,
    apps_generated: 0,
    apps_pushed: 0,
    errors: 0,
  });
  const [runnerLoading, setRunnerLoading] = useState(false);

  // Pipeline logs
  const [pipelineLogs, setPipelineLogs] = useState<
    { time: string; message: string; type: string }[]
  >([]);
  const logRef = useRef<HTMLDivElement>(null);

  const { lastEvent } = useWebSocket();

  /* ---------- Load runner status --------------------------------- */

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

  /* ---------- Load history -------------------------------------- */

  const loadHistory = useCallback(async () => {
    try {
      setHistoryLoading(true);
      const res = await fetchBuilds({ limit: 20 });
      setHistory(res.items);
    } catch {
      // ignore
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
    loadRunnerStatus();
    loadLogs();
  }, [loadHistory, loadRunnerStatus, loadLogs]);

  /* ---------- Polling -------------------------------------------- */

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
    if (lastEvent?.type === "pipeline_update") {
      const data = lastEvent.data as {
        thread_id?: string;
        stage?: string;
        progress?: number;
        message?: string;
      };
      if (data.thread_id && (!threadId || data.thread_id === threadId)) {
        setThreadId(data.thread_id);
        setPipelineStatus((prev) =>
          prev
            ? {
                ...prev,
                stage: data.stage ?? prev.stage,
                message: data.message ?? prev.message,
              }
            : {
                thread_id: data.thread_id!,
                status: "found",
                stage: data.stage ?? "idle",
                message: data.message,
              },
        );
      }
      loadLogs();
    }
    if (lastEvent?.type === "build_update") {
      loadHistory();
    }
    if (lastEvent?.type === "stage_change") {
      loadLogs();
      loadRunnerStatus();
    }
  }, [lastEvent, threadId, loadHistory, loadLogs, loadRunnerStatus]);

  // Auto-scroll logs
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [pipelineLogs]);

  /* ---------- Actions ------------------------------------------- */

  const handleSearch = async () => {
    if (!searchId.trim()) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetchPipelineStatus(searchId.trim());
      if (res) {
        setPipelineStatus(res);
        setThreadId(res.thread_id);
      } else {
        setError("未找到该流水线");
        setPipelineStatus(null);
      }
    } catch {
      setError("未找到该流水线");
      setPipelineStatus(null);
    } finally {
      setLoading(false);
    }
  };

  const handleTrigger = async () => {
    setTriggering(true);
    setError("");
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
      } else {
        setError("触发流水线失败");
      }
    } catch {
      setError("触发流水线失败");
    } finally {
      setTriggering(false);
    }
  };

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

  const currentStage = pipelineStatus?.stage ?? "idle";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <GitBranch className="h-6 w-6 text-purple-500" />
          <h1 className="text-2xl font-semibold text-gray-900">流水线</h1>
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
            触发单次运行
          </button>
        </div>
      </div>

      {/* Runner control panel */}
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
                {runnerStatus.running ? "流水线运行中" : "流水线已停止"}
              </h2>
            </div>
            {runnerStatus.started_at && (
              <span className="text-sm text-gray-500">
                {"启动于 " + new Date(runnerStatus.started_at).toLocaleString("zh-CN")}
              </span>
            )}
          </div>
          <div>
            {runnerStatus.running ? (
              <button
                onClick={handleStopPipeline}
                disabled={runnerLoading}
                className="flex items-center gap-2 rounded-lg bg-red-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-red-700 disabled:opacity-50"
              >
                <Square className="h-4 w-4" />
                {runnerLoading ? "处理中..." : "停止流水线"}
              </button>
            ) : (
              <button
                onClick={handleStartPipeline}
                disabled={runnerLoading}
                className="flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-emerald-700 disabled:opacity-50"
              >
                <Play className="h-4 w-4" />
                {runnerLoading ? "处理中..." : "启动流水线"}
              </button>
            )}
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 border-t border-gray-100 pt-4 sm:grid-cols-5">
          <div>
            <p className="text-xs text-gray-500">运行周期</p>
            <p className="text-xl font-semibold text-gray-900">{runnerStatus.cycles}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">已生成应用</p>
            <p className="text-xl font-semibold text-gray-900">{runnerStatus.apps_generated}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">已推送 GitHub</p>
            <p className="text-xl font-semibold text-gray-900">{runnerStatus.apps_pushed}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">错误次数</p>
            <p className={`text-xl font-semibold ${runnerStatus.errors > 0 ? "text-red-600" : "text-gray-900"}`}>
              {runnerStatus.errors}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">当前任务</p>
            <p className="text-sm font-medium text-gray-700">
              {runnerStatus.current_run_id ?? "--"}
            </p>
          </div>
        </div>
      </div>

      {/* Thread search */}
      <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <label className="mb-2 block text-sm font-medium text-gray-700">
          查询流水线运行状态
        </label>
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="输入 Thread ID..."
              value={searchId}
              onChange={(e) => setSearchId(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              className="w-full rounded-lg border border-gray-200 bg-white py-2 pl-9 pr-3 text-sm text-gray-700 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={loading}
            className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              "查询"
            )}
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
      </div>

      {/* Pipeline visualization */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-5 text-sm font-semibold text-gray-700">
          流水线阶段
          {pipelineStatus && (
            <span className="ml-3 text-xs font-normal text-gray-400">
              Thread: {pipelineStatus.thread_id}
            </span>
          )}
        </h2>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {pipelineStatus === null && !loading
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
                          <div
                            className={`h-2.5 w-2.5 rounded-full ${style.dot}`}
                          />
                          <span
                            className={`text-sm font-semibold ${style.text}`}
                          >
                            {stage.label}
                          </span>
                        </div>
                        <Icon className={`h-5 w-5 ${style.text}`} />
                      </div>

                      <div className="space-y-1.5 text-xs text-gray-500">
                        <p>
                          状态:{" "}
                          {isActive
                            ? "运行中"
                            : stageStatusStyle(stage.key, currentStage)
                                    .dot.includes("emerald")
                              ? "已完成"
                              : "等待中"}
                        </p>
                        {isActive && pipelineStatus?.message && (
                          <p className="truncate">
                            消息: {pipelineStatus.message}
                          </p>
                        )}
                      </div>
                    </div>
                  );
                },
              )}
        </div>

        {/* Pipeline info bar */}
        {pipelineStatus && (
          <div className="mt-4 flex flex-wrap gap-6 border-t border-gray-100 pt-4 text-sm text-gray-500">
            <span>
              Thread ID:{" "}
              <span className="font-medium text-gray-700">
                {pipelineStatus.thread_id}
              </span>
            </span>
            <span>
              状态:{" "}
              <span className="font-medium text-gray-700">
                {pipelineStatus.status}
              </span>
            </span>
          </div>
        )}
      </div>

      {/* Pipeline logs */}
      <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="flex items-center gap-2 border-b border-gray-100 px-5 py-4">
          <Activity className="h-4 w-4 text-gray-400" />
          <h2 className="text-sm font-semibold text-gray-700">流水线日志</h2>
          <button
            onClick={loadLogs}
            className="ml-auto flex items-center gap-1.5 text-xs text-gray-400 transition-colors hover:text-gray-600"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            刷新
          </button>
        </div>
        <div
          ref={logRef}
          className="max-h-72 overflow-y-auto px-5 py-3 font-mono text-xs leading-relaxed text-gray-600"
        >
          {pipelineLogs.length === 0 ? (
            <p className="py-6 text-center text-gray-400">
              暂无日志记录。启动流水线后将在此显示运行日志。
            </p>
          ) : (
            pipelineLogs.map((entry, i) => {
              const badgeColor: Record<string, string> = {
                stage_change: "bg-blue-100 text-blue-700",
                error: "bg-red-100 text-red-700",
                pipeline_update: "bg-emerald-100 text-emerald-700",
                info: "bg-gray-100 text-gray-600",
              };
              const badge = badgeColor[entry.type] ?? "bg-gray-100 text-gray-600";
              return (
                <div key={i} className="flex items-start gap-1.5 py-0.5">
                  <span className="shrink-0 text-gray-400">{entry.time}</span>
                  <span
                    className={`inline-block shrink-0 rounded px-1 py-0 text-[10px] font-medium ${badge}`}
                  >
                    {entry.type}
                  </span>
                  <span className={entry.type === "error" ? "text-red-600" : ""}>
                    {entry.message}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Pipeline run history */}
      <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
          <h2 className="text-sm font-semibold text-gray-700">运行历史</h2>
          <button
            onClick={loadHistory}
            className="flex items-center gap-1.5 text-xs text-gray-400 transition-colors hover:text-gray-600"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            刷新
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                <th className="px-4 py-3 font-medium">ID</th>
                <th className="px-4 py-3 font-medium">步骤</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">创建时间</th>
                <th className="px-4 py-3 font-medium">结束时间</th>
              </tr>
            </thead>
            <tbody>
              {historyLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 5 }).map((_, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-4 w-full animate-pulse rounded bg-gray-200" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : history.length === 0 ? (
                <tr>
                  <td
                    colSpan={5}
                    className="px-4 py-12 text-center"
                  >
                    <p className="text-gray-400">暂无运行历史</p>
                    <p className="mt-1 text-xs text-gray-400">
                      流水线运行后将在此显示历史记录。
                    </p>
                  </td>
                </tr>
              ) : (
                history.map((b) => (
                  <tr
                    key={b.build_id}
                    className="border-b border-gray-50 transition-colors hover:bg-gray-50"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">
                      #{b.build_id}
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {b.step}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          b.status === "success"
                            ? "bg-emerald-50 text-emerald-700"
                            : b.status === "failed"
                              ? "bg-red-50 text-red-700"
                              : b.status === "running"
                                ? "bg-blue-50 text-blue-700"
                                : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {b.status === "success"
                          ? "成功"
                          : b.status === "failed"
                            ? "失败"
                            : b.status === "running"
                              ? "运行中"
                              : b.status === "pending"
                                ? "待执行"
                                : b.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {new Date(b.created_at).toLocaleString("zh-CN", {
                        month: "2-digit",
                        day: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {b.finished_at
                        ? new Date(b.finished_at).toLocaleString("zh-CN", {
                            month: "2-digit",
                            day: "2-digit",
                            hour: "2-digit",
                            minute: "2-digit",
                          })
                        : "--"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
