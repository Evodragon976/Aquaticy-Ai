"""Merkt sich nebenbei Gesagtes ueber den Nutzer -- wie das Gedaechtnis grosser Chat-Apps (15.3.4).

Bis 15.2.4 hing alles am Modell: Es sollte von sich aus `save_memory` aufrufen, wenn der
Nutzer "ich heisse Louis" sagte. Starke Modelle taten das, kleine und manche Cloud-Modelle
vergassen es. Jetzt gibt es zwei feste Wege dazu:

1. **Sofort und ohne Modell** (`extract`): klare Saetze in der eigenen Nachricht ("ich heisse
   Louis", "ich wohne in Bremen", "ich mag Pizza", "nenn mich Lou") werden noch vor der
   Antwort abgelegt. So nutzt schon die erste Antwort den neuen Stand.
2. **Nach der Antwort mit dem schnellen Modell** (`llm_facts`): findet Beilaeufiges, das kein
   Muster trifft ("am Wochenende war ich wieder klettern, das ist einfach meins"). Laeuft
   nur bei Nachrichten mit Ich-Bezug und nur bei Wolkenmodellen; ein lokales Modell soll nicht
   die naechste Antwort aufhalten.

Regeln, die fuer beide gelten:

* **Nur ueber den Nutzer selbst**, nur was er klar sagt. Keine Vermutungen, nichts aus
  Webseiten, Mails oder Anhaengen (`own_words` liefert nur die eigenen Worte).
* **Nichts Besonderes ohne Bitte:** Gesundheit, Religion, Politik, Sexualitaet, ethnische
  Herkunft, Gewerkschaft, Straftaten, Passwoerter und Nummern (IBAN, Karten) werden nie von
  allein gemerkt. Sagt der Nutzer ausdruecklich "merk dir", entscheidet das Hauptmodell mit
  `save_memory` -- wie bisher.
* **Ein Stand je Sache:** Name, Wohnort, Beruf und Co. haben einen Platz. Ein neuer Wert
  ersetzt den alten ("ich bin nach Hamburg gezogen"). "Mag X" und "mag X nicht" heben sich
  auf. Doppeltes wird nicht noch einmal abgelegt.
* **Nie im Code-Modus** -- dort gibt es weder Lesen noch Schreiben (aquaticy/agent.py).
* **"Merk dir das nicht"** in der Nachricht: dann wird nichts automatisch gemerkt.
  "Vergiss, dass ich X mag" loescht passende Eintraege.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import queue
import re
import threading
import unicodedata
import weakref
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any

from aquaticy.zeit import heute as zeit_heute

PERSON = "person"
MAX_VALUE = 60
MAX_FACT = 200
MAX_LLM_FACTS = 5
MAX_PERSON_FACTS = 40

# Plaetze mit genau einem gueltigen Wert: Ein neuer Wert ersetzt den alten.
SINGLE = frozenset({"name", "anrede", "wohnort", "herkunft", "beruf", "arbeitgeber", "alter",
                    "geburtstag", "geburtsdatum", "ernaehrung", "schule", "studium"})
# 15.5.5: Ein Geburtsdatum macht Alter und Geburtstag ueberfluessig (das Alter veraltet).
REPLACED_BY = {"geburtsdatum": ("alter", "geburtstag")}


@dataclass(frozen=True)
class Fact:
    """Ein Satz ueber den Nutzer mit seinem Platz im Speicher."""

    slot: str
    text: str

    @property
    def topic(self) -> str:
        return f"{PERSON}:{self.slot}"[:80]


# -- Was nie von allein gemerkt wird -------------------------------------------------------------
_SENSIBEL = re.compile(
    r"(?i)\b(krank(?:e|en|er|es)?|krankheit\w*|diagnose\w*|depress\w*|therap\w*|medikament\w*|"
    r"allerg\w*|diabet\w*|krebs|schwanger\w*|behinder\w*|psych\w*|adhs|autis\w*|"
    r"religi\w*|christlich\w*|christentum|christianity|muslim\w*|moslem\w*|"
    r"jud(?:e|in|en)|jüd\w*|atheist\w*|"
    r"kirche\w*|moschee\w*|partei\w*|w(?:ä|ae)hle\w*|afd|spd|cdu|csu|fdp|"
    r"schwul\w*|lesbisch\w*|bisexuell\w*|transgender|trans\b|queer|sexuell\w*|"
    r"gewerkschaft\w*|vorstrafe\w*|knast|gefängnis\w*|verurteilt\w*|ethni\w*|hautfarbe|"
    r"passwort\w*|kennwort\w*|password|pin\b|iban|kreditkart\w*|tan\b|token|"
    r"sick|illness|disease|religion|church|gay|lesbian|ssn)\b")
_GEHEIM = re.compile(r"(?i)(?:\b[A-Z]{2}\d{2}(?:\s?\w{4}){3,7}\b|\b(?:\d[ -]?){13,19}\b|"
                     r"ghp_|github_pat_|sk-[a-z0-9]|nvapi-|xox[bp]-|AKIA[0-9A-Z]{8})")


_SENSIBEL_EXTRA = re.compile(
    r"(?i)\b(?:hiv|aids|bipolar\w*|disorder|katholi\w*|catholi\w*|protestant\w*|"
    r"evangelisch\w*|buddh\w*|hindu\w*|orthodox\w*|islam\w*|suizid\w*|suicid\w*|"
    r"grünen?|gruene[nr]?|linken?|republican\w*|democrat\w*|verdi|ver\.di|ig\s+metall|"
    r"pregnan\w*|disabled|disability|bisexual\w*|sexual\w*|convicted|criminal|"
    r"depression|medication|health|ethnicity|api[ _-]?key|geheimnis|secret)\b")

_LOCKS: weakref.WeakValueDictionary[str, Any] = weakref.WeakValueDictionary()
_LOCKS_GUARD = threading.Lock()


@contextmanager
def profile_lock(store: Any) -> Iterator[None]:
    key = str(getattr(store, "db_path", id(store)))
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(key, threading.RLock())
    with lock:
        yield


def _entries(store: Any) -> list[Any]:
    iterator = getattr(store, "iter_entries", None)
    return list(iterator()) if callable(iterator) else list(store.all_entries(limit=2000))


def credentials(text: str) -> bool:
    return bool(_GEHEIM.search(text or "") or re.search(
        r"(?i)\b(?:passwort\w*|kennwort\w*|password|pin|iban|kreditkart\w*|"
        r"api[ _-]?key|auth[ _-]?token|session[ _-]?key|zugangsdaten)\b", text or ""))


def sensitive(text: str) -> bool:
    """Gehoert das zu den Dingen, die nur auf ausdrueckliche Bitte in den Speicher duerfen?"""
    context = re.search(
        r"(?i)\b(?:bin|ist|is|am|a)\s+(?:ein\w*\s+)?christ(?:ian)?s?\b"
        r"|\b(?:bin|ist|is|am|liege|liegt)\s+im\s+Krankenhaus\b", text or "")
    return bool(_SENSIBEL.search(text or "") or _SENSIBEL_EXTRA.search(text or "")
                or _GEHEIM.search(text or "") or context)


_NICHT_MERKEN = re.compile(
    r"(?i)\b(?:merk\s+dir\s+(?:das|es|dies)\s+nicht|nicht\s+(?:merken|speichern|"
    r"abspeichern|notieren)|vergiss\s+(?:das|es)\s+(?:gleich|wieder|sofort)|"
    r"don'?t\s+(?:remember|save|store)\s+(?:this|that|it))\b")


def opted_out(text: str) -> bool:
    """Will der Nutzer, dass diese Nachricht nicht gemerkt wird?"""
    return bool(_NICHT_MERKEN.search(text or "") or re.search(
        r"(?i)\b(?:speicher\w*\s+(?:das|es|dies)\s+nicht|merk\w*\s+dir\s+nichts"
        r"|do\s+not\s+(?:remember|save|store)\s+(?:this|that|it))\b", text or ""))


# -- Werte saeubern ------------------------------------------------------------------------------
_ENDE = re.compile(
    r"\s*(?:[,.;:!?()\[\]\"„“”]|\s-\s|\s(?:und|aber|oder|weil|denn|doch|also|sondern|"
    r"wenn|dass|damit|obwohl|seit|bis|was|wie|wo|wer|kannst|könntest|bitte|and|but|or|"
    r"because|so|can|could|please)\s).*$", re.IGNORECASE | re.DOTALL)
_FUELL = re.compile(r"(?i)^(?:(?:auch|eigentlich|wirklich|total|sehr|echt|so|ja|halt|"
                    r"gerne?|gern|mittlerweile|inzwischen|jetzt|seit\s+kurzem|really|also|"
                    r"actually|now)\s+)+")


def _wert(roh: str, woerter: int = 6) -> str:
    """Schneidet einen gefundenen Wert am Satz- oder Nebensatzende ab."""
    wert = _ENDE.sub("", " ".join(str(roh or "").split()))
    wert = _FUELL.sub("", wert).strip(" -–'\"")
    teile = wert.split()
    if not teile or len(teile) > woerter or len(wert) > MAX_VALUE:
        return ""
    return wert


def _gross(wert: str) -> str:
    return " ".join(t[:1].upper() + t[1:] for t in wert.split())


def _schluessel(wert: str) -> str:
    """Vergleichswert fuer "mag X" und "mag X nicht": klein, ohne Artikel."""
    wert = re.sub(r"(?i)^(?:den|die|das|der|dem|einen?|eine[mnrs]?|kein\w*|the|a|an)\s+", "",
                  wert.strip())
    key = re.sub(r"[\W_]+", "-", unicodedata.normalize("NFKC", wert).casefold()).strip("-")
    if len(key) > 40:
        suffix = hashlib.sha256(key.encode()).hexdigest()[:8]
        key = key[:31] + "-" + suffix
    return key


_FRAGE = re.compile(r"(?i)^(?:wie|was|wo|wer|wann|warum|wieso|weißt|weisst|kennst|"
                    r"heiße\s+ich|heisse\s+ich|do|does|what|who|where)\b")


def explicit_request(text: str) -> bool:
    if opted_out(text):
        return False
    words = own_message(text)
    return bool(re.search(
        r"(?im)(?:^|[.!?]\s+)(?:bitte\s+|please\s+)?"
        r"(?:merk(?:e)?\s+dir|speicher(?:e)?|notier(?:e)?|remember|save|store|memorize)\b"
        r"|\b(?:kannst|könntest|koenntest)\s+du\s+(?:dir\s+)?[^.!?\n]{0,80}"
        r"\b(?:merken|speichern|notieren)\b"
        r"|\b(?:can|could)\s+you\s+(?:please\s+)?(?:remember|save|store|memorize)\b"
        r"|\bbitte\s+(?:merken|speichern|notieren)\b", words))


def own_message(text: str) -> str:
    text = re.sub(r"(?s)```.*?```|~~~.*?~~~", " ", str(text or ""))
    text = re.sub(r"(?ms)^[ \t]{0,3}(?:`{3,}|~{3,})[^\n]*(?:\n|$).*\Z", " ", text)
    text = re.sub(r'"[^"\n]*"|„[^“\n]*“|“[^”\n]*”', " ", text)
    lines = []
    for line in text.splitlines():
        if re.match(r"\s*>", line) or re.match(
                r"(?i)\s*(?:beispiel|zitiere|übersetz\w*|uebersetz\w*|translate|quote)\b", line):
            continue
        lines.append(line)
    return "\n".join(lines)


def _saetze(text: str) -> list[str]:
    """Aussagesaetze -- Fragen ("wie heisse ich?") und Wenn-Saetze zaehlen nicht."""
    saetze = []
    source = own_message(text)
    source = re.sub(
        r"\b\d{1,2}\.\s*(?:\d{1,2}\.?|Januar|Februar|März|April|Mai|Juni|Juli|"
        r"August|September|Oktober|November|Dezember)",
        lambda match: match[0].replace(".", "\u2024"), source, flags=re.I)
    for satz in re.split(r"\n+|(?<=[.!?])\s+", source):
        satz = satz.replace("\u2024", ".").strip()
        if satz.endswith("?") and "," in satz:
            # "Ich wohne in Bremen, und du?" -- die Aussage vor der kurzen Rueckfrage zaehlt.
            vorne, _, hinten = satz.rpartition(",")
            if len(hinten.split()) <= 4 and len(vorne.split()) >= 2:
                satz = vorne.strip()
        if not satz or satz.endswith("?") or _FRAGE.match(satz):
            continue
        if re.match(r"(?i)^(?:wenn|falls|angenommen|stell\s+dir\s+vor|if|suppose)\b", satz):
            continue
        saetze.append(satz)
    return saetze


# -- Feste Muster --------------------------------------------------------------------------------
_I = r"(?:^|(?<=[\s,;:]))"
_MUSTER: list[tuple[str, re.Pattern[str]]] = [
    ("name", re.compile(_I + r"(?:ich\s+hei(?:ß|ss)e|mein\s+name\s+ist|my\s+name\s+is|"
                        r"i'?m\s+called|i\s+am\s+called)\s+(?P<w>[^\s,.!?]+(?:\s+(?-i:[A-ZÄÖÜ])"
                        r"[^\s,.!?]*)?)", re.IGNORECASE)),
    ("anrede", re.compile(_I + r"(?:nenn(?:e)?\s+mich|sag\s+(?:einfach\s+)?|call\s+me)\s+"
                          r"(?P<w>[^\W\d_][^\s,.!?]{0,30})(?:\s+zu\s+mir)?",
                          re.IGNORECASE)),
    ("wohnort", re.compile(_I + r"(?:(?:ich|und)\s+wohne\s+(?:jetzt\s+|seit\s+\w+\s+)?(?:in|im)|"
                           r"ich\s+lebe\s+(?:jetzt\s+)?(?:in|im)|ich\s+bin\s+"
                           r"(?:jetzt\s+)?nach(?=[^,.!?\n]*\b(?:um)?gezogen\b)"
                           r"|i\s+live\s+in|i\s+moved\s+to)\s+(?P<w>[^,.!?\n]+)",
                           re.IGNORECASE)),
    ("herkunft", re.compile(_I + r"(?:ich\s+komme\s+(?:urspr(?:ü|ue)nglich\s+)?aus|"
                            r"ich\s+stamme\s+aus|i'?m\s+from|i\s+come\s+from)\s+"
                            r"(?P<w>[^,.!?\n]+)", re.IGNORECASE)),
    ("beruf", re.compile(_I + r"(?:(?:ich|und)\s+arbeite\s+als|ich\s+bin\s+von\s+beruf|"
                         r"i\s+work\s+as(?:\s+an?)?)\s+(?P<w>[^,.!?\n]+)", re.IGNORECASE)),
    ("arbeitgeber", re.compile(_I + r"(?:ich\s+arbeite\s+(?:bei|für|fuer)|i\s+work\s+(?:at|for))"
                               r"\s+(?P<w>[^,.!?\n]+)", re.IGNORECASE)),
    ("alter", re.compile(_I + r"(?:ich\s+bin|i'?m|i\s+am)\s+(?P<w>\d{1,2})\s+"
                         r"(?:jahre\s+alt|years?\s+old|jahre\b)", re.IGNORECASE)),
    ("geburtstag", re.compile(_I + r"(?:ich\s+habe\s+am(?=[^!?\n]*\bGeburtstag\b)|"
                              r"mein\s+geburtstag\s+ist\s+(?:am)?|"
                              r"my\s+birthday\s+is(?:\s+on)?)\s*(?P<w>[0-9]{1,2}\.\s?(?:[0-9]"
                              r"{1,2}\.?|[A-Za-zäöü]+)|[A-Za-z]+\s+\d{1,2})", re.IGNORECASE)),
    ("geburtsdatum", re.compile(_I + r"(?:ich\s+(?:bin|wurde)\s+am|i\s+was\s+born\s+on)\s+"
                                r"(?P<w>\d{1,2}\.\s?\d{1,2}\.\s?\d{4})"
                                r"(?=\s*(?:geboren|born|$|[,.!]))", re.IGNORECASE)),
    ("ernaehrung", re.compile(_I + r"(?:ich\s+bin|ich\s+lebe|i'?m|i\s+am)\s+(?:seit\s+\w+\s+)?"
                              r"(?P<w>vegetarier(?:in)?|veganer(?:in)?|vegan|vegetarisch|"
                              r"vegetarian|pescetarier(?:in)?)\b", re.IGNORECASE)),
    ("mag_nicht", re.compile(_I + r"(?:ich\s+mag\s+(?:keine?n?|kein)|ich\s+hasse|"
                             r"ich\s+kann\s+\S+\s+nicht\s+leiden|i\s+hate|i\s+don'?t\s+like|"
                             r"i\s+dislike)\s+(?P<w>[^,.!?\n]+)", re.IGNORECASE)),
    ("mag_nicht2", re.compile(_I + r"ich\s+kann\s+(?P<w>[^,.!?\n]+?)\s+nicht\s+leiden\b",
                              re.IGNORECASE)),
    ("mag_nicht2", re.compile(_I + r"ich\s+mag\s+(?P<w>[^,.!?\n]+?)\s+(?:gar\s+|überhaupt\s+)?"
                              r"nicht\b", re.IGNORECASE)),
    ("mag", re.compile(_I + r"(?:(?:ich|und)\s+(?:mag|liebe)|ich\s+(?:esse|trinke|höre|hoere|lese|"
                       r"spiele|schaue)\s+(?:sehr\s+)?gern(?:e)?|i\s+(?:really\s+)?(?:like|"
                       r"love|enjoy))\s+(?P<w>[^,.!?\n]+)", re.IGNORECASE)),
    ("lieblings", re.compile(_I + r"mein(?:e)?\s+lieblings(?P<art>[a-zäöüß]+)\s+(?:ist|sind)\s+"
                             r"(?P<w>[^,.!?\n]+)", re.IGNORECASE)),
    ("sprache", re.compile(_I + r"(?:ich\s+spreche|i\s+speak)\s+(?P<w>[A-ZÄÖÜa-zäöü]+"
                           r"(?:\s+und\s+[A-ZÄÖÜa-zäöü]+)?)", re.IGNORECASE)),
    ("haustier", re.compile(_I + r"(?:ich\s+habe|i\s+have)\s+(?P<w>(?:einen?|zwei|drei|a|two)\s+"
                            r"(?:hund|katze|kater|hamster|pferd|kaninchen|hunde|katzen|dog|cat|"
                            r"dogs|cats)(?:\s+(?:namens|der\s+heißt|die\s+heißt|named|called)\s+"
                            r"[A-ZÄÖÜ][a-zäöüß]+)?)", re.IGNORECASE)),
]

_KEIN_NAME = re.compile(r"(?i)^(?:nicht|kein\w*|so|eigentlich|wirklich|auch|du|sie|er|es|"
                        r"ein\w*|der|die|das|hier|da|gerade|jetzt|müde|fertig|ok|okay)$")
_KEIN_WERT = re.compile(r"(?i)^(?:es|das|dich|dir|euch|sie|ihn|ihr|it|you|that|this|"
                        r"nichts|alles|so|nicht)$")


def birth_date(text: str) -> date | None:
    """Ein plausibles Geburtsdatum aus "15.03.2001" (oder "Geboren am 15.03.2001.")."""
    treffer = re.search(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})\b", text or "")
    if not treffer:
        return None
    try:
        datum = date(int(treffer[3]), int(treffer[2]), int(treffer[1]))
    except ValueError:
        return None
    heute = zeit_heute()
    return datum if heute.year - 120 <= datum.year and datum <= heute else None


def age_on(geboren: date, heute: date | None = None) -> int:
    heute = heute or zeit_heute()
    return heute.year - geboren.year - ((heute.month, heute.day) < (geboren.month, geboren.day))


def with_age(text: str, topic: str = "") -> str:
    """Haengt an ein gespeichertes Geburtsdatum das heutige Alter an -- es veraltet nie."""
    if not str(topic or "").casefold().endswith(":geburtsdatum"):
        return text
    datum = birth_date(text)
    if datum is None:
        return text
    return f"{text.rstrip('.')} (heute {age_on(datum)} Jahre alt)."


def _fakt(slot: str, wert: str, art: str = "") -> Fact | None:
    if not wert or sensitive(wert):
        return None
    if slot == "name":
        teile = wert.split()
        if len(teile) > 2 or _KEIN_NAME.match(teile[0]) or not teile[0][:1].isalpha():
            return None
        return Fact("name", f"Der Nutzer heißt {_gross(wert)}.")
    if slot == "anrede":
        if _KEIN_NAME.match(wert):
            return None
        return Fact("anrede", f"Möchte mit „{wert}“ angesprochen werden.")
    if slot == "wohnort":
        return Fact("wohnort", f"Wohnt in {wert}.")
    if slot == "herkunft":
        return Fact("herkunft", f"Kommt ursprünglich aus {wert}.")
    if slot == "beruf":
        return Fact("beruf", f"Arbeitet als {wert}.")
    if slot == "arbeitgeber":
        return Fact("arbeitgeber", f"Arbeitet bei {wert}.")
    if slot == "alter":
        alter = int(wert)
        if not 6 <= alter <= 99:
            return None
        return Fact("alter", f"Ist {alter} Jahre alt (Stand {zeit_heute():%m/%Y}).")
    if slot == "geburtsdatum":
        datum = birth_date(wert)
        if datum is None:
            return None
        return Fact("geburtsdatum", f"Geboren am {datum:%d.%m.%Y}.")
    if slot == "geburtstag":
        import calendar

        months = {name.casefold(): number for number, name in enumerate(calendar.month_name)
                  if name}
        months.update({name: number for number, name in enumerate((
            "", "januar", "februar", "märz", "april", "mai", "juni", "juli", "august",
            "september", "oktober", "november", "dezember")) if name})
        match = re.fullmatch(r"(\d{1,2})\.\s*([\w]+)\.?", wert)
        english = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2})", wert)
        if match:
            day, month = int(match[1]), match[2]
        elif english:
            day, month = int(english[2]), english[1]
        else:
            return None
        try:
            number = int(month) if month.isdecimal() else months.get(month.casefold(), 0)
            date(2000, number, day)
        except (ValueError, OverflowError):
            return None
        return Fact("geburtstag", f"Hat am {wert} Geburtstag.")
    if slot == "ernaehrung":
        art_text = wert.casefold()
        if art_text.startswith(("veg", "vegan")) and "an" in art_text[:5]:
            return Fact("ernaehrung", "Ernährt sich vegan.")
        if art_text.startswith("pesc"):
            return Fact("ernaehrung", "Isst kein Fleisch, aber Fisch.")
        return Fact("ernaehrung", "Ernährt sich vegetarisch.")
    if slot in ("mag", "mag_nicht"):
        if _KEIN_WERT.match(wert) or wert.casefold().startswith(("es ", "dass ", "wenn ")):
            return None
        key = _schluessel(wert)
        if not key:
            return None
        if slot == "mag":
            return Fact(f"mag:{key}", f"Mag {wert}.")
        return Fact(f"mag_nicht:{key}", f"Mag {wert} nicht.")
    if slot == "lieblings":
        art = re.sub(r"[^a-zäöüß]", "", art.casefold())[:20]
        if not art:
            return None
        return Fact(f"lieblings:{art}", f"Lieblings{art}: {wert}.")
    if slot == "sprache":
        if re.match(r"(?i)^(?:über|ueber|von|mit|zu|gerade|heute|jetzt|noch|nicht|auch|nur)\b",
                    wert):
            return None
        return Fact(f"sprache:{_schluessel(wert)}", f"Spricht {wert}.")
    if slot == "haustier":
        return Fact(f"haustier:{_schluessel(wert)}", f"Hat {wert}.")
    return None


def extract(text: str) -> list[Fact]:
    """Feste Muster: klare Aussagen ueber den Nutzer, ohne Modell. Doppeltes nur einmal."""
    if not text or opted_out(text):
        return []
    gefunden: dict[str, Fact] = {}
    for satz in _saetze(text[:4000]):
        if sensitive(satz):
            continue
        belegt: list[tuple[int, int]] = []
        for slot, muster in _MUSTER:
            for treffer in muster.finditer(satz):
                woerter = 2 if slot in ("name", "anrede") else 6
                wert = (treffer.group("w").strip() if slot in ("geburtstag", "geburtsdatum",
                                                               "sprache")
                        else _wert(treffer.group("w"), woerter))
                start, ende = treffer.start(), treffer.start("w") + len(wert)
                if any(start < b and ende > a for a, b in belegt):
                    continue
                if treffer.group(0).strip().casefold().startswith("und") and not re.search(
                        r"(?i)\b(?:ich|i)\b", satz[:start]):
                    continue  # "Er heisst Max und mag Pizza" -- nicht der Nutzer
                if slot == "wohnort":
                    wert = re.sub(r"(?i)\s+(?:gezogen|umgezogen|moved)$", "", wert)
                if slot in ("wohnort", "herkunft") and wert:
                    wert = _gross(wert) if wert.islower() else wert
                art = treffer.groupdict().get("art") or ""
                fakt = _fakt("mag_nicht" if slot == "mag_nicht2" else slot, wert, art)
                if fakt is not None:
                    belegt.append((start, ende))
                    gefunden[fakt.slot] = fakt
    return list(gefunden.values())[:8]


_VERGISS = re.compile(r"(?i)\b(?:vergiss|lösch\w*|loesch\w*|forget)\s*,?\s*(?:bitte\s*,?\s*)?"
                      r"(?:dass|das\s+mit|was\s+ich\s+über|that)\s+(?P<w>[^.!?\n]{2,80})")


def forget_request(text: str) -> str:
    """"Vergiss, dass ich Pilze mag" -> "pilze mag" (oder "" ohne solche Bitte)."""
    text = own_message(text)
    field = re.fullmatch(
        r"(?i)\s*(?:bitte\s+|please\s+)?(?:vergiss|lösche|loesche|forget|erase)\s+"
        r"(?:bitte\s+)?(?:mein(?:e[nrms]?)?|my)\s+"
        r"(namen?|wohnort|ort|adresse|address|location|geburtstag|birthday|alter|age|"
        r"beruf|job|herkunft|origin)\s*[.!?]*\s*", text)
    if field:
        aliases = {"namen": "name", "ort": "wohnort", "adresse": "wohnort",
                   "address": "wohnort", "location": "wohnort", "birthday": "geburtstag",
                   "age": "alter", "job": "beruf", "origin": "herkunft"}
        name = field[1].casefold()
        return "@field:" + aliases.get(name, name)
    treffer = _VERGISS.search(text)
    if not treffer:
        return ""
    wert = re.sub(r"(?i)^(?:ich|i)\s+", "", treffer.group("w").strip())
    return wert[:80]


# -- Ablegen mit einem Stand je Sache ------------------------------------------------------------
def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", " ",
                  unicodedata.normalize("NFKC", text or "").casefold()).strip()


def person_entries(store: Any, limit: int | None = MAX_PERSON_FACTS) -> list[Any]:
    if limit is not None and limit <= 0:
        return []
    try:
        passend = []
        with contextlib.closing(store.iter_entries(topic_prefix=PERSON)) as stream:
            for entry in stream:
                if str(entry.topic or "").casefold().split(":", 1)[0].strip() == PERSON:
                    passend.append(entry)
                    if limit is not None and len(passend) >= limit:
                        break
        return list(reversed(passend))
    except Exception:
        return []


_ALTER_PLATZ = {
    "name": re.compile(r"(?i)\bhei(?:ß|ss)t\b|\bname\s+ist\b"),
    "wohnort": re.compile(r"(?i)\bwohnt\b|\blebt\s+in\b"),
    "beruf": re.compile(r"(?i)\barbeitet\s+als\b|\bvon\s+beruf\b"),
    "alter": re.compile(r"(?i)\bjahre\s+alt\b"),
}


def store_facts(store: Any, facts: list[Fact], *,
                expected_revision: int | None = None) -> list[Fact]:
    if store is None or not facts:
        return []
    with profile_lock(store):
        return _store_facts(store, facts, expected_revision)


def _store_facts(store: Any, facts: list[Fact],
                 expected_revision: int | None) -> list[Fact]:
    try:
        version = store.revision()
        if expected_revision is not None and version != expected_revision:
            return []
        vorhanden = _entries(store)
    except Exception:
        return []
    neu: list[Fact] = []
    for fakt in facts:
        gegenteil = ""
        if fakt.slot.startswith("mag:"):
            gegenteil = "mag_nicht:" + fakt.slot.split(":", 1)[1]
        elif fakt.slot.startswith("mag_nicht:"):
            gegenteil = "mag:" + fakt.slot.split(":", 1)[1]
        einzel = fakt.slot in SINGLE or fakt.slot.startswith("lieblings:")
        gleich = False
        ersetzen = set()
        for eintrag in vorhanden:
            thema = str(eintrag.topic or "").casefold()
            if thema.startswith(("person:mag:", "person:mag_nicht:")):
                old_kind = thema.split(":", 2)[1]
                value = re.sub(r"(?i)^mag\s+|\s+nicht\.?$|\.$", "", eintrag.text)
                thema = f"person:{old_kind}:{_schluessel(value)}"
            if _norm(eintrag.text) == _norm(fakt.text):
                gleich = True
                continue
            if any(thema == f"{PERSON}:{alt}" for alt in REPLACED_BY.get(fakt.slot, ())):
                ersetzen.add(eintrag.id)
                continue
            if (thema == fakt.topic.casefold() and einzel) or (
                    thema == PERSON and fakt.slot in _ALTER_PLATZ
                    and _ALTER_PLATZ[fakt.slot].search(str(eintrag.text or ""))) or (
                    gegenteil and thema == f"{PERSON}:{gegenteil}"):
                ersetzen.add(eintrag.id)
        if gleich:
            continue
        try:
            eintrag = store.remember(fakt.text, fakt.topic, replace_ids=ersetzen,
                                     expected_revision=version)
        except Exception:
            continue
        version += 1
        vorhanden = [e for e in vorhanden if e.id not in ersetzen]
        vorhanden.append(eintrag)
        neu.append(fakt)
    return neu


def forget_matching(store: Any, wunsch: str) -> list[str]:
    """Loescht Eintraege ueber den Nutzer, die zu *wunsch* passen. Returns: geloeschte Texte."""
    field = wunsch.removeprefix("@field:") if wunsch.startswith("@field:") else ""
    if field not in {"name", "wohnort", "geburtstag", "alter", "beruf", "herkunft"}:
        field = ""
    forms = {"heisse": "heisst", "wohne": "wohnt", "arbeite": "arbeitet", "komme": "kommt"}
    woerter = [forms.get(w, w) for w in _norm(wunsch).split() if w not in (
        "mag", "ich", "bin", "habe", "nicht", "dass", "the", "like", "and")]
    if store is None or not woerter:
        return []
    weg = []
    store.invalidate_pending()
    for eintrag in person_entries(store, limit=None):
        text = _norm(f"{eintrag.text} {eintrag.topic}")
        topic = str(eintrag.topic or "").strip().casefold()
        matches = (topic == PERSON + ":" + field if field
                   else set(woerter) <= set(text.split()))
        if matches and store.forget(eintrag.id):
            weg.append(str(eintrag.text))
    return weg


# -- Mit dem schnellen Modell: Beilaeufiges ------------------------------------------------------
_ICH = re.compile(r"(?i)\b(?:ich|mein\w*|mir|mich|wir|unser\w*|i|i'm|i've|my|me|we|our)\b")
ARTEN = frozenset({"name", "anrede", "wohnort", "herkunft", "beruf", "arbeitgeber", "alter",
                   "geburtstag", "geburtsdatum", "ernaehrung", "schule", "studium", "mag",
                   "mag_nicht",
                   "lieblings", "haustier", "familie", "sprache", "hobby", "vorhaben",
                   "ausstattung", "stil", "sonstiges"})

LLM_PROMPT = """Du bist das Gedächtnis eines Assistenten. Lies die Nachricht des Nutzers.
Schreib dauerhafte Tatsachen über den Nutzer SELBST heraus, die er klar sagt, auch nebenbei:
Name, Anrede, Wohnort, Beruf, Vorlieben und Abneigungen, Hobbys, Familie, Haustiere, Sprachen,
Ausstattung (Geräte, Auto), laufende Vorhaben, wie er Antworten mag.

