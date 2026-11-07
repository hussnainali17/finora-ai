import { Chip, Paper, Stack, Typography } from '@mui/material';
import { useAuth } from './AuthContext';

const ROLE_LABELS: Record<string, string> = {
  firm_admin: 'Firm Admin',
  ca_reviewer: 'CA / Reviewer',
  accountant: 'Accountant / Staff',
  client_user: 'Client User (read-only)',
};

export default function ProfilePanel() {
  const { state } = useAuth();
  if (state.status !== 'authenticated') return null;
  const { user } = state;
  return (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h6" component="h2" gutterBottom>
        Your access
      </Typography>
      <Typography>{user.full_name}</Typography>
      <Typography variant="body2" color="text.secondary" gutterBottom>
        {user.email} · {user.firm_name}
      </Typography>
      <Chip
        color="primary"
        size="small"
        label={ROLE_LABELS[user.role] ?? user.role}
        sx={{ mb: 2 }}
      />
      <Typography variant="subtitle2" gutterBottom>
        Permissions
      </Typography>
      <Stack direction="row" flexWrap="wrap" gap={0.5}>
        {user.permissions.map((p) => (
          <Chip key={p} size="small" variant="outlined" label={p} />
        ))}
      </Stack>
    </Paper>
  );
}
