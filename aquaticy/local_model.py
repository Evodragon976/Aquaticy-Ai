"""Lokales Modell einrichten -- ohne API-Key, ohne Konto, ohne Cloud.

aquaticy benutzt dafuer [Ollama](https://ollama.com). Dieses Modul kuemmert
sich um alles, was dazu noetig ist: Ollama finden oder installieren, den
Server starten, ein Modell laden und -- das Entscheidende -- pruefen, ob
das Modell wirklich Tool-Calling beherrscht. Ohne das kann der Agent weder
suchen noch Seiten lesen.

Nichts hier laeuft ungefragt: Der Installationsbefehl wird angezeigt und
muss bestaetigt werden.
"""

from __future__ import annotations

import json
import math
import platform
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

#: Wo Ollama standardmaessig lauscht.
DEFAULT_OLLAMA_URL = "http://localhost:11434"

#: LiteLLM-Praefix. `ollama_chat` kann Tool-Calling, das nackte `ollama` nicht.
MODEL_PREFIX = "ollama_chat"


@dataclass(frozen=True, slots=True)
class LocalModel:
    """Ein Modellvorschlag aus dem Ollama-Katalog."""

    name: str
    #: Ungefaehre Downloadgroesse in GB -- der genaue Wert kommt nach dem Laden.
    size_gb: float
    #: Empfohlener freier Speicher in GB (VRAM, sonst Arbeitsspeicher).
    needs_gb: int
    note: str
    #: Kann das Modell Werkzeuge aufrufen? Ohne das kann es nicht recherchieren.
    tools: bool = True
    #: Kann es Bilder ansehen?
    vision: bool = False

    @property
    def model_id(self) -> str:
        """Die ID, wie sie in die `.env` gehoert."""
        return f"{MODEL_PREFIX}/{self.name}"

    @property
    def does_everything(self) -> bool:
        """Deckt dieses Modell Recherche UND Bilder ab?"""
        return self.tools and self.vision


#: Modelle, die BEIDES koennen: Werkzeuge aufrufen und Bilder ansehen.
#: Sie sind die sparsamste Loesung -- nur ein Modell im Speicher statt zwei.
#: Stand August 2026, Groessen sind Richtwerte fuer die Q4-Quantisierung.
DUAL_MODELS: tuple[LocalModel, ...] = (
    LocalModel("gemma4:12b", 6.6, 10, "Vision + Werkzeuge, guter Allrounder", vision=True),
    LocalModel("qwen3-vl:8b", 6.1, 12, "Vision + Werkzeuge, sehr langer Kontext", vision=True),
    LocalModel("gemma4:e4b", 3.5, 6, "Kompakt, läuft auch auf kleinen Karten", vision=True),
    LocalModel("qwen3-vl:4b", 3.3, 6, "Kleinste Vision-Variante mit Werkzeugen", vision=True),
    LocalModel("gemma4:26b", 16.0, 24, "Deutlich stärker, braucht eine große Karte", vision=True),
)

#: Reine Textmodelle -- staerker im Recherchieren, sehen aber nichts.
LOCAL_MODELS: tuple[LocalModel, ...] = (
    LocalModel("qwen3:8b", 5.2, 8, "Sehr zuverlässig beim Werkzeugaufruf"),
    LocalModel("qwen2.5:7b", 4.7, 8, "Bewährt, guter Kompromiss"),
    LocalModel("llama3.1:8b", 4.9, 8, "Breit getestet"),
    LocalModel("qwen2.5:14b", 9.0, 16, "Stärker, braucht mehr Speicher"),
    LocalModel("qwen2.5:3b", 1.9, 4, "Notlösung für schwache Rechner"),
)

DEFAULT_MODEL = LOCAL_MODELS[0]

#: Reine Vision-Modelle, falls das Hauptmodell nichts sieht. Sie brauchen
#: KEIN Tool-Calling: sie beschreiben nur, recherchiert wird danach.
#: Achtung Namensfalle: das offizielle `gemma3` beherrscht in Ollama Vision,
#: aber KEIN Tool-Calling -- es taugt nur als Vision-Modell, nie als
#: Hauptmodell. Erst `gemma4` bringt beides mit.
VISION_MODELS: tuple[LocalModel, ...] = (
    LocalModel(
        "gemma3:4b", 3.3, 6, "Offizielles Google-Modell, sieht gut", tools=False, vision=True
    ),
    LocalModel("qwen3-vl:4b", 3.3, 6, "Klein und aktuell", tools=False, vision=True),
    LocalModel(
        "gemma3:12b", 8.1, 12, "Größere offizielle Gemma-Variante", tools=False, vision=True
    ),
    LocalModel(
        "llava:7b", 4.7, 8, "Bewährt, versteht Fotos und Schilder", tools=False, vision=True
    ),
    LocalModel("minicpm-v", 5.5, 8, "Stark bei Text im Bild", tools=False, vision=True),
    LocalModel("moondream", 1.7, 3, "Winzig, für schwache Rechner", tools=False, vision=True),
)

