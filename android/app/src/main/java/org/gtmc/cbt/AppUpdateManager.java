package org.gtmc.cbt;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.widget.Toast;
import androidx.core.content.FileProvider;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Locale;

public final class AppUpdateManager {
    private static final String RELEASE_API =
        "https://api.github.com/repos/veehicee1/VICORA-Releases/releases/latest";
    private static final String PREFS = "vicora_app_updates";
    private static final long CHECK_INTERVAL_MS = 24L * 60L * 60L * 1000L;
    private static final int MAX_APK_BYTES = 150 * 1024 * 1024;

    private AppUpdateManager() { }

    public static void checkForUpdates(Activity activity, boolean manual) {
        // Debug APKs are deliberately excluded: their temporary CI signing
        // certificate cannot safely update a permanently signed release app.
        if (BuildConfig.DEBUG) {
            if (manual) Toast.makeText(activity,
                "Automatic updates are available in the official signed release app.",
                Toast.LENGTH_LONG).show();
            return;
        }
        long last = activity.getSharedPreferences(PREFS, 0).getLong("last_check", 0L);
        if (!manual && System.currentTimeMillis() - last < CHECK_INTERVAL_MS) return;

        new Thread(() -> {
            try {
                JSONObject release = new JSONObject(readText(RELEASE_API));
                if (release.optBoolean("draft", true) || release.optBoolean("prerelease", true)) {
                    throw new IllegalStateException("No stable release is available.");
                }
                String tag = release.optString("tag_name", "");
                String latestVersion = tag.replaceFirst("^[vV]", "");
                String currentVersion = BuildConfig.VERSION_NAME.split("-", 2)[0];
                if (compareVersions(latestVersion, currentVersion) <= 0) {
                    activity.getSharedPreferences(PREFS, 0).edit()
                        .putLong("last_check", System.currentTimeMillis()).apply();
                    if (manual) activity.runOnUiThread(() -> Toast.makeText(activity,
                        "VICORA CBT is already up to date.", Toast.LENGTH_LONG).show());
                    return;
                }

                String assetName = "app-" + ("admin".equals(BuildConfig.FLAVOR)
                    ? "admin" : "examination") + "-release.apk";
                JSONArray assets = release.optJSONArray("assets");
                JSONObject selected = null;
                if (assets != null) {
                    for (int i = 0; i < assets.length(); i++) {
                        JSONObject item = assets.optJSONObject(i);
                        if (item != null && assetName.equals(item.optString("name"))) {
                            selected = item;
                            break;
                        }
                    }
                }
                if (selected == null) throw new IllegalStateException("The correct app update is not attached to this release.");
                String downloadUrl = selected.optString("browser_download_url", "");
                String digest = selected.optString("digest", "");
                if (!downloadUrl.startsWith("https://github.com/")
                        || !digest.toLowerCase(Locale.ROOT).matches("sha256:[0-9a-f]{64}")) {
                    throw new IllegalStateException("The release download is missing its trusted SHA-256 checksum.");
                }

                File updateDir = new File(activity.getCacheDir(), "updates");
                if (!updateDir.exists() && !updateDir.mkdirs()) throw new IllegalStateException("Cannot create update folder.");
                File apk = new File(updateDir, assetName);
                downloadAndVerify(downloadUrl, apk, digest.substring("sha256:".length()));
                activity.getSharedPreferences(PREFS, 0).edit()
                    .putString("pending_apk", apk.getAbsolutePath())
                    .putString("pending_version", latestVersion)
                    .putLong("last_check", System.currentTimeMillis()).apply();
                activity.runOnUiThread(() -> Toast.makeText(activity,
                    "VICORA CBT " + latestVersion + " has been downloaded. Close and reopen the app to install it.",
                    Toast.LENGTH_LONG).show());
            } catch (Exception ex) {
                if (manual) activity.runOnUiThread(() -> Toast.makeText(activity,
                    "Update check failed: " + (ex.getMessage() == null ? "Please try again later." : ex.getMessage()),
                    Toast.LENGTH_LONG).show());
            }
        }, "vicora-update-check").start();
    }

