package org.gtmc.cbt;

import android.content.Context;

import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.ExistingWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.OneTimeWorkRequest;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;

import java.util.concurrent.TimeUnit;

/** Network-constrained, duplicate-safe background result synchronisation. */
public final class AndroidHostSyncScheduler {
    private static final String PERIODIC = "gtmc_android_host_result_sync";
    private static final String IMMEDIATE = "gtmc_android_host_result_sync_now";

    private AndroidHostSyncScheduler() { }

    private static Constraints constraints() {
        return new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build();
    }

    public static void schedule(Context context) {
        WorkManager manager = WorkManager.getInstance(context.getApplicationContext());
        PeriodicWorkRequest periodic = new PeriodicWorkRequest.Builder(
                AndroidHostSyncWorker.class, 15, TimeUnit.MINUTES)
                .setConstraints(constraints())
                .build();
        manager.enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.KEEP, periodic);
        enqueueNow(context);
    }

    public static void enqueueNow(Context context) {
        OneTimeWorkRequest request = new OneTimeWorkRequest.Builder(AndroidHostSyncWorker.class)
                .setConstraints(constraints())
                .setBackoffCriteria(androidx.work.BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build();
        WorkManager.getInstance(context.getApplicationContext())
                .enqueueUniqueWork(IMMEDIATE, ExistingWorkPolicy.KEEP, request);
    }

    public static void cancel(Context context) {
        WorkManager.getInstance(context.getApplicationContext()).cancelUniqueWork(PERIODIC);
        WorkManager.getInstance(context.getApplicationContext()).cancelUniqueWork(IMMEDIATE);
    }
}
