"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Smartphone,
  Search,
  RefreshCw,
  Star,
  Download,
  DollarSign,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Package,
  FolderOpen,
  Wrench,
  Monitor,
  Tablet,
  Loader2,
  X,
} from "lucide-react";
import { fetchApps, rebuildApp, listGeneratedApps, fetchDeviceStatus, runAppOnDevice } from "@/lib/api";
import type { AppOut, PaginatedResponse, GeneratedApp } from "@/lib/types";
import { useWebSocket } from "@/hooks/useWebSocket";
import Link from "next/link";
import { useI18n } from "@/lib/i18n";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function statusBadge(status: string, t: (key: string) => string) {
  const map: Record<string, string> = {
    draft:
      "inline-flex items-center rounded-full border border-gray-200 bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600 dark:border-[#1e2756] dark:bg-[#161d45] dark:text-slate-300",
    code_generated: "badge-info",
    building: "badge-info",
    testing: "badge-info",
    live: "badge-success",
    failed: "badge-error",
    suspended: "badge-warning",
  };
  const labelKey: Record<string, string> = {
    draft: "status.draft",
    code_generated: "status.code_generated",
    building: "status.building",
    testing: "status.testing",
    live: "status.live",
    failed: "status.failed",
    suspended: "status.suspended",
  };
  return (
    <span
      className={
        map[status] ??
        "inline-flex items-center rounded-full border border-gray-200 bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600 dark:border-[#1e2756] dark:bg-[#161d45] dark:text-slate-300"
      }
    >
      {labelKey[status] ? t(labelKey[status]) : status}
    </span>
  );
}

