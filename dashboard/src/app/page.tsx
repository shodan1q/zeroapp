"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import {
  Layers,
  Rocket,
  Code2,
  Lightbulb,
  Hammer,
  Clock,
  ArrowRight,
  Activity,
  RefreshCw,
} from "lucide-react";
import { fetchDashboard, fetchDemands, fetchBuilds } from "@/lib/api";
import type {
  DashboardSummary,
  DemandOut,
  BuildLogOut,
  WsEvent,
} from "@/lib/types";
import { useWebSocket } from "@/hooks/useWebSocket";

/* ------------------------------------------------------------------ */
/*  Pipeline stage definitions                                        */
/* ------------------------------------------------------------------ */

const PIPELINE_STAGES = [
  "需求爬取",
  "数据处理",
  "需求评估",
  "决策",
  "代码生成",
  "构建",
  "资源生成",
  "发布",
] as const;

type StageStatus = "pending" | "active" | "completed" | "failed";

function stageColor(s: StageStatus) {
  switch (s) {
    case "completed":
      return "bg-emerald-500";
    case "active":
      return "bg-blue-500 animate-pulse";
    case "failed":
      return "bg-red-500";
    default:
      return "bg-gray-300";
  }
}

function stageTextColor(s: StageStatus) {
  switch (s) {
    case "completed":
      return "text-emerald-600";
    case "active":
      return "text-blue-600";
    case "failed":
      return "text-red-600";
    default:
      return "text-gray-400";
  }
}

function lineColor(s: StageStatus) {
  switch (s) {
    case "completed":
      return "bg-emerald-400";
    case "active":
      return "bg-blue-400";
    case "failed":
      return "bg-red-400";
    default:
      return "bg-gray-200";
  }
}

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
    approved: "bg-emerald-50 text-emerald-700",
    rejected: "bg-red-50 text-red-700",
    in_progress: "bg-purple-50 text-purple-700",
    done: "bg-blue-50 text-blue-700",
    queued: "bg-gray-100 text-gray-600",
    building: "bg-blue-50 text-blue-700",
    success: "bg-emerald-50 text-emerald-700",
    failed: "bg-red-50 text-red-700",
    cancelled: "bg-gray-100 text-gray-500",
  };
  const label: Record<string, string> = {
    pending: "待处理",
    approved: "已通过",
    rejected: "已拒绝",
    in_progress: "开发中",
    done: "已完成",
    queued: "排队中",
    building: "构建中",
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
  const [pipelineStages, setPipelineStages] = useState<StageStatus[]>(
    Array(8).fill("pending") as StageStatus[],
  );
  const [pipelineInfo, setPipelineInfo] = useState({
    demandTitle: "--",
    elapsed: "--",
    retries: 0,
  });
  const [activityLog, setActivityLog] = useState<
    { time: string; message: string }[]
  >([]);
  const logRef = useRef<HTMLDivElement>(null);
  const { connected, lastEvent, events } = useWebSocket();

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
      setBuilds(buildsRes);
    } catch (err) {
      console.error("Failed to load dashboard data", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const timer = setInterval(loadData, 30_000);
    return () => clearInterval(timer);
  }, [loadData]);

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
      { time: ts, message: `[${lastEvent.type}] ${msg}` },
    ]);

    if (lastEvent.type === "pipeline_update") {
      const d = lastEvent.data as {
        stage?: string;
        progress?: number;
        message?: string;
      };
      if (typeof d.progress === "number") {
        const activeIdx = Math.min(
          Math.floor(d.progress * 8),
          7,
        );
        setPipelineStages(
          PIPELINE_STAGES.map((_, i) => {
            if (i < activeIdx) return "completed";
            if (i === activeIdx) return "active";
            return "pending";
          }),
        );
      }
      if (d.message) {
        setPipelineInfo((prev) => ({ ...prev, demandTitle: d.message! }));
      }
    }

    // Re-fetch on meaningful updates
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
      value: summary ? summary.total_apps - (summary.active_builds ?? 0) : 0,
      icon: Rocket,
      color: "text-emerald-500",
      bg: "bg-emerald-50",
    },
    {
      label: "开发中",
      value: summary?.active_builds ?? 0,
      icon: Code2,
      color: "text-purple-500",
      bg: "bg-purple-50",
    },
    {
      label: "今日需求",
      value: summary?.total_demands ?? 0,
      icon: Lightbulb,
      color: "text-amber-500",
      bg: "bg-amber-50",
    },
    {
      label: "今日构建",
      value: summary?.recent_builds?.length ?? 0,
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

      {/* B) Pipeline status */}
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="mb-5 text-sm font-semibold text-gray-700">
          流水线状态
        </h2>

        {/* Stage flow */}
        <div className="flex items-center justify-between overflow-x-auto pb-2">
          {PIPELINE_STAGES.map((name, i) => {
            const status = pipelineStages[i];
            return (
              <div key={name} className="flex items-center">
                <div className="flex flex-col items-center">
                  <div
                    className={`flex h-10 w-10 items-center justify-center rounded-full ${stageColor(status)}`}
                  >
                    <span className="text-xs font-bold text-white">
                      {i + 1}
                    </span>
                  </div>
                  <span
                    className={`mt-2 whitespace-nowrap text-xs font-medium ${stageTextColor(status)}`}
                  >
                    {name}
                  </span>
                </div>
                {i < PIPELINE_STAGES.length - 1 && (
                  <div className="mx-2 flex items-center">
                    <div
                      className={`h-0.5 w-8 sm:w-12 lg:w-16 ${lineColor(status)}`}
                    />
                    <ArrowRight
                      className={`h-3.5 w-3.5 ${stageTextColor(status)}`}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Pipeline info */}
        <div className="mt-4 flex flex-wrap gap-6 border-t border-gray-100 pt-4 text-sm text-gray-500">
          <span>
            当前需求:{" "}
            <span className="font-medium text-gray-700">
              {pipelineInfo.demandTitle}
            </span>
          </span>
          <span>
            已用时间:{" "}
            <span className="font-medium text-gray-700">
              {pipelineInfo.elapsed}
            </span>
          </span>
          <span>
            重试次数:{" "}
            <span className="font-medium text-gray-700">
              {pipelineInfo.retries}
            </span>
          </span>
        </div>
      </div>

      {/* C) Two-column tables */}
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
                      key={d.id}
                      className="border-b border-gray-50 transition-colors hover:bg-gray-50"
                    >
                      <td className="px-4 py-3 text-gray-500">#{d.id}</td>
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
                  <th className="px-4 py-3 font-medium">应用</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium">耗时</th>
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
                      key={b.id}
                      className="border-b border-gray-50 transition-colors hover:bg-gray-50"
                    >
                      <td className="px-4 py-3 text-gray-500">#{b.id}</td>
                      <td className="max-w-[200px] truncate px-4 py-3 font-medium text-gray-900">
                        {b.app_name}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={b.status} />
                      </td>
                      <td className="px-4 py-3 text-gray-500">
                        {b.duration_seconds
                          ? `${b.duration_seconds}s`
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

      {/* D) Activity log */}
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
          className="max-h-64 overflow-y-auto px-5 py-3 font-mono text-xs leading-relaxed text-gray-600"
        >
          {activityLog.length === 0 ? (
            <p className="py-6 text-center text-gray-400">暂无活动记录</p>
          ) : (
            activityLog.map((entry, i) => (
              <div key={i} className="py-0.5">
                <span className="text-gray-400">{entry.time}</span>{" "}
                <span>{entry.message}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
