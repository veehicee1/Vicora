# VICORA cloud Android test builds

This repository contains a Codemagic workflow that builds the two Android debug APKs without installing Android Studio, Java, Gradle, or the Android SDK on the owner's computer.

## Build outputs

- Admin: `android/app/build/outputs/apk/admin/debug/app-admin-debug.apk`
- Examination: `android/app/build/outputs/apk/examination/debug/app-examination-debug.apk`

These are debug/testing APKs, not production-signed releases. The workflow does not publish to Google Play or the public release repository.

## Connect the repository

1. Sign in to Codemagic using a personal account.
2. Connect GitHub and authorize access to the private `veehicee1/Vicora` repository.
3. Add `veehicee1/Vicora` as an application.
4. In the branch selector, choose `fix/codemagic-main-android-test` (or `main` after this change is merged).
5. Select **Check for configuration file** so Codemagic reads the root `codemagic.yaml`.
6. Confirm the workflow `vicora-android-test` appears.

## Free-use safeguards

- Use only the personal Free allowance shown in your Codemagic account.
- The workflow selects `mac_mini_m2`; do not switch to a paid runner.
- Do not add a payment card, enable billing, upgrade, or create a Team.
- If Codemagic displays a payment prompt or says the free allowance is unavailable, stop and do not start a build.
- Free minutes and eligibility are controlled by Codemagic and may change; check the allowance displayed in your account before starting.

## What a successful build proves

It proves both APKs compiled and were attached as downloadable artifacts. It does not prove installation, device compatibility, server pairing, offline hosting, or cross-device synchronisation. Those still require testing on actual devices after downloading the APKs.
