# GTMC Android Remote Host, Result Sync and Proctor Mode

## Implemented application flow

- Android Host continues to run the existing Flask CBT server and its existing private database.
- The Android Host pairs outbound to the Windows Server using the one-time Admin code and HTTPS.
- Only exams imported from the Windows Server host package are eligible for automatic sync; unrelated standalone Android exams and old local-only history are left alone.
- Submitted Android-local attempts from eligible exams are snapshotted into `android_sync_outbox`. The original session, answers, drawings, theory responses, score and history are not deleted or rewritten.
- WorkManager runs an immediate network-constrained batch after pairing, a periodic batch at the Android minimum interval (15 minutes), and a foreground-host pulse every 30 seconds. The Admin can also request an immediate sync.
- SQLite claim leases prevent immediate and periodic workers from uploading the same attempt concurrently; abandoned claims become eligible again after the lease expires.
- Each attempt retains its original UUID. The Windows Server returns an acknowledgement; only then is the local outbox row marked `synced`.
- Network/server failures remain queued with exponential retry. HTTP 409/413 and other permanent validation errors are marked `conflict`; authentication failures are marked `auth_error` and requeued only after successful re-pairing.
- The host package carries a canonical exam revision fingerprint. The phone checks that the imported exam has not changed locally, and the Windows Server independently checks that its current exam still matches that fingerprint before accepting any attempt.
- The Windows Server validates device pairing, exam/candidate identity and question identities, rejects duplicate/conflicting attempts, and recomputes objective/automatic scores with its existing marking function. Theory responses and drawings are transferred for the existing teacher-marking workflow.
- Android hosting runs under a foreground notification. This improves process survival but cannot protect against force-stop, battery exhaustion, device shutdown, overheating, or loss of mobile connectivity.

## Remote home access: deployment prerequisite

The phone's built-in host is a private HTTP listener for local Wi-Fi/hotspot use. **Do not forward TCP 8765 directly to the public internet.** Home access requires an approved reverse HTTPS gateway/tunnel that:
1. terminates trusted HTTPS for the student browser (camera APIs require a secure browser context);
2. forwards only the student web shell and `/api/student/*`, `/api/public/info`, and required static assets to the Android Host;
3. never forwards `/admin`, `/api/admin/*`, backups, pairing, device-management, or database routes;
4. has an explicit school-controlled access policy, rate limits, logging, and a revocation procedure;
5. supports a stable origin and WebSocket/streaming behaviour if later required.

The Android app does not create a public tunnel, change router settings, or publish a URL. The school must choose and configure its gateway provider and credentials. Until then, Android-hosted exams are available only to devices on the same Wi-Fi/hotspot. The separate Windows Server `/home/` route remains a different hosting path and must not be described as an Android-hosted exam.

## Proctor Mode

The student browser already implements the exam-level `off`, `optional`, and `required` camera policies and records camera/browser interruption events. Camera images and continuous video are not uploaded by this implementation. Camera permission requires HTTPS in supported browsers; on a plain HTTP phone hotspot address, required camera preflight may fail. Use the trusted HTTPS gateway for camera-required home exams. Camera/browser events are review prompts, not automatic findings of misconduct.

## Operational checks before live use

- Pair a test Android device to a test Windows Server over HTTPS.
- Import the matching exam/candidate package on the Windows Server before attempting sync.
- Complete one objective attempt, one theory/drawing attempt, and one attempt with proctor events.
- Confirm the Android outbox remains pending while offline and becomes synced only after a Windows acknowledgement.
- Replay the same attempt and confirm idempotent duplicate acknowledgement.
- Force a conflicting attempt and verify Admin review rather than overwrite.
- Test 1, 5, 10 and 20 simultaneous candidates before increasing the target. No 50-candidate capacity claim is made without measurement.
- Do not use production records until the school's test-copy validation is complete.
