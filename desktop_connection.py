"""Desktop connection chooser shared by the Admin and Examination launchers.

A selected school-server URL is checked through /api/health before the UI opens.
Remote plain-HTTP URLs are rejected; HTTP is accepted only for loopback/private
LAN addresses. The legacy standalone mode is explicit and warns that its local
database is not the central school database.
"""
import ipaddress
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PORT = int(os.environ.get("CBT_PORT", "8000"))
LOCAL_URL = f"http://127.0.0.1:{PORT}/"


def _config_path(role):
    root = os.environ.get("APPDATA") or str(Path.home())
    folder = Path(root) / "GTMC CBT"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"desktop_connection_{role}.json"


def _load_config(role):
    try:
        return json.loads(_config_path(role).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def _save_config(role, data):
    try:
        path = _config_path(role)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        # Configuration persistence is helpful but must not prevent an exam.
        pass


def validate_server_url(value):
    value = (value or "").strip()
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Enter a complete server address beginning with http:// or https://.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Do not include a username, password, query or fragment in the server address.")
    host = parsed.hostname.lower()
    local_http = host in ("localhost", "127.0.0.1", "::1") or host.endswith((".local", ".lan"))
    try:
        local_http = local_http or ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    if parsed.scheme == "http" and not local_http:
        raise ValueError("Remote server addresses must use HTTPS. Plain HTTP is allowed only on a private school LAN.")
    return value.rstrip("/") + "/"


def check_server(url, timeout=5):
    target = urllib.parse.urljoin(url, "api/health")
    request = urllib.request.Request(target, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.status == 200 and payload.get("ok") is True
    except (OSError, ValueError, urllib.error.URLError):
        return False


def _local_port_busy():
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def _choose_with_tk(role, default_mode, default_url):
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("GTMC CBT — Connection")
    root.configure(bg="#f3f7fc")
    root.resizable(False, False)
    root.geometry("540x410")
    mode = tk.StringVar(value=default_mode)
    url = tk.StringVar(value=default_url)
    result = {"mode": None, "url": None}

    outer = tk.Frame(root, bg="#f3f7fc", padx=28, pady=24)
    outer.pack(fill="both", expand=True)
    tk.Label(outer, text="GTMC CBT", bg="#f3f7fc", fg="#0756a8",
             font=("Segoe UI", 21, "bold")).pack(anchor="w")
    tk.Label(outer, text="Choose how this application connects to the school system.",
             bg="#f3f7fc", fg="#52657a", font=("Segoe UI", 10)).pack(anchor="w", pady=(3, 18))

    if role == "admin":
        choices = [
            ("server", "This PC is the central School Server",
             "Starts or reuses the authoritative school server on this computer."),
            ("connect", "Connect to an existing School Server",
             "Use the central server running at school or at its secure remote address."),
        ]
    else:
        choices = [
            ("connect", "Connect to the School Server",
             "Use the school's central database and live examinations."),
            ("offline", "Standalone offline on this PC",
             "Uses a separate local database. It does not synchronise with school yet."),
        ]

    for value, title, desc in choices:
        card = tk.Frame(outer, bg="white", highlightbackground="#d8e3ef",
                        highlightthickness=1, padx=12, pady=9)
        card.pack(fill="x", pady=4)
        tk.Radiobutton(card, text=title, variable=mode, value=value, bg="white",
                       fg="#14263d", activebackground="white",
                       font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(card, text=desc, bg="white", fg="#61738a",
                 font=("Segoe UI", 9), wraplength=440, justify="left").pack(anchor="w", padx=25)

    tk.Label(outer, text="School server address", bg="#f3f7fc", fg="#14263d",
             font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(13, 4))
    entry = tk.Entry(outer, textvariable=url, font=("Segoe UI", 11),
                     relief="solid", bd=1, highlightthickness=1,
                     highlightcolor="#2677c9")
    entry.pack(fill="x", ipady=7)

    def update_entry(*_):
        entry.configure(state="normal" if mode.get() == "connect" else "disabled")
    mode.trace_add("write", update_entry)
    update_entry()

    def proceed():
        selected = mode.get()
        if selected == "connect":
            try:
                address = validate_server_url(url.get())
            except ValueError as exc:
                messagebox.showerror("Check server address", str(exc), parent=root)
                return
            if not check_server(address):
                messagebox.showerror(
                    "School server unavailable",
                    "The server did not respond to its health check. Check the address, Wi-Fi/mobile data and server power, then try again.",
                    parent=root,
                )
                return
            result.update(mode=selected, url=address)
        else:
            result.update(mode=selected, url=LOCAL_URL)
        root.destroy()

    buttons = tk.Frame(outer, bg="#f3f7fc")
    buttons.pack(fill="x", pady=(17, 0))
    tk.Button(buttons, text="Continue", command=proceed, bg="#0756a8", fg="white",
              activebackground="#043e7a", activeforeground="white",
              relief="flat", padx=22, pady=9, font=("Segoe UI", 10, "bold")).pack(side="right")
    tk.Button(buttons, text="Exit", command=root.destroy, bg="#e7edf5", fg="#14263d",
              relief="flat", padx=18, pady=9, font=("Segoe UI", 10)).pack(side="right", padx=8)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    if not result["mode"]:
        raise SystemExit("Connection selection cancelled.")
    return result["mode"], result["url"]


def choose_target(role):
    if role not in ("admin", "exam"):
        raise ValueError("Unknown desktop application role.")
    saved = _load_config(role)
    env_url = os.environ.get("CBT_SERVER_URL", "").strip()
    if env_url:
        address = validate_server_url(env_url)
        if not check_server(address):
            raise RuntimeError("CBT_SERVER_URL is set, but the school server health check failed.")
        return "connect", address

    default_mode = saved.get("mode", "server" if role == "admin" else "connect")
    if role == "exam" and default_mode == "server":
        default_mode = "connect"
    default_url = saved.get("url", LOCAL_URL if _local_port_busy() else "")
    mode, address = _choose_with_tk(role, default_mode, default_url)
    _save_config(role, {"mode": mode, "url": address})
    return mode, address


def ensure_local_server(cbt_module):
    """Start or reuse the local authoritative server and wait for its health check."""
    if check_server(LOCAL_URL):
        return LOCAL_URL
    if _local_port_busy():
        raise RuntimeError(
            f"Port {PORT} is already occupied, but it is not responding as a GTMC CBT server. "
            "Close the other program or change CBT_PORT."
        )
    cbt_module.start_background()
    import threading
    threading.Thread(target=cbt_module.serve, daemon=True, name="gtmc-cbt-server").start()
    for _ in range(150):
        if check_server(LOCAL_URL, timeout=1):
            return LOCAL_URL
        time.sleep(0.1)
    raise RuntimeError("The GTMC CBT server did not become ready. Check the server log and try again.")
