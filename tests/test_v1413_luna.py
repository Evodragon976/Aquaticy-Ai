"""14.1.3 Luna: Secure Pro ueberwacht, kennt Malware, prueft Pakete und wehrt per SSH ab.

Dazu: Aufgaben wie "Melde dich bei neuen Geraeten", Zeitplan wie bei Coworkern, nur Wichtiges
geht in Chat und Messenger. Die Einstellungen sind aufgeraeumt, und das Setup fragt nicht mehr
nach den Agenten.
"""

from __future__ import annotations

import re
import socket
import struct
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from aquaticy import (
    cli,
    lan,
    secure_defense,
    secure_knowledge,
    secure_packets,
    secure_pro,
    secure_tasks,
    web,
)
from aquaticy.agent import Agent
from aquaticy.cache import Cache
from aquaticy.tools import Toolbox
from tests.test_v1300_luna import server  # noqa: F401
from tests.test_v1401 import owner  # noqa: F401

NETZ = "192.168.1.0/24"


# -- Aufgaben ------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,trigger,host,port", [
    ("Melde dich, wenn ein neues Gerät ins Netz kommt", "new_device", "", 0),
    ("wenn sich ein neues gerät ins netz einloggt melde dich bitte", "new_device", "", 0),
    ("Tell me when a new device joins the network", "new_device", "", 0),
    ("Sag Bescheid, wenn 192.168.1.20 offline geht", "device_offline", "192.168.1.20", 0),
    ("Melde dich, wenn 192.168.1.20 wieder online ist", "device_online", "192.168.1.20", 0),
    ("Melde jeden Malware-Verdacht", "malware", "", 0),
    ("Warn mich bei einem Angriff oder Portscan", "attack", "", 0),
    ("Melde dich, wenn bei 192.168.1.5 Port 22 aufgeht", "new_port", "192.168.1.5", 22),
    ("Melde jeden Prüfhinweis", "any", "", 0),
])
def test_tasks_are_understood_without_a_model(text: str, trigger: str, host: str,
                                              port: int) -> None:
    aufgabe = secure_tasks.parse(text)
    assert (aufgabe["trigger"], aufgabe["host"], aufgabe["port"]) == (trigger, host, port)
    assert aufgabe["label"] == secure_tasks.TRIGGERS[trigger]
    assert re.fullmatch(r"[0-9a-f]{12}", aufgabe["id"])


@pytest.mark.parametrize("text,wort", [
    ("", "höchstens 300"),
    ("Mach mir einen Kaffee", "verstehe ich nicht"),
    ("Melde dich, wenn 8.8.8.8 offline geht", "Heimnetz"),
    ("Sag Bescheid, wenn der Drucker offline geht", "IP-Adresse"),
    ("Melde dich bei neuen Geräten " + "x" * 300, "höchstens 300"),
    ("Melde dich bei neuem Gerät\x00", "höchstens 300"),
])
def test_unclear_tasks_are_refused_with_a_reason(text: str, wort: str) -> None:
    with pytest.raises(ValueError, match=wort):
        secure_tasks.parse(text)


def test_tasks_match_only_their_event() -> None:
    neu = secure_tasks.parse("Melde neue Geräte")
    weg = secure_tasks.parse("Sag Bescheid, wenn 192.168.1.20 offline geht")
    angriff = secure_tasks.parse("Melde Angriffe")
    assert secure_tasks.matches(neu, {"kind": "new_device", "host": "192.168.1.3", "port": 0})
    assert not secure_tasks.matches(neu, {"kind": "malware", "host": "192.168.1.3", "port": 0})
    assert secure_tasks.matches(weg, {"kind": "device_offline", "host": "192.168.1.20"})
    assert not secure_tasks.matches(weg, {"kind": "device_offline", "host": "192.168.1.21"})
    for art in ("port_scan", "arp_spoof", "brute_force"):
        assert secure_tasks.matches(angriff, {"kind": art, "host": "", "port": 0})


def test_stored_tasks_are_checked_again() -> None:
    gut = secure_tasks.parse("Melde neue Geräte")
    sauber = secure_tasks.clean([gut, {"text": "Mach Kaffee"}, "kaputt",
                                 {**gut, "id": "../../x", "trigger": "any"}])
    assert len(sauber) == 2 and sauber[0]["id"] == gut["id"]
    assert sauber[1]["id"] != "../../x" and sauber[1]["trigger"] == "new_device"
    assert secure_tasks.clean("nein") == []


