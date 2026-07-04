"use client";

import React, { useEffect, useState, useCallback, useRef } from "react";
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
  ExternalLink,
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
import { useI18n } from "@/lib/i18n";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const STATUS_OPTIONS = [
  { value: "", labelKey: "demands.all_status" },
  { value: "pending", labelKey: "status.pending" },
  { value: "evaluating", labelKey: "status.evaluating" },
  { value: "approved", labelKey: "status.approved" },
  { value: "rejected", labelKey: "status.rejected" },
  { value: "in_progress", labelKey: "status.in_progress" },
  { value: "done", labelKey: "status.done" },
] as const;

const SOURCE_OPTIONS = [
  { value: "", labelKey: "demands.all_source" },
  { value: "reddit", labelKey: "Reddit" },
  { value: "producthunt", labelKey: "Product Hunt" },
  { value: "twitter", labelKey: "Twitter" },
  { value: "manual", labelKey: "demands.source_manual" },
] as const;

function statusBadge(status: string) {
  const map: Record<string, string> = {
    pending: "bg-gray-100 text-gray-600 dark:bg-[#161d45] dark:text-slate-300",
    evaluating: "bg-yellow-50 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
    approved: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
    rejected: "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    in_progress: "bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
    done: "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
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
      className={`inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${map[status] ?? "bg-gray-100 text-gray-600 dark:bg-[#161d45] dark:text-slate-300"}`}
    >
      {label[status] ?? status}
    </span>
  );
}

