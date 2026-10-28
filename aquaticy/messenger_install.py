"""WhatsApp und Signal fuer die Direktverbindung einrichten (12.7.8 Terra v2).

Die Direktverbindung (aquaticy/messenger_native.py) braucht zwei Dinge ausserhalb von Python:

* **WhatsApp:** das Paket neonize (ist seit Terra v2 eine feste Abhaengigkeit von Aquaticy) und
  auf Linux und macOS die Bibliothek libmagic. Sie liegt im Paketmanager und braucht
  Verwalterrechte -- darum nur im Terminal, mit angezeigten Befehlen und nach Rueckfrage
  (wie Podman, aquaticy/vm_install.py).
* **Signal:** das Programm signal-cli. Aquaticy laedt es von GitHub, wie llama.cpp und
  cloudflared: nur ueber HTTPS von den Download-Servern von GitHub, nur mit der
  veroeffentlichten SHA-256-Pruefsumme, sicher entpackt und erst nach einem Startversuch
  uebernommen. Das braucht keine Verwalterrechte. Auf Linux mit x86-64 gibt es eine fertige
  Fassung ohne Java; sonst braucht signal-cli ein Java ab Version 21.

Nichts davon laeuft aus dem Browser: Was auf dem Rechner installiert wird, entscheidet, wer am
Rechner sitzt. Im Container-Abbild ist signal-cli schon dabei (``/opt/aquaticy/signal-cli``).
"""

from __future__ import annotations

import contextlib
import os
import platform
import re
import shutil
import subprocess  # nosec B404 -- feste Befehle, ohne Shell
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

SIGNAL_API = "https://api.github.com/repos/AsamK/signal-cli"
SIGNAL_TAG_RE = re.compile(r"^v\d{1,2}\.\d{1,3}\.\d{1,3}$")
SIGNAL_ENV = "AQUATICY_SIGNAL_CLI"
SYSTEM_SIGNAL_DIR = Path("/opt/aquaticy/signal-cli")
SIGNAL_FOLDER = "signal-cli"
MAX_API_BYTES = 8 * 1024 * 1024
MIN_JAVA = 21
NEIN = "messenger-install-abgelehnt"


class InstallError(RuntimeError):
    """Etwas ging schief -- der Text ist fuer Menschen gedacht."""


def _exe(name: str) -> str:
    return name + (".exe" if os.name == "nt" else "")


def _machine() -> str:
    maschine = platform.machine().lower()
    return {"amd64": "x86_64", "arm64": "aarch64"}.get(maschine, maschine)


# ---------------------------------------------------------------------------------------------
# WhatsApp: libmagic
# ---------------------------------------------------------------------------------------------

_LIBMAGIC_LINUX: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = (
    ("apt-get", (("apt-get", "update"), ("apt-get", "install", "-y", "libmagic1"))),
    ("dnf", (("dnf", "install", "-y", "file-libs"),)),
    ("yum", (("yum", "install", "-y", "file-libs"),)),
    ("pacman", (("pacman", "-S", "--needed", "--noconfirm", "file"),)),
    ("zypper", (("zypper", "--non-interactive", "install", "libmagic1"),)),
    ("apk", (("apk", "add", "libmagic"),)),
)


def whatsapp_problem() -> str:
    """Leer, wenn die Direktverbindung zu WhatsApp laeuft; sonst, was fehlt."""
    from aquaticy import messenger_native

    return messenger_native.neonize_available()[1]


def libmagic_steps() -> list[list[str]] | None:
    """Die Befehle, die libmagic einrichten -- oder None, wenn es keinen bekannten Weg gibt."""
    from aquaticy.vm_install import _root

    system = platform.system()
    if system == "Linux":
        for werkzeug, schritte in _LIBMAGIC_LINUX:
            if not shutil.which(werkzeug):
                continue
            if _root():
                return [list(s) for s in schritte]
            if not shutil.which("sudo"):
                return None
            return [["sudo", *s] for s in schritte]
        return None
    if system == "Darwin":
        return [["brew", "install", "libmagic"]] if shutil.which("brew") else None
    return None


def libmagic_hint() -> str:
    if platform.system() == "Darwin":
        return "Installiere Homebrew (brew.sh), dann `brew install libmagic`."
    return ("Installiere die Bibliothek libmagic mit dem Paketmanager "
            "(z. B. `sudo apt install libmagic1`).")


