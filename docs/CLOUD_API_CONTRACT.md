# GTMC CBT Cloud API Contract (Prototype)

## Status and safety boundary

This document defines the first API contract only. It does not connect to Google, deploy an Apps Script project, alter the local SQLite database, or upload school/student data. All prototype tests must use synthetic records.

The local Flask/SQLite API remains authoritative for Standalone Offline and School Wi-Fi/Hotspot modes. Cloud mode is an additional connection, not a replacement.

## Deployment shape

- HTTPS Google Apps Script web app as the prototype API.
- Google Sheets as a modest-volume prototype store, with a separate private Google Drive backup process planned independently.
- One configured school initially: GTMC. Every cloud record is scoped to a server-validated `school_id`; clients cannot select another school merely by changing a request field.
- Keep API versioned at `/v1` in the action names so the storage implementation can later move to a transactional database without changing the client contract.

## Request envelope

All authenticated POST actions use JSON:

```json
{
  "api_version": "v1",
  "action": "sync.push",
  "request_id": "client-generated-uuid",
  "device_id": "stable-installation-uuid",
  "payload": {}
}
```

Authentication is supplied in an Authorization bearer token by the eventual HTTPS client. Tokens are short-lived, revocable, and scoped to a school, user, role, and permitted actions. Secrets and signing keys belong in Apps Script Properties, never in source control or the Android/web bundle.

The server derives `school_id`, user identity, and role from the validated token. It must not trust those values from the request payload.

## Standard response

```json
{
  "ok": true,
  "request_id": "same-request-uuid",
  "server_time": "ISO-8601 timestamp",
  "data": {},
  "error": null
}
```

Errors use `ok:false` and a stable code such as `AUTH_REQUIRED`, `FORBIDDEN`, `VALIDATION_ERROR`, `REVISION_CONFLICT`, `DUPLICATE_REQUEST`, or `TEMPORARY_UNAVAILABLE`. Do not return stack traces, password hashes, tokens, or internal sheet details.

## Initial action contract

| Action | Role | Purpose |
|---|---|---|
| `auth.login` | admin/teacher/student | Exchange credentials for a short-lived scoped token; exact credential verifier is a security design gate before implementation |
| `auth.refresh` | authenticated user | Rotate/refresh a valid session under server policy |
| `sync.pull` | admin/teacher | Fetch permitted changes after a server cursor |
| `sync.push` | admin/teacher | Submit a batch of permitted record changes |
| `exams.listPublished` | student | List published practice and assigned exams visible to this student |
| `attempt.start` | student | Create or resume the one authoritative attempt for the student and exam |
| `attempt.saveAnswers` | student | Idempotently save answer changes for the authoritative attempt |
| `attempt.submit` | student | Finalise the attempt exactly once and return the recorded result |
| `admin.syncStatus` | admin | Read last successful sync and pending/conflict counts |

## Record envelope and conflict rules

Cloud records use stable UUIDs independent of existing SQLite integer IDs:

```json
{
  "entity": "student",
  "record_uuid": "uuid",
  "local_id": 123,
  "base_revision": 4,
  "client_updated_at": "ISO-8601 timestamp",
  "operation": "upsert",
  "fields": {}
}
```

- Keep all existing SQLite integer IDs and foreign keys unchanged locally.
- Add a local UUID mapping/migration non-destructively before any production sync.
- The server assigns the next revision. A write with a stale `base_revision` returns `REVISION_CONFLICT`; it never silently overwrites newer data.
- Every mutation has a unique idempotency/request key. Retrying the same key returns the original outcome and does not create duplicates.
- Apply records in dependency order: classes/subjects, students, questions, exams/assignments, attempts, answers/results.
- Deletions are tombstones with revisions, not immediate row removal.
- Audit actor, school, device, action, entity UUID, and server timestamp. Never log credentials or bearer tokens.

## Student exam integrity

- A student may only see published practice exams or exams assigned to their class/student account.
- The server creates or resumes one authoritative attempt per allowed student/exam policy. A second device must not create a second attempt accidentally.
- Answer writes are idempotent and ordered by server revision/sequence, not trusted client clock alone.
- The server enforces exam duration, availability window, submission state, and permitted attempt count.
- A final submission is immutable unless a separately authorised admin correction workflow is introduced.
- If connectivity drops, the client may queue encrypted/persisted answer updates locally and retry. The UI must clearly show unsynced answers; do not tell the student an answer is safely stored in the cloud until acknowledged.

## Data and access boundaries

- Do not copy the local `admins` table, password hashes, local session tokens, or device secrets into ordinary Sheets tabs.
- Authentication credential storage and token signing are separate from school content data. The credential-verification method must be reviewed before a live deployment; never use plain-text passwords or a hard-coded shared secret in the app.
- Every query and write is scoped server-side to the token's school and role.
- Teachers can only read/write records permitted by their assigned classes/subjects. Students can only access their own profile, visible exams, attempt, answers, and results.
- Validate payload sizes, field types, allowed entity names, and role permissions on every request.
- Use a script lock around Sheets read-modify-write sections to reduce concurrent write races. Locks do not turn Sheets into a transactional database; load testing is required.

## Initial Sheets tabs (prototype only)

Suggested tabs: `Schools`, `CloudUsers`, `Classes`, `Subjects`, `Students`, `Questions`, `Exams`, `ExamClasses`, `Attempts`, `Answers`, `ChangeLog`, and `Idempotency`.

Each content row carries `school_id`, `record_uuid`, `revision`, `updated_at`, and `deleted_at` where applicable. Keep credential verifier data in a separately restricted store, not in the ordinary content tabs. Do not create or populate these tabs in the user's Google account until deployment and access controls are explicitly approved.

## Build and test gates

1. Implement a standalone Apps Script prototype with synthetic data and a local/mock test harness.
2. Review authentication, token expiry/revocation, role checks, school isolation, input validation, and request replay protection.
3. Test duplicate requests, concurrent edits, stale revisions, offline retry, and cross-school denial.
4. Only after those tests pass, connect one disposable test client. No production SQLite import.
5. Add real local-to-cloud mapping and foundational-record sync in a separate reviewed change.
6. Implement Drive snapshot backup/restore independently; do not treat Sheets as a backup.
7. Do not deploy, change the live app, merge implementation PRs, or use real student data without explicit approval.
