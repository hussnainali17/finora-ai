import React, { useState } from 'react';
import {
  Box,
  Drawer,
  IconButton,
  Tabs,
  Tab,
  Typography,
  Stack,
  Chip,
  Card,
  CardContent,
  Button,
  CircularProgress,
} from '@mui/material';
import {
  Close,
  CloudUpload,
  FactCheck,
  Balance,
  Assessment,
  Warning,
  ErrorOutline,
} from '@mui/icons-material';
import type { ContextSnapshot } from '../../types/caReview';

interface Props {
  open: boolean;
  onClose: () => void;
  context: ContextSnapshot | null;
  loading: boolean;
  onInsertReference: (refText: string) => void;
}

export const ContextDrawer: React.FC<Props> = ({
  open,
  onClose,
  context,
  loading,
  onInsertReference,
}) => {
  const [tabIndex, setTabIndex] = useState(0);

  const formatPkr = (val: number | null | undefined) => {
    if (val === null || val === undefined || isNaN(val)) return '—';
    return `PKR ${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: {
          width: { xs: '100%', sm: 460 },
          bgcolor: '#0f172a',
          color: '#f8fafc',
          borderLeft: '1px solid rgba(255, 255, 255, 0.1)',
          display: 'flex',
          flexDirection: 'column',
        },
      }}
    >
      {/* Drawer Header */}
      <Box sx={{ p: 2, borderBottom: '1px solid rgba(255, 255, 255, 0.08)', bgcolor: '#1e293b' }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Box>
            <Typography variant="subtitle1" fontWeight={700} sx={{ color: '#f8fafc' }}>
              Project Data & Agent Outputs
            </Typography>
            <Typography variant="caption" sx={{ color: '#94a3b8' }}>
              Live pipeline context across all 4 autonomous agents
            </Typography>
          </Box>
          <IconButton size="small" onClick={onClose} sx={{ color: '#94a3b8' }}>
            <Close fontSize="small" />
          </IconButton>
        </Stack>

        {/* Navigation Tabs */}
        <Tabs
          value={tabIndex}
          onChange={(_, val) => setTabIndex(val)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{
            mt: 1.5,
            minHeight: 38,
            '& .MuiTab-root': {
              minHeight: 38,
              py: 0.5,
              px: 1.5,
              fontSize: '0.75rem',
              fontWeight: 600,
              color: '#94a3b8',
              textTransform: 'none',
              '&.Mui-selected': { color: '#38bdf8' },
            },
            '& .MuiTabs-indicator': { bgcolor: '#38bdf8' },
          }}
        >
          <Tab icon={<CloudUpload sx={{ fontSize: 16 }} />} iconPosition="start" label="1. Intake" />
          <Tab icon={<FactCheck sx={{ fontSize: 16 }} />} iconPosition="start" label="2. Review" />
          <Tab icon={<Balance sx={{ fontSize: 16 }} />} iconPosition="start" label="3. Adjustments" />
          <Tab icon={<Assessment sx={{ fontSize: 16 }} />} iconPosition="start" label="4. Reports" />
        </Tabs>
      </Box>

      {/* Drawer Content */}
      <Box sx={{ p: 2, flexGrow: 1, overflowY: 'auto' }}>
        {loading ? (
          <Box display="flex" justifyContent="center" alignItems="center" height="200px">
            <CircularProgress size={28} sx={{ color: '#38bdf8' }} />
          </Box>
        ) : !context ? (
          <Typography variant="body2" sx={{ color: '#94a3b8', textAlign: 'center', mt: 4 }}>
            No agent context available for this period.
          </Typography>
        ) : (
          <>
            {/* TAB 0: Intake & OCR (Agent 1) */}
            {tabIndex === 0 && (
              <Stack spacing={2}>
                <Box>
                  <Typography variant="caption" fontWeight={700} sx={{ color: '#38bdf8', letterSpacing: '0.05em' }}>
                    UPLOADED SOURCE DOCUMENTS ({context.documents.length})
                  </Typography>
                  <Stack spacing={1} sx={{ mt: 1 }}>
                    {context.documents.map((doc) => (
                      <Card key={doc.id} sx={{ bgcolor: 'rgba(30, 41, 59, 0.7)', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
                        <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                          <Stack direction="row" justifyContent="space-between" alignItems="center">
                            <Box sx={{ overflow: 'hidden', pr: 1 }}>
                              <Typography variant="body2" fontWeight={600} noWrap sx={{ color: '#f1f5f9' }}>
                                {doc.filename}
                              </Typography>
                              <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                                Category: {doc.category} • Status: {doc.status}
                              </Typography>
                            </Box>
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={() => onInsertReference(`Document: ${doc.filename}`)}
                              sx={{
                                minWidth: 'auto',
                                px: 1,
                                py: 0.3,
                                fontSize: '0.7rem',
                                color: '#38bdf8',
                                borderColor: 'rgba(56, 189, 248, 0.3)',
                              }}
                            >
                              Cite
                            </Button>
                          </Stack>
                        </CardContent>
                      </Card>
                    ))}
                  </Stack>
                </Box>

                <Box sx={{ mt: 2 }}>
                  <Typography variant="caption" fontWeight={700} sx={{ color: '#38bdf8', letterSpacing: '0.05em' }}>
                    EXTRACTED DATA TABLES ({context.tables.length})
                  </Typography>
                  <Stack spacing={1} sx={{ mt: 1 }}>
                    {context.tables.map((t) => (
                      <Card key={t.id} sx={{ bgcolor: 'rgba(30, 41, 59, 0.7)', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
                        <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                          <Stack direction="row" justifyContent="space-between" alignItems="center">
                            <Box>
                              <Typography variant="body2" fontWeight={600} sx={{ color: '#f1f5f9' }}>
                                {t.name}
                              </Typography>
                              <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                                Type: {t.type} • {t.n_rows} rows • {t.columns.length} columns
                              </Typography>
                            </Box>
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={() => onInsertReference(`Table '${t.name}' (${t.type})`)}
                              sx={{
                                minWidth: 'auto',
                                px: 1,
                                py: 0.3,
                                fontSize: '0.7rem',
                                color: '#818cf8',
                                borderColor: 'rgba(129, 140, 248, 0.3)',
                              }}
                            >
                              Cite
                            </Button>
                          </Stack>
                        </CardContent>
                      </Card>
                    ))}
                  </Stack>
                </Box>
              </Stack>
            )}

            {/* TAB 1: Accounting Review (Agent 2) */}
            {tabIndex === 1 && (
              <Stack spacing={2}>
                <Box>
                  <Typography variant="caption" fontWeight={700} sx={{ color: '#a78bfa', letterSpacing: '0.05em' }}>
                    ANOMALY & RECONCILIATION FINDINGS ({context.review_findings.length})
                  </Typography>
                  <Stack spacing={1} sx={{ mt: 1 }}>
                    {context.review_findings.map((f) => (
                      <Card key={f.id} sx={{ bgcolor: 'rgba(30, 41, 59, 0.7)', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
                        <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                          <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                            <Box sx={{ pr: 1 }}>
                              <Stack direction="row" spacing={0.8} alignItems="center">
                                {f.severity === 'error' ? (
                                  <ErrorOutline sx={{ fontSize: 16, color: '#f43f5e' }} />
                                ) : (
                                  <Warning sx={{ fontSize: 16, color: '#f59e0b' }} />
                                )}
                                <Typography variant="body2" fontWeight={600} sx={{ color: '#f1f5f9' }}>
                                  {f.title}
                                </Typography>
                              </Stack>
                              <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mt: 0.5 }}>
                                Module: {f.module} • {formatPkr(f.amount)} • Status: {f.status}
                              </Typography>
                              <Typography variant="caption" sx={{ color: '#cbd5e1', display: 'block', mt: 0.5 }}>
                                {f.description}
                              </Typography>
                            </Box>
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={() => onInsertReference(`Finding '${f.title}' (${f.module})`)}
                              sx={{
                                minWidth: 'auto',
                                px: 1,
                                py: 0.3,
                                fontSize: '0.7rem',
                                color: '#a78bfa',
                                borderColor: 'rgba(167, 139, 250, 0.3)',
                              }}
                            >
                              Cite
                            </Button>
                          </Stack>
                        </CardContent>
                      </Card>
                    ))}
                  </Stack>
                </Box>
              </Stack>
            )}

            {/* TAB 2: Period Adjustments (Agent 3) */}
            {tabIndex === 2 && (
              <Stack spacing={2}>
                <Box>
                  <Typography variant="caption" fontWeight={700} sx={{ color: '#f59e0b', letterSpacing: '0.05em' }}>
                    PERIOD-END ADJUSTMENTS ({context.period_adjustments.length})
                  </Typography>
                  <Stack spacing={1} sx={{ mt: 1 }}>
                    {context.period_adjustments.map((adj) => (
                      <Card key={adj.id} sx={{ bgcolor: 'rgba(30, 41, 59, 0.7)', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
                        <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                          <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                            <Box sx={{ pr: 1 }}>
                              <Stack direction="row" spacing={1} alignItems="center">
                                <Chip
                                  label={adj.category.toUpperCase()}
                                  size="small"
                                  sx={{ height: 20, fontSize: '0.65rem', bgcolor: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24' }}
                                />
                                <Typography variant="body2" fontWeight={700} sx={{ color: '#f1f5f9' }}>
                                  {formatPkr(adj.amount)}
                                </Typography>
                              </Stack>
                              <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mt: 0.5 }}>
                                Dr: {adj.debit_account_name} ➔ Cr: {adj.credit_account_name}
                              </Typography>
                              <Typography variant="caption" sx={{ color: '#cbd5e1', display: 'block', mt: 0.5 }}>
                                {adj.accounting_rationale}
                              </Typography>
                            </Box>
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={() => onInsertReference(`Adjustment for ${adj.category}: ${formatPkr(adj.amount)}`)}
                              sx={{
                                minWidth: 'auto',
                                px: 1,
                                py: 0.3,
                                fontSize: '0.7rem',
                                color: '#f59e0b',
                                borderColor: 'rgba(245, 158, 11, 0.3)',
                              }}
                            >
                              Cite
                            </Button>
                          </Stack>
                        </CardContent>
                      </Card>
                    ))}
                  </Stack>
                </Box>
              </Stack>
            )}

            {/* TAB 3: Financial Statements (Agent 4) */}
            {tabIndex === 3 && (
              <Stack spacing={2}>
                <Box>
                  <Typography variant="caption" fontWeight={700} sx={{ color: '#10b981', letterSpacing: '0.05em' }}>
                    FINANCIAL REPORTS & TRIAL BALANCE
                  </Typography>

                  {/* TB Summary Card */}
                  <Card sx={{ mt: 1, bgcolor: 'rgba(30, 41, 59, 0.7)', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
                    <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                      <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Box>
                          <Typography variant="body2" fontWeight={700} sx={{ color: '#f1f5f9' }}>
                            Trial Balance Status
                          </Typography>
                          <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                            Debits: {formatPkr(context.summary.trial_balance.total_debits)} • Credits: {formatPkr(context.summary.trial_balance.total_credits)}
                          </Typography>
                        </Box>
                        <Chip
                          label={context.summary.trial_balance.is_balanced ? 'BALANCED' : 'UNBALANCED'}
                          size="small"
                          color={context.summary.trial_balance.is_balanced ? 'success' : 'error'}
                          sx={{ fontWeight: 700, fontSize: '0.7rem' }}
                        />
                      </Stack>
                    </CardContent>
                  </Card>

                  {/* Reports List */}
                  <Stack spacing={1} sx={{ mt: 1.5 }}>
                    {context.financial_reports.map((rep) => (
                      <Card key={rep.id} sx={{ bgcolor: 'rgba(30, 41, 59, 0.7)', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
                        <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                          <Stack direction="row" justifyContent="space-between" alignItems="center">
                            <Box>
                              <Typography variant="body2" fontWeight={600} sx={{ color: '#f1f5f9', textTransform: 'capitalize' }}>
                                {rep.report_type.replace(/_/g, ' ')}
                              </Typography>
                              <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                                Status: {rep.status}
                              </Typography>
                            </Box>
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={() => onInsertReference(`Report '${rep.report_type.replace(/_/g, ' ')}'`)}
                              sx={{
                                minWidth: 'auto',
                                px: 1,
                                py: 0.3,
                                fontSize: '0.7rem',
                                color: '#10b981',
                                borderColor: 'rgba(16, 185, 129, 0.3)',
                              }}
                            >
                              Cite
                            </Button>
                          </Stack>
                        </CardContent>
                      </Card>
                    ))}
                  </Stack>
                </Box>
              </Stack>
            )}
          </>
        )}
      </Box>
    </Drawer>
  );
};
