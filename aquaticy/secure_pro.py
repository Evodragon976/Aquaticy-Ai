"""Freiwillige defensive Heimnetzpruefung und lokale ClamAV-Befunde.

Seit 14.1.3 Luna: Secure Pro ueberwacht nach Zeitplan (wie ein Coworker), liest auf Wunsch
Paket-Kopfdaten, kennt Malware-Ports und erfuellt Aufgaben wie "Melde dich bei neuen
Geraeten". In den Chat und an den Messenger geht nur Wichtiges und was eine Aufgabe
verlangt. Alles andere steht im Status, wenn du fragst.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aquaticy import private_json

LOG = logging.getLogger(__name__)
RISK_PORTS = {21: "FTP", 23: "Telnet", 1433: "Microsoft SQL", 2375: "Docker-API",
              3389: "Fernwartung", 5900: "VNC", 6379: "Redis", 3306: "MySQL",
              5432: "PostgreSQL", 9200: "Elasticsearch", 11211: "Memcached",
              27017: "MongoDB"}
# Wie oft Secure Pro prueft, in Sekunden (wie bei den Coworkern waehlbar). 0 = die ganze
# Zeit: nach jeder Pruefung nur eine kurze Pause (14.1.3 Terra).
INTERVALS = (0, 30, 60, 120, 300, 900, 1800, 3600, 10800, 21600, 43200, 86400)
DEFAULT_INTERVAL = 900
CONTINUOUS_PAUSE = 5.0
# nmap prueft ein Geraet erneut, wenn es neu ist, neue Ports hat oder nach einem Tag.
NMAP_AGAIN = 86400.0
NMAP_PER_CHECK = 4
PACKET_SECONDS = 15.0
SCOPE = ("enabled", "subnet", "router", "folder")
WICHTIG, HINWEIS = "wichtig", "hinweis"
# Kennung im Messenger (14.4.4): so sieht man, dass Secure Pro schreibt.
SIGNATURE = "[Aquaticy Secure Pro]"


def read(directory: Path) -> dict[str, Any]:
    try:
        value = json.loads((directory / "secure-pro.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def scope(config: dict[str, Any]) -> dict[str, Any]:
    """Nur was festlegt, WAS geprueft wird. Zeitplan und Aufgaben gehoeren nicht dazu."""
    return {key: config.get(key) for key in SCOPE}


def config_token(config: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(scope(config), sort_keys=True).encode()).hexdigest()


def grant_active(directory: Path, config: dict[str, Any], capability: str = "") -> bool:
    current = read(directory)
    return (current.get("enabled") is True and scope(current) == scope(config)
            and (not capability or current.get(capability) is True))


def options(config: dict[str, Any]) -> dict[str, Any]:
    """Zeitplan, Paketpruefung, VM und Aufgaben -- mit sicheren Standardwerten."""
    from aquaticy import secure_tasks

    sekunden = config.get("seconds")
    if type(sekunden) is not int or sekunden not in INTERVALS:
        # Bis 14.1.3 Luna stand der Abstand in Minuten unter "interval".
        alt = config.get("interval")
        sekunden = alt * 60 if type(alt) is int and alt * 60 in INTERVALS else DEFAULT_INTERVAL
    return {
        "watch": config.get("watch", True) is not False,
        "seconds": sekunden,
        "packets": config.get("packets") is True,
        "vm": config.get("vm") is True,
        "nmap": config.get("nmap") is True,
        # Auftraege aus dem eigenen WhatsApp/Signal-Chat ("Secure Pro prüfen"), 14.4.4.
        "messenger": config.get("messenger") is True,
        # Bekannte Geraete mit Namen (15.0.0): MAC oder IP -> Name.
        "known": _known(config.get("known")),
        "tasks": secure_tasks.clean(config.get("tasks", [])),
    }


def _known(roh: Any) -> dict[str, str]:
    from aquaticy.secure_devices import clean_known

    return clean_known(roh)


def name_device(directory: Path, address: str, mac: str, name: str) -> dict[str, str]:
    """Merkt sich ein Geraet mit Namen -- leerer Name vergisst es wieder.

    Raises:
        ValueError: Secure Pro ist aus oder das Geraet liegt ausserhalb der Freigabe.
    """
    import ipaddress

    from aquaticy.secure_devices import clean_name, known_key

    config = read(directory)
    if config.get("enabled") is not True:
        raise ValueError("Gib zuerst dein Netz in den Secure-Pro-Einstellungen frei.")
    try:
        if ipaddress.IPv4Address(str(address)) not in ipaddress.IPv4Network(config["subnet"]):
            raise ValueError
    except (ValueError, KeyError) as exc:
        raise ValueError("Das Gerät liegt außerhalb des freigegebenen Netzes.") from exc
    neu = options(config)
    schluessel = known_key({"address": str(address), "mac": str(mac or "")})
    sauber = clean_name(name)
    if sauber:
        if schluessel not in neu["known"] and len(neu["known"]) >= 256:
            raise ValueError("Höchstens 256 bekannte Geräte.")
        neu["known"][schluessel] = sauber
    else:
        neu["known"].pop(schluessel, None)
    private_json.write(directory / "secure-pro.json", {**scope(config), **neu})
    return neu["known"]


def history_path(directory: Path) -> Path:
    return directory / "secure-pro-log.json"


def read_history(directory: Path) -> dict[str, Any]:
    """Verlauf: Befunde mit Zeit und die letzten Sicherheitswerte (lokal, nur fuer dich)."""
    try:
        daten = json.loads(history_path(directory).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"events": [], "scores": []}
    if not isinstance(daten, dict):
        return {"events": [], "scores": []}
    events = [e for e in daten.get("events", []) if isinstance(e, dict)][-300:]
    scores = [s for s in daten.get("scores", []) if isinstance(s, list) and len(s) == 2][-60:]
    return {"events": events, "scores": scores}


def configure(directory: Path, subnet: str, folder: str = "", *, router: str = "") -> None:
    from aquaticy.lan import parse_subnet

    network = parse_subnet(subnet)
    if network.num_addresses > 256:
        raise ValueError("Secure Pro prüft höchstens 256 Adressen.")
    if router:
        import ipaddress

        from aquaticy.network_router import private_address

        router = private_address(router)
        if ipaddress.IPv4Address(router) not in network:
            raise ValueError("Der Router muss im freigegebenen Netz liegen.")
    target = Path(folder).expanduser().resolve() if folder else None
    if target is not None and (not target.is_dir() or not shutil.which("clamscan")):
        raise ValueError("Für lokale Dateien braucht Secure Pro einen Ordner und ClamAV.")
    vorher = read(directory)
    private_json.write(directory / "secure-pro.json", {
        **(options(vorher) if vorher.get("enabled") is True else {}),
        "enabled": True, "subnet": str(network), "router": router,
        "folder": str(target) if target else ""})


def set_options(directory: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Aendert Zeitplan, Paketpruefung, nmap und VM-Nutzung.

    Raises:
        ValueError: Secure Pro ist aus, oder ein Wert ist ungueltig.
    """
    config = read(directory)
    if config.get("enabled") is not True:
        raise ValueError("Gib zuerst dein Netz in den Secure-Pro-Einstellungen frei.")
    neu = options(config)
    for key in ("watch", "packets", "vm", "nmap", "messenger"):
        if key in payload:
            if not isinstance(payload[key], bool):
                raise ValueError("Wähle an oder aus.")
            neu[key] = payload[key]
    if "seconds" in payload:
        wert = payload["seconds"]
        if type(wert) is not int or wert not in INTERVALS:
            raise ValueError("Wähle einen der angebotenen Abstände.")
        neu["seconds"] = wert
    private_json.write(directory / "secure-pro.json", {**scope(config), **neu})
    return neu


