"""11.2.2 Luna: Handy und Tablet -- und ein kleinerer Senden-Knopf.

Die Geometrie (Groesse, Trefferflaeche, Schatten, nichts steht ueber) misst
der Rundgang im echten Browser nach (tools/rundgang.py, Abschnitt 19). Hier
steht, was sich am Seitenquelltext pruefen laesst.
"""

from __future__ import annotations

import json
import re

from aquaticy import web


def _ui() -> str:
    return web.UI_FILE.read_text(encoding="utf-8")


def _css() -> str:
    html = _ui()
    return html[html.index("<style"):html.index("</style>")]


def test_hover_effects_only_with_a_mouse() -> None:
    # Am Handy blieb nach dem Antippen von "+" ein grauer Kasten stehen.
    css = _css()
    assert "@media (hover:hover){.iconbtn:hover{" in css
    nackt = [z for z in css.splitlines()
             if re.match(r"^[^\s@][^{]*:hover[^{]*\{", z) and "@media (hover:hover)" not in z]
    # Uebrig bleiben nur Regeln, die zusaetzlich :focus oder einen Zustand abdecken.
    assert all(":focus" in z or "aria-selected" in z for z in nackt), nackt


def test_hover_only_controls_are_visible_on_touch() -> None:
    css = _css()
    block = css[css.index("@media (hover:none) and (pointer:coarse){"):]
    block = block[:block.index("}\n}") + 3]
    assert ".answer-tools,.recent .more{opacity:1}" in block
    assert ".tasten-hinweis{display:none}" in block
    assert 'class="hint tasten-hinweis">Enter senden' in _ui()


def test_collapsed_sidebar_casts_no_shadow_and_takes_no_focus() -> None:
    css = _css()
    assert "body.collapsed aside{box-shadow:none}" in css
    assert re.search(r"body\.collapsed aside\{visibility:hidden;", css)


def test_page_height_follows_the_visible_area() -> None:
    html = _ui()
    assert "interactive-widget=resizes-content" in html
    assert "html.vv,html.vv body{height:var(--app-h)}" in html
    assert 'vv.addEventListener("resize", planen)' in html
    assert "if (vv.scale > 1.01) return;" in html  # Zoomen laesst das Layout in Ruhe


def test_send_button_is_smaller_but_easy_to_hit() -> None:
    css = _css()
    assert re.search(r"\.send\{[^}]*width:30px;height:30px", css)
    assert ".send{width:34px;height:34px" in css
    assert ".send{width:44px;height:44px}" not in css
    # Unsichtbarer Rand: 44px hoch, nach rechts nicht ueber die Knopfzeile hinaus.
    assert '.send::after{content:"";position:absolute;inset:-7px 0 -7px -6px}' in css
    assert ".send::after{inset:-5px 0 -5px -5px}" in css


def test_phone_start_page_puts_the_input_at_the_bottom() -> None:
    css = _css()
    start = css.index("11.2.2 Luna: Handy und Tablet")
    block = css[start:]
    assert "body.start .pane{justify-content:flex-start}" in block
    assert "body.start .chips{order:-1" in block
    assert "body.start footer > *{width:100%;max-width:100%}" in block
    assert ".composer textarea:focus-visible{outline:none}" in block


def test_model_name_stays_visible_on_common_phones() -> None:
    # Vorher wich der Name schon bei 360px einem Sinnbild -- der haeufigsten
    # Android-Breite. Jetzt erst unter 340px.
    css = _css()
    assert "@media (max-width:339px){\n  .modelpick #model-name{display:none}" in css
    assert "@media (max-width:360px){\n  .modelpick #model-name" not in css


# --- 11.2.2 Terra: lokale Modelle ohne Denk-Modus oder ohne Werkzeuge -----------------
# Gemeldet: Nach "Agenten arbeiten" kam nur "Da ist bei Aquaticy etwas
# schiefgelaufen" und keine Antwort. Ursache: Aquaticy schickte jedem
# Ollama-Modell die Denktiefe mit, LiteLLM machte daraus `think: true`, und
# Ollama lehnt das bei qwen2.5-coder, gemma & Co. ab.

import pytest  # noqa: E402

from aquaticy import local_model  # noqa: E402
from aquaticy.agent import Agent  # noqa: E402
from aquaticy.config import Settings  # noqa: E402
from tests.ollama_nachbau import Ollama  # noqa: E402


@pytest.fixture
def ollama():
    nachbau = Ollama()
    yield nachbau
    nachbau.stop()


@pytest.fixture(autouse=True)
def _frisch_gemerkt(monkeypatch):
    # Was ein Modell kann, merkt sich Aquaticy -- jeder Test faengt leer an.
    monkeypatch.setattr(local_model, "_CAPS", {})
    monkeypatch.setattr(local_model, "_FEHLT", {})


def _frage(url: str, modell: str, tmp_path, ereignisse: list | None = None, frage: str = ""):
    einstellungen = Settings(model=modell, api_base=url, data_dir=tmp_path / "d",
                             request_delay_seconds=0.0, enable_playwright=False,
                             subagents_auto=False, legal_guard=False, llm_retries=1)
    sammeln = ereignisse.append if ereignisse is not None else None
    agent = Agent(einstellungen,
                  on_event=(lambda n, p: sammeln((n, p))) if sammeln else None)
    agent.online = False
    return agent.ask(frage or "Schreib mir eine Website, die sich beim Neuladen ändert.",
                     stream=True)


