"""Podman fuer die virtual machine einrichten -- per Paketmanager, nach Rueckfrage (11.2.2 Sol).

Ohne Podman oder Docker gibt es keine virtual machine: Aquaticy fuehrt Code
nie ungeschuetzt auf dem Rechner selbst aus (aquaticy/sandbox.py). Bis 11.2.2
Sol musste der Betreiber das selbst nachinstallieren. Jetzt bietet
``aquaticy web`` es beim Start an, und ``aquaticy install-vm`` erledigt es.

Bewusst nur im Terminal und nie aus dem Browser: Die Installation braucht
Verwalterrechte (sudo, winget). Das entscheidet der Mensch am Rechner, kein
Konto im Chat. Jeder Befehl steht fest, laeuft ohne Shell und wird vorher
angezeigt.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

WINDOWS_PODMAN = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "RedHat" / "Podman"


_LINUX: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = (
    ("apt-get", (("apt-get", "update"),
                 ("apt-get", "install", "-y", "podman", "uidmap"))),
    ("dnf", (("dnf", "install", "-y", "podman"),)),
    ("yum", (("yum", "install", "-y", "podman"),)),
    ("pacman", (("pacman", "-S", "--needed", "--noconfirm", "podman"),)),
    ("zypper", (("zypper", "--non-interactive", "install", "podman"),)),
    ("apk", (("apk", "add", "podman"),)),
)


INSTALL_TIMEOUT = 1800
MACHINE_TIMEOUT = 600


def _root() -> bool:
    geteuid = getattr(os, "geteuid", None)
    return bool(geteuid and geteuid() == 0)


def install_steps() -> list[list[str]] | None:
    """Die Befehle, die Podman auf diesem System einrichten -- oder None, wenn unbekannt."""
    system = platform.system()
    if system == "Linux":
        for werkzeug, schritte in _LINUX:
            if not shutil.which(werkzeug):
                continue
            if _root():
                return [list(s) for s in schritte]
            if not shutil.which("sudo"):
                return None
            return [["sudo", *s] for s in schritte]
        return None
    if system == "Darwin":
        if not shutil.which("brew"):
            return None
        return [["brew", "install", "podman"], ["podman", "machine", "init"],
                ["podman", "machine", "start"]]
    if system == "Windows":
        if not shutil.which("winget"):
            return None
        return [["winget", "install", "--id", "RedHat.Podman", "-e",
                 "--accept-package-agreements", "--accept-source-agreements"],
                ["podman", "machine", "init"], ["podman", "machine", "start"]]
    return None


def install_hint() -> str:
    """Was der Betreiber von Hand tun kann, wenn es keinen bekannten Weg gibt."""
    system = platform.system()
    if system == "Darwin":
        return ("Podman von https://podman.io installieren (oder erst Homebrew, dann "
                "`aquaticy install-vm`).")
    if system == "Windows":
        return "Podman Desktop von https://podman.io installieren, dann Aquaticy neu starten."
    return ("Podman mit dem Paketmanager installieren (z. B. `sudo apt install podman`), "
            "dann Aquaticy neu starten.")


def _podman_auf_pfad() -> None:
    """Nach winget: den neuen Ordner fuer dieses Programm auffindbar machen."""
    if (platform.system() == "Windows" and not shutil.which("podman")
            and (WINDOWS_PODMAN / "podman.exe").exists()):
        os.environ["PATH"] = str(WINDOWS_PODMAN) + os.pathsep + os.environ.get("PATH", "")


def _laufen(befehl: list[str], timeout: float,
            run: Callable[..., Any] = subprocess.run) -> bool:
    try:

        return run(befehl, check=False, timeout=timeout).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _vergessen() -> None:
    """Der gemerkte Stand ("kein Podman") gilt nach einer Installation nicht mehr."""
    from aquaticy import sandbox

    with sandbox._LAUFZEIT_LOCK:
        sandbox._LAUFZEIT.update(bis=0.0, wert=None, bekannt=False)


def run_steps(schritte: list[list[str]], on_step: Callable[[list[str]], None] | None = None,
              run: Callable[..., Any] = subprocess.run) -> bool:
    """Fuehrt die Schritte der Reihe nach aus. Ein `machine init`, das es schon gibt, zaehlt."""
    for befehl in schritte:
        if befehl[0] == "podman":
            _podman_auf_pfad()
        if on_step is not None:
            on_step(befehl)
        zeit = MACHINE_TIMEOUT if befehl[:2] == ["podman", "machine"] else INSTALL_TIMEOUT
        if not _laufen(befehl, zeit, run) and befehl[1:3] != ["machine", "init"]:
            _vergessen()
            return False
    _vergessen()
    return True


def start_machine(run: Callable[..., Any] = subprocess.run) -> bool:
    """macOS/Windows: Podman ist da, aber seine Maschine laeuft nicht (etwa nach einem
    Neustart des Rechners). Startet sie -- ohne Verwalterrechte, ohne Installation."""
    if platform.system() not in ("Darwin", "Windows"):
        return False
    _podman_auf_pfad()
    if not shutil.which("podman"):
        return False
    from aquaticy import sandbox

    if sandbox.find_runtime() is not None:
        return True



    if not _laufen(["podman", "machine", "inspect"], MACHINE_TIMEOUT, run):
        return False
    ok = _laufen(["podman", "machine", "start"], MACHINE_TIMEOUT, run)
    _vergessen()
    return ok


def podman_installed() -> bool:
    """Liegt Podman (oder Docker) schon auf dem Rechner -- auch wenn es gerade nicht laeuft?"""
    _podman_auf_pfad()
    return bool(shutil.which("podman") or shutil.which("docker"))
