package org.gtmc.cbt;
import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.content.ClipboardManager;
import android.content.ClipData;
import android.app.AlertDialog;
import android.os.Bundle;
import android.view.Menu;
import android.view.MenuItem;
import android.view.ViewGroup;
import android.webkit.WebChromeClient;
import android.webkit.ValueCallback;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.Toast;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Button;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.NetworkInterface;
import java.net.Inet4Address;
import java.util.Enumeration;
import java.util.ArrayList;
import java.util.Collections;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

public class MainActivity extends Activity {
    private static final String LOCAL_URL = "http://127.0.0.1:8765/";
    private WebView webView;
    private ValueCallback<Uri[]> filePathCallback;
    private static final int FILE_CHOOSER_REQUEST_CODE = 4107;
    private String currentMode = "standalone";
    private boolean isAdminApp() { return "admin".equals(BuildConfig.FLAVOR); }
    private String currentBaseUrl() {
        if ("standalone".equals(currentMode) || "host".equals(currentMode)) return LOCAL_URL;
        String url = getPreferences(0).getString("server_url", "");
        if (!url.isEmpty() && !url.endsWith("/")) url += "/";
        return url;
    }
    private String appHomeUrl() { return currentBaseUrl() + (isAdminApp() ? "admin" : ""); }

    // Remote server addresses must use HTTPS. Plain HTTP is permitted only
    // for loopback/private school LAN addresses (including local DNS names).
    private boolean isLocalNetworkHost(String host) {
        if (host == null) return false;
        String h = host.toLowerCase(java.util.Locale.ROOT);
        if (h.equals("localhost") || h.endsWith(".local") || h.endsWith(".lan")) return true;
        if (h.startsWith("[") && h.endsWith("]")) {
            String v6 = h.substring(1, h.length() - 1);
            return v6.equals("::1") || v6.startsWith("fc") || v6.startsWith("fd") || v6.startsWith("fe80:");
        }
        String[] parts = h.split("\\.");
        if (parts.length != 4) return false;
        try {
            int a = Integer.parseInt(parts[0]), b = Integer.parseInt(parts[1]);
            int d = Integer.parseInt(parts[2]), e = Integer.parseInt(parts[3]);
            if (a < 0 || a > 255 || b < 0 || b > 255 || d < 0 || d > 255 || e < 0 || e > 255) return false;
            return a == 10 || a == 127 || (a == 192 && b == 168)
                || (a == 172 && b >= 16 && b <= 31) || (a == 169 && b == 254);
        } catch (NumberFormatException ex) {
            return false;
        }
    }

