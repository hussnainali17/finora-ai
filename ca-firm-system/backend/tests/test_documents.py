"""Phase 2: secure document management - storage, metadata, duplicates, authz, events, immutability."""

import asyncio
import io
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import ServiceUnavailableError
from app.integrations.storage.s3 import S3ObjectStore
from app.models import AuditEvent, Document, OutboxEvent
from app.services import documents as doc_service
from app.services.outbox import publish_pending
from app.services.uploads import sanitize_filename
from tests.conftest import (
    ACCOUNTANT,
    CA_REVIEWER,
    CLIENT_USER,
    FIRM_ADMIN,
    FakePublisher,
    World,
    login,
)

API = "/api/v1"
PERIOD = {"label": "FY2025", "start_date": "2025-01-01", "end_date": "2025-12-31"}


def pdf(n: int = 0, size: int = 2048) -> bytes:
    return b"%PDF-1.7\n" + f"% unique {n} {uuid.uuid4()}\n".encode() + b"x" * size + b"\n%%EOF"


def xlsx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/workbook.xml", f"<workbook id='{uuid.uuid4()}'/>")
    return buf.getvalue()


class Setup:
    def __init__(self, api: httpx.AsyncClient, world: World) -> None:
        self.api, self.world = api, world

    async def build(self) -> "Setup":
        # The relay drains EVERY pending outbox row; clear other tests' leftovers so each test
        # only sees its own events.
        async with self.world._sf() as session:
            await session.execute(text("DELETE FROM outbox_events WHERE published_at IS NULL"))
            await session.commit()
        self.firm = await self.world.firm()
        self.admin = await self.world.user(self.firm, FIRM_ADMIN)
        self.hdr = await login(self.api, self.admin)
        self.client = await self.world.client(self.firm)
        r = await self.api.post(
            f"{API}/clients/{self.client.id}/periods", json=PERIOD, headers=self.hdr
        )
        self.period_id = r.json()["id"]
        return self

    @property
    def url(self) -> str:
        return f"{API}/clients/{self.client.id}/periods/{self.period_id}/documents"

    async def upload(
        self,
        data: bytes | None = None,
        name: str = "statement.pdf",
        category: str = "bank_statement",
        hdr: dict[str, str] | None = None,
        url: str | None = None,
    ) -> httpx.Response:
        return await self.api.post(
            url or self.url,
            files={"file": (name, data if data is not None else pdf(), "application/octet-stream")},
            data={"category": category},
            headers=hdr or self.hdr,
        )


@pytest.fixture
async def s(api: httpx.AsyncClient, world: World) -> Setup:
    return await Setup(api, world).build()


def read_object(store: S3ObjectStore, key: str) -> bytes:
    return b"".join(store.iter_chunks(key))


# ------------------------------------------------------------------------------ happy path


async def test_upload_stores_unchanged_original_metadata_audit_and_one_pending_event(
    s: Setup, store: S3ObjectStore, db: AsyncSession
) -> None:
    data = pdf(1, 5000)
    r = await s.upload(data, "Bank Statement – Jan.pdf")
    assert r.status_code == 201, r.text
    body = r.json()
    import hashlib

    assert body["sha256"] == hashlib.sha256(data).hexdigest()
    assert body["size_bytes"] == len(data) and body["status"] == "uploaded"
    assert body["content_type"] == "application/pdf" and body["category"] == "bank_statement"
    assert body["original_filename"] == "Bank Statement – Jan.pdf"
    assert body["uploaded_by_email"] == s.admin.email

    doc = await db.get(Document, uuid.UUID(body["id"]))
    assert doc is not None
    # the file lives in object storage, byte-for-byte; the key contains no user-supplied text
    assert read_object(store, doc.object_key) == data
    assert (
        doc.object_key
        == f"firms/{s.firm.id}/clients/{s.client.id}/periods/{s.period_id}/{doc.id}/original"
    )
    assert "Statement" not in doc.object_key

    events = (
        await db.scalars(select(OutboxEvent).where(OutboxEvent.client_id == s.client.id))
    ).all()
    assert len(events) == 1 and events[0].published_at is None
    ev = events[0]
    assert (ev.event_type, ev.topic, ev.schema_version) == ("file.uploaded", "file-uploaded", 1)
    assert ev.firm_id == s.firm.id and ev.accounting_period_id == uuid.UUID(s.period_id)
    assert ev.payload["document_id"] == body["id"] and ev.payload["object_key"] == doc.object_key
    assert b"PDF" not in str(ev.payload).encode()  # IDs and keys only - never contents

    audit = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "document.uploaded", AuditEvent.target_id == doc.id
        )
    )
    assert audit and audit.actor_user_id == s.admin.id and audit.client_id == s.client.id
    assert audit.event_metadata["sha256"] == body["sha256"]


