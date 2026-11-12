# VICORA Multi-School Platform Architecture

## Product decision

VICORA is one centrally managed, multi-school examination platform. Schools register on one website, receive a unique School ID after approval, and use the same product through the cloud web host, Android host, or Windows host. Separate websites or separate codebases are not required for each school.

## School onboarding lifecycle

1. A school submits an application with its legal/display name, country, state, address, official contact details, proposed school administrator, and optional logo.
2. The application is stored as `pending`. It cannot create students, publish exams, or host a live examination.
3. A VICORA Platform Super Admin reviews the application and either requests changes, rejects it with a reason, or approves it.
4. Approval creates an immutable internal `school_id` and a human-friendly unique School Code. The code is an identifier, not a password.
5. The school administrator receives a secure account invitation and completes account activation and password setup.
6. The school configures its profile, classes, subjects, staff, students, question bank, examinations, and host devices.

A school name must never be used as the security boundary: names can be duplicated or changed. The immutable `school_id` is the tenant key. The School Code is used to locate the tenant before student sign-in.

## Tenant security boundary

Every school-owned record must be associated with a `school_id`, including:

- school administrators, staff and student accounts;
- classes, subjects, student registrations and access credentials;
- question banks, examinations, exam-class assignments and exam schedules;
- exam sessions, answers, submissions, theory marks, results and messages;
- proctoring events, audit events, school settings, uploads and logos;
- host-device registrations, sync receipts, sync outboxes and conflict records.

Every API must derive the active school from an authenticated account, validated host registration, or resolved School Code. It must not trust a client-supplied `school_id` without checking membership. Every read, write, export, backup, sync and file download must enforce the same tenant boundary on the server.

Platform Super Admins can review all schools. School administrators can manage only their own school. Other staff and students are limited to their own school and assigned permissions. Cross-school access must be denied even when a caller guesses another school's numeric ID, student registration number, exam ID, or sync UUID.

School-specific uniqueness must be enforced within a school, not globally. Examples include student registration number, class name, subject name, question identity, and exam code. Existing global SQLite UNIQUE constraints need a carefully tested table-rebuild migration; simply adding nullable `school_id` columns is not sufficient.

## Hosting model: cloud, Android and Windows

All three hosting modes are first-class VICORA hosts:

- **Cloud/Web:** the public VICORA site and central API serve browser-based candidates and school administrators.
- **Android:** the Android application can run a local examination server for a school's LAN and, when configured with secure public connectivity, remote candidates.
- **Windows:** the Windows application can run the equivalent local or securely exposed examination server.

Each host is registered to one approved school and receives a revocable host credential scoped to that school. A host must not switch tenants by changing a request parameter or local setting alone.

The central platform owns school approval, identity, account authority, and the canonical shared records. Android and Windows maintain local SQLite data for offline operation. They synchronize versioned records through authenticated APIs; they must not copy or merge raw SQLite database files. Sync must use stable IDs, revisions, idempotent attempt UUIDs, retry queues, tombstones for deletions, and an explicit conflict-review path. A host may conduct a pre-approved offline exam using its locally cached package and upload results when connectivity returns.

A local Android/Windows server is reachable on its LAN by default. Internet hosting requires a secure HTTPS gateway/tunnel or managed ingress, explicit host enrollment, and revocable credentials. Do not expose an unauthenticated raw device port to the public internet.

## Safe implementation sequence

This is deliberately staged because the current Flask/SQLite schema is single-school and contains global uniqueness constraints. Enabling school registration before tenant-scoping every endpoint would expose school data.

1. **Foundation and migration design:** document every school-owned table, existing unique constraint, account role, host credential and sync pathway. Define a backward-compatible migration that creates the first school from the existing installation's configured school name and maps all existing records to it without changing existing record IDs, passwords, attempts, answers, scores or history.
2. **Tenant-aware schema:** rebuild affected SQLite tables where required to make uniqueness school-scoped; add foreign keys and indexes; add school applications, school registry, school settings, host enrollment and platform/school role distinctions. Keep a tested rollback/backup path.
3. **Authorization and API scoping:** update every admin, student, export, report, upload, host and sync route. Add negative tests proving School A cannot read or modify School B data through IDs, codes, registration numbers, exports, sync payloads or file paths.
4. **Registration and approval:** add the public application flow and Platform Super Admin review/approval interface. Provision school administrator accounts only after approval.
5. **School selection and candidate sign-in:** update the web entry page to resolve School Code first, show the verified school identity, then authenticate the candidate using that school's registration number and exam access credential.
6. **Android and Windows host enrollment:** add school-scoped host pairing, school identity confirmation, local data migration, and tenant-aware package/result synchronization. Preserve offline hosting.
7. **Release gates:** run database migration tests against a copy of the existing GTMC database, cross-tenant security tests, web exam journey tests, Android and Windows builds, and LAN/offline/online sync tests. Do not deploy or migrate the live school database until these gates pass.

## Current implementation status — development PR #12

The following foundations are now implemented in the VICORA development branch and are undergoing CI validation:

- The existing installation is assigned a stable legacy school ID and School Code; the migration is designed to preserve existing student, score, exam and relationship IDs.
- Admin usernames, class names, subject names and student registration numbers are unique within a school rather than globally.
- Public school applications, Platform Super Admin approval, immutable School IDs, unique School Codes and expiring one-time school-admin activation credentials are implemented.
- Admin and student login resolve the School Code before credentials are checked. A School Code is an identifier, not a password.
- Tenant-aware SQLite connections route core school-table reads and writes through school-filtered views. Inserts are stamped with the active school, updates/deletes are restricted to that school, and cross-school foreign-key relationships are rejected.
- School settings use a composite school/key identity.
- Android and Windows Host setup accept the approved School Code. Android-to-Windows pairing and sync requests are scoped to the paired school.
- School-scoped host enrollment, heartbeat and revocation APIs, a Platform Admin review page, and school onboarding pages are included.
- The Vercel gateway can target an HTTPS cloud API origin or the existing Cloudflare Access-protected host tunnel.

This is a development foundation, not a claim that every host type already uses the new host-enrollment token or that universal Web ↔ Android ↔ Windows synchronization is complete.

### Remaining work before multi-school production use

1. Integrate new host-enrollment credentials into Android and Windows clients, including secure storage and revocation handling.
2. Complete the universal versioned sync protocol for exam packages, roster changes, answer/result uploads, retry queues and conflict review across all three host types.
3. Complete per-school backup/restore and archive/export. Until then, cross-school database backup routes fail closed.
4. Rehearse migration against a verified copy of the existing GTMC database and compare record counts, IDs, scores, foreign keys and reports.
5. Complete negative tenant-isolation tests for every API, file/export path and background job.
6. Approve and configure the paid persistent web host, HTTPS domain and production gateway separately.

No paid hosting deployment, live database migration or production deployment has been performed.
