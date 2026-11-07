import { vi } from 'vitest';
import type { TokenResponse } from './types/auth';

export const accountant: TokenResponse = {
  access_token: 'access-1',
  token_type: 'bearer',
  expires_in: 900,
  user: {
    id: 'u1',
    email: 'sam@firm.example',
    full_name: 'Sam Staff',
    firm_id: 'f1',
    firm_name: 'Acme & Co',
    role: 'accountant',
    permissions: ['client:read', 'period:read'],
  },
};

export type Route = (init?: RequestInit) => { status: number; body?: unknown };

/** Routes fetch() by "METHOD /path-suffix"; unknown routes fail the test loudly. */
export function mockApi(routes: Record<string, Route>) {
  const calls: { key: string; init?: RequestInit }[] = [];
  const fn = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const path = url.replace(/^.*\/api\/v1/, '');
    const key = `${init?.method ?? 'GET'} ${path}`;
    calls.push({ key, init });
    const route = routes[key];
    if (!route) return Promise.reject(new Error(`Unmocked request: ${key}`));
    const { status, body } = route(init);
    return Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
      blob: () => Promise.resolve(new Blob([String(body ?? '')])),
    } as Response);
  });
  vi.stubGlobal('fetch', fn);
  return { calls, fn };
}

export const healthy: Route = () => ({
  status: 200,
  body: { status: 'ok', dependencies: [{ name: 'postgres', ok: true, latency_ms: 2 }] },
});
