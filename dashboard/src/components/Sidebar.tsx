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
} from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useI18n } from "@/lib/i18n";

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

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  return (
    <aside
      className={clsx(
        "flex h-full flex-col border-r border-gray-200 bg-white transition-all duration-300 ease-in-out",
        collapsed ? "w-16" : "w-64",
      )}
    >
      {/* Logo + collapse toggle */}
      <div className="flex h-16 items-center border-b border-gray-200 px-3">
        <div className={clsx("flex items-center gap-2.5", collapsed ? "justify-center w-full" : "flex-1 px-2")}>
          <Bot className="h-7 w-7 flex-shrink-0 text-blue-600" />
          <span
            className={clsx(
              "text-lg font-semibold text-gray-900 whitespace-nowrap transition-opacity duration-300",
              collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100",
            )}
          >
            AutoDev
          </span>
        </div>
        <button
          onClick={onToggleCollapse}
          className={clsx(
            "flex-shrink-0 rounded-md p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600",
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
      <nav className="flex-1 space-y-1 px-2 py-4">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? t(item.labelKey) : undefined}
              className={clsx(
                "flex items-center rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                collapsed ? "justify-center" : "gap-3",
                active
                  ? "bg-blue-600 text-white"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900",
              )}
            >
              <Icon
                className={clsx(
                  "h-5 w-5 flex-shrink-0",
                  active ? "text-white" : "text-gray-400",
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

      {/* Language toggle */}
      <div className={clsx("border-t border-gray-200 px-3 py-2", collapsed && "px-2")}>
        <button
          onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
          title={t("common.language")}
          className={clsx(
            "flex w-full items-center rounded-lg px-3 py-2 text-xs text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700",
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
      </div>

      {/* Connection status */}
      <div className={clsx("border-t border-gray-200 px-3 py-3", collapsed && "px-2")}>
        <div className={clsx("flex items-center text-xs", collapsed ? "justify-center" : "gap-2")}>
          {connected ? (
            <>
              <Wifi className="h-3.5 w-3.5 flex-shrink-0 text-emerald-500" />
              <span
                className={clsx(
                  "text-gray-500 whitespace-nowrap transition-opacity duration-300",
                  collapsed ? "opacity-0 w-0 overflow-hidden" : "opacity-100",
                )}
              >
                {t("sidebar.connected")}
              </span>
            </>
          ) : (
            <>
              <WifiOff className="h-3.5 w-3.5 flex-shrink-0 text-red-500" />
              <span
                className={clsx(
                  "text-gray-500 whitespace-nowrap transition-opacity duration-300",
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