# -- Einstellungen in secure-pro.json -----------------------------------------------------------
def test_options_have_safe_defaults_and_are_validated(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Netz"):
        secure_pro.set_options(tmp_path, {"interval": 5})
    secure_pro.configure(tmp_path, NETZ)
    assert secure_pro.options(secure_pro.read(tmp_path)) == {
        "watch": True, "interval": 15, "packets": False, "vm": False, "tasks": []}
    for falsch in ({"interval": 7}, {"interval": "5"}, {"interval": True},
                   {"packets": "ja"}, {"vm": 1}, {"watch": None}):
        with pytest.raises(ValueError):
            secure_pro.set_options(tmp_path, falsch)
    token = secure_pro.config_token(secure_pro.read(tmp_path))
    neu = secure_pro.set_options(tmp_path, {"interval": 60, "packets": True, "vm": True,
                                            "watch": False})
    assert neu["interval"] == 60 and neu["packets"] and neu["vm"] and not neu["watch"]
    assert secure_pro.config_token(secure_pro.read(tmp_path)) == token, \
        "Zeitplan und Schalter verwerfen keine Ergebnisse"
    secure_pro.configure(tmp_path, NETZ, router="192.168.1.1")
    assert secure_pro.options(secure_pro.read(tmp_path))["interval"] == 60, "bleibt erhalten"


def test_tasks_are_added_and_removed(tmp_path: Path) -> None:
    secure_pro.configure(tmp_path, NETZ)
    aufgabe = secure_pro.add_task(tmp_path, "Melde neue Geräte")
    assert [t["id"] for t in secure_pro.options(secure_pro.read(tmp_path))["tasks"]] == [
        aufgabe["id"]]
    assert not secure_pro.remove_task(tmp_path, "000000000000")
    assert secure_pro.remove_task(tmp_path, aufgabe["id"])
    assert secure_pro.options(secure_pro.read(tmp_path))["tasks"] == []
    for _ in range(secure_tasks.MAX_TASKS):
        secure_pro.add_task(tmp_path, "Melde neue Geräte")
    with pytest.raises(ValueError, match="Höchstens 20"):
        secure_pro.add_task(tmp_path, "Melde neue Geräte")


def test_the_schedule_follows_the_settings(tmp_path: Path) -> None:
    watcher = secure_pro.Watcher(tmp_path, lambda text: True)
    secure_pro.configure(tmp_path, NETZ)
    assert watcher._wait_seconds() == 15 * 60
    secure_pro.set_options(tmp_path, {"interval": 1440})
    assert watcher._wait_seconds() == 1440 * 60
    secure_pro.set_options(tmp_path, {"watch": False})
    assert watcher._wait_seconds() is None, "aus: nur auf Anfrage"


# -- Nur Wichtiges meldet sich --------------------------------------------------------------------
def _beobachter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                geraete: list[lan.Device]) -> tuple[secure_pro.Watcher, list[str], list[str]]:
    monkeypatch.setattr(lan, "scan", lambda *a, **kw: list(geraete))
    from aquaticy import secure_network

    monkeypatch.setattr(secure_network, "neighbours", lambda subnet: [])
    nachrichten: list[str] = []
    chat: list[str] = []
    watcher = secure_pro.Watcher(tmp_path, lambda text: nachrichten.append(text) or True,
                                 lambda text: chat.append(text) or True)
    return watcher, nachrichten, chat


def test_only_important_findings_reach_chat_and_messenger(tmp_path, monkeypatch):
    secure_pro.configure(tmp_path, NETZ)
    geraete = [lan.Device("192.168.1.2", ports=[443])]
    watcher, nachrichten, chat = _beobachter(tmp_path, monkeypatch, geraete)
    watcher.tick()
    assert nachrichten == [] and chat == []
    geraete.append(lan.Device("192.168.1.3", ports=[80]))
    watcher.tick()
    assert nachrichten == [] and chat == [], "ein neues Geraet allein ist kein Alarm"
    assert "Neues Gerät: 192.168.1.3" in watcher.snapshot()["findings"]
    assert watcher.snapshot()["important"] == []
    geraete.append(lan.Device("192.168.1.4", ports=[4444]))
    watcher.tick()
    assert len(nachrichten) == 1 and nachrichten == chat
    assert "Port 4444" in nachrichten[0] and "Jede Abwehr braucht dein Ja" in nachrichten[0]
    assert any("4444" in item for item in watcher.snapshot()["important"])
    watcher.tick()
    assert len(nachrichten) == 1, "nicht doppelt"


