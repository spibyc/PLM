import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setCsrf, type Me } from "./api";

type AuthState = {
  me: Me | null; loading: boolean;
  login: (u: string, p: string) => Promise<void>; logout: () => Promise<void>;
  can: (perm: string) => boolean;
};
const Ctx = createContext<AuthState>(null as unknown as AuthState);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<Me>("/api/auth/me")
      .then((m) => { setCsrf(m.csrf_token); setMe(m); })
      .catch(() => setMe(null))
      .finally(() => setLoading(false));
    const onExpired = () => setMe(null);
    window.addEventListener("plm:unauthenticated", onExpired);
    return () => window.removeEventListener("plm:unauthenticated", onExpired);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const m = await api<Me>("/api/auth/login", { body: { username, password } });
    setCsrf(m.csrf_token);
    setMe(m);
  }, []);
  const logout = useCallback(async () => {
    try { await api("/api/auth/logout", { method: "POST" }); } finally { setMe(null); }
  }, []);
  const can = useCallback((p: string) => !!me?.permissions.includes(p), [me]);
  return <Ctx.Provider value={{ me, loading, login, logout, can }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
