"""Konfiguration von aquaticy.

Alle Einstellungen kommen aus Umgebungsvariablen bzw. der `.env` im
Arbeitsverzeichnis oder unter `~/.config/aquaticy/.env`.
"""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from aquaticy import __version__

ENV_CANDIDATES: tuple[Path, ...] = (
    Path.cwd() / ".env",
    Path.home() / ".config" / "aquaticy" / ".env",
    Path.home() / ".aquaticy" / ".env",
)


DEFAULT_ENV_PATH = Path.home() / ".config" / "aquaticy" / ".env"

DEFAULT_MODEL = "mistral/mistral-large-latest"










PROVIDER_KEYS: dict[str, str] = {
    "mistral": "MISTRAL_API_KEY",
    "nvidia_nim": "NVIDIA_NIM_API_KEY",
    "ollama": "",
    "ollama_chat": "",
    "lm_studio": "",
}












CLOUD_PROVIDERS: frozenset[str] = frozenset({"mistral", "nvidia_nim"})


LOCAL_PROVIDERS: dict[str, tuple[tuple[str, ...], str]] = {
    "ollama": (("OLLAMA_API_BASE",), "http://localhost:11434"),
    "ollama_chat": (("OLLAMA_API_BASE",), "http://localhost:11434"),
    "lm_studio": (("LM_STUDIO_API_BASE",), "http://localhost:1234/v1"),
    "llamafile": (("LLAMAFILE_API_BASE",), "http://127.0.0.1:8080/v1"),
    "hosted_vllm": (("HOSTED_VLLM_API_BASE",), ""),
    "openai": (("OPENAI_API_BASE", "OPENAI_BASE_URL"), ""),
    "text-completion-openai": (("OPENAI_API_BASE", "OPENAI_BASE_URL"), ""),
}

_OLLAMA_CLOUD = re.compile(r"[:-]cloud$", re.IGNORECASE)
MODEL_RULE_TEXT = ("Aquaticy nutzt nur Mistral und NVIDIA NIM (unter Add-ons) oder Modelle auf "
                   "dem Server, zum Beispiel mit Ollama.")

_LOKALE_NAMEN = (".local", ".lan", ".internal", ".home.arpa", ".localhost")

_LOKAL_MERK: dict[str, tuple[float, bool]] = {}
_LOKAL_DAUER = 300.0


class ModelNotAllowed(ValueError):
    """Ein Modell, das weder Mistral, NVIDIA NIM noch lokal ist (seit 12.0.0 Luna)."""

    def __init__(self) -> None:
        super().__init__(MODEL_RULE_TEXT)


def local_address(url: str) -> bool:
    """Zeigt *url* auf den Server selbst oder ins Netz dahinter -- nie ins Internet?

    Ein Name gilt als lokal, wenn er auf ".local", ".lan" ... endet oder jede
    seiner Adressen nicht oeffentlich ist (aquaticy/netguard.py). So geht auch
    ein Docker-Dienst ("ollama") oder ein Rechner im Heimnetz.
    """
    import ipaddress
    import time
    from urllib.parse import urlparse

    from aquaticy import netguard

    adresse = str(url or "").strip()
    if not adresse:
        return False
    try:
        teile = urlparse(adresse if "://" in adresse else f"http://{adresse}")
        host = (teile.hostname or "").lower().rstrip(".")
        port = teile.port
    except ValueError:
        return False
    if not host:
        return False
    with contextlib.suppress(ValueError):
        return not netguard.ip_allowed(str(ipaddress.ip_address(host)))
    if host == "localhost" or host.endswith(_LOKALE_NAMEN):
        return True
    jetzt = time.monotonic()
    gemerkt = _LOKAL_MERK.get(host)
    if gemerkt and jetzt - gemerkt[0] < _LOKAL_DAUER:
        return gemerkt[1]
    try:
        adressen = netguard.resolve(host, port)
    except OSError:
        adressen = []
    lokal = bool(adressen) and not any(netguard.ip_allowed(a) for a in adressen)
    if len(_LOKAL_MERK) > 64:
        _LOKAL_MERK.clear()
    _LOKAL_MERK[host] = (jetzt, lokal)
    return lokal


def model_allowed(model: str, api_base: str = "") -> bool:
    """Darf Aquaticy *model* aufrufen? Mistral, NVIDIA NIM oder lokal -- sonst nicht.

    Args:
        api_base: die Adresse, an die der Aufruf ginge. Leer heisst: die, die
            LiteLLM ohne Angabe nimmt (fuer ``openai/…`` waere das OpenAI).
    """
    modell = str(model or "").strip()
    if not modell:
        return True
    if modell == SPLIT_MODEL_ID:
        return True
    if "/" not in modell:
        return False
    anbieter = provider_of(modell)
    if anbieter in CLOUD_PROVIDERS:
        return True
    if anbieter not in LOCAL_PROVIDERS or _OLLAMA_CLOUD.search(modell):
        return False
    namen, standard = LOCAL_PROVIDERS[anbieter]
    basis = str(api_base or "").strip() or next(
        (_env_str(n) for n in namen if _env_str(n)), standard)
    return local_address(basis)


