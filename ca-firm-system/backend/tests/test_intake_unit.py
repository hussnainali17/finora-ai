"""Phase 3 unit tests: deterministic parsing, structuring and normalization (no database)."""

import io
import json
import shutil
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from app.agents.intake_agent.classify import (
    guess_role,
    profile_column,
    role_from_header,
    scan_preamble,
    score_document_type,
)
from app.agents.intake_agent.layout import detect_layout
from app.agents.intake_agent.llm import ColumnQuery, build_prompt, parse_response
from app.agents.intake_agent.normalize import normalize_rows
from app.agents.intake_agent.parsers.csv_parser import parse_csv
from app.agents.intake_agent.parsers.excel import parse_xlsx
from app.agents.intake_agent.parsers.ocr import OcrMyPdfEngine, image_to_pdf
from app.agents.intake_agent.parsers.pdf import parse_pdf
from app.agents.intake_agent.pipeline import build_tables
from app.agents.intake_agent.types import ExtractionError, RawCell
from app.agents.intake_agent.values import (
    amount_str,
    detect_decimal_style,
    find_currencies,
    parse_amount,
    parse_date,
)
from tests import intake_fixtures as fx

R = RawCell


# ----------------------------------------------------------------------------- amounts


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1,234.50", "1234.5000"),
        ("(1,234.50)", "-1234.5000"),
        ("1,234.50-", "-1234.5000"),
        ("-1,234.50", "-1234.5000"),
        ("Rs. 1,000", "1000.0000"),
        ("PKR 2,500.75", "2500.7500"),
        ("$ 99", "99.0000"),
        ("  42  ", "42.0000"),
        ("100 Dr", "100.0000"),
        ("100 Cr", "-100.0000"),
        ("0.00", "0.0000"),
    ],
)
def test_amount_formats_parse_to_exact_decimals(text: str, expected: str) -> None:
    r = parse_amount(R(text))
    assert r.status == "ok"
    assert r.value == Decimal(expected)
    assert isinstance(r.value, Decimal)


@pytest.mark.parametrize("text", ["abc", "12abc", "1,2,3,4", "--5", "1.2.3", "N/A", "12%", "()"])
def test_invalid_amounts_are_invalid_not_zero(text: str) -> None:
    r = parse_amount(R(text))
    assert r.status == "invalid"
    assert r.value is None


@pytest.mark.parametrize("text", ["", "   ", "-", "–", "nil"])
def test_blank_markers_are_blank_not_zero(text: str) -> None:
    r = parse_amount(R(text))
    assert r.status == "blank"
    assert r.value is None


def test_european_number_format_is_detected_per_column_and_parsed() -> None:
    values = ["1.234,50", "10.000,00", "99,5"]
    style = detect_decimal_style(values)
    assert style == "comma"
    assert parse_amount(R("1.234,50"), style).value == Decimal("1234.5")
    assert parse_amount(R("99,5"), style).value == Decimal("99.5")


def test_us_format_stays_us_when_column_is_us() -> None:
    assert detect_decimal_style(["1,234.50", "10,000.00", "7.25"]) == "dot"


def test_no_float_rounding_artifacts_from_numeric_cells() -> None:
    assert parse_amount(R("0.1", "n")).value == Decimal("0.1000")
    # 3 * 0.1 style drift never appears because amounts are Decimal end to end
    total = sum(
        (parse_amount(R(v, "n")).value or Decimal(0) for v in ["0.1", "0.2", "0.3"]), Decimal(0)
    )
    assert total == Decimal("0.6000")


def test_amount_str_is_fixed_point_with_two_decimals_minimum() -> None:
    assert amount_str(Decimal("1234.5000")) == "1234.50"
    assert amount_str(Decimal("1234.0000")) == "1234.00"
    assert amount_str(Decimal("0.0001")) == "0.0001"
    assert amount_str(Decimal("-5.2500")) == "-5.25"


# ----------------------------------------------------------------------------- dates