def test_a_weak_malware_sign_stays_a_hint(tmp_path, monkeypatch):
    secure_pro.configure(tmp_path, NETZ)
    watcher, nachrichten, _ = _beobachter(tmp_path, monkeypatch,
                                          [lan.Device("192.168.1.2", ports=[6667])])
    watcher.tick()
    assert nachrichten == []
    assert any("6667" in item for item in watcher.snapshot()["findings"])


def test_tasks_report_new_and_missing_devices(tmp_path, monkeypatch):
    secure_pro.configure(tmp_path, NETZ)
    secure_pro.add_task(tmp_path, "Melde dich, wenn ein neues Gerät ins Netz kommt")
    secure_pro.add_task(tmp_path, "Sag Bescheid, wenn 192.168.1.2 offline geht")
    geraete = [lan.Device("192.168.1.2", ports=[443])]
    watcher, nachrichten, chat = _beobachter(tmp_path, monkeypatch, geraete)
    watcher.tick()
    assert nachrichten == []
    geraete.append(lan.Device("192.168.1.9", ports=[80]))
    watcher.tick()
    assert len(chat) == 1 and "Neues Gerät: 192.168.1.9" in chat[0]
    assert chat[0].count("192.168.1.9") == 1, "eine Meldung je Geraet"
    del geraete[0]
    watcher.tick()
    assert "192.168.1.2 antwortet nicht mehr" in chat[-1]


def test_a_failed_delivery_is_tried_again(tmp_path, monkeypatch):
    secure_pro.configure(tmp_path, NETZ)
    watcher, _, _ = _beobachter(tmp_path, monkeypatch, [lan.Device("192.168.1.2", ports=[23])])
    watcher.notify = lambda text: False
    watcher.report = None
    watcher.tick()
    assert watcher.announced == set()
    zugestellt: list[str] = []
    watcher.report = lambda text: zugestellt.append(text) or True
    watcher.tick()
    assert len(zugestellt) == 1 and watcher.announced


def test_scan_includes_malware_and_risk_ports(tmp_path, monkeypatch):
    secure_pro.configure(tmp_path, NETZ)
    gesehen: dict[str, Any] = {}
    monkeypatch.setattr(lan, "scan", lambda *a, **kw: gesehen.update(kw) or [])
    secure_pro.Watcher(tmp_path, lambda text: True).tick()
    ports = set(gesehen["ports"])
    assert {4444, 31337, 2375, 27017, 23, 3389} <= ports and len(ports) <= 128
    assert set(lan.FULL_PORTS) <= ports


def test_scan_rejects_bad_port_lists() -> None:
    for ports in ((), (0,), (70000,), tuple(range(1, 200))):
        with pytest.raises(ValueError):
            lan.scan("192.168.1.0/30", ports=ports, with_titles=False, with_names=False)


def test_packet_findings_flow_into_the_report(tmp_path, monkeypatch):
    secure_pro.configure(tmp_path, "192.168.1.0/24", router="192.168.1.1")
    secure_pro.set_options(tmp_path, {"packets": True})
    syn = [{"t": "tcp", "src": "192.168.1.66", "dst": "192.168.1.2", "sport": 40000,
            "dport": port, "syn": True, "ack": False} for port in range(1, 40)]
    monkeypatch.setattr(secure_packets, "capture", lambda seconds: syn)
    watcher, nachrichten, _ = _beobachter(tmp_path, monkeypatch,
                                          [lan.Device("192.168.1.2", ports=[443])])
    monkeypatch.setattr(secure_pro, "own_addresses", lambda router="": frozenset())
    watcher.tick()
    assert nachrichten and "Portscan" in nachrichten[0]
    assert "Kopfdaten" in watcher.snapshot()["packet_status"]