def check_allowed(model: str, api_base: str = "") -> None:
    """Wie :func:`model_allowed`, nur als Sperre. Raises: :class:`ModelNotAllowed`."""
    if not model_allowed(model, api_base):
        raise ModelNotAllowed()


SEARCH_BACKEND_KEYS: dict[str, str] = {
    "duckduckgo": "",
    "ddg": "",
    "open": "",
    "searxng": "",
    "brave": "BRAVE_API_KEY",
    "tavily": "TAVILY_API_KEY",
}


def find_env_file() -> Path | None:
    """Gibt die erste existierende `.env` aus :data:`ENV_CANDIDATES` zurueck."""
    for candidate in ENV_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def load_env(path: Path | None = None, *, override: bool = False) -> Path | None:
    """Laedt die `.env` in die Prozessumgebung und gibt den benutzten Pfad zurueck."""
    env_path = path or find_env_file()
    if env_path and env_path.is_file():

        load_dotenv(env_path, override=override, interpolate=False)
        return env_path
    return None


def _env_str(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env_str(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env_str(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "ja"}



_GUARD_OFF = frozenset({"0", "false", "no", "off", "nein", "aus"})


def guard_on(raw: str | None) -> bool:
    """Liest den Schalter der Rechts-Leitplanken.

    Anders als bei allen anderen Schaltern schaltet nur ein ausdrueckliches
    "aus" ab. Ein Tippfehler ("an", "True ", "jaa") darf die Leitplanken nicht
    still verschwinden lassen -- bei `_env_bool` waere alles Unbekannte aus.
    """
    return (raw or "").strip().lower() not in _GUARD_OFF


def provider_of(model: str) -> str:
    """`mistral/mistral-large-latest` -> `mistral`."""
    return model.split("/", 1)[0].lower() if "/" in model else model.split("-", 1)[0].lower()


VISION_MODEL_MARKERS = (
    "gemma3", "gemma4", "qwen2-vl", "qwen2.5-vl", "qwen3-vl", "llava",
    "minicpm-v", "moondream", "pixtral", "vision", "gemini", "claude",
    "gpt-4o", "gpt-4.1", "gpt-5",
)


def selected_vision_model(settings: Settings) -> str:
    """Gibt das gewählte Bildmodell zurück, ohne ein Textmodell dafür auszugeben.

    Ein Eintrag im eigenen Vision-Feld ist eine ausdrückliche Auswahl. Bleibt
    es leer, darf das Hauptmodell übernehmen, sofern seine Modell-ID eine
    bekannte bildfähige Familie bezeichnet.
    """
    explicit = settings.vision_model.strip()
    if explicit:
        return explicit
    main = settings.model.strip()
    lowered = main.lower()
    return main if any(marker in lowered for marker in VISION_MODEL_MARKERS) else ""






NO_KEY = "kein-schluessel"



SPLIT_MODEL_ID = "hosted_vllm/aquaticy-verbund"




GENERIC_KEY_NAME = "AQUATICY_API_KEY"


def api_key_name_for(model: str) -> str:
    """Name der Umgebungsvariable, in der der Key fuer *model* erwartet wird.

    Steht der Anbieter nicht in :data:`PROVIDER_KEYS`, gilt
    :data:`GENERIC_KEY_NAME` -- aber nur, wenn dort auch etwas steht. Sonst
    bleibt es dabei, dass LiteLLM sich den Key selbst aus der Umgebung holt.
    """
    provider = provider_of(model)
    if provider in PROVIDER_KEYS:
        return PROVIDER_KEYS[provider]
    return GENERIC_KEY_NAME if _env_str(GENERIC_KEY_NAME) else ""








KNOWN_PREFIXES: frozenset[str] = frozenset({
    *PROVIDER_KEYS, "anthropic", "openai", "gemini",
    "azure", "bedrock", "cerebras", "cohere", "deepseek", "fireworks_ai",
    "groq", "hosted_vllm", "huggingface", "openrouter", "perplexity",
    "sambanova", "together_ai", "vertex_ai", "xai",
})




OLLAMA_THINKERS = re.compile(
    r"deepseek-r1|qwq|gpt-oss|magistral|cogito|reasoning|think|"
    r"qwen3(?!-coder)(?![^/]*instruct)")


def resolve_model(model: str) -> str:
    """Prueft, ob LiteLLM den Anbieter aus *model* ableiten kann.

    Returns:
        Den erkannten Anbieter, oder einen leeren String, wenn nicht.
    """
    model = model.strip()
    if not model:
        return ""
    prefix, _, rest = model.partition("/")
    if prefix in KNOWN_PREFIXES and rest.strip():
        return prefix
    try:
        import litellm

        litellm.suppress_debug_info = True
        _, provider, *_ = litellm.get_llm_provider(model=model)
        return str(provider or "")
    except Exception:
        return ""


def suggest_model(model: str) -> str:
    """Sucht zu einer nicht aufloesbaren Modell-ID eine, die funktioniert.

    Typischer Fall: `nvidia/nemotron-...` statt `nvidia_nim/nvidia/nemotron-...`.
    Vorgeschlagen wird nur, wenn das erste Segment der Eingabe zu einem
    bekannten Anbieter passt -- LiteLLM akzeptiert unter einem gueltigen
    Praefix naemlich jede beliebige Modell-ID, sodass wir sonst Unsinn
    vorschlagen wuerden.
    """
    model = model.strip()
    if "/" not in model:
        return ""
    head = model.split("/", 1)[0].lower()
    if not head:
        return ""
    related = [
        provider
        for provider in PROVIDER_KEYS
        if provider.startswith(head) or head.startswith(provider.split("_", 1)[0])
    ]
    for provider in related:
        candidate = f"{provider}/{model}"
        if resolve_model(candidate):
            return candidate
    return ""




OLLAMA_PORT = 11434


def is_ollama_base(url: str) -> bool:
    """Zeigt *url* auf eine Ollama-Instanz?"""
    from urllib.parse import urlparse

    if not url:
        return False
    parsed = urlparse(url if "://" in url else f"http://{url}")
    return parsed.port == OLLAMA_PORT


def base_fits(url: str, model: str) -> bool:
    """Passt die eigene Adresse zu diesem Modell?

    Wer von Ollama auf einen Cloud-Anbieter wechselt, laesst leicht
    `AQUATICY_API_BASE=http://localhost:11434` stehen. LiteLLM schickt die
    Anfrage dann brav dorthin, und Ollama antwortet mit "404 page not found"
    -- was wie ein Fehler des Anbieters aussieht, aber keiner ist.

    Geprueft wird nur der Ollama-Port, nicht "irgendwas Lokales": ein
    LiteLLM-Proxy auf localhost oder im Heimnetz ist ein voellig
    berechtigter Weg zu einem Cloud-Modell, und den wollen wir nicht
    versehentlich zusperren.
    """
    if not url or provider_of(model) in ("ollama", "ollama_chat"):
        return True
    return not is_ollama_base(url)


def model_problem(model: str, api_base: str = "") -> str:
    """Menschenlesbare Meldung, wenn *model* so nicht benutzbar ist.

    Erst, ob es den Anbieter gibt (ein Tippfehler bekommt seinen Vorschlag),
    dann, ob Aquaticy ihn aufruft (seit 12.0.0 Luna, :func:`model_allowed`).
    """
    if resolve_model(model):
        return "" if model_allowed(model, api_base) else MODEL_RULE_TEXT
    message = (
        f"Modell '{model}' lässt sich keinem Anbieter zuordnen. "
        "Die Modell-ID braucht ein Anbieter-Praefix."
    )
    suggestion = suggest_model(model)
    if suggestion:
        message += f"\nMeintest du: {suggestion}"
    else:
        message += (
            "\nBeispiele: mistral/mistral-large-latest, "
            "nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5, ollama_chat/qwen2.5:7b"
        )
    return message


@dataclass(slots=True)
class Settings:
    """Alle Laufzeit-Einstellungen an einem Ort."""

    model: str = DEFAULT_MODEL
    vision_model: str = ""
    api_base: str = ""


    api_keys: dict[str, str] = field(default_factory=dict)
    search_keys: dict[str, str] = field(default_factory=dict)
    search_backend: str = "duckduckgo"

    search_engines: str = ""

    searxng_url: str = ""
    location: str = ""
    lang: str = "de"
    country: str = "de"
    max_tool_calls: int = 20

    llm_retries: int = 3

    max_tool_chars: int = 8000

    keep_full_results: int = 4

    max_subagents: int = 12

    subagents_auto: bool = True

    triage_timeout: float = 5.0

    planner_timeout: float = 20.0





    context_tokens: int = 16384

    subagent_model: str = ""


    code_model: str = ""




    vm_size: str = "normal"
    vm_image: str = ""
    vm_idle_minutes: int = 20
    vm_memory_mb: int = 1024
    vm_disk_gb: int = 4
    vm_cpus: int = 1



    vm_user_mode: bool = False


    vm_internet: bool = False



    vm_lan: bool = False

    vm_desktop_image: str = "aquaticy-werkstatt-desktop:local"

    subagent_budget: int = 6



    subagent_parallel: int = 0





    rpm: int = 0
    parallel_calls: int = 0

    ha_url: str = ""

    ha_token: str = ""

    github_token: str = ""



    ha_control: bool = False



    ha_direct: bool = False



    google_direct: bool = False

    memory_enabled: bool = True



    memory_key: str = ""


    google_enabled: bool = False




    google_write: bool = False

    google_client_id: str = ""
    google_client_secret: str = ""

    storage_url: str = ""


    storage_access: str = "read"

    lan_enabled: bool = True




    legal_guard: bool = True




    answer_check: bool = True
    auto_model: bool = False


    council: bool = False



    quota: Any = None



    own_key_names: frozenset[str] = frozenset()





    operator_search_backends: frozenset[str] | None = None



    account_email: str = ""


    secret_vault: Any = None



    own_api_base: str = ""




    api_base_for: str = ""

    lan_subnet: str = ""
    fetch_timeout: float = 15.0
    cache_ttl_hours: int = 24
    max_results_default: int = 8



    search_variants: int = 3



    user_agent: str = field(
        default_factory=lambda: (
            f"aquaticy/{__version__} (+https://github.com/jonasenriklaumen-a11y/Aquaticy-Ai; "
            "research agent; contact via repository issues)"
        )
    )
    request_delay_seconds: float = 1.0
    enable_playwright: bool = True
    download_images: bool = False
    data_dir: Path = field(default_factory=lambda: Path.home() / ".aquaticy")
    env_path: Path | None = None

    model_access: Callable[[str], None] | None = field(default=None, repr=False, compare=False)

    model_context: Callable[[str], str] | None = field(default=None, repr=False, compare=False)


    @property
    def db_path(self) -> Path:
        return self.data_dir / "aquaticy.sqlite3"

    @property
    def effective_vision_model(self) -> str:
        return self.vision_model or self.model

    def parallel_for(self, limit: int) -> int:
        """Wie viele von *limit* Subagenten gleichzeitig laufen duerfen.

        Ohne eigene Angabe: zwei bei lokalen Modellen -- die GPU rechnet
        ohnehin nacheinander, mehr bringt nur Speicherdruck. In der Cloud
        alle auf einmal, denn dort ist Warten reine Netzwerklatenz.

        Der Pro-Modus schiebt *limit* hoch; ohne diesen Weg blieben 24
        Teilfragen in zwei Wellen haengen und die Breite kostete das Doppelte
        an Wartezeit statt gar nichts.
        """
        limit = max(1, int(limit or 1))



        from aquaticy.pace import limits_for

        _, erlaubt = limits_for(provider_of(self.effective_subagent_model))
        if erlaubt:
            limit = min(limit, erlaubt)
        if self.subagent_parallel > 0:
            return max(1, min(self.subagent_parallel, limit))
        local = provider_of(self.effective_subagent_model) in ("ollama", "ollama_chat")
        if local:
            return 2




        return limit

    @property
    def effective_parallel(self) -> int:
        """Die Nebenlaeufigkeit fuer die eingestellte Zahl an Subagenten."""
        return self.parallel_for(self.max_subagents)

    @property
    def effective_subagent_model(self) -> str:
        """Womit die Subagenten arbeiten.

        Ohne eigene Angabe das SCHNELLE Modell des Anbieters, nicht das
        Hauptmodell: ein 70B-Modell fuer "such die Oeffnungszeiten" kostet
        Sekunden, und die summieren sich mit jedem der vierundvierzig
        Agenten. Kennt Aquaticy zum Anbieter kein kleines Modell (lokal, oder
        von Hand eingetragen), bleibt es beim Hauptmodell.
        """
        if self.subagent_model:
            return self.subagent_model
        from aquaticy.system import fast_model

        return fast_model(self) or self.model

    @property
    def api_key_name(self) -> str:
        return self.key_name_for(self.model)

    @property
    def api_key(self) -> str:
        return self.key_for(self.model)

    def key_name_for(self, model: str) -> str:
        """Unter welchem Namen der Schluessel fuer *model* gesucht wird.

        Wie :func:`api_key_name_for` -- nur dass auch ein allgemeiner Schluessel
        des KONTOS zaehlt, nicht bloss einer in der Umgebung des Servers.
        """
        provider = provider_of(model)
        if provider in PROVIDER_KEYS:
            return PROVIDER_KEYS[provider]
        if self.api_keys.get(GENERIC_KEY_NAME) or _env_str(GENERIC_KEY_NAME):
            return GENERIC_KEY_NAME
        return ""

    def key_for(self, model: str) -> str:
        """Der Schluessel, mit dem *model* wirklich laeuft.

        Der eigene des Kontos, wenn der Aufruf auf seine Rechnung geht
        (:meth:`key_source`), sonst der gestellte. Hat das Konto zwar einen
        Schluessel fuer diesen Anbieter, laeuft das Modell aber auf einem
        Server des Betreibers, gilt dessen Schluessel -- der eigene geht dort
        nie hin.
        """
        name = self.key_name_for(model)
        if not name:
            return ""
        if self.key_source(model) == "own":
            return self.api_keys[name]
        if name in self.own_key_names:
            return _env_str(name)
        return self.api_keys.get(name) or _env_str(name)

    def route(self, model: str) -> tuple[str, bool]:
        """Wohin ein Aufruf mit *model* geht: (Adresse, ob das Konto sie eingetragen hat).

        Leer heisst: zum Anbieter selbst. Eine eingetragene Adresse gilt nur
        beim Anbieter des Hauptmodells, und nur wenn sie zum Modell passt
        (Ollama-Port, siehe base_fits). Eingetragen hat sie entweder der
        Betreiber (in der Umgebung des Servers) oder -- nur Ultra -- das Konto
        selbst (``own_api_base``).
        """
        if not self.api_base:
            return "", False
        des_kontos = self.api_base == self.own_api_base



        bezug = self.model if des_kontos or not self.api_base_for else self.api_base_for
        if provider_of(model) != provider_of(bezug) or not base_fits(self.api_base, model):
            return "", False
        return self.api_base, des_kontos

    def key_source(self, model: str) -> str:
        """Wer bezahlt diesen Aufruf? "own" = das Konto mit eigenem Schluessel.

        Alles andere ist "operator": ein Schluessel des Betreibers, ein lokales
        Modell auf dem Server (Ollama), ein Anbieter, bei dem LiteLLM sich den
        Schluessel selbst aus der Umgebung des Servers holt -- und jedes
        Modell, das auf einem Server des Betreibers laeuft. Dort ist es
        gestellt, auch wenn das Konto einen Schluessel fuer den Anbieter hat:
        sonst liefe es mit dem eigenen Schluessel beim Betreiber und zaehlte
        nicht, oder der Aufruf ginge an den falschen Rechner.
        """
        if model == SPLIT_MODEL_ID:

            return "operator"
        name = self.key_name_for(model)
        if not (name and name in self.own_key_names and self.api_keys.get(name)):
            return "operator"
        adresse, des_kontos = self.route(model)
        if adresse and not des_kontos:
            return "operator"
        return "own"

    def pace_key(self, model: str) -> str:
        """Wofuer der Takt gilt: eigene Schluessel haben ihren eigenen (aquaticy/pace.py).

        Die Grenzen der Anbieter gelten je Schluessel. Ein Konto mit eigenem
        Schluessel soll weder die anderen ausbremsen noch von ihnen
        ausgebremst werden. Im Namen steht nur ein Hash, nie der Schluessel.
        """
        if self.key_source(model) != "own":
            return ""
        from aquaticy.pace import own_gate

        return own_gate(self.key_for(model))

    def secrets(self) -> list[str]:
        """Alle Schluessel, die in keiner Meldung auftauchen duerfen -- eigene und gestellte."""
        namen = (set(PROVIDER_KEYS.values()) | set(SEARCH_BACKEND_KEYS.values())
                 | {GENERIC_KEY_NAME})
        werte = {self.api_keys.get(n, "") for n in namen} | {self.search_keys.get(n, "")
                                                             for n in namen}
        werte |= {_env_str(n) for n in namen if n}
        return sorted(w for w in werte if w and len(w) >= 8)

    @property
    def search_key_name(self) -> str:
        """Der Schluesselname der gewaehlten Suchmaschine, "" bei den offenen."""
        return SEARCH_BACKEND_KEYS.get(self.search_backend, "")

    def search_key_for(self, backend: str) -> str:
        """Der Schluessel, mit dem *backend* sucht -- "" wenn es keinen gibt.

        Der eigene des Kontos zuerst. Der des Betreibers nur, wenn er fuer
        dieses Konto gilt (:attr:`operator_search_backends`). Bis 9.5.15 kam
        der eigene bei Suchen nie an: die Werkzeuge riefen die Suche ohne
        Schluessel auf, und die nahm den aus der Umgebung des Servers.
        """
        name = SEARCH_BACKEND_KEYS.get((backend or "").lower(), "")
        if not name:
            return ""
        if name in self.own_key_names and self.search_keys.get(name):
            return self.search_keys[name]
        erlaubt = self.operator_search_backends
        if erlaubt is not None and (backend or "").lower() not in erlaubt:
            return ""
        if name in self.own_key_names:
            return _env_str(name)
        return self.search_keys.get(name) or _env_str(name)

    @property
    def search_api_key(self) -> str:
        return self.search_key_for(self.search_backend)

    @property
    def search_key_source(self) -> str:
        """"own", wenn die Suchmaschine mit dem Schluessel des Kontos laeuft."""
        name = self.search_key_name
        if name and name in self.own_key_names and self.search_keys.get(name):
            return "own"
        return "operator"

    def llm_kwargs(self) -> dict[str, Any]:
        """Zusatzargumente fuer `litellm.completion` mit dem Hauptmodell."""
        return self.llm_kwargs_for(self.model)

    def llm_kwargs_for(self, model: str) -> dict[str, Any]:
        """Zusatzargumente fuer einen Aufruf mit *model*.

        api_base und api_key gehoeren zum Anbieter des HAUPTmodells. Laeuft
        das Vision- oder Subagenten-Modell bei einem anderen Anbieter, waeren
        sie falsch -- eine lokale Ollama-Basis-URL an Anthropic zu schicken
        bricht den Aufruf. Dann lieber nichts mitgeben: LiteLLM findet den
        richtigen Key selbst in der Umgebung.

        Ollama-Modelle bekommen zusaetzlich `num_ctx`: ohne das gilt Ollamas
        winziger Default und der Verlauf wird bei Ueberlauf still vorn
        abgeschnitten -- das Modell "vergisst" dann die letzte Frage.
        """
        if self.model_access is not None:
            self.model_access(model)
        if model == SPLIT_MODEL_ID:



            from aquaticy.sharding import endpoint

            adresse, schluessel = endpoint()
            if not adresse:
                raise ValueError("Das auf den Server-Verbund verteilte Modell läuft gerade "
                                 "nicht. Wähle bitte ein anderes Modell.")
            return {"api_base": adresse, "api_key": schluessel or NO_KEY}
        kwargs: dict[str, object] = {}
        gleich = provider_of(model) == provider_of(self.api_base_for or self.model)


        adresse, adresse_des_kontos = self.route(model)
        if self.key_source(model) == "own":







            kwargs["api_key"] = self.key_for(model)
            if adresse_des_kontos:
                kwargs["api_base"] = adresse
        elif adresse_des_kontos:





            kwargs["api_base"] = adresse
            kwargs["api_key"] = NO_KEY
        elif gleich:
            if adresse:
                kwargs["api_base"] = adresse
            schluessel = self.key_for(model)
            if schluessel:
                kwargs["api_key"] = schluessel
        if provider_of(model) in ("ollama", "ollama_chat") and self.context_tokens > 0:
            kwargs["num_ctx"] = self.context_for(model)
        return kwargs

    def context_for(self, model: str) -> int:
        """Das Kontextfenster fuer *model*: wie eingestellt, aber hoechstens 5 GB RAM.

        Seit 11.3.0 Luna wird das fuer positive Werte bei lokalen Modellen gerechnet
        (aquaticy/local_model.py: context_limit) -- gleich, woher der Wert kommt:
        Regler, Einstellungen, Umgebung. Ohne Aufbau gilt die Token-Ersatzgrenze.
        Null behaelt Ollamas Standard bei; Wolkenmodelle halten ihr Fenster selbst.
        """
        wunsch = int(self.context_tokens or 0)
        if wunsch <= 0 or provider_of(model) not in ("ollama", "ollama_chat"):
            return wunsch
        from aquaticy.local_model import ContextLimitError, context_limit, local_name

        name = local_name(model)
        if not name:
            return wunsch
        try:
            return min(wunsch, context_limit(name, self.ollama_base(model)))
        except ContextLimitError:
            raise
        except Exception:
            return min(wunsch, 16384)

    def ollama_base(self, model: str) -> str:
        """Die Adresse des Ollama, bei dem *model* laeuft (wie LiteLLM sie waehlt)."""
        from aquaticy.local_model import DEFAULT_OLLAMA_URL

        adresse, _ = self.route(model)
        return adresse or os.environ.get("OLLAMA_API_BASE", "") or DEFAULT_OLLAMA_URL

    def thinks(self, model: str) -> bool:
        """Kann dieses Modell ueberhaupt "nachdenken"?

        `reasoning_effort` ist fuer Modelle gedacht, die vor der Antwort
        ueberlegen. Ein Llama oder Mistral kennt das nicht: der Wunsch wird
        entweder stillschweigend weggeworfen (dann kostet er nur Bytes) oder
        er kommt als Fehler zurueck -- und der Fehler kostet einen ganzen
        Wiederholungsversuch, also Sekunden, bei jeder Frage. Deshalb wird er
        nur noch dorthin geschickt, wo er hingehoert.
        """
        name = (model or "").lower()
        if provider_of(model) in ("ollama", "ollama_chat"):




            from aquaticy.local_model import can

            kann = can(model, "thinking", self.ollama_base(model))
            if kann is not None:
                return kann


            return OLLAMA_THINKERS.search(name) is not None
        return any(
            wort in name
            for wort in ("reason", "think", "-r1", "/r1", "qwq", "magistral", "o1", "o3", "gpt-5")
        )

    def fast_kwargs_for(self, model: str) -> dict[str, Any]:
        """Wie :meth:`llm_kwargs_for`, aber auf Tempo getrimmt.

        Fuer Vorpruefung und Planung: kein Denk-Modus (Qwen3 & Co. wuerden
        sonst erst seitenweise ueberlegen, bevor drei Stichworte kommen) und
        ein kleines Kontextfenster -- die Prompts sind ein paar hundert
        Token lang, ein 16k-Fenster kostet dort nur Ladezeit.
        """
        kwargs = self.llm_kwargs_for(model)
        if provider_of(model) in ("ollama", "ollama_chat"):
            kwargs["num_ctx"] = 2048
            kwargs["reasoning_effort"] = "disable"
            return kwargs





        if self.thinks(model):
            kwargs["reasoning_effort"] = "low"
        kwargs["drop_params"] = True


        return kwargs

    def missing_requirements(self) -> list[str]:
        """Liste menschenlesbarer Hinweise auf fehlende Pflichtangaben."""
        problems: list[str] = []
        model_issue = model_problem(self.model, self.api_base)
        if model_issue:
            problems.append(model_issue)
        key_name = self.api_key_name
        if key_name and not self.api_key:
            problems.append(f"{key_name} fehlt (für Modell {self.model})")
        backend_key = SEARCH_BACKEND_KEYS.get(self.search_backend, "")
        if backend_key and not self.search_api_key:
            problems.append(f"{backend_key} fehlt (für Suchmaschine {self.search_backend})")
        if self.search_backend == "searxng" and not self.searxng_url:
            problems.append("AQUATICY_SEARXNG_URL fehlt (für Suchmaschine searxng)")
        return problems


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings aus der Umgebung lesen (Ergebnis wird gecacht)."""
    from aquaticy.sandbox import VM_SIZES

    env_path = load_env()

    data_dir = Path(_env_str("AQUATICY_DATA_DIR") or str(Path.home() / ".aquaticy")).expanduser()
    vm_size = _env_str("AQUATICY_VM_SIZE", "normal").strip().lower()
    if vm_size not in VM_SIZES:
        vm_size = "normal"
    vm_preset = VM_SIZES[vm_size]
    settings = Settings(
        model=_env_str("AQUATICY_MODEL", DEFAULT_MODEL),
        vision_model=_env_str("AQUATICY_VISION_MODEL"),
        api_base=_env_str("AQUATICY_API_BASE"),
        search_backend=_env_str("AQUATICY_SEARCH_BACKEND", "duckduckgo").lower(),
        search_engines=_env_str("AQUATICY_SEARCH_ENGINES"),
        searxng_url=_env_str("AQUATICY_SEARXNG_URL"),
        location=_env_str("AQUATICY_LOCATION"),
        lang=_env_str("AQUATICY_LANG", "de"),
        country=_env_str("AQUATICY_COUNTRY", "de"),
        max_tool_calls=_env_int("AQUATICY_MAX_TOOL_CALLS", 20),
        llm_retries=_env_int("AQUATICY_LLM_RETRIES", 3),
        max_tool_chars=_env_int("AQUATICY_MAX_TOOL_CHARS", 8000),
        keep_full_results=_env_int("AQUATICY_KEEP_FULL_RESULTS", 4),
        max_subagents=_env_int("AQUATICY_MAX_SUBAGENTS", 12),
        subagents_auto=_env_bool("AQUATICY_SUBAGENTS_AUTO", True),
        triage_timeout=float(_env_int("AQUATICY_TRIAGE_TIMEOUT", 5)),
        planner_timeout=float(_env_int("AQUATICY_PLANNER_TIMEOUT", 20)),
        context_tokens=_env_int("AQUATICY_CONTEXT_TOKENS", 16384),
        subagent_model=_env_str("AQUATICY_SUBAGENT_MODEL"),
        code_model=_env_str("AQUATICY_CODE_MODEL"),
        vm_size=vm_size,
        vm_image=_env_str("AQUATICY_VM_IMAGE"),
        vm_idle_minutes=_env_int("AQUATICY_VM_IDLE_MINUTES", 20),


        vm_memory_mb=_env_int("AQUATICY_VM_MEMORY_MB", 0) or vm_preset["memory_mb"],
        vm_disk_gb=_env_int("AQUATICY_VM_DISK_GB", 0) or vm_preset["disk_gb"],
        vm_cpus=_env_int("AQUATICY_VM_CPUS", 0) or vm_preset["cpus"],
        vm_user_mode=_env_bool("AQUATICY_VM_USER_MODE", False),
        vm_internet=_env_bool("AQUATICY_VM_INTERNET", False),
        vm_lan=_env_bool("AQUATICY_VM_LAN", False),
        vm_desktop_image=(
            _env_str("AQUATICY_VM_DESKTOP_IMAGE") or "aquaticy-werkstatt-desktop:local"
        ),
        subagent_budget=_env_int("AQUATICY_SUBAGENT_BUDGET", 6),
        subagent_parallel=_env_int("AQUATICY_SUBAGENT_PARALLEL", 0),
        rpm=max(0, _env_int("AQUATICY_RPM", 0)),
        parallel_calls=max(0, _env_int("AQUATICY_PARALLEL_CALLS", 0)),
        ha_url=_env_str("AQUATICY_HA_URL"),
        ha_token=_env_str("HA_TOKEN") or _env_str("AQUATICY_HA_TOKEN"),
        github_token=_env_str("AQUATICY_GITHUB_TOKEN"),
        ha_control=_env_bool("AQUATICY_HA_CONTROL", False),
        ha_direct=_env_bool("AQUATICY_HA_DIRECT", False),
        memory_enabled=_env_bool("AQUATICY_MEMORY", True),
        memory_key=_env_str("AQUATICY_MEMORY_KEY"),
        lan_enabled=_env_bool("AQUATICY_LAN_ENABLED", True),
        legal_guard=guard_on(_env_str("AQUATICY_LEGAL_GUARD")),
        answer_check=_env_bool("AQUATICY_ANSWER_CHECK", True),
        auto_model=_env_bool("AQUATICY_AUTO_MODEL", False),
        council=_env_bool("AQUATICY_COUNCIL", False),
        lan_subnet=_env_str("AQUATICY_LAN_SUBNET"),
        fetch_timeout=float(_env_int("AQUATICY_FETCH_TIMEOUT", 15)),
        cache_ttl_hours=_env_int("AQUATICY_CACHE_TTL_HOURS", 24),
        search_variants=_env_int("AQUATICY_SEARCH_VARIANTS", 3),
        storage_url=_env_str("AQUATICY_STORAGE_URL"),
        storage_access=_env_str("AQUATICY_STORAGE_ACCESS", "read"),
        google_enabled=_env_bool("AQUATICY_GOOGLE", False),
        google_write=_env_bool("AQUATICY_GOOGLE_WRITE", False),
        google_direct=_env_bool("AQUATICY_GOOGLE_DIRECT", False),
        google_client_id=_env_str("GOOGLE_CLIENT_ID"),
        google_client_secret=_env_str("GOOGLE_CLIENT_SECRET"),
        enable_playwright=_env_bool("AQUATICY_ENABLE_PLAYWRIGHT", True),
        data_dir=data_dir,
        env_path=env_path,
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings


def reset_settings_cache() -> None:
    """Nach dem Schreiben einer neuen `.env` aufrufen."""
    get_settings.cache_clear()



ENV_KEY_RE = re.compile(r"[A-Z_][A-Z0-9_]{0,99}")



_ENV_BAD_CHARS = re.compile(r"[\x00-\x1f\x7f\x85\u2028\u2029]")

_ENV_PLAIN = re.compile(r"[A-Za-z0-9_./:@,+\-]*")

ENV_VALUE_MAX = 4000


def env_value_problem(value: str) -> str:
    """Warum *value* nicht in eine .env darf -- "" wenn er darf."""
    if _ENV_BAD_CHARS.search(value):
        return "Zeilenumbrüche und Steuerzeichen sind in einer Einstellung nicht erlaubt."
    if len(value) > ENV_VALUE_MAX:
        return f"Der Wert ist zu lang (höchstens {ENV_VALUE_MAX} Zeichen)."
    return ""


def env_line(key: str, value: str) -> str:
    """Eine .env-Zeile, die genau diesen einen Wert traegt -- nichts sonst.

    Einfache Werte stehen blank, alles andere in doppelten Anfuehrungszeichen
    mit maskiertem Backslash und Anfuehrungszeichen: ein offenes Zeichen im
    Wert kann so keine folgenden Zeilen verschlucken.

    Raises:
        ValueError: ungueltiger Name oder Wert (Zeilenumbruch, Steuerzeichen).
    """
    if not ENV_KEY_RE.fullmatch(key):
        raise ValueError(f"Ungültiger Name für eine Einstellung: {key[:40]!r}")
    wert = str(value)
    problem = env_value_problem(wert)
    if problem:
        raise ValueError(problem)
    if _ENV_PLAIN.fullmatch(wert):
        return f"{key}={wert}"
    return f'{key}="' + wert.replace("\\", "\\\\").replace('"', '\\"') + '"'


def read_env_file(path: Path | None) -> dict[str, str]:
    """Die Werte einer .env -- OHNE ``${VAR}``-Ersetzung.

    python-dotenv ersetzt ``${NAME}`` sonst durch Werte aus der Umgebung des
    Servers. Ein Ort wie ``${MISTRAL_API_KEY}`` holte so einen Schluessel des
    Betreibers in die Einstellungen eines Kontos (bis 9.5.14).
    """
    from dotenv import dotenv_values

    if path is None or not Path(path).is_file():
        return {}
    return {
        str(key): str(value or "")
        for key, value in dotenv_values(path, interpolate=False).items()
        if key
    }


def write_env_file(values: dict[str, str], path: Path | None = None) -> Path:
    """Schreibt/aktualisiert Schluessel in einer `.env`, ohne Fremdzeilen zu verlieren.

    Raises:
        ValueError: Ein Name oder Wert, der die Datei verbiegen wuerde. Dann
            wird gar nichts geschrieben.
    """

    zeilen = {key: env_line(key, value) for key, value in values.items()}
    target = path or find_env_file() or DEFAULT_ENV_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    existing: list[str] = (
        target.read_text(encoding="utf-8").splitlines() if target.is_file() else []
    )
    remaining = dict(values)
    out: list[str] = []
    for line in existing:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        key = stripped.split("=", 1)[0].strip().removeprefix("export ").strip()
        if key in remaining:
            remaining.pop(key)
            out.append(zeilen[key])
        elif key in zeilen:


            continue
        else:
            out.append(line)
    if remaining:
        if out and out[-1].strip():
            out.append("")
        out.extend(zeilen[key] for key in remaining)

    target.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")

    with contextlib.suppress(OSError):
        target.chmod(0o600)
    return target
