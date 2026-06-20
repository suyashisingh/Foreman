"use client";

/**
 * JWT-based auth context.
 *
 * The token is stored in localStorage.  Note: httpOnly cookies would be more
 * XSS-resistant; localStorage is used here for simplicity in a local-dev tool.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import * as api from "@/lib/api-client";

interface AuthUser {
  id: string;
  email: string;
  name: string | null;
}

interface AuthContextValue {
  token: string | null;
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = "foreman_token";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // Lazy initializer reads localStorage once at mount — no synchronous setState
  // in effects needed for the initial token restore.
  const [token, setToken] = useState<string | null>(() =>
    typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null,
  );
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchUser = useCallback(async (t: string) => {
    try {
      const u = await api.getCurrentUser(t);
      setUser({ id: u.id, email: u.email, name: u.name });
    } catch {
      // Token invalid or expired — clear it
      localStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setUser(null);
    }
  }, []);

  useEffect(() => {
    async function init() {
      const stored = localStorage.getItem(TOKEN_KEY);
      if (stored) {
        await fetchUser(stored);
      }
      setLoading(false);
    }
    void init();
  }, [fetchUser]);

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await api.login(email, password);
    localStorage.setItem(TOKEN_KEY, access_token);
    setToken(access_token);
    const u = await api.getCurrentUser(access_token);
    setUser({ id: u.id, email: u.email, name: u.name });
  }, []);

  const register = useCallback(
    async (email: string, password: string, name?: string) => {
      const { access_token } = await api.register(email, password, name);
      localStorage.setItem(TOKEN_KEY, access_token);
      setToken(access_token);
      const u = await api.getCurrentUser(access_token);
      setUser({ id: u.id, email: u.email, name: u.name });
    },
    [],
  );

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
