"""Freigabeentzug, begrenzte Prozesse, Paketdaten und vollstaendige Warnungen."""

import socket
import struct
import subprocess
import sys

import pytest

from aquaticy import secure_defense, secure_nmap, secure_packets, secure_pro, secure_tasks, web
from aquaticy.cache import Cache
from aquaticy.tools import Toolbox
from tests.test_v1401 import owner  # noqa: F401
from tests.test_v1402_sol import SERVER_KEY, ssh_box  # noqa: F401
from tests.test_v1413_luna import _eth, _ipv4
from tests.test_v1413_terra import NETZ, XML


@pytest.mark.parametrize("change", ["scope", "router", "disabled", "network"])
def test_secure_ssh_rechecks_exact_grant_after_confirmation(
        ssh_box, monkeypatch, change):  # noqa: F811
    toolbox, box = ssh_box
    toolbox.secure_mode = True
    grant = {"ok": True, "subnet": NETZ, "router": "192.168.1.1"}
    toolbox.secure_provider = lambda name, args: grant if name == "secure_vm" else {}
    monkeypatch.setattr(secure_pro, "own_addresses", lambda *a: frozenset())

    def revoke(*args):
        if change == "scope":
            grant["subnet"] = "192.168.1.0/25"
        elif change == "router":
            grant["router"] = "192.168.1.254"
        elif change == "disabled":
            grant["ok"] = False
        else:
            box.netz_offen = False
        return "ja"

    toolbox.ask_handler = revoke
    result = toolbox.call("secure_defend", {"action": "listeners", "host": "192.168.1.2",
                                            "user": "pi", "server_key": SERVER_KEY})
    assert "error" in result and box.calls == []


def test_secure_ssh_rechecks_grant_after_vm_start(ssh_box, monkeypatch):  # noqa: F811
    toolbox, box = ssh_box
    toolbox.secure_mode = True
    grant = {"ok": True, "subnet": NETZ, "router": ""}
    toolbox.secure_provider = lambda *a: grant

    def ensure():
        grant["subnet"] = "192.168.2.0/24"
        return box.name

    monkeypatch.setattr(box, "ensure", ensure)
    result = toolbox.call("secure_ssh", {"action": "inspect", "host": "192.168.1.2"})
    assert "error" in result and box.calls == []


def test_custom_ssh_port_cannot_be_blocked(ssh_box, monkeypatch):  # noqa: F811
    toolbox, box = ssh_box
    toolbox.secure_mode = True
    toolbox.secure_provider = lambda *a: {"ok": True, "subnet": NETZ, "router": ""}
    monkeypatch.setattr(secure_pro, "own_addresses", lambda *a: frozenset())
    result = toolbox.call("secure_defend", {"action": "block_port", "host": "192.168.1.2",
                                            "port": 2222, "ssh_port": 2222})
    assert "SSH-Port" in result["error"] and not box.calls


def test_firewalld_block_and_unblock_do_not_change_existing_port_allowances(tmp_path):
    folder = tmp_path / "bin"
    folder.mkdir()
    log = tmp_path / "calls"
    sudo = folder / "sudo"
    sudo.write_text('#!/bin/sh\nshift\nexec "$@"\n')
    sudo.chmod(0o700)
    firewall = folder / "firewall-cmd"
    firewall.write_text(f'#!{sys.executable}\nimport sys\n'
                        f'with open({str(log)!r}, "a") as f: f.write(repr(sys.argv[1:])+"\\n")\n')
    firewall.chmod(0o700)
    for action in ("block_port", "unblock_port"):
        command = secure_defense.build(action, host="192.168.1.2", subnet=NETZ, port=4444)
        subprocess.run(["/bin/sh", "-c", command["command"]], check=True,
                       env={"PATH": str(folder)}, timeout=5)
    all_calls = log.read_text().splitlines()
    assert all_calls.count("['--state']") == 2
    calls = [call for call in all_calls if call != "['--state']"]
    assert len(calls) == 2 and "--add-rich-rule=" in calls[0]
    assert "--remove-rich-rule=" in calls[1]
    assert "--add-port=" not in str(calls) and "--remove-port=" not in str(calls)


@pytest.mark.parametrize("subnet,host", [("127.0.0.0/24", "127.0.0.1"),
                                       ("169.254.1.0/24", "169.254.1.1"),
                                       ("8.8.8.0/24", "8.8.8.8")])
def test_all_private_scope_validators_reject_special_and_public_ranges(subnet, host):
    with pytest.raises(ValueError):
        secure_nmap.targets_in(subnet, [host])
    with pytest.raises(ValueError):
        secure_defense.build("listeners", host=host, subnet=subnet)
    with pytest.raises(ValueError):
        secure_tasks.parse(f"Melde dich, wenn {host} offline geht")


