"""Sprache und Standard-Ort aus dem Chat lernen (16.0.0).

Aquaticy beobachtet nur, was der Nutzer selbst schreibt, und stellt daraus drei Dinge ein:

* **Sprache der Suche** (``AQUATICY_LANG``): Schreibt der Nutzer mehrfach hintereinander auf
  Japanisch, wird Japanisch seine Sprache. Erst die dritte sichere Nachricht in Folge zaehlt --
  eine einzelne englische Frage aendert nichts.
* **Standard-Ort** (``AQUATICY_LOCATION``): Nennt der Nutzer immer wieder denselben Ort in einer
  Suche ("Restaurants in New York"), wird er sein Standard-Ort. Erst ab dem dritten Mal, und nur
  bei Fragen, die nach etwas Oertlichem suchen -- sonst wuerde "in Ordnung" oder "in Excel" zum
  Ort.
* **Land** (``AQUATICY_COUNTRY``): nie durch Zaehlen. Nur wenn der Nutzer es sagt ("Ich wohne in
  den USA") oder selbst einstellt.

Regeln, die nicht verhandelbar sind:

* Eine Einstellung, die der Nutzer selbst gesetzt hat, bleibt. Aquaticy aendert nur Werte, die
  noch ab Werk stehen oder die es selbst gesetzt hat (``auto`` in der Zustandsdatei).
* Gelernt wird nur aus den eigenen Worten des Nutzers im Chat -- nie aus Anhaengen, Webseiten,
  Werkzeugergebnissen, Helfern, Coworkern, dem Messenger oder Plugin-Befehlen. Der Aufruf sitzt
  deshalb hinter denselben Schranken wie das Gedaechtnis (agent.py, ``_memory_learn``).
* Die Zaehler sind persoenliche Daten. Sie liegen im Kontoordner, werden mit "Alle Daten
  loeschen" und mit "Alles vergessen" im Gedaechtnis geloescht und zaehlen nicht, wenn das
  Gedaechtnis aus ist.
* Jede Aenderung wird dem Nutzer im Chat gezeigt und laesst sich unter Konto -> Ort & Sprache
  zuruecknehmen.
"""

from __future__ import annotations

import contextlib
import json
import re
import threading
from pathlib import Path
from typing import Any

STATE_NAME = "autoort.json"
#: So viele sichere Nachrichten in Folge muessen in derselben Sprache sein.
SPRACH_SERIE = 3
#: So oft muss derselbe Ort in Suchfragen vorkommen.
ORT_MINDESTENS = 3
#: Hoechstens so viele Orte merkt sich der Zaehler.
ORT_MAX = 12
#: Laengere Nachrichten sind meist eingefuegter Text -- sie zaehlen nicht.
MAX_ZEICHEN = 800
_LOCK = threading.Lock()

STANDARD = {"lang": ("", "de"), "location": ("",), "country": ("", "de")}

# -- Sprache -------------------------------------------------------------------------------------

#: (Name, Zeichenbereiche) -- die Schrift allein verraet die Sprache.
SCHRIFTEN: tuple[tuple[str, tuple[tuple[int, int], ...]], ...] = (
    ("ja", ((0x3040, 0x30FF), (0x31F0, 0x31FF))),
    ("ko", ((0xAC00, 0xD7AF), (0x1100, 0x11FF))),
    ("zh", ((0x4E00, 0x9FFF),)),
    ("ru", ((0x0400, 0x04FF),)),
    ("ar", ((0x0600, 0x06FF),)),
    ("he", ((0x0590, 0x05FF),)),
    ("el", ((0x0370, 0x03FF),)),
    ("th", ((0x0E00, 0x0E7F),)),
    ("hi", ((0x0900, 0x097F),)),
)

