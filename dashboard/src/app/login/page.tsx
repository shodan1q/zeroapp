"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n";
import {
  Cpu, CheckCircle, Code, Hammer, FlaskConical, Rocket, Search,
  Languages, ArrowRight, Lock,
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
  const [phase, setPhase] = useState<"splash" | "login" | "leaving">("splash");
  const [activeNode, setActiveNode] = useState(0);

  useEffect(() => { setMounted(true); }, []);

  // Phase transition: splash (centered) -> login (split)
  useEffect(() => {
    if (!mounted) return;
    const timer = setTimeout(() => setPhase("login"), 2200);
    return () => clearTimeout(timer);
  }, [mounted]);

  // Node cycling
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
      setPhase("leaving");
      setTimeout(() => router.replace("/"), 800);
    } else {
      setError(t("login.error"));
    }
  }

  if (!mounted) return <div className="min-h-screen" style={{ background: "#06061a" }} />;

  const isLogin = phase === "login";

  return (
    <>
      <style jsx>{`
        @keyframes gradientShift {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }
        @keyframes fadeInUp {
          from { opacity: 0; transform: translateY(24px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes fadeInRight {
          from { opacity: 0; transform: translateX(60px); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes pulse-ring {
          0% { transform: scale(1); opacity: 0.5; }
          100% { transform: scale(1.6); opacity: 0; }
        }
        @keyframes float-subtle {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-6px); }
        }
        @keyframes scan-beam {
          0% { top: -2px; opacity: 0; }
          5% { opacity: 1; }
          95% { opacity: 0.6; }
          100% { top: 100%; opacity: 0; }
        }
        @keyframes gridPulse {
          0%, 100% { opacity: 0.02; }
          50% { opacity: 0.06; }
        }
        .page-bg {
          background: radial-gradient(ellipse at 30% 40%, #0f1642 0%, #06061a 60%);
        }
        .gradient-text {
          background: linear-gradient(135deg, #60a5fa 0%, #a78bfa 50%, #60a5fa 100%);
          background-size: 200% 200%;
          animation: gradientShift 4s ease infinite;
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }
        .grid-bg {
          background-image:
            linear-gradient(rgba(59,130,246,0.04) 1px, transparent 1px),
            linear-gradient(90deg, rgba(59,130,246,0.04) 1px, transparent 1px);
          background-size: 50px 50px;
          animation: gridPulse 6s ease-in-out infinite;
        }
        .scan-beam {
          position: absolute; left: 0; right: 0; height: 2px; z-index: 60;
          background: linear-gradient(90deg, transparent 0%, rgba(96,165,250,0.9) 30%, rgba(167,139,250,0.9) 70%, transparent 100%);
          box-shadow: 0 0 20px rgba(96,165,250,0.5), 0 0 60px rgba(167,139,250,0.3);
          animation: scan-beam 1.8s ease-in-out both;
          pointer-events: none;
        }

        /* Phase transitions -- transform-based for smooth animation */
        .brand-wrapper {
          position: absolute;
          inset: 0;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: transform 1.2s cubic-bezier(0.4, 0, 0.2, 1),
                      padding 1.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .brand-wrapper-centered {
          transform: translateX(0);
          padding: 2rem;
        }
        .brand-wrapper-left {
          transform: translateX(-15%);
          padding: 2rem 3rem;
        }
        .brand-inner {
          transition: all 1.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .brand-inner-centered {
          text-align: center;
          max-width: 600px;
        }
        .brand-inner-left {
          text-align: left;
          max-width: 520px;
        }
        .brand-title {
          transition: font-size 1.2s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .title-big { font-size: 4rem; }
        .title-small { font-size: 2.6rem; }
        .login-panel {
          position: absolute;
          right: 0; top: 0; bottom: 0;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          overflow: hidden;
          transition: width 1.2s cubic-bezier(0.4, 0, 0.2, 1),
                      opacity 0.8s ease 0.4s;
        }
        .login-hidden {
          width: 0;
          opacity: 0;
        }
        .login-visible {
          width: 420px;
          opacity: 1;
        }

        .node-active {
          box-shadow: 0 0 16px rgba(96, 165, 250, 0.6), 0 0 32px rgba(139, 92, 246, 0.25);
          border-color: rgba(96, 165, 250, 0.7) !important;
          background: rgba(96, 165, 250, 0.15) !important;
        }
        .node-done {
          border-color: rgba(52, 211, 153, 0.4) !important;
          background: rgba(52, 211, 153, 0.06) !important;
        }
        .node-default {
          border-color: rgba(255, 255, 255, 0.06);
          background: rgba(255, 255, 255, 0.02);
        }
        .connector-active {
          background: linear-gradient(90deg, rgba(96, 165, 250, 0.5), rgba(139, 92, 246, 0.5)) !important;
        }
        .input-field {
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.08);
          transition: all 0.3s ease;
        }
        .input-field:focus {
          background: rgba(255, 255, 255, 0.07);
          border-color: rgba(96, 165, 250, 0.5);
          box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.08);
        }
        .btn-login {
          background: linear-gradient(135deg, #3b82f6 0%, #7c3aed 100%);
          transition: all 0.3s ease;
        }
        .btn-login:hover {
          box-shadow: 0 6px 24px rgba(59, 130, 246, 0.3);
          transform: translateY(-1px);
        }
        /* Leaving transition */
        .page-leaving {
          animation: pageLeave 0.8s cubic-bezier(0.4, 0, 0.2, 1) forwards;
        }
        @keyframes pageLeave {
          0% { opacity: 1; transform: scale(1); filter: blur(0); }
          50% { opacity: 0.6; transform: scale(1.02); filter: blur(2px); }
          100% { opacity: 0; transform: scale(1.05); filter: blur(8px); }
        }
        /* White flash overlay */
        .flash-overlay {
          position: fixed; inset: 0; z-index: 100; pointer-events: none;
          background: radial-gradient(circle at center, rgba(96,165,250,0.3), rgba(6,6,26,1));
          animation: flashIn 0.8s ease-out forwards;
        }
        @keyframes flashIn {
          0% { opacity: 0; }
          20% { opacity: 0.8; }
          100% { opacity: 1; }
        }
      `}</style>

      <div className={`page-bg min-h-screen relative overflow-hidden flex flex-row ${phase === "leaving" ? "page-leaving" : ""}`}>
        {/* Flash overlay on leaving */}
        {phase === "leaving" && <div className="flash-overlay" />}
        {/* Grid background */}
        <div className="grid-bg absolute inset-0 z-0" />
        {/* Scan beam on entrance */}
        <div className="scan-beam" />
        {/* Radial glow */}
        <div className="absolute inset-0 z-0 pointer-events-none"
          style={{ background: "radial-gradient(circle at 40% 50%, rgba(59,130,246,0.07) 0%, transparent 50%)" }}
        />

        {/* ── Brand / Content Section ── */}
        <div className={`brand-wrapper z-10 ${isLogin ? "brand-wrapper-left" : "brand-wrapper-centered"}`}>
          <div className={`brand-inner ${isLogin ? "brand-inner-left" : "brand-inner-centered"}`}>
            {/* Title */}
            <h1 className={`gradient-text brand-title font-bold tracking-tight leading-tight mb-3 ${
              isLogin ? "title-small" : "title-big"
            }`}
              style={{ animation: "fadeInUp 0.6s ease-out both" }}
            >
              ZeroDev Agent
            </h1>

            <p className="text-blue-200/70 font-medium mb-1"
              style={{
                animation: "fadeInUp 0.6s ease-out 0.15s both",
                fontSize: isLogin ? "0.875rem" : "1.125rem",
                transition: "font-size 1s ease",
              }}
            >
              {t("login.subtitle")}
            </p>
            <p className="text-gray-500 text-sm mb-6"
              style={{ animation: "fadeInUp 0.6s ease-out 0.3s both" }}
            >
              {t("login.description")}
            </p>

            {/* Workflow */}
            <div style={{ animation: "fadeInUp 0.6s ease-out 0.5s both" }}>
              <p className="text-[10px] uppercase tracking-[0.2em] text-gray-600 mb-3">
                {t("login.workflow_title")}
              </p>
              <div className={`flex items-center gap-0 ${isLogin ? "" : "justify-center"}`}
                style={{ transition: "all 1.2s cubic-bezier(0.4, 0, 0.2, 1)" }}
              >
                {STAGES.map((stage, i) => {
                  const Icon = stage.icon;
                  const isAct = i === activeNode;
                  const isDone = i < activeNode;
                  return (
                    <React.Fragment key={stage.key}>
                      <div className="flex flex-col items-center gap-1 flex-shrink-0 relative"
                        style={{ animation: `float-subtle 3s ease-in-out ${i * 0.15}s infinite` }}
                      >
                        <div className={`w-9 h-9 rounded-lg flex items-center justify-center border transition-all duration-500 ${
                          isAct ? "node-active" : isDone ? "node-done" : "node-default"
                        }`}>
                          <Icon className={`w-4 h-4 transition-colors duration-500 ${
                            isAct ? "text-blue-300" : isDone ? "text-emerald-400/60" : "text-gray-600"
                          }`} />
                          {isAct && (
                            <div className="absolute inset-0 rounded-lg border border-blue-400/20"
                              style={{ animation: "pulse-ring 1.5s ease-out infinite" }}
                            />
                          )}
                        </div>
                        <span className={`text-[8px] whitespace-nowrap transition-colors duration-500 ${
                          isAct ? "text-blue-300" : isDone ? "text-emerald-400/50" : "text-gray-600"
                        }`}>
                          {t(stage.key)}
                        </span>
                      </div>
                      {i < STAGES.length - 1 && (
                        <div className={`w-4 xl:w-6 h-[1px] mx-0.5 flex-shrink-0 transition-all duration-500 ${
                          isDone ? "connector-active" : "bg-white/5"
                        }`} />
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
            </div>

            {/* Tech stack */}
            <div className="flex items-center gap-4 mt-5 text-gray-600 text-[10px]"
              style={{ animation: "fadeInUp 0.6s ease-out 0.7s both" }}
            >
              <span>LangGraph</span>
              <span className="w-0.5 h-0.5 rounded-full bg-gray-700" />
              <span>Claude Opus 4.6</span>
              <span className="w-0.5 h-0.5 rounded-full bg-gray-700" />
              <span>Flutter 3.7+</span>
            </div>
          </div>
        </div>

        {/* ── Login Panel (slides in from right) ── */}
        <div className={`login-panel z-20 ${isLogin ? "login-visible" : "login-hidden"}`}
          style={{
            background: "linear-gradient(180deg, rgba(15, 22, 66, 0.55) 0%, rgba(6, 6, 26, 0.7) 100%)",
            backdropFilter: "blur(40px)",
            WebkitBackdropFilter: "blur(40px)",
            borderLeft: isLogin ? "1px solid rgba(96,165,250,0.08)" : "none",
          }}
        >
          {/* Language toggle */}
          {isLogin && (
            <div className="absolute top-5 right-5" style={{ animation: "fadeInUp 0.4s ease-out 0.8s both" }}>
              <button
                onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
                className="flex items-center gap-1 rounded-md px-2 py-1 text-[10px] text-gray-400 border border-white/5 hover:text-gray-200 hover:border-white/10 transition-all"
              >
                <Languages className="h-3 w-3" />
                {locale === "zh" ? "EN" : "中文"}
              </button>
            </div>
          )}

          {isLogin && (
            <div className="w-full max-w-xs" style={{ animation: "fadeInRight 0.8s ease-out 0.3s both" }}>
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500/15 to-violet-500/15 border border-white/5 flex items-center justify-center mb-5">
                <Lock className="w-4 h-4 text-blue-400/70" />
              </div>

              <h2 className="text-lg font-semibold text-white mb-0.5">{t("login.submit")}</h2>
              <p className="text-[11px] text-gray-500 mb-6">{t("login.subtitle")}</p>

              <form onSubmit={handleLogin} className="space-y-3.5">
                <div>
                  <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-medium">
                    {t("login.username")}
                  </label>
                  <input
                    type="text" value={username}
                    onChange={(e) => { setUsername(e.target.value); setError(""); }}
                    className="input-field w-full rounded-lg px-3.5 py-2 text-sm text-white placeholder-gray-600 outline-none"
                    placeholder="admin" autoComplete="username"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-gray-500 mb-1 uppercase tracking-wider font-medium">
                    {t("login.password")}
                  </label>
                  <input
                    type="password" value={password}
                    onChange={(e) => { setPassword(e.target.value); setError(""); }}
                    className="input-field w-full rounded-lg px-3.5 py-2 text-sm text-white placeholder-gray-600 outline-none"
                    placeholder="********" autoComplete="current-password"
                  />
                </div>
                {error && <p className="text-red-400/80 text-xs">{error}</p>}
                <button type="submit"
                  className="btn-login w-full rounded-lg py-2.5 text-sm font-semibold text-white flex items-center justify-center gap-2"
                >
                  {t("login.submit")}
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </form>

              <div className="mt-8 rounded-lg border border-white/5 bg-white/3 px-3 py-2 text-center">
                <p className="text-[10px] text-gray-500 mb-0.5">Test Credentials</p>
                <p className="text-[11px] text-gray-400 font-mono">admin / admin123</p>
              </div>

              <p className="mt-6 text-center text-[9px] text-gray-700">
                ZeroDev Agent v0.1
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
