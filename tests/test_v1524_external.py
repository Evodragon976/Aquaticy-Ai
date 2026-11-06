"""Gegenproben zu den 18 Aussagen des externen LLM-Berichts."""

import httpcore
import httpx
import pytest
import yaml

from aquaticy import config, fetch, netguard, secure_nmap


@pytest.mark.parametrize('answer', [[], OSError('DNS fehlgeschlagen')])
def test_external_01_dns_failures_never_allow_a_connection(monkeypatch, answer):
    def resolve(*args):
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(netguard, 'resolve', resolve)
    with pytest.raises(netguard.Unresolvable):
        netguard.checked_addresses('dns-test.example', 443)


def test_external_02_backend_connects_to_the_checked_ip(monkeypatch):
    resolutions, connections = [], []
    def resolve(*args):
        resolutions.append(args)
        return ['93.184.216.34'] if len(resolutions) == 1 else ['127.0.0.1']
    def connect(self, host, port, **kwargs):
        connections.append((host, port))
        return object()
    monkeypatch.setattr(netguard, 'resolve', resolve)
    monkeypatch.setattr(netguard, 'upstream_proxy', lambda: None)
    monkeypatch.setattr(httpcore.SyncBackend, 'connect_tcp', connect)
    netguard._GuardedBackend().connect_tcp('dns-test.example', 443)
    assert len(resolutions) == 1
    assert connections == [('93.184.216.34', 443)]


@pytest.mark.parametrize('target', [
    '192.168.1.5; echo unsafe', '-oN/tmp/output', '$(id)',
    '../reports', '8.8.8.8', '192.168.1.0/16',
])
def test_external_03_nmap_rejects_unapproved_or_shell_targets(target):
    with pytest.raises(ValueError):
        secure_nmap.targets_in('192.168.1.0/24', [target])


def test_external_05_yaml_python_objects_are_rejected(tmp_path):
    target = tmp_path / 'selectors.yaml'
    target.write_text('!!python/object/apply:builtins.eval ["1 + 1"]', encoding='utf-8')
    with pytest.raises(yaml.constructor.ConstructorError):
        fetch.load_rules(str(target))


def test_f121_local_address_cache_evicts_one_old_entry_instead_of_all(monkeypatch):
    calls = []
    monkeypatch.setattr(netguard, 'resolve', lambda host, port:
                        calls.append(host) or ['192.168.1.5'])
    config._LOKAL_MERK.clear()
    try:
        for number in range(67):
            assert config.local_address(f'http://node-{number}.example:11434')
        before = len(calls)
        assert config.local_address('http://node-60.example:11434')
        assert len(calls) == before
        assert len(config._LOKAL_MERK) <= 64
    finally:
        config._LOKAL_MERK.clear()


def test_external_08_redirect_to_metadata_never_gets_sent(monkeypatch):
    requests = []
    def handle(request):
        requests.append(str(request.url))
        return httpx.Response(302, headers={'Location': 'http://169.254.169.254/latest/'})
    monkeypatch.setattr(netguard, 'resolve', lambda *args: ['93.184.216.34'])
    netguard.forget()
    with (httpx.Client(transport=httpx.MockTransport(handle)) as client,
          pytest.raises(netguard.BlockedTarget)):
        netguard.get(client, 'https://redirect.example/start', max_bytes=1024)
    assert requests == ['https://redirect.example/start']


@pytest.mark.parametrize('address, allowed', [
    ('::ffff:127.0.0.1', False), ('::ffff:10.0.0.1', False),
    ('::ffff:93.184.216.34', True), ('64:ff9b::7f00:1', False),
    ('64:ff9b::a00:1', False), ('64:ff9b::5db8:d822', True),
])
def test_external_17_ipv4_mapped_and_nat64(address, allowed):
    assert netguard.ip_allowed(address) is allowed
