"""15.8.9: Aquaticy Standard antwortet ohne Sprachmodell -- ohne Netz getestet."""

from __future__ import annotations

import datetime
import random
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from aquaticy import standard
from aquaticy.config import STANDARD_MODEL_ID, Settings, model_problem

JETZT = datetime.datetime(2026, 11, 9, 17, 30, tzinfo=ZoneInfo("Europe/Berlin"))


def holen(url: str) -> Any:
    if "geocoding" in url:
        ort = "Bremen" if "Bremen" in url else "Berlin"
        return {"results": [{"name": ort, "latitude": 52.5, "longitude": 13.4}]}
    if "forecast" in url:
        return {"daily": {"weather_code": [61, 0, 3], "temperature_2m_max": [9.4, 11, 8],
                          "temperature_2m_min": [3.1, 4, 2],
                          "precipitation_probability_max": [70, 10, 20]},
                "current": {"temperature_2m": 7.2}}
    if "frankfurter" in url:
        return {"date": "2026-11-09", "rates": {"USD": 1.0823}}
    if "tagesschau" in url:
        return {"news": [{"title": "Meldung A", "shareURL": "https://www.tagesschau.de/a"},
                         {"title": "Meldung [B]"}]}
    if "opensearch" in url:
        return ["Eiffelturm", ["Eiffelturm"], [""], [""]]
    if "summary" in url:
        return {"title": "Eiffelturm", "extract": "Der Eiffelturm ist 330 Meter hoch. Er steht "
                "in Paris. Er wurde 1889 gebaut. Noch ein Satz.",
                "content_urls": {"desktop": {"page": "https://de.wikipedia.org/wiki/Eiffelturm"}}}
    return None


def frag(text: str, **kwargs: Any) -> str:
    kwargs.setdefault("holen", holen)
    return standard.antwort(text, jetzt=JETZT, wuerfel=random.Random(1), **kwargs)


@pytest.mark.parametrize(("frage", "teil"), [
    ("Was ist 12 * (3 + 4)?", "**84**"),
    ("Wie viel ist 2 hoch 10", "**1.024**"),
    ("19 % von 250", "**47,5**"),
    ("200 plus 19 %", "**238**"),
    ("119 € brutto in netto", "**100 € netto**"),
    ("5 km in Meilen", "**3,1069 Meilen**"),
    ("100 Fahrenheit in Celsius", "**37,78 °C**"),
    ("3 GB in MB", "**3.000 MB**"),
    ("Wie spät ist es?", "**17:30 Uhr**"),
    ("Welcher Tag ist heute?", "Montag, der 09.11.2026"),
    ("Wie viele Tage bis Weihnachten?", "**45 Tage**"),
    ("Welcher Wochentag ist der 3.10.2027?", "**Sonntag**"),
    ("Wann ist Ostern?", "28.03.2027"),
    ("Wetter in Berlin", "**Heute in Berlin:**"),
    ("Wird es morgen in Berlin regnen?", "**Morgen in Berlin:**"),
    ("100 Euro in Dollar", "**108,23 USD**"),
    ("Nachrichten", "[Meldung A](https://www.tagesschau.de/a)"),
    ("Was ist der Eiffelturm?", "Quelle: [Wikipedia](https://de.wikipedia.org/wiki/Eiffelturm)"),
    ("Würfel", "🎲"),
    ("Soll ich Pizza oder Pasta essen?", "**P"),
])
def test_answers_without_a_language_model(frage: str, teil: str) -> None:
    assert teil in frag(frage)


def test_sources_are_named() -> None:
    assert "Quelle: [Open-Meteo]" in frag("Wetter in Berlin")
    assert "Europäische Zentralbank" in frag("100 Euro in Dollar")


def test_follow_up_weather_question() -> None:
    vorher = [{"role": "assistant", "content": "**Heute in Berlin:** klar"}]
    assert "**Morgen in Berlin:**" in frag("und morgen?", verlauf=vorher)


def test_unknown_questions_are_honest_and_point_to_the_other_models() -> None:
    antwort = frag("Wie geht es dem Universum?")
    assert "ohne Sprachmodell" in antwort and "Modell-Auswahl" in antwort
    assert "Was kannst du?" in antwort


def test_weather_without_a_place_uses_the_home_town() -> None:
    assert "**Heute in Bremen:**" in frag("Wie wird das Wetter?", wohnort="Bremen")
    assert standard.ORT_FRAGE in frag("Wie wird das Wetter?")


