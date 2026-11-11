# GTMC CBT Android automatic updates

Both the Admin and Examination release apps check the official GitHub Releases endpoint when opened. A successful check is cached for 24 hours; the user can also choose **Check for updates** from the app menu.

## Update flow

1. The app checks the latest stable release over HTTPS.
2. It selects only the APK matching the installed app role (Admin or Examination).
3. It downloads the APK into the app's private cache.
4. It verifies the release's published SHA-256 digest before making the APK available to Android's installer.
5. The downloaded update is staged and the app asks Android to install it the next time the app is opened. Android displays its normal installation confirmation.
6. Android enforces the package signing-certificate match. An update signed with a different key is rejected by Android.

The app does not install an APK silently, bypass Android's security prompts, or accept an APK without the expected checksum. The updater does not copy, replace, or clear the app's private CBT database.

## Release requirements

- Publish a stable, non-draft GitHub Release with a higher semantic version tag, such as `v1.0.4`.
- Attach both exact release asset names: `app-admin-release.apk` and `app-examination-release.apk`.
- Keep using the same permanent school Android signing key for every release. Never rotate or replace that key for an in-place update.
- Ensure GitHub reports a SHA-256 asset digest for each APK. The updater fails closed if the digest is missing or does not match.
- Release APKs must be built by the signed release workflow. Debug APKs intentionally do not run the updater because their temporary debug signing certificates cannot safely update the signed school release.

## Network and device behaviour

- Internet access is required to check and download an update. Offline and school-LAN CBT use continues when the update service is unavailable.
- Automatic checks happen at app launch, at most once every 24 hours. A manual check is available in the app menu.
- The APK download happens in the background. Installation is deferred to the next app opening to avoid interrupting an examination already in progress.
- On Android 8 and later, the user may need to allow this app to install updates from this source once. Android still asks for final approval.
- If no newer stable release exists, the app remains unchanged.

## Verification boundary

CI can compile the two APK flavours and validate source/configuration. A real-device test is still required to verify the download, checksum, Android installer prompt, signature continuity, and preservation of existing local records. Do not use a live examination device for first-time update testing.