def install_libmagic(on_step: Callable[[list[str]], None] | None = None,
                     run: Callable[..., Any] = subprocess.run) -> bool:
    """Fuehrt die Schritte aus. Danach prueft Aquaticy neonize neu."""
    from aquaticy import messenger_native
    from aquaticy.vm_install import INSTALL_TIMEOUT, _laufen

    schritte = libmagic_steps()
    if schritte is None:
        return False
    for befehl in schritte:
        if on_step is not None:
            on_step(befehl)
        if not _laufen(befehl, INSTALL_TIMEOUT, run):
            return False
    messenger_native.neonize_available.cache_clear()
    return not whatsapp_problem()


# ---------------------------------------------------------------------------------------------
# Signal: signal-cli
# ---------------------------------------------------------------------------------------------

def managed_dir(data_dir: Path) -> Path:
    return Path(data_dir) / SIGNAL_FOLDER


def _in_folder(ordner: Path) -> Path | None:
    for kandidat in (ordner / _exe("signal-cli"), ordner / "app" / "bin" / "signal-cli"):
        with contextlib.suppress(OSError):
            if kandidat.is_file() and os.access(kandidat, os.X_OK):
                return kandidat
    return None


def find_signal_cli(data_dir: Path | None = None) -> Path | None:
    """Ein vorhandenes signal-cli: eingetragen, selbst geladen, mitgeliefert, im Pfad."""
    from aquaticy.llamacpp import _trusted

    eingetragen = os.environ.get(SIGNAL_ENV, "").strip()
    if eingetragen:
        pfad = Path(eingetragen).expanduser()
        return pfad if pfad.is_file() else None
    if data_dir is None:
        from aquaticy.config import get_settings

        data_dir = Path(get_settings().data_dir)
    eigener = _in_folder(managed_dir(data_dir))
    if eigener is not None:
        return eigener
    mitgeliefert = _in_folder(SYSTEM_SIGNAL_DIR)
    if mitgeliefert is not None and _trusted(SYSTEM_SIGNAL_DIR):
        return mitgeliefert
    gefunden = shutil.which("signal-cli")
    return Path(gefunden) if gefunden else None


