"""15.5.5: erschlossenes Wissen merken, ganze Saetze aus dem Gedaechtnis, Secure-Pro-Meldungen
an WhatsApp/Signal, "schreib mir auf WhatsApp", HTTPS im Heimnetz, Google-Ruecksprung."""

from __future__ import annotations

import socket
import ssl
import threading
from datetime import UTC, date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aquaticy import homename, memory_auto


def _store(settings: Any) -> Any:
    from aquaticy.memory import Memory

    return Memory(settings.db_path, settings.data_dir, settings.memory_key)


def _antwort(text: str = "Gern.") -> Any:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=text, tool_calls=None))])


# -- Erschlossenes Wissen -------------------------------------------------------------------------
def test_a_birth_date_is_found_and_replaces_age_and_birthday(settings: Any) -> None:
    store = _store(settings)
    memory_auto.store_facts(store, memory_auto.extract("Ich bin 20 Jahre alt."))
    fakten = memory_auto.extract("Ich bin am 15.03.2001 geboren.")
    assert [(f.slot, f.text) for f in fakten] == [("geburtsdatum", "Geboren am 15.03.2001.")]
    memory_auto.store_facts(store, fakten)
    assert [e.text for e in memory_auto.person_entries(store)] == ["Geboren am 15.03.2001."]


def test_the_age_is_always_computed_from_the_birth_date() -> None:
    assert memory_auto.age_on(date(2001, 3, 15), date(2026, 3, 14)) == 24
    assert memory_auto.age_on(date(2001, 3, 15), date(2026, 3, 15)) == 25
    text = memory_auto.with_age("Geboren am 15.03.2001.", "person:geburtsdatum")
    assert "Jahre alt" in text and memory_auto.with_age("Mag Tee.", "person:mag:tee") == "Mag Tee."


def test_model_birth_dates_are_checked() -> None:
    roh = ('{"fakten": [{"art": "geburtsdatum", "text": "Geboren am 1.4.2001"}, '
           '{"art": "geburtsdatum", "text": "Geboren am 31.02.2001"}, '
           '{"art": "geburtsdatum", "text": "Geboren am 01.01.2999"}]}')
    assert [f.text for f in memory_auto.parse_llm(roh)] == ["Geboren am 01.04.2001."]


