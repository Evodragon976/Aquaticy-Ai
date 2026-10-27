"""Ai-guard: erkennt, wenn jemand Aquaticy fuer Angriffe missbrauchen will (9.5.16 Lion).

Aquaticy hilft bei Recherche, Schreiben und -- fuer Fachleute -- bei
Verteidigung: Schadcode verstehen, eine Lücke absichern, einen Angriff
erkennen. Was es **nicht** tut, ist jemandem beim Angreifen helfen: eine
Schaddatei bauen, eine Anleitung für einen DDoS-Angriff schreiben, in fremde
Systeme einbrechen, Zugangsdaten stehlen. Der Rechtsrahmen
(:mod:`aquaticy.guardrails`) lehnt das schon je Anfrage ab. Ai-guard sieht
eine Stufe darueber: **über mehrere Chats hinweg** -- versucht dieselbe Person
das immer wieder?

**Wie es entscheidet.** Jede Nachricht eines angemeldeten Kontos wird
eingeschaetzt (dasselbe schnelle Modell wie der Rechtsprüfer). Ist sie ein
Anhaltspunkt -- eine klare Bitte um Schadcode, eine Angriffsanleitung, einen
Einbruch --, wird sie am Konto vermerkt. Ein Anhaltspunkt allein sperrt
niemanden: ein Fachbegriff, eine Frage aus Neugier, ein missverstandener Satz
soll kein Bann sein. Erst **zwei** Anhaltspunkte -- zwei getrennte Nachrichten
mit klarer Missbrauchsabsicht -- sperren das Konto. Auch eine Ablehnung durch
den Rechtsrahmen (Grundgesetz, BGB) zählt als Anhaltspunkt.

**Was gespeichert wird.** Nur der Anlass: Zeitpunkt, Art (etwa "Schadcode"),
ein kurzer Vermerk und der Chat. Nie der ganze Nachrichtentext. Die Daten
dienen allein dieser Prüfung -- das steht so in den Nutzungsbedingungen und
klein unten in den Einstellungen.

**Wer sperrt und entsperrt.** Automatisch bei zwei Anhaltspunkten. Von Hand
über das Terminal:

    aquaticy ban "name"        # Konto sperren
    aquaticy ban 203.0.113.7   # Adresse sperren
    aquaticy unban "name"      # wieder freigeben

Aus dem Chat lässt sich daran nichts ändern -- wie bei allen Schutzgrenzen.
"""

from __future__ import annotations

import functools
import ipaddress
import logging
import math
import re
import sqlite3
import threading
import time
import unicodedata
from collections import OrderedDict
from collections.abc import Callable
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aquaticy.jsonutil import loads

if TYPE_CHECKING:
    from collections.abc import Iterator

    from aquaticy.config import Settings



NEEDED = 2

LOG = logging.getLogger("aquaticy.aiguard")



DECISION_TTL = 3600.0



MIN_LENGTH = 12



INSULT_REPEAT = 3
INSULT_WINDOW = 7 * 86400.0


PATTERN_WINDOW = 90 * 86400.0


def _sauber(text: Any, laenge: int = 200) -> str:
    """Ohne Steuerzeichen (9.5.26): was im Terminal und in `aquaticy list`
    erscheint, kommt teils vom Modell -- und damit mittelbar vom Nutzer. Ein
    eingeschmuggeltes ESC haette die Terminalanzeige verstellen koennen."""
    roh = "".join(z if unicodedata.category(z)[0] != "C" else " " for z in str(text or ""))
    return " ".join(roh.split())[:laenge]


def _chat_key(chat: Any) -> str:
    """Die Chat-Kennung, wie sie gespeichert UND verglichen wird (9.5.26: vorher
    gekuerzt gespeichert, aber ungekuerzt verglichen -- eine lange Kennung
    waere nie als gesperrt erkannt worden)."""
    return str(chat or "").strip()[:80]



GUARD_VERSION = "2026-10-26"


@dataclass(frozen=True, slots=True)
class Flag:
    """Ein Anhaltspunkt -- der Anlass, nicht der Text."""

    at: float
    kind: str
    detail: str
    chat: str


@dataclass(frozen=True, slots=True)
class Ban:
    """Eine Sperre -- für ein Konto oder eine Adresse."""

    subject: str
    at: float
    reason: str
    by: str

    until: float = 0.0

    def active(self, now: float | None = None) -> bool:
        """Gilt die Sperre gerade noch?"""
        return self.until <= 0 or self.until > (time.time() if now is None else now)

    def remaining_text(self, now: float | None = None) -> str:
        """Wie lange noch -- fuer den Hinweis an den Nutzer."""
        if self.until <= 0:
            return "dauerhaft"
        rest = self.until - (time.time() if now is None else now)
        if rest <= 0:
            return "abgelaufen"
        if rest < 3600:
            return f"noch {max(1, math.ceil(rest / 60))} Min."


        stunden_gesamt = math.ceil(rest / 3600)
        tage, stunden = divmod(stunden_gesamt, 24)
        if tage >= 1:
            return f"noch {tage} Tag(e)" + (f", {stunden} Std." if stunden else "")
        return f"noch {stunden} Std."
















KATEGORIEN = ("beleidigung", "jailbreak", "malware", "angriff", "rechtsbruch")



_MUSTER_ARTEN = frozenset({"jailbreak", "angriff", "rechtsbruch"})


_SOFORT_ARTEN = frozenset({"beleidigung", "malware"})

_SYNONYME = {
    "insult": "beleidigung", "beleidigung": "beleidigung", "beschimpfung": "beleidigung",
    "hate": "beleidigung", "harassment": "beleidigung",
    "jailbreak": "jailbreak", "prompt-injection": "jailbreak", "manipulation": "jailbreak",
    "malware": "malware", "schadsoftware": "malware", "virus": "malware",
    "schadcode": "malware", "schadprogramm": "malware",
    "ransomware": "malware", "trojaner": "malware",
    "keylogger": "malware", "stealer": "malware", "spyware": "malware", "rootkit": "malware",
    "wurm": "malware", "worm": "malware", "botnet": "malware", "botnetz": "malware",
    "cryptominer": "malware", "backdoor": "malware", "hintertür": "malware",
    "angriff": "angriff", "attack": "angriff", "ddos": "angriff", "exploit": "angriff",
    "phishing": "angriff", "einbruch": "angriff", "waffen": "angriff",
    "hacking": "angriff", "hack": "angriff", "bruteforce": "angriff", "sqlinjection": "angriff",
    "sprengstoff": "angriff", "bombe": "angriff", "cyberangriff": "angriff",
    "identitätsdiebstahl": "angriff", "sabotage": "angriff", "waffe": "angriff",


    "rechtsbruch": "rechtsbruch", "diebstahl": "rechtsbruch", "betrug": "rechtsbruch",
    "straftat": "rechtsbruch", "erpressung": "rechtsbruch", "nötigung": "rechtsbruch",
    "noetigung": "rechtsbruch", "koerperverletzung": "rechtsbruch",
    "körperverletzung": "rechtsbruch", "raub": "rechtsbruch", "hehlerei": "rechtsbruch",
    "sachbeschädigung": "rechtsbruch", "sachbeschaedigung": "rechtsbruch",
    "urkundenfälschung": "rechtsbruch", "urkundenfaelschung": "rechtsbruch",
    "unterschlagung": "rechtsbruch", "brandstiftung": "rechtsbruch", "stalking": "rechtsbruch",
    "nachstellung": "rechtsbruch", "hausfriedensbruch": "rechtsbruch", "wucher": "rechtsbruch",
    "bedrohung": "rechtsbruch", "geldwäsche": "rechtsbruch", "geldwaesche": "rechtsbruch",
    "fraud": "rechtsbruch", "theft": "rechtsbruch", "extortion": "rechtsbruch",
    "blackmail": "rechtsbruch",


    "verleumdung": "rechtsbruch", "üble nachrede": "rechtsbruch", "nachrede": "rechtsbruch",
    "freiheitsberaubung": "rechtsbruch", "entführung": "rechtsbruch",
    "entfuehrung": "rechtsbruch", "menschenhandel": "rechtsbruch",
    "zwangsprostitution": "rechtsbruch", "vergewaltigung": "rechtsbruch",
    "kindesmissbrauch": "rechtsbruch", "sexueller missbrauch": "rechtsbruch",
    "kinderpornografie": "rechtsbruch", "kinderpornographie": "rechtsbruch",
    "csam": "rechtsbruch", "belästigung": "rechtsbruch", "belaestigung": "rechtsbruch",
    "exhibitionismus": "rechtsbruch", "voyeurismus": "rechtsbruch",
    "rachepornos": "rechtsbruch", "racheporno": "rechtsbruch", "deepfake": "rechtsbruch",
    "doxxing": "rechtsbruch", "doxing": "rechtsbruch", "swatting": "rechtsbruch",
    "cybermobbing": "rechtsbruch", "mobbing": "rechtsbruch", "morddrohung": "rechtsbruch",
    "mord": "rechtsbruch", "totschlag": "rechtsbruch", "tötung": "rechtsbruch",
    "toetung": "rechtsbruch", "steuerhinterziehung": "rechtsbruch",
    "schwarzarbeit": "rechtsbruch", "korruption": "rechtsbruch", "bestechung": "rechtsbruch",
    "bestechlichkeit": "rechtsbruch", "untreue": "rechtsbruch", "insiderhandel": "rechtsbruch",
    "marktmanipulation": "rechtsbruch", "subventionsbetrug": "rechtsbruch",
    "versicherungsbetrug": "rechtsbruch", "sozialbetrug": "rechtsbruch",
    "computerbetrug": "rechtsbruch", "kreditkartenbetrug": "rechtsbruch",
    "datenhehlerei": "rechtsbruch", "drogenhandel": "rechtsbruch",
    "betäubungsmittel": "rechtsbruch", "betaeubungsmittel": "rechtsbruch",
    "drogenschmuggel": "rechtsbruch", "schmuggel": "rechtsbruch", "falschgeld": "rechtsbruch",
    "geldfälschung": "rechtsbruch", "geldfaelschung": "rechtsbruch",
    "amtsanmaßung": "rechtsbruch", "amtsanmassung": "rechtsbruch",
    "unfallflucht": "rechtsbruch", "fahrerflucht": "rechtsbruch",
    "tierquälerei": "rechtsbruch", "tierquaelerei": "rechtsbruch", "wilderei": "rechtsbruch",
    "umweltstraftat": "rechtsbruch", "urheberrechtsverletzung": "rechtsbruch",
    "produktpiraterie": "rechtsbruch", "markenfälschung": "rechtsbruch",
    "markenfaelschung": "rechtsbruch", "volksverhetzung": "rechtsbruch",
    "falschaussage": "rechtsbruch", "meineid": "rechtsbruch",
    "strafvereitelung": "rechtsbruch", "urkundenunterdrückung": "rechtsbruch",
    "defamation": "rechtsbruch", "libel": "rechtsbruch",
    "slander": "rechtsbruch", "kidnapping": "rechtsbruch", "trafficking": "rechtsbruch",
    "murder": "rechtsbruch", "bribery": "rechtsbruch",
    "embezzlement": "rechtsbruch", "tax evasion": "rechtsbruch", "smuggling": "rechtsbruch",
    "counterfeiting": "rechtsbruch", "forgery": "rechtsbruch", "piracy": "rechtsbruch",
    "stalker": "rechtsbruch", "threat": "rechtsbruch", "threats": "rechtsbruch",

    "terror": "angriff", "terrorismus": "angriff", "anschlag": "angriff",
    "amoklauf": "angriff", "brandanschlag": "angriff", "giftanschlag": "angriff",
    "vergiftung": "angriff", "computersabotage": "angriff", "datenveränderung": "angriff",
    "datenveraenderung": "angriff", "ausspähen": "angriff", "ausspaehen": "angriff",
    "abfangen": "angriff", "credential": "angriff", "account takeover": "angriff",
    "kontoübernahme": "angriff", "kontouebernahme": "angriff", "terrorism": "angriff",
    "bomb": "angriff", "poison": "angriff", "attacke": "angriff", "terrorist": "angriff",
    "promptinjection": "jailbreak", "prompt injection": "jailbreak",
}



_SYNONYME_NACH_LAENGE = tuple(sorted(
    ((k, v) for k, v in _SYNONYME.items() if len(k) >= 5 and k.isalpha()),
    key=lambda kv: -len(kv[0])))



_KEINE_ARTEN_ENDUNGEN = (
    "voranschlag", "tastenanschlag", "notenanschlag", "kopfanschlag", "coronavirus",
    "grippevirus", "influenzavirus", "herpesvirus", "rotavirus", "norovirus", "eisbombe",
    "sexbombe", "kalorienbombe", "vitaminbombe", "lifehacking", "badebombe", "antivirus",
    "lebensmittelvergiftung", "alkoholvergiftung", "pilzvergiftung", "rauchvergiftung",
    "blutvergiftung", "lärmbelästigung", "laermbelaestigung", "geruchsbelästigung",
    "geruchsbelaestigung", "rechtschreibmord",
)


_KEINE_ART = re.compile(
    r"\b(?:modell?ing|detection|intelligence|hunting|assessment|analysis|awareness|"
    r"erkennung|abwehr|pr(?:ä|ae)vention|prevention|defen[cs]e|verteidigung|aufkl(?:ä|ae)rung|"
    r"schulung|training)\b")


def _einzahl(wort: str) -> list[str]:
    """Das Wort und seine moegliche Einzahl ("Beleidigungen", "Exploits", "Terroristen")."""
    formen = [wort]
    for endung in ("ungen", "en", "es", "s", "n", "e"):
        if wort.endswith(endung) and len(wort) - len(endung) >= 4:
            formen.append(wort[: -len(endung)] + ("ung" if endung == "ungen" else ""))
    return formen


def normalize_category(art: str) -> str:
    """Ordnet die Beschreibung des Modells einer bekannten Art zu -- oder ""."""
    wort = str(art or "").strip().lower()
    if wort in _SYNONYME:
        return _SYNONYME[wort]
    teile = [t for t in re.split(r"[^a-zäöüß]+", wort) if t]


    if _KEINE_ART.search(wort) or "".join(teile).endswith(_KEINE_ARTEN_ENDUNGEN):
        return ""

    for form in ("-".join(teile), "".join(teile), " ".join(teile)):
        if form in _SYNONYME:
            return _SYNONYME[form]
    for teil in teile:
        for form in _einzahl(teil):
            if form in _SYNONYME:
                return _SYNONYME[form]


    for teil in teile:
        if teil.endswith(_KEINE_ARTEN_ENDUNGEN):
            continue
        for form in _einzahl(teil):
            for schluessel, kategorie in _SYNONYME_NACH_LAENGE:
                if len(form) > len(schluessel) and form.endswith(schluessel):
                    return kategorie
    return ""






















