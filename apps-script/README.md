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

The first setup step adds these school-scoped tabs: `Exams`, `Questions`, `ExamSessions`, `ExamAnswers`, `ExamResults`, `ExamEvents`, `StudentSessions` and `Messages`. The `Students` tab also gains `access_code` and `created_at` columns. Existing student rows are not deleted or rewritten. The `initializeVicoraBackend` function must be run again manually after deploying this code to create the new tabs/columns. The current student and administrator screens still call the existing Flask API; this schema addition alone does not connect those screens to Apps Script. The next implementation step is the authenticated Apps Script exam API and a controlled gateway adapter, followed by a small pilot test.

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
