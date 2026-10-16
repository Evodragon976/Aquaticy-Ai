"""11.2.3 Luna: widerrufene Rechte, Freigaben, Archivpfade und Website-Stopp."""

from __future__ import annotations

import gzip
import hashlib
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from types import SimpleNamespace

import httpx
import pytest

from aquaticy import coworker as cwm
from aquaticy import llamacpp, website
from tests.test_coworker import Kasten, _neu, _sitzung
from tests.test_llamacpp import _zip


@pytest.fixture
def store(settings):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return cwm.CoworkerStore(settings.db_path)


def test_running_coworker_respects_changed_rules(store):
    session = _sitzung(store, speicher="erlauben")
    assert session.gate(Kasten(), "save_memory", {"text": "Termin"}) is None
    store.set_rules(session.cw.id, {"speicher": "sperren"})
    assert session.gate(Kasten(), "save_memory", {"text": "Termin"})["gesperrt"]


@pytest.mark.parametrize("change", ["pause", "delete"])
@pytest.mark.parametrize("tool", ["web_search", "save_memory", "coworker_notes"])
def test_stopped_coworker_cannot_continue_tools(store, change, tool):
    session = _sitzung(store, speicher="erlauben")
    if change == "pause":
        store.set_enabled(session.cw.id, False)
    else:
        store.delete(session.cw.id)
    assert session.gate(Kasten(), tool, {})["gesperrt"]
    assert store.actions(session.cw.id) == []


def test_approval_expires_without_scheduler(store):
    cw = _neu(store)
    action, _ = store.add_action(cw.id, "mail_draft", {"subject": "x"}, "x", "mail")
    with store._connect() as conn:
        conn.execute("UPDATE coworker_actions SET created_at = ? WHERE id = ?",
                     (time.time() - 8 * 86400, action))
    assert store.decide(cw.id, action, True) is None
    assert store.action(action)["state"] == "abgelaufen"


def test_oversized_approval_is_rejected_without_corrupting_arguments(store):
    cw = _neu(store)
    with pytest.raises(cwm.CoworkerError):
        store.add_action(cw.id, "mail_draft", {"body": "ä" * 20_000}, "x", "mail")
    assert store.actions(cw.id) == []


@pytest.mark.parametrize("arguments", ['{"body": "abgeschnitten', '[]', 'null'])
def test_legacy_damaged_approval_never_executes_defaults(store, settings, monkeypatch, arguments):
    cw = _neu(store)
    action, _ = store.add_action(cw.id, "save_memory", {"text": "x"}, "x", "speicher")
    with store._connect() as conn:
        conn.execute("UPDATE coworker_actions SET arguments = ? WHERE id = ?",
                     (arguments, action))
    called = []
    monkeypatch.setattr("aquaticy.tools.Toolbox.call",
                        lambda *args: called.append(True) or {"ok": True})
    approved = store.decide(cw.id, action, True)
    assert cwm.run_action(store, approved, settings, ultra=False)[0] is False
    assert called == []


@pytest.mark.parametrize("change", ["ban", "downgrade", "pause", "delete"])
def test_scheduler_rechecks_access_between_workers(store, settings, monkeypatch, change):
    first, second = _neu(store), _neu(store)
    state = {"paused": False, "plan": "pro"}
    calls = []

    def run(cw, *args, **kwargs):
        calls.append(cw.id)
        if change == "ban":
            state["paused"] = True
        elif change == "downgrade":
            state["plan"] = "normal"
        elif change == "pause":
            store.set_enabled(second.id, False)
        else:
            store.delete(second.id)

    monkeypatch.setattr(cwm, "run_session", run)
    scheduler = cwm.Scheduler(lambda: settings, lambda: state["plan"],
                              paused=lambda: state["paused"])
    assert scheduler.tick() == 1
    assert calls == [first.id]


