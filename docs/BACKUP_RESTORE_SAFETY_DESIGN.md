# GTMC CBT — Backup and Restore Safety Design

## Status

Design document only. This file does not implement Google Drive access, upload, download, restore, or change the live database.

## Preserve the existing operating modes

- Standalone Windows and Android operation must continue without internet.
- School LAN/hotspot operation must continue using the local SQLite server.
- Cloud backup is an independent copy/restore service; it must not become the exam server or silently replace local SQLite.
- Android Admin and Examination apps currently have separate private data directories. A backup made by one device/app must be explicitly selected before it is restored on another device.
- Never merge two SQLite database files by copying one over another while either is running.

## Local snapshot requirements

1. Create a consistent SQLite snapshot with the SQLite backup API, not by copying a live database file.
2. Close snapshot connections and run `PRAGMA integrity_check`; accept only the exact result `ok`.
3. Record a manifest containing backup UUID, school identifier, app/database schema version, creation time (UTC), SQLite file size, SHA-256 digest, and source device label. Do not include passwords, access codes, or session tokens in the manifest.
4. Keep timestamped/versioned backups. Do not overwrite the only previous good backup.
5. Retain a configurable number of local automatic backups and never delete manual backups as a side effect of automatic retention.

## Google Drive requirements

- Use Google OAuth for an installed application. Do not embed a client secret, refresh token, or service-account private key in the APK, EXE, source repository, or Google Sheet.
- Ask the administrator to sign in and explicitly choose the backup destination/account.
- Store backup files as separate versioned files; do not replace the last known-good file.
- Upload the SQLite snapshot and manifest, then verify the uploaded file metadata/checksum where the Drive API permits.
- Support a clear last-successful-backup time and a visible failure state. Offline mode must continue when Drive is unavailable.
- Backups must be scoped to the school/account. Future multi-school support must use a stable school ID and enforce isolation.
- Do not upload real student data during development tests. Use generated synthetic records.

## Restore safety requirements

Restore is a destructive administrative operation and must require an explicit confirmation showing the selected backup date, school ID, and source device.

Before replacing a local database:

1. Stop accepting new exam actions and ensure no live exam is running.
2. Create a fresh pre-restore snapshot of the current local database.
3. Download the selected backup to a temporary file, never directly over the active database.
4. Verify its SHA-256 digest against the manifest and run SQLite `PRAGMA integrity_check`.
5. Check the school ID and schema compatibility. Reject a backup from another school or an unsupported future schema.
6. Open the candidate database read-only and verify required tables/columns and foreign-key consistency.
7. Close all database connections, checkpoint/close WAL state, and replace the database using a recoverable atomic file operation.
8. Re-open the database and run integrity checks again. If any step fails, restore the pre-restore snapshot automatically.
9. Record an audit event with actor, time, backup UUID, and outcome. Never log secrets or student answers.

A restore must never run automatically merely because a device signs in or connects to Wi-Fi.

## Required tests before release

- Snapshot consistency while normal writes are occurring.
- Integrity check and SHA-256 mismatch rejection.
- Corrupt, truncated, wrong-school, and unsupported-schema backup rejection.
- Restore to a disposable database and compare expected records and relationships.
- Simulated interruption before replacement, during replacement, and after replacement.
- Rollback to the pre-restore snapshot on every failed restore path.
- Two-device backup discovery and restore using the same authorized school account.
- Offline operation when Drive is unavailable, revoked, or out of quota.
- Permission checks: non-admin users cannot upload, list, delete, or restore school backups.
- Retention never deletes the last known-good backup or manual backups unexpectedly.

## Current implementation boundary

The repository currently has local manual backup/list/download endpoints and a local automatic backup worker. The current automatic worker creates backups while an exam is live, every ten minutes, and retains up to 30 automatic files. The current implementation does not yet validate snapshot integrity, create manifests, upload to Drive, or provide a restore endpoint. Those gaps must be addressed in separate, reviewed changes.

The first code milestone is isolated regression coverage for the existing local backup behavior. Restore implementation should follow only after the validation and rollback helpers have their own tests on disposable databases.
