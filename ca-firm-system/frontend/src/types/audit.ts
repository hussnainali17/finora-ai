export interface AuditEvent {
  id: string;
  firm_id: string;
  client_id?: string;
  actor_user_id?: string;
  actor_email?: string;
  action: string;
  target_type: string;
  target_id?: string;
  metadata: Record<string, unknown>;
  ip_address?: string;
  occurred_at: string;
}

export interface AuditEventPage {
  items: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}
