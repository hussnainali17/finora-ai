import { Alert, Chip, CircularProgress, Paper, Stack, Typography } from '@mui/material';
import { useEffect, useState } from 'react';
import { fetchReadiness } from '../../services/api';
import type { ReadinessResponse } from '../../types/health';

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'loaded'; data: ReadinessResponse };

export default function SystemStatus() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    fetchReadiness(controller.signal)
      .then((data) => setState({ kind: 'loaded', data }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setState({ kind: 'error', message: err instanceof Error ? err.message : 'Unknown error' });
      });
    return () => controller.abort();
  }, []);

  return (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h6" component="h2" gutterBottom>
        System status
      </Typography>
      {state.kind === 'loading' && <CircularProgress aria-label="Loading status" />}
      {state.kind === 'error' && (
        <Alert severity="error">Backend unreachable: {state.message}</Alert>
      )}
      {state.kind === 'loaded' && (
        <Stack spacing={1} mt={1}>
          <Alert severity={state.data.status === 'ok' ? 'success' : 'warning'}>
            Overall: {state.data.status}
          </Alert>
          {state.data.dependencies.map((d) => (
            <Stack key={d.name} direction="row" justifyContent="space-between">
              <Typography>{d.name}</Typography>
              <Chip
                size="small"
                color={d.ok ? 'success' : 'error'}
                label={d.ok ? `up (${d.latency_ms} ms)` : `down${d.detail ? `: ${d.detail}` : ''}`}
              />
            </Stack>
          ))}
        </Stack>
      )}
    </Paper>
  );
}
