"""12.1.1 Terra: zehn Konten, echtes HTTP/LiteLLM und ein paralleles Ollama."""

from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from typing import Any

import pytest

from aquaticy import guardrails, web
from aquaticy.auth import AuthStore
from aquaticy.cache import Cache
from aquaticy.config import Settings
from aquaticy.usage import UsageLog
from tests.anmeldung import AGENT, SPRACHE
from tests.ollama_nachbau import FAEHIGKEITEN, MODELLINFO
from tests.test_agent import _message, _stream

ECHTER_PRUEFER = guardrails._ask_model
MODELL = "qwen3:8b"


class ParallelOllama:
    """Haelt zehn echte Modellverbindungen offen, bis der Test sie freigibt."""

    def __init__(self) -> None:
        self.condition = threading.Condition()
        self.requests: list[dict[str, Any]] = []
        self.started: set[str] = set()
        self.denied: set[str] = set()
        self.release = {f"NUTZER_{i:02}": threading.Event() for i in range(10)}
        backend = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def _json(self, data: dict[str, Any]) -> None:
                body = json.dumps(data).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                self._json({"models": [{"name": MODELL, "size": 1}]})

            def do_POST(self) -> None:
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/api/show":
                    self._json({"capabilities": FAEHIGKEITEN[MODELL],
                                "model_info": MODELLINFO[MODELL]})
                    return
                assert self.path == "/api/chat", self.path
                with backend.condition:
                    backend.requests.append(data)
                response: dict[str, Any] = {
                    "model": MODELL, "created_at": "2026-10-19T12:00:00Z",
                    "done": True, "done_reason": "stop",
                    "prompt_eval_count": 120, "eval_count": 10,
                }
                if not data.get("stream"):
                    denied = any(marker in json.dumps(data["messages"])
                                 for marker in backend.denied)
                    response["message"] = {"role": "assistant", "content": json.dumps({
                        "zulaessig": not denied,
                        "regel": "persoenlichkeit" if denied else "",
                        "grund": "Private Daten" if denied else "",
                        "missbrauch": False, "missbrauch_art": "", "missbrauch_schwere": 0})}
                    self._json(response)
                    return
                messages = json.dumps(data["messages"], ensure_ascii=False)
                marker = re.findall(r"NUTZER_\d{2}", messages)[-1]
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                chunk = {**response, "done": False,
                         "message": {"role": "assistant", "content": f"Antwort für {marker}."}}
                self.wfile.write((json.dumps(chunk) + "\n").encode())
                self.wfile.flush()
                with backend.condition:
                    backend.started.add(marker)
                    backend.condition.notify_all()
                assert backend.release[marker].wait(40), "Test hat Ollama nicht freigegeben"
                response["message"] = {"role": "assistant", "content": ""}
                self.wfile.write((json.dumps(response) + "\n").encode())

        class Server(ThreadingHTTPServer):
            request_queue_size = 128

        self.server = Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        for event in self.release.values():
            event.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def ten_users(tmp_path, monkeypatch):

    import litellm  # noqa: F401

    backend = ParallelOllama()
    settings = Settings(model=f"ollama_chat/{MODELL}", api_base=backend.url,
                        data_dir=tmp_path / "operator", subagents_auto=False,
                        request_delay_seconds=0, enable_playwright=False, llm_retries=1)
    store = AuthStore(tmp_path / "accounts", "PROTEST234", "UltraTest12345!")
    monkeypatch.setattr(web, "get_settings", lambda: settings)
    monkeypatch.setattr(guardrails, "_ask_model", ECHTER_PRUEFER)
    monkeypatch.setattr(web, "AUTH", store)
    monkeypatch.setattr(web, "AIGUARD", None)
    monkeypatch.setattr(web, "CLUSTER", None)
    monkeypatch.setattr(web, "TOKEN", "")
    monkeypatch.setattr(web, "UPGRADE_DIR", None)
    monkeypatch.setattr(web, "SESSIONS", web.SessionRegistry())
    monkeypatch.setattr(web, "SESSION", web.SessionProxy())
    monkeypatch.setattr(web, "start_user_scheduler", lambda account: None)
    accounts, cookies = [], []
    for i in range(10):
        account = store.register(f"parallel{i}@example.org", "ein langes Testpasswort", "normal",
                                 username=f"Parallel{i}", terms_accepted=True, terms_version="1")
        accounts.append(account)
        token = store.create_session(account, f"{AGENT}\x1f{SPRACHE}", "127.0.0.1")
        cookies.append(f"{web.AUTH_COOKIE}={token}; {web.CONSENT_COOKIE}=yes")
    server = web.AquaticyServer(("127.0.0.1", 0), web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(index: int | None, method: str, path: str, body=None, **headers):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=45)
        try:
            fields = {"User-Agent": AGENT, "Accept-Language": SPRACHE,
                      "Content-Type": "application/json", **headers}
            if index is not None:
                fields["Cookie"] = cookies[index]
            connection.request(method, path, None if body is None else json.dumps(body), fields)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    try:
        yield SimpleNamespace(backend=backend, store=store, accounts=accounts, request=request)
    finally:
        backend.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        for session in web.SESSIONS._sessions.values():
            for chat in session.chat_sessions():
                if chat._agent is not None:
                    chat._agent.close()


