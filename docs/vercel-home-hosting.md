# VICORA web examination and school portal on Vercel

## Scope

Vercel serves the public VICORA student examination page and PWA shell, the school registration/activation pages, and the school Admin page at `/admin/`.
The Node gateway remains a strict allowlist. Student/public/platform/Android-host routes are separately constrained. School Admin API forwarding is **disabled by default** and is enabled only when `VICORA_ENABLE_ADMIN_GATEWAY=1` is set in Vercel. Even then, the upstream Flask application must authenticate the Admin session and enforce staff roles/tenant scope on every request. The gateway is not a general-purpose open proxy.

The Windows Server remains the authoritative results server. Android remains the temporary
examination host and retains its durable result outbox and acknowledgement-based sync.

## Required Vercel project settings

After reviewing and merging this change, create a Vercel project connected to
`sheggun1/CBT-GTMC` with:

- Framework preset: Other
- Root directory: repository root
- Build command: leave empty
- Output directory: `public`
- Production branch: `main`

Do not create or promote a production deployment until the school has completed the
gateway setup and approved a test deployment. Vercel Git integration can automatically
create Preview deployments for pushes and pull requests, so connect the project only
when ready to allow those previews.

## School Admin portal

- The school Admin UI is served from `/admin/` as a static copy of the maintained `web/admin.html`.
- To enable it, set `VICORA_ENABLE_ADMIN_GATEWAY=1` in the Vercel project environment. Leave it unset or set to `0` to keep the Admin API blocked.
- Configure `VICORA_API_ORIGIN` to a trusted HTTPS persistent API origin. The gateway forwards only the browser session cookie and expected headers; Flask remains responsible for login, CSRF protections where configured, role checks, school context and data isolation.
- The Admin page is not operational until a persistent backend is deployed and configured. Vercel static hosting alone does not host the Flask process or SQLite database.
- Do not use the Android student-only tunnel as the Admin API origin. Use a separately protected, persistent backend origin with server-side access controls.

## Android-side Cloudflare Tunnel ingress

Run the tunnel client on the Android phone that is hosting the CBT server (for example,
from a managed Termux session). The tunnel origin should connect to the local Android
listener at `http://127.0.0.1:8765`. Use path-based ingress as a second independent
restriction so the tunnel itself cannot route admin or management requests:

```yaml
ingress:
  - hostname: exam-host.example.com
    path: ^/api/(student/.*|public/info)$
    service: http://127.0.0.1:8765
  - hostname: exam-host.example.com
    service: http_status:404
  - service: http_status:404
```

Replace the sample hostname with the actual Cloudflare Tunnel hostname. Protect that
hostname with a Cloudflare Access application requiring the service token configured in
Vercel. Do not publish a tunnel hostname without Access protection. The path rule is
important because the Android local listener intentionally keeps loopback Admin access
for the phone's own Admin WebView; only the student API paths should traverse the tunnel.

## Required Vercel environment variables

Set all three as encrypted/sensitive server-side variables for Preview and Production:

- `ANDROID_HOST_ORIGIN`: the origin of the school's Cloudflare Tunnel, e.g. `https://exam-host.example.com`
- `CF_ACCESS_CLIENT_ID`: Cloudflare Access service-token client ID
- `CF_ACCESS_CLIENT_SECRET`: Cloudflare Access service-token client secret

Never put these values in the repository, student HTML, browser JavaScript, or a public
GitHub Actions variable. The proxy returns HTTP 503 until all three are configured.

Protect the tunnel hostname with a Cloudflare Access application that requires the
service token. Do not make the tunnel origin publicly accessible without Access protection.
The Vercel function adds the service-token headers server-side; browser clients never receive them.

## Android host and tunnel prerequisites

- Android hosting must be running and paired to the test Windows Server.
- The tunnel must terminate trusted HTTPS and reach the Android host over its private/local
  connection. Do not open or forward TCP 8765 on the router.
- Preserve the existing Android host's student-only remote route restrictions.
- Configure the tunnel/Access policy so only the Vercel server-side gateway can reach the
  origin. Keep the tunnel service token private and revocable.
- The student browser uses Vercel HTTPS for secure-context camera permission. The actual
  Proctor Mode policy remains controlled by the exam settings (Off / Optional / Required).

## Request and data handling

- Student login, exam retrieval, answers, and submissions are network-only; the service
  worker caches only the public page shell and static icons.
- The proxy forwards browser session cookies to the Android host and returns session cookies
  to the same Vercel origin. API responses are marked no-store.
- Only the two allowed student API route groups are proxied. All other paths return 404.
- The proxy uses a streamed request/response path. Vercel platform request-size and execution
  limits still apply; test large theory/drawing submissions before live exams.
- A disconnected phone, tunnel, or internet connection interrupts live access. The Android
  outbox continues to queue completed eligible attempts until the Windows Server acknowledges them.

## Test checklist before production

1. Deploy a Preview only after the Cloudflare Tunnel and Access service token are ready.
2. Confirm `/home/` loads and the PWA service worker registers.
3. Confirm `/api/public/info` and student login work through the Vercel hostname.
4. Confirm student exam retrieval, timer, autosave, objective answers, theory text/drawings,
   submit, and result acknowledgement work.
5. With `VICORA_ENABLE_ADMIN_GATEWAY` unset, confirm `/api/admin/*` returns 404.
6. On a separate protected Preview with the flag set, verify Admin login, session cookie,
   role restrictions, school isolation, and logout. Confirm backups remain blocked while
   more than one approved school exists until school-scoped backup/restore is complete.
7. Confirm pairing, device management, backup and database paths remain unavailable unless
   explicitly required and protected by the upstream application.
8. Test camera Off, Optional, and Required on supported HTTPS browsers.
9. Disconnect the phone/network during a test and verify Android outbox retry and Windows
   acknowledgement behaviour.
10. Benchmark 1, 5, 10, and 20 simultaneous candidates before increasing load.

No live deployment, Android configuration, Windows Server configuration, database, or router
change is performed by this repository preparation.
