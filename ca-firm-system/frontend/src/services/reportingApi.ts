import { http } from './http';
import type { FinancialReport, FinancialReportListOut } from '../types/reporting';

function base(clientId: string, periodId: string): string {
  return `/clients/${clientId}/periods/${periodId}/reports`;
}

export async function generateReports(
  clientId: string,
  periodId: string,
  currency: string = 'PKR',
): Promise<Record<string, unknown>> {
  return http.post<Record<string, unknown>>(`${base(clientId, periodId)}/generate`, {
    currency,
  });
}

export async function listReports(
  clientId: string,
  periodId: string,
  reportType?: string,
): Promise<FinancialReportListOut> {
  const q = reportType ? `?report_type=${reportType}` : '';
  return http.get<FinancialReportListOut>(`${base(clientId, periodId)}/${q}`);
}

export async function getReport(
  clientId: string,
  periodId: string,
  reportId: string,
): Promise<FinancialReport> {
  return http.get<FinancialReport>(`${base(clientId, periodId)}/${reportId}`);
}

export async function signOffReport(
  clientId: string,
  periodId: string,
  reportId: string,
  notes?: string,
): Promise<FinancialReport> {
  return http.post<FinancialReport>(`${base(clientId, periodId)}/${reportId}/sign-off`, {
    notes,
  });
}

export function getExcelDownloadUrl(clientId: string, periodId: string, reportId: string): string {
  return `/api/v1/clients/${clientId}/periods/${periodId}/reports/${reportId}/export/excel`;
}
