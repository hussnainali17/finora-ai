FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Tesseract is used for OCR of scanned PDFs/images (Agent 1). Parsing runs in-process for now;
# sandboxing of untrusted-file parsing is a Phase 11 hardening item.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies (editable so the bind-mounted source is used in development)
COPY pyproject.toml ./
COPY app ./app
RUN pip install -e ".[dev]"

COPY . .

RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
