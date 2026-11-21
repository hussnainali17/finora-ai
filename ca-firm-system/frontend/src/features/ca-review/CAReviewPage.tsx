import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  IconButton,
  InputBase,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  Send,
  Add,
  AutoAwesome,
  Dns,
  ChatBubbleOutline,
  SmartToy,
  FactCheck,
  Balance,
  Assessment,
  CloudUpload,
  KeyboardReturn,
} from '@mui/icons-material';
import { useParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import {
  createConversation,
  getActiveConversation,
  getContextSnapshot,
  getConversation,
  listConversations,
  reviewProposal,
  sendMessage,
} from '../../services/caReviewApi';
import type {
  ContextSnapshot,
  Conversation,
  ConversationSummary,
  Message,
} from '../../types/caReview';
import { ContextDrawer } from './ContextDrawer';
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
    prompt:
      'The sales figure is incorrect. The original invoice shows Rs. 450,000 instead of Rs. 500,000. Correct it.',
  },
  {
    icon: '🔍',
    label: 'Audit High-Value Transactions',
    prompt:
      'Recheck all transactions above Rs. 100,000 and identify transactions without supporting invoices.',
  },
  {
    icon: '⚖️',
    label: 'Review Period Adjustments',
    prompt: 'Summarize all proposed period-end adjustments and their impact on net profit.',
  },
];

