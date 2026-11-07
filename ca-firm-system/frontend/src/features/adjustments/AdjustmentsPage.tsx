import React, { useCallback, useEffect, useState } from 'react';
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
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { AutoFixHigh, CheckCircle, Close, Refresh } from '@mui/icons-material';
import { useParams } from 'react-router-dom';
import {
  decideAdjustment,
  generateAdjustments,
  listAdjustments,
} from '../../services/adjustmentsApi';
import type { PeriodAdjustment } from '../../types/adjustments';
import { CATEGORY_LABELS, STATUS_COLORS } from '../../types/adjustments';
import { useAuth } from '../auth/AuthContext';

export function AdjustmentsPage(): React.JSX.Element {
  const { clientId, periodId } = useParams<{ clientId: string; periodId: string }>();
  const { principal } = useAuth();

  const [adjustments, setAdjustments] = useState<PeriodAdjustment[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [decisionDialog, setDecisionDialog] = useState<{
    open: boolean;
    adj: PeriodAdjustment | null;
    decision: 'approved' | 'rejected';
  }>({ open: false, adj: null, decision: 'approved' });
  const [comments, setComments] = useState('');
  const [deciding, setDeciding] = useState(false);

  const canApprove = principal?.permissions?.includes('adjustment:approve') ?? false;
  const canPropose = principal?.permissions?.includes('adjustment:propose') ?? false;
  const canRead = principal?.permissions?.includes('adjustment:read') ?? false;

  const fetchAdjustments = useCallback(async () => {
    if (!clientId || !periodId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listAdjustments(clientId, periodId);
      setAdjustments(data.items);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load adjustments');
    } finally {
      setLoading(false);
    }
  }, [clientId, periodId]);

  useEffect(() => {
    if (canRead) void fetchAdjustments();
  }, [canRead, fetchAdjustments]);

  const handleGenerate = async () => {
    if (!clientId || !periodId) return;
    setGenerating(true);
    setError(null);
    try {
      await generateAdjustments(clientId, periodId);
      await fetchAdjustments();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to generate adjustments');
    } finally {
      setGenerating(false);
    }
  };

  const handleDecision = async () => {
    if (!clientId || !periodId || !decisionDialog.adj) return;
    setDeciding(true);
    try {
      const updated = await decideAdjustment(
        clientId,
        periodId,
        decisionDialog.adj.id,
        { decision: decisionDialog.decision, comments: comments || undefined },
      );
      setAdjustments((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      setDecisionDialog({ open: false, adj: null, decision: 'approved' });
      setComments('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Decision failed');
    } finally {
      setDeciding(false);
    }
  };

  if (!canRead) {
    return <Alert severity="error">You do not have permission to view period-end adjustments.</Alert>;
  }

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h5" component="h1">
            Period-End Adjustments (Agent 3)
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Proposed accruals, prepayments, depreciation, and allowances. Only approved adjustments feed the Adjusted Trial Balance.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" startIcon={<Refresh />} onClick={() => void fetchAdjustments()} disabled={loading}>
            Refresh
          </Button>
          {canPropose && (
            <Button
              variant="contained"
              startIcon={generating ? <CircularProgress size={16} /> : <AutoFixHigh />}
              onClick={() => void handleGenerate()}
              disabled={generating || loading}
            >
              Generate Adjustments
            </Button>
          )}
        </Stack>
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading && adjustments.length === 0 ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}><CircularProgress /></Box>
      ) : adjustments.length === 0 ? (
        <Alert severity="info">
          No adjustments registered yet.{canPropose ? ' Click "Generate Adjustments" to have Agent 3 calculate proposals.' : ''}
        </Alert>
      ) : (
        <Paper>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Category</TableCell>
                <TableCell>Debit Account</TableCell>
                <TableCell>Credit Account</TableCell>
                <TableCell align="right">Amount</TableCell>
                <TableCell>Accounting Rationale</TableCell>
                <TableCell>Status</TableCell>
                {canApprove && <TableCell align="center">CA Action</TableCell>}
              </TableRow>
            </TableHead>
            <TableBody>
              {adjustments.map((adj) => (
                <TableRow key={adj.id} hover>
                  <TableCell>
                    <Chip
                      size="small"
                      label={CATEGORY_LABELS[adj.category] ?? adj.category}
                      variant="outlined"
                    />
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" fontWeight="bold">
                      {adj.debit_account_code} - {adj.debit_account_name}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {adj.credit_account_code} - {adj.credit_account_name}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Typography variant="body2" fontWeight="bold">
                      {Number(adj.amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}{' '}
                      {adj.currency}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption" color="text.secondary" display="block">
                      {adj.accounting_rationale}
                    </Typography>
                    {adj.reviewer_comments && (
                      <Typography variant="caption" color="primary" display="block">
                        CA Note: {adj.reviewer_comments}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={adj.status.toUpperCase()}
                      color={STATUS_COLORS[adj.status] ?? 'default'}
                      size="small"
                    />
                  </TableCell>
                  {canApprove && (
                    <TableCell align="center">
                      {adj.status === 'proposed' && (
                        <Stack direction="row" spacing={1} justifyContent="center">
                          <Button
                            size="small"
                            variant="contained"
                            color="success"
                            onClick={() => {
                              setDecisionDialog({ open: true, adj, decision: 'approved' });
                              setComments('');
                            }}
                          >
                            Approve
                          </Button>
                          <Button
                            size="small"
                            variant="outlined"
                            color="error"
                            onClick={() => {
                              setDecisionDialog({ open: true, adj, decision: 'rejected' });
                              setComments('');
                            }}
                          >
                            Reject
                          </Button>
                        </Stack>
                      )}
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      {/* CA Decision Dialog */}
      <Dialog
        open={decisionDialog.open}
        onClose={() => setDecisionDialog({ open: false, adj: null, decision: 'approved' })}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          {decisionDialog.decision === 'approved' ? 'Approve' : 'Reject'} Adjustment Proposal
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            <strong>Debit:</strong> {decisionDialog.adj?.debit_account_name} ({decisionDialog.adj?.debit_account_code})<br />
            <strong>Credit:</strong> {decisionDialog.adj?.credit_account_name} ({decisionDialog.adj?.credit_account_code})<br />
            <strong>Amount:</strong> {decisionDialog.adj?.amount} {decisionDialog.adj?.currency}
          </Typography>
          <TextField
            fullWidth
            multiline
            rows={3}
            label="CA Reviewer Note"
            value={comments}
            onChange={(e) => setComments(e.target.value)}
            placeholder="Add comments on why this entry is approved or rejected..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDecisionDialog({ open: false, adj: null, decision: 'approved' })}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color={decisionDialog.decision === 'approved' ? 'success' : 'error'}
            onClick={() => void handleDecision()}
            disabled={deciding}
          >
            {deciding ? <CircularProgress size={16} /> : `Confirm ${decisionDialog.decision}`}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