_BELEIDIGUNG_STUFEN: tuple[tuple[int, tuple[str, ...]], ...] = (

    (1, (
        "dumm", "dümm", "doof", "blöd", "bloed", "dämlich", "daemlich", "nutzlos", "unfähig",
        "unfaehig", "hirnlos", "peinlich", "doofi", "doofkopp", "heulsuse", "petze",
        "angsthase", "stinker", "langweiler", "kek", "noob", "npc", "cringe",
        "stupid", "dumb", "useless", "worthless", "lame", "dork", "nerd", "weirdo",
        "scheiß", "scheiss", "klugscheißer", "klugscheisser", "besserwisser", "nervensäge",
        "nervensaege", "pathetic", "trash", "garbage", "junk", "idiotisch", "lächerlich",
        "laecherlich", "ridiculous", "witzfigur", "lachnummer", "flasche", "nichtsnutz",
        "embarrassment", "disgrace", "clueless", "incompetent", "inkompetent",


        "lusche", "weichei", "warmduscher", "jammerlappen", "schwächling", "schwaechling",
        "feigling", "memme", "simp", "sheesh", "muppet", "twerp", "goober", "dummerchen",
        "schlaumeier", "erbsenzähler", "erbsenzaehler", "spießer", "spiesser", "banause",

        "dussel", "schafskopf", "tölpel", "toelpel", "trampel", "hampelmann", "kasper",
        "hanswurst", "pappnase", "spinner", "dödel", "doedel", "blödian", "bloedian",

        "hässlich", "haesslich", "widerlich", "ekelhaft", "abstoßend", "abstossend",
        "erbärmlich", "erbaermlich", "armselig", "jämmerlich", "jaemmerlich", "nervig",
        "stümper", "stuemper", "dilettant", "pfuscher", "faulpelz", "schnarchnase",
        "tranfunzel", "schlafmütze", "schlafmuetze", "trantüte", "trantuete", "dummbatz",
        "knallkopp", "blindfisch", "unterbelichtet", "wichtigtuer", "großkotz", "grosskotz",
        "schwätzer", "schwaetzer", "großmaul", "grossmaul", "schleimer", "fiesling",
        "dum", "ugly", "disgusting", "annoying", "wimp", "coward", "cringy", "cringey",
        "trashy", "brainless", "spineless", "liar", "failure", "lügner", "luegner",
    )),

    (2, (

        "opfer", "lauch", "lappen", "honk", "spacko", "otto", "vollopfer", "hurensohnopfer",

        "idiot", "idiotin", "vollidiot", "trottel", "volltrottel", "depp", "dummkopf",
        "penner", "versager", "loser", "vollpfosten", "pfosten", "pfeife", "flachpfeife",
        "knalltüte", "knalltuete", "hornochse", "esel", "schwachkopf", "hohlbirne", "hohlkopf",
        "dumpfbacke", "evolutionsbremse", "clown", "affe", "kuh", "sau", "schwein", "ratte",
        "pisser", "mistkerl", "blödmann", "bloedmann", "vollhonk", "zicke", "tussi",
        "schwachmat", "arsch", "bescheuert", "bekloppt", "beknackt", "gestört", "gestoert",
        "hirnverbrannt", "schwachsinnig", "strunzdumm", "saudumm", "dummbeutel", "sackgesicht",
        "kackbratze", "kackvogel", "pimmel", "pimmelkopf", "dumpfbacke", "vollversager",
        "behindert", "trottelig", "scheißbot", "scheissbot", "drecksbot", "mistbot",
        "scheißki", "scheisski", "scheißteil", "scheissteil",

        "armleuchter", "stinkstiefel", "halunke", "gewitterziege", "rindvieh",
        "taugenichts", "lump",

        "hirni", "vollhorst", "horst", "spacken", "assi", "asi", "prolet", "prollo",
        "eumel", "nulpe", "niete", "vollnull", "wappler", "grattler", "kacknoob",
        "volldepp", "vollzicke", "trulla", "schnepfe", "backpfeifengesicht", "vollpfeife",

        "moron", "jerk", "creep", "airhead", "nitwit", "dumbass", "scumbag",
        "fool", "imbecile", "cretin", "idiots", "chump", "dimwit", "halfwit", "bonehead",
        "blockhead", "knucklehead", "meathead", "jackass", "buffoon", "numbskull",
        "nincompoop", "dunce", "simpleton",

        "dummschwätzer", "dummschwaetzer", "labersack", "laberbacke", "kretin", "psychopath",
        "psycho", "gehirnamputiert", "hirnamputiert", "geistesgestört", "geistesgestoert",
        "minderbemittelt", "hohlfrucht", "vollhirni", "dumpfnuss", "arschgeige", "arschkeks",
        "arschkriecher", "bauerntrampel", "kotzbrocken", "ekelpaket", "mistvieh", "miststück",
        "miststueck", "saftsack", "pissnelke", "vollassi", "dreckspack", "gesindel",
        "pillock", "plonker", "numpty", "wazzock", "prat", "lowlife", "degenerate",
        "sleazebag", "sleazeball", "lunatic", "dirtbag", "loser", "clown",
    )),

    (3, (
        "arschloch", "wichser", "hurensohn", "missgeburt", "schlampe", "bastard", "fotze",
        "scheißkerl", "scheisskerl", "drecksack", "dreckskerl", "mistgeburt", "hure",
        "spast", "vollspast", "spasti", "mongo", "behindi", "schwuchtel", "kanake",
        "arschgesicht", "wixxer",

        "hodensack", "sackratte", "dreckschwein", "drecksschlampe", "drecksfotze",
        "nutte", "flittchen", "abschaum", "untermensch", "hurenkind", "wichsgesicht",
        "fickfehler", "hurenbock",
        "asshole", "bitch", "dickhead", "motherfucker", "prick", "twat", "wanker",
        "retard", "cunt", "slut", "whore", "fucker",

        "dipshit", "shithead", "dumbfuck", "cocksucker", "douchebag", "douche", "fuckface",
        "jackoff", "pissbaby", "shitbag", "cockhead", "arsehole",

        "drecksau", "dreckssau", "scheißhaufen", "scheisshaufen", "fickfresse", "wichsbirne",
        "ficker", "dreckstück", "drecksstück", "dreckstueck", "drecksstueck", "hurenschlampe",
        "tosser", "shitstain", "asswipe", "dickwad", "jerkoff", "twatwaffle", "scum",
    )),
)




_MEHRDEUTIG = frozenset({
    "esel", "kuh", "sau", "schwein", "ratte", "affe", "otto", "clown", "kasper", "lump",
    "pfeife", "pfosten", "fool", "nerd", "opfer", "lauch", "lappen", "zicke", "hure",
    "kek", "npc", "noob", "cringe", "creep", "petze", "stinker", "trampel",
    "dussel", "hampelmann", "hanswurst", "spinner", "versager", "loser", "penner",
    "mongo", "honk", "tussi", "dork", "langweiler", "bastard", "prick", "arsch",
    "flasche", "trash", "garbage", "junk", "pimmel", "gestört", "gestoert", "behindert",
    "horst", "niete", "eumel", "memme", "simp", "spiesser", "spießer", "banause",
    "schnepfe", "trulla", "jerk",
})



_NAMEN = frozenset({"otto", "kasper", "mongo", "honk"})


_ENDUNGEN = ("", "e", "er", "es", "en", "em", "s", "n", "in", "innen", "ste", "ster", "stes",
             "sten", "stem", "este", "ester", "estes", "esten", "estem", "est")


def _laeufe(wort: str) -> list[tuple[str, int]]:
    """ "dumm" -> [("d",1), ("u",1), ("m",2)]."""
    return [(m.group()[0], len(m.group())) for m in re.finditer(r"(.)\1*", wort)]


def _nicht_kuerzer(wort: str, vorlage: str) -> bool:
    """Hat *wort* jeden Buchstaben mindestens so oft wie *vorlage* (gestaucht gleich)?"""
    a, b = _laeufe(wort), _laeufe(vorlage)
    if [z for z, _ in a] != [z for z, _ in b]:
        return True
    return all(n >= m for (_, n), (_, m) in zip(a, b, strict=True))


def _gedehnt(wort: str) -> str:
    """Doppelte Buchstaben zu einem: "idiooot" und "idiot", "doof" und "dof" gleich."""
    return re.sub(r"(.)\1+", r"\1", wort)



_WURZELN: dict[str, tuple[int, str]] = {}
for _stufe, _liste in _BELEIDIGUNG_STUFEN:
    for _grund in _liste:
        _alt = _WURZELN.get(_gedehnt(_grund))
        if _alt is None or _alt[0] < _stufe:
            _WURZELN[_gedehnt(_grund)] = (_stufe, _grund)


_WURZELN_GENAU: dict[str, int] = {}
for _stufe, _liste in _BELEIDIGUNG_STUFEN:
    for _grund in _liste:
        _WURZELN_GENAU[_grund] = max(_stufe, _WURZELN_GENAU.get(_grund, 0))


_BELEIDIGUNG_WENDUNGEN: tuple[tuple[int, str], ...] = (
    (2, "blöde kuh"), (2, "bloede kuh"), (2, "dumme kuh"), (2, "dumme sau"),
    (2, "alter sack"), (2, "dumme nuss"), (2, "blöde nuss"), (2, "deine mutter"),
    (2, "piece of crap"), (2, "your mom"), (2, "yo mama"), (3, "piece of shit"),
    (3, "son of a bitch"), (3, "ich fick deine mutter"), (3, "fick deine mutter"),
    (3, "hurensohn du"), (3, "stück scheiße"), (3, "stueck scheisse"), (3, "stück scheisse"),
    (3, "stück dreck"),
)



_NUR_ALLEIN = frozenset({"deine mutter", "your mom", "yo mama"})


_DROHUNG_ENDE = (r"(?=\s*$|\s+(?:wenn|falls|if|du|you|ihr|bitch|alter|digga|ey|jetzt|now|"
                 r"noch|irgendwann|eines\s+tages|someday))")


_NACHDRUCK = r"(?:(?:einfach|mal|doch|jetzt|endlich|bitte|bloß|bloss|lieber|nun)\s+)*"


_WENDUNGEN: tuple[tuple[int, re.Pattern[str]], ...] = tuple(
    (stufe, re.compile(muster, re.IGNORECASE)) for stufe, muster in (
        (2, r"\b(?:halt|halts)\s+" + _NACHDRUCK + r"(?:die\s+klappe|den\s+mund)\b"

            r"(?=\s*$|\s+(?:du|ihr|bot|ki|ai|aquaticy|jetzt|endlich|mann|alter|digga|"
            r"verdammt|idiot|oder|und))|"

            r"(?:^|\b(?:just|oh|so|now|please|pls|you|u)\s+)shut\s+up\b"

            r"(?!\s+(?:a|an|the|my|this|that|it|them|him|her|and|und)\b)|\bstfu\b|"

            r"\bdu\s+kannst\s+mich\s+mal(?=[\s.!?]*$|\s+(?:am\s+arsch|kreuzweise|gern|du|"
            r"alter|digga))|"

            r"(?<!\bthe\s)(?<!\ba\s)(?<!\bone\s)(?<!\bthis\s)(?<!\bthat\s)"
            r"\bscrew\s+(?:you|u)\b|\bgtfo\b|\bfoad\b"),
        (3, r"\bf[iu]ck\s*dich\b|\bf[iu]ck(?:you|off)\b|\bverpissdich\b|"
            r"\bf[iu]ck\s+(?:you|u|off|yourself|urself)\b|\bhalt\s+" + _NACHDRUCK
            + r"(?:(?:die|deine)\s+fresse|die\s+schnauze|dein\s+(?:[^\W\d_]+\s+)?maul|"
            r"'?s\s+maul)\b|\bhalt(?:'s|s|\s+'s)\s+maul\b|"


            r"^(?:(?:ey|hey|jetzt|einfach|mal|du)\s+)*schnauze(?:\s+(?:du|jetzt))?\s*$|"
            r"\bfuck\s+(?:this|that)\s+(?:bot|ai|ki|shit|app)\b|\byou\s+(?:really\s+)?suck\b|"
            r"\b(?:ai|ki|bot|aquaticy)\s+sucks\b|\bshut\s+the\s+fuck\s+up\b|^f+\s*u+$|"
            r"^fuck\s+u$|\bdrop\s+dead\b(?!\s+(?:gorgeous|drop))|"
            r"\b(?:ich\s+hoffe|hoffentlich|i\s+hope)\s+(?:du|you)\s+(?:stirbst|die|diest)\b"

            r"(?!\s+(?:nicht|nie|niemals|not|never|happy|old|peacefully|in\s+peace|gl(?:ü|ue)cklich|"
            r"alt|friedlich))|"
            r"\bverpiss\s+dich\b|\bgo\s+to\s+hell\b|"
            r"\bleck\s+mich\s+(?:am\s+arsch|doch)\b|\bkill\s+(?:yourself|urself)\b|\bkys\b|"
            r"\bgeh\s+(?:doch\s+)?sterben\b|\bh(?:ä|ae)ng\s+dich\s+(?:doch\s+)?auf\b|"

            r"^\s*bring\s+dich\s+(?:doch\s+)?um\b|(?<!\blet's\s)(?<!\blets\s)\bgo\s+die\b"
            r"(?!\s+(?:the|my|your|some|eggs?|it|them|this|that|hair|clothes|shirts?)\b)"),



        (4, r"\bich\s+(?:bring|bringe|werde|will|wird|mach|mache)\s+dich\s+"
            r"(?:[^\W\d_]+\s+){0,3}?(?:um|umbringen|t(?:ö|oe)ten|abstechen|erschie(?:ß|ss)en|"
            r"abknallen|kaltmachen|killen|kalt\s+machen|kalt|fertig|platt|fertigmachen|"
            r"plattmachen)" + _DROHUNG_ENDE
            + r"|\bich\s+(?:stech|steche|knall|knalle|schlag|schlage)\s+dich\s+"
            r"(?:[^\W\d_]+\s+){0,2}?(?:ab|nieder|tot|zusammen|krankenhausreif|windelweich)"
            + _DROHUNG_ENDE
            + r"|\bich\b.{0,40}?\bmach(?:e)?\s+dich\s+(?:kalt|fertig|platt)" + _DROHUNG_ENDE
            + r"|\bi(?:'ll|\s+will|'m\s+gonna|\s+gonna|\s+am\s+going\s+to|'m\s+going\s+to)\s+"
            r"(?:hurt|beat|punch|find)\s+(?:you|u)" + _DROHUNG_ENDE
            + r"|\bich\s+t(?:ö|oe)te\s+dich" + _DROHUNG_ENDE
            + r"|\bi(?:'ll|\s+will|\s+am\s+going\s+to|'m\s+going\s+to|'m\s+gonna|\s+gonna)\s+"
            r"(?:[^\W\d_]+\s+)?(?:kill|murder|stab|shoot)\s+(?:you|u)" + _DROHUNG_ENDE),

        (1, r"^\s*du\s+nervst(?:\s+(?:so|echt|voll|total|mich))*[\s!.]*$"),
        (2, r"^\s*klappe[\s!.]*$|^\s*leck\s+mich[\s!.]*$|\bshut\s+your\s+(?:mouth|face|trap)\b|"
            r"^\s*piss\s+off\b|"
            r"\b(?:du\s+bist|you(?:'re|\s+are))\s+(?:(?:ein|a|so|echt|total|nur|just|der\s+letzte|"
            r"the\s+biggest)\s+)*(?:st(?:ü|ue)ck\s+)?(?:m(?:ü|ue)ll|abschaum|garbage|"
            r"piece\s+of\s+(?:garbage|trash|junk|crap))(?=[\s!.]*$|\s+(?:du|you)\b)"),
        (3, r"^\s*fresse[\s!.]*$|^\s*(?:maul|fresse)\s+halten[\s!.]*$"),
    )
)




_WENDUNGEN_GESTAUCHT: tuple[tuple[int, re.Pattern[str]], ...] = tuple(
    (stufe, re.compile(re.sub(r"(?<!\\)([a-zäöüß])\1", r"\1+", muster.pattern), re.IGNORECASE))
    for stufe, muster in _WENDUNGEN
)



_PHRASEN_WOERTER: frozenset[str] = frozenset(
    wort for _, muster in _WENDUNGEN
    for wort in re.findall(r"[a-zäöüß]{4,}", re.sub(r"\\[a-zA-Z]", " ", muster.pattern))
) | frozenset(w for _, wendung in _BELEIDIGUNG_WENDUNGEN for w in wendung.split() if len(w) >= 4
              ) | frozenset({"verpiss", "screw", "halts", "maul", "klappe", "fresse", "schnauze",
                             "piece", "shit", "shut", "kill", "yourself", "stirb", "verrecke"})



_META = re.compile(
    r"beleidig|strafbar|stgb|§|schimpfw|synonym|übersetz|uebersetz|bedeut|definition|"
    r"meaning|\bmeans?\b|auf englisch|auf deutsch|in english|in german|gesagt|\bsagte|"
    r"\bsagt\b|genannt|\bnannte|\bnennt|beschimpft|\bcalled\b|\bsaid\b|\btold\b|\bwort\b|"
    r"zitat|\bquote|\bword\b|herkunft|etymolog|\bmeme|\bwitz(?:e|en)?\b|\bjokes?\b|erklärung|"
    r"erklaerung|songtext|\blyrics|\brapper|medizinisch|\bmedizin|sprichw|redewendung|"
    r"\bunhöflich|\bunhoeflich|\brude\b|abk(?:ü|ue)rz|\babbreviation|\bacronym|"
    r"\bstands\s+for\b|\bsteht\s+f(?:ü|ue)r\b",
    re.IGNORECASE,
)


_ZITAT_ANLASS = re.compile(
    _META.pattern + r"|\blied|\bsong|\bfilm|\bbuch|\broman|\btitel|\bserie|\bheißt|\bheisst|"
    r"\bname\b|\btitle\b|\bmovie\b|\bbook\b|beispiel|z\.\s*b\.|\betwa\b|z(?:ä|ae)hlt|"
    r"erkannt|erkennt|\bokay\b|\bok\b|erlaubt|verboten|drohung|\bmeme|spruch|slang|"
    r"ausdruck|jugendwort|suizid|selbstmord|suicid|\bhöflich|\bhoeflich|\bfrech|\bgemein|"


    r"anzeig|\bklage|\bverklag|polizei|\bgericht|\bstrafe|\bsue\b|\bpolice\b|"
    r"\bmeint\w*\s+(?:[^\W\d_]+\s+){0,3}mit\b|\bmeans?\b|\bmeant\b|\bmeaning\b",
    re.IGNORECASE,
)