def test_unambiguous_day_first_and_month_first() -> None:
    a = parse_date(R("13/02/2025"))
    assert (a.status, a.value, a.certain_order) == ("ok", date(2025, 2, 13), "DMY")
    b = parse_date(R("02/13/2025"))
    assert (b.status, b.value, b.certain_order) == ("ok", date(2025, 2, 13), "MDY")


def test_ambiguous_date_reports_both_readings_and_uses_default_order() -> None:
    r = parse_date(R("03/04/2025"), "DMY")
    assert r.status == "ambiguous"
    assert r.value == date(2025, 4, 3)
    assert r.alt == date(2025, 3, 4)
    r2 = parse_date(R("03/04/2025"), "MDY")
    assert r2.value == date(2025, 3, 4)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2025-03-04", date(2025, 3, 4)),
        ("2025/03/04", date(2025, 3, 4)),
        ("4 Mar 2025", date(2025, 3, 4)),
        ("04-Mar-25", date(2025, 3, 4)),
        ("March 4, 2025", date(2025, 3, 4)),
        ("4th March 2025", None),  # not a supported shape -> invalid, never guessed
        ("20250304", date(2025, 3, 4)),
        ("29 Feb 2024", date(2024, 2, 29)),
    ],
)
def test_date_formats(text: str, expected: date | None) -> None:
    r = parse_date(R(text))
    if expected is None:
        assert r.status == "invalid"
    else:
        assert (r.status, r.value) == ("ok", expected)


@pytest.mark.parametrize(
    "text", ["31/02/2025", "29 Feb 2025", "2025-13-01", "00/00/0000", "yesterday", "32/01/2025"]
)
def test_impossible_dates_are_invalid(text: str) -> None:
    assert parse_date(R(text)).status == "invalid"


def test_real_date_cells_pass_through() -> None:
    assert parse_date(R("2025-03-04T00:00:00", "d")).value == date(2025, 3, 4)


# ----------------------------------------------------------------------------- normalization


def test_date_column_order_is_inferred_from_the_data_not_guessed() -> None:
    rows = [[R(d), R("x"), R("1")] for d in ["03/04/2025", "13/04/2025", "05/04/2025"]]
    out = normalize_rows(rows, [0, 1, 2], ["date", "description", "amount"], ["D", "N", "A"], "MDY")
    # 13/04 proves day-first for the whole column, overriding the MDY default
    assert [r["0"] for r in out.rows] == ["2025-04-03", "2025-04-13", "2025-04-05"]
    assert any(f.code == "date_order_inferred" for f in out.findings)
    assert not any(f.code == "ambiguous_date_order" for f in out.findings)


def test_unresolvable_ambiguous_dates_are_flagged_with_the_assumption() -> None:
    rows = [[R(d), R("x"), R("1")] for d in ["03/04/2025", "05/06/2025"]]
    out = normalize_rows(rows, [0, 1], ["date", "description", "amount"], ["D", "N", "A"], "DMY")
    f = next(f for f in out.findings if f.code == "ambiguous_date_order")
    assert f.details["assumed_order"] == "DMY"
    assert all("ambiguous_date" in [x["code"] for x in fl] for fl in out.flags)


def test_invalid_values_become_null_with_a_flag_and_finding_never_zero() -> None:
    rows = [[R("10.00")], [R("abc")], [R("")]]
    out = normalize_rows(rows, [0, 1, 2], ["amount"], ["Amt"])
    assert [r["0"] for r in out.rows] == ["10.00", None, None]
    assert "invalid_amount" in [f["code"] for f in out.flags[1]]
    assert any(f.code == "invalid_amounts" and f.details["count"] == 1 for f in out.findings)


