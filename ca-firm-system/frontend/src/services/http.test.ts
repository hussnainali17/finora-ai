import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiFetch, setSessionListener } from './http';
import { tokenStore } from './tokenStore';
import { accountant, mockApi } from '../test-utils';

beforeEach(() => tokenStore.set('stale-token'));
afterEach(() => {
  vi.unstubAllGlobals();
  setSessionListener(() => {});
});

describe('apiFetch', () => {
  it('sends the bearer token and parses JSON', async () => {
    const api = mockApi({ 'GET /clients': () => ({ status: 200, body: { items: [] } }) });
    await expect(apiFetch('/clients')).resolves.toEqual({ items: [] });
    expect(new Headers(api.calls[0].init?.headers).get('Authorization')).toBe('Bearer stale-token');
  });

  it('refreshes once on 401 and retries with the new token', async () => {
    let first = true;
    const api = mockApi({
      'GET /clients': () => {
        if (first) {
          first = false;
          return { status: 401 };
        }
        return { status: 200, body: { ok: true } };
      },
      'POST /auth/refresh': () => ({ status: 200, body: accountant }),
    });
    const listener = vi.fn();
    setSessionListener(listener);

    await expect(apiFetch('/clients')).resolves.toEqual({ ok: true });
    expect(tokenStore.get()).toBe('access-1');
    expect(listener).toHaveBeenCalledWith(accountant);
    const retry = api.calls.filter((c) => c.key === 'GET /clients')[1];
    expect(new Headers(retry.init?.headers).get('Authorization')).toBe('Bearer access-1');
  });

  it('shares ONE refresh request between concurrent 401s (refresh tokens rotate)', async () => {
    const api = mockApi({
      'GET /a': () =>
        tokenStore.get() === 'access-1' ? { status: 200, body: 'a' } : { status: 401 },
      'GET /b': () =>
        tokenStore.get() === 'access-1' ? { status: 200, body: 'b' } : { status: 401 },
      'POST /auth/refresh': () => ({ status: 200, body: accountant }),
    });
    const results = await Promise.all([apiFetch('/a'), apiFetch('/b')]);
    expect(results).toEqual(['a', 'b']);
    expect(api.calls.filter((c) => c.key === 'POST /auth/refresh')).toHaveLength(1);
  });

  it('ends the session when the refresh fails', async () => {
    mockApi({
      'GET /clients': () => ({ status: 401, body: { detail: 'expired' } }),
      'POST /auth/refresh': () => ({ status: 401 }),
    });
    const listener = vi.fn();
    setSessionListener(listener);
    await expect(apiFetch('/clients')).rejects.toMatchObject({ status: 401 });
    expect(listener).toHaveBeenCalledWith(null);
    expect(tokenStore.get()).toBeNull();
  });

  it('surfaces server error messages without leaking details', async () => {
    mockApi({ 'GET /clients/x': () => ({ status: 404, body: { detail: 'Client not found' } }) });
    await expect(apiFetch('/clients/x')).rejects.toMatchObject({
      status: 404,
      message: 'Client not found',
    });
  });
});
