# GTMC Proctor Mode implementation status

## Implemented in this branch

- New exams can be assigned Proctor Mode: Off, Optional, or Required.
- Existing databases receive an additive `exams.camera_policy` migration with default `off`; existing exams do not unexpectedly request camera access.
- Required policy is enforced by the server-side `/api/student/begin` endpoint. A client cannot start a Required exam unless it reports a successful camera preflight.
- Browser students see a disclosure before camera permission is requested. Optional mode permits declining; Required mode blocks exam start when camera access is unavailable or denied.
- The browser reports camera start/stop/interruption and page visibility/fullscreen events to an authenticated endpoint.
- Event writes are idempotent per session and request ID.
- Admins can inspect event records and save a human review state and note.
- Camera event records are separate from answers and scores. Camera failure does not submit the exam or erase answers.

## Deliberate limitations of this first code increment

- No camera image or continuous video is uploaded or stored.
- Face counting, face absence, and head-direction detection are not implemented. The current release records browser/camera state events only; it must not claim to perform visual identity or gaze monitoring.
- A school-approved evidence retention duration and notice wording still need to be agreed before any image evidence is introduced.
- Android WebView camera permission bridging and Windows Electron camera permission handling are not yet implemented. This increment is for the browser/PWA student client.
- The browser camera API requires HTTPS outside localhost. Do not enable Required mode on a non-HTTPS remote address.

## Verification required

- Run GitHub Actions quality tests.
- Test Off, Optional and Required with synthetic candidates in Chrome Android, Safari iOS/iPadOS, and Chrome/Edge Windows.
- Confirm permission denial and camera disconnection do not lose answers or auto-submit.
- Review event access and retention controls before using real student records.

This is an implementation increment, not approval to enable camera monitoring in a live examination.