DEFAULT_VISION_MODEL = VISION_MODELS[0]

#: Leichte Modelle fuer die Subagenten. Sie bekommen eng umrissene
#: Teilfragen und muessen vor allem eines koennen: zuverlaessig Werkzeuge
#: aufrufen. Klein ist hier wichtiger als klug -- mehrere laufen parallel
#: neben dem Hauptmodell, und der Speicher ist endlich.
#: Stand August 2026, Groessen sind Richtwerte fuer Q4.
SUBAGENT_MODELS: tuple[LocalModel, ...] = (
    LocalModel("qwen3:1.7b", 1.4, 3, "Klein und flink, ruft zuverlässig Werkzeuge auf"),
    LocalModel("qwen2.5:3b", 1.9, 4, "Etwas größer, etwas gründlicher"),
    LocalModel("gemma4:e2b", 1.8, 3, "Sparsamste Gemma-Variante"),
    LocalModel("qwen3:4b", 2.5, 5, "Merklich besser, wenn Platz ist"),
    LocalModel("qwen3:0.6b", 0.5, 2, "Winzig – nur für sehr enge Teilfragen"),
)

DEFAULT_SUBAGENT_MODEL = SUBAGENT_MODELS[0]


class LocalModelError(RuntimeError):
    """Etwas an der lokalen Einrichtung ist schiefgegangen."""


# ---------------------------------------------------------------------------
# Ollama finden und starten
# ---------------------------------------------------------------------------
def ollama_binary() -> str | None:
    """Pfad zur `ollama`-Datei, oder `None`."""
    return shutil.which("ollama")


def install_command() -> list[str] | None:
    """Der plattformabhaengige Installationsbefehl.

    Returns:
        Der Befehl als Liste, oder `None`, wenn wir ihn nicht kennen.
    """
    system = platform.system()
    if system == "Linux":
        return ["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"]
    if system == "Darwin":
        if shutil.which("brew"):
            return ["brew", "install", "ollama"]
        return None
    if system == "Windows" and shutil.which("winget"):
        return ["winget", "install", "--id", "Ollama.Ollama", "-e", "--accept-package-agreements"]
    return None


def install_hint() -> str:
    """Was der Nutzer tun soll, wenn wir nicht automatisch installieren koennen."""
    system = platform.system()
    if system == "Darwin":
        return "Lade Ollama von https://ollama.com/download -- oder `brew install ollama`."
    if system == "Windows":
        return (
            "Installiere Ollama mit `winget install Ollama.Ollama` oder lade den "
            "Installer von https://ollama.com/download herunter."
        )
    return "Anleitung: https://ollama.com/download"


def server_running(base_url: str = DEFAULT_OLLAMA_URL, timeout: float = 3.0) -> bool:
    """Antwortet unter *base_url* ein Ollama-Server?"""
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def _tag_list(base_url: str) -> list[dict[str, Any]]:
    """Die Modellliste von ``/api/tags`` -- leer bei allem, was keine ist.

    Seit 9.5.16 auch bei einer Antwort, die kein Ollama-JSON ist (eine Liste,
    Text): bis dahin warf das einen AttributeError bis in ``/api/models``.
    """
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=5)
        if response.status_code != 200:
            return []
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    modelle = payload.get("models") if isinstance(payload, dict) else None
    return [item for item in modelle if isinstance(item, dict)] if isinstance(modelle, list) else []


def installed_models(base_url: str = DEFAULT_OLLAMA_URL) -> list[str]:
    """Namen der bereits geladenen Modelle."""
    return [str(item.get("name", "")) for item in _tag_list(base_url) if item.get("name")]


