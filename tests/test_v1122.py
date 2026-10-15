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