_WOERTER = {
    "de": "der die das und ist nicht ich du wir sie ein eine einen einem mit fuer für auf wie was "
          "wo wann warum wird sind zu den dem des im zum zur auch noch bei von nach aus kann mir "
          "mich dir bitte gibt habe hast haben mein meine kein aber oder wenn dann nur sehr "
          "welche welcher heute morgen gestern suche suchen finde finden zeige zeig gib hilf "
          "erkläre schreibe",
    "en": "the and is are was were of to for with that this what how why when where who which "
          "you your my me it its at be have has can will do does not from by please there "
          "about would should could just but or if then only very today tomorrow yesterday i i'm "
          "good find show give help explain write need want",
    "fr": "le la les des un une et est sont pas je tu il elle nous vous ils pour dans sur avec "
          "que qui quoi comment pourquoi quand où ou mon ma mes ton ta tes son sa ses ce cette "
          "ces au aux du de en ne plus très bien merci aujourd hui demain hier quel quelle "
          "temps fait c'est qu'est bonjour salut ça va cherche trouver à oui",
    "es": "el la los las un una y es son no yo tú él ella nosotros para con por que qué como cómo "
          "por porqué cuándo dónde donde mi mis tu tus su sus este esta estos estas del al muy "
          "más pero hoy mañana ayer cuál gracias hay hola hace tiempo busco buscar dime",
    "it": "il lo la i gli le un una e è sono non io tu lui lei noi voi per con su che cosa come "
          "perché quando dove mio mia miei tuo tua suo sua questo questa del della dei delle al "
          "molto più ma oggi domani ieri quale grazie c'è",
    "nl": "de het een en is zijn niet ik jij je hij zij wij jullie voor met op dat dit wat hoe "
          "waarom wanneer waar wie welke mijn jouw zijn haar deze die van naar uit kan mij mijn "
          "ook nog bij heel maar of als dan alleen vandaag morgen gisteren dank",
    "pt": "o a os as um uma e é são não eu tu ele ela nós vocês para com por que qual como porque "
          "quando onde meu minha meus teu tua seu sua este esta estes estas do da dos das ao muito "
          "mais mas hoje amanhã ontem obrigado tem está",
}


def _woerter() -> dict[str, dict[str, float]]:
    """Je Sprache: Wort -> Gewicht. Ein Wort, das in mehreren Sprachen steht, zaehlt weniger."""
    rohe = {name: set(text.split()) for name, text in _WOERTER.items()}
    gewichte: dict[str, dict[str, float]] = {}
    for name, menge in rohe.items():
        gewichte[name] = {w: 1.0 / sum(1 for m in rohe.values() if w in m) for w in menge}
    return gewichte


WOERTER = _woerter()
_TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?", re.UNICODE)


def erkenne_sprache(text: str) -> str:
    """Die Sprache einer Nachricht -- oder "" wenn sie nicht sicher ist (kurz, gemischt, Zahlen)."""
    text = str(text or "")
    buchstaben = [c for c in text if c.isalpha()]
    if not buchstaben:
        return ""
    zaehler: dict[str, int] = {}
    for name, bereiche in SCHRIFTEN:
        zaehler[name] = sum(1 for c in buchstaben if any(a <= ord(c) <= b for a, b in bereiche))
    if zaehler["ja"]:
        # Kana gibt es nur im Japanischen -- auch wenn viele Han-Zeichen dabei sind.
        zaehler["ja"] += zaehler["zh"]
        zaehler["zh"] = 0
    schrift, anzahl = max(zaehler.items(), key=lambda p: p[1])
    if anzahl and anzahl * 2 >= len(buchstaben) and anzahl >= 2:
        if schrift == "ru" and re.search(r"[іїєґ]", text.lower()):
            return "uk"
        return schrift
    worte = [w.lower() for w in _TOKEN.findall(text)]
    if len(worte) < 4:
        return ""
    treffer = sorted(((sum(gewichte.get(w, 0.0) for w in worte), name)
                      for name, gewichte in WOERTER.items()), reverse=True)
    beste, zweite = treffer[0], treffer[1]
    # Sicher heisst: genug Belege und deutlich vor der naechsten Sprache.
    if beste[0] >= 2.5 and beste[0] >= 2 * zweite[0]:
        return beste[1]
    return ""


# -- Land ----------------------------------------------------------------------------------------

