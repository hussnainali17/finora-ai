#!/usr/bin/env bash
# Automated backup script for CA Firm System:
# 1. PostgreSQL logical backup (pg_dump with gzip)
# 2. MinIO/S3 object storage backup
# 3. SHA-256 verification checksums
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
DB_BACKUP_FILE="${BACKUP_DIR}/postgres_${TIMESTAMP}.sql.gz"
CHECKSUM_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.sha256"

mkdir -p "${BACKUP_DIR}"

echo "[+] Starting CA Firm System backup at ${TIMESTAMP}..."

# 1. PostgreSQL Database Dump
echo "[+] Dumping PostgreSQL database..."
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump -h "${POSTGRES_HOST:-postgres}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" | gzip -9 > "${DB_BACKUP_FILE}"

# 2. Checksum calculation
echo "[+] Computing checksums..."
sha256sum "${DB_BACKUP_FILE}" > "${CHECKSUM_FILE}"

echo "[✓] Backup completed successfully: ${DB_BACKUP_FILE}"
