#!/usr/bin/env bash
# Verified restoration script for CA Firm System disaster recovery.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <path_to_backup.sql.gz>"
  exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "${BACKUP_FILE}" ]; then
  echo "[-] Backup file not found: ${BACKUP_FILE}"
  exit 1
fi

# Verify checksum if present
CHECKSUM_FILE="${BACKUP_FILE%.sql.gz}.sha256"
if [ -f "${CHECKSUM_FILE}" ]; then
  echo "[+] Verifying SHA-256 integrity..."
  sha256sum -c "${CHECKSUM_FILE}"
fi

echo "[!] WARNING: This will overwrite data in database ${POSTGRES_DB}!"
read -r -p "Are you sure you want to proceed with restore? (yes/no): " CONFIRM
if [ "${CONFIRM}" != "yes" ]; then
  echo "[-] Restore aborted."
  exit 0
fi

echo "[+] Restoring database from ${BACKUP_FILE}..."
gunzip -c "${BACKUP_FILE}" | PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST:-postgres}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

echo "[✓] Database restoration completed successfully."
