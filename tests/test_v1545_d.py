"""15.4.5: Proxy-Vertrauen, TCP-Dienstpruefung und sichere Aktionsparameter."""

import ipaddress
from email.message import Message
from types import SimpleNamespace

import pytest

from aquaticy import homeassistant, metering, secure_network, web


def test_f033_proxy_chains_resolve_the_client_beyond_trusted_intermediate_proxies(monkeypatch):
    monkeypatch.setattr(web, 'trusted_proxies', lambda: [
        ipaddress.ip_network('10.0.0.0/8'), ipaddress.ip_network('192.168.0.0/16')])
    assert web.client_ip('10.0.0.2', '198.51.100.7, 192.168.1.3') == '198.51.100.7'


def test_f036_ipv4_mapped_proxy_peers_keep_their_explicit_trust(monkeypatch):
    monkeypatch.setattr(web, 'trusted_proxies', lambda: [ipaddress.ip_network('127.0.0.0/8')])
    assert web.client_ip('::ffff:127.0.0.1', '198.51.100.7') == '198.51.100.7'
    handler = object.__new__(web.Handler)
    handler.connection = object()
    handler.client_address = ('::ffff:127.0.0.1', 12345)
    handler.headers = Message()
    handler.headers['X-Forwarded-Proto'] = 'https'
    assert handler._https() is True


def test_f037_an_invalid_nearest_forwarded_hop_does_not_expose_an_attacker_prefix(monkeypatch):
    monkeypatch.setattr(web, 'trusted_proxies', lambda: [ipaddress.ip_network('127.0.0.0/8')])
    assert web.client_ip('127.0.0.1', '8.8.8.8, malformed') == '127.0.0.1'


class _Socket:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def settimeout(self, *args):
        pass

    def sendall(self, *args):
        pass

    def recv(self, limit):
        return self.chunks.pop(0) if self.chunks else b''


@pytest.mark.parametrize(('port', 'chunks', 'expected'), [
    (22, [b'SS', b'H-2.0-OpenSSH_9.9\r\n'], 'SSH-2.0-OpenSSH_9.9'),
    (80, [b'HT', b'TP/1.1 200 OK\r\nServer: Example\r\n\r\n'], 'HTTP antwortet'),
])
def test_f038_fragmented_tcp_responses_are_read_to_the_protocol_boundary(
        monkeypatch, port, chunks, expected):
    monkeypatch.setattr(secure_network.lan, 'check_host',
                        lambda *args, **kwargs: SimpleNamespace(ports=[port]))
    monkeypatch.setattr(secure_network.socket, 'create_connection',
                        lambda *args, **kwargs: _Socket(chunks))
    result = secure_network.inspect('192.168.1.0/24', '192.168.1.2')
    text = str(result.get('ssh_banner', '')) + ' '.join(result['observations'])
    assert expected in text


def test_f039_ssh_identification_can_follow_a_legal_pre_identification_notice(monkeypatch):
    monkeypatch.setattr(secure_network.lan, 'check_host',
                        lambda *args, **kwargs: SimpleNamespace(ports=[22]))
    monkeypatch.setattr(secure_network.socket, 'create_connection',
                        lambda *args, **kwargs: _Socket([
                            b'Authorized access only\r\nSSH-2.0-OpenSSH_9.9\r\n']))
    result = secure_network.inspect('192.168.1.0/24', '192.168.1.2')
    assert result.get('ssh_banner') == 'SSH-2.0-OpenSSH_9.9'


@pytest.mark.parametrize('data', [['brightness', 1], 'brightness=1', True])
def test_f040_invalid_home_assistant_parameters_do_not_turn_into_another_action(data):
    with pytest.raises(homeassistant.HomeAssistantError):
        homeassistant.check_call('light', 'turn_on', 'light.room', data)


@pytest.mark.parametrize('usage', [
    {'prompt_tokens': True, 'completion_tokens': 2},
    {'prompt_tokens': 10, 'completion_tokens': False},
])
def test_f041_boolean_usage_fields_fall_back_to_accounting_instead_of_one_token(usage):
    assert metering.usage_of(usage) is None
