import { http } from './http';
import type { WorkflowRun } from '../types/workflows';

function base(clientId: string, periodId: string): string {
  return `/clients/${clientId}/periods/${periodId}/workflows`;
}

export async function startWorkflow(clientId: string, periodId: string): Promise<WorkflowRun> {
  return http.post<WorkflowRun>(`${base(clientId, periodId)}/`, {});
}

export async function listWorkflows(clientId: string, periodId: string): Promise<WorkflowRun[]> {
  return http.get<WorkflowRun[]>(`${base(clientId, periodId)}/`);
}

export async function getWorkflow(
  clientId: string,
  periodId: string,
  workflowId: string,
): Promise<WorkflowRun> {
  return http.get<WorkflowRun>(`${base(clientId, periodId)}/${workflowId}`);
}

export async function resumeWorkflow(
  clientId: string,
  periodId: string,
  workflowId: string,
): Promise<WorkflowRun> {
  return http.post<WorkflowRun>(`${base(clientId, periodId)}/${workflowId}/resume`, {});
}
