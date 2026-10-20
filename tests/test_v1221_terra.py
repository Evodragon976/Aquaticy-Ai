"""12.2.1 Terra: Haus-Regel, kurze Takte und zeitgleiche Besitzer-Aenderungen."""
from __future__ import annotations

import re
import sqlite3
import time

import pytest

from aquaticy import coworker as cw
from aquaticy.cache import Cache
from aquaticy.coworker_context import connection_key, permits
from aquaticy.tools import Toolbox
from tests.test_agent import ScriptedLLM, _message, _tool_call
from tests.test_v1221 import configured


@pytest.mark.parametrize("seconds", cw.INTERVAL_SECONDS[1:])
@pytest.mark.parametrize("scheduled", [False, True])
def test_all_intervals_persist_and_control_the_next_run(settings, seconds, scheduled):
    store = cw.CoworkerStore(settings.db_path)
    colleague = store.add("Ava", "Recherchiere neue Lastenrad Angebote.",
                          schedule={"kind": "research"} if scheduled else None)
    updated = store.update(colleague.id, interval_seconds=seconds)
    assert updated.interval_seconds == seconds and updated.timing_version == 1
    assert updated.next_wake == pytest.approx(time.time() + seconds, abs=2)
    assert store.due() == []
    assert [c.id for c in store.due(updated.next_wake + 1)] == [colleague.id]
    store.note_run(colleague.id, state="fertig", notes="Fakten", reason="Modell",
                   next_wake=time.time() + 999999, timing_version=colleague.timing_version)
    persisted = cw.CoworkerStore(settings.db_path).get(colleague.id)
    assert persisted.next_wake == pytest.approx(time.time() + seconds, abs=2)
    assert persisted.interval_seconds == seconds and persisted.notes == "Fakten"


@pytest.mark.parametrize("invalid", [True, False, "30", 30.0, -1, 1, 29, 31, 999999, [], {}])
def test_invalid_intervals_cannot_partially_change_the_task(settings, invalid):
    store = cw.CoworkerStore(settings.db_path)
    colleague = store.add("Ava", "Suche neue Lastenrad Angebote.")
    with pytest.raises(ValueError):
        store.update(colleague.id, goal="Diese Aufgabe darf nicht gespeichert werden.",
                     interval_seconds=invalid)
    assert store.get(colleague.id).goal == colleague.goal


@pytest.mark.parametrize("scheduled", [False, True])
def test_old_run_cannot_overwrite_an_edited_clock_or_a_limit_pause(settings, scheduled):
    store = cw.CoworkerStore(settings.db_path)
    colleague = store.add("Ava", "Suche neue Lastenrad Angebote.",
                          schedule={"kind": "research"} if scheduled else None)
    store.update(colleague.id, interval_seconds=30)
    old = store.get(colleague.id)
    store.update(colleague.id, interval_seconds=0)
    wake = store.get(colleague.id).next_wake
    store.note_run(colleague.id, state="fertig", notes=None, reason="alter Lauf",
                   next_wake=time.time(), timing_version=old.timing_version)
    assert store.get(colleague.id).next_wake == wake
    store.postpone(colleague.id, 120, "Kontingent erreicht")
    hold = store.get(colleague.id).hold_until
    store.update(colleague.id, interval_seconds=30)
    assert store.get(colleague.id).next_wake >= hold
    if scheduled:
        store.set_preferences(colleague.id, {"schedule": {"rhythm": "hourly"}})
        assert store.get(colleague.id).interval_seconds == 0
        assert store.get(colleague.id).next_wake >= hold
    store.note_run(colleague.id, state="fertig", notes=None, reason="alter Lauf",
                   next_wake=time.time(), timing_version=old.timing_version)
    store.wake(colleague.id)
    store.set_enabled(colleague.id, True)
    assert store.get(colleague.id).hold_until == hold
    assert store.due() == []


def test_fast_research_reuses_one_chat_and_still_has_a_daily_limit(settings, monkeypatch):
    store = cw.CoworkerStore(settings.db_path)
    colleague = store.add("Ava", "Suche Lastenrad Neuigkeiten.", plan="normal",
                          schedule={"kind": "research", "structured": False})
    store.update(colleague.id, interval_seconds=30)
    llm = ScriptedLLM(_message(content="Erster Bericht."), _message(content="Zweiter Bericht."))
    monkeypatch.setattr("litellm.completion", llm)
    for _ in range(2):
        assert cw.run_scheduled(store.get(colleague.id), settings, "normal",
                                store=store) == "fertig"
    current = store.get(colleague.id)
    history = Cache(settings.db_path).recent_history(10)
    assert len(history) == 2 and {h.session_id for h in history} == {current.chat}
    assert current.next_wake == pytest.approx(time.time() + 30, abs=2)
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute("UPDATE coworkers SET runs_today = 48 WHERE id = ?", (colleague.id,))
    assert cw.run_scheduled(current, settings, "normal", store=store) == "Tagespensum erreicht"
    assert len(llm.calls) == 2 and store.due() == []


