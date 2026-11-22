import {
  Box,
  CircularProgress,
} from '@mui/material';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
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
import { CAReviewPage } from '../features/ca-review/CAReviewPage';
import { ReportingPage } from '../features/reporting/ReportingPage';
import { WorkflowBoardPage } from '../features/workflows/WorkflowBoardPage';
import { AuditLogPage } from '../features/audit/AuditLogPage';
import { WorkspaceProvider } from '../features/workspace/WorkspaceContext';
import { AppLayout } from '../components/layout/AppLayout';

// Modular Architecture: Accounting, Taxation & Orchestration
import { AccountingDashboardPage } from '../features/accounting/AccountingDashboardPage';
import { TaxationDashboardPage } from '../features/taxation/TaxationDashboardPage';
import { TaxIntakePage } from '../features/taxation/TaxIntakePage';
import { TaxReconciliationPage } from '../features/taxation/TaxReconciliationPage';
import { TaxComputationPage } from '../features/taxation/TaxComputationPage';
import { TaxFilingPage } from '../features/taxation/TaxFilingPage';
import { CompleteWorkflowPage } from '../features/orchestration/CompleteWorkflowPage';
import { SharedDataPage } from '../features/orchestration/SharedDataPage';
import { CentralValidationPage } from '../features/orchestration/CentralValidationPage';

function Shell() {
  const { state, can } = useAuth();

  if (state.status === 'loading') {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh">
        <CircularProgress aria-label="Restoring session" sx={{ color: '#4f46e5' }} />
      </Box>
    );
  }
  if (state.status === 'anonymous') return <LoginPage />;

  return (
    <WorkspaceProvider>
      <AppLayout>
        <Routes>
          {/* Main Menu */}
          <Route path="/" element={<HomePage />} />
          <Route path="/clients" element={<ClientsPage />} />
          <Route path="/clients/:clientId" element={<ClientDetailPage />} />

          {/* Module 1: Accounting */}
          <Route path="/clients/:clientId/periods/:periodId/accounting" element={<AccountingDashboardPage />} />
          <Route path="/clients/:clientId/periods/:periodId/accounting/intake" element={<DocumentsPage />} />
          <Route
            path="/clients/:clientId/periods/:periodId/accounting/review"
            element={can('review:read') ? <AccountingReviewPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/clients/:clientId/periods/:periodId/accounting/adjustments"
            element={can('adjustment:read') ? <AdjustmentsPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/clients/:clientId/periods/:periodId/accounting/reports"
            element={can('report:read') ? <ReportingPage /> : <Navigate to="/" replace />}
          />

          {/* Backward compatibility for original accounting routes */}
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
            path="/clients/:clientId/periods/:periodId/ca-review"
            element={
              can('ca_review:read') || can('workflow:read') || can('review:read') ? (
                <CAReviewPage />
              ) : (
                <Navigate to="/" replace />
              )
            }
          />
          <Route
            path="/clients/:clientId/periods/:periodId/workflows"
            element={can('workflow:read') ? <WorkflowBoardPage /> : <Navigate to="/" replace />}
          />

          {/* Module 2: Taxation */}
          <Route
            path="/clients/:clientId/periods/:periodId/taxation"
            element={can('tax:read') || can('review:read') ? <TaxationDashboardPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/clients/:clientId/periods/:periodId/taxation/profile"
            element={can('tax:read') || can('review:read') ? <TaxIntakePage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/clients/:clientId/periods/:periodId/taxation/reconciliation"
            element={can('tax:read') || can('review:read') ? <TaxReconciliationPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/clients/:clientId/periods/:periodId/taxation/computation"
            element={can('tax:read') || can('review:read') ? <TaxComputationPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/clients/:clientId/periods/:periodId/taxation/filing"
            element={can('tax:read') || can('review:read') ? <TaxFilingPage /> : <Navigate to="/" replace />}
          />

          {/* Orchestration */}
          <Route
            path="/clients/:clientId/periods/:periodId/orchestration/workflow"
            element={can('workflow:read') || can('tax:read') ? <CompleteWorkflowPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/clients/:clientId/periods/:periodId/orchestration/shared-data"
            element={can('shared:read') || can('tax:read') || can('review:read') ? <SharedDataPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/clients/:clientId/periods/:periodId/orchestration/validation"
            element={can('shared:read') || can('tax:read') || can('review:read') ? <CentralValidationPage /> : <Navigate to="/" replace />}
          />

          {/* System & Settings */}
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
      </AppLayout>
    </WorkspaceProvider>
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
