"""Eine eigene Website: Aquaticy unter deiner Domain, ueber Cloudflare (11.1.0 Luna).

So laeuft es:

* **Einmal einrichten** (``aquaticy setup`` oder ``aquaticy website setup``):
  Domain und ein Cloudflare-API-Token. Aquaticy legt bei Cloudflare einen
  Tunnel an, traegt die Domain dafuer ein und holt sich ein Zertifikat von
  Let's Encrypt. Die Pruefung dafuer laeuft ueber einen DNS-Eintrag, den
  Aquaticy selbst setzt -- es muss kein Port offen sein.
* **Starten** mit ``aquaticy web``: erreichbar im Heimnetz, ueber Tailscale
  und unter der Domain.
* **Der Tunnel** (``cloudflared``) baut die Verbindung von innen nach aussen
  auf. Am Router muss nichts freigegeben werden. ``cloudflared`` laedt
  Aquaticy selbst von GitHub, nur mit veroeffentlichter Pruefsumme.

Sicherheit: Was ueber den Tunnel kommt, kommt aus dem Internet. Es landet auf
einem eigenen Eingang, der nur auf 127.0.0.1 hoert und das weiss (siehe
``PublicHandler`` in ``aquaticy/web.py``). Das Tunnel-Token bekommt
``cloudflared`` ueber die Umgebung, nicht ueber die Befehlszeile -- die kann
jeder auf dem Rechner mit ``ps`` lesen.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

#: Die Einstellungen in der ``.env``.
DOMAIN_ENV = "AQUATICY_DOMAIN"
TOKEN_ENV = "AQUATICY_CLOUDFLARE_TOKEN"
EMAIL_ENV = "AQUATICY_ACME_EMAIL"
STAGING_ENV = "AQUATICY_ACME_STAGING"
PUBLIC_PORT_ENV = "AQUATICY_PUBLIC_PORT"
CLOUDFLARED_ENV = "AQUATICY_CLOUDFLARED"

#: Der Eingang fuer den Tunnel. Nur auf 127.0.0.1.
DEFAULT_PUBLIC_PORT = 8443

CF_API = "https://api.cloudflare.com/client/v4"
ACME_DIRECTORY = "https://acme-v02.api.letsencrypt.org/directory"
ACME_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"
DOH_URL = "https://cloudflare-dns.com/dns-query"
CLOUDFLARED_API = "https://api.github.com/repos/cloudflare/cloudflared"

#: Ein Zertifikat wird erneuert, wenn es nur noch so lange gilt.
RENEW_DAYS = 30
#: So oft sieht Aquaticy nach dem Zertifikat.
CHECK_SECONDS = 12 * 3600
#: Nach einem Fehlschlag frühestens wieder -- Let's Encrypt zaehlt Fehlversuche.
RETRY_SECONDS = 6 * 3600
#: Neustarts von cloudflared, wenn es endet: erst schnell, dann geduldig.
TUNNEL_BACKOFF = (5.0, 15.0, 60.0, 300.0)
#: Wie lange Aquaticy hoechstens auf den DNS-Eintrag wartet.
DNS_WAIT_SECONDS = 90.0
#: Wie lange es hoechstens auf Let's Encrypt wartet (je Schritt).
ACME_POLL_SECONDS = 180.0
#: Groesste Antwort, die von Cloudflare oder Let's Encrypt gelesen wird.
MAX_API_BYTES = 4 * 1024 * 1024
#: cloudflared ist rund 40 MB gross.
MAX_LOG_BYTES = 5 * 1024 * 1024

DOMAIN_RE = re.compile(
    r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_.\-]{20,400}$")
#: Tunnel-Tokens sind Base64 (JSON darin) -- mit "+", "/" und "=".
TUNNEL_TOKEN_RE = re.compile(r"^[A-Za-z0-9+/=_.\-]{20,4000}$")
ID_RE = re.compile(r"^[0-9a-f]{32}$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
EMAIL_RE = re.compile(r"^[^@\s<>\"']{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,63}$")
RELEASE_TAG_RE = re.compile(r"^\d{4}\.\d{1,2}\.\d{1,3}$")

#: Welche Ausgabe von cloudflared zu welchem System passt.
CLOUDFLARED_ASSETS: dict[tuple[str, str], str] = {
    ("linux", "x86_64"): "cloudflared-linux-amd64",
    ("linux", "amd64"): "cloudflared-linux-amd64",
    ("linux", "aarch64"): "cloudflared-linux-arm64",
    ("linux", "arm64"): "cloudflared-linux-arm64",
    ("linux", "armv7l"): "cloudflared-linux-arm",
    ("darwin", "x86_64"): "cloudflared-darwin-amd64.tgz",
    ("darwin", "arm64"): "cloudflared-darwin-arm64.tgz",
    ("windows", "amd64"): "cloudflared-windows-amd64.exe",
    ("windows", "x86_64"): "cloudflared-windows-amd64.exe",
}

#: Wo ein mitgelieferter cloudflared liegt (Container-Abbild).
SYSTEM_CLOUDFLARED = Path("/opt/aquaticy/cloudflared/cloudflared")

#: Die Rechte, die das Cloudflare-Token braucht -- so steht es im Setup.
TOKEN_RIGHTS = ("Zone → Zone → Lesen", "Zone → DNS → Bearbeiten",
                "Konto → Cloudflare Tunnel → Bearbeiten")


class WebsiteError(RuntimeError):
    """Etwas an der Website klappt nicht -- mit einem Satz, den man versteht."""


# ---------------------------------------------------------------------------
# Eingaben
# ---------------------------------------------------------------------------
def clean_domain(roh: str) -> str:
    """Die Domain in der Form, die Cloudflare und Let's Encrypt erwarten.

    Nimmt auch "https://chat.example.de/" und Umlaut-Domains an.
    """
    text = str(roh or "").strip().lower()
    for vorne in ("https://", "http://"):
        if text.startswith(vorne):
            text = text[len(vorne):]
    text = text.split("/", 1)[0].rstrip(".")
    if not text or ":" in text or "@" in text or "*" in text:
        raise WebsiteError("Das ist keine Domain. Beispiel: chat.example.de")
    try:
        text = text.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise WebsiteError("Das ist keine Domain. Beispiel: chat.example.de") from exc
    if not DOMAIN_RE.fullmatch(text):
        raise WebsiteError("Das ist keine Domain. Beispiel: chat.example.de")
    return text


def clean_email(roh: str) -> str:
    text = str(roh or "").strip()
    if text and not EMAIL_RE.fullmatch(text):
        raise WebsiteError("Die E-Mail-Adresse sieht nicht richtig aus.")
    return text


def clean_token(roh: str) -> str:
    text = str(roh or "").strip()
    if not TOKEN_RE.fullmatch(text):
        raise WebsiteError("Das Cloudflare-Token sieht nicht richtig aus.")
    return text


@dataclass(slots=True)
class SiteConfig:
    """Was in der ``.env`` steht."""

    domain: str
    token: str
    email: str = ""
    staging: bool = False
    public_port: int = DEFAULT_PUBLIC_PORT

    @classmethod
    def from_env(cls, environ: Any = None) -> SiteConfig | None:
        """Die Website aus der Umgebung -- oder None, wenn keine eingerichtet ist."""
        umgebung = os.environ if environ is None else environ
        roh = str(umgebung.get(DOMAIN_ENV, "") or "").strip()
        if not roh:
            return None
        try:
            port = int(str(umgebung.get(PUBLIC_PORT_ENV, "") or DEFAULT_PUBLIC_PORT))
        except ValueError:
            port = DEFAULT_PUBLIC_PORT
        if not 1024 <= port <= 65535:
            port = DEFAULT_PUBLIC_PORT
        return cls(
            domain=clean_domain(roh),
            token=str(umgebung.get(TOKEN_ENV, "") or "").strip(),
            email=str(umgebung.get(EMAIL_ENV, "") or "").strip(),
            staging=str(umgebung.get(STAGING_ENV, "")).strip().lower() in {"1", "true", "ja", "on"},
            public_port=port,
        )

    @property
    def tunnel_name(self) -> str:
        return ("aquaticy-" + self.domain.replace(".", "-"))[:60]


# ---------------------------------------------------------------------------
# Was Aquaticy sich merkt (data_dir/website, nur fuer den eigenen Nutzer lesbar)
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class SiteState:
    domain: str
    zone_id: str = ""
    account_id: str = ""
    tunnel_id: str = ""
    tunnel_token: str = ""

    def complete(self) -> bool:
        return bool(ID_RE.fullmatch(self.zone_id) and ID_RE.fullmatch(self.account_id)
                    and UUID_RE.fullmatch(self.tunnel_id)
                    and TUNNEL_TOKEN_RE.fullmatch(self.tunnel_token))


def site_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "website"


def _privat_schreiben(pfad: Path, daten: bytes) -> None:
    """Schreibt eine Datei, die nur der eigene Nutzer lesen kann -- atomar."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        pfad.parent.chmod(0o700)
    fd, tmp = tempfile.mkstemp(dir=pfad.parent, prefix=".neu-")
    try:
        with os.fdopen(fd, "wb") as datei:
            datei.write(daten)
        with contextlib.suppress(OSError):
            os.chmod(tmp, 0o600)
        os.replace(tmp, pfad)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def load_state(data_dir: Path, domain: str) -> SiteState | None:
    pfad = site_dir(data_dir) / "site.json"
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(daten, dict) or daten.get("domain") != domain:
        return None
    zustand = SiteState(**{k: str(daten.get(k) or "") for k in
                           ("domain", "zone_id", "account_id", "tunnel_id", "tunnel_token")})
    return zustand if zustand.complete() else None


