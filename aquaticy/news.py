"""Die neuesten Nachrichten -- als Meldungen, nicht als Liste von Nachrichtenseiten.

Bis 11.0 antwortete Aquaticy auf "Was sind die neusten Nachrichten?" oft mit
"Aktuelles findest du bei Tagesschau, Spiegel, ...". Zwei Gruende:

* Im Standardmodus entscheidet das Modell selbst, ob es nachsieht. Viele
  Modelle antworten auf diese Frage aus dem Gedaechtnis -- und das kennt nur
  die Namen der Nachrichtenseiten, nicht die Meldungen von heute.
* Sah es doch nach, suchte es nach dem Wort "Nachrichten". Die Treffer sind
  die Startseiten der Nachrichtenseiten -- also wieder eine Liste von Quellen.

Jetzt erkennt :func:`news_request` solche Fragen, der Agent holt die
Meldungen vorab selbst, und eine Frage ohne Thema liefert die Schlagzeilen
aus den Feeds grosser Nachrichtenseiten. Feeds sind genau dafuer da, gelesen
zu werden; es gilt trotzdem robots.txt, die Netzregel und eine Groessengrenze
(siehe :func:`aquaticy.addons.read_feeds`).
"""

from __future__ import annotations

import contextlib
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

from aquaticy.models import SearchResult

HEADLINE_FEEDS: dict[str, tuple[str, ...]] = {
    "de": (
        "https://www.tagesschau.de/index~rss2.xml",
        "https://www.zdf.de/rss/zdf/nachrichten",
        "https://www.deutschlandfunk.de/nachrichten-100.rss",
        "https://www.spiegel.de/schlagzeilen/index.rss",
    ),
    "at": (
        "https://rss.orf.at/news.xml",
        "https://www.derstandard.at/rss",
        "https://www.tagesschau.de/index~rss2.xml",
    ),
    "ch": (
        "https://www.srf.ch/news/bnf/rss/1646",
        "https://www.nzz.ch/recent.rss",
        "https://www.tagesschau.de/index~rss2.xml",
    ),
    "en": (
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://feeds.npr.org/1001/rss.xml",
        "https://www.theguardian.com/world/rss",
    ),
}


HEADLINE_COUNT = 12


PER_FEED = 6

_NOMEN = r"nachrichten|news|schlagzeilen|neuigkeiten|headlines|tagesthemen|tagesschau"
_AKTUELL = (r"neu(e)?ste[nrs]?|aktuelle[nrs]?|heutige[nrs]?|letzte[nrs]?|wichtigste[nrs]?|"
            r"top|heute|gestern|gerade|jetzt|momentan|derzeit|latest|today|yesterday|breaking|"
            r"current|recent")


_FRAGE_RE = re.compile(rf"\b({_NOMEN})\b", re.IGNORECASE)
_AKTUELL_RE = re.compile(rf"\b({_AKTUELL})\b", re.IGNORECASE)

_MELDUNG_RE = re.compile(r"\bmeldungen\b", re.IGNORECASE)

_PASSIERT_RE = re.compile(
    r"\bwas\s+(ist|war|gibt'?s|gibt\s+es)\s+(denn\s+)?(heute|gerade|aktuell|so|neues|"
    r"in\s+der\s+welt|in\s+deutschland)\b.*\b(passiert|los|neues)\b"
    r"|\bwas\s+gibt'?s\s+neues\b|\bwas\s+gibt\s+es\s+neues\b"
    r"|\bwhat'?s\s+(happening|new)\b|\bwhat\s+happened\s+today\b",
    re.IGNORECASE,
)

_POST_RE = re.compile(
    r"\b(meine[nm]?|my|whatsapp|signal|telegram|sms|e-?mails?|mails?|postfach|"
    r"inbox|chat|chats|geschickt|geschrieben|bekommen|erhalten)\b",
    re.IGNORECASE,
)

_SCHREIBEN_RE = re.compile(
    r"\b(schreib\w*|formulier\w*|verfass\w*|erfind\w*|ausdenk\w*|write|draft)\b", re.IGNORECASE)


_FUELLWOERTER = frozenset({
    "was", "sind", "ist", "war", "gibt", "gibt's", "es", "die", "der", "das", "den", "dem",
    "des", "ein", "eine", "einen", "einem", "einer", "neueste", "neuesten", "neuester",
    "neuestes", "neuste", "neusten", "aktuelle", "aktuellen", "aktueller", "heutige",
    "heutigen", "letzte", "letzten", "wichtigste", "wichtigsten", "top", "heute", "gerade",
    "jetzt", "momentan", "derzeit", "nachrichten", "news", "schlagzeilen", "neuigkeiten",
    "headlines", "meldungen", "meldung", "tagesthemen", "tagesschau", "zeig", "zeige",
    "zeigst", "gib", "gibst", "sag", "sage", "sagst", "nenn", "nenne", "nennst", "mir", "mal",
    "bitte", "kannst", "du", "könntest", "koenntest", "würdest", "wuerdest", "so", "denn",
    "neues", "passiert", "los", "welt", "deutschland", "international", "inland", "ausland",
    "weltweit", "the", "latest", "today", "what's", "whats", "what", "is", "are", "happening",
    "new", "in", "im", "zu", "zum", "zur", "von", "aus", "über", "ueber", "auf", "für", "fuer",
    "about", "on", "from", "of", "world", "breaking", "current", "recent", "und", "and",
    "oder", "or", "welche", "welcher", "welches", "erzähl", "erzähle", "erzaehl", "erzaehle",
    "fass", "fasse", "zusammen", "überblick", "ueberblick", "kurz", "kurze", "kurzen",
    "kurzer", "übersicht", "uebersicht", "liste", "lies", "vor", "vorlesen", "möchte",
    "moechte", "will", "wissen", "hören", "hoeren", "brauche", "ich", "uns", "aller", "alle",
    "allen", "tag", "tages", "woche", "dieser", "diese", "gestern", "vorgestern", "morgen",
    "abend", "gesehen", "geschaut", "gehört", "gehoert", "give", "me", "tell", "show",
    "please", "summary", "summarize", "this", "week",
})


