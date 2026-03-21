"use client";

import { useEffect, useState, useCallback } from "react";
import {
  GitBranch,
  Search,
  Play,
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  Bug,
  Code2,
  Hammer,
  TestTube,
  Rocket,
  Brain,
  Globe,
  RefreshCw,
} from "lucide-react";
import {
  fetchPipelineStatus,
  triggerPipeline,
  fetchBuilds,
} from "@/lib/api";
import type { PipelineState, BuildLogOut } from "@/lib/types";
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
  const [pipeline, setPipeline] = useState<PipelineState | null>(null);
  const [history, setHistory] = useState<BuildLogOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState("");

  const { lastEvent } = useWebSocket();

  /* ---------- Load history -------------------------------------- */

  const loadHistory = useCallback(async () => {
    try {
      setHistoryLoading(true);
      const res = await fetchBuilds({ limit: 20 });
      setHistory(res);
    } catch {
      // ignore
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

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
        setPipeline((prev) =>
          prev
            ? {
                ...prev,
                stage: (data.stage as PipelineState["stage"]) ?? prev.stage,
                progress: data.progress ?? prev.progress,
                message: data.message ?? prev.message,
                updated_at: lastEvent.timestamp,
              }
            : null,
        );
      }
    }
    if (lastEvent?.type === "build_update") {
      loadHistory();
    }
  }, [lastEvent, threadId, loadHistory]);

  /* ---------- Actions ------------------------------------------- */

  const handleSearch = async () => {
    if (!searchId.trim()) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetchPipelineStatus(searchId.trim());
      setPipeline(res);
      setThreadId(res.thread_id);
    } catch {
      setError("未找到该流水线");
      setPipeline(null);
    } finally {
      setLoading(false);
    }
  };

  const handleTrigger = async () => {
    setTriggering(true);
    setError("");
    try {
      const res = await triggerPipeline();
      setPipeline(res);
      setThreadId(res.thread_id);
      setSearchId(res.thread_id);
    } catch {
      setError("触发流水线失败");
    } finally {
      setTriggering(false);
    }
  };

  const currentStage = pipeline?.stage ?? "idle";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <GitBranch className="h-6 w-6 text-purple-500" />
          <h1 className="text-2xl font-semibold text-gray-900">流水线</h1>
        </div>

        <button
          onClick={handleTrigger}
          disabled={triggering}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700 disabled:opacity-50"
        >
          {triggering ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          触发新流水线
        </button>
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
          {pipeline && (
            <span className="ml-3 text-xs font-normal text-gray-400">
              Thread: {pipeline.thread_id}
            </span>
          )}
        </h2>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {pipeline === null && !loading
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
                        {isActive && pipeline && (
                          <>
                            <p>进度: {Math.round(pipeline.progress * 100)}%</p>
                            <p className="truncate">
                              消息: {pipeline.message}
                            </p>
                          </>
                        )}
                        <p>
                          更新时间:{" "}
                          {pipeline
                            ? new Date(
                                pipeline.updated_at,
                              ).toLocaleTimeString("zh-CN")
                            : "--"}
                        </p>
                      </div>
                    </div>
                  );
                },
              )}
        </div>

        {/* Pipeline info bar */}
        {pipeline && (
          <div className="mt-4 flex flex-wrap gap-6 border-t border-gray-100 pt-4 text-sm text-gray-500">
            <span>
              需求 ID:{" "}
              <span className="font-medium text-gray-700">
                {pipeline.demand_id ?? "--"}
              </span>
            </span>
            <span>
              应用 ID:{" "}
              <span className="font-medium text-gray-700">
                {pipeline.app_id ?? "--"}
              </span>
            </span>
            <span>
              开始时间:{" "}
              <span className="font-medium text-gray-700">
                {new Date(pipeline.started_at).toLocaleString("zh-CN")}
              </span>
            </span>
          </div>
        )}
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
                <th className="px-4 py-3 font-medium">应用</th>
                <th className="px-4 py-3 font-medium">阶段</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">开始时间</th>
                <th className="px-4 py-3 font-medium">耗时</th>
              </tr>
            </thead>
            <tbody>
              {historyLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    {Array.from({ length: 6 }).map((_, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-4 w-full animate-pulse rounded bg-gray-200" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : history.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-12 text-center text-gray-400"
                  >
                    暂无数据
                  </td>
                </tr>
              ) : (
                history.map((b) => (
                  <tr
                    key={b.id}
                    className="border-b border-gray-50 transition-colors hover:bg-gray-50"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">
                      #{b.id}
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {b.app_name}
                    </td>
                    <td className="px-4 py-3 text-gray-600">{b.stage}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          b.status === "success"
                            ? "bg-emerald-50 text-emerald-700"
                            : b.status === "failed"
                              ? "bg-red-50 text-red-700"
                              : b.status === "building"
                                ? "bg-blue-50 text-blue-700"
                                : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {b.status === "success"
                          ? "成功"
                          : b.status === "failed"
                            ? "失败"
                            : b.status === "building"
                              ? "构建中"
                              : b.status === "queued"
                                ? "排队中"
                                : b.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {new Date(b.started_at).toLocaleString("zh-CN", {
                        month: "2-digit",
                        day: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {b.duration_seconds
                        ? b.duration_seconds < 60
                          ? `${b.duration_seconds}s`
                          : `${Math.floor(b.duration_seconds / 60)}m ${b.duration_seconds % 60}s`
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
