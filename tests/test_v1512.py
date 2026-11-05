"""15 bestaetigte Regressionen: GitHub, VM-Grenzen, Secure Pro und Serverprozesse."""

import base64
import io
import json
import shlex
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from aquaticy import addons, old_server, secure_pro
from aquaticy import github_write as gw
from aquaticy.tools import Toolbox
from tests.test_v1500 import BASE, FakeBox, FakeGitHub

TOKEN = "ghp_" + "a" * 36


@pytest.fixture
def github_case(settings, monkeypatch):
    fake = FakeGitHub()
    client_type = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: client_type(
        *a, **{"transport": httpx.MockTransport(fake), **kw}))
    monkeypatch.setattr(addons, "_takt", lambda *a, **kw: None)
    addons.install(settings, "github", pro=False)
    settings.github_token = TOKEN
    box = Toolbox(settings)
    box.ask_handler = lambda *a: "ja"
    yield box, fake
    box.close()


def test_f01_unrelated_process_with_aquaticy_in_arguments_is_not_a_server():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)", "Aquaticy"])
    try:
        assert not old_server.is_aquaticy(child.pid)
    finally:
        child.terminate()
        child.wait(timeout=5)


@pytest.mark.skipif(not Path('/proc').is_dir(), reason="Linux-Prozesszustand erforderlich")
def test_f02_a_terminated_child_counts_as_stopped_before_its_parent_reaps_it(monkeypatch):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
    monkeypatch.setattr(old_server, "is_aquaticy", lambda pid: pid == child.pid)
    try:
        assert old_server.stop(child.pid, wait=0.4)
    finally:
        child.wait(timeout=5)


def test_f03_a_transferred_repository_can_be_checked_out(github_case, monkeypatch):
    box, fake = github_case
    original = type(fake).__call__

    def respond(self, request):
        if request.url.path == "/repos/old/r":
            return httpx.Response(301, headers={"location": "https://api.github.com/repos/o/r"})
        if request.url.path == "/repos/o/r":
            return httpx.Response(200, json={"private": False, "full_name": "o/r",
                                             "default_branch": "main"})
        return original(self, request)

    monkeypatch.setattr(type(fake), "__call__", respond)
    box.github_vm_ready = lambda: True
    monkeypatch.setattr(box, "_sandbox", lambda: FakeBox())
    result = box.call("github_write", {"action": "checkout", "repo": "old/r"})
    assert result.get("repo") == "o/r" and result.get("sha") == BASE, result


def test_f04_private_checkout_requires_consent_before_public_research(github_case, monkeypatch):
    box, fake = github_case
    fake.private = True
    box.github_vm_ready = lambda: True
    monkeypatch.setattr(box, "_sandbox", lambda: FakeBox())
    assert box.call("github_write", {"action": "checkout", "repo": "o/r"}).get("dir")
    box.ask_handler = None
    monkeypatch.setattr(box, "web_search", lambda **kw: {"leaked": True})
    result = box.call("web_search", {"query": "internal project details"})
    assert result.get("skipped_reason") == "private_data", result


def test_f05_revoking_github_access_stops_the_remaining_commit_requests(github_case, monkeypatch):
    box, fake = github_case
    original = type(fake).__call__

    def respond(self, request):
        response = original(self, request)
        if request.url.path.endswith("/git/blobs"):
            addons.set_rights(box.settings, "github", {"inhalte": "ja"})
        return response

    monkeypatch.setattr(type(fake), "__call__", respond)
    result = box.call("github_write", {"action": "commit", "repo": "o/r", "branch": "fix",
                                       "message": "Fix", "files": [
                                           {"path": "a.py", "content": "print(1)"}]})
    assert result.get("error") and len(fake.writes()) == 1, (result, fake.writes())


@pytest.mark.parametrize("kind", ["write", "write_error", "archive"])
def test_f06_network_limits_apply_while_reading_instead_of_after_buffering(monkeypatch, kind):
    consumed = []
    chunk = b"x" * (1024 * 1024)

    class Body(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(6):
                consumed.append(1)
                yield chunk

    monkeypatch.setattr(gw, "MAX_TARBALL", len(chunk) * 2)
    monkeypatch.setattr(gw, "MAX_RESPONSE", len(chunk) * 2, raising=False)
    status = 500 if kind == "write_error" else 200
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, stream=Body())
    )) as client, pytest.raises(gw.WriteError):
        if kind == "archive":
            gw.download_tarball(client, {}, "o/r", BASE)
        else:
            gw.Api(client, {}, lambda host: None).send("POST", "/repos/o/r/git/blobs", {})
    assert len(consumed) <= 3, consumed


def test_f07_compressed_archives_have_an_expanded_size_limit(tmp_path):
    archive = tmp_path / "repo.tar.gz"
    data = b"\0" * (33 * 1024 * 1024)
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo("root/large.bin")
        member.size = len(data)
        tar.addfile(member, io.BytesIO(data))
    result = subprocess.run([sys.executable, "-c", gw.EXTRACT, str(archive), str(tmp_path / "r")],
                            capture_output=True, timeout=15, check=False)
    assert result.returncode != 0
    assert not (tmp_path / "r" / "large.bin").exists()