@pytest.mark.parametrize(
    ("name", "make"),
    [
        ("tb.xlsx", xlsx_bytes),
        ("ledger.csv", lambda: b"account,debit,credit\n1000,10.50,0\n"),
        ("old.xls", lambda: b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 100),
        ("scan.png", lambda: b"\x89PNG\r\n\x1a\n" + b"0" * 50),
        ("scan.JPG", lambda: b"\xff\xd8\xff\xe0" + b"0" * 50),
    ],
)
async def test_each_supported_type_is_accepted(s: Setup, name: str, make: Any) -> None:
    assert (await s.upload(make(), name)).status_code == 201


# ------------------------------------------------------------------------------ outbox / events


async def test_event_is_published_only_by_the_relay_and_marks_document_queued(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    publisher: FakePublisher,
    db: AsyncSession,
) -> None:
    doc_id = (await s.upload()).json()["id"]
    assert publisher.published == []  # nothing is sent inside the request

    assert await publish_pending(session_factory, publisher) == 1
    topic, key, env = publisher.published[0]
    assert (topic, key) == ("file-uploaded", str(s.client.id))
    assert env.event_type == "file.uploaded" and env.tenant_id == s.firm.id
    assert env.client_id == s.client.id and str(env.accounting_period_id) == s.period_id
    assert env.payload["document_id"] == doc_id and env.correlation_id
    status = (await s.api.get(f"{s.url}/{doc_id}", headers=s.hdr)).json()["status"]
    assert status == "queued"
    assert await publish_pending(session_factory, publisher) == 0  # nothing left to send


async def test_publish_failure_is_retried_with_backoff_and_leaks_no_details(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    publisher: FakePublisher,
    db: AsyncSession,
) -> None:
    await s.upload()
    publisher.fail_next = 1
    assert await publish_pending(session_factory, publisher) == 0
    ev = (await db.scalars(select(OutboxEvent).where(OutboxEvent.client_id == s.client.id))).one()
    assert ev.published_at is None and ev.attempts == 1
    assert ev.last_error == "ConnectionError" and "kafka.internal" not in (ev.last_error or "")
    assert ev.next_attempt_at > datetime.now(UTC)
    assert await publish_pending(session_factory, publisher) == 0  # still backing off

    await db.execute(
        update(OutboxEvent).where(OutboxEvent.id == ev.id).values(next_attempt_at=datetime.now(UTC))
    )
    await db.commit()
    assert await publish_pending(session_factory, publisher) == 1


