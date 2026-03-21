"use client";

import React, { useState, useCallback, useEffect } from "react";
import { usePathname } from "next/navigation";
import { Menu } from "lucide-react";
import { I18nProvider } from "@/lib/i18n";
import { AuthGuard } from "@/components/AuthGuard";
import { Sidebar } from "@/components/Sidebar";

export function LayoutShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  // Restore collapsed state from localStorage
  useEffect(() => {
    const stored = localStorage.getItem("sidebar_collapsed");
    if (stored === "true") setCollapsed(true);
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("sidebar_collapsed", String(next));
      return next;
    });
  }, []);

  const toggleMobile = useCallback(() => {
    setMobileOpen((prev) => !prev);
  }, []);

  const isLoginPage = pathname === "/login";

  return (
    <I18nProvider>
      <AuthGuard>
        {isLoginPage ? (
          <>{children}</>
        ) : (
          <div className="flex h-screen overflow-hidden">
            {/* Mobile overlay */}
            {mobileOpen && (
              <div
                className="fixed inset-0 z-30 bg-black/30 md:hidden"
                onClick={() => setMobileOpen(false)}
              />
            )}

            {/* Sidebar - desktop */}
            <div
              className={`hidden md:flex flex-shrink-0 transition-all duration-300 ease-in-out ${
                collapsed ? "w-16" : "w-64"
              }`}
            >
              <Sidebar
                collapsed={collapsed}
                onToggleCollapse={toggleCollapsed}
              />
            </div>

            {/* Sidebar - mobile */}
            <div
              className={`fixed inset-y-0 left-0 z-40 flex transition-transform duration-300 ease-in-out md:hidden ${
                mobileOpen ? "translate-x-0" : "-translate-x-full"
              }`}
            >
              <Sidebar
                collapsed={false}
                onToggleCollapse={() => setMobileOpen(false)}
              />
            </div>

            {/* Main content */}
            <main className="flex-1 overflow-y-auto p-6">
              {/* Mobile hamburger */}
              <button
                onClick={toggleMobile}
                className="mb-4 flex items-center gap-2 rounded-lg border border-gray-200 bg-white p-2 text-gray-600 shadow-sm md:hidden"
              >
                <Menu className="h-5 w-5" />
              </button>
              {children}
            </main>
          </div>
        )}
      </AuthGuard>
    </I18nProvider>
  );
}
