"""11.3.1 Luna: Kontextgrenzen, Modellrouting, Metadaten und sichere Podman-Einrichtung."""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from aquaticy import local_model as lm
from aquaticy import system, vm_install, web
from aquaticy.config import Settings


@pytest.fixture(autouse=True)
def fresh_caches(monkeypatch):
    monkeypatch.setattr(lm, "_SHOW", {})
    monkeypatch.setattr(lm, "_CAPS", {})


def _info(**fields):
    return {"general.architecture": "x", "x.block_count": 4,
            "x.attention.head_count": 8, "x.attention.head_count_kv": 8,
            "x.embedding_length": 1024, "x.context_length": 32768, **fields}


@pytest.mark.parametrize("maximum", [512, 1024, 1536])
def test_minimum_cannot_exceed_trained_context(monkeypatch, maximum):
    monkeypatch.setattr(lm, "_show", lambda *args: {
        "model_info": _info(**{"x.context_length": maximum})})
    assert lm.context_limit("x") <= maximum
    settings = Settings(model="ollama_chat/x", context_tokens=16384)
    view = web.context_view(settings, settings.model)
    assert view["effective"] == settings.context_for(settings.model)
    assert view["min"] <= view["max"] <= maximum


def test_minimum_cannot_exceed_ram_limit(monkeypatch):
    info = _info(**{"x.block_count": 128, "x.attention.head_count": 96,
                    "x.attention.head_count_kv": 96, "x.embedding_length": 12288})
    monkeypatch.setattr(lm, "_show", lambda *args: {"model_info": info})
    limit = lm.context_limit("x")
    assert limit * lm.kv_bytes_per_token("x") <= lm.CONTEXT_RAM_BYTES
    settings = Settings(model="ollama_chat/x", context_tokens=16384)
    assert web.context_view(settings, settings.model)["effective"] == limit


def test_variable_heads_use_each_layers_width(monkeypatch):
    info = _info(**{"x.block_count": 2, "x.attention.head_count": [8, 16],
                    "x.attention.head_count_kv": [8, 8]})
    monkeypatch.setattr(lm, "_show", lambda *args: {"model_info": info})
    assert lm.kv_bytes_per_token("x") == (8 * (128 + 128) + 8 * (64 + 64)) * 2


def test_incomplete_kv_heads_are_not_treated_as_a_complete_layout(monkeypatch):
    info = _info(**{"x.attention.head_count_kv": [8]})
    monkeypatch.setattr(lm, "_show", lambda *args: {"model_info": info})
    assert lm.kv_bytes_per_token("x") >= 4 * 8 * (128 + 128) * 2


@pytest.mark.parametrize("method", [system.available_models, system.strongest_models])
def test_model_discovery_uses_the_ollama_route(monkeypatch, tmp_path, method):
    monkeypatch.setenv("OLLAMA_API_BASE", "http://127.0.0.1:11999")
    settings = Settings(model="mistral/mistral-large-latest", api_base="https://api.example.org",
                        data_dir=tmp_path)
    visited = []
    monkeypatch.setattr(lm, "installed_models", lambda base: visited.append(base) or [])
    method(settings)
    assert visited == [settings.ollama_base("ollama_chat/x")]


def test_show_discards_unneeded_private_prompt_and_template(monkeypatch):
    raw = {"capabilities": ["completion", "tools"], "model_info": _info(),
           "system": "Private learning text", "modelfile": "Private prompt", "template": "x"}

    @contextmanager
    def stream(*args, **kwargs):
        yield httpx.Response(200, json=raw, request=httpx.Request("POST", "http://o/api/show"))

    monkeypatch.setattr(lm.httpx, "post", lambda *args, **kwargs: httpx.Response(200, json=raw))
    monkeypatch.setattr(lm.httpx, "stream", stream)
    result = lm._show("x", "http://o")
    assert result["model_info"] and result["capabilities"] == raw["capabilities"]
    assert not {"system", "modelfile", "template"}.intersection(result)


def test_show_rejects_compressed_oversize_metadata(monkeypatch):
    payload = gzip.compress(json.dumps({"model_info": _info(), "padding": "x" * 100_000})
                            .encode())

    @contextmanager
    def stream(*args, **kwargs):
        yield httpx.Response(200, headers={"Content-Encoding": "gzip"},
                             stream=httpx.ByteStream(payload),
                             request=httpx.Request("POST", "http://o/api/show"))

    monkeypatch.setattr(lm, "MAX_MODEL_INFO_BYTES", 1024, raising=False)
    monkeypatch.setattr(lm.httpx, "stream", stream)
    monkeypatch.setattr(lm.httpx, "post", lambda *args, **kwargs: httpx.Response(
        200, json={"model_info": _info(), "padding": "x" * 100_000}))
    assert lm._show("x", "http://o") is None


