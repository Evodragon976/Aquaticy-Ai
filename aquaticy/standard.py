"""Aquaticy Standard: antwortet ohne Sprachmodell (15.8.9, aus Aquaticy-Test uebernommen).

Ein Modell in der Modell-Auswahl. Wer kein Sprachmodell hat oder will, bekommt trotzdem
Antworten -- aus festen Regeln und freien, oeffentlichen Quellen:

* **Rechnen** ueber den sicheren Rechner (aquaticy/calc.py, AST mit Positivliste), dazu
  Prozente und Mehrwertsteuer ("200 plus 19 %", "119 € brutto in netto").
* **Einheiten**: Laenge, Gewicht, Volumen, Flaeche, Tempo, Zeit, Daten und Temperatur.
* **Datum und Uhrzeit** in deutscher Zeit (aquaticy/zeit.py), Tage bis Weihnachten, Silvester,
  Ostern oder einem Datum, der Wochentag eines Datums, Kalenderwoche.
* **Wetter** (Open-Meteo), **Wechselkurse** (EZB ueber Frankfurter), **Nachrichten**
  (Tagesschau) und **Wissen** (Wikipedia-Zusammenfassung) -- jeweils mit Quelle.
* **Gespraechsspeicher**: "Fuer welchen Ort?" -> "Erkelenz" reicht; der zuletzt genannte Ort
  gilt weiter ("und morgen?", "was soll ich anziehen?").
* **Zufall und Spass**: Wuerfel, Muenze, Zufallszahl, "A oder B?", Witze.
* **Zahlen und Texte** (16.0.3): Wurzeln, Primzahlen, Schaltjahre, roemische Zahlen, Binaer,
  Durchschnitt, Sternzeichen; Buchstaben zaehlen, rueckwaerts schreiben, buchstabieren.
* **Besondere Tage** (16.0.3): Muttertag, Advent, Halloween, Zeitumstellung und mehr.
* **Secure Pro**: Antworten aus dem festen Sicherheitswissen (aquaticy/secure_knowledge.py).
* **Deine Daten**: Was du ihm sagst ("ich wohne in Bremen"), merkt sich Aquaticy wie sonst im
  Gedaechtnis (aquaticy/memory_auto.py, feste Muster, ohne Modell). Aquaticy Standard bestaetigt
  das und nutzt es: Eine Wetterfrage ohne Ort gilt fuer deinen Wohnort.

Netz: nur feste, oeffentliche HTTPS-Adressen (keine Adresse aus der Frage), kurze Zeitgrenzen,
hoechstens 512 KB je Antwort. Findet Aquaticy Standard nichts, sagt es das ehrlich -- und dass
ein API-Schluessel (Add-ons) freie Antworten auf alles bringt.
"""

from __future__ import annotations

import calendar
import decimal
import fractions
import json
import math
import random
import re
import statistics
import unicodedata
from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

MODEL_ID = "aquaticy/standard"
LABEL = "Aquaticy Standard"
MAX_BYTES = 512 * 1024
TIMEOUT = 8.0

#: Was ein Abruf liefern muss: (url) -> JSON oder None. Tests geben eine eigene Funktion.
Holen = Callable[[str], Any]

KEY_HINT = ("\n\n*Übrigens: Ich bin Aquaticy Standard und komme ohne Sprachmodell aus. Mit "
            "einem anderen Modell aus der Modell-Auswahl kann ich dir zu allem frei antworten.*")
KEY_HINT_EN = ("\n\n*Aquaticy Standard answers without a language model. Pick another model "
               "in the model picker to get free answers to anything.*")


# -- Netz ---------------------------------------------------------------------------------------

ERLAUBTE_HOSTS = ("de.wikipedia.org", "en.wikipedia.org", "api.open-meteo.com",
                  "geocoding-api.open-meteo.com", "api.frankfurter.app", "www.tagesschau.de")
# 16.4.2: Wikipedia in jeder Sprache, die Aquaticy Standard kennt (feste Liste).
ERLAUBTE_HOSTS += tuple(h for h in __import__("aquaticy.weltsprachen", fromlist=["x"]).WIKI_HOSTS
                        if h not in ERLAUBTE_HOSTS)


def holen_json(url: str) -> Any:
    """Holt JSON von einer der festen Adressen. None bei jedem Fehler."""
    from urllib.parse import urlsplit

    teile = urlsplit(url)
    if teile.scheme != "https" or teile.hostname not in ERLAUBTE_HOSTS:
        return None
    try:
        import httpx

        with httpx.Client(timeout=TIMEOUT, follow_redirects=False,
                          headers={"User-Agent": "Aquaticy-Standard/16"}
                          ) as client, client.stream("GET", url) as antwort:
            if antwort.status_code != 200:
                return None
            daten = b""
            for stueck in antwort.iter_bytes():
                daten += stueck
                if len(daten) > MAX_BYTES:
                    return None
        return json.loads(daten)
    except Exception:
        return None


# -- Text ---------------------------------------------------------------------------------------

def falten(text: str) -> str:
    """Kleinbuchstaben, Umlaute als ae/oe/ue, ohne Satzzeichen am Rand."""
    text = text.lower().replace("ß", "ss")
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        text = text.replace(alt, neu)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip(" ?!.,;:")


def zahl(text: str) -> float:
    """'1.234,5' oder '1234.5' oder '1,5' als Zahl."""
    text = text.strip().replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", text):
        # "1.000" und "12.500": deutscher Tausenderpunkt. Vorher war "1.000" eins (16.4.5).
        return float(text.replace(".", ""))
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        # 1.000.000: mehrere Punkte trennen Tausender (16.1.6).
        text = text.replace(".", "")
    elif "," in text:
        text = text.replace(",", ".")
    return float(text)


def schoen(wert: float, stellen: int = 2) -> str:
    """Deutsche Schreibweise: 1.234,56 -- ohne ueberfluessige Nullen."""
    if isinstance(wert, int) and not isinstance(wert, bool):
        # Ganze Zahlen exakt: 9999999999 * 9999999999 ist ...0001, nicht ...2048 (Gleitkomma).
        return f"{wert:,}".replace(",", ".")
    if math.isinf(wert) or math.isnan(wert):
        return str(wert)
    gerundet = round(wert, stellen)
    if gerundet == int(gerundet) and abs(gerundet) < 1e15:
        text = f"{int(gerundet):,}"
    else:
        text = f"{gerundet:,.{stellen}f}".rstrip("0").rstrip(".")
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


ZAHL = r"(-?\d[\d.,]*)"


def jahr_aus(kern: str) -> int | None:
    """Ein ausdrueckliches Jahr ("Ostern 2024") -- sonst None. Nur der gregorianische Kalender."""
    treffer = re.search(r"(?<![\d.])(1[6-9]\d\d|2\d\d\d)(?![\d.,])", kern)
    return int(treffer.group(1)) if treffer else None


# -- Rechnen und Prozente -----------------------------------------------------------------------

RECHEN_VORN = re.compile(
    r"^(?:was\s+(?:ist|ergibt|gibt|sind|macht)|wie\s*viel\s+(?:ist|sind|ergibt|macht)|"
    r"rechne(?:\s+mal)?(?:\s+aus)?|berechne(?:\s+mir)?|what\s+is|what'?s|calculate|"
    # 16.4.5: "¿Cuánto es 2+2?", "Combien font 2+2 ?" -- ohne erkannte Sprache kam vorher eine
    # deutsche Absage.
    r"¿?\s*cuanto\s+(?:es|son)|combien\s+(?:font|fait)|quanto\s+(?:fa|e)|hoeveel\s+is|"
    r"ile\s+(?:to\s+)?(?:jest|bedzie)|kac\s+eder|hur\s+mycket\s+a?e?r|hvor\s+meget\s+er)\s+")
WOERTER = (("multiplied by", "*"), ("divided by", "/"), ("to the power of", "**"),
           ("times", "*"), ("plus", "+"), ("minus", "-"), ("mal", "*"), ("geteilt durch", "/"),
           ("durch", "/"), ("hoch", "**"), ("modulo", "%"), ("mod", "%"), ("x", "*"),
           ("×", "*"), ("÷", "/"), ("^", "**"))


def rechnen(text: str) -> str:
    from aquaticy.calc import calculate

    # 16.4.5: "3 zum Quadrat", "3 squared", "4²", "√16", "100 : 4", "Kubikwurzel von 27",
    # "minus 5 plus 3" und "15 modulo 4" kannte Standard vorher nicht.
    roh = str(text).replace("²", " ** 2").replace("³", " ** 3")
    roh = re.sub(r"√\s*(\d[\d.,]*)", r"(\1 ** 0.5)", roh)
    kern = RECHEN_VORN.sub("", falten(roh)).rstrip("= ")
    # 16.4.5: "5!", "10 Fakultät", "Fakultät von 6" -- der Worker konnte das schon.
    # Das "!" steht im Original -- falten() nimmt Satzzeichen am Ende weg.
    ausrufe = RECHEN_VORN.sub("", str(text).lower().strip()).strip(" ?.")
    fakultaet = (re.fullmatch(r"(\d{1,3})\s*!", ausrufe)
                 or re.fullmatch(r"(\d{1,3})\s+fakultaet|fakultaet\s+(?:von\s+)?(\d{1,3})",
                                 kern.strip()))
    if fakultaet:
        n = int(next(g for g in fakultaet.groups() if g))
        if n > 100:
            return "Das wird mir zu groß – Fakultäten rechne ich bis 100 aus."
        return f"**{schoen(math.factorial(n))}**"
    kern = re.sub(r"\s+(?:zum\s+quadrat|squared|im\s+quadrat)\b", " ** 2", kern)
    kern = re.sub(r"\s+(?:hoch\s+drei|cubed)\b", " ** 3", kern)
    kern = re.sub(r"(?<=\d)\s+:\s+(?=[\d(])", " / ", kern)
    # 16.4.5: "27 hoch 1/3" ergab 9 -- mit "hoch" ist der ganze Bruch der Exponent.
    kern = re.sub(r"\bhoch\s+(-?\d+)\s*/\s*(\d+)", r"hoch (\1/\2)", kern)
    for wort, zeichen in WOERTER:
        kern = re.sub(rf"(?:(?<=[\d\s)])|^){re.escape(wort)}(?=[\s\d(])", f" {zeichen} ", kern)
    # 16.4.5: erst die dritte Wurzel -- vorher griff "wurzel aus 27" in "dritte Wurzel aus 27"
    # zuerst, und es kam keine Antwort.
    kern = re.sub(r"(?:die\s+|the\s+)?(?:kubikwurzel|dritte\s+wurzel)\s+(?:aus|von)\s+"
                  r"(\d[\d.,]*)|(?:the\s+)?cube\s+root\s+of\s+(\d[\d.,]*)",
                  lambda t: f"({t.group(1) or t.group(2)} ** (1/3))", kern)
    if re.search(r"\b(?:quadrat)?wurzel\s+(?:aus|von)\s+(?:minus\s+|-\s*)\d|"
                 r"\bsquare\s+root\s+of\s+(?:minus\s+|-\s*)\d", kern):
        return "Die Wurzel aus einer negativen Zahl ist keine reelle Zahl."
    kern = re.sub(r"\b(?:die\s+|the\s+)?(?:quadrat)?wurzel\s+(?:aus|von)\s+"
                  r"(\d[\d.,]*|\([^()]*\))|(?:the\s+)?square\s+root\s+of\s+(\d[\d.,]*)",
                  lambda t: f"({t.group(1) or t.group(2)} ** 0.5)", kern)
    # 1.000.000 oder 1.234,5: Die Punkte trennen Tausender.
    # 16.4.5: auch eine einzelne Gruppe ("1.000 + 1" ergab vorher 2).
    kern = re.sub(r"(?<![\d.,])\d{1,3}(?:\.\d{3})+(?![\d.])|(?<![\d.,])\d{1,3}\.\d{3}(?=,\d)",
                  lambda t: t.group(0).replace(".", ""), kern)
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", kern.strip()):
        return ""  # "2026-12-24" ist ein Datum, keine Rechnung (16.4.5)
    if not re.fullmatch(r"[\d\s.,+\-*/()%]+", kern) or not re.search(r"\d", kern):
        return ""
    if not re.search(r"[+\-*/%]", kern):
        return ""
    try:
        ergebnis = calculate(kern)
    except Exception as fehler:
        grund = str(fehler).lower()
        if "null" in grund:
            return "Durch null kann man nicht teilen – das Ergebnis ist nicht definiert."
        if "gross" in grund:
            return "Das wird mir zu groß – so hohe Potenzen rechne ich nicht aus."
        return ""
    if isinstance(ergebnis, complex) or math.isinf(ergebnis) or math.isnan(ergebnis):
        return "Dafür gibt es keine reelle Zahl als Ergebnis."
    return f"**{schoen(ergebnis, 6)}**"


PROZENT_VON = re.compile(rf"{ZAHL}\s*(?:%|prozent|percent)\s+(von|aus|of)\s+{ZAHL}")
PROZENT_PLUS = re.compile(rf"{ZAHL}\s*(?:€|eur|euro)?\s*(plus|minus|\+|-|abzueglich|zuzueglich)"
                          rf"\s*{ZAHL}\s*(?:%|prozent)")
#: 16.4.5: "10 Prozent mehr als 50", "20 % weniger als 150".
PROZENT_MEHR = re.compile(rf"{ZAHL}\s*(?:%|prozent)\s+(mehr|weniger)\s+als\s+{ZAHL}")
#: 16.4.5: "30 von 120 in Prozent", "Von 80 auf 100 sind wie viel Prozent?"
PROZENT_IN = re.compile(rf"{ZAHL}\s+von\s+{ZAHL}\s+(?:in|als)\s+prozent")
PROZENT_AUF = re.compile(rf"\bvon\s+{ZAHL}\s+auf\s+{ZAHL}\s+(?:sind|ist|macht)\s+(?:das\s+|es\s+)?"
                         r"wie\s*viel\w*\s+prozent")
#: 16.4.5: "das Doppelte von 21".
VIELFACHE = {"doppelte": 2, "dreifache": 3, "vierfache": 4, "fuenffache": 5, "zehnfache": 10,
             "hundertfache": 100}
VIELFACH_VON = re.compile(r"\b(doppelte|dreifache|vierfache|fuenffache|zehnfache|hundertfache)"
                          rf"\s+(?:von|aus)\s+{ZAHL}")
#: 16.4.5: "Preis 80 Euro, 25 % Rabatt".
RABATT_HINTEN = re.compile(rf"{ZAHL}\s*(?:€|eur|euro)\s*,?\s*(?:und\s+|mit\s+)?{ZAHL}\s*"
                           r"(?:%|prozent)\s+(rabatt|nachlass|skonto|aufschlag)\b")
#: 16.4.5: "19 % MwSt auf 50 €", "Mehrwertsteuer von 100 Euro", "MwSt in 119 Euro".
MWST = re.compile(r"\b(?:mwst|mehrwertsteuer|umsatzsteuer|ust)\b")
BRUTTO_NETTO = re.compile(rf"{ZAHL}\s*(?:€|eur|euro)?\s*(brutto|netto)\s*(?:in|zu|nach)\s*"
                          r"(netto|brutto)")


#: 16.3.0: "ein Drittel von 90", "die Hälfte von 37", "drei Viertel von 200".
BRUECHE = {"halb": 2, "haelfte": 2, "drittel": 3, "viertel": 4, "fuenftel": 5, "sechstel": 6,
           "achtel": 8, "zehntel": 10, "hundertstel": 100}
ZAEHLER = {"ein": 1, "eine": 1, "einen": 1, "die": 1, "zwei": 2, "drei": 3, "vier": 4,
           "fuenf": 5, "sieben": 7, "neun": 9}
BRUCH_VON = re.compile(r"\b(?:(ein|eine|einen|die|zwei|drei|vier|fuenf|sieben|neun|\d+)\s+)?"
                       r"(halb|haelfte|drittel|viertel|fuenftel|sechstel|achtel|zehntel|"
                       rf"hundertstel)\s+(?:von|aus)\s+{ZAHL}")
PROZENT_ANTEIL = re.compile(rf"wie\s*viele?\s+prozent\s+(?:sind|ist|macht|machen|ergeben)\s+"
                            rf"{ZAHL}\s+(?:von|aus)\s+{ZAHL}")
PROZENT_ANTEIL_VORN = re.compile(rf"{ZAHL}\s+(?:sind|ist|macht|machen|ergeben)\s+"
                                 rf"wie\s*viele?\s+prozent\s+(?:von|aus)\s+{ZAHL}")
PROZENT_ABSTAND = re.compile(
    rf"um\s+wie\s*viel(?:e)?\s+prozent\s+(?:ist|sind|liegt|war|waere)\s+{ZAHL}\s+(?:\w+\s+)?"
    r"(?:groesser|hoeher|mehr|teurer|kleiner|niedriger|weniger|billiger|guenstiger)\s+als\s+"
    + ZAHL)
RABATT = re.compile(rf"{ZAHL}\s*(?:%|prozent)\s+(rabatt|nachlass|skonto|aufschlag)\s+"
                    rf"(?:auf|von|fuer)\s+{ZAHL}")


def _steuersatz(kern: str) -> float:
    """Der genannte Steuersatz ("bei 7 %") -- sonst 19 %."""
    treffer = re.search(r"(\d{1,2}(?:[.,]\d)?)\s*(?:%|prozent)", kern)
    satz = zahl(treffer.group(1)) if treffer else 19.0
    return satz if 0 < satz < 100 else 19.0


def _mwst(kern: str) -> str:
    satz = _steuersatz(kern)
    ohne = re.sub(r"(\d{1,2}(?:[.,]\d)?)\s*(?:%|prozent)", " ", kern)
    treffer = re.search(rf"\b(?:in|bei|im\s+preis\s+von)\s+{ZAHL}\s*(?:€|eur|euro)?", ohne)
    if treffer:
        brutto = zahl(treffer.group(1))
        steuer = brutto - brutto / (1 + satz / 100)
        return (f"In {geld(brutto)} stecken **{geld(steuer)}** Mehrwertsteuer "
                f"({schoen(satz)} %, netto {geld(brutto - steuer)}).")
    treffer = re.search(rf"\b(?:auf|von|fuer)\s+{ZAHL}\s*(?:€|eur|euro)?", ohne)
    if treffer:
        netto = zahl(treffer.group(1))
        steuer = netto * satz / 100
        return (f"Auf {geld(netto)} kommen **{geld(steuer)}** Mehrwertsteuer "
                f"({schoen(satz)} %, brutto {geld(netto + steuer)}).")
    return ""


def _mit_mal(kern: str) -> str:
    """"1,5 mio" -> "1500000": vorher galt in "25 % von 1,5 Mio" nur die 1,5 (16.4.5)."""
    def ersetzen(t: re.Match[str]) -> str:
        try:
            wert = zahl(t.group(1)) * WAEHRUNG_MAL[t.group(2)]
        except (ValueError, KeyError):
            return t.group(0)
        return str(int(wert)) if wert == int(wert) else str(wert)

    return re.sub(r"(\d[\d.,]*)\s*(" + "|".join(sorted(WAEHRUNG_MAL, key=len, reverse=True))
                  + r")\b", ersetzen, kern)


def prozente(text: str) -> str:
    kern = _mit_mal(falten(text).replace("€", " € "))
    treffer = VIELFACH_VON.search(kern)
    if treffer:
        mal, g = VIELFACHE[treffer.group(1)], zahl(treffer.group(2))
        return f"Das {treffer.group(1).capitalize()} von {schoen(g)} ist **{schoen(g * mal)}**."
    treffer = PROZENT_IN.search(kern)
    if treffer:
        teil, ganz = zahl(treffer.group(1)), zahl(treffer.group(2))
        if ganz:
            return f"{schoen(teil)} von {schoen(ganz)} sind **{schoen(teil / ganz * 100)} %**."
    treffer = PROZENT_AUF.search(kern)
    if treffer:
        a, b = zahl(treffer.group(1)), zahl(treffer.group(2))
        if a:
            aenderung = (b - a) / abs(a) * 100
            wort = "mehr" if aenderung >= 0 else "weniger"
            return (f"Von {schoen(a)} auf {schoen(b)} sind es **{schoen(abs(aenderung))} % "
                    f"{wort}**.")
    treffer = PROZENT_MEHR.search(kern)
    if treffer:
        p, art, g = zahl(treffer.group(1)), treffer.group(2), zahl(treffer.group(3))
        faktor = 1 + p / 100 if art == "mehr" else 1 - p / 100
        return f"{schoen(p)} % {art} als {schoen(g)} sind **{schoen(g * faktor)}**."
    if MWST.search(kern) and not BRUTTO_NETTO.search(kern):
        text_ = _mwst(kern)
        if text_:
            return text_
    treffer = RABATT_HINTEN.search(kern)
    if treffer:
        g, p, art = zahl(treffer.group(1)), zahl(treffer.group(2)), treffer.group(3)
        faktor = 1 + p / 100 if art == "aufschlag" else 1 - p / 100
        wort = "Aufschlag" if art == "aufschlag" else "Rabatt"
        return (f"{schoen(p)} % {wort} auf {schoen(g)} sind **{schoen(g * faktor)}** "
                f"(Unterschied: {schoen(abs(g * faktor - g))}).")
    treffer = re.search(rf"(?<![\d/.,])(\d{{1,4}})\s*/\s*(\d{{1,4}})\s+(?:von|aus|of)\s+"
                        rf"{ZAHL}", kern)
    if treffer and int(treffer.group(2)) > 0:
        # 16.4.5: "3/4 von 200" und "1/3 von 90" gingen vorher an Wikipedia.
        z, n, g = int(treffer.group(1)), int(treffer.group(2)), zahl(treffer.group(3))
        if re.search(r"\s+of\s+", treffer.group(0)):
            return _englisch(f"{z}/{n} of {schoen(g)} is **{schoen(g * z / n)}**.")
        return f"{z}/{n} von {schoen(g)} sind **{schoen(g * z / n)}**."
    treffer = BRUCH_VON.search(kern)
    if treffer:
        oben = treffer.group(1) or "ein"
        z = int(oben) if oben.isdigit() else ZAEHLER[oben]
        n, g = BRUECHE[treffer.group(2)], zahl(treffer.group(3))
        if 0 < z <= 1000:
            return f"{z}/{n} von {schoen(g)} sind **{schoen(g * z / n)}**."
    # "80 ist wie viel Prozent von 200?" -- die Zahl steht vor der Frage.
    treffer = PROZENT_ANTEIL.search(kern) or PROZENT_ANTEIL_VORN.search(kern)
    if treffer:
        teil, ganz = zahl(treffer.group(1)), zahl(treffer.group(2))
        if ganz:
            return f"{schoen(teil)} von {schoen(ganz)} sind **{schoen(teil / ganz * 100)} %**."
    treffer = PROZENT_ABSTAND.search(kern)
    if treffer:
        a, b = zahl(treffer.group(1)), zahl(treffer.group(2))
        if b:
            richtung = "größer" if a >= b else "kleiner"
            return (f"{schoen(a)} ist **{schoen(abs(a - b) / abs(b) * 100)} %** {richtung} "
                    f"als {schoen(b)}.")
    treffer = RABATT.search(kern)
    if treffer:
        p, art, g = zahl(treffer.group(1)), treffer.group(2), zahl(treffer.group(3))
        faktor = 1 + p / 100 if art == "aufschlag" else 1 - p / 100
        wort = "Aufschlag" if art == "aufschlag" else "Rabatt"
        return (f"{schoen(p)} % {wort} auf {schoen(g)} sind **{schoen(g * faktor)}** "
                f"(Unterschied: {schoen(abs(g * faktor - g))}).")
    treffer = PROZENT_VON.search(kern)
    if treffer:
        p, g = zahl(treffer.group(1)), zahl(treffer.group(3))
        if treffer.group(2) == "of":
            # "What is 15% of 200?" landete vorher bei Wikipedia (16.4.5).
            return _englisch(f"{schoen(p)} % of {schoen(g)} is **{schoen(g * p / 100)}**.")
        if kern[treffer.end():].lstrip().startswith(("%", "prozent")):
            # 16.4.5: "10 % von 10 %" ist 1 % -- vorher stand dort "sind 1".
            return f"{schoen(p)} % von {schoen(g)} % sind **{schoen(g * p / 100)} %**."
        return f"{schoen(p)} % von {schoen(g)} sind **{schoen(g * p / 100)}**."
    treffer = PROZENT_PLUS.search(kern)
    if treffer:
        g, art, p = zahl(treffer.group(1)), treffer.group(2), zahl(treffer.group(3))
        faktor = 1 + p / 100 if art in ("plus", "+", "zuzueglich") else 1 - p / 100
        return (f"{schoen(g)} {'plus' if faktor > 1 else 'minus'} {schoen(p)} % sind "
                f"**{schoen(g * faktor)}** (Unterschied: {schoen(abs(g * faktor - g))}).")
    treffer = BRUTTO_NETTO.search(kern)
    if treffer:
        betrag, von, nach = zahl(treffer.group(1)), treffer.group(2), treffer.group(3)
        if von == nach:
            return ""
        # 16.4.5: "bei 7 %" galt vorher nicht -- gerechnet wurde immer mit 19 %.
        satz = _steuersatz(kern[treffer.end():] + " " + kern[:treffer.start()])
        faktor = 1 + satz / 100
        if von == "brutto":
            netto = betrag / faktor
            return (f"{schoen(betrag)} € brutto sind **{schoen(netto)} € netto** "
                    f"({schoen(satz)} % MwSt.: {schoen(betrag - netto)} €).")
        return (f"{schoen(betrag)} € netto sind **{schoen(betrag * faktor)} € brutto** "
                f"({schoen(satz)} % MwSt.: {schoen(betrag * satz / 100)} €).")
    return ""


# -- Einheiten ----------------------------------------------------------------------------------

_EINHEITEN_JE_ART: dict[str, list[tuple[str, float]]] = {
    "laenge": [("mm", .001), ("millimeter", .001), ("cm", .01), ("zentimeter", .01),
               ("m", 1), ("meter", 1), ("km", 1000), ("kilometer", 1000), ("zoll", .0254),
               ("inch", .0254), ("fuss", .3048), ("feet", .3048), ("ft", .3048),
               ("meile", 1609.344), ("meilen", 1609.344), ("mile", 1609.344),
               ("miles", 1609.344), ("seemeile", 1852), ("seemeilen", 1852)],
    "gewicht": [("mg", .001), ("g", 1), ("gramm", 1), ("kg", 1000), ("kilo", 1000),
                ("kilogramm", 1000), ("t", 1e6), ("tonne", 1e6), ("tonnen", 1e6),
                ("pfund", 500), ("lb", 453.59237), ("lbs", 453.59237), ("unze", 28.349523),
                ("unzen", 28.349523), ("oz", 28.349523)],
    "volumen": [("ml", .001), ("milliliter", .001), ("cl", .01), ("l", 1), ("liter", 1),
                ("gallone", 3.785411784), ("gallonen", 3.785411784), ("gallon", 3.785411784),
                ("m3", 1000), ("kubikmeter", 1000)],
    "flaeche": [("m2", 1), ("quadratmeter", 1), ("qm", 1), ("km2", 1e6),
                ("quadratkilometer", 1e6), ("ha", 1e4), ("hektar", 1e4), ("ar", 100)],
    "tempo": [("km/h", 1), ("kmh", 1), ("m/s", 3.6), ("mph", 1.609344), ("knoten", 1.852)],
    "zeit": [("sekunde", 1), ("sekunden", 1), ("s", 1), ("minute", 60), ("minuten", 60),
             ("min", 60), ("stunde", 3600), ("stunden", 3600), ("h", 3600), ("tag", 86400),
             ("tage", 86400), ("woche", 604800), ("wochen", 604800), ("jahr", 31557600),
             ("jahre", 31557600)],
    "leistung": [("w", 1), ("watt", 1), ("kw", 1000), ("kilowatt", 1000), ("ps", 735.49875),
                 ("hp", 745.699872)],
    "daten": [("byte", 1), ("bytes", 1), ("kb", 1e3), ("mb", 1e6), ("gb", 1e9), ("tb", 1e12),
              ("kib", 1024), ("mib", 1024**2), ("gib", 1024**3), ("tib", 1024**4)],
}
EINHEITEN: dict[str, tuple[str, float]] = {
    name: (art, faktor) for art, liste in _EINHEITEN_JE_ART.items() for name, faktor in liste}
TEMPERATUR = {"c": "c", "grad": "c", "celsius": "c", "°c": "c", "f": "f", "fahrenheit": "f",
              "°f": "f", "k": "k", "kelvin": "k"}
UMRECHNEN = re.compile(rf"{ZAHL}\s*([a-z°/0-9]+)\s+(?:in|nach|zu|to|into|=)\s+([a-z°/0-9]+)")
#: 16.3.0: englische Namen der Einheiten.
for _name, _gleich in (("gram", "g"), ("grams", "g"), ("kilogram", "kg"), ("kilograms", "kg"),
                       ("pound", "lb"), ("pounds", "lb"), ("ounce", "oz"), ("ounces", "oz"),
                       ("meter", "m"), ("meters", "m"), ("metre", "m"), ("metres", "m"),
                       ("kilometers", "km"), ("kilometres", "km"), ("centimeters", "cm"),
                       ("inches", "inch"), ("foot", "ft"), ("yard", "yd"), ("yards", "yd"),
                       ("liters", "l"), ("litres", "l"), ("gallons", "gallon"),
                       ("hour", "h"), ("hours", "h"), ("minutes", "min"), ("seconds", "s"),
                       ("days", "tag"), ("day", "tag"), ("weeks", "woche"),
                       # "6 Fuß in Metern": die Einheit im Dativ (16.4.5).
                       ("metern", "m"), ("kilometern", "km"), ("zentimetern", "cm"),
                       ("millimetern", "mm"), ("litern", "l"), ("millilitern", "ml"),
                       ("tagen", "tag"), ("jahren", "jahr"), ("wattstunden", "watt")):
    if _gleich == "yd":
        EINHEITEN.setdefault("yd", ("laenge", .9144))
    EINHEITEN.setdefault(_name, EINHEITEN[_gleich])


def anzeige(name: str) -> str:
    """Einheit so geschrieben, wie man sie liest: GB, Meilen, km/h."""
    if EINHEITEN.get(name, ("",))[0] == "daten":
        return name.upper().replace("IB", "iB")
    deutsch = {"metern": "Meter", "kilometern": "Kilometer", "zentimetern": "Zentimeter",
               "millimetern": "Millimeter", "litern": "Liter", "millilitern": "Milliliter",
               "tagen": "Tage", "jahren": "Jahre", "tag": "Tag", "ps": "PS", "kw": "kW",
               "w": "W", "fuss": "Fuß"}
    if name in deutsch:
        return deutsch[name]
    if name.isalpha() and len(name) > 3:
        return name.capitalize()
    return name


#: 16.3.0: andersherum gefragt -- "Wie viele Minuten haben 3 Stunden?", "how many km is ...".
UMRECHNEN_FRAGE = re.compile(rf"\b(?:wie\s*viele?|how\s+many)\s+([a-z°/0-9]+)\s+"
                             r"(?:sind|ist|hat|haben|ergeben|machen|is|are|in)\s+"
                             rf"(?:{ZAHL}|(einen|eine|ein|one|an|a)\b)\s*([a-z°/0-9]+)")


