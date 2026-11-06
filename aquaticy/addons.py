"""Add-ons: Konten und Programme, die man Aquaticy dazugeben kann.

Jedes Add-on laesst sich **installieren**, **ein- und ausschalten** und wieder
**deinstallieren** -- auch die, die nichts herunterladen muessen (GitHub zum
Beispiel): "Installieren" heisst dann, dass es fuer dieses Konto eingerichtet
wird. Nach dem Installieren meldet man sich an, so wie es der Dienst vorsieht:

* **NVIDIA NIM** und **Mistral** (seit 12.0.0 Luna) -- mit dem API-Schluessel
  des eigenen Kontos beim Anbieter. Das ist die einzige Stelle in Aquaticy, an
  der sich ein API-Schluessel eintragen laesst (aquaticy/linked.py). Sie sind
  keine Werkzeuge: kein Befehl im Chat, kein Schalter; Deinstallieren loescht
  den Schluessel.
* **GitHub** -- mit einem persoenlichen Zugangs-Token. Aquaticy liest damit nur
  (Repos, Issues, Pull Requests, Dateien); geschrieben wird nie, auch wenn das
  Token es erlauben wuerde.
* **WhatsApp Web** -- per QR-Code mit dem Handy, in einem eigenen Firefox-Profil in der
  virtual machine. (Telegram Web gibt es seit 12.6.6 Luna nicht mehr.)
* **Signal** -- ein "Signal Web" gibt es nicht. Das Add-on installiert Signal
  Desktop (das offizielle Programm) in der virtual machine; gekoppelt wird wie ein
  Computer, ebenfalls per QR-Code.
* **Blender** -- ohne Anmeldung. Das offizielle Programm von blender.org, mit
  Oberflaeche im Desktop und fuer ``blender_run``.
* **Wetter** (Open-Meteo, ohne Schluessel) und **RSS-Feeds** (eigene Liste) --
  zwei Vorschlaege, die ohne virtual machine auskommen.

Die feste Regel beim Anmelden: **der Mensch meldet sich an, nie Aquaticy.**
QR-Codes scannt der Nutzer mit seinem Handy; Tokens und Passwoerter tippt er
selbst -- in das Feld hier oder, ueber "Login-Apps", direkt in den Bildschirm
der virtual machine. Aquaticy selbst tippt weiterhin nie ein Passwort (siehe
aquaticy/desktop.py).

Was wohin kommt:

* Der Zustand (installiert, an/aus, angemeldet als ...) liegt je Konto in
  ``addons.json`` im Kontoordner.
* Das GitHub-Token liegt in der ``.env`` des Kontos (wie alle Zugangsdaten)
  und geht nie an den Browser -- der erfaehrt nur, OB eines gesetzt ist.
* Programme und Anmeldungen der virtual-machine-Add-ons liegen je Konto und Add-on
  auf einem eigenen Datentraeger (``aquaticy-addon-<konto>-<name>``). Nur die
  eingeschalteten werden in die virtual machine eingehaengt; Deinstallieren loescht
  den Datentraeger samt Anmeldung.
* Installiert wird in einer eigenen, abgesperrten Wegwerf-virtual machine (Heimnetz
  gesperrt, kein root) -- nie auf dem Rechner selbst. Geladen wird nur von den
  offiziellen Servern, geprueft gegen die veroeffentlichte Pruefsumme
  (docker/desktop/aquaticy-addons).

virtual-machine-Add-ons brauchen den User mode -- und damit ein Ultra-Konto. Aus dem
Chat heraus laesst sich keins installieren, einschalten oder anmelden.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx


@dataclass(frozen=True)
class AddOn:
    """Ein Eintrag im Add-on-Fenster."""

    id: str
    name: str
    icon: str
    group: str
    summary: str

    login: str

    werkstatt: bool = False

    programm: str = ""

    adresse: str = ""

    vorschlag: bool = False

    anmelden: str = ""

    hinweis: str = ""


CATALOG: dict[str, AddOn] = {
    addon.id: addon
    for addon in (

        AddOn(
            "nvidia_nim", "NVIDIA NIM", "🟩", "KI-Modelle",
            "Offene Modelle bei NVIDIA, zum Beispiel Nemotron und Qwen-Coder. Viel kostenlos: 40 "
            "Fragen pro Minute.",
            login="apikey",
            anmelden="Melde dich bei NVIDIA an. Erstelle unter „API Keys“ einen Schlüssel. Er "
            "beginnt mit nvapi-. Füge ihn hier ein.",
            hinweis="Deine Fragen gehen an NVIDIA. Der Schlüssel wird verschlüsselt in deinem "
            "Konto gespeichert. Er geht nur an NVIDIA.",
        ),
        AddOn(
            "mistral", "Mistral", "🟧", "KI-Modelle",
            "Anbieter aus Europa, Server in der EU. Zum Beispiel Mistral Large, Mistral Small und "
            "Codestral.",
            login="apikey",
            anmelden="Melde dich bei Mistral an. Erstelle unter „API Keys“ einen Schlüssel. Füge "
            "ihn hier ein.",
            hinweis="Deine Fragen gehen an Mistral. Der Schlüssel wird verschlüsselt in deinem "
            "Konto gespeichert. Er geht nur an Mistral.",
        ),
        AddOn(
            "github", "GitHub", "🐙", "Konten",
            "Deine Repos, Commits, Issues, Pull Requests und Dateien. Aquaticy kann auch "
            "ändern, committen, pushen und Pull Requests öffnen. Code prüfen: "
            "„Prüfe https://github.com/besitzer/repo“.",
            login="token",
            anmelden="Erstelle ein Fine-grained-Token auf GitHub. Wähle deine Repos unter "
            "Repository access. Zum Lesen reicht Contents: Read-only. Zum Ändern erlaube "
            "Contents: Read and write und Pull requests: Read and write. Füge das Token hier "
            "ein.",
            hinweis="Ausgewählte Dateien gehen an dein Chat-Modell. Jeder Commit, Push, Pull "
            "Request und Kommentar braucht dein Ja. Aquaticy pusht nie mit force. Der "
            "Schlüssel bleibt auf diesem Rechner, auch wenn die VM das Repo bearbeitet. Nach "
            "privaten Repo-Inhalten braucht öffentliche Recherche deine Bestätigung.",
        ),
        AddOn(
            "whatsapp", "WhatsApp Web", "💬", "Messenger",
            "WhatsApp im Browser der virtual machine: Aquaticy kann Chats lesen und Antworten "
            "vorbereiten. Senden nur nach deinem Ja.",
            login="qr", werkstatt=True, programm="webapp",
            adresse="https://web.whatsapp.com/",
            anmelden="„Anmelden“ zeigt den QR-Code direkt in Aquaticy. Auf dem Handy: "
            "WhatsApp → Einstellungen → Verknüpfte Geräte → Gerät hinzufügen, dann den "
            "QR-Code im Anmeldefenster scannen.",
            hinweis="WhatsApp mag keine Automatisierung. Nutze es nur für dich, nie für "
            "Massennachrichten, sonst droht eine Sperre. Was Aquaticy liest, geht an dein Modell. "
            "Braucht Firefox (kommt beim Installieren mit).",
        ),
        AddOn(
            "signal", "Signal", "🔵", "Messenger",
            "Signal Desktop in der virtual machine (ein „Signal Web“ gibt es nicht): Aquaticy "
            "liest mit und bereitet Antworten vor. Senden nur nach deinem Ja.",
            login="qr", werkstatt=True, programm="signal",
            anmelden="„Anmelden“ zeigt den QR-Code direkt in Aquaticy. Auf dem Handy: Signal → "
            "Einstellungen → Gekoppelte Geräte → +, dann den QR-Code im Anmeldefenster "
            "scannen.",
            hinweis="Signal Desktop gibt es nur für x86_64. Nachrichten, die Aquaticy liest, "
            "gehen an dein Modell. Signal ist Ende-zu-Ende-verschlüsselt — überleg dir das also "
            "gut.",
        ),
        AddOn(
            "blender", "Blender", "🧊", "Programme",
            "Das 3D-Programm von blender.org: mit Oberfläche im Desktop der virtual machine und "
            "für Skripte (blender_run). Damit baust du Modelle, richtest Szenen ein und renderst.",
            login="keine", werkstatt=True, programm="blender",
            anmelden="Keine Anmeldung nötig.",
            hinweis="Rund 350 MB Download, ausgepackt über 1 GB. Mit der virtual machine in Größe "
            "„Plus“ läuft es viel ruhiger.",
        ),
        AddOn(
            "wetter", "Wetter", "🌦️", "Dienste",
            "Wetter jetzt und Vorhersage bis 7 Tage für jeden Ort. Von Open-Meteo (freie "
            "Wetterdaten, u. a. vom Deutschen Wetterdienst), ohne Schlüssel.",
            login="keine", vorschlag=True,
            anmelden="Keine Anmeldung nötig.",
            hinweis="Nur der Ortsname geht an Open-Meteo, sonst nichts.",
        ),
        AddOn(
            "feeds", "RSS-Feeds", "📰", "Dienste",
            "Deine eigenen Nachrichtenquellen: Aquaticy liest die Feeds, die du hier "
            "einträgst, und fasst zusammen, was neu ist.",
            login="feeds", vorschlag=True,
            anmelden="Trag die Adressen deiner Feeds ein (eine je Zeile, höchstens 20).",
            hinweis="Aquaticy ruft höflich ab: beachtet robots.txt, höchstens eine Anfrage pro "
            "Sekunde und Server, mit ehrlicher Kennung.",
        ),

        AddOn(
            "nachrichten", "Tagesschau", "🗞️", "Dienste",
            "Die aktuellen Meldungen der Tagesschau — nach Thema (Inland, Ausland, "
            "Wirtschaft, Sport …) oder als Suche. Ohne Anmeldung.",
            login="keine", vorschlag=True,
            anmelden="Keine Anmeldung nötig.",
            hinweis="Nur für den privaten Gebrauch. Die Tagesschau erlaubt höchstens 60 "
            "Abrufe pro Stunde — Aquaticy hält sich daran.",
        ),
        AddOn(
            "wikipedia", "Wikipedia", "📚", "Dienste",
            "Schnell nachschlagen: Artikel finden und die Kurzfassung lesen — ohne Umweg "
            "über eine Websuche.",
            login="keine", vorschlag=True,
            anmelden="Keine Anmeldung nötig.",
            hinweis="Nur dein Suchbegriff geht an Wikipedia. Texte stehen unter CC BY-SA.",
        ),
        AddOn(
            "waehrung", "Währungsrechner", "💱", "Dienste",
            "Tageskurse der Europäischen Zentralbank für rund 30 Währungen. Umrechnen ohne Suche.",
            login="keine", vorschlag=True,
            anmelden="Keine Anmeldung nötig.",
            hinweis="Neue Kurse gibt es einmal pro Werktag gegen 16 Uhr (Frankfurter Zeit, "
            "Referenzkurse der EZB). Für Überweisungen gilt der Kurs deiner Bank.",
        ),
        AddOn(
            "feiertage", "Feiertage", "📅", "Dienste",
            "Gesetzliche Feiertage für Deutschland und über 100 andere Länder. Auch, welche nur "
            "in einzelnen Bundesländern gelten.",
            login="keine", vorschlag=True,
            anmelden="Keine Anmeldung nötig.",
            hinweis="Daten von Nager.Date. Nur Jahr und Land gehen raus.",
        ),

        AddOn(
            "code-review", "Code-Review", "🔍", "Plugins",
            "Prüft Code auf typische Fehler. Besonders auf die, die KI-Code oft hat: erfundene "
            "Funktionen und Pakete, fehlende Randfälle, verschluckte Fehler.",
            login="keine",
            anmelden="Keine Anmeldung nötig. Im Chat: /code-review und dahinter Code, eine "
            "angehängte Datei oder ein GitHub-Repo.",
            hinweis="Der Code geht an dein Modell. Mit dem Add-on GitHub liest Aquaticy auch "
            "Repos und Pull Requests.",
        ),
        AddOn(
            "security-review", "Security-Review", "🛡️", "Plugins",
            "Sucht Sicherheitslücken wie XSS, SQL-Injection, fehlende Zugriffskontrolle oder "
            "Prompt-Injection (nach OWASP Top 10). Sagt dir auch, wie du sie schließt.",
            login="keine",
            anmelden="Keine Anmeldung nötig. Im Chat: /security-review und dahinter Code, "
            "eine angehängte Datei oder ein GitHub-Repo.",
            hinweis="Prüft wie ein Verteidiger: finden, belegen, beheben. Keine Anleitungen für "
            "Angriffe. Der Code geht an dein Modell.",
        ),
    )
}


MODEL_ADDONS = frozenset(a.id for a in CATALOG.values() if a.login == "apikey")


PLUGIN_CONTENT: dict[str, tuple[str, ...]] = {
    "code-review": (
        "Logik: Bedingungen, Randfälle (leer, None, 0, negativ), um eins daneben",
        "Fehlerbehandlung: verschluckte Ausnahmen, ungeprüfte Rückgaben, fehlende Zeitlimits",
        "Ressourcen und Nebenläufigkeit: offene Dateien, Race Conditions, async ohne await",
        "Daten und Zeit: Zeitzonen, Rundung, Kodierung, Kommazahlen mit ==",
        "KI-Code: erfundene Funktionen und Pakete (Slopsquatting), Platzhalter, Tests, die "
        "nur den Erfolgsfall prüfen, veraltete Bibliotheken",
    ),
    "security-review": (
        "OWASP Top 10:2025 — Zugriffskontrolle, Fehlkonfiguration, Lieferkette, "
        "Kryptografie, Injection, Design, Anmeldung, Integrität, Protokolle, Ausnahmen",
        "Injection: SQL, Shell, XSS (innerHTML & Co.), Templates, Logs",
        "Geheimnisse im Code, unsichere Cookies, JWT, Deserialisierung, Zip Slip",
        "OWASP LLM Top 10 2025 — Prompt-Injection, Datenabfluss, ungeprüfte Modellausgabe, "
        "zu viel Handlungsfreiheit für Agenten",
    ),
}




@dataclass(frozen=True)
class Recht:
    """Eine Einstellung im Add-on-Fenster: eine Frage, zwei oder drei Antworten.

    Bewusst so einfach: kein Regelwerk, sondern eine Wahl wie "Nur lesen" oder
    "Lesen und schreiben". Durchgesetzt wird sie im Code (Werkzeug bzw. Pruefung
    im Desktop), nicht nur im Prompt.
    """

    key: str
    label: str
    options: tuple[tuple[str, str], ...]
    default: str

    nur_wenn: tuple[str, str] | None = None


_MESSENGER_RECHTE = (
    Recht("zugriff", "Was Aquaticy darf",
          (("lesen", "Nur lesen"), ("schreiben", "Lesen und schreiben")), "lesen"),
    Recht("wo", "Schreiben in",
          (("einzeln", "Nur Einzelchats"), ("alle", "Einzelchats und Gruppen")), "einzeln",
          nur_wenn=("zugriff", "schreiben")),
)

RIGHTS: dict[str, tuple[Recht, ...]] = {
    "github": (
        Recht("repos", "Welche Repos",
              (("oeffentlich", "Nur öffentliche"), ("alle", "Auch private")), "alle"),
        # Seit 15.0.0 auch aendern wie Codex. Jeder Schritt braucht trotzdem dein Ja.
        # Den Standard-Branch, das Mergen und GitHub Actions macht Aquaticy nie: Das bleibt
        # beim Menschen auf GitHub (wie bei Codex: Branch und Pull Request).
        Recht("inhalte", "Dateien und Änderungen",
              (("nein", "Nur Übersicht"), ("ja", "Auch Inhalte lesen"),
               ("aendern", "Lesen und ändern: eigene Branches, Commits, Pull Requests")),
              "aendern"),
    ),
    "whatsapp": _MESSENGER_RECHTE,
    "signal": _MESSENGER_RECHTE,
    "blender": (
        Recht("nutzung", "Blender nutzen",
              (("skripte", "Nur Skripte"), ("alles", "Skripte und Oberfläche")), "alles"),
    ),
    "wetter": (
        Recht("orte", "Orte", (("alle", "Jeder Ort"), ("meiner", "Nur mein Ort")), "alle"),
    ),
    "feeds": (
        Recht("menge", "Einträge je Abruf", (("10", "10"), ("20", "20"), ("40", "40")), "20"),
    ),
    "nachrichten": (
        Recht("menge", "Meldungen je Abruf", (("5", "5"), ("10", "10"), ("20", "20")), "10"),
    ),
    "wikipedia": (
        Recht("sprache", "Sprache", (("de", "Deutsch"), ("en", "Englisch")), "de"),
    ),
    "waehrung": (
        Recht("waehrungen", "Welche Währungen",
              (("alle", "Alle"), ("euro", "Nur von oder nach Euro")), "alle"),
    ),
    "feiertage": (
        Recht("land", "Länder", (("alle", "Jedes Land"), ("de", "Nur Deutschland")), "alle"),
    ),
    "code-review": (
        Recht("umfang", "Was gemeldet wird",
              (("alles", "Alle Befunde"), ("wichtig", "Nur Kritisches und Hohes")), "alles"),
        Recht("fixes", "Korrekturen", (("ja", "Mit Code für den Fix"), ("nein", "Nur Befunde")),
              "ja"),
    ),
    "security-review": (
        Recht("umfang", "Was gemeldet wird",
              (("alles", "Alle Lücken"), ("wichtig", "Nur Kritisches und Hohes")), "alles"),
        Recht("fixes", "Korrekturen", (("ja", "Mit Code für den Fix"), ("nein", "Nur Befunde")),
              "ja"),
    ),
}


MESSENGERS = ("whatsapp", "signal")



OTHER_MESSENGERS = ("telegram",)


RETIRED = ("telegram",)



STRICTEST = {"zugriff": "lesen", "wo": "einzeln"}


def rights_of(settings: Any, addon_id: str) -> dict[str, str]:
    """Die gueltigen Rechte eines Add-ons -- Unbekanntes faellt auf den Standard."""
    gespeichert = (load_state(settings).get(addon_id) or {}).get("rechte")
    gespeichert = gespeichert if isinstance(gespeichert, dict) else {}
    rechte: dict[str, str] = {}
    for recht in RIGHTS.get(addon_id, ()):
        wert = str(gespeichert.get(recht.key, ""))
        erlaubt = {option for option, _ in recht.options}
        rechte[recht.key] = wert if wert in erlaubt else recht.default
    return rechte


def set_rights(settings: Any, addon_id: str, werte: Any) -> dict[str, str]:
    """Setzt Rechte. Nur bekannte Schluessel, nur erlaubte Werte -- sonst nichts."""
    addon = get(addon_id)
    if not (load_state(settings).get(addon.id) or {}).get("installed"):
        raise AddOnError(f"{addon.name} ist nicht installiert.")
    if not isinstance(werte, dict) or not werte:
        raise AddOnError("Rechte bitte als {Name: Wert}.")
    katalog = {recht.key: recht for recht in RIGHTS.get(addon.id, ())}
    neu = rights_of(settings, addon.id)
    for key, wert in werte.items():
        recht = katalog.get(str(key))
        if recht is None:
            raise AddOnError(f"{addon.name} hat kein Recht '{key}'.")
        erlaubt = {option for option, _ in recht.options}
        if str(wert) not in erlaubt:
            raise AddOnError(f"'{wert}' gibt es bei '{recht.label}' nicht.")
        neu[recht.key] = str(wert)
    _update(settings, addon.id, rechte=neu)
    return neu


def rights_text(addon_id: str, rechte: dict[str, str]) -> str:
    """Die Rechte in Worten -- fuer den Prompt und die Anzeige."""
    teile = []
    for recht in RIGHTS.get(addon_id, ()):
        if recht.nur_wenn and rechte.get(recht.nur_wenn[0]) != recht.nur_wenn[1]:
            continue
        label = dict(recht.options).get(rechte.get(recht.key, recht.default), "")
        teile.append(f"{recht.label}: {label}")
    return "; ".join(teile)


def messenger_of(klasse: str, titel: str) -> str:
    """Welcher Messenger ist dieses Fenster? "" = keiner.

    Zuerst die Fensterklasse, die das Add-on selbst setzt (Firefox mit
    --class aquaticy-whatsapp, Signal Desktop). Dann der Titel -- das faengt
    auch WhatsApp Web im gewoehnlichen Browser.
    """
    klasse, titel = (klasse or "").lower(), (titel or "").lower()
    for name in MESSENGERS:
        if f"aquaticy-{name}" in klasse:
            return name
    if "signal" in klasse:
        return "signal"
    for name, merkmal in (("whatsapp", "whatsapp"), ("telegram", "telegram"),
                          ("signal", "signal")):
        if merkmal in titel:
            return name
    return ""


def messenger_rights(settings: Any, name: str) -> dict[str, str]:
    """Die Rechte fuer ein Messenger-Fenster -- ohne eingeschaltetes Add-on die strengsten."""
    if name in MESSENGERS and name in active_ids(settings, pro=True):
        return rights_of(settings, name)
    return dict(STRICTEST)





FIREFOX = "_firefox"


MOUNT_ROOT = "/addons"


INSTALL_TIMEOUT = 1800



INSTALL_SOURCE = ""

MAX_FEEDS = 20
MAX_FEED_BYTES = 2_000_000
MAX_FEED_ITEMS = 40


GITHUB_TOKEN_KEY = "AQUATICY_GITHUB_TOKEN"
GITHUB_API = "https://api.github.com"
OPEN_METEO_GEO = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
TAGESSCHAU = "https://www.tagesschau.de/api2u"
WIKIPEDIA = "https://{sprache}.wikipedia.org"
FRANKFURTER = "https://api.frankfurter.dev/v1/latest"
NAGER = "https://date.nager.at/api/v3/PublicHolidays/{jahr}/{land}"

STATE_FILE = "addons.json"
_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()

_jobs: dict[tuple[str, str], threading.Thread] = {}


class AddOnError(ValueError):
    """Eine Beanstandung, die der Nutzer lesen soll."""


def user_agent() -> str:
    from aquaticy import __version__

    return f"aquaticy/{__version__} (+https://github.com/jonasenriklaumen-a11y/Aquaticy-Ai)"





def _data_dir(settings: Any) -> Path:
    return Path(getattr(settings, "data_dir", "") or ".").expanduser()


def _lock(settings: Any) -> threading.Lock:
    key = str(_data_dir(settings).resolve())
    with _locks_lock:
        return _locks.setdefault(key, threading.Lock())


def _state_path(settings: Any) -> Path:
    return _data_dir(settings) / STATE_FILE


def load_state(settings: Any) -> dict[str, dict[str, Any]]:
    """Der gespeicherte Zustand -- Unbekanntes wird ignoriert, nie geglaubt."""
    try:
        raw = json.loads(_state_path(settings).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    addons = raw.get("addons") if isinstance(raw, dict) else None
    if not isinstance(addons, dict):
        return {}
    return {
        key: value
        for key, value in addons.items()
        if (key in CATALOG or key == FIREFOX) and isinstance(value, dict)
    }


def _save_state(settings: Any, state: dict[str, dict[str, Any]]) -> None:
    ziel = _state_path(settings)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    tmp = ziel.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "addons": state}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    with contextlib.suppress(OSError):
        tmp.chmod(0o600)
    tmp.replace(ziel)


def _update(settings: Any, addon_id: str, **felder: Any) -> dict[str, Any]:
    with _lock(settings):
        state = load_state(settings)
        eintrag = dict(state.get(addon_id) or {})
        eintrag.update(felder)
        state[addon_id] = eintrag
        _save_state(settings, state)
        return eintrag


def _drop(settings: Any, addon_id: str) -> None:
    with _lock(settings):
        state = load_state(settings)
        state.pop(addon_id, None)
        _save_state(settings, state)


def get(addon_id: str) -> AddOn:
    addon = CATALOG.get(str(addon_id or "").strip().lower())
    if addon is None:
        raise AddOnError(f"Ein Add-on '{addon_id}' gibt es nicht.")
    return addon


def usable(addon: AddOn, settings: Any, pro: bool) -> tuple[bool, str]:
    """Kann dieses Konto das Add-on gerade nutzen? Returns: (ja, warum nicht)."""
    if not addon.werkstatt:
        return True, ""
    if not pro:
        return False, "Braucht den User mode — und der gehört zu Ultra."
    if not getattr(settings, "vm_user_mode", False):
        return False, "Wirkt erst mit eingeschaltetem User mode (Einstellungen → virtual machine)."
    return True, ""


def active_ids(settings: Any, pro: bool = True) -> list[str]:
    """Installiert, eingeschaltet und nutzbar -- nur diese sieht das Modell.

    Die Modell-Anbieter (NVIDIA NIM, Mistral) gehoeren nicht dazu: sie sind
    kein Werkzeug und kein Befehl im Chat.
    """
    state = load_state(settings)
    aktiv = []
    for addon in CATALOG.values():
        if addon.id in MODEL_ADDONS:
            continue
        eintrag = state.get(addon.id) or {}
        if eintrag.get("installed") and eintrag.get("enabled") and usable(addon, settings, pro)[0]:
            aktiv.append(addon.id)
    return aktiv


def active(settings: Any, addon_id: str, pro: bool = True) -> bool:
    return addon_id in active_ids(settings, pro)


def volume_prefix(settings: Any) -> str:
    """Datentraeger je Konto: der Kontoordner, gehasht -- nie der Name selbst."""
    kennung = hashlib.sha256(str(_data_dir(settings).resolve()).encode()).hexdigest()[:12]
    return f"aquaticy-addon-{kennung}-"


def volume_name(settings: Any, addon_id: str) -> str:
    return volume_prefix(settings) + addon_id


def mounts(settings: Any) -> dict[str, str]:
    """Welche Datentraeger in die virtual machine gehoeren: nur eingeschaltete.

    Ausgeschaltete bleiben liegen, sind aber nicht eingehaengt -- Aquaticy
    kommt dann weder an das Programm noch an die Anmeldung heran.
    """
    if not getattr(settings, "vm_user_mode", False):
        return {}
    state = load_state(settings)
    ergebnis: dict[str, str] = {}
    webapp = False
    for addon_id in active_ids(settings, pro=True):
        addon = CATALOG[addon_id]
        if not addon.programm:
            continue
        ergebnis[volume_name(settings, addon_id)] = f"{MOUNT_ROOT}/{addon_id}"
        webapp = webapp or addon.programm == "webapp"
    if webapp and (state.get(FIREFOX) or {}).get("installed"):
        ergebnis[volume_name(settings, FIREFOX)] = f"{MOUNT_ROOT}/{FIREFOX}"
    return ergebnis


def github_write_level(rechte: dict[str, str]) -> str:
    """Was Aquaticy bei GitHub aendern darf: "nein", "branches" oder "alles" (15.0.0)."""
    return "branches" if rechte.get("inhalte") == "aendern" else "nein"


def github_reads_content(rechte: dict[str, str]) -> bool:
    return rechte.get("inhalte") in ("ja", "aendern")


def github_token(settings: Any) -> str:
    return str(getattr(settings, "github_token", "") or "").strip()


def feeds_of(settings: Any) -> list[str]:
    feeds = (load_state(settings).get("feeds") or {}).get("feeds") or []
    return [str(feed) for feed in feeds if isinstance(feed, str)][:MAX_FEEDS]


def retire_removed(settings: Any) -> list[str]:
    """Raeumt weggefallene Add-ons auf (12.6.6 Luna: Telegram Web) -- einmal.

    Der Eintrag verschwindet aus ``addons.json``; war das Add-on installiert, geht auch
    sein Datentraeger samt Anmeldung weg (soweit Docker oder Podman gerade antwortet --
    sonst bleibt er unbenutzt liegen und geht mit dem Konto).

    Returns: die aufgeraeumten Kennungen.
    """
    try:
        roh = json.loads(_state_path(settings).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    eintraege = roh.get("addons") if isinstance(roh, dict) else None
    if not isinstance(eintraege, dict):
        return []
    weg = [key for key in RETIRED if key in eintraege]
    if not weg:
        return []
    if any(isinstance(eintraege[key], dict) and eintraege[key].get("installed") for key in weg):
        with contextlib.suppress(Exception):
            from aquaticy import sandbox as werkstatt

            runtime = werkstatt.find_runtime()
            if runtime is not None:
                for key in weg:
                    werkstatt.remove_addon_volume(runtime, volume_name(settings, key))
    with _lock(settings):
        _save_state(settings, load_state(settings))
    return weg


def public_view(settings: Any, pro: bool) -> dict[str, Any]:
    """Was der Browser sehen darf -- ohne ein einziges Geheimnis."""
    retire_removed(settings)
    state = load_state(settings)
    liste = []
    for addon in CATALOG.values():
        eintrag = state.get(addon.id) or {}
        ok, warum = usable(addon, settings, pro)
        roh = eintrag.get("login")
        anmeldung: dict[str, Any] = roh if isinstance(roh, dict) else {}
        if addon.login == "token":
            anmeldung = {**anmeldung, "token_set": bool(github_token(settings))}
        laeuft = installing(settings, addon.id)
        status = str(eintrag.get("status") or ("bereit" if eintrag.get("installed") else ""))
        if status == "installiert gerade" and not laeuft:

            status, eintrag["message"] = "fehler", "Die Installation wurde unterbrochen."
        liste.append({
            "id": addon.id,
            "name": addon.name,
            "icon": addon.icon,
            "group": addon.group,
            "summary": addon.summary,
            "login_kind": addon.login,
            "werkstatt": addon.werkstatt,
            "vorschlag": addon.vorschlag,
            "anmelden": addon.anmelden,
            "hinweis": addon.hinweis,
            "installed": bool(eintrag.get("installed")),
            "enabled": bool(eintrag.get("enabled")),
            "status": status,
            "message": str(eintrag.get("message") or ""),
            "version": str(eintrag.get("version") or ""),
            "login": {
                "state": str(anmeldung.get("state") or ""),
                "who": str(anmeldung.get("who") or ""),
                "at": anmeldung.get("at") or 0,
                **({"token_set": anmeldung["token_set"]} if "token_set" in anmeldung else {}),
            },
            "feeds": feeds_of(settings) if addon.id == "feeds" else [],

            "command": "" if addon.id in MODEL_ADDONS else f"/{addon.id}",
            "inhalt": list(PLUGIN_CONTENT.get(addon.id, ())),
            "rechte": rights_of(settings, addon.id),
            "rechte_katalog": [
                {"key": recht.key, "label": recht.label,
                 "options": [{"value": v, "label": t} for v, t in recht.options],
                 "nur_wenn": list(recht.nur_wenn) if recht.nur_wenn else None}
                for recht in RIGHTS.get(addon.id, ())
            ],
            "usable": ok,
            "reason": warum,
        })
    return {
        "addons": liste,
        "pro": pro,
        "user_mode": bool(getattr(settings, "vm_user_mode", False)),
        "active": active_ids(settings, pro),
    }





def _konto(settings: Any) -> str:
    return str(_data_dir(settings).resolve())


def installing(settings: Any, addon_id: str) -> bool:
    job = _jobs.get((_konto(settings), addon_id))
    return job is not None and job.is_alive()


def _check_allowed(addon: AddOn, settings: Any, pro: bool) -> None:
    if addon.werkstatt and not pro:
        raise AddOnError(
            f"{addon.name} läuft in der virtual machine im User mode — das gehört zu Ultra."
        )


def install(
    settings: Any, addon_id: str, pro: bool, *, wait: bool = False, on_done: Any = None
) -> dict[str, Any]:
    """Installiert ein Add-on. Mit Programm laeuft das im Hintergrund weiter.

    Returns: der neue Eintrag.
    """
    addon = get(addon_id)
    _check_allowed(addon, settings, pro)
    if installing(settings, addon.id):
        raise AddOnError(f"{addon.name} wird gerade schon installiert.")
    if not addon.programm:
        return _update(settings, addon.id, installed=True, enabled=True, status="bereit",
                       message="", installed_at=int(time.time()))
    eintrag = _update(settings, addon.id, status="installiert gerade",
                      message="Wird geladen und geprüft …", installed=bool(
                          (load_state(settings).get(addon.id) or {}).get("installed")))
    job = threading.Thread(
        target=_install_job, args=(settings, addon, on_done), name=f"addon-{addon.id}",
        daemon=True,
    )
    _jobs[(_konto(settings), addon.id)] = job
    job.start()
    if wait:
        job.join()
        return load_state(settings).get(addon.id) or {}
    return eintrag


def _last_json(text: str) -> dict[str, Any]:
    for zeile in reversed((text or "").strip().splitlines()):
        zeile = zeile.strip()
        if zeile.startswith("{"):
            with contextlib.suppress(ValueError):
                wert = json.loads(zeile)
                if isinstance(wert, dict):
                    return wert
    return {}


def _helper(box: Any, *args: str, timeout: int = INSTALL_TIMEOUT) -> dict[str, Any]:
    """Ruft aquaticy-addons in der Installations-virtual machine auf."""
    fertig = box.addon_helper(*args, timeout=timeout)
    antwort = _last_json(fertig.stdout)
    if not antwort:
        raise AddOnError(
            "Der Installer hat nicht geantwortet: "
            + (fertig.stderr.strip() or fertig.stdout.strip() or "keine Ausgabe")[:300]
        )
    if not antwort.get("ok"):
        raise AddOnError(str(antwort.get("fehler") or "Installation fehlgeschlagen."))
    return antwort


def _quelle() -> tuple[str, ...]:
    return ("--quelle", INSTALL_SOURCE) if INSTALL_SOURCE else ()


def _install_job(settings: Any, addon: AddOn, on_done: Any = None) -> None:
    from aquaticy import sandbox as werkstatt

    box = None
    try:
        runtime = werkstatt.find_runtime()
        if runtime is None:
            raise AddOnError(
                "Auf diesem Rechner gibt es keine virtual machine (Docker oder Podman) — ohne sie "
                "installiert Aquaticy nichts."
            )
        image = getattr(settings, "vm_desktop_image", "") or werkstatt.DESKTOP_IMAGE


        werkstatt.ensure_image(
            runtime, image, build=True,
            progress=lambda text: _update(settings, addon.id, message=text))
        vols = {volume_name(settings, addon.id): f"{MOUNT_ROOT}/{addon.id}"}
        if addon.programm == "webapp":
            vols[volume_name(settings, FIREFOX)] = f"{MOUNT_ROOT}/{FIREFOX}"
        for volume in vols:
            werkstatt.ensure_addon_volume(runtime, volume, image)
        box = werkstatt.Sandbox(
            image=image, user_mode=True, headless=True, addon_mounts=vols,
            browser_agent=werkstatt.browser_agent(settings), memory_mb=1024, cpus=1,
        )
        box.runtime = runtime
        box.ensure()
        info: dict[str, Any]
        if addon.programm == "webapp":
            firefox = load_state(settings).get(FIREFOX) or {}
            vorhanden = _helper(box, "status", f"{MOUNT_ROOT}/{FIREFOX}", timeout=60)
            if not (firefox.get("installed") and vorhanden.get("installiert")):
                _update(settings, addon.id, message="Lädt Firefox (ESR) von mozilla.org …")
                geladen = _helper(box, "install", "firefox", f"{MOUNT_ROOT}/{FIREFOX}", *_quelle())
                _update(settings, FIREFOX, installed=True, version=geladen.get("version", ""),
                        installed_at=int(time.time()))
            info = _helper(
                box, "webapp", f"{MOUNT_ROOT}/{addon.id}",
                "--firefox", f"{MOUNT_ROOT}/{FIREFOX}",
                "--adresse", addon.adresse,
                "--zusatz", werkstatt.browser_agent(settings).split("Falkon/3.2", 1)[-1].strip(),
                timeout=60,
            )
            info["version"] = (load_state(settings).get(FIREFOX) or {}).get("version", "")
        else:
            quelle = {"signal": "signal.org", "blender": "blender.org"}.get(addon.programm, "")
            _update(settings, addon.id, message=f"Lädt {addon.name} von {quelle} …")
            info = _helper(box, "install", addon.programm, f"{MOUNT_ROOT}/{addon.id}", *_quelle())
        _update(settings, addon.id, installed=True, enabled=True, status="bereit", message="",
                version=str(info.get("version") or ""), installed_at=int(time.time()))
    except Exception as exc:
        meldung = str(exc) or type(exc).__name__
        vorher = load_state(settings).get(addon.id) or {}
        _update(settings, addon.id, status="fehler", message=meldung[:400],
                installed=bool(vorher.get("installed") and vorher.get("version")))
    finally:
        if box is not None:
            with contextlib.suppress(Exception):
                box.stop("Installation fertig")
        if on_done is not None:
            with contextlib.suppress(Exception):
                on_done()


def set_enabled(settings: Any, addon_id: str, on: bool, pro: bool) -> dict[str, Any]:
    addon = get(addon_id)
    eintrag = load_state(settings).get(addon.id) or {}
    if not eintrag.get("installed"):
        raise AddOnError(f"{addon.name} ist nicht installiert.")
    if addon.id in MODEL_ADDONS:
        raise AddOnError(f"{addon.name} hat keinen Schalter. Zum Abschalten deinstallieren — "
                         "dann ist auch der Schlüssel weg.")
    if on:
        _check_allowed(addon, settings, pro)
    return _update(settings, addon.id, enabled=bool(on))


def uninstall(settings: Any, addon_id: str, pro: bool = True) -> dict[str, Any]:
    """Entfernt ein Add-on ganz: Programm, Anmeldung, Token, Feed-Liste.

    Die laufende virtual machine muss vorher weg (der Aufrufer baut sie ab), sonst
    haelt sie den Datentraeger fest.
    """
    addon = get(addon_id)
    if installing(settings, addon.id):
        raise AddOnError(f"{addon.name} wird gerade installiert — erst danach deinstallieren.")
    entfernt: list[str] = []
    if addon.programm:
        from aquaticy import sandbox as werkstatt

        runtime = werkstatt.find_runtime()
        if runtime is not None:
            if werkstatt.remove_addon_volume(runtime, volume_name(settings, addon.id)):
                entfernt.append(addon.id)
            andere_webapps = [
                other for other in active_or_installed(settings)
                if other != addon.id and CATALOG[other].programm == "webapp"
            ]
            if addon.programm == "webapp" and not andere_webapps:
                if werkstatt.remove_addon_volume(runtime, volume_name(settings, FIREFOX)):
                    entfernt.append("firefox")
                _drop(settings, FIREFOX)
        elif (load_state(settings).get(addon.id) or {}).get("installed"):
            raise AddOnError(
                "Ohne Docker oder Podman kommt Aquaticy nicht an den Datentraeger heran — "
                "deinstallieren geht erst, wenn die virtual machine wieder erreichbar ist."
            )
    if addon.login == "token":
        forget_github_token(settings)
    _drop(settings, addon.id)
    return {"removed": addon.id, "volumes": entfernt}


def installed(settings: Any, addon_id: str) -> bool:
    """Ist das Add-on fuer dieses Konto installiert (egal, ob an oder aus)?"""
    return bool((load_state(settings).get(addon_id) or {}).get("installed"))


def mark_installed(settings: Any, addon_id: str) -> None:
    """Traegt ein Add-on als installiert ein -- fuer Schluessel von vor 12.0.0 Luna."""
    if not installed(settings, addon_id):
        _update(settings, get(addon_id).id, installed=True, enabled=True, status="bereit",
                message="", installed_at=int(time.time()))


def active_or_installed(settings: Any) -> list[str]:
    state = load_state(settings)
    return [key for key in CATALOG if (state.get(key) or {}).get("installed")]





def _env_target(settings: Any) -> Path:
    from aquaticy.config import DEFAULT_ENV_PATH, find_env_file

    return Path(getattr(settings, "env_path", None) or find_env_file() or DEFAULT_ENV_PATH)


def _write_secret(settings: Any, key: str, value: str) -> None:
    """Legt ein Token ab -- bei einem Konto verschluesselt in seinem Schluesselbund.

    Bis 9.5.15 stand das GitHub-Token im Klartext in der .env des Kontos.
    Ohne Konten (Kommandozeile, eigener Rechner) bleibt es in der .env des
    Betreibers, geschuetzt wie die anderen Eintraege dort.
    """
    tresor = getattr(settings, "secret_vault", None)
    if tresor is not None:
        tresor.set_secret(key, value)
    else:
        from aquaticy.config import write_env_file

        ziel = write_env_file({key: value}, _env_target(settings))
        with contextlib.suppress(Exception):
            from aquaticy.memory import secure_file

            secure_file(ziel)
    with contextlib.suppress(Exception):
        settings.github_token = value


def forget_github_token(settings: Any) -> None:
    if (github_token(settings) or getattr(settings, "secret_vault", None) is not None
            or _env_target(settings).is_file()):
        with contextlib.suppress(OSError, ValueError):
            _write_secret(settings, GITHUB_TOKEN_KEY, "")


TOKEN_RE = re.compile(r"^[A-Za-z0-9_]{20,255}$")


def github_login(
    settings: Any, token: str, *, client: httpx.Client | None = None
) -> dict[str, Any]:
    """Prueft ein GitHub-Token bei GitHub und legt es ab, wenn es gilt."""
    eintrag = load_state(settings).get("github") or {}
    if not eintrag.get("installed"):
        raise AddOnError("Erst GitHub installieren, dann anmelden.")
    token = (token or "").strip()
    if not TOKEN_RE.fullmatch(token):
        raise AddOnError("Das sieht nicht nach einem GitHub-Token aus (ghp_…, github_pat_…).")
    eigener = client is None
    client = client or httpx.Client(timeout=15)
    try:
        antwort = client.get(f"{GITHUB_API}/user", headers=_github_headers(token),
                             follow_redirects=False)
    except httpx.HTTPError as exc:
        raise AddOnError(f"GitHub ist gerade nicht erreichbar ({type(exc).__name__}).") from exc
    finally:
        if eigener:
            client.close()
    if antwort.status_code == 401:
        raise AddOnError("GitHub kennt dieses Token nicht (abgelaufen oder vertippt).")
    if antwort.status_code != 200:
        raise AddOnError(f"GitHub hat mit {antwort.status_code} geantwortet.")
    try:
        body = antwort.json()
        login = str(body.get("login") or "")
        if not re.fullmatch(r"[A-Za-z0-9-]{1,100}", login):
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise AddOnError("GitHub hat keine gültigen Kontodaten geliefert.") from exc
    rechte = [teil.strip() for teil in antwort.headers.get("x-oauth-scopes", "").split(",")
              if teil.strip()]
    _write_secret(settings, GITHUB_TOKEN_KEY, token)
    _update(settings, "github", login={"state": "angemeldet", "who": login,
                                       "at": int(time.time())})
    warnung = ""
    if any(recht in {"repo", "delete_repo", "admin:org", "workflow", "write:packages"}
           for recht in rechte):
        warnung = ("Dieses Token darf auch schreiben. Aquaticy nutzt es nur lesend — sicherer "
                   "ist trotzdem ein Token mit nur Leserechten.")
    return {"who": login, "warning": warnung}


def mark_login(settings: Any, addon_id: str, state: str) -> dict[str, Any]:
    """Merkt sich, dass der Nutzer sich angemeldet (oder abgemeldet) hat.

    Bei QR-Anmeldungen kann Aquaticy nicht selbst pruefen, ob das Handy
    gekoppelt hat -- es glaubt dem Nutzer und sagt das auch so ("laut dir").
    """
    addon = get(addon_id)
    if not (load_state(settings).get(addon.id) or {}).get("installed"):
        raise AddOnError(f"{addon.name} ist nicht installiert.")
    if state == "angemeldet":
        return _update(settings, addon.id, login={"state": "angemeldet", "who": "laut dir",
                                                  "at": int(time.time())})
    return _update(settings, addon.id, login={"state": "", "who": "", "at": 0})


def logout(settings: Any, addon_id: str) -> dict[str, Any]:
    """Meldet ab: Token weg, bzw. Profil/Daten in der virtual machine geloescht."""
    addon = get(addon_id)
    if addon.login == "token":
        forget_github_token(settings)
    elif addon.programm in ("webapp", "signal"):
        _reset_profile(settings, addon)
    return mark_login(settings, addon.id, "")


def _reset_profile(settings: Any, addon: AddOn) -> None:
    """Loescht die Anmeldung auf dem Datentraeger -- in einem Wegwerf-Behaelter.

    Ohne Netz, ohne Faehigkeiten: dafuer braucht es beides nicht.
    """
    from aquaticy import sandbox as werkstatt

    runtime = werkstatt.find_runtime()
    if runtime is None:
        raise AddOnError("Ohne Docker oder Podman kommt Aquaticy nicht an die Anmeldung heran.")
    image = getattr(settings, "vm_desktop_image", "") or werkstatt.DESKTOP_IMAGE
    teil = "profil" if addon.programm == "webapp" else "daten"
    fertig = werkstatt._runs(
        runtime.binary, "run", "--rm", "--network", "none", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--user", werkstatt.RUN_AS,
        "-v", f"{volume_name(settings, addon.id)}:{MOUNT_ROOT}/{addon.id}",
        image, "aquaticy-addons", "reset", f"{MOUNT_ROOT}/{addon.id}", teil,
        timeout=120,
    )
    if fertig.returncode != 0:
        raise AddOnError("Abmelden hat nicht geklappt: " + fertig.stdout.strip()[-300:])
    if addon.programm == "webapp":


        fertig = werkstatt._runs(
            runtime.binary, "run", "--rm", "--network", "none", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", werkstatt.RUN_AS,
            "-v", f"{volume_name(settings, addon.id)}:{MOUNT_ROOT}/{addon.id}",
            "-v", f"{volume_name(settings, FIREFOX)}:{MOUNT_ROOT}/{FIREFOX}",
            image, "aquaticy-addons", "webapp", f"{MOUNT_ROOT}/{addon.id}",
            "--firefox", f"{MOUNT_ROOT}/{FIREFOX}", "--adresse", addon.adresse,
            "--zusatz", werkstatt.browser_agent(settings).split("Falkon/3.2", 1)[-1].strip(),
            timeout=120,
        )


def set_feeds(settings: Any, feeds: Any) -> list[str]:
    """Speichert die Feed-Liste. Nur oeffentliche http(s)-Adressen."""
    if not (load_state(settings).get("feeds") or {}).get("installed"):
        raise AddOnError("Erst RSS-Feeds installieren, dann Feeds eintragen.")
    if isinstance(feeds, str):
        feeds = feeds.splitlines()
    if not isinstance(feeds, list):
        raise AddOnError("Feeds bitte als Liste von Adressen.")
    sauber: list[str] = []
    for roh in feeds:
        adresse = str(roh or "").strip()
        if not adresse:
            continue
        teile = urlparse(adresse)
        if teile.scheme not in ("http", "https") or not teile.hostname or len(adresse) > 500:
            raise AddOnError(f"Keine gültige Feed-Adresse: {adresse[:80]}")
        if _private_host(teile.hostname):
            raise AddOnError(f"Feeds nur aus dem Internet, nicht aus dem Heimnetz: {adresse[:80]}")
        if adresse not in sauber:
            sauber.append(adresse)
    if len(sauber) > MAX_FEEDS:
        raise AddOnError(f"Höchstens {MAX_FEEDS} Feeds.")
    _update(settings, "feeds", feeds=sauber,
            login={"state": "angemeldet" if sauber else "", "who": f"{len(sauber)} Feeds",
                   "at": int(time.time())})
    return sauber


def _private_host(host: str) -> bool:
    """Heimnetz-Namen und -Adressen -- ohne DNS, das kommt beim Abruf."""
    import ipaddress

    host = host.strip("[]").lower()
    if host in {"localhost", "fritz.box"} or host.endswith((".local", ".lan", ".home", ".internal",
                                                ".localhost", ".fritz.box")):
        return True
    with contextlib.suppress(ValueError):
        return not ipaddress.ip_address(host).is_global
    return False





_throttle_lock = threading.Lock()
_last_call: dict[str, float] = {}


def _takt(host: str, abstand: float = 1.05) -> None:
    """Eine Anfrage je Sekunde und Server -- fuer alle Konten zusammen."""
    with _throttle_lock:
        jetzt = time.monotonic()
        frei = _last_call.get(host, 0.0) + abstand
        warte = max(0.0, frei - jetzt)
        _last_call[host] = jetzt + warte
    if warte:
        time.sleep(warte)


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": user_agent(),
    }


REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
REF_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
PATH_RE = re.compile(r"^[A-Za-z0-9 _.,@+()/-]{0,400}$")
GITHUB_ACTIONS = ("ich", "repos", "repo", "issues", "issue", "pulls", "pull", "datei",
                  "commits", "commit", "vergleich", "suche", "baum", "branches", "review")
MAX_GITHUB_TEXT = 20_000


def _kurz(text: Any, grenze: int = 600) -> str:
    text = str(text or "")
    return text if len(text) <= grenze else text[: grenze - 1] + "…"


def github_call(
    token: str,
    action: str,
    *,
    repo: str = "",
    number: Any = None,
    path: str = "",
    ref: str = "",
    state: str = "open",
    query: str = "",
    client: httpx.Client | None = None,
    nur_oeffentlich: bool = False,
    inhalte: bool = True,
    page: Any = 1,
    start_line: Any = 1,
    max_lines: Any = 300,
    recursive: bool = True,
    paths: Any = None,
    base: str = "",
) -> dict[str, Any]:
    """Liest bei GitHub -- ausschliesslich mit GET (Schreiben: aquaticy/github_write.py).

    Args:
        nur_oeffentlich: Recht "Nur öffentliche Repos". Private tauchen weder in
            Listen noch in der Suche auf, und ein privates Repo direkt zu lesen
            wird abgelehnt -- geprueft bei GitHub, nicht am Namen.
        inhalte: Recht "Auch Inhalte lesen". Ohne gibt es Ordner und Listen,
            aber keine Dateiinhalte.
    """
    from aquaticy import github_repo

    link_tail = ""
    if isinstance(repo, str) and repo.startswith("https://github.com/") and not ref:
        from urllib.parse import unquote

        segments = urlparse(repo).path.strip("/").split("/")
        if len(segments) > 3 and segments[2] in ("tree", "blob"):
            link_tail = unquote("/".join(segments[3:]))
    if not token:
        return {"error": "GitHub ist nicht angemeldet. Das macht der Nutzer im Add-on-Fenster."}
    action = (action or "").strip().lower()
    action = {"tree": "baum", "file": "datei", "search": "suche", "compare": "vergleich",
              "code-review": "review"}.get(action, action)
    if action not in GITHUB_ACTIONS:
        return {"error": f"Unbekannte Aktion. Moeglich: {', '.join(GITHUB_ACTIONS)}."}
    repo = (repo or "").strip().strip("/")
    braucht_repo = action in {"repo", "issues", "issue", "pulls", "pull", "datei", "commits",
                             "commit", "vergleich", "baum", "branches", "review"}
    # 15.0.1: "Aquaticy-Ai" ohne Besitzer -- das Repo wird in den eigenen Repos gesucht.
    kurz = ""
    if braucht_repo and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", repo or "") and repo not in (
            ".", ".."):
        kurz, repo = repo, f"eigenes/{repo}"
    try:
        if repo or braucht_repo:
            repo, ref, path, number = github_repo.target(repo, ref, path, number)
        if any(type(n) not in (str, int) for n in (page, start_line, max_lines)):
            raise ValueError
        if not isinstance(recursive, bool):
            raise ValueError
        page, start_line, max_lines = int(page), int(start_line), int(max_lines)
        if not (1 <= page <= 1000 and 1 <= start_line <= 400_000 and 1 <= max_lines <= 400):
            raise ValueError
        if paths is not None and (not isinstance(paths, list) or len(paths) > 6 or not all(
                isinstance(p, str) and p and github_repo.valid_path(p) for p in paths)):
            raise ValueError
    except github_repo.GitHubError as exc:
        return {"error": str(exc)}
    except (TypeError, ValueError):
        return {"error": "Ungültige Seite, Zeile oder Dateiliste. Höchstens sechs Dateien "
                         "und 400 Zeilen je Abruf."}
    if action == "review" and not inhalte:
        return {"error": "Dateiinhalte sind nicht freigegeben. Wähle im GitHub-Add-on unter "
                         "Rechte: Auch Inhalte lesen."}
    if action == "review" and number not in (None, ""):
        try:
            if int(str(number).strip()) <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return {"error": "number bitte als ganze Zahl."}


    if braucht_repo and (not REPO_RE.fullmatch(repo)
                         or any(t in (".", "..") for t in repo.split("/"))):
        return {"error": "repo bitte als 'besitzer/name'."}
    nummer = 0
    if action in {"issue", "pull"}:
        try:
            nummer = int(str(number).strip())
        except (TypeError, ValueError):
            return {"error": "number bitte als ganze Zahl."}
        if nummer <= 0:
            return {"error": "number bitte als ganze Zahl."}
    path = (path or "").strip().strip("/")
    if not github_repo.valid_path(path):
        return {"error": "Ungueltiger Pfad."}
    state = state if state in ("open", "closed", "all") else "open"
    base = (base or "").strip()
    if action in ("commit", "vergleich"):
        if not ref or not REF_RE.fullmatch(ref) or ".." in ref:
            return {"error": "ref bitte als Commit-SHA, Branch oder Tag."}
        if action == "vergleich" and (not base or not REF_RE.fullmatch(base) or ".." in base):
            return {"error": "base bitte als Branch, Tag oder Commit (zum Beispiel main)."}

    eigener = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=False)

    cache: dict[str, Any] = {}
    requests = 0

    def hole(pfad: str, *, _fresh: bool = False, **params: Any) -> Any:
        nonlocal requests
        schluessel = json.dumps([pfad, params], sort_keys=True)
        if schluessel in cache and not _fresh:
            return cache[schluessel]
        if requests >= 30:
            raise github_repo.GitHubError("Zu viele Abrufe. Grenze die Prüfung ein.")
        requests += 1
        _takt("api.github.com")
        parameter = {k: v for k, v in params.items() if v not in ("", None)}
        try:
            cache[schluessel] = github_repo.request(client, pfad, _github_headers(token),
                                                    parameter)
        except github_repo.Missing:
            # 15.0.1: Ein oeffentliches Repo geht auch ohne Token (wenn das Token es nicht
            # sieht, etwa weil es einem anderen Konto gehoert). Sonst: die genaue Ursache.
            if not repo or not pfad.startswith(f"/repos/{repo}"):
                raise
            ohne = {k: v for k, v in _github_headers(token).items() if k != "Authorization"}
            try:
                cache[schluessel] = github_repo.request(client, pfad, ohne, parameter)
            except github_repo.GitHubError:
                # Sieht das Token das Repo selbst? Dann fehlt nur Branch, Pfad oder Nummer --
                # kein Rechteproblem (etwa ref "main", wenn der Standard-Branch anders heisst).
                if pfad != f"/repos/{repo}":
                    daten: Any = None
                    with contextlib.suppress(github_repo.GitHubError, httpx.HTTPError,
                                             ValueError):
                        daten = github_repo.request(client, f"/repos/{repo}",
                                                    _github_headers(token), {})
                    if isinstance(daten, dict) and daten.get("full_name"):
                        raise github_repo.Missing(github_repo.missing_in_repo(
                            repo, str(daten.get("default_branch") or ""), pfad,
                            parameter)) from None
                info = github_repo.diagnose(client, repo, _github_headers(token))
                raise github_repo.Missing(github_repo.missing_reason(
                    repo, info["login"], token, scopes=info["scopes"],
                    invited=info["invited"])) from None
        return cache[schluessel]

    try:
        if kurz:
            eigene = hole("/user/repos", per_page=100, sort="updated")
            passend = [str(r.get("full_name") or "") for r in eigene
                       if str(r.get("name") or "").casefold() == kurz.casefold()]
            if not passend or not REPO_RE.fullmatch(passend[0]):
                raise AddOnError(f"Ein Repo „{kurz}“ finde ich in deinen Repos nicht. Nenne es "
                                 "als besitzer/name, zum Beispiel jonas/projekt.")
            repo = passend[0]
        if (nur_oeffentlich and braucht_repo
                and hole(f"/repos/{repo}").get("private") is not False):
            raise AddOnError(
                "Das Repo ist privat -- und der Nutzer hat Aquaticy nur öffentliche Repos "
                "erlaubt (Add-on GitHub -> Rechte)."
            )
        if link_tail and action in {"baum", "review", "datei", "commits"}:
            ref, path = github_repo.resolve_link(hole, repo, link_tail)
        if action == "review":
            try:
                review_number = int(str(number or 0).strip())
            except (ValueError, TypeError):
                raise github_repo.GitHubError("number bitte als ganze Zahl.") from None
            if review_number < 0:
                raise github_repo.GitHubError("number bitte als ganze Zahl.")
            ergebnis = github_repo.review(hole, repo, ref, path, page, review_number, paths,
                                           public_only=nur_oeffentlich)
        elif action == "baum":
            ergebnis = github_repo.tree(hole, repo, ref, path, page, bool(recursive))
        elif action == "branches":
            entries = hole(f"/repos/{repo}/branches", per_page=30, page=page)
            ergebnis = {"branches": [{"name": e.get("name"),
                                      "sha": (e.get("commit") or {}).get("sha")}
                                     for e in entries[:30]],
                        "next_page": page + 1 if len(entries) == 30 else None}
        elif action == "datei":
            ergebnis = github_repo.read_file(hole, repo, path, ref, start=start_line,
                                              lines=max_lines, page=page, contents=inhalte)
        else:
            ergebnis = _github_action(hole, action, repo, nummer, path, ref, state, query,
                                      nur_oeffentlich=nur_oeffentlich, inhalte=inhalte,
                                      page=page, base=base)
        if braucht_repo:
            ergebnis.setdefault("repo", repo)
            ergebnis.setdefault("privat", cache.get(
                json.dumps([f"/repos/{repo}", {}], sort_keys=True), {}).get("private") is not False)
    except (AddOnError, github_repo.GitHubError) as exc:
        return {"error": str(exc)}
    except (httpx.HTTPError, ValueError) as exc:
        return {"error": f"GitHub nicht erreichbar ({type(exc).__name__})."}
    except (AttributeError, TypeError, KeyError, IndexError):


        return {"error": "GitHub hat unerwartet geantwortet."}
    finally:
        if eigener:
            client.close()
    try:
        return github_repo.bound(ergebnis, MAX_GITHUB_TEXT)
    except github_repo.GitHubError as exc:
        return {"error": str(exc)}


def _github_dateien(dateien: list[Any], inhalte: bool, grenze: int = 1500
                    ) -> list[dict[str, Any]]:
    """Geaenderte Dateien eines Commits oder Vergleichs -- Patch nur mit Inhalte-Recht."""
    from aquaticy import github_repo

    return [{"datei": d.get("filename"), "status": d.get("status"),
             "plus": d.get("additions"), "minus": d.get("deletions"),
             **({"patch": github_repo.redact(str(d.get("patch", "")))[:grenze],
                 "patch_gekuerzt": len(str(d.get("patch", ""))) > grenze} if inhalte else {})}
            for d in dateien if isinstance(d, dict)]


def _github_action(hole: Any, action: str, repo: str, nummer: int, path: str, ref: str,
                   state: str, query: str, *, nur_oeffentlich: bool = False,
                   inhalte: bool = True, page: int = 1, base: str = "") -> dict[str, Any]:
    from aquaticy import github_repo

    if action == "ich":
        ich = hole("/user")
        return {"login": ich.get("login"), "name": ich.get("name"),
                "public_repos": ich.get("public_repos"), "private_repos":
                None if nur_oeffentlich else ich.get("total_private_repos")}
    if action == "repos":
        repos = hole("/user/repos", per_page=30, sort="updated",
                     visibility="public" if nur_oeffentlich else "", page=page)
        more = len(repos) == 30
        if nur_oeffentlich:
            repos = [r for r in repos if r.get("private") is False]
        return {"repos": [{"name": r.get("full_name"), "privat": r.get("private"),
                           "beschreibung": _kurz(r.get("description"), 200),
                           "sprache": r.get("language"), "aktualisiert": r.get("updated_at")}
                          for r in repos[:30]], "next_page": page + 1 if more else None}
    if action == "repo":
        r = hole(f"/repos/{repo}")
        return {"name": r.get("full_name"), "privat": r.get("private"),
                "beschreibung": _kurz(r.get("description"), 500), "sterne":
                r.get("stargazers_count"), "offene_issues": r.get("open_issues_count"),
                "standard_branch": r.get("default_branch"), "sprache": r.get("language"),
                "aktualisiert": r.get("updated_at")}
    if action == "issues":
        eintraege = hole(f"/repos/{repo}/issues", state=state, per_page=20)
        return {"issues": [{"nummer": i.get("number"), "titel": i.get("title"),
                            "zustand": i.get("state"), "von": (i.get("user") or {}).get("login"),
                            "kommentare": i.get("comments"), "aktualisiert": i.get("updated_at")}
                           for i in eintraege if "pull_request" not in i][:20]}
    if action == "issue":
        i = hole(f"/repos/{repo}/issues/{nummer}")
        kommentare = hole(f"/repos/{repo}/issues/{nummer}/comments", per_page=20)
        return {"nummer": i.get("number"), "titel": i.get("title"), "zustand": i.get("state"),
                "von": (i.get("user") or {}).get("login"),
                "text": github_repo.redact(_kurz(i.get("body"), 4000)),
                "kommentare": [{"von": (k.get("user") or {}).get("login"),
                                "text": github_repo.redact(_kurz(k.get("body"), 1200))}
                               for k in kommentare[:20]]}
    if action == "pulls":
        eintraege = hole(f"/repos/{repo}/pulls", state=state, per_page=20)
        return {"pulls": [{"nummer": p.get("number"), "titel": p.get("title"),
                           "zustand": p.get("state"), "von": (p.get("user") or {}).get("login"),
                           "entwurf": p.get("draft"), "aktualisiert": p.get("updated_at")}
                          for p in eintraege[:20]]}
    if action == "pull":
        p = hole(f"/repos/{repo}/pulls/{nummer}")
        dateien = hole(f"/repos/{repo}/pulls/{nummer}/files", per_page=10, page=page)
        return {"nummer": p.get("number"), "titel": p.get("title"), "zustand": p.get("state"),
                "von": (p.get("user") or {}).get("login"),
                "text": github_repo.redact(_kurz(p.get("body"), 4000)),
                "gemergt": p.get("merged"), "basis": (p.get("base") or {}).get("ref"),
                "kopf": (p.get("head") or {}).get("ref"),
                "dateien": [{"datei": d.get("filename"), "status": d.get("status"),
                             "plus": d.get("additions"), "minus": d.get("deletions"),
                             **({"patch": github_repo.redact(str(d.get("patch", "")))[:600],
                                 "patch_gekuerzt": len(str(d.get("patch", ""))) > 600}
                                if inhalte else {})}
                            for d in dateien[:10]],
                "next_page": page + 1 if len(dateien) == 10 else None,
                "head_sha": (p.get("head") or {}).get("sha")}
    if action == "commits":
        # Seit 14.4.4: voller SHA (fuer commit/vergleich), Seiten und Filter nach Datei.
        hinweis = ""
        try:
            eintraege = hole(f"/repos/{repo}/commits", sha=ref, path=path, per_page=20,
                             page=page)
        except github_repo.Missing:
            # 15.0.1: "main" oder "master" geraten, der Standard-Branch heisst aber anders.
            if ref.casefold() not in ("main", "master"):
                raise
            eintraege = hole(f"/repos/{repo}/commits", path=path, per_page=20, page=page)
            hinweis = (f"Einen Branch „{ref}“ gibt es nicht. Das sind die Commits des "
                       "Standard-Branches.")
        return {**({"hinweis": hinweis} if hinweis else {}), "commits": [{"sha": c.get("sha") or "",
                             "nachricht": _kurz((c.get("commit") or {}).get("message"), 300),
                             "von": ((c.get("commit") or {}).get("author") or {}).get("name"),
                             "datum": ((c.get("commit") or {}).get("author") or {}).get("date")}
                            for c in eintraege[:20]],
                "next_page": page + 1 if len(eintraege) == 20 else None}
    if action == "commit":
        c = hole(f"/repos/{repo}/commits/{quote(ref, safe='')}", per_page=20, page=page)
        dateien = c.get("files") or []
        return {"sha": c.get("sha"),
                "nachricht": github_repo.redact(_kurz((c.get("commit") or {}).get("message"),
                                                      4000)),
                "von": ((c.get("commit") or {}).get("author") or {}).get("name"),
                "datum": ((c.get("commit") or {}).get("author") or {}).get("date"),
                "eltern": [e.get("sha") for e in c.get("parents") or []][:4],
                "plus": (c.get("stats") or {}).get("additions"),
                "minus": (c.get("stats") or {}).get("deletions"),
                "dateien": _github_dateien(dateien[:20], inhalte),
                "next_page": page + 1 if len(dateien) >= 20 else None}
    if action == "vergleich":
        v = hole(f"/repos/{repo}/compare/{quote(base, safe='')}...{quote(ref, safe='')}",
                 per_page=20, page=page)
        file_page = v if page == 1 else hole(
            f"/repos/{repo}/compare/{quote(base, safe='')}...{quote(ref, safe='')}",
            per_page=20, page=1)
        dateien = file_page.get("files") or []
        offset = (page - 1) * 20
        return {"basis": base, "kopf": ref, "status": v.get("status"),
                "voraus": v.get("ahead_by"), "zurueck": v.get("behind_by"),
                "commits": [{"sha": c.get("sha"),
                             "nachricht": _kurz((c.get("commit") or {}).get("message"), 200)}
                            for c in (v.get("commits") or [])[-20:]],
                "dateien": _github_dateien(dateien[offset:offset + 20], inhalte),
                "dateien_gekuerzt": len(dateien) >= 300,
                "next_page": page + 1 if (offset + 20 < len(dateien)
                                         or len(v.get("commits") or []) == 20) else None}

    q = " ".join(str(query or "").split())[:256]
    if not q:
        raise AddOnError("Wonach suchen? (query)")
    if repo and REPO_RE.fullmatch(repo):
        q = f"{q} repo:{repo}"
    if nur_oeffentlich:
        q = f"{q} is:public"
    treffer = hole("/search/issues", q=q, per_page=20)
    items = (treffer.get("items") or [])[:20]
    if nur_oeffentlich:
        public = []
        for item in items:
            name = str(item.get("repository_url") or "").split("/repos/")[-1]
            if REPO_RE.fullmatch(name) and hole(f"/repos/{name}").get("private") is False:
                public.append(item)
        items = public
    return {"hinweis": "Diese Suche findet nur Issues und Pull Requests, keinen Code. "
                       "Code liest du mit baum, datei oder review.",
            "treffer": [{"repo": str(t.get("repository_url") or "").split("/repos/")[-1],
                         "nummer": t.get("number"), "titel": t.get("title"),
                         "zustand": t.get("state"), "pull_request": "pull_request" in t}
                        for t in items],
            "gesamt": treffer.get("total_count")}



WMO = {
    0: "klar", 1: "überwiegend klar", 2: "teils bewölkt", 3: "bedeckt", 45: "Nebel",
    48: "Nebel mit Reif", 51: "leichter Nieselregen", 53: "Nieselregen",
    55: "starker Nieselregen", 56: "gefrierender Nieselregen", 57: "gefrierender Nieselregen",
    61: "leichter Regen", 63: "Regen", 65: "starker Regen", 66: "gefrierender Regen",
    67: "gefrierender Regen", 71: "leichter Schneefall", 73: "Schneefall",
    75: "starker Schneefall", 77: "Schneegriesel", 80: "leichte Regenschauer",
    81: "Regenschauer", 82: "heftige Regenschauer", 85: "Schneeschauer",
    86: "starke Schneeschauer", 95: "Gewitter", 96: "Gewitter mit Hagel",
    99: "schweres Gewitter mit Hagel",
}


def _wetterlage(code: Any) -> str:
    """Der WMO-Wettercode als Wort ("unbekannt", wenn er fehlt oder fremd ist)."""
    if (isinstance(code, bool) or not isinstance(code, (int, float))
            or not math.isfinite(code) or int(code) != code):
        return "unbekannt"
    return WMO.get(int(code), "unbekannt")


def weather(place: str, days: Any = 3, *, client: httpx.Client | None = None) -> dict[str, Any]:
    """Wetter von Open-Meteo: erst den Ort finden, dann die Vorhersage."""
    ort = " ".join(str(place or "").split())[:120]
    if not ort:
        return {"error": "Fuer welchen Ort? (place)"}
    try:
        tage = max(1, min(7, int(str(days or 3))))
    except ValueError:
        tage = 3
    name, _, zusatz = ort.partition(",")
    eigener = client is None
    client = client or httpx.Client(timeout=15, headers={"User-Agent": user_agent()})
    try:
        _takt("open-meteo.com")
        geo = client.get(OPEN_METEO_GEO, params={"name": name.strip(), "count": 5,
                                                 "language": "de", "format": "json"})
        geo.raise_for_status()
        raw_places = _objekt(geo.json()).get("results")
        orte = [item for item in raw_places if isinstance(item, dict)] \
            if isinstance(raw_places, list) else []
        if zusatz.strip():
            suffix = zusatz.strip().casefold()
            if len(suffix) == 2 and suffix.isalpha():
                orte = [o for o in orte if str(o.get("country_code") or "").casefold() == suffix]
            else:
                orte = [o for o in orte if any(
                    suffix in str(o.get(k) or "").casefold()
                    for k in ("country", "admin1", "admin2"))]
        if not orte:
            return {"error": f"Einen Ort '{ort}' kennt Open-Meteo nicht."}
        treffer = orte[0]
        _takt("open-meteo.com")
        vorhersage = client.get(OPEN_METEO, params={
            "latitude": treffer["latitude"], "longitude": treffer["longitude"],
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,"
                       "precipitation",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
                     "precipitation_probability_max,wind_speed_10m_max,sunrise,sunset",
            "timezone": "auto", "forecast_days": tage,
        })
        vorhersage.raise_for_status()
        daten = _objekt(vorhersage.json())
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return {"error": f"Open-Meteo nicht erreichbar ({type(exc).__name__})."}
    finally:
        if eigener:
            client.close()
    jetzt = _objekt(daten.get("current"))
    taeglich = _objekt(daten.get("daily"))
    tage_liste = []
    dates = taeglich.get("time")
    for i, datum in enumerate(dates if isinstance(dates, list) else []):
        def feld(name: str, i: int = i) -> Any:
            werte = taeglich.get(name) or []
            return werte[i] if isinstance(werte, list) and i < len(werte) else None

        tage_liste.append({
            "datum": datum, "wetter": _wetterlage(feld("weather_code")),
            "max_c": feld("temperature_2m_max"), "min_c": feld("temperature_2m_min"),
            "niederschlag_mm": feld("precipitation_sum"),
            "regenwahrscheinlichkeit_prozent": feld("precipitation_probability_max"),
            "wind_max_kmh": feld("wind_speed_10m_max"),
            "sonnenaufgang": feld("sunrise"), "sonnenuntergang": feld("sunset"),
        })
    return {
        "ort": ", ".join(str(treffer.get(k)) for k in ("name", "admin1", "country")
                         if treffer.get(k)),
        "jetzt": {"temperatur_c": jetzt.get("temperature_2m"),
                  "gefuehlt_c": jetzt.get("apparent_temperature"),
                  "wetter": _wetterlage(jetzt.get("weather_code")),
                  "wind_kmh": jetzt.get("wind_speed_10m"),
                  "niederschlag_mm": jetzt.get("precipitation"), "zeit": jetzt.get("time")},
        "tage": tage_liste,
        "quelle": "Open-Meteo (open-meteo.com), Daten u. a. vom DWD — CC BY 4.0",
    }





TAGESSCHAU_PER_HOUR = 60
_tagesschau_abrufe: list[float] = []
_tagesschau_lock = threading.Lock()


RESSORTS = {
    "": "", "alle": "", "inland": "inland", "ausland": "ausland",
    "wirtschaft": "wirtschaft", "sport": "sport", "video": "video",
    "investigativ": "investigativ", "wissen": "wissen",
}


def _tagesschau_erlaubt(jetzt: float | None = None) -> bool:
    """Zaehlt einen Abruf -- oder sagt, dass die Stunde voll ist."""
    jetzt = time.time() if jetzt is None else jetzt
    with _tagesschau_lock:
        _tagesschau_abrufe[:] = [t for t in _tagesschau_abrufe if jetzt - t < 3600]
        if len(_tagesschau_abrufe) >= TAGESSCHAU_PER_HOUR:
            return False
        _tagesschau_abrufe.append(jetzt)
        return True


def _objekt(wert: Any) -> dict[str, Any]:
    """Eine JSON-Antwort als Objekt -- alles andere (Liste, null, Text) als leer."""
    return wert if isinstance(wert, dict) else {}


def _eigener_client(client: httpx.Client | None) -> tuple[httpx.Client, bool]:
    if client is not None:
        return client, False
    return httpx.Client(timeout=15, headers={"User-Agent": user_agent()}), True


def news(topic: str = "", query: str = "", limit: Any = 10, *,
         client: httpx.Client | None = None) -> dict[str, Any]:
    """Meldungen der Tagesschau: nach Thema oder als Suche."""
    try:
        menge = max(1, min(20, int(str(limit or 10))))
    except ValueError:
        menge = 10
    thema = str(topic or "").strip().lower()
    if thema not in RESSORTS:
        return {"error": "Unbekanntes Thema. Moeglich: " + ", ".join(k for k in RESSORTS if k)}
    suche = " ".join(str(query or "").split())[:120]
    if not _tagesschau_erlaubt():
        return {"error": "Die Tagesschau erlaubt 60 Abrufe pro Stunde -- die sind gerade "
                         "aufgebraucht. In ein paar Minuten geht es wieder."}
    client, eigener = _eigener_client(client)
    try:
        _takt("tagesschau.de")
        if suche:
            antwort = client.get(f"{TAGESSCHAU}/search/",
                                 params={"searchText": suche, "pageSize": menge})
        else:
            antwort = client.get(f"{TAGESSCHAU}/news/",
                                 params={"ressort": RESSORTS[thema]} if RESSORTS[thema] else {})
        antwort.raise_for_status()
        daten = _objekt(antwort.json())
    except (httpx.HTTPError, ValueError) as exc:
        return {"error": f"Tagesschau nicht erreichbar ({type(exc).__name__})."}
    finally:
        if eigener:
            client.close()
    roh = daten.get("searchResults") if suche else daten.get("news")
    meldungen = []
    for eintrag in (roh or [])[:menge]:
        if not isinstance(eintrag, dict):
            continue
        meldungen.append({
            "titel": _kurz(eintrag.get("title"), 200),
            "oberzeile": _kurz(eintrag.get("topline"), 120),
            "anriss": _kurz(eintrag.get("firstSentence"), 400),
            "datum": eintrag.get("date"),
            "thema": eintrag.get("ressort"),
            "link": eintrag.get("shareURL") or eintrag.get("detailsweb"),
        })
    return {"meldungen": meldungen, "thema": thema or "alle", "suche": suche,
            "quelle": "tagesschau.de (ARD-aktuell) — nur privater Gebrauch"}


def wikipedia(query: str, lang: str = "de", *,
              client: httpx.Client | None = None) -> dict[str, Any]:
    """Sucht einen Artikel und gibt die Kurzfassung des besten Treffers."""
    begriff = " ".join(str(query or "").split())[:200]
    if not begriff:
        return {"error": "Wonach nachschlagen? (query)"}
    sprache = lang if lang in ("de", "en") else "de"
    basis = WIKIPEDIA.format(sprache=sprache)
    client, eigener = _eigener_client(client)
    try:
        _takt("wikipedia.org")
        suche = client.get(f"{basis}/w/rest.php/v1/search/page",
                           params={"q": begriff, "limit": 5})
        suche.raise_for_status()
        seiten = [s for s in _objekt(suche.json()).get("pages") or [] if isinstance(s, dict)]
        if not seiten:
            return {"error": f"Zu '{begriff}' gibt es keinen Wikipedia-Artikel ({sprache})."}
        schluessel = str(seiten[0].get("key") or seiten[0].get("title") or "")
        _takt("wikipedia.org")
        zusammenfassung = client.get(f"{basis}/api/rest_v1/page/summary/"
                                     + quote(schluessel, safe=""))
        zusammenfassung.raise_for_status()
        artikel = _objekt(zusammenfassung.json())
    except (httpx.HTTPError, ValueError) as exc:
        return {"error": f"Wikipedia nicht erreichbar ({type(exc).__name__})."}
    finally:
        if eigener:
            client.close()
    link = _objekt(_objekt(artikel.get("content_urls")).get("desktop")).get("page")
    return {
        "titel": artikel.get("title") or schluessel,
        "beschreibung": _kurz(artikel.get("description"), 200),
        "zusammenfassung": _kurz(artikel.get("extract"), 2500),
        "link": link or f"{basis}/wiki/{quote(schluessel)}",
        "weitere": [str(s.get("title")) for s in seiten[1:5] if s.get("title")],
        "quelle": f"Wikipedia ({sprache}) — CC BY-SA 4.0",
    }


_WAEHRUNG = re.compile(r"^[A-Z]{3}$")


def currency(amount: Any = 1, base: str = "EUR", to: str = "",
             *, client: httpx.Client | None = None) -> dict[str, Any]:
    """Rechnet mit den Tageskursen der EZB (ueber Frankfurter) um."""
    von = str(base or "EUR").strip().upper()
    ziele = [z.strip().upper() for z in str(to or "").replace(";", ",").split(",") if z.strip()]
    if not _WAEHRUNG.fullmatch(von) or any(not _WAEHRUNG.fullmatch(z) for z in ziele):
        return {"error": "Waehrungen bitte als dreistelligen Code, z.B. EUR, USD, CHF."}
    try:
        betrag = float(str(amount if amount not in (None, "") else 1).replace(",", "."))
    except ValueError:
        return {"error": "Der Betrag ist keine Zahl."}
    if not 0 < betrag < 1e12:
        return {"error": "Der Betrag muss groesser als 0 sein."}
    params: dict[str, Any] = {"base": von}
    if ziele:
        params["symbols"] = ",".join(ziele[:10])
    client, eigener = _eigener_client(client)
    try:
        _takt("frankfurter.dev")
        antwort = client.get(FRANKFURTER, params=params)
        if antwort.status_code == 404:
            return {"error": f"Die EZB fuehrt keinen Kurs fuer {von} oder {', '.join(ziele)}."}
        antwort.raise_for_status()
        daten = _objekt(antwort.json())
    except (httpx.HTTPError, ValueError) as exc:
        return {"error": f"Kurse nicht erreichbar ({type(exc).__name__})."}
    finally:
        if eigener:
            client.close()
    kurse = {code: rate for code, rate in _objekt(daten.get("rates")).items()
             if isinstance(rate, (int, float)) and not isinstance(rate, bool)
             and math.isfinite(rate) and rate > 0 and math.isfinite(betrag * rate)}
    if von in ziele:
        kurse[von] = 1.0
    return {
        "betrag": betrag, "von": von, "stand": daten.get("date"),
        "ergebnis": {code: round(betrag * float(kurs), 4) for code, kurs in kurse.items()
                     if isinstance(kurs, (int, float))},
        "kurs": {code: kurs for code, kurs in kurse.items()},
        "quelle": "Referenzkurse der EZB über frankfurter.dev",
    }


def holidays(country: str = "DE", year: Any = None, region: str = "",
             *, client: httpx.Client | None = None) -> dict[str, Any]:
    """Gesetzliche Feiertage eines Landes (und optional eines Bundeslandes)."""
    land = str(country or "DE").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", land):
        return {"error": "Land bitte als zweistelligen Code, z.B. DE, AT, CH."}
    try:
        jahr = int(str(year)) if year not in (None, "") else time.localtime().tm_year
    except ValueError:
        return {"error": "Das Jahr ist keine Zahl."}
    if not 1990 <= jahr <= 2100:
        return {"error": "Nur Jahre von 1990 bis 2100."}
    bundesland = str(region or "").strip().upper()
    if bundesland and not bundesland.startswith(f"{land}-"):
        bundesland = f"{land}-{bundesland}"
    client, eigener = _eigener_client(client)
    try:
        _takt("date.nager.at")
        antwort = client.get(NAGER.format(jahr=jahr, land=land))
        if antwort.status_code == 404:
            return {"error": f"Fuer '{land}' kennt Nager.Date keine Feiertage."}
        antwort.raise_for_status()
        daten = antwort.json() or []
    except (httpx.HTTPError, ValueError) as exc:
        return {"error": f"Feiertage nicht erreichbar ({type(exc).__name__})."}
    finally:
        if eigener:
            client.close()
    tage = []
    for tag in daten if isinstance(daten, list) else []:
        if not isinstance(tag, dict):
            continue
        roh_gebiete = tag.get("counties")
        gebiete = [str(g) for g in roh_gebiete] if isinstance(roh_gebiete, list) else []
        if bundesland and not tag.get("global") and bundesland not in gebiete:
            continue
        tage.append({
            "datum": tag.get("date"), "name": tag.get("localName") or tag.get("name"),
            "ueberall": bool(tag.get("global")),
            "nur_in": [] if tag.get("global") else list(gebiete),
        })
    return {"land": land, "jahr": jahr, "bundesland": bundesland, "feiertage": tage,
            "quelle": "Nager.Date (date.nager.at)"}



def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def _strip_html(text: str) -> str:
    from html import unescape

    return " ".join(unescape(re.sub(r"<[^>]+>", " ", text or "")).split())


def _hat_dtd(data: bytes) -> bool:
    """Fragt den XML-Parser selbst (9.5.34): die Byte-Suche oben sieht eine DTD
    in UTF-16 nicht, der Parser erkennt jede Kodierung."""
    from xml.parsers import expat

    parser = expat.ParserCreate()
    gefunden = False

    def dtd(*_args: Any) -> None:
        nonlocal gefunden
        gefunden = True
        raise ValueError("DTD")

    parser.StartDoctypeDeclHandler = dtd
    parser.EntityDeclHandler = dtd
    with contextlib.suppress(expat.ExpatError, ValueError):
        parser.Parse(data, True)
    return gefunden


def parse_feed(data: bytes, quelle: str) -> list[dict[str, Any]]:
    """RSS 2.0 und Atom. Ohne DTD -- Entitaeten-Tricks kommen gar nicht an."""
    kopf = data[:4096].lower()
    if b"<!doctype" in kopf or b"<!entity" in data.lower() or _hat_dtd(data):
        raise ValueError("Feed mit DTD/Entitaeten -- wird nicht gelesen.")
    wurzel = ET.fromstring(data)
    eintraege: list[dict[str, Any]] = []
    bases: dict[ET.Element, str] = {}
    pending = [(wurzel, quelle)]
    while pending:
        element, parent_base = pending.pop()
        xml_base = element.get("{http://www.w3.org/XML/1998/namespace}base", "")
        current_base = urljoin(parent_base, xml_base)
        if len(current_base) > 8192:
            raise ValueError("Die Basisadresse im Feed ist zu lang.")
        bases[element] = current_base
        pending.extend((child, current_base) for child in element)
    for element in wurzel.iter():
        art = _local(element.tag)
        if art not in ("item", "entry"):
            continue
        felder = {_local(kind.tag): kind for kind in element}

        def erstes(*namen: str, felder: dict[str, ET.Element] = felder) -> ET.Element | None:

            for name in namen:
                if felder.get(name) is not None and _text(felder[name]):
                    return felder[name]
            return None

        links = [child for child in element if _local(child.tag) == "link"]
        link_node = next((child for child in links if child.get("rel", "alternate") == "alternate"
                          and child.get("type", "text/html") in
                          ("text/html", "application/xhtml+xml")),
                         links[0] if links else None)
        link = (link_node.get("href") or _text(link_node)) if link_node is not None else ""
        if not link:
            guid = erstes("guid")
            candidate = _text(guid)
            if (guid is not None and guid.get("isPermaLink", "true").lower() == "true"
                    and candidate.startswith(("http://", "https://"))):
                link = candidate

        def readable(node: ET.Element | None, *, html_default: bool = False) -> str:
            if node is None:
                return ""
            value = _text(node)
            content_type = node.get("type", "html" if html_default else "text").lower()
            if content_type in ("xhtml", "application/xhtml+xml"):
                value = ET.tostring(node, encoding="unicode", method="html")
            return (_strip_html(value) if content_type in
                    ("html", "xhtml", "text/html", "application/xhtml+xml") else value)

        datum = _text(erstes("pubdate", "updated", "published", "date"))
        zeit = 0.0
        with contextlib.suppress(Exception):
            zeit = parsedate_to_datetime(datum).timestamp()
        if not zeit and datum:
            with contextlib.suppress(ValueError):
                from datetime import datetime

                zeit = datetime.fromisoformat(datum.replace("Z", "+00:00")).timestamp()
        eintraege.append({
            "titel": _kurz(readable(felder.get("title")), 300),
            "link": urljoin(bases[link_node] if link_node is not None else bases[element], link)
            if link else "",
            "datum": datum,
            "zusammenfassung": _kurz(readable(
                erstes("description", "summary", "content", "encoded"),
                html_default=art == "item"), 400),
            "quelle": urlparse(quelle).hostname or quelle,
            "_zeit": zeit,
        })
    return eintraege


def read_feeds(
    feeds: list[str], query: str = "", limit: Any = 15, *, client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Liest die eingetragenen Feeds -- hoeflich und nur aus dem Internet."""
    from aquaticy.fetch import RobotsPolicy, public_web_url

    if not feeds:
        return {"error": "Es sind keine Feeds eingetragen. Das macht der Nutzer im "
                         "Add-on-Fenster (RSS-Feeds → Feeds eintragen)."}
    try:
        grenze = max(1, min(MAX_FEED_ITEMS, int(str(limit or 15))))
    except ValueError:
        grenze = 15
    worte = [wort for wort in re.findall(r"\w+", (query or "").lower()) if len(wort) > 2]
    eigener = client is None
    from aquaticy import netguard

    client = client or netguard.guarded_client(timeout=15, follow_redirects=False,
                                               headers={"User-Agent": user_agent(),
                                             "Accept": "application/rss+xml, application/atom+xml, "
                                                       "application/xml;q=0.9, */*;q=0.5"})
    robots = RobotsPolicy(client, user_agent())
    alle: list[dict[str, Any]] = []
    probleme: list[str] = []
    try:
        for feed in feeds[:MAX_FEEDS]:
            adresse = feed
            try:
                for _ in range(4):
                    if not public_web_url(adresse):
                        raise ValueError("nicht oeffentlich erreichbar")
                    if not robots.allows(adresse):
                        raise ValueError("robots.txt verbietet den Abruf")
                    _takt(urlparse(adresse).hostname or adresse)

                    antwort = netguard.get(client, adresse, follow_redirects=False,
                                           max_bytes=MAX_FEED_BYTES)
                    if antwort.status_code in (301, 302, 303, 307, 308):
                        adresse = urljoin(adresse, antwort.headers.get("location", ""))
                        continue
                    break
                else:
                    raise ValueError("zu viele Umleitungen")
                if antwort.status_code != 200:
                    raise ValueError(f"Antwort {antwort.status_code}")
                if len(antwort.content) > MAX_FEED_BYTES:
                    raise ValueError("zu gross")
                alle.extend(parse_feed(antwort.content, adresse))
            except (httpx.HTTPError, ValueError, ET.ParseError) as exc:
                probleme.append(f"{urlparse(feed).hostname}: {exc}"[:160])
    finally:
        if eigener:
            client.close()
    if worte:
        alle = [e for e in alle if any(
            wort in f"{e['titel']} {e['zusammenfassung']}".lower() for wort in worte)]
    alle.sort(key=lambda e: e["_zeit"], reverse=True)
    for eintrag in alle:
        eintrag.pop("_zeit", None)
    return {"eintraege": alle[:grenze], "feeds": len(feeds), "probleme": probleme}





