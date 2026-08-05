"use client";

import { useState, useEffect } from "react";
import {
  Settings,
  Key,
  GitBranch,
  Globe,
  Store,
  Eye,
  EyeOff,
  Save,
  Smartphone,
  Sparkles,
  Check,
} from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { fetchSettings, saveSettings, fetchLlmProviders, LlmProviderSpec } from "@/lib/api";

/* ------------------------------------------------------------------ */
/*  Static fallback registry (used when the backend is unreachable)    */
/* ------------------------------------------------------------------ */

const FALLBACK_PROVIDERS: LlmProviderSpec[] = [
  {
    id: "claude",
    label: "Claude (Anthropic)",
    description: "官方 Anthropic SDK，支持 API Key 或 Pro/Max 订阅 OAuth Token",
    kind: "anthropic",
    defaultModel: "claude-opus-4-8",
    suggestedModels: ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5"],
    defaultBaseUrl: "",
    requiresApiKey: true,
    keyHint: "sk-ant-... 或 claude setup-token 生成的订阅 token",
  },
  {
    id: "openai",
    label: "OpenAI (GPT)",
    description: "OpenAI 官方 API，GPT 系列模型",
    kind: "openai_compat",
    defaultModel: "gpt-5.1",
    suggestedModels: ["gpt-5.1", "gpt-5", "gpt-4.1", "gpt-4o"],
    defaultBaseUrl: "https://api.openai.com/v1",
    requiresApiKey: true,
    keyHint: "sk-...",
  },
  {
    id: "relay",
    label: "中转站 (OpenAI 兼容)",
    description:
      "第三方 API 中转/聚合服务，走 OpenAI 兼容端点。Base URL 与模型名由服务商决定，配置后用 `zerodev llm probe` 拉取可用模型列表确认。",
    kind: "openai_compat",
    // Deliberately blank: a relay's endpoint and model aliases are site-specific,
    // so a guessed default would point the key somewhere the user never chose.
    defaultModel: "",
    suggestedModels: [],
    defaultBaseUrl: "",
    requiresApiKey: true,
    keyHint: "中转站控制台签发的 key，通常不是 sk-proj- 开头的官方格式",
  },
  {
    id: "gemini",
    label: "Google Gemini",
    description: "Google AI Studio，走官方 OpenAI 兼容端点",
    kind: "openai_compat",
    defaultModel: "gemini-2.5-pro",
    suggestedModels: ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-3-pro-preview"],
    defaultBaseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    requiresApiKey: true,
    keyHint: "AI Studio API Key",
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    description: "深度求索官方 API",
    kind: "openai_compat",
    defaultModel: "deepseek-chat",
    suggestedModels: ["deepseek-chat", "deepseek-reasoner"],
    defaultBaseUrl: "https://api.deepseek.com/v1",
    requiresApiKey: true,
    keyHint: "platform.deepseek.com",
  },
  {
    id: "qwen",
    label: "通义千问 (Qwen)",
    description: "阿里云百炼 DashScope，OpenAI 兼容模式",
    kind: "openai_compat",
    defaultModel: "qwen-max",
    suggestedModels: ["qwen-max", "qwen-plus", "qwen-turbo", "qwen3-coder-plus"],
    defaultBaseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    requiresApiKey: true,
    keyHint: "bailian.console.aliyun.com",
  },
  {
    id: "zhipu",
    label: "智谱 GLM",
    description: "智谱开放平台 GLM 系列",
    kind: "openai_compat",
    defaultModel: "glm-4.6",
    suggestedModels: ["glm-4.6", "glm-4.5", "glm-4-plus"],
    defaultBaseUrl: "https://open.bigmodel.cn/api/paas/v4",
    requiresApiKey: true,
    keyHint: "open.bigmodel.cn",
  },
  {
    id: "moonshot",
    label: "月之暗面 Kimi",
    description: "Moonshot 开放平台 Kimi 系列",
    kind: "openai_compat",
    defaultModel: "kimi-k2-turbo-preview",
    suggestedModels: ["kimi-k2-turbo-preview", "kimi-k2-0905-preview", "moonshot-v1-32k"],
    defaultBaseUrl: "https://api.moonshot.cn/v1",
    requiresApiKey: true,
    keyHint: "platform.moonshot.cn",
  },
  {
    id: "ollama",
    label: "Ollama (本地)",
    description: "本地 Ollama 服务，无需 API Key，数据不出本机",
    kind: "openai_compat",
    defaultModel: "llama3.1",
    suggestedModels: ["llama3.1", "qwen3", "deepseek-r1", "gemma3"],
    defaultBaseUrl: "http://localhost:11434/v1",
    requiresApiKey: false,
    keyHint: "",
  },
];

