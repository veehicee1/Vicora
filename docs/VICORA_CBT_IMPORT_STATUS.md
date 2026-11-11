# VICORA CBT Import Status

## Scope
This branch contains the CBT product only. School management, parent portal, general learning platform, and unrelated modules are outside this import.

## Source baseline
- Source repository: `sheggun1/CBT-GTMC`
- Source commit used for file retrieval: `05fd17e94bf494eef228d120711a2ffb5afca076`
- Destination repository: `veehicee1/Vicora`
- Destination branch: `feature/cbt-core-import`
- The source repository was not modified.
- Files were copied individually. Original Git commit history, branches, tags, and binary assets are not yet fully migrated.

## VICORA platform identity and school branding
- Added the VICORA wordmark and separate VICORA icon as the product's main platform identity.
- The admin sign-in and console use VICORA branding; the student sign-in and exam header also retain VICORA branding.
- Added an Admin Settings school-identity area where an administrator can set the school's display name and upload its logo.
- School logos accept PNG, JPEG, or WebP images up to 2 MB. The image is stored in the SQLite settings store so it is included in normal database backups.
- The selected school name and logo are shown in the student portal and school-facing admin areas. The public logo endpoint is explicitly allowlisted through the restricted Vercel student gateway; admin upload remains behind the authenticated admin API.
- This configuration is per CBT server/database installation. Shared multi-school tenancy in one database is not implemented.
- These changes are in `feature/cbt-core-import` only. No build, automated test, deployment, or production verification has yet been completed.

## Imported application components
- Flask/SQLite server: `app.py`
- Server dependencies: `requirements.txt`
- Admin and student browser clients: `web/admin.html`, `web/student.html`
- Home-exam PWA: `public/home/index.html`, service worker, manifest, icon
- Flask PWA support: `web/home-sw.js`, `web/home-manifest.webmanifest`, `web/home-icon.svg`
- Vercel configuration and student API gateway: `vercel.json`, `api/[...path].js`
- Windows Electron examination and admin clients and their package/build configuration
- Android app configuration, manifest, MainActivity, host pairing/service, sync worker/scheduler, update manager, and Python sync backend
- Backup restore, diagnostics, build scripts, installer definitions, and supporting workflows
- Existing automated tests and CBT technical documentation

## Safety changes
- Android workflow renamed for VICORA.
- Removed the workflow step that published APKs to the legacy `sheggun1/GTMC-CBT-Releases` repository.
- No release was published, no APK was built, and no production deployment was made.
- No secrets or signing keys were copied or exposed.

## Outstanding before release readiness
1. Recover the original binary `gtmc-logo.jpg` asset. It is referenced by the server and Android asset-copy task; it was not possible to add it using the text-file upload route. Its absence may leave the logo missing and must be resolved before release; compilation has not yet been tested.
2. Check the source repository for any additional Android resources and static assets not yet recovered.
3. Confirm all Windows/Electron and Android source dependencies are present.
4. Run Python regression tests, JavaScript syntax checks, and Android debug build.
5. Only after successful checks, begin VICORA-specific branding and feature changes.

## Important status
This is a partial source import, not a verified complete application. Keep this branch separate from `main` until all missing files are recovered and builds/tests pass. Do not deploy from this branch.

## Staff roles and permissions — initial implementation complete

Implemented in the development branch:

- Additive database migration adds `admins.role` and `admins.active`; existing administrator accounts are preserved and remain active Super Admins.
- Staff login/session responses include the assigned role; each protected request rechecks the account's current role and active status from the database.
- Backend allow-lists distinguish Super Admin, Exam Administrator, Invigilator, Examiner/Marker and Auditor. Unknown admin routes remain Super Admin-only for restricted roles.
- Invigilators can supervise live sessions and use approved pause/resume/extension actions, but cannot reset or force-submit candidate sessions.
- Super Admin-only staff endpoints support account creation, role changes and activation/deactivation. Passwords are hashed and never returned.
- The Admin Dashboard has role-aware navigation and a Staff Accounts screen.
- Examiner/Marker accounts can be assigned specific examinations. Their exam list, theory responses, marking actions and result reports are restricted to assigned examinations.
- Added regression coverage for role boundaries, examiner assignments, inactive accounts, staff creation and self-lockout prevention.
- Restored the JavaScript extraction helper required by the quality-check workflow and enabled that workflow on this development branch.

**Latest automated verification:** GitHub Actions quality checks passed on commit `7e9992fece1b9cb93287fa429ff8ecce28e46fd2`. The run completed JavaScript syntax validation, Python compilation and all **54 automated tests** successfully.

**Still outstanding:** manual browser testing of the staff screens, a migration test using a copy of an existing school database, and separate Windows/Android packaging verification against the latest RBAC changes. This remains a partial source import and development branch; it is not approved for production deployment.
