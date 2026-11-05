"""Laeuft noch ein altes Aquaticy? Erkennen, melden und auf Wunsch beenden (15.0.0).

Nach einem Update lief oft der alte Hintergrundprozess weiter: Der neue Start wich dann auf
den naechsten Port aus, und der Browser zeigte unter der gewohnten Adresse die alte Version.
Dieses Modul fragt den belegten Port, welche Version dort antwortet, findet den Prozess dazu
(nur eigene Prozesse, nur wenn es Aquaticy ist) und beendet ihn nur mit Zustimmung.
"""

from __future__ import annotations

import ast
import contextlib
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

import httpx

_VERSION = re.compile(r'window\.__AQUATICY_VERSION__ = "([^"\\]{1,40})"')


def running_version(port: int, timeout: float = 2.0) -> str:
    """Die Version, die auf diesem Rechner unter *port* antwortet -- "" wenn keine."""
    try:
        with httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False) as client:
            antwort = client.get(f"http://127.0.0.1:{int(port)}/",
                                 headers={"User-Agent": "aquaticy-startcheck"})
    except (httpx.HTTPError, ValueError, OSError):
        return ""
    treffer = _VERSION.search(antwort.text[:400_000])
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
    befehl = ""
    with contextlib.suppress(OSError):
        befehl = Path(f"/proc/{int(pid)}/cmdline").read_bytes().replace(b"\0", b" ").decode(
            "utf-8", "replace")
    if not befehl and shutil.which("ps"):
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            befehl = subprocess.run(["ps", "-p", str(int(pid)), "-o", "command="],
                                    capture_output=True, text=True, timeout=5,
                                    check=False).stdout
    return "aquaticy" in befehl.lower() and int(pid) != os.getpid()


def stop(pid: int, wait: float = 10.0) -> bool:
    """Beendet einen eigenen Aquaticy-Prozess sanft. True, wenn er weg ist.

    Unter Windows nie: Dort waere os.kill(pid, 0) ein Strg+C an die ganze Prozessgruppe.
    """
    if os.name == "nt" or not is_aquaticy(pid):
        return False
    try:
        os.kill(int(pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        return False
    ende = time.monotonic() + wait
    while time.monotonic() < ende:
        try:
            os.kill(int(pid), 0)
        except OSError:
            return True
        time.sleep(0.2)
    return False


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
    """`aquaticy web ...` oder `python -m aquaticy.cli web ...` -- nichts anderes."""
    namen = [Path(t).name.lower() for t in befehl]
    for i, name in enumerate(namen):
        programm = i == 0 or (i == 1 and namen[0].startswith("python")) or (
            i >= 1 and namen[i - 1] == "-m")
        if (programm and name in ("aquaticy", "aquaticy.cli", "aquaticy.exe")
                and "web" in namen[i + 1:i + 3]):
            return True
    return False
