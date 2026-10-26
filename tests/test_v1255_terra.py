"""12.5.5 Terra: Fragen an die eigenen Dienste gehen nicht ins Web.

"Was sind meine Mails?", "Welche Termine habe ich morgen?", "Schalte meine Lichter
an", "Was ist in meinem Lager?" -- die Antwort steht im Postfach, im Kalender, in Home
Assistant oder in der Lagerverwaltung. Aquaticy erkennt das jetzt fest
(aquaticy/ownservices.py): keine Planung, keine Agenten, keine Websuche in diesem
Turn, der Dienst wird vorab gelesen. Ist er nicht eingerichtet, sagt Aquaticy, wo
er sich verbinden laesst -- statt im Netz zu suchen.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from aquaticy import web
from aquaticy.agent import Agent
from aquaticy.config import Settings
from aquaticy.ownservices import calendar_days, home_domain, missing_text, own_sources
from tests.test_guardrails import _reply
from tests.test_web import client, session, web_settings  # noqa: F401

JA = [
    ("was sind meine emails", "mail"),
    ("Was sind meine neuesten E-Mails?", "mail"),
    ("Hab ich neue Mails?", "mail"),
    ("welche mails habe ich bekommen", "mail"),
    ("do I have new emails", "mail"),
    ("check my inbox", "mail"),
    ("zeig mir meine Termine", "calendar"),
    ("Welche Termine habe ich morgen?", "calendar"),
    ("was steht morgen an", "calendar"),
    ("What's on my calendar today?", "calendar"),
    ("what meetings do I have today", "calendar"),
    ("schalte meine Lichter an", "home"),
    ("Schalte das Licht im Wohnzimmer aus", "home"),
    ("mach die Lampen im Flur an", "home"),
    ("Turn off the lights", "home"),
    ("dimme das Licht im Schlafzimmer auf 30 %", "home"),
    ("ist das Licht im Flur an", "home"),
    ("schalte über Home Assistant die Heizung an", "home"),
    ("was ist in meinem Lager", "storage"),
    ("Haben wir noch Schrauben im Lager?", "storage"),
    ("wo ist das Ladekabel in der Lagerverwaltung", "storage"),
]

NEIN = [
    "Wie schreibe ich eine gute E-Mail?",
    "Welche Termine hat das Bürgeramt?",
    "Was ist Home Assistant?",
    "Wie schalte ich in Blender ein Licht an?",
    "Was ist ein Lager?",
    "Wie funktioniert eine Lagerverwaltung Software?",
    "Was sind die neusten Nachrichten?",
    "Wie mache ich eine Lampe selbst?",
    "What is a calendar?",
    "Wie viele Lichter hat der Eiffelturm?",
    "Erkläre mir das Lager von Kugellagern",
    "",
]


@pytest.mark.parametrize(("frage", "quelle"), JA)
def test_questions_about_own_services_are_recognised(frage: str, quelle: str) -> None:
    assert quelle in own_sources(frage)


@pytest.mark.parametrize("frage", NEIN)
def test_other_questions_stay_normal(frage: str) -> None:
    assert own_sources(frage) == ()


def test_one_question_can_name_two_services() -> None:
    assert set(own_sources("Lies meine Mails und zeig meine Termine")) == {"mail", "calendar"}


def test_days_and_device_come_from_the_question() -> None:
    assert calendar_days("Termine heute") == 1
    assert calendar_days("Termine morgen") == 2
    assert calendar_days("meine Termine") == 7
    assert home_domain("schalte die Lichter an") == "light"
    assert home_domain("mach die Heizung wärmer") == "climate"
    assert home_domain("was ist im Haus los") == ""


def test_the_missing_text_says_where_to_connect() -> None:
    assert "Gmail & Kalender" in missing_text(("mail",))
    assert missing_text(("mail",)).startswith("Das kann ich noch nicht nachsehen: Dein Postfach")
    assert "Zuhause & Netz" in missing_text(("home", "storage"))
    assert "Gmail & Calendar" in missing_text(("calendar",), "en")


# -- Im Agenten --------------------------------------------------------------
class Modell:
    """Ein gestelltes Hauptmodell, das mitschreibt, welche Werkzeuge es bekam."""

    def __init__(self, *antworten: Any) -> None:
        self.antworten = list(antworten) or [_reply("Fertig.")]
        self.werkzeuge: list[set[str]] = []
        self.verlaeufe: list[list[dict[str, Any]]] = []

    def __call__(self, **kwargs: Any) -> Any:
        self.werkzeuge.append({t["function"]["name"] for t in kwargs.get("tools") or []})
        self.verlaeufe.append(list(kwargs.get("messages") or []))
        return self.antworten.pop(0) if len(self.antworten) > 1 else self.antworten[0]


def _kein_planer(*_: Any, **__: Any) -> Any:
    raise AssertionError("eigene Dienste brauchen keinen Planer")


@pytest.fixture
def google(settings: Settings) -> Settings:
    settings.google_enabled = True
    settings.google_client_id = "client"
    return settings


def _agent(settings: Settings, monkeypatch: pytest.MonkeyPatch, modell: Modell,
           ereignisse: list[tuple[str, dict[str, Any]]]) -> Agent:
    monkeypatch.setattr("litellm.completion", modell)
    monkeypatch.setattr("aquaticy.subagents.plan_request", _kein_planer)
    monkeypatch.setattr("aquaticy.subagents.plan_subtasks", _kein_planer)
    return Agent(settings, cache=None, on_event=lambda e, p: ereignisse.append((e, p)))


def test_own_mails_are_read_from_the_mailbox_not_the_web(
        google: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    modell = Modell(_reply("Du hast eine neue Mail von Anna."))
    ereignisse: list[tuple[str, dict[str, Any]]] = []
    agent = _agent(google, monkeypatch, modell, ereignisse)
    gelesen: list[dict[str, Any]] = []

    def postfach(query: str = "", count: int = 8) -> dict[str, Any]:
        gelesen.append({"query": query, "count": count})
        return {"query": query, "count": 1,
                "mails": [{"id": "abc", "from": "Anna", "subject": "Hallo"}]}

    monkeypatch.setattr(agent.toolbox, "mail_search", postfach)
    ergebnis = agent.ask("Was sind meine neuesten ungelesenen E-Mails?", stream=False,
                         structured=True, online=True)
    assert ergebnis.answer == "Du hast eine neue Mail von Anna."
    assert gelesen == [{"query": "is:unread", "count": 8}]
    # Das Modell sah weder Websuche noch Agenten -- und den Abruf schon im Verlauf.
    assert modell.werkzeuge and not modell.werkzeuge[0] & {"web_search", "fetch_page",
                                                         "search_news", "research_subtasks"}
    assert "mail_search" in modell.werkzeuge[0]
    assert any(m.get("role") == "tool" and m.get("name") == "mail_search"
               for m in modell.verlaeufe[0])
    assert "Such dafür nicht im Internet" in json.dumps(modell.verlaeufe[0],
                                                       ensure_ascii=False)
    namen = [e for e, _ in ereignisse]
    assert "planning" not in namen


def test_calendar_is_read_for_the_asked_day(google: Settings,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    modell = Modell()
    agent = _agent(google, monkeypatch, modell, [])
    tage: list[int] = []
    monkeypatch.setattr(agent.toolbox, "calendar_events",
                        lambda days=7, query="", count=10: tage.append(days) or {"events": []})
    agent.ask("Welche Termine habe ich morgen?", stream=False)
    assert tage == [2]


def test_lights_are_looked_up_in_home_assistant(settings: Settings,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    settings.ha_url, settings.ha_token, settings.ha_control = "http://ha.local:8123", "t", True
    modell = Modell()
    agent = _agent(settings, monkeypatch, modell, [])
    bereiche: list[str] = []
    monkeypatch.setattr(agent.toolbox, "ha_states",
                        lambda search="", domain="": bereiche.append(domain) or {"states": []})
    agent.ask("Schalte meine Lichter an", stream=False, structured=True, online=True)
    assert bereiche == ["light"]
    assert {"ha_states", "ha_call"} <= modell.werkzeuge[0]
    assert "web_search" not in modell.werkzeuge[0]


def test_storage_is_browsed(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.storage_url, settings.storage_access = "http://lager.local:3000", "read"
    modell = Modell()
    agent = _agent(settings, monkeypatch, modell, [])
    gestoebert: list[int] = []
    monkeypatch.setattr(agent.toolbox, "storage_browse",
                        lambda room_id=0, furniture_id=0: gestoebert.append(room_id)
                        or {"rooms": []})
    agent.ask("Was ist in meinem Lager?", stream=False)
    assert gestoebert == [0]
    assert "storage_find" in modell.werkzeuge[0] and "web_search" not in modell.werkzeuge[0]


def test_not_connected_means_a_clear_sentence_and_no_search(
        settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    modell = Modell()
    agent = _agent(settings, monkeypatch, modell, [])
    monkeypatch.setattr(agent.toolbox, "web_search", _kein_planer)
    ergebnis = agent.ask("Was sind meine Mails?", stream=False, structured=True, online=True)
    assert ergebnis.answer == missing_text(("mail",))
    assert modell.werkzeuge == [], "ohne Dienst braucht es kein Modell"
    agent.set_answer_language("en")
    assert "isn’t connected" in agent.ask("Schalte meine Lichter an", stream=False).answer


def test_a_web_search_the_model_tries_anyway_is_refused(
        google: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    aufruf = {"id": "web123456", "type": "function",
              "function": {"name": "web_search", "arguments": '{"query": "meine mails"}'}}
    modell = Modell(_reply("", [aufruf]), _reply("Hier sind deine Mails."))
    agent = _agent(google, monkeypatch, modell, [])
    monkeypatch.setattr(agent.toolbox, "mail_search",
                        lambda query="", count=8: {"mails": []})
    monkeypatch.setattr(agent.toolbox, "web_search", _kein_planer)
    agent.ask("Was sind meine Mails?", stream=False)
    antworten = [m for m in agent.messages if m.get("role") == "tool"
                 and m.get("name") == "web_search"]
    assert antworten and "eigene_dienste" in antworten[0]["content"]


def test_a_normal_question_keeps_the_web(google: Settings,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    modell = Modell()
    agent = _agent(google, monkeypatch, modell, [])
    agent.ask("Wie schreibe ich eine gute E-Mail?", stream=False)
    assert "web_search" in modell.werkzeuge[0]
    assert agent._eigene == ()


def test_the_council_does_not_answer_from_memory(google: Settings,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    google.council = True
    modell = Modell()
    agent = _agent(google, monkeypatch, modell, [])
    monkeypatch.setattr(agent, "_council_turn", _kein_planer)
    monkeypatch.setattr(agent.toolbox, "mail_search", lambda query="", count=8: {"mails": []})
    assert agent.ask("Was sind meine Mails?", stream=False).answer == "Fertig."


# -- Google verbinden, ohne vorher zu speichern ---------------------------------
GOOGLE_NAMEN = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "AQUATICY_GOOGLE",
                "AQUATICY_GOOGLE_WRITE")


@pytest.fixture
def leere_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> Any:
    """Eine eigene .env -- und Umgebungsvariablen, die nach dem Test wieder weg sind."""
    ziel = tmp_path / "formular.env"
    monkeypatch.setattr(web, "find_env_file", lambda: ziel)
    for name in GOOGLE_NAMEN:
        monkeypatch.setenv(name, "")
    web.SESSION.reload()
    return ziel


def test_connecting_saves_id_and_secret_from_the_form(
        client, leere_env: Any, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """Fund: ID und Secret eingetippt, aber nicht unten gespeichert -- dann stimmte man
    bei Google zu und bekam "Erst Client-ID und Secret speichern"."""
    import time

    from aquaticy.google import Tokens

    monkeypatch.setattr("aquaticy.google.exchange_code", lambda cid, secret, code, redirect:
                        Tokens(access_token="at", refresh_token="rt",
                               expires_at=time.time() + 3600))
    monkeypatch.setattr("aquaticy.google.Google.remember", lambda self, tokens: None)
    monkeypatch.setattr("aquaticy.google.Google.account", lambda self: "jemand@example.com")
    status, body = client("POST", "/api/google", {
        "action": "start", "client_id": "id-9.apps.googleusercontent.com",
        "client_secret": "geheim", "write": False})
    daten = json.loads(body)
    assert status == 200 and daten["ok"] is True, daten
    inhalt = leere_env.read_text(encoding="utf-8")
    assert "GOOGLE_CLIENT_ID=id-9.apps.googleusercontent.com" in inhalt
    assert "GOOGLE_CLIENT_SECRET=geheim" in inhalt
    assert "AQUATICY_GOOGLE=true" in inhalt and "AQUATICY_GOOGLE_WRITE=false" in inhalt
    status, seite = client("GET", f"/google?code=4/0AX&state={daten['state']}")
    assert status == 200 and b"jemand@example.com" in seite


def test_connecting_without_a_secret_says_so_before_google(
        client, leere_env: Any) -> None:  # noqa: F811
    status, body = client("POST", "/api/google", {
        "action": "start", "client_id": "id-9.apps.googleusercontent.com"})
    daten = json.loads(body)
    assert status == 200 and daten["ok"] is False and "url" not in daten
    assert "Client-Secret" in daten["error"]
