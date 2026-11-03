"""Lokale Standardroute lesen und nur bestaetigte private Router testen."""

from __future__ import annotations

import contextlib
import ipaddress
import platform
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aquaticy import lan


def private_address(value: str) -> str:
    address = ipaddress.IPv4Address(value.strip())
    if not lan.is_private_net(ipaddress.IPv4Network(f"{address}/32")):
        raise ValueError("Gib eine private IPv4-Adresse für den Router ein.")
    return str(address)


def linux_route(text: str) -> tuple[str, str]:
    routes: list[tuple[str, str, int, int, int]] = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 8:
            continue
        try:
            destination, gateway_num, flags, metric, mask = (
                int(parts[1], 16), int(parts[2], 16), int(parts[3], 16),
                int(parts[6]), int(parts[7], 16))
            if not flags & 1:
                continue
            ip = str(ipaddress.IPv4Address(gateway_num.to_bytes(4, "little")))
            routes.append((parts[0], ip, destination, mask, metric))
        except (ValueError, OverflowError):
            continue
    defaults = sorted((r for r in routes if r[2] == 0 and r[3] == 0), key=lambda r: r[4])
    for interface, gateway, _, _, _ in defaults:
        try:
            address = private_address(gateway)
        except ValueError:
            continue
        networks = []
        for device, _, destination, mask, _ in routes:
            if device != interface or not mask:
                continue
            try:
                network = ipaddress.IPv4Network((
                    str(ipaddress.IPv4Address(destination.to_bytes(4, "little"))),
                    str(ipaddress.IPv4Address(mask.to_bytes(4, "little")))))
            except (ValueError, OverflowError):
                continue
            if ipaddress.IPv4Address(address) in network and lan.is_private_net(network):
                networks.append(network)
        prefix = max((n.prefixlen for n in networks), default=24)
        return address, str(ipaddress.IPv4Network(f"{address}/{max(prefix, 24)}", strict=False))
    return "", ""


def detect() -> dict[str, str]:
    gateway, subnet = "", ""
    system = platform.system()
    if system == "Linux":
        with contextlib.suppress(OSError):
            gateway, subnet = linux_route(Path("/proc/net/route").read_text())
    elif system in {"Windows", "Darwin"}:
        command = (["route", "print", "-4"] if system == "Windows"
                   else ["route", "-n", "get", "default"])
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=3,
                                    check=False)
            pattern = (r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+([\d.]+)"
                       if system == "Windows" else r"^\s*gateway:\s*([\d.]+)")
            matches = re.findall(pattern, result.stdout, re.M) if result.returncode == 0 else []
            for candidate in matches:
                try:
                    gateway = private_address(candidate)
                    subnet = str(ipaddress.IPv4Network(f"{gateway}/24", strict=False))
                    break
                except ValueError:
                    continue
        except (OSError, subprocess.TimeoutExpired):
            pass
    hint = ("Vorschlag aus der Standardroute des Aquaticy-Servers. Prüfe, ob es dein Heimnetz ist."
            if gateway else "Keinen Router erkannt. Trage die private Router-IP und dein Netz ein.")
    if gateway and lan.in_container():
        hint += " Aquaticy läuft in einem Container. Die Route kann zum Container-Netz gehören."
    return {"router": gateway, "subnet": subnet, "hint": hint}


def test(address: str, subnet: str) -> dict[str, object]:
    address = private_address(address)
    network = lan.parse_subnet(subnet)
    if network.num_addresses > 256 or ipaddress.IPv4Address(address) not in network:
        raise ValueError("Der Router muss im freigegebenen Netz mit höchstens "
                         "256 Adressen liegen.")
    ports = (443, 80, 53)
    with ThreadPoolExecutor(max_workers=3) as pool:
        answers = list(pool.map(lambda port: lan.port_open(address, port), ports))
    found = [port for port, answered in zip(ports, answers, strict=True) if answered]
    if not found:
        raise ValueError("Keine Antwort auf TCP 443, 80 oder 53. "
                         "Prüfe Router-IP und Erreichbarkeit. "
                         "Ein gesperrter Port bedeutet nicht, dass der Router unsicher ist.")
    return {"router": address, "subnet": str(network), "ports": found}