def test_model_without_thinking_answers_instead_of_failing(ollama, tmp_path) -> None:
    ergebnis = _frage(ollama.url, "ollama_chat/qwen2.5-coder:14b", tmp_path)
    assert ergebnis.error == "" and ergebnis.answer == "Fertig."
    assert [(a["model"], a["think"], a["tools"]) for a in ollama.anfragen] == [
        ("qwen2.5-coder:14b", None, True)]


def test_thinking_model_still_gets_the_chosen_depth(ollama, tmp_path) -> None:
    ergebnis = _frage(ollama.url, "ollama_chat/qwen3:8b", tmp_path)
    assert ergebnis.answer == "Fertig."
    assert ollama.anfragen[0]["think"] is True


def test_model_without_tools_answers_without_tools(ollama, tmp_path) -> None:
    ergebnis = _frage(ollama.url, "ollama_chat/gemma3:4b", tmp_path)
    assert ergebnis.answer == "Fertig."
    assert [(a["model"], a["think"], a["tools"]) for a in ollama.anfragen] == [
        ("gemma3:4b", None, False)]


def test_old_ollama_teaches_aquaticy_by_its_error(tmp_path) -> None:
    # Ein aelteres Ollama nennt keine Faehigkeiten. Dann lernt Aquaticy aus der
    # Ablehnung, versucht es sofort ohne -- und schickt es danach nie wieder.
    nachbau = Ollama(alt=True)
    try:
        ereignisse: list = []
        ergebnis = _frage(nachbau.url, "ollama_chat/gemma3:4b", tmp_path, ereignisse)
        assert ergebnis.error == "" and ergebnis.answer == "Fertig."
        assert [a["tools"] for a in nachbau.anfragen] == [True, False]
        assert any(n == "note" and "keine Werkzeuge" in p["text"] for n, p in ereignisse)
        _frage(nachbau.url, "ollama_chat/gemma3:4b", tmp_path / "2")
        assert [a["tools"] for a in nachbau.anfragen] == [True, False, False]
    finally:
        nachbau.stop()


def test_rejected_thinking_is_learned_too(ollama, tmp_path, monkeypatch) -> None:
    # Sagt Ollama "thinking", lehnt es aber trotzdem ab: einmal lernen, dann ohne.
    monkeypatch.setitem(local_model._CAPS, (ollama.url, "qwen2.5-coder:14b"),
                        (1e18, frozenset({"completion", "tools", "thinking"})))
    ergebnis = _frage(ollama.url, "ollama_chat/qwen2.5-coder:14b", tmp_path)
    assert ergebnis.answer == "Fertig."
    assert [a["think"] for a in ollama.anfragen] == [True, None]


@pytest.mark.parametrize("meldung, fehlt", [
    ('litellm.BadRequestError: Ollama_chatException - {"error": "\\"qwen2.5-coder:14b\\" '
     'does not support thinking"}', "thinking"),
    ("registry.ollama.ai/library/gemma3:4b does not support tools", "tools"),
    ("Connection refused", ""), ("", ""),
])
def test_missing_capability_from_the_error(meldung: str, fehlt: str) -> None:
    assert local_model.missing_capability(meldung) == fehlt


def test_capabilities_are_remembered(ollama) -> None:
    for _ in range(3):
        assert local_model.ollama_capabilities("qwen3:8b", ollama.url) == frozenset(
            {"completion", "tools", "thinking"})
    assert len(local_model._CAPS) == 1
    assert local_model.can("mistral/mistral-large-latest", "tools") is None  # kein Ollama


def test_cloud_models_are_not_asked_for_capabilities(monkeypatch) -> None:
    gefragt: list[str] = []
    monkeypatch.setattr(local_model, "ollama_capabilities",
                        lambda *a, **k: gefragt.append(a[0]) or None)
    einstellungen = Settings(model="mistral/mistral-large-latest")
    assert einstellungen.thinks("anthropic/claude-sonnet-4-6") is False
    assert gefragt == []


from tests.test_web import FakeAgent, sse_events  # noqa: E402
from tests.test_web import client as client  # noqa: E402
from tests.test_web import session as session  # noqa: E402
from tests.test_web import web_settings as web_settings  # noqa: E402


def test_the_real_reason_reaches_the_operator_terminal(client, session, capsys) -> None:
    session._agent = FakeAgent([("error", {
        "message": 'BadRequestError: "qwen2.5-coder:14b" does not support thinking'})])
    _, body = client("POST", "/api/chat", {"message": "Hallo"})
    fehler = [e for e in sse_events(body) if e["type"] == "error"]
    # Im Chat weiter nur der allgemeine Satz ...
    assert fehler and fehler[0]["message"] == web.GENERIC_ERROR
    # ... im Terminal des Betreibers aber der Grund.
    assert "[Fehler] BadRequestError" in capsys.readouterr().out


def test_human_hints_are_not_echoed_to_the_terminal(client, session, capsys) -> None:
    session._agent = FakeAgent([("error", {"message": "Dein Limit ist erreicht."})])
    client("POST", "/api/chat", {"message": "Hallo"})
    assert "[Fehler]" not in capsys.readouterr().out


