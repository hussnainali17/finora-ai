import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import {
  AccountBalance,
  Analytics,
  FolderOpen,
  History,
  Psychology,
  Settings,
} from '@mui/icons-material';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import ProfilePanel from '../auth/ProfilePanel';
import SystemStatus from '../system/SystemStatus';
import { listClients } from '../../services/clientsApi';
import { listAuditEvents } from '../../services/auditApi';
import type { AuditEvent } from '../../types/audit';

export default function HomePage(): React.JSX.Element {
  const { principal, can } = useAuth();
  const navigate = useNavigate();

  const [clientCount, setClientCount] = useState<number | null>(null);
  const [recentEvents, setRecentEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function loadDashboard() {
      setLoading(true);
      try {
        if (can('client:read')) {
          const cData = await listClients({ limit: 1 });
          setClientCount(cData.total);
        }
        if (can('audit:read')) {
          const aData = await listAuditEvents({ limit: 8 });
          setRecentEvents(aData.items);
        }
      } catch {
        // Non-blocking dashboard load
      } finally {
        setLoading(false);
      }
    }
    void loadDashboard();
  }, [can]);

  return (
    <Stack spacing={3}>
      <ProfilePanel />

      {/* KPI Cards */}
      <Grid container spacing={2}>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ height: '100%', bgcolor: 'background.paper', borderLeft: '4px solid #1976d2' }}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Box>
                  <Typography variant="caption" color="text.secondary">TOTAL CLIENTS</Typography>
                  <Typography variant="h4" fontWeight="bold">
                    {clientCount !== null ? clientCount : '—'}
                  </Typography>
                </Box>
                <AccountBalance color="primary" sx={{ fontSize: 36 }} />
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ height: '100%', bgcolor: 'background.paper', borderLeft: '4px solid #2e7d32' }}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Box>
                  <Typography variant="caption" color="text.secondary">AI AGENTS</Typography>
                  <Typography variant="h4" fontWeight="bold">4</Typography>
                </Box>
                <Psychology color="success" sx={{ fontSize: 36 }} />
              </Stack>
              <Typography variant="caption" color="text.secondary">
                Intake, Review, Adjustments, Reporting
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ height: '100%', bgcolor: 'background.paper', borderLeft: '4px solid #ed6c02' }}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Box>
                  <Typography variant="caption" color="text.secondary">GATEWAY</Typography>
                  <Typography variant="h4" fontWeight="bold">LiteLLM</Typography>
                </Box>
                <Analytics color="warning" sx={{ fontSize: 36 }} />
              </Stack>
              <Typography variant="caption" color="text.secondary">
                Centralized server-side proxy
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ height: '100%', bgcolor: 'background.paper', borderLeft: '4px solid #9c27b0' }}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Box>
                  <Typography variant="caption" color="text.secondary">EVENT BUS</Typography>
                  <Typography variant="h4" fontWeight="bold">Kafka</Typography>
                </Box>
                <Settings color="secondary" sx={{ fontSize: 36 }} />
              </Stack>
              <Typography variant="caption" color="text.secondary">
                KRaft async workers & DLQ
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Quick Access Actions */}
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="h6" gutterBottom>Quick Actions</Typography>
        <Stack direction="row" spacing={2} flexWrap="wrap">
          {can('client:read') && (
            <Button
              variant="contained"
              startIcon={<FolderOpen />}
              component={RouterLink}
              to="/clients"
            >
              Browse Client Workspaces
            </Button>
          )}
          {can('llm:read') && (
            <Button
              variant="outlined"
              startIcon={<Psychology />}
              component={RouterLink}
              to="/settings/models"
            >
              Configure AI Models
            </Button>
          )}
          {can('audit:read') && (
            <Button
              variant="outlined"
              startIcon={<History />}
              component={RouterLink}
              to="/audit"
            >
              View Audit Trail
            </Button>
          )}
        </Stack>
      </Paper>

      {/* Recent Firm Audit Log */}
      {can('audit:read') && recentEvents.length > 0 && (
        <Paper sx={{ p: 2.5 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
            <Typography variant="h6">Recent Firm Activity</Typography>
            <Button size="small" component={RouterLink} to="/audit">
              View All Events
            </Button>
          </Stack>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Time</TableCell>
                <TableCell>Action</TableCell>
                <TableCell>Target Type</TableCell>
                <TableCell>Actor</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {recentEvents.map((e) => (
                <TableRow key={e.id} hover>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                    <Typography variant="caption">{new Date(e.occurred_at).toLocaleTimeString()}</Typography>
                  </TableCell>
                  <TableCell>
                    <Chip size="small" label={e.action} color="primary" variant="outlined" />
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">{e.target_type}</Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="caption" color="text.secondary">
                      {e.actor_user_id ? e.actor_user_id.slice(0, 8) + '...' : 'System'}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      {/* System Infrastructure Health */}
      <SystemStatus />
    </Stack>
  );
}
