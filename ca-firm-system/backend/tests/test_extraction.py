"""Phase 3: extraction service, review API, authorization, isolation, failure handling, runner."""

import asyncio
import hashlib
import io
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.intake_agent import service as intake
from app.agents.intake_agent.llm import ColumnAnswer, LlmResult
from app.core.config import Settings, get_settings
from app.integrations.storage.s3 import S3ObjectStore
from app.models import (
    AuditEvent,
    DataQualityFinding,
    Document,
    ExtractedColumn,
    ExtractedRow,
    ExtractedTable,
    ExtractionRun,
    OutboxEvent,
)
from tests import intake_fixtures as fx
from tests.conftest import ACCOUNTANT, CA_REVIEWER, CLIENT_USER, FIRM_ADMIN, World, login
from tests.test_documents import API, Setup, read_object


@pytest.fixture
async def s(api: httpx.AsyncClient, world: World) -> Setup:
    return await Setup(api, world).build()


def settings(**over: Any) -> Settings:
    return get_settings().model_copy(update=over)


class FakeOcr:
    def ocr_pdf(self, pdf_bytes: bytes) -> bytes:
        return fx.digital_statement_pdf()


class Assistant:
    def __init__(
        self, answers: dict[int, tuple[str, float]] | None, doc_type: str | None = None
    ) -> None:
        self.answers, self.doc_type, self.calls = answers, doc_type, 0

    async def suggest(self, columns: Any, category: Any, hint: Any) -> LlmResult | None:
        self.calls += 1
        if self.answers is None:
            return None  # simulates LiteLLM being down
        return LlmResult(
            [ColumnAnswer(i, r, c) for i, (r, c) in self.answers.items()],
            self.doc_type,
            "fake-model",
        )


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def upload_and_extract(
    s: Setup, sf: async_sessionmaker[AsyncSession], store: S3ObjectStore, data: bytes,
    name: str = "tb.xlsx", category: str = "trial_balance", **kw: Any,
) -> str:  # fmt: skip
    r = await s.upload(data, name, category)
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    await intake.extract_document(
        sf, store, kw.pop("settings", settings()), uuid.UUID(doc_id), **kw
    )
    return str(doc_id)


def ext_url(s: Setup, doc_id: str, tail: str = "") -> str:
    return f"{s.url}/{doc_id}/extraction{tail}"


# ------------------------------------------------------------------------------ happy path


async def test_extraction_end_to_end_keeps_original_byte_identical(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    db: AsyncSession,
) -> None:
    data = fx.messy_trial_balance_xlsx()
    doc_id = await upload_and_extract(s, session_factory, store, data)

    doc = await db.get(Document, uuid.UUID(doc_id))
    assert doc is not None
    await db.refresh(doc)
    assert doc.status == "processed"
    assert doc.sha256 == hashlib.sha256(data).hexdigest()  # identity untouched
    assert read_object(store, doc.object_key) == data  # original never modified

    r = await s.api.get(ext_url(s, doc_id), headers=s.hdr)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["document_status"] == "processed"
    run = body["run"]
    assert (run["status"], run["version"], run["trigger"]) == ("completed", 1, "auto")
    assert run["summary"]["tables"] == 2  # visible sheet + hidden sheet were both read
    t = body["tables"][0]
    assert (t["name"], t["detected_type"], t["effective_type"], t["currency"]) == (
        "TB June", "trial_balance", "trial_balance", "PKR",
    )  # fmt: skip
    assert t["period_end"] == "2025-06-30" and t["n_rows"] == 5 and t["status"] == "ok"
    assert [c["effective_role"] for c in t["columns"]] == [
        "account_code",
        "account_name",
        "debit",
        "credit",
    ]

    rows = (await s.api.get(ext_url(s, doc_id, f"/tables/{t['id']}/rows"), headers=s.hdr)).json()
    assert rows["total"] == 5
    first = rows["items"][0]
    assert first["row_index"] == 6  # source row number from the workbook
    assert first["source_ref"] == {"sheet": "TB June", "row": 6}
    assert first["raw"]["2"] == {"v": "150000.5", "t": "n"}
    assert first["normalized"]["2"] == "150000.50"
    second = rows["items"][1]
    assert second["raw"]["2"]["v"] == "2,500,000.00" and second["normalized"]["2"] == "2500000.00"
    assert rows["items"][4]["flags"][0]["code"] == "total_row"

    audit = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "extraction.completed", AuditEvent.target_id == doc.id
        )
    )
    assert (
        audit is not None
        and audit.actor_email == "system:intake"
        and audit.client_id == s.client.id
    )


async def test_extraction_does_not_emit_outbox_events_or_touch_the_upload_event(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    db: AsyncSession,
) -> None:
    await upload_and_extract(
        s, session_factory, store, fx.fixed_assets_xlsx(), category="fixed_asset_schedule"
    )
    events = (
        await db.scalars(select(OutboxEvent).where(OutboxEvent.client_id == s.client.id))
    ).all()
    assert [e.event_type for e in events] == ["file.uploaded"]


