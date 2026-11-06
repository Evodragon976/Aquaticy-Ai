"""Erfolgswege, Abbruch und parallele Nutzung der Korrekturen aus 15.2.4."""

import io
import json
import os
import sqlite3
from types import SimpleNamespace

import httpx
import pytest
from rich.console import Console

from aquaticy import (
    addons,
    cli,
    cluster,
    coworker,
    coworker_schedule,
    export,
    homeassistant,
    local_model,
    memory,
    storage,
)


def test_clearing_uploads_cannot_remove_files_outside_the_profile(tmp_path):
    profile = tmp_path / 'profile'
    profile.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    valuable = outside / 'keep.txt'
    valuable.write_text('Keep this', encoding='utf-8')
    (profile / 'uploads').symlink_to(outside, target_is_directory=True)
    store = memory.Memory(profile / 'memory.db')
    assert store.clear_uploads() == (0, 0)
    assert valuable.read_text(encoding='utf-8') == 'Keep this'


def test_feed_base_paths_have_a_size_limit():
    feed = b'<feed xml:base="https://example.org/' + b'a' * 8192 + b'"/>'
    with pytest.raises(ValueError, match='Basisadresse'):
        addons.parse_feed(feed, 'https://example.org/feed')


def test_currency_semicolons_keep_the_same_euro_permissions(settings, monkeypatch):
    from aquaticy.tools import Toolbox
    box = object.__new__(Toolbox)
    box.settings = settings
    box.stats = SimpleNamespace(addon_calls=0)
    monkeypatch.setattr(addons, "active", lambda *args: True)
    monkeypatch.setattr(addons, "rights_of", lambda *args: {"waehrungen": "euro"})
    monkeypatch.setattr(addons, "currency", lambda *args: {"ok": True})
    assert box._addon_call('currency', {'base': 'USD', 'to': 'EUR; EUR'}) == {'ok': True}
    assert box._addon_call('currency', {'base': 'USD', 'to': 'EUR; CHF'}).get('error')


def test_failed_default_export_does_not_leave_an_empty_document(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError('Disk unavailable')
    monkeypatch.setattr(export, 'to_markdown', fail)
    with pytest.raises(OSError):
        export.export([export.Turn('Question', 'Answer')], 'md', directory=tmp_path)
    assert not list(tmp_path.glob('*.md'))


@pytest.mark.parametrize('config', [{}, [], 'HTML page', {'version': ''}])
def test_home_assistant_connection_test_requires_a_real_config(config, monkeypatch):
    client = homeassistant.HomeAssistant('http://house.local:8123', 'synthetic-token')
    monkeypatch.setattr(client, '_request', lambda *args: config)
    with pytest.raises(homeassistant.HomeAssistantError):
        client.ping()


@pytest.mark.parametrize('method,status', [('GET', 302), ('POST', 307)])
def test_inventory_same_origin_redirects_preserve_the_request(method, status):
    requests = []
    def handle(request):
        requests.append(request)
        if request.url.path == '/old':
            return httpx.Response(status, headers={'Location': '/new'})
        return httpx.Response(200, json={'id': 1})
    with httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True) as http:
        client = storage.Storage('http://inventory.local:3000', access='write', client=http)
        assert client._request(method, '/old', json={'quantity': 2}) == {'id': 1}
    assert len(requests) == 2
    assert all(request.method == method for request in requests)
    assert all(json.loads(request.content) == {'quantity': 2} for request in requests)


