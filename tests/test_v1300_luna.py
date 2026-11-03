"""13.0.0 Luna: Code-Chats getrennt von Normal/Pro, Einzelkonto als Standard."""

from __future__ import annotations

import json
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from aquaticy import cli, guardrails, web
from aquaticy.auth import LOCAL_EMAIL_DOMAIN, SINGLE_TAKEN, AuthStore
from aquaticy.cache import Cache, chat_kind_of
from tests import fake_llm
from tests.anmeldung import wie_die_app
from tests.test_end_to_end import ECHTER_PRUEFER, _chat, _req

ROOT = Path(__file__).resolve().parents[1]
CODE = "Abcdef1234567!"
PASSWORT = "ein langes Passwort"


# -- Chat-Art im Speicher -------------------------------------------------------------------------
@pytest.fixture
def cache(tmp_path: Path) -> Cache:
    return Cache(tmp_path / "chats.sqlite3", 1)


def test_the_first_answer_fixes_the_kind_of_a_chat(cache: Cache) -> None:
    cache.add_history("c1", "Bau mir ein Skript", "print(1)", {}, mode="code")
    cache.add_history("c1", "Und noch was", "ok", {}, mode="normal")
    assert cache.chat_mode("c1") == {"kind": "code", "mode": "code"}, "bleibt ein Code-Chat"
    cache.add_history("n1", "Was ist neu?", "Viel", {}, mode="normal")
    cache.add_history("n1", "Genauer", "Mehr", {}, mode="pro")
    assert cache.chat_mode("n1") == {"kind": "chat", "mode": "pro"}, "Normal zu Pro geht"
    cache.add_history("n1", "Code bitte", "nein", {}, mode="code")
    assert cache.chat_mode("n1") == {"kind": "chat", "mode": "pro"}, "Code aendert ihn nicht"


def test_old_chats_without_a_kind_stay_chats(cache: Cache) -> None:
    cache.add_history("alt", "Frage von frueher", "Antwort", {})
    assert cache.chat_mode("alt") == {"kind": "chat", "mode": "normal"}
    cache.add_history("alt", "Jetzt Code", "x", {}, mode="code")
    assert cache.chat_mode("alt")["kind"] == "chat"
    assert cache.chat_mode("gibt-es-nicht") is None
    assert cache.chat_mode("") is None


def test_unknown_modes_are_ignored(cache: Cache) -> None:
    cache.add_history("x", "Frage", "Antwort", {}, mode="'; DROP TABLE history; --")
    assert cache.chat_mode("x") == {"kind": "chat", "mode": "normal"}
    assert len(cache.recent_chats()) == 1


def test_the_lists_are_separate_and_name_the_mode(cache: Cache) -> None:
    cache.add_history("code1", "Skript", "a", {}, mode="code")
    cache.add_history("pro1", "Große Frage", "b", {}, mode="pro")
    cache.add_history("norm1", "Kleine Frage", "c", {}, mode="normal")
    cache.add_history("alt1", "Alt", "d", {})
    code = cache.recent_chats(kind="code")
    chats = cache.recent_chats(kind="chat")
    assert [c["session_id"] for c in code] == ["code1"]
    assert [c["session_id"] for c in chats] == ["alt1", "norm1", "pro1"]
    assert {c["session_id"]: c["mode"] for c in chats} == {"alt1": "", "norm1": "normal",
                                                           "pro1": "pro"}
    assert len(cache.recent_chats()) == 4, "ohne Art: alle"
    assert len(cache.recent_chats(kind="unsinn")) == 4
    assert [c["session_id"] for c in cache.search_chats("Frage", kind="chat")] == [
        "norm1", "pro1"]
    assert cache.search_chats("Skript", kind="chat") == []
    assert [c["session_id"] for c in cache.search_chats("Skript", kind="code")] == ["code1"]


def test_deleting_a_chat_forgets_its_kind(cache: Cache) -> None:
    cache.add_history("c1", "Skript", "a", {}, mode="code")
    cache.delete_chat("c1")
    assert cache.chat_mode("c1") is None
    cache.add_history("c1", "Neu", "b", {}, mode="normal")
    assert cache.chat_mode("c1") == {"kind": "chat", "mode": "normal"}


