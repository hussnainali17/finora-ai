import { http } from './http';
import type {
  AdjustmentCreateIn,
  AdjustmentDecisionIn,
  AdjustmentListOut,
  PeriodAdjustment,
} from '../types/adjustments';

function base(clientId: string, periodId: string): string {
  return `/clients/${clientId}/periods/${periodId}/adjustments`;
}

export async function listAdjustments(
  clientId: string,
  periodId: string,
  params: { status?: string; category?: string; limit?: number; offset?: number } = {},
): Promise<AdjustmentListOut> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined) qs.set(k, String(v));
  });
  const q = qs.toString() ? `?${qs}` : '';
  return http.get<AdjustmentListOut>(`${base(clientId, periodId)}/${q}`);
}

export async function generateAdjustments(
  clientId: string,
  periodId: string,
): Promise<PeriodAdjustment[]> {
  return http.post<PeriodAdjustment[]>(`${base(clientId, periodId)}/generate`, {});
}

export async function createAdjustment(
  clientId: string,
  periodId: string,
  body: AdjustmentCreateIn,
): Promise<PeriodAdjustment> {
  return http.post<PeriodAdjustment>(`${base(clientId, periodId)}/`, body);
}

export async function getAdjustment(
  clientId: string,
  periodId: string,
  adjustmentId: string,
): Promise<PeriodAdjustment> {
  return http.get<PeriodAdjustment>(`${base(clientId, periodId)}/${adjustmentId}`);
}

export async function decideAdjustment(
  clientId: string,
  periodId: string,
  adjustmentId: string,
  body: AdjustmentDecisionIn,
): Promise<PeriodAdjustment> {
  return http.post<PeriodAdjustment>(
    `${base(clientId, periodId)}/${adjustmentId}/decision`,
    body,
  );
}
