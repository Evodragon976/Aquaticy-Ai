"""Freiwillige defensive Heimnetzpruefung und lokale ClamAV-Befunde."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)
RISK_PORTS = {21: "FTP", 23: "Telnet", 3389: "Fernwartung", 5900: "VNC",
              6379: "Redis", 3306: "MySQL", 5432: "PostgreSQL"}


def read(directory: Path) -> dict[str, Any]:
    try:
        value = json.loads((directory / "secure-pro.json").read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


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
    directory.mkdir(parents=True, exist_ok=True)
    fd = os.open(directory / "secure-pro.json", os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump({"enabled": True, "subnet": str(network),
                   "router": router, "folder": str(target) if target else ""}, output)


class Watcher:
    def __init__(self, directory: Path, notify: Callable[[str], bool]) -> None:
        self.directory = directory
        self.notify = notify
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.known: set[str] | None = None
        self.announced: set[str] = set()
        self.wake = threading.Event()
        self.last_findings: list[str] = []
        self.last_checked = 0.0
        self.positives: list[str] = []
        self.error = ""
        self.scanning = False
        self._network = ""
        self._result_subnet = ""
        self._requested = 0.0
        self._lock = threading.Lock()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"findings": list(self.last_findings), "positives": list(self.positives),
                    "checked": self.last_checked, "scanning": self.scanning, "error": self.error,
                    "scope": self._result_subnet}

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

    def tick(self) -> list[str]:
        from aquaticy import lan

        config = read(self.directory)
        if config.get("enabled") is not True or self.stop_event.is_set():
            return []
        network = lan.parse_subnet(config.get("subnet", ""))
        if network.num_addresses > 256:
            raise ValueError("Netz zu groß.")
        if str(network) != self._network:
            self.known = None
            self.announced.clear()
            self._network = str(network)
        devices = lan.scan(str(network), quick=False, with_titles=False, with_names=False)
        findings: set[str] = set()
        positives = [f"Der Prüfbereich bleibt privat und umfasst {network.num_addresses} Adressen."]
        current = {d.address for d in devices}
        if self.known is not None:
            findings.update(f"Neues Gerät: {ip}" for ip in current - self.known)
            if current and current == self.known:
                positives.append("Die erreichbaren Geräte sind seit der letzten Prüfung "
                                 "unverändert.")
        if devices:
            if not any(set(device.ports) & set(RISK_PORTS) for device in devices):
                positives.append(f"Bei {len(devices)} erreichbaren Geräten antwortet keiner der "
                                 "geprüften Risikodienste.")
            if not any(set(device.ports) & {21, 23} for device in devices):
                positives.append("Bei den erreichbaren Geräten antworten weder FTP noch Telnet.")
            tls_ports = sum(bool(set(device.ports) & {443, 8443}) for device in devices)
            if tls_ports:
                positives.append(f"Bei {tls_ports} Geräten antwortet Port 443 oder 8443. "
                                 "Dort sind oft verschlüsselte Weboberflächen erreichbar. "
                                 "TLS und Zertifikate wurden nicht geprüft.")
        else:
            findings.add("Keine Geräte über die geprüften TCP-Ports erreichbar. "
                         "Prüfe Netz, Router und Container-Anbindung. "
                         "Das ist kein sauberes Ergebnis.")
        for device in devices:
            for port in device.ports:
                if port in RISK_PORTS:
                    findings.add(f"Prüfhinweis: {device.address}, {RISK_PORTS[port]} "
                                 f"(Port {port}). "
                                 "Offen heißt nicht verwundbar oder infiziert.")
        folder = config.get("folder", "")
        if folder and shutil.which("clamscan"):
            result = subprocess.run(
                ["clamscan", "--recursive", "--infected", "--no-summary",
                 "--follow-dir-symlinks=0", "--follow-file-symlinks=0",
                 "--max-filesize=20M", "--max-scansize=100M", "--max-files=10000",
                 str(Path(folder).resolve())], capture_output=True, text=True,
                timeout=120, check=False)
            fd = os.open(self.directory / "secure-pro-report.json",
                         os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                         | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "w") as report:
                json.dump({"status": result.returncode, "scanned_at": int(time.time()),
                           "truncated": len(result.stdout) > 50000,
                           "findings": result.stdout[:50000]}, report)
            if result.returncode == 1:
                findings.add("ClamAV meldet mindestens einen Malwarefund im freigegebenen "
                             "lokalen Ordner. Öffne das lokale Secure-Pro-Protokoll.")
            elif result.returncode != 0:
                findings.add("ClamAV-Prüfung fehlgeschlagen. Es liegt kein sauberes Ergebnis vor.")
            else:
                positives.append("ClamAV meldet in den geprüften lokalen Dateien keinen Fund. "
                                 "Dateien außerhalb der Scan-Grenzen wurden nicht geprüft.")
        if self.stop_event.is_set() or read(self.directory) != config:
            return []
        self.known = current
        self.announced.intersection_update(findings)
        with self._lock:
            self.last_findings = sorted(findings)[:200]
            self.positives = positives
            self.last_checked = time.time()
            self._result_subnet = str(network)
            self.error = ""
        new = sorted(findings - self.announced)[:20]
        if new and not self.stop_event.is_set() and read(self.directory) == config:
            message = "[Aquaticy] Secure Pro\n" + "\n".join(new)
            if self.notify(message[:2900]):
                self.announced.update(new)
        return new

    def _run(self) -> None:
        while not self.stop_event.is_set():
            self.wake.clear()
            if self.stop_event.is_set():
                break
            if read(self.directory).get("enabled") is not True:
                self.wake.wait()
                continue
            try:
                with self._lock:
                    self.scanning = True
                findings = self.tick()
                if findings:
                    LOG.warning("Secure Pro: %s", "; ".join(findings))
            except Exception:
                with self._lock:
                    self.error = ("Die Prüfung ist fehlgeschlagen. "
                                  "Es liegt kein sauberes Ergebnis vor.")
                LOG.warning("Secure-Pro-Prüfung fehlgeschlagen; kein sauberes Ergebnis.")
                if (not self.stop_event.is_set()
                        and read(self.directory).get("enabled") is True):
                    try:
                        self.notify("[Aquaticy] Secure Pro: Die Prüfung ist fehlgeschlagen. "
                                    "Es liegt kein sauberes Ergebnis vor. "
                                    "Prüfe das lokale Protokoll.")
                    except Exception:
                        LOG.warning("Secure-Pro-Warnung konnte nicht versendet werden.")
            finally:
                with self._lock:
                    self.scanning = False
            self.wake.wait(900)
