import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../../app/App';
import { tokenStore } from '../../services/tokenStore';
import { accountant, mockApi, type Route } from '../../test-utils';
import type { TokenResponse } from '../../types/auth';

const session = (permissions: string[]): TokenResponse => ({
  ...accountant,
  user: { ...accountant.user, permissions: ['client:read', 'period:read', ...permissions] },
});
const reviewer = session([
  'document:read',
  'extraction:read',
  'extraction:review',
  'extraction:run',
]);
const readOnly = session(['document:read', 'extraction:read']);

const col = (i: number, header: string, role: string, confidence: number, extra: object = {}) => ({
  col_index: i,
  letter: 'ABCD'[i],
  header,
  header_synthetic: false,
  suggested_role: role,
  confidence,
  role_source: 'header',
  confirmed_role: null,
  effective_role: role,
  ...extra,
});
const table = (over: object = {}) => ({
  id: 't1',
  ordinal: 0,
  name: 'TB June',
  kind: 'sheet',
  n_rows: 2,
  n_cols: 3,
  detected_type: 'trial_balance',
  type_confidence: 0.95,
  type_source: 'heuristic',
  confirmed_type: null,
  effective_type: 'trial_balance',
  currency: 'PKR',
  period_start: null,
  period_end: '2025-06-30',
  status: 'needs_review',
  open_findings: 2,
  columns: [
    col(0, 'Account Name', 'account_name', 0.95),
    col(1, 'Debit', 'debit', 0.95),
    col(2, 'Foo', 'amount', 0.45),
  ],
  ...over,
});
const extraction = (over: object = {}) => ({
  document_id: 'd1',
  document_status: 'processed',
  run: {
    id: 'r1',
    version: 1,
    status: 'completed',
    trigger: 'auto',
    error_code: null,
    error_message: null,
    llm_used: false,
  },
  tables: [table()],
  open_findings: { info: 0, warning: 2, error: 0 },
  ...over,
});
const finding = (over: object = {}) => ({
  id: 'f1',
  table_id: 't1',
  row_index: null,
  col_index: 2,
  code: 'low_confidence_column',
  severity: 'warning',
  message: "Column 'Foo' is probably 'amount' (45% sure). Please confirm.",
  status: 'open',
  resolution_note: null,
  ...over,
});
const rows = {
  items: [
    {
      row_index: 6,
      raw: { '0': { v: 'Cash', t: 's' }, '1': { v: '1,500.50', t: 's' } },
      normalized: { '0': 'Cash', '1': '1500.50' },
      flags: [],
    },
    {
      row_index: 7,
      raw: { '0': { v: 'Total', t: 's' }, '1': { v: 'abc', t: 's' } },
      normalized: { '0': 'Total', '1': null },
      flags: [{ code: 'invalid_amount', col: 1, message: "'abc' is not a valid amount" }],
    },
  ],
  total: 2,
  limit: 25,
  offset: 0,
};

const D = '/clients/c1/periods/p1/documents/d1';
const E = `${D}/extraction`;
const routes = (s: TokenResponse, over: Record<string, Route> = {}): Record<string, Route> => ({
  'POST /auth/refresh': () => ({ status: 200, body: s }),
  [`GET ${E}`]: () => ({ status: 200, body: extraction() }),
  [`GET ${E}/findings`]: () => ({
    status: 200,
    body: [finding(), finding({ id: 'f2', severity: 'error', code: 'x', message: 'Hard error' })],
  }),
  [`GET ${E}/tables/t1/rows?limit=25&offset=0`]: () => ({ status: 200, body: rows }),
  ...over,
});
const open = () => {
  window.history.pushState({}, '', `${D}/review`);
  return render(<App />);
};

beforeEach(() => tokenStore.set(null));
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.pushState({}, '', '/');
});

