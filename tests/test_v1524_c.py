"""15.2.4: nachgestellte Fehler F041 bis F060."""

import json
import threading
from types import SimpleNamespace

import httpx
import pytest
from selectolax.parser import HTMLParser

from aquaticy import (
    addons,
    coworker_schedule,
    export,
    extract,
    github_repo,
    google,
    homeassistant,
    linked,
    places,
    queries,
    secure_tasks,
    storage,
)
from aquaticy.agent import AgentResult
from aquaticy.models import Product
from aquaticy.tools import Toolbox


def test_f041_each_currency_pair_must_respect_the_euro_permission(settings, monkeypatch):
    box = object.__new__(Toolbox)
    box.settings = settings
    box.stats = SimpleNamespace(addon_calls=0)
    monkeypatch.setattr(addons, 'active', lambda *a: True)
    monkeypatch.setattr(addons, 'rights_of', lambda *a: {'waehrungen': 'euro'})
    calls = []
    monkeypatch.setattr(addons, 'currency', lambda *a: calls.append(a) or {'ok': True})
    result = box._addon_call('currency', {'amount': 10, 'base': 'USD', 'to': 'EUR,CHF'})
    assert result.get('error') and not calls
    assert box._addon_call('currency', {'base': 'USD', 'to': 'EUR'}) == {'ok': True}
    assert box._addon_call('currency', {'base': 'EUR', 'to': 'USD,CHF'}) == {'ok': True}


def test_f042_calendar_descriptions_and_locations_can_be_explicitly_cleared():
    client = object.__new__(google.Google)
    sent = []
    client._write = lambda method, url, payload: sent.append(payload) or {'id': 'event1'}
    client.update_event('event1', description='', location='')
    assert sent == [{'description': '', 'location': ''}]
    with pytest.raises(google.GoogleError):
        client.update_event('event1')


def test_f043_home_assistant_cached_states_cannot_be_modified_by_the_caller(monkeypatch):
    homeassistant.forget_states()
    client = homeassistant.HomeAssistant('http://house.local:8123', 'synthetic-token')
    monkeypatch.setattr(client, '_request', lambda *a: [
        {'entity_id': 'light.office', 'state': 'off', 'attributes': {}}])
    first = client.states()
    first[0].state = 'on'
    first.clear()
    assert [(e.entity_id, e.state) for e in client.states()] == [('light.office', 'off')]


def test_f044_github_file_windows_inside_a_private_key_remain_redacted():
    body = 'QUFB' * 15
    raw = ('-----BEGIN PRIVATE KEY-----\n' + body + '\n-----END PRIVATE KEY-----\n').encode()
    import base64
    data = {'encoding': 'base64', 'size': len(raw), 'content': base64.b64encode(raw).decode()}
    result = github_repo.read_file(lambda *a, **kw: data, 'owner/project', 'key.pem',
                                   'main', start=2, lines=1)
    assert body not in result['text'] and 'verdeckt' in result['text']


def test_f045_nonrecursive_github_trees_open_the_requested_subdirectory():
    commit, root, child = 'a' * 40, 'b' * 40, 'c' * 40
    def get(route, **kw):
        if '/commits/' in route:
            return {'sha': commit, 'commit': {'tree': {'sha': root}}}
        if route.endswith('/' + root):
            return {'tree': [{'path': 'src', 'type': 'tree', 'sha': child}]}
        assert route.endswith('/' + child)
        return {'tree': [{'path': 'app.py', 'type': 'blob', 'sha': 'd' * 40}]}
    result = github_repo.tree(get, 'owner/project', 'main', 'src', 1, recursive=False)
    assert [e['path'] for e in result['eintraege']] == ['src/app.py']
    assert result['commit'] == commit


def test_f046_council_rejects_a_single_linked_provider(settings, monkeypatch):
    monkeypatch.setattr(linked, 'council_roles', lambda s: ([('one', 'one/model')], None))
    stop = threading.Event()
    stop.set()
    with pytest.raises(linked.LinkError, match='zwei'):
        linked.run_council(settings, 'Hello', stop=stop)


def test_f047_cancelling_council_work_prevents_checker_and_judge_calls(settings, monkeypatch):
    monkeypatch.setattr(linked, 'council_roles', lambda s: (
        [('one', 'one/model')], ('two', 'two/model')))
    stop = threading.Event()
    calls = []
    def ask(settings, model, *a, **kw):
        calls.append(model)
        stop.set()
        return 'Result'
    monkeypatch.setattr(linked, '_ask', ask)
    assert linked.run_council(settings, 'Hello', stop=stop) == ''
    assert calls == ['one/model']


def test_f048_an_oversized_secure_task_port_is_not_silently_ignored():
    with pytest.raises(ValueError, match='Port'):
        secure_tasks.parse('Melde einen neuen Port 100000 auf 192.168.1.20')


