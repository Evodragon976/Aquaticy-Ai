"""15.2.4: nachgestellte Fehler F021 bis F040."""

import contextlib
import threading
from types import SimpleNamespace

import pytest
from rich.console import Console
from selectolax.parser import HTMLParser

from aquaticy import (
    addons,
    cli,
    coworker,
    coworker_context,
    extract,
    local_model,
    messenger_native,
    secure_chat,
)
from aquaticy.agent import AgentResult
from aquaticy.config import Settings


class Worker:
    def __init__(self, error=''):
        self.error = error
        self.closed = False
        self.toolbox = SimpleNamespace(untrusted_seen=False)

    def ask(self, *a, **kw):
        return AgentResult(error=self.error, answer='')

    def close(self):
        self.closed = True


def test_f021_failed_coworker_steps_do_not_acknowledge_unprocessed_orders(settings):
    store = coworker.CoworkerStore(settings.db_path)
    cw = store.add('Ava', 'Beobachte die Preise')
    store.add_log(cw.id, 'nachricht', 'Neue Aufgabe')
    coworker.run_session(cw, settings, 'pro', store=store, vm=False,
                         agent_factory=lambda *a: Worker('Network error'))
    assert store.unread_messages(cw.id)


def test_f022_setup_failures_still_close_the_coworker_agent(settings, monkeypatch):
    store = coworker.CoworkerStore(settings.db_path)
    cw = store.add('Ava', 'Beobachte die Preise')
    agent = Worker()
    def broken(*args):
        raise OSError('Context unavailable')
    monkeypatch.setattr(coworker_context, 'relevant_context', broken)
    with contextlib.suppress(OSError):
        coworker.run_session(cw, settings, 'pro', store=store, vm=False,
                             agent_factory=lambda *a: agent)
    assert agent.closed


def test_f023_log_rotation_does_not_discard_unprocessed_user_orders(settings, monkeypatch):
    monkeypatch.setattr(coworker, 'LOG_KEEP', 2)
    store = coworker.CoworkerStore(settings.db_path)
    cw = store.add('Ava', 'Beobachte die Preise')
    store.add_log(cw.id, 'nachricht', 'Unprocessed')
    store.add_log(cw.id, 'schritt', 'First step', seen=True)
    store.add_log(cw.id, 'schritt', 'Second step', seen=True)
    assert [m['text'] for m in store.unread_messages(cw.id)] == ['Unprocessed']


def test_f024_messenger_signatures_fit_inside_the_message_size_limit():
    parts = messenger_native.message_parts('x' * (messenger_native.MAX_SEND_CHARS * 2 + 50))
    assert len(parts) >= 3
    assert all(len(part) <= messenger_native.MAX_SEND_CHARS for part in parts)


def test_f025_a_fitting_url_is_not_split_just_to_fill_the_previous_message():
    url = 'https://example.org/' + 'x' * 40
    parts = messenger_native.split_text('A short ' + url, limit=64)
    assert url in parts


def test_f026_message_splitting_preserves_code_indentation():
    text = 'first-line\n    return 1'
    parts = messenger_native.split_text(text, limit=14)
    assert any(part.startswith('    return') for part in parts)
    assert ''.join(parts) == text


def test_f027_signal_text_delivery_waits_for_the_rpc_confirmation(monkeypatch):
    transport = object.__new__(messenger_native.SignalTransport)
    calls = []
    monkeypatch.setattr(transport, '_rpc', lambda method, params, **kw: calls.append(kw))
    transport.send('+491701234567', 'Hello')
    assert calls and all(call.get('wait') is True for call in calls)


def test_f028_signal_disconnect_wakes_waiting_rpc_callers(monkeypatch):
    transport = object.__new__(messenger_native.SignalTransport)
    done = threading.Event()
    transport._pending_rpc = {1: (done, [])}
    transport._send_lock = threading.Lock()
    transport._stopping = threading.Event()
    transport._config = lambda: []
    transport._set = lambda *a, **kw: None
    transport._popen = lambda *a, **kw: SimpleNamespace(stdout=[], wait=lambda: 1)
    transport._daemon('+491701234567')
    assert done.is_set()


