import React, { useEffect, useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
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
  AccountBalance as AccountBalanceIcon,
  AutoAwesome as AutoAwesomeIcon,
  CloudUpload as CloudUploadIcon,
  FactCheck as FactCheckIcon,
  Balance as BalanceIcon,
  Assessment as AssessmentIcon,
  PlayArrow as PlayArrowIcon,
  ArrowForward as ArrowForwardIcon,
  FolderOpen as FolderOpenIcon,
  History as HistoryIcon,
  Psychology as PsychologyIcon,
  CheckCircle as CheckCircleIcon,
  Apartment as ApartmentIcon,
} from '@mui/icons-material';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import SystemStatus from '../system/SystemStatus';
import { listClients } from '../../services/clientsApi';
import { listAuditEvents } from '../../services/auditApi';
import type { AuditEvent } from '../../types/audit';
import { useWorkspace } from '../workspace/WorkspaceContext';

export default function HomePage(): React.JSX.Element {
  const { can, principal } = useAuth();
  const navigate = useNavigate();
  const { activeClient, activePeriod } = useWorkspace();

  const [clientCount, setClientCount] = useState<number | null>(null);
  const [recentEvents, setRecentEvents] = useState<AuditEvent[]>([]);

  useEffect(() => {
    async function loadDashboard() {
      try {
        if (can('client:read')) {
          const cData = await listClients({ limit: 1 });
          setClientCount(cData.total);
        }
        if (can('audit:read')) {
          const aData = await listAuditEvents({ limit: 6 });
          setRecentEvents(aData.items);
        }
      } catch {
        // Non-blocking dashboard load
      }
    }
    void loadDashboard();
  }, [can]);

  const getWorkspacePath = (sub: string) => {
    if (activeClient && activePeriod) {
      if (sub === 'intake') return `/clients/${activeClient.id}/periods/${activePeriod.id}`;
      return `/clients/${activeClient.id}/periods/${activePeriod.id}/${sub}`;
    }
    return '/clients';
  };

  return (
    <Stack spacing={3.5} className="animate-fade-in">
      {/* Hero Welcome Banner */}
      <Paper
        sx={{
          p: { xs: 3, md: 4 },
          borderRadius: '20px',
          background: 'linear-gradient(135deg, #0b0f19 0%, #1e1b4b 60%, #312e81 100%)',
          color: '#ffffff',
          position: 'relative',
          overflow: 'hidden',
          boxShadow: '0 10px 30px -10px rgba(79, 70, 229, 0.4)',
        }}
      >
        <Box
          sx={{
            position: 'absolute',
            right: '-60px',
            bottom: '-60px',
            width: '280px',
            height: '280px',
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(99, 102, 241, 0.3) 0%, rgba(99, 102, 241, 0) 70%)',
            filter: 'blur(30px)',
          }}
        />

        <Stack spacing={2} sx={{ position: 'relative', zIndex: 1, maxWidth: '850px' }}>
          <Stack direction="row" alignItems="center" spacing={1.5}>
            <Box
              sx={{
                width: 38,
                height: 38,
                borderRadius: '10px',
                background: 'linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 0 15px rgba(99, 102, 241, 0.5)',
              }}
            >
              <AutoAwesomeIcon sx={{ color: '#ffffff', fontSize: 22 }} />
            </Box>
            <Typography variant="overline" sx={{ letterSpacing: '0.12em', color: '#a5b4fc', fontWeight: 700 }}>
              FINORA AI • AUTONOMOUS CA INTELLIGENCE
            </Typography>
          </Stack>

          <Typography variant="h4" fontWeight="800" sx={{ letterSpacing: '-0.02em', lineHeight: 1.2 }}>
            Welcome back, {principal?.email?.split('@')[0] || 'Accountant'}
          </Typography>

          <Typography variant="body1" sx={{ color: '#cbd5e1', fontSize: '1.05rem', maxWidth: '720px' }}>
            Autonomous coordination of File Intake (OCR), Accounting Review, Period Adjustments, and Financial Statements with human checkpoints.
          </Typography>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ pt: 1 }}>
            {activeClient && activePeriod && (
              <Button
                variant="contained"
                size="large"
                startIcon={<PlayArrowIcon />}
                onClick={() => navigate(getWorkspacePath('workflows'))}
                sx={{
                  bgcolor: '#ffffff',
                  color: '#4f46e5',
                  fontWeight: 700,
                  borderRadius: '12px',
                  px: 3,
                  py: 1.2,
                  '&:hover': {
                    bgcolor: '#f1f5f9',
                    transform: 'translateY(-2px)',
                    boxShadow: '0 8px 20px rgba(0,0,0,0.2)',
                  },
                }}
              >
                Run Workflow for {activeClient.name}
              </Button>
            )}
            <Button
              variant="outlined"
              size="large"
              startIcon={<FolderOpenIcon />}
              component={RouterLink}
              to="/clients"
              sx={{
                color: '#ffffff',
                borderColor: 'rgba(255, 255, 255, 0.3)',
                borderRadius: '12px',
                px: 2.5,
                '&:hover': {
                  borderColor: '#ffffff',
                  bgcolor: 'rgba(255, 255, 255, 0.08)',
                },
              }}
            >
              Browse All Companies
            </Button>
          </Stack>
        </Stack>
      </Paper>

      {/* Active Workspace Banner Card */}
      {activeClient && activePeriod && (
        <Card
          sx={{
            p: 1,
            borderRadius: '16px',
            border: '1px solid #e0e7ff',
            background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)',
          }}
        >
          <CardContent sx={{ p: 2 }}>
            <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={2}>
              <Stack direction="row" spacing={2} alignItems="center">
                <Box
                  sx={{
                    width: 48,
                    height: 48,
                    borderRadius: '12px',
                    bgcolor: '#eef2ff',
                    color: '#4f46e5',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <ApartmentIcon fontSize="medium" />
                </Box>
                <Box>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="caption" sx={{ color: '#6366f1', fontWeight: 700, textTransform: 'uppercase' }}>
                      Current Active Workspace
                    </Typography>
                    <Chip label="Ready" size="small" color="success" sx={{ height: 18, fontSize: '0.65rem' }} />
                  </Stack>
                  <Typography variant="h6" fontWeight="700">
                    {activeClient.name}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Accounting Period: <strong>{activePeriod.label}</strong> ({activeClient.base_currency})
                  </Typography>
                </Box>
              </Stack>

              <Stack direction="row" spacing={1} flexWrap="wrap">
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => navigate(getWorkspacePath('intake'))}
                >
                  1. Intake
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => navigate(getWorkspacePath('review'))}
                >
                  2. Review
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => navigate(getWorkspacePath('adjustments'))}
                >
                  3. Adjustments
                </Button>
                <Button
                  size="small"
                  variant="contained"
                  color="success"
                  onClick={() => navigate(getWorkspacePath('reports'))}
                >
                  4. Statements
                </Button>
              </Stack>
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* 4 Autonomous Agents Pipeline Grid */}
      <Box>
        <Typography variant="h6" fontWeight="700" sx={{ mb: 2 }}>
          Finora AI 4-Agent Pipeline
        </Typography>

        <Grid container spacing={2.5}>
          {/* Agent 1 */}
          <Grid item xs={12} sm={6} md={3}>
            <Card
              sx={{
                height: '100%',
                cursor: 'pointer',
                borderTop: '4px solid #38bdf8',
                '&:hover': {
                  transform: 'translateY(-3px)',
                  borderColor: '#0284c7',
                },
              }}
              onClick={() => navigate(getWorkspacePath('intake'))}
            >
              <CardContent sx={{ p: 2.5 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 2 }}>
                  <Box
                    sx={{
                      width: 42,
                      height: 42,
                      borderRadius: '10px',
                      bgcolor: '#e0f2fe',
                      color: '#0284c7',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <CloudUploadIcon fontSize="small" />
                  </Box>
                  <Chip label="Agent 1" size="small" sx={{ bgcolor: '#e0f2fe', color: '#0369a1', fontWeight: 700 }} />
                </Stack>
                <Typography variant="subtitle1" fontWeight="700">
                  File Intake & OCR
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ minHeight: 40, mt: 0.5 }}>
                  Parses client invoices, ledgers, and trial balances with automated schema normalization.
                </Typography>
                <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mt: 2, color: '#0284c7' }}>
                  <Typography variant="button" sx={{ fontSize: '0.8rem', fontWeight: 700 }}>
                    Upload Documents
                  </Typography>
                  <ArrowForwardIcon sx={{ fontSize: 16 }} />
                </Stack>
              </CardContent>
            </Card>
          </Grid>

          {/* Agent 2 */}
          <Grid item xs={12} sm={6} md={3}>
            <Card
              sx={{
                height: '100%',
                cursor: 'pointer',
                borderTop: '4px solid #818cf8',
                '&:hover': {
                  transform: 'translateY(-3px)',
                  borderColor: '#4f46e5',
                },
              }}
              onClick={() => navigate(getWorkspacePath('review'))}
            >
              <CardContent sx={{ p: 2.5 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 2 }}>
                  <Box
                    sx={{
                      width: 42,
                      height: 42,
                      borderRadius: '10px',
                      bgcolor: '#eef2ff',
                      color: '#4f46e5',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <FactCheckIcon fontSize="small" />
                  </Box>
                  <Chip label="Agent 2" size="small" sx={{ bgcolor: '#eef2ff', color: '#4338ca', fontWeight: 700 }} />
                </Stack>
                <Typography variant="subtitle1" fontWeight="700">
                  Accounting Review
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ minHeight: 40, mt: 0.5 }}>
                  Autonomous reconciliation across AR, AP, Bank, Payroll, and Inventory ledgers.
                </Typography>
                <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mt: 2, color: '#4f46e5' }}>
                  <Typography variant="button" sx={{ fontSize: '0.8rem', fontWeight: 700 }}>
                    Audit Findings
                  </Typography>
                  <ArrowForwardIcon sx={{ fontSize: 16 }} />
                </Stack>
              </CardContent>
            </Card>
          </Grid>

          {/* Agent 3 */}
          <Grid item xs={12} sm={6} md={3}>
            <Card
              sx={{
                height: '100%',
                cursor: 'pointer',
                borderTop: '4px solid #f59e0b',
                '&:hover': {
                  transform: 'translateY(-3px)',
                  borderColor: '#d97706',
                },
              }}
              onClick={() => navigate(getWorkspacePath('adjustments'))}
            >
              <CardContent sx={{ p: 2.5 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 2 }}>
                  <Box
                    sx={{
                      width: 42,
                      height: 42,
                      borderRadius: '10px',
                      bgcolor: '#fef3c7',
                      color: '#d97706',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <BalanceIcon fontSize="small" />
                  </Box>
                  <Chip label="Agent 3" size="small" sx={{ bgcolor: '#fef3c7', color: '#b45309', fontWeight: 700 }} />
                </Stack>
                <Typography variant="subtitle1" fontWeight="700">
                  Period Adjustments
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ minHeight: 40, mt: 0.5 }}>
                  Proposes depreciation, accruals, and prepayments with CA approval checkpoint.
                </Typography>
                <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mt: 2, color: '#d97706' }}>
                  <Typography variant="button" sx={{ fontSize: '0.8rem', fontWeight: 700 }}>
                    Review Journals
                  </Typography>
                  <ArrowForwardIcon sx={{ fontSize: 16 }} />
                </Stack>
              </CardContent>
            </Card>
          </Grid>

          {/* Agent 4 */}
          <Grid item xs={12} sm={6} md={3}>
            <Card
              sx={{
                height: '100%',
                cursor: 'pointer',
                borderTop: '4px solid #10b981',
                '&:hover': {
                  transform: 'translateY(-3px)',
                  borderColor: '#059669',
                },
              }}
              onClick={() => navigate(getWorkspacePath('reports'))}
            >
              <CardContent sx={{ p: 2.5 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 2 }}>
                  <Box
                    sx={{
                      width: 42,
                      height: 42,
                      borderRadius: '10px',
                      bgcolor: '#d1fae5',
                      color: '#059669',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <AssessmentIcon fontSize="small" />
                  </Box>
                  <Chip label="Agent 4" size="small" sx={{ bgcolor: '#d1fae5', color: '#047857', fontWeight: 700 }} />
                </Stack>
                <Typography variant="subtitle1" fontWeight="700">
                  Financial Statements
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ minHeight: 40, mt: 0.5 }}>
                  Adjusted Trial Balance, Balance Sheet, P&L generation, and formal CA Sign-Off.
                </Typography>
                <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mt: 2, color: '#059669' }}>
                  <Typography variant="button" sx={{ fontSize: '0.8rem', fontWeight: 700 }}>
                    Statements & Sign-Off
                  </Typography>
                  <ArrowForwardIcon sx={{ fontSize: 16 }} />
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </Box>

      {/* KPI & Summary Row */}
      <Grid container spacing={2.5}>
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ height: '100%', p: 1 }}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Box>
                  <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, letterSpacing: '0.04em' }}>
                    CLIENT COMPANIES
                  </Typography>
                  <Typography variant="h4" fontWeight="800" sx={{ mt: 0.5 }}>
                    {clientCount !== null ? clientCount : '—'}
                  </Typography>
                </Box>
                <AccountBalanceIcon sx={{ fontSize: 36, color: '#4f46e5' }} />
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ height: '100%', p: 1 }}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Box>
                  <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, letterSpacing: '0.04em' }}>
                    AI PIPELINE
                  </Typography>
                  <Typography variant="h4" fontWeight="800" sx={{ mt: 0.5 }}>
                    4 Agents
                  </Typography>
                </Box>
                <PsychologyIcon sx={{ fontSize: 36, color: '#10b981' }} />
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ height: '100%', p: 1 }}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Box>
                  <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, letterSpacing: '0.04em' }}>
                    WORKFLOW ENGINE
                  </Typography>
                  <Typography variant="h5" fontWeight="800" sx={{ mt: 0.5, color: '#0ea5e9' }}>
                    LangGraph
                  </Typography>
                </Box>
                <CheckCircleIcon sx={{ fontSize: 36, color: '#0ea5e9' }} />
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ height: '100%', p: 1 }}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Box>
                  <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 700, letterSpacing: '0.04em' }}>
                    SYSTEM HEALTH
                  </Typography>
                  <Typography variant="h5" fontWeight="800" sx={{ mt: 0.5, color: '#10b981' }}>
                    100% Online
                  </Typography>
                </Box>
                <Box
                  sx={{
                    width: 14,
                    height: 14,
                    borderRadius: '50%',
                    bgcolor: '#10b981',
                    boxShadow: '0 0 10px #10b981',
                  }}
                />
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* System Status Component */}
      <SystemStatus />

      {/* Recent Firm Audit Log */}
      {can('audit:read') && recentEvents.length > 0 && (
        <Paper sx={{ p: 3, borderRadius: '16px', border: '1px solid #e2e8f0' }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <HistoryIcon sx={{ color: '#4f46e5' }} />
              <Typography variant="h6" fontWeight="700">Recent Audit Trail</Typography>
            </Stack>
            <Button size="small" component={RouterLink} to="/audit">
              View All Events
            </Button>
          </Stack>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Timestamp</TableCell>
                <TableCell>Action</TableCell>
                <TableCell>Target</TableCell>
                <TableCell>Details</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {recentEvents.map((evt) => (
                <TableRow key={evt.id} hover>
                  <TableCell sx={{ color: '#64748b', fontSize: '0.82rem' }}>
                    {new Date(evt.occurred_at).toLocaleString()}
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={evt.action}
                      sx={{ fontWeight: 600, bgcolor: '#f1f5f9', color: '#1e293b' }}
                    />
                  </TableCell>
                  <TableCell sx={{ fontWeight: 500 }}>
                    {evt.target_type ? `${evt.target_type}` : '—'}
                  </TableCell>
                  <TableCell sx={{ color: '#64748b', fontSize: '0.82rem' }}>
                    {evt.metadata ? JSON.stringify(evt.metadata).slice(0, 70) : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}
    </Stack>
  );
}
