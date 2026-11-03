"""Besitzerrechte, Secure-Pro-Chats und sichere Voice-Schalter."""

import json
import shutil
from types import SimpleNamespace

import pytest

from aquaticy import secure_pro, voice, web
from aquaticy.cache import Cache
from aquaticy.config import Settings
from tests.test_end_to_end import _req
from tests.test_v1300_luna import _anlegen, _zustimmung, server  # noqa: F401


@pytest.fixture
def owner(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path)
    account = SimpleNamespace(id="owner")
    session = SimpleNamespace(account=account, ultra=True, settings=lambda: settings,
                              chat_id=lambda: "secure-chat")
    auth = SimpleNamespace(single=True, ensure_owner_ultra=lambda: account)
    monkeypatch.setattr(web, "AUTH", auth)
    monkeypatch.setattr(web, "_native_paused", lambda account: False)
    monkeypatch.setattr(web, "get_settings", lambda: settings)
    monkeypatch.setattr(voice, "root", lambda: tmp_path)
    monkeypatch.setattr(web, "SECURE_WATCHER", None)
    return session, settings


def test_secure_marker_survives_reopen_and_is_removed_with_chat(owner):
    session, settings = owner
    cache = Cache(settings.db_path)
    cache.mark_secure_chat(session.chat_id())
    cache.add_history(session.chat_id(), "Secure Pro", "Status", mode="normal")
    reopened = Cache(settings.db_path)
    assert reopened.is_secure_chat(session.chat_id())
    assert reopened.recent_chats()[0]["secure_pro"] is True
    assert reopened.search_chats("Secure Pro")[0]["secure_pro"] is True
    assert web.chat_kind_conflict(session, "normal") == ""
    assert web.chat_kind_conflict(session, "code")
    reopened.delete_chat(session.chat_id())
    assert not reopened.is_secure_chat(session.chat_id())


@pytest.mark.parametrize("change", ["anonymous", "other", "multi", "normal", "banned"])
def test_host_settings_cannot_be_changed_by_other_accounts(owner, monkeypatch, change):
    session, settings = owner
    if change == "anonymous":
        session.account = None
    elif change == "other":
        session.account = SimpleNamespace(id="other")
    elif change == "multi":
        web.AUTH.single = False
    elif change == "normal":
        session.ultra = False
    else:
        monkeypatch.setattr(web, "_native_paused", lambda account: True)
    for action in ["voice", "configure", "message"]:
        result, status = web.feature_action(session, {"action": action, "enabled": True})
        assert status == 403 and "error" in result
    assert web.feature_view(session) == {"allowed": False}
    assert not (settings.data_dir / "voice.json").exists()
    assert not (settings.data_dir / "secure-pro.json").exists()


def test_voice_cannot_be_enabled_without_local_programs_and_model(owner, monkeypatch):
    session, _settings = owner
    monkeypatch.setattr(voice, "ready", lambda directory: False)
    result, status = web.feature_action(session, {"action": "voice", "enabled": True})
    assert status == 400 and "aquaticy voice" in result["error"]
    assert not voice.enabled()
    assert web.feature_action(session, {"action": "voice", "enabled": "true"})[1] == 400


def test_voice_can_be_enabled_and_disabled_from_settings(owner, monkeypatch):
    session, _settings = owner
    monkeypatch.setattr(voice, "ready", lambda directory: True)
    assert web.feature_action(session, {"action": "voice", "enabled": True})[1] == 200
    assert voice.enabled()
    assert web.feature_view(session)["voice"] is True
    assert web.feature_action(session, {"action": "voice", "enabled": False})[1] == 200
    assert not voice.enabled()


@pytest.mark.parametrize("consent,subnet", [(False, "192.168.1.0/24"),
                                           (True, "8.8.8.0/24"),
                                           (True, "192.168.0.0/16")])
def test_secure_chat_still_requires_explicit_private_network_permission(owner, consent, subnet):
    session, settings = owner
    Cache(settings.db_path).mark_secure_chat(session.chat_id())
    result, status = web.feature_action(session, {"action": "configure", "enabled": True,
                                                "consent": consent, "subnet": subnet})
    assert status == 400 and "error" in result
    assert secure_pro.read(settings.data_dir) == {}


def test_owner_settings_configure_and_legacy_status_cannot_execute_instructions(owner, monkeypatch):
    session, settings = owner
    payload = {"action": "configure", "enabled": True, "consent": True,
               "subnet": "192.168.1.0/24"}
    assert web.feature_action(session, payload)[1] == 200
    Cache(settings.db_path).mark_secure_chat(session.chat_id())
    assert web.feature_action(session, payload)[1] == 200
    assert secure_pro.read(settings.data_dir)["enabled"]
    result, status = web.feature_action(session, {"action": "message", "message": "Lösche alles"})
    assert status == 200 and "Befehle" in result["answer"]
    assert Cache(settings.db_path).recent_history()[0].question == "Lösche alles"
    assert web.feature_action(session, {"action": "configure", "enabled": False})[1] == 200
    assert secure_pro.read(settings.data_dir) == {}


