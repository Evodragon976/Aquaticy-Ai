"""12.1.1 Luna: mehrere Rueckfragen hintereinander, das Fenster zaehlt 1/3, 2/3, 3/3.

"Wo wohnst du?" als erste, "Was interessiert dich?" als zweite -- wenn Aquaticy mehr
Kontext braucht, fragt es in EINEM Aufruf von ask_user mehrere nacheinander. Gilt als
eine Rueckfrage (MAX_QUESTIONS); jede Frage hat eigene Vorschlaege und einen Zaehler.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from aquaticy import tools as tools_mod
from aquaticy import web
from aquaticy.agent import (
    ASK_PROMPT,
    PLACE_QUESTION,
    Agent,
    text_questions,
)
from aquaticy.config import Settings
from aquaticy.subagents import Plan, _parse_questions
from aquaticy.tools import ASK_SCHEMA, MAX_BATCH, MAX_QUESTIONS, Toolbox
from tests.test_agent import ScriptedLLM, _message, _tool_call, toolbox  # noqa: F401
from tests.test_v1140_terra import _denken, einstellungen  # noqa: F401

NACHRICHTEN = "Was sind die neuesten Nachrichten in meinem Ort?"


def _mit_antworten(box: Toolbox, antworten: list[str]) -> tuple[list[tuple[str, list[str]]],
                                                               list[tuple[str, dict[str, Any]]]]:
    gefragt: list[tuple[str, list[str]]] = []
    ereignisse: list[tuple[str, dict[str, Any]]] = []
    folge = iter(antworten)

    def handler(frage: str, optionen: list[str]) -> str:
        gefragt.append((frage, optionen))
        return next(folge, "")

    box.ask_handler = handler
    box.on_event = lambda name, daten: ereignisse.append((name, daten))
    return gefragt, ereignisse



def test_several_questions_are_asked_one_after_another_with_a_counter(
        toolbox: Toolbox) -> None:  # noqa: F811
    gefragt, ereignisse = _mit_antworten(toolbox, ["Bremen", "Sport", "eine Stunde"])
    ergebnis = toolbox.ask_user(questions=[
        {"question": "Wo wohnst du?", "options": ["Bremen", "Hamburg"]},
        {"question": "Was interessiert dich?", "options": ["Sport", "Politik"]},
        {"question": "Wie viel Zeit hast du?"},
    ])
    assert gefragt == [("Wo wohnst du?", ["Bremen", "Hamburg"]),
                       ("Was interessiert dich?", ["Sport", "Politik"]),
                       ("Wie viel Zeit hast du?", [])]
    asks = [d for n, d in ereignisse if n == "ask"]
    assert [(d["index"], d["total"]) for d in asks] == [(1, 3), (2, 3), (3, 3)]
    dones = [d for n, d in ereignisse if n == "ask_done"]
    assert [(d["index"], d["answer"]) for d in dones] == [(1, "Bremen"), (2, "Sport"),
                                                          (3, "eine Stunde")]
    assert ergebnis["answered"] is True and "unanswered" not in ergebnis
    assert [(a["question"], a["answer"]) for a in ergebnis["answers"]] == [
        ("Wo wohnst du?", "Bremen"), ("Was interessiert dich?", "Sport"),
        ("Wie viel Zeit hast du?", "eine Stunde")]
    assert toolbox.stats.questions == 1, "der ganze Aufruf zaehlt einmal"


def test_a_single_question_keeps_its_old_shape_and_has_no_counter(
        toolbox: Toolbox) -> None:  # noqa: F811
    _, ereignisse = _mit_antworten(toolbox, ["Bremen"])
    ergebnis = toolbox.ask_user("Welcher Ort?", ["Bremen"])
    assert ergebnis == {"answered": True, "question": "Welcher Ort?", "answer": "Bremen"}
    ask = next(d for n, d in ereignisse if n == "ask")
    assert "index" not in ask and "total" not in ask


def test_a_skipped_question_does_not_stop_the_series(toolbox: Toolbox) -> None:  # noqa: F811
    gefragt, _ = _mit_antworten(toolbox, ["", "Sport"])
    ergebnis = toolbox.ask_user(questions=[{"question": "Wo wohnst du?"},
                                           {"question": "Was interessiert dich?"}])
    assert len(gefragt) == 2
    assert [a["answer"] for a in ergebnis["answers"]] == ["Sport"]
    assert ergebnis["unanswered"] == ["Wo wohnst du?"]
    assert "Annahme" in ergebnis["note"]


def test_a_timeout_ends_the_series(toolbox: Toolbox, monkeypatch) -> None:  # noqa: F811
    """Nach abgelaufener Wartezeit nicht auch noch die naechste Frage stellen."""
    jetzt = [1000.0]
    monkeypatch.setattr(tools_mod.time, "monotonic", lambda: jetzt[0])
    gefragt: list[str] = []

    def handler(frage: str, optionen: list[str]) -> str:
        gefragt.append(frage)
        jetzt[0] += 180
        return ""

    toolbox.ask_handler = handler
    ergebnis = toolbox.ask_user(questions=[{"question": "Erste?"}, {"question": "Zweite?"}])
    assert gefragt == ["Erste?"]
    assert ergebnis["answered"] is False and "Keine Antwort" in ergebnis["note"]


def test_the_series_has_limits(toolbox: Toolbox) -> None:  # noqa: F811
    gefragt, _ = _mit_antworten(toolbox, ["x"] * 10)
    toolbox.ask_user(questions=[{"question": f"Frage {i}?"} for i in range(9)])
    assert len(gefragt) == MAX_BATCH == 5

    assert Toolbox._ask_list(" Eine? ", ["a", " ", "b"], [{"question": "Eine?"}, "Zwei?", {},
                                                          None, {"question": ""}]) == [
        ("Eine?", ["a", "b"]), ("Zwei?", [])]
    assert Toolbox._ask_list("", None, None) == []
    assert Toolbox._ask_list("Q?", ["1", "2", "3", "4", "5", "6"], None)[0][1] == [
        "1", "2", "3", "4"]


def test_the_two_question_limit_counts_calls_not_questions(
        toolbox: Toolbox) -> None:  # noqa: F811
    _mit_antworten(toolbox, ["a"] * 20)
    for _ in range(MAX_QUESTIONS):
        assert toolbox.ask_user(questions=[{"question": "A?"}, {"question": "B?"},
                                           {"question": "C?"}])["answered"]
    assert not toolbox.ask_user(questions=[{"question": "D?"}])["answered"]


def test_nothing_to_ask_nobody_to_ask(toolbox: Toolbox) -> None:  # noqa: F811
    assert toolbox.ask_user(questions=[])["error"] == "Leere Rueckfrage."
    toolbox.ask_handler = None
    assert toolbox.ask_user(questions=[{"question": "Wo?"}])["answered"] is False


def test_a_failing_window_after_the_first_answer_keeps_what_was_given(
        toolbox: Toolbox) -> None:  # noqa: F811
    zahl = [0]

    def handler(frage: str, optionen: list[str]) -> str:
        zahl[0] += 1
        if zahl[0] == 2:
            raise RuntimeError("Fenster weg")
        return "Bremen"

    toolbox.ask_handler = handler
    ergebnis = toolbox.ask_user(questions=[{"question": "A?"}, {"question": "B?"}])
    assert ergebnis["answered"] and [a["answer"] for a in ergebnis["answers"]] == ["Bremen"]
    assert ergebnis["unanswered"] == ["B?"]


def test_the_schema_and_the_call_know_questions(toolbox: Toolbox) -> None:  # noqa: F811
    eigenschaften = ASK_SCHEMA["function"]["parameters"]["properties"]
    assert eigenschaften["questions"]["maxItems"] == MAX_BATCH
    assert ASK_SCHEMA["function"]["parameters"]["required"] == []
    _mit_antworten(toolbox, ["Bremen", "Sport"])
    ergebnis = toolbox.call("ask_user", {"questions": [{"question": "Wo?"},
                                                       {"question": "Was?"}]})
    assert len(ergebnis["answers"]) == 2
    assert "questions=[" in ASK_PROMPT



def test_the_planner_can_ask_up_to_three_questions() -> None:
    roh = json.dumps({"recherche": True, "teilfragen": ["x"], "rueckfrage": "Wo wohnst du?",
                      "optionen": ["Bremen"], "weitere_fragen": [
                          {"frage": "Was interessiert dich?", "optionen": ["Sport", "Politik"]},
                          {"frage": "Wie viel Zeit?"}, {"frage": "Vierte [Frage]?"}]})
    frage, optionen, weitere = _parse_questions(roh)
    assert (frage, optionen) == ("Wo wohnst du?", ["Bremen"])
    assert weitere == [("Was interessiert dich?", ["Sport", "Politik"]), ("Wie viel Zeit?", [])]

    frage, _, weitere = _parse_questions(json.dumps(
        {"recherche": True, "teilfragen": [], "weitere_fragen": [{"frage": "Nur diese?"}]}))
    assert (frage, weitere) == ("Nur diese?", [])
    assert _parse_questions("kein json") == ("", [], [])
    plan = Plan(True, ["x"], "A?", ["1"], [("B?", ["2"])])
    assert plan.weitere == (("B?", ("2",)),) and plan.rueckfrage == "A?"
    assert Plan(True, ["x"]).weitere == ()


def _planer(monkeypatch: pytest.MonkeyPatch, plaene: list[Plan]) -> list[str]:
    geplant: list[str] = []

    def planer(frage: str, settings: Any, context: str = "", limit: int = 4) -> Plan:
        geplant.append(context)
        return plaene.pop(0) if len(plaene) > 1 else plaene[0]

    monkeypatch.setattr("aquaticy.subagents.plan_request", planer)
    monkeypatch.setattr("aquaticy.subagents.run_subagents", lambda *a, **k: [])
    monkeypatch.setattr("litellm.completion", ScriptedLLM(_message("Antwort aus Lilienthal.")))
    return geplant


def test_structured_asks_place_and_the_planners_questions_in_one_window(
        monkeypatch: pytest.MonkeyPatch, einstellungen: Settings,  # noqa: F811
        toolbox: Toolbox) -> None:  # noqa: F811
    """Ort fehlt, der Planer will noch die Interessen wissen: 1/2 und 2/2 in einem Fenster."""
    geplant = _planer(monkeypatch, [
        Plan(True, ["Nachrichten"], "Was interessiert dich?", ["Sport", "Politik"]),
        Plan(True, ["Nachrichten Lilienthal Sport"])])
    gefragt, ereignisse = _mit_antworten(toolbox, ["Lilienthal", "Sport"])
    agent = Agent(_denken(einstellungen), cache=None, toolbox=toolbox)
    agent.set_ask_handler(toolbox.ask_handler)
    agent.ask(NACHRICHTEN, stream=False, structured=True)
    assert gefragt == [(PLACE_QUESTION, []), ("Was interessiert dich?", ["Sport", "Politik"])]
    assert [(d["index"], d["total"]) for n, d in ereignisse if n == "ask"] == [(1, 2), (2, 2)]
    assert toolbox.stats.questions == 1
    assert agent.clarified == [(PLACE_QUESTION, "Lilienthal"),
                               ("Was interessiert dich?", "Sport")]
    assert "Lilienthal" in geplant[1] and "Sport" in geplant[1], "neu geplant mit allem"
    frage = next(m for m in agent.messages if m.get("role") == "user")["content"]
    assert f"[Rückfrage vor der Recherche: {PLACE_QUESTION} → Lilienthal; " \
           "Was interessiert dich? → Sport]" in frage


def test_three_questions_from_the_planner_without_a_place_question(
        monkeypatch: pytest.MonkeyPatch, einstellungen: Settings,  # noqa: F811
        toolbox: Toolbox) -> None:  # noqa: F811
    _planer(monkeypatch, [Plan(True, ["x"], "Wo wohnst du?", ["Bremen"],
                               [("Was interessiert dich?", ["Sport"]), ("Wie viel Zeit?", [])]),
                          Plan(True, ["x Bremen"])])
    gefragt, ereignisse = _mit_antworten(toolbox, ["Bremen", "Sport", "10 Minuten"])
    agent = Agent(_denken(einstellungen), cache=None, toolbox=toolbox)
    agent.ask(NACHRICHTEN, stream=False, structured=True)

    assert [f for f, _ in gefragt] == ["Wo wohnst du?", "Was interessiert dich?",
                                       "Wie viel Zeit?"]
    assert [(d["index"], d["total"]) for n, d in ereignisse if n == "ask"] == [
        (1, 3), (2, 3), (3, 3)]


def test_pro_mode_asks_the_series_too(
        monkeypatch: pytest.MonkeyPatch, einstellungen: Settings,  # noqa: F811
        toolbox: Toolbox) -> None:  # noqa: F811
    _planer(monkeypatch, [Plan(True, ["x"], "Welches Budget?", ["bis 500 €"],
                               [("Wofür brauchst du ihn?", [])])])
    gemeistert: list[str] = []
    monkeypatch.setattr(Agent, "_master_research",
                        lambda self, frage, budget: gemeistert.append(self._planner_context())
                        or 0)
    _mit_antworten(toolbox, ["bis 500 €", "fürs Büro"])
    agent = Agent(_denken(einstellungen), cache=None, toolbox=toolbox)
    agent.ask("Welchen Laptop soll ich kaufen?", stream=False, structured=True, mode="pro")
    assert [a for _, a in agent.clarified] == ["bis 500 €", "fürs Büro"]
    assert "fürs Büro" in gemeistert[0]



def test_questions_in_the_text_are_split_one_by_one() -> None:
    fragen = text_questions("Gern! Wo wohnst du? Und was interessiert dich?\n- Sport\n- Politik")
    assert fragen == [{"question": "Wo wohnst du?", "options": []},
                      {"question": "Was interessiert dich?", "options": ["Sport", "Politik"]}]
    assert text_questions("In welchem Ort wohnst du?") == [
        {"question": "In welchem Ort wohnst du?", "options": []}]
    assert text_questions("In Bremen sind es 12 Grad. Soll ich auch das Wochenende "
                          "nachsehen?") == []
    assert len(text_questions("A? B? C? D? E? F? G?")) == MAX_BATCH


def test_the_model_asking_two_questions_in_the_text_gets_a_window_series(
        monkeypatch: pytest.MonkeyPatch, settings: Settings,
        toolbox: Toolbox) -> None:  # noqa: F811
    gefragt, ereignisse = _mit_antworten(toolbox, ["Lilienthal", "Sport"])
    frage = "Wo wohnst du? Und was interessiert dich?"
    llm = ScriptedLLM(_message(content=frage), _message(content=frage),
                      _message(content="Sport aus Lilienthal: ..."))
    monkeypatch.setattr("litellm.completion", llm)
    agent = Agent(settings, cache=None, toolbox=toolbox)
    result = agent.ask(NACHRICHTEN, stream=False)
    assert [f for f, _ in gefragt] == ["Wo wohnst du?", "Was interessiert dich?"]
    assert [(d["index"], d["total"]) for n, d in ereignisse if n == "ask"] == [(1, 2), (2, 2)]
    assert result.answer.startswith("Sport aus Lilienthal")
    assert [a for _, a in agent.clarified] == ["Lilienthal", "Sport"]


def test_the_model_can_ask_a_series_itself(
        monkeypatch: pytest.MonkeyPatch, settings: Settings,
        toolbox: Toolbox) -> None:  # noqa: F811
    gefragt, _ = _mit_antworten(toolbox, ["Bremen", "Sport"])
    llm = ScriptedLLM(
        _message(tool_calls=[_tool_call("ask_user", {"questions": [
            {"question": "Wo wohnst du?", "options": ["Bremen"]},
            {"question": "Was interessiert dich?"}]})]),
        _message(content="Sport aus Bremen."))
    monkeypatch.setattr("litellm.completion", llm)
    agent = Agent(settings, cache=None, toolbox=toolbox)
    result = agent.ask(NACHRICHTEN, stream=False)
    assert len(gefragt) == 2 and result.answer == "Sport aus Bremen."
    assert agent.clarified == [("Wo wohnst du?", "Bremen"), ("Was interessiert dich?", "Sport")]
    antwort = next(m for m in agent.messages if m.get("role") == "tool")
    assert len(json.loads(antwort["content"])["answers"]) == 2



def _ui() -> str:
    return web.UI_FILE.read_text(encoding="utf-8")


def test_the_window_has_a_counter_top_right() -> None:
    html = _ui()
    kopf = html[html.index('<div class="ask-head">'):html.index('<div class="ask-q"')]
    assert 'id="ask-count"' in kopf and "hidden" in kopf
    assert ".ask-count{margin-left:auto;" in html
    assert 'case "ask": openAsk(bubble, ev.question, ev.options || [], ev.index, ev.total);' \
        in html
    skript = html[html.index("function openAsk("):html.index("async function finishAsk(")]
    assert "zaehler.hidden = total < 2;" in skript
    assert "zaehler.textContent = `${index}/${total}`;" in skript


def test_between_two_questions_the_window_stays_open_but_times_out() -> None:
    html = _ui()
    fertig = html[html.index("async function finishAsk("):
                  html.index("if (open.bubble?.parentNode){")]
    assert "if (open.index < open.total){" in fertig
    assert 'classList.add("wartet")' in fertig and "closeOverlay(askBox);" in fertig
    assert "setTimeout(() => { if (!asking) closeOverlay(askBox); }, 12000);" in fertig
