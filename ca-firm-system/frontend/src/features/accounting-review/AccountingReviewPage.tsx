import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  Typography,
} from '@mui/material';
import { PlayArrow, Refresh } from '@mui/icons-material';
import { useNavigate, useParams } from 'react-router-dom';
import { triggerReview, listReviewRuns } from '../../services/accountingReviewApi';
import type { ReviewRun, ModuleSummary } from '../../types/accounting_review';
import { MODULE_LABELS } from '../../types/accounting_review';
import { useAuth } from '../auth/AuthContext';

const STATUS_COLOR: Record<string, 'default' | 'info' | 'success' | 'warning' | 'error'> = {
  pending: 'info',
  running: 'warning',
  completed: 'success',
  failed: 'error',
};

export function AccountingReviewPage(): React.JSX.Element {
  const { clientId, periodId } = useParams<{ clientId: string; periodId: string }>();
  const navigate = useNavigate();
  const { principal } = useAuth();

  const [runs, setRuns] = useState<ReviewRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canManage = principal?.permissions?.includes('review:manage') ?? false;
  const canRead = principal?.permissions?.includes('review:read') ?? false;

  const fetchRuns = useCallback(async () => {
    if (!clientId || !periodId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listReviewRuns(clientId, periodId);
      setRuns(data.items);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load review runs');
    } finally {
      setLoading(false);
    }
  }, [clientId, periodId]);

  useEffect(() => {
    if (canRead) void fetchRuns();
  }, [canRead, fetchRuns]);

  // Poll for status updates while any run is pending/running
  useEffect(() => {
    const hasActive = runs.some((r) => r.status === 'pending' || r.status === 'running');
    if (!hasActive) return;
    const interval = setInterval(() => void fetchRuns(), 5000);
    return () => clearInterval(interval);
  }, [runs, fetchRuns]);

  const handleTrigger = async () => {
    if (!clientId || !periodId) return;
    setTriggering(true);
    setError(null);
    try {
      await triggerReview(clientId, periodId, {});
      await fetchRuns();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to trigger review');
    } finally {
      setTriggering(false);
    }
  };

  if (!canRead) {
    return (
      <Alert severity="error">
        You do not have permission to view accounting reviews.
      </Alert>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3, gap: 2 }}>
        <Typography variant="h5" component="h1" sx={{ flexGrow: 1 }}>
          Accounting Review
        </Typography>
        <Button
          variant="outlined"
          startIcon={<Refresh />}
          onClick={() => void fetchRuns()}
          disabled={loading}
        >
          Refresh
        </Button>
        {canManage && (
          <Button
            variant="contained"
            startIcon={triggering ? <CircularProgress size={16} /> : <PlayArrow />}
            onClick={() => void handleTrigger()}
            disabled={triggering || loading}
          >
            Trigger Review
          </Button>
        )}
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {loading && runs.length === 0 ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
          <CircularProgress />
        </Box>
      ) : runs.length === 0 ? (
        <Alert severity="info">
          No review runs yet.{canManage ? ' Click "Trigger Review" to start.' : ''}
        </Alert>
      ) : (
        <Grid container spacing={2}>
          {runs.map((run) => (
            <Grid item xs={12} key={run.id}>
              <Card
                sx={{ cursor: 'pointer', '&:hover': { boxShadow: 4 } }}
                onClick={() =>
                  navigate(`/clients/${clientId}/periods/${periodId}/review/${run.id}/findings`)
                }
              >
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1, gap: 1 }}>
                    <Chip
                      label={run.status.toUpperCase()}
                      color={STATUS_COLOR[run.status] ?? 'default'}
                      size="small"
                    />
                    <Typography variant="caption" color="text.secondary">
                      {run.trigger} · {new Date(run.created_at).toLocaleString()}
                    </Typography>
                    {run.status === 'running' && <CircularProgress size={16} sx={{ ml: 1 }} />}
                  </Box>

                  {run.error_message && (
                    <Alert severity="error" sx={{ mb: 1 }}>
                      {run.error_message}
                    </Alert>
                  )}

                  <Grid container spacing={1}>
                    {(Object.entries(run.module_summary) as [string, ModuleSummary][]).map(
                      ([module, summary]) => (
                        <Grid item xs={6} sm={4} md={2} key={module}>
                          <Box
                            sx={{
                              p: 1,
                              border: '1px solid',
                              borderColor: 'divider',
                              borderRadius: 1,
                            }}
                          >
                            <Typography variant="caption" color="text.secondary" display="block">
                              {MODULE_LABELS[module as keyof typeof MODULE_LABELS] ?? module}
                            </Typography>
                            <Typography variant="body2" fontWeight="bold">
                              {summary.finding_count} finding{summary.finding_count !== 1 ? 's' : ''}
                            </Typography>
                            {summary.exception_count > 0 && (
                              <Typography variant="caption" color="error">
                                {summary.exception_count} error{summary.exception_count !== 1 ? 's' : ''}
                              </Typography>
                            )}
                          </Box>
                        </Grid>
                      ),
                    )}
                  </Grid>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
}
