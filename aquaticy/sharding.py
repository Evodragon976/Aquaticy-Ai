"""Serverlast aufteilen: ein Modell, verteilt auf die Server des Verbunds.

Ohne diesen Schalter verteilt der Server-Verbund die *Nutzer*: jedes Konto hat
einen Heimserver, und jeder Server rechnet mit seinem eigenen Modell. Zwei
Server mit demselben Modell bedienen doppelt so viele Menschen -- aber kein
Modell darf groesser sein, als ein einzelner Server tragen kann.

Mit "Serverlast aufteilen" verteilt der Verbund stattdessen das *Modell*: seine
Schichten liegen auf mehreren Servern, die bei jedem Wort gemeinsam rechnen. So
laeuft auch ein Modell, das fuer keinen Server allein in den Speicher passt.
Bedient werden dann alle Konten vom Master, denn dort laeuft das Modell.

Technik: llama.cpp (https://github.com/ggml-org/llama.cpp).

* Jedes Mitglied startet ``rpc-server`` und stellt damit Arbeitsspeicher und
  Prozessor (oder seine Grafikkarte) zur Verfuegung. Er lauscht nur auf
  127.0.0.1 -- llama.cpp warnt ausdruecklich davor, ihn offen ins Netz zu
  haengen, denn er kennt weder Anmeldung noch Verschluesselung.
* Der Master startet ``llama-server`` mit ``--rpc`` und dem Modell, das er in
  Ollama hat. llama.cpp verteilt die Schichten nach freiem Speicher.
* Zwischen Master und Mitglied laeuft jede Verbindung durch einen Tunnel ueber
  den Aquaticy-Port des Mitglieds: angemeldet mit dem Schluessel aus der
  Kopplung (den kennen nur der Master und genau dieses Mitglied), dann in
  beide Richtungen mit AES-GCM verschluesselt; jedes Stueck ist nummeriert,
  vertauschte oder veraenderte Stuecke beenden die Verbindung.
* ``llama-server`` lauscht ebenfalls nur auf 127.0.0.1 und verlangt einen
  zufaelligen Schluessel, den nur dieser Aquaticy-Prozess kennt.
* Installieren muss man nichts (seit 11.0.0 Luna): Aquaticy laedt die
  offiziellen Programme von llama.cpp selbst -- auf jedem Server dieselbe
  Fassung, die der Master waehlt (aquaticy/llamacpp.py).
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aquaticy.config import SPLIT_MODEL_ID

MODEL_ID = SPLIT_MODEL_ID

TUNNEL_PATH = "/cluster/tunnel"
TUNNEL_UPGRADE = "aquaticy-tunnel"

READ_SIZE = 256 * 1024

FRAME_MAX = READ_SIZE + 16

MAX_TUNNELS = 8

GATHER_SECONDS = 30.0

RESTART_DELAY = 30.0

MAX_FAILURES = 3

LOAD_TIMEOUT = 45 * 60.0

MEMORY_FACTOR = 1.15
MEMORY_EXTRA_GB = 1.5

TICK_SECONDS = 3.0

MIN_CONTEXT, MAX_CONTEXT = 4096, 32768
MAX_MODEL_BYTES = 2 * 1024 * 1024

RPC_NAMES = ("rpc-server", "llama-rpc-server", "ggml-rpc-server")
SERVER_NAMES = ("llama-server",)
RPC_ENV, SERVER_ENV = "AQUATICY_RPC_SERVER", "AQUATICY_LLAMA_SERVER"

_LOCK = threading.RLock()

_AKTIV: Manager | None = None


class ShardError(RuntimeError):
    """Ein Satz fuer Menschen: warum das verteilte Modell nicht laeuft."""


class TunnelError(RuntimeError):
    """Der Tunnel ist kaputt oder nicht vom Verbund."""





def find_binary(env: str, names: tuple[str, ...]) -> str:
    """Wo das Programm liegt -- "" wenn es fehlt. Die Umgebung darf es vorgeben."""
    vorgabe = os.environ.get(env, "").strip()
    if vorgabe:
        pfad = Path(vorgabe).expanduser()
        return str(pfad) if pfad.is_file() and os.access(pfad, os.X_OK) else ""
    for name in names:
        gefunden = shutil.which(name)
        if gefunden:
            return gefunden
    return ""


def _is_gguf(pfad: Path) -> bool:
    try:
        if not pfad.is_file():
            return False
        with pfad.open("rb") as datei:
            return datei.read(4) == b"GGUF"
    except OSError:
        return False


def ollama_gguf(name: str, base_url: str) -> Path:
    """Die Modelldatei, die Ollama zu *name* gespeichert hat.

    llama.cpp liest dieselben GGUF-Dateien wie Ollama -- ein Modell muss also
    nicht noch einmal heruntergeladen werden. Ollama nennt die Datei in seinem
    Modelfile (``FROM /pfad/zum/blob``); bei Bildmodellen steht dort zusaetzlich
    der Bildteil, darum zaehlt die groesste GGUF-Datei.
    """
    import httpx

    from aquaticy.jsonutil import loads
    from aquaticy.netguard import read_response

    try:
        frist = time.monotonic() + 15.0
        with httpx.stream("POST", f"{base_url.rstrip('/')}/api/show", json={"model": name},
                          headers={"Accept-Encoding": "gzip, deflate"},
                          timeout=15.0, trust_env=False) as antwort:
            daten = loads(read_response(antwort, MAX_MODEL_BYTES, frist)) \
                if antwort.status_code == 200 else {}
    except (httpx.HTTPError, ValueError) as exc:
        raise ShardError("Ollama antwortet nicht — läuft es auf dem Master?") from exc
    text = str(daten.get("modelfile") or "") if isinstance(daten, dict) else ""
    kandidaten: list[Path] = []
    for zeile in text.splitlines():
        zeile = zeile.strip()
        if not zeile.upper().startswith("FROM "):
            continue
        pfad = Path(zeile[5:].strip().strip('"'))
        if pfad.is_absolute() and _is_gguf(pfad):
            kandidaten.append(pfad)
    if not kandidaten:
        raise ShardError(f"Zu „{name}“ hat Ollama keine Modelldatei, die llama.cpp lesen kann.")
    return max(kandidaten, key=lambda pfad: pfad.stat().st_size)


def ollama_models(base_url: str) -> list[dict[str, Any]]:
    """Die Modelle aus Ollama mit Groesse -- ohne die von Auto-Upgrading gebauten."""
    from aquaticy.local_model import _tag_list
    from aquaticy.upgrading import PREFIX

    modelle = []
    for eintrag in _tag_list(base_url):
        name = str(eintrag.get("name") or "")
        groesse = eintrag.get("size")
        if not name or name.startswith(PREFIX):
            continue
        gb = round(groesse / 1_000_000_000, 1) if isinstance(groesse, (int, float)) else 0.0
        modelle.append({"name": name, "size_gb": gb})
    return sorted(modelle, key=lambda m: (-m["size_gb"], m["name"]))


def needed_gb(size_gb: float) -> float:
    """Grobe Schaetzung: so viel Speicher braucht das Modell im ganzen Verbund."""
    return round(max(0.0, size_gb) * MEMORY_FACTOR + MEMORY_EXTRA_GB, 1)


_SPEICHER: dict[str, float] = {}


def node_memory_gb(gpu: bool | None = None) -> float:
    """Was dieser Server zum Modell beitragen kann (VRAM, sonst Arbeitsspeicher).

    *gpu* ``False``: die Ausgabe von llama.cpp rechnet nur auf dem Prozessor --
    dann zaehlt der Arbeitsspeicher, auch wenn eine Karte eingebaut ist.
    Teuer genug (nvidia-smi), um es nur alle zehn Minuten neu zu messen.
    """
    schluessel = "ram" if gpu is False else "gb"
    with _LOCK:
        if time.monotonic() - _SPEICHER.get(f"{schluessel}_at", -1e9) < 600:
            return _SPEICHER.get(schluessel, 0.0)
    try:
        if gpu is False:
            from aquaticy.local_model import total_memory_gb

            gb = round(float(total_memory_gb() or 0.0) * 0.7, 1)
        else:
            from aquaticy.local_model import usable_memory_gb

            gb = float(usable_memory_gb() or 0.0)
    except Exception:
        gb = 0.0
    with _LOCK:
        _SPEICHER.update({f"{schluessel}_at": time.monotonic(), schluessel: gb})
    return gb


def has_own_accelerator() -> bool:
    """Rechnet llama-server auf dem Master selbst auf einer Grafikkarte?

    Dann braucht der Master keinen eigenen rpc-server: llama.cpp nutzt seine
    Karte direkt. Ohne Karte (nur Prozessor) traegt er ueber einen eigenen
    rpc-server bei -- sonst bliebe sein Arbeitsspeicher ungenutzt. Gilt fuer
    selbst gebaute Programme; bei der mitgeladenen Fassung entscheidet deren
    Ausgabe (Manager._karte).
    """
    if sys.platform == "darwin":
        return True
    return nvidia_card()


def nvidia_card() -> bool:
    """Steckt eine NVIDIA-Karte im Server? (alle zehn Minuten neu gemessen)"""
    with _LOCK:
        if time.monotonic() - _SPEICHER.get("gpu_at", -1e9) < 600:
            return bool(_SPEICHER.get("gpu"))
    try:
        from aquaticy.local_model import gpu_vram_gb

        karte = bool(gpu_vram_gb())
    except Exception:
        karte = False
    with _LOCK:
        _SPEICHER.update(gpu_at=time.monotonic(), gpu=float(karte))
    return karte


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _tail(pfad: Path, zeilen: int = 3) -> str:
    """Die letzten Zeilen eines Protokolls -- fuer die Fehlermeldung."""
    try:
        with pfad.open("rb") as datei:
            datei.seek(0, os.SEEK_END)
            groesse = datei.tell()
            datei.seek(max(0, groesse - 4000))
            text = datei.read().decode("utf-8", "replace")
    except OSError:
        return ""
    rest = [z.strip() for z in text.splitlines() if z.strip()]
    return " · ".join(rest[-zeilen:])[:300]


_RPC_CACHE: dict[str, bool] = {}


def _rpc_cache_flag(binary: str) -> list[str]:
    """``-c`` (lokaler Zwischenspeicher fuer Modellteile), wenn die Version es kennt.

    Damit wandert ein Modell nach einem Neustart nicht noch einmal ueber das
    Netz. Aeltere rpc-server brechen bei einem unbekannten Schalter ab --
    deshalb erst in der Hilfe nachsehen.
    """
    if binary not in _RPC_CACHE:
        try:
            hilfe = subprocess.run([binary, "--help"], capture_output=True, timeout=10,
                                   check=False)
            text = (hilfe.stdout + hilfe.stderr).decode("utf-8", "replace")
        except (OSError, subprocess.SubprocessError):
            text = ""
        _RPC_CACHE[binary] = bool(re.search(r"(^|\s)-c,\s*--cache\b", text, re.M))
    return ["-c"] if _RPC_CACHE[binary] else []


def _start(cmd: list[str], log: Path, env: dict[str, str] | None = None) -> subprocess.Popen:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("wb") as ausgabe:
        with contextlib.suppress(OSError):
            log.chmod(0o600)
        return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=ausgabe,
                                stderr=subprocess.STDOUT, env=env)


def _beenden(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    with contextlib.suppress(OSError):
        proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            proc.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=5)





def tunnel_keys(link: bytes, master: bytes, mitglied: bytes) -> tuple[bytes, bytes]:
    """Zwei Schluessel aus dem Kopplungsschluessel und dem Zufall beider Seiten.

    Returns: (Master -> Mitglied, Mitglied -> Master). Jede Verbindung bekommt
    eigene Schluessel; ihre Zaehler beginnen bei null, ohne sich je zu wiederholen.
    """
    from aquaticy.cluster import _hkdf

    salz = hashlib.sha256(b"aquaticy-tunnel\0" + master + mitglied).digest()
    roh = _hkdf(link, salz, "aquaticy-tunnel", 64)
    return roh[:32], roh[32:]


class Richtung:
    """Eine Richtung des Tunnels: nummerierte, verschluesselte Stuecke."""

    AAD = b"aquaticy-tunnel"

    def __init__(self, key: bytes) -> None:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        self._aead = AESGCM(key)
        self._n = 0

    def _nonce(self) -> bytes:
        nonce = self._n.to_bytes(12, "big")
        self._n += 1
        return nonce

    def seal(self, daten: bytes) -> bytes:
        stueck = self._aead.encrypt(self._nonce(), daten, self.AAD)
        return len(stueck).to_bytes(4, "big") + stueck

    def open(self, stueck: bytes) -> bytes:
        from cryptography.exceptions import InvalidTag

        try:
            return self._aead.decrypt(self._nonce(), stueck, self.AAD)
        except InvalidTag as exc:
            raise TunnelError("Ein Stück ist nicht vom Verbund.") from exc


def _genau(quelle: Any, anzahl: int) -> bytes:
    daten = bytearray()
    while len(daten) < anzahl:
        stueck = quelle.read(anzahl - len(daten))
        if not stueck:
            raise EOFError
        daten.extend(stueck)
    return bytes(daten)


def pump_seal(quelle: socket.socket, ziel: socket.socket, richtung: Richtung) -> None:
    """Klartext von *quelle* verschluesselt nach *ziel* -- bis *quelle* schliesst."""
    while True:
        daten = quelle.recv(READ_SIZE)
        if not daten:
            return
        ziel.sendall(richtung.seal(daten))


def pump_open(quelle: Any, ziel: socket.socket, richtung: Richtung) -> None:
    """Verschluesselte Stuecke aus *quelle* (lesbar) entschluesselt nach *ziel*."""
    while True:
        kopf = quelle.read(4)
        if not kopf:
            return
        if len(kopf) < 4:
            kopf += _genau(quelle, 4 - len(kopf))
        laenge = int.from_bytes(kopf, "big")
        if not 16 < laenge <= FRAME_MAX:
            raise TunnelError("Ein Stück hat eine unmögliche Größe.")
        ziel.sendall(richtung.open(_genau(quelle, laenge)))


def _keepalive(sock: socket.socket) -> None:
    sock.settimeout(None)
    with contextlib.suppress(OSError):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    with contextlib.suppress(OSError):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)


def verbinden(netz_lesen: Any, netz: socket.socket, lokal: socket.socket,
              eingang: Richtung, ausgang: Richtung) -> None:
    """Pumpt in beide Richtungen, bis eine Seite schliesst -- dann beide zu.

    *netz* ist die verschluesselte Seite (ueber das Netz), *lokal* der
    Klartext zum rpc-server oder llama-server auf demselben Rechner.
    """
    fertig = threading.Event()

    def ende() -> None:
        if fertig.is_set():
            return
        fertig.set()
        for sock in (netz, lokal):
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)

    def herein() -> None:
        try:
            pump_open(netz_lesen, lokal, eingang)
        except (OSError, EOFError, TunnelError):
            pass
        finally:
            ende()

    faden = threading.Thread(target=herein, name="aquaticy-tunnel-in", daemon=True)
    faden.start()
    try:
        pump_seal(lokal, netz, ausgang)
    except OSError:
        pass
    finally:
        ende()
        faden.join(timeout=10)


_PLAETZE = threading.BoundedSemaphore(MAX_TUNNELS)


def serve_tunnel(handler: Any, verbund: Any, rpc_port: int, raw: bytes, quelle: str) -> None:
    """Mitglied: nimmt einen Tunnel des Masters an und verbindet ihn mit dem rpc-server.

    *handler* ist die HTTP-Verbindung, ueber die die Bitte kam. Sie wird zum
    Tunnel: erst "101 Switching Protocols", dann nur noch verschluesselte Stuecke.
    """
    from aquaticy.cluster import ClusterError

    link, zufall_master = verbund.open_tunnel(raw, quelle)
    if not rpc_port:
        raise ClusterError("Auf diesem Server läuft gerade kein rpc-server.")
    if not _PLAETZE.acquire(blocking=False):
        raise ClusterError("Zu viele Tunnel auf einmal.")
    lokal: socket.socket | None = None
    try:
        lokal = socket.create_connection(("127.0.0.1", int(rpc_port)), timeout=5)
        _keepalive(lokal)
        zufall_mitglied = secrets.token_bytes(16)
        hin, zurueck = tunnel_keys(link, zufall_master, zufall_mitglied)
        handler.wfile.write(
            b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: " + TUNNEL_UPGRADE.encode()
            + b"\r\nConnection: Upgrade\r\nX-Aquaticy-Salt: "
            + base64.b64encode(zufall_mitglied) + b"\r\n\r\n")
        handler.wfile.flush()
        handler.responded = True
        _keepalive(handler.connection)
        verbinden(handler.rfile, handler.connection, lokal, Richtung(hin), Richtung(zurueck))
    finally:
        handler.close_connection = True
        if lokal is not None:
            with contextlib.suppress(OSError):
                lokal.close()
        _PLAETZE.release()


class Tunnel:
    """Master: ein lokaler Port, hinter dem der rpc-server eines Mitglieds steht.

    llama-server verbindet sich mit 127.0.0.1:<port>; jede Verbindung wird zu
    einem eigenen, verschluesselten Tunnel zum Mitglied.
    """

    def __init__(self, verbund: Any, node: str) -> None:
        self.verbund = verbund
        self.node = node
        self.fehler = ""
        self._stop = threading.Event()
        self._offen: set[socket.socket] = set()
        self._lock = threading.Lock()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(MAX_TUNNELS)
        self._sock.settimeout(0.25)
        self.port = int(self._sock.getsockname()[1])
        self._plaetze = threading.BoundedSemaphore(MAX_TUNNELS)
        self._thread = threading.Thread(target=self._annehmen, name="aquaticy-tunnel-accept",
                                        daemon=True)
        self._thread.start()

    def _annehmen(self) -> None:
        while not self._stop.is_set():
            try:
                lokal, _ = self._sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            if self._stop.is_set() or not self._plaetze.acquire(blocking=False):
                lokal.close()
                continue
            threading.Thread(target=self._bedienen, args=(lokal,), name="aquaticy-tunnel",
                             daemon=True).start()

    def _merken(self, *socks: socket.socket) -> None:
        with self._lock:
            if self._stop.is_set():
                for sock in socks:
                    sock.close()
                raise TunnelError("Der Tunnel wurde gestoppt.")
            self._offen.update(socks)

    def _vergessen(self, *socks: socket.socket) -> None:
        with self._lock:
            for sock in socks:
                self._offen.discard(sock)
                with contextlib.suppress(OSError):
                    sock.close()

    def _bedienen(self, lokal: socket.socket) -> None:
        netz: socket.socket | None = None
        lesen = None
        try:
            self._merken(lokal)
            netz, lesen, eingang, ausgang = self.oeffnen()
            self._merken(netz)
            _keepalive(lokal)
            self.fehler = ""
            verbinden(lesen, netz, lokal, eingang, ausgang)
        except (OSError, EOFError, ValueError, TunnelError, RuntimeError) as exc:
            self.fehler = str(exc)[:200] or type(exc).__name__
        finally:
            if lesen is not None:
                with contextlib.suppress(OSError):
                    lesen.close()
            self._vergessen(lokal, *([netz] if netz is not None else []))
            self._plaetze.release()

    def oeffnen(self) -> tuple[socket.socket, Any, Richtung, Richtung]:
        """Baut einen Tunnel zum Mitglied auf. Returns (Socket, Leser, herein, hinaus)."""
        from aquaticy.cluster import lan_ip_ok

        ziel = self.verbund.member(self.node)
        if ziel is None:
            raise TunnelError("Der Server ist kein Mitglied mehr.")
        adresse, port = str(ziel.get("address", "")), int(ziel.get("port") or 0)
        if not adresse or not lan_ip_ok(adresse) or not 0 < port < 65536:
            raise TunnelError("Keine Adresse im eigenen Netz.")
        body, zufall_master, link = self.verbund.tunnel_request(self.node)
        netz = socket.create_connection((adresse, port), timeout=10)
        lesen = None
        try:
            self._merken(netz)
            gastgeber = f"[{adresse}]" if ":" in adresse else adresse
            netz.sendall((f"POST {TUNNEL_PATH} HTTP/1.1\r\nHost: {gastgeber}:{port}\r\n"
                          "Content-Type: application/octet-stream\r\n"
                          f"Content-Length: {len(body)}\r\nConnection: Upgrade\r\n"
                          f"Upgrade: {TUNNEL_UPGRADE}\r\n\r\n").encode() + body)
            lesen = netz.makefile("rb")
            status = lesen.readline(1024)
            if not status.startswith(b"HTTP/1.1 101"):
                raise TunnelError("Der andere Server nimmt keinen Tunnel an "
                                  f"({status.decode('latin-1', 'replace').strip()[:60]}).")
            zufall_mitglied = b""
            for _ in range(32):
                zeile = lesen.readline(8192)
                if zeile in (b"\r\n", b"\n", b""):
                    break
                name, _, wert = zeile.decode("latin-1").partition(":")
                if name.strip().lower() == "x-aquaticy-salt":
                    with contextlib.suppress(ValueError):
                        zufall_mitglied = base64.b64decode(wert.strip(), validate=True)
            if len(zufall_mitglied) != 16:
                raise TunnelError("Der andere Server hat den Tunnel nicht richtig angenommen.")
            _keepalive(netz)
            hin, zurueck = tunnel_keys(link, zufall_master, zufall_mitglied)
            return netz, lesen, Richtung(zurueck), Richtung(hin)
        except BaseException:
            if lesen is not None:
                with contextlib.suppress(OSError):
                    lesen.close()
            self._vergessen(netz)
            raise

    def stop(self) -> None:
        self._stop.set()
        with contextlib.suppress(OSError):
            self._sock.shutdown(socket.SHUT_RDWR)
        with contextlib.suppress(OSError):
            self._sock.close()
        self._thread.join(timeout=1)
        with self._lock:
            offen, self._offen = list(self._offen), set()
        for sock in offen:
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
            with contextlib.suppress(OSError):
                sock.close()





class RpcWorker:
    """Der rpc-server dieses Servers -- nur auf 127.0.0.1."""

    def __init__(self, log_dir: Path,
                 locate: Callable[[], tuple[str, str, str]] | None = None,
                 memory: Callable[[], float] = node_memory_gb) -> None:
        self.log = log_dir / "rpc-server.log"
        self.port = 0
        self.error = ""

        self.note = ""
        self._locate = locate or (lambda: (find_binary(RPC_ENV, RPC_NAMES), "", ""))
        self._memory = memory
        self._proc: subprocess.Popen | None = None
        self._bereit = False
        self._naechster = 0.0

    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def ensure(self) -> None:
        """Startet den rpc-server, wenn er nicht laeuft (mit Pause nach Fehlern)."""
        if self.running():
            if not self._bereit:
                self._bereit = _horcht(self.port)
            return
        if self._proc is not None:
            self.error = "rpc-server wurde beendet: " + (_tail(self.log) or "ohne Meldung")
            self._proc, self._bereit = None, False
        binary, wartet, fehler = self._locate()
        if not binary:
            self.note = wartet
            self.error = "" if wartet else (fehler or "rpc-server von llama.cpp fehlt auf "
                                            "diesem Server.")
            return
        self.note = ""
        if time.monotonic() < self._naechster:
            return
        self._naechster = time.monotonic() + RESTART_DELAY
        self.port = free_local_port()
        try:
            self._proc = _start([binary, "-H", "127.0.0.1", "-p", str(self.port),
                                 *_rpc_cache_flag(binary)], self.log)
        except OSError as exc:
            self.error = f"rpc-server startet nicht: {type(exc).__name__}"
            return
        self.error, self._bereit = "", False

    @property
    def ready(self) -> bool:
        return self.running() and self._bereit

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        _beenden(proc)
        self._bereit, self.port, self.error, self.note, self._naechster = (
            False, 0, "", "", 0.0)

    def status(self) -> dict[str, Any]:
        return {"ready": self.ready, "error": self.error, "note": self.note,
                "mem_gb": self._memory()}


def _horcht(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=1):
            return True
    except OSError:
        return False


class SplitServer:
    """Master: llama-server mit dem verteilten Modell."""

    def __init__(self, log_dir: Path) -> None:
        self.log = log_dir / "llama-server.log"
        self.phase = "aus"
        self.message = ""
        self.model = ""
        self.workers: list[str] = []
        self.port = 0
        self.api_key = ""
        self.failures = 0
        self.next_try = 0.0
        self.started = 0.0
        self.tunnels: dict[str, Tunnel] = {}
        self._proc: subprocess.Popen | None = None

    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, verbund: Any, model: str, gguf: Path, workers: list[str],
              local_rpc: int, context: int, binary: str) -> None:
        self.stop()
        tunnels: dict[str, Tunnel] = {}
        try:
            for node in workers:
                tunnels[node] = Tunnel(verbund, node)
        except OSError as exc:
            for tunnel in tunnels.values():
                tunnel.stop()
            raise ShardError(f"Tunnel lassen sich nicht öffnen ({type(exc).__name__}).") from exc
        geraete = ([f"127.0.0.1:{local_rpc}"] if local_rpc else []) + [
            f"127.0.0.1:{tunnel.port}" for tunnel in tunnels.values()]
        port = free_local_port()
        schluessel = secrets.token_urlsafe(24)
        cmd = [binary, "-m", str(gguf), "--host", "127.0.0.1", "--port", str(port),
               "-ngl", "999", "--jinja", "-c", str(context), "-np", "1",
               "--alias", "aquaticy-verbund"]
        if geraete:
            cmd += ["--rpc", ",".join(geraete)]


        umgebung = {**os.environ, "LLAMA_API_KEY": schluessel}
        try:
            self._proc = _start(cmd, self.log, umgebung)
        except OSError as exc:
            for tunnel in tunnels.values():
                tunnel.stop()
            raise ShardError(f"llama-server startet nicht ({type(exc).__name__}).") from exc
        self.tunnels, self.port, self.api_key = tunnels, port, schluessel
        self.model, self.workers = model, list(workers)
        self.phase, self.message, self.started = "lädt", "", time.monotonic()

    def poll(self) -> None:
        """Laeuft er noch? Ist das Modell schon geladen?"""
        if self._proc is None:
            return
        code = self._proc.poll()
        if code is not None:
            tunnel = next((t.fehler for t in self.tunnels.values() if t.fehler), "")
            meldung = _tail(self.log) or (f"Tunnel: {tunnel}" if tunnel else "ohne Meldung")
            self._aufraeumen()
            self.fail(f"llama-server ist beendet (Code {code}): {meldung}")
            return
        if self.phase == "lädt":
            if _gesund(self.port):
                self.phase, self.message, self.failures = "bereit", "", 0
            elif time.monotonic() - self.started > LOAD_TIMEOUT:
                self.stop()
                self.fail("Das Laden des Modells hat zu lange gedauert.")

    def fail(self, meldung: str) -> None:
        self.phase, self.message = "fehler", meldung[:400]
        self.failures += 1
        self.next_try = time.monotonic() + RESTART_DELAY

    def _aufraeumen(self) -> None:
        for tunnel in self.tunnels.values():
            tunnel.stop()
        self.tunnels, self._proc, self.api_key = {}, None, ""

    def stop(self) -> None:
        proc = self._proc
        self._aufraeumen()
        _beenden(proc)
        if self.phase in ("lädt", "bereit"):
            self.phase = "aus"

    def endpoint(self) -> tuple[str, str]:
        if self.phase == "bereit" and self.running():
            return f"http://127.0.0.1:{self.port}/v1", self.api_key
        return "", ""


def _gesund(port: int) -> bool:
    import httpx

    try:
        return httpx.get(f"http://127.0.0.1:{port}/health", timeout=2.0,
                         trust_env=False).status_code == 200
    except httpx.HTTPError:
        return False





class Manager:
    """Haelt die Prozesse passend zur Einstellung im Verbund -- alle drei Sekunden."""

    def __init__(self, verbund: Any, ollama_url: Callable[[], str],
                 context_tokens: Callable[[], int] = lambda: 16384) -> None:
        self.verbund = verbund
        self.ollama_url = ollama_url
        self.context_tokens = context_tokens
        log_dir = Path(verbund.dir)
        from aquaticy.llamacpp import Installer


        self.llama = Installer(log_dir.parent / "llama.cpp", gpu=nvidia_card)
        self.worker = RpcWorker(log_dir, locate=lambda: self._programm("rpc"),
                                memory=lambda: node_memory_gb(self._karte_oder_offen()))
        self.server = SplitServer(log_dir)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._wunsch: tuple[Any, ...] = ()
        self._sammeln_bis = 0.0
        self._neu = threading.Event()
        self._modelle: tuple[float, list[dict[str, Any]]] = (0.0, [])
        self._thread: threading.Thread | None = None


    def start(self) -> None:
        global _AKTIV
        if self._stop.is_set() or self._thread is not None:
            return
        with _LOCK:
            _AKTIV = self
        self._thread = threading.Thread(target=self._loop, name="aquaticy-sharding",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        global _AKTIV
        self._stop.set()
        self._wake.set()
        with self._lock:
            self.server.stop()
            self.worker.stop()
        with _LOCK:
            if _AKTIV is self:
                _AKTIV = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(TICK_SECONDS)
            self._wake.clear()
            try:
                self.tick()
            except Exception as exc:  # pragma: no cover
                print(f"  [Verbund] Serverlast aufteilen: {type(exc).__name__}: {exc}")

    def request_restart(self) -> None:
        """Neu verteilen -- etwa, wenn ein weiterer Server dazugekommen ist."""
        self._neu.set()
        self.wake()

    def wake(self) -> None:
        """Einstellungen im Hintergrund anwenden, ohne den HTTP-Aufruf zu blockieren."""
        self._wake.set()


    def _fassung(self) -> str:
        """Die Fassung von llama.cpp, die der Master fuer den Verbund gewaehlt hat."""
        from aquaticy.llamacpp import TAG_RE

        tag = str((self.verbund.split() if self.verbund.joined else {}).get("llama") or "")
        return tag if TAG_RE.fullmatch(tag) else ""

    def _programm(self, art: str, *, laden: bool = True) -> tuple[str, str, str]:
        """Wo rpc-server oder llama-server liegt. Returns: (Pfad, wartet, Fehler).

        Eine Vorgabe des Betreibers (AQUATICY_RPC_SERVER, AQUATICY_LLAMA_SERVER)
        hat Vorrang. Sonst die Fassung des Verbunds, die Aquaticy selbst laedt;
        erst wenn das nicht geht, ein llama.cpp aus dem Suchpfad.
        """
        env, namen = (RPC_ENV, RPC_NAMES) if art == "rpc" else (SERVER_ENV, SERVER_NAMES)
        if os.environ.get(env, "").strip():
            return find_binary(env, namen), "", ""
        tag = self._fassung()
        if tag:
            eintrag = self.llama.ensure(tag) if laden else self.llama.installed(tag)
            if eintrag is not None:
                return str(eintrag.rpc_server if art == "rpc" else eintrag.llama_server), "", ""
            if self.llama.phase != "fehler":
                return "", (self.llama.message if self.llama.tag == tag and self.llama.message
                            else f"Lädt llama.cpp {tag} …"), ""
        vorhanden = find_binary(env, namen)
        if vorhanden:
            return vorhanden, "", ""
        if self.llama.phase == "fehler" and self.llama.message:
            return "", "", self.llama.message
        name = "rpc-server" if art == "rpc" else "llama-server"
        return "", "", f"{name} von llama.cpp fehlt auf diesem Server."

    @staticmethod
    def _selbst_gebaut() -> bool:
        """Gibt der Betreiber beide Programme selbst vor, laedt Aquaticy nichts."""
        return bool(os.environ.get(RPC_ENV, "").strip()
                    and os.environ.get(SERVER_ENV, "").strip())

    def _installation(self) -> Any:
        """Die mitgeladene Fassung, falls dieser Server sie gerade nutzt."""
        if os.environ.get(RPC_ENV, "").strip() or os.environ.get(SERVER_ENV, "").strip():
            return None
        tag = self._fassung()
        return self.llama.installed(tag) if tag else None

    def _karte(self) -> bool:
        """Rechnet llama.cpp auf diesem Server mit einer Grafikkarte?"""
        eintrag = self._installation()
        return eintrag.accelerated if eintrag is not None else has_own_accelerator()

    def _karte_oder_offen(self) -> bool | None:
        """Fuer den Speicher: ``False`` = die Ausgabe nutzt nur den Prozessor."""
        eintrag = self._installation()
        return None if eintrag is None or eintrag.accelerated else False


    def tick(self) -> None:
        with self._lock:
            if not self._stop.is_set():
                self._tick()

    def _tick(self) -> None:
        v = self.verbund
        einstellung = v.split() if v.joined else {}
        if not (v.enabled and v.joined and einstellung.get("on")):
            self.server.stop()
            self.server.phase, self.server.message, self.server.failures = "aus", "", 0
            self.worker.stop()
            self._wunsch = ()
            return
        master = v.is_master
        if master and not self._fassung() and not self._selbst_gebaut():


            gewaehlt = self.llama.chosen()
            if gewaehlt:
                with contextlib.suppress(Exception):
                    v.set_split_llama(gewaehlt)
            elif self.llama.phase != "fehler":


                self.server.phase = "wartet"
                self.server.message = self.llama.message or "Sucht die passende Fassung " \
                                                            "von llama.cpp …"
                return
        if not master or not self._karte():
            self.worker.ensure()
        else:
            self.worker.stop()
        if not master:
            self.server.stop()
            self.server.phase = "aus"
            return
        modell = str(einstellung.get("model") or "")
        wunsch = (modell, einstellung.get("at"))
        jetzt = time.monotonic()
        if wunsch != self._wunsch or self._neu.is_set():
            self._wunsch = wunsch
            self._neu.clear()
            self.server.stop()
            self.server.failures = 0
            self.server.phase, self.server.message = "wartet", "Warte auf die anderen Server …"
            self._sammeln_bis = jetzt + GATHER_SECONDS
        lebendig = [m["node"] for m in v.peers() if v.alive(m["node"])]
        bereit = [n for n in lebendig if _split_ready(v.loads.get(n))]
        if self.server.running():
            if any(n not in bereit for n in self.server.workers):

                self.server.stop()
                self.server.phase, self.server.message = (
                    "wartet", "Ein Server ist weggefallen — verteile neu …")
                self._sammeln_bis = jetzt + 10.0
            else:
                self.server.poll()
            return
        if self.server.phase == "fehler" and (self.server.failures >= MAX_FAILURES
                                             or jetzt < self.server.next_try):
            return
        eigener = self.worker if not self._karte() else None
        warten = set(bereit) != set(lebendig) or (eigener is not None and not eigener.ready)
        if jetzt < self._sammeln_bis and warten:
            self.server.phase = "wartet"
            return
        try:
            self._starten(modell, bereit, eigener)
        except ShardError as exc:
            self.server.fail(str(exc))

    def _starten(self, modell: str, bereit: list[str], eigener: RpcWorker | None) -> None:
        if not modell:
            raise ShardError("Wähle zuerst ein Modell aus.")
        binary, wartet, fehler = self._programm("server")
        if not binary:
            if wartet:
                self.server.phase, self.server.message = "wartet", wartet
                return
            raise ShardError(fehler or "llama-server von llama.cpp fehlt auf dem Master.")
        if not bereit and not (eigener is not None and eigener.ready):
            raise ShardError("Kein Server hat einen rpc-server bereit — ist llama.cpp "
                             "auf den Servern installiert?")
        gguf = ollama_gguf(modell, self.ollama_url())


        v = self.verbund
        aktuell = v.split()
        if (self._stop.is_set() or not v.enabled or not v.joined or not v.is_master
                or not aktuell.get("on") or (aktuell.get("model"), aktuell.get("at"))
                != self._wunsch or self._neu.is_set()):
            return
        noetig = needed_gb(gguf.stat().st_size / 1_000_000_000)


        eigen = (node_memory_gb(self._karte_oder_offen())
                 if eigener is None or eigener.ready else 0.0)
        verfuegbar = eigen + sum(
            _split_status_mem(self.verbund.loads.get(n)) for n in bereit)
        if verfuegbar and noetig > verfuegbar:
            raise ShardError(f"Zu wenig Speicher: Das Modell braucht etwa {noetig:.0f} GB, "
                             f"die bereiten Server haben zusammen etwa {verfuegbar:.0f} GB.")
        kontext = max(MIN_CONTEXT, min(MAX_CONTEXT, int(self.context_tokens() or 0)))
        self.server.start(self.verbund, modell, gguf, bereit,
                          eigener.port if eigener is not None and eigener.ready else 0,
                          kontext, binary)


    def worker_status(self) -> dict[str, Any]:
        """Fuer das Lebenszeichen an die anderen Server: bin ich bereit?

        Ein Master mit Grafikkarte rechnet ohne eigenen rpc-server mit ("direct").
        """
        status = self.worker.status()
        if self.verbund.is_master and self._karte():
            status.update(ready=True, direct=True, error="", note="")
        return status

    def rpc_port(self) -> int:
        return self.worker.port if self.worker.ready else 0

    def endpoint(self) -> tuple[str, str]:
        return self.server.endpoint()

    def ready(self) -> bool:
        return bool(self.endpoint()[0])

    def servers(self) -> int:
        """Auf wie vielen Servern das Modell gerade liegt (der Master zaehlt mit)."""
        return len(self.server.workers) + 1 if self.server.running() else 0

    def label(self) -> str:
        return f"{self.server.model} · Verbund" if self.server.model else "Verbund-Modell"

    def models(self) -> list[dict[str, Any]]:
        """Die Modelle aus Ollama (auf dem Master), eine halbe Minute zwischengespeichert."""
        zeit, liste = self._modelle
        if time.monotonic() - zeit < 30:
            return liste
        try:
            liste = ollama_models(self.ollama_url())
        except Exception:
            liste = []
        self._modelle = (time.monotonic(), liste)
        return liste

    def view(self) -> dict[str, Any]:
        v = self.verbund
        einstellung = v.split() if v.joined else {}
        mitglieder = [m for m in v.members() if v.alive(m["node"])]
        speicher = node_memory_gb(self._karte_oder_offen()) + sum(
            _split_status_mem(v.loads.get(m["node"]))
            for m in mitglieder if m["node"] != v.node_id)
        eintrag = self._installation()
        antwort: dict[str, Any] = {
            "on": bool(einstellung.get("on")),
            "model": str(einstellung.get("model") or ""),
            "phase": self.server.phase if v.is_master else (
                "bereit" if self.worker.ready else "aus"),
            "message": self.server.message if v.is_master else self.worker.error,
            "servers": self.servers(),
            "memory_gb": round(speicher, 1),
            "rpc_binary": bool(self._programm("rpc", laden=False)[0]),
            "server_binary": bool(self._programm("server", laden=False)[0]),
            "self": self.worker.status(),


            "auto_install": bool(self.llama.names()),
            "llama": {**self.llama.status(), "fassung": self._fassung(),
                      "label": eintrag.label() if eintrag is not None else ""},
        }
        if v.is_master:
            antwort["models"] = [{**m, "needed_gb": needed_gb(m["size_gb"])}
                                 for m in self.models()]
        return antwort


def _split_ready(last: Any) -> bool:
    return isinstance(last, dict) and isinstance(last.get("split"), dict) \
        and last["split"].get("ready") is True


def _split_status_mem(last: Any) -> float:
    if not _split_ready(last):
        return 0.0
    try:
        wert = float(last["split"].get("mem_gb") or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return wert if 0.0 <= wert <= 100_000.0 else 0.0


def endpoint() -> tuple[str, str]:
    """(Adresse, Schluessel) des verteilten Modells -- ("", "") wenn es nicht laeuft."""
    with _LOCK:
        aktiv = _AKTIV
    return aktiv.endpoint() if aktiv is not None else ("", "")

