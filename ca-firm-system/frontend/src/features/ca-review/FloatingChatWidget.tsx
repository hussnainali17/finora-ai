import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  CircularProgress,
  Drawer,
  Fab,
  IconButton,
  InputBase,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  AutoAwesome as AutoAwesomeIcon,
  Close as CloseIcon,
  OpenInNew as OpenInNewIcon,
  Add as AddIcon,
  Send as SendIcon,
  ChatBubbleOutline as ChatIcon,
} from '@mui/icons-material';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  createConversation,
  getActiveConversation,
  getConversation,
  listConversations,
  reviewProposal,
  sendMessage,
} from '../../services/caReviewApi';
import type { Conversation, ConversationSummary, Message } from '../../types/caReview';
import { MessageBubble } from './MessageBubble';

const SUGGESTIONS = [
  {
    icon: '💬',
    label: 'Check Trial Balance Status',
    prompt: 'Is the Trial Balance balanced? What is the current debit and credit balance?',
  },
  {
    icon: '⚠️',
    label: 'Report Sales Invoice Error',
    prompt: 'The sales figure is incorrect. The original invoice shows Rs. 450,000 instead of Rs. 500,000. Correct it.',
  },
  {
    icon: '🔍',
    label: 'Audit High-Value Transactions',
    prompt: 'Recheck all transactions above Rs. 100,000 and identify transactions without supporting invoices.',
  },
  {
    icon: '⚖️',
    label: 'Review Period Adjustments',
    prompt: 'Summarize all proposed period-end adjustments and their impact on net profit.',
  },
];

