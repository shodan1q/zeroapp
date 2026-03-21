"use client";
import React, { createContext, useContext, useState, useCallback } from "react";

type Locale = "zh" | "en";

const translations: Record<Locale, Record<string, string>> = {
  zh: {
    // Sidebar
    "nav.overview": "概览",
    "nav.demands": "需求管理",
    "nav.apps": "应用管理",
    "nav.revise": "修改完善",
    "nav.builds": "构建日志",
    "nav.settings": "设置",

    // Overview
    "overview.title": "概览",
    "overview.refresh": "刷新",
    "overview.total_apps": "总应用数",
    "overview.live_apps": "已上架",
    "overview.developing": "开发中",
    "overview.total_demands": "总需求数",
    "overview.today_builds": "今日构建",
    "overview.pending": "待处理",
    "overview.pipeline_running": "流水线运行中",
    "overview.pipeline_stopped": "流水线已停止",
    "overview.start_pipeline": "启动流水线",
    "overview.stop_pipeline": "停止流水线",
    "overview.custom_gen": "自定义生成",
    "overview.custom_gen_desc": "输入你的 App 主题或需求描述，系统将自动生成完整的 Flutter 应用",
    "overview.custom_gen_placeholder": "例如：一个带有星空动画背景的冥想计时器...",
    "overview.start_gen": "开始生成",
    "overview.recent_demands": "最近需求",
    "overview.recent_builds": "最近构建",
    "overview.activity_log": "活动日志",
    "overview.no_data": "暂无数据",
    "overview.pipeline_control": "流水线控制",
    "overview.cycles": "运行周期",
    "overview.generated": "已生成",
    "overview.pushed": "已推送",
    "overview.errors": "错误",
    "overview.current_task": "当前任务",
    "overview.pipeline_logs": "流水线日志",
    "overview.started_at": "启动于",
    "overview.processing": "处理中...",
    "overview.realtime": "实时",
    "overview.backend_warning": "后端服务未连接，当前显示为空数据。",
    "overview.submitting": "提交中...",
    "overview.pipeline_busy": "流水线运行中，请等待完成后再生成",
    "overview.no_activity": "暂无活动记录",
    "overview.no_logs": "暂无日志记录。启动流水线后将在此显示运行日志。",
    "overview.trigger_single": "触发单次运行",
    "overview.query_pipeline": "查询流水线运行状态",
    "overview.query_placeholder": "输入 Thread ID...",
    "overview.query": "查询",
    "overview.pipeline_stages": "流水线阶段",
    "overview.generated_apps": "已生成应用",
    "overview.pushed_github": "已推送 GitHub",
    "overview.error_count": "错误次数",

    // Pipeline stages
    "stage.idle": "空闲",
    "stage.demand_analysis": "需求分析",
    "stage.code_generation": "代码生成",
    "stage.build": "构建",
    "stage.test": "测试",
    "stage.deploy": "部署",
    "stage.done": "完成",
    "stage.error": "错误",
    "stage.running": "运行中",
    "stage.completed": "已完成",
    "stage.waiting": "等待中",

    // Demands
    "demands.title": "需求管理",
    "demands.all_status": "全部状态",
    "demands.all_source": "全部来源",
    "demands.id": "ID",
    "demands.name": "标题",
    "demands.category": "分类",
    "demands.source": "来源",
    "demands.score": "综合分",
    "demands.trend": "趋势分",
    "demands.status": "状态",
    "demands.time": "时间",
    "demands.actions": "操作",
    "demands.approve": "通过",
    "demands.reject": "拒绝",
    "demands.description": "描述",
    "demands.core_features": "核心功能",
    "demands.target_users": "目标用户",
    "demands.complexity": "复杂度",
    "demands.monetization": "变现方式",
    "demands.competition": "竞争度",
    "demands.feasibility": "可行性",
    "demands.source_link": "需求来源",

    // Apps
    "apps.title": "应用管理",
    "apps.search": "搜索应用...",
    "apps.all_status": "全部状态",
    "apps.generated_apps": "已生成的应用",
    "apps.revise": "修改完善",
    "apps.run_android": "Android",
    "apps.run_ios": "iOS",
    "apps.run_ohos": "HarmonyOS",

    // Builds
    "builds.title": "构建日志",
    "builds.empty": "暂无构建日志。流水线运行后将在此显示。请先在概览页启动流水线。",

    // Settings
    "settings.title": "设置",

    // Revise
    "revise.title": "修改完善",
    "revise.select_app": "选择应用",
    "revise.instruction": "修改指令",
    "revise.instruction_placeholder": "描述你想要修改的内容...",
    "revise.submit": "提交修改",

    // Common
    "common.loading": "加载中...",
    "common.no_data": "暂无数据",
    "common.language": "语言",

    // Sidebar
    "sidebar.connected": "实时连接正常",
    "sidebar.disconnected": "连接已断开",
  },
  en: {
    "nav.overview": "Overview",
    "nav.demands": "Demands",
    "nav.apps": "Apps",
    "nav.revise": "Revise",
    "nav.builds": "Build Logs",
    "nav.settings": "Settings",

    "overview.title": "Overview",
    "overview.refresh": "Refresh",
    "overview.total_apps": "Total Apps",
    "overview.live_apps": "Published",
    "overview.developing": "Developing",
    "overview.total_demands": "Total Demands",
    "overview.today_builds": "Today Builds",
    "overview.pending": "Pending",
    "overview.pipeline_running": "Pipeline Running",
    "overview.pipeline_stopped": "Pipeline Stopped",
    "overview.start_pipeline": "Start Pipeline",
    "overview.stop_pipeline": "Stop Pipeline",
    "overview.custom_gen": "Custom Generation",
    "overview.custom_gen_desc": "Enter your app theme or requirements, the system will generate a complete Flutter app",
    "overview.custom_gen_placeholder": "e.g. A meditation timer with starry sky animations...",
    "overview.start_gen": "Generate",
    "overview.recent_demands": "Recent Demands",
    "overview.recent_builds": "Recent Builds",
    "overview.activity_log": "Activity Log",
    "overview.no_data": "No data",
    "overview.pipeline_control": "Pipeline Control",
    "overview.cycles": "Cycles",
    "overview.generated": "Generated",
    "overview.pushed": "Pushed",
    "overview.errors": "Errors",
    "overview.current_task": "Current Task",
    "overview.pipeline_logs": "Pipeline Logs",
    "overview.started_at": "Started at",
    "overview.processing": "Processing...",
    "overview.realtime": "Realtime",
    "overview.backend_warning": "Backend not connected. Showing empty data.",
    "overview.submitting": "Submitting...",
    "overview.pipeline_busy": "Pipeline running, please wait before generating",
    "overview.no_activity": "No activity yet",
    "overview.no_logs": "No logs yet. Start the pipeline to see logs here.",
    "overview.trigger_single": "Trigger Single Run",
    "overview.query_pipeline": "Query Pipeline Status",
    "overview.query_placeholder": "Enter Thread ID...",
    "overview.query": "Query",
    "overview.pipeline_stages": "Pipeline Stages",
    "overview.generated_apps": "Generated Apps",
    "overview.pushed_github": "Pushed to GitHub",
    "overview.error_count": "Error Count",

    // Pipeline stages
    "stage.idle": "Idle",
    "stage.demand_analysis": "Demand Analysis",
    "stage.code_generation": "Code Gen",
    "stage.build": "Build",
    "stage.test": "Test",
    "stage.deploy": "Deploy",
    "stage.done": "Done",
    "stage.error": "Error",
    "stage.running": "Running",
    "stage.completed": "Completed",
    "stage.waiting": "Waiting",

    "demands.title": "Demand Management",
    "demands.all_status": "All Status",
    "demands.all_source": "All Sources",
    "demands.id": "ID",
    "demands.name": "Title",
    "demands.category": "Category",
    "demands.source": "Source",
    "demands.score": "Score",
    "demands.trend": "Trend",
    "demands.status": "Status",
    "demands.time": "Time",
    "demands.actions": "Actions",
    "demands.approve": "Approve",
    "demands.reject": "Reject",
    "demands.description": "Description",
    "demands.core_features": "Core Features",
    "demands.target_users": "Target Users",
    "demands.complexity": "Complexity",
    "demands.monetization": "Monetization",
    "demands.competition": "Competition",
    "demands.feasibility": "Feasibility",
    "demands.source_link": "Source",

    "apps.title": "App Management",
    "apps.search": "Search apps...",
    "apps.all_status": "All Status",
    "apps.generated_apps": "Generated Apps",
    "apps.revise": "Revise",
    "apps.run_android": "Android",
    "apps.run_ios": "iOS",
    "apps.run_ohos": "HarmonyOS",

    "builds.title": "Build Logs",
    "builds.empty": "No build logs yet. Start the pipeline from the Overview page.",

    "settings.title": "Settings",

    "revise.title": "Revise & Improve",
    "revise.select_app": "Select App",
    "revise.instruction": "Instruction",
    "revise.instruction_placeholder": "Describe what you want to change...",
    "revise.submit": "Submit",

    "common.loading": "Loading...",
    "common.no_data": "No data",
    "common.language": "Language",

    "sidebar.connected": "Connected",
    "sidebar.disconnected": "Disconnected",
  },
};

interface I18nContextType {
  locale: Locale;
  t: (key: string) => string;
  setLocale: (locale: Locale) => void;
}

const I18nContext = createContext<I18nContextType>({
  locale: "zh",
  t: (key) => key,
  setLocale: () => {},
});

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem("locale") as Locale) || "zh";
    }
    return "zh";
  });

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    if (typeof window !== "undefined") {
      localStorage.setItem("locale", l);
    }
  }, []);

  const t = useCallback(
    (key: string) => translations[locale][key] ?? key,
    [locale],
  );

  return (
    <I18nContext.Provider value={{ locale, t, setLocale }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  return useContext(I18nContext);
}
