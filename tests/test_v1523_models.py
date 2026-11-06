"""15.2.3: Ollama-Erkennung und Auswahl ueber den vollstaendigen API-Weg."""

import json

import httpx
import pytest

from aquaticy import local_model, system, web, webview
from aquaticy.config import Settings
from tests.test_rundgang import _browser_da
from tests.test_v1300_luna import _anlegen, _zustimmung, server  # noqa: F401
from tests.test_web import client, session, web_settings  # noqa: F401


@pytest.mark.parametrize("base", ["http://localhost:11434/v1/", "http://host:11999/ollama/v1"])
def test_ollama_native_discovery_accepts_an_openai_compatible_base(monkeypatch, base):
    visited = []

    def get(url, **kwargs):
        visited.append(url)
        return httpx.Response(200 if url.endswith('/api/tags') and '/v1/' not in url else 404,
                              json={"models": [{"name": "qwen3:8b"}]})

    monkeypatch.setattr(local_model.httpx, "get", get)
    settings = Settings(model="ollama_chat/qwen3:8b", api_base=base)
    assert "ollama_chat/qwen3:8b" in [m["id"] for m in system.available_models(settings)]
    assert local_model.server_running(base)
    assert visited[-1] == base.rstrip('/').removesuffix('/v1') + '/api/tags'


@pytest.mark.parametrize("mode", ["normal", "pro", "code"])
def test_installed_local_models_remain_selectable_beside_cloud_recommendations(mode):
    local = {"id": "ollama_chat/qwen3:8b", "label": "Qwen", "kind": "lokal"}
    strong = [{"id": f"mistral/cloud-{n}", "label": str(n)} for n in range(3)]
    view = webview.picker_view(mode, [local, *strong], strong)
    assert local in view["models"]
    assert view["field"] == ("AQUATICY_MODEL" if mode == "normal" else "AQUATICY_CODE_MODEL")


def test_web_model_selection_returns_ollama_from_a_v1_base(client, session, monkeypatch):  # noqa: F811
    session._settings.model = "ollama_chat/qwen3:8b"
    session._settings.api_base = "http://localhost:11434/v1"
    monkeypatch.setattr(local_model.httpx, "get", lambda url, **kw: httpx.Response(
        200 if url == "http://localhost:11434/api/tags" else 404,
        json={"models": [{"name": "qwen3:8b"}]}))
    monkeypatch.setattr(web, "strong_models", lambda *a, **kw: [])
    status, body = client("GET", "/api/models?mode=normal")
    assert status == 200
    assert "ollama_chat/qwen3:8b" in [m["id"] for m in json.loads(body)["picker"]["models"]]


def test_ollama_provider_aliases_keep_the_configured_server_route():
    settings = Settings(model="ollama/qwen3:8b", api_base="http://host:11999/v1")
    assert settings.ollama_base("ollama_chat/other") == "http://host:11999"
    kwargs = settings.llm_kwargs_for("ollama_chat/other")
    assert kwargs["api_base"] == "http://host:11999"


def test_operator_ollama_management_honors_a_configured_custom_port(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_BASE", "http://host:11999/v1")
    monkeypatch.setattr(web, "get_settings", lambda: Settings(model="mistral/mistral-large-latest"))
    assert web.OLLAMA_URL() == "http://host:11999"


def test_local_chat_and_metadata_use_the_same_native_server(tmp_path):
    from aquaticy.agent import Agent
    from tests.ollama_nachbau import Ollama

    ollama = Ollama()
    agent = None
    try:
        settings = Settings(model="ollama_chat/qwen3:8b", api_base=ollama.url + '/v1',
                            data_dir=tmp_path, subagents_auto=False, context_tokens=2048)
        assert local_model.installed_models(settings.api_base)
        assert local_model.can(settings.model, "tools", settings.api_base) is True
        agent = Agent(settings, cache=None)
        result = agent.ask("Erkläre den Event-Loop", stream=False)
        assert result.error == "" and result.answer == "Fertig."
        assert ollama.anfragen and ollama.anfragen[-1]['num_ctx'] == 2048
    finally:
        if agent is not None:
            agent.close()
        ollama.stop()


def test_cloud_main_keeps_the_native_ollama_route_for_a_local_code_model(monkeypatch):
    monkeypatch.setenv('OLLAMA_API_BASE', 'http://host:11999/v1')
    settings = Settings(model='mistral/mistral-large-latest', code_model='ollama_chat/qwen3:8b')
    assert settings.llm_kwargs_for(settings.code_model)['api_base'] == 'http://host:11999'


def test_upgrade_backend_uses_the_operator_route_without_assuming_a_port():
    from aquaticy.upgrading import OllamaBackend

    assert OllamaBackend('http://host:11999/v1').url == 'http://host:11999'


@pytest.mark.skipif(not _browser_da(), reason='Playwright oder Browser fehlen')
@pytest.mark.parametrize('mode', ['normal', 'pro', 'code'])
def test_the_browser_displays_local_models_in_each_picker(server, monkeypatch, mode):  # noqa: F811
    import shutil

    from playwright.sync_api import expect, sync_playwright

    from tests.test_end_to_end import AGENT, SPRACHE, _req

    consent = _zustimmung(server)
    status, headers, _ = _anlegen(server, consent)
    assert status == 200
    cookie = consent + "; " + headers['Set-Cookie'].split(';', 1)[0]
    monkeypatch.setattr(local_model, 'installed_models', lambda *a: ['qwen3:8b'])
    monkeypatch.setattr(web, 'strong_models', lambda *a, **kw: [
        {'id': f'mistral/cloud-{n}', 'label': str(n), 'kind': 'Mistral'} for n in range(3)])
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=shutil.which('chromium') or
                                   shutil.which('chromium-browser') or '/opt/pw-browsers/chromium',
                                   args=['--no-sandbox'])
        page = browser.new_page(user_agent=AGENT, extra_http_headers={
            "Cookie": cookie, "Accept-Language": SPRACHE})
        page.goto(f'http://127.0.0.1:{server}')
        page.locator('#auth-gate').wait_for(state='hidden')
        page.locator(f'.mode[data-mode="{mode}"]').click()
        page.locator('#btn-model').click()
        choice = page.locator('#model-list .pick[title="ollama_chat/qwen3:8b"]')
        expect(choice).to_be_visible()
        with page.expect_response(lambda response: response.url.endswith('/api/config')
                                  and response.request.method == 'POST') as saved:
            choice.click()
        assert saved.value.status == 200
        values = json.loads(_req(server, 'GET', '/api/config', cookie=cookie)[2])['values']
        field = 'AQUATICY_MODEL' if mode == 'normal' else 'AQUATICY_CODE_MODEL'
        assert values[field] == 'ollama_chat/qwen3:8b'
        browser.close()


@pytest.mark.parametrize('mode', ['normal', 'pro', 'code'])
def test_installation_does_not_override_an_explicit_model_access_denial(monkeypatch, mode):
    monkeypatch.setattr(local_model, 'installed_models', lambda *a: ['private:latest'])
    def deny(model):
        raise ValueError('Not released for this account')
    settings = Settings(model='ollama_chat/private:latest', model_access=deny)
    models = system.available_models(settings)
    assert models == []
    assert webview.picker_view(mode, models, [])['models'] == []