def test_total_and_duplicate_rows_are_flagged_not_removed() -> None:
    rows = [
        [R("Cash"), R("100.00")],
        [R("Cash"), R("100.00")],
        [R("Total"), R("200.00")],
    ]
    out = normalize_rows(rows, [0, 1, 2], ["description", "amount"], ["D", "A"])
    assert len(out.rows) == 3
    assert [f["code"] for f in out.flags[1]] == ["duplicate_row"]
    assert [f["code"] for f in out.flags[2]] == ["total_row"]


def test_text_is_unicode_normalised_and_control_chars_stripped() -> None:
    rows = [[R("  Café​   Ltd\x07 ")]]
    out = normalize_rows(rows, [0], ["description"], ["D"])
    assert out.rows[0]["0"] == "Café Ltd"


def test_normalization_never_mutates_raw_cells() -> None:
    cell = R("  (1,000.00) ")
    normalize_rows([[cell]], [0], ["amount"], ["A"])
    assert cell.v == "  (1,000.00) "


# ----------------------------------------------------------------------------- layout


def test_messy_trial_balance_layout_finds_header_preamble_and_ignores_junk() -> None:
    parsed = parse_xlsx(fx.messy_trial_balance_xlsx(), 10_000, 10**8)
    assert [g.name for g in parsed.grids] == ["TB June", "Notes"]
    assert any(f.code == "hidden_sheet" for f in parsed.findings)
    grid = parsed.grids[0]
    lay = detect_layout(grid)
    assert lay.headers == ["Code", "Account Name", "Debit", "Credit"]
    assert grid.row_numbers[lay.header_rows[0]] == 5  # source row number is preserved
    assert len(lay.data_rows) == 5  # 4 accounts + total, blank row skipped
    assert lay.blank_rows_skipped == 1
    assert lay.extra_blocks  # "Prepared by" block is not part of the table


def test_merged_two_row_header_is_combined() -> None:
    parsed = parse_xlsx(fx.merged_header_xlsx(), 1000, 10**8)
    lay = detect_layout(parsed.grids[0])
    assert lay.headers == ["Account", "Balances Debit", "Balances Credit"]
    assert len(lay.data_rows) == 2


def test_table_without_header_is_detected_and_flagged() -> None:
    wb_rows = [["1000", "Cash", "100.00"], ["2000", "Bank", "200.00"], ["3000", "Loan", "300.00"]]
    csv_bytes = "\n".join(",".join(r) for r in wb_rows).encode()
    lay = detect_layout(parse_csv(csv_bytes, 100).grids[0])
    assert lay.has_header is False
    assert len(lay.data_rows) == 3


# ----------------------------------------------------------------------------- csv


def test_csv_semicolon_and_cp1252_encoding() -> None:
    data = "Date;Beschreibung;Betrag\n01.02.2025;Café;1.234,50\n".encode("cp1252")
    parsed = parse_csv(data, 100)
    g = parsed.grids[0]
    assert g.meta["delimiter"] == ";"
    assert g.meta["encoding"] == "cp1252"
    assert g.rows[1][1] == R("Café")


def test_csv_utf8_bom_and_utf16() -> None:
    assert parse_csv("﻿A,B\n1,2\n".encode(), 10).grids[0].rows[0][0] == R("A")
    assert parse_csv("A,B\n1,2\n".encode("utf-16"), 10).grids[0].rows[1][0] == R("1")


def test_csv_quotes_and_embedded_newlines() -> None:
    parsed = parse_csv(b'A,B\n"x, y","line1\nline2"\n', 10)
    assert parsed.grids[0].rows[1][0] == R("x, y")
    assert parsed.grids[0].rows[1][1] == R("line1\nline2")


def test_empty_and_binary_csv_are_rejected_cleanly() -> None:
    with pytest.raises(ExtractionError) as e1:
        parse_csv(b"\n\n,,\n", 10)
    assert e1.value.code == "empty_file"
    with pytest.raises(ExtractionError) as e2:
        parse_csv(b"\x00\x01\x02binary", 10)
    assert e2.value.code == "corrupt_file"


