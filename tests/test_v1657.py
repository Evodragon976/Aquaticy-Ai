"""16.5.7: Fehlersuche -- Aquaticy Standard auf Englisch (in Aquaticy AI nur Fehler behoben)."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from aquaticy import standard

JETZT = datetime(2026, 11, 22, 15, 10, tzinfo=ZoneInfo("Europe/Berlin"))


def frag_standard(frage: str, holen: Any = None) -> str:
    return standard._antwort(frage, [], holen=holen or (lambda url: None), jetzt=JETZT)


@pytest.mark.parametrize("frage, erwartet", [
    ("What day is tomorrow?", "Tomorrow is **Monday, 23 November 2026**."),
    ("Which day is tomorrow?", "Tomorrow is **Monday, 23 November 2026**."),
    ("What day was yesterday?", "Yesterday was **Saturday, 21 November 2026**."),
    ("What day of the week is it?", "Today is **Sunday, 22 November 2026**."),
    ("What day is the day after tomorrow?",
     "The day after tomorrow is **Tuesday, 24 November 2026**."),
    ("What is tomorrow's date?", "Tomorrow is **Monday, 23 November 2026**."),
    ("How many days in 2028?", "2028 has **366 days**."),
    ("How many days does 2027 have?", "2027 has **365 days**."),
])
def test_english_day_questions_get_an_answer(frage: str, erwartet: str) -> None:
    # Vorher "Sorry, I can't answer that" -- auf Deutsch ging es.
    assert frag_standard(frage) == erwartet


def test_english_answers_that_worked_stay_the_same() -> None:
    assert frag_standard("What day is it?") == "Today is 2026-11-22."
    assert frag_standard("How many days are in February 2028?") == "February 2028 has **29 days**."
    assert frag_standard("What year is it?") == "It is **2026**."


@pytest.mark.parametrize("frage", ["What day will it rain in Berlin?",
                                   "Which day will it rain in Berlin?"])
def test_an_english_weather_question_finds_the_place(frage: str) -> None:
    # Vorher suchte Aquaticy den Ort "day Berlin".
    gefragt: list[str] = []

    def holen(url: str) -> None:
        gefragt.append(url)

    frag_standard(frage, holen)
    orte = [u.split("name=")[1].split("&")[0] for u in gefragt if "name=" in u]
    assert orte == ["Berlin"]