def test_no_research_agents_for_a_model_without_tools(ollama, tmp_path) -> None:
    einstellungen = Settings(model="ollama_chat/gemma3:4b", api_base=ollama.url,
                             data_dir=tmp_path / "d", subagents_auto=True)
    assert Agent(einstellungen)._auto_subagents_wanted() is False
    einstellungen = Settings(model="ollama_chat/qwen2.5-coder:14b", api_base=ollama.url,
                             data_dir=tmp_path / "e", subagents_auto=True)
    assert Agent(einstellungen)._auto_subagents_wanted() is True


# --- 11.2.2 Terra: Werkzeugaufrufe, die ein Modell als Text schreibt ------------------

from aquaticy.agent import tool_calls_from_text  # noqa: E402
from tests.test_agent import ScriptedLLM, _message, _tool_call  # noqa: E402
from tests.test_agent import _stub_search as _stub_search  # noqa: E402
from tests.test_agent import toolbox as toolbox  # noqa: E402
from tests.test_subagents import _toolbox  # noqa: E402

NAMEN = ("web_search", "fetch_page", "calculate")


@pytest.mark.parametrize("text, erwartet", [
    ('{"name": "web_search", "arguments": {"query": "dynamische Website"}}',
     [("web_search", {"query": "dynamische Website"})]),
    ('```json\n{"name": "web_search", "arguments": {"query": "x"}}\n```',
     [("web_search", {"query": "x"})]),
    ('<tool_call>\n{"name": "fetch_page", "arguments": {"url": "https://a.de"}}\n</tool_call>',
     [("fetch_page", {"url": "https://a.de"})]),
    ('{"name": "web_search", "arguments": "{\\"query\\": \\"x\\"}"}',
     [("web_search", {"query": "x"})]),
    ('[{"name": "web_search", "parameters": {"query": "a"}},'
     ' {"name": "calculate", "arguments": {"expression": "1+1"}}]',
     [("web_search", {"query": "a"}), ("calculate", {"expression": "1+1"})]),
    ('{"type": "function", "function": {"name": "web_search", "arguments": {"query": "b"}}}',
     [("web_search", {"query": "b"})]),
])
def test_tool_calls_written_as_text_are_recognised(text: str, erwartet: list) -> None:
    aufrufe = tool_calls_from_text(text, NAMEN)
    assert [(a["function"]["name"], json.loads(a["function"]["arguments"]))
            for a in aufrufe] == erwartet


@pytest.mark.parametrize("text", [
    "Hier ist deine Website: <html>...</html>",
    'Das JSON sieht so aus: {"name": "web_search", "arguments": {"query": "x"}}',
    '```json\n{"name": "Max", "alter": 3}\n```',
    '{"name": "rm_rf", "arguments": {}}',
    '{"name": "web_search", "arguments": [1, 2]}',
    '{"name": "web_search", "arguments": {"query": "x"}} und dann noch Text',
    "",
    '{"name": "web_search", "arguments": {"query": "' + "x" * 9000 + '"}}',
])
def test_ordinary_answers_stay_answers(text: str) -> None:
    assert tool_calls_from_text(text, NAMEN) == []


def test_main_agent_runs_a_tool_call_written_as_text(monkeypatch, settings, toolbox) -> None:
    llm = ScriptedLLM(
        _message(content='```json\n{"name": "web_search", "arguments": {"query": "Bremen"}}\n```'),
        _message(content="In Bremen gibt es das Café Sonntag."),
    )
    monkeypatch.setattr("litellm.completion", llm)
    ereignisse: list = []
    agent = Agent(settings, cache=None, toolbox=toolbox,
                  on_event=lambda n, p: ereignisse.append((n, p)))
    ergebnis = agent.ask("Cafés in Bremen?", stream=False)
    assert ergebnis.answer == "In Bremen gibt es das Café Sonntag."
    assert ergebnis.searches == ["Bremen"]
    # Das JSON war nie eine Antwort.
    assert not any(n == "answer_chunk" and "web_search" in p.get("text", "")
                   for n, p in ereignisse)


def test_research_agent_searches_when_the_call_comes_as_text(
        monkeypatch, settings, fixture_html) -> None:
    from aquaticy.subagents import _run_one

    antworten = iter([
        _message(content='<tool_call>{"name": "web_search", "arguments": '
                         '{"query": "cafés"}}</tool_call>'),
        _message(content="Ein Café gefunden. Quelle: cafe-sonntag.de"),
    ])
    monkeypatch.setattr("litellm.completion", lambda **kw: next(antworten))
    ergebnis = _run_one("Finde Cafés", settings, None, None,
                        toolbox=_toolbox(settings, fixture_html))
    assert ergebnis.searches == ["cafés"]
    assert "Café gefunden" in ergebnis.summary


def test_real_tool_calls_are_left_alone(monkeypatch, settings, toolbox) -> None:
    llm = ScriptedLLM(
        _message(tool_calls=[_tool_call("web_search", {"query": "echt"})]),
        _message(content="Fertig."),
    )
    monkeypatch.setattr("litellm.completion", llm)
    assert Agent(settings, cache=None, toolbox=toolbox).ask(
        "Frage", stream=False).searches == ["echt"]


