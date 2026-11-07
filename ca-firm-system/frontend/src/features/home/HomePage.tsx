import { Stack, Typography } from '@mui/material';
import ProfilePanel from '../auth/ProfilePanel';
import SystemStatus from '../system/SystemStatus';

export default function HomePage() {
  return (
    <Stack spacing={3}>
      <ProfilePanel />
      <Typography variant="body2" color="text.secondary">
        Open <strong>Clients</strong> to select a client and accounting period and manage its files.
      </Typography>
      <SystemStatus />
    </Stack>
  );
}
