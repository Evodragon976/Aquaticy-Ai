"""15.7.7: Speicher, Widerruf, Quellen und verlaessliche Warnungen."""

import base64
import contextlib
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from aquaticy import addons, budget, google, places, secure_pro, secure_tasks, website
from aquaticy.cache import Cache


def test_f090_concurrent_sql_cache_writes_do_not_spend_the_same_free_space(tmp_path, monkeypatch):
    cache = Cache(tmp_path / 'state.db')
    initial = budget.used_bytes(tmp_path, fresh=True)
    monkeypatch.setattr(budget, 'MAX_BYTES', int((initial + 35000) / budget.CLEANUP_AT))
    fits = budget.fits
    barrier = threading.Barrier(2)

    def simultaneous(*args):
        result = fits(*args)
        with contextlib.suppress(threading.BrokenBarrierError):
            barrier.wait(.2)
        return result

    monkeypatch.setattr(budget, 'fits', simultaneous)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda key: cache.set(key, 'x' * 20000), ['a', 'b']))
    assert sum(cache.get(key) is not None for key in ('a', 'b')) == 1


def test_f091_a_delayed_github_login_cannot_undo_logout(settings):
    addons._update(settings, 'github', installed=True)

    def respond(request):
        addons.logout(settings, 'github')
        return httpx.Response(200, json={'login': 'owner'})

    with (httpx.Client(transport=httpx.MockTransport(respond)) as client,
          pytest.raises(addons.AddOnError)):
        addons.github_login(settings, 'ghp_' + 'a' * 30, client=client)
    assert not addons.github_token(settings)


def test_f092_a_running_tunnel_log_is_bounded_without_restarting_the_process(tmp_path, monkeypatch):
    monkeypatch.setattr(website, 'MAX_LOG_BYTES', 1024)
    payload = b'noise\n' * 2000 + b'last log line\n'

    class Process:
        def __init__(self, args, **kw):
            self.stdout = io.BytesIO(payload)
            if kw.get('stdout') != website.subprocess.PIPE:
                kw['stdout'].write(payload)

        def wait(self):
            return 1

    tunnel = website.Tunnel(tmp_path, lambda: 'token', locate=lambda: Path('/bin/true'),
                            popen=Process, sleep=lambda pause: True)
    tunnel._run()
    log = website.site_dir(tmp_path) / 'cloudflared.log'
    assert log.stat().st_size <= website.MAX_LOG_BYTES
    assert log.read_bytes().endswith(b'last log line\n')


def test_f093_addon_state_writes_do_not_follow_a_predictable_temporary_symlink(settings, tmp_path):
    folder = Path(settings.data_dir)
    folder.mkdir()
    outside = tmp_path / 'other-private-file'
    outside.write_bytes(b'Previous private bytes')
    addons._state_path(settings).with_suffix('.tmp').symlink_to(outside)
    addons._update(settings, 'feeds', installed=True)
    assert outside.read_bytes() == b'Previous private bytes'


@pytest.mark.parametrize('address', ['2001:4860:4860::8888', 'fd00::1234'])
def test_f095_unsupported_ipv6_task_filters_cannot_turn_into_network_wide_tasks(address):
    with pytest.raises(ValueError):
        secure_tasks.parse(f'Melde Malware bei {address}.')


@pytest.mark.parametrize('lat,lon', [('NaN', 8), (200, 8), (52, 300), (None, None)])
def test_f096_invalid_map_result_coordinates_use_the_unknown_location_fallback(
        monkeypatch, lat, lon):
    monkeypatch.setattr(places, 'geocode', lambda *a, **kw: (52, 8, 'Town'))
    monkeypatch.setattr(places, '_warte', lambda: None)
    data = {'elements': [{'tags': {'name': 'Incorrect'}, 'lat': lat, 'lon': lon},
                         {'tags': {'name': 'Correct'}, 'lat': 52, 'lon': 8}]}
    monkeypatch.setattr(places, '_client', lambda *a: httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data))))
    result, _ = places.find_places('cafe', 'Town', 'aquaticy')
    assert [item.name for item in result] == ['Incorrect', 'Correct']
    assert (result[0].lat, result[0].lon) == (0.0, 0.0)
    assert (result[1].lat, result[1].lon) == (52, 8)


@pytest.mark.parametrize('link', ['javascript:alert(1)', 'data:text/html,bad',
                                 'https://name:password@example.org/private'])
def test_f097_a_feed_cannot_deliver_active_or_credential_bearing_article_links(link):
    data = f'<rss><channel><item><title>Article</title><link>{link}</link></item></channel></rss>'
    assert addons.parse_feed(data.encode(), 'https://example.org/feed')[0]['link'] == ''


def test_f098_html_mail_table_cells_do_not_merge_distinct_numbers():
    data = base64.urlsafe_b64encode(b'<table><tr><td>120</td><td>300</td></tr></table>').decode()
    result = google._body_text({'mimeType': 'text/html', 'body': {'data': data}})
    assert result.split() == ['120', '300']


def test_f099_optional_observances_are_not_reported_as_statutory_holidays(monkeypatch):
    monkeypatch.setattr(addons, '_takt', lambda *a: None)
    data = [{'date': '2026-04-03', 'localName': 'Good Friday', 'global': True,
             'types': ['Optional']}]
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=data))
    with httpx.Client(transport=transport) as client:
        result = addons.holidays('US', 2026, client=client)
    day = result['feiertage'][0]
    assert day.get('gesetzlich') is False
    assert day.get('arten') == ['Optional']


def test_f100_a_failed_security_check_warning_is_retried_until_delivered(tmp_path, monkeypatch):
    secure_pro.configure(tmp_path, '192.168.1.0/24')
    sent = []
    watcher = secure_pro.Watcher(tmp_path, lambda text: sent.append(text) or len(sent) >= 2)
    monkeypatch.setattr(watcher, 'tick', lambda: (_ for _ in ()).throw(OSError('scan failed')))
    rounds = []

    def pause():
        rounds.append(True)
        if len(rounds) == 2:
            watcher.stop_event.set()
        return 0

    monkeypatch.setattr(watcher, '_wait_seconds', pause)
    watcher._run()
    assert len(sent) == 2
