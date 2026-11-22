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
  Paper,
} from '@mui/material';
import {
  Calculate as ComputeIcon,
  PlayArrow as PlayIcon,
  ReceiptLong as ReceiptIcon,
  Security as SecurityIcon,
} from '@mui/icons-material';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  listTaxEngagements,
  listTaxCalculations,
  runTaxComputation,
} from '../../services/taxationApi';
import type { TaxCalculationRun, TaxEngagement } from '../../types/taxation';

export const TaxComputationPage: React.FC = () => {
  const { activeClient, activePeriod } = useWorkspace();
  const [engagement, setEngagement] = useState<TaxEngagement | null>(null);
  const [, setCalculations] = useState<TaxCalculationRun[]>([]);
  const [activeRun, setActiveRun] = useState<TaxCalculationRun | null>(null);

  const [loading, setLoading] = useState<boolean>(true);
  const [running, setRunning] = useState<boolean>(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    if (!activeClient || !activePeriod) return;
    try {
      setLoading(true);
      setError(null);
      const engRes = await listTaxEngagements(activeClient.id, activePeriod.id);
      if (engRes.items.length === 0) {
        setEngagement(null);
        return;
      }
      const eng = engRes.items[0];
      setEngagement(eng);

      const calcRes = await listTaxCalculations(activeClient.id, activePeriod.id, eng.id);
      setCalculations(calcRes.items);
      setActiveRun(calcRes.items[0] || null);
    } catch (err: any) {
      setError(err?.message || 'Failed to load tax computation data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [activeClient, activePeriod]);

  const handleRunComputation = async () => {
    if (!activeClient || !activePeriod || !engagement) return;
    try {
      setRunning(true);
      setError(null);
      await runTaxComputation(activeClient.id, activePeriod.id, engagement.id);
      setMessage('Agent 3 Deterministic Tax Computation executed successfully.');
      await loadData();
    } catch (err: any) {
      setError(err?.message || 'Failed to execute tax computation');
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

  return (
    <Box sx={{ p: 3, maxWidth: 1400, mx: 'auto' }}>
      {/* Header */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Typography variant="h5" fontWeight="700" sx={{ color: '#0f766e' }}>
              Agent 3: Tax Computation & Compliance
            </Typography>
            <Chip label="Taxation Workstream 3" color="success" size="small" variant="outlined" />
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Deterministic statutory tax engine: Book-to-Tax adjustments, Section 113 Minimum Tax, Section 113C ACT & Section 4C Super Tax.
          </Typography>
        </Box>

        <Button
          variant="contained"
          sx={{ bgcolor: '#0f766e', '&:hover': { bgcolor: '#115e59' } }}
          startIcon={<PlayIcon />}
          onClick={handleRunComputation}
          disabled={!engagement || running}
        >
          {running ? 'Computing Tax Liability...' : 'Run Computation Agent'}
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

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 5 }}>
          <CircularProgress color="success" />
        </Box>
      ) : !activeRun ? (
        <Card sx={{ p: 4, textAlign: 'center', border: '1px dashed #cbd5e1' }}>
          <ComputeIcon sx={{ fontSize: 48, color: '#94a3b8', mb: 2 }} />
          <Typography variant="h6" fontWeight="600" gutterBottom>
            No Tax Calculations Performed Yet
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Click "Run Computation Agent" to execute deterministic tax liability calculations.
          </Typography>
          <Button variant="contained" sx={{ bgcolor: '#0f766e' }} onClick={handleRunComputation} disabled={!engagement || running}>
            Execute Agent 3
          </Button>
        </Card>
      ) : (
        <Grid container spacing={3}>
          {/* Book-to-Tax Bridge Summary Card */}
          <Grid item xs={12} md={7}>
            <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2 }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <ReceiptIcon sx={{ color: '#0f766e' }} />
                    <Typography variant="h6" fontWeight="700">
                      Pakistan Book-to-Tax Bridge (TY{activeRun.tax_year})
                    </Typography>
                  </Stack>
                  <Chip label={`Rules: ${activeRun.rules_version}`} size="small" color="primary" variant="outlined" />
                </Stack>
                <Divider sx={{ mb: 2.5 }} />

                <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #e2e8f0' }}>
                  <Table size="small">
                    <TableBody>
                      <TableRow sx={{ bgcolor: '#f8fafc' }}>
                        <TableCell sx={{ fontWeight: 600 }}>Accounting Net Profit Before Tax (PBT)</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>
                          PKR {Number(activeRun.accounting_profit_before_tax).toLocaleString()}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell sx={{ color: '#b91c1c' }}>
                          (+) Inadmissible Expenses (s.21, accounting depreciation, provisions)
                        </TableCell>
                        <TableCell align="right" sx={{ color: '#b91c1c', fontWeight: 600 }}>
                          + PKR {Number(activeRun.total_additions).toLocaleString()}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell sx={{ color: '#15803d' }}>
                          (-) Admissible Tax Deductions (3rd Schedule tax depreciation, initial allowance)
                        </TableCell>
                        <TableCell align="right" sx={{ color: '#15803d', fontWeight: 600 }}>
                          - PKR {Number(activeRun.total_deductions).toLocaleString()}
                        </TableCell>
                      </TableRow>
                      <TableRow sx={{ bgcolor: '#ecfdf5' }}>
                        <TableCell sx={{ fontWeight: 700, color: '#065f46' }}>
                          (=) Taxable Income (Income Tax Ordinance 2001)
                        </TableCell>
                        <TableCell align="right" sx={{ fontWeight: 800, color: '#065f46', fontSize: '1.05rem' }}>
                          PKR {Number(activeRun.taxable_income).toLocaleString()}
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </TableContainer>

                {/* Regime Comparison */}
                <Typography variant="subtitle1" fontWeight="700" sx={{ mt: 3, mb: 1.5, color: '#1e293b' }}>
                  Statutory Regimes Benchmark
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={6} sm={3}>
                    <Box sx={{ p: 1.5, border: '1px solid #e2e8f0', borderRadius: 1.5, bgcolor: '#f8fafc' }}>
                      <Typography variant="caption" color="text.secondary">Normal CIT (29%)</Typography>
                      <Typography variant="body2" fontWeight="700">
                        PKR {Number(activeRun.normal_corporate_tax).toLocaleString()}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Box sx={{ p: 1.5, border: '1px solid #e2e8f0', borderRadius: 1.5, bgcolor: '#f8fafc' }}>
                      <Typography variant="caption" color="text.secondary">Min Tax s.113 (1.25%)</Typography>
                      <Typography variant="body2" fontWeight="700">
                        PKR {Number(activeRun.minimum_tax_turnover).toLocaleString()}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Box sx={{ p: 1.5, border: '1px solid #e2e8f0', borderRadius: 1.5, bgcolor: '#f8fafc' }}>
                      <Typography variant="caption" color="text.secondary">ACT s.113C (17%)</Typography>
                      <Typography variant="body2" fontWeight="700">
                        PKR {Number(activeRun.alternate_corporate_tax).toLocaleString()}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={3}>
                    <Box sx={{ p: 1.5, border: '1px solid #e2e8f0', borderRadius: 1.5, bgcolor: '#f8fafc' }}>
                      <Typography variant="caption" color="text.secondary">Super Tax s.4C</Typography>
                      <Typography variant="body2" fontWeight="700">
                        PKR {Number(activeRun.super_tax_4c).toLocaleString()}
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          {/* Net Tax Payable Card */}
          <Grid item xs={12} md={5}>
            <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2 }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                  <SecurityIcon sx={{ color: '#0f766e' }} />
                  <Typography variant="h6" fontWeight="700">
                    Net Tax Liability Due
                  </Typography>
                </Stack>
                <Divider sx={{ mb: 2.5 }} />

                <Stack spacing={2}>
                  <Box sx={{ p: 2, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                    <Typography variant="caption" color="text.secondary">Gross Tax Payable (Highest of CIT / Min Tax / ACT + s.4C)</Typography>
                    <Typography variant="h6" fontWeight="700">
                      PKR {Number(activeRun.final_gross_tax_payable).toLocaleString()}
                    </Typography>
                  </Box>

                  <Box sx={{ p: 2, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                    <Typography variant="caption" color="text.secondary">Less: Adjustable Withholding Tax & Advance Tax Paid</Typography>
                    <Typography variant="body1" fontWeight="600" color="#15803d">
                      - PKR {Number(Number(activeRun.withholding_tax_adjustable) + Number(activeRun.advance_tax_paid)).toLocaleString()}
                    </Typography>
                  </Box>

                  <Box sx={{ p: 2.5, bgcolor: '#ecfdf5', borderRadius: 2, border: '1px solid #a7f3d0' }}>
                    <Typography variant="caption" sx={{ color: '#065f46', fontWeight: 600 }}>
                      FINAL NET TAX PAYABLE / (REFUNDABLE)
                    </Typography>
                    <Typography variant="h4" fontWeight="800" sx={{ color: '#047857', mt: 0.5 }}>
                      PKR {Number(activeRun.net_tax_payable).toLocaleString()}
                    </Typography>
                  </Box>
                </Stack>
              </CardContent>
            </Card>
          </Grid>

          {/* Deterministic Calculation Trace */}
          {activeRun.calculation_trace && activeRun.calculation_trace.length > 0 && (
            <Grid item xs={12}>
              <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2 }}>
                <CardContent sx={{ p: 3 }}>
                  <Typography variant="h6" fontWeight="700" sx={{ mb: 2 }}>
                    Deterministic Calculation Audit Trace (Pure Python Decimal Proof)
                  </Typography>
                  <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #e2e8f0' }}>
                    <Table size="small">
                      <TableHead sx={{ bgcolor: '#f8fafc' }}>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 700 }}>Step</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Statutory Description</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>Rule Reference</TableCell>
                          <TableCell align="right" sx={{ fontWeight: 700 }}>Basis (PKR)</TableCell>
                          <TableCell align="right" sx={{ fontWeight: 700 }}>Rate Applied</TableCell>
                          <TableCell align="right" sx={{ fontWeight: 700 }}>Calculated Amount (PKR)</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {activeRun.calculation_trace.map((tr, idx) => (
                          <TableRow key={idx}>
                            <TableCell sx={{ fontWeight: 600 }}>{tr.step}</TableCell>
                            <TableCell>{tr.description}</TableCell>
                            <TableCell><Chip label={tr.rule_ref} size="small" variant="outlined" /></TableCell>
                            <TableCell align="right">{Number(tr.basis).toLocaleString()}</TableCell>
                            <TableCell align="right">{(Number(tr.rate) * 100).toFixed(2)}%</TableCell>
                            <TableCell align="right" sx={{ fontWeight: 700 }}>{Number(tr.amount).toLocaleString()}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </CardContent>
              </Card>
            </Grid>
          )}
        </Grid>
      )}
    </Box>
  );
};
