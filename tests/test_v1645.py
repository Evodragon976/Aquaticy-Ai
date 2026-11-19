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
    ("6 Fuß in Metern", "6 Fuß sind **1,8288 Meter**."),
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


# -- Teil 2 -------------------------------------------------------------------------------


def test_lone_surrogates_from_json_become_a_replacement_character():
    from aquaticy.jsonutil import loads

    daten = loads(b'{"a": "x\\ud800y", "b": ["\\ud83d\\ude00"], "\\udcff": 1}')
    assert daten == {"a": "x�y", "b": ["\U0001F600"], "�": 1}
    assert frag("Wetter in Berlin\ud800").encode("utf-8")


def test_lookalike_usernames_are_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("AQUATICY_KDF", "schnell")
    from aquaticy.auth import AuthStore, name_key, normalize_username

    with pytest.raises(ValueError):
        normalize_username("admin​")
    assert normalize_username("Jürgen") == "Jürgen"
    assert name_key("ＡＤＭＩＮ") == name_key("admin")
    store = AuthStore(tmp_path, "PRO123456")
    store.register("a@example.com", "sehr-langes-passwort-123", "normal", username="admin",
                   terms_accepted=True, terms_version="t", trusted=True)
    for doppelt in ("ADMIN", "ａｄｍｉｎ"):
        with pytest.raises(ValueError):
            store.register(f"{doppelt}@example.org".replace("ａ", "b"), "sehr-langes-passwort-123",
                           "normal", username=doppelt, terms_accepted=True, terms_version="t",
                           trusted=True)


