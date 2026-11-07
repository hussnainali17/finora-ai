"""OCR for scanned PDFs and images. OCRmyPDF + Tesseract; injectable for tests."""

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Protocol

from app.agents.intake_agent.types import ExtractionError


class OcrEngine(Protocol):
    def ocr_pdf(self, pdf_bytes: bytes) -> bytes:
        """Return a PDF with a searchable text layer."""
        ...


class OcrMyPdfEngine:
    def __init__(self, language: str = "eng", timeout: int = 300) -> None:
        self.language = language
        self.timeout = timeout

    def ocr_pdf(self, pdf_bytes: bytes) -> bytes:
        with tempfile.TemporaryDirectory() as td:
            src, dst = Path(td, "in.pdf"), Path(td, "out.pdf")
            src.write_bytes(pdf_bytes)
            try:
                proc = subprocess.run(  # noqa: S603
                    [
                        sys.executable, "-m", "ocrmypdf", "--skip-text",
                        "--output-type", "pdf", "-l", self.language, "--quiet",
                        str(src), str(dst),
                    ],
                    capture_output=True, timeout=self.timeout, check=False,
                )  # fmt: skip
            except FileNotFoundError as exc:
                raise ExtractionError("ocr_unavailable", "OCR is not installed") from exc
            except subprocess.TimeoutExpired as exc:
                raise ExtractionError("ocr_timeout", "OCR timed out") from exc
            if proc.returncode != 0 or not dst.exists():
                raise ExtractionError("ocr_failed", "OCR could not read this document")
            return dst.read_bytes()


def image_to_pdf(data: bytes) -> bytes:
    import pymupdf

    try:
        with pymupdf.open(stream=data) as img:
            return bytes(img.convert_to_pdf())
    except Exception as exc:  # noqa: BLE001 - PyMuPDF raises several types for bad images
        raise ExtractionError("corrupt_file", "Image could not be read") from exc
