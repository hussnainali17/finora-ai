import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { login as apiLogin, logout as apiLogout } from '../../services/authApi';
import { refreshSession, setSessionListener } from '../../services/http';
import type { CurrentUser, TokenResponse } from '../../types/auth';

type AuthState =
  { status: 'loading' } | { status: 'anonymous' } | { status: 'authenticated'; user: CurrentUser };

interface AuthContextValue {
  state: AuthState;
  principal: CurrentUser | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** UI convenience only. The backend re-checks every permission on every request. */
  can: (permission: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' });

  const apply = useCallback((session: TokenResponse | null) => {
    setState(session ? { status: 'authenticated', user: session.user } : { status: 'anonymous' });
  }, []);

  useEffect(() => {
    setSessionListener(apply);
    let active = true;
    // Restore the session after a page reload using the HttpOnly refresh cookie.
    void refreshSession().then((session) => {
      if (active) apply(session);
    });
    return () => {
      active = false;
      setSessionListener(() => {});
    };
  }, [apply]);

  const login = useCallback(
    async (email: string, password: string) => apply(await apiLogin(email, password)),
    [apply],
  );

  const logout = useCallback(async () => {
    await apiLogout();
    apply(null);
  }, [apply]);

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      principal: state.status === 'authenticated' ? state.user : null,
      login,
      logout,
      can: (permission) =>
        state.status === 'authenticated' && state.user.permissions.includes(permission),
    }),
    [state, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
