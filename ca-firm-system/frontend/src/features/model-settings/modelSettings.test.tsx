import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../../app/App';
import { tokenStore } from '../../services/tokenStore';
import { accountant, mockApi, type Route } from '../../test-utils';
import type { RoleKey, TokenResponse } from '../../types/auth';
import type { LlmAgents, LlmModels } from '../../types/llm';

const withPerms = (role: RoleKey, permissions: string[]): TokenResponse => ({
  ...accountant,
  user: { ...accountant.user, role, permissions },
});
const admin = withPerms('firm_admin', ['llm:read', 'llm:manage', 'llm:select']);
const reviewer = withPerms('ca_reviewer', ['llm:read', 'llm:select']);
const staff = withPerms('accountant', ['llm:read']);
const clientUser = withPerms('client_user', ['client:read']);

const model = (alias: string, name: string, over: object = {}) => ({
  alias,
  display_name: name,
  provider: 'OpenAI',
  description: `${name} desc`,
  context_window: 128000,
  capabilities: ['structured_output'],
  tier: 'economy',
  enabled: false,
  available: null,
  used_by: [] as string[],
  ...over,
});
const models = (over: Partial<LlmModels> = {}): LlmModels => ({
  models: [model('fast-general', 'Fast general'), model('claude-balanced', 'Claude balanced')],
  config_version: 1,
  ...over,
});
const agents = (over: Partial<LlmAgents> = {}): LlmAgents => ({
  agents: [
    {
      key: 'intake',
      label: 'Intake agent',
      default_alias: null,
      fallback_alias: null,
      eligible: [],
      tasks: [
        {
          task: 'column_roles',
          description: 'Suggest column roles',
          requires: ['structured_output'],
          min_context: 8000,
          effective_alias: null,
          source: null,
          override_alias: null,
          eligible: [],
        },
      ],
    },
  ],
  allow_task_overrides: false,
  config_version: 1,
  ...over,
});

const routes = (
  session: TokenResponse,
  m: LlmModels = models(),
  a: LlmAgents = agents(),
  extra: Record<string, Route> = {},
): Record<string, Route> => ({
  'POST /auth/refresh': () => ({ status: 200, body: session }),
  'GET /llm/models': () => ({ status: 200, body: m }),
  'GET /llm/agents': () => ({ status: 200, body: a }),
  'GET /llm/usage/summary': () => ({ status: 200, body: [] }),
  ...extra,
});
const open = () => {
  window.history.pushState({}, '', '/settings/models');
  return render(<App />);
};

beforeEach(() => tokenStore.set(null));
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.pushState({}, '', '/');
});

