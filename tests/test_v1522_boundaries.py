"""15.2.2: Gegenproben fuer Zugriffsgrenzen, Quellen und parallele Schreibvorgaenge."""

import struct
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from aquaticy import (
    addons,
    cache,
    coworker_schedule,
    local_model,
    media,
    private_json,
    research,
    secure_devices,
    secure_nmap,
    secure_packets,
    webview,
)
from aquaticy import github_write as gw
from aquaticy.tools import Toolbox
from tests.test_v1500 import BASE, FakeBox, FakeGitHub


@pytest.fixture
def github_case(settings, monkeypatch):
    fake = FakeGitHub()
    client_type = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: client_type(
        *a, **{"transport": httpx.MockTransport(fake), **kw}))
    monkeypatch.setattr(addons, "_takt", lambda *a, **kw: None)
    addons.install(settings, "github", pro=False)
    settings.github_token = "ghp_" + "a" * 36
    box = Toolbox(settings)
    questions = []
    box.ask_handler = lambda question, choices: questions.append(question) or "ja"
    yield box, fake, questions
    box.close()


@pytest.mark.parametrize("answer,source", [
    ("https://shop.example/Private", "https://shop.example/private"),
    ("https://www.shop.example/p", "https://shop.example/p"),
    ("https://shop.example/p/", "https://shop.example/p"),
    ("https://shop.example/p?id=1&id=2", "https://shop.example/p?id=2&id=1"),
])
def test_f21_unread_urls_cannot_be_verified_through_unsafe_equivalence(answer, source):
    assert coworker_schedule.verified_offer_url(answer, [{"url": source}]) == ""


@pytest.mark.parametrize("path", [".github", ".github/workflows"])
def test_f22_deleting_workflow_parent_directories_is_also_protected(path):
    with pytest.raises(gw.WriteError):
        gw.check_changes([{"path": path, "data": None}], workflows_allowed=False)


def test_f23_missing_capabilities_do_not_leak_between_ollama_endpoints(monkeypatch):
    monkeypatch.setattr(local_model, "_FEHLT", {})
    monkeypatch.setattr(local_model, "ollama_capabilities", lambda *a: frozenset({"tools"}))
    local_model.note_missing("ollama_chat/probe", "tools")
    assert local_model.can("ollama_chat/probe", "tools", "http://other:11434") is True


def test_f24_the_default_branch_is_rechecked_after_confirmation(github_case, monkeypatch):
    box, fake, _ = github_case
    default = ["main"]
    original = type(fake).__call__

    def reply(self, request):
        if request.url.path == "/repos/o/r":
            return httpx.Response(200, json={"private": False, "default_branch": default[0]})
        return original(self, request)

    monkeypatch.setattr(type(fake), "__call__", reply)
    fake.refs["feature"] = BASE

    def approve(*args):
        default[0] = "feature"
        return "ja"

    box.ask_handler = approve
    result = box.call("github_write", {"action": "commit", "repo": "o/r", "branch": "feature",
                                       "message": "Fix", "files": [
                                           {"path": "a.py", "content": "safe"}]})
    assert result.get("error"), result
    assert not any(method == "PATCH" for method, _, _ in fake.writes())


def test_f25_pull_request_confirmation_discloses_the_body(github_case):
    box, _, questions = github_case
    result = box.call("github_write", {"action": "pull_request", "repo": "o/r", "branch": "fix",
                                       "title": "Fix", "body": "Text that will be published"})
    assert result.get("number")
    assert "Text that will be published" in questions[-1]


def test_f26_checkout_respects_the_branch_in_a_github_url(github_case, monkeypatch):
    box, _, _ = github_case
    box.github_vm_ready = lambda: True
    monkeypatch.setattr(box, "_sandbox", lambda: FakeBox())
    result = box.call("github_write", {"action": "checkout", "repo": "https://github.com/o/r/tree/dev"})
    assert result.get("ref") == "dev", result


