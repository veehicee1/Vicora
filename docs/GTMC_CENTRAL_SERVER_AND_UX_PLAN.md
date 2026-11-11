# GTMC CBT — Central Server, Remote Access and UI/UX Implementation Plan

Status: implementation baseline for the next development milestones  
Repository: `sheggun1/CBT-GTMC`  
Base: existing Flask + SQLite CBT engine and the merged Admin/Examination application split

## Decisions confirmed by the school

- Keep two installable products: **GTMC CBT Admin** and **GTMC CBT Examination**.
- Admin is for staff accounts and role-based administrative work. There is no separate invigilator application.
- Examination is for students only; it must not expose staff administration routes or controls.
- One designated Windows school computer is the authoritative server and owns the live school database.
- Windows and Android clients should connect to that same server/database whenever connected.
- Supported ways to give the server internet access: school Wi-Fi, Ethernet, a phone's Wi-Fi hotspot, and USB tethering.
- School LAN examinations must continue to work without internet.
- Remote administration must use a direct, encrypted connection to the school server. Do not require Tailscale, Cloudflare Tunnel, or a third-party traffic relay.
- Preserve existing student records, questions, exams, attempts, answers, scores, backups, and audit history. No destructive migration or live SQLite file copying.

## Important network distinction

A phone hotspot or USB tethering gives the server PC an **outbound internet connection**. It does not guarantee that a device outside the school can initiate a connection back to the PC. Many mobile and fixed ISPs use carrier-grade NAT (CGNAT), which blocks unsolicited inbound connections.

Direct remote access without a relay requires the ISP/network to provide a publicly reachable address and permit inbound traffic, plus router/firewall configuration. If a phone network uses CGNAT, hotspot internet will still work for ordinary outbound traffic and LAN CBT, but it will not by itself make the school server remotely reachable. The school can ask its ISP for a public IP or suitable business/static-IP service. Do not expose Flask/Waitress port 8000 directly to the public internet.

## Target architecture

```
GTMC Admin Windows / Android  ─┐
GTMC Examination Windows / Android ─┼─ HTTPS (443) ─ School network edge ─ Reverse proxy ─ Flask API (private) ─ SQLite
School LAN browsers / kiosks ───────┘                                  (TLS)             (127.0.0.1:8000)
```

- The school Windows PC remains the single authority for student, class, subject, question, exam, session, answer, result, settings and audit data.
- The application server stays on a private interface/loopback behind a TLS reverse proxy. The database file is never served or exposed over the network.
- LAN clients use the server's private LAN address. Remote clients use the school's public hostname/address over HTTPS when the ISP supports direct inbound connectivity.
- Phone hotspot and USB tethering are server-side internet uplinks; the CBT server should not need to know which adapter supplied the internet.
- Admin access is protected by server-side authentication and role/permission checks, not by hiding menu items alone.
- The student app accepts student credentials only. Staff endpoints remain inaccessible to student sessions.
- Both Windows launchers must detect and reuse the same running server instead of starting a second database/server instance.

## Connection and availability behaviour

1. Prefer the configured school LAN endpoint while the device is on the school network.
2. Use the configured HTTPS remote endpoint away from school.
3. Show a clear connection indicator: Connected to School Server, Connecting, Offline, or Server Unavailable. Show the selected endpoint label without exposing credentials or tokens.
4. Reconnect with bounded backoff and a visible manual Retry action.
5. Do not claim an answer is saved centrally until the server acknowledges it.
6. For any future offline answer queue, persist pending answers locally, use stable attempt/question identifiers and idempotent writes, retry safely, and show pending/synced/failed states. Never merge SQLite database files or silently overwrite server records.
7. Formal exams remain server-timed. If a client loses connection, preserve the student's in-progress UI and durable pending answer data, but clearly show the connection state. The server remains authoritative for final submission and timing. The exact offline-exam policy must be validated before production release.

## Security requirements before remote release

