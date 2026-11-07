import type { Page } from '../types/clients';
import type { DocumentCategory, DocumentRecord } from '../types/documents';
import { apiFetch, apiRequest } from './http';

const base = (clientId: string, periodId: string) =>
  `/clients/${clientId}/periods/${periodId}/documents`;

export const listDocuments = (
  clientId: string,
  periodId: string,
  p: { limit: number; offset: number; category?: string },
) => {
  const qs = new URLSearchParams({ limit: String(p.limit), offset: String(p.offset) });
  if (p.category) qs.set('category', p.category);
  return apiFetch<Page<DocumentRecord>>(`${base(clientId, periodId)}?${qs}`);
};

export function uploadDocument(
  clientId: string,
  periodId: string,
  file: File,
  category: DocumentCategory,
) {
  const form = new FormData();
  form.append('file', file);
  form.append('category', category);
  return apiFetch<DocumentRecord>(base(clientId, periodId), { method: 'POST', body: form });
}

export const deleteDocument = (clientId: string, periodId: string, documentId: string) =>
  apiFetch<void>(`${base(clientId, periodId)}/${documentId}`, { method: 'DELETE' });

/** Downloads through the API (the bearer token is required; there are no public file URLs). */
export async function downloadDocument(
  clientId: string,
  periodId: string,
  doc: Pick<DocumentRecord, 'id' | 'original_filename'>,
): Promise<void> {
  const resp = await apiRequest(`${base(clientId, periodId)}/${doc.id}/download`);
  const url = URL.createObjectURL(await resp.blob());
  try {
    const a = document.createElement('a');
    a.href = url;
    a.download = doc.original_filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
