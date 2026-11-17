import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { Refresh } from '@mui/icons-material';
import { listAuditEvents } from '../../services/auditApi';
import type { AuditEvent } from '../../types/audit';
import { useAuth } from '../auth/AuthContext';

export function AuditLogPage(): React.JSX.Element {
  const { principal } = useAuth();
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionFilter, setActionFilter] = useState('');

  const canRead = principal?.permissions?.includes('audit:read') ?? false;

  const fetchAudit = useCallback(async () => {
    if (!canRead) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listAuditEvents({
        limit: pageSize,
        offset: page * pageSize,
        action: actionFilter || undefined,
      });
      setEvents(data.items);
      setTotal(data.total);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load audit trail');
    } finally {
      setLoading(false);
    }
  }, [canRead, page, pageSize, actionFilter]);

  useEffect(() => {
    void fetchAudit();
  }, [fetchAudit]);

  if (!canRead) {
    return <Alert severity="error">You do not have permission to view the audit log.</Alert>;
  }

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h5" component="h1">
            Audit Trail & Activity History
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Immutable log of sensitive operations, CA decisions, file uploads, and model configurations.
          </Typography>
        </Box>
        <Button variant="outlined" startIcon={<Refresh />} onClick={() => void fetchAudit()} disabled={loading}>
          Refresh
        </Button>
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Paper sx={{ mb: 2, p: 2 }}>
        <Stack direction="row" spacing={2} alignItems="center">
          <TextField
            size="small"
            label="Filter by Action"
            value={actionFilter}
            onChange={(e) => {
              setActionFilter(e.target.value);
              setPage(0);
            }}
            placeholder="e.g. document.uploaded, adjustment.approved"
            sx={{ minWidth: 320 }}
          />
        </Stack>
      </Paper>

      {loading && events.length === 0 ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}><CircularProgress /></Box>
      ) : events.length === 0 ? (
        <Alert severity="info">No audit events found.</Alert>
      ) : (
        <Paper>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Timestamp</TableCell>
                <TableCell>Action</TableCell>
                <TableCell>Target Type</TableCell>
                <TableCell>Actor ID</TableCell>
                <TableCell>IP Address</TableCell>
                <TableCell>Details / Metadata</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {events.map((evt) => (
                <TableRow key={evt.id} hover>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                    <Typography variant="caption">
                      {new Date(evt.occurred_at).toLocaleString()}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip size="small" label={evt.action} color="primary" variant="outlined" />
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">{evt.target_type}</Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption" color="text.secondary">
                      {evt.actor_user_id ? evt.actor_user_id.slice(0, 8) + '...' : 'System'}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption">{evt.ip_address ?? '—'}</Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                      {JSON.stringify(evt.metadata)}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={total}
            page={page}
            onPageChange={(_, newPage) => setPage(newPage)}
            rowsPerPage={pageSize}
            onRowsPerPageChange={(e) => {
              setPageSize(parseInt(e.target.value, 10));
              setPage(0);
            }}
            rowsPerPageOptions={[10, 25, 50, 100]}
          />
        </Paper>
      )}
    </Box>
  );
}