def test_f08_manifest_hashes_large_files_without_loading_them_whole(tmp_path):
    (tmp_path / "large.bin").write_bytes(b"x" * (8 * 1024 * 1024))
    wrapper = ("import atexit,sys,tracemalloc\ntracemalloc.start()\n"
               "atexit.register(lambda: print(tracemalloc.get_traced_memory()[1], "
               "file=sys.stderr))\n" + gw.MANIFEST)
    result = subprocess.run([sys.executable, "-c", wrapper, str(tmp_path),
                             json.dumps(list(gw.SKIP)), "write"],
                            capture_output=True, text=True, timeout=15, check=True)
    assert json.loads(result.stdout)["files"] == 1
    assert int(result.stderr.strip()) < 3 * 1024 * 1024


def test_f09_changes_during_push_are_not_marked_as_already_committed(
    github_case, monkeypatch, tmp_path,
):
    box, fake = github_case
    root = tmp_path / "repo"
    root.mkdir()
    file = root / "a.py"
    file.write_text("old")

    class LocalBox:
        def run(self, command, timeout=0):
            result = subprocess.run(shlex.split(command), capture_output=True, text=True,
                                    timeout=10, check=False)
            return SimpleNamespace(exit_code=result.returncode, stdout=result.stdout)

        def get_bytes(self, path, max_bytes):
            return Path(path).read_bytes()

    vm = LocalBox()
    manifest_command = shlex.join([sys.executable, "-c", gw.MANIFEST, str(root),
                                   json.dumps(list(gw.SKIP))])
    assert vm.run(manifest_command + " write").exit_code == 0
    box._github_checkout_merken(str(root), {"repo": "o/r", "sha": BASE, "branch": ""})
    monkeypatch.setattr(gw, "vm_dir", lambda name: str(root))
    monkeypatch.setattr(box, "_sandbox", lambda: vm)
    box.github_vm_ready = lambda: True
    file.write_text("first")
    box.ask_handler = lambda *a: file.write_text("late edit") and "ja"
    result = box.call("github_write", {"action": "push", "repo": "o/r", "branch": "fix",
                                       "message": "Fix"})
    assert result.get("commit"), result
    blob = next(c[2] for c in fake.writes() if c[1].endswith("/git/blobs"))
    assert base64.b64decode(blob["content"]) == b"first"
    remaining = json.loads(vm.run(manifest_command + " diff").stdout)["changes"]
    assert [entry["path"] for entry in remaining] == ["a.py"], remaining


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-32", "utf-32-be"])
def test_f10_encoded_text_cannot_bypass_the_secret_check(encoding):
    assert gw.secret_problem("settings.txt", f'API_KEY="{TOKEN}"'.encode(encoding))


@pytest.mark.parametrize("field", ["commit_message", "pr_title"])
def test_f11_outbound_metadata_cannot_publish_credentials(github_case, field):
    box, fake = github_case
    if field == "commit_message":
        args = {"action": "commit", "branch": "fix", "message": TOKEN,
                "files": [{"path": "a.py", "content": "safe"}]}
    else:
        args = {"action": "pull_request", "branch": "fix", "title": TOKEN, "body": "safe"}
    result = box.call("github_write", {"repo": "o/r", **args})
    assert result.get("error") and not fake.writes(), result


def test_f12_upnp_observations_from_the_previous_network_are_discarded(settings, monkeypatch):
    from aquaticy import lan, secure_network

    secure_pro.configure(settings.data_dir, "192.168.1.0/24", router="192.168.1.1")
    watcher = secure_pro.Watcher(settings.data_dir, notify=lambda text: None)
    watcher._configuration = secure_pro.config_token(secure_pro.read(settings.data_dir))
    watcher._upnp = (time.time(), ["192.168.1.1"])
    secure_pro.configure(settings.data_dir, "10.0.0.0/24", router="10.0.0.1")
    secure_pro.set_options(settings.data_dir, {"nmap": True})
    monkeypatch.setattr(lan, "scan", lambda *a, **kw: [])
    monkeypatch.setattr(secure_network, "neighbours", lambda *a: [])
    monkeypatch.setattr(watcher, "_nmap", lambda *a: [])
    monkeypatch.setattr("aquaticy.secure_devices.upnp_gateways", lambda *a, **kw: [])
    watcher.tick()
    assert not any("192.168.1.1" in text for text in watcher.last_findings)


def test_f13_a_finishing_scan_cannot_recreate_history_after_disable(settings):
    secure_pro.configure(settings.data_dir, "192.168.1.0/24")
    watcher = secure_pro.Watcher(settings.data_dir, notify=lambda text: None)
    config = secure_pro.read(settings.data_dir)
    (settings.data_dir / "secure-pro.json").unlink()
    watcher._remember({"risk": {"kind": "risk_port", "level": "wichtig", "text": "risk"}},
                      secure_pro.options(config))
    assert not secure_pro.history_path(settings.data_dir).exists()


