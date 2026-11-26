"""17.1.1: Funde der Fehlersuche (Fundbuch-Nummern in den Fällen) -- ohne Netz."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit
from zoneinfo import ZoneInfo

import pytest

from aquaticy import standard

JETZT = datetime(2026, 11, 25, 10, 30, tzinfo=ZoneInfo("Europe/Berlin"))
ORTE = {
    "berlin": ("Berlin", 52.52, 13.41, "Europe/Berlin"),
    "hamburg": ("Hamburg", 53.55, 9.99, "Europe/Berlin"),
    "türkei": ("Türkei", 39.0, 35.0, "Europe/Istanbul"),
    "tokio": ("Tokio", 35.69, 139.69, "Asia/Tokyo"),
    "kathmandu": ("Kathmandu", 27.7, 85.3, "Asia/Kathmandu"),
    "mumbai": ("Mumbai", 19.08, 72.88, "Asia/Kolkata"),
    "new york": ("New York", 40.71, -74.01, "America/New_York"),
    "london": ("London", 51.51, -0.13, "Europe/London"),
    "madrid": ("Madrid", 40.42, -3.7, "Europe/Madrid"),
    "dubai": ("Dubai", 25.2, 55.27, "Asia/Dubai"),
    "paris": ("Paris", 48.85, 2.35, "Europe/Paris"),
}


def holen(url: str) -> Any:
    teile = urlsplit(url)
    q = {k: v[0] for k, v in parse_qs(teile.query).items()}
    if "geocoding" in str(teile.hostname):
        ort = ORTE.get(unquote(q.get("name", "")).strip().lower())
        if not ort:
            return {"results": []}
        return {"results": [{"name": ort[0], "latitude": ort[1], "longitude": ort[2],
                             "timezone": ort[3]}]}
    if "forecast" in url:
        tage = [(date(2026, 11, 25) + timedelta(days=i)).isoformat() for i in range(7)]
        return {"daily": {"time": tage, "weather_code": [61, 0, 3, 71, 95, 45, 1],
                          "temperature_2m_max": [9.4, 11.0, 8.2, -1.0, 24.5, 5.0, 31.0],
                          "temperature_2m_min": [3.1, 4.0, 2.0, -6.5, 15.0, -0.4, 19.0],
                          "apparent_temperature_max": [7.0, 10.0, 6.0, -5.0, 26.0, 3.0, 33.0],
                          "apparent_temperature_min": [0.5, 2.0, -1.0, -11.0, 15.0, -3.0, 20.0],
                          "precipitation_probability_max": [70, 10, 20, 80, 90, 5, 0],
                          "precipitation_sum": [4.2, 0.0, 0.3, 6.0, 22.0, 0.0, 0.0],
                          "wind_speed_10m_max": [18.0, 9.0, 35.0, 55.0, 70.0, 4.0, 12.0],
                          "uv_index_max": [1.0, 2.0, 1.0, 0.5, 6.0, 1.0, 9.0],
                          "sunrise": [t + "T07:48" for t in tage],
                          "sunset": [t + "T16:05" for t in tage]},
                "current": {"temperature_2m": 7.2, "apparent_temperature": 5.1,
                            "weather_code": 61, "wind_speed_10m": 14.0}}
    if "frankfurter" in url:
        kurse = {"EUR": 1.0, "USD": 1.0823, "GBP": 0.8412, "CHF": 0.9367, "JPY": 162.35}
        basis = q.get("from", "EUR").upper()
        ziele = [z for z in q.get("to", "").upper().split(",") if z] or list(kurse)
        return {"base": basis, "date": "2026-11-25",
                "rates": {z: round(kurse[z] / kurse[basis], 6) for z in ziele
                          if z in kurse and z != basis}}
    return None


def frag(frage: str, jetzt: datetime = JETZT, verlauf: list[dict[str, Any]] | None = None) -> str:
    return standard._antwort(frage, verlauf or [], holen=holen, jetzt=jetzt,
                             wuerfel=random.Random(1))


SONNTAG = datetime(2026, 11, 29, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))

STANDARD = [
    (1, "Was ist der größte gemeinsame Teiler von 12 und 18?",
     "größte gemeinsame Teiler ist **6**"),
    (1, "Welche Teiler hat 12?", "12 hat **6 Teiler**"),
    (2, "Welches Datum ist in einem Monat?", "**Freitag, der 25.12.2026**"),
    (2, "Welches Datum ist in 3 Monaten?", "**Donnerstag, der 25.02.2027**"),
    (2, "Welches Datum ist in einem Jahr?", "**Donnerstag, der 25.11.2027**"),
    (2, "Welches Datum war vor zwei Jahren?", "**Montag, der 25.11.2024**"),
    (3, "Welcher Wochentag ist in 10 Tagen?", "**Samstag, der 05.12.2026**"),
    (3, "Was ist heute in 14 Tagen?", "**Mittwoch, der 09.12.2026**"),
    (4, "Wie viele Arbeitstage zwischen 1.12.2026 und 31.12.2026?", "**22 Arbeitstage**"),
    (4, "Wie viele Tage zwischen 1.12.2026 und 31.12.2026?", "**30 Tage**"),
    (5, "Welcher Tag ist der 100. Tag des Jahres?", "**Freitag, der 10.04.2026**"),
    (5, "Was ist der 256. Tag des Jahres 2024?", "**Donnerstag, der 12.09.2024**"),
    (5, "Welcher Tag ist der 366. Tag des Jahres 2026?", "nur 365 Tage"),
    (5, "Der wievielte Tag im Jahr ist heute?", "der **329. Tag**"),
    (6, "In welcher Kalenderwoche ist Weihnachten?", "**KW 52**"),
    (6, "In welcher KW ist Ostern 2027?", "**KW 12**"),
    (7, "Wann ist der 2. Advent?", "**Sonntag, 06.12.2026**"),
    (7, "Wann ist der dritte Advent 2027?", "**Sonntag, 12.12.2027**"),
    (8, "Wann ist Mariä Himmelfahrt?", "**Sonntag, 15.08.2027**"),
    (8, "Wann ist Christi Himmelfahrt?", "**Donnerstag, 06.05.2027**"),
    (9, "Wann ist Ostern 1583?", "**10.04.1583**"),
    (9, "Wann ist Ostern 3000?", "**13.04.3000**"),
    (9, "Wann war Ostern 1500?", "1583 bis 9999"),
    (10, "Wie spät ist es in Kathmandu?", "4 Stunden und 45 Minuten mehr"),
    (10, "Wie spät ist es in Tokio?", "8 Stunden mehr"),
    (11, "Wann ist Vollmond?", "Heute ist **Vollmond 🌕**. Der nächste ist etwa **in 28 Tagen**"),
    (11, "Ist heute Vollmond?", "Ja, heute ist **Vollmond 🌕**"),
    (12, "Wie ist das Wetter in der Türkei?", "**Heute in der Türkei:**"),
    (12, "Was soll ich heute in der Türkei anziehen?", "in der **Türkei**"),
    (14, "Wann ist Allerheiligen?", "**Montag, 01.11.2027**"),
    (14, "Wann ist der Buß- und Bettag 2026?", "**Mittwoch, 18.11.2026**"),
    (14, "Wann ist Totensonntag 2026?", "**Sonntag, 22.11.2026**"),
    (14, "Wann ist Volkstrauertag 2026?", "**Sonntag, 15.11.2026**"),
    (14, "Wann ist Erntedank 2026?", "**Sonntag, 04.10.2026**"),
    (14, "Wann ist Heilige Drei Könige?", "**Mittwoch, 06.01.2027**"),
    (15, "Wie viele Stunden Zeitunterschied sind zwischen Berlin und Tokio?", "**8 Stunden**"),
    (16, "Was ist 3! + 4!", "**30**"),
    (16, "Was ist 101! + 1", "Fakultäten rechne ich bis 100"),
    (17, "Was ist pi mal 2?", "**6,283185**"),
    (17, "Was ist 1e3 + 1?", "**1.001**"),
    (18, "Was ist sin(30)?", "**0,5**"),
    (18, "Was ist ln(e)?", "**1**"),
    (18, "Was ist der Logarithmus von 100?", "**2**"),
    (18, "Was ist der Sinus von 90?", "**1**"),
    (19, "Was ist der Rest von 17 durch 5?", "**3 Rest 2**"),
    (19, "17 durch 5 mit Rest", "**3 Rest 2**"),
    (20, "Runde 3,14159 auf zwei Stellen", "Gerundet: **3,14**"),
    (20, "Runde 2,5", "Gerundet: **3**"),
    (20, "3,456 auf zwei Stellen runden", "Gerundet: **3,46**"),
    (70, "Runde 1234 auf Hunderter", "Gerundet: **1.200**"),
    (70, "Runde 1234,5 auf volle Zehner", "Gerundet: **1.230**"),
    (21, "100 Euro netto plus 7 % Mehrwertsteuer",
     "**7,00 €** Mehrwertsteuer (7 %, brutto 107,00 €)"),
    (21, "119 Euro brutto, wie viel MwSt?", "**19,00 €**"),
    (22, "1000 Wattstunden in Watt", "Wattstunden ist eine Energie, Watt ist eine Leistung"),
    (22, "1000 Wattstunden in kWh", "**1 kWh**"),
    (22, "1 kWh in Joule", "**3.600.000 Joule**"),
    (22, "1 kg in Meter", "Das geht nicht"),
    (23, "2 Esslöffel in ml", "**30 ml**"),
    (23, "1 Acre in Quadratmeter", "**4.046,8564 Quadratmeter**"),
    (23, "8 Bit in Byte", "8 Bit sind **1 Byte**"),
    (23, "1 bar in psi", "**14,5038 psi**"),
    (23, "1 Lichtjahr in km", "**9.460.730.472.581 km**"),
    (24, "1024 Byte in KiB", "1.024 Byte sind **1 KiB**"),
    (25, "1 Ar in Quadratmeter", "1 Ar ist"),
    (26, "5 feet 10 inches in cm", "70 inches is **177.8 cm**"),
    (26, "6 Fuß 2 Zoll in cm", "**187,96 cm**"),
    (27, 'Kehre "abc" um', "**cba**"),
    (28, "Sortiere: Banane, Apfel, Kirsche", "**Apfel, Banane, Kirsche**"),
    (29, 'Wie viele Vokale hat "Banane"?', "**3 Vokale**"),
    (29, 'Zähle das e in "Erdbeere"', "**4-mal**"),
    (30, "Wie viele Wochen hat das Jahr 2026?", "**53 Kalenderwochen**"),
    (31, "Wie viele Stunden bis Mitternacht?", "**13 Stunden und 30 Minuten**"),
    (32, "Wann ist der nächste Freitag der 13.?", "**13.08.2027**"),
    (33, "Wie viele Tage hat dieses Jahr noch?", "**36 Tage**"),
    # Ohne "noch" ist die Laenge gemeint -- und "das Jahr 2028" ging schon in 17.1.0.
    (33, "Wie viele Tage hat das Jahr?", "Das Jahr 2026 hat **365 Tage**."),
    (33, "Wie viele Tage hat das Jahr 2028?", "Das Jahr 2028 hat **366 Tage**."),
    (34, "Wie viele Tage sind seit Neujahr vergangen?", "**328 Tage**"),
    (35, "Ist heute Wochenende?", "Nein, heute ist **Mittwoch"),
    (35, "Ist morgen Donnerstag?", "Ja, morgen ist **Donnerstag"),
    (36, "Welche Zeitzone hat Tokio?", "**Asia/Tokyo** (gerade UTC+9)"),
    (36, "Welche Zeitzone hat Kathmandu?", "UTC+5:45"),
    (36, "Welche Zeitzone haben wir?", "**MEZ** (UTC+1)"),
    (37, "Wie lange ist der Tag heute in Berlin?", "8 Stunden und 17 Minuten lang"),
    (39, "Wie windig wird es morgen in Hamburg?", "bis zu **9 km/h**"),
    (39, "Wie windig wird es am Samstag in Hamburg?", "**55 km/h** – ein starker Wind"),
    (40, "Wie hoch ist der UV-Index in Paris?", "Der UV-Index liegt bei **1** (niedrig)"),
    (41, "Ist es in Dubai gerade heiß?", "**Heute in Dubai:**"),
    (41, "Ist es gesund, wenn es warm ist?", "ohne Sprachmodell"),
    (43, "Average of 1, 2, 3, 4", "The average of 4 numbers is **2.5**"),
    (43, "5 factorial", "5! = **120**"),
    (43, "100 euros in dollars", "100 EUR is **108.23 USD**"),
    (43, "100 eur to usd", "100 EUR is **"),
    (43, "Square root of 2", "**1.414214**"),
    (43, "100 Euro in Dollar", "100 EUR sind **108,23 USD**"),
    (44, "Will it rain in Paris this weekend?", "**Paris** · saturday: "),
    (45, "What should I wear in Madrid today?", "I'd wear a warm jacket"),
    (46, "When does the sun set in Paris?", "sets at **16:05**"),
    (47, "What time is sunrise in Madrid tomorrow?", "**Madrid** · tomorrow: the sun rises"),
    (48, "How hot will it be on Saturday in Dubai?", "**Dubai** · saturday: "),
    (48, "Is it hot in Dubai?", "**Dubai** · today: "),
    (48, "How warm is it in Paris today?", "**Paris** · today: "),
    (48, "Will it be cold tomorrow in Paris?", "**Paris** · tomorrow: "),
    (48, "Is it healthy when it is warm?", "Sorry"),
    (49, "Weather forecast for the next 7 days in Tokio", "**Tokio** · friday: "),
    (50, "How windy is it in Hamburg?", "wind up to 18 km/h"),
    (51, "Time difference between Berlin and Kathmandu", "**4 hours 45 minutes** ahead"),
    (52, "If it's 3 pm here, what time is it in New York?", "it's **09:00** in **New York**"),
    (53, "What time will it be in 3 hours?", "**13:30**"),
    (53, "What time was it 90 minutes ago?", "**09:00**"),
    (54, "What's 100 minus 15%?", "100 minus 15 % is **85** (difference: 15)"),
    (54, "What's my BMI if I'm 180 cm and 75 kg?", "Your BMI is **23.1**"),
    (55, "What percent of 120 is 30?", "**25 %**"),
    (56, "What is the greatest common divisor of 12 and 18?", "**6**"),
    (56, "What is the least common multiple of 4 and 6?", "**12**"),
    (57, "What is 255 in binary?", "**11111111**"),
    (57, "What is 2026 in Roman numerals?", "**MMXXVI**"),
    (57, "What is MMXXVI in numbers?", "**2,026**"),
    (58, "How many days until Easter?", "**123 days**"),
    (59, "How many days since January 1, 2026?", "**328 days**"),
    (60, "When is Halloween?", "**Sunday, October 31, 2027**"),
    (60, "When is Thanksgiving?", "**Thursday, November 26, 2026**"),
    (60, "When is the first day of winter?", "**Monday, December 21, 2026**"),
    (60, "When do the clocks change?", "**Sunday, March 28, 2027**"),
    (61, "Is today a holiday?", "**Christmas Day**"),
    (61, "What holidays are in December?", "**Boxing Day:**"),
    (62, "How old is someone born on 5 May 1990?", "**36 years**"),
    (63, "Generate a password with 16 characters", "Here's a random password with 16 characters"),
    (64, "Pick a random number between 1 and 100", "Your random number between 1 and 100"),
    (66, "When is the next full moon?", "The next full moon is in about **28 days**"),
    (68, "I feel sad", "I'm sorry to hear that"),
    # Gleitkomma: keine erfundenen Ziffern, keine 0 fuer winzige Ergebnisse.
    (147, "1,5 * 10^30", "**1,5 · 10³⁰**"),
    (147, "10^30 / 3", "**3,333333 · 10²⁹**"),
    (148, "1/7000000", "**1,428571 · 10⁻⁷**"),
    (148, "1 Gramm in Tonnen", "**1 · 10⁻⁶ Tonnen**"),
]


def test_english_jokes_quotes_and_news() -> None:
    # 65 und 67: Witz, Zitat und Nachrichten bekamen vorher "Sorry" oder deutsche Rahmentexte.
    assert frag("Tell me a joke") in standard._WITZE_EN
    assert frag("Give me a quote") in standard._ZITATE_EN
    nachrichten = standard._antwort("News", [], holen=lambda url: {"news": [
        {"title": "A", "shareURL": "https://www.tagesschau.de/a"}]} if "tagesschau" in url
        else None, jetzt=JETZT)
    assert "**Top news from tagesschau.de (in German):**" in nachrichten
    assert "Source:" in nachrichten and "Quelle" not in nachrichten


def test_english_weather_for_two_places_names_the_source_once() -> None:
    # 69: Die Quelle stand vorher nach jedem Ort.
    antwort = frag("Weather in Berlin and Paris")
    assert antwort.count("Source: [Open-Meteo]") == 1
    assert antwort.startswith("**Berlin** · today: ") and "**Paris** · today: " in antwort


def test_rounding_to_millions_is_not_guessed() -> None:
    # 70: Eine unbekannte Stelle ("auf Millionen") wird nicht still zur ganzen Zahl.
    assert "Gerundet" not in frag("Runde 1234 auf Millionen")


def test_small_talk_in_english_with_a_language_model() -> None:
    # 13: Mit einem Sprachmodell bekam "Thanks" vorher "Keine Ursache!" (deutsch).
    from aquaticy import agent as agent_mod

    class Modell:
        _plugin_turn = False
        secure_pro = False

        def _standard_model(self) -> bool:
            return False

    assert agent_mod.smalltalk_fuer(Modell(), "Thanks") == "You're welcome!"
    assert agent_mod.smalltalk_fuer(Modell(), "Good night") == "Good night! Sleep well."
    assert agent_mod.smalltalk_fuer(Modell(), "hola") == ""
    assert agent_mod.smalltalk_fuer(Modell(), "Danke") not in ("", "You're welcome!")


def test_follow_up_time_question() -> None:
    # 38: "Und in Tokio?" nach "Wie spät ist es?" -- vorher "kann ich nicht".
    vorher = [{"role": "user", "content": "Wie spät ist es?"},
              {"role": "assistant", "content": "Es ist **10:30 Uhr** (MEZ)."}]
    assert "In **Tokio** ist es gerade **18:30 Uhr**" in frag("Und in Tokio?", verlauf=vorher)
    wetter = [{"role": "assistant", "content": "**Heute in Berlin:** klar"}]
    assert "in Hamburg" in frag("und in Hamburg?", verlauf=wetter)


def test_moon_knowledge_goes_to_wikipedia() -> None:
    # 42: "Erzähl mir etwas über den Mond" bekam vorher die Mondphase.
    assert standard.mond("Erzähl mir etwas über den Mond", JETZT.date()) == ""
    assert "Vollmond" in standard.mond("Welche Mondphase haben wir?", JETZT.date())


@pytest.mark.parametrize(("nr", "frage", "teil"), STANDARD,
                         ids=[f"{n}-{f[:30]}" for n, f, _ in STANDARD])
def test_standard_answers(nr: int, frage: str, teil: str) -> None:
    assert teil in frag(frage), (nr, frag(frage))
