"""Automatische Modellwahl und entfernte Bilderstellung (12.2.1 Sol).

Die Wahl kommt ohne Modellaufruf aus -- also laesst sie sich ohne Attrappe
fuer ein Modell pruefen. Entfernte Bildanbieter duerfen nicht mehr aufgerufen werden.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aquaticy import router
from aquaticy.config import Settings

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture(autouse=True)
def _frisch() -> None:
    router.forget()


@pytest.mark.parametrize(
    ("frage", "erwartet"),
    [
        ("Erstelle mir ein Bild von einem Hund am Strand", "recherche"),
        ("Kannst du mir ein Logo für meine Bäckerei entwerfen?", "recherche"),
        ("male ein Bild von einem Sonnenuntergang", "recherche"),
        ("Generate an image of a red bicycle", "recherche"),
        ("Ein Poster für das Sommerfest gestalten", "recherche"),
        ("Zeig mir ein Bild vom Eiffelturm", "recherche"),
        ("Such mir ein Foto vom Brandenburger Tor", "recherche"),
        ("mach mal eine Liste mit Ideen", "recherche"),
        ("Wie hoch ist die Zugspitze?", "recherche"),
        ("Schreib mir eine Python-Funktion, die Primzahlen findet", "code"),
        ("Traceback (most recent call last):\n  File \"x.py\"", "code"),
        ("```js\nconst a = 1\n```\nwas macht das?", "code"),
        ("Warum ist mein SQL so langsam? Kannst du es optimieren?", "code"),
        ("Hallo!", "schnell"),
        ("danke dir", "schnell"),
        ("Vielen Dank, das hilft!", "schnell"),
        ("Danke", "schnell"),
        ("Schreib einen Brief an meinen Vermieter wegen der Heizung", "schreiben"),
        ("Übersetze das bitte ins Englische: Guten Morgen", "schreiben"),
        ("", "recherche"),
    ],
)
def test_messages_land_in_the_right_drawer(frage: str, erwartet: str) -> None:
    assert router.kategorie(frage) == erwartet


def test_code_mode_is_always_code() -> None:
    assert router.kategorie("Hallo", mode="code") == "code"


def test_classifying_is_fast() -> None:
    lang = "Bitte erkläre mir ausführlich " * 400
    start = time.perf_counter()
    for _ in range(200):
        router.kategorie(lang)
    assert (time.perf_counter() - start) / 200 < 0.01, "unter zehn Millisekunden je Nachricht"


def _settings(tmp_path: Path, **mehr: Any) -> Settings:
    mehr.setdefault("model", "mistral/mistral-large-latest")
    return Settings(data_dir=tmp_path / "d", **mehr)


def test_the_choice_per_drawer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy import system

    monkeypatch.setattr(system, "strongest_model", lambda s, purpose="work": {
        "code": "mistral/codestral-latest", "work": "mistral/mistral-large-latest"}[purpose])
    settings = _settings(tmp_path)
    settings.api_keys["MISTRAL_API_KEY"] = "k"
    assert router.choose(settings, "Schreib ein Bash-Skript, das Logs packt").model == (
        "mistral/codestral-latest")
    assert router.choose(settings, "Hallo").model == "mistral/mistral-small-latest"
    wahl = router.choose(settings, "Erstelle ein Bild von einem Leuchtturm")
    assert wahl.kategorie == "recherche" and wahl.model == "mistral/mistral-large-latest"
    assert not hasattr(wahl, "bild_modell")
    assert router.choose(settings, "Wie wird das Wetter?").model == "mistral/mistral-large-latest"


def test_no_image_backend_is_said_honestly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aquaticy import system

    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_NIM_API_KEY", raising=False)
    monkeypatch.setattr(system, "strongest_model", lambda s, purpose="work": "")
    wahl = router.choose(_settings(tmp_path), "Male ein Bild von einer Katze")
    assert wahl.kategorie == "recherche" and not hasattr(wahl, "bild_modell")
    assert wahl.model == "mistral/mistral-large-latest", "ohne Liste bleibt das eingestellte"


def test_the_list_of_models_is_remembered(tmp_path: Path,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy import system

    aufrufe: list[str] = []
    monkeypatch.setattr(system, "strongest_model",
                        lambda s, purpose="work": aufrufe.append(purpose) or "m/x")
    settings = _settings(tmp_path)
    for _ in range(5):
        router.choose(settings, "Wie hoch ist der Mount Everest?")
    assert aufrufe == ["work"], "einmal nachgesehen, dann gemerkt"


# Die entfernten Anbieter haben keinen Import- oder Ausfuehrungspfad mehr.
@pytest.mark.parametrize("arguments", [
    {}, {"prompt": "a lighthouse"}, {"prompt": "", "format": "quer"},
    {"prompt": "x", "format": "hoch"}, {"prompt": "x", "format": "quadrat"},
    {"prompt": "x", "model": "mistral/mistral-medium-latest"},
    {"prompt": "x", "model": "nvidia_nim/black-forest-labs/flux.1-schnell"},
    {"prompt": "x", "url": "http://127.0.0.1/"},
    {"prompt": "x", "file_id": "../../etc"}, {"prompt": "x", "file_id": "a\r\nHost: x"},
    {"prompt": "x", "data": "<html>"}, {"prompt": "x", "api_key": "secret"},
])
def test_retired_image_tool_has_no_provider_or_dispatch_path(settings, arguments):
    import importlib.util

    from aquaticy.tools import Toolbox

    assert importlib.util.find_spec("aquaticy.images") is None
    box = Toolbox(settings)
    try:
        assert not hasattr(box, "create_image")
        assert box.call("create_image", arguments)["error"]
        assert box.stats.visuals == []
        assert not (settings.data_dir / "media").exists()
    finally:
        box.close()


# -- Im Agenten ----------------------------------------------------------------------
def _antwort(text: str = "", tool_calls: Any = None) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=text, tool_calls=tool_calls))])


def test_the_master_changes_the_agents_do_not(settings: Settings,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy import system
    from aquaticy.agent import Agent

    monkeypatch.setattr(system, "strongest_model", lambda s, purpose="work": {
        "code": "mistral/codestral-latest", "work": "mistral/mistral-large-latest"}[purpose])
    settings.auto_model = True
    modelle: list[str] = []
    monkeypatch.setattr("litellm.completion",
                        lambda **kw: modelle.append(kw["model"]) or _antwort("fertig"))
    ereignisse: list[tuple[str, dict]] = []
    agent = Agent(settings, cache=None, on_event=lambda e, p: ereignisse.append((e, p)))
    fast_vorher = system.fast_model(settings)
    agent.ask("Schreib mir eine Python-Funktion für Fibonacci", stream=False)
    assert modelle == ["mistral/codestral-latest"]
    wahl = next(p for e, p in ereignisse if e == "model_auto")
    assert wahl["kategorie"] == "code" and wahl["grund"] == "Programmieren"
    assert settings.model == "mistral/mistral-large-latest", "die Einstellung bleibt"
    assert system.fast_model(settings) == fast_vorher, "die Agenten bleiben dieselben"
    assert agent.active_model == "mistral/mistral-large-latest", "nur fuer diesen Turn"
    agent.ask("Hallo", stream=False)
    assert modelle[-1] in ("mistral/mistral-small-latest",) or modelle == [
        "mistral/codestral-latest"], "Hallo bekommt das schnelle -- oder die Standardantwort"


def test_switched_off_changes_nothing(settings: Settings,
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy.agent import Agent

    modelle: list[str] = []
    monkeypatch.setattr("litellm.completion",
                        lambda **kw: modelle.append(kw["model"]) or _antwort("fertig"))
    ereignisse: list[str] = []
    agent = Agent(settings, cache=None, on_event=lambda e, p: ereignisse.append(e))
    agent.ask("Schreib mir eine Python-Funktion für Fibonacci", stream=False)
    assert modelle == ["mistral/mistral-large-latest"] and "model_auto" not in ereignisse


def test_a_model_cannot_call_the_retired_tool_even_with_provider_keys(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aquaticy.agent import Agent

    settings.api_keys["MISTRAL_API_KEY"] = "k"
    aufruf = SimpleNamespace(id="c1", type="function", function=SimpleNamespace(
        name="create_image", arguments=json.dumps({"prompt": "a lighthouse", "format": "quer"})))
    antworten = [_antwort(tool_calls=[aufruf]), _antwort("Das Werkzeug ist nicht verfügbar.")]
    angebot = []

    def llm(**kw: Any) -> Any:
        angebot.extend(t["function"]["name"] for t in kw.get("tools") or [])
        return antworten.pop(0)

    monkeypatch.setattr("litellm.completion", llm)
    agent = Agent(settings, cache=None)
    result = agent.ask("Erstelle mir ein Bild von einem Leuchtturm", stream=False)
    assert "create_image" not in angebot and not result.visuals
    assert not (settings.data_dir / "media").exists()
    replies = [m for m in agent.messages if m["role"] == "tool"]
    assert replies and "error" in str(replies[0]["content"])
    agent.close()


def test_no_image_tool_without_a_provider(settings: Settings,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy.agent import Agent

    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_NIM_API_KEY", raising=False)
    agent = Agent(settings, cache=None)
    assert "create_image" not in [t["function"]["name"] for t in agent.tools]


def test_image_prompts_go_through_the_legal_check() -> None:
    from aquaticy.guardrails import SENSITIVE_TOOLS

    assert "create_image" in SENSITIVE_TOOLS


def test_the_switch_is_for_every_account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy import web

    profil = tmp_path / "normal"
    profil.mkdir()
    sitzung = web.ChatSession(account=SimpleNamespace(plan="normal", username="n"),
                              profile=profil)
    monkeypatch.setattr(web, "SESSION", sitzung)
    web.save_values({"AQUATICY_AUTO_MODEL": "true"})
    assert sitzung.settings().auto_model is True
    assert web.current_values()["AQUATICY_AUTO_MODEL"] == "true"
    html = web.UI_FILE.read_text(encoding="utf-8")
    teil = html[html.index('id="dev-settings"'):html.index("</fieldset>",
                                                           html.index('id="dev-settings"'))]
    assert 'name="AQUATICY_AUTO_MODEL"' in teil, "unter Dev settings"
