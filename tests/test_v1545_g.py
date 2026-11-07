"""15.4.5: Netzfreigaben, sparsames Scannen und wiederkehrende UI-Abfragen."""

import inspect
import json
import shutil
import subprocess
import threading
from collections import Counter
from pathlib import Path

import pytest

from aquaticy import lan

UI = Path(__file__).resolve().parents[1] / 'aquaticy' / 'webui.html'
NODE = shutil.which('node')


def test_f058_revoking_a_scan_stops_requests_that_have_not_started(monkeypatch):
    revoked = threading.Event()
    calls = []

    def probe(address, port):
        calls.append((address, port))
        revoked.set()
        return False

    monkeypatch.setattr(lan, 'WORKERS', 1)
    monkeypatch.setattr(lan, 'port_open', probe)
    options = {'allowed': lambda: not revoked.is_set()} if 'allowed' in inspect.signature(
        lan.scan).parameters else {}
    lan.scan('192.168.1.1/32', ports=(21, 22, 23), with_titles=False,
             with_names=False, **options)
    assert len(calls) == 1


def test_f059_discovery_reuses_confirmed_ports_instead_of_probing_every_port_twice(monkeypatch):
    calls = Counter()

    def probe(address, port):
        calls[(address, port)] += 1
        return port == 80

    monkeypatch.setattr(lan, 'port_open', probe)
    monkeypatch.setattr(lan, 'hostname_of', lambda address: 'nas.local')
    monkeypatch.setattr(lan, 'web_title', lambda *args: 'Personal NAS')
    found = lan.scan('192.168.1.1/32', ports=(22, 80))
    assert found[0].title == 'Personal NAS' and found[0].name == 'nas.local'
    assert calls == {('192.168.1.1', 22): 1, ('192.168.1.1', 80): 1}


def _function(name):
    source = UI.read_text(encoding='utf-8')
    start = source.index('async function ' + name + '(')
    return source[start:source.index('\n}', start) + 2]


@pytest.mark.skipif(not NODE, reason='JavaScript-Laufzeit fehlt')
@pytest.mark.parametrize('component', ['coworker', 'addons'])
def test_f060_polling_recovers_from_a_transient_connection_failure(component):
    function = 'coworkerLaden' if component == 'coworker' else 'addonsLaden'
    setup = '''
    let timers = [], calls = 0;
    const elements = new Map();
    const $ = selector => {
      if (!elements.has(selector)) elements.set(selector, {classList:{contains:()=>true}});
      return elements.get(selector);
    };
    const document = {hidden:false};
    const setTimeout = (callback, delay) => { timers.push(callback); return timers.length; };
    const clearTimeout = () => {};
    const addonBox = $('#addonbox'), coworkerBox = $('#coworkerbox');
    let addonTakt = 0, coworkerTakt = 0, addonDaten = null, coworkerDaten = null;
    const zeigeAddons = () => {}, coworkerZeigen = () => {}, coworkerAbzeichen = () => {};
    const api = async () => { calls++; throw new Error('Connection briefly interrupted'); };
    '''
    script = setup + _function(function) + f'\n{function}().then(() => {{' + '''
      if (!timers.length) throw new Error('The open window never retries after the outage');
    });
    '''
    result = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not NODE, reason='JavaScript-Laufzeit fehlt')
def test_f061_addon_polling_does_not_request_hidden_tabs():
    script = '''
    let calls = 0, addonTakt = 0, addonDaten = null;
    const document = {hidden:true};
    const clearTimeout = () => {}, setTimeout = () => 1;
    const addonBox = {classList:{contains:()=>true}};
    const $ = () => ({});
    const api = async () => { calls++; return {json:async () => ({addons:[]})}; };
    const zeigeAddons = () => {};
    ''' + _function('addonsLaden') + '''
    addonsLaden().then(() => process.stdout.write(JSON.stringify({calls})));
    '''
    result = subprocess.run([NODE, '-e', script], capture_output=True, text=True,
                            timeout=10, check=True)
    assert json.loads(result.stdout)['calls'] == 0
