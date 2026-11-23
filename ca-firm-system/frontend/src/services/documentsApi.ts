import type { Page } from '../types/clients';
import type {
  BatchUploadResult,
  DocumentCategory,
  DocumentRecord,
  ModuleType,
  SharedDocumentReference,
} from '../types/documents';
import { apiFetch, apiRequest } from './http';

const base = (clientId: string, periodId: string) =>
  `/clients/${clientId}/periods/${periodId}/documents`;

export const listDocuments = (
  clientId: string,
  periodId: string,
  p: { limit: number; offset: number; module?: string; category?: string },
) => {
  const qs = new URLSearchParams({ limit: String(p.limit), offset: String(p.offset) });
  if (p.module && p.module !== 'all') qs.set('module', p.module);
  if (p.category) qs.set('category', p.category);
  return apiFetch<Page<DocumentRecord>>(`${base(clientId, periodId)}?${qs}`);
};

export function uploadDocument(
  clientId: string,
  periodId: string,
  file: File,
  category: DocumentCategory,
  module: ModuleType = 'accounting',
) {
  const form = new FormData();
  form.append('file', file);
  form.append('category', category);
  form.append('module', module);
  return apiFetch<DocumentRecord>(base(clientId, periodId), { method: 'POST', body: form });
}

export function uploadMultipleDocuments(
  clientId: string,
  periodId: string,
  files: File[],
  category: DocumentCategory,
  module: ModuleType = 'accounting',
) {
  const form = new FormData();
  files.forEach((file) => form.append('files', file));
  form.append('category', category);
  form.append('module', module);
  return apiFetch<BatchUploadResult>(`${base(clientId, periodId)}/batch`, {
    method: 'POST',
    body: form,
  });
}

export function shareDocumentWithModule(
  clientId: string,
  periodId: string,
  documentId: string,
  targetModule: ModuleType,
  targetCategory?: string,
  notes?: string,
) {
  return apiFetch<SharedDocumentReference>(`${base(clientId, periodId)}/${documentId}/share`, {
    method: 'POST',
    body: JSON.stringify({
      target_module: targetModule,
      target_category: targetCategory,
      notes,
    }),
  });
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
