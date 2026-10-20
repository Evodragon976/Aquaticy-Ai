"""11.3.0 Luna: Kontextfenster mit hoechstens 5 GB, robuste Adressen, stille Abbrueche."""

from __future__ import annotations

import io
import json
import socket
import struct
import threading
import time
from contextlib import redirect_stderr, redirect_stdout

import pytest

from aquaticy import local_model, web
from aquaticy.config import Settings
from tests.ollama_nachbau import Ollama
from tests.test_web import client, session, web_settings  # noqa: F401

GIB = 1024 ** 3


@pytest.fixture
def ollama():
    nachbau = Ollama()
    yield nachbau
    nachbau.stop()


@pytest.fixture(autouse=True)
def _frisch(monkeypatch):
    monkeypatch.setattr(local_model, "_CAPS", {})
    monkeypatch.setattr(local_model, "_SHOW", {})
    monkeypatch.setattr(local_model, "_FEHLT", {})


def _lokal(url: str, tmp_path, modell: str = "qwen2.5-coder:14b", tokens: int = 16384):
    return Settings(model=f"ollama_chat/{modell}", api_base=url, data_dir=tmp_path / "d",
                    context_tokens=tokens, subagents_auto=False)


# --- Kontextfenster: hoechstens 5 GB -------------------------------------------

def test_the_ram_per_token_comes_from_the_model(ollama) -> None:
    # qwen2.5-coder:14b: 48 Schichten x 8 KV-Koepfe x (128 + 128) x 2 Byte.
    assert local_model.kv_bytes_per_token("qwen2.5-coder:14b", ollama.url) == 196_608
    assert local_model.kv_bytes_per_token("qwen3:8b", ollama.url) == 147_456
    assert local_model.kv_bytes_per_token("unbekannt:1b", ollama.url) == 0
    for modell in ("qwen2.5-coder:14b", "qwen3:8b", "gemma3:4b"):
        grenze = local_model.context_limit(modell, ollama.url)
        belegt = grenze * local_model.kv_bytes_per_token(modell, ollama.url)
        assert belegt <= 5 * GIB, modell
        assert belegt > 4.5 * GIB, "und nicht unnoetig klein"
        assert grenze % 1024 == 0
    # Ohne Angaben: der bisherige Standard, nicht mehr.
    assert local_model.context_limit("unbekannt:1b", ollama.url) == 16384


def test_per_layer_kv_heads_and_the_trained_length_count(monkeypatch) -> None:
    info = {"general.architecture": "x", "x.block_count": 4,
            "x.attention.head_count": [8, 8, 8, 8], "x.attention.head_count_kv": [2, 2, 1, 1],
            "x.embedding_length": 1024, "x.context_length": 4096}
    monkeypatch.setattr(local_model, "_show", lambda *a, **k: {"model_info": info})
    # (2+2+1+1) KV-Koepfe x (128 + 128) x 2 Byte
    assert local_model.kv_bytes_per_token("x", "http://o") == 6 * 256 * 2
    assert local_model.context_limit("x", "http://o") == 4096   # trainiert: 4096


def test_every_local_call_stays_under_5_gb(ollama, tmp_path) -> None:
    viel = _lokal(ollama.url, tmp_path, tokens=1_000_000)
    assert viel.llm_kwargs_for(viel.model)["num_ctx"] == 26624
    wenig = _lokal(ollama.url, tmp_path, tokens=8192)
    assert wenig.llm_kwargs_for(wenig.model)["num_ctx"] == 8192     # darunter: wie gewollt
    wolke = Settings(model="mistral/mistral-large-latest", context_tokens=1_000_000,
                     data_dir=tmp_path / "w")
    assert "num_ctx" not in wolke.llm_kwargs_for(wolke.model)
    assert wolke.context_for(wolke.model) == 1_000_000            # Anbieter haelt es selbst


def test_the_agent_trims_history_to_the_capped_window(ollama, tmp_path) -> None:
    from aquaticy.agent import Agent

    agent = Agent(_lokal(ollama.url, tmp_path, tokens=1_000_000), cache=None)
    klein = Agent(_lokal(ollama.url, tmp_path, tokens=26624), cache=None)
    assert agent._budget_chars() == klein._budget_chars()


