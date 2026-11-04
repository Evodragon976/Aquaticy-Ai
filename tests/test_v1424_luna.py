"""GitHub-Codepruefung liest echte Auszuege, achtet Rechte und begrenzt Netzwerkdaten."""

import base64
import json

import httpx
import pytest

from aquaticy import addons, github_repo, plugins
from aquaticy.agent import Agent
from aquaticy.tools import Toolbox
from tests.test_agent import ScriptedLLM, _message

COMMIT = "a" * 40
TREE = "b" * 40
TOKEN = "ghp_" + "t" * 36


def content(text):
    return {"type": "file", "encoding": "base64", "size": len(text.encode()),
            "content": base64.b64encode(text.encode()).decode()}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(addons, "_takt", lambda *a, **kw: None)
    routes = {
        "/repos/o/r": {"full_name": "o/r", "private": False, "default_branch": "main"},
        "/repos/o/r/commits/main": {"sha": COMMIT, "commit": {"tree": {"sha": TREE}}},
        "/repos/o/r/commits/HEAD": {"sha": COMMIT, "commit": {"tree": {"sha": TREE}}},
        f"/repos/o/r/git/trees/{TREE}": {"tree": [
            {"path": "src/auth.py", "type": "blob", "size": 100},
            {"path": "src/öffnen.py", "type": "blob", "size": 10}]},
        "/repos/o/r/contents/src/auth.py": content("import os\nos.system(request.args['q'])\n"),
        "/repos/o/r/contents/src/öffnen.py": content("print('Hallo')\n"),
    }
    calls = []

    def handle(request):
        calls.append(request)
        assert request.method == "GET" and request.url.host == "api.github.com"
        value = routes.get(request.url.path)
        if callable(value):
            value = value(request)
        if value is None:
            return httpx.Response(404, json={})
        if isinstance(value, httpx.Response):
            return value
        return httpx.Response(200, json=value)

    with httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=True) as client:
        yield client, routes, calls


def test_review_reads_code_at_one_immutable_commit(api):
    client, _, calls = api
    result = addons.github_call(TOKEN, "review", repo="https://github.com/o/r.git", client=client)
    assert result["commit"] == COMMIT and result["privat"] is False
    assert result["dateien"][0]["datei"] == "src/auth.py"
    assert "os.system" in result["dateien"][0]["text"]
    assert result["dateien"][0]["vorpruefung"]
    assert any(r.url.params.get("ref") == COMMIT for r in calls if "/contents/" in r.url.path)


def test_tree_and_files_are_paged_with_full_paths_and_line_numbers(api):
    client, routes, _ = api
    routes[f"/repos/o/r/git/trees/{TREE}"]["tree"] = [
        {"path": f"src/file{i}.py", "type": "blob"} for i in range(45)]
    first = addons.github_call(TOKEN, "baum", repo="o/r", client=client)
    second = addons.github_call(TOKEN, "tree", repo="o/r", page=2, client=client)
    assert first["next_page"] == 2 and second["eintraege"][0]["path"] == "src/file20.py"
    routes["/repos/o/r/contents/large.py"] = content(''.join(f"line{i}\n" for i in range(1000)))
    part = addons.github_call(TOKEN, "datei", repo="o/r", path="large.py", start_line=501,
                              max_lines=20, client=client)
    assert part["start_line"] == 501 and part["end_line"] == 520 and part["next_line"] == 521
    assert part["text"].startswith("line500\n") and part["text"].endswith("line519\n")


def test_url_branches_with_slashes_are_resolved_before_reading(api):
    client, routes, calls = api
    routes["/repos/o/r/commits/feature/security"] = routes["/repos/o/r/commits/main"]
    result = addons.github_call(TOKEN, "datei", repo=(
        "https://github.com/o/r/blob/feature/security/src/%C3%B6ffnen.py"), client=client)
    assert result["datei"] == "src/öffnen.py" and result["text"] == "print('Hallo')\n"
    assert calls[-1].url.params["ref"] == "feature/security"


def test_pr_review_includes_diff_and_handles_removed_files(api):
    client, routes, _ = api
    routes["/repos/o/r/pulls/12"] = {"head": {"sha": COMMIT}}
    routes["/repos/o/r/pulls/12/files"] = [
        {"filename": "src/auth.py", "status": "modified", "patch": "@@ -1 +1 @@\n+safe"},
        {"filename": "gone.py", "status": "removed", "patch": "-old code"}]
    result = addons.github_call(TOKEN, "review", repo="https://github.com/o/r/pull/12",
                                client=client)
    assert result["pull"] == 12 and result["commit"] == COMMIT
    assert "+safe" in result["dateien"][0]["patch"]
    assert "gelöscht" in result["dateien"][1]["hinweis"]


