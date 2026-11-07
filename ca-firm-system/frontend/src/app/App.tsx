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
import ReviewPage from '../features/documents/ReviewPage';
import HomePage from '../features/home/HomePage';
import ModelSettingsPage from '../features/model-settings/ModelSettingsPage';
import { AccountingReviewPage } from '../features/accounting-review/AccountingReviewPage';
import { FindingsPage } from '../features/accounting-review/FindingsPage';
import { AdjustmentsPage } from '../features/adjustments/AdjustmentsPage';
import { ReportingPage } from '../features/reporting/ReportingPage';
import { WorkflowBoardPage } from '../features/workflows/WorkflowBoardPage';
import { AuditLogPage } from '../features/audit/AuditLogPage';

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
          {can('llm:read') && (
            <Button color="inherit" component={RouterLink} to="/settings/models">
              AI models
            </Button>
          )}
          {can('audit:read') && (
            <Button color="inherit" component={RouterLink} to="/audit">
              Audit
            </Button>
          )}
          <Button color="inherit" onClick={() => void logout()}>
            Sign out
          </Button>
        </Toolbar>
      </AppBar>
      <Container maxWidth="lg" sx={{ mt: 4, mb: 6 }}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/clients" element={<ClientsPage />} />
          <Route path="/clients/:clientId" element={<ClientDetailPage />} />
          <Route path="/clients/:clientId/periods/:periodId" element={<DocumentsPage />} />
          <Route
            path="/clients/:clientId/periods/:periodId/documents/:documentId/review"
            element={<ReviewPage />}
          />
          <Route
            path="/clients/:clientId/periods/:periodId/review"
            element={can('review:read') ? <AccountingReviewPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/clients/:clientId/periods/:periodId/review/:reviewRunId/findings"
            element={can('review:read') ? <FindingsPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/clients/:clientId/periods/:periodId/adjustments"
            element={can('adjustment:read') ? <AdjustmentsPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/clients/:clientId/periods/:periodId/reports"
            element={can('report:read') ? <ReportingPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/clients/:clientId/periods/:periodId/workflows"
            element={can('workflow:read') ? <WorkflowBoardPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/settings/models"
            element={can('llm:read') ? <ModelSettingsPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/audit"
            element={can('audit:read') ? <AuditLogPage /> : <Navigate to="/" replace />}
          />
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
