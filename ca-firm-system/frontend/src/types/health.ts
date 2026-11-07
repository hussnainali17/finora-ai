export interface DependencyResult {
  name: string;
  ok: boolean;
  latency_ms: number;
  detail?: string | null;
}

export interface ReadinessResponse {
  status: 'ok' | 'degraded';
  dependencies: DependencyResult[];
}