    private boolean isAllowedServerUrl(String value) {
        android.net.Uri uri = android.net.Uri.parse(value);
        String scheme = uri.getScheme();
        if ("https".equalsIgnoreCase(scheme)) return uri.getHost() != null;
        return "http".equalsIgnoreCase(scheme) && isLocalNetworkHost(uri.getHost());
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        if (getActionBar() != null) getActionBar().setTitle(isAdminApp() ? "VICORA CBT Admin" : "VICORA CBT Examination");
        webView = new WebView(this);
        webView.setLayoutParams(new ViewGroup.LayoutParams(-1, -1));
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setDatabaseEnabled(true);
        webView.getSettings().setSupportZoom(false);
        webView.setWebViewClient(new WebViewClient());
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                    FileChooserParams params) {
                if (filePathCallback != null) {
                    filePathCallback.onReceiveValue(null);
                    filePathCallback = null;
                }
                filePathCallback = callback;
                try {
                    Intent intent = params.createIntent();
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST_CODE);
                    return true;
                } catch (Exception ex) {
                    filePathCallback = null;
                    callback.onReceiveValue(null);
                    Toast.makeText(MainActivity.this,
                        "Unable to open the file picker. Please try again.",
                        Toast.LENGTH_LONG).show();
                    return false;
                }
            }
        });
        setContentView(webView);
        AppUpdateManager.installPendingUpdate(this);
        AppUpdateManager.checkForUpdates(this, false);
        String mode = getPreferences(0).getString("mode", "");
        String savedServerUrl = getPreferences(0).getString("server_url", "");
        if ("school".equals(mode) && !savedServerUrl.isEmpty()) {
            if (isAllowedServerUrl(savedServerUrl)) {
                currentMode = "school"; loadUrl(appHomeUrl()); return;
            }
            getPreferences(0).edit().remove("mode").remove("server_url").apply();
        }
        if ("standalone".equals(mode)) startStandalone(); else if ("host".equals(mode) && isAdminApp()) { currentMode = "host"; startStandalone(); } else chooseMode();
    }
    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }

    private void addModeButton(LinearLayout layout, AlertDialog dialog, String label, Runnable action) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setTextSize(16);
        button.setMinHeight(dp(52));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.topMargin = dp(8);
        layout.addView(button, params);
        button.setOnClickListener(view -> {
            dialog.dismiss();
            action.run();
        });
    }

    private void chooseMode() {
        if (isAdminApp()) {
            LinearLayout choices = new LinearLayout(this);
            choices.setOrientation(LinearLayout.VERTICAL);
            choices.setPadding(dp(20), dp(8), dp(20), dp(12));

            TextView message = new TextView(this);
            message.setText("Host exams directly from this Android device over its hotspot or Wi-Fi. This uses the database stored on this phone. To use the central school database, connect to the school server instead.");
            message.setTextSize(16);
            message.setPadding(0, dp(8), 0, dp(12));
            choices.addView(message, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

            ScrollView scroll = new ScrollView(this);
            scroll.setFillViewport(true);
            scroll.addView(choices);

            AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("VICORA CBT Admin")
                .setView(scroll)
                .setNegativeButton("Exit", (d, which) -> { stopHostingServiceAndServer(); finish(); })
                .create();

            addModeButton(choices, dialog, "Host Exam on This Device (Wi-Fi / Hotspot)", () -> {
                currentMode = "host";
                startStandalone();
            });
            addModeButton(choices, dialog, "Connect to School Server", () -> enterServerAddress());
            addModeButton(choices, dialog, "Standalone Offline (This Device Only)", () -> {
                currentMode = "standalone";
                startStandalone();
            });

            dialog.setCancelable(false);
            dialog.show();
        } else {
            new AlertDialog.Builder(this).setTitle("VICORA CBT Examination")
                .setMessage("Connect to the school's central server, or use a separate offline copy on this device.")
                .setPositiveButton("Connect to School Server", (d,w) -> enterServerAddress())
                .setNegativeButton("Standalone offline", (d,w) -> startStandalone())
                .setNeutralButton("Cancel", (d,w) -> finish()).show();
        }
    }
    private void startStandalone() {
        if (!"host".equals(currentMode)) currentMode = "standalone";
        final String requestedMode = currentMode;
        String schoolName = getPreferences(0).getString("school_name", "");
        if ("host".equals(requestedMode) && schoolName.trim().isEmpty()) {
            EditText school = new EditText(this);
            school.setSingleLine(true);
            school.setHint("Enter the full school name");
            school.setTextSize(17);
            new AlertDialog.Builder(this)
                .setTitle("Set up VICORA CBT Host")
                .setMessage("Enter the school's name. It will appear on the examination login page and school reports.")
                .setView(school)
                .setCancelable(false)
                .setPositiveButton("Save and Start", (dialog, which) -> {
                    String value = school.getText().toString().trim().replaceAll("\\s+", " ");
                    if (value.isEmpty()) {
                        Toast.makeText(this, "School name is required.", Toast.LENGTH_LONG).show();
                        startStandalone();
                        return;
                    }
                    value = value.length() > 120 ? value.substring(0, 120) : value;
                    getPreferences(0).edit().putString("school_name", value).apply();
                    startStandaloneWithSchoolName(requestedMode, value);
                })
                .setNegativeButton("Cancel", (dialog, which) -> chooseMode())
                .show();
            return;
        }
        startStandaloneWithSchoolName(requestedMode, schoolName);
    }

    private void startStandaloneWithSchoolName(String requestedMode, String schoolName) {
        getWindow().clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        Toast.makeText(this, "host".equals(requestedMode)
            ? "Starting VICORA Wi-Fi / hotspot host…"
            : "Starting offline CBT…", Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
                copyAssetFolder("web", new File(getFilesDir(), "web"));
                Python.getInstance().getModule("android_server").callAttr("start_server",
                    getFilesDir().getAbsolutePath() + "/gtmc-cbt-data",
                    new File(getFilesDir(), "web").getAbsolutePath(),
                    "host".equals(requestedMode) ? "0.0.0.0" : "127.0.0.1",
                    8765,
                    schoolName == null ? "" : schoolName);
                runOnUiThread(() -> {
                    currentMode = requestedMode;
                    getPreferences(0).edit().putString("mode",requestedMode).apply();
                    if ("host".equals(requestedMode)) startHostingService(); else stopHostingService();
                    loadUrl(appHomeUrl());
                    if ("host".equals(requestedMode)) showStudentAccess();
                });
            } catch (Exception ex) {
                runOnUiThread(() -> new AlertDialog.Builder(this).setTitle("Could not start VICORA CBT")
                    .setMessage(ex.getMessage() == null ? "Unknown startup error" : ex.getMessage())
                    .setPositiveButton("Retry",(d,w)->startStandalone()).setNegativeButton("Close",(d,w)->finish()).show());
            }
        }).start();
    }
    private void enterServerAddress() {
        EditText address = new EditText(this); address.setSingleLine(true);
        address.setHint("http://192.168.1.10:8000/");
        address.setText(getPreferences(0).getString("server_url",""));
        new AlertDialog.Builder(this).setTitle("School server address")
            .setMessage("Enter the CBT server address on the school's Wi-Fi/LAN.").setView(address)
            .setPositiveButton("Connect",(d,w)->{
                String url=address.getText().toString().trim();
                if (!isAllowedServerUrl(url)) {
                    Toast.makeText(this,"Use HTTPS for remote servers. HTTP is allowed only on a private school LAN.",Toast.LENGTH_LONG).show(); enterServerAddress(); return;
                }
                if (!url.endsWith("/")) url += "/";
                currentMode="school";
                stopHostingServiceAndServer();
                getPreferences(0).edit().putString("mode","school").putString("server_url",url).apply();
                loadUrl(appHomeUrl());
            }).setNegativeButton("Back",(d,w)->chooseMode()).show();
    }
    private void copyAssetFolder(String assetPath, File destination) throws IOException {
        String[] children=getAssets().list(assetPath);
        if (children==null || children.length==0) {
            File parent=destination.getParentFile(); if(parent!=null && !parent.exists()) parent.mkdirs();
            try(InputStream in=getAssets().open(assetPath); FileOutputStream out=new FileOutputStream(destination)) {
                byte[] buffer=new byte[8192]; int count; while((count=in.read(buffer))>0) out.write(buffer,0,count);
            } return;
        }
        if(!destination.exists() && !destination.mkdirs()) throw new IOException("Could not create web asset folder: "+destination);
        for(String child:children) copyAssetFolder(assetPath+"/"+child,new File(destination,child));
    }
    private void loadUrl(String url) { webView.loadUrl(url); }

    @Override public boolean onCreateOptionsMenu(Menu menu) {
        menu.add("Check for updates");
        if (!isAdminApp()) return true;
        menu.add("Admin Console");
        menu.add("Student access URL");
        menu.add("Open Wi-Fi / Hotspot settings");
        menu.add("Change connection mode");
        menu.add("Reconnect");
        if ("host".equals(currentMode)) { menu.add("Pair with Windows Server"); menu.add("Sync results now"); menu.add("Sync status"); }
        return true;
    }

    private ArrayList<String> getLanAddresses() {
        ArrayList<String> addresses = new ArrayList<>();
        try {
            Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
            while (interfaces != null && interfaces.hasMoreElements()) {
                NetworkInterface network = interfaces.nextElement();
                if (!network.isUp() || network.isLoopback()) continue;
                Enumeration<java.net.InetAddress> values = network.getInetAddresses();
                while (values.hasMoreElements()) {
                    java.net.InetAddress address = values.nextElement();
                    if (address instanceof Inet4Address && !address.isLoopbackAddress() && !address.isLinkLocalAddress()) {
                        String value = address.getHostAddress();
                        if (!addresses.contains(value)) addresses.add(value);
                    }
                }
            }
        } catch (Exception ignored) { }
        Collections.sort(addresses);
        return addresses;
    }

    private void showStudentAccess() {
        ArrayList<String> addresses = getLanAddresses();
        StringBuilder message = new StringBuilder();
        message.append("The CBT server is running on this device. Students must join the same Wi-Fi network or this phone's hotspot, then open one of these addresses in Chrome:");
        if (addresses.isEmpty()) {
            message.append("\n\nNo Wi-Fi/hotspot IP is available yet. Turn on the hotspot or connect to Wi-Fi, then tap Student access URL again.");
        } else {
            for (String ip : addresses) message.append("\n\nhttp://").append(ip).append(":8765/");
        }
        message.append("\n\nInternet is not required for local candidates. Keep this phone powered, connected to the school Wi-Fi/hotspot, and leave the VICORA Host notification active.");
        new AlertDialog.Builder(this).setTitle("VICORA Student Exam Link")
            .setMessage(message.toString())
            .setPositiveButton("Open Hotspot Settings", (dialog, which) -> openHotspotSettings())
            .setNegativeButton("Done", null)
            .setNeutralButton("Copy link", (dialog, which) -> {
                if (!addresses.isEmpty()) {
                    String link = "http://" + addresses.get(0) + ":8765/";
                    ClipboardManager clipboard = (ClipboardManager)getSystemService(CLIPBOARD_SERVICE);
                    if (clipboard != null) clipboard.setPrimaryClip(ClipData.newPlainText("VICORA student exam link", link));
                    Toast.makeText(this, "Student link copied", Toast.LENGTH_SHORT).show();
                }
            }).show();
    }

    private void showWindowsServerPairing() {
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(20), dp(8), dp(20), dp(8));
        EditText server = new EditText(this);
        server.setSingleLine(true);
        server.setHint("https://your-secure-server.example/");
        server.setText(getPreferences(0).getString("android_sync_server_url", ""));
        form.addView(server);
        EditText code = new EditText(this);
        code.setSingleLine(true);
        code.setHint("One-time pairing code from Windows Admin");
        form.addView(code);
        new AlertDialog.Builder(this)
            .setTitle("Pair Android Host")
            .setMessage("Enter the HTTPS address of your Windows CBT Server and the one-time code generated in Admin Settings. Completed exam results will be transferred securely to the paired Windows host.")
            .setView(form)
            .setPositiveButton("Pair", (dialog, which) -> {
                String serverUrl = server.getText().toString().trim();
                String pairingCode = code.getText().toString().trim();
                android.net.Uri parsed = android.net.Uri.parse(serverUrl);
                if (!"https".equalsIgnoreCase(parsed.getScheme()) || parsed.getHost() == null
                        || parsed.getUserInfo() != null || parsed.getQuery() != null || parsed.getFragment() != null) {
                    Toast.makeText(this, "Use a valid HTTPS Windows Server address.", Toast.LENGTH_LONG).show();
                    return;
                }
                if (pairingCode.isEmpty()) {
                    Toast.makeText(this, "Enter the one-time pairing code.", Toast.LENGTH_LONG).show();
                    return;
                }
                if (serverUrl.endsWith("/")) serverUrl = serverUrl.substring(0, serverUrl.length() - 1);
                final String endpoint = serverUrl;
                final String secret = pairingCode;
                Toast.makeText(this, "Pairing with Windows Server…", Toast.LENGTH_SHORT).show();
                new Thread(() -> {
                    try {
                        AndroidHostPairing.pair(this, endpoint, secret);
                        Python.getInstance().getModule("android_sync").callAttr("reset_auth_errors",
                            getFilesDir().getAbsolutePath() + "/gtmc-cbt-data");
                        runOnUiThread(() -> {
                            getPreferences(0).edit().putString("android_sync_server_url", endpoint).apply();
                            AndroidHostSyncScheduler.schedule(this);
                            Toast.makeText(this, "Android Host paired. Completed results will sync automatically when internet is available.", Toast.LENGTH_LONG).show();
                        });
                    } catch (Exception ex) {
                        String message = ex.getMessage() == null ? "Pairing failed." : ex.getMessage();
                        runOnUiThread(() -> new AlertDialog.Builder(this).setTitle("Pairing failed")
                            .setMessage(message).setPositiveButton("OK", null).show());
                    }
                }).start();
            })
            .setNegativeButton("Cancel", null)
            .show();
    }

    private void showAndroidSyncStatus() {
        Toast.makeText(this, "Checking the Android result queue…", Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            try {
                String dataDir = getFilesDir().getAbsolutePath() + "/gtmc-cbt-data";
                String raw = Python.getInstance().getModule("android_sync")
                        .callAttr("local_status_json", dataDir).toString();
                org.json.JSONObject status = new org.json.JSONObject(raw);
                String message = "Total saved results: " + status.optInt("total", 0)
                    + "\nWaiting to sync: " + status.optInt("pending", 0)
                    + "\nCurrently syncing: " + status.optInt("syncing", 0)
                    + "\nRetrying: " + status.optInt("retry", 0)
                    + "\nSynchronised: " + status.optInt("synced", 0)
                    + "\nNeeds Admin review: " + status.optInt("conflict", 0)
                    + "\nAuthentication issue: " + status.optInt("auth_error", 0);
                runOnUiThread(() -> new AlertDialog.Builder(this).setTitle("Android result sync status")
                    .setMessage(message).setPositiveButton("Sync now", (d, w) -> AndroidHostSyncScheduler.enqueueNow(this))
                    .setNegativeButton("Close", null).show());
            } catch (Exception ex) {
                runOnUiThread(() -> new AlertDialog.Builder(this).setTitle("Sync status unavailable")
                    .setMessage(ex.getMessage() == null ? "Start Android Host mode first." : ex.getMessage())
                    .setPositiveButton("OK", null).show());
            }
        }).start();
    }

    private void startHostingService() {
        Intent intent = new Intent(this, AndroidHostService.class);
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) startForegroundService(intent);
        else startService(intent);
    }

    private void stopHostingService() {
        stopService(new Intent(this, AndroidHostService.class));
    }

    private void stopHostingServiceAndServer() {
        if (!Python.isStarted()) {
            stopHostingService();
            return;
        }
        new Thread(() -> {
            try {
                Python.getInstance().getModule("android_server").callAttr("stop_server");
            } catch (Exception ex) {
                android.util.Log.w("VICORA-Host", "Could not stop the local host cleanly.", ex);
            }
            runOnUiThread(this::stopHostingService);
        }, "vicora-stop-host").start();
    }

    private void openHotspotSettings() {
        try { startActivity(new Intent(android.provider.Settings.ACTION_WIRELESS_SETTINGS)); }
        catch (Exception ex) { startActivity(new Intent(android.provider.Settings.ACTION_WIFI_SETTINGS)); }
    }
    @Override public boolean onOptionsItemSelected(MenuItem item) {
        if ("Check for updates".contentEquals(item.getTitle())) {
            AppUpdateManager.checkForUpdates(this, true);
            return true;
        }
        if ("Admin Console".contentEquals(item.getTitle()) && isAdminApp()) {
            if ("school".equals(currentMode)) {
                new AlertDialog.Builder(this).setTitle("Open school Admin Console?")
                    .setMessage("Remote Admin access must be enabled by the school administrator. Use only the school's trusted LAN or HTTPS connection.")
                    .setPositiveButton("Continue",(d,w)->loadUrl(appHomeUrl())).setNegativeButton("Cancel",null).show();
            } else loadUrl(appHomeUrl());
            return true;
        }
        if ("Student access URL".contentEquals(item.getTitle()) && isAdminApp()) { showStudentAccess(); return true; }
        if ("Open Wi-Fi / Hotspot settings".contentEquals(item.getTitle()) && isAdminApp()) { openHotspotSettings(); return true; }
        if ("Change connection mode".contentEquals(item.getTitle()) && isAdminApp()) { chooseMode(); return true; }
        if ("Reconnect".contentEquals(item.getTitle()) && isAdminApp()) {
            if ("standalone".equals(currentMode) || "host".equals(currentMode)) startStandalone(); else loadUrl(appHomeUrl()); return true;
        }
        if ("Pair with Windows Server".contentEquals(item.getTitle()) && isAdminApp() && "host".equals(currentMode)) {
            showWindowsServerPairing(); return true;
        }
        if ("Sync status".contentEquals(item.getTitle()) && isAdminApp() && "host".equals(currentMode)) {
            showAndroidSyncStatus(); return true;
        }
        if ("Sync results now".contentEquals(item.getTitle()) && isAdminApp() && "host".equals(currentMode)) {
            AndroidHostSyncScheduler.enqueueNow(this);
            Toast.makeText(this, "Result synchronisation queued. Results remain safely stored until the Windows Server acknowledges them.", Toast.LENGTH_LONG).show();
            return true;
        }
        return super.onOptionsItemSelected(item);
    }
    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == FILE_CHOOSER_REQUEST_CODE) {
            if (filePathCallback != null) {
                Uri[] results = WebChromeClient.FileChooserParams.parseResult(resultCode, data);
                filePathCallback.onReceiveValue(results);
                filePathCallback = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override public void onBackPressed() {
        if(webView!=null && webView.canGoBack()) webView.goBack(); else super.onBackPressed();
    }
    @Override protected void onDestroy() {
        if (filePathCallback != null) {
            filePathCallback.onReceiveValue(null);
            filePathCallback = null;
        }
        if(webView!=null) { webView.stopLoading(); webView.destroy(); }
        super.onDestroy();
    }
}
