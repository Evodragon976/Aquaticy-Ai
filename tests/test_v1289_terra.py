"""Widerruf, Antwortgrenzen und isolierte Messenger-Einstellungen."""

import time

import pytest

from aquaticy import bridge
from aquaticy.bridge_native import NativeResponder
from aquaticy.config import Settings
from aquaticy.messenger_native import Incoming
from tests.test_bridge import FakeAgent, cfg


class Transport:
    def __init__(self):
        self.sent = []

    def send(self, chat, text):
        self.sent.append(text)

    def typing(self, msg, on):
        pass

    def mark_read(self, msg):
        pass


@pytest.mark.parametrize("messenger", ["whatsapp", "signal"])
@pytest.mark.parametrize("change", ["disable", "permissions", "ban"])
@pytest.mark.parametrize("fails", [False, True])
def test_revoked_access_discards_inflight_reply(tmp_path, change, fails, messenger):
    settings = Settings(data_dir=tmp_path)
    bridge.set_config(settings, messenger, {"an": True, "dienste": {"mail": "lesen"}})
    paused = []

    def answer(*args):
        if change == "disable":
            bridge.set_config(settings, messenger, {"an": False})
        elif change == "permissions":
            bridge.set_config(settings, messenger, {"dienste": {"mail": "aus"}})
        else:
            paused.append(True)
        if fails:
            raise RuntimeError("Failed")
        return "Private Antwort"

    responder = NativeResponder(lambda: settings, answer, paused=lambda: bool(paused))
    transport = Transport()
    msg = Incoming(messenger, "self", "Frage", "id1", time.time(),
                   from_me=True, self_chat=True)
    responder(msg, transport)
    assert transport.sent == []


def test_failed_replies_also_use_hourly_limit(tmp_path):
    settings = Settings(data_dir=tmp_path)
    bridge.set_config(settings, "signal", {"an": True})

    def fail(*args):
        raise RuntimeError("Failed")

    responder = NativeResponder(lambda: settings, fail)
    transport = Transport()
    for i in range(bridge.MAX_REPLIES_PER_HOUR + 2):
        msg = Incoming("signal", "self", "Frage", str(i), time.time(),
                       from_me=True, self_chat=True)
        responder(msg, transport)
    assert len(transport.sent) == bridge.MAX_REPLIES_PER_HOUR


def test_untrusted_commands_do_not_evict_other_chat_settings(tmp_path):
    settings = Settings(data_dir=tmp_path)
    answerer = bridge.AgentAnswerer(lambda: settings, agent_factory=FakeAgent)
    for i in range(answerer.MAX_AGENTS):
        answerer("/pro", bridge.Decision(True, trusted=True), cfg(), str(i), "whatsapp")
    before = {k: dict(v) for k, v in answerer._mobile.items()}
    for command in ("/switch", "/pro", "/export", "/quit"):
        answerer(command, bridge.Decision(True), cfg(), "stranger", "whatsapp")
    assert answerer._mobile == before


@pytest.mark.parametrize("change", ["config", "paused", "addon"])
def test_desktop_bridge_also_rechecks_before_sending(tmp_path, change):
    settings = Settings(data_dir=tmp_path)
    config = bridge.set_config(settings, "whatsapp", {"an": True})
    blocked = []

    def answer(*args):
        if change == "config":
            bridge.set_config(settings, "whatsapp", {"an": False})
        else:
            blocked.append(True)
        return "Private Antwort"

    from tests.test_bridge import FakeDriver

    driver = FakeDriver()
    driver.offen = "Ich"
    runner = bridge.Bridge(lambda: settings, lambda name: driver, answer,
                           paused=lambda: bool(blocked) and change == "paused",
                           ready=lambda s, m: "aus" if blocked and change == "addon" else "")
    report = bridge.Report("whatsapp")
    runner._answer(bridge.StateStore(settings), driver, "whatsapp", config, "key", "Ich",
                   bridge.Transcript(), bridge.Decision(True, trusted=True, selbst=True),
                   "Frage", report)
    assert not driver.gesendet and report.beantwortet == 0


def test_delivery_fails_closed_when_settings_cannot_be_read():
    def unavailable():
        raise RuntimeError("unavailable")

    assert not bridge.delivery_allowed(unavailable, "signal", {"an": True}, None)
