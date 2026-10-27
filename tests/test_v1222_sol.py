"""12.2.2 Sol: Die Pruefungen laufen auch, wenn der Chat ein Modell ueber den API-Schluessel nutzt.

Gemeldet: Mit NVIDIA NIM oder Mistral lehnte Aquaticy ab ("Das Modell fuer die Pruefung
hat nicht geantwortet"). Die Rechtspruefung fragte nur das schnelle und das Hauptmodell
-- im Code-Modus (Code-Modell), im Pro-Modus (staerkstes Modell) und bei der
automatischen Wahl arbeitet der Chat aber mit einem anderen. Waren die beiden lokal und
Ollama aus, kam kein Urteil. Jetzt fragt der Pruefer dann das Modell, mit dem der Chat
wirklich arbeitet. Abgeschaltet wird nichts: ohne Urteil bleibt es bei der Absage.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from aquaticy import aiguard, guardrails
from aquaticy.agent import Agent
from aquaticy.config import Settings
from aquaticy.tools import Toolbox
from tests.test_agent import ScriptedLLM, _message, toolbox  # noqa: F401

ERLAUBT = json.dumps({"zulaessig": True, "regel": "", "grund": "", "missbrauch": False,
                      "missbrauch_art": "", "missbrauch_schwere": 0})
VERBOTEN = json.dumps({"zulaessig": False, "regel": "", "grund": "nein", "missbrauch": False,
                       "missbrauch_art": "", "missbrauch_schwere": 0})


def _pruefer(monkeypatch: pytest.MonkeyPatch, antworten: dict[str, str]) -> list[str]:
    """Lokale Modelle fallen aus (Ollama aus), die anderen antworten wie angegeben."""
    gefragt: list[str] = []

    def frage(prompt: str, model: str, settings: Any) -> str:
        gefragt.append(model)
        if model.startswith(("ollama", "ollama_chat")):
            raise ConnectionError("Ollama läuft nicht")
        return antworten.get(model, ERLAUBT)

    guardrails.forget_verdicts()
    monkeypatch.setattr(guardrails, "_ask_model", frage)
    return gefragt


def _lokal(tmp_path: Any) -> Settings:
    return Settings(model="ollama/qwen3:14b", subagent_model="ollama/qwen3:4b",
                    data_dir=tmp_path / "d")



def test_the_model_the_chat_uses_steps_in(monkeypatch, tmp_path) -> None:
    gefragt = _pruefer(monkeypatch, {})
    urteil = guardrails.judge("Wie wird das Wetter morgen in Bremen?", _lokal(tmp_path),
                              fallback=lambda: ["mistral/mistral-large-latest"])
    assert urteil.allowed and urteil.source == "pruefer"
    assert gefragt == ["ollama/qwen3:4b", "ollama/qwen3:14b", "mistral/mistral-large-latest"]


def test_without_any_answer_it_still_refuses(monkeypatch, tmp_path) -> None:
    """Nicht abgeschwaecht: faellt auch das Modell des Chats aus, bleibt es bei der Absage."""
    _pruefer(monkeypatch, {})
    urteil = guardrails.judge("Wie wird das Wetter morgen?", _lokal(tmp_path),
                              fallback=lambda: ["ollama/noch-eins"])
    assert not urteil.allowed and urteil.source == "ausfall"
    assert not guardrails.judge("Wetter?", _lokal(tmp_path)).allowed, "ohne Ersatz wie bisher"

    def kaputt() -> list[str]:
        raise RuntimeError("weg")

    assert guardrails.judge("Wetter morgen?", _lokal(tmp_path),
                            fallback=kaputt).source == "ausfall"


def test_its_refusal_counts_and_nothing_is_remembered(monkeypatch, tmp_path) -> None:
    gefragt = _pruefer(monkeypatch, {"mistral/mistral-large-latest": VERBOTEN})
    ersatz = lambda: ["mistral/mistral-large-latest"]  # noqa: E731
    urteil = guardrails.judge("Etwas Heikles bitte", _lokal(tmp_path), fallback=ersatz)
    assert not urteil.allowed and urteil.reason == "nein"

    guardrails.judge("Etwas Heikles bitte", _lokal(tmp_path), fallback=ersatz)
    assert gefragt.count("mistral/mistral-large-latest") == 2


def test_the_fallback_is_only_asked_when_needed(monkeypatch, tmp_path) -> None:
    gefragt = _pruefer(monkeypatch, {})
    benutzt: list[int] = []
    settings = Settings(model="mistral/mistral-large-latest", data_dir=tmp_path / "d")
    urteil = guardrails.judge("Wie wird das Wetter morgen in Bremen?", settings,
                              fallback=lambda: benutzt.append(1) or ["nvidia_nim/x"])
    assert urteil.allowed and benutzt == [] and "nvidia_nim/x" not in gefragt


def test_a_tool_call_uses_the_fallback_too(monkeypatch, tmp_path) -> None:
    gefragt = _pruefer(monkeypatch, {})
    waechter = guardrails.Guard(_lokal(tmp_path))
    waechter.fallback = lambda: ["mistral/mistral-large-latest"]
    tool = sorted(guardrails.SENSITIVE_TOOLS)[0]
    assert waechter.check_call(tool, {"query": "Wetter Bremen"}).allowed
    assert "mistral/mistral-large-latest" in gefragt



@pytest.mark.parametrize("mode", ["code", "pro"])
def test_code_and_pro_with_an_api_model_are_not_refused(
        monkeypatch, tmp_path, mode: str) -> None:
    """Der gemeldete Fall: lokales Hauptmodell, Ollama aus, der Chat nimmt Mistral."""
    gefragt = _pruefer(monkeypatch, {})
    monkeypatch.setattr(Agent, "_strongest_model",
                        lambda self, purpose="": "mistral/mistral-large-latest")
    monkeypatch.setattr("litellm.completion",
                        ScriptedLLM(*[_message("Antwort von Mistral.")] * 12))
    settings = _lokal(tmp_path)
    agent = Agent(settings, cache=None, toolbox=Toolbox(settings))
    result = agent.ask("Erkläre mir bitte, wie eine Wärmepumpe funktioniert.",
                       stream=False, mode=mode)
    assert result.error != "Rechtsprüfung nicht erreichbar", result.answer
    assert "Rechtsrahmen" not in result.answer and agent._absage is None
    assert gefragt[:3] == ["ollama/qwen3:4b", "ollama/qwen3:14b",
                           "mistral/mistral-large-latest"]


def test_before_the_fix_the_same_case_was_refused(monkeypatch, tmp_path) -> None:
    """Gegenprobe: ohne das Modell des Chats lehnt die Pruefung ab -- so sah es aus."""
    _pruefer(monkeypatch, {})
    monkeypatch.setattr("litellm.completion", ScriptedLLM(_message("nie")))
    settings = _lokal(tmp_path)
    agent = Agent(settings, cache=None, toolbox=Toolbox(settings))
    assert agent.guard is not None
    agent.guard.fallback = None
    result = agent.ask("Erkläre mir bitte, wie eine Wärmepumpe funktioniert.", stream=False)
    assert result.error == "Rechtsprüfung nicht erreichbar"
    assert "nicht gegen den Rechtsrahmen prüfen" in result.answer


def test_auto_pick_counts_as_the_chat_model(monkeypatch, tmp_path, toolbox) -> None:  # noqa: F811
    agent = Agent(_lokal(tmp_path), cache=None, toolbox=toolbox)
    agent._auto_pick = "nvidia_nim/meta/llama-3.3-70b-instruct"
    assert agent._guard_models() == ["nvidia_nim/meta/llama-3.3-70b-instruct"]
    assert agent.guard is not None and agent.guard.fallback == agent._guard_models



def test_aiguard_asks_the_main_model_when_the_fast_one_is_down(monkeypatch, tmp_path) -> None:
    gefragt: list[str] = []

    def einer(prompt: str, settings: Any, model: str) -> str:
        gefragt.append(model)
        if model.startswith("ollama"):
            raise ConnectionError("Ollama läuft nicht")
        return '{"missbrauch": false, "art": "", "grund": ""}'

    monkeypatch.setattr(aiguard, "_ask_one", einer)
    settings = Settings(model="mistral/mistral-large-latest", subagent_model="ollama/qwen3:4b",
                        data_dir=tmp_path / "d")
    assert aiguard._ask_model("Prüfe das", settings).startswith("{")
    assert gefragt == ["ollama/qwen3:4b", "mistral/mistral-large-latest"]

    with pytest.raises(ConnectionError):
        aiguard._ask_model("x", _lokal(tmp_path))
