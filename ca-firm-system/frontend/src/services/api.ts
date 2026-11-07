import type { ReadinessResponse } from '../types/health';

// Public, non-secret setting. All privileged calls go through the backend.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export async function fetchReadiness(signal?: AbortSignal): Promise<ReadinessResponse> {
  const resp = await fetch(`${API_BASE_URL}/health/ready`, { signal });
  // The backend returns 503 with a valid body when a dependency is down.
  if (resp.status !== 200 && resp.status !== 503) {
    throw new Error(`Unexpected response: ${resp.status}`);
  }
  return (await resp.json()) as ReadinessResponse;
}
