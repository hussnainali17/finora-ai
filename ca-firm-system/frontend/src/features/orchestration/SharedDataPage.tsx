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
  Share as ShareIcon,
  CheckCircle as CheckIcon,
  Visibility as ViewIcon,
} from '@mui/icons-material';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { listSharedOutputs } from '../../services/sharedDataApi';
import type { ApprovedModuleOutput } from '../../types/sharedData';

export const SharedDataPage: React.FC = () => {
  const { activeClient, activePeriod } = useWorkspace();
  const [outputs, setOutputs] = useState<ApprovedModuleOutput[]>([]);
  const [selectedOutput, setSelectedOutput] = useState<ApprovedModuleOutput | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    if (!activeClient || !activePeriod) return;
    try {
      setLoading(true);
      setError(null);
      const res = await listSharedOutputs(activeClient.id, activePeriod.id);
      setOutputs(res.items);
    } catch (err: any) {
      setError(err?.message || 'Failed to load shared outputs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [activeClient, activePeriod]);

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
            <Typography variant="h5" fontWeight="700" sx={{ color: '#1e293b' }}>
              Central Shared Data & Documents Layer
            </Typography>
            <Chip label="Cross-Module Storage" color="primary" size="small" variant="outlined" />
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Persistent versioned repository for approved accounting & taxation outputs, validation tie-outs, and dependency tracking.
          </Typography>
        </Box>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 5 }}>
          <CircularProgress />
        </Box>
      ) : outputs.length === 0 ? (
        <Card sx={{ p: 4, textAlign: 'center', border: '1px dashed #cbd5e1' }}>
          <ShareIcon sx={{ fontSize: 48, color: '#94a3b8', mb: 2 }} />
          <Typography variant="h6" fontWeight="600" gutterBottom>
            No Approved Outputs Published Yet
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Outputs will automatically publish here when the CA signs off on Financial Statements in Accounting or Tax Returns in Taxation.
          </Typography>
        </Card>
      ) : (
        <Card sx={{ border: '1px solid #e2e8f0', borderRadius: 2 }}>
          <CardContent sx={{ p: 3 }}>
            <Typography variant="h6" fontWeight="700" sx={{ mb: 2 }}>
              Published Module Outputs & Version Lineage
            </Typography>
            <TableContainer component={Paper} elevation={0} sx={{ border: '1px solid #e2e8f0' }}>
              <Table size="small">
                <TableHead sx={{ bgcolor: '#f8fafc' }}>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 700 }}>Module</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Version</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Status</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Validation</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>Signed Off At</TableCell>
                    <TableCell sx={{ fontWeight: 700 }}>CA Review Notes</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 700 }}>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {outputs.map((out) => (
                    <TableRow key={out.id}>
                      <TableCell>
                        <Chip
                          label={out.module.toUpperCase()}
                          size="small"
                          color={out.module === 'accounting' ? 'primary' : 'success'}
                          variant="filled"
                        />
                      </TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>v{out.version}</TableCell>
                      <TableCell>
                        <Chip
                          label={out.status}
                          size="small"
                          color={out.status === 'approved' ? 'success' : 'default'}
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell>
                        {out.validation_results?.is_valid ? (
                          <Chip icon={<CheckIcon />} label="Valid" size="small" color="success" />
                        ) : (
                          <Chip label="Check Warnings" size="small" color="warning" />
                        )}
                      </TableCell>
                      <TableCell>{out.signed_off_at ? new Date(out.signed_off_at).toLocaleString() : 'N/A'}</TableCell>
                      <TableCell sx={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {out.ca_notes || 'No notes recorded'}
                      </TableCell>
                      <TableCell align="right">
                        <Button
                          size="small"
                          startIcon={<ViewIcon />}
                          onClick={() => setSelectedOutput(out)}
                        >
                          Inspect
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}

      {/* Inspect Dialog */}
      <Dialog open={Boolean(selectedOutput)} onClose={() => setSelectedOutput(null)} maxWidth="md" fullWidth>
        <DialogTitle>
          Inspect Shared Output: {selectedOutput?.module.toUpperCase()} v{selectedOutput?.version}
        </DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          {selectedOutput && (
            <Stack spacing={2}>
              <Box sx={{ p: 2, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                <Typography variant="caption" fontWeight="700" color="text.secondary">SUMMARY DATA</Typography>
                <pre style={{ margin: 0, fontSize: '0.8rem', overflowX: 'auto' }}>
                  {JSON.stringify(selectedOutput.summary, null, 2)}
                </pre>
              </Box>

              <Box sx={{ p: 2, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                <Typography variant="caption" fontWeight="700" color="text.secondary">SOURCE VERSION REFERENCES</Typography>
                <pre style={{ margin: 0, fontSize: '0.8rem', overflowX: 'auto' }}>
                  {JSON.stringify(selectedOutput.source_version_refs, null, 2)}
                </pre>
              </Box>

              <Box sx={{ p: 2, bgcolor: '#f8fafc', borderRadius: 1.5, border: '1px solid #e2e8f0' }}>
                <Typography variant="caption" fontWeight="700" color="text.secondary">FULL PAYLOAD (EXCERPT)</Typography>
                <pre style={{ margin: 0, fontSize: '0.75rem', maxHeight: 250, overflow: 'auto' }}>
                  {JSON.stringify(selectedOutput.data, null, 2)}
                </pre>
              </Box>
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectedOutput(null)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
