# VICORA architecture and migration blueprint

## Recorded CBT architecture

The prior project discussions describe this intended architecture:

- Public student website hosted through Vercel.
- Android device can act as a local CBT host on port 8765.
- Cloudflare Tunnel provides HTTPS access to the Android host without router port forwarding.
- Cloudflare Access service credentials remain server-side in the Vercel function.
- Public proxy routes are restricted to student/public information routes; administrative, pairing, sync, management and backup routes must not be exposed publicly.
- Windows Server remains authoritative for examination results.
- Android uses a durable result outbox and retries synchronisation; results are marked synced only after acknowledgement.
- Student-facing route guards and proctor camera policy are part of the recorded design.

These are historical architecture notes, not a fresh audit of current code or deployment state.

## Proposed repository layout

```text
vicora/
  apps/
    web/
    admin/
    parent/
    student/
    desktop/
    android-host/
  services/
    api/
    auth/
    examination/
    learning/
    notifications/
    reporting/
    synchronisation/
  packages/
    ui/
    shared-types/
    validation/
  infrastructure/
    vercel/
    cloudflare/
    windows-server/
    android/
  docs/
  tests/
  .github/
    workflows/
```

This is a proposed layout, not a claim that these modules have already been implemented.

## Release validation

- Compare the recovered source against the latest source repository commit.
- Inventory branches, tags, GitHub Actions workflows and release assets.
- Recreate required repository secrets through GitHub settings without exposing values.
- Verify authentication, roles, student data isolation and server-side authorization.
- Test online/offline examinations, result outbox recovery, duplicate prevention and conflict handling.
- Test proctor camera policy over HTTPS.
- Test Windows Server compatibility on a separate staging machine.
- Run automated tests and create release builds only after owner approval.
