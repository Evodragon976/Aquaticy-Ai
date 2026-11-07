"""15.4.5: Loeschwuensche passen auch zur gespeicherten Erzaehlform."""

import pytest

from aquaticy import memory_auto
from aquaticy.memory import Memory


@pytest.mark.parametrize('statement', [
    'Ich heiße Lisa.',
    'Ich wohne in Bremen.',
    'Ich arbeite als Lehrerin.',
    'Ich komme aus Berlin.',
])
def test_f066_first_person_forgetting_matches_third_person_saved_facts(settings, statement):
    memory = Memory(settings.db_path, settings.data_dir, settings.memory_key)
    facts = memory_auto.extract(statement)
    assert len(memory_auto.store_facts(memory, facts)) == 1
    other = memory.remember('Mag Musik.', topic='person:mag:musik')
    request = 'Vergiss, dass ' + statement[0].lower() + statement[1:]
    forgotten = memory_auto.forget_matching(memory, memory_auto.forget_request(request))
    assert forgotten == [facts[0].text]
    assert [entry.id for entry in memory.all_entries()] == [other.id]
