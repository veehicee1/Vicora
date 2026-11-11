package org.gtmc.cbt;

import android.content.Context;

import androidx.annotation.NonNull;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

import com.chaquo.python.android.AndroidPlatform;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

import org.json.JSONObject;

/** Runs a bounded HTTPS sync batch; pending records remain in SQLite until acknowledged. */
public final class AndroidHostSyncWorker extends Worker {
    public AndroidHostSyncWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    @NonNull
    @Override
    public Result doWork() {
        try {
            JSONObject pairing = AndroidHostPairing.getPairing(getApplicationContext());
            if (pairing == null) return Result.success();
            if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
            String dataDir = getApplicationContext().getFilesDir().getAbsolutePath() + "/gtmc-cbt-data";
            PyObject module = Python.getInstance().getModule("android_sync");
            boolean complete = module.callAttr("sync_once", dataDir,
                    pairing.getString("server_url"), pairing.getString("device_id"),
                    pairing.getString("device_token")).toBoolean();
            return complete ? Result.success() : Result.retry();
        } catch (Exception ex) {
            return Result.retry();
        }
    }
}
