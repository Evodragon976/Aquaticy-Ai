"""15.4.4: Eingabegrenzen, private Dateien und befristete Modellwahl."""

from pathlib import Path

import httpx
import pytest

from aquaticy import media, router, storage, system


@pytest.mark.parametrize('quantity', [1.5, True, -1])
def test_i01_invalid_inventory_numbers_never_change_stock(quantity):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(201, json={'id': 1})
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = storage.Storage('http://inventory.local', 'write', client=http)
        with pytest.raises(storage.StorageError):
            client.add_item(1, 'Screws', quantity)
    assert calls == []


def test_inventory_ids_are_not_silently_truncated():
    calls = []
    with httpx.Client(transport=httpx.MockTransport(lambda request:
            calls.append(request) or httpx.Response(200, json={'id': 1}))) as http:
        client = storage.Storage('http://inventory.local', 'write', client=http)
        with pytest.raises(storage.StorageError):
            client.update_item(1.5, quantity=5)
    assert calls == []


@pytest.mark.parametrize('payload', [[], None, {}, {'error': 'rejected'}])
def test_i02_invalid_inventory_write_responses_are_not_reported_as_success(payload):
    with httpx.Client(transport=httpx.MockTransport(lambda request:
            httpx.Response(201, json=payload))) as http:
        client = storage.Storage('http://inventory.local', 'write', client=http)
        with pytest.raises(storage.StorageError):
            client.add_room('Office')


@pytest.mark.parametrize('kind', ['file', 'directory'])
def test_i03_private_media_never_reads_through_links_into_other_directories(tmp_path, kind):
    profile, outside = tmp_path / 'profile', tmp_path / 'outside'
    profile.mkdir()
    outside.mkdir()
    identifier = '1000000000000-' + 'a' * 16 + '.png'
    secret = outside / identifier
    secret.write_bytes(b'private-data')
    folder = profile / 'media'
    if kind == 'directory':
        folder.symlink_to(outside, target_is_directory=True)
    else:
        folder.mkdir()
        (folder / identifier).symlink_to(secret)
    assert media.snapshot_path(profile, identifier) is None
    assert media.load_snapshot(profile, identifier) is None
    assert not media.delete_snapshot(profile, identifier)
    assert secret.read_bytes() == b'private-data'


def test_media_writes_do_not_follow_a_replaced_media_directory(tmp_path):
    profile, outside = tmp_path / 'profile', tmp_path / 'outside'
    profile.mkdir()
    outside.mkdir()
    (profile / 'media').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        media.save_snapshot(profile, b'png', 'image/png')
    assert not list(outside.iterdir())


def test_i04_expired_model_routing_entries_do_not_accumulate(settings, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(router.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(system, 'strongest_model', lambda *args, **kwargs: 'mistral/example')
    router.forget()
    try:
        for number in range(20):
            settings.data_dir = Path('profile-' + str(number))
            assert router._staerkstes(settings, 'work') == 'mistral/example'
            clock[0] += 31
        assert len(router._cache) <= 1
    finally:
        router.forget()


def test_i05_quick_replies_apply_mode_and_privacy_settings(settings):
    from aquaticy.agent import Agent
    agent = Agent(settings)
    try:
        assert agent.ask('Hallo', mode='code', online=False, structured=False,
                         recheck=True, stream=False).answer
        assert agent.mode == 'code' and not agent.online
        assert not agent.structured and agent.recheck
        names = {tool['function']['name'] for tool in agent.tools}
        assert not names.intersection({'remember', 'save_memory', 'recall_memory'})
    finally:
        agent.close()
