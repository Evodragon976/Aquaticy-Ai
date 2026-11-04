"""nmap fuer Secure Pro: Dienste, Versionen und sichere Schwachstellen-Skripte im Heimnetz.

Der Befehl ist fest. Ziele sind nur IPv4-Adressen oder das Netz aus der Freigabe. nmap nutzt
nur Skripte der Gruppen "vuln" UND "safe" -- ohne "external" (nichts geht ins Internet),
ohne "intrusive", "dos", "brute" und "exploit". Banner und Skriptausgaben kommen von den
Geraeten und koennen luegen; deshalb gehen nur bereinigte Felder weiter (Produkt, Version,
Skriptname, CVE-Nummern), nie freier Text.
"""

from __future__ import annotations

import ipaddress
import os
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import Any

from aquaticy.lan import parse_subnet

SCRIPTS = "vuln and safe and not (external or intrusive or dos or brute or exploit)"
MODES = ("dienste", "schwachstellen")
MAX_TARGETS = 8
MAX_OUTPUT = 4 * 1024 * 1024
_FELD = re.compile(r"[^\w .+/()-]")
_SKRIPT = re.compile(r"[a-z0-9][a-z0-9_-]{0,60}")
_CVE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b")


class NmapError(RuntimeError):
    """nmap fehlt, lief zu lange oder lieferte nichts Lesbares."""


def available() -> bool:
    return shutil.which("nmap") is not None


def targets_in(subnet: str, targets: list[str]) -> list[str]:
    """Prueft die Ziele gegen die Freigabe. Erlaubt: Adressen darin oder genau das Netz.

    Raises:
        ValueError: Wenn ein Ziel ausserhalb liegt oder es zu viele sind.
    """
    netz = parse_subnet(subnet)
    if netz.num_addresses > 256:
        raise ValueError("nmap prüft nur das freigegebene private Netz.")
    sauber: list[str] = []
    for ziel in targets:
        text = str(ziel).strip()
        if text == str(netz):
            sauber.append(text)
            continue
        try:
            adresse = ipaddress.IPv4Address(text)
        except ValueError as exc:
            raise ValueError("Nenne eine IP-Adresse aus deinem freigegebenen Netz.") from exc
        if adresse not in netz:
            raise ValueError("Das Gerät liegt außerhalb des freigegebenen Netzes.")
        sauber.append(str(adresse))
    if not sauber or len(sauber) > MAX_TARGETS:
        raise ValueError(f"nmap prüft 1 bis {MAX_TARGETS} Ziele auf einmal.")
    return list(dict.fromkeys(sauber))


def command(targets: list[str], mode: str) -> list[str]:
    """Der feste nmap-Aufruf. Ohne Root nutzt nmap normale Verbindungen (-sT)."""
    if mode not in MODES:
        raise ValueError("Modus: dienste oder schwachstellen.")
    programm = shutil.which("nmap")
    if programm is None:
        raise NmapError("nmap fehlt. Installiere es, zum Beispiel mit: sudo apt install nmap")
    ganzes_netz = any("/" in ziel for ziel in targets)
    args = [programm, "-n", "-Pn", "-sV", "-T3", "--max-retries", "2",
            "--host-timeout", "180s", "-oX", "-"]
    if mode == "dienste" or ganzes_netz:
        args += ["--version-light", "--top-ports", "100"]
    else:
        args += ["--top-ports", "1000", "--script", SCRIPTS]
    return [*args, "--", *targets]


def _feld(text: str | None) -> str:
    return " ".join(_FELD.sub("", str(text or "")).split())[:60]