    public static void installPendingUpdate(Activity activity) {
        android.content.SharedPreferences prefs = activity.getSharedPreferences(PREFS, 0);
        String path = prefs.getString("pending_apk", "");
        if (path == null || path.isEmpty()) return;
        if (prefs.getLong("snooze_install_until", 0L) > System.currentTimeMillis()) return;
        String pendingVersion = prefs.getString("pending_version", "");
        String installedVersion = BuildConfig.VERSION_NAME.split("-", 2)[0];
        if (!pendingVersion.isEmpty() && compareVersions(pendingVersion, installedVersion) <= 0) {
            new File(path).delete();
            prefs.edit().remove("pending_apk").remove("pending_version").remove("snooze_install_until").apply();
            return;
        }
        File apk = new File(path);
        if (!apk.isFile() || apk.length() == 0) {
            prefs.edit().remove("pending_apk").remove("pending_version").apply();
            return;
        }
        if (Build.VERSION.SDK_INT >= 26
                && !activity.getPackageManager().canRequestPackageInstalls()) {
            if (prefs.getBoolean("awaiting_install_permission", false)) {
                prefs.edit().putBoolean("awaiting_install_permission", false)
                    .putLong("snooze_install_until", System.currentTimeMillis() + CHECK_INTERVAL_MS).apply();
                return;
            }
            new AlertDialog.Builder(activity)
                .setTitle("VICORA CBT update is ready")
                .setMessage("Android needs your permission to install the downloaded official update. Your CBT records are kept by the app.")
                .setPositiveButton("Allow installation", (dialog, which) -> {
                    prefs.edit().putBoolean("awaiting_install_permission", true).apply();
                    Intent settings = new Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        Uri.parse("package:" + activity.getPackageName()));
                    activity.startActivity(settings);
                })
                .setNegativeButton("Later", (dialog, which) -> prefs.edit()
                    .putLong("snooze_install_until", System.currentTimeMillis() + CHECK_INTERVAL_MS).apply())
                .show();
            return;
        }
        prefs.edit().remove("awaiting_install_permission")
            .putLong("snooze_install_until", System.currentTimeMillis() + CHECK_INTERVAL_MS).apply();
        try {
            Uri uri = FileProvider.getUriForFile(activity,
                BuildConfig.APPLICATION_ID + ".fileprovider", apk);
            Intent install = new Intent(Intent.ACTION_INSTALL_PACKAGE);
            install.setDataAndType(uri, "application/vnd.android.package-archive");
            install.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            activity.startActivity(install);
        } catch (Exception ex) {
            Toast.makeText(activity, "Could not open Android installer: " + ex.getMessage(),
                Toast.LENGTH_LONG).show();
        }
    }

    private static String readText(String address) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(address).openConnection();
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(20000);
        connection.setRequestProperty("Accept", "application/vnd.github+json");
        connection.setRequestProperty("User-Agent", "VICORA-CBT-Android-Updater");
        try {
            int status = connection.getResponseCode();
            if (status != 200) throw new IllegalStateException("Release service returned HTTP " + status);
            try (InputStream input = connection.getInputStream()) {
                java.io.ByteArrayOutputStream output = new java.io.ByteArrayOutputStream();
                byte[] buffer = new byte[8192];
                int count;
                while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
                return output.toString("UTF-8");
            }
        } finally { connection.disconnect(); }
    }

    private static void downloadAndVerify(String address, File destination, String expectedHash) throws Exception {
        File temporary = new File(destination.getParentFile(), destination.getName() + ".part");
        HttpURLConnection connection = (HttpURLConnection) new URL(address).openConnection();
        connection.setConnectTimeout(20000);
        connection.setReadTimeout(30000);
        connection.setInstanceFollowRedirects(true);
        connection.setRequestProperty("User-Agent", "VICORA-CBT-Android-Updater");
        try {
            int status = connection.getResponseCode();
            if (status != 200) throw new IllegalStateException("APK download returned HTTP " + status);
            long declared = connection.getContentLengthLong();
            if (declared > MAX_APK_BYTES) throw new IllegalStateException("APK is larger than the allowed update size.");
            MessageDigest sha = MessageDigest.getInstance("SHA-256");
            long total = 0;
            try (InputStream input = connection.getInputStream();
                 FileOutputStream output = new FileOutputStream(temporary)) {
                byte[] buffer = new byte[16384];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    total += count;
                    if (total > MAX_APK_BYTES) throw new IllegalStateException("APK is larger than the allowed update size.");
                    sha.update(buffer, 0, count);
                    output.write(buffer, 0, count);
                }
                output.getFD().sync();
            }
            StringBuilder actual = new StringBuilder();
            for (byte value : sha.digest()) actual.append(String.format(Locale.ROOT, "%02x", value & 0xff));
            if (!actual.toString().equalsIgnoreCase(expectedHash)) {
                throw new SecurityException("The downloaded update failed its SHA-256 check.");
            }
            if (destination.exists() && !destination.delete()) throw new IllegalStateException("Cannot replace old update file.");
            if (!temporary.renameTo(destination)) throw new IllegalStateException("Cannot save the verified update.");
        } catch (Exception ex) {
            if (temporary.exists()) temporary.delete();
            throw ex;
        } finally { connection.disconnect(); }
    }

    private static int compareVersions(String left, String right) {
        String[] a = left.split("\\.");
        String[] b = right.split("\\.");
        int length = Math.max(a.length, b.length);
        for (int i = 0; i < length; i++) {
            int x = i < a.length ? leadingNumber(a[i]) : 0;
            int y = i < b.length ? leadingNumber(b[i]) : 0;
            if (x != y) return Integer.compare(x, y);
        }
        return 0;
    }

    private static int leadingNumber(String value) {
        String digits = value.replaceFirst("^([0-9]+).*$", "$1");
        try { return Integer.parseInt(digits); }
        catch (NumberFormatException ex) { return 0; }
    }
}