def add_task(directory: Path, text: str) -> dict[str, Any]:
    """Neue Aufgabe. Raises ValueError, wenn sie nicht verstaendlich ist."""
    from aquaticy import secure_tasks

    config = read(directory)
    if config.get("enabled") is not True:
        raise ValueError("Gib zuerst dein Netz in den Secure-Pro-Einstellungen frei.")
    neu = options(config)
    if len(neu["tasks"]) >= secure_tasks.MAX_TASKS:
        raise ValueError("Höchstens 20 Aufgaben.")
    aufgabe = secure_tasks.parse(text)
    if aufgabe["host"]:
        import ipaddress

        if ipaddress.IPv4Address(aufgabe["host"]) not in ipaddress.IPv4Network(config["subnet"]):
            raise ValueError("Das Gerät liegt außerhalb des freigegebenen Netzes.")
    neu["tasks"].append(aufgabe)
    private_json.write(directory / "secure-pro.json", {**scope(config), **neu})
    return aufgabe


def remove_task(directory: Path, task_id: str) -> bool:
    config = read(directory)
    if config.get("enabled") is not True:
        return False
    neu = options(config)
    rest = [task for task in neu["tasks"] if task["id"] != str(task_id)]
    if len(rest) == len(neu["tasks"]):
        return False
    neu["tasks"] = rest
    private_json.write(directory / "secure-pro.json", {**scope(config), **neu})
    return True