def test_deleted_coworker_cannot_recreate_private_records(store):
    cw = _neu(store)
    store.delete(cw.id)
    assert store.add_log(cw.id, "meldung", "Private Notizen") == 0
    with pytest.raises(cwm.CoworkerError):
        store.add_action(cw.id, "mail_draft", {"subject": "privat"}, "x", "mail")
    assert store.log(cw.id) == []
    assert store.actions(cw.id) == []


def test_zip_symlink_chain_cannot_create_files_outside_destination(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    archive = tmp_path / "bad.zip"
    archive.write_bytes(_zip({}, {
        "tree/a": "..", "tree/a/escape": "../outside", "escape/proof": "target",
    }))
    with pytest.raises(llamacpp.LlamaError):
        llamacpp.unpack_zip(archive, tmp_path / "extract")
    assert not (outside / "proof").is_symlink()


def test_zip_cannot_write_through_preexisting_external_link(tmp_path):
    outside, root = tmp_path / "outside", tmp_path / "extract"
    outside.mkdir()
    root.mkdir()
    (root / "alias").symlink_to(outside, target_is_directory=True)
    archive = tmp_path / "bad.zip"
    archive.write_bytes(_zip({"alias/proof": b"not outside"}))
    with pytest.raises(llamacpp.LlamaError):
        llamacpp.unpack_zip(archive, root)
    assert not (outside / "proof").exists()


def test_binary_download_refuses_http_compression_before_reading(tmp_path):
    payload = gzip.compress(b"a" * 1024)
    read = []

    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            read.append(True)
            yield payload

    def response(request):
        return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=Stream())

    asset = {"size": 1024, "digest": "sha256:" + hashlib.sha256(b"a" * 1024).hexdigest(),
             "browser_download_url": "https://github.com/ggml-org/llama.cpp/test.zip"}
    with httpx.Client(transport=httpx.MockTransport(response)) as client, \
            pytest.raises(llamacpp.LlamaError):
        llamacpp.download(asset, tmp_path / "download", http=client)
    assert not read, "Keine Dekompression vor der Groessenpruefung"


def test_website_stop_during_provision_does_not_restart_tunnel(tmp_path, monkeypatch):
    site = website.Website(website.SiteConfig(domain="chat.example.org", token="x" * 40),
                           tmp_path)
    started = []
    site.tunnel = SimpleNamespace(start=lambda: started.append(True), stop=lambda: None)

    def provision(*args):
        site.stop()
        return website.SiteState("chat.example.org", "zone", "account", "tunnel", "token")

    monkeypatch.setattr(website, "provision", provision)
    monkeypatch.setattr(website, "needs_certificate", lambda *args: False)
    monkeypatch.setattr(website, "load_certificate", lambda *args: True)
    site._ingress = (0, True)
    site._step()
    assert started == []


def test_rules_can_be_relaxed_again_and_fresh_approvals_preserve_unicode(store):
    session = _sitzung(store, speicher="sperren")
    store.set_rules(session.cw.id, {"speicher": "erlauben"})
    assert session.gate(Kasten(), "save_memory", {"text": "Termin"}) is None
    arguments = {"body": "Grüße 🌊" * 1000, "subject": "Montag"}
    action, _ = store.add_action(session.cw.id, "mail_draft", arguments, "x", "mail")
    assert store.decide(session.cw.id, action, True)["arguments"] == arguments
    assert store.decide(session.cw.id, action, True) is None


def test_zip_forward_links_are_checked_after_all_links_exist(tmp_path):
    archive = tmp_path / "bad.zip"
    archive.write_bytes(_zip({}, {"alias": "sub/z/../..", "sub/z": ".."}))
    with pytest.raises(llamacpp.LlamaError):
        llamacpp.unpack_zip(archive, tmp_path / "extract")


def test_zip_legitimate_link_chains_are_preserved(tmp_path):
    archive = tmp_path / "good.zip"
    archive.write_bytes(_zip({"real": b"library"},
                             {"alias": "lib/current", "lib/current": "../real"}))
    llamacpp.unpack_zip(archive, tmp_path / "extract")
    assert (tmp_path / "extract" / "alias").read_bytes() == b"library"


