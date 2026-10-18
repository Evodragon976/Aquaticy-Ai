"""11.4.0 Terra: Aquaticy fragt wieder nach, wenn etwas Entscheidendes fehlt."""

from __future__ import annotations

from typing import Any

import pytest

from aquaticy.agent import FORCE_DETAIL_PROMPT, Agent, own_words
from aquaticy.config import Settings
from aquaticy.subagents import Plan, plan_request
from tests.test_agent import ScriptedLLM, _message, _stub_search, toolbox  # noqa: F401
from tests.test_subagents import _reply


@pytest.fixture
def einstellungen(tmp_path) -> Settings:
    return Settings(model="mistral/mistral-large-latest", data_dir=tmp_path / "d",
                    subagents_auto=False)


# --- Der Nachfass fuer gezielte Angaben drueckt nicht mehr ueber eine Frage hinweg --

def test_a_question_back_is_not_pushed_into_a_search(einstellungen, monkeypatch) -> None:
    """Seit 11.4.0 Luna: "Was laeuft im Kino?" ohne Stadt -- fragte das Modell nach
    der Stadt, kam der Auftrag "oeffne jetzt die Seiten", und es riet einen Ort."""
    llm = ScriptedLLM(_message("Für welche Stadt soll ich das Kinoprogramm suchen?"))
    monkeypatch.setattr("litellm.completion", llm)
    agent = Agent(einstellungen, cache=None)
    ergebnis = agent.ask("Was läuft heute im Kino?", stream=False)
    assert ergebnis.answer.startswith("Für welche Stadt")
    assert len(llm.calls) == 1, "kein Nachfass ueber die Frage hinweg"


def test_the_detail_nudge_allows_asking(einstellungen) -> None:
    assert "dann frag jetzt mit `ask_user` nach, statt zu raten" in " ".join(
        FORCE_DETAIL_PROMPT.split())
    prompt = " ".join(Agent(einstellungen, cache=None).messages[0]["content"].split())
    assert "frag ZUERST nach (siehe Rueckfragen); rate nie eine Stadt" in prompt


def test_the_clarified_note_is_no_ban_on_asking(einstellungen) -> None:
    agent = Agent(einstellungen, cache=None)
    agent.remember_clarified([("Für welchen Ort?", "Bremen")])
    hinweis = agent._clarified_note()
    assert "frag nicht noch einmal danach" not in hinweis
    assert "Fehlt für diese Frage etwas ANDERES, frag wie immer mit ask_user nach." in hinweis


def test_own_words_drop_every_appendix() -> None:
    """Bis 11.4.0 Terra blieb der Block mit den geklaerten Angaben an den "eigenen
    Worten" haengen -- Planer, Rechtspruefer und Ai-guard hielten ihn fuer seine."""
    text = ("Wie wird das Wetter?\n\n[Im Gespräch schon geklärt: Ort? → Bremen; ...]"
            "\n\n[Rückfrage vor der Recherche: Tag? → morgen]\n\n[Ortsfilter: Bremen]")
    assert own_words(text) == "Wie wird das Wetter?"


# --- Der Planer fragt, bevor die Agenten losrennen -----------------------------

def test_the_planner_can_ask(monkeypatch, einstellungen) -> None:
    monkeypatch.setattr("litellm.completion", lambda **k: _reply(
        content='{"recherche": true, "teilfragen": ["Kinoprogramm heute"], '
                '"rueckfrage": "In welcher Stadt? [x]", "optionen": ["Bremen", "Hamburg"]}'))
    plan = plan_request("Was läuft heute im Kino?", einstellungen)
    assert plan == (True, ["Kinoprogramm heute"])            # wie bisher entpackbar
    assert plan.rueckfrage == "In welcher Stadt? (x)" and plan.optionen == ("Bremen", "Hamburg")
    monkeypatch.setattr("litellm.completion", lambda **k: _reply(
        content='{"recherche": true, "teilfragen": ["A"]}'))
    assert plan_request("Frage", einstellungen).rueckfrage == ""


def _denken(einstellungen: Settings) -> Settings:
    einstellungen.subagents_auto = True
    return einstellungen


def test_thinking_mode_asks_before_the_agents_search(monkeypatch, einstellungen,
                                                     toolbox) -> None:  # noqa: F811
    geplant: list[str] = []
    plaene = [Plan(True, ["Kinoprogramm heute"], "In welcher Stadt?", ["Bremen", "Hamburg"]),
              Plan(True, ["Kinoprogramm heute Bremen"])]

    def planer(frage: str, settings: Any, context: str = "", limit: int = 4) -> Plan:
        geplant.append(context)
        return plaene.pop(0)

    gestartet: list[list[str]] = []
    monkeypatch.setattr("aquaticy.subagents.plan_request", planer)
    monkeypatch.setattr("aquaticy.subagents.run_subagents",
                        lambda tasks, *a, **k: gestartet.append([getattr(t, "text", t)
                                                                 for t in tasks]) or [])
    monkeypatch.setattr("litellm.completion", ScriptedLLM(_message("In Bremen läuft ...")))
    gefragt: list[tuple[str, list[str]]] = []
    agent = Agent(_denken(einstellungen), cache=None, toolbox=toolbox)
    agent.set_ask_handler(lambda frage, optionen: gefragt.append((frage, optionen)) or "Bremen")
    agent.ask("Was läuft heute im Kino?", stream=False, structured=True)
    assert gefragt == [("In welcher Stadt?", ["Bremen", "Hamburg"])]
    assert "Bremen" in geplant[1], "neu geplant mit der Antwort"
    assert gestartet and gestartet[0][0] == "Kinoprogramm heute Bremen"
    frage = next(m for m in agent.messages if m.get("role") == "user")["content"]
    assert "[Rückfrage vor der Recherche: In welcher Stadt? → Bremen]" in frage
    assert agent.clarified == [("In welcher Stadt?", "Bremen")]


def test_no_question_without_someone_to_answer(monkeypatch, einstellungen,
                                               toolbox) -> None:  # noqa: F811
    monkeypatch.setattr("aquaticy.subagents.plan_request",
                        lambda *a, **k: Plan(True, ["x"], "In welcher Stadt?"))
    monkeypatch.setattr("aquaticy.subagents.run_subagents", lambda *a, **k: [])
    monkeypatch.setattr("litellm.completion", ScriptedLLM(_message("Antwort.")))
    agent = Agent(_denken(einstellungen), cache=None, toolbox=toolbox)
    agent.ask("Was läuft heute im Kino?", stream=False, structured=True)
    assert agent.toolbox.stats.questions == 0


def test_pro_mode_asks_first_too(monkeypatch, einstellungen, toolbox) -> None:  # noqa: F811
    monkeypatch.setattr("aquaticy.subagents.plan_request",
                        lambda *a, **k: Plan(True, ["x"], "Welches Budget?", ["bis 500 €"]))
    gemeistert: list[str] = []
    monkeypatch.setattr(Agent, "_master_research",
                        lambda self, frage, budget: gemeistert.append(self._planner_context())
                        or 0)
    monkeypatch.setattr("litellm.completion", ScriptedLLM(_message("Antwort.")))
    agent = Agent(_denken(einstellungen), cache=None, toolbox=toolbox)
    agent.set_ask_handler(lambda frage, optionen: "bis 500 €")
    agent.ask("Welchen Laptop soll ich kaufen?", stream=False, structured=True, mode="pro")
    assert agent.clarified == [("Welches Budget?", "bis 500 €")]
    assert gemeistert and "Welches Budget? → bis 500 €" in gemeistert[0]
