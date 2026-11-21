import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  Paper,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Typography,
} from '@mui/material';
import {
  PlayArrow,
  Refresh,
  SkipNext,
  AutoAwesome,
  CheckCircle,
  HourglassEmpty,
  Error as ErrorIcon,
  FactCheck,
  Balance,
  Assessment,
  ArrowForward,
} from '@mui/icons-material';
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
    const interval = setInterval(() => void fetchWorkflows(), 3000);
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
    <Box className="animate-fade-in">
      {/* Header */}
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={2} sx={{ mb: 3 }}>
        <Box>
          <Stack direction="row" alignItems="center" spacing={1.5}>
            <Box
              sx={{
                width: 36,
                height: 36,
                borderRadius: '10px',
                background: 'linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <AutoAwesome sx={{ color: '#ffffff', fontSize: 20 }} />
            </Box>
            <Typography variant="h5" fontWeight="800">
              Autonomous Accounting Pipeline
            </Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Automated LangGraph coordination: Intake → Review → Adjustments → CA Checkpoint → Financial Statements.
          </Typography>
        </Box>

        <Stack direction="row" spacing={1.5} alignItems="center">
          <Button
            variant="contained"
            color="secondary"
            startIcon={<AutoAwesome />}
            onClick={() => navigate(`/clients/${clientId}/periods/${periodId}/ca-review`)}
            sx={{
              background: 'linear-gradient(135deg, #6366f1 0%, #0ea5e9 100%)',
              fontWeight: 700,
              textTransform: 'none',
              borderRadius: '8px',
            }}
          >
            CA Review & AI Chat
          </Button>
          <Button variant="outlined" startIcon={<Refresh />} onClick={() => void fetchWorkflows()} disabled={loading}>
            Refresh
          </Button>
          {canExecute && (
            <Button
              variant="contained"
              size="large"
              startIcon={starting ? <CircularProgress size={16} color="inherit" /> : <PlayArrow />}
              onClick={() => void handleStart()}
              disabled={starting || loading || activeWf?.status === 'running'}
              sx={{
                background: 'linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%)',
                fontWeight: 700,
                boxShadow: '0 4px 14px rgba(79, 70, 229, 0.4)',
                '&:hover': {
                  background: 'linear-gradient(135deg, #4338ca 0%, #0891b2 100%)',
                },
              }}
            >
              {starting ? 'Starting Workflow...' : 'Start Workflow'}
            </Button>
          )}
        </Stack>
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 3, borderRadius: '12px' }}>{error}</Alert>}

      {/* Active Run Card */}
      {activeWf ? (
        <Paper
          sx={{
            p: { xs: 2.5, md: 3.5 },
            mb: 3.5,
            borderRadius: '18px',
            border: '1px solid #e2e8f0',
            boxShadow: '0 4px 20px -4px rgba(15, 23, 42, 0.06)',
          }}
        >
          <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={2} sx={{ mb: 3 }}>
            <Box>
              <Stack direction="row" spacing={1} alignItems="center">
                <Typography variant="subtitle1" fontWeight="800">
                  Run ID: {activeWf.id.slice(0, 8)}...
                </Typography>
                <Chip
                  icon={
                    activeWf.status === 'completed' ? (
                      <CheckCircle sx={{ fontSize: '14px !important' }} />
                    ) : activeWf.status === 'running' ? (
                      <HourglassEmpty sx={{ fontSize: '14px !important' }} />
                    ) : (
                      <ErrorIcon sx={{ fontSize: '14px !important' }} />
                    )
                  }
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
                  sx={{ fontWeight: 700, fontSize: '0.72rem' }}
                />
              </Stack>
              <Typography variant="caption" color="text.secondary">
                Started on {new Date(activeWf.created_at).toLocaleString()}
              </Typography>
            </Box>

            {activeWf.status === 'paused_approval' && canExecute && (
              <Button
                variant="contained"
                color="warning"
                size="large"
                startIcon={resuming ? <CircularProgress size={16} color="inherit" /> : <SkipNext />}
                onClick={() => void handleResume(activeWf.id)}
                disabled={resuming}
                sx={{
                  fontWeight: 700,
                  boxShadow: '0 4px 14px rgba(245, 158, 11, 0.4)',
                }}
              >
                {resuming ? 'Resuming...' : 'Resume After CA Approval'}
              </Button>
            )}
          </Stack>

          {/* Checkpoint Banner */}
          {activeWf.status === 'paused_approval' && (
            <Alert
              severity="warning"
              sx={{
                mb: 3.5,
                borderRadius: '14px',
                border: '1px solid #fde68a',
                bgcolor: '#fffbeb',
                p: 2,
              }}
            >
              <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={1.5}>
                <Box>
                  <Typography variant="subtitle2" fontWeight="800" sx={{ color: '#92400e' }}>
                    Human-in-the-Loop Checkpoint
                  </Typography>
                  <Typography variant="body2" sx={{ color: '#b45309' }}>
                    Agent 3 generated proposed adjustments. Please inspect & approve them under Period Adjustments, then click Resume.
                  </Typography>
                </Box>
                <Button
                  variant="outlined"
                  color="warning"
                  size="small"
                  onClick={() => navigate(`/clients/${clientId}/periods/${periodId}/adjustments`)}
                  sx={{ fontWeight: 700, whiteSpace: 'nowrap' }}
                >
                  Review Adjustments
                </Button>
              </Stack>
            </Alert>
          )}

          {activeWf.error_message && (
            <Alert severity="error" sx={{ mb: 3.5, borderRadius: '12px' }}>
              {activeWf.error_message}
            </Alert>
          )}

          {/* Stepper with Modern Glow */}
          <Box sx={{ py: 2 }}>
            <Stepper activeStep={activeStepIdx} alternativeLabel>
              {STEPS_ORDER.map((stepKey, idx) => {
                const isCurrent = idx === activeStepIdx;
                const isPassed = idx < activeStepIdx || activeWf.status === 'completed';
                return (
                  <Step key={stepKey} completed={isPassed}>
                    <StepLabel
                      StepIconProps={{
                        sx: {
                          fontSize: '1.75rem',
                          ...(isCurrent && {
                            color: '#4f46e5',
                            filter: 'drop-shadow(0 0 8px rgba(99, 102, 241, 0.6))',
                          }),
                          ...(isPassed && {
                            color: '#10b981',
                          }),
                        },
                      }}
                    >
                      <Typography
                        variant="caption"
                        fontWeight={isCurrent ? 800 : 600}
                        sx={{
                          color: isCurrent ? '#4f46e5' : isPassed ? '#10b981' : '#64748b',
                          fontSize: '0.75rem',
                        }}
                      >
                        {STEP_LABELS[stepKey]}
                      </Typography>
                    </StepLabel>
                  </Step>
                );
              })}
            </Stepper>
          </Box>
        </Paper>
      ) : (
        <Paper
          sx={{
            p: 4,
            mb: 3.5,
            borderRadius: '18px',
            textAlign: 'center',
            bgcolor: '#ffffff',
            border: '1px dashed #cbd5e1',
          }}
        >
          <Box
            sx={{
              width: 56,
              height: 56,
              borderRadius: '16px',
              bgcolor: '#eef2ff',
              color: '#4f46e5',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              mx: 'auto',
              mb: 2,
            }}
          >
            <PlayArrow sx={{ fontSize: 32 }} />
          </Box>
          <Typography variant="h6" fontWeight="700">
            No Workflow Runs Initiated
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 480, mx: 'auto', mt: 0.5, mb: 3 }}>
            Execute the complete autonomous accounting loop with 1 click. Finora AI will run all 4 agents sequentially with a CA review checkpoint.
          </Typography>
          {canExecute && (
            <Button
              variant="contained"
              size="large"
              startIcon={<PlayArrow />}
              onClick={() => void handleStart()}
              disabled={starting}
              sx={{
                px: 3.5,
                py: 1.2,
                borderRadius: '12px',
                fontWeight: 700,
                background: 'linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%)',
              }}
            >
              Start Autonomous Workflow Now
            </Button>
          )}
        </Paper>
      )}

      {/* Agent Shortcut Cards */}
      <Typography variant="h6" fontWeight="700" sx={{ mb: 2 }}>
        Inspect Individual Agent Modules
      </Typography>

      <Grid container spacing={2.5}>
        <Grid item xs={12} sm={6} md={4}>
          <Card
            sx={{
              cursor: 'pointer',
              height: '100%',
              borderRadius: '16px',
              transition: 'all 0.2s',
              '&:hover': { transform: 'translateY(-3px)', borderColor: '#818cf8' },
            }}
            onClick={() => navigate(`/clients/${clientId}/periods/${periodId}/review`)}
          >
            <CardContent sx={{ p: 2.5 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="subtitle2" color="primary" fontWeight="700">Agent 2</Typography>
                <FactCheck sx={{ color: '#818cf8' }} />
              </Stack>
              <Typography variant="h6" fontWeight="700">Accounting Review</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, minHeight: 40 }}>
                Inspect anomalies in AR, AP, Bank reconciliations, and Payroll ledgers.
              </Typography>
              <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mt: 2, color: '#4f46e5' }}>
                <Typography variant="button" sx={{ fontSize: '0.8rem', fontWeight: 700 }}>Open Review</Typography>
                <ArrowForward sx={{ fontSize: 14 }} />
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={4}>
          <Card
            sx={{
              cursor: 'pointer',
              height: '100%',
              borderRadius: '16px',
              transition: 'all 0.2s',
              '&:hover': { transform: 'translateY(-3px)', borderColor: '#f59e0b' },
            }}
            onClick={() => navigate(`/clients/${clientId}/periods/${periodId}/adjustments`)}
          >
            <CardContent sx={{ p: 2.5 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="subtitle2" sx={{ color: '#d97706', fontWeight: 700 }}>Agent 3</Typography>
                <Balance sx={{ color: '#f59e0b' }} />
              </Stack>
              <Typography variant="h6" fontWeight="700">Period Adjustments</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, minHeight: 40 }}>
                Approve or reject proposed depreciation, prepayments, and accrual entries.
              </Typography>
              <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mt: 2, color: '#d97706' }}>
                <Typography variant="button" sx={{ fontSize: '0.8rem', fontWeight: 700 }}>Open Adjustments</Typography>
                <ArrowForward sx={{ fontSize: 14 }} />
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={4}>
          <Card
            sx={{
              cursor: 'pointer',
              height: '100%',
              borderRadius: '16px',
              transition: 'all 0.2s',
              '&:hover': { transform: 'translateY(-3px)', borderColor: '#10b981' },
            }}
            onClick={() => navigate(`/clients/${clientId}/periods/${periodId}/reports`)}
          >
            <CardContent sx={{ p: 2.5 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="subtitle2" sx={{ color: '#059669', fontWeight: 700 }}>Agent 4</Typography>
                <Assessment sx={{ color: '#10b981' }} />
              </Stack>
              <Typography variant="h6" fontWeight="700">Financial Statements</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, minHeight: 40 }}>
                View Adjusted Trial Balance, Balance Sheet, P&L statement, and record CA sign-off.
              </Typography>
              <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mt: 2, color: '#059669' }}>
                <Typography variant="button" sx={{ fontSize: '0.8rem', fontWeight: 700 }}>Open Statements</Typography>
                <ArrowForward sx={{ fontSize: 14 }} />
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
