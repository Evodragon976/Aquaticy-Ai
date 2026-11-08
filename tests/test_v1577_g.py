"""15.7.7: Robots-Regeln, Sicherheitsberichte und Prozessidentitaet."""

import os
import subprocess
import sys

import httpx
import pytest

from aquaticy import cli, fetch, lan, old_server, private_json, secure_pro


def test_f059_untrusted_robots_wildcards_cannot_trigger_exponential_matching():
    code = ('from aquaticy.fetch import RobotsRules\n'
            'rules=RobotsRules([(False, "/" + "*a" * 18 + "b")])\n'
            'assert rules.allows("https://example.org/" + "a" * 70)\n')
    subprocess.run([sys.executable, '-c', code], check=True, timeout=3,
                   capture_output=True)


def test_f060_wildcard_characters_do_not_make_a_robots_rule_more_specific():
    rules = fetch.RobotsRules([(False, '/private'), (True, '/' + '*' * 20)])
    assert not rules.allows('https://example.org/private/document')
    assert rules.allows('https://example.org/public/document')


def test_f061_only_the_most_specific_robot_agent_group_applies():
    rules = fetch.RobotsRules.parse('User-agent: aqua\nDisallow: /private\n\n'
                                    'User-agent: aquaticy\nAllow: /\n', 'aquaticy/15')
    assert rules.allows('https://example.org/private')


def test_f062_an_unresolved_robots_redirect_is_not_treated_as_permission(monkeypatch):
    monkeypatch.setattr(fetch.netguard, 'get', lambda *a, **kw: httpx.Response(302))
    with httpx.Client() as client:
        policy = fetch.RobotsPolicy(client, 'aquaticy/15')
        assert policy.check('https://example.org/private') == 'robots_unavailable'


def _watcher(tmp_path, monkeypatch, send):
    secure_pro.configure(tmp_path, '192.168.1.0/24')
    monkeypatch.setattr(lan, 'scan', lambda *a, **kw: [
        lan.Device(f'192.168.1.{n}', ports=[21]) for n in range(2, 22)])
    return secure_pro.Watcher(tmp_path, send)


def test_f063_revoking_secure_pro_stops_remaining_chunks_of_an_alert(tmp_path, monkeypatch):
    sent = []

    def send(text):
        sent.append(text)
        secure_pro.disable(tmp_path)
        return True

    watcher = _watcher(tmp_path, monkeypatch, send)
    monkeypatch.setattr(secure_pro, 'RISK_PORTS', {21: 'FTP-' + 'x' * 220})
    watcher.tick()
    assert len(sent) == 1


def test_f064_failed_history_writes_do_not_mark_findings_as_already_recorded(tmp_path, monkeypatch):
    watcher = _watcher(tmp_path, monkeypatch, lambda text: True)
    write = private_json.write
    failed = []

    def interrupted(path, data):
        if path == secure_pro.history_path(tmp_path) and not failed:
            failed.append(True)
            raise OSError('disk temporarily unavailable')
        write(path, data)

    monkeypatch.setattr(private_json, 'write', interrupted)
    watcher.tick()
    watcher.tick()
    assert secure_pro.read_history(tmp_path)['events']


def test_f065_the_default_terminal_chat_is_not_misidentified_as_a_web_server(monkeypatch):
    started = []
    monkeypatch.setattr(sys, 'argv', ['aquaticy'])
    monkeypatch.setattr(cli, 'app', lambda: started.append(tuple(sys.argv)))
    monkeypatch.setattr('aquaticy.startup.update_at_start', lambda console: False)
    cli.main()
    assert started == [('aquaticy', 'chat')]
    assert old_server._ist_server(['aquaticy']) is False
    assert old_server._ist_server([sys.executable, '-m', 'aquaticy.cli']) is False


@pytest.mark.skipif(not hasattr(os, 'pidfd_open'), reason='Linux-pidfd erforderlich')
def test_f066_waiting_for_a_stopped_process_uses_the_pinned_identity(monkeypatch):
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    monkeypatch.setattr(old_server, 'is_aquaticy', lambda pid: pid == process.pid)
    monkeypatch.setattr(old_server, '_exited', lambda pid: False)
    try:
        assert old_server.stop(process.pid, wait=0.5)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
