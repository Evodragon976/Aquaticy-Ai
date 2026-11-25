"""17.1.0: Funde aus 17.0.0 und weitere Fehler -- ohne Netz, Konten in ``tmp_path``."""

from __future__ import annotations

import json
import sqlite3
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from aquaticy import aiguard, web
from aquaticy.auth import AuthStore
from tests.test_v1700 import ADRESSE, PASSWORT, _gast

ROOT = Path(__file__).resolve().parents[1]


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
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def test_guests_never_see_their_internal_address(server: int) -> None:
    # 17.0.0 gab "gast-...@gast.invalid" in Status, Konto und Einstellungen heraus.
    browser, _ = _gast(server)
    for pfad in ("/api/auth/status", "/api/account", "/api/config"):
        status, daten = browser("GET", pfad)
        assert status == 200 and "gast.invalid" not in json.dumps(daten), pfad


def test_deleting_guests_is_reported_so_vercel_saves_it(server: int) -> None:
    # Auf Vercel speichert der Rahmen nach GET nichts -- das Loeschen in /api/auth/status
    # meldet sich deshalb, damit trotzdem gespeichert wird.
    assert web.AUTH is not None
    alt = web.AUTH.create_guest(ip=ADRESSE, terms_version="t")
    with sqlite3.connect(web.AUTH.db_path) as conn:
        conn.execute("UPDATE users SET created_at = created_at - 400 WHERE id = ?", (alt.id,))
    web.gaeste_geloescht_abholen()
    assert web.gaeste_aufraeumen(sofort=True) == 1
    assert web.gaeste_geloescht_abholen() is True
    assert web.gaeste_geloescht_abholen() is False
    assert web.gaeste_aufraeumen(sofort=True) == 0
    assert web.gaeste_geloescht_abholen() is False



def test_cleanup_starts_with_the_own_address_and_skips_failures(
        server: int, monkeypatch: pytest.MonkeyPatch) -> None:
    # Ein Durchgang loescht hoechstens GAESTE_JE_DURCHGANG Gaeste. Vor einem neuen Gast kommen die
    # abgelaufenen Gaeste der eigenen Adresse zuerst dran -- sonst hiesse es "schon genug Gaeste
    # da". Was nicht klappt, zaehlt nicht mit: Sonst hielten dieselben Fehlschlaege alle auf.
    assert web.AUTH is not None
    andere = [web.AUTH.create_guest(ip=f"198.51.100.{i}", terms_version="t") for i in range(3)]
    eigener = web.AUTH.create_guest(ip=ADRESSE, terms_version="t")
    with sqlite3.connect(web.AUTH.db_path) as conn:
        for alter, konto in zip((1000, 900, 800, 500), (*andere, eigener), strict=True):
            conn.execute("UPDATE users SET created_at = created_at - ? WHERE id = ?",
                         (alter, konto.id))
    assert web.AUTH.expired_guests()[0] == andere[0].id
    assert web.AUTH.expired_guests(vorrang_ip=ADRESSE)[0] == eigener.id
    monkeypatch.setattr(web, "GAESTE_JE_DURCHGANG", 1)
    assert web.gaeste_aufraeumen(sofort=True, adresse=ADRESSE) == 1
    assert web.AUTH.account(eigener.id) is None

    echt = web.konto_entfernen

    def entfernen(konto: object) -> None:
        if getattr(konto, "id", "") == andere[0].id:
            raise TimeoutError("belegt")
        echt(konto)  # type: ignore[arg-type]

    monkeypatch.setattr(web, "konto_entfernen", entfernen)
    assert web.gaeste_aufraeumen(sofort=True) == 1
    assert web.AUTH.account(andere[0].id) is not None
    assert web.AUTH.account(andere[1].id) is None
    assert web.AUTH.account(andere[2].id) is not None

