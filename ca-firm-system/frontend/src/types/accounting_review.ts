export type ReviewStatus = 'pending' | 'running' | 'completed' | 'failed';
export type FindingSeverity = 'info' | 'warning' | 'error';
export type FindingStatus = 'open' | 'explained' | 'resolved' | 'escalated';
export type ReviewModule =
  | 'sales_receivables'
  | 'purchases_payables'
  | 'bank_cash'
  | 'inventory'
  | 'fixed_assets'
  | 'payroll';

export interface ModuleSummary {
  status: string;
  finding_count: number;
  exception_count: number;
  error?: string;
}

export interface ReviewRun {
  id: string;
  client_id: string;
  period_id: string;
  firm_id: string;
  status: ReviewStatus;
  trigger: 'auto' | 'manual';
  triggered_by?: string;
  started_at?: string;
  finished_at?: string;
  error_message?: string;
  module_summary: Record<string, ModuleSummary>;
  created_at: string;
  updated_at: string;
}

export interface ReviewRunListOut {
  items: ReviewRun[];
  total: number;
}

export interface EvidenceRef {
  document_id?: string;
  table_id?: string;
  row_index?: number;
  description: string;
}

export interface ReviewFinding {
  id: string;
  review_run_id: string;
  firm_id: string;
  client_id: string;
  period_id: string;
  module: ReviewModule;
  finding_type: string;
  severity: FindingSeverity;
  title: string;
  description: string;
  source_ref: Record<string, unknown>;
  amount?: string;
  currency?: string;
  status: FindingStatus;
  reviewer_id?: string;
  reviewed_at?: string;
  reviewer_note?: string;
  evidence_refs: EvidenceRef[];
  created_at: string;
  updated_at: string;
}

export interface ReviewFindingListOut {
  items: ReviewFinding[];
  total: number;
}

export interface ReconciliationSchedule {
  id: string;
  review_run_id: string;
  firm_id: string;
  client_id: string;
  period_id: string;
  module: ReviewModule;
  schedule_type: string;
  label: string;
  data: Record<string, unknown>;
  generated_at: string;
  source_refs: Record<string, unknown>[];
}

export interface FindingStatusUpdate {
  status: FindingStatus;
  reviewer_note?: string;
}

export interface TriggerReviewIn {
  modules?: ReviewModule[];
}

export const MODULE_LABELS: Record<ReviewModule, string> = {
  sales_receivables: 'Sales & Receivables',
  purchases_payables: 'Purchases & Payables',
  bank_cash: 'Bank & Cash',
  inventory: 'Inventory',
  fixed_assets: 'Fixed Assets',
  payroll: 'Payroll',
};

export const SEVERITY_COLORS: Record<FindingSeverity, 'default' | 'warning' | 'error'> = {
  info: 'default',
  warning: 'warning',
  error: 'error',
};

export const STATUS_COLORS: Record<FindingStatus, string> = {
  open: '#f44336',
  explained: '#ff9800',
  resolved: '#4caf50',
  escalated: '#9c27b0',
};
