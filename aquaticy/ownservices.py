"""Eigene Dienste: Fragen nach Mails, Terminen, Zuhause oder Lager erkennen (12.5.5 Terra).

"Was sind meine Mails?", "Welche Termine habe ich morgen?", "Schalte die Lichter im
Wohnzimmer an", "Was ist in meinem Lager?" -- die Antwort steht im eigenen Postfach,
im Kalender, in Home Assistant oder in der Lagerverwaltung. Im Netz steht sie nie.
Bis 12.5.5 Luna entschied das Modell selbst, wo es nachsieht, und der Planer
schickte bei "Strukturiert" oder im Pro-Modus Agenten ins Web.

Erkannt wird bewusst eng, mit einem Besitzwort ("meine Mails", "my calendar"),
"habe ich ..." oder einem Befehl am Satzanfang ("Schalte ..."). "Wie schreibe ich eine
gute E-Mail?" oder "Welche Termine hat das Bürgeramt?" bleiben normale Fragen.
"""

from __future__ import annotations

import re

SOURCES = ("home", "storage", "calendar", "mail")

_BESITZ = r"(?:mein|meine|meinen|meinem|meiner|meines|my|unser|unsere|unseren|unserem|our)"

_LUECKE = r"(?:[\w'-]+\s+){0,3}"
_ICH_HABE = (r"(?:hab(?:e)?\s+ich|habe\s+ich|hast\s+du\s+(?:f(?:ü|ue)r\s+mich)|"
             r"do\s+i\s+have|have\s+i\s+(?:got|received)|did\s+i\s+(?:get|receive)|"
             r"gibt\s+es|is\s+there|are\s+there|any)")

_DAVOR_ICH = r"\s+(?:hab(?:e)?\s+ich|hast\s+du\s+f(?:ü|ue)r\s+mich|do\s+i\s+have)\b"

_MAIL_WORT = r"(?:e-?mails?|mails?|posteingang|postfach|inbox|gmail)"
_MAIL = re.compile(
    rf"\b{_BESITZ}\s+{_LUECKE}{_MAIL_WORT}\b"
    rf"|\b{_ICH_HABE}\s+{_LUECKE}{_MAIL_WORT}\b"
    rf"|\b{_MAIL_WORT}{_DAVOR_ICH}"
    rf"|\b(?:neue|neuen|ungelesene|ungelesenen|new|unread)\s+{_MAIL_WORT}\b"
    rf"|^\s*(?:lies|lese|zeig|zeige|check|checke|pr(?:ü|ue)fe?|read|show|open|"
    rf"(?:ö|oe)ffne)\s+(?:mir\s+|me\s+)?(?:die\s+|the\s+)?{_LUECKE}{_MAIL_WORT}\b",
    re.IGNORECASE,
)

_TERMIN_WORT = (r"(?:termin\w*|kalender\w*|calendar|appointments?|meetings?|"
                r"besprechung\w*|verabredung\w*|events?|schedule|agenda)")
_KALENDER = re.compile(
    rf"\b{_BESITZ}\s+{_LUECKE}{_TERMIN_WORT}\b"
    rf"|\b{_ICH_HABE}\s+{_LUECKE}{_TERMIN_WORT}\b"
    rf"|\b{_TERMIN_WORT}{_DAVOR_ICH}"
    r"|\bwas\s+steht\s+(?:(?:heute|morgen|(?:ü|ue)bermorgen|diese\s+woche|am\s+\w+)\s+)?"
    r"(?:bei\s+mir\s+)?an\b"
    r"|\bwhat(?:'s|\s+is)\s+on\s+my\s+(?:calendar|schedule|agenda)\b"
    rf"|^\s*(?:trag|trage|zeig|zeige|lies|check|add|show)\s+(?:mir\s+|me\s+)?"
    rf"(?:die\s+|den\s+|einen\s+|the\s+|an?\s+)?{_LUECKE}{_TERMIN_WORT}\b",
    re.IGNORECASE,
)

_GERAET = (r"(?:licht\w*|lampe\w*|leuchte\w*|lights?|lamps?|steckdose\w*|plugs?|"
           r"heizung\w*|thermostat\w*|heating|rolll?(?:a|ä|ae)den\w*|rollo\w*|"
           r"jalousie\w*|blinds?|shutters?|ventilator\w*|fans?|klima\w*|"
           r"fernseher\w*|tv|staubsauger\w*|vacuum)")
_HAUS = re.compile(

    rf"^\s*(?:bitte\s+|please\s+|hey\s+aquaticy,?\s+)?(?:schalt\w*|mach\w*|dimm\w*|"
    rf"stell\w*|dreh\w*|turn|switch|dim|set)\s+(?:[\w'-]+\s+){{0,6}}?{_GERAET}\b"
    rf"|\b{_BESITZ}\s+{_LUECKE}{_GERAET}\b"
    rf"|\b(?:ist|sind|is|are)\s+(?:das|die|der|the)\s+{_GERAET}\s+"
    rf"(?:im|in\s+der|in\s+the|in)\s+\w+\s+(?:an|aus|on|off|offen|zu|open|closed)\b"
    r"|\b(?:(?:ü|ue)ber|via|mit|with|in)\s+home\s*assistant\b",
    re.IGNORECASE,
)

