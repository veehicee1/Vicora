# VICORA tenant schema and isolation inventory

Status: implementation checklist for the staged multi-school migration. This file describes the current schema and the required target behaviour; it does not claim tenant isolation is already active.

## Current globally unique constraints

The current SQLite schema contains these constraints that must be reviewed before multiple schools share one database:

| Table | Current constraint | Target treatment |
|---|---|---|
| admins | UNIQUE(username) | Rebuild as UNIQUE(school_id, username) |
| classes | UNIQUE(name) | Rebuild as UNIQUE(school_id, name) |
| subjects | UNIQUE(name) | Rebuild as UNIQUE(school_id, name) |
| students | UNIQUE(reg_no) | Rebuild as UNIQUE(school_id, reg_no) |
| questions | UNIQUE(subject_id, text) | Keep scoped through a subject that belongs to exactly one school; add explicit school consistency checks |
| sessions | UNIQUE(exam_id, student_id) | Keep; both parent records must belong to the same authenticated school |
| proctor_events | UNIQUE(session_id, request_id) | Keep; scope through the parent session |
| classes, subjects, students, questions, exams | unique sync_uuid indexes | Keep globally unique stable UUIDs |
| sessions | unique attempt_uuid index | Keep globally unique for idempotent cross-device result delivery |
| android_host_devices | device_id primary key | Keep globally unique device UUID; bind each device to one school |
| android_sync_receipts / conflicts / outbox | attempt_uuid unique | Keep globally unique to prevent cross-device duplicate processing |

Do not simply add school_id and leave username, class, subject, and registration-number uniqueness global: that would prevent two schools from using ordinary local identifiers.

## Tenant-owned records

The first migration adds school_id to core entities: admins, classes, subjects, students, questions, exams, sessions, messages, answers, theory marks, proctor events, host devices, sync records, and audit records.

Relationship tables remain unchanged in the compatibility migration because their ownership is inherited through their parent relationships:
- exam_classes -> exam_id and class_id
- session_questions -> session_id
- staff_exam_assignments -> staff_id and exam_id

Every relationship must be validated so that all referenced parents belong to the same school. A client-supplied ID must never be sufficient to cross a school boundary.

## Authentication and request scope

1. Platform Super Admin is a platform-level identity and may manage school applications and approvals.
2. School staff login resolves to one active admin row and its school_id. The server stores the resolved school_id in the signed session.
3. Student login must resolve a School Code first, then match registration number and access code inside that school.
4. School Code is an identifier, never a password or authorization token.
5. Never accept school_id from a request body as proof of tenant membership. If it is supplied, compare it to the authenticated principal and reject mismatches.
6. Android/Windows host pairing must be initiated by an authenticated school administrator. The resulting device credential is bound to that school_id and can be revoked.
7. Every list, detail, update, delete, export, backup, file, exam-package and sync query must include the authenticated school scope or prove it through a same-school parent join.

## Required negative tests

- School A cannot look up School B's student by guessed database ID, registration number, access code, or sync UUID.
- School A staff cannot read or modify School B's classes, subjects, questions, exams, sessions, messages, marks, audit entries, or host devices.
- School A cannot pair a device to School B by supplying a different school_id.
- Cross-school exam/class, exam/student, session/question, staff/exam and message/student relationships are rejected.
- Same username, class name, subject name and student registration number may be reused by different schools.
- Duplicate attempt UUIDs and sync UUIDs remain globally rejected.
- A backup/export generated for one school contains no other school's data.

## Safe migration sequence

1. Back up and inventory a copy of the existing GTMC database.
2. Apply the additive legacy-school assignment and verify row counts and foreign-key integrity.
3. Rebuild only the four tables that need school-scoped natural-key uniqueness (admins, classes, subjects, students), preserving IDs and every column. Do this in a transaction with foreign-key checks and rollback tests.
4. Add school binding to Android/Windows host credentials and sync payload validation.
5. Scope authentication and every school-owned API route; add the negative tests above.
6. Only then enable school applications, approval, School Code login and additional tenant creation.

The live GTMC database must not be migrated until the copy-based migration and all regression/security tests pass and the owner approves deployment.