def start_server(base_url: str = DEFAULT_OLLAMA_URL, wait_seconds: float = 20.0) -> bool:
    """Startet `ollama serve` im Hintergrund und wartet, bis es antwortet."""
    binary = ollama_binary()
    if binary is None:
        return False
    if server_running(base_url):
        return True
    # Unter Windows kennt Popen `start_new_session` nicht; dort loesen
    # Creation-Flags den Prozess von der Konsole und unterdruecken das
    # aufpoppende Fenster.
    extra: dict[str, Any] = {}
    if platform.system() == "Windows":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )
        if flags:
            extra["creationflags"] = flags
    else:
        extra["start_new_session"] = True

    try:
        subprocess.Popen(
            [binary, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **extra,
        )
    except (OSError, ValueError):
        return False

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if server_running(base_url, timeout=1.5):
            return True
        time.sleep(0.5)
    return False


def install_ollama(runner: Callable[[list[str]], int] | None = None) -> bool:
    """Fuehrt den Installationsbefehl aus. Gibt `True` bei Erfolg zurueck."""
    command = install_command()
    if command is None:
        return False
    run = runner or _default_runner
    return run(command) == 0


def _default_runner(command: list[str]) -> int:
    return subprocess.run(command, check=False).returncode


# ---------------------------------------------------------------------------
# Modell laden
# ---------------------------------------------------------------------------
def pull_model(name: str, binary: str | None = None) -> Iterator[str]:
    """Laedt *name* per `ollama pull` und liefert die Fortschrittszeilen.

    Raises:
        LocalModelError: Wenn Ollama fehlt oder der Download scheitert.
    """
    executable = binary or ollama_binary()
    if executable is None:
        raise LocalModelError("Ollama ist nicht installiert.")

    process = subprocess.Popen(
        [executable, "pull", name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    last_line = ""
    for line in process.stdout:
        line = line.strip()
        if line:
            last_line = line
            yield line
    if process.wait() != 0:
        raise LocalModelError(f"`ollama pull {name}` fehlgeschlagen: {last_line or 'kein Grund'}")


def local_name(model_id: str) -> str:
    """Der blanke Modellname, wenn *model_id* ein oertliches Modell ist.

    Ein Wolkenmodell hat nichts zu laden; nur die oertlichen muessen erst in
    den Speicher. Leerer String heisst also: geht uns nichts an.
    """
    text = str(model_id or "").strip()
    for prefix in (f"{MODEL_PREFIX}/", "ollama/"):
        if text.startswith(prefix):
            return text[len(prefix):]
    return ""


def _ohne_latest(name: str) -> str:
    """`gemma3` und `gemma3:latest` sind dasselbe Modell."""
    text = str(name or "").strip()
    return text[: -len(":latest")] if text.endswith(":latest") else text


def is_installed(name: str, installed: list[str]) -> bool:
    """Steht *name* in der Liste von Ollama? `gemma3` und `gemma3:latest` sind dasselbe."""
    gesucht = _ohne_latest(name)
    return bool(gesucht) and any(_ohne_latest(eintrag) == gesucht for eintrag in installed)


def model_is_loaded(model_id: str, base_url: str = DEFAULT_OLLAMA_URL) -> bool | None:
    """Liegt das Modell schon im Speicher?

    Returns:
        `True`/`False` fuer oertliche Modelle, `None` fuer alles andere --
        bei einem Wolkenmodell gibt es nichts zu warten.
    """
    name = local_name(model_id)
    if not name:
        return None
    geladen = {_ohne_latest(eintrag) for eintrag in loaded_models(base_url)}
    return _ohne_latest(name) in geladen


def loaded_models(base_url: str = DEFAULT_OLLAMA_URL) -> list[str]:
    """Modelle, die gerade im Speicher liegen (`ollama ps`)."""
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/ps", timeout=5)
        if response.status_code != 200:
            return []
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    # Wie _tag_list (9.5.34): eine Liste oder "models": null ist kein Absturz.
    modelle = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(modelle, list):
        return []
    return [str(item["name"]) for item in modelle if isinstance(item, dict) and item.get("name")]


def unload_model(name: str, base_url: str = DEFAULT_OLLAMA_URL) -> bool:
    """Wirft *name* aus dem Speicher (keep_alive=0).

    Zwei Modelle gleichzeitig sprengen auf vielen Rechnern den VRAM -- der
    Ollama-Runner stirbt dann mitten im Aufruf. Vor dem Sehtest raeumen wir
    deshalb auf. Fehler sind egal: schlimmstenfalls bleibt alles geladen.
    """
    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/api/generate",
            json={"model": name, "keep_alive": 0},
            timeout=30,
        )
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def free_memory(base_url: str = DEFAULT_OLLAMA_URL) -> list[str]:
    """Entlaedt alle laufenden Modelle. Gibt zurueck, was entladen wurde."""
    return [name for name in loaded_models(base_url) if unload_model(name, base_url)]


def model_size_gb(name: str, base_url: str = DEFAULT_OLLAMA_URL) -> float | None:
    """Tatsaechliche Groesse eines geladenen Modells in GB."""
    for item in _tag_list(base_url):
        if str(item.get("name", "")) == name:
            size = item.get("size")
            if isinstance(size, (int, float)) and size > 0:
                return round(size / 1_000_000_000, 1)
    return None


# ---------------------------------------------------------------------------
# Was ein Modell kann (11.2.2 Terra)
# ---------------------------------------------------------------------------
#: So lange gilt, was Ollama ueber ein Modell gesagt hat (Sekunden).
CAPABILITY_TTL = 600.0

_CAPS: dict[tuple[str, str], tuple[float, frozenset[str] | None]] = {}
#: Benoetigte Metadaten aus /api/show; private Modelltexte werden nicht gemerkt.
_SHOW: dict[tuple[str, str], tuple[float, dict[str, Any] | None]] = {}
#: Hoechstens so viele Modelle gemerkt: ein Name kommt auch aus einer Anfrage
#: (/api/context), und jeder fremde Name waere sonst fuer immer ein Eintrag.
_MERK_MAX = 256
#: Metadaten bleiben auch bei HTTP-Komprimierung und tiefem JSON begrenzt.
MAX_MODEL_INFO_BYTES = 8 * 1024 * 1024
#: Was ein Modell nachweislich NICHT kann -- gelernt aus seiner Fehlermeldung.
_FEHLT: dict[str, set[str]] = {}
_CAPS_LOCK = threading.Lock()

#: Ollama lehnt eine Anfrage ab, wenn das Modell etwas nicht kann:
#: '"qwen2.5-coder:14b" does not support thinking' oder '... does not support tools'.
_FEHLT_RE = re.compile(r"does not support (thinking|tools)", re.IGNORECASE)


def _show(name: str, base_url: str = DEFAULT_OLLAMA_URL,
          timeout: float = 3.0) -> dict[str, Any] | None:
    """Die Antwort von ``/api/show`` zu *name* -- zehn Minuten gemerkt, None ohne Antwort.

    Seit 11.3.0 Luna eine Abfrage fuer beides: die Faehigkeiten und den Aufbau
    des Modells (Schichten, Koepfe), aus dem sich der Speicher je Token ergibt.
    """
    schluessel = (base_url.rstrip("/"), _ohne_latest(name))
    jetzt = time.monotonic()
    with _CAPS_LOCK:
        gemerkt = _SHOW.get(schluessel)
    if gemerkt is not None and jetzt - gemerkt[0] < CAPABILITY_TTL:
        return gemerkt[1]
    daten: dict[str, Any] | None = None
    try:
        from aquaticy.jsonutil import loads
        from aquaticy.netguard import read_response

        frist = time.monotonic() + timeout
        with httpx.stream("POST", f"{schluessel[0]}/api/show", json={"model": name},
                          timeout=timeout, trust_env=False) as antwort:
            roh = loads(read_response(antwort, MAX_MODEL_INFO_BYTES, frist)) \
                if antwort.status_code == 200 else None
        if isinstance(roh, dict):
            # /api/show kann private Systemtexte trainierter Modelle enthalten.
            # Nur die hier benoetigten Felder im gemeinsamen Prozess merken.
            info = roh.get("model_info")
            arch = info.get("general.architecture") if isinstance(info, dict) else None
            aufbau: dict[str, Any] = {}
            if isinstance(info, dict) and isinstance(arch, str) and 0 < len(arch) <= 64:
                aufbau["general.architecture"] = arch
                for feld in ("block_count", "context_length", "embedding_length",
                             "attention.head_count", "attention.head_count_kv",
                             "attention.key_length", "attention.value_length"):
                    wert = info.get(f"{arch}.{feld}")
                    if isinstance(wert, (int, float)) or (
                            isinstance(wert, list) and len(wert) <= 4096
                            and all(isinstance(x, (int, float)) for x in wert)):
                        aufbau[f"{arch}.{feld}"] = wert
            caps = roh.get("capabilities")
            daten = {"model_info": aufbau, "capabilities": (
                [x for x in caps[:64] if isinstance(x, str) and len(x) <= 100]
                if isinstance(caps, list) else None)}
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, UnicodeError):
        daten = None
    with _CAPS_LOCK:
        if len(_SHOW) >= _MERK_MAX:
            _SHOW.clear()
        _SHOW[schluessel] = (jetzt, daten)
    return daten


def ollama_capabilities(name: str, base_url: str = DEFAULT_OLLAMA_URL,
                        timeout: float = 3.0) -> frozenset[str] | None:
    """Was Ollama zu *name* als Faehigkeit fuehrt ("tools", "thinking", ...).

    Aus ``/api/show`` (Ollama 0.9+), zehn Minuten gemerkt. ``None``, wenn
    Ollama es nicht sagt (aelter, nicht erreichbar, Modell unbekannt) --
    dann gilt das Gelernte aus :func:`note_missing`.
    """
    schluessel = (base_url.rstrip("/"), _ohne_latest(name))
    jetzt = time.monotonic()
    with _CAPS_LOCK:
        gemerkt = _CAPS.get(schluessel)
    if gemerkt is not None and jetzt - gemerkt[0] < CAPABILITY_TTL:
        return gemerkt[1]
    daten = _show(name, base_url, timeout)
    liste = daten.get("capabilities") if daten else None
    faehig = (frozenset(str(x).lower() for x in liste if isinstance(x, str))
              if isinstance(liste, list) else None)
    with _CAPS_LOCK:
        if len(_CAPS) >= _MERK_MAX:
            _CAPS.clear()
        _CAPS[schluessel] = (jetzt, faehig)
    return faehig


# ---------------------------------------------------------------------------
# Kontextfenster: hoechstens 5 GB Arbeitsspeicher (11.3.0 Luna)
# ---------------------------------------------------------------------------
#: So viel Arbeitsspeicher darf das Kontextfenster eines lokalen Modells belegen.
CONTEXT_RAM_BYTES = 5 * 1024 ** 3
#: Bevorzugte Regler-Mindestgroesse; harte Modell- und RAM-Grenzen gehen vor.
CONTEXT_MIN = 2048
#: Gilt, wenn Ollama den Aufbau des Modells nicht verraet: der bisherige Standard.
CONTEXT_UNKNOWN_MAX = 16384
#: Ollama haelt den Zwischenspeicher je Token (K und V) in 16 Bit.
_KV_BYTES = 2


class ContextLimitError(ValueError):
    """Selbst ein Token passt laut Modellangaben nicht in das Speicherlimit."""


def _zahl(wert: Any) -> int:
    """Eine positive ganze Zahl aus der Antwort von Ollama -- sonst 0.

    JSON darf auch ``NaN`` und ``Infinity`` enthalten; ``int()`` darauf warf bis
    zur Pruefung fuer 11.3.0 Luna. Negative Werte zaehlen ebenso wenig: zwei davon
    ergaeben zusammen eine kleine positive Zahl und damit ein riesiges Fenster.
    """
    if isinstance(wert, bool) or not isinstance(wert, (int, float)):
        return 0
    if isinstance(wert, float) and (not math.isfinite(wert) or not wert.is_integer()):
        return 0
    return int(wert) if wert > 0 else 0


def kv_bytes_per_token(name: str, base_url: str = DEFAULT_OLLAMA_URL) -> int:
    """Wie viele Bytes das Kontextfenster je Token belegt -- 0, wenn unbekannt.

    Je Schicht ein Schluessel und ein Wert fuer jeden KV-Kopf:
    Schichten x KV-Koepfe x (Schluessel- + Wertlaenge) x 2 Byte. Zaehlt Ollama
    die KV-Koepfe je Schicht einzeln auf, wird ueber die Schichten summiert.
    """
    daten = _show(name, base_url)
    info = daten.get("model_info") if daten else None
    if not isinstance(info, dict):
        return 0
    arch = str(info.get("general.architecture") or "")

    def feld(endung: str) -> Any:
        return info.get(f"{arch}.{endung}")

    schichten = _zahl(feld("block_count"))
    koepfe = feld("attention.head_count")
    kv = feld("attention.head_count_kv")
    breite = _zahl(feld("embedding_length"))
    if not schichten or schichten > 4096:
        return 0
    heads = [_zahl(k) for k in koepfe] if isinstance(koepfe, list) \
        else [_zahl(koepfe)] * schichten
    if len(heads) != schichten or not all(heads):
        return 0
    # Eine abgeschnittene Liste beschreibt nicht alle Schichten. Dann mit
    # vollen Koepfen rechnen, statt fehlende Schichten mit null anzusetzen.
    kv_heads = (kv if isinstance(kv, list) and len(kv) == schichten else
                [(_zahl(kv) or h) if not isinstance(kv, list) else h for h in heads])
    summe = 0
    for h, k in zip(heads, kv_heads, strict=True):
        schluessel = _zahl(feld("attention.key_length")) or breite // h
        wert = _zahl(feld("attention.value_length")) or schluessel
        if not schluessel:
            return 0
        anzahl = _zahl(k) if not isinstance(k, bool) and (k == 0 or _zahl(k)) else h
        summe += anzahl * (schluessel + wert) * _KV_BYTES
    return summe


def trained_context(name: str, base_url: str = DEFAULT_OLLAMA_URL) -> int:
    """Wie lang das Modell trainiert wurde (Tokens) -- 0, wenn unbekannt."""
    daten = _show(name, base_url)
    info = daten.get("model_info") if daten else None
    if not isinstance(info, dict):
        return 0
    return _zahl(info.get(f"{info.get('general.architecture') or ''}.context_length"))


def context_limit(name: str, base_url: str = DEFAULT_OLLAMA_URL) -> int:
    """Das groesste Kontextfenster fuer *name*, das hoechstens 5 GB belegt.

    Ab 1024 Tokens abgerundet auf ganze 1024, nie ueber die trainierte Laenge.
    Verraet Ollama den Aufbau nicht, gilt der bisherige Standard (16384).
    """
    je_token = kv_bytes_per_token(name, base_url)
    grenze = (CONTEXT_RAM_BYTES // je_token) if je_token else CONTEXT_UNKNOWN_MAX
    trainiert = trained_context(name, base_url)
    if trainiert:
        grenze = min(grenze, trainiert)
    if grenze < 1:
        raise ContextLimitError("Dieses Modell braucht mehr Kontextspeicher als erlaubt.")
    # Eine Bedienungs-Mindestgroesse darf harte Obergrenzen nicht vergroessern.
    return grenze // 1024 * 1024 if grenze >= 1024 else grenze


def missing_capability(detail: str) -> str:
    """Was ein Modell laut Fehlermeldung nicht kann: "thinking", "tools" oder ""."""
    treffer = _FEHLT_RE.search(str(detail or ""))
    return treffer.group(1).lower() if treffer else ""


def note_missing(model_id: str, faehigkeit: str) -> bool:
    """Merkt sich, dass *model_id* *faehigkeit* nicht kann. True, wenn das neu ist."""
    with _CAPS_LOCK:
        bekannt = _FEHLT.setdefault(str(model_id), set())
        if faehigkeit in bekannt:
            return False
        bekannt.add(faehigkeit)
        return True


def can(model_id: str, faehigkeit: str, base_url: str = DEFAULT_OLLAMA_URL) -> bool | None:
    """Kann das oertliche *model_id* *faehigkeit*? None = unbekannt (kein Ollama-Modell
    oder Ollama sagt es nicht)."""
    with _CAPS_LOCK:
        if faehigkeit in _FEHLT.get(str(model_id), set()):
            return False
    name = local_name(model_id)
    if not name:
        return None
    faehig = ollama_capabilities(name, base_url)
    return None if faehig is None else faehigkeit in faehig


# ---------------------------------------------------------------------------
# Der entscheidende Test: kann das Modell Werkzeuge aufrufen?
# ---------------------------------------------------------------------------
PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Sucht im Web und liefert Treffer.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Die Suchanfrage."}},
            "required": ["query"],
        },
    },
}

