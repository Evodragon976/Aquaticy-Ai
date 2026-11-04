"""Secure Pro: Geraete erkennen, benennen, bewerten -- und UPnP am Router finden (14.4.4).

Der Hersteller kommt aus den ersten drei Bytes der Hardware-Adresse (OUI). Die Liste ist klein
und fest; ein Treffer ist ein Hinweis, kein Beweis. Zufaellige Adressen (Handys und Laptops
mit privater WLAN-Adresse) haben keinen Hersteller. Der Sicherheitswert fasst die Befunde
in einer Zahl zusammen -- als Orientierung, nicht als Zertifikat.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import time
from typing import Any

# Hersteller nach OUI. Nur verbreitete Heimgeraete, ohne Anspruch auf Vollstaendigkeit.
VENDORS: dict[str, tuple[str, str]] = {}
for _hersteller, _art, _prefixe in (
    ("AVM (FRITZ!)", "Router oder Repeater",
     "00040e 246511 3ca62f 7cff4d c80e14 2c91ab 3810d5 e0286d 444e6d 989bcb dc396f 5c4979"),
    ("Raspberry Pi", "Kleinrechner", "b827eb dca632 e45f01 d83add 28cdc1 2ccf67"),
    ("Espressif", "Smart-Home-Gerät",
     "240ac4 30aea4 84cca8 a4cf12 bcddc2 cc50e3 ecfabc 600194 5ccf7f 3c71bf 246f28 8caab5 "
     "c82b96 483fda 7c9ebd"),
    ("Amazon", "Echo, Fire TV oder Kindle", "44650d 6854fd f0272d 74c246 fc65de 0c47c9"),
    ("Google", "Nest oder Chromecast", "f4f5d8 546009 1cf29a d86c63"),
    ("Hikvision", "Kamera", "4419b6 bcad28 c056e3 4cbd8f 54c415"),
    ("Dahua", "Kamera", "3cef8c 9002a9 e0508b 4c11bf"),
    ("TP-Link", "Router, Repeater oder Steckdose", "50c7bf 98dac4 ec086b f4f26d c006c3 6032b1"),
    ("Synology", "NAS", "001132"),
    ("Ubiquiti", "Netzwerkgerät", "24a43c 788a20 f09fc2 fcecda 7483c2"),
    ("Sonos", "Lautsprecher", "000e58 5caafd 949f3e b8e937 48a6b8"),
    ("Philips Hue (Signify)", "Smart-Home-Gerät", "001788 ecb5fa"),
    ("Xiaomi", "Smart-Home-Gerät oder Handy", "640980 7811dc 50ec50 286c07"),
    ("Intel", "PC oder Laptop", "3ca9f4 a434d9 7c5cf8 001b21"),
    ("Brother", "Drucker", "008077 30055c"),
    ("VMware", "Virtuelle Maschine", "005056 000c29"),
    ("VirtualBox", "Virtuelle Maschine", "080027"),
    ("QEMU/KVM", "Virtuelle Maschine", "525400"),
):
    for _prefix in _prefixe.split():
        VENDORS[_prefix] = (_hersteller, _art)

# Was offene Ports ueber die Art verraten (wenn der Hersteller nichts sagt).
_PORT_ARTEN = ((9100, "Drucker"), (631, "Drucker"), (515, "Drucker"), (554, "Kamera"),
               (8123, "Home Assistant"), (32400, "Medienserver"), (8096, "Medienserver"),
               (1883, "Smart-Home-Zentrale"), (8006, "Server (Proxmox)"), (11434, "KI-Server"))
_NAME = re.compile(r"[^\w .,()+&'-]")


def mac_info(mac: str) -> dict[str, Any]:
    """Hersteller, Art und ob die Adresse zufaellig ist."""
    roh = re.sub(r"[^0-9a-f]", "", str(mac or "").lower())
    if len(roh) != 12:
        return {}
    if roh.startswith("0242"):
        return {"vendor": "Docker", "kind": "Container", "random_mac": False}
    if int(roh[:2], 16) & 0x02:
        return {"vendor": "", "kind": "Handy oder Laptop (private WLAN-Adresse)",
                "random_mac": True}
    hersteller, art = VENDORS.get(roh[:6], ("", ""))
    return {"vendor": hersteller, "kind": art, "random_mac": False}


def describe(device: dict[str, Any], router: str = "") -> dict[str, Any]:
    """Ein Geraet mit Hersteller, Art und Namen (falls bekannt)."""
    info = mac_info(str(device.get("mac") or ""))
    art = info.get("kind", "")
    if device.get("address") == router:
        art = "Router"
    elif not art:
        ports = set(device.get("ports") or [])
        art = next((name for port, name in _PORT_ARTEN if port in ports), "")
    return {"vendor": info.get("vendor", ""), "kind": art,
            "random_mac": bool(info.get("random_mac"))}


def known_key(device: dict[str, Any]) -> str:
    """Schluessel fuer "bekannte Geraete": die MAC, sonst die IP."""
    mac = str(device.get("mac") or "").lower()
    return mac if re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", mac) else str(
        device.get("address") or "")


def clean_name(name: Any) -> str:
    return " ".join(_NAME.sub("", str(name or "")).split())[:40]


def clean_known(known: Any) -> dict[str, str]:
    """Gespeicherte Namen pruefen: Schluessel MAC oder private IPv4, Name hoechstens 40."""
    sauber: dict[str, str] = {}
    if not isinstance(known, dict):
        return sauber
    for key, name in list(known.items())[:256]:
        key = str(key).lower()
        if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", key):
            try:
                if not ipaddress.IPv4Address(key).is_private:
                    continue
            except ValueError:
                continue
        name = clean_name(name)
        if name:
            sauber[key] = name
    return sauber


GEWICHTE = {"malware": 20, "arp_spoof": 20, "vulnerability": 15, "brute_force": 15,
            "port_scan": 10, "risk_port": 8, "error": 5, "new_port": 4, "upnp": 3}


def score(events: list[dict[str, Any]], devices: list[dict[str, Any]],
          opts: dict[str, Any]) -> tuple[int, str]:
    """Sicherheitswert 0 bis 100 und Note (A bis E). Mehr Punkte heisst: weniger gefunden."""
    abzug = 0
    for event in events:
        gewicht = GEWICHTE.get(str(event.get("kind")), 0)
        abzug += gewicht if event.get("level") == "wichtig" else min(gewicht, 4) // 2
    aktiv = [d for d in devices if d.get("active")]
    nur_http = sum(1 for d in aktiv if set(d.get("ports") or []) & {80, 8080}
                   and not set(d.get("ports") or []) & {443, 8443})
    abzug += min(6, 2 * nur_http)
    abzug += min(8, sum(1 for d in aktiv if not d.get("name")))
    abzug += (0 if opts.get("watch", True) else 5) + (0 if opts.get("packets") else 3) \
        + (0 if opts.get("nmap") else 3)
    wert = max(0, min(100, 100 - abzug))
    note = "A" if wert >= 90 else "B" if wert >= 75 else "C" if wert >= 60 else \
        "D" if wert >= 40 else "E"
    return wert, note


SSDP = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\n"
        "MX: 1\r\nST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n\r\n")


def upnp_gateways(subnet: str, router: str = "", wait: float = 2.0) -> list[str]:
    """Antwortet der Router (oder ein anderes Geraet) als UPnP-Internet-Gateway?

    Eine einzige SSDP-Frage ins eigene Netz. Nur Antworten aus dem freigegebenen Netz zaehlen.
    """
    netz = ipaddress.IPv4Network(subnet)
    gefunden: set[str] = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            sock.settimeout(0.3)
            sock.sendto(SSDP.encode("ascii"), ("239.255.255.250", 1900))
            ende = time.monotonic() + max(0.5, min(wait, 5.0))
            while time.monotonic() < ende and len(gefunden) < 16:
                try:
                    daten, (absender, _) = sock.recvfrom(2048)
                except TimeoutError:
                    continue
                text = daten.decode("latin1", "replace").lower()
                try:
                    if ipaddress.IPv4Address(absender) not in netz:
                        continue
                except ValueError:
                    continue
                if "internetgatewaydevice" in text or "wanipconnection" in text:
                    gefunden.add(absender)
    except OSError:
        return []
    return sorted(gefunden, key=lambda a: (a != router, a))
