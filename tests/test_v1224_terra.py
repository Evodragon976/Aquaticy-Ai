"""12.2.4 Terra: Passwortwechsel, Verbindungsgrenzen und Urteilscaches."""

from __future__ import annotations

import socket
import sqlite3
import ssl
import threading
from collections import OrderedDict
from dataclasses import replace
from socketserver import BaseRequestHandler
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from aquaticy import aiguard, linked, system, web
from aquaticy.auth import AuthStore, _password_hash
from aquaticy.config import Settings

OLD = "eine lange alte Passphrase"
NEW = "eine andere neue Passphrase"
MODEL = "mistral/terra-main-chat"
NEXT = "mistral/terra-next-chat"


@pytest.mark.parametrize("action", ["wipe_data", "remove_account"])
def test_a_password_change_invalidates_pending_account_erasure(tmp_path, monkeypatch, action):
    store = AuthStore(tmp_path, "PRO123456")
    account = store.register("terra@example.org", OLD, "normal",
                             terms_accepted=True, terms_version="test")
    profile = store.profile_dir(account.id)
    marker = profile / "keep.txt"
    marker.write_text("private data")
    store.vault(account).set("MISTRAL_API_KEY", "synthetic-private-key")
    assert store.verify_password(account, OLD)
    store.change_password(account, OLD, NEW)
    forgotten = []
    monkeypatch.setattr("aquaticy.upgrading.forget_account",
                        lambda *args: forgotten.append(args))

    with pytest.raises(ValueError, match=r"Passwort|anmelden"):
        getattr(store, action)(account)

    assert marker.read_text() == "private data"
    assert store.account(account.id) is not None
    assert store.vault(account).keys()["MISTRAL_API_KEY"] == "synthetic-private-key"
    assert not forgotten, "Auch Metadaten bleiben bei veralteter Freigabe erhalten"
    current = store.authenticate(account.email, NEW)
    assert current is not None
    getattr(store, action)(current)
    assert not marker.exists(), "Eine frische Passwortfreigabe funktioniert weiter"


@pytest.mark.parametrize("action", ["wipe_data", "remove_account"])
def test_a_forged_account_snapshot_cannot_erase_a_profile(tmp_path, action):
    store = AuthStore(tmp_path, "PRO123456")
    account = store.register("terra@example.org", OLD, "normal",
                             terms_accepted=True, terms_version="test")
    marker = store.profile_dir(account.id) / "keep.txt"
    marker.write_text("private data")
    with pytest.raises(ValueError, match="Passwort"):
        getattr(store, action)(replace(account, _credential=b""))
    assert marker.read_text() == "private data"


@pytest.mark.parametrize("action", ["wipe_data", "remove_account"])
def test_erasure_holds_the_database_write_lock_until_files_are_deleted(
        tmp_path, monkeypatch, action):
    import shutil

    store = AuthStore(tmp_path, "PRO123456")
    account = store.register("terra@example.org", OLD, "normal",
                             terms_accepted=True, terms_version="test")
    marker = store.profile_dir(account.id) / "keep.txt"
    marker.write_text("private data")
    remove = shutil.rmtree
    checked = []

    def check_and_remove(path):
        with (sqlite3.connect(store.db_path, timeout=0) as concurrent,
              pytest.raises(sqlite3.OperationalError, match="locked")):
            concurrent.execute("UPDATE users SET username='changed' WHERE id=?", (account.id,))
        checked.append(path)
        remove(path)

    monkeypatch.setattr("aquaticy.auth.shutil.rmtree", check_and_remove)
    getattr(store, action)(account)
    assert checked and not marker.exists()