_HAUS_NICHT = re.compile(r"\b(?:blender|unity|unreal|minecraft|photoshop|szene\s+in)\b",
                         re.IGNORECASE)

_LAGER_WORT = (r"(?:lager\w*|lagerverwaltung|vorrat\w*|vorr(?:ä|ae)te\w*|inventar\w*|"
               r"storage|inventory|bestand\w*)")
_LAGER = re.compile(
    rf"\b{_BESITZ}\s+{_LUECKE}{_LAGER_WORT}\b"
    rf"|\b(?:im|ins|aus\s+dem|in\s+der)\s+{_LAGER_WORT}\b",
    re.IGNORECASE,
)

_MUSTER = {"home": _HAUS, "storage": _LAGER, "calendar": _KALENDER, "mail": _MAIL}


READ_TOOL = {"home": "ha_states", "storage": "storage_browse", "calendar": "calendar_events",
             "mail": "mail_search"}
TOOLS = {
    "home": frozenset({"ha_states", "ha_call"}),
    "storage": frozenset({"storage_find", "storage_browse", "storage_add", "storage_edit"}),
    "calendar": frozenset({"calendar_events", "calendar_add", "calendar_edit"}),
    "mail": frozenset({"mail_search", "mail_read", "mail_draft"}),
}


NAMES = {
    "de": {"home": "Home Assistant", "storage": "die Lagerverwaltung",
           "calendar": "dein Kalender", "mail": "dein Postfach"},
    "en": {"home": "Home Assistant", "storage": "the storage manager",
           "calendar": "your calendar", "mail": "your mailbox"},
}


WHERE = {
    "de": {"home": "Zuhause & Netz", "storage": "Zuhause & Netz",
           "calendar": "Gmail & Kalender", "mail": "Gmail & Kalender"},
    "en": {"home": "Home & network", "storage": "Home & network",
           "calendar": "Gmail & Calendar", "mail": "Gmail & Calendar"},
}


def own_sources(text: str) -> tuple[str, ...]:
    """Welche eigenen Dienste meint *text*? Leer = keiner (eine normale Frage)."""
    roh = " ".join(str(text or "").split())
    if not roh or len(roh) > 300:
        return ()
    treffer = []
    for quelle in SOURCES:
        if not _MUSTER[quelle].search(roh):
            continue
        if quelle == "home" and _HAUS_NICHT.search(roh):
            continue
        treffer.append(quelle)
    return tuple(treffer)


def calendar_days(text: str) -> int:
    """Wie viele Tage der Kalender zeigen soll: heute 1, morgen 2, sonst eine Woche."""
    klein = str(text or "").lower()
    if re.search(r"\b(?:heute|today|tonight|heute\s+abend)\b", klein):
        return 1
    if re.search(r"\b(?:(?:ü|ue)bermorgen)\b", klein):
        return 3
    if re.search(r"\b(?:morgen|tomorrow)\b", klein):
        return 2
    if re.search(r"\b(?:monat|month)\b", klein):
        return 31
    return 7


def home_domain(text: str) -> str:
    """Der Home-Assistant-Bereich, nach dem zuerst gesehen wird -- "" = Uebersicht."""
    klein = str(text or "").lower()
    for muster, bereich in (
        (r"licht|lampe|leuchte|light|lamp", "light"),
        (r"heizung|thermostat|heating|klima", "climate"),
        (r"roll|jalousie|blind|shutter", "cover"),
        (r"steckdose|plug|ventilator|fan", "switch"),
        (r"fernseher|\btv\b", "media_player"),
        (r"staubsauger|vacuum", "vacuum"),
    ):
        if re.search(muster, klein):
            return bereich
    return ""


def missing_text(sources: tuple[str, ...] | list[str], language: str = "de") -> str:
    """Der Satz, wenn keiner der gemeinten Dienste eingerichtet ist."""
    sprache = "en" if language == "en" else "de"
    namen = [NAMES[sprache][q] for q in sources]
    orte = list(dict.fromkeys(WHERE[sprache][q] for q in sources))
    if sprache == "en":
        was = " and ".join(namen)
        wo = " and ".join(f"“{o}”" for o in orte)
        verb, es = ("aren’t", "them") if len(namen) > 1 else ("isn’t", "it")
        return (f"I can’t look that up yet: {was} {verb} connected. "
                f"You can connect {es} in Settings under {wo}. "
                "I won’t search the internet for it, because the answer is only there.")
    was = " und ".join(namen)
    wo = " und ".join(f"„{o}“" for o in orte)
    verb = "sind" if len(namen) > 1 else "ist"
    return (f"Das kann ich noch nicht nachsehen: {was[0].upper() + was[1:]} {verb} nicht "
            f"verbunden. Das geht in den Einstellungen unter {wo}. Im Internet "
            "suche ich dafür nicht, denn die Antwort steht nur dort.")


def turn_note(sources: tuple[str, ...] | list[str]) -> str:
    """Der Hinweis fuer das Modell in diesem Turn."""
    werkzeuge = ", ".join(f"`{w}`" for q in sources for w in sorted(TOOLS[q]))
    return ("[Diese Frage betrifft die eigenen Dienste des Nutzers. Nimm dafür "
            f"{werkzeuge}. Such dafür nicht im Internet -- die Antwort steht nur dort.]")