def test_streamed_text_call_is_taken_back_from_the_answer(monkeypatch, settings, toolbox) -> None:
    from tests.test_agent import _stream

    llm = ScriptedLLM(
        _stream(content='{"name": "web_search", "arguments": {"query": "Bremen"}}'),
        _stream(content="Das Café Sonntag."),
    )
    monkeypatch.setattr("litellm.completion", llm)
    ereignisse: list = []
    agent = Agent(settings, cache=None, toolbox=toolbox,
                  on_event=lambda n, p: ereignisse.append((n, p)))
    ergebnis = agent.ask("Cafés in Bremen?", stream=True)
    assert ergebnis.searches == ["Bremen"]
    assert ergebnis.answer.strip() == "Das Café Sonntag."  # _stream haengt Leerzeichen an
    # Die Oberflaeche nimmt den gestreamten JSON-Text als Zwischennachricht zurueck.
    assert any(n == "interim" and "web_search" in p["text"] for n, p in ereignisse)


def test_too_big_context_is_halved_instead_of_failing_three_times(monkeypatch, tmp_path) -> None:
    # Ollama: "model requires more system memory (12.5 GiB) than is available".
    monkeypatch.setattr("aquaticy.agent.time.sleep", lambda s: None)
    nachbau = Ollama(max_ctx=8192)
    try:
        einstellungen = Settings(model="ollama_chat/qwen2.5-coder:14b", api_base=nachbau.url,
                                 data_dir=tmp_path / "d", subagents_auto=False,
                                 legal_guard=False, context_tokens=16384, llm_retries=3)
        agent = Agent(einstellungen)
        agent.online = False
        ergebnis = agent.ask("Hallo, schreib mir eine Website.", stream=True)
        assert ergebnis.error == "" and ergebnis.answer == "Fertig."
        assert [a["num_ctx"] for a in nachbau.anfragen] == [16384, 8192]
        # Das kleinere Fenster gilt weiter -- der naechste Aufruf scheitert nicht erst.
        agent.ask("Und noch eine Frage.", stream=True)
        assert nachbau.anfragen[-1]["num_ctx"] == 8192
    finally:
        nachbau.stop()


def test_ollama_memory_message_counts_as_memory_problem() -> None:
    assert local_model.resource_problem(
        "APIConnectionError: model requires more system memory (12.5 GiB) than is "
        "available (8.0 GiB)")


@pytest.mark.parametrize("modus", ["normal", "pro", "code"])
def test_chat_with_a_local_coder_model_answers_end_to_end(client, session, ollama,
                                                           tmp_path, modus) -> None:
    # Der gemeldete Fall, ganz durch: Browser -> Server -> Agent -> LiteLLM -> Ollama.
    from tests.ollama_nachbau import FAEHIGKEITEN

    session._settings = Settings(
        model="ollama_chat/qwen2.5-coder:14b", api_base=ollama.url,
        data_dir=tmp_path / "w", env_path=tmp_path / ".env",
        subagents_auto=False, legal_guard=False)
    session._agent = None
    _, body = client("POST", "/api/chat", {
        "message": "schreibe mir den code für eine website die sich beim neu laden ändert",
        "online": False, "mode": modus})
    ereignisse = sse_events(body)
    assert [e for e in ereignisse if e["type"] == "error"] == []
    text = "".join(str(e.get("text", "")) for e in ereignisse if e["type"] == "chunk")
    assert "Fertig." in text
    # `think: true` nur an Modelle, die denken koennen. Im Pro- und Code-Modus nimmt
    # Aquaticy das staerkste Modell -- hier qwen3, das darf denken.
    assert ollama.anfragen
    for anfrage in ollama.anfragen:
        if anfrage["think"] is True:
            assert "thinking" in FAEHIGKEITEN[anfrage["model"]], anfrage


# --- 11.2.2 Sol: die virtual machine im Code-Modus ------------------------------------
# Gemeldet: Im Code-Modus mit eingeschalteter virtual machine nutzte Aquaticy sie
# nie und sagte auf Nachfrage, es habe keine.

from aquaticy import agent as agent_mod  # noqa: E402
from aquaticy import sandbox as sandbox_mod  # noqa: E402

#: Die echte Suche -- tests/conftest.py stellt sie fuer alle anderen Tests auf "unbekannt".
_RUNTIME_KNOWN_ECHT = sandbox_mod.runtime_known
_DOCKER = sandbox_mod.Runtime("docker", "docker", "Docker (gehaertet)")


@pytest.fixture
def vm_da(monkeypatch):
    """Eine Abschottung ist da; vm_write/vm_run laufen in einer Attrappe."""
    monkeypatch.setattr(sandbox_mod, "runtime_known", lambda: (True, _DOCKER))
    monkeypatch.setattr(agent_mod.Agent, "_warm_workshop", lambda self: None)
    monkeypatch.setattr(agent_mod.Agent, "_touch_workshop", lambda self: None)
    befehle: list[str] = []

    def einrichten(toolbox):
        def vm_run(command: str, timeout: int = 0):
            befehle.append(command)
            toolbox.stats.vm_calls += 1
            return {"exit_code": 0, "stdout": "Hallo\n", "stderr": ""}

        def vm_write(path: str, text: str):
            toolbox.stats.vm_calls += 1
            return {"ok": True, "path": path}

        toolbox.vm_run = vm_run
        toolbox.vm_write = vm_write
        return befehle

    return einrichten


def _code_agent(settings, toolbox, ereignisse):
    return Agent(settings, cache=None, toolbox=toolbox,
                 on_event=lambda n, p: ereignisse.append((n, p)))