async def test_paging_and_flagged_only_filter(
    s: Setup, session_factory: async_sessionmaker[AsyncSession], store: S3ObjectStore
) -> None:
    doc_id = await upload_and_extract(s, session_factory, store, fx.messy_trial_balance_xlsx())
    summary = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()
    tid = summary["tables"][0]["id"]
    page = (
        await s.api.get(ext_url(s, doc_id, f"/tables/{tid}/rows?limit=2&offset=3"), headers=s.hdr)
    ).json()
    assert (page["total"], page["limit"], page["offset"], len(page["items"])) == (5, 2, 3, 2)
    flagged = (
        await s.api.get(ext_url(s, doc_id, f"/tables/{tid}/rows?flagged_only=true"), headers=s.hdr)
    ).json()
    assert flagged["total"] >= 1
    assert all(r["flags"] for r in flagged["items"])
    assert (
        await s.api.get(ext_url(s, doc_id, f"/tables/{tid}/rows?limit=0"), headers=s.hdr)
    ).status_code == 422
    assert (
        await s.api.get(ext_url(s, doc_id, f"/tables/{tid}/rows?limit=500"), headers=s.hdr)
    ).status_code == 422


async def test_csv_and_digital_pdf_and_scanned_image_are_extracted(
    s: Setup, session_factory: async_sessionmaker[AsyncSession], store: S3ObjectStore
) -> None:
    csv_id = await upload_and_extract(
        s, session_factory, store, b"Date,Description,Withdrawals,Deposits,Balance\n13/02/2025,Rent,500.00,,9500.00\n",
        name="bank.csv", category="bank_statement",
    )  # fmt: skip
    pdf_id = await upload_and_extract(
        s, session_factory, store, fx.digital_statement_pdf(), name="bank.pdf", category="bank_statement"
    )  # fmt: skip
    png_id = await upload_and_extract(
        s, session_factory, store, fx.scanned_statement_png(), name="scan.png", category="bank_statement",
        ocr_engine=FakeOcr(),
    )  # fmt: skip
    csv = (await s.api.get(ext_url(s, csv_id), headers=s.hdr)).json()
    assert csv["tables"][0]["detected_type"] == "bank_statement"
    pdf = (await s.api.get(ext_url(s, pdf_id), headers=s.hdr)).json()
    assert pdf["document_status"] == "processed" and pdf["tables"][0]["kind"] == "pdf_table"
    png = (await s.api.get(ext_url(s, png_id), headers=s.hdr)).json()
    assert png["tables"][0]["kind"] == "ocr_table"
    findings = (await s.api.get(ext_url(s, png_id, "/findings"), headers=s.hdr)).json()
    assert "ocr_applied" in [f["code"] for f in findings]


# ------------------------------------------------------------------------------ corrections


async def test_column_role_correction_renormalizes_without_touching_raw(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    db: AsyncSession,
) -> None:
    doc_id = await upload_and_extract(
        s, session_factory, store, fx.weird_headers_xlsx(), category="bank_statement"
    )
    summary = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()
    t = summary["tables"][0]
    tid = t["id"]
    assert t["status"] == "needs_review" and t["effective_type"] == "unknown"
    assert [c["effective_role"] for c in t["columns"]] == ["other", "other", "amount"]
    codes = {
        f["code"] for f in (await s.api.get(ext_url(s, doc_id, "/findings"), headers=s.hdr)).json()
    }
    assert {"unknown_document_type", "low_confidence_column"} <= codes

    def rows_url() -> str:
        return ext_url(s, doc_id, f"/tables/{tid}/rows")

    before = (await s.api.get(rows_url(), headers=s.hdr)).json()["items"]
    assert before[0]["normalized"]["2"] == "10.00"

    # 1) treat the amount column as free text -> normalized becomes plain text, raw is identical
    r = await s.api.patch(
        ext_url(s, doc_id, f"/tables/{tid}/columns/2"), json={"role": "other"}, headers=s.hdr
    )
    assert r.status_code == 200, r.text
    after = (await s.api.get(rows_url(), headers=s.hdr)).json()["items"]
    assert after[0]["normalized"]["2"] == "10"
    assert [x["raw"] for x in after] == [x["raw"] for x in before]

    # 2) ignore a column -> it disappears from normalized data but stays in raw
    await s.api.patch(
        ext_url(s, doc_id, f"/tables/{tid}/columns/1"), json={"role": "ignore"}, headers=s.hdr
    )
    after2 = (await s.api.get(rows_url(), headers=s.hdr)).json()["items"]
    assert "1" not in after2[0]["normalized"] and "1" in after2[0]["raw"]

    # 3) back to amount, confirm the rest and set the type -> table is no longer in review
    for col, role in ((0, "description"), (1, "description"), (2, "amount")):
        r = await s.api.patch(
            ext_url(s, doc_id, f"/tables/{tid}/columns/{col}"), json={"role": role}, headers=s.hdr
        )
        assert r.status_code == 200
    r = await s.api.patch(
        ext_url(s, doc_id, f"/tables/{tid}"),
        json={"confirmed_type": "inventory_report"},
        headers=s.hdr,
    )
    assert r.status_code == 200
    t2 = r.json()
    assert (t2["status"], t2["effective_type"], t2["detected_type"]) == (
        "ok",
        "inventory_report",
        "unknown",
    )
    assert all(c["confirmed_role"] for c in t2["columns"])
    final = (await s.api.get(rows_url(), headers=s.hdr)).json()["items"]
    assert final[0]["normalized"]["2"] == "10.00"
    open_codes = {
        f["code"]
        for f in (
            await s.api.get(ext_url(s, doc_id, "/findings?status=open"), headers=s.hdr)
        ).json()
    }
    assert "unknown_document_type" not in open_codes and "low_confidence_column" not in open_codes

    audits = (
        await db.scalars(
            select(AuditEvent).where(
                AuditEvent.client_id == s.client.id, AuditEvent.action.like("extraction.%")
            )
        )
    ).all()
    actions = [a.action for a in audits]
    assert (
        actions.count("extraction.column_role_set") == 5 and "extraction.table_type_set" in actions
    )
    changed = next(a for a in audits if a.action == "extraction.column_role_set")
    assert changed.actor_user_id == s.admin.id
    assert changed.event_metadata["from"] == "amount" and changed.event_metadata["to"] == "other"