@pytest.mark.parametrize("cancel_first", [False, True])
def test_ten_accounts_stream_at_once_with_isolated_history_and_usage(ten_users, cancel_first):
    site = ten_users
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(site.request, i, "POST", "/api/chat", {
            "message": f"Erkläre die Photosynthese. Kennung NUTZER_{i:02}.",
            "structured": False, "recheck": False, "online": False,
        }) for i in range(10)]
        try:
            with site.backend.condition:
                ready = site.backend.condition.wait_for(lambda: len(site.backend.started) == 10, 25)
                assert ready, (
                    site.backend.started, [(f.done(), f.exception() if f.done() else None)
                                           for f in futures])
            states = [json.loads(site.request(i, "GET", "/api/runstate")[1]) for i in range(10)]
            assert all(state["running"] for state in states), states
            assert len({state["id"] for state in states}) == 10
            assert len({state["chat"] for state in states}) == 10

            assert site.request(0, "GET", f"/api/run?id={states[1]['id']}")[0] == 404
            assert site.request(0, "GET", "/api/runstate",
                                **{"X-Aquaticy-Chat": states[1]["chat"]})[0] == 400
            assert site.request(None, "GET", "/api/runstate")[0] == 401
            assert site.request(0, "POST", "/api/stop", {}, Origin="https://evil.example")[0] == 403

            if cancel_first:
                assert json.loads(site.request(0, "POST", "/api/stop", {})[1])["ok"]
            assert all(not future.done() for future in futures[1:])
        finally:
            for event in site.backend.release.values():
                event.set()
        for i, future in enumerate(futures):
            status, body = future.result(timeout=15)
            events = [json.loads(line[6:]) for line in body.decode().splitlines()
                      if line.startswith("data: ")]
            assert status == 200 and events[-1]["type"] == "done", events
            assert not [e for e in events if e["type"] == "error"], events
            if i or not cancel_first:
                answer = "".join(e.get("text", "") for e in events if e["type"] == "chunk")
                assert answer == f"Antwort für NUTZER_{i:02}.", events
            markers = set(re.findall(r"NUTZER_\d{2}", body.decode()))
            assert markers <= {f"NUTZER_{i:02}"}
    for i, account in enumerate(site.accounts):
        session = web.SESSIONS.get(account)
        history = Cache(session.settings().db_path, 24).chat_history(states[i]["chat"])
        if i or not cancel_first:
            assert len(history) == 1 and f"NUTZER_{i:02}" in history[0].answer
            assert UsageLog(session.settings().db_path).total_tokens() == 260
        quota = site.store.quota(account)
        assert quota.status()["session"]["active"]
    streams = [r for r in site.backend.requests if r.get("stream")]
    assert len(streams) == 10
    assert len([r for r in site.backend.requests if not r.get("stream")]) == 10, (
        "auch jede Rechtsprüfung muss den echten Modellweg nehmen")
    assert all(len(set(re.findall(r"NUTZER_\d{2}", json.dumps(request["messages"])))) == 1
               for request in site.backend.requests)
    assert len({web.SESSIONS.get(a).settings().db_path for a in site.accounts}) == 10

    quota = site.store.quota(site.accounts[0])
    quota.record(quota.session_tokens, "Test")
    assert site.request(0, "POST", "/api/chat", {"message": "Noch eine Frage"})[0] == 429
    assert not site.store.quota(site.accounts[1]).status()["session"]["exhausted"]


