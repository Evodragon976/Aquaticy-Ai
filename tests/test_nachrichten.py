"""11.1.0: "Was sind die neusten Nachrichten?" bekommt Meldungen, keine Quellenliste.

Gefunden: Im Standardmodus entschied das Modell selbst, ob es nachsieht,
und viele antworteten aus dem Gedaechtnis mit "Aktuelles gibt es bei
Tagesschau, Spiegel ...". Suchte es doch, fand es fuer "Nachrichten" nur die
Startseiten der Nachrichtenseiten. Alles hier ohne Netz.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from aquaticy.agent import Agent
from aquaticy.config import Settings
from aquaticy.models import SearchResult
from aquaticy.news import feeds_for, headlines, is_generic, news_request
from aquaticy.tools import Toolbox


@pytest.mark.parametrize(("frage", "thema"), [
    ("Was sind die neusten Nachrichten?", ""),
    ("Zeig mir die neuesten Nachrichten", ""),
    ("Nachrichten", ""),
    ("Was ist heute passiert?", ""),
    ("Was gibt's Neues?", ""),
    ("Was war gestern in den Nachrichten?", ""),
    ("latest news", ""),
    ("Neueste Nachrichten zu Tesla", "tesla"),
    ("News zur Bundesliga", "bundesliga"),
    ("Was ist so los in Köln?", "köln"),
])
def test_news_questions_are_recognised(frage: str, thema: str) -> None:
    anfrage = news_request(frage)
    assert anfrage is not None
    assert anfrage.topic == thema


@pytest.mark.parametrize("frage", [
    "Habe ich neue Nachrichten auf WhatsApp?",
    "Welche Nachrichten hat mir Oma geschickt?",
    "Schreib eine Nachricht an Oma",
    "Wie schreibe ich eine gute Nachricht?",
    "Was sind Nachrichtenagenturen?",
    "Meldungen im Log",
    "Finde Cafés mit WLAN",
    "Nachrichten " + "sehr lange Aufgabe " * 20,
])
def test_other_questions_are_left_alone(frage: str) -> None:
    assert news_request(frage) is None


def test_a_search_without_topic_counts_as_headlines() -> None:
    assert is_generic("Nachrichten heute")
    assert is_generic("aktuelle Nachrichten Deutschland")
    assert is_generic("top news today")
    assert not is_generic("Tesla")
    assert not is_generic("Nachrichten Mönchengladbach")


def test_feeds_follow_country_and_language() -> None:
    assert "tagesschau.de" in feeds_for("de", "de")[0]
    assert "orf.at" in feeds_for("at", "de")[0]
    assert "srf.ch" in feeds_for("ch", "de")[0]
    assert "bbci.co.uk" in feeds_for("us", "en")[0]


def _leser(feeds: list[str], limit: int = 6) -> dict[str, Any]:
    quelle = feeds[0].split("/")[2]
    if "spiegel" in quelle:
        raise RuntimeError("Feed kaputt")
    if "zdf" in quelle:
        return {"eintraege": [
            {"titel": "Bundestag beschließt Haushalt", "link": "https://www.zdf.de/a",
             "datum": "Tue, 13 Oct 2026 09:00:00 +0200", "zusammenfassung": "Mit knapper Mehrheit.",
             "quelle": "www.zdf.de"},
        ]}
    return {"eintraege": [
        {"titel": "Bundestag beschließt Haushalt", "link": "https://www.tagesschau.de/b",
         "datum": "Tue, 13 Oct 2026 08:00:00 +0200", "zusammenfassung": "Doppelt.",
         "quelle": quelle},
        {"titel": f"Sturm über der Nordsee ({quelle})", "link": f"https://{quelle}/sturm",
         "datum": "Tue, 13 Oct 2026 11:30:00 +0200", "zusammenfassung": "Fähren fallen aus.",
         "quelle": quelle},
        {"titel": "Ohne Link", "link": "javascript:alert(1)", "datum": "", "quelle": quelle},
    ]}


def test_headlines_are_merged_newest_first_without_duplicates() -> None:
    treffer = headlines("de", "de", reader=_leser)
    titel = [t.title for t in treffer]
    assert titel[0].startswith("Sturm über der Nordsee")
    assert titel.count("Bundestag beschließt Haushalt") == 1
    assert "Ohne Link" not in titel
    assert all(t.url.startswith("https://") for t in treffer)
    assert "13.10." in treffer[0].snippet
    assert [t.rank for t in treffer] == list(range(1, len(treffer) + 1))


def test_search_news_without_topic_returns_headlines(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setattr("aquaticy.news.headlines", lambda land, sprache, menge: [
        SearchResult(title="Sturm über der Nordsee", url="https://www.tagesschau.de/sturm",
                     snippet="[13.10. 11:30 · tagesschau.de] Fähren fallen aus.")])

    def nie(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("ohne Thema keine Stichwortsuche")

    monkeypatch.setattr("aquaticy.tools.search_news", nie)
    ergebnis = Toolbox(settings).search_news("Nachrichten heute")
    assert ergebnis["results"][0]["title"] == "Sturm über der Nordsee"
    assert "Keine Liste" in ergebnis["note"]


def test_search_news_falls_back_when_no_feed_answers(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setattr("aquaticy.news.headlines", lambda *a, **k: [])
    monkeypatch.setattr("aquaticy.tools.search_news", lambda query, **kwargs: [
        SearchResult(title="Meldung", url="https://news.example/a", snippet="x")])
    assert Toolbox(settings).search_news("Nachrichten")["results"][0]["title"] == "Meldung"


def test_a_topic_still_goes_to_the_news_search(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    gefragt: list[str] = []

    def suche(query: str, **kwargs: Any) -> list[SearchResult]:
        gefragt.append(query)
        return [SearchResult(title="Tesla senkt Preise", url="https://news.example/t", snippet="")]

    monkeypatch.setattr("aquaticy.tools.search_news", suche)
    Toolbox(settings).search_news("Tesla")
    assert gefragt and gefragt[0].startswith("Tesla")



class _Modell:
    def __init__(self, antwort: str) -> None:
        self.antwort = antwort
        self.aufrufe: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> Any:
        self.aufrufe.append(kwargs)
        nachricht = SimpleNamespace(content=self.antwort, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=nachricht)])


def test_the_agent_fetches_headlines_before_the_model_answers(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setattr("aquaticy.news.headlines", lambda land, sprache, menge: [
        SearchResult(title="Sturm über der Nordsee", url="https://www.tagesschau.de/sturm",
                     snippet="[13.10. 11:30 · tagesschau.de] Fähren fallen aus.")])
    modell = _Modell("Sturm über der Nordsee: Fähren fallen aus (tagesschau.de, 11:30).")
    monkeypatch.setattr("litellm.completion", modell)

    agent = Agent(settings, cache=None, toolbox=Toolbox(settings))
    ergebnis = agent.ask("Was sind die neusten Nachrichten?", stream=False)

    assert "Sturm" in ergebnis.answer
    verlauf = modell.aufrufe[0]["messages"]
    aufruf = next(m for m in verlauf if m.get("tool_calls"))
    call = aufruf["tool_calls"][0]
    assert call["function"]["name"] == "search_news"
    assert len(call["id"]) == 9 and call["id"].isalnum()
    antwort = next(m for m in verlauf if m.get("role") == "tool")
    assert antwort["tool_call_id"] == call["id"]
    assert "Sturm über der Nordsee" in antwort["content"]


def test_a_topic_question_prefetches_that_topic(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    gefragt: list[str] = []

    def suche(query: str, **kwargs: Any) -> list[SearchResult]:
        gefragt.append(query)
        return []

    monkeypatch.setattr("aquaticy.tools.search_news", suche)
    monkeypatch.setattr("litellm.completion", _Modell("Nichts Neues zu Tesla."))
    Agent(settings, cache=None, toolbox=Toolbox(settings)).ask(
        "Neueste Nachrichten zu Tesla", stream=False)
    assert gefragt and gefragt[0].startswith("tesla")


def test_other_questions_get_no_prefetch(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setattr("aquaticy.news.headlines", lambda *a, **k: pytest.fail("nicht gefragt"))
    modell = _Modell("Hallo!")
    monkeypatch.setattr("litellm.completion", modell)
    Agent(settings, cache=None, toolbox=Toolbox(settings)).ask(
        "Finde Cafés mit WLAN", stream=False)
    assert not any(m.get("tool_calls") for m in modell.aufrufe[0]["messages"])


def test_offline_there_is_no_prefetch(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setattr("aquaticy.news.headlines", lambda *a, **k: pytest.fail("offline"))
    modell = _Modell("Ohne Web kann ich nicht nachsehen.")
    monkeypatch.setattr("litellm.completion", modell)
    Agent(settings, cache=None, toolbox=Toolbox(settings)).ask(
        "Was sind die neusten Nachrichten?", stream=False, online=False)
    assert not any(m.get("tool_calls") for m in modell.aufrufe[0]["messages"])


def test_the_prompt_asks_for_the_news_themselves() -> None:
    from aquaticy.agent import SYSTEM_PROMPT

    assert "Eine Liste von Nachrichtenseiten ist keine Antwort" in SYSTEM_PROMPT


def test_the_tool_result_is_valid_json(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setattr("aquaticy.news.headlines", lambda land, sprache, menge: [
        SearchResult(title="A", url="https://www.tagesschau.de/a", snippet="x")])
    modell = _Modell("A.")
    monkeypatch.setattr("litellm.completion", modell)
    Agent(settings, cache=None, toolbox=Toolbox(settings)).ask("Nachrichten", stream=False)
    antwort = next(m for m in modell.aufrufe[0]["messages"] if m.get("role") == "tool")
    assert json.loads(antwort["content"])["results"][0]["title"] == "A"
