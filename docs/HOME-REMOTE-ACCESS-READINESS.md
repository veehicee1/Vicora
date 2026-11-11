# GTMC Home Examination — Remote Access Readiness

## Purpose

This runbook prepares the existing GTMC CBT server for students connecting from home through the additional `/home/` browser/PWA route. It does not deploy the service, change server settings, or authorise public access.

## Current architecture

- The browser client is served by the existing Flask CBT application.
- Student authentication, exam sessions, papers, answers and submissions continue through the existing student API.
- The existing school SQLite database remains authoritative.
- The PWA service worker caches only the public app shell. Login and all `/api/` traffic remain network-only.
- This is not a second cloud database and is not fully offline home examination.
- Android, Windows Electron and school LAN entry points must remain available.

## Mandatory security design

Before any home access is enabled:

1. Keep the Flask application bound to loopback (`127.0.0.1`); do not expose its application port directly to the internet.
2. Place a trusted HTTPS reverse proxy or secure tunnel in front of it.
3. Configure the application with `CBT_TRUST_PROXY=1` and `CBT_REMOTE_STUDENT_ONLY=1`.
4. Keep secure cookies enabled and require HTTPS at the public edge.
5. Configure the proxy to overwrite/forward client-address headers safely. Do not trust client-supplied forwarded headers from direct LAN connections.
6. Confirm remote requests can reach only the home student page, public school information/logo and authenticated student API. Remote Admin pages and all non-student API routes must remain blocked.
7. Never publish the SQLite file, database port, backup directory, signing key, or server administration interface.
8. Apply firewall rules so the CBT application is reachable only through the local proxy/tunnel and approved school LAN paths.

The application intentionally refuses to start in remote-student-only mode unless trusted-proxy mode is enabled. Do not bypass that guard.

## Pre-deployment checklist

- [ ] Identify the server operating system and version.
- [ ] Identify the current CBT service start method and its environment-variable configuration location.
- [ ] Confirm the actual CBT listening address and port.
- [ ] Confirm the server has a current, verified backup; test restore only against a disposable copy.
- [ ] Select and approve a hostname and HTTPS certificate.
- [ ] Select a trusted reverse proxy or tunnel and document who controls its account and access.
- [ ] Restrict the public route to student-only mode.
- [ ] Confirm the proxy does not expose Admin routes, database files, backups or management ports.
- [ ] Confirm login cookies are Secure and HTTPS is enforced.
- [ ] Test with synthetic student accounts and sample examinations only.
- [ ] Verify Android, Windows desktop and school LAN workflows remain operational.
- [ ] Test reconnect/retry behaviour and verify a submission appears once in the central test database.
- [ ] Complete staged performance tests before any school-wide use.

## Required test cases

1. From an external network, `/home/` loads over HTTPS.
2. A valid test student can sign in, see assigned test exams, start/resume, save objective and theory answers, and submit.
3. A temporary network interruption does not silently lose pending answers; reconnect does not create duplicate submissions.
4. External requests to `/admin`, Admin APIs, and every non-student API route are denied.
5. School LAN users retain their existing approved workflows.
6. The service worker never caches login, exam papers, tokens, answers, messages or submissions.
7. A test submission is written to the one authoritative test database and is visible to the test Admin.
8. The server remains inaccessible directly from the public internet except through the approved HTTPS proxy/tunnel.

## Rollback

If any security or regression test fails:

- Disable the public proxy/tunnel route first.
- Leave the existing school LAN and Android/desktop configurations unchanged.
- Preserve logs and the test database for investigation.
- Do not restore or overwrite the live SQLite database as a troubleshooting shortcut.
- Re-enable remote access only after the failure is fixed and the full relevant test set passes.

## Information needed to produce exact server commands

The next implementation instructions depend on the server environment. Record:

- Operating system and version (for example, Windows Server or Ubuntu Linux).
- Whether the CBT server currently runs as a Windows service, scheduled task, terminal process, or Linux service.
- Whether the school already owns a domain/hostname and has an HTTPS proxy/tunnel.

Do not share passwords, API tokens, private keys, signing-key files, or database files in chat.
