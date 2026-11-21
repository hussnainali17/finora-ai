import { apiRequest, http } from './http';
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

/** Downloads the generated report Excel file with proper authentication and error handling. */
export async function downloadReportExcel(
  clientId: string,
  periodId: string,
  reportId: string,
  suggestedFilename?: string,
): Promise<void> {
  const resp = await apiRequest(`${base(clientId, periodId)}/${reportId}/export/excel`);
  const blob = await resp.blob();

  // Try to parse filename from Content-Disposition header if present
  let filename = suggestedFilename;
  const disposition = resp.headers.get('Content-Disposition');
  if (disposition) {
    const filenameMatch = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
    if (filenameMatch && filenameMatch[1]) {
      filename = filenameMatch[1].replace(/['"]/g, '');
    }
  }
  if (!filename) {
    filename = `financial_report_${reportId}.xlsx`;
  }

  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}