APP_OF = {"whatsapp": "whatsapp", "signal": "signal", "blender": "blender"}


def desktop_apps(settings: Any, pro: bool = True) -> list[str]:
    """Welche Add-on-Programme sich im Desktop oeffnen lassen."""
    return [
        APP_OF[a] for a in active_ids(settings, pro)
        if a in APP_OF
        and not (a == "blender" and rights_of(settings, "blender")["nutzung"] == "skripte")
    ]


PROMPT = """\
## Add-ons
Der Nutzer hat diese Add-ons eingeschaltet: %(liste)s.
- Messenger (WhatsApp, Signal) oeffnest du mit desktop_open (app = \
whatsapp/signal) und bedienst sie wie ein Mensch. Lies nur, was die \
Frage braucht. Eine Nachricht abschicken ist "senden": nur nach ausdruecklichem \
Ja des Nutzers, und nur an die Person, die er genannt hat. Nie an mehrere \
gleichzeitig, nie Werbung, nie etwas im Namen des Nutzers versprechen.
- Ist ein Messenger abgemeldet (QR-Code zu sehen), meldest du ihn NICHT an -- \
das macht der Nutzer im Add-on-Fenster selbst.
- Namen, Nummern und Inhalte aus Chats oder privaten GitHub-Repos gehoeren nie \
in eine Websuche.
- GitHub lesen mit github (auch commit und vergleich). Aendern mit github_write, wenn \
das Recht es erlaubt: checkout holt das Repo in die VM (Code-Chat), dort aendern und \
testen, push committet und pusht die Aenderungen auf einen eigenen Branch; ohne VM \
commit mit files. Danach pull_request. Jeder Schritt fragt den Nutzer. Nie auf den \
Standard-Branch, kein Mergen, keine GitHub Actions; nie Schluessel oder Passwoerter.
- Blender: Skripte mit blender_run, die Oberflaeche mit desktop_open app=blender.
- Code-Review und Security-Review sind Prueflisten, keine Werkzeuge: sie gelten, \
wenn der Nutzer /code-review oder /security-review schreibt.
- Jedes eingeschaltete Add-on hat im Chat einen Befehl (/github, /wetter ...). \
Fragt der Nutzer danach, sag es ihm.
"""


def prompt_for(settings: Any, pro: bool = True) -> str:
    aktiv = active_ids(settings, pro)
    if not aktiv:
        return ""
    text = PROMPT % {"liste": ", ".join(CATALOG[a].name for a in aktiv)}
    zeilen = [
        f"- {CATALOG[a].name}: {rights_text(a, rights_of(settings, a))}"
        for a in aktiv if RIGHTS.get(a)
    ]
    if zeilen:
        text += (
            "Was der Nutzer dir je Add-on erlaubt hat (im Code durchgesetzt -- frag gar "
            "nicht erst nach mehr, sondern sag, wo man es aendert: Add-on-Fenster -> "
            "Rechte):\n" + "\n".join(zeilen) + "\n"
        )
    return text


def werkstatt_command_for_blender() -> str:
    """Blender aus dem Add-on, sonst das aus dem Abbild (Shell-Anfang eines Befehls)."""
    return (
        "B=$(python3 -c \"import json;print('/addons/blender/'+json.load(open("
        "'/addons/blender/aquaticy.json'))['start'])\" 2>/dev/null); "
        '[ -x "$B" ] || B=blender; "$B"'
    )