@dataclass(frozen=True, slots=True)
class NewsRequest:
    """Eine Frage nach Nachrichten. Ohne Thema: die Schlagzeilen des Tages."""

    topic: str = ""


def news_request(text: str) -> NewsRequest | None:
    """Ist *text* eine Frage nach aktuellen Nachrichten? Dann mit Thema.

    Bewusst eng: "Nachricht" in der Einzahl, Post ("meine Nachrichten",
    WhatsApp) und Schreibauftraege zaehlen nicht. Lange Texte auch nicht --
    sie sind Auftraege mit eigenem Plan, keine Frage nach den Schlagzeilen.
    """
    text = " ".join((text or "").split())
    if not text or len(text) > 200:
        return None
    if _SCHREIBEN_RE.search(text) or _POST_RE.search(text):
        return None
    worte = re.findall(r"[\w'äöüß-]+", text.lower())
    if _PASSIERT_RE.search(text):
        return NewsRequest(topic=_topic(worte))
    if not _FRAGE_RE.search(text) and not (_MELDUNG_RE.search(text) and _AKTUELL_RE.search(text)):
        return None
    if not (_AKTUELL_RE.search(text) or len(worte) <= 4
            or re.search(r"\b(zu|über|ueber|von|aus|about|on)\b", text, re.IGNORECASE)):
        return None
    return NewsRequest(topic=_topic(worte))


def _topic(worte: list[str]) -> str:
    return " ".join(w for w in worte if w not in _FUELLWOERTER)[:80]


def is_generic(query: str) -> bool:
    """Fragt *query* nach den Schlagzeilen allgemein -- ohne eigenes Thema?"""
    worte = re.findall(r"[\w'äöüß-]+", (query or "").lower())
    return bool(worte) and not _topic(worte)


def feeds_for(country: str, lang: str) -> tuple[str, ...]:
    """Die Schlagzeilen-Feeds fuer Land und Sprache des Nutzers."""
    land = (country or "").lower()
    if (lang or "de").lower() != "de":
        return HEADLINE_FEEDS["en"]
    return HEADLINE_FEEDS.get(land, HEADLINE_FEEDS["de"])


def _zeit(datum: str) -> float:
    with contextlib.suppress(Exception):
        return parsedate_to_datetime(datum).timestamp()
    with contextlib.suppress(ValueError):
        return datetime.fromisoformat(datum.replace("Z", "+00:00")).timestamp()
    return 0.0


def _wann(stempel: float) -> str:
    if not stempel:
        return ""
    return datetime.fromtimestamp(stempel).strftime("%d.%m. %H:%M")


def _ein_feed(feed: str, reader: Any) -> list[dict[str, Any]]:
    try:
        ergebnis = reader([feed], limit=PER_FEED)
    except Exception:
        return []
    eintraege = ergebnis.get("eintraege") if isinstance(ergebnis, dict) else None
    return [e for e in eintraege or [] if isinstance(e, dict)][:PER_FEED]


def headlines(country: str = "de", lang: str = "de", count: int = HEADLINE_COUNT, *,
              reader: Any = None) -> list[SearchResult]:
    """Die aktuellen Schlagzeilen, neueste zuerst, aus mehreren Redaktionen.

    *reader* liest einen Feed (Standard: :func:`aquaticy.addons.read_feeds`).
    Die Feeds laufen nebeneinander -- ein langsamer haelt die anderen nicht auf.
    """
    if reader is None:
        from aquaticy.addons import read_feeds as reader
    feeds = feeds_for(country, lang)
    with ThreadPoolExecutor(max_workers=len(feeds)) as pool:
        listen = list(pool.map(lambda feed: _ein_feed(feed, reader), feeds))
    gesehen: set[str] = set()
    alle: list[tuple[float, SearchResult]] = []
    for eintraege in listen:
        for eintrag in eintraege:
            titel = str(eintrag.get("titel") or "").strip()
            link = str(eintrag.get("link") or "").strip()
            schluessel = re.sub(r"\W+", " ", titel.lower()).strip()
            if not titel or not link.startswith(("https://", "http://")) or schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            stempel = _zeit(str(eintrag.get("datum") or ""))
            kopf = " · ".join(t for t in (_wann(stempel), str(eintrag.get("quelle") or "")) if t)
            text = str(eintrag.get("zusammenfassung") or "").strip()
            alle.append((stempel, SearchResult(
                title=titel, url=link, snippet=f"[{kopf}] {text}" if kopf else text)))
    alle.sort(key=lambda paar: paar[0], reverse=True)
    ergebnis = [treffer for _, treffer in alle[:max(1, count)]]
    for rang, treffer in enumerate(ergebnis, start=1):
        treffer.rank = rang
    return ergebnis
