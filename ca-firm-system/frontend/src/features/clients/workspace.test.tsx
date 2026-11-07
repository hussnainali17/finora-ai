import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../../app/App';
import { tokenStore } from '../../services/tokenStore';
import { accountant, mockApi, type Route } from '../../test-utils';
import type { TokenResponse } from '../../types/auth';

const reviewer: TokenResponse = {
  ...accountant,
  user: {
    ...accountant.user,
    role: 'ca_reviewer',
    permissions: [
      'client:read',
      'client:create',
      'period:read',
      'period:create',
      'period:close',
      'document:read',
      'document:upload',
      'document:delete',
    ],
  },
};
const readOnly: TokenResponse = {
  ...accountant,
  user: {
    ...accountant.user,
    role: 'client_user',
    permissions: ['client:read', 'period:read', 'document:read'],
  },
};

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
const doc = (over: object = {}) => ({
  id: 'd1',
  client_id: 'c1',
  period_id: 'p1',
  category: 'bank_statement',
  original_filename: 'jan.pdf',
  content_type: 'application/pdf',
  size_bytes: 2048,
  sha256: 'a'.repeat(64),
  status: 'uploaded',
  uploaded_by_email: 'sam@firm.example',
  created_at: '2026-02-01T10:00:00Z',
  ...over,
});
const page = <T,>(items: T[]) => ({ items, total: items.length, limit: 10, offset: 0 });

function open(path: string) {
  window.history.pushState({}, '', path);
  return render(<App />);
}
const base = (session: TokenResponse): Record<string, Route> => ({
  'POST /auth/refresh': () => ({ status: 200, body: session }),
  'GET /clients/c1': () => ({ status: 200, body: client }),
  'GET /clients/c1/periods': () => ({ status: 200, body: [period] }),
});

beforeEach(() => tokenStore.set(null));
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.pushState({}, '', '/');
});

describe('clients', () => {
  it('lists clients and links to the client workspace', async () => {
    mockApi({
      ...base(reviewer),
      'GET /clients?limit=10&offset=0': () => ({ status: 200, body: page([client]) }),
    });
    open('/clients');
    expect(await screen.findByRole('link', { name: 'Acme Traders' })).toHaveAttribute(
      'href',
      '/clients/c1',
    );
    expect(screen.getByText('PKR')).toBeInTheDocument();
  });

  it('shows an empty state and an error state', async () => {
    mockApi({
      ...base(accountant),
      'GET /clients?limit=10&offset=0': () => ({ status: 200, body: page([]) }),
    });
    const { unmount } = open('/clients');
    expect(await screen.findByText(/No clients yet/)).toBeInTheDocument();
    unmount();

    mockApi({
      ...base(accountant),
      'GET /clients?limit=10&offset=0': () => ({ status: 500, body: { detail: 'boom' } }),
    });
    open('/clients');
    expect(await screen.findByText('boom')).toBeInTheDocument();
  });

  it('only offers "New client" to users who may create clients', async () => {
    const list = { 'GET /clients?limit=10&offset=0': () => ({ status: 200, body: page([]) }) };
    mockApi({ ...base(accountant), ...list });
    const { unmount } = open('/clients');
    await screen.findByText(/No clients yet/);
    expect(screen.queryByRole('button', { name: 'New client' })).not.toBeInTheDocument();
    unmount();

    mockApi({ ...base(reviewer), ...list });
    open('/clients');
    expect(await screen.findByRole('button', { name: 'New client' })).toBeInTheDocument();
  });

  it('creates a client and reloads the list', async () => {
    let created = false;
    const api = mockApi({
      ...base(reviewer),
      'GET /clients?limit=10&offset=0': () => ({
        status: 200,
        body: page(created ? [client] : []),
      }),
      'POST /clients': () => {
        created = true;
        return { status: 201, body: client };
      },
    });
    open('/clients');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'New client' }));
    await user.type(screen.getByLabelText(/client code/i), 'ACME');
    await user.type(screen.getByLabelText(/client name/i), 'Acme Traders');
    await user.click(screen.getByRole('button', { name: 'Create client' }));
    expect(await screen.findByRole('link', { name: 'Acme Traders' })).toBeInTheDocument();
    const post = api.calls.find((c) => c.key === 'POST /clients')!;
    expect(JSON.parse(post.init!.body as string)).toEqual({
      code: 'ACME',
      name: 'Acme Traders',
      base_currency: 'PKR',
    });
  });

  it('shows periods, and a server error when a new period overlaps', async () => {
    mockApi({
      ...base(reviewer),
      'POST /clients/c1/periods': () => ({
        status: 409,
        body: { detail: 'Period overlaps an existing period for this client' },
      }),
    });
    open('/clients/c1');
    expect(await screen.findByRole('link', { name: 'FY2025' })).toHaveAttribute(
      'href',
      '/clients/c1/periods/p1',
    );
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/label/i), 'H2');
    await user.type(screen.getByLabelText(/^Start/), '2025-09-01');
    await user.type(screen.getByLabelText(/^End/), '2026-02-01');
    await user.click(screen.getByRole('button', { name: 'Add period' }));
    expect(await screen.findByText(/overlaps an existing period/)).toBeInTheDocument();
  });

  it('shows "not found" for a client outside the user’s scope', async () => {
    mockApi({
      'POST /auth/refresh': () => ({ status: 200, body: accountant }),
      'GET /clients/zzz': () => ({ status: 404, body: { detail: 'Client not found' } }),
      'GET /clients/zzz/periods': () => ({ status: 404, body: { detail: 'Client not found' } }),
    });
    open('/clients/zzz');
    expect(await screen.findByText('Client not found.')).toBeInTheDocument();
  });
});

