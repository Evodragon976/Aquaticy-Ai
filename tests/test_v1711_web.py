"""17.1.1: Ein neuer Chat geht auch auf einer anderen Instanz (Vercel), Gaeste ohne Namen.

Ohne Netz: Aquaticy Standard antwortet, Konten liegen in ``tmp_path``.
"""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from aquaticy import config, web
from aquaticy.auth import AuthStore
from tests.anmeldung import AGENT, FETCH, wie_die_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AQUATICY_DATA_DIR", str(tmp_path / "daten"))
    monkeypatch.setenv("AQUATICY_MODEL", "aquaticy/standard")
    monkeypatch.setenv("AQUATICY_SUBAGENTS_AUTO", "false")
    config.reset_settings_cache()
    monkeypatch.setattr(web, "AUTH", AuthStore(tmp_path / "konten", "PRO234567"))
    monkeypatch.setattr(web, "SESSIONS", web.SessionRegistry())
    monkeypatch.setattr(web, "SESSION", web.SessionProxy())
    monkeypatch.setattr(web, "strong_models", lambda *args, **kwargs: [])
    monkeypatch.setattr(web, "AIGUARD", None)
    monkeypatch.setattr(web, "AUTH_LIMIT", web.RateLimiter(attempts=100, window_seconds=60))
    monkeypatch.setattr(web, "GAST_LIMIT", web.RateLimiter(attempts=100, window_seconds=60))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()
    config.reset_settings_cache()


class Browser:
    def __init__(self, port: int) -> None:
        self.port = port
        self.kekse: dict[str, str] = {}

    def __call__(self, methode: str, pfad: str, body: object = None,
                 chat: str = "") -> tuple[int, str]:
        conn = HTTPConnection("127.0.0.1", self.port, timeout=30)
        kopf = {"Content-Type": "application/json", "User-Agent": AGENT,
                "Accept-Language": "de-DE", **FETCH}
        if chat:
            kopf["X-Aquaticy-Chat"] = chat
        if self.kekse:
            kopf["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.kekse.items())
        conn.request(methode, pfad, body=None if body is None else json.dumps(body),
                     headers=kopf)
        antwort = conn.getresponse()
        roh = antwort.read().decode("utf-8", "replace")
        for name, wert in antwort.getheaders():
            if name.lower() == "set-cookie":
                schluessel, _, rest = wert.partition("=")
                self.kekse[schluessel] = rest.split(";", 1)[0]
        conn.close()
        return antwort.status, roh


def _gast(port: int) -> Browser:
    browser = Browser(port)
    browser("POST", "/api/consent", {"accepted": True})
    status, roh = browser("POST", "/api/auth/guest",
                          wie_die_app({"terms_accepted": True, "lang": "de"}))
    assert status == 200, roh
    return browser


def _andere_instanz(monkeypatch: pytest.MonkeyPatch) -> None:
    # Eine zweite Vercel-Instanz: dieselben Daten, aber nichts im Speicher.
    monkeypatch.setattr(web, "SESSIONS", web.SessionRegistry())
    monkeypatch.setattr(web, "SESSION", web.SessionProxy())


def test_a_new_chat_works_on_another_instance(server: int,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    # Vorher: "Diesen Chat gibt es nicht mehr." -- auch fuer "Neuer Chat" und "Oeffnen".
    browser = _gast(server)
    status, roh = browser("POST", "/api/clear", {})
    neu = json.loads(roh)["current"]
    assert status == 200 and web.CHAT_KENNUNG.fullmatch(neu)
    _andere_instanz(monkeypatch)
    status, roh = browser("POST", "/api/chat", {"message": "Hallo", "mode": "normal"}, chat=neu)
    assert status == 200 and '"type": "done"' in roh
    # Die andere Instanz kennt den leeren Chat nicht: Die Nachricht landet in einem frischen
    # Chat mit neuer Kennung, die die Seite aus dem Ereignis "chat" uebernimmt.
    kennung = json.loads(roh.split("data: ", 2)[1].split("\n", 1)[0])["session_id"]
    assert kennung != neu and web.CHAT_KENNUNG.fullmatch(kennung)
    _andere_instanz(monkeypatch)
    status, roh = browser("POST", "/api/open", {"session_id": kennung}, chat=neu)
    daten = json.loads(roh)
    assert status == 200 and daten["ok"] is True and daten["turns"][0]["question"] == "Hallo"
    _andere_instanz(monkeypatch)
    status, roh = browser("POST", "/api/clear", {}, chat=neu)
    assert status == 200 and json.loads(roh)["current"] not in (neu, kennung)


def test_a_foreign_chat_id_is_never_taken_over(server: int,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    anna, bert = _gast(server), _gast(server)
    _, roh = anna("POST", "/api/clear", {})
    fremd = json.loads(roh)["current"]
    # Lauf-Abfragen mit einer fremden Kennung bleiben abgelehnt (wie test_v1211_terra).
    assert bert("GET", "/api/runstate", chat=fremd)[0] == 400
    status, roh = bert("POST", "/api/chat", {"message": "Hallo", "mode": "normal"}, chat=fremd)
    assert status == 200 and f'"session_id": "{fremd}"' not in roh


def test_a_strange_chat_id_is_still_refused(server: int) -> None:
    browser = _gast(server)
    status, roh = browser("POST", "/api/chat", {"message": "Hallo"}, chat="../../etc")
    assert status == 400 and json.loads(roh)["error"] == "Diesen Chat gibt es nicht mehr."


def test_the_page_greets_guests_without_their_name_and_retries_opening() -> None:
    seite = (ROOT / "aquaticy" / "webui.html").read_text(encoding="utf-8")
    # Vorher: "Hallo, Gast-4FE682. Wobei kann ich dir helfen?"
    assert 'grussZiehen(saetze, when, istGast ? "" : currentUsername)' in seite
    # "Neuer Chat" und "Chat öffnen" versuchen es nach 502/503/504 noch einmal.
    assert '["/api/open", "/api/clear"].includes(path)' in seite
