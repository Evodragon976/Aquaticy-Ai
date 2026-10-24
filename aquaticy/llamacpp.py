"""llama.cpp fuer "Serverlast aufteilen" -- installiert sich selbst (11.0.0 Luna).

Bis 10.2 musste llama.cpp auf jedem Server von Hand gebaut werden, bevor sich ein
Modell im Verbund aufteilen liess. Seit 11.0.0 holt Aquaticy die offiziellen,
fertig gebauten Programme selbst, sobald der Schalter an ist:

* **Eine Fassung fuer den ganzen Verbund.** llama.cpp verlangt auf allen Servern
  dieselbe Fassung -- sonst passt das RPC-Protokoll nicht zusammen. Der Master
  waehlt sie einmal (die, die er schon hat, sonst die neueste Veroeffentlichung)
  und schickt sie mit der Einstellung an alle Mitglieder.
* **Die passende Ausgabe je Server.** Apple Silicon rechnet mit Metal; Linux und
  Windows mit NVIDIA-Karte bekommen die Vulkan-Ausgabe, alle anderen die fuer den
  Prozessor. Startet die Grafik-Ausgabe nicht (etwa ohne passenden Treiber),
  nimmt Aquaticy die fuer den Prozessor.
* **Nur von GitHub, nur geprueft.** Die Liste kommt von api.github.com, die Datei
  nur von den Download-Servern von GitHub. Die Pruefsumme (SHA-256) aus der
  Veroeffentlichung muss stimmen, sonst wird nichts entpackt -- und ohne
  Pruefsumme wird gar nichts installiert. Entpackt wird nur in den eigenen
  Ordner: keine Pfade nach draussen, keine Verknuepfungen nach draussen, feste
  Grenzen fuer Groesse und Anzahl der Dateien.
* **Im Container schon dabei.** Das Abbild bringt eine Fassung mit
  (``/opt/aquaticy/llama.cpp``); dann muss nichts geladen werden.

Wer llama.cpp lieber selbst baut, gibt die Programme wie bisher mit
AQUATICY_RPC_SERVER und AQUATICY_LLAMA_SERVER vor -- das hat Vorrang.
"""

from __future__ import annotations

import contextlib
import ctypes.util
import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess
import tarfile
import threading
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

REPO_API = "https://api.github.com/repos/ggml-org/llama.cpp"
#: Wohin GitHub einen Download umleiten darf -- sonst nirgendwohin.
DOWNLOAD_HOSTS = frozenset({
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "github-releases.githubusercontent.com",
})
#: So heissen die Fassungen von llama.cpp: "b" und die Nummer des Builds.
TAG_RE = re.compile(r"^b\d{1,7}$")
#: So heissen die fertigen Ausgaben einer Veroeffentlichung.
ASSET_RE = re.compile(
    r"^llama-(?P<tag>b\d{1,7})-bin-(?P<plattform>[a-z0-9][a-z0-9.\-]{1,60}?)"
    r"\.(?P<art>zip|tar\.gz)$")
#: Ordnernamen einer Installation: <Fassung>-<Ausgabe>.
FOLDER_RE = re.compile(r"^(?P<tag>b\d{1,7})-(?P<plattform>[a-z0-9][a-z0-9.\-]{1,60})$")

MAX_API_BYTES = 8 * 1024 * 1024
#: Die Ausgaben fuer Prozessor und Vulkan sind 20 bis 100 MB gross.
MAX_ARCHIVE_BYTES = 600 * 1024 * 1024
MAX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024
MAX_FILES = 4000
#: Eine Fassung fest vorgeben (sonst waehlt der Master).
TAG_ENV = "AQUATICY_LLAMA_TAG"
#: Ein Ordner mit einer mitgelieferten Fassung (Container-Abbild).
DIR_ENV = "AQUATICY_LLAMA_DIR"
SYSTEM_DIR = Path("/opt/aquaticy/llama.cpp")
MARKER = "aquaticy-llama.json"
#: Nach einem Fehler so lange warten -- erst eine Minute, dann laenger.
RETRY_SECONDS = (60.0, 300.0, 900.0)
#: Ausgaben, die eine Grafikkarte nutzen (Metal oder Vulkan).
ACCELERATED = frozenset({
    "macos-arm64", "ubuntu-vulkan-x64", "ubuntu-vulkan-arm64", "win-vulkan-x64",
})


