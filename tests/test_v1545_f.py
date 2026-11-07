"""15.4.5: Profiluebertragung und Konfigurationsdateien bleiben vollstaendig."""

import base64
import contextlib
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from aquaticy import budget, cluster, config, web
from aquaticy.memory import Memory


@pytest.mark.parametrize('response', [{}, {'files': None}, {'files': []}, {'files': False}])
def test_f047_a_missing_profile_manifest_never_means_delete_the_local_profile(
        tmp_path, monkeypatch, response):
    node = cluster.Cluster(tmp_path)
    user = 'a' * 32
    folder = node._user_dir(user)
    folder.mkdir(parents=True)
    target = folder / 'keep.txt'
    target.write_bytes(b'Keep this private information')
    monkeypatch.setattr(node, 'call', lambda *args, **kwargs: response)
    with pytest.raises(cluster.ClusterError):
        node.sync_user(user, 'remote')
    assert target.read_bytes() == b'Keep this private information'


@pytest.mark.parametrize('direction', ['file-to-directory', 'directory-to-file'])
def test_f048_profile_sync_handles_a_legitimate_file_directory_replacement(
        tmp_path, monkeypatch, direction):
    node = cluster.Cluster(tmp_path)
    user = 'a' * 32
    folder = node._user_dir(user)
    folder.mkdir(parents=True)
    if direction == 'file-to-directory':
        (folder / 'entry').write_bytes(b'Previous file')
        relative = 'entry/new.txt'
    else:
        (folder / 'entry').mkdir()
        (folder / 'entry' / 'previous.txt').write_bytes(b'Previous child')
        relative = 'entry'
    monkeypatch.setattr(node, 'call', lambda *args, **kwargs: {'files': {relative: '3:1'}})
    monkeypatch.setattr(node, '_fetch', lambda *args, **kwargs: b'New')
    node.sync_user(user, 'remote')
    assert (folder / relative).read_bytes() == b'New'


def test_f049_local_speech_model_weights_do_not_exhaust_the_personal_storage_budget(settings):
    model = settings.data_dir / 'voice-models' / 'model.bin'
    model.parent.mkdir(parents=True)
    with model.open('wb') as stream:
        stream.truncate(budget.MAX_BYTES + 1)
    memory = Memory(settings.db_path, settings.data_dir, settings.memory_key)
    memory.remember('A small personal note.')
    assert budget.used_bytes(settings.data_dir, fresh=True) < 1_000_000
    assert model.stat().st_size == budget.MAX_BYTES + 1


@pytest.mark.parametrize('response', [
    {'data': '', 'eof': False},
    {'data': base64.b64encode(b'ab').decode(), 'eof': 'false'},
    {'data': base64.b64encode(b'ab').decode(), 'eof': True},
])
def test_f050_cluster_file_chunks_cannot_silently_end_before_the_announced_file(
        tmp_path, monkeypatch, response):
    node = cluster.Cluster(tmp_path)
    monkeypatch.setattr(node, 'call', lambda *args, **kwargs: response)
    with pytest.raises(cluster.ClusterError):
        node._fetch('remote', {'user': 'a' * 32, 'rel': 'note.txt', 'sig': '4:1'})


def test_f051_cluster_transfers_cannot_grow_past_the_announced_file_size(tmp_path, monkeypatch):
    node = cluster.Cluster(tmp_path)
    monkeypatch.setattr(node, 'call', lambda *args, **kwargs: {
        'data': base64.b64encode(b'Too much').decode(), 'eof': True})
    with pytest.raises(cluster.ClusterError):
        node._fetch('remote', {'user': 'a' * 32, 'rel': 'note.txt', 'sig': '2:1'})


def test_f052_parallel_setting_updates_preserve_both_changes(tmp_path, monkeypatch):
    target = tmp_path / '.env'
    target.write_text('FIRST=before\nSECOND=before\n', encoding='utf-8')
    original = Path.read_text
    barrier = threading.Barrier(2)

    def synchronized_read(self, *args, **kwargs):
        text = original(self, *args, **kwargs)
        if self == target:
            with contextlib.suppress(threading.BrokenBarrierError):
                barrier.wait(0.3)
        return text

    monkeypatch.setattr(Path, 'read_text', synchronized_read)
    with ThreadPoolExecutor(2) as pool:
        tasks = [pool.submit(config.write_env_file, values, target)
                 for values in ({'FIRST': 'after'}, {'SECOND': 'after'})]
        for task in tasks:
            task.result(3)
    assert config.read_env_file(target) == {'FIRST': 'after', 'SECOND': 'after'}


def test_f053_failed_settings_replacement_preserves_the_previous_file(tmp_path, monkeypatch):
    target = tmp_path / '.env'
    original_text = 'AQUATICY_MODEL=previous\nMISTRAL_API_KEY=ExistingPrivateKey\n'
    target.write_text(original_text, encoding='utf-8')
    original = Path.write_text

    def partial_write(self, text, *args, **kwargs):
        original(self, text[:9], *args, **kwargs)
        raise OSError('disk full')

    monkeypatch.setattr(Path, 'write_text', partial_write)
    with pytest.raises(OSError):
        config.write_env_file({'AQUATICY_MODEL': 'next'}, target)
    assert target.read_text(encoding='utf-8') == original_text