PROBE_MESSAGE = (
    "Suche im Web nach dem aktuellen Wetter in Berlin. "
    "Benutze dafuer das Werkzeug web_search."
)


def verify_tool_calling(model_id: str, api_base: str = DEFAULT_OLLAMA_URL) -> tuple[bool, str]:
    """Prueft an einem echten Aufruf, ob *model_id* Werkzeuge aufrufen kann.

    Das ist die Bedingung, unter der aquaticy ueberhaupt recherchieren kann --
    ein Modell ohne Tool-Calling wuerde aus dem Gedaechtnis antworten.
    """
    try:
        import litellm

        litellm.suppress_debug_info = True
        from aquaticy import llmcall

        response = llmcall.completion(
            model=model_id,
            messages=[{"role": "user", "content": PROBE_MESSAGE}],
            tools=[PROBE_TOOL],
            tool_choice="auto",
            api_base=api_base,
            timeout=180,
        )
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        if resource_problem(detail):
            return False, (
                "Der Ollama-Runner ist abgestuerzt -- dem Rechner ging der Speicher aus. "
                "Ein kleineres Modell sollte durchlaufen."
            )
        return False, detail

    message = response.choices[0].message
    calls = getattr(message, "tool_calls", None) or []
    if not calls:
        text = (getattr(message, "content", "") or "").strip()
        return False, (
            "Das Modell hat geantwortet, aber kein Werkzeug aufgerufen"
            + (f": {text[:120]}" if text else ".")
        )

    name = ""
    first = calls[0]
    function = getattr(first, "function", None)
    if function is not None:
        name = getattr(function, "name", "") or ""
    elif isinstance(first, dict):
        name = str(first.get("function", {}).get("name", ""))
    return True, f"Werkzeug aufgerufen: {name or '(ohne Namen)'}"


