package org.gtmc.cbt;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;

/** Keeps the embedded CBT process alive in both standalone and LAN-host modes. */
public final class AndroidHostService extends Service {
    public static final String EXTRA_MODE = "vicora.server.mode";
    private static final String PREFS = "vicora_host_service";
    private static final String CHANNEL = "vicora_exam_host";
    private static final int NOTIFICATION_ID = 8766;
    private final Handler syncHandler = new Handler(Looper.getMainLooper());
    private PowerManager.WakeLock hostWakeLock;
    private final Runnable syncPulse = new Runnable() {
        @Override public void run() {
            if ("host".equals(getSavedMode())) AndroidHostSyncScheduler.enqueueNow(AndroidHostService.this);
            syncHandler.postDelayed(this, 30_000L);
        }
    };

    private String getSavedMode() {
        return getSharedPreferences(PREFS, MODE_PRIVATE).getString(EXTRA_MODE, "host");
    }

    @Override public void onCreate() {
        super.onCreate();
        PowerManager power = (PowerManager) getSystemService(POWER_SERVICE);
        if (power != null) {
            hostWakeLock = power.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "VICORA:CBTHost");
            hostWakeLock.setReferenceCounted(false);
            hostWakeLock.acquire();
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(CHANNEL,
                    "VICORA CBT server", NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Keeps the VICORA CBT server available while the app is in the background.");
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) manager.createNotificationChannel(channel);
        }
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pending = PendingIntent.getActivity(this, 0, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        startForeground(NOTIFICATION_ID, builder
                .setSmallIcon(android.R.drawable.stat_sys_upload)
                .setContentTitle("VICORA CBT server is running")
                .setContentText("Keep this phone powered while using local examinations.")
                .setContentIntent(pending).setOngoing(true).build());
        syncHandler.post(syncPulse);
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && intent.hasExtra(EXTRA_MODE)) {
            getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                    .putString(EXTRA_MODE, intent.getStringExtra(EXTRA_MODE)).apply();
        }
        restartEmbeddedHost();
        return START_STICKY;
    }

    private void restartEmbeddedHost() {
        new Thread(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                String dataDir = getFilesDir().getAbsolutePath() + "/gtmc-cbt-data";
                String webDir = new File(getFilesDir(), "web").getAbsolutePath();
                String mode = getSavedMode();
                String bindHost = "host".equals(mode) ? "0.0.0.0" : "127.0.0.1";
                Python.getInstance().getModule("android_server")
                        .callAttr("start_server", dataDir, webDir, bindHost, 8765,
                                getSharedPreferences(MainActivity.class.getSimpleName() + "_preferences", MODE_PRIVATE)
                                        .getString("school_name", ""));
            } catch (Throwable ex) {
                android.util.Log.e("VICORA-Host", "Could not restore the embedded CBT server.", ex);
            }
        }, "vicora-host-restart").start();
    }

    @Override public void onDestroy() {
        syncHandler.removeCallbacks(syncPulse);
        if (hostWakeLock != null && hostWakeLock.isHeld()) hostWakeLock.release();
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }
}