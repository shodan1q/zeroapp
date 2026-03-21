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

  useEffect(() => {
    setMounted(true);
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

  return (
    <>
      <style jsx>{`
        @keyframes float1 {
          0%, 100% { transform: translateY(0px) translateX(0px); }
          25% { transform: translateY(-30px) translateX(10px); }
          50% { transform: translateY(-10px) translateX(-15px); }
          75% { transform: translateY(-25px) translateX(5px); }
        }
        @keyframes float2 {
          0%, 100% { transform: translateY(0px) translateX(0px) rotate(0deg); }
          33% { transform: translateY(-20px) translateX(-20px) rotate(120deg); }
          66% { transform: translateY(10px) translateX(15px) rotate(240deg); }
        }
        @keyframes float3 {
          0%, 100% { transform: translateY(0px) scale(1); }
          50% { transform: translateY(-40px) scale(1.1); }
        }
        @keyframes gradientShift {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }
        @keyframes fadeInUp {
          from { opacity: 0; transform: translateY(30px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes fadeInScale {
          from { opacity: 0; transform: scale(0.95); }
          to { opacity: 1; transform: scale(1); }
        }
        @keyframes nodeGlow {
          0%, 14% { box-shadow: 0 0 5px rgba(59,130,246,0.2); border-color: rgba(255,255,255,0.1); }
          7% { box-shadow: 0 0 20px rgba(59,130,246,0.8), 0 0 40px rgba(139,92,246,0.4); border-color: rgba(59,130,246,0.6); }
        }
        @keyframes flowDot {
          0% { left: 0%; opacity: 0; }
          5% { opacity: 1; }
          95% { opacity: 1; }
          100% { left: 100%; opacity: 0; }
        }
        @keyframes gridPulse {
          0%, 100% { opacity: 0.03; }
          50% { opacity: 0.08; }
        }
        @keyframes borderGlow {
          0%, 100% { border-color: rgba(59,130,246,0.2); }
          50% { border-color: rgba(139,92,246,0.4); }
        }
        .login-bg {
          background: #0a0a1a;
        }
        .gradient-text {
          background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 50%, #3b82f6 100%);
          background-size: 200% 200%;
          animation: gradientShift 4s ease infinite;
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }
        .hero-section {
          animation: fadeInUp 0.8s ease-out both;
        }
        .workflow-section {
          animation: fadeInUp 0.8s ease-out 0.2s both;
        }
        .login-card {
          animation: fadeInScale 0.8s ease-out 0.4s both;
        }
        .glass-card {
          background: rgba(255, 255, 255, 0.05);
          backdrop-filter: blur(24px);
          -webkit-backdrop-filter: blur(24px);
          border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .node-0 { animation: nodeGlow 8s ease-in-out infinite 0s; }
        .node-1 { animation: nodeGlow 8s ease-in-out infinite 1.14s; }
        .node-2 { animation: nodeGlow 8s ease-in-out infinite 2.28s; }
        .node-3 { animation: nodeGlow 8s ease-in-out infinite 3.42s; }
        .node-4 { animation: nodeGlow 8s ease-in-out infinite 4.56s; }
        .node-5 { animation: nodeGlow 8s ease-in-out infinite 5.7s; }
        .node-6 { animation: nodeGlow 8s ease-in-out infinite 6.84s; }
        .connector-dot {
          position: absolute;
          top: 50%;
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: linear-gradient(135deg, #3b82f6, #8b5cf6);
          transform: translateY(-50%);
          animation: flowDot 8s linear infinite;
        }
        .connector-dot-v {
          position: absolute;
          left: 50%;
          width: 4px;
          height: 4px;
          border-radius: 50%;
          background: linear-gradient(135deg, #3b82f6, #8b5cf6);
          transform: translateX(-50%);
          animation: flowDotV 8s linear infinite;
        }
        @keyframes flowDotV {
          0% { top: 0%; opacity: 0; }
          5% { opacity: 1; }
          95% { opacity: 1; }
          100% { top: 100%; opacity: 0; }
        }
        .dot-0 { animation-delay: 0s; }
        .dot-1 { animation-delay: 1.14s; }
        .dot-2 { animation-delay: 2.28s; }
        .dot-3 { animation-delay: 3.42s; }
        .dot-4 { animation-delay: 4.56s; }
        .dot-5 { animation-delay: 5.7s; }
        .grid-bg {
          background-image:
            linear-gradient(rgba(59,130,246,0.05) 1px, transparent 1px),
            linear-gradient(90deg, rgba(59,130,246,0.05) 1px, transparent 1px);
          background-size: 60px 60px;
          animation: gridPulse 6s ease-in-out infinite;
        }
        .floating-shape {
          position: absolute;
          border-radius: 50%;
          pointer-events: none;
        }
        .shape-1 {
          width: 300px;
          height: 300px;
          background: radial-gradient(circle, rgba(59,130,246,0.15) 0%, transparent 70%);
          top: 10%;
          left: 5%;
          animation: float1 12s ease-in-out infinite;
        }
        .shape-2 {
          width: 200px;
          height: 200px;
          background: radial-gradient(circle, rgba(139,92,246,0.12) 0%, transparent 70%);
          top: 60%;
          right: 10%;
          animation: float2 15s ease-in-out infinite;
        }
        .shape-3 {
          width: 150px;
          height: 150px;
          background: radial-gradient(circle, rgba(59,130,246,0.1) 0%, transparent 70%);
          bottom: 15%;
          left: 30%;
          animation: float3 10s ease-in-out infinite;
        }
        .shape-4 {
          width: 250px;
          height: 250px;
          background: radial-gradient(circle, rgba(139,92,246,0.08) 0%, transparent 70%);
          top: 5%;
          right: 25%;
          animation: float1 18s ease-in-out infinite reverse;
        }
        .shape-5 {
          width: 180px;
          height: 180px;
          background: radial-gradient(circle, rgba(59,130,246,0.06) 0%, transparent 70%);
          top: 40%;
          left: 60%;
          animation: float2 13s ease-in-out infinite reverse;
        }
        .input-glow:focus {
          box-shadow: 0 0 0 2px rgba(59,130,246,0.4), 0 0 20px rgba(59,130,246,0.15);
          border-color: rgba(59,130,246,0.6);
        }
        .btn-gradient {
          background: linear-gradient(135deg, #3b82f6, #8b5cf6);
          transition: all 0.3s ease;
        }
        .btn-gradient:hover {
          transform: scale(1.02);
          box-shadow: 0 0 30px rgba(59,130,246,0.4), 0 0 60px rgba(139,92,246,0.2);
        }
        .btn-gradient:active {
          transform: scale(0.98);
        }
        .gradient-line {
          background: linear-gradient(90deg, transparent, rgba(59,130,246,0.3), rgba(139,92,246,0.3), transparent);
        }
      `}</style>

      <div className="login-bg min-h-screen relative overflow-hidden flex">
        {/* Animated grid background */}
        <div className="grid-bg absolute inset-0 z-0" />
        {/* Floating shapes */}
        <div className="floating-shape shape-1" />
        <div className="floating-shape shape-2" />
        <div className="floating-shape shape-3" />
        <div className="floating-shape shape-4" />
        <div className="floating-shape shape-5" />
        {/* Gradient overlay */}
        <div className="absolute inset-0 z-0 pointer-events-none"
          style={{
            background: "radial-gradient(ellipse at 30% 50%, rgba(59,130,246,0.1) 0%, transparent 60%), radial-gradient(ellipse at 70% 50%, rgba(139,92,246,0.08) 0%, transparent 60%)"
          }}
        />

        {/* ── Left side: Branding + Workflow ── */}
        <div className="relative z-10 hidden lg:flex flex-col justify-center items-center flex-1 px-12">
          {mounted && (
            <div className="hero-section text-center max-w-lg">
              <h1 className="gradient-text text-6xl xl:text-7xl font-bold tracking-tight mb-6">
                {t("login.title")}
              </h1>
              <p className="text-xl text-blue-200/80 font-medium mb-3">
                {t("login.subtitle")}
              </p>
              <p className="text-sm text-gray-400 leading-relaxed mb-12">
                {t("login.description")}
              </p>

              {/* Workflow Visualization -- vertical */}
              <div className="workflow-section">
                <h2 className="text-xs uppercase tracking-widest text-gray-500 mb-8">
                  {t("login.workflow_title")}
                </h2>
                <div className="flex flex-col items-start gap-0 mx-auto w-fit">
                  {STAGES.map((stage, i) => {
                    const Icon = stage.icon;
                    return (
                      <React.Fragment key={stage.key}>
                        <div className="flex items-center gap-4">
                          <div
                            className={`node-${i} w-12 h-12 rounded-xl glass-card flex items-center justify-center transition-all duration-300`}
                          >
                            <Icon className="w-5 h-5 text-blue-400/80" />
                          </div>
                          <div className="text-left">
                            <span className="text-sm text-gray-300 font-medium">
                              {t(stage.key)}
                            </span>
                          </div>
                        </div>
                        {i < STAGES.length - 1 && (
                          <div className="ml-[23px] relative w-[2px] h-8 overflow-hidden"
                            style={{
                              background: "linear-gradient(180deg, rgba(59,130,246,0.3), rgba(139,92,246,0.3))"
                            }}
                          >
                            <div className={`connector-dot-v dot-${i}`} />
                          </div>
                        )}
                      </React.Fragment>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── Right side: Login form ── */}
        <div className="relative z-10 flex flex-col justify-center items-center w-full lg:w-[480px] lg:flex-shrink-0 px-6 sm:px-12 py-8"
          style={{ background: "rgba(10, 10, 26, 0.6)", backdropFilter: "blur(40px)" }}
        >
          {/* Language toggle */}
          <div className="absolute top-6 right-6 z-20">
            <button
              onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
              className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-gray-300 transition-colors glass-card hover:text-white"
            >
              <Languages className="h-4 w-4" />
              {locale === "zh" ? "EN" : "中文"}
            </button>
          </div>

          {/* Mobile hero (shows on small screens where left side is hidden) */}
          {mounted && (
            <div className="hero-section text-center mb-8 lg:hidden">
              <h1 className="gradient-text text-4xl font-bold tracking-tight mb-3">
                {t("login.title")}
              </h1>
              <p className="text-sm text-blue-200/80 font-medium mb-1">
                {t("login.subtitle")}
              </p>
              <p className="text-xs text-gray-400">
                {t("login.description")}
              </p>
            </div>
          )}

          {/* Login form */}
          {mounted && (
            <div className="login-card w-full max-w-sm">
              <div className="mb-8 text-center lg:text-left">
                <h2 className="text-2xl font-bold text-white mb-2">{t("login.submit")}</h2>
                <p className="text-sm text-gray-400">{t("login.description")}</p>
              </div>

              <form onSubmit={handleLogin} className="space-y-5">
                <div>
                  <label className="block text-xs text-gray-400 mb-2 uppercase tracking-wider">
                    {t("login.username")}
                  </label>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => { setUsername(e.target.value); setError(""); }}
                    className="input-glow w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder-gray-500 outline-none transition-all duration-300"
                    placeholder={t("login.username")}
                    autoComplete="username"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-2 uppercase tracking-wider">
                    {t("login.password")}
                  </label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => { setPassword(e.target.value); setError(""); }}
                    className="input-glow w-full rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white placeholder-gray-500 outline-none transition-all duration-300"
                    placeholder={t("login.password")}
                    autoComplete="current-password"
                  />
                </div>
                {error && (
                  <p className="text-red-400 text-xs text-center">{error}</p>
                )}
                <button
                  type="submit"
                  className="btn-gradient w-full rounded-xl py-3 text-sm font-semibold text-white"
                >
                  {t("login.submit")}
                </button>
              </form>

              {/* Bottom branding */}
              <p className="mt-12 text-center text-xs text-gray-600">
                AutoDev Agent v0.1 -- Powered by LangGraph + Claude
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
