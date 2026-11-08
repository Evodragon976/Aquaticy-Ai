"""15.7.7: Laufende Aufgaben, Geheimnisse und Zeitumstellungen."""

import threading
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from aquaticy import coworker_schedule, homename, lan, secure_pro, web, zeit
from tests import test_v1577_b

hub = test_v1577_b.hub


def test_f032_account_shutdown_waits_for_inflight_native_answers(hub):
    instance, _, _ = hub
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()

    def answer(*args):
        entered.set()
        release.wait(3)

    instance._responder = answer
    instance._enqueue('signal', SimpleNamespace(messenger='signal'))
    assert entered.wait(1)
    thread = threading.Thread(target=lambda: (web._stop_native(instance), stopped.set()))
    thread.start()
    try:
        assert not stopped.wait(0.1)
    finally:
        release.set()
        thread.join(2)
    assert stopped.is_set()


@pytest.mark.parametrize('field', ['ha_token', 'github_token',
                                   'google_client_secret', 'memory_key'])
def test_f033_integration_secrets_are_also_in_the_redaction_set(settings, field):
    secret = 'privateConfiguredValue0123456789'
    setattr(settings, field, secret)
    assert secret in settings.secrets()


def test_f034_the_timezone_fallback_observes_fold_in_the_spring_gap():
    actual, fallback = ZoneInfo('Europe/Berlin'), zeit._EURegel()
    for fold in (0, 1):
        wall = datetime(2026, 3, 29, 2, 30, fold=fold)
        assert wall.replace(tzinfo=actual).utcoffset() == wall.replace(tzinfo=fallback).utcoffset()


@pytest.mark.parametrize('rhythm', ['daily', 'weekly'])
def test_f035_repeated_autumn_hours_never_return_an_already_passed_job(rhythm):
    zone = ZoneInfo('Europe/Berlin')
    now = datetime(2026, 10, 25, 2, 15, fold=1, tzinfo=zone).timestamp()
    target = coworker_schedule.next_time(rhythm, 2, 30, 6, now)
    assert target > now
    assert target == datetime(2026, 10, 25, 2, 30, fold=1, tzinfo=zone).timestamp()


def test_f036_https_startup_failure_closes_an_already_bound_listener(tmp_path, monkeypatch):
    closed = []

    class TLS:
        def __init__(self, *args):
            self.calls = 0

        def load(self, port):
            self.calls += 1
            if self.calls > 1:
                raise OSError('cannot reload certificate')
            return object()

    server = SimpleNamespace(server_address=('0.0.0.0', 8444),
                             server_close=lambda: closed.append(True))
    monkeypatch.setattr(homename, 'enabled', lambda: True)
    monkeypatch.setattr(homename, 'port', lambda: 8443)
    monkeypatch.setattr(homename, 'HomeTLS', TLS)
    monkeypatch.setattr(web, 'lan_address', lambda: '192.168.1.2')
    monkeypatch.setattr(web, 'tailscale_address', lambda: '')
    monkeypatch.setattr(web, '_HomeTLSServer', lambda *args: server)
    web._start_home_https('0.0.0.0', tmp_path, 8765)
    assert closed == [True]


def test_f038_revoking_a_scan_cannot_recreate_its_private_report(tmp_path, monkeypatch):
    monkeypatch.setattr(secure_pro.shutil, 'which', lambda name: '/bin/clamscan')
    secure_pro.configure(tmp_path, '192.168.1.0/24', str(tmp_path))
    monkeypatch.setattr(lan, 'scan', lambda *a, **kw: [lan.Device('192.168.1.1', ports=[443])])

    def scan(*args, **kwargs):
        secure_pro.disable(tmp_path)
        return SimpleNamespace(returncode=1, stdout='private-file: Signature FOUND')

    monkeypatch.setattr(secure_pro.subprocess, 'run', scan)
    secure_pro.Watcher(tmp_path, lambda text: True).tick()
    assert not (tmp_path / 'secure-pro-report.json').exists()


def _google_handler(settings, monkeypatch, host, https=False):
    handler = object.__new__(web.Handler)
    handler.headers = {'Host': host}
    handler._https = lambda: https
    handler._queue_header = lambda *args: None
    settings.google_client_id = 'client-id'
    settings.google_client_secret = 'client-secret'
    monkeypatch.setattr(web, 'SESSION', SimpleNamespace(settings=lambda: settings, account=None))
    return handler


def test_f037_google_login_on_home_https_uses_the_http_callback_port(settings, monkeypatch):
    monkeypatch.setattr(web, 'SERVER', SimpleNamespace(server_address=('0.0.0.0', 8765)))
    handler = _google_handler(settings, monkeypatch, 'aquaticy.local:8443', https=True)
    result = handler._google({'action': 'start'})
    assert result['redirect'] == 'http://localhost:8765/google'


def test_f039_google_code_exchange_keeps_the_original_redirect_after_an_address_change(
        settings, monkeypatch):
    from aquaticy import google

    captured = []
    handler = _google_handler(settings, monkeypatch, '127.0.0.1:8765')
    initial = handler._google({'action': 'start'})
    handler.headers = {'Host': 'localhost:8765'}
    monkeypatch.setattr(google, 'exchange_code', lambda cid, secret, code, redirect:
                        captured.append(redirect) or google.Tokens())
    monkeypatch.setattr(web, 'google_client', lambda settings: SimpleNamespace(
        remember=lambda tokens: None, close=lambda: None))
    monkeypatch.setattr(web, 'google_state', lambda settings: {})
    handler._google({'action': 'finish', 'code': 'code', 'state': initial['state']})
    assert captured == [initial['redirect']]