async def test_correction_validation_errors(
    s: Setup, session_factory: async_sessionmaker[AsyncSession], store: S3ObjectStore
) -> None:
    doc_id = await upload_and_extract(
        s, session_factory, store, fx.weird_headers_xlsx(), category="bank_statement"
    )
    tid = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()["tables"][0]["id"]
    col = ext_url(s, doc_id, f"/tables/{tid}/columns/0")
    assert (await s.api.patch(col, json={"role": "ledger_entry"}, headers=s.hdr)).status_code == 422
    assert (
        await s.api.patch(col, json={"role": "debit", "x": 1}, headers=s.hdr)
    ).status_code == 422
    assert (await s.api.patch(col, json={}, headers=s.hdr)).status_code == 422
    nocol = ext_url(s, doc_id, f"/tables/{tid}/columns/99")
    assert (await s.api.patch(nocol, json={"role": "debit"}, headers=s.hdr)).status_code == 404
    bad_t = ext_url(s, doc_id, f"/tables/{uuid.uuid4()}/columns/0")
    assert (await s.api.patch(bad_t, json={"role": "debit"}, headers=s.hdr)).status_code == 404
    typ = ext_url(s, doc_id, f"/tables/{tid}")
    assert (
        await s.api.patch(typ, json={"confirmed_type": "journal"}, headers=s.hdr)
    ).status_code == 422


async def test_findings_review_workflow(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    db: AsyncSession,
) -> None:
    doc_id = await upload_and_extract(
        s, session_factory, store, fx.weird_headers_xlsx(), category="bank_statement"
    )
    findings = (await s.api.get(ext_url(s, doc_id, "/findings"), headers=s.hdr)).json()
    assert findings and [f["severity"] for f in findings] == sorted(
        (f["severity"] for f in findings), key=["error", "warning", "info"].index
    )
    warn = next(f for f in findings if f["severity"] == "warning")
    r = await s.api.patch(
        ext_url(s, doc_id, f"/findings/{warn['id']}"),
        json={"status": "dismissed", "note": "known"},
        headers=s.hdr,
    )
    assert (
        r.status_code == 200
        and r.json()["status"] == "dismissed"
        and r.json()["resolution_note"] == "known"
    )
    row = await db.scalar(
        select(DataQualityFinding).where(DataQualityFinding.id == uuid.UUID(warn["id"]))
    )
    assert row is not None
    await db.refresh(row)
    assert row.resolved_by == s.admin.id and row.resolved_at is not None
    r = await s.api.patch(
        ext_url(s, doc_id, f"/findings/{warn['id']}"), json={"status": "open"}, headers=s.hdr
    )
    assert r.json()["status"] == "open" and r.json()["resolution_note"] is None
    only_open = (
        await s.api.get(ext_url(s, doc_id, "/findings?status=open&severity=warning"), headers=s.hdr)
    ).json()
    assert all(f["status"] == "open" and f["severity"] == "warning" for f in only_open)
    assert (
        await s.api.get(ext_url(s, doc_id, "/findings?status=bogus"), headers=s.hdr)
    ).status_code == 422
    assert (
        await s.api.patch(
            ext_url(s, doc_id, f"/findings/{uuid.uuid4()}"),
            json={"status": "resolved"},
            headers=s.hdr,
        )
    ).status_code == 404