def _englisch(text: str) -> str:
    """Deutsche Zahlen und "sind" einer Antwort auf Englisch: "16,0934" -> "16.0934"."""
    text = re.sub(r"\d[\d.,]*\d|\d", lambda z: z.group(0).replace(".", "\x00").replace(
        ",", ".").replace("\x00", ","), text)
    # "Miles" -> "miles": Einheiten schreibt man im Englischen klein.
    text = re.sub(r"\b[A-Z][a-z]+\b", lambda w: w.group(0).lower()
                  if w.group(0).lower() in EINHEITEN else w.group(0), text)
    return text.replace(" sind ", " is ").replace(" ist ", " is ")


_DAUER_TEIL = {"h": 3600, "min": 60, "s": 1}
_DAUER_ZIEL = {"stunden": ("Stunden", 3600), "stunde": ("Stunden", 3600), "h": ("Stunden", 3600),
               "minuten": ("Minuten", 60), "minute": ("Minuten", 60), "min": ("Minuten", 60),
               "sekunden": ("Sekunden", 1), "sekunde": ("Sekunden", 1), "s": ("Sekunden", 1),
               "hours": ("hours", 3600), "minutes": ("minutes", 60), "seconds": ("seconds", 1)}
_DAUER = re.compile(
    r"(?:(\d+(?:[.,]\d+)?)\s*(?:stunden?|std|h|hours?)\s+(?:und\s+|and\s+)?)?"
    r"(?:(\d+(?:[.,]\d+)?)\s*(?:minuten?|min|minutes?)\s*(?:und\s+|and\s+)?)?"
    r"(?:(\d+(?:[.,]\d+)?)\s*(?:sekunden?|sek|s|seconds?))?"
    r"\s+(?:in|nach|zu|to|into)\s+(stunden?|h|minuten?|min|sekunden?|s|hours|minutes|seconds)\b")


def _dauer_umrechnen(gefaltet: str) -> str:
    """16.4.5: "3 Stunden 20 Minuten in Minuten" -- vorher "20 Minuten sind 20 Minuten"."""
    treffer = _DAUER.search(gefaltet)
    if not treffer or sum(1 for g in treffer.groups()[:3] if g) < 2:
        return ""
    teile = [(treffer.group(1), "h"), (treffer.group(2), "min"), (treffer.group(3), "s")]
    sekunden = sum(zahl(wert) * _DAUER_TEIL[art] for wert, art in teile if wert)
    englisch = treffer.group(4) in ("hours", "minutes", "seconds")
    namen = ({"h": "h", "min": "min", "s": "s"} if englisch
             else {"h": "Std.", "min": "Min.", "s": "Sek."})
    vorn = " ".join(f"{schoen(zahl(wert))} {namen[art]}" for wert, art in teile if wert)
    name, faktor = _DAUER_ZIEL[treffer.group(4)]
    verb = "is" if englisch else "sind"
    return f"{vorn} {verb} **{schoen(sekunden / faktor)} {name}**."


def einheiten(text: str) -> str:
    # 16.4.5: "Wie viel sind 72 Grad Fahrenheit?" -- ohne Ziel die andere Temperaturskala.
    ohne_ziel = re.fullmatch(r"(?:wie\s*viel\s+(?:sind|ist)\s+|was\s+(?:sind|ist)\s+)?"
                             r"(-?\d+(?:[.,]\d+)?)\s*(?:grad\s+|°\s*)?(fahrenheit|celsius|f|c)",
                             falten(text))
    if ohne_ziel and (ohne_ziel.group(2) in ("fahrenheit", "celsius")
                      or "grad" in falten(text)):
        nach_ = "celsius" if ohne_ziel.group(2).startswith("f") else "fahrenheit"
        text = f"{ohne_ziel.group(1)} {ohne_ziel.group(2)} in {nach_}"
    gefaltet = re.sub(r"\b(?:grad|degrees?)\s+(celsius|fahrenheit)\b", r"\1", falten(text))
    # 16.4.5: "3 Fuß 6 Zoll in cm" rechnete vorher nur die 6 Zoll; "ein Zoll in cm" ging nicht.
    gefaltet = re.sub(r"(\d+(?:[.,]\d+)?)\s*(?:fuss|ft|')\s*(\d+(?:[.,]\d+)?)\s*"
                      r"(?:zoll|inch|inches|\")",
                      lambda t: f"{schoen(zahl(t.group(1)) * 12 + zahl(t.group(2)))} zoll",
                      gefaltet)
    gefaltet = re.sub(r"\bein(?:e|en|em)?\s+(?=[a-z°/]+\s+(?:in|nach|zu|to)\s)", "1 ", gefaltet)
    dauer = _dauer_umrechnen(gefaltet)
    if dauer:
        return dauer
    treffer = UMRECHNEN.search(gefaltet)
    # "5 km sind wie viele Meilen?" (16.4.5)
    vorn = re.search(rf"{ZAHL}\s*([a-z°/0-9]+)\s+(?:sind|ist|ergeben|machen)\s+wie\s*viele?\s+"
                     r"([a-z°/0-9]+)", gefaltet)
    if vorn and not treffer:
        treffer = vorn
    if treffer:
        wert, von, nach = zahl(treffer.group(1)), treffer.group(2), treffer.group(3)
    else:
        treffer = UMRECHNEN_FRAGE.search(gefaltet)
        if not treffer:
            return ""
        nach, von = treffer.group(1), treffer.group(4)
        wert = zahl(treffer.group(2)) if treffer.group(2) else 1.0
    if von in TEMPERATUR and nach in TEMPERATUR:
        celsius = {"c": wert, "f": (wert - 32) * 5 / 9, "k": wert - 273.15}[TEMPERATUR[von]]
        ziel = {"c": celsius, "f": celsius * 9 / 5 + 32, "k": celsius + 273.15}[TEMPERATUR[nach]]
        zeichen = {"c": "°C", "f": "°F", "k": "K"}
        return (f"{schoen(wert)} {zeichen[TEMPERATUR[von]]} {'ist' if wert == 1 else 'sind'} "
                f"**{schoen(ziel)} {zeichen[TEMPERATUR[nach]]}**.")
    if von not in EINHEITEN or nach not in EINHEITEN or EINHEITEN[von][0] != EINHEITEN[nach][0]:
        return ""
    ergebnis = wert * EINHEITEN[von][1] / EINHEITEN[nach][1]
    # "1 Meile sind" war falsch -- eins ist Einzahl (16.4.5).
    verb = "ist" if wert == 1 else "sind"
    return f"{schoen(wert)} {anzeige(von)} {verb} **{schoen(ergebnis, 4)} {anzeige(nach)}**."


# -- Datum und Uhrzeit --------------------------------------------------------------------------

WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
MONATE = ("januar", "februar", "maerz", "april", "mai", "juni", "juli", "august",
          "september", "oktober", "november", "dezember")


def ostern(jahr: int) -> date:
    """Ostersonntag nach Gauss/Anonymous Gregorian."""
    a, b, c = jahr % 19, jahr // 100, jahr % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    monat = (h + l_ - 7 * m + 114) // 31
    tag = (h + l_ - 7 * m + 114) % 31 + 1
    return date(jahr, monat, tag)


def datum_aus(text: str, heute: date) -> date | None:
    """'24.12.', '24.12.2026', '3. Oktober', '3 oktober 2027'."""
    # 16.4.5: auch ISO-Daten ("2026-12-24"), wie im Worker -- vorher gab es dazu keine Antwort.
    iso = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    # Am Satzende fehlt der letzte Punkt oft ("bis zum 24.12?").
    treffer = re.search(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4})?|(?=\s*$))", text)
    if treffer:
        tag, monat, jahr_text = int(treffer.group(1)), int(treffer.group(2)), treffer.group(3)
    else:
        treffer = re.search(r"\b(\d{1,2})\.?\s+(" + "|".join(MONATE) + r")\s*(\d{4})?", text)
        if not treffer:
            return None
        tag, monat = int(treffer.group(1)), MONATE.index(treffer.group(2)) + 1
        jahr_text = treffer.group(3)
    if jahr_text:
        jahr = int(jahr_text)
        if jahr < 100:
            # 16.1.6: "05.05.90" ist 1990, nicht 2090 -- mehr als 20 Jahre voraus gilt als 19xx.
            jahr += 2000 if 2000 + jahr <= heute.year + 20 else 1900
        jahre: tuple[int, ...] = (jahr,)
    else:
        # Ohne Jahr: dieses -- den 29. Februar gibt es aber nur im naechsten Schaltjahr.
        jahre = tuple(range(heute.year, heute.year + 9))
    for jahr in jahre:
        try:
            return date(jahr, monat, tag)
        except ValueError:
            continue
    return None


def im_jahr(tag: date, jahr: int) -> date:
    """Derselbe Tag in einem anderen Jahr. Den 29. Februar gibt es nicht jedes Jahr: dann

    gilt der 1. Maerz (so rechnet auch das Gesetz beim Geburtstag).
    """
    try:
        return tag.replace(year=jahr)
    except ValueError:
        return date(jahr, 3, 1)


def in_tagen(tage: int) -> str:
    """"morgen" oder "in 3 Tagen" -- vorher stand dort auch "in 1 Tagen" (16.4.5)."""
    return "morgen" if tage == 1 else f"in {tage} Tagen"


def arbeitstage(von: date, bis: date) -> int:
    """Montag bis Freitag ohne bundesweite Feiertage, *von* und *bis* mitgezaehlt."""
    from datetime import timedelta

    if bis < von:
        return 0
    frei = {t for jahr_ in range(von.year, bis.year + 1) for t, _ in feiertage(jahr_)}
    return sum(1 for i in range((bis - von).days + 1)
               if (von + timedelta(days=i)).weekday() < 5 and von + timedelta(days=i) not in frei)


def in_einheit(text: str, kern: str, tage: int, heute: date | None = None) -> str:
    """"Wie viele Wochen bis ...?" bekam vorher nur Tage (16.4.5)."""
    if heute is not None and 1 <= tage <= 3660 and re.search(r"\b(?:werk|arbeits)tage?\b", kern):
        # 16.4.5: "Wie viele Werktage bis Weihnachten?" nannte vorher alle Kalendertage.
        from datetime import timedelta

        anzahl = arbeitstage(heute + timedelta(days=1), heute + timedelta(days=tage - 1))
        wort = "Arbeitstag" if anzahl == 1 else "Arbeitstage"
        return (text + f" Dazwischen liegen **{anzahl} {wort}** (Montag bis Freitag, ohne "
                "bundesweite Feiertage).")
    if tage >= 7 and re.search(r"\bwochen\b", kern):
        wochen, rest = divmod(tage, 7)
        mehr = f" und {rest} {'Tag' if rest == 1 else 'Tage'}" if rest else ""
        return text + f" Das sind **{wochen} {'Woche' if wochen == 1 else 'Wochen'}{mehr}**."
    if tage >= 1 and re.search(r"\bstunden\b", kern):
        return text + f" Das sind etwa **{schoen(tage * 24)} Stunden**."
    return text


def tage_text(tage: int, was: str, wann: str = "") -> str:
    wann = f" ({wann})" if wann else ""
    if tage == 0:
        return f"{was}{wann} ist **heute**."
    if tage == 1:
        return f"Bis {was}{wann} ist es noch **1 Tag**."
    # 16.4.5: mit Tausenderpunkt -- vorher "1139 Tage".
    return f"Bis {was}{wann} sind es noch **{schoen(tage)} Tage**."


_DATUM_TEIL = (r"(\d{1,2}\.\s*\d{1,2}(?:\.(?:\d{2,4})?)?|\d{1,2}\.?\s+(?:" + "|".join(MONATE)
               + r")(?:\s+\d{4})?|\d{4}-\d{1,2}-\d{1,2})")


def zeitspanne(text: str, heute: date) -> str:
    """16.4.5: "Wie viele Tage liegen zwischen dem 1.1. und dem 31.12.?", "vom 1.3. bis 1.4.",
    "Wie lange ist der 1.1.2000 her?" -- vorher keine oder eine falsche Antwort."""
    kern = falten(text)
    treffer = re.search(r"\b(?:zwischen\s+(?:dem\s+)?" + _DATUM_TEIL + r"\s+und\s+(?:dem\s+)?"
                        + _DATUM_TEIL + r"|vom\s+" + _DATUM_TEIL + r"\s+bis\s+(?:zum\s+)?"
                        + _DATUM_TEIL + r")", kern)
    if treffer and re.search(r"\bwie\s*(?:viele|lange)\b", kern):
        a_text, b_text = [g for g in treffer.groups() if g][:2]
        a, b = datum_aus(a_text, heute), datum_aus(b_text, heute)
        if a and b:
            if re.search(r"\d{4}", b_text) and not re.search(r"\d{4}", a_text):
                a = im_jahr(a, b.year)  # "vom 1.5. bis 31.5.2027"
            if b < a and not re.search(r"\d{4}", b_text):
                b = im_jahr(b, a.year + 1)
            tage = abs((b - a).days)
            return (f"Vom {min(a, b):%d.%m.%Y} bis zum {max(a, b):%d.%m.%Y} sind es "
                    f"**{schoen(tage)} {'Tag' if tage == 1 else 'Tage'}**.")
    her = re.search(r"\bwie\s*(?:lange|viele\s+tage)\s+ist\s+(?:der\s+|das\s+)?" + _DATUM_TEIL
                    + r"\s+her\b", kern)
    if her:
        damals = datum_aus(her.group(1), heute)
        if damals and damals <= heute:
            tage = (heute - damals).days
            jahre = heute.year - damals.year - ((heute.month, heute.day)
                                                 < (damals.month, damals.day))
            zusatz = f" – gut {jahre} {'Jahr' if jahre == 1 else 'Jahre'}" if jahre >= 1 else ""
            return (f"Der {damals:%d.%m.%Y} ist **{schoen(tage)} "
                    f"{'Tag' if tage == 1 else 'Tage'}** her{zusatz}.")
    return ""


