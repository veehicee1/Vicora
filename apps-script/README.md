# VICORA Google Apps Script backend

This folder contains the VICORA central school-management service. It is a separate Google Apps Script project and does not modify or connect to GTMC's existing Apps Script projects.

## Responsibilities

- Public school applications.
- Platform administrator approval/rejection.
- School provisioning and unique `VIC-XXXXXXXX` School Codes.
- One-time school administrator activation.
- School Code + email/password sign-in.
- School-scoped users, classes, subjects and student registry.
- Android/Windows host enrollment, heartbeat and revocation.
- Idempotent host synchronisation event intake and pull.
- Audit trail and Google Drive storage-folder provisioning.

The Apps Script project now provisions the first CBT pilot data tabs alongside the central school-management tabs. These tabs are schema preparation only: the student/exam API actions and the existing generated screen integration are not yet connected. The existing Flask application remains the active examination engine until that integration is implemented and tested. Do not treat the pilot tabs as production-ready for simultaneous candidates.

## Create the Apps Script project

1. Sign in to the Google account that should own VICORA's central records.
2. Open [Google Apps Script](https://script.google.com/) and create a standalone project named **VICORA Central Backend**.
3. Replace the default script contents with `Code.gs` from this folder.
4. Add the `appsscript.json` manifest from this folder (enable **Show "appsscript.json" manifest file** in Project Settings).
5. In **Project Settings → Script Properties**, add:
   - `VICORA_PLATFORM_ADMIN_KEY` = a long, randomly generated secret (at least 32 random characters).
6. Run `initializeVicoraBackend` manually once and approve the Google Sheets and Drive permissions. It creates or extends a dedicated spreadsheet called **VICORA Central Database**, its required school-management and CBT pilot tabs, and a **VICORA School Storage** Drive folder. Existing tabs and records are preserved; missing columns are appended. It does not access GTMC spreadsheets.
7. Deploy → New deployment → Web app:
   - Execute as: **Me**
   - Who has access: **Anyone**
8. Copy the Web App URL. Do not publish the admin key or paste it into browser-side JavaScript.

No deployment, Google account changes, spreadsheet creation or permission grant is performed by this repository change.

## API contract

All POST calls send JSON with an `action` field. The web app returns JSON.

### Public endpoints

- GET `?action=health`
- GET `?action=resolveSchool&code=VIC-XXXXXXXX`
- POST `{"action":"applySchool","schoolName":"...","contactName":"...","contactEmail":"...","contactPhone":"...","schoolType":"Secondary","country":"Nigeria","state":"...","address":"..."}`
- POST `{"action":"activateSchool","activationToken":"...","email":"...","password":"at-least-12-characters"}`
- POST `{"action":"login","schoolCode":"VIC-XXXXXXXX","email":"...","password":"..."}`

### Platform administrator endpoints

These require `adminKey` in the POST body. Keep this key on a trusted server, never in a public web page or mobile app.

- `admin.listApplications`
- `admin.decideApplication` with `applicationId`, `decision` (`approve` or `reject`) and optional `note`.
- `admin.listSchools`

Approval creates a school, a pending school administrator and a one-time activation token. The service attempts to email the School Code and activation token. The admin response also returns the token so a trusted server-side admin console can deliver it securely if email delivery is unavailable. Treat it as a secret.

### Authenticated school endpoints

After login, pass the returned `sessionToken`:

- `account.create` — school admin creates teacher/exam-officer/viewer accounts.
- `class.save`
- `subject.save`
- `student.save`
- `school.profile`
- `host.enroll`
- `host.revoke`
- `logout`

Host endpoints use the `deviceId` and one-time `deviceToken` returned by `host.enroll`:

- `host.heartbeat`
- `sync.push` — up to 100 events per request; event IDs are idempotency keys.
- `sync.pull` — returns up to 200 school-scoped events after a timestamp cursor.

## CBT pilot status

The first setup step adds these school-scoped tabs: `Exams`, `Questions`, `ExamSessions`, `ExamAnswers`, `ExamResults`, `ExamEvents`, `StudentSessions` and `Messages`. The `Students` tab also gains `access_code` and `created_at` columns. Existing student rows are not deleted or rewritten.

The Apps Script pilot now includes authenticated, school-scoped exam authoring actions: `exam.list`, `exam.save`, `exam.publish`, `question.list` and `question.save`. Only school administrators, owners and exam officers can create or publish exams/questions; viewers can list them. The first pilot supports objective multiple-choice questions only. Exams must have the configured number of active questions before they can be published. Published exams and their questions are locked against edits through these actions.

**This is authoring-only at this stage.** The existing generated student and administrator screens still call the Flask API, and student login, paper delivery, answer saving, submission and results remain on Flask. Do not switch live candidates to Apps Script yet. The next stage is to add student pilot endpoints, then a controlled server-side adapter and end-to-end test using a small number of test accounts. Keep Flask available as the fallback throughout.

## Important integration and operational notes

- Apps Script web apps execute under the deploying Google account and are subject to Apps Script quotas, execution limits and Sheets concurrency limits.
- This is suitable for registration, school administration and modest metadata sync—not a high-concurrency CBT answer database.
- The browser UI should call Apps Script through a trusted server-side proxy/API route. Do not put the platform admin key in Vercel frontend code. A browser-to-Apps-Script direct fetch may encounter cross-origin/redirect restrictions.
- The existing Flask/SQLite tenant database and this Sheets database are separate stores until an explicit integration adapter and reconciliation policy are implemented. This change does not migrate or copy GTMC or VICORA records.
- Google Sheets is not a transactional relational database. For large schools or high-volume sync, move the central data layer to a managed database later while retaining Apps Script for Google Workspace automation.
- Do not treat the returned temporary account password as a permanent credential. Require a password-change flow before wider school rollout.
- Use a dedicated Google account owned/controlled by the VICORA organisation, enable two-step verification, and restrict editor access to trusted administrators.
- Backups and retention policies must be configured for the Google Drive folder and spreadsheet. A folder is provisioned; automated backup scheduling is not yet enabled.
- This repository change does not deploy the web app or activate any Google service.

## Security boundaries

Passwords are salted and SHA-256 hashed; session and device tokens are stored as SHA-256 hashes. School-owned records are filtered by the authenticated school ID. Platform administration uses a secret stored in Script Properties. HTTPS is provided by Google's Apps Script web app endpoint.

Before public launch, complete the separate Vercel/server-side proxy integration, add abuse throttling and stronger password hashing/rotation, implement password reset and account recovery, review all endpoint permissions, and establish backup/restore procedures. Apps Script's public endpoint and spreadsheet quotas must be considered in capacity planning.


## CBT roster connection (v1.3.0)

The existing Flask CBT engine remains authoritative for examination delivery and records:
- question bank, including objective and theory questions;
- exam scheduling, class assignment, timing and candidate attempts;
- answer saving, proctor events, automatic objective marking and manual theory marking;
- submissions, results, reporting and existing invigilator controls.

When a school administrator signs in through the central VICORA login route, the Flask server requests the authenticated `school.profile` from Apps Script and imports that school's active classes, subjects and students into that school's existing tenant-scoped CBT database. Student access codes are generated by Apps Script when a new central student record is saved and are included in the server-to-server roster sync. Existing local exams, questions, attempts, answers, scores and reports are not rewritten by roster sync.

After adding or changing central roster records while already signed in, sign out and sign in again to refresh the local CBT roster. Duplicate admission numbers that already belong to another local record are skipped rather than overwritten.

The Apps Script exam/question authoring API remains a pilot API and is not a replacement for the complete Flask exam management interface. The Apps Script CBT tabs are not yet the authoritative store for candidate attempts or answers. Do not describe this as a fully migrated or production load-tested Apps Script exam engine.

Deployment note: update the Apps Script project with the current `apps-script/Code.gs`, save, then create a new Web App deployment version only after the source is reviewed. The Flask server must also be updated with the matching `central_backend.py` from this branch and configured with the existing server-side central Apps Script URL. Never expose the platform admin key or central session token in browser code.
