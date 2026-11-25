"""16.6.7: Angriffe aus einer Liste geprueft (20 Punkte) und Fehlersuche."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from aquaticy import standard

JETZT = datetime(2026, 11, 24, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
UI = (Path(__file__).resolve().parent.parent / "aquaticy" / "webui.html").read_text(
    encoding="utf-8")


def frag(frage: str) -> str:
    return standard._antwort(frage, [], holen=lambda url: None, jetzt=JETZT)


def test_the_english_lookup_only_uses_own_entries() -> None:
    # Punkt 16 (Prototyp): "constructor" oder "toString" fanden sonst die Funktion von Object.
    kopf = UI.index("function aufEnglisch(")
    rumpf = UI[kopf:UI.index("\n}\n", kopf)]
    assert "Object.prototype.hasOwnProperty.call(EN, k)" in rumpf
    assert "if (EN[k] ||" not in rumpf


def test_the_month_without_a_name_is_this_month() -> None:
    assert frag("Wie viele Tage hat der Monat?") == "Der November 2026 hat **30 Tage**."
    assert frag("Wie viele Tage hat dieser Monat?") == "Der November 2026 hat **30 Tage**."
    assert frag("Wie viele Tage hat der Februar 2028?") == "Der Februar 2028 hat **29 Tage**."


@pytest.mark.parametrize("frage, erwartet", [
    ("Welcher Wochentag ist der 29.02.2027?",
     "Den 29.02.2027 gibt es nicht – 2027 ist kein Schaltjahr."),
    ("Welcher Wochentag ist der 31.04.2026?", "Den 31.04.2026 gibt es nicht."),
    ("Wie viele Tage bis zum 31.06.2027?", "Den 31.06.2027 gibt es nicht."),
    ("Welcher Wochentag ist der 29.02.2028?", "Der 29.02.2028 ist ein **Dienstag**."),
])
def test_a_date_that_does_not_exist_gets_a_hint(frage: str, erwartet: str) -> None:
    # Vorher: "Hm, das kann ich ohne Sprachmodell leider nicht beantworten."
    assert frag(frage) == erwartet
