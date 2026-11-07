import type { CurrentUser, TokenResponse } from '../types/auth';
import { API_BASE_URL, apiFetch, errorFrom } from './http';
import { tokenStore } from './tokenStore';

export async function login(email: string, password: string): Promise<TokenResponse> {
  const resp = await fetch(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    credentials: 'include', // lets the browser store the HttpOnly refresh cookie
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!resp.ok) throw await errorFrom(resp);
  const session = (await resp.json()) as TokenResponse;
  tokenStore.set(session.access_token);
  return session;
}

export async function logout(): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/auth/logout`, { method: 'POST', credentials: 'include' });
  } finally {
    tokenStore.set(null); // always forget the token locally, even if the request failed
  }
}

export const fetchMe = () => apiFetch<CurrentUser>('/auth/me');

export const changePassword = (current_password: string, new_password: string) =>
  apiFetch<void>('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password, new_password }),
  });