@pytest.mark.parametrize("state", [
    {"events": None, "scores": []},
    {"events": [], "scores": [["bad timestamp", "bad score"]]},
    {"events": [], "scores": [[1, float("nan")], [2, True], [3, 1000]]},
])
def test_f14_corrupt_history_cannot_crash_the_next_scan(settings, state):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    secure_pro.history_path(settings.data_dir).write_text(json.dumps(state))
    assert secure_pro.read_history(settings.data_dir) == {"events": [], "scores": []}


def test_f15_comparison_pagination_keeps_files_that_github_only_sends_on_page_one():
    files = [{"filename": f"file{i}.py", "status": "modified"} for i in range(30)]

    def fetch(route, **params):
        return {"files": files if params.get("page") == 1 else [], "commits": []}

    first = addons._github_action(fetch, "vergleich", "o/r", 0, "", "fix", "open", "",
                                   base="main", page=1)
    second = addons._github_action(fetch, "vergleich", "o/r", 0, "", "fix", "open", "",
                                    base="main", page=2)
    assert first["next_page"] == 2
    assert [f["datei"] for f in second["dateien"]] == [f"file{i}.py" for i in range(20, 30)]
    assert second["next_page"] is None


@pytest.mark.parametrize("command,expected", [
    (["python3", "-m", "aquaticy.cli", "web"], True),
    (["python3.12", "-u", "-m", "aquaticy.cli", "web", "--lan"], True),
    (["python3", "-c", "pass", "aquaticy", "web"], False),
    (["echo", "-m", "aquaticy.cli", "web"], False),
    (["python3", "-m", "/tmp/aquaticy.cli", "web"], False),
    (["/usr/bin/aquaticy", "/tmp/web"], False),
    (["/usr/bin/aquaticy", "chat", "web"], False),
])
def test_f01_command_recognition_accepts_only_actual_server_invocations(command, expected):
    assert old_server._ist_server(command) is expected


def test_f05_redirects_stop_after_access_is_revoked():
    allowed = [True]
    calls = []

    def reply(request):
        calls.append(request.url.path)
        allowed[0] = False
        return httpx.Response(301, headers={"location": "https://api.github.com/repos/new/r"})

    with (httpx.Client(transport=httpx.MockTransport(reply)) as client,
          pytest.raises(gw.WriteError, match="Freigabe")):
        gw.Api(client, {}, lambda host: None, allowed=lambda: allowed[0]).get("/repos/old/r")
    assert calls == ["/repos/old/r"]


@pytest.mark.parametrize("data", [b"plain text", b"\xff\x00image bytes", "Öffnen".encode("utf-16")])
def test_f10_safe_binary_and_encoded_files_remain_allowed(data):
    assert gw.secret_problem("safe.txt", data) == ""


@pytest.mark.parametrize("field", ["branch", "path", "long_message", "long_title"])
def test_f11_other_metadata_and_truncation_cannot_hide_credentials(github_case, field):
    box, fake = github_case
    args = {"repo": "o/r", "action": "commit", "branch": "fix", "message": "Fix",
            "files": [{"path": "a.py", "content": "safe"}]}
    if field == "branch":
        args["branch"] = TOKEN
    elif field == "path":
        args["files"] = [{"path": TOKEN + ".py", "content": "safe"}]
    elif field == "long_message":
        args["message"] = "x" * 3990 + TOKEN
    else:
        args = {"repo": "o/r", "action": "pull_request", "branch": "fix",
                "title": "x" * 240 + TOKEN, "body": "safe"}
    result = box.call("github_write", args)
    assert result.get("error") and not fake.writes(), result


def test_f13_disable_and_history_write_are_serialized(settings, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from aquaticy import secure_devices

    secure_pro.configure(settings.data_dir, "192.168.1.0/24")
    watcher = secure_pro.Watcher(settings.data_dir, notify=lambda text: True)
    entered, release, disabling = threading.Event(), threading.Event(), threading.Event()

    def score(*args):
        entered.set()
        assert release.wait(5)
        return 100, "A"

    def disable():
        disabling.set()
        secure_pro.disable(settings.data_dir)

    monkeypatch.setattr(secure_devices, "score", score)
    with ThreadPoolExecutor(max_workers=2) as pool:
        writing = pool.submit(watcher._remember, {}, secure_pro.options(
            secure_pro.read(settings.data_dir)))
        assert entered.wait(5)
        off = pool.submit(disable)
        assert disabling.wait(5)
        release.set()
        writing.result(timeout=5)
        off.result(timeout=5)
    assert secure_pro.read(settings.data_dir) == {}
    assert not secure_pro.history_path(settings.data_dir).exists()


def test_f14_invalid_event_values_and_large_timestamps_are_discarded(settings):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    state = {"events": [{"t": float("nan"), "text": "bad", "level": "wichtig"}],
             "scores": [[10 ** 500, 100]]}
    secure_pro.history_path(settings.data_dir).write_text(json.dumps(state))
    assert secure_pro.read_history(settings.data_dir) == {"events": [], "scores": []}
