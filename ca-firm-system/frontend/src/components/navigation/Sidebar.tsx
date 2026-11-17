import React, { useState } from 'react';
import {
  Box,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Typography,
  Chip,
  Divider,
  Avatar,
  IconButton,
  Menu,
  MenuItem,
  Stack,
  Tooltip,
} from '@mui/material';
import {
  AutoAwesome,
  Dashboard as DashboardIcon,
  Business as BusinessIcon,
  CloudUpload as CloudUploadIcon,
  FactCheck as FactCheckIcon,
  Balance as BalanceIcon,
  Assessment as AssessmentIcon,
  Hub as HubIcon,
  SmartToy as SmartToyIcon,
  Shield as ShieldIcon,
  Logout as LogoutIcon,
  SwapHoriz as SwapHorizIcon,
  CheckCircle as CheckCircleIcon,
} from '@mui/icons-material';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthContext';
import { useWorkspace } from '../../features/workspace/WorkspaceContext';

const DRAWER_WIDTH = 280;

export const Sidebar: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout, principal, can } = useAuth();
  const {
    activeClient,
    activePeriod,
    clientsList,
    periodsList,
    setActiveClientById,
    setActivePeriodById,
  } = useWorkspace();

  const [clientAnchor, setClientAnchor] = useState<null | HTMLElement>(null);

  const isActive = (path: string) => {
    if (path === '/' && location.pathname === '/') return true;
    if (path !== '/' && location.pathname.startsWith(path)) return true;
    return false;
  };

  const getWorkspacePath = (sub: string) => {
    if (activeClient && activePeriod) {
      if (sub === 'intake') return `/clients/${activeClient.id}/periods/${activePeriod.id}`;
      return `/clients/${activeClient.id}/periods/${activePeriod.id}/${sub}`;
    }
    return '/clients';
  };

  const handleNav = (targetPath: string) => {
    navigate(targetPath);
  };

  return (
    <Drawer
      variant="permanent"
      sx={{
        width: DRAWER_WIDTH,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: DRAWER_WIDTH,
          boxSizing: 'border-box',
          background: 'linear-gradient(180deg, #0b0f19 0%, #111827 100%)',
          color: '#f8fafc',
          borderRight: '1px solid rgba(255, 255, 255, 0.08)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          overflowX: 'hidden',
        },
      }}
    >
      <Box sx={{ p: 2.5 }}>
        {/* Brand Header */}
        <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 3, cursor: 'pointer' }} onClick={() => navigate('/')}>
          <Box
            sx={{
              width: 42,
              height: 42,
              borderRadius: '12px',
              background: 'linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 20px rgba(99, 102, 241, 0.5)',
              transition: 'transform 0.3s ease',
              '&:hover': {
                transform: 'scale(1.05) rotate(3deg)',
              },
            }}
          >
            <AutoAwesome sx={{ color: '#ffffff', fontSize: 24 }} />
          </Box>
          <Box>
            <Stack direction="row" alignItems="center" spacing={1}>
              <Typography variant="h6" fontWeight="800" sx={{ letterSpacing: '-0.02em', color: '#ffffff', fontSize: '1.25rem' }}>
                Finora <span style={{ color: '#818cf8' }}>AI</span>
              </Typography>
              <Chip
                label="v2.0"
                size="small"
                sx={{
                  height: 18,
                  fontSize: '0.65rem',
                  fontWeight: 700,
                  bgcolor: 'rgba(99, 102, 241, 0.2)',
                  color: '#a5b4fc',
                  border: '1px solid rgba(99, 102, 241, 0.4)',
                }}
              />
            </Stack>
            <Typography variant="caption" sx={{ color: '#94a3b8', fontSize: '0.72rem', display: 'block', mt: -0.2 }}>
              Autonomous CA Intelligence
            </Typography>
          </Box>
        </Stack>

        {/* Active Client & Period Context Card */}
        <Box
          sx={{
            p: 1.5,
            mb: 2.5,
            borderRadius: '14px',
            bgcolor: 'rgba(30, 41, 59, 0.7)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            backdropFilter: 'blur(8px)',
          }}
        >
          <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', fontSize: '0.68rem', letterSpacing: '0.05em' }}>
            Active Workspace
          </Typography>

          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mt: 0.5 }}>
            <Box sx={{ overflow: 'hidden', pr: 1 }}>
              <Typography variant="body2" fontWeight="700" noWrap sx={{ color: '#f1f5f9' }}>
                {activeClient ? activeClient.name : 'No Client Selected'}
              </Typography>
              <Typography variant="caption" sx={{ color: '#38bdf8', fontWeight: 600 }}>
                {activePeriod ? activePeriod.label : 'Select Period'}
              </Typography>
            </Box>

            <Tooltip title="Switch Company or Period">
              <IconButton
                size="small"
                onClick={(e) => setClientAnchor(e.currentTarget)}
                sx={{
                  bgcolor: 'rgba(99, 102, 241, 0.15)',
                  color: '#818cf8',
                  '&:hover': { bgcolor: 'rgba(99, 102, 241, 0.3)' },
                }}
              >
                <SwapHorizIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Stack>

          {/* Quick client switcher dropdown */}
          <Menu
            anchorEl={clientAnchor}
            open={Boolean(clientAnchor)}
            onClose={() => setClientAnchor(null)}
            PaperProps={{
              sx: {
                bgcolor: '#1e293b',
                color: '#f8fafc',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                minWidth: 220,
              },
            }}
          >
            <Typography variant="caption" sx={{ px: 2, py: 1, display: 'block', color: '#94a3b8', fontWeight: 700 }}>
              SELECT CLIENT COMPANY
            </Typography>
            {clientsList.map((c) => (
              <MenuItem
                key={c.id}
                selected={c.id === activeClient?.id}
                onClick={() => {
                  void setActiveClientById(c.id);
                  setClientAnchor(null);
                }}
                sx={{
                  '&.Mui-selected': { bgcolor: 'rgba(99, 102, 241, 0.25)' },
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)' },
                }}
              >
                <Stack direction="row" justifyContent="space-between" width="100%" alignItems="center">
                  <Typography variant="body2" fontWeight={c.id === activeClient?.id ? 700 : 500}>
                    {c.name}
                  </Typography>
                  {c.id === activeClient?.id && <CheckCircleIcon sx={{ fontSize: 16, color: '#10b981' }} />}
                </Stack>
              </MenuItem>
            ))}
            {periodsList.length > 1 && (
              <>
                <Divider sx={{ my: 1, borderColor: 'rgba(255, 255, 255, 0.1)' }} />
                <Typography variant="caption" sx={{ px: 2, py: 1, display: 'block', color: '#94a3b8', fontWeight: 700 }}>
                  ACCOUNTING PERIOD
                </Typography>
                {periodsList.map((p) => (
                  <MenuItem
                    key={p.id}
                    selected={p.id === activePeriod?.id}
                    onClick={() => {
                      setActivePeriodById(p.id);
                      setClientAnchor(null);
                    }}
                    sx={{
                      '&.Mui-selected': { bgcolor: 'rgba(56, 189, 248, 0.2)' },
                      '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)' },
                    }}
                  >
                    <Typography variant="body2">{p.label}</Typography>
                  </MenuItem>
                ))}
              </>
            )}
          </Menu>
        </Box>

        {/* Navigation Menu */}
        <Typography variant="caption" sx={{ px: 1, color: '#64748b', fontWeight: 700, letterSpacing: '0.06em', fontSize: '0.68rem' }}>
          OVERVIEW
        </Typography>

        <List sx={{ pt: 0.5, pb: 1 }}>
          <ListItem disablePadding sx={{ mb: 0.5 }}>
            <ListItemButton
              onClick={() => handleNav('/')}
              selected={isActive('/')}
              sx={{
                borderRadius: '10px',
                py: 1,
                px: 1.5,
                color: isActive('/') ? '#ffffff' : '#94a3b8',
                bgcolor: isActive('/') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                border: isActive('/') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
              }}
            >
              <ListItemIcon sx={{ minWidth: 34, color: isActive('/') ? '#818cf8' : '#94a3b8' }}>
                <DashboardIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText primary="Dashboard" primaryTypographyProps={{ fontSize: '0.875rem', fontWeight: 600 }} />
            </ListItemButton>
          </ListItem>

          {can('client:read') && (
            <ListItem disablePadding sx={{ mb: 0.5 }}>
              <ListItemButton
                onClick={() => handleNav('/clients')}
                selected={isActive('/clients') && !location.pathname.includes('/periods/')}
                sx={{
                  borderRadius: '10px',
                  py: 1,
                  px: 1.5,
                  color: isActive('/clients') && !location.pathname.includes('/periods/') ? '#ffffff' : '#94a3b8',
                  bgcolor: isActive('/clients') && !location.pathname.includes('/periods/') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                  border: isActive('/clients') && !location.pathname.includes('/periods/') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 34, color: isActive('/clients') && !location.pathname.includes('/periods/') ? '#818cf8' : '#94a3b8' }}>
                  <BusinessIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="Companies & Clients" primaryTypographyProps={{ fontSize: '0.875rem', fontWeight: 600 }} />
              </ListItemButton>
            </ListItem>
          )}
        </List>

        <Typography variant="caption" sx={{ px: 1, color: '#64748b', fontWeight: 700, letterSpacing: '0.06em', fontSize: '0.68rem', mt: 1, display: 'block' }}>
          AUTONOMOUS CA PIPELINE
        </Typography>

        <List sx={{ pt: 0.5, pb: 1 }}>
          {/* Agent 1 */}
          <ListItem disablePadding sx={{ mb: 0.5 }}>
            <ListItemButton
              onClick={() => handleNav(getWorkspacePath('intake'))}
              selected={location.pathname.endsWith(activePeriod?.id ?? '') || location.pathname.includes('/documents/')}
              sx={{
                borderRadius: '10px',
                py: 0.8,
                px: 1.5,
                color: location.pathname.endsWith(activePeriod?.id ?? '') ? '#ffffff' : '#94a3b8',
                bgcolor: location.pathname.endsWith(activePeriod?.id ?? '') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                border: location.pathname.endsWith(activePeriod?.id ?? '') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
              }}
            >
              <ListItemIcon sx={{ minWidth: 34, color: '#38bdf8' }}>
                <CloudUploadIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText
                primary="1. File Intake & OCR"
                secondary="Agent 1 • Document Extraction"
                primaryTypographyProps={{ fontSize: '0.85rem', fontWeight: 600 }}
                secondaryTypographyProps={{ fontSize: '0.68rem', color: '#64748b' }}
              />
            </ListItemButton>
          </ListItem>

          {/* Agent 2 */}
          {can('review:read') && (
            <ListItem disablePadding sx={{ mb: 0.5 }}>
              <ListItemButton
                onClick={() => handleNav(getWorkspacePath('review'))}
                selected={location.pathname.includes('/review')}
                sx={{
                  borderRadius: '10px',
                  py: 0.8,
                  px: 1.5,
                  color: location.pathname.includes('/review') ? '#ffffff' : '#94a3b8',
                  bgcolor: location.pathname.includes('/review') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                  border: location.pathname.includes('/review') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 34, color: '#a78bfa' }}>
                  <FactCheckIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText
                  primary="2. Accounting Review"
                  secondary="Agent 2 • Anomaly & Reconciliation"
                  primaryTypographyProps={{ fontSize: '0.85rem', fontWeight: 600 }}
                  secondaryTypographyProps={{ fontSize: '0.68rem', color: '#64748b' }}
                />
              </ListItemButton>
            </ListItem>
          )}

          {/* Agent 3 */}
          {can('adjustment:read') && (
            <ListItem disablePadding sx={{ mb: 0.5 }}>
              <ListItemButton
                onClick={() => handleNav(getWorkspacePath('adjustments'))}
                selected={location.pathname.includes('/adjustments')}
                sx={{
                  borderRadius: '10px',
                  py: 0.8,
                  px: 1.5,
                  color: location.pathname.includes('/adjustments') ? '#ffffff' : '#94a3b8',
                  bgcolor: location.pathname.includes('/adjustments') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                  border: location.pathname.includes('/adjustments') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 34, color: '#f59e0b' }}>
                  <BalanceIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText
                  primary="3. Period Adjustments"
                  secondary="Agent 3 • Accruals & Depreciation"
                  primaryTypographyProps={{ fontSize: '0.85rem', fontWeight: 600 }}
                  secondaryTypographyProps={{ fontSize: '0.68rem', color: '#64748b' }}
                />
              </ListItemButton>
            </ListItem>
          )}

          {/* Agent 4 */}
          {can('report:read') && (
            <ListItem disablePadding sx={{ mb: 0.5 }}>
              <ListItemButton
                onClick={() => handleNav(getWorkspacePath('reports'))}
                selected={location.pathname.includes('/reports')}
                sx={{
                  borderRadius: '10px',
                  py: 0.8,
                  px: 1.5,
                  color: location.pathname.includes('/reports') ? '#ffffff' : '#94a3b8',
                  bgcolor: location.pathname.includes('/reports') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                  border: location.pathname.includes('/reports') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 34, color: '#10b981' }}>
                  <AssessmentIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText
                  primary="4. Financial Statements"
                  secondary="Agent 4 • P&L, BS & Sign-Off"
                  primaryTypographyProps={{ fontSize: '0.85rem', fontWeight: 600 }}
                  secondaryTypographyProps={{ fontSize: '0.68rem', color: '#64748b' }}
                />
              </ListItemButton>
            </ListItem>
          )}

          {/* Autonomous Workflow (LangGraph) */}
          {can('workflow:read') && (
            <ListItem disablePadding sx={{ mb: 0.5 }}>
              <ListItemButton
                onClick={() => handleNav(getWorkspacePath('workflows'))}
                selected={location.pathname.includes('/workflows')}
                sx={{
                  borderRadius: '10px',
                  py: 1,
                  px: 1.5,
                  color: '#ffffff',
                  background: location.pathname.includes('/workflows')
                    ? 'linear-gradient(135deg, rgba(99, 102, 241, 0.35) 0%, rgba(6, 182, 212, 0.3) 100%)'
                    : 'linear-gradient(135deg, rgba(99, 102, 241, 0.12) 0%, rgba(6, 182, 212, 0.08) 100%)',
                  border: '1px solid rgba(99, 102, 241, 0.3)',
                  '&:hover': {
                    background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.25) 0%, rgba(6, 182, 212, 0.2) 100%)',
                  },
                }}
              >
                <ListItemIcon sx={{ minWidth: 34, color: '#38bdf8' }}>
                  <HubIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText
                  primary="Autonomous Workflow"
                  secondary="Full LangGraph Coordination"
                  primaryTypographyProps={{ fontSize: '0.85rem', fontWeight: 700 }}
                  secondaryTypographyProps={{ fontSize: '0.68rem', color: '#93c5fd' }}
                />
              </ListItemButton>
            </ListItem>
          )}
        </List>

        <Typography variant="caption" sx={{ px: 1, color: '#64748b', fontWeight: 700, letterSpacing: '0.06em', fontSize: '0.68rem', mt: 1, display: 'block' }}>
          SYSTEM & SETTINGS
        </Typography>

        <List sx={{ pt: 0.5, pb: 1 }}>
          {can('llm:read') && (
            <ListItem disablePadding sx={{ mb: 0.5 }}>
              <ListItemButton
                onClick={() => handleNav('/settings/models')}
                selected={isActive('/settings/models')}
                sx={{
                  borderRadius: '10px',
                  py: 0.8,
                  px: 1.5,
                  color: isActive('/settings/models') ? '#ffffff' : '#94a3b8',
                  bgcolor: isActive('/settings/models') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                  border: isActive('/settings/models') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 34, color: '#94a3b8' }}>
                  <SmartToyIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="AI Models & Routing" primaryTypographyProps={{ fontSize: '0.85rem', fontWeight: 500 }} />
              </ListItemButton>
            </ListItem>
          )}

          {can('audit:read') && (
            <ListItem disablePadding sx={{ mb: 0.5 }}>
              <ListItemButton
                onClick={() => handleNav('/audit')}
                selected={isActive('/audit')}
                sx={{
                  borderRadius: '10px',
                  py: 0.8,
                  px: 1.5,
                  color: isActive('/audit') ? '#ffffff' : '#94a3b8',
                  bgcolor: isActive('/audit') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                  border: isActive('/audit') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 34, color: '#94a3b8' }}>
                  <ShieldIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="Audit Logs" primaryTypographyProps={{ fontSize: '0.85rem', fontWeight: 500 }} />
              </ListItemButton>
            </ListItem>
          )}
        </List>
      </Box>

      {/* User & Status Footer */}
      <Box sx={{ p: 2, borderTop: '1px solid rgba(255, 255, 255, 0.08)', bgcolor: 'rgba(15, 23, 42, 0.6)' }}>
        <Stack direction="row" alignItems="center" spacing={1.5} justifyContent="space-between">
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ overflow: 'hidden' }}>
            <Avatar
              sx={{
                width: 36,
                height: 36,
                bgcolor: '#4f46e5',
                fontSize: '0.875rem',
                fontWeight: 700,
              }}
            >
              {principal?.email ? principal.email[0].toUpperCase() : 'U'}
            </Avatar>
            <Box sx={{ overflow: 'hidden' }}>
              <Typography variant="body2" fontWeight="700" noWrap sx={{ color: '#f1f5f9' }}>
                {principal?.email?.split('@')[0] || 'User'}
              </Typography>
              <Stack direction="row" alignItems="center" spacing={0.5}>
                <Box
                  sx={{
                    width: 7,
                    height: 7,
                    borderRadius: '50%',
                    bgcolor: '#10b981',
                    boxShadow: '0 0 8px #10b981',
                  }}
                />
                <Typography variant="caption" sx={{ color: '#94a3b8', fontSize: '0.7rem' }}>
                  AI Ready
                </Typography>
              </Stack>
            </Box>
          </Stack>

          <Tooltip title="Sign Out">
            <IconButton
              size="small"
              onClick={() => void logout()}
              sx={{
                color: '#94a3b8',
                '&:hover': { color: '#f43f5e', bgcolor: 'rgba(244, 63, 94, 0.1)' },
              }}
            >
              <LogoutIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      </Box>
    </Drawer>
  );
};
