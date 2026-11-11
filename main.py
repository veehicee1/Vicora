"""GTMC CBT Admin desktop launcher using an embedded Edge WebView2 window.

The launcher must never fall back to Chrome or another external browser.
"""
from pathlib import Path
import os
import sys
import traceback
from urllib.parse import urljoin

from desktop_connection import choose_target, ensure_local_server


BUILD_MARKER = "GTMC-ADMIN-SERVER-DIAGNOSTIC-1"


def _log_path():
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    folder = Path(base) / "GTMC CBT"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "admin_launcher.log"


def _log(message):
    line = str(message)
    print(line, flush=True)
    try:
        with _log_path().open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception as exc:
        print("Could not write diagnostic log:", exc, flush=True)


def _show_error(message):
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("GTMC CBT Admin", str(message), parent=root)
        root.destroy()
    except Exception:
        print("GTMC CBT Admin:", message, flush=True)


def main():
    _log("\n========== GTMC ADMIN LAUNCH START ==========")
    _log("Build marker: " + BUILD_MARKER)
    _log("Executable: " + sys.executable)
    _log("Frozen build: " + str(getattr(sys, "frozen", False)))
    _log("Application folder: " + str(getattr(sys, "_MEIPASS", Path(__file__).parent)))
    try:
        _log("Stage 1: showing connection chooser")
        mode, address = choose_target("admin")
        _log("Stage 2: connection chooser completed; mode=" + str(mode))
        if mode == "server":
            _log("Stage 3: importing local server application")
            import app as cbt
            _log("Stage 4: starting local server")
            base_url = ensure_local_server(cbt)
        else:
            base_url = address
        target = urljoin(base_url, "admin")
        _log("Stage 5: importing pywebview")
        import webview
        _log("Stage 6: creating embedded Admin window")
        webview.create_window(
            "GTMC CBT Admin",
            target,
            width=1440,
            height=920,
            min_size=(980, 680),
        )
        _log("Stage 7: starting Edge WebView2 engine")
        webview.start(gui="edgechromium")
        _log("Stage 8: embedded window closed normally")
    except SystemExit:
        _log("Launcher exited from connection chooser.")
        return
    except Exception as exc:
        _log("ADMIN LAUNCH ERROR: " + repr(exc))
        _log(traceback.format_exc())
        _show_error(
            "The GTMC CBT Admin embedded window could not start. "
            "Chrome will not be opened as a fallback.\n\n"
            "Check the black diagnostic window for the last stage and error.\n\n"
            "Technical detail: " + str(exc)
        )


if __name__ == "__main__":
    main()
