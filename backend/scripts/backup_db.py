#!/usr/bin/env python3
"""
scripts/backup_db.py

Production PostgreSQL Backup Utility for ProcureOps AI (Phase 16.2).

Features:
- Executes pg_dump using PostgreSQL's compressed custom format (-Fc).
- Avoids exposing credentials; uses docker compose exec / environment variables.
- Generates timestamped backup files: procureops_backup_{db}_{timestamp}.dump.
- Verifies backup integrity (rejects and removes empty / 0-byte files).
- Supports optional retention cleanup strictly limited to matching backups.
- Exits non-zero on any failure.
"""

import os
import sys
import time
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


BACKUP_PREFIX = "procureops_backup_"
BACKUP_SUFFIX = ".dump"


def generate_backup_filename(db_name: str, timestamp: Optional[datetime] = None) -> str:
    """Generates standard timestamped backup filename."""
    ts = timestamp or datetime.now(timezone.utc)
    ts_str = ts.strftime("%Y%m%d_%H%M%S")
    return f"{BACKUP_PREFIX}{db_name}_{ts_str}{BACKUP_SUFFIX}"


def filter_expired_backups(
    backup_files: List[Path],
    retention_days: int,
    now: Optional[datetime] = None
) -> List[Path]:
    """
    Identifies backups older than retention_days.
    Strictly filters only files matching BACKUP_PREFIX and BACKUP_SUFFIX.
    """
    if retention_days <= 0:
        return []

    current_time = now.timestamp() if now else time.time()
    cutoff_seconds = current_time - (retention_days * 86400)
    expired = []

    for file_path in backup_files:
        name = file_path.name
        if not (name.startswith(BACKUP_PREFIX) and name.endswith(BACKUP_SUFFIX)):
            continue
        try:
            stat = file_path.stat()
            if stat.st_mtime < cutoff_seconds:
                expired.append(file_path)
        except OSError:
            pass

    return expired


def run_backup(
    output_dir: Path,
    db_name: str,
    db_user: str,
    retention_days: Optional[int] = None,
    dry_run: bool = False,
) -> Path:
    """Executes pg_dump via docker compose and manages file integrity and retention."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = generate_backup_filename(db_name)
    target_path = output_dir / filename

    print(f"[*] Starting database backup: database='{db_name}', target='{target_path}'")

    if dry_run:
        print("[*] Dry run enabled; skipping actual pg_dump execution.")
        return target_path

    # Command executes pg_dump inside the postgres container using docker exec or docker compose
    container = os.getenv("PG_CONTAINER")
    if container:
        cmd = [
            "docker", "exec", container,
            "pg_dump", "-U", db_user, "-d", db_name, "-Fc", "--no-owner", "--no-acl"
        ]
    else:
        cmd = [
            "docker", "compose", "exec", "-T", "postgres",
            "pg_dump", "-U", db_user, "-d", db_name, "-Fc", "--no-owner", "--no-acl"
        ]

    try:
        with open(target_path, "wb") as f_out:
            proc = subprocess.run(cmd, stdout=f_out, stderr=subprocess.PIPE, check=False)

        if proc.returncode != 0:
            err_msg = proc.stderr.decode("utf-8", errors="replace").strip()
            if target_path.exists():
                target_path.unlink()
            raise RuntimeError(f"pg_dump failed with exit code {proc.returncode}: {err_msg}")

        # Validate file size
        file_size = target_path.stat().st_size
        if file_size == 0:
            target_path.unlink()
            raise RuntimeError("pg_dump produced a 0-byte backup file; backup aborted and deleted.")

        print(f"[+] Backup completed successfully: {target_path} ({file_size / 1024:.2f} KB)")

    except Exception as exc:
        if target_path.exists() and target_path.stat().st_size == 0:
            target_path.unlink()
        print(f"[-] ERROR during backup execution: {exc}", file=sys.stderr)
        raise

    # Manage retention if explicitly requested
    if retention_days and retention_days > 0:
        existing_files = list(output_dir.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"))
        expired_files = filter_expired_backups(existing_files, retention_days)
        for exp in expired_files:
            try:
                exp.unlink()
                print(f"[*] Retention cleanup: removed expired backup '{exp.name}' (older than {retention_days} days)")
            except OSError as err:
                print(f"[-] Warning: Failed to delete expired backup '{exp.name}': {err}", file=sys.stderr)

    return target_path


def load_env_defaults():
    """Loads default environment variables from .env if present."""
    candidates = [Path(".env"), Path(__file__).resolve().parent.parent / ".env"]
    for env_file in candidates:
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k not in os.environ:
                            os.environ[k] = v
            break


def main():
    load_env_defaults()
    parser = argparse.ArgumentParser(description="ProcureOps PostgreSQL Backup Utility")
    parser.add_argument("--output-dir", default=os.getenv("BACKUP_DIR", "./backups"), help="Directory to store backups")
    parser.add_argument("--db", default=os.getenv("POSTGRES_DB", "procureops_db"), help="Database name to back up")
    parser.add_argument("--user", default=os.getenv("POSTGRES_USER", "procureops"), help="PostgreSQL user")
    parser.add_argument("--retention-days", type=int, default=None, help="Retention period in days (optional)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate backup without executing pg_dump")

    args = parser.parse_args()

    try:
        run_backup(
            output_dir=Path(args.output_dir),
            db_name=args.db,
            db_user=args.user,
            retention_days=args.retention_days,
            dry_run=args.dry_run,
        )
        sys.exit(0)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
