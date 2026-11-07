"""15.4.5: Coworker achten auch bei Werkzeugen auf widerrufene Rechte."""

from types import SimpleNamespace

import pytest

from aquaticy import coworker, sandbox
from aquaticy.memory import Memory


def _session(settings, *, sharing=False, memory_rule='erlauben', **kwargs):
    store = coworker.CoworkerStore(settings.db_path)
    cw = store.add('Ava', 'Finde aktuelle Informationen zu Musik.', plan='ultra')
    store.set_preferences(cw.id, {'sharing_chats': sharing, 'sharing_coworkers': False,
                                  'notes_limit': 6000})
    store.set_rules(cw.id, {'speicher': memory_rule}, ultra=True)
    kwargs.setdefault('vm', False)
    return coworker.Session(store=store, cw=store.get(cw.id), plan='ultra', **kwargs)


def test_f062_coworker_memory_tools_require_the_explicit_chat_sharing_consent(settings):
    memory = Memory(settings.db_path, settings.data_dir, settings.memory_key)
    entry = memory.remember('Privates persönliches Wissen', topic='person:name')
    session = _session(settings)
    agent = coworker.coworker_agent_class()(settings, session)
    try:
        result = agent.toolbox.call('recall_memory', {'query': ''})
        assert result.get('error'), result
        assert str(entry.id) not in str(result.get('entries', []))
    finally:
        agent.close()


@pytest.mark.parametrize('rule', ['sperren', 'fragen'])
def test_f063_deleting_personal_notes_cannot_bypass_coworker_memory_rules(settings, rule):
    session = _session(settings, sharing=True, memory_rule=rule)
    memory = Memory(settings.db_path, settings.data_dir, settings.memory_key)
    entry = memory.remember('Persönliche Notiz', topic='person:name')
    agent = coworker.coworker_agent_class()(settings, session)
    try:
        result = agent.toolbox.call('forget_memory', {'id': entry.id})
        assert result.get('error') or result.get('wartet_auf_freigabe'), result
        assert memory.count() == 1
    finally:
        agent.close()


def test_f064_coworker_vms_adopt_changed_network_permissions(settings, monkeypatch):
    stopped = []

    class Box(SimpleNamespace):
        def stop(self, reason):
            stopped.append(self)

    monkeypatch.setattr(sandbox, 'Sandbox', Box)
    monkeypatch.setattr(coworker, '_BOXES', {})
    settings.vm_user_mode = False
    settings.vm_internet = True
    settings.vm_lan = True
    old = coworker._box(settings, 41)
    assert coworker._box(settings, 41) is old
    settings.vm_internet = False
    settings.vm_lan = False
    current = coworker._box(settings, 41)
    assert current is not old and old in stopped
    assert current.internet is False and current.lan is False


def test_f065_a_downgraded_account_cannot_continue_using_coworker_vms(settings):
    session = _session(settings, vm=True, current_plan=lambda: 'pro')
    result = session.gate(SimpleNamespace(settings=settings, untrusted_seen=False),
                          'vm_run', {'code': 'print(1)'})
    assert result and result.get('error'), result


def test_current_coworker_turn_cannot_restart_a_vm_with_revoked_network_rights(settings):
    import dataclasses

    settings.vm_internet = True
    current = dataclasses.replace(settings, vm_internet=False)
    session = _session(settings, vm=True, current_settings=lambda: current)
    result = session.gate(SimpleNamespace(settings=settings, untrusted_seen=False),
                          'vm_run', {'code': 'print(1)'})
    assert result and result.get('error'), result


def test_the_approved_memory_deletion_feature_still_works(settings):
    session = _session(settings, sharing=True, memory_rule='fragen')
    memory = Memory(settings.db_path, settings.data_dir, settings.memory_key)
    entry = memory.remember('Die freigegebene Notiz')
    agent = coworker.coworker_agent_class()(settings, session)
    try:
        pending = agent.toolbox.call('forget_memory', {'id': entry.id})
        action = session.store.decide(session.cw.id, pending['anfrage'], True)
        success, result = coworker.run_action(session.store, action, settings, ultra=True)
        assert success, result
        assert memory.count() == 0
    finally:
        agent.close()


def test_revoking_chat_sharing_also_blocks_an_existing_memory_tool(settings):
    session = _session(settings, sharing=True)
    memory = Memory(settings.db_path, settings.data_dir, settings.memory_key)
    memory.remember('Vertrauliche Notiz')
    agent = coworker.coworker_agent_class()(settings, session)
    try:
        assert agent.toolbox.call('recall_memory', {})['found'] == 1
        session.store.set_preferences(session.cw.id, {'sharing_chats': False})
        assert agent.toolbox.call('recall_memory', {}).get('error')
    finally:
        agent.close()


@pytest.mark.parametrize('identifier', [True, 1.5, float('inf')])
def test_memory_deletion_never_rounds_invalid_identifiers(settings, identifier):
    from aquaticy.tools import Toolbox

    memory = Memory(settings.db_path, settings.data_dir, settings.memory_key)
    memory.remember('Eine unveränderte Notiz')
    toolbox = Toolbox(settings)
    try:
        assert toolbox.forget_memory(identifier).get('error')
        assert memory.count() == 1
    finally:
        toolbox.close()