def test_context_view_for_the_slider(ollama, tmp_path) -> None:
    lokal = _lokal(ollama.url, tmp_path, tokens=16384)
    sicht = web.context_view(lokal, lokal.model)
    assert sicht["local"] and sicht["known"] and sicht["max"] == 26624
    assert sicht["effective"] == 16384 and sicht["cap_gb"] == 5
    assert sicht["ram_gb"] == round(16384 * 196_608 / GIB, 2)
    # Normale Konten bleiben zusaetzlich bei ihrer Obergrenze.
    assert web.context_view(lokal, lokal.model, account_cap=8192)["max"] == 8192
    wolke = web.context_view(lokal, "mistral/mistral-large-latest")
    assert wolke == {"local": False, "model": "mistral/mistral-large-latest", "tokens": 16384}


def test_context_endpoint(client, session, ollama, tmp_path) -> None:  # noqa: F811
    session._settings = _lokal(ollama.url, tmp_path)
    status, body = client("GET", "/api/context")
    assert status == 200 and json.loads(body)["max"] == 26624
    # Ein Modellname mit fremden Zeichen wird nicht weitergereicht.
    status, body = client("GET", "/api/context?model=%0Aboese%22")
    assert status == 200 and json.loads(body)["model"] == session._settings.model


# --- Fuzz-Funde: kaputte Adressen ----------------------------------------------

@pytest.mark.parametrize("adresse", ["x" * 3000, "\u0000퟿", "[1, 'a', None]",
                                     "{'a': {'b': []}}", "[]", "ha .local"])
def test_broken_addresses_are_a_clean_error(adresse: str) -> None:
    from aquaticy import homeassistant, storage

    assert homeassistant.normalize_url(adresse) == "" or "x" * 3000 in adresse
    with pytest.raises(homeassistant.HomeAssistantError):
        homeassistant.HomeAssistant(adresse, "tok").ping()
    with pytest.raises(storage.StorageError):
        storage.Storage(adresse, access="read").info()


def test_ha_and_storage_probes_answer_400_style_not_500(client, session,  # noqa: F811
                                                        monkeypatch) -> None:
    monkeypatch.setattr(type(session), "ultra", property(lambda self: True))
    for route in ("/api/ha", "/api/storage"):
        for kaputt in ("[1, 'a', None]", "\u0000x", "x" * 300):
            status, body = client("POST", route, {"url": kaputt, "token": "t"})
            assert status == 200, (route, kaputt)
            assert json.loads(body)["ok"] is False


# --- Abgerissene Verbindungen ---------------------------------------------------

def test_a_reset_connection_prints_no_traceback() -> None:
    server = web.AquaticyServer(("127.0.0.1", 0), web.Handler)
    faden = threading.Thread(target=server.serve_forever, daemon=True)
    faden.start()
    fehler, aus = io.StringIO(), io.StringIO()
    try:
        with redirect_stderr(fehler), redirect_stdout(aus):
            for _ in range(3):
                verbindung = socket.create_connection(server.server_address)
                verbindung.sendall(b"GET / HT")
                verbindung.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                                      struct.pack("ii", 1, 0))
                verbindung.close()      # RST, wie ein Handy, das einschlaeft
            time.sleep(0.5)
    finally:
        server.shutdown()
        server.server_close()
    assert "Traceback" not in fehler.getvalue() and "ConnectionReset" not in fehler.getvalue()
    assert aus.getvalue() == ""


def test_other_server_errors_are_one_line(capsys) -> None:
    server = web.AquaticyServer(("127.0.0.1", 0), web.Handler)
    try:
        try:
            raise RuntimeError("geheim")
        except RuntimeError:
            server.handle_error(None, ("10.0.0.7", 1))
    finally:
        server.server_close()
    ausgabe = capsys.readouterr()
    assert ausgabe.out.strip() == "[Verbindung] 10.0.0.7: RuntimeError"
    assert "geheim" not in ausgabe.out + ausgabe.err and "Traceback" not in ausgabe.err


