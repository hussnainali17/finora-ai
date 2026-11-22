export interface TaxEngagement {
  id: string;
  firm_id: string;
  client_id: string;
  period_id: string;
  tax_year: number;
  tax_period_label: string;
  tax_type: string;
  status: 'draft' | 'in_progress' | 'review' | 'ca_approved' | 'filed';
  jurisdiction: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaxEngagementListOut {
  items: TaxEngagement[];
  total: number;
}

export interface MissingInfoItem {
  query_id: string;
  field: string;
  question: string;
  severity: 'critical' | 'warning' | 'info';
  statutory_basis?: string;
}

export interface TaxpayerProfile {
  id: string;
  firm_id: string;
  client_id: string;
  engagement_id: string;
  version: number;
  legal_form: string;
  business_name?: string;
  ntn: string;
  strn: string | null;
  principal_activity: string | null;
  business_sector?: string;
  registered_branches?: Array<Record<string, unknown>>;
  jurisdictions?: string[];
  applicable_obligations: string[];
  is_active_taxpayer?: boolean;
  verified_attributes?: Record<string, unknown>;
  missing_information: MissingInfoItem[];
  verified_by_ca?: boolean;
  created_at: string;
  updated_at: string;
}

export interface TaxWorkpaper {
  id: string;
  firm_id: string;
  client_id: string;
  engagement_id: string;
  workpaper_type: string;
  title: string;
  source_origin: string;
  source_version: number;
  data: Record<string, unknown>;
  summary: Record<string, unknown>;
  reconciliation_notes: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface TaxWorkpaperListOut {
  items: TaxWorkpaper[];
  total: number;
}

export interface TaxCalculationRun {
  id: string;
  firm_id: string;
  client_id: string;
  engagement_id: string;
  tax_year: number;
  run_number: number;
  rules_version: string;
  accounting_profit_before_tax: number;
  total_additions: number;
  total_deductions: number;
  taxable_income: number;
  normal_corporate_tax: number;
  minimum_tax_turnover: number;
  alternate_corporate_tax: number;
  super_tax_4c: number;
  final_gross_tax_payable: number;
  tax_credits: number;
  withholding_tax_adjustable: number;
  advance_tax_paid: number;
  net_tax_payable: number;
  calculation_trace: Array<{
    step: string;
    description: string;
    basis: number;
    rate: number;
    amount: number;
    rule_ref: string;
  }>;
  status: string;
  created_at: string;
}

export interface TaxCalculationListOut {
  items: TaxCalculationRun[];
  total: number;
}

export interface TaxReturnDraft {
  id: string;
  firm_id: string;
  client_id: string;
  engagement_id: string;
  version: number;
  return_type: string;
  status: 'draft' | 'pending_approval' | 'ca_approved' | 'filed' | 'rejected';
  return_fields: Record<string, number | string>;
  review_report: {
    is_compliant: boolean;
    findings_count?: number;
    summary?: string;
  };
  risk_findings: Array<{
    code: string;
    severity: 'low' | 'medium' | 'high' | 'critical';
    title: string;
    description: string;
    rule_ref?: string;
  }>;
  filing_evidence: {
    cpr_number?: string;
    acknowledgment_number?: string;
    filed_by?: string;
    filed_at?: string;
    notes?: string;
  };
  ca_notes: string | null;
  signed_off_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaxReturnDraftListOut {
  items: TaxReturnDraft[];
  total: number;
}

export interface TaxWorkflowRun {
  id: string;
  firm_id: string;
  client_id: string;
  period_id: string;
  engagement_id: string;
  status: 'running' | 'paused_approval' | 'completed' | 'failed';
  current_step: string;
  state_data: Record<string, unknown>;
  checkpoint_id: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}