LAENDER: dict[str, str] = {
    "deutschland": "de", "germany": "de", "österreich": "at", "oesterreich": "at",
    "austria": "at", "schweiz": "ch", "switzerland": "ch", "usa": "us", "us": "us",
    "vereinigte staaten": "us", "vereinigten staaten": "us", "amerika": "us",
    "united states": "us", "america": "us", "großbritannien": "gb", "grossbritannien": "gb",
    "england": "gb", "uk": "gb", "vereinigtes königreich": "gb", "vereinigten königreich": "gb",
    "united kingdom": "gb", "britain": "gb", "great britain": "gb", "schottland": "gb",
    "frankreich": "fr", "france": "fr", "spanien": "es", "spain": "es", "italien": "it",
    "italy": "it", "niederlande": "nl", "niederlanden": "nl", "holland": "nl",
    "netherlands": "nl", "belgien": "be", "belgium": "be", "polen": "pl", "poland": "pl",
    "tschechien": "cz", "czechia": "cz", "dänemark": "dk", "daenemark": "dk", "denmark": "dk",
    "schweden": "se", "sweden": "se", "norwegen": "no", "norway": "no", "finnland": "fi",
    "finland": "fi", "portugal": "pt", "irland": "ie", "ireland": "ie", "kanada": "ca",
    "canada": "ca", "australien": "au", "australia": "au", "neuseeland": "nz",
    "new zealand": "nz", "japan": "jp", "china": "cn", "indien": "in", "india": "in",
    "brasilien": "br", "brazil": "br", "mexiko": "mx", "mexico": "mx", "türkei": "tr",
    "tuerkei": "tr", "turkey": "tr", "griechenland": "gr", "greece": "gr", "ungarn": "hu",
    "hungary": "hu", "luxemburg": "lu", "luxembourg": "lu", "südkorea": "kr", "suedkorea": "kr",
    "south korea": "kr", "russland": "ru", "russia": "ru", "ukraine": "ua",
    "argentinien": "ar", "argentina": "ar", "südafrika": "za", "suedafrika": "za",
    "south africa": "za", "rumänien": "ro", "romania": "ro", "österreichs": "at",
}
_LAND = "|".join(sorted((re.escape(n) for n in LAENDER), key=len, reverse=True))
_WOHNE = re.compile(
    r"(?i)\bich\s+(?:wohne|lebe|bin\s+wohnhaft)\s+(?:jetzt\s+|derzeit\s+|aktuell\s+|"
    r"zurzeit\s+|zur\s+zeit\s+|inzwischen\s+)?(?:in|im)\s+(?:den\s+|der\s+|dem\s+)?"
    rf"({_LAND})\b(?!\s*[-,]?\s*[A-ZÄÖÜ])")
_LIVE = re.compile(
    rf"(?i)\bi\s+(?:live|reside|(?:am|'m)\s+living|am\s+based)\s+in\s+(?:the\s+)?({_LAND})\b")


def land_aus(text: str) -> str:
    """Das Land, in dem der Nutzer nach eigener Aussage wohnt -- oder ""."""
    for muster in (_WOHNE, _LIVE):
        treffer = muster.search(str(text or ""))
        if treffer:
            return LAENDER.get(treffer.group(1).lower(), "")
    return ""


# -- Orte ----------------------------------------------------------------------------------------

# Kein Punkt im Namen: Sonst hinge "Paris. Hotels" aus zwei Saetzen zusammen.
# 16.1.0: Buchstaben mit Akzent zaehlen mit (São Paulo, Málaga, Kraków).
_NAME = r"[A-ZÄÖÜÀ-ÖØ-ÞĀ-Ž](?:[^\W\d_]|['’-])+"
#: Feste Zusaetze, die zum Namen gehoeren ("Frankfurt am Main") -- nur diese, damit
#: "Berlin am Wochenende" nicht als Ort durchgeht.
_ZUSATZ = (r"(?:\s+(?:am\s+(?:Main|Rhein|Neckar|Inn|Lech|See)|an\s+der\s+(?:Oder|Donau|Ruhr|"
           r"Saale|Elbe|Weser|Ilm|Havel|Lahn|Weinstraße)|im\s+Breisgau|ob\s+der\s+Tauber))?")
