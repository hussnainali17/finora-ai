export type ModuleType = 'accounting' | 'taxation' | 'audit';

// Accounting Document Categories (10 categories preserved exactly)
export const ACCOUNTING_CATEGORIES = [
  ['trial_balance', 'Trial Balance (TB)'],
  ['general_ledger', 'General Ledger (GL)'],
  ['bank_statement', 'Bank Statement'],
  ['invoice', 'Invoice'],
  ['receipt', 'Receipt'],
  ['contract', 'Contract'],
  ['fixed_asset_schedule', 'Fixed Asset Schedule'],
  ['inventory_report', 'Inventory Report'],
  ['payroll_schedule', 'Payroll Schedule'],
  ['other', 'Other'],
] as const;

// Taxation Document Categories (7 categories)
export const TAXATION_CATEGORIES = [
  ['tax_return', 'Tax Return (IRIS / IT-1)'],
  ['withholding_certificate', 'Withholding Certificate (CPR)'],
  ['sales_tax_return', 'Sales Tax Return'],
  ['tax_payment_challan', 'Tax Payment Challan'],
  ['tax_notice', 'Tax Notice'],
  ['tax_exemption_certificate', 'Tax Exemption Certificate'],
  ['tax_other', 'Other (Taxation)'],
] as const;

// Audit Document Categories (extensible)
export const AUDIT_CATEGORIES = [
  ['audit_engagement_letter', 'Audit Engagement Letter'],
  ['management_representation', 'Management Representation Letter'],
  ['audit_confirmation', 'Audit Confirmation (Bank / Counterparty)'],
  ['sampling_evidence', 'Sampling Evidence'],
  ['audit_other', 'Other (Audit)'],
] as const;

// Backward-compatibility alias
export const DOCUMENT_CATEGORIES = ACCOUNTING_CATEGORIES;

export const MODULE_CATEGORIES: Record<ModuleType, readonly (readonly [string, string])[]> = {
  accounting: ACCOUNTING_CATEGORIES,
  taxation: TAXATION_CATEGORIES,
  audit: AUDIT_CATEGORIES,
};

export type AccountingCategory = (typeof ACCOUNTING_CATEGORIES)[number][0];
export type TaxationCategory = (typeof TAXATION_CATEGORIES)[number][0];
export type DocumentCategory = string;
export type DocumentStatus = 'uploaded' | 'queued' | 'processing' | 'processed' | 'failed';

export interface DocumentRecord {
  id: string;
  client_id: string;
  period_id: string;
  module: ModuleType | string;
  category: DocumentCategory;
  user_category?: string;
  detected_category?: string | null;
  category_confidence?: number | null;
  category_mismatch?: boolean;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  status: DocumentStatus;
  uploaded_by_email: string | null;
  created_at: string;
}

export interface SharedDocumentReference {
  id: string;
  document_id: string;
  module: ModuleType;
  module_category: string;
  status: string;
  notes?: string | null;
  created_at: string;
}

export interface BatchUploadResult {
  uploaded: DocumentRecord[];
  failed: Array<{ filename: string; error: string }>;
  total_uploaded: number;
  total_failed: number;
}
