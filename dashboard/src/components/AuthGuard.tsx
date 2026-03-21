"use client";
import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const auth = localStorage.getItem("auth");
    if (auth === "true") {
      setAuthed(true);
      if (pathname === "/login") router.replace("/");
    } else {
      setAuthed(false);
      if (pathname !== "/login") router.replace("/login");
    }
  }, [pathname, router]);

  if (authed === null) return null;
  if (!authed && pathname !== "/login") return null;
  if (authed && pathname === "/login") return null;

  return <>{children}</>;
}
