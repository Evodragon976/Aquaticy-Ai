"""Regressionen fuer Kontotrennung, API-Pfade und Exporte in 11.3.2 Luna."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
from markdown_it import MarkdownIt

from aquaticy import google, homeassistant
from aquaticy.export import Turn, to_markdown
from aquaticy.google import Google, GoogleError, NotConnected, Tokens, TokenStore


def _google(tmp_path: Path) -> tuple[Google, TokenStore, list[httpx.Request]]:
    store = TokenStore(tmp_path)
    store.save(Tokens(access_token="access-old", refresh_token="refresh-old",
                      expires_at=time.time() + 3600))
    requests: list[httpx.Request] = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"items": [], "payload": {}})

    return Google("id", "secret", store, httpx.Client(
        transport=httpx.MockTransport(respond))), store, requests


def test_disconnecting_google_invalidates_an_existing_client(tmp_path):
    api, store, requests = _google(tmp_path)
    assert api.connected()
    Google("id", "secret", TokenStore(tmp_path)).disconnect()
    assert not api.connected()
    with pytest.raises(NotConnected):
        api.events()
    assert not requests
    assert not store.path.exists()


def test_reconnecting_google_replaces_the_previous_accounts_token(tmp_path):
    api, store, requests = _google(tmp_path)
    assert api.connected()
    store.save(Tokens(access_token="access-new", refresh_token="refresh-new",
                      expires_at=time.time() + 3600))
    api.events()
    assert requests[0].headers["Authorization"] == "Bearer access-new"


@pytest.mark.parametrize("reconnect", [False, True])
def test_google_refresh_cannot_restore_a_disconnected_or_replaced_account(
    tmp_path, monkeypatch, reconnect,
):
    api, store, requests = _google(tmp_path)
    store.save(Tokens(access_token="expired", refresh_token="refresh-old"))

    def refresh(*args):

        other = TokenStore(tmp_path)
        other.clear()
        if reconnect:
            other.save(Tokens(access_token="replacement", refresh_token="replacement-refresh",
                              expires_at=time.time() + 3600))
        args[-1].access_token = "late-access"
        args[-1].expires_at = time.time() + 3600
        return args[-1]

    monkeypatch.setattr(google, "refresh_tokens", refresh)
    with pytest.raises(NotConnected):
        api.events()
    assert not requests
    assert store.load().refresh_token == ("replacement-refresh" if reconnect else "")
    assert store.path.exists() is reconnect


def test_parallel_google_refresh_uses_the_newer_token_instead_of_failing(tmp_path, monkeypatch):
    api, store, requests = _google(tmp_path)
    store.save(Tokens(access_token="expired", refresh_token="refresh-old"))

    def refresh(*args):
        TokenStore(tmp_path).save(Tokens(
            access_token="already-refreshed", refresh_token="refresh-old",
            expires_at=time.time() + 3600))
        args[-1].access_token = "late-access"
        return args[-1]

    monkeypatch.setattr(google, "refresh_tokens", refresh)
    api.events()
    assert requests[0].headers["Authorization"] == "Bearer already-refreshed"
    assert store.load().access_token == "already-refreshed"


def test_late_google_account_lookup_cannot_reconnect_a_removed_account(tmp_path, monkeypatch):
    api, store, _ = _google(tmp_path)

    def email():
        TokenStore(tmp_path).clear()
        return "old@example.org"

    monkeypatch.setattr(api, "_email", email)
    api.remember(Tokens(access_token="new", refresh_token="new-refresh",
                        expires_at=time.time() + 3600))
    assert not store.path.exists()
    assert not api.connected()


def test_google_token_replacement_is_atomic_and_keeps_old_data_on_failure(tmp_path, monkeypatch):
    _, store, _ = _google(tmp_path)
    previous = store.load()

    def fail(source, target):
        assert store.load() == previous
        if google.os.name != "nt":
            assert Path(source).stat().st_mode & 0o077 == 0
        raise OSError("cannot replace")

    monkeypatch.setattr(google.os, "replace", fail)
    with pytest.raises(OSError, match="cannot replace"):
        store.save(Tokens(access_token="new", refresh_token="new-refresh"))
    assert store.load() == previous
    assert not list(tmp_path.glob(".google-*"))


def test_google_atomic_save_keeps_the_explicit_private_file_protection(tmp_path, monkeypatch):
    from aquaticy import memory

    _, store, _ = _google(tmp_path)
    protected = []
    original = memory.secure_file

    def protect(path):


        assert Path(path).read_bytes() == b""
        protected.append(Path(path))
        original(path)

    monkeypatch.setattr(memory, "secure_file", protect)
    store.save(Tokens(access_token="new", refresh_token="new-refresh"))
    assert len(protected) == 1
    assert protected[0] != store.path
    assert store.load().refresh_token == "new-refresh"


@pytest.mark.parametrize("method", ["read_mail", "_headers", "update_event"])
@pytest.mark.parametrize("identifier", [
    "../../other/events/target", "%2e%2e%2fother", "id?sendUpdates=all", "id#fragment",
    "id\\other", "..", "id\n", "id/other", "x" * 1025,
])
def test_google_resource_ids_cannot_change_the_api_path(tmp_path, method, identifier):
    api, _, requests = _google(tmp_path)
    with pytest.raises(GoogleError):
        if method == "update_event":
            api.update_event(identifier, summary="Changed")
        else:
            getattr(api, method)(identifier)
    assert not requests


@pytest.mark.parametrize("identifier", ["abc123", "ev-1", "event_20261018T120000Z"])
def test_valid_google_resource_ids_keep_the_intended_endpoint(tmp_path, identifier):
    api, _, requests = _google(tmp_path)
    api.read_mail(identifier)
    api.update_event(identifier, summary="Changed")
    assert requests[0].url.path == f"/gmail/v1/users/me/messages/{identifier}"
    assert requests[1].url.path == f"/calendar/v3/calendars/primary/events/{identifier}"
    assert requests[1].method == "PATCH"


@pytest.mark.parametrize("expires", ["invalid", [], {}, float("inf"), float("nan")])
def test_malformed_google_token_metadata_means_disconnected(tmp_path, expires):
    store = TokenStore(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(store._cipher().encrypt(json.dumps({
        "access_token": "private", "refresh_token": "private-refresh", "expires_at": expires,
    })), encoding="utf-8")
    assert not Google("id", "secret", store).connected()


@pytest.mark.parametrize("target", [
    'https://source.example/x) <img src=x onerror="alert(1)">',
    "https://source.example/x) [hidden](https://other.example/)",
    "https://source.example/path(with_parentheses)?q=hello world#part",
])
def test_exported_source_urls_remain_one_markdown_link(target):
    exported = to_markdown([Turn(question="Test", answer="Answer",
                                 sources=[{"title": "Source", "url": target}])])
    rendered = MarkdownIt("commonmark").render(exported)
    from selectolax.parser import HTMLParser

    page = HTMLParser(rendered)
    assert len(page.css("a")) == 1
    assert not page.css("img,script")
    assert page.css_first("a").attributes["href"].startswith("https://source.example/")
    assert ")" not in page.css_first("a").attributes["href"]


def test_homeassistant_cache_does_not_keep_plaintext_credentials(monkeypatch):
    monkeypatch.setattr(homeassistant, "_states_cache", {})
    ha = homeassistant.HomeAssistant("http://ha.local:8123", "private-long-token")
    monkeypatch.setattr(ha, "_request", lambda *args: [{"entity_id": "light.room"}])
    ha.states()
    assert "private-long-token" not in repr(homeassistant._states_cache)


def test_homeassistant_cache_is_bounded_and_prunes_other_expired_entries(monkeypatch):
    monkeypatch.setattr(homeassistant, "_states_cache", {})
    moment = [100.0]
    monkeypatch.setattr(homeassistant.time, "monotonic", lambda: moment[0])
    monkeypatch.setattr(homeassistant.HomeAssistant, "_request", lambda *args: [])
    for i in range(140):
        homeassistant.HomeAssistant("http://ha.local:8123", f"token-{i}").states()
    assert len(homeassistant._states_cache) <= 128
    moment[0] += homeassistant.STATES_TTL + 1
    homeassistant.HomeAssistant("http://ha.local:8123", "new-token").states()
    assert len(homeassistant._states_cache) == 1


def test_homeassistant_cache_is_account_scoped_and_selectively_forgotten(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(homeassistant, "_states_cache", {})
    calls = []

    def read(self, *args):
        calls.append(self)
        return []

    monkeypatch.setattr(homeassistant.HomeAssistant, "_request", read)
    a, b = (homeassistant.from_settings(SimpleNamespace(
        data_dir=tmp_path / profile, ha_url="http://ha.local:8123", ha_token="same-token"))
        for profile in ("a", "b"))
    a.states()
    b.states()
    assert len(calls) == 2
    homeassistant.forget_states(tmp_path / "a")
    b.states()
    assert len(calls) == 2
    a.states()
    assert len(calls) == 3


def test_late_homeassistant_response_does_not_repopulate_a_forgotten_cache(monkeypatch):
    monkeypatch.setattr(homeassistant, "_states_cache", {})
    ha = homeassistant.HomeAssistant("http://ha.local:8123", "test-token")

    def read(*args):
        homeassistant.forget_states()
        return [{"entity_id": "light.room"}]

    monkeypatch.setattr(ha, "_request", read)
    assert ha.states()[0].entity_id == "light.room"
    assert not homeassistant._states_cache


@pytest.mark.parametrize("method", ["wipe_data", "remove_account"])
def test_deleting_account_data_also_removes_homeassistant_states(tmp_path, monkeypatch, method):
    from aquaticy.auth import AuthStore

    monkeypatch.setattr(homeassistant, "_states_cache", {})
    auth = AuthStore(tmp_path, "PRO123456")
    account = auth.register("a@example.org", "a very long passphrase", "normal",
                            terms_accepted=True, terms_version="test")
    profile = auth.profile_dir(account.id)
    ha = homeassistant.HomeAssistant("http://ha.local:8123", "private-token", profile=profile)
    monkeypatch.setattr(ha, "_request", lambda *args: [{"entity_id": "sensor.private"}])
    ha.states()
    assert homeassistant._states_cache
    getattr(auth, method)(account)
    assert not homeassistant._states_cache


def test_a_configured_ultra_code_with_umlauts_can_register(tmp_path, monkeypatch):
    from aquaticy.auth import AuthStore, valid_ultra_code

    code = "ÄBC123xyz!ABCD"
    assert valid_ultra_code(code)
    monkeypatch.setenv("AQUATICY_ULTRA_CODE", code)
    auth = AuthStore(tmp_path, "PRO123456")
    account = auth.register("ultra@example.org", "a very long passphrase", "ultra", code,
                            terms_accepted=True, terms_version="test")
    assert account.plan == "ultra"


@pytest.mark.parametrize("code", ["ÜBC123xyz!ABCD", "🔑wrong", "\ud800wrong"])
def test_invalid_unicode_ultra_codes_are_refused_without_a_server_error(tmp_path, code):
    from aquaticy.auth import AuthStore

    auth = AuthStore(tmp_path, "PRO123456")
    with pytest.raises(ValueError, match="Ultra-Code stimmt nicht"):
        auth.register("ultra@example.org", "a very long passphrase", "ultra", code,
                      terms_accepted=True, terms_version="test")
    assert not auth.accounts()


@pytest.mark.parametrize("code", ["KBC123XYZ", "İBC123XYZ"])
def test_invalid_unicode_pro_codes_are_refused_without_a_server_error(tmp_path, code):
    from aquaticy.auth import AuthStore

    auth = AuthStore(tmp_path, "PRO123456")
    with pytest.raises(ValueError, match="Pro-Code stimmt nicht"):
        auth.register("pro@example.org", "a very long passphrase", "pro", code,
                      terms_accepted=True, terms_version="test")
    assert not auth.accounts()


@pytest.mark.parametrize("code", ["１２３４５６", "١٢٣٤٥٦"])
def test_unicode_cluster_codes_count_as_failed_pairing_attempts(tmp_path, code):
    from aquaticy import cluster

    server = cluster.Cluster(tmp_path)
    server.state["enabled"] = True
    invitation = cluster.Invite(id="a" * 32, peer={}, status="accepted", code="123456",
                                created=time.time())
    server.invites_out[invitation.id] = invitation
    for attempt in range(cluster.CODE_TRIES):
        with pytest.raises(cluster.ClusterError, match="Code stimmt nicht"):
            server.confirm(invitation.id, code)
        assert invitation.tries == attempt + 1
    assert invitation.status == "failed"
    assert server.info is None


@pytest.mark.parametrize("attributes", [[], ["bad"], "bad", 7, None])
def test_malformed_homeassistant_attributes_do_not_break_all_states(monkeypatch, attributes):
    ha = homeassistant.HomeAssistant("http://ha.local:8123", "test-token")
    monkeypatch.setattr(ha, "_request", lambda *args: [
        {"entity_id": "light.room", "attributes": attributes},
        {"entity_id": "sensor.good", "attributes": {"friendly_name": "Good"}},
    ])
    result = ha.states(fresh=True)
    assert result[0].name == ""
    assert result[1].name == "Good"
