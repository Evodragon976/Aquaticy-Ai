"""15.0.1: GitHub-Commits trotz Weiterleitung und fremdem Konto, genaue Fehlermeldung,
Repo ohne Besitzer, und `aquaticy stop`."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from aquaticy import addons, cli, github_repo, old_server

TOKEN_KLASSISCH = "ghp_" + "a" * 36
TOKEN_FEIN = "github_pat_" + "b" * 60
SHA = "1" * 40


def _client(routes: dict[str, Any], gesehen: list[httpx.Request]) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        gesehen.append(request)
        wert = routes.get(request.url.path)
        if callable(wert):
            wert = wert(request)
        if isinstance(wert, httpx.Response):
            return wert
        return httpx.Response(200, json=wert) if wert is not None else httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handle))


@pytest.fixture(autouse=True)
def ohne_takt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(addons, "_takt", lambda host, abstand=1.05: None)


def test_commits_of_a_moved_repo_follow_the_redirect() -> None:
    gesehen: list[httpx.Request] = []
    routes = {
        "/repos/alt/Aquaticy-Ai/commits": httpx.Response(
            301, headers={"location": "https://api.github.com/repositories/42/commits?per_page=20"}),
        "/repositories/42/commits": [{"sha": SHA, "commit": {"message": "Fix", "author": {}}}],
    }
    with _client(routes, gesehen) as client:
        ergebnis = addons.github_call(TOKEN_KLASSISCH, "commits", repo="alt/Aquaticy-Ai",
                                      client=client)
    assert ergebnis["commits"][0]["sha"] == SHA


def test_redirects_leave_api_github_com_never() -> None:
    gesehen: list[httpx.Request] = []
    routes = {"/repos/o/r/commits": httpx.Response(
        301, headers={"location": "https://evil.example/steal"})}
    with _client(routes, gesehen) as client:
        ergebnis = addons.github_call(TOKEN_KLASSISCH, "commits", repo="o/r", client=client)
    assert "unerwartete" in ergebnis["error"]
    assert all(r.url.host == "api.github.com" for r in gesehen)


def test_a_public_repo_is_read_without_the_token_if_needed() -> None:
    gesehen: list[httpx.Request] = []

    def commits(request: httpx.Request) -> httpx.Response:
        if "authorization" in request.headers:
            return httpx.Response(404)
        return httpx.Response(200, json=[{"sha": SHA, "commit": {"message": "x"}}])

    with _client({"/repos/o/r/commits": commits}, gesehen) as client:
        ergebnis = addons.github_call(TOKEN_FEIN, "commits", repo="o/r", client=client)
    assert ergebnis["commits"][0]["sha"] == SHA


def test_a_private_repo_of_another_account_says_why() -> None:
    gesehen: list[httpx.Request] = []
    routes = {"/user": {"login": "Evodragon976"}}
    with _client(routes, gesehen) as client:
        ergebnis = addons.github_call(TOKEN_FEIN, "commits",
                                      repo="jonasenriklaumen-a11y/Aquaticy-Ai", client=client)
    assert "gehört dem Konto jonasenriklaumen-a11y" in ergebnis["error"]
    assert "klassisches Token" in ergebnis["error"] and "Evodragon976" in ergebnis["error"]
    assert TOKEN_FEIN not in ergebnis["error"]


def test_missing_reasons_name_the_fix() -> None:
    assert "Repository access" in github_repo.missing_reason("me/r", "me", TOKEN_FEIN)
    assert "„repo“" in github_repo.missing_reason("me/r", "me", TOKEN_KLASSISCH)


def test_a_repo_without_owner_is_found_in_the_own_repos() -> None:
    gesehen: list[httpx.Request] = []
    routes = {
        "/user/repos": [{"name": "Aquaticy-Ai", "full_name": "jonas/Aquaticy-Ai"}],
        "/repos/jonas/Aquaticy-Ai/commits": [{"sha": SHA, "commit": {"message": "x"}}],
    }
    with _client(routes, gesehen) as client:
        ergebnis = addons.github_call(TOKEN_KLASSISCH, "commits", repo="aquaticy-ai",
                                      client=client)
        assert ergebnis["commits"][0]["sha"] == SHA and ergebnis["repo"] == "jonas/Aquaticy-Ai"
        fehlt = addons.github_call(TOKEN_KLASSISCH, "commits", repo="Unbekannt", client=client)
    assert "finde ich in deinen Repos nicht" in fehlt["error"]


# -- aquaticy stop --------------------------------------------------------------------------------
@pytest.mark.parametrize("befehl,server", [
    (["/usr/bin/python3", "-m", "aquaticy.cli", "web", "--foreground"], True),
    (["/home/u/.local/bin/aquaticy", "web"], True),
    (["aquaticy", "stop"], False),
    (["vim", "aquaticy", "web"], False),
])
def test_only_aquaticy_servers_are_found(befehl: list[str], server: bool) -> None:
    assert old_server._ist_server(befehl) is server


def test_stop_ends_the_running_servers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.os, "name", "posix")
    monkeypatch.setattr(old_server, "aquaticy_servers", lambda: [111, 222])
    beendet: list[int] = []
    monkeypatch.setattr(old_server, "stop", lambda pid: beendet.append(pid) or True)
    ergebnis = CliRunner().invoke(cli.app, ["stop"])
    assert ergebnis.exit_code == 0 and beendet == [111, 222]
    assert "Prozess 111) ist beendet" in ergebnis.output
    monkeypatch.setattr(old_server, "aquaticy_servers", lambda: [])
    assert "kein Aquaticy-Server" in CliRunner().invoke(cli.app, ["stop"]).output


def test_stop_by_port_only_touches_aquaticy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.os, "name", "posix")
    monkeypatch.setattr(old_server, "listener_pids", lambda port: [5, 6])
    monkeypatch.setattr(old_server, "is_aquaticy", lambda pid: pid == 6)
    beendet: list[int] = []
    monkeypatch.setattr(old_server, "stop", lambda pid: beendet.append(pid) or True)
    assert CliRunner().invoke(cli.app, ["stop", "--port", "8765"]).exit_code == 0
    assert beendet == [6]


def test_the_server_list_never_contains_this_process() -> None:
    import os

    assert os.getpid() not in old_server.aquaticy_servers()
