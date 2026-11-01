"""Messenger-Verlaeufe, Desktop-Freigaben und vollstaendige Ausgabefilter."""

import pytest

from aquaticy import bridge
from aquaticy.bridge_native import coworker_text
from aquaticy.config import Settings
from aquaticy.desktop import payment_data
from tests.test_bridge import FakeAgent, FakeDriver, cfg


@pytest.mark.parametrize("change", ["service", "credential", "role", "expiry"])
def test_export_revalidates_cached_history(tmp_path, change):
    settings = Settings(data_dir=tmp_path)
    now = [0.0]
    answerer = bridge.AgentAnswerer(lambda: settings, agent_factory=FakeAgent,
                                    clock=lambda: now[0])
    config = cfg(dienste={"mail": "lesen"})
    decision = bridge.Decision(True, trusted=True, selbst=change != "role")
    answerer("Private Mail", decision, config, "self", "signal")
    if change == "service":
        config = cfg(dienste={"mail": "aus"})
    elif change == "credential":
        settings.ha_token = "changed-test-token"
    elif change == "role":
        decision = bridge.Decision(True, trusted=True, selbst=True)
    else:
        now[0] += answerer.IDLE_SECONDS + 1
    result = answerer("/export", decision, config, "self", "signal")
    assert "Private Mail" not in result
    assert "self" not in answerer._agents


def test_desktop_can_send_with_restricted_group_rights(tmp_path, monkeypatch):
    from aquaticy import addons

    settings = Settings(data_dir=tmp_path)
    raw = bridge.set_config(settings, "whatsapp", {"an": True, "wer": "gruppen"})
    monkeypatch.setattr(addons, "rights_of", lambda *args: {"wo": "eigene"})
    config = bridge.capped_config(settings, "whatsapp", raw)
    assert config["wer"] == "einzeln"
    driver = FakeDriver()
    driver.offen = "Ich"
    runner = bridge.Bridge(lambda: settings, lambda name: driver, lambda *args: "Antwort",
                           ready=lambda *args: "")
    report = bridge.Report("whatsapp")
    runner._answer(bridge.StateStore(settings), driver, "whatsapp", config, "key", "Ich",
                   bridge.Transcript(), bridge.Decision(True, trusted=True, selbst=True),
                   "Frage", report)
    assert report.beantwortet == 1 and driver.gesendet


def test_desktop_rechecks_group_rights_at_delivery(tmp_path, monkeypatch):
    from aquaticy import addons

    settings = Settings(data_dir=tmp_path)
    config = bridge.set_config(settings, "whatsapp", {"an": True, "wer": "gruppen"})
    rights = {"wo": "alle"}
    monkeypatch.setattr(addons, "rights_of", lambda *args: rights)
    driver = FakeDriver()
    driver.offen = "Gruppe"
    driver.current_title = lambda: ("Gruppe", True)

    def answer(*args):
        rights["wo"] = "eigene"
        return "Antwort"

    runner = bridge.Bridge(lambda: settings, lambda name: driver, answer, ready=lambda *args: "")
    report = bridge.Report("whatsapp")
    runner._answer(bridge.StateStore(settings), driver, "whatsapp", config, "key", "Gruppe",
                   bridge.Transcript(), bridge.Decision(True, group=True), "Frage", report)
    assert report.beantwortet == 0 and not driver.gesendet


@pytest.mark.parametrize("field", ["name", "title", "formatted_body"])
def test_coworker_payment_filter_covers_the_entire_rendered_message(field):
    iban = "DE89 3704 0044 0532 0130 00"
    name = iban if field == "name" else "Ava"
    title = iban if field == "title" else "Meldung"
    body = "DE89 **3704** 0044 0532 0130 00" if field == "formatted_body" else "Hallo"
    text = coworker_text(name, title, body)
    assert not payment_data(text)
    assert "DE89" not in text
    assert "Zahlungsdaten" in text