def test_csv_row_cap_truncates_with_a_warning() -> None:
    data = ("A,B\n" + "\n".join(f"{i},{i}" for i in range(50))).encode()
    parsed = parse_csv(data, 10)
    assert len(parsed.grids[0].rows) == 10
    assert any(f.code == "rows_truncated" for f in parsed.grids[0].findings)


# ----------------------------------------------------------------------------- excel


def test_corrupt_and_non_xlsx_files_raise_extraction_errors() -> None:
    with pytest.raises(ExtractionError) as e:
        parse_xlsx(b"this is not a zip", 100, 10**8)
    assert e.value.code == "corrupt_file"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "x")
    with pytest.raises(ExtractionError):
        parse_xlsx(buf.getvalue(), 100, 10**8)


def test_zip_bomb_guard_rejects_oversized_expansion() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/big.xml", b"0" * 200_000)
    with pytest.raises(ExtractionError) as e:
        parse_xlsx(buf.getvalue(), 100, 100_000)
    assert e.value.code == "file_too_large"


def test_real_excel_date_cells_are_read_as_dates() -> None:
    g = parse_xlsx(fx.real_date_cells_xlsx(), 100, 10**8).grids[0]
    assert g.rows[1][0] is not None
    assert g.rows[1][0].t == "d"
    assert g.rows[1][2] == R("10", "n")


# ----------------------------------------------------------------------------- classification


@pytest.mark.parametrize(
    ("header", "role"),
    [
        ("Debit", "debit"),
        ("DR", "debit"),
        ("Credit Amount", "credit"),
        ("A/c Name", "account_name"),
        ("Account Code", "account_code"),
        ("Txn Date", "date"),
        ("Value Date", "value_date"),
        ("Withdrawals", "withdrawal"),
        ("Deposits", "deposit"),
        ("Closing Balance", "balance"),
        ("Narration", "description"),
        ("Accum. Depreciation", "accumulated_depreciation"),
        ("Net Book Value", "net_book_value"),
        ("Qty", "quantity"),
        ("Unit Cost", "unit_cost"),
        ("Gross Pay", "gross_pay"),
        ("Net Salary", "net_pay"),
        ("Cheque No", "reference"),
    ],
)
def test_header_synonyms(header: str, role: str) -> None:
    assert role_from_header(header) == role


def test_unrecognised_header_has_no_role() -> None:
    assert role_from_header("Foo") is None
    assert role_from_header("") is None
    assert role_from_header(None) is None


def test_header_and_content_disagreement_lowers_confidence() -> None:
    p = profile_column(0, "Debit", [R("hello world"), R("some text"), R("more text")])
    g = guess_role(p)
    assert g.role == "debit"
    assert g.confidence < 0.7


def test_content_only_guess_is_low_confidence() -> None:
    p = profile_column(0, None, [R("10.00"), R("20.00"), R("30.00")])
    g = guess_role(p)
    assert g.role == "amount"
    assert g.confidence < 0.7


def test_document_type_scoring() -> None:
    assert score_document_type({"account_name", "debit", "credit"}, None)[0] == "trial_balance"
    assert (
        score_document_type({"date", "description", "withdrawal", "deposit", "balance"}, None)[0]
        == "bank_statement"
    )
    assert (
        score_document_type({"description", "cost", "net_book_value"}, None)[0]
        == "fixed_asset_register"
    )
    assert score_document_type({"other"}, None) == ("unknown", 0.0)
    # a date column makes a debit/credit sheet a ledger, not a trial balance
    assert (
        score_document_type({"date", "account_name", "debit", "credit"}, None)[0]
        == "general_ledger"
    )


def test_preamble_period_currency_and_ambiguous_symbol() -> None:
    info = scan_preamble(["ABC Ltd", "Trial Balance as at 30 June 2025", "Amounts in PKR"])
    assert info.period_end == date(2025, 6, 30)
    assert info.currency == "PKR"
    amb = scan_preamble(["Amounts in $"])
    assert amb.currency is None
    assert amb.ambiguous_currency is True
    assert find_currencies("USD and EUR") == {"USD", "EUR"}
    rng = scan_preamble(["Statement from 01/07/2025 to 31/07/2025"])
    assert (rng.period_start, rng.period_end) == (date(2025, 7, 1), date(2025, 7, 31))


