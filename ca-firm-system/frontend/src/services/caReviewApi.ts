import { http } from './http';
import type {
  ContextSnapshot,
  Conversation,
  ConversationSummary,
  CorrectionProposal,
  Message,
} from '../types/caReview';

const BASE = (clientId: string, periodId: string) =>
  `/clients/${clientId}/periods/${periodId}/ca-review`;

export async function listConversations(
  clientId: string,
  periodId: string,
): Promise<ConversationSummary[]> {
  return http.get<ConversationSummary[]>(`${BASE(clientId, periodId)}/conversations`);
}

export async function createConversation(
  clientId: string,
  periodId: string,
  title = 'CA Review Session',
): Promise<Conversation> {
  return http.post<Conversation>(`${BASE(clientId, periodId)}/conversations`, { title });
}

export async function getActiveConversation(
  clientId: string,
  periodId: string,
): Promise<Conversation> {
  return http.get<Conversation>(`${BASE(clientId, periodId)}/conversations/active`);
}

export async function getConversation(
  clientId: string,
  periodId: string,
  conversationId: string,
): Promise<Conversation> {
  return http.get<Conversation>(
    `${BASE(clientId, periodId)}/conversations/${conversationId}`,
  );
}

export async function sendMessage(
  clientId: string,
  periodId: string,
  conversationId: string,
  content: string,
): Promise<Message> {
  return http.post<Message>(
    `${BASE(clientId, periodId)}/conversations/${conversationId}/messages`,
    { content },
  );
}

export async function listProposals(
  clientId: string,
  periodId: string,
  status?: string,
): Promise<CorrectionProposal[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : '';
  return http.get<CorrectionProposal[]>(`${BASE(clientId, periodId)}/proposals${query}`);
}

export async function reviewProposal(
  clientId: string,
  periodId: string,
  proposalId: string,
  decision: 'approve' | 'reject',
  notes?: string,
): Promise<CorrectionProposal> {
  return http.post<CorrectionProposal>(
    `${BASE(clientId, periodId)}/proposals/${proposalId}/review`,
    { decision, notes },
  );
}

export async function getContextSnapshot(
  clientId: string,
  periodId: string,
): Promise<ContextSnapshot> {
  return http.get<ContextSnapshot>(`${BASE(clientId, periodId)}/context-snapshot`);
}