_ORT = rf"(?P<ort>(?:St\.\s?|Sankt\s)?{_NAME}(?:[ -]{_NAME}){{0,2}}{_ZUSATZ})"
_THEMEN = (
    r"wetter|weather|restaurants?|cafés?|cafes?|hotels?|wohnung(?:en)?|apartments?|jobs?|"
    r"stellen|events?|veranstaltungen|konzerte?|kinos?|kinoprogramm|apotheken?|ärzte|"
    r"zahnärzte|nachrichten|news|geschäfte|shops?|läden|bars?|sehenswürdigkeiten|"
    r"attractions|things\s+to\s+do|bäckereien|bäckerei|supermärkte?|tankstellen?|friseure?|"
    r"parkplätze|verkehr|traffic|pizza|sushi|burger|flohmärkte|märkte|clubs?|museen|museums?|"
    r"nightlife|forecast|vorhersage"
)
_MUSTER = (
    re.compile(rf"\b(?i:{_THEMEN})\b\s+(?i:(?:heute|morgen|übermorgen|today|tomorrow)\s+)?"
               rf"(?i:in\s+der\s+nähe\s+von|in\s+der\s+naehe\s+von|"
               rf"rund\s+um|in|im|bei|near|around|nahe)\s+{_ORT}"),
    re.compile(
        r"\b(?i:such\w*|find\w*|search\w*|look\w*|zeig\w*|show|gibt\s+es|where\s+(?:can|to)|"
        r"wo\s+(?:gibt|finde|kann))\b[^.?!\n]{0,60}?\b(?i:in|im|near|around|bei)\s+" + _ORT),
)
#: Woerter, die nach "in" gross geschrieben werden, aber kein Ort sind.
_KEIN_ORT_TEXT = """
januar februar märz maerz april mai juni juli august september oktober november dezember
january february march may june july october december montag dienstag mittwoch donnerstag
freitag samstag sonntag monday tuesday wednesday thursday friday saturday sunday
deutsch englisch französisch spanisch italienisch japanisch chinesisch german english french
spanish italian japanese chinese python java javascript typescript excel word powerpoint outlook
linux windows macos android ios google youtube amazon ebay wikipedia github gitlab chatgpt
claude aquaticy internet ordnung betracht zukunft vergangenheit gegenwart summe bezug anspruch
arbeit kürze ruhe frage betrieb form formen zeit moment jahr jahren woche tag tagen nähe
umgebung europa asien afrika amerika nordamerika südamerika heute morgen gestern aktuelle
aktuelles aktuell neue neues beste bestes gute gutes
"""
KEIN_ORT = frozenset(_KEIN_ORT_TEXT.split()) | frozenset(LAENDER)