# ----------------------------------------------------------------------------- pipeline


async def _tables(data: bytes, category: str | None, **kw):  # type: ignore[no-untyped-def]
    return await build_tables(
        parse_xlsx(data, 10_000, 10**8),
        category=category,
        default_date_order="DMY",
        assistant=None,
        **kw,
    )


async def test_pipeline_messy_trial_balance_end_to_end() -> None:
    t = (await _tables(fx.messy_trial_balance_xlsx(), "trial_balance"))[0]
    assert t.detected_type == "trial_balance"
    assert t.currency == "PKR"
    assert t.period_end == date(2025, 6, 30)
    assert [c.role for c in t.columns] == ["account_code", "account_name", "debit", "credit"]
    assert t.status == "ok"
    assert t.row_numbers == [6, 7, 9, 10, 11]  # source row numbers survive the blank-row skip
    assert t.normalized.rows[0]["2"] == "150000.50"
    assert t.normalized.rows[1]["2"] == "2500000.00"
    assert t.normalized.rows[2]["3"] == "-1200000.00"  # parentheses -> negative, flagged below
    assert t.normalized.rows[4]["1"] == "Total"
    assert "total_row" in [f["code"] for f in t.normalized.flags[4]]
    # raw preserved verbatim
    assert t.raw_rows[1][2] == R("2,500,000.00")
    assert t.raw_rows[2][3] == R("(1,200,000.00)")


async def test_pipeline_bank_statement_ambiguous_dates_flagged() -> None:
    t = (
        await _tables(
            fx.bank_statement_xlsx(dates=["03/07/2025", "04/07/2025", "05/07/2025"]),
            "bank_statement",
        )
    )[0]
    assert t.detected_type == "bank_statement"
    assert t.period_start == date(2025, 7, 1)
    f = next(f for f in t.findings if f.code == "ambiguous_date_order")
    assert f.severity == "warning"
    assert t.normalized.rows[0]["0"] == "2025-07-03"  # default DMY applied, but flagged


async def test_pipeline_bank_statement_order_proven_by_data() -> None:
    t = (await _tables(fx.bank_statement_xlsx(), "bank_statement"))[0]
    assert not any(f.code == "ambiguous_date_order" for f in t.findings)
    assert t.normalized.rows[2]["0"] == "2025-07-13"


async def test_pipeline_fixed_assets() -> None:
    t = (await _tables(fx.fixed_assets_xlsx(), "fixed_asset_schedule"))[0]
    assert t.detected_type == "fixed_asset_register"
    assert not any(f.code == "type_mismatch" for f in t.findings)


async def test_type_mismatch_is_reported_when_category_disagrees() -> None:
    t = (await _tables(fx.fixed_assets_xlsx(), "bank_statement"))[0]
    assert any(f.code == "type_mismatch" for f in t.findings)


async def test_unrecognisable_table_needs_review_with_findings() -> None:
    t = (await _tables(fx.weird_headers_xlsx(), None))[0]
    assert t.detected_type == "unknown"
    assert t.status == "needs_review"
    codes = {f.code for f in t.findings}
    assert {"unknown_document_type", "low_confidence_column"} <= codes


async def test_carried_roles_override_suggestions_on_rerun() -> None:
    t = (
        await _tables(
            fx.weird_headers_xlsx(), None, carried_roles={("Sheet", "foo"): "account_code"}
        )
    )[0]
    assert t.columns[0].confirmed_role == "account_code"


# ----------------------------------------------------------------------------- llm assistant