def test_code_that_never_ran_goes_back_once(monkeypatch, settings, toolbox, vm_da) -> None:
    befehle = vm_da(toolbox)
    llm = ScriptedLLM(
        _message(content="```python\nprint('Hallo')\n```"),
        _message(tool_calls=[_tool_call("vm_run", {"command": "python3 -c \"print('Hallo')\""})]),
        _message(content="Läuft: gibt Hallo aus.\n```python\nprint('Hallo')\n```"),
    )
    monkeypatch.setattr("litellm.completion", llm)
    ereignisse: list = []
    ergebnis = _code_agent(settings, toolbox, ereignisse).ask(
        "Schreib Hallo Welt", stream=False, mode="code", sandbox=True)
    assert befehle == ["python3 -c \"print('Hallo')\""]
    assert ergebnis.answer.startswith("Läuft")
    assert agent_mod.VM_NUDGE_PROMPT in [m["content"] for m in llm.calls[1]["messages"]]
    assert ("answer_reset", {"reason": "virtual machine"}) in ereignisse


def test_the_nudge_comes_only_once_and_not_after_a_run(monkeypatch, settings, toolbox,
                                                       vm_da) -> None:
    vm_da(toolbox)
    llm = ScriptedLLM(
        _message(content="```python\nx = 1\n```"),
        _message(content="```python\nx = 1\n```"),  # bleibt dabei -- seine Entscheidung
    )
    monkeypatch.setattr("litellm.completion", llm)
    ergebnis = _code_agent(settings, toolbox, []).ask(
        "Code bitte", stream=False, mode="code", sandbox=True)
    assert ergebnis.answer == "```python\nx = 1\n```" and len(llm.calls) == 2
    # Ohne Codeblock (eine Erklaerung) gibt es keinen Anstoss.
    llm = ScriptedLLM(_message(content="Ein Decorator umhüllt eine Funktion."))
    monkeypatch.setattr("litellm.completion", llm)
    _code_agent(settings, toolbox, []).ask("Was ist ein Decorator?", stream=False,
                                           mode="code", sandbox=True)
    assert len(llm.calls) == 1


def test_every_question_reminds_of_the_vm(monkeypatch, settings, toolbox, vm_da) -> None:
    vm_da(toolbox)
    llm = ScriptedLLM(_message(content="Erklärung ohne Code."))
    monkeypatch.setattr("litellm.completion", llm)
    _code_agent(settings, toolbox, []).ask("Frage", stream=False, mode="code", sandbox=True)
    frage = [m for m in llm.calls[0]["messages"] if m["role"] == "user"][-1]["content"]
    assert agent_mod.VM_TURN_HINT in frage
    namen = [t["function"]["name"] for t in llm.calls[0]["tools"]]
    assert "vm_run" in namen and "vm_write" in namen


def test_vm_on_without_docker_says_so(monkeypatch, settings, toolbox) -> None:
    monkeypatch.setattr(sandbox_mod, "runtime_known", lambda: (True, None))
    llm = ScriptedLLM(_message(content="```python\nprint(1)\n```"))
    monkeypatch.setattr("litellm.completion", llm)
    ereignisse: list = []
    _code_agent(settings, toolbox, ereignisse).ask("Code", stream=False, mode="code",
                                                   sandbox=True)
    aufruf = llm.calls[0]
    assert not any(t["function"]["name"].startswith("vm_") for t in aufruf.get("tools") or [])
    system = aufruf["messages"][0]["content"]
    assert "Podman oder Docker fehlt" in system
    assert any(n == "note" and "Podman oder Docker" in p["text"] for n, p in ereignisse)
    assert len(llm.calls) == 1  # kein Anstoss zu etwas, das nicht geht


def test_runtime_lookup_is_cached(monkeypatch) -> None:
    aufrufe: list[int] = []
    monkeypatch.setattr(sandbox_mod, "find_runtime", lambda: aufrufe.append(1) or None)
    for _ in range(5):
        assert sandbox_mod.runtime_cached() is None
    assert aufrufe == [1]


def test_looking_for_docker_never_holds_up_a_question(monkeypatch) -> None:
    """Fund aus dem Volllauf: die erste Fassung fragte `docker info` mitten in ask()."""
    import threading
    import time

    gesucht = threading.Event()
    aufrufe: list[int] = []

    def langsam():
        aufrufe.append(1)
        time.sleep(0.5)
        gesucht.set()
        return _DOCKER

    monkeypatch.setattr(sandbox_mod, "find_runtime", langsam)
    vorher = time.monotonic()
    assert _RUNTIME_KNOWN_ECHT() == (False, None)      # noch nie gesucht
    assert _RUNTIME_KNOWN_ECHT() == (False, None)      # sucht schon -- kein zweiter Faden
    assert time.monotonic() - vorher < 0.2
    assert gesucht.wait(3)
    for _ in range(50):
        if _RUNTIME_KNOWN_ECHT() == (True, _DOCKER):
            break
        time.sleep(0.02)
    assert _RUNTIME_KNOWN_ECHT() == (True, _DOCKER) and aufrufe == [1]
    # Abgelaufen: der alte Stand gilt sofort weiter, neu gesucht wird nebenher.
    sandbox_mod._LAUFZEIT["bis"] = 0.0
    gesucht.clear()
    vorher = time.monotonic()
    assert _RUNTIME_KNOWN_ECHT() == (True, _DOCKER)
    assert time.monotonic() - vorher < 0.2
    assert gesucht.wait(3)


