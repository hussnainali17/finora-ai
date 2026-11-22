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
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
  Alert,
  Paper,
} from '@mui/material';
import {
  FactCheck as FilingIcon,
  PlayArrow as PlayIcon,
  Description as FormIcon,
  VerifiedUser as SignOffIcon,
  UploadFile as EvidenceIcon,
} from '@mui/icons-material';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  listTaxEngagements,
  listTaxReturnDrafts,
  runTaxReview,
  signOffTaxDraft,
  recordFilingEvidence,
} from '../../services/taxationApi';
import type { TaxEngagement, TaxReturnDraft } from '../../types/taxation';

export const TaxFilingPage: React.FC = () => {
  const { activeClient, activePeriod } = useWorkspace();
  const [engagement, setEngagement] = useState<TaxEngagement | null>(null);
  const [, setDrafts] = useState<TaxReturnDraft[]>([]);
  const [activeDraft, setActiveDraft] = useState<TaxReturnDraft | null>(null);

  const [loading, setLoading] = useState<boolean>(true);
  const [running, setRunning] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [signOffModalOpen, setSignOffModalOpen] = useState<boolean>(false);
  const [evidenceModalOpen, setEvidenceModalOpen] = useState<boolean>(false);
  const [caNotes, setCaNotes] = useState<string>('');
  const [cprNumber, setCprNumber] = useState<string>('');
  const [ackNumber, setAckNumber] = useState<string>('');
  const [evidenceNotes, setEvidenceNotes] = useState<string>('');
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

      const draftRes = await listTaxReturnDrafts(activeClient.id, activePeriod.id, eng.id);
      setDrafts(draftRes.items);
      setActiveDraft(draftRes.items[0] || null);
    } catch (err: any) {
      setError(err?.message || 'Failed to load return draft');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [activeClient, activePeriod]);

  const handleRunReview = async () => {
    if (!activeClient || !activePeriod || !engagement) return;
    try {
      setRunning(true);
      setError(null);
      await runTaxReview(activeClient.id, activePeriod.id, engagement.id);
      setMessage('Agent 4 Review & Filing Pack generated successfully.');
      await loadData();
    } catch (err: any) {
      setError(err?.message || 'Failed to execute tax review');
    } finally {
      setRunning(false);
    }
  };

  const handleSignOff = async () => {
    if (!activeClient || !activePeriod || !activeDraft) return;
    try {
      setActionLoading(true);
      setError(null);
      const updated = await signOffTaxDraft(activeClient.id, activePeriod.id, activeDraft.id, caNotes);
      setActiveDraft(updated);
      setSignOffModalOpen(false);
      setMessage(`Tax Return Draft v${updated.version} successfully approved by Chartered Accountant.`);
      await loadData();
    } catch (err: any) {
      setError(err?.message || 'Failed to sign off tax draft');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRecordEvidence = async () => {
    if (!activeClient || !activePeriod || !activeDraft) return;
    try {
      setActionLoading(true);
      setError(null);
      const updated = await recordFilingEvidence(activeClient.id, activePeriod.id, activeDraft.id, {
        cpr_number: cprNumber,
        acknowledgment_number: ackNumber,
        notes: evidenceNotes,
      });
      setActiveDraft(updated);
      setEvidenceModalOpen(false);
      setMessage('FBR Submission Evidence recorded successfully.');
      await loadData();
    } catch (err: any) {
      setError(err?.message || 'Failed to record filing evidence');
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

  // Common IRIS Form IT-1 line labels
  const irisLabels: Record<string, string> = {
    '7001': 'Total Turnover / Gross Receipts',
    '7002': 'Direct Cost of Sales / Purchases',
    '7003': 'Gross Profit / (Loss)',
    '7004': 'Management, Administrative & Selling Expenses',
    '7005': 'Net Accounting Profit / (Loss) Before Tax',
    '7006': 'Inadmissible Deductions u/s 21',
    '7007': 'Admissible Tax Depreciation u/s 22',
    '7008': 'Taxable Income (Subject to Normal Corporate Tax)',
    '7011': 'Normal Corporate Tax Payable @ 29%',
    '7012': 'Minimum Tax Payable u/s 113',
    '7013': 'Alternate Corporate Tax u/s 113C',
    '7014': 'Super Tax Payable u/s 4C',
    '7015': 'Tax Credits & Rebates',
    '7016': 'Advance Tax & Adjustable Withholding Deductions',
    '7017': 'Net Income Tax Payable / (Refundable)',
  };

  return (
    <Box sx={{ p: 3, maxWidth: 1400, mx: 'auto' }}>
      {/* Header */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Typography variant="h5" fontWeight="700" sx={{ color: '#0f766e' }}>
              Agent 4: Tax Review & Filing Pack
            </Typography>
            <Chip label="Taxation Workstream 4" color="success" size="small" variant="outlined" />
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            FBR IRIS Form IT-1 schedule mapping, cross-check validations, CA approval gate & filing submission records.
          </Typography>
        </Box>

        <Stack direction="row" spacing={2}>
          <Button
            variant="contained"
            sx={{ bgcolor: '#0f766e', '&:hover': { bgcolor: '#115e59' } }}
            startIcon={<PlayIcon />}
            onClick={handleRunReview}
            disabled={!engagement || running}
          >
            {running ? 'Compiling Filing Pack...' : 'Run Review Agent'}
          </Button>

          {activeDraft && activeDraft.status !== 'ca_approved' && activeDraft.status !== 'filed' && (
            <Button
              variant="contained"
              color="warning"
              startIcon={<SignOffIcon />}
              onClick={() => setSignOffModalOpen(true)}
            >
              CA Sign-Off & Approval
            </Button>
          )}

          {activeDraft && activeDraft.status === 'ca_approved' && (
            <Button
              variant="contained"
              color="success"
              startIcon={<EvidenceIcon />}
              onClick={() => setEvidenceModalOpen(true)}
            >
              Record FBR Filing Evidence
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
          <CircularProgress color="success" />
        </Box>
      ) : !activeDraft ? (
        <Card sx={{ p: 4, textAlign: 'center', border: '1px dashed #cbd5e1' }}>
          <FilingIcon sx={{ fontSize: 48, color: '#94a3b8', mb: 2 }} />
          <Typography variant="h6" fontWeight="600" gutterBottom>
            No Tax Return Draft Compiled Yet
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Click "Run Review Agent" to compile the FBR IRIS Form IT-1 filing pack and perform cross-check validations.
          </Typography>
          <Button variant="contained" sx={{ bgcolor: '#0f766e' }} onClick={handleRunReview} disabled={!engagement || running}>
            Execute Agent 4
          </Button>
        </Card>
      ) : (
        <Grid container spacing={3}>
          {/* Status & Validation Findings Card */}
          <Grid item xs={12}>
            <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2 }}>
              <CardContent sx={{ p: 2.5 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Stack direction="row" spacing={2} alignItems="center">
                    <Box
                      sx={{
                        p: 1.5,
                        borderRadius: 2,
                        bgcolor: activeDraft.status === 'ca_approved' ? '#dcfce7' : '#fef3c7',
                        color: activeDraft.status === 'ca_approved' ? '#15803d' : '#d97706',
                      }}
                    >
                      <SignOffIcon />
                    </Box>
                    <Box>
                      <Typography variant="subtitle1" fontWeight="700">
                        Return Draft v{activeDraft.version} Status: {activeDraft.status.replace(/_/g, ' ').toUpperCase()}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {activeDraft.signed_off_at
                          ? `Approved by CA on ${new Date(activeDraft.signed_off_at).toLocaleString()}`
                          : 'Pending Chartered Accountant formal review and sign-off.'}
                      </Typography>
                    </Box>
                  </Stack>

                  <Chip
                    label={activeDraft.review_report?.is_compliant ? 'All Checks Passed' : 'Validation Discrepancies Found'}
                    color={activeDraft.review_report?.is_compliant ? 'success' : 'warning'}
                    variant="filled"
                  />
                </Stack>

                {activeDraft.risk_findings && activeDraft.risk_findings.length > 0 && (
                  <Box sx={{ mt: 2 }}>
                    <Typography variant="caption" fontWeight="700" color="text.secondary">
                      RISK & VALIDATION FINDINGS:
                    </Typography>
                    <Stack spacing={1} sx={{ mt: 1 }}>
                      {activeDraft.risk_findings.map((f, idx) => (
                        <Alert key={idx} severity={f.severity === 'critical' || f.severity === 'high' ? 'error' : 'warning'} sx={{ py: 0.5 }}>
                          <Typography variant="body2" fontWeight="600">{f.title}</Typography>
                          <Typography variant="caption">{f.description}</Typography>
                        </Alert>
                      ))}
                    </Stack>
                  </Box>
                )}

                {activeDraft.filing_evidence?.cpr_number && (
                  <Box sx={{ mt: 2, p: 2, bgcolor: '#f0fdf4', borderRadius: 1.5, border: '1px solid #bbf7d0' }}>
                    <Typography variant="subtitle2" fontWeight="700" color="#166534">
                      FBR Filing Evidence Recorded:
                    </Typography>
                    <Typography variant="body2">
                      CPR #: {activeDraft.filing_evidence.cpr_number} • FBR Acknowledgment Slip #: {activeDraft.filing_evidence.acknowledgment_number || 'N/A'}
                    </Typography>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Form IT-1 Schedules */}
          <Grid item xs={12}>
            <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2 }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                  <FormIcon sx={{ color: '#0f766e' }} />
                  <Typography variant="h6" fontWeight="700">
                    FBR IRIS Form IT-1 Schedule Mappings (TY{engagement?.tax_year})
                  </Typography>
                </Stack>
                <Divider sx={{ mb: 2 }} />

                <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #e2e8f0' }}>
                  <Table size="small">
                    <TableHead sx={{ bgcolor: '#f8fafc' }}>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 700, width: 140 }}>IRIS Code</TableCell>
                        <TableCell sx={{ fontWeight: 700 }}>Description (Form IT-1 Field)</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700, width: 220 }}>Return Amount (PKR)</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {Object.entries(activeDraft.return_fields || {}).map(([code, val]) => (
                        <TableRow key={code} sx={{ bgcolor: code === '7017' ? '#ecfdf5' : 'inherit' }}>
                          <TableCell sx={{ fontWeight: 700, color: '#0f766e' }}>{code}</TableCell>
                          <TableCell sx={{ fontWeight: code === '7017' ? 700 : 500 }}>
                            {irisLabels[code] || `IRIS Return Field ${code}`}
                          </TableCell>
                          <TableCell align="right" sx={{ fontWeight: 700, color: code === '7017' ? '#047857' : 'inherit' }}>
                            {typeof val === 'number' ? Number(val).toLocaleString() : String(val)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* CA Sign-Off Dialog */}
      <Dialog open={signOffModalOpen} onClose={() => setSignOffModalOpen(false)}>
        <DialogTitle>Chartered Accountant Approval Sign-Off</DialogTitle>
        <DialogContent sx={{ minWidth: 440, pt: 2 }}>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            You are signing off on the Pakistan Tax Return Draft and Filing Pack. This confirms that all book-to-tax calculations, statutory rate benchmarks, and withholding tax tie-outs are approved.
          </Typography>
          <TextField
            label="CA Review Notes"
            multiline
            rows={3}
            fullWidth
            value={caNotes}
            onChange={(e) => setCaNotes(e.target.value)}
            placeholder="Enter verification notes and statutory references..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSignOffModalOpen(false)}>Cancel</Button>
          <Button variant="contained" color="warning" onClick={handleSignOff} disabled={actionLoading}>
            Approve & Sign Off
          </Button>
        </DialogActions>
      </Dialog>

      {/* Filing Evidence Dialog */}
      <Dialog open={evidenceModalOpen} onClose={() => setEvidenceModalOpen(false)}>
        <DialogTitle>Record FBR Filing Evidence</DialogTitle>
        <DialogContent sx={{ minWidth: 440, pt: 2 }}>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Computerized Payment Receipt (CPR) #"
              fullWidth
              value={cprNumber}
              onChange={(e) => setCprNumber(e.target.value)}
              placeholder="e.g. IT-20250630-0012-345678"
            />
            <TextField
              label="FBR IRIS Acknowledgment Slip #"
              fullWidth
              value={ackNumber}
              onChange={(e) => setAckNumber(e.target.value)}
              placeholder="e.g. ACK-2025-998877"
            />
            <TextField
              label="Filing Notes"
              multiline
              rows={2}
              fullWidth
              value={evidenceNotes}
              onChange={(e) => setEvidenceNotes(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEvidenceModalOpen(false)}>Cancel</Button>
          <Button variant="contained" color="success" onClick={handleRecordEvidence} disabled={actionLoading}>
            Save Evidence
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
