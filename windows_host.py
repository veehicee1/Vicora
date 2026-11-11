"""VICORA CBT Windows Host bootstrap.

Run this executable on the Windows computer that owns the school's authoritative
SQLite database. It serves the same Flask application used by the web and Android
clients, bound to the school LAN. Do not expose port 8000 directly to the public
internet; use a trusted HTTPS gateway for off-site access.
"""
import logging
import os
import socket
import sys
from pathlib import Path


def configure_environment(program_data=None, bundle_dir=None, host="0.0.0.0", port=8000):
    """Configure persistent data and bundled web paths before importing app.py."""
    root = Path(program_data or os.environ.get("PROGRAMDATA") or Path.home())
    data_dir = root / "CBTSystem"
    data_dir.mkdir(parents=True, exist_ok=True)
    if bundle_dir is None:
        bundle_dir = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)
    web_dir = Path(bundle_dir) / "web"
    if not web_dir.is_dir():
        raise RuntimeError("VICORA web assets are missing from the Windows Host installation.")
    os.environ["CBT_DATA"] = str(data_dir.resolve())
    os.environ["CBT_WEB"] = str(web_dir.resolve())
    os.environ["CBT_HOST"] = str(host)
    os.environ["CBT_PORT"] = str(int(port))
    os.environ["CBT_TRUST_PROXY"] = "0"
    os.environ["CBT_COOKIE_SECURE"] = "0"
    return data_dir, web_dir


def collect_school_name(existing=""):
    """Ask for the school identity on first run; permit a CI-supplied value."""
    supplied = (os.environ.get("CBT_HOST_SCHOOL_NAME") or "").strip()
    if supplied:
        return supplied[:120]
    if existing and existing.strip() and existing.strip() != "CBT Examination Centre":
        return existing.strip()[:120]
    import tkinter as tk
    from tkinter import simpledialog, messagebox
    root = tk.Tk()
    root.withdraw()
    try:
        while True:
            value = simpledialog.askstring(
                "Set up VICORA CBT Host",
                "Enter the school's full name. This name will appear to students and staff:",
                initialvalue=existing or "",
                parent=root,
            )
            if value is None:
                raise SystemExit("VICORA Host setup was cancelled.")
            value = " ".join(value.split())
            if value:
                return value[:120]
            messagebox.showwarning("School name required", "Enter the school name to continue.", parent=root)
    finally:
        root.destroy()


def local_addresses(port=8000):
    values = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = item[4][0]
            if not ip.startswith(("127.", "169.254.")):
                values.add(ip)
    except OSError:
        pass
    return sorted(values)


def main():
    data_dir, web_dir = configure_environment()
    log_dir = data_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        filename=str(log_dir / "windows-host.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        import app as cbt
        current = cbt.raw()
        row = current.execute("SELECT value FROM settings WHERE key='school_name'").fetchone()
        current_name = row[0] if row else ""
        current.close()
        school_name = collect_school_name(current_name)
        c = cbt.raw()
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('school_name',?)", (school_name,))
        c.execute("UPDATE settings SET value=? WHERE key='school_name'", (school_name,))
        c.commit()
        c.close()

        cbt.start_background()
        from waitress import serve
        addresses = local_addresses()
        logging.info("VICORA CBT Host starting for %s on %s:%s", school_name, "0.0.0.0", 8000)
        logging.info("VICORA CBT Host is running for: %s", school_name)
        logging.info("Admin: http://127.0.0.1:8000/admin")
        for address in addresses:
            logging.info("Student access link: http://%s:8000/", address)
        logging.info("Keep this host computer powered on and connected to the school network.")
        serve(cbt.app, host="0.0.0.0", port=8000, threads=64, channel_timeout=120)
    except SystemExit:
        raise
    except Exception:
        logging.exception("VICORA Windows Host stopped unexpectedly")
        raise


if __name__ == "__main__":
    main()
