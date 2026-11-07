import {
  Alert,
  Breadcrumbs,
  Button,
  Chip,
  CircularProgress,
  FormControlLabel,
  Link,
  MenuItem,
  Paper,
  Stack,
  Switch,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useState } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import {
  getExtraction,
  listExtractedRows,
  listFindings,
  rerunExtraction,
  setColumnRole,
  setTableType,
  updateFinding,
} from '../../services/extractionApi';
import { ApiError } from '../../services/http';
import type { Page } from '../../types/clients';
import {
  COLUMN_ROLES,
  TABLE_TYPES,
  type ExtractedRowRecord,
  type Extraction,
  type ExtractionTable,
  type Finding,
} from '../../types/extraction';

const ROWS_PER_PAGE = 25;
const POLL_MS = 4000;
const ROLE_LABEL = Object.fromEntries(COLUMN_ROLES) as Record<string, string>;
const SEVERITY_COLOR = { error: 'error', warning: 'warning', info: 'info' } as const;
const msg = (e: unknown) => (e instanceof ApiError ? e.message : 'Something went wrong');

export default function ReviewPage() {
  const { clientId = '', periodId = '', documentId = '' } = useParams();
  const { can } = useAuth();
  const canReview = can('extraction:review');
  const canRun = can('extraction:run');

  const [data, setData] = useState<Extraction | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState(0);
  const [rows, setRows] = useState<Page<ExtractedRowRecord> | null>(null);
  const [rowPage, setRowPage] = useState(0);
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const ext = await getExtraction(clientId, periodId, documentId);
      setData(ext);
      setFindings(
        ext.run?.status === 'completed' ? await listFindings(clientId, periodId, documentId) : [],
      );
      setError(null);
    } catch (e) {
      setError(msg(e));
    }
  }, [clientId, periodId, documentId]);

  useEffect(() => {
    void load();
  }, [load]);

  const pending =
    data !== null && ['uploaded', 'queued', 'processing'].includes(data.document_status);
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(t);
  }, [pending, load]);

  const table: ExtractionTable | undefined = data?.tables[selected];
  const tableId = table?.id;

  useEffect(() => {
    if (!tableId) {
      setRows(null);
      return;
    }
    let cancelled = false;
    listExtractedRows(clientId, periodId, documentId, tableId, {
      limit: ROWS_PER_PAGE,
      offset: rowPage * ROWS_PER_PAGE,
      flaggedOnly,
    })
      .then((r) => !cancelled && setRows(r))
      .catch((e) => !cancelled && setError(msg(e)));
    return () => {
      cancelled = true;
    };
  }, [clientId, periodId, documentId, tableId, rowPage, flaggedOnly, data]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(msg(e));
    } finally {
      setBusy(false);
    }
  }

  const tableFindings = findings.filter((f) => f.table_id === tableId || f.table_id === null);
  const openCount = findings.filter((f) => f.status === 'open').length;

  return (
    <Stack spacing={2}>
      <Breadcrumbs aria-label="Breadcrumb">
        <Link
          component={RouterLink}
          to={`/clients/${clientId}/periods/${periodId}`}
          underline="hover"
        >
          Documents
        </Link>
        <Typography color="text.primary">Review extracted data</Typography>
      </Breadcrumbs>
      <Typography variant="h5" component="h2">
        Review extracted data
      </Typography>

      {error && <Alert severity="error">{error}</Alert>}
      {!data && !error && <CircularProgress aria-label="Loading extraction" />}

      {data && pending && (
        <Alert severity="info">
          Extraction is {data.document_status}. This page updates automatically.
        </Alert>
      )}
      {data && !pending && data.run === null && (
        <Alert severity="warning">This document has not been extracted yet.</Alert>
      )}
      {data?.run?.status === 'failed' && (
        <Alert severity="error">
          Extraction failed: {data.run.error_message ?? 'unknown error'} ({data.run.error_code})
        </Alert>
      )}

      {data?.run && (
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Chip size="small" label={`Run ${data.run.version}`} />
          {data.run.llm_used && <Chip size="small" color="info" label="AI-assisted suggestions" />}
          <Chip
            size="small"
            color={openCount ? 'warning' : 'success'}
            label={`${openCount} open finding${openCount === 1 ? '' : 's'}`}
          />
          {canRun && !pending && (
            <Button
              size="small"
              disabled={busy}
              onClick={() => void act(() => rerunExtraction(clientId, periodId, documentId))}
            >
              Re-run extraction
            </Button>
          )}
        </Stack>
      )}

      {data && data.tables.length > 0 && (
        <Paper sx={{ p: 2 }}>
          <Tabs
            value={selected}
            onChange={(_, v: number) => {
              setSelected(v);
              setRowPage(0);
            }}
            variant="scrollable"
            aria-label="Extracted tables"
          >
            {data.tables.map((t) => (
              <Tab key={t.id} label={`${t.name}${t.status === 'needs_review' ? ' •' : ''}`} />
            ))}
          </Tabs>

          {table && (
            <Stack spacing={3} mt={2}>
              <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
                <TextField
                  select
                  size="small"
                  label="Document type"
                  value={table.effective_type}
                  disabled={!canReview || busy}
                  onChange={(e) =>
                    void act(() =>
                      setTableType(clientId, periodId, documentId, table.id, e.target.value),
                    )
                  }
                  sx={{ minWidth: 240 }}
                >
                  {TABLE_TYPES.map(([v, l]) => (
                    <MenuItem key={v} value={v}>
                      {l}
                    </MenuItem>
                  ))}
                </TextField>
                <Chip
                  size="small"
                  color={table.status === 'ok' ? 'success' : 'warning'}
                  label={table.status === 'ok' ? 'Ready' : 'Needs review'}
                />
                {table.currency && <Chip size="small" label={`Currency ${table.currency}`} />}
                {table.period_end && <Chip size="small" label={`Period end ${table.period_end}`} />}
                {!table.confirmed_type && (
                  <Typography variant="caption" color="text.secondary">
                    Detected {Math.round(table.type_confidence * 100)}% ({table.type_source})
                  </Typography>
                )}
              </Stack>

              <div>
                <Typography variant="subtitle1" component="h3" gutterBottom>
                  Column mapping
                </Typography>
                <Table size="small" aria-label="Column mapping">
                  <TableHead>
                    <TableRow>
                      <TableCell>Column</TableCell>
                      <TableCell>Suggested</TableCell>
                      <TableCell>Role</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {table.columns.map((c) => {
                      const label = c.header ?? `Column ${c.letter ?? c.col_index + 1}`;
                      return (
                        <TableRow key={c.col_index}>
                          <TableCell>{label}</TableCell>
                          <TableCell>
                            {ROLE_LABEL[c.suggested_role] ?? c.suggested_role} ·{' '}
                            {Math.round(c.confidence * 100)}%{c.role_source === 'llm' && ' · AI'}
                          </TableCell>
                          <TableCell>
                            <TextField
                              select
                              size="small"
                              value={c.effective_role}
                              disabled={!canReview || busy}
                              slotProps={{ htmlInput: { 'aria-label': `Role for ${label}` } }}
                              onChange={(e) =>
                                void act(() =>
                                  setColumnRole(
                                    clientId,
                                    periodId,
                                    documentId,
                                    table.id,
                                    c.col_index,
                                    e.target.value,
                                  ),
                                )
                              }
                              sx={{ minWidth: 200 }}
                            >
                              {COLUMN_ROLES.map(([v, l]) => (
                                <MenuItem key={v} value={v}>
                                  {l}
                                </MenuItem>
                              ))}
                            </TextField>
                            {c.confirmed_role && (
                              <Chip size="small" sx={{ ml: 1 }} label="Confirmed" color="success" />
                            )}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>

              <div>
                <Typography variant="subtitle1" component="h3" gutterBottom>
                  Findings
                </Typography>
                {tableFindings.length === 0 ? (
                  <Typography color="text.secondary">No findings.</Typography>
                ) : (
                  <Stack spacing={1}>
                    {tableFindings.map((f) => (
                      <Stack key={f.id} direction="row" spacing={1} alignItems="center">
                        <Chip size="small" color={SEVERITY_COLOR[f.severity]} label={f.severity} />
                        <Typography sx={{ flexGrow: 1 }} variant="body2">
                          {f.message}
                          {f.status !== 'open' && ` (${f.status})`}
                        </Typography>
                        {canReview && f.status === 'open' && (
                          <>
                            <Button
                              size="small"
                              disabled={busy}
                              onClick={() =>
                                void act(() =>
                                  updateFinding(clientId, periodId, documentId, f.id, 'resolved'),
                                )
                              }
                            >
                              Resolve
                            </Button>
                            {f.severity !== 'error' && (
                              <Button
                                size="small"
                                color="inherit"
                                disabled={busy}
                                onClick={() =>
                                  void act(() =>
                                    updateFinding(
                                      clientId,
                                      periodId,
                                      documentId,
                                      f.id,
                                      'dismissed',
                                    ),
                                  )
                                }
                              >
                                Dismiss
                              </Button>
                            )}
                          </>
                        )}
                        {canReview && f.status !== 'open' && (
                          <Button
                            size="small"
                            disabled={busy}
                            onClick={() =>
                              void act(() =>
                                updateFinding(clientId, periodId, documentId, f.id, 'open'),
                              )
                            }
                          >
                            Reopen
                          </Button>
                        )}
                      </Stack>
                    ))}
                  </Stack>
                )}
              </div>

              <div>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="subtitle1" component="h3">
                    Data preview (original → normalized)
                  </Typography>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={flaggedOnly}
                        onChange={(e) => {
                          setFlaggedOnly(e.target.checked);
                          setRowPage(0);
                        }}
                      />
                    }
                    label="Flagged rows only"
                  />
                </Stack>
                <div style={{ overflowX: 'auto' }}>
                  <Table size="small" aria-label="Extracted rows">
                    <TableHead>
                      <TableRow>
                        <TableCell>Row</TableCell>
                        {table.columns.map((c) => (
                          <TableCell key={c.col_index}>
                            {c.header ?? `Column ${c.letter}`}
                            <Typography variant="caption" display="block" color="text.secondary">
                              {ROLE_LABEL[c.effective_role] ?? c.effective_role}
                            </Typography>
                          </TableCell>
                        ))}
                        <TableCell>Flags</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {rows?.items.map((r) => (
                        <TableRow key={r.row_index} selected={r.flags.length > 0}>
                          <TableCell>{r.row_index}</TableCell>
                          {table.columns.map((c) => {
                            const raw = r.raw[String(c.col_index)]?.v ?? '';
                            const norm = r.normalized[String(c.col_index)];
                            return (
                              <TableCell key={c.col_index}>
                                {norm ?? (raw ? '—' : '')}
                                {raw !== '' && raw !== norm && (
                                  <Typography
                                    variant="caption"
                                    display="block"
                                    color="text.secondary"
                                  >
                                    {raw}
                                  </Typography>
                                )}
                              </TableCell>
                            );
                          })}
                          <TableCell>
                            {r.flags.map((f, i) => (
                              <Chip
                                key={i}
                                size="small"
                                title={f.message}
                                label={f.code}
                                sx={{ mr: 0.5 }}
                              />
                            ))}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                {rows && (
                  <TablePagination
                    component="div"
                    count={rows.total}
                    page={rowPage}
                    onPageChange={(_, p) => setRowPage(p)}
                    rowsPerPage={ROWS_PER_PAGE}
                    rowsPerPageOptions={[ROWS_PER_PAGE]}
                  />
                )}
              </div>
            </Stack>
          )}
        </Paper>
      )}
    </Stack>
  );
}
