import {
  Alert,
  Breadcrumbs,
  Button,
  Chip,
  CircularProgress,
  Link,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { Can } from '../auth/Can';
import { formatBytes, formatDate } from '../clients/format';
import { getClient, listPeriods } from '../../services/clientsApi';
import {
  deleteDocument,
  downloadDocument,
  listDocuments,
  uploadDocument,
} from '../../services/documentsApi';
import { ApiError } from '../../services/http';
import type { Client, Page, Period } from '../../types/clients';
import {
  DOCUMENT_CATEGORIES,
  type DocumentCategory,
  type DocumentRecord,
  type DocumentStatus,
} from '../../types/documents';

const PAGE_SIZE = 10;
const POLL_MS = 5000;
const STATUS_LABEL: Record<DocumentStatus, string> = {
  uploaded: 'Uploaded',
  queued: 'Queued for processing',
  processing: 'Processing',
  processed: 'Processed',
  failed: 'Processing failed',
};
const STATUS_COLOR: Record<DocumentStatus, 'default' | 'info' | 'warning' | 'success' | 'error'> = {
  uploaded: 'default',
  queued: 'info',
  processing: 'warning',
  processed: 'success',
  failed: 'error',
};
const CATEGORY_LABEL = Object.fromEntries(DOCUMENT_CATEGORIES) as Record<string, string>;
const ACCEPT = '.pdf,.xlsx,.xls,.csv,.png,.jpg,.jpeg';

type Notice = { severity: 'success' | 'error' | 'warning'; text: string };

export default function DocumentsPage() {
  const { clientId = '', periodId = '' } = useParams();
  const [client, setClient] = useState<Client | null>(null);
  const [period, setPeriod] = useState<Period | null>(null);
  const [data, setData] = useState<Page<DocumentRecord> | null>(null);
  const [page, setPage] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState<DocumentCategory>('bank_statement');
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    Promise.all([getClient(clientId), listPeriods(clientId)])
      .then(([c, ps]) => {
        setClient(c);
        const p = ps.find((x) => x.id === periodId) ?? null;
        if (!p) setLoadError('Accounting period not found.');
        setPeriod(p);
      })
      .catch(() => setLoadError('Client or period not found.'));
  }, [clientId, periodId]);

  const refresh = useCallback(
    () =>
      listDocuments(clientId, periodId, { limit: PAGE_SIZE, offset: page * PAGE_SIZE })
        .then(setData)
        .catch(() => setLoadError('Failed to load documents.')),
    [clientId, periodId, page],
  );
  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll while anything is still moving through processing so status stays current.
  const inFlight =
    data?.items.some((d) => d.status !== 'processed' && d.status !== 'failed') ?? false;
  useEffect(() => {
    if (!inFlight) return;
    const t = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(t);
  }, [inFlight, refresh]);

  async function onUpload(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setNotice(null);
    try {
      const doc = await uploadDocument(clientId, periodId, file, category);
      setNotice({ severity: 'success', text: `“${doc.original_filename}” uploaded.` });
      setFile(null);
      if (fileInput.current) fileInput.current.value = '';
      setPage(0);
      await refresh();
    } catch (err) {
      if (err instanceof ApiError && err.body.code === 'duplicate_document') {
        setNotice({
          severity: 'warning',
          text: `This exact file was already uploaded${err.body.existing_filename ? ` as “${String(err.body.existing_filename)}”` : ''}. Nothing was changed.`,
        });
      } else {
        setNotice({
          severity: 'error',
          text: err instanceof Error ? err.message : 'Upload failed',
        });
      }
    } finally {
      setUploading(false);
    }
  }

  async function onDownload(d: DocumentRecord) {
    try {
      await downloadDocument(clientId, periodId, d);
    } catch (err) {
      setNotice({
        severity: 'error',
        text: err instanceof Error ? err.message : 'Download failed',
      });
    }
  }

  async function onDelete(d: DocumentRecord) {
    if (
      !window.confirm(
        `Remove “${d.original_filename}”? The original is retained for audit purposes.`,
      )
    )
      return;
    try {
      await deleteDocument(clientId, periodId, d.id);
      setNotice({ severity: 'success', text: `“${d.original_filename}” removed.` });
      await refresh();
    } catch (err) {
      setNotice({ severity: 'error', text: err instanceof Error ? err.message : 'Remove failed' });
    }
  }

  if (loadError) return <Alert severity="error">{loadError}</Alert>;
  if (!client || !period) return <CircularProgress aria-label="Loading period" />;
  const canUpload = period.status === 'open' && client.status === 'active';

  return (
    <Stack spacing={3}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/clients" underline="hover">
          Clients
        </Link>
        <Link component={RouterLink} to={`/clients/${clientId}`} underline="hover">
          {client.name}
        </Link>
        <Typography color="text.primary">{period.label}</Typography>
      </Breadcrumbs>

      <Paper sx={{ p: 3 }}>
        <Typography variant="h5" component="h2">
          {period.label} documents
        </Typography>
        <Typography color="text.secondary">
          {formatDate(period.start_date)} – {formatDate(period.end_date)} ·{' '}
          <Chip
            size="small"
            label={period.status}
            color={period.status === 'open' ? 'success' : 'default'}
          />
        </Typography>
      </Paper>

      <Can permission="document:upload">
        <Paper sx={{ p: 3 }} component="form" onSubmit={onUpload}>
          <Typography variant="h6" component="h3" gutterBottom>
            Upload a file
          </Typography>
          {!canUpload && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Uploads are disabled because this period is closed or the client is archived.
            </Alert>
          )}
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
            <TextField
              select
              size="small"
              label="Document type"
              value={category}
              onChange={(e) => setCategory(e.target.value as DocumentCategory)}
              sx={{ minWidth: 210 }}
            >
              {DOCUMENT_CATEGORIES.map(([value, label]) => (
                <MenuItem key={value} value={value}>
                  {label}
                </MenuItem>
              ))}
            </TextField>
            <Button component="label" variant="outlined" disabled={!canUpload || uploading}>
              {file ? file.name : 'Choose file'}
              <input
                ref={fileInput}
                hidden
                type="file"
                accept={ACCEPT}
                aria-label="File"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </Button>
            <Button type="submit" variant="contained" disabled={!file || !canUpload || uploading}>
              {uploading ? 'Uploading…' : 'Upload'}
            </Button>
          </Stack>
          <Typography variant="caption" color="text.secondary" display="block" mt={1}>
            Excel, CSV, PDF or image files up to 50 MB. Originals are stored unchanged.
          </Typography>
        </Paper>
      </Can>

      {notice && (
        <Alert severity={notice.severity} onClose={() => setNotice(null)}>
          {notice.text}
        </Alert>
      )}

      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" component="h3" gutterBottom>
          Files
        </Typography>
        {!data && <CircularProgress aria-label="Loading documents" />}
        {data && data.items.length === 0 && (
          <Alert severity="info">No files uploaded for this period yet.</Alert>
        )}
        {data && data.items.length > 0 && (
          <>
            <Table size="small" aria-label="Documents">
              <TableHead>
                <TableRow>
                  <TableCell>File</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Size</TableCell>
                  <TableCell>Uploaded</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {data.items.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell sx={{ wordBreak: 'break-word' }}>{d.original_filename}</TableCell>
                    <TableCell>{CATEGORY_LABEL[d.category] ?? d.category}</TableCell>
                    <TableCell>{formatBytes(d.size_bytes)}</TableCell>
                    <TableCell>
                      {formatDate(d.created_at)}
                      {d.uploaded_by_email ? ` · ${d.uploaded_by_email}` : ''}
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        label={STATUS_LABEL[d.status]}
                        color={STATUS_COLOR[d.status]}
                      />
                    </TableCell>
                    <TableCell align="right">
                      <Button size="small" onClick={() => void onDownload(d)}>
                        Download
                      </Button>
                      <Can permission="document:delete">
                        {period.status === 'open' && (
                          <Button size="small" color="error" onClick={() => void onDelete(d)}>
                            Remove
                          </Button>
                        )}
                      </Can>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <TablePagination
              component="div"
              count={data.total}
              page={page}
              onPageChange={(_, p) => setPage(p)}
              rowsPerPage={PAGE_SIZE}
              rowsPerPageOptions={[PAGE_SIZE]}
            />
          </>
        )}
      </Paper>
    </Stack>
  );
}
