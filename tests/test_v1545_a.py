"""15.4.5: Gegenproben fuer Kontodaten und sichere lokale Schreibvorgaenge."""

import gc
import json
import os

import pytest
from pydantic import ValidationError

from aquaticy import auth, budget, export, uistate, web
from aquaticy.cache import Cache
from aquaticy.models import Product


def test_f001_profile_locks_are_released_after_the_profile_is_discarded(tmp_path):
    path = tmp_path / 'temporary-profile.sqlite3'
    state = uistate.UIState(path)
    assert state.read() == uistate.defaults()
    del state
    gc.collect()
    assert str(path.resolve()) not in uistate._SPERREN


@pytest.mark.parametrize('control', ['\u202e', '\u2066', '\u202a'])
def test_f002_usernames_cannot_reorder_identity_text_with_bidi_controls(control):
    with pytest.raises(ValueError):
        auth.normalize_username('Owner' + control + 'admin')


@pytest.mark.parametrize('control', ['\x00', '\x08', '\x7f'])
def test_f003_email_addresses_cannot_contain_nonprinting_controls(control):
    with pytest.raises(ValueError):
        auth.normalize_email('a' + control + 'b@example.org')


@pytest.mark.skipif(os.name != 'posix', reason='POSIX-Dateirechte')
@pytest.mark.parametrize('fmt', ['html', 'md', 'csv'])
def test_f004_new_chat_exports_are_private_under_a_public_umask(tmp_path, fmt):
    previous = os.umask(0o022)
    try:
        target = export.export([export.Turn('Private Frage', 'Private Antwort')],
                               fmt, directory=tmp_path)
    finally:
        os.umask(previous)
    assert target.stat().st_mode & 0o077 == 0


def test_f005_failed_csv_replacement_preserves_the_previous_export(tmp_path, monkeypatch):
    target = tmp_path / 'existing.csv'
    target.write_text('Previous export', encoding='utf-8')
    original = export._SafeCsv.writerow
    calls = []

    def fail_after_header(self, row):
        calls.append(row)
        if len(calls) == 2:
            raise OSError('disk full')
        original(self, row)

    monkeypatch.setattr(export._SafeCsv, 'writerow', fail_after_header)
    with pytest.raises(OSError):
        export.export([export.Turn('Question', 'Answer')], 'csv', path=target)
    assert target.read_text(encoding='utf-8') == 'Previous export'


@pytest.mark.parametrize('rating', [float('nan'), float('inf'), -float('inf')])
def test_f006_product_ratings_must_be_serializable_json_numbers(rating):
    with pytest.raises(ValidationError):
        Product(name='Example', url='https://example.org/item', rating=rating)


@pytest.mark.parametrize('metadata', ['not json', '[1]', 'true'])
def test_f007_invalid_history_metadata_does_not_make_the_chat_unreadable(settings, metadata):
    cache = Cache(settings.db_path)
    first = cache.add_history('chat', 'First question', 'First answer')
    cache.add_history('chat', 'Second question', 'Second answer', {'sources': []})
    with cache._connect() as conn:
        conn.execute('UPDATE history SET meta=? WHERE id=?',
                     (cache._seal(metadata, 'history.meta'), first))
    history = cache.chat_history('chat')
    assert [entry.answer for entry in history] == ['First answer', 'Second answer']
    assert all(isinstance(entry.meta, dict) for entry in history)
    json.dumps([entry.meta for entry in history], allow_nan=False)


@pytest.mark.parametrize('action', ['note', 'title'])
def test_f008_legacy_cache_writes_obey_the_profile_storage_limit(settings, monkeypatch, action):
    cache = Cache(settings.db_path)
    cache.add_history('chat', 'Question', 'Answer')
    (settings.data_dir / 'unrelated.bin').write_bytes(b'x' * 100_000)
    monkeypatch.setattr(budget, 'MAX_BYTES', 64_000)
    budget.forget(settings.data_dir)
    with pytest.raises(budget.StorageFull):
        if action == 'note':
            cache.add_note('This note must not bypass the storage limit.')
        else:
            cache.rename_chat('chat', 'This title must obey the storage limit.')


@pytest.mark.parametrize('identifier', [True, False, 1.9, -1.9])
def test_f009_json_identifiers_are_not_silently_truncated_or_converted_from_flags(identifier):
    with pytest.raises((TypeError, ValueError, OverflowError)):
        web._json_int(identifier)
