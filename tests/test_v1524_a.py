"""15.2.4: nachgestellte Fehler F001 bis F020."""

from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from aquaticy import addons, budget, cache, coworker_context, google, local_model, pace, search
from aquaticy.memory import Memory


def test_f001_qualified_ollama_names_identify_the_installed_default_registry_model():
    assert local_model.is_installed('registry.ollama.ai/library/qwen3:latest', ['qwen3:latest'])
    assert local_model.is_installed('library/qwen3', ['qwen3:latest'])
    assert not local_model.is_installed('other.example/library/qwen3', ['qwen3:latest'])


def test_f002_timing_out_on_a_parallel_slot_does_not_exceed_the_limit(monkeypatch):
    gate = pace.Gate(parallel=1)
    monkeypatch.setattr(pace, 'MAX_WAIT', 0)
    assert gate._slots.acquire()
    try:
        with pytest.raises(TimeoutError), gate.slot():
            pytest.fail('A second call started despite the occupied slot')
    finally:
        gate._slots.release()


def test_f003_low_rpm_limits_are_not_shortened_to_the_maximum_wait(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(pace.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(pace.time, 'sleep', lambda delay: clock.__setitem__(0, clock[0] + delay))
    gate = pace.Gate(rpm=1)
    with gate.slot():
        pass
    first = clock[0]
    with gate.slot():
        pass
    assert clock[0] - first >= 60


def test_f004_self_closing_void_elements_do_not_truncate_search_titles():
    parser = search._DuckDuckGoHTML()
    parser.feed('<a class="result__a" href="https://example.org">Before<img src="a"/>After</a>')
    assert parser.results[0]['title'] == 'BeforeAfter'


def test_f005_one_malformed_search_url_does_not_abort_the_other_results():
    parser = search._DuckDuckGoHTML()
    parser.feed('<a class="result__a" href="http://[broken">Bad</a>'
                '<a class="result__a" href="https://example.org">Good</a>')
    assert [r['url'] for r in parser.results] == ['https://example.org']


def test_f006_only_actual_duckduckgo_hosts_are_unwrapped():
    url = 'https://notduckduckgo.com/l/?uddg=https%3A%2F%2Fother.example'
    assert search._result_url(url) == url


def test_f007_atom_uses_the_article_link_instead_of_the_last_self_link():
    feed = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>A</title>' \
           b'<link rel="alternate" href="https://example.org/article"/>' \
           b'<link rel="self" href="https://example.org/item.xml"/></entry></feed>'
    assert addons.parse_feed(feed, 'https://example.org/feed')[0]['link'].endswith('/article')


def test_f008_rss_encoded_content_is_available_without_a_description():
    feed = b'<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item>' \
           b'<title>A</title><content:encoded>Useful body</content:encoded></item></channel></rss>'
    result = addons.parse_feed(feed, 'https://example.org/feed')[0]
    assert result['zusammenfassung'] == 'Useful body'


def test_f009_atom_xml_base_is_applied_to_relative_article_links():
    feed = b'<feed xmlns="http://www.w3.org/2005/Atom" xml:base="https://example.org/news/">' \
           b'<entry xml:base="daily/"><title>A</title><link href="story"/></entry></feed>'
    assert addons.parse_feed(feed, 'https://example.org/rss.xml')[0]['link'] \
        == 'https://example.org/news/daily/story'


def test_f010_currency_conversion_to_the_base_itself_keeps_the_amount(monkeypatch):
    monkeypatch.setattr(addons, '_takt', lambda *a: None)
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={'base': 'EUR', 'rates': {}, 'date': '2026-11-06'}))) as http:
        result = addons.currency(12, 'EUR', 'EUR', client=http)
    assert result.get('ergebnis') == {'EUR': 12}


