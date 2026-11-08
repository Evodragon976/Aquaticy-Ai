"""15.7.7: Datenschutz, Zustellung und gleichzeitige Cache-Zugriffe."""

import base64
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest

from aquaticy import bridge, coworker, google, homeassistant, local_model, secure_pro, web
from aquaticy.cache import Cache


def test_f050_disabling_secure_pro_removes_the_local_file_scan_report(tmp_path):
    report = tmp_path / 'secure-pro-report.json'
    report.write_text('{"findings": "private/path/file.txt: FOUND"}')
    secure_pro.disable(tmp_path)
    assert not report.exists()


def test_f051_naive_calendar_times_use_german_time_on_a_utc_server(monkeypatch):
    monkeypatch.setenv('TZ', 'UTC')
    time.tzset()
    try:
        actual = google._calendar_datetime('2026-11-08T14:00:00')
        expected = datetime(2026, 11, 8, 14, tzinfo=ZoneInfo('Europe/Berlin'))
        assert actual.timestamp() == expected.timestamp()
    finally:
        monkeypatch.undo()
        time.tzset()


def test_f052_attachment_dispositions_with_leading_space_stay_out_of_the_mail_body():
    part = {'mimeType': 'text/plain', 'headers': [
        {'name': 'Content-Disposition', 'value': ' attachment; filename="private.txt"'}],
        'body': {'data': base64.urlsafe_b64encode(b'Attachment private content').decode()}}
    assert google._body_text(part) == ''


@pytest.mark.parametrize('method', ['_get', '_write'])
def test_f053_google_api_responses_are_bounded_before_loading_the_body(
        tmp_path, method, monkeypatch):
    monkeypatch.setattr(google, 'MAX_RESPONSE_BYTES', 131072, raising=False)
    read = []

    class Body(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(150):
                read.append(1)
                yield b' ' * 65536

    with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=Body()))) as http:
        api = google.Google('id', 'secret', google.TokenStore(tmp_path), http)
        api._access = lambda: 'access'
        with pytest.raises(google.GoogleError):
            if method == '_get':
                api._get(google.GMAIL_API + '/messages', {})
            else:
                api._write('POST', google.GMAIL_API + '/drafts', {})
    assert len(read) < 150


@pytest.mark.parametrize('kind', ['coworker', 'bridge'])
def test_f054_a_shutdown_timeout_cannot_be_reported_as_quiescence(kind):
    thread = SimpleNamespace(join=lambda **kw: None, is_alive=lambda: True)
    if kind == 'coworker':
        worker = coworker.Scheduler(lambda: None, lambda: 'ultra')
    else:
        worker = bridge.Runner(lambda: None, lambda *args: None)
    worker._thread = thread
    with pytest.raises(TimeoutError):
        worker.wait_stopped(timeout=0)


def test_shutdown_failures_keep_the_runtime_registered_for_a_safe_retry(monkeypatch):
    account = SimpleNamespace(id='account')

    def busy():
        raise TimeoutError('still running')

    scheduler = SimpleNamespace(stop=lambda: None, wait_stopped=busy)
    registry = {account.id: scheduler}
    monkeypatch.setattr(web, 'USER_COWORKERS', registry)
    monkeypatch.setattr(web, 'USER_BRIDGES', {})
    monkeypatch.setattr(web, 'USER_NATIVE', {})
    monkeypatch.setattr(web, 'SESSIONS', SimpleNamespace(
        drop=lambda value: pytest.fail('must keep session until quiescent')))
    with pytest.raises(TimeoutError):
        web.forget_account_runtime(account)
    assert registry.get(account.id) is scheduler


def test_f055_partly_delivered_security_reports_resume_without_repeating_sent_chunks(tmp_path):
    sent = []
    attempts = [0]

    def send(text):
        attempts[0] += 1
        if attempts[0] == 2:
            return False
        sent.append(text)
        return True

    watcher = secure_pro.Watcher(tmp_path, send)
    lines = ['a' * 2800, 'b' * 2800, 'c' * 2800]
    assert not watcher._deliver(lines, False, send, 'Messenger')
    assert watcher._deliver(lines, False, send, 'Messenger')
    assert len(sent) == len(set(sent))


def test_f056_parallel_home_assistant_cache_misses_share_one_state_request(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    first = homeassistant.HomeAssistant('http://ha.local:8123', 'secret', profile=tmp_path)
    second = homeassistant.HomeAssistant('http://ha.local:8123', 'secret', profile=tmp_path)

    def request(*args):
        calls.append(True)
        entered.set()
        release.wait(2)
        return []

    monkeypatch.setattr(homeassistant.HomeAssistant, '_request', request)
    with ThreadPoolExecutor(2) as pool:
        one = pool.submit(first.states)
        assert entered.wait(1)
        two = pool.submit(second.states)
        try:
            assert not two.done()
            time.sleep(0.05)
            assert len(calls) == 1
        finally:
            release.set()
        assert one.result() == two.result() == []


def test_f057_parallel_ollama_metadata_misses_share_one_bounded_request(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    monkeypatch.setattr(local_model, '_SHOW', {})

    @contextmanager
    def stream(*args, **kwargs):
        calls.append(True)
        entered.set()
        release.wait(2)
        yield httpx.Response(200, json={'capabilities': ['tools']})

    monkeypatch.setattr(local_model.httpx, 'stream', stream)
    with ThreadPoolExecutor(2) as pool:
        one = pool.submit(local_model._show, 'example:7b')
        assert entered.wait(1)
        two = pool.submit(local_model._show, 'example:7b')
        try:
            time.sleep(0.05)
            assert len(calls) == 1
        finally:
            release.set()
        assert one.result() == two.result()


def test_f058_distinct_cache_objects_for_one_database_share_the_fill_lock(tmp_path):
    first = Cache(tmp_path / 'cache.sqlite3')
    second = Cache(tmp_path / 'cache.sqlite3')
    entered = threading.Event()

    def fill():
        with second.filling('same-key'):
            entered.set()

    with ThreadPoolExecutor(1) as pool:
        with first.filling('same-key'):
            worker = pool.submit(fill)
            assert not entered.wait(0.1)
        worker.result(1)


def test_bounded_google_responses_preserve_gzip_support(tmp_path, monkeypatch):
    import gzip

    payload = gzip.compress(b'{"email":"owner@example.org"}')
    transport = httpx.MockTransport(lambda request: httpx.Response(
        200, content=payload, headers={"content-encoding": "gzip"}))
    with httpx.Client(transport=transport) as client:
        connection = google.Google("client", "secret", google.TokenStore(tmp_path), client=client)
        monkeypatch.setattr(connection, "_access", lambda: "test-token")
        assert connection._get("https://www.googleapis.com/userinfo", {}) == {
            "email": "owner@example.org"}