def test_changelog_has_no_dead_internal_links():
    wurzel = Path(standard.__file__).resolve().parent.parent
    text = (wurzel / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "](#was-aquaticy-kann)" not in text
    for ziel in re.findall(r"\]\((tests/[^)#]+)\)", text):
        assert (wurzel / ziel).exists(), ziel


@pytest.mark.parametrize("frage, erwartet", [
    ("Wann geht morgen die Sonne in Berlin auf?", "Morgen geht die Sonne"),
    ("Wann wird es morgen in Berlin dunkel?", "Morgen geht die Sonne"),
    ("Wetter in 10 Tagen in Berlin", "nur sieben Tage"),
    ("Wird es am Samstag in Berlin warm?", "°C"),
    ("Was ziehe ich morgen in Berlin an?", "Für morgen"),
    ("Werde ich morgen in Berlin nass?", "Schirm"),
    ("Wetter Berlin morgen", "**Morgen in"),
    ("Berlin Wetter am Montag", "Montag"),
])
def test_weather_questions_in_more_forms(frage, erwartet):
    from datetime import date, timedelta

    orte = []

    def holen(url):
        if "geocoding" in url:
            orte.append(url)
            return {"results": [{"name": "Berlin", "latitude": 52.5, "longitude": 13.4}]}
        d0 = date(2026, 11, 19)
        tage = [(d0 + timedelta(days=i)).isoformat() for i in range(7)]
        return {"daily": {"time": tage, "weather_code": [71] * 7,
                          "temperature_2m_max": [3] * 7, "temperature_2m_min": [-2] * 7,
                          "precipitation_probability_max": [70] * 7,
                          "sunrise": [f"{t}T07:40" for t in tage],
                          "sunset": [f"{t}T16:10" for t in tage]}, "current": {}}

    antwort = standard._antwort(frage, [], holen=holen, jetzt=JETZT)
    assert erwartet in antwort, antwort
    assert all("name=Berlin&" in url or url.endswith("name=Berlin") for url in orte), orte


def test_snow_is_not_called_rain():
    d = {"name": "Berlin", "jetzt": {}, "tage": [
        {"datum": None, "code": 71, "tief": -2, "hoch": 1, "regen": 90}]}
    assert "Schneerisiko 90 %" in standard._tageszeile(d, 0)


@pytest.mark.parametrize("frage", ["Brauche ich in Frankfurt am Main eine Mütze?",
                                   "Wann geht in Frankfurt am Main die Sonne auf?",
                                   "Wann geht in Frankfurt am Main übermorgen die Sonne unter?"])
def test_place_names_lose_the_rest_of_the_question(frage):
    assert standard.orte_aus(frage) == ["Frankfurt am Main"]


@pytest.mark.parametrize("frage, thema", [
    ("Was ist eigentlich ein Axolotl?", "Axolotl"), ("Was heißt Demokratie?", "Demokratie"),
    ("Kennst du Marie Curie?", "Marie Curie"), ("Weißt du, was ein Okapi ist?", "Okapi"),
    ("Infos zu Paris", "Paris"), ("Wer erfand das Telefon?", "Telefon"),
    ("Wann lebte Kleopatra?", "Kleopatra"), ("Wie alt wurde Einstein?", "Einstein"),
    ("Was macht ein Notar?", "Notar"), ("Wie funktioniert ein Kühlschrank?", "Kühlschrank"),
    ("Tell me about Rome", "Rome"),
    ("Was ist das?", ""), ("Wer ist er?", ""), ("Kennst du mich?", ""),
    ("Was heißt Hund auf Englisch?", ""), ("Was macht ein gutes Leben aus?", ""),
])
def test_topics_of_knowledge_questions(frage, thema):
    assert standard.thema_aus(frage) == thema


@pytest.mark.parametrize("frage, erwartet", [
    ("Was ist 10 % von 1.000?", "10 % von 1.000 sind **100**."),
    ("Was ist 1.000 + 1?", "**1.001**"),
    ("1.500 m in km", "1.500 m sind **1,5 km**."),
    ("2.000 Euro netto in brutto", "2.000 € netto sind **2.380 € brutto**"),
    ("Was ist 1.5 + 1?", "**2,5**"),
    ("5 km sind wie viele Meilen?", "5 km sind **3,1069 Meilen**."),
])
def test_the_german_thousands_separator(frage, erwartet):
    assert frag(frage).startswith(erwartet)


@pytest.mark.parametrize("frage, erwartet", [
    ("Wie viel sind 1.000 Euro in Dollar?", "1.000 EUR sind **1.100 USD**"),
    ("1,5 Mio Euro in Dollar", "1.500.000 EUR sind **1.650.000 USD**"),
    ("100 Euro in Schweizer Franken", "100 EUR sind **110 CHF**"),
    ("100 euro to pounds", "100 EUR sind **110 GBP**"),
    ("Wie viele Dollar bekomme ich für 200 Euro?", "200 EUR sind **220 USD**"),
    ("200 Euro sind wie viel Dollar?", "200 EUR sind **220 USD**"),
    ("Wie steht der Dollar?", "1 EUR sind **1,1 USD**"),
])
def test_currency_questions(frage, erwartet):
    def holen(url):
        von = re.search(r"from=([A-Z]{3})", url).group(1)
        nach = re.search(r"to=([A-Z]+)", url).group(1)
        return {"base": von, "date": "2026-11-18", "rates": {nach: 1.1}}

    assert standard._antwort(frage, [], holen=holen, jetzt=JETZT).startswith(erwartet)


# -- Teil 3 -----------------------------------------------------------------------------------

@pytest.mark.parametrize("frage, erwartet", [
    ("Ist der 3. Oktober ein Feiertag?", "Ja, der 03.10.2026 war **Tag der Deutschen Einheit**."),
    ("Welcher Feiertag ist am 25.12.?", "Der 25.12.2026 ist **1. Weihnachtstag**."),
    ("Was ist heute für ein Datum?", "Heute ist **Donnerstag, der 19.11.2026**"),
    ("Welchen Tag haben wir heute?", "Heute ist **Donnerstag, der 19.11.2026**"),
    ("Welches Jahr haben wir?", "Wir haben das Jahr **2026**."),
    ("Welcher Monat ist gerade?", "Wir haben **November 2026**."),
    ("Wann ist Fronleichnam?", "Fronleichnam ist am **Donnerstag, 27.05.2027**"),
    ("Wann ist der Reformationstag?", "Der Reformationstag ist am **Sonntag, 31.10.2027**"),
    ("Wie viele Tage bis Freitag?", "Bis Freitag ist es noch **1 Tag**."),
    ("Wie viele Tage bis zum Wochenende?", "Bis zum Wochenende (Samstag) sind es noch **2 Tage**."),
    ("Wann werden die Uhren umgestellt?",
     "Die nächste Zeitumstellung ist am **Sonntag, 28.03.2027**"),
])
def test_date_questions_in_more_forms(frage, erwartet):
    assert frag(frage).startswith(erwartet)


def test_one_day_is_not_called_one_days():
    from datetime import date

    assert standard.in_tagen(1) == "morgen" and standard.in_tagen(3) == "in 3 Tagen"
    antwort = frag("Ich bin am 20.11.1990 geboren, wie alt bin ich?")
    assert "1 Tage" not in antwort and "Morgen ist dein Geburtstag" in antwort
    assert "in 1 Tagen" not in standard.anlass("Wann ist Nikolaus?", date(2026, 12, 5))


def test_a_birth_year_in_the_future():
    assert frag("Ich bin 2030 geboren") == "Das Jahr 2030 liegt noch in der Zukunft."


@pytest.mark.parametrize("frage, erwartet", [
    ("100 Euro netto in brutto bei 7 %",
     "100 € netto sind **107 € brutto** (7 % MwSt.: 7 €)."),
    ("100 Euro brutto in netto", "100 € brutto sind **84,03 € netto** (19 % MwSt."),
    ("30 von 120 in Prozent", "30 von 120 sind **25 %**."),
    ("Von 80 auf 100 sind wie viel Prozent?", "Von 80 auf 100 sind es **25 % mehr**."),
    ("Was ist die Wurzel von 2?", "**1,414214**"),
    ("Was ist das Doppelte von 21?", "Das Doppelte von 21 ist **42**."),
    ("10 Prozent mehr als 50", "10 % mehr als 50 sind **55**."),
    ("20 % weniger als 150", "20 % weniger als 150 sind **120**."),
    ("Mehrwertsteuer von 100 Euro", "Auf 100,00 € kommen **19,00 €** Mehrwertsteuer"),
    ("19 % MwSt auf 50 €", "Auf 50,00 € kommen **9,50 €** Mehrwertsteuer"),
    ("Wie viel MwSt ist in 119 Euro?", "In 119,00 € stecken **19,00 €** Mehrwertsteuer"),
    ("80 € abzüglich 25 %", "80 minus 25 % sind **60**"),
    ("Preis 80 Euro, 25 % Rabatt", "25 % Rabatt auf 80 sind **60**"),
    ("What is 15% of 200?", "15 % of 200 is **30**."),
])
def test_percent_questions_in_more_forms(frage, erwartet):
    assert frag(frage).startswith(erwartet)


@pytest.mark.parametrize("frage, erwartet", [
    ("Buchstabiere Straße", "S – T – R – A – ß – E"),
    ("Was ist 255 binär?", "255 ist binär **11111111**."),
    ("Was ist MMXXVI?", "Die römische Zahl MMXXVI ist **2026**."),
    ("Was bedeutet XLII?", "Die römische Zahl XLII ist **42**."),
    ("Wie schreibt man 49 römisch?", "49 schreibt man römisch **XLIX**."),
    ("Was ist 0xFF?", "0xff ist dezimal **255**."),
    ("0b1010 in dezimal", "0b1010 ist dezimal **10**."),
    ("Ist 1.000.003 eine Primzahl?", "Ja, **1.000.003** ist eine Primzahl."),
    ("Ist -7 eine Primzahl?", "Nein, -7 ist keine Primzahl."),
])
def test_numbers_and_text_in_more_forms(frage, erwartet):
    assert frag(frage).startswith(erwartet)


@pytest.mark.parametrize("frage", ["Was ist CD?", "Was ist MIX?", "Was ist MMMM?"])
def test_short_or_invalid_roman_numbers_stay_topics(frage):
    assert "römische Zahl" not in frag(frage)


def test_a_password_without_special_characters():
    for _ in range(20):
        antwort = frag("Generiere ein Passwort ohne Sonderzeichen")
        wort = re.search(r"`([^`]+)`", antwort).group(1)
        assert wort.isalnum()


def test_the_security_answer_takes_the_matching_word():
    antwort = standard._antwort("Wie sicher ist WPA3?", [], secure=True,
                                holen=lambda url: None, jetzt=JETZT)
    assert antwort.startswith("**WLAN sicher machen:**")
    assert "Ransomware" not in antwort


@pytest.mark.parametrize("frage", ["Was für Wetter ist morgen in Berlin?",
                                   "Was für Wetter haben wir in Berlin?"])
def test_was_fuer_is_not_a_place(frage):
    assert standard.orte_aus(frage) == ["Berlin"]


@pytest.mark.parametrize("satz, code, ort, tag", [
    ("¿Va a llover mañana en Sevilla?", "es", "Sevilla", "mañana"),
    ("Quel temps fait-il à Paris demain ?", "fr", "Paris", "demain"),
    ("Il va pleuvoir à Lyon aujourd'hui ?", "fr", "Lyon", "aujourd'hui"),
    ("Wat voor weer is het morgen in Amsterdam?", "nl", "Amsterdam", "morgen"),
    ("هوای تهران فردا چطور است؟", "fa", "تهران", "فردا"),
    ("Do I need an umbrella in London tomorrow?", "en", "London", "tomorrow"),
    ("What should I wear in London today?", "en", "London", "today"),
    ("Will it rain in London tomorrow?", "en", "London", "tomorrow"),
    ("How cold is it in Oslo?", "en", "Oslo", "today"),
])
def test_weather_sentences_in_other_languages(satz, code, ort, tag):
    from datetime import date, timedelta
    from urllib.parse import unquote

    orte = []

    def holen(url):
        if "geocoding" in url:
            orte.append(unquote(re.search(r"name=([^&]+)", url).group(1)))
            return {"results": [{"name": orte[-1], "latitude": 1, "longitude": 1}]}
        d0 = date(2026, 11, 19)
        return {"daily": {"time": [(d0 + timedelta(days=i)).isoformat() for i in range(7)],
                          "weather_code": [61] * 7, "temperature_2m_max": [8] * 7,
                          "temperature_2m_min": [2] * 7,
                          "precipitation_probability_max": [70] * 7}, "current": {}}

    assert weltsprachen.sprache_von(satz) == code
    antwort = standard._antwort(satz, [], holen=holen, jetzt=JETZT)
    assert orte == [ort]
    assert antwort.startswith(f"**{ort}** · {tag}:")


@pytest.mark.parametrize("satz", ["Gibt es morgen Regen in Köln?", "What is a hot dog?"])
def test_new_weather_words_do_not_take_over(satz):
    assert weltsprachen.sprache_von(satz) in ("de", "en", "")
    antwort = standard._antwort(satz, [], holen=lambda url: None, jetzt=JETZT)
    assert "·" not in antwort.split("\n")[0]


@pytest.mark.parametrize("frage, erwartet", [
    ("Wurzel aus 1.000.000", "**1.000**"), ("Was ist 1001 hoch 2?", "**1.002.001**"),
    ("Was ist 2 hoch 13?", "**8.192**"), ("Was ist 3 zum Quadrat?", "**9**"),
    ("what is 3 squared?", "**9**"), ("what is 2 to the power of 10?", "**1,024**"),
    ("Was ist 4²?", "**16**"), ("Was ist √16?", "**4**"), ("Was ist 100 : 4?", "**25**"),
    ("What is the square root of 16?", "**4**"), ("Was ist die Kubikwurzel von 27?", "**3**"),
    ("Was ist minus 5 plus 3?", "**-2**"), ("Was ist 15 modulo 4?", "**3**"),
    ("Was ist 25% von 1,5 Mio?", "25 % von 1.500.000 sind **375.000**."),
    ("2^1000", "Das wird mir zu groß"), ("Was ist 1001 hoch 12?", "Das wird mir zu groß"),
])
def test_calculations_in_more_forms(frage, erwartet):
    assert frag(frage).startswith(erwartet)


def test_the_power_limit_is_about_the_size_of_the_result():
    assert calculate("1001 ** 2") == 1002001
    assert calculate("1000000 ** 0.5") == 1000
    for zu_gross in ("9**9**9", "1e-300 ** -12", "2 ** 1000", "1 ** 100000"):
        with pytest.raises(CalcError):
            calculate(zu_gross)


@pytest.mark.parametrize("frage, erwartet", [
    ("Wann ist Vollmond?", "Heute ist **zunehmender Mond 🌔**. Der nächste Vollmond ist etwa"),
    ("Ist heute Vollmond?", "Nein, heute ist kein Vollmond"),
    ("Wann ist Neumond?", "Heute ist **zunehmender Mond 🌔**. Der nächste Neumond ist etwa"),
    ("Was ist heute für ein Wochentag?", "Heute ist **Donnerstag, der 19.11.2026**"),
    ("Was war vorgestern für ein Tag?", "Vorgestern war **Dienstag, der 17.11.2026**"),
    ("Welches Datum war vor 100 Tagen?", "Vor 100 Tagen war **Dienstag, der 11.08.2026**."),
    ("Welches Datum ist in 30 Tagen?", "In 30 Tagen ist **Samstag, der 19.12.2026**."),
    ("Was ist in 2 Wochen für ein Datum?", "In 2 Wochen ist **Donnerstag, der 03.12.2026**."),
    ("Wie viele Wochen bis Weihnachten?", "Bis Weihnachten (24.12.2026) sind es noch **35 Tage**. "
                                          "Das sind **5 Wochen**."),
    ("Wie viele Tage hat dieser Monat?", "Der November 2026 hat **30 Tage**."),
    ("Ist Pfingstmontag ein Feiertag?", "Ja, Pfingstmontag ist ein bundesweiter Feiertag"),
    ("Ist Rosenmontag ein Feiertag?", "Nein, Rosenmontag ist kein gesetzlicher Feiertag."),
    ("Welche Feiertage gibt es im Dezember?", "Bundesweite Feiertage im Dezember 2026:"),
])
def test_moon_and_calendar_in_more_forms(frage, erwartet):
    antwort = frag(frage)
    assert antwort.startswith(erwartet), antwort
    assert "Neujahr" not in antwort


@pytest.mark.parametrize("frage, wahl", [
    ("Wähle: rot, blau oder grün", {"rot", "blau", "grün"}),
    ("Wähle zwischen Pizza und Pasta", {"Pizza", "Pasta"}),
    ("Entscheide zwischen Kino und Theater", {"Kino", "Theater"}),
    ("Rot, Blau oder Grün?", {"Rot", "Blau", "Grün"}),
])
def test_choices_take_one_of_the_options(frage, wahl):
    for samen in range(10):
        antwort = frag(frage, random.Random(samen))
        assert re.fullmatch(r"Ich würde sagen: \*\*(.+)\*\*\.", antwort).group(1) in wahl


def test_a_number_between_in_any_order():
    for samen in range(10):
        antwort = frag("Nenn mir eine Zahl zwischen 10 und 5", random.Random(samen))
        assert 5 <= int(re.search(r"\*\*(\d+)\*\*", antwort).group(1)) <= 10


@pytest.mark.parametrize("tag, frage, erwartet", [
    (22, "Wetter am Wochenende", [0]), (22, "Wetter nächstes Wochenende", [6]),
    (21, "Wetter am Wochenende", [0, 1]), (19, "Wetter am Wochenende", [2, 3]),
    (19, "Wetter nächste Woche", [4, 5, 6]), (22, "Wetter nächste Woche", [1, 2, 3, 4, 5, 6]),
    (19, "Wetter diese Woche", list(range(7))),
])
def test_weekend_and_next_week(tag, frage, erwartet):
    from datetime import date

    assert standard.tage_aus(standard.falten(frage), date(2026, 11, tag)) == erwartet


@pytest.mark.parametrize("zweite, ort, tag", [
    ("und übermorgen in Bonn?", "Bonn", "Übermorgen"), ("und in Bonn morgen?", "Bonn", "Morgen"),
    ("und in Frankfurt am Main?", "Frankfurt am Main", "Heute"),
    ("und morgen in Frankfurt am Main?", "Frankfurt am Main", "Morgen"),
])
def test_follow_up_with_day_and_place(zweite, ort, tag):
    from datetime import date, timedelta
    from urllib.parse import unquote

    orte = []

    def holen(url):
        if "geocoding" in url:
            orte.append(unquote(re.search(r"name=([^&]+)", url).group(1)))
            return {"results": [{"name": orte[-1], "latitude": 1, "longitude": 1}]}
        tage = [(date(2026, 11, 19) + timedelta(days=i)).isoformat() for i in range(7)]
        return {"daily": {"time": tage, "weather_code": [61] * 7,
                          "temperature_2m_max": [5] * 7, "temperature_2m_min": [1] * 7,
                          "precipitation_probability_max": [80] * 7}, "current": {}}

    erste = standard._antwort("Wie ist das Wetter in Köln?", [], holen=holen, jetzt=JETZT)
    verlauf = [{"role": "user", "content": "Wie ist das Wetter in Köln?"},
               {"role": "assistant", "content": erste}]
    orte.clear()
    antwort = standard._antwort(zweite, verlauf, holen=holen, jetzt=JETZT)
    assert orte == [ort]
    assert f"**{tag} in {ort}:**" in antwort


def test_the_old_power_limits_still_hold():
    assert calculate("0.0001 ** 12") == pytest.approx(1e-48)
    assert calculate("1e-5 ** -12") == pytest.approx(1e60)
    assert calculate("2 ** 13") == 8192


@pytest.mark.parametrize("frage", [
    "Wählt man den Kanzler direkt oder indirekt?",
    "Messenger-Modellwahl und Arbeitsmodi, ohne echte Konten oder Modellaufrufe.",
    "Wähle zwischen dem roten Auto mit Schiebedach und dem blauen Auto",
])
def test_questions_and_sentences_are_not_choices(frage):
    assert not frag(frage).startswith("Ich würde sagen")


@pytest.mark.parametrize("frage", ["Welcher Monat ist der kälteste?", "Welchen Tag hat die Woche?"])
def test_only_the_whole_question_asks_for_the_date(frage):
    antwort = frag(frage)
    assert not antwort.startswith(("Wir haben", "Heute ist"))


@pytest.mark.parametrize("frage, thema", [
    ("Was ist ein Regenschirm?", "Regenschirm"), ("What is Sunset Boulevard?", "Sunset Boulevard"),
    ("What is the Umbrella Academy?", "Umbrella Academy"), ("Wer ist Mantel?", "Mantel"),
])
def test_knowledge_questions_about_weather_words(frage, thema):
    antwort = frag(frage)
    assert f"„{thema}“" in antwort or f"“{thema}”" in antwort
    assert "Ort" not in antwort and "place" not in antwort


@pytest.mark.parametrize("frage", ["Was ist das Wetter?", "Was ist das Wetter morgen?",
                                   "Brauche ich einen Schirm?"])
def test_weather_questions_still_ask_for_the_place(frage):
    assert "Für welchen Ort" in frag(frage)


@pytest.mark.parametrize("satz, ort", [
    ("Weather in Hot Springs", "Hot Springs"), ("Weather in Cold Lake", "Cold Lake"),
    ("Weather in Sunny Isles Beach", "Sunny Isles Beach"),
    ("Weather in London this weekend", "London"),
])
def test_english_place_names_keep_weather_words(satz, ort):
    assert weltsprachen.ort_aus(satz, weltsprachen.SPRACHEN["en"]) == ort


def test_and_is_not_a_place():
    antwort = frag("What is the weather like today and what should I wear?")
    assert antwort == "For which place should I check the weather?"


def test_feet_are_written_with_sharp_s():
    assert standard.einheiten("5 Fuß in Meter") == "5 Fuß sind **1,524 Meter**."