function SkeletonCard() {
  return (
    <div className="glass animate-pulse p-5">
      <div className="mb-4 flex items-center gap-3">
        <div className="h-10 w-10 rounded-xl bg-gray-200 dark:bg-[#161d45]" />
        <div className="flex-1 space-y-2">
          <div className="h-4 w-32 rounded bg-gray-200 dark:bg-[#161d45]" />
          <div className="h-3 w-24 rounded bg-gray-200 dark:bg-[#161d45]" />
        </div>
      </div>
      <div className="space-y-2">
        <div className="h-3 w-full rounded bg-gray-200 dark:bg-[#161d45]" />
        <div className="h-3 w-2/3 rounded bg-gray-200 dark:bg-[#161d45]" />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function AppsPage() {
  const { t } = useI18n();
  const [data, setData] = useState<PaginatedResponse<AppOut> | null>(null);
  const [generatedApps, setGeneratedApps] = useState<GeneratedApp[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [rebuildingId, setRebuildingId] = useState<number | null>(null);
  const [runningPlatform, setRunningPlatform] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Array<{id: number; message: string; type: "success" | "error" | "info"}>>([]);

  const { lastEvent } = useWebSocket();

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [appsRes, genRes] = await Promise.all([
        fetchApps({
          page,
          page_size: 12,
          status: statusFilter || undefined,
        }),
        listGeneratedApps(),
      ]);
      setData(appsRes);
      setGeneratedApps(genRes.apps);
      // Clamp current page when the result shrinks (e.g. after filtering)
      const total = Math.ceil(appsRes.total / appsRes.page_size);
      if (appsRes.total > 0 && page > total) {
        setPage(total);
      } else if (appsRes.items.length === 0 && page > 1) {
        setPage(page - 1);
      }
    } catch (err) {
      console.error("Failed to load apps", err);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (lastEvent?.type === "app_update") {
      loadData();
    }
  }, [lastEvent, loadData]);

  const handleRebuild = async (id: number) => {
    setRebuildingId(id);
    try {
      await rebuildApp(id);
      loadData();
    } catch (err) {
      console.error("Rebuild failed", err);
    } finally {
      setRebuildingId(null);
    }
  };

  const addToast = useCallback((message: string, type: "success" | "error" | "info") => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const handleRunOnDevice = async (appPath: string, platform: string) => {
    const platformLabel: Record<string, string> = {
      android: "Android",
      ios: "iOS",
      ohos: "HarmonyOS",
    };
    const key = `${appPath}-${platform}`;
    setRunningPlatform(key);
    try {
      // First check device status
      const devices = await fetchDeviceStatus();
      const available =
        platform === "android" ? devices.android :
        platform === "ios" ? devices.ios :
        platform === "ohos" ? devices.ohos : false;

      if (!available) {
        addToast(`${t("apps.start_emulator")} ${platformLabel[platform]}`, "error");
        return;
      }

      addToast(`${t("apps.running_on")} ${platformLabel[platform]}...`, "info");
      const result = await runAppOnDevice(appPath, platform);
      // Backend returns {status:"building"} when the run kicks off successfully
      if (result.status === "success" || result.status === "building") {
        addToast(result.message, result.status === "building" ? "info" : "success");
      } else {
        addToast(result.message, "error");
      }
    } catch (err) {
      console.error("Run on device failed", err);
      addToast(`${platformLabel[platform]} ${t("apps.run_failed")}`, "error");
    } finally {
      setRunningPlatform(null);
    }
  };

  const dbItems = data?.items ?? [];
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  // Client-side search filter for DB apps
  const filteredDbItems = search
    ? dbItems.filter((a) => a.app_name.toLowerCase().includes(search.toLowerCase()))
    : dbItems;

  // Client-side search filter for generated apps
  const filteredGenApps = search
    ? generatedApps.filter((a) => a.name.toLowerCase().includes(search.toLowerCase()))
    : generatedApps;

  const hasAnyData = filteredGenApps.length > 0 || filteredDbItems.length > 0;

  return (
    <div className="space-y-6">
      {/* Toast notifications */}
      {toasts.length > 0 && (
        <div className="fixed right-4 top-4 z-50 flex flex-col gap-2">
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm shadow-lg transition-all ${
                toast.type === "success"
                  ? "bg-emerald-600 text-white"
                  : toast.type === "error"
                    ? "bg-red-600 text-white"
                    : "bg-blue-600 text-white"
              }`}
            >
              {toast.type === "info" && <Loader2 className="h-4 w-4 animate-spin" />}
              <span>{toast.message}</span>
              <button
                onClick={() => removeToast(toast.id)}
                className="ml-2 rounded p-0.5 hover:bg-white/20"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Header */}
      <div className="fade-in-up flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span className="icon-chip icon-chip-blue">
            <Smartphone className="h-5 w-5" />
          </span>
          <h1 className="page-title">{t("apps.title")}</h1>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 dark:text-slate-500" />
            <input
              type="text"
              placeholder={t("apps.search")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="input w-56 pl-9"
            />
          </div>

          {/* Status filter (only applies to DB apps) */}
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="input w-auto"
          >
            <option value="">{t("apps.all_status")}</option>
            <option value="draft">{t("status.draft")}</option>
            <option value="code_generated">{t("status.code_generated")}</option>
            <option value="building">{t("status.building")}</option>
            <option value="live">{t("status.live")}</option>
            <option value="failed">{t("status.failed")}</option>
            <option value="suspended">{t("status.suspended")}</option>
          </select>

          <button onClick={loadData} className="btn btn-secondary">
            <RefreshCw className="h-4 w-4" />
            {t("overview.refresh")}
          </button>
        </div>
      </div>

      {/* Generated apps section (file system) */}
      {(loading || filteredGenApps.length > 0) && (
        <div className="fade-in-up">
          <h2 className="section-title mb-3">
            <span className="icon-chip icon-chip-green h-7 w-7 rounded-lg">
              <FolderOpen className="h-4 w-4" />
            </span>
            {t("apps.generated_apps")}
            {!loading && (
              <span className="text-xs font-normal tabular-nums text-gray-400 dark:text-slate-500">
                ({filteredGenApps.length})
              </span>
            )}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {loading
              ? Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
              : filteredGenApps.map((app) => (
                  <div key={app.id} className="glass glass-hover flex flex-col p-5">
                    {/* App header */}
                    <div className="mb-4 flex items-start gap-3">
                      <span className="icon-chip icon-chip-green">
                        <Package className="h-5 w-5" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <h3 className="truncate text-sm font-semibold text-gray-900 dark:text-slate-100">
                          {app.name}
                        </h3>
                        <p className="truncate text-xs text-gray-400 dark:text-slate-500">
                          {app.id}
                        </p>
                      </div>
                    </div>

                    {/* Status */}
                    <div className="mb-3">
                      <span className="badge-success">{t("status.code_generated")}</span>
                    </div>

                    {/* Path */}
                    <div className="mb-4">
                      <p
                        className="truncate rounded-lg border border-gray-100 bg-gray-50/70 px-2.5 py-1.5 font-mono text-xs text-gray-500 dark:border-[#1e2756] dark:bg-[#0a0e27]/50 dark:text-slate-400"
                        title={app.path}
                      >
                        {app.path}
                      </p>
                    </div>

                    {/* Run buttons */}
                    <div className="mb-4 flex items-center gap-2">
                      <button
                        onClick={() => handleRunOnDevice(app.path, "android")}
                        disabled={runningPlatform === `${app.path}-android`}
                        className="btn btn-secondary btn-sm flex-1"
                      >
                        {runningPlatform === `${app.path}-android` ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Smartphone className="h-3 w-3" />
                        )}
                        Android
                      </button>
                      <button
                        onClick={() => handleRunOnDevice(app.path, "ios")}
                        disabled={runningPlatform === `${app.path}-ios`}
                        className="btn btn-secondary btn-sm flex-1"
                      >
                        {runningPlatform === `${app.path}-ios` ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Monitor className="h-3 w-3" />
                        )}
                        iOS
                      </button>
                      <button
                        onClick={() => handleRunOnDevice(app.path, "ohos")}
                        disabled={runningPlatform === `${app.path}-ohos`}
                        className="btn btn-secondary btn-sm flex-1"
                      >
                        {runningPlatform === `${app.path}-ohos` ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Tablet className="h-3 w-3" />
                        )}
                        HarmonyOS
                      </button>
                    </div>

                    {/* Footer */}
                    <div className="mt-auto flex items-center justify-between border-t border-gray-100 pt-3 dark:border-[#1e2756]">
                      <p className="text-[10px] tabular-nums text-gray-400 dark:text-slate-500">
                        {new Date(app.created_at).toLocaleDateString("zh-CN")}
                      </p>
                      <div className="flex items-center gap-2">
                        <Link href="/revise" className="btn btn-primary btn-sm">
                          <Wrench className="h-3 w-3" />
                          {t("apps.revise")}
                        </Link>
                      </div>
                    </div>
                  </div>
                ))}
          </div>
        </div>
      )}

      {/* DB apps section */}
      {(loading || filteredDbItems.length > 0) && (
        <div className="fade-in-up">
          <h2 className="section-title mb-3">
            <span className="icon-chip icon-chip-blue h-7 w-7 rounded-lg">
              <Smartphone className="h-4 w-4" />
            </span>
            {t("apps.db_apps")}
            {!loading && (
              <span className="text-xs font-normal tabular-nums text-gray-400 dark:text-slate-500">
                ({data?.total ?? 0})
              </span>
            )}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {loading
              ? Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
              : filteredDbItems.map((app) => (
                  <div key={app.app_id} className="glass glass-hover flex flex-col p-5">
                    {/* App header */}
                    <div className="mb-4 flex items-start gap-3">
                      <span className="icon-chip icon-chip-blue">
                        <Package className="h-5 w-5" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <h3 className="truncate text-sm font-semibold text-gray-900 dark:text-slate-100">
                          {app.app_name}
                        </h3>
                        <p className="truncate text-xs text-gray-400 dark:text-slate-500">
                          {app.package_name}
                        </p>
                      </div>
                    </div>

                    {/* Status */}
                    <div className="mb-3">{statusBadge(app.status, t)}</div>

                    {/* Stats */}
                    <div className="mb-4 grid grid-cols-3 gap-2">
                      <div className="rounded-lg border border-gray-100 bg-gray-50/70 px-2 py-2 text-center dark:border-[#1e2756] dark:bg-[#0a0e27]/50">
                        <div className="flex items-center justify-center gap-1 text-gray-400 dark:text-slate-500">
                          <Download className="h-3 w-3" />
                          <span className="text-[10px]">{t("apps.downloads")}</span>
                        </div>
                        <p className="mt-0.5 text-sm font-semibold tabular-nums text-gray-800 dark:text-slate-200">
                          {app.total_downloads > 0 ? app.total_downloads.toLocaleString() : "--"}
                        </p>
                      </div>
                      <div className="rounded-lg border border-gray-100 bg-gray-50/70 px-2 py-2 text-center dark:border-[#1e2756] dark:bg-[#0a0e27]/50">
                        <div className="flex items-center justify-center gap-1 text-gray-400 dark:text-slate-500">
                          <Star className="h-3 w-3" />
                          <span className="text-[10px]">{t("apps.rating")}</span>
                        </div>
                        <p className="mt-0.5 text-sm font-semibold tabular-nums text-gray-800 dark:text-slate-200">
                          {app.rating !== null ? app.rating.toFixed(1) : "--"}
                        </p>
                      </div>
                      <div className="rounded-lg border border-gray-100 bg-gray-50/70 px-2 py-2 text-center dark:border-[#1e2756] dark:bg-[#0a0e27]/50">
                        <div className="flex items-center justify-center gap-1 text-gray-400 dark:text-slate-500">
                          <DollarSign className="h-3 w-3" />
                          <span className="text-[10px]">{t("apps.revenue")}</span>
                        </div>
                        <p className="mt-0.5 text-sm font-semibold tabular-nums text-gray-800 dark:text-slate-200">
                          {app.revenue_usd > 0 ? `$${app.revenue_usd.toFixed(2)}` : "--"}
                        </p>
                      </div>
                    </div>

                    {/* Footer */}
                    <div className="mt-auto flex items-center justify-between border-t border-gray-100 pt-3 dark:border-[#1e2756]">
                      <p className="text-[10px] tabular-nums text-gray-400 dark:text-slate-500">
                        {new Date(app.created_at).toLocaleDateString("zh-CN")}
                      </p>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleRebuild(app.app_id)}
                          disabled={rebuildingId === app.app_id}
                          className="btn btn-ghost btn-sm"
                        >
                          <RefreshCw
                            className={`h-3 w-3 ${rebuildingId === app.app_id ? "animate-spin" : ""}`}
                          />
                          {t("apps.rebuild")}
                        </button>
                        {app.google_play_url && (
                          <a
                            href={app.google_play_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="btn btn-secondary btn-sm"
                          >
                            <ExternalLink className="h-3 w-3" />
                            {t("apps.view_details")}
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && !hasAnyData && (
        <div className="glass fade-in-up flex flex-col items-center justify-center py-16">
          <Smartphone className="mb-3 h-10 w-10 text-gray-300 dark:text-gray-600" />
          <p className="text-sm text-gray-400 dark:text-slate-500">{t("common.no_data")}</p>
          <p className="mt-1 text-xs text-gray-400 dark:text-slate-500">
            {t("apps.no_apps_hint")}
          </p>
        </div>
      )}

      {/* Pagination (for DB apps) */}
      {data && totalPages > 1 && (
        <div className="fade-in-up flex items-center justify-between">
          <p className="text-xs tabular-nums text-gray-500 dark:text-slate-400">
            {t("apps.db_apps")}: {data.total} / {data.page}/{totalPages}
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="btn btn-ghost btn-sm px-2"
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
                    page === pageNum ? "btn-primary" : "btn-ghost"
                  }`}
                >
                  {pageNum}
                </button>
              );
            })}
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="btn btn-ghost btn-sm px-2"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
