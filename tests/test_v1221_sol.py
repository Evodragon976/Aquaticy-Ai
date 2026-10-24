"""12.2.1 Sol: entfernte Bilderstellung und Modellkonfiguration nur im Chat."""
from __future__ import annotations

import inspect
import json
from html.parser import HTMLParser

import pytest

from aquaticy import web
from aquaticy.agent import Agent
from tests.test_web import client, session, web_settings  # noqa: F401


@pytest.mark.parametrize("retired", [True, 1, "true", {}, [], 42])
def test_stale_image_mode_is_rejected_before_settings_or_model_work(
    client, session, monkeypatch, retired  # noqa: F811
):
    before = web.ui_state().read()
    calls = []
    monkeypatch.setattr(session, "ask", lambda *a, **kw: calls.append((a, kw)))
    status, body = client("POST", "/api/chat", {
        "message": "Eine normale Frage", "mode": "code", "image_mode": retired,
    })
    assert status == 400 and "gibt es nicht mehr" in json.loads(body)["error"]
    assert web.ui_state().read() == before and calls == []


def test_removed_tool_is_never_advertised_in_any_mode(settings):
    settings.api_keys.update({"MISTRAL_API_KEY": "fake", "NVIDIA_NIM_API_KEY": "fake"})
    agent = Agent(settings, cache=None)
    try:
        for mode in ("normal", "pro", "code"):
            agent.mode = mode
            for online in (False, True):
                agent.online = online
                assert "create_image" not in {t["function"]["name"] for t in agent.tools}
        assert "image_mode" not in inspect.signature(agent.ask).parameters
        assert not hasattr(agent.toolbox, "create_image")
    finally:
        agent.close()


def test_model_fields_belong_only_to_the_chat_model_form():
    class Forms(HTMLParser):
        def __init__(self):
            super().__init__()
            self.current = ""
            self.fields = {}

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag == "form":
                self.current = values.get("id", "")
            if tag in ("input", "select", "textarea") and values.get("name"):
                self.fields.setdefault(values["name"], []).append(self.current)

        def handle_endtag(self, tag):
            if tag == "form":
                self.current = ""

    parsed = Forms()
    source = web.UI_FILE.read_text()
    parsed.feed(source)
    for name in ("AQUATICY_MODEL", "AQUATICY_VISION_MODEL", "AQUATICY_SUBAGENT_MODEL",
                 "AQUATICY_CODE_MODEL", "AQUATICY_API_BASE"):
        assert parsed.fields[name] == ["model-settings"]
    assert parsed.fields["AQUATICY_SEARCH_BACKEND"] == ["settings"]
    assert 'id="picker-settings"' in source and 'id="model-close"' in source
    assert "Bilderstellung" not in source and "imageMode" not in source


def test_compact_phone_header_keeps_accessibility_and_reduced_motion():
    source = web.UI_FILE.read_text()
    assert 'id="chat-details"' in source and 'aria-controls="status"' in source
    assert 'setAttribute("aria-expanded", String(open))' in source
    assert "@media (max-width:599px)" in source and "body.chat-compact .topbar" in source
    assert "@media (prefers-reduced-motion:reduce)" in source
    assert "transition:none!important;animation:none!important" in source