def test_the_real_servers_use_the_quiet_class() -> None:
    assert issubclass(web._TLSServer, web.AquaticyServer)
    import inspect

    assert "AquaticyServer((host, kandidat), Handler)" in inspect.getsource(web.bind_server)


# --- Modellauswahl: nur, was wirklich antwortet ---------------------------------

def _ohne_schluessel(monkeypatch) -> None:
    for name in ("MISTRAL_API_KEY", "NVIDIA_NIM_API_KEY", "AQUATICY_API_KEY",
                 "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "OLLAMA_API_BASE"):
        monkeypatch.delenv(name, raising=False)


def test_the_preset_model_without_a_key_is_not_offered(monkeypatch, tmp_path) -> None:
    from aquaticy.system import available_models, model_usable

    _ohne_schluessel(monkeypatch)
    monkeypatch.setattr("aquaticy.local_model.installed_models", lambda base: [])
    frisch = Settings(model="mistral/mistral-large-latest", data_dir=tmp_path / "d")
    assert not model_usable(frisch, frisch.model)
    assert available_models(frisch) == []
    monkeypatch.setenv("MISTRAL_API_KEY", "m-test")
    assert available_models(frisch)[0]["id"] == "mistral/mistral-large-latest"


def test_what_counts_as_usable(monkeypatch, tmp_path) -> None:
    from aquaticy.config import SPLIT_MODEL_ID
    from aquaticy.system import model_usable

    _ohne_schluessel(monkeypatch)
    s = Settings(model="openai/lokal", api_base="http://localhost:1234/v1",
                 data_dir=tmp_path / "d")
    assert model_usable(s, "openai/lokal")                    # eingetragene Adresse
    assert not model_usable(s, "anthropic/claude-x")          # kein Schluessel
    # Seit 12.0.0 Luna auch mit Schluessel nicht: nur Mistral, NVIDIA NIM oder lokal.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    assert not model_usable(s, "anthropic/claude-x")
    assert not model_usable(s, "fremd/eigenes")
    monkeypatch.setenv("AQUATICY_API_KEY", "allgemein")
    assert not model_usable(s, "fremd/eigenes")
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "nvapi-test")
    assert model_usable(s, "nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5")
    # Abgeschaltet (12.2.3 Astra): auch mit Schluessel nicht mehr waehlbar.
    assert not model_usable(s, "nvidia_nim/meta/llama-3.3-70b-instruct")
    assert not model_usable(s, SPLIT_MODEL_ID)                # zeigt web.py nur, wenn er laeuft
    assert not model_usable(s, "")
    # Lokal zaehlt nur, was installiert ist -- `name` und `name:latest` sind dasselbe.
    assert model_usable(s, "ollama_chat/gemma3", ["gemma3:latest"])
    assert not model_usable(s, "ollama_chat/gemma3", ["gemma3n:e4b"])


def test_a_deleted_ollama_model_disappears_and_a_new_one_appears(ollama, tmp_path,
                                                                 monkeypatch) -> None:
    from aquaticy.system import available_models

    _ohne_schluessel(monkeypatch)
    s = _lokal(ollama.url, tmp_path, modell="qwen3:8b")
    assert "ollama_chat/qwen3:8b" in [m["id"] for m in available_models(s)]
    ollama.installiert = ["gemma3:4b"]           # qwen3 geloescht
    ids = [m["id"] for m in available_models(s)]
    assert ids == ["ollama_chat/gemma3:4b"], "kein 'Aktuell eingestellt' fuer Geloeschtes"
    ollama.installiert = ["gemma3:4b", "llama3.2:3b"]   # eben mit `ollama pull` geholt
    assert "ollama_chat/llama3.2:3b" in [m["id"] for m in available_models(s)]


def test_the_set_model_keeps_its_id_when_ollama_adds_latest(monkeypatch, tmp_path) -> None:
    from aquaticy.system import available_models

    _ohne_schluessel(monkeypatch)
    monkeypatch.setattr("aquaticy.local_model.installed_models", lambda base: ["gemma3:latest"])
    s = Settings(model="ollama_chat/gemma3", data_dir=tmp_path / "d")
    assert [m["id"] for m in available_models(s)] == ["ollama_chat/gemma3"]


