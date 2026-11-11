"""Standalone command-line diagnostics for GTMC CBT desktop clients."""
import argparse
import json
import os
import platform
import socket
import sys
import urllib.error
import urllib.request


def check_server(address: str) -> bool:
    url = address.rstrip("/") + "/api/health"
    print(f"Checking CBT server: {url}")
    try:
        with urllib.request.urlopen(url, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
            ok = response.status == 200 and payload.get("ok") is True and payload.get("service") == "gtmc-cbt"
            print(f"HTTP status: {response.status}")
            print(f"GTMC CBT service: {'READY' if ok else 'NOT CONFIRMED'}")
            return ok
    except (OSError, urllib.error.URLError, ValueError) as exc:
        print(f"Server check failed: {exc}")
        return False


def main() -> int:
    executable = os.path.basename(sys.executable).lower()
    default_role = "admin" if "admin" in executable else "examination"
    parser = argparse.ArgumentParser(description="GTMC CBT desktop diagnostic utility")
    parser.add_argument("--role", choices=("admin", "examination"), default=default_role)
    parser.add_argument("--server", help="Server URL, e.g. http://127.0.0.1:8000")
    args = parser.parse_args()
    print("=" * 54)
    print(f"GTMC CBT {args.role.title()} Diagnostic")
    print("=" * 54)
    print(f"Operating system: {platform.platform()}")
    print(f"Computer: {socket.gethostname()}")
    print("Desktop engine: Electron with bundled Chromium")
    print("WebView2 dependency: NONE")
    if not args.server:
        print("\nSupply --server http://SERVER-IP:8000 to test the CBT server.")
        input("\nPress Enter to close...")
        return 0
    ok = check_server(args.server)
    input("\nPress Enter to close...")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
