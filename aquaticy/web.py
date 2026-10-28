"""Weboberflaeche fuer aquaticy -- derselbe Agent, nur im Browser.

Bewusst ohne Webframework: die Standardbibliothek reicht fuer den lokalen
Mehrnutzer-Server, und jede zusaetzliche Abhaengigkeit macht die Installation
komplizierter. Der Server laeuft auf dem eigenen Rechner oder Heimserver.

Die Zwischenschritte gehen als Server-Sent Events an den Browser -- dieselben
Ereignisse, die im Terminal die "[Suche]"- und "[Lese]"-Zeilen erzeugen.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import gzip
import hashlib
import hmac
import io
import json
import logging
import math
import os
import queue
import re
import secrets
import socket
import sqlite3
import sys
import threading
import time
import unicodedata
import webbrowser
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import replace
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from aquaticy import INTERNAL, VERSION_LABEL, __version__, botguard, cluster, webview
from aquaticy.auth import Account, AuthStore, RateLimiter, pro_code_for
from aquaticy.cache import Cache
from aquaticy.config import (
    DEFAULT_ENV_PATH,
    SEARCH_BACKEND_KEYS,
    SPLIT_MODEL_ID,
    Settings,
    api_key_name_for,
    base_fits,
    find_env_file,
    get_settings,
    guard_on,
    load_env,
    read_env_file,
    reset_settings_cache,
    resolve_model,
    selected_vision_model,
    suggest_model,
    write_env_file,
)
from aquaticy.guardrails import rules_overview
from aquaticy.legal import LEGAL_ROUTES, LEGAL_VERSION, legal_page

UI_FILE = Path(__file__).with_name("webui.html")


STATIC_DIR = Path(__file__).with_name("static")
STATIC_FILES: dict[str, str] = {
    "/favicon.ico": "favicon-32.png",
    "/favicon-32.png": "favicon-32.png",
    "/favicon-64.png": "favicon-64.png",
    "/apple-touch-icon.png": "apple-touch-icon.png",
    "/logo.png": "logo.png",
}



DEFAULT_PORT = 8765



HEARTBEAT_SECONDS = 10.0




MAX_RUN_EVENTS = 20_000





PAST_THE_LIMIT = frozenset({"done"})






RESUME_WINDOW = 7 * 24 * 3600



PIN_WINDOW = 15 * 60


class Run:
    """Ein laufender Turn -- auf dem Server, nicht im Browser.

    Bisher lebte eine Anfrage in ihrer Verbindung: wer die Seite verliess,
    das Handy sperrte oder in den Zug fuhr, riss die Leitung ab. Der Agent
    arbeitete zwar weiter (der Faden laeuft), aber die Ereignisse gingen ins
    Leere, und zurueck kam man vor einen leeren Chat -- die Frage musste neu
    gestellt werden, samt aller Wartezeit noch einmal.

    Jetzt schreibt der Turn in diesen Puffer, und die Verbindung liest nur
    daraus. Reisst sie ab, laeuft der Lauf weiter; kommt jemand zurueck,
    haengt er sich ab Ereignis 0 wieder an und sieht den ganzen Verlauf
    nachwachsen, als waere er nie weg gewesen.
    """

    def __init__(self, run_id: str, question: str) -> None:
        self.id = run_id
        self.question = question


        self.chat = ""
        self.started = time.time()
        self.finished = 0.0
        self.events: list[dict[str, Any]] = []
        self.done = False


        self.delivered = False
        self._cond = threading.Condition()

        self._clipped = False

    def add(self, event: dict[str, Any]) -> None:
        with self._cond:
            if len(self.events) < MAX_RUN_EVENTS or event.get("type") in PAST_THE_LIMIT:
                self.events.append(event)
            elif not self._clipped:


                self._clipped = True
                self.events.append(
                    {
                        "type": "note",
                        "text": "Die Anzeige ist hier gekürzt — die vollständige Antwort "
                        "steht in den letzten Chats.",
                    }
                )
            self._cond.notify_all()

    def finish(self) -> None:
        with self._cond:
            self.done = True
            self.finished = time.time()
            self._cond.notify_all()

    def read(self, since: int, timeout: float) -> tuple[list[dict[str, Any]], int, bool]:
        """Wartet auf neue Ereignisse ab *since*.

        Returns:
            Die neuen Ereignisse, den neuen Stand und ob der Lauf fertig ist.
        """
        with self._cond:
            if since >= len(self.events) and not self.done:
                self._cond.wait(timeout)
            return self.events[since:], len(self.events), self.done

    @property
    def resumable(self) -> bool:
        """Lohnt es sich, diesen Lauf beim Laden wieder aufzunehmen?"""
        if not self.done:
            return True
        return not self.delivered and (time.time() - self.finished) < RESUME_WINDOW

    @property
    def pinned(self) -> bool:
        """Darf der Chat dieses Laufs nicht aus dem Speicher? Laeuft er oder ist er
        eben erst ungesehen fertig geworden (11.4.1 Luna)."""
        if not self.done:
            return True
        return not self.delivered and (time.time() - self.finished) < PIN_WINDOW

    def state(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "chat": self.chat,
            "events": len(self.events),
            "running": not self.done,
            "resume": self.resumable,
            "seconds": round(time.time() - self.started, 1),
        }


class RunCapacityError(RuntimeError):
    """Der Chat hat bereits die hoechste Zahl laufender Anfragen."""


class RunBook:
    """Die Laeufe eines Chats -- jeder ueber seine Kennung wiederzufinden (9.5.15).

    Eine zweite Anfrage darf warten, bis die erste fertig ist (die Sitzung
    reicht sie nacheinander durch und sagt das auch). Bis 9.5.14 kannte das
    Buch aber nur "den aktuellen" Lauf: der zweite ueberschrieb den ersten,
    und wer die Seite neu lud, haengte sich womoeglich an den falschen. Jetzt
    hat jeder Lauf seine Kennung, ``get`` findet genau ihn, und die
    Oberflaeche nimmt genau den Lauf wieder auf, den ``/api/runstate`` nannte.
    """


    KEEP = 8

    HARD = 32

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.current: Run | None = None
        self._runs: dict[str, Run] = {}

    def start(self, question: str) -> Run:
        """Ein neuer Lauf -- atomar angelegt und unter seiner Kennung abgelegt."""
        with self._lock:
            if sum(not r.done for r in self._runs.values()) >= self.HARD:


                raise RunCapacityError("Zu viele Anfragen laufen in diesem Chat. Warte auf eine "
                                       "Antwort.")
            lauf = Run(secrets.token_hex(8), question)
            self._runs[lauf.id] = lauf



            while len(self._runs) > self.KEEP:
                alt = next((k for k, r in self._runs.items() if r.done), None)
                if alt is None:
                    break
                self._runs.pop(alt)
            self.current = lauf
            return lauf

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            return self._runs.get(str(run_id or ""))

    def latest(self) -> Run | None:
        """Der zuletzt gestartete Lauf -- den nennt ``/api/runstate`` samt Kennung."""
        with self._lock:
            return self.current


RUNS = RunBook()



STRONG_TTL = 30.0




_strong_cache: dict[str, dict[str, Any]] = {}


def strong_models(limit: int = 3, purpose: str = "work") -> list[dict[str, str]]:
    """Die staerksten erreichbaren Modelle -- gemerkt fuer ein paar Sekunden."""
    from aquaticy.system import strongest_models

    purpose = "code" if purpose == "code" else "work"
    settings = SESSION.settings()
    cache_key = f"{settings.data_dir}|{purpose}"
    eintrag = _strong_cache.setdefault(cache_key, {"when": 0.0, "models": []})
    if time.time() - float(eintrag["when"]) > STRONG_TTL:
        try:
            eintrag["models"] = strongest_models(
                settings, limit=max(3, limit), purpose=purpose
            )
        except Exception:
            eintrag["models"] = []
        eintrag["when"] = time.time()
    models = list(eintrag["models"])
    if settings.model_access is not None:
        permitted = []
        for model in models:
            try:
                settings.model_access(model["id"])
            except ValueError:
                continue
            permitted.append(model)
        models = permitted
    return models[:limit]


def forget_strong_models(data_dir: Path | None = None) -> None:
    """Nach einer Aenderung an Modell oder Schluesseln neu nachsehen.

    Mit *data_dir* nur fuer dieses Konto: die Schluessel eines Kontos aendern
    nichts an der Rangfolge der anderen, die sollen nicht alle neu rechnen.
    """
    if data_dir is None:
        _strong_cache.clear()
        return
    praefix = f"{data_dir}|"
    for key in list(_strong_cache):
        if key.startswith(praefix):
            _strong_cache.pop(key, None)


SETTING_KEYS: tuple[str, ...] = (
    "AQUATICY_MODEL",
    "AQUATICY_VISION_MODEL",
    "AQUATICY_SUBAGENT_MODEL",
    "AQUATICY_CODE_MODEL",
    "AQUATICY_API_BASE",
    "AQUATICY_SEARCH_BACKEND",
    "AQUATICY_SEARCH_ENGINES",
    "AQUATICY_SEARCH_VARIANTS",
    "AQUATICY_SEARXNG_URL",
    "AQUATICY_LOCATION",
    "AQUATICY_LANG",
    "AQUATICY_COUNTRY",
    "AQUATICY_SUBAGENTS_AUTO",
    "AQUATICY_MAX_SUBAGENTS",
    "AQUATICY_SUBAGENT_BUDGET",
    "AQUATICY_SUBAGENT_PARALLEL",
    "AQUATICY_RPM",
    "AQUATICY_PARALLEL_CALLS",
    "AQUATICY_MAX_TOOL_CALLS",
    "AQUATICY_CONTEXT_TOKENS",
    "AQUATICY_PLANNER_TIMEOUT",
    "AQUATICY_ENABLE_PLAYWRIGHT",
    "AQUATICY_HA_URL",
    "AQUATICY_HA_CONTROL",
    "AQUATICY_HA_DIRECT",
    "AQUATICY_GOOGLE",
    "AQUATICY_GOOGLE_WRITE",
    "AQUATICY_GOOGLE_DIRECT",
    "AQUATICY_STORAGE_URL",
    "AQUATICY_STORAGE_ACCESS",
    "AQUATICY_LAN_ENABLED",
    "AQUATICY_LAN_SUBNET",
    "AQUATICY_MEMORY",
    "AQUATICY_VM_SIZE",
    "AQUATICY_VM_USER_MODE",
    "AQUATICY_VM_INTERNET",
    "AQUATICY_VM_LAN",
    "AQUATICY_LEGAL_GUARD",
    "AQUATICY_AUTO_MODEL",
    "AQUATICY_COUNCIL",
)






NUMBERS: dict[str, tuple[int, int]] = {


    "AQUATICY_SEARCH_VARIANTS": (1, 3),
    "AQUATICY_MAX_SUBAGENTS": (1, 12),
    "AQUATICY_SUBAGENT_BUDGET": (1, 40),



    "AQUATICY_SUBAGENT_PARALLEL": (0, 12),
    "AQUATICY_RPM": (1, 100_000),
    "AQUATICY_PARALLEL_CALLS": (1, 64),
    "AQUATICY_MAX_TOOL_CALLS": (1, 200),


    "AQUATICY_CONTEXT_TOKENS": (256, 2_000_000),
    "AQUATICY_PLANNER_TIMEOUT": (1, 600),
}


CHOICES: dict[str, tuple[str, ...]] = {
    "AQUATICY_STORAGE_ACCESS": ("off", "read", "write"),
    "AQUATICY_VM_SIZE": ("normal", "plus"),
}



MAX_VALUE_CHARS = 2_000


HA_TOKEN_FIELD = "__HA_TOKEN__"



GOOGLE_ID_FIELD = "__GOOGLE_ID__"
GOOGLE_SECRET_FIELD = "__GOOGLE_SECRET__"



MAX_UPLOAD_BYTES = 25_000_000


MAX_UPLOADS = 5





MAX_MESSAGE_CHARS = 100_000




MAX_BODY_BYTES = MAX_UPLOAD_BYTES * MAX_UPLOADS * 4 // 3 + 1_000_000
REQUEST_READ_TIMEOUT = 30.0


IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}





BLOCKED_UPLOAD_SUFFIXES = frozenset({
    ".php", ".php2", ".php3", ".php4", ".php5", ".php6", ".php7", ".php8", ".phtml",
    ".pht", ".phps", ".phar",
    ".jsp", ".jspx", ".jspf", ".jsw", ".jsv", ".jspa",
})
BLOCKED_UPLOAD_MESSAGE = (
    "PHP- und JSP-Dateien lassen sich nicht hochladen. Wenn du Hilfe mit dem Code "
    "brauchst, füg ihn einfach als Text in die Nachricht ein."
)


def blocked_upload(name: str) -> bool:
    """Ist *name* ein PHP- oder JSP-Skript -- auch hinter einer zweiten Endung?

    Vollbreite Zeichen ("ｐｈｐ") werden per NFKC zu normalen; Steuerzeichen,
    Leerraum und die Tricks mancher Server (";" bei IIS, ":" fuer NTFS-Streams,
    "%00") trennen wie ein Punkt. So faengt die Pruefung auch
    "shell.php\\x00.jpg", "shell.php .png", "x.jsp;.png" und "shell.php."
    (Fund 9.5.18) -- ein harmloses "jsp-vs-php.pdf" aber nicht.
    """
    basis = unicodedata.normalize("NFKC", str(name or "")).replace("\\", "/")
    basis = basis.rstrip("/ ").rsplit("/", 1)[-1].casefold()
    teile = _UPLOAD_TRENNER.split(basis)[1:]
    return any(f".{teil}" in BLOCKED_UPLOAD_SUFFIXES for teil in teile if teil)


_UPLOAD_TRENNER = re.compile(r"[.\s;:%$\x00-\x1f\x7f]+")



_IMAGE_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"), (b"BM", "image/bmp"),
)


def image_mime(data: bytes) -> str:
    """Die Bildart laut den ersten Bytes -- "" fuer alles, was kein Bild ist.

    Zaehlt statt der Angabe des Browsers: Die laesst sich beliebig faelschen
    (Fund 9.5.18: ein PNG mit "image/gif" wurde als .gif abgelegt).
    """
    head = bytes(data[:16])
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return next((mime for magie, mime in _IMAGE_MAGIC if head.startswith(magie)), "")


def looks_like_image(data: bytes) -> bool:
    """Beginnt *data* wirklich wie ein PNG, JPEG, GIF, WebP oder BMP?"""
    return bool(image_mime(data))



TEXT_TYPES = {".txt", ".md", ".csv", ".json", ".log", ".yaml", ".yml"}




KEEP_UPLOADS = 50



MAX_FILE_CHARS = 20_000



TOKEN: str = ""


TOKEN_COOKIE = "aquaticy_token"


DENIED_PAGE = """<!doctype html><html lang="de"><meta charset="utf-8">
<title>Aquaticy AI</title>
<link rel="icon" type="image/png" href="/favicon-32.png">
<body style="background:#0d0f0e;color:#e8ece9;font:15px/1.6 system-ui;
             display:grid;place-items:center;height:100vh;margin:0">
<div style="text-align:center;max-width:34em;padding:20px">
<h1 style="color:#31c46b;font-size:20px">Aquaticy AI</h1>
<p>Diese Oberflaeche ist mit einem Zugangswort geschuetzt.</p>
<p style="color:#8b9590;font-size:13px">Nimm die vollstaendige Adresse, die beim
Start im Terminal steht &mdash; die mit <code>?token=</code> am Ende.</p>
</div></body></html>"""


GENERIC_ERROR = "Bei Aquaticy ist etwas schiefgelaufen. Versuch es gleich noch einmal."


_TECHNISCH = re.compile(
    r"\b[A-Z][A-Za-z]*(?:Error|Exception|Warning)\b|Traceback|\bErrno\b|"
    r"\b(?:HTTP|Fehler|Status|status code|code|Antwort)\s*\(?\d{3}\b|\(\d{3}\)|"
    r"\blitellm\b|\bhttpx\b|\bsqlite3?\b|File \"|line \d+|0x[0-9a-f]{6,}")


def public_error(text: str) -> str:
    """Ein Fehlertext fuer Menschen: Hinweise bleiben, Technisches wird allgemein.

    Ein Satz wie "Das Passwort braucht mindestens 12 Zeichen" sagt, was zu tun
    ist, und bleibt. "TimeoutError: ..." oder "Fehler 502" sagt Nutzern nichts
    und verraet womoeglich Interna -- daraus wird die allgemeine Meldung.
    """
    wert = " ".join(str(text or "").split())
    if not wert or _TECHNISCH.search(wert):
        return GENERIC_ERROR
    return wert



_BIBLIOTHEK = re.compile(
    r"invalid literal|could not convert|codec can't|values to unpack|math domain|"
    r"substring not found|not in list|does not match format|unconverted data|"
    r"embedded null|^Expecting |^Invalid |is not a valid|unsupported|must be|"
    r"out of range|cannot be|object has no|argument", re.IGNORECASE)


def user_hint(exc: BaseException) -> str:
    """Der Satz aus einem absichtlichen Hinweis -- sonst die allgemeine Meldung.

    Absichtliche Hinweise sind ValueError oder FileNotFoundError -- oder eigene
    Unterklassen aus Aquaticy (CalcError, AddOnError ...) -- mit einem Satz
    fuer Menschen ("x.env ist kein Bild."). Was Bibliotheken werfen, ist eine
    fremde Unterklasse (UnicodeDecodeError, JSONDecodeError) oder ein englischer
    Fachtext ("invalid literal for int() ...") -- das wird allgemein (9.6.8 Ultra).
    """
    art = type(exc)
    eigen = art.__module__.split(".")[0] == "aquaticy"
    if not eigen and art not in (ValueError, FileNotFoundError):
        return GENERIC_ERROR
    text = str(exc).strip()
    if not text or _BIBLIOTHEK.search(text):
        return GENERIC_ERROR
    return public_error(text)


def error_page(status: int) -> bytes:
    """Eine Fehlerseite fuer den Browser -- allgemein, im Stil der Oberflaeche."""
    titel, satz = {
        404: ("Diese Seite gibt es nicht.",
              "Vielleicht hat sich ein Tippfehler in die Adresse geschlichen."),
        405: ("Das geht hier nicht.", "Diese Adresse ist nicht zum direkten Aufrufen gedacht."),
    }.get(status, ("Da ist etwas schiefgelaufen.",
                   "Bitte versuch es gleich noch einmal. Wenn es so bleibt, lade die Seite "
                   "später neu."))
    return f"""<!doctype html><html lang="de"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fehler – Aquaticy AI</title>
