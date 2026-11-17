import React, { useEffect } from 'react';
import { Box } from '@mui/material';
import { useParams, useLocation } from 'react-router-dom';
import { Sidebar } from '../navigation/Sidebar';
import { Header } from '../navigation/Header';
import { useWorkspace } from '../../features/workspace/WorkspaceContext';

interface AppLayoutProps {
  children: React.ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  const { clientId, periodId } = useParams<{ clientId?: string; periodId?: string }>();
  const location = useLocation();
  const { syncFromParams } = useWorkspace();

  useEffect(() => {
    // Extract clientId and periodId from pathname if not in params
    const clientMatch = location.pathname.match(/\/clients\/([0-9a-fA-F-]+)/);
    const periodMatch = location.pathname.match(/\/periods\/([0-9a-fA-F-]+)/);

    const cId = clientId || (clientMatch ? clientMatch[1] : undefined);
    const pId = periodId || (periodMatch ? periodMatch[1] : undefined);

    if (cId) {
      void syncFromParams(cId, pId);
    }
  }, [location.pathname, clientId, periodId, syncFromParams]);

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: '#f8fafc' }}>
      {/* Left Modern Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          display: 'flex',
          flexDirection: 'column',
          minWidth: 0,
          bgcolor: '#f8fafc',
        }}
      >
        <Header />
        <Box
          key={location.pathname}
          className="animate-fade-in"
          sx={{
            flexGrow: 1,
            p: { xs: 2, sm: 3, md: 4 },
            maxWidth: '1600px',
            width: '100%',
            mx: 'auto',
          }}
        >
          {children}
        </Box>
      </Box>
    </Box>
  );
};
