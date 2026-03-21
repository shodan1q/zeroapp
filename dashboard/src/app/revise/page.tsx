"use client";

import { useEffect, useState } from "react";
import { Wrench, Loader2, CheckCircle, XCircle, FileCode } from "lucide-react";
import { listGeneratedApps, reviseApp } from "@/lib/api";
import type { GeneratedApp, RevisionResult } from "@/lib/types";

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
    setInstruction("");
    setLoading(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Wrench className="h-6 w-6 text-gray-500" />
        <h1 className="text-2xl font-semibold text-gray-900">修改完善</h1>
      </div>

      {/* Main form card */}
      <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="border-b border-gray-100 px-5 py-4">
          <h2 className="text-sm font-semibold text-gray-700">提交修改请求</h2>
        </div>
        <div className="space-y-4 p-5">
          {/* App selector */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700">
              选择应用
            </label>
            {loadingApps ? (
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <Loader2 className="h-4 w-4 animate-spin" />
                加载中...
              </div>
            ) : apps.length === 0 ? (
              <p className="text-sm text-gray-400">暂无已生成的应用</p>
            ) : (
              <select
                value={selectedApp}
                onChange={(e) => setSelectedApp(e.target.value)}
                className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
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
              <label className="mb-1.5 block text-sm font-medium text-gray-700">
                项目路径
              </label>
              <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 font-mono text-sm text-gray-500">
                {selectedAppInfo.path}
              </div>
            </div>
          )}

          {/* Instruction textarea */}
          <div>
            <label className="mb-1.5 block text-sm font-medium text-gray-700">
              修改说明
            </label>
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="描述你想要修改的内容..."
              rows={4}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* Submit button */}
          <div>
            <button
              onClick={handleSubmit}
              disabled={loading || !selectedApp || !instruction.trim()}
              className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  修改中...
                </>
              ) : (
                <>
                  <Wrench className="h-4 w-4" />
                  提交修改
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Revision history */}
      {history.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-100 px-5 py-4">
            <h2 className="text-sm font-semibold text-gray-700">修改记录</h2>
          </div>
          <div className="divide-y divide-gray-100">
            {history.map((entry) => (
              <div key={entry.id} className="px-5 py-4">
                <div className="mb-2 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {entry.result.status === "success" ? (
                      <CheckCircle className="h-4 w-4 text-emerald-500" />
                    ) : (
                      <XCircle className="h-4 w-4 text-red-500" />
                    )}
                    <span className="text-sm font-medium text-gray-800">
                      {entry.result.status === "success" ? "修改成功" : "修改失败"}
                    </span>
                  </div>
                  <span className="text-xs text-gray-400">{entry.timestamp}</span>
                </div>

                <p className="mb-2 text-sm text-gray-600">{entry.instruction}</p>

                {entry.result.status === "success" && entry.result.changes_made.length > 0 && (
                  <div className="mt-2">
                    <p className="mb-1 text-xs font-medium text-gray-500">
                      修改的文件:
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {entry.result.changes_made.map((f) => (
                        <span
                          key={f}
                          className="inline-flex items-center gap-1 rounded bg-gray-100 px-2 py-0.5 text-xs font-mono text-gray-600"
                        >
                          <FileCode className="h-3 w-3" />
                          {f}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {entry.result.status === "success" && entry.result.analyze_ok !== undefined && (
                  <div className="mt-2 text-xs text-gray-500">
                    {entry.result.analyze_ok
                      ? "Flutter analyze: 无问题"
                      : `Flutter analyze: 存在问题 - ${entry.result.analyze_output ?? ""}`}
                  </div>
                )}

                {entry.result.status === "error" && entry.result.message && (
                  <p className="mt-1 text-xs text-red-500">{entry.result.message}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
