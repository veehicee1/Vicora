# GTMC Home Examination Website Package

## Delivery status
- Initial browser/PWA package is being added on a separate feature branch.
- It reuses the existing student examination page and student API; it does not replace the Android application or the existing school/LAN and Windows desktop clients.
- This increment adds a dedicated `/home/` entry point, install metadata, and a narrowly scoped service worker.
- This increment is **not** a public home-exam launch and does not create a cloud server, remote authentication gateway, or automatic cloud synchronisation.

## Student access packages
1. Existing Android Examination app — retained.
2. Existing school/LAN examination page — retained at `/` and `/exam`.
3. New browser/PWA package — `/home/`, intended for Windows laptops, Android browsers, iPhone Safari and iPad Safari.

The website is installable where the browser supports PWA installation, but installation is optional. The same responsive student client is used; no separate iPhone or Windows client is required.

## Current CBT integration
The existing Flask student API already provides credential login and assigned live-exam listing; exam start/resume with a server-issued session token; paper retrieval; objective/theory answer saving; heartbeat and submission; student inbox; and published grades.

The existing browser client already has a local pending-answer queue and retry logic for temporary connectivity loss. The PWA service worker deliberately does not cache or intercept any `/api/` request. It only caches the public app shell. It must never queue a final submission independently of the application's authenticated retry logic.

## Critical limitation before home examinations
The current API is backed by the local SQLite database. A student opening `/home/` from a phone or laptop can use it only when that browser can reach the same CBT server. The existing server must not be exposed directly to the public internet. The preferred first remote-access design is an HTTPS reverse proxy/tunnel to the existing Flask application, with the backend bound to loopback. This keeps one authoritative SQLite database and avoids a second cloud copy of each exam answer. It exposes an application API, never the database port or SQLite file.

For a public student-only hostname, enable both `CBT_TRUST_PROXY=1` and `CBT_REMOTE_STUDENT_ONLY=1`, keep `CBT_HOST=127.0.0.1`, and require HTTPS at the proxy. Student-only mode blocks remote access to Admin pages and every non-student API route while allowing the home page, public school info, logo and student API. Local loopback/LAN access remains available. The proxy/tunnel must be configured to forward the real client IP safely; never trust arbitrary forwarded headers from direct LAN clients.

A separately configured HTTPS reverse proxy or secure tunnel is required before real home use. It must forward browser requests to the existing Flask application while the Flask server remains bound to loopback. The student website then writes through the existing authenticated student API directly to the one authoritative school SQLite database. This is immediate central storage, not a second cloud copy or a file-level database sync.

The proxy must be paired with `CBT_TRUST_PROXY=1`, `CBT_HOST=127.0.0.1`, secure cookies, and `CBT_REMOTE_STUDENT_ONLY=1`. The new student-only guard blocks remote Admin pages and all non-student API routes. Only the home student page, public school information, logo and student API are exposed. Do not open the Flask port or SQLite database port to the internet. Do not enable remote Admin access as part of this work.

The separate `docs/CLOUD_SYNC_PLAN.md` concerns synchronising independent standalone copies and is not required for this home-website route. It remains a separate future project; any cross-device admin data synchronisation must use an authenticated API and a transactional store for high-concurrency use, not copy SQLite files.

## Camera monitoring
The cross-platform requirements and privacy safeguards are recorded in [CAMERA-MONITORING-DESIGN.md](CAMERA-MONITORING-DESIGN.md). Camera monitoring is a separate follow-on increment. Admin policy must be configurable per examination as Off, Optional or Required. Required monitoring must be enforced server-side, with clear consent and permission handling. Browser camera APIs require HTTPS (except localhost), explicit permission and compatibility testing. iOS Safari backgrounding, permission revocation and camera interruptions must be recorded as events, not treated as automatic proof of cheating. Human review is required.

## Safety and compatibility rules
- Do not change or remove Android standalone, Android school-server, Android hotspot hosting, Windows Electron, or school LAN workflows.
- Do not copy or merge SQLite database files between devices.
- Do not cache API responses, credentials, exam papers, answers, tokens or final submissions in the service worker.
- Do not claim offline login or fully offline home examination. Browser storage can be evicted, especially on mobile devices.
- Keep server-side time authoritative. A local timer is display-only.
- Never allow a retry to create a duplicate attempt or submission.
- Test Safari on iPhone/iPad, Chrome on Android, and Chrome/Edge on Windows before release.
- Use sample/test records only. No live server or school data changes.
- All work remains on this feature branch until reviewed. Do not merge or deploy without explicit approval.
- Do not enable public access until HTTPS proxy/tunnel, remote student-only mode, firewall rules and an approved hostname have been configured and tested.

## Acceptance gates
1. Existing Android and school/LAN smoke tests still pass.
2. `/home/` serves the same student experience without changing `/` or `/exam`.
3. Manifest and service worker are available under the `/home/` scope.
4. Service worker caches only the public shell; all API requests remain network-only.
5. Responsive layout is checked at phone, tablet and laptop widths.
6. Remote gateway, authentication, sync and camera monitoring are independently implemented and tested before home exams are enabled.
