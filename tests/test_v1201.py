"""12.0.1 Nutshell: Rueckfragen kommen wieder ins Fenster.

Gemeldet: "Was sind die neuesten Nachrichten in meinem Ort?" -- Aquaticy fragte
nach dem Ort im Chat statt im Fenster. Zwei Gruende: Eine Rueckfrage zaehlte nur,
wenn neben ihr hoechstens 40 Zeichen standen und vorher nichts gesucht war. Und
schrieb das Modell die Frage nach dem Anstoss wieder in den Text, blieb sie dort.
"""

from __future__ import annotations

from typing import Any

import pytest

from aquaticy.agent import Agent, text_question
from aquaticy.config import Settings
from aquaticy.tools import Toolbox
from tests.test_agent import ScriptedLLM, _message, _tool_call, toolbox  # noqa: F401

NACHRICHTEN = "Was sind die neuesten Nachrichten in meinem Ort?"


# -- Erkennen ------------------------------------------------------------------------------
@pytest.mark.parametrize("text, frage", [
    ("Gerne suche ich dir die neuesten Nachrichten heraus! Damit ich die richtigen finde: "
     "In welchem Ort wohnst du?", "In welchem Ort wohnst du?"),
    ("In welchem Ort wohnst du? 😊", "In welchem Ort wohnst du?"),
    ("**Für welchen Ort** soll ich nachsehen?", "Für welchen Ort soll ich nachsehen?"),
    ("Welche Stadt meinst du? Und welchen Zeitraum?", "Welche Stadt meinst du? Und welchen "
     "Zeitraum?"),
    ("Which town do you live in?", "Which town do you live in?"),
])
def test_a_polite_question_is_still_a_question(text: str, frage: str) -> None:
    gefunden = text_question(text)
    assert gefunden is not None and gefunden[0] == frage


def test_suggestions_under_the_question_become_buttons() -> None:
    text = ("Für welchen Zeitraum soll ich nachsehen?\n\n- **heute**\n- morgen\n"
            "- am Wochenende\n- nächste Woche\n- im Mai")
    assert text_question(text) == ("Für welchen Zeitraum soll ich nachsehen?",
                                   ["heute", "morgen", "am Wochenende", "nächste Woche"])
    assert text_question("Welche Stadt?\n1. Bremen\n2) Hamburg") == ("Welche Stadt?",
                                                                     ["Bremen", "Hamburg"])


@pytest.mark.parametrize("text", [
    # Ein Angebot am Ende einer Antwort.
    "In Bremen wird es morgen 12 Grad. Soll ich auch das Wochenende nachsehen?",
    "Möchtest du noch mehr dazu wissen?",
    "Would you like me to check the weekend too?",
    # Eine Antwort mit Quelle oder Code.
    "Laut https://example.org gibt es drei Termine. Welcher passt dir?",
    "```python\nprint(1)\n```\nPasst das so?",
    # Viel Inhalt und am Ende eine Frage: geantwortet.
    "Die Stadt hat drei Zeitungen, zwei Radiosender und ein Lokalfernsehen, das jeden "
    "Abend um sechs Uhr berichtet. Die größte Zeitung erscheint täglich außer sonntags, "
    "die anderen beiden wöchentlich. Online gibt es außerdem zwei Nachrichtenportale "
    "mit eigener Redaktion. Welche davon liest du?",
    "Das ist erledigt.", "", "Ja?" * 300,
])
def test_answers_and_offers_stay_text(text: str) -> None:
    assert text_question(text) is None


# -- Im Lauf -------------------------------------------------------------------------------
def _gefragt(toolbox: Toolbox, antwort: str = "Lilienthal") -> list[tuple[str, list[str]]]:  # noqa: F811
    liste: list[tuple[str, list[str]]] = []

    def handler(frage: str, optionen: Any = None) -> str:
        liste.append((frage, list(optionen or [])))
        return antwort

    toolbox.ask_handler = handler
    return liste


