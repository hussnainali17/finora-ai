"""Document upload, listing, download and removal.

Upload ordering (guarantees "no event for a failed upload"):
  1. authorise (permission + client scope), open period / active client
  2. stream to a temp file: size limit, SHA-256, content verification
  3. duplicate pre-check (hash within the client period)
  4. write the original to object storage under a new immutable key
  5. ONE DB transaction: document row + audit event + outbox event
  6. if step 5 fails, the just-written object is deleted (compensation)
The Kafka event is published later by the outbox relay, only for committed rows."""

import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    AppError,
    ConflictError,
    DomainValidationError,
    DuplicateDocumentError,
    NotFoundError,
    UnsupportedMediaTypeError,
)
from app.integrations.storage.s3 import ObjectStore
from app.models import AccountingPeriod, Document, User
from app.services import uploads
from app.services.audit import record_audit
from app.services.authz import Principal, get_accessible_client, require_permission
from app.services.outbox import enqueue_event

logger = logging.getLogger("app.documents")


def build_object_key(
    firm_id: uuid.UUID, client_id: uuid.UUID, period_id: uuid.UUID, doc_id: uuid.UUID
) -> str:
    # No user-supplied text in the key: filenames live only in the database.
    return f"firms/{firm_id}/clients/{client_id}/periods/{period_id}/{doc_id}/original"


async def _scoped_period(
    session: AsyncSession, principal: Principal, client_id: uuid.UUID, period_id: uuid.UUID
) -> tuple[object, AccountingPeriod]:
    client = await get_accessible_client(session, principal, client_id)
    period = await session.scalar(
        select(AccountingPeriod).where(
            AccountingPeriod.id == period_id,
            AccountingPeriod.client_id == client.id,
            AccountingPeriod.firm_id == principal.firm_id,
        )
    )
    if period is None:
        raise NotFoundError("Accounting period not found")
    return client, period


async def _get_document(
    session: AsyncSession,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Document:
    await _scoped_period(session, principal, client_id, period_id)
    doc = await session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.period_id == period_id,
            Document.client_id == client_id,
            Document.firm_id == principal.firm_id,
            Document.deleted_at.is_(None),
        )
    )
    if doc is None:
        raise NotFoundError("Document not found")
    return doc


async def _audit_failure(
    session: AsyncSession, principal: Principal, client_id: uuid.UUID, action: str, **meta: object
) -> None:
    await session.rollback()
    record_audit(
        session,
        action=action,
        actor=principal,
        target_type="document",
        client_id=client_id,
        outcome="failure",
        metadata=dict(meta),
    )
    await session.commit()


@dataclass
class DocumentRow:
    document: Document
    uploaded_by_email: str | None


async def upload_document(
    session: AsyncSession,
    store: ObjectStore,
    settings: Settings,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    *,
    upload: UploadFile,
    category: str,
    scanner: uploads.FileScanner | None = None,
) -> Document:
    require_permission(principal, "document:upload")
    client, period = await _scoped_period(session, principal, client_id, period_id)
    if client.status != "active":  # type: ignore[attr-defined]
        raise ConflictError("Cannot upload to an archived client")
    if period.status != "open":
        raise ConflictError("This accounting period is closed; reopen it to upload files")

    filename = uploads.sanitize_filename(upload.filename)
    ext = uploads.extension_of(filename)
    if not filename or ext not in settings.upload_extensions:
        await _audit_failure(
            session,
            principal,
            client_id,
            "document.upload_rejected",
            reason="type_not_allowed",
            extension=ext,
        )
        allowed = ", ".join(sorted(settings.upload_extensions))
        raise UnsupportedMediaTypeError(f"Unsupported file type. Allowed: {allowed}")

    spooled = await uploads.spool_upload(upload, settings.max_upload_bytes)
    doc_id = uuid.uuid4()
    key = build_object_key(principal.firm_id, client_id, period_id, doc_id)
    stored = False
    try:
        try:
            content_type = uploads.verify_content(spooled, ext)
            await (scanner or uploads.NoopScanner()).scan(spooled.file, filename=filename)
        except AppError:
            await _audit_failure(
                session,
                principal,
                client_id,
                "document.upload_rejected",
                reason="content_mismatch",
                extension=ext,
            )
            raise

        existing = await session.scalar(
            select(Document).where(
                Document.client_id == client_id,
                Document.period_id == period_id,
                Document.sha256 == spooled.sha256,
                Document.deleted_at.is_(None),
            )
        )
        if existing is not None:
            error = _duplicate(existing)  # build before the rollback expires `existing`
            await _audit_failure(
                session,
                principal,
                client_id,
                "document.duplicate_rejected",
                existing_document_id=error.extra["existing_document_id"],
            )
            raise error

        await store.put(key, spooled.file, content_type=content_type, sha256=spooled.sha256)
        stored = True

        doc = Document(
            id=doc_id,
            firm_id=principal.firm_id,
            client_id=client_id,
            period_id=period_id,
            category=category,
            original_filename=filename,
            object_key=key,
            content_type=content_type,
            size_bytes=spooled.size,
            sha256=spooled.sha256,
            uploaded_by=principal.user_id,
        )
        session.add(doc)
        try:
            await session.flush()
        except IntegrityError as exc:
            # Lost a race with a concurrent identical upload (unique live-hash index).
            await session.rollback()
            existing = await session.scalar(
                select(Document).where(
                    Document.client_id == client_id,
                    Document.period_id == period_id,
                    Document.sha256 == spooled.sha256,
                    Document.deleted_at.is_(None),
                )
            )
            if existing is None:
                raise
            raise _duplicate(existing) from exc
        record_audit(
            session,
            action="document.uploaded",
            actor=principal,
            target_type="document",
            target_id=doc.id,
            client_id=client_id,
            metadata={
                "filename": filename,
                "category": category,
                "size_bytes": spooled.size,
                "sha256": spooled.sha256,
                "period_id": period_id,
            },
        )
        enqueue_event(
            session,
            topic=settings.file_uploaded_topic,
            event_type="file.uploaded",
            partition_key=str(client_id),  # per-client ordering
            firm_id=principal.firm_id,
            client_id=client_id,
            period_id=period_id,
            payload={
                "document_id": str(doc.id),
                "object_key": key,
                "sha256": spooled.sha256,
                "size_bytes": spooled.size,
                "content_type": content_type,
                "category": category,
            },
        )
        await session.commit()
        await session.refresh(doc)
        return doc
    except BaseException:
        await session.rollback()
        if stored:  # compensate: never leave an unreferenced object behind
            try:
                await store.delete(key)
            except Exception:
                logger.exception("failed to delete orphaned object", extra={"object_key": key})
        raise
    finally:
        spooled.close()


