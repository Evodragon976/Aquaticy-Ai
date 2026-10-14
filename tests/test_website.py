"""11.1.0: Eigene Website -- Domain, Cloudflare-Tunnel, Zertifikat, oeffentlicher Eingang.

Kein Netz: Cloudflare und Let's Encrypt sind nachgebaut. Der nachgebaute
ACME-Server prueft wirklich -- Signatur (ES256), Nonce, Adresse im Kopf und den
DNS-Eintrag der Pruefung -- und stellt das Zertifikat mit einer Test-CA aus.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import ssl
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.x509.oid import NameOID
from typer.testing import CliRunner

from aquaticy import website
from aquaticy.website import (
    Acme,
    Cloudflare,
    SiteConfig,
    Tunnel,
    WebsiteError,
    clean_domain,
    clean_email,
)

DOMAIN = "chat.example.de"
ZONE = "a" * 32
KONTO = "b" * 32
TUNNEL = "11111111-2222-3333-4444-555555555555"
TOKEN = "cf_" + "x" * 37
#: Wie ein echtes Tunnel-Token: Base64, mit "+", "/" und "=".
TUNNEL_TOKEN = "eyJhIjoi" + "Ab+/" * 12 + "Zz=="


def _b64(daten: bytes) -> str:
    return base64.urlsafe_b64encode(daten).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# -- Eingaben ------------------------------------------------------------------------------
@pytest.mark.parametrize(("roh", "erwartet"), [
    ("chat.example.de", "chat.example.de"),
    ("https://Chat.Example.de/", "chat.example.de"),
    ("http://chat.example.de/pfad?x=1", "chat.example.de"),
    ("bücher.example.de", "xn--bcher-kva.example.de"),
])
def test_domains_are_cleaned(roh: str, erwartet: str) -> None:
    assert clean_domain(roh) == erwartet


@pytest.mark.parametrize("roh", [
    "", "localhost", "chat", "chat.example.de:8443", "*.example.de", "user@example.de",
    "-chat.example.de", "chat..example.de", "a" * 300 + ".de",
])
def test_bad_domains_are_refused(roh: str) -> None:
    with pytest.raises(WebsiteError):
        clean_domain(roh)


def test_email_and_token_are_checked() -> None:
    assert clean_email("") == ""
    assert clean_email("jonas@example.de") == "jonas@example.de"
    with pytest.raises(WebsiteError):
        clean_email("kein mail")
    with pytest.raises(WebsiteError):
        Cloudflare("zu kurz")
    with pytest.raises(WebsiteError):
        Cloudflare("x" * 30 + "\nHost: boese")


def test_config_comes_from_the_environment() -> None:
    assert SiteConfig.from_env({}) is None
    config = SiteConfig.from_env({"AQUATICY_DOMAIN": "https://Chat.Example.de",
                                  "AQUATICY_CLOUDFLARE_TOKEN": TOKEN,
                                  "AQUATICY_PUBLIC_PORT": "80"})
    assert config is not None
    assert config.domain == DOMAIN
    assert config.public_port == website.DEFAULT_PUBLIC_PORT  # unter 1024 nicht
    assert config.tunnel_name == "aquaticy-chat-example-de"


# -- Cloudflare (nachgebaut) ----------------------------------------------------------------
class FakeCloudflare:
    def __init__(self) -> None:
        self.tunnels: list[dict[str, Any]] = []
        self.records: list[dict[str, Any]] = []
        self.ingress: dict[str, Any] = {}
        self.calls: list[tuple[str, str]] = []
        self.token_ok = True
        self.txt_override = ""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        pfad = request.url.path.removeprefix("/client/v4")
        self.calls.append((request.method, pfad))
        if request.headers.get("Authorization") != f"Bearer {TOKEN}" or not self.token_ok:
            return httpx.Response(403, json={"success": False,
                                             "errors": [{"code": 10000, "message": "Auth"}]})
        params = dict(request.url.params)
        body = json.loads(request.content) if request.content else {}
        if pfad == "/zones":
            treffer = [{"id": ZONE, "name": "example.de", "status": "active",
                        "account": {"id": KONTO}}] if params.get("name") == "example.de" else []
            return self._ok(treffer)
        if pfad == f"/accounts/{KONTO}/cfd_tunnel":
            if request.method == "GET":
                return self._ok([t for t in self.tunnels if t["name"] == params.get("name")])
            neu = {"id": TUNNEL, "name": body["name"]}
            self.tunnels.append(neu)
            return self._ok(neu)
        if pfad == f"/accounts/{KONTO}/cfd_tunnel/{TUNNEL}/token":
            # Echte Tunnel-Tokens sind Base64 -- mit "+", "/" und "=".
            return self._ok(TUNNEL_TOKEN)
        if pfad == f"/accounts/{KONTO}/cfd_tunnel/{TUNNEL}/configurations":
            self.ingress = body
            return self._ok({})
        if pfad == f"/zones/{ZONE}/dns_records":
            if request.method == "GET":
                return self._ok([r for r in self.records if r["name"] == params.get("name")])
            neu = {**body, "id": secrets.token_hex(16)}
            if neu["type"] == "TXT" and self.txt_override:
                neu["content"] = self.txt_override
            self.records.append(neu)
            return self._ok(neu)
        if pfad.startswith(f"/zones/{ZONE}/dns_records/"):
            kennung = pfad.rsplit("/", 1)[-1]
            if request.method == "DELETE":
                self.records = [r for r in self.records if r["id"] != kennung]
            else:
                for r in self.records:
                    if r["id"] == kennung:
                        r.update(body)
            return self._ok({"id": kennung})
        return httpx.Response(404, json={"success": False, "errors": [{"message": "nix"}]})

    @staticmethod
    def _ok(result: Any) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "errors": [], "result": result})


def _cf(fake: FakeCloudflare) -> Cloudflare:
    return Cloudflare(TOKEN, http=httpx.Client(transport=httpx.MockTransport(fake)))


def test_provisioning_creates_tunnel_route_and_domain(tmp_path: Path) -> None:
    fake = FakeCloudflare()
    config = SiteConfig(domain=DOMAIN, token=TOKEN)
    schritte: list[str] = []
    zustand = website.provision(config, tmp_path, 8443, cloudflare=_cf(fake),
                                progress=schritte.append)
    assert zustand.tunnel_id == TUNNEL and zustand.zone_id == ZONE
    assert zustand.tunnel_token == TUNNEL_TOKEN
    assert zustand.complete()
    assert fake.tunnels[0]["name"] == "aquaticy-chat-example-de"
    regel = fake.ingress["config"]["ingress"][0]
    assert regel["hostname"] == DOMAIN
    assert regel["service"] == "https://localhost:8443"
    # Noch kein echtes Zertifikat: cloudflared vertraut genau dem selbst ausgestellten.
    assert regel["originRequest"]["originServerName"] == DOMAIN
    assert regel["originRequest"]["caPool"].endswith("selfsigned-cert.pem")
    assert "noTLSVerify" not in regel["originRequest"]
    assert fake.ingress["config"]["ingress"][-1] == {"service": "http_status:404"}
    eintrag = fake.records[0]
    assert (eintrag["type"], eintrag["content"], eintrag["proxied"]) == \
        ("CNAME", f"{TUNNEL}.cfargotunnel.com", True)
    assert schritte
    # Gemerkt -- nur fuer den eigenen Nutzer lesbar.
    datei = website.site_dir(tmp_path) / "site.json"
    assert datei.stat().st_mode & 0o077 == 0
    assert website.load_state(tmp_path, DOMAIN) == zustand


def test_provisioning_twice_reuses_tunnel_and_record(tmp_path: Path) -> None:
    fake = FakeCloudflare()
    config = SiteConfig(domain=DOMAIN, token=TOKEN)
    website.provision(config, tmp_path, 8443, cloudflare=_cf(fake))
    website.provision(config, tmp_path, 8443, cloudflare=_cf(fake))
    assert len(fake.tunnels) == 1
    assert len(fake.records) == 1


def test_an_existing_foreign_record_is_left_alone(tmp_path: Path) -> None:
    fake = FakeCloudflare()
    fake.records.append({"id": "c" * 32, "type": "A", "name": DOMAIN, "content": "203.0.113.7"})
    with pytest.raises(WebsiteError, match="schon einen Eintrag"):
        website.provision(SiteConfig(domain=DOMAIN, token=TOKEN), tmp_path, 8443,
                          cloudflare=_cf(fake))
    assert fake.records[0]["content"] == "203.0.113.7"


def test_an_old_tunnel_record_is_repointed(tmp_path: Path) -> None:
    fake = FakeCloudflare()
    fake.records.append({"id": "c" * 32, "type": "CNAME", "name": DOMAIN,
                         "content": "99999999-0000-0000-0000-000000000000.cfargotunnel.com",
                         "proxied": True})
    website.provision(SiteConfig(domain=DOMAIN, token=TOKEN), tmp_path, 8443,
                      cloudflare=_cf(fake))
    assert fake.records[0]["content"] == f"{TUNNEL}.cfargotunnel.com"


def test_a_domain_outside_cloudflare_is_explained(tmp_path: Path) -> None:
    with pytest.raises(WebsiteError, match="nicht bei Cloudflare"):
        website.provision(SiteConfig(domain="chat.anderswo.de", token=TOKEN), tmp_path, 8443,
                          cloudflare=_cf(FakeCloudflare()))


def test_a_rejected_token_names_the_rights(tmp_path: Path) -> None:
    fake = FakeCloudflare()
    fake.token_ok = False
    with pytest.raises(WebsiteError, match="Cloudflare Tunnel"):
        website.provision(SiteConfig(domain=DOMAIN, token=TOKEN), tmp_path, 8443,
                          cloudflare=_cf(fake))


# -- Let's Encrypt (nachgebaut) -------------------------------------------------------------
class FakeAcme:
    """Ein ACME-Server nach RFC 8555 -- so streng, wie es fuer den Test zaehlt."""

    BASE = "https://acme.test"

    def __init__(self, cloudflare: FakeCloudflare) -> None:
        self.cf = cloudflare
        self.nonces: set[str] = set()
        self.keys: dict[str, Any] = {}
        self.token = _b64(secrets.token_bytes(24))
        self.authz = "pending"
        self.order = "pending"
        self.cert_pem = b""
        self.bad_nonce_once = True
        self.txt_seen = ""
        self.ca_key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
        jetzt = datetime.now(UTC)
        self.ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                   .public_key(self.ca_key.public_key()).serial_number(1)
                   .not_valid_before(jetzt - timedelta(days=1))
                   .not_valid_after(jetzt + timedelta(days=3650))
                   .sign(self.ca_key, hashes.SHA256()))

    def _nonce(self) -> str:
        nonce = _b64(secrets.token_bytes(16))
        self.nonces.add(nonce)
        return nonce

    def _antwort(self, status: int, body: Any = None, **kopf: str) -> httpx.Response:
        kopf["Replay-Nonce"] = self._nonce()
        if isinstance(body, bytes):
            return httpx.Response(status, content=body, headers=kopf)
        return httpx.Response(status, json=body if body is not None else {}, headers=kopf)

    def _pruefen(self, request: httpx.Request) -> tuple[dict[str, Any], Any, Any]:
        jws = json.loads(request.content)
        kopf = json.loads(_unb64(jws["protected"]))
        assert kopf["alg"] == "ES256"
        assert kopf["url"] == str(request.url)
        assert request.headers["Content-Type"] == "application/jose+json"
        if kopf["nonce"] not in self.nonces:
            raise AssertionError("unbekannte Nonce")
        self.nonces.discard(kopf["nonce"])
        if "jwk" in kopf:
            jwk = kopf["jwk"]
            schluessel = ec.EllipticCurvePublicNumbers(
                int.from_bytes(_unb64(jwk["x"]), "big"), int.from_bytes(_unb64(jwk["y"]), "big"),
                ec.SECP256R1()).public_key()
        else:
            schluessel, jwk = self.keys[kopf["kid"]]
        roh = _unb64(jws["signature"])
        der = encode_dss_signature(int.from_bytes(roh[:32], "big"), int.from_bytes(roh[32:], "big"))
        schluessel.verify(der, f"{jws['protected']}.{jws['payload']}".encode(),
                          ec.ECDSA(hashes.SHA256()))
        payload = json.loads(_unb64(jws["payload"])) if jws["payload"] else None
        return kopf, payload, (schluessel, jwk)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.cloudflare.com":
            return self.cf(request)
        pfad = request.url.path
        if pfad == "/directory":
            return httpx.Response(200, json={k: f"{self.BASE}/{v}" for k, v in (
                ("newNonce", "nonce"), ("newAccount", "acct"), ("newOrder", "order"))})
        if pfad == "/nonce":
            return self._antwort(200)
        if self.bad_nonce_once and pfad == "/order":
            self.bad_nonce_once = False
            return self._antwort(400, {"type": "urn:ietf:params:acme:error:badNonce"})
        kopf, payload, (schluessel, jwk) = self._pruefen(request)
        if pfad == "/acct":
            assert payload["termsOfServiceAgreed"] is True
            kid = f"{self.BASE}/acct/1"
            self.keys[kid] = (schluessel, jwk)
            return self._antwort(201, {"status": "valid"}, Location=kid)
        assert "kid" in kopf, "nach dem Konto nur noch mit kid"
        if pfad == "/order":
            assert payload == {"identifiers": [{"type": "dns", "value": DOMAIN}]}
            return self._antwort(201, self._auftrag(), Location=f"{self.BASE}/order/1")
        if pfad == "/order/1":
            assert payload is None
            return self._antwort(200, self._auftrag())
        if pfad == "/authz/1":
            return self._antwort(200, {"status": self.authz,
                                       "identifier": {"type": "dns", "value": DOMAIN},
                                       "challenges": [
                                           {"type": "http-01", "url": f"{self.BASE}/x",
                                            "token": self.token},
                                           {"type": "dns-01", "url": f"{self.BASE}/chall/1",
                                            "token": self.token}]})
        if pfad == "/chall/1":
            assert payload == {}
            fingerabdruck = _b64(hashlib.sha256(json.dumps(
                jwk, sort_keys=True, separators=(",", ":")).encode()).digest())
            soll = _b64(hashlib.sha256(f"{self.token}.{fingerabdruck}".encode()).digest())
            txt = [r for r in self.cf.records
                   if r["type"] == "TXT" and r["name"] == f"_acme-challenge.{DOMAIN}"]
            self.txt_seen = txt[0]["content"] if txt else ""
            ok = self.txt_seen == soll
            self.authz = "valid" if ok else "invalid"
            self.order = "ready" if ok else "invalid"
            return self._antwort(200, {"status": "processing"})
        if pfad == "/finalize/1":
            assert self.order == "ready"
            csr = x509.load_der_x509_csr(_unb64(payload["csr"]))
            assert csr.is_signature_valid
            san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            assert san.value.get_values_for_type(x509.DNSName) == [DOMAIN]
            jetzt = datetime.now(UTC)
            zert = (x509.CertificateBuilder().subject_name(csr.subject)
                    .issuer_name(self.ca.subject).public_key(csr.public_key())
                    .serial_number(x509.random_serial_number())
                    .not_valid_before(jetzt - timedelta(minutes=1))
                    .not_valid_after(jetzt + timedelta(days=90))
                    .add_extension(san.value, critical=False)
                    .sign(self.ca_key, hashes.SHA256()))
            self.cert_pem = (zert.public_bytes(serialization.Encoding.PEM)
                             + self.ca.public_bytes(serialization.Encoding.PEM))
            self.order = "valid"
            return self._antwort(200, self._auftrag())
        if pfad == "/cert/1":
            assert request.headers["Accept"] == "application/pem-certificate-chain"
            return self._antwort(200, self.cert_pem)
        raise AssertionError(f"unerwartet: {pfad}")

    def _auftrag(self) -> dict[str, Any]:
        auftrag: dict[str, Any] = {"status": self.order,
                                   "authorizations": [f"{self.BASE}/authz/1"],
                                   "finalize": f"{self.BASE}/finalize/1"}
        if self.order == "valid":
            auftrag["certificate"] = f"{self.BASE}/cert/1"
        return auftrag


def _acme_client(fake: FakeAcme) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(fake))


def test_a_certificate_is_obtained_via_dns(monkeypatch: pytest.MonkeyPatch,
                                            tmp_path: Path) -> None:
    cf = FakeCloudflare()
    acme = FakeAcme(cf)
    monkeypatch.setattr(website, "ACME_DIRECTORY", f"{FakeAcme.BASE}/directory")
    gewartet: list[str] = []
    ablauf = website.obtain_certificate(
        SiteConfig(domain=DOMAIN, token=TOKEN, email="jonas@example.de"), tmp_path, ZONE,
        cloudflare=_cf(cf), http=_acme_client(acme),
        wait=lambda name, wert: gewartet.append(name), sleep=lambda s: None)
    assert ablauf > datetime.now(UTC) + timedelta(days=80)
    assert gewartet == [f"_acme-challenge.{DOMAIN}"]
    assert acme.txt_seen  # Let's Encrypt hat den Eintrag gesehen ...
    assert not [r for r in cf.records if r["type"] == "TXT"]  # ... und er ist wieder weg
    zert, key = website.cert_paths(tmp_path)
    assert zert.read_bytes().startswith(b"-----BEGIN CERTIFICATE-----")
    assert key.stat().st_mode & 0o077 == 0
    assert website.certificate_valid(tmp_path, DOMAIN)
    assert not website.needs_certificate(tmp_path, DOMAIN)
    assert website.needs_certificate(tmp_path, DOMAIN,
                                     now=datetime.now(UTC) + timedelta(days=70))
    # Der Kontoschluessel bleibt fuer die Erneuerung.
    assert (website.site_dir(tmp_path) / "acme-account.key").stat().st_mode & 0o077 == 0


def test_a_failed_dns_check_saves_nothing(monkeypatch: pytest.MonkeyPatch,
                                          tmp_path: Path) -> None:
    cf = FakeCloudflare()
    cf.txt_override = "falsch"
    acme = FakeAcme(cf)
    monkeypatch.setattr(website, "ACME_DIRECTORY", f"{FakeAcme.BASE}/directory")
    with pytest.raises(WebsiteError, match="abgelehnt"):
        website.obtain_certificate(
            SiteConfig(domain=DOMAIN, token=TOKEN), tmp_path, ZONE, cloudflare=_cf(cf),
            http=_acme_client(acme), wait=lambda n, w: None, sleep=lambda s: None)
    assert not website.cert_paths(tmp_path)[0].exists()
    assert not [r for r in cf.records if r["type"] == "TXT"]


def test_a_chain_for_another_domain_is_refused() -> None:
    schluessel = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "andere.example.de")])
    jetzt = datetime.now(UTC)
    zert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(schluessel.public_key()).serial_number(2)
            .not_valid_before(jetzt).not_valid_after(jetzt + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("andere.example.de")]),
                           critical=False)
            .sign(schluessel, hashes.SHA256()))
    pem = schluessel.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                   serialization.NoEncryption())
    with pytest.raises(WebsiteError, match="nicht für diese Domain"):
        website._check_chain(zert.public_bytes(serialization.Encoding.PEM), pem, DOMAIN)


def test_the_jws_thumbprint_follows_rfc_7638() -> None:
    fake = FakeAcme(FakeCloudflare())
    client = Acme(f"{FakeAcme.BASE}/directory", ec.generate_private_key(ec.SECP256R1()),
                  http=_acme_client(fake))
    jwk = client.jwk()
    assert list(jwk) == ["crv", "kty", "x", "y"]
    assert len(_unb64(jwk["x"])) == 32
    erwartet = _b64(hashlib.sha256(
        f'{{"crv":"P-256","kty":"EC","x":"{jwk["x"]}","y":"{jwk["y"]}"}}'.encode()).digest())
    assert client.thumbprint() == erwartet


def test_the_website_sets_itself_up_and_switches_to_strict_checking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cf = FakeCloudflare()
    acme = FakeAcme(cf)
    monkeypatch.setattr(website, "ACME_DIRECTORY", f"{FakeAcme.BASE}/directory")
    monkeypatch.setattr(website, "_guarded", lambda *a, **k: _acme_client(acme))
    monkeypatch.setattr(website, "wait_for_txt", lambda *a, **k: True)
    seite = website.Website(config=SiteConfig(domain=DOMAIN, token=TOKEN), data_dir=tmp_path,
                            pause=lambda s: None)
    seite.port = 8450
    assert seite.tls() is not None and seite.strict is False
    seite._step()
    assert seite.state is not None and seite.state.tunnel_id == TUNNEL
    assert website.certificate_valid(tmp_path, DOMAIN)
    regel = cf.ingress["config"]["ingress"][0]
    assert regel["service"] == "https://localhost:8450"
    assert regel["originRequest"] == {"originServerName": DOMAIN}
    assert seite.strict is True
    assert seite.view()["url"] == f"https://{DOMAIN}/"
    # Ein zweiter Durchgang aendert nichts mehr bei Cloudflare.
    vorher = len(cf.calls)
    seite._step()
    assert len(cf.calls) == vorher


# -- TLS fuer den Eingang ------------------------------------------------------------------
def test_without_a_real_certificate_a_self_signed_one_is_used(tmp_path: Path) -> None:
    kontext, echt = website.tls_context(tmp_path, DOMAIN)
    assert isinstance(kontext, ssl.SSLContext)
    assert echt is False
    assert (website.site_dir(tmp_path) / "selfsigned-key.pem").stat().st_mode & 0o077 == 0


# -- cloudflared ---------------------------------------------------------------------------
class FakeProzess:
    def __init__(self, aufrufe: list[Any], args: list[str], **kwargs: Any) -> None:
        aufrufe.append((args, kwargs))
        self.code = 1

    def wait(self, timeout: float | None = None) -> int:
        return self.code

    def poll(self) -> int:
        return self.code

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass


def test_the_tunnel_token_never_appears_on_the_command_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AQUATICY_CLOUDFLARE_TOKEN", TOKEN)
    monkeypatch.setenv("MISTRAL_API_KEY", "geheim-mistral")
    aufrufe: list[Any] = []
    pausen: list[float] = []

    def schlafen(sekunden: float) -> bool:
        pausen.append(sekunden)
        return len(pausen) >= 3

    tunnel = Tunnel(tmp_path, lambda: "eyJ" + "t" * 60, locate=lambda: Path("/bin/true"),
                    popen=lambda args, **kw: FakeProzess(aufrufe, args, **kw), sleep=schlafen)
    tunnel._run()
    args, kwargs = aufrufe[0]
    assert args[1:] == ["tunnel", "--no-autoupdate", "run"]
    assert not any("eyJ" in teil for teil in args)
    assert kwargs["env"]["TUNNEL_TOKEN"] == "eyJ" + "t" * 60
    assert "AQUATICY_CLOUDFLARE_TOKEN" not in kwargs["env"]
    assert "MISTRAL_API_KEY" not in kwargs["env"]
    # Endet cloudflared, startet es neu -- mit wachsender Pause.
    assert len(aufrufe) == 3
    assert pausen == list(website.TUNNEL_BACKOFF[:3])
    assert tunnel.phase == "fehler"
    log = website.site_dir(tmp_path) / "cloudflared.log"
    assert log.stat().st_mode & 0o077 == 0


def test_without_a_token_the_tunnel_waits(tmp_path: Path) -> None:
    gestartet: list[Any] = []
    tunnel = Tunnel(tmp_path, lambda: "", locate=lambda: Path("/bin/true"),
                    popen=lambda *a, **k: gestartet.append(a), sleep=lambda s: True)
    tunnel._run()
    assert gestartet == []
    assert "nicht eingerichtet" in tunnel.message


def test_cloudflared_is_installed_only_with_a_checksum(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(website, "cloudflared_asset", lambda: "cloudflared-linux-amd64")
    inhalt = b"#!/bin/sh\necho cloudflared version 2026.9.0\n"
    pruefsumme = hashlib.sha256(inhalt).hexdigest()

    def github(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(200, json={"tag_name": "2026.9.0", "assets": [{
                "name": "cloudflared-linux-amd64", "size": len(inhalt),
                "digest": f"sha256:{pruefsumme}",
                "browser_download_url": "https://github.com/cloudflare/cloudflared/releases/"
                                        "download/2026.9.0/cloudflared-linux-amd64"}]})
        return httpx.Response(200, content=inhalt)

    pfad = website.install_cloudflared(
        tmp_path, http=httpx.Client(transport=httpx.MockTransport(github)), check=lambda p: True)
    assert pfad == website.managed_cloudflared(tmp_path)
    assert pfad.read_bytes() == inhalt
    assert pfad.stat().st_mode & 0o111


def test_a_wrong_checksum_installs_nothing(monkeypatch: pytest.MonkeyPatch,
                                           tmp_path: Path) -> None:
    monkeypatch.setattr(website, "cloudflared_asset", lambda: "cloudflared-linux-amd64")

    def github(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(200, json={"tag_name": "2026.9.0", "assets": [{
                "name": "cloudflared-linux-amd64", "size": 5, "digest": "sha256:" + "0" * 64,
                "browser_download_url": "https://github.com/x/cloudflared-linux-amd64"}]})
        return httpx.Response(200, content=b"boese")

    with pytest.raises(WebsiteError, match="Prüfsumme"):
        website.install_cloudflared(
            tmp_path, http=httpx.Client(transport=httpx.MockTransport(github)),
            check=lambda p: True)
    assert not website.managed_cloudflared(tmp_path).exists()


# -- Der oeffentliche Eingang --------------------------------------------------------------
def test_the_public_entry_takes_the_visitor_address_from_cloudflare() -> None:
    from aquaticy.web import Handler, PublicHandler

    eingang = PublicHandler.__new__(PublicHandler)
    eingang.client_address = ("127.0.0.1", 50000)
    eingang.headers = {"CF-Connecting-IP": "203.0.113.9"}  # type: ignore[assignment]
    assert eingang._client_ip() == "203.0.113.9"
    assert eingang._https() is True
    eingang.headers = {"CF-Connecting-IP": "kein; ip"}  # type: ignore[assignment]
    assert eingang._client_ip() == "127.0.0.1"
    # Am normalen Eingang zaehlt die Kopfzeile nicht -- jeder koennte sie setzen.
    normal = Handler.__new__(Handler)
    normal.client_address = ("192.168.1.20", 50000)
    normal.headers = {"CF-Connecting-IP": "203.0.113.9"}  # type: ignore[assignment]
    assert normal._client_ip() == "192.168.1.20"


def test_the_public_entry_speaks_tls_on_loopback_and_hides_the_cluster(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from aquaticy import web

    class Verbund:
        enabled = True

        def beacon(self) -> dict[str, str]:
            return {"node": "geheim"}

    monkeypatch.setattr(web, "CLUSTER", Verbund())
    kontext, _ = website.tls_context(tmp_path, DOMAIN)
    server = web.bind_public(kontext, 0)
    assert server.server_address[0] == "127.0.0.1"
    faden = threading.Thread(target=server.serve_forever, daemon=True)
    faden.start()
    try:
        port = server.server_address[1]
        # Geprueft gegen das selbst ausgestellte Zertifikat -- es nennt auch "localhost".
        vertrauen = ssl.create_default_context(
            cafile=str(website.site_dir(tmp_path) / "selfsigned-cert.pem"))
        with httpx.Client(verify=vertrauen, timeout=10) as client:
            antwort = client.get(f"https://localhost:{port}/cluster/info")
        assert antwort.status_code == 404
        assert "geheim" not in antwort.text
        assert "max-age" in antwort.headers.get("Strict-Transport-Security", "")
        with pytest.raises(httpx.HTTPError):
            httpx.get(f"http://127.0.0.1:{port}/cluster/info", timeout=5)
    finally:
        server.shutdown()
        server.server_close()


# -- Kommandozeile -------------------------------------------------------------------------
runner = CliRunner()


def test_with_a_domain_web_listens_everywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy import cli

    gesehen: dict[str, Any] = {}
    monkeypatch.setenv("AQUATICY_DOMAIN", DOMAIN)
    monkeypatch.setenv("AQUATICY_CLOUDFLARE_TOKEN", TOKEN)
    monkeypatch.setattr("aquaticy.web.serve", lambda **kwargs: gesehen.update(kwargs))
    monkeypatch.setattr("aquaticy.web.lan_address", lambda: "192.168.1.44")
    monkeypatch.setattr("aquaticy.web.tailscale_address", lambda: "100.81.120.100")
    ergebnis = runner.invoke(cli.app, ["web", "--no-open"])
    assert ergebnis.exit_code == 0, ergebnis.output
    assert gesehen["host"] == "0.0.0.0"
    assert f"https://{DOMAIN}/" in ergebnis.output
    assert "http://192.168.1.44:8765/" in ergebnis.output
    assert "http://100.81.120.100:8765/" in ergebnis.output


def test_without_a_domain_web_stays_local(monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy import cli

    gesehen: dict[str, Any] = {}
    monkeypatch.delenv("AQUATICY_DOMAIN", raising=False)
    monkeypatch.setattr("aquaticy.web.serve", lambda **kwargs: gesehen.update(kwargs))
    assert runner.invoke(cli.app, ["web", "--no-open"]).exit_code == 0
    assert gesehen["host"] == "127.0.0.1"


def test_website_is_a_known_command() -> None:
    from aquaticy import cli

    assert "website" in cli.COMMANDS


def test_website_status_without_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy import cli

    monkeypatch.delenv("AQUATICY_DOMAIN", raising=False)
    monkeypatch.setattr(cli, "load_env", lambda: None)
    ergebnis = runner.invoke(cli.app, ["website"])
    assert ergebnis.exit_code == 0
    assert "aquaticy website setup" in ergebnis.output


def test_website_setup_asks_and_writes_the_env(monkeypatch: pytest.MonkeyPatch,
                                               tmp_path: Path) -> None:
    from aquaticy import cli

    ziel = tmp_path / ".env"
    eingerichtet: list[Any] = []
    monkeypatch.delenv("AQUATICY_DOMAIN", raising=False)
    monkeypatch.delenv("AQUATICY_CLOUDFLARE_TOKEN", raising=False)
    monkeypatch.setattr(cli, "load_env", lambda: None)
    monkeypatch.setattr(cli, "_set_up_website", lambda config: eingerichtet.append(config))
    ergebnis = runner.invoke(cli.app, ["website", "setup", "--env-file", str(ziel)],
                             input=f"kaputt\nhttps://{DOMAIN}/\n{TOKEN}\n")
    assert ergebnis.exit_code == 0, ergebnis.output
    assert "keine Domain" in ergebnis.output  # "kaputt" wurde abgelehnt
    text = ziel.read_text(encoding="utf-8")
    assert f"AQUATICY_DOMAIN={DOMAIN}" in text
    assert TOKEN in text
    assert TOKEN not in ergebnis.output  # verdeckt eingegeben
    assert eingerichtet[0].domain == DOMAIN
    assert ziel.stat().st_mode & 0o077 == 0


def test_empty_domain_skips_the_website(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aquaticy import cli

    monkeypatch.delenv("AQUATICY_DOMAIN", raising=False)
    monkeypatch.setattr(cli, "load_env", lambda: None)
    ergebnis = runner.invoke(cli.app, ["website", "setup", "--env-file",
                                       str(tmp_path / ".env")], input="\n")
    assert ergebnis.exit_code == 0
    assert not (tmp_path / ".env").exists()


def test_the_public_entry_accepts_its_own_domain_as_origin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from aquaticy import web
    from aquaticy.web import PublicHandler

    monkeypatch.setattr(web, "WEBSITE", website.Website(
        config=SiteConfig(domain=DOMAIN, token=TOKEN), data_dir=tmp_path))
    eingang = PublicHandler.__new__(PublicHandler)
    eingang.headers = {"Origin": f"https://{DOMAIN}", "Host": "localhost:8443"}  # type: ignore
    assert eingang._origin_ok()
    eingang.headers = {"Origin": "https://boese.example", "Host": "localhost:8443"}  # type: ignore
    assert not eingang._origin_ok()
    eingang.headers = {"Origin": f"https://{DOMAIN}", "Host": "localhost:8443",  # type: ignore
                       "Sec-Fetch-Site": "cross-site"}
    assert not eingang._origin_ok()


def _handler_von(adresse: str, klasse: Any = None) -> Any:
    import io

    from aquaticy.web import Handler

    h = (klasse or Handler).__new__(klasse or Handler)
    h.client_address = (adresse, 50000)
    h.command, h.path, h.request_version = "GET", "/", "HTTP/1.1"
    h.requestline = "GET / HTTP/1.1"
    h.headers = {}  # type: ignore[assignment]
    h.wfile = io.BytesIO()
    h.connection = None
    h.log_message = lambda *a: None  # type: ignore[method-assign]
    return h


def test_with_a_domain_the_plain_entry_only_serves_the_home_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Auf einem Server mit oeffentlicher Adresse waere Port 8765 sonst
    unverschluesselt aus dem Internet erreichbar."""
    from aquaticy import web

    monkeypatch.setattr(web, "WEBSITE", website.Website(
        config=SiteConfig(domain=DOMAIN, token=TOKEN), data_dir=tmp_path))
    monkeypatch.setattr(web, "LAN_ONLY", True)
    fremd = _handler_von("93.184.215.14")
    assert fremd._nur_heimnetz() is True
    assert _handler_von("2a00:1450:4001::1")._nur_heimnetz() is True
    antwort = fremd.wfile.getvalue().decode()
    assert " 403 " in antwort.splitlines()[0]
    assert f"https://{DOMAIN}/" in antwort
    for adresse in ("192.168.1.20", "10.0.0.7", "100.81.120.100", "127.0.0.1", "::1",
                    "fd12::5"):
        assert _handler_von(adresse)._nur_heimnetz() is False, adresse
    # Der Tunnel-Eingang ist davon nicht betroffen.
    assert _handler_von("93.184.215.14", web.PublicHandler)._nur_heimnetz() is False


def test_without_a_domain_nothing_is_restricted(monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy import web

    monkeypatch.setattr(web, "LAN_ONLY", False)
    assert _handler_von("93.184.215.14")._nur_heimnetz() is False
