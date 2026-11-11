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

## Outstanding before build verification
1. Import the original binary `gtmc-logo.jpg` asset. It is referenced by the server and Android asset-copy task; it was not possible to add it using the text-file upload route.
2. Check the source repository for any additional Android resources and static assets not yet recovered.
3. Confirm all Windows/Electron and Android source dependencies are present.
4. Run Python regression tests, JavaScript syntax checks, and Android debug build.
5. Only after successful checks, begin VICORA-specific branding and feature changes.

## Important status
This is a partial source import, not a verified complete application. Keep this branch separate from `main` until all missing files are recovered and builds/tests pass. Do not deploy from this branch.