def test_tailscale_scopes_work_consistently_and_tasks_cannot_leave_scope(tmp_path):
    subnet, host = "100.100.1.0/24", "100.100.1.2"
    assert secure_nmap.targets_in(subnet, [host]) == [host]
    assert secure_tasks.parse(f"Melde dich, wenn {host} offline geht")["host"] == host
    secure_pro.configure(tmp_path, subnet)
    assert secure_pro.add_task(tmp_path, f"Melde dich, wenn {host} offline geht")["host"] == host
    with pytest.raises(ValueError, match="außerhalb"):
        secure_pro.add_task(tmp_path, "Melde dich, wenn 192.168.1.2 offline geht")


def test_nmap_filters_unrequested_hosts_and_invalid_ports(monkeypatch):
    xml = XML.replace('</nmaprun>', '<host><address addr="8.8.8.8" addrtype="ipv4"/>'
                      '</host><host><address addr="192.168.1.9" addrtype="ipv4"/></host>'
                      '</nmaprun>').replace('portid="22"', 'portid="70000"').replace(
                          'state="closed"', 'state="open"')
    monkeypatch.setattr(secure_nmap.shutil, "which", lambda *a: "/fake/nmap")
    monkeypatch.setattr(secure_nmap, "_execute", lambda *a: xml)
    result = secure_nmap.run(NETZ, ["192.168.1.5"])
    assert [h["address"] for h in result["hosts"]] == ["192.168.1.5"]
    assert all(1 <= p["port"] <= 65535 for h in result["hosts"] for p in h["ports"])


@pytest.mark.parametrize("reason", ["timeout", "revoked", "output"])
def test_nmap_process_is_killed_and_reaped_on_limits(monkeypatch, reason):
    real_popen = subprocess.Popen
    processes = []

    def spawn(*args, **kwargs):
        assert kwargs["stdin"] == subprocess.DEVNULL and not kwargs.get("shell")
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(secure_nmap.subprocess, "Popen", spawn)
    monkeypatch.setattr(secure_nmap, "MAX_OUTPUT", 128)
    code = "import time; time.sleep(5)"
    if reason == "output":
        code = "import sys,time; sys.stdout.write('x'*1024); sys.stdout.flush(); time.sleep(5)"
    calls = []

    def allowed():
        calls.append(True)
        return reason != "revoked" or len(calls) < 2

    expected = {"timeout": "zu lange", "revoked": "entzogen", "output": "zu groß"}[reason]
    with pytest.raises(secure_nmap.NmapError, match=expected):
        secure_nmap._execute([sys.executable, "-c", code], 0.2, allowed)
    assert len(processes) == 1 and processes[0].poll() is not None


def test_nmap_success_and_xml_limit_are_real(monkeypatch):
    assert secure_nmap._execute([sys.executable, "-c", "print('<nmaprun/>')"], 5, None).strip() \
        == '<nmaprun/>'
    monkeypatch.setattr(secure_nmap, "MAX_OUTPUT", 10)
    with pytest.raises(secure_nmap.NmapError, match="zu groß"):
        secure_nmap.parse('<nmaprun/>' + ' ' * 10)


def test_disabling_nmap_during_chat_scan_discards_result(owner, monkeypatch):  # noqa: F811
    session, settings = owner
    Cache(settings.db_path).mark_secure_chat(session.chat_id())
    secure_pro.configure(settings.data_dir, NETZ)
    secure_pro.set_options(settings.data_dir, {"nmap": True})

    def execute(subnet, targets, mode, *, allowed):
        assert allowed()
        secure_pro.set_options(settings.data_dir, {"nmap": False})
        assert not allowed()
        return {"hosts": secure_nmap.parse(XML)}

    monkeypatch.setattr(secure_nmap, "run", execute)
    assert "error" in web.secure_feature_tool(session, "secure_nmap", {"host": "192.168.1.5"})


def tcp_frame(src="192.168.1.2", dst="192.168.1.1"):
    tcp = struct.pack("!HHIIBBHHH", 50000, 4444, 0, 0, 0x50, 0x02, 0, 0, 0)
    return _eth(0x0800, _ipv4(src, dst, 6, tcp))


@pytest.mark.parametrize("change", ["ihl", "length", "fragment", "tcp"])
def test_malformed_ip_and_fragment_payloads_cannot_forge_tcp_headers(change):
    frame = bytearray(tcp_frame())
    if change == "ihl":
        frame[14] = 0x44
    elif change == "length":
        frame[16:18] = struct.pack("!H", 10)
    elif change == "fragment":
        frame[20:22] = struct.pack("!H", 1)
    else:
        frame[46] = 0x10
    assert secure_packets.parse_frame(bytes(frame)) is None


