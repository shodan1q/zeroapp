"use client";

import React, { useEffect, useState, useCallback } from "react";
import {
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Check,
  X,
  Lightbulb,
} from "lucide-react";
import {
  fetchDemands,
  approveDemand,
  rejectDemand,
  fetchDemandDetail,
} from "@/lib/api";
import type {
  DemandOut,
  DemandDetail,
  PaginatedResponse,
} from "@/lib/types";
import { useWebSocket } from "@/hooks/useWebSocket";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const STATUS_OPTIONS = [
  { value: "", label: "全部状态" },
  { value: "pending", label: "待评估" },
  { value: "evaluating", label: "评估中" },
  { value: "approved", label: "已通过" },
  { value: "rejected", label: "已拒绝" },
  { value: "in_progress", label: "开发中" },
  { value: "done", label: "已完成" },
] as const;

const SOURCE_OPTIONS = [
  { value: "", label: "全部来源" },
  { value: "reddit", label: "Reddit" },
  { value: "producthunt", label: "Product Hunt" },
  { value: "twitter", label: "Twitter" },
  { value: "manual", label: "手动" },
] as const;

function statusBadge(status: string) {
  const map: Record<string, string> = {
    pending: "bg-gray-100 text-gray-600",
    evaluating: "bg-yellow-50 text-yellow-700",
    approved: "bg-emerald-50 text-emerald-700",
    rejected: "bg-red-50 text-red-700",
    in_progress: "bg-purple-50 text-purple-700",
    done: "bg-blue-50 text-blue-700",
  };
  const label: Record<string, string> = {
    pending: "待评估",
    evaluating: "评估中",
    approved: "已通过",
    rejected: "已拒绝",
    in_progress: "开发中",
    done: "已完成",
  };
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${map[status] ?? "bg-gray-100 text-gray-600"}`}
    >
      {label[status] ?? status}
    </span>
  );
}

function SkeletonRow() {
  return (
    <tr>
      {Array.from({ length: 9 }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-4 w-full animate-pulse rounded bg-gray-200" />
        </td>
      ))}
    </tr>
  );
}

function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "--";
  return score.toFixed(1);
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function DemandsPage() {
  const [data, setData] = useState<PaginatedResponse<DemandOut> | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<DemandDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const { lastEvent } = useWebSocket();

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetchDemands({
        page,
        page_size: 20,
        status: statusFilter || undefined,
      });
      setData(res);
    } catch (err) {
      console.error("Failed to load demands", err);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Auto-refresh on demand_update
  useEffect(() => {
    if (lastEvent?.type === "demand_update") {
      loadData();
    }
  }, [lastEvent, loadData]);

  const handleExpand = async (id: number) => {
    if (expandedId === id) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(id);
    setDetailLoading(true);
    try {
      const d = await fetchDemandDetail(id);
      setDetail(d);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleApprove = async (id: number) => {
    setActionLoading(id);
    try {
      await approveDemand(id);
      loadData();
    } catch (err) {
      console.error("Approve failed", err);
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (id: number) => {
    setActionLoading(id);
    try {
      await rejectDemand(id);
      loadData();
    } catch (err) {
      console.error("Reject failed", err);
    } finally {
      setActionLoading(null);
    }
  };

  const items = data?.items ?? [];
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <Lightbulb className="h-6 w-6 text-amber-500" />
          <h1 className="text-2xl font-semibold text-gray-900">需求管理</h1>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>

          <select
            value={sourceFilter}
            onChange={(e) => {
              setSourceFilter(e.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {SOURCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                <th className="px-4 py-3 font-medium">ID</th>
                <th className="px-4 py-3 font-medium">标题</th>
                <th className="px-4 py-3 font-medium">分类</th>
                <th className="px-4 py-3 font-medium">来源</th>
                <th className="px-4 py-3 font-medium">综合分</th>
                <th className="px-4 py-3 font-medium">趋势分</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">时间</th>
                <th className="px-4 py-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 8 }).map((_, i) => (
                  <SkeletonRow key={i} />
                ))
              ) : items.length === 0 ? (
                <tr>
                  <td
                    colSpan={9}
                    className="px-4 py-12 text-center text-gray-400"
                  >
                    暂无数据
                  </td>
                </tr>
              ) : (
                items.map((d) => (
                  <React.Fragment key={d.demand_id}>
                    <tr
                      onClick={() => handleExpand(d.demand_id)}
                      className="cursor-pointer border-b border-gray-50 transition-colors hover:bg-gray-50"
                    >
                      <td className="px-4 py-3 text-gray-500">#{d.demand_id}</td>
                      <td className="max-w-[220px] truncate px-4 py-3 font-medium text-gray-900">
                        {d.title}
                      </td>
                      <td className="px-4 py-3 text-gray-500">{d.category ?? "--"}</td>
                      <td className="px-4 py-3 text-gray-500">{d.source ?? "--"}</td>
                      <td className="px-4 py-3 text-gray-500">{formatScore(d.overall_score)}</td>
                      <td className="px-4 py-3 text-gray-500">{formatScore(d.trend_score)}</td>
                      <td className="px-4 py-3">{statusBadge(d.status)}</td>
                      <td className="px-4 py-3 text-gray-500">
                        {new Date(d.created_at).toLocaleDateString("zh-CN")}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {(d.status === "pending" || d.status === "evaluating") && (
                            <>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleApprove(d.demand_id);
                                }}
                                disabled={actionLoading === d.demand_id}
                                className="flex items-center gap-1 rounded-md bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 transition-colors hover:bg-emerald-100 disabled:opacity-50"
                              >
                                <Check className="h-3.5 w-3.5" />
                                通过
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleReject(d.demand_id);
                                }}
                                disabled={actionLoading === d.demand_id}
                                className="flex items-center gap-1 rounded-md bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700 transition-colors hover:bg-red-100 disabled:opacity-50"
                              >
                                <X className="h-3.5 w-3.5" />
                                拒绝
                              </button>
                            </>
                          )}
                          {expandedId === d.demand_id ? (
                            <ChevronUp className="h-4 w-4 text-gray-400" />
                          ) : (
                            <ChevronDown className="h-4 w-4 text-gray-400" />
                          )}
                        </div>
                      </td>
                    </tr>
                    {expandedId === d.demand_id && (
                      <tr key={`detail-${d.demand_id}`}>
                        <td
                          colSpan={9}
                          className="border-b border-gray-100 bg-gray-50 px-6 py-4"
                        >
                          {detailLoading ? (
                            <div className="flex items-center gap-2 text-sm text-gray-400">
                              <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-blue-500" />
                              加载中...
                            </div>
                          ) : detail ? (
                            <div className="space-y-2 text-sm">
                              <p>
                                <span className="font-medium text-gray-700">
                                  描述:
                                </span>{" "}
                                <span className="text-gray-600">
                                  {detail.description || "--"}
                                </span>
                              </p>
                              {detail.target_users && (
                                <p>
                                  <span className="font-medium text-gray-700">
                                    目标用户:
                                  </span>{" "}
                                  <span className="text-gray-600">
                                    {detail.target_users}
                                  </span>
                                </p>
                              )}
                              {detail.core_features && (
                                <p>
                                  <span className="font-medium text-gray-700">
                                    核心功能:
                                  </span>{" "}
                                  <span className="text-gray-600">
                                    {detail.core_features}
                                  </span>
                                </p>
                              )}
                              {detail.complexity && (
                                <p>
                                  <span className="font-medium text-gray-700">
                                    复杂度:
                                  </span>{" "}
                                  <span className="text-gray-600">
                                    {detail.complexity}
                                  </span>
                                </p>
                              )}
                              {detail.competition_score !== null && detail.competition_score !== undefined && (
                                <p>
                                  <span className="font-medium text-gray-700">
                                    竞争分:
                                  </span>{" "}
                                  <span className="text-gray-600">
                                    {detail.competition_score.toFixed(1)}
                                  </span>
                                </p>
                              )}
                              {detail.monetization && (
                                <p>
                                  <span className="font-medium text-gray-700">
                                    变现方式:
                                  </span>{" "}
                                  <span className="text-gray-600">
                                    {detail.monetization}
                                  </span>
                                </p>
                              )}
                            </div>
                          ) : (
                            <p className="text-sm text-gray-400">
                              无法加载详情
                            </p>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {data && totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-gray-100 px-4 py-3">
            <p className="text-xs text-gray-500">
              共 {data.total} 条，第 {data.page}/{totalPages} 页
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="rounded-md border border-gray-200 p-1.5 text-gray-500 transition-colors hover:bg-gray-50 disabled:opacity-40"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              {Array.from({ length: Math.min(totalPages, 5) }).map((_, i) => {
                const pageNum = i + 1;
                return (
                  <button
                    key={pageNum}
                    onClick={() => setPage(pageNum)}
                    className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                      page === pageNum
                        ? "bg-blue-600 text-white"
                        : "border border-gray-200 text-gray-600 hover:bg-gray-50"
                    }`}
                  >
                    {pageNum}
                  </button>
                );
              })}
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="rounded-md border border-gray-200 p-1.5 text-gray-500 transition-colors hover:bg-gray-50 disabled:opacity-40"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