def save_state(data_dir: Path, zustand: SiteState) -> None:
    _privat_schreiben(site_dir(data_dir) / "site.json",
                      json.dumps(asdict(zustand), indent=2).encode())


def forget_state(data_dir: Path) -> None:
    ordner = site_dir(data_dir)
    for name in ("site.json", "cert.pem", "key.pem", "selfsigned-cert.pem",
                 "selfsigned-key.pem", "acme-account.key", "cloudflared.log"):
        with contextlib.suppress(OSError):
            (ordner / name).unlink()


# ---------------------------------------------------------------------------
# Cloudflare
# ---------------------------------------------------------------------------
def _guarded(timeout: float = 30.0, **headers: str) -> httpx.Client:
    from aquaticy import __version__, netguard

    kopf = {"User-Agent": f"aquaticy/{__version__}", **headers}
    return netguard.guarded_client(timeout=timeout, follow_redirects=False, headers=kopf)


def _lesen(antwort: httpx.Response) -> bytes:
    from aquaticy.netguard import read_response

    return read_response(antwort, MAX_API_BYTES, time.monotonic() + 60.0)


def _kurz(text: Any, grenze: int = 200) -> str:
    return " ".join(str(text or "").split())[:grenze]


class Cloudflare:
    """Die paar Aufrufe an die Cloudflare-API, die Aquaticy braucht."""

    def __init__(self, token: str, *, http: httpx.Client | None = None) -> None:
        self._token = clean_token(token)
        self._eigener = http is None
        self._http = http or _guarded()

    def close(self) -> None:
        if self._eigener:
            self._http.close()

    def __enter__(self) -> Cloudflare:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def call(self, methode: str, pfad: str, *, json_body: Any = None,
             params: dict[str, str] | None = None) -> Any:
        try:
            with self._http.stream(methode, CF_API + pfad, json=json_body, params=params,
                                   headers={"Authorization": f"Bearer {self._token}"}) as antwort:
                status = antwort.status_code
                roh = _lesen(antwort)
        except httpx.HTTPError as exc:
            raise WebsiteError(f"Cloudflare ist nicht erreichbar ({type(exc).__name__}).") from exc
        try:
            daten = json.loads(roh) if roh else {}
        except ValueError:
            daten = {}
        if status in (401, 403) or (isinstance(daten, dict) and any(
                isinstance(f, dict) and f.get("code") in (9109, 10000)
                for f in daten.get("errors") or [])):
            raise WebsiteError("Cloudflare lehnt das Token ab. Es braucht diese Rechte: "
                               + ", ".join(TOKEN_RIGHTS) + ".")
        if not isinstance(daten, dict) or not daten.get("success"):
            fehler = (daten.get("errors") or [{}])[0] if isinstance(daten, dict) else {}
            text = _kurz(fehler.get("message") if isinstance(fehler, dict) else "")
            raise WebsiteError(f"Cloudflare sagt: {text or f'Fehler {status}'}")
        return daten.get("result")

    # -- Zone ---------------------------------------------------------------
    def zone_for(self, domain: str) -> tuple[str, str]:
        """(Zonen-Kennung, Konto-Kennung) der Zone, zu der *domain* gehoert."""
        teile = domain.split(".")
        for start in range(len(teile) - 1):
            name = ".".join(teile[start:])
            zonen = self.call("GET", "/zones", params={"name": name})
            for zone in zonen or []:
                if not isinstance(zone, dict) or zone.get("name") != name:
                    continue
                if zone.get("status") != "active":
                    raise WebsiteError(
                        f"Die Zone {name} ist bei Cloudflare noch nicht aktiv. Die Nameserver "
                        "deiner Domain müssen auf Cloudflare zeigen.")
                zone_id = str(zone.get("id") or "")
                konto = str((zone.get("account") or {}).get("id") or "")
                if ID_RE.fullmatch(zone_id) and ID_RE.fullmatch(konto):
                    return zone_id, konto
        raise WebsiteError(f"{domain} liegt nicht bei Cloudflare, oder das Token darf die "
                           "Zone nicht sehen.")

    # -- Tunnel -------------------------------------------------------------
    def tunnel(self, konto: str, name: str) -> str:
        """Die Kennung des Tunnels *name* -- angelegt, wenn es ihn noch nicht gibt."""
        gefunden = self.call("GET", f"/accounts/{konto}/cfd_tunnel",
                             params={"name": name, "is_deleted": "false"})
        for tunnel in gefunden or []:
            if (isinstance(tunnel, dict) and tunnel.get("name") == name
                    and not tunnel.get("deleted_at")
                    and UUID_RE.fullmatch(str(tunnel.get("id") or ""))):
                return str(tunnel["id"])
        neu = self.call("POST", f"/accounts/{konto}/cfd_tunnel",
                        json_body={"name": name, "config_src": "cloudflare"})
        kennung = str((neu or {}).get("id") or "")
        if not UUID_RE.fullmatch(kennung):
            raise WebsiteError("Cloudflare hat den Tunnel nicht angelegt.")
        return kennung

    def tunnel_token(self, konto: str, tunnel_id: str) -> str:
        token = self.call("GET", f"/accounts/{konto}/cfd_tunnel/{tunnel_id}/token")
        if not isinstance(token, str) or not TUNNEL_TOKEN_RE.fullmatch(token):
            raise WebsiteError("Cloudflare hat kein Tunnel-Token geliefert.")
        return token

    def set_ingress(self, konto: str, tunnel_id: str, domain: str, port: int, *,
                    ca_pool: str = "") -> None:
        """Wohin der Tunnel geht: zum Eingang auf 127.0.0.1.

        cloudflared prueft das Zertifikat immer gegen die Domain. Bis das echte
        von Let's Encrypt da ist, vertraut es genau dem selbst ausgestellten
        (*ca_pool*) -- nie "ungeprueft" (``noTLSVerify``).
        """
        herkunft: dict[str, Any] = {"originServerName": domain}
        if ca_pool:
            herkunft["caPool"] = ca_pool
        self.call("PUT", f"/accounts/{konto}/cfd_tunnel/{tunnel_id}/configurations", json_body={
            "config": {"ingress": [
                {"hostname": domain, "service": f"https://localhost:{int(port)}",
                 "originRequest": herkunft},
                {"service": "http_status:404"},
            ]}})

    def delete_tunnel(self, konto: str, tunnel_id: str) -> None:
        with contextlib.suppress(WebsiteError):
            self.call("DELETE", f"/accounts/{konto}/cfd_tunnel/{tunnel_id}/connections")
        self.call("DELETE", f"/accounts/{konto}/cfd_tunnel/{tunnel_id}")

    # -- DNS ----------------------------------------------------------------
    def records(self, zone: str, name: str) -> list[dict[str, Any]]:
        gefunden = self.call("GET", f"/zones/{zone}/dns_records", params={"name": name})
        return [r for r in gefunden or [] if isinstance(r, dict)]

    def point_domain(self, zone: str, domain: str, tunnel_id: str) -> None:
        """Laesst *domain* auf den Tunnel zeigen. Fremde Eintraege bleiben stehen."""
        ziel = f"{tunnel_id}.cfargotunnel.com"
        for eintrag in self.records(zone, domain):
            art, inhalt = str(eintrag.get("type") or ""), str(eintrag.get("content") or "")
            kennung = str(eintrag.get("id") or "")
            if art == "CNAME" and inhalt.endswith(".cfargotunnel.com") and ID_RE.fullmatch(kennung):
                if inhalt != ziel or not eintrag.get("proxied"):
                    self.call("PATCH", f"/zones/{zone}/dns_records/{kennung}",
                              json_body={"type": "CNAME", "name": domain, "content": ziel,
                                         "proxied": True})
                return
            if art in ("A", "AAAA", "CNAME"):
                raise WebsiteError(
                    f"Für {domain} gibt es bei Cloudflare schon einen Eintrag ({art} → "
                    f"{_kurz(inhalt, 80)}). Lösch ihn dort oder nimm eine andere Subdomain.")
        self.call("POST", f"/zones/{zone}/dns_records", json_body={
            "type": "CNAME", "name": domain, "content": ziel, "proxied": True,
            "comment": "Aquaticy"})

    def remove_domain(self, zone: str, domain: str, tunnel_id: str) -> None:
        ziel = f"{tunnel_id}.cfargotunnel.com"
        for eintrag in self.records(zone, domain):
            if eintrag.get("type") == "CNAME" and eintrag.get("content") == ziel:
                self.delete_record(zone, str(eintrag.get("id") or ""))

    def add_txt(self, zone: str, name: str, wert: str) -> str:
        neu = self.call("POST", f"/zones/{zone}/dns_records", json_body={
            "type": "TXT", "name": name, "content": wert, "ttl": 60,
            "comment": "Aquaticy: Pruefung fuer Let's Encrypt"})
        kennung = str((neu or {}).get("id") or "")
        if not ID_RE.fullmatch(kennung):
            raise WebsiteError("Cloudflare hat den Prüfeintrag nicht angelegt.")
        return kennung

    def delete_record(self, zone: str, kennung: str) -> None:
        if ID_RE.fullmatch(kennung):
            self.call("DELETE", f"/zones/{zone}/dns_records/{kennung}")


