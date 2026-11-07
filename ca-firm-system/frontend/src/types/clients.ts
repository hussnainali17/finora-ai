export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Client {
  id: string;
  code: string;
  name: string;
  legal_name: string | null;
  base_currency: string;
  fiscal_year_end_month: number;
  status: 'active' | 'archived';
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClientCreate {
  code: string;
  name: string;
  legal_name?: string | null;
  base_currency: string;
  fiscal_year_end_month?: number;
}

export interface Period {
  id: string;
  client_id: string;
  label: string;
  start_date: string;
  end_date: string;
  status: 'open' | 'closed';
  closed_at: string | null;
  created_at: string;
}

export interface PeriodCreate {
  label: string;
  start_date: string;
  end_date: string;
}
