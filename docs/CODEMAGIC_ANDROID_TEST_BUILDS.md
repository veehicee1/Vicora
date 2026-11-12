# VICORA cloud Android test builds

This repository includes a Codemagic workflow so Android test APKs can be built in the cloud. It avoids installing Android Studio, Java, Gradle, or the Android SDK on the owner's PC.

## What it builds

One cloud job builds both Android variants:

- Admin: `android/app/build/outputs/apk/admin/debug/app-admin-debug.apk`
- Examination: `android/app/build/outputs/apk/examination/debug/app-examination-debug.apk`

These are debug/testing APKs, not production-signed releases. The workflow does not publish to Google Play or upload to the public release repository.

## One-time account setup

1. Create/sign in to a Codemagic account at https://codemagic.io/.
2. Connect GitHub and authorize access to the private `veehicee1/Vicora` repository.
3. Add the repository as an application.
4. Select branch `work/finish-vicora-platform` and let Codemagic detect the root `codemagic.yaml`.
5. Select workflow `vicora-android-test` and start a manual build.

The workflow is restricted to the working branch so unrelated pushes do not start builds.

## Cost and privacy safeguards

- Check the current Codemagic account's included build minutes and machine eligibility before starting. Do not enable paid billing or upgrade.
- The workflow uses the macOS M2 machine type; if the account asks for a paid plan or payment method, stop and do not proceed.
- The source repository remains private; do not change its visibility.
- No signing key, student database, production secret, or school data is required for debug APK builds.
- Codemagic stores build artifacts according to its account retention policy. Download the APKs promptly after a successful build.

## Test limitation

A successful APK build proves compilation and artifact creation only. It does not prove installation, device compatibility, server pairing, offline hosting, or cross-device synchronisation. Those require actual device testing after downloading the APKs.
