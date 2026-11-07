"""15.4.5: Gegenproben fuer externe Antworten, Geheimnisse und Zeitplaene."""

import os
import time
from datetime import UTC, datetime

import httpx
import pytest

from aquaticy import (
    coworker_schedule,
    extract,
    github_repo,
    github_write,
    google,
    review_scan,
    secure_devices,
    secure_nmap,
    voice,
)
from aquaticy.learning import Learning
from aquaticy.legal import LEGAL_VERSION


@pytest.mark.parametrize('payload', [{}, {'error': {'message': 'Not accepted'}}])
def test_f010_google_writes_need_a_confirmed_resource_id(tmp_path, monkeypatch, payload):
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload)))
    api = google.Google('id', 'secret', google.TokenStore(tmp_path), client)
    monkeypatch.setattr(api, '_access', lambda: 'test-token')
    try:
        with pytest.raises(google.GoogleError):
            api.create_event('Meeting', '2026-11-08T10:00:00+00:00')
    finally:
        api.close()


def test_f011_nmap_down_hosts_are_not_reported_as_discovered_devices():
    xml = ('<nmaprun><host><status state="down"/>'
           '<address addr="192.168.1.9" addrtype="ipv4"/></host></nmaprun>')
    assert secure_nmap.parse(xml) == []


@pytest.mark.parametrize(('text', 'expected'), [
    ('Antworte nicht nur als Text, sondern auch als Sprachnachricht.', True),
    ('Eine Sprachnachricht bitte nicht. Antworte als Text.', False),
    ('Erkläre den Satz „Antworte als Sprachnachricht“.', False),
])
def test_f012_voice_output_requires_the_actual_current_request(text, expected):
    assert voice.requested(text) is expected


@pytest.mark.parametrize('path', ['.GIT/config', 'src/.git./config', 'src/.git /config'])
def test_f013_github_paths_cannot_alias_git_metadata_on_other_platforms(path):
    assert not github_write.valid_repo_path(path)


def test_f014_private_key_fragments_in_diff_hunks_remain_masked():
    fragment = 'MIIEpAIBAAKCAQEAq5Dx7Tn8Vb3Lu6Hw9Sz2Pr4Ey0Ca1Fk5Nm7Jt8Gv6Rb9Qs2Z'
    patch = '@@ -12,1 +12,1 @@\n+' + fragment + '\n'
    assert fragment not in github_repo.redact(patch)


@pytest.mark.parametrize('secret', ['s3cr3t', 'Long phrase with spaces 73!', 'A7z' * 100])
def test_f015_quoted_secrets_outside_the_old_length_and_character_range_are_masked(secret):
    source = 'password = "' + secret + '"'
    assert secret not in review_scan.mask_secrets(source)
    assert github_write.secret_problem('settings.py', source.encode())


@pytest.mark.parametrize('secret', ['ZKQPVNYRDTMBSXAW', r'Qx7\vN!k9', 'secret123'])
def test_f016_literal_credentials_are_not_mistaken_for_symbolic_references(secret):
    source = 'password = "' + secret + '"'
    assert secret not in review_scan.mask_secrets(source)
    assert github_write.secret_problem('settings.py', source.encode())


def test_one_damaged_shared_fact_does_not_hide_other_confirmed_facts(tmp_path):
    store = Learning(tmp_path)
    store.set_consent(True, LEGAL_VERSION)
    first = ('Photosynthese bezeichnet die Umwandlung von Lichtenergie in chemische Energie '
             'durch Pflanzen und andere Organismen unter Verwendung lichtabsorbierender Stoffe.')
    second = ('Photosynthese liefert Pflanzen chemische Energie aus Lichtenergie und ermöglicht '
              'die Bildung von Zucker aus Wasser und Kohlendioxid in den Blättern.')
    question = 'Wie speichern Pflanzen bei der Photosynthese chemische Energie?'
    assert store.learn(store.ticket(), question, first + ' ' + second,
                       [('https://de.wikipedia.org/wiki/Photosynthese', first + ' ' + second)]) == 2
    assert len(store.recall(question)) == 2
    with store.connect() as conn:
        key = conn.execute('SELECT id FROM learning_facts ORDER BY id LIMIT 1').fetchone()[0]
        conn.execute('UPDATE learning_facts SET text=? WHERE id=?', ('damaged', key))
    assert len(store.recall(question)) == 1


@pytest.mark.skipif(not hasattr(time, 'tzset'), reason='Lokale POSIX-Zeitzone')
def test_f018_hourly_jobs_do_not_skip_the_repeated_hour_at_dst_end(monkeypatch):
    previous = os.environ.get('TZ')
    monkeypatch.setenv('TZ', 'Europe/Berlin')
    time.tzset()
    try:
        now = datetime(2026, 10, 25, 0, 45, tzinfo=UTC).timestamp()
        expected = datetime(2026, 10, 25, 1, 30, tzinfo=UTC).timestamp()
        assert coworker_schedule.next_time('hourly', 8, 30, 0, now) == expected
    finally:
        if previous is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = previous
        time.tzset()


def test_f019_upnp_error_replies_do_not_claim_a_router_has_upnp_enabled(monkeypatch):
    clock = [100.0]

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def setsockopt(self, *args):
            pass

        def settimeout(self, *args):
            pass

        def sendto(self, *args):
            pass

        def recvfrom(self, *args):
            clock[0] += 0.2
            return (b'HTTP/1.1 404 Not Found\r\n'
                    b'ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n\r\n',
                    ('192.168.1.1', 1900))

    monkeypatch.setattr(secure_devices.socket, 'socket', lambda *args: Socket())
    monkeypatch.setattr(secure_devices.time, 'monotonic', lambda: clock[0])
    assert secure_devices.upnp_gateways('192.168.1.0/24', '192.168.1.1', 0.5) == []


@pytest.mark.parametrize(('text', 'expected'), [('-12.50 EUR', '-12.50'), ('1e3', '1000')])
def test_f020_prices_do_not_lose_a_sign_or_exponent(text, expected):
    assert extract.parse_price(text)[0] == expected


@pytest.mark.parametrize(('text', 'currency'), [('CA$ 12.50', 'CAD'), ('AU$ 12.50', 'AUD')])
def test_f021_prefixed_dollar_prices_keep_the_actual_currency(text, currency):
    assert extract.parse_price(text)[1] == currency
