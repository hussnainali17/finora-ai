import type { LlmAgents, LlmModels, LlmTestResult, LlmUsageSummary } from '../types/llm';
import { apiFetch } from './http';

const json = (method: string, body: unknown): RequestInit => ({
  method,
  body: JSON.stringify(body),
});

export const listModels = () => apiFetch<LlmModels>('/llm/models');
export const setModelEnabled = (alias: string, enabled: boolean) =>
  apiFetch<{ config_version: number }>(`/llm/models/${alias}/enabled`, json('PUT', { enabled }));
export const testModel = (alias: string) =>
  apiFetch<LlmTestResult>(`/llm/models/${alias}/test`, { method: 'POST' });
export const getAgents = () => apiFetch<LlmAgents>('/llm/agents');
export const setAgentConfig = (
  agent: string,
  default_alias: string,
  fallback_alias: string | null,
) =>
  apiFetch<{ config_version: number }>(
    `/llm/agents/${agent}`,
    json('PUT', { default_alias, fallback_alias }),
  );
export const setTaskOverride = (agent: string, task: string, alias: string) =>
  apiFetch<{ config_version: number }>(
    `/llm/agents/${agent}/tasks/${task}`,
    json('PUT', { alias }),
  );
export const clearTaskOverride = (agent: string, task: string) =>
  apiFetch<{ config_version: number }>(`/llm/agents/${agent}/tasks/${task}`, {
    method: 'DELETE',
  });
export const setPolicy = (allow_task_overrides: boolean) =>
  apiFetch<{ config_version: number }>('/llm/policy', json('PUT', { allow_task_overrides }));
export const usageSummary = () => apiFetch<LlmUsageSummary[]>('/llm/usage/summary');
