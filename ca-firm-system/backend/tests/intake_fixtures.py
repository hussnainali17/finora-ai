"""Builders for deliberately messy client files used by the Agent 1 tests."""

import io
from datetime import date

import openpyxl
import pymupdf


def messy_trial_balance_xlsx(as_at: str = "30 June 2025") -> bytes:
    """Title rows, blank gaps, merged header, text-formatted numbers, a total row, junk below."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "TB June"
    ws.append(["ABC Traders (Pvt) Ltd"])
    ws.append([f"Trial Balance as at {as_at}"])
    ws.append(["All amounts in PKR"])
    ws.append([])
    ws.append(["Code", "Account Name", "Debit", "Credit"])
    ws.append(["1000", "Cash at bank", 150000.5, None])
    ws.append(["1100", "Receivables", "2,500,000.00", None])
    ws.append([])  # blank row inside the table
    ws.append(["2000", "Payables", None, "(1,200,000.00)"])
    ws.append(["3000", "Capital", None, 1450000.5])
    ws.append(["", "Total", 2650000.5, 250000.5])
    ws.append([])
    ws.append([])
    ws.append(["Prepared by: accounts dept"])
    ws.append(["Checked by: ____"])
    hidden = wb.create_sheet("Notes")
    hidden.append(["Note", "Detail"])
    hidden.append(["1", "Some note"])
    hidden.sheet_state = "hidden"
    return _save(wb)


def bank_statement_xlsx(*, dates: list[str] | None = None) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Statement"
    ws.append(["Habib Bank Ltd", None, None, None, None])
    ws.append(["Statement from 01/07/2025 to 31/07/2025", None, None, None, None])
    ws.append(["Txn Date", "Description", "Withdrawals", "Deposits", "Balance"])
    rows = dates or ["01/07/2025", "05/07/2025", "13/07/2025"]
    amounts = [
        (None, "10,000.00", "10,000.00"),
        ("2,500.00", None, "7,500.00"),
        (None, "900.00", "8,400.00"),
    ]
    for d, (w, dep, bal) in zip(rows, amounts, strict=False):
        ws.append([d, f"Entry {d}", w, dep, bal])
    return _save(wb)


def fixed_assets_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Asset Register"])
    ws.append(["Asset", "Cost", "Accum. Depreciation", "Net Book Value"])
    ws.append(["Laptop", 120000, 40000, 80000])
    ws.append(["Vehicle", 3500000, 700000, 2800000])
    return _save(wb)


def weird_headers_xlsx() -> bytes:
    """No recognisable headers: forces low confidence + review findings."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Foo", "Bar", "Baz"])
    ws.append(["alpha", "zzz", "10"])
    ws.append(["beta", "yyy", "20"])
    ws.append(["gamma", "xxx", "30"])
    return _save(wb)


def dated_xlsx(date_strings: list[str]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Date", "Description", "Amount"])
    for i, d in enumerate(date_strings):
        ws.append([d, f"Item {i}", f"{100 + i}.00"])
    return _save(wb)


def real_date_cells_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Date", "Description", "Amount"])
    ws.append([date(2025, 3, 4), "Real date cell", 10])
    ws.append([date(2025, 3, 5), "Another", 20])
    return _save(wb)


def merged_header_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Account", "Balances", None])
    ws.append([None, "Debit", "Credit"])
    ws.append(["Cash", 100, None])
    ws.append(["Payables", None, 100])
    ws.merge_cells("B1:C1")
    return _save(wb)


def _save(wb: openpyxl.Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def digital_statement_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for x, t in ((72, "Date"), (200, "Description"), (400, "Amount")):
        page.insert_text((x, y), t, fontsize=14)
    for dt, de, am in (
        ("01/02/2025", "Opening", "1,000.00"),
        ("02/02/2025", "Sale", "2,500.00"),
        ("03/02/2025", "Fee", "(50.00)"),
    ):
        y += 24
        for x, t in ((72, dt), (200, de), (400, am)):
            page.insert_text((x, y), t, fontsize=14)
    return bytes(doc.tobytes())


def scanned_statement_png() -> bytes:
    doc = pymupdf.open(stream=digital_statement_pdf(), filetype="pdf")
    return bytes(doc[0].get_pixmap(dpi=200).tobytes("png"))


def prose_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72), "Dear Sirs, please find our management letter enclosed.", fontsize=12
    )
    return bytes(doc.tobytes())
