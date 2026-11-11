# GTMC CBT Cloud Synchronisation Design

## Status
Partially implemented on the VICORA CBT development branch. Android Host has a durable result outbox, HTTPS device pairing, retry/backoff, idempotent attempt identifiers and Windows-side acknowledgement/conflict handling. Windows Admin exposes pairing, device status/revocation and conflict review. Android-to-Windows result transfer is implemented for exams imported from a Windows Phone package. General bidirectional replication and automatic exam-package transfer are not implemented.

## Goals
- Allow authorised Admin devices to access the same GTMC CBT school data over the internet.
- Allow students to access published practice exams and teacher-assigned exams from their own devices.
- Store submitted answers and results centrally so Admin devices can review them.
- Keep Standalone Offline and local Wi-Fi/Hotspot hosting available.
- Provide independent Google Drive backup and a safe restore process.
- Keep the architecture ready for future school separation (school_id), without implementing subscriptions or monetisation now.

## Existing application facts
- The application currently uses SQLite at `DATA/cbt.db`.
- The schema contains: admins, classes, subjects, students, questions, exams, exam_classes, sessions, session_questions, answers, audit, and settings.
- Admin and student web clients call the Flask API under `/api/admin` and `/api/student`.
- Android Standalone/Host mode stores its own data under the app's private `gtmc-cbt-data` directory.
- Existing local backup uses SQLite's backup API and stores files in the local `backups` directory.
- Android Host result synchronisation to a paired Windows server is implemented for explicitly imported exam packages. It is not a general cloud database sync service.
- Exam package transfer from Windows to Android currently uses a manually transferred JSON file.
- No Google Drive backup integration is implemented by this plan.

## Proposed architecture
1. **Local engine:** retain SQLite and all existing Flask routes for offline and LAN operation.
2. **Cloud service:** add a separately deployed HTTPS API. Start with Google Apps Script for a low-cost prototype, with Google Sheets as the initial structured store.
3. **Sync client:** add an explicit connection setting and a sync queue. Local changes receive stable unique IDs, timestamps, and revision metadata. A successful server acknowledgement marks an operation as synced.
4. **Cloud backup:** independently export a consistent SQLite snapshot and upload it to a private Google Drive folder. Do not treat Sheets as the only backup.
5. **School isolation:** include a school identifier in cloud records and enforce it server-side. Only one GTMC school is enabled initially; no payment or subscription system is in scope.

## Data and sync rules
- Preserve existing numeric SQLite IDs locally; introduce stable UUIDs for cloud identity rather than assuming IDs from separate devices will match.
- Synchronise in dependency order: school/settings and users; classes and subjects; students; questions; exams and class assignments; exam attempts; answers and final results.
- Use server-side authentication and role checks for every operation. Never store Google account passwords in the app.
- Use idempotency keys for answer and submission uploads so retries do not create duplicate attempts or results.
- Keep an audit trail for cloud changes.
- Detect concurrent edits using record revisions. Do not silently overwrite a newer server version; present a conflict for review.
- A student exam attempt must be assigned to one authoritative attempt/session on the server. The client may cache the paper and queue answer updates during temporary disconnection, but final submission must be reconciled safely.
- Do not upload admin password hashes or session tokens to ordinary Sheets tables. Define a secure authentication approach before implementation.
- Minimise sensitive student data in cloud storage and restrict access to authorised school accounts.

## Google Sheets prototype limits
Sheets/Apps Script is suitable for a controlled prototype and modest usage, but it is not a high-concurrency transactional database. Apps Script quotas, execution limits, and spreadsheet write contention must be load-tested. If the school grows beyond safe limits, retain the same API contract and migrate the cloud store to a transactional database.

## Backup and restore safeguards
- Create a consistent SQLite snapshot with SQLite's backup API; do not copy a live WAL database file directly.
- Keep cloud backup independent from the sync connection and LAN hosting.
- Support automatic and manual backup, backup history, and a clear last-successful-backup status.
- Before restore, require confirmation and create a fresh safety backup of the current database.
- Validate a candidate backup before replacing live data; never restore directly over an open database.
- Do not uninstall, clear app data, or overwrite the live database during development/testing.
- Test restore using a disposable copy of sample data first.

## Delivery sequence
1. Confirm all existing schema migrations, API routes, data folder locations, and Android app variants.
2. Build and test the cloud API/authentication prototype with sample data only.
3. Add cloud sync for foundational records (classes, subjects, students, questions).
4. Add exam publishing/assignment and student attempt/result synchronisation.
5. Add retry queue, conflict handling, and multi-device tests.
6. Add Google Drive backup/restore independently, then test disaster recovery.
7. Add clear Admin controls for cloud connection, sync status, backup status, and restore.

## Acceptance criteria
- Existing offline and hotspot workflows continue to work without internet.
- A record created on one authorised Admin device appears on another after sync.
- Duplicate retries do not duplicate students, exams, attempts, answers, or results.
- Two conflicting edits are detected rather than silently lost.
- Student submissions are visible to Admin from a different device.
- Backup and restore can recover a test database on a second device without losing existing records.
- No production data is used in prototype testing.
- No change is merged into main or deployed without review and explicit approval.
