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

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

PERSON = "person"
MAX_VALUE = 60
MAX_FACT = 200
MAX_LLM_FACTS = 5
MAX_PERSON_FACTS = 40

# Plaetze mit genau einem gueltigen Wert: Ein neuer Wert ersetzt den alten.
SINGLE = frozenset({"name", "anrede", "wohnort", "herkunft", "beruf", "arbeitgeber", "alter",
                    "geburtstag", "ernaehrung", "schule", "studium"})


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
    r"(?i)\b(krank\w*|krankheit\w*|diagnose\w*|depress\w*|therap\w*|medikament\w*|"
    r"allerg\w*|diabet\w*|krebs|schwanger\w*|behinder\w*|psych\w*|adhs|autis\w*|"
    r"religi\w*|christ\w*|muslim\w*|moslem\w*|jud(?:e|in|en)|jüd\w*|atheist\w*|"
    r"kirche\w*|moschee\w*|partei\w*|w(?:ä|ae)hle\w*|afd|spd|cdu|csu|fdp|"
    r"schwul\w*|lesbisch\w*|bisexuell\w*|transgender|trans\b|queer|sexuell\w*|"
    r"gewerkschaft\w*|vorstrafe\w*|knast|gefängnis\w*|verurteilt\w*|ethni\w*|hautfarbe|"
    r"passwort\w*|kennwort\w*|password|pin\b|iban|kreditkart\w*|tan\b|token|"
    r"sick|illness|disease|religion|church|gay|lesbian|ssn)\b")
_GEHEIM = re.compile(r"(?i)(?:\b[A-Z]{2}\d{2}(?:\s?\w{4}){3,7}\b|\b(?:\d[ -]?){13,19}\b|"
                     r"ghp_|github_pat_|sk-[a-z0-9]|nvapi-|xox[bp]-|AKIA[0-9A-Z]{8})")


def sensitive(text: str) -> bool:
    """Gehoert das zu den Dingen, die nur auf ausdrueckliche Bitte in den Speicher duerfen?"""
    return bool(_SENSIBEL.search(text or "") or _GEHEIM.search(text or ""))


_NICHT_MERKEN = re.compile(
    r"(?i)\b(?:merk\s+dir\s+(?:das|es|dies)\s+nicht|nicht\s+(?:merken|speichern|"
    r"abspeichern|notieren)|vergiss\s+(?:das|es)\s+(?:gleich|wieder|sofort)|"
    r"don'?t\s+(?:remember|save|store)\s+(?:this|that|it))\b")


def opted_out(text: str) -> bool:
    """Will der Nutzer, dass diese Nachricht nicht gemerkt wird?"""
    return bool(_NICHT_MERKEN.search(text or ""))


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
    return re.sub(r"[^a-z0-9äöüß]+", "-", wert.casefold()).strip("-")[:40]


_FRAGE = re.compile(r"(?i)^(?:wie|was|wo|wer|wann|warum|wieso|weißt|weisst|kennst|"
                    r"heiße\s+ich|heisse\s+ich|do|does|what|who|where)\b")


def _saetze(text: str) -> list[str]:
    """Aussagesaetze -- Fragen ("wie heisse ich?") und Wenn-Saetze zaehlen nicht."""
    saetze = []
    for satz in re.split(r"(?<=[.!?\n])\s+", str(text or "")):
        satz = satz.strip()
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
                           r"ich\s+lebe\s+(?:jetzt\s+)?(?:in|im)|ich\s+bin\s+(?:jetzt\s+)?nach"
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
    ("geburtstag", re.compile(_I + r"(?:ich\s+habe\s+am|mein\s+geburtstag\s+ist\s+(?:am)?|"
                              r"my\s+birthday\s+is(?:\s+on)?)\s*(?P<w>[0-9]{1,2}\.\s?(?:[0-9]"
                              r"{1,2}\.?|[A-Za-zäöü]+)|[A-Za-z]+\s+\d{1,2})", re.IGNORECASE)),
    ("ernaehrung", re.compile(_I + r"(?:ich\s+bin|ich\s+lebe|i'?m|i\s+am)\s+(?:seit\s+\w+\s+)?"
                              r"(?P<w>vegetarier(?:in)?|veganer(?:in)?|vegan|vegetarisch|"
                              r"vegetarian|pescetarier(?:in)?)\b", re.IGNORECASE)),
    ("mag_nicht", re.compile(_I + r"(?:ich\s+mag\s+(?:keine?n?|kein)|ich\s+hasse|"
                             r"ich\s+kann\s+\S+\s+nicht\s+leiden|i\s+hate|i\s+don'?t\s+like|"
                             r"i\s+dislike)\s+(?P<w>[^,.!?\n]+)", re.IGNORECASE)),
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
        return Fact("alter", f"Ist {alter} Jahre alt (Stand {date.today():%m/%Y}).")
    if slot == "geburtstag":
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
                wert = _wert(treffer.group("w"), woerter)
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
    treffer = _VERGISS.search(text or "")
    if not treffer:
        return ""
    wert = re.sub(r"(?i)^(?:ich|i)\s+", "", treffer.group("w").strip())
    return wert[:80]


# -- Ablegen mit einem Stand je Sache ------------------------------------------------------------
def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", " ", (text or "").casefold()).strip()


def person_entries(store: Any, limit: int = MAX_PERSON_FACTS) -> list[Any]:
    """Alle Eintraege ueber den Nutzer (Thema "person" oder "person:..."), aelteste zuerst."""
    try:
        eintraege = store.all_entries(limit=2000)
    except Exception:
        return []
    passend = [e for e in eintraege
               if str(e.topic or "").casefold().split(":", 1)[0].strip() == PERSON]
    return list(reversed(passend[:limit]))


