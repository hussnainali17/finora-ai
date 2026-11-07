# Production Operations & Incident Runbooks (Phase 11)

---

## Runbook 1: Production Deployment

### 1. Pre-Deployment Checklist
- [ ] Ensure all environment variables are populated in `.env` without `CHANGE_ME` placeholders.
- [ ] Verify `APP_ENV=production` and `COOKIE_SECURE=true`.
- [ ] Confirm valid SSL certificates exist in `infrastructure/nginx/ssl/live/`.

### 2. Deploying Stack
```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### 3. Running Database Migrations
```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

---

## Runbook 2: Secret Rotation

### JWT Secret Rotation
1. Generate a new cryptographic key: `openssl rand -hex 32`.
2. Update `JWT_SECRET` in production `.env`.
3. Restart backend services: `docker compose -f docker-compose.prod.yml restart backend`.
4. *Effect*: Existing access tokens expire within 15 minutes; refresh tokens will require re-login.

### LiteLLM Master Key Rotation
1. Generate new key in LiteLLM Proxy configuration.
2. Update `LITELLM_API_KEY` in backend environment.
3. Restart backend: `docker compose -f docker-compose.prod.yml restart backend`.

---

## Runbook 3: Incident Response

### High Kafka Lag / Worker Stalled
1. Check worker logs:
   ```bash
   docker compose -f docker-compose.prod.yml logs --tail=100 -f worker
   ```
2. Verify Kafka topics and dead-letter queues:
   ```bash
   curl -H "Authorization: Bearer <TOKEN>" https://<DOMAIN>/api/v1/kafka/topics
   ```
3. Restart workers to trigger clean partition rebalance:
   ```bash
   docker compose -f docker-compose.prod.yml restart worker
   ```

### Review Finding False Positive Investigation
1. Note the finding ID from `GET /clients/{id}/periods/{id}/review/{run_id}/findings`.
2. Trace `source_ref` (`document_id`, `table_id`, `row_index`).
3. Verify the original file row via `GET /documents/{document_id}/review`.
4. Mark the finding as `explained` with review note via `PATCH /review/{run_id}/findings/{finding_id}`.
