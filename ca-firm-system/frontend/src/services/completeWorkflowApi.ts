import { http } from './http';
import type { MultiModuleWorkflowRun } from '../types/completeWorkflow';

function base(clientId: string, periodId: string): string {
  return `/clients/${clientId}/periods/${periodId}/workflows`;
}

export async function startCompleteWorkflow(
  clientId: string,
  periodId: string,
  taxYear: number = 2025,
): Promise<MultiModuleWorkflowRun> {
  return http.post<MultiModuleWorkflowRun>(
    `${base(clientId, periodId)}/complete/start?tax_year=${taxYear}`,
    {},
  );
}

export async function listCompleteWorkflows(
  clientId: string,
  periodId: string,
): Promise<MultiModuleWorkflowRun[]> {
  return http.get<MultiModuleWorkflowRun[]>(`${base(clientId, periodId)}/complete`);
}

export async function getCompleteWorkflow(
  clientId: string,
  periodId: string,
  runId: string,
): Promise<MultiModuleWorkflowRun> {
  return http.get<MultiModuleWorkflowRun>(`${base(clientId, periodId)}/complete/${runId}`);
}

export async function resumeCompleteWorkflow(
  clientId: string,
  periodId: string,
  runId: string,
  notes?: string,
): Promise<MultiModuleWorkflowRun> {
  return http.post<MultiModuleWorkflowRun>(
    `${base(clientId, periodId)}/complete/${runId}/resume`,
    { notes },
  );
}