async def test_redelivery_reuses_event_id_and_never_regresses_document_state(
    s: Setup,
    session_factory: async_sessionmaker[AsyncSession],
    publisher: FakePublisher,
    db: AsyncSession,
) -> None:
    """Crash after Kafka accepted the message but before published_at was saved => same event again."""
    doc_id = uuid.UUID((await s.upload()).json()["id"])
    await publish_pending(session_factory, publisher)
    await db.execute(update(Document).where(Document.id == doc_id).values(status="processing"))
    await db.execute(
        update(OutboxEvent).where(OutboxEvent.client_id == s.client.id).values(published_at=None)
    )
    await db.commit()

    await publish_pending(session_factory, publisher)
    assert len(publisher.published) == 2
    assert (
        publisher.published[0][2].event_id == publisher.published[1][2].event_id
    )  # consumers dedupe on this
    db.expire_all()
    assert (await db.get(Document, doc_id)).status == "processing"  # type: ignore[union-attr]


async def test_concurrent_relays_publish_each_event_once(
    s: Setup, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    for i in range(5):
        assert (await s.upload(pdf(i), f"f{i}.pdf")).status_code == 201

    class Slow(FakePublisher):
        async def publish(self, topic: str, key: str, event: Any) -> None:
            await asyncio.sleep(0.05)
            await super().publish(topic, key, event)

    pub = Slow()
    await asyncio.gather(*(publish_pending(session_factory, pub, batch_size=10) for _ in range(3)))
    ids = [e.event_id for _, _, e in pub.published]
    assert len(ids) == 5 and len(set(ids)) == 5


# ------------------------------------------------------------------------------ no event on failure


async def _no_trace(db: AsyncSession, s: Setup) -> None:
    assert (await db.scalars(select(Document).where(Document.client_id == s.client.id))).all() == []
    assert (
        await db.scalars(select(OutboxEvent).where(OutboxEvent.client_id == s.client.id))
    ).all() == []


async def test_storage_outage_means_no_row_and_no_event(
    s: Setup, store: S3ObjectStore, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*a: Any, **k: Any) -> None:
        raise ServiceUnavailableError("File storage is temporarily unavailable")

    monkeypatch.setattr(store, "put", boom)
    r = await s.upload()
    assert r.status_code == 503 and "temporarily unavailable" in r.json()["detail"]
    await _no_trace(db, s)


async def test_database_failure_after_storing_deletes_the_object_and_emits_nothing(
    s: Setup, store: S3ObjectStore, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored_keys: list[str] = []
    real_put = store.put

    async def spy(key: str, *a: Any, **k: Any) -> None:
        stored_keys.append(key)
        await real_put(key, *a, **k)

    def explode(*a: Any, **k: Any) -> None:
        raise RuntimeError("db went away")

    monkeypatch.setattr(store, "put", spy)
    monkeypatch.setattr(doc_service, "enqueue_event", explode)
    with pytest.raises(RuntimeError):
        await s.upload()
    assert len(stored_keys) == 1
    assert not await store.exists(stored_keys[0])  # compensated: no orphan object
    await _no_trace(db, s)


# ------------------------------------------------------------------------------ validation


@pytest.mark.parametrize(
    ("name", "data", "status_code"),
    [
        ("malware.exe", b"MZ" + b"0" * 100, 415),
        ("noextension", pdf(), 415),
        ("renamed.pdf", b"MZ\x90\x00" + b"0" * 100, 415),  # exe renamed to .pdf
        ("fake.xlsx", b"PK\x03\x04" + b"0" * 100, 415),  # zip header, not a workbook
        ("plain.xlsx", b"just text", 415),
        ("bin.csv", b"a,b\n\x00\x01\x02", 415),
        ("fake.png", pdf(), 415),
        ("empty.pdf", b"", 422),
        ("big.pdf", b"%PDF-" + b"0" * (1024 * 1024 + 1), 413),
    ],
)
async def test_invalid_uploads_are_rejected_with_no_trace(
    s: Setup, db: AsyncSession, name: str, data: bytes, status_code: int
) -> None:
    r = await s.upload(data, name)
    assert r.status_code == status_code, r.text
    await _no_trace(db, s)


async def test_rejection_is_audited_and_unknown_category_is_422(s: Setup, db: AsyncSession) -> None:
    await s.upload(b"MZ" + b"0" * 50, "x.exe")
    ev = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "document.upload_rejected", AuditEvent.client_id == s.client.id
        )
    )
    assert ev and ev.outcome == "failure" and ev.client_id == s.client.id
    assert (await s.upload(category="tax_return")).status_code == 422


