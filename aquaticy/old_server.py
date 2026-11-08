"""Laeuft noch ein altes Aquaticy? Erkennen, melden und auf Wunsch beenden (15.0.0).

Nach einem Update lief oft der alte Hintergrundprozess weiter: Der neue Start wich dann auf
den naechsten Port aus, und der Browser zeigte unter der gewohnten Adresse die alte Version.
Dieses Modul fragt den belegten Port, welche Version dort antwortet, findet den Prozess dazu
(nur eigene Prozesse, nur wenn es Aquaticy ist) und beendet ihn nur mit Zustimmung.
"""

from __future__ import annotations

import ast
import contextlib
import logging
import os
import re
import select
import shlex
import shutil
import signal
import subprocess
import time
from pathlib import Path

import httpx

LOG = logging.getLogger(__name__)

_VERSION = re.compile(r'window\.__AQUATICY_VERSION__ = "([^"\\]{1,40})"')


def running_version(port: int, timeout: float = 2.0) -> str:
    """Die Version, die auf diesem Rechner unter *port* antwortet -- "" wenn keine."""
    try:
        with httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False) as client:
            from aquaticy.netguard import read_response

            with client.stream("GET", f"http://127.0.0.1:{int(port)}/",
                               headers={"User-Agent": "aquaticy-startcheck"}) as response:
                raw = read_response(response, 400_000, time.monotonic() + timeout, truncate=True)
                page = raw.decode(response.encoding or "utf-8", "replace")
    except (httpx.HTTPError, ValueError, OSError):
        return ""
    treffer = _VERSION.search(page)
    return treffer.group(1) if treffer else ""


