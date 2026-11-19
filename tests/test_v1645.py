"""16.4.5: Gefundene Fehler in Aquaticy Standard, Werkzeugen, Rechner und Oberflaeche."""

import random
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from aquaticy import standard, weltsprachen
from aquaticy.calc import CalcError, calculate

JETZT = datetime(2026, 11, 19, 14, 30, tzinfo=ZoneInfo("Europe/Berlin"))


def frag(text: str, wuerfel: random.Random | None = None) -> str:
    return standard._antwort(text, [], holen=lambda url: None, jetzt=JETZT, wuerfel=wuerfel)


@pytest.mark.parametrize("frage, erwartet", [
    ("Wann ist Ostern 2024?", "Ostersonntag war am **31.03.2024**."),
    ("Wann ist Ostern 2027?", "Ostersonntag ist am **28.03.2027**."),
    ("Wann ist Pfingsten 2026?", "Pfingstsonntag war am **Sonntag, 24.05.2026**."),
    ("Wann ist Silvester 2025?", "Silvester war am **Mittwoch, 31.12.2025**."),
    ("Wann ist Karfreitag 2027?", "Karfreitag ist 2027 am **Freitag, 26.03.2027**."),
])
def test_an_explicit_year_is_used(frage, erwartet):
    assert frag(frage) == erwartet


def test_all_holidays_of_a_named_year():
    antwort = frag("Welche Feiertage gibt es 2027?")
    assert antwort.startswith("Die bundesweiten Feiertage 2027:")
    assert "Karfreitag:** Freitag, 26.03.2027" in antwort and "25.12.2027" in antwort


@pytest.mark.parametrize("frage, erwartet", [
    ("Welches Datum ist morgen?", "Morgen ist **Freitag, der 20.11.2026**"),
    ("Was für ein Tag ist übermorgen?", "Übermorgen ist **Samstag, der 21.11.2026**"),
    ("Welches Datum war gestern?", "Gestern war **Mittwoch, der 18.11.2026**"),
    ("Welcher Tag ist heute?", "Heute ist **Donnerstag, der 19.11.2026**"),
])
def test_dates_relative_to_today(frage, erwartet):
    assert frag(frage).startswith(erwartet)


def test_tip_with_the_word_percent():
    assert frag("Trinkgeld 10 Prozent auf 45 Euro").startswith(
        "10 % Trinkgeld auf 45,00 € sind **4,50 €**")


def test_big_whole_numbers_are_exact():
    assert frag("Was ist 9999999999 * 9999999999?") == "**99.999.999.980.000.000.001**"
    assert standard.schoen(10**20) == "100.000.000.000.000.000.000"
    assert frag("Was ist 1/3?") == "**0,333333**"


def test_percent_with_the_numbers_first():
    assert frag("80 ist wie viel Prozent von 200?") == "80 von 200 sind **40 %**."


@pytest.mark.parametrize("frage, erwartet", [
    ("Wie viele Tage seit dem 1.1.2026?", "Seit dem 01.01.2026 sind **322 Tage** vergangen."),
    ("Wie viele Tage bis zum 1.1.2026?", "Der 01.01.2026 war vor **322 Tagen**."),
])
def test_days_since_a_past_date(frage, erwartet):
    assert frag(frage) == erwartet


def test_when_is_christmas_and_the_countdown_stays():
    assert frag("Wann ist Weihnachten?").startswith("Heiligabend ist am **Donnerstag, 24.12.2026**")
    assert frag("Wie viele Tage bis Weihnachten?") == (
        "Bis Weihnachten (24.12.2026) sind es noch **35 Tage**.")


@pytest.mark.parametrize("frage", ["Mein BMI bei 1,75 m und 70 kg", "BMI 70 kg 175 cm"])
def test_bmi_in_both_orders(frage):
    assert "**22,9**" in frag(frage)


def test_dice_with_count_and_sides():
    drei = frag("Würfle 3 Würfel", random.Random(3))
    assert re.fullmatch(r"🎲 Gewürfelt: \d \+ \d \+ \d = \*\*\d+\*\*", drei)
    assert "(W20)" in frag("Würfle einen W20", random.Random(3))
    assert re.fullmatch(r"🎲 Gewürfelt: \*\*[1-6]\*\*", frag("Würfel", random.Random(3)))


