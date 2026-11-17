import React from 'react';
import {
  AppBar,
  Box,
  Button,
  Chip,
  IconButton,
  Stack,
  Toolbar,
  Typography,
} from '@mui/material';
import {
  PlayArrow as PlayArrowIcon,
  Refresh as RefreshIcon,
  Apartment as ApartmentIcon,
  CalendarMonth as CalendarMonthIcon,
} from '@mui/icons-material';
import { useLocation, useNavigate } from 'react-router-dom';
import { useWorkspace } from '../../features/workspace/WorkspaceContext';

export const Header: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { activeClient, activePeriod } = useWorkspace();

  const getPageTitle = () => {
    const p = location.pathname;
    if (p === '/') return 'Finora AI Command Center';
    if (p.includes('/workflows')) return 'Autonomous Accounting Workflow (LangGraph)';
    if (p.includes('/reports')) return 'Financial Statements & CA Sign-Off (Agent 4)';
    if (p.includes('/adjustments')) return 'Period-End Adjustments & Journals (Agent 3)';
    if (p.includes('/review')) return 'Accounting Review & Anomaly Detection (Agent 2)';
    if (p.includes('/documents') || p.match(/\/clients\/[^/]+\/periods\/[^/]+$/)) return 'Document Intake & OCR (Agent 1)';
    if (p.startsWith('/clients')) return 'Client Companies Management';
    if (p.startsWith('/settings/models')) return 'AI Models & Gateway Settings';
    if (p.startsWith('/audit')) return 'Compliance & Audit Trail';
    return 'Finora AI System';
  };

  return (
    <AppBar
      position="sticky"
      sx={{
        backgroundColor: 'rgba(255, 255, 255, 0.85)',
        backdropFilter: 'blur(12px)',
        borderBottom: '1px solid #e2e8f0',
        boxShadow: '0 1px 3px rgba(0, 0, 0, 0.03)',
        color: '#0f172a',
        zIndex: 1100,
      }}
    >
      <Toolbar sx={{ justifyContent: 'space-between', minHeight: '68px', px: { xs: 2, md: 3 } }}>
        {/* Left: Page Title & Context */}
        <Box>
          <Typography variant="h6" fontWeight="700" sx={{ color: '#0f172a', fontSize: '1.15rem' }}>
            {getPageTitle()}
          </Typography>
          {activeClient && (
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.2 }}>
              <Chip
                icon={<ApartmentIcon sx={{ fontSize: '14px !important' }} />}
                label={activeClient.name}
                size="small"
                onClick={() => navigate(`/clients/${activeClient.id}`)}
                sx={{
                  height: 22,
                  fontSize: '0.72rem',
                  fontWeight: 600,
                  bgcolor: '#f1f5f9',
                  color: '#334155',
                  cursor: 'pointer',
                  '&:hover': { bgcolor: '#e2e8f0' },
                }}
              />
              {activePeriod && (
                <Chip
                  icon={<CalendarMonthIcon sx={{ fontSize: '14px !important' }} />}
                  label={activePeriod.label}
                  size="small"
                  sx={{
                    height: 22,
                    fontSize: '0.72rem',
                    fontWeight: 600,
                    bgcolor: 'rgba(99, 102, 241, 0.1)',
                    color: '#4f46e5',
                    border: '1px solid rgba(99, 102, 241, 0.2)',
                  }}
                />
              )}
            </Stack>
          )}
        </Box>

        {/* Right: Quick Action Controls */}
        <Stack direction="row" spacing={1.5} alignItems="center">
          {activeClient && activePeriod && !location.pathname.includes('/workflows') && (
            <Button
              variant="contained"
              size="small"
              startIcon={<PlayArrowIcon />}
              onClick={() => navigate(`/clients/${activeClient.id}/periods/${activePeriod.id}/workflows`)}
              sx={{
                bgcolor: '#4f46e5',
                color: '#ffffff',
                fontWeight: 700,
                fontSize: '0.8rem',
                borderRadius: '8px',
                px: 2,
                py: 0.8,
                background: 'linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%)',
                boxShadow: '0 2px 10px rgba(79, 70, 229, 0.3)',
                '&:hover': {
                  background: 'linear-gradient(135deg, #4338ca 0%, #0891b2 100%)',
                },
              }}
            >
              Run Autonomous Workflow
            </Button>
          )}
          <IconButton
            size="small"
            onClick={() => window.location.reload()}
            sx={{
              color: '#64748b',
              border: '1px solid #e2e8f0',
              bgcolor: '#ffffff',
              '&:hover': { bgcolor: '#f8fafc', color: '#0f172a' },
            }}
          >
            <RefreshIcon fontSize="small" />
          </IconButton>
        </Stack>
      </Toolbar>
    </AppBar>
  );
};