def test_a_clarified_answer_is_learned_with_the_conversation(
        settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(settings)
    gesehen: list[str] = []

    def modell(einstellungen: Any, prompt: str) -> str:
        gesehen.append(prompt)
        return '{"fakten": [{"art": "geburtsdatum", "text": "Geboren am 10.07.2003."}]}'

    gespraech = ("Rückfrage: Wie alt bist du?\nAntwort des Nutzers: Heute in 123 Tagen hat "
                 "meine Mutter Geburtstag, 10 Tage vor meinem.\nAntwort des Assistenten: Du "
                 "bist am 10.07.2003 geboren.")
    neu = memory_auto.learn_with_model(
        settings, store, "Wie alt bin ich?\nHeute in 123 Tagen hat meine Mutter Geburtstag.",
        ask=modell, gespraech=gespraech)
    assert [f.text for f in neu] == ["Geboren am 10.07.2003."]
    assert "Antwort des Assistenten" in gesehen[0] and "errechnet" in gesehen[0]


def test_the_agent_passes_clarifications_but_not_after_untrusted_text(
        settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy.agent import Agent, AgentResult

    monkeypatch.setattr(memory_auto, "cloud_model", lambda s: True)
    geplant: list[Any] = []
    monkeypatch.setattr(memory_auto, "schedule_learning", lambda job: geplant.append(job))
    aufrufe: list[dict[str, Any]] = []
    monkeypatch.setattr(memory_auto, "learn_with_model",
                        lambda *a, **k: aufrufe.append(k) or [])
    agent = Agent(settings, cache=None)
    agent.toolbox.memory_blocked = False
    agent._plugin_turn = ""
    agent._turn_clarified = [("Wie alt bist du?", "Meine Mutter ist 10 Tage älter als ich.")]
    agent._memory_learn_later("Wie alt bin ich?", AgentResult(answer="Du bist 23."))
    geplant.pop()()
    assert "Antwort des Assistenten: Du bist 23." in aufrufe[-1]["gespraech"]
    agent.toolbox.untrusted_seen = True
    agent._memory_learn_later("Wie alt bin ich?", AgentResult(answer="Du bist 23."))
    geplant.pop()()
    assert "Antwort des Assistenten" not in aufrufe[-1]["gespraech"]


# -- Ganze Saetze aus dem Gedaechtnis -------------------------------------------------------------
@pytest.mark.parametrize(("frage", "art"), [
    ("wie heiße ich", "name"), ("Weißt du noch, wie ich heiße?", "name"),
    ("What's my name?", "name"), ("Wo wohne ich?", "wohnort"), ("Wie alt bin ich?", "alter"),
    ("Wann habe ich Geburtstag?", "geburtstag"), ("Wie heiße ich und wo wohne ich?", ""),
    ("Wer bist du?", ""),
])
def test_questions_about_oneself_are_recognised(frage: str, art: str) -> None:
    assert memory_auto.self_question(frage) == art


def test_answers_about_oneself_are_full_sentences(settings: Any) -> None:
    store = _store(settings)
    memory_auto.store_facts(store, memory_auto.extract(
        "Ich heiße Louis. Nenn mich Lou. Ich wohne in Bremen. Ich bin am 15.03.2001 geboren."))
    assert memory_auto.self_answer("wie heiße ich", store) == (
        "Du heißt Louis. Ich nenne dich Lou.")
    assert memory_auto.self_answer("Wo wohne ich?", store) == "Du wohnst in Bremen."
    assert memory_auto.self_answer("Wie alt bin ich?", store).startswith("Du bist ")
    assert memory_auto.self_answer("What's my name?", store, "en").startswith("Your name is")
    assert memory_auto.self_answer("Wann habe ich Geburtstag?", store) == (
        "Du hast am 15.03. Geburtstag.")


def test_the_agent_answers_at_once_without_the_model(settings: Any,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy.agent import Agent

    _store(settings).remember("Der Nutzer heißt Louis.", "person:name")
    aufrufe: list[Any] = []
    monkeypatch.setattr("litellm.completion", lambda **kw: aufrufe.append(kw) or _antwort())
    ergebnis = Agent(settings, cache=None).ask("wie heiße ich", stream=False)
    assert ergebnis.answer == "Du heißt Louis." and aufrufe == []


def test_unknown_facts_and_code_mode_go_to_the_model(settings: Any,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy.agent import Agent

    monkeypatch.setattr("litellm.completion", lambda **kw: _antwort("Das weiß ich nicht."))
    assert Agent(settings, cache=None).ask("wie heiße ich", stream=False).answer != (
        "Du heißt Louis.")
    _store(settings).remember("Der Nutzer heißt Louis.", "person:name")
    code = Agent(settings, cache=None).ask("wie heiße ich", mode="code", stream=False)
    assert "Louis" not in code.answer


# -- Secure Pro an WhatsApp/Signal ----------------------------------------------------------------
def test_messenger_alerts_are_retried_without_repeating_the_chat(tmp_path: Path) -> None:
    from aquaticy import secure_pro

    chat: list[str] = []
    watcher = secure_pro.Watcher(tmp_path, lambda text: False,
                                 lambda text: chat.append(text) or True)
    befund = ["Verdacht: 192.168.1.9 antwortet auf Port 4444."]
    assert watcher._deliver(befund, True, watcher.report, "Chat")
    assert not watcher._deliver(befund, True, watcher.notify, "Messenger")
    assert watcher._deliver(befund, True, lambda text: None, "Messenger")  # nichts gekoppelt
    assert len(chat) == 1


def _hub(tmp_path: Path, wanted: bool) -> Any:
    from aquaticy import messenger_native as nat
    from aquaticy.messenger_native import CONNECTED

    class Leitung:
        def __init__(self, *a: Any, **k: Any) -> None:
            self.sent: list[tuple[str, str]] = []
            self.running = False
            self.state = CONNECTED

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
    return hub


def test_alerts_reach_the_owner_even_with_the_chat_bridge_off(tmp_path: Path) -> None:
    hub = _hub(tmp_path, wanted=False)
    assert hub.notify_owner("normal") == []  # Coworker-Meldungen brauchen die Bruecke
    assert hub.alert_owner("[Aquaticy Secure Pro] Portscan") == ["whatsapp", "signal"]
    assert hub.transport("whatsapp").sent == [("self", "[Aquaticy Secure Pro] Portscan")]


def test_message_owner_sends_only_to_the_own_chat(tmp_path: Path) -> None:
    hub = _hub(tmp_path, wanted=True)
    assert hub.message_owner("signal", "Einkaufsliste") == "gesendet"
    assert hub.transport("signal").sent == [("self", "Einkaufsliste")]
    assert hub.message_owner("telegram", "x") == ""


# -- "Schreib mir das auf WhatsApp" ---------------------------------------------------------------
def test_the_messenger_tool_needs_a_coupling_and_limits_text(settings: Any) -> None:
    from aquaticy.tools import Toolbox

    box = Toolbox(settings, cache=None)
    assert "gekoppelt" in box.messenger_send("", "Hallo")["error"]
    gesendet: list[tuple[str, str]] = []
    box.messenger_sender = lambda m, t: gesendet.append((m, t)) or {"sent": True,
                                                                     "messenger": "whatsapp"}
    assert box.messenger_send("", "Hallo")["sent"] and gesendet == [("", "Hallo")]
    assert "zu lang" in box.messenger_send("", "x" * 3001)["error"]
    assert "whatsapp oder signal" in box.messenger_send("telegram", "x")["error"]


def test_the_tool_is_offered_only_with_a_sender(settings: Any) -> None:
    from aquaticy.agent import Agent
    from aquaticy.tools import CONFIRM_AFTER_UNTRUSTED

    agent = Agent(settings, cache=None)
    assert "messenger_send" not in {t["function"]["name"] for t in agent.tools}
    agent.toolbox.messenger_sender = lambda m, t: {"sent": True}
    assert "messenger_send" in {t["function"]["name"] for t in agent.tools}
    assert "messenger_send" in CONFIRM_AFTER_UNTRUSTED  # nach fremdem Text nur mit Ja


# -- HTTPS im Heimnetz ----------------------------------------------------------------------------
def test_the_home_certificate_is_trusted_through_the_own_ca(tmp_path: Path) -> None:
    zert, schluessel = homename.ensure_server_certificate(tmp_path, ["192.168.1.20"])
    assert {"aquaticy.local", "192.168.1.20"} <= homename._names_of(zert)
    assert oct((tmp_path / "home-tls" / "ca.key").stat().st_mode & 0o777) == "0o600"
    client = ssl.create_default_context(cafile=str(tmp_path / "home-tls" / "ca.crt"))
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(str(zert), str(schluessel))
    a, b = socket.socketpair()

    def antworten() -> None:
        with server.wrap_socket(a, server_side=True) as s:
            s.recv(1)

    faden = threading.Thread(target=antworten)
    faden.start()
    with client.wrap_socket(b, server_hostname="aquaticy.local") as c:
        c.send(b"x")
        assert c.version()
    faden.join(5)


def test_the_ca_may_only_sign_home_names(tmp_path: Path) -> None:
    from cryptography import x509

    homename.ensure_ca(tmp_path)
    ca = x509.load_pem_x509_certificate((tmp_path / "home-tls" / "ca.crt").read_bytes())
    grenzen = ca.extensions.get_extension_for_class(x509.NameConstraints)
    assert grenzen.critical
    namen = {str(n.value) for n in grenzen.value.permitted_subtrees or []}
    assert {"local", "home.arpa"} <= namen
    assert b"PRIVATE KEY" not in homename.ca_certificate(tmp_path)


def test_public_addresses_never_get_into_the_certificate() -> None:
    namen, ips = homename.local_names(["8.8.8.8", "192.168.0.5", "100.70.1.2"])
    assert "aquaticy.local" in namen and ips == ["100.70.1.2", "192.168.0.5"]


def test_tailscale_needs_https_in_the_tailnet(monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    import subprocess

    daten = {"Self": {"DNSName": "rechner.tail1234.ts.net."}, "CertDomains": []}
    monkeypatch.setattr(homename, "_tailscale", lambda *a, **k: subprocess.CompletedProcess(
        [], 0, json.dumps(daten), ""))
    zustand = homename.tailscale_state()
    assert zustand.name == "rechner.tail1234.ts.net" and not zustand.https
    assert "HTTPS Certificates" in zustand.reason
    daten["CertDomains"] = ["rechner.tail1234.ts.net"]
    assert homename.tailscale_state().https


def test_the_instructions_page_is_plain_and_bilingual() -> None:
    seite = homename.instructions_page()
    assert "/aquaticy-ca.crt" in seite and "iPhone" in seite and "English" in seite
    assert "<script" not in seite


# -- Google-Ruecksprung ---------------------------------------------------------------------------
@pytest.mark.parametrize(("host", "erwartet"), [
    ("127.0.0.1:8765", "http://127.0.0.1:8765/google"),
    ("localhost:8766", "http://localhost:8766/google"),
    ("[::1]:8765", "http://[::1]:8765/google"),
    ("192.168.1.20:8765", "http://localhost:8765/google"),
])
def test_google_returns_to_the_same_loopback_address(host: str, erwartet: str) -> None:
    from aquaticy.web import google_redirect

    assert google_redirect(host) == erwartet


def test_a_redirect_mismatch_explains_the_client_type() -> None:
    import httpx

    from aquaticy.google import _explain

    antwort = httpx.Response(400, json={"error": "redirect_uri_mismatch"})
    assert "Desktop-App" in _explain(antwort)


# -- Deutsche Zeit --------------------------------------------------------------------------------
def test_german_time_knows_summer_and_winter() -> None:
    from datetime import datetime

    from aquaticy import zeit

    winter = datetime(2026, 1, 15, 12, 0, tzinfo=UTC).timestamp()
    sommer = datetime(2026, 7, 15, 12, 0, tzinfo=UTC).timestamp()
    assert zeit.text(winter, "%H:%M") == "13:00" and zeit.kurz(zeit.aus_stempel(winter)) == "MEZ"
    assert zeit.text(sommer, "%H:%M") == "14:00" and zeit.kurz(zeit.aus_stempel(sommer)) == "MESZ"


def test_the_fallback_rule_matches_the_time_zone_database() -> None:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from aquaticy.zeit import _EURegel

    echt, regel = ZoneInfo("Europe/Berlin"), _EURegel()
    start = datetime(2025, 1, 1, tzinfo=UTC)
    for stunde in range(0, 2 * 365 * 24, 7):
        moment = start + timedelta(hours=stunde)
        assert moment.astimezone(echt).utcoffset() == moment.astimezone(regel).utcoffset()


def test_coworker_times_are_german_time_on_a_utc_server(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import time as zeitmodul
    from datetime import datetime

    from aquaticy import zeit
    from aquaticy.coworker_schedule import next_time

    monkeypatch.setenv("TZ", "UTC")
    if hasattr(zeitmodul, "tzset"):
        zeitmodul.tzset()
    try:
        for monat in (1, 7):
            jetzt = datetime(2026, monat, 10, 3, 0, tzinfo=UTC).timestamp()
            ziel = zeit.aus_stempel(next_time("daily", 8, 0, 0, now=jetzt))
            assert (ziel.hour, ziel.minute, ziel.day) == (8, 0, 10)
    finally:
        os.environ.pop("TZ", None)
        if hasattr(zeitmodul, "tzset"):
            zeitmodul.tzset()


def test_the_model_knows_the_german_time(settings: Any) -> None:
    from aquaticy.agent import Agent

    system = Agent(settings, cache=None).messages[0]["content"]
    assert "Uhr deutscher Zeit" in system and ("MEZ" in system or "MESZ" in system)
