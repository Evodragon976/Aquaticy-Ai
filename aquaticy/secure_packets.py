"""Paketpruefung fuer Secure Pro: nur Kopfdaten lesen, Angriffe und Malware-Zeichen finden.

Liest kurz Ethernet-, ARP-, IPv4-, TCP-, UDP- und DNS-Koepfe (Linux, Root oder CAP_NET_RAW).
Nachrichteninhalte werden nicht ausgewertet. Paketmitschnitte werden nicht gespeichert.
Metadaten sind Adressen, Ports und DNS-Namen. Im geswitchten Netz sieht er eigenen Verkehr,
Rundrufe (ARP, DHCP) und Verkehr, der ueber ihn laeuft. Das steht auch im Ergebnis.
"""

from __future__ import annotations

import ipaddress
import math
import platform
import re
import socket
import struct
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from typing import Any

from aquaticy.lan import parse_subnet
from aquaticy.secure_knowledge import MALWARE_PORTS

# Starke Zeichen: diese Ports nutzen kaum harmlose Programme.
_DNS_ZEICHEN = re.compile(r"[a-z0-9_-]+(?:\.[a-z0-9_-]+)*")
STRONG_PORTS = frozenset({1337, 1604, 2323, 3333, 4444, 5552, 12345, 14444, 20000, 27374,
                          31337, 45700})
LOGIN_PORTS = frozenset({21, 22, 23, 445, 1433, 2323, 3306, 3389, 5432, 5900})
MAX_PACKETS = 20_000
SNAP = 256


class Unavailable(RuntimeError):
    """Die Paketpruefung geht hier nicht (kein Linux oder keine Rechte)."""


def _ip(raw: bytes) -> str:
    return socket.inet_ntoa(raw)


def _mac(raw: bytes) -> str:
    return ":".join(f"{b:02x}" for b in raw)


def _dns_name(data: bytes, offset: int) -> str:
    """Liest den ersten Namen einer DNS-Frage (ohne Zeiger, hoechstens 253 Zeichen)."""
    teile: list[str] = []
    beendet = False
    for _ in range(64):
        if offset >= len(data):
            return ""
        laenge = data[offset]
        if laenge == 0:
            beendet = True
            break
        if laenge & 0xC0:
            return ""
        teil = data[offset + 1:offset + 1 + laenge]
        if len(teil) != laenge:
            return ""
        teile.append(teil.decode("ascii", "replace"))
        offset += 1 + laenge
    name = ".".join(teile).lower()
    # Nur uebliche Zeichen: Ein Name mit Leerzeichen oder Anfuehrungszeichen koennte sonst
    # als Text an das Modell gehen (Prompt-Injection ueber DNS).
    if not beendet or not 0 < len(name) <= 253 or not _DNS_ZEICHEN.fullmatch(name):
        return ""
    return name


