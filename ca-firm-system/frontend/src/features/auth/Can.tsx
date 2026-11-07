import type { ReactNode } from 'react';
import { useAuth } from './AuthContext';

/** Hides UI the user cannot use. Not a security control - the API enforces permissions. */
export function Can({ permission, children }: { permission: string; children: ReactNode }) {
  const { can } = useAuth();
  return can(permission) ? <>{children}</> : null;
}