<link rel="icon" type="image/png" href="/favicon-32.png">
<style>
:root{{--bg:#f6f5f0;--fg:#26251f;--muted:#5f5d54;--accent:#2f7a53;--card:#fffefa;--line:#e3e1d8}}
@media (prefers-color-scheme:dark){{:root{{--bg:#191a17;--fg:#f2f1ea;--muted:#b6b3a8;
  --accent:#5fcf8f;--card:#22231f;--line:#34352f}}}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);
  color:var(--fg);font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;padding:16px;
  box-sizing:border-box}}
main{{max-width:30rem;width:100%;text-align:center;background:var(--card);
  border:1px solid var(--line);border-radius:18px;padding:32px 24px}}
img{{width:56px;height:56px}}
h1{{font-size:21px;margin:14px 0 6px}}
p{{color:var(--muted);margin:0 0 22px}}
a{{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;
  border-radius:999px;padding:9px 20px;font-weight:600}}
</style>
<main><img src="/logo.png" alt=""><h1>{titel}</h1><p>{satz}</p>
<a href="/">Zur Startseite</a></main></html>""".encode()


AUTH_COOKIE = "aquaticy_session"
CONSENT_COOKIE = "aquaticy_consent"
AUTH: AuthStore | None = None

AIGUARD: Any = None

CLUSTER: Any = None

SERVER: Any = None

SHARDING: Any = None

WEBSITE: Any = None

PUBLIC_SERVER: Any = None


LAN_ONLY = False


UPGRADE_DIR: Path | None = None
UPGRADER: Any = None
_CLUSTER_RESTART = threading.Event()


CLUSTER_LOCAL = frozenset({"/api/auth/status", "/api/auth/login", "/api/auth/register",
                           "/api/auth/logout", "/api/auth/challenge", "/api/consent",
                           "/api/cluster"})





POST_WHEN_BANNED = frozenset({
    "/api/auth/logout", "/api/auth/login", "/api/auth/register", "/api/consent",
    "/api/prefs", "/api/stop", "/api/clear", "/api/open", "/api/chat-edit",

    "/api/account/delete", "/api/account/wipe", "/api/account/password",
    "/api/account/logout-all", "/api/account/events-seen",
    "/api/learning",
})

ACCOUNT_ROUTES = frozenset({
    "/api/account/delete", "/api/account/wipe", "/api/account/password",
    "/api/account/logout-all", "/api/account/events-seen",
})

DELETE_WORD = "LÖSCHEN"
AUTH_LIMIT = RateLimiter(attempts=8, window_seconds=60)


LOGIN_FAILS = RateLimiter(attempts=10, window_seconds=15 * 60)


BOT_FAILS = botguard.Failures()
BOT_BANS = botguard.Bans()

AUTH_BODY_BYTES = 16_384
REQUEST_LIMIT = RateLimiter(attempts=240, window_seconds=60)






ADDRESS_LIMIT = RateLimiter(attempts=1200, window_seconds=60)



KEY_TEST_LIMIT = RateLimiter(attempts=10, window_seconds=60)

CLUSTER_HELLO_LIMIT = RateLimiter(attempts=30, window_seconds=60)

_STRING_SETTINGS = {
    "AQUATICY_MODEL": "model",
    "AQUATICY_VISION_MODEL": "vision_model",
    "AQUATICY_SUBAGENT_MODEL": "subagent_model",
    "AQUATICY_CODE_MODEL": "code_model",
    "AQUATICY_API_BASE": "api_base",
    "AQUATICY_SEARCH_BACKEND": "search_backend",
    "AQUATICY_SEARCH_ENGINES": "search_engines",
    "AQUATICY_SEARXNG_URL": "searxng_url",
    "AQUATICY_LOCATION": "location",
    "AQUATICY_LANG": "lang",
    "AQUATICY_COUNTRY": "country",
    "AQUATICY_HA_URL": "ha_url",
    "HA_TOKEN": "ha_token",
    "AQUATICY_GITHUB_TOKEN": "github_token",
    "AQUATICY_LAN_SUBNET": "lan_subnet",
    "AQUATICY_STORAGE_URL": "storage_url",
    "AQUATICY_STORAGE_ACCESS": "storage_access",
    "GOOGLE_CLIENT_ID": "google_client_id",
    "GOOGLE_CLIENT_SECRET": "google_client_secret",
}
_BOOL_SETTINGS = {
    "AQUATICY_SUBAGENTS_AUTO": "subagents_auto",
    "AQUATICY_ENABLE_PLAYWRIGHT": "enable_playwright",
    "AQUATICY_HA_CONTROL": "ha_control",
    "AQUATICY_HA_DIRECT": "ha_direct",
    "AQUATICY_GOOGLE": "google_enabled",
    "AQUATICY_GOOGLE_WRITE": "google_write",
    "AQUATICY_GOOGLE_DIRECT": "google_direct",
    "AQUATICY_LAN_ENABLED": "lan_enabled",
    "AQUATICY_MEMORY": "memory_enabled",
    "AQUATICY_VM_USER_MODE": "vm_user_mode",
    "AQUATICY_VM_INTERNET": "vm_internet",
    "AQUATICY_VM_LAN": "vm_lan",
    "AQUATICY_AUTO_MODEL": "auto_model",
    "AQUATICY_COUNCIL": "council",
}
_INT_SETTINGS = {
    "AQUATICY_SEARCH_VARIANTS": "search_variants",
    "AQUATICY_MAX_SUBAGENTS": "max_subagents",
    "AQUATICY_SUBAGENT_BUDGET": "subagent_budget",
    "AQUATICY_SUBAGENT_PARALLEL": "subagent_parallel",
    "AQUATICY_RPM": "rpm",
    "AQUATICY_PARALLEL_CALLS": "parallel_calls",
    "AQUATICY_MAX_TOOL_CALLS": "max_tool_calls",
    "AQUATICY_CONTEXT_TOKENS": "context_tokens",
    "AQUATICY_PLANNER_TIMEOUT": "planner_timeout",
}



NORMAL_CONTEXT_CAP = 32_768

_MODELL_RE = re.compile(r"^[A-Za-z0-9_.:/@+-]{1,200}$")


def context_view(settings: Settings, model: str, account_cap: int = 0) -> dict[str, Any]:
    """Der Regler fuer das Kontextfenster unter der Modellauswahl (11.3.0 Luna).

    Nur lokale Modelle: ihr Fenster liegt im Arbeitsspeicher dieses Rechners und
    darf hoechstens 5 GB belegen (aquaticy/local_model.py: context_limit).
    Wolkenmodelle halten ihr Fenster beim Anbieter -- dort gibt es nichts zu stellen.
    """
    from aquaticy import local_model as lm
    from aquaticy.config import provider_of

    jetzt = int(settings.context_tokens or 0)
    name = lm.local_name(model) if provider_of(model) in ("ollama", "ollama_chat") else ""
    if not name:
        return {"local": False, "model": model, "tokens": jetzt}
    basis = settings.ollama_base(model)
    je_token = lm.kv_bytes_per_token(name, basis)
    try:
        grenze = lm.context_limit(name, basis)
    except lm.ContextLimitError as exc:
        return {"local": True, "model": model, "error": str(exc)}
    if account_cap:
        grenze = min(grenze, account_cap)
    minimum = min(lm.CONTEXT_MIN, grenze)
    wirksam = min(jetzt, grenze) if jetzt > 0 else None
    return {
        "local": True, "model": model, "tokens": jetzt, "effective": wirksam,
        "min": min(minimum, wirksam) if wirksam is not None else minimum,
        "max": grenze, "known": bool(je_token), "automatic": jetzt <= 0,
        "per_token": je_token,
        "ram_gb": round(wirksam * je_token / 1024 ** 3, 2) if wirksam is not None else None,
        "cap_gb": round(lm.CONTEXT_RAM_BYTES / 1024 ** 3),
    }


def header_for(settings: Settings) -> dict[str, Any]:
    """Die Kopfzeile fuer den Zustand, den der Server fuehrt (aquaticy/webview.py)."""
    kopf = webview.header_view(
        settings,
        ui_state().read(),
        strong_model=(strong_models(1) or [{}])[0].get("id", ""),
        strong_code_model=(strong_models(1, purpose="code") or [{}])[0].get("id", ""),
        ha_connected=bool(settings.ha_url and settings.ha_token),
        problems=settings.missing_requirements(),
    )
    if kopf.get("model") == SPLIT_MODEL_ID and SHARDING is not None:
        kopf["model_label"] = SHARDING.label()
    else:
        from aquaticy.local_model import local_name
        from aquaticy.system import model_usable

        modell = str(kopf.get("model") or "")



        if modell and not local_name(modell) and not model_usable(settings, modell):
            auto = str(kopf.get("model_label") or "").startswith("Auto · ")
            kopf["model_label"] = ("Auto · " if auto else "") + "Modell wählen"
    if UPGRADE_DIR is not None:

        from aquaticy import upgrading

        with contextlib.suppress(Exception):
            schoen = upgrading.display_label(UPGRADE_DIR, kopf.get("model", ""))
            if schoen:
                kopf["model_label"] = kopf["model_label"].replace(
                    kopf["model"].split("/")[-1], schoen)
    return kopf


def storage_view(usage: dict[str, Any]) -> dict[str, Any]:
    """Der Speicherstand mit fertigem Satz ("3,1 von 400 MB belegt · 12 Notizen")."""
    anzahl = int(usage.get("entries") or 0)
    text = (f"{usage.get('used_mb')} von {usage.get('limit_mb')} MB belegt · {anzahl} "
            f"{'Notiz' if anzahl == 1 else 'Notizen'}")
    return {**usage, "text": text, "title": f"{usage.get('used_mb')} von "
            f"{usage.get('limit_mb')} MB belegt"}


def system_gauges(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Die Anzeigen der Auslastung -- Name, Wert, Zusatz, Anteil."""
    anzeigen: list[dict[str, Any]] = []
    cpu, mem, disk, gpu = (data.get(k) or {} for k in ("cpu", "memory", "disk", "gpu"))
    if cpu.get("percent") is not None:
        anzeigen.append({"name": "Prozessor", "value": f"{cpu['percent']} %",
                         "sub": f"{cpu.get('cores')} Kerne · Last {cpu.get('load')}",
                         "percent": cpu["percent"]})
    if mem.get("percent") is not None:
        anzeigen.append({"name": "Arbeitsspeicher", "value": f"{mem.get('used_gb')} GB",
                         "sub": f"von {mem.get('total_gb')} GB", "percent": mem["percent"]})
    if disk.get("percent") is not None:
        anzeigen.append({"name": "Festplatte", "value": f"{disk.get('free_gb')} GB frei",
                         "sub": f"von {disk.get('total_gb')} GB", "percent": disk["percent"]})
    if gpu.get("name"):
        anzeigen.append({"name": "Grafikkarte", "value": f"{gpu.get('percent')} %",
                         "sub": f"{gpu['name']} · {gpu.get('used_gb')} von "
                                f"{gpu.get('total_gb')} GB", "percent": gpu.get("percent")})
    speicher = data.get("storage") or {}
    if speicher:
        anzeigen.append({"name": "Speicher", "value": f"{speicher.get('used_mb')} MB",
                         "sub": f"von {speicher.get('limit_mb')} MB · "
                                f"{speicher.get('entries')} Notizen",
                         "percent": speicher.get("percent")})
    return anzeigen



ROLE_LABELS = {"modelle": "Modelle und etwas Website", "website": "Nur Website"}


def cluster_gauges(verbund: Any) -> list[dict[str, Any]]:
    """Die Auslastung jedes Servers im Verbund -- fuer die Anzeige unter "Auslastung".

    Aus den Lebenszeichen, die sich die Server alle drei Sekunden schicken;
    geprueft in cluster.hardware. Dazu, was der Master dem Server zuteilt.
    """
    rollen = verbund.roles()
    master = verbund.master_node()
    server: list[dict[str, Any]] = []
    for mitglied in verbund.members():
        knoten = str(mitglied.get("node", ""))
        hw = verbund.hw_of(knoten)
        lebendig = verbund.alive(knoten)
        anzeigen: list[dict[str, Any]] = []
        if lebendig and hw.get("cores"):
            anzeigen.append({"name": "Prozessor", "value": f"{hw['cpu_pct']} %",
                             "sub": f"{hw['cores']} Kerne", "percent": hw["cpu_pct"]})
        if lebendig and hw.get("ram_gb"):
            anzeigen.append({"name": "Arbeitsspeicher", "value": f"{hw['ram_used_gb']} GB",
                             "sub": f"von {hw['ram_gb']} GB", "percent": hw["ram_pct"]})
        if lebendig and hw.get("gpu"):
            anzeigen.append({"name": "Grafikkarte", "value": f"{hw['gpu_pct']} %",
                             "sub": f"{hw['gpu']} · {hw['vram_used_gb']} von "
                                    f"{hw['vram_gb']} GB", "percent": hw["gpu_pct"]})
        rolle = rollen.get(knoten, "")
        server.append({
            "name": str(mitglied.get("name") or knoten[:8])[:60],
            "self": knoten == verbund.node_id, "master": knoten == master,
            "alive": lebendig, "role": rolle, "role_label": ROLE_LABELS.get(rolle, ""),
            "accounts": sum(1 for n in list(verbund.homes.values()) if n == knoten),
            "gauges": anzeigen,
        })
    return server


def usage_view(settings: Settings) -> dict[str, Any]:
    """Der Verbrauch fuer den Browser: Prozent und Uhrzeiten, keine Tokenzahlen.

    Alles hier rechnet der Server -- die Oberflaeche zeichnet nur die Balken.
    """
    from datetime import datetime

    from aquaticy.quota import public

    jetzt = time.time()
    stand_um = "Stand: " + datetime.fromtimestamp(jetzt).strftime("%H:%M")
    kontingent = getattr(settings, "quota", None)
    if kontingent is None:
        return {"limited": False, "text": "Kein Limit", "summary": "Kein Limit",
                "updated_at": jetzt, "updated_text": stand_um}
    try:
        stand = public(kontingent.status(jetzt))
    except Exception:  # pragma: no cover
        return {"limited": True, "error": "Der Verbrauch ließ sich nicht lesen.",
                "summary": "nicht verfügbar", "updated_at": jetzt, "updated_text": stand_um}
    stand["updated_at"] = jetzt
    stand["updated_text"] = stand_um
    stand["summary"] = (f"Sitzung {stand['session']['percent']} % · "
                        f"Woche {stand['week']['percent']} %")
    stand["warning"] = _usage_warning(stand)
    return stand


def _usage_warning(stand: dict[str, Any]) -> str:
    """Ein Satz, sobald ein Limit knapp wird (ab 80 %) -- sonst leer."""
    from aquaticy.quota import when_phrase

    for key, name in (("week", "deines Wochenlimits"), ("session", "dieser Sitzung")):
        teil = stand.get(key) or {}
        prozent = int(teil.get("percent") or 0)
        wann = when_phrase(str(teil.get("resets_text") or ""))
        if teil.get("exhausted"):
            return f"Das Limit {name} ist erreicht — es setzt sich {wann} zurück."
        if prozent >= 80:
            return f"Du hast {prozent} % {name} genutzt — es setzt sich {wann} zurück."
    return ""


def account_quota(profile: Path, account: Account | None = None) -> Any:
    """Das Kontingent eines normalen Kontos (aquaticy/quota.py).

    Es liegt in der Kontendatenbank an der Kennung des Kontos. Nur ohne
    Kontenverwaltung (Tests, kaputter Start) landet es im Profilordner --
    ein normales Konto ohne Kontingent gibt es nicht.
    """
    from aquaticy.quota import Quota

    if AUTH is not None:
        konto = account or AUTH.account(profile.name)
        if konto is not None:
            return AUTH.quota(konto)
    erstellt = float(getattr(account, "created_at", 0.0) or 0.0)
    return Quota(profile / "quota.sqlite3", getattr(account, "id", "") or profile.name, erstellt)





_MEDIA_CACHE: OrderedDict[tuple[str, str], tuple[float, bytes, str]] = OrderedDict()
_MEDIA_LOCK = threading.Lock()
MEDIA_CACHE_TTL = 600.0
MEDIA_CACHE_BYTES = 48_000_000
_MEDIA_FETCHERS: dict[tuple[str, float, float], Any] = {}


def _media_fetcher(settings: Settings) -> Any:
    """Ein gemeinsamer Abrufer fuer Bilder -- mit gemeinsamer Drossel je Domain.

    Bis 9.5.15 baute jedes Bild einen eigenen, samt eigener Drossel: zwanzig
    Bilder einer Seite gingen dann gleichzeitig an denselben Server. Ohne
    Browser: ein Bild braucht keinen, und ein Bildaufruf darf auf dem Server
    kein Chromium starten.
    """
    from aquaticy.fetch import Fetcher

    schluessel = (settings.user_agent, float(settings.fetch_timeout),
                  float(settings.request_delay_seconds))
    with _MEDIA_LOCK:
        abrufer = _MEDIA_FETCHERS.get(schluessel)
        if abrufer is None:
            abrufer = Fetcher(user_agent=settings.user_agent, timeout=settings.fetch_timeout,
                              delay_seconds=settings.request_delay_seconds,
                              enable_browser=False)
            _MEDIA_FETCHERS[schluessel] = abrufer
        return abrufer


def media_by_url(settings: Settings, target: str) -> tuple[int, bytes, str]:
    """Holt ein oeffentliches Bild fuer die Oberflaeche. Returns: (Status, Inhalt, Typ).

    Seit 9.5.16 zaehlt der Abruf bei normalen Konten ins Kontingent wie jede
    andere Serverarbeit ("seite"); ein Bild aus dem Zwischenspeicher nicht.
    """
    from aquaticy import metering

    schluessel = (str(settings.data_dir), target)
    jetzt = time.monotonic()
    with _MEDIA_LOCK:
        treffer = _MEDIA_CACHE.get(schluessel)
        if treffer and jetzt - treffer[0] < MEDIA_CACHE_TTL:
            _MEDIA_CACHE.move_to_end(schluessel)
            return 200, treffer[1], treffer[2]
    try:
        vorab = metering.reserve_work(settings, "seite")
    except metering.QuotaExceeded as exc:
        return 429, str(exc).encode("utf-8"), "text/plain"
    try:
        visual, error = _media_fetcher(settings).load_public_visual(target)
    finally:
        vorab.cancel()
    if visual is None:
        return 404, (error or "Das Bild ist nicht erreichbar.").encode("utf-8"), "text/plain"
    metering.charge_work(settings, "seite")
    with _MEDIA_LOCK:
        _MEDIA_CACHE[schluessel] = (jetzt, visual.content, visual.content_type)
        while sum(len(e[1]) for e in _MEDIA_CACHE.values()) > MEDIA_CACHE_BYTES:
            _MEDIA_CACHE.popitem(last=False)
    return 200, visual.content, visual.content_type


def trusted_proxies() -> list[Any]:
    """Die Proxys, deren ``X-Forwarded-For`` gilt (``AQUATICY_TRUSTED_PROXIES``).

    Leer (Standard): keinem -- sonst koennte sich jeder mit einer Kopfzeile eine
    beliebige Adresse geben und damit Anfragegrenze und IP-Sperre umgehen.
    """
    import ipaddress

    netze = []
    for teil in os.environ.get("AQUATICY_TRUSTED_PROXIES", "").split(","):
        with contextlib.suppress(ValueError):
            if teil.strip():
                netze.append(ipaddress.ip_network(teil.strip(), strict=False))
    return netze


def client_ip(direkt: str, forwarded: str = "", real_ip: str = "") -> str:
    """Die Adresse des Menschen am anderen Ende.

    Hinter einem eingetragenen Proxy (``AQUATICY_TRUSTED_PROXIES``) die, die der
    Proxy meldet -- sonst teilten sich alle Nutzer dessen eine Adresse: eine
    Anfragegrenze fuer alle, und eine IP-Sperre traefe jeden (seit 9.5.16).
    Genommen wird der LETZTE Eintrag: den hat der eigene Proxy angehaengt, alle
    davor kann der Browser selbst mitgeschickt haben.
    """
    import ipaddress

    try:
        quelle = ipaddress.ip_address(direkt.split("%", 1)[0])
    except ValueError:
        return direkt
    if not any(quelle in netz for netz in trusted_proxies()):
        return direkt
    for kandidat in [*reversed(forwarded.split(",")), real_ip]:
        kandidat = kandidat.strip()
        with contextlib.suppress(ValueError):
            if kandidat:
                return str(ipaddress.ip_address(kandidat))
    return direkt




WORKSHOP_FIELDS: tuple[str, ...] = (
    "vm_size", "vm_image", "vm_idle_minutes", "vm_memory_mb", "vm_disk_gb", "vm_cpus",
    "vm_user_mode", "vm_internet", "vm_lan", "vm_desktop_image", "user_agent", "data_dir",
)


def workshop_changed(alt: Any, neu: Any) -> bool:
    """Braucht die virtual machine nach diesem Speichern einen Neuaufbau?"""
    return any(getattr(alt, feld, None) != getattr(neu, feld, None) for feld in WORKSHOP_FIELDS)


def delete_coworker(store: Any, nummer: int, settings: Settings) -> bool:
    """Loescht den Coworker samt exklusivem privaten Vergleichsbild."""
    cw = store.get(nummer)
    bild = str(cw.schedule.get("image_id") or "") if cw is not None else ""
    deleted = bool(store.delete(nummer))
    if deleted and bild and not any(c.schedule.get("image_id") == bild for c in store.all()):
        from aquaticy.media import delete_snapshot

        with contextlib.suppress(OSError, ValueError):
            delete_snapshot(settings.data_dir, bild)
    return deleted


def _chat_untrusted(entries: list[Any]) -> bool:
    """Stand in diesem Chat schon fremder Text (Webseite, Mail, Anhang)?

    Seit 9.5.16 am Verlauf vermerkt. Aeltere Eintraege tragen den Vermerk
    nicht -- dort gilt: wer Quellen gelesen hat, hatte fremden Text.
    """
    for entry in entries:
        meta = getattr(entry, "meta", None) or {}
        if meta.get("untrusted") or meta.get("sources") or meta.get("visuals"):
            return True
    return False


def _resume(agent: Any, session_id: str, entries: list[Any], untrusted: bool) -> None:
    """``agent.resume`` -- mit dem Vermerk "fremder Text", wo der Agent ihn kennt."""
    import inspect

    turns = [(entry.question, entry.answer) for entry in entries]
    try:
        kennt = "untrusted" in inspect.signature(agent.resume).parameters
    except (TypeError, ValueError):
        kennt = False
    if kennt:
        agent.resume(session_id, turns, untrusted=untrusted)
    else:
        agent.resume(session_id, turns)
        toolbox = getattr(agent, "toolbox", None)
        if toolbox is not None and untrusted:
            with contextlib.suppress(Exception):
                toolbox.untrusted_seen = True


    merken = getattr(agent, "remember_clarified", None)
    if callable(merken):
        for entry in entries:
            meta = getattr(entry, "meta", None) or {}
            if isinstance(meta.get("clarified"), list):
                merken(meta["clarified"])


def account_vault(profile: Path, account: Account | None = None) -> Any:
    """Der Schluesselbund eines Kontos (aquaticy/keyvault.py).

    Er liegt in der Kontendatenbank an der Kennung des Kontos. Nur ohne
    Kontenverwaltung (Tests, kaputter Start) im Profilordner.
    """
    from aquaticy.keyvault import KeyVault, load_secret

    if AUTH is not None:
        konto = account or AUTH.account(profile.name)
        if konto is not None:
            return AUTH.vault(konto)
    kennung = getattr(account, "id", "") or profile.name
    return KeyVault(profile / "keys.sqlite3", kennung, load_secret(profile / "vault.key"))


def _move_keys_into_vault(tresor: Any, env_path: Path | None, raw: dict[str, str]) -> None:
    """Schluessel aus der .env des Kontos (bis 9.5.14) wandern in den Schluesselbund.

    Danach stehen sie nicht mehr im Klartext in der Datei. Ein Schluessel, den
    der Schluesselbund schon hat, gewinnt -- er ist der neuere.
    """
    from aquaticy.keyvault import SLOT_BY_NAME, VaultError

    alte = {name: raw[name].strip() for name in SLOT_BY_NAME if raw.get(name, "").strip()}
    if not alte:
        return
    vorhanden = set(tresor.names())
    for name, wert in alte.items():
        if name not in vorhanden:
            with contextlib.suppress(VaultError):
                tresor.set(name, wert)
    if env_path is not None:
        remove_env_keys(env_path, set(alte))


def remove_env_keys(path: Path, names: set[str]) -> None:
    """Streicht Zeilen aus einer .env -- fuer Schluessel, die dort nicht mehr hingehoeren."""
    from aquaticy.memory import secure_file

    if not path.is_file() or not names:
        return
    zeilen = path.read_text(encoding="utf-8").splitlines()
    bleiben = [
        zeile for zeile in zeilen
        if zeile.strip().startswith("#") or "=" not in zeile
        or zeile.split("=", 1)[0].strip().removeprefix("export ").strip() not in names
    ]
    if bleiben != zeilen:
        path.write_text("\n".join(bleiben).rstrip("\n") + "\n", encoding="utf-8")
        secure_file(path)


def _profile_settings(profile: Path, plan: str, account: Account | None = None) -> Settings:
    """Kopiert die Servervorgaben und legt die Werte eines Kontos darueber."""
    base = get_settings()
    settings = replace(
        base,
        data_dir=profile,
        env_path=profile / ".env",
        api_keys=dict(base.api_keys),
        search_keys=dict(base.search_keys),
    )


    raw = read_env_file(settings.env_path)


    settings.ha_url = ""
    settings.ha_token = ""



    settings.legal_guard = True
    for key, attr in _STRING_SETTINGS.items():
        if key in raw:
            setattr(settings, attr, raw[key].strip())


    if settings.google_client_id != base.google_client_id:
        settings.google_client_secret = ""
    for key, attr in _BOOL_SETTINGS.items():
        if key in raw:
            setattr(settings, attr, raw[key].strip().lower() in {"1", "true", "yes", "on", "ja"})
    for key, attr in _INT_SETTINGS.items():
        if key in raw:
            with contextlib.suppress(ValueError):
                setattr(settings, attr, int(raw[key]))
    if "AQUATICY_LEGAL_GUARD" in raw:

        settings.legal_guard = guard_on(raw["AQUATICY_LEGAL_GUARD"])



    from aquaticy.keyvault import SEARCH_KEY_NAMES

    tresor = account_vault(profile, account)
    _move_keys_into_vault(tresor, settings.env_path, raw)
    eigene = tresor.keys()
    for name, wert in eigene.items():
        (settings.search_keys if name in SEARCH_KEY_NAMES else settings.api_keys)[name] = wert
    settings.own_key_names = frozenset(eigene)



    from aquaticy.addons import GITHUB_TOKEN_KEY

    settings.secret_vault = tresor
    altes = raw.get(GITHUB_TOKEN_KEY, "").strip()
    if altes:
        with contextlib.suppress(Exception):
            if not tresor.secret(GITHUB_TOKEN_KEY):
                tresor.set_secret(GITHUB_TOKEN_KEY, altes)
            if settings.env_path is not None:
                remove_env_keys(settings.env_path, {GITHUB_TOKEN_KEY})
    try:
        settings.github_token = tresor.secret(GITHUB_TOKEN_KEY)
    except Exception:
        settings.github_token = ""


    for name, attr in (("HA_TOKEN", "ha_token"), ("GOOGLE_CLIENT_SECRET", "google_client_secret")):
        with contextlib.suppress(Exception):
            alt = raw.get(name, "").strip()
            if alt:
                if not tresor.secret(name):
                    tresor.set_secret(name, alt)
                if settings.env_path is not None:
                    remove_env_keys(settings.env_path, {name})
            gespeichert = tresor.secret(name)
            if gespeichert:
                setattr(settings, attr, gespeichert)
    _bind_ha_token(settings, tresor)


    settings.account_email = str(getattr(account, "email", "") or "")
    settings.operator_search_backends = (
        None if plan == "ultra" else frozenset({(base.search_backend or "").lower()}))

    eigene_adresse = raw.get("AQUATICY_API_BASE", "").strip()
    settings.own_api_base = (
        eigene_adresse if plan == "ultra" and eigene_adresse
        and eigene_adresse != (base.api_base or "") else ""
    )


    settings.api_base_for = base.model
    if plan != "ultra":



        settings.lan_enabled = False
        settings.ha_url = ""
        settings.ha_token = ""
        settings.ha_control = False
        settings.ha_direct = False
        settings.storage_url = ""
        settings.storage_access = "off"
        settings.vm_size = "normal"
        settings.vm_cpus = 1
        settings.vm_memory_mb = 1024
        settings.vm_disk_gb = 4



        settings.legal_guard = True
        settings.vm_user_mode = False



        settings.vm_internet = False
        settings.vm_lan = False


        settings.quota = account_quota(profile, account)


        settings.api_base = base.api_base
        settings.searxng_url = base.searxng_url
        obergrenze = max(int(base.context_tokens or 0), NORMAL_CONTEXT_CAP)
        settings.context_tokens = min(int(settings.context_tokens or 0), obergrenze)
    else:
        settings.quota = None
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings


HELP_MARKDOWN = """### Befehle

- `/location <ort>` — Ortsfilter fuer diese Sitzung (leer = aufheben)
- `/model <name>` — Modell wechseln, z. B. `mistral/mistral-large-latest`
- `/max <frage>` — im Pro-Modus mit voller Mannschaft recherchieren
- `/image <pfad>` — Bild ansehen lassen und damit recherchieren (Datei oder Ordner)
- `/export html|md|csv` — die letzten Recherchen herunterladen
- `/history` — fruehere Recherchen
- `/notes` — Merkzettel (`/notes delete <nr>` loescht eine Notiz, `/notes clear` alle)
- `/clear` — Gespraechsverlauf verwerfen
- `/memory` — zeigen, was im Langzeitspeicher liegt
- `/uploads` — zeigen, was du hochgeladen hast
- `/uploads clear` — alle hochgeladenen Dateien loeschen
- `/forget` — den Langzeitspeicher leeren
- `/quit`, `/exit`, `/q` — im Browser das Fenster schliessen
- `/help` — diese Uebersicht
- `/<plugin>` — ein eingeschaltetes Plugin gezielt nutzen, z. B. `/code-review`,
  `/security-review`, `/github` oder `/wetter` (Add-ons → einschalten)

Dauerhaft aendern lassen sich Modell, Suche und Ort oben unter **Einstellungen**."""


class ChatSession:
    """Haelt einen Chat-Agenten und serialisiert die Anfragen dieses Chats."""




    ANSWER_TIMEOUT = 180.0

    def __init__(self, account: Account | None = None, profile: Path | None = None) -> None:
        self._lock = threading.Lock()


        self._agent_lock = threading.RLock()
        self._agent: Any = None
        self._settings: Settings | None = None
        self.account = account
        self.profile = profile
        self.runs = RunBook()


        self._answers: queue.Queue[str] = queue.Queue()




        self._frage_offen = False
        self._frage_lock = threading.Lock()


        self._reload_after = False

        self._reload_workshop = False

        self._reload_old: Settings | None = None


        self._carry_over = ""

        self._carry_untrusted = False

        self._owner = self
        self._chat_lock = threading.RLock()
        self._chat_sessions: dict[str, ChatSession] = {}
        self._qr_lock = threading.Lock()
        self._qr_state_lock = threading.Lock()
        self._qr_login: tuple[str, str, float] = ("", "", 0.0)
        self._selected = self

    def chat_sessions(self) -> list[ChatSession]:
        owner = self._owner
        with owner._chat_lock:
            return list({id(s): s for s in [owner, *owner._chat_sessions.values()]}.values())

    def has_running_chat(self) -> bool:
        book = self.runs if self.account is not None or self._owner._chat_sessions else RUNS
        run = book.latest()
        return self.busy() or (run is not None and not run.done)

    def forget_chat(self, chat_id: str) -> None:
        owner = self._owner
        with owner._chat_lock:
            for session in self.chat_sessions():
                if session.chat_id() != chat_id:
                    continue
                owner._chat_sessions.pop(chat_id, None)
                if session in (owner, owner._selected):
                    session.reset()
                    if session is not owner:
                        owner._chat_sessions[session.chat_id()] = session
                elif session._agent is not None:
                    session._agent.close()

    def resolve_chat(self, chat_id: str = "") -> ChatSession:
        owner = self._owner
        with owner._chat_lock:
            if not chat_id:
                return owner._selected
            for session in self.chat_sessions():
                if session.chat_id() == chat_id:
                    return session

            cache = Cache(self.settings().db_path, self.settings().cache_ttl_hours)
            entries = cache.chat_history(chat_id)
            if not entries:
                raise BadRequest("Diesen Chat gibt es nicht mehr.")
            return self._new_chat_session(chat_id, entries)

    def _new_chat_session(self, chat_id: str = "", entries: list[Any] | None = None
                          ) -> ChatSession:
        owner = self._owner
        with owner._chat_lock:

            for key, session in list(owner._chat_sessions.items()):
                if len(owner._chat_sessions) < 16:
                    break
                run = session.runs.latest()
                if session not in (owner, owner._selected) and not session.busy() and not (
                        run is not None and run.pinned):
                    owner._chat_sessions.pop(key)
                    if session._agent is not None:
                        session._agent.close()
            if len(owner._chat_sessions) >= 16:
                raise BadRequest("Zu viele offene Chats. Bitte laufende Antworten abwarten.")
            session = ChatSession(self.account, self.profile)
            session._owner = owner
            if chat_id:
                _resume(session.agent(), chat_id, entries or [], _chat_untrusted(entries or []))
            owner._chat_sessions[session.chat_id()] = session
            return session

    def switch_chat(self, chat_id: str = "") -> tuple[ChatSession, dict[str, Any]]:
        owner = self._owner
        with owner._chat_lock:
            current = owner._selected
            book = current.runs if current.account is not None or owner._chat_sessions else RUNS
            last = book.latest()
            if not owner._chat_sessions and not current.has_running_chat() and not (
                    last is not None and last.resumable):

                if chat_id:
                    data = current.open_chat(chat_id)
                else:
                    current.reset()
                    data = {}
                return current, data
            if current.account is None and current is owner and not owner._chat_sessions:
                current.runs = RUNS
            owner._chat_sessions[current.chat_id()] = current
            selected = self.resolve_chat(chat_id) if chat_id else self._new_chat_session()
            owner._selected = selected
            cache = Cache(selected.settings().db_path, selected.settings().cache_ttl_hours)
            entries = cache.chat_history(selected.chat_id())
            run = selected.runs.latest()
            if run is not None and run.resumable and entries and (
                    entries[-1].question == run.question and entries[-1].created_at >= run.started):
                entries = entries[:-1]
            return selected, {"turns": [
                {"question": e.question, "answer": e.answer,
                 "products": e.meta.get("products", []), "visuals": [
                     {**v, "captured_text": webview.iso_moment_text(v.get("captured_at"))}
                     if isinstance(v, dict) and v.get("captured_at") else v
                     for v in e.meta.get("visuals", []) or []]}
                for e in entries
            ]}

    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = (
                _profile_settings(self.profile, self.plan, self.account)
                if self.profile is not None
                else get_settings()
            )
            self._upgrade_gen = -1
        if UPGRADE_DIR is not None:

            from aquaticy import upgrading

            directory = UPGRADE_DIR

            def access(model: str) -> None:
                if not upgrading.allowed(directory, model, self.ultra):
                    raise ValueError("Diese Modellversion steht dir nicht mehr zur Wahl.")

            self._settings.model_access = access
            self._settings.model_context = lambda model: upgrading.model_context(
                directory, model, self.ultra)
            for field in ("model", "vision_model", "subagent_model", "code_model"):
                value = getattr(self._settings, field)
                if value and (field == "model" or not upgrading.allowed(
                        directory, value, self.ultra)):


                    with contextlib.suppress(upgrading.UpgradeError):
                        setattr(self._settings, field, upgrading.resolve(
                            directory, value, self.ultra,
                            getattr(self.account, "id", "") or ""))
        return self._settings

    @property
    def plan(self) -> str:

        return self.account.plan if self.account is not None else "ultra"

    @property
    def pro(self) -> bool:
        """Erhöhte Stufe -- Pro ODER Ultra (Nutzungsanzeige, Add-ons, Pro-Modus)."""
        return self.plan in ("pro", "ultra")

    @property
    def ultra(self) -> bool:
        """Die Vollstufe: alle Netz-Features und das Abschalten der Leitplanken."""
        return self.plan == "ultra"

    def agent(self) -> Any:
        from aquaticy.agent import Agent

        with self._agent_lock:
            if self._agent is None:
                settings = self.settings()
                cache = Cache(settings.db_path, settings.cache_ttl_hours)
                agent = Agent(settings, cache=cache)
                from aquaticy.learning import Learning

                agent.learning = Learning(settings.data_dir)


                if self._carry_over:
                    weiter, self._carry_over = self._carry_over, ""
                    vorher_fremd, self._carry_untrusted = self._carry_untrusted, False
                    with contextlib.suppress(Exception):
                        entries = cache.chat_history(weiter)
                        _resume(agent, weiter, entries, vorher_fremd or _chat_untrusted(entries))
                self._agent = agent
            return self._agent

    def reset(self) -> None:
        """Beginnt einen neuen Chat. Der Merkzettel bleibt."""
        with self._lock:
            self.agent().clear()
            self._forget_runs()

    def _forget_runs(self) -> None:
        """Ein neuer oder geoeffneter Chat darf keine alten Laufdaten liefern."""
        global RUNS

        self.runs = RunBook()
        if self.account is None and not self._owner._chat_sessions:
            RUNS = self.runs

    def chat_id(self) -> str:
        """Kennung des Chats, in dem gerade geschrieben wird."""
        return str(getattr(self.agent(), "session_id", ""))

    def open_chat(self, session_id: str) -> dict[str, Any]:
        """Oeffnet einen frueheren Chat wieder -- samt Verlauf.

        Der Verlauf geht an den Agenten zurueck, damit Nachfragen wie "und
        davon nur die guenstigen" auch nach Tagen noch funktionieren.
        """
        settings = self.settings()
        cache = Cache(settings.db_path, settings.cache_ttl_hours)
        entries = cache.chat_history(session_id)
        if not entries:
            return {"turns": [], "title": "", "note": "Diesen Chat gibt es nicht mehr."}
        with self._lock:
            _resume(self.agent(), session_id, entries, _chat_untrusted(entries))
            self._forget_runs()
        return {
            "session_id": session_id,
            "title": entries[0].question,
            "turns": [
                {
                    "question": entry.question,
                    "answer": entry.answer,
                    "products": entry.meta.get("products", []),
                    "visuals": [
                        {**v, "captured_text": webview.iso_moment_text(v.get("captured_at"))}
                        if isinstance(v, dict) and v.get("captured_at") else v
                        for v in entry.meta.get("visuals", []) or []
                    ],
                }
                for entry in entries
            ],
        }

    def reload(self, workshop: bool = False, *, _peers: bool = True) -> None:
        """Nach dem Speichern neuer Einstellungen alles neu aufbauen.

        Die virtual machine gehoert dazu, wenn sich an ihr etwas geaendert hat: haette
        jemand ihre Grenzen geaendert, arbeitete die laufende sonst noch mit den
        alten weiter. *workshop* erzwingt den Neuaufbau (Add-ons: die virtual machine
        muss ihre Datentraeger loslassen oder neu einhaengen).

        Der Chat bleibt derselbe. Wer waehrend eines Gespraechs das Modell
        wechselt, will ein anderes Modell -- nicht ein anderes Gespraech.
        """
        if _peers:
            from aquaticy.homeassistant import forget_states

            forget_states(self.profile or getattr(self._settings, "data_dir", None))
            for session in self.chat_sessions():
                if session is not self:
                    session.reload(workshop, _peers=False)
        if self.busy():



            if self._reload_old is None:
                self._reload_old = self._settings
            self._reload_workshop = self._reload_workshop or workshop
            self._reload_after = True
            self._settings = None
            if self.profile is None:
                reset_settings_cache()
            return
        with self._lock, self._agent_lock:
            old_settings = self._reload_old or self._settings
            workshop = workshop or self._reload_workshop
            self._reload_old, self._reload_workshop = None, False
            if self._agent is not None:
                self._carry_over = str(getattr(self._agent, "session_id", ""))


                self._carry_untrusted = bool(getattr(
                    getattr(self._agent, "toolbox", None), "untrusted_seen", False))
                with contextlib.suppress(Exception):
                    self._agent.close()
            self._agent = None
            self._settings = None
            if self.profile is None:
                reset_settings_cache()




            with contextlib.suppress(Exception):
                from aquaticy.sandbox import forget_shared

                if (workshop or old_settings is None
                        or workshop_changed(old_settings, self.settings())):
                    forget_shared(old_settings)

            self._settings = None

    def _settings_dirty(self) -> None:
        """Merkt vor, dass der Agent neu gebaut werden muss.

        Sofort neu bauen geht nicht: der laufende Durchlauf benutzt ihn
        gerade. Also erst, wenn er fertig ist.
        """
        self._reload_after = True

    def stop(self) -> bool:
        """Bricht den laufenden Durchlauf ab. `False` = es lief gerade keiner.

        Gelesen wird hier absichtlich OHNE die Sperre: `agent()` wuerde auf
        das Ende des laufenden Durchlaufs warten, und ein Abbruch, der auf
        das Ende wartet, waere keiner.

        Eine offene Rueckfrage wird gleich mit geschlossen -- sonst haengt der
        Durchlauf noch bis zum Zeitlimit an ihr fest, obwohl er enden soll.
        """
        agent = self._agent
        if agent is None or not self.busy():
            return False
        agent.cancel()
        self.answer("")
        return True

    def busy(self) -> bool:
        """Laeuft gerade eine Anfrage?"""
        if self._lock.acquire(blocking=False):
            self._lock.release()
            return False
        return True

    def ask(
        self,
        message: str,
        emit: Any,
        attachments: list[dict[str, Any]] | None = None,
        mode: str = "",
        structured: bool | None = None,
        recheck: bool | None = None,
        effort: str = "",
        online: bool | None = None,
        sandbox: bool | None = None,
        agents: int | None = None,
        visual_sources: bool | None = None,
    ) -> Any:
        """Fuehrt eine Anfrage aus und meldet jeden Zwischenschritt an *emit*.

        Das abschliessende "done" kommt vom Agenten selbst -- hier noch eines
        zu senden wuerde die Oberflaeche zweimal abschliessen lassen.
        """


        reload_after = False
        if self.busy():
            emit(
                "waiting",
                {
                    "reason": (
                        "Es läuft noch eine früher gestellte Anfrage — ich bin "
                        "gleich da."
                    ),
                    "reason_en": "An earlier question is still running — I'll be right there.",
                },
            )
        try:
            with self._lock:
                self._drain_answers()
                with self._frage_lock:
                    self._frage_offen = False
                agent = self.agent()
                previous_agent_limit = getattr(agent, "_agent_limit_override", None)
                try:
                    def melden(name: str, payload: dict[str, Any]) -> None:


                        if name == "ask":
                            with self._frage_lock:
                                self._frage_offen = True
                        emit(name, payload)

                    agent.on_event = melden
                    agent.toolbox.on_event = agent.on_event



                    agent.toolbox.on_settings_changed = self._settings_dirty
                    agent.set_ask_handler(self._ask_browser)
                    agent._agent_limit_override = agents


                    plugin = None
                    plugin_prompt = ""
                    if message.startswith("/") and not message.startswith("/image"):
                        from aquaticy import plugins as plugin_mod

                        plugin = plugin_mod.match(message, self.settings(), self.ultra)
                    if plugin is not None:
                        mode = plugin.mode or mode
                        structured, recheck = False, False

                        visual_sources = False
                        if plugin.online is not None:
                            online = plugin.online
                        if plugin.sandbox is not None:
                            sandbox = plugin.sandbox
                        context = ""
                        if attachments:
                            context = self.attachments_text(
                                agent, attachments, emit,
                                workshop=self._workshop_wanted(agent, mode, sandbox))
                            if context:
                                from aquaticy.injection import wrap_attachment

                                context = wrap_attachment(context)
                                if getattr(agent, "toolbox", None) is not None:
                                    agent.toolbox.untrusted_seen = True
                        auftrag = plugin.argument or plugin_mod.DEFAULT_QUESTIONS.get(
                            plugin.addon, "")
                        if not auftrag and not context:
                            raise plugin_mod.PluginError(plugin_mod.usage(plugin.addon))
                        plugin_prompt = plugin_mod.prompt(
                            plugin, "\n\n".join(t for t in (context, auftrag) if t),
                            self.settings(), self.ultra)

                        message = f"{context}\n\n{message}" if context else message
                    elif message.startswith("/image"):
                        message = self._image_question(agent, message)
                    elif attachments:
                        context = self.attachments_text(
                            agent, attachments, emit, workshop=self._workshop_wanted(
                                agent, mode, sandbox
                            )
                        )


                        if context:
                            from aquaticy.injection import wrap_attachment

                            context = wrap_attachment(context)
                        message = f"{context}\n\n{message}" if context else message


                        if context and getattr(agent, "toolbox", None) is not None:
                            agent.toolbox.untrusted_seen = True
                    ask_options = {
                        "stream": True, "mode": mode, "structured": structured,
                        "recheck": recheck, "effort": effort, "online": online,
                        "sandbox": sandbox,
                    }



                    from aquaticy.agent import Agent as BuiltinAgent
                    if isinstance(agent, BuiltinAgent):
                        ask_options["visual_sources"] = visual_sources
                        if plugin_prompt:
                            ask_options["plugin_prompt"] = plugin_prompt

                        with contextlib.suppress(Exception):
                            from aquaticy.uistate import UIState

                            agent.set_answer_language(
                                str(UIState(self.settings().db_path).read().get("lang", "de")))
                    return agent.ask(message, **ask_options)
                finally:
                    agent._agent_limit_override = previous_agent_limit
                    agent.on_event = None
                    agent.toolbox.on_event = None
                    agent.toolbox.on_settings_changed = None
                    if self._reload_after:
                        self._reload_after = False
                        reload_after = True


        finally:



            if reload_after or self._reload_after:
                self._reload_after = False
                self.reload()

    @staticmethod
    def _workshop_wanted(agent: Any, mode: str, sandbox: bool | None) -> bool:
        """Ob dieser Turn in der virtual machine landet -- vor `agent.ask`.

        Die Anhaenge werden verarbeitet, bevor der Agent den Modus dieses
        Turns kennt. Wer stattdessen `agent.workshop_on` fragt, bekommt den
        Stand der VORIGEN Frage -- und legt die Datei in die falsche Welt
        oder gar nicht ab.
        """
        from aquaticy.agent import clean_mode

        an = getattr(agent, "sandbox", False) if sandbox is None else bool(sandbox)
        welcher = clean_mode(mode) if mode else getattr(agent, "mode", "normal")
        return bool(an) and welcher == "code"

    def _ask_browser(self, question: str, options: list[str]) -> str:
        """Wartet auf die Antwort aus dem Browser.

        Das "ask"-Ereignis ist schon raus, wenn wir hier ankommen -- die
        Oberflaeche zeigt die Frage also bereits an. Bleibt die Antwort aus,
        geben wir auf: das Modell trifft dann eine Annahme und macht weiter.
        Aufgeraeumt wird zu Beginn der Anfrage, nicht hier -- sonst koennte
        eine sehr schnelle Antwort dem eigenen Aufraeumen zum Opfer fallen.
        """
        with self._frage_lock:
            self._frage_offen = True
        try:
            return self._answers.get(timeout=self.ANSWER_TIMEOUT)
        except queue.Empty:
            return ""
        finally:

            with self._frage_lock:
                self._frage_offen = False

    def _drain_answers(self) -> None:
        """Antworten aus einer frueheren Runde wegwerfen."""
        while True:
            try:
                self._answers.get_nowait()
            except queue.Empty:
                return

    def answer(self, text: str) -> bool:
        """Nimmt die Antwort aus dem Browser entgegen. `False` = niemand wartet.

        Genau eine Antwort je offener Frage: die zweite (doppelt geklickt) oder eine
        nach dem Aufgeben kommt nicht in die Schlange und beantwortet nichts.
        """
        with self._frage_lock:
            if not self.busy() or not self._frage_offen:
                return False
            self._frage_offen = False
            self._answers.put(text)
        return True

    def attachments_text(
        self,
        agent: Any,
        attachments: list[dict[str, Any]],
        emit: Any,
        *,
        workshop: bool = False,
    ) -> str:
        """Macht aus hochgeladenen Dateien Text, den das Modell lesen kann.

        Bilder gehen ans Vision-Modell, PDFs durch pypdf, Textdateien direkt.
        Eine Datei, die nicht lesbar ist, beendet nicht die ganze Anfrage --
        sie wird benannt und uebersprungen, wie eine unlesbare Webseite auch.
        """
        blocks: list[str] = []
        for item in attachments[:MAX_UPLOADS]:
            if blocked_upload(str(item.get("name") or "")):
                blocks.append(f"[Anhang {safe_name(str(item.get('name') or 'datei'))}: "
                              "PHP- und JSP-Dateien werden nicht angenommen]")
                continue
            name = safe_name(str(item.get("name") or "datei"))
            try:
                data = base64.b64decode(str(item.get("data") or ""), validate=True)
            except (ValueError, binascii.Error):
                blocks.append(f"[Anhang {name}: konnte nicht gelesen werden]")
                continue
            if not data:
                blocks.append(f"[Anhang {name}: leer]")
                continue
            if len(data) > MAX_UPLOAD_BYTES:
                blocks.append(
                    f"[Anhang {name}: zu gross "
                    f"({len(data) // 1_000_000} MB, erlaubt sind "
                    f"{MAX_UPLOAD_BYTES // 1_000_000} MB)]"
                )
                continue
            emit("upload", {"name": name, "bytes": len(data)})
            block = self._one_attachment(agent, name, data)




            gelegt = self._into_workshop(name, data) if workshop else ""
            if gelegt:
                block += f"\n[Liegt in der virtual machine unter {gelegt}]"
            blocks.append(block)
        return "\n\n".join(blocks)

    def _into_workshop(self, name: str, data: bytes) -> str:
        """Legt einen Anhang in die virtual machine.

        Returns: der Pfad drinnen, oder "" wenn das Hineinlegen nicht
        geklappt hat. Ein Fehlschlag hier darf die Anfrage nicht abbrechen:
        der Text der Datei steht ja trotzdem da.
        """
        from aquaticy.sandbox import MAX_FILE_BYTES

        if len(data) > MAX_FILE_BYTES:
            return ""

        schlicht = "".join(
            zeichen if zeichen.isascii() and (zeichen.isalnum() or zeichen in "-_.") else "_"
            for zeichen in name
        ).strip("._") or "datei"
        from aquaticy import metering
        from aquaticy import sandbox as werkstatt

        try:

            metering.check_work(self.settings(), "datei")
            antwort = werkstatt.shared(self.settings()).put_bytes(f"eingang/{schlicht}", data)
            if isinstance(antwort, dict) and antwort.get("written"):
                metering.charge_work(self.settings(), "datei")
                return str(antwort["written"])
        except metering.QuotaExceeded:
            return ""
        except Exception:


            logging.getLogger("aquaticy.web").warning(
                "Anhang nicht in die virtual machine gelegt", exc_info=True)
        return ""

    def _one_attachment(self, agent: Any, name: str, data: bytes) -> str:
        """Liest eine einzelne Datei aus -- je nach Art auf ihrem eigenen Weg."""
        suffix = Path(name).suffix.lower()



        limit = min(MAX_FILE_CHARS, agent.blob_limit()) if hasattr(agent, "blob_limit") else (
            MAX_FILE_CHARS
        )

        if suffix in IMAGE_TYPES:
            if not looks_like_image(data):

                return f"[Bild {name}: keine gültige Bilddatei – nicht angenommen]"
            try:
                path = self._store(name, data)
            except OSError as exc:
                return f"[Bild {name}: nicht abgelegt – {exc}]"
            try:
                description = agent.describe_image(path)
            except Exception as exc:
                return f"[Bild {name}: konnte nicht angesehen werden – {exc}]"
            return f"[Bild {name}] Darauf ist zu sehen:\n{description}"

        if suffix == ".pdf":
            from aquaticy.fetch import extract_pdf_text

            text, title = extract_pdf_text(data)
            if not text:
                return (
                    f"[PDF {name}: kein Text enthalten – vermutlich ein Scan. "
                    "Gescannte Seiten kann Aquaticy AI nicht lesen.]"
                )
            head = f"[PDF {name}" + (f", Titel: {title}" if title else "") + "]"
            return f"{head}\n{text[:limit]}"

        try:
            text = data.decode("utf-8").strip()
        except UnicodeDecodeError:
            return f"[Anhang {name}: kein Text und kein bekanntes Bildformat]"
        if not text:
            return f"[Anhang {name}: leer]"
        return f"[Datei {name}]\n{text[:limit]}"

    def _store(self, name: str, data: bytes) -> Path:
        """Legt eine hochgeladene Datei ab -- das Vision-Modell braucht einen Pfad."""
        from aquaticy.budget import ensure_room, forget

        folder = self.settings().data_dir / "uploads"
        folder.mkdir(parents=True, exist_ok=True)

        ensure_room(self.settings().data_dir, len(data))
        target = folder / f"{int(time.time() * 1000)}-{name}"

        from aquaticy.privacy import write_private

        write_private(target, data, self.settings().data_dir)
        forget(self.settings().data_dir)
        _prune_uploads(folder)
        return target

    def _image_question(self, agent: Any, line: str) -> str:
        """Macht aus `/image <pfad>` eine Frage, die das Bild beschreibt."""
        from aquaticy.cli import IMAGE_SUFFIXES

        argument = line[len("/image") :].strip()
        if not argument:
            raise ValueError("Nutzung: /image pfad/zum/bild.jpg (oder ein Ordner)")
        target = Path(argument)
        if self.account is not None:




            uploads = (self.settings().data_dir / "uploads").resolve()
            target = (uploads / target).resolve()
            if not target.is_relative_to(uploads):
                raise PermissionError(
                    "Im Browser geht /image nur mit deinen eigenen hochgeladenen "
                    "Bildern – häng das Bild einfach an die Nachricht an."
                )
        else:
            target = target.expanduser()
        image = resolve_image(target)
        if image.suffix.lower() not in IMAGE_SUFFIXES:

            raise ValueError(
                f"{image.name} ist kein Bild ({', '.join(IMAGE_SUFFIXES)})."
            )
        description = agent.describe_image(image)
        return (
            f"Auf dem Bild ({image.name}) ist Folgendes zu sehen:\n{description}\n\n"
            "Recherchiere dazu und sag mir, worum es sich handelt."
        )

    def command(self, line: str) -> dict[str, Any]:
        """Fuehrt einen Slash-Befehl aus -- dieselben wie im Terminal.

        `/image` gehoert nicht hierher: das recherchiert und laeuft deshalb
        ueber den normalen Chat-Weg mit Live-Anzeige.
        """
        from aquaticy.config import model_problem

        command, _, argument = line[1:].partition(" ")
        command = command.lower().strip()
        argument = argument.strip()

        with self._lock:
            if command == "help":
                return {"text": HELP_MARKDOWN + self._plugin_help()}


            from aquaticy import plugins as plugin_mod

            plugin = plugin_mod.match(line, self.settings(), self.ultra)
            if plugin is not None:
                return {"text": plugin_mod.usage(plugin.addon)}

            if command == "max":



                return {
                    "text": (
                        "**/max** stellt im **Pro-Modus** die volle Mannschaft auf: "
                        "alle Agenten, die beiden starken dazu und – wenn "
                        "*Gegenprüfen* an ist – die vier Prüfer.\n\n"
                        "Schreib die Frage dahinter:\n\n"
                        "`/max Welche Fahrradläden in Bremen reparieren Lastenräder?`\n\n"
                        "Ohne den Befehl entscheidet der Master selbst, wie viele "
                        "Agenten die Frage braucht."
                    )
                }

            if command == "location":
                self.agent().set_location(argument)
                return {
                    "text": f"Ortsfilter: **{argument}**" if argument
                    else "Ortsfilter aufgehoben.",
                    "reload": True,
                }

            if command == "model":
                settings = self.settings()
                if not argument:
                    return {"text": f"Aktuelles Modell: **{settings.model}**"}
                problem = model_problem(argument, settings.route(argument)[0])
                if problem:
                    return {"text": f"{problem}\n\nWeiter mit `{settings.model}`."}
                self.agent().set_model(argument)
                return {"text": f"Modell: **{argument}**", "reload": True}

            if command == "clear":
                if self._agent is not None:
                    self._agent.clear()
                self._forget_runs()
                return {"text": "Verlauf verworfen.", "clear": True}

            if command == "memory":
                return {"text": self._memory_overview()}

            if command == "forget":
                return {"text": self._forget()}

            if command == "uploads":
                return {"text": self._uploads(argument)}

            if command == "notes":
                return {"text": self._notes(argument)}

            if command == "history":
                entries = self._cache().recent_history(limit=15)
                if not entries:
                    return {"text": "Noch keine Recherchen im Verlauf."}
                lines = "\n".join(f"- {entry.question}" for entry in entries)
                return {"text": f"### Früher gefragt\n{lines}"}

            if command == "export":
                return self._export(argument or "html")

            if command in ("quit", "exit", "q"):
                return {"text": "Im Browser reicht es, das Fenster zu schliessen."}

        return {"text": f"Unbekannter Befehl `/{command}` — `/help` zeigt alle."}

    def _plugin_help(self) -> str:
        """Die eingeschalteten Plugins dieses Kontos fuer ``/help``."""
        from aquaticy import plugins as plugin_mod

        try:
            liste = plugin_mod.commands(self.settings(), self.ultra)
        except Exception:
            return ""
        if not liste:
            return ("\n\n### Plugins\nNoch keins eingeschaltet — unter **Add-ons** gibt "
                    "es zum Beispiel Code-Review und Security-Review.")
        zeilen = "\n".join(f"- `/{eintrag['name']}` — {eintrag['label']}" for eintrag in liste)
        return f"\n\n### Deine Plugins\n{zeilen}"

    def _notes(self, argument: str) -> str:
        """``/notes`` zeigt den Merkzettel, ``/notes delete 3`` und ``/notes clear`` raeumen auf.

        Bis 9.5.15 ging Loeschen nur in der Kommandozeile -- im Browser stand
        eine Notiz fuer immer im Systemtext jeder Frage.
        """
        cache = self._cache()
        wort, _, rest = argument.partition(" ")
        wort = wort.lower()
        if wort in ("clear", "leeren", "alle"):
            return f"{cache.clear_notes()} Notizen gelöscht. Der Merkzettel ist leer."
        if wort in ("delete", "del", "löschen", "loeschen", "weg"):
            nummer = rest.strip().lstrip("#")
            if not nummer.isdigit():
                return ("Welche Notiz? Zum Beispiel `/notes delete 3` – die Nummer steht "
                        "bei `/notes`.")
            return (f"Notiz {nummer} gelöscht." if cache.delete_note(int(nummer))
                    else f"Eine Notiz mit der Nummer {nummer} gibt es nicht.")
        notes = cache.list_notes()
        if not notes:
            return "Der Merkzettel ist leer. Sag im Chat einfach *merk dir …*"
        lines = "\n".join(f"- **{note.id}** · {note.text}" for note in notes)
        return (f"### Merkzettel\n{lines}\n\nLöschen: `/notes delete <Nummer>` · "
                "alles: `/notes clear`")

    def memory(self) -> Any:
        """Den Langzeitspeicher oeffnen.

        Nicht `_store` nennen: so heisst schon die Ablage fuer hochgeladene
        Dateien, und die haette diese Methode ueberschrieben.
        """
        from aquaticy.memory import Memory

        settings = self.settings()
        return Memory(settings.db_path, settings.data_dir, settings.memory_key)

    def _memory_overview(self) -> str:
        """Was liegt im Speicher, und wie voll ist er?"""
        from aquaticy.memory import human_size

        settings = self.settings()
        if not settings.memory_enabled:
            return (
                "Der Speicher ist ausgeschaltet. Unter **Einstellungen → Speicher** "
                "lässt er sich wieder einschalten."
            )
        store = self.memory()
        usage = store.usage()
        entries = store.all_entries(limit=30)
        head = (
            f"### Speicher\n{usage['entries']} Notizen · "
            f"{usage['used_mb']} von {usage['limit_mb']} MB belegt "
            f"({usage['percent']} %), davon {human_size(int(usage['uploads']))} Dateien."
        )
        if not entries:
            return f"{head}\n\nNoch nichts abgelegt."
        lines = "\n".join(
            f"- **{entry.topic or 'Notiz'}** — {entry.text}" for entry in entries
        )
        return f"{head}\n\n{lines}"

    def _forget(self) -> str:
        """Den Speicher leeren."""
        if not self.settings().memory_enabled:
            return "Der Speicher ist ausgeschaltet – da ist nichts zu löschen."
        count = self.memory().clear()
        if not count:
            return "Der Speicher war schon leer."
        return f"{count} Notizen gelöscht. Hochgeladene Dateien bleiben – `/uploads clear`."

    def _uploads(self, argument: str) -> str:
        """Hochgeladenes zeigen oder loeschen."""
        from aquaticy.memory import human_size

        store = self.memory()
        if argument.strip().lower() in ("clear", "loeschen", "löschen", "weg"):
            count, freed = store.clear_uploads()
            if not count:
                return "Es liegt nichts Hochgeladenes herum."
            word = "Datei" if count == 1 else "Dateien"
            return f"{count} {word} gelöscht, {human_size(freed)} wieder frei."

        folder = self.settings().data_dir / "uploads"
        files = sorted(folder.iterdir()) if folder.is_dir() else []
        files = [item for item in files if item.is_file()]
        if not files:
            return "Es liegt nichts Hochgeladenes herum."
        lines = "\n".join(

            f"- {item.name.split('-', 1)[-1]} ({human_size(item.stat().st_size)})"
            for item in files[-30:]
        )
        total = human_size(sum(item.stat().st_size for item in files))
        return (
            f"### Hochgeladen\n{len(files)} {'Datei' if len(files) == 1 else 'Dateien'}, "
            f"zusammen {total}.\n\n{lines}"
            "\n\nAlles löschen: `/uploads clear`"
        )

    def _cache(self) -> Cache:
        settings = self.settings()
        return Cache(settings.db_path, settings.cache_ttl_hours)

    def _export(self, fmt: str) -> dict[str, Any]:
        """Exportiert die letzten Recherchen -- wie `aquaticy export`.

        Die Datei geht als Download an den Browser. Bis 9.5.12 landete sie im
        Arbeitsordner des Servers: wer von einem anderen Geraet kam, bekam
        nur einen Pfad, mit dem er nichts anfangen konnte -- und jedes Konto
        konnte dort beliebig viele Dateien anlegen. Nur ohne Konten (lokal,
        ein Nutzer) bleibt zusaetzlich eine Kopie in ``./exports`` liegen,
        wie im Terminal.
        """
        import tempfile

        from aquaticy.export import Turn, export

        entries = self._cache().recent_history(limit=5)
        if not entries:
            return {"text": "Noch nichts zu exportieren — stell erst eine Frage."}
        turns = [
            Turn(
                question=entry.question,
                answer=entry.answer,
                sources=entry.meta.get("sources", []),
                searches=entry.meta.get("searches", []),
                skipped=entry.meta.get("skipped", {}),
            )
            for entry in entries
        ]
        try:
            with tempfile.TemporaryDirectory(prefix="aquaticy-export-") as ordner:
                path = export(turns, fmt, directory=Path(ordner))
                inhalt = path.read_text(encoding="utf-8")
                name = path.name
        except ValueError as exc:
            return {"text": str(exc)}
        except OSError as exc:
            return {"text": f"Der Export ist fehlgeschlagen: {type(exc).__name__}"}
        mime = {
            "html": "text/html;charset=utf-8",
            "md": "text/markdown;charset=utf-8",
            "csv": "text/csv;charset=utf-8",
        }[path.suffix.lstrip(".")]
        text = f"Export fertig: **{name}** — der Download startet."
        if self.account is None:
            with contextlib.suppress(OSError):
                ziel = Path.cwd() / name
                ziel.write_text(inhalt, encoding="utf-8")
                text += f"\n\nEine Kopie liegt in `{ziel}`."
        return {"text": text, "download": {"name": name, "mime": mime, "content": inhalt}}


def resolve_image(target: Path) -> Path:
    """Datei oder Ordner zu genau einem Bild aufloesen.

    Im Terminal fragt aquaticy bei mehreren Bildern nach; hier nimmt er das
    neueste und sagt es dazu -- eine Rueckfrage mitten im Stream waere
    umstaendlicher als ein zweiter `/image`-Aufruf mit genauem Pfad.
    """
    from aquaticy.cli import IMAGE_SUFFIXES, _images_in

    if target.is_file():
        return target
    if target.is_dir():
        images = _images_in(target)
        if not images:
            raise FileNotFoundError(
                f"Keine Bilder in {target}. Gesucht wurde nach: {', '.join(IMAGE_SUFFIXES)}"
            )
        return images[0]
    raise FileNotFoundError(f"Nicht gefunden: {target}")


DEFAULT_SESSION = ChatSession()
_REQUEST = threading.local()


class SessionRegistry:
    """Eine unabhaengige ChatSession je Konto."""

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._lock = threading.Lock()

    def get(self, account: Account) -> ChatSession:
        with self._lock:
            session = self._sessions.get(account.id)
            if session is None:
                if AUTH is None:  # pragma: no cover
                    return DEFAULT_SESSION
                session = ChatSession(account, AUTH.profile_dir(account.id))
                self._sessions[account.id] = session
            return session

    def drop(self, account_id: str) -> ChatSession | None:
        """Vergisst die Sitzung eines Kontos (Daten oder Konto geloescht, 9.5.32)."""
        with self._lock:
            return self._sessions.pop(str(account_id), None)


SESSIONS = SessionRegistry()

USER_COWORKERS: dict[str, Any] = {}

USER_BRIDGES: dict[str, Any] = {}

BRIDGE_RUNNER: Any = None



_SCHEDULER_LOCK = threading.Lock()


class SessionProxy:
    """Haelt den bestehenden Code lesbar und waehlt pro Anfrage das Konto."""

    @staticmethod
    def current() -> ChatSession:
        return getattr(_REQUEST, "session", DEFAULT_SESSION)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.current(), name)


SESSION = SessionProxy()


def current_runs() -> RunBook:
    session = SESSION.current() if isinstance(SESSION, SessionProxy) else SESSION
    return session.runs if session.account is not None or session._owner._chat_sessions else RUNS


def previous_user_message(session: Any) -> str:
    """Die letzte Frage des Nutzers im laufenden Chat -- "" wenn keine.

    Fuer Ai-guard (9.5.28): ein Zitat in der Nachricht davor und der Auftrag
    in dieser gehoeren zusammen.
    """
    from aquaticy.agent import own_words

    agent = getattr(session, "_agent", None)
    for eintrag in reversed(list(getattr(agent, "messages", None) or [])):
        if isinstance(eintrag, dict) and eintrag.get("role") == "user":
            if not isinstance(eintrag.get("content"), str):
                return ""

            inhalt = own_words(eintrag.get("content"))
            if inhalt:
                return inhalt[:2000]
    return ""


def job_abuse(account: Any, job: Any, payload: dict[str, Any]) -> None:
    """Missbrauch in einem Auftrag -> Ai-guard, wie im Chat (9.5.26)."""
    if AIGUARD is None or account is None:
        return
    AIGUARD.record_incident(
        str(account.id), str(payload.get("art") or ""), payload.get("schwere") or 0,
        chat=f"auftrag:{getattr(job, 'id', '')}", detail=str(payload.get("art") or ""),
        enforce=not getattr(account, "ultra", False), text=str(getattr(job, "question", "")))


def coworker_abuse(account: Any, kollege: Any, payload: dict[str, Any]) -> None:
    """Missbrauch in einem Coworker -> Ai-guard, wie bei Auftraegen (11.0.0 Luna)."""
    if AIGUARD is None or account is None:
        return
    AIGUARD.record_incident(
        str(account.id), str(payload.get("art") or ""), payload.get("schwere") or 0,
        chat=f"coworker:{getattr(kollege, 'id', '')}", detail=str(payload.get("art") or ""),
        enforce=not getattr(account, "ultra", False), text=str(getattr(kollege, "goal", "")))


def _plan_of(konto_id: str, fallback: Any) -> str:
    """Die Stufe, wie sie JETZT ist -- ein herabgestuftes Konto laesst Coworker ruhen."""
    if AUTH is not None:
        with contextlib.suppress(Exception):
            frisch = AUTH.account(konto_id)
            return frisch.plan if frisch is not None else ""
    return str(getattr(fallback, "plan", "") or "")


def start_user_scheduler(account: Account) -> None:
    """Startet genau einen Coworker-Taktgeber fuer alle Aufgaben des Kontos."""
    from aquaticy import coworker as coworker_mod

    with _SCHEDULER_LOCK:


        konto_id = account.id

        def ruht() -> bool:


            return (AIGUARD is not None
                    and AIGUARD.is_banned(user_id=konto_id) is not None) or (
                CLUSTER is not None and not CLUSTER.is_home(konto_id))

        if account.id not in USER_COWORKERS:


            kollegen = coworker_mod.Scheduler(
                SESSIONS.get(account).settings,
                plan=lambda: _plan_of(konto_id, account),
                paused=ruht,
                on_abuse=lambda kollege, payload: coworker_abuse(account, kollege, payload),
            )
            kollegen.start()
            USER_COWORKERS[account.id] = kollegen
    start_user_bridge(account)


def bridge_abuse(account: Any, payload: dict[str, Any]) -> None:
    """Missbrauch in der Messenger-Bruecke -> Ai-guard, wie bei Auftraegen (12.6.6 Luna).

    Die Bruecke meldet nur, was der Besitzer oder eine seiner Nummern geschrieben hat.
    """
    if AIGUARD is None or account is None:
        return
    AIGUARD.record_incident(
        str(account.id), str(payload.get("art") or ""), payload.get("schwere") or 0,
        chat="messenger", detail=str(payload.get("art") or ""),
        enforce=not getattr(account, "ultra", False), text="")


def _build_bridge_runner(get_session: Callable[[], Any], account: Any) -> Any:
    """Der Hintergrundlauf der Messenger-Bruecke fuer ein Konto (oder den eigenen Rechner)."""
    from aquaticy import bridge as bridge_mod
    from aquaticy import sandbox as werkstatt
    from aquaticy.desktop import Desktop

    def einstellungen() -> Settings:
        return get_session().settings()

    def ruht() -> bool:



        if account is not None:
            if _plan_of(account.id, account) != "ultra":
                return True
            if AIGUARD is not None and AIGUARD.is_banned(user_id=account.id) is not None:
                return True
            if CLUSTER is not None and not CLUSTER.is_home(account.id):
                return True
        session = get_session()
        owner = getattr(session, "_owner", session)
        return bool(workshop_busy(session)
                    or getattr(owner, "_qr_login", ("", "", 0.0))[2] > time.monotonic())

    def treiber(messenger: str) -> Any:
        settings = einstellungen()
        return bridge_mod.VisionDriver(Desktop(werkstatt.shared(settings), settings), messenger)

    antworter = bridge_mod.AgentAnswerer(
        einstellungen, on_abuse=lambda payload: bridge_abuse(account, payload))
    runner = bridge_mod.Runner(
        bridge_mod.Bridge(einstellungen, treiber, antworter, paused=ruht), einstellungen)
    runner.answerer = antworter  # type: ignore[attr-defined]
    return runner


def start_user_bridge(account: Account) -> None:
    """Startet die Messenger-Bruecke des Kontos -- aber nur, wenn eine eingeschaltet ist.

    Die Pruefung liest nur die Datei im Profilordner: Die Einstellungen des Kontos werden
    erst geladen, wenn sie gebraucht werden (nicht schon bei der Anmeldung).
    """
    from aquaticy import bridge as bridge_mod

    if AUTH is None:
        return
    with contextlib.suppress(Exception):
        if not bridge_mod.enabled_in(AUTH.profile_dir(account.id)):
            return
        with _SCHEDULER_LOCK:
            runner = USER_BRIDGES.get(account.id)
            if runner is None:
                runner = _build_bridge_runner(lambda: SESSIONS.get(account), account)
                USER_BRIDGES[account.id] = runner
        runner.ensure_running()


def _bridge_runner(session: Any) -> Any:
    """Der Hintergrundlauf der Bruecke fuer die Sitzung -- gebaut beim ersten Bedarf."""
    global BRIDGE_RUNNER
    konto = getattr(session, "account", None)
    if konto is not None:
        with _SCHEDULER_LOCK:
            if konto.id not in USER_BRIDGES:
                USER_BRIDGES[konto.id] = _build_bridge_runner(
                    lambda: SESSIONS.get(konto), konto)
            return USER_BRIDGES[konto.id]
    with _SCHEDULER_LOCK:
        if BRIDGE_RUNNER is None:
            BRIDGE_RUNNER = _build_bridge_runner(lambda: DEFAULT_SESSION, None)
        return BRIDGE_RUNNER


def _stop_bridge(runner: Any) -> None:
    with contextlib.suppress(Exception):
        runner.stop()
        runner.wait_stopped()
    with contextlib.suppress(Exception):
        runner.answerer.close()


def _bind_ha_token(settings: Settings, tresor: Any) -> None:
    """Der Home-Assistant-Token eines Kontos gilt nur fuer seine Adresse (9.6.9 Luna).

    Beim Speichern steht die Adresse mit im Schluesselbund (HA_TOKEN_URL).
    Zeigt die Einstellung danach woanders hin, wird der Token nicht benutzt --
    fuer die neue Adresse traegt man ihn neu ein. Ein Token aus der Zeit vor
    der Bindung wird einmal an die Adresse gebunden, die gerade gilt.
    """
    from aquaticy.homeassistant import normalize_url

    if not settings.ha_token:
        return
    with contextlib.suppress(Exception):
        gebunden = tresor.secret("HA_TOKEN_URL")
        jetzt = normalize_url(settings.ha_url)
        if not gebunden and jetzt:
            tresor.set_secret("HA_TOKEN_URL", jetzt)
            return
        if gebunden and gebunden == jetzt:
            return
    settings.ha_token = ""


def _stop_schedulers() -> None:
    """Haelt alle Planer an -- beim Beenden und vor einem Neustart (9.6.8 Ultra)."""
    global COWORKER_SCHEDULER, BRIDGE_RUNNER
    with _SCHEDULER_LOCK:
        planer = list(USER_COWORKERS.values())
        USER_COWORKERS.clear()
        bruecken = list(USER_BRIDGES.values())
        USER_BRIDGES.clear()
        if BRIDGE_RUNNER is not None:
            bruecken.append(BRIDGE_RUNNER)
        BRIDGE_RUNNER = None
    for global_planer in (COWORKER_SCHEDULER,):
        if global_planer is not None:
            planer.append(global_planer)
    COWORKER_SCHEDULER = None
    for eins in planer:
        with contextlib.suppress(Exception):
            eins.stop()
    for bruecke in bruecken:
        _stop_bridge(bruecke)
    with contextlib.suppress(Exception):
        from aquaticy import coworker as coworker_mod

        coworker_mod.stop_boxes()


def forget_account_runtime(account: Account) -> None:
    """Haelt alles an, was fuer ein Konto laeuft: Auftraege, virtual machine, Sitzung.

    Vor dem Loeschen der Daten oder des Kontos (9.5.32) -- sonst schriebe ein
    laufender Auftrag gleich wieder in den frisch geleerten Ordner.
    """
    with _SCHEDULER_LOCK:
        planer = [USER_COWORKERS.pop(account.id, None)]
        bruecke = USER_BRIDGES.pop(account.id, None)
    for eins in planer:
        if eins is not None:
            with contextlib.suppress(Exception):
                eins.stop()
                if hasattr(eins, "wait_stopped"):
                    eins.wait_stopped()
    if bruecke is not None:
        _stop_bridge(bruecke)
    sitzung = SESSIONS.drop(account.id)


    with contextlib.suppress(Exception):
        from aquaticy import coworker as coworker_mod

        gebaut = getattr(sitzung, "_settings", None) if sitzung is not None else None
        ordner = gebaut.data_dir if gebaut is not None else (
            AUTH.profile_dir(account.id) if AUTH is not None else None)
        if ordner is not None:
            coworker_mod.stop_boxes(ordner)
    if sitzung is not None:


        chats = sitzung.chat_sessions()
        for chat in chats:
            with contextlib.suppress(Exception):
                chat.stop()
        for chat in chats:
            if chat._lock.acquire(timeout=60):
                chat._lock.release()
            with contextlib.suppress(Exception):
                if chat._agent is not None:
                    chat._agent.close()
        with contextlib.suppress(Exception):
            from aquaticy import sandbox as werkstatt

            werkstatt.forget_shared(sitzung.settings())


def ui_state() -> Any:
    """Der Zustand der Oberflaeche -- er liegt beim Server, nicht im Browser."""
    from aquaticy.uistate import UIState

    return UIState(SESSION.settings().db_path)




COWORKER_SCHEDULER: Any = None



OWN_MODEL_FIELDS = (
    ("AQUATICY_MODEL", "model", "Hauptmodell"),
    ("AQUATICY_VISION_MODEL", "vision_model", "Bilder"),
    ("AQUATICY_SUBAGENT_MODEL", "subagent_model", "Helfer"),
    ("AQUATICY_CODE_MODEL", "code_model", "Code"),
)


def own_models(settings: Any) -> list[dict[str, str]]:
    """Die Modelle, die ein Konto selbst eingetragen hat -- nicht die des Betreibers.

    Grundlage fuer den Abschnitt "Eigene Modelle": er zeigt nur, was der
    Nutzer oben selbst hinzugefuegt hat. Ohne Konten gibt es keinen
    Unterschied zwischen "eigen" und "gestellt" -- dann ist die Liste leer.
    """
    if getattr(SESSION, "account", None) is None:
        return []
    try:
        basis = get_settings()
    except Exception:  # pragma: no cover
        return []
    eigene = []
    for feld, attr, name in OWN_MODEL_FIELDS:
        wert = str(getattr(settings, attr, "") or "")
        if wert and wert != str(getattr(basis, attr, "") or ""):
            eigene.append({"field": feld, "label": name, "model": wert})
    return eigene


def current_values() -> dict[str, str]:
    """Aktuelle Einstellungen als Formularwerte."""
    settings = SESSION.settings()
    return {
        "AQUATICY_MODEL": settings.model,
        "AQUATICY_VISION_MODEL": settings.vision_model,
        "AQUATICY_SUBAGENT_MODEL": settings.subagent_model,
        "AQUATICY_CODE_MODEL": settings.code_model,
        "AQUATICY_API_BASE": settings.api_base,
        "AQUATICY_SEARCH_BACKEND": settings.search_backend,
        "AQUATICY_SEARCH_ENGINES": settings.search_engines,
        "AQUATICY_SEARCH_VARIANTS": str(settings.search_variants),
        "AQUATICY_SEARXNG_URL": settings.searxng_url,
        "AQUATICY_LOCATION": settings.location,
        "AQUATICY_LANG": settings.lang,
        "AQUATICY_COUNTRY": settings.country,
        "AQUATICY_SUBAGENTS_AUTO": "true" if settings.subagents_auto else "false",
        "AQUATICY_MAX_SUBAGENTS": str(settings.max_subagents),
        "AQUATICY_SUBAGENT_BUDGET": str(settings.subagent_budget),
        "AQUATICY_SUBAGENT_PARALLEL": str(settings.subagent_parallel),



        "AQUATICY_RPM": str(settings.rpm) if settings.rpm else "",
        "AQUATICY_PARALLEL_CALLS": str(settings.parallel_calls) if settings.parallel_calls else "",
        "AQUATICY_MAX_TOOL_CALLS": str(settings.max_tool_calls),
        "AQUATICY_CONTEXT_TOKENS": str(settings.context_tokens),
        "AQUATICY_PLANNER_TIMEOUT": str(int(settings.planner_timeout)),
        "AQUATICY_ENABLE_PLAYWRIGHT": "true" if settings.enable_playwright else "false",
        "AQUATICY_HA_URL": settings.ha_url,
        "AQUATICY_HA_CONTROL": "true" if settings.ha_control else "false",
        "AQUATICY_HA_DIRECT": "true" if settings.ha_direct else "false",
        "AQUATICY_GOOGLE": "true" if settings.google_enabled else "false",
        "AQUATICY_GOOGLE_WRITE": "true" if settings.google_write else "false",
        "AQUATICY_GOOGLE_DIRECT": "true" if settings.google_direct else "false",
        "AQUATICY_STORAGE_URL": settings.storage_url,
        "AQUATICY_STORAGE_ACCESS": settings.storage_access,
        "AQUATICY_LAN_ENABLED": "true" if settings.lan_enabled else "false",
        "AQUATICY_LAN_SUBNET": settings.lan_subnet,
        "AQUATICY_MEMORY": "true" if settings.memory_enabled else "false",
        "AQUATICY_VM_SIZE": settings.vm_size,
        "AQUATICY_VM_USER_MODE": "true" if settings.vm_user_mode else "false",
        "AQUATICY_VM_INTERNET": "true" if settings.vm_internet else "false",
        "AQUATICY_VM_LAN": "true" if settings.vm_lan else "false",
        "AQUATICY_LEGAL_GUARD": "true" if settings.legal_guard else "false",
        "AQUATICY_AUTO_MODEL": "true" if settings.auto_model else "false",
        "AQUATICY_COUNCIL": "true" if getattr(settings, "council", False) else "false",
    }


def fix_model_id(model: str) -> str:
    """Ergaenzt ein fehlendes Anbieter-Praefix, wenn es eindeutig ist.

    Wer bei NVIDIA "nvidia/nemotron-3-ultra-550b-a55b" von der Webseite
    kopiert, traegt genau das ein -- und LiteLLM findet dazu keinen Anbieter.
    Statt den Nutzer mit "LLM Provider NOT provided" stehenzulassen, setzen
    wir das Praefix davor, das ohnehin gemeint war.
    """
    model = (model or "").strip()
    if not model or resolve_model(model):
        return model
    return suggest_model(model) or model


def google_client(settings: Settings) -> Any:
    """Der Google-Zugriff mit den aktuellen Einstellungen."""
    from aquaticy.google import Google, TokenStore

    return Google(
        settings.google_client_id,
        settings.google_client_secret,
        TokenStore(settings.data_dir, settings.memory_key),
    )


def google_write_gap(settings: Settings, tokens: Any) -> str:
    """Ein Satz, wenn "Aendern erlaubt" an ist, Google es aber nicht erteilt hat."""
    from aquaticy.google import granted_write

    erlaubt = granted_write(list(getattr(tokens, "scopes", []) or []))
    if not settings.google_write or erlaubt is None or all(erlaubt):
        return ""
    return (" Aber Google hat das Ändern nicht erlaubt. Klick in Aquaticy noch einmal auf "
            "„Verbinden“ und setz bei Google alle Haken.")


def google_state(settings: Settings) -> dict[str, Any]:
    """Was die Oberflaeche ueber die Google-Anbindung wissen darf.

    Token und Secret bleiben hier -- der Browser erfaehrt nur, ob etwas
    hinterlegt ist und welches Konto verbunden wurde.
    """
    client = google_client(settings)
    try:
        connected = client.connected()
        account = client.account()
        erlaubt = client.write_access() if connected else None
    finally:
        client.close()
    return {
        "enabled": settings.google_enabled,
        "write": settings.google_write,

        "write_granted": None if erlaubt is None else all(erlaubt),
        "has_id": bool(settings.google_client_id),
        "has_secret": bool(settings.google_client_secret),
        "connected": connected,
        "account": account,
    }







_GOOGLE_STATES: dict[str, tuple[str, float, str]] = {}



GOOGLE_FLOW_COOKIE = "aquaticy_google_flow"
_GOOGLE_STATES_LOCK = threading.Lock()
GOOGLE_STATE_SECONDS = 600.0


def _flow_hash(browser: str) -> str:
    return hashlib.sha256(browser.encode("utf-8")).hexdigest() if browser else ""


def google_state_new(account_id: str, browser: str = "") -> str:
    """Ein neuer, einmaliger state fuer genau dieses Konto (und diesen Browser)."""
    import secrets as _secrets

    state = _secrets.token_urlsafe(32)
    jetzt = time.time()
    with _GOOGLE_STATES_LOCK:
        for alt, (_, bis, _b) in list(_GOOGLE_STATES.items()):
            if bis < jetzt:
                _GOOGLE_STATES.pop(alt, None)
        _GOOGLE_STATES[state] = (account_id, jetzt + GOOGLE_STATE_SECONDS, _flow_hash(browser))
    return state


def google_state_take(state: str, account_id: str) -> bool:
    """Loest einen state ein -- genau einmal, rechtzeitig, vom selben Konto."""
    if not state:
        return False
    with _GOOGLE_STATES_LOCK:
        eintrag = _GOOGLE_STATES.pop(state, None)
    if eintrag is None:
        return False
    konto, bis, _ = eintrag
    return bis >= time.time() and hmac.compare_digest(konto, account_id)


def google_state_take_browser(state: str, browser: str) -> str | None:
    """Loest einen state ueber das Ablauf-Cookie ein -- fuer den Ruecksprung.

    Returns: die Kontokennung, fuer die die Anmeldung begonnen wurde -- oder
    None, wenn state oder Browser nicht passen. Einmalig wie google_state_take.
    """
    if not state or not browser:
        return None
    with _GOOGLE_STATES_LOCK:
        eintrag = _GOOGLE_STATES.pop(state, None)
    if eintrag is None:
        return None
    konto, bis, erwartet = eintrag
    if bis < time.time() or not erwartet:
        return None
    if not hmac.compare_digest(erwartet, _flow_hash(browser)):
        return None
    return konto


def google_redirect(host: str = "") -> str:
    """Wohin Google nach der Zustimmung zurueckschickt.

    Google erlaubt fuer Desktop-Anwendungen nur `localhost` und `127.0.0.1`.
    Sitzt der Browser auf einem anderen Geraet, laeuft die Weiterleitung ins
    Leere -- dann kopiert der Nutzer die Adresse aus der Adresszeile, der
    Code steht darin. Deshalb ist die Adresse hier fest und haengt NICHT vom
    aufrufenden Geraet ab: sie muss mit der in der Google Cloud Console
    eingetragenen uebereinstimmen, sonst lehnt Google ab.
    """
    port = host.rsplit(":", 1)[-1] if ":" in host else str(DEFAULT_PORT)
    if not port.isdigit():
        port = str(DEFAULT_PORT)
    return f"http://localhost:{port}/google"


def check_values(values: dict[str, str]) -> str:
    """Prueft die Formularwerte. Returns: die Beanstandung, oder "".

    Der Browser kann alles schicken -- ein Zahlenfeld mit Buchstaben darin,
    eine Auswahl mit einem Wort, das es nicht gibt, eine Adresse von einer
    Laenge, die niemand tippt. Hier ist die Stelle, an der das auffaellt.
    """
    for key, wert in values.items():
        if len(wert) > MAX_VALUE_CHARS:
            return f"{key}: zu lang ({len(wert)} Zeichen, erlaubt sind {MAX_VALUE_CHARS})."
        if key in NUMBERS and wert:
            von, bis = NUMBERS[key]
            try:
                zahl = int(wert)
            except ValueError:
                return f"{key}: '{wert}' ist keine Zahl."
            if not von <= zahl <= bis:
                return f"{key}: {zahl} liegt ausserhalb von {von} bis {bis}."
        if key in CHOICES and wert and wert not in CHOICES[key]:
            erlaubt = ", ".join(CHOICES[key])
            return f"{key}: '{wert}' gibt es nicht. Erlaubt sind: {erlaubt}."
    return ""


def save_values(payload: dict[str, Any]) -> Path:
    """Schreibt die Formularwerte in die `.env` und laedt neu.

    Raises:
        ValueError: Wenn ein Wert nicht durch die Pruefung kommt. Dann wird
            nichts geschrieben -- halb gespeicherte Einstellungen waeren
            schlimmer als gar keine.
    """
    session = SESSION.current() if isinstance(SESSION, SessionProxy) else SESSION
    pro_integration = any(
        key in payload
        for key in (
            "AQUATICY_HA_URL",
            "AQUATICY_HA_CONTROL",
            "AQUATICY_HA_DIRECT",
            HA_TOKEN_FIELD,
            "AQUATICY_LAN_ENABLED",
            "AQUATICY_LAN_SUBNET",
            "AQUATICY_STORAGE_URL",
            "AQUATICY_STORAGE_ACCESS",
        )
    )
    plus_workshop = str(payload.get("AQUATICY_VM_SIZE", "")).strip() == "plus"
    if not session.ultra and (pro_integration or plus_workshop):
        raise ValueError(
            "Heimnetz-Suche, Home Assistant, Lagerverwaltung und die große virtual machine "
            "gibt es nur mit einem Ultra-Konto."
        )
    if not session.ultra:
        base = get_settings()
        for key, erlaubt in (("AQUATICY_API_BASE", base.api_base),
                             ("AQUATICY_SEARXNG_URL", base.searxng_url)):
            if key in payload and str(payload.get(key) or "").strip() != (erlaubt or ""):
                raise ValueError(
                    "Eigene Adressen für Modell oder Suche gibt es nur mit einem Ultra-Konto — "
                    "sonst legt sie der Betreiber fest."
                )
    guard_off = "AQUATICY_LEGAL_GUARD" in payload and not guard_on(
        str(payload.get("AQUATICY_LEGAL_GUARD", ""))
    )
    if guard_off and not session.ultra:
        raise ValueError(
            "Die Rechts-Leitplanken (Grundgesetz und BGB) lassen sich nur mit einem "
            "Ultra-Konto abschalten."
        )
    user_mode_on = "AQUATICY_VM_USER_MODE" in payload and str(
        payload.get("AQUATICY_VM_USER_MODE", "")
    ).strip().lower() in {"1", "true", "yes", "on", "ja"}
    if user_mode_on and not session.ultra:
        raise ValueError(
            "Der User mode (virtual machine mit Desktop und Internet) braucht ein Ultra-Konto."
        )


    netz_on = "AQUATICY_VM_INTERNET" in payload and str(
        payload.get("AQUATICY_VM_INTERNET", "")
    ).strip().lower() in {"1", "true", "yes", "on", "ja"}
    if netz_on and not session.ultra:
        raise ValueError("Internet für die virtual machine gibt es nur mit einem "
                         "Ultra-Konto.")
    lan_on = "AQUATICY_VM_LAN" in payload and str(
        payload.get("AQUATICY_VM_LAN", "")
    ).strip().lower() in {"1", "true", "yes", "on", "ja"}
    if lan_on and not session.ultra:

        raise ValueError("Das lokale Netz für die virtual machine gibt es nur mit einem "
                         "Ultra-Konto.")
    values = {
        key: str(payload.get(key, "")).strip() for key in SETTING_KEYS if key in payload
    }
    if "AQUATICY_LEGAL_GUARD" in values:


        values["AQUATICY_LEGAL_GUARD"] = "false" if guard_off else "true"
    beanstandung = check_values(values)
    if beanstandung:
        raise ValueError(beanstandung)
    for key in (
        "AQUATICY_MODEL",
        "AQUATICY_VISION_MODEL",
        "AQUATICY_SUBAGENT_MODEL",
        "AQUATICY_CODE_MODEL",
    ):
        if values.get(key):
            values[key] = fix_model_id(values[key])

            from aquaticy.config import MODEL_RULE_TEXT, model_allowed

            basis = values.get("AQUATICY_API_BASE", session.settings().api_base) or ""
            if not model_allowed(values[key], basis):
                raise ValueError(MODEL_RULE_TEXT)
    if UPGRADE_DIR is not None:


        from aquaticy import upgrading

        for key in ("AQUATICY_MODEL", "AQUATICY_VISION_MODEL",
                    "AQUATICY_SUBAGENT_MODEL", "AQUATICY_CODE_MODEL"):
            if values.get(key) and not upgrading.allowed(UPGRADE_DIR, values[key], session.ultra):
                raise ValueError("Diese Modellversion steht dir nicht mehr zur Wahl.")
    ha_token = str(payload.get(HA_TOKEN_FIELD, "")).strip()

    geheim: dict[str, str] = {}
    if ha_token:
        geheim["HA_TOKEN"] = ha_token

        from aquaticy.homeassistant import normalize_url

        ziel = normalize_url(str(values.get("AQUATICY_HA_URL")
                                 or payload.get("AQUATICY_HA_URL")
                                 or session.settings().ha_url))
        if ziel:
            geheim["HA_TOKEN_URL"] = ziel


    google_id = str(payload.get(GOOGLE_ID_FIELD, "")).strip()
    if google_id:
        values["GOOGLE_CLIENT_ID"] = google_id
    google_secret = str(payload.get(GOOGLE_SECRET_FIELD, "")).strip()
    if google_secret:
        geheim["GOOGLE_CLIENT_SECRET"] = google_secret
    if geheim and session.profile is None:

        geheim.pop("HA_TOKEN_URL", None)
        values.update(geheim)
        geheim = {}
    target = (
        session.settings().env_path
        if session.profile is not None
        else find_env_file() or DEFAULT_ENV_PATH
    )
    written = write_env_file(values, target)
    if geheim and session.profile is not None:
        from aquaticy.keyvault import VaultError

        tresor = account_vault(session.profile, session.account)
        for name, wert in geheim.items():
            try:
                tresor.set_secret(name, wert)
            except VaultError as exc:
                raise ValueError(str(exc)) from exc




    if session.profile is None:
        load_env(written, override=True)
    else:
        from aquaticy.memory import secure_file

        secure_file(written)
    if UPGRADE_DIR is not None and values.get("AQUATICY_MODEL"):
        upgrading.choose(UPGRADE_DIR, values["AQUATICY_MODEL"], session.ultra,
                         getattr(session.account, "id", "") or "")
    session.reload()
    return written


def scrub_payload(wert: Any, geheim: list[str]) -> Any:
    """Entfernt Schluessel aus allen Texten eines Ereignisses (auch verschachtelt)."""
    from aquaticy.keyvault import scrub

    if isinstance(wert, str):
        return scrub(wert, geheim)
    if isinstance(wert, dict):
        return {k: scrub_payload(v, geheim) for k, v in wert.items()}
    if isinstance(wert, list):
        return [scrub_payload(v, geheim) for v in wert]
    return wert




_SCHLUESSEL_MUSTER = re.compile(
    r"(?i)((?:bearer|token|authorization:?)\s+)[A-Za-z0-9._~+/=-]{12,}|"
    r"((?:api[_-]?key|(?:access|refresh|id)[_-]?token|token|code|secret|password|passwort)"
    r"[\"']?\s*[=:]\s*[\"']?)"
    r"[^\s&\"',;]{6,}|\b(?:sk|pk|rk|nvapi|hf|gsk|xai)[-_][A-Za-z0-9_-]{16,}")


def scrub_error(text: str, geheim: list[str] | None = None) -> str:
    """Ein Fehlertext fuer den Browser -- ohne Schluessel (9.6.0)."""
    from aquaticy.keyvault import scrub

    if geheim is None:
        try:
            geheim = list(SESSION.settings().secrets())
        except Exception:
            geheim = []
    ergebnis = scrub(str(text or ""), geheim)
    return _SCHLUESSEL_MUSTER.sub(
        lambda m: (m.group(1) or m.group(2) or "") + "••••", ergebnis)


def linked_view(session: Any) -> dict[str, Any]:
    """Die Add-ons NVIDIA NIM und Mistral (12.0.0 Luna): Schluessel, Modelle, Tokens.

    Den Schluessel selbst bekommt der Browser nie -- nur, ob einer da ist.
    """
    from aquaticy import addons, linked

    settings = session.settings()
    stand = linked.load(settings.data_dir)
    aktiv = set(linked.linked_providers(settings))
    konten = []
    for provider, d in linked.PROVIDERS.items():
        info = stand.get(provider) or {}
        verknuepft = provider in aktiv
        konten.append({
            "provider": provider, "label": d["label"], "company": d["company"],
            "get_key": d["get_key"], "form": d["form"], "linked": verknuepft,
            "installed": addons.installed(settings, provider),

            "provided": (not verknuepft and session.profile is not None
                         and bool(os.environ.get(d["key"], "").strip())),
            "sign_in": [{"id": art, "label": linked.SIGN_IN_LABELS[art]}
                        for art in linked.SIGN_IN.get(provider, ())],
            "tier": info.get("tier", "") if verknuepft else "",
            "tokens": info.get("tokens") if verknuepft else None,
            "models": [m.get("label") or m.get("id") for m in info.get("models", [])]
            if verknuepft else [],
            "note": info.get("note", "") if verknuepft else "",
            "warning": info.get("warning", "") if verknuepft else "",
            "checked": webview.moment_text(info["checked"])
            if verknuepft and info.get("checked") else "",
        })
    arbeiter, pruefer = linked.council_roles(settings)
    return {"accounts": konten, "council": {
        "possible": bool(arbeiter) and pruefer is not None,
        "on": bool(getattr(settings, "council", False)),
        "workers": [m for _, m in arbeiter], "checker": pruefer[1] if pruefer else "",
        "judge": settings.model}}


def _forget_model_key(session: Any, provider: str) -> None:
    """Loescht den Schluessel eines Modell-Add-ons samt ausgelesenem Stand."""
    from aquaticy import linked

    name = linked.PROVIDERS[provider]["key"]
    if session.profile is not None:
        account_vault(session.profile, session.account).remove(name)
    else:
        os.environ.pop(name, None)
        write_env_file({name: ""}, find_env_file() or DEFAULT_ENV_PATH)
    linked.save(session.settings().data_dir, provider, None)


def linked_action(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Schluessel eines Modell-Add-ons: verknuepfen, aktualisieren, entfernen.

    Seit 12.0.0 Luna der einzige Weg, in Aquaticy einen API-Schluessel
    einzutragen -- und nur fuer NVIDIA NIM und Mistral, nachdem das Add-on
    installiert ist. Gespeichert wird erst, wenn der Anbieter ihn annimmt.
    """
    from aquaticy import addons, linked
    from aquaticy.keyvault import VaultError, check_key

    session = SESSION.current() if isinstance(SESSION, SessionProxy) else SESSION
    aktion = str(payload.get("action") or "")
    provider = str(payload.get("provider") or "")
    erkannt = linked.detect_provider(str(payload.get("key") or ""))
    if aktion == "link" and not provider:
        provider = erkannt
        if not provider:
            return {"ok": False, "error": "Diesen Schlüssel kenne ich nicht. Ein Schlüssel von "
                                          "NVIDIA beginnt mit „nvapi-“. Einer von Mistral hat 32 "
                                          "Buchstaben und Zahlen."}, 400
    if provider not in linked.PROVIDERS:
        return {"ok": False, "error": "Diesen Anbieter gibt es hier nicht."}, 400
    d = linked.PROVIDERS[provider]
    name = d["key"]
    if aktion == "link" and not addons.installed(session.settings(), provider):
        return {"ok": False, "error": f"Installiere zuerst das Add-on {d['label']}."}, 400
    if aktion == "link" and erkannt and erkannt != provider:
        anders = linked.PROVIDERS[erkannt]["label"]
        return {"ok": False, "error": f"Das ist ein Schlüssel von {anders} — füg ihn beim "
                                      f"Add-on {anders} ein."}, 400
    wer = getattr(session.account, "id", "") or "lokal"
    try:
        if aktion in ("link", "refresh"):
            if not KEY_TEST_LIMIT.allow(wer):
                return {"ok": False, "error": "Das waren zu viele Versuche. Versuch es in einer "
                                              "Minute noch einmal."}, 429
            if aktion == "link":
                wert = check_key(name, str(payload.get("key") or ""))
            else:
                settings = session.settings()
                wert = (settings.api_keys.get(name, "") if session.profile is None
                        or name in settings.own_key_names else "")
                wert = wert or (os.environ.get(name, "").strip() if session.profile is None
                                else "")
                if not wert:
                    return {"ok": False, "error": "Hier ist noch kein Schlüssel."}, 400
            info = linked.inspect(provider, wert)
            if aktion == "link":
                if session.profile is not None:
                    account_vault(session.profile, session.account).set(name, wert)
                else:
                    ziel = write_env_file({name: wert}, find_env_file() or DEFAULT_ENV_PATH)
                    load_env(ziel, override=True)
            linked.save(session.settings().data_dir, provider, info)
        elif aktion == "unlink":
            _forget_model_key(session, provider)
        else:
            return {"ok": False, "error": "Unbekannte Aktion."}, 400
    except (VaultError, linked.LinkError) as exc:
        return {"ok": False, "error": scrub_error(str(exc))}, 400
    session.reload()
    forget_strong_models(session.settings().data_dir)
    return {"ok": True, "provider": provider, **linked_view(session)}, 200


def addons_view(session: Any) -> dict[str, Any]:
    """Das Add-on-Fenster: der Katalog, bei NVIDIA NIM und Mistral mit dem Schluesselstand."""
    from aquaticy import addons, linked

    settings = session.settings()


    for provider in linked.linked_providers(settings):
        addons.mark_installed(settings, provider)
    view = addons.public_view(settings, session.ultra)
    konten = {k["provider"]: k for k in linked_view(session)["accounts"]}
    from aquaticy import bridge

    for eintrag in view["addons"]:
        if eintrag["id"] in konten:
            eintrag["konto"] = konten[eintrag["id"]]
        if eintrag["id"] in bridge.MESSENGERS:

            eintrag["bruecke"] = bridge.public_view(settings, eintrag["id"], session.ultra)
    return view



ADDON_ACTIONS = frozenset({
    "install", "uninstall", "enable", "disable", "token", "login", "login_done", "logout",
    "feeds", "rights", "bridge",
})



_RESTARTS_WORKSHOP = frozenset({"uninstall", "enable", "disable", "logout"})


def _bridge_action(session: Any, settings: Any, messenger: str, daten: Any) -> str:
    """Speichert die Einstellungen der Messenger-Bruecke und weckt ihren Lauf (12.6.6 Luna).

    Nur Ultra darf sie einschalten; Einschalten braucht alle Voraussetzungen.
    """
    from aquaticy import addons
    from aquaticy import bridge as bridge_mod

    if messenger not in bridge_mod.MESSENGERS:
        raise addons.AddOnError("Dafür gibt es keine Brücke.")
    if not isinstance(daten, dict):
        raise addons.AddOnError("Es fehlen die Einstellungen.")
    einschalten = daten.get("an") is True
    ready = bridge_mod.ready_problem(settings, messenger, session.ultra) if einschalten else ""
    try:
        neu = bridge_mod.set_config(settings, messenger, daten, ready=ready)
    except bridge_mod.BridgeError as exc:
        raise addons.AddOnError(str(exc)) from exc
    runner = _bridge_runner(session)
    if neu["an"]:
        runner.ensure_running()
        runner.wake()
        return ("Gespeichert. Die Brücke ist an. Schreib erst, wenn „bereit“ dasteht: "
                "Beim ersten Blick merkt sie sich nur, was schon im Chat steht.")
    runner.wake()
    return "Gespeichert. Die Brücke ist aus."


def addon_action(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Installieren, Schalten, Anmelden -- alles aus dem Add-on-Fenster.

    Returns: (Antwort, HTTP-Status).
    """
    from aquaticy import addons

    session = SESSION.current() if isinstance(SESSION, SessionProxy) else SESSION
    settings = session.settings()
    action = str(payload.get("action") or "").strip().lower()
    addon_id = str(payload.get("id") or "").strip().lower()
    if action not in ADDON_ACTIONS:
        return {"ok": False, "error": "Unbekannte Aktion."}, 400
    try:
        addon = addons.get(addon_id)
        if action in _RESTARTS_WORKSHOP and addon.programm and session.busy():
            return {"ok": False, "error": (
                "Gerade arbeitet Aquaticy noch — die virtual machine muss dafür neu starten. "
                "Bitte gleich noch einmal."
            )}, 409
        hinweis = ""
        qr_token = ""
        if action == "install":
            addons.install(settings, addon.id, session.ultra,
                           on_done=lambda: session.reload(workshop=True))
            if not addon.programm:
                session.reload(workshop=True)
            hinweis = "Wird installiert …" if addon.programm else "Installiert und eingeschaltet."
        elif action == "uninstall":
            if addon.programm:
                session.reload(workshop=True)
            if addon.id in addons.MODEL_ADDONS:

                _forget_model_key(session, addon.id)
                forget_strong_models(session.settings().data_dir)
            addons.uninstall(session.settings(), addon.id)
            session.reload(workshop=True)
            hinweis = ("Entfernt. Der Schlüssel ist gelöscht."
                       if addon.id in addons.MODEL_ADDONS
                       else "Deinstalliert — Programm und Anmeldung sind gelöscht.")
        elif action in ("enable", "disable"):
            addons.set_enabled(settings, addon.id, action == "enable", session.ultra)
            session.reload(workshop=True)
            hinweis = "Eingeschaltet." if action == "enable" else "Ausgeschaltet."
        elif action == "token":
            if addon.login != "token":
                raise addons.AddOnError(f"{addon.name} meldet sich nicht mit einem Token an.")
            ergebnis = addons.github_login(settings, str(payload.get("token") or ""))
            session.reload()
            hinweis = f"Angemeldet als {ergebnis['who']}." + (
                f" {ergebnis['warning']}" if ergebnis["warning"] else "")
        elif action == "login":
            hinweis, qr_token = _addon_login(session, addon)
        elif action == "login_done":
            with session._owner._qr_state_lock:
                if payload.get("token"):
                    name, token, until = session._owner._qr_login
                    if (not session.ultra or name != addon.id or until <= time.monotonic()
                            or not same_secret(str(payload["token"]), token)):
                        raise addons.AddOnError("Die Anmeldung ist abgelaufen. Öffne sie erneut.")
                addons.mark_login(settings, addon.id, "angemeldet")
                if session._owner._qr_login[0] == addon.id:
                    session._owner._qr_login = ("", "", 0.0)
            hinweis = "Gemerkt: angemeldet."
        elif action == "logout":
            if addon.programm:
                session.reload(workshop=True)
            addons.logout(session.settings(), addon.id)
            session.reload(workshop=True)
            hinweis = "Abgemeldet." + (
                " Entferne die virtual machine auf dem Handy auch unter „Verknüpfte Geräte“."
                if addon.login == "qr" else "")
        elif action == "rights":



            neu = addons.set_rights(settings, addon.id, payload.get("rechte"))
            hinweis = "Gespeichert: " + addons.rights_text(addon.id, neu) + "."
        elif action == "bridge":
            hinweis = _bridge_action(session, settings, addon.id, payload.get("bruecke"))
        else:
            feeds = addons.set_feeds(settings, payload.get("feeds") or [])
            session.reload()
            hinweis = f"{len(feeds)} Feeds gespeichert."
        if action in ("uninstall", "disable", "logout"):

            from aquaticy import bridge as bridge_mod

            if addon.id in bridge_mod.MESSENGERS:
                bridge_mod.set_config(session.settings(), addon.id, {"an": False})
    except addons.AddOnError as exc:
        return {"ok": False, "error": str(exc)}, 400
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500
    antwort = {"ok": True, "message": hinweis, **addons_view(session)}
    if action == "login":
        antwort["qr_token"] = qr_token
    return antwort, 200





COWORKER_ACTIONS = frozenset({
    "create", "message", "approve", "reject", "pause", "resume", "wake", "rules", "edit",
    "delete", "seen", "reset_notes", "preferences",
})


def _coworker_scheduler(session: Any) -> Any:
    """Der Taktgeber, der die Coworker dieses Kontos weckt."""
    konto = getattr(session, "account", None)
    if konto is None:
        return COWORKER_SCHEDULER
    with _SCHEDULER_LOCK:
        return USER_COWORKERS.get(konto.id)


def coworkers_view(session: Any, *, badge_only: bool = False) -> dict[str, Any]:
    """Was der Browser von den Coworkern sieht -- ohne ein einziges Geheimnis."""
    from aquaticy import coworker as coworker_mod
    from aquaticy.coworker_context import connection_key

    plan = session.plan
    erlaubt = plan in coworker_mod.MAX_COWORKERS
    antwort: dict[str, Any] = {"allowed": True, "autonomous_allowed": erlaubt,
                               "plan": plan, "badge": 0}
    settings = session.settings()
    store = coworker_mod.CoworkerStore(settings.db_path)
    antwort["badge"] = store.unseen()
    if badge_only:
        antwort["working"] = any(coworker_mod.is_running(store.db_path, cw.id)
                                 for cw in store.all())
        return antwort
    antwort.update({
        "max": coworker_mod.MAX_COWORKERS.get(plan, 0),
        "max_scheduled": coworker_mod.MAX_SCHEDULED,
        "vm": coworker_mod.vm_possible(settings, session.ultra),
        "categories": coworker_mod.catalog(session.ultra),
        "avatars": list(coworker_mod.AVATARS),
        "connections": coworker_mod.connections(settings, session.ultra),
        "min_sleep": coworker_mod.MIN_SLEEP_MINUTES.get(plan, 15),
        "daily": coworker_mod.DAILY_RUNS.get(plan, 0),
        "coworkers": [{**coworker_mod.view(store, cw),
                       "home_approval_valid": bool(cw.ha_binding) and cw.ha_binding ==
                       connection_key(settings)} for cw in store.all()],
    })
    return antwort


def _coworker_insult(konto: Any, text: str, wo: str) -> str:
    """Ai-guard: eine Beleidigung in Aufgabe oder Nachricht zaehlt wie im Chat."""
    if AIGUARD is None or konto is None:
        return ""
    from aquaticy.aiguard import demeaning_request, insult_level

    stufe = insult_level(text) or demeaning_request(text)
    if not stufe:
        return ""
    AIGUARD.record_incident(konto.id, "beleidigung", stufe, chat=wo,
                            detail="Beleidigung an einen Coworker (erkannt)",
                            enforce=not getattr(konto, "ultra", False))
    return ("Das schicke ich nicht weiter — Ai-guard hat darin eine Beleidigung oder den "
            "Auftrag erkannt, jemanden herabzusetzen.")


def _json_int(wert: Any) -> int:
    """Eine Zahl aus einer JSON-Anfrage. Unsinn wirft TypeError, ValueError oder OverflowError."""
    return int(wert)


def coworker_image(payload: dict[str, Any], settings: Settings) -> tuple[str, str]:
    """Nimmt das Vergleichsbild eines Bildauftrags entgegen.

    Es landet im privaten Datenordner des Kontos -- derselbe Ort, an dem
    auch geprueftes Bildmaterial liegt. Zurueck kommt (Kennung, Fehler);
    genau eines von beiden ist gefuellt.
    """
    from aquaticy.media import save_snapshot

    try:
        data = base64.b64decode(str(payload.get("image_data") or ""), validate=True)
    except (ValueError, binascii.Error):
        return "", "Das Bild konnte nicht gelesen werden."
    if not data:
        return "", "Für die Bildsuche fehlt das Bild."
    if not looks_like_image(data) or blocked_upload(str(payload.get("image_name") or "")):
        return "", ("Das Bildformat stimmt nicht: Es gehen nur echte PNG-, JPEG-, "
                    "GIF- oder WebP-Bilder.")
    if len(data) > MAX_UPLOAD_BYTES:
        return "", (
            f"Das Bild ist zu groß (erlaubt sind "
            f"{MAX_UPLOAD_BYTES // 1_000_000} MB)."
        )
    try:


        return save_snapshot(settings.data_dir, data, image_mime(data), keep=True), ""
    except (OSError, ValueError):
        return "", "Dieses Bildformat wird nicht unterstützt (JPEG, PNG, WebP, GIF)."


def coworker_action(payload: dict[str, Any], konto: Any) -> tuple[dict[str, Any], int]:
    """Anlegen, schreiben, freigeben, pausieren -- alles aus der Coworker-Uebersicht.

    Returns: (Antwort, HTTP-Status).
    """
    from aquaticy import coworker as coworker_mod
    from aquaticy.agent import new_session_id
    from aquaticy.cache import Cache

    session = SESSION.current() if isinstance(SESSION, SessionProxy) else SESSION
    if konto is None:
        konto = getattr(session, "account", None)
    if AIGUARD is not None and konto is not None and AIGUARD.is_banned(
            user_id=konto.id) is not None:
        return {"ok": False, "error": "Während einer Sperre arbeiten keine Coworker."}, 403
    action = str(payload.get("action") or "").strip().lower()
    if action not in COWORKER_ACTIONS:
        return {"ok": False, "error": "Unbekannte Aktion."}, 400
    settings = session.settings()
    store = coworker_mod.CoworkerStore(settings.db_path)
    takt = _coworker_scheduler(session)
    hinweis = ""
    try:
        if action == "create":
            name = str(payload.get("name") or "")
            aufgabe = str(payload.get("goal") or "")
            nein = _coworker_insult(konto, f"{name}\n{aufgabe}", "coworker")
            if nein:
                return {"ok": False, "error": nein}, 400
            chat = new_session_id()
            timing = payload.get("schedule") or {}
            if not isinstance(timing, dict):
                raise coworker_mod.CoworkerError("Der Zeitplan muss ein Objekt sein.")
            if not timing and session.plan not in coworker_mod.MAX_COWORKERS:
                return {"ok": False, "error": "Dauerhafte Coworker gibt es mit Pro und Ultra."}, 403

            timing = {k: v for k, v in timing.items() if k not in ("image_id", "image_note")}
            image_id, saved = "", False
            try:
                if (timing.get("kind") in ("visual", "image")
                        and not selected_vision_model(settings)):
                    raise coworker_mod.CoworkerError(
                        "Die Bildbeobachtung braucht ein Vision-Modell unter Modelle und "
                        "Verbindungen im Chat.")
                if timing.get("kind") == "image":
                    image_id, error = coworker_image(payload, settings)
                    if error:
                        raise coworker_mod.CoworkerError(error)
                    timing["image_id"] = image_id
                kollege: Any = store.add(name, aufgabe, avatar=str(payload.get("avatar") or ""),
                                         plan=session.plan, chat=chat, schedule=timing)
                saved = True

                store.set_preferences(kollege.id, {k: payload[k] for k in (
                    "sharing_chats", "sharing_coworkers", "notes_limit") if k in payload})
                kollege = store.get(kollege.id)
            except (ValueError, TypeError, OverflowError):
                if saved:
                    delete_coworker(store, kollege.id, settings)
                raise
            finally:
                if image_id and not saved:
                    from aquaticy.media import delete_snapshot

                    with contextlib.suppress(OSError, ValueError):
                        delete_snapshot(settings.data_dir, image_id)

            with contextlib.suppress(Exception):
                Cache(settings.db_path, settings.cache_ttl_hours).add_history(
                    chat, coworker_mod.chat_title(kollege),
                    f"Hallo, ich bin {kollege.name}. Ich kümmere mich ab jetzt um:\n\n"
                    f"> {kollege.goal}\n\nMeine Meldungen erscheinen hier und in der "
                    "Coworker-Übersicht. Bevor ich etwas verändere, frage ich — so, wie "
                    "du es in meinen Regeln einstellst. Schreiben kannst du mir in der "
                    "Coworker-Übersicht; hier im Chat antwortet dir Aquaticy wie sonst auch "
                    "— mit meinen Meldungen im Blick.", {"coworker": kollege.id})
            hinweis = f"{kollege.name} fängt gleich an."
        else:
            try:
                nummer = _json_int(payload.get("id"))
            except (TypeError, ValueError, OverflowError):
                return {"ok": False, "error": "Keine gültige Kennung."}, 400
            kollege = store.get(nummer)
            if kollege is None:
                return {"ok": False, "error": "Diesen Coworker gibt es nicht."}, 404
            if action == "message":
                text = coworker_mod._clean_text(payload.get("text"), coworker_mod.MAX_MESSAGE)
                if not text:
                    return {"ok": False, "error": "Schreib erst etwas."}, 400
                nein = _coworker_insult(konto, text, f"coworker:{kollege.id}")
                if nein:
                    return {"ok": False, "error": nein}, 400
                store.add_log(kollege.id, "nachricht", text)
                hinweis = (f"{kollege.name} liest es gleich." if kollege.enabled else
                           f"{kollege.name} ist pausiert und liest es, sobald es weitergeht.")
            elif action in ("approve", "reject"):
                try:
                    anfrage = _json_int(payload.get("action_id"))
                except (TypeError, ValueError, OverflowError):
                    return {"ok": False, "error": "Keine gültige Anfrage."}, 400
                entschieden = store.decide(kollege.id, anfrage, action == "approve")
                if entschieden is None:
                    return {"ok": False, "error": "Diese Anfrage ist schon entschieden."}, 409
                if action == "approve":

                    def ausfuehren() -> None:
                        try:
                            banned = AIGUARD is not None and konto is not None and \
                                AIGUARD.is_banned(user_id=konto.id) is not None
                            fresh_plan = (_plan_of(konto.id, konto) if konto is not None
                                          else session.plan)
                            if banned:
                                ok, ergebnis = False, "Während einer Sperre laufen keine Aktionen."
                            else:
                                ok, ergebnis = coworker_mod.run_action(
                                    store, entschieden, session.settings(), fresh_plan == "ultra")
                        except Exception as exc:
                            ok, ergebnis = False, f"Fehler: {type(exc).__name__}"
                        try:
                            store.finish_action(entschieden["id"], ok, ergebnis)
                            store.add_log(kollege.id, "aktion",
                                          ("Erledigt: " if ok else "Hat nicht geklappt: ")
                                          + entschieden["summary"], seen=True)
                        except sqlite3.Error:
                            coworker_mod.LOG.exception("Coworker: Ergebnis nicht gespeichert")
                        if takt is not None:
                            takt.wake()

                    threading.Thread(target=ausfuehren, name="aquaticy-coworker-aktion",
                                     daemon=True).start()
                    hinweis = "Erlaubt — wird ausgeführt."
                else:
                    store.add_log(kollege.id, "aktion",
                                  "Abgelehnt: " + entschieden["summary"], seen=True)
                    hinweis = "Abgelehnt."
            elif action in ("pause", "resume"):
                store.set_enabled(kollege.id, action == "resume")
                hinweis = "Pausiert." if action == "pause" else "Geht weiter."
            elif action == "wake":
                if not kollege.enabled:
                    return {"ok": False, "error": "Erst fortsetzen, dann wecken."}, 400
                store.wake(kollege.id, "vom Nutzer geweckt")
                hinweis = f"{kollege.name} legt gleich los."
            elif action == "rules":
                store.set_rules(kollege.id, payload.get("rules"), settings=settings,
                                ultra=session.ultra)
                hinweis = "Regeln gespeichert."
            elif action == "edit":
                neuer_name = payload.get("name")
                neue_aufgabe = payload.get("goal")
                nein = _coworker_insult(konto, f"{neuer_name or ''}\n{neue_aufgabe or ''}",
                                        f"coworker:{kollege.id}")
                if nein:
                    return {"ok": False, "error": nein}, 400
                if "interval_seconds" in payload and (
                    type(payload["interval_seconds"]) is not int
                    or payload["interval_seconds"] not in coworker_mod.INTERVAL_SECONDS
                ):
                    raise ValueError("Wähl einen der angebotenen Rhythmen.")
                store.update(kollege.id, name=None if neuer_name is None else str(neuer_name),
                             goal=None if neue_aufgabe is None else str(neue_aufgabe),
                             avatar=None if payload.get("avatar") is None
                             else str(payload.get("avatar")),
                             interval_seconds=payload.get("interval_seconds"))
                hinweis = "Gespeichert."
            elif action == "preferences":
                store.set_preferences(kollege.id, payload, settings=settings, ultra=session.ultra)
                hinweis = "Einstellungen gespeichert."
            elif action == "reset_notes":
                store.reset_notes(kollege.id)
                hinweis = f"Die Notizen von {kollege.name} sind gelöscht."
            elif action == "delete":
                delete_coworker(store, kollege.id, settings)
                coworker_mod.stop_boxes(settings.data_dir, kollege.id)
                hinweis = f"{kollege.name} ist gelöscht. Sein Chat bleibt."
            else:
                store.mark_seen(kollege.id)
    except (ValueError, TypeError, OverflowError) as exc:
        return {"ok": False, "error": str(exc)}, 400
    except sqlite3.Error:
        return {"ok": False, "error": "Das ließ sich nicht speichern. Bitte versuch es gleich "
                "noch einmal."}, 500
    if takt is not None and action in ("create", "message", "wake", "resume"):
        takt.wake()
    return {"ok": True, "message": hinweis, **coworkers_view(session)}, 200


def workshop_busy(session: Any) -> bool:
    sessions = session.chat_sessions() if hasattr(session, "chat_sessions") else [session]
    return any(chat.has_running_chat() for chat in sessions)


def _addon_login(session: Any, addon: Any) -> tuple[str, str]:
    """Oeffnet das Programm in der virtual machine -- anmelden tut sich der Nutzer selbst."""
    from aquaticy import addons
    from aquaticy import sandbox as werkstatt

    settings = session.settings()
    if addon.login != "qr":
        raise addons.AddOnError(f"{addon.name} braucht keine Anmeldung in der virtual machine.")
    ok, warum = addons.usable(addon, settings, session.ultra)
    if not ok:
        raise addons.AddOnError(warum)
    if not addons.active(settings, addon.id, session.ultra):
        raise addons.AddOnError(f"{addon.name} ist nicht installiert oder ausgeschaltet.")
    box = werkstatt.shared(settings)
    if workshop_busy(session):
        raise addons.AddOnError("Ein Chat läuft gerade. Warte, bis er fertig ist.")
    with session._owner._qr_lock:
        qr_token = secrets.token_urlsafe(24)
        with session._owner._qr_state_lock:
            session._owner._qr_login = (addon.id, qr_token, time.monotonic() + 600)
        try:
            fertig = box.desktop("open", addons.APP_OF[addon.id], timeout=90)
        except Exception:
            with session._owner._qr_state_lock:
                if session._owner._qr_login[1] == qr_token:
                    session._owner._qr_login = ("", "", 0.0)
            raise
    if fertig.returncode != 0:
        with session._owner._qr_state_lock:
            if session._owner._qr_login[1] == qr_token:
                session._owner._qr_login = ("", "", 0.0)
        raise addons.AddOnError(
            f"{addon.name} ließ sich nicht öffnen: "
            + (fertig.stderr.decode("utf-8", "replace").strip() or "keine Meldung")[:300]
        )
    return (
        f"{addon.name} ist offen. Scanne den QR-Code im Anmeldefenster mit deinem Handy "
        "und drück dann „Ich bin angemeldet“."
    ), qr_token


def front_is_messenger(window: dict[str, Any], after: dict[str, Any], name: str) -> bool:
    """Ist nach dem Bildschirmfoto der Messenger das vordere Fenster?

    Ist der Titel des vorderen Fensters bekannt, muss er der des Messengers sein. Meldet der
    Fenstermanager keinen Titel, entscheidet die Klasse; fehlt auch die, geht es weiter: Das
    Bild verlaesst den Server ohnehin nur als frisch gezeichneter, echter Kopplungscode
    dieses Messengers, nie als Ausschnitt vom Bildschirm.
    """
    from aquaticy import addons

    titel = str(after.get("aktiv") or "")[:200]
    if titel:
        return titel == str(window.get("titel") or "")
    klasse = str(after.get("aktiv_klasse") or "").casefold()
    return addons.messenger_of(klasse, "") == name if klasse else True


def addon_qr(session: Any, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Kurzlebige, kontogebundene QR-Anmeldung. Gibt nie ein ganzes Bildschirmfoto heraus."""
    from aquaticy import addons
    from aquaticy import sandbox as werkstatt
    from aquaticy.messenger_login import qr_image

    if not session.ultra:
        return {"error": "Das gibt es nur mit einem Ultra-Konto."}, 403
    owner = session._owner

    def valid() -> bool:
        name, token, until = owner._qr_login
        return bool(token and until > time.monotonic() and payload.get("id") == name
                    and same_secret(str(payload.get("token") or ""), token))

    if payload.get("close") is True:
        with owner._qr_state_lock:
            if not valid():
                return {"error": "Die Anmeldung ist abgelaufen. Öffne sie erneut."}, 409
            owner._qr_login = ("", "", 0.0)
            return {"ok": True}, 200
    if not owner._qr_lock.acquire(blocking=False):
        return {"error": "Einen Moment …"}, 429
    try:
        with owner._qr_state_lock:
            if not valid():
                return {"error": "Die Anmeldung ist abgelaufen. Öffne sie erneut."}, 409
            name = owner._qr_login[0]
        settings = session.settings()
        if name not in ("whatsapp", "signal") or not addons.active(settings, name, session.ultra):
            return {"error": "Das Add-on ist nicht eingeschaltet."}, 403
        if workshop_busy(session):
            return {"error": "Ein Chat läuft gerade. Warte, bis er fertig ist."}, 409
        box = werkstatt.shared(settings)
        if not box.alive or not box.user_mode:
            return {"error": "Die virtual machine läuft gerade nicht."}, 409

        def windows() -> dict[str, Any]:
            result = box.desktop("windows", start=False, timeout=10)
            try:
                info = json.loads(result.stdout) if result.returncode == 0 else {}
            except ValueError:
                return {}
            return info if isinstance(info, dict) else {}

        def nichts(grund: str) -> tuple[dict[str, Any], int]:
            logging.getLogger("aquaticy.web").info("QR-Anmeldung %s: kein Bild (%s)", name, grund)
            return {"ok": True, "image": None, "reason": grund}, 200

        info = windows()
        window = next((w for w in info.get("fenster", []) if isinstance(w, dict)
                       and addons.messenger_of(str(w.get("klasse") or ""), "") == name), None)
        if window is None:
            return nichts("kein_fenster")
        wid = str(window.get("id") or "")
        if not re.fullmatch(r"0x[0-9a-fA-F]{1,10}", wid):
            return nichts("kein_fenster")
        if box.desktop("focus", wid, start=False, timeout=10).returncode != 0:
            return nichts("nicht_vorn")
        shot = box.screenshot(start=False, quality=92)
        after = windows()
        if not front_is_messenger(window, after, name):
            return nichts("nicht_vorn")
        if workshop_busy(session):
            return {"error": "Ein Chat läuft gerade. Warte, bis er fertig ist."}, 409
        image = qr_image(shot, name)
        with owner._qr_state_lock:
            if not valid():
                return {"error": "Die Anmeldung ist abgelaufen. Öffne sie erneut."}, 409
        if image is None:
            return nichts("kein_qr")
        return {"ok": True, "image": image}, 200
    except ImportError:
        return {"error": "Die QR-Erkennung fehlt. Aktualisiere Aquaticy und starte den "
                         "Server neu."}, 503
    except Exception:

        return {"error": "Der QR-Code lässt sich gerade nicht lesen. Versuch es erneut."}, 502
    finally:
        owner._qr_lock.release()



INPUT_KEYS = frozenset({
    "Return", "Tab", "BackSpace", "Escape", "Delete", "Up", "Down", "Left", "Right",
    "Home", "End", "Page_Up", "Page_Down", "ctrl+a", "ctrl+c", "ctrl+v", "ctrl+l", "shift+Tab",
    "F5",
})


MAX_INPUT_CHARS = 1000


def workshop_input(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Der Nutzer bedient die virtual machine selbst: klicken, tippen, Tasten.

    Das ist der Weg fuer Anmeldungen ("Login-Apps"): Passwoerter und Codes
    tippt der Mensch, nicht Aquaticy. Deshalb laeuft das bewusst NICHT durch
    die Pruefungen aus aquaticy/desktop.py -- die gelten fuer die KI. Und
    deshalb wird der Text nirgends abgelegt: nicht im Verlauf, nicht im
    Protokoll, nicht beim Modell. Er geht einmal an die virtual machine, fertig.
    """
    from aquaticy import sandbox as werkstatt
    from aquaticy.desktop import HEIGHT, WIDTH

    session = SESSION.current() if isinstance(SESSION, SessionProxy) else SESSION
    if not session.ultra:

        return {"ok": False, "error": "Der User mode gehört zu Ultra."}, 403
    settings = session.settings()
    if not getattr(settings, "vm_user_mode", False):
        return {"ok": False, "error": "Der User mode ist aus."}, 400
    box = werkstatt.shared(settings)
    art = str(payload.get("art") or "").strip().lower()
    if art == "open":


        from aquaticy.desktop import URL_RE

        adresse = str(payload.get("url") or "").strip()
        if not URL_RE.match(adresse) or len(adresse) > 2000:
            return {"ok": False, "error": "Bitte eine Adresse mit https:// (oder http://)."}, 400
        try:
            fertig = box.desktop("open", "browser", adresse, timeout=90)
        except Exception as exc:
            return {"ok": False, "error": f"Die virtual machine startet nicht: {exc}"}, 502
        if fertig.returncode != 0:
            return {"ok": False, "error": fertig.stderr.decode("utf-8", "replace")[:200]}, 400
        return {"ok": True}, 200
    if not box.alive or not box.user_mode:
        return {"ok": False, "error": "Es läuft gerade keine virtual machine im User mode."}, 404
    try:
        if art == "click":
            x, y = _json_int(payload.get("x")), _json_int(payload.get("y"))
            if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
                return {"ok": False, "error": "Die Stelle liegt nicht auf dem Bildschirm."}, 400
            args = ["click", str(x), str(y)]
            if payload.get("double") is True:
                args.append("--double")
            fertig = box.desktop(*args, timeout=20, start=False)
        elif art == "type":
            text = str(payload.get("text") or "")
            if not text or len(text) > MAX_INPUT_CHARS:
                return {"ok": False, "error": f"1 bis {MAX_INPUT_CHARS} Zeichen."}, 400
            fertig = box.desktop("type", stdin=text.encode("utf-8"), timeout=60, start=False)
        elif art == "key":
            taste = str(payload.get("key") or "")
            if taste not in INPUT_KEYS:
                return {"ok": False, "error": "Diese Taste gibt es hier nicht."}, 400
            fertig = box.desktop("key", taste, timeout=20, start=False)
        else:
            return {"ok": False, "error": "art: open, click, type oder key."}, 400
    except (TypeError, ValueError, OverflowError):
        return {"ok": False, "error": "x und y bitte als Zahlen."}, 400
    except Exception as exc:
        return {"ok": False,
                "error": f"Die virtual machine antwortet nicht: {type(exc).__name__}"}, 502
    if fertig.returncode != 0:
        meldung = fertig.stderr.decode("utf-8", "replace").strip()[:200]
        return {"ok": False, "error": meldung or "Das hat nicht geklappt."}, 400
    return {"ok": True}, 200


def _prune_uploads(folder: Path) -> None:
    """Laesst nur die juengsten Dateien liegen."""
    with contextlib.suppress(OSError):
        files = sorted(
            (item for item in folder.iterdir() if item.is_file()),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for old in files[KEEP_UPLOADS:]:
            with contextlib.suppress(OSError):
                old.unlink()


class TooLarge(ValueError):
    """Der Anfragekoerper sprengt die Grenze -- 413 statt 500."""


class BadRequest(ValueError):
    """Eine Anfrage, die so nicht gemeint sein kann -- 400 statt 500."""


def chat_markdown(title: str, entries: list[Any]) -> str:
    """Ein ganzer Chat als Markdown -- Frage als Ueberschrift, Antwort darunter.

    Markdown, weil die Antworten schon in Markdown geschrieben sind: jedes
    andere Format muesste sie umbauen und dabei etwas verlieren.
    """
    from datetime import datetime

    zeilen = [f"# {title or 'Chat'}", ""]
    for entry in entries:
        when = ""
        with contextlib.suppress(Exception):
            when = datetime.fromtimestamp(entry.created_at).strftime("%d.%m.%Y %H:%M")
        frage = " ".join(str(entry.question or "").split())
        zeilen += [f"## {frage or '(ohne Frage)'}", ""]
        if when:
            zeilen += [f"*{when}*", ""]
        zeilen += [str(entry.answer or "").strip(), ""]
    zeilen += ["---", "", "Aufgezeichnet von Aquaticy AI."]
    return "\n".join(zeilen)


def _design_style(design: dict[str, Any]) -> str:
    """Baut aus dem eigenen Design die CSS-Variablen fuer das <html>-Tag.

    Nur die Grundfarben -- den Rest (Kontrast der Knopfschrift, der helle
    Akzentton, die Schrift auf der Seitenleiste) rechnet das Skript beim
    Laden aus. Jede Farbe ist bereits geprueft (nur ``#rrggbb``), hier wird
    zur Sicherheit noch einmal auf genau dieses Muster geachtet.
    """
    import re as _re

    hexmuster = _re.compile(r"^#[0-9a-fA-F]{6}$")
    teile = []
    accent = str(design.get("accent") or "").strip().lower()
    bg = str(design.get("bg") or "").strip().lower()
    sidebar = str(design.get("sidebar") or "").strip().lower()
    if hexmuster.fullmatch(accent):
        teile += [f"--accent:{accent}", f"--accent-text:{accent}"]
    if hexmuster.fullmatch(bg):
        teile += [f"--bg:{bg}", f"--surface:{bg}"]
    if hexmuster.fullmatch(sidebar):
        teile += [f"--sidebar:{sidebar}"]
    return ";".join(teile)



_UI_CACHE: dict[str, Any] = {"entry": None}
_STATIC_CACHE: dict[str, bytes] = {}
_CACHE_LOCK = threading.Lock()


def ui_template() -> str:
    """Die Oberflaeche aus dem Speicher statt bei jedem Aufruf von der Platte (9.6.1).

    Neu gelesen wird nur, wenn sich die Datei geaendert hat -- wer an
    webui.html arbeitet, sieht seine Aenderung also weiterhin sofort.
    """
    try:
        stat = UI_FILE.stat()
        stempel = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        stempel = None
    with _CACHE_LOCK:
        eintrag = _UI_CACHE["entry"]
        if stempel is None or eintrag is None or eintrag[0] != (str(UI_FILE), stempel):
            eintrag = ((str(UI_FILE), stempel), UI_FILE.read_text(encoding="utf-8"))
            _UI_CACHE["entry"] = eintrag if stempel is not None else None
        return str(eintrag[1])


def _static_bytes(name: str) -> bytes:
    """Logo und Symbole -- einmal gelesen, danach aus dem Speicher (9.6.1)."""
    with _CACHE_LOCK:
        daten = _STATIC_CACHE.get(name)
    if daten is None:
        daten = (STATIC_DIR / name).read_bytes()
        with _CACHE_LOCK:
            _STATIC_CACHE[name] = daten
    return daten


def accepts_gzip(header: str) -> bool:
    """Nimmt der Browser gzip an? ("gzip;q=0" heisst ausdruecklich nein.)"""
    for teil in header.lower().split(","):
        name, _, rest = teil.strip().partition(";")
        if name.strip() in ("gzip", "*"):
            q = rest.strip()
            return not (q.startswith("q=") and q[2:].strip() in ("0", "0.0", "0.00", "0.000"))
    return False


def with_state(html: str, *, nonce: str = "") -> str:
    """Gibt der Seite den Zustand gleich mit auf den Weg.

    Zwei Gruende, das hier zu tun und nicht im Browser:

    * **Es blinkt nicht.** Wer das Erscheinungsbild erst per Skript setzt,
      sieht die Seite einen Wimpernschlag lang hell, bevor sie dunkel wird.
      Steht es im ausgelieferten HTML, ist sie von der ersten Zeile an
      richtig.
    * **Der Browser haelt nichts fest.** Er bekommt gesagt, was gilt. Was
      er selbst gespeichert haette, muesste man ihm glauben -- und das ist
      genau das, was hier nicht mehr passieren soll.
    """
    from aquaticy.uistate import defaults

    if AUTH is not None and getattr(SESSION.current(), "account", None) is None:



        stand = defaults()
    else:
        try:
            stand = ui_state().read()
        except Exception:  # pragma: no cover
            stand = defaults()

    attrs = ""
    if stand.get("theme") in ("light", "dark"):
        attrs += f' data-theme="{stand["theme"]}"'
    if stand.get("palette"):
        attrs += f' data-palette="{stand["palette"]}"'


    if stand.get("palette") == "custom":
        stil = _design_style(stand.get("design") or {})
        if stil:
            attrs += f' style="{stil}"'



    if stand.get("fontsize") in ("small", "large"):
        attrs += f' data-fontsize="{stand["fontsize"]}"'
    sprache = "en" if stand.get("lang") == "en" else "de"
    html = html.replace('<html lang="de">', f'<html lang="{sprache}"{attrs}>', 1)


    koerper = ["start"]
    if stand.get("mode") == "code":
        koerper.append("code-mode")
    if stand.get("mode") == "pro":
        koerper.append("pro-mode")
    if stand.get("tracing"):
        koerper.append("tracing")
    if stand.get("denken"):
        koerper.append("denken")
    html = html.replace('<body class="start">', f'<body class="{" ".join(koerper)}">', 1)





    roh = json.dumps(stand, ensure_ascii=False).replace("</", "<\\/")
    texte = json.dumps(webview.start_texts(), ensure_ascii=False).replace("</", "<\\/")
    boot = (
        f"window.__AQUATICY_STATE__ = {roh};"
        f"window.__AQUATICY_VERSION__ = {json.dumps(VERSION_LABEL)};"

        f"window.__AQUATICY_INTERNAL__ = {json.dumps(INTERNAL)};"

        f"window.__AQUATICY_TEXTS__ = {texte};"
    )
    marke = f' nonce="{nonce}"' if nonce else ""
    html = html.replace("<script>", f"<script{marke}>{boot}</script>\n<script{marke}>", 1)
    return html


def safe_name(name: str) -> str:
    """Macht aus einem hochgeladenen Namen einen, der gefahrlos auf die Platte darf.

    Der Name kommt vom Browser und damit von aussen: "../../.ssh/authorized_keys"
    waere sonst ein gueltiger Ablageort.
    """
    name = Path(name.replace("\\", "/")).name
    cleaned = "".join(
        character if character.isalnum() or character in "-_. " else "_" for character in name
    ).strip(". ")
    return cleaned[:80] or "datei"


def same_secret(candidate: str, secret: str) -> bool:
    """Zeitkonstanter Vergleich zweier Zugangswoerter.

    Ueber Bytes, nicht ueber str: `compare_digest` lehnt Zeichenketten mit
    Nicht-ASCII rundheraus ab. Ein Zugangswort wie "grün" haette damit jeden
    Vergleich zum Fehler gemacht -- auch den mit dem richtigen Wort.
    """
    return secrets.compare_digest(
        candidate.encode("utf-8", "surrogateescape"),
        secret.encode("utf-8", "surrogateescape"),
    )


class Handler(BaseHTTPRequestHandler):
    """Sehr kleiner Router -- eine Handvoll Endpunkte."""

    server_version = "Aquaticy"
    sys_version = ""

    _retry_after: int = 0

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(REQUEST_READ_TIMEOUT)

    def parse_request(self) -> bool:
        if not super().parse_request():
            return False
        try:
            urlsplit(self.path)

            self._body_length(MAX_BODY_BYTES * 2)
        except (BadRequest, TooLarge) as exc:
            self._reject_body(exc)
            return False
        except ValueError:
            self._reject_body(BadRequest("Ungültiger Anfragepfad."))
            return False
        return True

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def send_response(self, code: int, message: str | None = None) -> None:


        self.responded = True
        super().send_response(code, message)

    def end_headers(self) -> None:
        """Sicherheitskopfzeilen gelten fuer HTML, JSON, Downloads und SSE.

        XSS-Schutz (seit 9.5.18 strenger): Skripte laufen nur mit der Nonce
        dieser einen Antwort -- ein eingeschleustes ``<script>`` oder ein
        ``onerror=`` wird vom Browser nicht ausgefuehrt, selbst wenn es
        irgendwo durch die Maskierung rutschen sollte. Ohne Seite (JSON, SSE,
        Downloads) gibt es gar keine erlaubten Skripte.
        """
        nonce = getattr(self, "_csp_nonce", "")
        skripte = f"'self' 'nonce-{nonce}'" if nonce else "'none'"
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")


        self.send_header("Permissions-Policy", "camera=(), microphone=(self), geolocation=()")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        if self._https():

            self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            f"default-src 'self'; script-src {skripte}; script-src-attr 'none'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
            "connect-src 'self'; object-src 'none'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'",
        )
        super().end_headers()

    def _guarded(self, handler: Any) -> None:
        """Faengt alles ab, was in einer Route schiefgeht.

        Ohne das druckt die Standardbibliothek eine seitenlange Ablaufverfolgung
        in die Konsole, und der Browser bekommt gar nichts -- er versucht es
        dann immer wieder. Eine Zeile im Terminal und ein 500 sind brauchbarer.
        """
        self.responded = False
        self.__dict__.pop("_pending_headers", None)


        self._retry_after = 0
        route = self._route()
        client = self._client_ip()
        weitergereicht = bool(getattr(self, "_cluster_user", ""))



        gezaehlt = route not in STATIC_FILES and not weitergereicht
        if gezaehlt and not ADDRESS_LIMIT.allow(client):
            self._zu_viele(ADDRESS_LIMIT.retry_after(client))
            return
        account = self._account()

        schluessel = f"konto:{account.id}" if account is not None else f"ip:{client}"
        if gezaehlt and not REQUEST_LIMIT.allow(schluessel):
            self._zu_viele(REQUEST_LIMIT.retry_after(schluessel))
            return
        public = route in {
            "/",
            "/index.html",
            "/api/auth/status",
            "/api/consent",
            "/api/auth/register",
            "/api/auth/login",

            "/api/auth/challenge",


            "/api/auth/logout",
        }
        if AUTH is not None and route.startswith("/api/") and not public and account is None:
            self._json({"error": "Bitte melde dich an."}, 401)
            return
        if (self.command == "POST" and AIGUARD is not None and account is not None
                and route not in POST_WHEN_BANNED):



            sperre = AIGUARD.is_banned(user_id=account.id, ip=client)
            if sperre is not None:
                from aquaticy.aiguard import BANNED_MESSAGE, ban_info

                self._json({"error": BANNED_MESSAGE, "code": "banned",
                            "ban": ban_info(sperre)}, 403)
                return
        if account is not None and self._cluster_dispatch(route, account, weitergereicht):
            return
        previous = getattr(_REQUEST, "session", None)
        if account is not None:
            _REQUEST.session = SESSIONS.get(account)
        try:
            base = SESSION.current() if isinstance(SESSION, SessionProxy) else SESSION
            chat_route = route in {"/api/chat", "/api/chats", "/api/clear", "/api/open",
                                  "/api/run", "/api/runstate", "/api/stop", "/api/answer",
                                  "/api/command", "/api/chat-edit", "/api/chatexport"}
            _REQUEST.session = base.resolve_chat(
                self.headers.get("X-Aquaticy-Chat", "") if chat_route else "")
            handler()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except TimeoutError:
            self.close_connection = True
            if not self.responded:
                with contextlib.suppress(OSError):
                    self._json({"error": "Die Anfrage wurde nicht rechtzeitig übertragen."}, 408)
        except TooLarge as exc:
            if not self.responded:
                with contextlib.suppress(OSError):
                    self._json({"error": str(exc)}, 413)
        except BadRequest as exc:
            if not self.responded:
                with contextlib.suppress(OSError):
                    self._json({"error": str(exc)}, 400)
        except Exception as exc:


            print(f"  [Fehler] {self.command}: {type(exc).__name__}")
            if not self.responded:
                with contextlib.suppress(OSError):
                    self._error(500)
        finally:
            if previous is None:
                with contextlib.suppress(AttributeError):
                    del _REQUEST.session
            else:
                _REQUEST.session = previous


    def _cluster_dispatch(self, route: str, account: Account, weitergereicht: bool) -> bool:
        """Reicht die Anfrage an den Heimserver des Kontos weiter.

        Returns: True, wenn hier nichts mehr zu tun ist (weitergereicht oder
        abgewiesen); False, wenn dieser Server die Anfrage selbst bedient.
        """
        verbund = CLUSTER
        if verbund is None or not verbund.joined:
            return False
        if weitergereicht:
            if verbund.is_home(account.id):
                start_user_scheduler(account)
                return False

            body = b'{"error": "Bitte gleich noch einmal."}'
            self.send_response(409)
            self.send_header(cluster.MOVED_HEADER, "moved")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return True
        if (route in CLUSTER_LOCAL or route in STATIC_FILES or route in LEGAL_ROUTES
                or route.startswith("/cluster/")):
            return False


        if not self._authorized():
            self._deny()
            return True
        try:
            body = self._read_body(MAX_BODY_BYTES)
        except (BadRequest, TooLarge, TimeoutError) as exc:
            self._reject_body(exc)
            return True

        direkt = self._client_ip()
        try:
            if verbund.forward(self, account.id, body, self._https(), direkt):
                return True
            if not verbund.is_home(account.id):
                raise cluster.ClusterError("Dieses Konto hat einen anderen Heimserver.")
        except Exception as exc:  # pragma: no cover
            print(f"  [Verbund] Weiterleitung: {type(exc).__name__}: {exc}")
            if self.responded:
                self.close_connection = True
                return True
            if isinstance(exc, cluster.ForwardingError):
                self._json({"error": str(exc)}, 503)
                return True
            self._json({"error": "Der Heimserver ist gerade nicht erreichbar. "
                                 "Bitte versuche es später erneut."}, 503)
            return True

        self.rfile = io.BytesIO(body)
        return False

    def _cluster_route(self) -> None:
        """/cluster/... -- Aufrufe anderer Server, nicht des Browsers."""
        self.responded = False
        verbund = CLUSTER
        route = self._route()
        direkt = str(self.client_address[0] if self.client_address else "")
        if verbund is None or not verbund.enabled:
            self._json({"error": "Kein Verbund."}, 404)
            return
        if self.command == "GET" and route == "/cluster/info":
            if not CLUSTER_HELLO_LIMIT.allow(direkt):
                self._json({"error": "Zu viele Anfragen."}, 429)
                return
            self._json(verbund.beacon())
            return
        if self.command != "POST":
            self._json({"error": "unbekannter Pfad"}, 404)
            return
        if route == "/cluster/tunnel":
            self._cluster_tunnel(verbund, direkt)
            return
        grenze = MAX_BODY_BYTES * 2 if route == "/cluster/proxy" else 4 * cluster.CHUNK
        try:
            daten = self._read_body(grenze)
        except (BadRequest, TooLarge, TimeoutError) as exc:
            self._reject_body(exc)
            return
        try:
            if route == "/cluster/rpc":
                self._send(200, verbund.handle_rpc(daten, direkt), "application/octet-stream")
            elif route == "/cluster/proxy":
                self._cluster_proxy(verbund, daten, direkt)
            elif route in ("/cluster/hello", "/cluster/hello-status", "/cluster/hello-join"):

                if not CLUSTER_HELLO_LIMIT.allow(direkt):
                    self._json({"error": "Zu viele Anfragen."}, 429)
                    return
                try:
                    from aquaticy.jsonutil import JsonDepthError, loads

                    anfrage = loads(daten or b"{}")
                except (JsonDepthError, RecursionError) as exc:
                    raise BadRequest("Die Anfrage ist zu stark verschachtelt.") from exc
                except ValueError:
                    anfrage = {}
                if not isinstance(anfrage, dict):
                    anfrage = {}
                handler = {"/cluster/hello": verbund.handle_hello,
                           "/cluster/hello-status": verbund.hello_status,
                           "/cluster/hello-join": verbund.hello_join}[route]
                self._json(handler(anfrage, direkt))
            else:
                self._json({"error": "unbekannter Pfad"}, 404)
        except BadRequest as exc:
            self._reject_body(exc)
        except (cluster.ClusterError, ValueError, RecursionError, binascii.Error) as exc:
            if not self.responded:
                self._json({"error": str(exc) if isinstance(exc, cluster.ClusterError)
                            else "Ungültige Anfrage."}, 403)

    def _cluster_tunnel(self, verbund: Any, direkt: str) -> None:
        """Serverlast aufteilen: der Master will an den rpc-server dieses Servers.

        Die Verbindung wird selbst zum Tunnel (aquaticy/sharding.py) und bleibt
        offen, solange llama-server auf dem Master sie braucht.
        """
        from aquaticy import sharding

        try:
            daten = self._read_body(64 * 1024)
        except (BadRequest, TooLarge, TimeoutError) as exc:
            self._reject_body(exc)
            return
        try:
            port = SHARDING.rpc_port() if SHARDING is not None else 0
            sharding.serve_tunnel(self, verbund, port, daten, direkt)
        except (cluster.ClusterError, ValueError, RecursionError, binascii.Error,
                OSError) as exc:
            if not self.responded:
                with contextlib.suppress(OSError):
                    self._json({"error": str(exc) if isinstance(exc, cluster.ClusterError)
                                else "Kein Tunnel."}, 403)
            self.close_connection = True

    def _cluster_proxy(self, verbund: Any, daten: bytes, direkt: str) -> None:
        """Heimserver: bedient eine weitergereichte Anfrage wie eine eigene.

        Die ganze HTTP-Antwort -- Kopf und Inhalt, auch ein laufender Chat --
        geht verschluesselt in Stuecken zurueck; der Eingang schreibt sie
        unveraendert an den Browser.
        """
        from http.client import HTTPMessage

        anfrage, nonce, key = verbund.open_proxy(daten, direkt)
        salz = secrets.token_bytes(16)
        roh = self.wfile
        roh.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\n"
                  b"Cache-Control: no-store\r\nConnection: close\r\n"
                  b"X-Aquaticy-Salt: " + base64.b64encode(salz) + b"\r\n\r\n")
        roh.flush()
        self.responded = True
        strom = cluster.FrameWriter(roh, key, salz, f"stream:{nonce}")
        kopf = HTTPMessage()
        for eintrag in anfrage.get("h") or []:
            if isinstance(eintrag, list) and len(eintrag) == 2:
                kopf[str(eintrag[0])[:200]] = str(eintrag[1])[:8000]
        koerper = base64.b64decode(str(anfrage.get("b") or ""))
        kopf["Content-Length"] = str(len(koerper))
        methode = str(anfrage.get("m", "GET")).upper()
        ausfuehren = {"GET": self.do_GET, "POST": self.do_POST, "DELETE": self.do_DELETE,
                      "HEAD": self.do_HEAD}.get(methode)
        self.command, self.path, self.headers = methode, str(anfrage.get("p", "/")), kopf
        self.rfile = io.BytesIO(koerper)
        self.client_address = (str(anfrage.get("ip", "")), 0)
        self._cluster_user = str(anfrage["u"])
        self._cluster_https = bool(anfrage.get("https"))

        self.wfile = cast(Any, strom)
        try:
            if ausfuehren is None:
                self.send_response(405)
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                ausfuehren()
        finally:
            strom.end()
            self.wfile = roh
            self.close_connection = True


    def _queue_header(self, name: str, wert: str) -> None:
        """Eine Kopfzeile fuer die naechste Antwort (etwa ein Cookie, 9.6.9 Luna)."""
        if not isinstance(self.__dict__.get("_pending_headers"), list):
            self._pending_headers: list[tuple[str, str]] = []
        self._pending_headers.append((name, wert))

    def _flush_headers(self) -> None:
        for name, wert in self.__dict__.pop("_pending_headers", None) or ():
            self.send_header(name, wert)

    def _fetch_metadata_expected(self) -> bool:
        """Schickt ein Browser hier ``Sec-Fetch-*``? Bei https und localhost ja --
        bei http im Heimnetz nicht, dort zaehlt es fuer den Fingerabdruck nicht."""
        if self._https():
            return True
        host = (self.headers.get("Host") or "").strip().lower()
        name = host.split("]", 1)[0] + "]" if host.startswith("[") else host.rsplit(":", 1)[0]
        return (name in {"localhost", "[::1]"} or name.startswith("127.")
                or name.endswith(".localhost"))

    def _bot_keys(self, geraet: Any, neue_kennung: bool) -> tuple[str, ...]:
        """Woran ein Client fuer den Anmeldeschutz wiedererkannt wird: Adresse und,
        wenn er schon eine hat, seine Geraete-Kennung (nur als Hash)."""
        schluessel = [f"ip:{botguard.address_key(self._client_ip())}"]
        kennung = str(getattr(geraet, "cookie_hash", "") or "")
        if kennung and not neue_kennung:
            schluessel.append(f"dev:{kennung}")
        return tuple(schluessel)

    def _bot_gate(self, payload: dict[str, Any], geraet: Any, neue_kennung: bool) -> bool:
        """Die Risikozahl vor dem Passwort (12.0.0 Terra, aquaticy/botguard.py).

        Returns: True -- weiter zum Passwort. False -- schon beantwortet: mit
        einer Aufgabe "Bestaetige, dass du ein Mensch bist" (428) oder
        abgewiesen (429, ohne Passwortpruefung).
        """
        schluessel = self._bot_keys(geraet, neue_kennung)
        mensch = payload.get("human")
        mensch_ok = (isinstance(mensch, dict) and botguard.check(mensch, ("human",))
                     and botguard.human_track(mensch.get("track")))


        beweis_ok = mensch_ok or botguard.check(payload.get("proof"), ("visit",))
        skript = bool(botguard.fingerprint(self.headers, beweis_ok,
                                           payload.get("webdriver") is True,
                                           self._fetch_metadata_expected()))


        gesperrt = BOT_BANS.remaining(*schluessel[1:])
        if skript:
            gesperrt = max(gesperrt, BOT_BANS.remaining(schluessel[0]))
        if gesperrt:
            self._abgewiesen(gesperrt)
            return False
        neu = True
        if AUTH is not None:
            with contextlib.suppress(Exception):
                neu = not AUTH.seen_device_for_login(str(payload.get("email", "")), geraet)
        zahl = botguard.score(skript, BOT_FAILS.count(*schluessel), neu)
        urteil = botguard.verdict(zahl)
        if urteil == botguard.DROPPED:
            BOT_FAILS.add(*schluessel)
            BOT_BANS.ban(*schluessel)
            self._abgewiesen(botguard.BAN_SECONDS)
            return False
        if urteil == botguard.CHALLENGE and not mensch_ok:
            self._json({"ok": False, "challenge": botguard.issue("human"),
                        "error": "Bitte bestätige kurz, dass du ein Mensch bist."}, 428)
            return False
        return True

    def _abgewiesen(self, sekunden: int) -> None:
        """429 fuer einen abgewiesenen Client -- mit der Zeit, bis er es wieder darf."""
        self._retry_after = max(1, int(sekunden))
        minuten = max(1, math.ceil(sekunden / 60))
        wann = "einer Minute" if minuten == 1 else f"{minuten} Minuten"
        self._json({"ok": False, "code": "dropped",
                    "error": "Zu viele verdächtige Anmeldeversuche von hier. Versuch es in "
                             f"{wann} noch einmal."}, 429)

    def _zu_viele(self, sekunden: int) -> None:
        """429 mit ``Retry-After``: die Seite wartet so lange und fragt dann noch einmal."""
        self._retry_after = max(1, min(int(sekunden or 1), 60))
        self._json({"error": "Zu viele Anfragen. Bitte warte kurz."}, 429)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if status == 429 and self._retry_after:
            self.send_header("Retry-After", str(self._retry_after))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._flush_headers()
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        if isinstance(payload, dict) and isinstance(payload.get("error"), str):


            payload = {**payload, "error": scrub_error(payload["error"])}


            payload["error"] = (GENERIC_ERROR if status >= 500
                                else public_error(payload["error"]))
        self._send(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json")

    def _wants_page(self) -> bool:
        """Ruft ein Mensch die Adresse im Browser auf (statt die Seite per Skript)?"""
        route = self._route()
        return (self.command in ("GET", "HEAD") and not route.startswith(("/api/", "/cluster/"))
                and "text/html" in (self.headers.get("Accept") or ""))

    def _error(self, status: int, message: str = "") -> None:
        """Fehler als Seite fuer den Browser oder als JSON fuer die Oberflaeche."""
        if self._wants_page():
            body = error_page(status)
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        self._json({"error": message or GENERIC_ERROR}, status)

    def _json_cookie(
        self, payload: dict[str, Any], name: str, value: str, max_age: int, status: int = 200,
        extra: tuple[tuple[str, str, int], ...] = (),
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")



        for extra_name, extra_value, extra_age in extra:
            self._set_cookie(extra_name, extra_value, extra_age)
        self._set_cookie(name, value, max_age)
        self.end_headers()
        self.wfile.write(body)

    def _route(self) -> str:
        """Pfad ohne Query -- `/?token=...` ist immer noch die Startseite."""
        return urlsplit(self.path).path

    def _query_token(self) -> str:
        return (parse_qs(urlsplit(self.path).query).get("token") or [""])[0]

    def _cookie_token(self) -> str:
        raw = self.headers.get("Cookie") or ""
        with contextlib.suppress(Exception):
            cookie = SimpleCookie(raw)
            if TOKEN_COOKIE in cookie:
                return cookie[TOKEN_COOKIE].value
        return ""

    def _cookie(self, name: str) -> str:
        raw = self.headers.get("Cookie") or ""
        with contextlib.suppress(Exception):
            cookie = SimpleCookie(raw)
            if name in cookie:
                return cookie[name].value
        return ""

    def _client_ip(self) -> str:
        direkt = str(self.client_address[0] if self.client_address else "unknown")
        return client_ip(direkt, self.headers.get("X-Forwarded-For") or "",
                         self.headers.get("X-Real-IP") or "")

    def _device(self) -> str:
        return "\x1f".join(
            (
                self.headers.get("User-Agent") or "unbekannt",
                self.headers.get("Accept-Language") or "",
            )
        )[:1000]

    def _account(self) -> Account | None:
        if AUTH is None:
            return None
        if getattr(self, "_cluster_user", ""):


            return AUTH.account(self._cluster_user)
        return AUTH.session_account(self._cookie(AUTH_COOKIE), self._device(),
                                    self._client_ip())

    def _ban_view(self, account: Any) -> dict[str, Any]:
        """Die Sperre eines Kontos fuer die Oberflaeche (9.5.24) -- oder {banned: False}."""
        if AIGUARD is None or account is None:
            return {"banned": False}
        from aquaticy.aiguard import ban_info

        try:
            return ban_info(AIGUARD.is_banned(user_id=str(getattr(account, "id", "")),
                                              ip=self._client_ip()))
        except Exception:
            return {"banned": False}

    def _origin_ok(self) -> bool:



        herkunft = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if herkunft in {"cross-site", "same-site"}:
            return False
        origin = (self.headers.get("Origin") or "").strip()
        if not origin:
            return True
        try:
            parsed = urlsplit(origin)
        except ValueError:
            return False
        return parsed.scheme in {"http", "https"} and parsed.netloc == (
            self.headers.get("Host") or ""
        )

    def _https(self) -> bool:
        """Laeuft die Verbindung verschluesselt -- direkt oder hinter einem
        eingetragenen Proxy, der "X-Forwarded-Proto: https" meldet (9.5.22)?"""
        if getattr(self, "_cluster_user", ""):
            return bool(getattr(self, "_cluster_https", False))
        if isinstance(self.connection, __import__("ssl").SSLSocket):
            return True
        import ipaddress

        direkt = str(self.client_address[0] if self.client_address else "")
        try:
            quelle = ipaddress.ip_address(direkt.split("%", 1)[0])
        except ValueError:
            return False
        if not any(quelle in netz for netz in trusted_proxies()):
            return False
        return (self.headers.get("X-Forwarded-Proto") or "").strip().lower() == "https"

    def _set_cookie(self, name: str, value: str, max_age: int) -> None:


        secure = "; Secure" if self._https() else ""
        self.send_header(
            "Set-Cookie",
            f"{name}={value}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict{secure}",
        )

    def _authorized(self) -> bool:
        """Prueft das Zugangswort -- aus Adresse, Cookie oder Kopfzeile.

        Ohne gesetztes TOKEN ist alles erlaubt; so bleibt der rein lokale
        Betrieb genauso einfach wie vorher.
        """
        if not TOKEN or bool(getattr(self, "_cluster_user", "")):
            return True
        return any(
            candidate and same_secret(candidate, TOKEN)
            for candidate in (
                self._query_token(),
                self._cookie_token(),
                self.headers.get("X-Aquaticy-Token") or "",
            )
        )

    def _deny(self) -> None:
        body = DENIED_PAGE.encode()
        self.send_response(401)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _reject_body(self, exc: Exception) -> None:
        self.close_connection = True
        if isinstance(exc, TimeoutError):
            self._json({"error": "Die Anfrage wurde nicht rechtzeitig übertragen."}, 408)
        else:
            self._json({"error": str(exc)}, 413 if isinstance(exc, TooLarge) else 400)

    def _body_length(self, limit: int) -> int:
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get_all("Transfer-Encoding") or len(lengths) > 1:
            raise BadRequest("Mehrdeutige Länge der Anfrage.")
        roh = (lengths[0] if lengths else "0").strip()
        if not re.fullmatch(r"[0-9]{1,12}", roh):
            raise BadRequest("Ungültige Länge der Anfrage.")
        length = int(roh)
        if length > limit:
            raise TooLarge("Anfrage zu gross.")
        return length

    def _read_body(self, limit: int) -> bytes:
        length = self._body_length(limit)
        data = self.rfile.read(length) if length else b""
        if len(data) != length:
            raise BadRequest("Die Anfrage wurde nicht vollständig übertragen.")
        return data

    def _read_json(self, limit: int = 0) -> dict[str, Any]:
        """Liest den JSON-Koerper. *limit*: kleinere Obergrenze fuer diese Route."""
        data = self._read_body(min(limit or MAX_BODY_BYTES, MAX_BODY_BYTES))
        from aquaticy.jsonutil import JsonDepthError, loads

        try:
            gelesen = loads(data or b"{}")
        except (JsonDepthError, RecursionError) as exc:
            raise BadRequest("Die Anfrage ist zu stark verschachtelt.") from exc
        except (json.JSONDecodeError, ValueError):
            return {}




        return gelesen if isinstance(gelesen, dict) else {}



    def _nur_heimnetz(self) -> bool:
        """Mit eigener Domain (11.1) gilt dieser Eingang nur fuer Heimnetz, Tailscale
        und den Rechner selbst. Von aussen geht es ueber die Domain -- verschluesselt.

        Ohne diese Grenze waere Aquaticy auf einem Server mit oeffentlicher Adresse
        (etwa einem gemieteten) unverschluesselt aus dem Internet erreichbar.

        Returns: True, wenn die Anfrage abgewiesen wurde.
        """
        seite = WEBSITE
        if (not LAN_ONLY or seite is None or getattr(self, "public_entry", False)
                or getattr(self, "_cluster_user", "")):
            return False
        direkt = str(self.client_address[0] if self.client_address else "")
        if cluster.lan_ip_ok(direkt):
            return False
        adresse = f"https://{seite.config.domain}/"
        text = f"Von außen ist Aquaticy unter {adresse} erreichbar.".encode()
        self.send_response(403)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(text)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(text)
        self.close_connection = True
        return True

    def do_GET(self) -> None:
        if self._nur_heimnetz():
            return
        if self._route().startswith("/cluster/") and not getattr(self, "_cluster_user", ""):
            self._cluster_route()
            return
        self._guarded(self._get)

    def do_POST(self) -> None:
        if self._nur_heimnetz():
            return
        if self._route().startswith("/cluster/") and not getattr(self, "_cluster_user", ""):
            self._cluster_route()
            return
        self._guarded(self._post)

    def do_DELETE(self) -> None:
        if self._nur_heimnetz():
            return
        self._guarded(self._delete)

    def do_HEAD(self) -> None:
        """HEAD nur fuer das Logo (9.6.0) -- alles andere bleibt 405."""
        if self._nur_heimnetz():
            return
        if self._route() in STATIC_FILES:
            self._guarded(lambda: self._send_static(self._route()))
            return
        self.send_response(405)
        self.send_header("Allow", "GET, POST, DELETE")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _delete(self) -> None:
        """Loeschen ist ein eigenes Verb -- ein POST "loeschAlles" waere gelogen."""
        if not self._authorized():
            self._deny()
            return
        if not self._origin_ok():
            self._json({"error": "Die Herkunft der Anfrage stimmt nicht."}, 403)
            return
        route = self._route()
        settings = SESSION.settings()
        if route == "/api/coworkers":
            value = (parse_qs(urlsplit(self.path).query).get("id") or [""])[0]
            response, status = coworker_action({"action": "delete", "id": value}, self._account())
            self._json(response, status)
        elif route == "/api/memory":
            frage = parse_qs(urlsplit(self.path).query)
            if not settings.memory_enabled:
                self._json({"error": "Der Speicher ist abgeschaltet."}, 400)
                return
            store = SESSION.memory()
            eintrag = (frage.get("id") or [""])[0].strip()
            if not eintrag:
                self._json({"forgotten": store.clear()})
                return


            try:
                nummer = int(eintrag)
            except ValueError:
                self._json({"error": "Keine gültige Kennung."}, 400)
                return
            self._json({"forgotten": bool(store.forget(nummer))})
        else:
            self._json({"error": "unbekannt"}, 404)

    def _workshop_file(self) -> None:
        """Reicht eine Datei aus der virtual machine heraus -- zum Herunterladen."""
        from aquaticy import sandbox as werkstatt

        wanted = (parse_qs(urlsplit(self.path).query).get("path") or [""])[0]
        box = werkstatt.shared(SESSION.settings())
        if not box.alive:
            self._json({"error": "Die virtual machine läuft gerade nicht."}, 404)
            return
        try:
            data = box.get_bytes(wanted)
        except FileNotFoundError as exc:
            self._json({"error": str(exc)}, 404)
            return
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
            return
        except Exception as exc:  # pragma: no cover
            self._json({"error": f"Die virtual machine antwortet nicht: {exc}"}, 502)
            return
        name = safe_name(wanted.rsplit("/", 1)[-1] or "datei")
        self.send_response(200)


        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _workshop_screen(self) -> None:
        """Der Bildschirm der virtual machine im User mode -- so, wie Aquaticy ihn sieht.

        Startet nichts: laeuft keine virtual machine, gibt es auch kein Bild. Ein
        Blick hinein soll keine Maschine hochfahren.
        """
        from aquaticy import sandbox as werkstatt

        box = werkstatt.shared(SESSION.settings())
        if not box.alive or not box.user_mode:
            if "leise=1" in self.path:


                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self._json({"error": "Es läuft gerade keine virtual machine im User mode."}, 404)
            return
        try:
            data = box.screenshot(start=False)
        except Exception as exc:  # pragma: no cover
            self._json({"error": f"Kein Bildschirmfoto bekommen: {exc}"}, 502)
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _send_static(self, route: str) -> None:
        """Eine feste Datei aus aquaticy/static -- mit Zwischenspeicher im Browser."""
        try:
            daten = _static_bytes(STATIC_FILES[route])
        except OSError:
            self._json({"error": "nicht gefunden"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(daten)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(daten)

    def _get(self) -> None:


        if self._route() in STATIC_FILES:
            self._send_static(self._route())
            return



        ruecksprung = self._route() == "/google" and bool(self._cookie(GOOGLE_FLOW_COOKIE))
        if not ruecksprung and not self._authorized():
            self._deny()
            return
        route = self._route()
        if route in ("/", "/index.html"):
            self._send_ui()
        elif route in LEGAL_ROUTES:
            self._send(200, legal_page(route), "text/html; charset=utf-8")
        elif route == "/api/cluster":
            verbund, status = cluster_view(SESSION.current())
            self._json(verbund, status)
        elif route == "/api/linked":
            self._json(linked_view(SESSION.current()))
        elif route == "/api/upgrades":
            self._json(upgrades_view(SESSION.current()))
        elif route == "/api/auth/status":
            account = self._account()
            self._json(
                {
                    "consent": self._cookie(CONSENT_COOKIE) == "yes",
                    "learning_version": LEGAL_VERSION,
                    "authenticated": account is not None,
                    "account": (
                        {"email": account.email, "username": account.username,
                         "plan": account.plan} if account else None
                    ),
                }
            )
        elif route == "/api/auth/challenge":


            self._json(botguard.issue("visit"))
        elif route == "/api/learning":
            from aquaticy.learning import Learning

            self._json(Learning(SESSION.settings().data_dir).status())
        elif route == "/api/media":
            query = parse_qs(urlsplit(self.path).query)
            media_id = (query.get("id") or [""])[0].strip()
            if media_id:
                from aquaticy.media import load_snapshot

                gespeichert = load_snapshot(SESSION.settings().data_dir, media_id)
                if gespeichert is None:
                    self._json({"error": "Dieses Bild ist nicht mehr vorhanden."}, 404)
                    return
                data, mime = gespeichert
                self._send(200, data, mime)
                return
            target = (query.get("url") or [""])[0].strip()
            if not target or len(target) > 8_000:
                self._json({"error": "Keine gültige Bildadresse."}, 400)
                return
            status, inhalt, art = media_by_url(SESSION.settings(), target)
            if status != 200:
                self._json({"error": inhalt.decode("utf-8")}, status)
                return
            self._send(200, inhalt, art)
        elif route == "/api/account":
            account = self._account()
            if account is None:
                self._json({"error": "Bitte melde dich an."}, 401)
                return


            self._json(
                {
                    "email": account.email,
                    "username": account.username,
                    "plan": account.plan,
                    "pro": account.elevated,
                    "ultra": account.ultra,
                    "plan_label": account.plan_label,
                    "usage": usage_view(SESSION.settings()),

                    "ban": self._ban_view(account),

                    "security_notices": [
                        e for e in (AUTH.events(account.id, unseen_only=True)
                                    if AUTH is not None else [])
                        if e["kind"] == "neues-geraet"],
                }
            )
        elif route == "/api/account/security":


            account = self._account()
            if account is None or AUTH is None:
                self._json({"error": "Bitte melde dich an."}, 401)
                return
            self._json({
                "devices": AUTH.devices(account.id),
                "last_address": AUTH.last_address(account.id),
                "sessions": AUTH.session_count(account.id),
                "events": AUTH.events(account.id),
            })
        elif route == "/google":
            self._google_return()
        elif route == "/api/config":
            settings = SESSION.settings()
            self._json(
                {
                    "version": __version__,
                    "version_label": VERSION_LABEL,
                    "account": (
                        {
                            "email": SESSION.account.email,
                            "username": SESSION.account.username,
                            "plan": SESSION.plan,


                            "plan_label": SESSION.account.plan_label,
                            "pro": SESSION.pro,
                            "ultra": SESSION.ultra,
                            "ban": self._ban_view(SESSION.account),
                        }
                        if SESSION.account is not None
                        else {"email": "lokal", "username": "", "plan": "ultra",
                              "plan_label": "Ultra", "pro": True, "ultra": True}
                    ),
                    "values": current_values(),
                    "key_name": api_key_name_for(settings.model),
                    "search_key_name": SEARCH_BACKEND_KEYS.get(settings.search_backend, ""),
                    "env_path": str(settings.env_path or DEFAULT_ENV_PATH),
                    "problems": settings.missing_requirements(),

                    "ha_connected": bool(settings.ha_url and settings.ha_token),
                    "search_key_set": bool(settings.search_api_key),




                    "strong_model": (strong_models(1) or [{}])[0].get("id", ""),


                    "strong_code_model": (
                        strong_models(1, purpose="code") or [{}]
                    )[0].get("id", ""),
                    "google": google_state(settings),
                    "legal_rules": rules_overview(),

                    "header": header_for(settings),
                    "providers": webview.provider_view(),

                    "own_models": own_models(settings),
                }
            )
        elif route == "/api/header":

            self._json(header_for(SESSION.settings()))
        elif route == "/api/run":
            self._run_stream()
        elif route == "/api/runstate":
            self._run_state()
        elif route == "/api/chats":
            settings = SESSION.settings()
            cache = Cache(settings.db_path, settings.cache_ttl_hours)


            suche = (parse_qs(urlsplit(self.path).query).get("q") or [""])[0].strip()
            chats = cache.search_chats(suche, limit=40) if suche else cache.recent_chats(limit=40)
            for session in SESSION.chat_sessions():
                book = session.runs if session.account is not None or (
                    session._owner._chat_sessions) else RUNS
                run = book.latest()
                if run is not None and not run.done:
                    chat_id = session.chat_id()
                    found = next((c for c in chats if c["session_id"] == chat_id), None)
                    if found is not None:
                        found["running"] = True
                    elif not suche or suche.casefold() in run.question.casefold():
                        chats.insert(0, {"session_id": chat_id, "title": run.question,
                                         "turns": 0, "touched": run.started, "running": True})
            self._json(
                {

                    "chats": webview.with_groups(
                        chats
                    ),
                    "query": suche,
                    "current": SESSION.chat_id(),
                }
            )
        elif route == "/api/chatexport":



            settings = SESSION.settings()
            cache = Cache(settings.db_path, settings.cache_ttl_hours)
            wanted = (parse_qs(urlsplit(self.path).query).get("session_id") or [""])[0].strip()
            entries = cache.chat_history(wanted) if wanted else []
            if not entries:
                self._json({"error": "Diesen Chat gibt es nicht."}, 404)
                return
            je_chat = {chat["session_id"]: chat for chat in cache.recent_chats(limit=200)}
            title = str(je_chat.get(wanted, {}).get("title") or entries[0].question).strip()
            self._json({"title": title, "markdown": chat_markdown(title, entries),
                        "filename": webview.export_filename(title)})
        elif route == "/api/werkstatt":


            from aquaticy import sandbox as werkstatt

            box = werkstatt.shared(SESSION.settings())
            self._json(
                {
                    "running": bool(box.alive),
                    "status": box.status(),
                    "usage_gb": box.usage_gb() if box.alive else 0.0,
                    "disk_gb": box.disk_gb,
                    "files": [
                        {**datei, "size_text": webview.size_text(datei.get("bytes"))}
                        for datei in (box.list_files() if box.alive else [])
                    ],
                }
            )
        elif route == "/api/werkstatt/datei":
            self._workshop_file()
        elif route == "/api/addons":
            self._json(addons_view(SESSION.current() if isinstance(SESSION, SessionProxy)
                                   else SESSION))
        elif route == "/api/context":

            einstellungen = SESSION.settings()
            gewuenscht = (parse_qs(urlsplit(self.path).query).get("model") or [""])[0].strip()
            modell = gewuenscht if _MODELL_RE.fullmatch(gewuenscht) else einstellungen.model
            konto = self._account()
            obergrenze = (max(int(get_settings().context_tokens or 0), NORMAL_CONTEXT_CAP)
                          if konto is not None and not SESSION.ultra else 0)
            self._json(context_view(einstellungen, modell, obergrenze))
        elif route == "/api/vm":



            from aquaticy import sandbox as werkstatt

            einstellungen = SESSION.settings()
            laufzeit = None
            with contextlib.suppress(Exception):
                laufzeit = werkstatt.runtime_cached()
            self._json({
                "internet": bool(getattr(einstellungen, "vm_internet", False)),
                "lan": bool(getattr(einstellungen, "vm_lan", False)),
                "ultra": bool(SESSION.ultra),
                "runtime": laufzeit is not None,
            })
        elif route == "/api/plugins":

            from aquaticy import plugins as plugin_mod

            self._json({"commands": plugin_mod.commands(SESSION.settings(), SESSION.ultra)})
        elif route == "/api/coworkers":


            nur = (parse_qs(urlsplit(self.path).query).get("badge") or [""])[0] == "1"
            sitzung = SESSION.current() if isinstance(SESSION, SessionProxy) else SESSION
            self._json(coworkers_view(sitzung, badge_only=nur))
        elif route == "/api/werkstatt/bildschirm":
            self._workshop_screen()
        elif route == "/api/prefs":
            self._json(ui_state().read())
        elif route == "/api/models":
            from aquaticy.system import available_models



            frage = parse_qs(urlsplit(self.path).query)
            zweck = (frage.get("purpose") or [""])[0].strip()
            modus = (frage.get("mode") or [""])[0].strip()
            from aquaticy.linked import picker_models

            alle = available_models(SESSION.settings())

            verknuepft = []
            with contextlib.suppress(Exception):
                verknuepft = picker_models(SESSION.settings())
            gesehen = {m.get("id") for m in alle}
            alle = alle + [m for m in verknuepft if m["id"] not in gesehen]
            if SHARDING is not None and SHARDING.ready():

                alle = [{"id": SPLIT_MODEL_ID, "label": SHARDING.label(), "kind": "Verbund",
                         "note": f"Verteilt auf {SHARDING.servers()} Server",
                         "source": "operator", "source_label": ""}] + [
                    m for m in alle if m.get("id") != SPLIT_MODEL_ID]
            if UPGRADE_DIR is not None:


                from aquaticy import upgrading

                current = SESSION.current() if isinstance(SESSION, SessionProxy) else SESSION
                alle = upgrading.picker_entries(UPGRADE_DIR, alle, bool(current.ultra))
            antwort: dict[str, Any] = {
                "models": alle,

                "strong": strong_models(3, purpose=zweck) + verknuepft,
            }
            if modus:



                antwort["picker"] = webview.picker_view(
                    modus, alle,
                    strong_models(3, purpose="code" if modus == "code" else "") + verknuepft,
                    limited=SESSION.settings().quota is not None,
                )
            self._json(antwort)
        elif route == "/api/memory":

            if not SESSION.settings().memory_enabled:
                self._json({"enabled": False, "entries": []})
            else:
                store = SESSION.memory()
                self._json(
                    {
                        "enabled": True,
                        "usage": storage_view(store.usage()),
                        "entries": [
                            {**eintrag, "when_text": webview.date_text(eintrag.get("when"))}
                            for eintrag in (e.as_dict() for e in store.all_entries(limit=300))
                        ],
                    }
                )
        elif route == "/api/usage":
            from aquaticy.usage import UsageLog, summary_view

            settings = SESSION.settings()



            self._json({
                "limits": usage_view(settings),
                "stats": (
                    summary_view(UsageLog(settings.db_path).summary())
                    if settings.quota is None else None
                ),
            })
        elif route == "/api/system":



            if not SESSION.ultra:
                self._json({"error": "Die Auslastungsanzeige gibt es nur mit Ultra."}, 403)
                return
            from aquaticy.system import snapshot

            settings = SESSION.settings()
            payload = snapshot(settings.data_dir)


            if settings.memory_enabled:
                payload["storage"] = storage_view(SESSION.memory().usage())
            payload["gauges"] = system_gauges(payload)
            if CLUSTER is not None and CLUSTER.joined:

                with contextlib.suppress(Exception):
                    payload["cluster"] = cluster_gauges(CLUSTER)
            self._json(payload)
        elif route == "/api/notes":
            settings = SESSION.settings()
            cache = Cache(settings.db_path, settings.cache_ttl_hours)
            self._json({"notes": [{"id": n.id, "text": n.text} for n in cache.list_notes()]})
        elif route == "/api/history":
            settings = SESSION.settings()
            cache = Cache(settings.db_path, settings.cache_ttl_hours)
            self._json(
                {
                    "history": [
                        {"question": entry.question, "answer": entry.answer}
                        for entry in cache.recent_history(limit=20)
                    ]
                }
            )
        else:
            self._error(404, "unbekannter Pfad")

    def _post(self) -> None:
        if not self._authorized():
            self._deny()
            return
        route = self._route()
        if not self._origin_ok():
            self._json({"error": "Die Herkunft der Anfrage stimmt nicht."}, 403)
            return
        if route == "/api/consent":
            accepted = self._read_json(limit=AUTH_BODY_BYTES).get("accepted") is True
            if not accepted:
                self._json_cookie(
                    {"ok": False, "leave": True}, CONSENT_COOKIE, "", 0, status=403
                )
                return
            self._json_cookie({"ok": True}, CONSENT_COOKIE, "yes", 365 * 86400)
        elif route in {"/api/auth/register", "/api/auth/login"}:
            if AUTH is None:
                self._json({"error": "Die Kontoverwaltung ist nicht gestartet."}, 503)
                return
            if self._cookie(CONSENT_COOKIE) != "yes":
                self._json({"error": "Bitte bestätige zuerst den Datenschutzhinweis."}, 403)
                return
            if not AUTH_LIMIT.allow(self._client_ip()):
                self._json({"error": "Zu viele Anmeldeversuche. Bitte warte eine Minute."}, 429)
                return
            payload = self._read_json(limit=AUTH_BODY_BYTES)


            from aquaticy.devices import (
                DEVICE_COOKIE,
                DEVICE_COOKIE_AGE,
                clean_device,
                new_device_token,
                token_hash,
            )

            geraete_kennung = self._cookie(DEVICE_COOKIE)
            neue_kennung = not token_hash(geraete_kennung)
            if neue_kennung:
                geraete_kennung = new_device_token()
            geraet = clean_device(
                payload.get("device"),
                user_agent=self.headers.get("User-Agent") or "",
                accept_language=self.headers.get("Accept-Language") or "",



                cookie=geraete_kennung,
            )
            if route.endswith("register"):
                if not str(payload.get("username", "")).strip():
                    self._json({"ok": False, "error": "Bitte wähle einen Nutzernamen."}, 400)
                    return
                if payload.get("terms_accepted") is not True:
                    self._json(
                        {
                            "ok": False,
                            "error": (
                                "Bitte stimme den Datenschutz- und "
                                "Nutzungsbedingungen ausdrücklich zu."
                            ),
                        },
                        400,
                    )
                    return


                if AIGUARD is not None:
                    from aquaticy.aiguard import BANNED_MESSAGE



                    if AIGUARD.is_banned(ip=self._client_ip(),
                                         device=geraet.cookie_hash) is not None:
                        self._json({"ok": False, "error": BANNED_MESSAGE, "code": "banned"},
                                   403)
                        return
                try:
                    account: Account | None = AUTH.register(
                        str(payload.get("email", "")),
                        str(payload.get("password", "")),
                        str(payload.get("plan", "normal")),
                        str(payload.get("pro_code", "")),
                        username=str(payload.get("username", "")),
                        terms_accepted=True,
                        terms_version=LEGAL_VERSION,
                        ip=self._client_ip(),
                        device=geraet,
                    )
                except ValueError as exc:
                    self._json({"ok": False, "error": str(exc)}, 400)
                    return
            else:


                if not self._bot_gate(payload, geraet, neue_kennung):
                    return
                konto_schluessel = "login:" + str(payload.get("email", "")).strip().lower()
                if LOGIN_FAILS.full(konto_schluessel):
                    self._json({"ok": False, "error": (
                        "Zu viele falsche Passwörter für dieses Konto. Bitte warte "
                        "eine Viertelstunde.")}, 429)
                    return
                account = AUTH.authenticate(
                    str(payload.get("email", "")), str(payload.get("password", ""))
                )
                if account is None:
                    LOGIN_FAILS.allow(konto_schluessel)
                    BOT_FAILS.add(*self._bot_keys(geraet, neue_kennung))
                    self._json({"ok": False, "error": "E-Mail oder Passwort stimmt nicht."}, 401)
                    return



            if AIGUARD is not None:
                from aquaticy.aiguard import BANNED_MESSAGE

                if AIGUARD.is_banned(ip=self._client_ip()) is not None:
                    self._json({"ok": False, "error": BANNED_MESSAGE, "code": "banned"}, 403)
                    return
            if account is None:  # pragma: no cover
                self._json({"ok": False, "error": "E-Mail oder Passwort stimmt nicht."}, 401)
                return
            try:
                token = AUTH.create_session(account, self._device(), self._client_ip())
            except ValueError:
                self._json({"ok": False, "error": "E-Mail oder Passwort stimmt nicht."}, 401)
                return
            AUTH.note_seen(account.id, self._client_ip())



            if not route.endswith("register"):
                with contextlib.suppress(Exception):
                    if not AUTH.is_known_device(account.id, geraet):
                        AUTH.add_event(account.id, "neues-geraet",
                                       f"Anmeldung mit {geraet.browser} auf "
                                       f"{geraet.hardware.split(' · ')[0]}")


            with contextlib.suppress(Exception):
                AUTH.note_device(account.id, geraet)
            with contextlib.suppress(Exception):
                start_user_scheduler(account)
            if (payload.get("learning_accepted") is True
                    and payload.get("learning_version") == LEGAL_VERSION
                    and (AIGUARD is None or AIGUARD.is_banned(
                        user_id=account.id, ip=self._client_ip()) is None)):
                from aquaticy.learning import Learning

                Learning(AUTH.profile_dir(account.id)).set_consent(True, LEGAL_VERSION)
            self._json_cookie(
                {"ok": True, "account": {"email": account.email,
                  "username": account.username, "plan": account.plan}},
                AUTH_COOKIE,
                token,
                30 * 86400,
                extra=((DEVICE_COOKIE, geraete_kennung, DEVICE_COOKIE_AGE),)
                if neue_kennung else (),
            )
        elif route == "/api/auth/logout":
            if AUTH is not None:
                AUTH.logout(self._cookie(AUTH_COOKIE))
            self._json_cookie({"ok": True}, AUTH_COOKIE, "", 0)
        elif route in ACCOUNT_ROUTES:
            self._account_action(route, self._read_json(limit=AUTH_BODY_BYTES))
        elif route == "/api/cluster":
            antwort, status = cluster_action(SESSION.current(),
                                             self._read_json(limit=AUTH_BODY_BYTES))
            self._json(antwort, status)
        elif route == "/api/linked":
            antwort, status = linked_action(self._read_json(limit=AUTH_BODY_BYTES))
            self._json(antwort, status)
        elif route == "/api/upgrades":
            antwort, status = upgrades_action(SESSION.current(),
                                              self._read_json(limit=AUTH_BODY_BYTES))
            self._json(antwort, status)
        elif route == "/api/learning":
            from aquaticy.learning import Learning

            payload = self._read_json(limit=AUTH_BODY_BYTES)
            account = self._account()
            if (payload.get("enabled") is True and AIGUARD is not None
                    and account is not None and AIGUARD.is_banned(
                        user_id=account.id, ip=self._client_ip()) is not None):
                self._json({"error": "Solange dein Konto gesperrt ist, kannst du Gemeinsames "
                            "Lernen nur ausschalten."}, 403)
                return
            try:
                state = Learning(SESSION.settings().data_dir).set_consent(
                    payload.get("enabled"), str(payload.get("version", "")))
            except ValueError as exc:
                self._json({"error": str(exc)}, 400)
                return
            self._json({"ok": True, **state})
        elif route == "/api/chat":
            self._chat()
        elif route == "/api/clear":
            selected, _ = SESSION.switch_chat()
            self._json({"ok": True, "current": selected.chat_id()})
        elif route == "/api/open":
            wanted = str(self._read_json().get("session_id", "")).strip()
            if not wanted:
                self._json({"ok": False, "error": "keine Chat-Kennung"}, 400)
                return

            with contextlib.suppress(Exception):
                settings = SESSION.settings()
                Cache(settings.db_path, settings.cache_ttl_hours).clear_unread(wanted)
            selected, data = SESSION.switch_chat(wanted)
            self._json({"ok": True, **data, "session_id": selected.chat_id()})
        elif route == "/api/ha":
            if not SESSION.ultra:
                self._json({"ok": False, "error": "Home Assistant gibt es nur mit Ultra."},
                           403)
                return
            self._json(self._ha_probe(self._read_json()))
        elif route == "/api/probe":
            self._json(self._probe(self._read_json()))
        elif route == "/api/google":
            self._json(self._google(self._read_json()))
        elif route == "/api/storage":
            if not SESSION.ultra:
                self._json({"ok": False,
                            "error": "Die Lagerverwaltung gibt es nur mit Ultra."}, 403)
                return
            self._json(self._storage_probe(self._read_json()))
        elif route == "/api/addons":
            antwort, status = addon_action(self._read_json())
            self._json(antwort, status)
        elif route == "/api/addons/qr":
            antwort, status = addon_qr(SESSION.current(), self._read_json(limit=AUTH_BODY_BYTES))
            self._json(antwort, status)
        elif route == "/api/werkstatt/eingabe":
            antwort, status = workshop_input(self._read_json())
            self._json(antwort, status)
        elif route == "/api/chat-edit":
            self._json(self._chat_edit(self._read_json()))
        elif route == "/api/coworkers":
            antwort, status = coworker_action(self._read_json(), self._account())
            self._json(antwort, status)
        elif route == "/api/prefs":


            self._json(ui_state().write(self._read_json()))
        elif route == "/api/stop":
            self._json({"ok": SESSION.stop()})
        elif route == "/api/answer":
            text = str(self._read_json().get("text", "")).strip()[:MAX_MESSAGE_CHARS]


            konto = self._account()
            aktueller = SESSION.current() if isinstance(SESSION, SessionProxy) else SESSION
            if (AIGUARD is not None and konto is not None
                    and self._aiguard_text(konto, text, aktueller.chat_id(),
                                           previous_user_message(aktueller))):

                with contextlib.suppress(Exception):
                    SESSION.stop()
                return
            self._json({"ok": SESSION.answer(text)})
        elif route == "/api/command":
            line = str(self._read_json().get("line", "")).strip()
            if not line.startswith("/"):
                self._json({"ok": False, "error": "kein Befehl"}, 400)
                return
            try:
                self._json({"ok": True, **SESSION.command(line)})
            except Exception as exc:
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        elif route == "/api/config":
            try:
                written = save_values(self._read_json())
            except ValueError as exc:


                self._json({"ok": False, "error": str(exc)}, 400)
                return
            except Exception as exc:
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
                return



            forget_strong_models(SESSION.settings().data_dir)

            del written
            self._json({"ok": True})
        else:
            self._json({"error": "unbekannter Pfad"}, 404)

    def _google_return(self) -> None:
        """Der Rueckweg von Google -- hier landet der Nutzer nach der Zustimmung.

        Sitzt der Browser auf demselben Rechner, ist die Anmeldung damit
        fertig; er sieht eine Seite mit dem Ergebnis. Sitzt er woanders,
        kommt er hier nie an -- dann kopiert er die Adresse in das Feld in
        den Einstellungen, was auf denselben Tausch hinauslaeuft.
        """
        from urllib.parse import parse_qs, urlparse

        from aquaticy.google import GoogleError, exchange_code

        query = parse_qs(urlparse(self.path).query)
        denied = query.get("error", [""])[0]
        code = query.get("code", [""])[0]
        state = query.get("state", [""])[0]
        if denied:
            self._google_page(False, f"Google hat abgelehnt: {denied}")
            return
        if not code:
            self._google_page(False, "Google hat keinen Code mitgeschickt.")
            return



        konto = self._account()
        abgelaufen = ("Diese Rückmeldung von Google gehört zu keiner Anmeldung, die du "
                      "hier begonnen hast (oder sie ist abgelaufen). Bitte in den "
                      "Einstellungen neu verbinden.")
        if konto is not None or (AUTH is None and self._authorized()):
            if not google_state_take(state, getattr(konto, "id", "") or ""):
                self._google_page(False, abgelaufen)
                return
        elif AUTH is None:


            if google_state_take_browser(state, self._cookie(GOOGLE_FLOW_COOKIE)) is None:
                self._google_page(False, abgelaufen)
                return
        else:



            kennung = google_state_take_browser(state, self._cookie(GOOGLE_FLOW_COOKIE))
            konto = AUTH.account(kennung) if kennung else None
            if konto is None:
                self._google_page(False, "Bitte melde dich zuerst bei Aquaticy an und "
                                         "verbinde Google dann aus den Einstellungen.")
                return
            _REQUEST.session = SESSIONS.get(konto)
        self._queue_header(
            "Set-Cookie", f"{GOOGLE_FLOW_COOKIE}=; Path=/google; Max-Age=0; HttpOnly; "
                          "SameSite=Lax")
        settings = SESSION.settings()
        if not settings.google_client_id or not settings.google_client_secret:
            self._google_page(False, "Client-ID und Client-Secret fehlen. Trag beides in "
                                     "den Einstellungen ein und verbinde neu.")
            return
        client = google_client(settings)
        try:
            tokens = exchange_code(
                settings.google_client_id,
                settings.google_client_secret,
                code,
                google_redirect(self.headers.get("Host", "")),
            )
            client.remember(tokens)
            account = client.account()
        except GoogleError as exc:
            self._google_page(False, str(exc))
            return
        finally:
            client.close()
        self._google_page(True, f"Verbunden{f' als {account}' if account else ''}."
                          + google_write_gap(settings, tokens))

    def _google_page(self, ok: bool, message: str) -> None:
        """Eine schlichte Seite als Rueckmeldung -- ohne Skript, ohne Ballast."""
        if not ok:
            message = public_error(scrub_error(message))
        colour = "#2f6f4e" if ok else "#a4342b"
        title = "Geschafft" if ok else "Das hat nicht geklappt"
        body = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Aquaticy AI</title>
<link rel="icon" type="image/png" href="/favicon-32.png">
<style>body{{font:15px/1.6 system-ui,sans-serif;margin:0;display:grid;place-items:center;
min-height:100vh;background:#faf9f6;color:#26241f}}
main{{max-width:30em;padding:32px;text-align:center}}
h1{{color:{colour};font-size:20px;margin:0 0 12px}}
p{{margin:0 0 8px;color:#57534a}}</style></head><body><main>
<h1>{title}</h1><p>{escape(message)}</p>
<p>Du kannst dieses Fenster schliessen und zu Aquaticy AI zurueckgehen.</p>
</main></body></html>"""
        raw = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self._flush_headers()
        self.end_headers()
        self.wfile.write(raw)

    def _aiguard_text(self, konto: Any, text: str, chat: str, previous: str = "") -> bool:
        """Chatsperre, Beleidigungen und Auftraege zum Herabsetzen (Ai-guard).

        *previous*: die Nachricht davor im selben Chat -- ein Zitat dort und
        "gib mir was Fieseres zurueck" jetzt sind zusammen ein Auftrag (9.5.28).

        Returns: True, wenn die Anfrage damit schon beantwortet ist (403).
        """
        from aquaticy.aiguard import (
            BANNED_MESSAGE,
            DEMEANING_REASON,
            ban_info,
            chat_locked_message,
            demeaning_request,
            insult_level,
        )


        grund = AIGUARD.chat_locked(konto.id, chat)
        if grund:
            self._json({"error": chat_locked_message(grund), "code": "chat_locked"}, 403)
            return True



        stufe, eigener_grund, detail = insult_level(text), "", "Beleidigung (erkannt)"
        if not stufe:
            stufe = demeaning_request(text, previous)
            eigener_grund, detail = DEMEANING_REASON, DEMEANING_REASON
        if not stufe:
            return False
        massnahme = AIGUARD.record_incident(
            konto.id, "beleidigung", stufe, chat=chat, detail=detail,
            enforce=not getattr(konto, "ultra", False), reason=eigener_grund)
        if massnahme.kind == "ban":
            self._json({"error": BANNED_MESSAGE, "code": "banned",
                        "ban": ban_info(AIGUARD.is_banned(user_id=konto.id))}, 403)
            return True
        if massnahme.kind == "chat":
            self._json({"error": chat_locked_message(massnahme.reason),
                        "code": "chat_locked"}, 403)
            return True
        return False

    def _chat_edit(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Benennt einen Chat um oder loescht ihn."""
        session_id = str(payload.get("session_id", "")).strip()
        action = str(payload.get("action", "")).strip()
        if not session_id:
            return {"ok": False, "error": "keine Chat-Kennung"}
        settings = SESSION.settings()
        cache = Cache(settings.db_path, settings.cache_ttl_hours)
        if action == "rename":


            titel = payload.get("title")
            return {"ok": True, "title": cache.rename_chat(
                session_id, titel if isinstance(titel, str) else "")}
        if action == "delete":
            if any(s.chat_id() == session_id and s.has_running_chat()
                    for s in SESSION.chat_sessions()):


                return {"ok": False, "error": "Dieser Chat antwortet gerade. "
                        "Bitte erst stoppen, dann löschen.", "code": "busy"}
            removed = cache.delete_chat(session_id)


            SESSION.forget_chat(session_id)
            return {"ok": True, "removed": removed}
        return {"ok": False, "error": f"unbekannte Aktion '{action}'"}

    def _storage_probe(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Sucht die Lagerverwaltung im Netz oder testet eine eingetippte Adresse."""
        from aquaticy.storage import Storage, StorageError, discover

        settings = SESSION.settings()
        url = str(payload.get("url", "")).strip()
        if not url:
            found = discover(settings.lan_subnet)
            if not found:
                return {
                    "ok": False,
                    "error": (
                        "Nichts gefunden. Läuft die Lagerverwaltung? Sonst die Adresse "
                        "von Hand eintragen, z.B. 192.168.1.5:3000."
                    ),
                }
            return {"ok": True, "url": found[0], "found": found}

        from aquaticy.storage import normalize_url

        if not normalize_url(url):
            return {"ok": False, "error": "Die Adresse ist ungültig."}

        client = Storage(url, access="read")
        try:
            info = client.info()
            rooms = client.rooms()
        except StorageError as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            client.close()
        items = sum(int(room.get("itemCount") or 0) for room in rooms)
        return {
            "ok": True,
            "url": client.url,
            "name": str(info.get("name") or "Lagerverwaltung"),
            "version": str(info.get("version") or ""),
            "rooms": len(rooms),
            "items": items,
        }

    def _google(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Verbindet, trennt oder meldet den Stand des Google-Kontos.

        Der Ablauf hat zwei Schritte, weil Google dazwischen den Nutzer fragt:
        `start` liefert die Adresse zum Zustimmen, `finish` nimmt den Code
        entgegen, den Google zurueckgibt.
        """
        from aquaticy.google import GoogleError, consent_url, exchange_code

        action = str(payload.get("action", "state")).strip()
        settings = SESSION.settings()
        redirect = google_redirect(self.headers.get("Host", ""))

        if action == "start":



            darf_aendern = payload.get("write")
            if darf_aendern is None:
                darf_aendern = settings.google_write




            neu: dict[str, Any] = {}
            client_id = str(payload.get("client_id", "")).strip()
            if client_id and client_id != settings.google_client_id:
                neu[GOOGLE_ID_FIELD] = client_id
            secret = str(payload.get("client_secret", "")).strip()
            if secret:
                neu[GOOGLE_SECRET_FIELD] = secret
            if neu:


                neu["AQUATICY_GOOGLE"] = "true"
                neu["AQUATICY_GOOGLE_WRITE"] = "true" if darf_aendern else "false"
                try:
                    save_values(neu)
                except ValueError as exc:
                    return {"ok": False, "error": str(exc)}
                settings = SESSION.settings()
            if not settings.google_client_id or not settings.google_client_secret:
                return {"ok": False, "error": (
                    "Trag erst Client-ID und Client-Secret ein. Dann klick auf „Verbinden“. "
                    "Ohne beides kann Google die Anmeldung nicht abschließen.")}
            client_id = settings.google_client_id
            try:
                browser = secrets.token_urlsafe(32)
                state = google_state_new(getattr(SESSION.account, "id", "") or "", browser)
                self._queue_header(
                    "Set-Cookie",
                    f"{GOOGLE_FLOW_COOKIE}={browser}; Path=/google; "
                    f"Max-Age={int(GOOGLE_STATE_SECONDS)}; HttpOnly; SameSite=Lax"
                    + ("; Secure" if self._https() else ""))
                return {
                    "ok": True,
                    "url": consent_url(client_id, redirect, state,
                                       write=bool(darf_aendern)),
                    "redirect": redirect,
                    "write": bool(darf_aendern),
                    "state": state,
                }
            except GoogleError as exc:
                return {"ok": False, "error": str(exc)}

        if action == "finish":
            eingefuegt = str(payload.get("code", ""))


            state = (parse_qs(urlsplit(eingefuegt.strip()).query).get("state") or [""])[0] \
                if "state=" in eingefuegt else str(payload.get("state", ""))
            if not google_state_take(state, getattr(SESSION.account, "id", "") or ""):
                return {"ok": False, "error": (
                    "Dieser Code gehört zu keiner Anmeldung, die du hier begonnen hast (oder "
                    "sie ist abgelaufen). Bitte auf „Mit Google verbinden“ klicken und neu "
                    "zustimmen.")}
            if not settings.google_client_id or not settings.google_client_secret:
                return {
                    "ok": False,
                    "error": (
                        "Trag erst Client-ID und Client-Secret ein. Dann klick auf "
                        "„Verbinden“. Ohne beides kann Google den Code nicht einlösen."
                    ),
                }
            client = google_client(settings)
            try:
                tokens = exchange_code(
                    settings.google_client_id,
                    settings.google_client_secret,
                    str(payload.get("code", "")),
                    redirect,
                )
                client.remember(tokens)
                return {"ok": True, **google_state(SESSION.settings())}
            except GoogleError as exc:
                return {"ok": False, "error": str(exc)}
            finally:
                client.close()

        if action == "disconnect":
            client = google_client(settings)
            try:
                client.disconnect()
            finally:
                client.close()
            return {"ok": True, **google_state(SESSION.settings())}

        return {"ok": True, **google_state(settings), "redirect": redirect}

    def _probe(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Testet Modell und Suchmaschine -- dasselbe, was `aquaticy setup` macht.

        Geprueft werden Modell und Adresse aus dem Formular, mit dem
        Schluessel, der dafuer hinterlegt ist. Schluessel selbst nimmt das
        Formular seit 12.0.0 Luna nicht mehr an -- die kommen ueber Add-ons.
        """
        from aquaticy.config import NO_KEY
        from aquaticy.keyvault import scrub
        from aquaticy.probe import check_llm, check_search

        settings = SESSION.settings()
        konto = SESSION.account is not None
        model = fix_model_id(str(payload.get("AQUATICY_MODEL", "")).strip()) or settings.model
        api_base = str(payload.get("AQUATICY_API_BASE", settings.api_base) or "").strip()
        if not SESSION.ultra:


            api_base = settings.api_base
        if api_base and not base_fits(api_base, model):


            api_base = ""
        des_betreibers = get_settings().api_base or ""




        vorschau = replace(
            settings, model=model, api_base=api_base,
            own_api_base=(api_base if konto and SESSION.ultra and api_base
                          and api_base != des_betreibers else ""),
        )
        quelle = vorschau.key_source(model)
        weg = vorschau.llm_kwargs_for(model)
        api_key = str(weg.get("api_key") or "")
        api_base = str(weg.get("api_base") or "")
        if not konto and api_base and api_base not in {settings.api_base or "",
                                                       des_betreibers}:




            api_key = NO_KEY

        backend = str(payload.get("AQUATICY_SEARCH_BACKEND", "")).strip() or settings.search_backend


        search_key = settings.search_key_for(backend)
        engines = str(payload.get("AQUATICY_SEARCH_ENGINES", settings.search_engines) or "").strip()
        instance = str(payload.get("AQUATICY_SEARXNG_URL", settings.searxng_url) or "").strip()
        if not SESSION.ultra:
            instance = settings.searxng_url



        kontingent = settings.quota if quelle != "own" else None
        try:


            from aquaticy.pace import own_gate
            from aquaticy.probe import PROBE_QUESTION, PROBE_TOKENS
            from aquaticy.usage import tokens



            if kontingent is not None:
                kontingent.reserve(tokens(PROBE_QUESTION) + PROBE_TOKENS, model)
            llm_ok, llm_msg = check_llm(model, api_key, api_base,
                                        pace_key=own_gate(api_key) if quelle == "own" else "")
        except Exception as exc:
            llm_ok, llm_msg = False, str(exc)
        search_ok, search_msg = check_search(backend, search_key, engines, instance)

        geheim = [api_key, search_key, *settings.secrets()]
        return {
            "ok": llm_ok and search_ok,
            "llm": {"ok": llm_ok, "message": scrub(llm_msg, geheim), "model": model},
            "search": {"ok": search_ok, "message": scrub(search_msg, geheim),
                       "backend": backend},
        }

    def _ha_probe(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Sucht eine Instanz oder testet die eingetragenen Angaben.

        Damit klappt die Einrichtung in der Oberflaeche genauso wie mit
        `aquaticy connect-ha`: Knopf druecken, Adresse steht da, Token einfuegen,
        Knopf druecken, fertig.
        """
        from aquaticy.homeassistant import HomeAssistant, HomeAssistantError, discover

        if payload.get("action") == "discover":
            try:
                return {"ok": True, "found": discover()}
            except Exception as exc:
                return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        from aquaticy.homeassistant import normalize_url

        settings = SESSION.settings()
        url = str(payload.get("url") or settings.ha_url).strip()
        eingetippt = str(payload.get("token") or "").strip()
        token = eingetippt or settings.ha_token
        if (not eingetippt and settings.ha_token and settings.ha_url
                and normalize_url(url) != normalize_url(settings.ha_url)):



            return {"ok": False, "error": (
                "Für eine neue Adresse bitte den Token dazu eintragen — der "
                "gespeicherte geht nur an die gespeicherte Adresse."
            )}
        if not url or not token:
            return {"ok": False, "error": "Bitte trag die Adresse und den Zugangsschlüssel ein."}
        if not normalize_url(url):
            return {"ok": False, "error": "Die Adresse ist ungültig."}
        client = HomeAssistant(url, token)
        try:
            hello = client.ping()
            counts = client.domains()
        except HomeAssistantError as exc:
            return {"ok": False, "error": str(exc)}
        gespeichert = False
        if payload.get("save") and (eingetippt or normalize_url(url)
                                    != normalize_url(settings.ha_url)):



            neu = {"AQUATICY_HA_URL": client.url}
            if eingetippt:
                neu[HA_TOKEN_FIELD] = eingetippt
            try:
                save_values(neu)
            except ValueError as exc:
                return {"ok": False, "error": str(exc)}
            gespeichert = True
        return {
            "ok": True,
            "name": hello,
            "url": client.url,
            "entities": sum(counts.values()),
            "domains": counts,
            "saved": gespeichert,

            "control": bool(SESSION.settings().ha_control),
        }

    def _send_ui(self) -> None:
        """Liefert die Oberflaeche und legt das Zugangswort als Cookie ab.

        So braucht nur der erste Aufruf die lange Adresse; danach kennt der
        Browser das Wort von selbst.
        """
        _warm_up_once()
        self._csp_nonce = secrets.token_urlsafe(18)
        body = with_state(ui_template(), nonce=self._csp_nonce).encode("utf-8")


        gepackt = accepts_gzip(self.headers.get("Accept-Encoding") or "")
        if gepackt:
            body = gzip.compress(body, compresslevel=5)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if gepackt:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Cache-Control", "no-store")
        if TOKEN:
            self._set_cookie(TOKEN_COOKIE, TOKEN, 30 * 86400)
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, text: str) -> bool:
        """Schreibt ein Stueck in den Ereignisstrom. `False` = niemand mehr da.

        Bricht die Verbindung ab -- Tab zu, Seite neu geladen, Handy im
        Standby -- läuft der Auftrag weiter. Ein Lauf gehört der Sitzung,
        nicht der einzelnen HTTP-Verbindung; das Ergebnis bleibt danach als
        Chat erhalten und kann auf einem anderen Gerät geöffnet werden.
        """
        try:
            self.wfile.write(text.encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False
        return True

    def _account_action(self, route: str, payload: dict[str, Any]) -> None:
        """Das eigene Konto verwalten (9.5.32).

        Daten loeschen, Konto loeschen und das Passwort aendern gehen nur mit
        dem Passwort -- eine offene Sitzung auf einem fremden Rechner soll
        dafuer nicht reichen. Fehlversuche zaehlen wie bei der Anmeldung.
        """
        konto = self._account()
        if AUTH is None or konto is None:
            self._json({"ok": False, "error": "Bitte melde dich an."}, 401)
            return
        token = self._cookie(AUTH_COOKIE)
        if route == "/api/account/events-seen":
            AUTH.mark_events_seen(konto.id)
            self._json({"ok": True})
            return
        if route == "/api/account/logout-all":
            self._json({"ok": True, "ended": AUTH.logout_others(konto.id, token)})
            return
        schluessel = "konto:" + konto.id
        if LOGIN_FAILS.full(schluessel):
            self._json({"ok": False, "error": (
                "Zu viele falsche Passwörter. Bitte warte eine Viertelstunde.")}, 429)
            return
        passwort = str(payload.get("password") or "")
        if route == "/api/account/password":
            try:
                AUTH.change_password(konto, passwort, str(payload.get("new_password") or ""),
                                     token)
            except ValueError as exc:
                if "bisherige" in str(exc):
                    LOGIN_FAILS.allow(schluessel)
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            self._json({"ok": True})
            return
        verified = AUTH.authenticate(konto.email, passwort) if 0 < len(passwort) <= 128 else None
        if verified is None or verified.id != konto.id:
            LOGIN_FAILS.allow(schluessel)
            self._json({"ok": False, "error": "Das Passwort stimmt nicht."}, 403)
            return


        konto = verified
        if route == "/api/account/delete" and (
                str(payload.get("confirm") or "").strip().upper() != DELETE_WORD):
            self._json({"ok": False, "error": f"Tippe zur Bestätigung {DELETE_WORD} ein."},
                       400)
            return
        forget_account_runtime(konto)
        if route == "/api/account/wipe":
            try:
                AUTH.wipe_data(konto)
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 409)
                return


            with contextlib.suppress(Exception):
                start_user_scheduler(konto)
            self._json({"ok": True})
            return



        if AIGUARD is not None:
            sperre = AIGUARD.is_banned(user_id=konto.id)
            if sperre is not None:
                for keks in AUTH.device_cookie_hashes(konto.id):
                    AIGUARD.ban_device(keks, reason=sperre.reason, until=sperre.until)


                with contextlib.suppress(Exception):
                    adresse = AUTH.last_address(konto.id)
                    if adresse:
                        AIGUARD.ban_ip(adresse, reason=sperre.reason, by="konto-geloescht",
                                       until=sperre.until)
        try:
            AUTH.remove_account(konto)
        except ValueError as exc:
            self._json({"ok": False, "error": str(exc)}, 409)
            return
        self._json_cookie({"ok": True, "deleted": True}, AUTH_COOKIE, "", 0)

    def _chat(self) -> None:
        """Fuehrt die Anfrage aus und streamt die Ereignisse als SSE."""
        kontingent = SESSION.settings().quota



        eigenes_modell = SESSION.settings().key_source(SESSION.settings().model) == "own"
        if kontingent is not None and not eigenes_modell:
            from aquaticy.quota import QuotaExceeded

            try:
                kontingent.check()
            except QuotaExceeded as exc:


                self._json(
                    {"error": str(exc), "code": "quota", "which": exc.which,
                     "usage": usage_view(SESSION.settings())},
                    429,
                )
                return
        payload = self._read_json()
        message = str(payload.get("message", "")).strip()[:MAX_MESSAGE_CHARS]
        raw = payload.get("attachments")
        attachments = (
            [item for item in raw if isinstance(item, dict)][:MAX_UPLOADS]
            if isinstance(raw, list)
            else []
        )
        if any(blocked_upload(str(item.get("name") or "")) for item in attachments):
            self._json({"error": BLOCKED_UPLOAD_MESSAGE, "code": "blocked_upload"}, 400)
            return












        wunsch = {
            name: payload[name]
            for name in (
                "mode", "effort", "structured", "recheck", "online", "sandbox", "agents",
                "visual_sources"
            )
            if name in payload
        }
        if "structured" not in wunsch and "thinking" in payload:
            wunsch["structured"] = payload["thinking"]

        if payload.get("image_mode") not in (None, False):
            self._json({"error": "Diesen Modus gibt es nicht mehr."}, 400)
            return




        from aquaticy.uistate import clean as clean_state

        gewuenscht = str(clean_state(wunsch, base=ui_state().read())["mode"])
        if gewuenscht == "code":
            wunsch.pop("online", None)
            wunsch.pop("visual_sources", None)
        stand = ui_state().write(wunsch) if wunsch else ui_state().read()
        mode = str(stand["mode"])
        effort = str(stand["effort"])
        structured = bool(stand["structured"])
        recheck = bool(stand["recheck"])
        online = bool(stand["online"])
        sandbox = bool(stand["sandbox"])
        agents = int(stand.get("agents", 12))
        visual_sources = bool(stand.get("visual_sources", False))
        agents = max(1, min(50 if mode == "pro" else 12, agents))





        if mode == "code":
            online = True
            visual_sources = False




        vm_switch = False
        if mode == "code" and sandbox:
            konto_vorab = self._account()
            if (konto_vorab is not None and not getattr(konto_vorab, "ultra", False)):
                from aquaticy.aiguard import security_topic

                if security_topic(message):
                    mode, sandbox, online, vm_switch = "normal", False, True, True
                    with contextlib.suppress(Exception):
                        ui_state().write({"mode": "normal", "sandbox": False})
        if visual_sources and not selected_vision_model(SESSION.settings()):
            self._json(
                {"error": "Webcams und Satellitenbilder brauchen ein bildfähiges "
                 "Hauptmodell oder ein Vision-Modell unter Chat → Modelle und Verbindungen."}, 400
            )
            return
        if not message and not attachments:
            self._json({"error": "leere Nachricht"}, 400)
            return
        if not message:

            message = "Sieh dir das Angehängte an und sag mir, worum es geht."




        konto = self._account()
        if konto is not None and AUTH is not None:
            AUTH.note_seen(konto.id, self._client_ip())
        if AIGUARD is not None and konto is not None:
            gesperrt = AIGUARD.is_banned(user_id=konto.id, ip=self._client_ip())
            if gesperrt is not None:
                from aquaticy.aiguard import BANNED_MESSAGE, ban_info

                self._json({"error": BANNED_MESSAGE, "code": "banned",
                            "ban": ban_info(gesperrt)}, 403)
                return
            aktueller = SESSION.current() if isinstance(SESSION, SessionProxy) else SESSION
            if self._aiguard_text(konto, message, aktueller.chat_id(),
                                  previous_user_message(aktueller)):
                return



        session = SESSION.current() if isinstance(SESSION, SessionProxy) else SESSION
        session.chat_id()
        try:
            lauf = current_runs().start(message)
        except RunCapacityError as exc:
            self._json({"error": str(exc), "code": "busy"}, 429)
            return
        if session.chat_id():
            lauf.chat = session.chat_id()
            lauf.add({"type": "chat", "session_id": session.chat_id()})
        if vm_switch:


            from aquaticy.aiguard import VM_SWITCH_MESSAGE

            lauf.add({"type": "mode_switch", "mode": "normal", "text": VM_SWITCH_MESSAGE})
        if kontingent is not None:


            kontingent.begin()
        seen_done = threading.Event()


        geheim = session.settings().secrets()

        def emit(name: str, payload: dict[str, Any]) -> None:



            kind = "chunk" if name == "answer_chunk" else name
            if geheim and kind not in ("chunk", "thought"):
                payload = scrub_payload(payload, geheim)
            if kind == "error":


                technisch = str(payload.get("message", ""))
                oeffentlich = public_error(technisch)
                if oeffentlich != " ".join(technisch.split()):



                    print(f"  [Fehler] {scrub_error(technisch, geheim)[:300]}", flush=True)
                payload = {**payload, "message": oeffentlich}
            if AIGUARD is not None and konto is not None and kind == "abuse":






                with contextlib.suppress(Exception):
                    massnahme = AIGUARD.record_incident(
                        konto.id, str(payload.get("art") or ""),
                        payload.get("schwere") or 0,
                        chat=session.chat_id(), detail=str(payload.get("art") or ""),
                        enforce=not getattr(konto, "ultra", False), text=message)
                    if massnahme.kind == "ban":
                        lauf.add({"type": "banned"})
                    elif massnahme.kind == "chat":
                        lauf.add({"type": "chat_locked"})
            if kind == "done":
                seen_done.set()


                payload = {**payload, "visuals": [
                    {**v, "captured_text": webview.iso_moment_text(v.get("captured_at"))}
                    if isinstance(v, dict) and v.get("captured_at") else v
                    for v in payload.get("visuals") or []
                ]} if payload.get("visuals") else payload
            lauf.add({"type": kind, **payload})

        def run() -> None:
            previous = getattr(_REQUEST, "session", None)
            _REQUEST.session = session
            try:




                if (AIGUARD is not None and konto is not None
                        and not session.settings().legal_guard):
                    from aquaticy.aiguard import check_message

                    verdaechtig, grund = check_message(
                        AIGUARD, konto, message, session.settings(),
                        chat=session.chat_id())
                    if verdaechtig:
                        lauf.add({"type": "chunk", "text": grund})
                        lauf.add({"type": "banned"})
                        lauf.add({"type": "done"})
                        seen_done.set()
                        return
                SESSION.ask(
                    message,
                    emit,
                    attachments,
                    mode=mode,
                    structured=structured,
                    recheck=recheck,
                    effort=effort,
                    online=online,
                    sandbox=sandbox,
                    agents=agents,
                    visual_sources=visual_sources,
                )
            except Exception as exc:



                meldung = user_hint(exc)
                if meldung != GENERIC_ERROR:
                    meldung = public_error(scrub_error(meldung, geheim))
                else:
                    print(f"  [Fehler] Chat: {type(exc).__name__}")
                lauf.add({"type": "error", "message": meldung})
            finally:


                if not seen_done.is_set():
                    lauf.add({"type": "done"})
                lauf.finish()
                if previous is None:
                    with contextlib.suppress(AttributeError):
                        del _REQUEST.session
                else:
                    _REQUEST.session = previous

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        self._stream_run(lauf, since=0)

    def _run_stream(self) -> None:
        """Haengt sich an einen Turn -- genau den mit dieser Kennung (seit 9.5.15)."""
        frage = parse_qs(urlsplit(self.path).query)
        kennung = (frage.get("id") or [""])[0]
        lauf = current_runs().get(kennung) if kennung else current_runs().latest()
        if lauf is None:
            self._json({"error": "kein Lauf"}, 404)
            return
        roh = (frage.get("since") or ["0"])[0]
        try:
            since = max(0, int(roh))
        except (TypeError, ValueError):
            since = 0
        self._stream_run(lauf, since=since)

    def _run_state(self) -> None:
        """Was gerade laeuft -- fuer die Seite, die eben geladen wurde."""
        lauf = current_runs().latest()
        self._json(lauf.state() if lauf is not None else {"running": False, "resume": False})

    def _stream_run(self, lauf: Run, since: int = 0) -> None:
        """Schickt die Ereignisse eines Laufs als SSE, ab *since*."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")


        self.send_header("Connection", "close")
        self.end_headers()



        self._sse(": los\n\n")

        stand = since
        while True:
            neue, stand, fertig = lauf.read(stand, HEARTBEAT_SECONDS)
            for event in neue:
                if not self._sse(f"data: {json.dumps(event, ensure_ascii=False)}\n\n"):
                    return
            if fertig and stand <= len(lauf.events):


                lauf.delivered = True
                return






            if not neue and not self._sse(": warte\n\n"):
                return


def _route_to(target: str) -> str:
    """Welche eigene Adresse benutzt das System, um *target* zu erreichen?

    Der UDP-"Verbindungsaufbau" schickt kein einziges Paket -- er laesst nur
    das Betriebssystem die Route waehlen und verraet damit die Adresse der
    passenden Netzwerkkarte. Das ist zuverlaessiger als
    ``gethostbyname(gethostname())``, das auf vielen Linux-Systemen
    127.0.1.1 liefert.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((target, 9))
        address = probe.getsockname()[0]
    except OSError:
        return ""
    finally:
        probe.close()
    return "" if address.startswith("127.") else address


def lan_address() -> str:
    """Die eigene Adresse im heimischen Netz."""
    address = _route_to("8.8.8.8")
    if address and not is_tailscale(address):
        return address
    with contextlib.suppress(OSError):
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidate = str(info[4][0])
            if not candidate.startswith("127.") and not is_tailscale(candidate):
                return candidate
    return "" if is_tailscale(address) else address


def is_tailscale(address: str) -> bool:
    """Liegt *address* in einem der Tailscale-Adressbereiche?"""
    return cluster.tailscale_ip_ok(address)


def tailscale_address() -> str:
    """Die eigene Tailscale-Adresse, falls es eine gibt.

    100.100.100.100 ist der DNS-Dienst im Tailnet -- die Route dorthin fuehrt
    zwangslaeufig ueber die Tailscale-Karte. Ohne Tailscale gibt es keine
    solche Route und wir bekommen nichts Brauchbares zurueck.
    """
    address = _route_to("100.100.100.100")
    return address if is_tailscale(address) else ""


def is_public_host(host: str) -> bool:
    """Bindet *host* an mehr als nur den eigenen Rechner?"""
    return host not in ("127.0.0.1", "localhost", "::1", "")


def token_problem(token: str) -> str:
    """Prueft ein selbst gewaehltes Zugangswort. Leer = in Ordnung.

    Der Browser schickt das Wort als HTTP-Kopfzeile mit, und die darf nur
    ASCII enthalten -- ein "grün" kaeme dort nie an. Lieber gleich beim Start
    sagen als spaeter bei jedem Aufruf scheitern.
    """
    if not token:
        return ""
    if any(character.isspace() for character in token):
        return "Das Zugangswort darf keine Leerzeichen enthalten."
    if not token.isascii():
        umlauts = "".join(sorted({c for c in token if not c.isascii()}))
        return (
            f"Das Zugangswort darf keine Sonderzeichen enthalten ({umlauts}). "
            "Nimm ein Wort ohne Umlaute – also 'gruen' statt 'grün'."
        )
    if any(character in token for character in "?&#/%"):
        return "Das Zugangswort darf kein ?, &, #, / oder % enthalten – das zerlegt die Adresse."
    return ""


def new_token() -> str:
    """Kurzes Zugangswort -- muss auf einem Handy tippbar bleiben."""
    return secrets.token_urlsafe(9)


def addresses_for(host: str, port: int, token: str = "") -> list[tuple[str, str]]:
    """Alle Adressen, unter denen die Oberflaeche erreichbar ist.

    Gibt Paare aus Adresse und Erklaerung zurueck. Bei Bindung an alle
    Schnittstellen steht die lokale Adresse zuletzt, damit der Browser
    sie beim Start oeffnet. Bei einer einzelnen Schnittstelle gilt nur diese.
    """
    suffix = f"?token={token}" if token else ""
    found: list[tuple[str, str]] = []
    if is_public_host(host):
        if host == "0.0.0.0":
            lan = lan_address()
            if lan:
                found.append((lan, "im heimischen Netz"))
            tailscale = tailscale_address()
            if tailscale:
                found.append((tailscale, "über Tailscale"))
        else:
            found.append((host, "wie angegeben"))
    if host in ("::", "::1"):
        found = [(address, note) for address, note in found if address != "::"]
        found.append(("::1", "auf diesem Rechner"))
    elif host in ("0.0.0.0", "127.0.0.1", "localhost", ""):
        found.append(("127.0.0.1", "auf diesem Rechner"))
    return [(f"http://{'[' + address + ']' if ':' in address else address}:{port}/{suffix}",
             note) for address, note in found]


def urls_for(host: str, port: int, token: str = "") -> list[str]:
    """Nur die Adressen aus :func:`addresses_for`, ohne Erklaerungen."""
    return [url for url, _ in addresses_for(host, port, token)]



_WARMED = threading.Event()


def _warm_up() -> None:
    """Laedt LiteLLM im Hintergrund vor, damit die erste Antwort nicht wartet.

    Seit 11.2.1 erst, wenn jemand die Oberflaeche oeffnet, nicht schon beim
    Start: Ein Server, den niemand benutzt, spart so rund 190 MB.
    """
    with contextlib.suppress(Exception):
        import litellm  # noqa: F401


def _warm_up_once() -> None:
    """Startet :func:`_warm_up` beim ersten Seitenaufruf, danach nie wieder."""
    with _CACHE_LOCK:
        if _WARMED.is_set():
            return
        _WARMED.set()
    threading.Thread(target=_warm_up, daemon=True, name="aquaticy-warmup").start()


def _cluster_load() -> dict[str, Any]:
    """Wie viel dieser Server gerade zu tun hat -- fuer den Lastausgleich."""
    with SESSIONS._lock:
        sitzungen = list(SESSIONS._sessions.values())
    laeufe = 0
    for sitzung in [chat for s in sitzungen for chat in s.chat_sessions()]:
        with contextlib.suppress(Exception):
            buch = sitzung.runs
            with buch._lock:
                laeufe += sum(1 for lauf in buch._runs.values() if not lauf.done)
    last: dict[str, Any] = {"runs": laeufe, "sessions": len(sitzungen)}
    if SHARDING is not None:

        with contextlib.suppress(Exception):
            last["split"] = SHARDING.worker_status()
    return last


def _cluster_hardware() -> dict[str, Any]:
    """Hardware und Auslastung dieses Rechners fuer den Verbund (11.3.2 Sol).

    Der Master teilt danach ein, wer Modelle rechnet und wer nur die Website
    bedient; die Auslastungsanzeige zeigt es fuer jeden Server.
    """
    from aquaticy.local_model import installed_models
    from aquaticy.system import cpu_load, gpu_use, memory_use

    cpu, ram, gpu = cpu_load(), memory_use(), gpu_use()
    try:
        modelle = len(installed_models(OLLAMA_URL()))
    except Exception:
        modelle = 0
    return {"cores": cpu.get("cores"), "cpu_pct": cpu.get("percent"),
            "ram_gb": ram.get("total_gb"), "ram_used_gb": ram.get("used_gb"),
            "ram_pct": ram.get("percent"), "gpu": gpu.get("name", ""),
            "vram_gb": gpu.get("total_gb"), "vram_used_gb": gpu.get("used_gb"),
            "gpu_pct": gpu.get("percent"), "ollama_models": modelle}


def _cluster_wants_models(user_id: str) -> bool:
    """Rechnet dieses Konto mit lokalen Modellen? Dann gehoert es auf einen Modell-Server.

    Aus der .env seines Profils (wie _profile_settings), sonst die Vorgabe des
    Servers: Hauptmodell, Code-Modell, Agenten-Modell.
    """
    from aquaticy.local_model import local_name

    if AUTH is None or AUTH.account(user_id) is None:
        return False
    try:
        roh = read_env_file(AUTH.profile_dir(user_id) / ".env")
    except Exception:
        roh = {}
    vorgabe = get_settings()
    for feld, attr in (("AQUATICY_MODEL", "model"), ("AQUATICY_CODE_MODEL", "code_model"),
                       ("AQUATICY_SUBAGENT_MODEL", "subagent_model")):
        modell = str(roh.get(feld) or getattr(vorgabe, attr, "") or "").strip()
        if modell and (local_name(modell) or modell == SPLIT_MODEL_ID):
            return True
    return False


def _cluster_release(user_id: str) -> bool:
    """Gibt ein Konto an einen anderen Server ab -- nur, wenn hier nichts laeuft."""
    with SESSIONS._lock:
        sitzung = SESSIONS._sessions.get(user_id)
    if sitzung is not None:
        for chat in sitzung.chat_sessions():
            with contextlib.suppress(Exception), chat.runs._lock:
                if any(not lauf.done for lauf in chat.runs._runs.values()):
                    return False
    konto = AUTH.account(user_id) if AUTH is not None else None
    if konto is not None:
        forget_account_runtime(konto)
    return True


def _cluster_adopt(user_id: str) -> None:
    konto = AUTH.account(user_id) if AUTH is not None else None
    if konto is not None:
        start_user_scheduler(konto)


def _cluster_restart() -> None:
    """Nach dem Beitritt: einmal neu starten, damit alles die Daten des Verbunds liest."""
    print("  [Verbund] Starte neu, um die Daten des Verbunds zu laden ...", flush=True)
    _CLUSTER_RESTART.set()
    if SERVER is not None:
        SERVER.shutdown()


def cluster_view(session: Any) -> tuple[dict[str, Any], int]:
    """Der Verbund fuer die Dev settings -- nur fuer Ultra."""
    if not getattr(session, "ultra", False):
        return {"error": "Der Server-Verbund gehört zu Ultra.", "locked": True}, 403
    if CLUSTER is None:
        return {"error": "Der Verbund ist hier nicht verfügbar.", "enabled": False}, 200
    return _cluster_view_full(), 200


def _cluster_view_full() -> dict[str, Any]:
    """Der Verbund samt "Serverlast aufteilen" (10.2.0 Luna)."""
    antwort = CLUSTER.view()
    if SHARDING is not None:
        with contextlib.suppress(Exception):
            antwort["split"] = SHARDING.view()
    return antwort


def upgrades_view(session: Any) -> dict[str, Any]:
    """Auto-Upgrading (10.0 Luna): die Startmeldung fuer jedes Konto, der Stand fuer Ultra."""
    if UPGRADE_DIR is None:
        return {"available": False, "notice": None}
    from aquaticy import upgrading

    konto = getattr(getattr(session, "account", None), "id", "") or ""
    antwort: dict[str, Any] = {"available": True,
                               "notice": upgrading.launch_notice(UPGRADE_DIR, konto)}
    if getattr(session, "ultra", False):
        antwort["ultra"] = upgrading.view(UPGRADE_DIR)
    return antwort


def upgrades_action(session: Any, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Gesehen (jedes Konto); Schalter, Training, Upgraden, Ueberspringen und
    Zuruecksetzen (nur Ultra -- geprueft hier, nicht im Browser)."""
    if UPGRADE_DIR is None:
        return {"error": "Auto-Upgrading läuft nur mit der Weboberfläche."}, 400
    from aquaticy import upgrading

    aktion = str(payload.get("action", ""))
    konto = getattr(getattr(session, "account", None), "id", "") or ""
    try:
        if aktion == "seen":
            upgrading.mark_seen(UPGRADE_DIR, konto, str(payload.get("id", "")))
            return {"ok": True}, 200
        if not getattr(session, "ultra", False):
            return {"error": "Auto-Upgrading steuert nur ein Ultra-Konto.", "locked": True}, 403
        base = str(payload.get("base", ""))
        if aktion == "enable":
            from aquaticy.local_model import installed_models

            an = payload.get("on") is True
            lokal = installed_models(OLLAMA_URL()) if an else []
            upgrading.set_enabled(UPGRADE_DIR, an, lokal)
            if an and UPGRADER is not None:
                UPGRADER.run_now()
        elif aktion == "train":
            if not upgrading.load(UPGRADE_DIR)["enabled"]:
                return {"error": "Schalte Auto-Upgrading zuerst ein."}, 400
            if UPGRADER is not None:
                UPGRADER.run_now()
        elif aktion == "upgrade":
            upgrading.upgrade(UPGRADE_DIR, base)
        elif aktion == "skip":
            upgrading.skip(UPGRADE_DIR, base, upgrading.OllamaBackend(OLLAMA_URL()))
        elif aktion == "rollback":
            upgrading.rollback(UPGRADE_DIR, base, str(payload.get("version", "")))
        else:
            return {"error": "Unbekannte Aktion."}, 400
    except upgrading.UpgradeError as exc:
        return {"error": str(exc)}, 400
    return {"ok": True, "ultra": upgrading.view(UPGRADE_DIR)}, 200


def OLLAMA_URL() -> str:
    """Die Ollama-Adresse des Betreibers (fuer Auto-Upgrading)."""
    from aquaticy.local_model import DEFAULT_OLLAMA_URL

    base = (get_settings().api_base or "").strip().rstrip("/")
    return re.sub(r"/v1$", "", base) if "11434" in base else DEFAULT_OLLAMA_URL


def cluster_action(session: Any, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Schalten, einladen, Code bestaetigen, entfernen, verlassen -- nur Ultra."""
    if not getattr(session, "ultra", False):
        return {"error": "Der Server-Verbund gehört zu Ultra.", "locked": True}, 403
    if CLUSTER is None:
        return {"error": "Der Verbund ist hier nicht verfügbar."}, 400
    aktion = str(payload.get("action", ""))
    try:
        if aktion == "enable":
            CLUSTER.set_enabled(bool(payload.get("on")))
        elif aktion == "invite":
            adresse = str(payload.get("address", "")).strip()
            port = cluster.parse_port(payload.get("port", DEFAULT_PORT))
            if not CLUSTER.enabled:
                return {"error": "Schalte den Server-Verbund zuerst ein."}, 400
            CLUSTER.invite(adresse, port)
        elif aktion == "confirm":
            CLUSTER.confirm(str(payload.get("id", "")), str(payload.get("code", "")))
        elif aktion == "remove":
            if not CLUSTER.is_master:
                return {"error": "Entfernen kann nur der Master."}, 403
            CLUSTER.remove(str(payload.get("node", "")))
        elif aktion == "failover":
            if not CLUSTER.is_master:
                return {"error": "Konten übernehmen kann nur der Master."}, 403
            CLUSTER.failover(str(payload.get("node", "")))
        elif aktion == "leave":
            CLUSTER.leave()
        elif aktion == "split":


            if not CLUSTER.is_master:
                return {"error": "Die Serverlast teilt nur der Master auf."}, 403
            an = payload.get("on") is True
            modell = str(payload.get("model") or "").strip()
            if an:
                from aquaticy.sharding import ollama_models

                if modell not in {m["name"] for m in ollama_models(OLLAMA_URL())}:
                    return {"error": "Dieses Modell gibt es in Ollama auf dem Master nicht."}, 400
            CLUSTER.set_split(an, modell)
            if SHARDING is not None:
                SHARDING.wake()
        elif aktion == "split-restart":
            if not CLUSTER.is_master:
                return {"error": "Neu verteilen kann nur der Master."}, 403
            if not CLUSTER.split_on:
                return {"error": "Schalte „Serverlast aufteilen“ zuerst ein."}, 400
            if SHARDING is not None:
                SHARDING.request_restart()
        else:
            return {"error": "Unbekannte Aktion."}, 400
    except cluster.ClusterError as exc:
        return {"error": str(exc)}, 400
    except (OSError, ValueError) as exc:
        return {"error": f"Der andere Server ist nicht erreichbar ({type(exc).__name__})."}, 502
    return _cluster_view_full(), 200



BACKUP_PORTS = 20
_PORT_BELEGT = {98, 48, 10048, 13, 10013}


def port_candidates(port: int) -> list[int]:
    """Der eingestellte Port und dahinter die Ersatz-Ports.

    Den UDP-Port des Server-Verbunds laesst die Liste aus, damit sich beides
    nicht verwechseln laesst. Port 0 heisst "irgendeiner" -- dann nur der.
    """
    port = int(port)
    if port == 0:
        return [0]
    out = [port]
    kandidat = port
    while len(out) <= BACKUP_PORTS and kandidat < 65535:
        kandidat += 1
        if kandidat != cluster.DISCOVERY_PORT:
            out.append(kandidat)
    if port < 1024 and DEFAULT_PORT not in out:
        out.append(DEFAULT_PORT)
    return out


def free_port(host: str, port: int) -> int:
    """Der erste freie Port ab *port* -- fuer die Adresse, die vor dem Start gezeigt wird."""
    for kandidat in port_candidates(port):
        familie = socket.AF_INET6 if ":" in host else socket.AF_INET
        with contextlib.closing(socket.socket(familie, socket.SOCK_STREAM)) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, kandidat))
            except OSError as exc:
                if exc.errno in _PORT_BELEGT:
                    continue
                raise
            return kandidat
    return port




VERBINDUNG_WEG = (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError)


class AquaticyServer(ThreadingHTTPServer):
    """Der Webserver -- ohne Ablaufverfolgung im Terminal fuer jede abgerissene Leitung.

    Die Standardbibliothek druckte bei jedem "Connection reset by peer" einen
    ganzen Traceback (gemeldet mit Python 3.14, ueber Tailscale). Jetzt bleibt
    ein Abbruch durch die Gegenseite still, alles andere steht als eine Zeile da.
    """





    request_queue_size = 128


    max_connections = 256

    def __init__(self, server_address: tuple[str, int], handler: Any,
                 bind_and_activate: bool = True) -> None:
        self.address_family = socket.AF_INET6 if ":" in server_address[0] else socket.AF_INET
        self._connection_slots = threading.BoundedSemaphore(self.max_connections)
        super().__init__(server_address, handler, bind_and_activate=bind_and_activate)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._connection_slots.acquire(blocking=False):
            try:
                self._reject_overload(request)
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._connection_slots.release()
            raise

    def _reject_overload(self, request: Any) -> None:
        with contextlib.suppress(OSError):
            request.settimeout(0.1)
            request.sendall(b"HTTP/1.1 503 Service Unavailable\r\n"
                            b"Content-Length: 0\r\nConnection: close\r\n"
                            b"Cache-Control: no-store\r\nRetry-After: 1\r\n"
                            b"X-Content-Type-Options: nosniff\r\nX-Frame-Options: DENY\r\n"
                            b"Referrer-Policy: no-referrer\r\n"
                            b"Content-Security-Policy: default-src 'none'; "
                            b"frame-ancestors 'none'\r\n\r\n")

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            self._serve_connection(request, client_address)
        finally:
            self._connection_slots.release()

    def _serve_connection(self, request: Any, client_address: Any) -> None:
        super().process_request_thread(request, client_address)

    def handle_error(self, request: Any, client_address: Any) -> None:
        fehler = sys.exc_info()[1]
        if isinstance(fehler, VERBINDUNG_WEG):
            return
        wer = client_address[0] if client_address else "?"
        print(f"  [Verbindung] {wer}: {type(fehler).__name__}", flush=True)


def bind_server(host: str, port: int) -> ThreadingHTTPServer:
    """Der Webserver auf dem eingestellten Port -- oder dem naechsten freien (9.6.8 Sol).

    Ein belegter oder gesperrter Port ist kein Grund, nicht zu starten: Aquaticy
    nimmt den naechsten und sagt im Terminal, welcher es geworden ist.
    """
    letzter: OSError | None = None
    for kandidat in port_candidates(port):
        try:
            return AquaticyServer((host, kandidat), Handler)
        except OSError as exc:
            if exc.errno not in _PORT_BELEGT:
                raise
            letzter = exc
    raise letzter or OSError("Kein freier Port gefunden.")


class PublicHandler(Handler):
    """Der Eingang fuer den Cloudflare-Tunnel (11.1.0): hier kommt alles aus dem Internet.

    Er hoert nur auf 127.0.0.1 -- cloudflared erreicht ihn, das Netz nicht.
    Drei Dinge sind anders als am normalen Eingang:

    * Die Adresse des Besuchers kommt von Cloudflare (``CF-Connecting-IP``).
      Sonst saehen alle aus wie 127.0.0.1: eine Anfragegrenze fuer alle, und
      die Regeln fuer neue Konten galten nicht (Loopback ist dort ausgenommen).
    * Der Server-Verbund ist hier nicht erreichbar. Er vertraut dem eigenen
      Netz, und dazu gehoert 127.0.0.1.
    * Die Verbindung gilt als verschluesselt: der Besucher spricht HTTPS mit
      Cloudflare. Cookies gehen deshalb nur mit "Secure" raus.
    """

    public_entry = True

    def _client_ip(self) -> str:
        import ipaddress

        roh = (self.headers.get("CF-Connecting-IP") or "").strip() if self.headers else ""
        with contextlib.suppress(ValueError):
            if roh:
                return str(ipaddress.ip_address(roh.split("%", 1)[0]))
        return str(self.client_address[0] if self.client_address else "unknown")

    def _https(self) -> bool:
        return True

    def _origin_ok(self) -> bool:
        """Wie sonst -- und die eigene Domain zaehlt auch dann, wenn der Tunnel
        den Host umschreibt. Fremde Seiten kommen weiter nicht durch."""
        if super()._origin_ok():
            return True
        herkunft = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
        if herkunft in {"cross-site", "same-site"} or WEBSITE is None:
            return False
        origin = (self.headers.get("Origin") or "").strip().lower()
        return origin == f"https://{WEBSITE.config.domain}"

    def _cluster_route(self) -> None:
        self.responded = False
        self._json({"error": "unbekannter Pfad"}, 404)


class _TLSServer(AquaticyServer):
    """HTTPS fuer den Tunnel-Eingang.

    Der TLS-Handschlag laeuft im Faden der Verbindung, nicht in der Schleife,
    die Verbindungen annimmt -- ein haengender Client hielte sonst alle auf.
    """

    def __init__(self, address: tuple[str, int], handler: Any, context: Any) -> None:
        self.context = context
        super().__init__(address, handler)

    def _reject_overload(self, request: Any) -> None:

        return

    def _serve_connection(self, request: Any, client_address: Any) -> None:
        import ssl

        try:
            request.settimeout(15)
            request = self.context.wrap_socket(request, server_side=True)
            request.settimeout(None)
        except (ssl.SSLError, OSError):
            with contextlib.suppress(OSError):
                request.close()
            return
        super()._serve_connection(request, client_address)


def bind_public(context: Any, port: int) -> ThreadingHTTPServer:
    """Der Tunnel-Eingang: nur 127.0.0.1, nur HTTPS, auf *port* oder dem naechsten freien."""
    letzter: OSError | None = None
    for kandidat in port_candidates(port):
        try:
            return _TLSServer(("127.0.0.1", kandidat), PublicHandler, context)
        except OSError as exc:
            if exc.errno not in _PORT_BELEGT:
                raise
            letzter = exc
    raise letzter or OSError("Kein freier Port gefunden.")


def _start_website(data_dir: Path) -> tuple[Any, Any]:
    """Startet Tunnel-Eingang und Website, wenn eine Domain eingerichtet ist.

    Returns: (Website, Eingang) -- oder (None, None). Nichts davon darf den
    Start kosten: ohne Website laeuft Aquaticy eben im Heimnetz.
    """
    from aquaticy import website

    try:
        seite = website.from_settings(data_dir)
    except website.WebsiteError as exc:
        print(f"  [Website] {exc}", flush=True)
        return None, None
    if seite is None:
        return None, None
    try:
        eingang = bind_public(seite.tls(), seite.config.public_port)
    except Exception as exc:
        print(f"  [Website] Eingang nicht gestartet: {type(exc).__name__}: {exc}", flush=True)
        return None, None
    threading.Thread(target=eingang.serve_forever, name="aquaticy-public", daemon=True).start()
    seite.start(eingang.server_address[1])
    print(f"  Website:    https://{seite.config.domain}/ (über Cloudflare)", flush=True)
    return seite, eingang


class AlreadyRunning(RuntimeError):
    """Ein anderes Aquaticy arbeitet schon mit diesem Datenordner (9.6.9 Luna)."""


class DataDirLock:
    """Haelt den Datenordner fuer genau einen laufenden Server.

    Seit dem Ersatz-Port (9.6.8 Sol) brach ein versehentlich zweimal
    gestartetes Aquaticy nicht mehr ab, sondern lief auf dem naechsten Port
    mit denselben Daten mit -- Auftraege liefen doppelt, Schreibzugriffe
    kamen sich in die Quere. Die Sperre gibt das Betriebssystem frei, sobald
    der Prozess endet, auch nach einem harten Absturz.
    """

    def __init__(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "aquaticy.lock"
        self._file: Any = open(self.path, "a+b")  # noqa: SIM115
        try:
            self._lock()
        except OSError as exc:
            self._file.close()
            raise AlreadyRunning(
                "Aquaticy läuft mit diesem Datenordner schon – ein zweites Mal "
                "starten würde Aufträge doppelt ausführen.") from exc

    def _lock(self) -> None:
        if sys.platform == "win32":
            import msvcrt

            self._file.seek(0)
            msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            return
        import fcntl

        fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def release(self) -> None:
        if self._file.closed:
            return
        with contextlib.suppress(OSError):
            if sys.platform == "win32":
                import msvcrt

                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        self._file.close()


def serve(
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    token: str = "",
) -> None:
    """Startet die Oberflaeche und blockiert, bis Strg+C kommt.

    Den Zugang schuetzen die Konten: ohne Anmeldung gibt es nichts ausser der
    Anmeldeseite. *token* ist eine freiwillige zweite Schranke davor
    (``aquaticy web --token``) -- gesetzt wird es nur, wenn man es angibt.

    Raises:
        AlreadyRunning: wenn ein anderes Aquaticy denselben Datenordner nutzt.
    """
    sperre = DataDirLock(get_settings().data_dir)
    try:
        _serve(host, port, open_browser, token)
    except BaseException:

        _stop_schedulers()
        raise
    finally:
        sperre.release()
    if _CLUSTER_RESTART.is_set():

        import sys

        with contextlib.suppress(Exception):
            sys.stdout.flush()
            sys.stderr.flush()
        os.execv(sys.executable, [sys.executable, "-c", "from aquaticy.cli import main; main()",
                                 *sys.argv[1:]])


def _serve(host: str, port: int, open_browser: bool, token: str) -> None:
    global AUTH, TOKEN

    _CLUSTER_RESTART.clear()
    TOKEN = token
    data_dir = get_settings().data_dir
    code = pro_code_for(data_dir)
    from aquaticy.auth import ultra_code_for

    ultra = ultra_code_for(data_dir)
    AUTH = AuthStore(data_dir, code, ultra)
    global AIGUARD
    from aquaticy.aiguard import guard_for

    AIGUARD = guard_for(data_dir)
    print(f"  Pro-Code:   {code} (9 Zeichen, geheim halten)")
    print(f"  Ultra-Code: {ultra} (14 Zeichen, geheim halten)")


    try:
        from aquaticy.sandbox import sweep

        threading.Thread(target=sweep, daemon=True).start()
    except Exception:  # pragma: no cover
        pass


    try:
        global COWORKER_SCHEDULER
        from aquaticy import coworker as coworker_mod

        COWORKER_SCHEDULER = coworker_mod.Scheduler(SESSION.settings, plan=lambda: "ultra")
        COWORKER_SCHEDULER.start()
        for account in AUTH.accounts():
            start_user_scheduler(account)

        with contextlib.suppress(Exception):
            _bridge_runner(DEFAULT_SESSION).ensure_running()
    except Exception:  # pragma: no cover
        pass
    try:
        server = bind_server(host, port)
    except BaseException:

        _stop_schedulers()
        raise
    if server.server_address[1] != port:
        print(f"  Aquaticy läuft auf Port {server.server_address[1]}.")
        for address, note in addresses_for(host, server.server_address[1], token):
            print(f"  {address} ({note})")
    port = server.server_address[1]
    global SERVER, CLUSTER, UPGRADE_DIR, UPGRADER, SHARDING
    research_stop: threading.Event | None = None
    research_worker: threading.Thread | None = None




    try:
        from aquaticy.learning import Learning
        from aquaticy.research import start_cleanup

        research_stop, research_worker = start_cleanup(Learning(data_dir).research)
        SERVER = server


        from aquaticy import upgrading
        from aquaticy.local_model import installed_models

        UPGRADE_DIR = data_dir
        UPGRADER = upgrading.Trainer(
            data_dir,
            lambda: Learning(data_dir).confirmed_facts(upgrading.MAX_FACTS, metadata=True),
            lambda: upgrading.OllamaBackend(OLLAMA_URL()),
            lambda: installed_models(OLLAMA_URL()),
            manifest=lambda: Learning(data_dir).upgrade_manifest())
        UPGRADER.start()

        try:
            frage = cluster.TerminalPrompt()
            CLUSTER = cluster.Cluster(data_dir, host=host, port=port, version=VERSION_LABEL,
                                      hooks=cluster.Hooks(load=_cluster_load,
                                                          release=_cluster_release,
                                                          adopt=_cluster_adopt,
                                                          restart=_cluster_restart, ask=frage,
                                                          hardware=_cluster_hardware,
                                                          wants_models=_cluster_wants_models))
            frage.cluster = CLUSTER
            CLUSTER.start()


            from aquaticy import sharding

            SHARDING = sharding.Manager(
                CLUSTER, OLLAMA_URL, lambda: int(get_settings().context_tokens or 0))
            SHARDING.start()
            if CLUSTER.joined:
                rolle = "Master" if CLUSTER.is_master else "Mitglied"
                print(f"  Verbund:    {rolle}, {len(CLUSTER.members())} Server")
        except Exception as exc:  # pragma: no cover
            print(f"  [Verbund] nicht gestartet: {type(exc).__name__}: {exc}")
            CLUSTER = None
        global WEBSITE, PUBLIC_SERVER, LAN_ONLY
        WEBSITE, PUBLIC_SERVER = _start_website(data_dir)
        LAN_ONLY = WEBSITE is not None
        if open_browser:


            local = urls_for(host, port, token)[-1]
            threading.Timer(0.6, lambda: webbrowser.open(local)).start()
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if PUBLIC_SERVER is not None:
            with contextlib.suppress(Exception):
                PUBLIC_SERVER.shutdown()
                PUBLIC_SERVER.server_close()
            PUBLIC_SERVER = None
        if WEBSITE is not None:
            WEBSITE.stop()
            WEBSITE = None
        LAN_ONLY = False
        if research_stop is not None and research_worker is not None:
            research_stop.set()
            research_worker.join(timeout=6)
        if SHARDING is not None:
            SHARDING.stop()
            SHARDING = None
        if CLUSTER is not None:
            CLUSTER.stop()
        if UPGRADER is not None:
            UPGRADER.stop()
        UPGRADER = None
        UPGRADE_DIR = None
        _stop_schedulers()
        TOKEN = ""
        AUTH = None
