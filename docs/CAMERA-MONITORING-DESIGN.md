# GTMC CBT Camera Monitoring Design

## Goal
Provide one administrator-controlled camera policy per examination across the existing Android Examination app, Windows Electron Examination client and the new browser/PWA student client. Camera monitoring is an exam integrity aid, not an automated cheating verdict.

## Administrator policy
Each exam will support:
- **Off** — camera is not requested and no camera evidence is collected.
- **Optional** — the student is invited to enable the camera; declining is recorded as a choice and does not prevent starting.
- **Required** — the student must grant camera permission and pass a camera preflight before the exam can begin.

The selected policy is saved with the exam and returned by the student exam-list API. It must be enforced by the server, not only hidden or shown by the client.

## Capture and detection
- Request camera access only after showing a clear notice describing what is captured, why, who can review it and how long evidence is retained.
- Use the front-facing camera on mobile where available; allow a suitable camera choice on laptops.
- Prefer on-device face landmark processing. Do not stream or record continuous video by default.
- Detect only defined events such as no face visible, multiple faces, camera blocked, camera disconnected, or a sustained head-direction change from the student's calibrated forward position.
- Use a short calibration period at the start. Apply a configurable tolerance and minimum event duration to reduce false alerts from normal movement.
- Capture a compressed still image only for configured evidence moments (for example, a sustained head-direction event and periodic audit sample). Do not upload continuous video.
- Record timestamps, event type, camera state and client/device metadata. The server timestamp is authoritative.
- If a model cannot load or the device cannot run detection, report monitoring unavailable. Do not silently claim the student was monitored.

## Student experience and failure handling
- Off: no camera prompt or camera access.
- Optional: show a clear Enable camera / Continue without camera choice.
- Required: block exam start until permission is granted and camera preflight succeeds. Explain how to enable permission if denied.
- If the camera is covered, disconnected, permission is revoked or the browser backgrounds the page, record an event and notify the student. Do not automatically submit or mark the student as cheating.
- Admin policy should define whether a temporary camera interruption pauses the exam or allows a short recovery grace period. This must be explicit before release.
- Save ordinary exam answers independently of camera status. A camera failure must never erase answers.

## Evidence storage and review
- Do not store image blobs in the SQLite exam tables.
- Store compressed evidence in a private evidence directory or approved private object storage, with random identifiers and strict access checks.
- Store only the evidence reference, session ID, event type, server timestamp and review status in the database.
- Only authorised Admin users can view evidence. Students cannot access another student's evidence.
- Provide a configurable retention period and a deletion process. Evidence must not be exposed through public static file routes or ordinary backups without an approved retention policy.
- Admin review states: Unreviewed, Reviewed - no concern, Needs follow-up. No automatic disciplinary action.
- Audit every evidence view, download, review and deletion.

## Platform requirements
### Browser/PWA (Windows, Android browser, iPhone/iPad Safari)
- HTTPS is mandatory for camera access outside localhost.
- Use `navigator.mediaDevices.getUserMedia` and handle permission denial, camera absence, device switching and browser suspension.
- Test Safari on iOS/iPadOS separately. Backgrounding may suspend camera capture; this is a recorded interruption, not proof of misconduct.
- The service worker must never cache camera evidence, camera streams, tokens or authenticated API responses.

### Android application
- Add Android CAMERA manifest permission and a runtime permission explanation/request.
- Handle WebView `onPermissionRequest` safely; grant only video capture after Android permission has been granted.
- Keep camera permission disabled/unrequested when exam policy is Off.
- Test both Admin and Examination APK flavours, including standalone and school-server modes.

### Windows Electron application
- Add an explicit permission handler for the trusted local CBT origin only.
- Do not grant camera access to arbitrary remote origins or pop-up windows.
- Test laptop webcams and thin-client/RDP camera redirection separately; RDP camera availability is not guaranteed.

## Server and API requirements
- Add an additive `camera_policy` exam column with default `off`; existing exams remain unaffected.
- Add authenticated student camera-event upload and Admin-only evidence review endpoints.
- Validate the active session, exam policy, event type, image MIME type, image dimensions and upload size server-side.
- Use request IDs/idempotency keys so retries do not create duplicate events.
- Keep camera evidence separate from answer submission and scoring.
- Never trust client timestamps or client-supplied student/exam IDs without checking the authenticated session.

## Release and load-test gates
1. Existing exam workflows pass with camera policy Off and no camera permission prompt.
2. Optional and Required policies work on all supported clients.
3. Permission denial, camera removal, browser backgrounding and network loss are handled without answer loss.
4. Evidence is private and accessible only to authorised Admin users; audit and retention tests pass.
5. False-positive head-turn detection is evaluated with ordinary reading, writing, looking at working paper and brief natural movement.
6. CPU, memory, network and evidence-storage impact are measured with staged 1/10/20/30/50-user tests. Do not enable face-landmark processing school-wide until measured.
7. No camera stream is continuously uploaded or stored by default.
8. Use synthetic student data and test evidence only until explicit school approval.

## Implementation order
1. Add the exam policy field and Admin controls (default Off).
2. Add shared API event contract and private evidence storage/review.
3. Implement browser/PWA camera preflight and event capture.
4. Implement Android runtime permission/WebView camera bridge.
5. Implement Electron camera permission handling.
6. Add on-device face landmark detection and sustained head-direction event capture after device-performance tests.
7. Run privacy, compatibility, regression and 50-session load tests before enabling Required policy.