@pytest.mark.parametrize(("mode", "art"), [("code", "code"), ("normal", "chat"), ("pro", "chat"),
                                           ("", "chat"), ("CODE", "code")])
def test_the_kind_of_a_mode(mode: str, art: str) -> None:
    assert chat_kind_of(mode) == art


def test_a_mode_that_does_not_fit_the_open_chat_is_refused(cache: Cache, tmp_path: Path) -> None:
    sitzung = SimpleNamespace(
        settings=lambda: SimpleNamespace(db_path=tmp_path / "chats.sqlite3", cache_ttl_hours=1),
        chat_id=lambda: "c1")
    assert web.chat_kind_conflict(sitzung, "code") == "", "ein neuer Chat nimmt alles"
    cache.add_history("c1", "Skript", "a", {}, mode="code")
    assert web.chat_kind_conflict(sitzung, "code") == ""
    assert web.chat_kind_conflict(sitzung, "normal") == web.CODE_CHAT_ONLY
    assert web.chat_kind_conflict(sitzung, "pro") == web.CODE_CHAT_ONLY
    cache.add_history("c2", "Frage", "b", {}, mode="normal")
    sitzung.chat_id = lambda: "c2"
    assert web.chat_kind_conflict(sitzung, "pro") == ""
    assert web.chat_kind_conflict(sitzung, "code") == web.CHAT_NOT_CODE


def test_the_page_keeps_code_chats_apart() -> None:
    html = (ROOT / "aquaticy" / "webui.html").read_text(encoding="utf-8")
    for teil in ("const chatArt = (m = mode) =>", "/api/chats?kind=${art}",
                 'id="side-title"', 'id="btn-new-label"', "function zeigeChatArt()",
                 'if (data.kind === "code" && mode !== "code") setMode("code");',
                 "if (chatArt() !== artVorher){"):
        assert teil in html, teil
    assert "if (anders && thread.children.length) neuerChat" not in html


# -- Einzelkonto im Speicher ----------------------------------------------------------------------
@pytest.fixture
def einzeln(tmp_path: Path) -> AuthStore:
    return AuthStore(tmp_path / "konten", "PRO123456", CODE, single=True)


def test_the_one_account_needs_the_setup_code_and_is_ultra(einzeln: AuthStore) -> None:
    with pytest.raises(ValueError, match="Einrichtungscode"):
        einzeln.register("", PASSWORT, "normal", "falsch", username="Jonas")
    konto = einzeln.register("", PASSWORT, "normal", CODE, username="Jonas")
    assert konto.plan == "ultra" and konto.username == "Jonas"
    assert konto.email.endswith("@" + LOCAL_EMAIL_DOMAIN)
    assert einzeln.owner() == konto


def test_there_is_never_a_second_account(einzeln: AuthStore) -> None:
    einzeln.register("", PASSWORT, "ultra", CODE, username="Jonas")
    for name in ("Zweiter", "jonas"):
        with pytest.raises(ValueError) as fehler:
            einzeln.register("x@example.org", PASSWORT, "ultra", CODE, username=name)
        assert str(fehler.value) == SINGLE_TAKEN
    assert len(einzeln.accounts()) == 1


def test_the_command_line_needs_no_code(einzeln: AuthStore) -> None:
    konto = einzeln.register("", PASSWORT, "normal", "", username="Jonas", trusted=True)
    assert konto.ultra


def test_login_with_the_username_or_the_email(einzeln: AuthStore) -> None:
    konto = einzeln.register("", PASSWORT, "ultra", CODE, username="Jonas")
    assert einzeln.login("Jonas", PASSWORT) == konto
    assert einzeln.login("  jonas ", PASSWORT) == konto
    assert einzeln.login(konto.email, PASSWORT) == konto
    assert einzeln.login("Jonas", "falsches Passwort!") is None
    assert einzeln.login("Fremder", PASSWORT) is None
    assert einzeln.login("", PASSWORT) is None


def _mehrere(tmp_path: Path) -> tuple[Any, Any, Any]:
    """Konten aus der Zeit mit Kontensystem -- danach ist es aus."""
    mehr = AuthStore(tmp_path / "konten", "PRO123456", CODE)
    normal = mehr.register("a@example.org", PASSWORT, "normal", username="Anna",
                           terms_accepted=True, terms_version="1")
    ultra = mehr.register("b@example.org", PASSWORT, "ultra", CODE, username="Bernd",
                          terms_accepted=True, terms_version="1")
    return mehr, normal, ultra