@pytest.mark.parametrize("action", ["datei", "baum", "review", "pull"])
def test_public_only_rejects_private_and_unknown_visibility_before_contents(api, action):
    client, routes, calls = api
    for metadata in ({"private": True}, {}):
        routes["/repos/o/r"] = metadata
        calls.clear()
        result = addons.github_call(TOKEN, action, repo="o/r", path="src/auth.py", number=1,
                                    nur_oeffentlich=True, client=client)
        assert "error" in result and len(calls) == 1 and calls[0].url.path == "/repos/o/r"


def test_search_cannot_return_private_repos_via_query_operators(api):
    client, routes, _ = api
    routes["/search/issues"] = {"items": [
        {"repository_url": "https://api.github.com/repos/o/secret", "title": "private"},
        {"repository_url": "https://api.github.com/repos/o/r", "title": "public"}]}
    routes["/repos/o/secret"] = {"private": True}
    result = addons.github_call(TOKEN, "suche", query="x OR is:private", nur_oeffentlich=True,
                                client=client)
    assert [r["titel"] for r in result["treffer"]] == ["public"]


def test_overview_blocks_review_without_fetching_source(api):
    client, _, calls = api
    result = addons.github_call(TOKEN, "review", repo="o/r", inhalte=False, client=client)
    assert "nicht freigegeben" in result["error"] and calls == []


@pytest.mark.parametrize("repo,path,ref", [
    ("https://github.com.evil.example/o/r", "", ""),
    ("https://github.com@evil.example/o/r", "", ""),
    ("o/r", "../secrets", ""), ("o/r", "%2e%2e/user", ""),
    ("o/r", "x", "../../user"), ("../..", "", "")])
def test_unsafe_targets_are_rejected_without_requests(api, repo, path, ref):
    client, _, calls = api
    assert "error" in addons.github_call(TOKEN, "datei", repo=repo, path=path, ref=ref,
                                         client=client)
    assert calls == []


def test_redirects_never_forward_token_to_another_host(api):
    client, routes, calls = api
    routes["/repos/o/r"] = httpx.Response(302, headers={"Location": "https://evil.example/"})
    assert "error" in addons.github_call(TOKEN, "repo", repo="o/r", client=client)
    assert len(calls) == 1


def test_http_and_base64_limits_are_enforced_before_large_decode(api, monkeypatch):
    client, routes, _ = api
    monkeypatch.setattr(github_repo, "MAX_RESPONSE", 100)
    routes["/repos/o/r"] = {"name": "x" * 200}
    assert "zu groß" in addons.github_call(TOKEN, "repo", repo="o/r", client=client)["error"]
    monkeypatch.setattr(github_repo, "MAX_RESPONSE", 10000)
    monkeypatch.setattr(github_repo, "MAX_FILE", 10)
    monkeypatch.setattr(github_repo.base64, "b64decode", lambda *a, **kw:
                        pytest.fail("oversized base64 was decoded"))
    result = addons.github_call(TOKEN, "datei", repo="o/r", path="src/auth.py", client=client)
    assert "text" not in result


def test_credentials_are_masked_and_preflight_keeps_original_lines(api):
    client, routes, _ = api
    secret = "ghp_" + "a" * 36
    text = (f"token = '{secret}'\n-----BEGIN PRIVATE KEY-----\n"
            "secret-body\n-----END PRIVATE KEY-----\n")
    routes["/repos/o/r/contents/secrets.py"] = content(text)
    result = addons.github_call(TOKEN, "datei", repo="o/r", path="secrets.py", client=client)
    assert secret not in json.dumps(result) and "secret-body" not in result["text"]
    assert len(result["text"].splitlines()) == 4 and result["start_line"] == 1
    assert any(h["regel"] == "CWE-798" and h["zeilen"] == [1] for h in result["vorpruefung"])


def test_context_budget_is_real_and_does_not_break_json_or_line_resume(api):
    client, routes, _ = api
    routes["/repos/o/r/contents/large.py"] = content('print("x"*10)\n' * 1000)
    result = addons.github_call(TOKEN, "datei", repo="o/r", path="large.py", max_lines=400,
                                client=client)
    bounded = github_repo.bound(result, 2000)
    assert len(json.dumps(bounded, ensure_ascii=False)) <= 2000
    assert bounded["next_line"] == 1 + bounded["text"].count("\n")


def test_private_repo_data_requires_confirmation_before_public_search(settings, monkeypatch):
    box = Toolbox(settings)
    try:
        box._after_untrusted("github", {"privat": True, "text": "private source"})
        monkeypatch.setattr(box, "web_search", lambda **kw: pytest.fail("private search"))
        assert box.call("web_search", {"query": "some private code"})[
            "skipped_reason"] == "private_data"
        box.ask_handler = lambda *a: "nein"
        assert box.call("web_search", {"query": "general documentation"})[
            "skipped_reason"] == "private_data"
        box.ask_handler = lambda *a: "ja"
        monkeypatch.setattr(box, "web_search", lambda **kw: {"results": []})
        assert box.call("web_search", {"query": "general documentation"})["results"] == []
    finally:
        box.close()