def test_f054_key_migration_removes_valid_tab_separated_export_assignments(tmp_path):
    target = tmp_path / '.env'
    target.write_text('export\tMISTRAL_API_KEY=OldPlaintextSecret\nOTHER=keep\n', encoding='utf-8')
    web.remove_env_keys(target, {'MISTRAL_API_KEY'})
    assert 'OldPlaintextSecret' not in target.read_text(encoding='utf-8')
    assert config.read_env_file(target) == {'OTHER': 'keep'}


@pytest.mark.parametrize('action', ['update', 'remove'])
def test_f055_multiline_env_assignments_are_replaced_or_removed_as_one_value(tmp_path, action):
    target = tmp_path / '.env'
    target.write_text('MISTRAL_API_KEY="FirstSecretLine\nSecondSecretLine"\nOTHER=keep\n',
                      encoding='utf-8')
    if action == 'update':
        config.write_env_file({'MISTRAL_API_KEY': 'replacement'}, target)
    else:
        web.remove_env_keys(target, {'MISTRAL_API_KEY'})
    text = target.read_text(encoding='utf-8')
    assert 'FirstSecretLine' not in text and 'SecondSecretLine' not in text
    assert config.read_env_file(target).get('OTHER') == 'keep'


def test_utf8_bom_env_files_keep_the_first_setting(tmp_path, monkeypatch):
    target = tmp_path / '.env'
    target.write_bytes(b'\xef\xbb\xbfAQUATICY_LOCATION=Bremen\n')
    monkeypatch.delenv('AQUATICY_LOCATION', raising=False)
    assert config.read_env_file(target) == {'AQUATICY_LOCATION': 'Bremen'}
    config.load_env(target, override=True)
    assert os.environ.get('AQUATICY_LOCATION') == 'Bremen'


@pytest.mark.skipif(os.name != 'posix', reason='POSIX-Dateirechte')
def test_f056_cluster_database_snapshots_keep_private_file_permissions(tmp_path):
    source = tmp_path / 'source.db'
    with sqlite3.connect(source) as connection:
        connection.execute('CREATE TABLE info (text TEXT)')
    previous = os.umask(0o022)
    try:
        target = tmp_path / 'snapshot.db'
        cluster.snapshot_sqlite(source, target)
    finally:
        os.umask(previous)
    assert target.stat().st_mode & 0o077 == 0


def test_f057_failed_database_snapshot_does_not_destroy_the_previous_copy(tmp_path, monkeypatch):
    source, target = tmp_path / 'source.db', tmp_path / 'snapshot.db'
    with sqlite3.connect(source) as connection:
        connection.execute('CREATE TABLE info (text TEXT)')
    target.write_bytes(b'Previous valid backup')
    connect = cluster.sqlite3.connect

    def failure(path, *args, **kwargs):
        if Path(path) == source:
            raise sqlite3.OperationalError('database temporarily unavailable')
        return connect(path, *args, **kwargs)

    monkeypatch.setattr(cluster.sqlite3, 'connect', failure)
    with pytest.raises(sqlite3.OperationalError):
        cluster.snapshot_sqlite(source, target)
    assert target.read_bytes() == b'Previous valid backup'


@pytest.mark.parametrize('directory_first', [True, False])
def test_failed_file_directory_replacement_restores_the_original_data(
        tmp_path, monkeypatch, directory_first):
    node = cluster.Cluster(tmp_path)
    user = 'a' * 32
    folder = node._user_dir(user)
    folder.mkdir(parents=True)
    original = folder / 'entry' / 'previous.txt' if directory_first else folder / 'entry'
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(b'Original personal data')
    relative = 'entry' if directory_first else 'entry/new.txt'
    monkeypatch.setattr(node, 'call', lambda *args, **kwargs: {'files': {relative: '3:1'}})
    monkeypatch.setattr(node, '_fetch', lambda *args, **kwargs: b'New')

    def failure(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(cluster, 'write_atomic', failure)
    with pytest.raises(OSError, match='disk full'):
        node.sync_user(user, 'remote')
    assert original.read_bytes() == b'Original personal data'
    assert not list(folder.rglob('.sync-*'))


def test_profile_sync_preserves_files_with_valid_pre_epoch_timestamps(tmp_path, monkeypatch):
    source = cluster.Cluster(tmp_path / 'source')
    destination = cluster.Cluster(tmp_path / 'destination')
    user = 'a' * 32
    folder = source._user_dir(user)
    folder.mkdir(parents=True)
    original = folder / 'old-note.txt'
    original.write_bytes(b'Historical note')
    os.utime(original, (-86400, -86400))

    def request(node, operation, args, **kwargs):
        if operation == 'manifest':
            return {'files': cluster.manifest(folder)}
        assert operation == 'file'
        return source._serve_file(args)

    monkeypatch.setattr(destination, 'call', request)
    destination.sync_user(user, 'remote')
    assert (destination._user_dir(user) / original.name).read_bytes() == b'Historical note'