class LlamaError(RuntimeError):
    """Ein Satz fuer Menschen: warum llama.cpp nicht installiert werden konnte."""


@dataclass(frozen=True)
class Install:
    """Eine fertige Installation einer Fassung fuer diesen Server."""

    tag: str
    plattform: str
    folder: Path
    rpc_server: Path
    llama_server: Path

    @property
    def accelerated(self) -> bool:
        return self.plattform in ACCELERATED

    def label(self) -> str:
        art = {"macos-arm64": "Metal"}.get(self.plattform, "")
        if not art:
            art = "Vulkan" if "vulkan" in self.plattform else "Prozessor"
        return f"llama.cpp {self.tag} ({art})"


# ---------------------------------------------------------------------------
# Welche Ausgabe passt zu diesem Server?
# ---------------------------------------------------------------------------
def vulkan_loader() -> bool:
    """Ist der Vulkan-Lader da? Ohne ihn startet die Vulkan-Ausgabe nicht.

    Unter Windows bringt ihn jeder Grafiktreiber mit.
    """
    if platform.system() == "Windows":
        return True
    try:
        return bool(ctypes.util.find_library("vulkan"))
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def platform_names(system: str = "", machine: str = "", *, gpu: bool = False,
                   vulkan: bool = False) -> list[str]:
    """Die passenden Ausgaben, die beste zuerst. Leer: es gibt keine fertige."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    arm = machine in ("arm64", "aarch64")
    x64 = machine in ("x86_64", "amd64", "x64")
    if system == "darwin":
        return ["macos-arm64"] if arm else (["macos-x64"] if x64 else [])
    if system == "linux":
        if x64:
            return ["ubuntu-vulkan-x64", "ubuntu-x64"] if gpu and vulkan else ["ubuntu-x64"]
        if arm:
            return (["ubuntu-vulkan-arm64", "ubuntu-arm64"] if gpu and vulkan
                    else ["ubuntu-arm64"])
        return ["ubuntu-s390x"] if machine == "s390x" else []
    if system == "windows":
        if arm:
            return ["win-cpu-arm64"]
        if x64:
            return ["win-vulkan-x64", "win-cpu-x64"] if gpu else ["win-cpu-x64"]
    return []


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------
def _headers() -> dict[str, str]:
    from aquaticy import __version__

    return {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"aquaticy/{__version__} "
                      "(+https://github.com/jonasenriklaumen-a11y/Aquaticy-Ai)",
    }


def client() -> httpx.Client:
    """Der Abruf zu GitHub. Umleitungen prueft Aquaticy selbst (siehe download)."""
    return httpx.Client(timeout=httpx.Timeout(30.0, read=120.0), follow_redirects=False,
                        headers=_headers())


def release(tag: str = "", *, http: httpx.Client | None = None) -> dict[str, Any]:
    """Eine Veroeffentlichung von llama.cpp -- ohne *tag* die neueste."""
    from aquaticy.jsonutil import loads
    from aquaticy.netguard import read_response

    if tag and not TAG_RE.fullmatch(tag):
        raise LlamaError("Diese llama.cpp-Fassung gibt es nicht.")
    pfad = f"/releases/tags/{tag}" if tag else "/releases/latest"
    eigener = http is None
    http = http or client()
    try:
        frist = time.monotonic() + 60.0
        with http.stream("GET", REPO_API + pfad) as antwort:
            if antwort.status_code == 404:
                raise LlamaError(f"Die llama.cpp-Fassung {tag or '(neueste)'} gibt es bei "
                                 "GitHub nicht.")
            if antwort.status_code == 429 or (antwort.status_code == 403 and antwort.headers.get(
                    "x-ratelimit-remaining") == "0"):
                raise LlamaError("GitHub bremst gerade (zu viele Anfragen) — Aquaticy "
                                 "versucht es gleich noch einmal.")
            if antwort.status_code == 403:
                raise LlamaError("GitHub verweigert den Zugriff (403) — ist github.com von "
                                 "diesem Server aus erreichbar?")
            if antwort.status_code != 200:
                raise LlamaError(f"GitHub antwortet mit {antwort.status_code}.")
            daten = loads(read_response(antwort, MAX_API_BYTES, frist))
    except httpx.HTTPError as exc:
        raise LlamaError(f"GitHub ist nicht erreichbar ({type(exc).__name__}).") from exc
    except ValueError as exc:
        raise LlamaError("GitHub hat unerwartet geantwortet.") from exc
    finally:
        if eigener:
            http.close()
    if not isinstance(daten, dict) or not TAG_RE.fullmatch(str(daten.get("tag_name") or "")):
        raise LlamaError("GitHub hat unerwartet geantwortet.")
    if tag and daten.get("tag_name") != tag:
        raise LlamaError("GitHub hat eine andere Fassung geliefert als verlangt.")
    return daten


def pick_asset(daten: dict[str, Any], namen: list[str]) -> dict[str, Any] | None:
    """Die erste Ausgabe aus *namen*, die es in dieser Veroeffentlichung gibt."""
    tag = str(daten.get("tag_name") or "")
    gefunden: dict[str, dict[str, Any]] = {}
    for asset in daten.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        treffer = ASSET_RE.match(str(asset.get("name") or ""))
        if treffer and treffer.group("tag") == tag:
            gefunden.setdefault(treffer.group("plattform"), asset)
    for name in namen:
        if name in gefunden:
            return {**gefunden[name], "plattform": name}
    return None


def _digest(asset: dict[str, Any]) -> str:
    wert = str(asset.get("digest") or "").strip().lower()
    if not wert.startswith("sha256:") or not re.fullmatch(r"[0-9a-f]{64}", wert[7:]):
        raise LlamaError("Die Veröffentlichung nennt keine Prüfsumme — ungeprüft installiert "
                         "Aquaticy nichts.")
    return wert[7:]


def download(asset: dict[str, Any], ziel: Path, *, http: httpx.Client,
             on_progress: Callable[[int, int], None] | None = None) -> str:
    """Laedt eine Ausgabe und prueft sie. Returns: die Pruefsumme (SHA-256).

    Umleitungen gehen nur zu den Download-Servern von GitHub, und nur ueber HTTPS.
    """
    soll = _digest(asset)
    try:
        groesse = int(asset.get("size") or 0)
    except (TypeError, ValueError):
        groesse = 0
    if not 0 < groesse <= MAX_ARCHIVE_BYTES:
        raise LlamaError("Die Datei ist größer, als Aquaticy lädt.")
    adresse = str(asset.get("browser_download_url") or "")
    for _ in range(6):
        teile = urlsplit(adresse)
        if (teile.scheme != "https" or (teile.hostname or "").lower() not in DOWNLOAD_HOSTS
                or teile.port not in (None, 443) or teile.username or teile.password):
            raise LlamaError("Aquaticy lädt nur von den Download-Servern von GitHub.")
        with http.stream("GET", adresse, headers={"Accept": "application/octet-stream",
                                                   "Accept-Encoding": "identity"}) as antwort:
            if antwort.status_code in (301, 302, 303, 307, 308):
                adresse = urljoin(adresse, antwort.headers.get("location", ""))
                continue
            if antwort.status_code != 200:
                raise LlamaError(f"Der Download antwortet mit {antwort.status_code}.")
            if antwort.headers.get("content-encoding", "identity").strip().lower() not in (
                    "", "identity"):
                # iter_bytes wuerde vor unserer Groessenpruefung unbegrenzt entpacken.
                raise LlamaError("Die Datei kam in einem unerwarteten Format an.")
            pruefer = hashlib.sha256()
            geladen = 0
            with ziel.open("wb") as datei:
                for stueck in antwort.iter_bytes(1024 * 1024):
                    geladen += len(stueck)
                    if geladen > groesse:
                        raise LlamaError("Die Datei ist größer als angekündigt.")
                    pruefer.update(stueck)
                    datei.write(stueck)
                    if on_progress is not None:
                        on_progress(geladen, groesse)
            break
    else:
        raise LlamaError("Zu viele Umleitungen beim Download.")
    if geladen != groesse:
        raise LlamaError("Der Download ist unvollständig.")
    ist = pruefer.hexdigest()
    if not hmac.compare_digest(ist, soll):
        raise LlamaError("Die Prüfsumme stimmt nicht — die Datei wird verworfen.")
    return ist


# ---------------------------------------------------------------------------
# Entpacken -- nur in den eigenen Ordner
# ---------------------------------------------------------------------------
def _safe_name(name: str) -> PurePosixPath | None:
    name = str(name or "").replace("\\", "/")
    if not name or "\x00" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        return None
    teile = [teil for teil in PurePosixPath(name).parts if teil not in ("", ".")]
    if not teile or any(teil == ".." for teil in teile):
        return None
    return PurePosixPath(*teile)


def _inside(pfad: str, wurzel: Path) -> bool:
    basis = str(wurzel)
    return pfad == basis or pfad.startswith(basis.rstrip(os.sep) + os.sep)


def _check_path(pfad: Path, wurzel: Path) -> None:
    """Auch vorhandene und verkettete Verknuepfungen muessen im Ziel bleiben."""
    try:
        sicher = _inside(str(pfad.resolve()), wurzel)
    except (OSError, RuntimeError) as exc:
        raise LlamaError("Das Archiv enthält eine unsichere Verknüpfung.") from exc
    if not sicher:
        raise LlamaError("Eine Verknüpfung im Archiv zeigt aus dem Ordner heraus.")


def _link(pfad: Path, ziel_text: str, wurzel: Path) -> None:
    """Eine Verknuepfung aus dem Archiv -- nur, wenn sie im Ordner bleibt."""
    if os.name == "nt":
        return  # die Windows-Ausgaben haben keine
    if (not ziel_text or ziel_text.startswith("/") or "\x00" in ziel_text
            or "\\" in ziel_text):
        raise LlamaError("Das Archiv enthält eine unsichere Verknüpfung.")
    aufgeloest = os.path.normpath(os.path.join(os.path.dirname(pfad), ziel_text))
    if not _inside(aufgeloest, wurzel):
        raise LlamaError("Eine Verknüpfung im Archiv zeigt aus dem Ordner heraus.")
    _check_path(pfad.parent, wurzel)
    _check_path(pfad.parent / ziel_text, wurzel)
    if pfad.exists() or pfad.is_symlink():
        raise LlamaError("Das Archiv enthält einen Eintrag doppelt.")
    pfad.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(ziel_text, pfad)


def unpack_zip(archiv: Path, ziel: Path) -> None:
    wurzel = ziel.resolve()
    with zipfile.ZipFile(archiv) as zf:
        eintraege = zf.infolist()
        if len(eintraege) > MAX_FILES:
            raise LlamaError("Das Archiv enthält zu viele Dateien.")
        if sum(max(0, e.file_size) for e in eintraege) > MAX_UNPACKED_BYTES:
            raise LlamaError("Ausgepackt wäre das Archiv zu groß.")
        links: list[tuple[Path, str]] = []
        for eintrag in eintraege:
            if eintrag.is_dir() and not eintrag.filename.replace("\\", "/").strip("./"):
                continue  # der Ordner selbst ("./")
            name = _safe_name(eintrag.filename)
            if name is None:
                raise LlamaError("Das Archiv enthält einen unsicheren Pfad.")
            pfad = wurzel.joinpath(*name.parts)
            _check_path(pfad, wurzel)
            modus = (eintrag.external_attr >> 16) & 0xFFFF
            if eintrag.is_dir():
                pfad.mkdir(parents=True, exist_ok=True)
                continue
            if stat.S_ISLNK(modus):
                if eintrag.file_size > 4096:
                    raise LlamaError("Das Archiv enthält eine unsichere Verknüpfung.")
                links.append((pfad, zf.read(eintrag).decode("utf-8", "strict")))
                continue
            if stat.S_IFMT(modus) not in (0, stat.S_IFREG):
                raise LlamaError("Das Archiv enthält eine unbekannte Dateiart.")
            pfad.parent.mkdir(parents=True, exist_ok=True)
            geschrieben = 0
            try:
                with zf.open(eintrag) as quelle, pfad.open("xb") as datei:
                    while stueck := quelle.read(1024 * 1024):
                        geschrieben += len(stueck)
                        if geschrieben > eintrag.file_size:
                            raise LlamaError("Ein Eintrag im Archiv ist größer als angegeben.")
                        datei.write(stueck)
            except FileExistsError as exc:
                raise LlamaError("Das Archiv enthält einen Eintrag doppelt.") from exc
            pfad.chmod(0o755 if modus & 0o111 else 0o644)
        for pfad, ziel_text in links:
            _link(pfad, ziel_text, wurzel)
        # Spaeter angelegte Links koennen fruehere Ziele veraendern.
        for pfad, _ in links:
            _check_path(pfad, wurzel)


def unpack_tar(archiv: Path, ziel: Path) -> None:
    if not hasattr(tarfile, "data_filter"):  # Python vor 3.11.4
        raise LlamaError("Zum sicheren Entpacken braucht es Python 3.11.4 oder neuer.")
    with tarfile.open(archiv, "r:gz") as tf:
        mitglieder: list[tarfile.TarInfo] = []
        summe = 0
        for mitglied in tf:
            if mitglied.isdir() and not mitglied.name.strip("./"):
                continue  # der Ordner selbst ("./")
            mitglieder.append(mitglied)
            summe += max(0, mitglied.size)
            if len(mitglieder) > MAX_FILES:
                raise LlamaError("Das Archiv enthält zu viele Dateien.")
            if summe > MAX_UNPACKED_BYTES:
                raise LlamaError("Ausgepackt wäre das Archiv zu groß.")
            if _safe_name(mitglied.name) is None:
                raise LlamaError("Das Archiv enthält einen unsicheren Pfad.")
        try:
            # "data": keine Pfade und Verknuepfungen nach draussen, keine
            # Geraetedateien, keine Sonderrechte (setuid).
            tf.extractall(ziel, members=mitglieder, filter="data")
        except tarfile.FilterError as exc:
            raise LlamaError("Das Archiv enthält einen unsicheren Eintrag.") from exc


def _exe(name: str) -> str:
    return name + (".exe" if os.name == "nt" else "")


def _find(ordner: Path, name: str) -> Path | None:
    """Das Programm im entpackten Ordner -- das am wenigsten tief liegende."""
    wurzel = ordner.resolve()
    treffer = []
    for pfad in ordner.rglob(_exe(name)):
        with contextlib.suppress(OSError):
            if pfad.is_file() and _inside(str(pfad.resolve()), wurzel):
                treffer.append(pfad)
    treffer.sort(key=lambda p: (len(p.parts), str(p)))
    return treffer[0] if treffer else None


def _starts(programm: Path, plattform: str = "") -> tuple[bool, str]:
    """Laeuft das Programm auf diesem Server? (fehlende Bibliotheken, zu altes System)

    Eine Vulkan-Ausgabe muss ausserdem eine Karte sehen -- sonst rechnete sie
    still auf dem Prozessor, und Aquaticy zaehlte trotzdem den Grafikspeicher.
    """
    vulkan = "vulkan" in plattform
    try:
        fertig = subprocess.run([str(programm), "--list-devices" if vulkan else "--version"],
                                capture_output=True, timeout=60, check=False,
                                stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, type(exc).__name__
    text = (fertig.stdout + b"\n" + fertig.stderr).decode("utf-8", "replace")
    zeilen = [z.strip() for z in text.splitlines() if z.strip()]
    grund = (zeilen[-1] if zeilen else "")[:200]
    if fertig.returncode != 0:
        return False, grund
    if vulkan and "vulkan" not in text.lower():
        return False, "keine Grafikkarte für Vulkan gefunden"
    return True, ""


# ---------------------------------------------------------------------------
# Was schon da ist
# ---------------------------------------------------------------------------
def _trusted(ordner: Path) -> bool:
    """Ein mitgelieferter Ordner zaehlt nur, wenn ihn kein Fremder veraendern kann."""
    if os.name == "nt":
        return True
    try:
        info = ordner.stat()
    except OSError:
        return False
    return info.st_uid in (0, os.getuid()) and not info.st_mode & 0o022


def read_install(folder: Path) -> Install | None:
    """Liest eine Installation -- nur, wenn Ordner, Merkzettel und Programme passen."""
    treffer = FOLDER_RE.match(folder.name)
    if not treffer:
        return None
    try:
        daten = json.loads((folder / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (not isinstance(daten, dict) or daten.get("tag") != treffer.group("tag")
            or daten.get("plattform") != treffer.group("plattform")):
        return None
    wurzel = folder.resolve()
    pfade: dict[str, Path] = {}
    for schluessel, name in (("rpc_server", "rpc-server"), ("llama_server", "llama-server")):
        relativ = _safe_name(str(daten.get(schluessel) or ""))
        if relativ is None or relativ.name != _exe(name):
            return None
        pfad = wurzel.joinpath(*relativ.parts)
        try:
            if not pfad.is_file() or not _inside(str(pfad.resolve()), wurzel):
                return None
        except OSError:
            return None
        pfade[schluessel] = pfad
    return Install(tag=treffer.group("tag"), plattform=treffer.group("plattform"),
                   folder=wurzel, rpc_server=pfade["rpc_server"],
                   llama_server=pfade["llama_server"])


def system_dirs() -> list[Path]:
    """Mitgelieferte Fassungen (Container-Abbild) -- nur zum Lesen."""
    ordner = []
    vorgabe = os.environ.get(DIR_ENV, "").strip()
    if vorgabe:
        ordner.append(Path(vorgabe).expanduser())
    ordner.append(SYSTEM_DIR)
    return ordner


# ---------------------------------------------------------------------------
# Installieren -- im Hintergrund, eine Installation zur Zeit
# ---------------------------------------------------------------------------
class Installer:
    """Haelt llama.cpp fuer diesen Server bereit.

    ``ensure(tag)`` blockiert nie: fehlt die Fassung, laedt ein eigener Faden sie
    im Hintergrund, und ``status()`` sagt, wie weit er ist.
    """

    def __init__(self, root: Path, *, gpu: Callable[[], bool] = lambda: False,
                 http: Callable[[], httpx.Client] | None = None) -> None:
        self.root = Path(root)
        self._gpu = gpu
        self._http = http or (lambda: client())
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._namen: list[str] | None = None
        #: Grafik-Ausgaben, die hier nicht starten -- dann die fuer den Prozessor.
        self._schlecht: set[str] = set()
        #: Ausgaben, die es in einer Fassung nicht gibt.
        self._fehlend: dict[str, set[str]] = {}
        self._fehler = 0
        self._naechster = 0.0
        self._gewaehlt = ""
        self.phase = "aus"       # aus, lädt, bereit, fehler
        self.message = ""
        self.progress = 0
        self.tag = ""

    # -- Was passt, was ist da ---------------------------------------------
    def names(self) -> list[str]:
        """Die passenden Ausgaben fuer diesen Server (einmal ermittelt)."""
        with self._lock:
            if self._namen is None:
                try:
                    gpu = bool(self._gpu())
                except Exception:
                    gpu = False
                self._namen = platform_names(gpu=gpu, vulkan=vulkan_loader() if gpu else False)
            return [name for name in self._namen if name not in self._schlecht]

    def _bases(self) -> list[Path]:
        return [self.root, *[o for o in system_dirs() if o.is_dir() and _trusted(o)]]

    def _candidates(self, tag: str) -> list[str]:
        """Die Ausgaben, die fuer *tag* noch in Frage kommen -- die beste zuerst."""
        fehlt = self._fehlend.get(tag, set())
        return [name for name in self.names() if name not in fehlt]

    def installed(self, tag: str) -> Install | None:
        """Die Installation von *tag* in der besten Ausgabe, die hier in Frage kommt.

        Eine schlechtere zaehlt erst, wenn die bessere ausscheidet: weil es sie
        in dieser Fassung nicht gibt oder weil sie hier nicht startet.
        """
        if not TAG_RE.fullmatch(str(tag or "")):
            return None
        for name in self._candidates(tag)[:1]:
            for basis in self._bases():
                eintrag = read_install(basis / f"{tag}-{name}")
                if eintrag is not None:
                    return eintrag
        return None

    def newest_installed_tag(self) -> str:
        """Die neueste vorhandene Fassung (eigene oder mitgelieferte)."""
        namen = set(self.names())
        beste = ""
        for basis in self._bases():
            with contextlib.suppress(OSError):
                for ordner in basis.iterdir():
                    treffer = FOLDER_RE.match(ordner.name)
                    if (treffer and treffer.group("plattform") in namen
                            and read_install(ordner) is not None
                            and int(treffer.group("tag")[1:]) > int(beste[1:] or 0)):
                        beste = treffer.group("tag")
        return beste

    # -- Im Hintergrund ----------------------------------------------------
    def ensure(self, tag: str) -> Install | None:
        """Die Installation von *tag* -- oder None, solange sie noch geladen wird."""
        eintrag = self.installed(tag)
        if eintrag is not None:
            self.tag, self.phase, self.message, self.progress = tag, "bereit", "", 100
            return eintrag
        self._start(lambda: self._install(tag), tag)
        return None

    def chosen(self) -> str:
        """Master: die Fassung fuer den Verbund -- "" solange sie noch gesucht wird."""
        vorgabe = os.environ.get(TAG_ENV, "").strip()
        if TAG_RE.fullmatch(vorgabe):
            return vorgabe
        if self._gewaehlt:
            return self._gewaehlt
        vorhanden = self.newest_installed_tag()
        if vorhanden:
            self._gewaehlt = vorhanden
            return vorhanden
        self._start(self._choose, "")
        return self._gewaehlt

    def _choose(self) -> None:
        self.message = "Sucht die neueste Version von llama.cpp …"
        http = self._http()
        try:
            self._gewaehlt = str(release(http=http)["tag_name"])
        finally:
            http.close()

    def _start(self, aufgabe: Callable[[], None], tag: str) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            if time.monotonic() < self._naechster:
                return
            if tag:
                self.tag = tag
            self.phase, self.progress = "lädt", 0
            self._thread = threading.Thread(target=self._run, args=(aufgabe,),
                                            name="aquaticy-llama-install", daemon=True)
            self._thread.start()

    def _run(self, aufgabe: Callable[[], None]) -> None:
        try:
            aufgabe()
            self._fehler = 0
            if self.phase == "lädt":
                self.phase, self.message = "aus", ""
        except Exception as exc:  # jeder Fehler wird ein Satz, nicht ein toter Faden
            meldung = str(exc) if isinstance(exc, LlamaError) else (
                f"llama.cpp ließ sich nicht installieren ({type(exc).__name__}).")
            pause = RETRY_SECONDS[min(self._fehler, len(RETRY_SECONDS) - 1)]
            self._fehler += 1
            self._naechster = time.monotonic() + pause
            self.phase, self.message = "fehler", meldung[:300]

    def wait(self, timeout: float = 600.0) -> None:
        """Nur fuer Kommandozeile und Tests: auf den Hintergrundfaden warten."""
        faden = self._thread
        if faden is not None:
            faden.join(timeout)

    def _progress(self, geladen: int, gesamt: int) -> None:
        self.progress = max(0, min(99, int(geladen * 100 / max(1, gesamt))))
        self.message = f"Lädt llama.cpp {self.tag} … {self.progress} %"

    def _install(self, tag: str) -> None:
        if not TAG_RE.fullmatch(tag):
            raise LlamaError("Diese llama.cpp-Fassung gibt es nicht.")
        if not self.names():
            raise LlamaError("Für dieses System gibt es llama.cpp nicht fertig gebaut — "
                             "bau es selbst und gib die Programme mit AQUATICY_RPC_SERVER "
                             "und AQUATICY_LLAMA_SERVER an.")
        self.message = f"Lädt llama.cpp {tag} …"
        http = self._http()
        try:
            daten = release(tag, http=http)
            letzter = ""
            while kandidaten := self._candidates(tag):
                name = kandidaten[0]
                if self.installed(tag) is not None:
                    return
                asset = pick_asset(daten, [name])
                if asset is None:
                    self._fehlend.setdefault(tag, set()).add(name)
                    continue
                try:
                    self._install_asset(tag, asset, http)
                    return
                except _StartetNicht as exc:
                    letzter = str(exc)
                    if name not in ACCELERATED:
                        raise LlamaError(letzter) from exc
                    # Die Grafik-Ausgabe startet hier nicht -- dann die fuer den
                    # Prozessor (fehlender Treiber, zu alter Lader).
                    with self._lock:
                        self._schlecht.add(name)
            raise LlamaError(letzter or "Für dieses System gibt es in dieser Fassung keine "
                             "fertige Ausgabe von llama.cpp.")
        finally:
            http.close()

    def _install_asset(self, tag: str, asset: dict[str, Any], http: httpx.Client) -> Install:
        name = str(asset["plattform"])
        self.root.mkdir(parents=True, exist_ok=True)
        arbeit = self.root / f".neu-{secrets.token_hex(6)}"
        arbeit.mkdir(mode=0o700)
        try:
            endung = ".tar.gz" if str(asset.get("name", "")).endswith(".tar.gz") else ".zip"
            archiv = arbeit / f"download{endung}"
            pruefsumme = download(asset, archiv, http=http, on_progress=self._progress)
            self.message = f"Entpackt llama.cpp {tag} …"
            inhalt = arbeit / "inhalt"
            inhalt.mkdir()
            if endung == ".zip":
                unpack_zip(archiv, inhalt)
            else:
                unpack_tar(archiv, inhalt)
            archiv.unlink()
            rpc, server = _find(inhalt, "rpc-server"), _find(inhalt, "llama-server")
            if rpc is None or server is None:
                raise LlamaError("In dieser Ausgabe von llama.cpp fehlt rpc-server oder "
                                 "llama-server.")
            if os.name != "nt":
                for pfad in (rpc, server):
                    pfad.chmod(pfad.stat().st_mode | 0o755)
            laeuft, grund = _starts(server, name)
            if not laeuft:
                raise _StartetNicht(f"llama.cpp startet auf diesem Server nicht"
                                    f"{': ' + grund if grund else ''}")
            wurzel = inhalt.resolve()
            (inhalt / MARKER).write_text(json.dumps({
                "tag": tag, "plattform": name, "sha256": pruefsumme, "at": int(time.time()),
                "rpc_server": rpc.resolve().relative_to(wurzel).as_posix(),
                "llama_server": server.resolve().relative_to(wurzel).as_posix(),
            }), encoding="utf-8")
            ziel = self.root / f"{tag}-{name}"
            if ziel.exists():
                shutil.rmtree(ziel, ignore_errors=True)
            os.replace(inhalt, ziel)
        finally:
            shutil.rmtree(arbeit, ignore_errors=True)
        eintrag = read_install(ziel)
        if eintrag is None:
            raise LlamaError("Die Installation von llama.cpp ist unvollständig.")
        self._aufraeumen(behalten=ziel.name)
        self.phase, self.message, self.progress = "bereit", "", 100
        return eintrag

    def _aufraeumen(self, behalten: str) -> None:
        """Alte Fassungen weg -- nur eigene Ordner mit Merkzettel."""
        with contextlib.suppress(OSError):
            for ordner in self.root.iterdir():
                if ordner.name == behalten:
                    continue
                if ordner.name.startswith(".neu-") or read_install(ordner) is not None:
                    shutil.rmtree(ordner, ignore_errors=True)

    def status(self) -> dict[str, Any]:
        return {"phase": self.phase, "message": self.message, "progress": self.progress,
                "tag": self.tag}


class _StartetNicht(LlamaError):
    """Die Ausgabe ist geladen und geprueft, laeuft aber auf diesem Server nicht."""


def main(argv: list[str] | None = None) -> int:
    """``python -m aquaticy.llamacpp install`` -- fuer das Container-Abbild."""
    import argparse

    parser = argparse.ArgumentParser(prog="python -m aquaticy.llamacpp")
    unter = parser.add_subparsers(dest="befehl", required=True)
    install = unter.add_parser("install", help="llama.cpp laden und prüfen")
    install.add_argument("--dir", default="", help="Zielordner")
    install.add_argument("--tag", default="", help="Fassung (Standard: die neueste)")
    install.add_argument("--gpu", action="store_true", help="die Grafik-Ausgabe bevorzugen")
    args = parser.parse_args(argv)
    ziel = (Path(args.dir).expanduser() if args.dir else
            Path(os.environ.get("AQUATICY_DATA_DIR") or Path.home() / ".aquaticy").expanduser()
            / "llama.cpp")
    installer = Installer(ziel, gpu=lambda: bool(args.gpu))
    try:
        tag = args.tag or str(release()["tag_name"])
        if installer.ensure(tag) is None:
            installer.wait()
        eintrag = installer.installed(tag)
    except LlamaError as exc:
        print(f"llama.cpp: {exc}")
        return 1
    if eintrag is None:
        print(f"llama.cpp: {installer.message or 'nicht installiert'}")
        return 1
    print(f"{eintrag.label()} in {eintrag.folder}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
