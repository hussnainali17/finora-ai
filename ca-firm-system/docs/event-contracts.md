# Event contracts (Phase 5 update)

Phase 5 establishes the full Kafka event infrastructure, versioned event schemas, idempotent consumer framework, bounded retries, and dead-letter queues.

## Envelope (`EventEnvelope[P]`, JSON)

Every event published to Kafka is wrapped in the standard envelope:
```json
{
  "event_id": "UUID (stable across redeliveries for idempotency)",
  "event_type": "string (e.g. file.uploaded, accounting.review.requested)",
  "schema_version": 1,
  "tenant_id": "UUID (firm_id)",
  "client_id": "UUID | null",
  "accounting_period_id": "UUID | null",
  "correlation_id": "string | null",
  "occurred_at": "ISO 8601 UTC timestamp",
  "payload": { ... }
}
```

- **Kafka record key**: `client_id` or `document_id` for per-entity ordering.
- **Headers**: `event_id`, `event_type`, `schema_version`.
- **Payload rule**: Contains IDs and object keys only — never document contents or secrets.

---

## Topic Catalog & Schemas

### 1. `file-uploaded`
- **Topic**: `file-uploaded` (DLQ: `file-uploaded-dlq`)
- **Event Type**: `file.uploaded`
- **Consumer Group**: `ca-firm-file-processing`
- **Payload**:
  ```json
  {
    "document_id": "UUID",
    "client_id": "UUID",
    "period_id": "UUID",
    "firm_id": "UUID",
    "object_key": "string",
    "category": "string",
    "original_filename": "string",
    "content_type": "string",
    "sha256": "string (64 hex chars)"
  }
  ```

### 2. `file-processing`
- **Topic**: `file-processing` (DLQ: `file-processing-dlq`)
- **Event Type**: `file.processing`
- **Emitted by**: `FileProcessingConsumer` when claiming a document for Agent 1 processing.

### 3. `data-structured`
- **Topic**: `data-structured` (DLQ: `data-structured-dlq`)
- **Event Type**: `data.structured`
- **Payload**:
  ```json
  {
    "extraction_run_id": "UUID",
    "document_id": "UUID",
    "client_id": "UUID",
    "period_id": "UUID",
    "firm_id": "UUID",
    "table_count": 3,
    "finding_count": 0,
    "status": "completed"
  }
  ```

### 4. `accounting-review-requested`
- **Topic**: `accounting-review-requested` (DLQ: `accounting-review-requested-dlq`)
- **Event Type**: `accounting.review.requested`
- **Consumer Group**: `ca-firm-accounting-review`
- **Payload**:
  ```json
  {
    "review_run_id": "UUID",
    "client_id": "UUID",
    "period_id": "UUID",
    "firm_id": "UUID"
  }
  ```

### 5. `reconciliation-requested`
- **Topic**: `reconciliation-requested` (DLQ: `reconciliation-requested-dlq`)
- **Event Type**: `reconciliation.requested`
- **Payload**:
  ```json
  {
    "review_run_id": "UUID",
    "client_id": "UUID",
    "period_id": "UUID",
    "firm_id": "UUID",
    "module": "sales_receivables | purchases_payables | bank_cash | inventory | fixed_assets | payroll"
  }
  ```

### 6. `workflow-status`
- **Topic**: `workflow-status` (DLQ: `workflow-status-dlq`)
- **Event Type**: `workflow.status`
- **Payload**:
  ```json
  {
    "workflow_id": "UUID",
    "client_id": "UUID",
    "period_id": "UUID",
    "firm_id": "UUID",
    "status": "running | completed | failed",
    "step": "string",
    "message": "string"
  }
  ```

---

## Consumer Framework Guarantees

1. **Idempotency via `worker_jobs`**:
   - Every consumer queries `worker_jobs` by `event_id` prior to processing.
   - If status is `completed` or `running`, redelivered duplicate messages are skipped as no-ops.
2. **Bounded Retries with Exponential Backoff**:
   - Consumers retry transient failures up to `max_retries` (default 3) with backoff `backoff_ms * (2^(attempt-1))`.
3. **Dead-Letter Queues (DLQ)**:
   - When max retries are exceeded or when an event payload is malformed/unparseable, raw message bytes are forwarded to `{topic}-dlq` with a `dlq_reason` header.
4. **Graceful Shutdown**:
   - Consumers listen for `SIGINT`/`SIGTERM`, finish processing the in-flight batch, commit manual offsets, and close cleanly.
