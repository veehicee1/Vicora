# VICORA CBT — Android and Windows Hosting

## Hosting choices

VICORA CBT supports three student entry paths to the same examination application:

1. **Windows school host** — the Windows Admin application starts the bundled VICORA server on the school's computer. The server owns the authoritative SQLite database. Students use the displayed LAN link in a browser or the VICORA Examination app.
2. **Android phone host** — the Android Admin app runs the same Flask backend in the phone's private app storage and serves the student portal on Wi-Fi or the phone's hotspot. The phone owns a separate local database until it synchronises approved attempts to a paired Windows server.
3. **Web host** — students use the school-provided HTTPS or LAN address in a supported browser. A web deployment must point to the intended school database.

## Web examination website

The browser examination is a single shared client, not a separate database or a third independent exam engine:

- The school shares the browser link served by its selected host: `http(s)://school-host/` or `http(s)://school-host/home`.
- Both browser entry points serve the same `web/student.html` client. The client calls relative `/api/student/*` routes, so login, exam lists, paper retrieval, answer saves, heartbeat, submission and published grades stay on the same origin as the active host.
- The browser reads the school name, theme and school logo from `/api/public/info`; it does not need a separately configured school database URL.
- Therefore a school can use the same browser examination experience whether its selected host is Windows or Android. The link must point to that host, and the host must remain reachable for the duration of the examination.
- A public website/domain does not automatically discover or reach a phone/PC behind a school router. Off-site browser access requires the school's HTTPS gateway/reverse proxy to route the student-facing requests to the selected host. Do not expose the host's raw LAN HTTP port.

**Current limitation:** browser examination itself is already host-relative, but automatic Android ↔ Windows exam-package synchronization and automatic public-domain routing to whichever host is active are not yet complete. Until then, share the selected host's own address and use the existing controlled package-transfer/result-sync workflow where required.

## First-run school identity

- Android Host asks for the school's name before starting the host for the first time.
- Windows Host asks for the school's name during its first launch.
- The name is stored in the local CBT database and displayed by the Admin and student interfaces.
- The school logo is uploaded separately from Admin → Settings → School identity.
- VICORA remains the platform identity. Each host installation has one school identity and one local database; this is not multi-school tenancy.

## Windows host setup

1. Install the VICORA CBT Admin Windows installer.
2. Open **VICORA CBT Admin** and choose **Host on this Windows PC**.
3. On first launch, enter the school's full name in the setup prompt.
4. The Admin application starts the bundled server on port 8000 and opens the Admin portal.
5. Connect the Windows computer and candidate devices to the same school Wi-Fi/router, or enable Windows Mobile Hotspot.
6. Use the student link shown in Admin → Settings → Local Exam Network. Keep the Windows host powered on and the host process running.
7. Install the VICORA Examination client on Windows candidates if they are using the desktop client; connect it to the same school link.

The installer adds a Windows Firewall inbound rule for TCP 8000 on Private network profiles only. Do not expose this HTTP port directly to the public internet.

## Android host setup

1. Install the VICORA CBT Admin Android APK.
2. Choose **Host Exam on This Device**.
3. Enter the school's name when prompted.
4. Connect to school Wi-Fi or enable the phone hotspot.
5. Share the student link shown by the app. Candidates must join the same network.
6. Keep the phone powered, cool, connected and hosting throughout the examination. Android may stop a host after force-stop, battery exhaustion, device shutdown or thermal protection.

The Android host uses port 8765. Local Wi-Fi/hotspot hosting does not require internet access.

## Windows ↔ Android examination and result synchronisation

The Windows school server is the authoritative source for exam setup, question content and candidate records when it is selected as the central server. Android is a paired edge host/cache that can serve the browser examination locally over Wi-Fi or hotspot.

1. Start the Windows host and sign in as Super Admin or Exam Administrator.
2. Open Admin → Settings → Android Host pairing and generate a one-time pairing code.
3. In Android Host mode, choose Pair with Windows Server and enter the Windows server's trusted HTTPS address and one-time code.
4. In Windows Admin → Exams, select **Enable Android sync** for each examination approved for that phone. Only explicitly enabled examinations are sent to paired devices.
5. The Android host's network-constrained background worker checks for approved exam packages after pairing and periodically (WorkManager minimum interval: 15 minutes). It also runs result uploads in the same sync cycle.
6. Downloaded exams, their assigned classes, candidate roster/access codes and question content are imported into the Android database automatically. Imported exams remain **Draft** until an administrator reviews and opens them on the Android host.
7. Candidate attempts completed on Android are placed in the durable local outbox and uploaded to Windows over HTTPS. Windows validates the device, school identities, candidate, exam revision and question identities, then recomputes objective/automatic marks. Theory responses and drawings enter the normal marking workflow.
8. Windows acknowledges each attempt before Android marks it synced. Network failures retry. Duplicate uploads are idempotent; revision mismatches and duplicate/conflicting attempts are held for administrator review.

**Revision and safety rules:** candidate roster changes are tracked separately from exam-content revisions, so new or updated candidate records can sync without rewriting an exam attempt. If exam content changes after an Android candidate has started an attempt, the phone will not overwrite that exam; it records a sync conflict for review. A school-name mismatch is rejected to prevent mixing two schools' databases. The automatic pull sends one approved exam package per polling cycle and enforces an 18 MB response limit; larger packages need to be reduced or transferred through the existing secure manual method.

**What this means:** exam definitions and candidate records flow Windows → Android; completed Android attempts flow Android → Windows. This is controlled application-level synchronisation, not raw SQLite replication or simultaneous multi-master editing. If Android is selected as the only host, it can still serve browser candidates locally, but a separate Windows server must be paired as the central result destination for this sync path.

## Internet and off-site access

An internet connection alone does not make a private phone or Windows LAN address reachable from home. For off-site access, deploy a trusted HTTPS gateway/reverse proxy with an explicit school-controlled access policy. For the Windows Host, the safest simple arrangement is a tunnel/reverse-proxy connector running on the same Windows PC and forwarding HTTPS requests to `http://127.0.0.1:8000`. The Windows Host accepts the forwarded HTTPS scheme only from loopback proxy connections; it does not trust forwarded client-IP headers and remote Admin remains disabled by default. This permits the Android Host pairing and result-sync endpoints to recognise the HTTPS connection without making the Admin console public. Do not port-forward Android port 8765 or Windows port 8000 directly to the public internet. The gateway should expose only the specific pairing and result-sync endpoints needed for device synchronisation, plus student-facing routes if required; Admin, device management, backups and database endpoints must remain private.

## Validation still required on real devices

- Test Android Admin and Examination APKs on supported physical phones.
- Test Windows Admin and Examination apps on a clean Windows 10/11 PC.
- Confirm Windows Firewall prompts/rules and student access from another device.
- Test Android hotspot, Wi-Fi change, screen lock, app restart and battery behaviour.
- Pair Android to a Windows host over HTTPS; test objective, theory/drawing and proctor-event result transfer.
- Test offline queue/retry, duplicate acknowledgement, revocation and conflict review.
- Load-test candidate concurrency before claiming a maximum capacity.

CI unit tests and package builds do not replace these real-device/network tests. No production deployment or merge to main is implied by this document.