def test_deleted_worker_cannot_publish_a_late_model_reply(store, settings, monkeypatch):
    cw = _neu(store)
    posted = []

    class Agent:
        def __init__(self, settings, session):
            self.session = session

        def ask(self, *args, **kwargs):
            self.session.reports.append({"titel": "Privat", "text": "Notiz", "frage": False})
            store.delete(cw.id)
            return SimpleNamespace(answer="Privates Protokoll")

        def close(self):
            pass

    monkeypatch.setattr(cwm, "connections", lambda *args: "")
    monkeypatch.setattr(cwm, "post_to_chat", lambda *args: posted.append(True))
    assert cwm.run_session(cw, settings, "pro", store=store, agent_factory=Agent,
                           vm=False) == "gelöscht"
    assert posted == [] and store.log(cw.id) == []


def test_stopped_website_does_not_provision(tmp_path, monkeypatch):
    site = website.Website(website.SiteConfig(domain="chat.example.org", token="x" * 40),
                           tmp_path)
    calls = []
    monkeypatch.setattr(website, "provision", lambda *args: calls.append(True))
    site.stop()
    site._step()
    assert calls == []


def test_parallel_first_requests_can_initialize_the_same_database(tmp_path):
    from aquaticy.cache import Cache
    from aquaticy.jobs import JobStore
    from aquaticy.uistate import UIState

    for attempt in range(5):
        path = tmp_path / str(attempt) / "history.db"
        barrier = Barrier(8)

        def open_store(index, barrier=barrier, path=path):
            barrier.wait(timeout=10)
            factory = (Cache, cwm.CoworkerStore, JobStore, UIState)[index % 4]
            factory(path)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(open_store, range(8)))
        assert Cache(path).get("missing") is None


def test_cache_waits_for_another_store_to_finish_initializing(tmp_path, monkeypatch):
    from aquaticy import cache

    path = tmp_path / "history.db"
    connect = sqlite3.connect
    blocked = Event()

    class Connection(sqlite3.Connection):
        def execute(self, statement, *args, **kwargs):
            try:
                return super().execute(statement, *args, **kwargs)
            except sqlite3.OperationalError:
                if statement == "PRAGMA journal_mode=WAL":
                    blocked.set()
                raise

    writer = connect(path)
    try:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("CREATE TABLE first_store (value TEXT)")
        monkeypatch.setattr(cache.sqlite3, "connect",
                            lambda *args, **kwargs: connect(*args, factory=Connection, **kwargs))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(cache.Cache, path)
            try:
                assert blocked.wait(timeout=3), "Der Test muss die echte Sperre treffen"
            finally:
                writer.commit()
            db = future.result(timeout=3)
            assert db.get("missing") is None
            with db._connect() as conn:
                assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 10_000
    finally:
        writer.close()


@pytest.mark.parametrize("code", [
    sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_ERROR,
    sqlite3.SQLITE_BUSY_RECOVERY, sqlite3.SQLITE_LOCKED_SHAREDCACHE,
])
def test_wal_retry_is_bounded_and_only_for_lock_errors(tmp_path, monkeypatch, code):
    from aquaticy import cache

    calls = []
    closed = []

    class Connection:
        def execute(self, statement):
            calls.append(statement)
            error = sqlite3.OperationalError("gestellt")
            error.sqlite_errorcode = code
            raise error

        def close(self):
            closed.append(True)

    db = object.__new__(cache.Cache)
    db.db_path = tmp_path / "cache.db"
    clock = iter([0.0, 1.0, 11.0])
    monkeypatch.setattr(cache.sqlite3, "connect", lambda *args, **kwargs: Connection())
    monkeypatch.setattr(cache, "time", SimpleNamespace(monotonic=lambda: next(clock),
                                                      sleep=lambda seconds: None))
    with pytest.raises(sqlite3.OperationalError), db._connect():
        pytest.fail("Eine gesperrte oder defekte Datenbank wird nicht verwendet")
    assert len(calls) == (1 if code == sqlite3.SQLITE_ERROR else 2)
    assert closed == [True]