def test_the_agent_answers_without_waiting_for_docker(monkeypatch, settings, toolbox) -> None:
    import threading
    import time

    frei = threading.Event()
    monkeypatch.setattr(sandbox_mod, "runtime_known", _RUNTIME_KNOWN_ECHT)
    monkeypatch.setattr(sandbox_mod, "find_runtime", lambda: frei.wait(5) and None)
    monkeypatch.setattr(agent_mod.Agent, "_warm_workshop", lambda self: None)
    llm = ScriptedLLM(_message(content="Erklärung ohne Code."))
    monkeypatch.setattr("litellm.completion", llm)
    vorher = time.monotonic()
    _code_agent(settings, toolbox, []).ask("Frage", stream=False, mode="code", sandbox=True)
    dauer = time.monotonic() - vorher
    frei.set()
    assert dauer < 2, "die Frage wartet nicht auf docker info"
    # Noch unbekannt: angeboten wie vor 11.2.2 Sol.
    assert "vm_run" in [t["function"]["name"] for t in llm.calls[0]["tools"]]


def test_vm_status_endpoint(client, session, monkeypatch) -> None:
    monkeypatch.setattr(sandbox_mod, "runtime_cached", lambda: None)
    status, body = client("GET", "/api/vm")
    daten = json.loads(body)
    assert status == 200
    assert daten == {"internet": False, "lan": False, "ultra": bool(session.ultra),
                     "runtime": False}


def test_vm_internet_needs_ultra_at_the_server(client, session, monkeypatch) -> None:
    # Der neue Schalter speichert ueber /api/config -- dort prueft der Server Ultra.
    monkeypatch.setattr(type(session), "ultra", property(lambda self: False))
    status, body = client("POST", "/api/config", {"AQUATICY_VM_INTERNET": "true"})
    assert status == 400
    assert "nur mit einem Ultra-Konto" in json.loads(body).get("error", "")


def test_vm_switch_text_no_longer_promises_internet() -> None:
    html = _ui()
    start = html.index('id="werkstatt"')
    abschnitt = html[start:html.index("</label>", start)]
    assert "Internet" not in abschnitt
    assert 'id="werkstatt-netz"' in html and 'id="werkstatt-status"' in html
    # Jeder sichtbare Satz hat seine englische Fassung.
    for satz in ("Internet für die virtual machine",
                 "Auf diesem Rechner fehlt Podman oder Docker – die virtual machine kann "
                 "nicht starten."):
        assert f'"{satz}":' in html, satz


# --- 11.2.2 Sol: Begruessung auch ohne Namen ---------------------------------

def _gruss_en() -> dict[str, list[str]]:
    html = _ui()
    start = html.index("const GRUSS_EN = {")
    block = html[start:html.index("\n};", start)]
    return {modus: re.findall(r'"([^"]+)"', teil)
            for modus, teil in re.findall(r"\n  (\w+): \[(.*?)\]", block, re.S)}


def test_greetings_come_with_and_without_name() -> None:
    from aquaticy.starttexte import GREETINGS

    englisch = _gruss_en()
    for modus in ("normal", "pro", "code"):
        saetze = GREETINGS[modus]
        assert len(saetze) == len(set(saetze))
        # Die Saetze mit Namen bleiben, dazu kommen eigene ohne.
        assert sum("{name}" in s for s in saetze) >= 50, modus
        assert sum("{name}" not in s for s in saetze) >= 15, modus
        assert {"Womit fangen wir an?", "Womit fangen wir an, {name}?"} <= set(saetze)
        # Englisch hat jetzt auch je Modus ganze Saetze, mit und ohne Namen.
        en = englisch[modus]
        assert len(en) >= 20 and len(en) == len(set(en)), modus
        assert any("{name}" in s for s in en) and any("{name}" not in s for s in en)
        assert "Where do we start?" in en and "Where do we start, {name}?" in en


def test_about_every_second_greeting_names_the_user() -> None:
    import subprocess

    from aquaticy.starttexte import GREETINGS

    html = _ui()

    def stueck(anfang: str) -> str:
        i = html.index(anfang)
        return html[i:html.index("\n}", i) + 2]

    skript = "\n".join((
        "function zufaellig(l){ return l[Math.floor(Math.random() * l.length)]; }",
        stueck("function grussSatz("), stueck("function grussZiehen("),
        f"const DE = {json.dumps(GREETINGS, ensure_ascii=False)};",
        f"const EN = {json.dumps(_gruss_en())};",
        """const kaputt = [];
for (const [quelle, gruss] of [[DE, "Guten Morgen"], [EN, "Good morning"]])
  for (const liste of Object.values(quelle))
    for (const satz of liste)
      for (const name of ["Jonas", ""]){
        const t = grussSatz(satz, gruss, name);
        if (/[{}]|,\\s*[.?!:]|\\s[.,?!:]|^[,.]|  /.test(t)) kaputt.push(t);
      }
let mit = 0;
for (let i = 0; i < 4000; i++)
  if (grussZiehen(DE.normal, "Hallo", "Jonas").includes("Jonas")) mit++;
console.log(JSON.stringify({kaputt, mit,
  wenig: grussZiehen(DE.normal, "Hallo", "Jonas", 0.1),
  viel: grussZiehen(DE.normal, "Hallo", "Jonas", 0.9),
  gast: grussZiehen(DE.normal, "Hallo", "", 0.1),
  ohne: grussSatz("Womit fangen wir an, {name}?", "Hallo", ""),
  dollar: grussSatz("Womit fangen wir an, {name}?", "Hallo", "Jo$&nas$1")}));""",
    ))
    try:
        aus = subprocess.run(["node", "-e", skript], capture_output=True, text=True,
                             timeout=30)
    except FileNotFoundError:
        pytest.skip("node fehlt")
    ergebnis = json.loads(aus.stdout)
    assert ergebnis["kaputt"] == []
    assert 1600 < ergebnis["mit"] < 2400            # rund die Haelfte
    assert "Jonas" in ergebnis["wenig"] and "Jonas" not in ergebnis["viel"]
    assert "{" not in ergebnis["gast"] and "Jonas" not in ergebnis["gast"]
    assert ergebnis["ohne"] == "Womit fangen wir an?"
    # Ein "$" im Namen ist erlaubt (auth.USERNAME_RE) und bleibt stehen, wie er ist.
    assert ergebnis["dollar"] == "Womit fangen wir an, Jo$&nas$1?"
    assert "grussZiehen(saetze, when, currentUsername)" in html