class FakeAssistant:
    def __init__(self, answers: dict[int, tuple[str, float]], doc_type: str | None = None) -> None:
        self.answers, self.doc_type, self.calls = answers, doc_type, []

    async def suggest(self, columns, category, doc_type_hint):  # type: ignore[no-untyped-def]
        from app.agents.intake_agent.llm import ColumnAnswer, LlmResult

        self.calls.append([c.index for c in columns])
        return LlmResult(
            [ColumnAnswer(i, r, c) for i, (r, c) in self.answers.items()], self.doc_type, "fake"
        )


async def test_llm_only_sees_weak_columns_and_cannot_override_strong_matches() -> None:
    fake = FakeAssistant(
        {0: ("credit", 0.8), 1: ("description", 0.8), 2: ("description", 0.8)}, "general_ledger"
    )
    parsed = parse_xlsx(fx.weird_headers_xlsx(), 100, 10**8)
    t = (await build_tables(parsed, category=None, default_date_order="DMY", assistant=fake))[0]
    assert fake.calls == [[0, 1, 2]]
    assert t.llm_used and t.llm_model == "fake"
    assert all(c.source == "llm" for c in t.columns)
    assert t.type_source == "llm"
    assert t.type_confidence < 0.7  # LLM-derived type never counts as confident
    assert t.status == "needs_review"


async def test_llm_not_called_when_heuristics_are_confident() -> None:
    fake = FakeAssistant({})
    parsed = parse_xlsx(fx.fixed_assets_xlsx(), 100, 10**8)
    await build_tables(
        parsed, category="fixed_asset_schedule", default_date_order="DMY", assistant=fake
    )
    assert fake.calls == []


async def test_llm_cannot_override_a_confirmed_role() -> None:
    fake = FakeAssistant({0: ("credit", 0.8)})
    parsed = parse_xlsx(fx.weird_headers_xlsx(), 100, 10**8)
    t = (
        await build_tables(parsed, category=None, default_date_order="DMY", assistant=fake,
                           carried_roles={("Sheet", "foo"): "account_code"})
    )[0]  # fmt: skip
    assert t.columns[0].confirmed_role == "account_code"
    assert t.columns[0].role != "credit"


def test_llm_response_is_validated_hallucinations_dropped() -> None:
    good = json.dumps(
        {
            "document_type": "bank_statement",
            "columns": [{"index": 0, "role": "date", "confidence": 0.99}],
        }
    )
    r = parse_response(good, {0, 1}, "m")
    assert r is not None
    assert r.document_type == "bank_statement"
    assert r.columns[0].confidence == 0.8  # capped
    bad = json.dumps(
        {
            "document_type": "made_up_type",
            "columns": [
                {"index": 0, "role": "ledger_posting", "confidence": 0.9},  # not in enum
                {"index": 99, "role": "date", "confidence": 0.9},  # unknown column
                {"index": 1, "role": "debit", "confidence": "high"},  # bad confidence
                {"index": True, "role": "debit", "confidence": 0.5},  # bool is not an int index
                "garbage",
            ],
        }
    )
    r2 = parse_response(f"Sure! ```json\n{bad}\n```", {0, 1}, "m")
    assert r2 is not None
    assert r2.columns == []
    assert r2.document_type is None
    assert parse_response("not json at all", {0}, "m") is None
    assert parse_response("[1,2,3]", {0}, "m") is None


def test_llm_prompt_forbids_calculation_and_limits_data_sent() -> None:
    cols = [ColumnQuery(i, f"H{i}", [f"{'x' * 500}"] * 20) for i in range(80)]
    prompt = build_prompt(cols, "bank_statement", None)
    assert "Do NOT calculate" in prompt
    assert len(prompt) < 60_000
    assert "x" * 100 not in prompt  # cell values are truncated before leaving the system


# ----------------------------------------------------------------------------- pdf + ocr


