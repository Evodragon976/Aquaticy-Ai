"""13.0.1 Luna: Den ganzen Text einer eigenen Mail zeigen sperrt der Rechtsprüfer nicht mehr.

"Was sind meine neusten Mails?" ging, "Bitte sende mir den ganzen Text von der Email xy"
danach nicht: Die Folgefrage galt nicht als Frage an das eigene Postfach, und der Prüfer
las im Verlauf fremde Absender und lehnte ab (Fernmeldegeheimnis). Jetzt erkennt der Code
solche Folgefragen, sagt dem Prüfer, dass es um das eigene Postfach geht, und die Regeln
sagen ausdrücklich: Die eigene Post vollständig zu lesen ist erlaubt.
"""

from __future__ import annotations

from typing import Any

import pytest

from aquaticy import guardrails
from aquaticy.agent import Agent
from aquaticy.config import Settings
from aquaticy.guardrails import judge, judge_prompt, own_data_request, own_service_note
from aquaticy.ownservices import followup_sources, own_sources
from tests.test_guardrails import pruefer  # noqa: F401

ERLAUBT = ('{"zulaessig": true, "regel": "", "grund": "", "missbrauch": false, '
           '"missbrauch_art": "", "missbrauch_schwere": 0}')


# -- Erkennen ---------------------------------------------------------------------------------
@pytest.mark.parametrize("frage", [
    "Bitte sende mir den ganzen Text von der Email xy",
    "Sende mir den ganzen Text von der Email von Amazon",
    "Schick mir bitte die komplette Mail von der Bank",
    "Kannst du mir die letzte E-Mail vorlesen",
    "Zeig mir den vollständigen Inhalt der Mail von Anna",
    "Please show me the full text of the email from Amazon",
    "Gib mir die ganze Mail",
])
def test_a_request_to_show_a_mail_is_about_the_own_mailbox(frage: str) -> None:
    assert own_sources(frage) == ("mail",)


@pytest.mark.parametrize("frage", [
    "Zeig mir, wie man eine gute Mail schreibt",
    "Wie schreibe ich eine gute E-Mail?",
    "Was gibt es Neues in den Nachrichten?",
    "Sende mir ein Rezept für Pfannkuchen",
    "Schreib eine Mail an meinen Chef",
])
def test_other_questions_stay_normal(frage: str) -> None:
    assert own_sources(frage) == ()
    assert followup_sources(frage, ("mail",)) == ()


@pytest.mark.parametrize("frage", [
    "lies mir die zweite vor",
    "Und was steht in der Mail von der Bank genau?",
    "Gib mir den vollständigen Inhalt der Nachricht von Anna",
    "zeig den ganzen Text",
    "show me the whole text",
    "lies sie mir vor",
    "Kannst du mir die Mail von Amazon zeigen",
])
def test_a_follow_up_after_mails_means_the_same_mailbox(frage: str) -> None:
    assert followup_sources(frage, ("mail",)) == ("mail",)
    assert followup_sources(frage, ()) == own_sources(frage), "ohne Mails davor: normal"
    assert followup_sources(frage, ("calendar",)) == own_sources(frage)


def test_follow_ups_are_bounded() -> None:
    assert followup_sources("die zweite " * 100, ("mail",)) == ()
    assert followup_sources("", ("mail",)) == ()


# -- Der Pruefer ---------------------------------------------------------------------------------
def test_the_note_for_the_judge_names_only_the_own_mailbox() -> None:
    notiz = own_service_note(("mail",))
    assert "eigene, verbundene Postfach" in notiz and "zulässig" in notiz
    assert "Alles andere an der Anfrage prüfst du wie sonst" in notiz
    assert own_service_note(()) == "" and own_service_note(("home", "storage")) == ""
    assert "Kalender" in own_service_note(("calendar",))
    assert guardrails._HINWEIS not in notiz, "keine Absage-Markierung"


def test_the_rules_say_that_own_mail_may_be_read_in_full() -> None:
    allgemein = judge_prompt("Bitte sende mir den ganzen Text von der Email xy")
    assert "'ganzer Text der Mail von Amazon'" in allgemein, "ein typischer Fehlalarm"
    assert "Fernmeldegeheimnis schützt Post" not in allgemein, "die Einzelheiten nur bei Bedarf"
    prompt = judge_prompt("Bitte sende mir den ganzen Text von der Email xy",
                          context="Nutzer: meine Mails" + own_service_note(("mail",)))
    assert "Fernmeldegeheimnis schützt Post vor fremden Lesern" in prompt
    assert "fremde Konten oder Gespräche heimlich mitzulesen" in prompt
    assert guardrails.RULES_VERSION >= "2026-11-02", "alte gemerkte Urteile gelten nicht mehr"


