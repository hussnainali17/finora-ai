import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
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
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { Can } from '../auth/Can';
import { createClient, listClients } from '../../services/clientsApi';
import { ApiError } from '../../services/http';
import type { Client, Page } from '../../types/clients';

const PAGE_SIZE = 10;
const CURRENCIES = ['PKR', 'USD', 'EUR', 'GBP', 'AED', 'SAR'];

function NewClientDialog({
  open,
  onClose,
  onCreated,
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
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="xs"
      component="form"
      onSubmit={submit}
    >
      <DialogTitle>New client</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            label="Client code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
            helperText="Letters, digits, . _ - (unique in your firm)"
          />
          <TextField
            label="Client name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <TextField
            select
            label="Base currency"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          >
            {CURRENCIES.map((c) => (
              <MenuItem key={c} value={c}>
                {c}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button type="submit" variant="contained" disabled={busy || !code || !name}>
          Create client
        </Button>
      </DialogActions>
    </Dialog>
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
    const t = setTimeout(() => {
      setPage(0);
      setQ(search.trim());
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  return (
    <Paper sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2} gap={2}>
        <Typography variant="h5" component="h2">
          Clients
        </Typography>
        <Can permission="client:create">
          <Button variant="contained" onClick={() => setCreating(true)}>
            New client
          </Button>
        </Can>
      </Stack>
      <TextField
        size="small"
        label="Search clients"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        sx={{ mb: 2, minWidth: 260 }}
      />

      {error && <Alert severity="error">{error}</Alert>}
      {!data && !error && <CircularProgress aria-label="Loading clients" />}
      {data && data.items.length === 0 && (
        <Alert severity="info">
          {q
            ? 'No clients match your search.'
            : 'No clients yet. Clients you are assigned to appear here.'}
        </Alert>
      )}
      {data && data.items.length > 0 && (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" aria-label="Clients">
            <TableHead>
              <TableRow>
                <TableCell>Code</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Currency</TableCell>
                <TableCell>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.items.map((c) => (
                <TableRow key={c.id} hover>
                  <TableCell>{c.code}</TableCell>
                  <TableCell>
                    <Button component={RouterLink} to={`/clients/${c.id}`} size="small">
                      {c.name}
                    </Button>
                  </TableCell>
                  <TableCell>{c.base_currency}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={c.status}
                      color={c.status === 'active' ? 'success' : 'default'}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={data.total}
            page={page}
            onPageChange={(_, p) => setPage(p)}
            rowsPerPage={PAGE_SIZE}
            rowsPerPageOptions={[PAGE_SIZE]}
          />
        </Box>
      )}
      <NewClientDialog open={creating} onClose={() => setCreating(false)} onCreated={load} />
    </Paper>
  );
}
