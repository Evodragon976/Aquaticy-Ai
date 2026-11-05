"""15.1.1: Was genau fehlt (statt "diese Nummer oder Seite"), Suche nur Issues/PRs,
Sicherheits-Workflow und Hinweise gegen erfundene Befunde."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from aquaticy import addons, github_repo, tools

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "ghp_" + "a" * 36
REPO = {"full_name": "Evodragon976/Aquaticy-Ai", "default_branch": "Aquaticy-ai"}


def _client(routes: dict[str, Any], gesehen: list[httpx.Request]) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        gesehen.append(request)
        wert = routes.get(request.url.path)
        return httpx.Response(200, json=wert) if wert is not None else httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handle))


@pytest.fixture(autouse=True)
def ohne_takt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(addons, "_takt", lambda host, abstand=1.05: None)


def test_a_missing_file_is_named_not_a_number() -> None:
    gesehen: list[httpx.Request] = []
    with _client({"/repos/Evodragon976/Aquaticy-Ai": REPO}, gesehen) as client:
        ergebnis = addons.github_call(TOKEN, "datei", repo="Evodragon976/Aquaticy-Ai",
                                      path="requirements.txt", client=client)
    assert "„requirements.txt“" in ergebnis["error"]
    assert "Nummer" not in ergebnis["error"] and "der Zugriff passt" in ergebnis["error"]
    assert all(r.method == "GET" for r in gesehen)


@pytest.mark.parametrize(("route", "params", "erwartet"), [
    ("/repos/o/r/contents/a/b.py", {"ref": "dev"}, "„a/b.py“ im Branch „dev“"),
    ("/repos/o/r/commits/abc", {}, "Commit oder Branch „abc“"),
    ("/repos/o/r/git/trees/main", {}, "Branch oder Commit „main“"),
    ("/repos/o/r/issues/7/comments", {}, "das Issue Nr. 7"),
    ("/repos/o/r/pulls/3", {}, "den Pull Request Nr. 3"),
    ("/repos/o/r/commits", {"sha": "main"}, "„main“"),
    ("/repos/o/r/issues", {}, "diese Seite"),
])
def test_missing_in_repo_names_the_part(route: str, params: dict[str, Any],
                                        erwartet: str) -> None:
    text = github_repo.missing_in_repo("o/r", "Aquaticy-ai", route, params)
    assert erwartet in text and "„Aquaticy-ai“" in text and "kein Rechteproblem" in text


def test_search_says_it_finds_no_code() -> None:
    gesehen: list[httpx.Request] = []
    with _client({"/search/issues": {"items": [], "total_count": 0}}, gesehen) as client:
        ergebnis = addons.github_call(TOKEN, "suche", repo="o/r", query="security",
                                      client=client)
    assert ergebnis["gesamt"] == 0 and "keinen Code" in ergebnis["hinweis"]


def test_the_tool_warns_against_invented_findings() -> None:
    beschreibung = tools.GITHUB_SCHEMA["function"]["description"]
    assert "kein Code" in beschreibung and "erfinde keine" in beschreibung
    assert "pyproject.toml statt requirements.txt" in beschreibung
    basis = tools.GITHUB_SCHEMA["function"]["parameters"]["properties"]["base"]["description"]
    assert "main" not in basis


def test_the_security_workflow_only_reads_and_pins_its_tools() -> None:
    text = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in text
    assert "persist-credentials: false" in text
    assert "pip-audit==" in text and "bandit==" in text
    assert "tools/bandit-baseline.json" in text and "constraints.txt" in text
    bandit = next(z for z in (ROOT / "constraints.txt").read_text().splitlines()
                  if z.startswith("bandit=="))
    assert bandit in text
    assert "secrets." not in text and "write" not in text
