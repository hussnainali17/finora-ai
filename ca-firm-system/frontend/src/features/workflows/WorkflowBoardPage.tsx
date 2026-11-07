import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Typography,
} from '@mui/material';
import { PlayArrow, Refresh, SkipNext } from '@mui/icons-material';
import { useNavigate, useParams } from 'react-router-dom';
import {
  listWorkflows,
  resumeWorkflow,
  startWorkflow,
} from '../../services/workflowsApi';
import type { WorkflowRun, WorkflowStep } from '../../types/workflows';
import { STEP_LABELS } from '../../types/workflows';
import { useAuth } from '../auth/AuthContext';

const STEPS_ORDER: WorkflowStep[] = [
  'intake',
  'data_quality_gate',
  'accounting_review',
  'period_adjustments',
  'ca_approval',
  'financial_reporting',
  'validation_gate',
  'completed',
];

export function WorkflowBoardPage(): React.JSX.Element {
  const { clientId, periodId } = useParams<{ clientId: string; periodId: string }>();
  const navigate = useNavigate();
  const { principal } = useAuth();

  const [workflows, setWorkflows] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [resuming, setResuming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canExecute = principal?.permissions?.includes('workflow:execute') ?? false;
  const canRead = principal?.permissions?.includes('workflow:read') ?? false;

  const fetchWorkflows = useCallback(async () => {
    if (!clientId || !periodId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listWorkflows(clientId, periodId);
      setWorkflows(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load workflow state');
    } finally {
      setLoading(false);
    }
  }, [clientId, periodId]);

  useEffect(() => {
    if (canRead) void fetchWorkflows();
  }, [canRead, fetchWorkflows]);

  // Poll while running
  useEffect(() => {
    const hasActive = workflows.some((w) => w.status === 'running');
    if (!hasActive) return;
    const interval = setInterval(() => void fetchWorkflows(), 4000);
    return () => clearInterval(interval);
  }, [workflows, fetchWorkflows]);

  const handleStart = async () => {
    if (!clientId || !periodId) return;
    setStarting(true);
    setError(null);
    try {
      await startWorkflow(clientId, periodId);
      await fetchWorkflows();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start workflow');
    } finally {
      setStarting(false);
    }
  };

  const handleResume = async (wfId: string) => {
    if (!clientId || !periodId) return;
    setResuming(true);
    setError(null);
    try {
      await resumeWorkflow(clientId, periodId, wfId);
      await fetchWorkflows();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to resume workflow');
    } finally {
      setResuming(false);
    }
  };

  const activeWf = workflows[0];
  const activeStepIdx = activeWf
    ? STEPS_ORDER.indexOf(activeWf.current_step as WorkflowStep)
    : 0;

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h5" component="h1">
            End-to-End Accounting Workflow (LangGraph)
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Autonomous coordination of Agent 1 (Intake) → Agent 2 (Review) → Agent 3 (Adjustments) → Human Checkpoint → Agent 4 (Reporting).
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" startIcon={<Refresh />} onClick={() => void fetchWorkflows()} disabled={loading}>
            Refresh
          </Button>
          {canExecute && (
            <Button
              variant="contained"
              startIcon={starting ? <CircularProgress size={16} /> : <PlayArrow />}
              onClick={() => void handleStart()}
              disabled={starting || loading || activeWf?.status === 'running'}
            >
              Start Workflow
            </Button>
          )}
        </Stack>
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {activeWf && (
        <Paper sx={{ p: 3, mb: 3 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
            <Box>
              <Typography variant="subtitle1" fontWeight="bold">
                Current Run: {activeWf.id.slice(0, 8)}...
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Started {new Date(activeWf.created_at).toLocaleString()}
              </Typography>
            </Box>
            <Stack direction="row" spacing={1} alignItems="center">
              <Chip
                label={activeWf.status.toUpperCase()}
                color={
                  activeWf.status === 'completed'
                    ? 'success'
                    : activeWf.status === 'paused_approval'
                    ? 'warning'
                    : activeWf.status === 'running'
                    ? 'info'
                    : 'error'
                }
              />
              {activeWf.status === 'paused_approval' && canExecute && (
                <Button
                  variant="contained"
                  color="warning"
                  startIcon={<SkipNext />}
                  onClick={() => void handleResume(activeWf.id)}
                  disabled={resuming}
                >
                  Resume After CA Approval
                </Button>
              )}
            </Stack>
          </Stack>

          {activeWf.status === 'paused_approval' && (
            <Alert severity="warning" sx={{ mb: 3 }}>
              <strong>Human-in-the-Loop Checkpoint:</strong> The workflow has generated proposed period-end adjustments. Please review and approve them before resuming statement generation.
              <Button
                size="small"
                sx={{ ml: 2 }}
                onClick={() => navigate(`/clients/${clientId}/periods/${periodId}/adjustments`)}
              >
                Go to Adjustments
              </Button>
            </Alert>
          )}

          {activeWf.error_message && (
            <Alert severity="error" sx={{ mb: 3 }}>
              {activeWf.error_message}
            </Alert>
          )}

          <Stepper activeStep={activeStepIdx} alternativeLabel>
            {STEPS_ORDER.map((stepKey) => (
              <Step key={stepKey}>
                <StepLabel>{STEP_LABELS[stepKey]}</StepLabel>
              </Step>
            ))}
          </Stepper>
        </Paper>
      )}

      {/* Navigation shortcuts */}
      <Grid container spacing={2}>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ cursor: 'pointer', height: '100%' }} onClick={() => navigate(`/clients/${clientId}/periods/${periodId}/review`)}>
            <CardContent>
              <Typography variant="subtitle2" color="primary">Agent 2</Typography>
              <Typography variant="h6">Accounting Review</Typography>
              <Typography variant="body2" color="text.secondary">Inspect AR, AP, Bank, Payroll and Inventory findings.</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ cursor: 'pointer', height: '100%' }} onClick={() => navigate(`/clients/${clientId}/periods/${periodId}/adjustments`)}>
            <CardContent>
              <Typography variant="subtitle2" color="primary">Agent 3</Typography>
              <Typography variant="h6">Period Adjustments</Typography>
              <Typography variant="body2" color="text.secondary">Review proposed accruals, prepayments, and depreciation.</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ cursor: 'pointer', height: '100%' }} onClick={() => navigate(`/clients/${clientId}/periods/${periodId}/reports`)}>
            <CardContent>
              <Typography variant="subtitle2" color="primary">Agent 4</Typography>
              <Typography variant="h6">Financial Statements</Typography>
              <Typography variant="body2" color="text.secondary">Adjusted TB, Balance Sheet, P&L, and CA Sign-off.</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