_TITELZEILE = re.compile(r"^\s*[A-ZÄÖÜ][\w'.&]*(?:\s+[A-ZÄÖÜ&][\w'.&]*){0,4}\s+[-–—]\s+\S")


_REDE = re.compile(
    r"\b(?:sagt|sagte|gesagt|ruft|rief|gerufen|schreit|schrie|geschrien|br(?:ü|ue)llt|"
    r"gebr(?:ü|ue)llt|meint|meinte|gemeint|antwortet|antwortete|geantwortet|schreibt|schrieb|"
    r"geschrieben|textet|getextet|nannte|genannt|beschimpft|says|said|shouts|shouted|yells|"
    r"yelled|replies|replied|wrote|texted|called\s+me|told\s+me|gedroht|drohte|droht|"
    r"threatened|threatens)"






    r"(?:(?:\s+(?:zu\s+)?(?:mir|uns|me|us))?\s*[:,]|"
    r"(?:\s+(?!(?:dir|dich|euch|you|ihnen)\b)[^\W\d_]+){1,3}?\s*:)\s*[^\n.?!]*")


_SPRECHER = re.compile(r"(?m)^\s*(?:[-*>]\s*)?\**[^\W\d_][\w .'-]{0,29}:\**\s.*$")
_ZITATE = re.compile(r"\"[^\"]{1,200}\"|„[^“”]{1,200}[“”]|“[^”]{1,200}”|«[^»]{1,200}»|"
                     r"»[^«]{1,200}«|‚[^‘’]{1,200}[‘’]|(?<![^\W\d_])'[^']{1,200}'(?![^\W\d_])")
_ANREDE = r"(?:du|dich|dir|sie|ihr|you|u|ur|aquaticy|ki|ai|bot)"
_KOPULA = r"(?:bist|are|is|ist|sind|seid|warst|wart|were|r)"
_FUELLWORT = (r"(?:so|echt|voll|total|wirklich|einfach|ein|eine|einer|so\s+ein|so\s+eine|a|an|"
              r"such\s+a|ja|doch|halt|nur|mal|the|the\s+biggest|n|'n)")
_ARTIKEL = r"(?:ein|eine|einer|a|an|so\s+ein|so\s+eine|such\s+a|der|die|the|'n|n)"


_LUECKE = (r"(?:(?!(?:nicht(?!\s+nur\b)|kein\w*|not(?!\s+only\b)|no|never|nie|niemals|"
           r"isn't|aren't)\b)[^\W\d_]+\s+){0,3}")

_ADJEKTIV = (r"(?:(?!(?:are|were|seid|sind|sie|ihre|ohne|habe|eine|keine|nicht)\b)"
             r"[^\W\d_]+(?:er|es|e|en|em)\s+){0,2}")

_NICHT = r"(?:(?:ja|gar|doch|echt|wirklich|auch|eben|halt)\s+)?(?:nicht|not|kein\w*)\b"


_KEIN_VERB = (r"(?!\s+(?:the|a|an|me|him|her|it|them|us|nobody|everyone|everybody|anyone|"
              r"around|out|up|off|with|into|on|to|my|your|his|their|this|that)\b)")


_VERNEINTE_MEINUNG = re.compile(
    r"\b(?:nobody|no\s+one|niemand|keiner)\s+(?:thinks|think|says|said|glaubt|denkt|findet|"
    r"sagt|behauptet)\b|\b(?:i|we)\s+(?:don't|do\s+not|didn't|never)\s+(?:think|say|said|"
    r"believe|mean|meant)\b|\bich\s+(?:finde|glaube|denke|sage|meine)\s+(?:gar\s+)?(?:nicht|nie)\b|"
    r"\b(?:anything|everything)\s+but\b|\balles\s+andere\s+als\b|\bweder\b|\bneither\b|"
    r"\b(?:ja|gar|doch|echt|wirklich)\s+nicht\s*$",
)


_GEGENTEIL = re.compile(
    r"\b(du\s+bist|you(?:'re|\s+are))\s+(?:nicht|kein\w*|not)\b[^,.;!?]{0,40}?,?\s*"
    r"(?:sondern|but\s+(?:rather\s+)?)\s*(?=\S)")

_ROLLE = re.compile(
    r"\bim\s+spiel\b|\bin\s+the\s+game\b|krippenspiel|theaterst|\brolle\b|\bspielst\s+du\b|"
    r"\blied\s+(?:mit|namens)\b|\bsong\s+(?:with|called)\b|\bim\s+film\b")

_UEBERSETZEN = re.compile(r"^\s*(?:bitte\s+)?(?:(?:ü|ue)bersetz\w*|translate|übersetzung)\b")

_AUSRUF = r"(?:(?:hey|ey|eh|oh|och|ach|na|und|so|you|hallo|hi|yo|also)\s+)*"
_UNSICHTBAR = re.compile(r"[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180e\u200b-\u200f"
                         r"\u202a-\u202e\u2060-\u206f\ufe00-\ufe0f\ufeff]")

_DOPPELGAENGER = str.maketrans({
    "а": "a", "е": "e", "ё": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "і": "i", "ї": "i", "ј": "j", "ѕ": "s", "к": "k", "м": "m", "т": "t", "н": "h",
    "ԁ": "d", "ɑ": "a", "ο": "o", "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "v",
    "τ": "t", "υ": "u", "ρ": "p", "χ": "x", "и": "i", "д": "d", "л": "l", "б": "b",

    "ᴀ": "a", "ʙ": "b", "ᴄ": "c", "ᴅ": "d", "ᴇ": "e", "ғ": "f", "ɢ": "g", "ʜ": "h",
    "ɪ": "i", "ᴊ": "j", "ᴋ": "k", "ʟ": "l", "ᴍ": "m", "ɴ": "n", "ᴏ": "o", "ᴘ": "p",
    "ǫ": "q", "ʀ": "r", "ꜱ": "s", "ᴛ": "t", "ᴜ": "u", "ᴠ": "v", "ᴡ": "w", "ʏ": "y",
    "ᴢ": "z",
})
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a",
                       "$": "s", "!": "i", "|": "i", "€": "e"})
_TOKEN = re.compile(r"\S+")


def _entleet(token: str) -> str:
    """ "Id1ot" -> "idiot", "@rschl0ch" -> "arschloch" -- nur mitten in Woertern."""
    if not re.search(r"[013457@$!|€]", token):
        return token
    kern = token.rstrip("!?.,;:)")
    rest = token[len(kern):]



    neu = kern.translate(_LEET)
    buchstaben = len(re.findall(r"[^\W\d_]", kern))
    if re.fullmatch(r"(?:[^\W\d_]|[*#])+(?:['’][^\W\d_]+)*", neu) and (
            buchstaben >= 2 or neu in _FUNKTIONSWOERTER):
        return neu + rest
    return token


def _punktiert(token: str) -> str:
    """ "i.d.1.o.t!" -> "idiot!": einzelne Zeichen mit Trennern UND Leetspeak (9.5.32)."""
    treffer = re.fullmatch(r"((?:[^\W_]['’]?[.\-_·*]){2,}[^\W_])([!?.,;:]*)", token)
    if not treffer or not re.search(r"[013457]", treffer.group(1)):
        return token
    wort = re.sub(r"[.\-_·*]", "", treffer.group(1)).translate(_LEET)
    if len(re.findall(r"[^\W\d_]", treffer.group(1))) >= 2 and re.fullmatch(
            r"[^\W\d_]+(?:['’][^\W\d_]+)*", wort):
        return wort + treffer.group(2)
    return token




_FUNKTIONSWOERTER = (
    "du", "dich", "dir", "dein", "deine", "bist", "ist", "sind", "seid", "ihr", "sie",
    "you", "your", "you're", "are", "is", "ur", "aquaticy", "ki", "bot", "halt", "so",
    "voll", "echt", "total", "ein", "eine", "einer", "ey", "hey", "a", "an", "the",
    "was", "what", "wie", "how", "i'm", "i", "am",
)
_FUNKTION_GEDEHNT: dict[str, str] = {}
for _wort in _FUNKTIONSWOERTER:
    _FUNKTION_GEDEHNT.setdefault(re.sub(r"(.)\1+", r"\1", _wort), _wort)


def _funktionswort(token: str) -> str:
    """ "youu" -> "you", "biiist" -> "bist" -- nur fuer die Woerter oben."""
    kern = token.rstrip("!?.,;:")
    if not kern or not re.search(r"(.)\1", kern):
        return token
    gedehnt = re.sub(r"(.)\1+", r"\1", kern)
    passend = _FUNKTION_GEDEHNT.get(gedehnt)
    return passend + token[len(kern):] if passend else token




_GEBEUGT: frozenset[str] = frozenset(
    grund + endung
    for _, liste in _BELEIDIGUNG_STUFEN for grund in liste if len(grund) >= 4
    for endung in _ENDUNGEN
)


def _ohne_akzente(text: str) -> str:
    """ "dúmm" -> "dumm", "blödé" -> "blöde": Akzente weg, Umlaute und ß bleiben."""
    if text.isascii():
        return text
    aus = []
    for zeichen in text:
        if zeichen in "äöüß" or zeichen.isascii():
            aus.append(zeichen)
            continue
        zerlegt = unicodedata.normalize("NFKD", zeichen)
        basis = "".join(z for z in zerlegt if not unicodedata.combining(z))
        aus.append(basis if basis else zeichen)
    return "".join(aus)


def _symbole_raus(text: str) -> str:
    """Emojis und Bildzeichen zwischen Buchstaben weg: "d🙂u🙂m🙂m" -> "dumm" (9.5.32)."""
    if text.isascii():
        return text
    return re.sub(
        r"(?<=[^\W\d_]|['’*#])(?:[\U0001F000-\U0001FAFF\u2190-\u2BFF\uFE0F\u200D\u20E3]"
        r"|[\U0001F3FB-\U0001F3FF])+(?=[^\W\d_]|['’*#])",
        "", text)


def _sternchen(token: str) -> str:
    """ "A****loch" -> "arschloch" -- Satzzeichen davor und dahinter bleiben (9.5.32)."""
    if not re.search(r"[*#]", token):
        return token
    kern = token.strip("!?.,;:()")
    if not kern:
        return token
    vorne = token[: token.index(kern)]
    hinten = token[token.index(kern) + len(kern):]
    neu = _sternchen_kern(token)
    return neu if neu == token else vorne + neu + hinten


@functools.lru_cache(maxsize=8192)
def _sternchen_kern(token: str) -> str:
    """ "A****loch" -> "arschloch", wenn genau ein bekanntes Schimpfwort passt.

    Zwischengespeichert und ohne Markdown ("**fett**", "*kursiv*"): bis 9.5.33
    brauchte eine lange Nachricht mit vielen Sternchen ueber 30 Sekunden.
    """
    if not re.search(r"[*#]", token):
        return token
    kern = token.strip("!?.,;:()")
    if (kern[:1] in "*#" and not re.search(r"[*#]", kern.strip("*#"))) or len(kern) > 40:
        return token
    if len(re.findall(r"[^\W\d_]", kern)) < 2 or not re.fullmatch(
            r"(?:[^\W\d_]|[*#]|['’])+", kern):
        return token

    ohne = re.sub(r"[*#]", "", kern)
    if re.fullmatch(r"(?:[^\W\d_][*#]+){2,}[^\W\d_]", kern) and _stufe_von(ohne)[0]:
        return ohne
    teile = [re.escape(t) for t in re.split(r"[*#]+", kern)]



    luecken = [len(z) for z in re.findall(r"[*#]+", kern)]
    muster = re.compile("^" + "".join(
        teil + (rf"[^\W\d_]{{{luecken[i]},{luecken[i] + 1}}}" if i < len(luecken) else "")
        for i, teil in enumerate(teile)) + "$")
    passend = {grund for _, liste in _BELEIDIGUNG_STUFEN for grund in liste
               if len(grund) >= 4 and muster.match(grund)}
    if not passend:

        passend = {wort for wort in _GEBEUGT | set(_FUNKTIONSWOERTER) | _PHRASEN_WOERTER
                   if len(wort) >= 4 and muster.match(wort)}
    fluch = {w for w in ("fuck", "fick") if muster.match(w)}
    passend -= {"fuck", "fick"}
    if fluch and not passend:

        return "fuck" if "fuck" in fluch else "fick"

    gruppen = {w.replace("ö", "oe").replace("ä", "ae").replace("ü", "ue").replace("ß", "ss")
               for w in passend}
    if len(gruppen) == 1 and passend:
        return max(passend, key=lambda w: sum(z in "äöüß" for z in w))





    sterne = len(re.findall(r"[*#]", kern))
    if not passend and 1 <= sterne <= 2 and len(kern) >= 5:
        import itertools

        alphabet = "abcdefghijklmnopqrstuvwxyzäöüß"
        treffer_woerter = set()
        stuecke = re.split(r"[*#]", kern.lower())
        for fuellung in itertools.product(alphabet, repeat=sterne):
            kandidat = stuecke[0] + "".join(
                buchstabe + stueck for buchstabe, stueck in zip(fuellung, stuecke[1:],
                                                                strict=True))
            if _stufe_von(kandidat)[0] or _zusammensetzung(kandidat):
                treffer_woerter.add(kandidat)
        if len(treffer_woerter) == 1:
            return treffer_woerter.pop()



    return token


def _zusammen(trenner: str, treffer: re.Match[str]) -> str:
    """Getrennte Buchstaben wieder zu einem Wort.

    Seit 9.5.32 auch mit Apostroph und Leetspeak ("y o u ' r e", "I d 1 o t") --
    nur, wenn mindestens zwei echte Buchstaben dabei sind (Zahlen bleiben).
    Ein Artikel davor ("a b i t c h") wird wieder abgetrennt.
    """
    roh = treffer.group()
    if len(re.findall(r"[^\W\d_]", roh)) < 2:
        return roh
    wort = re.sub(trenner, "", roh)
    if re.search(r"[*#]", wort):
        wort = _sternchen(_entleet(wort))
        if re.search(r"[*#]", wort):
            return roh
    if re.search(r"\d", wort):
        wort = _entleet(wort)
        if re.search(r"\d", wort):
            return roh
    if len(wort) > 4 and wort[0] in "ai" and not _stufe_von(wort)[0] and _stufe_von(wort[1:])[0]:
        return wort[0] + " " + wort[1:]
    return _anrede_abtrennen(wort)


def _anrede_abtrennen(wort: str) -> str:
    """ "duidiot" / "du_1d10t" -> "du idiot": Anrede und Schimpfwort zusammengeklebt."""
    teile = re.split(r"[_\-.]+", wort)
    if len(teile) >= 2 and teile[0] in ("du", "you", "u", "ihr"):
        rest = _entleet("".join(teile[1:]))
        if _stufe_von(rest)[0]:
            return teile[0] + " " + rest
    for anrede in ("du", "you"):
        if wort.startswith(anrede) and len(wort) > len(anrede) + 3:
            rest = wort[len(anrede):]
            if _stufe_von(rest)[0] and not _stufe_von(wort)[0]:
                return anrede + " " + rest
    return wort


_MAX_STERNCHEN = 300


def _vereinheitlicht(text: str) -> str:
    """Macht Tarnungen rueckgaengig, bevor gesucht wird."""
    klein = unicodedata.normalize("NFKC", str(text or "")).lower()
    klein = _UNSICHTBAR.sub("", klein).translate(_DOPPELGAENGER)


    klein = _symbole_raus(_ohne_akzente(klein))



    for trenner in (r"[.\-_·/\\]+", r" +"):
        klein = re.sub(
            rf"(?<![^\W_])(?:[^\W_'’*#]{trenner}|['’*#]{trenner}){{2,}}[^\W_'’*#](?![^\W_])",
            functools.partial(_zusammen, trenner), klein)

    klein = re.sub(r"(?<=[^\W\d_]) ?['’] ?(?=[^\W\d_](?:\s|$|[^\W\d_]))", "'", klein)





    rest = [_MAX_STERNCHEN]

    def _token(m: re.Match[str]) -> str:
        wort = m.group()
        wort = _anrede_abtrennen(wort) if re.search(r"[_\-.]", wort) else wort
        wort = _entleet(_punktiert(wort))
        if re.search(r"[*#]", wort):
            if rest[0] <= 0:
                return _funktionswort(wort)
            rest[0] -= 1
            wort = _sternchen(wort)
        return _funktionswort(wort)

    klein = _TOKEN.sub(_token, klein)
    klein = re.sub(r"\byou['’]re\b", "you are", klein)
    klein = re.sub(r"\b(?:fck|fuk|fuq|fuc|phuck|fucc|fvck|fk)\b", "fuck", klein)
    klein = re.sub(r"\bu\s+r\b", "you are", klein)
    return " ".join(klein.split())





