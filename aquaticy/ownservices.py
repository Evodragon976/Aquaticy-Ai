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
from datetime import date

SOURCES = ("home", "storage", "calendar", "mail")

_BESITZ = r"(?:mein|meine|meinen|meinem|meiner|meines|my|unser|unsere|unseren|unserem|our)"

_LUECKE = r"(?:[\w'-]+\s+){0,3}"
_ICH_HABE = (r"(?:hab(?:e)?\s+ich|habe\s+ich|hast\s+du\s+(?:f(?:ü|ue)r\s+mich)|"
             r"do\s+i\s+have|have\s+i\s+(?:got|received)|did\s+i\s+(?:get|receive)|"
             r"gibt\s+es|is\s+there|are\s+there|any)")

_DAVOR_ICH = r"\s+(?:hab(?:e)?\s+ich|hast\s+du\s+f(?:ü|ue)r\s+mich|do\s+i\s+have)\b"

# 16.4.5: Nicht als Teil eines Wortes: "E-Mail-Programme" ist keine Frage ans Postfach.
_MAIL_WORT = r"(?:e-?mails?|mails?|posteingang|postfach|inbox|gmail)(?![-\w])"
#: "Gibt es Termine für die Impfung in Berlin?" fragt nach fremden Terminen, nicht nach den
#: eigenen -- dann ist das Netz gefragt.
_FREMD = (r"(?!\s+(?:f(?:ü|ue)r|bei|beim|zur|zum|in|im|for|at|with|in)\s+"
          r"(?!mich\b|mir\b|me\b|uns\b|us\b|mein\w*|my\b|unser\w*|our\b))")
_ES_GIBT = r"(?:gibt\s+es|is\s+there|are\s+there|any)"
_MAIL = re.compile(
    rf"\b{_BESITZ}\s+{_LUECKE}{_MAIL_WORT}\b"
    rf"|\b(?!{_ES_GIBT}\b){_ICH_HABE}\s+{_LUECKE}{_MAIL_WORT}"
    rf"|\b{_ES_GIBT}\s+{_LUECKE}{_MAIL_WORT}{_FREMD}"
    rf"|\b{_MAIL_WORT}{_DAVOR_ICH}"
    rf"|\b(?:neue|neuen|ungelesene|ungelesenen|new|unread)\s+{_MAIL_WORT}\b"
    # 16.4.5: "Hat mir Peter geschrieben?", "Did Anna email me?" -- vorher Websuche.
    r"|^\s*hat\s+mir\s+(?:[\w'-]+\s+){1,3}(?:eine?\s+)?(?:e-?mail\s+|mail\s+)?"
    r"(?:geschrieben|gemailt|geantwortet)\s*[?.!]*\s*$"
    r"|^\s*(?:did|has)\s+(?:[\w'-]+\s+){1,3}(?:e-?mailed|written\s+to|wr(?:o|i)te\s+to|"
    r"replied\s+to|e-?mail)\s+me\b"
    rf"|^\s*(?:lies|lese|zeig|zeige|check|checke|pr(?:ü|ue)fe?|read|show|open|"
    rf"(?:ö|oe)ffne)\s+(?:mir\s+|me\s+)?(?:die\s+|the\s+)?{_LUECKE}{_MAIL_WORT}\b",
    re.IGNORECASE,
)

_TERMIN_WORT = (r"(?:termin\w*|kalender\w*|calendar|appointments?|meetings?|"
                r"besprechung\w*|verabredung\w*|events?|schedule|agenda)")
