import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { LayoutShell } from "@/components/LayoutShell";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "湍流ZeroDev",
  description: "自动化 Flutter 应用工厂 - 监控仪表盘",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" className={inter.className}>
      <body className="bg-gray-50 dark:bg-[#0a0e27] text-gray-900 dark:text-slate-200 antialiased">
        <LayoutShell>{children}</LayoutShell>
      </body>
    </html>
  );
}