# --- 11.2.2 Sol: alles auf Englisch -------------------------------------------

def _en() -> dict[str, str]:
    roh = re.search(r"const EN = (\{.*?\n\});", _ui(), re.S)
    assert roh
    return json.loads(roh.group(1))


def _js_block(anfang: str, ende: str = "\n};") -> str:
    html = _ui()
    start = html.index(anfang)
    return html[start:html.index(ende, start)]


def test_run_phases_and_step_tags_have_english() -> None:
    en = _en()
    # "Modell laden", "Agenten arbeiten" ... standen beim Schreiben auf Deutsch da.
    phasen = re.findall(r'\w+: "([^"]+)"', _js_block("const PHASEN = {", "};"))
    assert "Modell laden" in phasen and len(phasen) >= 15
    for name in [*phasen, "Gedacht", "Keine Einzelheiten.",
                 "Das Modell hat seine Gedanken hier nicht offengelegt."]:
        assert name in en, name
    marken = set(re.findall(r'(?:step|trace)\([a-zA-Z_]+, "(\[[^"\]]+\])"', _ui()))
    assert len(marken) >= 40
    gleich = {"[Master]", "[Desktop]", "[AI Council]", "[Ai-guard]", "[Skip]", "[Mail]",
              "[virtual machine]", "[Limit]", "[Code]", "[Pro]"}
    assert sorted(m for m in marken - gleich if m not in en) == []


def test_every_english_key_is_used_somewhere() -> None:
    """Strenger als test_every_translated_text_exists_on_the_page (9.5.25): dort
    zaehlte das Woerterbuch selbst mit. Jetzt muss jeder Schluessel ausserhalb davon
    stehen -- in der Seite, in einem zusammengesetzten Satz oder beim Server."""
    import html as html_mod
    from pathlib import Path

    seite = _ui()
    roh = re.search(r"const EN = (\{.*?\n\});", seite, re.S)
    assert roh
    rest = seite[:roh.start()] + seite[roh.end():]
    rest = html_mod.unescape(re.sub(r"[\"'`]\s*\+\s*[\"'`]", "", rest))
    quellen = [" ".join(rest.split()), " ".join(re.sub(r"<[^>]+>", " ", rest).split())]
    py = "".join(p.read_text(encoding="utf-8")
                 for p in (Path(web.__file__).parent).glob("*.py"))
    py = re.sub(r"\"\s+\"", "", py)
    quellen.append(" ".join(py.split()))
    tot = [k for k in _en() if not any(k in q for q in quellen)]
    assert tot == []


