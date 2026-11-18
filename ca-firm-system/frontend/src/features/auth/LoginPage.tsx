import { useState, type FormEvent } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Container,
  Divider,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { Bolt, LockOpen } from '@mui/icons-material';
import { ApiError } from '../../services/http';
import { useAuth } from './AuthContext';

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setError('Too many attempts. Please wait a minute and try again.');
      } else if (err instanceof ApiError && err.status === 401) {
        setError('Invalid email or password.');
      } else {
        setError('Unable to sign in right now. Please try again.');
      }
      setPassword('');
    } finally {
      setSubmitting(false);
    }
  }

  const fillDemoCredentials = () => {
    setEmail('admin@apex.example');
    setPassword('AdminPassword123!');
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #0b0f19 0%, #1e1b4b 50%, #0f172a 100%)',
        position: 'relative',
        overflow: 'hidden',
        p: 2,
      }}
    >
      {/* Background Decorative Glow Circles */}
      <Box
        sx={{
          position: 'absolute',
          top: '20%',
          left: '15%',
          width: '350px',
          height: '350px',
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(99, 102, 241, 0.25) 0%, rgba(99, 102, 241, 0) 70%)',
          filter: 'blur(50px)',
          pointerEvents: 'none',
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          bottom: '20%',
          right: '15%',
          width: '400px',
          height: '400px',
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(6, 182, 212, 0.2) 0%, rgba(6, 182, 212, 0) 70%)',
          filter: 'blur(60px)',
          pointerEvents: 'none',
        }}
      />

      <Container maxWidth="xs" sx={{ position: 'relative', zIndex: 1 }} className="animate-fade-in">
        <Card
          sx={{
            p: 1,
            borderRadius: '24px',
            background: 'rgba(30, 41, 59, 0.8)',
            backdropFilter: 'blur(16px)',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
          }}
        >
          <CardContent sx={{ p: { xs: 2.5, sm: 3.5 } }}>
            {/* Finora AI Brand Logo */}
            <Stack direction="row" spacing={1.5} alignItems="center" justifyContent="center" sx={{ mb: 2 }}>
              <Box
                component="img"
                src="/finora-logo-dark.png"
                alt="Finora"
                sx={{
                  height: 48,
                  width: 'auto',
                  maxWidth: 220,
                  objectFit: 'contain',
                }}
              />
            </Stack>

            <Typography variant="body2" textAlign="center" sx={{ color: '#cbd5e1', mb: 3 }}>
              Autonomous 4-Agent Pipeline for Chartered Accountants
            </Typography>

            {error && (
              <Alert severity="error" sx={{ mb: 2.5, borderRadius: '10px' }}>
                {error}
              </Alert>
            )}

            <Box component="form" onSubmit={onSubmit} noValidate>
              <Stack spacing={2}>
                <TextField
                  label="Email Address"
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  fullWidth
                  InputProps={{
                    sx: {
                      bgcolor: 'rgba(15, 23, 42, 0.6)',
                      color: '#ffffff',
                      borderRadius: '12px',
                    },
                  }}
                  InputLabelProps={{ sx: { color: '#94a3b8' } }}
                />

                <TextField
                  label="Password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  fullWidth
                  InputProps={{
                    sx: {
                      bgcolor: 'rgba(15, 23, 42, 0.6)',
                      color: '#ffffff',
                      borderRadius: '12px',
                    },
                  }}
                  InputLabelProps={{ sx: { color: '#94a3b8' } }}
                />

                <Button
                  type="submit"
                  variant="contained"
                  size="large"
                  disabled={submitting || !email || !password}
                  startIcon={submitting ? <CircularProgress size={18} color="inherit" /> : <LockOpen />}
                  sx={{
                    py: 1.3,
                    borderRadius: '12px',
                    fontWeight: 700,
                    fontSize: '0.95rem',
                    background: 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
                    boxShadow: '0 8px 20px -4px rgba(99, 102, 241, 0.5)',
                    '&:hover': {
                      background: 'linear-gradient(135deg, #4338ca 0%, #4f46e5 100%)',
                    },
                  }}
                >
                  {submitting ? 'Authenticating...' : 'Sign In to Workspace'}
                </Button>

                <Divider sx={{ my: 1, borderColor: 'rgba(255, 255, 255, 0.1)' }}>
                  <Typography variant="caption" sx={{ color: '#94a3b8', px: 1 }}>
                    QUICK ACCESS
                  </Typography>
                </Divider>

                <Button
                  variant="outlined"
                  size="small"
                  onClick={fillDemoCredentials}
                  startIcon={<Bolt sx={{ color: '#f59e0b' }} />}
                  sx={{
                    color: '#e2e8f0',
                    borderColor: 'rgba(255, 255, 255, 0.2)',
                    bgcolor: 'rgba(255, 255, 255, 0.05)',
                    borderRadius: '10px',
                    textTransform: 'none',
                    py: 0.9,
                    '&:hover': {
                      bgcolor: 'rgba(255, 255, 255, 0.1)',
                      borderColor: '#818cf8',
                    },
                  }}
                >
                  Fill Demo Admin Credentials
                </Button>
              </Stack>
            </Box>
          </CardContent>
        </Card>
      </Container>
    </Box>
  );
}