def _duplicate(existing: Document) -> DuplicateDocumentError:
    return DuplicateDocumentError(
        "This exact file has already been uploaded to this period",
        existing_document_id=str(existing.id),
        existing_filename=existing.original_filename,
    )


async def list_documents(
    session: AsyncSession,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
    category: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> tuple[list[DocumentRow], int]:
    require_permission(principal, "document:read")
    await _scoped_period(session, principal, client_id, period_id)
    where = [
        Document.period_id == period_id,
        Document.client_id == client_id,
        Document.firm_id == principal.firm_id,
        Document.deleted_at.is_(None),
    ]
    if category:
        where.append(Document.category == category)
    if status:
        where.append(Document.status == status)
    if q:
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where.append(Document.original_filename.ilike(f"%{escaped}%"))
    total = await session.scalar(select(func.count()).select_from(Document).where(*where)) or 0
    rows = await session.execute(
        select(Document, User.email)
        .outerjoin(User, User.id == Document.uploaded_by)
        .where(*where)
        .order_by(Document.created_at.desc(), Document.id)
        .limit(limit)
        .offset(offset)
    )
    return [DocumentRow(d, email) for d, email in rows.all()], total


async def get_document(
    session: AsyncSession,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
) -> DocumentRow:
    require_permission(principal, "document:read")
    doc = await _get_document(session, principal, client_id, period_id, document_id)
    email = await session.scalar(select(User.email).where(User.id == doc.uploaded_by))
    return DocumentRow(doc, email)


async def open_download(
    session: AsyncSession,
    store: ObjectStore,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
) -> tuple[Document, Iterator[bytes]]:
    require_permission(principal, "document:read")
    doc = await _get_document(session, principal, client_id, period_id, document_id)
    record_audit(
        session,
        action="document.downloaded",
        actor=principal,
        target_type="document",
        target_id=doc.id,
        client_id=client_id,
        metadata={"filename": doc.original_filename, "sha256": doc.sha256},
    )
    await session.commit()
    return doc, store.iter_chunks(doc.object_key)


async def delete_document(
    session: AsyncSession,
    principal: Principal,
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:
    """Soft delete: hides the record; the original object is RETAINED (retention/purge policy is a
    separate, later concern) so nothing the client supplied is ever destroyed by a click."""
    require_permission(principal, "document:delete")
    _, period = await _scoped_period(session, principal, client_id, period_id)
    if period.status != "open":
        raise ConflictError("This accounting period is closed; reopen it to remove files")
    doc = await _get_document(session, principal, client_id, period_id, document_id)
    if doc.status in ("processing",):
        raise ConflictError("The file is being processed and cannot be removed right now")
    from datetime import UTC, datetime

    doc.deleted_at = datetime.now(UTC)
    doc.deleted_by = principal.user_id
    record_audit(
        session,
        action="document.deleted",
        actor=principal,
        target_type="document",
        target_id=doc.id,
        client_id=client_id,
        metadata={"filename": doc.original_filename, "sha256": doc.sha256, "object_retained": True},
    )
    await session.commit()


__all__ = ["DocumentRow", "DomainValidationError"]
