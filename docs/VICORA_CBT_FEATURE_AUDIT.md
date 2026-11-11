# VICORA CBT Feature Audit

This is a source-level inventory of the imported CBT baseline at source commit `05fd17e94bf494eef228d120711a2ffb5afca076`. It is not a live security review or a passing build report.

## Already present in the imported CBT

### Examination administration
- Admin sign-in, sign-out, password change, settings and dashboard
- Student and class management, access-code generation/regeneration, import/export
- Subject and question management, bulk question import/export
- Examination creation, class assignment, opening, pausing, resuming, closing and time extension
- Live candidate monitoring and session actions
- Objective and theory answer handling, manual theory marking, results and exports
- Candidate messaging and activity/audit log
- Backup creation, listing, download and restore support

### Candidate experience
- Student login using registration number and access code
- Assigned live-exam listing, begin/resume, paper retrieval
- Objective and theory answer saving, heartbeat and final submission
- Student inbox and published grades
- Browser/PWA home-exam client with a local pending-answer retry queue

### Android host and proctoring
- Android Admin and Examination app flavors
- Android host pairing and local service
- Durable result sync worker/scheduler and sync backend
- Device status/revocation and sync-conflict review routes
- Exam-level proctor policy, proctor event collection and review
- Remote-host exam package export/import

### Technical foundation
- Flask + SQLite backend with existing database tables for exams, sessions, answers, theory marks, proctor events, Android devices, sync receipts/conflicts/outbox, audit and settings
- Windows Electron examination and admin clients
- Windows offline installer definitions and build workflows
- Vercel student gateway configuration and PWA shell
- Automated Python regression tests

## Gaps to address for a commercial VICORA CBT

1. **Granular staff roles and permissions.** The current backend has an admin account/session model and a student model. There is no complete role-permission system for owner, exam administrator, invigilator, examiner/marker or support staff.
2. **Persistent login throttling.** Failed-login throttling is currently process-memory based; it resets when the server restarts and is not shared between multiple server processes.
3. **Commercial tenant separation.** The current database is structured around one school installation. A multi-school SaaS mode needs explicit tenant boundaries, data isolation and per-school settings.
4. **Release and update identity.** Package names, application IDs, display labels, update metadata and installer branding still use GTMC identifiers. Rebranding must be coordinated across Android, Electron, server, PWA and installers.
5. **Centralized observability.** Add safe diagnostics, health checks, error reporting and sync monitoring without exposing candidate data or secrets.
6. **Build/release verification.** The import is not yet proven complete. Binary logo and any remaining assets must be recovered; automated tests and Android/Windows builds must pass before deployment.
7. **Commercial onboarding and licensing.** School activation, license validity, plan limits and controlled offline grace periods are not yet established.

## Recommended implementation sequence

1. Finish import and run baseline tests/builds without changing exam behavior or stored data.
2. Add backward-compatible role-based access control while retaining the existing admin login and existing databases.
3. Add persistent, configurable authentication throttling and stronger session controls.
4. Add tenant-safe school setup and activation/licensing only after choosing the hosting model.
5. Apply the VICORA brand consistently to all CBT clients.
6. Improve exam analytics, candidate performance reports and safe exports.
7. Complete automated release, update and recovery workflows.

## Preservation rules
- Existing question banks, students, exams, sessions, answers, marks, results and backups must remain intact.
- Database changes must be additive and migration-tested against a copy of an existing database.
- Never expose admin, pairing, device management, backup or sync-management endpoints through the public student gateway.
- Do not publish or deploy until the user approves the tested release.
