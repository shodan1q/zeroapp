"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n";
import {
  Cpu,
  CheckCircle,
  Code,
  Hammer,
  FlaskConical,
  Rocket,
  Search,
  Languages,
  ArrowRight,
  Lock,
} from "lucide-react";

const STAGES = [
  { key: "login.stage_crawl", icon: Search },
  { key: "login.stage_process", icon: Cpu },
  { key: "login.stage_evaluate", icon: CheckCircle },
  { key: "login.stage_generate", icon: Code },
  { key: "login.stage_build", icon: Hammer },
  { key: "login.stage_test", icon: FlaskConical },
  { key: "login.stage_publish", icon: Rocket },
];

export default function LoginPage() {
  const { t, locale, setLocale } = useI18n();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [mounted, setMounted] = useState(false);
  const [activeNode, setActiveNode] = useState(0);

  useEffect(() => { setMounted(true); }, []);

  // Animate active node cycling
  useEffect(() => {
    const timer = setInterval(() => {
      setActiveNode((prev) => (prev + 1) % STAGES.length);
    }, 1500);
    return () => clearInterval(timer);
  }, []);

  function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    if (username === "admin" && password === "admin123") {
      localStorage.setItem("auth", "true");
      router.replace("/");
    } else {
      setError(t("login.error"));
    }
  }

  if (!mounted) return <div className="min-h-screen" style={{ background: "#06061a" }} />;

  return (
    <>
      <style jsx>{`
        @keyframes gradientShift {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulse-ring {
          0% { transform: scale(1); opacity: 0.6; }
          100% { transform: scale(1.8); opacity: 0; }
        }
        @keyframes orbit1 {
          0% { transform: rotate(0deg) translateX(180px) rotate(0deg); }
          100% { transform: rotate(360deg) translateX(180px) rotate(-360deg); }
        }
        @keyframes orbit2 {
          0% { transform: rotate(120deg) translateX(250px) rotate(-120deg); }
          100% { transform: rotate(480deg) translateX(250px) rotate(-480deg); }
        }
        @keyframes orbit3 {
          0% { transform: rotate(240deg) translateX(140px) rotate(-240deg); }
          100% { transform: rotate(600deg) translateX(140px) rotate(-600deg); }
        }
        @keyframes float-subtle {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-8px); }
        }
        .page-bg {
          background: radial-gradient(ellipse at 20% 50%, #0f1642 0%, #06061a 50%, #06061a 100%);
        }
        .gradient-text {
          background: linear-gradient(135deg, #60a5fa 0%, #a78bfa 50%, #60a5fa 100%);
          background-size: 200% 200%;
          animation: gradientShift 4s ease infinite;
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }
        .fade-in-1 { animation: fadeIn 0.6s ease-out both; }
        .fade-in-2 { animation: fadeIn 0.6s ease-out 0.15s both; }
        .fade-in-3 { animation: fadeIn 0.6s ease-out 0.3s both; }
        .fade-in-4 { animation: fadeIn 0.6s ease-out 0.45s both; }
        .orbit-dot {
          position: absolute;
          border-radius: 50%;
          pointer-events: none;
        }
        .orbit-1 {
          width: 6px; height: 6px;
          background: #3b82f6;
          box-shadow: 0 0 12px #3b82f6;
          animation: orbit1 20s linear infinite;
        }
        .orbit-2 {
          width: 4px; height: 4px;
          background: #8b5cf6;
          box-shadow: 0 0 10px #8b5cf6;
          animation: orbit2 28s linear infinite;
        }
        .orbit-3 {
          width: 5px; height: 5px;
          background: #06b6d4;
          box-shadow: 0 0 10px #06b6d4;
          animation: orbit3 16s linear infinite;
        }
        .node-active {
          box-shadow: 0 0 20px rgba(96, 165, 250, 0.6), 0 0 40px rgba(139, 92, 246, 0.3);
          border-color: rgba(96, 165, 250, 0.7) !important;
          background: rgba(96, 165, 250, 0.15) !important;
        }
        .node-done {
          border-color: rgba(52, 211, 153, 0.5) !important;
          background: rgba(52, 211, 153, 0.08) !important;
        }
        .node-default {
          border-color: rgba(255, 255, 255, 0.08);
          background: rgba(255, 255, 255, 0.03);
        }
        .connector-active {
          background: linear-gradient(90deg, rgba(96, 165, 250, 0.6), rgba(139, 92, 246, 0.6)) !important;
        }
        .input-field {
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.1);
          transition: all 0.3s ease;
        }
        .input-field:focus {
          background: rgba(255, 255, 255, 0.07);
          border-color: rgba(96, 165, 250, 0.5);
          box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.1), 0 0 20px rgba(96, 165, 250, 0.08);
        }
        .btn-login {
          background: linear-gradient(135deg, #3b82f6 0%, #7c3aed 100%);
          transition: all 0.3s ease;
        }
        .btn-login:hover {
          box-shadow: 0 8px 30px rgba(59, 130, 246, 0.35), 0 0 60px rgba(124, 58, 237, 0.15);
          transform: translateY(-1px);
        }
        .btn-login:active { transform: translateY(0); }
      `}</style>

      <div className="page-bg min-h-screen relative overflow-hidden flex flex-col lg:flex-row">

        {/* ── Left: Branding + Animated Workflow ── */}
        <div className="relative flex-1 flex flex-col justify-center items-center px-8 py-12 lg:py-0">

          {/* Orbiting dots background */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none overflow-hidden">
            <div className="relative w-0 h-0">
              <div className="orbit-dot orbit-1" />
              <div className="orbit-dot orbit-2" />
              <div className="orbit-dot orbit-3" />
            </div>
          </div>

          {/* Subtle radial glow */}
          <div className="absolute inset-0 pointer-events-none"
            style={{ background: "radial-gradient(circle at 50% 50%, rgba(59,130,246,0.06) 0%, transparent 60%)" }}
          />

          <div className="relative z-10 max-w-xl w-full">
            {/* Title */}
            <div className="fade-in-1 mb-4">
              <h1 className="gradient-text text-5xl lg:text-6xl xl:text-7xl font-bold tracking-tight leading-none">
                AutoDev
              </h1>
              <h1 className="gradient-text text-5xl lg:text-6xl xl:text-7xl font-bold tracking-tight leading-none">
                Agent
              </h1>
            </div>

            <p className="fade-in-2 text-lg text-blue-200/70 font-medium mb-2">
              {t("login.subtitle")}
            </p>
            <p className="fade-in-2 text-sm text-gray-500 mb-10 max-w-md">
              {t("login.description")}
            </p>

            {/* Workflow -- horizontal animated graph */}
            <div className="fade-in-3">
              <p className="text-[10px] uppercase tracking-[0.2em] text-gray-600 mb-5">
                {t("login.workflow_title")}
              </p>

              <div className="flex items-center gap-0 overflow-x-auto pb-2">
                {STAGES.map((stage, i) => {
                  const Icon = stage.icon;
                  const isActive = i === activeNode;
                  const isDone = i < activeNode;
                  return (
                    <React.Fragment key={stage.key}>
                      <div className="flex flex-col items-center gap-2 flex-shrink-0"
                        style={{ animation: `float-subtle 3s ease-in-out ${i * 0.2}s infinite` }}
                      >
                        <div className={`w-11 h-11 rounded-xl flex items-center justify-center border transition-all duration-500 ${
                          isActive ? "node-active" : isDone ? "node-done" : "node-default"
                        }`}>
                          <Icon className={`w-5 h-5 transition-colors duration-500 ${
                            isActive ? "text-blue-300" : isDone ? "text-emerald-400/70" : "text-gray-600"
                          }`} />
                          {isActive && (
                            <div className="absolute inset-0 rounded-xl border border-blue-400/30"
                              style={{ animation: "pulse-ring 1.5s ease-out infinite" }}
                            />
                          )}
                        </div>
                        <span className={`text-[10px] whitespace-nowrap transition-colors duration-500 ${
                          isActive ? "text-blue-300" : isDone ? "text-emerald-400/60" : "text-gray-600"
                        }`}>
                          {t(stage.key)}
                        </span>
                      </div>
                      {i < STAGES.length - 1 && (
                        <div className={`w-6 xl:w-10 h-[1.5px] mx-0.5 flex-shrink-0 rounded-full transition-all duration-500 ${
                          isDone ? "connector-active" : "bg-white/5"
                        }`} />
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
            </div>

            {/* Stats line */}
            <div className="fade-in-4 flex items-center gap-6 mt-10 text-gray-600 text-xs">
              <span>LangGraph</span>
              <span className="w-1 h-1 rounded-full bg-gray-700" />
              <span>Claude Opus 4.6</span>
              <span className="w-1 h-1 rounded-full bg-gray-700" />
              <span>Flutter 3.7+</span>
            </div>
          </div>
        </div>

        {/* ── Right: Login Panel ── */}
        <div className="relative z-10 flex flex-col justify-center items-center w-full lg:w-[440px] xl:w-[480px] flex-shrink-0 px-8 sm:px-14 py-12 lg:py-0"
          style={{
            background: "linear-gradient(180deg, rgba(15, 15, 40, 0.95) 0%, rgba(6, 6, 26, 0.98) 100%)",
            borderLeft: "1px solid rgba(255,255,255,0.04)",
          }}
        >
          {/* Language toggle */}
          <div className="absolute top-6 right-6">
            <button
              onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-gray-400 border border-white/5 bg-white/3 hover:text-gray-200 hover:border-white/10 transition-all"
            >
              <Languages className="h-3.5 w-3.5" />
              {locale === "zh" ? "EN" : "中文"}
            </button>
          </div>

          <div className="w-full max-w-sm fade-in-3">
            {/* Lock icon */}
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-blue-500/20 to-violet-500/20 border border-white/5 flex items-center justify-center mb-6">
              <Lock className="w-5 h-5 text-blue-400/80" />
            </div>

            <h2 className="text-xl font-semibold text-white mb-1">{t("login.submit")}</h2>
            <p className="text-xs text-gray-500 mb-8">{t("login.subtitle")}</p>

            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="block text-[11px] text-gray-500 mb-1.5 uppercase tracking-wider font-medium">
                  {t("login.username")}
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => { setUsername(e.target.value); setError(""); }}
                  className="input-field w-full rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-600 outline-none"
                  placeholder="admin"
                  autoComplete="username"
                />
              </div>
              <div>
                <label className="block text-[11px] text-gray-500 mb-1.5 uppercase tracking-wider font-medium">
                  {t("login.password")}
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => { setPassword(e.target.value); setError(""); }}
                  className="input-field w-full rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-600 outline-none"
                  placeholder="********"
                  autoComplete="current-password"
                />
              </div>
              {error && (
                <p className="text-red-400/80 text-xs">{error}</p>
              )}
              <button
                type="submit"
                className="btn-login w-full rounded-lg py-2.5 text-sm font-semibold text-white flex items-center justify-center gap-2 mt-2"
              >
                {t("login.submit")}
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>

            <p className="mt-16 text-center text-[10px] text-gray-700">
              AutoDev Agent v0.1
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
