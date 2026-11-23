import React, { useEffect, useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  Grid,
  InputLabel,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
  Alert,
  AlertTitle,
  IconButton,
  Tooltip,
} from '@mui/material';
import {
  Badge as BadgeIcon,
  CheckCircle as CheckIcon,
  Warning as WarningIcon,
  Error as ErrorIcon,
  Info as InfoIcon,
  PlayArrow as PlayIcon,
  Business as BusinessIcon,
  Gavel as GavelIcon,
  Description as DocIcon,
  Edit as EditIcon,
  ExpandMore as ExpandIcon,
  ExpandLess as CollapseIcon,
  ArrowForward as ArrowIcon,
  AutoFixHigh as AutoIcon,
} from '@mui/icons-material';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  createTaxEngagement,
  listTaxEngagements,
  getTaxpayerProfile,
  runTaxIntake,
} from '../../services/taxationApi';
import type { TaxEngagement, TaxpayerProfile, MissingInfoItem } from '../../types/taxation';

const LEGAL_FORMS = [
  { value: 'private_company', label: 'Private Limited Company' },
  { value: 'public_company', label: 'Public Limited Company' },
  { value: 'single_member_company', label: 'Single Member Company' },
  { value: 'association_of_persons', label: 'Association of Persons (AOP)' },
  { value: 'individual', label: 'Individual / Sole Proprietor' },
  { value: 'ngo_npo', label: 'NGO / Not-for-Profit' },
];

const JURISDICTIONS = [
  { value: 'Federal', label: 'Federal (FBR)' },
  { value: 'SRB', label: 'SRB — Sindh Revenue Board' },
  { value: 'PRA', label: 'PRA — Punjab Revenue Authority' },
  { value: 'KPRA', label: 'KPRA — KP Revenue Authority' },
  { value: 'BRA', label: 'BRA — Balochistan Revenue Authority' },
  { value: 'ICT', label: 'ICT — Islamabad Capital Territory' },
];

const SEVERITY_ICON: Record<string, React.ReactNode> = {
  critical: <ErrorIcon sx={{ color: '#dc2626', fontSize: 20 }} />,
  warning: <WarningIcon sx={{ color: '#f59e0b', fontSize: 20 }} />,
  info: <InfoIcon sx={{ color: '#3b82f6', fontSize: 20 }} />,
};
const SEVERITY_COLOR: Record<string, string> = {
  critical: '#fef2f2',
  warning: '#fffbeb',
  info: '#eff6ff',
};