def test_missing_packet_rights_are_explained(tmp_path, monkeypatch):
    secure_pro.configure(tmp_path, NETZ)
    secure_pro.set_options(tmp_path, {"packets": True})

    def ohne(seconds: float) -> list[dict[str, Any]]:
        raise secure_packets.Unavailable("Die Paketprüfung braucht Root-Rechte oder CAP_NET_RAW.")

    monkeypatch.setattr(secure_packets, "capture", ohne)
    watcher, _, _ = _beobachter(tmp_path, monkeypatch, [lan.Device("192.168.1.2", ports=[443])])
    watcher.tick()
    assert "CAP_NET_RAW" in watcher.snapshot()["packet_status"]
    assert watcher.snapshot()["checked"] > 0, "der Netzscan laeuft trotzdem"


# -- Paket-Kopfdaten ----------------------------------------------------------------------------
def _eth(art: int, nutzlast: bytes) -> bytes:
    return b"\xff" * 6 + b"\x02\x00\x00\x00\x00\x01" + struct.pack("!H", art) + nutzlast


def _ipv4(src: str, dst: str, proto: int, rest: bytes) -> bytes:
    kopf = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(rest), 0, 0, 64, proto, 0,
                       socket.inet_aton(src), socket.inet_aton(dst))
    return kopf + rest


def test_frames_are_read_as_headers_only() -> None:
    arp = struct.pack("!HHBBH6s4s6s4s", 1, 0x0800, 6, 4, 2, bytes.fromhex("02aabbccdd01"),
                      socket.inet_aton("192.168.1.1"), b"\x00" * 6, socket.inet_aton("192.168.1.5"))
    assert secure_packets.parse_frame(_eth(0x0806, arp)) == {
        "t": "arp", "op": 2, "mac": "02:aa:bb:cc:dd:01", "ip": "192.168.1.1",
        "target": "192.168.1.5"}
    tcp = struct.pack("!HHIIBBHHH", 50000, 4444, 0, 0, 0x50, 0x02, 0, 0, 0)
    gelesen = secure_packets.parse_frame(_eth(0x0800, _ipv4("192.168.1.5", "10.0.0.1", 6, tcp)))
    assert gelesen == {"t": "tcp", "src": "192.168.1.5", "dst": "10.0.0.1", "sport": 50000,
                       "dport": 4444, "syn": True, "ack": False}
    frage = struct.pack("!HHHHHH", 1, 0x0100, 1, 0, 0, 0) + b"\x07example\x03com\x00" \
        + b"\x00\x01\x00\x01"
    udp = struct.pack("!HHHH", 53000, 53, 8 + len(frage), 0) + frage
    dns = secure_packets.parse_frame(_eth(0x0800, _ipv4("192.168.1.5", "192.168.1.1", 17, udp)))
    assert dns is not None and dns["dns"] == "example.com" and not dns["qr"]
    assert secure_packets.parse_frame(b"\x00" * 10) is None
    assert secure_packets.parse_frame(_eth(0x86DD, b"\x60" + b"\x00" * 40)) is None


def test_attacks_are_found_in_headers() -> None:
    def syn(src: str, dst: str, port: int) -> dict[str, Any]:
        return {"t": "tcp", "src": src, "dst": dst, "sport": 40000, "dport": port,
                "syn": True, "ack": False}

    records = [syn("192.168.1.66", "192.168.1.2", p) for p in range(1, 30)]
    records += [syn("192.168.1.67", f"192.168.1.{n}", 23) for n in range(10, 30)]
    records += [syn("192.168.1.68", "192.168.1.2", 22) for _ in range(30)]
    records += [syn("192.168.1.69", "93.184.216.34", 445)]
    records += [syn("192.168.1.70", "198.51.100.9", 31337)]
    records += [{"t": "arp", "op": 2, "mac": "02:00:00:00:00:99", "ip": "192.168.1.1"}]
    records += [{"t": "udp", "src": "192.168.1.1", "dst": "192.168.1.71", "sport": 53,
                 "dport": 53, "dns": f"x{n}.example", "qr": True, "nx": True}
                for n in range(30)]
    records += [{"t": "udp", "src": "192.168.1.72", "dst": "192.168.1.1", "sport": 5353,
                 "dport": 53, "dns": "qxzkvbtrplmnwshgd7k2.com", "qr": False, "nx": False}]
    events = secure_packets.analyze(records, NETZ, router="192.168.1.1",
                                    known_macs={"192.168.1.1": "02:00:00:00:00:01"})
    arten = {(e["kind"], e["level"]) for e in events}
    texte = " ".join(e["text"] for e in events)
    assert ("port_scan", "wichtig") in arten and "29 Ports" in texte
    assert "Port 23 bei 20 Geräten" in texte
    assert ("brute_force", "wichtig") in arten
    assert "WannaCry" in texte and "Back Orifice" in texte
    assert "Routers 192.168.1.1" in texte and "ARP-Spoofing" in texte
    assert "DGA" in texte and "qxzkvbtrplmnwshgd7k2.com" in texte


