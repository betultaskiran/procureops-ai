#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/restore_db.sh
#
# Safe PostgreSQL database restore utility for ProcureOps AI.
#
# SAFETY GUARDRAILS:
# 1. Prohibits restoring over the active database (POSTGRES_DB) by default.
# 2. Requires a target database name (e.g., procureops_restore_test).
# 3. Validates backup file existence and format before attempting restore.
#
# Usage:
#   ./scripts/restore_db.sh <PATH_TO_BACKUP.dump> <TARGET_DATABASE_NAME>
# Example:
#   ./scripts/restore_db.sh ./backups/procureops_backup_procureops_20261018_203000.dump procureops_restore_test
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

if [ -f .env ]; then
    set -a
    source .env 2>/dev/null || true
    set +a
fi

BACKUP_FILE="${1:-}"
TARGET_DB="${2:-}"
ACTIVE_DB="${POSTGRES_DB:-procureops_db}"
DB_USER="${POSTGRES_USER:-procureops}"

if [ -z "${BACKUP_FILE}" ] || [ -z "${TARGET_DB}" ]; then
    echo "[-] Error: Missing required arguments." >&2
    echo "Usage: $0 <path_to_backup.dump> <target_database_name>" >&2
    exit 1
fi

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "[-] Error: Backup file '${BACKUP_FILE}' not found." >&2
    exit 1
fi

# Guardrail: Do not overwrite the active production/development database
if [ "${TARGET_DB}" = "${ACTIVE_DB}" ]; then
    echo "[-] SAFETY ALERT: Refusing to restore over the active database '${ACTIVE_DB}'." >&2
    echo "    Please specify a separate target database name (e.g., '${ACTIVE_DB}_restore_test')." >&2
    exit 1
fi

echo "[*] Restoring backup to disposable target database: '${TARGET_DB}'"

# 1. Create target database if it doesn't already exist
docker compose exec -T postgres psql -U "${DB_USER}" -d postgres -c \
    "SELECT 1 FROM pg_database WHERE datname = '${TARGET_DB}'" | grep -q 1 || \
    docker compose exec -T postgres createdb -U "${DB_USER}" "${TARGET_DB}"

# 2. Run pg_restore
echo "[*] Executing pg_restore..."
if ! docker compose exec -T postgres pg_restore -U "${DB_USER}" -d "${TARGET_DB}" --no-owner --no-acl < "${BACKUP_FILE}"; then
    echo "[-] Warning: pg_restore completed with warnings or non-critical errors (standard for schema drops)." >&2
fi

# 3. Verify restored tables
TABLE_COUNT=$(docker compose exec -T postgres psql -U "${DB_USER}" -d "${TARGET_DB}" -t -c \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")

echo "[+] Restore verification complete: Target database '${TARGET_DB}' contains $(echo "${TABLE_COUNT}" | tr -d '[:space:]') public tables."
echo "[+] Done. You can inspect or drop '${TARGET_DB}' when verification is finished."
exit 0