# ---------------------------------------------------------------------------
# Speicher-Hinweis
# ---------------------------------------------------------------------------
def total_memory_gb() -> float | None:
    """Gesamter Arbeitsspeicher in GB, soweit ermittelbar."""
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        try:
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 1_048_576, 1)
        except (OSError, ValueError, IndexError):
            return None
    if platform.system() == "Darwin":
        try:
            output = subprocess.run(
                ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=False
            )
            return round(int(output.stdout.strip()) / 1_073_741_824, 1)
        except (OSError, ValueError):
            return None
    if platform.system() == "Windows":
        return _windows_memory_gb()
    return None


def _windows_memory_gb() -> float | None:
    """Arbeitsspeicher unter Windows ueber GlobalMemoryStatusEx."""
    try:
        import ctypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = (
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            )

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        # windll gibt es nur unter Windows; der Aufrufer prueft das vorher.
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined,unused-ignore]
        if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return round(status.ullTotalPhys / 1_073_741_824, 1)
    except (AttributeError, OSError, ValueError):
        return None


def _recommend(models: tuple[LocalModel, ...], memory_gb: float | None) -> LocalModel:
    """Groesstes Modell aus *models*, das in den Speicher passt."""
    available = memory_gb if memory_gb is not None else total_memory_gb()
    if available is None:
        return models[0]
    fitting = [model for model in models if model.needs_gb <= available]
    if not fitting:
        return min(models, key=lambda model: model.needs_gb)
    return max(fitting, key=lambda model: model.size_gb)


