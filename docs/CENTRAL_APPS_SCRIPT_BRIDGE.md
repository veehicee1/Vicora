# VICORA Central Apps Script bridge

## Architecture

- Google Apps Script is the central school registry and account service.
- The existing Flask/SQLite database remains the local CBT engine and continues to own examination content, attempts, answers, scores and reports.
- The Apps Script database and local SQLite database are separate stores. This bridge does not migrate, overwrite or silently merge records.

## Server configuration

Set the following environment variable on the trusted VICORA API/Windows Host process:

```text
VICORA_CENTRAL_APPS_SCRIPT_URL=https://script.google.com/macros/s/DEPLOYMENT_ID/exec
```

Use the exact Web App URL from the VICORA Central Backend deployment. The bridge validates that it is an HTTPS Google Apps Script Web App URL.

For trusted platform administration only, configure this additional secret on the server that hosts the platform administrator API:

```text
VICORA_CENTRAL_ADMIN_KEY=<the VICORA_PLATFORM_ADMIN_KEY from Apps Script Script Properties>
```

Never place this key in a browser page, Android APK, Windows renderer, source file, GitHub commit, or a school computer's public configuration. The normal school-facing requests do not need this key.

## Bridge endpoints

- `GET /api/central/health` — server-side health check of the configured Apps Script deployment.
- `POST /api/central/request` — allowlisted public and authenticated school actions. Apps Script remains responsible for validating activation tokens, session tokens and host tokens.
- `POST /api/central/admin` — allowlisted platform-admin actions. The server injects the admin key; callers cannot supply or override it.

The Vercel API gateway forwards only the `/api/central/` prefix to the configured trusted VICORA API origin. It is not an unrestricted URL proxy.

## Integration status and next work

This bridge is the server-side transport foundation. The existing public registration/activation pages and local CBT Admin login still use the legacy SQLite onboarding routes at this stage. Do not enable both registration systems for real schools until the UI and account/session provisioning adapter are completed and tested.

Next implementation steps:
1. Connect school application, approval and activation screens to the central Apps Script actions.
2. Implement a safe central-login-to-local-CBT session mapping, including school identity provisioning and role mapping.
3. Add host enrollment and modest metadata sync with idempotency and conflict handling.
4. Test with a disposable school and sample data; verify existing GTMC records, scores and reports remain unchanged.

## Local health test

After setting the URL in the Windows Host process environment and restarting the Host, open:

```text
http://127.0.0.1:8000/api/central/health
```

A successful response includes `"ok": true`, `"connected": true`, and the Apps Script service name. If the URL is not configured or Apps Script cannot be reached, the endpoint returns HTTP 503 and does not pretend the central service is connected.
