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
  GitBranch,
  Settings,
  Wifi,
  WifiOff,
  Wrench,
} from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

const navItems: NavItem[] = [
  { label: "概览", href: "/", icon: LayoutDashboard },
  { label: "需求管理", href: "/demands", icon: Lightbulb },
  { label: "应用管理", href: "/apps", icon: Smartphone },
  { label: "修改完善", href: "/revise", icon: Wrench },
  { label: "构建日志", href: "/builds", icon: Hammer },
  { label: "流水线", href: "/pipeline", icon: GitBranch },
  { label: "设置", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { connected } = useWebSocket();

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  }

  return (
    <aside className="flex h-full w-64 flex-col border-r border-gray-200 bg-white">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2.5 border-b border-gray-200 px-5">
        <Bot className="h-7 w-7 text-blue-600" />
        <span className="text-lg font-semibold text-gray-900">AutoDev</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                active
                  ? "bg-blue-600 text-white"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              )}
            >
              <Icon
                className={clsx("h-5 w-5", active ? "text-white" : "text-gray-400")}
              />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Connection status */}
      <div className="border-t border-gray-200 px-4 py-3">
        <div className="flex items-center gap-2 text-xs">
          {connected ? (
            <>
              <Wifi className="h-3.5 w-3.5 text-emerald-500" />
              <span className="text-gray-500">实时连接正常</span>
            </>
          ) : (
            <>
              <WifiOff className="h-3.5 w-3.5 text-red-500" />
              <span className="text-gray-500">连接已断开</span>
            </>
          )}
        </div>
      </div>
    </aside>
  );
}