def recommend_model(memory_gb: float | None = None) -> LocalModel:
    """Waehlt das groesste Textmodell, das in den Speicher passt."""
    return _recommend(LOCAL_MODELS, memory_gb)


def recommend_vision_model(memory_gb: float | None = None) -> LocalModel:
    """Waehlt das groesste Vision-Modell, das in den Speicher passt."""
    return _recommend(VISION_MODELS, memory_gb)


def recommend_dual_model(memory_gb: float | None = None) -> LocalModel:
    """Waehlt das groesste Modell, das Werkzeuge UND Bilder beherrscht."""
    return _recommend(DUAL_MODELS, memory_gb)


def recommend_subagent_model(
    memory_gb: float | None = None, main: LocalModel | None = None
) -> LocalModel:
    """Waehlt ein leichtes Modell fuer die Subagenten.

    Gerechnet wird mit dem Platz, der neben dem Hauptmodell uebrig bleibt --
    beide liegen im Betrieb gleichzeitig im Speicher.
    """
    available = memory_gb if memory_gb is not None else usable_memory_gb()
    if available is not None and main is not None:
        available = max(1.0, available - main.size_gb - 1.0)
    return _recommend(SUBAGENT_MODELS, available)


def known_model(name: str) -> LocalModel | None:
    """Findet *name* im Katalog -- oder `None` bei einem freien Namen."""
    bare = name.split("/", 1)[-1].strip()
    for model in (*DUAL_MODELS, *LOCAL_MODELS, *VISION_MODELS, *SUBAGENT_MODELS):
        if model.name == bare:
            return model
    return None


