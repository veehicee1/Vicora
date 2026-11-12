# VICORA cloud Android test builds

The repository contains a Codemagic workflow for building the two Android test APKs without installing Android Studio, Java, Gradle, or the Android SDK on the owner's PC.

## Build outputs

- Admin: `android/app/build/outputs/apk/admin/debug/app-admin-debug.apk`
- Examination: `android/app/build/outputs/apk/examination/debug/app-examination-debug.apk`

These are debug/testing APKs, not production-signed releases. The workflow does not publish to Google Play or the public release repository.

## Account setup

1. Sign in to Codemagic using a personal account (not a Team account).
2. Connect GitHub and authorize access to the private `veehicee1/Vicora` repository using the GitHub account that has collaborator access.
3. Add the repository as an application.
4. Select branch `work/finish-vicora-platform` and let Codemagic detect `codemagic.yaml`.
5. Select workflow `vicora-android-test`.

## Strict no-payment rules

- Codemagic's current personal Free plan includes 500 macOS M2 build minutes each month. Free minutes are not available on Team accounts. Linux and Windows build machines are paid. See https://codemagic.io/pricing/ and https://docs.codemagic.io/billing/pricing/.
- This workflow explicitly selects `mac_mini_m2`, with a 60-minute job limit. Do not switch it to Linux or Windows.
- Do not enable billing, add a payment card, upgrade, or create a Team. If the account asks for payment or does not clearly show the personal Free plan, stop without starting a build.
- The free allowance is not a guarantee that the complete build will fit within one run. If minutes are exhausted, stop; do not enable paid usage.
- The GitHub repository remains private. No signing key, student database, production secret, or school data is required for debug APK builds.

## What a successful build proves

It proves that both APKs compiled and were attached as downloadable artifacts. It does not prove installation, device compatibility, server pairing, offline hosting, or cross-device synchronisation. Those still require testing on actual devices after downloading the APKs.