def test_static_texts_with_german_have_english() -> None:
    from html.parser import HTMLParser

    en = _en()
    deutsch = re.compile(r"[äöüßÄÖÜ]|\b(und|nicht|ist|mit|für|ein|eine|wird|noch|auf|dein|"
                         r"deine|ich|du|wir|oder|bei|nach|von|im|den|dem|kein|keine|jetzt|"
                         r"hier|nur|auch|wie|wenn|der|das|zum|zur|aus|kann|bitte)\b")
    raus = {"code", "pre", "textarea", "script", "style"}
    leer = {"br", "img", "input", "meta", "link", "hr", "source", "wbr"}

    class Leser(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.stapel: list[str] = []
            self.fehlt: list[str] = []

        def handle_starttag(self, tag: str, attrs: list) -> None:
            werte = dict(attrs)
            if tag not in leer:
                self.stapel.append(tag)
            if set(self.stapel) & raus:
                return
            for name in ("placeholder", "title", "aria-label"):
                wert = " ".join(str(werte.get(name) or "").split())
                if wert and deutsch.search(wert) and wert not in en:
                    self.fehlt.append(wert)

        def handle_endtag(self, tag: str) -> None:
            if tag in self.stapel:
                del self.stapel[len(self.stapel) - 1 - self.stapel[::-1].index(tag):]

        def handle_data(self, data: str) -> None:
            text = " ".join(data.split())
            if text and not set(self.stapel) & raus and deutsch.search(text) \
                    and text not in en:
                self.fehlt.append(text)

    seite = _ui()
    body = seite[seite.index("<body"):]
    leser = Leser()
    leser.feed(body[:body.index("<script")])
    assert [t for t in leser.fehlt if t != "Mönchengladbach"] == []


def test_legal_rules_and_addons_have_english() -> None:
    from aquaticy import addons, guardrails

    ids = set(re.findall(r"\n  (\w+): \[", _js_block("const RECHT_EN = {", "\n};")))
    assert ids == {r.id for r in guardrails.RULES} | {guardrails.GENERIC.id}
    en = _en()
    texte = []
    for a in addons.CATALOG.values():
        texte += [a.summary, a.anmelden, a.hinweis]
    for gruppe in addons.PLUGIN_CONTENT.values():
        texte += list(gruppe)
    for rechte in addons.RIGHTS.values():
        for r in rechte:
            texte += [r.label] + [o[1] for o in r.options if not o[1].isdigit()]
    fehlt = {" ".join(t.split()) for t in texte if t} - set(en)
    # Was in beiden Sprachen gleich heisst, braucht keinen Eintrag.
    assert fehlt <= {"Injection: SQL, Shell, XSS (innerHTML & Co.), Templates, Logs"}


def test_server_notes_and_waits_carry_english() -> None:
    import ast
    import inspect

    from aquaticy import agent as agent_quelle

    baum = ast.parse(inspect.getsource(agent_quelle))
    hinweise = [k for k in ast.walk(baum) if isinstance(k, ast.Call)
                and getattr(k.func, "attr", "") == "_emit" and k.args
                and isinstance(k.args[0], ast.Constant) and k.args[0].value == "note"]
    assert len(hinweise) >= 7
    for k in hinweise:
        assert "text_en" in {w.arg for w in k.keywords}, ast.unparse(k)[:80]
    assert '"reason_en":' in inspect.getsource(web)
    html = _ui()
    assert 'sp(ev.text, ev.text_en || ev.text)' in html
    assert 'sp(ev.reason, ev.reason_en || ev.reason)' in html
    # Sichtbare Texte mit echten Umlauten (AGENTS.md).
    assert "laeuft normal" not in inspect.getsource(agent_quelle)


def test_patterns_translate_texts_with_numbers_and_names() -> None:
    import subprocess

    html = _ui()
    skript = "\n".join((
        "const EN = " + json.dumps(_en(), ensure_ascii=False) + ";",
        'const schluessel = text => text.replace(/\\s+/g, " ").trim();',
        html[html.index("const EN_MUSTER = ["):html.index("// Fuer Text in der Antwortblase")],
        """const faelle = {
  "3 Dateien": "3 files", "1 Datei": "1 file",
  "kein Ortsfilter · Pro · strukturiert · 4 Prüfer · Speicher an":
    "no location filter · Pro · structured · 4 checkers · memory on",
  "Bremen · virtual machine · Denktiefe high · Speicher an":
    "Bremen · Virtual machine · thinking depth high · memory on",
  "0.1 von 400 MB belegt · 0 Notizen": "0.1 of 400 MB used · 0 notes",
  "MISTRAL_API_KEY fehlt (für Modell mistral/large)":
    "MISTRAL_API_KEY missing (for model mistral/large)",
  "Firefox · unbekanntes Gerät — zuletzt 15.10.2026":
    "Firefox · unknown device — last 15.10.2026",
  "angemeldet auf 2 Gerät(en)": "signed in on 2 device(s)",
  "Das hat nicht geklappt: Da ist etwas schiefgelaufen.":
    "That didn't work: Something went wrong.",
  ["a.php: PHP- und JSP-Dateien lassen sich nicht hochladen. "
   + "Füg den Code lieber als Text in die Nachricht ein."]:
    "a.php: PHP and JSP files can't be uploaded. "
    + "Better paste the code into the message as text.",
  ["Neue Anmeldung bei deinem Konto: unbekanntes Gerät (15.10.2026). Warst du das nicht? "
   + "Ändere dein Passwort und melde dich überall sonst ab."]:
    "New sign-in to your account: unknown device (15.10.2026). Wasn't that you? "
    + "Change your password and sign out everywhere else.",
};
const aus = {};
for (const [de, soll] of Object.entries(faelle)) aus[de] = [aufEnglisch(de), soll];
aus.lang = aufEnglisch("x ".repeat(300) + "von y GB belegt");
aus.englisch = aufEnglisch("3 files");
console.log(JSON.stringify(aus));""",
    ))
    try:
        lauf = subprocess.run(["node", "-e", skript], capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        pytest.skip("node fehlt")
    ergebnis = json.loads(lauf.stdout)
    assert ergebnis.pop("lang") == "" and ergebnis.pop("englisch") == ""
    for de, (ist, soll) in ergebnis.items():
        assert ist == soll, de


def test_every_vm_stop_reason_has_english() -> None:
    from pathlib import Path

    quelle = "".join(p.read_text(encoding="utf-8")
                     for p in Path(web.__file__).parent.glob("*.py"))
    gruende = set(re.findall(r'\.stop\("([^"]+)"\)', quelle))
    gruende |= set(re.findall(r'def stop\(self, reason: str = "([^"]+)"', quelle))
    assert len(gruende) >= 5
    block = _js_block("const VM_GRUENDE_EN = {", "};")
    assert sorted(g for g in gruende if f'"{g}":' not in block) == []


def test_role_and_verdict_names_come_from_the_server_in_both_languages() -> None:
    from aquaticy import webview

    texte = webview.start_texts()
    assert set(texte["roles_en"]) == set(texte["roles"])
    assert set(texte["verdicts_en"]) == set(texte["verdicts"])