async def test_unsafe_filenames_are_neutralised(s: Setup, db: AsyncSession) -> None:
    r = await s.upload(pdf(7), "../../etc/passwd.pdf")
    assert r.json()["original_filename"] == "passwd.pdf"
    r = await s.upload(pdf(8), 'evil\r\nname".pdf')
    assert "\r" not in r.json()["original_filename"] and "\n" not in r.json()["original_filename"]
    assert sanitize_filename("C:\\Users\\x\\..\\report.xlsx") == "report.xlsx"
    assert sanitize_filename(".hidden.pdf") == "hidden.pdf"
    assert len(sanitize_filename("a" * 400 + ".pdf")) <= 200 and sanitize_filename(
        "a" * 400 + ".pdf"
    ).endswith(".pdf")


async def test_cannot_upload_to_closed_period_or_archived_client(s: Setup) -> None:
    base = f"{API}/clients/{s.client.id}"
    await s.api.post(f"{base}/periods/{s.period_id}/close", headers=s.hdr)
    assert (await s.upload()).status_code == 409
    await s.api.post(f"{base}/periods/{s.period_id}/reopen", headers=s.hdr)
    assert (await s.upload()).status_code == 201
    await s.api.patch(base, json={"status": "archived"}, headers=s.hdr)
    assert (await s.upload(pdf(2), "b.pdf")).status_code == 409


# ------------------------------------------------------------------------------ duplicates


async def test_duplicate_upload_is_rejected_safely(s: Setup, db: AsyncSession) -> None:
    data = pdf(3)
    first = (await s.upload(data, "a.pdf")).json()
    dup = await s.upload(data, "renamed-copy.pdf")
    assert dup.status_code == 409
    body = dup.json()
    assert body["code"] == "duplicate_document"
    assert body["existing_document_id"] == first["id"] and body["existing_filename"] == "a.pdf"
    assert (
        len((await db.scalars(select(Document).where(Document.client_id == s.client.id))).all())
        == 1
    )
    assert (
        len(
            (
                await db.scalars(select(OutboxEvent).where(OutboxEvent.client_id == s.client.id))
            ).all()
        )
        == 1
    )
    audit = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "document.duplicate_rejected", AuditEvent.client_id == s.client.id
        )
    )
    assert audit and audit.outcome == "failure"


async def test_same_bytes_allowed_in_another_period_or_after_removal(s: Setup) -> None:
    data = pdf(4)
    assert (await s.upload(data)).status_code == 201
    other = (
        await s.api.post(
            f"{API}/clients/{s.client.id}/periods",
            json={"label": "FY2026", "start_date": "2026-01-01", "end_date": "2026-12-31"},
            headers=s.hdr,
        )
    ).json()["id"]
    assert (
        await s.upload(data, url=f"{API}/clients/{s.client.id}/periods/{other}/documents")
    ).status_code == 201

    first_id = (await s.api.get(s.url, headers=s.hdr)).json()["items"][0]["id"]
    assert (await s.api.delete(f"{s.url}/{first_id}", headers=s.hdr)).status_code == 204
    assert (await s.upload(data)).status_code == 201  # no longer a live duplicate


async def test_concurrent_identical_uploads_yield_exactly_one_document_and_event(
    s: Setup, db: AsyncSession
) -> None:
    data = pdf(5)
    results = await asyncio.gather(*(s.upload(data, f"race{i}.pdf") for i in range(4)))
    assert sorted(r.status_code for r in results) == [201, 409, 409, 409]
    assert (
        len((await db.scalars(select(Document).where(Document.client_id == s.client.id))).all())
        == 1
    )
    assert (
        len(
            (
                await db.scalars(select(OutboxEvent).where(OutboxEvent.client_id == s.client.id))
            ).all()
        )
        == 1
    )


