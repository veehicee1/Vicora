# GTMC Android Remote Examination Host + Proctor Mode

## Decision and scope

The requested operating model is:

- An authorised administrator carries the GTMC Android Admin app and starts Remote Host Examination from that phone, wherever the administrator is located.
- Students at home use the browser/PWA at the approved HTTPS examination address. They do not need to install the GTMC app.
- The Android phone is the active examination host and its existing Android-host database is authoritative for that hosted examination.
- Proctor Mode is configured per examination by the administrator and is available to supported browser clients.
- Existing Windows Server hosting, Windows Electron clients, Android standalone mode, Android school-server mode, Android local Wi-Fi/hotspot hosting and the existing school database must remain available and unchanged unless a separate migration is explicitly approved.

This is a design and implementation plan only. It does not enable public access, change app code, move data, deploy a relay, or modify any live database.

## Important data ownership distinction

The current Android Host mode stores its own CBT data in the Android app's private data directory. It is a separate database from the Windows Server's cbt.db. Remote students connected to the Android host will therefore write to the Android host's database, not automatically to the Windows Server database.

Do not copy, merge or synchronise SQLite database files between the phone and Windows Server. If school-wide centralisation is later required, design a separate authenticated, transactional sync/API migration with stable IDs, conflict handling, backups and explicit approval.

## Proposed connection architecture

1. The Android app starts the existing embedded Flask server using the Android Host database.
2. A secure outbound tunnel agent on the Android device establishes an authenticated, encrypted, persistent connection to an approved public HTTPS relay/gateway. The phone must not require an inbound public IP and must not expose port 8765 directly to the internet.
3. Students open the approved HTTPS URL in Chrome, Edge, Safari or another supported browser. The gateway forwards only the student home-exam routes and student API to the Android host.
4. Admin routes, host-management routes, database files, backups, diagnostics containing secrets and server control endpoints are never exposed through the student gateway.
5. The Android app shows tunnel state, public student URL, connected student count, host health, battery/network warnings and a clear Stop Hosting control.
6. If the tunnel or phone disconnects, students see a clear connection warning. Existing answer retry logic is retained; final submission must not be acknowledged until the host confirms it.

### Tunnel and Android lifecycle requirements

- Select and approve a tunnel/relay provider before implementation; do not assume the school Windows Server is publicly reachable.
- The phone initiates outbound connections only. Use authenticated device identity, short-lived credentials, TLS validation and revocation.
- Run hosting under an Android foreground service with a persistent notification while an exam is active. Request battery-optimisation exemption only with an explanation and user consent.
- Handle Android Doze, app process death, network changes, Wi-Fi/mobile-data handover, low battery, loss of signal and reboot. Hosting must show Stopped/Interrupted if it cannot guarantee service; it must not silently claim to be online.
- Do not promise uninterrupted hosting if the phone loses power, mobile data or network coverage.
- Keep the Flask listener private to the device/tunnel bridge. Never expose TCP 8765 or SQLite to the public internet.
- The public gateway must enforce HTTPS and student-only routing. No public remote Admin API is included in this scope.

## Proctor Mode

### Per-exam administrator policy

Each examination has one of three policies:

- Off: no camera permission prompt, camera capture or proctor evidence.
- Optional: students may enable the camera or continue without it; the choice is recorded.
- Required: the student must grant camera permission and pass the camera preflight before starting.

The policy is saved with the examination and enforced by the host API, not merely by hiding/showing browser controls.

### Student browser experience

- Display a clear notice explaining what is monitored, why, who can review evidence and the retention period before requesting camera access.
- Use the front camera on phones where available and a selectable webcam on computers.
- Use HTTPS and explicit browser permission.
- Calibrate at the start; tolerate ordinary reading, writing and looking at working paper.
- Record defined events only: no face visible for a sustained interval, multiple faces, camera blocked/disconnected, permission revoked, browser backgrounded, or sustained head-direction change after calibration.
- A camera interruption is an event, not an automatic exam failure or cheating verdict. Apply an administrator-configured grace/recovery policy.
- Preserve and submit answers independently of camera status.
- Do not upload or retain continuous video by default. Use on-device detection and only upload compressed still evidence for explicitly configured event types.

