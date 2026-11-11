# VICORA CBT Staff Roles and Access Design

## Goal
Introduce separate staff access levels without breaking the existing administrator login or changing examination records.

## Roles

| Role | Main responsibility | Access |
|---|---|---|
| Super Admin | Owns and configures the CBT installation | All CBT settings, staff accounts, devices, exams, results, backups and audit records |
| Exam Administrator | Prepares and manages examinations | Students, classes, subjects, question bank, exam creation/scheduling, monitoring and results |
| Invigilator | Supervises live examinations | Live exam monitor, candidate session actions, approved time extensions, proctor alerts and candidate messaging |
| Examiner / Marker | Marks written responses | Assigned theory responses, marking, moderation view and approved result reports |
| Auditor | Reviews activity and performance | Read-only dashboards, audit trail and approved result/export views |
| Student | Takes assigned examinations | Own login, assigned exam, own answers, inbox and published grades only |

## Backward compatibility
- Existing administrator accounts are migrated additively as **Super Admin**.
- Existing passwords and login names remain unchanged.
- Existing student registration numbers and access codes remain unchanged.
- Existing question banks, exam papers, sessions, answers, marks, results and backups remain unchanged.
- No user is silently downgraded or locked out during migration.

## Permission boundaries
- Staff account creation, role changes, deactivation, system settings, device pairing/revocation and backup restore are Super Admin only.
- Exam Administrators can manage exam content and schedules but cannot change system ownership or restore backups.
- Invigilators can supervise live sessions but cannot view or edit the question-bank answer key.
- Examiners can mark written responses only for examinations explicitly assigned by a Super Admin; their examination list and result reports are limited to those assignments. They cannot alter student access codes or exam schedules.
- Auditors are read-only.
- Students cannot access any staff API, other candidates' records, answer keys or unpublished results.

## Implementation safeguards
1. Add role and active-status columns to the existing admin table; do not replace it.
2. Enforce permissions in Flask API decorators, not only by hiding buttons in the browser.
3. Return the signed-in staff role from the existing session endpoint.
4. Add staff-account management endpoints restricted to Super Admin.
5. Hide or disable unauthorized controls in the admin interface after backend enforcement is tested.
6. Add regression tests for every role and sensitive endpoint.
7. Test the migration against a copy of an existing CBT database before using it with real data.

## Implementation status

The initial role system is implemented in `app.py` and `web/admin.html`. The `staff_exam_assignments` table stores examiner-to-examination assignments. Staff management is available in the Super Admin dashboard, including staff password resets. Backend permission checks and role regression tests are in place. GitHub Actions quality checks passed with 56 tests on the initial implementation commit; manual browser checks and real-database migration testing remain outstanding.

## Not included in this increment
- Student accounts are not converted into staff accounts.
- No teacher/parent portal or general school-management roles are introduced.
- No multi-school SaaS tenancy is introduced in the same migration.
