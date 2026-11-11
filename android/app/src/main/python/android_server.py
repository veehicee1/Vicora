"""Android embedded Flask server bootstrap.

The Android UI and foreground service both call this module. It configures the
same application backend used by Windows, but points it at Android's private
data directory and serves the student/admin web assets on the local network.
"""
import importlib
import os
import threading

_lock = threading.RLock()
_server = None
_server_thread = None
_worker_started = False


def start_server(data_dir, web_dir, host="0.0.0.0", port=8765, school_name=None):
    """Start (or reuse) the Android-local CBT host and return its address."""
    global _server, _server_thread, _worker_started

    with _lock:
        if _server is not None and _server_thread is not None and _server_thread.is_alive():
            return {"ok": True, "host": host, "port": int(port), "already_running": True}

        os.makedirs(data_dir, exist_ok=True)
        if not os.path.isdir(web_dir):
            raise RuntimeError("The VICORA CBT web interface has not been installed on this device.")

        # These must be set before importing app.py: it selects its SQLite and
        # web-asset paths during module initialisation.
        os.environ["CBT_DATA"] = os.path.abspath(data_dir)
        os.environ["CBT_WEB"] = os.path.abspath(web_dir)
        os.environ["CBT_HOST"] = str(host)
        os.environ["CBT_PORT"] = str(int(port))
        os.environ["CBT_COOKIE_SECURE"] = "0"
        os.environ["CBT_TRUST_PROXY"] = "0"
        if school_name and str(school_name).strip():
            os.environ["CBT_INITIAL_SCHOOL_NAME"] = " ".join(str(school_name).split())[:120]

        cbt = importlib.import_module("app")
        if school_name and str(school_name).strip():
            conn = cbt.raw()
            conn.execute(
                "UPDATE settings SET value=? WHERE key='school_name' AND "
                "value IN ('', 'CBT Examination Centre')",
                (" ".join(str(school_name).split())[:120],),
            )
            conn.commit()
            conn.close()
        if not _worker_started:
            cbt.start_background()
            _worker_started = True

        # Bind synchronously so a port or permission error is reported to the
        # Android UI instead of silently leaving it on an endless loading page.
        from werkzeug.serving import make_server
        _server = make_server(host, int(port), cbt.app, threaded=True)
        _server_thread = threading.Thread(
            target=_server.serve_forever,
            name="vicora-android-cbt-server",
            daemon=True,
        )
        _server_thread.start()

        return {"ok": True, "host": host, "port": int(port), "already_running": False}