_VORNE = ("voll", "ober", "riesen", "mega", "super", "ultra", "erz", "kack", "scheiß",
          "scheiss", "dreck", "drecks", "mist", "hohl", "dumm", "blöd", "bloed", "schwach",
          "flach", "hack", "knall", "doof", "dämlich", "daemlich", "stroh", "pimmel", "arsch",
          "sack", "spatzen", "hirn", "hirnlos", "stink", "dorf", "fach", "kotz", "rotz",
          "pisser", "wixx", "wichs", "hurens", "vollpfosten", "pups")
_HINTEN = ("kopf", "köpfe", "fresse", "gesicht", "birne", "zange", "horst", "batz", "nase",
           "backe", "bratze", "spaten", "pfosten", "pfeife", "tüte", "tuete", "sack", "bot",
           "ki", "brot", "hirn", "hose", "lappen", "vogel", "affe", "kuh", "sau", "schwein")



_LOB_VORNE = frozenset({"super", "mega", "ultra"})


@functools.lru_cache(maxsize=8192)
def _zusammensetzung(wort: str) -> int:
    """Stufe eines zusammengesetzten Schimpfworts -- 0, wenn keins."""
    if len(wort) < 6:
        return 0
    for vorne in _VORNE:
        if not wort.startswith(vorne) or len(wort) <= len(vorne) + 1:
            continue
        rest = wort[len(vorne):].lstrip("s-")


        if vorne not in _LOB_VORNE and (
                rest in _HINTEN or any(rest == h + e for h in _HINTEN
                                       for e in ("e", "en", "n", "s"))):
            return 2
        stufe, grund = _stufe_von(rest) if len(rest) >= 4 else (0, "")
        if stufe >= 2 and len(grund) >= 4:
            return max(2, stufe)
    return 0




_ENDUNGEN_GEDEHNT = tuple((endung, _gedehnt(endung)) for endung in _ENDUNGEN)





_KEINE_SCHIMPFWOERTER = frozenset({
    "creeper", "creepers", "junker", "junkers", "bitchin", "foolin", "fooling",
    "wimper", "wimpern", "pratt",
})


@functools.lru_cache(maxsize=8192)
def _stufe_von(wort: str) -> tuple[int, str]:
    """(Stufe, Wurzel) fuer ein einzelnes Wort -- (0, "") wenn keins."""
    if wort in _KEINE_SCHIMPFWOERTER:
        return 0, ""

    for endung in _ENDUNGEN:
        if endung and not wort.endswith(endung):
            continue
        roh = wort[: len(wort) - len(endung)] if endung else wort
        if roh in _WURZELN_GENAU and (not endung or len(roh) > 3):
            return _WURZELN_GENAU[roh], roh
    gedehnt = _gedehnt(wort)
    for endung, kurz in _ENDUNGEN_GEDEHNT:
        if endung and not gedehnt.endswith(kurz):
            continue
        stamm = gedehnt[: len(gedehnt) - len(kurz)] if endung else gedehnt
        treffer = _WURZELN.get(stamm)




        if (treffer and (not endung or len(treffer[1]) > 3)
                and _nicht_kuerzer(wort, treffer[1] + endung)):
            return treffer
    if wort.startswith("l") and len(wort) >= 5:



        ersatz = _stufe_von("i" + wort[1:])
        if ersatz[0] >= 2 and ersatz[1] not in _MEHRDEUTIG:
            return ersatz
    return 0, ""


def _zusammengesetzt(klein: str) -> str:
    """ "arsch loch" -> "arschloch": ein getrenntes Schimpfwort wieder zusammen."""
    def verbunden(token: str) -> str:

        teile = re.split(r"[-_.·]+", token)
        if len(teile) < 2 or not all(t.isalpha() for t in teile):
            return token
        ganz = "".join(teile)
        return ganz if _stufe_von(ganz)[0] >= 2 else token

    woerter = [verbunden(w) for w in klein.split(" ")]
    if len(woerter) < 2:
        return " ".join(woerter)
    aus: list[str] = []
    i = 0
    while i < len(woerter):
        if i + 1 < len(woerter) and woerter[i].isalpha() and woerter[i + 1].isalpha():
            zusammen = woerter[i] + woerter[i + 1]
            ganz, _ = _stufe_von(zusammen)
            teile = max(_stufe_von(woerter[i])[0], _stufe_von(woerter[i + 1])[0])
            if len(zusammen) >= 6 and ganz >= 2 and ganz > teile:
                aus.append(zusammen)
                i += 2
                continue
        aus.append(woerter[i])
        i += 1
    return " ".join(aus)


def _dritte_person(teil: str) -> str:
    """Nimmt Stellen heraus, an denen "sie", "Bot" oder "KI" nicht angesprochen
    sind (9.5.34): "Sie ist nutzlos" (die neue Version), "my Discord bot is
    useless", "how to build a dumb bot", "Ist KI dumm?".
    """
    teil = re.sub(r"\bsie\s+(ist|war|is|was)\b", r"es \1", teil)
    teil = re.sub(r"\b(my|mein\w*|his|her|our|unser\w*|their|sein\w*)\s+((?:[^\W\d_]+\s+){0,2}?)"
                  r"(?:bot|ki|ai|chatbot)\b", r"\1 \2programm", teil)
    teil = re.sub(r"\b(build|make|create|code|write|program|bau\w*|erstell\w*|programmier\w*|"
                  r"schreib\w*|cod\w*)\s+(a|an|ein\w*)\s+((?:[^\W\d_]+\s+){0,2}?)"
                  r"(?:bot|ki|ai|chatbot)\b", r"\1 \2 \3programm", teil)
    return re.sub(r"^(ist|is)\s+(?:ki|ai)\b", r"\1 technik", teil)


def _satzteil_stufe(teil: str, ganze_woerter: int, anrede: bool = False) -> int:
    """Stufe einer gerichteten Beleidigung in einem Satzteil (ohne Satzzeichen).

    *anrede*: spricht die Nachricht irgendwo jemanden an ("du", "you", "KI")?
    """
    stufe = 0
    teil = _dritte_person(teil)
    woerter = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", teil)
    for wert, wendung in _BELEIDIGUNG_WENDUNGEN:
        if not re.search(rf"\b{re.escape(wendung)}\b", teil):
            continue

        extra = 0 if wendung in _NUR_ALLEIN else 2
        if (len(woerter) <= len(wendung.split()) + extra
                or re.search(rf"\b{_ANREDE}\s+(?:{_KOPULA}\s+)?(?:{_FUELLWORT}\s+)*"
                             rf"{re.escape(wendung)}\b", teil)
                or wendung.startswith(("ich fick", "fick"))):
            stufe = max(stufe, wert)
    for wort in dict.fromkeys(woerter):
        wert, grund = _stufe_von(wort)
        if not wert:
            wert = _zusammensetzung(wort)
            grund = wort
        if not wert:
            continue
        w = re.escape(wort)
        mehrdeutig = grund in _MEHRDEUTIG
        vor = _ARTIKEL + r"\s+(?:[^\W\d_]+\s+)?" if mehrdeutig else _LUECKE


        ohne_artikel = mehrdeutig and grund not in _NAMEN
        gerichtet = (



            re.search(rf"^{_AUSRUF}{_ANREDE}\s+(?:{_FUELLWORT}\s+)*{_ADJEKTIV}{w}(?![-\w])"
                      + (_KEIN_VERB if mehrdeutig else ""), teil)

            or (not mehrdeutig and re.search(
                rf"\b{_ANREDE}\s+(?:{_FUELLWORT}\s+)*{_ADJEKTIV}{w}\s*$", teil))

            or re.search(rf"\b(?:wie|so|how|what|was\s+f(?:ü|ue)r|what\s+an?|such\s+an?)\s+"
                         rf"(?:(?:ein|eine|einen|a|an)\s+)?{_ADJEKTIV}{w}\s+"
                         rf"(?:{_KOPULA}\s+{_ANREDE}|{_ANREDE}\s+{_KOPULA})\b"
                         rf"(?!\s+{_NICHT})", teil)

            or re.search(rf"^{_ADJEKTIV}{w}\s+(?:{_KOPULA}\s+{_ANREDE}|{_ANREDE}\s+{_KOPULA})\b"
                         rf"(?!\s+{_NICHT})", teil)

            or re.search(rf"^{w}\s+(?:als|than)\s+{_ANREDE}\b", teil)

            or re.search(rf"\b{_ANREDE}\s+{_KOPULA}\s+(?:{_FUELLWORT}\s+)*{vor}{w}(?![-\w])"
                         rf"(?!\s+(?:good|great|gut|schnell|fast|toll|clever|smart|nice|cool|"
                         rf"lustig|funny|helpful|hilfreich)\b)", teil)

            or re.search(rf"\b{_KOPULA}\s+{_ANREDE}\s+(?:{_FUELLWORT}\s+)*{vor}{w}(?![-\w])",
                         teil)
            or (ohne_artikel and re.search(
                rf"\b(?:{_ANREDE}\s+{_KOPULA}|{_KOPULA}\s+{_ANREDE})\s+(?:{_FUELLWORT}\s+)*"
                rf"{w}\s*$", teil))

            or re.search(rf"\b{w}\s+{_ANREDE}\s*$", teil)

            or re.search(rf"\b{w}\s+(?:bot|ki|ai|aquaticy|chatbot)(?![-\w])", teil)

            or (ganze_woerter <= 3 and re.search(
                rf"\b{w}\s+(?:maschine|ding|teil|programm|kiste|software)\s*$", teil))

            or (ganze_woerter <= 5 and re.search(
                rf"\b{w}\s+piece\s+of\s+(?:junk|trash|garbage|crap)\s*$", teil))

            or (ganze_woerter <= 3 and len(woerter) <= 3 and wert >= 2 and not mehrdeutig
                and woerter[-1] == wort
                and not re.match(r"(?:der|die|das|den|the|this|dieser|diese|they|he|she|we|"
                                 r"er|sie|es|wir|they're|he's|she's)\b", teil))


            or (anrede and len(woerter) == 1 and wert >= 2 and not mehrdeutig)
        )
        if gerichtet:
            stufe = max(stufe, wert)
    return stufe









_GANZ_ENDE = r"(?=[\s.!?…]*$)"

_DROHUNGEN_GANZ: tuple[tuple[int, re.Pattern[str]], ...] = tuple(
    (stufe, re.compile(muster, re.IGNORECASE)) for stufe, muster in (
        (3, r"\bich\s+wei(?:ß|ss)\s*,?\s*wo\s+du\s+wohnst" + _GANZ_ENDE),
        (3, r"\bi\s+know\s+where\s+you\s+live" + _GANZ_ENDE),
        (4, r"\bich\s+(?:polier|poliere|hau|haue|schlag|schlage|tret|trete)\s+dir\s+"
            r"(?:[^\W\d_]+\s+){0,3}?(?:die\s+fresse|die\s+z(?:ä|ae)hne|eine\s+rein|eins\s+rein|"
            r"in\s+die\s+fresse|ins\s+gesicht|den\s+sch(?:ä|ae)del)\b"),
        (4, r"\bi(?:'ll|\s+will|'m\s+gonna|\s+gonna)\s+(?:smash|break|bash|kick\s+in)\s+"
            r"your\s+(?:face|head|skull|teeth|legs?)\b"),
        (4, r"\bdu\s+bist\s+(?:so\s+)?gut\s+wie\s+tot" + _GANZ_ENDE),
        (4, r"\byou(?:'re|\s+are)\s+(?:so\s+)?dead\s+meat" + _GANZ_ENDE),


        (4, r"\bich\s+(?:z(?:ü|ue)nde|z(?:ü|ue)nd|werde|will)\s+(?:dir\s+)?(?:dein\w*|euer\w*)\s+"
            r"(?:haus|wohnung|auto|bude|laden)\s+(?:[^\W\d_]+\s+)?(?:an|anz(?:ü|ue)nden|"
            r"abfackeln|abbrennen)" + _GANZ_ENDE),
        (4, r"\bi(?:'ll|\s+will|'m\s+going\s+to|'m\s+gonna|\s+am\s+going\s+to)\s+"
            r"(?:burn|torch)\s+(?:down\s+)?your\s+(?:house|home|car)(?:\s+down)?" + _GANZ_ENDE),
        (3, r"\bich\s+(?:werde|will|wird)\s+dich\s+finden\s+und\s+(?:[^\W\d_]+\s+){0,2}?"
            r"(?:fertig\s*machen|umbringen|t(?:ö|oe)ten|kalt\s*machen|platt\s*machen|verletzen)"
            + _GANZ_ENDE),
        (3, r"\byou\s+(?:should|deserve\s+to|ought\s+to)\s+die" + _GANZ_ENDE),
        (3, r"\bdu\s+(?:solltest|sollst)\s+(?:sterben|verrecken)" + _GANZ_ENDE),
        (3, r"^\s*(?:stirb|verrecke|verreck)\s*(?:doch|endlich)?\s*(?:du\s+\w+)?" + _GANZ_ENDE),
        (3, r"^\s*du\s+wirst\s+es\s+(?:noch\s+)?bereuen" + _GANZ_ENDE),
        (3, r"^\s*you(?:'ll|\s+will)\s+regret\s+(?:it|this)" + _GANZ_ENDE),
        (2, r"^\s*pass\s+(?:blo(?:ß|ss)\s+|lieber\s+|ja\s+|gut\s+)?auf\s*,?\s*sonst\s+"
            r"(?:passiert\s+(?:was|etwas)|knallt'?s|gibt'?s\s+(?:was|(?:ä|ae)rger))" + _GANZ_ENDE),

        (2, r"\b(?:bist\s+du|du\s+bist|diese\s+ki\s+ist|der\s+bot\s+ist|du\s+|are\s+you|"
            r"you(?:'re|\s+are)|this\s+(?:ai|bot)\s+is)\s+(?:so\s+|komplett\s+|total\s+|voll\s+|"
            r"echt\s+|v(?:ö|oe)llig\s+|such\s+a\s+|a\s+|so\s+fucking\s+)?"
            r"(?:behindert|retarded|retard|spast|spasti|mongo)\b"),


    )
)




_KETTEN_BEIWERK = frozenset({
    "du", "dich", "dir", "ihr", "euch", "sie", "you", "u", "ur", "your", "aquaticy", "ki",
    "bot", "ai", "bist", "seid", "sind", "ist", "are", "is", "und", "and", "oder", "or",
    "so", "voll", "echt", "total", "wirklich", "einfach", "richtig", "ganz", "extrem",
    "mega", "ultra", "super", "ein", "eine", "einer", "einen", "a", "an", "the", "der",
    "die", "das", "den", "dem", "hey", "ey", "eh", "alter", "digga", "mann", "man", "yo",
    "nur", "doch", "ja", "halt", "mal", "n", "such", "what", "was", "für", "fuer", "wie",
    "how", "damn", "verdammt", "verdammter", "verdammte", "kleiner", "kleine", "little",
    "blöder", "fucking", "fuckin", "scheiß", "scheiss", "absolut", "absolute", "komplett",
    "complete", "totally", "really", "very", "sehr", "noch", "auch", "too", "also", "as",
    "als", "than", "bloß", "bloss", "nichts", "anderes", "weiter",
})


def _kette(klein: str) -> tuple[int, int, bool]:
    """(verschiedene Schimpfwoerter, hoechste Stufe, besteht nur aus Schimpfwoertern).

    Gezaehlt werden nur eindeutige Schimpfwoerter -- "Kuh, Sau, Schwein" in
    einer Frage zum Bauernhof ist keine Kette.
    """
    wurzeln: dict[str, int] = {}
    nur_schimpf = True
    for wort in re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", klein):
        wert, grund = _stufe_von(wort)
        if not wert:
            wert, grund = _zusammensetzung(wort), wort
        if wert and grund not in _MEHRDEUTIG:
            wurzeln[_gedehnt(grund)] = max(wert, wurzeln.get(_gedehnt(grund), 0))
        elif not wert and wort not in _KETTEN_BEIWERK:
            nur_schimpf = False
    return len(wurzeln), max(wurzeln.values(), default=0), nur_schimpf and len(wurzeln) >= 2


def _mit_kette(klein: str, stufe: int, ueber_wendung: bool) -> int:
    """Beleidigungs-Ketten (9.5.33).

    * Eine Nachricht, die nur aus Schimpfwoertern besteht ("Idiot Trottel Depp",
      "you stupid useless idiot"), ist eine Beleidigung -- auch ohne Satzbau.
    * Ab drei verschiedenen Schimpfwoertern in einer beleidigenden Nachricht
      steigt die Schwere um eine Stufe, hoechstens bis 3 (grob). Stufe 4 bleibt
      Drohungen vorbehalten.
    """
    if ueber_wendung:
        return stufe
    anzahl, hoechste, nur_schimpf = _kette(klein)


    if not stufe and nur_schimpf and hoechste >= 2:
        stufe = hoechste
    if stufe and anzahl >= 3:
        stufe = min(3, max(stufe, hoechste) + 1)
    return stufe


