export interface ApprovedModuleOutput {
  id: string;
  firm_id: string;
  client_id: string;
  period_id: string;
  module: 'accounting' | 'taxation' | 'audit';
  version: number;
  status: 'approved' | 'superseded';
  data: Record<string, unknown>;
  summary: Record<string, unknown>;
  source_version_refs: Record<string, number>;
  validation_results: {
    is_valid: boolean;
    issues?: string[];
    [key: string]: unknown;
  };
  ca_notes: string | null;
  signed_off_at: string | null;
  created_at: string;
}

export interface ApprovedModuleOutputListOut {
  items: ApprovedModuleOutput[];
  total: number;
}
