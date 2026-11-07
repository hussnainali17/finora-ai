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
  Divider,
  Grid,
  Paper,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import { CheckCircle, Download, Error, Refresh, TaskAlt } from '@mui/icons-material';
import { useParams } from 'react-router-dom';
import {
  generateReports,
  getExcelDownloadUrl,
  listReports,
  signOffReport,
} from '../../services/reportingApi';
import type { FinancialReport } from '../../types/reporting';
import { useAuth } from '../auth/AuthContext';

export function ReportingPage(): React.JSX.Element {
  const { clientId, periodId } = useParams<{ clientId: string; periodId: string }>();
  const { principal } = useAuth();

  const [reports, setReports] = useState<FinancialReport[]>([]);
  const [selectedReport, setSelectedReport] = useState<FinancialReport | null>(null);
  const [tabIndex, setTabIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [signOffDialog, setSignOffDialog] = useState(false);
  const [signOffNotes, setSignOffNotes] = useState('');
  const [signingOff, setSigningOff] = useState(false);

  const canSignOff = principal?.permissions?.includes('report:sign_off') ?? false;
  const canGenerate = principal?.permissions?.includes('report:generate') ?? false;
  const canRead = principal?.permissions?.includes('report:read') ?? false;

  const fetchReports = useCallback(async () => {
    if (!clientId || !periodId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listReports(clientId, periodId);
      setReports(data.items);
      if (data.items.length > 0) {
        setSelectedReport(data.items[0]);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load financial reports');
    } finally {
      setLoading(false);
    }
  }, [clientId, periodId]);

  useEffect(() => {
    if (canRead) void fetchReports();
  }, [canRead, fetchReports]);

  const handleGenerate = async () => {
    if (!clientId || !periodId) return;
    setGenerating(true);
    setError(null);
    try {
      await generateReports(clientId, periodId);
      await fetchReports();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Report generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const handleSignOff = async () => {
    if (!clientId || !periodId || !selectedReport) return;
    setSigningOff(true);
    try {
      const updated = await signOffReport(clientId, periodId, selectedReport.id, signOffNotes);
      setSelectedReport(updated);
      setReports((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
      setSignOffDialog(false);
      setSignOffNotes('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Sign-off failed');
    } finally {
      setSigningOff(false);
    }
  };

  if (!canRead) {
    return <Alert severity="error">You do not have permission to view financial reports.</Alert>;
  }

  const repData = selectedReport?.data ?? {};
  const validation = selectedReport?.validation_results;
  const adjTbRows = repData.adjusted_tb?.rows ?? [];
  const pl = repData.profit_and_loss ?? {};
  const bs = repData.balance_sheet ?? {};

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h5" component="h1">
            Financial Statements & Validation (Agent 4)
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Adjusted Trial Balance (Original TB + Approved Adjustments) and generated statements.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" startIcon={<Refresh />} onClick={() => void fetchReports()} disabled={loading}>
            Refresh
          </Button>
          {selectedReport && (
            <Button
              variant="outlined"
              startIcon={<Download />}
              href={getExcelDownloadUrl(clientId ?? '', periodId ?? '', selectedReport.id)}
              download
            >
              Export Excel
            </Button>
          )}
          {selectedReport && canSignOff && selectedReport.status !== 'signed_off' && (
            <Button
              variant="contained"
              color="success"
              startIcon={<TaskAlt />}
              onClick={() => setSignOffDialog(true)}
            >
              CA Sign-Off
            </Button>
          )}
          {canGenerate && (
            <Button
              variant="contained"
              onClick={() => void handleGenerate()}
              disabled={generating || loading}
            >
              {generating ? <CircularProgress size={16} /> : 'Generate Statements'}
            </Button>
          )}
        </Stack>
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* Validation Banner */}
      {validation && (
        <Card sx={{ mb: 3, borderLeft: '6px solid', borderColor: validation.is_valid ? 'success.main' : 'error.main' }}>
          <CardContent>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              {validation.is_valid ? (
                <CheckCircle color="success" />
              ) : (
                <Error color="error" />
              )}
              <Typography variant="subtitle1" fontWeight="bold">
                Validation Summary: {validation.is_valid ? 'All Integrity Checks Passed' : 'Validation Issues Detected'}
              </Typography>
              <Chip
                size="small"
                label={`${validation.passed_checks} / ${validation.total_checks} passed`}
                color={validation.is_valid ? 'success' : 'error'}
              />
              {selectedReport?.status === 'signed_off' && (
                <Chip
                  size="small"
                  label={`Signed off by CA at ${new Date(selectedReport.signed_off_at ?? '').toLocaleString()}`}
                  color="success"
                />
              )}
            </Stack>
            {validation.issues && validation.issues.length > 0 && (
              <Stack spacing={0.5} sx={{ mt: 1 }}>
                {validation.issues.map((iss, i) => (
                  <Alert key={i} severity={iss.severity === 'error' ? 'error' : 'warning'}>
                    <strong>{iss.check_name}:</strong> {iss.description}
                  </Alert>
                ))}
              </Stack>
            )}
          </CardContent>
        </Card>
      )}

      {selectedReport && (
        <Paper sx={{ mb: 3 }}>
          <Tabs value={tabIndex} onChange={(_, v) => setTabIndex(v)} sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Tab label="Adjusted Trial Balance" />
            <Tab label="Statement of Profit or Loss" />
            <Tab label="Statement of Financial Position" />
          </Tabs>

          {/* TAB 0: Adjusted Trial Balance */}
          {tabIndex === 0 && (
            <Box sx={{ p: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Code</TableCell>
                    <TableCell>Account Name</TableCell>
                    <TableCell align="right">Original Debit</TableCell>
                    <TableCell align="right">Original Credit</TableCell>
                    <TableCell align="right">Adj Debit</TableCell>
                    <TableCell align="right">Adj Credit</TableCell>
                    <TableCell align="right">Adjusted Debit</TableCell>
                    <TableCell align="right">Adjusted Credit</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {adjTbRows.map((r: any, idx: number) => (
                    <TableRow key={idx} hover>
                      <TableCell>{r.account_code}</TableCell>
                      <TableCell>{r.account_name}</TableCell>
                      <TableCell align="right">{Number(r.original_debit).toLocaleString()}</TableCell>
                      <TableCell align="right">{Number(r.original_credit).toLocaleString()}</TableCell>
                      <TableCell align="right">{Number(r.adjustment_debit) > 0 ? Number(r.adjustment_debit).toLocaleString() : '—'}</TableCell>
                      <TableCell align="right">{Number(r.adjustment_credit) > 0 ? Number(r.adjustment_credit).toLocaleString() : '—'}</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 'bold' }}>{Number(r.final_debit).toLocaleString()}</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 'bold' }}>{Number(r.final_credit).toLocaleString()}</TableCell>
                    </TableRow>
                  ))}
                  <TableRow sx={{ bgcolor: 'action.hover' }}>
                    <TableCell colSpan={2}><strong>Total</strong></TableCell>
                    <TableCell align="right"><strong>{repData.original_tb_summary?.total_debit}</strong></TableCell>
                    <TableCell align="right"><strong>{repData.original_tb_summary?.total_credit}</strong></TableCell>
                    <TableCell colSpan={2} />
                    <TableCell align="right"><strong>{repData.adjusted_tb?.total_debit}</strong></TableCell>
                    <TableCell align="right"><strong>{repData.adjusted_tb?.total_credit}</strong></TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </Box>
          )}

          {/* TAB 1: Profit and Loss */}
          {tabIndex === 1 && (
            <Box sx={{ p: 3, maxWidth: 650 }}>
              <Typography variant="h6" gutterBottom>Statement of Profit or Loss</Typography>
              <Divider sx={{ mb: 2 }} />
              <Grid container spacing={1}>
                <Grid item xs={8}><Typography variant="body1">Total Revenue</Typography></Grid>
                <Grid item xs={4} textAlign="right"><Typography variant="body1">{Number(pl.revenue ?? 0).toLocaleString()}</Typography></Grid>

                <Grid item xs={8}><Typography variant="body1">Cost of Goods Sold</Typography></Grid>
                <Grid item xs={4} textAlign="right"><Typography variant="body1">({Number(pl.cost_of_goods_sold ?? 0).toLocaleString()})</Typography></Grid>

                <Grid item xs={8}><Typography variant="subtitle1" fontWeight="bold">Gross Profit</Typography></Grid>
                <Grid item xs={4} textAlign="right"><Typography variant="subtitle1" fontWeight="bold">{Number(pl.gross_profit ?? 0).toLocaleString()}</Typography></Grid>

                <Grid item xs={8}><Typography variant="body1">Operating Expenses</Typography></Grid>
                <Grid item xs={4} textAlign="right"><Typography variant="body1">({Number(pl.operating_expenses ?? 0).toLocaleString()})</Typography></Grid>

                <Grid item xs={8} sx={{ pt: 1 }}><Typography variant="h6" color="primary.main">Net Profit / (Loss)</Typography></Grid>
                <Grid item xs={4} textAlign="right" sx={{ pt: 1 }}><Typography variant="h6" color="primary.main">{Number(pl.net_profit ?? 0).toLocaleString()}</Typography></Grid>
              </Grid>
            </Box>
          )}

          {/* TAB 2: Balance Sheet */}
          {tabIndex === 2 && (
            <Box sx={{ p: 3, maxWidth: 650 }}>
              <Typography variant="h6" gutterBottom>Statement of Financial Position</Typography>
              <Divider sx={{ mb: 2 }} />
              <Grid container spacing={1}>
                <Grid item xs={12}><Typography variant="subtitle2" color="text.secondary">ASSETS</Typography></Grid>
                <Grid item xs={8} sx={{ pl: 2 }}><Typography variant="body1">Current Assets</Typography></Grid>
                <Grid item xs={4} textAlign="right"><Typography variant="body1">{Number(bs.current_assets ?? 0).toLocaleString()}</Typography></Grid>

                <Grid item xs={8} sx={{ pl: 2 }}><Typography variant="body1">Non-Current Assets</Typography></Grid>
                <Grid item xs={4} textAlign="right"><Typography variant="body1">{Number(bs.non_current_assets ?? 0).toLocaleString()}</Typography></Grid>

                <Grid item xs={8}><Typography variant="subtitle1" fontWeight="bold">Total Assets</Typography></Grid>
                <Grid item xs={4} textAlign="right"><Typography variant="subtitle1" fontWeight="bold">{Number(bs.total_assets ?? 0).toLocaleString()}</Typography></Grid>

                <Grid item xs={12} sx={{ mt: 2 }}><Typography variant="subtitle2" color="text.secondary">LIABILITIES & EQUITY</Typography></Grid>
                <Grid item xs={8} sx={{ pl: 2 }}><Typography variant="body1">Current Liabilities</Typography></Grid>
                <Grid item xs={4} textAlign="right"><Typography variant="body1">{Number(bs.current_liabilities ?? 0).toLocaleString()}</Typography></Grid>

                <Grid item xs={8} sx={{ pl: 2 }}><Typography variant="body1">Non-Current Liabilities</Typography></Grid>
                <Grid item xs={4} textAlign="right"><Typography variant="body1">{Number(bs.non_current_liabilities ?? 0).toLocaleString()}</Typography></Grid>

                <Grid item xs={8} sx={{ pl: 2 }}><Typography variant="body1">Total Liabilities</Typography></Grid>
                <Grid item xs={4} textAlign="right"><Typography variant="body1">{Number(bs.total_liabilities ?? 0).toLocaleString()}</Typography></Grid>

                <Grid item xs={8} sx={{ pl: 2 }}><Typography variant="body1">Equity & Retained Earnings</Typography></Grid>
                <Grid item xs={4} textAlign="right"><Typography variant="body1">{Number(bs.total_equity ?? 0).toLocaleString()}</Typography></Grid>

                <Grid item xs={8}><Typography variant="subtitle1" fontWeight="bold">Total Liabilities and Equity</Typography></Grid>
                <Grid item xs={4} textAlign="right"><Typography variant="subtitle1" fontWeight="bold">{Number(bs.total_liabilities_and_equity ?? 0).toLocaleString()}</Typography></Grid>
              </Grid>
            </Box>
          )}
        </Paper>
      )}

      {/* CA Sign-Off Dialog */}
      <Dialog open={signOffDialog} onClose={() => setSignOffDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>CA Final Sign-Off</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            You are signing off on the financial statements for this period. This indicates formal approval of the Adjusted Trial Balance and associated statements.
          </Typography>
          <TextField
            fullWidth
            multiline
            rows={3}
            label="Sign-Off Opinion & Notes"
            value={signOffNotes}
            onChange={(e) => setSignOffNotes(e.target.value)}
            placeholder="Add professional sign-off notes or review opinion remarks..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSignOffDialog(false)}>Cancel</Button>
          <Button variant="contained" color="success" onClick={() => void handleSignOff()} disabled={signingOff}>
            {signingOff ? <CircularProgress size={16} /> : 'Confirm Sign-Off'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