@pytest.mark.parametrize('body,success', [
    (b'{"status":"downloading"}\n{"status":"success"}\n', True),
    (b'{"status":"success"}', True),
    (b'{"status":"downloading"}\n', False),
    (b'{"error":"disk full"}\n', False),
    (b'[]\n', False),
])
def test_ollama_server_can_download_without_a_local_cli(body, success, monkeypatch):
    monkeypatch.setattr(local_model, 'ollama_binary', lambda: None)
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, content=body)
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        def stream(method, url, **kwargs):
            assert kwargs.pop('trust_env') is False
            assert kwargs['follow_redirects'] is False
            return http.stream(method, url, **kwargs)
        monkeypatch.setattr(local_model.httpx, 'stream', stream)
        if success:
            assert list(local_model.pull_model('qwen3:8b', base_url='http://ollama:11434'))[-1] \
                == 'success'
        else:
            with pytest.raises(local_model.LocalModelError):
                list(local_model.pull_model('qwen3:8b', base_url='http://ollama:11434'))
    assert requests[0].url == 'http://ollama:11434/api/pull'
    assert json.loads(requests[0].content)['model'] == 'qwen3:8b'


def test_image_descriptions_are_displayed_as_plain_text(tmp_path, monkeypatch):
    image = tmp_path / '[image].png'
    image.write_bytes(b'png')
    output = io.StringIO()
    monkeypatch.setattr(cli, 'console', Console(file=output, width=150, color_system=None))
    description = 'Text [/invalid] [bold] als Text'
    agent = SimpleNamespace(describe_image=lambda *args: description)
    assert description in cli._describe_image(agent, image)
    assert description in output.getvalue()


def test_parallel_replication_transfers_keep_separate_database_snapshots(tmp_path, monkeypatch):
    peer = cluster.Cluster(tmp_path)
    user = 'b' * 32
    source = tmp_path / 'users' / user / 'data.db'
    source.parent.mkdir(parents=True)
    with sqlite3.connect(source) as conn:
        conn.execute('CREATE TABLE entries (value TEXT)')
        conn.execute('INSERT INTO entries VALUES ("original")')
    monkeypatch.setattr(cluster, 'CHUNK', 1024)
    signature = cluster.manifest(source.parent)['data.db']
    base = {'user': user, 'rel': 'data.db', 'sig': signature}
    request_a = dict(base, transfer='a' * 24)
    request_b = dict(base, transfer='b' * 24)
    first_a = peer._serve_file(request_a)
    first_b = peer._serve_file(request_b)
    assert not first_a['eof'] and not first_b['eof']
    with sqlite3.connect(source) as conn:
        conn.execute('INSERT INTO entries VALUES ("later")')
    stamp = source.stat().st_mtime_ns + 1_000_000
    os.utime(source, ns=(stamp, stamp))
    def finish(request, first):
        data = cluster._unb64(first['data'])
        while True:
            part = peer._serve_file(dict(request, offset=len(data)))
            assert not part.get('changed')
            data += cluster._unb64(part['data'])
            if part['eof']:
                return data
    body_a = finish(request_a, first_a)
    body_b = finish(request_b, first_b)
    assert body_a == body_b
    replica = tmp_path / 'replica.db'
    replica.write_bytes(body_a)
    with sqlite3.connect(replica) as conn:
        assert conn.execute('SELECT value FROM entries').fetchall() == [('original',)]


def test_scheduled_failures_keep_pending_coworker_orders(settings, monkeypatch):
    store = coworker.CoworkerStore(settings.db_path)
    cw = store.add('Ava', 'News', schedule={'kind': 'research'})
    store.add_log(cw.id, 'nachricht', 'Unprocessed order')
    monkeypatch.setattr(coworker_schedule, 'run_job', lambda *a, **kw: ('Fehler: timeout', ''))
    coworker.run_scheduled(cw, settings, 'pro', store=store)
    assert [item['text'] for item in store.unread_messages(cw.id)] == ['Unprocessed order']


def test_full_coworker_queue_keeps_its_existing_messages(settings, monkeypatch):
    monkeypatch.setattr(coworker, 'LOG_KEEP', 2)
    store = coworker.CoworkerStore(settings.db_path)
    cw = store.add('Ava', 'Suche aktuelle Nachrichten')
    store.add_log(cw.id, 'nachricht', 'One')
    store.add_log(cw.id, 'nachricht', 'Two')
    with pytest.raises(coworker.CoworkerError):
        store.add_log(cw.id, 'nachricht', 'Three')
    assert [item['text'] for item in store.unread_messages(cw.id)] == ['One', 'Two']
