"""Aquaticy Standard in den meistgesprochenen Sprachen: erkennen, verstehen, antworten (16.4.2).

Ohne Sprachmodell gibt es keine Uebersetzung. Stattdessen kennt jede Sprache eine kleine Liste
typischer Woerter (Gruss, Dank, Wetter, Uhrzeit, Datum, Fragen nach Wissen) und feste Antworten.
Die Daten stehen in `aquaticy/weltsprachen_daten.py`. Erkannt wird ueber diese Woerter und die
Schrift (Kyrillisch, Arabisch, Devanagari ...). Deutsch und Englisch kennt Aquaticy Standard
ausserdem viel genauer -- dort bleibt der bisherige Weg (aquaticy/standard.py).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from aquaticy.weltsprachen_daten import DATEN

LISTEN = ("hallo", "info", "danke", "tschuess", "wiegehts", "wetter", "zeit", "datum", "heute",
          "morgen", "wiki", "stopp", "krise", "endungen", "vorsilben", "zeichen")
ANTWORTEN = ("intro", "danke", "tschuess", "wiegehts", "zeit", "datum", "ort", "nichts",
             "rueckfall", "krise")
#: Diese Listen zaehlen fuer die Erkennung. "stopp" (kleine Woerter wie "in") nicht: die teilen
#: sich zu viele Sprachen.
ERKENNEN = ("hallo", "info", "danke", "tschuess", "wiegehts", "wetter", "zeit", "datum", "heute",
            "morgen", "krise")
#: Ohne passendes Wort entscheidet die Schrift -- wo eine Schrift fast nur eine Sprache hat.
SCHRIFT_SPRACHE = {
    "cyrillic": "ru", "arabic": "ar", "devanagari": "hi", "bengali": "bn", "han": "zh",
    "kana": "ja", "hangul": "ko", "thai": "th", "greek": "el", "hebrew": "he", "georgian": "ka",
    "armenian": "hy", "ethiopic": "am", "tamil": "ta", "telugu": "te", "kannada": "kn",
    "malayalam": "ml", "gujarati": "gu", "gurmukhi": "pa", "oriya": "or", "sinhala": "si",
    "khmer": "km", "lao": "lo", "myanmar": "my",
}
_SCHRIFT_NAMEN = {"CJK": "han", "HIRAGANA": "kana", "KATAKANA": "kana", "HANGUL": "hangul"}


@dataclass(frozen=True)
class Sprache:
    """Eine Sprache: Woerter zum Erkennen und feste Antworten."""

    code: str
    name: str
    wiki: str
    schriften: tuple[str, ...]
    ohne_leerzeichen: bool
    listen: dict[str, tuple[str, ...]]
    antworten: dict[str, str]


def norm(text: str) -> str:
    """Kleinbuchstaben, ohne Satzzeichen, einfache Leerzeichen -- Zeichen jeder Schrift bleiben."""
    text = unicodedata.normalize("NFKC", str(text or "")).replace("İ", "i").replace("’", "'")
    text = text.replace("`", "'").casefold()
    zeichen = [c if unicodedata.category(c)[0] in "LMN" or c in "'-" else " " for c in text]
    return " ".join("".join(zeichen).split()).strip("'- ")


def schrift(text: str) -> str:
    """Die Schrift, in der die meisten Buchstaben stehen ("latin", "cyrillic", "han" ...)."""
    zaehler: dict[str, int] = {}
    for c in str(text or ""):
        if not c.isalpha():
            continue
        try:
            wort = unicodedata.name(c).split(" ")[0]
        except ValueError:
            continue
        name = _SCHRIFT_NAMEN.get(wort, wort.lower())
        zaehler[name] = zaehler.get(name, 0) + 1
    if zaehler.get("kana"):
        return "kana"
    return max(zaehler, key=lambda k: zaehler[k]) if zaehler else ""


def _teile(wert: str) -> tuple[str, ...]:
    return tuple(t for t in (norm(s) if "{x}" not in s else s.strip().casefold()
                             for s in wert.split(";")) if t)


def lesen(daten: str) -> dict[str, Sprache]:
    """Liest den Text aus weltsprachen_daten.py (Format dort beschrieben)."""
    sprachen: dict[str, Sprache] = {}
    roh: list[tuple[str, str, dict[str, str], dict[str, str]]] = []
    letzter = ""
    for zeile in daten.splitlines():
        if not zeile.strip() or zeile.lstrip().startswith("#"):
            continue
        if zeile.startswith("@"):
            kopf, _, rest = zeile[1:].partition(" ")
            roh.append((kopf.strip(), rest, {}, {}))
            letzter = ""
            continue
        if not roh:
            raise ValueError(f"Zeile vor der ersten Sprache: {zeile[:40]}")
        felder = roh[-1][2]
        if zeile.startswith("  ") and letzter:
            felder[letzter] += " " + zeile.strip()
            continue
        name, gleich, wert = zeile.partition("=")
        if not gleich:
            raise ValueError(f"{roh[-1][0]}: Zeile ohne '=': {zeile[:40]}")
        letzter = name.strip()
        felder[letzter] = wert.strip()
    for code, kopf, felder, _ in roh:
        teile = [t.strip() for t in kopf.split("|")]
        optionen = dict(t.split("=", 1) for t in teile[1:] if "=" in t)
        listen = {n: _teile(felder.get(n, "")) for n in LISTEN}
        antworten = {n: felder[f"A.{n}"] for n in ANTWORTEN if f"A.{n}" in felder}
        sprachen[code] = Sprache(code, teile[0], optionen.get("wiki", code),
                                 tuple(optionen.get("schrift", "latin").split(",")),
                                 "nospace" in teile, listen, antworten)
    return sprachen


SPRACHEN = lesen(DATEN)
#: Jede Wikipedia, die Aquaticy Standard abfragen darf.
WIKI_HOSTS = tuple(sorted({f"{s.wiki}.wikipedia.org" for s in SPRACHEN.values()}))


def _hat(text: str, satz: str, ohne_leer: bool) -> bool:
    if "{x}" in satz:
        return _wiki_muster(satz, ohne_leer).fullmatch(text) is not None
    return satz in text if ohne_leer else f" {satz} " in f" {text} "


def punkte(text: str, sprache: Sprache) -> int:
    """Wie viele Zeichen von *text* nach dieser Sprache aussehen (laengere Treffer zaehlen mehr)."""
    gesamt = 0
    for liste in ERKENNEN:
        for satz in sprache.listen[liste]:
            if _hat(text, satz, sprache.ohne_leerzeichen):
                gesamt += len(satz)
    for satz in sprache.listen["wiki"]:
        if _hat(text, satz, sprache.ohne_leerzeichen):
            gesamt += len(satz.replace("{x}", ""))
    # Typische Buchstaben ("ї" nur im Ukrainischen, "ș" im Rumänischen) helfen bei Verwandten --
    # aber nur, wenn schon ein Wort passt ("Crêpes" allein ist kein Französisch).
    if gesamt:
        gesamt += 3 * sum(1 for z in sprache.listen["zeichen"] if z in text)
    return gesamt


#: Haeufige kleine Woerter. In lateinischer Schrift muss eine andere Sprache deutlich mehr
#: Belege haben als diese -- sonst bleibt es bei Deutsch (oder Englisch). Sonst wuerde
#: "Gibt es morgen Regen in Köln?" wegen "morgen" und "regen" Niederlaendisch.
_DEUTSCH = """der die das den dem des ein eine einen einem einer und oder ist sind war
        wird werden hat haben habe ich du er sie wir ihr mir mich dir dich mein meine dein deine
        nicht kein keine wie was wo wann warum wer welche welcher welches gibt mit von zu zum zur
        auf aus bei nach für über unter im am vom kann kannst soll muss bitte auch noch schon
        sehr heute morgen ja nein man mal doch aber dass denn"""
_ENGLISCH = """the an and or is are was were be been do does did have has had i you he
        she it we they me my your what how where when why who which can could would should will
        not no with of to for from on at by this that there please today tomorrow like look
        going get tell show about"""
FUNKTION = {"de": frozenset(_DEUTSCH.split()), "en": frozenset(_ENGLISCH.split())}


def _funktion(gefaltet: str, code: str) -> int:
    return sum(len(w) for w in gefaltet.split() if w in FUNKTION[code])


def sprache_von(text: str) -> str:
    """Die Sprache einer Nachricht -- oder "" (dann bleibt es beim deutschen Weg).

    Bei Gleichstand gewinnt die Sprache, die weiter oben steht (Deutsch zuerst, dann nach Zahl
    der Sprecher). Typische Buchstaben zaehlen nur, wenn schon ein Wort passt.
    """
    gefaltet = norm(text)
    art = schrift(text)
    if not gefaltet or not art:
        return ""
    beste, beste_punkte = "", 0
    for sprache in SPRACHEN.values():
        if art not in sprache.schriften:
            continue
        zahl = punkte(gefaltet, sprache)
        if zahl > beste_punkte:
            beste, beste_punkte = sprache.code, zahl
    if art == "latin":
        deutsch, englisch = _funktion(gefaltet, "de"), _funktion(gefaltet, "en")
        if beste not in ("de", "en") and beste_punkte <= 2 * max(deutsch, englisch):
            beste = ""
        if not beste and max(deutsch, englisch) >= 3:
            beste = "de" if deutsch >= englisch else "en"
    return beste or SCHRIFT_SPRACHE.get(art, "")


def krise_sprache(text: str) -> str:
    """Die Sprache, deren Worte fuer eine Krise in *text* stehen -- unabhaengig von der Erkennung.

    Hilfe darf nie an einer falsch erkannten Sprache scheitern.
    """
    gefaltet = norm(text)
    art = schrift(text)
    for sprache in SPRACHEN.values():
        if art in sprache.schriften and sprache.antworten.get("krise") and any(
                _hat(gefaltet, satz, sprache.ohne_leerzeichen)
                for satz in sprache.listen["krise"]):
            return sprache.code
    return ""


_MUSTER_CACHE: dict[tuple[str, bool], re.Pattern[str]] = {}


def _wiki_muster(satz: str, ohne_leer: bool) -> re.Pattern[str]:
    schluessel = (satz, ohne_leer)
    if schluessel not in _MUSTER_CACHE:
        vorn, _, hinten = satz.partition("{x}")
        vorn, hinten = norm(vorn), norm(hinten)
        lueck = "" if ohne_leer else r"\s+"
        teile = [re.escape(vorn) + lueck if vorn else "", r"(?P<x>.+?)",
                 lueck + re.escape(hinten) if hinten else ""]
        _MUSTER_CACHE[schluessel] = re.compile("".join(teile))
    return _MUSTER_CACHE[schluessel]


def thema(text: str, sprache: Sprache) -> str:
    """Das Thema einer Wissensfrage ("qué es la fotosíntesis" -> "fotosíntesis") -- oder ""."""
    gefaltet = norm(text)
    for satz in sprache.listen["wiki"]:
        treffer = _wiki_muster(satz, sprache.ohne_leerzeichen).fullmatch(gefaltet)
        if treffer:
            worte = treffer.group("x").split()
            # Artikel und kleine Woerter vorn gehoeren nicht zum Thema ("la fotosíntesis").
            while len(worte) > 1 and worte[0] in sprache.listen["stopp"]:
                worte = worte[1:]
            return " ".join(worte).strip()
    return ""


def enthaelt(text: str, sprache: Sprache, liste: str) -> bool:
    gefaltet = norm(text)
    return any(_hat(gefaltet, satz, sprache.ohne_leerzeichen) for satz in sprache.listen[liste])


def nur_aus(text: str, sprache: Sprache, listen: tuple[str, ...]) -> bool:
    """Besteht *text* nur aus Woertern dieser Listen (und kleinen Fuellwoertern)?"""
    rest = norm(text)
    saetze = sorted({s for n in (*listen, "stopp") for s in sprache.listen[n] if "{x}" not in s},
                    key=len, reverse=True)
    for satz in saetze:
        if sprache.ohne_leerzeichen:
            rest = rest.replace(satz, " ")
        else:
            rest = f" {rest} ".replace(f" {satz} ", " ")
            rest = f" {rest} ".replace(f" {satz} ", " ")
    return not rest.strip(" -'")


def ort_aus(text: str, sprache: Sprache, listen: tuple[str, ...] = ("wetter",)) -> str:
    """Der Ort einer Frage: alles, was nach Wetter- (oder Uhrzeit-), Tages- und Fuellwoertern
    uebrig ist."""
    weg = [s for n in (*listen, "heute", "morgen", "stopp", "hallo") for s in sprache.listen[n]]
    if sprache.ohne_leerzeichen:
        rest = unicodedata.normalize("NFKC", str(text or ""))
        for satz in sorted(weg, key=len, reverse=True):
            rest = re.sub(re.escape(satz), " ", rest, flags=re.IGNORECASE)
        rest = "".join(c if unicodedata.category(c)[0] in "LMN" or c in " -" else " "
                       for c in rest)
        worte = []
        for wort in rest.split():
            # Koreanisch: Endungen wie "의" oder "에서" haengen am Wort.
            for endung in sprache.listen["endungen"]:
                if len(wort) > len(endung) and wort.endswith(endung):
                    wort = wort[: len(wort) - len(endung)]
                    break
            worte.append(wort)
        return " ".join(worte)[:60]
    worte = []
    for roh in unicodedata.normalize("NFKC", str(text or "")).split():
        stueck = roh.strip("?!.,;:¿¡«»“”\"()[]،؟。、")
        if "'" in stueck.replace("’", "'") and stueck[:1].isupper():
            stueck = stueck.replace("’", "'").split("'")[0]
        for endung in sprache.listen["endungen"]:
            if len(stueck) > len(endung) + 1 and norm(stueck).endswith(endung):
                stueck = stueck[: len(stueck) - len(endung)]
                break
        if stueck:
            worte.append(stueck)
    gefaltet = [norm(w) for w in worte]
    raus = [False] * len(worte)
    for satz in sorted(weg, key=lambda s: -len(s.split())):
        teile = satz.split()
        for i in range(len(gefaltet) - len(teile) + 1):
            if gefaltet[i:i + len(teile)] == teile:
                for j in range(i, i + len(teile)):
                    raus[j] = True
    return " ".join(w for w, r in zip(worte, raus, strict=True) if not r)[:60]


__all__ = [
    "SPRACHEN",
    "WIKI_HOSTS",
    "Sprache",
    "enthaelt",
    "krise_sprache",
    "lesen",
    "norm",
    "nur_aus",
    "ort_aus",
    "schrift",
    "sprache_von",
    "thema",
]