# ------------------------------------------------------------------------------ authorization


async def test_unassigned_user_cannot_touch_documents_of_other_clients(
    s: Setup, api: httpx.AsyncClient, world: World
) -> None:
    doc_id = (await s.upload()).json()["id"]
    outsider = await world.user(s.firm, CA_REVIEWER)  # has document permissions, NOT assigned
    hdr = await login(api, outsider)
    for method, url, kw in [
        ("GET", s.url, {}),
        ("GET", f"{s.url}/{doc_id}", {}),
        ("GET", f"{s.url}/{doc_id}/download", {}),
        ("DELETE", f"{s.url}/{doc_id}", {}),
    ]:
        r = await api.request(method, url, headers=hdr, **kw)
        assert r.status_code == 404, (method, url, r.status_code)
    assert (await s.upload(hdr=hdr, url=s.url)).status_code == 404


async def test_other_firm_cannot_access_documents(
    s: Setup, api: httpx.AsyncClient, world: World
) -> None:
    doc_id = (await s.upload()).json()["id"]
    firm_b = await world.firm("Beta")
    hdr_b = await login(api, await world.user(firm_b, FIRM_ADMIN))
    assert (await api.get(f"{s.url}/{doc_id}/download", headers=hdr_b)).status_code == 404
    assert (await api.get(s.url, headers=hdr_b)).status_code == 404
    assert (await s.upload(pdf(9), hdr=hdr_b)).status_code == 404
    assert (await api.delete(f"{s.url}/{doc_id}", headers=hdr_b)).status_code == 404


async def test_role_permissions_for_documents(
    s: Setup, api: httpx.AsyncClient, world: World
) -> None:
    doc_id = (await s.upload()).json()["id"]
    acc = await world.user(s.firm, ACCOUNTANT)
    cu = await world.user(s.firm, CLIENT_USER)
    await world.assign(acc, s.client)
    await world.assign(cu, s.client)
    acc_h, cu_h = await login(api, acc), await login(api, cu)

    assert (await api.get(s.url, headers=cu_h)).status_code == 200
    assert (await api.get(f"{s.url}/{doc_id}/download", headers=cu_h)).status_code == 200
    assert (await s.upload(pdf(10), hdr=cu_h)).status_code == 403  # read-only client user
    assert (await api.delete(f"{s.url}/{doc_id}", headers=cu_h)).status_code == 403
    assert (await s.upload(pdf(11), hdr=acc_h)).status_code == 201  # staff may upload...
    assert (
        await api.delete(f"{s.url}/{doc_id}", headers=acc_h)
    ).status_code == 403  # ...not delete


async def test_unauthenticated_requests_are_rejected(s: Setup, api: httpx.AsyncClient) -> None:
    doc_id = (await s.upload()).json()["id"]
    assert (await api.get(s.url)).status_code == 401
    assert (await api.get(f"{s.url}/{doc_id}/download")).status_code == 401
    assert (
        await api.post(s.url, files={"file": ("a.pdf", pdf())}, data={"category": "other"})
    ).status_code == 401


async def test_document_cannot_be_reached_through_a_different_client_or_period_path(
    s: Setup, api: httpx.AsyncClient, world: World
) -> None:
    doc_id = (await s.upload()).json()["id"]
    other_client = await world.client(s.firm)
    p2 = (
        await api.post(f"{API}/clients/{other_client.id}/periods", json=PERIOD, headers=s.hdr)
    ).json()["id"]
    wrong = f"{API}/clients/{other_client.id}/periods/{p2}/documents/{doc_id}"
    assert (await api.get(wrong, headers=s.hdr)).status_code == 404
    assert (await api.get(f"{wrong}/download", headers=s.hdr)).status_code == 404
    mixed = f"{API}/clients/{s.client.id}/periods/{p2}/documents/{doc_id}"  # client A + client B's period
    assert (await api.get(mixed, headers=s.hdr)).status_code == 404


