import {
  AppBar,
  Box,
  Button,
  CircularProgress,
  Container,
  Toolbar,
  Typography,
} from '@mui/material';
import { BrowserRouter, Link as RouterLink, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from '../features/auth/AuthContext';
import LoginPage from '../features/auth/LoginPage';
import ClientDetailPage from '../features/clients/ClientDetailPage';
import ClientsPage from '../features/clients/ClientsPage';
import DocumentsPage from '../features/documents/DocumentsPage';
import HomePage from '../features/home/HomePage';

function Shell() {
  const { state, logout, can } = useAuth();

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
        <Toolbar sx={{ gap: 1 }}>
          <Typography variant="h6" component="h1" sx={{ flexGrow: 1 }}>
            CA Firm System
          </Typography>
          <Button color="inherit" component={RouterLink} to="/">
            Home
          </Button>
          {can('client:read') && (
            <Button color="inherit" component={RouterLink} to="/clients">
              Clients
            </Button>
          )}
          <Button color="inherit" onClick={() => void logout()}>
            Sign out
          </Button>
        </Toolbar>
      </AppBar>
      <Container maxWidth="md" sx={{ mt: 4, mb: 6 }}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/clients" element={<ClientsPage />} />
          <Route path="/clients/:clientId" element={<ClientDetailPage />} />
          <Route path="/clients/:clientId/periods/:periodId" element={<DocumentsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Container>
    </Box>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Shell />
      </AuthProvider>
    </BrowserRouter>
  );
}
