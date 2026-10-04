#!/usr/bin/env python3
"""Install and run the whole AegIs stack after a fresh git clone.

    python start.py

Needs Python 3.10+ and Node.js 18+ on PATH. Creates .venv, installs
the gate, builds the dashboard, then starts API + proxy + /app.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
MIN_PY = (3, 10)
HOST = "127.0.0.1"
PORT = 8080
PROXY_PORT = 8888


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def in_venv() -> bool:
    try:
        return Path(sys.executable).resolve() == venv_python().resolve()
    except OSError:
        return False


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    printable = " ".join(str(part) for part in cmd)
    print(f"\n>> {printable}", flush=True)
    subprocess.check_call(cmd, cwd=str(cwd or ROOT))


def port_busy(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def gate_already_up() -> bool:
    try:
        with urlopen(f"http://{HOST}:{PORT}/health", timeout=1.5) as resp:
            payload = resp.read().decode("utf-8", "replace")
    except (OSError, URLError, TimeoutError, ValueError):
        return False
    return "backend" in payload


def find_npm() -> str:
    for name in ("npm.cmd", "npm"):
        found = shutil.which(name)
        if found:
            return found
    sys.exit(
        "Brak Node.js / npm. Zainstaluj Node 18+ (https://nodejs.org) i uruchom ponownie:\n"
        "  python start.py"
    )


def parse_flags(argv: list[str]) -> dict[str, object]:
    return {
        "with_laya": "--with-laya" in argv,
        "skip_build": "--skip-build" in argv,
        "mitm": "--mitm" in argv,
        "no_browser": "--no-browser" in argv,
        "help": "-h" in argv or "--help" in argv,
    }


def print_help() -> None:
    print(
        """AegIs — instalacja i start po sklonowaniu repo.

  python start.py

Opcje:
  --with-laya    doinstaluj model Laya (~850 MB) zamiast heurystyki
  --skip-build   nie buduj dashboardu, jeśli dashboard/dist już jest
  --mitm         włącz deszyfrację HTTPS na proxy (domyślnie wyłączone)
  --no-browser   nie otwieraj przeglądarki
"""
    )


def banner(*, backend: str, mitm: bool) -> None:
    app = f"http://{HOST}:{PORT}/app"
    home = f"http://{HOST}:{PORT}/"
    demo = f"http://{HOST}:{PORT}/demo"
    film = f"http://{HOST}:{PORT}/film/"
    ext = ROOT / "extension"
    print(
        f"""
============================================================
  AegIs działa

  Dashboard     {app}
  Start         {home}
  Demo chat     {demo}
  Film          {film}
  API / bramka  http://{HOST}:{PORT}/net/health
  HTTP proxy    http://{HOST}:{PROXY_PORT}
  backend       {backend}   MITM {("ON" if mitm else "OFF")}

  Wtyczka Chrome:
    chrome://extensions  →  tryb deweloperski
    → Załaduj rozpakowane  →  {ext}
============================================================
""",
        flush=True,
    )


def open_browser_later(url: str) -> None:
    def _open() -> None:
        time.sleep(1.6)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    flags = parse_flags(argv)
    if flags["help"]:
        print_help()
        return 0

    if sys.version_info < MIN_PY:
        print(
            f"Potrzebny Python {MIN_PY[0]}.{MIN_PY[1]}+, jest {sys.version.split()[0]}.",
            file=sys.stderr,
        )
        return 2

    if not in_venv():
        if not venv_python().exists():
            print("Tworzę .venv …", flush=True)
            run([sys.executable, "-m", "venv", str(VENV)])
        return subprocess.call([str(venv_python()), str(ROOT / "start.py"), *argv])

    extras = "demo,laya" if flags["with_laya"] else "demo"
    run([sys.executable, "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"])
    run([sys.executable, "-m", "pip", "install", "-e", f".[{extras}]"])

    dist = ROOT / "dashboard" / "dist" / "index.html"
    if not (flags["skip_build"] and dist.is_file()):
        npm = find_npm()
        run([npm, "install"], cwd=ROOT / "dashboard")
        run([npm, "run", "build"], cwd=ROOT / "dashboard")
    elif not dist.is_file():
        print("Brak dashboard/dist — buduję mimo --skip-build.", flush=True)
        npm = find_npm()
        run([npm, "install"], cwd=ROOT / "dashboard")
        run([npm, "run", "build"], cwd=ROOT / "dashboard")

    backend = "laya" if flags["with_laya"] else "heuristic"
    mitm = bool(flags["mitm"])

    if port_busy(HOST, PORT):
        if gate_already_up():
            print(f"AegIs już nasłuchuje na http://{HOST}:{PORT} — pomijam start.", flush=True)
            banner(backend=backend, mitm=mitm)
            if not flags["no_browser"]:
                webbrowser.open(f"http://{HOST}:{PORT}/app")
            return 0
        print(
            f"Port {PORT} jest zajęty przez inny proces. Zamknij go i uruchom ponownie: python start.py",
            file=sys.stderr,
        )
        return 1

    banner(backend=backend, mitm=mitm)
    if not flags["no_browser"]:
        open_browser_later(f"http://{HOST}:{PORT}/app")

    cmd = [
        sys.executable,
        "-m",
        "sensitive_guard",
        "net",
        "--backend",
        backend,
        "--host",
        HOST,
        "--port",
        str(PORT),
        "--proxy-port",
        str(PROXY_PORT),
    ]
    if not mitm:
        cmd.append("--no-mitm")
    if port_busy(HOST, PROXY_PORT):
        print(f"Port {PROXY_PORT} zajęty — startuję bez HTTP proxy.", flush=True)
        cmd.append("--no-proxy")
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nZatrzymane.", flush=True)
        raise SystemExit(130)
    except subprocess.CalledProcessError as exc:
        print(f"\nKomenda nie powiodła się (kod {exc.returncode}).", file=sys.stderr)
        raise SystemExit(exc.returncode or 1)