@pytest.mark.parametrize("route", ["/api/account/wipe", "/api/account/delete"])
@pytest.mark.parametrize("change", ["password", "legacy-hash"])
def test_account_routes_handle_password_races_and_legacy_hash_migration(
        tmp_path, monkeypatch, route, change):
    store = AuthStore(tmp_path, "PRO123456")
    account = store.register("terra@example.org", OLD, "normal",
                             terms_accepted=True, terms_version="test")
    if change == "legacy-hash":
        salt = b"0123456789abcdef"
        with store._connect() as conn:
            conn.execute("UPDATE users SET password_hash=?,password_salt=? WHERE id=?",
                         (_password_hash(OLD, salt), salt, account.id))
        account = store.account(account.id)
    marker = store.profile_dir(account.id) / "keep.txt"
    marker.write_text("private data")
    handler = web.Handler.__new__(web.Handler)
    handler._account = lambda: account
    handler._cookie = lambda name: ""
    replies = []
    handler._json = lambda data, status=200: replies.append((status, data))
    handler._json_cookie = lambda data, *args: replies.append((200, data))
    monkeypatch.setattr(web, "AUTH", store)
    monkeypatch.setattr(web, "AIGUARD", None)
    monkeypatch.setattr(web, "start_user_scheduler", lambda *args: None)

    def stop_runtime(current):
        if change == "password":
            store.change_password(current, OLD, NEW)

    monkeypatch.setattr(web, "forget_account_runtime", stop_runtime)
    handler._account_action(route, {"password": OLD, "confirm": web.DELETE_WORD})
    assert replies[0][0] == (409 if change == "password" else 200)
    assert marker.exists() == (change == "password")


def test_slow_connections_are_bounded_before_http_headers_are_available(monkeypatch):
    monkeypatch.setattr(web.AquaticyServer, "max_connections", 2, raising=False)
    entered = threading.Barrier(3)
    release = threading.Event()

    class WaitingHandler(BaseRequestHandler):
        def handle(self):
            entered.wait(timeout=3)
            release.wait(timeout=5)

    server = web.AquaticyServer(("127.0.0.1", 0), WaitingHandler)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    clients = []
    try:
        clients = [socket.create_connection(server.server_address, timeout=2) for _ in range(2)]
        entered.wait(timeout=3)
        with socket.create_connection(server.server_address, timeout=2) as overloaded:
            with overloaded.makefile("rb") as response:
                data = response.read()
            assert data.startswith(b"HTTP/1.1 503 ")
            assert b"Retry-After: 1\r\n" in data
            assert b"Cache-Control: no-store\r\n" in data
            assert b"X-Content-Type-Options: nosniff\r\n" in data
            assert b"Content-Security-Policy: default-src 'none';" in data
    finally:
        release.set()
        for client in clients:
            client.close()
        server.shutdown()
        server.server_close()
        serving.join(timeout=3)


def test_a_handler_error_returns_the_connection_slot(monkeypatch):
    monkeypatch.setattr(web.AquaticyServer, "max_connections", 1)
    server = web.AquaticyServer(("127.0.0.1", 0), web.Handler)
    request = Mock()
    monkeypatch.setattr(server, "finish_request", Mock(side_effect=ValueError("synthetic error")))
    monkeypatch.setattr(server, "handle_error", Mock())
    try:
        assert server._connection_slots.acquire(blocking=False)
        server.process_request_thread(request, ("127.0.0.1", 1))
        assert server._connection_slots.acquire(blocking=False)
        request.close.assert_called_once()
        server.handle_error.assert_called_once()
    finally:
        server.server_close()


def test_successful_connections_reuse_the_server_capacity(monkeypatch):
    monkeypatch.setattr(web.AquaticyServer, "max_connections", 1)

    class ReplyHandler(BaseRequestHandler):
        def handle(self):
            self.request.sendall(b"ok")

    server = web.AquaticyServer(("127.0.0.1", 0), ReplyHandler)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    try:
        for _ in range(3):
            with socket.create_connection(server.server_address, timeout=2) as client:
                assert client.recv(512) == b"ok"
            assert server._connection_slots.acquire(timeout=3)
            server._connection_slots.release()
    finally:
        server.shutdown()
        server.server_close()
        serving.join(timeout=3)


def test_a_failed_thread_start_does_not_lose_a_connection_slot(monkeypatch):
    monkeypatch.setattr(web.AquaticyServer, "max_connections", 1)
    server = web.AquaticyServer(("127.0.0.1", 0), web.Handler)
    monkeypatch.setattr(web.ThreadingHTTPServer, "process_request",
                        Mock(side_effect=RuntimeError("cannot start thread")))
    try:
        with pytest.raises(RuntimeError, match="cannot start thread"):
            server.process_request(Mock(), ("127.0.0.1", 1))
        assert server._connection_slots.acquire(blocking=False)
    finally:
        server.server_close()


