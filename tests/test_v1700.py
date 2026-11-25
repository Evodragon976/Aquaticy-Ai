"""17.0.0: Gastzugang ("Ohne Anmeldung fortfahren") und ReDoS in Aquaticy Standard.

Ohne Netz und ohne Modell: ein echter Server im selben Prozess, Konten in ``tmp_path``.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from aquaticy import auth as auth_mod
from aquaticy import standard, web
from aquaticy.auth import GAST_DOMAIN, AuthStore
from aquaticy.devices import clean_device, new_device_token
from aquaticy.legal import legal_page
from tests.anmeldung import AGENT, FETCH, SPRACHE, wie_die_app

ROOT = Path(__file__).resolve().parents[1]
PASSWORT = "ein-langes-Passwort-42"
JETZT = datetime(2026, 11, 24, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
ADRESSE = "203.0.113.9"


# -- ReDoS (Punkt 7 der Angriffsliste) --------------------------------------------------------

@pytest.mark.parametrize("text", ["0" * 2000, "1" * 2000, "wie viele km sind " + "0" * 2000,
                                  "1." * 1000, "rechne " + "00" * 1000])
def test_long_digit_runs_no_longer_take_seconds(text: str) -> None:
    # Vorher rund 40 Sekunden: Zahl und Einheit durften sich Ziffern teilen (n hoch 3).
    start = time.perf_counter()
    standard._antwort(text, [], holen=lambda url: None, jetzt=JETZT)
    assert time.perf_counter() - start < 8


@pytest.mark.parametrize("frage, antwort", [
    ("5 km in meilen", "5 km sind **3,1069 Meilen**."),
    ("1.000 m in km", "1.000 m sind **1 km**."),
    ("2 stunden 30 minuten in minuten", "2 Std. 30 Min. sind **150 Minuten**."),
    ("1,5 h in min", "1,5 h sind **90 min**."),
    ("3 fuß 6 zoll in cm", "42 Zoll sind **106,68 cm**."),
    ("wie viele meter sind 3 km", "3 km sind **3.000 Meter**."),
    ("5 km sind wie viele meilen?", "5 km sind **3,1069 Meilen**."),
])
def test_units_still_work_after_the_fix(frage: str, antwort: str) -> None:
    # Dieselben Antworten wie vor 17.0.0: Der Treffer ganz links bleibt derselbe.
    assert standard._antwort(frage, [], holen=lambda url: None, jetzt=JETZT) == antwort


# -- Gaeste im Kontenspeicher -------------------------------------------------------------------

def _geraet() -> Any:
    return clean_device({}, user_agent=AGENT, accept_language=SPRACHE, cookie=new_device_token())


def test_a_guest_has_no_mail_no_password_and_a_reserved_name(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "konten", "PRO234567")
    gast = store.create_guest(ip=ADRESSE, terms_version="t")
    assert gast.guest and gast.plan == "normal" and gast.plan_label == "Gast"
    assert gast.email.endswith("@" + GAST_DOMAIN) and gast.username.startswith("Gast-")
    assert store.authenticate(gast.email, "irgendein-Passwort-123") is None
    assert store.login(gast.username, "irgendein-Passwort-123") is None
    with pytest.raises(ValueError, match="reserviert"):
        store.register("ana@example.org", PASSWORT, "normal", username="Gast-ABC123",
                       terms_accepted=True, terms_version="t")
    with pytest.raises(ValueError, match=r"Zustimmung|Stimm"):
        store.create_guest(ip=ADRESSE, terms_version="")


def test_a_new_guest_does_not_start_with_a_fresh_quota(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "konten", "PRO234567")
    eins = store.create_guest(ip=ADRESSE, terms_version="t")
    store.quota(eins).record(5000)
    store.remove_account(eins)
    zwei = store.create_guest(ip=ADRESSE, terms_version="t")
    assert store.quota(zwei).status()["_used"]["week"] >= 5000
    fremd = store.create_guest(ip="198.51.100.20", terms_version="t")
    assert store.quota(fremd).status()["_used"]["week"] == 0
    # IPv6: dasselbe /64-Netz ist derselbe Anschluss.
    a = store.create_guest(ip="2001:db8:1:2::1", terms_version="t")
    b = store.create_guest(ip="2001:db8:1:2::ffff", terms_version="t")
    assert a.guest_key == b.guest_key and a.guest_key != fremd.guest_key


def test_at_most_three_guests_per_address(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "konten", "PRO234567")
    for _ in range(3):
        store.create_guest(ip=ADRESSE, terms_version="t")
    with pytest.raises(ValueError, match="genug Gäste"):
        store.create_guest(ip=ADRESSE, terms_version="t")


def test_a_leftover_guest_does_not_block_the_real_registration(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "konten", "PRO234567")
    geraet = _geraet()
    store.create_guest(ip=ADRESSE, device=geraet, terms_version="t")
    store.register("ana@example.org", PASSWORT, "normal", username="Ana", terms_accepted=True,
                   terms_version="t", ip=ADRESSE, device=geraet)
    # Die Pruefung gegen mehrere Konten pro Geraet laeuft weiter.
    with pytest.raises(ValueError, match="schon ein Konto"):
        store.register("bo@example.org", PASSWORT, "normal", username="Bo", terms_accepted=True,
                       terms_version="t", ip=ADRESSE, device=geraet)


def test_the_single_owner_is_never_a_guest(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "konten", "PRO234567")
    store.create_guest(ip=ADRESSE, terms_version="t")
    store.register("ana@example.org", PASSWORT, "normal", username="Ana", terms_accepted=True,
                   terms_version="t")
    eins = store.owner()
    assert eins is not None and eins.username == "Ana"


def test_no_guests_with_a_single_account(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "konten", "PRO234567", single=True)
    with pytest.raises(ValueError, match="Einzelkonto"):
        store.create_guest(ip=ADRESSE, terms_version="t")


def test_old_guest_usage_is_forgotten_after_eight_days(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "konten", "PRO234567")
    gast = store.create_guest(ip=ADRESSE, terms_version="t")
    store.quota(gast).record(100)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE token_usage SET at = at - 9 * 86400")
    store.forget_old_guest_usage()
    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0] == 0


# -- Ueber den echten Server ----------------------------------------------------------------

@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(web, "AUTH", AuthStore(tmp_path / "accounts", "PRO234567"))
    monkeypatch.setattr(web, "SESSIONS", web.SessionRegistry())
    monkeypatch.setattr(web, "SESSION", web.SessionProxy())
    monkeypatch.setattr(web, "strong_models", lambda *args, **kwargs: [])
    monkeypatch.setattr(web, "AIGUARD", None)
    monkeypatch.setattr(web, "AUTH_LIMIT", web.RateLimiter(attempts=100, window_seconds=60))
    monkeypatch.setattr(web, "GAST_LIMIT", web.RateLimiter(attempts=100, window_seconds=60))
    monkeypatch.setattr(web, "_GAESTE_ZULETZT", [0.0])
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    faden = threading.Thread(target=httpd.serve_forever, daemon=True)
    faden.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


class Browser:
    def __init__(self, port: int) -> None:
        self.port = port
        self.kekse: dict[str, str] = {}
        self.roh: list[str] = []

    def __call__(self, methode: str, pfad: str, body: Any = None) -> tuple[int, dict[str, Any]]:
        conn = HTTPConnection("127.0.0.1", self.port, timeout=20)
        kopf = {"Content-Type": "application/json", "User-Agent": AGENT,
                "Accept-Language": SPRACHE, **FETCH}
        if self.kekse:
            kopf["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.kekse.items())
        conn.request(methode, pfad, body=None if body is None else json.dumps(body),
                     headers=kopf)
        antwort = conn.getresponse()
        roh = antwort.read()
        self.roh = []
        for name, wert in antwort.getheaders():
            if name.lower() == "set-cookie":
                self.roh.append(wert)
                schluessel, _, rest = wert.partition("=")
                if "Max-Age=0;" in wert:
                    self.kekse.pop(schluessel, None)
                else:
                    self.kekse[schluessel] = rest.split(";", 1)[0]
        conn.close()
        return antwort.status, (json.loads(roh) if roh else {})


def _gast(port: int) -> tuple[Browser, dict[str, Any]]:
    browser = Browser(port)
    browser("POST", "/api/consent", {"accepted": True})
    status, daten = browser("POST", "/api/auth/guest",
                            wie_die_app({"terms_accepted": True, "lang": "de"}))
    assert status == 200, daten
    return browser, daten


def _gast_id() -> str:
    assert web.AUTH is not None
    with sqlite3.connect(web.AUTH.db_path) as conn:
        zeilen = conn.execute("SELECT id FROM users WHERE guest != ''").fetchall()
    assert len(zeilen) == 1
    return str(zeilen[0][0])


def test_guests_need_the_privacy_notice_and_the_terms(server: int) -> None:
    browser = Browser(server)
    assert browser("POST", "/api/auth/guest", wie_die_app({"terms_accepted": True}))[0] == 403
    browser("POST", "/api/consent", {"accepted": True})
    status, daten = browser("POST", "/api/auth/guest", wie_die_app({"lang": "de"}))
    assert status == 400 and daten["error"] == web.GAST_ZUSTIMMUNG


def test_a_guest_gets_a_cookie_that_ends_with_the_browser(server: int) -> None:
    browser, daten = _gast(server)
    assert daten["ok"] is True and daten["account"]["guest"] is True
    assert daten["account"]["email"] == ""
    auth_keks = [k for k in browser.roh if k.startswith(web.AUTH_COOKIE + "=")]
    assert auth_keks and "Max-Age" not in auth_keks[0] and "HttpOnly" in auth_keks[0]
    _, stand = browser("GET", "/api/auth/status")
    assert stand["authenticated"] is True and stand["guest"] is True
    assert stand["guest_allowed"] is True
    _, konto = browser("GET", "/api/account")
    assert konto["guest"] is True and konto["plan_label"] == "Gast"


def test_guests_cannot_use_password_mail_or_google(server: int) -> None:
    browser, _ = _gast(server)
    for pfad, body in (("/api/account/password", {"password": "x", "new_password": PASSWORT}),
                       ("/api/account/wipe", {"password": "x"}),
                       ("/api/account/delete", {"password": "x", "confirm": "LÖSCHEN"}),
                       ("/api/google", {"action": "start"})):
        status, daten = browser("POST", pfad, body)
        assert status == 403 and daten["error"] == web.GAST_NUR_KONTO, pfad
    if hasattr(web, "ZWEI_FAKTOR"):
        status, daten = browser("POST", "/api/account/2fa", {"action": "an"})
        assert status in (401, 403)
    if "/api/learning" in Path(web.__file__).read_text(encoding="utf-8"):
        status, _ = browser("POST", "/api/learning", {"enabled": True})
        assert status in (403, 404)


def test_ending_a_guest_deletes_the_account_and_its_data(server: int) -> None:
    browser, _ = _gast(server)
    assert web.AUTH is not None
    kennung = _gast_id()
    profil = web.AUTH.profile_dir(kennung)
    (profil / "notiz.txt").write_text("nur fuer diesen Tab", encoding="utf-8")
    status, daten = browser("POST", "/api/auth/guest/end", {})
    assert status == 200 and daten["ended"] is True
    assert web.AUTH_COOKIE not in browser.kekse
    assert web.AUTH.account(kennung) is None and not profil.exists()
    assert browser("GET", "/api/auth/status")[1]["authenticated"] is False


def test_signing_out_as_a_guest_also_deletes_it(server: int) -> None:
    browser, _ = _gast(server)
    assert web.AUTH is not None
    kennung = _gast_id()
    browser("POST", "/api/auth/logout", {})
    assert web.AUTH.account(kennung) is None


def test_guest_end_never_deletes_a_real_account(server: int) -> None:
    browser = Browser(server)
    browser("POST", "/api/consent", {"accepted": True})
    status, _ = browser("POST", "/api/auth/register", {
        "email": "ana@example.org", "username": "Ana", "password": PASSWORT, "plan": "normal",
        "terms_accepted": True})
    assert status == 200
    status, daten = browser("POST", "/api/auth/guest/end", {})
    assert status == 400 and daten["ok"] is False
    assert web.AUTH is not None and web.AUTH.authenticate("ana@example.org", PASSWORT)
    assert browser("GET", "/api/auth/status")[1]["authenticated"] is True


def test_expired_guests_are_cleaned_up(server: int) -> None:
    assert web.AUTH is not None
    alt = web.AUTH.create_guest(ip=ADRESSE, terms_version="t")
    frisch = web.AUTH.create_guest(ip=ADRESSE, terms_version="t")
    web.AUTH.create_session(frisch, "geraet", ADRESSE)
    with sqlite3.connect(web.AUTH.db_path) as conn:
        conn.execute("UPDATE users SET created_at = created_at - 400 WHERE id IN (?, ?)",
                     (alt.id, frisch.id))
    assert web.gaeste_aufraeumen(sofort=True) == 1
    assert web.AUTH.account(alt.id) is None and web.AUTH.account(frisch.id) is not None
    with sqlite3.connect(web.AUTH.db_path) as conn:
        conn.execute("UPDATE users SET created_at = created_at - 13 * 3600 WHERE id = ?",
                     (frisch.id,))
    assert web.gaeste_aufraeumen(sofort=True) == 1
    assert web.AUTH.account(frisch.id) is None


def test_no_guest_access_with_a_single_account(server: int, tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(web, "AUTH", AuthStore(tmp_path / "einzel", "PRO234567", single=True))
    browser = Browser(server)
    browser("POST", "/api/consent", {"accepted": True})
    assert browser("GET", "/api/auth/status")[1]["guest_allowed"] is False
    status, daten = browser("POST", "/api/auth/guest",
                            wie_die_app({"terms_accepted": True, "lang": "de"}))
    assert status == 403 and "Einzelkonto" in daten["error"]


def test_closing_the_tab_shortens_the_guest_session(server: int) -> None:
    browser, _ = _gast(server)
    assert web.AUTH is not None
    kennung = _gast_id()

    def sitzung() -> tuple[float, float]:
        assert web.AUTH is not None
        with sqlite3.connect(web.AUTH.db_path) as conn:
            zeile = conn.execute(
                "SELECT sessions.expires_at, users.created_at FROM sessions "
                "JOIN users ON users.id = sessions.user_id WHERE users.id = ?",
                (kennung,)).fetchone()
        return float(zeile[0]), float(zeile[1])

    status, daten = browser("POST", "/api/auth/guest/pause", {})
    assert status == 200 and daten["ok"] is True
    assert sitzung()[0] <= time.time() + auth_mod.GAST_PAUSE_SEKUNDEN + 1
    # Neu geladen: volle Zeit zurueck -- nie laenger als 12 Stunden ab dem Anlegen.
    assert browser("POST", "/api/auth/guest/resume", {})[1]["ok"] is True
    bis, angelegt = sitzung()
    assert abs(bis - (angelegt + auth_mod.GAST_STUNDEN * 3600)) < 1
    # Tab zu: Nach der Pause ist die Sitzung abgelaufen, der Gast geht beim Aufraeumen.
    browser("POST", "/api/auth/guest/pause", {})
    with sqlite3.connect(web.AUTH.db_path) as conn:
        conn.execute("UPDATE sessions SET expires_at = ? WHERE user_id = ?",
                     (time.time() - 1, kennung))
        conn.execute("UPDATE users SET created_at = created_at - 400 WHERE id = ?", (kennung,))
    assert web.gaeste_aufraeumen(sofort=True) == 1
    assert web.AUTH.account(kennung) is None


def test_pause_never_touches_a_real_account(server: int) -> None:
    browser = Browser(server)
    browser("POST", "/api/consent", {"accepted": True})
    browser("POST", "/api/auth/register", {
        "email": "ana@example.org", "username": "Ana", "password": PASSWORT, "plan": "normal",
        "terms_accepted": True})
    assert browser("POST", "/api/auth/guest/pause", {})[1]["ok"] is False
    assert web.AUTH is not None
    with sqlite3.connect(web.AUTH.db_path) as conn:
        bis = conn.execute("SELECT MAX(expires_at) FROM sessions").fetchone()[0]
    assert bis > time.time() + 29 * 86400


# -- Oberflaeche und Datenschutz ----------------------------------------------------------------

def test_the_page_offers_guest_access_only_when_allowed() -> None:
    seite = (ROOT / "aquaticy" / "webui.html").read_text(encoding="utf-8")
    karte = seite[seite.index('id="login-card"'):seite.index('id="leave-card"')]
    assert 'id="gast-los">Ohne Anmeldung fortfahren</button>' in karte
    # Nach den Formularen: Der Fokus beim Oeffnen bleibt im Anmeldeformular.
    assert karte.index('id="gast-bereich"') > karte.index('id="auth-form"')
    assert 'class="gast-bereich" id="gast-bereich" hidden' in karte
    assert '$("#gast-bereich").hidden = !gastErlaubt;' in seite
    assert "state.guest_allowed === true" in seite
    # Der Merker lebt nur im Tab; fehlt er, geht der Gast.
    assert "sessionStorage.setItem(GAST_MERKER" in seite
    assert 'state.authenticated && state.guest && !gastMerker()' in seite
    assert seite.count('"/api/auth/guest/end"') >= 2
    # Einstellungen -> Konto: "Anmelden" nur fuer Gaeste, der Rest nicht fuer Gaeste.
    assert 'id="gast-konto" hidden' in seite and 'id="gast-anmelden">Anmelden</button>' in seite
    assert '<div class="danger-zone" data-kein-gast>' in seite
    assert '$("#gast-konto").hidden = !istGast;' in seite
    # Tab zu: kurze Pause per keepalive; neu geladen: volle Zeit zurueck.
    assert 'window.addEventListener("pagehide"' in seite and "keepalive:true" in seite
    assert '"/api/auth/guest/pause"' in seite and '"/api/auth/guest/resume"' in seite
    # Der Regler nach einer 428 schickt die Gast-Anfrage erneut, nicht das Formular.
    assert "if (gastWartet){ gastWartet = false;" in seite
    en = json.loads("{" + seite.split("const EN = {", 1)[1].split("\n};", 1)[0].rstrip(",\n")
                    + "}")
    for text in ("Ohne Anmeldung fortfahren", "Gast", "Jetzt anmelden?",
                 "Stimm zuerst der Datenschutzerklärung und den Nutzungsbedingungen zu."):
        assert en.get(text), text


def test_the_privacy_page_explains_guest_access() -> None:
    text = legal_page("/privacy").decode("utf-8") if isinstance(
        legal_page("/privacy"), bytes) else str(legal_page("/privacy"))
    assert "Ohne Anmeldung (Gast)" in text and "12 Stunden" in text
    assert "kein Ablaufdatum" in text and "acht Tage" in text

