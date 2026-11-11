# GTMC CBT Central Server — Network Setup Notes

This guide describes the current safe server configuration baseline. Remote access is **not enabled by default**.

## 1. Choose the school server computer

Use one designated Windows PC as the authoritative CBT server. Keep its power supply stable and prevent Windows from sleeping during examinations. The server owns the authoritative `cbt.db` file in its configured data directory.

The server can get its internet connection from any of these uplinks:

- School Wi-Fi
- Ethernet cable to the school router
- A phone's Wi-Fi hotspot
- USB tethering from a phone

The uplink method does not change the database or CBT client configuration. On the school LAN, client devices must be able to reach the server over the same local network.

## 2. Choosing the server from the desktop applications

On Windows, the Admin application offers two choices:

- **This PC is the central School Server** — starts or reuses the authoritative server on the designated school computer.
- **Connect to an existing School Server** — connects to a server already running elsewhere, including the school's HTTPS address when remote access has been configured.

The Examination application offers:

- **Connect to the School Server** — the recommended option for school examinations; it uses the central database and does not create a second local database.
- **Standalone offline on this PC** — a legacy fallback for isolated practice only. It uses a separate database and does not synchronise with the school server.

Each desktop app remembers its own connection choice. A client checks `/api/health` before opening the school application. Remote addresses must use HTTPS; plain HTTP is accepted only for private LAN addresses.

## 3. Host an examination from the Android Admin app (no internet)

The Android Admin app can run the CBT server directly on the Admin phone. Choose **Host exam on this device (Wi-Fi / Hotspot)**. The app starts its local server on port 8765 and binds it to the phone's LAN interfaces. Then:

1. Open the phone's Wi-Fi / Hotspot settings from the Admin app and enable its mobile hotspot, or connect the phone and student devices to the same Wi-Fi router.
2. In the Admin app, open **Student access URL** and use the displayed http://PHONE-IP:8765/ address.
3. Students join that same network and enter the URL in Chrome or another browser. They do not need to install the CBT app.
4. Keep the Admin phone awake, powered and connected to the network for the full examination. The Admin console remains available locally on the phone.

This works without mobile data or internet. Android does not allow ordinary apps to silently enable a hotspot on current versions, so the Admin must turn it on in Android Settings. Some phone manufacturers isolate hotspot clients or block client-to-host traffic; test the displayed URL from one student phone before starting a real examination. The Android-hosted database is stored on that Admin phone and is separate from a different Windows server database unless records are exported/imported.

Windows Admin hosting already binds the central server to LAN interfaces; students use http://WINDOWS-SERVER-IP:8000/ while connected to the same Wi-Fi/LAN.

## 4. Normal school-LAN mode

The default backend settings are:

- Bind address: `0.0.0.0` (LAN interfaces)
- Backend port: `8000`
- Remote admin: disabled unless explicitly enabled from the local Admin Console
- Health check: `http://SERVER-LAN-IP:8000/api/health`

Use the LAN IP displayed by the Admin Console's Server Information panel. Permit TCP port 8000 only on the trusted Windows Private network profile. Do not create a public router port-forward to port 8000.

## 5. Direct remote access — prerequisites

A phone hotspot or USB tethering supplies outbound internet to the PC. It does **not** guarantee that an outside device can connect back to the PC.

Before enabling remote access, confirm all of the following with the ISP/network operator:

1. The school connection has a publicly reachable IPv4 address or another explicitly supported inbound route.
2. The connection is not behind CGNAT, or the ISP has provided a suitable public-IP service.
3. The router/firewall can direct inbound TCP 443 to the school's own HTTPS reverse proxy.
4. The school controls a hostname whose DNS points to that public address.
5. A valid TLS certificate is installed and renews correctly.

If a mobile hotspot is behind CGNAT, remote inbound access will usually not work through that hotspot alone. LAN examinations and outbound internet use can still work. Do not work around this by exposing port 8000 or the SQLite database.

## 6. Reverse-proxy mode

The application now supports a locally operated HTTPS reverse proxy. In this mode, Flask/Waitress is loopback-only and trusts forwarded client headers only from that local proxy.

Set these environment variables for the Windows server process:

```text
CBT_TRUST_PROXY=1
CBT_HOST=127.0.0.1
CBT_PORT=8000
CBT_COOKIE_SECURE=1
```

Important:

- `CBT_TRUST_PROXY=1` with a non-loopback `CBT_HOST` is rejected at startup.
- The reverse proxy must listen on the school's approved LAN/HTTPS interface and forward to `http://127.0.0.1:8000`.
- The proxy must overwrite (not append untrusted client-supplied) `X-Forwarded-For`, `X-Forwarded-Proto`, and `X-Forwarded-Host` headers.
- The reverse proxy must be the only process able to reach the loopback backend. Do not configure a public listener for port 8000.
- Remote Admin remains blocked unless the school deliberately enables the existing remote-admin setting after HTTPS, public-IP, firewall and account-security checks are complete.
- Use a valid HTTPS certificate. Do not disable certificate verification in Android or Windows clients.

If the public address changes, update the school's DNS record. A domain name and DNS record do not relay CBT traffic; they only direct clients to the school's own public address.

## 7. Security and operational checklist

- Change the initial admin password before putting the server into use.
- Keep Windows firewall rules restricted to trusted network profiles and required ports.
- Do not expose the SQLite database file, backup folder, or port 8000 to the internet.
- Use a strong unique admin password and review audit records.
- Back up the database before every server update and test restoration.
- Keep the server awake and connected while remote administration is expected.
- If the school internet fails, LAN clients on the school network can continue to use the server. Remote users cannot reach it until the internet path returns.
- The current student page keeps unsent answer writes and the latest question paper in browser session storage. It retries pending writes when connectivity returns, can restore them after a page refresh in the same browser session, and blocks final submission while pending answers remain unsynchronised. This is not yet durable across closing/restarting the app or device; native secure storage and a versioned sync protocol are still required.

## 8. Current implementation boundary

The application now has environment-based bind/port configuration, an opt-in loopback-only trusted-proxy mode, secure-cookie configuration, a minimal health endpoint, richer local server diagnostics, Windows/Android client connection selection, and an Android Admin local-network hosting mode that serves student browsers over Wi-Fi/hotspot without internet. The student page has a browser-session pending-answer queue with retry and page-refresh recovery.

This does not yet implement a full Windows reverse-proxy installer, public-IP/CGNAT detection, durable native offline storage across app/device restarts, or offline multi-device database merging. Those are separate milestones and must be tested before remote production use.