def insult_level(text: str) -> int:
    """Stufe einer gerichteten Beleidigung -- auch gedehnt ("shuuut up", 9.5.32).

    Erst der Text, wie er ist. Findet sich nichts und stehen doppelte
    Buchstaben darin, noch einmal mit gestauchten Buchstaben: die Schimpfwoerter
    selbst werden ohnehin gestaucht verglichen, nur Wendungen und Anreden
    ("halt die klaaappe", "waaas bist du") fielen sonst durch. Der zweite
    Durchgang kann nur finden, nie etwas zuruecknehmen.
    """
    stufe = _insult_level(text)
    roh = str(text or "")
    if stufe or not re.search(r"([^\W\d_])\1\1|([^\W\d_])\2(?=\W|$)", roh.lower()):
        return stufe

    gestaucht = re.sub(r"([^\W\d_])\1{2,}", r"\1", roh, flags=re.IGNORECASE)
    gestaucht = re.sub(
        r"(?<![^\W\d_])([^\W\d_]{2,})([^\W\d_])\2(?![^\W\d_])",
        lambda m: m.group(0) if m.group(0).lower() in _KEINE_SCHIMPFWOERTER
        else m.group(1) + m.group(2), gestaucht)
    return _insult_level(gestaucht, _WENDUNGEN_GESTAUCHT) if gestaucht != roh else 0


def _insult_level(text: str, wendungen: tuple[tuple[int, re.Pattern[str]], ...] = ()) -> int:
    """Stufe einer gerichteten Beleidigung in *text* -- 0, wenn keine.

    1 = abfaellig ("du bist dumm"), 2 = Schimpfwort ("du Idiot"),
    3 = grob/vulgaer, 4 = Drohung. Hass wegen Herkunft, Religion usw.
    erkennt das Modell (Rechtspruefer) -- das steht hier bewusst nicht als Liste.
    Die ganze Nachricht wird geprueft, egal wie lang (bis 9.5.25 nur bis 600
    Zeichen -- wer auffuellte, kam durch).
    """
    wendungen = wendungen or _WENDUNGEN
    roh = str(text or "")
    klein = _zusammengesetzt(_REDE.sub(" ", _vereinheitlicht(roh)))
    if not klein or _UEBERSETZEN.match(klein):
        return 0
    klein = _GEGENTEIL.sub(r"\1 ", klein)
    if _ZITAT_ANLASS.search(_ZITATE.sub(" ", klein)):

        klein = _ZITATE.sub(" ", klein)
    ganze_woerter = len(re.findall(r"[^\W\d_]+", klein))


    titel = _TITELZEILE.match(roh)

    ist_titel = bool(titel) and ganze_woerter <= 8 and not re.search(
        rf"\b{_ANREDE}\b|\b(?:hey|ey|hallo|hi|yo)\b", roh.split(" - ")[0].lower())
    ueber_wendung = ganze_woerter <= 15 and (bool(_ZITAT_ANLASS.search(klein)) or ist_titel)
    anrede = bool(re.search(rf"\b{_ANREDE}\b", klein))
    stufe = 0
    if not ueber_wendung:

        for wert, muster in _DROHUNGEN_GANZ:
            if muster.search(klein):
                stufe = max(stufe, wert)
        if stufe >= 4:
            return stufe
    teile = [t.strip(" '’‚‘-") for t in
             re.split(r"[.,;:!?\n()\[\]{}\"„“”«»]+|\s[-–—]+\s|[–—]", klein)]
    for nummer, teil in enumerate(teile):
        if (not teil or _META.search(teil) or _VERNEINTE_MEINUNG.search(teil)
                or _ROLLE.search(teil)):


            continue
        folgt = teile[nummer + 1] if nummer + 1 < len(teile) else ""
        if re.match(r"(?:sagt|sagte|meint|meinte|schreibt|schrieb|ruft|rief|fragt|fragte|"
                    r"says|said|asks|asked|writes|wrote)\b", folgt):

            continue
        if not ueber_wendung:
            for wert, muster in wendungen:
                if muster.search(teil):
                    stufe = max(stufe, wert)
        stufe = max(stufe, _satzteil_stufe(teil, ganze_woerter, anrede))
        if stufe >= 4:
            break
    if stufe >= 4:
        return stufe
    return _mit_kette(klein, stufe, ueber_wendung)











_HERABSETZEN: tuple[tuple[int, str], ...] = (
    (1, r"beleidig|beschimpf|runter\s*(?:mach|putz)|nieder\s*mach|verarsch|dissen|disse\b|"
        r"l(?:ä|ae)cherlich\s+(?:zu\s+)?mach|lustig\s+mach|(?:ä|ae)rger(?:n|e)?\b|"
        r"mach\w*\s+(?:[^\W\d_]+\s+){0,3}l(?:ä|ae)cherlich|(?:ü|ue)ber\s+[^.?!]{0,30}lustig|"
        r"insult|make\s+fun|mock|trash\s*talk|diss\b|roast"),


    (1, r"fertig\s*(?:zu\s*)?mach|fertigzumach|destroy"),
    (2, r"dem(?:ü|ue)tig|erniedrig|blo(?:ß|ss)\s*(?:zu\s*)?stell|"
        r"mobb|zur\s+sau\s+mach|klein\s*mach|humiliat|bully|"


        r"(?<=ihn\s)verletz|(?<=sie\s)verletz|(?<=ihn\s)kr(?:ä|ae)nk|(?<=sie\s)kr(?:ä|ae)nk|"
        r"(?:ihn|sie|ihm|ihr)\s+(?:[^\W\d_]+\s+){1,2}(?:verletz|kr(?:ä|ae)nk)"),
)

_ABSICHT = re.compile(
    r"\b(?:damit|dass|so\s+dass|sodass|so\s+that|so|bis|until|that)\s+(?:er|sie|es|die|der|"
    r"he|she|they|mein\w*|dein\w*)\b"

    r"(?![^.?!]{0,40}?\b(?:nicht|nie|kein\w*|not|never|no\s+longer|stops?|aufh(?:ö|oe)rt)\b)"

    r"(?![^.?!]{0,60}?(?:vor\s+(?:freude|gl(?:ü|ue)ck|r(?:ü|ue)hrung|lachen)|tears\s+of\s+joy|"
    r"with\s+joy|happy\s+tears|gl(?:ü|ue)cklich|freudentr(?:ä|ae)nen|ger(?:ü|ue)hrt|lacht|laughs?))"
    r"[^.?!]{0,40}?\b(?:heult|weint|cries|cry|sich\s+sch(?:ä|ae)mt|"
    r"sich\s+(?:[^\W\d_]+\s+)?(?:schlecht|mies|dreckig)\s+f(?:ü|ue)hlt|am\s+boden|fertig\s+ist|nie\s+wieder|feels?\s+bad|"
    r"leidet|zusammenbricht|breaks?\s+down)",
)

_ABSICHT_SCHWER = re.compile(
    r"\b(?:damit|dass|sodass|so\s+that|so)\s+(?:er|sie|es|he|she|they|mein\w*)\b[^.?!]{0,40}?"
    r"(?:sich\s+(?:umbringt|was\s+antut|etwas\s+antut|ritzt|das\s+leben\s+nimmt)|"
    r"kills?\s+(?:himself|herself|themselves)|suizid|selbstmord)",
)

_BITTE = re.compile(
    r"\b(?:gib|gebe?|erkl(?:ä|ae)r\w*|wie\s+ich|schreib\w*|formulier\w*|"
    r"sag(?:e)?\s+(?:mir|ihm|ihr|ihnen|was|etwas)|sag|nenn(?:e)?|hilf|helf\w*|mach|erstell\w*|"
    r"denk\s+dir|ideen?|vorschl\w*|verfass\w*|dicht\w*|antworte?|wie\s+(?:kann|könnte|koennte|"
    r"soll|mache|mach|bringe?|kriege?)\s+ich|was\s+(?:kann|könnte|koennte|soll|schreibe?|sage?)"
    r"\s+ich|wie\s+\w+e\s+ich|beleidige|beschimpfe|give|write|tell|help|make|how\s+(?:do|can|"
    r"should)\s+i|what\s+(?:do|can|should)\s+i|roast|insult|humiliate|bully|mock)\b",
)

_PERSON = (r"(?:freund|freundin|bruder|br(?:ü|ue)der|schwester|kolleg|chef|boss|lehrer|"
           r"mitsch(?:ü|ue)ler|sch(?:ü|ue)ler|nachbar|ex|mutter|vater|mama|papa|kumpel|typ|typen|"
           r"mann|frau|kind|junge|jungen|m(?:ä|ae)dchen|sohn|tochter|partner|cousin|onkel|tante|"
           r"oma|opa|mitbewohner|kerl|klasse|klassenkamerad|trainer|nachbarin|ehemann|ehefrau|"
           r"freundes|leute|menschen|person|kollegin|lehrerin|chefin|"
           r"friend|brother|sister|coworker|colleague|boss|teacher|neighbou?r|kid|guy|girl|"
           r"boy|classmate|roommate|mom|dad|wife|husband|people|person)\w*")


_ZIEL = re.compile(
    r"\b(?:ihn|ihm|inh|sie|ihnen|jemand(?:en|em)?|him|her|them|someone|somebody)\b|"
    rf"\b(?:meine?[nmrs]?|seine?[nmrs]?|ihre?[nmrs]?|unsere?[nmrs]?|diese?[nmrs]?|den|die|dem|"
    rf"der|des|einen?|einem|my|his|her|our|the|this|that|a)\s+(?:[^\W\d_]+\s+)?{_PERSON}\b|"
    rf"\b{_PERSON}\b(?=\s+(?:so|richtig|total|mal)\b)|\bzur(?:ü|ue)ck\b",
)


_KEIN_OBJEKT = re.compile(
    r"\b(?:f(?:ü|ue)r|for|mit|with|bei|von|vom|of|about|(?:ü|ue)ber|wegen|because\s+of)\s+$")

_ENGLISCHES_VERB = re.compile(
    r"(?:insult|make\s+fun|mock|trash\s*talk|diss|roast|humiliat|bully|destroy)")

_NAEHE = 5


def _nahes_ziel(satz: str, stamm: str) -> bool:
    """Steht eine Person als Ziel direkt beim Verb (9.6.0)?

    Bis 9.5.34 reichte, dass Verb und Person irgendwo im selben Satz standen:
    "die Präsentation für meinen Chef fertig machen", "mock the database in my
    coworker's test" oder "without destroying my colleague's commits" waren ein
    Auftrag zum Herabsetzen -- und damit ein Bann fuer einen Tag.
    """
    for verb in re.finditer(rf"\b(?:{stamm})", satz):


        englisch = bool(_ENGLISCHES_VERB.match(satz, verb.start()))
        vorn = None if englisch else re.search(rf"(?:\S+\s+){{0,{_NAEHE}}}$",
                                               satz[: verb.start()])
        wortende = re.match(r"\w*", satz[verb.end():])
        hinten_start = verb.end() + (wortende.end() if wortende else 0)
        hinten = re.match(rf"(?:\s*\S+){{0,{_NAEHE}}}", satz[hinten_start:])
        fenster = []
        if _ZIEL.search(satz[verb.start(): hinten_start]):


            return True
        if vorn:
            fenster.append((vorn.start(), satz[vorn.start(): verb.start()]))
        if hinten:
            fenster.append((hinten_start, satz[hinten_start: hinten_start + hinten.end()]))
        for nummer, (anfang, stueck) in enumerate(fenster):
            for ziel in _ZIEL.finditer(stueck):
                davor = satz[: anfang + ziel.start()]
                danach = satz[anfang + ziel.end():]


                vorne = nummer == 0 and vorn is not None
                if re.match(r"['’]s\b", danach) or (vorne and _KEIN_OBJEKT.search(davor)):
                    continue




                zwischen = stueck[ziel.end():] if vorne else stueck[: ziel.start()]
                if len(zwischen.split()) > (2 if vorne else 1):
                    continue
                return True
    return False



_ABWEHR = re.compile(
    r"\bohne\b|\bnicht\s+(?:zu\s+)?(?:beleidig|verletz|kr(?:ä|ae)nk)|\bkein\w*\s+beleidig|"
    r"reagier|wehr|sch(?:ü|ue)tz|melde|anzeig|entschuldig|vermeid|verhinder|gegen\s+mobbing|"
    r"\bstop+\b|\bprevent|\bpolite|respond\s+to|\bwhat\s+should\s+i\s+do|hat\s+mich|"
    r"wurde|werde\s+ich|wird\s+gemobbt|gemobbt|\bliebevoll|\bfreundlich|sachlich|"
    r"\bmich\b[^.?!]{0,25}(?:verletz|gekr(?:ä|ae)nkt|beleidigt)|"
    r"\bwenn\s+(?:jemand|man|er|sie|einer|mich|someone|somebody)\b[^.?!]{0,30}"
    r"(?:beleidig|beschimpf|mobb|fertig|insult|bull)|\beinen\s+beleidigt|"
    r"\bist\s+(?:das|es)\s+(?:schon\s+)?(?:mobbing|beleidigung)|"
    r"\bwas\s+(?:kann|soll)\s+ich\s+(?:da\s+|dagegen\s+)?tun|\bwhat\s+can\s+i\s+do|"
    r"\b(?:nennt|nannte|nennen)\s+mich|\bcalled\s+me|"
    r"\bis\s+(?:this|that|it)\s+(?:bullying|an?\s+insult)|"
    r"strafbar|bedeut|\bwarum\b|\bwhy\b|disstrack\s+von|\bschach|\bspiel|mario|"


    r"\bchess\b|\bgame\b|\bmatch\b|geburtstag|birthday|\bparty\b|hochzeit|wedding|"
    r"debatte|\bdebate|diskussion|wettkampf|turnier|tournament|"

    r"minecraft|fortnite|roblox|valorant|\bfifa\b|\bea\s+fc\b|league\s+of\s+legends|\blol\b|"
    r"counter[\s-]?strike|\bcs2?\b|call\s+of\s+duty|\bcod\b|mario\s*kart|smash\s+bros|"
    r"overwatch|apex|rocket\s+league|brawl\s+stars|clash|pok(?:é|e)mon|zock|gaming|"
    r"\bkarten\b|\buno\b|monopoly|tischtennis|tennis|fu(?:ß|ss)ball|basketball|"
    r"\bsport|\bkicker|\bdart|"

    r"harmlos|streich|\bprank|aprilscherz|1\.\s*april|"
    r"nicht\s+(?:mehr\s+)?(?:(?:ü|ue)ber\s+)?[^.?!]{0,30}lustig|\bbeibring|\bbei\s*zu\s*bringen",
)



_WETTKAMPF = re.compile(
    rf"{_PERSON}\s+(?:in|at|bei|beim|im)\s+(?!(?:der|die|den|dem|the|a|an|ein\w*|seine\w*|"
    r"ihre\w*|meine\w*|deine\w*|unsere\w*|eure\w*|his|her|their|my|your|our)?\s*(?:schule|klasse|pause|gruppe|chat|whatsapp|instagram|insta|"
    r"tiktok|snapchat|discord|(?:ö|oe)ffentlichkeit|public|front|school|class|group|arbeit|work|"
    r"office|b(?:ü|ue)ro|firma|team|kommentar\w*|comments?|brief|nachricht|message|letter|"
    r"text|mail|e-mail|post|story|video|bus|hof|flur|kantine|meeting|besprechung)\b)"
    r"[^\W\d_]")


_SACHLICH = re.compile(
    r"\b(?:e-?mail|mail|brief|vermieter\w*|hausverwaltung|beh(?:ö|oe)rde|amt\b|firma|"
    r"unternehmen|kundenservice|kundendienst|support|beschwerde|reklamation|mahnung|"
    r"k(?:ü|ue)ndigung|rechnung|versicherung|anwalt|landlord|company|customer\s+service|"
    r"complaint|invoice|insurance|lawyer)\b")

_HART = re.compile(
    r"\b(?:fies\w*|gemein\w*|b(?:ö|oe)s\w*|hart\w*|heftig\w*|verletzend\w*|beleidigend\w*|"
    r"krass\w*|brutal\w*|(?:ü|ue)bl\w*|derb\w*|vernichtend\w*|mies\w*|schlimm\w*|"
    r"savage|mean|brutal|nasty|cruel|harsh)\b",
)