function SkeletonRow() {
  return (
    <tr className="table-row">
      {Array.from({ length: 9 }).map((_, i) => (
        <td key={i}>
          <div className="h-4 w-full animate-pulse rounded bg-gray-200 dark:bg-[#161d45]" />
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
  const { t } = useI18n();
  const [data, setData] = useState<PaginatedResponse<DemandOut> | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<DemandDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [actionError, setActionError] = useState("");
  const expandedIdRef = useRef<number | null>(null);

  const { lastEvent } = useWebSocket();

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetchDemands({
        page,
        page_size: 20,
        status: statusFilter || undefined,
        source: sourceFilter || undefined,
      });
      setData(res);
      // Clamp current page when the result shrinks (e.g. after filtering)
      const total = Math.ceil(res.total / res.page_size);
      if (res.total > 0 && page > total) {
        setPage(total);
      } else if (res.items.length === 0 && page > 1) {
        setPage(page - 1);
      }
    } catch (err) {
      console.error("Failed to load demands", err);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, sourceFilter]);

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
      expandedIdRef.current = null;
      setDetail(null);
      return;
    }
    setExpandedId(id);
    expandedIdRef.current = id;
    setDetail(null);
    setDetailLoading(true);
    try {
      const d = await fetchDemandDetail(id);
      // Ignore late responses for rows that are no longer expanded
      if (expandedIdRef.current === id) setDetail(d);
    } catch {
      if (expandedIdRef.current === id) setDetail(null);
    } finally {
      if (expandedIdRef.current === id) setDetailLoading(false);
    }
  };

  const showActionError = () => {
    setActionError("操作失败，请检查后端连接");
    setTimeout(() => setActionError(""), 5000);
  };

  const handleApprove = async (id: number) => {
    setActionLoading(id);
    try {
      const res = await approveDemand(id);
      if (res) {
        loadData();
      } else {
        showActionError();
      }
    } catch (err) {
      console.error("Approve failed", err);
      showActionError();
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (id: number) => {
    setActionLoading(id);
    try {
      const res = await rejectDemand(id);
      if (res) {
        loadData();
      } else {
        showActionError();
      }
    } catch (err) {
      console.error("Reject failed", err);
      showActionError();
    } finally {
      setActionLoading(null);
    }
  };

  const items = data?.items ?? [];
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="fade-in-up flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="icon-chip icon-chip-amber">
            <Lightbulb className="h-5 w-5" />
          </div>
          <h1 className="page-title">{t("demands.title")}</h1>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="input w-auto"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {t(o.labelKey)}
              </option>
            ))}
          </select>

          <select
            value={sourceFilter}
            onChange={(e) => {
              setSourceFilter(e.target.value);
              setPage(1);
            }}
            className="input w-auto"
          >
            {SOURCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {t(o.labelKey)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Action error banner */}
      {actionError && (
        <div className="fade-in-up rounded-xl border border-red-200 dark:border-red-800 bg-red-50/80 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-400">
          {actionError}
        </div>
      )}

      {/* Table */}
      <div className="glass fade-in-up overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="table-head">
              <tr>
                <th>{t("demands.id")}</th>
                <th>{t("demands.name")}</th>
                <th>{t("demands.category")}</th>
                <th>{t("demands.source")}</th>
                <th>{t("demands.score")}</th>
                <th>{t("demands.trend")}</th>
                <th>{t("demands.status")}</th>
                <th>{t("demands.time")}</th>
                <th>{t("demands.actions")}</th>
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
                    className="px-4 py-12 text-center text-gray-400 dark:text-slate-500"
                  >
                    {t("common.no_data")}
                  </td>
                </tr>
              ) : (
                items.map((d) => (
                  <React.Fragment key={d.demand_id}>
                    <tr
                      onClick={() => handleExpand(d.demand_id)}
                      className="table-row cursor-pointer"
                    >
                      <td className="text-xs tabular-nums text-gray-500 dark:text-slate-400">#{d.demand_id}</td>
                      <td className="max-w-[220px] truncate text-sm font-medium text-gray-900 dark:text-slate-200">
                        {d.title}
                      </td>
                      <td className="text-xs text-gray-500 dark:text-slate-400">{d.category ?? "--"}</td>
                      <td className="text-xs text-gray-500 dark:text-slate-400">{d.source ?? "--"}</td>
                      <td className="text-xs tabular-nums text-gray-500 dark:text-slate-400">{formatScore(d.overall_score)}</td>
                      <td className="text-xs tabular-nums text-gray-500 dark:text-slate-400">{formatScore(d.trend_score)}</td>
                      <td>{statusBadge(d.status)}</td>
                      <td className="whitespace-nowrap text-xs tabular-nums text-gray-500 dark:text-slate-400">
                        {new Date(d.created_at).toLocaleDateString("zh-CN")}
                      </td>
                      <td>
                        <div className="flex items-center gap-2">
                          {(d.status === "pending" || d.status === "evaluating") && (
                            <>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleApprove(d.demand_id);
                                }}
                                disabled={actionLoading === d.demand_id}
                                className="btn btn-success btn-sm"
                              >
                                <Check className="h-3.5 w-3.5" />
                                {t("demands.approve")}
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleReject(d.demand_id);
                                }}
                                disabled={actionLoading === d.demand_id}
                                className="btn btn-danger btn-sm"
                              >
                                <X className="h-3.5 w-3.5" />
                                {t("demands.reject")}
                              </button>
                            </>
                          )}
                          {expandedId === d.demand_id ? (
                            <ChevronUp className="h-4 w-4 shrink-0 text-gray-400 dark:text-slate-500" />
                          ) : (
                            <ChevronDown className="h-4 w-4 shrink-0 text-gray-400 dark:text-slate-500" />
                          )}
                        </div>
                      </td>
                    </tr>
                    {expandedId === d.demand_id && (
                      <tr key={`detail-${d.demand_id}`}>
                        <td
                          colSpan={9}
                          className="border-b border-gray-100 dark:border-[#1e2756] px-4 py-4"
                        >
                          <div className="rounded-xl border border-gray-200/70 dark:border-[#1e2756]/60 bg-gray-50/70 dark:bg-[#0a0e27]/50 p-4">
                            {detailLoading ? (
                              <div className="flex items-center gap-2 text-sm text-gray-400 dark:text-slate-500">
                                <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-300 dark:border-[#1e2756] border-t-blue-500" />
                                加载中...
                              </div>
                            ) : detail ? (
                              <div className="grid gap-4 text-sm md:grid-cols-2">
                                {/* Left column */}
                                <div className="space-y-3">
                                  <div>
                                    <p className="field-label">描述 / Description</p>
                                    <p className="text-sm text-gray-600 dark:text-slate-400">{detail.description || "--"}</p>
                                  </div>
                                  {detail.core_features && (
                                    <div>
                                      <p className="field-label">核心功能 / Core Features</p>
                                      <div className="flex flex-wrap gap-1.5">
                                        {(() => {
                                          try {
                                            const features = JSON.parse(detail.core_features);
                                            if (Array.isArray(features)) {
                                              return features.map((f: string, i: number) => (
                                                <span key={i} className="inline-flex items-center rounded-md bg-indigo-50 dark:bg-indigo-900/30 px-2 py-0.5 text-xs text-indigo-700 dark:text-indigo-400">
                                                  {f}
                                                </span>
                                              ));
                                            }
                                          } catch {}
                                          return <span className="text-sm text-gray-600 dark:text-slate-400">{detail.core_features}</span>;
                                        })()}
                                      </div>
                                    </div>
                                  )}
                                  {detail.target_users && (
                                    <div>
                                      <p className="field-label">目标用户 / Target Users</p>
                                      <p className="text-sm text-gray-600 dark:text-slate-400">{detail.target_users}</p>
                                    </div>
                                  )}
                                </div>
                                {/* Right column */}
                                <div className="space-y-3">
                                  <div className="grid grid-cols-2 gap-3">
                                    {detail.complexity && (
                                      <div className="glass p-3">
                                        <p className="text-xs text-gray-500 dark:text-slate-400">复杂度 / Complexity</p>
                                        <p className="mt-1 text-sm font-semibold text-gray-800 dark:text-slate-200">{detail.complexity}</p>
                                      </div>
                                    )}
                                    {detail.monetization && (
                                      <div className="glass p-3">
                                        <p className="text-xs text-gray-500 dark:text-slate-400">变现方式 / Monetization</p>
                                        <p className="mt-1 text-sm font-semibold text-gray-800 dark:text-slate-200">{detail.monetization}</p>
                                      </div>
                                    )}
                                    {detail.competition_score !== null && detail.competition_score !== undefined && (
                                      <div className="glass p-3">
                                        <p className="text-xs text-gray-500 dark:text-slate-400">竞争度 / Competition</p>
                                        <p className="mt-1 text-sm font-semibold tabular-nums text-gray-800 dark:text-slate-200">{detail.competition_score.toFixed(2)}</p>
                                      </div>
                                    )}
                                    {detail.feasibility_score !== null && detail.feasibility_score !== undefined && (
                                      <div className="glass p-3">
                                        <p className="text-xs text-gray-500 dark:text-slate-400">可行性 / Feasibility</p>
                                        <p className="mt-1 text-sm font-semibold tabular-nums text-gray-800 dark:text-slate-200">{detail.feasibility_score.toFixed(2)}</p>
                                      </div>
                                    )}
                                  </div>
                                  {detail.source_url && (
                                    <div>
                                      <p className="field-label">需求来源 / Source</p>
                                      <a
                                        href={detail.source_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-1 text-sm text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 dark:hover:text-indigo-300 hover:underline"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        {detail.source || "查看来源"}
                                        <ExternalLink className="h-3.5 w-3.5" />
                                      </a>
                                    </div>
                                  )}
                                  {!detail.source_url && detail.source && (
                                    <div>
                                      <p className="field-label">需求来源 / Source</p>
                                      <span className="text-sm text-gray-600 dark:text-slate-400">{detail.source}</span>
                                    </div>
                                  )}
                                </div>
                              </div>
                            ) : (
                              <p className="text-sm text-gray-400 dark:text-slate-500">
                                无法加载详情
                              </p>
                            )}
                          </div>
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
          <div className="flex items-center justify-between border-t border-gray-100 dark:border-[#1e2756] px-5 py-3">
            <p className="text-xs tabular-nums text-gray-500 dark:text-slate-400">
              共 {data.total} 条，第 {data.page}/{totalPages} 页
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="btn btn-secondary btn-sm"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              {Array.from({ length: Math.min(totalPages, 5) }).map((_, i) => {
                const start = Math.max(1, Math.min(page - 2, totalPages - 4));
                const pageNum = start + i;
                return (
                  <button
                    key={pageNum}
                    onClick={() => setPage(pageNum)}
                    className={`btn btn-sm tabular-nums ${
                      page === pageNum ? "btn-primary" : "btn-secondary"
                    }`}
                  >
                    {pageNum}
                  </button>
                );
              })}
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="btn btn-secondary btn-sm"
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
