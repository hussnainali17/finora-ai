import React, { useEffect, useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  Stack,
  Typography,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
} from '@mui/material';
import {
  FactCheck as ValidationIcon,
  CheckCircle as CheckIcon,
  Warning as WarningIcon,
  Assessment as ReportIcon,
} from '@mui/icons-material';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { listSharedOutputs } from '../../services/sharedDataApi';
import type { ApprovedModuleOutput } from '../../types/sharedData';

export const CentralValidationPage: React.FC = () => {
  const { activeClient, activePeriod } = useWorkspace();
  const [outputs, setOutputs] = useState<ApprovedModuleOutput[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeClient || !activePeriod) return;
    setLoading(true);
    listSharedOutputs(activeClient.id, activePeriod.id)
      .then((res) => setOutputs(res.items))
      .catch((err) => setError(err?.message || 'Failed to load validation data'))
      .finally(() => setLoading(false));
  }, [activeClient, activePeriod]);

  if (!activeClient || !activePeriod) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">Please select a workspace client and period first.</Alert>
      </Box>
    );
  }

  const latestAcct = outputs.filter((o) => o.module === 'accounting')[0] || null;
  const latestTax = outputs.filter((o) => o.module === 'taxation')[0] || null;

  const acctProfit = Number(latestAcct?.summary?.net_profit || 0);
  const taxProfit = Number(latestTax?.summary?.net_accounting_profit || latestTax?.summary?.taxable_income || 0);
  const difference = Math.abs(acctProfit - taxProfit);
  const tieOutValid = Boolean(latestAcct && latestTax && difference === 0);

  return (
    <Box sx={{ p: 3, maxWidth: 1400, mx: 'auto' }}>
      {/* Header */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Typography variant="h5" fontWeight="700" sx={{ color: '#1e293b' }}>
              Central Cross-Module Validation & Consolidated Reports
            </Typography>
            <Chip label="Firm Verification" color="primary" size="small" variant="outlined" />
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Cross-checks accounting financial statements against Pakistan tax return schedules to ensure mathematical and statutory integrity.
          </Typography>
        </Box>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 5 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Grid container spacing={3}>
          {/* Tie-Out Card */}
          <Grid item xs={12} md={7}>
            <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2 }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                  <ValidationIcon sx={{ color: '#0284c7' }} />
                  <Typography variant="h6" fontWeight="700">
                    Accounting vs. Taxation Tie-Out Analysis
                  </Typography>
                </Stack>
                <Divider sx={{ mb: 2.5 }} />

                <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #e2e8f0' }}>
                  <Table size="small">
                    <TableHead sx={{ bgcolor: '#f8fafc' }}>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 700 }}>Verification Item</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>Accounting Statements</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>Taxation Workpapers</TableCell>
                        <TableCell align="center" sx={{ fontWeight: 700 }}>Tie-Out</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 600 }}>Profit Before Tax (PBT)</TableCell>
                        <TableCell align="right">PKR {acctProfit.toLocaleString()}</TableCell>
                        <TableCell align="right">PKR {taxProfit.toLocaleString()}</TableCell>
                        <TableCell align="center">
                          {tieOutValid ? (
                            <Chip icon={<CheckIcon />} label="Match" size="small" color="success" />
                          ) : (
                            <Chip icon={<WarningIcon />} label="Diff" size="small" color="warning" />
                          )}
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </TableContainer>

                <Box sx={{ mt: 3, p: 2, bgcolor: tieOutValid ? '#f0fdf4' : '#fffbeb', borderRadius: 2, border: tieOutValid ? '1px solid #bbf7d0' : '1px solid #fde68a' }}>
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    {tieOutValid ? <CheckIcon sx={{ color: '#16a34a' }} /> : <WarningIcon sx={{ color: '#d97706' }} />}
                    <Box>
                      <Typography variant="subtitle2" fontWeight="700" color={tieOutValid ? '#166534' : '#92400e'}>
                        {tieOutValid ? 'Cross-Module Reconciliation Verified' : 'Reconciliation Incomplete or In Progress'}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {tieOutValid
                          ? 'Accounting Net Profit matches Tax Return Book-to-Tax Bridge with zero variance.'
                          : 'Both Accounting and Taxation outputs must be approved to complete central cross-module verification.'}
                      </Typography>
                    </Box>
                  </Stack>
                </Box>
              </CardContent>
            </Card>
          </Grid>

          {/* Consolidated Report Overview */}
          <Grid item xs={12} md={5}>
            <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2, height: '100%' }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                  <ReportIcon sx={{ color: '#0284c7' }} />
                  <Typography variant="h6" fontWeight="700">
                    Consolidated Firm Summary
                  </Typography>
                </Stack>
                <Divider sx={{ mb: 2.5 }} />

                <Stack spacing={2}>
                  <Box sx={{ p: 2, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                    <Typography variant="caption" color="text.secondary">Client Entity</Typography>
                    <Typography variant="body1" fontWeight="700">{activeClient.name}</Typography>
                  </Box>

                  <Box sx={{ p: 2, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                    <Typography variant="caption" color="text.secondary">Reporting Period & Tax Year</Typography>
                    <Typography variant="body1" fontWeight="700">{activePeriod.label}</Typography>
                  </Box>

                  <Box sx={{ p: 2, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                    <Typography variant="caption" color="text.secondary">Accounting Module State</Typography>
                    <Typography variant="body1" fontWeight="600" color={latestAcct ? '#16a34a' : '#d97706'}>
                      {latestAcct ? `Signed Off & Published (v${latestAcct.version})` : 'Pending Approval'}
                    </Typography>
                  </Box>

                  <Box sx={{ p: 2, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                    <Typography variant="caption" color="text.secondary">Taxation Module State</Typography>
                    <Typography variant="body1" fontWeight="600" color={latestTax ? '#16a34a' : '#d97706'}>
                      {latestTax ? `Signed Off & Published (v${latestTax.version})` : 'Pending Approval'}
                    </Typography>
                  </Box>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}
    </Box>
  );
};
