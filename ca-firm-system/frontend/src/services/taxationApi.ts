import { http } from './http';
import type {
  TaxCalculationListOut,
  TaxEngagement,
  TaxEngagementListOut,
  TaxpayerProfile,
  TaxReturnDraft,
  TaxReturnDraftListOut,
  TaxWorkflowRun,
  TaxWorkpaperListOut,
} from '../types/taxation';

function base(clientId: string, periodId: string): string {
  return `/clients/${clientId}/periods/${periodId}/taxation`;
}

// ----------------------------------------------------------------------------- Engagements
export async function createTaxEngagement(
  clientId: string,
  periodId: string,
  data: {
    tax_year: number;
    tax_period_label?: string;
    tax_type?: string;
    notes?: string;
  },
): Promise<TaxEngagement> {
  return http.post<TaxEngagement>(`${base(clientId, periodId)}/engagements`, data);
}

export async function listTaxEngagements(
  clientId: string,
  periodId: string,
): Promise<TaxEngagementListOut> {
  return http.get<TaxEngagementListOut>(`${base(clientId, periodId)}/engagements`);
}

// ----------------------------------------------------------------------------- Agent 1: Intake & Profile
export async function runTaxIntake(
  clientId: string,
  periodId: string,
  engagementId: string,
  overrideProfile?: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return http.post<Record<string, unknown>>(
    `${base(clientId, periodId)}/engagements/${engagementId}/intake`,
    overrideProfile ?? {},
  );
}

export async function getTaxpayerProfile(
  clientId: string,
  periodId: string,
  engagementId: string,
): Promise<TaxpayerProfile | null> {
  return http.get<TaxpayerProfile | null>(
    `${base(clientId, periodId)}/engagements/${engagementId}/profile`,
  );
}

// ----------------------------------------------------------------------------- Agent 2: Data & Recon
export async function runTaxReconciliation(
  clientId: string,
  periodId: string,
  engagementId: string,
  sourceOrigin: 'approved_accounting' | 'client_direct' = 'approved_accounting',
  version?: number,
): Promise<Record<string, unknown>> {
  const query = new URLSearchParams({ source_origin: sourceOrigin });
  if (version !== undefined) query.set('version', String(version));
  return http.post<Record<string, unknown>>(
    `${base(clientId, periodId)}/engagements/${engagementId}/reconcile?${query.toString()}`,
    {},
  );
}

export async function listTaxWorkpapers(
  clientId: string,
  periodId: string,
  engagementId: string,
): Promise<TaxWorkpaperListOut> {
  return http.get<TaxWorkpaperListOut>(
    `${base(clientId, periodId)}/engagements/${engagementId}/workpapers`,
  );
}

// ----------------------------------------------------------------------------- Agent 3: Computation
export async function runTaxComputation(
  clientId: string,
  periodId: string,
  engagementId: string,
  overrideInputs?: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return http.post<Record<string, unknown>>(
    `${base(clientId, periodId)}/engagements/${engagementId}/compute`,
    overrideInputs ?? {},
  );
}

export async function listTaxCalculations(
  clientId: string,
  periodId: string,
  engagementId: string,
): Promise<TaxCalculationListOut> {
  return http.get<TaxCalculationListOut>(
    `${base(clientId, periodId)}/engagements/${engagementId}/calculations`,
  );
}

// ----------------------------------------------------------------------------- Agent 4: Review & Filing Pack
export async function runTaxReview(
  clientId: string,
  periodId: string,
  engagementId: string,
): Promise<Record<string, unknown>> {
  return http.post<Record<string, unknown>>(
    `${base(clientId, periodId)}/engagements/${engagementId}/review`,
    {},
  );
}

export async function listTaxReturnDrafts(
  clientId: string,
  periodId: string,
  engagementId: string,
): Promise<TaxReturnDraftListOut> {
  return http.get<TaxReturnDraftListOut>(
    `${base(clientId, periodId)}/engagements/${engagementId}/drafts`,
  );
}

export async function signOffTaxDraft(
  clientId: string,
  periodId: string,
  draftId: string,
  notes?: string,
): Promise<TaxReturnDraft> {
  return http.post<TaxReturnDraft>(`${base(clientId, periodId)}/drafts/${draftId}/sign-off`, {
    notes,
  });
}

export async function recordFilingEvidence(
  clientId: string,
  periodId: string,
  draftId: string,
  evidence: {
    cpr_number?: string;
    acknowledgment_number?: string;
    notes?: string;
  },
): Promise<TaxReturnDraft> {
  return http.post<TaxReturnDraft>(
    `${base(clientId, periodId)}/drafts/${draftId}/filing-evidence`,
    evidence,
  );
}

// ----------------------------------------------------------------------------- Independent Tax Workflow
export async function startTaxWorkflow(
  clientId: string,
  periodId: string,
  engagementId: string,
  sourceOriginPreference: string = 'approved_accounting',
): Promise<TaxWorkflowRun> {
  return http.post<TaxWorkflowRun>(
    `${base(clientId, periodId)}/engagements/${engagementId}/workflow/start?source_origin_preference=${sourceOriginPreference}`,
    {},
  );
}

export async function getTaxWorkflow(
  clientId: string,
  periodId: string,
  engagementId: string,
): Promise<TaxWorkflowRun | null> {
  return http.get<TaxWorkflowRun | null>(
    `${base(clientId, periodId)}/engagements/${engagementId}/workflow`,
  );
}

export async function resumeTaxWorkflow(
  clientId: string,
  periodId: string,
  engagementId: string,
  workflowId: string,
  notes?: string,
): Promise<TaxWorkflowRun> {
  return http.post<TaxWorkflowRun>(
    `${base(clientId, periodId)}/engagements/${engagementId}/workflow/${workflowId}/resume`,
    { notes },
  );
}