def own_addresses(router: str = "") -> frozenset[str]:
    """Adressen dieses Rechners -- seine eigenen Pruefungen sind kein Angriff."""
    adressen: set[str] = set()
    with contextlib.suppress(OSError):
        adressen.update(socket.gethostbyname_ex(socket.gethostname())[2])
    if router:
        with contextlib.suppress(OSError), socket.socket(socket.AF_INET,
                                                         socket.SOCK_DGRAM) as probe:
            probe.connect((router, 9))
            adressen.add(probe.getsockname()[0])
    return frozenset(a for a in adressen if not a.startswith("127."))


class Watcher:
    def __init__(self, directory: Path, notify: Callable[[str], bool],
                 report: Callable[[str], bool] | None = None) -> None:
        self.directory = directory
        self.notify = notify
        self.report = report
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.known: set[str] | None = None
        self.announced: set[str] = set()
        self.wake = threading.Event()
        self.last_findings: list[str] = []
        self.important: list[str] = []
        self.events: list[dict[str, Any]] = []
        self.last_checked = 0.0
        self.next_check = 0.0
        self.positives: list[str] = []
        self.packet_status = ""
        self.error = ""
        self.scanning = False
        self._network = ""
        self._result_subnet = ""
        self._configuration = ""
        self.devices: list[dict[str, Any]] = []
        self._inventory: dict[str, dict[str, Any]] | None = None
        self._offline: set[str] = set()
        self._requested = 0.0
        self._fehler_gemeldet = False
        self._logged: set[str] = set()
        self.score: int | None = None
        self.grade = ""
        self.trend = 0
        self._upnp: tuple[float, list[str]] = (0.0, [])
        self._nmap_seen: dict[str, tuple[float, tuple[int, ...]]] = {}
        self._nmap_services: dict[str, list[str]] = {}
        self._nmap_hosts: dict[str, dict[str, Any]] = {}
        self._nmap_events: list[dict[str, Any]] = []
        self.nmap_status = ""
        self._lock = threading.Lock()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"findings": list(self.last_findings), "positives": list(self.positives),
                    "important": list(self.important),
                    "events": [dict(item) for item in self.events],
                    "checked": self.last_checked, "next_check": self.next_check,
                    "scanning": self.scanning, "error": self.error,
                    "packet_status": self.packet_status, "nmap_status": self.nmap_status,
                    "score": self.score, "grade": self.grade, "trend": self.trend,
                    "scope": self._result_subnet, "configuration": self._configuration,
                    "devices": [{**item, "ports": list(item["ports"])} for item in self.devices]}

    def start(self) -> None:
        with self._lock:
            if read(self.directory).get("enabled") is not True:
                return
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._run, name="aquaticy-secure-pro",
                                               daemon=True)
                self.thread.start()

    def request(self) -> bool:
        with self._lock:
            now = time.monotonic()
            if self._requested and now - self._requested < 60:
                return False
            self._requested = now
        self.wake.set()
        self.start()
        return True

    def stop(self) -> None:
        self.stop_event.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=3)

    def _packets(self, config: dict[str, Any], network: str,
                 known: dict[str, str]) -> list[dict[str, Any]]:
        """Liest kurz Kopfdaten und sucht Angriffe. Fehlt das Recht, steht das im Status."""
        from aquaticy import secure_packets

        if not options(config)["packets"]:
            with self._lock:
                self.packet_status = ""
            return []
        router = str(config.get("router") or "")
        def allowed() -> bool:
            return (not self.stop_event.is_set()
                    and grant_active(self.directory, config, "packets"))
        try:
            records = secure_packets.capture(PACKET_SECONDS, subnet=network, allowed=allowed)
        except secure_packets.Unavailable as exc:
            with self._lock:
                self.packet_status = str(exc)
            return []
        if not allowed():
            return []
        events = secure_packets.analyze(records, network, router=router, known_macs=known,
                                        own=own_addresses(router))
        with self._lock:
            self.packet_status = secure_packets.summary(records, PACKET_SECONDS)
        return events

    def _nmap(self, config: dict[str, Any], network: str,
              devices: list[Any]) -> list[dict[str, Any]]:
        """nmap-Schwachstellenpruefung fuer neue oder geaenderte Geraete (14.1.3 Terra).

        Je Pruefung hoechstens NMAP_PER_CHECK Geraete; jedes hoechstens einmal am Tag, ausser
        es hat neue Ports. Ergebnisse alter Laeufe bleiben als Befund, bis das Geraet wieder
        geprueft wurde.
        """
        from aquaticy import secure_nmap

        if not options(config)["nmap"]:
            with self._lock:
                self.nmap_status = ""
            return []
        if not secure_nmap.available():
            with self._lock:
                self.nmap_status = "nmap fehlt. Installiere es mit: sudo apt install nmap"
            return []
        jetzt = time.time()
        faellig = []
        for device in devices:
            ports = tuple(sorted(device.ports))
            zuletzt = self._nmap_seen.get(device.address)
            if zuletzt is None or zuletzt[1] != ports or jetzt - zuletzt[0] > NMAP_AGAIN:
                faellig.append((zuletzt[0] if zuletzt else 0.0, device.address, ports))
        faellig.sort()
        ziele = faellig[:NMAP_PER_CHECK]
        if ziele:
            try:
                ergebnis = secure_nmap.run(
                    network, [z[1] for z in ziele], "schwachstellen",
                    allowed=lambda: (not self.stop_event.is_set()
                                     and grant_active(self.directory, config, "nmap")))
            except (secure_nmap.NmapError, ValueError) as exc:
                if not grant_active(self.directory, config, "nmap"):
                    return []
                with self._lock:
                    self.nmap_status = str(exc)
                return self._nmap_events
            if not grant_active(self.directory, config, "nmap"):
                return []
            gefunden = {host["address"]: host for host in ergebnis["hosts"]}
            for _, address, ports in ziele:
                self._nmap_seen[address] = (jetzt, ports)
                host = gefunden.get(address, {"address": address, "ports": []})
                self._nmap_services[address] = [
                    f"{p['port']}/{p['proto']} " + " ".join(
                        x for x in (p["service"], p["product"], p["version"]) if x)
                    for p in host["ports"]][:30]
                self._nmap_hosts[address] = host
        aktiv = {device.address for device in devices}
        self._nmap_hosts = {a: h for a, h in self._nmap_hosts.items() if a in aktiv}
        self._nmap_events = secure_nmap.events(list(self._nmap_hosts.values()))
        with self._lock:
            self.nmap_status = (f"nmap: {len(self._nmap_hosts)} Geräte mit sicheren "
                                "Prüfskripten untersucht. Kein Treffer heißt nicht sicher.")
        return self._nmap_events

    def tick(self) -> list[str]:
        from aquaticy import lan, secure_tasks
        from aquaticy.secure_knowledge import MALWARE_PORTS
        from aquaticy.secure_packets import STRONG_PORTS

        config = read(self.directory)
        if config.get("enabled") is not True or self.stop_event.is_set():
            return []
        token = config_token(config)
        with self._lock:
            if self._configuration != token:
                self._configuration = token
                self.announced.clear()
                self.last_findings = []
                self.important = []
                self.events = []
                self.positives = []
                self.last_checked = 0
                self.error = ""
                self.devices = []
                self._inventory = None
                self._offline = set()
                self._nmap_seen = {}
                self._nmap_services = {}
                self._nmap_hosts = {}
                self._nmap_events = []
        network = lan.parse_subnet(config.get("subnet", ""))
        if network.num_addresses > 256:
            raise ValueError("Netz zu groß.")
        if str(network) != self._network:
            self.known = None
            self.announced.clear()
            self._network = str(network)
        from aquaticy.secure_network import neighbours

        vorher_macs: dict[str, str] = {}
        if options(config)["packets"]:
            vorher_macs = {address: str(item.get("mac") or "") for address, item in
                           (self._inventory or {}).items() if item.get("mac")}
            if not vorher_macs:
                vorher_macs = {item["address"]: item["mac"]
                               for item in neighbours(str(network))}
        packet_events = self._packets(config, str(network), vorher_macs)
        if not grant_active(self.directory, config) or self.stop_event.is_set():
            return []
        ports = tuple(sorted(set(lan.FULL_PORTS) | set(RISK_PORTS) | set(MALWARE_PORTS)))
        devices = lan.scan(str(network), quick=False, with_titles=False, with_names=False,
                           ports=ports)
        if not grant_active(self.directory, config) or self.stop_event.is_set():
            return []
        inventory = {item["address"]: item for item in neighbours(str(network))}
        for device in devices:
            item = inventory.setdefault(device.address, {"address": device.address, "mac": ""})
            item.update(ports=list(device.ports), active=True, source="TCP-Antwort")
        # Jeder Befund hat eine Stufe: Wichtiges geht in Chat und Messenger, Hinweise
        # stehen nur im Status.
        befunde: dict[str, dict[str, Any]] = {}

        def befund(text: str, kind: str, level: str, host: str = "", port: int = 0) -> None:
            alt = befunde.get(text)
            if alt is None or (level == WICHTIG and alt["level"] != WICHTIG):
                befunde[text] = {"kind": kind, "level": level, "text": text, "host": host,
                                 "port": port}

        # Geraete erkennen und benennen (15.0.0): Hersteller, Art, bekannter Name.
        from aquaticy import secure_devices

        bekannt = options(config)["known"]
        router_ip = str(config.get("router") or "")
        for item in inventory.values():
            item.update(secure_devices.describe(item, router_ip))
            name = bekannt.get(secure_devices.known_key(item)) or bekannt.get(item["address"])
            if name:
                item["name"] = name
            else:
                item.pop("name", None)

        def bekanntes(address: str) -> bool:
            return bool(inventory.get(address, {}).get("name"))

        def merkmal(address: str) -> str:
            item = inventory.get(address, {})
            was = item.get("vendor") or item.get("kind") or ""
            return f" ({was})" if was else ""

        ereignisse: list[dict[str, Any]] = []
        positives = [("Der Prüfbereich bleibt privat und umfasst 1 Adresse."
                      if network.num_addresses == 1 else
                      "Der Prüfbereich bleibt privat und umfasst "
                      f"{network.num_addresses} Adressen.")]
        changed = False
        router = str(config.get("router") or "")
        if self._inventory is not None:
            for address, item in inventory.items():
                old = self._inventory.get(address)
                if old is None and bekanntes(address):
                    pass
                elif old is None:
                    befund(f"Neu in der lokalen Beobachtung: {address}{merkmal(address)}. "
                           "Das kann ein eigenes Gerät oder ein alter Nachbareintrag sein.",
                           "new_device", HINWEIS, address)
                elif old.get("mac") and item.get("mac") and old["mac"] != item["mac"]:
                    changed = True
                    if address == router:
                        befund(f"Die Hardware-Adresse des Routers {address} hat sich "
                               f"geändert. Das kann ARP-Spoofing sein. Prüfe, ob du den "
                               "Router getauscht hast.", "arp_spoof", WICHTIG, address)
                    befund(f"Geänderte Geräteadresse bei {address}. "
                           "Prüfe DHCP und das Gerät; das allein belegt keinen Angriff.",
                           "mac_change", HINWEIS, address)
                if old and old.get("active") and item.get("active"):
                    added = sorted(set(item["ports"]) - set(old["ports"]))
                    if added:
                        changed = True
                        riskant = any(p in RISK_PORTS or p in MALWARE_PORTS for p in added)
                        befund(f"Neue antwortende Dienste bei {address}: {added}. "
                               "Prüfe, ob du diese Änderung erwartet hast.",
                               "new_port", WICHTIG if riskant else HINWEIS, address, added[0])
                        ereignisse.extend({"kind": "new_port", "level": HINWEIS, "text": "",
                                           "host": address, "port": port} for port in added)
        current = {d.address for d in devices}
        if self.known is not None:
            for ip in sorted(current - self.known):
                if not bekanntes(ip):
                    befund(f"Neues Gerät: {ip}{merkmal(ip)}", "new_device", HINWEIS, ip)
            for ip in sorted(self.known - current):
                self._offline.add(ip)
                ereignisse.append({"kind": "device_offline", "level": HINWEIS, "host": ip,
                                   "port": 0, "text": f"{ip} antwortet nicht mehr."})
            for ip in sorted(current & self._offline):
                self._offline.discard(ip)
                ereignisse.append({"kind": "device_online", "level": HINWEIS, "host": ip,
                                   "port": 0, "text": f"{ip} antwortet wieder."})
            if current and current == self.known and not changed:
                positives.append("Die erreichbaren Geräte sind seit der letzten Prüfung "
                                 "unverändert.")
        if devices:
            if not any(set(device.ports) & set(RISK_PORTS) for device in devices):
                positives.append(
                    "Bei einem erreichbaren Gerät antwortet keiner der geprüften Risikodienste."
                    if len(devices) == 1 else
                    f"Bei {len(devices)} erreichbaren Geräten antwortet keiner der "
                    "geprüften Risikodienste.")
            if not any(set(device.ports) & {21, 23} for device in devices):
                positives.append("Bei den erreichbaren Geräten antworten weder FTP noch Telnet.")
            if not any(set(device.ports) & set(MALWARE_PORTS) for device in devices):
                positives.append("Kein Gerät antwortet auf einem der bekannten Malware-Ports.")
            tls_ports = sum(bool(set(device.ports) & {443, 8443}) for device in devices)
            if tls_ports:
                positives.append(
                    ("Bei einem Gerät antwortet Port 443 oder 8443. "
                     "Dort sind oft verschlüsselte Weboberflächen erreichbar. "
                     "TLS und Zertifikate wurden nicht geprüft.") if tls_ports == 1 else
                    (f"Bei {tls_ports} Geräten antwortet Port 443 oder 8443. "
                     "Dort sind oft verschlüsselte Weboberflächen erreichbar. "
                     "TLS und Zertifikate wurden nicht geprüft."))
        else:
            befund("Keine Geräte über die geprüften TCP-Ports erreichbar. "
                   "Prüfe Netz, Router und Container-Anbindung. "
                   "Das ist kein sauberes Ergebnis.", "error", WICHTIG)
        for device in devices:
            for port in device.ports:
                if port in RISK_PORTS:
                    befund(f"Prüfhinweis: {device.address}, {RISK_PORTS[port]} "
                           f"(Port {port}). "
                           "Offen heißt nicht verwundbar oder infiziert.",
                           "risk_port", WICHTIG, device.address, port)
                elif port in MALWARE_PORTS:
                    name = MALWARE_PORTS[port][0]
                    befund(f"Verdacht: {device.address} antwortet auf Port {port} ({name}). "
                           "Das kann auch ein harmloses Programm sein. Prüfe, was dort läuft.",
                           "malware", WICHTIG if port in STRONG_PORTS else HINWEIS,
                           device.address, port)
        for event in packet_events if grant_active(self.directory, config, "packets") else []:
            befund(event["text"], event["kind"], event["level"], event["host"], event["port"])
            if event.get("dns_names"):
                befunde[event["text"]]["dns_names"] = list(event["dns_names"])
        for event in self._nmap(config, str(network), devices):
            befund(event["text"], event["kind"], event["level"], event["host"], event["port"])
        for address, dienste in self._nmap_services.items():
            if address in inventory:
                inventory[address]["services"] = list(dienste)
        # UPnP am Router (15.0.0): mit dem nmap-Schalter, hoechstens einmal je Stunde.
        if router_ip and options(config)["nmap"] and time.time() - self._upnp[0] > 3600:
            try:
                self._upnp = (time.time(), secure_devices.upnp_gateways(str(network),
                                                                        router_ip, 1.5))
            except (OSError, ValueError):
                self._upnp = (time.time(), [])
        for gateway in self._upnp[1] if options(config)["nmap"] else []:
            befund(f"UPnP ist an bei {gateway}. Geräte können damit selbst Ports ins "
                   "Internet öffnen. Schalte UPnP am Router aus, wenn du es nicht brauchst.",
                   "upnp", HINWEIS, gateway)
        if not grant_active(self.directory, config) or self.stop_event.is_set():
            return []
        folder = config.get("folder", "")
        target = Path(folder) if folder else None
        if target and (not target.is_dir() or target.resolve() != target):
            befund("Der freigegebene Dateiordner wurde verschoben oder ersetzt. "
                   "Die Dateiprüfung ist nicht erfolgt. Gib den Ordner erneut frei.",
                   "error", WICHTIG)
        elif folder and not shutil.which("clamscan"):
            befund("ClamAV fehlt. Die freigegebene Dateiprüfung ist nicht erfolgt. "
                   "Installiere ClamAV erneut.", "error", WICHTIG)
        elif target:
            result = subprocess.run(
                ["clamscan", "--recursive", "--infected", "--no-summary",
                 "--follow-dir-symlinks=0", "--follow-file-symlinks=0",
                 "--max-filesize=20M", "--max-scansize=100M", "--max-files=10000",
                 str(target)], capture_output=True, text=True,
                timeout=120, check=False)
            private_json.write(self.directory / "secure-pro-report.json", {
                "status": result.returncode, "scanned_at": int(time.time()),
                "truncated": len(result.stdout) > 50000, "findings": result.stdout[:50000]})
            if result.returncode == 1:
                befund("ClamAV meldet mindestens einen Malwarefund im freigegebenen "
                       "lokalen Ordner. Öffne das lokale Secure-Pro-Protokoll.",
                       "malware", WICHTIG)
            elif result.returncode != 0:
                befund("ClamAV-Prüfung fehlgeschlagen. Es liegt kein sauberes Ergebnis vor.",
                       "error", WICHTIG)
            else:
                positives.append("ClamAV meldet in den geprüften lokalen Dateien keinen Fund. "
                                 "Dateien außerhalb der Scan-Grenzen wurden nicht geprüft.")
        if self.stop_event.is_set() or config_token(read(self.directory)) != token:
            return []
        findings = set(befunde)
        # Eine TCP-Antwort ("Neues Gerät") sagt mehr als ein Eintrag der Nachbartabelle.
        alle = sorted(list(befunde.values()) + ereignisse,
                      key=lambda item: not str(item["text"]).startswith("Neues Gerät"))
        # Aufgaben: "Melde dich, wenn ...". Jede passende Beobachtung wird gemeldet.
        aufgaben: list[str] = []
        gemeldet: set[tuple[str, str, str, int]] = set()
        for task in options(read(self.directory))["tasks"]:
            for event in alle:
                schluessel = (task["id"], event["kind"], event["host"], int(event["port"]))
                if schluessel in gemeldet or not secure_tasks.matches(task, event):
                    continue
                gemeldet.add(schluessel)
                was = event["text"] or (f"{event['host']}: neuer Dienst auf Port "
                                        f"{event['port']}.")
                aufgaben.append(f"Aufgabe „{task['text']}“: {was}")
        self.known = current
        self._inventory = inventory
        wichtig = sorted(text for text, item in befunde.items() if item["level"] == WICHTIG)
        self.announced.intersection_update(findings | set(aufgaben))
        with self._lock:
            self.last_findings = sorted(findings)[:200]
            self.important = wichtig[:200]
            self.events = sorted(befunde.values(), key=lambda item: (
                item["level"] != WICHTIG, item["text"]))[:200]
            self.positives = positives
            self.last_checked = time.time()
            self._result_subnet = str(network)
            self.error = ""
            self.devices = sorted(inventory.values(), key=lambda item: tuple(
                int(part) for part in item["address"].split(".")))[:256]
        self._remember(befunde, options(read(self.directory)))
        new = [text for text in dict.fromkeys(wichtig + aufgaben)
               if text not in self.announced][:20]
        if new and not self.stop_event.is_set() and config_token(read(self.directory)) == token:
            abwehr = any(befunde.get(text, {}).get("kind") in (
                "malware", "arp_spoof", "port_scan", "brute_force", "risk_port",
                "vulnerability") for text in new)
            if self._deliver(new, abwehr):
                self.announced.update(new)
        return new

    def _remember(self, befunde: dict[str, dict[str, Any]], gewaehlt: dict[str, Any]) -> None:
        """Sicherheitswert und Verlauf (15.0.0). Der Verlauf bleibt lokal und privat."""
        from aquaticy import secure_devices

        wert, note = secure_devices.score(list(befunde.values()), self.devices, gewaehlt)
        verlauf = read_history(self.directory)
        jetzt = time.time()
        vorher = verlauf["scores"][-1] if verlauf["scores"] else None
        with self._lock:
            self.trend = wert - int(vorher[1]) if vorher else 0
            self.score, self.grade = wert, note
        neu = [item for text, item in befunde.items() if text not in self._logged]
        self._logged = set(befunde)
        if not neu and vorher and vorher[1] == wert and jetzt - float(vorher[0]) < 3600:
            return
        verlauf["events"].extend({"t": int(jetzt), "level": item["level"],
                                  "text": item["text"][:500]} for item in neu)
        if not vorher or vorher[1] != wert or jetzt - float(vorher[0]) >= 3600:
            verlauf["scores"].append([int(jetzt), wert])
        try:
            private_json.write(history_path(self.directory), {
                "events": verlauf["events"][-300:], "scores": verlauf["scores"][-60:]})
        except OSError:
            LOG.warning("Der Secure-Pro-Verlauf ließ sich nicht speichern.")

    def rename(self, bekannt: dict[str, str]) -> None:
        """Neue Namen gleich in der Geraeteliste zeigen, nicht erst nach der Pruefung."""
        from aquaticy.secure_devices import known_key

        with self._lock:
            for item in self.devices:
                name = bekannt.get(known_key(item)) or bekannt.get(item["address"])
                if name:
                    item["name"] = name
                else:
                    item.pop("name", None)

    def _deliver(self, lines: list[str], abwehr: bool) -> bool:
        """Meldet Wichtiges an Messenger und Secure-Pro-Chat. True, wenn es ankam."""
        prefix = SIGNATURE + "\n"
        suffix = ("\nSchreib im Secure-Pro-Chat, was ich tun soll, zum Beispiel "
                  "„Sperre Port 4444 auf 192.168.1.20“. Jede Abwehr braucht dein Ja."
                  if abwehr else "")
        body = "\n".join(lines)
        size = 2900 - len(prefix) - len(suffix)
        delivered = True
        for offset in range(0, len(body), size):
            message = prefix + body[offset:offset + size] + suffix
            angekommen = False
            for weg, name in ((self.notify, "Messenger"), (self.report, "Chat")):
                if weg is None:
                    continue
                try:
                    angekommen = bool(weg(message)) or angekommen
                except Exception:
                    LOG.warning("Secure-Pro-Hinweis (%s) konnte nicht zugestellt werden; "
                                "die Prüfergebnisse bleiben verfügbar.", name)
            delivered = delivered and angekommen
        return delivered and bool(body)

    def _wait_seconds(self) -> float | None:
        """Wie lange bis zur naechsten Pruefung -- None: nur auf Anfrage."""
        config = read(self.directory)
        gewaehlt = options(config)
        if not gewaehlt["watch"]:
            return None
        return float(gewaehlt["seconds"]) or CONTINUOUS_PAUSE

    def _run(self) -> None:
        while not self.stop_event.is_set():
            self.wake.clear()
            if self.stop_event.is_set():
                break
            if read(self.directory).get("enabled") is not True:
                self.next_check = 0.0
                self.wake.wait()
                continue
            try:
                with self._lock:
                    self.scanning = True
                findings = self.tick()
                self._fehler_gemeldet = False
                if findings:
                    LOG.warning("Secure Pro: %s", "; ".join(findings))
            except Exception:
                with self._lock:
                    self.error = ("Die Prüfung ist fehlgeschlagen. "
                                  "Es liegt kein sauberes Ergebnis vor.")
                LOG.warning("Secure-Pro-Prüfung fehlgeschlagen; kein sauberes Ergebnis.")
                # Nur einmal melden, bis eine Pruefung wieder klappt -- sonst kaeme bei
                # "die ganze Zeit" alle paar Sekunden dieselbe Warnung.
                if (not self.stop_event.is_set() and not self._fehler_gemeldet
                        and read(self.directory).get("enabled") is True):
                    self._fehler_gemeldet = True
                    try:
                        self.notify(f"{SIGNATURE} Die Prüfung ist fehlgeschlagen. "
                                    "Es liegt kein sauberes Ergebnis vor. "
                                    "Prüfe das lokale Protokoll.")
                    except Exception:
                        LOG.warning("Secure-Pro-Warnung konnte nicht versendet werden.")
            finally:
                with self._lock:
                    self.scanning = False
            pause = self._wait_seconds()
            self.next_check = time.time() + pause if pause else 0.0
            if pause is None:
                self.wake.wait()
            else:
                self.wake.wait(pause)