Nicht aufschreiben: Fragen, Vermutungen, Tagesaktuelles ("ich bin müde"), Dinge über andere,
Inhalte aus Texten, die er nur zitiert. Nie: Gesundheit, Religion, Politik, Sexualität,
ethnische Herkunft, Gewerkschaft, Straftaten, Passwörter, Konto- oder Kartennummern.
Was schon bekannt ist, nicht noch einmal – außer es hat sich geändert.

Wurde im Gespräch unten etwas über den Nutzer aus SEINEN Angaben errechnet (zum Beispiel sein
Geburtsdatum aus einer Rückfrage), schreib das Ergebnis auf: ein Geburtsdatum als
"Geboren am TT.MM.JJJJ." mit art geburtsdatum, statt eines Alters. Prüfe die Rechnung selbst
nach; ist sie unsicher, schreib nichts. Über andere Personen (z. B. die Mutter) nichts.

Bekannt:
%(bekannt)s

Nachricht des Nutzers:
<<<
%(nachricht)s
>>>
%(gespraech)s
Antworte nur mit JSON: {"fakten": [{"art": "...", "text": "..."}]}
art ist eins von: %(arten)s. text ist ein kurzer deutscher Satz in der dritten Person,
zum Beispiel "Mag Klettern." oder "Wohnt in Bremen.". Nichts gefunden: {"fakten": []}"""


def worth_asking(text: str) -> bool:
    """Lohnt der Modellaufruf? Nur bei Ich-Bezug, ohne Opt-out, nicht bei reinen Fragen."""
    text = own_message(text).strip()
    if sensitive(text) or forget_request(text):
        return False
    if len(text) < 12 or opted_out(text) or not _ICH.search(text):
        return False
    return any(not s.endswith("?") for s in re.split(r"(?<=[.!?\n])\s+", text) if s.strip())


def llm_prompt(nachricht: str, bekannt: list[str], gespraech: str = "") -> str:
    gespraech = gespraech[:2500].replace(">>>", "> > >").replace("<<<", "< < <")
    return LLM_PROMPT % {
        "bekannt": "\n".join(f"- {t}" for t in bekannt[:MAX_PERSON_FACTS]) or "- (noch nichts)",
        "nachricht": nachricht[:1500].replace(">>>", "> > >"),
        "gespraech": (f"\nGespräch dazu (Rückfragen, Antworten des Nutzers, Antwort des "
                      f"Assistenten):\n<<<\n{gespraech}\n>>>\n" if gespraech else ""),
        "arten": ", ".join(sorted(ARTEN)),
    }


def parse_llm(raw: str) -> list[Fact]:
    """Liest die Antwort des Modells -- streng: unbekannte Arten, Sensibles, Ueberlanges fliegt."""
    raw = str(raw or "")
    start, ende = raw.find("{"), raw.rfind("}")
    if start == -1 or ende <= start:
        return []
    try:
        daten = json.loads(raw[start:ende + 1])
    except (ValueError, RecursionError):
        return []
    liste = daten.get("fakten") if isinstance(daten, dict) else None
    if not isinstance(liste, list):
        return []
    fakten: list[Fact] = []
    for eintrag in liste[:MAX_LLM_FACTS]:
        if not isinstance(eintrag, dict):
            continue
        art = str(eintrag.get("art") or "").strip().casefold()
        value = eintrag.get("text")
        if not isinstance(value, str) or not 4 <= len(value.strip()) <= MAX_FACT:
            continue
        text = " ".join(value.split())
        if art not in ARTEN or len(text) < 4 or sensitive(text) or "http" in text.casefold():
            continue
        if not text.endswith((".", "!")):
            text += "."
        from aquaticy.injection import suspicious

        if suspicious(text):
            continue
        if art == "geburtsdatum":
            datum = birth_date(text)
            if datum is None:
                continue
            text = f"Geboren am {datum:%d.%m.%Y}."
        slot = art if art in SINGLE else f"{art}:{_schluessel(text)}"
        if art == "lieblings":
            favorite = re.match(r"(?i)^Lieblings([a-zäöüß]+)\s*:", text)
            if favorite is None:
                continue
            slot = "lieblings:" + favorite[1].casefold()
        if art in ("mag", "mag_nicht"):
            kern = re.sub(r"(?i)^mag\s+|\s+nicht\.?$|\.$", "", text)
            slot = f"{art}:{_schluessel(kern)}"
        fakten.append(Fact(slot, text))
    return fakten


def ask_model(settings: Any, prompt: str) -> str:
    """Ein kurzer Aufruf beim schnellen Modell -- die einzige Stelle mit Netz hier."""
    from aquaticy import metering
    from aquaticy.pace import key_of, paced

    model = str(getattr(settings, "effective_subagent_model", "") or settings.model)
    with paced(model, key_of(settings, model)):
        antwort = metering.completion(
            settings, enforce=True, model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300, timeout=25.0, **settings.fast_kwargs_for(model))
    return str(antwort.choices[0].message.content or "")


def cloud_model(settings: Any) -> bool:
    """Laeuft das schnelle Modell in der Cloud? Lokal bleibt es beim festen Weg."""
    from aquaticy.config import provider_of

    model = str(getattr(settings, "effective_subagent_model", "") or settings.model)
    return provider_of(model) not in ("ollama", "ollama_chat", "llamacpp", "hosted_vllm", "")


def learn_with_model(settings: Any, store: Any, nachricht: str, *,
                     allowed: Any = None, ask: Any = None, gespraech: str = "") -> list[Fact]:
    def enabled() -> bool:
        return bool(settings.memory_enabled and (allowed is None or allowed()))

    nachricht = own_message(nachricht)
    if store is None or not enabled() or not worth_asking(nachricht):
        return []
    from aquaticy.keyvault import scrub

    secrets = settings.secrets()
    if scrub(nachricht, secrets) != nachricht or scrub(gespraech, secrets) != gespraech:
        return []
    if gespraech and (sensitive(gespraech) or opted_out(gespraech)):
        gespraech = ""
    version = store.revision()
    bekannt = [str(e.text) for e in person_entries(store)
               if not sensitive(str(e.text)) and scrub(str(e.text), secrets) == str(e.text)]
    try:
        fakten = parse_llm((ask or ask_model)(settings,
                                              llm_prompt(nachricht, bekannt, gespraech)))
    except Exception:
        return []
    with profile_lock(store):
        if not enabled() or store.revision() != version:
            return []
        return store_facts(store, [f for f in fakten if scrub(f.text, secrets) == f.text],
                           expected_revision=version)


_LEARNING_JOBS: queue.Queue[Callable[[], None]] = queue.Queue(maxsize=32)
_LEARNING_START = threading.Lock()
_LEARNING_THREADS = 0


def _learning_worker() -> None:
    while True:
        job = _LEARNING_JOBS.get()
        try:
            with contextlib.suppress(Exception):
                job()
        finally:
            _LEARNING_JOBS.task_done()


def schedule_learning(job: Callable[[], None]) -> bool:
    global _LEARNING_THREADS
    with _LEARNING_START:
        while _LEARNING_THREADS < 4:
            thread = threading.Thread(target=_learning_worker, daemon=True,
                                      name=f"aquaticy-gedaechtnis-{_LEARNING_THREADS}")
            try:
                thread.start()
            except RuntimeError:
                break
            _LEARNING_THREADS += 1
        if not _LEARNING_THREADS:
            return False
    try:
        _LEARNING_JOBS.put_nowait(job)
        return True
    except queue.Full:
        return False


# -- 15.5.5: Fragen nach dem eigenen Wissen ueber den Nutzer -------------------------------------
_SELBST_FRAGEN: list[tuple[str, re.Pattern[str]]] = [
    ("name", re.compile(r"(?i)^(?:(?:und\s+)?(?:wie\s+hei(?:ß|ss)e\s+ich|wie\s+ist\s+mein\s+"
                        r"name|wei(?:ß|ss)t\s+du(?:\s+noch)?,?\s+wie\s+ich\s+hei(?:ß|ss)e|"
                        r"kennst\s+du\s+meinen\s+namen|what'?s\s+my\s+name|what\s+is\s+my\s+"
                        r"name|do\s+you\s+know\s+my\s+name))\s*[?!.]*$")),
    ("wohnort", re.compile(r"(?i)^(?:wo\s+wohne\s+ich|wo\s+lebe\s+ich|where\s+do\s+i\s+"
                           r"live)\s*[?!.]*$")),
    ("alter", re.compile(r"(?i)^(?:wie\s+alt\s+bin\s+ich|how\s+old\s+am\s+i)\s*[?!.]*$")),
    ("geburtstag", re.compile(r"(?i)^(?:wann\s+habe\s+ich\s+geburtstag|wann\s+ist\s+mein\s+"
                              r"geburtstag|when\s+is\s+my\s+birthday)\s*[?!.]*$")),
]


def self_question(text: str) -> str:
    """Welche Angabe ueber sich fragt der Nutzer ab? ("" = keine eindeutige Frage)."""
    text = " ".join(str(text or "").split())
    for art, muster in _SELBST_FRAGEN:
        if muster.match(text):
            return art
    return ""


def self_answer(text: str, store: Any, language: str = "de") -> str:
    """Ein ganzer Satz aus dem Gedaechtnis ("Du heißt Louis.") -- oder "" (dann das Modell).

    Nur fuer eindeutige Fragen und nur, wenn die Angabe gespeichert ist. Fehlt sie, fragt
    das Modell nach -- wie bisher.
    """
    art = self_question(text)
    if not art or store is None:
        return ""
    fakten = {str(e.topic or "").casefold().split(":", 1)[-1]: str(e.text or "")
              for e in person_entries(store, limit=None)
              if str(e.topic or "").casefold().startswith(f"{PERSON}:")}
    en = language == "en"
    if art == "name":
        treffer = re.match(r"^Der Nutzer heißt (.+?)\.?$", fakten.get("name", ""))
        if not treffer:
            return ""
        name = treffer[1]
        anrede = re.match(r"^Möchte mit „(.+?)“ angesprochen werden\.$", fakten.get("anrede", ""))
        if en:
            return f"Your name is {name}." + (f" I call you {anrede[1]}." if anrede else "")
        return f"Du heißt {name}." + (f" Ich nenne dich {anrede[1]}." if anrede else "")
    if art == "wohnort":
        treffer = re.match(r"^Wohnt in (.+?)\.?$", fakten.get("wohnort", ""))
        if not treffer:
            return ""
        return f"You live in {treffer[1]}." if en else f"Du wohnst in {treffer[1]}."
    datum = birth_date(fakten.get("geburtsdatum", ""))
    if art == "alter":
        if datum is not None:
            alter = age_on(datum)
            return (f"You are {alter} years old (born on {datum:%d.%m.%Y})." if en else
                    f"Du bist {alter} Jahre alt. Du bist am {datum:%d.%m.%Y} geboren.")
        return ""
    if art == "geburtstag":
        if datum is not None:
            return (f"Your birthday is on {datum:%d.%m.}." if en else
                    f"Du hast am {datum:%d.%m.} Geburtstag.")
        treffer = re.match(r"^Hat am (.+?) Geburtstag\.$", fakten.get("geburtstag", ""))
        if treffer:
            return (f"Your birthday is on {treffer[1]}." if en else
                    f"Du hast am {treffer[1]} Geburtstag.")
    return ""
