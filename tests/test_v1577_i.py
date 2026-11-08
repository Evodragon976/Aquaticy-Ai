"""15.7.7: Datenquellen, Review-Snapshots und genaue Aufgabenregeln."""

import base64
import socket

import httpx
import pytest

from aquaticy import addons, github_repo, homeassistant, lan, secure_tasks


def test_f075_lan_autodiscovery_never_probes_public_dns_answers(monkeypatch):
    probes = []
    monkeypatch.setattr(socket, 'gethostbyname', lambda host: '8.8.8.8')
    monkeypatch.setattr(lan, 'port_open', lambda address, *a, **kw: probes.append(address) or True)
    monkeypatch.setattr(lan, 'find_port', lambda *a: [])
    assert homeassistant.discover() == []
    assert not probes


def test_f076_currency_results_cannot_silently_use_a_different_base(monkeypatch):
    monkeypatch.setattr(addons, '_takt', lambda *a: None)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(
            200, json={'base': 'EUR', 'amount': 1, 'rates': {'CHF': 2}}))) as client:
        result = addons.currency(10, 'USD', 'CHF', client=client)
    assert 'error' in result


@pytest.mark.parametrize('url', ['https://name:secret@example.org/feed',
                                'https://example.org:wrong/feed', 'https://[bad/feed'])
def test_f077_invalid_feed_addresses_are_rejected_without_persisting(settings, url):
    addons._update(settings, 'feeds', installed=True, feeds=['https://example.org/previous'])
    with pytest.raises(addons.AddOnError):
        addons.set_feeds(settings, [url])
    assert addons.load_state(settings)['feeds']['feeds'] == ['https://example.org/previous']


def test_f078_foreign_feed_namespaces_do_not_replace_the_article_title():
    feed = b'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
    <entry><title>Article</title><media:title>Photo credit</media:title>
    <link href="https://example.org/article"/><media:link href="https://example.org/photo"/>
    </entry></feed>'''
    item = addons.parse_feed(feed, 'https://example.org/feed')[0]
    assert item['titel'] == 'Article'
    assert item['link'] == 'https://example.org/article'


def test_f079_a_review_rejects_a_pr_whose_base_changed_during_the_read():
    def get(path, **params):
        if path.endswith('/pulls/1'):
            return {'head': {'sha': 'a' * 40},
                    'base': {'sha': ('b' if params.get('_fresh') else 'c') * 40}}
        if path.endswith('/files'):
            return []
        return {'private': False}

    with pytest.raises(github_repo.GitHubError):
        github_repo.review(get, 'owner/repo', '', '', 1, 1)


@pytest.mark.parametrize('encoding', ['utf-16', 'utf-32'])
def test_f080_bom_encoded_source_files_can_be_reviewed(encoding):
    source = 'print("Grüße")\n'
    raw = source.encode(encoding)
    data = {'size': len(raw), 'encoding': 'base64', 'content': base64.b64encode(raw).decode()}
    result = github_repo.read_file(lambda *a, **kw: data, 'o/r', 'hello.py', 'main')
    assert result.get('text') == source


@pytest.mark.parametrize('text', ['Melde dich nicht, wenn ein neues Gerät ins Netz kommt.',
                                'Do not notify me when a new device joins the network.'])
def test_f081_negated_notifications_cannot_create_positive_tasks(text):
    with pytest.raises(ValueError):
        secure_tasks.parse(text)


def test_f082_an_existing_risky_service_is_not_a_new_port_event():
    task = secure_tasks.parse('Melde dich bei einem neuen Port.')
    assert not secure_tasks.matches(task, {'kind': 'risk_port', 'port': 21})
    assert secure_tasks.matches(task, {'kind': 'new_port', 'port': 21})
