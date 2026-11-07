"""15.4.5: Exporte bleiben im Chat, Uploads bleiben eindeutig und im Kontingent."""

import contextlib
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from aquaticy import export, metering, privacy, sandbox, web
from aquaticy.cache import Cache
from aquaticy.quota import Quota


def _session(settings, *, local=False):
    session = web.ChatSession()
    session._settings = settings
    session._agent = SimpleNamespace(session_id='current')
    session.account = None if local else SimpleNamespace(id='example-account')
    return session


def test_f042_exporting_the_active_chat_does_not_include_other_chats(settings):
    session = _session(settings)
    cache = Cache(settings.db_path)
    cache.add_history('current', 'Current question', 'Current answer')
    cache.add_history('other', 'Other question', 'PRIVATE_OTHER_CHAT')
    output = session._export('md')['download']['content']
    assert 'Current answer' in output and 'PRIVATE_OTHER_CHAT' not in output


def test_f043_web_exports_keep_the_product_data_saved_with_the_answer(settings):
    session = _session(settings)
    Cache(settings.db_path).add_history('current', 'Find a computer', 'I found one.', {
        'products': [{'name': 'Unique machine', 'url': 'https://example.org/item',
                      'price': '19.95', 'currency': 'EUR', 'specs': {'RAM': '16 GB'}}]})
    output = session._export('csv')['download']['content']
    assert 'Unique machine' in output and '19.95' in output and '16 GB' in output


def test_f044_the_local_web_export_copy_does_not_overwrite_an_earlier_export(
        settings, tmp_path, monkeypatch):
    session = _session(settings, local=True)
    cache = Cache(settings.db_path)
    cache.add_history('current', 'Question', 'First answer')
    output_dir = tmp_path / 'exports'
    output_dir.mkdir()
    monkeypatch.chdir(output_dir)
    monkeypatch.setattr(export, 'default_path', lambda turns, fmt, directory: directory / 'same.md')
    session._export('md')
    first = next(output_dir.glob('*.md'))
    previous = first.read_bytes()
    cache.add_history('current', 'Question', 'Second answer')
    session._export('md')
    assert first.read_bytes() == previous
    assert len(list(output_dir.glob('*.md'))) == 2


@pytest.mark.skipif(os.name != 'posix', reason='POSIX-Dateirechte')
def test_the_local_web_export_copy_keeps_the_private_file_permissions(
        settings, tmp_path, monkeypatch):
    session = _session(settings, local=True)
    Cache(settings.db_path).add_history('current', 'Question', 'Private answer')
    output_dir = tmp_path / 'exports'
    output_dir.mkdir()
    monkeypatch.chdir(output_dir)
    previous = os.umask(0o022)
    try:
        session._export('md')
    finally:
        os.umask(previous)
    assert next(output_dir.glob('*.md')).stat().st_mode & 0o077 == 0


def test_f045_uploads_with_equal_names_and_timestamps_keep_both_contents(settings, monkeypatch):
    session = _session(settings)
    monkeypatch.setattr(web.time, 'time', lambda: 1_800_000_000.0)
    first = session._store('image.png', b'First image')
    second = session._store('image.png', b'Second image')
    assert first != second
    assert privacy.read_private(first, settings.data_dir) == b'First image'
    assert privacy.read_private(second, settings.data_dir) == b'Second image'


def test_f046_parallel_vm_uploads_reserve_their_work_budget_before_writing(settings, monkeypatch):
    session = _session(settings)
    quota = Quota(settings.data_dir / 'quota.sqlite3', 'account', time.time())
    settings.quota = quota
    cost = metering.work_cost('datei')
    quota.record(quota.session_tokens - cost)
    barrier = threading.Barrier(2)
    calls = []
    lock = threading.Lock()

    class Box:
        def put_bytes(self, path, data):
            with lock:
                calls.append(path)
            with contextlib.suppress(threading.BrokenBarrierError):
                barrier.wait(0.3)
            return {'written': path}

    monkeypatch.setattr(sandbox, 'shared', lambda *args, **kwargs: Box())
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda name: session._into_workshop(name, b'content'),
                                ['first.txt', 'second.txt']))
    assert len(calls) == 1 and sum(bool(result) for result in results) == 1
    assert quota.remaining() == 0