async def test_error_findings_cannot_be_dismissed(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    db: AsyncSession,
) -> None:
    doc_id = await upload_and_extract(
        s, session_factory, store, fx.fixed_assets_xlsx(), category="fixed_asset_schedule"
    )
    run = await db.scalar(
        select(ExtractionRun).where(ExtractionRun.document_id == uuid.UUID(doc_id))
    )
    assert run is not None
    f = DataQualityFinding(
        run_id=run.id, firm_id=run.firm_id, client_id=run.client_id, period_id=run.period_id,
        document_id=run.document_id, code="synthetic_error", severity="error", message="x",
    )  # fmt: skip
    db.add(f)
    await db.commit()
    r = await s.api.patch(
        ext_url(s, doc_id, f"/findings/{f.id}"), json={"status": "dismissed"}, headers=s.hdr
    )
    assert r.status_code == 422
    assert (
        await s.api.patch(
            ext_url(s, doc_id, f"/findings/{f.id}"), json={"status": "resolved"}, headers=s.hdr
        )
    ).status_code == 200


# ------------------------------------------------------------------------------ dates, periods


async def test_ambiguous_dates_surface_as_a_reviewable_finding(
    s: Setup, session_factory: async_sessionmaker[AsyncSession], store: S3ObjectStore
) -> None:
    doc_id = await upload_and_extract(
        s,
        session_factory,
        store,
        fx.dated_xlsx(["03/04/2025", "05/06/2025"]),
        name="d.xlsx",
        category="bank_statement",
    )
    findings = (await s.api.get(ext_url(s, doc_id, "/findings"), headers=s.hdr)).json()
    f = next(f for f in findings if f["code"] == "ambiguous_date_order")
    assert (
        f["severity"] == "warning"
        and f["origin"] == "normalize"
        and f["details"]["assumed_order"] == "DMY"
    )
    tid = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()["tables"][0]["id"]
    rows = (await s.api.get(ext_url(s, doc_id, f"/tables/{tid}/rows"), headers=s.hdr)).json()[
        "items"
    ]
    assert rows[0]["normalized"]["0"] == "2025-04-03"
    # the MDY house setting flips the reading for a re-run of the same file
    doc2 = await upload_and_extract(
        s, session_factory, store, fx.dated_xlsx(["03/04/2025", "05/06/2025", "07/08/2025"]),
        name="d2.xlsx", category="bank_statement", settings=settings(intake_default_date_order="MDY"),
    )  # fmt: skip
    t2 = (await s.api.get(ext_url(s, doc2), headers=s.hdr)).json()["tables"][0]["id"]
    rows2 = (await s.api.get(ext_url(s, doc2, f"/tables/{t2}/rows"), headers=s.hdr)).json()["items"]
    assert rows2[0]["normalized"]["0"] == "2025-03-04"


async def test_period_mismatch_is_reported(
    s: Setup, session_factory: async_sessionmaker[AsyncSession], store: S3ObjectStore
) -> None:
    doc_id = await upload_and_extract(
        s, session_factory, store, fx.messy_trial_balance_xlsx("30 June 2024"), name="old.xlsx"
    )
    findings = (await s.api.get(ext_url(s, doc_id, "/findings"), headers=s.hdr)).json()
    f = next(f for f in findings if f["code"] == "period_mismatch")
    assert f["details"]["detected_end"] == "2024-06-30"


async def test_row_cap_truncates_with_a_warning(
    s: Setup, session_factory: async_sessionmaker[AsyncSession], store: S3ObjectStore
) -> None:
    data = (
        "Date,Description,Amount\n"
        + "\n".join(f"{(i % 28) + 1:02d}/02/2025,Row {i},{i}.00" for i in range(300))
    ).encode()
    doc_id = await upload_and_extract(
        s,
        session_factory,
        store,
        data,
        name="big.csv",
        category="bank_statement",
        settings=settings(intake_max_rows=100),
    )
    body = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()
    assert body["tables"][0]["n_rows"] <= 100
    codes = [
        f["code"] for f in (await s.api.get(ext_url(s, doc_id, "/findings"), headers=s.hdr)).json()
    ]
    assert "rows_truncated" in codes


# ------------------------------------------------------------------------------ LLM assist


