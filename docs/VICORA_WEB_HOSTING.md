# VICORA Web Host (independent cloud host)

## Purpose

This service runs the existing Flask CBT backend and the same Admin and Student browser
interfaces as an independent HTTPS examination host. It does not depend on an Android phone
or a Windows PC staying online. The school database lives on the host's persistent disk.

## Deployment target

The initial deployment blueprint targets Render because the current backend uses SQLite and
needs a persistent disk. Vercel remains suitable for static front-end/gateway work, but its
serverless functions are not the right place to store this SQLite database.

1. Connect the `veehicee1/Vicora` repository to a Render Web Service using the included
   `render.yaml` blueprint.
2. Review the paid Starter web-service plan and 10 GB persistent disk before creating it.
3. Keep automatic deployment disabled until the owner approves a production release.
4. After the service is created, set the school name, upload the school logo, and immediately
   change the initial administrator password.
5. Use the HTTPS Render hostname or connect the school's custom domain.
6. Test the admin login, student login, question bank, exam open/close, autosave, submission,
   result publication, backups and restart persistence before inviting candidates.

## Vercel gateway configuration

- Set `VICORA_API_ORIGIN` in the Vercel project to the HTTPS origin of the approved persistent
  VICORA API host. Do not include a path, username, password, query or fragment.
- The older `ANDROID_HOST_ORIGIN` variable remains supported for a Cloudflare Access-protected
  Android/Windows host tunnel.
- For a public Render HTTPS origin, Cloudflare Access credentials are optional. If the upstream
  is protected by Cloudflare Access, set both `CF_ACCESS_CLIENT_ID` and
  `CF_ACCESS_CLIENT_SECRET`; never set only one.
- Set `VICORA_PLATFORM_ADMIN_TOKEN` only as a backend environment secret. The platform review
  page asks the authorized platform operator to enter that token for the current browser session.
  Do not commit it or place it in public frontend code.
- The Vercel gateway exposes only the explicitly allowed student, school onboarding and
  platform-review API routes. It does not proxy general school administration, backup or sync
  endpoints.

## Security

- Remote Admin is allowed only when public hosting, HTTPS cookie protection and the explicit
  hosted-admin switch are all enabled.
- The managed hosting ingress is the only trusted forwarded-header layer in this mode.
- The raw HTTP listener must not be exposed outside the managed host ingress.
- Keep the admin password private and use separate staff roles.
- The persistent disk is required: the service must not use an ephemeral filesystem for
  `cbt.db`, backups or school identity data.
- One service instance is intentional because this release uses SQLite; do not horizontally
  scale the service or attach multiple writers to the same database.

## Current cross-device boundary

The web host is an independent online examination host with its own persistent school
database. Android already has a controlled sync protocol for pairing to a compatible
authoritative server. Windows-to-cloud synchronization and a single universal sync engine
for all three host types are separate remaining work; this blueprint does not claim those
are complete. Do not copy SQLite files between devices.

## Release safety

The blueprint has `autoDeploy: false`. Creating this file does not create a Render service,
incur hosting charges, configure a domain, or publish the school database. Production
deployment requires owner approval.


## VICORA Platform Admin dashboard (Apps Script central registry)

The mobile-friendly platform dashboard is served at `/platform-admin.html`. It uses the dedicated Vercel function at `/api/central/admin`; the Apps Script platform key is injected only by that server-side function and is never sent to browser code.

Configure these three Vercel environment variables as encrypted server-side secrets for the intended Preview/Production environment:

- `VICORA_CENTRAL_APPS_SCRIPT_URL`: the deployed Apps Script Web App URL ending in `/exec`.
- `VICORA_PLATFORM_ADMIN_KEY`: the same secret configured as `VICORA_PLATFORM_ADMIN_KEY` in the Apps Script project's Script Properties.
- `VICORA_PLATFORM_ADMIN_TOKEN`: a separate strong operator token that the platform owner enters on the dashboard. Do not reuse the Apps Script key.

The dashboard supports listing pending/all applications, approving or rejecting applications, and viewing registered schools. Approval creates the School ID, School Code and pending school administrator in the Apps Script central spreadsheet. The one-time activation token is displayed to the authorized operator and may also be emailed by Apps Script.

Do not place either secret in HTML, JavaScript, GitHub source, or a mobile app. The platform operator token is held only in page memory for the active browser session. Use a unique random value for each secret and restrict access to Vercel project environment settings.

Before enabling real school onboarding:
1. Confirm the Apps Script deployment's health endpoint reports the intended source version.
2. Confirm the Apps Script Script Properties contain the platform key and that the key matches the Vercel secret without sharing either value.
3. Configure the three Vercel secrets and deploy a Preview.
4. Open `/platform-admin.html`, enter the separate operator token, and verify the application list and registered-school list.
5. Submit one clearly marked test school application and verify approval, generated IDs, pending admin record and one-time activation flow.
6. Do not approve production schools until the central backend version mismatch and tenant onboarding readiness have been resolved.

This dashboard does not create a Vercel deployment, set environment variables, modify the live Google spreadsheet, or approve any school by itself.
