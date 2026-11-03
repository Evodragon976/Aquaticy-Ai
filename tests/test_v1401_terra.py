"""Routervorschlag, bestaetigter Start und ehrliche Secure-Pro-Ergebnisse."""

import ipaddress
import shutil
import subprocess
import threading
from types import SimpleNamespace

import pytest

from aquaticy import lan, secure_pro, web
from aquaticy import network_router as router
from aquaticy.cache import Cache
from tests.test_end_to_end import AGENT, SPRACHE
from tests.test_v1300_luna import _anlegen, _zustimmung, server  # noqa: F401
from tests.test_v1401 import owner  # noqa: F401


def route_line(interface, destination, gateway, mask, metric=100):
    def hex_ip(value):
        return ipaddress.IPv4Address(value).packed[::-1].hex()

    return (f"{interface}\t{hex_ip(destination)}\t{hex_ip(gateway)}\t0003\t0\t0\t"
            f"{metric}\t{hex_ip(mask)}\t0\t0\t0")


def routes(prefix="255.255.255.0"):
    return "Iface Destination Gateway Flags RefCnt Use Metric Mask\n" + "\n".join([
        route_line("eth0", "0.0.0.0", "192.168.1.1", "0.0.0.0"),
        route_line("eth0", "192.168.1.0", "0.0.0.0", prefix),
    ])


@pytest.mark.parametrize("mask,expected", [("255.255.255.0", "192.168.1.0/24"),
                                           ("255.255.255.128", "192.168.1.0/25")])
def test_linux_route_uses_interface_mask_and_default_gateway(mask, expected):
    assert router.linux_route(routes(mask)) == ("192.168.1.1", expected)


def test_linux_route_caps_large_network_and_prefers_lower_metric():
    text = routes() + "\n" + "\n".join([
        route_line("eth1", "0.0.0.0", "10.2.3.1", "0.0.0.0", 10),
        route_line("eth1", "10.2.0.0", "0.0.0.0", "255.255.0.0"),
    ])
    assert router.linux_route(text) == ("10.2.3.1", "10.2.3.0/24")


def test_detection_only_reads_local_route_and_does_not_probe(monkeypatch):
    monkeypatch.setattr(router.platform, "system", lambda: "Linux")
    monkeypatch.setattr(router.Path, "read_text", lambda path: routes())
    monkeypatch.setattr(lan, "in_container", lambda: True)
    monkeypatch.setattr(lan, "port_open", lambda *args: pytest.fail("no consent"))
    result = router.detect()
    assert result["router"] == "192.168.1.1"
    assert "Container" in result["hint"] and result["subnet"] == "192.168.1.0/24"


@pytest.mark.parametrize("system,output", [
    ("Windows", "  0.0.0.0    0.0.0.0   192.168.2.1    192.168.2.5  25"),
    ("Darwin", "   gateway: 192.168.2.1\n interface: en0"),
])
def test_other_system_routes_have_bounded_fixed_commands(monkeypatch, system, output):
    monkeypatch.setattr(router.platform, "system", lambda: system)
    monkeypatch.setattr(lan, "in_container", lambda: False)

    def run(command, **kwargs):
        assert command[0] == "route" and kwargs["timeout"] == 3
        assert not kwargs.get("shell")
        return SimpleNamespace(returncode=0, stdout=output)

    monkeypatch.setattr(router.subprocess, "run", run)
    assert router.detect()["router"] == "192.168.2.1"


def test_missing_route_and_command_timeout_do_not_guess_router(monkeypatch):
    assert router.linux_route("Header\nmalformed\n" +
                              route_line("eth0", "0.0.0.0", "8.8.8.8", "0.0.0.0")) == ("", "")
    monkeypatch.setattr(router.platform, "system", lambda: "Darwin")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("route", 3)

    monkeypatch.setattr(router.subprocess, "run", timeout)
    assert router.detect()["router"] == ""


@pytest.mark.parametrize("address,subnet", [
    ("8.8.8.8", "192.168.1.0/24"), ("127.0.0.1", "192.168.1.0/24"),
    ("169.254.169.254", "192.168.1.0/24"), ("localhost", "192.168.1.0/24"),
    ("192.168.1.1;id", "192.168.1.0/24"), ("192.168.2.1", "192.168.1.0/24"),
    ("192.168.1.1", "192.168.0.0/16"), ("::1", "192.168.1.0/24"),
])
def test_router_probe_rejects_invalid_targets_before_socket_use(monkeypatch, address, subnet):
    monkeypatch.setattr(lan, "port_open", lambda *a: pytest.fail("invalid target"))
    with pytest.raises(ValueError):
        router.test(address, subnet)


