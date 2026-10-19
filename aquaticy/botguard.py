"""Anmeldeschutz gegen Bots (12.0.0 Terra): drei Hinweise, eine Risikozahl.

Bei jeder Anmeldung -- bevor das Passwort ueberhaupt gehasht wird -- schaut
Aquaticy auf drei Dinge:

==============================  ===============  ===============
Hinweis                         gut              schlecht
==============================  ===============  ===============
Fingerabdruck des Clients       passt zur App    wie ein Skript
Fehlversuche dieses Clients     keine            viele
dieses Geraet                   schon gesehen    neu
==============================  ===============  ===============

Daraus wird eine Zahl von 0 bis 100::

    6 + 40 (Skript) + 4 je Fehlversuch (hoechstens 33) + 20 (neues Geraet)

* **unter 34:** durch -- weiter zum Passwort.
* **34 bis 66:** Nachweis -- "Bestaetige kurz, dass du ein Mensch bist": ein
  Regler, den man ganz nach rechts schiebt, und dazu eine Rechenaufgabe, die
  der Browser im Hintergrund loest.
* **ab 67:** abgewiesen -- ohne Passwortpruefung, und die Adresse ist fuer
  ein Skript 15 Minuten gesperrt.

Die Gewichte sind so gewaehlt, dass die drei Beispiele der Vorlage
herauskommen: passt / 0 Fehlversuche / bekanntes Geraet = 6, passt / 6 /
neu = 50, Skript / 40 / neu = 99. Ein Browser, dessen Fingerabdruck passt,
erreicht hoechstens 59 -- er wird nie abgewiesen, schlimmstenfalls gefragt.

**Fingerabdruck.** Einen echten TLS-Fingerabdruck (JA3/JA4) sieht Aquaticy
nicht: Hinter dem Cloudflare-Tunnel endet die Verschluesselung des Besuchers
bei Cloudflare, im Heimnetz gibt es sie gar nicht. Geprueft wird deshalb, was
hier ankommt und was ein Skript ohne Browser nicht von selbst mitbringt:

* ein Browser als User-Agent -- keiner der bekannten Werkzeuge (curl,
  python-requests, Go, Headless-Chrome ...);
* die Fetch-Metadaten, die jeder heutige Browser bei einem ``fetch()`` der
  eigenen Seite schickt (``Sec-Fetch-Site: same-origin``) -- nur dort, wo
  Browser sie schicken (https und localhost, nicht http im Heimnetz);
* ``Accept-Language``;
* einen Nachweis aus dem Hintergrund: Beim Besuch holt die Seite eine kleine
  Rechenaufgabe (SHA-256, im Mittel gut 16.000 Versuche) und loest sie,
  waehrend man tippt. Er gilt einmal und eine Viertelstunde;
* ``navigator.webdriver`` -- ein ferngesteuerter Browser meldet sich so.

Alles hier liegt im Speicher des Servers: Fehlversuche eine Stunde, Sperren
15 Minuten. Gespeichert wird nur ein Schluessel aus Adresse oder Geraete-
Kennung (die ohnehin nur als Hash vorliegt), nie ein Passwort oder Name.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import itertools
import json
import math
import re
import secrets
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Iterable, Mapping
from typing import Any

#: Die Gewichte (siehe oben).
BASE = 6
SCRIPT = 40
PER_FAIL = 4
FAIL_CAP = 33
NEW_DEVICE = 20
#: Ab hier Nachweis, ab hier abgewiesen.
CHALLENGE_FROM = 34
DROP_FROM = 67

THROUGH, CHALLENGE, DROPPED = "durch", "nachweis", "abgewiesen"

#: So lange zaehlen Fehlversuche, so lange gilt eine Sperre.
FAIL_WINDOW = 3600.0
BAN_SECONDS = 15 * 60
#: Die Rechenaufgaben: beim Besuch klein, beim Nachweis groesser.
VISIT_BITS = 14
HUMAN_BITS = 17
VISIT_TTL = 15 * 60
HUMAN_TTL = 5 * 60

#: Ein Schluessel je Serverstart -- ein Neustart macht offene Aufgaben ungueltig;
#: dann fragt Aquaticy eben einmal nach.
_SECRET = secrets.token_bytes(32)
_NONCE = re.compile(r"[0-9]{1,12}")
_SEED = re.compile(r"[0-9a-f]{32}")

#: Werkzeuge statt Browser. "headless" faengt HeadlessChrome; "bot" und Co. die,
#: die sich ehrlich nennen.
_SKRIPT = re.compile(
    r"curl|wget|python|httpx|aiohttp|requests|urllib|go-http|okhttp|java/|apache-http|"
    r"libwww|perl|ruby|php/|node-fetch|axios|undici|postman|insomnia|scrapy|headless|"
    r"phantomjs|selenium|puppeteer|playwright|\bbot\b|bot/|spider|crawler",
    re.IGNORECASE,
)
#: Browser, die bei jedem fetch() Sec-Fetch-Site/-Mode mitschicken.
_SENDET_FETCH = re.compile(r"\b(?:Chrome|Chromium|Edg|Firefox)/")


# -- Risikozahl -------------------------------------------------------------------------
def score(script_like: bool, failures: int, new_device: bool) -> int:
    """Die Risikozahl 0 bis 100 aus den drei Hinweisen."""
    zahl = (BASE + (SCRIPT if script_like else 0)
            + min(FAIL_CAP, PER_FAIL * max(0, int(failures)))
            + (NEW_DEVICE if new_device else 0))
    return max(0, min(100, zahl))


def verdict(zahl: int) -> str:
    """durch, Nachweis oder abgewiesen."""
    if zahl >= DROP_FROM:
        return DROPPED
    if zahl >= CHALLENGE_FROM:
        return CHALLENGE
    return THROUGH


def fingerprint(headers: Mapping[str, str] | Any, proof_ok: bool, webdriver: bool,
                fetch_metadata: bool) -> list[str]:
    """Was am Client nach Skript aussieht -- leer heisst: passt zur App.

    Args:
        fetch_metadata: Schickt ein Browser hier ``Sec-Fetch-*``? Bei https und
            localhost ja, bei http im Heimnetz nicht -- dort zaehlt es nicht.
    """
    def kopf(name: str) -> str:
        try:
            return str(headers.get(name) or "").strip()
        except Exception:
            return ""

    gruende: list[str] = []
    agent = kopf("User-Agent")
    if not agent.lower().startswith("mozilla/5.0") or _SKRIPT.search(agent):
        gruende.append("user-agent")
    # Chrome, Edge und Firefox schicken die Fetch-Metadaten seit Jahren -- aeltere
    # WebKit-Fenster (Desktop-App unter Linux) nicht immer, die fragen wir nicht.
    if fetch_metadata and _SENDET_FETCH.search(agent) and (
            kopf("Sec-Fetch-Site").lower() != "same-origin"
            or kopf("Sec-Fetch-Mode").lower() not in {"cors", "same-origin"}):
        gruende.append("fetch")
    if not kopf("Accept-Language"):
        gruende.append("sprache")
    if not proof_ok:
        gruende.append("nachweis")
    if webdriver:
        gruende.append("webdriver")
    return gruende


# -- Rechenaufgaben ---------------------------------------------------------------------
def _b64(daten: bytes) -> str:
    return base64.urlsafe_b64encode(daten).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _signatur(roh: str) -> str:
    return _b64(hmac.new(_SECRET, roh.encode("ascii"), hashlib.sha256).digest())


def issue(kind: str = "visit") -> dict[str, Any]:
    """Eine neue Aufgabe: ``visit`` beim Besuch, ``human`` beim Nachweis."""
    bits = HUMAN_BITS if kind == "human" else VISIT_BITS
    daten = {"k": "human" if kind == "human" else "visit", "s": secrets.token_hex(16),
             "d": bits, "t": int(time.time())}
    roh = _b64(json.dumps(daten, separators=(",", ":")).encode("ascii"))
    return {"token": f"{roh}.{_signatur(roh)}", "seed": daten["s"], "bits": bits}


def zero_bits(digest: bytes) -> int:
    """Wie viele Nullbits am Anfang stehen."""
    gezaehlt = 0
    for byte in digest:
        if byte == 0:
            gezaehlt += 8
            continue
        return gezaehlt + 8 - byte.bit_length()
    return gezaehlt


def solves(seed: str, nonce: str, bits: int) -> bool:
    """Loest *nonce* die Aufgabe? SHA-256 von "seed:nonce" mit *bits* Nullbits vorn."""
    return zero_bits(hashlib.sha256(f"{seed}:{nonce}".encode("ascii")).digest()) >= bits


class _Used:
    """Geloeste Aufgaben gelten einmal -- danach ist ihr Samen verbraucht."""

    def __init__(self, max_entries: int = 100_000) -> None:
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._max = max_entries
        self._lock = threading.Lock()

    def take(self, seed: str, until: float) -> bool:
        jetzt = time.time()
        with self._lock:
            while self._seen and next(iter(self._seen.values())) < jetzt:
                self._seen.popitem(last=False)
            if seed in self._seen:
                return False
            self._seen[seed] = until
            while len(self._seen) > self._max:
                self._seen.popitem(last=False)
            return True


_USED = _Used()


def check(proof: Any, kinds: Iterable[str]) -> bool:
    """Ist *proof* ({token, nonce}) eine gueltige, frische, noch nicht benutzte Loesung?"""
    if not isinstance(proof, Mapping):
        return False
    token, nonce = proof.get("token"), proof.get("nonce")
    if (not isinstance(token, str) or len(token) > 400 or not isinstance(nonce, str)
            or not _NONCE.fullmatch(nonce)):
        return False
    roh, _, signatur = token.partition(".")
    if not roh or not hmac.compare_digest(signatur.encode(), _signatur(roh).encode()):
        return False
    try:
        daten = json.loads(_unb64(roh))
    except (ValueError, binascii.Error):
        return False
    if not isinstance(daten, dict):
        return False
    art, samen, bits, ausgestellt = daten.get("k"), daten.get("s"), daten.get("d"), daten.get("t")
    if (art not in set(kinds) or not isinstance(samen, str) or not _SEED.fullmatch(samen)
            or not isinstance(bits, int) or not isinstance(ausgestellt, int)):
        return False
    dauer = HUMAN_TTL if art == "human" else VISIT_TTL
    jetzt = time.time()
    if not ausgestellt - 5 <= jetzt <= ausgestellt + dauer:
        return False
    if bits < (HUMAN_BITS if art == "human" else VISIT_BITS) or not solves(samen, nonce, bits):
        return False
    return _USED.take(samen, ausgestellt + dauer)


# -- Der Regler ---------------------------------------------------------------------------
def human_track(track: Any) -> bool:
    """Sieht die Bewegung am Regler nach einem Menschen aus?

    *track* ist eine Liste von [Millisekunden, Stellung 0..1]. Verlangt wird:
    mindestens sechs Punkte, eine Viertelsekunde bis zwei Minuten, von links
    (hoechstens 0,2) bis ganz rechts (mindestens 0,95) -- und kein Lineal: ein
    Skript, das in gleichen Schritten gleich schnell schiebt, faellt durch.
    Mit der Tastatur geht es auch (Pfeiltasten), dann sind es eben Spruenge.
    """
    if not isinstance(track, list) or not 6 <= len(track) <= 400:
        return False
    punkte: list[tuple[float, float]] = []
    for punkt in track:
        if (not isinstance(punkt, (list, tuple)) or len(punkt) != 2
                or not all(isinstance(w, (int, float)) and not isinstance(w, bool)
                           and math.isfinite(w) for w in punkt)):
            return False
        zeit, stelle = float(punkt[0]), float(punkt[1])
        if not 0 <= zeit <= 120_000 or not -0.05 <= stelle <= 1.05:
            return False
        if punkte and zeit < punkte[-1][0]:
            return False
        punkte.append((zeit, stelle))
    dauer = punkte[-1][0] - punkte[0][0]
    if not 250 <= dauer <= 120_000 or punkte[0][1] > 0.2 or punkte[-1][1] < 0.95:
        return False
    tempi = [(b[1] - a[1]) / (b[0] - a[0]) for a, b in itertools.pairwise(punkte)
             if b[0] > a[0]]
    if len(tempi) < 3:
        return False
    mittel = sum(tempi) / len(tempi)
    streuung = math.sqrt(sum((t - mittel) ** 2 for t in tempi) / len(tempi))
    return mittel > 0 and streuung / mittel >= 0.05


# -- Fehlversuche und Sperren -------------------------------------------------------------
def address_key(adresse: str) -> str:
    """Unter welcher Adresse gezaehlt wird: IPv4 einzeln, IPv6 je /64-Netz.

    Ein Anschluss bekommt bei IPv6 meist ein ganzes /64 -- ein Bot koennte sonst
    fuer jeden Versuch eine neue Adresse nehmen und kaeme nie auf Fehlversuche.
    """
    try:
        ip = ipaddress.ip_address(str(adresse).strip())
    except ValueError:
        return str(adresse)[:64]
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.IPv6Network(f"{ip}/64", strict=False))
    return str(ip)



class Failures:
    """Fehlversuche je Client (Adresse, Geraete-Kennung) -- eine Stunde lang."""

    def __init__(self, window: float = FAIL_WINDOW, max_keys: int = 50_000) -> None:
        self.window = window
        self._max = max_keys
        self._events: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def add(self, *keys: str) -> None:
        jetzt = time.monotonic()
        with self._lock:
            for key in filter(None, keys):
                ereignisse = self._events.pop(key, None) or deque(maxlen=64)
                ereignisse.append(jetzt)
                self._events[key] = ereignisse
            while len(self._events) > self._max:
                self._events.popitem(last=False)

    def count(self, *keys: str) -> int:
        """Die meisten Fehlversuche unter *keys* im Fenster."""
        jetzt = time.monotonic()
        meiste = 0
        with self._lock:
            for key in filter(None, keys):
                ereignisse = self._events.get(key)
                if not ereignisse:
                    continue
                while ereignisse and jetzt - ereignisse[0] >= self.window:
                    ereignisse.popleft()
                meiste = max(meiste, len(ereignisse))
        return meiste


class Bans:
    """Abgewiesene Clients, fuer eine Weile."""

    def __init__(self, max_keys: int = 50_000) -> None:
        self._bis: OrderedDict[str, float] = OrderedDict()
        self._max = max_keys
        self._lock = threading.Lock()

    def ban(self, *keys: str, seconds: float = BAN_SECONDS) -> None:
        bis = time.monotonic() + seconds
        with self._lock:
            for key in filter(None, keys):
                self._bis.pop(key, None)
                self._bis[key] = bis
            while len(self._bis) > self._max:
                self._bis.popitem(last=False)

    def remaining(self, *keys: str) -> int:
        """Sekunden, bis die laengste Sperre unter *keys* ablaeuft (0 = frei)."""
        jetzt = time.monotonic()
        rest = 0.0
        with self._lock:
            for key in filter(None, keys):
                bis = self._bis.get(key)
                if bis is None:
                    continue
                if bis <= jetzt:
                    self._bis.pop(key, None)
                    continue
                rest = max(rest, bis - jetzt)
        return math.ceil(rest)
