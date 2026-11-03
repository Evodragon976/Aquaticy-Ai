"""Abwehr fuer Secure Pro: feste Befehle, die ueber SSH aus der VM laufen.

Das Modell waehlt nur eine Massnahme und ihre Werte. Den Befehl baut dieser Code aus
festen Vorlagen: Port sperren, Adresse sperren, Dienst stoppen, offene Dienste zeigen --
und jede Sperre wieder aufheben. Jeder Befehl braucht dein Ja (aquaticy/tools.py lan_ssh).
Der Router, dieser Rechner und das Zielgeraet selbst werden nie gesperrt.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any

ACTIONS: dict[str, str] = {
    "listeners": "Offene Dienste und ihre Programme zeigen (nur lesen).",
    "block_port": "Eingehende Verbindungen auf einen Port sperren.",
    "unblock_port": "Die Sperre eines Ports aufheben.",
    "block_ip": "Ein Gerät aus dem Heimnetz aussperren.",
    "unblock_ip": "Die Sperre eines Geräts aufheben.",
    "stop_service": "Einen Dienst stoppen und beim Start auslassen.",
}
SYSTEMS = ("linux", "windows")
_UNIT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,79}")


def _linux_port(port: int, proto: str, block: bool) -> str:
    if block:
        return (f"if command -v ufw >/dev/null 2>&1; then sudo -n ufw deny {port}/{proto}; "
                f"elif command -v firewall-cmd >/dev/null 2>&1; then "
                f"sudo -n firewall-cmd --add-port={port}/{proto} --remove-port={port}/{proto} "
                f">/dev/null 2>&1; sudo -n firewall-cmd --add-rich-rule='rule port "
                f"port=\"{port}\" protocol=\"{proto}\" drop'; "
                f"else sudo -n iptables -I INPUT -p {proto} --dport {port} -j DROP; fi")
    return (f"if command -v ufw >/dev/null 2>&1; then sudo -n ufw delete deny {port}/{proto}; "
            f"elif command -v firewall-cmd >/dev/null 2>&1; then "
            f"sudo -n firewall-cmd --remove-rich-rule='rule port port=\"{port}\" "
            f"protocol=\"{proto}\" drop'; "
            f"else sudo -n iptables -D INPUT -p {proto} --dport {port} -j DROP; fi")


def _linux_ip(address: str, block: bool) -> str:
    if block:
        return (f"if command -v ufw >/dev/null 2>&1; then sudo -n ufw insert 1 deny from "
                f"{address}; elif command -v firewall-cmd >/dev/null 2>&1; then "
                f"sudo -n firewall-cmd --add-rich-rule='rule family=\"ipv4\" source "
                f"address=\"{address}\" drop'; "
                f"else sudo -n iptables -I INPUT -s {address} -j DROP; fi")
    return (f"if command -v ufw >/dev/null 2>&1; then sudo -n ufw delete deny from {address}; "
            f"elif command -v firewall-cmd >/dev/null 2>&1; then "
            f"sudo -n firewall-cmd --remove-rich-rule='rule family=\"ipv4\" source "
            f"address=\"{address}\" drop'; "
            f"else sudo -n iptables -D INPUT -s {address} -j DROP; fi")


def _windows(script: str) -> str:
    return f'powershell -NoProfile -NonInteractive -Command "{script}"'


def build(action: str, *, system: str = "linux", host: str, port: Any = 0,
          proto: str = "tcp", address: str = "", service: str = "", subnet: str,
          router: str = "", own: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Baut den Befehl fuer eine Abwehr-Massnahme.

    Raises:
        ValueError: Bei unbekannter Massnahme oder Werten ausserhalb der Grenzen.
    """
    if action not in ACTIONS:
        raise ValueError("Massnahme: " + ", ".join(ACTIONS) + ".")
    if system not in SYSTEMS:
        raise ValueError("System: linux oder windows.")
    network = ipaddress.IPv4Network(subnet)
    ziel = ipaddress.IPv4Address(host)
    if ziel not in network:
        raise ValueError("Das Gerät liegt außerhalb des freigegebenen Netzes.")
    data: dict[str, Any] = {"action": action, "system": system, "host": str(ziel),
                            "label": ACTIONS[action]}
    if action in ("block_port", "unblock_port"):
        try:
            nummer = int(port)
        except (TypeError, ValueError) as exc:
            raise ValueError("Nenne einen Port zwischen 1 und 65535.") from exc
        if not 1 <= nummer <= 65535:
            raise ValueError("Nenne einen Port zwischen 1 und 65535.")
        if proto not in ("tcp", "udp"):
            raise ValueError("Protokoll: tcp oder udp.")
        if nummer == 22 and action == "block_port":
            raise ValueError("Port 22 sperrt Secure Pro nicht: Sonst kommt auch die Abwehr "
                             "nicht mehr auf das Gerät.")
        data.update(port=nummer, proto=proto)
        sperren = action == "block_port"
        if system == "linux":
            data["command"] = _linux_port(nummer, proto, sperren)
        else:
            name = f"Aquaticy Secure Pro {proto.upper()} {nummer}"
            data["command"] = _windows(
                f"New-NetFirewallRule -DisplayName '{name}' -Direction Inbound -Protocol "
                f"{proto.upper()} -LocalPort {nummer} -Action Block" if sperren else
                f"Remove-NetFirewallRule -DisplayName '{name}'")
    elif action in ("block_ip", "unblock_ip"):
        try:
            fremd = ipaddress.IPv4Address(str(address).strip())
        except ValueError as exc:
            raise ValueError("Nenne die IP-Adresse des Geräts, das gesperrt werden soll.") from exc
        if fremd not in network:
            raise ValueError("Secure Pro sperrt nur Geräte im freigegebenen Netz.")
        geschuetzt = {str(ziel), router, *own}
        if action == "block_ip" and str(fremd) in geschuetzt:
            raise ValueError("Den Router, diesen Rechner oder das Gerät selbst sperrt "
                             "Secure Pro nie.")
        data["address"] = str(fremd)
        sperren = action == "block_ip"
        if system == "linux":
            data["command"] = _linux_ip(str(fremd), sperren)
        else:
            name = f"Aquaticy Secure Pro {fremd}"
            data["command"] = _windows(
                f"New-NetFirewallRule -DisplayName '{name}' -Direction Inbound "
                f"-RemoteAddress {fremd} -Action Block" if sperren else
                f"Remove-NetFirewallRule -DisplayName '{name}'")
    elif action == "stop_service":
        name = str(service or "").strip()
        if not _UNIT.fullmatch(name) or name.lower().startswith(("ssh", "sshd", "openssh")):
            raise ValueError("Nenne einen gültigen Dienstnamen. SSH stoppt Secure Pro nie.")
        data["service"] = name
        data["command"] = (f"sudo -n systemctl disable --now {name}" if system == "linux"
                           else _windows(f"Stop-Service -Name '{name}'; Set-Service -Name "
                                         f"'{name}' -StartupType Disabled"))
    else:
        data["command"] = ("ss -tulpn 2>/dev/null || netstat -tulpn 2>/dev/null"
                           if system == "linux" else
                           _windows("Get-NetTCPConnection -State Listen | Select-Object "
                                    "LocalAddress,LocalPort,OwningProcess"))
    return data