- HTTPS only for remote traffic; valid TLS certificate and hostname.
- Keep port 8000 private; expose only the HTTPS reverse-proxy listener.
- Windows firewall allows port 8000 only from loopback or the trusted private LAN as required; firewall rules are documented and least-privilege.
- Change the default admin password on first setup; use strong password hashing, login throttling, secure session cookies, CSRF protection for cookie-authenticated state changes, and server-side role checks.
- Add a dedicated staff account/role and permission model before enabling multiple staff roles; the current backend has a single admin login.
- Add audit events for remote logins, failed logins, exam actions, imports, exports, and permission changes.
- Keep automatic and manual backups on the school server, with a tested restore procedure.
- Never include passwords, access codes, session tokens, or private student information in diagnostic logs.

## UI/UX standard

### Admin application
- Modern responsive blue-and-white school operations interface with clear hierarchy, consistent spacing, readable typography and accessible contrast.
- Persistent navigation on desktop; compact collapsible/drawer navigation on phones.
- Dashboard cards for active exams, candidates, submitted, writing, offline and pending actions.
- Clear quick actions for Create Exam, Import Students, Import Questions, Live Monitor and Results.
- Live Monitor with searchable/filterable candidate table, status chips, progress, time remaining, and carefully confirmed actions.
- Consistent empty, loading, error, success and offline states; no blank panels when an API fails.
- Forms with inline validation, preview-before-import, duplicate warnings and confirmation for destructive actions.
- Connection centre with LAN/remote endpoint status, last successful contact, retry, and setup guidance. Never display secrets.

### Examination application
- Student-first, distraction-free layout; no admin navigation.
- Large readable question text and answer choices, generous touch targets, responsive portrait/landscape layout.
- Persistent exam title, candidate identity, countdown timer and connection/sync status.
- Question palette showing current, answered, unanswered and flagged questions with a text legend (not colour alone).
- Clear previous/next controls, flag-for-review, answer count and a review screen before submission.
- Confirmed submission flow and clear completion/result policy according to exam mode.
- Keyboard support on Windows and touch support on Android; prevent accidental browser zoom/scroll without blocking legitimate accessibility features.
- In practice mode, reveal corrections and explanations only when permitted. In formal exam mode, never send answer keys to the client before authorised release.

## Safe implementation sequence

### Milestone 1 — Baseline and product UX
- Verify the merged Admin/Examination split and its CI workflows.
- Review current API permissions and the two client interfaces.
- Establish shared design tokens/components and improve responsive Admin and Examination UX without changing score calculations or existing records.
- Add a connection-status/health contract and clear endpoint selection UX.

### Milestone 2 — One authoritative server
- Add an explicit server configuration for bind address, port, data directory and advertised LAN endpoint.
- Add safe single-instance/server readiness checks for both Windows launchers.
- Add a documented school-server setup wizard/checklist for Wi-Fi, Ethernet and phone USB/hotspot tethering.
- Keep the existing SQLite database path and use additive migrations only.

### Milestone 3 — Direct secure remote access
- Support a school-owned hostname/public IP and a locally operated HTTPS reverse proxy.
- Add a preflight diagnostic that explains public-IP, CGNAT, DNS, TLS and firewall readiness.
- Keep port 8000 private. Remote access remains disabled until all security checks pass.
- No third-party traffic relay is required or assumed.

### Milestone 4 — Durable offline recovery and sync
- Implement a versioned, authenticated, idempotent record-level sync protocol only after the central-server contract is stable.
- Persist pending answer writes on clients; add duplicate protection, acknowledgements, retry/backoff, conflict handling and audit trail.
- Keep the central server authoritative for exam timing, attempt identity, marking and final result.
- Do not automatically merge independent standalone student databases into the school database.

### Milestone 5 — Exam modes and template centre
- Add Practice, Test, Exam and WAEC/JAMB simulation profiles with server-enforced release/correction policies.
- Add validated template download/import/export, sample rows, preview, error report and duplicate checks.
- Add question explanation support through a backward-compatible schema migration.

## Release gates

- Existing database is backed up before any server upgrade.
- Existing records and scores are verified unchanged after upgrade.
- CI builds both Windows executables and both Android APKs.
- LAN tests cover Windows and Android clients, simultaneous candidates and server restart.
- Remote tests are performed only on a confirmed publicly reachable ISP connection using HTTPS.
- Network interruption tests verify that answers are not silently lost or duplicated.
- No production release based solely on a successful compile; physical-device and school-LAN testing is required.
