"""Begrenzte Nachbartabelle und lesende Dienstpruefungen im freigegebenen Netz."""

from __future__ import annotations

import ipaddress
import platform
import re
import socket
import ssl
import subprocess
import time
from pathlib import Path
from typing import Any

from aquaticy import lan
from aquaticy.network_router import private_address

MAC = re.compile(r"\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b", re.I)
IP = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")


def _response(connection: socket.socket, *, ssh: bool = False) -> bytes:
    output = bytearray()
    deadline = time.monotonic() + 1.5
    while len(output) < 4096:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if hasattr(connection, "settimeout"):
            connection.settimeout(remaining)
        chunk = connection.recv(min(1024, 4096 - len(output)))
        if not chunk:
            break
        output.extend(chunk)
        if ssh:
            if any(line.startswith(b"SSH-") and line.endswith(b"\n")
                   for line in output.splitlines(keepends=True)):
                break
        elif b"\r\n\r\n" in output or b"\n\n" in output:
            break
    return bytes(output)


def neighbours(subnet: str) -> list[dict[str, Any]]:
    network = lan.parse_subnet(subnet)
    try:
        if platform.system() == "Linux":
            text = Path("/proc/net/arp").read_text(encoding="ascii", errors="replace")
        else:
            command = ["arp", "-an"] if platform.system() == "Darwin" else ["arp", "-a"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=3,
                                    check=False)
            text = result.stdout if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return []
    found = {}
    for line in text.splitlines()[:4096]:
        address, mac = IP.search(line), MAC.search(line)
        if not address or not mac:
            continue
        try:
            ip = ipaddress.IPv4Address(address.group())
        except ValueError:
            continue
        value = mac.group().lower().replace("-", ":")
        if ip not in network or (network.prefixlen < 31 and ip in (
                network.network_address, network.broadcast_address)):
            continue
        if int(value[:2], 16) & 1 or value == "00:00:00:00:00:00":
            continue
        found[str(ip)] = {"address": str(ip), "mac": value, "ports": [],
                          "active": False, "source": "Nachbartabelle"}
    return list(found.values())[:256]


def inspect(subnet: str, host: str) -> dict[str, Any]:
    address = private_address(host)
    network = lan.parse_subnet(subnet)
    if network.num_addresses > 256 or ipaddress.IPv4Address(address) not in network:
        raise ValueError("Das Gerät liegt außerhalb des freigegebenen Prüfbereichs.")
    device = lan.check_host(address, (22, 80, 443, 8080, 8443),
                            with_title=False, with_names=False)
    result: dict[str, Any] = {"address": address, "ports": device.ports if device else [],
                              "observations": [], "limitations": (
                                  "Keine Anmeldung, keine Angriffe und keine Fernprüfung "
                                  "von Dateien. Banner können falsch oder veraltet sein.")}
    if not device:
        result["observations"].append("Keine Antwort auf die geprüften Dienstports.")
        return result
    if 22 in device.ports:
        try:
            with socket.create_connection((address, 22), timeout=1.5) as connection:
                banner = _response(connection, ssh=True).decode("ascii", "replace")
            identification = next((line for line in banner.splitlines()
                                   if line.startswith("SSH-")), "")
            if identification:
                result["ssh_banner"] = identification.strip()[:200]
        except OSError:
            result["observations"].append("SSH-Banner konnte nicht gelesen werden.")
    for port in (443, 8443):
        if port not in device.ports:
            continue
        try:
            context = ssl.create_default_context()
            with (socket.create_connection((address, port), timeout=1.5) as connection,
                  context.wrap_socket(connection, server_hostname=address) as tls):
                result["observations"].append(
                    f"Port {port}: Zertifikat für die IP erfolgreich geprüft, {tls.version()}.")
        except ssl.SSLCertVerificationError:
            result["observations"].append(
                f"Port {port}: Zertifikat für die IP nicht verifizierbar. "
                "Im Heimnetz kann es selbst signiert sein. Das belegt keinen Angriff.")
        except OSError:
            result["observations"].append(f"Port {port}: TLS-Prüfung nicht abgeschlossen.")
    for port in (80, 8080):
        if port not in device.ports:
            continue
        try:
            with socket.create_connection((address, port), timeout=1.5) as connection:
                connection.sendall((f"HEAD / HTTP/1.0\r\nHost: {address}\r\n"
                                    "Connection: close\r\n\r\n").encode("ascii"))
                header = _response(connection).decode("latin1")
            lines = header.split("\r\n\r\n", 1)[0].splitlines()
            status = re.match(r"HTTP/\d\.\d (\d{3})", lines[0]) if lines else None
            if status:
                result["observations"].append(f"Port {port}: HTTP antwortet, "
                                              f"Status {status.group(1)}.")
                for line in lines[1:]:
                    if line.lower().startswith("server:"):
                        result["observations"].append(f"Selbst gemeldeter Server: {line[7:167]}")
            else:
                result["observations"].append(f"Port {port}: Kein vollständiger HTTP-Status.")
        except OSError:
            result["observations"].append(f"Port {port}: HTTP-Prüfung nicht abgeschlossen.")
    return result
