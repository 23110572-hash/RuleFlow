import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, Firm, RegisterIn, Session, tokenStore, User } from "./api";

type AuthCtx = {
  user: User | null;
  firm: Firm | null;
  dataSource: Session["data_source"];
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (body: RegisterIn) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
};

const Ctx = createContext<AuthCtx>({} as AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [firm, setFirm] = useState<Firm | null>(null);
  const [dataSource, setDataSource] = useState<Session["data_source"]>(null);
  const [loading, setLoading] = useState(true);

  const apply = (s: Session) => {
    tokenStore.set(s.token);
    setUser(s.user);
    setFirm(s.firm);
    setDataSource(s.data_source);
  };

  useEffect(() => {
    (async () => {
      if (tokenStore.get()) {
        try {
          const s = await api.me();
          setUser(s.user);
          setFirm(s.firm);
          setDataSource(s.data_source);
        } catch {
          tokenStore.clear();
        }
      }
      setLoading(false);
    })();
  }, []);

  const login = async (email: string, password: string) => apply(await api.login(email, password));
  const register = async (body: RegisterIn) => apply(await api.register(body));
  const refresh = async () => {
    const s = await api.me();
    setUser(s.user);
    setFirm(s.firm);
    setDataSource(s.data_source);
  };
  const logout = () => {
    tokenStore.clear();
    setUser(null);
    setFirm(null);
    setDataSource(null);
  };

  return (
    <Ctx.Provider value={{ user, firm, dataSource, loading, login, register, logout, refresh }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);

// Compatibility helper for pages that only need the active firm.
export const useFirm = () => {
  const { firm } = useAuth();
  return { firm, firmId: firm?.id ?? null };
};