export const TaxIntakePage: React.FC = () => {
  const { activeClient, activePeriod } = useWorkspace();
  const [engagement, setEngagement] = useState<TaxEngagement | null>(null);
  const [profile, setProfile] = useState<TaxpayerProfile | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [running, setRunning] = useState<boolean>(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [guideOpen, setGuideOpen] = useState<boolean>(true);
  const [dialogOpen, setDialogOpen] = useState<boolean>(false);

  // Taxpayer details form state
  const [formLegalForm, setFormLegalForm] = useState('private_company');
  const [formNtn, setFormNtn] = useState('');
  const [formStrn, setFormStrn] = useState('');
  const [formActivity, setFormActivity] = useState('General Trading & Commercial');
  const [formSector, setFormSector] = useState('Commercial');
  const [formJurisdictions, setFormJurisdictions] = useState<string[]>(['Federal', 'SRB']);

  const ensureEngagement = async (): Promise<TaxEngagement | null> => {
    if (!activeClient || !activePeriod) return null;
    // Try to list existing engagements
    const engRes = await listTaxEngagements(activeClient.id, activePeriod.id);
    if (engRes.items.length > 0) return engRes.items[0];
    // Auto-create a default engagement
    const currentYear = new Date().getFullYear();
    const eng = await createTaxEngagement(activeClient.id, activePeriod.id, {
      tax_year: currentYear,
      tax_period_label: `TY${currentYear}`,
      tax_type: 'composite',
      notes: 'Auto-created by Tax Intake screen',
    });
    return eng;
  };

  const loadData = async () => {
    if (!activeClient || !activePeriod) return;
    try {
      setLoading(true);
      setError(null);
      const eng = await ensureEngagement();
      if (!eng) {
        setEngagement(null);
        setProfile(null);
        return;
      }
      setEngagement(eng);
      try {
        const prof = await getTaxpayerProfile(activeClient.id, activePeriod.id, eng.id);
        setProfile(prof);
        // Pre-fill form from existing profile
        if (prof) {
          setFormLegalForm(prof.legal_form || 'private_company');
          setFormNtn(prof.ntn || '');
          setFormStrn(prof.strn || '');
          setFormActivity(prof.principal_activity || 'General Trading & Commercial');
          setFormSector(prof.business_sector || 'Commercial');
          setFormJurisdictions(prof.jurisdictions || ['Federal', 'SRB']);
        }
      } catch {
        setProfile(null);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load taxpayer profile');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [activeClient, activePeriod]);

  const handleRunIntake = async (overrideData?: Record<string, unknown>) => {
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
      await runTaxIntake(activeClient.id, activePeriod.id, eng.id, overrideData);
      setMessage('Tax Intake & Taxpayer Profile Agent executed successfully.');
      await loadData();
    } catch (err: any) {
      setError(err?.message || 'Failed to execute tax intake');
    } finally {
      setRunning(false);
    }
  };

  const handleAutoDetect = () => {
    void handleRunIntake();
  };

  const handleManualSubmit = () => {
    setDialogOpen(false);
    void handleRunIntake({
      legal_form: formLegalForm,
      ntn: formNtn || undefined,
      strn: formStrn || undefined,
      principal_activity: formActivity,
      business_sector: formSector,
      jurisdictions: formJurisdictions,
    });
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

        <Stack direction="row" spacing={1.5}>
          <Tooltip title="Manually configure taxpayer details before execution">
            <Button
              variant="outlined"
              sx={{ borderColor: '#0f766e', color: '#0f766e' }}
              startIcon={<EditIcon />}
              onClick={() => setDialogOpen(true)}
              disabled={running}
            >
              Configure Profile
            </Button>
          </Tooltip>
          <Button
            variant="contained"
            sx={{ bgcolor: '#0f766e', '&:hover': { bgcolor: '#115e59' } }}
            startIcon={running ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : <AutoIcon />}
            onClick={handleAutoDetect}
            disabled={running}
          >
            {running ? 'Executing Agent 1...' : 'Auto-Detect & Run'}
          </Button>
        </Stack>
      </Stack>

      {/* How Data Ingestion Works Guide */}
      <Card sx={{ mb: 3, border: '1px solid #bfdbfe', borderRadius: 2, bgcolor: '#eff6ff' }}>
        <CardContent sx={{ p: 2.5, '&:last-child': { pb: 2.5 } }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Stack direction="row" spacing={1} alignItems="center">
              <InfoIcon sx={{ color: '#2563eb' }} />
              <Typography variant="subtitle1" fontWeight="700" sx={{ color: '#1e40af' }}>
                How Taxation Data Ingestion Works
              </Typography>
            </Stack>
            <IconButton size="small" onClick={() => setGuideOpen(!guideOpen)}>
              {guideOpen ? <CollapseIcon /> : <ExpandIcon />}
            </IconButton>
          </Stack>
          <Collapse in={guideOpen}>
            <Box sx={{ mt: 2 }}>
              <Stack spacing={1.5}>
                {[
                  {
                    step: '1',
                    icon: '📁',
                    title: 'Upload Source Documents (Central Document Intelligence)',
                    desc: 'Invoices, CPR challans, Tax Returns, and Withholding Certificates are uploaded in Central Document Intelligence (or shared from Accounting).',
                  },
                  {
                    step: '2',
                    icon: '🔍',
                    title: 'Agent 1 — Tax Intake & Profile (This Screen)',
                    desc: 'Consumes centrally extracted documents. Verifies NTN/STRN, checks profile completeness, flags document conflicts for CA review, and prepares consolidated tax inputs.',
                  },
                  {
                    step: '3',
                    icon: '📊',
                    title: 'Agent 2 — Data & Reconciliation',
                    desc: 'Pulls CA-approved Trial Balance (Mode A) or raw uploaded files (Mode B). Maps into FBR workpapers. Reconciles CPR withholding certificates.',
                  },
                  {
                    step: '4',
                    icon: '🧮',
                    title: 'Agent 3 — Tax Computation',
                    desc: 'Calculates taxable income, s.113 Minimum Tax, s.113C ACT, s.4C Super Tax using deterministic Python Decimal arithmetic.',
                  },
                  {
                    step: '5',
                    icon: '✅',
                    title: 'Agent 4 — Review & Filing Pack',
                    desc: 'Validates computations, compiles FBR IRIS IT-1 return schedules, and prepares the CA approval pack.',
                  },
                ].map((item, idx) => (
                  <Stack key={idx} direction="row" spacing={2} alignItems="flex-start">
                    <Box
                      sx={{
                        minWidth: 32,
                        height: 32,
                        borderRadius: '50%',
                        bgcolor: '#2563eb',
                        color: '#fff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontWeight: 700,
                        fontSize: 14,
                        flexShrink: 0,
                      }}
                    >
                      {item.step}
                    </Box>
                    <Box>
                      <Typography variant="body2" fontWeight="600" sx={{ color: '#1e3a5f' }}>
                        {item.icon} {item.title}
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#475569' }}>
                        {item.desc}
                      </Typography>
                    </Box>
                  </Stack>
                ))}
              </Stack>
              <Alert severity="info" variant="outlined" sx={{ mt: 2, borderColor: '#93c5fd' }}>
                <AlertTitle sx={{ fontWeight: 600 }}>Two Ways to Start</AlertTitle>
                <strong>Auto-Detect:</strong> Click "Auto-Detect & Run" to have Agent 1 automatically scan existing
                uploaded documents and client profile.
                <br />
                <strong>Manual Config:</strong> Click "Configure Profile" to enter NTN, STRN, legal form, and
                jurisdictions before running the agent.
              </Alert>
            </Box>
          </Collapse>
        </CardContent>
      </Card>

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
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3, maxWidth: 500, mx: 'auto' }}>
            Start by clicking <strong>"Auto-Detect & Run"</strong> to let Agent 1 scan your uploaded documents
            and build a verified FBR taxpayer profile, or click <strong>"Configure Profile"</strong> to manually
            enter taxpayer details first.
          </Typography>
          <Stack direction="row" spacing={2} justifyContent="center">
            <Button
              variant="outlined"
              sx={{ borderColor: '#0f766e', color: '#0f766e' }}
              startIcon={<EditIcon />}
              onClick={() => setDialogOpen(true)}
              disabled={running}
            >
              Configure & Run
            </Button>
            <Button
              variant="contained"
              sx={{ bgcolor: '#0f766e' }}
              startIcon={<AutoIcon />}
              onClick={handleAutoDetect}
              disabled={running}
            >
              Auto-Detect & Run
            </Button>
          </Stack>
        </Card>
      ) : (
        <Grid container spacing={3}>
          {/* Profile Details Card */}
          <Grid item xs={12} md={7}>
            <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2 }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" spacing={1.5} alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <BusinessIcon sx={{ color: '#0f766e' }} />
                    <Typography variant="h6" fontWeight="700">
                      Verified Taxpayer Profile
                    </Typography>
                    <Chip
                      label={profile.verified_by_ca ? 'CA Verified' : `Draft v${profile.version}`}
                      color={profile.verified_by_ca ? 'success' : 'default'}
                      size="small"
                    />
                  </Stack>
                  <Tooltip title="Edit taxpayer details and re-run Agent 1">
                    <IconButton size="small" onClick={() => setDialogOpen(true)}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Stack>
                <Divider sx={{ mb: 2.5 }} />

                <Grid container spacing={2}>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Business Name</Typography>
                    <Typography variant="body1" fontWeight="600">
                      {String(profile.business_name || profile.verified_attributes?.client_name || activeClient?.name || '—')}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Legal Entity Form</Typography>
                    <Typography variant="body1" fontWeight="600" sx={{ textTransform: 'capitalize' }}>
                      {profile.legal_form?.replace(/_/g, ' ')}
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
                    <Typography variant="body1" fontWeight="600">
                      TY{String(profile.verified_attributes?.tax_year || engagement?.tax_year || '—')}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Business Sector</Typography>
                    <Typography variant="body1" fontWeight="600" sx={{ textTransform: 'capitalize' }}>
                      {profile.business_sector || '—'}
                    </Typography>
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">Principal Activity</Typography>
                    <Typography variant="body1" fontWeight="500">
                      {profile.principal_activity || '—'}
                    </Typography>
                  </Grid>
                  {profile.jurisdictions && profile.jurisdictions.length > 0 && (
                    <Grid item xs={12}>
                      <Typography variant="caption" color="text.secondary">Tax Jurisdictions</Typography>
                      <Stack direction="row" spacing={0.5} flexWrap="wrap" sx={{ mt: 0.5 }}>
                        {profile.jurisdictions.map((j) => (
                          <Chip key={j} label={j} size="small" variant="outlined" color="primary" sx={{ mb: 0.5 }} />
                        ))}
                      </Stack>
                    </Grid>
                  )}
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
                  <List disablePadding>
                    {profile.missing_information.map((item: MissingInfoItem, idx: number) => (
                      <ListItem
                        key={item.query_id || idx}
                        sx={{
                          px: 1.5,
                          py: 1,
                          mb: 1,
                          borderRadius: 1.5,
                          bgcolor: SEVERITY_COLOR[item.severity] || '#f8fafc',
                          border: '1px solid #e2e8f0',
                        }}
                      >
                        <ListItemIcon sx={{ minWidth: 32 }}>
                          {SEVERITY_ICON[item.severity] || SEVERITY_ICON.info}
                        </ListItemIcon>
                        <ListItemText
                          primary={item.question}
                          secondary={item.statutory_basis ? `Ref: ${item.statutory_basis}` : undefined}
                          primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
                          secondaryTypographyProps={{ variant: 'caption', sx: { color: '#64748b' } }}
                        />
                        <Chip
                          label={item.severity}
                          size="small"
                          sx={{
                            ml: 1,
                            textTransform: 'capitalize',
                            bgcolor: item.severity === 'critical' ? '#fecaca' : item.severity === 'warning' ? '#fde68a' : '#bfdbfe',
                            color: item.severity === 'critical' ? '#991b1b' : item.severity === 'warning' ? '#92400e' : '#1e40af',
                            fontWeight: 600,
                            fontSize: 11,
                          }}
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
                    <Box sx={{ mt: 2 }}>
                      <Button
                        size="small"
                        variant="outlined"
                        color="success"
                        endIcon={<ArrowIcon />}
                        href="/taxation/reconciliation"
                      >
                        Continue to Agent 2
                      </Button>
                    </Box>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* Taxpayer Details Configuration Dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 700, color: '#0f766e' }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <EditIcon />
            <span>Configure Taxpayer Details</span>
          </Stack>
        </DialogTitle>
        <DialogContent sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
            Enter or override taxpayer information before running Agent 1. These values will be verified against
            uploaded documents and client records.
          </Typography>
          <Stack spacing={2.5}>
            <FormControl fullWidth size="small">
              <InputLabel>Legal Entity Form</InputLabel>
              <Select
                value={formLegalForm}
                label="Legal Entity Form"
                onChange={(e) => setFormLegalForm(e.target.value)}
              >
                {LEGAL_FORMS.map((lf) => (
                  <MenuItem key={lf.value} value={lf.value}>{lf.label}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <Stack direction="row" spacing={2}>
              <TextField
                fullWidth
                size="small"
                label="NTN (National Tax Number)"
                placeholder="e.g. 1234567-8"
                value={formNtn}
                onChange={(e) => setFormNtn(e.target.value)}
                helperText="7-8 digit FBR NTN. Leave blank for auto-detection."
              />
              <TextField
                fullWidth
                size="small"
                label="STRN (Sales Tax Reg.)"
                placeholder="e.g. 12-34-5678-901-23"
                value={formStrn}
                onChange={(e) => setFormStrn(e.target.value)}
                helperText="13-digit STRN. Only for goods/services registrants."
              />
            </Stack>

            <TextField
              fullWidth
              size="small"
              label="Principal Business Activity"
              value={formActivity}
              onChange={(e) => setFormActivity(e.target.value)}
            />

            <TextField
              fullWidth
              size="small"
              label="Business Sector"
              value={formSector}
              onChange={(e) => setFormSector(e.target.value)}
            />

            <FormControl fullWidth size="small">
              <InputLabel>Tax Jurisdictions</InputLabel>
              <Select
                multiple
                value={formJurisdictions}
                label="Tax Jurisdictions"
                onChange={(e) => setFormJurisdictions(typeof e.target.value === 'string' ? e.target.value.split(',') : e.target.value)}
                renderValue={(selected) => (
                  <Stack direction="row" spacing={0.5} flexWrap="wrap">
                    {selected.map((v) => (
                      <Chip key={v} label={v} size="small" />
                    ))}
                  </Stack>
                )}
              >
                {JURISDICTIONS.map((j) => (
                  <MenuItem key={j.value} value={j.value}>{j.label}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
        </DialogContent>
        <DialogActions sx={{ p: 2.5 }}>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            sx={{ bgcolor: '#0f766e', '&:hover': { bgcolor: '#115e59' } }}
            startIcon={<PlayIcon />}
            onClick={handleManualSubmit}
          >
            Save & Run Agent 1
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
