import React, { useEffect, useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  Alert,
  AlertTitle,
  Paper,
  RadioGroup,
  FormControlLabel,
  Radio,
} from '@mui/material';
import {
  CompareArrows as ReconIcon,
  PlayArrow as PlayIcon,
  CheckCircle as CheckIcon,
  TableChart as TableIcon,
} from '@mui/icons-material';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  createTaxEngagement,
  listTaxEngagements,
  listTaxWorkpapers,
  runTaxReconciliation,
} from '../../services/taxationApi';
import { getLatestApprovedAccounting } from '../../services/sharedDataApi';
import type { TaxEngagement, TaxWorkpaper } from '../../types/taxation';
import type { ApprovedModuleOutput } from '../../types/sharedData';

export const TaxReconciliationPage: React.FC = () => {
  const { activeClient, activePeriod } = useWorkspace();
  const [engagement, setEngagement] = useState<TaxEngagement | null>(null);
  const [workpapers, setWorkpapers] = useState<TaxWorkpaper[]>([]);
  const [latestAccounting, setLatestAccounting] = useState<ApprovedModuleOutput | null>(null);
  const [sourceMode, setSourceMode] = useState<'approved_accounting' | 'client_direct'>('approved_accounting');

  const [loading, setLoading] = useState<boolean>(true);
  const [running, setRunning] = useState<boolean>(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ensureEngagement = async (): Promise<TaxEngagement | null> => {
    if (!activeClient || !activePeriod) return null;
    const engRes = await listTaxEngagements(activeClient.id, activePeriod.id);
    if (engRes.items.length > 0) return engRes.items[0];
    const currentYear = new Date().getFullYear();
    return createTaxEngagement(activeClient.id, activePeriod.id, {
      tax_year: currentYear,
      tax_period_label: `TY${currentYear}`,
      tax_type: 'composite',
    });
  };

  const loadData = async () => {
    if (!activeClient || !activePeriod) return;
    try {
      setLoading(true);
      setError(null);
      const eng = await ensureEngagement();
      if (!eng) {
        setEngagement(null);
        return;
      }
      setEngagement(eng);

      // Load existing workpapers
      const wpRes = await listTaxWorkpapers(activeClient.id, activePeriod.id, eng.id);
      setWorkpapers(wpRes.items);

      // Check shared accounting output
      try {
        const acct = await getLatestApprovedAccounting(activeClient.id, activePeriod.id);
        setLatestAccounting(acct);
      } catch {
        setLatestAccounting(null);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load reconciliation data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [activeClient, activePeriod]);

  const handleRunReconciliation = async () => {
    if (!activeClient || !activePeriod) return;
    try {
      setRunning(true);
      setError(null);
      let eng = engagement;
      if (!eng) {
        eng = await ensureEngagement();
        if (!eng) throw new Error('Could not create tax engagement');
        setEngagement(eng);
      }
      await runTaxReconciliation(
        activeClient.id,
        activePeriod.id,
        eng.id,
        sourceMode,
        latestAccounting?.version,
      );
      setMessage(`Agent 2 Reconciliation executed using Mode: ${sourceMode === 'approved_accounting' ? 'Approved Accounting Layer' : 'Direct Client Records'}`);
      await loadData();
    } catch (err: any) {
      setError(err?.message || 'Failed to execute tax reconciliation');
    } finally {
      setRunning(false);
    }
  };

  if (!activeClient || !activePeriod) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">Please select a workspace client and period first.</Alert>
      </Box>
    );
  }

  // Separate mapped categories and withholding workpaper
  const mappingWp = workpapers.find((w) => w.workpaper_type === 'book_to_tax_mapping');
  const whtWp = workpapers.find((w) => w.workpaper_type === 'withholding_reconciliation');

  return (
    <Box sx={{ p: 3, maxWidth: 1400, mx: 'auto' }}>
      {/* Header */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Typography variant="h5" fontWeight="700" sx={{ color: '#0f766e' }}>
              Agent 2: Tax Data & Reconciliation
            </Typography>
            <Chip label="Taxation Workstream 2" color="success" size="small" variant="outlined" />
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Trial Balance mapping, source tie-out, withholding tax certificate reconciliation & discrepancy detection.
          </Typography>
        </Box>

        <Button
          variant="contained"
          sx={{ bgcolor: '#0f766e', '&:hover': { bgcolor: '#115e59' } }}
          startIcon={<PlayIcon />}
          onClick={handleRunReconciliation}
          disabled={!engagement || running}
        >
          {running ? 'Reconciling Data...' : 'Run Reconciliation Agent'}
        </Button>
      </Stack>

      {message && (
        <Alert severity="success" sx={{ mb: 3 }} onClose={() => setMessage(null)}>
          {message}
        </Alert>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Data Source Guide */}
      <Alert severity="info" variant="outlined" sx={{ mb: 3, borderColor: '#93c5fd' }}>
        <AlertTitle sx={{ fontWeight: 600 }}>How Agent 2 Ingests Financial Data</AlertTitle>
        <strong>Mode A — Approved Accounting (Recommended):</strong> Agent 2 pulls the CA-approved Trial Balance,
        P&L, and Balance Sheet from the Central Shared Data Layer. Requires Accounting to be completed and signed off first.
        <br />
        <strong>Mode B — Direct Client Records (Standalone):</strong> Agent 2 maps data directly from uploaded
        client Trial Balance / GL exports. Use this when the Accounting Module has not been run yet. Upload source
        documents in <strong>Accounting → File Intake & OCR</strong> first.
      </Alert>

      {/* Source Selection Card */}
      <Card sx={{ mb: 4, border: '1px solid #e2e8f0', borderRadius: 2 }}>
        <CardContent sx={{ p: 2.5 }}>
          <Typography variant="subtitle1" fontWeight="700" sx={{ mb: 1.5 }}>
            Data Ingestion Source Mode
          </Typography>
          <RadioGroup
            row
            value={sourceMode}
            onChange={(e) => setSourceMode(e.target.value as any)}
          >
            <FormControlLabel
              value="approved_accounting"
              control={<Radio color="success" />}
              label={
                <Box>
                  <Typography variant="body2" fontWeight="600">
                    Mode A: Consume Published Accounting Output (Recommended)
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {latestAccounting
                      ? `Version ${latestAccounting.version} published on ${new Date(latestAccounting.created_at).toLocaleDateString()}`
                      : 'No approved output yet. Publish from Accounting Module first.'}
                  </Typography>
                </Box>
              }
            />
            <FormControlLabel
              value="client_direct"
              control={<Radio color="success" />}
              label={
                <Box>
                  <Typography variant="body2" fontWeight="600">
                    Mode B: Direct Client Records (Standalone Mode)
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Runs independently using raw client trial balance uploads without requiring accounting sign-off.
                  </Typography>
                </Box>
              }
            />
          </RadioGroup>
        </CardContent>
      </Card>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 5 }}>
          <CircularProgress color="success" />
        </Box>
      ) : workpapers.length === 0 ? (
        <Card sx={{ p: 4, textAlign: 'center', border: '1px dashed #cbd5e1' }}>
          <TableIcon sx={{ fontSize: 48, color: '#94a3b8', mb: 2 }} />
          <Typography variant="h6" fontWeight="600" gutterBottom>
            No Tax Workpapers Generated Yet
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Click "Run Reconciliation Agent" to map accounting records into FBR tax workpapers.
          </Typography>
          <Button variant="contained" sx={{ bgcolor: '#0f766e' }} onClick={handleRunReconciliation} disabled={!engagement || running}>
            Execute Agent 2
          </Button>
        </Card>
      ) : (
        <Grid container spacing={3}>
          {/* Mapped Categories */}
          <Grid item xs={12} md={7}>
            <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2 }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                  <ReconIcon sx={{ color: '#0f766e' }} />
                  <Typography variant="h6" fontWeight="700">
                    FBR Book-to-Tax Category Mappings
                  </Typography>
                  {mappingWp && (
                    <Chip label={`Source: v${mappingWp.source_version}`} size="small" color="primary" variant="outlined" />
                  )}
                </Stack>
                <Divider sx={{ mb: 2 }} />

                {mappingWp?.data?.categories ? (
                  <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #e2e8f0' }}>
                    <Table size="small">
                      <TableHead sx={{ bgcolor: '#f8fafc' }}>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 700 }}>Tax Workpaper Category</TableCell>
                          <TableCell align="right" sx={{ fontWeight: 700 }}>Mapped Amount (PKR)</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Status</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {Object.entries(mappingWp.data.categories as Record<string, number>).map(([cat, amt]) => (
                          <TableRow key={cat}>
                            <TableCell sx={{ textTransform: 'capitalize', fontWeight: 500 }}>
                              {cat.replace(/_/g, ' ')}
                            </TableCell>
                            <TableCell align="right" sx={{ fontWeight: 600 }}>
                              {Number(amt).toLocaleString()}
                            </TableCell>
                            <TableCell>
                              <Chip label="Reconciled" size="small" color="success" variant="outlined" sx={{ height: 22 }} />
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    No mapping details found in workpaper.
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Withholding Tax Reconciliation */}
          <Grid item xs={12} md={5}>
            <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2 }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                  <CheckIcon sx={{ color: '#0f766e' }} />
                  <Typography variant="h6" fontWeight="700">
                    Withholding Tax (WHT) Reconciliation
                  </Typography>
                </Stack>
                <Divider sx={{ mb: 2 }} />

                {whtWp ? (
                  <Stack spacing={2}>
                    <Box sx={{ p: 2, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                      <Typography variant="caption" color="text.secondary">Total WHT Deducted (GL / Books)</Typography>
                      <Typography variant="h6" fontWeight="700">
                        PKR {Number(whtWp.summary?.total_deducted_gl || 0).toLocaleString()}
                      </Typography>
                    </Box>
                    <Box sx={{ p: 2, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                      <Typography variant="caption" color="text.secondary">CPR Certificates Verified</Typography>
                      <Typography variant="h6" fontWeight="700" color="#16a34a">
                        PKR {Number(whtWp.summary?.cpr_verified_total || 0).toLocaleString()}
                      </Typography>
                    </Box>
                    <Box sx={{ p: 2, bgcolor: '#f0fdf4', borderRadius: 1.5, border: '1px solid #bbf7d0' }}>
                      <Typography variant="caption" color="text.secondary">Variance / Unmatched</Typography>
                      <Typography variant="h6" fontWeight="700" color="#15803d">
                        PKR {Number(whtWp.summary?.discrepancy || 0).toLocaleString()}
                      </Typography>
                    </Box>
                  </Stack>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    No withholding tax reconciliation workpaper yet.
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}
    </Box>
  );
};
