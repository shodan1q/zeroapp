import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { LayoutShell } from "@/components/LayoutShell";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "AutoDev Agent",
  description: "Monitoring dashboard for the automated app development pipeline",
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