def test_with_accounts_off_only_the_owner_gets_in(tmp_path: Path) -> None:
    mehr, normal, ultra = _mehrere(tmp_path)
    alte_sitzung = mehr.create_session(normal, "geraet", "127.0.0.1")
    einzeln = AuthStore(tmp_path / "konten", "PRO123456", CODE, single=True)
    assert einzeln.owner().id == ultra.id, "das aelteste Ultra-Konto"
    assert einzeln.login("Anna", PASSWORT) is None
    assert einzeln.login("a@example.org", PASSWORT) is None
    assert einzeln.session_account(alte_sitzung, "geraet", "127.0.0.1") is None
    with pytest.raises(ValueError):
        einzeln.create_session(normal, "geraet", "127.0.0.1")
    besitzer = einzeln.login("Bernd", PASSWORT)
    token = einzeln.create_session(besitzer, "geraet", "127.0.0.1")
    assert einzeln.session_account(token, "geraet", "127.0.0.1").id == ultra.id
    assert [k.id for k in einzeln.active_accounts()] == [ultra.id]
    assert len(einzeln.accounts()) == 2, "nichts wird geloescht"
    assert mehr.session_account(alte_sitzung, "geraet", "127.0.0.1") is not None, \
        "mit dem Kontensystem geht es wieder"


def test_without_an_ultra_account_the_oldest_becomes_ultra(tmp_path: Path) -> None:
    mehr = AuthStore(tmp_path / "konten", "PRO123456", CODE)
    erstes = mehr.register("a@example.org", PASSWORT, "normal", username="Anna",
                           terms_accepted=True, terms_version="1")
    mehr.register("c@example.org", PASSWORT, "pro", "PRO123456", username="Carla",
                  terms_accepted=True, terms_version="1")
    einzeln = AuthStore(tmp_path / "konten", "PRO123456", CODE, single=True)
    besitzer = einzeln.ensure_owner_ultra()
    assert besitzer.id == erstes.id and besitzer.plan == "ultra"


def test_resetting_the_account_changes_name_and_password_and_logs_out(
        einzeln: AuthStore) -> None:
    konto = einzeln.register("", PASSWORT, "ultra", CODE, username="Jonas")
    token = einzeln.create_session(konto, "geraet", "127.0.0.1")
    neu = einzeln.reset_owner("Jonas L", "ein neues langes Passwort")
    assert neu.id == konto.id and neu.username == "Jonas L" and neu.ultra
    assert einzeln.session_account(token, "geraet", "127.0.0.1") is None, "alle abgemeldet"
    assert einzeln.login("Jonas L", "ein neues langes Passwort") is not None
    assert einzeln.login("Jonas L", PASSWORT) is None
    with pytest.raises(ValueError, match="12 Zeichen"):
        einzeln.reset_owner("Jonas", "kurz")


def test_resetting_without_an_account_creates_it(einzeln: AuthStore) -> None:
    konto = einzeln.reset_owner("Jonas", PASSWORT)
    assert konto.ultra and einzeln.owner() == konto


def test_the_name_of_another_old_account_cannot_be_taken(tmp_path: Path) -> None:
    _mehrere(tmp_path)
    einzeln = AuthStore(tmp_path / "konten", "PRO123456", CODE, single=True)
    with pytest.raises(ValueError, match="anderes Konto"):
        einzeln.reset_owner("anna", PASSWORT)


def test_the_terminal_names_the_account_or_the_setup_code(tmp_path: Path) -> None:
    einzeln = AuthStore(tmp_path / "eins", "PRO123456", CODE, single=True)
    zeilen = "\n".join(web.auth_banner(einzeln))
    assert CODE in zeilen and "Einrichtungscode" in zeilen and "PRO123456" not in zeilen
    einzeln.register("", PASSWORT, "ultra", CODE, username="Jonas")
    zeilen = "\n".join(web.auth_banner(einzeln))
    assert "Jonas" in zeilen and CODE not in zeilen, "steht das Konto, zeigt sich kein Code"
    _mehrere(tmp_path / "zwei")
    zeilen = "\n".join(web.auth_banner(AuthStore(tmp_path / "zwei" / "konten", "PRO123456",
                                                 CODE, single=True)))
    assert "1 weitere Konten" in zeilen
    mehr = "\n".join(web.auth_banner(AuthStore(tmp_path / "drei", "PRO123456", CODE)))
    assert "PRO123456" in mehr and CODE in mehr


