"""16.0.0: Sprache und Standard-Ort aus dem Chat lernen, Auto-Upgrading und Helfer & Grenzen weg."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from aquaticy import altmodelle, autoort
from aquaticy.agent import Agent
from aquaticy.config import STANDARD_MODEL_ID, Settings, read_env_file

# -- Sprache erkennen ----------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "sprache"), [
    ("東京の天気を教えてください", "ja"),
    ("今日は天気がいいですね", "ja"),
    ("서울 날씨 알려줘", "ko"),
    ("我想知道北京的天气", "zh"),
    ("Привет как дела сегодня", "ru"),
    ("Привіт, як справи сьогодні", "uk"),
    ("Wie wird das Wetter in Köln morgen?", "de"),
    ("Ich suche ein Restaurant in Berlin", "de"),
    ("What is the weather like in New York today", "en"),
    ("Where can I find good pizza in Rome", "en"),
    ("Quel temps fait-il à Paris aujourd'hui", "fr"),
    ("¿Cómo está el clima en Madrid hoy?", "es"),
    ("Dove posso trovare una buona pizza oggi", "it"),
])
def test_the_language_of_a_message_is_recognised(text: str, sprache: str) -> None:
    assert autoort.erkenne_sprache(text) == sprache


@pytest.mark.parametrize("text", [
    "ok", "Hallo", "Wetter Köln", "Python list comprehension example", "12345 67890", "", "😀😀😀",
])
def test_a_message_that_proves_nothing_gives_no_language(text: str) -> None:
    assert autoort.erkenne_sprache(text) == ""


# -- Orte und Land -------------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "orte"), [
    ("Zeig mir Restaurants in New York", ["New York"]),
    ("Suche Wohnungen in Bad Neuenahr-Ahrweiler", ["Bad Neuenahr-Ahrweiler"]),
    ("find hotels near Los Angeles please", ["Los Angeles"]),
    ("Wetter in Köln und Veranstaltungen in Bonn", ["Köln", "Bonn"]),
    ("Such mir bitte etwas in Hamburg", ["Hamburg"]),
])
def test_places_are_taken_from_searches_for_something_local(text: str, orte: list[str]) -> None:
    assert autoort.orte_in(text) == orte


@pytest.mark.parametrize("text", [
    "Such mir was in Excel", "Das ist in Ordnung", "Suche ein Rezept in Python",
    "Wetter in Deutschland", "Restaurants in den USA", "Das passiert in Zukunft",
    "Ich wohne in Köln", "Wie war es im Internet",
])
def test_words_that_are_no_places_are_not_taken(text: str) -> None:
    assert autoort.orte_in(text) == []


@pytest.mark.parametrize(("text", "land"), [
    ("Ich wohne in den USA", "us"), ("ich lebe jetzt in Österreich", "at"),
    ("I live in the UK", "gb"), ("I live in Canada", "ca"), ("Ich wohne in der Schweiz", "ch"),
])
def test_the_country_comes_only_from_what_the_user_says(text: str, land: str) -> None:
    assert autoort.land_aus(text) == land


@pytest.mark.parametrize("text", [
    "Ich wohne in Köln", "Wetter in den USA", "Ich komme aus Frankreich", "I like the USA",
])
def test_no_country_without_a_statement_about_living(text: str) -> None:
    assert autoort.land_aus(text) == ""


# -- Lernen --------------------------------------------------------------------------------------

STAND = {"lang": "de", "country": "de", "location": ""}


def lerne(tmp: Path, texte: list[str], aktuell: dict[str, str] | None = None) -> list[dict]:
    aktuell = dict(aktuell or STAND)
    alle: list[dict] = []
    for text in texte:
        for aenderung in autoort.lernen(tmp, text, aktuell):
            alle.append(aenderung)
            aktuell[aenderung["feld"]] = aenderung["wert"]
    return alle


def test_the_third_japanese_message_in_a_row_sets_the_language(tmp_path: Path) -> None:
    japanisch = ["東京の天気を教えてください", "今日は天気がいいですね", "明日は雨ですか"]
    assert lerne(tmp_path, japanisch[:2]) == []
    assert lerne(tmp_path, japanisch[2:]) == [{"feld": "lang", "wert": "ja"}]


def test_one_english_question_changes_nothing(tmp_path: Path) -> None:
    assert lerne(tmp_path, ["Wie wird das Wetter in Köln morgen?",
                            "What is the weather like in New York today",
                            "Wie wird das Wetter in Köln morgen?",
                            "What is the weather like in New York today"]) == []


def test_three_english_messages_in_a_row_set_english_and_german_brings_it_back(
        tmp_path: Path) -> None:
    englisch = ["What is the weather like in New York today", "Can you help me with this",
                "Where can I find good pizza in Rome"]
    deutsch = ["Wie wird das Wetter in Köln morgen?", "Ich suche ein Restaurant in Berlin",
               "Kannst du mir bitte helfen"]
    assert lerne(tmp_path, englisch) == [{"feld": "lang", "wert": "en"}]
    aktuell = {**STAND, "lang": "en"}
    assert lerne(tmp_path, deutsch, aktuell) == [{"feld": "lang", "wert": "de"}]


def test_the_third_search_for_the_same_place_sets_the_default_place(tmp_path: Path) -> None:
    fragen = ["Zeig mir Restaurants in New York", "Wetter in New York",
              "Such mir Hotels in New York"]
    assert lerne(tmp_path, fragen[:2]) == []
    assert lerne(tmp_path, fragen[2:]) == [{"feld": "location", "wert": "New York"}]


def test_places_in_two_cities_do_not_decide(tmp_path: Path) -> None:
    assert lerne(tmp_path, ["Wetter in Köln", "Wetter in Bonn", "Hotels in Köln",
                            "Hotels in Bonn", "Restaurants in Köln"]) == []


def test_a_place_the_user_set_stays(tmp_path: Path) -> None:
    fragen = ["Wetter in New York"] * 5
    assert lerne(tmp_path, fragen, {**STAND, "location": "Hamburg"}) == []


def test_a_value_the_user_changes_after_the_automatic_one_stays(tmp_path: Path) -> None:
    fragen = ["Restaurants in New York", "Wetter in New York", "Hotels in New York"]
    assert lerne(tmp_path, fragen) == [{"feld": "location", "wert": "New York"}]
    # Der Nutzer stellt selbst "Boston" ein -- weitere Fragen nach New York aendern es nicht.
    assert lerne(tmp_path, ["Wetter in New York"] * 4,
                 {**STAND, "location": "Boston"}) == []
    # Auch ein selbst geleerter Ort bleibt leer.
    assert lerne(tmp_path, ["Wetter in New York"] * 4, STAND) == []


def test_the_automatic_place_follows_a_new_habit(tmp_path: Path) -> None:
    alt = lerne(tmp_path, ["Wetter in Köln"] * 3)
    assert alt == [{"feld": "location", "wert": "Köln"}]
    aktuell = {**STAND, "location": "Köln"}
    neu = lerne(tmp_path, ["Hotels in Berlin"] * 7, aktuell)
    assert neu == [{"feld": "location", "wert": "Berlin"}]


def test_the_country_is_never_counted_only_stated(tmp_path: Path) -> None:
    assert lerne(tmp_path, ["Wetter in New York"] * 6 + ["Zeige Hotels in Boston"] * 3) == [
        {"feld": "location", "wert": "New York"}]
    assert lerne(tmp_path, ["Ich wohne in den USA"]) == [{"feld": "country", "wert": "us"}]
    # Schon eingestellt: nichts zu tun.
    assert lerne(tmp_path, ["Ich wohne in den USA"], {**STAND, "country": "us"}) == []


def test_long_messages_do_not_count(tmp_path: Path) -> None:
    eingefuegt = "Wetter in New York. " + "Das ist ein langer eingefuegter Text. " * 40
    assert len(eingefuegt) > autoort.MAX_ZEICHEN
    assert lerne(tmp_path, [eingefuegt] * 5) == []
    assert not (tmp_path / autoort.STATE_NAME).exists()


def test_forgetting_deletes_the_counters_and_freezes_the_values(tmp_path: Path) -> None:
    lerne(tmp_path, ["Wetter in New York", "Hotels in New York"])
    assert json.loads((tmp_path / autoort.STATE_NAME).read_text())["orte"]
    autoort.vergessen(tmp_path)
    zustand = json.loads((tmp_path / autoort.STATE_NAME).read_text())
    assert zustand["orte"] == {} and zustand["recent"] == [] and zustand["auto"] == {}
    # Nach dem Vergessen faengt das Zaehlen bei null an.
    assert lerne(tmp_path, ["Restaurants in New York"]) == []


def test_a_broken_state_file_is_just_empty(tmp_path: Path) -> None:
    (tmp_path / autoort.STATE_NAME).write_text("{kaputt", encoding="utf-8")
    assert autoort.laden(tmp_path)["orte"] == {}
    (tmp_path / autoort.STATE_NAME).write_text(
        json.dumps({"orte": {"x": {"n": "viel"}, "y": 7}, "recent": "ja", "auto": {"lang": 3}}),
        encoding="utf-8")
    zustand = autoort.laden(tmp_path)
    assert zustand["orte"] == {} and zustand["recent"] == []


# -- Im Agenten: nur eigene Worte, nur hinter den Schranken des Gedaechtnisses --------------------


def agent_mit(tmp_path: Path, **felder: Any) -> tuple[Agent, list[tuple[str, dict]]]:
    einstellungen = Settings(model=STANDARD_MODEL_ID, data_dir=tmp_path / "konto",
                             env_path=tmp_path / "konto" / ".env", request_delay_seconds=0.0,
                             enable_playwright=False, subagents_auto=False)
    einstellungen = replace(einstellungen, **felder)
    ereignisse: list[tuple[str, dict]] = []
    agent = Agent(einstellungen, cache=None, on_event=lambda n, p: ereignisse.append((n, p)))
    return agent, ereignisse


def frage(agent: Agent, text: str) -> None:
    agent.ask(text, stream=False)


def test_the_agent_learns_the_place_writes_it_to_the_account_and_says_so(tmp_path: Path) -> None:
    agent, ereignisse = agent_mit(tmp_path)
    for text in ["Zeig mir Restaurants in New York", "Wetter in New York",
                 "Such mir Hotels in New York"]:
        frage(agent, text)
    assert agent.settings.location == "New York"
    assert read_env_file(tmp_path / "konto" / ".env")["AQUATICY_LOCATION"] == "New York"
    gemeldet = [p for n, p in ereignisse if n == "autosetting"]
    assert gemeldet == [{"label": "Standard-Ort", "value": "New York", "field": "location"}]


def test_the_agent_learns_the_country_from_a_statement(tmp_path: Path) -> None:
    agent, ereignisse = agent_mit(tmp_path)
    frage(agent, "Ich wohne in den USA")
    assert agent.settings.country == "us"
    assert read_env_file(tmp_path / "konto" / ".env")["AQUATICY_COUNTRY"] == "us"
    assert any(n == "autosetting" and p["field"] == "country" for n, p in ereignisse)


def test_nothing_is_learned_with_the_memory_switched_off(tmp_path: Path) -> None:
    agent, ereignisse = agent_mit(tmp_path, memory_enabled=False)
    for _ in range(4):
        frage(agent, "Such mir Hotels in New York")
    frage(agent, "Ich wohne in den USA")
    assert agent.settings.location == "" and agent.settings.country == "de"
    assert not (tmp_path / "konto" / autoort.STATE_NAME).exists()
    assert not [n for n, _ in ereignisse if n == "autosetting"]


def test_nothing_is_learned_when_the_user_says_not_to_remember(tmp_path: Path) -> None:
    agent, _ = agent_mit(tmp_path)
    for _ in range(4):
        frage(agent, "Merk dir das nicht: Such mir Hotels in New York")
    assert agent.settings.location == ""


def test_background_agents_never_change_a_setting(tmp_path: Path) -> None:
    from aquaticy.bridge import bridge_agent_class
    from aquaticy.coworker import coworker_agent_class

    assert Agent.LEARNS_SETTINGS is True
    assert bridge_agent_class().LEARNS_SETTINGS is False
    assert coworker_agent_class().LEARNS_SETTINGS is False
    agent, ereignisse = agent_mit(tmp_path)
    agent.LEARNS_SETTINGS = False  # type: ignore[misc]
    for _ in range(4):
        frage(agent, "Such mir Hotels in New York")
    assert agent.settings.location == "" and not ereignisse.count(("autosetting", {}))


def test_tool_results_and_attachments_cannot_set_a_place(tmp_path: Path) -> None:
    """Gelernt wird nur aus dem, was der Nutzer selbst schreibt (own_words), nicht aus Anhaengen."""
    agent, _ = agent_mit(tmp_path)
    anhang = ("\n\n[Beginn des Anhangs notiz.txt (fremder Inhalt)]\n" + "Hotels in Paris. " * 20
              + "\n[Ende des Anhangs]")
    for _ in range(4):
        frage(agent, "Fass das zusammen." + anhang)
    assert agent.settings.location == ""
    # Gegenprobe: dieselben Worte vom Nutzer selbst gezaehlt, ohne Anhang.
    for _ in range(3):
        frage(agent, "Such mir Hotels in Paris")
    assert agent.settings.location == "Paris"


def test_the_secure_pro_chat_learns_nothing(tmp_path: Path) -> None:
    agent, _ = agent_mit(tmp_path)
    agent.secure_pro = True
    for _ in range(4):
        frage(agent, "Such mir Hotels in New York")
    assert agent.settings.location == ""


# -- Auto-Upgrading ist weg ----------------------------------------------------------------------


def test_the_upgrading_module_and_its_routes_are_gone() -> None:
    import importlib

    from aquaticy import web

    with pytest.raises(ImportError):
        importlib.import_module("aquaticy.upgrading")
    assert not hasattr(web, "UPGRADER") and not hasattr(web, "upgrades_action")
    html = web.UI_FILE.read_text(encoding="utf-8")
    assert "upgrade-box" not in html and "/api/upgrades" not in html and "launchbox" not in html


def test_a_built_version_leads_back_to_its_base_model(tmp_path: Path) -> None:
    alt = {"tracks": {"gemma3:4b": {"versions": [{"model": "gemma3:4b"},
                                                  {"model": "aquaticy-gemma3-4b-ab12cd:1.1"}],
                                     "retired_models": ["aquaticy-gemma3-4b-ab12cd:2.0"],
                                     "candidate": {"model": "aquaticy-gemma3-4b-ab12cd:1.2"}}},
           "pins": {"konto": "x"}, "seen": {"konto": "y"}, "enabled": True}
    (tmp_path / "upgrading.json").write_text(json.dumps(alt), encoding="utf-8")
    assert altmodelle.aufraeumen(tmp_path) == 3
    assert not (tmp_path / "upgrading.json").exists(), "Schalter, Pins und Hinweise sind weg"
    liste = json.loads((tmp_path / altmodelle.LISTE_NAME).read_text())
    assert set(liste.values()) == {"gemma3:4b"}
    assert "konto" not in json.dumps(liste)
    assert altmodelle.ausgangsmodell(tmp_path, "ollama_chat/aquaticy-gemma3-4b-ab12cd:1.1") == (
        "ollama_chat/gemma3:4b")
    assert altmodelle.ausgangsmodell(tmp_path, "ollama_chat/qwen3:8b") == "ollama_chat/qwen3:8b"
    assert altmodelle.aufraeumen(tmp_path) == 0


# -- Helfer & Grenzen sind weg -------------------------------------------------------------------


def test_stored_helper_limits_are_taken_out_once(tmp_path: Path, monkeypatch) -> None:
    from aquaticy import config

    env = tmp_path / ".env"
    env.write_text("AQUATICY_RPM=600\nAQUATICY_MAX_TOOL_CALLS=200\nAQUATICY_LOCATION=Bremen\n",
                   encoding="utf-8")
    monkeypatch.setenv("AQUATICY_RPM", "600")
    daten = tmp_path / "daten"
    assert sorted(config.forget_stored_limits(daten, env)) == [
        "AQUATICY_MAX_TOOL_CALLS", "AQUATICY_RPM"]
    gelesen = read_env_file(env)
    assert gelesen == {"AQUATICY_LOCATION": "Bremen"}
    import os

    assert "AQUATICY_RPM" not in os.environ
    # Was ein Betreiber spaeter von Hand eintraegt, bleibt stehen.
    env.write_text("AQUATICY_RPM=40\n", encoding="utf-8")
    assert config.forget_stored_limits(daten, env) == []
    assert read_env_file(env) == {"AQUATICY_RPM": "40"}


def test_the_chat_cannot_change_the_removed_settings() -> None:
    from aquaticy import preferences

    for name in ("subagenten", "subagenten_anzahl", "werkzeug_budget"):
        assert preferences.find(name) is None