# ------------------------------------------------------------------------------ download/list/delete


async def test_download_returns_identical_bytes_with_safe_headers_and_is_audited(
    s: Setup, db: AsyncSession
) -> None:
    data = pdf(12, 600_000)
    doc = (await s.upload(data, 'résumé "Q1".pdf')).json()
    r = await s.api.get(f"{s.url}/{doc['id']}/download", headers=s.hdr)
    assert r.status_code == 200 and r.content == data
    assert r.headers["content-type"] == "application/pdf"
    assert (
        r.headers["x-content-type-options"] == "nosniff"
        and "no-store" in r.headers["cache-control"]
    )
    cd = r.headers["content-disposition"]
    assert cd.startswith("attachment;") and "filename*=UTF-8''r%C3%A9sum%C3%A9" in cd
    assert "\n" not in cd and '"Q1"' not in cd
    ev = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "document.downloaded", AuditEvent.client_id == s.client.id
        )
    )
    assert ev and ev.actor_user_id == s.admin.id and ev.target_id == uuid.UUID(doc["id"])


async def test_removal_hides_the_record_but_retains_the_original_object(
    s: Setup, store: S3ObjectStore, db: AsyncSession
) -> None:
    doc = (await s.upload(pdf(13))).json()
    key = (await db.get(Document, uuid.UUID(doc["id"]))).object_key  # type: ignore[union-attr]
    assert (await s.api.delete(f"{s.url}/{doc['id']}", headers=s.hdr)).status_code == 204
    assert (await s.api.get(f"{s.url}/{doc['id']}", headers=s.hdr)).status_code == 404
    assert (await s.api.get(f"{s.url}/{doc['id']}/download", headers=s.hdr)).status_code == 404
    assert (await s.api.get(s.url, headers=s.hdr)).json()["total"] == 0
    assert await store.exists(key)  # retained
    ev = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "document.deleted", AuditEvent.client_id == s.client.id
        )
    )
    assert ev and ev.event_metadata["object_retained"] is True
    # closed periods are frozen
    d2 = (await s.upload(pdf(14))).json()
    await s.api.post(f"{API}/clients/{s.client.id}/periods/{s.period_id}/close", headers=s.hdr)
    assert (await s.api.delete(f"{s.url}/{d2['id']}", headers=s.hdr)).status_code == 409


async def test_list_filters_search_and_pagination(s: Setup) -> None:
    await s.upload(pdf(20), "bank-jan.pdf", "bank_statement")
    await s.upload(pdf(21), "bank-feb.pdf", "bank_statement")
    await s.upload(pdf(22), "invoice-1.pdf", "invoice")
    page = (await s.api.get(f"{s.url}?limit=2", headers=s.hdr)).json()
    assert page["total"] == 3 and len(page["items"]) == 2
    assert (await s.api.get(f"{s.url}?category=invoice", headers=s.hdr)).json()["total"] == 1
    assert (await s.api.get(f"{s.url}?q=bank", headers=s.hdr)).json()["total"] == 2
    assert (await s.api.get(f"{s.url}?q=%25", headers=s.hdr)).json()["total"] == 0
    assert (await s.api.get(f"{s.url}?status=uploaded", headers=s.hdr)).json()["total"] == 3
    assert (await s.api.get(f"{s.url}?status=bogus", headers=s.hdr)).status_code == 422


# ------------------------------------------------------------------------------ database guarantees


