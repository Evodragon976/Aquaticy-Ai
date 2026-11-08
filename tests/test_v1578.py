"""15.7.8: Modell fuer die Agenten waehlen, Cloud wie bisher; README aufgeraeumt."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aquaticy.config import Settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(("haupt", "agent", "erwartet"), [
    ("ollama_chat/qwen3:14b", "ollama_chat/qwen3:4b", "ollama_chat/qwen3:4b"),
    ("ollama_chat/qwen3:14b", "", None),
    ("mistral/mistral-large-latest", "mistral/mistral-small-latest",
     "mistral/mistral-small-latest"),
])
def test_the_chosen_agent_model_is_used(haupt: str, agent: str, erwartet: str | None) -> None:
    s = Settings(model=haupt, subagent_model=agent)
    if erwartet is not None:
        assert s.effective_subagent_model == erwartet
    else:
        assert s.effective_subagent_model  # automatisch, wie bisher


def test_cloud_models_work_as_before() -> None:
    """Ohne Auswahl ("Automatisch") nimmt ein Cloud-Chat wie bisher das schnelle Modell."""
    assert Settings(model="mistral/mistral-large-latest").effective_subagent_model == (
        "mistral/mistral-small-latest")


def test_the_settings_offer_a_selection_with_english_texts() -> None:
    html = (ROOT / "aquaticy" / "webui.html").read_text(encoding="utf-8")
    assert '<select name="AQUATICY_SUBAGENT_MODEL" id="agent-model">' in html
    assert "agentenModelleLaden" in html
    assert '"Modell für die Agenten": "Model for the agents"' in html
    assert '"Automatisch (wie bisher)": "Automatic (as before)"' in html


def test_the_readme_is_short_and_links_the_changelog() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## Inhalt" in readme and "[CHANGELOG.md](CHANGELOG.md)" in readme
    assert readme.count("**Neu in ") == 0 and "**Neu in 15.5.6:**" in changelog
    assert len(readme.splitlines()) < 1600
    for anker in ("#speicher", "#modelle-und-anbieter", "#konfiguration"):
        assert f"]({anker})" in readme


# -- Fremdbericht: geprueft und behoben -----------------------------------------------------------
def test_the_tunnel_log_is_trimmed_with_headroom() -> None:
    from aquaticy import website

    assert website.log_keep_bytes() <= website.MAX_LOG_BYTES - 1024 * 1024


def test_relative_and_absolute_paths_share_one_lock(tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy import keyvault

    monkeypatch.chdir(tmp_path)
    assert keyvault._lock_for(Path("konten.sqlite3")) is keyvault._lock_for(
        tmp_path / "konten.sqlite3")


def test_tailscale_addresses_with_a_scope_are_recognised() -> None:
    from aquaticy.cluster import tailscale_ip_ok

    assert tailscale_ip_ok("100.101.102.103") and tailscale_ip_ok("fd7a:115c:a1e0::1%tailscale0")
    assert not tailscale_ip_ok("192.168.1.2%eth0")


def test_dns_never_raises_an_index_error() -> None:
    from aquaticy import dns_lookup

    assert dns_lookup.call(lambda: 42) == 42
    with pytest.raises(OSError):
        dns_lookup.call(lambda: (_ for _ in ()).throw(OSError("kaputt")))


# -- Google: Reihenfolge der Anmeldungen ----------------------------------------------------------
class _Konto:
    def __init__(self) -> None:
        self.gespeichert: list[str] = []

    def remember(self, tokens: str) -> None:
        self.gespeichert.append(tokens)


def test_a_late_google_login_cannot_undo_disconnecting() -> None:
    from aquaticy import web

    state = web.google_state_new("konto-g")
    assert web.google_state_take(state, "konto-g")
    web.google_cut("konto-g")                       # Trennen, waehrend Google noch antwortet
    konto = _Konto()
    assert not web.google_commit("konto-g", "alt", konto) and konto.gespeichert == []


def test_disconnecting_voids_open_logins() -> None:
    from aquaticy import web

    state = web.google_state_new("konto-h")
    web.google_cut("konto-h")
    assert not web.google_state_take(state, "konto-h")


def test_an_older_login_cannot_overwrite_a_newer_one(monkeypatch: pytest.MonkeyPatch) -> None:
    import time as zeit

    from aquaticy import web

    jetzt = [zeit.time()]
    monkeypatch.setattr(web.time, "time", lambda: jetzt[0])
    alt = web.google_state_new("konto-i")
    jetzt[0] += 5
    neu = web.google_state_new("konto-i")
    konto = _Konto()
    assert web.google_state_take(neu, "konto-i")
    assert web.google_commit("konto-i", "neu", konto)
    assert web.google_state_take(alt, "konto-i")
    assert not web.google_commit("konto-i", "alt", konto)
    assert konto.gespeichert == ["neu"]


def test_a_commit_needs_a_login_from_this_request() -> None:
    from aquaticy import web

    web._GOOGLE_FLOW.start = None
    assert not web.google_commit("konto-j", "x", _Konto())


# -- Feeds ----------------------------------------------------------------------------------------
@pytest.mark.parametrize(("adresse", "ok"), [
    ("https://example.org/feed.xml", True), ("https://xn--mnchen-3ya.de/rss", True),
    ("https://@example.org/feed", False), ("https://exa mple.org/feed", False),
    ("https://example.org/fe ed", False), ("https://example.org/\x01", False),
    ("https://user:pw@example.org/x", False), ("ftp://example.org/x", False),
    ("https://ex_ample.org/x", False),
])
def test_only_loadable_feed_addresses_are_kept(adresse: str, ok: bool) -> None:
    from aquaticy.addons import feed_address_ok

    assert feed_address_ok(adresse) is ok


# -- Zertifikatsketten ----------------------------------------------------------------------------
def _kette(*, path_length: int | None = None, signieren: bool = True,
           erlaubt: list[str] | None = None, zwischen: int = 1,
           domain: str = "aquaticy.example") -> tuple[bytes, bytes]:
    from datetime import UTC, datetime, timedelta

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    jetzt = datetime.now(UTC)

    def zert(name: str, key: Any, issuer_name: str, issuer_key: Any, ca: bool,
             pfad: int | None = None, sign: bool = True,
             constraints: list[str] | None = None, san: str = "") -> Any:
        bau = (x509.CertificateBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
               .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_name)]))
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(jetzt - timedelta(days=1))
               .not_valid_after(jetzt + timedelta(days=30))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=pfad if ca else None),
                              critical=True))
        if ca:
            bau = bau.add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=sign,
                crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
        if constraints is not None:
            bau = bau.add_extension(x509.NameConstraints(
                [x509.DNSName(c) for c in constraints], None), critical=True)
        if san:
            bau = bau.add_extension(x509.SubjectAlternativeName([x509.DNSName(san)]),
                                    critical=False)
        return bau.sign(issuer_key, hashes.SHA256())

    root_key = ec.generate_private_key(ec.SECP256R1())
    oben, oben_key = "Root", root_key
    kette = []
    for i in range(zwischen):
        key = ec.generate_private_key(ec.SECP256R1())
        name = f"Zwischen {i}"
        kette.insert(0, zert(name, key, oben, oben_key, True,
                             path_length if i == 0 else None,  # oberste Zwischenstelle
                             signieren if i == zwischen - 1 else True,
                             erlaubt if i == zwischen - 1 else None))
        oben, oben_key = name, key
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf = zert(domain, leaf_key, oben, oben_key, False, san=domain)
    pem = b"".join(c.public_bytes(serialization.Encoding.PEM) for c in [leaf, *kette])
    return pem, leaf_key.private_bytes(serialization.Encoding.PEM,
                                       serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption())


def test_a_correct_chain_is_accepted() -> None:
    from aquaticy import website

    website._check_chain(*_kette(), "aquaticy.example")


@pytest.mark.parametrize("kaputt", [
    {"signieren": False},                                  # darf nicht signieren
    {"path_length": 0, "zwischen": 2},                     # Pfadlaenge ueberschritten
    {"erlaubt": ["andere.example"]},                       # Name ausserhalb der Beschraenkung
])
def test_invalid_chains_are_rejected(kaputt: dict[str, Any]) -> None:
    from aquaticy import website

    with pytest.raises(website.WebsiteError):
        website._check_chain(*_kette(**kaputt), "aquaticy.example")
