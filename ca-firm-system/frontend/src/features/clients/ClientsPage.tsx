import {
  Alert,
  Avatar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  InputAdornment,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import {
  Add as AddIcon,
  Business as BusinessIcon,
  Search as SearchIcon,
  ArrowForward as ArrowForwardIcon,
} from '@mui/icons-material';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { Can } from '../auth/Can';
import { createClient, listClients } from '../../services/clientsApi';
import { ApiError } from '../../services/http';
import type { Client, Page } from '../../types/clients';

const PAGE_SIZE = 12;
const CURRENCIES = ['PKR', 'USD', 'EUR', 'GBP', 'AED', 'SAR'];

const CURRENCY_FLAGS: Record<string, string> = {
  PKR: '🇵🇰', USD: '🇺🇸', EUR: '🇪🇺', GBP: '🇬🇧', AED: '🇦🇪', SAR: '🇸🇦',
};

const CLIENT_COLORS = [
  '#4f46e5', '#059669', '#0891b2', '#7c3aed', '#dc2626', '#d97706',
];

function getClientColor(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) hash = id.charCodeAt(i) + ((hash << 5) - hash);
  return CLIENT_COLORS[Math.abs(hash) % CLIENT_COLORS.length];
}

function NewClientDialog({
  open, onClose, onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [currency, setCurrency] = useState('PKR');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createClient({ code, name, base_currency: currency });
      setCode('');
      setName('');
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create the client');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs" component="form" onSubmit={submit}>
      <DialogTitle sx={{ pb: 1 }}>
        <Stack direction="row" alignItems="center" gap={1.5}>
          <Avatar sx={{ bgcolor: '#4f46e5', width: 36, height: 36 }}>
            <BusinessIcon sx={{ fontSize: 18 }} />
          </Avatar>
          <Box>
            <Typography variant="h6" sx={{ lineHeight: 1.2 }}>Add New Client</Typography>
            <Typography variant="caption" color="text.secondary">Set up a new client profile</Typography>
          </Box>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2.5} sx={{ mt: 1 }}>
          {error && <Alert severity="error" sx={{ borderRadius: 2 }}>{error}</Alert>}
          <TextField
            label="Client Code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
            helperText="Unique short code (letters, digits, . _ -)"
            variant="outlined"
          />
          <TextField
            label="Company / Client Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            variant="outlined"
          />
          <TextField
            select
            label="Base Currency"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            variant="outlined"
          >
            {CURRENCIES.map((c) => (
              <MenuItem key={c} value={c}>
                {CURRENCY_FLAGS[c] ?? ''} {c}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 3 }}>
        <Button onClick={onClose} sx={{ color: '#64748b' }}>Cancel</Button>
        <Button
          type="submit"
          variant="contained"
          disabled={busy || !code || !name}
          startIcon={busy ? <CircularProgress size={16} /> : <AddIcon />}
          sx={{
            background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
            px: 3,
            '&:hover': { background: 'linear-gradient(135deg, #3730a3 0%, #6d28d9 100%)' },
          }}
        >
          {busy ? 'Creating…' : 'Create Client'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function ClientCard({ client }: { client: Client }) {
  const navigate = useNavigate();
  const color = getClientColor(client.id);
  const initials = client.name.split(' ').slice(0, 2).map((w) => w[0]).join('').toUpperCase();

  return (
    <Box
      onClick={() => navigate(`/clients/${client.id}`)}
      sx={{
        bgcolor: '#fff',
        border: '1px solid #e2e8f0',
        borderRadius: 3,
        borderTop: `4px solid ${color}`,
        p: 2.5,
        minHeight: 230,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        position: 'relative',
        overflow: 'hidden',
        '&:hover': {
          transform: 'translateY(-4px)',
          boxShadow: '0 12px 32px rgba(79,70,229,0.12)',
          borderColor: color,
        },
      }}
    >
      <Stack spacing={2} sx={{ flex: 1 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Box
            sx={{
              width: 42,
              height: 42,
              borderRadius: '10px',
              bgcolor: `${color}18`,
              color,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
              fontSize: '1rem',
            }}
          >
            {initials || <BusinessIcon fontSize="small" />}
          </Box>
          <Chip
            size="small"
            label={client.status === 'active' ? 'Active' : client.status}
            sx={{
              bgcolor: client.status === 'active' ? '#dcfce7' : '#f1f5f9',
              color: client.status === 'active' ? '#15803d' : '#475569',
              fontWeight: 600,
              fontSize: '0.72rem',
            }}
          />
        </Stack>

        <Box>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#0f172a', lineHeight: 1.3 }}>
            {client.name}
          </Typography>
          <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 500 }}>
            {client.code}
          </Typography>
        </Box>

        <Typography variant="body2" color="text.secondary" sx={{ minHeight: 38, mt: 0.5 }}>
          {client.legal_name || `Base currency: ${CURRENCY_FLAGS[client.base_currency] ?? ''} ${client.base_currency} • FY ends month ${client.fiscal_year_end_month}`}
        </Typography>

        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mt: 'auto', pt: 1.5 }}>
          <Chip
            size="small"
            label={`${CURRENCY_FLAGS[client.base_currency] ?? ''} ${client.base_currency}`}
            sx={{ bgcolor: '#f8fafc', color: '#475569', fontWeight: 600, fontSize: '0.75rem' }}
          />
          <Stack direction="row" alignItems="center" spacing={0.5} sx={{ color, fontSize: '0.8rem', fontWeight: 700 }}>
            <Typography variant="button" sx={{ fontSize: '0.8rem', fontWeight: 700, color, textTransform: 'none' }}>
              View details
            </Typography>
            <ArrowForwardIcon sx={{ fontSize: 16 }} />
          </Stack>
        </Stack>
      </Stack>
    </Box>
  );
}

export default function ClientsPage() {
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState('');
  const [q, setQ] = useState('');
  const [data, setData] = useState<Page<Client> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    setError(null);
    listClients({ limit: PAGE_SIZE, offset: page * PAGE_SIZE, q: q || undefined })
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load clients'));
  }, [page, q]);

  useEffect(load, [load]);
  useEffect(() => {
    const t = setTimeout(() => { setPage(0); setQ(search.trim()); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  return (
    <Stack spacing={3}>
      {/* Header */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={2}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 800, color: '#0f172a' }}>
            Clients
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {data ? `${data.total} client${data.total !== 1 ? 's' : ''} in your firm` : 'Manage your client portfolio'}
          </Typography>
        </Box>
        <Can permission="client:create">
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setCreating(true)}
            sx={{
              background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
              px: 3, py: 1.2, borderRadius: 2.5, fontWeight: 600,
              boxShadow: '0 4px 14px rgba(79,70,229,0.3)',
              '&:hover': {
                background: 'linear-gradient(135deg, #3730a3 0%, #6d28d9 100%)',
                transform: 'translateY(-1px)',
                boxShadow: '0 6px 20px rgba(79,70,229,0.4)',
              },
              transition: 'all 0.2s ease',
            }}
          >
            New Client
          </Button>
        </Can>
      </Stack>

      {/* Search */}
      <TextField
        size="small"
        placeholder="Search clients by name or code…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon sx={{ color: '#94a3b8', fontSize: 20 }} />
            </InputAdornment>
          ),
        }}
        sx={{
          maxWidth: 400,
          '& .MuiOutlinedInput-root': { borderRadius: 2.5, bgcolor: '#fff' },
        }}
      />

      {/* States */}
      {error && <Alert severity="error" sx={{ borderRadius: 2 }}>{error}</Alert>}
      {!data && !error && (
        <Stack alignItems="center" py={8}>
          <CircularProgress sx={{ color: '#4f46e5' }} />
          <Typography variant="body2" color="text.secondary" mt={2}>Loading clients…</Typography>
        </Stack>
      )}

      {data && data.items.length === 0 && (
        <Stack alignItems="center" py={8} spacing={2}>
          <Avatar sx={{ bgcolor: '#f1f5f9', width: 72, height: 72 }}>
            <BusinessIcon sx={{ fontSize: 36, color: '#94a3b8' }} />
          </Avatar>
          <Box textAlign="center">
            <Typography variant="h6" sx={{ fontWeight: 700, color: '#0f172a' }}>
              {q ? 'No clients found' : 'No clients yet'}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {q ? `No results for "${q}". Try a different search.` : 'Add your first client to get started.'}
            </Typography>
          </Box>
          {!q && (
            <Can permission="client:create">
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={() => setCreating(true)}
                sx={{ background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)' }}
              >
                Add First Client
              </Button>
            </Can>
          )}
        </Stack>
      )}

      {/* Card Grid */}
      {data && data.items.length > 0 && (
        <>
          <Grid container spacing={2.5}>
            {data.items.map((c) => (
              <Grid key={c.id} item xs={12} sm={6} md={4} lg={3}>
                <ClientCard client={c} />
              </Grid>
            ))}
          </Grid>

          {/* Pagination */}
          {totalPages > 1 && (
            <Stack direction="row" justifyContent="center" alignItems="center" gap={1} pt={1}>
              <Button
                size="small"
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
                sx={{ borderRadius: 2 }}
              >
                Previous
              </Button>
              <Typography variant="body2" sx={{ color: '#64748b', px: 2 }}>
                Page {page + 1} of {totalPages}
              </Typography>
              <Button
                size="small"
                disabled={page >= totalPages - 1}
                onClick={() => setPage((p) => p + 1)}
                sx={{ borderRadius: 2 }}
              >
                Next
              </Button>
            </Stack>
          )}
        </>
      )}

      <NewClientDialog open={creating} onClose={() => setCreating(false)} onCreated={load} />
    </Stack>
  );
}