describe('model settings', () => {
  it('shows that AI is off and that no model is enabled by default', async () => {
    mockApi(routes(admin));
    open();
    expect(await screen.findByRole('heading', { name: 'AI model settings' })).toBeInTheDocument();
    expect(screen.getByText(/No model is enabled/)).toBeInTheDocument();
    expect(screen.getByLabelText('Enable Fast general')).not.toBeChecked();
    expect(screen.getByText(/Using no model \(AI off\)/)).toBeInTheDocument();
  });

  it('lets an admin enable a model and reloads', async () => {
    let enabled = false;
    const { calls } = mockApi(
      routes(admin, models(), agents(), {
        'GET /llm/models': () => ({
          status: 200,
          body: models({ models: [model('fast-general', 'Fast general', { enabled })] }),
        }),
        'PUT /llm/models/fast-general/enabled': (init) => {
          expect(JSON.parse(String(init?.body))).toEqual({ enabled: true });
          enabled = true;
          return { status: 200, body: { config_version: 2 } };
        },
      }),
    );
    open();
    await userEvent.click(await screen.findByLabelText('Enable Fast general'));
    expect(await screen.findByText('Fast general enabled')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText('Enable Fast general')).toBeChecked());
    expect(calls.some((c) => c.key === 'PUT /llm/models/fast-general/enabled')).toBe(true);
  });

  it('shows the server error when a change is refused', async () => {
    mockApi(
      routes(admin, models(), agents(), {
        'PUT /llm/models/fast-general/enabled': () => ({
          status: 403,
          body: { detail: 'Not allowed' },
        }),
      }),
    );
    open();
    await userEvent.click(await screen.findByLabelText('Enable Fast general'));
    expect(await screen.findByText('Not allowed')).toBeInTheDocument();
  });

  it('prevents disabling a model that an agent uses', async () => {
    mockApi(
      routes(
        admin,
        models({
          models: [model('fast-general', 'Fast general', { enabled: true, used_by: ['intake'] })],
        }),
      ),
    );
    open();
    expect(await screen.findByLabelText('Enable Fast general')).toBeDisabled();
    expect(screen.getByText(/In use by intake/)).toBeInTheDocument();
  });

  it('only offers eligible models and saves the agent default and fallback', async () => {
    const a = agents({
      agents: [{ ...agents().agents[0], eligible: ['fast-general', 'claude-balanced'] }],
    });
    const { calls } = mockApi(
      routes(admin, models({ models: models().models.map((m) => ({ ...m, enabled: true })) }), a, {
        'PUT /llm/agents/intake': (init) => {
          expect(JSON.parse(String(init?.body))).toEqual({
            default_alias: 'fast-general',
            fallback_alias: 'claude-balanced',
          });
          return { status: 200, body: { config_version: 2 } };
        },
      }),
    );
    open();
    await userEvent.click(await screen.findByLabelText('Intake agent default model'));
    await userEvent.click(await screen.findByRole('option', { name: 'Fast general' }));
    await userEvent.click(screen.getByLabelText('Intake agent fallback model'));
    const opts = screen.getAllByRole('option').map((o) => o.textContent);
    expect(opts).toEqual(['No fallback', 'Claude balanced']); // default is excluded from the fallback list
    await userEvent.click(screen.getByRole('option', { name: 'Claude balanced' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save Intake agent' }));
    await waitFor(() => expect(calls.some((c) => c.key === 'PUT /llm/agents/intake')).toBe(true));
  });

  it('is read-only for users without llm:manage and hides usage and testing', async () => {
    mockApi(
      routes(staff, models({ models: [model('fast-general', 'Fast general', { enabled: true })] })),
    );
    open();
    expect(await screen.findByText(/only a firm admin can change/)).toBeInTheDocument();
    expect(screen.getByLabelText('Enable Fast general')).toBeDisabled();
    expect(screen.getByLabelText('Allow task-level model selection')).toBeDisabled();
    expect(screen.queryByRole('button', { name: /Test Fast general/ })).toBeNull();
    expect(screen.queryByText('Usage')).toBeNull();
  });

  it('shows task override selectors only when policy allows and the user may select', async () => {
    const task = {
      ...agents().agents[0].tasks[0],
      eligible: ['fast-general'],
      effective_alias: 'fast-general',
      source: 'agent_default',
    };
    const a = (allow: boolean) =>
      agents({
        allow_task_overrides: allow,
        agents: [
          {
            ...agents().agents[0],
            default_alias: 'fast-general',
            eligible: ['fast-general'],
            tasks: [task],
          },
        ],
      });
    const m = models({ models: [model('fast-general', 'Fast general', { enabled: true })] });

    mockApi(routes(reviewer, m, a(false)));
    const first = open();
    await screen.findByText(/Using Fast general/);
    expect(screen.queryByLabelText('Model for column roles')).toBeNull();
    first.unmount();
    vi.unstubAllGlobals();

    mockApi(routes(reviewer, m, a(true)));
    const second = open();
    expect(await screen.findByLabelText('Model for column roles')).toBeInTheDocument();
    second.unmount();
    vi.unstubAllGlobals();

    mockApi(routes(staff, m, a(true))); // accountant has no llm:select
    open();
    await screen.findByText(/Using Fast general/);
    expect(screen.queryByLabelText('Model for column roles')).toBeNull();
  });

  it('shows usage to admins, including a missing cost as a dash', async () => {
    mockApi(
      routes(admin, models(), agents(), {
        'GET /llm/usage/summary': () => ({
          status: 200,
          body: [
            {
              alias: 'fast-general',
              agent: 'intake',
              calls: 3,
              errors: 1,
              fallbacks: 0,
              tokens: 480,
              cost_usd: '0.012',
              avg_latency_ms: 120,
            },
            {
              alias: 'claude-balanced',
              agent: 'intake',
              calls: 1,
              errors: 0,
              fallbacks: 1,
              tokens: 10,
              cost_usd: null,
              avg_latency_ms: 90,
            },
          ],
        }),
      }),
    );
    open();
    expect(await screen.findByText('0.0120')).toBeInTheDocument();
    expect(screen.getByLabelText('Usage summary')).toBeInTheDocument();
    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('reports a connection test result without any provider detail', async () => {
    mockApi(
      routes(admin, models(), agents(), {
        'POST /llm/models/fast-general/test': () => ({
          status: 200,
          body: {
            ok: false,
            alias: 'fast-general',
            latency_ms: null,
            attempts: null,
            error_code: 'llm_call_failed',
          },
        }),
      }),
    );
    open();
    await userEvent.click(await screen.findByRole('button', { name: 'Test Fast general' }));
    expect(await screen.findByText('Failed')).toBeInTheDocument();
  });

  it('hides the page link and redirects users without llm:read', async () => {
    mockApi({
      'POST /auth/refresh': () => ({ status: 200, body: clientUser }),
      'GET /clients?limit=10&offset=0': () => ({
        status: 200,
        body: { items: [], total: 0, limit: 10, offset: 0 },
      }),
    });
    open();
    await screen.findByRole('button', { name: 'Sign out' });
    expect(screen.queryByRole('link', { name: 'AI models' })).toBeNull();
    expect(screen.queryByRole('heading', { name: 'AI model settings' })).toBeNull();
  });
});