async def test_original_file_columns_are_immutable_and_rows_cannot_be_deleted(
    s: Setup, db: AsyncSession
) -> None:
    doc_id = (await s.upload(pdf(30))).json()["id"]
    for stmt in (
        f"UPDATE documents SET sha256 = repeat('a', 64) WHERE id = '{doc_id}'",
        f"UPDATE documents SET object_key = 'other' WHERE id = '{doc_id}'",
        f"UPDATE documents SET original_filename = 'x.pdf' WHERE id = '{doc_id}'",
        f"UPDATE documents SET size_bytes = 1 WHERE id = '{doc_id}'",
        f"DELETE FROM documents WHERE id = '{doc_id}'",
    ):
        with pytest.raises((DBAPIError, IntegrityError), match="immutable|cannot be deleted"):
            await db.execute(text(stmt))
        await db.rollback()
    # workflow columns remain writable
    await db.execute(text(f"UPDATE documents SET status = 'processing' WHERE id = '{doc_id}'"))
    await db.commit()


async def test_database_rejects_a_document_whose_period_belongs_to_another_client(
    s: Setup, world: World, db: AsyncSession
) -> None:
    other = await world.client(s.firm)
    p2 = (await s.api.post(f"{API}/clients/{other.id}/periods", json=PERIOD, headers=s.hdr)).json()[
        "id"
    ]
    with pytest.raises(IntegrityError, match="fk_documents_period_client"):
        await db.execute(
            text(
                "INSERT INTO documents (firm_id, client_id, period_id, category, original_filename, "
                "object_key, content_type, size_bytes, sha256, uploaded_by) "
                "VALUES (:f, :c, :p, 'other', 'x.pdf', :k, 'application/pdf', 1, repeat('a', 64), :u)"
            ),
            {"f": s.firm.id, "c": s.client.id, "p": p2, "k": f"k/{uuid.uuid4()}", "u": s.admin.id},
        )
    await db.rollback()


# ------------------------------------------------------------------------------ Kafka producer


async def test_kafka_publisher_sends_idempotent_keyed_event_and_reconnects_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import aiokafka

    from app.integrations.kafka.publisher import EventEnvelope, KafkaEventPublisher

    created: list[Any] = []

    class FakeProducer:
        def __init__(self, **kw: Any) -> None:
            self.kw, self.sent, self.stopped, self.fail = kw, [], False, False
            created.append(self)

        async def start(self) -> None: ...
        async def stop(self) -> None:
            self.stopped = True

        async def send_and_wait(self, topic: str, **kw: Any) -> None:
            if self.fail:
                raise ConnectionError("down")
            self.sent.append((topic, kw))

    monkeypatch.setattr(aiokafka, "AIOKafkaProducer", FakeProducer)
    pub = KafkaEventPublisher("kafka:9092")
    eid = uuid.uuid4()
    ev = EventEnvelope(
        event_id=eid, event_type="file.uploaded", schema_version=1, tenant_id=uuid.uuid4(),
        client_id=None, accounting_period_id=None, correlation_id="c", occurred_at=datetime.now(UTC),
        payload={"document_id": "d"},
    )  # fmt: skip
    await pub.publish("file-uploaded", "k1", ev)
    p = created[0]
    assert p.kw["acks"] == "all" and p.kw["enable_idempotence"] is True
    topic, kw = p.sent[0]
    assert topic == "file-uploaded" and kw["key"] == b"k1" and str(eid).encode() in kw["value"]
    assert ("event_id", str(eid).encode()) in kw["headers"]

    p.fail = True
    with pytest.raises(ConnectionError):
        await pub.publish("file-uploaded", "k1", ev)
    assert p.stopped
    p2_ok = len(created)
    created[0].fail = False
    # next publish builds a fresh producer
    await pub.publish("file-uploaded", "k1", ev)
    assert len(created) == p2_ok + 1


def test_extension_allowlist_is_configurable() -> None:
    from app.core.config import Settings
    from tests.test_config import BASE

    s = Settings(**{**BASE, "allowed_upload_extensions": "PDF, .csv"})  # type: ignore[arg-type]
    assert s.upload_extensions == {"pdf", "csv"}
