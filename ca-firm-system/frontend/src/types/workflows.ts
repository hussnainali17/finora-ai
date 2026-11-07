export type WorkflowStatus = 'running' | 'paused_approval' | 'completed' | 'failed';

export type WorkflowStep =
  | 'intake'
  | 'data_quality_gate'
  | 'accounting_review'
  | 'period_adjustments'
  | 'ca_approval'
  | 'financial_reporting'
  | 'validation_gate'
  | 'completed';

export interface WorkflowRun {
  id: string;
  firm_id: string;
  client_id: string;
  period_id: string;
  status: WorkflowStatus;
  current_step: WorkflowStep;
  state_data: Record<string, unknown>;
  checkpoint_id?: string;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export const STEP_LABELS: Record<WorkflowStep, string> = {
  intake: 'File Intake (Agent 1)',
  data_quality_gate: 'Data Quality Gate',
  accounting_review: 'Accounting Review (Agent 2)',
  period_adjustments: 'Adjustments (Agent 3)',
  ca_approval: 'CA Review & Approval (Human Checkpoint)',
  financial_reporting: 'Financial Statements (Agent 4)',
  validation_gate: 'Integrity Validation',
  completed: 'Final Sign-off Ready',
};