const PROVIDER_CHIP: Record<string, { initials: string; gradient: string }> = {
  claude: { initials: "CL", gradient: "from-orange-400 to-amber-600" },
  openai: { initials: "GP", gradient: "from-emerald-400 to-teal-600" },
  relay: { initials: "RL", gradient: "from-rose-400 to-pink-600" },
  gemini: { initials: "GM", gradient: "from-sky-400 to-blue-600" },
  deepseek: { initials: "DS", gradient: "from-indigo-400 to-violet-600" },
  qwen: { initials: "QW", gradient: "from-purple-400 to-fuchsia-600" },
  zhipu: { initials: "GL", gradient: "from-cyan-400 to-sky-600" },
  moonshot: { initials: "KM", gradient: "from-slate-500 to-slate-700" },
  ollama: { initials: "OL", gradient: "from-lime-500 to-green-600" },
};

/* ------------------------------------------------------------------ */
/*  Section wrapper                                                    */
/* ------------------------------------------------------------------ */

function Section({
  title,
  icon: Icon,
  chip = "icon-chip-blue",
  description,
  children,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  chip?: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="glass fade-in-up">
      <div className="flex items-center gap-3 border-b border-gray-100 dark:border-[#1e2756] px-5 py-4">
        <div className={`icon-chip ${chip} h-8 w-8 rounded-lg`}>
          <Icon className="h-4 w-4" />
        </div>
        <div>
          <h2 className="section-title">{title}</h2>
          {description && (
            <p className="text-xs text-gray-500 dark:text-slate-400">{description}</p>
          )}
        </div>
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
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="field-label">{label}</label>
      {children}
      {hint && <p className="mt-1 text-xs text-gray-400 dark:text-slate-500">{hint}</p>}
    </div>
  );
}

function TextInput({
  value,
  onChange,
  placeholder,
  type = "text",
  readOnly = false,
  list,
}: {
  value: string;
  onChange?: (v: string) => void;
  placeholder?: string;
  type?: string;
  readOnly?: boolean;
  list?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
      onFocus={() => {
        // Backend masks stored secrets as "****xxxx"; clear the mask on focus
        // so typing a new secret never appends to the masked placeholder.
        if (type === "password" && value.startsWith("*")) onChange?.("");
      }}
      placeholder={placeholder}
      readOnly={readOnly}
      list={list}
      className={`input ${readOnly ? "cursor-not-allowed opacity-60" : ""}`}
    />
  );
}