def java_major(run: Callable[..., Any] = subprocess.run) -> int:
    """Die Hauptversion von Java -- 0, wenn es keins gibt."""
    java = shutil.which("java")
    if not java:
        return 0
    try:
        fertig = run([java, "-version"], capture_output=True, text=True, timeout=30,
                     check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return 0
    ausgabe = (fertig.stderr or "") + (fertig.stdout or "")
    treffer = re.search(r'version "(\d+)(?:\.(\d+))?', ausgabe)
    if not treffer:
        return 0
    haupt = int(treffer.group(1))
    return int(treffer.group(2) or 0) if haupt == 1 else haupt


def signal_asset_name(tag: str, *, system: str = "", machine: str = "",
                      java: int | None = None) -> tuple[str, str]:
    """(Dateiname, Art) -- Art ist "native" oder "jvm". Leerer Name: kein Weg auf diesem System."""
    if not SIGNAL_TAG_RE.fullmatch(tag):
        return "", ""
    version = tag[1:]
    system = (system or platform.system()).lower()
    maschine = machine or _machine()
    if system == "linux" and maschine == "x86_64":
        return f"signal-cli-{version}-Linux-native.tar.gz", "native"
    if system in ("linux", "darwin") and (java_major() if java is None else java) >= MIN_JAVA:
        return f"signal-cli-{version}.tar.gz", "jvm"
    return "", ""


def signal_hint() -> str:
    system = platform.system()
    if system == "Windows":
        return ("Auf Windows richtet Aquaticy signal-cli nicht ein. Installiere es selbst "
                f"(github.com/AsamK/signal-cli) und trage den Pfad in {SIGNAL_ENV} ein.")
    if system in ("Linux", "Darwin"):
        return (f"Hier braucht signal-cli ein Java ab Version {MIN_JAVA}. Installiere es "
                "(z. B. „sudo apt install openjdk-21-jre-headless“ oder „brew install "
                "openjdk@21“). Führe dann „aquaticy install-messenger“ noch einmal aus.")
    return ("Installiere signal-cli selbst (github.com/AsamK/signal-cli) "
            f"und trage den Pfad in {SIGNAL_ENV} ein.")


def _latest_release(http: httpx.Client) -> dict[str, Any]:
    import json

    from aquaticy import llamacpp

    try:
        with http.stream("GET", SIGNAL_API + "/releases/latest",
                         headers=llamacpp._headers()) as antwort:
            roh = b""
            for stueck in antwort.iter_bytes(64 * 1024):
                roh += stueck
                if len(roh) > MAX_API_BYTES:
                    raise InstallError("GitHub hat unerwartet geantwortet.")
            status = antwort.status_code
    except httpx.HTTPError as exc:
        raise InstallError(f"GitHub ist nicht erreichbar ({type(exc).__name__}).") from exc
    if status != 200:
        raise InstallError(f"GitHub antwortet mit {status}.")
    try:
        daten = json.loads(roh)
    except ValueError as exc:
        raise InstallError("GitHub hat unerwartet geantwortet.") from exc
    if not isinstance(daten, dict) or not SIGNAL_TAG_RE.fullmatch(str(daten.get("tag_name"))):
        raise InstallError("GitHub hat unerwartet geantwortet.")
    return daten


def _starts(programm: Path) -> bool:
    try:
        fertig = subprocess.run([str(programm), "--version"], capture_output=True,  # nosec B603
                                timeout=120, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return False
    return fertig.returncode == 0


def install_signal_cli(data_dir: Path, *, target: Path | None = None,
                       http: httpx.Client | None = None,
                       check: Callable[[Path], bool] | None = None,
                       java: int | None = None) -> Path:
    """Laedt signal-cli -- nur mit veroeffentlichter Pruefsumme. Returns: das Programm.

    Ohne *target* landet es im Datenordner (``signal-cli/``); ein vorheriges wird ersetzt.
    """
    from aquaticy import llamacpp

    eigener = http is None
    http = http or llamacpp.client()
    ordner = Path(target) if target else managed_dir(data_dir)
    ordner.parent.mkdir(parents=True, exist_ok=True)
    arbeit = Path(tempfile.mkdtemp(dir=ordner.parent, prefix=".neu-signal-"))
    try:
        daten = _latest_release(http)
        name, art = signal_asset_name(str(daten["tag_name"]), java=java)
        if not name:
            raise InstallError(signal_hint())
        asset = next((a for a in daten.get("assets") or []
                      if isinstance(a, dict) and a.get("name") == name), None)
        if asset is None:
            raise InstallError(f"Die Veröffentlichung enthält {name} nicht.")
        archiv = arbeit / name
        inhalt = arbeit / "inhalt"
        inhalt.mkdir()
        try:
            llamacpp.download(asset, archiv, http=http)
            llamacpp.unpack_tar(archiv, inhalt)
        except llamacpp.LlamaError as exc:
            raise InstallError(str(exc)) from exc
        fertig = arbeit / "fertig"
        fertig.mkdir()
        if art == "native":
            programm = llamacpp._find(inhalt, "signal-cli")
            if programm is None:
                raise InstallError("Im Archiv fehlt signal-cli.")
            shutil.move(str(programm), str(fertig / _exe("signal-cli")))
            start = fertig / _exe("signal-cli")
        else:
            wurzel = llamacpp._find(inhalt, "signal-cli")
            if wurzel is None or wurzel.parent.name != "bin":
                raise InstallError("Im Archiv fehlt signal-cli.")
            shutil.move(str(wurzel.parent.parent), str(fertig / "app"))
            start = fertig / "app" / "bin" / "signal-cli"
        start.chmod(0o755)
        if not (check or _starts)(start):
            raise InstallError("signal-cli startet auf diesem System nicht."
                               + (f" Es braucht Java {MIN_JAVA} oder neuer."
                                  if art == "jvm" else ""))
        alt = arbeit / "alt"
        if ordner.exists():
            os.replace(ordner, alt)
        try:
            os.replace(fertig, ordner)
        except OSError:
            if alt.exists():
                os.replace(alt, ordner)  # das bisherige signal-cli bleibt
            raise
        return _in_folder(ordner) or ordner / _exe("signal-cli")
    finally:
        shutil.rmtree(arbeit, ignore_errors=True)
        if eigener:
            http.close()


# ---------------------------------------------------------------------------------------------
# Gesamtstand
# ---------------------------------------------------------------------------------------------

def status(data_dir: Path | None = None) -> dict[str, str]:
    """Was fehlt? Leere Texte heissen: in Ordnung."""
    from aquaticy.messenger_native import NEED_SIGNAL_CLI

    return {"whatsapp": whatsapp_problem(),
            "signal": "" if find_signal_cli(data_dir) else NEED_SIGNAL_CLI}


def main(argv: list[str] | None = None) -> int:
    """``python -m aquaticy.messenger_install signal-cli --dir ORDNER`` (fuers Abbild)."""
    import argparse

    eltern = argparse.ArgumentParser(prog="aquaticy.messenger_install")
    eltern.add_argument("was", choices=["signal-cli"])
    eltern.add_argument("--dir", required=True, help="Zielordner (wird ersetzt).")
    args = eltern.parse_args(argv)
    try:
        pfad = install_signal_cli(Path(args.dir).parent, target=Path(args.dir))
    except InstallError as exc:
        print(f"signal-cli: {exc}")
        return 1
    print(f"signal-cli: {pfad}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
