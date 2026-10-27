"""11.3.2 Sol: LiteLLM 1.106.0 ohne `mcp`, und was die Pruefung danach fand."""

from __future__ import annotations

import pytest

from aquaticy import llmcall
from tests.test_web import client, session, web_settings  # noqa: F401

WERKZEUG = [{"type": "function", "function": {"name": "f", "parameters": {"type": "object"}}}]


@pytest.fixture(autouse=True)
def _frisch(monkeypatch):
    monkeypatch.setattr(llmcall, "_OHNE_MCP", False)


def _wie_litellm_1106(aufrufe: list[dict]):
    """Greift bei Werkzeugen nach `mcp` -- ausser mit _skip_mcp_handler."""
    def completion(**kwargs):
        aufrufe.append(dict(kwargs))
        if kwargs.get("tools") and not kwargs.get("_skip_mcp_handler"):
            raise ModuleNotFoundError("No module named 'mcp'", name="mcp")
        return "antwort"
    return completion


def test_a_missing_mcp_package_no_longer_breaks_every_question(monkeypatch) -> None:
    import litellm

    aufrufe: list[dict] = []
    monkeypatch.setattr(litellm, "completion", _wie_litellm_1106(aufrufe))
    assert llmcall.completion(model="mistral/m", messages=[], tools=WERKZEUG) == "antwort"
    assert [a.get("_skip_mcp_handler") for a in aufrufe] == [None, True]

    aufrufe.clear()
    assert llmcall.completion(model="mistral/m", messages=[], tools=WERKZEUG) == "antwort"
    assert [a.get("_skip_mcp_handler") for a in aufrufe] == [True]

    aufrufe.clear()
    llmcall.completion(model="mistral/m", messages=[])
    assert "_skip_mcp_handler" not in aufrufe[0]


@pytest.mark.parametrize("fehler", [ModuleNotFoundError("No module named 'x'", name="x"),
                                    ValueError("mcp")])
def test_other_errors_are_not_hidden(monkeypatch, fehler) -> None:
    import litellm

    def completion(**kwargs):
        raise fehler
    monkeypatch.setattr(litellm, "completion", completion)
    with pytest.raises(type(fehler)):
        llmcall.completion(model="mistral/m", messages=[], tools=WERKZEUG)
    assert llmcall._OHNE_MCP is False


def test_the_agent_and_the_meter_go_through_llmcall() -> None:
    import inspect

    from aquaticy import agent, local_model, metering

    assert "llmcall.completion(" in inspect.getsource(agent.Agent._completion)
    assert "llmcall.completion(**kwargs)" in inspect.getsource(metering)
    assert "llmcall.completion(" in inspect.getsource(local_model.verify_tool_calling)