def test_sign_in_works_while_the_guest_column_is_missing(tmp_path: Path) -> None:
    # Eine Datenbank von einer aelteren Instanz hat die Spalte noch nicht: Anmelden geht trotzdem.
    store = AuthStore(tmp_path / "konten", "PRO234567")
    store.register("ana@example.org", PASSWORT, "normal", username="Ana", terms_accepted=True,
                   terms_version="t")
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("ALTER TABLE users DROP COLUMN guest")
    konto = store.authenticate("ana@example.org", PASSWORT)
    assert konto is not None and not konto.guest


def test_parts_without_letters_skip_the_insult_check(monkeypatch: pytest.MonkeyPatch) -> None:
    # "1,1,1,..." pruefte jeden der 50.000 Teile voll (2 s); jetzt ohne Buchstaben sofort 0.
    aufrufe: list[str] = []
    echt = aiguard._dritte_person
    monkeypatch.setattr(aiguard, "_dritte_person", lambda t: aufrufe.append(t) or echt(t))
    assert aiguard.insult_level("1," * 1000) == 0
    assert aufrufe == []
    assert aiguard.insult_level("du Idiot") >= 2 and aufrufe


def test_the_page_handles_guest_details_in_both_languages() -> None:
    seite = (ROOT / "aquaticy" / "webui.html").read_text(encoding="utf-8")
    # #account-email wird nicht uebersetzt -- der Gast-Text kommt deshalb in beiden Sprachen.
    assert 'sp("Keine, du bist Gast", "None, you\'re a guest")' in seite
    # "Anmelden" in den Einstellungen fuehrt auf den Reiter "Anmelden".
    assert 'sessionStorage.setItem("aquaticy-anmelden", "1")' in seite
    assert 'sessionStorage.getItem("aquaticy-anmelden") === "1"' in seite
    # Bleibt die Seite im Zwischenspeicher, ist der Tab nicht zu: keine Pause.
    assert "if (!istGast || event.persisted) return;" in seite


def test_learning_consent_does_not_follow_every_legal_change(tmp_path: Path) -> None:
    # 17.0.0 zaehlte LEGAL_VERSION hoch (Absatz zum Gastzugang) und schaltete damit das
    # Gemeinsame Lernen bei allen still ab. Die Zustimmung haengt jetzt am Lern-Absatz.
    from aquaticy.learning import Learning
    from aquaticy.legal import LEARNING_VERSION, LEGAL_VERSION

    assert LEARNING_VERSION == "2026-10-07.1" and LEARNING_VERSION != LEGAL_VERSION
    lernen = Learning(tmp_path / "profil")
    lernen.set_consent(True, LEARNING_VERSION)
    assert lernen.status()["enabled"] is True and lernen.status()["version"] == LEARNING_VERSION
    quelle = (ROOT / "aquaticy" / "web.py").read_text(encoding="utf-8")
    assert '"learning_version": LEARNING_VERSION,' in quelle



@pytest.mark.parametrize("an", [True, False])
def test_consent_given_under_17_0_0_stays_as_it_was(tmp_path: Path, an: bool) -> None:
    # 17.0.0 speicherte die Zustimmung unter 2026-11-24.1. Der Absatz zum Lernen war derselbe:
    # Wer zugestimmt hat, bleibt dabei -- wer abgeschaltet hat, bleibt abgeschaltet.
    import time

    from aquaticy.learning import Learning

    lernen = Learning(tmp_path / "profil")
    with lernen.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO learning_consent VALUES (?, ?, ?, ?, ?)",
                     (lernen.owner, "2026-11-24.1", int(an), "epoche", time.time()))
    assert Learning(tmp_path / "profil").status()["enabled"] is an

def test_a_guest_gets_twenty_megabytes(tmp_path: Path) -> None:
    # Vorher bekam jeder Gast 400 MB wie ein Konto -- drei Gaeste je Adresse fuellten 1,2 GB.
    from aquaticy import budget

    store = AuthStore(tmp_path / "konten", "PRO234567")
    gast = store.create_guest(ip=ADRESSE, terms_version="t")
    ordner = store.profile_dir(gast.id)
    assert (ordner / budget.GAST_MARKE).exists()
    assert budget.grenze(ordner) == 20_000_000
    konto = store.register("ana@example.org", PASSWORT, "normal", username="Ana",
                           terms_accepted=True, terms_version="t")
    assert budget.grenze(store.profile_dir(konto.id)) == budget.MAX_BYTES