def test_impossible_context_is_rejected_instead_of_using_a_large_fallback(monkeypatch):
    info = _info(**{"x.block_count": 128, "x.attention.head_count": 1_000_000,
                    "x.attention.head_count_kv": 1_000_000,
                    "x.embedding_length": 128_000_000})
    monkeypatch.setattr(lm, "_show", lambda *args: {"model_info": info})
    settings = Settings(model="ollama_chat/x")
    with pytest.raises(lm.ContextLimitError):
        settings.llm_kwargs_for(settings.model)
    assert "error" in web.context_view(settings, settings.model)


@pytest.mark.parametrize("last_model", ["a", "b", "cloud"])
@pytest.mark.parametrize("closed", [False, True])
@pytest.mark.skipif(shutil.which("node") is None, reason="node fehlt")
def test_old_context_response_cannot_overwrite_newer_state(last_model, closed):
    html = Path(web.__file__).with_name("webui.html").read_text(encoding="utf-8")
    block = html[html.index("let ctxStand = null;"):
                 html.index('$("#ctx-regler").addEventListener("input"')]
    script = """
const els = {};
const $ = sel => els[sel] ||= {hidden: true, value: 'unchanged'};
const sprache = 'de', sp = de => de, toast = () => {}, nutzerFehler = x => x;
let open = true;
const pickerOpen = () => open;
const pending = [];
const api = () => new Promise(resolve => pending.push(resolve));
""" + block + "\n" + f"const last = {json.dumps(last_model)}, closed = {json.dumps(closed)};" + """
const data = (model, effective) => ({local: model !== 'cloud', model, effective,
  min: 2048, max: 16384, per_token: 1024, known: true, cap_gb: 5});
const first = zeigeKontext('a'), second = zeigeKontext(last);
if (closed) open = false;
pending[1]({json: async () => data(last, 8192)});
await second;
pending[0]({json: async () => data('a', 4096)});
await first;
console.log(JSON.stringify({model: ctxStand?.model, value: $('#ctx-regler').value,
  hidden: $('#picker-ctx').hidden}));
"""
    result = subprocess.run(["node", "--input-type=module"], input=script,
                            capture_output=True, text=True, check=True)
    state = json.loads(result.stdout)
    if closed:
        assert state.get("model") is None and state["value"] == "unchanged"
    elif last_model == "cloud":
        assert state["hidden"] is True and state["model"] == "cloud"
    else:
        assert state["value"] == "8192" and state["model"] == last_model


@pytest.mark.parametrize("platform", ["Darwin", "Windows"])
@pytest.mark.parametrize("exists", [False, True])
def test_automatic_podman_start_never_creates_a_machine(monkeypatch, platform, exists):
    monkeypatch.setattr(vm_install.platform, "system", lambda: platform)
    monkeypatch.setattr(vm_install.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr("aquaticy.sandbox.find_runtime", lambda: None)
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        code = 0 if exists or command[-1] != "inspect" else 1
        return SimpleNamespace(returncode=code)

    assert vm_install.start_machine(run=run) is exists
    expected = [["podman", "machine", "inspect"]]
    if exists:
        expected.append(["podman", "machine", "start"])
    assert commands == expected


def test_automatic_context_keeps_default_and_reports_unknown_effective_size(monkeypatch):
    monkeypatch.setattr(lm, "_show", lambda *args: {"model_info": _info()})
    settings = Settings(model="ollama_chat/x", context_tokens=0)
    assert "num_ctx" not in settings.llm_kwargs()
    view = web.context_view(settings, settings.model)
    assert view["automatic"] is True
    assert view["effective"] is None and view["ram_gb"] is None


@pytest.mark.parametrize("language", ["de", "en"])
@pytest.mark.skipif(shutil.which("node") is None, reason="node fehlt")
def test_automatic_context_label_and_manual_preview(language):
    html = Path(web.__file__).with_name("webui.html").read_text(encoding="utf-8")
    block = html[html.index("let ctxStand = null;"):
                 html.index('$("#ctx-regler").addEventListener("input"')]
    script = f"const sprache = {json.dumps(language)};" + """
const sp = (de, en) => sprache === 'en' ? en : de;
""" + block + """
ctxStand = {automatic: true, known: true, per_token: 1024};
console.log(JSON.stringify([ctxText(null), ctxText(4096, true)]));
"""
    result = subprocess.run(["node", "--input-type=module"], input=script,
                            capture_output=True, text=True, check=True)
    default, preview = json.loads(result.stdout)
    assert default == ("Ollama-Standard" if language == "de" else "Ollama default")
    assert preview.startswith("4.096" if language == "de" else "4,096")