def too_big(name: str, memory_gb: float | None = None) -> str:
    """Warnt, wenn ein Modell nicht in den Speicher passt.

    Returns:
        Leerer String, wenn alles passt oder die Groesse unbekannt ist --
        bei freien Namen raten wir nicht.
    """
    model = known_model(name)
    if model is None:
        return ""
    available = memory_gb if memory_gb is not None else usable_memory_gb()
    if available is None or model.needs_gb <= available:
        return ""
    return (
        f"{model.name} braucht etwa {model.needs_gb} GB, verfuegbar sind {available} GB. "
        "Der Ollama-Runner stirbt dann meist mitten im Aufruf."
    )


def fits_together(main: LocalModel, vision: LocalModel, memory_gb: float | None) -> bool:
    """Passen zwei Modelle gleichzeitig in den Speicher?

    aquaticy entlaedt zwar zwischen den Aufrufen, aber wer beides parallel
    halten kann, spart bei jedem Bild das Nachladen.
    """
    if memory_gb is None:
        return False
    # Etwas Luft fuer Kontext und Grafikausgabe.
    return main.size_gb + vision.size_gb + 1.5 <= memory_gb


def plan_setup(memory_gb: float | None = None) -> tuple[LocalModel, LocalModel | None, str]:
    """Schlaegt eine Aufteilung vor: (Hauptmodell, Vision-Modell, Begruendung).

    Ist das Hauptmodell selbst bildfaehig, entfaellt das zweite Modell -- das
    ist auf knappen Karten deutlich sparsamer.
    """
    available = memory_gb if memory_gb is not None else usable_memory_gb()

    dual = recommend_dual_model(available)
    if available is not None and dual.needs_gb <= available:
        return dual, None, (
            f"{dual.name} kann Werkzeuge und Bilder -- ein Modell reicht "
            f"({dual.size_gb} GB statt zwei getrennter)."
        )

    main = recommend_model(available)
    vision = recommend_vision_model(available)
    if fits_together(main, vision, available):
        return main, vision, (
            f"{main.name} und {vision.name} passen zusammen in {available} GB."
        )
    return main, vision, (
        "Beide Modelle passen nicht gleichzeitig hinein -- Aquaticy AI laedt sie "
        "abwechselnd, das kostet bei jedem Bild ein paar Sekunden."
    )


def gpu_vram_gb() -> float | None:
    """Groesster freier VRAM einer NVIDIA-Karte in GB, sonst `None`.

    Fuer die Modellwahl zaehlt der VRAM, nicht der Arbeitsspeicher: laeuft ein
    Modell nicht vollstaendig auf der Karte, wird es zaeh oder stirbt.
    """
    if not shutil.which("nvidia-smi"):
        return None
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sizes: list[float] = []
    for line in output.stdout.strip().splitlines():
        try:
            sizes.append(int(line.strip()) / 1024)
        except ValueError:
            continue
    return round(max(sizes), 1) if sizes else None


