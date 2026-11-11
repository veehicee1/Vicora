# GTMC CBT — Offline Desktop and Android Architecture

## Target operating model

The product supports two independent operating modes. Internet is optional.

1. **Central school mode (LAN):** one Windows PC runs the authoritative Flask/SQLite server. Windows kiosk clients and Android clients connect to its private Wi-Fi/LAN address. No internet is needed. Student sessions, timing, marking and results remain on the central server.
2. **Standalone device mode:** a Windows PC runs its own local server/database; the Android APK embeds the same Flask application and SQLite database inside the app sandbox. Each device can conduct an exam without Wi-Fi or internet.

## Current repository foundation

- Flask routes and SQLite database are already local-first.
- Windows data is stored outside the executable, so upgrades do not overwrite the database.
- The Windows launcher starts the server and opens the admin console.
- Student browser pages already use same-origin API calls and can be served from a LAN host.
- The Android wrapper starts the existing Python backend locally and loads the existing student/admin web pages in a WebView. It does not reimplement the examination engine.

## Android connection modes

- **Standalone offline:** start the embedded Flask server on 127.0.0.1:8765; database files live in the app-private data directory.
- **School server:** enter the school's LAN URL (for example http://192.168.1.10:8000/) and use the central server's existing API. This mode needs only the local school Wi-Fi, not internet.

The app remembers the last selected mode and provides a connection menu to switch modes.

## Data and synchronisation boundary

A standalone device database and the central school database are separate databases. Do not copy a live SQLite database file over another live database, and do not silently merge them. That can overwrite sessions or create conflicting student/exam records.

The first packaging milestone provides local standalone operation and central-server connectivity. A later synchronisation milestone must use explicit, validated transfer records (stable IDs, exam identifiers, student identifiers, submission timestamps, duplicate detection, conflict reporting and audit entries). Until that is implemented and tested, results created in standalone mode must be exported/backed up and transferred through an approved administrative process; automatic bidirectional synchronisation is not claimed.

## Exam integrity

The central server remains the preferred mode for formal school examinations because it owns the clock, question selection, answer persistence, final marking and invigilator monitoring. Standalone mode uses the same local backend and preserves its current server-side timing/marking behaviour on that device. A fully disconnected device cannot be monitored by the central server while disconnected.

## Build outputs

- Windows: CBTServer.exe, built from main.py with PyInstaller. The SQLite database is stored separately from the executable.
- Android: installable APK, built from android/ using Android Gradle Plugin and Chaquopy. The APK bundles the existing Flask app, Python dependencies and web assets.

## Safe rollout sequence

1. Build and test the Windows EXE without touching existing database files.
2. Build and test the Android APK in standalone mode with a fresh test database.
3. Test Android-to-school-server mode on the same Wi-Fi.
4. Run simultaneous-device tests and power/network interruption tests.
5. Implement and validate a record-level synchronisation protocol before enabling automatic sync.
6. Back up the live school database before any production upgrade.

## Explicit non-goals for the first packaging milestone

- No destructive database migration.
- No replacement of the existing exam engine.
- No claim that standalone results automatically merge into the central database.
- No requirement for internet during an examination.
