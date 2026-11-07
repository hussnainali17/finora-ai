import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { tokenStore } from '../services/tokenStore';
import { accountant, healthy, mockApi } from '../test-utils';
import App from './App';

beforeEach(() => tokenStore.set(null));
afterEach(() => vi.unstubAllGlobals());

describe('App authentication', () => {
  it('restores the session from the refresh cookie after a reload', async () => {
    mockApi({
      'POST /auth/refresh': () => ({ status: 200, body: accountant }),
      'GET /health/ready': healthy,
    });
    render(<App />);
    expect(await screen.findByText('Sam Staff')).toBeInTheDocument();
    expect(screen.getByText('Accountant / Staff')).toBeInTheDocument();
    expect(screen.getByText('client:read')).toBeInTheDocument();
    expect(await screen.findByText('Overall: ok')).toBeInTheDocument();
    expect(tokenStore.get()).toBe('access-1');
  });

  it('shows the login form when there is no valid session', async () => {
    mockApi({ 'POST /auth/refresh': () => ({ status: 401, body: { detail: 'nope' } }) });
    render(<App />);
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.queryByText('Your access')).not.toBeInTheDocument();
  });

  it('signs in, then shows the user and permissions', async () => {
    const api = mockApi({
      'POST /auth/refresh': () => ({ status: 401 }),
      'POST /auth/login': () => ({ status: 200, body: accountant }),
      'GET /health/ready': healthy,
    });
    render(<App />);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/email/i), 'sam@firm.example');
    await user.type(screen.getByLabelText(/password/i), 'Correct-Horse-Battery-9');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Sam Staff')).toBeInTheDocument();
    const login = api.calls.find((c) => c.key === 'POST /auth/login')!;
    expect(login.init?.credentials).toBe('include');
    expect(JSON.parse(login.init!.body as string)).toEqual({
      email: 'sam@firm.example',
      password: 'Correct-Horse-Battery-9',
    });
  });

  it('shows a generic error and clears the password after a failed sign-in', async () => {
    mockApi({
      'POST /auth/refresh': () => ({ status: 401 }),
      'POST /auth/login': () => ({ status: 401, body: { detail: 'Invalid email or password' } }),
    });
    render(<App />);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/email/i), 'sam@firm.example');
    await user.type(screen.getByLabelText(/password/i), 'wrong-password-1');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Invalid email or password.')).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toHaveValue('');
    expect(tokenStore.get()).toBeNull();
  });

  it('tells the user to wait when rate limited', async () => {
    mockApi({
      'POST /auth/refresh': () => ({ status: 401 }),
      'POST /auth/login': () => ({ status: 429 }),
    });
    render(<App />);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/email/i), 'a@b.example');
    await user.type(screen.getByLabelText(/password/i), 'whatever-123');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText(/too many attempts/i)).toBeInTheDocument();
  });

  it('signs out: calls the server, forgets the token, returns to the login form', async () => {
    const api = mockApi({
      'POST /auth/refresh': () => ({ status: 200, body: accountant }),
      'POST /auth/logout': () => ({ status: 204 }),
      'GET /health/ready': healthy,
    });
    render(<App />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Sign out' }));

    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(api.calls.some((c) => c.key === 'POST /auth/logout')).toBe(true);
    expect(tokenStore.get()).toBeNull();
  });

  it('never writes credentials to web storage', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    mockApi({
      'POST /auth/refresh': () => ({ status: 200, body: accountant }),
      'GET /health/ready': healthy,
    });
    render(<App />);
    await screen.findByText('Sam Staff');
    await waitFor(() => expect(setItem).not.toHaveBeenCalled());
    setItem.mockRestore();
  });

  it('still shows the backend-unreachable state on the dashboard', async () => {
    mockApi({
      'POST /auth/refresh': () => ({ status: 200, body: accountant }),
      'GET /health/ready': () => {
        throw new Error('network down');
      },
    });
    render(<App />);
    expect(await screen.findByText(/Backend unreachable: network down/)).toBeInTheDocument();
  });
});
