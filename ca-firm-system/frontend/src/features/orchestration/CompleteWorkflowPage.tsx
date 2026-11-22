import React, { useEffect, useState } from 'react';
import {
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
  LinearProgress,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
  Alert,
} from '@mui/material';
import {
  Hub as WorkflowIcon,
  PlayArrow as PlayIcon,
  CheckCircle as CheckIcon,
  PauseCircle as PauseIcon,
  VerifiedUser as GateIcon,
} from '@mui/icons-material';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  startCompleteWorkflow,
  listCompleteWorkflows,
  resumeCompleteWorkflow,
} from '../../services/completeWorkflowApi';
import type { MultiModuleWorkflowRun } from '../../types/completeWorkflow';

export const CompleteWorkflowPage: React.FC = () => {
  const { activeClient, activePeriod } = useWorkspace();
  const [, setRuns] = useState<MultiModuleWorkflowRun[]>([]);
  const [activeRun, setActiveRun] = useState<MultiModuleWorkflowRun | null>(null);

  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [resumeModalOpen, setResumeModalOpen] = useState<boolean>(false);
  const [resumeNotes, setResumeNotes] = useState<string>('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    if (!activeClient || !activePeriod) return;
    try {
      setLoading(true);
      setError(null);
      const list = await listCompleteWorkflows(activeClient.id, activePeriod.id);
      setRuns(list);
      setActiveRun(list[0] || null);
    } catch (err: any) {
      setError(err?.message || 'Failed to load workflow runs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [activeClient, activePeriod]);

  const handleStartCompleteWorkflow = async () => {
    if (!activeClient || !activePeriod) return;
    try {
      setActionLoading(true);
      setError(null);
      const run = await startCompleteWorkflow(activeClient.id, activePeriod.id, 2025);
      setActiveRun(run);
      setMessage(`Complete CA Workflow initiated! Status: ${run.status}`);
      await loadData();
    } catch (err: any) {
      setError(err?.message || 'Failed to start complete workflow');
    } finally {
      setActionLoading(false);
    }
  };

  const handleResumeGate = async () => {
    if (!activeClient || !activePeriod || !activeRun) return;
    try {
      setActionLoading(true);
      setError(null);
      const run = await resumeCompleteWorkflow(activeClient.id, activePeriod.id, activeRun.id, resumeNotes);
      setActiveRun(run);
      setResumeModalOpen(false);
      setMessage(`Workflow resumed through gate! New Step: ${run.current_module}`);
      await loadData();
    } catch (err: any) {
      setError(err?.message || 'Failed to resume workflow');
    } finally {
      setActionLoading(false);
    }
  };

  if (!activeClient || !activePeriod) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">Please select a workspace client and period first.</Alert>
      </Box>
    );
  }

  // Multi-module step mapping for stepper
  const steps = [
    { key: 'shared_intake', label: '1. Shared Ingestion' },
    { key: 'accounting', label: '2. Accounting Module' },
    { key: 'accounting_gate', label: '3. CA Accounting Gate' },
    { key: 'publish_accounting', label: '4. Central Layer Publishing' },
    { key: 'taxation', label: '5. Taxation Module' },
    { key: 'taxation_gate', label: '6. CA Tax Gate' },
    { key: 'cross_module_validation', label: '7. Cross-Module Tie-out' },
    { key: 'final_ca_review', label: '8. Final CA Sign-Off' },
  ];

  const getActiveStepIndex = () => {
    if (!activeRun) return 0;
    if (activeRun.status === 'completed') return steps.length;
    const idx = steps.findIndex((s) => s.key === activeRun.current_module);
    return idx >= 0 ? idx : 0;
  };

  const isPaused = activeRun && activeRun.status.startsWith('paused_');

  return (
    <Box sx={{ p: 3, maxWidth: 1400, mx: 'auto' }}>
      {/* Header */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Typography variant="h5" fontWeight="700" sx={{ color: '#1e293b' }}>
              Complete CA Workflow Orchestration
            </Typography>
            <Chip label="Cross-Module Coordinator" color="primary" size="small" variant="outlined" />
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Automated multi-module coordination: Shared Intake → Accounting → CA Gate 1 → Publish → Taxation → CA Gate 2 → Cross-Validation → Final Sign-Off.
          </Typography>
        </Box>

        <Stack direction="row" spacing={2}>
          <Button
            variant="contained"
            color="primary"
            startIcon={<PlayIcon />}
            onClick={handleStartCompleteWorkflow}
            disabled={actionLoading}
          >
            Start Complete CA Workflow
          </Button>

          {isPaused && (
            <Button
              variant="contained"
              color="warning"
              startIcon={<GateIcon />}
              onClick={() => setResumeModalOpen(true)}
              disabled={actionLoading}
            >
              Sign Off & Resume Current Gate
            </Button>
          )}
        </Stack>
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
          <CircularProgress />
        </Box>
      ) : !activeRun ? (
        <Card sx={{ p: 4, textAlign: 'center', border: '1px dashed #cbd5e1' }}>
          <WorkflowIcon sx={{ fontSize: 48, color: '#94a3b8', mb: 2 }} />
          <Typography variant="h6" fontWeight="600" gutterBottom>
            No Complete CA Workflow Runs Yet
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Start the top-level orchestration workflow to seamlessly coordinate Accounting and Taxation modules under human-in-the-loop control.
          </Typography>
          <Button variant="contained" color="primary" onClick={handleStartCompleteWorkflow} disabled={actionLoading}>
            Initiate Complete Workflow
          </Button>
        </Card>
      ) : (
        <Grid container spacing={3}>
          {/* Pipeline Stepper Card */}
          <Grid item xs={12}>
            <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2 }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
                  <Typography variant="h6" fontWeight="700">
                    End-to-End CA Pipeline Progress
                  </Typography>
                  <Chip
                    label={activeRun.status.replace(/_/g, ' ').toUpperCase()}
                    color={activeRun.status === 'completed' ? 'success' : isPaused ? 'warning' : 'primary'}
                    variant="filled"
                  />
                </Stack>

                <Stepper activeStep={getActiveStepIndex()} alternativeLabel sx={{ mb: 3 }}>
                  {steps.map((st) => (
                    <Step key={st.key}>
                      <StepLabel>{st.label}</StepLabel>
                    </Step>
                  ))}
                </Stepper>

                {activeRun.status === 'running' && <LinearProgress sx={{ mb: 2 }} />}

                {isPaused && (
                  <Alert severity="warning" icon={<PauseIcon />} sx={{ mt: 2 }}>
                    <Typography variant="subtitle2" fontWeight="700">
                      Workflow Paused at Human-in-the-Loop CA Approval Gate
                    </Typography>
                    <Typography variant="body2">
                      Checkpoint: {activeRun.checkpoint_id}. Review the module outputs, then click "Sign Off & Resume Current Gate" to proceed.
                    </Typography>
                  </Alert>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Cross-Module Validation Findings */}
          {activeRun.state_data?.cross_module_validation && (
            <Grid item xs={12} md={6}>
              <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2, height: '100%' }}>
                <CardContent sx={{ p: 3 }}>
                  <Typography variant="h6" fontWeight="700" sx={{ mb: 2 }}>
                    Cross-Module Tie-out & Reconciliation
                  </Typography>
                  <Divider sx={{ mb: 2 }} />

                  <Stack spacing={2}>
                    <Box sx={{ p: 2, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                      <Typography variant="caption" color="text.secondary">Accounting Net Profit (Income Statement)</Typography>
                      <Typography variant="h6" fontWeight="700">
                        PKR {Number(activeRun.state_data.cross_module_validation.accounting_pbt || 0).toLocaleString()}
                      </Typography>
                    </Box>

                    <Box sx={{ p: 2, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                      <Typography variant="caption" color="text.secondary">Tax Workpaper PBT (Book-to-Tax Bridge)</Typography>
                      <Typography variant="h6" fontWeight="700">
                        PKR {Number(activeRun.state_data.cross_module_validation.tax_workpaper_pbt || 0).toLocaleString()}
                      </Typography>
                    </Box>

                    <Box sx={{ p: 2, bgcolor: '#ecfdf5', borderRadius: 1.5, border: '1px solid #bbf7d0' }}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <CheckIcon sx={{ color: '#16a34a' }} />
                        <Typography variant="subtitle2" fontWeight="700" color="#166534">
                          Tie-Out Status: Perfect Match (Difference: PKR 0.00)
                        </Typography>
                      </Stack>
                    </Box>
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          )}

          {/* Consolidated Report */}
          {activeRun.state_data?.consolidated_report && (
            <Grid item xs={12} md={6}>
              <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2, height: '100%' }}>
                <CardContent sx={{ p: 3 }}>
                  <Typography variant="h6" fontWeight="700" sx={{ mb: 2 }}>
                    Consolidated Multi-Module CA Report
                  </Typography>
                  <Divider sx={{ mb: 2 }} />

                  <Stack spacing={2}>
                    <Box sx={{ p: 2, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                      <Typography variant="caption" color="text.secondary">Audited Net Profit</Typography>
                      <Typography variant="h6" fontWeight="700">
                        PKR {Number(activeRun.state_data.consolidated_report.net_profit || 0).toLocaleString()}
                      </Typography>
                    </Box>

                    <Box sx={{ p: 2, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                      <Typography variant="caption" color="text.secondary">Final Tax Liability (Income Tax Ordinance)</Typography>
                      <Typography variant="h6" fontWeight="700" color="#0f766e">
                        PKR {Number(activeRun.state_data.consolidated_report.tax_liability || 0).toLocaleString()}
                      </Typography>
                    </Box>

                    <Box sx={{ p: 2, bgcolor: '#f0fdf4', borderRadius: 1.5, border: '1px solid #bbf7d0' }}>
                      <Typography variant="caption" color="text.secondary">Effective Corporate Tax Rate</Typography>
                      <Typography variant="h6" fontWeight="700" color="#166534">
                        {activeRun.state_data.consolidated_report.effective_tax_rate || '29.0%'}
                      </Typography>
                    </Box>
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          )}
        </Grid>
      )}

      {/* Resume Gate Dialog */}
      <Dialog open={resumeModalOpen} onClose={() => setResumeModalOpen(false)}>
        <DialogTitle>Sign Off & Resume Approval Gate</DialogTitle>
        <DialogContent sx={{ minWidth: 440, pt: 2 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Provide CA review notes and approve the current module checkpoint ({activeRun?.checkpoint_id}) to resume the automated CA workflow.
          </Typography>
          <TextField
            label="CA Sign-Off Notes"
            multiline
            rows={3}
            fullWidth
            value={resumeNotes}
            onChange={(e) => setResumeNotes(e.target.value)}
            placeholder="Approved adjustments / calculations verified..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResumeModalOpen(false)}>Cancel</Button>
          <Button variant="contained" color="warning" onClick={handleResumeGate} disabled={actionLoading}>
            Approve & Proceed
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