def test_f27_unquoted_environment_passwords_are_not_published():
    assert gw.secret_problem(".env", b"PASSWORD=correctHorse_Battery42\n")


def test_f28_cache_key_components_are_not_ambiguous():
    assert cache.cache_key("x", "a\x1fb", "c") != cache.cache_key("x", "a", "b\x1fc")


def test_f29_all_branch_components_follow_git_lock_suffix_rules():
    assert not gw.valid_branch("feature.lock/sub")


def test_f30_absolute_commit_paths_are_rejected_instead_of_silently_rewritten(github_case):
    box, fake, _ = github_case
    result = box.call("github_write", {"action": "commit", "repo": "o/r", "branch": "fix",
                                       "message": "Fix", "files": [
                                           {"path": "/src/a.py", "content": "safe"}]})
    assert result.get("error") and not fake.writes(), result


def test_f31_concurrent_checkout_records_preserve_both_entries(settings, monkeypatch):
    first, second = Toolbox(settings), Toolbox(settings)
    entered, release, second_written = threading.Event(), threading.Event(), threading.Event()
    write = private_json.write

    def paused(path, value):
        if set(value) == {"/work/a"}:
            entered.set()
            assert release.wait(5)
        write(path, value)
        if "/work/b" in value:
            second_written.set()

    monkeypatch.setattr(private_json, "write", paused)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(first._github_checkout_merken, "/work/a", {"repo": "o/a"})
            assert entered.wait(5)
            b = pool.submit(second._github_checkout_merken, "/work/b", {"repo": "o/b"})
            second_written.wait(0.15)
            release.set()
            a.result(timeout=5)
            b.result(timeout=5)
        assert set(first._github_checkouts()) == {"/work/a", "/work/b"}
    finally:
        release.set()
        first.close()
        second.close()


def test_f32_upnp_does_not_probe_addresses_outside_the_granted_network(monkeypatch):
    destinations = []

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def setsockopt(self, *args):
            pass

        def settimeout(self, *args):
            pass

        def sendto(self, data, target):
            destinations.append(target[0])

        def recvfrom(self, size):
            raise TimeoutError

    clock = iter(range(20))
    monkeypatch.setattr(secure_devices.socket, "socket", lambda *args: Socket())
    monkeypatch.setattr(secure_devices.time, "monotonic", lambda: next(clock))
    secure_devices.upnp_gateways("192.168.1.1/32", "192.168.1.1", wait=0.5)
    assert destinations and set(destinations) == {"192.168.1.1"}


def test_f33_device_names_support_the_same_tailscale_scope_as_the_scanner():
    assert secure_devices.clean_known({"100.64.1.5": "Laptop"}) == {"100.64.1.5": "Laptop"}


def test_f34_deleting_one_chat_keeps_media_still_referenced_by_another(settings):
    store = cache.Cache(settings.db_path)
    identifier = media.save_snapshot(settings.data_dir, b"image", "image/png")
    meta = {"visuals": [{"media_id": identifier}]}
    store.add_history("a" * 32, "q", "a", meta)
    store.add_history("b" * 32, "q", "a", meta)
    store.delete_chat("a" * 32)
    assert media.load_snapshot(settings.data_dir, identifier) is not None


@pytest.mark.parametrize("timestamp", [float("nan"), float("inf"), 1e300])
def test_f35_invalid_persisted_timestamps_do_not_break_the_ui(timestamp):
    assert webview.moment_text(timestamp) == ""


def test_f36_research_cache_keeps_person_disambiguation():
    url = "https://de.wikipedia.org/wiki/Karl_Müller_(Politiker)"
    question = "Was weißt du über den Arzt Karl Müller?"
    assert not research.matches_subject(url, research.words(question), question)