def test_f011_nonfinite_exchange_rates_are_never_returned_as_money(monkeypatch):
    monkeypatch.setattr(addons, '_takt', lambda *a: None)
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, text='{"rates":{"USD":NaN,"CHF":1.2}}'))) as http:
        result = addons.currency(12, 'EUR', client=http)
    assert result['ergebnis'] == {'CHF': 14.4} and 'USD' not in result['kurs']


def test_f012_case_insensitive_memory_search_handles_german_sharp_s(tmp_path):
    store = Memory(tmp_path / 'memory.db')
    store.remember('Die Straße ist lang', 'Weg')
    assert store.recall('STRASSE')


def test_f013_concurrent_file_removal_does_not_break_memory_cleanup(tmp_path, monkeypatch):
    store = Memory(tmp_path / 'memory.db')
    monkeypatch.setattr(budget, 'make_room', lambda *a: 0)
    uploads = tmp_path / 'uploads'
    uploads.mkdir()
    item = uploads / 'old'
    item.write_bytes(b'a')
    original = Path.stat
    calls = [0]
    def stat(path, *a, **kw):
        if path == item:
            calls[0] += 1
            if calls[0] >= 2:
                raise FileNotFoundError(2, 'removed by another request')
        return original(path, *a, **kw)
    monkeypatch.setattr(Path, 'stat', stat)
    assert store.make_room() == 0


def test_f014_profile_usage_does_not_count_external_symlink_targets(tmp_path):
    profile = tmp_path / 'profile'
    profile.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'data').write_bytes(b'x' * 300)
    (profile / 'shared').symlink_to(outside, target_is_directory=True)
    assert budget.used_bytes(profile, fresh=True) == 0


def test_f015_an_empty_chat_identifier_cannot_load_every_chat(settings):
    store = cache.Cache(settings.db_path)
    store.add_history('first', 'private question', 'private answer')
    assert store.chat_history('') == []


def test_f016_zero_ttl_expires_even_within_the_same_clock_tick(settings, monkeypatch):
    monkeypatch.setattr(cache.time, 'time', lambda: 100)
    store = cache.Cache(settings.db_path)
    store.set('probe', {'x': 1}, ttl=0)
    assert store.get('probe') is None


def test_f017_replacing_the_same_cache_entry_does_not_reserve_its_entire_size_again(
    settings, monkeypatch,
):
    store = cache.Cache(settings.db_path)
    amounts = []
    monkeypatch.setattr(budget, 'note_written', lambda folder, amount: amounts.append(amount))
    monkeypatch.setattr(budget, 'fits', lambda *a: True)
    store.set('probe', {'value': 'x' * 100})
    store.set('probe', {'value': 'x' * 100})
    assert amounts[0] > 0 and sum(amounts[1:]) == 0


def test_f018_rotated_google_refresh_tokens_are_saved(monkeypatch):
    monkeypatch.setattr(google, '_token_request', lambda payload: {
        'access_token': 'new-access', 'refresh_token': 'rotated-refresh', 'expires_in': 3600})
    tokens = google.Tokens(refresh_token='old-refresh')
    assert google.refresh_tokens('id', 'secret', tokens).refresh_token == 'rotated-refresh'


def test_f019_invalid_google_json_shapes_raise_a_google_error():
    client = object.__new__(google.Google)
    client._access = lambda: 'synthetic-token'
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json=[]))) as http:
        client._http = http
        with pytest.raises(google.GoogleError):
            client._get('https://gmail.googleapis.com/example', {})


def test_f020_coworker_context_redacts_current_dictionary_api_keys(settings):
    token = 'syntheticCredential1524NeverPublish'
    settings.api_keys = {'NVIDIA_NIM_API_KEY': token}
    current = SimpleNamespace(id=1, sharing_chats=False, sharing_coworkers=True,
                              goal='Preise beobachten', chat='')
    other = SimpleNamespace(id=2, name='Other', notes='Preise: ' + token)
    store = SimpleNamespace(all=lambda: [current, other])
    context = coworker_context.relevant_context(current, store, settings)
    assert 'Preise' in context and token not in context
