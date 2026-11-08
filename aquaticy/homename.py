"""Eigene Adresse im Heimnetz und ueber Tailscale, mit HTTPS (15.5.5).

Statt ``http://192.168.1.20:8765`` gibt es zwei feste Namen:

* **Tailscale:** ``https://<rechner>.<tailnet>.ts.net:8443`` mit einem echten Zertifikat.
  Aquaticy holt es mit ``tailscale cert`` (das muss im Tailnet unter "HTTPS Certificates"
  eingeschaltet sein) und holt es neu, bevor es abläuft.
* **Heimnetz:** ``https://aquaticy.local:8443``. Der Name wird per mDNS angesagt (zeroconf,
  wenn installiert, sonst ``avahi-publish-address`` oder ``dns-sd``). Das Zertifikat stellt
  eine eigene kleine Zertifizierungsstelle (CA) von Aquaticy aus. Ihr Zertifikat laedt man
  einmal je Geraet unter ``/zertifikat`` herunter und vertraut ihm; danach gibt es keine
  Warnung mehr.

Sicherheit: Der private Schluessel der CA verlaesst den Datenordner nie (Dateirechte 600),
ausgeliefert wird nur das oeffentliche CA-Zertifikat. Die CA darf nur Namen im Heimnetz
unterschreiben (Name Constraints: .local, .home.arpa und private Adressen). Selbst wer ihr
vertraut, kann damit keine fremde Internetseite faelschen. Anmeldung und Zugangswort gelten
auf dem HTTPS-Eingang genauso wie auf dem normalen.
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aquaticy.tlsfiles import (
    folder_lock as _folder_lock,
)
from aquaticy.tlsfiles import (
    replace_pair as _replace_pair,
)
from aquaticy.tlsfiles import (
    write_private as _write_private,
)


def _valid_pair(cert: Path, key: Path, *, name: str = "") -> bool:
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    try:
        certificate = x509.load_pem_x509_certificate(cert.read_bytes())
        private = serialization.load_pem_private_key(key.read_bytes(), password=None)
        now = datetime.now(UTC)
        return bool(
            certificate.not_valid_before_utc <= now < certificate.not_valid_after_utc
            and certificate.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
            == private.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
            and (not name or name in _names_of(cert)))
    except Exception:
        return False


LOCAL_NAME = "aquaticy.local"
DEFAULT_PORT = 8443
CA_DAYS = 3650
SERVER_DAYS = 397  # Apple nimmt Serverzertifikate mit hoechstens 398 Tagen
RENEW_BEFORE = timedelta(days=21)
RECHECK_SECONDS = 24 * 3600
_PRIVATE_NETS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")


def folder(data_dir: Path) -> Path:
    ziel = Path(data_dir) / "home-tls"
    ziel.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(ziel, 0o700)
    return ziel




# -- Tailscale ------------------------------------------------------------------------------------
@dataclass
class TailscaleState:
    name: str = ""
    https: bool = False
    reason: str = ""


def _tailscale(*args: str, timeout: float = 30.0) -> subprocess.CompletedProcess[str] | None:
    programm = shutil.which("tailscale")
    if not programm:
        return None
    try:
        return subprocess.run([programm, *args], capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def tailscale_state() -> TailscaleState:
    """Liest nur vollstaendig geformte Statusantworten des lokalen Tailscale-Dienstes."""
    lauf = _tailscale("status", "--json", timeout=10.0)
    if lauf is None:
        return TailscaleState(reason="Tailscale ist nicht installiert.")
    if lauf.returncode != 0:
        return TailscaleState(reason="Tailscale läuft nicht.")
    try:
        daten = json.loads(lauf.stdout or "{}")
    except (ValueError, TypeError):
        return TailscaleState(reason="Tailscale antwortet unerwartet.")
    if (not isinstance(daten, dict) or not isinstance(daten.get("Self"), dict)
            or not isinstance(daten.get("CertDomains", []), list)):
        return TailscaleState(reason="Tailscale antwortet unerwartet.")
    name = daten["Self"].get("DNSName")
    domains = daten.get("CertDomains", [])
    if not isinstance(name, str) or not all(isinstance(d, str) for d in domains):
        return TailscaleState(reason="Tailscale antwortet unerwartet.")
    name = name.rstrip(".").lower()
    domains = [d.rstrip(".").lower() for d in domains]
    if not name.endswith(".ts.net"):
        return TailscaleState(reason="MagicDNS ist im Tailnet aus.")
    if name not in domains:
        return TailscaleState(name=name, reason=(
            "HTTPS ist im Tailnet aus. Schalte es in der Tailscale-Verwaltung unter DNS → "
            "„HTTPS Certificates“ ein."))
    return TailscaleState(name=name, https=True)


def tailscale_certificate(data_dir: Path, state: TailscaleState) -> tuple[Path, Path] | None:
    """Erneuert zuerst abseits der laufenden Dateien und uebernimmt nur gueltige Paare."""
    if not state.https or not state.name.endswith(".ts.net"):
        return None
    ziel = folder(data_dir)
    zert, schluessel = ziel / "tailscale.crt", ziel / "tailscale.key"
    with _folder_lock(ziel):
        valid = _valid_pair(zert, schluessel, name=state.name)
        if valid and not _expires_soon(zert):
            return zert, schluessel
        with tempfile.TemporaryDirectory(prefix=".tailscale-", dir=ziel) as directory:
            temporary = Path(directory)
            cert, key = temporary / "certificate.crt", temporary / "private.key"
            for path in (cert, key):
                _write_private(path, b"")
            lauf = _tailscale("cert", "--cert-file", str(cert), "--key-file", str(key),
                              state.name, timeout=90.0)
            if (lauf is not None and lauf.returncode == 0
                    and _valid_pair(cert, key, name=state.name)):
                _replace_pair(zert, schluessel, cert.read_bytes(), key.read_bytes())
                return zert, schluessel
        return (zert, schluessel) if _valid_pair(zert, schluessel, name=state.name) else None


# -- Eigene CA fuer das Heimnetz ------------------------------------------------------------------
def _expires_soon(path: Path) -> bool:
    from cryptography import x509

    try:
        zert = x509.load_pem_x509_certificate(path.read_bytes())
    except (OSError, ValueError):
        return True
    return zert.not_valid_after_utc - datetime.now(UTC) < RENEW_BEFORE


def _names_of(path: Path) -> set[str]:
    from cryptography import x509

    try:
        zert = x509.load_pem_x509_certificate(path.read_bytes())
        san = zert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except (OSError, ValueError, x509.ExtensionNotFound):
        return set()
    return {str(n) for n in san.get_values_for_type(x509.DNSName)} | {
        str(n) for n in san.get_values_for_type(x509.IPAddress)}


def _ensure_ca(data_dir: Path) -> tuple[Path, Path]:
    """Die eigene CA -- einmal erzeugt, danach wiederverwendet."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    ziel = folder(data_dir)
    zert, schluessel = ziel / "ca.crt", ziel / "ca.key"
    if _valid_pair(zert, schluessel) and not _expires_soon(zert):
        return zert, schluessel
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Aquaticy Heimnetz-CA"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Aquaticy (lokal)")])
    jetzt = datetime.now(UTC)
    erlaubt = [x509.DNSName("local"), x509.DNSName("home.arpa")] + [
        x509.IPAddress(ipaddress.ip_network(netz)) for netz in _PRIVATE_NETS]
    ca = (x509.CertificateBuilder()
          .subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number())
          .not_valid_before(jetzt - timedelta(minutes=5))
          .not_valid_after(jetzt + timedelta(days=CA_DAYS))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(
              digital_signature=False, content_commitment=False, key_encipherment=False,
              data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
              encipher_only=False, decipher_only=False), critical=True)
          .add_extension(x509.NameConstraints(permitted_subtrees=erlaubt,
                                              excluded_subtrees=None), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                         critical=False)
          .sign(key, hashes.SHA256()))
    _replace_pair(zert, schluessel, ca.public_bytes(serialization.Encoding.PEM),
                  key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
    with contextlib.suppress(OSError):
        (ziel / "server.crt").unlink()
    return zert, schluessel


def local_names(addresses: list[str]) -> tuple[list[str], list[str]]:
    """Namen und private Adressen fuer das Heimnetz-Zertifikat."""
    namen = [LOCAL_NAME]
    rechner = socket.gethostname().split(".")[0].lower()
    if rechner and rechner.replace("-", "").isalnum() and rechner != "aquaticy":
        namen.append(f"{rechner}.local")
    ips = []
    for adresse in addresses:
        with contextlib.suppress(ValueError):
            ip = ipaddress.ip_address(adresse)
            if any(ip in ipaddress.ip_network(n) for n in _PRIVATE_NETS):
                ips.append(str(ip))
    return namen, sorted(set(ips))


def _ensure_server_certificate(data_dir: Path, addresses: list[str]) -> tuple[Path, Path]:
    """Serverzertifikat fuer aquaticy.local und die eigenen Heimnetz-Adressen."""
    from cryptography import x509
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    ca_zert, ca_schluessel = ensure_ca(data_dir)
    ziel = folder(data_dir)
    zert, schluessel = ziel / "server.crt", ziel / "server.key"
    namen, ips = local_names(addresses)
    ca = x509.load_pem_x509_certificate(ca_zert.read_bytes())
    if (_valid_pair(zert, schluessel) and not _expires_soon(zert)
            and _names_of(zert) == set(namen) | set(ips)):
        try:
            x509.load_pem_x509_certificate(zert.read_bytes()).verify_directly_issued_by(ca)
            return zert, schluessel
        except (ValueError, TypeError, InvalidSignature):
            pass
    ca_key = serialization.load_pem_private_key(ca_schluessel.read_bytes(), password=None)
    if not isinstance(ca_key, ec.EllipticCurvePrivateKey):
        raise ValueError("Unerwarteter CA-Schlüssel.")
    key = ec.generate_private_key(ec.SECP256R1())
    jetzt = datetime.now(UTC)
    alt = [x509.DNSName(n) for n in namen] + [x509.IPAddress(ipaddress.ip_address(i))
                                               for i in ips]
    server = (x509.CertificateBuilder()
              .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, LOCAL_NAME)]))
              .issuer_name(ca.subject).public_key(key.public_key())
              .serial_number(x509.random_serial_number())
              .not_valid_before(jetzt - timedelta(minutes=5))
              .not_valid_after(min(jetzt + timedelta(days=SERVER_DAYS), ca.not_valid_after_utc))
              .add_extension(x509.SubjectAlternativeName(alt), critical=False)
              .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
              .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                             critical=False)
              .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(
                  ca_key.public_key()), critical=False)
              .sign(ca_key, hashes.SHA256()))
    _replace_pair(zert, schluessel, server.public_bytes(serialization.Encoding.PEM),
                  key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
    return zert, schluessel


def ca_certificate(data_dir: Path) -> bytes:
    """Das oeffentliche CA-Zertifikat zum Herunterladen -- nie der Schluessel."""
    return ensure_ca(data_dir)[0].read_bytes()


# -- mDNS: aquaticy.local -------------------------------------------------------------------------
class Announcer:
    """Sagt "aquaticy.local" im Heimnetz an. Ohne passendes Werkzeug: still, mit Grund."""

    def __init__(self) -> None:
        self._zeroconf: Any = None
        self._process: subprocess.Popen[bytes] | None = None
        self.reason = ""

    def start(self, address: str, port: int = DEFAULT_PORT) -> bool:
        self.stop()
        if not address:
            self.reason = "Keine Heimnetz-Adresse gefunden."
            return False
        try:
            from importlib import import_module

            module = import_module("zeroconf")
            self._zeroconf = module.Zeroconf()
            info = module.ServiceInfo("_https._tcp.local.", "Aquaticy._https._tcp.local.",
                               addresses=[socket.inet_aton(address)], port=port,
                               server=LOCAL_NAME + ".")
            self._zeroconf.register_service(info)
            return True
        except Exception:
            self.stop()
        for befehl in (["avahi-publish-address", "-R", LOCAL_NAME, address],
                       ["dns-sd", "-P", "Aquaticy", "_https._tcp", "local",
                        str(port), LOCAL_NAME, address]):
            programm = shutil.which(befehl[0])
            if not programm:
                continue
            with contextlib.suppress(OSError):
                self._process = subprocess.Popen(
                    [programm, *befehl[1:]], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                return True
        self.reason = ("aquaticy.local braucht mDNS: installiere avahi-utils (Linux) oder "
                       "„pip install zeroconf“. Bis dahin geht die Adresse mit IP.")
        return False

    def stop(self) -> None:
        if self._zeroconf is not None:
            with contextlib.suppress(Exception):
                self._zeroconf.unregister_all_services()
            with contextlib.suppress(Exception):
                self._zeroconf.close()
            self._zeroconf = None
        process, self._process = self._process, None
        if process is not None:
            with contextlib.suppress(OSError):
                process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(OSError):
                    process.kill()
                with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                    process.wait(timeout=2)


# -- Alles zusammen -------------------------------------------------------------------------------
@dataclass
class HomeTLS:
    """Ein TLS-Kontext mit beiden Zertifikaten, ausgewaehlt nach dem Namen (SNI)."""

    data_dir: Path
    addresses: list[str]
    tailscale: TailscaleState = field(default_factory=TailscaleState)
    urls: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    _local: ssl.SSLContext | None = None
    _ts: ssl.SSLContext | None = None
    _checked: float = 0.0
    _port: int = DEFAULT_PORT
    _refresh_lock: Any = field(default_factory=threading.Lock, repr=False)
    _refreshing: bool = False

    @staticmethod
    def _context(zert: Path, schluessel: Path) -> ssl.SSLContext:
        with _folder_lock(zert.parent):
            kontext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            kontext.minimum_version = ssl.TLSVersion.TLSv1_2
            kontext.load_cert_chain(str(zert), str(schluessel))
            return kontext

    def load(self, port: int) -> ssl.SSLContext:
        self._port = port
        self.refresh()
        assert self._local is not None
        return self._local

    def _choose(self, sock: ssl.SSLObject, name: str | None, _: ssl.SSLContext) -> None:
        if time.time() - self._checked > RECHECK_SECONDS:
            with self._refresh_lock:
                if not self._refreshing:
                    self._refreshing = True
                    threading.Thread(target=self._renew, name="aquaticy-cert-renew",
                                     daemon=True).start()
        if name and name.lower() == self.tailscale.name and self._ts is not None:
            sock.context = self._ts
        elif self._local is not None:
            sock.context = self._local

    def refresh(self) -> None:
        zert, schluessel = ensure_server_certificate(self.data_dir, self.addresses)
        local = self._context(zert, schluessel)
        local.sni_callback = self._choose
        state = tailscale_state()
        paar = tailscale_certificate(self.data_dir, state)
        tail = self._context(*paar) if paar is not None else None
        urls = [(f"https://{LOCAL_NAME}:{self._port}/", "im Heimnetz (HTTPS)")]
        if tail is not None:
            urls.append((f"https://{state.name}:{self._port}/", "über Tailscale (HTTPS)"))
        self._local, self._ts, self.tailscale = local, tail, state
        self.urls = urls
        self.notes = [state.reason] if state.reason and state.name else []
        self._checked = time.time()

    def _renew(self) -> None:
        try:
            self.refresh()
        except Exception:
            self._checked = time.time() - RECHECK_SECONDS + 300
        finally:
            with self._refresh_lock:
                self._refreshing = False


def enabled() -> bool:
    return os.environ.get("AQUATICY_HOME_HTTPS", "true").strip().lower() not in (
        "0", "false", "no", "off", "aus")


def port() -> int:
    try:
        wert = int(os.environ.get("AQUATICY_HTTPS_PORT", str(DEFAULT_PORT)))
    except ValueError:
        return DEFAULT_PORT
    return wert if 1024 <= wert <= 65535 else DEFAULT_PORT


def instructions_page() -> str:
    """Kurze Anleitung zum Vertrauen der Heimnetz-CA -- deutsch und englisch."""
    return """<!doctype html><html lang="de"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Zertifikat – Aquaticy</title>
<style>
:root{--bg:#f6f5f0;--fg:#26251f;--muted:#5f5d54;--accent:#2f7a53;--card:#fffefa}
@media (prefers-color-scheme:dark){:root{--bg:#191a17;--fg:#f2f1ea;--muted:#b6b3a8;
  --accent:#5fcf8f;--card:#22231f}}
body{margin:0;background:var(--bg);color:var(--fg);padding:16px;
  font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:40rem;margin:0 auto;background:var(--card);border-radius:16px;padding:24px}
a.knopf{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;
  border-radius:999px;padding:9px 20px;font-weight:600}
h2{font-size:18px;margin:22px 0 4px}p,li{color:var(--muted)}
</style>
<main>
<h1>HTTPS im Heimnetz</h1>
<p>Damit <b>https://aquaticy.local</b> ohne Warnung geht, vertraust du einmal dem Zertifikat von
Aquaticy. Es gilt nur für Adressen im Heimnetz, nicht für Seiten im Internet.</p>
<p><a class="knopf" href="/aquaticy-ca.crt">Zertifikat laden</a></p>
<h2>iPhone und iPad</h2>
<ol><li>Zertifikat laden und „Erlauben“ tippen.</li>
<li>Einstellungen → Profil geladen → Installieren.</li>
<li>Einstellungen → Allgemein → Info → Zertifikatsvertrauen → Aquaticy einschalten.</li></ol>
<h2>Android</h2>
<ol><li>Zertifikat laden.</li>
<li>Einstellungen → Sicherheit → Verschlüsselung → Zertifikat installieren →
CA-Zertifikat.</li></ol>
<h2>Windows</h2>
<ol><li>Datei öffnen → Zertifikat installieren → Lokaler Computer.</li>
<li>Speicher „Vertrauenswürdige Stammzertifizierungsstellen“ wählen.</li></ol>
<h2>Mac</h2>
<ol><li>Datei öffnen, sie landet in der Schlüsselbundverwaltung.</li>
<li>Doppelklick auf „Aquaticy Heimnetz-CA“ → Vertrauen → Immer vertrauen.</li></ol>
<hr>
<p lang="en"><b>English:</b> To open https://aquaticy.local without a warning, trust the
Aquaticy certificate once on each device (download above). It only works for addresses in
your home network, never for websites on the internet.</p>
</main></html>"""


def ensure_ca(data_dir: Path) -> tuple[Path, Path]:
    with _folder_lock(folder(data_dir)):
        return _ensure_ca(data_dir)


def ensure_server_certificate(data_dir: Path, addresses: list[str]) -> tuple[Path, Path]:
    with _folder_lock(folder(data_dir)):
        return _ensure_server_certificate(data_dir, addresses)
