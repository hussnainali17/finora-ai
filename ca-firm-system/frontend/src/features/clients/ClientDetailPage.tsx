import {
  Alert,
  Avatar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Grid,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import {
  Add as AddIcon,
  Business as BusinessIcon,
  CalendarMonth as CalendarIcon,
  Lock as LockIcon,
  LockOpen as LockOpenIcon,
  ArrowForward as ArrowForwardIcon,
  Folder as FolderIcon,
} from '@mui/icons-material';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Can } from '../auth/Can';
import { createPeriod, getClient, listPeriods, setPeriodState } from '../../services/clientsApi';
import { ApiError } from '../../services/http';
import type { Client, Period } from '../../types/clients';
import { formatDate } from './format';

export default function ClientDetailPage() {
  const { clientId = '' } = useParams();
  const navigate = useNavigate();
  const [client, setClient] = useState<Client | null>(null);
  const [periods, setPeriods] = useState<Period[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [label, setLabel] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [addingPeriod, setAddingPeriod] = useState(false);

  const load = useCallback(() => {
    Promise.all([getClient(clientId), listPeriods(clientId)])
      .then(([c, p]) => { setClient(c); setPeriods(p); })
      .catch((e: unknown) =>
        setError(
          e instanceof ApiError && e.status === 404
            ? 'Client not found.'
            : 'Failed to load client.',
        ),
      );
  }, [clientId]);
  useEffect(load, [load]);

  async function add(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setAddingPeriod(true);
    try {
      await createPeriod(clientId, { label, start_date: start, end_date: end });
      setLabel('');
      setStart('');
      setEnd('');
      load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Could not create the period');
    } finally {
      setAddingPeriod(false);
    }
  }

  async function toggle(p: Period) {
    try {
      await setPeriodState(clientId, p.id, p.status === 'open' ? 'close' : 'reopen');
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed');
    }
  }

  if (error) return <Alert severity="error" sx={{ borderRadius: 2 }}>{error}</Alert>;
  if (!client || !periods) {
    return (
      <Stack alignItems="center" py={8} spacing={2}>
        <CircularProgress sx={{ color: '#4f46e5' }} />
        <Typography variant="body2" color="text.secondary">Loading client details…</Typography>
      </Stack>
    );
  }

  const initials = client.name.split(' ').slice(0, 2).map((w) => w[0]).join('').toUpperCase();
  const openPeriods = periods.filter((p) => p.status === 'open').length;

  return (
    <Stack spacing={3}>
      {/* Client Header Card */}
      <Paper
        elevation={0}
        sx={{
          p: 3,
          border: '1px solid #e2e8f0',
          borderRadius: 3,
          background: 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 60%, #312e81 100%)',
          color: '#fff',
          position: 'relative',
          overflow: 'hidden',
          '&::after': {
            content: '""',
            position: 'absolute',
            top: -60, right: -60,
            width: 200, height: 200,
            borderRadius: '50%',
            background: 'rgba(255,255,255,0.04)',
          },
        }}
      >
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3} alignItems={{ sm: 'center' }}>
          <Avatar
            sx={{
              bgcolor: 'rgba(255,255,255,0.15)',
              width: 72, height: 72,
              fontSize: '1.6rem', fontWeight: 800,
              border: '2px solid rgba(255,255,255,0.2)',
            }}
          >
            {initials || <BusinessIcon sx={{ fontSize: 32 }} />}
          </Avatar>

          <Box flex={1}>
            <Stack direction="row" alignItems="center" gap={1.5} flexWrap="wrap">
              <Typography variant="h5" sx={{ fontWeight: 800 }}>
                {client.name}
              </Typography>
              <Chip
                size="small"
                label={client.status === 'active' ? '● Active' : client.status}
                sx={{
                  bgcolor: client.status === 'active' ? '#dcfce7' : '#fef3c7',
                  color: client.status === 'active' ? '#15803d' : '#92400e',
                  fontWeight: 700, fontSize: '0.72rem',
                }}
              />
            </Stack>
            <Stack direction="row" gap={2} mt={0.5} flexWrap="wrap">
              <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.6)' }}>
                Code: <strong style={{ color: '#c7d2fe' }}>{client.code}</strong>
              </Typography>
              <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.6)' }}>
                Currency: <strong style={{ color: '#c7d2fe' }}>{client.base_currency}</strong>
              </Typography>
              <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.6)' }}>
                FY ends month: <strong style={{ color: '#c7d2fe' }}>{client.fiscal_year_end_month}</strong>
              </Typography>
            </Stack>
          </Box>

          {/* Quick stats */}
          <Stack direction="row" gap={3}>
            <Box textAlign="center">
              <Typography variant="h4" sx={{ fontWeight: 800, color: '#a5f3fc' }}>{periods.length}</Typography>
              <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.5)' }}>Periods</Typography>
            </Box>
            <Box textAlign="center">
              <Typography variant="h4" sx={{ fontWeight: 800, color: '#86efac' }}>{openPeriods}</Typography>
              <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.5)' }}>Open</Typography>
            </Box>
          </Stack>
        </Stack>
      </Paper>

      {/* Accounting Periods */}
      <Box>
        <Stack direction="row" alignItems="center" justifyContent="space-between" mb={2.5}>
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 700, color: '#0f172a' }}>
              Accounting Periods
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Click a period to view documents and run the accounting workflow
            </Typography>
          </Box>
        </Stack>

        {periods.length === 0 ? (
          <Paper elevation={0} sx={{ p: 5, border: '1px dashed #cbd5e1', borderRadius: 3, textAlign: 'center' }}>
            <CalendarIcon sx={{ fontSize: 48, color: '#cbd5e1', mb: 1 }} />
            <Typography variant="subtitle1" sx={{ fontWeight: 600, color: '#64748b' }}>
              No accounting periods yet
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Add a period below to start processing financial data.
            </Typography>
          </Paper>
        ) : (
          <Grid container spacing={2}>
            {periods.map((p) => (
              <Grid key={p.id} item xs={12} sm={6} md={4}>
                <Box
                  sx={{
                    bgcolor: '#fff',
                    border: '1px solid #e2e8f0',
                    borderRadius: 3,
                    p: 2.5,
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    position: 'relative',
                    overflow: 'hidden',
                    '&:hover': {
                      transform: 'translateY(-3px)',
                      boxShadow: '0 8px 24px rgba(79,70,229,0.12)',
                      borderColor: '#4f46e5',
                    },
                    '&::before': {
                      content: '""',
                      position: 'absolute',
                      top: 0, left: 0, right: 0,
                      height: 3,
                      background: p.status === 'open'
                        ? 'linear-gradient(90deg, #059669, #34d399)'
                        : 'linear-gradient(90deg, #94a3b8, #cbd5e1)',
                      borderRadius: '12px 12px 0 0',
                    },
                  }}
                  onClick={() => navigate(`/clients/${clientId}/periods/${p.id}`)}
                >
                  <Stack spacing={1.5}>
                    <Stack direction="row" alignItems="center" justifyContent="space-between">
                      <Avatar
                        sx={{
                          bgcolor: p.status === 'open' ? '#dcfce7' : '#f1f5f9',
                          color: p.status === 'open' ? '#15803d' : '#94a3b8',
                          width: 40, height: 40,
                        }}
                      >
                        <CalendarIcon sx={{ fontSize: 20 }} />
                      </Avatar>
                      <Chip
                        size="small"
                        icon={p.status === 'open' ? <LockOpenIcon sx={{ fontSize: 12 }} /> : <LockIcon sx={{ fontSize: 12 }} />}
                        label={p.status === 'open' ? 'Open' : 'Closed'}
                        sx={{
                          bgcolor: p.status === 'open' ? '#dcfce7' : '#f1f5f9',
                          color: p.status === 'open' ? '#15803d' : '#64748b',
                          fontWeight: 600, fontSize: '0.72rem',
                        }}
                      />
                    </Stack>

                    <Box>
                      <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#0f172a' }}>
                        {p.label}
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                        {formatDate(p.start_date)} → {formatDate(p.end_date)}
                      </Typography>
                    </Box>

                    <Stack direction="row" alignItems="center" justifyContent="space-between">
                      <Box
                        sx={{
                          display: 'flex', alignItems: 'center', gap: 0.5,
                          color: '#4f46e5', fontSize: '0.78rem', fontWeight: 600,
                        }}
                      >
                        <FolderIcon sx={{ fontSize: 14 }} /> Open period
                        <ArrowForwardIcon sx={{ fontSize: 14 }} />
                      </Box>
                      <Can permission="period:close">
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={(e) => { e.stopPropagation(); void toggle(p); }}
                          sx={{
                            borderRadius: 1.5, fontSize: '0.72rem', py: 0.3, px: 1.2,
                            borderColor: p.status === 'open' ? '#fca5a5' : '#86efac',
                            color: p.status === 'open' ? '#dc2626' : '#15803d',
                            '&:hover': {
                              bgcolor: p.status === 'open' ? '#fef2f2' : '#f0fdf4',
                              borderColor: p.status === 'open' ? '#dc2626' : '#059669',
                            },
                          }}
                        >
                          {p.status === 'open' ? 'Close' : 'Reopen'}
                        </Button>
                      </Can>
                    </Stack>
                  </Stack>
                </Box>
              </Grid>
            ))}
          </Grid>
        )}
      </Box>

      {/* Add Period Form */}
      <Can permission="period:create">
        <Paper elevation={0} sx={{ border: '1px solid #e2e8f0', borderRadius: 3, overflow: 'hidden' }}>
          <Box sx={{ px: 3, py: 2, bgcolor: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
            <Stack direction="row" alignItems="center" gap={1}>
              <AddIcon sx={{ color: '#4f46e5', fontSize: 20 }} />
              <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#0f172a' }}>
                Add Accounting Period
              </Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Define a new accounting period for this client (e.g., FY2026)
            </Typography>
          </Box>
          <Box sx={{ p: 3 }}>
            {formError && (
              <Alert severity="error" sx={{ mb: 2.5, borderRadius: 2 }}>{formError}</Alert>
            )}
            <Stack
              component="form"
              onSubmit={add}
              direction={{ xs: 'column', sm: 'row' }}
              spacing={2}
              alignItems={{ sm: 'flex-end' }}
            >
              <TextField
                size="small"
                label="Period Label"
                placeholder="e.g. FY2026"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                required
                sx={{ minWidth: 150 }}
              />
              <TextField
                size="small"
                type="date"
                label="Start Date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                required
                slotProps={{ inputLabel: { shrink: true } }}
              />
              <TextField
                size="small"
                type="date"
                label="End Date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                required
                slotProps={{ inputLabel: { shrink: true } }}
              />
              <Button
                type="submit"
                variant="contained"
                disabled={client.status !== 'active' || addingPeriod || !label || !start || !end}
                startIcon={addingPeriod ? <CircularProgress size={16} /> : <AddIcon />}
                sx={{
                  background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
                  px: 3, whiteSpace: 'nowrap',
                  '&:hover': { background: 'linear-gradient(135deg, #3730a3 0%, #6d28d9 100%)' },
                }}
              >
                {addingPeriod ? 'Adding…' : 'Add Period'}
              </Button>
            </Stack>
            {client.status !== 'active' && (
              <Typography variant="caption" color="error" sx={{ mt: 1, display: 'block' }}>
                Client must be active to add periods.
              </Typography>
            )}
          </Box>
        </Paper>
      </Can>
    </Stack>
  );
}