async def test_llm_suggestions_are_marked_for_review_and_never_auto_accepted(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    db: AsyncSession,
) -> None:
    fake = Assistant(
        {0: ("description", 0.95), 1: ("description", 0.9), 2: ("amount", 0.9)}, "inventory_report"
    )
    doc_id = await upload_and_extract(
        s,
        session_factory,
        store,
        fx.weird_headers_xlsx(),
        category="bank_statement",
        assistant=fake,
    )
    assert fake.calls == 1
    body = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()
    t = body["tables"][0]
    assert body["run"]["llm_used"] is True
    assert t["status"] == "needs_review" and t["type_source"] == "llm"
    assert all(c["role_source"] == "llm" and c["confidence"] <= 0.8 for c in t["columns"])
    codes = {
        f["code"] for f in (await s.api.get(ext_url(s, doc_id, "/findings"), headers=s.hdr)).json()
    }
    assert {"llm_suggested_role", "llm_suggested_type"} <= codes
    run = await db.scalar(
        select(ExtractionRun).where(ExtractionRun.document_id == uuid.UUID(doc_id))
    )
    assert run is not None and run.llm_model == "fake-model"
    # confirming everything clears the review state
    for c in t["columns"]:
        await s.api.patch(
            ext_url(s, doc_id, f"/tables/{t['id']}/columns/{c['col_index']}"),
            json={"role": c["effective_role"]},
            headers=s.hdr,
        )
    r = await s.api.patch(
        ext_url(s, doc_id, f"/tables/{t['id']}"),
        json={"confirmed_type": "inventory_report"},
        headers=s.hdr,
    )
    assert r.json()["status"] == "ok"


async def test_llm_outage_falls_back_to_heuristics_and_still_succeeds(
    s: Setup, session_factory: async_sessionmaker[AsyncSession], store: S3ObjectStore
) -> None:
    down = Assistant(None)
    doc_id = await upload_and_extract(
        s,
        session_factory,
        store,
        fx.weird_headers_xlsx(),
        category="bank_statement",
        assistant=down,
    )
    body = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()
    assert down.calls == 1
    assert body["document_status"] == "processed" and body["run"]["llm_used"] is False
    assert body["tables"][0]["status"] == "needs_review"


# ------------------------------------------------------------------------------ failures


def zip_without_workbook() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/workbook.xml", "<workbook/>")
    return buf.getvalue()


async def test_corrupt_file_fails_cleanly_without_partial_data_or_leaked_details(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    db: AsyncSession,
) -> None:
    doc_id = await upload_and_extract(
        s, session_factory, store, zip_without_workbook(), name="bad.xlsx"
    )
    body = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()
    assert body["document_status"] == "failed"
    assert body["run"]["status"] == "failed" and body["run"]["error_code"] == "corrupt_file"
    assert body["tables"] == []
    assert "Traceback" not in (body["run"]["error_message"] or "")
    n = await db.scalar(
        select(text("count(*)"))
        .select_from(ExtractedTable)
        .where(ExtractedTable.document_id == uuid.UUID(doc_id))
    )
    assert n == 0
    failure = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "extraction.failed", AuditEvent.target_id == uuid.UUID(doc_id)
        )
    )
    assert (
        failure is not None
        and failure.outcome == "failure"
        and failure.event_metadata["error_code"] == "corrupt_file"
    )


async def test_image_without_ocr_available_fails_with_a_clear_code(
    s: Setup, session_factory: async_sessionmaker[AsyncSession], store: S3ObjectStore
) -> None:
    doc_id = await upload_and_extract(
        s, session_factory, store, fx.scanned_statement_png(), name="scan.png", category="bank_statement",
        settings=settings(intake_ocr_enabled=False),
    )  # fmt: skip
    run = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()["run"]
    assert run["status"] == "failed" and run["error_code"] == "ocr_unavailable"


async def test_unexpected_parser_crash_is_contained_and_generic(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*a: Any, **k: Any) -> None:
        raise RuntimeError("secret-internal-path /etc/passwd")

    monkeypatch.setattr(intake, "parse_bytes", boom)
    doc_id = await upload_and_extract(
        s, session_factory, store, fx.fixed_assets_xlsx(), category="fixed_asset_schedule"
    )
    run = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()["run"]
    assert run["error_code"] == "internal_error"
    assert "passwd" not in (run["error_message"] or "")