def parse_frame(frame: bytes) -> dict[str, Any] | None:
    """Ein Ethernet-Rahmen als kleines Woerterbuch -- oder None."""
    if len(frame) < 14:
        return None
    art = struct.unpack("!H", frame[12:14])[0]
    start = 14
    if art == 0x8100 and len(frame) >= 18:
        art = struct.unpack("!H", frame[16:18])[0]
        start = 18
    data = frame[start:]
    if art == 0x0806 and len(data) >= 28:
        if data[:6] != b"\x00\x01\x08\x00\x06\x04":
            return None
        op = struct.unpack("!H", data[6:8])[0]
        if op not in (1, 2):
            return None
        return {"t": "arp", "op": op, "mac": _mac(data[8:14]), "ip": _ip(data[14:18]),
                "target": _ip(data[24:28])}
    if art != 0x0800 or len(data) < 20 or data[0] >> 4 != 4:
        return None
    kopf = (data[0] & 0x0F) * 4
    gesamt = struct.unpack("!H", data[2:4])[0]
    fragment = struct.unpack("!H", data[6:8])[0] & 0x1FFF
    if kopf < 20 or kopf > len(data) or gesamt < kopf or fragment:
        return None
    proto = data[9]
    record: dict[str, Any] = {"src": _ip(data[12:16]), "dst": _ip(data[16:20])}
    rest = data[kopf:min(gesamt, len(data))]
    if proto == 6 and len(rest) >= 20:
        tcp_kopf = (rest[12] >> 4) * 4
        if tcp_kopf < 20 or tcp_kopf > len(rest):
            return None
        sport, dport = struct.unpack("!HH", rest[:4])
        flags = rest[13]
        record.update(t="tcp", sport=sport, dport=dport, syn=bool(flags & 0x02),
                      ack=bool(flags & 0x10))
        return record
    if proto == 17 and len(rest) >= 8:
        udp_laenge = struct.unpack("!H", rest[4:6])[0]
        if udp_laenge < 8 or udp_laenge > gesamt - kopf:
            return None
        rest = rest[:udp_laenge]
        sport, dport = struct.unpack("!HH", rest[:4])
        record.update(t="udp", sport=sport, dport=dport)
        if 53 in (sport, dport) and len(rest) >= 20:
            dns = rest[8:]
            flags = struct.unpack("!H", dns[2:4])[0]
            questions = struct.unpack("!H", dns[4:6])[0]
            name = _dns_name(dns, 12) if questions else ""
            if name and len(dns) >= 12 + len(name) + 2 + 4:
                record.update(dns=name, qr=bool(flags & 0x8000), nx=(flags & 0x000F) == 3)
        return record
    return None


def capture(seconds: float = 15.0, max_packets: int = MAX_PACKETS, *, subnet: str = "",
            allowed: Callable[[], bool] | None = None) -> list[dict[str, Any]]:
    """Liest *seconds* lang Metadaten mit, ohne gespeicherte Paketmitschnitte."""
    if platform.system() != "Linux" or not hasattr(socket, "AF_PACKET"):
        raise Unavailable("Die Paketprüfung gibt es nur unter Linux.")
    network = parse_subnet(subnet) if subnet else None
    limit = max(1, min(MAX_PACKETS, int(max_packets)))
    if allowed is not None and not allowed():
        return []
    try:
        sock = socket.socket(getattr(socket, "AF_PACKET"), socket.SOCK_RAW,  # noqa: B009
                             socket.ntohs(0x0003))
    except PermissionError as exc:
        raise Unavailable("Die Paketprüfung braucht Root-Rechte oder CAP_NET_RAW.") from exc
    except OSError as exc:
        raise Unavailable("Die Paketprüfung konnte nicht starten.") from exc
    records: list[dict[str, Any]] = []
    ende = time.monotonic() + max(1.0, min(float(seconds), 60.0))
    try:
        sock.settimeout(0.5)
        while (time.monotonic() < ende and len(records) < limit
               and (allowed is None or allowed())):
            try:
                frame = sock.recv(SNAP)
            except TimeoutError:
                continue
            except OSError:
                break
            record = parse_frame(frame)
            if record is not None:
                if network is not None and not any(
                        ipaddress.IPv4Address(record[key]) in network
                        for key in ("src", "dst", "ip", "target") if key in record):
                    continue
                records.append(record)
    finally:
        sock.close()
    return records


def _entropy(text: str) -> float:
    if not text:
        return 0.0
    zaehler = Counter(text)
    return -sum(n / len(text) * math.log2(n / len(text)) for n in zaehler.values())


def random_name(name: str) -> bool:
    """Sieht ein DNS-Name zufaellig erzeugt aus (DGA)? Nur ein Verdacht."""
    teile = name.split(".")
    if len(teile) < 2:
        return False
    teil = max(teile[:-1], key=len)
    if len(teil) < 16 or not teil.isalnum():
        return False
    vokale = sum(c in "aeiou" for c in teil) / len(teil)
    return _entropy(teil) >= 3.6 and vokale < 0.3