def test_invalid_arp_and_unterminated_dns_are_rejected():
    arp = struct.pack("!HHBBH6s4s6s4s", 2, 0x0800, 6, 4, 2, b"\x02" * 6,
                      socket.inet_aton("192.168.1.1"), b"\x00" * 6,
                      socket.inet_aton("192.168.1.5"))
    assert secure_packets.parse_frame(_eth(0x0806, arp)) is None
    assert secure_packets._dns_name(b"\x07example\x03com", 0) == ""


def test_capture_keeps_only_scoped_metadata_and_closes_socket(monkeypatch):
    frames = iter([tcp_frame("10.0.0.1", "10.0.0.2"), tcp_frame()])

    class Socket:
        closed = False

        def settimeout(self, timeout):
            pass

        def recv(self, size):
            return next(frames)

        def close(self):
            self.closed = True

    sock = Socket()
    monkeypatch.setattr(secure_packets.platform, "system", lambda: "Linux")
    monkeypatch.setattr(secure_packets.socket, "socket", lambda *a: sock)
    records = secure_packets.capture(1, 1, subnet=NETZ)
    assert sock.closed and len(records) == 1 and records[0]["src"] == "192.168.1.2"


def test_capture_stops_when_permission_changes(monkeypatch):
    granted = [True]

    class Socket:
        closed = False
        received = 0

        def settimeout(self, timeout):
            pass

        def recv(self, size):
            self.received += 1
            granted[0] = False
            return tcp_frame()

        def close(self):
            self.closed = True

    sock = Socket()
    monkeypatch.setattr(secure_packets.platform, "system", lambda: "Linux")
    monkeypatch.setattr(secure_packets.socket, "socket", lambda *a: sock)
    secure_packets.capture(60, subnet=NETZ, allowed=lambda: granted[0])
    assert sock.closed and sock.received == 1


def test_revoked_packet_grant_prevents_next_network_scan(tmp_path, monkeypatch):
    secure_pro.configure(tmp_path, NETZ)
    secure_pro.set_options(tmp_path, {"packets": True})

    def capture(seconds, *, subnet, allowed):
        assert subnet == NETZ and allowed()
        (tmp_path / "secure-pro.json").unlink()
        assert not allowed()
        return []

    monkeypatch.setattr(secure_packets, "capture", capture)
    monkeypatch.setattr("aquaticy.secure_network.neighbours", lambda *a: [])
    monkeypatch.setattr("aquaticy.lan.scan", lambda *a, **kw: pytest.fail("grant revoked"))
    watcher = secure_pro.Watcher(tmp_path, lambda *a: pytest.fail("stale notification"))
    assert watcher.tick() == [] and watcher.last_checked == 0


def test_large_alert_batches_are_delivered_without_truncation(tmp_path):
    messages = []
    watcher = secure_pro.Watcher(tmp_path, lambda text: messages.append(text) or True)
    lines = [f"Befund {i}: " + "x" * 400 for i in range(20)]
    assert watcher._deliver(lines, False)
    assert len(messages) > 1 and all(len(m) <= 2900 for m in messages)
    assert ''.join(m.removeprefix('[Aquaticy Secure Pro]\n') for m in messages) == '\n'.join(lines)
    watcher.notify = lambda text: text != messages[-1]
    assert not watcher._deliver(lines, False)


@pytest.mark.parametrize("tool", ["secure_advisories", "secure_read_advisory"])
def test_observed_dns_names_do_not_leave_in_public_research(settings, monkeypatch, tool):
    box = Toolbox(settings)
    domain = "qxzkvbtrplmnwshgd7k2.example.com"
    box.secure_mode = True
    box.untrusted_seen = True
    box.secure_provider = lambda *a: {"allowed": True, "domains": [domain]}
    url = "https://vendor.example/report?domain=" + domain
    box._secure_sources.add(url)
    monkeypatch.setattr(box, "web_search", lambda *a, **kw: pytest.fail("private DNS search"))
    monkeypatch.setattr(box, "fetch_page", lambda *a: pytest.fail("private DNS URL"))
    try:
        arguments = {"query": domain} if tool == "secure_advisories" else {"url": url}
        assert box.call(tool, arguments)["skipped_reason"] == "private_data"
        box.secure_provider = lambda *a: {"allowed": True, "domains": []}
        assert box.call(tool, arguments)["skipped_reason"] == "private_data"
    finally:
        box.close()


def test_dns_names_from_status_are_registered_before_public_research(settings, monkeypatch):
    box = Toolbox(settings)
    box.secure_mode = True
    box.secure_provider = lambda *a: {"events": [{"dns_names": ["personal-domain.example"]}]}
    monkeypatch.setattr(box, "web_search", lambda *a, **kw: pytest.fail("private DNS search"))
    try:
        box.call("secure_status", {})
        assert box.call("secure_advisories", {"query": "personal-domain.example"})[
            "skipped_reason"] == "private_data"
    finally:
        box.close()