def test_a_hand_picked_model_without_key_is_not_the_strongest(monkeypatch, tmp_path) -> None:
    from aquaticy.system import strongest_models

    _ohne_schluessel(monkeypatch)
    monkeypatch.setattr("aquaticy.local_model.installed_models", lambda *a, **k: ["qwen3:8b"])
    monkeypatch.setattr("aquaticy.local_model.model_size_gb", lambda *a, **k: 5.0)
    s = Settings(model="ollama_chat/qwen3:8b", code_model="mistral/codestral-latest",
                 data_dir=tmp_path / "d")
    assert [m["id"] for m in strongest_models(s, purpose="code")] == ["ollama_chat/qwen3:8b"]


def test_the_picker_in_every_mode_shows_only_usable_models(client, session,  # noqa: F811
                                                           monkeypatch) -> None:
    _ohne_schluessel(monkeypatch)
    web._strong_cache.clear()
    monkeypatch.setattr("aquaticy.local_model.installed_models", lambda *a, **k: [])
    session._settings.code_model = "nvidia_nim/meta/llama-3.3-70b-instruct"
    for modus in ("normal", "pro", "code"):
        _, body = client("GET", f"/api/models?mode={modus}")
        auswahl = json.loads(body)["picker"]
        assert auswahl["models"] == [], modus
        assert "Schlüssel" in auswahl["empty"]
    web._strong_cache.clear()


def test_the_web_start_reports_what_ollama_has(ollama, tmp_path, monkeypatch) -> None:
    from aquaticy import cli

    zeilen: list[str] = []
    monkeypatch.setattr(cli.console, "print", lambda text="", *a, **k: zeilen.append(str(text)))
    s = _lokal(ollama.url, tmp_path, modell="qwen3:8b")
    assert cli._ollama_beim_start(s) == list(ollama.installiert)
    assert "3 Modelle" in zeilen[0] and "qwen3:8b" in zeilen[0]
    zeilen.clear()
    ollama.installiert = ["gemma3:4b"]
    cli._ollama_beim_start(s)
    assert "1 Modell" in zeilen[0]
    assert any("nicht installiert" in z for z in zeilen[1:])
    # Kein Ollama, Hauptmodell in der Wolke: kein Wort und kein Start.
    zeilen.clear()
    monkeypatch.setattr(local_model, "start_server",
                        lambda *a, **k: pytest.fail("darf nicht starten"))
    wolke = Settings(model="mistral/mistral-large-latest", api_base="http://127.0.0.1:9",
                     data_dir=tmp_path / "w")
    assert cli._ollama_beim_start(wolke) == [] and zeilen == []


def test_a_local_main_model_starts_an_installed_ollama(tmp_path, monkeypatch) -> None:
    from aquaticy import cli

    gestartet: list[str] = []
    monkeypatch.setattr(local_model, "server_running", lambda *a, **k: False)
    monkeypatch.setattr(local_model, "ollama_binary", lambda: "/usr/bin/ollama")
    monkeypatch.setattr(local_model, "start_server",
                        lambda basis, **k: gestartet.append(basis) or True)
    monkeypatch.setattr(local_model, "installed_models", lambda basis: ["qwen3:8b"])
    monkeypatch.setattr(cli.console, "print", lambda *a, **k: None)
    s = Settings(model="ollama_chat/qwen3:8b", data_dir=tmp_path / "d")
    assert cli._ollama_beim_start(s) == ["qwen3:8b"]
    assert gestartet == [local_model.DEFAULT_OLLAMA_URL]
    # Ein fremder Rechner wird nie "gestartet".
    gestartet.clear()
    fern = Settings(model="ollama_chat/qwen3:8b", api_base="http://10.0.0.5:11434",
                    data_dir=tmp_path / "f")
    cli._ollama_beim_start(fern)
    assert gestartet == []