def test_the_guest_limit_holds_on_the_way_the_app_takes(server: int) -> None:
    # Die App rechnet mit dem Profil der Sitzung -- dort liegt die Marke des Gastes.
    browser, _ = _gast(server)
    status, daten = browser("GET", "/api/memory")
    assert status == 200 and daten["enabled"] is True
    assert daten["usage"]["limit_mb"] == 20, daten["usage"]

@pytest.mark.parametrize("frage, antwort", [
    ("Welcher Wochentag ist der 29.02.0000?", "Den 29.02.0000 gibt es nicht."),
    ("Wie viele Tage hat der Monat Februar?", "Der Februar 2026 hat **28 Tage**."),
    ("Wie viele Tage hat der Monat Februar 2028?", "Der Februar 2028 hat **29 Tage**."),
    ("how many days does this month have?", "November 2026 has **30 days**."),
    ("how many days in this month?", "November 2026 has **30 days**."),
    ("Welcher Wochentag ist der 24.12.26?", "Der 24.12.2026 ist ein **Donnerstag**."),
])
def test_standard_reads_month_and_year_correctly(frage: str, antwort: str) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from aquaticy import standard

    jetzt = datetime(2026, 11, 25, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert standard._antwort(frage, [], holen=lambda url: None, jetzt=jetzt) == antwort


def test_a_number_chain_is_no_date() -> None:
    # "1.1.1" galt vorher als 1. Januar dieses Jahres ("Der 01.01.2026 war ein Donnerstag").
    from datetime import date

    from aquaticy import standard

    assert standard.datum_aus("welcher wochentag ist der 1.1.1", date(2026, 11, 25)) is None
    assert standard.datum_aus("version 1.24.12", date(2026, 11, 25)) is None
    assert standard.datum_aus("am 24.12. um 18 uhr", date(2026, 11, 25)) == date(2026, 12, 24)


@pytest.mark.parametrize("frage, antwort", [
    ("Welche Kalenderwoche ist morgen?", "Der 30.11.2026 liegt in **KW 49** (2026)."),
    ("Welche KW ist übermorgen?", "Der 01.12.2026 liegt in **KW 49** (2026)."),
    ("Guten Morgen, welche Kalenderwoche haben wir?", "Wir haben **KW 48**."),
    ("Welche Kalenderwoche haben wir heute Morgen?", "Wir haben **KW 48**."),
    ("Welches Datum ist heute Morgen?", "Heute ist **Sonntag, der 29.11.2026** (KW 48)."),
    ("100 km in miles", "100 km is **62.1371 miles**."),
    ("Welche Kalenderwoche ist der 29.02.2027?",
     "Den 29.02.2027 gibt es nicht – 2027 ist kein Schaltjahr."),
])
def test_the_calendar_week_belongs_to_the_day_asked(frage: str, antwort: str) -> None:
    # Vorher nannten "morgen" und ein Datum, das es nicht gibt, die Woche von heute.
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from aquaticy import standard

    sonntag = datetime(2026, 11, 29, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert standard._antwort(frage, [], holen=lambda url: None, jetzt=sonntag) == antwort


def test_a_greeting_does_not_swallow_the_question() -> None:
    # "Hello, what day is it?" kam vorher nur als Gruss an: "what", "day", "is" und "it" sind
    # Fuellwoerter. Ein Gruss allein bleibt ein Gruss.
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from aquaticy import standard

    jetzt = datetime(2026, 11, 25, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))

    def frag(frage: str) -> str:
        return standard._antwort(frage, [], holen=lambda url: None, jetzt=jetzt)

    assert frag("Hello, what day is it?") == "Today is 2026-11-25."
    assert frag("Halo, hari apa ini?") == "Hari ini 2026-11-25."
    assert frag("Hello").startswith("Hello! I'm Aquaticy Standard.")