def test_adaptive_run_obeys_owner_interval_instead_of_model_sleep(settings, monkeypatch):
    store = cw.CoworkerStore(settings.db_path)
    colleague = store.add("Ava", "Suche Lastenrad Neuigkeiten.")
    store.update(colleague.id, interval_seconds=30)
    llm = ScriptedLLM(
        _message(tool_calls=[_tool_call("coworker_sleep", {"minuten": 900}, "sleep")]),
        _message(content="Fertig."))
    monkeypatch.setattr("litellm.completion", llm)
    assert cw.run_session(colleague, settings, "pro", store=store, vm=False) == "fertig"
    assert store.get(colleague.id).next_wake == pytest.approx(time.time() + 30, abs=2)


def test_fast_research_backs_off_when_quota_is_exhausted(settings, monkeypatch):
    from aquaticy import metering

    store = cw.CoworkerStore(settings.db_path)
    colleague = store.add("Ava", "Suche Lastenrad Neuigkeiten.",
                          schedule={"kind": "research"})
    store.update(colleague.id, interval_seconds=30)

    def exhausted(*args):
        raise metering.QuotaExceeded("Limit")

    monkeypatch.setattr(metering, "check", exhausted)
    assert cw.run_scheduled(colleague, settings, "pro", store=store) == "Kontingent erreicht"
    current = store.get(colleague.id)
    assert current.hold_until >= time.time() + 1700 and store.due() == []


def test_research_helper_is_callable_only_for_scheduled_research(settings):
    store = cw.CoworkerStore(settings.db_path)
    adaptive = store.add("Ava", "Suche neue Lastenrad Angebote.")
    research = store.add("Recherche", "Neue Lastenräder", schedule={"kind": "research"})
    visual = store.add("Sicht", "Neue Bilder", schedule={"kind": "visual",
                                                        "source_url": "https://example.org/"})
    box = Toolbox(settings)
    try:
        for colleague in (adaptive, research, visual):
            session = cw.Session(store, colleague, False)
            result = session.gate(box, "research_subtasks", {})
            assert (result is None) is (colleague.id == research.id)
            assert session.gate(box, "change_setting", {})["error"]
    finally:
        box.close()


@pytest.mark.parametrize("untrusted", [False, True])
def test_house_allow_never_falls_through_for_protected_or_broad_actions(settings, untrusted):
    configured(settings)
    store = cw.CoworkerStore(settings.db_path)
    colleague = store.add("Haus", "Schalte die Lichter nach Bedarf.", plan="ultra")
    store.set_rules(colleague.id, {"zuhause": "erlauben"}, settings=settings, ultra=True)
    box = Toolbox(settings)
    box.untrusted_seen = untrusted
    session = cw.Session(store, store.get(colleague.id), False, plan="ultra")
    try:
        for args in (
            {"domain": "lock", "service": "unlock", "entity_id": "lock.front"},
            {"domain": "alarm_control_panel", "service": "alarm_disarm",
             "entity_id": "alarm_control_panel.home"},
            {"domain": "light", "service": "turn_on", "entity_id": "all"},
            {"domain": "light", "service": "turn_on", "entity_id": "light.room",
             "data": {"brightness": 200}},
        ):
            assert session.gate(box, "ha_call", args)["wartet_auf_freigabe"]
            assert not session.ha_approved(box, args)
        store.set_rules(colleague.id, {"zuhause": "sperren"})
        assert session.gate(box, "ha_call", {"domain": "light", "service": "turn_on",
                                            "entity_id": "light.room"})["gesperrt"]
    finally:
        box.close()


def test_old_grants_are_removed_without_escalating_permissions(settings):
    store = cw.CoworkerStore(settings.db_path)
    colleague = store.add("Haus", "Schalte die Lichter nach Bedarf.", plan="ultra")
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute("DELETE FROM coworker_privacy WHERE version = 3")
        conn.execute("UPDATE coworkers SET ha_grants = ? WHERE id = ?",
                     ('[{"entity_id":"light.room","service":"turn_on"}]', colleague.id))
    migrated = cw.CoworkerStore(settings.db_path).get(colleague.id)
    assert migrated.rule("zuhause") == "fragen" and migrated.ha_binding == ""
    with sqlite3.connect(settings.db_path) as conn:
        assert conn.execute("SELECT ha_grants FROM coworkers").fetchone()[0] == ""
    configured(settings)
    assert not permits(migrated.ha_binding, {"domain": "light", "service": "turn_on",
                                           "entity_id": "light.room"}, settings, ultra=True)
    assert connection_key(settings)


def test_product_has_no_decorative_emoji_outside_coworkers_or_notes_sidebar_button():
    from aquaticy.web import UI_FILE

    source = UI_FILE.read_text()
    assert 'id="btn-notes"' not in source and '$("#btn-notes")' not in source
    assert '>Coworker<span' in source and '>🤝 Coworker' not in source
    assert "Home-Assistant-Dauerfreigaben" not in source
    for line in source.splitlines():
        if re.search(r"[\U0001f000-\U0001ffff]", line):
            assert "coworkerAvatar" in line or "CW_ART" in line