def zeit(text: str, jetzt: datetime | None = None) -> str:
    from aquaticy import zeit as zeit_mod

    jetzt = jetzt or zeit_mod.jetzt()
    heute = jetzt.date()
    kern = falten(text)
    spanne = zeitspanne(text, heute)
    if spanne:
        return spanne
    # 16.4.5: "Wie spät ist es in 3 Stunden?" nannte vorher die Uhrzeit von jetzt.
    spaeter = re.search(r"\b(in|vor)\s+(\d{1,3})\s+(stunden?|minuten?)\b", kern)
    if spaeter and re.search(r"\b(wie\s*spaet|uhrzeit|wieviel\s+uhr|wie\s+viel\s+uhr)\b", kern):
        from datetime import timedelta

        menge = int(spaeter.group(2))
        schritt = timedelta(hours=menge) if spaeter.group(3).startswith("stunde") else timedelta(
            minutes=menge)
        dann = jetzt + schritt if spaeter.group(1) == "in" else jetzt - schritt
        anderer_tag = "" if dann.date() == heute else f", {WOCHENTAGE[dann.weekday()]}"
        einheit = {"stunde": "Stunde", "stunden": "Stunden", "minute": "Minute",
                   "minuten": "Minuten"}[spaeter.group(3)]
        if spaeter.group(1) == "in":
            return f"In {menge} {einheit} ist es **{dann:%H:%M} Uhr**{anderer_tag}."
        return f"Vor {menge} {einheit} war es **{dann:%H:%M} Uhr**{anderer_tag}."
    # "Wie lange noch bis 18 Uhr?"
    bis_uhr = re.search(r"\b(?:wie\s*(?:lange|viele\s+(?:minuten|stunden))"
                        r"(?:\s+(?:noch|ist\s+es))*|"
                        r"wann\s+ist\s+es)\s+bis\s+(\d{1,2})(?::(\d{2}))?\s*uhr\b", kern)
    if bis_uhr and int(bis_uhr.group(1)) <= 24 and int(bis_uhr.group(2) or 0) < 60:
        from datetime import timedelta

        stunde, minute = int(bis_uhr.group(1)) % 24, int(bis_uhr.group(2) or 0)
        ziel = jetzt.replace(hour=stunde, minute=minute, second=0, microsecond=0)
        if ziel <= jetzt:
            ziel += timedelta(days=1)
        minuten = int((ziel - jetzt).total_seconds() // 60)
        std, rest = divmod(minuten, 60)
        teile = ([f"{std} {'Stunde' if std == 1 else 'Stunden'}"] if std else []) + (
            [f"{rest} {'Minute' if rest == 1 else 'Minuten'}"] if rest else [])
        dauer = " und ".join(teile) or "0 Minuten"
        return f"Bis {stunde:02d}:{minute:02d} Uhr sind es noch **{dauer}**."
    if re.search(r"\b(wie\s*spaet|uhrzeit|wieviel\s+uhr|wie\s+viel\s+uhr)\b", kern):
        return f"Es ist **{jetzt:%H:%M} Uhr** ({zeit_mod.kurz(jetzt)})."
    # 16.4.5: "Welchen Tag haben wir heute?", "Was ist heute für ein Datum?"
    # 16.4.5: "Welcher Wochentag ist morgen?", "Was ist heute in einer Woche?"
    zahlwoerter = {"einer": 1, "einem": 1, "zwei": 2, "drei": 3, "vier": 4}
    kern = re.sub(r"\bin\s+(einer|einem|zwei|drei|vier)\s+(woche|wochen|tag|tagen)\b",
                  lambda t: f"in {zahlwoerter[str(t.group(1))]} {t.group(2)!s}", kern)
    if re.search(r"\b(welche[rs]?\s+wochentag\s+(?:ist|war)\s+(?:morgen|uebermorgen|gestern|"
                 r"vorgestern|(?:heute\s+)?(?:in|vor)\s+\d)|"
                 r"(?:was|welches\s+datum)\s+ist\s+heute\s+in\s+\d|"
                 r"welche[rs]?\s+(tag|datum)|welchen\s+tag\s+haben\s+wir|den\s+wievielten|"
                 r"welches\s+datum|was\s+fuer\s+ein\s+(?:tag|datum)|"
                 r"was\s+(?:ist\s+|war\s+|haben\s+wir\s+)?(?:\w+\s+){0,3}fuer\s+ein\s+"
                 r"(?:datum|tag|wochentag))\b", kern) and not datum_aus(kern, heute) \
            and not _benannter_tag(kern, heute):
        from datetime import timedelta

        # 16.4.5: "Welches Datum war vor 100 Tagen?" nannte vorher das Datum von heute.
        versatz_ = re.search(r"\b(in|vor)\s+(\d{1,4})\s+(tag|tagen|woche|wochen)\b", kern)
        if versatz_:
            tage_ = int(versatz_.group(2)) * (7 if versatz_.group(3).startswith("woche") else 1)
            tag = heute + timedelta(days=tage_ if versatz_.group(1) == "in" else -tage_)
            zeitform = "war" if versatz_.group(1) == "vor" else "ist"
            einheit = versatz_.group(3).capitalize()
            return (f"{versatz_.group(1).capitalize()} {versatz_.group(2)} {einheit} {zeitform} "
                    f"**{WOCHENTAGE[tag.weekday()]}, der {tag:%d.%m.%Y}**.")

        # "Welches Datum ist morgen?" nannte vorher das Datum von heute.
        for wort, name, versatz in (("uebermorgen", "Übermorgen", 2), ("vorgestern", "Vorgestern",
                                    -2), ("morgen", "Morgen", 1), ("gestern", "Gestern", -1)):
            if re.search(rf"\b{wort}\b", kern):
                tag = heute + timedelta(days=versatz)
                zeitform = "war" if versatz < 0 else "ist"
                return (f"{name} {zeitform} **{WOCHENTAGE[tag.weekday()]}, der {tag:%d.%m.%Y}** "
                        f"(KW {tag.isocalendar()[1]}).")
        return (f"Heute ist **{WOCHENTAGE[heute.weekday()]}, der {heute:%d.%m.%Y}** "
                f"(KW {heute.isocalendar()[1]}).")
    # 16.4.5: "Datum", "Datum heute", "heutiges Datum" -- "Uhrzeit" allein ging schon.
    if re.fullmatch(r"(?:das\s+)?(?:datum(?:\s+(?:heute|von\s+heute))?|heutiges\s+datum|"
                    r"heute(?:\s+ist)?\s+(?:der|den)\s+wievielte)", kern):
        return (f"Heute ist **{WOCHENTAGE[heute.weekday()]}, der {heute:%d.%m.%Y}** "
                f"(KW {heute.isocalendar()[1]}).")
    # 16.3.0: "Welcher Wochentag ist heute?", "Was ist heute für ein Tag?", "what day is it".
    if re.search(r"\bwelche[rs]?\s+wochentag\s+(?:ist\s+heute|haben\s+wir(?:\s+heute)?)\b|"
                 r"\bwas\s+(?:ist\s+)?heute\s+fuer\s+ein\s+tag\b|"
                 r"\bwhat\s+day\s+is\s+(?:it|today)\b|\bwhat(?:'s|\s+is)\s+the\s+date\b",
                 kern):
        return (f"Heute ist **{WOCHENTAGE[heute.weekday()]}, der {heute:%d.%m.%Y}** "
                f"(KW {heute.isocalendar()[1]}).")
    # Nur die ganze Frage: "Welcher Monat ist der kälteste?" fragt nach etwas anderem.
    nur_noch = r"(?:\s+(?:gerade|jetzt|heute|eigentlich|denn|aktuell))*$"
    if re.search(r"^(?:welche[sn]?\s+jahr\s+(?:haben\s+wir|ist|schreiben\s+wir)|"
                 r"in\s+welchem\s+jahr\s+(?:sind|leben)\s+wir)" + nur_noch, kern):
        return f"Wir haben das Jahr **{heute.year}**."
    if re.search(r"^welche[rn]?\s+monat\s+(?:haben\s+wir|ist)" + nur_noch, kern):
        name = "März" if heute.month == 3 else MONATE[heute.month - 1].capitalize()
        return f"Wir haben **{name} {heute.year}**."
    if re.search(r"\bkalenderwoche\b", kern) or (
            re.search(r"\bkw\b", kern)
            and not re.search(r"\d\s*(?:kw|ps|w|watt)\b|\b(?:in|nach|zu)\s+(?:kw|ps)\b", kern)):
        # 16.4.5: "Welche KW ist der 1. März?" nannte vorher die Woche von heute.
        tag_kw = datum_aus(kern, heute)
        if tag_kw:
            jahr_kw, woche_kw = tag_kw.isocalendar()[:2]
            return f"Der {tag_kw:%d.%m.%Y} liegt in **KW {woche_kw}** ({jahr_kw})."
        return f"Wir haben **KW {heute.isocalendar()[1]}**."
    if re.search(r"\bwie\s*viele\s+tage\s+hat\s+(?:dieser|der\s+aktuelle|unser)\s+monat\b",
                 kern):
        # 16.4.5: "Wie viele Tage hat dieser Monat?"
        kern = re.sub(r"\b(?:dieser|der\s+aktuelle|unser)\s+monat\b",
                      f"{MONATE[heute.month - 1]} {heute.year}", kern)
    arbeit = re.search(r"\bwie\s*viele\s+(?:arbeits|werk)tage\s+(?:hat|haben|gibt\s+es\s+im)\s+"
                       r"(?:der\s+|dieser\s+|im\s+)?(" + "|".join(MONATE)
                       + r")(?:\s+(\d{4}))?\b", kern)
    if arbeit and 1 <= int(arbeit.group(2) or heute.year) <= 9999:
        # 16.4.5: "Wie viele Arbeitstage hat der Dezember?" ging vorher nicht.
        jahr = int(arbeit.group(2) or heute.year)
        nummer = MONATE.index(arbeit.group(1)) + 1
        letzter = calendar.monthrange(jahr, nummer)[1]
        anzahl = arbeitstage(date(jahr, nummer, 1), date(jahr, nummer, letzter))
        name = "März" if nummer == 3 else arbeit.group(1).capitalize()
        return (f"Der {name} {jahr} hat **{anzahl} Arbeitstage** (Montag bis Freitag, ohne "
                "bundesweite Feiertage).")
    monat = re.search(r"\bwie\s*viele\s+tage\s+hat\s+(?:der\s+|dieser\s+)?(" + "|".join(MONATE)
                      + r")(?:\s+(\d{4}))?\b", kern)
    if monat:
        jahr = int(monat.group(2) or heute.year)
        nummer = MONATE.index(monat.group(1)) + 1
        if 1 <= jahr <= 9999:
            tage = calendar.monthrange(jahr, nummer)[1]
            name = ("März" if nummer == 3 else monat.group(1).capitalize())
            return f"Der {name} {jahr} hat **{tage} Tage**."
    jahr_frage = re.search(r"\bwie\s*viele\s+tage\s+hat\s+(?:das\s+jahr\s+)?(\d{4})\b", kern)
    if jahr_frage and 1 <= int(jahr_frage.group(1)) <= 9999:
        jahr = int(jahr_frage.group(1))
        return f"Das Jahr {jahr} hat **{366 if calendar.isleap(jahr) else 365} Tage**."
    if re.search(r"\bwie\s*(viele|lange)\b.*\bbis\b|\bbis\s+(weihnachten|silvester|ostern)\b|"
                 r"\btage\s+bis\b|\bin\s+wie\s*vielen\s+tagen\b", kern):
        ziele = {"weihnachten": date(heute.year, 12, 24), "heiligabend": date(heute.year, 12, 24),
                 "silvester": date(heute.year, 12, 31), "neujahr": date(heute.year + 1, 1, 1),
                 "ostern": ostern(heute.year)}
        for name, tag in ziele.items():
            if name in kern:
                if tag < heute:
                    tag = (ostern(heute.year + 1) if name == "ostern"
                           else tag.replace(year=tag.year + 1))
                anzeige = {"heiligabend": "Heiligabend"}.get(name, name.capitalize())
                return in_einheit(tage_text((tag - heute).days, anzeige, f"{tag:%d.%m.%Y}"),
                                  kern, (tag - heute).days, heute)
        if re.search(r"\bbis\s+(?:zum\s+)?wochenende\b", kern):
            if heute.weekday() >= 5:
                return "Es ist schon **Wochenende**."
            return tage_text(5 - heute.weekday(), "zum Wochenende", "Samstag")
        wochentag = re.search(r"\bbis\s+(?:zum\s+|naechsten\s+)?(" + "|".join(WOCHENTAG_WORT)
                              + r")\b", kern)
        if wochentag:
            nummer = WOCHENTAG_WORT.index(wochentag.group(1))
            return tage_text((nummer - heute.weekday()) % 7, WOCHENTAGE[nummer])
        gesucht = datum_aus(kern, heute)
        if gesucht:
            if gesucht < heute and not re.search(r"\d{4}", kern):
                gesucht = im_jahr(gesucht, gesucht.year + 1)
            if gesucht >= heute:
                return in_einheit(tage_text((gesucht - heute).days, f"zum {gesucht:%d.%m.%Y}"),
                                  kern, (gesucht - heute).days, heute)
            # "Wie viele Tage bis zum 1.1.2026?" mit einem Datum, das schon war.
            tage = (heute - gesucht).days
            return (f"Der {gesucht:%d.%m.%Y} war vor **{schoen(tage)} "
                    f"{'Tag' if tage == 1 else 'Tagen'}**.")
    seit = re.search(r"\bwie\s*(?:viele|lange)\b.*\bseit\b", kern)
    if seit:
        gesucht = datum_aus(kern, heute)
        if gesucht and gesucht <= heute:
            tage = (heute - gesucht).days
            return (f"Seit dem {gesucht:%d.%m.%Y} sind **{schoen(tage)} "
                    f"{'Tag' if tage == 1 else 'Tage'}** vergangen.")
    treffer = re.search(r"\b(welche[rs]?\s+(?:wochen)?tag\s+(?:ist|war|wird|faellt)|"
                        r"auf\s+welchen\s+tag|welches\s+datum\s+(?:ist|war|hat))\b", kern)
    if treffer:
        gesucht = datum_aus(kern, heute)
        if gesucht:
            zeitform = "war" if gesucht < heute else "ist"
            return f"Der {gesucht:%d.%m.%Y} {zeitform} ein **{WOCHENTAGE[gesucht.weekday()]}**."
        benannt = _benannter_tag(kern, heute)
        if benannt:
            # 16.4.5: "Welcher Tag ist Halloween?" nannte vorher das Datum von heute.
            name, tag = benannt
            zeitform = "war" if tag < heute else "ist"
            return f"{name} {zeitform} am **{WOCHENTAGE[tag.weekday()]}, {tag:%d.%m.%Y}**."
    if re.search(r"\bwann\s+(?:ist|war|wird|faellt)\s+ostern\b", kern):
        osterjahr = jahr_aus(kern)
        if osterjahr:
            # "Wann ist Ostern 2024?" nannte vorher das naechste Ostern.
            tag = ostern(osterjahr)
            return f"Ostersonntag {'war' if tag < heute else 'ist'} am **{tag:%d.%m.%Y}**."
        tag = ostern(heute.year)
        if tag < heute:
            tag = ostern(heute.year + 1)
        return f"Ostersonntag ist am **{tag:%d.%m.%Y}**."
    return ""


def _benannter_tag(kern: str, heute: date) -> tuple[str, date] | None:
    """Ein benannter Tag in *kern* ("heiligabend", "halloween", "tag der arbeit") mit Datum.

    Ohne Jahreszahl der naechste, sonst der im genannten Jahr.
    """
    jahr_ = jahr_aus(kern)
    for jahr in ([jahr_] if jahr_ else [heute.year, heute.year + 1]):
        tage_ = {"heiligabend": ("Heiligabend", date(jahr, 12, 24)),
                 "weihnachten": ("Heiligabend", date(jahr, 12, 24)),
                 "silvester": ("Silvester", date(jahr, 12, 31)),
                 "neujahr": ("Neujahr", date(jahr, 1, 1)),
                 "ostern": ("Ostersonntag", ostern(jahr))}
        tage_.update(anlaesse(jahr))
        nach_name = {name: tag for tag, name in feiertage(jahr)}
        tage_.update({wort: (name, nach_name[name]) for wort, name in FEIERTAG_NAMEN.items()})
        for wort in sorted(tage_, key=len, reverse=True):
            if re.search(rf"\b{re.escape(wort)}\b", kern):
                name, tag = tage_[wort]
                if jahr_ or tag >= heute:
                    return name, tag
                break
    return None


def _sonntag_am_oder_vor(tag: date) -> date:
    from datetime import timedelta

    return tag - timedelta(days=(tag.weekday() + 1) % 7)


def anlaesse(jahr: int) -> dict[str, tuple[str, date]]:
    """Besondere Tage eines Jahres: Suchwort -> (Name, Datum)."""
    from datetime import timedelta

    o = ostern(jahr)
    vierter_advent = _sonntag_am_oder_vor(date(jahr, 12, 24))
    erster_mai = date(jahr, 5, 1)
    muttertag = erster_mai + timedelta(days=(6 - erster_mai.weekday()) % 7 + 7)
    erster_nov = date(jahr, 11, 1)
    vierter_do = erster_nov + timedelta(days=(3 - erster_nov.weekday()) % 7 + 21)
    return {
        "valentinstag": ("Valentinstag", date(jahr, 2, 14)),
        "frauentag": ("Der Frauentag", date(jahr, 3, 8)),
        "rosenmontag": ("Rosenmontag", o - timedelta(days=48)),
        "karneval": ("Rosenmontag", o - timedelta(days=48)),
        "fasching": ("Rosenmontag", o - timedelta(days=48)),
        "aschermittwoch": ("Aschermittwoch", o - timedelta(days=46)),
        "pfingsten": ("Pfingstsonntag", o + timedelta(days=49)),
        "muttertag": ("Muttertag", muttertag),
        # 16.4.5: Die Antwort zu Feiertagen nennt beide -- gefragt kannte sie keiner.
        "fronleichnam": ("Fronleichnam", o + timedelta(days=60)),
        "reformationstag": ("Der Reformationstag", date(jahr, 10, 31)),
        "fruehlingsanfang": ("Der Frühlingsanfang", date(jahr, 3, 20)),
        "sommeranfang": ("Der Sommeranfang", date(jahr, 6, 21)),
        "herbstanfang": ("Der Herbstanfang", date(jahr, 9, 23)),
        "winteranfang": ("Der Winteranfang", date(jahr, 12, 21)),
        "halloween": ("Halloween", date(jahr, 10, 31)),
        "black friday": ("Black Friday", vierter_do + timedelta(days=1)),
        "nikolaus": ("Nikolaus", date(jahr, 12, 6)),
        "1. advent": ("Der 1. Advent", vierter_advent - timedelta(days=21)),
        "erste advent": ("Der 1. Advent", vierter_advent - timedelta(days=21)),
        "ersten advent": ("Der 1. Advent", vierter_advent - timedelta(days=21)),
        "erster advent": ("Der 1. Advent", vierter_advent - timedelta(days=21)),
        "4. advent": ("Der 4. Advent", vierter_advent),
        "heiligabend": ("Heiligabend", date(jahr, 12, 24)),
        "weihnachten": ("Heiligabend", date(jahr, 12, 24)),
        "silvester": ("Silvester", date(jahr, 12, 31)),
    }


def anlass(text: str, heute: date) -> str:
    """"Wann ist Muttertag?", "Wie viele Tage bis Halloween?", "Wann ist die Zeitumstellung?"."""
    kern = falten(text)
    if re.search(r"\b(zeitumstellung|sommerzeit|winterzeit|"
                 r"uhr(?:en)?\s+(?:\w+\s+)?um(?:ge)?stell\w*|"
                 r"uhr\s+(?:vor|zurueck)\w*)\b", kern):
        for jahr in (heute.year, heute.year + 1):
            for monat, satz in ((3, "Die Uhr springt von 2 auf 3 Uhr vor – ab dann gilt die "
                                    "Sommerzeit."),
                                (10, "Die Uhr geht von 3 auf 2 Uhr zurück – ab dann gilt die "
                                     "Winterzeit. Du kannst eine Stunde länger schlafen.")):
                tag = _sonntag_am_oder_vor(date(jahr, monat, 31))
                if tag >= heute:
                    wann = "heute" if tag == heute else in_tagen((tag - heute).days)
                    return (f"Die nächste Zeitumstellung ist am **Sonntag, {tag:%d.%m.%Y}** – "
                            f"{wann}. {satz}")
    if not re.search(r"\b(wann|wie\s*(?:viele|vielen|lange)|tage\s+bis|bis\s+zum?)\b", kern):
        return ""
    # 16.4.5: "Wann beginnt der Winter?", "Winterbeginn" -- nur "Winteranfang" ging.
    zeiten = {"fruehling": "fruehlingsanfang", "fruehlings": "fruehlingsanfang",
              "sommer": "sommeranfang", "herbst": "herbstanfang", "winter": "winteranfang"}
    kern = re.sub(r"\b(?:beginnt|startet|faengt)\s+(?:der\s+|das\s+)?(fruehling|sommer|herbst|"
                  r"winter)\b|\b(fruehlings|sommer|herbst|winter)beginn\b",
                  lambda t: zeiten[t.group(1) or t.group(2)], kern)
    jahr_genannt = jahr_aus(kern)
    if jahr_genannt:
        # "Wann ist Pfingsten 2026?" nannte vorher das naechste Pfingsten.
        for wort, (name, tag) in anlaesse(jahr_genannt).items():
            if wort in kern:
                if tag == heute:
                    return f"{name} ist **heute**!"
                zeitform = "war" if tag < heute else "ist"
                return f"{name} {zeitform} am **{WOCHENTAGE[tag.weekday()]}, {tag:%d.%m.%Y}**."
        return ""
    for jahr in (heute.year, heute.year + 1):
        for wort, (name, tag) in anlaesse(jahr).items():
            if wort in ("heiligabend", "weihnachten", "silvester") and not re.search(
                    r"\bwann\b", kern):
                continue  # "Wie viele Tage bis Weihnachten?" beantwortet zeit() wie bisher.
            if wort in kern and tag >= heute:
                if tag == heute:
                    return f"{name} ist **heute**!"
                return (f"{name} ist am **{WOCHENTAGE[tag.weekday()]}, {tag:%d.%m.%Y}** – "
                        f"{in_tagen((tag - heute).days)}.")
    return ""


# -- Zufall und Spass ---------------------------------------------------------------------------

WITZE = (
    "Treffen sich zwei Magneten. Sagt der eine: „Was soll ich heute bloß anziehen?“",
    "Warum können Geister so schlecht lügen? Weil man durch sie hindurchsieht.",
    "Was macht ein Pirat am Computer? Er drückt die Enter-Taste.",
    "Wie nennt man einen Bumerang, der nicht zurückkommt? Stock.",
    "Was ist orange und läuft durch den Wald? Eine Wanderine.",
    "Treffen sich zwei Kerzen. Fragt die eine: „Ist Wachs gefährlich?“",
)


NICHT_WAHL = re.compile(
    r"\b(was|wie|wer|wann|wo|warum|wieso|welche[rsmn]?|ist|sind|war|wird|werden|hat|haben|kann|"
    r"kannst|gibt|regnet|schneit|scheint|wetter|heute|morgen|uebermorgen|wochenende|kopf|zahl|"
    r"brauche|braucht|muss|darf|soll|sollte)\b|\d")


def zufall(text: str, wuerfel: random.Random | None = None) -> str:
    rnd = wuerfel or random.SystemRandom()
    kern = falten(text)
    if re.search(r"\bwuerf(el|le|eln)?\b", kern):
        # "Würfle 3 Würfel" und "einen W20": vorher immer ein Würfel mit sechs Seiten.
        seiten_ = re.search(r"\b(?:w|d)(4|6|8|10|12|20|100)\b", kern)
        anzahl_ = re.search(r"\b([2-9]|10|zwei|drei|vier|fuenf)\s+(?:w|d)?(?:\d+\s+)?wuerfel", kern)
        seiten = int(seiten_.group(1)) if seiten_ else 6
        woerter = {"zwei": 2, "drei": 3, "vier": 4, "fuenf": 5}
        anzahl = (woerter.get(anzahl_.group(1)) or int(anzahl_.group(1))) if anzahl_ else 1
        # 16.4.5: "Würfle 3W6", "2d20" -- vorher ein Wurf mit sechs Seiten.
        kombi = re.search(r"\b([1-9]|1\d|20)\s*[wd](4|6|8|10|12|20|100)\b", kern)
        if kombi:
            anzahl, seiten = int(kombi.group(1)), int(kombi.group(2))
        wuerfe = [rnd.randint(1, seiten) for _ in range(anzahl)]
        art = f" (W{seiten})" if seiten != 6 else ""
        if anzahl == 1:
            return f"🎲 Gewürfelt{art}: **{wuerfe[0]}**"
        return (f"🎲 Gewürfelt{art}: {' + '.join(str(w) for w in wuerfe)} = **{sum(wuerfe)}**")
    if re.search(r"\b(muenze|kopf\s+oder\s+zahl)\b", kern):
        return f"🪙 **{rnd.choice(('Kopf', 'Zahl'))}**"
    # 16.4.5: "Nenn mir eine Zahl zwischen 10 und 5" kannte Standard vorher nicht.
    treffer = re.search(r"zufallszahl(?:\s+zwischen)?\s+(-?\d+)\s+(?:und|bis|-)\s+(-?\d+)|"
                        r"^(?:(?:nenn|gib|sag|zieh|waehl)\w*\s+(?:mir\s+)?)?(?:eine\s+)?zahl\s+"
                        r"zwischen\s+(-?\d+)\s+und\s+(-?\d+)$", kern)
    if treffer:
        a, b = sorted(int(z) for z in treffer.groups() if z is not None)
        return f"Zufallszahl: **{rnd.randint(a, b)}**"
    if re.search(r"\bzufallszahl\b", kern):
        return f"Zufallszahl zwischen 1 und 100: **{rnd.randint(1, 100)}**"
    # 16.4.5: "Wähle zwischen Pizza und Pasta", "Wähle: rot, blau oder grün" -- vorher kam
    # "kann ich nicht" bzw. "Wähle: rot, blau" als eine Wahl.
    liste = re.match(r"^(?:w(?:ä|ae)hle?|entscheide?|such\s+(?:mir\s+)?aus)\b\s*"
                     r"(?:mir\s+)?(?:bitte\s+)?"
                     r"(?:zwischen\s+|aus\s+|eins?\s+aus\s+)?:?\s*(.+?)[?!. ]*$",
                     str(text).strip(), re.I)
    if liste:
        teile = [t.strip(" „“\"'") for t in re.split(r"\s*,\s*|\s+(?:oder|und|or|and)\s+",
                                                   liste.group(1)) if t.strip(" „“\"'")]
        # Nur Befehle mit kurzen Optionen: "Wählt man den Kanzler direkt oder indirekt?"
        # ist eine Frage, keine Wahl.
        if (2 <= len(teile) <= 20 and all(len(t.split()) <= 4 for t in teile)
                and not NICHT_WAHL.search(falten(liste.group(1)))):
            return f"Ich würde sagen: **{rnd.choice(teile)}**."
    treffer = re.match(r"^((?:[^\s,]+,?\s+){1,9}[^\s,]+),?\s+oder\s+((?:\S+\s+){0,2}"
                       r"[^\s?!.]+)[?!. ]*$", str(text).strip(), re.I)
    teile = [t.strip() for t in treffer.group(1).split(",") if t.strip()] if treffer else []
    # Nur kurze Listen ("Rot, Blau oder Grün?") -- kein beliebiger Satz mit Komma und "oder".
    if (treffer and len(teile) >= 2 and not NICHT_WAHL.search(kern)
            and all(len(t.split()) <= 2 and not re.search(r"\b(?:und|and)\b", t, re.I)
                    for t in [*teile, treffer.group(2)])):
        return f"Ich würde sagen: **{rnd.choice([*teile, treffer.group(2)])}**."
    treffer = re.match(r"^soll\s+ich\s+(?:lieber\s+)?(.{1,60}?)\s+oder\s+(.{1,60}?)"
                       r"(?:\s+(?:essen|machen|nehmen|kaufen|tun|gehen|spielen))?[?!. ]*$",
                       str(text).strip(), re.I)
    if treffer:
        return f"Ich würde sagen: **{rnd.choice((treffer.group(1), treffer.group(2)))}**."
    treffer = re.match(r"^((?:\S+\s+){0,2}\S+)\s+oder\s+((?:\S+\s+){0,2}[^\s?!.]+)[?!. ]*$",
                       str(text).strip(), re.I)
    if treffer and not NICHT_WAHL.search(kern):
        if falten(treffer.group(1)) == "ja" and falten(treffer.group(2)) == "nein":
            return f"Meine Antwort: **{rnd.choice(('Ja', 'Nein'))}**."
        return f"Ich würde sagen: **{rnd.choice((treffer.group(1), treffer.group(2)))}**."
    if re.search(r"\b(witz|erzaehl\s+(mir\s+)?was\s+lustiges)\b", kern):
        return rnd.choice(WITZE)
    return ""


# -- Wetter -------------------------------------------------------------------------------------

WETTERCODES = {0: "klar ☀️", 1: "überwiegend klar 🌤️", 2: "teils bewölkt ⛅", 3: "bedeckt ☁️",
               45: "Nebel 🌫️", 48: "Nebel mit Reif 🌫️", 51: "leichter Niesel 🌦️",
               53: "Niesel 🌦️", 55: "starker Niesel 🌧️", 61: "leichter Regen 🌦️",
               63: "Regen 🌧️", 65: "starker Regen 🌧️", 66: "gefrierender Regen 🌧️",
               67: "starker gefrierender Regen 🌧️", 71: "leichter Schnee 🌨️", 73: "Schnee 🌨️",
               75: "starker Schnee ❄️", 77: "Schneegriesel 🌨️", 80: "Regenschauer 🌦️",
               81: "kräftige Schauer 🌧️", 82: "heftige Schauer ⛈️", 85: "Schneeschauer 🌨️",
               86: "kräftige Schneeschauer ❄️", 95: "Gewitter ⛈️", 96: "Gewitter mit Hagel ⛈️",
               99: "schweres Gewitter mit Hagel ⛈️"}
WETTER_WORT = re.compile(r"\b(wetter|wettervorhersage|wetterbericht|wetterlage|weather|forecast|"
                         r"raining|temperature|wie\s*viel\s+grad|grad\s+(?:hat|haben|sind)|"
                         r"regnet|regnen|regen|sonne|sonnig|temperatur|grad\s+warm|"
                         r"wie\s+warm|wie\s+kalt|schnee|schneit|schneien|gewitter|vorhersage|"
                         r"wind|windig|sturm|frost|glatt|glatteis|draussen|"
                         # 16.4.5: "Ist es heute neblig?", "Friert es morgen?", "Brauche ich
                         # Sonnencreme?", "Wie hoch ist die Regenwahrscheinlichkeit?"
                         r"nebel|neblig|friert\s+es|es\s+friert|es\s+frieren|sonnencreme|"
                         r"regenwahrscheinlichkeit|"
                         r"niederschlag|regenrisiko|hagel|hagelt|nieselt|niesel)\b|"
                         r"\bwie\s+wird\s+(?:es|das\s+wochenende|der\s+tag|der\s+\w+tag|"
                         r"die\s+(?:naechste\s+|kommende\s+)?woche|heute|morgen|uebermorgen)\b|"
                         r"\bwird\s+es\s+(?:heute|morgen|uebermorgen|am\s+\w+)?\s*"
                         r"(?:warm|kalt|nass|schoen|heiss|trocken)\b|"
                         # "Wird es am Samstag in Berlin warm?" -- der Ort steht dazwischen (16.4.5)
                         r"\bwird\s+es\b(?:\s+\S+){1,6}?\s+(?:warm|kalt|nass|schoen|heiss|"
                         r"trocken)\b")
ANZIEHEN_WORT = re.compile(r"\b(anziehen|anzieh|kleidung|klamotten|jacke|mantel|pulli|pullover|"
                           r"kurze\s+hose|kurzer?\s+hose|muetze|handschuhe|t-?shirt|outfit|"
                           r"what\s+(?:should\s+i|to)\s+wear)\b|"
                           # "Was ziehe ich morgen in Berlin an?" -- getrenntes Verb (16.4.5)
                           r"\bzieh(?:e|st|t)?\s+(?:ich|man|wir|du)\b.*\ban\b")
#: 16.3.0: "Kann ich heute joggen gehen?" -- das entscheidet das Wetter.
DRAUSSEN = re.compile(r"\b(?:kann|koennen|soll|sollte|sollten)\s+(?:ich|man|wir)\b.*\b(?:joggen|"
                      r"laufen\s+gehen|radfahren|rad\s+fahren|fahrrad\s+fahren|grillen|"
                      r"baden\s+gehen|schwimmen\s+gehen|spazieren|wandern|draussen)\b")
SCHIRM_WORT = re.compile(r"\b((regen)?schirm|umbrella|nass\s+werden|regenjacke)\b|"
                         # "Werde ich in Berlin nass?" (16.4.5)
                         r"\b(?:werde\s+ich|werden\s+wir|wird\s+man)\b.*\bnass\b")
SONNE_WORT = re.compile(r"\b(sonnenaufgang|sonnenuntergang|sonne\s+(?:auf|unter)|"
                        r"geht\s+die\s+sonne|wird\s+es\s+(?:hell|dunkel)|sunrise|sunset)\b|"
                        # "Wann geht morgen die Sonne in Berlin auf?" (16.4.5)
                        r"\bgeht\s+(?:\S+\s+){1,2}?die\s+sonne\b|"
                        r"\bwann\b.*\bsonne\b(?:\s+\S+){0,4}?\s+(?:auf|unter)\b|"
                        # "Wann wird es in Berlin dunkel?" (16.4.5)
                        r"\bwann\s+wird\s+es\b(?:\s+\S+){0,5}?\s+(?:hell|dunkel)\b")
# 16.4.5: "was fuer" ist keine Ortsangabe ("Was für Wetter ist in Berlin?" suchte vorher
# den Ort "ist in berlin").
ORT_NACH = re.compile(r"\b(?<!was\s)(?:in|fuer|bei|um|im)\s+([a-z][a-z\s.\-]{1,60}?)"
                      r"(?:\s+(?:heute|morgen|uebermorgen|am\s+wochenende|diese\s+woche|"
                      r"die\s+naechsten\s+tage|am\s+\w+tag|am\s+mittwoch|am\s+samstag|"
                      r"am\s+sonntag|an|aus|anziehen|mitnehmen))?$")
#: 16.3.0: Der Ort ohne "in" -- "Wetter Hamburg", "Hamburg Wetter".
_KEIN_ORTSWORT = (r"(?!.*\b(?:wie|wird|ist|sind|war|das|der|die|was|es|gibt|ein|eine|kein|so|"
                  r"gut|gutes|schlecht|schlechtes|schoen|schoenes|mies|mieses|toll|tolles|super|"
                  r"bitte|ich|du|mir|dir|fuer|heute|morgen|uebermorgen|aktuell|gerade)\b)")
#: 16.4.5: auch "Regen Berlin", "Nebel Hamburg" -- vorher kam die Rueckfrage nach dem Ort,
#: obwohl er dastand. Nicht hinten: "leichter Regen" ist kein Ort "leichter".
_WETTER_NOMEN = r"(?:regen|schnee|nebel|hagel|sturm|frost|gewitter|glatteis|wind)"
ORT_OHNE = re.compile(r"^(?:wie\s+ist\s+)?(?:das\s+)?(?:wetter|wetterbericht|wettervorhersage|"
                      r"vorhersage|weather|forecast|temperatur|" + _WETTER_NOMEN[3:-1] + r")\s+"
                      + _KEIN_ORTSWORT + r"([a-z][a-z\s.\-]{1,40}?)$|^" + _KEIN_ORTSWORT
                      + r"([a-z][a-z\s.\-]{1,40}?)\s+(?:wetter|weather)$")
ZEIT_WORTE = (r"\b(?:am\s+)?(?:wochenende|montag|dienstag|mittwoch|donnerstag|freitag|samstag|"
              r"sonntag)\b|\b(?:heute|morgen|uebermorgen)(?:\s+(?:frueh|abend|nacht|mittag))?\b|"
              r"\b(?:die\s+)?(?:naechsten|kommenden)\s+tage\b|"
              r"\b(?:diese|naechste|kommende|ganze|die)\s+woche\b")
#: Fuellwoerter im Ortsteil einer Frage -- ohne "am", damit "Frankfurt am Main" ganz bleibt.
ORT_FUELL = (r"\b(wetter|das|die|der|den|regnen|regnet|schneien|schneit|sonnig|warm|kalt|werden|"
             r"wird|es|sein|geben|anziehen|mitnehmen|soll|ich|einen|schirm|regenschirm|jacke|"
             r"brauche|draussen|gerade|jetzt|aktuell|bitte|denn|eigentlich|so|joggen|laufen|"
             r"gehen|radfahren|fahren|grillen|baden|schwimmen|spazieren|wandern|kann|man|ein|"
             r"schoenes|gutes|tolles|herrliches|schlechtes|mieses|"
             # Reste aus Anziehen-, Schirm- und Sonnenfragen ("Berlin eine Mütze", "Berlin
             # die Sonne auf") gingen vorher mit in die Ortssuche (16.4.5).
             r"eine|einer|muetze|hose|kurze|pulli|pullover|mantel|handschuhe|schal|"
             r"sonnenbrille|sonnencreme|sonne|nass|dunkel|hell|zieh|ziehe|"
             # "Kann man am Wochenende in Hamburg Fahrrad fahren?" suchte "Hamburg Fahrrad".
             r"fahrrad|rad|ski|skifahren|schlitten|eislaufen|segeln|surfen|neblig|friert|"
             r"regenwahrscheinlichkeit|niederschlag)\b")
#: Nach "in/im/für/bei" steht nicht immer ein Ort.
NICHT_ORT = frozenset({
    "mir", "uns", "dir", "mich", "hier", "hause", "zuhause", "moment", "augenblick", "urlaub",
    "arbeit", "schule", "buero", "uni", "party", "hochzeit", "sport", "spaziergang", "wandern",
    "date", "feier", "konzert", "festival", "freien", "garten", "sommer", "winter", "fruehling",
    "herbst", "nacht", "abend", "morgen", "allgemeinen", "prinzip", "kuerze", "ordnung", "ruhe",
    "naehe", "gegend", "region", "umgebung", "stadt", "dorf", "land", "ausland", "norden",
    "sueden", "osten", "westen", "regen", "schnee", "sonne", "wind", "sturm", "januar",
    "februar", "maerz", "april", "mai", "juni", "juli", "august", "september", "oktober",
    "november", "dezember"})
DAHEIM = re.compile(r"\b(bei\s+(?:mir|uns)|hier|zu\s*hause|daheim|vor\s+der\s+tuer)\b")
KEIN_ORT = re.compile(r"^(keine\s+ahnung|k\.?\s?a\.?|weiss\s+(?:ich\s+)?(?:es\s+)?nicht|"
                      r"ich\s+weiss\s+(?:es\s+)?nicht|egal|nichts|nirgends|nirgendwo|"
                      r"vergiss\s+es|abbrechen|abbruch|lass\s+(?:mal|es)|schon\s+gut|"
                      r"hat\s+sich\s+erledigt|spaeter|nicht\s+so\s+wichtig|doch\s+nicht|"
                      r"stop|stopp)\b")
NICHT_ERREICHBAR = ("Der Wetterdienst antwortet gerade nicht. Versuch es gleich noch einmal – "
                    "am Ort liegt es nicht.")
QUELLE_WETTER = "\n\nQuelle: [Open-Meteo](https://open-meteo.com)"
ORT_FRAGE = "Für welchen Ort soll ich nachsehen?"
ORT_BEISPIEL = " Schreib einfach den Namen, zum Beispiel „Berlin“."
WOCHENTAG_KURZ = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
WOCHENTAG_WORT = ("montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag")


def waehle(optionen: tuple[str, ...], schluessel: str) -> str:
    """Eine Formulierung je Frage -- abwechslungsreich, aber fuer dieselbe Frage immer gleich."""
    import hashlib

    nummer = int(hashlib.sha256(schluessel.encode("utf-8")).hexdigest()[:8], 16)
    return optionen[nummer % len(optionen)]


def tage_aus(kern: str, heute: date) -> list[int]:
    """Welche Tage gemeint sind: [0] heute, [1] morgen, Wochenende, Wochentag, naechste Tage."""
    if re.search(r"\b(?:naechste|kommende)\s+woche\b", kern):
        # 16.4.5: "nächste Woche" zeigte vorher ab heute -- jetzt ab dem nächsten Montag.
        montag = 7 - heute.weekday()
        return list(range(montag, 7)) if montag < 7 else list(range(0, 7))
    if re.search(r"\b(naechsten\s+tage|diese\s+woche|ganze\s+woche|woche|7\s+tage)\b", kern):
        return list(range(0, 7))
    # "Wetter in 10 Tagen" zeigte vorher stillschweigend heute (16.4.5).
    in_tagen = re.search(r"\bin\s+(\d{1,3}|zwei|drei|vier|fuenf|sechs|sieben|acht|neun|zehn)"
                         r"\s+tagen\b", kern)
    if in_tagen:
        woerter = {"zwei": 2, "drei": 3, "vier": 4, "fuenf": 5, "sechs": 6, "sieben": 7,
                   "acht": 8, "neun": 9, "zehn": 10}
        return [woerter.get(in_tagen.group(1)) or int(in_tagen.group(1))]
    if "wochenende" in kern:
        if heute.weekday() == 6 and not re.search(r"\b(?:naechste|kommende)s?\s+wochenende", kern):
            # 16.4.5: Am Sonntag ist noch Wochenende -- vorher kam der Samstag der neuen Woche.
            return [0]
        sa = (5 - heute.weekday()) % 7
        return [sa, sa + 1] if sa + 1 < 7 else [sa]
    if "uebermorgen" in kern:
        return [2]
    if re.search(r"\b(?:morgen|tomorrow)\b", kern):
        return [1]
    for nummer, name in enumerate(WOCHENTAG_WORT):
        if re.search(rf"\b(am\s+)?{name}\b", kern):
            return [(nummer - heute.weekday()) % 7]
    return [0]


def tag_aus(kern: str) -> int:
    if "uebermorgen" in kern:
        return 2
    if re.search(r"\bmorgen\b", kern):
        return 1
    return 0


def original(frage: str, gefaltet: str) -> str:
    """Die Schreibweise aus der Frage (mit Umlauten) fuer einen gefalteten Ausschnitt.

    Der Wetterdienst findet "München" sicher, "muenchen" nicht immer.
    """
    worte = re.findall(r"[^\s,;:?!]+", frage)
    gesucht = [w.strip(".") for w in gefaltet.split()]
    gefaltete = [falten(w).strip(".") for w in worte]
    for i in range(len(worte) - len(gesucht) + 1):
        if gesucht and gefaltete[i:i + len(gesucht)] == gesucht:
            teile = worte[i:i + len(gesucht)]
            teile[-1] = teile[-1].rstrip(".")
            return " ".join(teile)
    return gefaltet


def orte_aus(frage: str) -> list[str]:
    """Die Orte einer Frage: "in Erkelenz und in Köln" -> ["Erkelenz", "Köln"] (hoechstens 3)."""
    kern = re.sub(r"\b(?:im\s+moment|im\s+augenblick|zur\s+zeit|zurzeit|momentan)\b", " ",
                  falten(frage))
    kern = re.sub(r"\s+", " ", kern).strip()
    # "Wetter Berlin morgen", "Berlin Wetter am Montag": ohne "in" stoerte der Tag (16.4.5).
    ohne_zeit = re.sub(r"\s+", " ", re.sub(ZEIT_WORTE, " ", kern)).strip()
    treffer = ORT_NACH.search(kern) or ORT_OHNE.search(kern) or ORT_OHNE.search(ohne_zeit)
    if not treffer:
        return []
    rest = re.sub(ZEIT_WORTE, " ", next(g for g in treffer.groups() if g))
    orte: list[str] = []
    for teil in re.split(r"\s+(?:und|oder|sowie)\s+|\s*,\s*", rest):
        teil = re.sub(r"^\s*(?:in|im|fuer|bei|um)\s+", "", teil)
        # 16.4.5: "für eine Radtour in Köln" -- der Ort steht hinter dem zweiten "in".
        teil = re.sub(r"^(?:eine?[nmr]?|den|die|das|der)\s+[a-z]+\s+(?:in|bei)\s+", "", teil)
        teil = re.sub(r"\s+", " ", re.sub(ORT_FUELL, " ", teil)).strip(" .-")
        teil = re.sub(r"^(?:am|und|in)\s+|\s+(?:am|und|in|an|auf|unter)$", "", teil).strip(" .-")
        if not teil or teil in NICHT_ORT or teil.split()[-1] in NICHT_ORT:
            continue
        ort = original(frage, teil)
        if ort not in orte:
            orte.append(ort)
    return orte[:3]


def ort_aus(frage: str) -> str:
    orte = orte_aus(frage)
    return orte[0] if orte else ""


def _liste(werte: Any, n: int) -> list[Any]:
    return list(werte)[:n] + [None] * max(0, n - len(werte)) if isinstance(werte, list) else (
        [None] * n)


def wetterdaten(ort: str, holen: Holen, heute: date | None = None) -> dict[str, Any] | str:
    """Vorhersage fuer sieben Tage. Returns: die Daten -- oder einen Satz, warum nicht."""
    geo = holen("https://geocoding-api.open-meteo.com/v1/search?count=1&language=de&name="
                + quote(ort))
    if not isinstance(geo, dict):
        return NICHT_ERREICHBAR
    treffer = geo.get("results") or []
    if not treffer:
        return (f"Hm, einen Ort namens „{ort}“ finde ich nicht. Magst du ihn anders schreiben, "
                "vielleicht mit dem Land dazu?")
    stelle = treffer[0] if isinstance(treffer, list) else None
    # Fremde Daten: ohne Zahlen fuer Breite und Laenge gibt es keine Vorhersage.
    if not isinstance(stelle, dict) or not all(
            isinstance(stelle.get(k), (int, float)) and not isinstance(stelle.get(k), bool)
            for k in ("latitude", "longitude")):
        return NICHT_ERREICHBAR
    daten = holen("https://api.open-meteo.com/v1/forecast?latitude={}&longitude={}&daily="
                  "weather_code,temperature_2m_max,temperature_2m_min,"
                  "apparent_temperature_max,apparent_temperature_min,"
                  "precipitation_probability_max,precipitation_sum,wind_speed_10m_max,"
                  "uv_index_max,sunrise,sunset&current=temperature_2m,apparent_temperature,"
                  "weather_code,wind_speed_10m&timezone=auto&forecast_days=7"
                  .format(stelle.get("latitude"), stelle.get("longitude")))
    if not isinstance(daten, dict) or not isinstance(daten.get("daily"), dict):
        return NICHT_ERREICHBAR
    t = daten["daily"]
    n = len(t.get("weather_code") or []) or 1
    spalten = {k: _liste(t.get(k), n) for k in (
        "time", "weather_code", "temperature_2m_max", "temperature_2m_min",
        "apparent_temperature_max", "apparent_temperature_min", "precipitation_probability_max",
        "precipitation_sum", "wind_speed_10m_max", "uv_index_max", "sunrise", "sunset")}
    for k, werte in spalten.items():
        if k not in ("time", "sunrise", "sunset"):
            # Was keine Zahl ist, gilt als fehlend -- sonst bricht "°C" an einem Text ab.
            spalten[k] = [w if isinstance(w, (int, float)) and not isinstance(w, bool) else None
                          for w in werte]
    tage = []
    for i in range(n):
        try:
            datum = (date.fromisoformat(str(spalten["time"][i])[:10]) if spalten["time"][i]
                     else (heute or date.today()).fromordinal((heute or date.today())
                                                              .toordinal() + i))
        except ValueError:
            datum = None
        tage.append({"datum": datum, "code": spalten["weather_code"][i],
                     "hoch": spalten["temperature_2m_max"][i],
                     "tief": spalten["temperature_2m_min"][i],
                     "gefuehlt_hoch": spalten["apparent_temperature_max"][i],
                     "gefuehlt_tief": spalten["apparent_temperature_min"][i],
                     "regen": spalten["precipitation_probability_max"][i],
                     "menge": spalten["precipitation_sum"][i],
                     "wind": spalten["wind_speed_10m_max"][i], "uv": spalten["uv_index_max"][i],
                     "auf": spalten["sunrise"][i], "unter": spalten["sunset"][i]})
    jetzt = daten.get("current")
    return {"name": str(stelle.get("name") or ort), "zone": str(stelle.get("timezone") or ""),
            "tage": tage, "jetzt": jetzt if isinstance(jetzt, dict) else {}}


def _grad(wert: Any) -> str:
    return "?" if wert is None else schoen(float(wert), 0)


def _tagesname(tag: int, datum: date | None) -> str:
    if tag < 3:
        return ("Heute", "Morgen", "Übermorgen")[tag]
    if datum is None:
        return f"In {tag} Tagen"
    return f"{WOCHENTAGE[datum.weekday()]}, {datum:%d.%m.}"


def _einschaetzung(t: dict[str, Any]) -> str:
    """Ein Satz, wie sich der Tag anfuehlt -- wie man es einem Freund sagen wuerde."""
    hoch = t.get("hoch")
    regen = t.get("regen") or 0
    code = int(t.get("code") or 0)
    wind = t.get("wind") or 0
    if code >= 95:
        return "Bei Gewitter bleibst du am besten drinnen."
    if code in (66, 67) or (t.get("tief") is not None and t["tief"] <= 0 and regen >= 40):
        return "Pass auf, es kann glatt werden."
    if t.get("tief") is not None and t["tief"] <= 0:
        return "Morgens ist es frostig – auf Brücken und Gehwegen kann es glatt sein."
    if code >= 71 and code <= 86 and code not in (80, 81, 82):
        return "Schnee! Zieh dich warm an und plane mehr Zeit ein."
    if regen >= 70:
        return "Ziemlich nass – ein Schirm lohnt sich auf jeden Fall."
    if wind >= 50:
        return "Es wird stürmisch, halt deinen Hut fest."
    if hoch is not None and hoch >= 28:
        return "Richtig warm! Trink genug und denk an Sonnencreme."
    if hoch is not None and hoch >= 20 and regen < 30:
        return "Schönes Wetter, um rauszugehen."
    if hoch is not None and hoch <= 5:
        return "Ganz schön frisch, eine warme Jacke ist eine gute Idee."
    if regen >= 40:
        return "Ein paar Tropfen sind drin, also lieber einen Schirm einpacken."
    return "Ein ziemlich normaler Tag, nichts Besonderes zu beachten."


#: Wettercodes mit Schnee (WMO): leichter bis starker Schnee, Schneegriesel, Schneeschauer.
SCHNEE_CODES = frozenset({71, 73, 75, 77, 85, 86})


def _tageszeile(d: dict[str, Any], i: int) -> str:
    """"**Heute in Erkelenz:** leichter Regen, -1 bis 7 °C, Regenrisiko 39 %. Gerade ..."."""
    t = d["tage"][i]
    zeile = (f"**{_tagesname(i, t['datum'])} in {d['name']}:** "
             f"{WETTERCODES.get(int(t['code'] or 0), 'wechselhaft')}, "
             f"{_grad(t['tief'])} bis {_grad(t['hoch'])} °C")
    if t.get("regen") is not None:
        # Bei Schnee ist es kein Regen: die Zahl ist das Risiko fuer Niederschlag (16.4.5).
        wort = "Schneerisiko" if int(t["code"] or 0) in SCHNEE_CODES else "Regenrisiko"
        zeile += f", {wort} {t['regen']} %"
    zeile += "."
    jetzt = d["jetzt"]
    if i == 0 and jetzt.get("temperature_2m") is not None:
        zeile += f" Gerade sind es {_grad(jetzt['temperature_2m'])} °C"
        gefuehlt = jetzt.get("apparent_temperature")
        if gefuehlt is not None and abs(float(gefuehlt) - float(jetzt["temperature_2m"])) >= 2:
            zeile += f", gefühlt eher {_grad(gefuehlt)} °C"
        zeile += "."
    return zeile


def wetter_mehrere(orte: list[str], kern: str, holen: Holen, heute: date) -> str:
    """Mehrere Orte nebeneinander: "Wetter in Erkelenz und in Köln"."""
    tag = tage_aus(kern, heute)[0]
    zeilen: list[str] = []
    waermster: tuple[float, str] | None = None
    for ort in orte:
        daten = wetterdaten(ort, holen, heute)
        if isinstance(daten, str):
            if daten == NICHT_ERREICHBAR:
                return daten
            zeilen.append(f"- {daten}")
            continue
        if tag >= len(daten["tage"]):
            return "So weit kann ich leider nicht vorausschauen – nur sieben Tage."
        zeilen.append("- " + _tageszeile(daten, tag))
        hoch = daten["tage"][tag].get("hoch")
        if hoch is not None and (waermster is None or float(hoch) > waermster[0]):
            waermster = (float(hoch), str(daten["name"]))
    schluss = ""
    if waermster and sum(1 for z in zeilen if z.startswith("- **")) > 1:
        schluss = f"\n\nAm wärmsten wird es in **{waermster[1]}**."
    return "Gern, hier ist der Vergleich:\n\n" + "\n".join(zeilen) + schluss + QUELLE_WETTER


def wetter_text(d: dict[str, Any], tage: list[int], frage: str = "") -> str:
    name = d["name"]
    verfuegbar = [i for i in tage if i < len(d["tage"])]
    if not verfuegbar:
        return f"So weit kann ich für {name} leider nicht vorausschauen – nur sieben Tage."
    if len(verfuegbar) == 1:
        i = verfuegbar[0]
        t = d["tage"][i]
        zeile = _tageszeile(d, i)
        tipp = _einschaetzung(t)
        ideen = ["Willst du wissen, was du am besten anziehst?"]
        ideen.append("Soll ich auch nach morgen schauen?" if i == 0 else
                     "Soll ich dir auch die nächsten Tage zeigen?")
        if (t.get("regen") or 0) < 40:
            ideen.append("Frag mich gern, ob du einen Schirm brauchst.")
        weiter = waehle(tuple(ideen), name + frage + str(i))
        vorn = waehle(("Ich hab für dich nachgesehen.", "Klar, hier ist das Wetter.",
                       "Gern, so sieht es aus.", "Hier kommt die Vorhersage."), name + frage)
        return f"{vorn}\n\n{zeile}\n\n{tipp} {weiter}{QUELLE_WETTER}"
    kopf = ("Das Wochenende" if len(verfuegbar) == 2 and d["tage"][verfuegbar[0]]["datum"] and
            d["tage"][verfuegbar[0]]["datum"].weekday() == 5 else
            "Die nächste Woche" if verfuegbar[0] > 0 and d["tage"][verfuegbar[0]]["datum"] and
            d["tage"][verfuegbar[0]]["datum"].weekday() == 0 and len(verfuegbar) >= 3 else
            "Die nächsten Tage")
    zeilen = [f"**{kopf} in {name}:**"]
    for i in verfuegbar:
        t = d["tage"][i]
        datum = t["datum"]
        tagname = ("heute" if i == 0 else "morgen" if i == 1 else
                   (f"{WOCHENTAG_KURZ[datum.weekday()]} {datum:%d.%m.}" if datum else f"Tag {i}"))
        regen = f", Regen {t['regen']} %" if t.get("regen") is not None else ""
        zeilen.append(f"- **{tagname}:** {WETTERCODES.get(int(t['code'] or 0), 'wechselhaft')}, "
                      f"{_grad(t['tief'])} bis {_grad(t['hoch'])} °C{regen}")
    trocken = [i for i in verfuegbar if (d["tage"][i].get("regen") or 0) < 30]
    if trocken and len(trocken) < len(verfuegbar):
        beste = max(trocken, key=lambda i: d["tage"][i].get("hoch") or -99)
        name_beste = _tagesname(beste, d["tage"][beste]["datum"])
        name_beste = name_beste.lower() if beste < 3 else name_beste
        zeilen.append(f"\nAm schönsten wird es wohl **{name_beste.rstrip('.')}**.")
    elif not trocken:
        zeilen.append("\nEs bleibt leider durchweg nass – Schirm griffbereit halten.")
    else:
        zeilen.append("\nSieht gut aus: Es bleibt überwiegend trocken.")
    return "\n".join(zeilen) + QUELLE_WETTER


def anziehen_text(d: dict[str, Any], tag: int) -> str:
    """Was man anzieht -- aus Temperatur (gefuehlt), Regen, Wind und Sonne."""
    if tag >= len(d["tage"]):
        tag = 0
    t = d["tage"][tag]
    hoch = t.get("gefuehlt_hoch") if t.get("gefuehlt_hoch") is not None else t.get("hoch")
    tief = t.get("gefuehlt_tief") if t.get("gefuehlt_tief") is not None else t.get("tief")
    regen = t.get("regen") or 0
    wann = ("heute", "morgen", "übermorgen")[tag] if tag < 3 else _tagesname(tag, t["datum"])
    if hoch is None:
        return f"Für {d['name']} habe ich gerade keine Temperaturen. Versuch es gleich noch mal."
    if hoch >= 25:
        kleidung = "leichte Sachen: ein T-Shirt und eine kurze Hose oder ein luftiges Kleid"
    elif hoch >= 18:
        kleidung = "ein T-Shirt und für später eine dünne Jacke oder einen Pulli"
    elif hoch >= 12:
        kleidung = "eine lange Hose, einen Pulli und eine leichte Jacke"
    elif hoch >= 5:
        kleidung = "eine warme Jacke, einen Pulli und eine lange Hose"
    else:
        kleidung = "die dicke Winterjacke, dazu Mütze, Schal und Handschuhe"
    mitnehmen = []
    # 16.4.5: Bei Schnee hiess es vorher "Regenjacke oder Schirm" und "Regenrisiko".
    schnee = int(t.get("code") or 0) in SCHNEE_CODES
    risiko = "Schneerisiko" if schnee else "Regenrisiko"
    if schnee and regen >= 30:
        mitnehmen.append("warme, wasserfeste Schuhe")
    elif regen >= 50:
        mitnehmen.append("eine Regenjacke oder einen Schirm")
    elif regen >= 30:
        mitnehmen.append("sicherheitshalber einen kleinen Schirm")
    if (t.get("uv") or 0) >= 6:
        mitnehmen.append("Sonnenbrille und Sonnencreme")
    extra = ""
    if (t.get("wind") or 0) >= 40 and hoch < 18:
        extra += " Es wird windig, also lieber etwas Winddichtes."
    if tief is not None and hoch - tief >= 10:
        extra += " Am besten im Zwiebellook – morgens ist es deutlich kühler."
    if mitnehmen:
        extra = (" Nimm außerdem " + " und ".join(mitnehmen) + " mit." + extra)
    einstieg = waehle(("Ich würde sagen:", "Mein Tipp:", "So wärst du gut angezogen:"),
                      d["name"] + str(tag))
    return (f"{einstieg} Für {wann} in **{d['name']}** zieh am besten {kleidung} an.{extra}\n\n"
            f"Es werden {_grad(t.get('tief'))} bis {_grad(t.get('hoch'))} °C"
            + (f", gefühlt bis {_grad(t.get('gefuehlt_hoch'))} °C" if t.get("gefuehlt_hoch")
               is not None and t.get("gefuehlt_hoch") != t.get("hoch") else "")
            + f", {risiko} {regen} %." + QUELLE_WETTER)


def schirm_text(d: dict[str, Any], tag: int) -> str:
    if tag >= len(d["tage"]):
        tag = 0
    t = d["tage"][tag]
    regen = t.get("regen")
    wann = ("heute", "morgen", "übermorgen")[tag] if tag < 3 else _tagesname(tag, t["datum"])
    if regen is None:
        return f"Für {d['name']} kenne ich das Regenrisiko gerade nicht." + QUELLE_WETTER
    menge = t.get("menge")
    mm = f" (etwa {schoen(float(menge), 1)} mm)" if menge else ""
    if int(t.get("code") or 0) in SCHNEE_CODES and regen >= 30:
        satz = (f"Es soll schneien (Schneerisiko {regen} %). Ein Schirm hilft da wenig – nimm "
                "lieber warme, wasserfeste Schuhe und eine Mütze.")
        return f"Für {wann} in **{d['name']}**: {satz}" + QUELLE_WETTER
    if regen >= 60:
        satz = f"Ja, nimm auf jeden Fall einen Schirm mit. Das Regenrisiko liegt bei {regen} %{mm}."
    elif regen >= 30:
        satz = (f"Vielleicht. Das Regenrisiko liegt bei {regen} %{mm} – ein kleiner Schirm "
                "schadet nicht.")
    else:
        wort = "Schneerisiko" if int(t.get("code") or 0) in SCHNEE_CODES else "Regenrisiko"
        satz = (f"Eher nicht, den Schirm kannst du zu Hause lassen. Das {wort} liegt nur bei "
                f"{regen} %.")
    return f"Für {wann} in **{d['name']}**: {satz}" + QUELLE_WETTER


def sonne_text(d: dict[str, Any], tag: int) -> str:
    if tag >= len(d["tage"]):
        tag = 0
    t = d["tage"][tag]
    auf, unter = str(t.get("auf") or ""), str(t.get("unter") or "")
    if len(auf) < 16 or len(unter) < 16:
        return f"Die Zeiten für Sonnenauf- und -untergang in {d['name']} habe ich gerade nicht."
    wann = ("Heute", "Morgen", "Übermorgen")[tag] if tag < 3 else _tagesname(tag, t["datum"])
    try:
        a, u = datetime.fromisoformat(auf), datetime.fromisoformat(unter)
        dauer = u - a
        stunden, rest = divmod(int(dauer.total_seconds()) // 60, 60)
        laenge = f" Der Tag ist damit {stunden} Stunden und {rest} Minuten lang."
    except ValueError:
        laenge = ""
    return (f"{wann} geht die Sonne in **{d['name']}** um **{auf[11:16]} Uhr** auf und um "
            f"**{unter[11:16]} Uhr** unter.{laenge}" + QUELLE_WETTER)


# -- Wechselkurse -------------------------------------------------------------------------------

WAEHRUNGEN = {"euro": "EUR", "eur": "EUR", "€": "EUR", "dollar": "USD", "usd": "USD",
              "$": "USD", "pfund": "GBP", "gbp": "GBP", "franken": "CHF", "chf": "CHF",
              "yen": "JPY", "jpy": "JPY", "zloty": "PLN", "pln": "PLN", "krone": "SEK",
              "kronen": "SEK", "sek": "SEK", "dkk": "DKK", "nok": "NOK", "yuan": "CNY",
              "cny": "CNY", "lira": "TRY", "try": "TRY", "aud": "AUD", "cad": "CAD",
              # 16.4.5: englische und zusammengesetzte Namen
              "dollars": "USD", "pound": "GBP", "pounds": "GBP", "francs": "CHF",
              "franc": "CHF", "kronor": "SEK", "zlotys": "PLN", "euros": "EUR"}
#: "Schweizer Franken", "US-Dollar", "britische Pfund" -- vor der Suche zusammengefasst.
WAEHRUNG_NAMEN = ((r"\bschweizer\s+franken\b", "franken"), (r"\bus-?\s?dollars?\b", "dollar"),
                  (r"\bbritische[n]?\s+pfund\b", "pfund"), (r"\bswiss\s+francs?\b", "franken"),
                  (r"\bbritish\s+pounds?\b", "pfund"), (r"\bjapanische[n]?\s+yen\b", "yen"),
                  (r"\bschwedische[n]?\s+kronen?\b", "kronen"),
                  (r"\bpolnische[n]?\s+zloty\b", "zloty"))
#: "1,5 Mio Euro": Mio, Millionen, Mrd, Tausend hinter der Zahl.
WAEHRUNG_MAL = {"tsd": 1e3, "tausend": 1e3, "k": 1e3, "mio": 1e6, "million": 1e6,
                "millionen": 1e6, "mrd": 1e9, "milliarde": 1e9, "milliarden": 1e9}
WAEHRUNG_SATZ = re.compile(rf"{ZAHL}?\s*([a-z€$]+)\s+(?:in|nach|zu|to)\s+([a-z€$]+)")


def waehrung(text: str, holen: Holen) -> str:
    kern = falten(text).replace("€", " € ").replace("$", " $ ")
    for muster, name in WAEHRUNG_NAMEN:
        kern = re.sub(muster, name, kern)
    # "1,5 Mio Euro" rechnete vorher mit einem Euro (16.4.5).
    mal = re.search(rf"{ZAHL}\s*({'|'.join(WAEHRUNG_MAL)})\b", kern)
    faktor = 1.0
    if mal:
        faktor = WAEHRUNG_MAL[mal.group(2)]
        kern = kern[:mal.start(2)] + kern[mal.end(2):]
    # "Wie viele Dollar bekomme ich für 200 Euro?", "200 Euro sind wie viel Dollar?"
    umgekehrt = re.search(rf"wie\s*viele?\s+([a-z€$]+)\s+(?:bekomme|kriege|gibt\s+es)\s+"
                          rf"(?:ich|man)?\s*(?:fuer|for)\s+{ZAHL}\s*([a-z€$]+)", kern)
    vorn = re.search(rf"{ZAHL}\s*([a-z€$]+)\s+(?:sind|ist|macht|machen)\s+wie\s*viele?\s+"
                     r"([a-z€$]+)", kern)
    # 16.4.5: "Wie viel Euro sind 1000 Yen?"
    frage_vorn = re.search(rf"wie\s*viele?\s+([a-z€$]+)\s+(?:sind|ist|macht|machen|ergeben)\s+"
                           rf"{ZAHL}\s*([a-z€$]+)", kern)
    if frage_vorn and not vorn and WAEHRUNGEN.get(frage_vorn.group(1)) and WAEHRUNGEN.get(
            frage_vorn.group(3)):
        vorn = re.search(rf"{ZAHL}\s*([a-z€$]+)\s+(?:in)\s+([a-z€$]+)",
                         f"{frage_vorn.group(2)} {frage_vorn.group(3)} in {frage_vorn.group(1)}")
    treffer = WAEHRUNG_SATZ.search(kern)
    von = nach = None
    betrag = 1.0
    if umgekehrt and WAEHRUNGEN.get(umgekehrt.group(1)) and WAEHRUNGEN.get(umgekehrt.group(3)):
        von, nach = WAEHRUNGEN[umgekehrt.group(3)], WAEHRUNGEN[umgekehrt.group(1)]
        betrag = zahl(umgekehrt.group(2))
    elif vorn and WAEHRUNGEN.get(vorn.group(2)) and WAEHRUNGEN.get(vorn.group(3)):
        von, nach = WAEHRUNGEN[vorn.group(2)], WAEHRUNGEN[vorn.group(3)]
        betrag = zahl(vorn.group(1))
    elif treffer:
        von, nach = WAEHRUNGEN.get(treffer.group(2)), WAEHRUNGEN.get(treffer.group(3))
        betrag = zahl(treffer.group(1)) if treffer.group(1) else 1.0
    betrag *= faktor
    kurs_frage = re.search(r"\b(kurs|wechselkurs)\b|\bwie\s+steht\s+(?:der|die|das)\b", kern)
    if (not von or not nach) and kurs_frage:
        # 16.3.0: Ohne "in": die genannten Waehrungen der Reihe nach, eine allein gegen Euro.
        genannt = list(dict.fromkeys(WAEHRUNGEN[w] for w in re.findall(r"[a-z€$]+", kern)
                                     if w in WAEHRUNGEN and w != "try"))
        if len(genannt) == 1:
            genannt = ["EUR", "USD"] if genannt[0] == "EUR" else ["EUR", genannt[0]]
        if len(genannt) >= 2:
            von, nach = genannt[0], genannt[1]
            betrag_text = re.search(r"-?\d[\d.,]*", kern)
            betrag = (zahl(betrag_text.group(0)) if betrag_text else 1.0) * faktor
    if not von or not nach or von == nach:
        return ""
    daten = holen(f"https://api.frankfurter.app/latest?from={von}&to={nach}")
    # 16.1.6: Antwortet der Dienst anders als erwartet, kein Absturz.
    kurse = daten.get("rates") if isinstance(daten, dict) else None
    try:
        kurs = float(kurse.get(nach) or 0) if isinstance(kurse, dict) else 0.0
    except (TypeError, ValueError):
        kurs = 0.0
    if not math.isfinite(kurs) or kurs <= 0:
        return "Die Wechselkurse lassen sich gerade nicht abrufen."
    stand = str(daten.get("date", "") or "")[:20] if isinstance(daten, dict) else ""
    return (f"{schoen(betrag)} {von} {'ist' if betrag == 1 else 'sind'} "
            f"**{schoen(betrag * float(kurs))} {nach}** "
            f"(Kurs {schoen(float(kurs), 4)}, Stand {stand}).\n\nQuelle: Europäische Zentralbank "
            "über [Frankfurter](https://www.frankfurter.app)")


# -- Nachrichten --------------------------------------------------------------------------------

def nachrichten(holen: Holen) -> str:
    daten = holen("https://www.tagesschau.de/api2u/homepage/")
    alle = daten.get("news") if isinstance(daten, dict) else None
    meldungen = [m for m in (alle if isinstance(alle, list) else [])
                 if isinstance(m, dict) and m.get("title")][:5]
    if not meldungen:
        return "Die Nachrichten lassen sich gerade nicht abrufen."
    zeilen = ["**Die wichtigsten Nachrichten:**"]
    for m in meldungen:
        link = str(m.get("shareURL") or m.get("detailsweb") or "")
        titel = str(m["title"]).replace("[", "(").replace("]", ")")
        zeilen.append(f"- [{titel}]({link})" if link.startswith("https://") else f"- {titel}")
    return "\n".join(zeilen) + "\n\nQuelle: [tagesschau.de](https://www.tagesschau.de)"


# -- Wissen (Wikipedia) -------------------------------------------------------------------------

WISSEN_VORN = re.compile(
    r"^(?:und\s+)?(?:wer|was)\s+(?:ist|sind|war|waren)\s+|^erzaehl\s+(?:mir\s+)?(?:etwas\s+|was\s+)?"
    r"(?:ueber|von)\s+|^was\s+weisst\s+du\s+(?:ueber|von)\s+|^erklaer(?:e)?\s+(?:mir\s+)?|"
    r"^was\s+bedeutet\s+|^was\s+versteht\s+man\s+unter\s+|^(?:who|what)\s+(?:is|are|was)\s+|"
    # 16.4.5: weitere uebliche Formen
    r"^was\s+heisst\s+|^kennst\s+du\s+|^(?:infos?|informationen)\s+(?:zu|ueber)\s+|"
    r"^tell\s+me\s+about\s+")
ARTIKEL = re.compile(r"^(?:der|die|das|ein|eine|einen|den|dem|des|the|a|an)\s+")


#: 16.3.0: Wissensfragen, deren Thema in der Mitte steht.
WISSEN_FRAGEN = (
    re.compile(r"^wie\s+(?:hoch|lang|gross|alt|tief|breit|schwer|weit\s+weg)\s+(?:ist|sind|war)\s+"
               r"(?!es\b|das\s+wetter\b)(.+)$"),
    re.compile(r"^wie\s*viele\s+einwohner\s+(?:hat|haben|hatte)\s+(.+)$"),
    re.compile(r"^wo\s+(?:liegt|liegen|befindet\s+sich)\s+(.+)$"),
    re.compile(r"^wann\s+(?:wurde|wurden|ist|war)\s+(.+?)\s+(?:gegruendet|geboren|gebaut|erfunden|"
               r"gestorben|entdeckt|erbaut|eroeffnet|errichtet)$"),
    re.compile(r"^wer\s+hat\s+(.+?)\s+(?:erfunden|entdeckt|gebaut|gegruendet|geschrieben|gemalt|"
               r"komponiert|entwickelt|erbaut)$"),
    re.compile(r"^(?:wikipedia|wiki)\s+(?:zu\s+|ueber\s+)?(.+)$"),
    # 16.4.5: "Wer erfand das Telefon?", "Wann lebte Kleopatra?", "Wie alt wurde Einstein?",
    # "Weißt du, was ein Okapi ist?", "Was macht ein Notar?", "Wie funktioniert ein Kühlschrank?"
    re.compile(r"^wer\s+(?:erfand|entdeckte|gruendete|schrieb|malte|komponierte|baute|"
               r"entwickelte)\s+(.+)$"),
    re.compile(r"^wann\s+(?:lebte|lebten|starb|regierte)\s+(.+)$"),
    re.compile(r"^wie\s+alt\s+wurde\s+(.+)$"),
    re.compile(r"^weisst\s+du,?\s+(?:was|wer)\s+(.+?)\s+(?:ist|sind|war|waren)$"),
    re.compile(r"^was\s+macht\s+(?:ein|eine)\s+(.+)$"),
    re.compile(r"^wie\s+funktionier(?:t|en)\s+(.+)$"),
    re.compile(r"^(.+?)\s+(?:auf\s+)?(?:wikipedia|wiki)$"),
    # 16.4.5: "Kannst du mir etwas über die Römer erzählen?", "Wann war der Zweite Weltkrieg?"
    # fanden vorher kein Thema.
    re.compile(r"^(?:kannst|koenntest)\s+du\s+mir\s+(?:etwas|was|mehr|bitte\s+etwas)\s+"
               r"(?:ueber|zu)\s+(.+?)\s+(?:erzaehlen|sagen|erklaeren)$"),
    re.compile(r"^wann\s+(?:war|begann|endete)\s+(?:der|die|das)\s+(?!letzte|naechste|erste\s+"
               r"(?:schnee|frost))(.+)$"),
)


def thema_aus(text: str) -> str:
    thema = _thema_aus(text)
    # Kein Thema: Fuerwoerter ("Wie funktioniert das?", "Kennst du mich?"), Uebersetzungen
    # ("Was heißt Hund auf Englisch?") und "Was macht ein gutes Leben aus?" (16.4.5).
    klein = falten(thema)
    if (klein in {"das", "es", "er", "die", "der", "mich", "dich", "uns", "euch", "ihn", "sie",
                  "man", "du", "ich", "wer", "was",
                  "dies", "dieses", "das hier", "so etwas", "sowas"}
            or re.search(r"\bauf\s+(?:englisch|deutsch|franzoesisch|spanisch|italienisch|"
                         r"tuerkisch|english|german)$", klein)
            or (re.match(r"^was\s+macht\b", falten(text)) and re.search(r"\baus$", klein))):
        return ""
    return thema


def _thema_aus(text: str) -> str:
    roh = re.sub(r"\s+", " ", text).strip(" ?!.")
    kern = falten(roh)
    for muster in WISSEN_FRAGEN:
        frage = muster.match(kern)
        if frage:
            if re.match(r"(?:mein|dein|sein|ihr|unser|euer)(?:e|en|em|er|es)?\b",
                        frage.group(1)):
                return ""
            rest = original(roh, frage.group(1)).strip()
            rest = ARTIKEL.sub("", rest) if ARTIKEL.match(rest.lower()) else rest
            # "Wie funktioniert die Zellatmung genau?" -- Fuellwoerter am Ende weg (16.4.5).
            rest = re.sub(r"\s+(?:eigentlich|denn|genau|nochmal|so|bitte)$", "", rest, flags=re.I)
            return rest[:80]
    treffer = WISSEN_VORN.match(kern)
    if not treffer:
        return ""
    # Den Rest aus dem Original nehmen, damit Umlaute und Grossschreibung bleiben.
    worte = roh.split(" ")
    vorn = len(treffer.group(0).split())
    rest = " ".join(worte[vorn:]).strip()
    # "Was ist eigentlich ein Axolotl?" suchte vorher nach "eigentlich ein Axolotl" (16.4.5).
    rest = re.sub(r"^(?:eigentlich|denn|genau|nochmal|so)\s+", "", rest, flags=re.I)
    rest = ARTIKEL.sub("", rest) if ARTIKEL.match(rest.lower()) else rest
    rest = re.sub(r"\s+(?:eigentlich|denn|genau|nochmal|so|bitte)$", "", rest, flags=re.I)
    return rest[:80]


#: Abkuerzungen, nach denen kein Satz endet.
ABKUERZUNGEN = frozenset({"z", "b", "d", "h", "u", "a", "s", "v", "ca", "bzw", "vgl", "usw", "evtl",
                          "ggf", "dr", "prof", "st", "nr", "jh", "mio", "mrd", "chr", "geb",
                          "gest", "etc", "e", "g", "i", "vs", "mr", "mrs", "jr", "sr", "no"})


def saetze_aus(text: str) -> list[str]:
    """Saetze eines Auszugs -- nicht nach "14. März", "z. B." oder "ca. 84" getrennt (16.4.5)."""
    teile: list[str] = []
    anfang = 0
    for ende in re.finditer(r"[.!?](?=\s+\S)|[。！？।۔]", text):
        davor = re.search(r"(\w+)\W*$", text[anfang:ende.start()])
        wort = davor.group(1) if davor else ""
        danach = text[ende.end():].lstrip()[:1]
        if ende.group(0) == "." and (wort.isdigit() or wort.lower() in ABKUERZUNGEN
                                     or not danach or not danach.isupper()):
            continue
        teile.append(text[anfang:ende.end()].strip())
        anfang = ende.end()
    rest = text[anfang:].strip()
    return [t for t in [*teile, rest] if t]


def wissen(thema: str, holen: Holen, sprache: str = "de") -> str:
    """Der Anfang des passenden Wikipedia-Artikels -- in der Wikipedia *sprache* (16.4.2)."""
    basis = f"https://{sprache}.wikipedia.org"
    suche = holen(basis + "/w/api.php?action=opensearch&limit=1&namespace=0"
                  "&format=json&search=" + quote(thema))
    titel = ""
    if isinstance(suche, list) and len(suche) > 1 and suche[1]:
        titel = str(suche[1][0])
    if not titel:
        return ""
    seite = holen(basis + "/api/rest_v1/page/summary/"
                  + quote(titel.replace(" ", "_"), safe=""))
    if not isinstance(seite, dict) or seite.get("type") == "disambiguation":
        if isinstance(seite, dict) and sprache == "en":
            # 16.4.5: "What is Mercury?" hiess vorher "I couldn't find anything".
            return f"“{thema}” has several meanings. Tell me which one you mean."
        return (f"Zu „{thema}“ gibt es mehrere Bedeutungen. Sag mir genauer, welche du meinst."
                if isinstance(seite, dict) and sprache == "de" else "")
    auszug = str(seite.get("extract") or "").strip()
    if not auszug:
        return ""
    kurz = " ".join(saetze_aus(auszug)[:3])[:700]
    # 16.4.5: Ein unerwartetes "content_urls" (Liste statt Objekt) brachte die Antwort zum Absturz.
    urls = seite.get("content_urls")
    desktop = urls.get("desktop") if isinstance(urls, dict) else None
    link = desktop.get("page") if isinstance(desktop, dict) else None
    if not isinstance(link, str) or not link.startswith(basis + "/"):
        link = basis + "/wiki/" + quote(titel.replace(" ", "_"))
    quelle = "Quelle: [Wikipedia]" if sprache == "de" else "📖 [Wikipedia]"
    return f"**{seite.get('title', titel)}:** {kurz}\n\n{quelle}({link})"


# -- Uhrzeit in anderen Staedten ----------------------------------------------------------------

#: 16.4.5: "Was ist die Zeitverschiebung nach Tokio?", "Wie viele Stunden ist Tokio voraus?"
ZEITVERSCHIEBUNG = re.compile(r"\b(?:zeitverschiebung|zeitunterschied)\s+(?:nach|zu|mit|in)\s+"
                              r"([a-z][a-z\s.\-]{1,40})$|\bwie\s*viele\s+stunden\s+(?:ist|liegt)\s+"
                              r"([a-z][a-z\s.\-]{1,40}?)\s+(?:voraus|zurueck|hinterher)$")
UHRZEIT_IN = re.compile(r"\b(?:wie\s*spaet|uhrzeit|wieviel\s+uhr|wie\s+viel\s+uhr)\b.*?\b"
                        r"(?:in|auf)\s+([a-z][a-z\s.,\-]{1,60})$")


_ORT_ZEIT = r"([a-z][a-z.\-]*(?:\s+[a-z][a-z.\-]*){0,3}?)"
UHRZEIT_WENN = (
    re.compile(r"\bwenn\s+es\s+(?:bei\s+uns|hier|in\s+" + _ORT_ZEIT
               + r")\s+(\d{1,2})(?:[:.](\d{2}))?"
               r"\s*uhr\s+ist\s*,?\s+(?:wie\s*spaet|wie\s*viel\s+uhr)\s+ist\s+es\s+(?:dann\s+)?"
               r"(?:in|auf)\s+" + _ORT_ZEIT + r"$"),
    re.compile(r"\b(?:wie\s*spaet|wie\s*viel\s+uhr)\s+ist\s+es\s+(?:dann\s+)?(?:in|auf)\s+"
               + _ORT_ZEIT + r"\s*,?\s+wenn\s+es\s+(?:bei\s+uns|hier|in\s+" + _ORT_ZEIT
               + r")\s+(\d{1,2})(?:[:.](\d{2}))?\s*uhr\s+ist$"))


def _zone_von(ort: str, holen: Holen) -> tuple[str, str] | str:
    """(Zeitzone, Name) eines Ortes -- sonst der Satz, warum nicht."""
    geo = holen("https://geocoding-api.open-meteo.com/v1/search?count=1&language=de&name="
                + quote(ort))
    if not isinstance(geo, dict):
        return "Die Ortssuche antwortet gerade nicht. Versuch es gleich noch einmal."
    treffer = geo.get("results")
    erster = treffer[0] if isinstance(treffer, list) and treffer and isinstance(
        treffer[0], dict) else {}
    zone = erster.get("timezone") if isinstance(erster.get("timezone"), str) else ""
    if not zone:
        return f"Für „{ort}“ finde ich keine Zeitzone. Schreib die Stadt vielleicht etwas genauer?"
    return zone, str(erster.get("name") or ort)


def uhrzeit_wenn(frage: str, kern: str, holen: Holen, jetzt: datetime | None = None) -> str:
    """16.4.5: "Wenn es in Berlin 9 Uhr ist, wie spät ist es dann in Tokio?" -- vorher kam die
    aktuelle Zeit in Tokio bzw. die Zeit von hier."""
    from datetime import timedelta, tzinfo
    from zoneinfo import ZoneInfo

    from aquaticy import zeit as zeit_mod

    vorn = UHRZEIT_WENN[0].search(kern)
    hinten = UHRZEIT_WENN[1].search(kern)
    if vorn:
        von, stunde, minute, nach = vorn.groups()
    elif hinten:
        nach, von, stunde, minute = hinten.groups()
    else:
        return ""
    if int(stunde) > 24 or int(minute or 0) > 59:
        return ""
    hier = jetzt or zeit_mod.jetzt()
    try:
        if von:
            gefunden = _zone_von(original(frage, von), holen)
            if isinstance(gefunden, str):
                return gefunden
            zone_von: tzinfo = ZoneInfo(gefunden[0])
            wo = f"in {gefunden[1]}"
        else:
            zone_von, wo = hier.tzinfo or ZoneInfo("Europe/Berlin"), "bei dir"
        gefunden = _zone_von(original(frage, nach), holen)
        if isinstance(gefunden, str):
            return gefunden
        zone_nach, name_nach = ZoneInfo(gefunden[0]), gefunden[1]
    except Exception:
        return "Diese Zeitzone kenne ich leider nicht."
    tag = hier.astimezone(zone_von).date()
    start = datetime(tag.year, tag.month, tag.day, tzinfo=zone_von) + timedelta(
        hours=int(stunde), minutes=int(minute or 0))
    dort = start.astimezone(zone_nach)
    versatz = (dort.date() - start.date()).days
    tag_text = {1: " – am nächsten Tag", -1: " – am Tag davor"}.get(versatz, "")
    return (f"Wenn es {wo} {start:%H:%M} Uhr ist, ist es in **{name_nach}** "
            f"**{dort:%H:%M} Uhr**{tag_text}.")


ZEIT_ZWISCHEN = re.compile(r"\bzeit(?:verschiebung|unterschied|differenz)\s+zwischen\s+"
                           + _ORT_ZEIT + r"\s+und\s+" + _ORT_ZEIT + r"$")


def zeit_zwischen(frage: str, kern: str, holen: Holen, jetzt: datetime | None = None) -> str:
    """16.4.5: "Wie viele Stunden Zeitunterschied zwischen Berlin und New York?" -- vorher
    "kann ich nicht" ("Zeitverschiebung nach Tokio" ging schon)."""
    from zoneinfo import ZoneInfo

    from aquaticy import zeit as zeit_mod

    treffer = ZEIT_ZWISCHEN.search(kern)
    if not treffer:
        return ""
    jetzt_ = jetzt or zeit_mod.jetzt()
    zonen = []
    for ort in treffer.groups():
        gefunden = _zone_von(original(frage, ort), holen)
        if isinstance(gefunden, str):
            return gefunden
        zonen.append(gefunden)
    try:
        versatz = [jetzt_.astimezone(ZoneInfo(z)).utcoffset() for z, _ in zonen]
    except Exception:
        return "Diese Zeitzone kenne ich leider nicht."
    if versatz[0] is None or versatz[1] is None:
        return ""
    diff = (versatz[1] - versatz[0]).total_seconds() / 3600
    (_, a), (_, b) = zonen
    if not diff:
        return f"**{a}** und **{b}** haben gerade dieselbe Uhrzeit."
    wort = "Stunde" if abs(diff) == 1 else "Stunden"
    return (f"Zwischen **{a}** und **{b}** liegen gerade **{schoen(abs(diff), 1)} {wort}** – in "
            f"{b} ist es {'später' if diff > 0 else 'früher'}.")


def uhrzeit_in(ort: str, holen: Holen, jetzt: datetime | None = None) -> str:
    from zoneinfo import ZoneInfo

    from aquaticy import zeit as zeit_mod

    geo = holen("https://geocoding-api.open-meteo.com/v1/search?count=1&language=de&name="
                + quote(ort))
    if not isinstance(geo, dict):
        return "Die Ortssuche antwortet gerade nicht. Versuch es gleich noch einmal."
    # 16.4.5: Kaputte Ortsdaten ("results": "x" oder [None]) brachten die Antwort zum Absturz.
    treffer = geo.get("results")
    erster = treffer[0] if isinstance(treffer, list) and treffer and isinstance(
        treffer[0], dict) else {}
    zone = erster.get("timezone") if isinstance(erster.get("timezone"), str) else ""
    if not zone:
        return f"Für „{ort}“ finde ich keine Zeitzone. Schreib die Stadt vielleicht etwas genauer?"
    try:
        dort = (jetzt or zeit_mod.jetzt()).astimezone(ZoneInfo(zone))
    except Exception:
        return f"Die Zeitzone von „{ort}“ kenne ich leider nicht."
    hier = jetzt or zeit_mod.jetzt()
    versatz_dort, versatz_hier = dort.utcoffset(), hier.utcoffset()
    diff = ((versatz_dort - versatz_hier).total_seconds() / 3600
            if versatz_dort is not None and versatz_hier is not None else 0.0)
    if diff:
        # 16.4.5: vorher "Das sind 1 Stunden weniger" (London).
        unterschied = (f" Das {'ist' if abs(diff) == 1 else 'sind'} {schoen(abs(diff), 1)} "
                       f"{'Stunde' if abs(diff) == 1 else 'Stunden'} "
                       f"{'mehr' if diff > 0 else 'weniger'} als bei dir.")
    else:
        unterschied = " Dieselbe Zeit wie bei dir."
    name = str(erster.get("name") or ort)
    return (f"In **{name}** ist es gerade **{dort:%H:%M} Uhr** "
            f"({WOCHENTAGE[dort.weekday()]}).{unterschied}")


# -- Feiertage und Mond -------------------------------------------------------------------------

def feiertage(jahr: int) -> list[tuple[date, str]]:
    """Die bundesweiten Feiertage in Deutschland."""
    from datetime import timedelta

    o = ostern(jahr)
    return sorted([
        (date(jahr, 1, 1), "Neujahr"), (o - timedelta(days=2), "Karfreitag"),
        (o + timedelta(days=1), "Ostermontag"), (date(jahr, 5, 1), "Tag der Arbeit"),
        (o + timedelta(days=39), "Christi Himmelfahrt"), (o + timedelta(days=50), "Pfingstmontag"),
        (date(jahr, 10, 3), "Tag der Deutschen Einheit"), (date(jahr, 12, 25), "1. Weihnachtstag"),
        (date(jahr, 12, 26), "2. Weihnachtstag")])


FEIERTAG_NAMEN = {"karfreitag": "Karfreitag", "ostermontag": "Ostermontag",
                  "himmelfahrt": "Christi Himmelfahrt", "vatertag": "Christi Himmelfahrt",
                  "pfingstmontag": "Pfingstmontag", "tag der arbeit": "Tag der Arbeit",
                  "einheit": "Tag der Deutschen Einheit"}


def feiertag(text: str, heute: date) -> str:
    kern = falten(text)
    if "feiertag" not in kern and not any(k in kern for k in FEIERTAG_NAMEN):
        return ""
    if re.search(r"\b(welche[rs]?\s+(?:wochen)?tag\s+(?:ist|war|wird|faellt)|auf\s+welchen\s+"
                 r"(?:wochen)?tag)\b", kern) and not jahr_aus(kern):
        # 16.4.6: "Welcher Wochentag ist Pfingstmontag?" bekam vorher die Liste der naechsten
        # Feiertage.
        benannt = _benannter_tag(kern, heute)
        if benannt:
            name, tag = benannt
            zeitform = "war" if tag < heute else "ist"
            return f"{name} {zeitform} am **{WOCHENTAGE[tag.weekday()]}, {tag:%d.%m.%Y}**."
    if re.search(r"\bwie\s*viele\s+(?:gesetzliche\s+)?feiertage\b", kern) and not re.search(
            r"\b(?:im|in|bis|noch)\b", kern):
        # 16.4.5: "Wie viele Feiertage hat Deutschland?" bekam vorher die naechsten drei.
        return (f"Bundesweit gibt es in Deutschland **{len(feiertage(heute.year))} gesetzliche "
                "Feiertage**. Je nach Bundesland kommen weitere dazu, zum Beispiel Fronleichnam "
                "oder der Reformationstag.")
    alle = feiertage(heute.year) + feiertage(heute.year + 1)
    bereich = re.search(r"\b(?:zwischen\s+(?:dem\s+)?" + _DATUM_TEIL + r"\s+und\s+(?:dem\s+)?"
                        + _DATUM_TEIL + r"|vom\s+" + _DATUM_TEIL + r"\s+bis\s+(?:zum\s+)?"
                        + _DATUM_TEIL + r")", kern)
    if bereich:
        a_text, b_text = [g for g in bereich.groups() if g][:2]
        von, bis = datum_aus(a_text, heute), datum_aus(b_text, heute)
        if von and bis:
            if re.search(r"\d{4}", b_text) and not re.search(r"\d{4}", a_text):
                von = im_jahr(von, bis.year)
            if bis < von and not re.search(r"\d{4}", b_text):
                bis = im_jahr(bis, von.year + 1)
            von, bis = min(von, bis), max(von, bis)
            if bis.year - von.year > 2:
                return ("Nenn mir einen kürzeren Zeitraum – höchstens zwei Jahre, dann zähle ich "
                        "die Feiertage auf.")
            drin = [(t, n) for jahr_ in range(von.year, bis.year + 1) for t, n in feiertage(jahr_)
                    if von <= t <= bis]
            if not drin:
                return (f"Vom {von:%d.%m.%Y} bis zum {bis:%d.%m.%Y} gibt es keinen bundesweiten "
                        "Feiertag.")
            return (f"Bundesweite Feiertage vom {von:%d.%m.%Y} bis zum {bis:%d.%m.%Y}:\n"
                    + "\n".join(f"- **{n}:** {WOCHENTAGE[t.weekday()]}, {t:%d.%m.%Y}"
                                for t, n in drin))
    jahr_genannt = jahr_aus(kern)
    if jahr_genannt:
        # "Welche Feiertage gibt es 2027?" nannte vorher nur die naechsten drei.
        im_jahr_ = feiertage(jahr_genannt)
        for wort, name in FEIERTAG_NAMEN.items():
            if wort in kern:
                tag = next(t for t, n in im_jahr_ if n == name)
                zeitform = "war" if tag < heute else "ist"
                return (f"{name} {zeitform} {jahr_genannt} am "
                        f"**{WOCHENTAGE[tag.weekday()]}, {tag:%d.%m.%Y}**.")
        if not re.search(r"\b(heute|morgen|uebermorgen)\b", kern) and not datum_aus(kern, heute):
            zeilen = [f"- **{n}:** {WOCHENTAGE[t.weekday()]}, {t:%d.%m.%Y}" for t, n in im_jahr_]
            return (f"Die bundesweiten Feiertage {jahr_genannt}:\n" + "\n".join(zeilen)
                    + "\n\nEinige Bundesländer haben noch weitere, zum Beispiel Fronleichnam oder "
                    "den Reformationstag.")
    for wort, name in FEIERTAG_NAMEN.items():
        if wort in kern and "wann" not in kern and "feiertag" in kern:
            # 16.4.5: "Ist Pfingstmontag ein Feiertag?" bekam vorher nur eine Liste.
            tag = next(t for t, n in alle if n == name and t >= heute)
            return (f"Ja, {name} ist ein bundesweiter Feiertag – das nächste Mal am "
                    f"**{WOCHENTAGE[tag.weekday()]}, {tag:%d.%m.%Y}**.")
    if "feiertag" in kern and not jahr_genannt:
        for wort, (name, _) in anlaesse(heute.year).items():
            if re.search(rf"\b{re.escape(wort)}\b", kern) and wort not in (
                    "weihnachten", "pfingsten"):
                if wort in ("fronleichnam", "reformationstag"):
                    return (f"{name} ist kein bundesweiter Feiertag, aber in einigen "
                            "Bundesländern frei.")
                return f"Nein, {name} ist kein gesetzlicher Feiertag."
        monat_ = re.search(r"\b(?:im\s+)?(" + "|".join(MONATE) + r")\b", kern)
        if monat_ and not datum_aus(kern, heute):
            # "Welche Feiertage gibt es im Dezember?" nannte vorher auch Neujahr.
            nummer = MONATE.index(monat_.group(1)) + 1
            jahr = heute.year if nummer >= heute.month else heute.year + 1
            im_monat = [(t, n) for t, n in feiertage(jahr) if t.month == nummer]
            name = "März" if nummer == 3 else monat_.group(1).capitalize()
            if not im_monat:
                return f"Im {name} {jahr} gibt es keinen bundesweiten Feiertag."
            zeilen = [f"- **{n}:** {WOCHENTAGE[t.weekday()]}, {t:%d.%m.%Y}" for t, n in im_monat]
            return f"Bundesweite Feiertage im {name} {jahr}:\n" + "\n".join(zeilen)
    for wort, name in FEIERTAG_NAMEN.items():
        if wort in kern and "wann" in kern:
            tag = next(t for t, n in alle if n == name and t >= heute)
            wann = "heute" if tag == heute else in_tagen((tag - heute).days)
            return (f"{name} ist dieses Mal am **{WOCHENTAGE[tag.weekday()]}, {tag:%d.%m.%Y}** – "
                    f"{wann}.")
    from datetime import timedelta

    gefragt: tuple[str, date] | None = None
    for wort, name, versatz in (("uebermorgen", "übermorgen", 2), ("morgen", "morgen", 1),
                                ("heute", "heute", 0)):
        if re.search(rf"\b{wort}\b", kern):
            gefragt = (name, heute + timedelta(days=versatz))
            break
    if gefragt is None:
        genannt = datum_aus(kern, heute)
        if genannt:
            gefragt = (f"der {genannt:%d.%m.%Y}", genannt)
    if gefragt:
        wann, stichtag = gefragt
        namen = [n for t, n in feiertage(stichtag.year) if t == stichtag]
        # 16.4.5: Ein Tag, der schon war, "war" ein Feiertag. "Welcher Feiertag ...?" ist keine
        # Ja-Nein-Frage.
        zeitform = "war" if stichtag < heute else "ist"
        if namen:
            schluss = " – genieß den freien Tag!" if stichtag == heute else "."
            if re.search(r"\bwelche[rs]?\b", kern):
                return f"{wann[:1].upper() + wann[1:]} {zeitform} **{namen[0]}**{schluss}"
            return f"Ja, {wann} {zeitform} **{namen[0]}**{schluss}"
        kommt = next(((t, n) for t, n in alle if t >= max(stichtag, heute)), None)
        mehr = (f" Der nächste ist **{kommt[1]}** am {WOCHENTAGE[kommt[0].weekday()]}, "
                f"{kommt[0]:%d.%m.%Y}." if kommt else "")
        return (f"Nein, {wann} {zeitform} kein bundesweiter Feiertag. In manchen "
                f"Bundesländern kann es "
                f"anders sein.{mehr}")
    naechste = [(t, n) for t, n in alle if t >= heute][:3]
    zeilen = [f"- **{n}:** {WOCHENTAGE[t.weekday()]}, {t:%d.%m.%Y}" for t, n in naechste]
    return ("Die nächsten bundesweiten Feiertage:\n" + "\n".join(zeilen)
            + "\n\nEinige Bundesländer haben noch weitere, zum Beispiel Fronleichnam oder den "
            "Reformationstag.")


MONDPHASEN = ("Neumond 🌑", "zunehmende Sichel 🌒", "erstes Viertel 🌓", "zunehmender Mond 🌔",
              "Vollmond 🌕", "abnehmender Mond 🌖", "letztes Viertel 🌗", "abnehmende Sichel 🌘")


def mond(text: str, heute: date) -> str:
    kern = falten(text)
    if not re.search(r"\b(mond|mondphase|vollmond|neumond)\b", kern):
        return ""
    synodisch = 29.530588853
    alter = (heute - date(2000, 1, 6)).days % synodisch
    phase = MONDPHASEN[int((alter / synodisch) * 8 + 0.5) % 8]
    bis_voll = (14.765 - alter) % synodisch
    bis_neu = (synodisch - alter) % synodisch
    # 16.4.5: "Wann ist Vollmond?" ist keine Ja-Nein-Frage, und nach dem Neumond gab es vorher
    # nur eine Antwort zum Vollmond.
    gesucht, bis, zeichen = (("Neumond", bis_neu, "🌑") if "neumond" in kern
                             else ("Vollmond", bis_voll, "🌕"))
    heute_ist = phase.startswith(gesucht)
    gefragt = gesucht.lower() in kern
    if gefragt and not heute_ist and re.search(r"\b(?:letzte[rn]?|vorige[rn]?)\b|\bwann\s+war\b",
                                               kern):
        # 16.4.5: "Wann war der letzte Vollmond?" nannte vorher den naechsten.
        vor = round((alter - 14.765) % synodisch if gesucht == "Vollmond" else alter) or 1
        damals = date.fromordinal(heute.toordinal() - vor)
        return (f"Der letzte {gesucht} war etwa **am {damals:%d.%m.%Y}** ({vor} Tage her). "
                "(Ungefähr berechnet, auf ein bis zwei Tage genau.)")
    if gefragt and heute_ist:
        satz = f"Ja, heute ist **{gesucht} {zeichen}**."
    elif gefragt and re.search(r"\b(wann|naechste[rn]?)\b", kern):
        satz = f"Heute ist **{phase}**."
    elif gefragt:
        satz = f"Nein, heute ist kein {gesucht}, sondern **{phase}**."
    else:
        satz = f"Heute ist **{phase}**."
    if (gefragt or "wann" in kern) and not heute_ist:
        satz += f" Der nächste {gesucht} ist etwa **{in_tagen(round(bis) or 1)}**."
    return satz + " (Ungefähr berechnet, auf ein bis zwei Tage genau.)"


# -- Rechnen im Alltag --------------------------------------------------------------------------

def alter(text: str, heute: date) -> str:
    kern = falten(text)
    if not re.search(r"\b(wie\s+alt|alter|geboren|geburtstag)\b", kern):
        return ""
    geburt = datum_aus(kern, heute)
    mit_jahr = re.search(r"\d{1,2}\.\d{1,2}\.\d{2,4}|\b(?:" + "|".join(MONATE) + r")\s+\d{4}\b|"
                         r"\b\d{4}-\d{1,2}-\d{1,2}\b", kern)
    if geburt is not None and not mit_jahr:
        # 16.4.5: "Ich habe am 1. Januar Geburtstag" hiess vorher "Dann bist du 0 Jahre alt",
        # "Mein Geburtstag ist am 20.11." bekam keine Antwort.
        naechster = im_jahr(geburt, heute.year)
        if naechster < heute:
            naechster = im_jahr(geburt, heute.year + 1)
        bis = (naechster - heute).days
        if bis == 0:
            return "Heute ist dein Geburtstag – herzlichen Glückwunsch! 🎉"
        if bis == 1:
            return "Morgen ist dein Geburtstag. 🎂"
        return (f"Bis zu deinem Geburtstag am {naechster:%d.%m.} sind es noch "
                f"**{schoen(bis)} Tage**.")
    alt_jetzt = re.search(r"\bwenn\s+ich\s+(\d{1,3})\s+(?:jahre\s+(?:alt\s+)?)?bin\b|"
                          r"\bich\s+bin\s+(\d{1,3})(?:\s+jahre(?:\s+alt)?)?\b", kern)
    if (geburt is None and alt_jetzt and re.search(r"\b(?:wann|welchem\s+jahr)\b", kern)
            and re.search(r"\bgeboren\b", kern)):
        # 16.4.5: "In welchem Jahr bin ich geboren, wenn ich 30 bin?"
        n = int(alt_jetzt.group(1) or alt_jetzt.group(2))
        if n <= 130:
            return (f"Wenn du jetzt {n} bist, bist du **{heute.year - n}** geboren – oder "
                    f"{heute.year - n - 1}, falls du dieses Jahr noch Geburtstag hast.")
    if geburt is None:
        # 16.4.5: "Wie alt wird man 2040, wenn man 1990 geboren ist?" nahm 2040 als Geburtsjahr.
        jahr = (re.search(r"\b(?:geboren|jahrgang)\s+(?:im\s+jahr\s+|in\s+)?(19\d{2}|20\d{2})\b|"
                          r"\b(19\d{2}|20\d{2})\s+geboren\b", kern)
                or re.search(r"\b(19\d{2}|20\d{2})\b", kern))
        if not jahr or not re.search(r"\bgeboren\b", kern):
            return ""
        geburtsjahr = next(g for g in jahr.groups() if g)
        ziel = next((int(z) for z in re.findall(r"\b(?:19|20)\d{2}\b", kern)
                     if z != geburtsjahr), None)
        if ziel and re.search(r"\b(?:wird|werde|wirst|ist|bin|bist)\b", kern):
            if ziel < int(geburtsjahr):
                return f"{ziel} warst du noch nicht geboren."
            zeitform = "wird man" if ziel >= heute.year else "wurde man"
            return (f"{ziel} {zeitform} **{ziel - int(geburtsjahr)}**, wenn man {geburtsjahr} "
                    "geboren ist.")
        jahr = re.search(geburtsjahr, kern)
        assert jahr
        jahre = heute.year - int(jahr.group(0))
        if jahre < 0:
            return f"Das Jahr {jahr.group(0)} liegt noch in der Zukunft."
        return (f"Wenn du {jahr.group(0)} geboren bist, wirst du dieses Jahr **{jahre}** "
                f"(oder bist es schon, je nach Geburtstag).")
    if geburt > heute:
        return ""
    if re.search(r"\bwie\s*viele\s+tage\b", kern):
        # 16.4.5: "Wie viele Tage bin ich alt?" nannte vorher die Jahre.
        return (f"Seit dem {geburt:%d.%m.%Y} sind **{schoen((heute - geburt).days)} Tage** "
                "vergangen.")
    jahre = heute.year - geburt.year - ((heute.month, heute.day) < (geburt.month, geburt.day))
    naechster = im_jahr(geburt, heute.year)
    if naechster < heute:
        naechster = im_jahr(geburt, heute.year + 1)
    bis = (naechster - heute).days
    zusatz = ("Heute ist dein Geburtstag – herzlichen Glückwunsch! 🎉" if bis == 0 else
              "Morgen ist dein Geburtstag. 🎂" if bis == 1 else
              f"Bis zum nächsten Geburtstag sind es noch {bis} Tage.")
    return f"Dann bist du **{jahre} Jahre** alt. {zusatz}"


BMI_SATZ = re.compile(r"\b(?:bmi|body\s*mass)\b.*?(\d{2,3}(?:[.,]\d)?)\s*kg.*?(\d[.,]\d{1,2}|\d{3})"
                      r"\s*(m|cm)?\b|\b(\d{2,3}(?:[.,]\d)?)\s*kg.*?(\d[.,]\d{1,2}|\d{3})\s*(m|cm)?"
                      r".*\bbmi\b")
#: "BMI bei 1,75 m und 70 kg" -- erst die Groesse, dann das Gewicht.
BMI_UMGEKEHRT = re.compile(r"\b(?:bmi|body\s*mass)\b.*?(\d[.,]\d{1,2}|\d{3})\s*(m|cm)\b.*?"
                           r"(\d{2,3}(?:[.,]\d)?)\s*kg\b")


def bmi(text: str, englisch: bool = False) -> str:
    kern = falten(text)
    treffer = BMI_SATZ.search(kern)
    umgekehrt = BMI_UMGEKEHRT.search(kern)
    if umgekehrt and (not treffer or umgekehrt.start(3) < (treffer.start(1) if treffer.group(1)
                                                           else treffer.start(4))):
        groesse, einheit, kg = umgekehrt.group(1), umgekehrt.group(2), umgekehrt.group(3)
    elif not treffer:
        return ""
    else:
        kg, groesse, einheit = (treffer.group(1), treffer.group(2), treffer.group(3)) if (
            treffer.group(1)) else (treffer.group(4), treffer.group(5), treffer.group(6))
    meter = zahl(groesse)
    if einheit == "cm" or meter > 3:
        meter /= 100
    if not 0.5 < meter < 2.6:
        return ""
    # 16.4.5: Die Stufe gilt fuer den angezeigten Wert -- vorher hiess es
    # "18,5 – Untergewicht" und "25 – Normalgewicht".
    wert = round(zahl(kg) / (meter * meter), 1)
    stufe = ("Untergewicht" if wert < 18.5 else "Normalgewicht" if wert < 25 else
             "Übergewicht" if wert < 30 else "starkes Übergewicht")
    if englisch:
        # 16.4.5: "What is my BMI if I weigh 70 kg ...?" bekam vorher eine deutsche Antwort.
        stufe_en = {"Untergewicht": "underweight", "Normalgewicht": "normal weight",
                    "Übergewicht": "overweight", "starkes Übergewicht": "obese"}[stufe]
        return (f"Your BMI is **{wert:.1f}** – that counts as {stufe_en}. The BMI is only a "
                "rough value: it does not count muscles, age or build.")
    return (f"Dein BMI liegt bei **{schoen(wert, 1)}** – das gilt als {stufe}. Der BMI ist aber "
            "nur ein grober Wert: Muskeln, Alter und Körperbau zählt er nicht mit.")


TRINKGELD = re.compile(rf"(?:{ZAHL}\s*%\s*)?trinkgeld.*?{ZAHL}\s*(?:€|eur|euro)?|"
                       rf"{ZAHL}\s*(?:€|eur|euro)?.*?trinkgeld(?:.*?{ZAHL}\s*%)?")


def trinkgeld(text: str) -> str:
    kern = falten(text).replace("€", " € ")
    if "trinkgeld" not in kern:
        return ""
    zahlen = [zahl(z) for z in re.findall(r"\d[\d.,]*", kern)]
    # "10 Prozent" wie "10 %": vorher galt die 10 als Betrag.
    prozent = re.search(r"(\d[\d.,]*)\s*(?:%|prozent\b)", kern)
    satz = zahl(prozent.group(1)) if prozent else 10.0
    betraege = [z for z in zahlen if not prozent or z != satz]
    if not betraege:
        return ("Üblich sind in Deutschland etwa 5 bis 10 % Trinkgeld. Nenn mir den Betrag, dann "
                "rechne ich es aus.")
    betrag = betraege[0]
    tg = betrag * satz / 100
    gesamt = round(betrag + tg, 2)
    # "Aufrunden auf 220 €" bei genau 220,00 € war sinnlos (16.4.5).
    runden = (f" Aufrunden auf {schoen(math.ceil(gesamt))} € geht auch."
              if gesamt != math.ceil(gesamt) else "")
    return (f"{schoen(satz)} % Trinkgeld auf {geld(betrag)} sind **{geld(tg)}** – "
            f"zusammen also **{geld(gesamt)}**.{runden}")


def geld(wert: float) -> str:
    """12,5 -> "12,50 €"."""
    return f"{wert:,.2f} €".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def passwort(text: str) -> str:
    import secrets
    import string

    kern = falten(text)
    if not re.search(r"\b(passwort|password|kennwort)\b", kern) or not re.search(
            r"\b(generier|erstell|erzeug|mach|gib|vorschlag|neues|zufaellig|sicheres)|"
            r"^(?:ein\s+)?(?:passwort|password|kennwort)\s+mit\s+\d{1,3}\s*(?:zeichen|stellen)$|"
            # 16.4.5: "Passwort mit 8 Zeichen ohne Sonderzeichen", "Passwort 12 Zeichen"
            r"^(?:ein\s+)?(?:passwort|password|kennwort)(?:\s+mit)?(?:\s+\d{1,3}\s*(?:zeichen|"
            r"stellen))?(?:\s+(?:und\s+)?(?:ohne|keine)\s+sonderzeichen)?$(?<!passwort)"
            r"(?<!password)(?<!kennwort)",
            kern):
        return ""
    laenge = re.search(r"\b(\d{1,3})\s*(?:zeichen|stellen|stellig|characters)", kern)
    n = max(12, min(64, int(laenge.group(1)))) if laenge else 20
    # 16.4.5: Vorher kamen still 12 statt 8 Zeichen -- wer ein Feld mit 8 Zeichen hat, merkt es
    # erst beim Einfuegen. Die Grenzen bleiben, die Antwort sagt sie jetzt.
    hinweis = ""
    if laenge and int(laenge.group(1)) < 12:
        hinweis = ("\n\nKürzer als 12 Zeichen mache ich keine Passwörter – die wären zu leicht "
                   "zu erraten.")
    elif laenge and int(laenge.group(1)) > 64:
        hinweis = "\n\nLänger als 64 Zeichen mache ich keine Passwörter."
    ohne = re.search(r"\b(?:ohne|keine)\s+sonderzeichen\b|\bnur\s+(?:buchstaben\s+und\s+)?"
                     r"(?:zahlen|ziffern)\s+und\s+buchstaben\b|\bwithout\s+special", kern)
    # 16.4.5: "ohne Sonderzeichen" galt vorher nicht.
    zeichen = string.ascii_letters + string.digits + ("" if ohne else "!@#$%&*+-=?")
    while True:
        wort = "".join(secrets.choice(zeichen) for _ in range(n))
        if (any(c.islower() for c in wort) and any(c.isupper() for c in wort)
                and any(c.isdigit() for c in wort)):
            break
    return (f"Hier ist ein zufälliges Passwort mit {n} Zeichen:\n\n`{wort}`\n\nEs wurde nur für "
            "dich erzeugt und nirgends gespeichert. Am besten legst du es gleich in einem "
            f"Passwort-Manager ab.{hinweis}")


# -- Zahlen und Texte ---------------------------------------------------------------------------

ROEMISCH = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
            (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
STERNZEICHEN = (((1, 20), "Steinbock ♑"), ((2, 19), "Wassermann ♒"), ((3, 20), "Fische ♓"),
                ((4, 20), "Widder ♈"), ((5, 20), "Stier ♉"), ((6, 21), "Zwillinge ♊"),
                ((7, 22), "Krebs ♋"), ((8, 23), "Löwe ♌"), ((9, 23), "Jungfrau ♍"),
                ((10, 23), "Waage ♎"), ((11, 22), "Skorpion ♏"), ((12, 21), "Schütze ♐"),
                ((12, 31), "Steinbock ♑"))


def roemisch(wert: int) -> str:
    teile = []
    for zahl_, zeichen in ROEMISCH:
        while wert >= zahl_:
            teile.append(zeichen)
            wert -= zahl_
    return "".join(teile)


def _roemisch_wert(zeichen: str) -> int:
    werte = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    summe = 0
    for i, z in enumerate(zeichen):
        wert = werte[z]
        summe += -wert if i + 1 < len(zeichen) and werte[zeichen[i + 1]] > wert else wert
    return summe


#: Kleine Zahlwoerter fuer "auf zwei Stellen".
KLEINE_ZAHLEN = {"null": 0, "eine": 1, "einer": 1, "eins": 1, "zwei": 2, "drei": 3, "vier": 4,
                 "fuenf": 5, "sechs": 6}
_LISTE = r"(-?\d[\d.,]*(?:(?:\s*[,;]\s*|\s+und\s+|\s+)-?\d[\d.,]*)+)"


def _werte(liste: str) -> list[float]:
    stuecke = re.split(r"\s+und\s+|\s*;\s*|,\s+|\s+", liste.strip(" ,."))
    try:
        return [zahl(st.strip(",")) for st in stuecke if st.strip(",")]
    except ValueError:
        return []


def _mehr_zahlen(kern: str) -> str:
    """16.4.5: Fragen, die vorher bei Wikipedia oder bei "kann ich nicht" landeten."""
    treffer = re.search(r"\b(median|maximum|minimum|groesste\s+zahl|kleinste\s+zahl)\s+"
                        r"(?:von|aus|der\s+zahlen|unter)\s+" + _LISTE, kern)
    if treffer:
        werte_ = _werte(treffer.group(2))
        if len(werte_) >= 2:
            art = treffer.group(1)
            if art == "median":
                return f"Der Median ist **{schoen(statistics.median(werte_), 4)}**."
            if art in ("maximum", "groesste zahl"):
                return f"Die größte Zahl ist **{schoen(max(werte_), 4)}**."
            return f"Die kleinste Zahl ist **{schoen(min(werte_), 4)}**."
    treffer = re.search(r"\bsumme\s+(?:aller\s+zahlen\s+|der\s+zahlen\s+)?(?:von\s+)?"
                        r"(-?\d{1,9})\s+bis\s+(-?\d{1,9})\b", kern)
    if treffer:
        a, b = int(treffer.group(1)), int(treffer.group(2))
        if a <= b:
            return (f"Die Summe der ganzen Zahlen von {schoen(a)} bis {schoen(b)} ist "
                    f"**{schoen((a + b) * (b - a + 1) // 2)}**.")
    treffer = re.search(r"\b(ggt|groesste[rn]?\s+gemeinsame[rn]?\s+teiler|kgv|kleinste[sn]?\s+"
                        r"gemeinsame[sn]?\s+vielfache)\s+(?:von\s+)?" + _LISTE, kern)
    if treffer:
        werte_ = _werte(treffer.group(2))
        if len(werte_) >= 2 and all(w == int(w) and 0 < abs(w) <= 10 ** 12 for w in werte_):
            ganze = [abs(int(w)) for w in werte_]
            if treffer.group(1).startswith(("ggt", "groesste")):
                return f"Der größte gemeinsame Teiler ist **{schoen(math.gcd(*ganze))}**."
            return f"Das kleinste gemeinsame Vielfache ist **{schoen(math.lcm(*ganze))}**."
    treffer = re.search(r"\bprimfaktor(?:en|zerlegung)\s+(?:von\s+)?(\d{1,10})\b", kern)
    if treffer:
        n = int(treffer.group(1))
        if n < 2:
            return f"{n} hat keine Primfaktoren."
        faktoren, rest, t = [], n, 2
        while t * t <= rest:
            while rest % t == 0:
                faktoren.append(t)
                rest //= t
            t += 1
        if rest > 1:
            faktoren.append(rest)
        return f"{schoen(n)} = **{' × '.join(schoen(f) for f in faktoren)}**"
    treffer = re.search(r"\brunde\w*\s+(-?\d[\d.,]*)\s+auf\s+(\d|" + "|".join(KLEINE_ZAHLEN)
                        + r")\s+(?:nach\s*komma\s*)?(?:stellen?|nachkommastellen?)\b", kern)
    if treffer:
        try:
            wert = decimal.Decimal(str(zahl(treffer.group(1))))
        except (ValueError, decimal.InvalidOperation):
            wert = None
        stellen = KLEINE_ZAHLEN.get(treffer.group(2))
        stellen = int(treffer.group(2)) if stellen is None else stellen
        if wert is not None:
            # Kaufmaennisch: 2,5 wird 3 (round() rundet zur geraden Zahl).
            gerundet = wert.quantize(decimal.Decimal(1).scaleb(-stellen), decimal.ROUND_HALF_UP)
            text = f"{gerundet:,.{stellen}f}".replace(",", "\x00").replace(".", ",")
            return f"Gerundet: **{text.replace(chr(0), '.')}**"
    treffer = re.search(r"\b(-?\d{1,6})\s*/\s*(\d{1,6})\s+(?:als|in)\s+(?:dezimalzahl|"
                        r"kommazahl|dezimal)\b", kern)
    if treffer and int(treffer.group(2)):
        a, b = int(treffer.group(1)), int(treffer.group(2))
        return f"{a}/{b} ist **{schoen(a / b, 6)}**."
    treffer = re.search(r"\b(-?\d{1,6}(?:,\d{1,6})?)\s+(?:als|in)\s+(?:einen\s+)?bruch\b",
                        kern)
    if treffer:
        bruch = fractions.Fraction(treffer.group(1).replace(",", ".")).limit_denominator(10 ** 6)
        if bruch.denominator == 1:
            return f"{treffer.group(1)} ist die ganze Zahl **{bruch.numerator}**."
        return f"{treffer.group(1)} ist als Bruch **{bruch.numerator}/{bruch.denominator}**."
    return ""


def zahlenkram(text: str, heute: date) -> str:
    """Primzahl, Schaltjahr, roemische Zahlen, Binaer/Hex, Durchschnitt, Sternzeichen."""
    kern = falten(text)
    treffer = re.search(r"\b(?:ist|war)\s+(?:die\s+)?(-?(?:\d{1,3}(?:\.\d{3}){1,3}|\d{1,12}))"
                        r"\s+(?:eine\s+)?primzahl\b", kern)
    if treffer:
        # 16.4.5: "1.000.003" und "-7" wurden vorher nicht erkannt.
        n = int(treffer.group(1).replace(".", ""))
        if n < 2:
            return f"Nein, {schoen(n)} ist keine Primzahl. Primzahlen beginnen bei 2."
        teiler = next((t for t in range(2, int(n ** 0.5) + 1) if n % t == 0), 0)
        if n < 2:
            return f"Nein, {n} ist keine Primzahl. Primzahlen beginnen bei 2."
        if teiler:
            return (f"Nein, {schoen(n)} ist keine Primzahl: Sie lässt sich durch {schoen(teiler)} "
                    f"teilen ({schoen(teiler)} × {schoen(n // teiler)}).")
        return f"Ja, **{schoen(n)}** ist eine Primzahl."
    # 16.4.5: "Ist 12 gerade?", "Ist 1001 durch 7 teilbar?", "Welche Teiler hat 28?",
    # "Quersumme von 12345" -- vorher "kann ich nicht" bzw. Wikipedia.
    treffer = re.search(r"\bist\s+(-?\d{1,15})\s+(?:eine\s+)?(gerade|ungerade)(?:\s+zahl)?\b", kern)
    if treffer:
        n = int(treffer.group(1))
        art = "gerade" if n % 2 == 0 else "ungerade"
        ja = art == treffer.group(2)
        return f"{'Ja' if ja else 'Nein'}, {schoen(n)} ist eine **{art}** Zahl."
    treffer = re.search(r"\bist\s+(-?\d{1,15})\s+(?:glatt\s+)?durch\s+(-?\d{1,15})\s+teilbar\b",
                        kern)
    if treffer:
        a, b = int(treffer.group(1)), int(treffer.group(2))
        if b == 0:
            return "Durch null kann man nicht teilen."
        if a % b == 0:
            return (f"Ja, {schoen(a)} ist durch {schoen(b)} teilbar: {schoen(a)} : {schoen(b)} = "
                    f"**{schoen(a // b)}**.")
        return (f"Nein, {schoen(a)} ist nicht durch {schoen(b)} teilbar – es bleibt der Rest "
                f"**{schoen(a % b)}**.")
    treffer = re.search(r"\b(?:welche\s+teiler\s+hat(?:\s+die\s+zahl)?|(?:die\s+|alle\s+)?teiler\s+"
                        r"(?:von|der\s+zahl))\s+(\d{1,9})\b", kern)
    if treffer:
        n = int(treffer.group(1))
        if n == 0:
            return "Jede Zahl außer 0 teilt 0 – die Liste hätte kein Ende."
        klein = [t for t in range(1, math.isqrt(n) + 1) if n % t == 0]
        alle = sorted(set(klein + [n // t for t in klein]))
        if len(alle) > 60:
            return f"{schoen(n)} hat **{len(alle)} Teiler**."
        return f"{schoen(n)} hat **{len(alle)} Teiler**: {', '.join(schoen(t) for t in alle)}."
    treffer = re.search(r"\bquersumme\s+(?:von\s+|aus\s+|der\s+zahl\s+)?(-?\d{1,40})\b", kern)
    if treffer:
        ziffern = treffer.group(1).lstrip("-")
        return f"Die Quersumme von {treffer.group(1)} ist **{sum(int(z) for z in ziffern)}**."
    # 16.4.5: "Was ist ein Schaltjahr?", "Wann war das letzte Schaltjahr?" und "Wann ist das
    # nächste?" bekamen vorher alle "Nein, 2026 ist kein Schaltjahr".
    if re.search(r"\bschaltjahr", kern) and not re.search(r"\d{4}", kern):
        def schalt(j: int) -> bool:
            return j % 4 == 0 and (j % 100 != 0 or j % 400 == 0)

        if re.search(r"\bwie\s*viele\s+tage\s+(?:hat|haben)\s+(?:ein|das)\s+schaltjahr", kern):
            # 16.4.5: vorher "Nein, 2026 ist kein Schaltjahr".
            return "Ein Schaltjahr hat **366 Tage** – der Februar hat dann 29 Tage."
        if re.search(r"^was\s+(?:ist|sind|bedeutet)\s+(?:ein\s+)?schaltjahr", kern):
            return ("Ein **Schaltjahr** hat 366 Tage – der Februar hat dann 29 Tage. Schaltjahre "
                    "sind durch 4 teilbar, außer volle Jahrhunderte, die nicht durch 400 teilbar "
                    "sind: 2000 war eins, 2100 ist keins.")
        if re.search(r"\b(?:letzte[sn]?|vorige[sn]?)\b", kern):
            letztes = next(j for j in range(heute.year - 1, heute.year - 9, -1) if schalt(j))
            return f"Das letzte Schaltjahr war **{letztes}**."
        if re.search(r"\b(?:wann|welche[sn]?|naechste[sn]?)\b", kern):
            naechstes = next(j for j in range(heute.year + 1, heute.year + 9) if schalt(j))
            jetzt_ = (f"Dieses Jahr ({heute.year}) ist ein Schaltjahr. " if schalt(heute.year)
                      else "")
            return f"{jetzt_}Das nächste Schaltjahr ist **{naechstes}**."
    treffer = re.search(r"\b(?:ist|war|wird)\s+(\d{4})\s+ein\s+schaltjahr\b|"
                        r"\bschaltjahr\b.*?\b(\d{4})\b", kern)
    if treffer or re.search(r"\bschaltjahr\b", kern):
        jahr = int(treffer.group(1) or treffer.group(2)) if treffer else heute.year
        ist = jahr % 4 == 0 and (jahr % 100 != 0 or jahr % 400 == 0)
        naechstes = next(j for j in range(jahr + 1, jahr + 9)
                         if j % 4 == 0 and (j % 100 != 0 or j % 400 == 0))
        if ist:
            return f"Ja, **{jahr}** ist ein Schaltjahr – der Februar hat 29 Tage."
        return f"Nein, {jahr} ist kein Schaltjahr. Das nächste ist **{naechstes}**."
    treffer = re.search(r"(?<![-\d.,])\b(\d{1,4})\s+(?:(?:in|als)\s+)?roemisch\w*", kern)
    if treffer:
        n = int(treffer.group(1))
        if 1 <= n <= 3999:
            return f"{n} schreibt man römisch **{roemisch(n)}**."
        return "Römische Zahlen kann ich von 1 bis 3999 schreiben."
    treffer = re.search(r"\b([mdclxvi]{1,15})\b\s+(?:in|als)\s+(?:arabisch\w*|zahl\w*|dezimal\w*|"
                        r"ziffern)|\broemische\s+zahl\s+([mdclxvi]{1,15})\b", kern)
    gross = re.fullmatch(r"(?i:was\s+(?:ist|bedeutet|heisst|heißt)|wie\s*viel\s+ist)\s+"
                         r"([MDCLXVI]{4,15})\s*[?!.]*", str(text).strip())
    if (not treffer and gross and _roemisch_wert(gross.group(1)) <= 3999
            and roemisch(_roemisch_wert(gross.group(1))) == gross.group(1)):
        # 16.4.5: "Was ist MMXXVI?" -- nur grossgeschrieben, ab vier Zeichen und gueltig.
        return f"Die römische Zahl {gross.group(1)} ist **{_roemisch_wert(gross.group(1))}**."
    if treffer:
        zeichen = (treffer.group(1) or treffer.group(2)).upper()
        werte = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
        summe = 0
        for i, z in enumerate(zeichen):
            wert = werte[z]
            summe += -wert if i + 1 < len(zeichen) and werte[zeichen[i + 1]] > wert else wert
        if 1 <= summe <= 3999 and roemisch(summe) == zeichen:
            return f"Die römische Zahl {zeichen} ist **{summe}**."
        return f"„{zeichen}“ ist keine gültige römische Zahl."
    treffer = re.search(r"\b0x([0-9a-f]{1,12})\b|\b0b([01]{1,48})\b", kern)
    if treffer and re.search(r"^(?:was\s+(?:ist|ergibt)|wie\s*viel\s+ist)\b|"
                             r"\b(?:in|als)\s+(?:dezimal|zahl|zehner)", kern):
        # 16.4.5: "Was ist 0xFF?", "0b1010 in dezimal"
        wert = int(treffer.group(1), 16) if treffer.group(1) else int(treffer.group(2), 2)
        return f"{treffer.group(0)} ist dezimal **{schoen(wert)}**."
    systeme = r"(binaer\w*|dual\w*|hex\w*|oktal\w*)"
    zurueck = re.search(r"\b([0-9a-f]{1,16})\s+(?:von\s+|aus\s+)?" + systeme
                        + r"\s+(?:in|als|nach|zu)\s+(?:dezimal\w*|zehner\w*|zahl)\b", kern)
    vorn = re.search(r"\b" + systeme + r"\s+([0-9a-f]{1,16})\s+(?:in|als|nach|zu)\s+"
                     r"(?:dezimal\w*|zehner\w*)\b", kern)
    if zurueck or vorn:
        # 16.4.5: "Was ist 1010 binär in dezimal?" rechnete vorher 1010 (dezimal) nach binaer.
        ziffern, art = ((zurueck.group(1), zurueck.group(2)) if zurueck
                        else (vorn.group(2), vorn.group(1)) if vorn else ("", ""))
        basis = 2 if art.startswith(("binaer", "dual")) else 16 if art.startswith("hex") else 8
        name = {2: "binär", 16: "hexadezimal", 8: "oktal"}[basis]
        try:
            return f"{ziffern.upper()} ({name}) ist dezimal **{schoen(int(ziffern, basis))}**."
        except ValueError:
            return f"„{ziffern.upper()}“ ist keine gültige Zahl im System {name}."
    treffer = re.search(r"\b(\d{1,15})\s+(?:(?:in|als)\s+)?(binaer\w*|dual\w*|hex\w*|oktal\w*)",
                        kern)
    if treffer:
        n, art = int(treffer.group(1)), treffer.group(2)
        if art.startswith(("binaer", "dual")):
            return f"{schoen(n)} ist binär **{n:b}**."
        if art.startswith("hex"):
            return f"{schoen(n)} ist hexadezimal **{n:X}**."
        return f"{schoen(n)} ist oktal **{n:o}**."
    treffer = re.search(r"\b(durchschnitt|mittelwert|summe)\s+(?:von|aus)\s+([\d.,;\s]+(?:und\s+"
                        r"[\d.,]+)?)", kern)
    if treffer:
        stuecke = re.split(r"\s+und\s+|\s*;\s*|,\s+|\s+", treffer.group(2).strip(" ,."))
        try:
            werte_ = [zahl(st.strip(",")) for st in stuecke if st.strip(",")]
        except ValueError:
            werte_ = []
        if len(werte_) >= 2:
            if treffer.group(1) == "summe":
                return f"Die Summe ist **{schoen(sum(werte_), 4)}**."
            return (f"Der Durchschnitt von {len(werte_)} Zahlen ist "
                    f"**{schoen(sum(werte_) / len(werte_), 4)}**.")
    text_zahl = _mehr_zahlen(kern)
    if text_zahl:
        return text_zahl
    if "sternzeichen" in kern:
        tag = datum_aus(kern, heute)
        if tag:
            name = next(n for (monat, bis), n in STERNZEICHEN
                        if (tag.month, tag.day) <= (monat, bis))
            return f"Wer am {tag:%d.%m.} Geburtstag hat, ist **{name}**."
        return ("Sag mir das Datum dazu, zum Beispiel: „Welches Sternzeichen ist der 3. Mai?“")
    return ""


def textkram(text: str) -> str:
    """Buchstaben und Woerter zaehlen, rueckwaerts schreiben, buchstabieren."""
    roh = re.sub(r"\s+", " ", str(text)).strip()

    def inhalt(stueck: str) -> str:
        return stueck.strip().strip("?!.").strip().strip("\"'„“”‚‘»«:").strip()

    treffer = re.search(r"wie\s*viele\s+(buchstaben|zeichen|w(?:ö|oe)rter)\s+"
                        r"(?:hat|haben|sind\s+in|stecken\s+in|enth(?:ä|ae)lt)\s+"
                        # 16.4.5: auch "der Satz: ..." mit Doppelpunkt
                        r"((?:das\s+wort|der\s+satz|der\s+text|der\s+name)\s*:?\s+)?(.+)",
                        roh, re.I)
    if treffer:
        was, stueck = treffer.group(1).lower(), inhalt(treffer.group(3))
        # "Wie viele Zeichen hat ein Tweet?" ist eine Wissensfrage, kein Zaehlauftrag.
        gemeint = bool(treffer.group(2)) or treffer.group(3).strip()[:1] in "\"'„“‚»" or (
            was == "buchstaben" and len(stueck.split()) == 1)
        if stueck and gemeint:
            if was == "buchstaben":
                return f"„{stueck}“ hat **{sum(1 for c in stueck if c.isalpha())} Buchstaben**."
            if was == "zeichen":
                return f"„{stueck}“ hat **{len(stueck)} Zeichen** (mit Leerzeichen)."
            anzahl = len(stueck.split())
            if anzahl == 1:
                return "Das ist **1 Wort**."
            return f"Das sind **{anzahl} Wörter**."
    treffer = re.search(r"z(?:ä|ae)hl\w*\s+(?:mal\s+)?(?:die\s+)?(w(?:ö|oe)rter|buchstaben|"
                        r"zeichen)\s*:?\s+(?:in|von|im\s+text|im\s+satz)?\s*:?\s*(.+)", roh, re.I)
    if treffer and inhalt(treffer.group(2)):
        was, stueck = treffer.group(1).lower(), inhalt(treffer.group(2))
        if was == "buchstaben":
            return f"„{stueck}“ hat **{sum(1 for c in stueck if c.isalpha())} Buchstaben**."
        if was == "zeichen":
            return f"„{stueck}“ hat **{len(stueck)} Zeichen** (mit Leerzeichen)."
        anzahl = len(stueck.split())
        return "Das ist **1 Wort**." if anzahl == 1 else f"Das sind **{anzahl} Wörter**."
    treffer = re.search(r"schreib\w*\s+(.+?)\s+(klein|gro(?:ß|ss))(?:\s+geschrieben)?$",
                        roh.strip(" ?!."), re.I)
    if treffer and inhalt(treffer.group(1)):
        stueck = inhalt(treffer.group(1))
        return stueck.lower() if treffer.group(2).lower() == "klein" else stueck.upper()
    treffer = re.search(r"(?:schreib\w*|dreh\w*|sag\w*)\s+(.+?)\s+r(?:ü|ue)ckw(?:ä|ae)rts",
                        roh, re.I)
    if treffer and inhalt(treffer.group(1)):
        stueck = inhalt(treffer.group(1))
        return f"„{stueck}“ rückwärts ist **{stueck[::-1]}**."
    # 16.4.5: "Dreh das Wort Lagerregal um", "Ist Otto ein Palindrom?", "Sortiere 5, 3, 9, 1"
    treffer = re.fullmatch(r"dreh\w*\s+(?:(?:das\s+wort|den\s+satz)\s+(.+?)|"
                           r"([„\x22'‚»].+?[“\x22'‘«]))\s+um", roh.strip(" ?!."), re.I)
    if treffer and inhalt(treffer.group(1) or treffer.group(2)):
        stueck = inhalt(treffer.group(1) or treffer.group(2))
        return f"„{stueck}“ rückwärts ist **{stueck[::-1]}**."
    treffer = re.fullmatch(r"ist\s+(.+?)\s+ein\s+palindrom", roh.strip(" ?!."), re.I)
    if treffer and inhalt(treffer.group(1)):
        stueck = inhalt(treffer.group(1))
        nur = [c.casefold() for c in stueck if c.isalnum()]
        if nur and nur == nur[::-1]:
            return f"Ja, „{stueck}“ ist ein Palindrom – vorwärts und rückwärts gleich."
        return f"Nein, „{stueck}“ ist kein Palindrom. Rückwärts heißt es „{stueck[::-1]}“."
    treffer = re.fullmatch(r"sortier\w*\s+(?:mir\s+)?(?:die\s+(?:zahlen|w(?:ö|oe)rter|liste)"
                           r"\s*:?\s*)?(.+?)(?:\s+(auf|ab)steigend|\s+alphabetisch)?",
                           roh.strip(" ?!."), re.I)
    if treffer:
        teile = [t.strip(" „“\"'") for t in re.split(r"\s*[,;]\s*|\s+und\s+", treffer.group(1))]
        teile = [t for t in teile if t]
        if len(teile) >= 2:
            try:
                sortiert = [schoen(w, 4) for w in sorted(zahl(t) for t in teile)]
            except ValueError:
                sortiert = sorted(teile, key=lambda t: falten(t))
            if (treffer.group(2) or "").lower() == "ab":
                sortiert.reverse()
            return "Sortiert: **" + ", ".join(sortiert) + "**"
    treffer = re.search(r"buchstabier\w*\s+(?:mir\s+)?(?:das\s+wort\s+)?(.+)", roh, re.I)
    if treffer and inhalt(treffer.group(1)):
        stueck = inhalt(treffer.group(1))[:40]
        # "ß".upper() ist "SS": Das ist beim Buchstabieren falsch (16.4.5).
        return " – ".join(c if c == "ß" else c.upper() for c in stueck if not c.isspace())
    treffer = re.search(r"(?:schreib\w*\s+)?(.+?)\s+in\s+(gro(?:ß|ss)buchstaben|kleinbuchstaben)",
                        roh, re.I)
    if treffer and inhalt(treffer.group(1)):
        stueck = inhalt(treffer.group(1))
        return stueck.upper() if treffer.group(2).lower().startswith("gro") else stueck.lower()
    return ""


# -- Ein bisschen Gespraech ---------------------------------------------------------------------

LANGEWEILE = ("Wie wär's mit einem kurzen Spaziergang? Frische Luft wirkt Wunder.",
              "Lern doch heute fünf Wörter in einer neuen Sprache.",
              "Räum eine Schublade auf – das fühlt sich danach erstaunlich gut an.",
              "Schreib jemandem, von dem du lange nichts gehört hast.",
              "Probier ein neues Rezept mit dem aus, was gerade im Kühlschrank ist.",
              "Mach ein Foto von etwas Schönem in deiner Nähe.",
              "Hör ein Album komplett durch, das du noch nicht kennst.")
MUT = ("Du schaffst das. Ein Schritt nach dem anderen reicht völlig.",
       "Fehler sind kein Rückschritt, sondern ein Teil vom Weg.",
       "Denk daran, wie viel du schon geschafft hast. Das hier schaffst du auch.",
       "Es ist okay, eine Pause zu machen. Danach geht es mit frischer Kraft weiter.",
       "Kleine Fortschritte sind auch Fortschritte. Sei stolz darauf.")
TROST = ("Schlechte Tage gehören dazu – und sie gehen vorbei.",
         "Du musst heute nichts leisten. Sei einfach freundlich zu dir.",
         "Es ist okay, wenn gerade nicht alles gut ist.",
         "Du bist damit nicht allein, auch wenn es sich gerade so anfühlt.")
FAKTEN = ("Honig verdirbt praktisch nie – in ägyptischen Gräbern fand man essbaren Honig.",
          "Ein Tag auf der Venus dauert länger als ein Jahr auf der Venus.",
          "Oktopusse haben drei Herzen und blaues Blut.",
          "Bananen sind botanisch gesehen Beeren, Erdbeeren dagegen nicht.",
          "Der Eiffelturm ist im Sommer bis zu 15 Zentimeter höher, weil sich das Eisen ausdehnt.",
          "Kühe haben beste Freundinnen und sind gestresst, wenn man sie trennt.",
          "Auf der Erde gibt es mehr Bäume als Sterne in der Milchstraße.")


ESSEN = ("Nudeln mit Tomatensoße und frischem Basilikum – geht schnell und schmeckt immer.",
         "Ofengemüse mit Feta: alles klein schneiden, Öl drüber, 25 Minuten in den Ofen.",
         "Pfannkuchen – süß mit Apfelmus oder herzhaft mit Käse.",
         "Eine große Gemüsepfanne mit Reis und Sojasoße.",
         "Kartoffeln mit Kräuterquark – einfach, günstig, lecker.",
         "Ein Wrap mit allem, was der Kühlschrank hergibt.",
         "Linsensuppe: wärmt und hält lange satt.",
         "Rührei mit Brot und einem kleinen Salat dazu.")
ZITATE = ("„Auch aus Steinen, die einem in den Weg gelegt werden, kann man Schönes bauen.“ "
          "(Johann Wolfgang von Goethe zugeschrieben)",
          "„Es ist nicht wenig Zeit, die wir haben, sondern es ist viel Zeit, die wir nicht "
          "nutzen.“ (Seneca)",
          "„Der Weg ist das Ziel.“ (Konfuzius zugeschrieben)",
          "„Wer immer tut, was er schon kann, bleibt immer das, was er schon ist.“ "
          "(Henry Ford zugeschrieben)",
          "„Phantasie ist wichtiger als Wissen, denn Wissen ist begrenzt.“ (Albert Einstein)")
KOMPLIMENTE = ("Du stellst gute Fragen – das zeigt, dass du neugierig bist.",
               "Mit dir zu schreiben macht richtig Spaß.",
               "Du gibst nicht so schnell auf. Das ist eine echte Stärke.",
               "Ich finde es klasse, dass du Dinge genau wissen willst.")
RAETSEL = (("Was hat Zähne, aber beißt nicht?", "Ein Kamm."),
           ("Was wird nass, während es trocknet?", "Ein Handtuch."),
           ("Was hat ein Bett, schläft aber nie?", "Ein Fluss."),
           ("Was geht die Treppe hoch und runter und bewegt sich nicht?", "Der Teppich."),
           ("Je mehr du davon wegnimmst, desto größer wird es. Was ist das?", "Ein Loch."))
ZUNGENBRECHER = ("Fischers Fritze fischt frische Fische, frische Fische fischt Fischers Fritze.",
                 "Blaukraut bleibt Blaukraut und Brautkleid bleibt Brautkleid.",
                 "Zehn zahme Ziegen zogen zehn Zentner Zucker zum Zoo.",
                 "Wenn Fliegen hinter Fliegen fliegen, fliegen Fliegen Fliegen nach.")
SCHLECHT = re.compile(
    r"\b(motivier\w*|mut\s+machen|muntere?\s+mich\s+auf|aufmuntern|hab\w?\s+keine\s+lust|"
    r"schaffe?\s+(?:das|es)\s+nicht|(?:mir\s+)?geht\s*'?(?:es|s)\s+(?:mir\s+)?(?:heute\s+)?"
    r"(?:gar\s+|echt\s+|wirklich\s+|gerade\s+)?(?:nicht\s+(?:so\s+)?gut|schlecht|mies|"
    r"beschissen|dreckig)|bin\s+(?:so\s+|sehr\s+|total\s+|gerade\s+|echt\s+)?(?:traurig|down|"
    r"niedergeschlagen|einsam|allein|verzweifelt|ungluecklich|deprimiert|gestresst|"
    r"ueberfordert|erschoepft|fertig|am\s+ende)|fuehle\s+mich\s+(?:so\s+|sehr\s+|total\s+)?"
    r"(?:schlecht|einsam|allein|leer|mies|traurig|ueberfordert)|mir\s+ist\s+zum\s+heulen|"
    r"hab\w?\s+(?:so\s+|grosse\s+|viel\s+)?(?:angst|sorgen|stress|kummer|liebeskummer)|"
    r"alles\s+(?:ist\s+)?(?:zu\s+viel|sinnlos|doof|bloed)|kann\s+nicht\s+mehr|"
    # 16.4.5: "Ich hatte einen schlechten Tag" -- die Trost-Antworten passen genau dazu.
    r"(?:hatte|habe|hab)\s+(?:heute\s+)?(?:einen\s+|nen\s+)?(?:echt\s+|so\s+|richtig\s+)?"
    r"(?:schlechten|miesen|beschissenen|harten|bloeden|doofen)\s+tag)\b")


#: Wer so schreibt, braucht einen Menschen -- und zwar sofort die richtigen Nummern.
KRISE = re.compile(
    r"\b(nicht\s+mehr\s+(?:weiter)?leben|(?:will|moechte|wuerde\s+(?:gern|gerne|am\s+liebsten))"
    r"\s+(?:nur\s+noch\s+|einfach\s+|lieber\s+)?(?:sterben|tot\s+sein)|"
    # 16.4.5: "Ich will einfach nur tot sein", "Am liebsten wäre ich tot" bekamen keine Hilfe.
    r"(?:will|moechte)\s+(?:(?!nicht\b)\w+\s+){1,3}?(?:sterben|tot\s+sein)|"
    r"(?:am\s+liebsten|lieber|besser)\s+waere\s+ich\s+tot|waere\s+ich\s+(?:doch\s+)?"
    r"(?:lieber\s+|besser\s+)?tot|mich\s+(?:selbst\s+)?"
    r"umbringen|bringe?\s+mich\s+(?:selbst\s+)?um|mir\s+das\s+leben\s+(?:zu\s+)?nehmen|"
    r"nehme\s+mir\s+das\s+leben|(?:suizid|selbstmord)gedanken|(?:denke|gedanken|gedacht)\s+"
    r"(?:\w+\s+){0,3}?(?:suizid|selbstmord)|mich\s+(?:selbst\s+)?ritzen|ritze\s+mich|"
    r"mich\s+(?:selbst|absichtlich)\s+verletzen|verletze\s+mich\s+(?:selbst|absichtlich)|"
    r"(?:will|moechte|werde|muss)\s+mich\s+(?:selbst\s+)?verletzen|verletze\s+mich$|"
    r"will\s+nicht\s+mehr\s+da\s+sein|waere\s+(?:lieber|besser)\s+tot|"
    r"(?:mein\s+)?leben\s+hat\s+keinen\s+sinn(?:\s+mehr)?)\b")
KRISE_TEXT = (
    "Das klingt sehr schwer. Gut, dass du es schreibst.\n\n"
    "Ich bin ein Programm mit festen Antworten. Dabei können dir Menschen besser helfen:\n\n"
    "- **Telefonseelsorge:** 0800 111 0 111 oder 0800 111 0 222. Kostenlos, anonym, Tag und "
    "Nacht. Auch als Chat: [online.telefonseelsorge.de](https://online.telefonseelsorge.de)\n"
    "- **Nummer gegen Kummer** für Kinder und Jugendliche: 116 111 (kostenlos)\n"
    "- **Bist du in akuter Gefahr?** Ruf sofort den Notruf **112** an.\n\n"
    "Du musst da nicht allein durch. Sag am besten auch jemandem Bescheid, dem du vertraust.")


KRISE_EN = re.compile(
    r"\b(want(?:s)?\s+to\s+die|wanna\s+die|kill(?:ing)?\s+myself|end(?:ing)?\s+my\s+(?:own\s+)?"
    r"life|take\s+my\s+(?:own\s+)?life|suicidal|suicide\s+thoughts|thoughts\s+of\s+suicide|"
    r"(?:do\s*n.?t|do\s+not)\s+want\s+to\s+(?:live|be\s+alive|be\s+here)\s*(?:anymore)?|"
    r"harm(?:ing)?\s+myself|cutting\s+myself|(?:hurt(?:ing)?|cut(?:ting)?)\s+myself\s+on\s+purpose|"
    r"self[\s-]?harm(?:ing)?|"
    r"better\s+off\s+dead)\b")
KRISE_TEXT_EN = (
    "That sounds really hard. I'm glad you wrote it down.\n\n"
    "I'm a program with fixed answers. People can help you much better:\n\n"
    "- **In Germany:** Telefonseelsorge 0800 111 0 111 or 0800 111 0 222. Free, anonymous, "
    "day and night.\n"
    "- **In other countries:** [findahelpline.com](https://findahelpline.com) lists free "
    "helplines.\n"
    "- **In immediate danger?** Call the emergency number now: **112** in Europe, **911** in "
    "the US.\n\n"
    "You don't have to go through this alone. Tell someone you trust, too.")


def krise(text: str) -> str:
    kern = falten(text)
    if KRISE.search(kern):
        return KRISE_TEXT
    return KRISE_TEXT_EN if KRISE_EN.search(kern) else ""


def gespraech(text: str, rnd: random.Random) -> str:
    kern = falten(text)
    treffer = SCHLECHT.search(kern)
    if treffer and re.match(r"motivier|mut|munter|aufmunter|hab\w?\s+keine|schaff",
                            treffer.group(1)):
        return (rnd.choice(MUT) + "\n\nWenn es dir länger schlecht geht, rede mit jemandem, dem du "
                "vertraust. Bei der Telefonseelsorge erreichst du rund um die Uhr jemanden: "
                "0800 111 0 111 (kostenlos).")
    if treffer:
        return ("Das tut mir leid zu hören. " + rnd.choice(TROST)
                + "\n\nManchmal hilft schon eine Kleinigkeit: kurz an die frische Luft, ein Glas "
                "Wasser, jemandem schreiben. Wenn es dir länger schlecht geht, rede mit jemandem, "
                "dem du vertraust. Bei der Telefonseelsorge erreichst du rund um die Uhr jemanden: "
                "0800 111 0 111 (kostenlos).")
    if re.search(r"\bwas\s+(?:soll|kann|koennte)\s+ich\s+(?:heute\s+|morgen\s+)?(?:abend\s+)?"
                 r"(?:kochen|essen)\b|\b(?:hab\w?\s+hunger|rezeptidee|idee\s+(?:zum|fuers)\s+"
                 r"(?:kochen|essen|abendessen|mittagessen))\b", kern):
        ideen = rnd.sample(ESSEN, 3)
        return ("Da fällt mir etwas ein:\n" + "\n".join(f"- {i}" for i in ideen)
                + "\n\nGuten Appetit!")
    if re.search(r"\b(zitat|spruch|weisheit|lebensweisheit)\b", kern):
        return rnd.choice(ZITATE)
    if re.search(r"\b(kompliment|sag\s+(?:mir\s+)?(?:was|etwas)\s+nettes)\b", kern):
        return rnd.choice(KOMPLIMENTE)
    if re.search(r"\b(raetsel|scherzfrage)\b", kern):
        frage, loesung = rnd.choice(RAETSEL)
        return f"{frage}\n\n*Lösung: {loesung}*"
    if re.search(r"\bzungenbrecher\b", kern):
        return "Versuch den mal dreimal schnell hintereinander:\n\n" + rnd.choice(ZUNGENBRECHER)
    # "Mir ist nicht langweilig" bekam vorher Ideen gegen Langeweile (16.4.5).
    if re.search(r"\b(langweilig|langeweile|bored|was\s+(?:soll|kann)\s+ich\s+(?:heute\s+)?"
                 r"(?:machen|tun|unternehmen))\b", kern) and not re.search(
                     r"\b(?:nicht|nie|keine)\s+(?:so\s+|mehr\s+)?(?:langweilig|langeweile)|not\s+bored",
                     kern):
        ideen = rnd.sample(LANGEWEILE, 3)
        return ("Ich hab ein paar Ideen für dich:\n" + "\n".join(f"- {i}" for i in ideen)
                + "\n\nUnd wenn das Wetter mitspielt: Frag mich einfach, wie es draußen wird.")
    # "Erzähl mir einen Fakt" kannte Standard vorher nicht (16.4.5).
    if re.search(r"\b(fun\s*fact|erzaehl\s+(?:mir\s+)?(?:was|etwas)\s+(?:interessantes|spannendes)|"
                 r"(?:erzaehl|nenn|sag|gib)\w*\s+(?:mir\s+)?(?:einen|ein|nen|noch\s+einen)\s+"
                 r"(?:fakt|zufaelligen\s+fakt|interessanten\s+fakt)|fakt\s+des\s+tages|"
                 r"wusstest\s+du|interessante\s+tatsache)\b", kern):
        return "Wusstest du schon? " + rnd.choice(FAKTEN)
    if re.search(r"^(?:was\s+kannst\s+du|hilfe|help|was\s+(?:kann|koennte)\s+ich\s+dich\s+fragen|"
                 r"wie\s+funktionierst\s+du)\b", kern):
        return HILFE
    return ""


HILFE = ("Ich bin Aquaticy Standard und komme ganz ohne Sprachmodell aus. Das kann ich:\n"
         "- **Wetter:** heute, morgen, am Wochenende oder die ganze Woche, auch für mehrere Orte "
         "auf einmal – dazu was du anziehen sollst, ob du einen Schirm brauchst und wann die "
         "Sonne aufgeht\n"
         "- **Rechnen:** Aufgaben, Wurzeln, Prozente, Mehrwertsteuer, Trinkgeld, BMI, Einheiten, "
         "Durchschnitt, Primzahlen, römische Zahlen, Binär und Hex\n"
         "- **Zeit:** Uhrzeit (auch in anderen Städten), Datum, Feiertage, Muttertag, Advent, "
         "Zeitumstellung, Mondphase, Sternzeichen, Countdowns und dein Alter\n"
         "- **Wissen:** Nachrichten, Wechselkurse und kurze Antworten aus Wikipedia\n"
         "- **Texte:** Buchstaben und Wörter zählen, rückwärts schreiben, buchstabieren\n"
         "- **Kleinigkeiten:** Würfeln, Münzwurf, „Pizza oder Pasta?“, Witze, Rätsel, "
         "Zungenbrecher, Zitate, Fun Facts, Ideen zum Kochen und gegen Langeweile, sichere "
         "Passwörter\n\n"
         "Ich merke mir auch, was du mir erzählst – zum Beispiel, wo du wohnst.")


# -- Secure Pro ---------------------------------------------------------------------------------

SICHERHEIT_TIPPS = {
    "phishing": ("**Phishing** sind gefälschte Mails, SMS oder Seiten, die an Passwörter oder Geld "
                 "wollen. So schützt du dich: Links nicht anklicken, sondern die Seite selbst "
                 "aufrufen. Absender genau prüfen. Nie Passwörter oder TANs per Mail oder Telefon "
                 "weitergeben. Zwei-Faktor-Anmeldung einschalten."),
    "passwort": ("**Gute Passwörter** sind lang (mindestens 12 Zeichen), für jeden Dienst anders "
                 "und zufällig. Am einfachsten mit einem Passwort-Manager. Schalte zusätzlich die "
                 "Zwei-Faktor-Anmeldung ein. Prüfen, ob ein Passwort geleakt ist: "
                 "[Have I Been Pwned](https://haveibeenpwned.com)."),
    "wlan": ("**WLAN sicher machen:** WPA3 oder WPA2 mit langem Passwort, WPS aus, das "
             "Router-Passwort ändern, Firmware aktuell halten, Gäste in ein eigenes Gastnetz."),
    "update": ("**Updates** schließen Sicherheitslücken. Schalte automatische Updates für System, "
               "Browser, Apps und Router ein. Geräte ohne Updates gehören nicht ins Internet."),
    "backup": ("**Backups** schützen vor Erpressersoftware: 3-2-1-Regel – drei Kopien, zwei "
               "verschiedene Speicher, eine davon außer Haus oder offline."),
}


def sicherheit(text: str) -> str:
    """Antwort aus dem festen Sicherheitswissen (aquaticy/secure_knowledge.py) -- oder ""."""
    from aquaticy import secure_knowledge

    kern = falten(text)
    for stichwort, tipp in SICHERHEIT_TIPPS.items():
        if stichwort in kern:
            return tipp
    if re.search(r"\b(?:wpa[23]?|wep|wps|router)\b", kern):
        return SICHERHEIT_TIPPS["wlan"]
    port = re.search(r"\bport\s+(\d{1,5})\b", kern)
    worte = [w for w in re.findall(r"[a-z0-9-]{3,}", kern) if w not in {
        "was", "ist", "der", "die", "das", "wie", "bei", "mit", "und", "ich", "mein", "meine",
        "einen", "eine", "ein", "gegen", "schuetze", "schuetzen", "hilft", "port",
        # 16.4.5: "Wie sicher ist WPA3?" fand vorher "unsicher" im Text zu Ransomware.
        "sicher", "unsicher", "sind", "kann", "man", "mir", "mich", "gut", "gefaehrlich",
        "bedeutet", "heisst", "offen", "warum", "welche", "welcher", "soll", "sollte",
        # 16.4.5: "Was läuft auf Port 443?" fand "auf" in einem Text zu Mirai, "Was macht
        # Port 53?" fand "macht" beim SOCKS-Proxy.
        "auf", "laeuft", "macht", "machen", "tut", "gibt", "hat", "haben", "fuer", "von", "dem",
        "den", "des", "eigentlich", "genau", "erklaer", "erklaere", "bitte", "zum", "zur"}]
    if port:
        # Mit Port zaehlt nur der Port -- sonst fand ein anderes Wort etwas Falsches.
        worte = []
    for stichwort in ([port.group(1)] if port else []) + worte:
        try:
            treffer = secure_knowledge.lookup(stichwort)
        except Exception:
            continue
        ergebnisse = [e for e in (treffer or {}).get("results") or [] if isinstance(e, dict)]
        if not ergebnisse:
            continue
        if not port:
            # 16.4.5: "Was ist ein Trojaner?" nannte vorher Port 20000 statt der Malware-Familie,
            # "Was ist RDP?" Mirai statt der Zeile zu RDP: erst wer das Wort im Namen traegt,
            # dann Schwachstellen, riskante Dienste, zuletzt Malware, die es nur erwaehnt.
            def rang(e: dict[str, Any], wort: str = stichwort) -> tuple[int, int]:
                name = falten(str(e.get("name") or ""))
                # Wer so heisst ("Mirai und Nachfolger", "SMB (Windows-Freigabe)"), vor dem,
                # der das Wort nur im Namen traegt ("Telnet-Ersatz (Mirai)").
                stufe = (0 if re.match(rf"{re.escape(wort)}(?![a-z0-9])", name) else
                         1 if re.search(rf"(?<![a-z]){re.escape(wort)}", name) else 2)
                art = {"schwachstelle": 0, "riskant": 1, "verdaechtig": 2,
                       "verdächtig": 2}.get(str(e.get("art") or ""), 3)
                return (stufe, art)

            ergebnisse.sort(key=rang)
        zeilen = []
        for e in ergebnisse[:3]:
            kopf = f"**{e.get('name', '')}**" + (f" (Port {e['port']})" if e.get("port") else "")
            text_teile = [str(e[k]) for k in ("text", "signs") if e.get(k)]
            rat = e.get("hint") or e.get("defense")
            zeile = kopf + (": " + " ".join(text_teile) if text_teile else "")
            if rat:
                zeile += f" **Was tun:** {rat}"
            zeilen.append("- " + zeile)
        return "\n".join(zeilen) + "\n\n*Ein Treffer ist ein Verdacht, kein Beweis.*"
    if port:
        return (f"Port {port.group(1)} steht nicht auf meiner Liste riskanter oder verdächtiger "
                "Ports. Ob er bei dir offen sein soll, hängt vom Dienst ab, der dort läuft.")
    return ""


# -- Gespraechsspeicher -------------------------------------------------------------------------

ORT_IM_TEXT = re.compile(r"\*\*(?:Heute|Morgen|Übermorgen|Das Wochenende|Die nächsten Tage|"
                         r"[A-ZÄÖÜ][a-zäöü]+, \d\d\.\d\d\.) in ([^:*]+):\*\*"
                         r"|\b[Ii]n \*\*([^*]{2,40})\*\*")


def letzter_ort(verlauf: list[dict[str, Any]]) -> str:
    """Der Ort, um den es zuletzt ging -- aus den eigenen Antworten dieses Gespraechs.

    Hat der Nutzer danach gesagt, wo er wohnt, gilt das (der Wohnort kommt dann vom Aufrufer).
    """
    for eintrag in reversed(verlauf[-12:]):
        if not isinstance(eintrag, dict):
            continue
        if eintrag.get("role") == "user" and re.search(
                r"\b(?:wohne|lebe)\s+(?:jetzt\s+|seit\s+\S+\s+)?in\b|\bi\s+live\s+in\b",
                falten(str(eintrag.get("content") or ""))):
            return ""
        if eintrag.get("role") != "assistant":
            continue
        treffer = ORT_IM_TEXT.search(str(eintrag.get("content") or ""))
        if treffer:
            return (treffer.group(1) or treffer.group(2)).strip()
    return ""


TAG_IM_TEXT = re.compile(r"\*\*(Heute|Morgen|Übermorgen) in [^:*]+:\*\*|"
                         r"\bFür (heute|morgen|übermorgen) in \*\*|"
                         r"\b(Heute|Morgen|Übermorgen) geht die Sonne in \*\*")


def letzte_wetterfrage(verlauf: list[dict[str, Any]]) -> tuple[str, int] | None:
    """Ort und Tag der letzten Antwort mit Ort -- fuer "und morgen?" und "und in Köln?".

    Es zaehlt die juengste Antwort: Ging es zuletzt um heute (auch beim Schirm oder beim
    Anziehen), gilt eine Folgefrage ohne Tag fuer heute.
    """
    for eintrag in reversed(verlauf[-6:]):
        if eintrag.get("role") != "assistant":
            continue
        text = str(eintrag.get("content") or "")
        ort = ORT_IM_TEXT.search(text)
        if not ort:
            continue
        tag = TAG_IM_TEXT.search(text)
        wort = next((g for g in tag.groups() if g), "heute").lower() if tag else "heute"
        return ((ort.group(1) or ort.group(2)).strip(),
                ("heute", "morgen", "übermorgen").index(wort))
    return None


def absicht(kern: str) -> str:
    """Was die Frage will -- fuer Antworten, die einen Ort brauchen."""
    if ANZIEHEN_WORT.search(kern):
        return "anziehen"
    if SCHIRM_WORT.search(kern):
        return "schirm"
    if SONNE_WORT.search(kern):
        return "sonne"
    if WETTER_WORT.search(kern) or DRAUSSEN.search(kern):
        return "wetter"
    return ""


#: 16.4.5: "Was ist ein Regenschirm?", "What is Sunset Boulevard?" fragten vorher nach dem Ort.
DEFINITION = re.compile(r"^(?:was\s+(?:ist|sind|bedeutet|heisst)|wer\s+(?:ist|war)|"
                        r"what\s+(?:is|are)|who\s+(?:is|was))\s+\S")
WETTER_THEMEN = frozenset({"wetter", "weather", "temperatur", "temperature", "vorhersage",
                           "wettervorhersage", "forecast", "wetterbericht"})


def definitionsfrage(frage: str, kern: str) -> bool:
    """Eine Frage nach der Bedeutung eines Wortes -- ohne Ort, Tag und ohne "Wetter" als Thema."""
    if not DEFINITION.match(kern) or orte_aus(frage):
        return False
    if re.search(r"\b(heute|morgen|uebermorgen|today|tomorrow|tonight|wochenende|weekend|"
                 r"jetzt|gerade|now|draussen|outside)\b", kern):
        return False
    thema = falten(thema_aus(frage))
    # Nur "Wetter" allein ist eine Wetterfrage -- "Unterschied zwischen Wetter und Klima" nicht.
    return bool(thema) and thema not in WETTER_THEMEN


def offene_ortsfrage(verlauf: list[dict[str, Any]]) -> str:
    """Hat Aquaticy gerade nach dem Ort gefragt? Returns: die Frage davor -- oder ""."""
    if len(verlauf) < 2:
        return ""
    letzte = verlauf[-1]
    if letzte.get("role") != "assistant" or ORT_FRAGE not in str(letzte.get("content") or ""):
        return ""
    for eintrag in reversed(verlauf[:-1]):
        if eintrag.get("role") == "user":
            return str(eintrag.get("content") or "")
    return ""


def sieht_aus_wie_ort(text: str) -> bool:
    """"Erkelenz", "in Köln", "New York" -- kurz, ohne Fragewort und ohne Zahlenrechnung."""
    kern = falten(text)
    if not kern or len(kern) > 40 or len(kern.split()) > 4:
        return False
    if re.search(r"\b(was|wie|wer|wann|warum|wieso|weshalb|welche[rsmn]?|kannst|bitte|nein|ja|"
                 r"danke|ok|okay|brauche|brauch|soll|sollte|kann|ist|sind|wird|habe|hab|bin|mach|"
                 r"gib|zeig|sag|erzaehl|weiss|hilfe|hallo)\b|\d", kern):
        return False
    if absicht(kern) or KEIN_ORT.search(kern) or kern in NICHT_ORT:
        return False
    return bool(re.fullmatch(r"(?:in\s+|fuer\s+|nach\s+|bei\s+)?[a-z][a-z .\-]{1,38}", kern))


def mit_ort(art: str, ort: str, kern: str, holen: Holen, heute: date) -> str:
    """Antwortet auf eine Frage, die einen Ort braucht."""
    daten = wetterdaten(ort, holen, heute)
    if isinstance(daten, str):
        return daten
    tage = tage_aus(kern, heute)
    if art == "anziehen":
        return anziehen_text(daten, tage[0])
    if art == "schirm":
        return schirm_text(daten, tage[0])
    if art == "sonne":
        return sonne_text(daten, tage[0])
    return wetter_text(daten, tage, kern)


def ort_fragen(art: str) -> str:
    vorn = {"anziehen": "Gern helfe ich dir beim Anziehen! ",
            "schirm": "Das schaue ich gern nach! ",
            "sonne": "Gute Frage! "}.get(art, "")
    return vorn + ORT_FRAGE + ORT_BEISPIEL


# -- Zusammen -----------------------------------------------------------------------------------

FEHLER_TEXT = ("Da ist bei mir gerade etwas schiefgegangen. Frag mich gern noch einmal, "
              "vielleicht etwas anders formuliert.")


def antwort(frage: str, verlauf: list[dict[str, Any]] | None = None, *, secure: bool = False,
            holen: Holen | None = None, jetzt: datetime | None = None,
            wuerfel: random.Random | None = None, wohnort: str = "",
            gemerkt: list[str] | None = None) -> str:
    """Die Antwort von Aquaticy Standard -- nie leer und nie eine Ausnahme (16.1.6).

    Ein Fehler in einer einzelnen Antwort (etwa ein Dienst, der anders antwortet als erwartet)
    brach vorher den ganzen Zug ab. Jetzt gibt es eine freundliche Meldung; der Fehler steht im
    Protokoll.
    """
    # Nur Eintraege, die wie Nachrichten aussehen -- ein kaputter Verlauf bricht sonst ab.
    verlauf = [e for e in verlauf or [] if isinstance(e, dict)]
    # Einzelne Surrogate (etwa aus der Kommandozeile) brachen die Ortssuche ab (16.4.5).
    frage = re.sub("[\ud800-\udfff]", "\ufffd", str(frage or ""))
    try:
        return _antwort(frage, verlauf, secure=secure, holen=holen, jetzt=jetzt,
                        wuerfel=wuerfel, wohnort=wohnort, gemerkt=gemerkt)
    except Exception as fehler:
        print(f"  [Aquaticy Standard] {type(fehler).__name__} bei einer Antwort", flush=True)
        return FEHLER_TEXT


def _antwort(frage: str, verlauf: list[dict[str, Any]] | None = None, *, secure: bool = False,
             holen: Holen | None = None, jetzt: datetime | None = None,
             wuerfel: random.Random | None = None, wohnort: str = "",
             gemerkt: list[str] | None = None) -> str:
    """Die Antwort von Aquaticy Standard -- nie leer.

    Args:
        verlauf: das bisherige Gespraech. Daraus kennt Aquaticy Standard den zuletzt genannten
            Ort und eine offene Rueckfrage ("Fuer welchen Ort?" -> "Erkelenz").
        wohnort: aus dem Gedaechtnis oder den Einstellungen -- fuer Fragen ohne Ort.
        gemerkt: was sich Aquaticy in diesem Zug gerade gemerkt hat.
    """
    from aquaticy import zeit as zeit_mod

    holen = holen or holen_json
    verlauf = verlauf or []
    rnd = wuerfel or random.SystemRandom()
    frage = str(frage or "").strip()[:2000]
    kern = falten(frage)
    jetzt = jetzt or zeit_mod.jetzt()
    heute = jetzt.date()
    if not kern:
        return ("Frag mich ruhig etwas – zum Beispiel nach dem Wetter, einer Rechnung oder dem "
                "Datum.")
    hilfe = krise(frage)
    if hilfe:
        return hilfe
    # 16.3.0: Ein Gruss oder Dank vorne aendert die Frage nicht.
    ohne_vorspann = FUELL_VORN.sub("", VORSPANN.sub("", frage, count=1), count=1).strip()
    if ohne_vorspann and ohne_vorspann != frage and falten(ohne_vorspann):
        frage, kern = ohne_vorspann, falten(ohne_vorspann)
    if secure:
        text = sicherheit(frage)
        if text:
            return text + KEY_HINT
        return ("Dazu habe ich ohne Sprachmodell leider kein festes Sicherheitswissen. Frag mich "
                "nach einem Port (z. B. „Port 3389“), einem Dienst oder einer Malware." + KEY_HINT)
    # 16.4.2: Andere Sprachen -- erkannt an typischen Woertern und an der Schrift. Worte einer
    # Krise zuerst, in jeder Sprache derselben Schrift: Hilfe haengt nie an der Erkennung.
    hilfe_sprache = welt_krise(frage)
    if hilfe_sprache:
        return hilfe_sprache
    sprache = welt_sprache(frage, verlauf)
    if sprache and sprache != "de":
        text = welt_antwort(frage, sprache, holen, jetzt, wohnort, verlauf)
        if text:
            return text
    if sprache == "en":
        # 16.4.5: "What is 1,000 + 1?" ergab vorher 2 -- das Komma ist im Englischen ein
        # Tausendertrenner, der Punkt das Dezimalzeichen.
        frage = englische_zahlen(frage)
        kern = falten(frage)
        text = englisch_kram(kern, heute)
        if text:
            return text

    # 1. Antwort auf die eigene Rueckfrage: "Fuer welchen Ort?" -> "Erkelenz"
    vorher_gefragt = offene_ortsfrage(verlauf)
    if vorher_gefragt:
        vorher_kern = falten(vorher_gefragt)
        art = absicht(vorher_kern) or "wetter"
        if KEIN_ORT.search(kern):
            return ("Kein Problem. Wenn du magst, nenn mir später einfach einen Ort. Oder sag mir, "
                    "wo du wohnst – dann merke ich es mir und frage nicht mehr.")
        if DAHEIM.fullmatch(kern) or kern in ("bei mir zu hause", "wo ich wohne", "wo ich bin"):
            if str(wohnort or "").strip():
                return mit_ort(art, str(wohnort).strip(), vorher_kern, holen, heute)
            return ("Ich weiß leider nicht, wo du gerade bist. " + ORT_FRAGE + ORT_BEISPIEL)
        if sieht_aus_wie_ort(frage):
            ort = re.sub(r"^(?:in|für|fuer|nach|bei)\s+", "", frage.strip(" ?!.,"), flags=re.I)
            return mit_ort(art, ort, vorher_kern, holen, heute)

    for teil in (lambda: passwort(frage), lambda: gespraech(frage, rnd),
                 lambda: textkram(frage), lambda: zahlenkram(frage, heute),
                 lambda: zufall(frage, wuerfel), lambda: feiertag(frage, heute),
                 lambda: anlass(frage, heute),
                 lambda: mond(frage, heute), lambda: alter(frage, heute)):
        text = teil()
        if text:
            return text
    text = uhrzeit_wenn(frage, kern, holen, jetzt) or zeit_zwischen(frage, kern, holen, jetzt)
    if text:
        return text
    treffer = UHRZEIT_IN.search(kern) or ZEITVERSCHIEBUNG.search(kern)
    if treffer:
        ort = re.sub(r"\s+", " ", re.sub(r"\b(gerade|jetzt|aktuell|denn|eigentlich)\b", " ",
                                         next(g for g in treffer.groups() if g))).strip(" .-")
        # 16.4.5: "in der Türkei" suchte "der Türkei", "in Tokio und in London" einen Ort
        # "Tokio und in London".
        orte_zeit = [re.sub(r"^(?:in|auf)\s+", "", o_).strip()
                     for o_ in re.split(r"\s+(?:und|sowie|oder)\s+|\s*,\s*", ort)]
        orte_zeit = [re.sub(r"^(?:der|die|den|dem|das)\s+", "", o_) for o_ in orte_zeit if o_]
        orte_zeit = [o_ for o_ in orte_zeit if o_ and o_ not in NICHT_ORT][:3]
        if orte_zeit:
            return "\n\n".join(uhrzeit_in(original(frage, o_), holen, jetzt)
                               for o_ in orte_zeit)
    if re.search(r"\b(?:wie\s*spaet|uhrzeit|wie\s*viel\s+uhr)\b", kern) and re.search(
            r"\b(?:dort|da|drueben)\b", kern):
        # 16.4.5: "Wie spät ist es dort?" nach "Wie spät ist es in Tokio?" nannte die Zeit von
        # hier.
        dort_ort = letzter_ort(verlauf)
        if dort_ort:
            return uhrzeit_in(dort_ort, holen, jetzt)
    for teil in (lambda: zeit(frage, jetzt), lambda: trinkgeld(frage),
                 lambda: bmi(frage, sprache == "en"), lambda: prozente(frage)):
        text = teil()
        if text:
            return text
    for teil in (lambda: einheiten(frage), lambda: rechnen(frage)):
        text = teil()
        if text:
            # "Convert 10 miles to km" bekam vorher "10 Miles sind **16,0934 km**".
            englisch_gefragt = sprache == "en" or re.search(r"\b(?:to|into)\b|\bhow\s+many\b", kern)
            # 16.4.5: "1 km2 ist 100 Hektar" -- falten() macht aus "km²" ein "km2".
            text = re.sub(r"\b(k?m|cm|mm|dm)([23])\b",
                          lambda t: t.group(1) + {"2": "²", "3": "³"}[t.group(2)], text)
            return _englisch(text) if englisch_gefragt else text
    if re.search(r"\b(nachrichten|news|schlagzeilen|neuigkeiten|tagesschau|"
                 r"was\s+gibt\s+es\s+neues)\b|\bwas\s+ist\s+heute\s+(?:in\s+der\s+welt\s+)?"
                 r"passiert\b|\bwas\s+ist\s+(?:heute\s+)?in\s+der\s+welt\s+passiert\b|"
                 r"\bwas\s+passiert\s+(?:gerade\s+)?in\s+der\s+welt\b", kern):
        return nachrichten(holen)
    if re.search(r"\b(kurs|wechselkurs|umrechnen)\b|\bwie\s+steht\s+(?:der|die|das)\b|"
                 r"\b(?:bekomme|kriege)\s+(?:ich|man)\s+fuer\b|\bsind\s+wie\s*viele?\b|"
                 r"\bwie\s*viele?\s+[a-z€$]+\s+(?:sind|ist|macht|machen)\s+\d",
                 kern) or WAEHRUNG_SATZ.search(kern):
        text = waehrung(frage, holen)
        if text and sprache == "en":
            # 16.4.5: "What's 50 euros in dollars?" bekam vorher "50 EUR sind ..., Kurs, Stand".
            text = _englisch(text.replace("Die Wechselkurse lassen sich gerade nicht abrufen.",
                                          "The exchange rates can't be loaded right now.")
                             .replace("(Kurs ", "(rate ").replace(", Stand ", ", as of ")
                             .replace("Quelle: Europäische Zentralbank über ",
                                      "Source: European Central Bank via "))
        if text:
            return text

    # 2. Folgefragen: "und morgen?", "und in Köln?", "und am Wochenende?"
    # 16.4.5: auch Tag und Ort zusammen ("und übermorgen in Bonn?") -- vorher "kann ich nicht".
    tagwoerter = (r"heute|morgen|uebermorgen|am\s+wochenende|die\s+naechsten\s+tage|"
                  r"diese\s+woche|naechste\s+woche|am\s+\w+")
    folge = re.fullmatch(rf"(?:und\s+)?(?:wie\s+(?:wird|ist)\s+es\s+)?({tagwoerter})"
                         r"(?:\s+(?:in|fuer)\s+(.+))?|und\s+(?:in|fuer)\s+(.+?)"
                         r"(?:\s+(heute|morgen|uebermorgen|naechste\s+woche|am\s+(?:wochenende|"
                         r"montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)))?", kern)
    folge_tag = (folge.group(1) or folge.group(4)) if folge else None
    folge_ort = (folge.group(2) or folge.group(3)) if folge else None
    letzter = letzter_ort(verlauf)
    daheim = str(wohnort or "").strip()
    vorher = letzte_wetterfrage(verlauf)
    if folge and vorher and (folge_ort or letzter or daheim):
        ort = original(frage, folge_ort) if folge_ort else (letzter or daheim)
        tagwort = ("heute", "morgen", "uebermorgen")[vorher[1]]
        return mit_ort("wetter", ort, folge_tag or tagwort, holen, heute)

    # 3. Alles, was einen Ort braucht: Wetter, Anziehen, Schirm, Sonne
    art = absicht(kern)
    if art and definitionsfrage(frage, kern):
        art = ""
    if art and (re.match(r"(?:warum|wieso|weshalb|wie\s+entsteh\w*|woraus\s+besteh\w*)\b", kern)
                or re.match(r"ist\s+\w+\s+(?:gut|schlecht|gesund|ungesund|gefaehrlich|"
                            r"schaedlich|wichtig)\s+fuer\b", kern)) and not re.search(
                                r"\b(heute|morgen|uebermorgen|wochenende|jetzt|gerade)\b", kern):
        # 16.4.5: allgemeine Fragen, keine Vorhersage ("Ist Regen gut für Pflanzen?").
        art = ""
    if art:
        orte = orte_aus(frage)
        if len(orte) > 1 and art == "wetter":
            return wetter_mehrere(orte, kern, holen, heute)
        ort = (orte[0] if orte else "") or (
            (daheim or letzter) if DAHEIM.search(kern) else (letzter or daheim))
        if not ort:
            return ort_fragen(art)
        return mit_ort(art, ort, kern, holen, heute)

    if gemerkt:
        return ("Alles klar, das merke ich mir:\n" + "\n".join(f"- {g}" for g in gemerkt[:5])
                + "\n\nIch nutze das später, zum Beispiel beim Wetter.")
    englisch = welt_texte("en") if sprache == "en" else {}
    thema = thema_aus(frage)
    if thema:
        text = wissen(thema, holen, "en" if englisch else "de")
        if text:
            return text
        if englisch:
            return englisch["nichts"].format(x=thema) + KEY_HINT_EN
        return (f"Zu „{thema}“ finde ich auf Wikipedia leider nichts Passendes. Vielleicht hilft "
                "eine andere Schreibweise?" + KEY_HINT)
    if englisch:
        return englisch["rueckfall"] + KEY_HINT_EN
    return (waehle(("Hm, das kann ich ohne Sprachmodell leider nicht beantworten.",
                    "Das übersteigt leider, was ich ohne Sprachmodell kann.",
                    "Da muss ich passen – dafür bräuchte ich ein Sprachmodell."), kern)
            + " Aber frag mich gern nach dem Wetter (auch was du anziehen sollst), einer Rechnung,"
            " dem Datum, Feiertagen, Wechselkursen, Nachrichten oder Wissen aus Wikipedia. "
            "„Was kannst du?“ zeigt dir alles." + KEY_HINT)


#: Gruss oder Dank am Anfang, mit Satzzeichen dahinter.
VORSPANN = re.compile(r"^\s*(?:hallo|hi|hey|moin|servus|guten\s+(?:morgen|tag|abend)|"
                      r"danke(?:\s+(?:dir|schoen|schön))?|vielen\s+dank|ok(?:ay)?|super|prima|"
                      r"bitte|sag\s+mal|also)(?:\s+aquaticy)?"
                      r"\s*[,!.;:]+\s*(?:und\s+)?", re.IGNORECASE)
#: 16.4.5: "Und was ist 9 durch 3?", "Ok und was ist 2 hoch 8?", "Hey Aquaticy, was ist 2+2?"
#: -- vorher kam "kann ich nicht".
FUELL_VORN = re.compile(r"^\s*(?:(?:und|ok(?:ay)?|also|bitte|sag\s+mal)[,!]?\s+)+"
                        r"(?=(?:was|wie|wann|wer|wo|welche\w*|rechne|berechne)\b)", re.IGNORECASE)


# -- Andere Sprachen (16.4.2) --------------------------------------------------------------------

MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _en_datum(kern: str, heute: date) -> date | None:
    """'July 4, 1776', '4 July 1776', '2026-12-24', 'December 24'."""
    monate = "|".join(MONTHS)
    for muster, reihe in ((r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", "jmt"),
                          (rf"\b({monate})\s+(\d{{1,2}})(?!\d)(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?",
                           "mtj"),
                          (rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({monate})(?:,?\s+(\d{{4}}))?",
                           "tmj")):
        treffer = re.search(muster, kern)
        if not treffer:
            continue
        teile = dict(zip(reihe, treffer.groups(), strict=True))
        monat = teile["m"]
        nummer = MONTHS.index(monat) + 1 if monat in MONTHS else int(monat)
        try:
            return date(int(teile["j"] or heute.year), nummer, int(teile["t"]))
        except ValueError:
            return None
    return None


def englisch_kram(kern: str, heute: date) -> str:
    """16.4.5: Englische Fragen zu Datum und Zahlen -- vorher kam "Sorry, I can't answer that".

    Die deutsche Kette erkennt diese Saetze nicht, und ihre Antworten waeren deutsch.
    """
    if re.fullmatch(r"(?:what|which)\s+year\s+is\s+it(?:\s+(?:now|today))?", kern):
        return f"It is **{heute.year}**."
    # 16.5.7: "What day is tomorrow?", "What day was yesterday?", "What day of the week is it?",
    # "What is tomorrow's date?" -- vorher "Sorry"; "Welcher Tag ist morgen?" ging.
    wann_ = (r"(today|tomorrow|yesterday|the\s+day\s+after\s+tomorrow|"
             r"the\s+day\s+before\s+yesterday)")
    relativ = (re.fullmatch(r"(?:what|which)\s+(?:day|date)(\s+of\s+the\s+week)?\s+"
                            r"(?:is|was|will\s+be)(?:\s+it)?(?:\s+" + wann_ + r")?(?:\s+now)?",
                            kern)
               or re.fullmatch(r"what(?:\s+is|'s|s)?()\s+" + wann_ + r"(?:'s|s)?\s+date", kern))
    if relativ and (relativ.group(1) or relativ.group(2)):
        wort = re.sub(r"\s+", " ", relativ.group(2) or "today")
        versatz = {"today": 0, "tomorrow": 1, "yesterday": -1, "the day after tomorrow": 2,
                   "the day before yesterday": -2}[wort]
        tag = date.fromordinal(heute.toordinal() + versatz)
        verb = "was" if versatz < 0 else "is"
        return (f"{wort[:1].upper()}{wort[1:]} {verb} **{WEEKDAYS[tag.weekday()]}, {tag.day} "
                f"{MONTHS[tag.month - 1].title()} {tag.year}**.")
    # 16.5.7: "How many days in 2028?" -- "Wie viele Tage hat 2028?" ging schon.
    jahres_frage = re.fullmatch(r"how\s+many\s+days\s+(?:are\s+(?:there\s+)?in\s+|in\s+|does\s+)"
                         r"(?:the\s+year\s+)?(\d{4})(?:\s+have)?", kern)
    if jahres_frage and 1 <= int(jahres_frage.group(1)) <= 9999:
        jahr = int(jahres_frage.group(1))
        return f"{jahr} has **{366 if calendar.isleap(jahr) else 365} days**."
    # 16.4.5: "What week number is it?" und "What's the week number?" verfehlten das Muster.
    if re.fullmatch(r"(?:what|which)\s+(?:calendar\s+)?week(?:\s+number)?\s+(?:is\s+it|are\s+we"
                    r"\s+in)(?:\s+(?:now|today))?|(?:what(?:\s+is|'s|s)?\s+the\s+)?(?:current\s+)?"
                    r"week\s+number(?:\s+(?:now|today))?", kern):
        return f"It is **week {heute.isocalendar()[1]}**."
    ziele = {"christmas eve": (12, 24), "christmas": (12, 25), "new year's eve": (12, 31),
             "new years eve": (12, 31), "new year": (1, 1), "new year's": (1, 1),
             "new years": (1, 1), "halloween": (10, 31), "valentine's day": (2, 14),
             "valentines day": (2, 14)}
    namen_ = "|".join(sorted(ziele, key=len, reverse=True))
    anlass_ = re.search(r"\bwhat\s+day\s+(?:of\s+the\s+week\s+)?(?:is|will\s+be|falls)\s+"
                        r"(?:on\s+)?(" + namen_ + r")(?:\s+(?:in\s+)?(\d{4}))?\b", kern)
    if anlass_:
        # 16.4.5: "What day of the week is Christmas?" -- vorher "Sorry".
        monat, tag_nr = ziele[anlass_.group(1)]
        jahr_ = int(anlass_.group(2) or heute.year)
        ziel = date(jahr_, monat, tag_nr)
        if not anlass_.group(2) and ziel < heute:
            ziel = date(heute.year + 1, monat, tag_nr)
        name = anlass_.group(1).title().replace("'S", "'s")
        zeitform = "was" if ziel < heute else "is"
        return (f"{name} {ziel.year} ({MONTHS[ziel.month - 1].title()} {ziel.day}) {zeitform} a "
                f"**{WEEKDAYS[ziel.weekday()]}**.")
    treffer = re.search(r"\bhow\s+(?:many\s+(days|weeks)|long)\s+(?:is\s+it\s+|are\s+there\s+|"
                        r"are\s+left\s+)?(?:until|till|til|to|before)\s+(" + namen_ + r")\b",
                        kern)
    if treffer:
        monat, tag_nr = ziele[treffer.group(2)]
        ziel = date(heute.year, monat, tag_nr)
        if ziel < heute:
            ziel = date(heute.year + 1, monat, tag_nr)
        tage = (ziel - heute).days
        name = treffer.group(2).title().replace("'S", "'s")
        if tage == 0:
            return f"{name} is today!"
        if treffer.group(1) == "weeks" and tage >= 7:
            # 16.4.5: "How many weeks until New Year?" -- vorher "Sorry".
            wochen, rest = divmod(tage, 7)
            mehr = f" and {rest} day{'s' * (rest != 1)}" if rest else ""
            return (f"There are **{wochen} week{'s' * (wochen != 1)}{mehr}** until {name} "
                    f"({ziel.isoformat()}).")
        return f"There {'is' if tage == 1 else 'are'} **{tage:,} day{'s' * (tage != 1)}** until " \
               f"{name} ({ziel.isoformat()})."
    if re.fullmatch(r"(?:please\s+)?(?:roll|throw)\s+(?:a|one|the)\s+(?:dice|die)(?:\s+for\s+me)?|"
                    r"(?:please\s+)?(?:flip|toss)\s+a\s+coin(?:\s+for\s+me)?", kern):
        # 16.4.5: "Roll a dice", "Flip a coin" -- auf Deutsch ging es, auf Englisch "Sorry".
        rnd = random.SystemRandom()
        if "coin" in kern:
            return f"🪙 **{rnd.choice(('Heads', 'Tails'))}**"
        return f"🎲 Rolled: **{rnd.randint(1, 6)}**"
    treffer = re.search(r"\bwhen\s+is\s+mother'?s\s+day(?:\s+(?:in\s+)?(\d{4}))?\b", kern)
    if treffer:
        # 16.4.5: Muttertag (zweiter Sonntag im Mai, in Deutschland und den USA) -- vorher "Sorry".
        jahr_ = int(treffer.group(1) or heute.year)
        erster = date(jahr_, 5, 1)
        tag_ = erster.replace(day=1 + (6 - erster.weekday()) % 7 + 7)
        if not treffer.group(1) and tag_ < heute:
            erster = date(jahr_ + 1, 5, 1)
            tag_ = erster.replace(day=1 + (6 - erster.weekday()) % 7 + 7)
        return (f"Mother's Day (Germany and the US) is on **Sunday, {MONTHS[4].title()} "
                f"{tag_.day}, {tag_.year}**.")
    treffer = re.search(r"\bwhen\s+is\s+easter(?:\s+sunday)?(?:\s+(?:in\s+)?(\d{4}))?\b", kern)
    if treffer:
        jahr = int(treffer.group(1) or heute.year)
        ostertag = ostern(jahr)
        if not treffer.group(1) and ostertag < heute:
            ostertag = ostern(jahr + 1)
        return (f"Easter Sunday is on **{ostertag.isoformat()}** "
                f"({MONTHS[ostertag.month - 1].title()} {ostertag.day}).")
    treffer = re.search(r"\bis\s+(\d{1,4})\s+a\s+leap\s+year\b", kern)
    if treffer:
        jahr = int(treffer.group(1))
        if calendar.isleap(jahr):
            return f"Yes, **{jahr}** is a leap year (366 days)."
        return f"No, {jahr} is not a leap year (365 days)."
    treffer = re.search(r"\bis\s+(-?\d{1,12})\s+(?:a\s+)?prime(?:\s+number)?\b", kern)
    if treffer:
        n = int(treffer.group(1))
        if n < 2:
            return f"No, {n} is not a prime number. Prime numbers start at 2."
        teiler = next((t for t in range(2, int(n ** 0.5) + 1) if n % t == 0), 0)
        if teiler:
            return (f"No, {n:,} is not a prime number: it can be divided by {teiler:,} "
                    f"({teiler:,} × {n // teiler:,}).")
        return f"Yes, **{n:,}** is a prime number."
    treffer = re.search(r"\b(\d{1,4})\s+factorial\b|\bfactorial\s+of\s+(\d{1,4})\b", kern)
    if treffer:
        n = int(treffer.group(1) or treffer.group(2))
        if n > 100:
            return "That gets too big – I calculate factorials up to 100."
        return f"{n}! = **{math.factorial(n):,}**"
    treffer = re.search(r"\b(average|mean|sum)\s+of\s+(-?\d+(?:\.\d+)?(?:(?:\s*,\s*|\s+and\s+|"
                        r"\s*,\s*and\s+|\s+)-?\d+(?:\.\d+)?)+)", kern)
    if treffer:
        werte_ = [float(w) for w in re.findall(r"-?\d+(?:\.\d+)?", treffer.group(2))]
        ergebnis = sum(werte_) if treffer.group(1) == "sum" else sum(werte_) / len(werte_)
        art = "sum" if treffer.group(1) == "sum" else "average"
        return _englisch(f"The {art} of {len(werte_)} numbers is **{schoen(ergebnis, 4)}**.")
    # 16.4.5: auch "How many days are in February 2028?" (vorher nur "are there in")
    treffer = re.search(r"\bhow\s+many\s+days\s+(?:are\s+(?:there\s+)?|does\s+|is\s+)?(?:in\s+)?(" +
                        "|".join(MONTHS) + r")(?:\s+(\d{4}))?(?:\s+have)?\b", kern)
    if treffer:
        jahr = int(treffer.group(2) or heute.year)
        nummer = MONTHS.index(treffer.group(1)) + 1
        tage = calendar.monthrange(jahr, nummer)[1]
        return f"{treffer.group(1).title()} {jahr} has **{tage} days**."
    teil = re.search(r"\b(half|a\s+third|one\s+third|a\s+quarter|one\s+quarter|quarter)\s+of\s+"
                     r"(-?\d+(?:\.\d+)?)\b", kern)
    if teil:
        name = re.sub(r"\s+", " ", teil.group(1))
        anteil = {"half": 2, "a third": 3, "one third": 3}.get(name, 4)
        wert = float(teil.group(2)) / anteil
        return _englisch(f"{name.capitalize()} of {teil.group(2)} is **{schoen(wert, 4)}**.")
    trinkgeld_en = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:%|percent)\s+tip\s+(?:on|for)\s+\$?"
                             r"(\d+(?:\.\d+)?)", kern)
    if trinkgeld_en:
        satz, betrag = float(trinkgeld_en.group(1)), float(trinkgeld_en.group(2))
        tip = betrag * satz / 100
        return _englisch(f"A {schoen(satz)} % tip on {schoen(betrag, 2)} is **{schoen(tip, 2)}** "
                         f"– {schoen(betrag + tip, 2)} in total.")
    if re.search(r"\bhow\s+many\s+days\s+(?:are\s+there\s+)?in\s+a\s+year\b", kern):
        return ("A year has **365 days** – a leap year has 366. "
                f"{heute.year} has {366 if calendar.isleap(heute.year) else 365}.")
    if re.search(r"\bwhat\s+day\s+(?:of\s+the\s+week\s+)?(?:was|is|will)\b", kern):
        gesucht = _en_datum(kern, heute)
        if gesucht:
            zeitform = "was" if gesucht < heute else "is" if gesucht == heute else "will be"
            return (f"{MONTHS[gesucht.month - 1].title()} {gesucht.day}, {gesucht.year} "
                    f"{zeitform} a **{WEEKDAYS[gesucht.weekday()]}**.")
    treffer = re.search(r"\bhow\s+old\s+am\s+i\b.*\bborn\s+in\s+(\d{4})\b|"
                        r"\bborn\s+in\s+(\d{4})\b.*\bhow\s+old\b", kern)
    if treffer:
        jahr = int(treffer.group(1) or treffer.group(2))
        if jahr > heute.year:
            return f"{jahr} is still in the future."
        return (f"If you were born in {jahr}, you turn **{heute.year - jahr}** this year (or "
                "already have, depending on your birthday).")
    return ""


def englische_zahlen(text: str) -> str:
    """'1,000,000' -> '1000000', '1,234.5' -> '1234.5' -- nur Gruppen mit drei Ziffern."""
    return re.sub(r"(?<![\d.,])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d,])",
                  lambda t: t.group(0).replace(",", ""), text)


def welt_texte(code: str) -> dict[str, str]:
    from aquaticy import weltsprachen

    sprache = weltsprachen.SPRACHEN.get(code)
    return dict(sprache.antworten) if sprache is not None else {}


def _letzte_antwort(verlauf: list[dict[str, Any]] | None) -> str:
    for eintrag in reversed(verlauf or []):
        if isinstance(eintrag, dict) and eintrag.get("role") == "assistant":
            return str(eintrag.get("content") or "").strip()
    return ""


def welt_sprache(frage: str, verlauf: list[dict[str, Any]] | None = None) -> str:
    """Die Sprache der Frage -- nach "Für welchen Ort?" in einer Sprache auch die Antwort darauf."""
    from aquaticy import weltsprachen

    letzte = _letzte_antwort(verlauf)
    if letzte and len(frage.split()) <= 5:
        for sprache in weltsprachen.SPRACHEN.values():
            if sprache.antworten.get("ort") and letzte == sprache.antworten["ort"]:
                gefunden = weltsprachen.sprache_von(frage)
                return gefunden if gefunden not in ("", "de") else sprache.code
    return weltsprachen.sprache_von(frage)


#: Diese Sprachen kennen wir gut. Bei den anderen steht unter der Hilfe auch der englische Satz --
#: falls eine Uebersetzung holpert, kommt die Hilfe trotzdem an.
_KRISE_SICHER = "en es fr pt it ru zh ja ko ar hi tr pl nl id vi uk fa ro el cs sv da no fi hu he"
_KRISE_SICHER += " th"
KRISE_SICHER = frozenset(_KRISE_SICHER.split())


def welt_krise(frage: str) -> str:
    """Hilfe in der Sprache, in der jemand von einer Krise schreibt -- oder ""."""
    from aquaticy import weltsprachen

    code = weltsprachen.krise_sprache(frage)
    if not code or code in ("de", "en"):
        return ""
    text = weltsprachen.SPRACHEN[code].antworten["krise"]
    if code not in KRISE_SICHER:
        text += "\n\n" + weltsprachen.SPRACHEN["en"].antworten["krise"]
    return text


def welt_uhrzeit(ort: str, code: str, holen: Holen, jetzt: datetime) -> str:
    """Die Uhrzeit an einem Ort ("¿Qué hora es en Tokio?") -- ueber die Zeitzone des Orts."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    from aquaticy import weltsprachen

    a = weltsprachen.SPRACHEN[code].antworten
    geo = holen("https://geocoding-api.open-meteo.com/v1/search?count=1&language=en&name="
                + quote(ort))
    treffer = (geo.get("results") or [None])[0] if isinstance(geo, dict) else None
    if not isinstance(treffer, dict):
        return a["nichts"].format(x=ort)
    zone = str(treffer.get("timezone") or "")
    try:
        dort = jetzt.astimezone(ZoneInfo(zone)) if zone else None
    except (ZoneInfoNotFoundError, ValueError):
        dort = None
    if dort is None:
        return a["nichts"].format(x=ort)
    return a["zeit"].format(zeit=f"{dort:%H:%M} ({treffer.get('name') or ort})")


#: 16.4.5: "uebermorgen" in Sprachen, deren Wort sicher ist. Vorher landete "pasado mañana",
#: "après-demain" oder "послезавтра" im Ortsnamen, und gezeigt wurde heute oder morgen.
UEBERMORGEN = {
    "en": ("the day after tomorrow", "day after tomorrow"), "es": ("pasado mañana",),
    "fr": ("après-demain", "apres-demain"), "it": ("dopodomani",), "pt": ("depois de amanhã",),
    "nl": ("overmorgen",), "pl": ("pojutrze",), "ru": ("послезавтра",), "uk": ("післязавтра",),
    "cs": ("pozítří",), "sv": ("i övermorgon", "övermorgon"), "da": ("i overmorgen", "overmorgen"),
    "no": ("i overmorgen", "overmorgen"), "tr": ("yarından sonra",), "hu": ("holnapután",),
    "ro": ("poimâine",), "el": ("μεθαύριο",), "fi": ("ylihuomenna",),
}


#: Wochentage (Montag bis Sonntag) in Sprachen, deren Namen sicher sind (16.4.5).
WOCHENTAGE_WELT = {
    "en": ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"),
    "es": ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
    "fr": ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"),
    "it": ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"),
    "pt": ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira",
           "sábado", "domingo"),
    "nl": ("maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"),
    "sv": ("måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"),
    "da": ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"),
    "no": ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"),
    "pl": ("poniedziałek", "wtorek", "środę", "czwartek", "piątek", "sobotę", "niedzielę"),
    "ru": ("понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"),
    "cs": ("pondělí", "úterý", "středu", "čtvrtek", "pátek", "sobotu", "neděli"),
}
#: Die Woerter davor, die mit dem Tag zusammen weg muessen ("el sábado", "on Saturday").
TAG_VORN = r"(?:(?:el|le|il|o|on|op|på|w|в|ve|v)\s+)?"


def wochentag_in(frage: str, code: str, heute: date) -> tuple[int, str, str]:
    """(Tag ab heute, Wort, Frage ohne den Tag) -- oder (-1, "", Frage)."""
    for nummer, wort in enumerate(WOCHENTAGE_WELT.get(code, ())):
        # Englisch nur mit "on/this/next" davor: "Sunday Island" ist ein Ort.
        vorn = r"(?:on|this|next)\s+" if code == "en" else TAG_VORN
        treffer = re.search(rf"(?<![\w-]){vorn}{re.escape(wort)}(?!\w)", frage, re.IGNORECASE)
        if treffer:
            rest = (frage[:treffer.start()] + " " + frage[treffer.end():]).strip()
            return (nummer - heute.weekday()) % 7, wort, rest
    return -1, "", frage


def uebermorgen_in(frage: str, code: str) -> tuple[str, str]:
    """(gefundenes Wort, Frage ohne dieses Wort) -- oder ("", Frage)."""
    for wort in UEBERMORGEN.get(code, ()):
        treffer = re.search(rf"(?<!\w){re.escape(wort)}(?!\w)", frage, re.IGNORECASE)
        if treffer:
            return treffer.group(0), (frage[:treffer.start()] + " " + frage[treffer.end():]).strip()
    return "", frage


def welt_wetter(ort: str, code: str, frage: str, holen: Holen, heute: date) -> str:
    """Das Wetter fuer *ort* -- mit Zahlen und Zeichen, die jede Sprache lesen kann."""
    from aquaticy import weltsprachen

    sprache = weltsprachen.SPRACHEN[code]
    daten: dict[str, Any] | str = wetterdaten(ort, holen, heute)
    # Gebeugte Formen ("в Москве", "Helsingissä") und Vorsilben ("בתל אביב"): noch einmal mit
    # kuerzerem Namen versuchen.
    versuche = [ort[:-1], ort[:-2]] if len(ort) >= 6 else []
    versuche += [ort[len(v):] for v in sprache.listen["vorsilben"]
                 if ort.startswith(v) and len(ort) - len(v) >= 3]
    for anders in versuche:
        if isinstance(daten, dict) or daten == NICHT_ERREICHBAR:
            break
        daten = wetterdaten(anders, holen, heute)
    if not isinstance(daten, dict) or not daten.get("tage"):
        return sprache.antworten["nichts"].format(x=ort)
    ueber, _ = uebermorgen_in(frage, code)
    wochentag, tagname, _ = wochentag_in(frage, code, heute)
    wort: tuple[str, ...]
    if ueber and len(daten["tage"]) > 2:
        tag, wort = 2, (ueber.lower(),)
    elif 0 <= wochentag < len(daten["tage"]):
        tag, wort = wochentag, (tagname,)
    else:
        tag = 1 if weltsprachen.enthaelt(frage, sprache, "morgen") and len(daten["tage"]) > 1 else 0
        wort = sprache.listen["morgen" if tag else "heute"][:1] or ("",)
    t = daten["tage"][tag]
    zeichen = WETTERCODES.get(t.get("code"), "").split(" ")[-1]
    regen = "" if t.get("regen") is None else f" · ☔ {_grad(t['regen'])} %"
    return (f"**{daten['name']}** · {wort[0]}: {zeichen} {_grad(t.get('tief'))} – "
            f"{_grad(t.get('hoch'))} °C{regen}\n\n[Open-Meteo](https://open-meteo.com)")


def welt_antwort(frage: str, code: str, holen: Holen, jetzt: datetime, wohnort: str = "",
                 verlauf: list[dict[str, Any]] | None = None) -> str:
    """Die Antwort in einer anderen Sprache -- oder "" (Englisch: dann der deutsche Weg)."""
    from aquaticy import weltsprachen

    sprache = weltsprachen.SPRACHEN.get(code)
    if sprache is None or not sprache.antworten:
        return ""
    a = sprache.antworten
    # Reihenfolge = Vorrang bei gleich langen Wendungen; sonst gewinnt die laengste:
    # "субҳ ба хайр" (guten Morgen) ist ein Gruss, auch wenn "хайр" allein Tschuess heisst.
    plaudern = ("wiegehts", "info", "danke", "tschuess", "hallo")
    gefaltet = weltsprachen.norm(frage)
    if weltsprachen.nur_aus(frage, sprache, plaudern):
        gefunden = weltsprachen.treffer(gefaltet, sprache, plaudern)
        if gefunden:
            liste = gefunden[0][0]
            return a["intro" if liste in ("info", "hallo") else liste]
    # Ungarisch "idő", Lettisch "laiks", Serbisch "време" heissen Wetter und Zeit: Steht das
    # Wort nur in einer Zeit-Frage ("mennyi az idő"), ist es eine Zeit-Frage.
    arten = {liste for liste, _ in weltsprachen.treffer(gefaltet, sprache,
                                                         ("wetter", "zeit", "datum"))}
    wetter = "wetter" in arten
    if "zeit" in arten and not wetter:
        ort = weltsprachen.ort_aus(frage, sprache, ("zeit",))
        # 16.4.5: Ein Rest der Zeit-Frage ist kein Ort ("지금 몇 시야" suchte die Uhrzeit in "야").
        ort = " ".join(w for w in ort.split() if len(w) > 2 or not any(
            w.lower() in z for z in sprache.listen["zeit"]))
        if ort:
            return "\n".join(welt_uhrzeit(o_, code, holen, jetzt) for o_ in _welt_orte(ort))
        versatz = jetzt.utcoffset()
        stunden = int(versatz.total_seconds() // 3600) if versatz is not None else 0
        return a["zeit"].format(zeit=f"{jetzt:%H:%M} (UTC{stunden:+d})")
    if "datum" in arten and not wetter:
        if weltsprachen.enthaelt(frage, sprache, "morgen"):
            # "What is the date tomorrow?" nannte vorher das Datum von heute.
            from datetime import timedelta

            wort = sprache.listen["morgen"][0]
            morgen = (jetzt.date() + timedelta(days=1)).isoformat()
            return f"{wort[:1].upper()}{wort[1:]}: **{morgen}**"
        return a["datum"].format(datum=jetzt.date().isoformat())
    if not wetter and _letzte_antwort(verlauf) == a["ort"] and len(frage.split()) <= 5:
        ort = frage.strip(" ?!.,;:¿¡")
        return welt_wetter(ort, code, frage, holen, jetzt.date()) if ort else a["ort"]
    if wetter:
        ohne_tag = wochentag_in(uebermorgen_in(frage, code)[1], code, jetzt.date())[2]
        ort = weltsprachen.ort_aus(ohne_tag, sprache) or str(wohnort or "").strip()
        if not ort:
            return a["ort"]
        return "\n\n".join(welt_wetter(o_, code, frage, holen, jetzt.date())
                             for o_ in _welt_orte(ort))
    if code == "en":
        return ""
    ausdruck = re.search(r"[\d(][\d\s.,+\-*/()%^×÷]*[\d)]", frage)
    if ausdruck and re.search(r"[+\-*/^×÷]", ausdruck.group(0)):
        text = rechnen(ausdruck.group(0))
        if text:
            return text
    thema = weltsprachen.thema(frage, sprache)
    if thema:
        # Die Schreibweise aus der Frage: vorher hiess es „victor hugo“ statt „Victor Hugo“.
        wie_gefragt = re.search(re.escape(thema), frage, re.I)
        thema = wie_gefragt.group(0) if wie_gefragt else thema
        return wissen(thema, holen, sprache.wiki) or a["nichts"].format(x=thema)
    return a["rueckfall"]


#: 16.4.5: "und" in anderen Sprachen -- "Paris and Rome" suchte vorher einen Ort
#: "Paris and Rome". Ein Ort, der selbst "y" enthaelt (Trinidad y Tobago), wird dann zweimal
#: gesucht; das ist seltener als zwei Orte.
_UND_WELT = re.compile(r"\s+(?:and|und|y|et|e|i|og|och|en|und|ve|oraz|és|a|и|та|і)\s+|\s*,\s*",
                       re.IGNORECASE)


def _welt_orte(ort: str) -> list[str]:
    teile = [t.strip() for t in _UND_WELT.split(ort) if t.strip()]
    if len(teile) > 1 and all(len(t) >= 3 for t in teile):
        return teile[:3]
    return [ort]


def ist_standard(model: str) -> bool:
    return str(model or "").strip() == MODEL_ID


__all__ = ["LABEL", "MODEL_ID", "antwort", "ist_standard"]
