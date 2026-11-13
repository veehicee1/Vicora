# VICORA Fresh CBT Records Implementation

## Data decision

VICORA will start with new examination records. Existing CBT records are not imported, overwritten, or deleted by this change. Keep the old CBT system available separately until a deliberate export/import project is approved.

## New Apps Script database tabs

The non-destructive `initializeVicoraBackend()` setup now provisions these additional school-scoped tabs when next run:

- `Questions`: question text, options, correct answer, explanation, marks, difficulty, status, author and timestamps.
- `Exams`: exam settings, subject, duration, total marks, instructions, schedule, publication status and result visibility.
- `ExamQuestions`: ordered question-to-exam mapping and exam-specific marks.
- `ExamAssignments`: exam-to-class assignments.
- `ExamAudit`: examination management audit events.

Existing VICORA Central tabs are retained. Existing rows are not cleared. Missing headers are appended by the existing initializer.

## Important current limitation

This change creates the data structure only. It does not yet expose question/exam CRUD endpoints, publish candidate-safe exam snapshots, connect Firebase live attempts, or enable candidate login. Do not run a real examination yet.

## Implementation sequence

1. Provision and verify the new tabs in the dedicated VICORA Central database.
2. Add authenticated, school-scoped question and exam management API actions.
3. Connect the full examination admin interface to those APIs.
4. Implement the server-side Firebase custom-token broker and restrictive database rules.
5. Add candidate identity, exam assignment, autosave, reconnect, submission, monitoring and results.
6. Run security, recovery and load tests before any production examination.

## Security rules

- Every question and exam record must be scoped to the authenticated `school_id`.
- Correct answers and marking data must never be copied into candidate-readable Firebase paths.
- Candidate identity and role must come from trusted VICORA Central records, not browser-supplied claims.
- Firebase Realtime Database rules remain deny-all until the token broker and tested rules are complete.
- Do not store service-account credentials or session tokens in source control.
