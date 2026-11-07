"""Safe handling of uploaded bytes: size-limited streaming, hashing, filename sanitising and
content (magic-byte) verification. Nothing here parses accounting content (that is Phase 3)."""

import hashlib
import re
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from typing import IO, Protocol

from fastapi import UploadFile

from app.core.errors import DomainValidationError, PayloadTooLargeError, UnsupportedMediaTypeError

READ_CHUNK = 1024 * 1024
_CONTENT_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass
class SpooledFile:
    file: IO[bytes]
    size: int
    sha256: str
    head: bytes

    def close(self) -> None:
        self.file.close()


class FileScanner(Protocol):
    """Integration point for malware scanning (ClamAV etc.), wired in Phase 11."""

    async def scan(self, file: IO[bytes], *, filename: str) -> None: ...


class NoopScanner:
    async def scan(self, file: IO[bytes], *, filename: str) -> None:  # pragma: no cover
        return None


def sanitize_filename(raw: str | None) -> str:
    """Display-only name: no directories, control characters or leading dots; max 200 chars."""
    name = unicodedata.normalize("NFC", (raw or "").replace("\\", "/").split("/")[-1])
    name = _CONTROL.sub("", name).strip().lstrip(".")
    name = re.sub(r"\s+", " ", name)
    if len(name) > 200:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: 200 - len(ext) - 1] + dot + ext) if dot and len(ext) <= 10 else name[:200]
    return name


def extension_of(filename: str) -> str:
    return filename.rpartition(".")[2].lower() if "." in filename else ""


async def spool_upload(upload: UploadFile, max_bytes: int) -> SpooledFile:
    """Streams to a temp file while hashing; aborts as soon as the size limit is exceeded."""
    tmp = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)  # noqa: SIM115
    digest = hashlib.sha256()
    size = 0
    head = b""
    try:
        while chunk := await upload.read(READ_CHUNK):
            size += len(chunk)
            if size > max_bytes:
                raise PayloadTooLargeError(
                    f"File exceeds the maximum upload size of {max_bytes // (1024 * 1024)} MB"
                )
            if not head:
                head = chunk[:4096]
            digest.update(chunk)
            tmp.write(chunk)
    except BaseException:
        tmp.close()
        raise
    if size == 0:
        tmp.close()
        raise DomainValidationError("The uploaded file is empty")
    tmp.seek(0)
    return SpooledFile(file=tmp, size=size, sha256=digest.hexdigest(), head=head)


def verify_content(spooled: SpooledFile, extension: str) -> str:
    """Checks the bytes really are what the extension claims. Returns the canonical content type."""
    head, f = spooled.head, spooled.file
    ok: bool
    if extension == "pdf":
        ok = head.lstrip(b"\x00\r\n ").startswith(b"%PDF-")
    elif extension in ("png",):
        ok = head.startswith(b"\x89PNG\r\n\x1a\n")
    elif extension in ("jpg", "jpeg"):
        ok = head.startswith(b"\xff\xd8\xff")
    elif extension == "xls":
        ok = head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    elif extension == "xlsx":
        ok = False
        if head.startswith(b"PK\x03\x04"):
            try:
                f.seek(0)
                with zipfile.ZipFile(f) as zf:  # reads only the central directory
                    names = set(zf.namelist())
                ok = "[Content_Types].xml" in names and any(n.startswith("xl/") for n in names)
            except zipfile.BadZipFile:
                ok = False
            finally:
                f.seek(0)
    elif extension == "csv":
        ok = b"\x00" not in head and _decodes_as_text(head)
    else:
        raise UnsupportedMediaTypeError("This file type is not accepted")
    if not ok:
        raise UnsupportedMediaTypeError(
            f"The file content does not match a .{extension} file; it may be corrupted."
        )
    f.seek(0)
    return _CONTENT_TYPES[extension]


def _decodes_as_text(head: bytes) -> bool:
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            head.decode(enc)
            return True
        except UnicodeDecodeError:
            # the 4 KiB cut may split a multibyte char at the end
            try:
                head[:-3].decode(enc)
                return True
            except UnicodeDecodeError:
                continue
    return False
