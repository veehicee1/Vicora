"""Student Examination launcher with visible diagnostics for Windows troubleshooting.

This diagnostic build deliberately keeps a console open so startup stages and
exceptions are visible on Windows Server. It never launches an external browser.
"""
import os
import sys
import traceback
from pathlib import Path
from urllib.parse import urljoin

from desktop_connection import choose_target, ensure_local_server


def _log(message):
    line = str(message)
    print(line, flush=True)
    try:
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        folder = Path(root) / "GTMC CBT"
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "exam_launcher.log").open("a", encoding="utf-8") as handle:
            handle.write(line + "\\n")
    except Exception as log_exc:
        print("DIAGNOSTIC LOG WRITE FAILED: " + repr(log_exc), flush=True)


def _show_error(message):
    _log("ERROR: " + str(message))
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("GTMC CBT Examination - Diagnostic Build", str(message), parent=root)
        root.destroy()
    except Exception:
        print("GTMC CBT Examination:", message, flush=True)


def main():
    _log("\\n========== GTMC EXAM DIAGNOSTIC LAUNCH ==========")
    _log("BUILD MARKER: SERVER2016-CONSOLE-DIAGNOSTIC-2")
    _log("Executable: " + sys.executable)
    _log("Frozen build: " + str(getattr(sys, "frozen", False)))
    _log("Application folder: " + str(getattr(sys, "_MEIPASS", Path(__file__).parent)))
    try:
        _log("STAGE 1: showing connection chooser")
        mode, address = choose_target("exam")
        _log("STAGE 2: connection selected; mode=" + str(mode))
        if mode == "offline":
            _log("STAGE 3: importing local CBT server module")
            import app as cbt
            _log("STAGE 4: starting/reusing local CBT server")
            base_url = ensure_local_server(cbt)
        else:
            base_url = address

        target = urljoin(base_url, "")
        _log("STAGE 5: importing pywebview")
        import webview
        _log("STAGE 6: creating embedded examination window")
        webview.create_window(
            "GTMC CBT Examination",
            target,
            width=1180,
            height=860,
            min_size=(800, 600),
        )
        _log("STAGE 7: starting Edge WebView2 engine")
        webview.start(gui="edgechromium")
        _log("STAGE 8: WebView window closed normally")
    except SystemExit as exc:
        _log("Startup cancelled: " + str(exc))
    except Exception as exc:
        _log("FATAL EXCEPTION: " + repr(exc))
        _log(traceback.format_exc())
        _show_error("The examination app could not start.\n\n" + repr(exc) +
                    "\\n\\nPlease send a photo of this diagnostic window and the black console.")


if __name__ == "__main__":
    main()
