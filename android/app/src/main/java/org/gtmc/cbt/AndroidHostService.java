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

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;

/** Keeps the phone-hosted CBT process alive while an examination is being hosted. */
public final class AndroidHostService extends Service {
    private static final String CHANNEL = "gtmc_exam_host";
    private static final int NOTIFICATION_ID = 8766;
    private final Handler syncHandler = new Handler(Looper.getMainLooper());
    private final Runnable syncPulse = new Runnable() {
        @Override public void run() {
            AndroidHostSyncScheduler.enqueueNow(AndroidHostService.this);
            syncHandler.postDelayed(this, 30_000L);
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL, "GTMC examination hosting", NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Shows while this phone is hosting student examinations.");
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) manager.createNotificationChannel(channel);
        }
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pending = PendingIntent.getActivity(this, 0, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? new Notification.Builder(this, CHANNEL)
                : new Notification.Builder(this);
        Notification notification = builder
                .setSmallIcon(android.R.drawable.stat_sys_upload)
                .setContentTitle("GTMC CBT Host is running")
                .setContentText("Keep this phone powered and connected during the examination.")
                .setContentIntent(pending)
                .setOngoing(true)
                .build();
        startForeground(NOTIFICATION_ID, notification);
        syncHandler.post(syncPulse);
    }

    @Override public void onDestroy() {
        syncHandler.removeCallbacks(syncPulse);
        super.onDestroy();
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        restartEmbeddedHost();
        return START_STICKY;
    }

    private void restartEmbeddedHost() {
        new Thread(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                String dataDir = getFilesDir().getAbsolutePath() + "/gtmc-cbt-data";
                String webDir = new File(getFilesDir(), "web").getAbsolutePath();
                Python.getInstance().getModule("android_server")
                        .callAttr("start_server", dataDir, webDir, "0.0.0.0");
            } catch (Exception ex) {
                android.util.Log.e("GTMC-Host", "Could not restore the Android CBT host after process restart.", ex);
            }
        }, "gtmc-host-restart").start();
    }

    @Override public IBinder onBind(Intent intent) { return null; }
}
