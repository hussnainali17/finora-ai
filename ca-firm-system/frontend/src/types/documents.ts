export const DOCUMENT_CATEGORIES = [
  ['trial_balance', 'Trial balance'],
  ['bank_statement', 'Bank statement'],
  ['invoice', 'Invoice'],
  ['receipt', 'Receipt'],
  ['contract', 'Contract'],
  ['fixed_asset_schedule', 'Fixed asset schedule'],
  ['inventory_report', 'Inventory report'],
  ['payroll_schedule', 'Payroll schedule'],
  ['other', 'Other'],
] as const;

export type DocumentCategory = (typeof DOCUMENT_CATEGORIES)[number][0];
export type DocumentStatus = 'uploaded' | 'queued' | 'processing' | 'processed' | 'failed';

export interface DocumentRecord {
  id: string;
  client_id: string;
  period_id: string;
  category: DocumentCategory;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  status: DocumentStatus;
  uploaded_by_email: string | null;
  created_at: string;
}