def test_accounts_are_off_unless_chosen(monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy import config

    monkeypatch.delenv("AQUATICY_ACCOUNTS", raising=False)
    config.reset_settings_cache()
    assert config.get_settings().accounts is False
    monkeypatch.setenv("AQUATICY_ACCOUNTS", "true")
    config.reset_settings_cache()
    assert config.get_settings().accounts is True
    config.reset_settings_cache()


# -- Einzelkonto und Chat-Art ueber HTTP ----------------------------------------------------------
@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from aquaticy import config
    from aquaticy.aiguard import AiGuard, forget_judgements

    llm, llm_port = fake_llm.starte()
    fake_llm.ANFRAGEN.clear()
    for key, wert in {
        "AQUATICY_MODEL": "openai/fake-modell",
        "AQUATICY_API_BASE": f"http://127.0.0.1:{llm_port}/v1",
        "OPENAI_API_KEY": "sk-fake",
        "AQUATICY_SUBAGENTS_AUTO": "false",
        "AQUATICY_DATA_DIR": str(tmp_path / "daten"),
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    }.items():
        monkeypatch.setenv(key, wert)
    config.reset_settings_cache()
    monkeypatch.setattr(guardrails, "_ask_model", ECHTER_PRUEFER)
    forget_judgements()
    monkeypatch.setattr(web, "AUTH", AuthStore(tmp_path / "konten", "PROE2E234", CODE,
                                               single=True))
    monkeypatch.setattr(web, "AIGUARD", AiGuard(tmp_path / "konten" / "accounts.sqlite3"))
    monkeypatch.setattr(web, "SESSIONS", web.SessionRegistry())
    monkeypatch.setattr(web, "SESSION", web.SessionProxy())
    monkeypatch.setattr(web, "strong_models", lambda *args, **kwargs: [])
    monkeypatch.setattr(web, "AUTH_LIMIT", web.RateLimiter(attempts=100, window_seconds=60))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()
    llm.shutdown()
    config.reset_settings_cache()


def _zustimmung(port: int) -> str:
    _, kopf, _ = _req(port, "POST", "/api/consent", {"accepted": True})
    return kopf["Set-Cookie"].split(";", 1)[0]


def _anlegen(port: int, zustimmung: str, code: str = CODE, name: str = "Jonas") -> Any:
    return _req(port, "POST", "/api/auth/register", {
        "username": name, "password": PASSWORT, "plan": "normal", "pro_code": code}, zustimmung)


def _status(port: int, cookie: str = "") -> dict[str, Any]:
    return json.loads(_req(port, "GET", "/api/auth/status", cookie=cookie)[2])


def test_the_first_visit_creates_the_one_account_with_the_setup_code(server: int) -> None:
    zustimmung = _zustimmung(server)
    stand = _status(server, zustimmung)
    assert stand["single"] is True and stand["setup_needed"] is True
    status, _, daten = _anlegen(server, zustimmung, code="falsch")
    assert status == 400 and "Einrichtungscode" in json.loads(daten)["error"]
    status, kopf, daten = _anlegen(server, zustimmung)
    assert status == 200 and json.loads(daten)["account"]["plan"] == "ultra"
    cookie = zustimmung + "; " + kopf["Set-Cookie"].split(";", 1)[0]
    assert _status(server, cookie)["authenticated"] is True
    assert _status(server, zustimmung)["setup_needed"] is False
    status, _, daten = _anlegen(server, _zustimmung(server), name="Zweiter")
    assert status == 400 and json.loads(daten)["error"] == SINGLE_TAKEN


def test_login_with_username_and_password(server: int) -> None:
    zustimmung = _zustimmung(server)
    assert _anlegen(server, zustimmung)[0] == 200
    status, kopf, _ = _req(server, "POST", "/api/auth/login", wie_die_app({
        "email": "jonas", "password": PASSWORT}), zustimmung, browser=True)
    assert status == 200 and kopf.get("Set-Cookie", "").startswith(web.AUTH_COOKIE + "=")
    status, _, daten = _req(server, "POST", "/api/auth/login", wie_die_app({
        "email": "Jonas", "password": "falsches Passwort"}), zustimmung, browser=True)
    assert status == 401 and json.loads(daten)["error"] == web.WRONG_LOGIN_SINGLE


def test_code_chats_and_chats_live_in_their_own_lists(server: int) -> None:
    zustimmung = _zustimmung(server)
    status, kopf, _ = _anlegen(server, zustimmung)
    cookie = zustimmung + "; " + kopf["Set-Cookie"].split(";", 1)[0]
    status, ereignisse = _chat(server, cookie, "Bau mir ein kleines Skript", mode="code")
    assert status == 200 and ereignisse[-1]["type"] == "done", ereignisse
    code = json.loads(_req(server, "GET", "/api/chats?kind=code", cookie=cookie)[2])["chats"]
    normal = json.loads(_req(server, "GET", "/api/chats?kind=chat", cookie=cookie)[2])["chats"]
    assert [c["kind"] for c in code] == ["code"] and normal == []
    code_chat = code[0]["session_id"]
    status, _, daten = _req(server, "POST", "/api/chat",
                            {"message": "Jetzt normal weiter", "mode": "normal"}, cookie)
    assert status == 409 and json.loads(daten)["code"] == "chat_kind"
    assert "Code-Chat" in json.loads(daten)["error"]
    assert _req(server, "POST", "/api/clear", {}, cookie)[0] == 200
    status, _ = _chat(server, cookie, "Was ist eine Primzahl?", mode="pro")
    assert status == 200
    normal = json.loads(_req(server, "GET", "/api/chats?kind=chat", cookie=cookie)[2])["chats"]
    assert [(c["kind"], c["mode"]) for c in normal] == [("chat", "pro")]
    status, _, daten = _req(server, "POST", "/api/open", {"session_id": code_chat}, cookie)
    geoeffnet = json.loads(daten)
    assert status == 200 and geoeffnet["kind"] == "code" and geoeffnet["mode"] == "code"


# -- Setup und Befehl -----------------------------------------------------------------------------
def test_setup_writes_accounts_off_by_default(monkeypatch: pytest.MonkeyPatch,
                                              tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "_ensure_ollama", lambda **kw: True)
    monkeypatch.setattr(cli, "_ask_website", lambda **kw: {})
    monkeypatch.setattr(cli, "_vm_beim_start", lambda settings: None)
    monkeypatch.setattr(cli, "_messenger_beim_start", lambda settings: None)
    eingerichtet: list[Any] = []
    monkeypatch.setattr(cli, "_einzelkonto_einrichten", eingerichtet.append)
    ziel = tmp_path / ".env"
    ergebnis = CliRunner().invoke(cli.app, ["setup", "--yes", "--no-probe", "--env-file",
                                            str(ziel)], input="1\n1\n\n\n\n\n")
    assert ergebnis.exit_code == 0, ergebnis.output
    assert "AQUATICY_ACCOUNTS=false" in ziel.read_text() and len(eingerichtet) == 1
    ergebnis = CliRunner().invoke(cli.app, ["setup", "--yes", "--no-probe", "--accounts",
                                            "--env-file", str(ziel)], input="1\n1\n\n\n\n\n")
    assert "AQUATICY_ACCOUNTS=true" in ziel.read_text() and len(eingerichtet) == 1


def test_the_account_command_creates_and_resets_the_one_account(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aquaticy import config

    monkeypatch.setenv("AQUATICY_DATA_DIR", str(tmp_path / "daten"))
    monkeypatch.delenv("AQUATICY_ACCOUNTS", raising=False)
    config.reset_settings_cache()
    ergebnis = CliRunner().invoke(cli.app, ["account"],
                                  input=f"Jonas\n{PASSWORT}\n{PASSWORT}\n")
    assert ergebnis.exit_code == 0, ergebnis.output
    store = AuthStore(tmp_path / "daten", "PRO123456", single=True)
    assert store.owner().username == "Jonas" and store.owner().ultra
    ergebnis = CliRunner().invoke(cli.app, ["account"],
                                  input="\nein neues langes Passwort\nein neues langes Passwort\n")
    assert ergebnis.exit_code == 0, ergebnis.output
    assert store.login("Jonas", "ein neues langes Passwort") is not None
    monkeypatch.setenv("AQUATICY_ACCOUNTS", "true")
    config.reset_settings_cache()
    assert CliRunner().invoke(cli.app, ["account"]).exit_code == 1
    config.reset_settings_cache()


def test_a_bad_password_is_asked_again_and_gives_up_after_three(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aquaticy import config

    monkeypatch.setenv("AQUATICY_DATA_DIR", str(tmp_path / "daten"))
    monkeypatch.delenv("AQUATICY_ACCOUNTS", raising=False)
    config.reset_settings_cache()
    ergebnis = CliRunner().invoke(cli.app, ["account"], input="Jonas\nkurz\nkurz\n" * 3)
    assert ergebnis.exit_code == 1 and "12 Zeichen" in ergebnis.output
    config.reset_settings_cache()


def test_without_a_terminal_setup_only_points_to_the_command(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    cli._einzelkonto_einrichten(SimpleNamespace(data_dir=tmp_path / "daten"))
    assert "aquaticy account" in capsys.readouterr().out
    AuthStore(tmp_path / "daten", "PRO123456", single=True).reset_owner("Jonas", PASSWORT)
    cli._einzelkonto_einrichten(SimpleNamespace(data_dir=tmp_path / "daten"))
    assert "Jonas" in capsys.readouterr().out


def test_the_login_page_knows_the_single_account() -> None:
    html = (ROOT / "aquaticy" / "webui.html").read_text(encoding="utf-8")
    for teil in ("einzelKonto = state.single === true;",
                 "kontoEinrichten = state.setup_needed === true;",
                 "function einzelKontoZeigen(registering)", 'id="email-row"',
                 '$("#pro-code-label").textContent = "Einrichtungscode";'):
        assert teil in html, teil


# -- Der Besitzer ist fest gemerkt -------------------------------------------------------------
def test_deleting_the_one_account_never_promotes_an_old_one(tmp_path: Path) -> None:
    _, normal, ultra = _mehrere(tmp_path)
    einzeln = AuthStore(tmp_path / "konten", "PRO123456", CODE, single=True)
    assert einzeln.owner().id == ultra.id
    einzeln.remove_account(einzeln.login("Bernd", PASSWORT))
    assert einzeln.owner() is None, "Anna rueckt nicht nach"
    assert einzeln.ensure_owner_ultra() is None
    assert einzeln.login("Anna", PASSWORT) is None
    assert AuthStore(tmp_path / "konten", "PRO123456", CODE, single=True).owner() is None, \
        "auch nach einem Neustart nicht"
    with pytest.raises(ValueError, match="Einrichtungscode"):
        einzeln.register("", PASSWORT, "ultra", "falsch", username="Neu")
    neu = einzeln.register("", PASSWORT, "ultra", CODE, username="Neu")
    assert einzeln.owner().id == neu.id and neu.id != normal.id


def test_the_command_line_picks_another_old_account(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from aquaticy import config

    _mehrere(tmp_path)
    monkeypatch.setenv("AQUATICY_DATA_DIR", str(tmp_path / "konten"))
    monkeypatch.delenv("AQUATICY_ACCOUNTS", raising=False)
    config.reset_settings_cache()
    ergebnis = CliRunner().invoke(cli.app, ["account", "--use", "Anna"])
    assert ergebnis.exit_code == 0, ergebnis.output
    einzeln = AuthStore(tmp_path / "konten", "PRO123456", CODE, single=True)
    assert einzeln.owner().username == "Anna" and einzeln.owner().ultra
    assert einzeln.login("Bernd", PASSWORT) is None and einzeln.login("Anna", PASSWORT)
    assert CliRunner().invoke(cli.app, ["account", "--use", "Niemand"]).exit_code == 1
    config.reset_settings_cache()


def test_the_choice_is_made_once_and_kept(tmp_path: Path) -> None:
    mehr, _, ultra = _mehrere(tmp_path)
    einzeln = AuthStore(tmp_path / "konten", "PRO123456", CODE, single=True)
    assert einzeln.owner().id == ultra.id
    spaeter = mehr.register("z@example.org", PASSWORT, "ultra", CODE, username="Zora",
                            terms_accepted=True, terms_version="1")
    assert einzeln.owner().id == ultra.id != spaeter.id


# -- Im echten Browser -------------------------------------------------------------------------
def _warte(bedingung, sekunden: float = 30) -> None:
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        if bedingung():
            return
        time.sleep(0.2)
    raise AssertionError("Bedingung nicht erfuellt")


def test_the_single_account_and_the_chat_lists_in_a_real_browser(server: int) -> None:
    sync = pytest.importorskip("playwright.sync_api")
    import shutil

    chromium = shutil.which("chromium") or (
        "/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)
    if chromium is None:
        pytest.skip("kein Chromium")
    with sync.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chromium)
        page = browser.new_page(viewport={"width": 1280, "height": 860})
        fehler: list[str] = []
        page.on("pageerror", lambda e: fehler.append(str(e)))
        page.goto(f"http://127.0.0.1:{server}/")
        page.click("#consent-yes")
        page.wait_for_selector("#login-card:not([hidden])")
        assert page.is_hidden("#auth-tabs") and page.is_hidden("#plan-choice")
        assert page.is_hidden("#email-row") and page.is_visible("#pro-code-row")
        assert page.inner_text("#pro-code-label") == "Einrichtungscode"
        assert page.is_hidden("#terms-row"), "keine Bedingungen fuer das eigene Konto"
        page.fill("#auth-username", "Jonas")
        page.fill("#auth-password", PASSWORT)
        page.fill("#auth-pro-code", "falsch")
        page.click("#auth-submit")
        _warte(lambda: page.inner_text("#auth-error").strip() != "")
        assert "Einrichtungscode" in page.inner_text("#auth-error")
        page.fill("#auth-pro-code", CODE)
        page.click("#auth-submit")
        page.wait_for_selector("#auth-gate", state="hidden", timeout=20000)
        assert page.inner_text("#side-title").lower() == "letzte chats"

        page.fill("#input", "Was ist eine Primzahl?")
        page.keyboard.press("Enter")
        page.wait_for_selector(".recent", timeout=60000)
        time.sleep(1.5)
        page.wait_for_selector(".recent .art", timeout=20000)
        assert page.inner_text(".recent .art") == "Normal"
        nachrichten = page.locator(".msg").count()

        page.click('#modes .mode[data-mode="pro"]')
        time.sleep(0.5)
        assert page.locator(".msg").count() == nachrichten, "Normal zu Pro bleibt im Chat"

        page.click('#modes .mode[data-mode="code"]')
        _warte(lambda: page.inner_text("#side-title").strip().lower() == "code-chats")
        time.sleep(1)
        assert page.locator(".msg").count() == 0, "Code beginnt einen neuen Chat"
        assert page.locator(".recent").count() == 0, "keine Code-Chats bisher"
        assert page.inner_text("#btn-new-label") == "Neuer Code-Chat"
        page.fill("#input", "Bau mir ein kleines Skript")
        page.keyboard.press("Enter")
        page.wait_for_selector(".recent", timeout=60000)
        time.sleep(3)
        assert page.locator(".recent .art").count() == 0, "Code-Chats ohne Schild"

        page.click('#modes .mode[data-mode="normal"]')
        _warte(lambda: page.inner_text("#side-title").strip().lower() == "letzte chats")
        time.sleep(1.5)
        titel = page.locator(".recent .name").all_inner_texts()
        assert any("Primzahl" in t for t in titel) and not any("Skript" in t for t in titel)
        assert fehler == [], fehler
        # Abmelden und wieder anmelden: nur Nutzername und Passwort
        page.context.clear_cookies()
        page.goto(f"http://127.0.0.1:{server}/")
        page.click("#consent-yes")
        page.wait_for_selector("#login-card:not([hidden])")
        assert page.is_hidden("#auth-tabs") and page.is_hidden("#username-row")
        assert page.is_hidden("#pro-code-row") and page.is_hidden("#terms-row")
        assert page.inner_text("#email-label") == "Nutzername"
        page.fill("#auth-email", "Jonas")
        page.fill("#auth-password", PASSWORT)
        page.click("#auth-submit")
        # Ein gesteuerter Browser (navigator.webdriver) bekommt vom Anmeldeschutz den Regler --
        # das ist richtig. Entscheidend: kein "Nutzername oder Passwort stimmt nicht".
        _warte(lambda: page.is_visible("#human-check") or page.is_hidden("#auth-gate"))
        assert "stimmt nicht" not in page.inner_text("#auth-error")
        browser.close()
