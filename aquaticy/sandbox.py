"""Die virtual machine: eine Wegwerf-Maschine, in der Aquaticy Code ausfuehren darf.

Im Code-Modus laesst sich eine abgeschottete Umgebung zuschalten. Darin darf
Aquaticy alles -- Dateien anlegen, Programme starten, Tests laufen lassen --,
nur eines nicht: heraus. Diese Datei ist die Wand.

**Warum ueberhaupt eine Wand.** Code, den ein Sprachmodell schreibt, ist
fremder Code. Er kann falsch sein, er kann bei einem praeparierten Prompt
boesartig sein, und er kann beides sein, ohne dass man es ihm ansieht. Er
darf deshalb nie auf dem Rechner des Nutzers laufen -- auch nicht "nur kurz"
und auch nicht "nur zum Testen".

**Was die Wand ist.** Nach dem Stand der Technik (Stand 2026) reicht ein
gewoehnlicher Container fuer fremden Code nicht mehr: Kernel und Container
teilen sich denselben Kern, und eine Kernel-Luecke fuehrt aus jedem Container
heraus. Die drei belastbaren Stufen sind, von stark nach schwach:

1. **MicroVM** (Firecracker, Kata) -- eigener Kernel auf Hardware-
   Virtualisierung. Was drinnen passiert, bleibt hinter der CPU-Grenze.
2. **gVisor** (`runsc`) -- ein Kern im Nutzerraum faengt die Systemaufrufe ab
   und beantwortet sie selbst; das Programm sieht den echten Kernel nie.
3. **Container ohne Wurzelrechte** (rootless Podman) -- ein Ausbruch landet in
   einem unprivilegierten Nutzernamensraum, nicht bei root.

Aquaticy nimmt, was da ist, in genau dieser Reihenfolge, und faellt niemals auf
"dann eben direkt auf dem Rechner" zurueck. Ist keine der Stufen vorhanden,
gibt es die virtual machine nicht, und das Werkzeug sagt, was zu installieren ist.

**Womit die Wand zusaetzlich gehaertet wird** -- jede Zeile hat einen Grund:

* `--network none` -- kein Netz. Weder hinaus noch ins Heimnetz. Damit ist der
  haeufigste Missbrauch (Daten abfliessen lassen, Nachladen von Schadcode) an
  der Wurzel erledigt.
* `--cap-drop ALL` -- keine Linux-Faehigkeiten. Kein Mounten, keine rohen
  Sockets, keine Kernelmodule.
* `--security-opt no-new-privileges` -- ein setuid-Programm kann drinnen keine
  Rechte mehr hinzugewinnen.
* `--read-only` -- das Wurzeldateisystem ist unveraenderlich. Geschrieben wird
  nur in `/work` und in ein kleines `/tmp` im Arbeitsspeicher.
* `--user` auf eine unprivilegierte Kennung -- niemand arbeitet als root.
* `--memory`, `--cpus`, `--pids-limit`, `--ulimit` -- eine Endlosschleife, eine
  Gabelbombe oder ein Speicherfresser bringt den Rechner nicht in die Knie.
* Keine Umgebungsvariablen von aussen. Die Schluessel des Nutzers haben in der
  virtual machine nichts zu suchen, und sie kommen auch nicht hinein.
* Kein Verzeichnis des Rechners wird hineingereicht. Dateien gehen nur durch
  das Werkzeug hinein und heraus, ueber die Standardeingabe des Prozesses.

**Was danach uebrig bleibt: nichts.** Zwanzig Minuten nach der letzten Nutzung
werden Behaelter und Datentraeger geloescht. Beim naechsten Mal entsteht eine
neue, leere virtual machine. Auch beim Beenden des Programms wird aufgeraeumt.

**User mode.** Auf Wunsch (Einstellungen -> virtual machine) wird die virtual machine ein
kleiner Desktop, den Aquaticy bedient wie ein Mensch: Bildschirm ansehen,
klicken, tippen, Programme oeffnen (siehe aquaticy/desktop.py). Dafuer
aendert sich genau zweierlei, und beides ist hier begruendet:

* Es gibt **Internet** -- aber **kein Heimnetz**. Beim Start setzt ein Skript
  im Abbild (docker/desktop/aquaticy-netz) als root eine Sperre fuer alle
  privaten und lokalen Bereiche; dafuer bekommt der Behaelter als einzige
  Faehigkeit `NET_ADMIN`. Alles andere laeuft weiter als unprivilegierter
  Nutzer ohne jede Faehigkeit -- die Sperre kann von drinnen niemand aendern.
  Aquaticy liest die Regeln danach selbst nach. Fehlt auch nur ein Bereich,
  wird die virtual machine sofort wieder abgebaut: ohne Sperre kein User mode.
* Mehr Prozesse und offene Dateien, ein Aufraeumer (`tini`) als erster
  Prozess und ein beschreibbares `/run` -- ein Browser ist kein Skript.

Alles andere bleibt: kein root, unveraenderliches Wurzeldateisystem, keine
Verzeichnisse und keine Umgebungsvariablen vom Rechner, feste Grenzen fuer
Speicher und Prozessor, Loeschen nach zwanzig Minuten Ruhe.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

IDLE_MINUTES = 20


CPUS = 1
MEMORY_MB = 1024
DISK_GB = 4







VM_SIZES: dict[str, dict[str, int]] = {
    "normal": {"cpus": CPUS, "memory_mb": MEMORY_MB, "disk_gb": DISK_GB},
    "plus": {"cpus": 4, "memory_mb": 6144, "disk_gb": 20},
}




BLENDER_TIMEOUT = 90


PID_LIMIT = 256
FILE_LIMIT = 512


COMMAND_TIMEOUT = 30
MAX_TIMEOUT = 120



MAX_OUTPUT = 8000


MAX_READ_BYTES = 200_000





MAX_FILE_BYTES = 20 * 1024 * 1024


MAX_LIST = 500




DEFAULT_IMAGE = "docker.io/library/python:3.12-slim"


WORKDIR = "/work"


RUN_AS = "1000:1000"


DESKTOP_IMAGE = "aquaticy-werkstatt-desktop:local"




DESKTOP_PID_LIMIT = 1024
DESKTOP_FILE_LIMIT = 4096

# Ein Desktop mit Firefox (WhatsApp Web) braucht mehr als die Voreinstellung der normalen
# virtual machine (1 GB, 1 Kern): Der Tab stuerzt sonst ab (12.6.8 Astra). Der gemeinsame
# Speicher (/dev/shm) zaehlt zum Speicher des Behaelters.
DESKTOP_MIN_MEMORY_MB = 2048
DESKTOP_MIN_CPUS = 2
DESKTOP_SHM = "512m"


DISPLAY = ":1"


DESKTOP_HELPER = "aquaticy-desktop"
NETWORK_SCRIPT = "/usr/local/sbin/aquaticy-netz"




BLOCKED_RANGES = (
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.168.0.0/16",
)




ROOT_PATH = "/usr/sbin:/sbin:/usr/bin:/bin"



MAX_SHOT_BYTES = 5 * 1024 * 1024


class SandboxUnavailable(RuntimeError):
    """Es gibt keine belastbare Abschottung auf diesem Rechner."""


@dataclass(frozen=True)
class Runtime:
    """Womit die virtual machine betrieben wird."""

    binary: str

    kind: str
    label: str

    extra: tuple[str, ...] = ()

    @property
    def strength(self) -> str:
        """Ein Satz darueber, wie stark die Wand hier ist."""
        return {
            "gvisor": (
                "gVisor: die Systemaufrufe beantwortet ein Kern im Nutzerraum, "
                "der echte Kernel wird nicht angefasst."
            ),
            "podman": (
                "Podman ohne Wurzelrechte: ein Ausbruch landet in einem "
                "unprivilegierten Nutzernamensraum, nicht bei root."
            ),
            "podman-root": (
                "Podman mit Wurzelrechten und gehaertetem Profil: kein Netz, keine "
                "Faehigkeiten, unveraenderliches Wurzeldateisystem. Der Kernel ist "
                "geteilt -- ohne Wurzelrechte oder mit gVisor waere der Abstand groesser."
            ),
            "docker": (
                "Docker mit gehaertetem Profil: kein Netz, keine Faehigkeiten, "
                "unveraenderliches Wurzeldateisystem. Der Kernel ist geteilt -- "
                "fuer noch mehr Abstand waere gVisor oder eine MicroVM noetig."
            ),
        }[self.kind]


def _runs(binary: str, *args: str, timeout: float = 8.0) -> subprocess.CompletedProcess[str]:
    """Ruft die Laufzeit auf -- ohne Shell, damit nichts interpretiert wird."""
    return subprocess.run(
        [binary, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )



_CLEANUP_RE = re.compile(r"^\s*(rm|rmdir|truncate|du|ls|df)(\s[^;&|`$<>(){}\n]*)?$")


def cleanup_command(command: str) -> bool:
    """Ist das ein reiner Aufraeumbefehl -- ohne Verkettung, Umleitung oder Ersetzung?"""
    return bool(_CLEANUP_RE.fullmatch(command or ""))


def _runs_capped(
    binary: str, *args: str, timeout: float = 8.0
) -> subprocess.CompletedProcess[str]:
    """Fuehrt einen virtual-machine-Befehl mit begrenzten Empfangspuffern aus.

    Die Begrenzung muss hier am Host-Rohr liegen: ein Container-Speicherlimit
    verhindert nicht, dass sein Client beliebig viel Ausgabe in Aquaticys
    Hauptprozess puffert.
    """
    command = [binary, *args]
    stdout = bytearray()
    stderr = bytearray()

    def drain(pipe: Any, target: bytearray, limit: int) -> None:
        while chunk := pipe.read(8192):
            remaining = limit - len(target)
            if remaining > 0:
                target.extend(chunk[:remaining])

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdout is not None and process.stderr is not None


    readers = [
        threading.Thread(target=drain, args=(process.stdout, stdout, MAX_OUTPUT * 2)),
        threading.Thread(target=drain, args=(process.stderr, stderr, MAX_OUTPUT)),
    ]
    for reader in readers:
        reader.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise
    finally:
        for reader in readers:
            reader.join()
    return subprocess.CompletedProcess(
        command,
        process.returncode,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def _works(binary: str) -> bool:
    """Antwortet die Laufzeit ueberhaupt? Ein installierter Client ohne
    laufenden Dienst ist so gut wie keiner."""


    feld = "{{.Version.Version}}" if Path(binary).name.startswith("podman") \
        else "{{.ServerVersion}}"
    try:
        return _runs(binary, "info", "--format", feld).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _has_gvisor(binary: str) -> bool:
    """Kennt diese Laufzeit `runsc`? Nur Docker meldet das ueber `info`.

    Podman fuehrt keine Liste der Laufzeiten; wie bisher laeuft es dann ohne
    gVisor als Podman ohne Wurzelrechte.
    """
    if Path(binary).name.startswith("podman"):
        return False
    try:
        found = _runs(binary, "info", "--format", "{{.Runtimes}}")
    except (OSError, subprocess.SubprocessError):
        return False
    return found.returncode == 0 and "runsc" in found.stdout



PROXY_VARS = tuple(n for name in ("HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY", "ALL_PROXY",
                                   "NO_PROXY") for n in (name, name.lower()))


def quota_unsupported_message(stderr: str) -> bool:
    """Sagt die Laufzeit, dass sie keine Plattengrenze je Behaelter kann?

    Docker: "--storage-opt is supported only for overlay over xfs ...". Podman
    (11.2.2 Sol): "storage option overlay.size and overlay.inodes only supported
    for backingFS XFS" -- bis dahin nicht erkannt, und auf ext4 (dem Standard der
    meisten Linux-Rechner) startete die virtual machine mit Podman nie.
    """
    text = str(stderr or "").lower()
    return any(zeichen in text for zeichen in (
        "storage-opt", "storage option", "overlay.size", "backingfs",
        "filesystem does not support, or has not enabled quotas"))


def _podman_rootless() -> bool:
    """Laeuft Podman ohne Wurzelrechte? Im Zweifel nein -- dann steht nichts Falsches da."""
    try:
        found = _runs("podman", "info", "--format", "{{.Host.Security.Rootless}}")
    except (OSError, subprocess.SubprocessError):
        return False
    return found.returncode == 0 and found.stdout.strip().lower() == "true"


def find_runtime() -> Runtime | None:
    """Sucht die staerkste verfuegbare Abschottung.

    Returns:
        Die Laufzeit, oder `None`, wenn es keine gibt. Dann gibt es auch keine
        virtual machine -- ein Rueckfall auf den Rechner selbst waere genau das, was
        diese Datei verhindern soll.
    """


    da = [b for b in ("podman", "docker") if shutil.which(b) and _works(b)]
    for binary in da:
        if _has_gvisor(binary):
            return Runtime(binary, "gvisor", f"{binary} + gVisor", ("--runtime", "runsc"))
    if "podman" in da:

        if _podman_rootless():
            return Runtime("podman", "podman", "Podman (ohne Wurzelrechte)")
        return Runtime("podman", "podman-root", "Podman (gehaertet)")
    if "docker" in da:
        return Runtime("docker", "docker", "Docker (gehaertet)")
    return None




RUNTIME_TTL = 60.0
_LAUFZEIT: dict[str, Any] = {"bis": 0.0, "wert": None, "bekannt": False, "sucht": False}
_LAUFZEIT_LOCK = threading.Lock()


def runtime_cached() -> Runtime | None:
    """:func:`find_runtime`, eine Minute gemerkt (11.2.2 Sol). Wartet, wenn es sucht."""
    with _LAUFZEIT_LOCK:
        if _LAUFZEIT["bekannt"] and time.monotonic() < _LAUFZEIT["bis"]:
            return _LAUFZEIT["wert"]
    wert = find_runtime()
    with _LAUFZEIT_LOCK:
        _LAUFZEIT.update(bis=time.monotonic() + RUNTIME_TTL, wert=wert, bekannt=True)
    return wert


def runtime_known() -> tuple[bool, Runtime | None]:
    """Was zuletzt ueber Podman/Docker bekannt war -- ohne zu warten (11.2.2 Sol).

    Eine Anfrage darf nie auf `docker info` warten (Fund 9.5.18). Ist der Stand
    aelter als :data:`RUNTIME_TTL` oder noch keiner da, sucht ein kurzer Faden im
    Hintergrund; bis dahin gilt der alte Stand. Returns: (bekannt, Laufzeit).
    """
    with _LAUFZEIT_LOCK:
        bekannt, wert = bool(_LAUFZEIT["bekannt"]), _LAUFZEIT["wert"]
        alt = not bekannt or time.monotonic() >= _LAUFZEIT["bis"]
        suchen = alt and not _LAUFZEIT["sucht"]
        if suchen:
            _LAUFZEIT["sucht"] = True
    if suchen:
        def neu_suchen() -> None:
            try:
                runtime_cached()
            except Exception:
                pass
            finally:
                with _LAUFZEIT_LOCK:
                    _LAUFZEIT["sucht"] = False

        try:
            threading.Thread(target=neu_suchen, name="aquaticy-laufzeit", daemon=True).start()
        except RuntimeError:

            with _LAUFZEIT_LOCK:
                _LAUFZEIT["sucht"] = False
    return bekannt, wert


@dataclass
class RunResult:
    """Was ein Befehl in der virtual machine hinterlassen hat."""

    exit_code: int
    stdout: str
    stderr: str
    seconds: float
    timed_out: bool = False
    truncated: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "seconds": round(self.seconds, 2),
        }
        if self.timed_out:
            payload["note"] = (
                "Abgebrochen: der Befehl lief laenger als erlaubt. Lass ihn "
                "kuerzer laufen oder teile ihn auf."
            )
        if self.truncated:
            payload["truncated"] = True
        return payload


def _cut(text: str, limit: int = MAX_OUTPUT) -> tuple[str, bool]:
    """Kuerzt lange Ausgaben und sagt, ob gekuerzt wurde."""
    if len(text) <= limit:
        return text, False
    half = limit // 2
    return text[:half] + "\n… [gekuerzt] …\n" + text[-half:], True





PATH_CHARS = re.compile(r"^[A-Za-z0-9._/\- ]+$")


def safe_path(path: str) -> str:
    """Prueft einen Pfad in der virtual machine.

    Erlaubt ist alles unterhalb von `/work`. Das ist keine Sicherheitsgrenze --
    die ist die virtual machine selbst --, sondern Ordnung: Dateien, die ausserhalb
    liegen, waeren beim naechsten Start weg und wuerden nur verwirren.

    Raises:
        ValueError: Wenn der Pfad hinausfuehrt.
    """
    import posixpath

    raw = (path or "").strip()
    if not raw:
        raise ValueError("Ohne Pfad geht es nicht.")
    if not PATH_CHARS.fullmatch(raw):
        raise ValueError(
            "Im Pfad sind nur Buchstaben, Ziffern, Punkt, Strich, Unterstrich und "
            f"Schraegstrich erlaubt -- '{raw}' hat anderes darin."
        )
    full = raw if raw.startswith("/") else posixpath.join(WORKDIR, raw)
    full = posixpath.normpath(full)
    if full != WORKDIR and not full.startswith(WORKDIR + "/"):
        raise ValueError(f"Nur Pfade unterhalb von {WORKDIR} -- '{raw}' liegt ausserhalb.")
    return full



ADDON_VOLUME_RE = re.compile(r"^aquaticy-addon-[0-9a-f]{12}-[a-z_]{2,20}$")

ADDON_PATH_RE = re.compile(r"^/addons/[a-z_]{2,20}$")

ADDON_LABEL = "aquaticy-addon=1"



BUILD_TIMEOUT = 3600

DESKTOP_HELPERS = ("aquaticy-desktop", "aquaticy-netz", "aquaticy-addons")

_BUILD_LOCK = threading.Lock()


def short_name_problem(text: str) -> bool:
    """Meldet die Laufzeit "short-name ... did not resolve" (12.6.6 Luna)?

    Podman sucht einen Namen ohne Registry (``python:3.12-slim``) nur dort, wo die
    ``registries.conf`` es erlaubt. Steht dort nichts, ist das Abbild "unbekannt" --
    auch dann, wenn es nur noch nicht gebaut wurde.
    """
    klein = (text or "").lower()
    return "short-name" in klein and "did not resolve" in klein


def image_present(runtime: Runtime, image: str) -> bool:
    """Gibt es dieses Abbild schon auf dem Rechner? (``image inspect`` kennt Docker und Podman.)"""
    try:
        return _runs(runtime.binary, "image", "inspect", image, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def desktop_recipe() -> tuple[Path, Path] | None:
    """Rezept und Hilfen aus dem installierten Paket oder dem eigenen Projektordner.

    Nie im Arbeitsordner suchen: Dort koennte ein fremdes Dockerfile liegen.
    """
    paket = Path(__file__).resolve().parent
    kandidaten = [paket / "_desktop"]
    if (paket.parent / "pyproject.toml").is_file():
        kandidaten.append(paket.parent / "docker")
    for wurzel in kandidaten:
        rezept = wurzel / "workshop-desktop.Dockerfile"
        hilfen = wurzel / "desktop"
        if rezept.is_file() and all((hilfen / name).is_file() for name in DESKTOP_HELPERS):
            return rezept, hilfen
    return None


def missing_image_text(runtime: Runtime, image: str) -> str:
    """Ein Satz fuer Menschen, wenn ein Abbild fehlt -- statt der Meldung von Podman."""
    if image == DESKTOP_IMAGE:
        return (
            f"Das Desktop-Abbild '{image}' gibt es auf diesem Rechner noch nicht. Aquaticy "
            "baut es beim Installieren eines Add-ons selbst. Von Hand, im Ordner des "
            f"Projekts: '{runtime.binary} build -f docker/workshop-desktop.Dockerfile "
            f"-t {image} .'"
        )
    return (
        f"Das Abbild '{image}' gibt es auf diesem Rechner nicht. Hol es mit "
        f"'{runtime.binary} pull {image}' -- mit vollem Namen samt Registry, zum Beispiel "
        "docker.io/library/... -- oder wähle ein anderes in AQUATICY_VM_DESKTOP_IMAGE."
    )


def build_desktop_image(runtime: Runtime) -> None:
    """Baut das Desktop-Abbild aus docker/workshop-desktop.Dockerfile (12.6.6 Luna).

    Gebaut wird aus einem kleinen, eigenen Ordner: das Rezept und die drei
    Hilfsprogramme, sonst nichts. Das dauert beim ersten Mal einige Minuten.

    Raises:
        SandboxUnavailable: Wenn das Rezept fehlt oder das Bauen scheitert.
    """
    gefunden = desktop_recipe()
    if gefunden is None:
        raise SandboxUnavailable(
            "Die Bauvorlage für den Desktop fehlt in dieser Installation. "
            "Installiere Aquaticy mit allen Paketdateien neu. "
            + missing_image_text(runtime, DESKTOP_IMAGE)
        )
    rezept, hilfen = gefunden
    with tempfile.TemporaryDirectory(prefix="aquaticy-abbild-") as ordner:
        wurzel = Path(ordner)
        (wurzel / "docker" / "desktop").mkdir(parents=True)
        ziel = wurzel / "docker" / "workshop-desktop.Dockerfile"
        shutil.copy2(rezept, ziel)
        for name in DESKTOP_HELPERS:
            shutil.copy2(hilfen / name, wurzel / "docker" / "desktop" / name)
        try:
            gebaut = _runs(runtime.binary, "build", "-f", str(ziel), "-t", DESKTOP_IMAGE,
                           str(wurzel), timeout=BUILD_TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            raise SandboxUnavailable(
                "Das Bauen des Desktop-Abbilds dauert zu lange (über eine Stunde). Prüfe die "
                "Internetverbindung und versuch es noch einmal."
            ) from exc
    if gebaut.returncode != 0:
        raise SandboxUnavailable(
            "Das Desktop-Abbild ließ sich nicht bauen: "
            + (gebaut.stderr.strip() or gebaut.stdout.strip())[-400:]
            + (" (Podman findet Abbilder ohne Registry-Namen nicht: In "
               "/etc/containers/registries.conf fehlt 'unqualified-search-registries'.)"
               if short_name_problem(gebaut.stderr) else "")
        )


def ensure_image(runtime: Runtime, image: str, *, build: bool = False,
                 progress: Any = None) -> None:
    """Sorgt dafuer, dass *image* da ist -- das Desktop-Abbild baut Aquaticy bei Bedarf.

    Raises:
        SandboxUnavailable: Mit einem Satz, was fehlt und was zu tun ist.
    """
    if image_present(runtime, image):
        return
    if image == DESKTOP_IMAGE and build:
        with _BUILD_LOCK:
            if image_present(runtime, image):
                return
            if progress is not None:
                progress("Baut das Desktop-Abbild (einmalig, 5 bis 20 Minuten) …")
            build_desktop_image(runtime)
        return
    raise SandboxUnavailable(missing_image_text(runtime, image))


def ensure_addon_volume(runtime: Runtime, volume: str, image: str) -> None:
    """Legt den Datentraeger eines Add-ons an (falls noetig) und gibt ihn 1000.

    Raises:
        SandboxUnavailable: Wenn das nicht geht.
    """
    if not ADDON_VOLUME_RE.fullmatch(volume):
        raise SandboxUnavailable(f"Ungueltiger Name fuer einen Add-on-Datentraeger: {volume}")
    da = _runs(runtime.binary, "volume", "inspect", volume, timeout=20)
    if da.returncode != 0:
        made = _runs(
            runtime.binary, "volume", "create", "--label", ADDON_LABEL, volume, timeout=20
        )
        if made.returncode != 0:
            raise SandboxUnavailable(
                "Datentraeger fuers Add-on liess sich nicht anlegen: " + made.stderr.strip()[:300]
            )
    prepared = _runs(
        runtime.binary,
        "run", "--rm",
        "--network", "none",
        "--cap-drop", "ALL",
        "--cap-add", "CHOWN",
        "--security-opt", "no-new-privileges",
        "--user", "0:0",
        "-v", f"{volume}:/addon",
        image,
        "chown", RUN_AS, "/addon",
        timeout=120,
    )
    if prepared.returncode != 0:
        if short_name_problem(prepared.stderr):

            raise SandboxUnavailable(missing_image_text(runtime, image))
        raise SandboxUnavailable(
            "Datentraeger fuers Add-on liess sich nicht vorbereiten: "
            + prepared.stderr.strip()[:300]
        )


def remove_addon_volume(runtime: Runtime, volume: str) -> bool:
    """Loescht den Datentraeger eines Add-ons samt Programm und Anmeldung."""
    if not ADDON_VOLUME_RE.fullmatch(volume):
        return False
    weg = _runs(runtime.binary, "volume", "rm", "--force", volume, timeout=60)
    if weg.returncode == 0:
        return True
    return "no such volume" in weg.stderr.lower()


def addon_volumes(runtime: Runtime, prefix: str) -> list[str]:
    """Welche Add-on-Datentraeger es fuer ein Konto gibt."""
    gefunden = _runs(
        runtime.binary, "volume", "ls", "--quiet", "--filter", f"label={ADDON_LABEL}",
        timeout=30,
    )
    return [
        zeile.strip()
        for zeile in gefunden.stdout.splitlines()
        if zeile.strip().startswith(prefix) and ADDON_VOLUME_RE.fullmatch(zeile.strip())
    ]


class Sandbox:
    """Eine virtual machine: startet auf Bedarf, raeumt sich selbst weg."""

    def __init__(
        self,
        *,
        image: str = "",
        idle_minutes: int = IDLE_MINUTES,
        memory_mb: int = MEMORY_MB,
        disk_gb: int = DISK_GB,
        cpus: int = CPUS,
        on_event: Any = None,
        user_mode: bool = False,
        browser_agent: str = "",
        addon_mounts: dict[str, str] | None = None,
        headless: bool = False,
        internet: bool = False,
        lan: bool = False,
    ) -> None:

        self.user_mode = bool(user_mode)




        self.internet = bool(internet) and not self.user_mode


        self.lan = bool(lan) and (self.user_mode or bool(internet))

        self.browser_agent = browser_agent



        self.addon_mounts = {
            volume: ziel
            for volume, ziel in (addon_mounts or {}).items()
            if ADDON_VOLUME_RE.fullmatch(volume) and ADDON_PATH_RE.fullmatch(ziel)
        }

        self.headless = bool(headless)


        self.image = image or (DESKTOP_IMAGE if self.netz_offen else DEFAULT_IMAGE)
        self.idle_seconds = max(60, int(idle_minutes) * 60)
        self.memory_mb = max(128, int(memory_mb))
        self.disk_gb = max(1, int(disk_gb))
        self.cpus = max(1, int(cpus))
        if self.user_mode:
            self.memory_mb = max(self.memory_mb, DESKTOP_MIN_MEMORY_MB)
            self.cpus = max(self.cpus, DESKTOP_MIN_CPUS)
        self.on_event = on_event
        self.runtime: Runtime | None = None
        self._name = ""
        self._volume = ""
        self._lock = threading.RLock()
        self._timer: threading.Timer | None = None
        self._quota_warned = False


        self._over_quota = False

        self._quota_ok = True

        self._last_quota_check = 0.0

        self.last_used = 0.0


    @property
    def name(self) -> str:
        return self._name

    @property
    def alive(self) -> bool:
        return bool(self._name)

    def _emit(self, event: str, **payload: Any) -> None:



        if not self.on_event:
            return
        with contextlib.suppress(Exception):
            self.on_event(event, payload)


    def ensure(self) -> str:
        """Startet die virtual machine, falls sie nicht schon laeuft.

        Returns:
            Der Name des Behaelters.

        Raises:
            SandboxUnavailable: Wenn es keine belastbare Abschottung gibt oder
                der Start scheitert.
        """
        with self._lock:
            if self._name and self._running():
                self._touch_locked()
                return self._name
            self._name = ""
            runtime = self.runtime or find_runtime()
            if runtime is None:
                raise SandboxUnavailable(
                    "Auf diesem Rechner gibt es keine Abschottung, der ich fremden "
                    "Code anvertrauen wuerde. Installiere Podman (ohne Wurzelrechte) "
                    "oder Docker; am besten zusaetzlich gVisor. Auf dem Rechner "
                    "selbst fuehre ich nichts aus."
                )
            self.runtime = runtime
            self._check_nested_network()
            token = uuid.uuid4().hex[:12]
            self._name = f"aquaticy-werkstatt-{token}"
            self._volume = f"aquaticy-werkstatt-{token}"
            self._quota_warned = False
            self._emit(
                "vm_start", runtime=runtime.label, image=self.image, user_mode=self.user_mode,
                internet=self.internet,
            )
            try:
                self._create_volume()
                self._start_container()
                if self.netz_offen and not self.lan:
                    self._lock_network()
                if self.user_mode and not self.headless:
                    self._start_desktop()
            except Exception:

                self._destroy_locked("Start fehlgeschlagen")
                raise
            self._touch_locked()
            return self._name

    def _check_nested_network(self) -> None:
        """Im eingeschlossenen Start (Kiste in der Kiste) braucht Netz ein Geraet.

        Die innere virtual machine laeuft dort mit Podman ohne Wurzelrechte, und das
        baut sein Netz ueber /dev/net/tun. Die aeussere Kiste reicht dieses
        Geraet bewusst nicht von selbst herein (compose.sandbox.yaml). Ohne
        diese Pruefung kaeme eine Fehlermeldung von Podman, die niemand
        versteht -- so steht da, was fehlt und wo man es freigibt.
        """
        if not self.netz_offen or os.environ.get("AQUATICY_SANDBOXED") != "1":
            return
        if not Path("/dev/net/tun").exists():
            raise SandboxUnavailable(
                "Im eingeschlossenen Start braucht der User mode das Geraet /dev/net/tun, "
                "damit die virtual machine ins Internet kann. Freigeben in compose.sandbox.yaml "
                "(Abschnitt 'devices', dort erklaert) und neu starten -- oder den User "
                "mode ausschalten."
            )

    def _create_volume(self) -> None:
        """Legt den Datentraeger an und macht ihn fuer die Kennung schreibbar.

        Der Datentraeger gehoert dieser virtual machine allein und verschwindet mit
        ihr. Bind-Mounts vom Rechner gibt es bewusst nicht: was drinnen
        passiert, soll drinnen bleiben.
        """
        runtime = self.runtime
        assert runtime is not None
        made = _runs(runtime.binary, "volume", "create", "--label", instance_label(),
                     self._volume, timeout=20)
        if made.returncode != 0:
            raise SandboxUnavailable(
                "Datentraeger liess sich nicht anlegen: " + made.stderr.strip()[:300]
            )



        prepared = _runs(
            runtime.binary,
            "run", "--rm",
            "--network", "none",
            "--cap-drop", "ALL",
            "--cap-add", "CHOWN",
            "--security-opt", "no-new-privileges",
            "--user", "0:0",
            "-v", f"{self._volume}:{WORKDIR}",
            self.image,
            "chown", RUN_AS, WORKDIR,
            timeout=120,
        )
        if prepared.returncode != 0:
            raise SandboxUnavailable(
                "Die virtual machine liess sich nicht vorbereiten: " + prepared.stderr.strip()[:300]
            )

    def _run_flags(self) -> list[str]:
        """Die Haertung. Jede Zeile steht im Kopf der Datei begruendet."""
        runtime = self.runtime
        assert runtime is not None
        desktop = self.user_mode
        offen = self.netz_offen



        netz = [] if offen else ["--network", "none"]




        faehigkeiten = ["--cap-drop", "ALL",
                        *(("--cap-add", "NET_ADMIN") if offen and not self.lan else ())]
        kein_kopieren = "" if Path(runtime.binary).name.startswith("podman") else ":nocopy"
        prozesse = DESKTOP_PID_LIMIT if desktop else PID_LIMIT
        dateien = DESKTOP_FILE_LIMIT if desktop else FILE_LIMIT
        flags = [
            "run", "--detach",
            "--name", self._name,
            *runtime.extra,

            *netz,
            *faehigkeiten,
            "--security-opt", "no-new-privileges",
            "--read-only",
            "--user", RUN_AS,

            "--memory", f"{self.memory_mb}m",
            "--memory-swap", f"{self.memory_mb}m",
            "--cpus", str(self.cpus),
            "--pids-limit", str(prozesse),
            "--ulimit", f"nofile={dateien}:{dateien}",
            "--ulimit", f"fsize={self.disk_gb * 1024 * 1024 * 1024}",









            "-v", f"{self._volume}:{WORKDIR}{kein_kopieren}",
            *(
                flag
                for volume, ziel in sorted(self.addon_mounts.items())
                for flag in ("-v", f"{volume}:{ziel}{kein_kopieren}")
            ),
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",



            *(("--storage-opt", f"size={self.disk_gb}G") if self._quota_ok else ()),
            "--workdir", WORKDIR,

            "--env", "HOME=" + WORKDIR,
            "--env", "PATH=/usr/local/bin:/usr/bin:/bin",
            "--env", "LANG=C.UTF-8",
            "--env", "PYTHONDONTWRITEBYTECODE=1",




            *(flag for name in PROXY_VARS for flag in ("--env", f"{name}=")),
            *(("--http-proxy=false",) if kein_kopieren == "" else ()),
            "--label", "aquaticy-werkstatt=1",
            "--label", instance_label(),
        ]
        if offen:



            flags += ["--tmpfs", "/run:rw,nosuid,nodev,size=8m"]
        if desktop:
            flags += [

                "--shm-size", DESKTOP_SHM,
                "--env", f"DISPLAY={DISPLAY}",
                "--label", "aquaticy-werkstatt-user=1",
                # Firefox soll bei einem Absturz nichts an Mozilla schicken.
                "--env", "MOZ_CRASHREPORTER_DISABLE=1",
                "--env", "MOZ_CRASHREPORTER_NO_REPORT=1",
            ]
        return flags

    @property
    def netz_offen(self) -> bool:
        """Darf die virtual machine ins Internet (User mode oder Internet, 9.5.31)?"""
        return self.user_mode or getattr(self, "internet", False)

    def _command(self) -> list[str]:
        """Was im Behaelter als erster Prozess laeuft.

        Im User mode startet und beendet der Desktop Programme. Deren
        Ueberbleibsel raeumt nur ein echter erster Prozess weg -- `sleep` tut
        das nicht, und jeder nicht abgeholte Prozess zaehlt gegen die Grenze.
        """
        if self.user_mode:
            return ["tini", "--", "sleep", "infinity"]
        return ["sleep", "infinity"]

    def _start_container(self) -> None:
        runtime = self.runtime
        assert runtime is not None
        args = [
            *self._run_flags(),
            self.image,


            *self._command(),
        ]
        started = _runs(runtime.binary, *args, timeout=300)
        quota_unsupported = quota_unsupported_message(started.stderr)
        if started.returncode != 0 and quota_unsupported:


            self._quota_ok = False
            args = [*self._run_flags(), self.image, *self._command()]
            started = _runs(runtime.binary, *args, timeout=300)
        if started.returncode != 0:
            if self.netz_offen:
                hilfe = (
                    " (Fuer User mode und Internet braucht es das Desktop-Abbild. Bauen mit: "
                    f"'{runtime.binary} build -f docker/workshop-desktop.Dockerfile "
                    f"-t {DESKTOP_IMAGE} .')"
                )
            else:
                hilfe = (
                    f" (Fehlt das Abbild? '{runtime.binary} pull {self.image}' holt es einmalig.)"
                )
            if short_name_problem(started.stderr):

                hilfe = " " + missing_image_text(runtime, self.image)
                started.stderr = "Das Abbild ist nicht da."
            raise SandboxUnavailable(
                "Die virtual machine liess sich nicht starten: "
                + started.stderr.strip()[:300] + hilfe
            )

    def _lock_network(self) -> None:
        """Setzt die Sperre fuers Heimnetz -- und prueft sie selbst nach.

        Das Skript im Abbild laeuft als root, weil nur root mit NET_ADMIN die
        Regeln setzen kann. Danach liest Aquaticy die Regeln aus und verlaesst
        sich nicht auf das "gesperrt" des Skripts: steht auch nur ein Bereich
        nicht darin, gilt die virtual machine als offen -- und wird abgebaut.

        Raises:
            SandboxUnavailable: Wenn die Sperre fehlt oder unvollstaendig ist.
        """
        runtime = self.runtime
        assert runtime is not None
        gesetzt = _runs(
            runtime.binary, "exec", "--user", "0:0", "--env", f"PATH={ROOT_PATH}",
            self._name, NETWORK_SCRIPT,
            timeout=60,
        )
        if gesetzt.returncode != 0 or "gesperrt" not in gesetzt.stdout:
            raise SandboxUnavailable(
                "Die Netzsperre fuers Heimnetz liess sich nicht einrichten -- ohne sie "
                "startet die virtual machine mit Internet nicht. " + gesetzt.stderr.strip()[:300]
            )
        regeln = _runs(
            runtime.binary, "exec", "--user", "0:0", "--env", f"PATH={ROOT_PATH}",
            self._name, "iptables", "-S", "OUTPUT",
            timeout=30,
        )
        fehlt = [
            bereich
            for bereich in BLOCKED_RANGES
            if f"-d {bereich} -j REJECT" not in regeln.stdout
        ]
        if regeln.returncode != 0 or fehlt:
            raise SandboxUnavailable(
                "Die Netzsperre fuers Heimnetz ist unvollstaendig (es fehlt: "
                + (", ".join(fehlt) or "die Regelliste")
                + ") -- ohne sie startet die virtual machine mit Internet nicht."
            )
        self._emit("vm_net", locked=True, ranges=len(BLOCKED_RANGES))

    def _start_desktop(self) -> None:
        """Startet Bildschirm, Fenstermanager und Leiste in der virtual machine."""
        runtime = self.runtime
        assert runtime is not None
        gestartet = _runs(
            runtime.binary,
            "exec", "--user", RUN_AS, "--workdir", WORKDIR, self._name,
            DESKTOP_HELPER, "start", self.browser_agent,
            timeout=90,
        )
        if gestartet.returncode != 0 or "bereit" not in gestartet.stdout:
            raise SandboxUnavailable(
                "Der Desktop in der virtual machine ist nicht hochgekommen: "
                + (gestartet.stderr.strip() or gestartet.stdout.strip())[:300]
            )
        self._emit("vm_desktop", ready=True)

    def desktop(
        self, *args: str, stdin: bytes | None = None, timeout: float = 60, start: bool = True
    ) -> subprocess.CompletedProcess[bytes]:
        """Ruft das Hilfsprogramm des Desktops auf -- mit festen Argumenten.

        Keine Shell, kein Text, der als Befehl gelesen werden koennte: die
        Argumente gehen als Liste an die Laufzeit, getippter Text ueber die
        Standardeingabe.

        Args:
            start: Darf dafuer eine virtual machine entstehen? Ein Blick von aussen
                (die Oberflaeche) soll keine hochfahren -- auch keine, deren
                Behaelter inzwischen verschwunden ist.

        Raises:
            SandboxUnavailable: Wenn die virtual machine nicht im User mode laeuft.
        """
        if not self.user_mode:
            raise SandboxUnavailable(
                "Die virtual machine laeuft nicht im User mode -- den schaltet der Nutzer in "
                "den Einstellungen unter 'virtual machine' ein."
            )
        if start:
            name = self.ensure()
        elif self._name and self._running():
            name = self._name
        else:
            raise SandboxUnavailable("Die virtual machine laeuft gerade nicht.")
        runtime = self.runtime
        assert runtime is not None
        done = subprocess.run(
            [
                runtime.binary, "exec", *(("--interactive",) if stdin is not None else ()),
                "--user", RUN_AS, "--workdir", WORKDIR, name,
                DESKTOP_HELPER, *args,
            ],
            input=stdin,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        self.touch()
        return done

    def addon_helper(
        self, *args: str, timeout: int = 1800
    ) -> subprocess.CompletedProcess[str]:
        """Ruft den Add-on-Installer in der virtual machine auf -- feste Argumente, keine Shell.

        Laenger als ein gewoehnlicher Befehl darf er: Blender ist gut 350 MB gross.
        """
        name = self.ensure()
        runtime = self.runtime
        assert runtime is not None
        return _runs(
            runtime.binary,
            "exec", "--user", RUN_AS, "--workdir", WORKDIR, name,
            "aquaticy-addons", *args,
            timeout=max(10, int(timeout)),
        )

    def screenshot(
        self, *, grid: bool = False, mark: tuple[int, int] | None = None, start: bool = True,
        quality: int | None = None,
    ) -> bytes:
        """Ein Bildschirmfoto als JPEG (quality 30 bis 95; ohne Angabe die Voreinstellung).

        Raises:
            SandboxUnavailable: Ohne User mode oder wenn kein Bild kommt.
        """
        extra: list[str] = []
        if grid:
            extra.append("--grid")
        if mark is not None:
            extra += ["--mark", str(int(mark[0])), str(int(mark[1]))]
        if quality is not None:
            extra += ["--quality", str(max(30, min(95, int(quality))))]
        done = self.desktop("shot", *extra, timeout=40, start=start)
        bild = done.stdout or b""
        if done.returncode != 0 or not bild.startswith(b"\xff\xd8"):
            grund = (done.stderr or b"").decode("utf-8", "replace").strip()[:300]
            raise SandboxUnavailable("Kein Bildschirmfoto bekommen. " + grund)
        if len(bild) > MAX_SHOT_BYTES:
            raise SandboxUnavailable("Das Bildschirmfoto ist unplausibel gross.")
        return bild

    def _running(self) -> bool:
        runtime = self.runtime
        if runtime is None or not self._name:
            return False
        found = _runs(runtime.binary, "inspect", "--format", "{{.State.Running}}", self._name)
        return found.returncode == 0 and found.stdout.strip() == "true"


    def run(self, command: str, timeout: int = COMMAND_TIMEOUT) -> RunResult:
        """Fuehrt *command* in der virtual machine aus.

        Der Befehl geht als Argument an die Laufzeit, nie durch eine Shell auf
        diesem Rechner -- interpretiert wird er erst drinnen.
        """
        command = (command or "").strip()
        if not command:
            raise ValueError("Ohne Befehl gibt es nichts zu tun.")
        limit = max(1, min(int(timeout or COMMAND_TIMEOUT), MAX_TIMEOUT))
        name = self.ensure()
        runtime = self.runtime
        assert runtime is not None
        if self._over_quota and not cleanup_command(command):

            return RunResult(
                exit_code=125, stdout="",
                stderr=(f"[virtual machine] Voll: mehr als {self.disk_gb} GB belegt. Erst "
                        "aufräumen "
                        "-- erlaubt sind jetzt nur rm, rmdir, truncate, du, ls und df, "
                        "jeweils einzeln."),
                seconds=0.0,
            )
        self._emit("vm_run", command=command[:200])
        started = time.monotonic()



        stop = threading.Event()
        waechter = None
        if not self._quota_ok:
            waechter = threading.Thread(target=self._watch_disk, args=(stop,), daemon=True)
            waechter.start()
        try:
            done = _runs_capped(
                runtime.binary,
                "exec", "--user", RUN_AS, "--workdir", WORKDIR, name,
                "sh", "-c", command,


                timeout=limit + 5,
            )
            out, cut_out = _cut(done.stdout)
            err, cut_err = _cut(done.stderr, MAX_OUTPUT // 2)
            result = RunResult(
                exit_code=done.returncode,
                stdout=out,
                stderr=err,
                seconds=time.monotonic() - started,
                truncated=cut_out or cut_err,
            )
        except subprocess.TimeoutExpired:

            self._kill_processes()
            result = RunResult(
                exit_code=124,
                stdout="",
                stderr="",
                seconds=time.monotonic() - started,
                timed_out=True,
            )
        finally:
            stop.set()
            if waechter is not None:
                waechter.join(timeout=5)
        self.touch()
        self._check_quota(result)
        self._emit("vm_done", exit_code=result.exit_code, seconds=round(result.seconds, 2))
        return result

    def _refuse_if_full(self) -> None:
        """Ueber der Grenze wird nichts mehr hineingeschrieben (9.5.15)."""
        if self._over_quota:
            raise ValueError(f"Die virtual machine ist voll (mehr als {self.disk_gb} GB) -- "
                             "erst aufräumen.")


    WATCH_SECONDS = 3.0

    def _watch_disk(self, stop: threading.Event) -> None:
        """Misst waehrend eines Befehls -- ueber der Grenze wird abgebrochen."""
        while not stop.wait(self.WATCH_SECONDS):
            if self.usage_gb() > self.disk_gb:
                self._over_quota = True
                self._kill_processes()
                return

    def _check_quota(self, result: RunResult) -> None:
        """Misst den Platz nach jedem Befehl, wo die Laufzeit keine Quote kann.

        Ueber der Grenze ist die virtual machine gesperrt -- bis aufgeraeumt ist,
        laufen nur noch Aufraeumbefehle (``cleanup_command``). Bis 9.5.14 gab
        es hier nur eine Warnung.
        """
        if self._quota_ok:
            return
        self._last_quota_check = time.monotonic()
        voll = self.usage_gb()
        if voll <= self.disk_gb:
            self._over_quota = False
            self._quota_warned = False
            return
        self._over_quota = True
        self._quota_warned = True
        result.stderr = (
            f"[virtual machine] {voll} GB belegt, erlaubt sind {self.disk_gb} GB. Der Befehl wurde "
            "abgebrochen bzw. ist gesperrt, bis aufgeräumt ist (rm, einzeln).\n" + result.stderr
        )

    def _kill_processes(self) -> None:
        """Beendet, was nach einer Zeitueberschreitung noch laeuft.

        Im User mode baut ein Neustart das Netz des Behaelters neu auf -- ohne
        die Sperre von vorher. Die wird deshalb sofort neu gesetzt und
        nachgelesen, bevor irgendetwas anderes darin laeuft, und der Desktop
        kommt wieder hoch. Klappt eins davon nicht, wird die virtual machine
        abgebaut: eine offene virtual machine ist schlimmer als keine.
        """
        runtime = self.runtime
        if runtime is None or not self._name:
            return
        with self._lock:
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                _runs(runtime.binary, "restart", "--time", "1", self._name, timeout=60)
            if not self.netz_offen or not self._name:
                return
            try:
                if not self.lan:
                    self._lock_network()
                if self.user_mode and not self.headless:
                    self._start_desktop()
            except Exception:
                self._destroy_locked("Netzsperre nach dem Neustart nicht wiederhergestellt")

    def write(self, path: str, text: str) -> dict[str, Any]:
        """Legt eine Datei in der virtual machine an."""
        full = safe_path(path)
        name = self.ensure()
        runtime = self.runtime
        assert runtime is not None
        self._refuse_if_full()
        data = (text or "").encode("utf-8")
        if len(data) > 4 * 1024 * 1024:
            raise ValueError("Die Datei ist zu gross fuer den Weg durch das Werkzeug (4 MB).")
        parent = full.rsplit("/", 1)[0] or WORKDIR
        done = subprocess.run(
            [
                runtime.binary, "exec", "--interactive",
                "--user", RUN_AS, "--workdir", WORKDIR, name,
                "sh", "-c", f'mkdir -p "{parent}" && cat > "{full}"',
            ],
            input=data,
            capture_output=True,
            timeout=60,
            check=False,
        )
        self.touch()
        if done.returncode != 0:
            grund = done.stderr.decode("utf-8", "replace")[:300]
            return {"error": grund or "Schreiben ging nicht."}
        self._emit("vm_write", path=full, bytes=len(data))
        return {"written": full, "bytes": len(data)}

    def read(self, path: str, max_bytes: int = MAX_READ_BYTES) -> dict[str, Any]:
        """Liest eine Datei aus der virtual machine."""
        full = safe_path(path)
        name = self.ensure()
        runtime = self.runtime
        assert runtime is not None
        limit = max(1, min(int(max_bytes or MAX_READ_BYTES), MAX_READ_BYTES))
        done = _runs(
            runtime.binary,
            "exec", "--user", RUN_AS, "--workdir", WORKDIR, name,
            "sh", "-c", f'head -c {limit + 1} "{full}"',
            timeout=60,
        )
        self.touch()
        if done.returncode != 0:
            return {"error": done.stderr.strip()[:300] or "Datei nicht lesbar."}
        text = done.stdout
        cut = len(text.encode("utf-8", "ignore")) > limit
        if cut:
            text = text[:limit]
        return {"path": full, "text": text, "truncated": cut}

    def put_bytes(self, path: str, data: bytes) -> dict[str, Any]:
        """Legt eine Datei unveraendert in die virtual machine -- auch ein Bild.

        `write` nimmt Text und wuerde an einem PNG scheitern. Hierueber geht
        alles, was der Nutzer anhaengt, unangetastet hinein.
        """
        full = safe_path(path)
        if len(data) > MAX_FILE_BYTES:
            raise ValueError(
                f"Die Datei ist zu gross fuer die virtual machine "
                f"({MAX_FILE_BYTES // (1024 * 1024)} MB sind das Hoechste)."
            )
        name = self.ensure()
        self._refuse_if_full()
        runtime = self.runtime
        assert runtime is not None
        parent = full.rsplit("/", 1)[0] or WORKDIR
        done = subprocess.run(
            [
                runtime.binary, "exec", "--interactive",
                "--user", RUN_AS, "--workdir", WORKDIR, name,
                "sh", "-c", f'mkdir -p "{parent}" && cat > "{full}"',
            ],
            input=data,
            capture_output=True,
            timeout=120,
            check=False,
        )
        self.touch()
        if done.returncode != 0:
            grund = done.stderr.decode("utf-8", "replace")[:300]
            return {"error": grund or "Hineinlegen ging nicht."}
        self._emit("vm_write", path=full, bytes=len(data))
        return {"written": full, "bytes": len(data)}

    def get_bytes(self, path: str, max_bytes: int = MAX_FILE_BYTES) -> bytes:
        """Holt eine Datei unveraendert heraus.

        Raises:
            ValueError: Wenn der Pfad hinausfuehrt oder die Datei zu gross ist.
            FileNotFoundError: Wenn es sie nicht gibt.
        """
        full = safe_path(path)
        limit = max(1, min(int(max_bytes or MAX_FILE_BYTES), MAX_FILE_BYTES))
        name = self.ensure()
        runtime = self.runtime
        assert runtime is not None
        done = subprocess.run(
            [
                runtime.binary, "exec", "--user", RUN_AS, "--workdir", WORKDIR, name,
                "sh", "-c", f'test -f "{full}" && head -c {limit + 1} "{full}"',
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
        self.touch()
        if done.returncode != 0:
            raise FileNotFoundError(f"In der virtual machine liegt keine Datei '{full}'.")
        if len(done.stdout) > limit:
            raise ValueError(
                f"Die Datei ist groesser als {limit // (1024 * 1024)} MB -- "
                "so viel geht nicht durch."
            )
        return done.stdout

    def list_files(self, path: str = WORKDIR) -> list[dict[str, Any]]:
        """Was in der virtual machine liegt -- Pfad und Groesse, flach aufgelistet.

        Ohne diese Liste muesste man raten, wie eine erzeugte Datei heisst,
        um sie herauszuholen.
        """
        full = safe_path(path)
        if not self.alive or self.runtime is None:
            return []

        done = _runs(
            self.runtime.binary,
            "exec", "--user", RUN_AS, "--workdir", WORKDIR, self._name,
            "sh", "-c",
            f'find "{full}" -type f -not -path "*/.git/*" 2>/dev/null '


            f"| head -n {MAX_LIST} | tr '\\n' '\\000' | xargs -0 -r stat -c '%s %n' 2>/dev/null",
            timeout=30,
        )
        self.touch()
        dateien: list[dict[str, Any]] = []
        for zeile in done.stdout.splitlines():
            groesse, _, pfad = zeile.strip().partition(" ")
            if not pfad:
                continue
            try:
                dateien.append({"path": pfad, "bytes": int(groesse)})
            except ValueError:
                continue
        dateien.sort(key=lambda eintrag: eintrag["path"])
        return dateien

    def usage_gb(self) -> float:
        """Wie voll die virtual machine ist -- in Gigabyte."""
        if not self.alive or self.runtime is None:
            return 0.0
        done = _runs(
            self.runtime.binary,
            "exec", "--user", RUN_AS, self._name,
            "sh", "-c", f"du -sk {WORKDIR} 2>/dev/null | cut -f1",
            timeout=30,
        )
        try:
            return round(int(done.stdout.strip() or 0) / (1024 * 1024), 2)
        except ValueError:
            return 0.0


    def touch(self) -> None:
        """Setzt die Uhr zurueck: erst zwanzig Minuten Ruhe raeumen auf."""
        with self._lock:
            self._touch_locked()

    def _touch_locked(self) -> None:
        self.last_used = time.time()
        if self._timer is not None:
            self._timer.cancel()
        if not self._name:
            self._timer = None
            return
        self._timer = threading.Timer(self.idle_seconds, self._idle_out)
        self._timer.daemon = True
        self._timer.start()

    def _idle_out(self) -> None:
        self.stop("seit 20 Minuten unbenutzt")

    def stop(self, reason: str = "aufgeräumt") -> None:
        """Loescht Behaelter und Datentraeger -- ohne Rueckstand."""
        with self._lock:
            if not self._name and not self._volume:
                return
            self._destroy_locked(reason)

    def _destroy_locked(self, reason: str) -> None:
        runtime = self.runtime
        name, volume = self._name, self._volume
        self._name, self._volume = "", ""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if runtime is None:
            return
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            if name:
                _runs(runtime.binary, "rm", "--force", "--volumes", name, timeout=60)
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            if volume:
                _runs(runtime.binary, "volume", "rm", "--force", volume, timeout=60)
        if name:
            self._emit("vm_stop", reason=reason)

    def status(self) -> dict[str, Any]:
        """Kurzer Zustandsbericht fuer Anzeige und Werkzeug."""
        if not self.alive:
            return {"running": False}
        ruhe = max(0, int(self.idle_seconds - (time.time() - self.last_used)))
        return {
            "running": True,
            "user_mode": self.user_mode,
            "internet": self.internet or self.user_mode,
            "lan": self.lan,
            "addons": sorted(ziel.rsplit("/", 1)[-1] for ziel in self.addon_mounts.values()),
            "runtime": self.runtime.label if self.runtime else "",
            "image": self.image,
            "cpus": self.cpus,
            "memory_mb": self.memory_mb,
            "disk_gb": self.disk_gb,
            "idle_left_seconds": ruhe,
        }


def instance_label() -> str:
    """Die Beschriftung dieser Aquaticy-Installation -- aus ihrem Datenordner.

    Zwei Installationen auf demselben Docker-Host (zwei Nutzer, Test und
    Betrieb) erkennen so ihre eigenen Werkstaetten.
    """
    import hashlib

    ordner = os.environ.get("AQUATICY_DATA_DIR", "").strip() or str(Path.home() / ".aquaticy")
    with contextlib.suppress(OSError):
        ordner = str(Path(ordner).expanduser().resolve())
    return "aquaticy-instanz=" + hashlib.sha256(ordner.encode("utf-8")).hexdigest()[:16]


def sweep(runtime: Runtime | None = None) -> int:
    """Raeumt vergessene Werkstaetten weg -- etwa nach einem Absturz.

    Erkannt werden sie an ihrer Beschriftung. Beim Start des Servers einmal
    aufgerufen, bleibt von einem harten Abbruch nichts liegen.

    Returns:
        Wie viele Behaelter entfernt wurden.
    """
    runtime = runtime or find_runtime()
    if runtime is None:
        return 0



    found = _runs(
        runtime.binary, "ps", "--all", "--quiet", "--filter", "label=aquaticy-werkstatt=1",
        "--filter", f"label={instance_label()}", timeout=30,
    )
    ids = [line.strip() for line in found.stdout.splitlines() if line.strip()]
    for container in ids:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            _runs(runtime.binary, "rm", "--force", "--volumes", container, timeout=60)
    volumes = _runs(
        runtime.binary, "volume", "ls", "--quiet", "--filter", f"label={instance_label()}",
        timeout=30,
    )
    for volume in volumes.stdout.splitlines():
        volume = volume.strip()
        if volume.startswith("aquaticy-werkstatt-"):
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                _runs(runtime.binary, "volume", "rm", "--force", volume, timeout=60)
    return len(ids)




_shared: dict[str, Sandbox] = {}
_shared_lock = threading.Lock()
_shared_registered = False



_KEEP = object()


def shared(settings: Any = None, on_event: Any = _KEEP) -> Sandbox:
    """Die virtual machine des aktuellen Kontoprofils.

    Wer keinen Empfaenger uebergibt, laesst den bestehenden stehen: sonst
    haette ein Blick auf die Dateiliste mitten in einer Anfrage die
    Live-Anzeige stumm geschaltet.
    """
    global _shared_registered
    data_dir = getattr(settings, "data_dir", None)
    key = str(Path(data_dir).resolve()) if data_dir else "__default__"
    with _shared_lock:
        if not _shared_registered:
            atexit.register(_stop_shared)
            _shared_registered = True
        box = _shared.get(key)
        if box is None:
            user_mode = bool(getattr(settings, "vm_user_mode", False))



            lan = bool(getattr(settings, "vm_lan", False))
            internet = (bool(getattr(settings, "vm_internet", False)) or lan) and not user_mode
            box = Sandbox(
                image=(
                    getattr(settings, "vm_desktop_image", "") or DESKTOP_IMAGE
                    if user_mode or internet
                    else getattr(settings, "vm_image", "") or DEFAULT_IMAGE
                ),
                user_mode=user_mode,
                internet=internet,
                lan=lan,
                headless=internet,
                browser_agent=browser_agent(settings) if user_mode else "",
                addon_mounts=_addon_mounts(settings) if user_mode else None,
                idle_minutes=int(
                    getattr(settings, "vm_idle_minutes", IDLE_MINUTES) or IDLE_MINUTES
                ),
                memory_mb=int(getattr(settings, "vm_memory_mb", MEMORY_MB) or MEMORY_MB),
                disk_gb=int(getattr(settings, "vm_disk_gb", DISK_GB) or DISK_GB),
                cpus=int(getattr(settings, "vm_cpus", CPUS) or CPUS),
            )
            _shared[key] = box
        if on_event is not _KEEP:
            box.on_event = on_event
        return box


def _addon_mounts(settings: Any) -> dict[str, str]:
    """Die Datentraeger der eingeschalteten Add-ons dieses Kontos."""
    if settings is None:
        return {}
    try:
        from aquaticy import addons

        return addons.mounts(settings)
    except Exception:
        return {}


def browser_agent(settings: Any = None) -> str:
    """Die Kennung des Browsers im User mode -- ehrlich, mit Kontaktweg.

    Der Anfang ist der uebliche Browser-Teil, damit Seiten nicht nur eine
    Fehlerseite ausliefern. Der Schluss sagt, wer hier wirklich bedient: eine
    KI, und wo man sich beschweren kann.
    """
    from aquaticy import __version__

    return (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/87.0 Safari/537.36 Falkon/3.2 "
        f"aquaticy-usermode/{__version__} (KI-gesteuert; "
        "+https://github.com/jonasenriklaumen-a11y/Aquaticy-Ai)"
    )


def _stop_shared() -> None:
    """Beim Beenden des Programms: alle Werkstaetten gehen mit."""
    for box in list(_shared.values()):
        box.stop("Programm beendet")


def forget_shared(settings: Any = None) -> None:
    """Vergisst eine Kontowerkstatt oder, ohne Konto, alle Werkstaetten."""
    data_dir = getattr(settings, "data_dir", None)
    key = str(Path(data_dir).resolve()) if data_dir else ""
    with _shared_lock:
        boxes = [_shared.pop(key)] if key and key in _shared else []
        if not key:
            boxes = list(_shared.values())
            _shared.clear()
        for box in boxes:
            box.stop("neu aufgebaut")