def provision(config: SiteConfig, data_dir: Path, port: int, *,
              cloudflare: Cloudflare | None = None,
              progress: Callable[[str], None] | None = None) -> SiteState:
    """Richtet Tunnel und Domain bei Cloudflare ein. Laesst sich gefahrlos wiederholen."""
    melden = progress or (lambda _text: None)
    cf = cloudflare or Cloudflare(config.token)
    try:
        melden("Suche die Domain bei Cloudflare …")
        zone, konto = cf.zone_for(config.domain)
        melden("Lege den Tunnel an …")
        tunnel_id = cf.tunnel(konto, config.tunnel_name)
        cf.set_ingress(konto, tunnel_id, config.domain, port,
                       ca_pool=ca_pool_for(data_dir, config.domain))
        melden(f"Trage {config.domain} für den Tunnel ein …")
        cf.point_domain(zone, config.domain, tunnel_id)
        zustand = SiteState(domain=config.domain, zone_id=zone, account_id=konto,
                            tunnel_id=tunnel_id, tunnel_token=cf.tunnel_token(konto, tunnel_id))
    finally:
        if cloudflare is None:
            cf.close()
    save_state(data_dir, zustand)
    return zustand


# ---------------------------------------------------------------------------
# Let's Encrypt (ACME, RFC 8555) -- Pruefung per DNS-Eintrag
# ---------------------------------------------------------------------------
def _b64(daten: bytes) -> str:
    return base64.urlsafe_b64encode(daten).rstrip(b"=").decode("ascii")


