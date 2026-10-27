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

    "In Bremen wird es morgen 12 Grad. Soll ich auch das Wochenende nachsehen?",
    "Möchtest du noch mehr dazu wissen?",
    "Would you like me to check the weekend too?",

    "Laut https://example.org gibt es drei Termine. Welcher passt dir?",
    "```python\nprint(1)\n```\nPasst das so?",

    "Die Stadt hat drei Zeitungen, zwei Radiosender und ein Lokalfernsehen, das jeden "
    "Abend um sechs Uhr berichtet. Die größte Zeitung erscheint täglich außer sonntags, "
    "die anderen beiden wöchentlich. Online gibt es außerdem zwei Nachrichtenportale "
    "mit eigener Redaktion. Welche davon liest du?",
    "Das ist erledigt.", "", "Ja?" * 300,
])
def test_answers_and_offers_stay_text(text: str) -> None:
    assert text_question(text) is None



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

    aufrufe = [c for m in agent.messages for c in (m.get("tool_calls") or [])
               if c["function"]["name"] == "ask_user"]
    assert len(aufrufe) == 1
    antworten = [m for m in agent.messages if m.get("role") == "tool"
                 and m.get("name") == "ask_user"]
    assert "Lilienthal" in antworten[0]["content"]


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



from aquaticy.agent import PLACE_QUESTION, needs_place  # noqa: E402
from aquaticy.subagents import Plan  # noqa: E402
from tests.test_v1140_terra import _denken, einstellungen  # noqa: E402,F401


@pytest.mark.parametrize("frage", [
    NACHRICHTEN, "Was ist in meiner Stadt am Wochenende los?", "Gibt es eine Apotheke in der "
    "Nähe?", "Wie wird das Wetter morgen?", "Was läuft heute im Kino?",
    "Restaurants near me", "Öffnungszeiten vom Rathaus",
])
def test_these_questions_need_a_place(frage: str) -> None:
    assert needs_place(frage)


@pytest.mark.parametrize("frage", [
    "Wie wird das Wetter morgen in Bremen?", "Was läuft heute im Kino in Lilienthal?",
    "Neueste Nachrichten aus Hamburg", "Wie entsteht ein Regenbogen?",
    "Was kostet ein Laptop?", "Wer hat die Wahl gewonnen?",
])
def test_these_do_not(frage: str) -> None:
    assert not needs_place(frage)


def _strukturiert(monkeypatch: pytest.MonkeyPatch, plaene: list[Plan]) -> list[str]:
    geplant: list[str] = []

    def planer(frage: str, settings: Any, context: str = "", limit: int = 4) -> Plan:
        geplant.append(context)
        return plaene.pop(0) if len(plaene) > 1 else plaene[0]

    monkeypatch.setattr("aquaticy.subagents.plan_request", planer)
    monkeypatch.setattr("aquaticy.subagents.run_subagents", lambda *a, **k: [])
    monkeypatch.setattr("litellm.completion",
                        ScriptedLLM(_message("Die neuesten Nachrichten aus Lilienthal: ...")))
    return geplant


def test_structured_asks_for_the_place_when_the_planner_does_not(
    monkeypatch: pytest.MonkeyPatch, einstellungen: Settings, toolbox: Toolbox,  # noqa: F811
) -> None:
    """Der gemeldete Fall: "Strukturiert" an, der Planer fragt nicht -- jetzt doch."""
    geplant = _strukturiert(monkeypatch, [Plan(True, ["neueste Nachrichten"]),
                                          Plan(True, ["neueste Nachrichten Lilienthal"])])
    gefragt: list[str] = []
    agent = Agent(_denken(einstellungen), cache=None, toolbox=toolbox)
    agent.set_ask_handler(lambda frage, optionen: gefragt.append(frage) or "Lilienthal")
    agent.ask(NACHRICHTEN, stream=False, structured=True)
    assert gefragt == [PLACE_QUESTION]
    assert len(geplant) == 2 and "Lilienthal" in geplant[1], "neu geplant mit dem Ort"
    assert agent.clarified == [(PLACE_QUESTION, "Lilienthal")]


def test_the_planners_own_question_wins(
    monkeypatch: pytest.MonkeyPatch, einstellungen: Settings, toolbox: Toolbox,  # noqa: F811
) -> None:
    """Fragt der Planer selbst (mit Vorschlaegen), kommt keine zweite Frage."""
    _strukturiert(monkeypatch, [Plan(True, ["x"], "In welcher Stadt?", ["Bremen"]),
                                Plan(True, ["x Bremen"])])
    gefragt: list[str] = []
    agent = Agent(_denken(einstellungen), cache=None, toolbox=toolbox)
    agent.set_ask_handler(lambda frage, optionen: gefragt.append(frage) or "Bremen")
    agent.ask(NACHRICHTEN, stream=False, structured=True)
    assert gefragt == ["In welcher Stadt?"]


@pytest.mark.parametrize("bekannt", ["ortsfilter", "geklaert", "gesprochen"])
def test_no_question_when_the_place_is_known(
    monkeypatch: pytest.MonkeyPatch, einstellungen: Settings, toolbox: Toolbox,  # noqa: F811
    bekannt: str,
) -> None:
    from dataclasses import replace

    _strukturiert(monkeypatch, [Plan(True, ["neueste Nachrichten"])])
    settings = _denken(einstellungen)
    if bekannt == "ortsfilter":
        settings = replace(settings, location="Lilienthal")
    agent = Agent(settings, cache=None, toolbox=toolbox)
    if bekannt == "geklaert":
        agent.remember_clarified([("In welchem Ort wohnst du?", "Lilienthal")])
    if bekannt == "gesprochen":
        monkeypatch.setattr(Agent, "_person_prompt", lambda self: "- wohnt in Lilienthal")
    gefragt: list[str] = []
    agent.set_ask_handler(lambda frage, optionen: gefragt.append(frage) or "x")
    agent.ask(NACHRICHTEN, stream=False, structured=True)
    assert gefragt == []


def test_structured_pro_mode_asks_for_the_place_too(
    monkeypatch: pytest.MonkeyPatch, einstellungen: Settings, toolbox: Toolbox,  # noqa: F811
) -> None:
    _strukturiert(monkeypatch, [Plan(True, ["x"])])
    gemeistert: list[str] = []
    monkeypatch.setattr(Agent, "_master_research",
                        lambda self, frage, budget: gemeistert.append(self._planner_context())
                        or 0)
    agent = Agent(_denken(einstellungen), cache=None, toolbox=toolbox)
    agent.set_ask_handler(lambda frage, optionen: "Lilienthal")
    agent.ask(NACHRICHTEN, stream=False, structured=True, mode="pro")
    assert agent.clarified == [(PLACE_QUESTION, "Lilienthal")]
    assert gemeistert and "Lilienthal" in gemeistert[0]


def test_without_structured_this_path_does_not_ask_first(
    monkeypatch: pytest.MonkeyPatch, einstellungen: Settings, toolbox: Toolbox,  # noqa: F811
) -> None:
    """Ohne "Strukturiert" fragt das Hauptmodell selbst -- nichts davor (nur das fixen)."""
    _strukturiert(monkeypatch, [Plan(True, ["x"])])
    gefragt: list[str] = []
    agent = Agent(_denken(einstellungen), cache=None, toolbox=toolbox)
    agent.set_ask_handler(lambda frage, optionen: gefragt.append(frage) or "x")
    agent.ask(NACHRICHTEN, stream=False, structured=False)
    assert gefragt == []