def test_f37_negative_nmap_results_with_whitespace_are_not_vulnerabilities():
    xml = ('<nmaprun><host><address addrtype="ipv4" addr="192.168.1.2"/>'
           '<ports><port protocol="tcp" portid="80"><state state="open"/>'
           '<script id="http-vuln-test" output="State: NOT  VULNERABLE"/>'
           '</port></ports></host></nmaprun>')
    assert secure_nmap.parse(xml)[0]["ports"][0]["findings"] == []


@pytest.mark.parametrize("questions,with_fields", [(0, True), (1, False)])
def test_f38_dns_metadata_requires_an_actual_complete_question(questions, with_fields):
    question = b"\x03www\x07example\x03com\x00" + (b"\x00\x01\x00\x01" if with_fields else b"")
    dns = struct.pack("!HHHHHH", 1, 0, questions, 0, 0, 0) + question
    udp = struct.pack("!HHHH", 12345, 53, 8 + len(dns), 0) + dns
    ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), 0, 0, 64, 17, 0,
                     b"\xc0\xa8\x01\x02", b"\xc0\xa8\x01\x01")
    frame = b"\0" * 12 + b"\x08\x00" + ip + udp
    result = secure_packets.parse_frame(frame)
    assert result is not None and not result.get("dns"), result


def test_safe_environment_examples_and_noncredential_metadata_remain_allowed():
    content = b'AUTHOR=AliceSmith42\nPASSWORD=${PASSWORD}\nSECRET_KEY_FILE=./secret.key\n'
    assert gw.secret_problem(".env.example", content) == ""
    gw.check_changes([{"path": ".github/ISSUE_TEMPLATE/question.md", "data": b"Ask a question"}],
                     workflows_allowed=False)


def test_qualifiers_still_allow_learning_about_the_right_person():
    url = "https://de.wikipedia.org/wiki/Karl_Müller_(Politiker)"
    question = "Wer ist der Politiker Karl Müller?"
    assert research.matches_subject(url, research.words(question), question)


def test_actual_positive_nmap_results_are_kept():
    xml = ('<nmaprun><host><address addrtype="ipv4" addr="192.168.1.2"/>'
           '<ports><port protocol="tcp" portid="80"><state state="open"/>'
           '<script id="http-vuln-test" output="State: VULNERABLE"/>'
           '</port></ports></host></nmaprun>')
    assert secure_nmap.parse(xml)[0]["ports"][0]["findings"]


def test_checkout_branch_urls_keep_slashes_in_branch_names(github_case, monkeypatch):
    box, fake, _ = github_case
    original = type(fake).__call__

    def reply(self, request):
        if "/commits/" in request.url.path and not request.url.path.endswith("/commits/dev/sub"):
            return httpx.Response(404)
        return original(self, request)

    monkeypatch.setattr(type(fake), "__call__", reply)
    box.github_vm_ready = lambda: True
    monkeypatch.setattr(box, "_sandbox", lambda: FakeBox())
    result = box.call("github_write", {"action": "checkout", "repo": "https://github.com/o/r/tree/dev/sub"})
    assert result.get("ref") == "dev/sub", result


def test_a_pull_request_url_cannot_silently_check_out_the_default_branch(github_case):
    box, _, _ = github_case
    result = box.call("github_write", {"action": "checkout", "repo": "https://github.com/o/r/pull/7"})
    assert "error" in result and "ref" in result["error"]


def test_missing_capability_notes_are_private_to_the_profile_and_expire(monkeypatch):
    monkeypatch.setattr(local_model, "_FEHLT", {})
    clock = [1.0]
    monkeypatch.setattr(local_model.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(local_model, "ollama_capabilities", lambda *a: frozenset({"tools"}))
    model = "ollama_chat/profile-probe"
    local_model.note_missing(model, "tools", scope="one")
    assert local_model.can(model, "tools", scope="one") is False
    assert local_model.can(model, "tools", scope="two") is True
    clock[0] += local_model.CAPABILITY_TTL + 1
    assert local_model.can(model, "tools", scope="one") is True
