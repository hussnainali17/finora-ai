import {
  Alert,
  Breadcrumbs,
  Button,
  Chip,
  CircularProgress,
  Link,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { Can } from '../auth/Can';
import { createPeriod, getClient, listPeriods, setPeriodState } from '../../services/clientsApi';
import { ApiError } from '../../services/http';
import type { Client, Period } from '../../types/clients';
import { formatDate } from './format';

export default function ClientDetailPage() {
  const { clientId = '' } = useParams();
  const [client, setClient] = useState<Client | null>(null);
  const [periods, setPeriods] = useState<Period[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [label, setLabel] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');

  const load = useCallback(() => {
    Promise.all([getClient(clientId), listPeriods(clientId)])
      .then(([c, p]) => {
        setClient(c);
        setPeriods(p);
      })
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
    try {
      await createPeriod(clientId, { label, start_date: start, end_date: end });
      setLabel('');
      setStart('');
      setEnd('');
      load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Could not create the period');
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

  if (error) return <Alert severity="error">{error}</Alert>;
  if (!client || !periods) return <CircularProgress aria-label="Loading client" />;

  return (
    <Stack spacing={3}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/clients" underline="hover">
          Clients
        </Link>
        <Typography color="text.primary">{client.name}</Typography>
      </Breadcrumbs>
      <Paper sx={{ p: 3 }}>
        <Typography variant="h5" component="h2">
          {client.name}
        </Typography>
        <Typography color="text.secondary">
          {client.code} · {client.base_currency} · fiscal year ends month{' '}
          {client.fiscal_year_end_month}
        </Typography>
      </Paper>

      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" component="h3" gutterBottom>
          Accounting periods
        </Typography>
        {periods.length === 0 ? (
          <Alert severity="info">No accounting periods yet.</Alert>
        ) : (
          <Table size="small" aria-label="Accounting periods">
            <TableHead>
              <TableRow>
                <TableCell>Period</TableCell>
                <TableCell>From</TableCell>
                <TableCell>To</TableCell>
                <TableCell>Status</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {periods.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <Button
                      component={RouterLink}
                      to={`/clients/${clientId}/periods/${p.id}`}
                      size="small"
                    >
                      {p.label}
                    </Button>
                  </TableCell>
                  <TableCell>{formatDate(p.start_date)}</TableCell>
                  <TableCell>{formatDate(p.end_date)}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={p.status}
                      color={p.status === 'open' ? 'success' : 'default'}
                    />
                  </TableCell>
                  <TableCell align="right">
                    <Can permission="period:close">
                      <Button size="small" onClick={() => void toggle(p)}>
                        {p.status === 'open' ? 'Close' : 'Reopen'}
                      </Button>
                    </Can>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        <Can permission="period:create">
          <Stack
            component="form"
            onSubmit={add}
            direction={{ xs: 'column', sm: 'row' }}
            spacing={2}
            mt={3}
            alignItems={{ sm: 'flex-start' }}
          >
            <TextField
              size="small"
              label="Label (e.g. FY2025)"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              required
            />
            <TextField
              size="small"
              type="date"
              label="Start"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              required
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <TextField
              size="small"
              type="date"
              label="End"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              required
              slotProps={{ inputLabel: { shrink: true } }}
            />
            <Button type="submit" variant="contained" disabled={client.status !== 'active'}>
              Add period
            </Button>
          </Stack>
          {formError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {formError}
            </Alert>
          )}
        </Can>
      </Paper>
    </Stack>
  );
}
