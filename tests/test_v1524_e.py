"""15.2.4: nachgestellte Fehler F081 bis F100."""

import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest

from aquaticy import (
    addons,
    auth,
    bridge,
    devices,
    google,
    jsonutil,
    linked,
    local_model,
    memory,
    metering,
    old_server,
    router,
    search,
    system,
    usage,
)
from aquaticy.agent import Agent
from aquaticy.tools import Toolbox


def test_f081_ollama_discovery_and_management_bypass_environment_proxies(monkeypatch):
    calls = []
    def get(*a, **kw):
        calls.append(kw)
        return httpx.Response(200, json={'models': [{'name': 'qwen:7b'}]})
    def post(*a, **kw):
        calls.append(kw)
        return httpx.Response(200, json={})
    monkeypatch.setattr(local_model.httpx, 'get', get)
    monkeypatch.setattr(local_model.httpx, 'post', post)
    assert local_model.server_running('http://ollama.local:11434')
    assert local_model.installed_models('http://ollama.local:11434')
    assert local_model.loaded_models('http://ollama.local:11434')
    assert local_model.unload_model('qwen:7b', 'http://ollama.local:11434')
    assert len(calls) == 4 and all(call.get('trust_env') is False for call in calls)


def test_f082_new_notes_cannot_grow_past_the_remaining_storage_budget(settings, monkeypatch):
    store = memory.Memory(settings.db_path)
    monkeypatch.setattr(memory, 'MAX_BYTES', 1000)
    monkeypatch.setattr(store, 'used_bytes', lambda: 950)
    monkeypatch.setattr(store, 'make_room', lambda: 0)
    with pytest.raises(memory.MemoryFull):
        store.remember('X' * 200)
    assert store.count() == 0


def test_f083_usage_fallback_counts_tool_arguments_and_reasoning():
    arguments, thought = 'x' * 300, 'y' * 300
    function = SimpleNamespace(name='web_search', arguments=arguments)
    message = SimpleNamespace(content='', tool_calls=[SimpleNamespace(function=function)],
                              reasoning_content=thought)
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    assert metering._counted([], response)[1] >= usage.tokens(arguments) + usage.tokens(thought)


def test_f084_a_broken_stream_still_accounts_for_its_already_received_answer(settings, monkeypatch):
    agent = Agent(settings, cache=None)
    settled = []
    reservation = SimpleNamespace(kwargs={}, cancel=lambda: None,
                                  settle=lambda a, b: settled.append((a, b)))
    monkeypatch.setattr(agent, '_reserve', lambda *a: reservation)
    def response():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
            content='Already generated answer', tool_calls=[]))])
        raise httpx.ReadError('Connection dropped')
    from aquaticy import llmcall
    monkeypatch.setattr(llmcall, 'completion', lambda **kw: response())
    try:
        with pytest.raises(httpx.ReadError):
            agent._completion([{'role': 'user', 'content': 'Question'}], stream=True)
        assert len(settled) == 1 and settled[0][1] >= usage.tokens('Already generated answer')
    finally:
        agent.close()


def test_f085_oversized_device_numbers_do_not_crash_registration():
    assert devices.clean_device({'cores': 10 ** 1000}).hardware_hash == ''
    assert '8 Kerne' in devices.clean_device({'cores': 8}).hardware


@pytest.mark.parametrize('text', ['NaN', 'Infinity', '-Infinity', '{"x":NaN}'])
def test_f086_network_json_rejects_nonstandard_nonfinite_literals(text):
    with pytest.raises(ValueError):
        jsonutil.loads(text)
    with pytest.raises(ValueError):
        jsonutil.raw_decode(text)


def test_f087_storage_tool_calls_can_create_zero_stock(settings, monkeypatch):
    box = Toolbox(settings)
    monkeypatch.setattr(box, 'storage_add', lambda **kw: kw)
    try:
        assert box._call('storage_add', {'name': 'Spare part', 'furniture_id': 1,
                                         'quantity': 0})['quantity'] == 0
    finally:
        box.close()


def test_f088_plain_messenger_text_keeps_literal_multiplication_operators():
    text = bridge.to_chat_text('Das Ergebnis ist 2*3=6. **Richtig.**')
    assert '2*3=6' in text and '**' not in text


def test_f089_models_are_not_hidden_before_their_announced_deprecation_date():
    def handle(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': 'small-latest',
                'deprecation': '2099-01-01T00:00:00Z', 'capabilities': {'completion_chat': True}}]})
        return httpx.Response(200, json={})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        info = linked.inspect('mistral', 'synthetic-token', client)
    assert [m['id'] for m in info['models']] == ['mistral/small-latest']


def test_f090_unexpected_weather_payloads_return_an_error_instead_of_crashing(monkeypatch):
    monkeypatch.setattr(addons, '_takt', lambda *a: None)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[1]))) as c:
        assert addons.weather('Berlin', client=c).get('error')


def test_f091_weather_never_silently_uses_a_different_country(monkeypatch):
    monkeypatch.setattr(addons, '_takt', lambda *a: None)
    requests = []
    def handle(request):
        requests.append(request)
        if request.url.host == 'geocoding-api.open-meteo.com':
            return httpx.Response(200, json={'results': [{'name': 'Berlin', 'country': 'Germany',
                'country_code': 'DE', 'latitude': 52.5, 'longitude': 13.4}]})
        return httpx.Response(200, json={})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = addons.weather('Berlin, US', client=client)
    assert result.get('error') and len(requests) == 1


