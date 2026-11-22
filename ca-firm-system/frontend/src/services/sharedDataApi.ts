import { http } from './http';
import type { ApprovedModuleOutput, ApprovedModuleOutputListOut } from '../types/sharedData';

function base(clientId: string, periodId: string): string {
  return `/clients/${clientId}/periods/${periodId}/shared`;
}

export async function publishAccountingOutput(
  clientId: string,
  periodId: string,
  notes?: string,
): Promise<ApprovedModuleOutput> {
  return http.post<ApprovedModuleOutput>(`${base(clientId, periodId)}/publish-accounting`, {
    notes,
  });
}

export async function listSharedOutputs(
  clientId: string,
  periodId: string,
  module?: string,
): Promise<ApprovedModuleOutputListOut> {
  const query = module ? `?module=${module}` : '';
  return http.get<ApprovedModuleOutputListOut>(`${base(clientId, periodId)}/outputs${query}`);
}

export async function getLatestApprovedAccounting(
  clientId: string,
  periodId: string,
): Promise<ApprovedModuleOutput> {
  return http.get<ApprovedModuleOutput>(`${base(clientId, periodId)}/latest-accounting`);
}

export async function getSharedOutputById(
  clientId: string,
  periodId: string,
  outputId: string,
): Promise<ApprovedModuleOutput> {
  return http.get<ApprovedModuleOutput>(`${base(clientId, periodId)}/outputs/${outputId}`);
}
