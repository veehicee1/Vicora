# VICORA Firebase Live Examination Foundation

## Decision

Google Apps Script remains VICORA's system of record for school tenancy, school administration, staff, classes, subjects, question authoring, exam configuration, marking, results, reports, and audit. Firebase Realtime Database is the low-latency live session and answer transport for candidates.

The web client must not receive a Firebase service-account credential or an Admin SDK credential. Firebase client access is denied until a trusted token-exchange endpoint and restrictive Realtime Database rules are deployed.

## Identity and trust boundary

1. A candidate signs in through VICORA's existing school identity flow.
2. A trusted server endpoint validates the existing VICORA Central session against the Apps Script `school.profile` action.
3. Only after validation, the trusted endpoint mints a short-lived Firebase custom token with server-derived claims: `school_id`, `user_id`, `role`, and (for candidates) `candidate_id`.
4. The browser exchanges that custom token for a Firebase ID token. Never accept school, role, candidate, or exam access claims supplied by the browser.
5. Revoke/expire access when the VICORA session expires or is revoked. Do not put Firebase service-account JSON, private keys, Apps Script admin keys, or session tokens in GitHub or frontend files.

The token broker is intended to run as a Cloudflare Pages Function because the current VICORA Pages deployment already has a server-side admin bridge and secure HttpOnly VICORA session cookie. The Apps Script Central API remains authoritative for identity. The broker must validate the session on every exchange and must not create a parallel password database.

## Live data boundaries

Suggested Realtime Database layout (all records scoped by immutable `school_id`):

- `liveExams/{schoolId}/{examId}/`: published exam runtime metadata only; no answer keys.
- `liveQuestions/{schoolId}/{examId}/{questionId}/`: candidate-visible question text/options only; no correct answers or marking keys.
- `attempts/{schoolId}/{examId}/{candidateId}/`: attempt state, server timestamps, deadline, and sync status.
- `attempts/{schoolId}/{examId}/{candidateId}/answers/{questionId}/`: latest acknowledged answer plus monotonically increasing client sequence.
- `presence/{schoolId}/{examId}/{candidateId}/`: ephemeral connection/heartbeat data.

Question authoring and exam publication remain in VICORA administration. A controlled publish operation copies only the candidate-visible exam snapshot to Firebase. Correct answers and marking rubrics remain server-side and are never published to candidate-readable paths.

## Reliability and exam integrity

- One authoritative attempt per candidate and exam unless an explicit exam policy allows otherwise.
- Use server timestamps and server-side deadlines; never trust the candidate device clock.
- Answer writes are idempotent and ordered by sequence. A stale retry must not replace a newer answer.
- Show a clear saved/saving/offline state. An answer is "saved" only after Firebase acknowledges it.
- Queue pending answers locally during a brief network interruption and retry safely after reconnect.
- Final submission is server-controlled and immutable; duplicate submits return the original result.
- Admin/invigilator controls and monitoring must be role-checked server-side.
- Keep audit events for attempt start, reconnect, answer save, submit, and administrative intervention.
- Do not declare support for 100 concurrent candidates until a load test with at least 100 simulated clients and real-device network tests passes.

## Cost and capacity

The Firebase Spark plan's Realtime Database simultaneous-connection allowance is 100. That leaves no safe headroom for administrators, invigilators, test clients, or reconnect bursts. For VICORA's stated target of 100 candidates in one sitting, plan for the Blaze pay-as-you-go plan before a real examination. Set budget alerts and usage monitoring; budget alerts notify but do not automatically cap charges. Validate the current Firebase pricing/quotas before production.

## Setup checklist

1. Create a dedicated Firebase project named for VICORA (do not reuse a personal or unrelated project).
2. Add a Web App to obtain the Firebase public web configuration. The web API key is not a server secret; database rules and Auth token claims enforce access.
3. Enable Realtime Database and choose a region close to the expected users where available.
4. Keep the database rules deny-all until the trusted token broker and tested rules are ready.
5. Enable Firebase Authentication custom-token sign-in as the identity mechanism. Do not enable public email/password sign-up for candidates.
6. Create a service account for the token broker. Store its private key only as a Cloudflare secret, never in GitHub, Apps Script source, browser code, chat, or screenshots.
7. Configure the Pages Function secrets and public Firebase web config only after the broker implementation is reviewed.
8. Test with synthetic schools, exams, candidates, and answers. Do not copy live student data into the test project.
9. Run security-rule tests, duplicate/retry tests, reconnect tests, and a 100-client load test before enabling a real exam.

## Current status

This is a design/setup foundation only. It does not create a Firebase project, connect candidate login, change existing exam records, or deploy a production live-exam service. The next implementation step is the trusted VICORA-session-to-Firebase-token broker and the associated rules/tests.