def test_f092_atom_xhtml_blocks_do_not_join_separate_words():
    feed = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>News</title>
    <content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml">
    <p>Alpha</p><p>Beta</p></div></content></entry></feed>'''
    assert addons.parse_feed(feed, 'https://example.org/feed')[0]['zusammenfassung'] == 'Alpha Beta'


def test_f093_refreshing_google_tokens_also_updates_the_effective_permissions(monkeypatch):
    tokens = google.Tokens(refresh_token='old', scopes=list(google.WRITE_SCOPES))
    monkeypatch.setattr(google, '_token_request', lambda p: {'access_token': 'new',
        'expires_in': 3600, 'scope': ' '.join(google.SCOPES)})
    google.refresh_tokens('client', 'secret', tokens)
    assert google.granted_write(tokens.scopes) == (False, False)


def test_f094_parallel_google_requests_share_a_single_token_refresh(settings, monkeypatch):
    store = google.TokenStore(settings.data_dir)
    store.save(google.Tokens(refresh_token='old-refresh', expires_at=0))
    started, release, second_read = threading.Event(), threading.Event(), threading.Event()
    calls = []
    def remote(payload):
        calls.append(payload)
        index = len(calls)
        started.set()
        assert release.wait(3)
        if index > 1:
            raise google.GoogleError('Old refresh token already rotated')
        return {'access_token': 'new-access', 'refresh_token': 'new-refresh', 'expires_in': 3600}
    monkeypatch.setattr(google, '_token_request', remote)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    with httpx.Client(transport=transport) as http:
        one = google.Google('client', 'secret', store, client=http)
        two = google.Google('client', 'secret', google.TokenStore(settings.data_dir), client=http)
        original = two.tokens
        def tokens():
            result = original()
            second_read.set()
            return result
        monkeypatch.setattr(two, 'tokens', tokens)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(one._access)
            try:
                assert started.wait(3)
                second = pool.submit(two._access)
                assert second_read.wait(3)
            finally:
                release.set()
            assert first.result(3) == second.result(3) == 'new-access'
    assert len(calls) == 1


@pytest.mark.parametrize('provider', ['mistral', 'nvidia_nim'])
def test_f095_invalid_linked_model_catalogues_raise_a_useful_service_error(provider):
    def handle(request):
        return httpx.Response(200, json=[] if request.method == 'GET' else {})
    with (httpx.Client(transport=httpx.MockTransport(handle)) as client,
          pytest.raises(linked.LinkError)):
        linked.inspect(provider, 'synthetic-token', client)


def test_f096_changing_the_configured_code_model_invalidates_router_choices(settings, monkeypatch):
    router.forget()
    monkeypatch.setattr(system, 'strongest_model', lambda s, **kw: s.code_model)
    settings.code_model = 'mistral/first'
    assert router.choose(settings, 'Schreibe Python Code').model == 'mistral/first'
    settings.code_model = 'mistral/second'
    assert router.choose(settings, 'Schreibe Python Code').model == 'mistral/second'
    router.forget()


def test_f097_login_sessions_are_expired_at_the_exact_expiry_instant(tmp_path, monkeypatch):
    store = auth.AuthStore(tmp_path, 'PRO123456')
    account = store.register('reader@example.org', 'long synthetic password', 'normal',
                             terms_accepted=True, terms_version='test')
    monkeypatch.setattr(auth.time, 'time', lambda: 100)
    token = store.create_session(account, 'browser', '192.168.1.20')
    with store._connect() as conn:
        conn.execute('UPDATE sessions SET expires_at=100')
    assert store.session_account(token, 'browser') is None
    assert store.session_count(account.id) == 0


def test_f098_local_version_probes_stop_reading_after_the_page_size_limit(monkeypatch):
    seen = []
    class Body(httpx.SyncByteStream):
        def __iter__(self):
            for i in range(2048):
                chunk = (b'window.__AQUATICY_VERSION__ = "15.2.3";' if i == 0 else b'')
                seen.append(1024)
                yield chunk.ljust(1024, b' ')
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(
        200, stream=Body())))
    monkeypatch.setattr(old_server.httpx, 'Client', lambda **kw: client)
    assert old_server.running_version(8765) == '15.2.3'
    assert sum(seen) <= 500_000


def test_f099_brave_receives_lowercase_language_codes(monkeypatch):
    sent = []
    def get(*a, **kw):
        sent.append(kw['params'])
        return httpx.Response(200, json={'web': {'results': []}})
    monkeypatch.setattr(search.httpx, 'get', get)
    search._search_brave('Question', search.SearchOptions(lang='DE', api_key='synthetic'))
    assert sent[0]['search_lang'] == 'de'


def test_f100_search_result_text_does_not_expose_provider_highlight_markup(monkeypatch):
    monkeypatch.setattr(search.httpx, 'get', lambda *a, **kw: httpx.Response(200, json={
        'web': {'results': [{'title': 'Clean &amp; <strong>safe</strong>',
                             'url': 'https://example.org',
                             'description': 'A <strong>useful</strong> page.'}]}}))
    result = search._search_brave('Question', search.SearchOptions(api_key='synthetic'))[0]
    assert result.title == 'Clean & safe' and result.snippet == 'A useful page.'
