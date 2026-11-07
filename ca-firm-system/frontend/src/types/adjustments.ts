export type AdjustmentCategory =
  | 'accruals'
  | 'prepayments'
  | 'depreciation'
  | 'provisions'
  | 'other';

export type AdjustmentStatus = 'draft' | 'proposed' | 'approved' | 'rejected';

export interface PeriodAdjustment {
  id: string;
  firm_id: string;
  client_id: string;
  period_id: string;
  category: AdjustmentCategory;
  status: AdjustmentStatus;
  version: number;
  debit_account_code: string;
  debit_account_name: string;
  credit_account_code: string;
  credit_account_name: string;
  amount: string;
  currency: string;
  accounting_rationale: string;
  calculation_details: Record<string, unknown>;
  source_refs: Record<string, unknown>[];
  prepared_by_agent: string;
  created_by?: string;
  reviewer_id?: string;
  reviewed_at?: string;
  reviewer_decision?: string;
  reviewer_comments?: string;
  history: Record<string, unknown>[];
  created_at: string;
  updated_at: string;
}

export interface AdjustmentListOut {
  items: PeriodAdjustment[];
  total: number;
}

export interface AdjustmentCreateIn {
  category: AdjustmentCategory;
  debit_account_code: string;
  debit_account_name: string;
  credit_account_code: string;
  credit_account_name: string;
  amount: number | string;
  currency?: string;
  accounting_rationale: string;
  calculation_details?: Record<string, unknown>;
  source_refs?: Record<string, unknown>[];
}

export interface AdjustmentDecisionIn {
  decision: 'approved' | 'rejected';
  comments?: string;
}

export const CATEGORY_LABELS: Record<AdjustmentCategory, string> = {
  accruals: 'Accrual',
  prepayments: 'Prepayment Amortization',
  depreciation: 'Depreciation',
  provisions: 'Provision / Allowance',
  other: 'Other Period-End Adjustment',
};

export const STATUS_COLORS: Record<AdjustmentStatus, 'default' | 'info' | 'success' | 'error'> = {
  draft: 'default',
  proposed: 'info',
  approved: 'success',
  rejected: 'error',
};
