import React, { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import {
  CheckCircle,
  Cancel,
  PlayCircleOutline,
  CompareArrows,
  VerifiedUser,
  AutoAwesome,
  ArrowForward,
} from '@mui/icons-material';
import type { CorrectionProposal } from '../../types/caReview';

interface Props {
  proposal: CorrectionProposal;
  onReview: (proposalId: string, decision: 'approve' | 'reject', notes?: string) => Promise<void>;
  canApprove?: boolean;
}

export const CorrectionProposalCard: React.FC<Props> = ({
  proposal,
  onReview,
  canApprove = true,
}) => {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [decision, setDecision] = useState<'approve' | 'reject'>('approve');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const orig = proposal.original_data || {};
  const prop = proposal.proposed_data || {};

  const origAmt = orig.recorded_amount ?? orig.amount;
  const propAmt = prop.corrected_amount ?? prop.amount;
  const diff = prop.difference ?? (propAmt && origAmt ? propAmt - origAmt : null);

  const formatPkr = (val: number | null | undefined) => {
    if (val === null || val === undefined || isNaN(val)) return '—';
    return `PKR ${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const handleOpenReview = (dec: 'approve' | 'reject') => {
    setDecision(dec);
    setNotes(dec === 'approve' ? 'Verified against source document. Approved for re-execution.' : '');
    setError(null);
    setDialogOpen(true);
  };

  const handleConfirm = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onReview(proposal.id, decision, notes);
      setDialogOpen(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Action failed');
    } finally {
      setSubmitting(false);
    }
  };

  const isPending = proposal.status === 'pending';
  const isApplied = proposal.status === 'applied';
  const isRejected = proposal.status === 'rejected';

  return (
    <Card
      sx={{
        mt: 1.5,
        mb: 1.5,
        bgcolor: 'rgba(15, 23, 42, 0.85)',
        border: '1px solid',
        borderColor: isApplied
          ? 'rgba(16, 185, 129, 0.4)'
          : isRejected
          ? 'rgba(244, 63, 94, 0.3)'
          : 'rgba(99, 102, 241, 0.4)',
        borderRadius: '12px',
        boxShadow: '0 4px 20px rgba(0, 0, 0, 0.3)',
      }}
    >
      <CardContent sx={{ p: 2.5, '&:last-child': { pb: 2.5 } }}>
        {/* Header & Status */}
        <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
          <Stack direction="row" spacing={1} alignItems="center">
            <AutoAwesome sx={{ color: '#818cf8', fontSize: 20 }} />
            <Typography variant="subtitle1" fontWeight={700} sx={{ color: '#f8fafc' }}>
              {proposal.title}
            </Typography>
          </Stack>

          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              label={proposal.target_agent.replace('_', ' ').toUpperCase()}
              size="small"
              sx={{
                bgcolor: 'rgba(99, 102, 241, 0.15)',
                color: '#a5b4fc',
                fontWeight: 600,
                fontSize: '0.72rem',
              }}
            />
            <Chip
              label={proposal.status.toUpperCase()}
              size="small"
              color={isApplied ? 'success' : isRejected ? 'error' : 'warning'}
              sx={{ fontWeight: 700, fontSize: '0.72rem' }}
            />
          </Stack>
        </Stack>

        <Typography variant="body2" sx={{ color: '#94a3b8', mt: 1, mb: 2 }}>
          {proposal.description}
        </Typography>

        {/* Diff Comparison Box */}
        <Box
          sx={{
            p: 1.5,
            borderRadius: '8px',
            bgcolor: 'rgba(30, 41, 59, 0.6)',
            border: '1px solid rgba(255, 255, 255, 0.05)',
            mb: 2,
          }}
        >
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={2}
            justifyContent="space-around"
            alignItems="center"
          >
            {/* Current Value */}
            <Box textAlign="center">
              <Typography variant="caption" sx={{ color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                Current Extracted Value
              </Typography>
              <Typography variant="h6" fontWeight={700} sx={{ color: '#ef4444', mt: 0.2 }}>
                {formatPkr(origAmt)}
              </Typography>
              <Typography variant="caption" sx={{ color: '#64748b' }}>
                Ref: {orig.reference || proposal.target_entity_id}
              </Typography>
            </Box>

            <CompareArrows sx={{ color: '#818cf8', fontSize: 28, display: { xs: 'none', sm: 'block' } }} />

            {/* Proposed Value */}
            <Box textAlign="center">
              <Typography variant="caption" sx={{ color: '#38bdf8', textTransform: 'uppercase', fontWeight: 600 }}>
                CA Proposed Correct Value
              </Typography>
              <Typography variant="h6" fontWeight={700} sx={{ color: '#10b981', mt: 0.2 }}>
                {formatPkr(propAmt)}
              </Typography>
              {diff !== null && (
                <Chip
                  label={`Variance: ${diff < 0 ? '-' : '+'}${formatPkr(Math.abs(diff))}`}
                  size="small"
                  sx={{
                    height: 20,
                    fontSize: '0.68rem',
                    bgcolor: 'rgba(56, 189, 248, 0.15)',
                    color: '#38bdf8',
                    fontWeight: 700,
                  }}
                />
              )}
            </Box>
          </Stack>
        </Box>

        {/* Downstream Re-execution Plan */}
        <Box sx={{ mb: 2 }}>
          <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 600, display: 'block', mb: 0.8 }}>
            DOWNSTREAM RE-EXECUTION PIPELINE:
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            {proposal.reexecution_plan?.map((agent, idx) => (
              <React.Fragment key={agent}>
                <Chip
                  label={agent.replace('_', ' ')}
                  size="small"
                  sx={{
                    bgcolor: 'rgba(56, 189, 248, 0.1)',
                    color: '#bae6fd',
                    border: '1px solid rgba(56, 189, 248, 0.2)',
                    fontSize: '0.72rem',
                    textTransform: 'capitalize',
                  }}
                />
                {idx < (proposal.reexecution_plan?.length || 0) - 1 && (
                  <ArrowForward sx={{ color: '#64748b', fontSize: 14 }} />
                )}
              </React.Fragment>
            ))}
          </Stack>
        </Box>

        {/* Re-execution results if applied */}
        {isApplied && proposal.reexecution_result && (
          <Box
            sx={{
              p: 1.5,
              borderRadius: '8px',
              bgcolor: 'rgba(16, 185, 129, 0.08)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              mb: 1,
            }}
          >
            <Stack direction="row" spacing={1} alignItems="center">
              <CheckCircle sx={{ color: '#10b981', fontSize: 18 }} />
              <Typography variant="body2" fontWeight={700} sx={{ color: '#10b981' }}>
                Pipeline Re-executed & Outputs Validated
              </Typography>
            </Stack>
            <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mt: 0.5 }}>
              Re-executed: {proposal.reexecution_result.executed_agents?.join(', ')} • Validation status: {proposal.reexecution_result.validation_status}
            </Typography>
            {proposal.reviewer_notes && (
              <Typography variant="caption" sx={{ color: '#cbd5e1', display: 'block', mt: 0.5 }}>
                CA Notes: &quot;{proposal.reviewer_notes}&quot;
              </Typography>
            )}
          </Box>
        )}

        {/* Action Buttons for Pending */}
        {isPending && (
          <Box sx={{ mt: 2, pt: 1.5, borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}>
            <Stack direction="row" spacing={1.5} justifyContent="flex-end">
              <Button
                variant="outlined"
                color="error"
                size="small"
                disabled={!canApprove}
                startIcon={<Cancel />}
                onClick={() => handleOpenReview('reject')}
                sx={{ borderRadius: '8px', textTransform: 'none', px: 2 }}
              >
                Reject Proposal
              </Button>
              <Button
                variant="contained"
                size="small"
                disabled={!canApprove}
                startIcon={<PlayCircleOutline />}
                onClick={() => handleOpenReview('approve')}
                sx={{
                  borderRadius: '8px',
                  textTransform: 'none',
                  px: 2.5,
                  background: 'linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%)',
                  fontWeight: 600,
                  '&:hover': {
                    background: 'linear-gradient(135deg, #4338ca 0%, #0891b2 100%)',
                  },
                }}
              >
                Approve & Re-execute Pipeline
              </Button>
            </Stack>
          </Box>
        )}
      </CardContent>

      {/* Approval / Rejection Confirmation Dialog */}
      <Dialog
        open={dialogOpen}
        onClose={() => !submitting && setDialogOpen(false)}
        PaperProps={{
          sx: {
            bgcolor: '#1e293b',
            color: '#f8fafc',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '12px',
            maxWidth: 480,
          },
        }}
      >
        <DialogTitle sx={{ pb: 1 }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <VerifiedUser sx={{ color: decision === 'approve' ? '#10b981' : '#f43f5e' }} />
            <Typography variant="h6" fontWeight={700}>
              {decision === 'approve' ? 'Approve & Re-execute Agents' : 'Reject Correction Proposal'}
            </Typography>
          </Stack>
        </DialogTitle>
        <DialogContent sx={{ pt: 1 }}>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          <Typography variant="body2" sx={{ color: '#cbd5e1', mb: 2 }}>
            {decision === 'approve'
              ? 'Approving will modify the transaction in the client ledger, trigger automatic re-execution of dependent agents (Accounting Review ➔ Adjustments ➔ Reporting), and generate updated financial statements.'
              : 'Rejecting this proposal will preserve the original data. No agent re-execution will occur.'}
          </Typography>

          <TextField
            fullWidth
            label="CA Reviewer Notes (Audit Trail)"
            multiline
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            disabled={submitting}
            placeholder="Provide context or explanation for the audit log..."
            sx={{
              '& .MuiOutlinedInput-root': {
                color: '#f8fafc',
                bgcolor: 'rgba(15, 23, 42, 0.6)',
                '& fieldset': { borderColor: 'rgba(255, 255, 255, 0.2)' },
              },
            }}
          />
        </DialogContent>
        <DialogActions sx={{ p: 2, pt: 0 }}>
          <Button onClick={() => setDialogOpen(false)} disabled={submitting} sx={{ color: '#94a3b8' }}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={submitting}
            variant="contained"
            color={decision === 'approve' ? 'primary' : 'error'}
            startIcon={submitting ? <CircularProgress size={16} /> : undefined}
            sx={{
              borderRadius: '8px',
              textTransform: 'none',
              px: 3,
              bgcolor: decision === 'approve' ? '#4f46e5' : '#ef4444',
            }}
          >
            {submitting ? 'Executing Pipeline...' : decision === 'approve' ? 'Confirm & Execute' : 'Confirm Rejection'}
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
};
