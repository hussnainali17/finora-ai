export interface MultiModuleWorkflowRun {
  id: string;
  firm_id: string;
  client_id: string;
  period_id: string;
  workflow_type: string;
  status:
    | 'running'
    | 'paused_accounting_approval'
    | 'paused_taxation_approval'
    | 'paused_final_signoff'
    | 'completed'
    | 'failed';
  current_module:
    | 'shared_intake'
    | 'accounting'
    | 'accounting_gate'
    | 'publish_accounting'
    | 'taxation'
    | 'taxation_gate'
    | 'cross_module_validation'
    | 'final_ca_review'
    | 'completed';
  accounting_run_id: string | null;
  tax_run_id: string | null;
  checkpoint_id: string | null;
  state_data: {
    accounting_approved_version?: number;
    tax_draft_version?: number;
    cross_module_validation?: {
      statements_tied_to_tax: boolean;
      accounting_pbt: number;
      tax_workpaper_pbt: number;
      difference: number;
      tie_out_valid: boolean;
    };
    consolidated_report?: {
      summary?: string;
      net_profit?: number;
      tax_liability?: number;
      effective_tax_rate?: string;
      status?: string;
    };
    ca_final_signoff?: boolean;
    final_signoff_notes?: string;
    [key: string]: unknown;
  };
  error_message: string | null;
  created_at: string;
  updated_at: string;
}
