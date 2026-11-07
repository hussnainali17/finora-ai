import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { ExpandLess, ExpandMore } from '@mui/icons-material';
import { useParams } from 'react-router-dom';
import { listFindings, updateFindingStatus } from '../../services/accountingReviewApi';
import type { FindingStatus, ReviewFinding } from '../../types/accounting_review';
import { MODULE_LABELS, STATUS_COLORS } from '../../types/accounting_review';
import { useAuth } from '../auth/AuthContext';

const SEVERITY_CHIP_COLOR: Record<string, 'default' | 'warning' | 'error'> = {
  info: 'default',
  warning: 'warning',
  error: 'error',
};

const FINDING_STATUSES: FindingStatus[] = ['open', 'explained', 'resolved', 'escalated'];

export function FindingsPage(): React.JSX.Element {
  const { clientId, periodId, reviewRunId } = useParams<{
    clientId: string;
    periodId: string;
    reviewRunId: string;
  }>();
  const { principal } = useAuth();

  const canRead = principal?.permissions?.includes('review:read') ?? false;
  const canResolve = principal?.permissions?.includes('review:resolve') ?? false;

  const [findings, setFindings] = useState<ReviewFinding[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [filterModule, setFilterModule] = useState('');
  const [filterSeverity, setFilterSeverity] = useState('');
  const [filterStatus, setFilterStatus] = useState('');

  // Expanded row
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Status update dialog
  const [updateDialog, setUpdateDialog] = useState<{
    open: boolean;
    finding: ReviewFinding | null;
  }>({ open: false, finding: null });
  const [newStatus, setNewStatus] = useState<FindingStatus>('explained');
  const [reviewerNote, setReviewerNote] = useState('');
  const [updating, setUpdating] = useState(false);

  const fetchFindings = useCallback(async () => {
    if (!clientId || !periodId || !reviewRunId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listFindings(clientId, periodId, reviewRunId, {
        module: filterModule || undefined,
        severity: filterSeverity || undefined,
        status: filterStatus || undefined,
        limit: 200,
      });
      setFindings(data.items);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load findings');
    } finally {
      setLoading(false);
    }
  }, [clientId, periodId, reviewRunId, filterModule, filterSeverity, filterStatus]);

  useEffect(() => {
    if (canRead) void fetchFindings();
  }, [canRead, fetchFindings]);

  const handleUpdateStatus = async () => {
    if (!clientId || !periodId || !reviewRunId || !updateDialog.finding) return;
    setUpdating(true);
    try {
      const updated = await updateFindingStatus(
        clientId,
        periodId,
        reviewRunId,
        updateDialog.finding.id,
        { status: newStatus, reviewer_note: reviewerNote || undefined },
      );
      setFindings((prev) => prev.map((f) => (f.id === updated.id ? updated : f)));
      setUpdateDialog({ open: false, finding: null });
      setReviewerNote('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update finding');
    } finally {
      setUpdating(false);
    }
  };

  if (!canRead) {
    return <Alert severity="error">You do not have permission to view findings.</Alert>;
  }

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" component="h1" sx={{ mb: 3 }}>
        Review Findings
      </Typography>

      {/* Filters */}
      <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
        <FormControl size="small" sx={{ minWidth: 180 }}>
          <InputLabel>Module</InputLabel>
          <Select
            value={filterModule}
            label="Module"
            onChange={(e) => setFilterModule(e.target.value)}
          >
            <MenuItem value="">All modules</MenuItem>
            {Object.entries(MODULE_LABELS).map(([key, label]) => (
              <MenuItem key={key} value={key}>
                {label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 130 }}>
          <InputLabel>Severity</InputLabel>
          <Select
            value={filterSeverity}
            label="Severity"
            onChange={(e) => setFilterSeverity(e.target.value)}
          >
            <MenuItem value="">All</MenuItem>
            <MenuItem value="error">Error</MenuItem>
            <MenuItem value="warning">Warning</MenuItem>
            <MenuItem value="info">Info</MenuItem>
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 130 }}>
          <InputLabel>Status</InputLabel>
          <Select
            value={filterStatus}
            label="Status"
            onChange={(e) => setFilterStatus(e.target.value)}
          >
            <MenuItem value="">All</MenuItem>
            {FINDING_STATUSES.map((s) => (
              <MenuItem key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
          <CircularProgress />
        </Box>
      ) : findings.length === 0 ? (
        <Alert severity="success">No findings match the current filters.</Alert>
      ) : (
        <Paper>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell />
                <TableCell>Module</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>Severity</TableCell>
                <TableCell>Title</TableCell>
                <TableCell align="right">Amount</TableCell>
                <TableCell>Status</TableCell>
                {canResolve && <TableCell>Action</TableCell>}
              </TableRow>
            </TableHead>
            <TableBody>
              {findings.map((finding) => (
                <React.Fragment key={finding.id}>
                  <TableRow hover>
                    <TableCell>
                      <IconButton
                        size="small"
                        onClick={() =>
                          setExpandedId(expandedId === finding.id ? null : finding.id)
                        }
                      >
                        {expandedId === finding.id ? <ExpandLess /> : <ExpandMore />}
                      </IconButton>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption">
                        {MODULE_LABELS[finding.module] ?? finding.module}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" color="text.secondary">
                        {finding.finding_type}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={finding.severity}
                        color={SEVERITY_CHIP_COLOR[finding.severity] ?? 'default'}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">{finding.title}</Typography>
                    </TableCell>
                    <TableCell align="right">
                      {finding.amount ? (
                        <Typography variant="body2">
                          {Number(finding.amount).toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                          })}{' '}
                          {finding.currency ?? ''}
                        </Typography>
                      ) : (
                        '—'
                      )}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={finding.status}
                        size="small"
                        sx={{
                          backgroundColor: STATUS_COLORS[finding.status],
                          color: 'white',
                        }}
                      />
                    </TableCell>
                    {canResolve && (
                      <TableCell>
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={() => {
                            setUpdateDialog({ open: true, finding });
                            setNewStatus('explained');
                            setReviewerNote(finding.reviewer_note ?? '');
                          }}
                        >
                          Update
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>

                  {/* Expanded detail row */}
                  <TableRow>
                    <TableCell colSpan={canResolve ? 8 : 7} sx={{ py: 0 }}>
                      <Collapse in={expandedId === finding.id} timeout="auto" unmountOnExit>
                        <Box sx={{ p: 2, bgcolor: 'background.paper' }}>
                          <Typography variant="body2" sx={{ mb: 1 }}>
                            {finding.description}
                          </Typography>
                          {finding.reviewer_note && (
                            <Typography variant="caption" color="text.secondary">
                              Reviewer note: {finding.reviewer_note}
                            </Typography>
                          )}
                          {finding.evidence_refs.length > 0 && (
                            <Box sx={{ mt: 1 }}>
                              <Typography variant="caption" fontWeight="bold">
                                Evidence references:
                              </Typography>
                              {finding.evidence_refs.map((ref, i) => (
                                <Typography key={i} variant="caption" display="block" sx={{ ml: 1 }}>
                                  {ref.description ?? JSON.stringify(ref)}
                                </Typography>
                              ))}
                            </Box>
                          )}
                        </Box>
                      </Collapse>
                    </TableCell>
                  </TableRow>
                </React.Fragment>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      {/* Status update dialog */}
      <Dialog
        open={updateDialog.open}
        onClose={() => setUpdateDialog({ open: false, finding: null })}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Update Finding Status</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            {updateDialog.finding?.title}
          </Typography>
          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel>New Status</InputLabel>
            <Select
              value={newStatus}
              label="New Status"
              onChange={(e) => setNewStatus(e.target.value as FindingStatus)}
            >
              {FINDING_STATUSES.map((s) => (
                <MenuItem key={s} value={s}>
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            fullWidth
            multiline
            rows={3}
            label="Reviewer Note"
            value={reviewerNote}
            onChange={(e) => setReviewerNote(e.target.value)}
            placeholder="Explain the reason for this status change..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUpdateDialog({ open: false, finding: null })}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => void handleUpdateStatus()}
            disabled={updating}
          >
            {updating ? <CircularProgress size={18} /> : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