def test_own_checks_and_normal_traffic_are_no_alarm() -> None:
    eigene = [{"t": "tcp", "src": "192.168.1.10", "dst": "192.168.1.2", "sport": 40000,
               "dport": p, "syn": True, "ack": False} for p in range(1, 60)]
    normal = [{"t": "tcp", "src": "192.168.1.5", "dst": "142.250.0.1", "sport": 50000,
               "dport": 443, "syn": True, "ack": False},
              {"t": "udp", "src": "192.168.1.5", "dst": "192.168.1.1", "sport": 5000,
               "dport": 53, "dns": "www.wikipedia.org", "qr": False, "nx": False}]
    assert secure_packets.analyze(eigene + normal, NETZ,
                                  own=frozenset({"192.168.1.10"})) == []


def test_capture_needs_linux_and_rights(monkeypatch) -> None:
    monkeypatch.setattr(secure_packets.platform, "system", lambda: "Windows")
    with pytest.raises(secure_packets.Unavailable, match="Linux"):
        secure_packets.capture(1)
    monkeypatch.setattr(secure_packets.platform, "system", lambda: "Linux")

    def verboten(*args: Any) -> Any:
        raise PermissionError

    monkeypatch.setattr(secure_packets.socket, "socket", verboten)
    if hasattr(socket, "AF_PACKET"):
        with pytest.raises(secure_packets.Unavailable, match="CAP_NET_RAW"):
            secure_packets.capture(1)


# -- Wissen ---------------------------------------------------------------------------------------
def test_knowledge_explains_ports_malware_and_weaknesses() -> None:
    assert secure_knowledge.port_info(4444)["art"] == "verdächtig"
    assert "Ransomware" in secure_knowledge.port_info(3389)["text"]
    assert secure_knowledge.port_info(443) == {}
    treffer = secure_knowledge.lookup("Port 31337")["results"]
    assert treffer[0]["name"] == "Back Orifice"
    assert any("Mirai" in r.get("name", "") for r in secure_knowledge.lookup("mirai")["results"])
    assert any(r["art"] == "schwachstelle" for r in secure_knowledge.lookup("UPnP")["results"])
    assert "error" in secure_knowledge.lookup("  ")
    assert len(secure_knowledge.topics()["malware"]) >= 8


# -- Abwehr ---------------------------------------------------------------------------------------
def test_defense_builds_fixed_commands() -> None:
    sperre = secure_defense.build("block_port", host="192.168.1.20", port=4444, subnet=NETZ)
    assert "ufw deny 4444/tcp" in sperre["command"] and "iptables -I INPUT" in sperre["command"]
    auf = secure_defense.build("unblock_port", host="192.168.1.20", port=4444, subnet=NETZ)
    assert "ufw delete deny 4444/tcp" in auf["command"]
    ip = secure_defense.build("block_ip", host="192.168.1.20", address="192.168.1.66",
                              subnet=NETZ, router="192.168.1.1")
    assert "deny from 192.168.1.66" in ip["command"]
    win = secure_defense.build("block_port", system="windows", host="192.168.1.20", port=3389,
                               subnet=NETZ)
    assert win["command"].startswith("powershell") and "-LocalPort 3389" in win["command"]
    dienst = secure_defense.build("stop_service", host="192.168.1.20", service="telnet.socket",
                                  subnet=NETZ)
    assert dienst["command"] == "sudo -n systemctl disable --now telnet.socket"
    assert "ss -tulpn" in secure_defense.build("listeners", host="192.168.1.20",
                                               subnet=NETZ)["command"]