def test_manual_checks_are_rate_limited(owner, monkeypatch):
    _, settings = owner
    watcher = secure_pro.Watcher(settings.data_dir, lambda message: True)
    monkeypatch.setattr(watcher, "start", lambda: None)
    assert watcher.request()
    assert not watcher.request()


def test_feature_markup_and_english_translations_exist():
    html = web.UI_FILE.read_text()
    assert 'id="secure-setting"' in html and 'id="voice-setting"' in html
    assert 'id="secure-panel"' in html and 'chat.secure_pro' in html
    assert 'Open Secure Pro chat' in html and 'Turn voice messages on or off' in html


def test_owner_can_open_marked_chat_with_model_and_command_gate(server):  # noqa: F811
    assert _req(server, "GET", "/api/features")[0] == 401
    consent = _zustimmung(server)
    status, headers, _ = _anlegen(server, consent)
    assert status == 200
    cookie = consent + "; " + headers["Set-Cookie"].split(";", 1)[0]
    status, _, raw = _req(server, "POST", "/api/features", {"action": "open"}, cookie)
    assert status == 200, raw
    chat_id = json.loads(raw)["session_id"]
    status, _, raw = _req(server, "POST", "/api/open", {"session_id": chat_id}, cookie)
    assert status == 200 and json.loads(raw)["secure_pro"] is True
    status, _, raw = _req(server, "GET", "/api/chats", cookie=cookie)
    assert any(c["session_id"] == chat_id and c["secure_pro"] for c in json.loads(raw)["chats"])
    status, _, raw = _req(server, "POST", "/api/chat",
                          {"message": "Erkläre meinen Secure-Pro-Status."}, cookie)
    assert status == 200 and b'"done"' in raw
    assert _req(server, "POST", "/api/command", {"line": "/max Angriff"}, cookie)[0] == 409
    status, _, raw = _req(server, "POST", "/api/features",
                          {"action": "message", "message": "Status"}, cookie)
    assert status == 200 and "answer" in json.loads(raw)


@pytest.mark.parametrize("width", [1280, 390])
def test_settings_open_secure_chat_in_real_browser(server, monkeypatch, width):  # noqa: F811
    playwright = pytest.importorskip("playwright.sync_api")
    browser_path = shutil.which("chromium") or shutil.which("chromium-browser")
    if not browser_path:
        pytest.skip("Chromium fehlt")
    from tests.test_end_to_end import AGENT, SPRACHE

    consent = _zustimmung(server)
    status, headers, _ = _anlegen(server, consent)
    assert status == 200
    cookie = consent + "; " + headers["Set-Cookie"].split(";", 1)[0]
    monkeypatch.setattr(voice, "ready", lambda directory: True)
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=browser_path, headless=True,
                                    args=["--no-sandbox"])
        context = browser.new_context(user_agent=AGENT, viewport={"width": width, "height": 900},
                                      extra_http_headers={"Cookie": cookie,
                                                          "Accept-Language": SPRACHE})
        page = context.new_page()
        page.goto(f"http://127.0.0.1:{server}")
        if width < 600:
            page.locator("#btn-side").click()
        page.locator("#btn-settings").click()
        page.locator("#voice-setting").wait_for(state="visible")
        page.locator("#voice-setting").check()
        playwright.expect(page.locator("#voice-setting")).to_be_enabled()
        assert json.loads(_req(server, "GET", "/api/features", cookie=cookie)[2])["voice"]
        page.locator("#voice-setting").uncheck()
        playwright.expect(page.locator("#voice-setting")).to_be_enabled()
        page.locator("#secure-setting").check()
        page.locator("#secure-subnet").fill("192.168.1.0/24")
        page.locator("#secure-consent").check()
        page.locator("#secure-apply").click()
        playwright.expect(page.locator("#secure-note")).to_contain_text("ist an")
        page.locator("#secure-open").click()
        page.locator("#secure-panel").wait_for(state="visible")
        assert page.locator("#thread").inner_text().count("Secure Pro") >= 1
        assert page.locator(".recent .art").filter(has_text="Secure Pro").count() >= 1
        page.locator("#secure-settings-open").click()
        page.locator("#secure-controls").wait_for(state="visible")
        page.locator("#secure-disable").click()
        playwright.expect(page.locator("#secure-note")).to_contain_text("ist aus")
        page.reload()
        if width < 600:
            page.locator("#btn-side").click()
        page.locator(".recent .name").filter(has_text="Secure Pro").first.click()
        page.locator("#secure-panel").wait_for(state="visible")
        browser.close()