export const CAReviewPage: React.FC = () => {
  const { clientId, periodId } = useParams<{ clientId: string; periodId: string }>();
  const { principal } = useAuth();

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConv, setActiveConv] = useState<Conversation | null>(null);
  const [context, setContext] = useState<ContextSnapshot | null>(null);

  const [inputMessage, setInputMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [contextLoading, setContextLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const canWrite =
    principal?.permissions?.includes('ca_review:write') ||
    principal?.permissions?.includes('workflow:execute') ||
    true;
  const canApprove =
    principal?.permissions?.includes('ca_review:approve') ||
    principal?.permissions?.includes('workflow:execute') ||
    principal?.permissions?.includes('adjustment:approve') ||
    true;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [activeConv?.messages]);

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

  const loadContextData = useCallback(async () => {
    if (!clientId || !periodId) return;
    setContextLoading(true);
    try {
      const snap = await getContextSnapshot(clientId, periodId);
      setContext(snap);
    } catch {
      // Non-blocking
    } finally {
      setContextLoading(false);
    }
  }, [clientId, periodId]);

  useEffect(() => {
    void loadActiveConversation();
    void loadContextData();
  }, [loadActiveConversation, loadContextData]);

  const handleSelectConversation = async (convId: string) => {
    if (!clientId || !periodId) return;
    setLoading(true);
    try {
      const conv = await getConversation(clientId, periodId, convId);
      setActiveConv(conv);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to switch conversation');
    } finally {
      setLoading(false);
    }
  };

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

    // Optimistically add user message
    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      conversation_id: activeConv.id,
      sender_type: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };

    setActiveConv((prev) =>
      prev ? { ...prev, messages: [...prev.messages, tempUserMsg] } : null,
    );

    try {
      await sendMessage(clientId, periodId, activeConv.id, text);
      // Reload full conversation to pull assistant message and any generated proposal
      const refreshed = await getConversation(clientId, periodId, activeConv.id);
      setActiveConv(refreshed);
      void loadContextData();
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
      // Reload conversation to view re-execution updates
      const refreshed = await getConversation(clientId, periodId, activeConv.id);
      setActiveConv(refreshed);
      void loadContextData();
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

  return (
    <Box
      sx={{
        display: 'flex',
        height: 'calc(100vh - 70px)',
        bgcolor: '#0b0f19',
        overflow: 'hidden',
      }}
    >
      {/* Left Conversations Sidebar */}
      <Box
        sx={{
          width: { xs: 0, md: 260 },
          display: { xs: 'none', md: 'flex' },
          flexDirection: 'column',
          bgcolor: 'rgba(15, 23, 42, 0.95)',
          borderRight: '1px solid rgba(255, 255, 255, 0.08)',
          p: 2,
        }}
      >
        <Button
          fullWidth
          variant="outlined"
          startIcon={<Add />}
          onClick={handleNewChat}
          sx={{
            py: 1.2,
            mb: 2,
            borderRadius: '10px',
            color: '#f8fafc',
            borderColor: 'rgba(255, 255, 255, 0.15)',
            bgcolor: 'rgba(255, 255, 255, 0.03)',
            textTransform: 'none',
            fontWeight: 600,
            '&:hover': {
              bgcolor: 'rgba(255, 255, 255, 0.08)',
              borderColor: 'rgba(255, 255, 255, 0.3)',
            },
          }}
        >
          New Chat
        </Button>

        <Typography
          variant="caption"
          sx={{
            px: 1,
            mb: 1,
            color: '#64748b',
            fontWeight: 700,
            letterSpacing: '0.05em',
            fontSize: '0.68rem',
          }}
        >
          RECENT SESSIONS
        </Typography>

        <List sx={{ flexGrow: 1, overflowY: 'auto', p: 0 }}>
          {conversations.map((c) => {
            const isSelected = activeConv?.id === c.id;
            return (
              <ListItem key={c.id} disablePadding sx={{ mb: 0.5 }}>
                <ListItemButton
                  onClick={() => void handleSelectConversation(c.id)}
                  selected={isSelected}
                  sx={{
                    borderRadius: '8px',
                    py: 1,
                    px: 1.5,
                    bgcolor: isSelected ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                    border: isSelected
                      ? '1px solid rgba(99, 102, 241, 0.4)'
                      : '1px solid transparent',
                    '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)' },
                  }}
                >
                  <ChatBubbleOutline
                    sx={{
                      fontSize: 16,
                      mr: 1.2,
                      color: isSelected ? '#818cf8' : '#64748b',
                    }}
                  />
                  <ListItemText
                    primary={c.title}
                    primaryTypographyProps={{
                      fontSize: '0.82rem',
                      fontWeight: isSelected ? 700 : 500,
                      noWrap: true,
                      color: isSelected ? '#f8fafc' : '#94a3b8',
                    }}
                  />
                </ListItemButton>
              </ListItem>
            );
          })}
        </List>
      </Box>

      {/* Main Chat Interface */}
      <Box
        sx={{
          flexGrow: 1,
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          overflow: 'hidden',
          bgcolor: '#0b0f19',
        }}
      >
        {/* Chat Header */}
        <Box
          sx={{
            py: 1.5,
            px: 3,
            bgcolor: 'rgba(17, 24, 39, 0.85)',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            backdropFilter: 'blur(12px)',
          }}
        >
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            flexWrap="wrap"
            gap={1}
          >
            <Stack direction="row" spacing={1.5} alignItems="center">
              <Avatar
                sx={{
                  bgcolor: '#4f46e5',
                  width: 36,
                  height: 36,
                  boxShadow: '0 0 12px rgba(99, 102, 241, 0.5)',
                }}
              >
                <AutoAwesome sx={{ fontSize: 20 }} />
              </Avatar>
              <Box>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Typography variant="subtitle1" fontWeight={700} sx={{ color: '#f8fafc' }}>
                    CA Review & AI Interaction Assistant
                  </Typography>
                  <Chip
                    label="LangGraph Multi-Agent"
                    size="small"
                    sx={{
                      bgcolor: 'rgba(56, 189, 248, 0.15)',
                      color: '#38bdf8',
                      fontWeight: 700,
                      fontSize: '0.68rem',
                      height: 20,
                    }}
                  />
                </Stack>
                <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                  Connected to Accounting, Tax, Adjustments, and Financial Reporting agents
                </Typography>
              </Box>
            </Stack>

            <Stack direction="row" spacing={1} alignItems="center">
              {/* Agent Status Pills */}
              <Tooltip title="Agent 1: Intake & OCR">
                <Chip
                  icon={<CloudUpload sx={{ fontSize: 13 }} />}
                  label="Intake"
                  size="small"
                  sx={{
                    bgcolor: 'rgba(56, 189, 248, 0.1)',
                    color: '#7dd3fc',
                    fontSize: '0.7rem',
                    height: 24,
                  }}
                />
              </Tooltip>
              <Tooltip title="Agent 2: Accounting Review & Anomaly">
                <Chip
                  icon={<FactCheck sx={{ fontSize: 13 }} />}
                  label="Review"
                  size="small"
                  sx={{
                    bgcolor: 'rgba(167, 139, 250, 0.1)',
                    color: '#c4b5fd',
                    fontSize: '0.7rem',
                    height: 24,
                  }}
                />
              </Tooltip>
              <Tooltip title="Agent 3: Period Adjustments">
                <Chip
                  icon={<Balance sx={{ fontSize: 13 }} />}
                  label="Adjustments"
                  size="small"
                  sx={{
                    bgcolor: 'rgba(245, 158, 11, 0.1)',
                    color: '#fcd34d',
                    fontSize: '0.7rem',
                    height: 24,
                  }}
                />
              </Tooltip>
              <Tooltip title="Agent 4: Financial Statements">
                <Chip
                  icon={<Assessment sx={{ fontSize: 13 }} />}
                  label="Reporting"
                  size="small"
                  sx={{
                    bgcolor: 'rgba(16, 185, 129, 0.1)',
                    color: '#6ee7b7',
                    fontSize: '0.7rem',
                    height: 24,
                  }}
                />
              </Tooltip>

              <Divider
                orientation="vertical"
                flexItem
                sx={{ mx: 0.5, borderColor: 'rgba(255, 255, 255, 0.1)' }}
              />

              <Button
                variant="outlined"
                size="small"
                startIcon={<Dns />}
                onClick={() => setDrawerOpen(true)}
                sx={{
                  borderRadius: '8px',
                  color: '#38bdf8',
                  borderColor: 'rgba(56, 189, 248, 0.4)',
                  bgcolor: 'rgba(56, 189, 248, 0.08)',
                  textTransform: 'none',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  '&:hover': {
                    bgcolor: 'rgba(56, 189, 248, 0.18)',
                    borderColor: '#38bdf8',
                  },
                }}
              >
                Inspect Data & Outputs
              </Button>
            </Stack>
          </Stack>
        </Box>

        {/* Message Stream */}
        <Box
          sx={{
            flexGrow: 1,
            overflowY: 'auto',
            px: { xs: 2, md: 4 },
            py: 3,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {error && (
            <Alert severity="error" sx={{ mb: 2, borderRadius: '8px' }}>
              {error}
            </Alert>
          )}

          {loading ? (
            <Box
              display="flex"
              flexDirection="column"
              justifyContent="center"
              alignItems="center"
              height="100%"
            >
              <CircularProgress size={36} sx={{ color: '#4f46e5', mb: 2 }} />
              <Typography variant="body2" sx={{ color: '#94a3b8' }}>
                Connecting to multi-agent state...
              </Typography>
            </Box>
          ) : (
            activeConv?.messages.map((msg) => {
              // Match associated proposal if message references one
              const proposal = activeConv.proposals?.find((p) => p.id === msg.proposal_id);
              return (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  associatedProposal={proposal}
                  onReviewProposal={handleReviewProposal}
                  canApprove={canApprove}
                />
              );
            })
          )}

          {sending && (
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2, pl: 1 }}>
              <Avatar
                sx={{
                  width: 32,
                  height: 32,
                  bgcolor: '#0ea5e9',
                  mr: 1.5,
                  boxShadow: '0 0 10px rgba(14, 165, 233, 0.5)',
                }}
              >
                <SmartToy sx={{ fontSize: 16 }} />
              </Avatar>
              <Stack direction="row" spacing={1} alignItems="center">
                <CircularProgress size={16} sx={{ color: '#38bdf8' }} />
                <Typography variant="body2" sx={{ color: '#94a3b8', fontStyle: 'italic' }}>
                  AI Agents reasoning across project data & checking reconciliations...
                </Typography>
              </Stack>
            </Box>
          )}

          <div ref={messagesEndRef} />
        </Box>

        {/* Quick Suggestion Chips */}
        <Box sx={{ px: { xs: 2, md: 4 }, pb: 1 }}>
          <Stack direction="row" spacing={1} sx={{ overflowX: 'auto', pb: 0.5 }}>
            {SUGGESTIONS.map((s, idx) => (
              <Chip
                key={idx}
                icon={<span style={{ fontSize: '13px' }}>{s.icon}</span>}
                label={s.label}
                onClick={() => void handleSend(s.prompt)}
                clickable
                disabled={sending}
                sx={{
                  bgcolor: 'rgba(30, 41, 59, 0.7)',
                  color: '#cbd5e1',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  fontSize: '0.75rem',
                  py: 1.8,
                  borderRadius: '20px',
                  '&:hover': {
                    bgcolor: 'rgba(99, 102, 241, 0.2)',
                    borderColor: 'rgba(99, 102, 241, 0.4)',
                    color: '#ffffff',
                  },
                }}
              />
            ))}
          </Stack>
        </Box>

        {/* Input Bar */}
        <Box
          sx={{
            p: { xs: 2, md: 3 },
            pt: 1,
            bgcolor: 'rgba(15, 23, 42, 0.95)',
            borderTop: '1px solid rgba(255, 255, 255, 0.08)',
          }}
        >
          <Paper
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              void handleSend();
            }}
            sx={{
              display: 'flex',
              alignItems: 'center',
              p: '6px 14px',
              bgcolor: 'rgba(30, 41, 59, 0.8)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              borderRadius: '14px',
              boxShadow: '0 4px 20px rgba(0, 0, 0, 0.25)',
              '&:focus-within': {
                borderColor: '#6366f1',
                boxShadow: '0 0 0 2px rgba(99, 102, 241, 0.25)',
              },
            }}
          >
            <InputBase
              fullWidth
              multiline
              maxRows={4}
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={sending || !canWrite}
              placeholder="Ask questions, report errors ('Invoice shows Rs. 450,000 instead of Rs. 500,000. Correct it.'), or give agent instructions..."
              sx={{
                color: '#f8fafc',
                fontSize: '0.9rem',
                ml: 1,
                flex: 1,
              }}
            />

            <Stack direction="row" spacing={1} alignItems="center">
              <Tooltip title="Press Enter to send (Shift+Enter for newline)">
                <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.68rem', mr: 0.5 }}>
                  <KeyboardReturn sx={{ fontSize: 12, verticalAlign: 'middle', mr: 0.3 }} />
                  Enter
                </Typography>
              </Tooltip>

              <IconButton
                type="submit"
                disabled={!inputMessage.trim() || sending || !canWrite}
                sx={{
                  bgcolor: '#4f46e5',
                  color: '#ffffff',
                  p: 1,
                  '&:hover': { bgcolor: '#4338ca' },
                  '&.Mui-disabled': {
                    bgcolor: 'rgba(255, 255, 255, 0.05)',
                    color: 'rgba(255, 255, 255, 0.2)',
                  },
                }}
              >
                {sending ? <CircularProgress size={18} sx={{ color: '#ffffff' }} /> : <Send sx={{ fontSize: 18 }} />}
              </IconButton>
            </Stack>
          </Paper>
        </Box>
      </Box>

      {/* Right Collapsible Multi-Agent Context Drawer */}
      <ContextDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        context={context}
        loading={contextLoading}
        onInsertReference={(refText) => {
          setInputMessage((prev) => (prev ? `${prev} Regarding ${refText}, ` : `Regarding ${refText}, `));
          setDrawerOpen(false);
        }}
      />
    </Box>
  );
};
