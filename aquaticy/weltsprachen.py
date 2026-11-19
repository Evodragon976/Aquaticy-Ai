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
    # Nullbreiten-Zeichen (ZWNJ/ZWJ) verbinden: "می" + ZWNJ + "خواهم" ist dasselbe Wort wie
    # "میخواهم".
    text = text.replace("`", "'").replace("\u200c", "").replace("\u200d", "").casefold()
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


def schriften_in(text: str) -> set[str]:
    """Alle Schriften, in denen Buchstaben stehen ("Python是什么" -> latin und han)."""
    arten: set[str] = set()
    for c in str(text or ""):
        if c.isalpha():
            try:
                wort = unicodedata.name(c).split(" ")[0]
            except ValueError:
                continue
            arten.add(_SCHRIFT_NAMEN.get(wort, wort.lower()))
    return arten


def _teile(wert: str) -> tuple[str, ...]:
    teile: list[str] = []
    for s in wert.split(";"):
        formen = [norm(s), norm(s.replace("\u200c", " "))] if "{x}" not in s else [
            s.strip().casefold()]
        # Wer kein ZWNJ tippen kann, schreibt oft ein Leerzeichen ("می خواهم").
        teile += [f for f in dict.fromkeys(formen) if f and f not in teile]
    return tuple(teile)


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


def _stellen(text: str, satz: str, ohne_leer: bool) -> list[tuple[int, int]]:
    """Wo *satz* in *text* steht (Anfang, Ende) -- ohne Leerzeichen als Teilwort, sonst ganz."""
    stellen, start = [], 0
    rand = "" if ohne_leer else " "
    voll = f"{rand}{text}{rand}"
    such = f"{rand}{satz}{rand}"
    while (i := voll.find(such, start)) >= 0:
        # Die Leerzeichen am Rand gehoeren nicht dazu -- sonst "ueberlappen" Nachbarwoerter.
        stellen.append((i + len(rand), i + len(such) - len(rand)))
        start = i + max(1, len(such) - len(rand))
    return stellen


def treffer(text: str, sprache: Sprache, listen: tuple[str, ...]) -> list[tuple[str, str]]:
    """Die Woerter dieser Listen in *text*, laengste zuerst, ohne Ueberlappung.

    "kumusta ka diha" zaehlt so einmal ganz -- nicht noch einmal als "kumusta" und "kumusta ka".
    """
    kandidaten = sorted(((len(satz), liste, satz) for liste in listen
                         for satz in sprache.listen[liste] if "{x}" not in satz),
                        key=lambda k: -k[0])
    belegt: list[tuple[int, int]] = []
    gefunden: list[tuple[str, str]] = []
    for _, liste, satz in kandidaten:
        for anfang, ende in _stellen(text, satz, sprache.ohne_leerzeichen):
            if all(ende <= a or anfang >= e for a, e in belegt):
                belegt.append((anfang, ende))
                gefunden.append((liste, satz))
    return gefunden


