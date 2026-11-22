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
  Typography,
  Alert,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
} from '@mui/material';
import {
  Badge as BadgeIcon,
  CheckCircle as CheckIcon,
  Warning as WarningIcon,
  PlayArrow as PlayIcon,
  Business as BusinessIcon,
  Gavel as GavelIcon,
  Description as DocIcon,
} from '@mui/icons-material';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  listTaxEngagements,
  getTaxpayerProfile,
  runTaxIntake,
} from '../../services/taxationApi';
import type { TaxEngagement, TaxpayerProfile } from '../../types/taxation';

export const TaxIntakePage: React.FC = () => {
  const { activeClient, activePeriod } = useWorkspace();
  const [engagement, setEngagement] = useState<TaxEngagement | null>(null);
  const [profile, setProfile] = useState<TaxpayerProfile | null>(null);
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
        setProfile(null);
        return;
      }
      const eng = engRes.items[0];
      setEngagement(eng);
      const prof = await getTaxpayerProfile(activeClient.id, activePeriod.id, eng.id);
      setProfile(prof);
    } catch (err: any) {
      setError(err?.message || 'Failed to load taxpayer profile');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [activeClient, activePeriod]);

  const handleRunIntake = async () => {
    if (!activeClient || !activePeriod || !engagement) return;
    try {
      setRunning(true);
      setError(null);
      await runTaxIntake(activeClient.id, activePeriod.id, engagement.id);
      setMessage('Tax Intake & Taxpayer Profile Agent executed successfully.');
      await loadData();
    } catch (err: any) {
      setError(err?.message || 'Failed to execute tax intake');
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
              Agent 1: Tax Intake & Taxpayer Profile
            </Typography>
            <Chip label="Taxation Workstream 1" color="success" size="small" variant="outlined" />
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Legal status identification, FBR tax obligations, jurisdictional rules & missing requirements.
          </Typography>
        </Box>

        <Button
          variant="contained"
          sx={{ bgcolor: '#0f766e', '&:hover': { bgcolor: '#115e59' } }}
          startIcon={<PlayIcon />}
          onClick={handleRunIntake}
          disabled={!engagement || running}
        >
          {running ? 'Executing Agent 1...' : 'Run Intake Agent'}
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
      ) : !profile ? (
        <Card sx={{ p: 4, textAlign: 'center', border: '1px dashed #cbd5e1' }}>
          <BadgeIcon sx={{ fontSize: 48, color: '#94a3b8', mb: 2 }} />
          <Typography variant="h6" fontWeight="600" gutterBottom>
            No Taxpayer Profile Extracted Yet
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Click "Run Intake Agent" to inspect client documents and construct the verified FBR taxpayer profile.
          </Typography>
          <Button variant="contained" sx={{ bgcolor: '#0f766e' }} onClick={handleRunIntake} disabled={!engagement || running}>
            Execute Agent 1 Intake
          </Button>
        </Card>
      ) : (
        <Grid container spacing={3}>
          {/* Profile Details Card */}
          <Grid item xs={12} md={7}>
            <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2 }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                  <BusinessIcon sx={{ color: '#0f766e' }} />
                  <Typography variant="h6" fontWeight="700">
                    Verified Taxpayer Profile
                  </Typography>
                  <Chip
                    label={profile.verified_by_ca ? 'Verified' : 'Draft / Active'}
                    color={profile.verified_by_ca ? 'success' : 'default'}
                    size="small"
                  />
                </Stack>
                <Divider sx={{ mb: 2.5 }} />

                <Grid container spacing={2}>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Business Legal Name</Typography>
                    <Typography variant="body1" fontWeight="600">{profile.business_name}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Legal Entity Form</Typography>
                    <Typography variant="body1" fontWeight="600" sx={{ textTransform: 'capitalize' }}>
                      {profile.legal_form}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">National Tax Number (NTN)</Typography>
                    <Typography variant="body1" fontWeight="600" sx={{ color: '#0f766e' }}>
                      {profile.ntn}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Sales Tax Reg. (STRN)</Typography>
                    <Typography variant="body1" fontWeight="600">
                      {profile.strn || 'Not Registered'}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Tax Year</Typography>
                    <Typography variant="body1" fontWeight="600">TY{profile.tax_year}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Residential Status</Typography>
                    <Typography variant="body1" fontWeight="600" sx={{ textTransform: 'capitalize' }}>
                      {profile.residential_status}
                    </Typography>
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">Principal Activity</Typography>
                    <Typography variant="body1" fontWeight="500">
                      {profile.principal_activity || 'Manufacturing, Trading & Services'}
                    </Typography>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>

            {/* Applicable Obligations */}
            <Card sx={{ mt: 3, border: '1px solid #e2e8f0', borderRadius: 2 }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                  <GavelIcon sx={{ color: '#0f766e' }} />
                  <Typography variant="h6" fontWeight="700">
                    Applicable Pakistan Tax Obligations
                  </Typography>
                </Stack>
                <Divider sx={{ mb: 2 }} />

                <Stack spacing={1}>
                  {profile.applicable_obligations.map((ob, idx) => (
                    <Box
                      key={idx}
                      sx={{
                        p: 1.5,
                        borderRadius: 1.5,
                        bgcolor: '#f8fafc',
                        border: '1px solid #e2e8f0',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <Stack direction="row" spacing={1.5} alignItems="center">
                        <CheckIcon sx={{ color: '#16a34a', fontSize: 20 }} />
                        <Typography variant="body2" fontWeight="600">
                          {ob}
                        </Typography>
                      </Stack>
                      <Chip label="Active Requirement" size="small" sx={{ bgcolor: '#ecfdf5', color: '#065f46' }} />
                    </Box>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Grid>

          {/* Missing Information & Documents Checklist */}
          <Grid item xs={12} md={5}>
            <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2, height: '100%' }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                  <DocIcon sx={{ color: '#d97706' }} />
                  <Typography variant="h6" fontWeight="700">
                    Missing Information & Action Items
                  </Typography>
                </Stack>
                <Divider sx={{ mb: 2 }} />

                {profile.missing_information && profile.missing_information.length > 0 ? (
                  <List>
                    {profile.missing_information.map((item, idx) => (
                      <ListItem key={idx} sx={{ px: 0 }}>
                        <ListItemIcon sx={{ minWidth: 32 }}>
                          <WarningIcon sx={{ color: '#f59e0b', fontSize: 20 }} />
                        </ListItemIcon>
                        <ListItemText
                          primary={item}
                          primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
                        />
                      </ListItem>
                    ))}
                  </List>
                ) : (
                  <Box sx={{ p: 3, textAlign: 'center', bgcolor: '#f0fdf4', borderRadius: 2 }}>
                    <CheckIcon sx={{ color: '#16a34a', fontSize: 36, mb: 1 }} />
                    <Typography variant="body2" fontWeight="600" color="#166534">
                      All Mandatory Intake Facts Collected
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Ready to proceed to Agent 2: Tax Data & Reconciliation.
                    </Typography>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}
    </Box>
  );
};