@pytest.mark.parametrize("kwargs,wort", [
    ({"action": "rm_rf"}, "Massnahme"),
    ({"action": "block_port", "port": 22}, "Port 22"),
    ({"action": "block_port", "port": "4444; reboot"}, "Port"),
    ({"action": "block_port", "port": 4444, "proto": "icmp"}, "Protokoll"),
    ({"action": "block_ip", "address": "192.168.1.1"}, "Router"),
    ({"action": "block_ip", "address": "192.168.1.20"}, "Router"),
    ({"action": "block_ip", "address": "192.168.1.10"}, "Router"),
    ({"action": "block_ip", "address": "8.8.8.8"}, "freigegebenen"),
    ({"action": "block_ip", "address": "192.168.1.5; reboot"}, "IP-Adresse"),
    ({"action": "stop_service", "service": "sshd"}, "SSH"),
    ({"action": "stop_service", "service": "x; reboot"}, "Dienstnamen"),
    ({"action": "listeners", "system": "beos"}, "System"),
    ({"action": "listeners", "host": "192.168.2.5"}, "außerhalb"),
])
def test_defense_refuses_dangerous_or_foreign_values(kwargs: dict[str, Any], wort: str) -> None:
    werte = {"host": "192.168.1.20", "subnet": NETZ, "router": "192.168.1.1",
             "own": frozenset({"192.168.1.10"}), **kwargs}
    with pytest.raises(ValueError, match=wort):
        secure_defense.build(werte.pop("action"), **werte)


def _box(settings, vm: dict[str, Any]) -> tuple[Toolbox, list[dict[str, Any]]]:
    box = Toolbox(settings)
    box.secure_mode = True
    box.secure_provider = lambda name, args: vm if name == "secure_vm" else {"allowed": True}
    aufrufe: list[dict[str, Any]] = []
    box.lan_ssh = lambda **kw: aufrufe.append(kw) or {"exit_code": 0}  # type: ignore[method-assign]
    return box, aufrufe


def test_defense_needs_the_vm_switch(settings) -> None:
    box, aufrufe = _box(settings, {"ok": False, "error": "Secure Pro darf die VM nicht nutzen."})
    try:
        ergebnis = box.call("secure_defend", {"action": "block_port", "host": "192.168.1.20",
                                              "user": "pi", "server_key": "x", "port": 4444})
        assert "VM nicht nutzen" in ergebnis["error"] and aufrufe == []
    finally:
        box.close()


def test_defense_runs_the_built_command_through_ssh(settings, monkeypatch) -> None:
    monkeypatch.setattr(secure_pro, "own_addresses", lambda router="": frozenset())
    box, aufrufe = _box(settings, {"ok": True, "subnet": NETZ, "router": "192.168.1.1"})
    try:
        ergebnis = box.call("secure_defend", {
            "action": "block_port", "host": "192.168.1.20", "user": "pi",
            "server_key": "ssh-ed25519 AAAA", "port": 4444, "command": "rm -rf /"})
        assert ergebnis["measure"].startswith("Eingehende Verbindungen")
        assert aufrufe[0]["action"] == "run" and "ufw deny 4444/tcp" in aufrufe[0]["command"]
        assert "rm -rf" not in aufrufe[0]["command"], "eigene Befehle gibt es nicht"
        assert box.call("secure_ssh", {"action": "inspect", "host": "10.0.0.5"})["error"]
        box.call("secure_ssh", {"action": "key"})
        assert aufrufe[-1] == {"action": "key"}
    finally:
        box.close()


def test_defense_tools_are_offered_only_when_allowed(settings, monkeypatch) -> None:
    agent = Agent(settings)
    try:
        agent.secure_pro = True
        agent.toolbox.secure_mode = True
        agent.toolbox.ask_handler = lambda question, options: "ja"
        monkeypatch.setattr(agent, "_model_can_use_tools", lambda: True)
        monkeypatch.setattr(agent, "_vm_can_start", lambda: True)
        vm = {"ok": True}
        agent.toolbox.secure_provider = lambda name, args: vm if name == "secure_vm" else {}
        settings.lan_enabled, settings.vm_lan = True, True
        namen = {s["function"]["name"] for s in agent.tools}
        assert {"secure_defend", "secure_ssh", "secure_knowledge"} <= namen
        assert "vm_run" not in namen and "lan_ssh" not in namen
        vm["ok"] = False
        assert "secure_defend" not in {s["function"]["name"] for s in agent.tools}
        vm["ok"] = True
        agent.toolbox.ask_handler = None
        assert "secure_defend" not in {s["function"]["name"] for s in agent.tools}
        assert not agent._ssh_ready(), "ohne Rueckfrage kein SSH"
    finally:
        agent.close()