def _sauber(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip(" .,-'’")
    return name


def orte_in(text: str) -> list[str]:
    """Orte, nach denen der Nutzer in dieser Nachricht sucht -- hoechstens drei, ohne Doppelte."""
    text = str(text or "")
    gefunden: list[str] = []
    for muster in _MUSTER:
        for treffer in muster.finditer(text):
            name = _sauber(treffer.group("ort"))
            erste = name.replace("-", " ").split(" ")[0].casefold()
            if (len(name) < 3 or name.casefold() in KEIN_ORT or erste in KEIN_ORT
                    or name.casefold() in (g.casefold() for g in gefunden)):
                continue
            gefunden.append(name)
    return gefunden[:3]


# -- Zustand und Lernen --------------------------------------------------------------------------

def _pfad(data_dir: Path | str) -> Path:
    return Path(data_dir) / STATE_NAME


def _leer() -> dict[str, Any]:
    return {"v": 1, "recent": [], "orte": {}, "auto": {}}


def laden(data_dir: Path | str) -> dict[str, Any]:
    zustand = _leer()
    with contextlib.suppress(OSError, ValueError):
        gelesen = json.loads(_pfad(data_dir).read_text(encoding="utf-8"))
        if isinstance(gelesen, dict):
            if isinstance(gelesen.get("recent"), list):
                zustand["recent"] = [str(x)[:3] for x in gelesen["recent"]][-SPRACH_SERIE * 2:]
            if isinstance(gelesen.get("orte"), dict):
                for schluessel, eintrag in list(gelesen["orte"].items())[:ORT_MAX * 2]:
                    if isinstance(eintrag, dict) and isinstance(eintrag.get("n"), int):
                        zustand["orte"][str(schluessel)[:80]] = {
                            "name": str(eintrag.get("name") or schluessel)[:80],
                            "n": max(0, min(int(eintrag["n"]), 10_000))}
            if isinstance(gelesen.get("auto"), dict):
                zustand["auto"] = {str(k): str(v)[:80] for k, v in gelesen["auto"].items()
                                   if k in STANDARD}
    return zustand


def speichern(data_dir: Path | str, zustand: dict[str, Any]) -> None:
    from aquaticy import private_json

    private_json.write(_pfad(data_dir), zustand)


def vergessen(data_dir: Path | str) -> None:
    """Loescht die Zaehler (Orte, letzte Sprachen). Eingestellte Werte bleiben stehen."""
    with _LOCK:
        zustand = laden(data_dir)
        zustand["recent"], zustand["orte"] = [], {}
        # Ohne "auto" gelten die Werte danach als vom Nutzer gesetzt: nichts aendert sich mehr.
        zustand["auto"] = {}
        with contextlib.suppress(OSError):
            speichern(data_dir, zustand)


def _frei(feld: str, aktuell: str, zustand: dict[str, Any]) -> bool:
    """Darf Aquaticy dieses Feld aendern? Nur wenn es ab Werk steht oder von Aquaticy kommt."""
    heute = str(aktuell or "").strip()
    auto = zustand["auto"].get(feld, "")
    if auto:
        return heute.casefold() == auto.casefold()
    return heute.casefold() in STANDARD[feld]


def lernen(data_dir: Path | str, text: str, aktuell: dict[str, str]) -> list[dict[str, str]]:
    """Wertet eine Nachricht des Nutzers aus.

    Args:
        data_dir: der Kontoordner (dort liegt die Zustandsdatei).
        text: nur die eigenen Worte des Nutzers.
        aktuell: heutige Werte von ``lang``, ``country`` und ``location``.

    Returns:
        Was jetzt eingestellt werden soll: je Eintrag ``feld`` (lang, country, location) und
        ``wert``. Die Datei ``autoort.json`` ist dann schon fortgeschrieben -- wer die Werte
        nicht schreiben kann, ruft :func:`zuruecknehmen` auf.
    """
    text = " ".join(str(text or "").split())
    if not text or len(text) > MAX_ZEICHEN:
        return []
    aenderungen: list[dict[str, str]] = []
    with _LOCK:
        zustand = laden(data_dir)
        vorher = json.dumps(zustand, sort_keys=True)

        land = land_aus(text)
        if land and land != str(aktuell.get("country", "")).strip().lower():
            aenderungen.append({"feld": "country", "wert": land})

        sprache = erkenne_sprache(text)
        if sprache:
            zustand["recent"] = (zustand["recent"] + [sprache])[-SPRACH_SERIE * 2:]
            serie = zustand["recent"][-SPRACH_SERIE:]
            if (len(serie) == SPRACH_SERIE and set(serie) == {sprache}
                    and sprache != str(aktuell.get("lang", "")).strip().lower()
                    and _frei("lang", aktuell.get("lang", ""), zustand)):
                aenderungen.append({"feld": "lang", "wert": sprache})
                zustand["auto"]["lang"] = sprache

        for name in orte_in(text):
            schluessel = name.casefold()
            eintrag = zustand["orte"].setdefault(schluessel, {"name": name, "n": 0})
            eintrag["n"] += 1
        if len(zustand["orte"]) > ORT_MAX:
            behalten = sorted(zustand["orte"].items(), key=lambda p: -p[1]["n"])[:ORT_MAX]
            zustand["orte"] = dict(behalten)
        rang = sorted(zustand["orte"].values(), key=lambda e: -e["n"])
        if rang and rang[0]["n"] >= ORT_MINDESTENS and (
                len(rang) == 1 or rang[0]["n"] >= 2 * rang[1]["n"]):
            ort = rang[0]["name"]
            if (ort.casefold() != str(aktuell.get("location", "")).strip().casefold()
                    and _frei("location", aktuell.get("location", ""), zustand)):
                aenderungen.append({"feld": "location", "wert": ort})
                zustand["auto"]["location"] = ort

        if json.dumps(zustand, sort_keys=True) != vorher:
            with contextlib.suppress(OSError):
                speichern(data_dir, zustand)
    return aenderungen


def zuruecknehmen(data_dir: Path | str, feld: str) -> None:
    """Das Schreiben eines Werts ist gescheitert: die Marke "kam von Aquaticy" wieder weg."""
    with _LOCK:
        zustand = laden(data_dir)
        if zustand["auto"].pop(feld, None) is not None:
            with contextlib.suppress(OSError):
                speichern(data_dir, zustand)