def test_f049_a_secure_task_does_not_silently_ignore_additional_hosts():
    with pytest.raises(ValueError):
        secure_tasks.parse('Melde wenn 192.168.1.20 und 192.168.1.21 offline gehen')


def test_f050_price_monitors_do_not_compare_different_currencies():
    product = Product(name='Item', url='https://shop.example/item', price='20', currency='USD')
    assert coworker_schedule.price_condition_met('Unter 50 EUR', [product]) is None
    product.currency = 'EUR'
    assert coworker_schedule.price_condition_met('Unter 50 EUR', [product]) is True


def test_f051_negated_price_limits_are_not_interpreted_as_upper_bounds():
    product = Product(name='Item', url='https://shop.example/item', price='20', currency='EUR')
    assert coworker_schedule.price_condition_met('Nicht unter 50 EUR', [product]) is False


def test_f052_a_price_monitor_only_uses_prices_from_its_verified_source(settings):
    job = coworker_schedule.JobStore(settings.db_path).add(
        'Unter 50 EUR', kind='price', source_url='https://shop.example/watched')
    class Agent:
        session_id = 'monitor'
        def ask(self, *a, **kw):
            return AgentResult(answer='BEDINGUNG ERFÜLLT', products=[Product(
                name='Other', url='https://other.example/item', price='20', currency='EUR')])
        def close(self):
            pass
    state, chat = coworker_schedule.run_job(job, settings, agent_factory=lambda *a, **kw: Agent())
    assert state == 'kein prüfbarer Preis gefunden' and not chat


def test_f053_markdown_exports_escape_html_in_product_metadata():
    attack = '<img src=x onerror=alert(1)>'
    turn = export.Turn(question='Product?', answer='Found', products=[Product(
        name=attack, url='https://shop.example/item', specs={'Size': attack})])
    result = export.to_markdown([turn])
    assert attack not in result and r'\<img' in result


def test_f054_default_exports_do_not_overwrite_an_earlier_export(tmp_path, monkeypatch):
    from datetime import datetime
    fixed = datetime(2026, 11, 6, 12)
    monkeypatch.setattr(export, 'datetime', SimpleNamespace(now=lambda: fixed))
    first = export.export([export.Turn('Same', 'First answer')], 'md', directory=tmp_path)
    second = export.export([export.Turn('Same', 'Second answer')], 'md', directory=tmp_path)
    assert first != second and 'First answer' in first.read_text()


@pytest.mark.parametrize('query,canonical', [('Ärzte', 'arzt'), ('Bücher', 'buch')])
def test_f055_german_irregular_plurals_find_the_correct_place_category(query, canonical):
    assert places._filter_for(query) == places.CATEGORIES[canonical]


def test_f056_swimming_pool_searches_include_the_standard_osm_pool_tag():
    assert 'swimming_pool' in places._filter_for('Schwimmbad')


def test_f057_home_assistant_connection_tests_reject_a_login_redirect(monkeypatch):
    monkeypatch.setattr(httpx, 'request', lambda *a, **kw: httpx.Response(
        302, headers={'location': '/login'}, text='Login'))
    client = homeassistant.HomeAssistant('http://house.local:8123', 'synthetic-token')
    with pytest.raises(homeassistant.HomeAssistantError):
        client.ping()


def test_f058_storage_writes_do_not_follow_a_redirect_to_another_server():
    requests = []
    def request(req):
        requests.append(req)
        if req.url.host == 'storage.local':
            return httpx.Response(307, headers={'location': 'https://outside.example/collect'})
        return httpx.Response(200, json={'id': 1, 'name': 'Private item'})
    with httpx.Client(transport=httpx.MockTransport(request), follow_redirects=True) as http:
        client = storage.Storage('http://storage.local:3000', access='write', client=http)
        with pytest.raises(storage.StorageError):
            client.add_room('Private item')
    assert [req.url.host for req in requests] == ['storage.local']


def test_f059_product_extraction_finds_a_price_after_an_offer_without_a_price():
    obj = {'@type': 'Product', 'name': 'Item', 'offers': [
        {'@type': 'Offer', 'availability': 'https://schema.org/SoldOut'},
        {'@type': 'Offer', 'price': '12', 'priceCurrency': 'EUR'}]}
    tree = HTMLParser('<script type="application/ld+json">' + json.dumps(obj) + '</script>')
    product = extract.product_from_jsonld(tree, 'https://shop.example/item')
    assert product is not None and product.price == '12' and product.currency == 'EUR'


def test_f060_a_suffix_of_a_city_does_not_disable_the_location_filter():
    assert queries.with_place('Cafés in York', 'New York') == 'Cafés in York New York'
    assert queries.mentions_place('Cafés in Bremen', 'Bremen Nord') is True
