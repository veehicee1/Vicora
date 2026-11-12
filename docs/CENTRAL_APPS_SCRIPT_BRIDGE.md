# VICORA Central Apps Script integration

## Responsibilities and data boundaries

- Google Apps Script is the central school registry, application approval, activation and credential service.
- The existing Flask/SQLite application remains the CBT engine and keeps examination content, candidates, attempts, answers, scoring and reports.
- When a central school administrator first activates or signs in, the matching approved school identity is provisioned in local SQLite using the exact central `schoolId` and `schoolCode`.
- Central account IDs are mapped to local Admin role records. A random unusable local password hash is generated; the Apps Script password is never copied into SQLite.
- The Apps Script session bearer token is stored server-side in the local `central_sessions` table. The browser receives only a random local session key in Flask's signed session cookie.
- No existing GTMC school identity, students, questions, exams, attempts, scores or reports are migrated or overwritten by this bridge.

## Server configuration

Set this variable on the trusted Flask/Windows Host process and the trusted API origin used by the Vercel gateway:

```text
VICORA_CENTRAL_APPS_SCRIPT_URL=https://script.google.com/macros/s/DEPLOYMENT_ID/exec
```

Use the exact Web App URL from the VICORA Central Backend deployment. The bridge validates that it is an HTTPS Google Apps Script Web App URL.

For platform administration, configure these secrets on the trusted API server only:

```text
VICORA_PLATFORM_ADMIN_TOKEN=<the existing VICORA platform gateway token>
VICORA_CENTRAL_ADMIN_KEY=<the VICORA_PLATFORM_ADMIN_KEY from Apps Script Script Properties>
```

The first token authorizes a platform administrator request to the Flask API. The second is injected by Flask when it calls Apps Script. Never expose either value in a browser page, Android APK, Windows renderer, source file, GitHub commit or school-facing environment configuration.

## Integrated endpoints and pages

- `GET /api/central/health` — server-side health check of the configured Apps Script deployment.
- `POST /api/central/request` — allowlisted public and authenticated school actions.
- `POST /api/central/activate` — activates the central school administrator, resolves the approved central school, and provisions the same school identity in local SQLite.
- `POST /api/central/login` — verifies School Code, email and password with Apps Script, then creates a local CBT session mapped to the central user and role.
- `POST /api/central/admin` — allowlisted platform-admin actions; requires the platform gateway token and injects the Apps Script admin key server-side.
- `public/register-school.html` — sends new applications to Apps Script.
- `public/activate-school.html` — activates the central school administrator.
- `public/admin/index.html` and `web/admin.html` — use central School Code + email + password sign-in.

The Vercel API gateway forwards only the `/api/central/` prefix to the configured trusted VICORA API origin. It is not an unrestricted URL proxy.

## Role mapping

| Apps Script role | Local CBT role |
|---|---|
| school_admin / school_owner | super_admin |
| teacher / exam_officer | exam_administrator |
| viewer | auditor |

This mapping is intentionally explicit. A new central role must not gain CBT permissions until a reviewed mapping is added.

## Important limits before production

1. Apps Script and local SQLite remain separate databases. Class, subject, student, host and general metadata synchronisation is not yet a complete bidirectional sync implementation.
2. The central administrator console UI and secure delivery of one-time approval tokens still need to be connected to the central admin endpoint. Do not approve schools through the old local onboarding screen and expect that approval to exist in Apps Script.
3. A central school must use the same persistent Flask/SQLite API origin for its CBT portal. Do not point multiple schools at separate ephemeral databases.
4. Test with a disposable school before onboarding real schools. Verify registration, approval, email delivery, activation, login, role permissions, logout, expiry and school isolation.
5. Apps Script quotas and execution limits apply. Do not send high-volume candidate answer traffic to Google Sheets.
6. Configure backups, recovery, abuse throttling and account recovery before public launch.

## Local health test

After setting `VICORA_CENTRAL_APPS_SCRIPT_URL` in the Windows Host process environment and restarting the Host, open:

```text
http://127.0.0.1:8000/api/central/health
```

A successful response includes `"ok": true`, `"connected": true`, and the Apps Script service name. If the URL is missing or Apps Script cannot be reached, the endpoint returns HTTP 503.
