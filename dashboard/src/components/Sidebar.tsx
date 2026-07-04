"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import {
  Bot,
  LayoutDashboard,
  Lightbulb,
  Smartphone,
  Hammer,
  Settings,
  Wifi,
  WifiOff,
  Wrench,
  ChevronLeft,
  ChevronRight,
  Languages,
  LogOut,
  Sun,
  Moon,
} from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useI18n } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";

interface NavItem {
  labelKey: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

const navItems: NavItem[] = [
  { labelKey: "nav.overview", href: "/", icon: LayoutDashboard },
  { labelKey: "nav.demands", href: "/demands", icon: Lightbulb },
  { labelKey: "nav.apps", href: "/apps", icon: Smartphone },
  { labelKey: "nav.revise", href: "/revise", icon: Wrench },
  { labelKey: "nav.builds", href: "/builds", icon: Hammer },
  { labelKey: "nav.settings", href: "/settings", icon: Settings },
];

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export function Sidebar({ collapsed, onToggleCollapse }: SidebarProps) {
  const pathname = usePathname();
  const { connected } = useWebSocket();
  const { t, locale, setLocale } = useI18n();
  const { theme, toggleTheme } = useTheme();

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  return (
    <aside
      className={clsx(
        "flex h-full flex-col border-r border-white/50 dark:border-[#1e2756]/60 bg-white/70 dark:bg-[#0c1130]/80 backdrop-blur-xl transition-all duration-300 ease-in-out",
        collapsed ? "w-16" : "w-64",
      )}
    >
      {/* Logo + collapse toggle */}
      <div className="flex h-16 items-center border-b border-gray-200/70 dark:border-[#1e2756]/70 px-3">
        <div className={clsx("flex items-center gap-2.5", collapsed ? "justify-center w-full" : "flex-1 px-2")}>
          <span className="icon-chip icon-chip-blue h-8 w-8 rounded-lg">
            <Bot className="h-5 w-5" />
          </span>
          <span
            className={clsx(
              "text-lg font-semibold tracking-tight text-gray-900 dark:text-slate-100 whitespace-nowrap transition-opacity duration-300",
              collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100",
            )}
          >
            湍流ZeroDev
          </span>
        </div>
        <button
          onClick={onToggleCollapse}
          className={clsx(
            "flex-shrink-0 rounded-lg p-1.5 text-gray-400 dark:text-slate-500 transition-colors hover:bg-blue-600/8 dark:hover:bg-blue-400/10 hover:text-blue-600 dark:hover:text-blue-300",
            collapsed && "hidden md:flex",
          )}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1.5 px-2.5 py-5">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? t(item.labelKey) : undefined}
              className={clsx(
                "group relative flex items-center rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200",
                collapsed ? "justify-center" : "gap-3",
                active
                  ? "bg-gradient-to-r from-blue-600/12 to-indigo-600/8 text-blue-700 dark:from-blue-500/15 dark:to-indigo-500/10 dark:text-blue-300"
                  : "text-gray-600 dark:text-slate-400 hover:bg-blue-600/5 dark:hover:bg-blue-400/8 hover:text-gray-900 dark:hover:text-slate-100",
              )}
            >
              {active && (
                <span
                  className={clsx(
                    "absolute left-0 top-1/2 -translate-y-1/2 h-5 w-1 rounded-r-full bg-gradient-to-b from-blue-500 to-indigo-500",
                    collapsed && "h-4",
                  )}
                />
              )}
              <Icon
                className={clsx(
                  "h-5 w-5 flex-shrink-0 transition-colors duration-200",
                  active
                    ? "text-blue-600 dark:text-blue-400"
                    : "text-gray-400 dark:text-slate-500 group-hover:text-gray-600 dark:group-hover:text-slate-300",
                )}
              />
              <span
                className={clsx(
                  "whitespace-nowrap transition-opacity duration-300",
                  collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100",
                )}
              >
                {t(item.labelKey)}
              </span>
            </Link>
          );
        })}
      </nav>

      {/* Footer actions: theme / language / logout */}
      <div
        className={clsx(
          "space-y-0.5 border-t border-gray-200/70 dark:border-[#1e2756]/70 px-2.5 py-2.5",
          collapsed && "px-2",
        )}
      >
        <button
          onClick={toggleTheme}
          title={t("common.toggle_theme")}
          className={clsx(
            "flex w-full items-center rounded-lg px-3 py-2 text-xs text-gray-500 dark:text-slate-400 transition-colors hover:bg-blue-600/8 dark:hover:bg-blue-400/10 hover:text-blue-600 dark:hover:text-blue-300",
            collapsed ? "justify-center" : "gap-2",
          )}
        >
          {theme === "light" ? (
            <Moon className="h-4 w-4 flex-shrink-0" />
          ) : (
            <Sun className="h-4 w-4 flex-shrink-0" />
          )}
          <span
            className={clsx(
              "whitespace-nowrap transition-opacity duration-300",
              collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100",
            )}
          >
            {theme === "light" ? t("common.dark_mode") : t("common.light_mode")}
          </span>
        </button>

        <button
          onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
          title={t("common.language")}
          className={clsx(
            "flex w-full items-center rounded-lg px-3 py-2 text-xs text-gray-500 dark:text-slate-400 transition-colors hover:bg-blue-600/8 dark:hover:bg-blue-400/10 hover:text-blue-600 dark:hover:text-blue-300",
            collapsed ? "justify-center" : "gap-2",
          )}
        >
          <Languages className="h-4 w-4 flex-shrink-0" />
          <span
            className={clsx(
              "whitespace-nowrap transition-opacity duration-300",
              collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100",
            )}
          >
            {locale === "zh" ? "English" : "中文"}
          </span>
        </button>

        <button
          onClick={() => {
            localStorage.removeItem("auth");
            window.location.href = "/login";
          }}
          title={t("nav.logout")}
          className={clsx(
            "flex w-full items-center rounded-lg px-3 py-2 text-xs text-gray-500 dark:text-slate-400 transition-colors hover:bg-red-500/8 dark:hover:bg-red-500/12 hover:text-red-600 dark:hover:text-red-400",
            collapsed ? "justify-center" : "gap-2",
          )}
        >
          <LogOut className="h-4 w-4 flex-shrink-0" />
          <span
            className={clsx(
              "whitespace-nowrap transition-opacity duration-300",
              collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100",
            )}
          >
            {t("nav.logout")}
          </span>
        </button>
      </div>

      {/* Connection status */}
      <div className={clsx("border-t border-gray-200/70 dark:border-[#1e2756]/70 px-3 py-3", collapsed && "px-2")}>
        <div className={clsx("flex items-center text-xs", collapsed ? "justify-center" : "gap-2 px-2")}>
          <span className="relative flex h-2 w-2 flex-shrink-0 items-center justify-center">
            {connected && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            )}
            <span
              className={clsx(
                "relative inline-flex h-2 w-2 rounded-full",
                connected ? "bg-emerald-500" : "bg-red-500",
              )}
            />
          </span>
          {connected ? (
            <>
              <Wifi
                className={clsx(
                  "h-3.5 w-3.5 flex-shrink-0 text-emerald-500 transition-opacity duration-300",
                  collapsed && "hidden",
                )}
              />
              <span
                className={clsx(
                  "text-gray-500 dark:text-slate-400 whitespace-nowrap transition-opacity duration-300",
                  collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100",
                )}
              >
                {t("sidebar.connected")}
              </span>
            </>
          ) : (
            <>
              <WifiOff
                className={clsx(
                  "h-3.5 w-3.5 flex-shrink-0 text-red-500 transition-opacity duration-300",
                  collapsed && "hidden",
                )}
              />
              <span
                className={clsx(
                  "text-gray-500 dark:text-slate-400 whitespace-nowrap transition-opacity duration-300",
                  collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100",
                )}
              >
                {t("sidebar.disconnected")}
              </span>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}
