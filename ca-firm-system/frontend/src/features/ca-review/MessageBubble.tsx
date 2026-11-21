import React from 'react';
import {
  Avatar,
  Box,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import {
  SmartToy,
  Person,
  HelpOutline,
  Build,
  PlaylistAddCheck,
  CheckCircle,
  TableChart,
} from '@mui/icons-material';
import type { CorrectionProposal, Message } from '../../types/caReview';
import { CorrectionProposalCard } from './CorrectionProposalCard';

interface Props {
  message: Message;
  associatedProposal?: CorrectionProposal;
  onReviewProposal: (proposalId: string, decision: 'approve' | 'reject', notes?: string) => Promise<void>;
  canApprove?: boolean;
}

export const MessageBubble: React.FC<Props> = ({
  message,
  associatedProposal,
  onReviewProposal,
  canApprove = true,
}) => {
  const isUser = message.sender_type === 'user';
  const meta = message.message_metadata || {};
  const instructionResult = meta.instruction_result;
  const reexecResult = meta.reexecution_result;

  const renderIntentBadge = () => {
    if (isUser) return null;
    const intent = message.intent;
    if (!intent) return null;

    let label = 'AI Response';
    let icon = <SmartToy sx={{ fontSize: 14 }} />;
    let color: 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' = 'info';

    if (intent === 'question') {
      label = 'Question Answered';
      icon = <HelpOutline sx={{ fontSize: 14 }} />;
      color = 'info';
    } else if (intent === 'error_report' || intent === 'correction_request') {
      label = 'Correction Proposal';
      icon = <Build sx={{ fontSize: 14 }} />;
      color = 'warning';
    } else if (intent === 'instruction') {
      label = 'Instruction Executed';
      icon = <PlaylistAddCheck sx={{ fontSize: 14 }} />;
      color = 'primary';
    } else if (intent === 'approval_action') {
      label = 'Pipeline Re-executed';
      icon = <CheckCircle sx={{ fontSize: 14 }} />;
      color = 'success';
    }

    return (
      <Chip
        icon={icon}
        label={label}
        size="small"
        color={color}
        sx={{ height: 22, fontSize: '0.68rem', fontWeight: 700, mb: 1 }}
      />
    );
  };

  // Simple Markdown Parser for clear chat rendering
  const renderFormattedContent = (content: string) => {
    const lines = content.split('\n');
    const elements: React.ReactNode[] = [];
    let tableLines: string[] = [];
    let inTable = false;

    const flushTable = (key: number) => {
      if (tableLines.length < 2) return null;
      const headers = tableLines[0]
        .split('|')
        .map((h) => h.trim())
        .filter(Boolean);
      const rows = tableLines.slice(2).map((r) =>
        r
          .split('|')
          .map((c) => c.trim())
          .filter(Boolean),
      );

      return (
        <TableContainer
          key={`tbl-${key}`}
          component={Paper}
          sx={{
            my: 1.5,
            bgcolor: 'rgba(15, 23, 42, 0.7)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '8px',
          }}
        >
          <Table size="small">
            <TableHead sx={{ bgcolor: 'rgba(30, 41, 59, 0.8)' }}>
              <TableRow>
                {headers.map((h, i) => (
                  <TableCell key={i} sx={{ color: '#38bdf8', fontWeight: 700, fontSize: '0.75rem', py: 1 }}>
                    {h.replace(/\*\*/g, '')}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row, ri) => (
                <TableRow key={ri} sx={{ '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.03)' } }}>
                  {row.map((cell, ci) => (
                    <TableCell key={ci} sx={{ color: '#f1f5f9', fontSize: '0.75rem', py: 0.8 }}>
                      {cell.startsWith('`') && cell.endsWith('`') ? (
                        <Box
                          component="span"
                          sx={{
                            fontFamily: 'monospace',
                            bgcolor: 'rgba(255, 255, 255, 0.1)',
                            px: 0.6,
                            py: 0.2,
                            borderRadius: '4px',
                          }}
                        >
                          {cell.replace(/`/g, '')}
                        </Box>
                      ) : cell.startsWith('**') && cell.endsWith('**') ? (
                        <strong>{cell.replace(/\*\*/g, '')}</strong>
                      ) : (
                        cell
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      );
    };

    lines.forEach((line, idx) => {
      if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
        inTable = true;
        tableLines.push(line.trim());
        return;
      } else if (inTable) {
        elements.push(flushTable(idx));
        tableLines = [];
        inTable = false;
      }

      if (line.startsWith('### ')) {
        elements.push(
          <Typography key={idx} variant="subtitle1" fontWeight={700} sx={{ color: '#38bdf8', mt: 1.5, mb: 0.5 }}>
            {line.replace('### ', '')}
          </Typography>,
        );
      } else if (line.startsWith('#### ')) {
        elements.push(
          <Typography key={idx} variant="subtitle2" fontWeight={700} sx={{ color: '#a5b4fc', mt: 1, mb: 0.5 }}>
            {line.replace('#### ', '')}
          </Typography>,
        );
      } else if (line.startsWith('> ')) {
        elements.push(
          <Box
            key={idx}
            sx={{
              p: 1.2,
              my: 1,
              borderRadius: '6px',
              bgcolor: 'rgba(99, 102, 241, 0.1)',
              borderLeft: '4px solid #6366f1',
              color: '#cbd5e1',
              fontSize: '0.85rem',
            }}
          >
            {line.replace('> ', '').replace(/\*\*/g, '')}
          </Box>,
        );
      } else if (line.startsWith('- ') || line.startsWith('* ')) {
        const text = line.replace(/^[-*]\s+/, '');
        elements.push(
          <Typography key={idx} variant="body2" sx={{ color: '#e2e8f0', ml: 1.5, mb: 0.4 }}>
            •{' '}
            {text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((chunk, ci) => {
              if (chunk.startsWith('`') && chunk.endsWith('`')) {
                return (
                  <Box
                    key={ci}
                    component="span"
                    sx={{
                      fontFamily: 'monospace',
                      bgcolor: 'rgba(255, 255, 255, 0.1)',
                      px: 0.5,
                      py: 0.1,
                      borderRadius: '4px',
                      fontSize: '0.8rem',
                    }}
                  >
                    {chunk.replace(/`/g, '')}
                  </Box>
                );
              }
              if (chunk.startsWith('**') && chunk.endsWith('**')) {
                return <strong key={ci}>{chunk.replace(/\*\*/g, '')}</strong>;
              }
              return chunk;
            })}
          </Typography>,
        );
      } else if (line.trim().length > 0) {
        elements.push(
          <Typography key={idx} variant="body2" sx={{ color: '#e2e8f0', mb: 1, lineHeight: 1.6 }}>
            {line.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((chunk, ci) => {
              if (chunk.startsWith('`') && chunk.endsWith('`')) {
                return (
                  <Box
                    key={ci}
                    component="span"
                    sx={{
                      fontFamily: 'monospace',
                      bgcolor: 'rgba(255, 255, 255, 0.1)',
                      px: 0.5,
                      py: 0.1,
                      borderRadius: '4px',
                      fontSize: '0.8rem',
                    }}
                  >
                    {chunk.replace(/`/g, '')}
                  </Box>
                );
              }
              if (chunk.startsWith('**') && chunk.endsWith('**')) {
                return <strong key={ci}>{chunk.replace(/\*\*/g, '')}</strong>;
              }
              return chunk;
            })}
          </Typography>,
        );
      }
    });

    if (inTable) {
      elements.push(flushTable(9999));
    }

    return elements;
  };

  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        mb: 2.5,
        width: '100%',
      }}
    >
      <Stack
        direction={isUser ? 'row-reverse' : 'row'}
        spacing={1.5}
        alignItems="flex-start"
        sx={{ maxWidth: { xs: '92%', md: '80%' } }}
      >
        {/* Avatar */}
        <Avatar
          sx={{
            width: 34,
            height: 34,
            bgcolor: isUser ? '#4f46e5' : '#0ea5e9',
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.25)',
          }}
        >
          {isUser ? <Person sx={{ fontSize: 18 }} /> : <SmartToy sx={{ fontSize: 18 }} />}
        </Avatar>

        {/* Message Container */}
        <Box sx={{ width: '100%' }}>
          <Box
            sx={{
              p: 2,
              borderRadius: isUser ? '16px 4px 16px 16px' : '4px 16px 16px 16px',
              bgcolor: isUser
                ? 'linear-gradient(135deg, #4338ca 0%, #312e81 100%)'
                : 'rgba(30, 41, 59, 0.95)',
              background: isUser
                ? 'linear-gradient(135deg, #4f46e5 0%, #3730a3 100%)'
                : 'rgba(30, 41, 59, 0.95)',
              color: '#f8fafc',
              border: '1px solid',
              borderColor: isUser ? 'rgba(99, 102, 241, 0.3)' : 'rgba(255, 255, 255, 0.08)',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
            }}
          >
            {renderIntentBadge()}

            {renderFormattedContent(message.content)}

            {/* Instruction Result Card if present */}
            {instructionResult && (
              <Box
                sx={{
                  mt: 2,
                  p: 1.5,
                  borderRadius: '8px',
                  bgcolor: 'rgba(15, 23, 42, 0.6)',
                  border: '1px solid rgba(56, 189, 248, 0.2)',
                }}
              >
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                  <TableChart sx={{ color: '#38bdf8', fontSize: 18 }} />
                  <Typography variant="caption" fontWeight={700} sx={{ color: '#38bdf8' }}>
                    AUDIT EXCEPTION SUMMARY ({instructionResult.flagged_missing_doc_count} Flagged of {instructionResult.scanned_transactions} Scanned)
                  </Typography>
                </Stack>
                <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                  Transactions matching criteria were verified against stored invoice registers.
                </Typography>
              </Box>
            )}

            {/* Reexecution Result Card if present */}
            {reexecResult && (
              <Box
                sx={{
                  mt: 2,
                  p: 1.5,
                  borderRadius: '8px',
                  bgcolor: 'rgba(16, 185, 129, 0.08)',
                  border: '1px solid rgba(16, 185, 129, 0.3)',
                }}
              >
                <Stack direction="row" spacing={1} alignItems="center">
                  <CheckCircle sx={{ color: '#10b981', fontSize: 18 }} />
                  <Typography variant="body2" fontWeight={700} sx={{ color: '#10b981' }}>
                    Re-execution Completed Successfully
                  </Typography>
                </Stack>
                <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mt: 0.5 }}>
                  Agents Re-executed: {reexecResult.executed_agents?.join(' ➔ ')}
                </Typography>
              </Box>
            )}
          </Box>

          {/* Render Associated Proposal Card directly inside conversation stream */}
          {associatedProposal && (
            <CorrectionProposalCard
              proposal={associatedProposal}
              onReview={onReviewProposal}
              canApprove={canApprove}
            />
          )}

          <Typography
            variant="caption"
            sx={{
              display: 'block',
              mt: 0.5,
              textAlign: isUser ? 'right' : 'left',
              color: '#64748b',
              fontSize: '0.68rem',
            }}
          >
            {new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </Typography>
        </Box>
      </Stack>
    </Box>
  );
};