async def test_empty_workbook_and_prose_only_pdf(
    s: Setup, session_factory: async_sessionmaker[AsyncSession], store: S3ObjectStore
) -> None:
    import openpyxl

    buf = io.BytesIO()
    openpyxl.Workbook().save(buf)
    doc_id = await upload_and_extract(s, session_factory, store, buf.getvalue(), name="empty.xlsx")
    assert (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()["run"][
        "error_code"
    ] == "empty_file"
    pdf_id = await upload_and_extract(
        s, session_factory, store, fx.prose_pdf(), name="letter.pdf", category="other"
    )
    body = (await s.api.get(ext_url(s, pdf_id), headers=s.hdr)).json()
    assert body["document_status"] == "processed"
    assert (
        body["tables"][0]["effective_type"] == "text_document"
        and body["tables"][0]["status"] == "needs_review"
    )


# ------------------------------------------------------------------------------ re-run + versions


async def test_rerun_creates_a_new_version_and_carries_confirmed_roles(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    db: AsyncSession,
) -> None:
    doc_id = await upload_and_extract(
        s, session_factory, store, fx.weird_headers_xlsx(), category="bank_statement"
    )
    tid = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()["tables"][0]["id"]
    await s.api.patch(
        ext_url(s, doc_id, f"/tables/{tid}/columns/0"), json={"role": "item_code"}, headers=s.hdr
    )
    await s.api.patch(
        ext_url(s, doc_id, f"/tables/{tid}"),
        json={"confirmed_type": "inventory_report"},
        headers=s.hdr,
    )

    r = await s.api.post(ext_url(s, doc_id, "/rerun"), headers=s.hdr)
    assert r.status_code == 202 and r.json()["status"] == "queued"
    assert (
        await s.api.post(ext_url(s, doc_id, "/rerun"), headers=s.hdr)
    ).status_code == 409  # already queued

    claimed = await intake.claim_next(session_factory)
    assert (
        claimed is not None and claimed[0] == uuid.UUID(doc_id) or claimed is not None
    )  # other tests may queue docs
    while claimed is not None and claimed[0] != uuid.UUID(doc_id):
        await intake.process_run(
            session_factory, store, settings(), document_id=claimed[0], run_id=claimed[1]
        )
        claimed = await intake.claim_next(session_factory)
    assert claimed is not None
    assert await intake.process_run(
        session_factory, store, settings(), document_id=claimed[0], run_id=claimed[1]
    )

    body = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()
    assert body["run"]["version"] == 2
    t = body["tables"][0]
    assert t["confirmed_type"] == "inventory_report"  # decision carried over
    assert t["columns"][0]["confirmed_role"] == "item_code"  # ... by (sheet, header)
    runs = (
        await db.scalars(
            select(ExtractionRun)
            .where(ExtractionRun.document_id == uuid.UUID(doc_id))
            .order_by(ExtractionRun.version)
        )
    ).all()
    assert [(x.version, x.is_current, x.status) for x in runs] == [
        (1, False, "completed"),
        (2, True, "completed"),
    ]
    # the old run's data is retained for audit, but old table ids are no longer addressable
    assert (
        await s.api.get(ext_url(s, doc_id, f"/tables/{tid}/rows"), headers=s.hdr)
    ).status_code == 404


async def test_rerun_requires_a_finished_document(
    s: Setup, session_factory: async_sessionmaker[AsyncSession], store: S3ObjectStore
) -> None:
    r = await s.upload(fx.fixed_assets_xlsx(), "a.xlsx", "fixed_asset_schedule")
    assert (
        await s.api.post(ext_url(s, r.json()["id"], "/rerun"), headers=s.hdr)
    ).status_code == 409


async def test_only_one_runner_can_claim_a_document(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    db: AsyncSession,
) -> None:
    await db.execute(
        text("UPDATE documents SET status = 'processed' WHERE status IN ('uploaded','queued')")
    )
    await db.commit()
    r = await s.upload(fx.fixed_assets_xlsx(), "a.xlsx", "fixed_asset_schedule")
    claims = await asyncio.gather(*(intake.claim_next(session_factory) for _ in range(6)))
    won = [c for c in claims if c is not None]
    assert len(won) == 1 and str(won[0][0]) == r.json()["id"]
    assert await intake.claim_next(session_factory) is None
    runs = (
        await db.scalars(select(ExtractionRun).where(ExtractionRun.document_id == won[0][0]))
    ).all()
    assert len(runs) == 1 and runs[0].status == "running"


async def test_stale_runs_are_reclaimed_and_attempts_are_bounded(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    db: AsyncSession,
) -> None:
    await db.execute(
        text("UPDATE documents SET status = 'processed' WHERE status IN ('uploaded','queued')")
    )
    await db.commit()
    r = await s.upload(fx.fixed_assets_xlsx(), "a.xlsx", "fixed_asset_schedule")
    doc_id = uuid.UUID(r.json()["id"])
    cfg = settings(intake_stale_after_minutes=15)
    for attempt in range(1, 4):
        claimed = await intake.claim_next(session_factory)
        assert claimed is not None and claimed[0] == doc_id
        # a fresh run is NOT stale
        assert await intake.reclaim_stale(session_factory, cfg) == 0
        await db.execute(
            update(ExtractionRun)
            .where(ExtractionRun.id == claimed[1])
            .values(started_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await db.commit()
        assert await intake.reclaim_stale(session_factory, cfg) >= 1
        doc = await db.get(Document, doc_id)
        assert doc is not None
        await db.refresh(doc)
        assert doc.status == ("queued" if attempt < 3 else "failed")
    run = await db.scalar(
        select(ExtractionRun).where(ExtractionRun.document_id == doc_id, ExtractionRun.version == 3)
    )
    assert run is not None and (run.status, run.error_code) == ("failed", "interrupted")


async def test_background_runner_processes_uploaded_documents_and_stops_cleanly(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    db: AsyncSession,
) -> None:
    await db.execute(
        text("UPDATE documents SET status = 'processed' WHERE status IN ('uploaded','queued')")
    )
    await db.commit()
    r = await s.upload(fx.messy_trial_balance_xlsx(), "tb.xlsx", "trial_balance")
    doc_id = r.json()["id"]
    stop = asyncio.Event()
    task = asyncio.create_task(
        intake.run_intake_loop(
            session_factory, store, settings(intake_poll_interval_seconds=0.05), stop
        )
    )
    try:
        for _ in range(100):
            body = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()
            if body["document_status"] == "processed":
                break
            await asyncio.sleep(0.1)
        assert body["document_status"] == "processed" and body["run"]["trigger"] == "auto"
    finally:
        stop.set()
        await asyncio.wait_for(task, 5)


# ------------------------------------------------------------------------------ authorization


async def test_permissions_and_roles(
    s: Setup, session_factory: async_sessionmaker[AsyncSession], store: S3ObjectStore
) -> None:
    doc_id = await upload_and_extract(
        s, session_factory, store, fx.weird_headers_xlsx(), category="bank_statement"
    )
    tid = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()["tables"][0]["id"]
    col, typ, rerun = (
        ext_url(s, doc_id, f"/tables/{tid}/columns/0"),
        ext_url(s, doc_id, f"/tables/{tid}"),
        ext_url(s, doc_id, "/rerun"),
    )

    # client_user: may read, may not review or re-run
    cu = await s.world.user(s.firm, CLIENT_USER)
    await s.world.assign(cu, s.client)
    h = await login(s.api, cu)
    assert (await s.api.get(ext_url(s, doc_id), headers=h)).status_code == 200
    assert (
        await s.api.get(ext_url(s, doc_id, f"/tables/{tid}/rows"), headers=h)
    ).status_code == 200
    assert (await s.api.get(ext_url(s, doc_id, "/findings"), headers=h)).status_code == 200
    assert (await s.api.patch(col, json={"role": "debit"}, headers=h)).status_code == 403
    assert (
        await s.api.patch(typ, json={"confirmed_type": "unknown"}, headers=h)
    ).status_code == 403
    assert (await s.api.post(rerun, headers=h)).status_code == 403
    fid = (await s.api.get(ext_url(s, doc_id, "/findings"), headers=h)).json()[0]["id"]
    assert (
        await s.api.patch(
            ext_url(s, doc_id, f"/findings/{fid}"), json={"status": "resolved"}, headers=h
        )
    ).status_code == 403

    # assigned accountant / reviewer: full review rights
    for role in (ACCOUNTANT, CA_REVIEWER):
        u = await s.world.user(s.firm, role)
        await s.world.assign(u, s.client)
        hu = await login(s.api, u)
        assert (await s.api.patch(col, json={"role": "description"}, headers=hu)).status_code == 200

    # no token
    assert (await s.api.get(ext_url(s, doc_id))).status_code == 401
    assert (await s.api.patch(col, json={"role": "debit"})).status_code == 401
    assert (await s.api.post(rerun)).status_code == 401


async def test_unassigned_users_and_other_firms_get_404_everywhere(
    s: Setup, session_factory: async_sessionmaker[AsyncSession], store: S3ObjectStore
) -> None:
    doc_id = await upload_and_extract(
        s, session_factory, store, fx.weird_headers_xlsx(), category="bank_statement"
    )
    summary = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()
    tid = summary["tables"][0]["id"]
    fid = (await s.api.get(ext_url(s, doc_id, "/findings"), headers=s.hdr)).json()[0]["id"]
    attempts = [
        ("get", ext_url(s, doc_id), None), ("get", ext_url(s, doc_id, f"/tables/{tid}/rows"), None),
        ("get", ext_url(s, doc_id, "/findings"), None),
        ("patch", ext_url(s, doc_id, f"/tables/{tid}/columns/0"), {"role": "debit"}),
        ("patch", ext_url(s, doc_id, f"/tables/{tid}"), {"confirmed_type": "unknown"}),
        ("patch", ext_url(s, doc_id, f"/findings/{fid}"), {"status": "resolved"}),
        ("post", ext_url(s, doc_id, "/rerun"), None),
    ]  # fmt: skip

    outsiders = []
    unassigned = await s.world.user(
        s.firm, ACCOUNTANT, label="unassigned"
    )  # same firm, not assigned
    outsiders.append(await login(s.api, unassigned))
    other_firm = await s.world.firm("Other")
    outsiders.append(await login(s.api, await s.world.user(other_firm, FIRM_ADMIN)))
    for h in outsiders:
        for method, url, body in attempts:
            resp = await getattr(s.api, method)(url, headers=h, **({"json": body} if body else {}))
            assert resp.status_code == 404, (method, url, resp.status_code)

    # state is unchanged by the failed attempts
    after = (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).json()
    assert after["tables"][0]["columns"] == summary["tables"][0]["columns"]
    assert after["document_status"] == "processed"


async def test_table_and_finding_ids_cannot_be_used_across_documents_or_clients(
    s: Setup, session_factory: async_sessionmaker[AsyncSession], store: S3ObjectStore
) -> None:
    a = await upload_and_extract(
        s, session_factory, store, fx.weird_headers_xlsx(), name="a.xlsx", category="bank_statement"
    )
    b = await upload_and_extract(
        s,
        session_factory,
        store,
        fx.fixed_assets_xlsx(),
        name="b.xlsx",
        category="fixed_asset_schedule",
    )
    tid_a = (await s.api.get(ext_url(s, a), headers=s.hdr)).json()["tables"][0]["id"]
    fid_a = (await s.api.get(ext_url(s, a, "/findings"), headers=s.hdr)).json()[0]["id"]
    # A's ids through B's document path
    assert (
        await s.api.get(ext_url(s, b, f"/tables/{tid_a}/rows"), headers=s.hdr)
    ).status_code == 404
    assert (
        await s.api.patch(
            ext_url(s, b, f"/tables/{tid_a}/columns/0"), json={"role": "debit"}, headers=s.hdr
        )
    ).status_code == 404
    assert (
        await s.api.patch(
            ext_url(s, b, f"/findings/{fid_a}"), json={"status": "resolved"}, headers=s.hdr
        )
    ).status_code == 404
    # same firm, different client (admin can reach both): the client in the URL must match
    other = await s.world.client(s.firm)
    r = await s.api.post(
        f"{API}/clients/{other.id}/periods",
        json={"label": "FY2025", "start_date": "2025-01-01", "end_date": "2025-12-31"},
        headers=s.hdr,
    )
    wrong = f"{API}/clients/{other.id}/periods/{r.json()['id']}/documents/{a}/extraction"
    assert (await s.api.get(wrong, headers=s.hdr)).status_code == 404


async def test_soft_deleted_documents_are_not_reachable(
    s: Setup, session_factory: async_sessionmaker[AsyncSession], store: S3ObjectStore
) -> None:
    doc_id = await upload_and_extract(
        s, session_factory, store, fx.fixed_assets_xlsx(), category="fixed_asset_schedule"
    )
    assert (await s.api.delete(f"{s.url}/{doc_id}", headers=s.hdr)).status_code in (200, 204)
    assert (await s.api.get(ext_url(s, doc_id), headers=s.hdr)).status_code == 404
    assert (
        await intake.extract_document(session_factory, store, settings(), uuid.UUID(doc_id)) is None
    )


# ------------------------------------------------------------------------------ database rules


async def test_database_rejects_cross_client_extraction_rows(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    db: AsyncSession,
) -> None:
    doc_id = await upload_and_extract(
        s, session_factory, store, fx.fixed_assets_xlsx(), category="fixed_asset_schedule"
    )
    doc = await db.get(Document, uuid.UUID(doc_id))
    assert doc is not None
    other = await s.world.client(s.firm)
    db.add(
        ExtractionRun(
            firm_id=doc.firm_id,
            client_id=other.id,
            period_id=doc.period_id,
            document_id=doc.id,
            version=99,
            status="running",
            parser_version="x",
        )
    )
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_database_allows_only_one_current_run_and_valid_enums(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    db: AsyncSession,
) -> None:
    doc_id = await upload_and_extract(
        s, session_factory, store, fx.fixed_assets_xlsx(), category="fixed_asset_schedule"
    )
    doc = await db.get(Document, uuid.UUID(doc_id))
    assert doc is not None
    base = dict(
        firm_id=doc.firm_id,
        client_id=doc.client_id,
        period_id=doc.period_id,
        document_id=doc.id,
        parser_version="x",
    )
    db.add(ExtractionRun(version=50, is_current=True, status="completed", **base))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()
    db.add(ExtractionRun(version=51, is_current=False, status="bogus", **base))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_deleting_a_run_removes_its_extracted_data(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    store: S3ObjectStore,
    db: AsyncSession,
) -> None:
    """Derived data cascades with its run; the document and original are never affected."""
    doc_id = await upload_and_extract(
        s, session_factory, store, fx.fixed_assets_xlsx(), category="fixed_asset_schedule"
    )
    run = await db.scalar(
        select(ExtractionRun).where(ExtractionRun.document_id == uuid.UUID(doc_id))
    )
    assert run is not None
    tids = (
        await db.scalars(select(ExtractedTable.id).where(ExtractedTable.run_id == run.id))
    ).all()
    assert tids
    await db.delete(run)
    await db.commit()
    assert not (await db.scalars(select(ExtractedRow).where(ExtractedRow.table_id.in_(tids)))).all()
    assert not (
        await db.scalars(select(ExtractedColumn).where(ExtractedColumn.table_id.in_(tids)))
    ).all()
    assert await db.get(Document, uuid.UUID(doc_id)) is not None
