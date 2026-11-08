"""15.7.7: Containergrenzen, private Dateien, Bilderexport und Robots-Normalisierung."""

import contextlib
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from aquaticy import (
    budget,
    coworker,
    export,
    fetch,
    local_model,
    media,
    news,
    privacy,
    system,
    webview,
)
from aquaticy.models import Product


def test_f067_day_groups_and_coworker_dates_follow_the_german_clock():
    zone = ZoneInfo('Europe/Berlin')
    now = datetime(2026, 11, 8, 0, 20, tzinfo=zone).timestamp()
    yesterday = datetime(2026, 11, 7, 23, 50, tzinfo=zone).timestamp()
    assert coworker._today(now) == '2026-11-08'
    assert webview.chat_group(yesterday, now) == 'Gestern'
    assert '00:20' in webview.moment_text(now)
    assert news._wann(now) == '08.11. 00:20'


@pytest.mark.parametrize('check', ['memory', 'model_memory', 'cpu'])
def test_f068_resource_detection_honors_cgroup_limits(monkeypatch, check):
    read = Path.read_text

    def value(path, *args, **kwargs):
        fields = {'/proc/meminfo': 'MemTotal: 67108864 kB\nMemAvailable: 33554432 kB\n',
                  '/sys/fs/cgroup/memory.max': str(2 * 1024 ** 3),
                  '/sys/fs/cgroup/memory.current': str(1024 ** 3),
                  '/sys/fs/cgroup/cpu.max': '200000 100000'}
        return fields[str(path)] if str(path) in fields else read(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', value)
    monkeypatch.setattr(system.os, 'cpu_count', lambda: 64)
    monkeypatch.setattr(system.os, 'getloadavg', lambda: (1.0, 1.0, 1.0))
    if check == 'memory':
        assert system.memory_use()['total_gb'] == round(2 * 1024 ** 3 / 1e9, 1)
    elif check == 'model_memory':
        assert local_model.total_memory_gb() == 2.0
    else:
        assert system.cpu_load()['cores'] == 2
        assert system.cpu_load()['percent'] == 50


def test_f069_two_image_exports_do_not_overwrite_the_first_export_assets(tmp_path, monkeypatch):
    monkeypatch.setattr(export.netguard, 'guarded_transport', lambda **kwargs: httpx.MockTransport(
        lambda request: httpx.Response(200, headers={'content-type': 'image/jpeg'},
                                       content=str(request.url).encode())))
    first = export.Turn('', '', products=[Product(name='Machine', url='https://shop.example',
                                                 image_url='https://images.example/first')])
    second = export.Turn('', '', products=[Product(name='Machine', url='https://shop.example',
                                                  image_url='https://images.example/second')])
    initial = export.download_images([first], tmp_path)
    path = tmp_path / next(iter(initial.values()))
    previous = path.read_bytes()
    after = export.download_images([second], tmp_path)
    assert path.read_bytes() == previous
    assert next(iter(after.values())) != path.name


def test_f070_parallel_file_writes_reserve_the_actual_encrypted_storage_size(tmp_path, monkeypatch):
    privacy.profile_sealer(tmp_path)
    (tmp_path / 'keep.bin').write_bytes(b'k' * 400)
    monkeypatch.setattr(budget, 'MAX_BYTES', 600)
    budget.forget(tmp_path)
    seal = privacy.Sealer.seal_bytes
    barrier = threading.Barrier(2)

    def encrypt(self, data, aad):
        encrypted = seal(self, data, aad)
        with contextlib.suppress(threading.BrokenBarrierError):
            barrier.wait(1)
        return encrypted

    monkeypatch.setattr(privacy.Sealer, 'seal_bytes', encrypt)

    def write(data):
        try:
            return media.save_snapshot(tmp_path, data, 'image/png', keep=True)
        except budget.StorageFull:
            return ''

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(write, [b'a' * 50, b'b' * 50]))
    assert sum(bool(result) for result in results) == 1
    assert budget.used_bytes(tmp_path, fresh=True) <= 600


def test_f071_private_uploads_cannot_be_redirected_outside_the_profile(tmp_path):
    profile, outside = tmp_path / 'profile', tmp_path / 'outside'
    profile.mkdir()
    outside.mkdir()
    (profile / 'uploads').symlink_to(outside, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        privacy.write_private(profile / 'uploads' / 'secret.png', b'private', profile)
    assert not list(outside.iterdir())


def test_f072_an_interrupted_private_file_write_preserves_the_previous_content(
        tmp_path, monkeypatch):
    target = tmp_path / 'private.bin'
    privacy.write_private(target, b'Previous bytes', tmp_path)
    previous = target.read_bytes()
    write = Path.write_bytes

    def interrupted(path, data):
        write(path, data[:10])
        raise OSError('interrupted write')

    monkeypatch.setattr(Path, 'write_bytes', interrupted)
    with pytest.raises(OSError):
        privacy.write_private(target, b'Replacement bytes', tmp_path)
    assert target.read_bytes() == previous


def test_f073_escaped_reserved_characters_do_not_create_a_different_robots_allow_rule():
    rules = fetch.RobotsRules([(False, '/private'), (True, '/private%2F')])
    assert not rules.allows('https://example.org/private/file')
    assert rules.allows('https://example.org/private%2Ffile')


def test_f074_a_utf8_bom_does_not_hide_the_first_robots_agent_group():
    rules = fetch.RobotsRules.parse('\ufeffUser-agent: *\nDisallow: /\n', 'aquaticy/15')
    assert not rules.allows('https://example.org/private')