def test_agent_prefetches_repo_even_without_model_tools_and_skips_council(
        settings, api, monkeypatch):
    client, _, _ = api
    addons.install(settings, "github", pro=True)
    settings.github_token = TOKEN
    settings.council = True
    real_call = addons.github_call
    monkeypatch.setattr(addons, "github_call", lambda *a, **kw: real_call(*a, **kw, client=client))
    model = ScriptedLLM(_message("Im gelesenen Ausschnitt src/auth.py steht os.system. "
                                 "Die Übergabe ungeprüfter Eingaben ist riskant."))
    monkeypatch.setattr("litellm.completion", model)
    agent = Agent(settings)
    monkeypatch.setattr(agent, "_model_can_use_tools", lambda *a: False)
    monkeypatch.setattr(agent, "_council_turn", lambda *a, **kw: pytest.fail("council bypass"))
    try:
        result = agent.ask("/code-review o/r", stream=False, structured=False, online=True,
                           plugin_prompt="Prüfe den Code, nur belegte Befunde.")
        context = json.dumps(model.calls[0]["messages"], ensure_ascii=False)
        assert "os.system" in result.answer and "os.system" in context
        assert "GitHub-Prüfgrundlage" in context and agent.toolbox.untrusted_seen
    finally:
        agent.close()


def test_review_target_does_not_treat_pasted_code_as_repo_request():
    assert github_repo.review_target("/code-review o/r")["repo"] == "o/r"
    assert github_repo.review_target("/code-review ```python\na/b\n```") is None
    assert github_repo.review_target("Schau dir src/auth.py an") is None


def test_review_prompt_guides_to_real_code(settings):
    addons.install(settings, "github", pro=True)
    addons.install(settings, "code-review", pro=True)
    settings.github_token = TOKEN
    turn = plugins.match("/code-review o/r", settings, True)
    text = plugins.prompt(turn, turn.argument, settings, True)
    assert "action=review" in text and "start_line" in text


def test_review_discards_moving_pull_request(api):
    client, routes, _ = api
    seen = []

    def pull(request):
        seen.append(True)
        return {"head": {"sha": COMMIT if len(seen) == 1 else "c" * 40}}

    routes["/repos/o/r/pulls/12"] = pull
    routes["/repos/o/r/pulls/12/files"] = [
        {"filename": "src/auth.py", "status": "modified", "patch": "+code"}]
    result = addons.github_call(TOKEN, "review", repo="o/r#12", client=client)
    assert "geändert" in result["error"] and "os.system" not in json.dumps(result)
    assert len(seen) == 2


def test_private_fork_cannot_bypass_public_only_base_repo(api):
    client, routes, calls = api
    routes["/repos/o/r/pulls/12"] = {"head": {
        "sha": COMMIT, "repo": {"full_name": "o/private"}}}
    routes["/repos/o/private"] = {"private": True}
    result = addons.github_call(TOKEN, "review", repo="o/r#12", nur_oeffentlich=True,
                                client=client)
    assert "Quell-Fork" in result["error"]
    assert not any("/contents/" in r.url.path for r in calls)


def test_withdrawn_github_rights_discard_running_read(settings, monkeypatch):
    addons.install(settings, "github", pro=True)
    settings.github_token = TOKEN
    box = Toolbox(settings)

    def revoke(*a, **kw):
        addons.set_rights(settings, "github", {"inhalte": "nein"})
        return {"text": "old private source", "privat": True}

    monkeypatch.setattr(addons, "github_call", revoke)
    try:
        result = box.call("github", {"action": "datei", "repo": "o/r", "path": "src/auth.py"})
        assert "geändert" in result["error"] and "old private source" not in json.dumps(result)
    finally:
        box.close()


def test_malformed_login_does_not_store_a_token(settings, api):
    client, routes, _ = api
    addons.install(settings, "github", pro=True)
    routes["/user"] = {"not_login": "missing"}
    with pytest.raises(addons.AddOnError, match="Kontodaten"):
        addons.github_login(settings, TOKEN, client=client)
    assert not addons.github_token(settings)


def test_context_limits_preserve_source_identity():
    repo = "a" * 100 + "/" + "b" * 100
    path = "src/" + "x" * 280 + ".py"
    result = github_repo.bound({"repo": repo, "datei": path, "text": "line\n" * 1000,
                                "start_line": 1, "total_lines": 1000}, 1000)
    assert result["repo"] == repo and result["datei"] == path
    assert len(json.dumps(result, ensure_ascii=False)) <= 1000


def test_literal_repo_name_ending_in_git_is_not_changed():
    assert github_repo.target("o/literal.git")[0] == "o/literal.git"