def test_router_probe_tests_only_three_ports_and_reports_silence(monkeypatch):
    calls = []
    monkeypatch.setattr(lan, "port_open", lambda address, port: calls.append((address, port))
                        or port == 443)
    result = router.test("192.168.1.1", "192.168.1.0/24")
    assert result["ports"] == [443]
    assert set(calls) == {("192.168.1.1", p) for p in (80, 443, 53)}
    monkeypatch.setattr(lan, "port_open", lambda *a: False)
    with pytest.raises(ValueError, match="Keine Antwort"):
        router.test("192.168.1.1", "192.168.1.0/24")


def test_router_start_requires_owner_marked_chat_and_consent(owner, monkeypatch):  # noqa: F811
    session, settings = owner
    monkeypatch.setattr(router, "detect", lambda: {"router": "192.168.1.1"})
    monkeypatch.setattr(router, "test", lambda *a: pytest.fail("no consent"))
    assert web.feature_action(session, {"action": "detect"})[1] == 409
    Cache(settings.db_path).mark_secure_chat(session.chat_id())
    assert web.feature_action(session, {"action": "detect"})[0]["router"] == "192.168.1.1"
    assert web.feature_action(session, {"action": "router_test", "consent": False})[1] == 400
    session.account = None
    for action in ("detect", "router_test"):
        assert web.feature_action(session, {"action": action, "consent": True})[1] == 403


def test_tested_router_is_saved(owner, monkeypatch):  # noqa: F811
    session, settings = owner
    Cache(settings.db_path).mark_secure_chat(session.chat_id())
    payload = {"action": "router_test", "router": "192.168.1.1",
               "subnet": "192.168.1.0/24", "consent": True}
    monkeypatch.setattr(lan, "port_open", lambda *args: False)
    assert web.feature_action(session, payload)[1] == 400
    assert secure_pro.read(settings.data_dir) == {}
    monkeypatch.setattr(lan, "port_open", lambda *args: True)
    data, status = web.feature_action(session, payload)
    assert status == 200 and data["secure"]
    assert secure_pro.read(settings.data_dir)["router"] == "192.168.1.1"
    assert web.feature_action(session, {"action": []})[1] == 400


def test_positive_observations_do_not_claim_tls(tmp_path, monkeypatch):
    secure_pro.configure(tmp_path, "192.168.1.0/24")
    devices = [lan.Device("192.168.1.1", ports=[443])]
    monkeypatch.setattr(lan, "scan", lambda *a, **kw: devices)
    watcher = secure_pro.Watcher(tmp_path, lambda text: True)
    watcher.tick()
    snapshot = watcher.snapshot()
    assert snapshot["checked"] > 0
    assert any("Risikodienste" in text for text in snapshot["positives"])
    assert any("nicht geprüft" in text for text in snapshot["positives"])
    devices.clear()
    watcher.tick()
    assert any("Keine Geräte" in text for text in watcher.last_findings)
    assert not any("Risikodienste" in text for text in watcher.positives)


def test_secure_scan_skips_reverse_dns(tmp_path, monkeypatch):
    secure_pro.configure(tmp_path, "192.168.1.1/32")
    monkeypatch.setattr(lan, "hostname_of", lambda *a: pytest.fail("blocking reverse DNS"))
    monkeypatch.setattr(lan, "port_open", lambda address, port: port == 443)
    watcher = secure_pro.Watcher(tmp_path, lambda text: True)
    watcher.tick()
    assert watcher.last_checked > 0 and not watcher.last_findings


def test_secure_scan_reuses_all_port_results_without_nested_probe_pools(monkeypatch):
    calls = []

    def probe(address, port):
        calls.append((address, port))
        return port in {443, 23}

    monkeypatch.setattr(lan, "port_open", probe)
    monkeypatch.setattr(lan, "check_host", lambda *a, **kw: pytest.fail("duplicate probing"))
    found = lan.scan("192.168.1.0/30", quick=False, with_titles=False, with_names=False)
    assert len(calls) == 2 * len(lan.FULL_PORTS)
    assert len(set(calls)) == len(calls)
    assert [device.address for device in found] == ["192.168.1.1", "192.168.1.2"]
    assert all(device.ports == [23, 443] and "Telnet" in device.services for device in found)