def test_it_confirms_what_it_remembered() -> None:
    antwort = frag("Ich wohne in Bremen.", gemerkt=["Wohnt in Bremen."])
    assert "merke ich mir" in antwort and "Wohnt in Bremen." in antwort


def test_secure_pro_answers_from_fixed_knowledge() -> None:
    assert "RDP" in frag("Was ist Port 3389?", secure=True)
    assert "Phishing" in frag("Wie erkenne ich Phishing?", secure=True)


def test_only_fixed_public_hosts_are_fetched() -> None:
    assert standard.holen_json("https://example.com/x") is None
    assert standard.holen_json("http://de.wikipedia.org/x") is None
    assert standard.holen_json("https://169.254.169.254/latest") is None


def test_the_model_is_known_and_usable() -> None:
    from aquaticy.system import model_usable

    assert STANDARD_MODEL_ID == standard.MODEL_ID == "aquaticy/standard"
    assert model_problem(STANDARD_MODEL_ID) == ""
    assert model_usable(Settings(), STANDARD_MODEL_ID)


def test_the_agent_answers_with_standard_and_never_calls_litellm(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy.agent import Agent
    from aquaticy.cache import Cache

    monkeypatch.setattr(standard, "holen_json", holen)

    def nie(**_kw: Any) -> None:
        raise AssertionError("LiteLLM darf nicht gerufen werden")

    monkeypatch.setattr("litellm.completion", nie)
    settings = Settings(model=STANDARD_MODEL_ID, data_dir=tmp_path / "d", memory_enabled=True,
                        enable_playwright=False, subagents_auto=False,
                        request_delay_seconds=0.0)
    agent = Agent(settings, cache=Cache(settings.db_path))
    assert agent.ask("Was ist 2 + 3?", stream=False).answer == "**5**"
    assert "merke ich mir" in agent.ask("Ich wohne in Bremen.", stream=False).answer
    assert "**Heute in Bremen:**" in agent.ask("Wie wird das Wetter?", stream=False).answer
    agent.ask("Ich heiße Louis.", stream=False)
    assert agent.ask("Wie heiße ich?", stream=False).answer == "Du heißt Louis."


def test_the_header_names_the_model() -> None:
    from aquaticy import web

    assert web.header_for(Settings(model=STANDARD_MODEL_ID))["model_label"] == "Aquaticy Standard"


def test_the_model_picker_offers_standard_next_to_the_other_models() -> None:
    """15.8.9: Aquaticy Standard ist eine Wahl in der Modell-Auswahl -- nicht die Voreinstellung."""
    from aquaticy import web

    quelle = Path(web.__file__).read_text(encoding="utf-8")
    teil = quelle[quelle.index('elif route == "/api/models"'):]
    teil = teil[:teil.index('elif route == "/api/memory"')]
    assert '{"id": STANDARD_MODEL_ID, "label": standard_mod.LABEL, "kind": "Standard"' in teil
    assert Settings().model != STANDARD_MODEL_ID


def test_small_talk_is_still_answered_without_any_model(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hallo, Danke und Co. beantwortet weiter die feste Schicht -- mit jedem Modell."""
    from aquaticy import smalltalk
    from aquaticy.agent import Agent
    from aquaticy.cache import Cache

    def nie(**_kw: Any) -> None:
        raise AssertionError("LiteLLM darf nicht gerufen werden")

    monkeypatch.setattr("litellm.completion", nie)
    for modell in (STANDARD_MODEL_ID, "mistral/mistral-large-latest"):
        settings = Settings(model=modell, data_dir=tmp_path / modell.replace("/", "_"),
                            memory_enabled=False, enable_playwright=False,
                            subagents_auto=False, request_delay_seconds=0.0)
        agent = Agent(settings, cache=Cache(settings.db_path))
        antwort = agent.ask("Hallo", stream=False).answer
        assert antwort and "ohne Sprachmodell" not in antwort
        assert smalltalk.antwort("Hallo")


# -- Gespraechsspeicher und neue Antworten ---------------------------------------------

def gespraech(*fragen: str) -> list[str]:
    verlauf: list[dict[str, Any]] = []
    antworten = []
    for text in fragen:
        antwort = frag(text, verlauf=verlauf)
        verlauf += [{"role": "user", "content": text}, {"role": "assistant", "content": antwort}]
        antworten.append(antwort)
    return antworten


def test_the_place_after_the_question_answers_the_open_question() -> None:
    """Nach "Fuer welchen Ort?" reicht "Erkelenz" als Antwort."""
    frage, ort = gespraech("wie wird das wetter heute", "Erkelenz")
    assert standard.ORT_FRAGE in frage
    assert "**Heute in Bremen:**" not in ort and "Heute in" in ort
    assert "ohne Sprachmodell" not in ort


def test_the_last_place_counts_for_the_next_questions() -> None:
    antworten = gespraech("Wetter in Berlin", "was soll ich anziehen?", "und morgen?",
                          "brauche ich morgen einen Schirm?")
    assert "in **Berlin**" in antworten[1] and "zieh am besten" in antworten[1]
    assert "**Morgen in Berlin:**" in antworten[2]
    assert "Für morgen in **Berlin**" in antworten[3] and "Schirm" in antworten[3]


def test_clothing_advice_asks_for_the_place_first() -> None:
    frage, rat = gespraech("Was soll ich heute anziehen?", "in Bremen")
    assert standard.ORT_FRAGE in frage and "Anziehen" in frage
    assert "in **Bremen**" in rat and "zieh am besten" in rat


def test_a_normal_question_is_not_taken_for_a_place() -> None:
    _, rechnung = gespraech("Wie wird das Wetter?", "Was ist 2 + 3?")
    assert rechnung == "**5**"


@pytest.mark.parametrize(("frage", "teil"), [
    ("Wann geht die Sonne unter in Berlin?", "Sonne"),
    ("Wie wird das Wetter die nächsten Tage in Berlin?", "Die nächsten Tage in Berlin"),
    ("Wann ist der nächste Feiertag?", "1. Weihnachtstag"),
    ("Wann ist Pfingstmontag?", "Pfingstmontag"),
    ("Ist heute Vollmond?", "Vollmond"),
    ("Ich bin am 3.5.1990 geboren. Wie alt bin ich?", "**36 Jahre**"),
    ("15 % Trinkgeld auf 42 Euro", "**6,30 €**"),
    ("BMI 80 kg 1,80 m", "**24,7**"),
    ("Mir ist langweilig", "Ideen"),
    ("Erzähl mir einen Fun Fact", "Wusstest du schon?"),
    ("Was kannst du?", "ohne Sprachmodell"),
])
def test_new_answers(frage: str, teil: str) -> None:
    assert teil in frag(frage)


def test_a_password_is_random_long_and_mixed() -> None:
    import re

    antwort = frag("Generiere ein Passwort mit 16 Zeichen")
    wort = re.search(r"`([^`]+)`", antwort)
    assert wort and len(wort[1]) == 16
    assert any(c.isupper() for c in wort[1]) and any(c.isdigit() for c in wort[1])
    assert frag("Generiere ein Passwort") != antwort


def test_the_time_in_another_city() -> None:
    def mit_zone(url: str) -> Any:
        if "geocoding" in url:
            return {"results": [{"name": "New York", "timezone": "America/New_York"}]}
        return holen(url)

    antwort = frag("Wie spät ist es in New York?", holen=mit_zone)
    assert "**11:30 Uhr**" in antwort and "6 Stunden weniger" in antwort


def test_the_weekend_forecast() -> None:
    def sieben_tage(url: str) -> Any:
        if "forecast" in url:
            return {"daily": {"weather_code": [61, 0, 3, 1, 2, 0, 63],
                              "temperature_2m_max": [9, 11, 8, 10, 12, 14, 7],
                              "temperature_2m_min": [3, 4, 2, 3, 5, 6, 2],
                              "precipitation_probability_max": [70, 10, 20, 5, 10, 0, 80]}}
        return holen(url)

    antwort = frag("Wetter in Berlin am Wochenende", holen=sieben_tage)
    assert "**Das Wochenende in Berlin:**" in antwort
    assert "**Sa 14.11.:**" in antwort and "**So 15.11.:**" in antwort
    assert "Am schönsten wird es wohl" in antwort


def test_a_new_home_town_wins_over_the_last_place() -> None:
    verlauf = [{"role": "user", "content": "Wetter in Berlin"},
               {"role": "assistant", "content": frag("Wetter in Berlin")},
               {"role": "user", "content": "Ich wohne in Bremen."},
               {"role": "assistant", "content": "Alles klar, das merke ich mir."}]
    assert "in Bremen:**" in frag("Wie wird das Wetter morgen?", verlauf=verlauf, wohnort="Bremen")


# -- Grenzfaelle und weitere Antworten ------------------------------------------------

def test_the_weekend_works_without_the_word_weather() -> None:
    """"Wie wird das Wochenende?" ist eine Wetterfrage, auch ohne das Wort Wetter."""
    def sieben_tage(url: str) -> Any:
        if "forecast" in url:
            return {"daily": {"weather_code": [61, 0, 3, 1, 2, 0, 63],
                              "temperature_2m_max": [9, 11, 8, 10, 12, 14, 7],
                              "temperature_2m_min": [3, 4, 2, 3, 5, 6, 2],
                              "precipitation_probability_max": [70, 10, 20, 5, 10, 0, 80]}}
        return holen(url)

    verlauf = [{"role": "user", "content": "Wetter in Berlin"},
               {"role": "assistant", "content": frag("Wetter in Berlin")}]
    antwort = frag("Wie wird das Wochenende?", verlauf=verlauf, holen=sieben_tage)
    assert "**Das Wochenende in Berlin:**" in antwort


@pytest.mark.parametrize("satz", ["Mir geht es nicht gut", "mir gehts schlecht",
                                  "Ich bin so traurig", "ich fühle mich einsam"])
def test_feeling_bad_gets_comfort_and_the_helpline(satz: str) -> None:
    antwort = frag(satz)
    assert "Das tut mir leid" in antwort and "0800 111 0 111" in antwort


@pytest.mark.parametrize("ausweichen", ["keine Ahnung", "weiß nicht", "egal", "vergiss es"])
def test_a_non_place_is_not_looked_up_as_a_place(ausweichen: str) -> None:
    gesehen: list[str] = []

    def zaehlen(url: str) -> Any:
        gesehen.append(url)
        return holen(url)

    verlauf = [{"role": "user", "content": "Wie wird das Wetter?"},
               {"role": "assistant", "content": frag("Wie wird das Wetter?")}]
    antwort = frag(ausweichen, verlauf=verlauf, holen=zaehlen)
    assert "Kein Problem" in antwort and not gesehen


def test_a_question_is_not_taken_for_a_place_after_the_place_question() -> None:
    verlauf = [{"role": "user", "content": "Wie wird das Wetter?"},
               {"role": "assistant", "content": frag("Wie wird das Wetter?")}]
    assert standard.ORT_FRAGE in frag("brauche ich einen Schirm", verlauf=verlauf)


def test_at_my_place_means_the_home_town_not_a_place_called_mir() -> None:
    assert standard.ORT_FRAGE in frag("Wetter bei mir")
    assert "in Bremen" in frag("Wie ist das Wetter bei mir?", wohnort="Bremen")
    verlauf = [{"role": "user", "content": "Wetter"},
               {"role": "assistant", "content": frag("Wetter")}]
    assert "weiß leider nicht, wo du gerade bist" in frag("hier", verlauf=verlauf)


@pytest.mark.parametrize(("frage", "gesucht"), [
    ("Wie wird das Wetter in Frankfurt am Main morgen?", "Frankfurt%20am%20Main"),
    ("Regnet es heute in München?", "M%C3%BCnchen"),
    ("Wie ist das Wetter im Moment in Bad Honnef?", "Bad%20Honnef"),
    ("Wie spät ist es in Köln?", "K%C3%B6ln"),
])
def test_places_keep_their_spelling_for_the_lookup(frage: str, gesucht: str) -> None:
    """Nicht "frankfurt main" und "muenchen": Der Wetterdienst bekommt die echte Schreibweise."""
    gesehen: list[str] = []

    def merken(url: str) -> Any:
        gesehen.append(url)
        if "geocoding" in url:
            return {"results": [{"name": "X", "latitude": 1, "longitude": 1,
                                 "timezone": "Europe/Berlin"}]}
        return holen(url)

    frag(frage, holen=merken)
    assert any(url.endswith("name=" + gesucht) for url in gesehen), gesehen


def test_an_unreachable_service_is_not_reported_as_an_unknown_place() -> None:
    antwort = frag("Wetter in Berlin", holen=lambda url: None)
    assert antwort == standard.NICHT_ERREICHBAR and "finde ich nicht" not in antwort
    unbekannt = frag("Wetter in Xyzqw", holen=lambda url: {"generationtime_ms": 1})
    assert "einen Ort namens „Xyzqw“ finde ich nicht" in unbekannt


def test_and_in_another_place_keeps_the_day_of_the_latest_answer() -> None:
    """Nach Fragen zu heute (auch zum Schirm) gilt "und in Bremen?" fuer heute."""
    antworten = gespraech("Wetter in Berlin", "und morgen?", "brauche ich einen Schirm?",
                          "und in Bremen?")
    assert "**Morgen in Berlin:**" in antworten[1]
    assert "Für heute in **Berlin**" in antworten[2]
    assert "**Heute in Bremen:**" in antworten[3]


def test_several_places_are_compared() -> None:
    antwort = frag("Wie ist das Wetter in Berlin und in Bremen?")
    assert "**Heute in Berlin:**" in antwort and "**Heute in Bremen:**" in antwort
    assert antwort.count("Open-Meteo") == 1


@pytest.mark.parametrize(("frage", "teil"), [
    ("Wurzel aus 144", "**12**"),
    ("1/0", "Durch null kann man nicht teilen"),
    ("2^1000", "zu groß"),
    ("Ist morgen ein Feiertag?", "Nein, morgen ist kein bundesweiter Feiertag"),
    ("Ist der 25.12. ein Feiertag?", "Ja, der 25.12.2026 ist **1. Weihnachtstag**"),
    ("Wann ist Muttertag?", "**Sonntag, 09.05.2027**"),
    ("Wie viele Tage bis Halloween?", "31.10.2027"),
    ("Wann ist der 1. Advent?", "**Sonntag, 29.11.2026**"),
    ("Wann ist die Zeitumstellung?", "**Sonntag, 28.03.2027**"),
    ("Wann ist Pfingsten?", "16.05.2027"),
    ("Ist 97 eine Primzahl?", "Ja, **97** ist eine Primzahl"),
    ("Ist 91 eine Primzahl?", "7 × 13"),
    ("Ist 2028 ein Schaltjahr?", "Ja, **2028**"),
    ("2024 in römischen Zahlen", "**MMXXIV**"),
    ("MMXXIV als Zahl", "**2024**"),
    ("255 in binär", "**11111111**"),
    ("255 in hex", "**FF**"),
    ("Durchschnitt von 3, 5 und 10", "**6**"),
    ("Welches Sternzeichen ist der 3. Mai?", "Stier"),
    ("Wie viele Buchstaben hat Donaudampfschiff?", "**16 Buchstaben**"),
    ("Schreib Lagerregal rückwärts", "lagerregaL"),
    ("Buchstabiere Mut", "M – U – T"),
    ("Was soll ich heute kochen?", "Guten Appetit"),
    ("Erzähl mir ein Rätsel", "Lösung"),
    ("Sag mir einen Zungenbrecher", "dreimal schnell"),
])
def test_answers_new_in_1603(frage: str, teil: str) -> None:
    assert teil in frag(frage)


def test_a_or_b_without_soll_ich() -> None:
    assert frag("Pizza oder Pasta?") in ("Ich würde sagen: **Pizza**.",
                                         "Ich würde sagen: **Pasta**.")
    assert "Meine Antwort: **" in frag("Ja oder nein?")
    # Eine Wetterfrage mit "oder" bleibt eine Wetterfrage.
    assert standard.ORT_FRAGE in frag("Regnet es heute oder morgen?")


def test_a_knowledge_question_is_not_counted_as_text() -> None:
    assert "Zeichen**" not in frag("Wie viele Zeichen hat ein Tweet?")


def test_pro_and_code_use_the_strong_model_when_there_is_one(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aquaticy Standard ist das Modell fuer Normal. Pro und Code nehmen ein starkes Modell,
    wenn es eines gibt -- sonst antwortet auch dort Aquaticy Standard statt eines Fehlers."""
    from aquaticy.agent import Agent
    from aquaticy.cache import Cache

    settings = Settings(model=STANDARD_MODEL_ID, data_dir=tmp_path / "d", memory_enabled=False,
                        enable_playwright=False, subagents_auto=False,
                        request_delay_seconds=0.0)
    agent = Agent(settings, cache=Cache(settings.db_path))
    agent.mode = "code"
    monkeypatch.setattr(agent, "_strongest_model", lambda purpose="": "mistral/codestral-latest")
    assert not agent._standard_model()
    monkeypatch.setattr(agent, "_strongest_model", lambda purpose="": "")
    assert agent._standard_model()
    agent.mode = "normal"
    monkeypatch.setattr(agent, "_strongest_model", lambda purpose="": "mistral/codestral-latest")
    assert agent._standard_model()