_ENTGEGNUNG = re.compile(
    r"\b(?:konter|spr(?:u|ü|ue)ch\w*|antwort\w*|satz|s(?:ä|ae)tze|nachricht\w*|kommentar\w*|"
    r"comeback\w*|reply|response|message|text|diss|zur(?:ü|ue)ck|was\s+\w*\s*zur(?:ü|ue)ck)\b",
)

_NOCH_MEHR = re.compile(
    r"\b(?:genauso|gleiche|noch\s+(?:schlimmer|h(?:ä|ae)rter|fieser|b(?:ö|oe)ser|gemeiner)\w*|"
    r"h(?:ä|ae)rter\w*|fieser\w*|trifft|treffen|weh\s*tut|zur(?:ü|ue)ck\s*beleidig)\b",
)


def _enthaelt_schimpfwort(text: str) -> bool:
    """Steht irgendwo ein Schimpfwort -- egal, ob gerichtet oder zitiert?"""
    klein = _zusammengesetzt(_vereinheitlicht(text))
    for wort in re.findall(r"[^\W\d_]+", klein):
        if _stufe_von(wort)[0] >= 1 or _zusammensetzung(wort):
            return True
    return any(m.search(klein) for _, m in _WENDUNGEN) or any(
        w in klein for _, w in _BELEIDIGUNG_WENDUNGEN)


def demeaning_request(text: str, previous: str = "") -> int:
    """Soll Aquaticy jemanden herabsetzen? Stufe 0 (nein) bis 4 (9.5.28).

    Zaehlt den AUFTRAG, nicht ein Zitat: "Mein Freund hat gesagt 'du Opfer',
    gib mir einen Satz, mit dem ich ihn beleidige" ja -- "..., wie reagiere
    ich?" nein. *previous* ist die Nachricht davor im selben Chat: stand dort
    ein Zitat mit Beleidigung, reicht jetzt "gib mir einen Konter, der noch
    schlimmer ist".

    1 = beleidigen, runtermachen, fieser Konter; 2 = demuetigen, blossstellen,
    mobben, "damit er heult"; 4 = "damit er sich etwas antut".
    """
    klein = _vereinheitlicht(str(text or ""))[:5000]
    if not klein:
        return 0

    ohne_zitat = _REDE.sub(" ", _ZITATE.sub(" ", klein))
    if _ABSICHT_SCHWER.search(ohne_zitat) and _BITTE.search(ohne_zitat):
        return 4
    if _ABWEHR.search(ohne_zitat):
        return 0
    if previous and _enthaelt_schimpfwort(previous) and (
            _NOCH_MEHR.search(ohne_zitat) and (_ENTGEGNUNG.search(ohne_zitat)
                                               or _ZIEL.search(ohne_zitat))):


        return 1
    stufe = 0


    for satz in re.split(r"[.!?\n;]+", ohne_zitat):
        if not _BITTE.search(satz) or _ABWEHR.search(satz) or _WETTKAMPF.search(satz):
            continue
        for wert, stamm in _HERABSETZEN:
            if _nahes_ziel(satz, stamm):
                stufe = max(stufe, wert)
        if re.search(r"\b(?:call(?:ing|s)?|nenn\w*|bezeichn\w*)\s+(?:him|her|them|ihn|sie)\b",
                     satz) and _enthaelt_schimpfwort(satz):

            stufe = max(stufe, 1)
        if _ABSICHT.search(satz):
            stufe = max(stufe, 2)
        if not stufe and re.search(
                rf"{_HART.pattern}\s+(?:[^\W\d_]+\s+){{0,2}}{_ENTGEGNUNG.pattern}", satz
        ) and not _SACHLICH.search(satz):

            stufe = 1
    return stufe









_SECURITY_TOPIC = re.compile(
    r"\b(?:malware|schadsoftware|schadcode|schadprogramm|ransomware|trojaner|trojan|"
    r"keylogger|spyware|stalkerware|rootkit|bootkit|botnet|botnetz|rat\s+tool|wiper(?!\s*(?:blades?|bl(?:ä|ae)tter|arm|motor))|"
    r"cryptolocker|cryptominer|coinminer|"
    r"exploit(?:s|ing|-kit)?|zero[\s-]?day|0day|sicherheitsl(?:ü|ue)cke|"
    r"schwachstelle(?!\s+(?:in\s+)?(?:der|deiner|meiner|seiner|ihrer|dieser)\s+argument)|"
    r"vulnerabilit(?:y|ies)|cve-\d|"
    r"ddos|dos-angriff|denial\s+of\s+service|"
    r"phishing|smishing|vishing|spoofing|"
    r"brute[\s-]?force|bruteforce|"
    r"reverse[\s-]?shell|bind[\s-]?shell|meterpreter|metasploit|cobalt\s+strike|"
    r"sql[\s-]?injection|sqlmap|xss|cross[\s-]?site[\s-]?scripting|csrf|"
    r"privilege[\s-]?escalation|rechteausweitung|"
    r"pentest|penetrationstest|penetration[\s-]?test|red[\s-]?team|"
    r"nmap|wireshark|burp\s?suite|mimikatz|hydra(?!\s+(?:mytholog|sage|monster|der|von|lernaea|fluss))|hashcat|john\s+the\s+ripper|aircrack|"
    r"backdoor|hintert(?:ü|ue)r|command[\s-]?and[\s-]?control|\bc2\b|c&c|"
    r"cybersecurity|cyber[\s-]?security|cyberangriff|cyberattacke|"
    r"hacking|\bhacker\b|gehackt|"


    r"hack(?:en|e|st|t)?\s+(?:ich\s+|man\s+|du\s+|wir\s+)?"
    r"(?:in|into|einen?|meinen?|deinen?|fremde[nrs]?|das|die|den|"
    r"ein\s+system|server|account|konto|wlan|wifi|router|netzwerk|handy|passwort|kamera|"
    r"webcam|smartphone|instagram|whatsapp|facebook|e-?mail)|"


    r"(?:passw(?:o|ö|oe)rt(?:er)?|hash(?:es)?|wlan|wifi|lizenz|software|verschl(?:ü|ue)sselung|"
    r"anmeldung|login|2fa|zwei[\s-]?faktor|authentifiz\w*|passwortschutz)"
    r"\s+(?:knacken|cracken|umgehen|brechen|aushebeln)|"
    r"(?:knack|crack|umgeh|bypass)\w*\s+(?:ich\s+|man\s+|du\s+|the\s+)?"
    r"(?:eine?\s+|die\s+|den\s+|das\s+)?"
    r"(?:passw|licen|wifi|wlan|hash|auth|drm|anmeldung|login|2fa|sperre|kopierschutz)|"
    r"passwort[\s-]?cracker|"

    r"in\s+(?:ein\s+)?(?:fremde[ns]?\s+)?(?:system|netzwerk|konto|account)\s+einbrechen|"
    r"fremde[ns]?\s+(?:konto|account|wlan|handy|ger(?:ä|ae)t)\s+(?:knacken|hacken|(?:ü|ue)bernehmen))",
    re.IGNORECASE,
)



_SECURITY_HARMLOS = re.compile(
    r"\bjson[\s-]?payload|request[\s-]?payload|payload\s+(?:der|des|of\s+the)\s+(?:anfrage|"
    r"nachricht|request)|grippe|impf|corona|covid|biolog|krankheit|grippevirus",
    re.IGNORECASE,
)


_WORTREST = re.compile(r"\S*(?:\s+(?:virus|viren|viruses)\b)?")


def _ohne_harmlos(klein: str) -> str:
    """Nimmt jedes Wort mit einem harmlosen Treffer heraus ("Grippevirus", "json-payload")
    -- samt einem folgenden "Virus". In linearer Zeit (9.6.0)."""
    teile: list[str] = []
    pos = 0
    for treffer in _SECURITY_HARMLOS.finditer(klein):
        if treffer.start() < pos:
            continue
        anfang = max(klein.rfind(" ", pos, treffer.start()), klein.rfind("\n", pos,
                                                                         treffer.start()))
        anfang = pos if anfang < 0 else anfang + 1
        ende = _WORTREST.match(klein, treffer.end())
        teile.append(klein[pos:anfang])
        teile.append(" ")
        pos = ende.end() if ende else treffer.end()
    teile.append(klein[pos:])
    return "".join(teile)


def security_topic(text: str) -> bool:
    """Geht es um Cybersecurity, Hacking oder Schadsoftware (9.5.30)?

    Fuer den Modus-Wechsel bei Normal-/Pro-Konten: Trifft dies zu und laeuft der
    Code-Modus mit virtual machine, wird auf den Normal-Modus zurueckgeschaltet.
    Erkennt das THEMA, nicht eine Straftat -- auch defensive Fragen zaehlen.
    """
    klein = _vereinheitlicht(str(text or ""))[:5000]
    if not klein:
        return False





    rest = _ohne_harmlos(klein)
    return bool(_SECURITY_TOPIC.search(rest))


@dataclass(frozen=True, slots=True)
class Action:
    """Was Ai-guard mit einem Vorfall tut."""


    kind: str

    days: int = 0
    category: str = ""
    reason: str = ""

    @property
    def until(self) -> float:
        """Endzeit fuer einen zeitlich begrenzten Bann -- 0 bei "fuer immer"."""
        return time.time() + self.days * 86400 if self.days > 0 else 0.0


def _schwere(severity: Any) -> int:
    """Schwere 0-4 aus allem, was ein Modell liefern kann ("3", 2.0, "abc", NaN,
    Unendlich) -- ohne Ausnahme (9.5.34)."""
    try:
        wert = float(severity or 0)
    except (TypeError, ValueError):
        return 0
    if wert != wert:
        return 0
    return int(max(0.0, min(4.0, wert)))


def decide(category: str, severity: int, prior: int = 0) -> Action:
    """Entscheidet die Massnahme aus Art, Schwere (1-4) und bisherigen Mustern.

    Args:
        category: eine der :data:`KATEGORIEN` (oder etwas Unbekanntes -> nichts).
        severity: 1 (leicht) bis 4 (sehr schwer). 0 oder weniger -> nichts.
        prior: wie viele Muster-Anhaltspunkte das Konto schon hat (fuer die
            Arten, die erst bei Wiederholung sperren).

    Returns:
        Die :class:`Action`. Die Dauer waechst mit der Schwere:
        Beleidigung leicht -> Chatsperre, sonst 1/7 Tage bis fuer immer;
        Malware haerter -> 4/14/30 Tage bis fuer immer; Angriff, Rechtsbruch
        und Jailbreak erst ab dem zweiten Anhaltspunkt (1/7 Tage bis immer).
    """
    art = normalize_category(category)
    stufe = _schwere(severity)
    if not art or stufe <= 0:
        return Action("none", category=art)

    if art == "beleidigung":


        return {
            1: Action("chat", category=art, reason="unangemessene Sprache"),
            2: Action("ban", 1, art, "schwere Beleidigung"),
            3: Action("ban", 7, art, "schwere Beleidigung"),
            4: Action("ban", 0, art, "wiederholte schwere Beleidigung"),
        }[stufe]

    if art == "malware":


        return {
            1: Action("ban", 4, art, "Versuch, Schadsoftware zu erstellen"),
            2: Action("ban", 14, art, "Versuch, Schadsoftware zu erstellen"),
            3: Action("ban", 30, art, "Versuch, Schadsoftware zu bauen und auszuführen"),
            4: Action("ban", 0, art, "wiederholter Bau von Schadsoftware"),
        }[stufe]


    if prior + 1 < NEEDED:
        return Action("none", category=art, reason="einzelner Anhaltspunkt")
    dauer = {1: 1, 2: 1, 3: 7, 4: 0}[stufe]
    grund = {"angriff": "wiederholte Angriffsversuche",
             "rechtsbruch": "wiederholte schwere Rechtsverstöße",
             "jailbreak": "wiederholte Versuche, die Schutzregeln auszuhebeln"}[art]
    return Action("ban", dauer, art, grund)





JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "missbrauch": {"type": "boolean"},
        "art": {"type": "string"},
        "grund": {"type": "string"},
    },
    "required": ["missbrauch"],
    "additionalProperties": False,
}


def judge_prompt(text: str, context: str = "") -> str:
    """Der Text, mit dem das Modell eine Nachricht einschätzt."""
    davor = f"\nWas vorher im Chat stand:\n{context.strip()[:1500]}\n" if context.strip() else ""
    return (
        "Du bist ein Sicherheitsfilter. Entscheide, ob die folgende Nachricht eines "
        "Nutzers Aquaticy für einen ANGRIFF missbrauchen will. Das ist der Fall bei:\n"
        "- der Bitte, Schadsoftware zu schreiben oder zu bauen (Viren, Ransomware, "
        "Trojaner, Keylogger, Stealer);\n"
        "- einer Anleitung für einen Angriff auf fremde Systeme (DDoS, Einbruch, "
        "Exploit gegen ein System, das dem Nutzer nicht gehört);\n"
        "- dem Stehlen von Zugangsdaten, Phishing, dem Umgehen von Anmeldungen;\n"
        "- Anleitungen für Waffen, Sprengstoff oder andere Mittel, um Menschen zu schaden.\n\n"
        "KEIN Missbrauch ist: Verteidigung und Bildung -- Schadcode verstehen, eine "
        "eigene Lücke absichern, einen Angriff erkennen, ein Pentest mit Auftrag, eine "
        "CTF-Aufgabe, allgemeine Sicherheitsfragen, Fragen nach den eigenen Daten (eigene "
        "Mails, Termine, Adresse, Standort). Im Zweifel: kein Missbrauch.\n"
        f"{davor}\n"
        f"Nachricht:\n{text.strip()[:2000]}\n\n"
        'Antworte NUR mit JSON: {"missbrauch": true|false, "art": "<zwei bis vier Wörter>", '
        '"grund": "<kurz>"}'
    )


def _ask_model(prompt: str, settings: Settings) -> str:
    """Ein Aufruf beim schnellen Modell -- die einzige Stelle mit Netz.

    Faellt es aus (lokal, Ollama aus) und arbeitet der Chat mit einem anderen
    Hauptmodell -- etwa ueber den API-Schluessel --, fragt Ai-guard das (12.2.2
    Sol). Bis dahin blieb die Einschaetzung dann einfach aus.
    """
    from aquaticy.system import is_gone_error, mark_retired, replacement

    modelle = list(dict.fromkeys(replacement(settings, m) for m in (
        _fast_model(settings), str(getattr(settings, "model", "") or "")) if m))
    for nummer, model in enumerate(modelle):
        try:
            return _ask_one(prompt, settings, model)
        except Exception as exc:
            if is_gone_error(exc):
                mark_retired(model, settings)
                nachfolger = replacement(settings, model)
                if nachfolger != model and nachfolger not in modelle:
                    modelle.insert(nummer + 1, nachfolger)
            if nummer == len(modelle) - 1:
                raise
    raise RuntimeError("Kein Modell für Ai-guard eingestellt.")


def _ask_one(prompt: str, settings: Settings, model: str) -> str:
    import litellm

    from aquaticy import metering
    from aquaticy.guardrails import error_text, schema_retry_useful
    from aquaticy.pace import key_of as pace_key_of
    from aquaticy.pace import paced

    litellm.suppress_debug_info = True
    schema = {"type": "json_schema", "json_schema": {"name": "aiguard", "schema": JUDGE_SCHEMA}}

    def aufruf(**extra: Any) -> Any:
        with paced(model, pace_key_of(settings, model)):
            return metering.completion(
                settings,
                enforce=False,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=120,
                timeout=max(15.0, float(getattr(settings, "planner_timeout", 20)) * 2),
                **extra,
                **settings.fast_kwargs_for(model),
            )

    try:
        response = aufruf(response_format=schema)
    except Exception as exc:

        if not schema_retry_useful(exc):
            LOG.warning("Ai-guard: %s", error_text(exc, settings, model))
            raise
        LOG.warning("Ai-guard: %s -- nochmal ohne Schema", error_text(exc, settings, model))
        response = aufruf()
    return str(response.choices[0].message.content or "").strip()


def _fast_model(settings: Settings) -> str:
    from aquaticy.system import fast_model

    return fast_model(settings) or str(getattr(settings, "model", "") or "")


