import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';

function mockFetch(status: number, body: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ status, json: () => Promise.resolve(body) }));
}

afterEach(() => vi.unstubAllGlobals());

describe('App', () => {
  it('shows healthy dependencies', async () => {
    mockFetch(200, {
      status: 'ok',
      dependencies: [{ name: 'postgres', ok: true, latency_ms: 2 }],
    });
    render(<App />);
    expect(await screen.findByText('Overall: ok')).toBeInTheDocument();
    expect(screen.getByText('postgres')).toBeInTheDocument();
  });

  it('shows degraded state with failing dependency', async () => {
    mockFetch(503, {
      status: 'degraded',
      dependencies: [{ name: 'kafka', ok: false, latency_ms: 3, detail: 'OSError' }],
    });
    render(<App />);
    expect(await screen.findByText('Overall: degraded')).toBeInTheDocument();
    expect(screen.getByText('down: OSError')).toBeInTheDocument();
  });

  it('shows an error when the backend is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')));
    render(<App />);
    expect(await screen.findByText(/Backend unreachable: network down/)).toBeInTheDocument();
  });
});