def installed_label() -> str:
    """Die Version, die gerade auf der Platte installiert ist (nicht die geladene)."""
    werte: dict[str, str] = {}
    try:
        baum = ast.parse((Path(__file__).with_name("__init__.py")).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return ""
    for knoten in baum.body:
        if isinstance(knoten, ast.Assign) and isinstance(knoten.value, ast.Constant):
            for ziel in knoten.targets:
                if isinstance(ziel, ast.Name) and isinstance(knoten.value.value, str):
                    werte[ziel.id] = knoten.value.value
    return " ".join(t for t in (werte.get("__version__", ""), werte.get("__codename__", ""),
                                werte.get("__stage__", "")) if t)


def _linux_listeners(port: int) -> list[int]:
    inodes: set[str] = set()
    for datei in ("/proc/net/tcp", "/proc/net/tcp6"):
        with contextlib.suppress(OSError):
            for zeile in Path(datei).read_text().splitlines()[1:]:
                teile = zeile.split()
                if len(teile) > 9 and teile[3] == "0A" and int(teile[1].rsplit(":", 1)[1],
                                                               16) == port:
                    inodes.add(teile[9])
    gefunden: list[int] = []
    if not inodes:
        return gefunden
    for eintrag in Path("/proc").iterdir():
        if not eintrag.name.isdigit():
            continue
        with contextlib.suppress(OSError):
            for fd in (eintrag / "fd").iterdir():
                ziel = os.readlink(fd)
                if ziel.startswith("socket:[") and ziel[8:-1] in inodes:
                    gefunden.append(int(eintrag.name))
                    break
    return gefunden


def listener_pids(port: int) -> list[int]:
    """Eigene Prozesse, die auf *port* lauschen (Linux direkt, sonst mit lsof)."""
    if Path("/proc/net/tcp").exists():
        return sorted(set(_linux_listeners(int(port))))
    lsof = shutil.which("lsof")
    if not lsof:
        return []
    try:
        aus = subprocess.run([lsof, "-t", f"-iTCP:{int(port)}", "-sTCP:LISTEN"],
                             capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted({int(z) for z in aus.stdout.split() if z.isdigit()})


def is_aquaticy(pid: int) -> bool:
    """Ist der Prozess wirklich Aquaticy? Sonst wird er nie angefasst."""
    if int(pid) <= 0 or int(pid) == os.getpid() or os.name == "nt":
        return False
    proc = Path(f"/proc/{int(pid)}")
    if Path("/proc/net/tcp").exists():
        try:
            if proc.stat().st_uid != os.getuid():
                return False
            command = proc.joinpath("cmdline").read_bytes().split(b"\0")
            return _ist_server([part.decode("utf-8", "replace") for part in command if part])
        except OSError:
            return False
    if shutil.which("ps"):
        with contextlib.suppress(OSError, subprocess.SubprocessError, ValueError):
            output = subprocess.run(["ps", "-p", str(int(pid)), "-o", "uid=,command="],
                                    capture_output=True, text=True, timeout=5,
                                    check=False).stdout.strip().split(None, 1)
            return (len(output) == 2 and output[0] == str(os.getuid())
                    and _ist_server(shlex.split(output[1])))
    return False


def _exited(pid: int) -> bool:
    try:
        state = Path(f"/proc/{int(pid)}/stat").read_text().rsplit(")", 1)[-1].split()[0]
        if state in ("Z", "X"):
            return True
    except (OSError, IndexError):
        pass
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


def stop(pid: int, wait: float = 10.0) -> bool:
    """Beendet einen eigenen Aquaticy-Prozess sanft. True, wenn er weg ist.

    Unter Windows nie: Dort waere os.kill(pid, 0) ein Strg+C an die ganze Prozessgruppe.
    """
    if os.name == "nt":
        return False
    pidfd = -1
    if callable(getattr(signal, "pidfd_send_signal", None)):
        with contextlib.suppress(AttributeError, OSError):
            pidfd = os.pidfd_open(int(pid))
    try:
        if not is_aquaticy(pid):
            return False
        LOG.warning("[Sicherheit] Alter Aquaticy-Server (Prozess %s) wird beendet.", int(pid))
        try:
            if pidfd >= 0:
                signal.pidfd_send_signal(pidfd, signal.SIGTERM)
                poller = select.poll()
                poller.register(pidfd, select.POLLIN)
                return bool(poller.poll(max(0, int(wait * 1000))))
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            return False
        ende = time.monotonic() + wait
        while time.monotonic() < ende:
            if _exited(pid):
                return True
            time.sleep(min(0.2, max(0, ende - time.monotonic())))
        return _exited(pid)
    finally:
        if pidfd >= 0:
            os.close(pidfd)


def aquaticy_servers() -> list[int]:
    """Alle eigenen laufenden Aquaticy-Server ("aquaticy web"), ohne diesen Prozess (15.0.1)."""
    gefunden: list[int] = []
    proc = Path("/proc")
    if proc.is_dir():
        for eintrag in proc.iterdir():
            if not eintrag.name.isdigit() or int(eintrag.name) == os.getpid():
                continue
            with contextlib.suppress(OSError):
                if eintrag.stat().st_uid != os.getuid():
                    continue
                teile = (eintrag / "cmdline").read_bytes().split(b"\0")
                befehl = [t.decode("utf-8", "replace") for t in teile if t]
                if _ist_server(befehl):
                    gefunden.append(int(eintrag.name))
        return sorted(gefunden)
    if shutil.which("ps"):
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            aus = subprocess.run(["ps", "-x", "-o", "pid=,command="], capture_output=True,
                                 text=True, timeout=5, check=False).stdout
            for zeile in aus.splitlines():
                pid, _, rest = zeile.strip().partition(" ")
                if pid.isdigit() and int(pid) != os.getpid() and _ist_server(rest.split()):
                    gefunden.append(int(pid))
    return sorted(gefunden)


def _ist_server(befehl: list[str]) -> bool:
    """Nur ein ausdruecklicher Web-Aufruf ist ein Server; ohne Befehl startet der Terminalchat."""
    if not befehl:
        return False
    program = Path(befehl[0]).name.lower()
    args = befehl[1:]
    if re.fullmatch(r"(?:python|pypy)[0-9.]*w?(?:\.exe)?", program):
        while args and args[0] in ("-u", "-B", "-E", "-s", "-S", "-I", "-O", "-OO", "-q"):
            args = args[1:]
        if args[:2] == ["-m", "aquaticy.cli"]:
            return len(args) > 2 and args[2] == "web"
        if not args:
            return False
        program, args = Path(args[0]).name.lower(), args[1:]
    return program in ("aquaticy", "aquaticy.exe") and bool(args) and args[0] == "web"
