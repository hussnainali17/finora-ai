import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  Grid,
  IconButton,
  InputLabel,
  Link,
  MenuItem,
  Paper,
  Select,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  CloudUpload as UploadIcon,
  Warning as WarningIcon,
  Share as ShareIcon,
  AccountBalance as AccountingIcon,
  ReceiptLong as TaxIcon,
  FactCheck as AuditIcon,
} from '@mui/icons-material';
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { Can } from '../auth/Can';
import { formatBytes, formatDate } from '../clients/format';
import { getClient, listPeriods } from '../../services/clientsApi';
import {
  deleteDocument,
  downloadDocument,
  listDocuments,
  shareDocumentWithModule,
  uploadDocument,
  uploadMultipleDocuments,
} from '../../services/documentsApi';
import { ApiError } from '../../services/http';
import type { Client, Page, Period } from '../../types/clients';
import {
  ACCOUNTING_CATEGORIES,
  AUDIT_CATEGORIES,
  MODULE_CATEGORIES,
  TAXATION_CATEGORIES,
  type DocumentCategory,
  type DocumentRecord,
  type DocumentStatus,
  type ModuleType,
} from '../../types/documents';

const PAGE_SIZE = 10;
const POLL_MS = 5000;
const STATUS_LABEL: Record<DocumentStatus, string> = {
  uploaded: 'Uploaded',
  queued: 'Queued for processing',
  processing: 'Processing OCR & extraction',
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

// Flattened category label map
const ALL_LABELS = Object.fromEntries([
  ...ACCOUNTING_CATEGORIES,
  ...TAXATION_CATEGORIES,
  ...AUDIT_CATEGORIES,
]);

const ACCEPT = '.pdf,.xlsx,.xls,.csv,.png,.jpg,.jpeg';

type Notice = { severity: 'success' | 'error' | 'warning' | 'info'; text: string };

export default function DocumentsPage() {
  const { clientId = '', periodId = '' } = useParams();
  const [client, setClient] = useState<Client | null>(null);
  const [period, setPeriod] = useState<Period | null>(null);
  const [data, setData] = useState<Page<DocumentRecord> | null>(null);
  const [page, setPage] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  // Central Upload Form State
  const [uploadModule, setUploadModule] = useState<ModuleType>('accounting');
  const [category, setCategory] = useState<DocumentCategory>('bank_statement');
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  // List View Filter State
  const [activeTab, setActiveTab] = useState<'all' | 'accounting' | 'taxation' | 'audit'>('all');
  const [mismatchesOnly, setMismatchesOnly] = useState(false);

  // Share Dialog State
  const [shareDoc, setShareDoc] = useState<DocumentRecord | null>(null);
  const [shareTargetModule, setShareTargetModule] = useState<ModuleType>('taxation');
  const [shareNotes, setShareNotes] = useState('');
  const [sharing, setSharing] = useState(false);

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

  // Keep category in sync when upload module changes
  useEffect(() => {
    const defaultCat = MODULE_CATEGORIES[uploadModule][0][0];
    setCategory(defaultCat);
  }, [uploadModule]);

  const refresh = useCallback(
    () =>
      listDocuments(clientId, periodId, {
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        module: activeTab,
      })
        .then(setData)
        .catch(() => setLoadError('Failed to load documents.')),
    [clientId, periodId, page, activeTab],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll while any document is being processed
  const inFlight =
    data?.items.some((d) => d.status !== 'processed' && d.status !== 'failed') ?? false;
  useEffect(() => {
    if (!inFlight) return;
    const t = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(t);
  }, [inFlight, refresh]);

  async function onUpload(e: FormEvent) {
    e.preventDefault();
    if (files.length === 0) return;
    setUploading(true);
    setNotice(null);

    try {
      if (files.length === 1) {
        const doc = await uploadDocument(clientId, periodId, files[0], category, uploadModule);
        setNotice({
          severity: 'success',
          text: `“${doc.original_filename}” uploaded to ${uploadModule.toUpperCase()} under ${ALL_LABELS[doc.category] || doc.category}. Processing via Central Document Intelligence.`,
        });
      } else {
        const batch = await uploadMultipleDocuments(
          clientId,
          periodId,
          files,
          category,
          uploadModule,
        );
        setNotice({
          severity: batch.total_failed > 0 ? 'warning' : 'success',
          text: `Uploaded ${batch.total_uploaded} file(s) to ${uploadModule.toUpperCase()}.${
            batch.total_failed > 0 ? ` ${batch.total_failed} file(s) failed.` : ''
          }`,
        });
      }
      setFiles([]);
      if (fileInput.current) fileInput.current.value = '';
      setPage(0);
      await refresh();
    } catch (err) {
      if (err instanceof ApiError && err.body.code === 'duplicate_document') {
        setNotice({
          severity: 'warning',
          text: `This exact file was already uploaded${
            err.body.existing_filename ? ` as “${String(err.body.existing_filename)}”` : ''
          }. Duplicates are rejected within the same client period.`,
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
        `Remove “${d.original_filename}”? The original is retained in audit storage.`,
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

  async function handleShareSubmit() {
    if (!shareDoc) return;
    setSharing(true);
    try {
      await shareDocumentWithModule(
        clientId,
        periodId,
        shareDoc.id,
        shareTargetModule,
        undefined,
        shareNotes || undefined,
      );
      setNotice({
        severity: 'success',
        text: `Shared “${shareDoc.original_filename}” with ${shareTargetModule.toUpperCase()} without duplicating files or OCR.`,
      });
      setShareDoc(null);
      setShareNotes('');
      await refresh();
    } catch (err) {
      setNotice({
        severity: 'error',
        text: err instanceof Error ? err.message : 'Failed to share document',
      });
    } finally {
      setSharing(false);
    }
  }

  if (loadError) return <Alert severity="error">{loadError}</Alert>;
  if (!client || !period) return <CircularProgress aria-label="Loading period" />;
  const canUpload = period.status === 'open' && client.status === 'active';

  // Filter items by mismatch if toggled
  const displayedItems = (data?.items || []).filter((item) =>
    mismatchesOnly ? item.category_mismatch : true,
  );

  const mismatchCount = (data?.items || []).filter((item) => item.category_mismatch).length;

  return (
    <Stack spacing={3}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/clients" underline="hover">
          Clients
        </Link>
        <Link component={RouterLink} to={`/clients/${clientId}`} underline="hover">
          {client.name}
        </Link>
        <Typography color="text.secondary">{period.label}</Typography>
        <Typography color="text.primary" fontWeight={600}>
          Central Document Upload
        </Typography>
      </Breadcrumbs>

      {/* Period Header */}
      <Paper sx={{ p: 3 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap">
          <Box>
            <Stack direction="row" spacing={1.5} alignItems="center">
              <Typography variant="h5" component="h2" fontWeight="700">
                Document Intelligence & Central Ingestion
              </Typography>
              <Chip
                label="Central Shared Layer"
                size="small"
                color="primary"
                variant="outlined"
              />
            </Stack>
            <Typography color="text.secondary" sx={{ mt: 0.5 }}>
              {client.name} · {formatDate(period.start_date)} – {formatDate(period.end_date)} ·{' '}
              <Chip
                size="small"
                label={period.status}
                color={period.status === 'open' ? 'success' : 'default'}
              />
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: { xs: 2, sm: 0 } }}>
            <Button
              variant="outlined"
              component={RouterLink}
              to={`/clients/${clientId}/periods/${periodId}/accounting`}
              startIcon={<AccountingIcon />}
            >
              Accounting Module
            </Button>
            <Button
              variant="outlined"
              component={RouterLink}
              to={`/clients/${clientId}/periods/${periodId}/taxation`}
              startIcon={<TaxIcon />}
            >
              Taxation Module
            </Button>
            <Button
              variant="outlined"
              component={RouterLink}
              to={`/clients/${clientId}/periods/${periodId}/workflows`}
            >
              Workflows
            </Button>
          </Stack>
        </Stack>
      </Paper>

      {/* Centralized Upload Interface with Module-Specific Categories */}
      <Can permission="document:upload">
        <Paper sx={{ p: 3 }} component="form" onSubmit={onUpload}>
          <Stack spacing={2}>
            <Box>
              <Typography variant="h6" component="h3" fontWeight="700">
                Upload Documents
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Select the target module and category. Central Document Intelligence will process
                OCR, verify classifications, and route structured tables automatically.
              </Typography>
            </Box>

            {!canUpload && (
              <Alert severity="info">
                Uploads are disabled because this period is closed or the client is archived.
              </Alert>
            )}

            <Grid container spacing={2} alignItems="center">
              {/* Step 1: Select Module */}
              <Grid item xs={12} sm={3}>
                <FormControl fullWidth size="small">
                  <InputLabel id="select-module-label">1. Target Module</InputLabel>
                  <Select
                    labelId="select-module-label"
                    value={uploadModule}
                    label="1. Target Module"
                    onChange={(e) => setUploadModule(e.target.value as ModuleType)}
                  >
                    <MenuItem value="accounting">
                      <Stack direction="row" spacing={1} alignItems="center">
                        <AccountingIcon fontSize="small" sx={{ color: '#4f46e5' }} />
                        <Typography variant="body2">Accounting</Typography>
                      </Stack>
                    </MenuItem>
                    <MenuItem value="taxation">
                      <Stack direction="row" spacing={1} alignItems="center">
                        <TaxIcon fontSize="small" sx={{ color: '#0f766e' }} />
                        <Typography variant="body2">Taxation</Typography>
                      </Stack>
                    </MenuItem>
                    <MenuItem value="audit">
                      <Stack direction="row" spacing={1} alignItems="center">
                        <AuditIcon fontSize="small" sx={{ color: '#d97706' }} />
                        <Typography variant="body2">Audit</Typography>
                      </Stack>
                    </MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              {/* Step 2: Dynamically Displayed Categories for Selected Module */}
              <Grid item xs={12} sm={4}>
                <FormControl fullWidth size="small">
                  <InputLabel id="select-category-label">2. Document Category</InputLabel>
                  <Select
                    labelId="select-category-label"
                    value={category}
                    label="2. Document Category"
                    onChange={(e) => setCategory(e.target.value)}
                  >
                    {MODULE_CATEGORIES[uploadModule].map(([val, label]) => (
                      <MenuItem key={val} value={val}>
                        {label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>

              {/* Step 3: File Picker (Supports Multiple Files) */}
              <Grid item xs={12} sm={3}>
                <Button
                  component="label"
                  variant="outlined"
                  fullWidth
                  disabled={!canUpload || uploading}
                  startIcon={<UploadIcon />}
                  sx={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}
                >
                  {files.length === 0
                    ? 'Choose File(s)'
                    : files.length === 1
                    ? files[0].name
                    : `${files.length} files selected`}
                  <input
                    ref={fileInput}
                    hidden
                    type="file"
                    multiple
                    accept={ACCEPT}
                    aria-label="Files"
                    onChange={(e) => {
                      const selected = Array.from(e.target.files || []);
                      setFiles(selected);
                    }}
                  />
                </Button>
              </Grid>

              {/* Step 4: Submit Upload Button */}
              <Grid item xs={12} sm={2}>
                <Button
                  type="submit"
                  variant="contained"
                  fullWidth
                  disabled={files.length === 0 || !canUpload || uploading}
                >
                  {uploading ? (
                    <CircularProgress size={24} sx={{ color: '#fff' }} />
                  ) : files.length > 1 ? (
                    `Upload (${files.length})`
                  ) : (
                    'Upload'
                  )}
                </Button>
              </Grid>
            </Grid>

            <Typography variant="caption" color="text.secondary">
              Supported formats: PDF, Excel (.xlsx, .xls), CSV, Images (PNG, JPG, JPEG) up to 50 MB.
              User category selection is stored as primary. Content is automatically verified by
              Central Document Intelligence.
            </Typography>
          </Stack>
        </Paper>
      </Can>

      {notice && (
        <Alert severity={notice.severity} onClose={() => setNotice(null)}>
          {notice.text}
        </Alert>
      )}

      {/* Document Category Mismatch Alert Banner */}
      {mismatchCount > 0 && (
        <Alert
          severity="warning"
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => setMismatchesOnly(!mismatchesOnly)}
            >
              {mismatchesOnly ? 'Show All Files' : `Review ${mismatchCount} Mismatch(es)`}
            </Button>
          }
        >
          <strong>Category Mismatch Warning:</strong> {mismatchCount} document(s) have a mismatch
          between the CA-selected category and detected content. The original user selection is
          preserved; please review.
        </Alert>
      )}

      {/* Module-Specific Document Lists & Filter Tabs */}
      <Paper sx={{ p: 3 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap">
          <Tabs
            value={activeTab}
            onChange={(_, val) => {
              setActiveTab(val);
              setPage(0);
            }}
            sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}
          >
            <Tab label="All Documents" value="all" />
            <Tab
              icon={<AccountingIcon fontSize="small" />}
              iconPosition="start"
              label="Accounting"
              value="accounting"
            />
            <Tab
              icon={<TaxIcon fontSize="small" />}
              iconPosition="start"
              label="Taxation"
              value="taxation"
            />
            <Tab
              icon={<AuditIcon fontSize="small" />}
              iconPosition="start"
              label="Audit"
              value="audit"
            />
          </Tabs>

          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
            {mismatchCount > 0 && (
              <Button
                variant={mismatchesOnly ? 'contained' : 'outlined'}
                color="warning"
                size="small"
                startIcon={<WarningIcon />}
                onClick={() => setMismatchesOnly(!mismatchesOnly)}
              >
                {mismatchesOnly ? 'Showing Mismatches' : `Mismatches (${mismatchCount})`}
              </Button>
            )}
          </Stack>
        </Stack>

        {!data && <CircularProgress aria-label="Loading documents" />}
        {data && displayedItems.length === 0 && (
          <Alert severity="info" sx={{ mt: 2 }}>
            {mismatchesOnly
              ? 'No category mismatches found in this view.'
              : `No documents uploaded under ${activeTab.toUpperCase()} for this period yet.`}
          </Alert>
        )}

        {data && displayedItems.length > 0 && (
          <>
            <Table size="small" aria-label="Documents">
              <TableHead>
                <TableRow>
                  <TableCell>File</TableCell>
                  <TableCell>Module</TableCell>
                  <TableCell>Selected Category</TableCell>
                  <TableCell>Verification & Status</TableCell>
                  <TableCell>Size</TableCell>
                  <TableCell>Uploaded</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {displayedItems.map((d) => (
                  <TableRow key={d.id} hover>
                    <TableCell sx={{ wordBreak: 'break-word', fontWeight: 600 }}>
                      {d.original_filename}
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        label={(d.module || 'accounting').toUpperCase()}
                        color={
                          d.module === 'taxation'
                            ? 'success'
                            : d.module === 'audit'
                            ? 'warning'
                            : 'primary'
                        }
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {ALL_LABELS[d.category] || d.category}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Chip
                          size="small"
                          label={STATUS_LABEL[d.status]}
                          color={STATUS_COLOR[d.status]}
                        />
                        {/* Mismatch Warning Chip */}
                        {d.category_mismatch && (
                          <Tooltip
                            title={`CA selected: "${
                              ALL_LABELS[d.user_category || d.category] || d.category
                            }". Central intelligence detected content suggests: "${
                              ALL_LABELS[d.detected_category || ''] || d.detected_category
                            }". Original user selection is preserved.`}
                          >
                            <Chip
                              size="small"
                              icon={<WarningIcon fontSize="small" />}
                              label="Mismatch Flagged"
                              color="warning"
                            />
                          </Tooltip>
                        )}
                      </Stack>
                    </TableCell>
                    <TableCell>{formatBytes(d.size_bytes)}</TableCell>
                    <TableCell>
                      {formatDate(d.created_at)}
                      {d.uploaded_by_email ? ` · ${d.uploaded_by_email}` : ''}
                    </TableCell>
                    <TableCell align="right">
                      <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                        <Can permission="extraction:read">
                          {(d.status === 'processed' || d.status === 'failed') && (
                            <Button
                              size="small"
                              component={RouterLink}
                              to={`/clients/${clientId}/periods/${periodId}/documents/${d.id}/review`}
                            >
                              Review
                            </Button>
                          )}
                        </Can>
                        <Tooltip title="Share this document with another module without re-uploading">
                          <IconButton
                            size="small"
                            color="primary"
                            onClick={() => {
                              setShareDoc(d);
                              setShareTargetModule(d.module === 'accounting' ? 'taxation' : 'accounting');
                            }}
                          >
                            <ShareIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
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
                      </Stack>
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

      {/* Share Document Modal */}
      <Dialog open={Boolean(shareDoc)} onClose={() => setShareDoc(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Share Document Across Modules</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2">
              Share <strong>“{shareDoc?.original_filename}”</strong> with another module. This avoids
              duplicate uploads and re-running OCR while maintaining complete source traceability.
            </Typography>
            <FormControl fullWidth size="small">
              <InputLabel id="share-target-label">Target Module</InputLabel>
              <Select
                labelId="share-target-label"
                value={shareTargetModule}
                label="Target Module"
                onChange={(e) => setShareTargetModule(e.target.value as ModuleType)}
              >
                <MenuItem value="accounting">Accounting</MenuItem>
                <MenuItem value="taxation">Taxation</MenuItem>
                <MenuItem value="audit">Audit</MenuItem>
              </Select>
            </FormControl>
            <TextField
              label="Notes (Optional)"
              size="small"
              fullWidth
              multiline
              rows={2}
              value={shareNotes}
              onChange={(e) => setShareNotes(e.target.value)}
              placeholder="e.g. Sales invoice relevant for section 153 withholding tax reconciliation."
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShareDoc(null)} disabled={sharing}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleShareSubmit}
            disabled={sharing}
            startIcon={sharing ? <CircularProgress size={16} /> : <ShareIcon />}
          >
            {sharing ? 'Sharing...' : 'Share Document'}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
