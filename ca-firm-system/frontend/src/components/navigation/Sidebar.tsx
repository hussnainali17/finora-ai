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
  Divider,
  Avatar,
  IconButton,
  Menu,
  MenuItem,
  Stack,
  Tooltip,
  Collapse,
} from '@mui/material';
import {
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
  AccountBalance as TaxIcon,
  Badge as ProfileIcon,
  CompareArrows as ReconIcon,
  Calculate as ComputeIcon,
  Article as FilingIcon,
  Share as ShareIcon,
  Rule as ValidationIcon,
  ExpandLess,
  ExpandMore,
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
  const [accountingOpen, setAccountingOpen] = useState<boolean>(true);
  const [taxationOpen, setTaxationOpen] = useState<boolean>(true);
  const [orchestrationOpen, setOrchestrationOpen] = useState<boolean>(true);

  const isActive = (path: string) => {
    if (path === '/' && location.pathname === '/') return true;
    if (path !== '/' && location.pathname.startsWith(path)) return true;
    return false;
  };

  const getWorkspacePath = (module: string, sub?: string) => {
    if (activeClient && activePeriod) {
      if (!sub) return `/clients/${activeClient.id}/periods/${activePeriod.id}/${module}`;
      return `/clients/${activeClient.id}/periods/${activePeriod.id}/${module}/${sub}`;
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
      <Box sx={{ p: 2, overflowY: 'auto', flex: 1 }}>
        {/* Brand Header */}
        <Stack
          direction="row"
          alignItems="center"
          spacing={1.5}
          sx={{ mb: 2.5, cursor: 'pointer' }}
          onClick={() => navigate('/')}
        >
          <Box
            component="img"
            src="/finora-logo-dark.png"
            alt="Finora Logo"
            sx={{
              height: 38,
              width: 'auto',
              maxWidth: 190,
              objectFit: 'contain',
              display: 'block',
              transition: 'transform 0.25s ease',
              '&:hover': {
                transform: 'scale(1.03)',
              },
            }}
          />
        </Stack>

        {/* Active Client & Period Context Card */}
        <Box
          sx={{
            p: 1.5,
            mb: 2,
            borderRadius: '12px',
            bgcolor: 'rgba(30, 41, 59, 0.7)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            backdropFilter: 'blur(8px)',
          }}
        >
          <Typography
            variant="caption"
            sx={{
              color: '#94a3b8',
              fontWeight: 600,
              textTransform: 'uppercase',
              fontSize: '0.65rem',
              letterSpacing: '0.05em',
            }}
          >
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

        {/* 1. MAIN MENU */}
        <Typography variant="caption" sx={{ px: 1, color: '#64748b', fontWeight: 700, letterSpacing: '0.06em', fontSize: '0.65rem' }}>
          MAIN MENU
        </Typography>

        <List sx={{ pt: 0.5, pb: 1 }}>
          <ListItem disablePadding sx={{ mb: 0.4 }}>
            <ListItemButton
              onClick={() => handleNav('/')}
              selected={isActive('/')}
              sx={{
                borderRadius: '8px',
                py: 0.8,
                px: 1.5,
                color: isActive('/') ? '#ffffff' : '#94a3b8',
                bgcolor: isActive('/') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                border: isActive('/') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
              }}
            >
              <ListItemIcon sx={{ minWidth: 32, color: isActive('/') ? '#818cf8' : '#94a3b8' }}>
                <DashboardIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText primary="Dashboard" primaryTypographyProps={{ fontSize: '0.82rem', fontWeight: 600 }} />
            </ListItemButton>
          </ListItem>

          {can('client:read') && (
            <ListItem disablePadding sx={{ mb: 0.4 }}>
              <ListItemButton
                onClick={() => handleNav('/clients')}
                selected={isActive('/clients') && !location.pathname.includes('/periods/')}
                sx={{
                  borderRadius: '8px',
                  py: 0.8,
                  px: 1.5,
                  color: isActive('/clients') && !location.pathname.includes('/periods/') ? '#ffffff' : '#94a3b8',
                  bgcolor: isActive('/clients') && !location.pathname.includes('/periods/') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                  border: isActive('/clients') && !location.pathname.includes('/periods/') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 32, color: isActive('/clients') && !location.pathname.includes('/periods/') ? '#818cf8' : '#94a3b8' }}>
                  <BusinessIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="Companies & Clients" primaryTypographyProps={{ fontSize: '0.82rem', fontWeight: 600 }} />
              </ListItemButton>
            </ListItem>
          )}
        </List>

        {/* 2. WORK MODULES: ACCOUNTING */}
        <Stack
          direction="row"
          justifyContent="space-between"
          alignItems="center"
          sx={{ px: 1, mt: 1.5, mb: 0.5, cursor: 'pointer' }}
          onClick={() => setAccountingOpen(!accountingOpen)}
        >
          <Typography variant="caption" sx={{ color: '#818cf8', fontWeight: 700, letterSpacing: '0.06em', fontSize: '0.65rem' }}>
            1. ACCOUNTING MODULE
          </Typography>
          {accountingOpen ? <ExpandLess sx={{ fontSize: 16, color: '#818cf8' }} /> : <ExpandMore sx={{ fontSize: 16, color: '#818cf8' }} />}
        </Stack>

        <Collapse in={accountingOpen} timeout="auto" unmountOnExit>
          <List sx={{ pt: 0, pb: 1 }}>
            {/* Accounting Dashboard */}
            <ListItem disablePadding sx={{ mb: 0.4 }}>
              <ListItemButton
                onClick={() => handleNav(getWorkspacePath('accounting'))}
                selected={location.pathname.endsWith('/accounting')}
                sx={{
                  borderRadius: '8px',
                  py: 0.6,
                  px: 1.5,
                  color: location.pathname.endsWith('/accounting') ? '#ffffff' : '#94a3b8',
                  bgcolor: location.pathname.endsWith('/accounting') ? 'rgba(99, 102, 241, 0.25)' : 'transparent',
                  border: location.pathname.endsWith('/accounting') ? '1px solid rgba(99, 102, 241, 0.5)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 32, color: '#818cf8' }}>
                  <DashboardIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="Accounting Dashboard" primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 600 }} />
              </ListItemButton>
            </ListItem>

            {/* File Intake & OCR */}
            <ListItem disablePadding sx={{ mb: 0.4 }}>
              <ListItemButton
                onClick={() => handleNav(getWorkspacePath('accounting', 'intake'))}
                selected={location.pathname.includes('/accounting/intake') || (location.pathname.includes('/documents') && !location.pathname.includes('/orchestration/'))}
                sx={{
                  borderRadius: '8px',
                  py: 0.6,
                  px: 1.5,
                  color: location.pathname.includes('/accounting/intake') ? '#ffffff' : '#94a3b8',
                  bgcolor: location.pathname.includes('/accounting/intake') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                  border: location.pathname.includes('/accounting/intake') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 32, color: '#38bdf8' }}>
                  <CloudUploadIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="File Intake & OCR" primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 500 }} />
              </ListItemButton>
            </ListItem>

            {/* Accounting Review */}
            {can('review:read') && (
              <ListItem disablePadding sx={{ mb: 0.4 }}>
                <ListItemButton
                  onClick={() => handleNav(getWorkspacePath('accounting', 'review'))}
                  selected={location.pathname.includes('/accounting/review') || (location.pathname.includes('/review') && !location.pathname.includes('/taxation/'))}
                  sx={{
                    borderRadius: '8px',
                    py: 0.6,
                    px: 1.5,
                    color: location.pathname.includes('/accounting/review') ? '#ffffff' : '#94a3b8',
                    bgcolor: location.pathname.includes('/accounting/review') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                    border: location.pathname.includes('/accounting/review') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                    '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                  }}
                >
                  <ListItemIcon sx={{ minWidth: 32, color: '#a78bfa' }}>
                    <FactCheckIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText primary="Accounting Review" primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 500 }} />
                </ListItemButton>
              </ListItem>
            )}

            {/* Period Adjustments */}
            {can('adjustment:read') && (
              <ListItem disablePadding sx={{ mb: 0.4 }}>
                <ListItemButton
                  onClick={() => handleNav(getWorkspacePath('accounting', 'adjustments'))}
                  selected={location.pathname.includes('/accounting/adjustments') || (location.pathname.includes('/adjustments') && !location.pathname.includes('/taxation/'))}
                  sx={{
                    borderRadius: '8px',
                    py: 0.6,
                    px: 1.5,
                    color: location.pathname.includes('/accounting/adjustments') ? '#ffffff' : '#94a3b8',
                    bgcolor: location.pathname.includes('/accounting/adjustments') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                    border: location.pathname.includes('/accounting/adjustments') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                    '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                  }}
                >
                  <ListItemIcon sx={{ minWidth: 32, color: '#f59e0b' }}>
                    <BalanceIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText primary="Period Adjustments" primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 500 }} />
                </ListItemButton>
              </ListItem>
            )}

            {/* Financial Statements & CA Sign-Off */}
            {can('report:read') && (
              <ListItem disablePadding sx={{ mb: 0.4 }}>
                <ListItemButton
                  onClick={() => handleNav(getWorkspacePath('accounting', 'reports'))}
                  selected={location.pathname.includes('/accounting/reports') || (location.pathname.includes('/reports') && !location.pathname.includes('/taxation/'))}
                  sx={{
                    borderRadius: '8px',
                    py: 0.6,
                    px: 1.5,
                    color: location.pathname.includes('/accounting/reports') ? '#ffffff' : '#94a3b8',
                    bgcolor: location.pathname.includes('/accounting/reports') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                    border: location.pathname.includes('/accounting/reports') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                    '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                  }}
                >
                  <ListItemIcon sx={{ minWidth: 32, color: '#10b981' }}>
                    <AssessmentIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText primary="Financial Statements & Sign-Off" primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 500 }} />
                </ListItemButton>
              </ListItem>
            )}
          </List>
        </Collapse>

        {/* 3. WORK MODULES: TAXATION */}
        <Stack
          direction="row"
          justifyContent="space-between"
          alignItems="center"
          sx={{ px: 1, mt: 1.5, mb: 0.5, cursor: 'pointer' }}
          onClick={() => setTaxationOpen(!taxationOpen)}
        >
          <Typography variant="caption" sx={{ color: '#34d399', fontWeight: 700, letterSpacing: '0.06em', fontSize: '0.65rem' }}>
            2. TAXATION MODULE
          </Typography>
          {taxationOpen ? <ExpandLess sx={{ fontSize: 16, color: '#34d399' }} /> : <ExpandMore sx={{ fontSize: 16, color: '#34d399' }} />}
        </Stack>

        <Collapse in={taxationOpen} timeout="auto" unmountOnExit>
          <List sx={{ pt: 0, pb: 1 }}>
            {/* Taxation Dashboard */}
            <ListItem disablePadding sx={{ mb: 0.4 }}>
              <ListItemButton
                onClick={() => handleNav(getWorkspacePath('taxation'))}
                selected={location.pathname.endsWith('/taxation')}
                sx={{
                  borderRadius: '8px',
                  py: 0.6,
                  px: 1.5,
                  color: location.pathname.endsWith('/taxation') ? '#ffffff' : '#94a3b8',
                  bgcolor: location.pathname.endsWith('/taxation') ? 'rgba(16, 185, 129, 0.25)' : 'transparent',
                  border: location.pathname.endsWith('/taxation') ? '1px solid rgba(16, 185, 129, 0.5)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 32, color: '#34d399' }}>
                  <TaxIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="Taxation Dashboard" primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 600 }} />
              </ListItemButton>
            </ListItem>

            {/* Agent 1: Tax Intake & Profile */}
            <ListItem disablePadding sx={{ mb: 0.4 }}>
              <ListItemButton
                onClick={() => handleNav(getWorkspacePath('taxation', 'profile'))}
                selected={location.pathname.includes('/taxation/profile')}
                sx={{
                  borderRadius: '8px',
                  py: 0.6,
                  px: 1.5,
                  color: location.pathname.includes('/taxation/profile') ? '#ffffff' : '#94a3b8',
                  bgcolor: location.pathname.includes('/taxation/profile') ? 'rgba(16, 185, 129, 0.2)' : 'transparent',
                  border: location.pathname.includes('/taxation/profile') ? '1px solid rgba(16, 185, 129, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 32, color: '#10b981' }}>
                  <ProfileIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="Tax Intake & Profile" primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 500 }} />
              </ListItemButton>
            </ListItem>

            {/* Agent 2: Tax Data & Reconciliation */}
            <ListItem disablePadding sx={{ mb: 0.4 }}>
              <ListItemButton
                onClick={() => handleNav(getWorkspacePath('taxation', 'reconciliation'))}
                selected={location.pathname.includes('/taxation/reconciliation')}
                sx={{
                  borderRadius: '8px',
                  py: 0.6,
                  px: 1.5,
                  color: location.pathname.includes('/taxation/reconciliation') ? '#ffffff' : '#94a3b8',
                  bgcolor: location.pathname.includes('/taxation/reconciliation') ? 'rgba(16, 185, 129, 0.2)' : 'transparent',
                  border: location.pathname.includes('/taxation/reconciliation') ? '1px solid rgba(16, 185, 129, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 32, color: '#0d9488' }}>
                  <ReconIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="Tax Data & Reconciliation" primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 500 }} />
              </ListItemButton>
            </ListItem>

            {/* Agent 3: Tax Computation & Compliance */}
            <ListItem disablePadding sx={{ mb: 0.4 }}>
              <ListItemButton
                onClick={() => handleNav(getWorkspacePath('taxation', 'computation'))}
                selected={location.pathname.includes('/taxation/computation')}
                sx={{
                  borderRadius: '8px',
                  py: 0.6,
                  px: 1.5,
                  color: location.pathname.includes('/taxation/computation') ? '#ffffff' : '#94a3b8',
                  bgcolor: location.pathname.includes('/taxation/computation') ? 'rgba(16, 185, 129, 0.2)' : 'transparent',
                  border: location.pathname.includes('/taxation/computation') ? '1px solid rgba(16, 185, 129, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 32, color: '#059669' }}>
                  <ComputeIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="Tax Computation & Compliance" primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 500 }} />
              </ListItemButton>
            </ListItem>

            {/* Agent 4: Tax Review & Filing Pack */}
            <ListItem disablePadding sx={{ mb: 0.4 }}>
              <ListItemButton
                onClick={() => handleNav(getWorkspacePath('taxation', 'filing'))}
                selected={location.pathname.includes('/taxation/filing')}
                sx={{
                  borderRadius: '8px',
                  py: 0.6,
                  px: 1.5,
                  color: location.pathname.includes('/taxation/filing') ? '#ffffff' : '#94a3b8',
                  bgcolor: location.pathname.includes('/taxation/filing') ? 'rgba(16, 185, 129, 0.2)' : 'transparent',
                  border: location.pathname.includes('/taxation/filing') ? '1px solid rgba(16, 185, 129, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 32, color: '#16a34a' }}>
                  <FilingIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="Tax Review & Filing Pack" primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 500 }} />
              </ListItemButton>
            </ListItem>
          </List>
        </Collapse>

        {/* 4. ORCHESTRATION */}
        <Stack
          direction="row"
          justifyContent="space-between"
          alignItems="center"
          sx={{ px: 1, mt: 1.5, mb: 0.5, cursor: 'pointer' }}
          onClick={() => setOrchestrationOpen(!orchestrationOpen)}
        >
          <Typography variant="caption" sx={{ color: '#38bdf8', fontWeight: 700, letterSpacing: '0.06em', fontSize: '0.65rem' }}>
            ORCHESTRATION
          </Typography>
          {orchestrationOpen ? <ExpandLess sx={{ fontSize: 16, color: '#38bdf8' }} /> : <ExpandMore sx={{ fontSize: 16, color: '#38bdf8' }} />}
        </Stack>

        <Collapse in={orchestrationOpen} timeout="auto" unmountOnExit>
          <List sx={{ pt: 0, pb: 1 }}>
            {/* Complete CA Workflow */}
            <ListItem disablePadding sx={{ mb: 0.4 }}>
              <ListItemButton
                onClick={() => handleNav(getWorkspacePath('orchestration', 'workflow'))}
                selected={location.pathname.includes('/orchestration/workflow')}
                sx={{
                  borderRadius: '8px',
                  py: 0.6,
                  px: 1.5,
                  color: location.pathname.includes('/orchestration/workflow') ? '#ffffff' : '#94a3b8',
                  bgcolor: location.pathname.includes('/orchestration/workflow') ? 'rgba(56, 189, 248, 0.25)' : 'transparent',
                  border: location.pathname.includes('/orchestration/workflow') ? '1px solid rgba(56, 189, 248, 0.5)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 32, color: '#38bdf8' }}>
                  <HubIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="Complete CA Workflow" primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 600 }} />
              </ListItemButton>
            </ListItem>

            {/* Shared Data & Documents */}
            <ListItem disablePadding sx={{ mb: 0.4 }}>
              <ListItemButton
                onClick={() => handleNav(getWorkspacePath('orchestration', 'shared-data'))}
                selected={location.pathname.includes('/orchestration/shared-data')}
                sx={{
                  borderRadius: '8px',
                  py: 0.6,
                  px: 1.5,
                  color: location.pathname.includes('/orchestration/shared-data') ? '#ffffff' : '#94a3b8',
                  bgcolor: location.pathname.includes('/orchestration/shared-data') ? 'rgba(56, 189, 248, 0.2)' : 'transparent',
                  border: location.pathname.includes('/orchestration/shared-data') ? '1px solid rgba(56, 189, 248, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 32, color: '#a855f7' }}>
                  <ShareIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="Shared Data & Documents" primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 500 }} />
              </ListItemButton>
            </ListItem>

            {/* Central Validation / Reports */}
            <ListItem disablePadding sx={{ mb: 0.4 }}>
              <ListItemButton
                onClick={() => handleNav(getWorkspacePath('orchestration', 'validation'))}
                selected={location.pathname.includes('/orchestration/validation')}
                sx={{
                  borderRadius: '8px',
                  py: 0.6,
                  px: 1.5,
                  color: location.pathname.includes('/orchestration/validation') ? '#ffffff' : '#94a3b8',
                  bgcolor: location.pathname.includes('/orchestration/validation') ? 'rgba(56, 189, 248, 0.2)' : 'transparent',
                  border: location.pathname.includes('/orchestration/validation') ? '1px solid rgba(56, 189, 248, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 32, color: '#f59e0b' }}>
                  <ValidationIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="Central Validation / Reports" primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 500 }} />
              </ListItemButton>
            </ListItem>
          </List>
        </Collapse>

        {/* 5. SYSTEM & SETTINGS */}
        <Typography variant="caption" sx={{ px: 1, color: '#64748b', fontWeight: 700, letterSpacing: '0.06em', fontSize: '0.65rem' }}>
          SYSTEM & SETTINGS
        </Typography>

        <List sx={{ pt: 0.5, pb: 1 }}>
          {can('llm:read') && (
            <ListItem disablePadding sx={{ mb: 0.4 }}>
              <ListItemButton
                onClick={() => handleNav('/settings/models')}
                selected={isActive('/settings/models')}
                sx={{
                  borderRadius: '8px',
                  py: 0.6,
                  px: 1.5,
                  color: isActive('/settings/models') ? '#ffffff' : '#94a3b8',
                  bgcolor: isActive('/settings/models') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                  border: isActive('/settings/models') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 32, color: '#94a3b8' }}>
                  <SmartToyIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="AI Models & Routing" primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 500 }} />
              </ListItemButton>
            </ListItem>
          )}

          {can('audit:read') && (
            <ListItem disablePadding sx={{ mb: 0.4 }}>
              <ListItemButton
                onClick={() => handleNav('/audit')}
                selected={isActive('/audit')}
                sx={{
                  borderRadius: '8px',
                  py: 0.6,
                  px: 1.5,
                  color: isActive('/audit') ? '#ffffff' : '#94a3b8',
                  bgcolor: isActive('/audit') ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                  border: isActive('/audit') ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid transparent',
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc' },
                }}
              >
                <ListItemIcon sx={{ minWidth: 32, color: '#94a3b8' }}>
                  <ShieldIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="Audit Logs" primaryTypographyProps={{ fontSize: '0.8rem', fontWeight: 500 }} />
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
                width: 34,
                height: 34,
                bgcolor: '#4f46e5',
                fontSize: '0.825rem',
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
                <Typography variant="caption" sx={{ color: '#94a3b8', fontSize: '0.68rem' }}>
                  AI Multi-Agent Ready
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