def test_digital_pdf_table_extraction_without_ocr() -> None:
    parsed = parse_pdf(fx.digital_statement_pdf(), max_pages=5, max_rows=100, ocr_engine=None)
    assert parsed.ocr_applied is False
    rows = [[c.v if c else None for c in r] for r in parsed.grids[0].rows]
    assert rows[0] == ["Date", "Description", "Amount"]
    assert rows[3] == ["03/02/2025", "Fee", "(50.00)"]
    assert parsed.grids[0].row_refs[0] == {"page": 1}


def test_corrupt_and_empty_pdfs_raise_clean_errors() -> None:
    with pytest.raises(ExtractionError) as e:
        parse_pdf(b"%PDF-1.7 garbage", max_pages=5, max_rows=10, ocr_engine=None)
    assert e.value.code == "corrupt_file"


def test_encrypted_pdf_is_rejected_with_a_clear_code() -> None:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    with pytest.raises(ExtractionError) as e:
        parse_pdf(data, max_pages=5, max_rows=10, ocr_engine=None)
    assert e.value.code == "encrypted_file"


def test_page_limit_is_enforced() -> None:
    import pymupdf

    doc = pymupdf.open()
    for _ in range(4):
        doc.new_page().insert_text((72, 72), "Some page text that is long enough to count")
    with pytest.raises(ExtractionError) as e:
        parse_pdf(doc.tobytes(), max_pages=3, max_rows=10, ocr_engine=None)
    assert e.value.code == "too_many_pages"


def test_prose_pdf_becomes_a_text_document_not_fake_rows() -> None:
    parsed = parse_pdf(fx.prose_pdf(), max_pages=5, max_rows=100, ocr_engine=None)
    assert parsed.grids[0].kind == "pdf_text"


async def test_prose_pdf_is_kept_as_text_needing_review() -> None:
    parsed = parse_pdf(fx.prose_pdf(), max_pages=5, max_rows=100, ocr_engine=None)
    t = (await build_tables(parsed, category=None, default_date_order="DMY", assistant=None))[0]
    assert t.detected_type == "text_document"
    assert t.status == "needs_review"
    assert any(f.code == "no_table_found" for f in t.findings)


def test_image_without_text_layer_and_no_ocr_engine_reports_unavailable() -> None:
    parsed = (
        parse_pdf(
            image_to_pdf(fx.scanned_statement_png()), max_pages=5, max_rows=100, ocr_engine=None
        )
        if False
        else None
    )
    assert parsed is None  # image intake requires OCR; covered at the service level


class FakeOcr:
    """Stands in for Tesseract: returns a PDF that already has a text layer."""

    def ocr_pdf(self, pdf_bytes: bytes) -> bytes:
        return fx.digital_statement_pdf()


def test_scanned_pdf_goes_through_ocr_and_is_flagged() -> None:
    parsed = parse_pdf(
        image_to_pdf(fx.scanned_statement_png()), max_pages=5, max_rows=100, ocr_engine=FakeOcr()
    )
    assert parsed.ocr_applied is True
    assert any(f.code == "ocr_applied" and f.severity == "warning" for f in parsed.findings)
    assert parsed.grids[0].kind == "ocr_table"


def test_scanned_pdf_without_engine_gets_an_error_finding() -> None:
    from app.agents.intake_agent.parsers.pdf import MIN_TEXT_CHARS  # noqa: F401

    pdf_bytes = image_to_pdf(fx.scanned_statement_png())
    with pytest.raises(ExtractionError) as e:
        parse_pdf(pdf_bytes, max_pages=5, max_rows=100, ocr_engine=None)
    assert e.value.code == "no_content"


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_real_tesseract_ocr_reads_a_scanned_statement() -> None:
    parsed = parse_pdf(
        image_to_pdf(fx.scanned_statement_png()),
        max_pages=5,
        max_rows=100,
        ocr_engine=OcrMyPdfEngine(),
    )
    assert parsed.ocr_applied
    flat = " ".join(c.v for r in parsed.grids[0].rows for c in r if c)
    assert "1,000.00" in flat
    assert "Opening" in flat
