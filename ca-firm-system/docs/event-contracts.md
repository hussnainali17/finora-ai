# Event contracts (Phase 2 subset)

Phase 5 builds the full Kafka framework (topics, consumer groups, retries, dead-lettering). Phase 2 fixes
the envelope and the first event so that work does not need to change them.

## Envelope (`EventEnvelope`, JSON)
`event_id` (UUID; stable across redeliveries), `event_type`, `schema_version`, `tenant_id` (firm),
`client_id`, `accounting_period_id`, `correlation_id` (the originating request id), `occurred_at`,
`payload`. Kafka record key = `client_id` (per-client ordering); headers `event_id`, `event_type`,
`schema_version`. Payloads carry **IDs and object keys only** - never file contents, filenames or secrets.

## `file.uploaded` v1 - topic `file-uploaded`
`payload`: `{document_id, object_key, sha256, size_bytes, content_type, category}`.
A consumer must (1) deduplicate on `event_id`, (2) re-check the document and authorise by
`tenant_id`/`client_id`, and (3) fetch the file through the backend/storage layer using `object_key`.

## Delivery guarantees
1. **Committed-only.** The event row is written to `outbox_events` in the same DB transaction as the
   document. A failed upload (storage error, validation, duplicate, DB error) commits no document and no
   event; if the DB step fails after the object was stored, the object is deleted.
2. **At-least-once.** A relay publishes pending rows (`acks=all`, idempotent producer) and then sets
   `published_at` and advances the document `uploaded` -> `queued`. If the process dies between Kafka
   accepting the message and `published_at` being saved, the **same `event_id`** is sent again. Consumers
   must be idempotent. The relay never moves a document backwards (a document already `processing` stays so).
3. **Retry.** Failures set `attempts`, a class-name-only `last_error`, and exponential backoff
   (2^n seconds, capped at 300 s). Rows stay pending until published.
4. **Concurrency.** Relays use `FOR UPDATE SKIP LOCKED`, so several backend replicas never publish the
   same row twice at the same time.

Topics are auto-created by the dev broker; Phase 5 defines partitions/retention explicitly.
