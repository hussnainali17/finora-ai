import type { Client, ClientCreate, Page, Period, PeriodCreate } from '../types/clients';
import { apiFetch } from './http';

const json = (method: string, body: unknown): RequestInit => ({
  method,
  body: JSON.stringify(body),
});

export const listClients = (p: { limit: number; offset: number; q?: string; status?: string }) => {
  const qs = new URLSearchParams({ limit: String(p.limit), offset: String(p.offset) });
  if (p.q) qs.set('q', p.q);
  if (p.status) qs.set('status', p.status);
  return apiFetch<Page<Client>>(`/clients?${qs}`);
};
export const getClient = (id: string) => apiFetch<Client>(`/clients/${id}`);
export const createClient = (body: ClientCreate) =>
  apiFetch<Client>('/clients', json('POST', body));
export const setClientStatus = (id: string, status: 'active' | 'archived') =>
  apiFetch<Client>(`/clients/${id}`, json('PATCH', { status }));

export const listPeriods = (clientId: string) => apiFetch<Period[]>(`/clients/${clientId}/periods`);
export const createPeriod = (clientId: string, body: PeriodCreate) =>
  apiFetch<Period>(`/clients/${clientId}/periods`, json('POST', body));
export const setPeriodState = (clientId: string, periodId: string, action: 'close' | 'reopen') =>
  apiFetch<Period>(`/clients/${clientId}/periods/${periodId}/${action}`, { method: 'POST' });