def test_simultaneous_first_requests_build_only_one_complete_agent(settings, monkeypatch):
    from aquaticy import agent as agent_module

    session = web.ChatSession()
    session._settings = settings
    entered, duplicate, release = threading.Event(), threading.Event(), threading.Event()
    start = threading.Barrier(10)
    made = []

    def build(*args, **kwargs):
        made.append(SimpleNamespace())
        if entered.is_set():
            duplicate.set()
        entered.set()
        assert release.wait(5)
        return made[-1]

    def first_request():
        start.wait(timeout=5)
        result = session.agent()
        assert result.learning is not None, "kein halb aufgebauter Agent"
        return result

    monkeypatch.setattr(agent_module, "Agent", build)
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(first_request) for _ in range(10)]
        try:
            assert entered.wait(3)
            assert not duplicate.wait(0.2), "derselbe Chat wurde mehrfach aufgebaut"
        finally:
            release.set()
        results = [future.result(timeout=5) for future in futures]
    assert len(made) == 1 and all(result is results[0] for result in results)


def test_a_denied_request_never_reaches_the_chat_model_while_another_account_answers(ten_users):
    site = ten_users
    site.backend.denied.add("NUTZER_00")
    site.backend.release["NUTZER_01"].set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(site.request, i, "POST", "/api/chat", {
            "message": f"Eine Frage mit Kennung NUTZER_{i:02}", "online": False,
        }) for i in range(2)]
        status, denied = futures[0].result(timeout=15)
        assert status == 200 and b'"type": "guard"' in denied
        status, allowed = futures[1].result(timeout=15)
        assert status == 200 and b"Antwort" in allowed
    assert site.backend.started == {"NUTZER_01"}, "die Ablehnung gilt auch unter Last"


def test_full_run_book_rejects_new_work_and_keeps_all_active_runs():
    book = web.RunBook()
    runs = [book.start(str(i)) for i in range(book.HARD)]
    with pytest.raises(RuntimeError, match="Zu viele Anfragen laufen"):
        book.start("zu viel")
    assert all(book.get(run.id) is run for run in runs)
    assert book.latest() is runs[-1]
    runs[0].finish()
    assert book.start("wieder Platz") is book.latest()
    assert len(book._runs) == book.HARD


def test_simultaneous_admission_cannot_overfill_the_run_book():
    book = web.RunBook()
    for i in range(book.HARD - 1):
        book.start(str(i))
    start = threading.Barrier(10)

    def admit(i):
        start.wait(timeout=5)
        try:
            book.start(f"parallel {i}")
            return True
        except web.RunCapacityError:
            return False

    with ThreadPoolExecutor(max_workers=10) as pool:
        assert sum(pool.map(admit, range(10))) == 1
    assert len(book._runs) == book.HARD


