"""Offline, explicit-confirmation SQLite restore utility for GTMC CBT.

Run only after the CBT server has been fully stopped:
    python restore_backup.py --data-dir /path/to/CBT_DATA --backup cbt_..._manual.db --confirm-restore

This tool never imports app.py and never chooses a database directory implicitly.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKUP_NAME = re.compile(r"cbt_[0-9_]+_(?:manual|auto)(?:_pre_restore_[a-f0-9]{8})?\.db\Z")
REQUIRED_COLUMNS = {
    "admins": {"id", "username", "password_hash"},
    "classes": {"id", "name"},
    "subjects": {"id", "name"},
    "students": {"id", "reg_no", "name", "class_id", "access_code"},
    "questions": {"id", "subject_id", "text", "a", "b", "c", "d", "answer", "marks", "topic", "difficulty"},
    "exams": {"id", "title", "subject_id", "duration_min", "num_questions", "shuffle", "show_score", "pass_mark", "instructions", "status", "created_ts"},
    "exam_classes": {"exam_id", "class_id"},
    "sessions": {"id", "exam_id", "student_id", "token", "device", "start_ts", "last_seen", "extra_sec", "status", "submitted_ts", "score", "total", "tab_switches"},
    "session_questions": {"session_id", "pos", "question_id", "opt_order"},
    "answers": {"session_id", "question_id", "choice", "flagged", "ts"},
    "audit": {"id", "ts", "actor", "action"},
    "settings": {"key", "value"},
}


class RestoreError(RuntimeError):
    """Raised when a restore is unsafe or cannot be completed."""


def validate_database(path: Path) -> None:
    if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
        raise RestoreError("Backup file is missing, empty, or is a symbolic link.")
    try:
        conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True, timeout=10)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise RestoreError("SQLite integrity check failed.")
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            missing_tables = set(REQUIRED_COLUMNS) - tables
            if missing_tables:
                raise RestoreError("Backup is missing required tables: " + ", ".join(sorted(missing_tables)))
            for table, required in REQUIRED_COLUMNS.items():
                columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
                missing = required - columns
                if missing:
                    raise RestoreError(
                        f"Backup table {table} is missing required columns: " + ", ".join(sorted(missing))
                    )
            violations = conn.execute("PRAGMA foreign_key_check").fetchmany(1)
            if violations:
                raise RestoreError("Backup contains foreign-key violations.")
        finally:
            conn.close()
    except RestoreError:
        raise
    except (sqlite3.DatabaseError, OSError, ValueError) as exc:
        raise RestoreError(f"Could not validate SQLite backup: {exc}") from exc


def _snapshot(source: Path, destination: Path) -> None:
    src = sqlite3.connect(str(source), timeout=15)
    dst = sqlite3.connect(str(destination), timeout=15)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()
    validate_database(destination)


def _has_live_attempts(db_path: Path) -> bool:
    conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True, timeout=5)
    try:
        row = conn.execute(
            """SELECT 1 FROM exams WHERE status='live' LIMIT 1"""
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def restore_backup(data_dir: str | Path, backup_name: str, *, confirmed: bool = False) -> dict:
    if not confirmed:
        raise RestoreError("Explicit confirmation is required; no database was changed.")
    if not isinstance(backup_name, str) or not BACKUP_NAME.fullmatch(backup_name):
        raise RestoreError("Invalid backup filename.")
    root = Path(data_dir).expanduser().resolve()
    backup_dir = root / "backups"
    active_db = root / "cbt.db"
    selected = backup_dir / backup_name
    if not root.is_dir() or not backup_dir.is_dir() or not active_db.is_file():
        raise RestoreError("Data folder, backup folder, or active database was not found.")
    if selected.parent.resolve() != backup_dir.resolve() or selected.is_symlink():
        raise RestoreError("Selected backup must be a regular file inside the backups folder.")
    validate_database(selected)
    validate_database(active_db)
    if _has_live_attempts(active_db):
        raise RestoreError("A live exam is still open. Close all live exams and stop the CBT server first.")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    pre_name = f"cbt_{stamp}_manual_pre_restore_{uuid.uuid4().hex[:8]}.db"
    pre_path = backup_dir / pre_name
    candidate = root / f".cbt_restore_{uuid.uuid4().hex}.tmp"
    rollback = root / f".cbt_rollback_{uuid.uuid4().hex}.tmp"
    replaced = False
    try:
        _snapshot(active_db, pre_path)
        shutil.copyfile(selected, candidate)
        # Flush the copied candidate to disk using a writable handle. Windows
        # does not permit fsync on a read-only file descriptor.
        with candidate.open("r+b") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        validate_database(candidate)

        # The application must be stopped: no process may hold cbt.db open.
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(active_db) + suffix)
            if sidecar.exists():
                raise RestoreError(
                    f"SQLite sidecar {sidecar.name} still exists. Stop the CBT app completely and retry."
                )
        os.replace(candidate, active_db)
        replaced = True
        validate_database(active_db)
        return {
            "restored": backup_name,
            "pre_restore_backup": pre_name,
            "database": str(active_db),
        }
    except Exception as exc:
        if replaced and pre_path.exists():
            try:
                shutil.copyfile(pre_path, rollback)
                os.replace(rollback, active_db)
                validate_database(active_db)
            except Exception as rollback_exc:
                raise RestoreError(
                    f"Restore failed ({exc}); automatic rollback also failed ({rollback_exc}). "
                    f"Keep the pre-restore backup: {pre_path}"
                ) from rollback_exc
        if isinstance(exc, RestoreError):
            raise
        raise RestoreError(f"Restore failed; previous database was protected: {exc}") from exc
    finally:
        for temp in (candidate, rollback):
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely restore a GTMC CBT SQLite backup.")
    parser.add_argument("--data-dir", required=True, help="Exact CBT data directory containing cbt.db and backups/")
    parser.add_argument("--backup", required=True, help="Backup filename inside the backups folder")
    parser.add_argument(
        "--confirm-restore", action="store_true",
        help="Required confirmation that the CBT server is stopped and this restore is intended",
    )
    args = parser.parse_args()
    try:
        result = restore_backup(args.data_dir, args.backup, confirmed=args.confirm_restore)
    except RestoreError as exc:
        parser.error(str(exc))
    print("RESTORE SUCCESS")
    print(f"Restored: {result['restored']}")
    print(f"Pre-restore safety copy: {result['pre_restore_backup']}")
    print(f"Database: {result['database']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