function MaskedField({ label, value }: { label: string; value: string }) {
  const [visible, setVisible] = useState(false);
  const { t } = useI18n();
  const masked = value
    ? value.startsWith("*")
      ? value // already masked by the backend ("****xxxx"), show as-is
      : value.slice(0, 4) + "****" + value.slice(-4)
    : t("settings.not_configured");
  return (
    <Field label={label}>
      <div className="flex items-center gap-2">
        <div className="input flex-1 cursor-default font-mono text-gray-500 dark:text-slate-400">
          {visible ? value || t("settings.not_configured") : masked}
        </div>
        <button
          onClick={() => setVisible(!visible)}
          className="btn btn-ghost btn-sm h-9 w-9 p-0"
          aria-label="toggle visibility"
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
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

  // AI provider selection
  const [providers, setProviders] = useState<LlmProviderSpec[]>(FALLBACK_PROVIDERS);
  const [llmProvider, setLlmProvider] = useState("claude");
  // Flat per-provider config values keyed like the backend settings file:
  // openaiApiKey / openaiModel / openaiBaseUrl / geminiApiKey / ...
  const [providerCfg, setProviderCfg] = useState<Record<string, string>>({});

  // Claude API config (dedicated fields: dual auth)
  const [claudeOauthToken, setClaudeOauthToken] = useState("");
  const [claudeApiKey, setClaudeApiKey] = useState("");
  const [claudeBaseUrl, setClaudeBaseUrl] = useState("");
  const [claudeModel, setClaudeModel] = useState("claude-opus-4-8");

  // Build targets
  const [targetPlatforms, setTargetPlatforms] = useState<string[]>(["android"]);

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

  // Output / GitHub config
  const [outputDir, setOutputDir] = useState("/Users/shodan/project/zerodev");
  const [githubOrg, setGithubOrg] = useState("zerogenerate");

  // Publish config
  const [googlePlayKeyPath, setGooglePlayKeyPath] = useState("");
  const [appStoreKeyPath, setAppStoreKeyPath] = useState("");
  const [huaweiKeyPath, setHuaweiKeyPath] = useState("");
  const [huaweiAgcClientId, setHuaweiAgcClientId] = useState("");
  const [huaweiAgcClientSecret, setHuaweiAgcClientSecret] = useState("");
  const [huaweiAgcAppId, setHuaweiAgcAppId] = useState("");

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load settings + provider registry from backend on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [data, registry] = await Promise.all([fetchSettings(), fetchLlmProviders()]);
        if (cancelled) return;
        if (registry.providers.length > 0) setProviders(registry.providers);
        if (!data || Object.keys(data).length === 0) {
          // Backend unreachable (fetchSettings returns {} on failure). Block
          // saving so we never overwrite data/settings.json with empty values.
          setLoadFailed(true);
          setError("无法加载设置，请确认后端已启动后刷新重试");
          setLoading(false);
          return;
        }
        setLoadFailed(false);
        if (data.llmProvider !== undefined) setLlmProvider(String(data.llmProvider));
        // Collect flat per-provider keys (openaiApiKey, qwenModel, ...)
        const cfg: Record<string, string> = {};
        const ids = (registry.providers.length > 0 ? registry.providers : FALLBACK_PROVIDERS).map(
          (p) => p.id,
        );
        for (const id of ids) {
          if (id === "claude") continue;
          for (const suffix of ["ApiKey", "Model", "BaseUrl"]) {
            const key = `${id}${suffix}`;
            if (data[key] !== undefined) cfg[key] = String(data[key]);
          }
        }
        setProviderCfg(cfg);
        if (data.claudeOauthToken !== undefined) setClaudeOauthToken(String(data.claudeOauthToken));
        if (data.claudeApiKey !== undefined) setClaudeApiKey(String(data.claudeApiKey));
        if (data.claudeBaseUrl !== undefined) setClaudeBaseUrl(String(data.claudeBaseUrl));
        if (data.claudeModel !== undefined) setClaudeModel(String(data.claudeModel));
        if (Array.isArray(data.targetPlatforms)) setTargetPlatforms(data.targetPlatforms.map(String));
        if (data.crawlInterval !== undefined) setCrawlInterval(String(data.crawlInterval));
        if (data.maxConcurrent !== undefined) setMaxConcurrent(String(data.maxConcurrent));
        if (data.autoApproveThreshold !== undefined) setAutoApproveThreshold(String(data.autoApproveThreshold));
        if (data.maxRetries !== undefined) setMaxRetries(String(data.maxRetries));
        if (data.retryDelay !== undefined) setRetryDelay(String(data.retryDelay));
        if (data.redditClientId !== undefined) setRedditClientId(String(data.redditClientId));
        if (data.redditClientSecret !== undefined) setRedditClientSecret(String(data.redditClientSecret));
        if (data.enabledSources && typeof data.enabledSources === "object") {
          setEnabledSources(data.enabledSources as typeof enabledSources);
        }
        if (data.outputDir !== undefined) setOutputDir(String(data.outputDir));
        if (data.githubOrg !== undefined) setGithubOrg(String(data.githubOrg));
        if (data.googlePlayKeyPath !== undefined) setGooglePlayKeyPath(String(data.googlePlayKeyPath));
        if (data.appStoreKeyPath !== undefined) setAppStoreKeyPath(String(data.appStoreKeyPath));
        if (data.huaweiKeyPath !== undefined) setHuaweiKeyPath(String(data.huaweiKeyPath));
        if (data.huaweiAgcClientId !== undefined) setHuaweiAgcClientId(String(data.huaweiAgcClientId));
        if (data.huaweiAgcClientSecret !== undefined) setHuaweiAgcClientSecret(String(data.huaweiAgcClientSecret));
        if (data.huaweiAgcAppId !== undefined) setHuaweiAgcAppId(String(data.huaweiAgcAppId));
      } catch (err) {
        console.warn("Failed to load settings:", err);
        if (!cancelled) {
          setLoadFailed(true);
          setError("无法加载设置，请确认后端已启动后刷新重试");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const setCfg = (key: string, value: string) =>
    setProviderCfg((prev) => ({ ...prev, [key]: value }));

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const payload = {
        llmProvider,
        claudeOauthToken,
        claudeApiKey,
        claudeModel,
        claudeBaseUrl,
        ...providerCfg,
        targetPlatforms,
        crawlInterval,
        maxConcurrent,
        autoApproveThreshold,
        maxRetries,
        retryDelay,
        enabledSources,
        redditClientId,
        redditClientSecret,
        outputDir,
        githubOrg,
        googlePlayKeyPath,
        appStoreKeyPath,
        huaweiKeyPath,
        huaweiAgcClientId,
        huaweiAgcClientSecret,
        huaweiAgcAppId,
      };
      const result = await saveSettings(payload);
      if (result) {
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      } else {
        setError("Failed to save settings.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  const toggleSource = (key: string) => {
    setEnabledSources((prev) => ({
      ...prev,
      [key]: !prev[key as keyof typeof prev],
    }));
  };

  const activeSpec =
    providers.find((p) => p.id === llmProvider) ?? providers[0] ?? FALLBACK_PROVIDERS[0];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-sm text-gray-500 dark:text-slate-400">Loading settings...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <Settings className="h-6 w-6 text-blue-500" />
            {t("settings.title")}
          </h1>
        </div>
        <div className="flex items-center gap-3">
          {error && (
            <span className="text-sm text-red-600 dark:text-red-400">{error}</span>
          )}
          <button onClick={handleSave} disabled={saving || loadFailed} className="btn btn-primary">
            <Save className="h-4 w-4" />
            {saving ? t("settings.saving") : saved ? t("settings.saved") : t("settings.save")}
          </button>
        </div>
      </div>

      {/* AI providers */}
      <Section
        title={t("settings.ai_config")}
        icon={Sparkles}
        chip="icon-chip-purple"
        description={t("settings.ai_provider_desc")}
      >
        {/* Provider cards */}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {providers.map((p) => {
            const active = p.id === llmProvider;
            const chip = PROVIDER_CHIP[p.id] ?? { initials: p.id.slice(0, 2).toUpperCase(), gradient: "from-gray-400 to-gray-600" };
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => setLlmProvider(p.id)}
                className={`relative flex items-start gap-3 rounded-xl border p-3 text-left transition-all duration-150 ${
                  active
                    ? "border-blue-500/60 bg-blue-50/70 dark:bg-blue-900/20 shadow-[0_0_0_3px_rgb(59_130_246/0.12)]"
                    : "border-gray-200/70 dark:border-[#1e2756] hover:border-blue-300 dark:hover:border-blue-800 hover:bg-white/50 dark:hover:bg-[#161d45]/50"
                }`}
              >
                <span
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br text-[11px] font-bold text-white shadow-sm ${chip.gradient}`}
                >
                  {chip.initials}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-gray-800 dark:text-slate-200">
                    {p.label}
                  </span>
                  <span className="mt-0.5 block text-xs leading-snug text-gray-500 dark:text-slate-400 line-clamp-2">
                    {p.description}
                  </span>
                </span>
                {active && (
                  <span className="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-blue-500 text-white">
                    <Check className="h-3 w-3" />
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Per-provider credentials */}
        <div className="mt-5 border-t border-gray-100 dark:border-[#1e2756] pt-5">
          <p className="mb-4 flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-slate-300">
            <span className="badge-info">{t("settings.current_provider")}</span>
            {activeSpec.label}
          </p>

          {llmProvider === "claude" ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("settings.oauth_token")} hint="claude setup-token 生成，订阅内零额外成本">
                <TextInput
                  value={claudeOauthToken}
                  onChange={setClaudeOauthToken}
                  placeholder="sk-ant-oat..."
                  type="password"
                />
              </Field>
              <Field label={t("settings.provider_model")}>
                <TextInput
                  value={claudeModel}
                  onChange={setClaudeModel}
                  list="models-claude"
                  placeholder={activeSpec.defaultModel}
                />
              </Field>
              <Field label={t("settings.api_key")} hint={activeSpec.keyHint}>
                <TextInput
                  value={claudeApiKey}
                  onChange={setClaudeApiKey}
                  placeholder="sk-ant-..."
                  type="password"
                />
              </Field>
              <Field label={t("settings.base_url")}>
                <TextInput
                  value={claudeBaseUrl}
                  onChange={setClaudeBaseUrl}
                  placeholder="https://api.anthropic.com"
                />
              </Field>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {activeSpec.requiresApiKey ? (
                <Field label={t("settings.provider_api_key")} hint={activeSpec.keyHint}>
                  <TextInput
                    value={providerCfg[`${llmProvider}ApiKey`] ?? ""}
                    onChange={(v) => setCfg(`${llmProvider}ApiKey`, v)}
                    placeholder="API Key"
                    type="password"
                  />
                </Field>
              ) : (
                <Field label={t("settings.provider_api_key")}>
                  <div className="input flex cursor-default items-center text-gray-400 dark:text-slate-500">
                    {t("settings.no_key_required")}
                  </div>
                </Field>
              )}
              <Field label={t("settings.provider_model")}>
                <TextInput
                  value={providerCfg[`${llmProvider}Model`] ?? activeSpec.defaultModel}
                  onChange={(v) => setCfg(`${llmProvider}Model`, v)}
                  list={`models-${llmProvider}`}
                  placeholder={activeSpec.defaultModel || "由服务商决定，必填"}
                />
              </Field>
              <Field label={t("settings.provider_base_url")}>
                <TextInput
                  value={providerCfg[`${llmProvider}BaseUrl`] ?? activeSpec.defaultBaseUrl}
                  onChange={(v) => setCfg(`${llmProvider}BaseUrl`, v)}
                  placeholder={activeSpec.defaultBaseUrl || "https://your-relay.example.com/v1"}
                />
              </Field>
            </div>
          )}

          {/* Model suggestions for every provider */}
          {providers.map((p) => (
            <datalist key={p.id} id={`models-${p.id}`}>
              {p.suggestedModels.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          ))}
        </div>
      </Section>

      {/* Build targets */}
      <Section title={t("settings.platforms_config")} icon={Smartphone} chip="icon-chip-green">
        <Field label={t("settings.target_platforms")}>
          <div className="flex flex-wrap gap-3">
            {(["android", "ios", "ohos"] as const).map((p) => {
              const active = targetPlatforms.includes(p);
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() =>
                    setTargetPlatforms((prev) =>
                      prev.includes(p)
                        ? prev.filter((x) => x !== p)
                        : [...prev, p],
                    )
                  }
                  className={`btn ${active ? "btn-primary" : "btn-secondary"}`}
                >
                  {active && <Check className="h-4 w-4" />}
                  {t(`settings.platform_${p}`)}
                </button>
              );
            })}
          </div>
        </Field>
      </Section>

      {/* Pipeline config */}
      <Section title={t("settings.pipeline_config")} icon={GitBranch} chip="icon-chip-blue">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label={t("settings.crawl_interval")}>
            <TextInput value={crawlInterval} onChange={setCrawlInterval} placeholder="60" />
          </Field>
          <Field label={t("settings.max_concurrent")}>
            <TextInput value={maxConcurrent} onChange={setMaxConcurrent} placeholder="3" />
          </Field>
          <Field label={t("settings.auto_approve")}>
            <TextInput value={autoApproveThreshold} onChange={setAutoApproveThreshold} placeholder="0.8" />
          </Field>
          <Field label={t("settings.max_retries")}>
            <TextInput value={maxRetries} onChange={setMaxRetries} placeholder="3" />
          </Field>
          <Field label={t("settings.retry_delay")}>
            <TextInput value={retryDelay} onChange={setRetryDelay} placeholder="30" />
          </Field>
        </div>
      </Section>

      {/* Data sources */}
      <Section title={t("settings.datasource_config")} icon={Globe} chip="icon-chip-amber">
        <div className="space-y-5">
          {/* Enabled sources */}
          <div>
            <p className="mb-3 text-sm font-medium text-gray-700 dark:text-slate-300">
              {t("settings.enabled_sources")}
            </p>
            <div className="flex flex-wrap gap-3">
              {Object.entries(enabledSources).map(([key, enabled]) => (
                <label key={key} className="flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={() => toggleSource(key)}
                    className="h-4 w-4 rounded border-gray-300 dark:border-[#1e2756] text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-sm text-gray-700 dark:text-slate-300">
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
          <div className="border-t border-gray-100 dark:border-[#1e2756] pt-4">
            <p className="mb-3 text-sm font-medium text-gray-700 dark:text-slate-300">
              {t("settings.reddit_credentials")}
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

      {/* Output / GitHub config */}
      <Section title={t("settings.output_config")} icon={GitBranch} chip="icon-chip-slate">
        <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-2">
          <Field label={t("settings.output_dir")}>
            <TextInput value={outputDir} onChange={setOutputDir} placeholder="/path/to/output" />
          </Field>
          <Field label={t("settings.github_org")}>
            <TextInput value={githubOrg} onChange={setGithubOrg} placeholder="zerogenerate" />
          </Field>
        </div>
      </Section>

      {/* Publish config */}
      <Section title={t("settings.publish_config")} icon={Store} chip="icon-chip-rose">
        <div className="grid gap-4 sm:grid-cols-1 lg:grid-cols-3">
          <Field label={t("settings.gplay_path")}>
            <TextInput
              value={googlePlayKeyPath}
              onChange={setGooglePlayKeyPath}
              placeholder="/path/to/google-play-key.json"
            />
          </Field>
          <Field label={t("settings.appstore_path")}>
            <TextInput
              value={appStoreKeyPath}
              onChange={setAppStoreKeyPath}
              placeholder="/path/to/appstore-key.p8"
            />
          </Field>
          <Field label={t("settings.huawei_path")}>
            <TextInput
              value={huaweiKeyPath}
              onChange={setHuaweiKeyPath}
              placeholder="/path/to/huawei-credentials.json"
            />
          </Field>
          <Field label={t("settings.agc_client_id")}>
            <TextInput
              value={huaweiAgcClientId}
              onChange={setHuaweiAgcClientId}
              placeholder="AppGallery Connect client ID"
            />
          </Field>
          <Field label={t("settings.agc_client_secret")}>
            <TextInput
              value={huaweiAgcClientSecret}
              onChange={setHuaweiAgcClientSecret}
              placeholder="AppGallery Connect client secret"
              type="password"
            />
          </Field>
          <Field label={t("settings.agc_app_id")}>
            <TextInput
              value={huaweiAgcAppId}
              onChange={setHuaweiAgcAppId}
              placeholder="HarmonyOS App ID"
            />
          </Field>
        </div>
      </Section>

      {/* Current env display */}
      <Section title={t("settings.env_vars")} icon={Key} chip="icon-chip-slate">
        <div className="space-y-3">
          <MaskedField label="CLAUDE_OAUTH_TOKEN" value={claudeOauthToken} />
          <MaskedField label="CLAUDE_API_KEY" value={claudeApiKey} />
          <MaskedField label="REDDIT_CLIENT_SECRET" value={redditClientSecret} />
          <MaskedField label="GOOGLE_PLAY_KEY" value={googlePlayKeyPath} />
          <MaskedField label="APP_STORE_KEY" value={appStoreKeyPath} />
          <MaskedField label="HUAWEI_AGC_CLIENT_SECRET" value={huaweiAgcClientSecret} />
        </div>
      </Section>
    </div>
  );
}
