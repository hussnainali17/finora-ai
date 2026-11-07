export type ReportType =
  | 'adjusted_trial_balance'
  | 'profit_loss'
  | 'balance_sheet'
  | 'cash_flows'
  | 'changes_in_equity'
  | 'full_pack';

export type ReportStatus = 'draft' | 'published' | 'signed_off';

export interface ValidationIssue {
  check_name: string;
  severity: 'error' | 'warning' | 'info';
  description: string;
  difference: string;
  details: Record<string, unknown>;
}

export interface ValidationReport {
  is_valid: boolean;
  total_checks: number;
  passed_checks: number;
  failed_checks: number;
  issues: ValidationIssue[];
}

export interface FinancialReport {
  id: string;
  firm_id: string;
  client_id: string;
  period_id: string;
  report_type: ReportType;
  status: ReportStatus;
  version: number;
  data: Record<string, any>;
  validation_results: ValidationReport;
  excel_object_key?: string;
  pdf_object_key?: string;
  signed_off_by?: string;
  signed_off_at?: string;
  sign_off_notes?: string;
  created_at: string;
  updated_at: string;
}

export interface FinancialReportListOut {
  items: FinancialReport[];
  total: number;
}
