export type IntentType =
  | 'question'
  | 'error_report'
  | 'correction_request'
  | 'instruction'
  | 'approval_action'
  | 'general';

export type TargetAgentType =
  | 'intake'
  | 'accounting_review'
  | 'adjustments'
  | 'reporting'
  | 'audit'
  | 'general';

export type ProposalStatus = 'pending' | 'approved' | 'rejected' | 'applied' | 'failed';

export interface CorrectionProposal {
  id: string;
  conversation_id: string;
  target_agent: string;
  target_entity_type: string;
  target_entity_id: string;
  title: string;
  description: string;
  original_data: Record<string, any>;
  proposed_data: Record<string, any>;
  status: ProposalStatus;
  reexecution_plan: string[];
  reexecution_result: Record<string, any>;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  reviewer_notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_type: 'user' | 'assistant' | 'system';
  sender_id?: string | null;
  content: string;
  intent?: IntentType | string | null;
  target_agent?: TargetAgentType | string | null;
  proposal_id?: string | null;
  message_metadata?: Record<string, any>;
  created_at: string;
}

export interface Conversation {
  id: string;
  firm_id: string;
  client_id: string;
  period_id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  messages: Message[];
  proposals: CorrectionProposal[];
}

export interface ConversationSummary {
  id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ContextSnapshot {
  summary: {
    documents_count: number;
    tables_count: number;
    total_extracted_rows: number;
    review_findings_count: number;
    open_findings_count: number;
    adjustments_count: number;
    proposed_adjustments_count: number;
    approved_adjustments_count: number;
    financial_reports_count: number;
    trial_balance: {
      rows_count: number;
      total_debits: number;
      total_credits: number;
      is_balanced: boolean;
      variance: number;
    };
    latest_workflow_status: string;
  };
  documents: Array<{
    id: string;
    filename: string;
    category: string;
    status: string;
    created_at: string | null;
  }>;
  tables: Array<{
    id: string;
    name: string;
    detected_type: string;
    confirmed_type?: string | null;
    type: string;
    n_rows: number;
    currency?: string | null;
    columns: Array<{ col_index: number; header: string; role: string }>;
    rows_sample: any[];
  }>;
  review_findings: Array<{
    id: string;
    module: string;
    finding_type: string;
    severity: string;
    title: string;
    description: string;
    amount?: number | null;
    currency?: string | null;
    status: string;
    reviewer_note?: string | null;
  }>;
  period_adjustments: Array<{
    id: string;
    category: string;
    status: string;
    debit_account_code: string;
    debit_account_name: string;
    credit_account_code: string;
    credit_account_name: string;
    amount: number;
    accounting_rationale: string;
  }>;
  financial_reports: Array<{
    id: string;
    report_type: string;
    status: string;
    data: Record<string, any>;
    validation_details?: Record<string, any>;
  }>;
}
