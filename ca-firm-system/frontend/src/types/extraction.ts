export const COLUMN_ROLES = [
  ['account_code', 'Account code'],
  ['account_name', 'Account name'],
  ['description', 'Description'],
  ['date', 'Date'],
  ['value_date', 'Value date'],
  ['debit', 'Debit'],
  ['credit', 'Credit'],
  ['withdrawal', 'Withdrawal'],
  ['deposit', 'Deposit'],
  ['amount', 'Amount'],
  ['balance', 'Balance'],
  ['quantity', 'Quantity'],
  ['unit_cost', 'Unit cost'],
  ['reference', 'Reference'],
  ['party', 'Party'],
  ['currency', 'Currency'],
  ['item_code', 'Item code'],
  ['cost', 'Cost'],
  ['depreciation', 'Depreciation'],
  ['accumulated_depreciation', 'Accumulated depreciation'],
  ['net_book_value', 'Net book value'],
  ['gross_pay', 'Gross pay'],
  ['deductions', 'Deductions'],
  ['net_pay', 'Net pay'],
  ['other', 'Other'],
  ['ignore', 'Ignore'],
] as const;

export const TABLE_TYPES = [
  ['trial_balance', 'Trial balance'],
  ['general_ledger', 'General ledger listing'],
  ['bank_statement', 'Bank statement'],
  ['sales_ledger', 'Sales listing'],
  ['purchase_ledger', 'Purchases listing'],
  ['fixed_asset_register', 'Fixed asset register'],
  ['inventory_report', 'Inventory report'],
  ['payroll_schedule', 'Payroll schedule'],
  ['text_document', 'Text document'],
  ['unknown', 'Unknown'],
] as const;

export type ColumnRole = (typeof COLUMN_ROLES)[number][0];
export type TableType = (typeof TABLE_TYPES)[number][0];

export interface ExtractionColumn {
  col_index: number;
  letter: string | null;
  header: string | null;
  header_synthetic: boolean;
  suggested_role: string;
  confidence: number;
  role_source: string;
  confirmed_role: string | null;
  effective_role: string;
}

export interface ExtractionTable {
  id: string;
  ordinal: number;
  name: string;
  kind: string;
  n_rows: number;
  n_cols: number;
  detected_type: string;
  type_confidence: number;
  type_source: string;
  confirmed_type: string | null;
  effective_type: string;
  currency: string | null;
  period_start: string | null;
  period_end: string | null;
  status: 'ok' | 'needs_review' | 'ignored';
  columns: ExtractionColumn[];
  open_findings: number;
}

export interface ExtractionRun {
  id: string;
  version: number;
  status: 'running' | 'completed' | 'failed';
  trigger: string;
  error_code: string | null;
  error_message: string | null;
  llm_used: boolean;
}

export interface Extraction {
  document_id: string;
  document_status: string;
  run: ExtractionRun | null;
  tables: ExtractionTable[];
  open_findings: Record<string, number>;
}

export interface RowFlag {
  code: string;
  col: number | null;
  message: string;
}

export interface ExtractedRowRecord {
  row_index: number;
  raw: Record<string, { v: string; t: string }>;
  normalized: Record<string, string | null>;
  flags: RowFlag[];
}

export interface Finding {
  id: string;
  table_id: string | null;
  row_index: number | null;
  col_index: number | null;
  code: string;
  severity: 'info' | 'warning' | 'error';
  message: string;
  status: 'open' | 'resolved' | 'dismissed';
  resolution_note: string | null;
}