_KALENDER = re.compile(
    rf"\b{_BESITZ}\s+{_LUECKE}{_TERMIN_WORT}\b"
    rf"|\b(?!{_ES_GIBT}\b){_ICH_HABE}\s+{_LUECKE}{_TERMIN_WORT}\b"
    rf"|\b{_ES_GIBT}\s+{_LUECKE}{_TERMIN_WORT}\b{_FREMD}"
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
    r"|\b(?:(?:ü|ue)ber|via|mit|with|in)\s+home\s*assistant\b"
    # 16.4.5: "Ist die Heizung an?", "Welche Lampen sind an?", "Ist die Haustür abgeschlossen?",
    # "Wie warm ist es im Schlafzimmer?" -- vorher Websuche bzw. Wetter.
    rf"|^\s*(?:ist|sind|is|are)\s+(?:das|die|der|the)\s+{_GERAET}\s+(?:an|aus|on|off|offen|zu|"
    r"open|closed|eingeschaltet|ausgeschaltet)\s*[?.!]*\s*$"
    rf"|^\s*(?:welche|which)\s+{_GERAET}\s+(?:sind|ist|are|is)\s+(?:noch\s+|still\s+)?"
    r"(?:an|aus|on|off|offen|zu|open)\s*[?.!]*\s*$"
    r"|^\s*(?:ist|is)\s+(?:die|das|der|the)\s+(?:haust(?:ü|ue)r|wohnungst(?:ü|ue)r|"
    r"terrassent(?:ü|ue)r|garage(?:ntor)?|front\s+door|garage\s+door)\s+(?:noch\s+|still\s+)?"
    r"(?:offen|zu|auf|abgeschlossen|verschlossen|geschlossen|open|closed|locked|unlocked)\b"
    r"|\b(?:wie\s+(?:warm|kalt)\s+ist\s+es|temperatur|luftfeuchtigkeit|how\s+(?:warm|cold)\s+"
    r"is\s+it)\s+(?:im|in\s+der|in\s+the)\s+(?:wohn|schlaf|kinder|bade?|arbeits|g(?:ä|ae)ste|"
    r"ess)?(?:zimmer|k(?:ü|ue)che|keller|flur|living\s+room|bedroom|kitchen|bathroom|"
    r"basement)\s*[?.!]*\s*$",
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

# "Bitte sende mir den ganzen Text von der Email xy" (13.0.1 Luna): Ein Befehl, der eine Mail
# zeigen, vorlesen oder schicken soll -- mit Bitte davor und etwas mehr Platz bis zum Mail-Wort.
_MAIL_BEFEHL = re.compile(
    r"^\s*(?:(?:bitte|please|kannst\s+du|k(?:ö|oe)nntest\s+du|can\s+you|could\s+you)\s+)?"
    r"(?:lies|lese|zeig|zeige|sende|send|schick|schicke|gib|give|show|read|open|"
    r"(?:ö|oe)ffne|kopier\w*|copy|fass|fasse)\s+(?:mir\s+|me\s+)?(?:[\w'-]+\s+){0,6}"
    rf"{_MAIL_WORT}\b",
    re.IGNORECASE,
)

# "Kannst du mir die letzte Mail vorlesen?" -- das Verb steht am Ende.
_MAIL_BITTE = re.compile(
    r"\b(?:kannst|k(?:ö|oe)nntest|w(?:ü|ue)rdest)\s+du\s+(?:mir\s+)?(?:[\w'-]+\s+){0,4}"
    rf"{_MAIL_WORT}\s+(?:[\w'-]+\s+){{0,3}}(?:vor)?(?:lesen|zeigen|schicken|senden|geben|"
    r"(?:ö|oe)ffnen|kopieren)\b",
    re.IGNORECASE,
)

# Nach einer Antwort aus dem eigenen Postfach: "lies mir die zweite vor", "zeig den ganzen
# Text", "und die Nachricht von Anna?" -- gemeint ist dieselbe Post.
_POST_FOLGE = re.compile(
    # bestimmt: "die Mail von Anna", "diese Nachricht" -- nicht "eine gute E-Mail" und nicht
    # "die Nachrichten" (Neuigkeiten)
    r"\b(?:die|der|den|dem|diese\w*|jene\w*|the|that|this)\s+(?:[\w'-]+\s+){0,2}"
    r"(?:e-?mail|mail|nachricht|message)\b(?!en)"
    r"|\b(?:die|der|den|the)\s+(?:erste|zweite|dritte|vierte|f(?:ü|ue)nfte|letzte|neueste|"
    r"oberste|untere|first|second|third|fourth|fifth|last|latest|top)\b"
    r"|\b(?:ganzen?|vollst(?:ä|ae)ndig\w*|komplett\w*|full|whole|entire)\s+"
    r"(?:text|inhalt|content|wortlaut|body)\b"
    r"|\bvor(?:lesen)?\s*[.!?]?\s*$",
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
        if not _MUSTER[quelle].search(roh) and not (
                quelle == "mail" and (_MAIL_BEFEHL.search(roh) or _MAIL_BITTE.search(roh))):
            continue
        if quelle == "home" and _HAUS_NICHT.search(roh):
            continue
        treffer.append(quelle)
    return tuple(treffer)


def followup_sources(text: str, previous: tuple[str, ...] | list[str] = ()) -> tuple[str, ...]:
    """Wie :func:`own_sources` -- und eine Folgefrage zur eigenen Post (13.0.1 Luna).

    Kam die vorige Antwort aus dem eigenen Postfach, meint "lies mir die zweite vor" oder
    "schick mir den ganzen Text" dieselbe Post. Ohne so eine vorige Antwort bleibt es eine
    normale Frage.
    """
    eigene = own_sources(text)
    if eigene or "mail" not in tuple(previous or ()):
        return eigene
    roh = " ".join(str(text or "").split())
    if not roh or len(roh) > 300:
        return ()
    return ("mail",) if _POST_FOLGE.search(roh) else ()


_MONATE = ("januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september",
           "oktober", "november", "dezember")
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december")
_ZAHLWORT = {"zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "two": 2, "three": 3, "four": 4,
             "five": 5}


def calendar_days(text: str, heute: date | None = None) -> int:
    """Wie viele Tage der Kalender zeigen soll: heute 1, morgen 2, sonst eine Woche.

    16.4.5: "Termine im Dezember" (am 19. November), "nächste Woche" und "in zwei Wochen"
    reichten vorher nur sieben Tage weit -- die gesuchten Termine fehlten.
    """
    klein = str(text or "").lower()
    if heute is None:
        from aquaticy import zeit

        heute = zeit.jetzt().date()
    monat = re.search(r"\b(?:im|in|for|during)\s+(" + "|".join(_MONATE + _MONTHS) + r")\b", klein)
    if monat:
        nummer = ((_MONATE.index(monat.group(1)) if monat.group(1) in _MONATE
                   else _MONTHS.index(monat.group(1))) + 1)
        jahr = heute.year if nummer >= heute.month else heute.year + 1
        ende = date(jahr + (nummer == 12), nummer % 12 + 1, 1)
        return max(1, min((ende - heute).days, 365))
    menge = re.search(r"\b(?:in|innerhalb|n(?:ä|ae)chsten|next|within)\s+(?:den\s+|der\s+)?"
                      r"(\d{1,3}|zwei|drei|vier|fünf|two|three|four|five)\s+"
                      r"(tag(?:e|en)?|days?|woche(?:n)?|weeks?)\b", klein)
    if menge:
        n = _ZAHLWORT.get(menge.group(1)) or int(menge.group(1))
        tage = n + 1 if menge.group(2).startswith(("tag", "day")) else n * 7 + 7
        return max(1, min(tage, 365))
    if re.search(r"\b(?:monat|month)\b", klein):
        return 31
    if re.search(r"\b(?:n(?:ä|ae)chste|kommende)\s+woche\b|\bnext\s+week\b", klein):
        return 14 - heute.weekday()
    if re.search(r"\b(?:wochenende|weekend)\b", klein):
        return 7 - heute.weekday()
    if re.search(r"\b(?:woche|week)\b", klein):
        return 7
    if re.search(r"\b(?:(?:ü|ue)bermorgen)\b", klein):
        return 3
    if re.search(r"\b(?:morgen|tomorrow)\b", klein):
        return 2
    if re.search(r"\b(?:heute|today|tonight)\b", klein):
        return 1
    return 7


def home_domain(text: str) -> str:
    """Der Home-Assistant-Bereich, nach dem zuerst gesehen wird -- "" = Uebersicht."""
    klein = str(text or "").lower()
    for muster, bereich in (
        (r"licht|lampe|leuchte|light|lamp", "light"),
        (r"heizung|thermostat|heating|klima", "climate"),
        (r"\broll(?:laden|o|os|läden)|jalousie|\bblinds?\b|shutter", "cover"),
        (r"ventilator|\bfans?\b", "fan"),
        (r"steckdose|\bplugs?\b", "switch"),
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
