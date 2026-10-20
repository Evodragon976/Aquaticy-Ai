"""12.2.4 Luna: Modellwechsel, Anbieterlisten und getrennte Sicherheitspruefungen."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

import pytest

from aquaticy import aiguard, guardrails, linked, metering, system
from aquaticy.agent import Agent
from aquaticy.config import Settings
from tests.test_v1222_astra import ERLAUBT

MODEL = "mistral/review-main-chat"
NEXT = "mistral/review-next-chat"


def _settings(tmp: Path, **kwargs: Any) -> Settings:
    return Settings(model=MODEL, data_dir=tmp,
                    api_keys={"MISTRAL_API_KEY": "synthetic-review-key"},
                    own_key_names=frozenset({"MISTRAL_API_KEY"}), **kwargs)


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_retired_seen", OrderedDict())
    monkeypatch.setattr("aquaticy.local_model.installed_models", lambda *a, **k: [])
    aiguard.forget_judgements()


@pytest.mark.parametrize("change", ["account", "key", "endpoint"])
def test_one_accounts_provider_error_does_not_disable_another_connection(
        monkeypatch, tmp_path, change: str) -> None:
    first = _settings(tmp_path / "a")
    second = _settings(tmp_path / ("b" if change == "account" else "a"))
    if change == "key":
        second.api_keys = {"MISTRAL_API_KEY": "another-synthetic-review-key"}
    if change == "endpoint":
        second.api_base = second.own_api_base = "https://models.example.org/v1"
    monkeypatch.setattr("aquaticy.llmcall.completion",
                        lambda **kw: (_ for _ in ()).throw(Exception("410 Gone")))
    assert system.model_usable(second, MODEL)
    with pytest.raises(Exception, match="410"):
        metering.completion(first, model=MODEL, enforce=False,
                            messages=[{"role": "user", "content": "Test"}])
    assert not system.model_usable(first, MODEL)
    assert system.model_usable(second, MODEL), "Sperren gelten nur fuer die betroffene Verbindung"


@pytest.mark.parametrize("catalog", [[], [{"id": MODEL}], None, "ungueltig"])
def test_a_known_empty_or_unusable_catalog_does_not_offer_unconfirmed_defaults(
        tmp_path, catalog: Any) -> None:
    settings = _settings(tmp_path)
    linked.save(tmp_path, "mistral", {"models": catalog})
    if catalog == [{"id": MODEL}]:
        # Der Fehler kommt ueber den echten Buchungsweg, nicht ueber eine globale Sperre.
        from unittest.mock import patch

        with patch("aquaticy.llmcall.completion", side_effect=RuntimeError("410 Gone")), \
                pytest.raises(RuntimeError, match="410"):
            metering.completion(settings, model=MODEL, enforce=False, messages=[])
    assert system.provider_choice(settings, "mistral", "main") == ""
    assert system.available_models(settings) == []
    assert not system.model_usable(settings, MODEL)


def test_a_current_model_outside_the_known_catalog_is_not_reinserted(tmp_path) -> None:
    settings = _settings(tmp_path)
    linked.save(tmp_path, "mistral", {"models": [{"id": NEXT}]})
    assert [m["id"] for m in system.available_models(settings)] == [NEXT]
    assert not system.model_usable(settings, MODEL)


def test_a_retired_coder_prefers_an_available_coding_successor(tmp_path) -> None:
    settings = _settings(tmp_path)
    settings.api_keys["NVIDIA_NIM_API_KEY"] = "synthetic-nvidia-key"
    retired = system.CODING_MODELS["nvidia_nim"]
    successor = "nvidia_nim/qwen/qwen3-coder-480b-a35b-instruct"
    linked.save(tmp_path, "nvidia_nim", {"models": [
        {"id": retired}, {"id": system.PROVIDER_MODELS["nvidia_nim"]}, {"id": successor}]})
    system.mark_retired(retired, settings)
    assert system.replacement(settings, retired) == successor


def test_the_current_model_does_not_exceed_the_picker_limit(tmp_path) -> None:
    settings = _settings(tmp_path)
    linked.save(tmp_path, "mistral", {
        "models": [{"id": f"mistral/model-{i}-chat"} for i in range(12)] + [{"id": MODEL}]})
    models = system.available_models(settings)
    assert MODEL in [m["id"] for m in models]
    assert len(models) == system.MAX_PICKER_MODELS


def test_addon_models_use_the_same_filtered_selection_and_council_ignores_retired(tmp_path) -> None:
    settings = _settings(tmp_path)
    linked.save(tmp_path, "mistral", {"models": [
        {"id": f"mistral/model-{i}-chat"} for i in range(12)] + [{"id": MODEL}]})
    system.mark_retired("mistral/model-0-chat", settings)
    expected = [m["id"] for m in system.available_models(settings)]
    assert [m["id"] for m in linked.picker_models(settings)] == expected
    assert len(expected) == system.MAX_PICKER_MODELS
    assert "mistral/model-0-chat" not in expected
    assert linked.best_model(settings, "mistral") != "mistral/model-0-chat"


def test_council_calls_switch_once_and_preserve_access_and_quota_checks(
        monkeypatch, tmp_path) -> None:
    from tests.test_v1222_astra import _antwort

    settings = _settings(tmp_path)
    linked.save(tmp_path, "mistral", {"models": [{"id": MODEL}, {"id": NEXT}]})
    called: list[str] = []

    def completion(current: Settings, *, enforce: bool = True, **kwargs: Any) -> Any:
        assert current is settings and enforce
        called.append(kwargs["model"])
        if kwargs["model"] == MODEL:
            raise RuntimeError("410 Gone")
        return _antwort("ok")

    monkeypatch.setattr(metering, "completion", completion)
    assert linked._ask(settings, MODEL, "Pruefung", "Frage") == "ok"
    assert called == [MODEL, NEXT]


@pytest.mark.parametrize("choice", ["normal", "auto", "backup", "pro", "code"])
def test_a_retired_model_switches_in_every_chat_mode(tmp_path, choice: str) -> None:
    settings = _settings(tmp_path, llm_retries=1)
    linked.save(tmp_path, "mistral", {"models": [{"id": MODEL}, {"id": NEXT}]})
    # Die echte Wiederholungslogik mit einem nachgestellten Anbieter und ohne Netz.
    agent = Agent.__new__(Agent)
    agent.settings = settings
    agent.mode = choice if choice in {"pro", "code"} else "normal"
    agent._auto_pick = MODEL if choice == "auto" else ""
    agent._ausweich_model = MODEL if choice == "backup" else ""
    agent._strongest_model = lambda: MODEL
    agent._tell_if_loading = lambda: None
    agent._model_ready = lambda: None
    agent._emit = lambda *a, **k: None
    called: list[str] = []

    def completion(messages: Any, *, stream: bool) -> dict[str, str]:
        called.append(agent.active_model)
        if agent.active_model == MODEL:
            raise Exception("410 Gone")
        return {"role": "assistant", "content": "ok"}

    agent._completion = completion
    assert agent._completion_with_retry([], stream=False)["content"] == "ok"
    assert called == [MODEL, NEXT]


def test_a_parallel_retirement_does_not_mark_the_successor_as_retired(tmp_path) -> None:
    settings = _settings(tmp_path, llm_retries=1)
    linked.save(tmp_path, "mistral", {"models": [{"id": MODEL}, {"id": NEXT}]})
    agent = Agent.__new__(Agent)
    agent.settings = settings
    agent.mode = "normal"
    agent._tell_if_loading = lambda: None
    agent._model_ready = lambda: None
    agent._emit = lambda *a, **k: None
    called: list[str] = []

    def completion(messages: Any, *, stream: bool) -> dict[str, str]:
        called.append(agent.active_model)
        if len(called) == 1:
            # Eine parallele Pruefung hat denselben Fehler bereits eingetragen.
            system.mark_retired(MODEL, settings)
            assert agent.active_model == MODEL, "Ein laufender Aufruf muss dasselbe Modell behalten"
            raise Exception("410 Gone")
        return {"role": "assistant", "content": "ok"}

    agent._completion = completion
    assert agent._completion_with_retry([], stream=False)["content"] == "ok"
    assert called == [MODEL, NEXT]
    assert not system.is_retired(NEXT, settings)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 503])
def test_an_explicit_status_is_not_overridden_by_retirement_words(status: int) -> None:
    error = type("ProviderError", (Exception,), {"status_code": status})(
        'Request rejected: user asked about a model that has reached its end of life')
    assert not system.is_gone_error(error)


def test_aiguard_tries_a_fresh_successor_in_the_same_check(monkeypatch, tmp_path) -> None:
    settings = _settings(tmp_path, subagent_model=MODEL)
    linked.save(tmp_path, "mistral", {"models": [{"id": MODEL}, {"id": NEXT}]})
    called: list[str] = []

    def one(prompt: str, settings: Settings, model: str) -> str:
        called.append(model)
        if model == MODEL:
            system.mark_retired(model, settings)
            raise Exception("410 Gone")
        return '{"missbrauch":false,"art":"ok","grund":""}'

    monkeypatch.setattr(aiguard, "_ask_one", one)
    assert aiguard.parse_judgement(aiguard._ask_model("Pruefe das", settings)) == (False, "ok")
    assert called == [MODEL, NEXT]


def test_aiguard_cache_also_depends_on_the_fallback_credentials(monkeypatch, tmp_path) -> None:
    settings = _settings(tmp_path, subagent_model="nvidia_nim/review-fast-chat")
    settings.api_keys["NVIDIA_NIM_API_KEY"] = "synthetic-fast-key"
    asked: list[str] = []

    def ask(prompt: str, current: Settings) -> str:
        asked.append(current.api_keys["MISTRAL_API_KEY"])
        return '{"missbrauch":false,"art":"ok","grund":""}'

    text = "Erklaere mir bitte ausfuehrlich die Funktionsweise einer Waermepumpe."
    assert aiguard.classify(text, settings, ask=ask) == (False, "ok")
    settings.api_keys["MISTRAL_API_KEY"] = "changed-synthetic-fallback-key"
    assert aiguard.classify(text, settings, ask=ask) == (False, "ok")
    assert len(asked) == 2, "Urteile gelten nicht nach Wechsel der Ersatz-Zugangsdaten"


def test_a_fresh_successor_verdict_cannot_reappear_after_retirement_eviction(
        monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(system, "MAX_RETIRED_MODELS", 1)
    settings = _settings(tmp_path, subagent_model=MODEL)
    linked.save(tmp_path, "mistral", {"models": [{"id": MODEL}, {"id": NEXT}]})

    def ask(prompt: str, model: str, current: Settings) -> str:
        current.fast_kwargs_for(model)
        if model == MODEL:
            raise RuntimeError("410 Gone")
        return ERLAUBT

    text = "Wie arbeitet eine Waermepumpe?"
    assert guardrails.judge(text, settings, ask=ask).allowed
    system.mark_retired("mistral/unrelated-model", settings)

    def access(model: str) -> None:
        if model == NEXT:
            raise ValueError("Modellfreigabe entzogen")

    settings.model_access = access
    result = guardrails.judge(text, settings, ask=ask)
    assert not result.allowed and result.source == "ausfall"


@pytest.mark.parametrize("kind", ["request", "answer"])
def test_aiguard_does_not_cache_under_a_connection_changed_during_the_call(
        monkeypatch, tmp_path, kind: str) -> None:
    monkeypatch.setattr(system, "MAX_RETIRED_MODELS", 1)
    settings = _settings(tmp_path, subagent_model=MODEL)
    linked.save(tmp_path, "mistral", {"models": [{"id": MODEL}, {"id": NEXT}]})
    called: list[str] = []

    def one(prompt: str, current: Settings, model: str) -> str:
        called.append(model)
        current.fast_kwargs_for(model)
        if model == MODEL:
            raise RuntimeError("410 Gone")
        return '{"missbrauch":false,"art":"ok","grund":""}'

    monkeypatch.setattr(aiguard, "_ask_one", one)
    text = "Ich erklaere allgemein, wie man Schadsoftware erkennt und sicher analysiert."

    def check() -> Any:
        return aiguard.classify(text, settings) if kind == "request" else \
            aiguard.answer_problem(text, settings)

    check()
    assert called == [MODEL, NEXT]
    system.mark_retired("mistral/unrelated-model", settings)

    def access(model: str) -> None:
        if model == NEXT:
            raise ValueError("Modellfreigabe entzogen")

    settings.model_access = access
    check()
    assert called == [MODEL, NEXT, MODEL, NEXT], "Nach Entzug erneut pruefen, kein altes Urteil"


def test_error_messages_redact_overlapping_keys_and_uppercase_urls(tmp_path) -> None:
    settings = _settings(tmp_path)
    settings.api_keys = {"MISTRAL_API_KEY": "synthetic-secret", "NVIDIA_NIM_API_KEY":
                         "synthetic-secret-long-private-suffix"}
    text = guardrails.error_text(Exception(
        "synthetic-secret-long-private-suffix HTTPS://private.example.org/v1"), settings, MODEL)
    assert "private-suffix" not in text and "private.example.org" not in text


def test_runtime_observations_are_bounded_and_store_no_plaintext_credentials(
        monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(system, "MAX_RETIRED_MODELS", 2)
    monkeypatch.setattr(system, "MAX_RETIRED_SCOPES", 2)
    settings = _settings(tmp_path)
    for model in (MODEL, NEXT, "mistral/review-third-chat"):
        system.mark_retired(model, settings)
    assert not system.is_retired(MODEL, settings)
    assert system.is_retired(NEXT, settings)
    assert system.is_retired("mistral/review-third-chat", settings)
    for key in ("first-synthetic-key", "second-synthetic-key", "third-synthetic-key"):
        settings.api_keys["MISTRAL_API_KEY"] = key
        system.mark_retired(NEXT, settings)
    assert system.is_retired(NEXT, settings)
    settings.api_keys["MISTRAL_API_KEY"] = "first-synthetic-key"
    assert not system.is_retired(NEXT, settings)
    assert "synthetic" not in repr(system._retired_seen)


def test_legal_checks_still_refuse_when_every_successor_fails(tmp_path) -> None:
    settings = _settings(tmp_path)
    linked.save(tmp_path, "mistral", {"models": [{"id": MODEL}, {"id": NEXT}]})
    called: list[str] = []

    def ask(prompt: str, model: str, current: Settings) -> str:
        called.append(model)
        raise Exception("410 Gone")

    verdict = guardrails.judge("Wie arbeitet eine Waermepumpe?", settings, ask=ask)
    assert not verdict.allowed and verdict.source == "ausfall"
    assert called == [MODEL, NEXT]
