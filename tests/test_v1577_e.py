"""15.7.7: Modellgrenzen, Einwilligung und Produktdaten."""

import json
from contextlib import closing, contextmanager
from types import SimpleNamespace

import pytest

from aquaticy import config, extract, github_write, memory_auto, voice
from tests.test_bridge_native import Werkstatt


def test_f040_local_parallelism_cannot_exceed_the_number_of_planned_agents(settings):
    settings.model = 'ollama_chat/qwen:7b'
    assert settings.parallel_for(1) == 1


@pytest.mark.parametrize('url', ['http://localhost:wrong', 'http://[broken', 'http://host:99999'])
def test_f041_a_malformed_endpoint_does_not_crash_ollama_detection(url):
    assert config.is_ollama_base(url) is False


@pytest.mark.parametrize('method', ['transcribe', 'synthesize'])
def test_f043_disabling_voice_while_waiting_stops_the_queued_conversion(monkeypatch, method):
    active = [True]
    monkeypatch.setattr(voice, 'enabled', lambda: active[0])

    @contextmanager
    def wait():
        active[0] = False
        yield

    calls = []
    monkeypatch.setattr(voice, '_processing', wait)
    monkeypatch.setattr(voice, 'root', lambda: pytest.fail('must not access voice data'))
    monkeypatch.setattr(voice.subprocess, 'run', lambda *a, **kw: calls.append(a) or
                        SimpleNamespace(stdout=b'', returncode=0))
    with pytest.raises(ValueError, match=r'aus|deaktiviert|Freigabe'):
        getattr(voice, method)(b'audio' if method == 'transcribe' else 'Private text')
    assert calls == []


@pytest.mark.parametrize('text', [
    'Mein Bruder sagt: Ich wohne in Hamburg.',
    'Das Beispiel lautet: Ich heiße Lisa.',
    'Er schrieb: Ich arbeite als Koch.',
])
def test_f044_reported_first_person_speech_is_not_saved_as_the_users_own_fact(text):
    assert memory_auto.extract(text) == []


def test_f045_failed_read_receipts_can_be_retried(tmp_path):
    case = Werkstatt(tmp_path)
    msg = case.nachricht()
    attempts = []

    def read(message):
        attempts.append(message)
        if len(attempts) == 1:
            raise OSError('temporary connection failure')

    transport = SimpleNamespace(mark_read=read)
    case.antwort._mark_read(msg, transport)
    case.antwort._mark_read(msg, transport)
    assert len(attempts) == 2


def test_f046_rejected_senders_do_not_write_the_deduplication_database(tmp_path):
    case = Werkstatt(tmp_path, wer='selbst')
    calls = []
    reason, _, _ = case.antwort._screen(case.nachricht(),
                                      {'an': True, 'wer': 'selbst'},
                                      lambda: calls.append(True) or True)
    assert reason.startswith('abgelehnt')
    assert calls == []


@pytest.mark.parametrize('scheme', ['postgresql', 'mysql', 'https'])
def test_f047_credentials_embedded_in_connection_urls_cannot_be_pushed(scheme):
    text = f'DATABASE_URL="{scheme}://user:ActualPrivatePass234@database.example/db"'
    assert github_write.secret_problem('settings.env', text.encode())


def test_f048_jsonld_properties_obey_the_product_specification_limit():
    data = {'@type': 'Product', 'name': 'Machine', 'additionalProperty': [
        {'name': f'Property {i}', 'value': f'Value {i}'} for i in range(100)]}
    html = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
    result = extract.extract_product(html, 'https://shop.example/product')
    assert result is not None and len(result.specs) <= extract.MAX_SPECS


def test_f049_fallbacks_cannot_apply_an_unrelated_currency_to_a_different_price():
    data = {'@type': 'Product', 'name': 'Machine', 'offers': {'price': '199'}}
    html = ('<script type="application/ld+json">' + json.dumps(data) + '</script>'
            '<meta property="og:title" content="Machine">'
            '<meta property="product:price:amount" content="249">'
            '<meta property="product:price:currency" content="EUR">')
    result = extract.extract_product(html, 'https://shop.example/product')
    assert result is not None and result.price == '199'
    assert result.currency is None


@pytest.mark.parametrize('operation', ['server_running', 'installed_models', 'loaded_models'])
def test_f042_ollama_list_responses_are_stopped_at_a_fixed_byte_limit(monkeypatch, operation):
    import httpx

    from aquaticy import local_model

    read = []

    class Body(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(100):
                read.append(1)
                yield b' ' * 65536

    @contextmanager
    def stream(*args, **kwargs):
        with closing(httpx.Response(200, stream=Body())) as response:
            yield response

    def get(*args, **kwargs):
        with stream() as response:
            response.read()
            return response

    monkeypatch.setattr(local_model.httpx, 'stream', stream)
    monkeypatch.setattr(local_model.httpx, 'get', get)
    result = getattr(local_model, operation)('http://ollama.local:11434')
    assert not result
    assert len(read) < 100