def test_a_failed_tls_handshake_returns_its_slot_and_never_sends_plaintext(monkeypatch):
    monkeypatch.setattr(web.AquaticyServer, "max_connections", 1)
    context = SimpleNamespace(wrap_socket=Mock(side_effect=ssl.SSLError("invalid handshake")))
    server = web._TLSServer(("127.0.0.1", 0), web.Handler, context)
    request = Mock()
    try:
        assert server._connection_slots.acquire(blocking=False)
        server.process_request_thread(request, ("127.0.0.1", 1))
        assert server._connection_slots.acquire(blocking=False)
        server.process_request(request, ("127.0.0.1", 1))
        request.sendall.assert_not_called()
        assert request.close.call_count == 2
    finally:
        server.server_close()


def test_real_tls_connections_keep_working_and_reuse_capacity(monkeypatch, tmp_path):
    from aquaticy import website

    monkeypatch.setattr(web.AquaticyServer, "max_connections", 1)
    domain = "terra.example.org"
    context, _ = website.tls_context(tmp_path, domain)
    certificate, _ = website.self_signed(tmp_path, domain)
    client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_context.load_verify_locations(cafile=str(certificate))

    class ReplyHandler(BaseRequestHandler):
        def handle(self):
            self.request.sendall(b"encrypted reply")

    server = web._TLSServer(("127.0.0.1", 0), ReplyHandler, context)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    try:
        for _ in range(2):
            with (socket.create_connection(server.server_address, timeout=2) as raw,
                  client_context.wrap_socket(raw, server_hostname=domain) as client):
                assert client.recv(512) == b"encrypted reply"
            assert server._connection_slots.acquire(timeout=3)
            server._connection_slots.release()
    finally:
        server.shutdown()
        server.server_close()
        serving.join(timeout=3)


@pytest.mark.parametrize("kind", ["request", "answer"])
def test_retirement_eviction_during_a_check_cannot_restore_an_old_cache_binding(
        monkeypatch, tmp_path, kind):
    monkeypatch.setattr(system, "_retired_seen", OrderedDict())
    monkeypatch.setattr(system, "MAX_RETIRED_MODELS", 1)
    monkeypatch.setattr("aquaticy.local_model.installed_models", lambda *a, **kw: [])
    settings = Settings(model=MODEL, subagent_model=MODEL, data_dir=tmp_path,
                        api_keys={"MISTRAL_API_KEY": "synthetic-terra-key"},
                        own_key_names=frozenset({"MISTRAL_API_KEY"}))
    linked.save(tmp_path, "mistral", {"models": [{"id": MODEL}, {"id": NEXT}]})
    called = []
    aiguard.forget_judgements()

    def one(prompt, current, model):
        called.append(model)
        current.fast_kwargs_for(model)
        if model == MODEL:
            raise RuntimeError("410 Gone")

        system.mark_retired("mistral/unrelated-model", current)
        return '{"missbrauch":false,"art":"ok","grund":""}'

    monkeypatch.setattr(aiguard, "_ask_one", one)
    text = "Ich erklaere allgemein, wie man Schadsoftware erkennt und sicher analysiert."

    def check():
        return (aiguard.classify(text, settings) if kind == "request" else
                aiguard.answer_problem(text, settings))

    check()
    assert called == [MODEL, NEXT]

    def access(model):
        if model == NEXT:
            raise ValueError("Modellfreigabe entzogen")

    settings.model_access = access
    check()
    assert called == [MODEL, NEXT, MODEL, NEXT], "Erneut pruefen, kein fremd gebundenes Urteil"


def test_retirements_do_not_flush_other_accounts_cached_judgements(monkeypatch, tmp_path):
    monkeypatch.setattr(system, "_retired_seen", OrderedDict())
    monkeypatch.setattr("aquaticy.local_model.installed_models", lambda *a, **kw: [])
    settings = Settings(model=MODEL, subagent_model=MODEL, data_dir=tmp_path,
                        api_keys={"MISTRAL_API_KEY": "synthetic-terra-key"},
                        own_key_names=frozenset({"MISTRAL_API_KEY"}))
    other = replace(settings, data_dir=tmp_path / "other")
    called = []
    aiguard.forget_judgements()

    def ask(prompt, current):
        called.append(prompt)
        return '{"missbrauch":false,"art":"ok","grund":""}'

    text = "Erklaere mir bitte ausfuehrlich die Funktionsweise einer Waermepumpe."
    assert aiguard.classify(text, settings, ask=ask) == (False, "ok")
    system.mark_retired(MODEL, other)
    assert aiguard.classify(text, settings, ask=ask) == (False, "ok")
    assert len(called) == 1, "Bestehende Urteile anderer Konten bleiben nutzbar"