def test_f029_configured_local_vision_models_also_start_ollama(monkeypatch):
    settings = Settings(model='mistral/mistral-large-latest', vision_model='ollama_chat/qwen3:8b')
    started = []
    monkeypatch.setattr(local_model, 'server_running', lambda *a, **kw: False)
    monkeypatch.setattr(local_model, 'ollama_binary', lambda: 'ollama')
    monkeypatch.setattr(local_model, 'start_server', lambda *a, **kw: started.append(a) or True)
    monkeypatch.setattr(local_model, 'installed_models', lambda *a: ['qwen3:8b'])
    cli._ollama_beim_start(settings)
    assert started


def test_f030_changing_search_language_does_not_replace_the_country_with_a_language_code():
    settings = Settings(country='at', lang='de')
    cli._apply_overrides(settings, '', 'en', '', '', 0)
    assert settings.lang == 'en' and settings.country == 'at'


def test_f031_terminal_commands_accept_tabs_as_argument_separators(monkeypatch):
    locations = []
    agent = SimpleNamespace(set_location=locations.append)
    cli._handle_slash('/location\tBremen', agent, Settings(), [], None)
    assert locations == ['Bremen']


def test_f032_terminal_model_errors_are_printed_as_data(monkeypatch):
    console = Console(record=True, width=100)
    monkeypatch.setattr(cli, 'console', console)
    result = AgentResult(answer='', error='Model replied [/broken]')
    agent = SimpleNamespace(ask=lambda *a, **kw: result)
    renderer = SimpleNamespace(reset=lambda: None)
    assert cli._run_turn(agent, renderer, 'q', True, False) is result
    assert '[/broken]' in console.export_text()


@pytest.mark.parametrize('code', [float('nan'), float('inf'), 0.5])
def test_f033_invalid_weather_codes_do_not_report_clear_weather_or_crash(code):
    assert addons._wetterlage(code) == 'unbekannt'


def test_f034_private_home_arpa_names_never_enter_public_advisory_search():
    assert not secure_chat.public_query('router.home.arpa vulnerabilities')


def test_f035_rss_permalink_guids_are_used_when_the_link_is_missing():
    feed = b'<rss><channel><item><title>A</title><guid isPermaLink="true">' \
           b'https://example.org/story</guid></item></channel></rss>'
    assert addons.parse_feed(feed, 'https://example.org/feed')[0]['link'] \
        == 'https://example.org/story'


def test_f036_empty_feed_descriptions_do_not_hide_available_content():
    feed = b'<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item>' \
           b'<title>A</title><description> </description>' \
           b'<content:encoded>Body</content:encoded></item></channel></rss>'
    assert addons.parse_feed(feed, 'https://example.org/feed')[0]['zusammenfassung'] == 'Body'


def test_f037_atom_text_and_html_types_are_rendered_according_to_the_declared_type():
    feed = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry>' \
           b'<title type="html">&lt;b&gt;Headline&lt;/b&gt;</title>' \
           b'<summary type="text">Use &lt;vector&gt; in C++</summary></entry></feed>'
    result = addons.parse_feed(feed, 'https://example.org/feed')[0]
    assert result['titel'] == 'Headline'
    assert result['zusammenfassung'] == 'Use <vector> in C++'


def test_f038_feed_html_entities_are_decoded_for_readers():
    feed = b'<rss><channel><item><title>A</title><description><![CDATA[' \
           b'<p>One &amp; two</p>]]></description></item></channel></rss>'
    assert addons.parse_feed(feed, 'https://example.org/feed')[0]['zusammenfassung'] == 'One & two'


def test_f039_nested_microdata_brand_names_do_not_replace_product_names():
    tree = HTMLParser('<div itemscope itemtype="https://schema.org/Product">'
        '<div itemprop="brand" itemscope itemtype="https://schema.org/Brand">'
        '<span itemprop="name">Brand</span></div><span itemprop="name">Camera</span>'
        '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
        '<meta itemprop="price" content="10"></div></div>')
    product = extract.product_from_microdata(tree, 'https://example.org')
    assert product is not None and product.name == 'Camera' and product.price == '10'


def test_f040_named_jsonld_brands_use_the_name_instead_of_the_identifier_url():
    tree = HTMLParser('<script type="application/ld+json">{"@type":"Product","name":"Camera",'
        '"brand":{"@type":"Brand","@id":"https://example.org/brand","name":"Acme"}}'
        '</script>')
    product = extract.product_from_jsonld(tree, 'https://example.org')
    assert product is not None and product.specs['Marke'] == 'Acme'
