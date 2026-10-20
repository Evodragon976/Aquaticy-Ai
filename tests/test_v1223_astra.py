"""12.2.3 Astra: abgeschaltete Modelle (410 Gone) und eine Modellwahl nur mit Verfuegbarem.

Gemeldet: "nvidia_nim/meta/llama-3.3-70b-instruct: ... Error code: 410 - Gone ... has reached
its end of life". NVIDIA hat Llama 3.3 70B und 3.1 8B am 26.08.2026 abgeschaltet -- genau die
beiden, die Aquaticy fuer NVIDIA vorschlug. Dazu der Wunsch: nur verfuegbare Modelle zeigen,
Nemotron vorn.
"""

from __future__ import annotations

import tempfile  # noqa: F401
from collections import OrderedDict
from pathlib import Path
from typing import Any

import pytest

from aquaticy import guardrails, linked, metering, system
from aquaticy.config import Settings
from tests.test_v1222_astra import ERLAUBT, _antwort

ALT = "nvidia_nim/meta/llama-3.3-70b-instruct"
LIVE = ["nvidia_nim/meta/llama-3.1-8b-instruct", "nvidia_nim/deepseek-ai/deepseek-v3.2",
        "nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5",
        "nvidia_nim/nvidia/nvidia-nemotron-nano-9b-v2", "nvidia_nim/qwen/qwen3.5-122b-a10b",
        *[f"nvidia_nim/x/model-{i}" for i in range(10)]]


def _nvidia(tmp: Path, live: list[str] | None = None, model: str = ALT) -> Settings:
    settings = Settings(model=model, data_dir=tmp,
                        api_keys={"NVIDIA_NIM_API_KEY": "nvapi-geheim-12345678"},
                        own_key_names=frozenset({"NVIDIA_NIM_API_KEY"}))
    if live is not None:
        linked.save(tmp, "nvidia_nim", {"models": [{"id": i} for i in live]})
    return settings


@pytest.fixture(autouse=True)
def _vergessen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_retired_seen", OrderedDict())
    monkeypatch.delenv("NVIDIA_NIM_API_KEY", raising=False)


def test_the_retired_nvidia_models_are_known_and_no_default_anymore() -> None:
    for alt in (ALT, "nvidia_nim/meta/llama-3.1-8b-instruct"):
        assert system.is_retired(alt)
        assert alt not in (system.PROVIDER_MODELS["nvidia_nim"], system.FAST_MODELS["nvidia_nim"])
    assert "nemotron" in system.PROVIDER_MODELS["nvidia_nim"]
    assert not system.is_retired("mistral/mistral-medium-latest")


def test_a_410_is_recognised_and_remembered(tmp_path) -> None:
    fehler = Exception("litellm.APIError: Nvidia_nimException - Error code: 410 - {'title': "
                       "'Gone', 'detail': \"The model 'x' has reached its end of life\"}")
    assert system.is_gone_error(fehler)
    assert system.is_gone_error(type("E", (Exception,), {"status_code": 410})("x"))
    assert not system.is_gone_error(Exception("401 Unauthorized"))
    settings = _nvidia(tmp_path)
    system.mark_retired("nvidia_nim/neu/weg", settings)
    assert system.is_retired("nvidia_nim/neu/weg", settings)


def test_the_picker_shows_only_what_the_provider_offers_nemotron_first(tmp_path) -> None:
    settings = _nvidia(tmp_path, LIVE)
    ids = [m["id"] for m in system.available_models(settings) if m["kind"] != "lokal"]
    assert ids[:2] == ["nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5",
                       "nvidia_nim/nvidia/nvidia-nemotron-nano-9b-v2"]
    assert ALT not in ids and "nvidia_nim/meta/llama-3.1-8b-instruct" not in ids
    assert len(ids) == system.MAX_PICKER_MODELS
    klein = next(m for m in system.available_models(settings)
                 if m["id"].endswith("nemotron-nano-9b-v2"))
    assert klein["note"].startswith("Klein und schnell")


def test_without_a_list_the_defaults_and_never_a_retired_one(tmp_path) -> None:
    settings = _nvidia(tmp_path, None)
    ids = [m["id"] for m in system.available_models(settings) if m["kind"] != "lokal"]
    assert ids == [system.PROVIDER_MODELS["nvidia_nim"], system.FAST_MODELS["nvidia_nim"]]
    assert not system.model_usable(settings, ALT)


def test_choices_come_from_the_providers_list(tmp_path) -> None:
    settings = _nvidia(tmp_path, ["nvidia_nim/nvidia/nemotron-3-super-120b-a12b",
                                  "nvidia_nim/foo/tiny-mini-chat"])
    assert system.provider_choice(settings, "nvidia_nim", "main") == \
        "nvidia_nim/nvidia/nemotron-3-super-120b-a12b"
    assert system.provider_choice(settings, "nvidia_nim", "fast") == "nvidia_nim/foo/tiny-mini-chat"
    assert system.provider_choice(settings, "nvidia_nim", "code") == ""
    assert system.fast_model(settings) == "nvidia_nim/foo/tiny-mini-chat"


