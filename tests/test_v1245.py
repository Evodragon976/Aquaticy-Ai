"""12.4.5 Sol: Fehler- und Sicherheitsrunde.

* Rueckfragen: eine Antwort zaehlt nur, wenn gerade eine Frage offen ist -- und nur
  eine je Frage. Vorher beantwortete ein doppelt geschicktes "ja" oder eine
  verspaetete Antwort still die naechste Frage derselben Reihe.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from aquaticy import web
from aquaticy.agent import AgentResult
from tests.test_web import FakeAgent, client, session, web_settings  # noqa: F401


class ZweiFragen(FakeAgent):
    """Stellt zwei Rueckfragen hintereinander (wie ask_user mit 1/2, 2/2)."""

    def __init__(self, nach_erster: Any = None) -> None:
        super().__init__()
        self.antworten: list[str] = []
        self.nach_erster = nach_erster

    def ask(self, question: str, **_: Any) -> AgentResult:
        self.asked.append(question)
        for nummer, frage in enumerate(("Welches Budget?", "Welche Farbe?"), start=1):
            self.on_event("ask", {"question": frage, "options": [], "index": nummer,
                                  "total": 2})
            self.antworten.append(self.ask_handler(frage, []))
            if nummer == 1 and self.nach_erster is not None:
                self.nach_erster()
        self.on_event("done", {"tool_calls": 0})
        return AgentResult(answer="fertig")


def _warte(bedingung: Any, sekunden: float = 5.0) -> None:
    ende = time.monotonic() + sekunden
    while not bedingung() and time.monotonic() < ende:
        time.sleep(0.01)


def test_a_double_sent_answer_never_answers_the_next_question(
        client, session: web.ChatSession, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    monkeypatch.setattr(web.ChatSession, "ANSWER_TIMEOUT", 5)
    ergebnisse: list[bool] = []

    def doppelt() -> None:
        # Der Browser schickt die Antwort auf Frage 1 ein zweites Mal (Doppelklick,
        # wiederholte Anfrage) -- nachdem Frage 1 schon beantwortet ist.
        ergebnisse.append(session.answer("bis 800"))

    agent = ZweiFragen(nach_erster=doppelt)
    session._agent = agent

    def browser() -> None:
        _warte(lambda: getattr(session, "_frage_offen", True))
        ergebnisse.append(session.answer("bis 800"))
        _warte(lambda: len(agent.antworten) == 1 and getattr(session, "_frage_offen", True))
        ergebnisse.append(session.answer("blau"))

    threading.Thread(target=browser, daemon=True).start()
    status, _ = client("POST", "/api/chat", {"message": "Laptop gesucht"})
    assert status == 200
    assert agent.antworten == ["bis 800", "blau"]
    assert ergebnisse == [True, False, True]


def test_an_answer_after_giving_up_is_refused(client, session: web.ChatSession,  # noqa: F811
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web.ChatSession, "ANSWER_TIMEOUT", 0.2)
    spaet: list[bool] = []

    def zu_spaet() -> None:
        # Frage 1 ist abgelaufen; jetzt kommt die Antwort doch noch.
        spaet.append(session.answer("zu spaet"))

    agent = ZweiFragen(nach_erster=zu_spaet)
    session._agent = agent
    client("POST", "/api/chat", {"message": "Laptop gesucht"})
    assert spaet == [False]
    assert agent.antworten == ["", ""]


def test_two_answers_to_one_question_count_once(
        client, session: web.ChatSession, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    monkeypatch.setattr(web.ChatSession, "ANSWER_TIMEOUT", 5)
    agent = ZweiFragen()
    session._agent = agent
    ergebnisse: list[bool] = []

    def browser() -> None:
        _warte(lambda: getattr(session, "_frage_offen", True))
        ergebnisse.extend([session.answer("erste"), session.answer("zweite")])
        _warte(lambda: len(agent.antworten) == 1 and getattr(session, "_frage_offen", True))
        ergebnisse.append(session.answer("dritte"))

    threading.Thread(target=browser, daemon=True).start()
    client("POST", "/api/chat", {"message": "Laptop gesucht"})
    assert agent.antworten == ["erste", "dritte"]
    assert ergebnisse == [True, False, True]