def test_a_long_history_never_cuts_the_note() -> None:
    verlauf = "Aquaticy AI: " + "Mail von Anna, Betreff Rechnung. " * 300
    prompt = judge_prompt("lies mir die zweite vor", context=verlauf + own_service_note(("mail",)))
    notiz = own_service_note(("mail",)).strip()
    assert notiz in prompt and "ausgelassen" in prompt
    assert len(prompt) < 12_000 + len(notiz)


def test_the_note_does_not_skip_the_model(pruefer, settings: Settings) -> None:  # noqa: F811
    """Der Hinweis hilft dem Modell -- er ersetzt es nicht (Beleidigungen, Missbrauch)."""
    gestellt = pruefer(ERLAUBT)
    urteil = judge("Bitte sende mir den ganzen Text von der Email xy", settings,
                   context="Nutzer: Was sind meine neusten Mails?" + own_service_note(("mail",)))
    assert urteil.allowed and gestellt.gefragt, "das Modell urteilt"
    assert "Info an den Prüfer" in gestellt.gefragt[0][0]
    assert not own_data_request("Bitte sende mir den ganzen Text von der Email xy")


def test_the_own_data_shortcut_still_works_with_the_note(pruefer, settings: Settings) -> None:  # noqa: F811
    gestellt = pruefer(ERLAUBT)
    urteil = judge("Was sind meine neusten Mails?", settings, context=own_service_note(("mail",)))
    assert urteil.allowed and urteil.source == "eigen" and gestellt.gefragt == []


# -- Der ganze Weg im Agenten -------------------------------------------------------------------
def test_the_agent_tells_the_judge_about_the_mailbox_in_a_follow_up(
        pruefer, settings: Settings) -> None:  # noqa: F811
    gestellt = pruefer(ERLAUBT)
    agent = Agent(settings, cache=None)
    try:
        agent.ask("Was sind meine neusten Mails?", stream=False)
        assert gestellt.gefragt == [], "die Abkuerzung fuer eigene Daten"
        agent.ask("Bitte sende mir den ganzen Text von der Email xy", stream=False)
        assert "Info an den Prüfer" in gestellt.gefragt[-1][0]
        anzahl = len(gestellt.gefragt)
        agent.ask("lies mir die zweite vor", stream=False)
        assert len(gestellt.gefragt) == anzahl + 1
        assert "Info an den Prüfer" in gestellt.gefragt[-1][0], "Folgefrage"
        assert agent._eigene == ("mail",)
    finally:
        agent.close()


def test_a_normal_question_after_mails_gets_no_note(pruefer, settings: Settings) -> None:  # noqa: F811
    gestellt = pruefer(ERLAUBT)
    agent = Agent(settings, cache=None)
    try:
        agent.ask("Was sind meine neusten Mails?", stream=False)
        _frage(agent, "Wie schreibe ich eine gute E-Mail an einen Kunden?")
        assert gestellt.gefragt and "Info an den Prüfer" not in gestellt.gefragt[-1][0]
        assert agent._eigene == ()
    finally:
        agent.close()


def _frage(agent: Agent, text: str) -> Any:
    """Nur die Rechtspruefung -- ohne Modell fuer die Antwort."""
    agent._eigene = followup_sources(text, getattr(agent, "_eigene_davor", ()))
    agent._eigene_davor = agent._eigene
    return agent._legal_check(text)


def test_a_new_chat_forgets_the_mails_a_reopened_one_remembers(settings: Settings) -> None:
    agent = Agent(settings, cache=None)
    try:
        agent._eigene_davor = ("mail",)
        agent.clear()
        assert agent._eigene_davor == ()
        agent.resume("alt", [("Was sind meine neusten Mails?", "1. Amazon 2. Bank")])
        assert agent._eigene_davor == ("mail",)
        agent.resume("anders", [("Wie wird das Wetter?", "Sonnig")])
        assert agent._eigene_davor == ()
    finally:
        agent.close()