def test_the_header_does_not_present_a_model_without_key(client, session,  # noqa: F811
                                                         monkeypatch) -> None:
    _ohne_schluessel(monkeypatch)
    web._strong_cache.clear()
    monkeypatch.setattr("aquaticy.local_model.installed_models", lambda *a, **k: [])
    _, body = client("GET", "/api/header")
    assert json.loads(body)["model_label"] == "Modell wählen"
    session._settings.api_keys["MISTRAL_API_KEY"] = "m-test"
    web._strong_cache.clear()
    _, body = client("GET", "/api/header")
    assert json.loads(body)["model_label"] == "mistral-large-latest"
    web._strong_cache.clear()


def test_a_deleted_upgrade_version_is_not_offered(tmp_path) -> None:
    from aquaticy import upgrading as up
    from tests.test_upgrading import BASE, FAKTEN
    from tests.test_upgrading import Ollama as UpOllama

    up.set_enabled(tmp_path, True, [BASE])
    up.train_all(tmp_path, FAKTEN, UpOllama(base_kennt=18))
    up.upgrade(tmp_path, BASE)
    neu = "ollama_chat/" + up.model_name(BASE, [1, 1])
    da = [{"id": f"ollama_chat/{BASE}", "label": BASE}, {"id": neu, "label": "x"}]
    assert neu in [m["id"] for m in up.picker_entries(tmp_path, da, False)]
    # `ollama rm` der neuen Fassung: sie steht nicht mehr zur Wahl.
    weg = up.picker_entries(tmp_path, da[:1], False)
    assert neu not in [m["id"] for m in weg] and weg


def test_foreign_model_names_do_not_fill_the_memory(monkeypatch) -> None:
    monkeypatch.setattr(local_model.httpx, "stream",
                        lambda *a, **k: (_ for _ in ()).throw(local_model.httpx.ConnectError("x")))
    for nummer in range(local_model._MERK_MAX * 3):
        local_model.ollama_capabilities(f"fremd-{nummer}", "http://o")
    assert len(local_model._SHOW) <= local_model._MERK_MAX
    assert len(local_model._CAPS) <= local_model._MERK_MAX


def test_the_picker_has_the_context_slider() -> None:
    from pathlib import Path

    html = (Path(web.__file__).parent / "webui.html").read_text(encoding="utf-8")
    regler = html[html.index('id="picker-ctx"'):html.index('<div class="picker-actions">')]
    assert 'type="range" id="ctx-regler"' in regler and "5 GB" in regler
    oeffnen = html[html.index("async function openPicker"):html.index("async function chooseModel")]
    assert "zeigeKontext(currentModel)" in oeffnen
    assert '$("#picker-ctx").hidden = true' in oeffnen     # alte Zeile weg, auch bei leerer Liste
    skript = html[html.index("async function zeigeKontext"):
                  html.index("async function chooseModel")]
    assert '"/api/context?model="' in skript and "AQUATICY_CONTEXT_TOKENS" in skript
    assert "if (!ctxStand?.local){ zeile.hidden = true; return; }" in skript


@pytest.mark.parametrize("kaputt", [float("nan"), float("inf"), -1, "48", None, True, [None]])
def test_odd_model_info_never_crashes_or_widens_the_window(monkeypatch, kaputt) -> None:
    for feld in ("block_count", "attention.key_length", "attention.head_count_kv"):
        info = {"general.architecture": "x", "x.block_count": 32, "x.attention.head_count": 32,
                "x.attention.head_count_kv": 8, "x.attention.key_length": 128,
                "x.embedding_length": 4096, "x.context_length": 1_000_000}
        info[f"x.{feld}"] = kaputt
        if feld == "attention.key_length":
            info["x.attention.key_length"] = info["x.block_count"] = kaputt
        monkeypatch.setattr(local_model, "_show", lambda *a, _i=info, **k: {"model_info": _i})
        je_token = local_model.kv_bytes_per_token("x", "http://o")
        grenze = local_model.context_limit("x", "http://o")
        assert je_token >= 0
        assert grenze == 16384 or grenze * je_token <= 5 * GIB, (feld, kaputt)
