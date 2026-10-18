#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/backup_db.sh
#
# Production PostgreSQL automated backup script for Linux hosts & cron jobs.
# Usage:
#   ./scripts/backup_db.sh [OUTPUT_DIR] [RETENTION_DAYS]
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

if [ -f .env ]; then
    set -a
    source .env 2>/dev/null || true
    set +a
fi

BACKUP_DIR="${1:-./backups}"
RETENTION_DAYS="${2:-}"
DB_NAME="${POSTGRES_DB:-procureops_db}"
DB_USER="${POSTGRES_USER:-procureops}"

mkdir -p "${BACKUP_DIR}"

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
FILENAME="procureops_backup_${DB_NAME}_${TIMESTAMP}.dump"
TARGET="${BACKUP_DIR}/${FILENAME}"

echo "[*] Starting PostgreSQL backup: database='${DB_NAME}', target='${TARGET}'"

# Execute pg_dump inside postgres container via docker compose
if ! docker compose exec -T postgres pg_dump -U "${DB_USER}" -d "${DB_NAME}" -Fc --no-owner --no-acl > "${TARGET}"; then
    echo "[-] Backup failed. Removing incomplete file..." >&2
    rm -f "${TARGET}"
    exit 1
fi

# Verify non-empty file
if [ ! -s "${TARGET}" ]; then
    echo "[-] Backup failed: Target file is empty (0 bytes). Removing..." >&2
    rm -f "${TARGET}"
    exit 1
fi

FILESIZE=$(du -h "${TARGET}" | cut -f1)
echo "[+] Backup successfully created: ${TARGET} (${FILESIZE})"

# Retention policy (if specified)
if [ -n "${RETENTION_DAYS}" ] && [ "${RETENTION_DAYS}" -gt 0 ]; then
    echo "[*] Running retention cleanup for files older than ${RETENTION_DAYS} days..."
    find "${BACKUP_DIR}" -type f -name "procureops_backup_${DB_NAME}_*.dump" -mtime +"${RETENTION_DAYS}" -exec rm -v {} \;
fi

echo "[+] Done."
exit 0
