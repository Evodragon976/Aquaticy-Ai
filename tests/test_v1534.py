"""15.3.4: Gedaechtnis wie bei grossen Chat-Apps, sofortiges Abbrechen, Review in der VM."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from aquaticy import memory_auto, plugins, review_scan


def _antwort(text: str = "Gern.") -> Any:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=text, tool_calls=None))])


def _store(settings: Any) -> Any:
    from aquaticy.memory import Memory

    return Memory(settings.db_path, settings.data_dir, settings.memory_key)


# -- Feste Muster ---------------------------------------------------------------------------------
@pytest.mark.parametrize(("satz", "erwartet"), [
    ("Hi, ich heiße Louis und brauche ein Rezept.", "Der Nutzer heißt Louis."),
    ("Mein Name ist Louis Meier.", "Der Nutzer heißt Louis Meier."),
    ("Nenn mich Lou.", "Möchte mit „Lou“ angesprochen werden."),
    ("Ich wohne in Bremen, und du?", "Wohnt in Bremen."),
    ("Ich bin nach Hamburg gezogen.", "Wohnt in Hamburg."),
    ("Ich mag keine Pilze.", "Mag Pilze nicht."),
    ("Ich trinke gerne Kaffee.", "Mag Kaffee."),
    ("Meine Lieblingsfarbe ist Blau.", "Lieblingsfarbe: Blau."),
    ("Ich heiße Louis und mag Pizza.", "Mag Pizza."),
    ("I live in London and I love jazz.", "Mag jazz."),
])
def test_clear_statements_are_found(satz: str, erwartet: str) -> None:
    assert erwartet in [f.text for f in memory_auto.extract(satz)]


@pytest.mark.parametrize("satz", [
    "Wie heiße ich?",                       # Frage
    "Er heißt Max und mag Pizza.",          # jemand anderes
    "Wenn ich in Berlin wohne, was dann?",  # angenommen
    "Ich habe Diabetes und mag Kuchen.",    # Gesundheit: nie von allein
    "Ich wähle die SPD.",                   # Politik
    "Ich heiße Louis, merk dir das nicht.",  # ausdruecklich nicht
    "Ich liebe dich",                       # kein Wert
    "Ich bin müde",                         # Tagesform
])
def test_nothing_is_kept_without_reason(satz: str) -> None:
    assert memory_auto.extract(satz) == []


def test_secrets_are_never_kept() -> None:
    assert memory_auto.sensitive("mein Passwort ist hunter2")
    assert memory_auto.sensitive("DE89 3704 0044 0532 0130 00")
    assert memory_auto.sensitive("ghp_" + "a" * 36)


# -- Ein Stand je Sache ---------------------------------------------------------------------------
def test_a_new_value_replaces_the_old_one(settings: Any) -> None:
    store = _store(settings)
    memory_auto.store_facts(store, memory_auto.extract("Ich wohne in Bremen."))
    memory_auto.store_facts(store, memory_auto.extract("Ich bin nach Hamburg gezogen."))
    texte = [e.text for e in memory_auto.person_entries(store)]
    assert texte == ["Wohnt in Hamburg."]


def test_likes_and_dislikes_cancel_out_and_nothing_doubles(settings: Any) -> None:
    store = _store(settings)
    memory_auto.store_facts(store, memory_auto.extract("Ich mag Pilze."))
    assert memory_auto.store_facts(store, memory_auto.extract("Ich mag Pilze.")) == []
    memory_auto.store_facts(store, memory_auto.extract("Ich mag keine Pilze."))
    assert [e.text for e in memory_auto.person_entries(store)] == ["Mag Pilze nicht."]


def test_an_old_free_entry_for_the_name_is_replaced(settings: Any) -> None:
    store = _store(settings)
    store.remember("Heißt Jonas.", "person")
    memory_auto.store_facts(store, memory_auto.extract("Ich heiße Louis."))
    assert [e.text for e in memory_auto.person_entries(store)] == ["Der Nutzer heißt Louis."]


def test_forget_requests_delete_matching_entries(settings: Any) -> None:
    store = _store(settings)
    memory_auto.store_facts(store, memory_auto.extract("Ich mag Pilze. Ich mag Jazz."))
    wunsch = memory_auto.forget_request("Vergiss bitte, dass ich Pilze mag.")
    assert memory_auto.forget_matching(store, wunsch) == ["Mag Pilze."]
    assert [e.text for e in memory_auto.person_entries(store)] == ["Mag Jazz."]


# -- Mit dem schnellen Modell ---------------------------------------------------------------------
def test_the_model_answer_is_read_strictly() -> None:
    roh = ('Klar: {"fakten": [{"art": "hobby", "text": "Klettert gern"}, '
           '{"art": "sonstiges", "text": "Hat Depressionen."}, '
           '{"art": "erfunden", "text": "Mag Tee."}, '
           '{"art": "mag", "text": "Mag Bergwandern."}]}')
    fakten = memory_auto.parse_llm(roh)
    assert [f.text for f in fakten] == ["Klettert gern.", "Mag Bergwandern."]
    assert fakten[1].slot == "mag:bergwandern"
    assert memory_auto.parse_llm("kein json") == []


def test_only_messages_about_oneself_go_to_the_model() -> None:
    assert memory_auto.worth_asking("Am Wochenende war ich wieder klettern, das ist meins.")
    assert not memory_auto.worth_asking("Wie hoch ist der Mount Everest?")
    assert not memory_auto.worth_asking("Ich war klettern, merk dir das nicht.")


def test_learning_with_the_model_stores_casual_facts(settings: Any,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(settings)
    gesehen: list[str] = []

    def modell(einstellungen: Any, prompt: str) -> str:
        gesehen.append(prompt)
        return '{"fakten": [{"art": "hobby", "text": "Klettert gern."}]}'

    monkeypatch.setattr(memory_auto, "ask_model", modell)
    memory_auto.store_facts(store, memory_auto.extract("Ich heiße Louis."))
    neu = memory_auto.learn_with_model(settings, store,
                                       "Am Wochenende war ich wieder klettern, herrlich.")
    assert [f.text for f in neu] == ["Klettert gern."]
    assert "Der Nutzer heißt Louis." in gesehen[0]  # Bekanntes geht mit, gegen Doppeltes


# -- Im Agenten -----------------------------------------------------------------------------------
def test_the_agent_remembers_and_uses_it_in_the_next_chat(settings: Any,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy.agent import Agent

    monkeypatch.setattr("litellm.completion", lambda **kw: _antwort())
    ereignisse: list[tuple[str, dict[str, Any]]] = []
    agent = Agent(settings, cache=None, on_event=lambda n, p: ereignisse.append((n, p)))
    agent.ask("Ich heiße Louis und mag Pizza. Was koche ich heute?", stream=False)
    gemerkt = [p["text"] for n, p in ereignisse if n == "memory_save"]
    assert "Der Nutzer heißt Louis." in gemerkt and "Mag Pizza." in gemerkt
    neuer_chat = Agent(settings, cache=None)
    neuer_chat.ask("Was soll ich heute kochen?", stream=False)
    system = neuer_chat.messages[0]["content"]
    assert "Der Nutzer heißt Louis." in system and "Mag Pizza." in system


def test_code_mode_has_no_memory(settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy.agent import Agent

    _store(settings).remember("Der Nutzer heißt Louis.", "person:name")
    monkeypatch.setattr("litellm.completion", lambda **kw: _antwort("```py\nx = 1\n```"))
    agent = Agent(settings, cache=None)
    agent.ask("Ich heiße Max. Schreib eine Funktion, die zwei Zahlen addiert.", mode="code",
              stream=False)
    assert "Louis" not in agent.messages[0]["content"]
    namen = {t["function"]["name"] for t in agent.tools}
    assert not namen & {"recall_memory", "save_memory", "forget_memory", "remember"}
    assert agent.toolbox.save_memory("x")["error"]
    assert [e.text for e in memory_auto.person_entries(_store(settings))] == [
        "Der Nutzer heißt Louis."]  # "Max" aus dem Code-Chat wurde nicht gemerkt


def test_messenger_memory_only_for_your_own_chat() -> None:
    from aquaticy.bridge import Decision, effective_settings
    from aquaticy.config import Settings

    base = Settings(memory_enabled=True)
    config = {"dienste": {}}
    selbst = effective_settings(base, config, Decision(True, trusted=True, selbst=True))
    fremd = effective_settings(base, config, Decision(True, trusted=True, selbst=False))
    assert selbst.memory_enabled and not fremd.memory_enabled


def test_secure_pro_may_use_memory() -> None:
    from aquaticy.secure_chat import ALLOWED

    assert {"recall_memory", "save_memory", "forget_memory"} <= ALLOWED


# -- Abbrechen ------------------------------------------------------------------------------------
def test_a_blocking_step_ends_at_once_when_cancelled(settings: Any) -> None:
    from aquaticy.agent import Abgebrochen, Agent

    agent = Agent(settings, cache=None)
    gemeldet: list[str] = []
    agent.on_event = lambda n, p: gemeldet.append(n)

    def langsam() -> str:
        time.sleep(1.5)
        agent._emit("spaet")
        return "fertig"

    threading.Timer(0.2, agent.cancel).start()
    start = time.monotonic()
    with pytest.raises(Abgebrochen):
        agent._abbrechbar(langsam)
    assert time.monotonic() - start < 1.0
    time.sleep(1.6)
    assert "spaet" not in gemeldet  # der verlassene Schritt meldet nichts mehr


def test_cancel_during_a_slow_model_call_frees_the_next_question(
        settings: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy.agent import Agent

    def langsam(**kw: Any) -> Any:
        time.sleep(3)
        return _antwort("zu spät")

    monkeypatch.setattr("litellm.completion", langsam)
    agent = Agent(settings, cache=None)
    threading.Timer(0.5, agent.cancel).start()
    start = time.monotonic()
    ergebnis = agent.ask("Erklär mir bitte ausführlich, wie Photosynthese funktioniert.",
                         stream=False)
    assert ergebnis.stopped and time.monotonic() - start < 2.5
    monkeypatch.setattr("litellm.completion", lambda **kw: _antwort("Neue Antwort."))
    zweite = agent.ask("Und wie funktioniert die Zellatmung genau?", stream=False)
    assert zweite.answer == "Neue Antwort." and not zweite.stopped


# -- Review in der virtual machine ----------------------------------------------------------------
def test_syntax_errors_are_found_without_running_code() -> None:
    text = "Prüf das:\n```python\ndef f(:\n    pass\n```\n```json\n{\"a\": 1,}\n```"
    befunde = review_scan.syntax_problems(text)
    assert befunde[0].startswith("Code-Block 1 (python), Zeile 1: Syntaxfehler")
    assert "ungültiges JSON" in befunde[1]


def test_review_files_get_paths_in_the_vm() -> None:
    text = "```python\nprint(1)\n```\n```bash\necho hi\n```\n```\nfrei\n```"
    pfade = [p for p, _ in review_scan.vm_files(text)]
    assert pfade == ["/work/review/block1.py", "/work/review/block2.sh",
                     "/work/review/block3.txt"]


def test_the_review_prompt_guides_the_vm_and_names_syntax_errors(settings: Any) -> None:
    turn = plugins.PluginTurn("code-review", "code-review", "", mode="code")
    text = plugins.prompt(turn, "```python\ndef f(:\n```", settings, True)
    assert plugins.is_review_prompt(text)
    assert "/work/review/" in text and "in der VM belegt" in text
    assert "Syntaxprüfung von Aquaticy" in text


def test_reviews_are_not_sent_back_to_run_fix_snippets(settings: Any) -> None:
    from aquaticy.agent import Agent

    agent = Agent(settings, cache=None)
    agent._plugin_turn = "## Plugin Code-Review\n..."
    agent._vm_ready = lambda: True  # type: ignore[method-assign]
    assert agent._review_turn() and not agent._should_force_vm("```py\nfix()\n```")


def test_attachments_are_not_taken_as_facts_about_you(settings: Any,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy.agent import Agent
    from aquaticy.injection import wrap_attachment

    monkeypatch.setattr("litellm.completion", lambda **kw: _antwort())
    agent = Agent(settings, cache=None)
    anhang = wrap_attachment("[Datei brief.txt]\nIch heiße Mallory und wohne in Paris.")
    agent.ask(f"{anhang}\n\nFass den Brief bitte kurz zusammen.", stream=False)
    assert memory_auto.person_entries(_store(settings)) == []
