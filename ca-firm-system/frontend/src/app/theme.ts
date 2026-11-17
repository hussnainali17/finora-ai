import { createTheme } from '@mui/material/styles';

// Finora AI Modern Brand Palette
const PRIMARY = {
  main: '#4f46e5', // Electric Indigo
  light: '#818cf8',
  dark: '#3730a3',
  contrastText: '#ffffff',
};

const SECONDARY = {
  main: '#059669', // Emerald Growth
  light: '#34d399',
  dark: '#065f46',
  contrastText: '#ffffff',
};


export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: PRIMARY,
    secondary: SECONDARY,
    background: {
      default: '#f8fafc', // Ultra crisp slate canvas
      paper: '#ffffff',
    },
    text: {
      primary: '#0f172a',
      secondary: '#64748b',
    },
    success: {
      main: '#10b981',
      light: '#d1fae5',
      dark: '#047857',
    },
    warning: {
      main: '#f59e0b',
      light: '#fef3c7',
      dark: '#b45309',
    },
    error: {
      main: '#f43f5e',
      light: '#ffe4e6',
      dark: '#be123c',
    },
    info: {
      main: '#0ea5e9',
      light: '#e0f2fe',
      dark: '#0369a1',
    },
    divider: '#e2e8f0',
  },
  typography: {
    fontFamily: ['Plus Jakarta Sans', 'Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'].join(','),
    h1: { fontWeight: 800, letterSpacing: '-0.025em' },
    h2: { fontWeight: 700, letterSpacing: '-0.02em' },
    h3: { fontWeight: 700, letterSpacing: '-0.015em' },
    h4: { fontWeight: 700, letterSpacing: '-0.01em' },
    h5: { fontWeight: 600, letterSpacing: '-0.005em' },
    h6: { fontWeight: 600 },
    subtitle1: { fontWeight: 600 },
    subtitle2: { fontWeight: 600, color: '#64748b' },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  shape: {
    borderRadius: 12,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: '#f8fafc',
          color: '#0f172a',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          padding: '8px 18px',
          boxShadow: 'none',
          transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
          '&:hover': {
            transform: 'translateY(-1px)',
            boxShadow: '0 4px 12px rgba(79, 70, 229, 0.25)',
          },
          '&:active': {
            transform: 'translateY(0)',
          },
        },
        containedPrimary: {
          background: 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
          color: '#ffffff',
          '&:hover': {
            background: 'linear-gradient(135deg, #4338ca 0%, #4f46e5 100%)',
          },
        },
        containedSecondary: {
          background: 'linear-gradient(135deg, #059669 0%, #10b981 100%)',
          color: '#ffffff',
          '&:hover': {
            background: 'linear-gradient(135deg, #047857 0%, #059669 100%)',
            boxShadow: '0 4px 12px rgba(16, 185, 129, 0.25)',
          },
        },
        outlined: {
          borderColor: '#e2e8f0',
          backgroundColor: '#ffffff',
          color: '#334155',
          '&:hover': {
            borderColor: '#cbd5e1',
            backgroundColor: '#f8fafc',
            boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          border: '1px solid #e2e8f0',
          boxShadow: '0 2px 8px -2px rgba(15, 23, 42, 0.05)',
          transition: 'all 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
          '&:hover': {
            boxShadow: '0 12px 24px -4px rgba(15, 23, 42, 0.08)',
          },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 14,
          boxShadow: '0 1px 4px rgba(15, 23, 42, 0.05)',
        },
      },
    },
    MuiTableHead: {
      styleOverrides: {
        root: {
          backgroundColor: '#f8fafc',
          '& .MuiTableCell-root': {
            color: '#475569',
            fontWeight: 700,
            fontSize: '0.785rem',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            borderBottom: '1px solid #e2e8f0',
          },
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: {
          borderBottom: '1px solid #f1f5f9',
          padding: '12px 16px',
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          fontWeight: 600,
          borderRadius: 8,
          fontSize: '0.75rem',
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: '#ffffff',
          color: '#0f172a',
          boxShadow: '0 1px 3px rgba(0, 0, 0, 0.05)',
          borderBottom: '1px solid #e2e8f0',
        },
      },
    },
  },
});