def _problem(roh: bytes) -> tuple[str, str]:
    try:
        daten = json.loads(roh)
    except ValueError:
        return "", ""
    if not isinstance(daten, dict):
        return "", ""
    return str(daten.get("type") or ""), _kurz(daten.get("detail"))


class Acme:
    """Ein schlanker ACME-Client: Konto, Auftrag, DNS-Pruefung, Zertifikat."""

    def __init__(self, directory: str, account_key: Any, *, http: httpx.Client,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._http = http
        self._key = account_key
        self._sleep = sleep
        self._nonce = ""
        self.kid = ""
        try:
            verzeichnis = json.loads(self._get(directory))
        except ValueError as exc:
            raise WebsiteError("Let's Encrypt hat unerwartet geantwortet.") from exc
        noetig = ("newNonce", "newAccount", "newOrder")
        if not isinstance(verzeichnis, dict) or not all(
                isinstance(verzeichnis.get(k), str) for k in noetig):
            raise WebsiteError("Let's Encrypt hat unerwartet geantwortet.")
        self.directory = verzeichnis

    def _get(self, url: str) -> bytes:
        try:
            with self._http.stream("GET", url) as antwort:
                roh = _lesen(antwort)
                if antwort.status_code != 200:
                    raise WebsiteError(f"Let's Encrypt antwortet mit {antwort.status_code}.")
                return roh
        except httpx.HTTPError as exc:
            raise WebsiteError(f"Let's Encrypt ist nicht erreichbar ({type(exc).__name__}).") \
                from exc

    # -- Signieren ----------------------------------------------------------
    def jwk(self) -> dict[str, str]:
        zahlen = self._key.public_key().public_numbers()
        return {"crv": "P-256", "kty": "EC", "x": _b64(zahlen.x.to_bytes(32, "big")),
                "y": _b64(zahlen.y.to_bytes(32, "big"))}

    def thumbprint(self) -> str:
        roh = json.dumps(self.jwk(), sort_keys=True, separators=(",", ":")).encode()
        return _b64(hashlib.sha256(roh).digest())

    def _new_nonce(self) -> str:
        try:
            antwort = self._http.head(self.directory["newNonce"])
        except httpx.HTTPError as exc:
            raise WebsiteError(f"Let's Encrypt ist nicht erreichbar ({type(exc).__name__}).") \
                from exc
        nonce = antwort.headers.get("Replay-Nonce", "")
        if not nonce:
            raise WebsiteError("Let's Encrypt hat keine Nonce geliefert.")
        return nonce

    def _signed(self, url: str, payload: Any) -> bytes:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

        kopf: dict[str, Any] = {"alg": "ES256", "nonce": self._nonce or self._new_nonce(),
                                "url": url}
        if self.kid:
            kopf["kid"] = self.kid
        else:
            kopf["jwk"] = self.jwk()
        geschuetzt = _b64(json.dumps(kopf).encode())
        inhalt = "" if payload is None else _b64(json.dumps(payload).encode())
        der = self._key.sign(f"{geschuetzt}.{inhalt}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        signatur = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return json.dumps({"protected": geschuetzt, "payload": inhalt,
                           "signature": _b64(signatur)}).encode()

    def post(self, url: str, payload: Any, *, accept: str = "") -> tuple[httpx.Headers, bytes]:
        """Ein signierter Aufruf. ``payload=None`` ist ein POST-as-GET."""
        for _ in range(4):
            kopf = {"Content-Type": "application/jose+json"}
            if accept:
                kopf["Accept"] = accept
            koerper = self._signed(url, payload)
            self._nonce = ""
            try:
                with self._http.stream("POST", url, content=koerper, headers=kopf) as antwort:
                    roh = _lesen(antwort)
                    status, header = antwort.status_code, antwort.headers
            except httpx.HTTPError as exc:
                raise WebsiteError(
                    f"Let's Encrypt ist nicht erreichbar ({type(exc).__name__}).") from exc
            self._nonce = header.get("Replay-Nonce", "")
            if status < 400:
                return header, roh
            art, text = _problem(roh)
            if art.endswith(":badNonce"):
                continue
            if art.endswith(":rateLimited"):
                raise WebsiteError("Let's Encrypt bremst gerade (zu viele Versuche). "
                                   "Aquaticy versucht es später noch einmal.")
            raise WebsiteError(f"Let's Encrypt sagt: {text or f'Fehler {status}'}")
        raise WebsiteError("Let's Encrypt lehnt die Anfragen ab (Nonce).")

    def _json(self, roh: bytes) -> dict[str, Any]:
        try:
            daten = json.loads(roh)
        except ValueError as exc:
            raise WebsiteError("Let's Encrypt hat unerwartet geantwortet.") from exc
        if not isinstance(daten, dict):
            raise WebsiteError("Let's Encrypt hat unerwartet geantwortet.")
        return daten

    # -- Ablauf -------------------------------------------------------------
    def register(self, email: str = "") -> None:
        anfrage: dict[str, Any] = {"termsOfServiceAgreed": True}
        if email:
            anfrage["contact"] = [f"mailto:{email}"]
        kopf, _ = self.post(self.directory["newAccount"], anfrage)
        self.kid = kopf.get("Location", "")
        if not self.kid.startswith("https://"):
            raise WebsiteError("Let's Encrypt hat kein Konto angelegt.")

    def _poll(self, url: str, gut: set[str], schlecht: set[str]) -> dict[str, Any]:
        frist = time.monotonic() + ACME_POLL_SECONDS
        while True:
            kopf, roh = self.post(url, None)
            daten = self._json(roh)
            stand = str(daten.get("status") or "")
            if stand in gut:
                return daten
            if stand in schlecht:
                raise WebsiteError("Let's Encrypt hat die Prüfung abgelehnt: "
                                   + (_acme_detail(daten) or stand))
            if time.monotonic() > frist:
                raise WebsiteError("Let's Encrypt braucht zu lange.")
            warten = 2.0
            with contextlib.suppress(ValueError):
                warten = min(30.0, max(1.0, float(kopf.get("Retry-After", "2"))))
            self._sleep(warten)

    def certificate(self, domain: str, publish: Callable[[str, str], Callable[[], None]],
                    wait: Callable[[str, str], None]) -> tuple[bytes, bytes]:
        """Holt ein Zertifikat fuer *domain*. Returns: (Schluessel, Zertifikatskette) als PEM.

        *publish(name, wert)* legt den TXT-Eintrag an und gibt zurueck, wie er
        wieder verschwindet. *wait(name, wert)* wartet, bis er im DNS steht.
        """
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        kopf, roh = self.post(self.directory["newOrder"],
                              {"identifiers": [{"type": "dns", "value": domain}]})
        auftrag_url = kopf.get("Location", "")
        auftrag = self._json(roh)
        if not auftrag_url.startswith("https://"):
            raise WebsiteError("Let's Encrypt hat keinen Auftrag angelegt.")
        for authz_url in auftrag.get("authorizations") or []:
            _, roh = self.post(str(authz_url), None)
            authz = self._json(roh)
            if authz.get("status") == "valid":
                continue
            pruefung = next((c for c in authz.get("challenges") or []
                             if isinstance(c, dict) and c.get("type") == "dns-01"), None)
            if pruefung is None:
                raise WebsiteError("Let's Encrypt bietet keine DNS-Prüfung an.")
            token = str(pruefung.get("token") or "")
            if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", token):
                raise WebsiteError("Let's Encrypt hat unerwartet geantwortet.")
            wert = _b64(hashlib.sha256(f"{token}.{self.thumbprint()}".encode()).digest())
            name = "_acme-challenge." + domain
            aufraeumen = publish(name, wert)
            try:
                wait(name, wert)
                self.post(str(pruefung.get("url") or ""), {})
                self._poll(str(authz_url), {"valid"}, {"invalid", "deactivated", "expired",
                                                       "revoked"})
            finally:
                with contextlib.suppress(Exception):
                    aufraeumen()
        auftrag = self._poll(auftrag_url, {"ready", "valid"}, {"invalid"})
        if auftrag.get("status") != "ready":
            raise WebsiteError("Let's Encrypt hat den Auftrag schon abgeschlossen -- "
                               "bitte noch einmal versuchen.")
        schluessel = ec.generate_private_key(ec.SECP256R1())
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
               .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]),
                              critical=False)
               .sign(schluessel, hashes.SHA256()))
        self.post(str(auftrag.get("finalize") or ""),
                  {"csr": _b64(csr.public_bytes(serialization.Encoding.DER))})
        auftrag = self._poll(auftrag_url, {"valid"}, {"invalid"})
        _, kette = self.post(str(auftrag.get("certificate") or ""), None,
                             accept="application/pem-certificate-chain")
        schluessel_pem = schluessel.private_bytes(serialization.Encoding.PEM,
                                                  serialization.PrivateFormat.PKCS8,
                                                  serialization.NoEncryption())
        _check_chain(kette, schluessel_pem, domain)
        return schluessel_pem, kette