_ALTER_PLATZ = {
    "name": re.compile(r"(?i)\bhei(?:ß|ss)t\b|\bname\s+ist\b"),
    "wohnort": re.compile(r"(?i)\bwohnt\b|\blebt\s+in\b"),
    "beruf": re.compile(r"(?i)\barbeitet\s+als\b|\bvon\s+beruf\b"),
    "alter": re.compile(r"(?i)\bjahre\s+alt\b"),
}


def store_facts(store: Any, facts: list[Fact]) -> list[Fact]:
    """Legt *facts* ab: ersetzt den alten Stand, hebt Gegenteile auf, nichts doppelt.

    Returns: die Fakten, die wirklich neu oder geaendert sind.
    """
    if store is None or not facts:
        return []
    try:
        vorhanden = list(store.all_entries(limit=2000))
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
        for eintrag in vorhanden:
            thema = str(eintrag.topic or "").casefold()
            if _norm(eintrag.text) == _norm(fakt.text):
                gleich = True
                continue
            if thema == fakt.topic.casefold() and einzel:
                store.forget(eintrag.id)
            elif (thema == PERSON and fakt.slot in _ALTER_PLATZ
                  and _ALTER_PLATZ[fakt.slot].search(str(eintrag.text or ""))):
                # Von Hand oder vom Modell abgelegt ("Heisst Jonas."): auch das ist der Platz.
                store.forget(eintrag.id)
            elif gegenteil and thema == f"{PERSON}:{gegenteil}":
                store.forget(eintrag.id)
        if gleich:
            continue
        try:
            eintrag = store.remember(fakt.text, fakt.topic)
        except Exception:
            continue
        vorhanden.append(eintrag)
        neu.append(fakt)
    return neu


def forget_matching(store: Any, wunsch: str) -> list[str]:
    """Loescht Eintraege ueber den Nutzer, die zu *wunsch* passen. Returns: geloeschte Texte."""
    woerter = [w for w in _norm(wunsch).split() if len(w) > 2 and w not in (
        "mag", "ich", "bin", "habe", "nicht", "dass", "the", "like", "and")]
    if store is None or not woerter:
        return []
    weg = []
    for eintrag in person_entries(store, limit=2000):
        text = _norm(f"{eintrag.text} {eintrag.topic}")
        if all(w in text for w in woerter) and store.forget(eintrag.id):
            weg.append(str(eintrag.text))
    return weg


# -- Mit dem schnellen Modell: Beilaeufiges ------------------------------------------------------
_ICH = re.compile(r"(?i)\b(?:ich|mein\w*|mir|mich|wir|unser\w*|i|i'm|i've|my|me|we|our)\b")
ARTEN = frozenset({"name", "anrede", "wohnort", "herkunft", "beruf", "arbeitgeber", "alter",
                   "geburtstag", "ernaehrung", "schule", "studium", "mag", "mag_nicht",
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

Bekannt:
%(bekannt)s

Nachricht des Nutzers:
<<<
%(nachricht)s
>>>

Antworte nur mit JSON: {"fakten": [{"art": "...", "text": "..."}]}
art ist eins von: %(arten)s. text ist ein kurzer deutscher Satz in der dritten Person,
zum Beispiel "Mag Klettern." oder "Wohnt in Bremen.". Nichts gefunden: {"fakten": []}"""


def worth_asking(text: str) -> bool:
    """Lohnt der Modellaufruf? Nur bei Ich-Bezug, ohne Opt-out, nicht bei reinen Fragen."""
    text = (text or "").strip()
    if len(text) < 12 or opted_out(text) or not _ICH.search(text):
        return False
    return any(not s.endswith("?") for s in re.split(r"(?<=[.!?\n])\s+", text) if s.strip())


def llm_prompt(nachricht: str, bekannt: list[str]) -> str:
    return LLM_PROMPT % {
        "bekannt": "\n".join(f"- {t}" for t in bekannt[:MAX_PERSON_FACTS]) or "- (noch nichts)",
        "nachricht": nachricht[:1500].replace(">>>", "> > >"),
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
        text = " ".join(str(eintrag.get("text") or "").split())[:MAX_FACT]
        if art not in ARTEN or len(text) < 4 or sensitive(text) or "http" in text.casefold():
            continue
        if not text.endswith((".", "!")):
            text += "."
        slot = art if art in SINGLE else f"{art}:{_schluessel(text)}"
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
            settings, enforce=False, model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300, timeout=25.0, **settings.fast_kwargs_for(model))
    return str(antwort.choices[0].message.content or "")


def cloud_model(settings: Any) -> bool:
    """Laeuft das schnelle Modell in der Cloud? Lokal bleibt es beim festen Weg."""
    from aquaticy.config import provider_of

    model = str(getattr(settings, "effective_subagent_model", "") or settings.model)
    return provider_of(model) not in ("ollama", "ollama_chat", "llamacpp", "hosted_vllm", "")


def learn_with_model(settings: Any, store: Any, nachricht: str) -> list[Fact]:
    """Fragt das schnelle Modell nach Beilaeufigem und legt es ab. Fehler bleiben still."""
    if store is None or not worth_asking(nachricht):
        return []
    bekannt = [str(e.text) for e in person_entries(store)]
    try:
        fakten = parse_llm(ask_model(settings, llm_prompt(nachricht, bekannt)))
    except Exception:
        return []
    return store_facts(store, fakten)