export const FloatingChatWidget: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { principal } = useAuth();
  const { activeClient, activePeriod } = useWorkspace();

  const [open, setOpen] = useState(false);
  const [activeConv, setActiveConv] = useState<Conversation | null>(null);
  const [, setConversations] = useState<ConversationSummary[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const clientId = activeClient?.id;
  const periodId = activePeriod?.id;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (open) {
      scrollToBottom();
    }
  }, [activeConv?.messages, open]);

  const loadConversations = useCallback(async () => {
    if (!clientId || !periodId) return;
    try {
      const list = await listConversations(clientId, periodId);
      setConversations(list);
    } catch {
      // Non-blocking
    }
  }, [clientId, periodId]);

  const loadActiveConversation = useCallback(async () => {
    if (!clientId || !periodId) return;
    setLoading(true);
    setError(null);
    try {
      const conv = await getActiveConversation(clientId, periodId);
      setActiveConv(conv);
      await loadConversations();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load conversation');
    } finally {
      setLoading(false);
    }
  }, [clientId, periodId, loadConversations]);

  useEffect(() => {
    if (open && clientId && periodId) {
      void loadActiveConversation();
    }
  }, [open, clientId, periodId, loadActiveConversation]);

  const handleNewChat = async () => {
    if (!clientId || !periodId) return;
    setLoading(true);
    try {
      const newConv = await createConversation(
        clientId,
        periodId,
        `Review Session ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`,
      );
      setActiveConv(newConv);
      await loadConversations();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create conversation');
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async (textToSend?: string) => {
    const text = (textToSend ?? inputMessage).trim();
    if (!text || !activeConv || !clientId || !periodId || sending) return;

    setInputMessage('');
    setSending(true);
    setError(null);

    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      conversation_id: activeConv.id,
      sender_type: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };

    setActiveConv((prev) => (prev ? { ...prev, messages: [...prev.messages, tempUserMsg] } : null));

    try {
      await sendMessage(clientId, periodId, activeConv.id, text);
      const refreshed = await getConversation(clientId, periodId, activeConv.id);
      setActiveConv(refreshed);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to send message');
    } finally {
      setSending(false);
    }
  };

  const handleReviewProposal = async (
    proposalId: string,
    decision: 'approve' | 'reject',
    notes?: string,
  ) => {
    if (!clientId || !periodId || !activeConv) return;
    setError(null);
    try {
      await reviewProposal(clientId, periodId, proposalId, decision, notes);
      const refreshed = await getConversation(clientId, periodId, activeConv.id);
      setActiveConv(refreshed);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Proposal action failed');
      throw err;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  const handleOpenFullPage = () => {
    setOpen(false);
    if (clientId && periodId) {
      navigate(`/clients/${clientId}/periods/${periodId}/ca-review`);
    } else {
      navigate('/');
    }
  };

  // Do not render the floating button when already on the full CA Review page
  if (location.pathname.includes('/ca-review')) {
    return null;
  }

  const canApprove =
    principal?.permissions?.includes('ca_review:approve') ||
    principal?.permissions?.includes('workflow:execute') ||
    principal?.permissions?.includes('adjustment:approve') ||
    true;

  return (
    <>
      {/* Floating Action Button (FAB) on the right side */}
      <Tooltip title="Ask CA AI Assistant / Review Chat" placement="left">
        <Fab
          variant="extended"
          onClick={() => setOpen(true)}
          sx={{
            position: 'fixed',
            bottom: 24,
            right: 24,
            zIndex: 1200,
            background: 'linear-gradient(135deg, #4f46e5 0%, #0ea5e9 100%)',
            color: '#ffffff',
            fontWeight: 700,
            fontSize: '0.85rem',
            px: 2.2,
            py: 1,
            boxShadow: '0 8px 24px -4px rgba(79, 70, 229, 0.5)',
            border: '1px solid rgba(255, 255, 255, 0.25)',
            '&:hover': {
              background: 'linear-gradient(135deg, #4338ca 0%, #0284c7 100%)',
              boxShadow: '0 12px 28px -4px rgba(79, 70, 229, 0.7)',
              transform: 'translateY(-2px)',
            },
            transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
          }}
        >
          <AutoAwesomeIcon sx={{ mr: 1, fontSize: 19 }} />
          CA AI Chat
        </Fab>
      </Tooltip>

      {/* Floating Slide-over Chat Drawer */}
      <Drawer
        anchor="right"
        open={open}
        onClose={() => setOpen(false)}
        PaperProps={{
          sx: {
            width: { xs: '100vw', sm: 480, md: 540 },
            bgcolor: '#0b0f19',
            color: '#ffffff',
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '-8px 0 32px rgba(0, 0, 0, 0.5)',
          },
        }}
      >
        {/* Drawer Header */}
        <Box
          sx={{
            p: 2,
            background: 'linear-gradient(135deg, #111827 0%, #1e1b4b 100%)',
            borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
          }}
        >
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Stack direction="row" spacing={1.5} alignItems="center">
              <Avatar
                sx={{
                  bgcolor: '#4f46e5',
                  width: 36,
                  height: 36,
                  boxShadow: '0 0 12px rgba(99, 102, 241, 0.5)',
                }}
              >
                <AutoAwesomeIcon sx={{ fontSize: 20 }} />
              </Avatar>
              <Box>
                <Typography variant="subtitle1" fontWeight={700} sx={{ color: '#ffffff' }}>
                  CA Review & AI Assistant
                </Typography>
                <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                  {activeClient ? `${activeClient.name} • ${activePeriod?.label || ''}` : 'No Client Selected'}
                </Typography>
              </Box>
            </Stack>

            <Stack direction="row" spacing={0.5} alignItems="center">
              {activeClient && activePeriod && (
                <>
                  <Tooltip title="Start New Chat Session">
                    <IconButton size="small" onClick={handleNewChat} sx={{ color: '#94a3b8', '&:hover': { color: '#ffffff' } }}>
                      <AddIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Open Full-Screen Review Page">
                    <IconButton size="small" onClick={handleOpenFullPage} sx={{ color: '#94a3b8', '&:hover': { color: '#ffffff' } }}>
                      <OpenInNewIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </>
              )}
              <IconButton size="small" onClick={() => setOpen(false)} sx={{ color: '#94a3b8', '&:hover': { color: '#ffffff' } }}>
                <CloseIcon fontSize="small" />
              </IconButton>
            </Stack>
          </Stack>
        </Box>

        {/* Drawer Content */}
        {!activeClient || !activePeriod ? (
          <Box sx={{ p: 3, flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Alert severity="info" sx={{ bgcolor: 'rgba(30, 41, 59, 0.9)', color: '#f8fafc', border: '1px solid rgba(255,255,255,0.1)' }}>
              Please select an active client company and accounting period to chat with the CA AI Review Assistant.
            </Alert>
          </Box>
        ) : (
          <Box
            sx={{
              flex: 1,
              overflowY: 'auto',
              p: 2,
              display: 'flex',
              flexDirection: 'column',
              gap: 2,
            }}
          >
            {error && (
              <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 1 }}>
                {error}
              </Alert>
            )}

            {loading ? (
              <Box display="flex" justifyContent="center" alignItems="center" flex={1}>
                <CircularProgress size={32} sx={{ color: '#6366f1' }} />
              </Box>
            ) : (
              <>
                {/* Suggestions Pills if few messages */}
                {(!activeConv?.messages || activeConv.messages.length <= 1) && (
                  <Box sx={{ mb: 1 }}>
                    <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 600, display: 'block', mb: 1 }}>
                      QUICK QUERIES
                    </Typography>
                    <Stack spacing={1}>
                      {SUGGESTIONS.map((s, idx) => (
                        <Paper
                          key={idx}
                          onClick={() => void handleSend(s.prompt)}
                          sx={{
                            p: 1.2,
                            borderRadius: '8px',
                            bgcolor: 'rgba(30, 41, 59, 0.7)',
                            border: '1px solid rgba(255, 255, 255, 0.08)',
                            cursor: 'pointer',
                            transition: 'all 0.2s',
                            '&:hover': {
                              bgcolor: 'rgba(99, 102, 241, 0.15)',
                              borderColor: 'rgba(99, 102, 241, 0.4)',
                              transform: 'translateX(3px)',
                            },
                          }}
                        >
                          <Stack direction="row" spacing={1} alignItems="center">
                            <Typography fontSize="1rem">{s.icon}</Typography>
                            <Box>
                              <Typography variant="body2" fontWeight={600} sx={{ color: '#e2e8f0', fontSize: '0.8rem' }}>
                                {s.label}
                              </Typography>
                            </Box>
                          </Stack>
                        </Paper>
                      ))}
                    </Stack>
                  </Box>
                )}

                {/* Messages List */}
                {activeConv?.messages && activeConv.messages.length > 0 ? (
                  activeConv.messages.map((msg) => (
                    <MessageBubble
                      key={msg.id}
                      message={msg}
                      onReviewProposal={handleReviewProposal}
                      canApprove={canApprove}
                    />
                  ))
                ) : (
                  <Box sx={{ textAlign: 'center', py: 4, color: '#64748b' }}>
                    <ChatIcon sx={{ fontSize: 40, opacity: 0.5, mb: 1 }} />
                    <Typography variant="body2">Ask any question about your financial data, trial balances, or adjustments.</Typography>
                  </Box>
                )}

                {sending && (
                  <Stack direction="row" spacing={1.5} alignItems="center" sx={{ pl: 1 }}>
                    <CircularProgress size={16} sx={{ color: '#6366f1' }} />
                    <Typography variant="caption" sx={{ color: '#a5b4fc' }}>
                      CA AI is reviewing data...
                    </Typography>
                  </Stack>
                )}

                <div ref={messagesEndRef} />
              </>
            )}
          </Box>
        )}

        {/* Drawer Footer Input */}
        {activeClient && activePeriod && (
          <Box sx={{ p: 2, borderTop: '1px solid rgba(255, 255, 255, 0.1)', bgcolor: '#111827' }}>
            <Paper
              sx={{
                p: '4px 8px',
                display: 'flex',
                alignItems: 'center',
                bgcolor: 'rgba(30, 41, 59, 0.8)',
                border: '1px solid rgba(255, 255, 255, 0.12)',
                borderRadius: '12px',
                '&:focus-within': {
                  borderColor: '#6366f1',
                  boxShadow: '0 0 0 2px rgba(99, 102, 241, 0.25)',
                },
              }}
            >
              <InputBase
                sx={{ ml: 1, flex: 1, color: '#ffffff', fontSize: '0.875rem' }}
                placeholder="Ask CA AI, report an error, or request re-execution..."
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={sending}
                multiline
                maxRows={3}
              />
              <IconButton
                color="primary"
                onClick={() => void handleSend()}
                disabled={!inputMessage.trim() || sending}
                sx={{
                  bgcolor: '#4f46e5',
                  color: '#ffffff',
                  width: 32,
                  height: 32,
                  '&:hover': { bgcolor: '#4338ca' },
                  '&.Mui-disabled': { bgcolor: 'rgba(255, 255, 255, 0.08)', color: 'rgba(255, 255, 255, 0.3)' },
                }}
              >
                {sending ? <CircularProgress size={16} sx={{ color: '#ffffff' }} /> : <SendIcon sx={{ fontSize: 16 }} />}
              </IconButton>
            </Paper>
          </Box>
        )}
      </Drawer>
    </>
  );
};