def punkte(text: str, sprache: Sprache) -> int:
    """Wie viele Zeichen von *text* nach dieser Sprache aussehen (laengere Treffer zaehlen mehr)."""
    gesamt = sum(len(satz) for _, satz in treffer(text, sprache, ERKENNEN))
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
        going get tell show about a flip roll coin dice joke leap year convert until days many
        much whats"""
FUNKTION = {"de": frozenset(_DEUTSCH.split()), "en": frozenset(_ENGLISCH.split())}


def _funktion(gefaltet: str, code: str) -> int:
    return sum(len(w) for w in gefaltet.split() if w in FUNKTION[code])


def _ganz_belegt(gefaltet: str, sprache: Sprache) -> bool:
    """Besteht der Text nur aus Woertern dieser Sprache, mit mindestens einer Wendung aus
    mehreren Woertern? Dann ist "god morgen" Daenisch, obwohl "morgen" auch deutsch ist."""
    gefunden = treffer(gefaltet, sprache, ERKENNEN)
    return any(" " in satz for _, satz in gefunden) and nur_aus(gefaltet, sprache, ERKENNEN)


def _wiki_belegt(gefaltet: str, sprache: Sprache) -> bool:
    """Passt eine Wissensfrage dieser Sprache ganz, und stehen im Thema keine deutschen oder
    englischen kleinen Woerter? Dann ist "wie was rembrandt" Niederlaendisch."""
    gesucht = thema(gefaltet, sprache)
    return bool(gesucht) and not any(
        w in FUNKTION["de"] or w in FUNKTION["en"] for w in gesucht.split())


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
    # Ein Name in lateinischer Schrift ("ChatGPT क्या है") macht den Satz nicht lateinisch:
    # Jede Schrift im Text bringt ihre Sprachen mit.
    arten = schriften_in(text)
    for sprache in SPRACHEN.values():
        if not arten & set(sprache.schriften):
            continue
        zahl = punkte(gefaltet, sprache)
        if zahl > beste_punkte:
            beste, beste_punkte = sprache.code, zahl
    if art == "latin":
        deutsch, englisch = _funktion(gefaltet, "de"), _funktion(gefaltet, "en")
        if (beste not in ("", "de", "en") and "latin" in SPRACHEN[beste].schriften
                and beste_punkte <= 2 * max(deutsch, englisch)
                and not _ganz_belegt(gefaltet, SPRACHEN[beste])
                and not _wiki_belegt(gefaltet, SPRACHEN[beste])):
            beste = ""
        if not beste and max(deutsch, englisch) >= 3:
            beste = "de" if deutsch >= englisch else "en"
    if not beste and art != "latin":
        # Kein Stichwort: Buchstaben, die nur wenige Sprachen haben ("ے" Urdu, "ї" Ukrainisch,
        # "ә" Kasachisch), sagen mehr als die Schrift allein. In lateinischer Schrift nicht --
        # "Crêpes" allein ist kein Französisch.
        zahl_beste = 0
        for sprache in SPRACHEN.values():
            if art in sprache.schriften:
                zahl = sum(gefaltet.count(z) for z in sprache.listen["zeichen"])
                if zahl > zahl_beste:
                    beste, zahl_beste = sprache.code, zahl
    return beste or SCHRIFT_SPRACHE.get(art, "")


def krise_sprache(text: str) -> str:
    """Die Sprache, deren Worte fuer eine Krise in *text* stehen -- unabhaengig von der Erkennung.

    Hilfe darf nie an einer falsch erkannten Sprache scheitern.
    """
    gefaltet = norm(text)
    art = schrift(text)
    # Die Schrift zaehlt hier nicht: Serbisch steht oft in lateinischer Schrift ("ubijem se").
    for sprache in sorted(SPRACHEN.values(), key=lambda s: art not in s.schriften):
        if sprache.antworten.get("krise") and any(
                _hat(gefaltet, satz, sprache.ohne_leerzeichen)
                for satz in sprache.listen["krise"]):
            return sprache.code
    return ""


_MUSTER_CACHE: dict[tuple[str, bool], re.Pattern[str]] = {}


def _wiki_muster(satz: str, ohne_leer: bool) -> re.Pattern[str]:
    schluessel = (satz, ohne_leer)
    if schluessel not in _MUSTER_CACHE:
        roh_vorn, _, roh_hinten = satz.partition("{x}")
        vorn, hinten = norm(roh_vorn), norm(roh_hinten)
        # "{x}manta" (Quechua) oder "{x}-ийн" (Mongolisch): die Endung haengt direkt am Thema.
        lueck_vorn = r"\s+" if not ohne_leer and roh_vorn.endswith(" ") else ""
        lueck_hinten = r"\s+" if not ohne_leer and roh_hinten.startswith(" ") else ""
        teile = [re.escape(vorn) + lueck_vorn if vorn else "", r"(?P<x>.+?)",
                 lueck_hinten + re.escape(hinten) if hinten else ""]
        _MUSTER_CACHE[schluessel] = re.compile("".join(teile))
    return _MUSTER_CACHE[schluessel]


def thema(text: str, sprache: Sprache) -> str:
    """Das Thema einer Wissensfrage ("qué es la fotosíntesis" -> "fotosíntesis") -- oder ""."""
    gefaltet = norm(text)
    # Laengstes Muster zuerst: "co je to {x}" vor "co je {x}" -- sonst ist "to" Teil des Themas.
    for satz in sorted(sprache.listen["wiki"], key=lambda s: -len(s.replace("{x}", ""))):
        treffer = _wiki_muster(satz, sprache.ohne_leerzeichen).fullmatch(gefaltet)
        if treffer:
            worte = treffer.group("x").split()
            # Artikel und kleine Woerter vorn gehoeren nicht zum Thema ("la fotosíntesis").
            while len(worte) > 1 and worte[0] in sprache.listen["stopp"]:
                worte = worte[1:]
            return " ".join(worte).strip(" -'")
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


def _abdecken(text: str, saetze: list[str]) -> str:
    """Ersetzt bekannte Woerter durch Leerzeichen -- so, dass moeglichst viele Zeichen wegfallen.

    Gierig von links waere "今天气温" (heute Temperatur) zu "今|天气|温" geworden.
    """
    # Zeichen fuer Zeichen klein -- "ß".casefold() waere "ss" und verschoebe die Stellen.
    klein = "".join(z.lower() if len(z.lower()) == 1 else z for z in text)
    laenge = len(klein)
    kandidaten = sorted({s.lower() for s in saetze if s}, key=len, reverse=True)
    # beste[i] = (abgedeckte Zeichen ab i, -Zahl der Woerter, naechster Schritt)
    beste: list[tuple[int, int, int, bool]] = [(0, 0, laenge, False)] * (laenge + 1)
    for i in range(laenge - 1, -1, -1):
        wahl = (beste[i + 1][0], beste[i + 1][1], i + 1, False)
        for satz in kandidaten:
            if klein.startswith(satz, i):
                j = i + len(satz)
                probe = (beste[j][0] + len(satz), beste[j][1] - 1, j, True)
                if probe[:2] > wahl[:2]:
                    wahl = probe
        beste[i] = wahl
    teile, i = [], 0
    while i < laenge:
        _, _, weiter, weg = beste[i]
        teile.append(" " if weg else text[i:weiter])
        i = weiter
    return "".join(teile)


def ort_aus(text: str, sprache: Sprache, listen: tuple[str, ...] = ("wetter",)) -> str:
    """Der Ort einer Frage: alles, was nach Wetter- (oder Uhrzeit-), Tages- und Fuellwoertern
    uebrig ist."""
    weg = [s for n in (*listen, "heute", "morgen", "stopp", "hallo") for s in sprache.listen[n]]
    if sprache.ohne_leerzeichen:
        rest = _abdecken(unicodedata.normalize("NFKC", str(text or "")), weg)
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
        if stueck:
            worte.append(stueck)

    def ohne_endung(stueck: str) -> str:
        for endung in sprache.listen["endungen"]:
            if len(stueck) > len(endung) + 1 and norm(stueck).endswith(endung):
                return stueck[: len(stueck) - len(endung)]
        return stueck

    # Erst die bekannten Wendungen im ganzen Wort suchen, dann mit abgeschnittener Endung:
    # Sonst wird Ungarisch "milyen az idő" zu "mily az idő" und passt nicht mehr.
    gekuerzt = [ohne_endung(w) for w in worte]
    raus = [False] * len(worte)
    for formen in ([norm(w) for w in worte], [norm(w) for w in gekuerzt]):
        for satz in sorted(weg, key=lambda s: -len(s.split())):
            teile = satz.split()
            for i in range(len(formen) - len(teile) + 1):
                if formen[i:i + len(teile)] == teile:
                    for j in range(i, i + len(teile)):
                        raus[j] = True
    return " ".join(w for w, r in zip(gekuerzt, raus, strict=True) if not r)[:60]


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
    "schriften_in",
    "sprache_von",
    "thema",
    "treffer",
]
