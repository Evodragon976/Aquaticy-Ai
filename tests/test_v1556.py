"""15.5.6: Meldungen von Secure Pro und Coworkern auch an die eingetragenen Nummern."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aquaticy import messenger_native as nat
from aquaticy.messenger_native import CONNECTED, STARTING


@pytest.mark.parametrize(("eintrag", "erwartet"), [
    ("+49 151 2345678", "+491512345678"), ("0049 151 2345678", "+491512345678"),
    ("0151 2345678", ""), ("Anna", ""), ("+49", ""),
])
def test_only_numbers_with_country_code_get_messages(eintrag: str, erwartet: str) -> None:
    assert nat.recipient_number(eintrag) == erwartet


def _hub(tmp_path: Path, nummern: list[str], wanted: bool = True,
         state: str = CONNECTED) -> Any:
    class Leitung:
        def __init__(self, *a: Any, **k: Any) -> None:
            self.sent: list[tuple[str, str]] = []
            self.running = False
            self.state = state
            self.store = SimpleNamespace(who=lambda name: "+4917000000000")

        def has_session(self) -> bool:
            return True

        def own_chat(self) -> str:
            return "self"

        def status(self) -> Any:
            return SimpleNamespace(state=self.state)

        def send(self, chat: str, text: str) -> None:
            self.sent.append((chat, text))

        def available(self) -> tuple[bool, str]:
            return True, ""

        def start(self) -> None:
            self.running = True

        def stop(self) -> None:
            self.running = False

    hub = nat.NativeHub(tmp_path, lambda *a: None, lambda name: wanted,
                        factories={"whatsapp": Leitung, "signal": Leitung})
    hub.recipients = lambda name: nummern
    return hub


NUMMERN = ["+49 151 2345678", "0049 160 1111111", "Anna", "0151 999", "+49 170 00000000"]


def test_coworker_messages_reach_own_chat_and_entered_numbers(tmp_path: Path) -> None:
    hub = _hub(tmp_path, NUMMERN)
    assert hub.notify_owner("[Aquaticy Coworker Mia] fertig") == ["whatsapp", "signal"]
    assert [ziel for ziel, _ in hub.transport("signal").sent] == [
        "self", "+491512345678", "+491601111111"]  # eigene Nummer nicht doppelt
    assert [ziel for ziel, _ in hub.transport("whatsapp").sent] == [
        "self", "491512345678@s.whatsapp.net", "491601111111@s.whatsapp.net"]


def test_secure_pro_alerts_reach_entered_numbers(tmp_path: Path) -> None:
    hub = _hub(tmp_path, NUMMERN)
    hub.alert_owner("[Aquaticy Secure Pro] Portscan")
    assert len(hub.transport("signal").sent) == 3


def test_asking_for_a_message_only_writes_to_the_own_chat(tmp_path: Path) -> None:
    hub = _hub(tmp_path, NUMMERN)
    assert hub.message_owner("signal", "Einkaufsliste") == "gesendet"
    assert hub.transport("signal").sent == [("self", "Einkaufsliste")]


def test_without_the_bridge_only_the_owner_gets_alerts(tmp_path: Path) -> None:
    hub = _hub(tmp_path, NUMMERN, wanted=False)
    hub.alert_owner("[Aquaticy Secure Pro] Portscan")
    assert hub.transport("signal").sent == [("self", "[Aquaticy Secure Pro] Portscan")]


def test_waiting_messages_reach_every_recipient_after_connecting(tmp_path: Path) -> None:
    hub = _hub(tmp_path, NUMMERN[:1], state=STARTING)
    hub.notify_owner("später")
    eins = hub.transport("signal")
    eins.state = CONNECTED
    hub._flush("signal")
    assert sorted(ziel for ziel, _ in eins.sent) == ["+491512345678", "self"]


def test_removed_numbers_get_no_waiting_messages(tmp_path: Path) -> None:
    nummern = list(NUMMERN[:1])
    hub = _hub(tmp_path, nummern, state=STARTING)
    hub.notify_owner("später")
    nummern.clear()
    eins = hub.transport("signal")
    eins.state = CONNECTED
    hub._flush("signal")
    assert [ziel for ziel, _ in eins.sent] == ["self"]


def test_each_recipient_has_its_own_hourly_limit(tmp_path: Path) -> None:
    hub = _hub(tmp_path, NUMMERN[:1])
    for i in range(nat.NOTIFY_PER_HOUR + 3):
        hub.notify_owner(f"m{i}")
    gesendet = hub.transport("signal").sent
    assert sum(z == "self" for z, _ in gesendet) == nat.NOTIFY_PER_HOUR
    assert sum(z == "+491512345678" for z, _ in gesendet) == nat.NOTIFY_PER_HOUR


def test_at_most_ten_extra_recipients(tmp_path: Path) -> None:
    viele = [f"+49151000000{i:02d}" for i in range(15)]
    hub = _hub(tmp_path, viele)
    hub.notify_owner("x")
    assert len(hub.transport("signal").sent) == 1 + nat.MAX_RECIPIENTS


def test_the_server_uses_numbers_only_with_the_numbers_scope(settings: Any) -> None:
    from aquaticy import bridge, web

    bridge.set_config(settings, "signal", {"an": True, "wer": "selbst",
                                           "nummern": ["+49 151 2345678"]})
    hub = web._build_native_hub(lambda: SimpleNamespace(settings=lambda: settings), None,
                                settings.data_dir / "native-test")
    try:
        assert hub.recipients("signal") == []
        bridge.set_config(settings, "signal", {"an": True, "wer": "nummern",
                                               "nummern": ["+49 151 2345678"]})
        assert hub.recipients("signal") == ["+49 151 2345678"]
    finally:
        hub.stop()
