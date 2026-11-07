/**
 * Accounting Review API service (Phase 6).
 * All calls go through the FastAPI backend — never to LiteLLM or any AI
 * provider directly. Authorization is enforced server-side.
 */

import { http } from './http';
import type {
  FindingStatusUpdate,
  ReconciliationSchedule,
  ReviewFinding,
  ReviewFindingListOut,
  ReviewRun,
  ReviewRunListOut,
  TriggerReviewIn,
} from '../types/accounting_review';

function reviewBase(clientId: string, periodId: string): string {
  return `/clients/${clientId}/periods/${periodId}/review`;
}

/** Trigger a new accounting review run for a client/period. */
export async function triggerReview(
  clientId: string,
  periodId: string,
  body: TriggerReviewIn = {},
): Promise<ReviewRun> {
  return http.post<ReviewRun>(`${reviewBase(clientId, periodId)}/`, body);
}

/** List review runs for a client/period. */
export async function listReviewRuns(
  clientId: string,
  periodId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<ReviewRunListOut> {
  const qs = new URLSearchParams();
  if (params.limit !== undefined) qs.set('limit', String(params.limit));
  if (params.offset !== undefined) qs.set('offset', String(params.offset));
  const query = qs.toString() ? `?${qs}` : '';
  return http.get<ReviewRunListOut>(`${reviewBase(clientId, periodId)}/${query}`);
}

/** Get a specific review run by id. */
export async function getReviewRun(
  clientId: string,
  periodId: string,
  runId: string,
): Promise<ReviewRun> {
  return http.get<ReviewRun>(`${reviewBase(clientId, periodId)}/${runId}`);
}

/** List findings for a review run with optional filters. */
export async function listFindings(
  clientId: string,
  periodId: string,
  runId: string,
  params: {
    module?: string;
    severity?: string;
    status?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<ReviewFindingListOut> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined) qs.set(k, String(v));
  });
  const query = qs.toString() ? `?${qs}` : '';
  return http.get<ReviewFindingListOut>(
    `${reviewBase(clientId, periodId)}/${runId}/findings${query}`,
  );
}

/** Update a finding's status (open/explained/resolved/escalated). */
export async function updateFindingStatus(
  clientId: string,
  periodId: string,
  runId: string,
  findingId: string,
  update: FindingStatusUpdate,
): Promise<ReviewFinding> {
  return http.patch<ReviewFinding>(
    `${reviewBase(clientId, periodId)}/${runId}/findings/${findingId}`,
    update,
  );
}

/** List reconciliation schedules for a review run. */
export async function listSchedules(
  clientId: string,
  periodId: string,
  runId: string,
): Promise<ReconciliationSchedule[]> {
  return http.get<ReconciliationSchedule[]>(
    `${reviewBase(clientId, periodId)}/${runId}/schedules`,
  );
}

/** Get a specific reconciliation schedule. */
export async function getSchedule(
  clientId: string,
  periodId: string,
  runId: string,
  scheduleId: string,
): Promise<ReconciliationSchedule> {
  return http.get<ReconciliationSchedule>(
    `${reviewBase(clientId, periodId)}/${runId}/schedules/${scheduleId}`,
  );
}