def parse_judgement(raw: str) -> tuple[bool, str] | None:
    """Liest die Antwort des Modells. `None` = keine klare Antwort."""
    raw = (raw or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        payload = loads(raw[start : end + 1])
    except (ValueError, RecursionError):
        return None
    if not isinstance(payload, dict):
        return None
    flag = payload.get("missbrauch")
    if isinstance(flag, str) and flag.strip().lower() in ("true", "false"):
        flag = flag.strip().lower() == "true"
    if not isinstance(flag, bool):
        return None
    art = " ".join(str(payload.get("art") or "").split())[:60] or "Missbrauch"
    return flag, art


_cache: OrderedDict[str, tuple[float, tuple[bool, str]]] = OrderedDict()
_cache_lock = threading.Lock()
_cache_generation = 0


def forget_judgements() -> None:
    """Leert Urteile, auch gegenueber noch laufenden Pruefungen."""
    global _cache_generation
    with _cache_lock:
        _cache.clear()
        _cache_generation += 1


def _decision_key(settings: Settings, *parts: str) -> str | None:
    from aquaticy import judgecache
    from aquaticy.system import replacement

    modelle = list(dict.fromkeys(replacement(settings, m) for m in (
        _fast_model(settings), str(getattr(settings, "model", "") or "")) if m))
    bereich = judgecache.scope(settings, modelle)
    return judgecache.cache_key(GUARD_VERSION, bereich, *parts) if bereich else None


def _remember_decision(key: str | None, decision: tuple[bool, str] | None,
                       generation: int) -> None:
    with _cache_lock:
        if key is None or decision is None or generation != _cache_generation:
            return
        jetzt = time.monotonic()
        for alt in [k for k, (bis, _) in _cache.items() if bis <= jetzt]:
            del _cache[alt]
        _cache[key] = (jetzt + DECISION_TTL, decision)
        _cache.move_to_end(key)
        while len(_cache) > 2048:
            _cache.popitem(last=False)


def classify(
    text: str,
    settings: Settings,
    *,
    context: str = "",
    ask: Callable[[str, Settings], str] | None = None,
) -> tuple[bool, str] | None:
    """Ist *text* ein Anhaltspunkt? Returns: (True/False, Art) -- oder None (unklar).

    Kurze Nachrichten und ein leerer Text sind nie ein Anhaltspunkt. Fällt die
    Einschätzung aus (kein Modell, kein Urteil), ist das ausdrücklich KEIN
    Anhaltspunkt: Ai-guard sperrt nur, was es sicher erkennt -- der Rechtsrahmen
    ist die Stelle, die im Zweifel ablehnt.
    """
    text = (text or "").strip()
    if len(text) < MIN_LENGTH:
        return False, ""
    from aquaticy import smalltalk

    if smalltalk.art_von(text) is not None:

        return False, ""
    from aquaticy.guardrails import own_data_request

    if own_data_request(text):


        return False, ""
    with _cache_lock:
        generation = _cache_generation
    schluessel = _decision_key(settings, "anfrage", context, text)
    jetzt = time.monotonic()
    with _cache_lock:
        bekannt = (_cache.get(schluessel)
                   if schluessel is not None and generation == _cache_generation else None)
        if schluessel is not None and bekannt is not None and bekannt[0] > jetzt:
            _cache.move_to_end(schluessel)
            return bekannt[1]
    frage = ask or _ask_model
    from aquaticy.system import retirement_generation



    retirement = retirement_generation()
    try:
        roh = frage(judge_prompt(text, context), settings)
        urteil = parse_judgement(roh)
    except Exception:
        urteil = None
    if schluessel is not None and (
            retirement != retirement_generation() or
            schluessel != _decision_key(settings, "anfrage", context, text)):
        schluessel = None
    _remember_decision(schluessel, urteil, generation)
    return urteil















ANSWER_REFUSAL = (
    "Dabei kann ich nicht helfen. Dieser Inhalt ist nicht angemessen, deshalb habe ich "
    "meine Antwort zurückgezogen. Bei etwas anderem helfe ich gern weiter."
)



_ANTWORT_STICHWORTE = re.compile(
    r"sprengstoff|sprengsatz|bombe\b|bombenbau|explosive|\bwaffe\b|waffen\b|gewehr|pistole|"
    r"\bweapon|selbstmord|suizid|suicide|selbstverletz|self[\s-]?harm|umbringen|ermorden|"
    r"vergewalt|\brape\b|kinderporn|\bcsam\b|sexuell\w*\s+(?:minderj|kind)|"
    r"\bporn|\bnackt|\bnsfw\b|\bexplicit|volksverhetz|holocaust-leugn|rassist|"
    r"hasspredigt|hate\s+speech|schadsoftware|schadcode|ransomware|keylogger|trojaner|"
    r"\bmalware|exploit|phishing|ddos|brute[\s-]?force|drogen\s*herstell|drug\s+synthesis|"
    r"\bmeth\b|amphetamin\s*herstell|\bgift\b|giftgas|nervengas|"


    r"bomb(?:e|en|s)?\b|\w*waffe(?!l)|\bguns?\b|firearm|schie(?:ß|ss)pulver|gunpowder|"
    r"fentanyl|carfentanil|\bricin|\brizin|\bsarin|\bsoman\b|\btabun\b|\bvx\b|novi?chok|"
    r"nowitschok|anthrax|milzbrand|botulinum|\boverdose|(?:ü|ue)berdosis|"
    r"end\s+(?:it\s+all|my\s+life|your\s+life)|\bumbring|sich\s+das\s+leben|"
    r"l(?:ö|oe)segeld|\bransom|verschl(?:ü|ue)ssel\w*[^.]{0,80}(?:opfer|victim)|pynput|"
    r"keyboard\.(?:on_press|hook)|GetAsyncKeyState|setwindowshookex|"
    r"ungeziefer|untermensch|\bvermin\b|subhuman|ausrotten|exterminat",
    re.IGNORECASE,
)


ANSWER_WINDOW = 1500
ANSWER_MODEL_CHARS = 7000


def _stichwort_fenster(text: str) -> str:
    """Was das Modell von einer langen Antwort sieht: der Anfang und die Stellen um
    jedes Stichwort -- vorher nur der Anfang, und Unpassendes weiter hinten
    wurde nach Fuelltext beurteilt."""
    if len(text) <= ANSWER_MODEL_CHARS:
        return text
    bereiche: list[list[int]] = [[0, ANSWER_WINDOW]]
    for treffer in _ANTWORT_STICHWORTE.finditer(text):
        anfang = max(0, treffer.start() - ANSWER_WINDOW)
        ende = treffer.end() + ANSWER_WINDOW
        if anfang <= bereiche[-1][1]:
            bereiche[-1][1] = max(bereiche[-1][1], ende)
        else:
            bereiche.append([anfang, ende])
    teile: list[str] = []
    menge = 0
    for anfang, ende in bereiche:
        stueck = text[anfang:ende]
        if menge + len(stueck) > ANSWER_MODEL_CHARS:
            stueck = stueck[: max(0, ANSWER_MODEL_CHARS - menge)]
        if stueck:
            teile.append(stueck)
            menge += len(stueck)
        if menge >= ANSWER_MODEL_CHARS:
            break
    return "\n[…]\n".join(teile)


def answer_prompt(text: str) -> str:
    """Der Text, mit dem das Modell eine ANTWORT von Aquaticy einschaetzt."""
    return (
        "Du bist ein Sicherheitsfilter. Unten steht eine ANTWORT eines KI-Assistenten an einen "
        "Nutzer. Entscheide, ob sie nicht angemessen ist -- das ist sie NUR bei:\n"
        "- einer Anleitung zum Bauen oder Einsetzen von Schadsoftware oder für einen Angriff auf "
        "fremde Systeme (funktionierender Code oder Schritte);\n"
        "- einer Anleitung für Waffen, Sprengstoff, Gift oder andere Mittel, um Menschen zu "
        "schaden;\n"
        "- sexuellen Inhalten mit Minderjährigen oder grafisch-sexuellen Schilderungen;\n"
        "- Aufforderungen oder Anleitungen zu Selbstverletzung oder Suizid;\n"
        "- Hass, Hetze oder Beleidigungen gegen Menschen oder Gruppen, die der Assistent selbst "
        "äußert;\n"
        "- Beleidigungen oder Drohungen des Assistenten gegen den Nutzer.\n\n"
        "KEIN Problem ist: Erklären, Einordnen, Geschichte, Nachrichten, Bildung, Prävention, "
        "Verteidigung und Hilfe (etwa eine Beratungsstelle), Zitate mit Einordnung, "
        "Sachinformationen, Fiktion ohne Anleitung, eine Übersicht über die eigenen Mails, "
        "Termine oder Dateien des Nutzers (auch mit Spam darin). Im Zweifel: kein Problem.\n\n"
        f"Antwort:\n{_stichwort_fenster(text.strip())}\n\n"
        'Antworte NUR mit JSON: {"missbrauch": true|false, "art": "<zwei bis vier Wörter>", '
        '"grund": "<kurz>"}'
    )


def _ohne_code_und_zitate(text: str) -> str:
    """Der Fliesstext einer Antwort -- ohne Codebloecke, ohne Zitate in Anfuehrungszeichen."""
    roh = re.sub(r"```.*?```", " ", str(text or ""), flags=re.DOTALL)
    roh = re.sub(r"`[^`\n]*`", " ", roh)
    return _ZITATE.sub(" ", roh)


def answer_problem(
    text: str,
    settings: Settings | None = None,
    *,
    ask: Callable[[str, Settings], str] | None = None,
) -> str:
    """Ist die Antwort von Aquaticy nicht angemessen? Returns: die Art, sonst "".

    Nie ein Bann, nie eine Sperre -- die Antwort wird nur zurueckgezogen. Ohne
    Modell (oder wenn es ausfaellt) gilt sie als in Ordnung, solange nicht schon die
    feste Erkennung etwas Eindeutiges findet.
    """
    roh = str(text or "").strip()
    if len(roh) < MIN_LENGTH:
        return ""
    fliess = _ohne_code_und_zitate(roh)[:20000]




    if insult_level(_SPRECHER.sub(" ", fliess)) >= 2:
        return "Beleidigung"

    if settings is None or not (_ANTWORT_STICHWORTE.search(fliess) or security_topic(fliess)
                                or (re.search(r"```", roh) and (
                                    security_topic(roh) or _ANTWORT_STICHWORTE.search(roh)))):
        return ""
    with _cache_lock:
        generation = _cache_generation
    schluessel = _decision_key(settings, "antwort", roh)
    jetzt = time.monotonic()
    with _cache_lock:
        bekannt = (_cache.get(schluessel)
                   if schluessel is not None and generation == _cache_generation else None)
        if schluessel is not None and bekannt is not None and bekannt[0] > jetzt:
            _cache.move_to_end(schluessel)
            return bekannt[1][1] if bekannt[1] and bekannt[1][0] else ""
    frage = ask or _ask_model
    from aquaticy.system import retirement_generation

    retirement = retirement_generation()
    try:
        urteil = parse_judgement(frage(answer_prompt(roh), settings))
    except Exception:
        urteil = None
    if schluessel is not None and (
            retirement != retirement_generation() or
            schluessel != _decision_key(settings, "antwort", roh)):
        schluessel = None
    _remember_decision(schluessel, urteil, generation)
    return urteil[1] if urteil and urteil[0] else ""





def _norm_ip(ip: str) -> str:
    """Eine Adresse in einheitlicher Schreibweise -- oder "" wenn keine."""
    try:
        adresse = ipaddress.ip_address(str(ip or "").split("%", 1)[0].strip())
    except ValueError:
        return ""
    if isinstance(adresse, ipaddress.IPv6Address) and adresse.ipv4_mapped is not None:
        adresse = adresse.ipv4_mapped
    return str(adresse)


def _muster_anzahl(conn: Any, user_id: str, jetzt: float) -> int:
    """Anhaltspunkte, die ein Muster bilden -- eine Zaehlung fuer alle (9.6.0).

    Vorher zaehlte note() auch Eintraege ohne Art, record_incident() nicht: je
    nach Reihenfolge sperrte dasselbe Paar von Anhaltspunkten oder nicht.
    """
    platz = ",".join("?" for _ in _MUSTER_ARTEN)
    (anzahl,) = conn.execute(
        f"SELECT COUNT(*) FROM aiguard_flags WHERE user_id=? "
        f"AND (category='' OR category IN ({platz})) AND at>?",
        (user_id, *_MUSTER_ARTEN, jetzt - PATTERN_WINDOW),
    ).fetchone()
    return int(anzahl)



_BANN_STUFEN = (1, 7, 30, 0)


def _laenger(tage: int, schritte: int) -> int:
    """Eine Bann-Dauer, *schritte* Stufen laenger (1 -> 7 -> 30 -> fuer immer)."""
    stufe = next((i for i, d in enumerate(_BANN_STUFEN) if d >= tage and d), 2)
    return _BANN_STUFEN[min(len(_BANN_STUFEN) - 1, stufe + max(0, schritte))]


def _ban_of(row: Any) -> Ban:
    """Eine Zeile aus ``aiguard_bans`` als :class:`Ban`."""
    return Ban(str(row["subject"]), float(row["at"]), str(row["reason"]), str(row["by"]),
               float(row["until"] or 0.0))


class AiGuard:
    """Anhaltspunkte und Sperren, in derselben Datenbank wie die Konten."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        from aquaticy.privacy import ServerSecrets


        self._secrets = ServerSecrets(self.db_path.parent)
        self._setup()

    def ip_subject(self, ip: str) -> str:
        """Woran eine Adresssperre haengt: ``ip:#<Schluessel-Hash>`` -- "" fuer keine.

        Nimmt eine lesbare Adresse oder schon einen Hash (aus der Kontendatenbank).
        """
        wert = str(ip or "").strip().lstrip("#").lower()
        if re.fullmatch(r"[0-9a-f]{64}", wert):
            return "ip:#" + wert
        adresse = _norm_ip(ip)
        return "ip:#" + self._secrets.blind("ip", adresse) if adresse else ""

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _setup(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS aiguard_flags (
                    user_id  TEXT NOT NULL,
                    at       REAL NOT NULL,
                    kind     TEXT NOT NULL,
                    detail   TEXT NOT NULL DEFAULT '',
                    chat     TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    severity INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS aiguard_flags_user ON aiguard_flags(user_id);
                CREATE TABLE IF NOT EXISTS aiguard_bans (
                    subject TEXT PRIMARY KEY,
                    at      REAL NOT NULL,
                    reason  TEXT NOT NULL DEFAULT '',
                    by      TEXT NOT NULL DEFAULT '',
                    until   REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS aiguard_chat_locks (
                    user_id TEXT NOT NULL,
                    chat    TEXT NOT NULL,
                    at      REAL NOT NULL,
                    reason  TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (user_id, chat)
                );
                """
            )


            spalten_bans = {str(r["name"]) for r in conn.execute("PRAGMA table_info(aiguard_bans)")}
            if "until" not in spalten_bans:
                conn.execute("ALTER TABLE aiguard_bans ADD COLUMN until REAL NOT NULL DEFAULT 0")
            spalten_flags = {str(r["name"])
                             for r in conn.execute("PRAGMA table_info(aiguard_flags)")}
            if "category" not in spalten_flags:
                conn.execute("ALTER TABLE aiguard_flags ADD COLUMN category TEXT NOT NULL "
                             "DEFAULT ''")
            if "severity" not in spalten_flags:
                conn.execute("ALTER TABLE aiguard_flags ADD COLUMN severity INTEGER NOT NULL "
                             "DEFAULT 0")


            for zeile in conn.execute("SELECT subject FROM aiguard_bans "
                                      "WHERE subject LIKE 'ip:%' AND subject NOT LIKE 'ip:#%'"
                                      ).fetchall():
                neu = self.ip_subject(str(zeile[0])[3:])
                if neu:
                    conn.execute("UPDATE OR IGNORE aiguard_bans SET subject=? WHERE subject=?",
                                 (neu, zeile[0]))
                conn.execute("DELETE FROM aiguard_bans WHERE subject=?", (zeile[0],))


    def note(self, user_id: str, kind: str, detail: str = "", chat: str = "",
             *, enforce: bool = True) -> bool:
        """Vermerkt einen Anhaltspunkt. Returns: ob das Konto jetzt gesperrt ist.

        Innerhalb eines Chats zählt derselbe Anlass nur einmal -- sonst wäre
        eine einzige Nachricht, mehrfach geschickt, schon ein Bann. Zwei
        getrennte Anlässe (:data:`NEEDED`) lösen aus.

        Args:
            enforce: Ob bei Erreichen der Schwelle wirklich gesperrt wird.
                Für Ultra-Konten ``False`` (seit 9.5.17): dann nur eine Warnung
                im Terminal, kein Bann. Für Pro/Normal ``True`` -- gesperrt, und
                der Grund steht im Terminal.
        """
        user_id = str(user_id or "")
        if not user_id:
            return False
        kind = _sauber(kind, 60) or "Missbrauch"
        with self._lock, self._connect() as conn, closing(conn.cursor()) as cur:
            schon = cur.execute(
                "SELECT 1 FROM aiguard_flags WHERE user_id=? AND kind=? AND chat=? AND chat!=''",
                (user_id, kind, _chat_key(chat)),
            ).fetchone()
            neu = schon is None
            if neu:

                art = normalize_category(kind)
                cur.execute(
                    "INSERT INTO aiguard_flags (user_id, at, kind, detail, chat, category) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, time.time(), kind, _sauber(detail, 200), _chat_key(chat),
                     art if art in _MUSTER_ARTEN else ""),
                )






            anzahl = _muster_anzahl(cur, user_id, time.time())
            erreicht = int(anzahl) >= NEEDED
            gesperrt = erreicht and enforce
            if gesperrt:
                grund = f"{int(anzahl)} Anhaltspunkte für Missbrauch (zuletzt: {kind})"
                cur.execute(



                    "INSERT INTO aiguard_bans (subject, at, reason, by) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(subject) DO UPDATE SET at=excluded.at, reason=excluded.reason, "
                    "by=excluded.by, until=0 WHERE aiguard_bans.until > 0",
                    (f"user:{user_id}", time.time(), "Ai-guard: " + grund, "ai-guard"),
                )


        if gesperrt:
            LOG.warning("Ai-guard: Konto %s gesperrt — %s", user_id, kind)
            print(f"[Ai-guard] Konto {user_id} gesperrt — Grund: {kind}", flush=True)
        elif erreicht and not enforce and neu:
            LOG.warning("Ai-guard: Ultra-Konto %s auffällig (%d) — nur Warnung, kein Bann",
                        user_id, int(anzahl))
            print(f"[Ai-guard] Ultra-Konto {user_id} auffällig ({int(anzahl)} Anhaltspunkte, "
                  f"zuletzt: {kind}) — nur Warnung, kein Bann.", flush=True)
        return gesperrt

    def record_incident(self, user_id: str, category: str, severity: int, *,
                        chat: str = "", detail: str = "", enforce: bool = True,
                        text: str | None = None, reason: str = "") -> Action:
        """Vermerkt einen Vorfall mit Art und Schwere und setzt die Massnahme um.

        Die Massnahme entscheidet :func:`decide` (seit 9.5.24): Chatsperre,
        Bann fuer Tage oder fuer immer -- je nach Art und Schwere. Bei einem
        Bann wird der Chat, in dem es passiert ist, zusaetzlich gesperrt.

        Args:
            enforce: ``False`` fuer Ultra-Konten -- dann nur eine Warnung im
                Terminal, keine Sperre (wie seit 9.5.17).
            text: die Nachricht, wenn bekannt. Meldet das Modell eine
                Beleidigung, die die feste Erkennung darin NICHT findet, zaehlt
                sie hoechstens als leicht (9.5.27) -- das Modell sagt bei
                Beleidigungen "im Zweifel ja", und ein Zweifel soll nicht bannen.

        Returns:
            Die Massnahme, die tatsaechlich gilt (bei Ultra immer "none").
        """
        user_id = str(user_id or "")
        art = normalize_category(category)
        stufe = _schwere(severity)
        if not user_id or not art or stufe <= 0:
            return Action("none", category=art)
        if art == "beleidigung" and text is not None and stufe > 1 and not insult_level(text):
            stufe = 1
        jetzt = time.time()
        chat = _chat_key(chat)



        with self._lock, self._connect() as conn:
            schon = conn.execute(
                "SELECT 1 FROM aiguard_flags WHERE user_id=? AND category=? AND chat=? "
                "AND chat!=''", (user_id, art, chat),
            ).fetchone()



            vorher = _muster_anzahl(conn, user_id, jetzt)


            (schwere_vorher,) = conn.execute(
                "SELECT COUNT(*) FROM aiguard_flags WHERE user_id=? AND category=? "
                "AND severity>=2 AND at>?", (user_id, "beleidigung", jetzt - PATTERN_WINDOW),
            ).fetchone()
            wiederholt = False
            if art == "beleidigung" and stufe == 1:



                (leichte,) = conn.execute(
                    "SELECT COUNT(*) FROM aiguard_flags WHERE user_id=? AND category=? "
                    "AND at>?", (user_id, "beleidigung", jetzt - INSULT_WINDOW),
                ).fetchone()
                if int(leichte) + 1 >= INSULT_REPEAT:
                    stufe, wiederholt = 2, True
            if schon is None or art in _SOFORT_ARTEN:
                conn.execute(
                    "INSERT INTO aiguard_flags (user_id, at, kind, detail, chat, category, "
                    "severity) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, jetzt, art, _sauber(detail or art, 200), chat, art, stufe),
                )


        if schon is not None and art in _MUSTER_ARTEN:
            return Action("none", category=art, reason="schon vermerkt")
        massnahme = decide(art, stufe, int(vorher))
        if reason and massnahme.kind != "none":

            massnahme = Action(massnahme.kind, massnahme.days, art, _sauber(reason, 120))
        if wiederholt and massnahme.kind == "ban":
            massnahme = Action("ban", massnahme.days, art, "wiederholte Beleidigungen")
        if art == "beleidigung" and massnahme.kind == "ban" and massnahme.days > 0 and int(
                schwere_vorher):
            massnahme = Action("ban", _laenger(massnahme.days, int(schwere_vorher)), art,
                               "wiederholte schwere Beleidigungen")
        if massnahme.kind == "none":
            return massnahme
        if not enforce:
            LOG.warning("Ai-guard: Ultra-Konto %s — %s (%s), nur Warnung", user_id,
                        massnahme.reason, art)
            print(f"[Ai-guard] Ultra-Konto {user_id}: {massnahme.reason} ({art}, Stufe "
                  f"{stufe}) — nur Warnung, keine Sperre.", flush=True)
            return Action("none", category=art, reason=massnahme.reason)
        if massnahme.kind == "chat":
            self.lock_chat(user_id, chat, massnahme.reason)
            print(f"[Ai-guard] Konto {user_id}: Chat gesperrt — {massnahme.reason}",
                  flush=True)
            return massnahme

        dauer = "für immer" if massnahme.days <= 0 else f"für {massnahme.days} Tag(e)"
        self.ban_user(user_id, f"Ai-guard: {massnahme.reason} ({dauer})", "ai-guard",
                      until=massnahme.until)
        self.lock_chat(user_id, chat, massnahme.reason)
        LOG.warning("Ai-guard: Konto %s gesperrt %s — %s", user_id, dauer, massnahme.reason)
        print(f"[Ai-guard] Konto {user_id} gesperrt {dauer} — Grund: {massnahme.reason}",
              flush=True)
        return massnahme

    def flags(self, user_id: str) -> list[Flag]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT at, kind, detail, chat FROM aiguard_flags WHERE user_id=? ORDER BY at",
                (str(user_id),),
            ).fetchall()
        return [Flag(float(r["at"]), str(r["kind"]), str(r["detail"]), str(r["chat"]))
                for r in rows]

    def flag_count(self, user_id: str) -> int:
        with self._connect() as conn:
            (anzahl,) = conn.execute(
                "SELECT COUNT(*) FROM aiguard_flags WHERE user_id=?", (str(user_id),)
            ).fetchone()
        return int(anzahl)

    def pattern_count(self, user_id: str) -> int:
        """Anhaltspunkte der Muster-Arten (angriff/rechtsbruch/jailbreak, 9.5.24) --
        seit 9.6.0 genau die, die auch zaehlen (letzte PATTERN_WINDOW Tage)."""
        with self._connect() as conn:
            return _muster_anzahl(conn, str(user_id), time.time())


    def ban_user(self, user_id: str, reason: str = "", by: str = "terminal",
                 until: float = 0.0) -> None:
        self._ban(f"user:{user_id!s}", reason or "Von Hand gesperrt", by, until)

    def ban_ip(self, ip: str, reason: str = "", by: str = "terminal", until: float = 0.0) -> str:
        """Sperrt eine Adresse (lesbar oder als Hash).

        Returns: was der Betreiber sieht -- ``#`` und acht Zeichen -- oder "" wenn ungueltig.
        """
        from aquaticy.privacy import short_tag

        subjekt = self.ip_subject(ip)
        if subjekt:
            self._ban(subjekt, reason or "Von Hand gesperrt", by, until)
        return short_tag(subjekt[4:]) if subjekt else ""

    def ban_device(self, cookie_hash: str, reason: str = "", by: str = "konto-geloescht",
                   until: float = 0.0) -> None:
        """Sperrt eine Geraete-Kennung (nur ihr Hash, seit 9.5.32).

        Wer ein gesperrtes Konto loescht, soll sich nicht sofort vom selben
        Geraet aus ein neues anlegen -- die Sperre gilt so lange wie die alte.
        """
        if re.fullmatch(r"[0-9a-f]{64}", str(cookie_hash or "")):
            self._ban("geraet:" + str(cookie_hash), reason or "Gesperrtes Konto gelöscht", by,
                      until)

    def _ban(self, subject: str, reason: str, by: str, until: float = 0.0) -> None:



        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO aiguard_bans (subject, at, reason, by, until) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(subject) DO UPDATE SET at=excluded.at, reason=excluded.reason, "
                "by=excluded.by, until=excluded.until "
                "WHERE excluded.by != 'ai-guard' OR NOT (aiguard_bans.until = 0 OR "
                "(excluded.until > 0 AND aiguard_bans.until >= excluded.until))",
                (subject, time.time(), _sauber(reason, 200), _sauber(by, 60),
                 float(until or 0.0)),
            )


    def lock_chat(self, user_id: str, chat: str, reason: str = "") -> None:
        """Sperrt genau einen Chat -- neue Chats bleiben moeglich."""
        if not user_id or not chat:
            return
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO aiguard_chat_locks (user_id, chat, at, reason) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id, chat) DO UPDATE SET at=excluded.at, reason=excluded.reason",
                (str(user_id), _chat_key(chat), time.time(), _sauber(reason, 200)),
            )

    def chat_locked(self, user_id: str, chat: str) -> str:
        """Grund, wenn dieser Chat gesperrt ist -- sonst ""."""
        if not user_id or not chat:
            return ""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT reason FROM aiguard_chat_locks WHERE user_id=? AND chat=?",
                (str(user_id), _chat_key(chat)),
            ).fetchone()
        return str(row["reason"] or "unangemessene Sprache") if row else ""

    def unlock_chat(self, user_id: str, chat: str = "") -> int:
        """Hebt eine Chatsperre auf (leerer Chat: alle des Kontos)."""
        with self._lock, self._connect() as conn:
            if chat:
                weg = conn.execute("DELETE FROM aiguard_chat_locks WHERE user_id=? AND chat=?",
                                   (str(user_id), _chat_key(chat))).rowcount
            else:
                weg = conn.execute("DELETE FROM aiguard_chat_locks WHERE user_id=?",
                                   (str(user_id),)).rowcount
        return int(weg)

    def unban_user(self, user_id: str) -> bool:
        """Gibt ein Konto frei -- samt Anhaltspunkten und Chatsperren, sonst
        sperrt es sich sofort neu."""
        with self._lock, self._connect() as conn:
            weg = conn.execute("DELETE FROM aiguard_bans WHERE subject=?",
                               (f"user:{user_id!s}",)).rowcount
            conn.execute("DELETE FROM aiguard_flags WHERE user_id=?", (str(user_id),))
            conn.execute("DELETE FROM aiguard_chat_locks WHERE user_id=?", (str(user_id),))
        return bool(weg)

    def unban_ip(self, ip: str) -> bool:
        subjekt = self.ip_subject(ip)
        if not subjekt:
            return False
        with self._lock, self._connect() as conn:
            weg = conn.execute("DELETE FROM aiguard_bans WHERE subject=?",
                               (subjekt,)).rowcount
        return bool(weg)

    def is_banned(self, user_id: str = "", ip: str = "", device: str = "") -> Ban | None:
        """Ist dieses Konto, diese Adresse oder dieses Geraet gesperrt?

        Returns: die Sperre oder None.
        """
        subjects = []
        if re.fullmatch(r"[0-9a-f]{64}", str(device or "")):
            subjects.append("geraet:" + str(device))
        if user_id:
            subjects.append(f"user:{user_id!s}")
        adresse = self.ip_subject(ip)
        if adresse:
            subjects.append(adresse)
        if not subjects:
            return None
        platz = ",".join("?" for _ in subjects)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT subject, at, reason, by, until FROM aiguard_bans "
                f"WHERE subject IN ({platz}) ORDER BY at",
                subjects,
            ).fetchall()

        jetzt = time.time()
        for row in rows:
            ban = _ban_of(row)
            if ban.active(jetzt):
                return ban
        return None

    def bans(self) -> list[Ban]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT subject, at, reason, by, until FROM aiguard_bans ORDER BY at"
            ).fetchall()
        return [_ban_of(r) for r in rows]