def _acme_detail(daten: dict[str, Any]) -> str:
    for pruefung in daten.get("challenges") or []:
        if isinstance(pruefung, dict) and isinstance(pruefung.get("error"), dict):
            return _kurz(pruefung["error"].get("detail"))
    fehler = daten.get("error")
    return _kurz(fehler.get("detail")) if isinstance(fehler, dict) else ""


def _check_chain(kette: bytes, schluessel_pem: bytes, domain: str) -> None:
    """Passt das Zertifikat zu Schluessel und Domain? Sonst wird nichts gespeichert."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    try:
        zertifikate = x509.load_pem_x509_certificates(kette)
        schluessel = serialization.load_pem_private_key(schluessel_pem, password=None)
    except ValueError as exc:
        raise WebsiteError("Das Zertifikat von Let's Encrypt ist unlesbar.") from exc
    erstes = zertifikate[0]
    format_ = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if erstes.public_key().public_bytes(*format_) != schluessel.public_key().public_bytes(
            *format_):
        raise WebsiteError("Das Zertifikat passt nicht zum Schlüssel.")
    if domain not in _domains_of(erstes):
        raise WebsiteError("Das Zertifikat gilt nicht für diese Domain.")


def _domains_of(zertifikat: Any) -> list[str]:
    from cryptography import x509

    try:
        san = zertifikat.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        return []
    return [str(name) for name in san.value.get_values_for_type(x509.DNSName)]


def _account_key(data_dir: Path) -> Any:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    pfad = site_dir(data_dir) / "acme-account.key"
    with contextlib.suppress(OSError, ValueError, TypeError):
        schluessel = serialization.load_pem_private_key(pfad.read_bytes(), password=None)
        if isinstance(schluessel, ec.EllipticCurvePrivateKey):
            return schluessel
    schluessel = ec.generate_private_key(ec.SECP256R1())
    _privat_schreiben(pfad, schluessel.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    return schluessel


def wait_for_txt(name: str, wert: str, *, http: httpx.Client | None = None,
                 timeout: float = DNS_WAIT_SECONDS,
                 sleep: Callable[[float], None] = time.sleep) -> bool:
    """Wartet, bis der Pruefeintrag im DNS steht. Returns: ob er gesehen wurde.

    Cloudflare verteilt Eintraege in Sekunden. Kommt die Antwort trotzdem
    nicht, geht es weiter -- Let's Encrypt fragt die Nameserver selbst.
    """
    eigener = http is None
    http = http or _guarded(timeout=10.0, Accept="application/dns-json")
    frist = time.monotonic() + timeout
    try:
        while time.monotonic() < frist:
            with contextlib.suppress(httpx.HTTPError, ValueError):
                with http.stream("GET", DOH_URL, params={"name": name, "type": "TXT"},
                                 headers={"Accept": "application/dns-json"}) as antwort:
                    daten = json.loads(_lesen(antwort))
                for eintrag in (daten.get("Answer") or []) if isinstance(daten, dict) else []:
                    if isinstance(eintrag, dict) and wert in str(eintrag.get("data") or ""):
                        return True
            sleep(3.0)
    finally:
        if eigener:
            http.close()
    return False


def cert_paths(data_dir: Path) -> tuple[Path, Path]:
    return site_dir(data_dir) / "cert.pem", site_dir(data_dir) / "key.pem"


def certificate_expiry(data_dir: Path, domain: str) -> datetime | None:
    """Bis wann das Zertifikat fuer *domain* gilt -- oder None, wenn es keins gibt."""
    from cryptography import x509

    zert, _ = cert_paths(data_dir)
    try:
        erstes = x509.load_pem_x509_certificates(zert.read_bytes())[0]
    except (OSError, ValueError, IndexError):
        return None
    if domain not in _domains_of(erstes):
        return None
    return erstes.not_valid_after_utc


def certificate_valid(data_dir: Path, domain: str, *, now: datetime | None = None) -> bool:
    ablauf = certificate_expiry(data_dir, domain)
    jetzt = now or datetime.now(UTC)
    return ablauf is not None and ablauf > jetzt


def needs_certificate(data_dir: Path, domain: str, *, now: datetime | None = None) -> bool:
    ablauf = certificate_expiry(data_dir, domain)
    jetzt = now or datetime.now(UTC)
    return ablauf is None or ablauf - jetzt < timedelta(days=RENEW_DAYS)


def obtain_certificate(config: SiteConfig, data_dir: Path, zone: str, *,
                       cloudflare: Cloudflare | None = None, http: httpx.Client | None = None,
                       wait: Callable[[str, str], None] | None = None,
                       sleep: Callable[[float], None] = time.sleep) -> datetime:
    """Holt (oder erneuert) das Zertifikat. Returns: bis wann es gilt."""
    cf = cloudflare or Cloudflare(config.token)
    eigener = http is None
    http = http or _guarded(timeout=30.0)
    try:
        acme = Acme(ACME_STAGING if config.staging else ACME_DIRECTORY, _account_key(data_dir),
                    http=http, sleep=sleep)
        acme.register(config.email)

        def veroeffentlichen(name: str, wert: str) -> Callable[[], None]:
            kennung = cf.add_txt(zone, name, wert)
            return lambda: cf.delete_record(zone, kennung)

        def warten(name: str, wert: str) -> None:
            if wait is not None:
                wait(name, wert)
                return
            sleep(5.0)
            wait_for_txt(name, wert, sleep=sleep)

        schluessel, kette = acme.certificate(config.domain, veroeffentlichen, warten)
    finally:
        if eigener:
            http.close()
        if cloudflare is None:
            cf.close()
    zert, key = cert_paths(data_dir)
    _privat_schreiben(key, schluessel)
    _privat_schreiben(zert, kette)
    ablauf = certificate_expiry(data_dir, config.domain)
    if ablauf is None:
        raise WebsiteError("Das neue Zertifikat ließ sich nicht lesen.")
    return ablauf


def self_signed(data_dir: Path, domain: str) -> tuple[Path, Path]:
    """Ein selbst ausgestelltes Zertifikat fuer den Weg cloudflared -> Aquaticy,
    solange das echte noch fehlt. Es verlaesst den Rechner nie."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    ordner = site_dir(data_dir)
    zert, key = ordner / "selfsigned-cert.pem", ordner / "selfsigned-key.pem"
    with contextlib.suppress(OSError, ValueError, IndexError):
        bisher = x509.load_pem_x509_certificates(zert.read_bytes())[0]
        if (domain in _domains_of(bisher) and key.is_file()
                and bisher.not_valid_after_utc - datetime.now(UTC) > timedelta(days=30)):
            return zert, key
    schluessel = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
    jetzt = datetime.now(UTC)
    zertifikat = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                  .public_key(schluessel.public_key()).serial_number(x509.random_serial_number())
                  .not_valid_before(jetzt - timedelta(minutes=5))
                  .not_valid_after(jetzt + timedelta(days=365))
                  .add_extension(x509.SubjectAlternativeName(
                      [x509.DNSName(domain), x509.DNSName("localhost")]), critical=False)
                  .sign(schluessel, hashes.SHA256()))
    _privat_schreiben(key, schluessel.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    _privat_schreiben(zert, zertifikat.public_bytes(serialization.Encoding.PEM))
    return zert, key


def ca_pool_for(data_dir: Path, domain: str) -> str:
    """Wem cloudflared vertrauen soll: "" (echtes Zertifikat, die ueblichen
    Stellen) oder der Pfad des selbst ausgestellten."""
    if certificate_valid(data_dir, domain):
        return ""
    zert, _ = self_signed(data_dir, domain)
    return str(zert.resolve())


def tls_context(data_dir: Path, domain: str) -> tuple[ssl.SSLContext, bool]:
    """Der TLS-Kontext fuer den Tunnel-Eingang. Returns: (Kontext, echtes Zertifikat?)"""
    kontext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    kontext.minimum_version = ssl.TLSVersion.TLSv1_2
    echt = load_certificate(kontext, data_dir, domain)
    return kontext, echt


def load_certificate(kontext: ssl.SSLContext, data_dir: Path, domain: str) -> bool:
    """Laedt das beste Zertifikat in *kontext* -- neue Verbindungen bekommen es sofort."""
    if certificate_valid(data_dir, domain):
        zert, key = cert_paths(data_dir)
        with contextlib.suppress(ssl.SSLError, OSError):
            kontext.load_cert_chain(zert, key)
            return True
    zert, key = self_signed(data_dir, domain)
    kontext.load_cert_chain(zert, key)
    return False


# ---------------------------------------------------------------------------
# cloudflared
# ---------------------------------------------------------------------------
def cloudflared_asset(system: str = "", machine: str = "") -> str:
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    return CLOUDFLARED_ASSETS.get((system, machine), "")


def _exe_name() -> str:
    return "cloudflared.exe" if os.name == "nt" else "cloudflared"


def managed_cloudflared(data_dir: Path) -> Path:
    return Path(data_dir) / "cloudflared" / _exe_name()


def find_cloudflared(data_dir: Path) -> Path | None:
    """Ein vorhandenes cloudflared: eingetragen, selbst geladen, mitgeliefert, im Pfad."""
    from aquaticy.llamacpp import _trusted

    eingetragen = os.environ.get(CLOUDFLARED_ENV, "").strip()
    if eingetragen:
        pfad = Path(eingetragen)
        return pfad if pfad.is_file() else None
    eigener = managed_cloudflared(data_dir)
    if eigener.is_file():
        return eigener
    if SYSTEM_CLOUDFLARED.is_file() and _trusted(SYSTEM_CLOUDFLARED.parent):
        return SYSTEM_CLOUDFLARED
    gefunden = shutil.which("cloudflared")
    return Path(gefunden) if gefunden else None


def _cloudflared_release(http: httpx.Client) -> dict[str, Any]:
    from aquaticy.llamacpp import _headers

    try:
        with http.stream("GET", CLOUDFLARED_API + "/releases/latest", headers=_headers()) \
                as antwort:
            roh = _lesen(antwort)
            status = antwort.status_code
    except httpx.HTTPError as exc:
        raise WebsiteError(f"GitHub ist nicht erreichbar ({type(exc).__name__}).") from exc
    if status != 200:
        raise WebsiteError(f"GitHub antwortet mit {status}.")
    try:
        daten = json.loads(roh)
    except ValueError as exc:
        raise WebsiteError("GitHub hat unerwartet geantwortet.") from exc
    if not isinstance(daten, dict) or not RELEASE_TAG_RE.fullmatch(str(daten.get("tag_name"))):
        raise WebsiteError("GitHub hat unerwartet geantwortet.")
    return daten


def install_cloudflared(data_dir: Path, *, target: Path | None = None,
                        http: httpx.Client | None = None,
                        check: Callable[[Path], bool] | None = None) -> Path:
    """Laedt cloudflared von GitHub -- nur mit veroeffentlichter Pruefsumme.

    Ohne *target* landet es im Datenordner (``cloudflared/``).
    """
    from aquaticy import llamacpp

    name = cloudflared_asset()
    if not name:
        raise WebsiteError("Für dieses System gibt es kein fertiges cloudflared. Installier es "
                           f"selbst und trag den Pfad in {CLOUDFLARED_ENV} ein.")
    eigener = http is None
    http = http or llamacpp.client()
    ziel = target or managed_cloudflared(data_dir)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    arbeit = Path(tempfile.mkdtemp(dir=ziel.parent, prefix=".neu-"))
    try:
        daten = _cloudflared_release(http)
        asset = next((a for a in daten.get("assets") or []
                      if isinstance(a, dict) and a.get("name") == name), None)
        if asset is None:
            raise WebsiteError(f"Die Veröffentlichung enthält {name} nicht.")
        datei = arbeit / name
        try:
            llamacpp.download(asset, datei, http=http)
        except llamacpp.LlamaError as exc:
            raise WebsiteError(str(exc)) from exc
        if name.endswith(".tgz"):
            ausgepackt = arbeit / "inhalt"
            ausgepackt.mkdir()
            try:
                llamacpp.unpack_tar(datei, ausgepackt)
            except llamacpp.LlamaError as exc:
                raise WebsiteError(str(exc)) from exc
            programm = llamacpp._find(ausgepackt, "cloudflared")
            if programm is None:
                raise WebsiteError("Im Archiv fehlt cloudflared.")
            datei = programm
        datei.chmod(0o755)
        if not (check or _starts)(datei):
            raise WebsiteError("cloudflared startet auf diesem System nicht.")
        os.replace(datei, ziel)
        return ziel
    finally:
        shutil.rmtree(arbeit, ignore_errors=True)
        if eigener:
            http.close()


def _starts(programm: Path) -> bool:
    try:
        fertig = subprocess.run([str(programm), "--version"], capture_output=True, timeout=60,
                                check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return False
    return fertig.returncode == 0


#: Was cloudflared aus der Umgebung bekommt. Die Schluessel von Aquaticy
#: (Modell-Anbieter, Cloudflare-API) braucht es nicht -- also bekommt es sie nicht.
TUNNEL_ENV_KEEP = (
    "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TMPDIR", "TEMP", "TMP", "TZ", "LANG",
    "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY",
    "https_proxy", "http_proxy", "no_proxy",
)


def tunnel_env(token: str) -> dict[str, str]:
    umgebung = {name: os.environ[name] for name in TUNNEL_ENV_KEEP if os.environ.get(name)}
    umgebung["TUNNEL_TOKEN"] = token
    umgebung["NO_AUTOUPDATE"] = "true"
    return umgebung


class Tunnel:
    """Haelt cloudflared am Laufen -- startet es neu, wenn es endet."""

    def __init__(self, data_dir: Path, token: Callable[[], str], *,
                 locate: Callable[[], Path | None] | None = None,
                 install: Callable[[], Path] | None = None,
                 popen: Callable[..., Any] = subprocess.Popen,
                 sleep: Callable[[float], bool] | None = None) -> None:
        self.data_dir = Path(data_dir)
        self._token = token
        self._locate = locate or (lambda: find_cloudflared(self.data_dir))
        self._install = install or (lambda: install_cloudflared(self.data_dir))
        self._popen = popen
        self._stop = threading.Event()
        self._sleep = sleep or (lambda sekunden: self._stop.wait(sekunden))
        self._proc: Any = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.phase = "aus"
        self.message = ""

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="aquaticy-tunnel", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            proc = self._proc
        if proc is not None:
            with contextlib.suppress(Exception):
                proc.terminate()
                proc.wait(timeout=10)
            with contextlib.suppress(Exception):
                if proc.poll() is None:
                    proc.kill()
        if self._thread is not None:
            self._thread.join(timeout=15)
        self.phase, self.message = "aus", ""

    def _set(self, phase: str, message: str = "") -> None:
        self.phase, self.message = phase, message[:200]

    def _binary(self) -> Path:
        gefunden = self._locate()
        if gefunden is not None:
            return gefunden
        self._set("laedt", "Lade cloudflared …")
        return self._install()

    def _run(self) -> None:
        versuch = 0
        while not self._stop.is_set():
            try:
                programm = self._binary()
                token = self._token()
                if not token:
                    raise WebsiteError("Die Website ist noch nicht eingerichtet.")
                self._set("startet", "Verbinde mit Cloudflare …")
                log = site_dir(self.data_dir) / "cloudflared.log"
                log.parent.mkdir(parents=True, exist_ok=True)
                with contextlib.suppress(OSError):
                    if log.stat().st_size > MAX_LOG_BYTES:
                        log.unlink()
                umgebung = tunnel_env(token)
                fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                with os.fdopen(fd, "ab") as ausgabe:
                    with self._lock:
                        if self._stop.is_set():
                            return
                        self._proc = self._popen(
                            [str(programm), "tunnel", "--no-autoupdate", "run"],
                            env=umgebung, stdin=subprocess.DEVNULL, stdout=ausgabe,
                            stderr=subprocess.STDOUT)
                    self._set("laeuft", "Mit Cloudflare verbunden.")
                    gestartet = time.monotonic()
                    code = self._proc.wait()
                if self._stop.is_set():
                    return
                if time.monotonic() - gestartet > 600:
                    versuch = 0
                self._set("fehler", f"cloudflared hat sich beendet (Code {code}). "
                                    "Details: website/cloudflared.log")
            except (WebsiteError, OSError) as exc:
                self._set("fehler", str(exc))
            pause = TUNNEL_BACKOFF[min(versuch, len(TUNNEL_BACKOFF) - 1)]
            versuch += 1
            if self._sleep(pause):
                return

    def status(self) -> dict[str, str]:
        return {"phase": self.phase, "message": self.message}


# ---------------------------------------------------------------------------
# Alles zusammen
# ---------------------------------------------------------------------------
@dataclass
class Website:
    """Haelt Domain, Zertifikat und Tunnel in Ordnung, solange Aquaticy laeuft."""

    config: SiteConfig
    data_dir: Path
    context: ssl.SSLContext | None = None
    port: int = 0
    strict: bool = False
    state: SiteState | None = None
    expiry: datetime | None = None
    message: str = ""
    tunnel: Tunnel | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    _next_try: float = 0.0
    _ingress: tuple[int, bool] | None = None
    #: Wartet zwischen den Schritten bei Let's Encrypt (Tests setzen das auf nichts).
    pause: Callable[[float], None] = time.sleep

    def tls(self) -> ssl.SSLContext:
        """Der Kontext fuer den Tunnel-Eingang -- vor dem Binden zu holen."""
        if self.context is None:
            self.context, self.strict = tls_context(self.data_dir, self.config.domain)
            self.expiry = certificate_expiry(self.data_dir, self.config.domain)
        return self.context

    def start(self, port: int) -> None:
        """Startet die Arbeit im Hintergrund: einrichten, Zertifikat, Tunnel."""
        self.port = int(port)
        self.tls()
        self.tunnel = Tunnel(self.data_dir, lambda: self.state.tunnel_token if self.state else "")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="aquaticy-website", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self.tunnel is not None:
            self.tunnel.stop()
        if self._thread is not None:
            self._thread.join(timeout=15)

    def _cloudflare(self) -> Cloudflare:
        return Cloudflare(self.config.token)

    def _run(self) -> None:
        pause = 60.0
        while not self._stop.is_set():
            try:
                self._step()
                pause, warten = 60.0, CHECK_SECONDS / 12
            except WebsiteError as exc:
                self.message = str(exc)
                print(f"  [Website] {exc}", flush=True)
                # Erst nach einer Minute, dann immer geduldiger -- ein falsches
                # Token soll Cloudflare nicht minuetlich behelligen.
                warten, pause = pause, min(pause * 2, 3600.0)
            except Exception as exc:  # pragma: no cover - die Website darf nie den Server kosten
                self.message = f"{type(exc).__name__}"
                print(f"  [Website] {type(exc).__name__}: {exc}", flush=True)
                warten, pause = pause, min(pause * 2, 3600.0)
            if self._stop.wait(warten):
                return

    def _step(self) -> None:
        if not self.config.token:
            raise WebsiteError(f"Für {self.config.domain} fehlt das Cloudflare-Token "
                               f"({TOKEN_ENV}).")
        if self.state is None:
            self.state = load_state(self.data_dir, self.config.domain)
        if self.state is None:
            self.message = "Richte Tunnel und Domain bei Cloudflare ein …"
            self.state = provision(self.config, self.data_dir, self.port)
        if self.tunnel is not None:
            self.tunnel.start()
        if needs_certificate(self.data_dir, self.config.domain) and time.monotonic() >= \
                self._next_try:
            self.message = "Hole das Zertifikat von Let's Encrypt …"
            try:
                with self._cloudflare() as cf:
                    self.expiry = obtain_certificate(self.config, self.data_dir,
                                                     self.state.zone_id, cloudflare=cf,
                                                     sleep=self.pause)
            except WebsiteError:
                self._next_try = time.monotonic() + RETRY_SECONDS
                raise
        echt = load_certificate(self.tls(), self.data_dir, self.config.domain)
        if self._ingress != (self.port, echt):
            # Der Tunnel muss wissen, wohin (Port) und wie streng er prueft.
            with self._cloudflare() as cf:
                cf.set_ingress(self.state.account_id, self.state.tunnel_id, self.config.domain,
                               self.port, ca_pool=ca_pool_for(self.data_dir, self.config.domain))
            self._ingress = (self.port, echt)
        self.strict = echt
        self.expiry = certificate_expiry(self.data_dir, self.config.domain)
        self.message = "Läuft." if echt else "Läuft (Zertifikat folgt)."

    def view(self) -> dict[str, Any]:
        return {
            "domain": self.config.domain,
            "url": f"https://{self.config.domain}/",
            "message": self.message,
            "certificate_until": self.expiry.isoformat() if self.expiry else "",
            "tunnel": self.tunnel.status() if self.tunnel else {"phase": "aus", "message": ""},
        }


def from_settings(data_dir: Path, environ: Any = None) -> Website | None:
    """Die Website aus der ``.env`` -- oder None. Eine kaputte Domain meldet sich laut."""
    config = SiteConfig.from_env(environ)
    if config is None:
        return None
    return Website(config=config, data_dir=Path(data_dir))


def main(argv: list[str] | None = None) -> int:
    """``python -m aquaticy.website install-cloudflared --dir /opt/aquaticy/cloudflared``

    Fuers Container-Abbild: cloudflared schon beim Bauen mitbringen.
    """
    import argparse

    parser = argparse.ArgumentParser(prog="python -m aquaticy.website")
    parser.add_argument("befehl", choices=["install-cloudflared"])
    parser.add_argument("--dir", default=str(SYSTEM_CLOUDFLARED.parent))
    args = parser.parse_args(argv)
    ordner = Path(args.dir)
    try:
        pfad = install_cloudflared(ordner, target=ordner / _exe_name())
    except WebsiteError as exc:
        print(f"cloudflared: {exc}")
        return 1
    print(f"cloudflared: {pfad}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