def _event(kind: str, level: str, text: str, host: str = "", port: int = 0) -> dict[str, Any]:
    return {"kind": kind, "level": level, "text": text, "host": host, "port": port}


def analyze(records: list[dict[str, Any]], subnet: str, *, router: str = "",
            known_macs: dict[str, str] | None = None,
            own: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """Sucht in den Kopfdaten nach Angriffen und Malware-Zeichen.

    Args:
        known_macs: Bekannte Zuordnung IP -> MAC aus der Nachbartabelle.
        own: Eigene Adressen dieses Rechners -- deren Pruefungen sind kein Angriff.
    """
    network = ipaddress.IPv4Network(subnet)

    def lokal(adresse: str) -> bool:
        try:
            return ipaddress.IPv4Address(adresse) in network
        except ValueError:
            return False

    def oeffentlich(adresse: str) -> bool:
        try:
            return ipaddress.IPv4Address(adresse).is_global
        except ValueError:
            return False

    events: list[dict[str, Any]] = []
    ip_macs: dict[str, set[str]] = defaultdict(set)
    mac_ips: dict[str, set[str]] = defaultdict(set)
    ports_je_ziel: dict[tuple[str, str], set[int]] = defaultdict(set)
    ziele_je_port: dict[tuple[str, int], set[str]] = defaultdict(set)
    versuche: Counter[tuple[str, str, int]] = Counter()
    mail_ziele: dict[str, set[str]] = defaultdict(set)
    nx: Counter[str] = Counter()
    zufall: dict[str, set[str]] = defaultdict(set)
    gesehen: set[tuple[str, str, int]] = set()
    for record in records:
        art = record.get("t")
        if art == "arp":
            adresse, mac = str(record.get("ip", "")), str(record.get("mac", ""))
            # ARP-Proben ohne Absender (unspezifische Adresse) liegen nie im privaten Netz.
            if lokal(adresse) and mac not in (
                    "00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"):
                ip_macs[adresse].add(mac)
                mac_ips[mac].add(adresse)
            continue
        src, dst = str(record.get("src", "")), str(record.get("dst", ""))
        if src in own:
            continue
        dport = int(record.get("dport", 0))
        if art == "tcp" and record.get("syn") and not record.get("ack"):
            if lokal(src) or lokal(dst):
                ports_je_ziel[(src, dst)].add(dport)
                ziele_je_port[(src, dport)].add(dst)
                if dport in LOGIN_PORTS:
                    versuche[(src, dst, dport)] += 1
            if lokal(src) and dport == 25 and oeffentlich(dst):
                mail_ziele[src].add(dst)
            if lokal(src) and dport == 445 and oeffentlich(dst):
                schluessel = (src, "smb", 445)
                if schluessel not in gesehen:
                    gesehen.add(schluessel)
                    events.append(_event(
                        "malware", "wichtig",
                        f"{src} baut Windows-Freigaben (SMB, Port 445) ins Internet auf "
                        f"({dst}). So verbreiten sich Würmer wie WannaCry. Prüfe das Gerät.",
                        src, 445))
        if art in ("tcp", "udp") and (art == "udp" or record.get("syn")):
            for port, wer, gegen in ((dport, src, dst),
                                     (int(record.get("sport", 0)), dst, src)):
                if port not in MALWARE_PORTS or not (lokal(wer) or lokal(gegen)):
                    continue
                if art == "tcp" and port != dport:
                    continue
                schluessel = (wer if lokal(wer) else gegen, "port", port)
                if schluessel in gesehen:
                    continue
                gesehen.add(schluessel)
                name, text = MALWARE_PORTS[port]
                stark = port in STRONG_PORTS
                geraet = wer if lokal(wer) else gegen
                events.append(_event(
                    "malware", "wichtig" if stark else "hinweis",
                    f"Verdacht: Verkehr über Port {port} ({name}) bei {geraet}. {text} "
                    "Das kann auch ein harmloses Programm sein.", geraet, port))
        if art == "udp" and record.get("dns"):
            name = str(record["dns"])
            frager = dst if record.get("qr") else src
            if not lokal(frager):
                continue
            if record.get("qr") and record.get("nx"):
                nx[frager] += 1
            if not record.get("qr") and random_name(name) and len(zufall[frager]) < 3:
                zufall[frager].add(name)
    if router and router in ip_macs and known_macs and known_macs.get(router):
        neu = ip_macs[router] - {known_macs[router]}
        if neu:
            events.append(_event(
                "arp_spoof", "wichtig",
                f"Die Hardware-Adresse des Routers {router} hat sich geändert "
                f"({known_macs[router]} → {', '.join(sorted(neu))}). Das kann ARP-Spoofing "
                "sein: Ein Gerät liest dann den Verkehr mit. Prüfe, ob du den Router getauscht "
                "hast.", router))
    for adresse, macs in sorted(ip_macs.items()):
        if len(macs) > 1:
            events.append(_event(
                "arp_spoof", "wichtig",
                f"Mehrere Geräte geben sich als {adresse} aus ({', '.join(sorted(macs))}). "
                "Das kann ARP-Spoofing sein.", adresse))
    for mac, adressen in sorted(mac_ips.items()):
        if len(adressen) >= 3:
            events.append(_event(
                "arp_spoof", "wichtig",
                f"Ein Gerät ({mac}) gibt sich für {len(adressen)} Adressen aus. Das kann "
                "ARP-Spoofing sein. Manche Repeater tun das auch.", sorted(adressen)[0]))
    for (src, dst), ports in sorted(ports_je_ziel.items()):
        if len(ports) >= 20:
            events.append(_event(
                "port_scan", "wichtig",
                f"{src} prüft {len(ports)} Ports bei {dst}. Das ist ein Portscan. Wenn du "
                "das nicht selbst warst, prüfe das Gerät.", src))
    for (src, port), ziele in sorted(ziele_je_port.items()):
        if len(ziele) >= 12:
            events.append(_event(
                "port_scan", "wichtig",
                f"{src} versucht Port {port} bei {len(ziele)} Geräten. So suchen Würmer "
                "und Botnetze neue Opfer.", src, port))
    for (src, dst, port), anzahl in sorted(versuche.items()):
        if anzahl >= 25:
            events.append(_event(
                "brute_force", "wichtig",
                f"{src} verbindet sich {anzahl}-mal mit Port {port} bei {dst}. Das können "
                "Passwort-Angriffe sein.", dst, port))
    for src, ziele in sorted(mail_ziele.items()):
        if len(ziele) >= 10:
            events.append(_event(
                "malware", "wichtig",
                f"{src} verbindet sich mit {len(ziele)} Mailservern (Port 25). Das kann ein "
                "Spam-Bot sein.", src, 25))
    for frager, anzahl in sorted(nx.items()):
        if anzahl >= 25:
            events.append(_event(
                "malware", "wichtig",
                f"{frager} fragt {anzahl} Namen ab, die es nicht gibt. So suchen manche "
                "Schadprogramme ihren Server (DGA).", frager))
    for frager, namen in sorted(zufall.items()):
        event = _event(
            "malware", "hinweis",
            f"{frager} fragt zufällig aussehende Namen ab ({', '.join(sorted(namen))}). "
            "Das kann ein Zeichen für Schadsoftware sein.", frager)
        event["dns_names"] = sorted(namen)
        events.append(event)
    return events[:50]


def summary(records: list[dict[str, Any]], seconds: float) -> str:
    """Kurzer Satz, was die Paketpruefung gesehen hat -- mit ihrer Grenze."""
    return (f"Paketprüfung: {len(records)} Kopfdaten in {int(seconds)} Sekunden gelesen. "
            "Nachrichteninhalte werden nicht ausgewertet. "
            "In einem Netz mit Switch sieht dieser Rechner nur "
            "seinen eigenen Verkehr und Rundrufe.")
