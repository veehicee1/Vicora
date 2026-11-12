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
    # A tunnel/reverse proxy running on this PC (for example, a local
    # Cloudflare Tunnel connector) may forward HTTPS to this host. The app
    # trusts only X-Forwarded-Proto from loopback, never forwarded client IPs.
    os.environ.setdefault("CBT_TRUSTED_PROXY_IPS", "127.0.0.1,::1")
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


def collect_school_code(existing=""):
    """Collect the immutable VICORA School Code for this local host."""
    import re
    supplied = (os.environ.get("CBT_HOST_SCHOOL_CODE") or "").strip().upper()
    if supplied:
        if not re.fullmatch(r"VIC-[A-F0-9]{8}", supplied):
            raise ValueError("CBT_HOST_SCHOOL_CODE must use the format VIC-XXXXXXXX.")
        return supplied
    import tkinter as tk
    from tkinter import simpledialog, messagebox
    root = tk.Tk()
    root.withdraw()
    try:
        while True:
            value = simpledialog.askstring(
                "VICORA School Code",
                "Enter the School Code issued when your school was approved on VICORA. "
                "For local-only testing, you may keep the prefilled code:",
                initialvalue=existing or "",
                parent=root,
            )
            if value is None:
                raise SystemExit("VICORA School Code setup was cancelled.")
            value = value.strip().upper()
            if re.fullmatch(r"VIC-[A-F0-9]{8}", value):
                return value
            messagebox.showwarning("Valid School Code required",
                                   "Enter a code in the format VIC-XXXXXXXX.", parent=root)
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
    log_file = Path(os.environ.get("CBT_HOST_LOG") or (log_dir / "windows-host.log"))
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_file),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        import app as cbt
        current = cbt.raw()
        school_row = current.execute(
            "SELECT school_id,school_code,name FROM schools WHERE is_legacy_default=1 LIMIT 1"
        ).fetchone()
        if not school_row:
            current.close()
            raise RuntimeError("The Windows Host has no initialized school identity.")
        school_id = school_row["school_id"]
        name_row = current.execute(
            "SELECT value FROM settings WHERE key='school_name' AND school_id=?", (school_id,)
        ).fetchone()
        current_name = name_row["value"] if name_row else school_row["name"]
        configured = current.execute(
            "SELECT value FROM settings WHERE key='host_school_code_configured' AND school_id=?",
            (school_id,),
        ).fetchone()
        current.close()
        school_name = collect_school_name(current_name)
        school_code = school_row["school_code"]
        if not configured or configured["value"] != "1":
            school_code = collect_school_code(school_code)
        c = cbt.raw()
        c.execute("UPDATE schools SET name=?,school_code=? WHERE school_id=?",
                  (school_name, school_code, school_id))
        c.execute("INSERT OR REPLACE INTO settings(key,value,school_id) VALUES('school_name',?,?)",
                  (school_name, school_id))
        c.execute("INSERT OR REPLACE INTO settings(key,value,school_id) VALUES('vicora_legacy_school_code',?,?)",
                  (school_code, school_id))
        c.execute("INSERT OR REPLACE INTO settings(key,value,school_id) VALUES('host_school_code_configured','1',?)",
                  (school_id,))
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
    except SystemExit as exc:
        logging.warning("VICORA Host setup exited: %s", exc)
        raise
    except Exception:
        logging.exception("VICORA Windows Host stopped unexpectedly")
        raise


if __name__ == "__main__":
    main()
