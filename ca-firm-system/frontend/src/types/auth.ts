export type RoleKey = 'firm_admin' | 'ca_reviewer' | 'accountant' | 'client_user';

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string;
  firm_id: string;
  firm_name: string;
  role: RoleKey;
  permissions: string[];
}

export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  user: CurrentUser;
}
