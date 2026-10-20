"""Verknuepfte Konten (9.6.1) und AI Council.

Seit 12.0.0 Luna sind es die Add-ons NVIDIA NIM und Mistral -- Claude, ChatGPT
und Gemini gibt es nicht mehr, und ein Schluessel kommt nur ueber das Add-on.
"""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import httpx
import pytest

from aquaticy import addons, linked

MISTRAL_KEY = "A" * 32


def _client(routen: dict[str, Any]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        for teil, antwort in routen.items():
            if teil in str(request.url):
                return antwort(request) if callable(antwort) else antwort
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_mistral_reads_chat_models_and_tokens() -> None:
    gesehen: list[httpx.Request] = []

    def probe(request: httpx.Request) -> httpx.Response:
        gesehen.append(request)
        return httpx.Response(200, json={}, headers={
            "x-ratelimit-limit-tokens-minute": "500000",
            "x-ratelimit-remaining-tokens-minute": "499990"})

    client = _client({
        "/v1/models": httpx.Response(200, json={"data": [
            {"id": "mistral-large-latest", "name": "Mistral Large",
             "capabilities": {"completion_chat": True}},
            {"id": "mistral-small-latest", "capabilities": {"completion_chat": True}},
            {"id": "mistral-embed", "capabilities": {"completion_chat": False}},
            {"id": "mistral-moderation-latest", "capabilities": {"completion_chat": False}},
            {"id": "open-mistral-7b", "capabilities": {"completion_chat": True},
             "deprecation": "2025-03-30T00:00:00Z"}]}),
        "/v1/chat/completions": probe})
    info = linked.inspect("mistral", MISTRAL_KEY, client)
    assert [m["id"] for m in info["models"]] == ["mistral/mistral-large-latest",
                                                 "mistral/mistral-small-latest"]
    assert info["models"][0]["label"] == "Mistral Large"
    assert info["tokens"] == {"limit": 500000, "remaining": 499990, "per": "Minute",
                              "reset": ""}
    # Die Probe nimmt das kleine Modell und genau einen Token.
    assert b'"max_tokens":1' in gesehen[0].content.replace(b" ", b"")
    assert b"mistral-small-latest" in gesehen[0].content
    assert gesehen[0].headers["authorization"] == f"Bearer {MISTRAL_KEY}"


def test_mistral_without_limits_says_so() -> None:
    client = _client({
        "/v1/models": httpx.Response(200, json={"data": [{"id": "mistral-small-latest"}]}),
        "/v1/chat/completions": httpx.Response(200, json={})})
    info = linked.inspect("mistral", MISTRAL_KEY, client)
    assert info["tokens"] is None and "Limits" in info["note"]


def test_nvidia_checks_the_key_with_one_token_and_keeps_only_chat_models() -> None:
    gesehen: list[httpx.Request] = []

    def probe(request: httpx.Request) -> httpx.Response:
        gesehen.append(request)
        return httpx.Response(200, json={})

    client = _client({
        "/v1/chat/completions": probe,
        "/v1/models": httpx.Response(200, json={"data": [
            {"id": "deepseek-ai/deepseek-r1"}, {"id": "meta/llama-3.1-8b-instruct"},
            {"id": "meta/llama-3.3-70b-instruct"}, {"id": "nvidia/nv-embedqa-e5-v5"},
            {"id": "nvidia/llama-3.3-nemotron-super-49b-v1.5"},
            {"id": "nvidia/nvidia-nemotron-nano-9b-v2"}, {"id": "nvidia/nemotron-mini-4b"},
            {"id": "nvidia/llama-3.1-nemotron-70b-reward"},
            {"id": "black-forest-labs/flux.1-schnell"}, {"id": "meta/llama-guard-4-12b"}]})})
    info = linked.inspect("nvidia_nim", "nvapi-test-123456", client)
    ids = [m["id"] for m in info["models"]]
    # Seit 12.2.3 Astra: das Nemotron-Arbeitspferd und das kleine zuerst, dann die
    # uebrigen Nemotron-Modelle, dann der Rest.
    assert ids[:3] == ["nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5",
                       "nvidia_nim/nvidia/nvidia-nemotron-nano-9b-v2",
                       "nvidia_nim/nvidia/nemotron-mini-4b"], "das Arbeitspferd zuerst"
    assert "nvidia_nim/deepseek-ai/deepseek-r1" in ids
    assert not any(wort in i for i in ids for wort in ("embed", "reward", "flux", "guard"))
    assert b'"max_tokens":1' in gesehen[0].content.replace(b" ", b"")
    assert info["tokens"] is None and "40 Anfragen" in info["note"]


def test_rejected_key_is_reported() -> None:
    with pytest.raises(linked.LinkError, match="lehnt den Schlüssel ab"):
        linked.inspect("mistral", MISTRAL_KEY, _client({"/v1/models": httpx.Response(401)}))
    with pytest.raises(linked.LinkError, match="lehnt den Schlüssel ab"):
        linked.inspect("nvidia_nim", "nvapi-falsch-123",
                       _client({"/v1/chat/completions": httpx.Response(401)}))


def test_only_mistral_and_nvidia_can_be_linked() -> None:
    assert set(linked.PROVIDERS) == {"mistral", "nvidia_nim"}
    for anbieter in ("anthropic", "openai", "gemini"):
        with pytest.raises(linked.LinkError):
            linked.inspect(anbieter, "sk-irgendwas-123456", _client({}))


def _settings(tmp_path: Path, keys: dict[str, str]) -> Any:
    return types.SimpleNamespace(
        data_dir=tmp_path, api_keys=dict(keys), own_key_names=frozenset(keys),
        account_email="a@example.org", model="mistral/mistral-large-latest",
        llm_kwargs_for=lambda model: {})


def test_picker_and_roles_only_for_own_linked_keys(tmp_path: Path) -> None:
    linked.save(tmp_path, "mistral", {"models": [
        {"id": "mistral/mistral-large-latest", "label": "Large"},
        {"id": "mistral/mistral-small-latest"}]})
    linked.save(tmp_path, "nvidia_nim", {"models": [
        {"id": "nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5"}]})
    # NVIDIA ist ausgelesen, aber der Schluessel gehoert nicht dem Konto.
    s = _settings(tmp_path, {"MISTRAL_API_KEY": "k1"})
    assert {m["id"] for m in linked.picker_models(s)} == {
        "mistral/mistral-large-latest", "mistral/mistral-small-latest"}
    assert linked.council_roles(s) == ([("mistral", "mistral/mistral-large-latest")], None)
    beide = _settings(tmp_path, {"MISTRAL_API_KEY": "k1", "NVIDIA_NIM_API_KEY": "k2"})
    arbeiter, pruefer = linked.council_roles(beide)
    assert arbeiter == [("mistral", "mistral/mistral-large-latest")]
    assert pruefer == ("nvidia_nim", "nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5"), \
        "der letzte prueft"


def test_council_iterates_until_the_judge_agrees(tmp_path: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    linked.save(tmp_path, "mistral", {"models": [{"id": "mistral/mistral-large-latest"}]})
    linked.save(tmp_path, "nvidia_nim", {"models": [
        {"id": "nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5"}]})
    s = _settings(tmp_path, {"MISTRAL_API_KEY": "a", "NVIDIA_NIM_API_KEY": "b"})
    urteile = iter(['{"ok": false, "feedback": "Zahl prüfen"}', '{"ok": true}'])
    aufrufe: list[tuple[str, str]] = []

    def ask(settings: Any, model: str, system: str, user: str, *, json_mode: bool = False):
        aufrufe.append((model, system[:20]))
        if system == linked.JUDGE_PROMPT:
            return next(urteile)
        if system == linked.FINAL_PROMPT:
            return "Endgültige Antwort"
        return f"Lösung von {model}"

    monkeypatch.setattr(linked, "_ask", ask)
    ereignisse: list[dict[str, Any]] = []
    antwort = linked.run_council(s, "Was ist 2+2?", emit=lambda art, **d: ereignisse.append(d))
    assert antwort == "Endgültige Antwort"
    urteile_gesehen = [e for e in ereignisse if e.get("phase") == "verdict"]
    assert [e["ok"] for e in urteile_gesehen] == [False, True], "zweite Runde nach Einwand"
    bearbeiter = {m for m, sys in aufrufe if sys.startswith(linked.WORKER_PROMPT[:20])}
    assert bearbeiter == {"mistral/mistral-large-latest"}
    assert ("nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5",
            linked.CHECK_PROMPT[:20]) in aufrufe
    assert aufrufe[-1][0] == s.model, "der Richter ist das Hauptmodell"


@pytest.mark.parametrize("text", ['{"ok": "false"}', 'true', '{"feedback": "ok"}'])
def test_judge_does_not_accept_invalid_verdicts(text: str) -> None:
    assert linked._judge(text)[0] is False


def test_council_reports_judge_failure_as_unverified(tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    linked.save(tmp_path, "mistral", {"models": [{"id": "mistral/mistral-large-latest"}]})
    linked.save(tmp_path, "nvidia_nim", {"models": [
        {"id": "nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5"}]})
    s = _settings(tmp_path, {"MISTRAL_API_KEY": "a", "NVIDIA_NIM_API_KEY": "b"})
    verdicts: list[bool] = []
    final_request: list[str] = []

    def ask(settings: Any, model: str, system: str, user: str, *, json_mode: bool = False) -> str:
        if system == linked.JUDGE_PROMPT:
            raise TimeoutError("nicht erreichbar")
        if system == linked.FINAL_PROMPT:
            final_request.append(user)
        return "Antwort"

    monkeypatch.setattr(linked, "_ask", ask)
    linked.run_council(s, "Frage", emit=lambda art, **d: verdicts.append(d["ok"])
                       if d.get("phase") == "verdict" else None)
    assert verdicts and not any(verdicts)
    assert "Prüfung wurde nicht bestätigt" in final_request[0]


def test_stopped_council_makes_no_further_model_call(tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    linked.save(tmp_path, "mistral", {"models": [{"id": "mistral/mistral-large-latest"}]})
    linked.save(tmp_path, "nvidia_nim", {"models": [
        {"id": "nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5"}]})
    s = _settings(tmp_path, {"MISTRAL_API_KEY": "a", "NVIDIA_NIM_API_KEY": "b"})
    stop = threading.Event()
    stop.set()
    monkeypatch.setattr(linked, "_ask", lambda *a, **k: pytest.fail("Modell aufgerufen"))
    assert linked.run_council(s, "Frage", stop=stop) == ""


class _Tresor:
    def __init__(self, gespeichert: dict[str, str]) -> None:
        self.gespeichert = gespeichert

    def set(self, name: str, wert: str) -> None:
        self.gespeichert[name] = wert

    def remove(self, name: str) -> bool:
        return self.gespeichert.pop(name, None) is not None


def _sitzung(tmp_path: Path, gespeichert: dict[str, str], monkeypatch: pytest.MonkeyPatch,
             kennung: str = "u1") -> None:
    from aquaticy import web

    sitzung = types.SimpleNamespace(
        account=types.SimpleNamespace(id=kennung), profile=tmp_path,
        settings=lambda: _settings(tmp_path, gespeichert), reload=lambda: None)
    monkeypatch.setattr(web, "SESSION", sitzung)
    monkeypatch.setattr(web, "account_vault", lambda profile, account: _Tresor(gespeichert))
    monkeypatch.setattr(web, "forget_strong_models", lambda *a: None)


def test_web_link_needs_the_addon_and_stores_the_key_only_when_accepted(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy import web

    gespeichert: dict[str, str] = {}
    _sitzung(tmp_path, gespeichert, monkeypatch)
    monkeypatch.setattr(linked, "inspect", lambda provider, key: pytest.fail("gefragt"))
    # Erst installieren -- vorher nimmt Aquaticy keinen Schluessel an.
    antwort, status = web.linked_action({"action": "link", "provider": "mistral",
                                         "key": MISTRAL_KEY})
    assert status == 400 and "Installiere zuerst" in antwort["error"] and not gespeichert
    addons.mark_installed(_settings(tmp_path, {}), "mistral")

    def abgelehnt(provider: str, key: str) -> dict[str, Any]:
        raise linked.LinkError("Mistral lehnt den Schlüssel ab — bitte prüfen.")

    monkeypatch.setattr(linked, "inspect", abgelehnt)
    antwort, status = web.linked_action({"action": "link", "provider": "mistral",
                                         "key": MISTRAL_KEY})
    assert status == 400 and not gespeichert
    monkeypatch.setattr(linked, "inspect", lambda provider, key: {
        "models": [{"id": "mistral/mistral-large-latest", "label": "Large"}],
        "tier": "", "tokens": {"limit": 10, "remaining": 9, "per": "Minute"}})
    antwort, status = web.linked_action({"action": "link", "provider": "mistral",
                                         "key": MISTRAL_KEY})
    assert status == 200 and gespeichert == {"MISTRAL_API_KEY": MISTRAL_KEY}
    karte = next(k for k in antwort["accounts"] if k["provider"] == "mistral")
    assert karte["linked"] and karte["installed"] and karte["models"] == ["Large"]
    assert MISTRAL_KEY not in str(antwort), "der Schluessel geht nie zurueck an den Browser"
    # Ein NVIDIA-Schluessel gehoert nicht ins Mistral-Add-on.
    antwort, status = web.linked_action({"action": "link", "provider": "mistral",
                                         "key": "nvapi-falscher-ort-1"})
    assert status == 400 and "NVIDIA NIM" in antwort["error"]


def test_uninstalling_the_addon_deletes_the_key(tmp_path: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy import web

    gespeichert: dict[str, str] = {"NVIDIA_NIM_API_KEY": "nvapi-eigen-1234"}
    _sitzung(tmp_path, gespeichert, monkeypatch)
    web.SESSION.ultra = False
    web.SESSION.busy = lambda: False
    web.SESSION.reload = lambda **k: None
    linked.save(tmp_path, "nvidia_nim", {"models": [{"id": "nvidia_nim/meta/x"}]})
    # Ein Schluessel von vor 12.0.0: das Add-on gilt dafuer als installiert.
    karten = {a["id"]: a for a in web.addons_view(web.SESSION)["addons"]}
    assert karten["nvidia_nim"]["installed"] and karten["nvidia_nim"]["konto"]["linked"]
    assert karten["nvidia_nim"]["command"] == "", "kein Befehl im Chat"
    antwort, status = web.addon_action({"action": "uninstall", "id": "nvidia_nim"})
    assert status == 200 and gespeichert == {}
    karte = next(a for a in antwort["addons"] if a["id"] == "nvidia_nim")
    assert not karte["installed"] and not karte["konto"]["linked"]
    assert "nvidia_nim" not in linked.load(tmp_path)


def test_lm_studio_stays_but_openai_itself_is_gone(tmp_path: Path) -> None:
    from aquaticy.config import Settings, model_allowed

    s = Settings(model="openai/lokal", api_base="http://lmstudio.local:1234/v1",
                 api_base_for="openai/lokal", data_dir=tmp_path)
    assert s.llm_kwargs_for("openai/lokal")["api_base"] == "http://lmstudio.local:1234/v1"
    assert model_allowed("openai/lokal", "http://lmstudio.local:1234/v1")
    assert not model_allowed("openai/gpt-4o"), "ohne eigene Adresse ginge es zu OpenAI"
    assert not hasattr(s, "is_linked")


def test_key_tells_its_provider() -> None:
    assert linked.detect_provider(" nvapi-abc123 ") == "nvidia_nim"
    assert linked.detect_provider("aB3" * 10 + "xy") == "mistral"
    assert linked.detect_provider("sk-ant-api03-abc") == ""
    assert linked.detect_provider("AIzaSyAbc") == ""
    assert linked.detect_provider("zu kurz") == ""


def test_sign_in_offers_only_what_the_provider_has() -> None:
    assert {"google", "apple", "email"} <= set(linked.SIGN_IN["mistral"])
    assert linked.SIGN_IN["nvidia_nim"] == ("google", "email")
    assert all(art in linked.SIGN_IN_LABELS for arten in linked.SIGN_IN.values()
               for art in arten)


def test_web_link_without_provider_detects_it(tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy import web

    gespeichert: dict[str, str] = {}
    _sitzung(tmp_path, gespeichert, monkeypatch, "u2")
    addons.mark_installed(_settings(tmp_path, {}), "mistral")
    monkeypatch.setattr(linked, "inspect", lambda provider, key: {"models": [], "tier": ""})
    antwort, status = web.linked_action({"action": "link", "key": MISTRAL_KEY})
    assert status == 200 and antwort["provider"] == "mistral"
    assert gespeichert == {"MISTRAL_API_KEY": MISTRAL_KEY}
    karte = next(k for k in antwort["accounts"] if k["provider"] == "nvidia_nim")
    assert [w["id"] for w in karte["sign_in"]] == ["google", "email"]
    antwort, status = web.linked_action({"action": "link", "key": "irgendwas-12345"})
    assert status == 400 and "erkenne" in antwort["error"]


def test_newly_linked_models_are_seen_without_restart(tmp_path: Path) -> None:
    s = _settings(tmp_path, {"MISTRAL_API_KEY": "k"})
    assert linked.picker_models(s) == []
    linked.save(tmp_path, "mistral", {"models": [{"id": "mistral/magistral-medium-latest"}]})
    assert [m["id"] for m in linked.picker_models(s)] == ["mistral/magistral-medium-latest"]
