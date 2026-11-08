"""15.7.7: Persoenliche Antworten, Geburtsdaten und Loeschwuensche bleiben korrekt."""

import json
from datetime import date

import pytest

from aquaticy import coworker, memory_auto
from aquaticy.agent import Agent
from aquaticy.memory import Memory


@pytest.fixture
def memory(settings):
    return Memory(settings.db_path, settings.data_dir, settings.memory_key)


def test_fast_personal_answers_use_the_newest_saved_value(memory):
    memory.remember('Der Nutzer heißt Earlier.', 'person:name')
    memory.remember('Der Nutzer heißt Current.', 'person:name')
    assert memory_auto.self_answer('Wie heiße ich?', memory) == 'Du heißt Current.'


def test_f024_fast_answers_do_not_bypass_the_configured_secret_filter(settings, memory):
    settings.api_keys['MISTRAL_API_KEY'] = 'ConfiguredSecretValuePrivate123'
    memory.remember('Der Nutzer heißt ConfiguredSecretValuePrivate123.', 'person:name')
    agent = Agent(settings, cache=None)
    agent._plugin_turn = ""
    try:
        assert agent._memory_answer('Wie heiße ich?') == ''
    finally:
        agent.close()


def test_f025_coworker_fast_answers_need_the_personal_context_consent(settings, memory):
    memory.remember('Der Nutzer heißt PrivateName.', 'person:name')
    store = coworker.CoworkerStore(settings.db_path)
    cw = store.add('Ava', 'Lies aktuelle Nachrichten.', plan='pro')
    session = coworker.Session(store, cw, vm=False, plan='pro')
    agent = coworker.coworker_agent_class()(settings, session)
    agent._plugin_turn = ""
    try:
        assert agent._memory_answer('Wie heiße ich?') == ''
    finally:
        agent.close()


@pytest.mark.parametrize('wunsch', ['Vergiss mein Geburtsdatum.', 'Vergiss meinen Geburtstag.',
                                     'Vergiss mein Alter.'])
def test_f026_birth_dates_and_derived_private_values_can_really_be_forgotten(memory, wunsch):
    memory.remember('Geboren am 15.03.2001.', 'person:geburtsdatum')
    memory.remember('Mag Musik.', 'person:mag:musik')
    forgotten = memory_auto.forget_matching(memory, memory_auto.forget_request(wunsch))
    assert forgotten == ['Geboren am 15.03.2001.']
    assert [entry.text for entry in memory.all_entries()] == ['Mag Musik.']
    assert memory_auto.self_answer('Wie alt bin ich?', memory) == ''


def test_f027_new_age_corrections_cannot_leave_a_contradicting_birth_date(memory, monkeypatch):
    monkeypatch.setattr(memory_auto, 'zeit_heute', lambda: date(2026, 11, 8))
    memory_auto.store_facts(memory, memory_auto.extract('Ich bin am 15.03.2001 geboren.'))
    memory_auto.store_facts(memory, memory_auto.extract('Ich bin 20 Jahre alt.'))
    assert not [entry for entry in memory.all_entries() if entry.topic == 'person:geburtsdatum']
    assert '25' not in memory_auto.self_answer('Wie alt bin ich?', memory)


def test_f028_reconfirming_a_birth_date_also_cleans_obsolete_derived_facts(memory):
    fact = memory_auto.Fact('geburtsdatum', 'Geboren am 15.03.2001.')
    memory_auto.store_facts(memory, [fact])
    memory.remember('Ist 17 Jahre alt.', 'person:alter')
    memory.remember('Hat am 01.01. Geburtstag.', 'person:geburtstag')
    memory_auto.store_facts(memory, [fact])
    assert [(entry.topic, entry.text) for entry in memory.all_entries()] == [
        ('person:geburtsdatum', fact.text)]


@pytest.mark.parametrize('text', ['Heißt Lisa.', 'Der Nutzer heisst Lisa.', 'Name: Lisa.'])
def test_f029_valid_model_name_facts_are_usable_by_the_fast_answer_path(memory, text):
    facts = memory_auto.parse_llm(json.dumps({'fakten': [{'art': 'name', 'text': text}]}))
    assert facts
    memory_auto.store_facts(memory, facts)
    assert memory_auto.self_answer('Wie heiße ich?', memory) == 'Du heißt Lisa.'


@pytest.mark.parametrize('text', ['Die Mutter wurde am 15.03.2001 geboren.',
                                 'Sein Freund wurde am 15.03.2001 geboren.',
                                 'Der Termin ist am 15.03.2001.'])
def test_f030_a_date_about_somebody_else_is_not_rewritten_as_the_users_birth_date(text):
    raw = json.dumps({'fakten': [{'art': 'geburtsdatum', 'text': text}]})
    assert memory_auto.parse_llm(raw) == []


def test_f031_an_explicitly_saved_age_is_available_without_guessing_a_birth_date(memory):
    memory_auto.store_facts(memory, memory_auto.extract('Ich bin 20 Jahre alt.'))
    answer = memory_auto.self_answer('Wie alt bin ich?', memory)
    assert '20' in answer
    assert memory_auto.birth_date(answer) is None


@pytest.mark.parametrize('statement', ['Vergiss, dass ich am 15.03.2001 geboren bin.',
                                     'Vergiss, dass ich am 15.3.2001 geboren bin.'])
def test_f023_dates_in_forget_requests_cannot_be_truncated_to_a_different_fact(memory, statement):
    entry = memory.remember('Geboren am 15.02.2002.', 'person:geburtsdatum')
    assert memory_auto.forget_matching(memory, memory_auto.forget_request(statement)) == []
    assert [value.id for value in memory.all_entries()] == [entry.id]


def test_a_matching_birth_date_can_be_forgotten_with_an_unpadded_month(memory):
    memory.remember('Geboren am 15.03.2001.', 'person:geburtsdatum')
    statement = 'Vergiss, dass ich am 15.3.2001 geboren bin.'
    assert memory_auto.forget_matching(memory, memory_auto.forget_request(statement))
    assert memory.count() == 0