def test_the_broken_litellm_is_excluded() -> None:
    from pathlib import Path

    text = (Path(llmcall.__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert '"litellm>=1.100.0,!=1.106.0,<2"' in text


def test_the_slider_minimum_is_accepted_by_the_server(monkeypatch, tmp_path) -> None:
    from aquaticy import local_model, web
    from aquaticy.config import Settings


    monkeypatch.setattr(local_model, "kv_bytes_per_token", lambda *a, **k: 5 * 1024 ** 3 // 1536)
    monkeypatch.setattr(local_model, "trained_context", lambda *a, **k: 0)
    s = Settings(model="ollama_chat/riesig:405b", context_tokens=16384, data_dir=tmp_path)
    sicht = web.context_view(s, s.model)
    assert sicht["max"] == 1024 and sicht["min"] <= 1024
    unten, oben = web.NUMBERS["AQUATICY_CONTEXT_TOKENS"]
    assert unten <= sicht["min"] and oben >= sicht["max"]




SCHWACH = {"cores": 4, "cpu_pct": 30, "ram_gb": 8, "ram_used_gb": 3, "ram_pct": 37,
           "ollama_models": 0}
STARK = {"cores": 16, "cpu_pct": 10, "ram_gb": 64, "ram_used_gb": 20, "ram_pct": 31,
         "gpu": "RTX 4090", "vram_gb": 24, "vram_used_gb": 4, "gpu_pct": 12, "ollama_models": 3}


@pytest.fixture
def staerken(tmp_path):
    """Master A ist schwach (nur Website), Mitglied B hat eine starke Grafikkarte."""
    import time as zeit

    from aquaticy import cluster
    from tests.test_cluster import Netz, _konto, _store, _verbinden

    netz = Netz()
    neustarts: list[str] = []
    gefragt: list[dict] = []
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    _konto(_store(a_dir), "anna@example.org")
    _konto(_store(b_dir), "bert@example.org")
    lokal = lambda user: user.startswith("lokal")  # noqa: E731
    a = cluster.Cluster(a_dir, port=1001, transport=netz, hooks=cluster.Hooks(
        restart=lambda: neustarts.append("a"), hardware=lambda: SCHWACH, wants_models=lokal))
    b = cluster.Cluster(b_dir, port=1002, transport=netz, hooks=cluster.Hooks(
        restart=lambda: neustarts.append("b"), ask=gefragt.append, hardware=lambda: STARK,
        wants_models=lokal))
    netz.knoten = {1001: a, 1002: b}
    for c in (a, b):
        c.state["enabled"] = True
    _verbinden(a, b, gefragt, neustarts)
    b.sync_once()
    a.sync_once()
    a.last_ok[b.node_id] = zeit.time()
    return a, b


def test_the_master_gives_models_to_the_strong_server_and_web_to_the_weak(staerken) -> None:
    a, b = staerken
    assert a.roles() == {a.node_id: "website", b.node_id: "modelle"}
    assert a.assign("lokal-1") == b.node_id, "lokale Modelle nur auf den Modell-Server"
    assert a.assign("web-1") == a.node_id, "Website-Arbeit zuerst auf den schwachen"


def test_the_strong_server_takes_a_bit_of_website_when_the_weak_is_busy(staerken) -> None:
    import time as zeit

    a, b = staerken
    for nummer in range(6):
        a.homes[f"web-alt-{nummer}"] = a.node_id
        a._activity[f"web-alt-{nummer}"] = zeit.time()
    assert a.least_loaded("web-neu") == b.node_id

    for nummer in range(6):
        a.homes[f"lokal-alt-{nummer}"] = b.node_id
        a._activity[f"lokal-alt-{nummer}"] = zeit.time()
    assert a.least_loaded("lokal-neu") == b.node_id


def test_a_local_model_account_on_the_weak_server_moves(staerken) -> None:
    import time as zeit

    a, b = staerken
    a._set_home("lokal-7", a.node_id)
    a._activity["lokal-7"] = zeit.time()
    assert a.misplaced("lokal-7", a.node_id)
    assert a.assign("lokal-7") == b.node_id
    assert not a.misplaced("lokal-7", b.node_id)


def test_without_any_model_server_everything_stays_as_before(tmp_path) -> None:
    from aquaticy import cluster

    hw = cluster.hardware(SCHWACH)
    assert cluster.model_power(hw) == 0.0
    assert cluster.model_power(cluster.hardware(STARK)) > 0

    assert cluster.model_power(cluster.hardware({**STARK, "ollama_models": 0})) == 0.0


@pytest.mark.parametrize("kaputt", [float("nan"), float("inf"), -5, "16", None, True, 10 ** 30])
def test_hardware_from_another_server_is_checked(kaputt) -> None:
    from aquaticy import cluster

    hw = cluster.hardware({key: kaputt for key in STARK} | {"gpu": "<b>x</b>" * 50})
    assert all(v == 0 for k, v in hw.items() if k != "gpu")
    assert len(hw["gpu"]) == 80
    assert cluster.hardware("kein dict")["cores"] == 0


def test_the_load_display_shows_every_server(staerken, monkeypatch) -> None:
    from aquaticy import web

    a, b = staerken
    a.assign("lokal-1")
    server = web.cluster_gauges(a)
    assert [s["role"] for s in server] == ["website", "modelle"]
    stark = server[1]
    assert stark["role_label"] == "Modelle und etwas Website" and stark["accounts"] == 1
    assert [g["name"] for g in stark["gauges"]] == ["Prozessor", "Arbeitsspeicher",
                                                     "Grafikkarte"]
    assert "RTX 4090" in stark["gauges"][2]["sub"]
    assert server[0]["self"] and server[0]["master"]

    a.last_ok[b.node_id] = 0
    assert web.cluster_gauges(a)[1]["gauges"] == [] and not web.cluster_gauges(a)[1]["alive"]


def test_the_system_endpoint_carries_the_cluster_for_ultra(client, session,  # noqa: F811
                                                           staerken, monkeypatch) -> None:
    import json

    from aquaticy import web

    a, _ = staerken
    monkeypatch.setattr(web, "CLUSTER", a)
    monkeypatch.setattr(type(session), "ultra", property(lambda self: True))
    _, body = client("GET", "/api/system")
    assert [s["role"] for s in json.loads(body)["cluster"]] == ["website", "modelle"]


def test_the_web_hooks_know_local_model_accounts(tmp_path, monkeypatch) -> None:
    from aquaticy import web
    from aquaticy.auth import AuthStore

    store = AuthStore(tmp_path, "ABCDEFGH1", "Abcdefgh1234!x")
    konto = store.register("x@example.org", "ein-sicheres-passwort", "normal",
                           terms_accepted=True, terms_version="1")
    monkeypatch.setattr(web, "AUTH", store)
    monkeypatch.setattr(web, "get_settings", lambda: web.Settings(
        model="mistral/mistral-large-latest", data_dir=tmp_path))
    assert not web._cluster_wants_models(konto.id)
    profil = store.profile_dir(konto.id)
    profil.mkdir(parents=True, exist_ok=True)
    (profil / ".env").write_text("AQUATICY_MODEL=ollama_chat/qwen3:8b\n", encoding="utf-8")
    assert web._cluster_wants_models(konto.id)
    assert not web._cluster_wants_models("gibt-es-nicht")
    hw = web._cluster_hardware()
    assert hw["cores"] >= 1 and "ollama_models" in hw


def test_a_burst_of_connections_does_not_stall() -> None:
    """Beim Laden oeffnet die Seite zwoelf Anfragen auf einmal; mit der Standard-
    Warteschlange (5) hingen einzelne davon 30 s und mehr (Rundgang, 11.3.2 Sol)."""
    import socket
    import time

    from aquaticy import web

    assert web.AquaticyServer.request_queue_size >= 64
    server = web.AquaticyServer(("127.0.0.1", 0), web.Handler)
    verbindungen = []
    try:
        anfang = time.monotonic()
        for _ in range(40):
            verbindung = socket.create_connection(server.server_address, timeout=2)
            verbindungen.append(verbindung)
        assert time.monotonic() - anfang < 2, "jeder Verbindungsaufbau sofort angenommen"
    finally:
        for verbindung in verbindungen:
            verbindung.close()
        server.server_close()
