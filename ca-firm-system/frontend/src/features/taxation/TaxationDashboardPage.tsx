import React, { useEffect, useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  MenuItem,
  Select,
  Stack,
  Typography,
  Alert,
  TextField,
  LinearProgress,
} from '@mui/material';
import {
  Badge as ProfileIcon,
  CompareArrows as ReconIcon,
  Calculate as ComputeIcon,
  FactCheck as FilingIcon,
  PlayArrow as PlayIcon,
  CheckCircle as CheckCircleIcon,
  ArrowForward as ArrowForwardIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  listTaxEngagements,
  createTaxEngagement,
  startTaxWorkflow,
  getTaxWorkflow,
  resumeTaxWorkflow,
} from '../../services/taxationApi';
import { getLatestApprovedAccounting } from '../../services/sharedDataApi';
import type { TaxEngagement, TaxWorkflowRun } from '../../types/taxation';
import type { ApprovedModuleOutput } from '../../types/sharedData';

export const TaxationDashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { activeClient, activePeriod } = useWorkspace();

  const [engagements, setEngagements] = useState<TaxEngagement[]>([]);
  const [selectedEng, setSelectedEng] = useState<TaxEngagement | null>(null);
  const [latestAccounting, setLatestAccounting] = useState<ApprovedModuleOutput | null>(null);
  const [workflowRun, setWorkflowRun] = useState<TaxWorkflowRun | null>(null);

  const [, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [createDialogOpen, setCreateDialogOpen] = useState<boolean>(false);
  const [newTaxYear, setNewTaxYear] = useState<number>(2025);
  const [newTaxType, setNewTaxType] = useState<string>('corporate');
  const [error, setError] = useState<string | null>(null);
  const [infoMsg, setInfoMsg] = useState<string | null>(null);

  const basePath = activeClient && activePeriod ? `/clients/${activeClient.id}/periods/${activePeriod.id}/taxation` : '';

  const loadData = async () => {
    if (!activeClient || !activePeriod) return;
    try {
      setLoading(true);
      setError(null);

      // Load engagements
      const engRes = await listTaxEngagements(activeClient.id, activePeriod.id);
      setEngagements(engRes.items);
      const active = engRes.items[0] || null;
      setSelectedEng(active);

      // Load latest accounting output
      try {
        const acct = await getLatestApprovedAccounting(activeClient.id, activePeriod.id);
        setLatestAccounting(acct);
      } catch {
        setLatestAccounting(null);
      }

      // Load workflow run if engagement exists
      if (active) {
        try {
          const wf = await getTaxWorkflow(activeClient.id, activePeriod.id, active.id);
          setWorkflowRun(wf);
        } catch {
          setWorkflowRun(null);
        }
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load taxation data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [activeClient, activePeriod]);

  const handleCreateEngagement = async () => {
    if (!activeClient || !activePeriod) return;
    try {
      setActionLoading(true);
      const created = await createTaxEngagement(activeClient.id, activePeriod.id, {
        tax_year: newTaxYear,
        tax_type: newTaxType,
        tax_period_label: `TY${newTaxYear}`,
      });
      setCreateDialogOpen(false);
      setInfoMsg(`Tax engagement for TY${created.tax_year} created successfully.`);
      await loadData();
    } catch (err: any) {
      setError(err?.message || 'Failed to create engagement');
    } finally {
      setActionLoading(false);
    }
  };

  const handleStartWorkflow = async () => {
    if (!activeClient || !activePeriod || !selectedEng) return;
    try {
      setActionLoading(true);
      setError(null);
      const wf = await startTaxWorkflow(activeClient.id, activePeriod.id, selectedEng.id);
      setWorkflowRun(wf);
      setInfoMsg(`Autonomous Tax Workflow started (Run ID: ${wf.id.slice(0, 8)}). Current Step: ${wf.current_step}`);
    } catch (err: any) {
      setError(err?.message || 'Failed to start tax workflow');
    } finally {
      setActionLoading(false);
    }
  };

  const handleResumeWorkflow = async () => {
    if (!activeClient || !activePeriod || !selectedEng || !workflowRun) return;
    try {
      setActionLoading(true);
      setError(null);
      const wf = await resumeTaxWorkflow(activeClient.id, activePeriod.id, selectedEng.id, workflowRun.id, 'CA approved tax review');
      setWorkflowRun(wf);
      setInfoMsg(`Tax Workflow resumed! New Status: ${wf.status}`);
    } catch (err: any) {
      setError(err?.message || 'Failed to resume tax workflow');
    } finally {
      setActionLoading(false);
    }
  };

  if (!activeClient || !activePeriod) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">Please select an active client company and accounting period to access the Taxation Module.</Alert>
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
              Pakistan Taxation Module
            </Typography>
            <Chip label="Independent Module" color="success" size="small" variant="outlined" />
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {activeClient.name} • Period: {activePeriod.label}
          </Typography>
        </Box>

        <Stack direction="row" spacing={2} alignItems="center">
          {engagements.length > 0 ? (
            <Select
              size="small"
              value={selectedEng?.id || ''}
              onChange={(e) => {
                const found = engagements.find((x) => x.id === e.target.value);
                if (found) setSelectedEng(found);
              }}
              sx={{ minWidth: 160 }}
            >
              {engagements.map((eng) => (
                <MenuItem key={eng.id} value={eng.id}>
                  Tax Year {eng.tax_year} ({eng.tax_type})
                </MenuItem>
              ))}
            </Select>
          ) : (
            <Button
              variant="contained"
              sx={{ bgcolor: '#0f766e', '&:hover': { bgcolor: '#115e59' } }}
              onClick={() => setCreateDialogOpen(true)}
            >
              + Create Tax Engagement
            </Button>
          )}

          <Button
            variant="contained"
            color="success"
            startIcon={<PlayIcon />}
            disabled={!selectedEng || actionLoading}
            onClick={handleStartWorkflow}
          >
            Run Autonomous Tax Workflow
          </Button>
        </Stack>
      </Stack>

      {infoMsg && (
        <Alert severity="success" sx={{ mb: 3 }} onClose={() => setInfoMsg(null)}>
          {infoMsg}
        </Alert>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Upstream Accounting Output Card */}
      <Card sx={{ mb: 4, bgcolor: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 2 }}>
        <CardContent sx={{ p: 2.5 }}>
          <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ md: 'center' }} spacing={2}>
            <Stack direction="row" spacing={2} alignItems="center">
              <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: '#dcfce7', color: '#15803d' }}>
                <CheckCircleIcon />
              </Box>
              <Box>
                <Typography variant="subtitle1" fontWeight="700" sx={{ color: '#166534' }}>
                  Accounting Output Integration (Central Shared Layer)
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {latestAccounting ? (
                    `Approved Accounting Output v${latestAccounting.version} is available. P&L Net Profit: PKR ${(Number(latestAccounting.summary?.net_profit || 0)).toLocaleString()}`
                  ) : (
                    'No published accounting outputs found. Taxation will operate in standalone mode (direct client uploads).'
                  )}
                </Typography>
              </Box>
            </Stack>

            <Chip
              label={latestAccounting ? `Mode A: Using Accounting v${latestAccounting.version}` : 'Mode B: Standalone Mode'}
              color={latestAccounting ? 'success' : 'default'}
              variant="filled"
            />
          </Stack>
        </CardContent>
      </Card>

      {/* Workflow Run Status if active */}
      {workflowRun && (
        <Card sx={{ mb: 4, border: '1px solid #e2e8f0', borderRadius: 2 }}>
          <CardContent sx={{ p: 2.5 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
              <Typography variant="subtitle1" fontWeight="700">
                Tax Workflow State: {workflowRun.status.toUpperCase()}
              </Typography>
              <Chip
                label={workflowRun.current_step}
                color={workflowRun.status === 'completed' ? 'success' : workflowRun.status === 'paused_approval' ? 'warning' : 'primary'}
                size="small"
              />
            </Stack>
            {workflowRun.status === 'running' && <LinearProgress sx={{ mb: 2 }} />}
            {workflowRun.status === 'paused_approval' && (
              <Stack direction="row" spacing={2} alignItems="center" sx={{ mt: 2 }}>
                <Alert severity="warning" sx={{ flex: 1 }}>
                  Workflow paused at CA Approval Gate ({workflowRun.checkpoint_id}). Human-in-the-loop review required.
                </Alert>
                <Button variant="contained" color="warning" onClick={handleResumeWorkflow} disabled={actionLoading}>
                  CA Sign-Off & Resume
                </Button>
              </Stack>
            )}
          </CardContent>
        </Card>
      )}

      {/* 4 Agent Workstreams */}
      <Typography variant="subtitle1" fontWeight="700" sx={{ mb: 2, color: '#334155' }}>
        Pakistan Tax Multi-Agent Pipeline
      </Typography>

      <Grid container spacing={3}>
        {/* Agent 1 */}
        <Grid item xs={12} sm={6} md={3}>
          <Card
            sx={{
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              border: '1px solid #e2e8f0',
              borderRadius: 2,
              '&:hover': { boxShadow: 4, borderColor: '#0f766e' },
            }}
          >
            <CardContent>
              <Box sx={{ color: '#0f766e', mb: 1.5 }}>
                <ProfileIcon fontSize="large" />
              </Box>
              <Typography variant="h6" fontWeight="700" gutterBottom>
                1. Tax Intake & Profile
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Identifies legal status, NTN, STRN, applicable tax obligations (CIT, WHT, Sales Tax, Provincial), and missing documents.
              </Typography>
            </CardContent>
            <Box sx={{ p: 2, pt: 0 }}>
              <Button
                variant="text"
                fullWidth
                endIcon={<ArrowForwardIcon />}
                onClick={() => navigate(`${basePath}/profile`)}
              >
                Open Intake & Profile
              </Button>
            </Box>
          </Card>
        </Grid>

        {/* Agent 2 */}
        <Grid item xs={12} sm={6} md={3}>
          <Card
            sx={{
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              border: '1px solid #e2e8f0',
              borderRadius: 2,
              '&:hover': { boxShadow: 4, borderColor: '#0f766e' },
            }}
          >
            <CardContent>
              <Box sx={{ color: '#0d9488', mb: 1.5 }}>
                <ReconIcon fontSize="large" />
              </Box>
              <Typography variant="h6" fontWeight="700" gutterBottom>
                2. Tax Data & Recon
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Maps Trial Balance / GL exports into tax workpaper categories, reconciles withholding tax certificates (CPR) and sales tax.
              </Typography>
            </CardContent>
            <Box sx={{ p: 2, pt: 0 }}>
              <Button
                variant="text"
                fullWidth
                endIcon={<ArrowForwardIcon />}
                onClick={() => navigate(`${basePath}/reconciliation`)}
              >
                Open Data & Recon
              </Button>
            </Box>
          </Card>
        </Grid>

        {/* Agent 3 */}
        <Grid item xs={12} sm={6} md={3}>
          <Card
            sx={{
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              border: '1px solid #e2e8f0',
              borderRadius: 2,
              '&:hover': { boxShadow: 4, borderColor: '#0f766e' },
            }}
          >
            <CardContent>
              <Box sx={{ color: '#059669', mb: 1.5 }}>
                <ComputeIcon fontSize="large" />
              </Box>
              <Typography variant="h6" fontWeight="700" gutterBottom>
                3. Tax Computation
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Deterministic Pakistan rules engine (Pure Decimal): Section 21 disallowances, Section 113 minimum tax, ACT 113C, Super Tax 4C.
              </Typography>
            </CardContent>
            <Box sx={{ p: 2, pt: 0 }}>
              <Button
                variant="text"
                fullWidth
                endIcon={<ArrowForwardIcon />}
                onClick={() => navigate(`${basePath}/computation`)}
              >
                Open Computation
              </Button>
            </Box>
          </Card>
        </Grid>

        {/* Agent 4 */}
        <Grid item xs={12} sm={6} md={3}>
          <Card
            sx={{
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              border: '1px solid #e2e8f0',
              borderRadius: 2,
              '&:hover': { boxShadow: 4, borderColor: '#0f766e' },
            }}
          >
            <CardContent>
              <Box sx={{ color: '#16a34a', mb: 1.5 }}>
                <FilingIcon fontSize="large" />
              </Box>
              <Typography variant="h6" fontWeight="700" gutterBottom>
                4. Review & Filing Pack
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                FBR IRIS Form IT-1 schedule mapping (codes 7001-7017), cross-check validations, CA sign-off gate, and CPR submission pack.
              </Typography>
            </CardContent>
            <Box sx={{ p: 2, pt: 0 }}>
              <Button
                variant="text"
                fullWidth
                endIcon={<ArrowForwardIcon />}
                onClick={() => navigate(`${basePath}/filing`)}
              >
                Open Filing Pack
              </Button>
            </Box>
          </Card>
        </Grid>
      </Grid>

      {/* Create Engagement Dialog */}
      <Dialog open={createDialogOpen} onClose={() => setCreateDialogOpen(false)}>
        <DialogTitle>New Pakistan Tax Engagement</DialogTitle>
        <DialogContent sx={{ pt: 2, minWidth: 400 }}>
          <Stack spacing={2.5} sx={{ mt: 1 }}>
            <TextField
              label="Tax Year"
              type="number"
              fullWidth
              value={newTaxYear}
              onChange={(e) => setNewTaxYear(Number(e.target.value))}
              helperText="E.g. 2024 or 2025"
            />
            <TextField
              label="Entity Tax Type"
              select
              fullWidth
              value={newTaxType}
              onChange={(e) => setNewTaxType(e.target.value)}
            >
              <MenuItem value="corporate">Corporate / Private Limited (29%)</MenuItem>
              <MenuItem value="aop">Association of Persons (AOP)</MenuItem>
              <MenuItem value="individual">Individual / Sole Proprietor</MenuItem>
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreateEngagement} disabled={actionLoading}>
            Create Engagement
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
