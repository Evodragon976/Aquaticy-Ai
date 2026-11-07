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
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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


def _write_private(path: Path, data: bytes) -> None:
    """Schreibt eine Schluesseldatei so, dass nur der eigene Benutzer sie lesen kann."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as datei:
        datei.write(data)
    os.replace(tmp, path)


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
    """Wie heisst dieser Rechner im Tailnet, und ist HTTPS dort eingeschaltet?"""
    lauf = _tailscale("status", "--json", timeout=10.0)
    if lauf is None:
        return TailscaleState(reason="Tailscale ist nicht installiert.")
    if lauf.returncode != 0:
        return TailscaleState(reason="Tailscale läuft nicht.")
    try:
        daten = json.loads(lauf.stdout or "{}")
    except ValueError:
        return TailscaleState(reason="Tailscale antwortet unerwartet.")
    selbst = daten.get("Self") if isinstance(daten, dict) else None
    name = str((selbst or {}).get("DNSName") or "").rstrip(".").lower()
    domains = [str(d).rstrip(".").lower() for d in daten.get("CertDomains") or []]
    if not name.endswith(".ts.net"):
        return TailscaleState(reason="MagicDNS ist im Tailnet aus.")
    if name not in domains:
        return TailscaleState(name=name, reason=(
            "HTTPS ist im Tailnet aus. Schalte es in der Tailscale-Verwaltung unter DNS → "
            "„HTTPS Certificates“ ein."))
    return TailscaleState(name=name, https=True)


def tailscale_certificate(data_dir: Path, state: TailscaleState) -> tuple[Path, Path] | None:
    """Holt (oder erneuert) das Zertifikat fuer den ts.net-Namen. None: geht gerade nicht."""
    if not state.https:
        return None
    ziel = folder(data_dir)
    zert, schluessel = ziel / "tailscale.crt", ziel / "tailscale.key"
    if zert.exists() and schluessel.exists() and not _expires_soon(zert):
        return zert, schluessel
    lauf = _tailscale("cert", "--cert-file", str(zert), "--key-file", str(schluessel),
                      state.name, timeout=90.0)
    if lauf is None or lauf.returncode != 0 or not zert.exists():
        return (zert, schluessel) if zert.exists() and schluessel.exists() else None
    with contextlib.suppress(OSError):
        os.chmod(schluessel, 0o600)
    return zert, schluessel


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


def ensure_ca(data_dir: Path) -> tuple[Path, Path]:
    """Die eigene CA -- einmal erzeugt, danach wiederverwendet."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    ziel = folder(data_dir)
    zert, schluessel = ziel / "ca.crt", ziel / "ca.key"
    if zert.exists() and schluessel.exists() and not _expires_soon(zert):
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
    _write_private(schluessel, key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    zert.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
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


def ensure_server_certificate(data_dir: Path, addresses: list[str]) -> tuple[Path, Path]:
    """Serverzertifikat fuer aquaticy.local und die eigenen Heimnetz-Adressen."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    ca_zert, ca_schluessel = ensure_ca(data_dir)
    ziel = folder(data_dir)
    zert, schluessel = ziel / "server.crt", ziel / "server.key"
    namen, ips = local_names(addresses)
    if (zert.exists() and schluessel.exists() and not _expires_soon(zert)
            and _names_of(zert) == set(namen) | set(ips)):
        return zert, schluessel
    ca = x509.load_pem_x509_certificate(ca_zert.read_bytes())
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
              .not_valid_after(jetzt + timedelta(days=SERVER_DAYS))
              .add_extension(x509.SubjectAlternativeName(alt), critical=False)
              .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
              .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                             critical=False)
              .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(
                  ca_key.public_key()), critical=False)
              .sign(ca_key, hashes.SHA256()))
    _write_private(schluessel, key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    zert.write_bytes(server.public_bytes(serialization.Encoding.PEM))
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
        if not address:
            self.reason = "Keine Heimnetz-Adresse gefunden."
            return False
        with contextlib.suppress(Exception):
            from zeroconf import (  # type: ignore[import-not-found]  # optional, erst hier
                ServiceInfo,
                Zeroconf,
            )

            self._zeroconf = Zeroconf()
            info = ServiceInfo("_https._tcp.local.", "Aquaticy._https._tcp.local.",
                               addresses=[socket.inet_aton(address)], port=port,
                               server=LOCAL_NAME + ".")
            self._zeroconf.register_service(info)
            return True
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
                self._zeroconf.close()
            self._zeroconf = None
        if self._process is not None:
            with contextlib.suppress(Exception):
                self._process.terminate()
            self._process = None


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

    @staticmethod
    def _context(zert: Path, schluessel: Path) -> ssl.SSLContext:
        kontext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        kontext.minimum_version = ssl.TLSVersion.TLSv1_2
        kontext.load_cert_chain(str(zert), str(schluessel))
        return kontext

    def load(self, port: int) -> ssl.SSLContext:
        """Baut oder erneuert die Zertifikate und gibt den Kontext fuer den Server zurueck."""
        self._checked = time.time()
        self.urls, self.notes = [], []
        zert, schluessel = ensure_server_certificate(self.data_dir, self.addresses)
        self._local = self._context(zert, schluessel)
        self.urls.append((f"https://{LOCAL_NAME}:{port}/", "im Heimnetz (HTTPS)"))
        self.tailscale = tailscale_state()
        paar = tailscale_certificate(self.data_dir, self.tailscale)
        if paar is not None:
            with contextlib.suppress(ssl.SSLError, OSError):
                self._ts = self._context(*paar)
                self.urls.append((f"https://{self.tailscale.name}:{port}/",
                                  "über Tailscale (HTTPS)"))
        elif self.tailscale.reason and self.tailscale.name:
            self.notes.append(self.tailscale.reason)
        haupt = self._local
        haupt.sni_callback = self._choose
        return haupt

    def _choose(self, sock: ssl.SSLObject, name: str | None, _: ssl.SSLContext) -> None:
        if time.time() - self._checked > RECHECK_SECONDS:
            # Einmal am Tag beim Handschlag nachsehen -- ohne eigenen Hintergrund-Faden.
            with contextlib.suppress(Exception):
                self.refresh()
        if name and name.lower().endswith(".ts.net") and self._ts is not None:
            sock.context = self._ts
        elif self._local is not None:
            sock.context = self._local

    def refresh(self) -> None:
        self._checked = time.time()
        zert, schluessel = ensure_server_certificate(self.data_dir, self.addresses)
        self._local = self._context(zert, schluessel)
        self._local.sni_callback = self._choose
        paar = tailscale_certificate(self.data_dir, tailscale_state())
        if paar is not None:
            self._ts = self._context(*paar)


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