def test_queue_limit_is_per_chat_and_rejects_before_spawning_work(ten_users):
    site = ten_users
    session = web.SESSIONS.get(site.accounts[0])
    for i in range(session.runs.HARD):
        session.runs.start(f"wartet {i}")
    status, body = site.request(0, "POST", "/api/chat", {"message": "Noch eine Frage"})
    assert status == 429 and json.loads(body)["code"] == "busy", body
    assert not site.backend.requests
    assert not site.store.quota(site.accounts[0]).status()["session"]["active"]

    site.backend.release["NUTZER_01"].set()
    status, body = site.request(1, "POST", "/api/chat", {
        "message": "Erkläre Photosynthese. Kennung NUTZER_01.", "online": False})
    assert status == 200 and b"NUTZER_01" in body, body


def test_oom_recovery_uses_the_selected_ollama_and_never_a_cloud_error(settings, monkeypatch):
    from aquaticy import local_model
    from aquaticy.agent import Agent

    settings.model = "ollama_chat/qwen3:8b"
    settings.api_base = "http://127.0.0.1:11999"
    freed, loading = [], []
    monkeypatch.setattr(local_model, "free_memory", lambda base: freed.append(base) or [])
    monkeypatch.setattr(local_model, "model_is_loaded",
                        lambda model, base="": loading.append(base) or True)
    monkeypatch.setattr(local_model, "can", lambda *args: True)
    monkeypatch.setattr(local_model, "context_limit", lambda *args: 32768)
    monkeypatch.setattr("time.sleep", lambda _: None)
    from tests.test_agent import ScriptedLLM

    class Runner:
        def __init__(self):
            self.calls = 0

        def __call__(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("model runner has unexpectedly stopped, resource limitations")
            return _message("Fertig")

    monkeypatch.setattr("litellm.completion", Runner())
    agent = Agent(settings)
    result = agent.ask("Erkläre Photosynthese", stream=False)
    assert result.answer == "Fertig" and freed == [settings.api_base]
    assert loading == [settings.api_base]
    agent.close()
    settings.model, settings.api_base = "mistral/mistral-large-latest", ""
    freed.clear()
    runner = ScriptedLLM(_message("Wieder da"))
    calls = [0]

    def cloud(**kwargs):
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("model runner has unexpectedly stopped, resource limitations")
        return runner(**kwargs)

    monkeypatch.setattr("litellm.completion", cloud)
    agent = Agent(settings)
    try:
        agent.ask("Erkläre Photosynthese", stream=False)
        assert not freed, "ein Cloudfehler darf kein lokales Modell entladen"
    finally:
        agent.close()


def test_memory_recovery_preserves_other_active_streams(settings, monkeypatch):
    from aquaticy import local_model
    from aquaticy.agent import Agent

    settings.model = "ollama_chat/qwen3:8b"
    settings.api_base = "http://127.0.0.1:11998"
    freed, during = [], []
    monkeypatch.setattr(local_model, "loaded_models", lambda base: [MODELL])
    monkeypatch.setattr(local_model, "unload_model",
                        lambda name, base: freed.append((name, base)) or True)
    monkeypatch.setattr(local_model, "can", lambda *args: True)
    monkeypatch.setattr(local_model, "context_limit", lambda *args: 32768)

    def stream(**kwargs):
        try:
            during.append(local_model.free_memory(settings.api_base))
            yield from _stream("Eine Antwort")
        finally:
            during.append("geschlossen")

    monkeypatch.setattr("litellm.completion", stream)
    agent = Agent(settings)
    try:
        assert agent._completion([{"role": "user", "content": "Frage"}], stream=True)["content"]
        assert during == [[], "geschlossen"] and not freed
        assert local_model.free_memory(settings.api_base) == [MODELL]
        assert freed == [(MODELL, settings.api_base)]
    finally:
        agent.close()


@pytest.mark.parametrize("failure", [False, True])
def test_nonstream_calls_protect_only_their_own_backend_and_release_on_error(monkeypatch, failure):
    from aquaticy import llmcall, local_model

    base, other = "http://127.0.0.1:11996", "http://127.0.0.1:11995"
    freed = []
    monkeypatch.setattr(local_model, "loaded_models", lambda url: [MODELL])
    monkeypatch.setattr(local_model, "unload_model",
                        lambda name, url: freed.append(url) or True)

    def completion(**kwargs):
        assert local_model.free_memory(base) == []
        assert local_model.free_memory(other) == [MODELL]
        if failure:
            raise RuntimeError("Verbindung verloren")
        return _message("Fertig")

    monkeypatch.setattr("litellm.completion", completion)
    if failure:
        with pytest.raises(RuntimeError, match="Verbindung verloren"):
            llmcall.completion(model=f"ollama_chat/{MODELL}", api_base=base)
    else:
        assert llmcall.completion(model=f"ollama_chat/{MODELL}", api_base=base)
    assert freed == [other]
    assert local_model.free_memory(base) == [MODELL]


def test_stop_closes_the_stream_and_releases_ollama_protection(settings, monkeypatch):
    from aquaticy import local_model
    from aquaticy.agent import Agent

    settings.model = f"ollama_chat/{MODELL}"
    settings.api_base = "http://127.0.0.1:11994"
    monkeypatch.setattr(local_model, "can", lambda *args: True)
    monkeypatch.setattr(local_model, "context_limit", lambda *args: 32768)
    monkeypatch.setattr(local_model, "loaded_models", lambda url: [MODELL])
    monkeypatch.setattr(local_model, "unload_model", lambda *args: True)
    closed = []
    agent = Agent(settings)

    def stream(**kwargs):
        try:
            yield from _stream("Anfang")
            agent.cancel()
            yield from _stream("wird verworfen")
            pytest.fail("ein gestoppter Stream darf nicht weitergelesen werden")
        finally:
            closed.append(True)

    monkeypatch.setattr("litellm.completion", stream)
    try:
        result = agent._completion([{"role": "user", "content": "Frage"}], stream=True)
        assert result["content"] == "Anfang " and closed == [True]
        assert local_model.free_memory(settings.api_base) == [MODELL]
    finally:
        agent.close()


def test_broken_stream_also_releases_ollama_protection(settings, monkeypatch):
    from aquaticy import local_model
    from aquaticy.agent import Agent

    settings.model = f"ollama_chat/{MODELL}"
    settings.api_base = "http://127.0.0.1:11993"
    monkeypatch.setattr(local_model, "can", lambda *args: True)
    monkeypatch.setattr(local_model, "context_limit", lambda *args: 32768)
    monkeypatch.setattr(local_model, "loaded_models", lambda url: [MODELL])
    monkeypatch.setattr(local_model, "unload_model", lambda *args: True)

    def stream(**kwargs):
        yield from _stream("Anfang")
        raise RuntimeError("Stream kaputt")

    monkeypatch.setattr("litellm.completion", stream)
    agent = Agent(settings)
    try:
        with pytest.raises(RuntimeError, match="Stream kaputt"):
            agent._completion([{"role": "user", "content": "Frage"}], stream=True)
        assert local_model.free_memory(settings.api_base) == [MODELL]
    finally:
        agent.close()


def test_the_real_litellm_wrapper_closes_its_underlying_http_connection():
    import inspect

    from aquaticy import llmcall

    backend = ParallelOllama()
    backend.release["NUTZER_00"].set()
    response = None
    try:
        response = llmcall.completion(model=f"ollama_chat/{MODELL}", api_base=backend.url,
                                     messages=[{"role": "user", "content": "NUTZER_00"}],
                                     stream=True)
        next(response)
        lines = response.completion_stream.streaming_response
        raw = inspect.getgeneratorlocals(lines)["self"]
        assert not raw.is_closed
        llmcall.close_stream(response)
        assert raw.is_closed, "vor Freigabe des Schutzes muss die Verbindung wirklich zu sein"
    finally:
        if response is not None:
            llmcall.close_stream(response)
        backend.close()