# -- Server ---------------------------------------------------------------------------------------
def test_owner_sets_schedule_and_tasks(owner) -> None:  # noqa: F811
    session, settings = owner
    secure_pro.configure(settings.data_dir, NETZ)
    daten, status = web.feature_action(session, {"action": "options", "interval": 60,
                                                 "packets": True})
    assert status == 200 and daten["interval"] == 60 and daten["packets"]
    assert web.feature_action(session, {"action": "options", "interval": 2})[1] == 400
    assert web.feature_action(session, {"action": "options"})[1] == 400
    daten, status = web.feature_action(session, {"action": "task_add",
                                                 "text": "Melde neue Geräte"})
    assert status == 200 and daten["tasks"][0]["label"] == secure_tasks.TRIGGERS["new_device"]
    kennung = daten["task"]["id"]
    assert web.feature_action(session, {"action": "task_add", "text": "Kaffee"})[1] == 400
    assert web.feature_action(session, {"action": "task_remove", "id": kennung})[1] == 200
    assert web.feature_action(session, {"action": "task_remove", "id": kennung})[1] == 404
    assert web.feature_view(session)["intervals"] == list(secure_pro.INTERVALS)


def test_others_cannot_change_secure_pro(owner) -> None:  # noqa: F811
    session, settings = owner
    secure_pro.configure(settings.data_dir, NETZ)
    session.ultra = False
    for payload in ({"action": "options", "vm": True}, {"action": "task_add", "text": "x"}):
        assert web.feature_action(session, payload)[1] == 403
    assert secure_pro.options(secure_pro.read(settings.data_dir))["vm"] is False


def test_vm_use_needs_switch_and_network_rights(owner) -> None:  # noqa: F811
    session, settings = owner
    Cache(settings.db_path).mark_secure_chat(session.chat_id())
    secure_pro.configure(settings.data_dir, NETZ, router="192.168.1.1")
    assert web.secure_feature_tool(session, "secure_vm", {})["ok"] is False
    secure_pro.set_options(settings.data_dir, {"vm": True})
    assert "lokale Netz" in web.secure_feature_tool(session, "secure_vm", {})["error"]
    settings.lan_enabled, settings.vm_lan = True, True
    assert web.secure_feature_tool(session, "secure_vm", {}) == {
        "ok": True, "subnet": NETZ, "router": "192.168.1.1"}


def test_latest_secure_chat(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "db.sqlite")
    assert cache.latest_secure_chat() == ""
    cache.mark_secure_chat("alt")
    cache.add_history("alt", "a", "b")
    cache.mark_secure_chat("neu")
    cache.add_history("neu", "a", "b")
    assert cache.latest_secure_chat() == "neu"


# -- Setup ----------------------------------------------------------------------------------------
def test_setup_no_longer_asks_about_agents(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "_ensure_ollama", lambda **kw: True)
    monkeypatch.setattr(cli, "_ask_website", lambda **kw: {})
    monkeypatch.setattr(cli, "_vm_beim_start", lambda settings: None)
    monkeypatch.setattr(cli, "_messenger_beim_start", lambda settings: None)
    monkeypatch.setattr(cli, "_einzelkonto_einrichten", lambda settings: None)
    ziel = tmp_path / ".env"
    ergebnis = CliRunner().invoke(cli.app, ["setup", "--yes", "--no-probe", "--env-file",
                                            str(ziel)], input="1\n1\n\nKöln\n\n\n")
    assert ergebnis.exit_code == 0, ergebnis.output
    assert "Subagenten" not in ergebnis.output
    text = ziel.read_text()
    assert "AQUATICY_SUBAGENTS_AUTO=true" in text and "Köln" in text


# -- Oberflaeche ----------------------------------------------------------------------------------
def _ui() -> str:
    return (Path(web.__file__).parent / "webui.html").read_text(encoding="utf-8")


