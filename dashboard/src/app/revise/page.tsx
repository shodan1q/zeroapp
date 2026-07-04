"use client";

import { useEffect, useState } from "react";
import { Wrench, Loader2, CheckCircle, XCircle, FileCode, History } from "lucide-react";
import { listGeneratedApps, reviseApp } from "@/lib/api";
import type { GeneratedApp, RevisionResult } from "@/lib/types";
import { useI18n } from "@/lib/i18n";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface RevisionEntry {
  id: number;
  instruction: string;
  result: RevisionResult;
  timestamp: string;
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function RevisePage() {
  const { t } = useI18n();
  const [apps, setApps] = useState<GeneratedApp[]>([]);
  const [selectedApp, setSelectedApp] = useState<string>("");
  const [instruction, setInstruction] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingApps, setLoadingApps] = useState(true);
  const [history, setHistory] = useState<RevisionEntry[]>([]);
  const [nextId, setNextId] = useState(1);

  useEffect(() => {
    (async () => {
      setLoadingApps(true);
      const data = await listGeneratedApps();
      setApps(data.apps);
      if (data.apps.length > 0) {
        setSelectedApp(data.apps[0].path);
      }
      setLoadingApps(false);
    })();
  }, []);

  const selectedAppInfo = apps.find((a) => a.path === selectedApp);

  const handleSubmit = async () => {
    if (!selectedApp || !instruction.trim()) return;
    setLoading(true);
    const result = await reviseApp(selectedApp, instruction.trim());
    const entry: RevisionEntry = {
      id: nextId,
      instruction: instruction.trim(),
      result,
      timestamp: new Date().toLocaleString("zh-CN"),
    };
    setHistory((prev) => [entry, ...prev]);
    setNextId((n) => n + 1);
    // Keep the instruction in the textarea on failure so the user can retry
    if (result.status === "success") {
      setInstruction("");
    }
    setLoading(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="fade-in-up flex items-center gap-3">
        <span className="icon-chip icon-chip-purple">
          <Wrench className="h-5 w-5" />
        </span>
        <h1 className="page-title">{t("revise.title")}</h1>
      </div>

      {/* Main form card */}
      <div className="glass fade-in-up">
        <div className="border-b border-gray-100 px-5 py-4 dark:border-[#1e2756]">
          <h2 className="section-title">{t("revise.submit_request")}</h2>
        </div>
        <div className="space-y-4 p-5">
          {/* App selector */}
          <div>
            <label className="field-label">
              {t("revise.select_app")}
            </label>
            {loadingApps ? (
              <div className="flex items-center gap-2 text-sm text-gray-400 dark:text-slate-500">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("common.loading")}
              </div>
            ) : apps.length === 0 ? (
              <p className="text-sm text-gray-400 dark:text-slate-500">{t("revise.no_apps")}</p>
            ) : (
              <select
                value={selectedApp}
                onChange={(e) => setSelectedApp(e.target.value)}
                className="input"
              >
                {apps.map((app) => (
                  <option key={app.id} value={app.path}>
                    {app.name} ({app.id})
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Selected app path */}
          {selectedAppInfo && (
            <div>
              <label className="field-label">
                {t("revise.project_path")}
              </label>
              <div className="input font-mono text-gray-500 dark:text-slate-400">
                {selectedAppInfo.path}
              </div>
            </div>
          )}

          {/* Instruction textarea */}
          <div>
            <label className="field-label">
              {t("revise.instruction")}
            </label>
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder={t("revise.instruction_placeholder")}
              rows={4}
              className="input min-h-28 resize-y"
            />
          </div>

          {/* Submit button */}
          <div>
            <button
              onClick={handleSubmit}
              disabled={loading || !selectedApp || !instruction.trim()}
              className="btn btn-primary"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t("revise.submitting")}
                </>
              ) : (
                <>
                  <Wrench className="h-4 w-4" />
                  {t("revise.submit")}
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Revision history */}
      {history.length > 0 && (
        <div className="fade-in-up space-y-4">
          <h2 className="section-title">
            <span className="icon-chip icon-chip-slate h-7 w-7 rounded-lg">
              <History className="h-4 w-4" />
            </span>
            {t("revise.history")}
            <span className="text-xs font-normal tabular-nums text-gray-400 dark:text-slate-500">
              ({history.length})
            </span>
          </h2>
          <div className="space-y-4">
            {history.map((entry) => (
              <div key={entry.id} className="glass p-5">
                <div className="mb-3 flex items-center justify-between gap-4">
                  <span className={entry.result.status === "success" ? "badge-success" : "badge-error"}>
                    {entry.result.status === "success" ? (
                      <CheckCircle className="h-3.5 w-3.5" />
                    ) : (
                      <XCircle className="h-3.5 w-3.5" />
                    )}
                    {entry.result.status === "success" ? t("revise.success") : t("revise.failed")}
                  </span>
                  <span className="font-mono text-xs tabular-nums text-gray-400 dark:text-slate-500">
                    {entry.timestamp}
                  </span>
                </div>

                <p className="mb-2 text-sm text-gray-700 dark:text-slate-300">{entry.instruction}</p>

                {entry.result.status === "success" && entry.result.changes_made.length > 0 && (
                  <div className="mt-3 rounded-lg border border-gray-200/70 bg-gray-50/70 p-3 dark:border-[#1e2756] dark:bg-[#0a0e27]/50">
                    <p className="mb-2 text-xs font-medium text-gray-500 dark:text-slate-400">
                      {t("revise.files_changed")}:
                    </p>
                    <ul className="space-y-1">
                      {entry.result.changes_made.map((f) => (
                        <li
                          key={f}
                          className="flex items-center gap-1.5 font-mono text-xs text-gray-600 dark:text-slate-300"
                        >
                          <FileCode className="h-3 w-3 shrink-0 text-gray-400 dark:text-slate-500" />
                          {f}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {entry.result.status === "success" && entry.result.analyze_ok !== undefined && (
                  <div className="mt-2 text-xs text-gray-500 dark:text-slate-400">
                    {entry.result.analyze_ok
                      ? `Flutter analyze: ${t("revise.analyze_ok")}`
                      : `Flutter analyze: ${t("revise.analyze_fail")} - ${entry.result.analyze_output ?? ""}`}
                  </div>
                )}

                {entry.result.status === "error" && entry.result.message && (
                  <p className="mt-2 text-xs text-red-500 dark:text-red-400">{entry.result.message}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
