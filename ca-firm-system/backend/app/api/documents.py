import re
import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.concurrency import iterate_in_threadpool
from fastapi.responses import StreamingResponse

from app.api.deps import PrincipalDep, SessionDep, SettingsDep
from app.document_intelligence.categories import get_categories_for_module
from app.document_intelligence.service import share_document_with_module
from app.integrations.storage.s3 import ObjectStore, get_object_store
from app.models import Document
from app.schemas.common import Page
from app.schemas.documents import (
    BatchUploadResponse,
    DocumentCategory,
    DocumentCategoryItem,
    DocumentOut,
    DocumentShareRequest,
    DocumentShareResponse,
    DocumentStatus,
    ModuleCategoriesResponse,
)
from app.services import documents as svc

router = APIRouter(prefix="/clients/{client_id}/periods/{period_id}/documents", tags=["documents"])
StoreDep = Annotated[ObjectStore, Depends(get_object_store)]


def _out(row: svc.DocumentRow) -> DocumentOut:
    d: Document = row.document
    return DocumentOut(
        id=d.id,
        client_id=d.client_id,
        period_id=d.period_id,
        module=getattr(d, "module", "accounting") or "accounting",
        category=d.category,
        user_category=getattr(d, "user_category", None) or d.category,
        detected_category=getattr(d, "detected_category", None),
        category_confidence=getattr(d, "category_confidence", None),
        category_mismatch=getattr(d, "category_mismatch", False),
        original_filename=d.original_filename,
        content_type=d.content_type,
        size_bytes=d.size_bytes,
        sha256=d.sha256,
        status=d.status,
        uploaded_by=d.uploaded_by,
        uploaded_by_email=row.uploaded_by_email,
        created_at=d.created_at,
    )


@router.get("/categories", response_model=ModuleCategoriesResponse)
async def get_module_categories(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    module: Annotated[str, Query()] = "accounting",
) -> ModuleCategoriesResponse:
    """Returns the valid document categories belonging to the selected module."""
    raw_cats = get_categories_for_module(module)
    return ModuleCategoriesResponse(
        module=module,
        categories=[DocumentCategoryItem(value=val, label=lbl) for val, lbl in raw_cats],
    )


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    file: Annotated[UploadFile, File()],
    category: Annotated[DocumentCategory, Form()],
    principal: PrincipalDep,
    session: SessionDep,
    settings: SettingsDep,
    store: StoreDep,
    module: Annotated[str, Form()] = "accounting",
) -> DocumentOut:
    doc = await svc.upload_document(
        session,
        store,
        settings,
        principal,
        client_id,
        period_id,
        upload=file,
        category=category,
        module=module,
    )
    return _out(svc.DocumentRow(doc, principal.email))


@router.post("/batch", response_model=BatchUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_multiple_documents(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    files: Annotated[list[UploadFile], File()],
    category: Annotated[DocumentCategory, Form()],
    principal: PrincipalDep,
    session: SessionDep,
    settings: SettingsDep,
    store: StoreDep,
    module: Annotated[str, Form()] = "accounting",
) -> BatchUploadResponse:
    """Supports multiple document uploads under the selected module & category."""
    uploaded_docs: list[DocumentOut] = []
    failed_docs: list[dict[str, str]] = []

    for file in files:
        try:
            doc = await svc.upload_document(
                session,
                store,
                settings,
                principal,
                client_id,
                period_id,
                upload=file,
                category=category,
                module=module,
            )
            uploaded_docs.append(_out(svc.DocumentRow(doc, principal.email)))
        except Exception as exc:
            failed_docs.append(
                {"filename": getattr(file, "filename", "unknown"), "error": str(exc)}
            )

    return BatchUploadResponse(
        uploaded=uploaded_docs,
        failed=failed_docs,
        total_uploaded=len(uploaded_docs),
        total_failed=len(failed_docs),
    )


@router.post("/{document_id}/share", response_model=DocumentShareResponse)
async def share_document(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    body: DocumentShareRequest,
    principal: PrincipalDep,
    session: SessionDep,
) -> DocumentShareResponse:
    """Explicitly authorizes and references an existing document in another module without re-upload."""
    ref = await share_document_with_module(
        session,
        principal,
        client_id,
        period_id,
        document_id,
        target_module=body.target_module,
        target_category=body.target_category,
        notes=body.notes,
    )
    return DocumentShareResponse(
        id=ref.id,
        document_id=ref.document_id,
        module=ref.module,
        module_category=ref.module_category,
        status=ref.status,
        notes=ref.notes,
        created_at=ref.created_at,
    )


@router.get("", response_model=Page[DocumentOut])
async def list_documents(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    principal: PrincipalDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    module: Annotated[str | None, Query()] = None,
    category: DocumentCategory | None = None,
    status_filter: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[DocumentOut]:
    rows, total = await svc.list_documents(
        session,
        principal,
        client_id,
        period_id,
        limit=limit,
        offset=offset,
        module=module,
        category=category,
        status=status_filter,
        q=q,
    )
    return Page(items=[_out(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    principal: PrincipalDep,
    session: SessionDep,
) -> DocumentOut:
    return _out(await svc.get_document(session, principal, client_id, period_id, document_id))


def _content_disposition(filename: str) -> str:
    ascii_name = re.sub(r"[^A-Za-z0-9._ -]", "_", filename) or "download"
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'


@router.get("/{document_id}/download")
async def download_document(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    principal: PrincipalDep,
    session: SessionDep,
    store: StoreDep,
) -> StreamingResponse:
    doc, chunks = await svc.open_download(
        session, store, principal, client_id, period_id, document_id
    )
    return StreamingResponse(
        iterate_in_threadpool(chunks),
        media_type=doc.content_type,
        headers={
            "Content-Disposition": _content_disposition(doc.original_filename),
            "Content-Length": str(doc.size_bytes),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "X-Content-SHA256": doc.sha256,
        },
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    client_id: uuid.UUID,
    period_id: uuid.UUID,
    document_id: uuid.UUID,
    principal: PrincipalDep,
    session: SessionDep,
) -> Response:
    await svc.delete_document(session, principal, client_id, period_id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
