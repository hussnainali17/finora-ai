# Backup and Disaster Recovery Procedure (Phase 11)

This document describes the automated backup policy, integrity verification, and point-in-time recovery runbook for the CA Firm System.

---

## 1. Backup Architecture

### Daily Automated Schedule
1. **PostgreSQL Database**:
   - Automated logical dump using `pg_dump` with gzip compression level 9.
   - Script: `infrastructure/backup/backup.sh`.
   - Generates checksum file `backup_<timestamp>.sha256`.
2. **MinIO / S3 Object Storage**:
   - Replicated to secondary backup bucket or versioned S3 storage.
3. **Kafka Topics**:
   - Kafka KRaft retains event data per topic retention policies (7 days default).

---

## 2. Restoration & Disaster Recovery Runbook

### Step 1: Verify Backup Integrity
Verify that the archive is intact using the SHA-256 checksum:
```bash
sha256sum -c backup_20261107_120000Z.sha256
```

### Step 2: Database Restoration
Run the restoration script:
```bash
./infrastructure/backup/restore.sh /backups/postgres_20261107_120000Z.sql.gz
```
The script will prompt for explicit confirmation before restoring.

### Step 3: Run Alembic Migrations
Verify schema migrations are up to date:
```bash
cd backend
alembic upgrade head
```

### Step 4: Health Verification
Run health checks against the live system:
```bash
curl -f http://localhost:8000/api/v1/health/ready
```
Ensure all external dependencies (Postgres, Redis, Kafka, MinIO, LiteLLM) return `status: "ok"`.
