"""
backend/tests/test_backup_utility.py

Unit tests for PostgreSQL backup utility (Phase 16.2 Phase D).

Verifies:
  1. Standardized backup filename formatting.
  2. Retention policy strictly filtering matching backups older than threshold.
  3. Retention policy strictly ignoring unrelated files.
  4. Dry-run mode without executing external commands.
  5. Zero-byte backup rejection and automatic file cleanup.
  6. Subprocess error handling with non-zero exit code.
"""

import sys
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add repository root to sys.path so we can import scripts.backup_db
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.backup_db import (
    BACKUP_PREFIX,
    BACKUP_SUFFIX,
    generate_backup_filename,
    filter_expired_backups,
    run_backup,
)


def test_generate_backup_filename_format():
    """Generates valid filename with database name and timestamp."""
    dt = datetime(2026, 10, 18, 20, 30, 45, tzinfo=timezone.utc)
    filename = generate_backup_filename("procureops", dt)
    assert filename == "procureops_backup_procureops_20261018_203045.dump"
    assert filename.startswith(BACKUP_PREFIX)
    assert filename.endswith(BACKUP_SUFFIX)


def test_filter_expired_backups_retention_days(tmp_path):
    """Retention strictly identifies backups older than threshold."""
    now = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
    old_time = (now - timedelta(days=10)).timestamp()
    recent_time = (now - timedelta(days=2)).timestamp()

    old_backup = tmp_path / "procureops_backup_procureops_20261008_120000.dump"
    recent_backup = tmp_path / "procureops_backup_procureops_20261016_120000.dump"
    unrelated_file = tmp_path / "other_backup_file.dump"
    random_txt = tmp_path / "procureops_backup_notes.txt"

    for f in (old_backup, recent_backup, unrelated_file, random_txt):
        f.write_text("data")

    # Set file modification times
    import os
    os.utime(old_backup, (old_time, old_time))
    os.utime(recent_backup, (recent_time, recent_time))
    os.utime(unrelated_file, (old_time, old_time))
    os.utime(random_txt, (old_time, old_time))

    all_files = list(tmp_path.iterdir())
    expired = filter_expired_backups(all_files, retention_days=7, now=now)

    # Only old_backup should be expired
    assert len(expired) == 1
    assert expired[0].name == old_backup.name


def test_filter_expired_backups_zero_or_negative_retention(tmp_path):
    """When retention is <= 0, no files are expired."""
    test_file = tmp_path / "procureops_backup_procureops_old.dump"
    test_file.write_text("data")

    assert filter_expired_backups([test_file], retention_days=0) == []
    assert filter_expired_backups([test_file], retention_days=-5) == []


def test_run_backup_dry_run(tmp_path):
    """Dry-run returns path without calling subprocess."""
    with patch("subprocess.run") as mock_run:
        target = run_backup(
            output_dir=tmp_path,
            db_name="testdb",
            db_user="testuser",
            dry_run=True,
        )
        assert mock_run.call_count == 0
        assert target.name.startswith("procureops_backup_testdb_")
        assert target.name.endswith(".dump")


def test_run_backup_zero_byte_aborts_and_cleans_up(tmp_path):
    """If pg_dump generates an empty file (0 bytes), it is deleted and an exception is raised."""
    def fake_subprocess_run(cmd, stdout, stderr, check):
        # Empty file written
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        return mock_proc

    with patch("subprocess.run", side_effect=fake_subprocess_run):
        with pytest.raises(RuntimeError, match="0-byte backup file"):
            run_backup(
                output_dir=tmp_path,
                db_name="testdb",
                db_user="testuser",
                dry_run=False,
            )

        # Confirm target directory is empty (no 0-byte file left)
        assert len(list(tmp_path.glob("*.dump"))) == 0


def test_run_backup_nonzero_exit_code_aborts(tmp_path):
    """If pg_dump fails with non-zero exit code, error is raised and incomplete file cleaned up."""
    def fake_subprocess_fail(cmd, stdout, stderr, check):
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = b"FATAL: database does not exist"
        return mock_proc

    with patch("subprocess.run", side_effect=fake_subprocess_fail):
        with pytest.raises(RuntimeError, match="pg_dump failed with exit code 1"):
            run_backup(
                output_dir=tmp_path,
                db_name="testdb",
                db_user="testuser",
                dry_run=False,
            )

        assert len(list(tmp_path.glob("*.dump"))) == 0