def test_a_retired_main_model_is_replaced_only_with_a_known_successor(tmp_path) -> None:
    mit = _nvidia(tmp_path / "a", LIVE)
    assert system.replacement(mit, ALT) == "nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5"
    assert system.replacement(mit, "nvidia_nim/meta/llama-3.1-8b-instruct") == \
        "nvidia_nim/nvidia/nvidia-nemotron-nano-9b-v2"
    ohne = _nvidia(tmp_path / "b", None)
    assert system.replacement(ohne, ALT) == ALT, "ohne Liste kein Raten"
    assert system.replacement(mit, "mistral/mistral-medium-latest") == \
        "mistral/mistral-medium-latest"


def test_the_legal_check_uses_the_successor(monkeypatch, tmp_path) -> None:
    gefragt: list[str] = []

    def frage(prompt: str, model: str, settings: Any) -> str:
        gefragt.append(model)
        return ERLAUBT

    monkeypatch.setattr(guardrails, "_ask_model", frage)
    urteil = guardrails.judge("Wie viel Uhr ist es gerade in Berlin?", _nvidia(tmp_path, LIVE))
    assert urteil.allowed and ALT not in gefragt
    assert gefragt[0].startswith("nvidia_nim/nvidia/")


def test_a_freshly_retired_model_hands_over_in_the_same_check(monkeypatch, tmp_path) -> None:
    """Meldet der Anbieter ein Modell erst jetzt als abgeschaltet, fragt der Pruefer gleich
    den Ersatz aus der Liste des Anbieters -- in derselben Pruefung."""
    neu_weg = "nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5"
    gefragt: list[str] = []

    def frage(prompt: str, model: str, settings: Any) -> str:
        gefragt.append(model)
        if model == neu_weg:
            system.mark_retired(model, settings)
            raise Exception("Error code: 410 - Gone, reached its end of life")
        return ERLAUBT

    monkeypatch.setattr(guardrails, "_ask_model", frage)
    settings = _nvidia(tmp_path, [neu_weg, "nvidia_nim/deepseek-ai/deepseek-v3.2"],
                       model=neu_weg)
    urteil = guardrails.judge("Wie viel Uhr ist es gerade in Berlin?", settings)
    assert urteil.allowed, gefragt
    assert gefragt == [neu_weg, "nvidia_nim/deepseek-ai/deepseek-v3.2"]


def test_the_refusal_says_the_model_was_retired(monkeypatch, tmp_path) -> None:
    fehler = Exception("Error code: 410 - {'title': 'Gone', 'detail': \"The model "
                       "'meta/llama-3.3-70b-instruct' has reached its end of life\"}")
    text = guardrails.error_text(fehler, _nvidia(tmp_path), ALT)
    assert text == (f"{ALT} hat der Anbieter abgeschaltet (410, Ende der Laufzeit). "
                    "Bitte im Chat ein anderes Modell wählen.")


def test_metering_remembers_a_410(monkeypatch, tmp_path) -> None:
    from aquaticy import llmcall

    def gone(**kwargs: Any) -> Any:
        raise Exception("Error code: 410 - Gone")

    monkeypatch.setattr(llmcall, "completion", gone)
    settings = _nvidia(tmp_path)
    with pytest.raises(Exception, match="410"):
        metering.completion(settings, model="nvidia_nim/foo/bar",
                            messages=[{"role": "user", "content": "x"}], enforce=False)
    assert system.is_retired("nvidia_nim/foo/bar", settings)


def test_the_chat_switches_to_the_successor(monkeypatch, tmp_path) -> None:
    """Eben abgeschaltet: der Chat merkt es, sagt es und antwortet mit dem Ersatz."""
    from aquaticy.agent import Agent
    from aquaticy.tools import Toolbox

    neu_weg = "nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5"
    benutzt: list[str] = []

    def completion(**kwargs: Any) -> Any:
        benutzt.append(kwargs["model"])
        if kwargs["model"] == neu_weg:
            raise Exception("Error code: 410 - Gone, has reached its end of life")
        return _antwort("Es ist 12 Uhr.")

    monkeypatch.setattr("litellm.completion", completion)
    monkeypatch.setattr(guardrails, "_ask_model", lambda prompt, model, settings: ERLAUBT)
    settings = _nvidia(tmp_path, LIVE, model=neu_weg)
    ereignisse: list[tuple[str, dict[str, Any]]] = []
    agent = Agent(settings, cache=None, toolbox=Toolbox(settings),
                  on_event=lambda n, d: ereignisse.append((n, d)))
    result = agent.ask("Wie viel Uhr ist es?", stream=False)
    assert result.answer == "Es ist 12 Uhr.", result.error
    assert benutzt.count(neu_weg) == 1, benutzt
    assert any(n == "note" and "gibt es beim Anbieter nicht mehr" in d.get("text", "")
               for n, d in ereignisse)


def test_no_schema_retry_when_the_status_says_it_is_pointless() -> None:
    """Im Rundgang gesehen: "InternalServerError: ... 403 Forbidden" lief zweimal."""
    from aquaticy.guardrails import schema_retry_useful

    class InternalServerError(Exception):
        pass

    assert not schema_retry_useful(InternalServerError("MistralException - 403 Forbidden"))
    assert not schema_retry_useful(type("E", (Exception,), {"status_code": 401})("x"))
    assert not schema_retry_useful(type("E", (Exception,), {"status_code": 503})("x"))
    assert schema_retry_useful(type("E", (Exception,), {"status_code": 422})("x"))
    assert schema_retry_useful(type("E", (Exception,), {"status_code": 400})("x"))
    assert schema_retry_useful(Exception("response_format json_schema is not supported"))