@pytest.mark.parametrize("frage, erwartet", [
    ("1 PS in kW", "1 PS sind **0,7355 kW**."),
    ("100 kW in PS", "100 kW sind **135,9622 PS**."),
    ("6 Fuß in Metern", "6 Fuss sind **1,8288 Meter**."),
    ("1 Gallone in Litern", "1 Gallone sind **3,7854 Liter**."),
    ("1 Jahr in Tagen", "1 Jahr sind **365,25 Tage**."),
    ("Wie viele Sekunden hat ein Tag?", "1 Tag sind **86.400 Sekunden**."),
])
def test_units_with_power_and_dative(frage, erwartet):
    assert frag(frage) == erwartet


def test_the_calendar_week_still_works():
    assert frag("Welche Kalenderwoche ist heute?") == "Wir haben **KW 47**."


@pytest.mark.parametrize("frage, erwartet", [
    ("What is the date tomorrow?", "Tomorrow: **2026-11-20**"),
    ("¿Qué fecha es mañana?", "Mañana: **2026-11-20**"),
])
def test_the_date_of_tomorrow_in_other_languages(frage, erwartet):
    assert frag(frage) == erwartet


@pytest.mark.parametrize("frage, erwartet", [
    ("What's 2 + 2?", "**4**"),
    ("Convert 10 miles to km", "10 miles is **16.0934 km**."),
    ("5 kg to pounds", "5 kg is **11.0231 pounds**."),
])
def test_english_questions_get_english_numbers(frage, erwartet):
    assert frag(frage) == erwartet


@pytest.mark.parametrize("frage", ["Flip a coin", "Roll a die", "Is 2024 a leap year?"])
def test_english_commands_get_an_english_fallback(frage):
    assert weltsprachen.sprache_von(frage) == "en"
    assert frag(frage).startswith("Sorry")


def test_german_stays_german():
    assert frag("5 kg in Pfund") == "5 kg sind **10 Pfund**."
    assert weltsprachen.sprache_von("Die Kinder spielen draußen") in ("", "de")


@pytest.mark.parametrize("wert, erwartet", [
    ("5", 5), (5.7, 5), ("fünf", 0), (["a"], 0), (None, 0), ("1e309", 0), (True, 1),
])
def test_tool_numbers_from_the_model_never_crash(wert, erwartet):
    from aquaticy.tools import _ganzzahl

    assert _ganzzahl(wert) == erwartet


def test_the_calculator_prints_no_syntax_warning():
    lauf = subprocess.run(
        ["python", "-W", "error::SyntaxWarning", "-c",
         "from aquaticy.calc import calculate, CalcError\n"
         "try:\n    calculate('1_0x+1')\nexcept CalcError:\n    print('ok')"],
        capture_output=True, text=True, timeout=30)
    assert lauf.stdout.strip() == "ok", lauf.stderr
    with pytest.raises(CalcError):
        calculate("1_0x+1")


def _md(text: str) -> str:
    seite = Path(standard.__file__).with_name("webui.html").read_text(encoding="utf-8")
    js = seite[seite.index("const esc = (t) =>"):seite.index("function chatDetails(")]
    skript = js + "\nprocess.stdout.write(md(process.argv[2]));"
    try:
        lauf = subprocess.run(["node", "-", text], input=skript, capture_output=True,
                              text=True, timeout=30)
    except FileNotFoundError:
        pytest.skip("node fehlt")
    return lauf.stdout


def test_links_lose_the_full_stop_at_the_end():
    html = _md("Mehr unter https://example.com.")
    assert 'href="https://example.com"' in html and html.endswith("</a>.</p>")


def test_links_keep_brackets_in_the_address():
    html = _md("[Wiki](https://de.wikipedia.org/wiki/Klammer_(Begriff))")
    assert 'href="https://de.wikipedia.org/wiki/Klammer_(Begriff)"' in html


def test_multiplication_signs_are_not_italics():
    assert _md("a * b * c") == "<p>a * b * c</p>"
    assert _md("Text *mit Betonung* hier") == "<p>Text <em>mit Betonung</em> hier</p>"
