"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";

export type AuthUser = {
  id: string;
  name: string;
  email: string;
  case_id: string | null;
  created_at: string;
};

type AuthContextValue = {
  user: AuthUser | null;
  loading: boolean;
  signup: (name: string, email: string, password: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  updateUser: (updates: Partial<Pick<AuthUser, "case_id" | "name">>) => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/** The session lives in an httpOnly cookie set by /api/auth/{signup,login}, so it travels with
 * every request automatically and there is no token for this code to hold or hand out. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const authenticate = useCallback(
    async (path: string, body: unknown, fallbackError: string) => {
      const res = await fetch(path, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail ?? fallbackError);
      }
      setUser((await res.json()) as AuthUser);
    },
    [],
  );

  const logout = useCallback(() => {
    setUser(null);
    void fetch("/api/auth/logout", { method: "POST" });
  }, []);

  // Restore the session on mount: whether the cookie is still valid is the server's call.
  useEffect(() => {
    let cancelled = false;
    fetch("/api/auth/me")
      .then((res) => (res.ok ? res.json() : null))
      .then((u: AuthUser | null) => {
        if (!cancelled && u) setUser(u);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const signup = useCallback(
    (name: string, email: string, password: string) =>
      authenticate("/api/auth/signup", { name, email, password }, "Signup failed"),
    [authenticate],
  );

  const login = useCallback(
    (email: string, password: string) =>
      authenticate("/api/auth/login", { email, password }, "Invalid email or password"),
    [authenticate],
  );

  const updateUser = useCallback(
    async (updates: Partial<Pick<AuthUser, "case_id" | "name">>) => {
      const res = await fetch("/api/auth/me", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(updates),
      });
      if (!res.ok) throw new Error(`Update failed: ${res.status}`);
      setUser((await res.json()) as AuthUser);
    },
    [],
  );

  const value = useMemo(
    () => ({ user, loading, signup, login, logout, updateUser }),
    [user, loading, signup, login, logout, updateUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