def test_worker_can_be_enabled_later_and_publishes_errors(tmp_path, monkeypatch):
    watcher = secure_pro.Watcher(tmp_path, lambda text: True)
    watcher.start()
    assert watcher.thread is None
    checked = threading.Event()

    def scan(*args, **kwargs):
        checked.set()
        raise OSError("unreachable")

    monkeypatch.setattr(lan, "scan", scan)
    secure_pro.configure(tmp_path, "192.168.1.0/24")
    watcher.start()
    assert checked.wait(3)
    watcher.stop()
    assert "fehlgeschlagen" in watcher.snapshot()["error"]
    assert not watcher.snapshot()["scanning"]


def test_old_network_results_are_not_shown_for_new_scope(owner, monkeypatch):  # noqa: F811
    session, settings = owner
    secure_pro.configure(settings.data_dir, "192.168.1.0/24")
    monkeypatch.setattr(lan, "scan", lambda *a, **kw: [lan.Device("192.168.1.1", ports=[443])])
    watcher = secure_pro.Watcher(settings.data_dir, lambda text: True)
    monkeypatch.setattr(web, "SECURE_WATCHER", watcher)
    watcher.tick()
    assert web.feature_view(session)["checked"] > 0
    secure_pro.configure(settings.data_dir, "192.168.2.0/24")
    assert web.feature_view(session)["checked"] == 0
    assert web.feature_view(session)["positives"] == []


@pytest.mark.parametrize("width", [1280, 390])
def test_automatic_router_setup_and_live_results_in_browser(
    server, monkeypatch, width,  # noqa: F811
):
    playwright = pytest.importorskip("playwright.sync_api")
    browser_path = shutil.which("chromium") or shutil.which("chromium-browser")
    if not browser_path:
        pytest.skip("Chromium fehlt")
    monkeypatch.setattr(router, "detect", lambda: {
        "router": "192.168.1.1", "subnet": "192.168.1.0/24", "hint": "Erkannter Router"})
    scan_gate = threading.Event()

    def scan(*args, **kwargs):
        assert scan_gate.wait(10)
        return [lan.Device("192.168.1.1", ports=[443])]

    monkeypatch.setattr(lan, "scan", scan)
    monkeypatch.setattr(lan, "port_open", lambda *a: True)
    watcher = secure_pro.Watcher(web.get_settings().data_dir, lambda text: True)
    monkeypatch.setattr(web, "SECURE_WATCHER", watcher)
    consent = _zustimmung(server)
    status, headers, _ = _anlegen(server, consent)
    assert status == 200
    cookie = consent + "; " + headers["Set-Cookie"].split(";", 1)[0]
    try:
        with playwright.sync_playwright() as p:
            browser = p.chromium.launch(executable_path=browser_path, headless=True,
                                       args=["--no-sandbox"])
            context = browser.new_context(user_agent=AGENT,
                                          viewport={"width": width, "height": 900},
                                          extra_http_headers={"Cookie": cookie,
                                                              "Accept-Language": SPRACHE})
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{server}")
            if width < 600:
                page.locator("#btn-side").click()
            page.locator("#btn-settings").click()
            page.locator("#secure-setting").check()
            playwright.expect(page.locator("#secure-router")).to_have_value("192.168.1.1")
            playwright.expect(page.locator("#secure-subnet")).to_have_value("192.168.1.0/24")
            page.locator("#secure-test").click()
            playwright.expect(page.locator("#secure-note")).to_contain_text("Bestätige")
            assert secure_pro.read(watcher.directory) == {}
            page.locator("#secure-consent").check()
            page.locator("#secure-test").click()
            playwright.expect(page.locator("#secure-note")).to_contain_text("ist an")
            page.locator("#secure-router").fill("192.168.1.254")
            scan_gate.set()
            playwright.expect(page.locator("#secure-positive")).to_contain_text(
                "Zertifikate wurden nicht geprüft", timeout=15000)
            playwright.expect(page.locator("#secure-router")).to_have_value("192.168.1.254")
            playwright.expect(page.locator("#secure-checked")).to_contain_text("Letzte")
            page.locator("#secure-disable").click()
            playwright.expect(page.locator("#secure-note")).to_contain_text("ist aus")
            assert secure_pro.read(watcher.directory) == {}
            browser.close()
    finally:
        scan_gate.set()
        watcher.stop()