describe('data review screen', () => {
  it('shows detected type, column suggestions, findings and original vs normalized values', async () => {
    mockApi(routes(reviewer));
    open();
    expect(
      await screen.findByRole('heading', { name: 'Review extracted data' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Needs review')).toBeInTheDocument();
    expect(screen.getByText('Currency PKR')).toBeInTheDocument();
    expect(screen.getByText('Period end 2025-06-30')).toBeInTheDocument();

    const mapping = screen.getByRole('table', { name: 'Column mapping' });
    expect(within(mapping).getByText('Account name · 95%')).toBeInTheDocument();
    expect(within(mapping).getByText('Amount · 45%')).toBeInTheDocument();

    expect(await screen.findByText(/probably 'amount'/)).toBeInTheDocument();
    const data = screen.getByRole('table', { name: 'Extracted rows' });
    expect(within(data).getByText('1500.50')).toBeInTheDocument();
    expect(within(data).getByText('1,500.50')).toBeInTheDocument(); // original shown under normalized
    expect(within(data).getByText('invalid_amount')).toBeInTheDocument();
    expect(within(data).getByText('—')).toBeInTheDocument(); // unreadable value is not shown as 0
  });

  it('lets a reviewer change a column role, which is saved and reloaded', async () => {
    let saved: unknown = null;
    const api = mockApi(
      routes(reviewer, {
        [`PATCH ${E}/tables/t1/columns/2`]: (init) => {
          saved = JSON.parse(String(init?.body));
          return { status: 200, body: table() };
        },
      }),
    );
    open();
    await screen.findByText('Needs review');
    await userEvent.click(screen.getByRole('combobox', { name: 'Role for Foo' }));
    await userEvent.click(await screen.findByRole('option', { name: 'Debit' }));
    await waitFor(() => expect(saved).toEqual({ role: 'debit' }));
    expect(api.calls.filter((c) => c.key === `GET ${E}`).length).toBeGreaterThan(1);
  });

  it('lets a reviewer resolve warnings, but errors cannot be dismissed', async () => {
    let body: unknown = null;
    mockApi(
      routes(reviewer, {
        [`PATCH ${E}/findings/f1`]: (init) => {
          body = JSON.parse(String(init?.body));
          return { status: 200, body: finding({ status: 'resolved' }) };
        },
      }),
    );
    open();
    await screen.findByText('Hard error');
    const dismiss = screen.getAllByRole('button', { name: 'Dismiss' });
    expect(dismiss).toHaveLength(1); // only the warning offers Dismiss
    expect(screen.getAllByRole('button', { name: 'Resolve' })).toHaveLength(2);
    await userEvent.click(screen.getAllByRole('button', { name: 'Resolve' })[0]);
    await waitFor(() => expect(body).toEqual({ status: 'resolved' }));
  });

  it('is read-only for users without review permission', async () => {
    mockApi(routes(readOnly));
    open();
    await screen.findByText('Needs review');
    expect(screen.getByRole('combobox', { name: 'Role for Foo' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    expect(screen.queryByRole('button', { name: 'Resolve' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Dismiss' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Re-run extraction' })).not.toBeInTheDocument();
  });

  it('offers re-run only to users who may run extraction, and posts it', async () => {
    const api = mockApi(
      routes(reviewer, {
        [`POST ${E}/rerun`]: () => ({ status: 202, body: { status: 'queued' } }),
      }),
    );
    open();
    await userEvent.click(await screen.findByRole('button', { name: 'Re-run extraction' }));
    await waitFor(() => expect(api.calls.some((c) => c.key === `POST ${E}/rerun`)).toBe(true));
  });

  it('shows a failure with its reason and no data tables', async () => {
    mockApi(
      routes(reviewer, {
        [`GET ${E}`]: () => ({
          status: 200,
          body: extraction({
            document_status: 'failed',
            tables: [],
            run: {
              id: 'r1',
              version: 1,
              status: 'failed',
              trigger: 'auto',
              llm_used: false,
              error_code: 'encrypted_file',
              error_message: 'PDF is password protected',
            },
          }),
        }),
      }),
    );
    open();
    expect(await screen.findByText(/PDF is password protected/)).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Column mapping' })).not.toBeInTheDocument();
  });

  it('shows progress while the document is still being processed', async () => {
    mockApi(
      routes(reviewer, {
        [`GET ${E}`]: () => ({
          status: 200,
          body: extraction({ document_status: 'processing', run: null, tables: [] }),
        }),
      }),
    );
    open();
    expect(await screen.findByText(/Extraction is processing/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Re-run extraction' })).not.toBeInTheDocument();
  });

  it('surfaces API errors (e.g. no access) instead of an empty page', async () => {
    mockApi(
      routes(reviewer, {
        [`GET ${E}`]: () => ({ status: 404, body: { detail: 'Document not found' } }),
      }),
    );
    open();
    expect(await screen.findByText('Document not found')).toBeInTheDocument();
  });

  it('filters to flagged rows only', async () => {
    const api = mockApi(
      routes(reviewer, {
        [`GET ${E}/tables/t1/rows?limit=25&offset=0&flagged_only=true`]: () => ({
          status: 200,
          body: { ...rows, items: [rows.items[1]], total: 1 },
        }),
      }),
    );
    open();
    await screen.findByText('Needs review');
    await userEvent.click(screen.getByRole('checkbox', { name: 'Flagged rows only' }));
    await waitFor(() =>
      expect(api.calls.some((c) => c.key.endsWith('flagged_only=true'))).toBe(true),
    );
    await waitFor(() => expect(screen.queryByText('Cash')).not.toBeInTheDocument());
  });

  it('links to the review screen from the document list only for finished documents', async () => {
    const client = {
      id: 'c1',
      code: 'ACME',
      name: 'Acme Traders',
      legal_name: null,
      base_currency: 'PKR',
      fiscal_year_end_month: 6,
      status: 'active',
      notes: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };
    const period = {
      id: 'p1',
      client_id: 'c1',
      label: 'FY2025',
      start_date: '2025-07-01',
      end_date: '2026-06-30',
      status: 'open',
      closed_at: null,
      created_at: '2026-01-01T00:00:00Z',
    };
    const doc = (id: string, status: string) => ({
      id,
      client_id: 'c1',
      period_id: 'p1',
      category: 'bank_statement',
      original_filename: `${id}.xlsx`,
      content_type: 'x',
      size_bytes: 10,
      sha256: 'a'.repeat(64),
      status,
      uploaded_by_email: null,
      created_at: '2026-02-01T10:00:00Z',
    });
    const docs = {
      items: [doc('p', 'processed'), doc('u', 'uploaded'), doc('f', 'failed')],
      total: 3,
      limit: 10,
      offset: 0,
    };
    const list = (s: TokenResponse): Record<string, Route> => ({
      'POST /auth/refresh': () => ({ status: 200, body: s }),
      'GET /clients/c1': () => ({ status: 200, body: client }),
      'GET /clients/c1/periods': () => ({ status: 200, body: [period] }),
      'GET /clients/c1/periods/p1/documents?limit=10&offset=0': () => ({ status: 200, body: docs }),
    });
    mockApi(list(readOnly));
    window.history.pushState({}, '', '/clients/c1/periods/p1');
    const { unmount } = render(<App />);
    const links = await screen.findAllByRole('link', { name: 'Review data' });
    expect(links.map((l) => l.getAttribute('href'))).toEqual([
      '/clients/c1/periods/p1/documents/p/review',
      '/clients/c1/periods/p1/documents/f/review',
    ]);
    unmount();

    mockApi(list(session(['document:read'])));
    render(<App />);
    await screen.findByText('p.xlsx');
    expect(screen.queryByRole('link', { name: 'Review data' })).not.toBeInTheDocument();
  });
});
