export interface LlmModel {
  alias: string;
  display_name: string;
  provider: string;
  description: string;
  context_window: number;
  capabilities: string[];
  tier: string;
  enabled: boolean;
  available: boolean | null;
  used_by: string[];
}
export interface LlmModels {
  models: LlmModel[];
  config_version: number;
}
export interface LlmTask {
  task: string;
  description: string;
  requires: string[];
  min_context: number;
  effective_alias: string | null;
  source: string | null;
  override_alias: string | null;
  eligible: string[];
}
export interface LlmAgent {
  key: string;
  label: string;
  default_alias: string | null;
  fallback_alias: string | null;
  eligible: string[];
  tasks: LlmTask[];
}
export interface LlmAgents {
  agents: LlmAgent[];
  allow_task_overrides: boolean;
  config_version: number;
}
export interface LlmUsageSummary {
  alias: string;
  agent: string;
  calls: number;
  errors: number;
  fallbacks: number;
  tokens: number;
  cost_usd: string | number | null;
  avg_latency_ms: number | null;
}
export interface LlmTestResult {
  ok: boolean;
  alias: string;
  latency_ms: number | null;
  attempts: number | null;
  error_code: string | null;
}