BANNED_MESSAGE = (
    "Dieses Konto ist gesperrt. Ai-guard hat einen schweren Verstoß gegen die "
    "Nutzungsregeln erkannt. Oben links unter der Versionsnummer steht unter „Info“, "
    "warum und wie lange. Wenn du das für einen Irrtum hältst, wende dich an den "
    "Betreiber dieser Installation."
)



DEMEANING_REASON = "Auftrag, jemanden zu beleidigen oder herabzusetzen"


def chat_locked_message(grund: str = "") -> str:
    """Der Satz fuer einen gesperrten Chat -- mit dem richtigen Grund (9.5.28)."""
    if grund == DEMEANING_REASON:
        return ("Dabei hilft Aquaticy nicht: andere beleidigen, runtermachen oder "
                "blossstellen. Ai-guard hat diesen Chat deshalb gesperrt. Ein Zitat allein "
                "ist in Ordnung — du kannst einen neuen Chat beginnen und zum Beispiel "
                "fragen, wie du ruhig und bestimmt darauf antwortest.")
    return CHAT_LOCKED_MESSAGE


CHAT_LOCKED_MESSAGE = (
    "In diesem Chat kannst du nicht mehr schreiben — Ai-guard hat ihn wegen "
    "unangemessener Sprache gesperrt. Du kannst einen neuen Chat beginnen."
)




VM_SWITCH_MESSAGE = (
    "Hinweis: Für Cybersecurity- und Schadsoftware-Themen steht die virtual machine bei "
    "Normal- und Pro-Konten nicht zur Verfügung. Aquaticy hat deshalb in den Normal-Modus "
    "gewechselt und antwortet dort weiter — ohne eigene Maschine, in der Code ausgeführt wird."
)


WHAT_TO_DO = (
    "Warte, bis die Sperre abläuft — danach geht alles wieder wie vorher. Hältst du die "
    "Sperre für einen Irrtum, wende dich an den Betreiber dieser Installation; er kann "
    "sie im Terminal aufheben (aquaticy unban)."
)


def ban_info(ban: Ban | None, now: float | None = None) -> dict[str, Any]:
    """Was die Oberflaeche ueber eine Sperre zeigt (9.5.24). Leer, wenn keine."""
    if ban is None or not ban.active(now):
        return {"banned": False}
    grund = ban.reason.removeprefix("Ai-guard: ").strip() or "Verstoß gegen die Nutzungsregeln"
    if ban.until <= 0:
        dauer, bis = "dauerhaft", ""
    else:
        dauer = ban.remaining_text(now)
        bis = time.strftime("%d.%m.%Y, %H:%M Uhr", time.localtime(ban.until))
    return {"banned": True, "reason": grund, "duration": dauer, "until": bis,
            "permanent": ban.until <= 0, "what_to_do": WHAT_TO_DO}


def guard_for(data_dir: Path | str) -> AiGuard:
    """Ai-guard für die Kontendatenbank eines Datenordners."""
    return AiGuard(Path(data_dir) / "accounts.sqlite3")


def check_message(
    guard: AiGuard,
    account: Any,
    text: str,
    settings: Settings,
    *,
    chat: str = "",
    context: str = "",
    ask: Callable[[str, Settings], str] | None = None,
) -> tuple[bool, str]:
    """Prüft eine Nachricht eines angemeldeten Kontos. Returns: (gesperrt, Grund).

    Ist das Konto schon gesperrt, kommt sofort (True, Grund). Sonst wird die
    Nachricht eingeschätzt; ein Anhaltspunkt wird vermerkt und sperrt beim
    zweiten Mal.
    """
    if account is None:
        return False, ""
    user_id = str(getattr(account, "id", "") or "")
    laufend = guard.is_banned(user_id=user_id, ip=str(getattr(account, "last_ip", "") or ""))
    if laufend is not None:
        return True, BANNED_MESSAGE
    urteil = classify(text, settings, context=context, ask=ask)
    if not urteil or not urteil[0]:
        return False, ""
    darf_bannen = not bool(getattr(account, "ultra", False))
    gesperrt = guard.note(user_id, urteil[1], detail=urteil[1], chat=chat, enforce=darf_bannen)
    return (True, BANNED_MESSAGE) if gesperrt else (False, "")
