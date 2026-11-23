import React, { useEffect, useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  Stack,
  Typography,
  Alert,
} from '@mui/material';
import {
  CloudUpload as CloudUploadIcon,
  FactCheck as FactCheckIcon,
  Balance as BalanceIcon,
  Assessment as AssessmentIcon,
  Hub as HubIcon,
  ArrowForward as ArrowForwardIcon,
  Share as ShareIcon,
  CheckCircle as CheckCircleIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { publishAccountingOutput, getLatestApprovedAccounting } from '../../services/sharedDataApi';
import type { ApprovedModuleOutput } from '../../types/sharedData';

export const AccountingDashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { activeClient, activePeriod } = useWorkspace();
  const [latestShared, setLatestShared] = useState<ApprovedModuleOutput | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [publishing, setPublishing] = useState<boolean>(false);
  const [publishSuccess, setPublishSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeClient || !activePeriod) return;
    setLoading(true);
    getLatestApprovedAccounting(activeClient.id, activePeriod.id)
      .then((out) => setLatestShared(out))
      .catch(() => setLatestShared(null))
      .finally(() => setLoading(false));
  }, [activeClient, activePeriod]);

  const handleManualPublish = async () => {
    if (!activeClient || !activePeriod) return;
    try {
      setPublishing(true);
      setError(null);
      const res = await publishAccountingOutput(activeClient.id, activePeriod.id, 'Published via Accounting Dashboard');
      setLatestShared(res);
      setPublishSuccess(`Successfully published accounting output version ${res.version} to Central Shared Layer.`);
    } catch (err: any) {
      setError(err?.message || 'Failed to publish accounting output.');
    } finally {
      setPublishing(false);
    }
  };

  const basePath = activeClient && activePeriod ? `/clients/${activeClient.id}/periods/${activePeriod.id}` : '';

  if (!activeClient || !activePeriod) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">Please select an active client company and accounting period to view the Accounting Module.</Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3, maxWidth: 1400, mx: 'auto' }}>
      {/* Header */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Typography variant="h5" fontWeight="700" sx={{ color: '#1e293b' }}>
              Accounting Module Dashboard
            </Typography>
            <Chip label="Independent Module" color="primary" size="small" variant="outlined" />
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            {activeClient.name} • Period: {activePeriod.label}
          </Typography>
        </Box>

        <Stack direction="row" spacing={2}>
          <Button
            variant="contained"
            color="primary"
            startIcon={<HubIcon />}
            onClick={() => navigate(`${basePath}/workflows`)}
          >
            Autonomous Workflow
          </Button>
          <Button
            variant="outlined"
            color="secondary"
            startIcon={<ShareIcon />}
            onClick={handleManualPublish}
            disabled={publishing}
          >
            {publishing ? 'Publishing...' : 'Publish to Shared Layer'}
          </Button>
        </Stack>
      </Stack>

      {publishSuccess && (
        <Alert severity="success" sx={{ mb: 3 }} onClose={() => setPublishSuccess(null)}>
          {publishSuccess}
        </Alert>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Shared Data Status Banner */}
      <Card sx={{ mb: 4, bgcolor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 2 }}>
        <CardContent sx={{ p: 2.5 }}>
          <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ md: 'center' }} spacing={2}>
            <Stack direction="row" spacing={2} alignItems="center">
              <Box sx={{ p: 1.5, borderRadius: 2, bgcolor: '#e0e7ff', color: '#4338ca' }}>
                <ShareIcon />
              </Box>
              <Box>
                <Typography variant="subtitle1" fontWeight="700" sx={{ color: '#0f172a' }}>
                  Central Shared Data Layer Integration
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {loading ? (
                    'Checking published status...'
                  ) : latestShared ? (
                    `Active Approved Output: Version ${latestShared.version} • Published ${new Date(latestShared.created_at).toLocaleString()}`
                  ) : (
                    'No published accounting outputs yet. Approved reports will automatically publish here, or you can publish manually.'
                  )}
                </Typography>
              </Box>
            </Stack>

            {latestShared && (
              <Chip
                icon={<CheckCircleIcon />}
                label={`v${latestShared.version} Ready for Taxation`}
                color="success"
                variant="filled"
              />
            )}
          </Stack>
        </CardContent>
      </Card>

      {/* 4 Agent Workstreams */}
      <Typography variant="subtitle1" fontWeight="700" sx={{ mb: 2, color: '#334155' }}>
        Accounting Agent Workstreams
      </Typography>

      <Grid container spacing={3}>
        {/* Step 1 */}
        <Grid item xs={12} sm={6} md={3}>
          <Card
            sx={{
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              border: '1px solid #e2e8f0',
              borderRadius: 2,
              '&:hover': { boxShadow: 4, borderColor: '#38bdf8' },
            }}
          >
            <CardContent>
              <Box sx={{ color: '#0284c7', mb: 1.5 }}>
                <CloudUploadIcon fontSize="large" />
              </Box>
              <Typography variant="h6" fontWeight="700" gutterBottom>
                1. Intake & Preparation (Agent 1)
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Consumes centrally extracted documents, categorizes transactions, maps to Chart of Accounts, flags duplicates & exceptions, and prepares structured inputs for Reconciliation.
              </Typography>
            </CardContent>
            <Box sx={{ p: 2, pt: 0 }}>
              <Button
                variant="text"
                fullWidth
                endIcon={<ArrowForwardIcon />}
                onClick={() => navigate(`${basePath}`)}
              >
                Open Intake
              </Button>
            </Box>
          </Card>
        </Grid>

        {/* Step 2 */}
        <Grid item xs={12} sm={6} md={3}>
          <Card
            sx={{
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              border: '1px solid #e2e8f0',
              borderRadius: 2,
              '&:hover': { boxShadow: 4, borderColor: '#a78bfa' },
            }}
          >
            <CardContent>
              <Box sx={{ color: '#7c3aed', mb: 1.5 }}>
                <FactCheckIcon fontSize="large" />
              </Box>
              <Typography variant="h6" fontWeight="700" gutterBottom>
                2. Accounting Review
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Cross-document reconciliation, anomaly detection, duplicate detection, and missing documentation flags.
              </Typography>
            </CardContent>
            <Box sx={{ p: 2, pt: 0 }}>
              <Button
                variant="text"
                fullWidth
                endIcon={<ArrowForwardIcon />}
                onClick={() => navigate(`${basePath}/review`)}
              >
                Open Review
              </Button>
            </Box>
          </Card>
        </Grid>

        {/* Step 3 */}
        <Grid item xs={12} sm={6} md={3}>
          <Card
            sx={{
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              border: '1px solid #e2e8f0',
              borderRadius: 2,
              '&:hover': { boxShadow: 4, borderColor: '#f59e0b' },
            }}
          >
            <CardContent>
              <Box sx={{ color: '#d97706', mb: 1.5 }}>
                <BalanceIcon fontSize="large" />
              </Box>
              <Typography variant="h6" fontWeight="700" gutterBottom>
                3. Period Adjustments
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Accruals, prepayments, depreciation schedules, and period-end adjusting journal entries.
              </Typography>
            </CardContent>
            <Box sx={{ p: 2, pt: 0 }}>
              <Button
                variant="text"
                fullWidth
                endIcon={<ArrowForwardIcon />}
                onClick={() => navigate(`${basePath}/adjustments`)}
              >
                Open Adjustments
              </Button>
            </Box>
          </Card>
        </Grid>

        {/* Step 4 */}
        <Grid item xs={12} sm={6} md={3}>
          <Card
            sx={{
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              border: '1px solid #e2e8f0',
              borderRadius: 2,
              '&:hover': { boxShadow: 4, borderColor: '#10b981' },
            }}
          >
            <CardContent>
              <Box sx={{ color: '#059669', mb: 1.5 }}>
                <AssessmentIcon fontSize="large" />
              </Box>
              <Typography variant="h6" fontWeight="700" gutterBottom>
                4. Financial Statements
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Profit & Loss, Balance Sheet, Trial Balance tie-out, and CA final sign-off with auto-publishing.
              </Typography>
            </CardContent>
            <Box sx={{ p: 2, pt: 0 }}>
              <Button
                variant="text"
                fullWidth
                endIcon={<ArrowForwardIcon />}
                onClick={() => navigate(`${basePath}/reports`)}
              >
                Open Statements
              </Button>
            </Box>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};
