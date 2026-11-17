import { tokenStore } from './tokenStore';
import type { TokenResponse } from '../types/auth';

// Public, non-secret setting. All privileged calls go through the backend.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly body: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function errorFrom(resp: Response): Promise<ApiError> {
  let message = `Request failed (${resp.status})`;
  let body: Record<string, unknown> = {};
  try {
    body = (await resp.json()) as Record<string, unknown>;
    if (typeof body.detail === 'string') message = body.detail;
    else if (Array.isArray(body.detail)) message = 'Please check the highlighted fields';
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(resp.status, message, body);
}

type SessionListener = (session: TokenResponse | null) => void;
let onSession: SessionListener = () => {};

/** AuthProvider registers here so a silent refresh (or a final failure) updates the UI. */
export function setSessionListener(listener: SessionListener): void {
  onSession = listener;
}

let refreshInFlight: Promise<TokenResponse | null> | null = null;

/**
 * Exchanges the HttpOnly refresh cookie for a new access token. Single-flight: concurrent callers
 * share one request, because the server rotates the refresh token on every use and treats a
 * replayed token as theft.
 */
export function refreshSession(): Promise<TokenResponse | null> {
  refreshInFlight ??= (async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!resp.ok) {
        tokenStore.set(null);
        return null;
      }
      const session = (await resp.json()) as TokenResponse;
      tokenStore.set(session.access_token);
      return session;
    } catch {
      return null; // network error: keep the current token, caller decides
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

/** Authenticated request with one transparent retry after a 401. Returns the raw Response. */
export async function apiRequest(path: string, init: RequestInit = {}): Promise<Response> {
  const send = () => {
    const headers = new Headers(init.headers);
    const token = tokenStore.get();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    // Only JSON string bodies get a JSON content type; FormData must set its own multipart boundary.
    if (typeof init.body === 'string' && !headers.has('Content-Type'))
      headers.set('Content-Type', 'application/json');
    return fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  };

  let resp = await send();
  if (resp.status === 401) {
    const session = await refreshSession();
    if (session) {
      onSession(session);
      resp = await send();
    } else {
      onSession(null); // refresh failed: the session is over
    }
  }
  if (!resp.ok) throw await errorFrom(resp);
  return resp;
}

/** Authenticated JSON request. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const resp = await apiRequest(path, init);
  return resp.status === 204 ? (undefined as T) : ((await resp.json()) as T);
}

/** HTTP helper object providing standard REST verb methods. */
export const http = {
  get: <T>(path: string, init?: RequestInit): Promise<T> =>
    apiFetch<T>(path, { ...init, method: 'GET' }),
  post: <T>(path: string, body?: unknown, init?: RequestInit): Promise<T> =>
    apiFetch<T>(path, {
      ...init,
      method: 'POST',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
    }),
  put: <T>(path: string, body?: unknown, init?: RequestInit): Promise<T> =>
    apiFetch<T>(path, {
      ...init,
      method: 'PUT',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
    }),
  patch: <T>(path: string, body?: unknown, init?: RequestInit): Promise<T> =>
    apiFetch<T>(path, {
      ...init,
      method: 'PATCH',
      body: body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined,
    }),
  delete: <T>(path: string, init?: RequestInit): Promise<T> =>
    apiFetch<T>(path, { ...init, method: 'DELETE' }),
};

export { errorFrom };
