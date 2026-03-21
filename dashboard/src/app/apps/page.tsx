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
    draft: "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300",
    code_generated: "bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400",
    building: "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    testing: "bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400",
    live: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
    failed: "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    suspended: "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
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
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${map[status] ?? "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300"}`}
    >
      {labelKey[status] ? t(labelKey[status]) : status}
    </span>
  );
}

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-3">
        <div className="h-12 w-12 rounded-lg bg-gray-200 dark:bg-gray-700" />
        <div className="flex-1 space-y-2">
          <div className="h-4 w-32 rounded bg-gray-200 dark:bg-gray-700" />
          <div className="h-3 w-24 rounded bg-gray-200 dark:bg-gray-700" />
        </div>
      </div>
      <div className="space-y-2">
        <div className="h-3 w-full rounded bg-gray-200 dark:bg-gray-700" />
        <div className="h-3 w-2/3 rounded bg-gray-200 dark:bg-gray-700" />
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
      if (result.status === "success") {
        addToast(result.message, "success");
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
              className={`flex items-center gap-2 rounded-lg px-4 py-3 text-sm shadow-lg transition-all ${
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
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <Smartphone className="h-6 w-6 text-blue-500" />
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">{t("apps.title")}</h1>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder={t("apps.search")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 py-2 pl-9 pr-3 text-sm text-gray-700 dark:text-gray-200 shadow-sm placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* Status filter (only applies to DB apps) */}
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-700 dark:text-gray-200 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="">{t("apps.all_status")}</option>
            <option value="draft">{t("status.draft")}</option>
            <option value="code_generated">{t("status.code_generated")}</option>
            <option value="building">{t("status.building")}</option>
            <option value="live">{t("status.live")}</option>
            <option value="failed">{t("status.failed")}</option>
            <option value="suspended">{t("status.suspended")}</option>
          </select>

          <button
            onClick={loadData}
            className="flex items-center gap-1.5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-600 dark:text-gray-300 shadow-sm transition-colors hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            <RefreshCw className="h-4 w-4" />
            {t("overview.refresh")}
          </button>
        </div>
      </div>

      {/* Generated apps section (file system) */}
      {(loading || filteredGenApps.length > 0) && (
        <div>
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
            <FolderOpen className="h-4 w-4 text-emerald-500" />
            {t("apps.generated_apps")}
            {!loading && (
              <span className="text-xs font-normal text-gray-400 dark:text-gray-500">
                ({filteredGenApps.length})
              </span>
            )}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {loading
              ? Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
              : filteredGenApps.map((app) => (
                  <div
                    key={app.id}
                    className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5 shadow-sm transition-shadow hover:shadow-md"
                  >
                    {/* App header */}
                    <div className="mb-4 flex items-start gap-3">
                      <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-emerald-50 dark:bg-emerald-900/30">
                        <Package className="h-6 w-6 text-emerald-500" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <h3 className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
                          {app.name}
                        </h3>
                        <p className="truncate text-xs text-gray-400 dark:text-gray-500">
                          {app.id}
                        </p>
                      </div>
                    </div>

                    {/* Status */}
                    <div className="mb-4">
                      <span className="inline-block rounded-full bg-emerald-50 dark:bg-emerald-900/30 px-2.5 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-400">
                        {t("status.code_generated")}
                      </span>
                    </div>

                    {/* Path */}
                    <div className="mb-4">
                      <p className="truncate font-mono text-xs text-gray-400 dark:text-gray-500" title={app.path}>
                        {app.path}
                      </p>
                    </div>

                    {/* Run buttons */}
                    <div className="mb-4 flex items-center gap-2">
                      <button
                        onClick={() => handleRunOnDevice(app.path, "android")}
                        disabled={runningPlatform === `${app.path}-android`}
                        className="flex flex-1 items-center justify-center gap-1 rounded-md border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 px-2 py-1.5 text-xs font-medium text-green-700 dark:text-green-400 transition-colors hover:bg-green-100 dark:hover:bg-green-900/40 disabled:opacity-50"
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
                        className="flex flex-1 items-center justify-center gap-1 rounded-md border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 px-2 py-1.5 text-xs font-medium text-blue-700 dark:text-blue-400 transition-colors hover:bg-blue-100 dark:hover:bg-blue-900/40 disabled:opacity-50"
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
                        className="flex flex-1 items-center justify-center gap-1 rounded-md border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-2 py-1.5 text-xs font-medium text-red-700 dark:text-red-400 transition-colors hover:bg-red-100 dark:hover:bg-red-900/40 disabled:opacity-50"
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
                    <div className="flex items-center justify-between border-t border-gray-100 dark:border-gray-700 pt-3">
                      <p className="text-[10px] text-gray-400 dark:text-gray-500">
                        {new Date(app.created_at).toLocaleDateString("zh-CN")}
                      </p>
                      <div className="flex items-center gap-2">
                        <Link
                          href="/revise"
                          className="flex items-center gap-1 rounded-md border border-gray-200 dark:border-gray-600 px-2 py-1 text-xs text-gray-600 dark:text-gray-300 transition-colors hover:bg-gray-50 dark:hover:bg-gray-700"
                        >
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
        <div>
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
            <Smartphone className="h-4 w-4 text-blue-500" />
            {t("apps.db_apps")}
            {!loading && (
              <span className="text-xs font-normal text-gray-400 dark:text-gray-500">
                ({data?.total ?? 0})
              </span>
            )}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {loading
              ? Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
              : filteredDbItems.map((app) => (
                  <div
                    key={app.app_id}
                    className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5 shadow-sm transition-shadow hover:shadow-md"
                  >
                    {/* App header */}
                    <div className="mb-4 flex items-start gap-3">
                      <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-blue-50 dark:bg-blue-900/30">
                        <Package className="h-6 w-6 text-blue-500" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <h3 className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
                          {app.app_name}
                        </h3>
                        <p className="truncate text-xs text-gray-400 dark:text-gray-500">
                          {app.package_name}
                        </p>
                      </div>
                    </div>

                    {/* Status */}
                    <div className="mb-4">{statusBadge(app.status, t)}</div>

                    {/* Stats */}
                    <div className="mb-4 grid grid-cols-3 gap-2 text-center">
                      <div>
                        <div className="flex items-center justify-center gap-1 text-gray-400">
                          <Download className="h-3.5 w-3.5" />
                        </div>
                        <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                          {app.total_downloads > 0 ? app.total_downloads.toLocaleString() : "--"}
                        </p>
                        <p className="text-[10px] text-gray-400 dark:text-gray-500">{t("apps.downloads")}</p>
                      </div>
                      <div>
                        <div className="flex items-center justify-center gap-1 text-gray-400">
                          <Star className="h-3.5 w-3.5" />
                        </div>
                        <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                          {app.rating !== null ? app.rating.toFixed(1) : "--"}
                        </p>
                        <p className="text-[10px] text-gray-400 dark:text-gray-500">{t("apps.rating")}</p>
                      </div>
                      <div>
                        <div className="flex items-center justify-center gap-1 text-gray-400">
                          <DollarSign className="h-3.5 w-3.5" />
                        </div>
                        <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                          {app.revenue_usd > 0 ? `$${app.revenue_usd.toFixed(2)}` : "--"}
                        </p>
                        <p className="text-[10px] text-gray-400 dark:text-gray-500">{t("apps.revenue")}</p>
                      </div>
                    </div>

                    {/* Footer */}
                    <div className="flex items-center justify-between border-t border-gray-100 dark:border-gray-700 pt-3">
                      <p className="text-[10px] text-gray-400 dark:text-gray-500">
                        {new Date(app.created_at).toLocaleDateString("zh-CN")}
                      </p>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleRebuild(app.app_id)}
                          disabled={rebuildingId === app.app_id}
                          className="flex items-center gap-1 rounded-md border border-gray-200 dark:border-gray-600 px-2 py-1 text-xs text-gray-600 dark:text-gray-300 transition-colors hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
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
                            className="flex items-center gap-1 rounded-md border border-gray-200 dark:border-gray-600 px-2 py-1 text-xs text-gray-600 dark:text-gray-300 transition-colors hover:bg-gray-50 dark:hover:bg-gray-700"
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
        <div className="flex flex-col items-center justify-center rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 py-16 shadow-sm">
          <Smartphone className="mb-3 h-10 w-10 text-gray-300 dark:text-gray-600" />
          <p className="text-sm text-gray-400 dark:text-gray-500">{t("common.no_data")}</p>
          <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
            {t("apps.no_apps_hint")}
          </p>
        </div>
      )}

      {/* Pagination (for DB apps) */}
      {data && totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {t("apps.db_apps")}: {data.total} / {data.page}/{totalPages}
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="rounded-md border border-gray-200 dark:border-gray-600 p-1.5 text-gray-500 dark:text-gray-400 transition-colors hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-40"
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
                      : "border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                  }`}
                >
                  {pageNum}
                </button>
              );
            })}
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="rounded-md border border-gray-200 dark:border-gray-600 p-1.5 text-gray-500 dark:text-gray-400 transition-colors hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-40"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