def test_settings_are_grouped() -> None:
    html = _ui()
    formular = html[html.index('<form id="settings">'):html.index('id="savenote"')]
    legenden = re.findall(r"<legend>(.*?)</legend>", formular)
    assert legenden == ["Konto", "Nutzung", "Speicher", "Gemeinsames Lernen", "Mitlesen",
                        "Auslastung · Ultra", "Ort &amp; Sprache", "Suche",
                        "Helfer &amp; Grenzen", "Gmail &amp; Kalender", "Zuhause &amp; Netz",
                        "Secure Pro", "virtual machine", "Messenger", "Dev settings"]

    def abschnitt(legende: str) -> str:
        start = formular.index(f"<legend>{legende}</legend>")
        return formular[start:formular.index("</fieldset>", start)]

    assert 'id="secure-setting"' in abschnitt("Secure Pro")
    for feld in ("secure-interval", "secure-watch", "secure-packets", "secure-vm",
                 "secure-task-text", "secure-important"):
        assert f'id="{feld}"' in abschnitt("Secure Pro"), feld
    assert 'id="secure-status"' not in html, "Status zeigt die Seite ohnehin laufend"
    assert 'id="voice-setting"' in abschnitt("Messenger")
    assert 'id="pw"' in abschnitt("Suche")
    assert "OpenSSH" in abschnitt("virtual machine") and "OpenSSH" not in abschnitt(
        "Zuhause &amp; Netz")
    dev = abschnitt("Dev settings")
    assert 'id="secure-setting"' not in dev and 'id="voice-setting"' not in dev
    assert dev.index('id="legalguard"') < dev.index('id="legal-rules"') < dev.index(
        'id="automodel"'), "die Leitplanken stehen bei ihren Regeln"
    assert formular.count('href="/privacy"') == 1, "der Datenschutz-Link stand doppelt da"
    assert "Ab Werk an." in " ".join(abschnitt("Helfer &amp; Grenzen").split())


def test_schedule_and_tasks_in_real_browser(server, monkeypatch):  # noqa: F811
    import json
    import os
    import shutil

    playwright = pytest.importorskip("playwright.sync_api")
    browser_path = shutil.which("chromium") or shutil.which("chromium-browser")
    if not browser_path:
        pytest.skip("Chromium fehlt")
    from tests.test_end_to_end import AGENT, SPRACHE, _req
    from tests.test_v1300_luna import _anlegen, _zustimmung

    monkeypatch.setattr(lan, "scan", lambda *a, **kw: [])
    consent = _zustimmung(server)
    status, headers, _ = _anlegen(server, consent)
    assert status == 200
    cookie = consent + "; " + headers["Set-Cookie"].split(";", 1)[0]
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=browser_path, headless=True,
                                    args=["--no-sandbox"])
        context = browser.new_context(user_agent=AGENT, viewport={"width": 1280, "height": 900},
                                      extra_http_headers={"Cookie": cookie,
                                                          "Accept-Language": SPRACHE})
        page = context.new_page()
        page.goto(f"http://127.0.0.1:{server}")
        page.locator("#btn-settings").click()
        page.locator('#secnav button:has-text("Secure Pro")').click()
        page.locator("#secure-setting").check()
        playwright.expect(page.locator("#secure-more")).to_be_hidden()
        page.locator("#secure-subnet").fill("192.168.1.0/24")
        page.locator("#secure-consent").check()
        page.locator("#secure-apply").click()
        playwright.expect(page.locator("#secure-more")).to_be_visible()
        playwright.expect(page.locator("#secure-watch")).to_be_checked()
        page.locator("#secure-interval").select_option("60")
        page.locator("#secure-task-text").fill("Melde dich, wenn ein neues Gerät ins Netz kommt")
        page.locator("#secure-task-add").click()
        playwright.expect(page.locator("#secure-task-note")).to_contain_text("Verstanden")
        playwright.expect(page.locator("#secure-tasks li")).to_have_count(1)
        page.locator("#secure-task-text").fill("Mach mir einen Kaffee")
        page.locator("#secure-task-add").click()
        playwright.expect(page.locator("#secure-task-note")).to_contain_text("verstehe ich nicht")
        page.locator("#secure-vm").check()
        playwright.expect(page.locator("#secure-vm-note")).to_contain_text("Auch ins lokale Netz")
        daten = json.loads(_req(server, "GET", "/api/features", cookie=cookie)[2])
        assert daten["interval"] == 60 and daten["vm"] and len(daten["tasks"]) == 1
        if os.environ.get("AQUATICY_SCREENSHOT"):
            page.locator("#secure-section").screenshot(path=os.environ["AQUATICY_SCREENSHOT"])
        page.locator("#secure-tasks li button").click()
        playwright.expect(page.locator("#secure-tasks li")).to_have_count(0)
        browser.close()
