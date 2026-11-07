import type { Page } from '../types/clients';
import type { ExtractedRowRecord, Extraction, ExtractionTable, Finding } from '../types/extraction';
import { apiFetch } from './http';

const base = (c: string, p: string, d: string) =>
  `/clients/${c}/periods/${p}/documents/${d}/extraction`;
const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export const getExtraction = (c: string, p: string, d: string) =>
  apiFetch<Extraction>(base(c, p, d));

export const listExtractedRows = (
  c: string,
  p: string,
  d: string,
  tableId: string,
  q: { limit: number; offset: number; flaggedOnly: boolean },
) => {
  const qs = new URLSearchParams({ limit: String(q.limit), offset: String(q.offset) });
  if (q.flaggedOnly) qs.set('flagged_only', 'true');
  return apiFetch<Page<ExtractedRowRecord>>(`${base(c, p, d)}/tables/${tableId}/rows?${qs}`);
};

export const listFindings = (c: string, p: string, d: string) =>
  apiFetch<Finding[]>(`${base(c, p, d)}/findings`);

export const setColumnRole = (
  c: string,
  p: string,
  d: string,
  tableId: string,
  colIndex: number,
  role: string,
) =>
  apiFetch<ExtractionTable>(
    `${base(c, p, d)}/tables/${tableId}/columns/${colIndex}`,
    json('PATCH', { role }),
  );

export const setTableType = (c: string, p: string, d: string, tableId: string, type: string) =>
  apiFetch<ExtractionTable>(
    `${base(c, p, d)}/tables/${tableId}`,
    json('PATCH', { confirmed_type: type }),
  );

export const updateFinding = (
  c: string,
  p: string,
  d: string,
  id: string,
  status: 'open' | 'resolved' | 'dismissed',
) => apiFetch<Finding>(`${base(c, p, d)}/findings/${id}`, json('PATCH', { status }));

export const rerunExtraction = (c: string, p: string, d: string) =>
  apiFetch<{ status: string }>(`${base(c, p, d)}/rerun`, { method: 'POST' });
