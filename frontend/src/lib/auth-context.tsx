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

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type AuthUser = {
  id: string;
  name: string;
  email: string;
  case_id: string | null;
  created_at: string;
};

type AuthContextValue = {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  signup: (name: string, email: string, password: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  updateUser: (updates: Partial<Pick<AuthUser, "case_id" | "name">>) => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = "ilera_token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const persist = useCallback((t: string, u: AuthUser) => {
    localStorage.setItem(TOKEN_KEY, t);
    setToken(t);
    setUser(u);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  // On mount, try to restore session from localStorage
  useEffect(() => {
    let cancelled = false;
    const stored = localStorage.getItem(TOKEN_KEY);
    if (!stored) {
      // Use microtask to avoid synchronous setState in effect
      queueMicrotask(() => { if (!cancelled) setLoading(false); });
      return () => { cancelled = true; };
    }
    fetch(`${BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${stored}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("expired");
        return res.json();
      })
      .then((u: AuthUser) => {
        if (!cancelled) {
          setToken(stored);
          setUser(u);
        }
      })
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const signup = useCallback(
    async (name: string, email: string, password: string) => {
      const res = await fetch(`${BASE}/api/auth/signup`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, email, password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? "Signup failed");
      }
      const data = await res.json();
      persist(data.token, data.user);
    },
    [persist],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await fetch(`${BASE}/api/auth/login`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? "Invalid email or password");
      }
      const data = await res.json();
      persist(data.token, data.user);
    },
    [persist],
  );

  const updateUser = useCallback(
    async (updates: Partial<Pick<AuthUser, "case_id" | "name">>) => {
      // Fall back to storage so a caller that signs up and updates in the same
      // tick still sees a token (state hasn't re-rendered into this closure yet).
      const active = token ?? localStorage.getItem(TOKEN_KEY);
      if (!active) return;
      const res = await fetch(`${BASE}/api/auth/me`, {
        method: "PATCH",
        headers: {
          "content-type": "application/json",
          Authorization: `Bearer ${active}`,
        },
        body: JSON.stringify(updates),
      });
      if (res.ok) {
        const u = await res.json();
        setUser(u);
      }
    },
    [token],
  );

  const value = useMemo(
    () => ({ user, token, loading, signup, login, logout, updateUser }),
    [user, token, loading, signup, login, logout, updateUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
