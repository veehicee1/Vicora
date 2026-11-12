"""Android embedded Flask server bootstrap with health diagnostics."""
import importlib
import os
import threading
import time
import traceback
import urllib.request

_lock = threading.RLock()
_server = None
_server_thread = None
_server_host = None
_server_port = None
_worker_started = False


def _write_diagnostic(data_dir, message):
    try:
        os.makedirs(data_dir, exist_ok=True)
        path = os.path.join(data_dir, "android-server-startup.log")
        with open(path, "a", encoding="utf-8") as log:
            log.write("\n[{:.3f}] {}\n".format(time.time(), message))
    except Exception:
        pass


def health_check(host="127.0.0.1", port=8765, timeout=2.5):
    """Return true only when the embedded HTTP server answers a real request."""
    try:
        request = urllib.request.Request(
            "http://{}:{}/".format(host, int(port)),
            headers={"Cache-Control": "no-cache", "Connection": "close"},
        )
        with urllib.request.urlopen(request, timeout=float(timeout)) as response:
            return 200 <= response.status < 500
    except Exception:
        return False


def start_server(data_dir, web_dir, host="0.0.0.0", port=8765, school_name=None):
    """Start (or reuse) the Android-local CBT host and return its address."""
    global _server, _server_thread, _server_host, _server_port, _worker_started
    with _lock:
        try:
            if _server is not None and _server_thread is not None and _server_thread.is_alive():
                if _server_host == str(host) and _server_port == int(port):
                    return {"ok": True, "host": host, "port": int(port), "already_running": True}
                _server.shutdown()
                close = getattr(_server, "server_close", None)
                if callable(close):
                    close()
                _server_thread.join(timeout=5)
                _server = None
                _server_thread = None
                _server_host = None
                _server_port = None

            os.makedirs(data_dir, exist_ok=True)
            if not os.path.isdir(web_dir):
                raise RuntimeError("The VICORA CBT web interface has not been installed on this device.")

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
                try:
                    conn.execute(
                        "UPDATE settings SET value=? WHERE key='school_name' AND "
                        "value IN ('', 'CBT Examination Centre')",
                        (" ".join(str(school_name).split())[:120],),
                    )
                    conn.commit()
                finally:
                    conn.close()
            if not _worker_started:
                cbt.start_background()
                _worker_started = True

            from werkzeug.serving import make_server
            server = make_server(host, int(port), cbt.app, threaded=True)
            thread = threading.Thread(
                target=server.serve_forever,
                name="vicora-android-cbt-server",
                daemon=True,
            )
            _server = server
            _server_thread = thread
            _server_host = str(host)
            _server_port = int(port)
            thread.start()
            if not health_check("127.0.0.1", int(port), timeout=5):
                raise RuntimeError("The VICORA server started but did not answer its local health check.")
            _write_diagnostic(data_dir, "Server ready on {}:{}".format(host, int(port)))
            return {"ok": True, "host": host, "port": int(port), "already_running": False}
        except BaseException:
            _write_diagnostic(data_dir, traceback.format_exc())
            raise


def stop_server():
    """Stop the embedded server when leaving local hosting mode."""
    global _server, _server_thread, _server_host, _server_port
    with _lock:
        server = _server
        thread = _server_thread
        if server is None:
            return {"ok": True, "already_stopped": True}
        try:
            server.shutdown()
        finally:
            close = getattr(server, "server_close", None)
            if callable(close):
                close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        _server = None
        _server_thread = None
        _server_host = None
        _server_port = None
        return {"ok": True, "already_stopped": False}