### Administrator proctor dashboard on Android

During hosting, show each active attempt with:
- Student identity and exam/attempt state.
- Connection and last-heartbeat state.
- Camera permission/preflight state.
- Event count and latest event timestamp.
- Evidence review state: Unreviewed, Reviewed - no concern, or Needs follow-up.

Authorised Admin users can open private evidence, add a review outcome and record notes. Every evidence view, download, review and deletion is audited. Do not expose evidence to students or other students' sessions.

### Evidence protection

- Keep evidence outside public static directories and outside ordinary exam answer tables.
- Store random evidence IDs and references in the database, not image blobs in exam tables.
- Validate authenticated attempt, exam policy, MIME type, image dimensions, file size and idempotency key server-side.
- Apply a school-approved retention period and deletion workflow.
- Require access checks for every evidence view and audit access.
- No automated disciplinary decision, cheating label or auto-submission based solely on camera events.

## Android host capacity and reliability

The Android phone is both the application server and the database host. This is not equivalent to a dedicated Windows Server. Before school-wide use:
- Benchmark a representative Android device on real mobile/Wi-Fi networks.
- Run staged tests with 1, 5, 10, 20 and then higher concurrent synthetic student sessions.
- Measure CPU, memory, temperature, battery drain, storage, request latency, reconnects and answer-write durability.
- Do not assume the phone can serve 50 simultaneous candidates until a measured test proves it.
- Keep an automatic local backup before hosting and after completed exams; verify restore using a disposable copy.
- Display a clear warning if available storage, battery or thermal state is unsafe.

## Compatibility and regression rules

- Keep the existing /home/ browser/PWA route and Android student app.
- Keep the existing Windows Server and Windows Electron workflows.
- Keep Android Standalone, School Server and local Wi-Fi/Hotspot Host modes.
- Keep the existing exam timer, attempt/session validation, question delivery, objective/theory saving, scoring and final submission behavior.
- The service worker may cache only the public app shell. It must never cache API responses, credentials, exam papers, tokens, answers, proctor events or evidence.
- Test Chrome on Android, Safari on iPhone/iPad, and Chrome/Edge on Windows.
- Use synthetic students, synthetic exams and test evidence only.

## Implementation sequence

1. Inspect current Android Host UI, embedded Flask server lifecycle, Android manifest/service configuration, /home/ route guards and existing camera-policy API design.
2. Implement a feature-flagged Android foreground host service and private tunnel bridge; add status/health UI. No public URL until security tests pass.
3. Add remote student-only gateway routing, authentication, rate limits, session protections and security tests. Keep all Admin and management routes private.
4. Add exam-level camera policy persistence and Admin controls, defaulting all existing exams to Off.
5. Add browser camera preflight, event contract, private evidence storage, Admin review UI and audit trail.
6. Add Android host dashboard and lifecycle/network interruption handling.
7. Run security, privacy, data-integrity, cross-browser and staged load tests.
8. Produce a signed test APK and test deployment instructions. Do not publish a public release or enable live student access without explicit approval.

## Release acceptance gates

- No direct public access to Android port 8765, database or Admin routes.
- Remote students can reach only the intended student website/API through HTTPS.
- Host disconnect/reconnect does not lose acknowledged answers or create duplicate submissions.
- Existing Android and Windows workflows pass regression tests.
- Camera Off requests no permission; Optional permits declining; Required blocks start until preflight succeeds.
- Camera interruptions do not erase answers or automatically penalise students.
- Evidence is private, audited, size-limited and deleted according to the approved retention policy.
- Device capacity is demonstrated under staged load before any 50-student or larger use.
- All tests use non-production data until explicit approval.