def parse(xml_text: str) -> list[dict[str, Any]]:
    """Liest die XML-Ausgabe von nmap. Nur bereinigte Felder kommen heraus."""
    # Schutz vor XXE und "Billion Laughs": nmap schreibt nur "<!DOCTYPE nmaprun>". Das faellt
    # weg; jede weitere Deklaration (DOCTYPE mit Inhalt, ENTITY, ELEMENT ...) wird abgelehnt.
    if len(xml_text) > MAX_OUTPUT:
        raise NmapError("Die nmap-Ausgabe ist zu groß.")
    ohne_dtd = re.sub(r"<!DOCTYPE nmaprun>", "", xml_text, count=1)
    if "<!" in ohne_dtd.replace("<!--", "").replace("<![CDATA[", "") or "&" in re.sub(
            r"&(?:amp|lt|gt|quot|apos|#\d{1,7}|#x[0-9a-fA-F]{1,6});", "", ohne_dtd):
        raise NmapError("Unerwartete nmap-Ausgabe.")
    try:
        wurzel = ET.fromstring(ohne_dtd)
    except ET.ParseError as exc:
        raise NmapError("Die nmap-Ausgabe ließ sich nicht lesen.") from exc
    hosts: list[dict[str, Any]] = []
    for host in wurzel.iter("host"):
        adresse = ""
        for addr in host.iter("address"):
            if addr.get("addrtype") == "ipv4":
                try:
                    adresse = str(ipaddress.IPv4Address(addr.get("addr", "")))
                except ValueError:
                    adresse = ""
        if not adresse:
            continue
        ports: list[dict[str, Any]] = []
        for port in host.iter("port"):
            state = port.find("state")
            if state is None or state.get("state") != "open":
                continue
            try:
                nummer = int(port.get("portid", "0"))
            except ValueError:
                continue
            if not 1 <= nummer <= 65535:
                continue
            service = port.find("service")
            eintrag: dict[str, Any] = {
                "port": nummer, "proto": "udp" if port.get("protocol") == "udp" else "tcp",
                "service": _feld(service.get("name") if service is not None else ""),
                "product": _feld(service.get("product") if service is not None else ""),
                "version": _feld(service.get("version") if service is not None else ""),
                "findings": []}
            for script in port.iter("script"):
                kennung = str(script.get("id", ""))
                ausgabe = str(script.get("output", ""))
                if not _SKRIPT.fullmatch(kennung):
                    continue
                verwundbar = bool(re.search(r"(?<!NOT )\bVULNERABLE\b", ausgabe))
                if verwundbar:
                    eintrag["findings"].append({
                        "script": kennung,
                        "cves": sorted(set(_CVE.findall(ausgabe)))[:10]})
            ports.append(eintrag)
        hosts.append({"address": adresse, "ports": ports[:200]})
    return hosts[:256]


def _execute(args: list[str], timeout: float,
             allowed: Callable[[], bool] | None) -> str:
    with tempfile.TemporaryFile() as output:
        with subprocess.Popen(args, stdout=output, stderr=subprocess.DEVNULL,
                              stdin=subprocess.DEVNULL) as process:
            deadline = time.monotonic() + timeout
            try:
                while True:
                    if allowed is not None and not allowed():
                        raise NmapError("Die Freigabe wurde während der Prüfung entzogen.")
                    if os.fstat(output.fileno()).st_size > MAX_OUTPUT:
                        raise NmapError("Die nmap-Ausgabe ist zu groß.")
                    status = process.poll()
                    if status is not None:
                        break
                    if time.monotonic() >= deadline:
                        raise NmapError("nmap hat zu lange gebraucht. "
                                        "Prüfe weniger Geräte auf einmal.")
                    time.sleep(0.1)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
        output.seek(0)
        data = output.read(MAX_OUTPUT + 1)
    if status != 0 or not data.strip() or len(data) > MAX_OUTPUT:
        raise NmapError("nmap ist fehlgeschlagen. Es liegt kein Ergebnis vor.")
    return data.decode("utf-8", "replace")


def run(subnet: str, targets: list[str], mode: str = "schwachstellen", *,
        allowed: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Fuehrt nmap aus. Raises NmapError oder ValueError."""
    ziele = targets_in(subnet, targets)
    args = command(ziele, mode)
    zeit = 120 + 200 * len(ziele) if mode == "schwachstellen" else 600
    try:
        if allowed is not None and not allowed():
            raise NmapError("Die Netzfreigabe ist nicht mehr gültig.")
        xml = _execute(args, min(zeit, 1200), allowed)
    except OSError as exc:
        raise NmapError("nmap ließ sich nicht starten.") from exc
    network = parse_subnet(subnet)
    hosts = [h for h in parse(xml) if ipaddress.IPv4Address(h["address"]) in network
             and (str(network) in ziele or h["address"] in ziele)]
    return {"mode": mode, "targets": ziele, "hosts": hosts,
            "limits": "Nur sichere Prüfskripte ohne Internet. Versionen sind selbst gemeldet "
                      "und können falsch sein. Kein Treffer heißt nicht sicher."}


def events(hosts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Wichtige Befunde aus dem nmap-Ergebnis: Skripte, die eine Luecke melden."""
    befunde: list[dict[str, Any]] = []
    for host in hosts:
        for port in host["ports"]:
            dienst = " ".join(x for x in (port["product"], port["version"]) if x) \
                or port["service"] or "unbekannter Dienst"
            for treffer in port["findings"]:
                cves = ", ".join(treffer["cves"]) or "ohne CVE-Nummer"
                befunde.append({
                    "kind": "vulnerability", "level": "wichtig", "host": host["address"],
                    "port": port["port"],
                    "text": f"nmap meldet eine Schwachstelle bei {host['address']}, Port "
                            f"{port['port']} ({dienst}): {treffer['script']} ({cves}). "
                            "Prüfe Updates beim Hersteller."})
    return befunde
