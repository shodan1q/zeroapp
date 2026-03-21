"use client";

import { useState } from "react";
import {
  Settings,
  Key,
  GitBranch,
  Globe,
  Store,
  Eye,
  EyeOff,
  Save,
  Server,
  Monitor,
} from "lucide-react";
import { useI18n } from "@/lib/i18n";

/* ------------------------------------------------------------------ */
/*  Section wrapper                                                    */
/* ------------------------------------------------------------------ */

function Section({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="flex items-center gap-2 border-b border-gray-100 px-5 py-4">
        <Icon className="h-5 w-5 text-gray-400" />
        <h2 className="text-sm font-semibold text-gray-700">{title}</h2>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Form field helpers                                                 */
/* ------------------------------------------------------------------ */

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-gray-700">
        {label}
      </label>
      {children}
    </div>
  );
}

function TextInput({
  value,
  onChange,
  placeholder,
  type = "text",
  readOnly = false,
}: {
  value: string;
  onChange?: (v: string) => void;
  placeholder?: string;
  type?: string;
  readOnly?: boolean;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
      placeholder={placeholder}
      readOnly={readOnly}
      className={`w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 ${readOnly ? "cursor-not-allowed bg-gray-50 text-gray-500" : ""}`}
    />
  );
}

function MaskedField({ label, value }: { label: string; value: string }) {
  const [visible, setVisible] = useState(false);
  const masked = value
    ? value.slice(0, 4) + "****" + value.slice(-4)
    : "未配置";
  return (
    <Field label={label}>
      <div className="flex items-center gap-2">
        <div className="flex-1 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 font-mono text-sm text-gray-500">
          {visible ? value || "未配置" : masked}
        </div>
        <button
          onClick={() => setVisible(!visible)}
          className="rounded-md border border-gray-200 p-2 text-gray-400 transition-colors hover:bg-gray-50 hover:text-gray-600"
        >
          {visible ? (
            <EyeOff className="h-4 w-4" />
          ) : (
            <Eye className="h-4 w-4" />
          )}
        </button>
      </div>
    </Field>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function SettingsPage() {
  const { t } = useI18n();
  // Claude API config
  const [claudeMode, setClaudeMode] = useState("api");
  const [claudeApiKey, setClaudeApiKey] = useState("");
  const [claudeBaseUrl, setClaudeBaseUrl] = useState(
    "https://api.anthropic.com",
  );
  const [claudeModel, setClaudeModel] = useState("claude-sonnet-4-20250514");

  // Pipeline config
  const [crawlInterval, setCrawlInterval] = useState("60");
  const [maxConcurrent, setMaxConcurrent] = useState("3");
  const [autoApproveThreshold, setAutoApproveThreshold] = useState("0.8");
  const [maxRetries, setMaxRetries] = useState("3");
  const [retryDelay, setRetryDelay] = useState("30");

  // Data source config
  const [redditClientId, setRedditClientId] = useState("");
  const [redditClientSecret, setRedditClientSecret] = useState("");
  const [enabledSources, setEnabledSources] = useState({
    reddit: true,
    producthunt: true,
    twitter: false,
    hackernews: true,
  });

  // Publish config
  const [googlePlayKeyPath, setGooglePlayKeyPath] = useState("");
  const [appStoreKeyPath, setAppStoreKeyPath] = useState("");
  const [huaweiKeyPath, setHuaweiKeyPath] = useState("");

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    // Simulate save
    await new Promise((r) => setTimeout(r, 800));
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  const toggleSource = (key: string) => {
    setEnabledSources((prev) => ({
      ...prev,
      [key]: !prev[key as keyof typeof prev],
    }));
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Settings className="h-6 w-6 text-gray-500" />
          <h1 className="text-2xl font-semibold text-gray-900">{t("settings.title")}</h1>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700 disabled:opacity-50"
        >
          <Save className="h-4 w-4" />
          {saving ? "保存中..." : saved ? "已保存" : "保存配置"}
        </button>
      </div>

      {/* Claude API */}
      <Section title="Claude API 配置" icon={Key}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="模式">
            <div className="flex gap-3">
              <button
                onClick={() => setClaudeMode("api")}
                className={`flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
                  claudeMode === "api"
                    ? "border-blue-500 bg-blue-50 text-blue-700"
                    : "border-gray-200 text-gray-600 hover:bg-gray-50"
                }`}
              >
                <Server className="h-4 w-4" />
                API
              </button>
              <button
                onClick={() => setClaudeMode("local")}
                className={`flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
                  claudeMode === "local"
                    ? "border-blue-500 bg-blue-50 text-blue-700"
                    : "border-gray-200 text-gray-600 hover:bg-gray-50"
                }`}
              >
                <Monitor className="h-4 w-4" />
                Local
              </button>
            </div>
          </Field>

          <Field label="模型">
            <select
              value={claudeModel}
              onChange={(e) => setClaudeModel(e.target.value)}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
              <option value="claude-opus-4-20250514">Claude Opus 4</option>
              <option value="claude-3-5-haiku-20241022">
                Claude 3.5 Haiku
              </option>
            </select>
          </Field>

          <Field label="API Key">
            <TextInput
              value={claudeApiKey}
              onChange={setClaudeApiKey}
              placeholder="sk-ant-..."
              type="password"
            />
          </Field>

          <Field label="Base URL">
            <TextInput
              value={claudeBaseUrl}
              onChange={setClaudeBaseUrl}
              placeholder="https://api.anthropic.com"
            />
          </Field>
        </div>
      </Section>

      {/* Pipeline config */}
      <Section title="流水线配置" icon={GitBranch}>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="爬取间隔 (分钟)">
            <TextInput
              value={crawlInterval}
              onChange={setCrawlInterval}
              placeholder="60"
            />
          </Field>
          <Field label="最大并发构建">
            <TextInput
              value={maxConcurrent}
              onChange={setMaxConcurrent}
              placeholder="3"
            />
          </Field>
          <Field label="自动审批阈值">
            <TextInput
              value={autoApproveThreshold}
              onChange={setAutoApproveThreshold}
              placeholder="0.8"
            />
          </Field>
          <Field label="最大重试次数">
            <TextInput
              value={maxRetries}
              onChange={setMaxRetries}
              placeholder="3"
            />
          </Field>
          <Field label="重试延迟 (秒)">
            <TextInput
              value={retryDelay}
              onChange={setRetryDelay}
              placeholder="30"
            />
          </Field>
        </div>
      </Section>

      {/* Data sources */}
      <Section title="数据源配置" icon={Globe}>
        <div className="space-y-5">
          {/* Enabled sources */}
          <div>
            <p className="mb-3 text-sm font-medium text-gray-700">
              启用的数据源
            </p>
            <div className="flex flex-wrap gap-3">
              {Object.entries(enabledSources).map(([key, enabled]) => (
                <label
                  key={key}
                  className="flex cursor-pointer items-center gap-2"
                >
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={() => toggleSource(key)}
                    className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-sm text-gray-700">
                    {key === "reddit"
                      ? "Reddit"
                      : key === "producthunt"
                        ? "Product Hunt"
                        : key === "twitter"
                          ? "Twitter"
                          : key === "hackernews"
                            ? "Hacker News"
                            : key}
                  </span>
                </label>
              ))}
            </div>
          </div>

          {/* Reddit credentials */}
          <div className="border-t border-gray-100 pt-4">
            <p className="mb-3 text-sm font-medium text-gray-700">
              Reddit 凭据
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Client ID">
                <TextInput
                  value={redditClientId}
                  onChange={setRedditClientId}
                  placeholder="Reddit Client ID"
                />
              </Field>
              <Field label="Client Secret">
                <TextInput
                  value={redditClientSecret}
                  onChange={setRedditClientSecret}
                  placeholder="Reddit Client Secret"
                  type="password"
                />
              </Field>
            </div>
          </div>
        </div>
      </Section>

      {/* Publish config */}
      <Section title="发布配置" icon={Store}>
        <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-3">
          <Field label="Google Play 凭据路径">
            <TextInput
              value={googlePlayKeyPath}
              onChange={setGooglePlayKeyPath}
              placeholder="/path/to/google-play-key.json"
            />
          </Field>
          <Field label="App Store 凭据路径">
            <TextInput
              value={appStoreKeyPath}
              onChange={setAppStoreKeyPath}
              placeholder="/path/to/appstore-key.p8"
            />
          </Field>
          <Field label="华为应用商店凭据路径">
            <TextInput
              value={huaweiKeyPath}
              onChange={setHuaweiKeyPath}
              placeholder="/path/to/huawei-credentials.json"
            />
          </Field>
        </div>
      </Section>

      {/* Current env display */}
      <Section title="当前环境变量 (只读)" icon={Key}>
        <div className="space-y-3">
          <MaskedField
            label="CLAUDE_API_KEY"
            value="sk-ant-api03-xxxxxxxxxxxxxxxxxxxx"
          />
          <MaskedField
            label="REDDIT_CLIENT_SECRET"
            value="xxxxxxxxxxxxxxxxxxxxxxxx"
          />
          <MaskedField
            label="GOOGLE_PLAY_KEY"
            value="/etc/secrets/gplay.json"
          />
          <MaskedField
            label="APP_STORE_KEY"
            value="/etc/secrets/appstore.p8"
          />
        </div>
      </Section>
    </div>
  );
}