def usable_memory_gb() -> float | None:
    """Wonach sich die Modellwahl richtet: VRAM, sonst Arbeitsspeicher."""
    vram = gpu_vram_gb()
    if vram:
        return vram
    memory = total_memory_gb()
    # Ohne GPU laeuft alles auf der CPU; dort ist nicht der ganze RAM nutzbar.
    return round(memory * 0.7, 1) if memory else None


def gpu_hint() -> str:
    """Kurze Notiz zur erkannten GPU, falls `nvidia-smi` vorhanden ist."""
    if not shutil.which("nvidia-smi"):
        return ""
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    line = output.stdout.strip().splitlines()
    return line[0].strip() if line else ""


# ---------------------------------------------------------------------------
# Sehtest: kann das Modell ein Bild wirklich anschauen?
# ---------------------------------------------------------------------------
#: Marker, an denen ein Absturz wegen Speichermangels zu erkennen ist.
RESOURCE_MARKERS = (
    "model runner has unexpectedly stopped",
    "resource limitations",
    "out of memory",
    "cudamalloc",
    "insufficient memory",
    "failed to allocate",
    # So sagt es Ollama selbst: 'model requires more system memory (12.5 GiB)
    # than is available (8.0 GiB)' -- bis 11.2.2 nicht erkannt.
    "requires more system memory",
    "more memory than is available",
)


def resource_problem(detail: str) -> bool:
    """Deutet die Fehlermeldung auf zu wenig Speicher hin?"""
    lowered = detail.lower()
    return any(marker in lowered for marker in RESOURCE_MARKERS)


#: Farbe des Testbildes und die Woerter, die eine richtige Antwort enthaelt.
PROBE_COLOR = (220, 20, 20)
PROBE_COLOR_WORDS = ("rot", "red", "rouge", "rosso")

VISION_PROBE_MESSAGE = (
    "Welche Farbe hat dieses Bild? Antworte mit einem einzigen Wort."
)


def solid_png(rgb: tuple[int, int, int] = PROBE_COLOR, size: int = 64) -> bytes:
    """Erzeugt ein einfarbiges PNG -- ohne zusaetzliche Abhaengigkeit.

    Damit laesst sich pruefen, ob ein Modell das Bild tatsaechlich sieht:
    Die richtige Antwort ist bekannt.
    """
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    scanline = b"\x00" + bytes(rgb) * size
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(scanline * size, 9))
        + chunk(b"IEND", b"")
    )


def verify_vision(model_id: str, api_base: str = DEFAULT_OLLAMA_URL) -> tuple[bool, str]:
    """Prueft an einem echten Bild, ob *model_id* sehen kann.

    Gezeigt wird ein rotes Quadrat und nach der Farbe gefragt. Nennt das
    Modell die Farbe, schaut es das Bild wirklich an -- ein Textmodell kann
    das nicht.
    """
    import base64

    encoded = base64.b64encode(solid_png()).decode("ascii")
    try:
        import litellm

        litellm.suppress_debug_info = True
        response = litellm.completion(
            model=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VISION_PROBE_MESSAGE},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                    ],
                }
            ],
            api_base=api_base,
            max_tokens=20,
            timeout=180,
        )
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        if resource_problem(detail):
            return False, (
                "Der Ollama-Runner ist abgestuerzt -- dem Rechner ging der Speicher aus. "
                "Das sagt nichts darueber, ob das Modell sehen kann."
            )
        return False, detail

    answer = (response.choices[0].message.content or "").strip()
    if not answer:
        return False, "Das Modell hat nichts geantwortet."
    if any(word in answer.lower() for word in PROBE_COLOR_WORDS):
        return True, f"Testbild erkannt (Antwort: {answer[:40]})"
    return False, (
        f"Das Modell hat das Testbild nicht erkannt (Antwort: {answer[:60]}). "
        "Vermutlich kann es keine Bilder sehen."
    )


def vision_env_values(model: LocalModel | str) -> dict[str, str]:
    """Der `.env`-Eintrag fuer das Vision-Modell."""
    model_id = model.model_id if isinstance(model, LocalModel) else str(model)
    if "/" not in model_id:
        model_id = f"{MODEL_PREFIX}/{model_id}"
    return {"AQUATICY_VISION_MODEL": model_id}


def env_values(model: LocalModel | str, base_url: str = DEFAULT_OLLAMA_URL) -> dict[str, str]:
    """Die `.env`-Eintraege fuer ein lokales Modell."""
    model_id = model.model_id if isinstance(model, LocalModel) else str(model)
    if "/" not in model_id:
        model_id = f"{MODEL_PREFIX}/{model_id}"
    return {
        "AQUATICY_MODEL": model_id,
        "AQUATICY_API_BASE": base_url.rstrip("/"),
    }


def as_json(model: LocalModel) -> str:
    """Fuer Logs und Tests."""
    return json.dumps(
        {"name": model.name, "id": model.model_id, "size_gb": model.size_gb},
        ensure_ascii=False,
    )
