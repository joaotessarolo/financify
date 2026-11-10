"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ApiError, apiFetch } from "@/lib/api";

type User = { id: string; email: string; first_name: string; last_name: string; currency: string; timezone: string };
type Session = { user: User | null; loading: boolean; logout: () => Promise<void> };

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<User>("/api/v1/users/me/")
      .then(setUser)
      .catch((error) => {
        if (error instanceof ApiError && [401, 403].includes(error.status)) router.replace("/login");
      })
      .finally(() => setLoading(false));
  }, [router]);

  async function logout() {
    try {
      await apiFetch<void>("/api/v1/auth/logout/", { method: "POST" });
    } finally {
      setUser(null);
      router.replace("/login");
      router.refresh();
    }
  }

  return <SessionContext.Provider value={{ user, loading, logout }}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider");
  return context;
}