def test_the_local_news_question_opens_the_window(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, toolbox: Toolbox,  # noqa: F811
) -> None:
    """Genau der gemeldete Fall: erst gesucht, dann im Text nach dem Ort gefragt --
    auch nach dem Anstoss noch einmal. Jetzt stellt Aquaticy die Frage selbst."""
    gefragt = _gefragt(toolbox)
    frage = ("Gerne suche ich dir die neuesten Nachrichten heraus! Damit ich die richtigen "
             "finde: In welchem Ort wohnst du? 😊")
    llm = ScriptedLLM(
        _message(tool_calls=[_tool_call("web_search", {"query": "neueste Nachrichten"})]),
        _message(content=frage),
        _message(content=frage),
        _message(content="Die neuesten Nachrichten aus Lilienthal: ..."),
    )
    monkeypatch.setattr("litellm.completion", llm)
    agent = Agent(settings, cache=None, toolbox=toolbox)
    result = agent.ask(NACHRICHTEN, stream=False)

    assert gefragt == [("In welchem Ort wohnst du?", [])]
    assert result.answer.startswith("Die neuesten Nachrichten aus Lilienthal")
    # Im Verlauf steht ein echter Aufruf von ask_user mit der Antwort -- keine Frage im Text.
    aufrufe = [c for m in agent.messages for c in (m.get("tool_calls") or [])
               if c["function"]["name"] == "ask_user"]
    assert len(aufrufe) == 1
    antworten = [m for m in agent.messages if m.get("role") == "tool"
                 and m.get("name") == "ask_user"]
    assert "Lilienthal" in antworten[0]["content"]
    # Die erste Fassung bleibt stehen (auf sie bezieht sich der Anstoss), die zweite
    # ist zum Aufruf geworden.
    assert sum(m.get("role") == "assistant" and m.get("content") == frage
               for m in agent.messages) == 1


def test_the_suggestions_come_along(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, toolbox: Toolbox,  # noqa: F811
) -> None:
    gefragt = _gefragt(toolbox, "morgen")
    frage = "Für welchen Tag?\n- heute\n- morgen"
    llm = ScriptedLLM(_message(content=frage), _message(content=frage),
                      _message(content="Morgen: 12 Grad."))
    monkeypatch.setattr("litellm.completion", llm)
    result = Agent(settings, cache=None, toolbox=toolbox).ask("Wetter in Bremen?", stream=False)
    assert gefragt == [("Für welchen Tag?", ["heute", "morgen"])]
    assert result.answer == "Morgen: 12 Grad."


def test_after_reading_pages_a_question_stays(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, toolbox: Toolbox,  # noqa: F811
) -> None:
    """Wer Seiten gelesen hat, hat geantwortet -- die Anschlussfrage bleibt Text."""
    gefragt = _gefragt(toolbox)
    llm = ScriptedLLM(
        _message(tool_calls=[_tool_call("fetch_page", {"url": "https://example.org/a"})]),
        _message(content="Welche der drei Meldungen interessiert dich?"),
    )
    monkeypatch.setattr("litellm.completion", llm)
    result = Agent(settings, cache=None, toolbox=toolbox).ask(NACHRICHTEN, stream=False)
    assert gefragt == []
    assert result.answer == "Welche der drei Meldungen interessiert dich?"


def test_never_more_than_two_questions(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, toolbox: Toolbox,  # noqa: F811
) -> None:
    """Die Grenze von zwei Rueckfragen je Anfrage gilt auch hier."""
    gefragt = _gefragt(toolbox)
    llm = ScriptedLLM(
        _message(tool_calls=[_tool_call("ask_user", {"question": "Welcher Ort?"}, "a1")]),
        _message(tool_calls=[_tool_call("ask_user", {"question": "Welcher Tag?"}, "a2")]),
        _message(content="Und welche Uhrzeit?"),
        _message(content="Und welche Uhrzeit?"),
    )
    monkeypatch.setattr("litellm.completion", llm)
    result = Agent(settings, cache=None, toolbox=toolbox).ask(NACHRICHTEN, stream=False)
    assert [frage for frage, _ in gefragt] == ["Welcher Ort?", "Welcher Tag?"]
    assert result.answer == "Und welche Uhrzeit?"
