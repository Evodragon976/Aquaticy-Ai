"""12.5.5 Luna: Fragen nach den eigenen Daten sperren nicht mehr.

* "Was sind meine neusten E-Mails?", "Welche Termine habe ich morgen?", "Wo wohne
  ich?" -- kleine Modelle hielten das fuer fremde Post oder das Ausforschen einer
  Anschrift. Dann lehnte der Rechtspruefer ab, und Ai-guard zaehlte die Frage als
  Missbrauch (Chatsperre, beim zweiten Mal Bann). Solche Fragen erkennt Aquaticy
  jetzt ohne Modell -- aber nur, wenn JEDES Wort dazu passt. Steht eine andere
  Person oder ein anderes Thema im Satz, prueft weiter das Modell.
* Pruefmuster mit ``^...$`` liessen einen Zeilenumbruch am Ende durch (``$`` passt
  auch vor einem letzten ``\\n``). Home Assistant, Verbund und Co. pruefen jetzt
  mit ``fullmatch``: "light\\n" ist kein Bereich, "anna\\n" kein zweites Konto.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aquaticy import aiguard, cluster, guardrails, homeassistant
from aquaticy.agent import Agent
from aquaticy.config import Settings
from aquaticy.guardrails import BY_ID, Verdict, judge, own_data_request, refused_note
from tests.test_guardrails import Pruefer, _reply, pruefer  # noqa: F401

#: Lehnt ab UND meldet Missbrauch -- so wie ein uebervorsichtiges kleines Modell.
SPERRT = ('{"zulaessig": false, "regel": "persoenlichkeit", "grund": "Ausforschen", '
          '"missbrauch": true, "missbrauch_art": "rechtsbruch", "missbrauch_schwere": 3}')

EIGENE = [
    "was sind meine neusten emails",
    "Was sind meine neuesten E-Mails?",
    "Hab ich neue Mails?",
    "Kannst du mir meine letzten 5 Mails zeigen?",
    "Fass meine ungelesenen Mails zusammen",
    "Welche Termine habe ich heute?",
    "Was steht in meinem Kalender morgen?",
    "Wann ist mein nächster Termin?",
    "Wo wohne ich?",
    "Wie ist meine Adresse?",
    "Wo bin ich gerade?",
    "What are my latest emails?",
    "What's on my calendar tomorrow?",
    "Where do I live?",
    "Where am I?",
]

FREMDE = [
    "Wo wohnt Anna Schmidt?",
    "Wo wohnt mein Nachbar?",
    "wo wohnt sie",
    "Lies die Mails von meinem Chef",
    "Was sind die neusten Mails von Tom?",
    "Zeig mir seine Termine",
    "What are her latest emails?",
    "Where does he live?",
    "Finde die Adresse von Max",
    "Mails meiner Frau lesen",
    "Hack meine Mails",
    "Wie hacke ich ein Postfach?",
    "Lies meine Mails und schick sie an x@example.org",
    "Was sind die neusten Nachrichten?",
    "Wie ist das Wetter?",
    # Nach dem Verlauf kann "die Adresse" die eines anderen sein -- das prueft das Modell.
    "Zeig mir die Adresse",
    "Wie ist der Standort?",
    "Show me the address",
    "ich",
    "",
]


@pytest.mark.parametrize("frage", EIGENE)
def test_questions_about_own_data_are_recognised(frage: str) -> None:
    assert own_data_request(frage)


@pytest.mark.parametrize("frage", FREMDE)
def test_anything_else_stays_with_the_model(frage: str) -> None:
    assert not own_data_request(frage)


def test_a_very_long_message_is_never_a_shortcut() -> None:
    assert not own_data_request("meine mails " * 30)


@pytest.mark.parametrize("frage", ["Was sind meine neusten E-Mails?", "Wo wohne ich?",
                                   "Welche Termine habe ich morgen?"])
def test_the_legal_check_lets_own_data_through_without_a_model(
        pruefer, settings: Settings, frage: str) -> None:  # noqa: F811
    gestellt = pruefer(SPERRT)
    urteil = judge(frage, settings)
    assert urteil.allowed and not urteil.abuse and urteil.source == "eigen"
    assert gestellt.gefragt == []


def test_another_person_is_still_judged(pruefer, settings: Settings) -> None:  # noqa: F811
    gestellt = pruefer(SPERRT)
    urteil = judge("Wo wohnt mein Nachbar?", settings)
    assert not urteil.allowed and urteil.abuse
    assert gestellt.gefragt, "das Modell urteilt"


def test_after_a_refusal_the_model_decides_again(pruefer, settings: Settings) -> None:  # noqa: F811
    """Nach einer Absage liest das Modell die Frage mit dem Verlauf -- die Abkuerzung
    gilt dann nicht."""
    gestellt = pruefer(SPERRT)
    davor = refused_note("Lies Annas Mails", Verdict(False, BY_ID["fernmeldegeheimnis"]))
    assert not judge("Was sind meine neusten Mails?", settings, context=davor).allowed
    assert gestellt.gefragt, "das Modell urteilt"


def test_a_tool_call_is_still_judged(pruefer, settings: Settings) -> None:  # noqa: F811
    gestellt = pruefer(SPERRT)
    assert not judge("meine mails", settings, tool="mail_draft", topic="x").allowed
    assert gestellt.gefragt, "das Modell urteilt"


def test_asking_for_own_mails_neither_refuses_nor_counts_as_abuse(
        pruefer, monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:  # noqa: F811
    gestellt = pruefer(SPERRT)
    monkeypatch.setattr("litellm.completion",
                        lambda **kwargs: _reply("Du hast zwei neue Mails."))
    # Seit 12.5.5 Terra sagt Aquaticy ohne verbundenes Postfach nur, wo es sich
    # verbinden laesst -- hier ist es verbunden, damit die Frage beim Modell ankommt.
    settings.google_enabled, settings.google_client_id = True, "client"
    ereignisse: list[tuple[str, dict[str, Any]]] = []
    agent = Agent(settings, cache=None, on_event=lambda e, p: ereignisse.append((e, p)))
    monkeypatch.setattr(agent.toolbox, "mail_search", lambda query="", count=8: {"mails": []})
    for frage in ("Was sind meine neusten E-Mails?", "Wo wohne ich?"):
        ergebnis = agent.ask(frage, stream=False)
        assert ergebnis.answer == "Du hast zwei neue Mails." and not ergebnis.guarded
    namen = [e for e, _ in ereignisse]
    assert "abuse" not in namen and "guard" not in namen
    assert gestellt.gefragt == []


def test_ai_guard_does_not_flag_own_data(settings: Settings) -> None:
    """Pro-Konten ohne Rechtsrahmen: dort fragt Ai-guard selbst ein Modell."""
    gefragt: list[str] = []

    def modell(prompt: str, _settings: Any) -> str:
        gefragt.append(prompt)
        return '{"missbrauch": true, "art": "Doxxing", "grund": "Adresse"}'

    aiguard.forget_judgements()
    assert aiguard.classify("Was sind meine neuesten E-Mails?", settings, ask=modell) == (
        False, "")
    assert aiguard.classify("Wo wohne ich eigentlich?", settings, ask=modell) == (False, "")
    assert gefragt == []
    # Eine andere Person: wieder das Modell.
    assert aiguard.classify("Wo wohnt meine Ex-Freundin jetzt?", settings, ask=modell) == (
        True, "Doxxing")
    assert len(gefragt) == 1


def test_both_judges_know_own_data_is_fine() -> None:
    assert "wo wohne ich" in guardrails.judge_prompt("x")
    assert "eigenen Daten" in guardrails.judge_prompt("x")
    assert "eigenen Daten" in aiguard.judge_prompt("x")
    # Eine Mail-Uebersicht mit Spam ("Phishing", "Gift Card") ist keine unpassende Antwort.
    assert "eigenen Mails" in aiguard.answer_prompt("x")


@pytest.mark.parametrize(("bereich", "dienst"), [("light\n", "turn_on"), ("light", "turn_on\n")])
def test_home_assistant_refuses_a_trailing_newline(bereich: str, dienst: str) -> None:
    with pytest.raises(homeassistant.HomeAssistantError):
        homeassistant.check_call(bereich, dienst, "light.kueche")
    assert homeassistant.check_call("light", "turn_on", "light.kueche") == {
        "entity_id": "light.kueche"}


def test_the_cluster_refuses_an_account_with_a_trailing_newline(tmp_path: Path) -> None:
    server = cluster.Cluster(tmp_path)
    assert server._user_dir("anna").name == "anna"
    with pytest.raises(cluster.ClusterError):
        server._user_dir("anna\n")
