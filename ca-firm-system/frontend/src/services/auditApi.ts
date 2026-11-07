import { http } from './http';
import type { AuditEventPage } from '../types/audit';

export async function listAuditEvents(params: {
  limit?: number;
  offset?: number;
  action?: string;
  clientId?: string;
  actorUserId?: string;
  since?: string;
  until?: string;
} = {}): Promise<AuditEventPage> {
  const qs = new URLSearchParams();
  if (params.limit !== undefined) qs.set('limit', String(params.limit));
  if (params.offset !== undefined) qs.set('offset', String(params.offset));
  if (params.action) qs.set('action', params.action);
  if (params.clientId) qs.set('client_id', params.clientId);
  if (params.actorUserId) qs.set('actor_user_id', params.actorUserId);
  if (params.since) qs.set('since', params.since);
  if (params.until) qs.set('until', params.until);

  const query = qs.toString() ? `?${qs}` : '';
  return http.get<AuditEventPage>(`/audit-events${query}`);
}
