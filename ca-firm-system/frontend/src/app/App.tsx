import {
  AppBar,
  Box,
  Button,
  CircularProgress,
  Container,
  Stack,
  Toolbar,
  Typography,
} from '@mui/material';
import { AuthProvider, useAuth } from '../features/auth/AuthContext';
import LoginPage from '../features/auth/LoginPage';
import ProfilePanel from '../features/auth/ProfilePanel';
import SystemStatus from '../features/system/SystemStatus';

function Shell() {
  const { state, logout } = useAuth();

  if (state.status === 'loading') {
    return (
      <Box display="flex" justifyContent="center" mt={10}>
        <CircularProgress aria-label="Restoring session" />
      </Box>
    );
  }
  if (state.status === 'anonymous') return <LoginPage />;

  return (
    <Box>
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" component="h1" sx={{ flexGrow: 1 }}>
            CA Firm System
          </Typography>
          <Button color="inherit" onClick={() => void logout()}>
            Sign out
          </Button>
        </Toolbar>
      </AppBar>
      <Container maxWidth="sm" sx={{ mt: 4 }}>
        <Stack spacing={3}>
          <ProfilePanel />
          <Typography variant="body2" color="text.secondary">
            Phase 1: identity and access. Client workspaces and accounting review arrive in later
            phases.
          </Typography>
          <SystemStatus />
        </Stack>
      </Container>
    </Box>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}
