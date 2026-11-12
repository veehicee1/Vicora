package org.gtmc.cbt;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.UUID;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.net.ssl.HttpsURLConnection;

/**
 * Pairs this Android Host with the trusted Windows CBT Server.
 * The bearer token is encrypted with a key held by Android Keystore.
 */
public final class AndroidHostPairing {
    private static final String KEY_ALIAS = "gtmc_android_host_pairing_v1";
    private static final String PREFS = "gtmc_android_host_secure";
    private static final String SECRET_KEY = "pairing_record";
    private static final int MAX_RESPONSE_BYTES = 64 * 1024;

    private AndroidHostPairing() { }

    public static synchronized JSONObject pair(Context context, String serverBaseUrl,
                                                 String oneTimeCode, String schoolCode) throws Exception {
        if (serverBaseUrl == null || !serverBaseUrl.startsWith("https://")) {
            throw new IllegalArgumentException("A trusted HTTPS server address is required.");
        }
        String deviceId = getOrCreateDeviceId(context);
        JSONObject request = new JSONObject();
        request.put("pairing_code", oneTimeCode);
        request.put("school_code", schoolCode == null ? "" : schoolCode.trim().toUpperCase());
        request.put("device_id", deviceId);
        request.put("label", "VICORA Android Host");

        URL url = new URL(serverBaseUrl.replaceAll("/+$", "") + "/api/android-host/pair");
        HttpsURLConnection connection = (HttpsURLConnection) url.openConnection();
        connection.setRequestMethod("POST");
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(15000);
        connection.setInstanceFollowRedirects(false);
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        connection.setRequestProperty("Accept", "application/json");
        byte[] body = request.toString().getBytes(StandardCharsets.UTF_8);
        connection.setFixedLengthStreamingMode(body.length);

        try {
            try (OutputStream output = connection.getOutputStream()) {
                output.write(body);
            }
            int status = connection.getResponseCode();
            InputStream stream = status >= 200 && status < 300
                    ? connection.getInputStream() : connection.getErrorStream();
            String responseText = readBounded(stream);
            JSONObject response = new JSONObject(responseText);
            if (status < 200 || status >= 300 || !response.optBoolean("ok", false)) {
                String message = response.optString("error", "Windows Server rejected pairing (HTTP " + status + ").");
                throw new IllegalStateException(message);
            }
            String returnedId = response.optString("device_id", "");
            String token = response.optString("device_token", "");
            if (!deviceId.equals(returnedId) || token.length() < 32) {
                throw new IllegalStateException("The server returned an invalid device credential.");
            }
            JSONObject record = new JSONObject();
            record.put("device_id", deviceId);
            record.put("school_code", schoolCode == null ? "" : schoolCode.trim().toUpperCase());
            record.put("device_token", token);
            record.put("server_url", serverBaseUrl.replaceAll("/+$", ""));
            saveEncrypted(context, record.toString());
            AndroidHostSyncScheduler.schedule(context);
            return record;
        } finally {
            connection.disconnect();
        }
    }

    private static String getOrCreateDeviceId(Context context) throws Exception {
        SharedPreferences identity = context.getSharedPreferences("gtmc_android_host_identity", Context.MODE_PRIVATE);
        String id = identity.getString("device_id", "");
        if (id.isEmpty()) {
            id = UUID.randomUUID().toString();
            identity.edit().putString("device_id", id).commit();
        }
        return id;
    }

    public static synchronized JSONObject getPairing(Context context) throws Exception {
        return readEncrypted(context);
    }

    public static synchronized void clearPairing(Context context) {
        AndroidHostSyncScheduler.cancel(context);
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().remove(SECRET_KEY).apply();
    }

    private static String readBounded(InputStream stream) throws Exception {
        if (stream == null) return "{}";
        try (InputStream input = stream; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096];
            int count;
            while ((count = input.read(buffer)) != -1) {
                if (output.size() + count > MAX_RESPONSE_BYTES) {
                    throw new IllegalStateException("Server response exceeded the allowed size.");
                }
                output.write(buffer, 0, count);
            }
            return output.toString("UTF-8");
        }
    }

    private static SecretKey getOrCreateKey() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        java.security.Key existing = store.getKey(KEY_ALIAS, null);
        if (existing instanceof SecretKey) return (SecretKey) existing;

        KeyGenerator generator = KeyGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build());
        return generator.generateKey();
    }

    private static void saveEncrypted(Context context, String value) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey());
        byte[] encrypted = cipher.doFinal(value.getBytes(StandardCharsets.UTF_8));
        byte[] iv = cipher.getIV();
        byte[] packed = new byte[iv.length + encrypted.length];
        System.arraycopy(iv, 0, packed, 0, iv.length);
        System.arraycopy(encrypted, 0, packed, iv.length, encrypted.length);
        String encoded = Base64.encodeToString(packed, Base64.NO_WRAP);
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString(SECRET_KEY, encoded).apply();
    }

    private static JSONObject readEncrypted(Context context) throws Exception {
        SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String encoded = prefs.getString(SECRET_KEY, null);
        if (encoded == null) return null;
        byte[] packed = Base64.decode(encoded, Base64.NO_WRAP);
        if (packed.length < 29) throw new IllegalStateException("Stored Android Host credential is invalid.");
        byte[] iv = new byte[12];
        byte[] encrypted = new byte[packed.length - iv.length];
        System.arraycopy(packed, 0, iv, 0, iv.length);
        System.arraycopy(packed, iv.length, encrypted, 0, encrypted.length);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), new GCMParameterSpec(128, iv));
        return new JSONObject(new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8));
    }
}