describe('documents', () => {
  const docsUrl = 'GET /clients/c1/periods/p1/documents?limit=10&offset=0';

  it('lists files with their processing status', async () => {
    mockApi({
      ...base(reviewer),
      [docsUrl]: () => ({
        status: 200,
        body: page([doc(), doc({ id: 'd2', original_filename: 'feb.pdf', status: 'queued' })]),
      }),
    });
    open('/clients/c1/periods/p1');
    const table = await screen.findByRole('table', { name: 'Documents' });
    expect(within(table).getByText('jan.pdf')).toBeInTheDocument();
    expect(within(table).getByText('Uploaded', { selector: '.MuiChip-label' })).toBeInTheDocument();
    expect(within(table).getByText('Queued for processing')).toBeInTheDocument();
    expect(within(table).getAllByText('Bank statement', { selector: 'td' })).toHaveLength(2);
  });

  it('uploads a file as multipart form data with the chosen type', async () => {
    let uploaded = false;
    const api = mockApi({
      ...base(reviewer),
      [docsUrl]: () => ({ status: 200, body: page(uploaded ? [doc()] : []) }),
      'POST /clients/c1/periods/p1/documents': () => {
        uploaded = true;
        return { status: 201, body: doc() };
      },
    });
    open('/clients/c1/periods/p1');
    const user = userEvent.setup();
    await screen.findByText(/No files uploaded/);
    await user.upload(
      screen.getByLabelText('File'),
      new File(['%PDF-1.7 hello'], 'jan.pdf', { type: 'application/pdf' }),
    );
    await user.click(screen.getByRole('button', { name: 'Upload' }));

    expect(await screen.findByText(/“jan.pdf” uploaded/)).toBeInTheDocument();
    const call = api.calls.find((c) => c.key === 'POST /clients/c1/periods/p1/documents')!;
    const form = call.init!.body as FormData;
    expect((form.get('file') as File).name).toBe('jan.pdf');
    expect(form.get('category')).toBe('bank_statement');
    // multipart boundary must be set by the browser, never overridden by us
    expect(new Headers(call.init!.headers).has('Content-Type')).toBe(false);
    expect(await screen.findByRole('table', { name: 'Documents' })).toBeInTheDocument();
  });

  it('explains a duplicate upload instead of showing a generic error', async () => {
    mockApi({
      ...base(reviewer),
      [docsUrl]: () => ({ status: 200, body: page([]) }),
      'POST /clients/c1/periods/p1/documents': () => ({
        status: 409,
        body: {
          detail: 'dup',
          code: 'duplicate_document',
          existing_filename: 'jan.pdf',
          existing_document_id: 'd1',
        },
      }),
    });
    open('/clients/c1/periods/p1');
    const user = userEvent.setup();
    await screen.findByText(/No files uploaded/);
    await user.upload(screen.getByLabelText('File'), new File(['%PDF-1.7'], 'copy.pdf'));
    await user.click(screen.getByRole('button', { name: 'Upload' }));
    expect(
      await screen.findByText(/already uploaded as “jan.pdf”. Nothing was changed/),
    ).toBeInTheDocument();
  });

  it('shows server rejections (type/size) to the user', async () => {
    mockApi({
      ...base(reviewer),
      [docsUrl]: () => ({ status: 200, body: page([]) }),
      'POST /clients/c1/periods/p1/documents': () => ({
        status: 415,
        body: { detail: 'The file content does not match a .pdf file; it may be corrupted.' },
      }),
    });
    open('/clients/c1/periods/p1');
    const user = userEvent.setup();
    await screen.findByText(/No files uploaded/);
    await user.upload(screen.getByLabelText('File'), new File(['MZ'], 'x.pdf'));
    await user.click(screen.getByRole('button', { name: 'Upload' }));
    expect(await screen.findByText(/does not match a .pdf file/)).toBeInTheDocument();
  });

  it('downloads through the authenticated API', async () => {
    const createObjectURL = vi.fn(() => 'blob:x');
    Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const api = mockApi({
      ...base(reviewer),
      [docsUrl]: () => ({ status: 200, body: page([doc()]) }),
      'GET /clients/c1/periods/p1/documents/d1/download': () => ({
        status: 200,
        body: 'file-bytes',
      }),
    });
    open('/clients/c1/periods/p1');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Download' }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    const call = api.calls.find((c) => c.key.endsWith('/download'))!;
    expect(new Headers(call.init?.headers).get('Authorization')).toBe('Bearer access-1'); // never a public URL
    expect(createObjectURL).toHaveBeenCalled();
    click.mockRestore();
  });

  it('hides upload and remove controls from read-only users', async () => {
    mockApi({ ...base(readOnly), [docsUrl]: () => ({ status: 200, body: page([doc()]) }) });
    open('/clients/c1/periods/p1');
    await screen.findByRole('table', { name: 'Documents' });
    expect(screen.getByRole('button', { name: 'Download' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Upload' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument();
  });

  it('disables uploading for a closed period', async () => {
    mockApi({
      ...base(reviewer),
      'GET /clients/c1/periods': () => ({ status: 200, body: [{ ...period, status: 'closed' }] }),
      [docsUrl]: () => ({ status: 200, body: page([]) }),
    });
    open('/clients/c1/periods/p1');
    expect(await screen.findByText(/Uploads are disabled/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Upload' })).toBeDisabled();
  });

  it('removes a document after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    let removed = false;
    const api = mockApi({
      ...base(reviewer),
      [docsUrl]: () => ({ status: 200, body: page(removed ? [] : [doc()]) }),
      'DELETE /clients/c1/periods/p1/documents/d1': () => {
        removed = true;
        return { status: 204 };
      },
    });
    open('/clients/c1/periods/p1');
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Remove' }));
    expect(await screen.findByText(/“jan.pdf” removed/)).toBeInTheDocument();
    expect(api.calls.some((c) => c.key === 'DELETE /clients/c1/periods/p1/documents/d1')).toBe(
      true,
    );
  });
});
