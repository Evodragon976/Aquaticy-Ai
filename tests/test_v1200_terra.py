"""12.0.0 Terra: Anmeldeschutz gegen Bots -- drei Hinweise, eine Risikozahl.

Fingerabdruck (passt zur App / wie ein Skript), Fehlversuche dieses Clients
(Adresse, Geraete-Kennung) und ob das Geraet schon bekannt ist ergeben eine Zahl:
unter 34 durch, 34 bis 66 "Bestaetige, dass du ein Mensch bist", ab 67
abgewiesen -- vor dem Passwort. Siehe aquaticy/botguard.py.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Any

import pytest

from aquaticy import botguard, web
from tests.anmeldung import AGENT, BROWSER, FETCH, SPRACHE, loese, mensch, wie_die_app
from tests.test_security import _anfrage, server  # noqa: F401

PASSWORT = "ein langes Passwort"
SKRIPT = {"User-Agent": "python-requests/2.32", "Accept": "*/*"}


def _ui() -> str:
    return web.UI_FILE.read_text(encoding="utf-8")



def test_the_three_examples_give_six_fifty_and_ninety_nine() -> None:

    assert botguard.score(False, 0, False) == 6
    assert botguard.verdict(6) == botguard.THROUGH

    assert botguard.score(False, 6, True) == 50
    assert botguard.verdict(50) == botguard.CHALLENGE

    assert botguard.score(True, 40, True) == 99
    assert botguard.verdict(99) == botguard.DROPPED


def test_a_browser_is_never_dropped_only_asked() -> None:
    for fehl in range(0, 200, 7):
        for neu in (False, True):
            assert botguard.verdict(botguard.score(False, fehl, neu)) != botguard.DROPPED
    assert botguard.score(False, 10_000, True) == 59
    assert botguard.verdict(33) == botguard.THROUGH
    assert botguard.verdict(34) == botguard.CHALLENGE
    assert botguard.verdict(66) == botguard.CHALLENGE
    assert botguard.verdict(67) == botguard.DROPPED


    assert botguard.verdict(botguard.score(True, 0, True)) == botguard.CHALLENGE
    assert botguard.verdict(botguard.score(True, 1, True)) == botguard.DROPPED



def test_the_fingerprint_sees_scripts_and_lets_the_app_through() -> None:
    assert botguard.fingerprint(BROWSER, True, False, True) == []
    for agent in ("curl/8.5.0", "python-requests/2.32", "Go-http-client/1.1", "",
                  "Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/130.0.0.0 Safari/537.36",
                  "Mozilla/5.0 (compatible; Googlebot/2.1)"):
        assert "user-agent" in botguard.fingerprint({**BROWSER, "User-Agent": agent},
                                                    True, False, True), agent
    ohne_fetch = {"User-Agent": AGENT, "Accept-Language": SPRACHE}
    assert botguard.fingerprint(ohne_fetch, True, False, True) == ["fetch"]

    assert botguard.fingerprint(ohne_fetch, True, False, False) == []
    fremd = {**BROWSER, "Sec-Fetch-Site": "cross-site"}
    assert botguard.fingerprint(fremd, True, False, True) == ["fetch"]

    webkit = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/605.1.15 "
                            "(KHTML, like Gecko) Version/16.0 Safari/605.1.15",
              "Accept-Language": SPRACHE}
    assert botguard.fingerprint(webkit, True, False, True) == []
    assert botguard.fingerprint({**BROWSER, "Accept-Language": ""}, True, False, True) == [
        "sprache"]
    assert botguard.fingerprint(BROWSER, False, False, True) == ["nachweis"]
    assert botguard.fingerprint(BROWSER, True, True, True) == ["webdriver"]



def test_a_proof_is_signed_fresh_and_single_use() -> None:
    aufgabe = botguard.issue("visit")
    assert aufgabe["bits"] == botguard.VISIT_BITS and len(aufgabe["seed"]) == 32
    beweis = loese(aufgabe)
    assert botguard.check(beweis, ("visit",))
    assert not botguard.check(beweis, ("visit",)), "einmal"

    zweite = loese(botguard.issue("visit"))
    assert not botguard.check(zweite, ("human",))
    falsch = botguard.issue("visit")
    nonce = next(str(z) for z in range(10**6)
                 if not botguard.solves(falsch["seed"], str(z), falsch["bits"]))
    assert not botguard.check({"token": falsch["token"], "nonce": nonce}, ("visit",))
    roh, _, signatur = zweite["token"].partition(".")
    daten = json.loads(botguard._unb64(roh))
    daten["d"] = 1
    geaendert = botguard._b64(json.dumps(daten, separators=(",", ":")).encode())
    assert not botguard.check({"token": f"{geaendert}.{signatur}", "nonce": "0"}, ("visit",))
    for kaputt in (None, "x", {"token": 5, "nonce": "1"}, {"token": "a.b", "nonce": "-1"},
                   {"token": "a" * 500, "nonce": "1"}, {"token": "e30.x", "nonce": "1"}):
        assert not botguard.check(kaputt, ("visit", "human"))


def test_an_old_proof_no_longer_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    jetzt = time.time()
    beweis = loese(botguard.issue("visit"))
    menschlich = loese(botguard.issue("human"))
    monkeypatch.setattr(botguard.time, "time", lambda: jetzt + botguard.VISIT_TTL + 1)
    assert not botguard.check(beweis, ("visit",))
    assert botguard.zero_bits(b"\x00\x00\x7f") == 17
    monkeypatch.setattr(botguard.time, "time", lambda: jetzt + botguard.HUMAN_TTL + 1)
    assert not botguard.check(menschlich, ("human",)), "der Regler gilt fuenf Minuten"
    monkeypatch.setattr(botguard.time, "time", lambda: jetzt + 10)
    assert botguard.check(menschlich, ("human",))



def test_the_slider_wants_a_human_movement() -> None:
    gut = mensch(botguard.issue("human"))["track"]
    assert botguard.human_track(gut)
    gleichmaessig = [[i * 50, i / 10] for i in range(11)]
    assert not botguard.human_track(gleichmaessig), "ein Lineal, kein Mensch"
    assert not botguard.human_track([[0, 0], [5, 1]]), "ein Ruck ans Ende"
    assert not botguard.human_track(gut[:-2]), "nicht am Ende"
    assert not botguard.human_track([[t / 10, s] for t, s in gut]), "zu schnell"
    rueckwaerts = [list(p) for p in gut]
    rueckwaerts[3][0] = 10
    assert not botguard.human_track(rueckwaerts), "die Zeit laeuft vorwaerts"
    for kaputt in (None, "x", [], [[0, "a"]] * 8, [[float("nan"), 0]] * 8, [[0, 0]] * 500,
                   [[True, 0]] * 8):
        assert not botguard.human_track(kaputt)



def test_failures_and_bans_are_kept_per_key(monkeypatch: pytest.MonkeyPatch) -> None:
    uhr = [1000.0]
    monkeypatch.setattr(botguard.time, "monotonic", lambda: uhr[0])
    fehl = botguard.Failures(window=60, max_keys=3)
    for _ in range(5):
        fehl.add("ip:a", "dev:x")
    fehl.add("ip:b")
    assert fehl.count("ip:a") == 5 and fehl.count("ip:b", "dev:x") == 5
    assert fehl.count("ip:c") == 0 and fehl.count() == 0
    uhr[0] += 61
    assert fehl.count("ip:a", "dev:x") == 0, "nach dem Fenster vergessen"
    fehl.add("ip:1", "ip:2", "ip:3", "ip:4")
    assert len(fehl._events) == 3, "begrenzt"
    sperre = botguard.Bans()
    sperre.ban("ip:a", seconds=900)
    assert sperre.remaining("ip:a") == 900 and sperre.remaining("ip:b") == 0
    uhr[0] += 901
    assert sperre.remaining("ip:a") == 0


def test_ipv6_is_counted_per_network() -> None:
    assert botguard.address_key("203.0.113.7") == "203.0.113.7"
    assert botguard.address_key("2001:db8:1:2:aaaa::1") == "2001:db8:1:2::/64"
    assert botguard.address_key("2001:db8:1:2:ffff::9") == "2001:db8:1:2::/64"
    assert botguard.address_key("2001:db8:1:3::1") != botguard.address_key("2001:db8:1:2::1")
    assert botguard.address_key("::ffff:198.51.100.4") == "198.51.100.4"
    assert botguard.address_key("unbekannt") == "unbekannt"



def _zustimmung(port: int) -> str:
    _, kopf, _ = _anfrage(port, "POST", "/api/consent", {"accepted": True})
    return kopf["Set-Cookie"].split(";", 1)[0]


def _post(port: int, body: dict[str, Any], kopf: dict[str, str],
          cookie: str) -> tuple[int, list[tuple[str, str]], dict[str, Any]]:
    from http.client import HTTPConnection

    conn = HTTPConnection("127.0.0.1", port, timeout=20)
    conn.request("POST", "/api/auth/login", body=json.dumps(body),
                 headers={"Content-Type": "application/json", "Cookie": cookie, **kopf})
    antwort = conn.getresponse()
    roh = antwort.read()
    conn.close()
    return antwort.status, antwort.getheaders(), json.loads(roh) if roh else {}


@pytest.fixture
def konto(server: int, monkeypatch: pytest.MonkeyPatch) -> tuple[int, str, list[str]]:  # noqa: F811
    cookie = _zustimmung(server)
    status, _, daten = _anfrage(server, "POST", "/api/auth/register", {
        "email": "terra@example.org", "username": "Terra", "password": PASSWORT,
        "plan": "normal", "terms_accepted": True}, cookie)
    assert status == 200, daten

    gehasht: list[str] = []
    echt = web.AUTH.authenticate

    def authenticate(email: str, password: str) -> Any:
        gehasht.append(email)
        return echt(email, password)

    monkeypatch.setattr(web.AUTH, "authenticate", authenticate)
    return server, cookie, gehasht


def test_the_app_logs_in_without_noticing_anything(konto) -> None:
    port, cookie, gehasht = konto
    status, _, daten = _post(port, wie_die_app({"email": "terra@example.org",
                                                "password": PASSWORT}), BROWSER, cookie)
    assert status == 200 and daten["ok"], daten
    assert gehasht == ["terra@example.org"]

    status, _, aufgabe = _anfrage(port, "GET", "/api/auth/challenge")
    assert status == 200 and set(aufgabe) == {"token", "seed", "bits"}
    assert aufgabe["bits"] == botguard.VISIT_BITS
    assert botguard.check(loese(aufgabe), ("visit",))


def test_a_script_is_asked_before_the_password_and_then_dropped(konto) -> None:
    port, cookie, gehasht = konto
    body = {"email": "terra@example.org", "password": PASSWORT}

    status, _, daten = _post(port, body, SKRIPT, cookie)
    assert status == 428 and daten["challenge"]["bits"] == botguard.HUMAN_BITS, daten
    assert "Mensch" in daten["error"] and gehasht == []

    falsch = {**body, "password": "falsch", "human": mensch(daten["challenge"])}
    status, _, _ = _post(port, falsch, SKRIPT, cookie)
    assert status == 401 and gehasht == ["terra@example.org"]

    status, kopf, daten = _post(port, body, SKRIPT, cookie)
    assert status == 429 and daten["code"] == "dropped", daten
    assert dict(kopf)["Retry-After"] == str(botguard.BAN_SECONDS)
    assert "15 Minuten" in daten["error"] and len(gehasht) == 1

    status, _, aufgabe = _anfrage(port, "GET", "/api/auth/challenge")
    nochmal = {**body, "proof": loese(aufgabe),
               "human": mensch(botguard.issue("human"))}
    status, _, daten = _post(port, nochmal, SKRIPT, cookie)
    assert status == 429 and len(gehasht) == 1


    status, _, daten = _post(port, wie_die_app(body), BROWSER, cookie)
    assert status == 428, daten
    status, _, daten = _post(port, {**body, "human": mensch(daten["challenge"])}, BROWSER,
                             cookie)
    assert status == 200 and daten["ok"], daten


def test_many_failures_ask_a_browser_to_slide(konto) -> None:
    port, cookie, gehasht = konto
    body = {"email": "terra@example.org", "password": PASSWORT}
    status, _, _ = _post(port, wie_die_app({**body, "password": "falsch"}), BROWSER, cookie)
    assert status == 401 and web.BOT_FAILS.count("ip:127.0.0.1") == 1

    status, _, _ = _post(port, wie_die_app({**body, "password": "falsch"}), BROWSER, cookie)
    assert status == 401 and len(gehasht) == 2
    for _ in range(4):
        web.BOT_FAILS.add("ip:127.0.0.1")

    status, _, daten = _post(port, wie_die_app(body), BROWSER, cookie)
    assert status == 428 and len(gehasht) == 2

    ruck = {**loese(daten["challenge"]), "track": [[0, 0], [10, 1]]}
    status, _, nochmal = _post(port, wie_die_app({**body, "human": ruck}), BROWSER, cookie)
    assert status == 428 and len(gehasht) == 2

    beweis = mensch(nochmal["challenge"])
    status, _, daten = _post(port, {**body, "human": beweis}, BROWSER, cookie)
    assert status == 200 and daten["ok"], daten


    status, _, _ = _post(port, {**body, "human": beweis}, BROWSER, cookie)
    assert status == 429 and len(gehasht) == 3


def test_a_proof_used_once_does_not_count_again(konto) -> None:
    port, cookie, _ = konto
    beweis = wie_die_app({"email": "terra@example.org", "password": PASSWORT})
    assert _post(port, beweis, BROWSER, cookie)[0] == 200

    assert _post(port, beweis, BROWSER, cookie)[0] == 428


def test_a_remote_controlled_browser_counts_as_script(konto) -> None:
    port, cookie, _ = konto
    body = {**wie_die_app({"email": "terra@example.org", "password": PASSWORT}),
            "webdriver": True}
    assert _post(port, body, BROWSER, cookie)[0] == 428


def test_a_known_device_counts_only_by_its_cookie(konto) -> None:
    from aquaticy.devices import DEVICE_COOKIE, clean_device

    port, cookie, _ = konto
    status, kopf, _ = _post(port, wie_die_app({"email": "terra@example.org",
                                               "password": PASSWORT}), BROWSER, cookie)
    assert status == 200
    kekse = [wert.split(";", 1)[0] for name, wert in kopf if name.lower() == "set-cookie"]
    kennung = next(k.split("=", 1)[1] for k in kekse if k.startswith(DEVICE_COOKIE + "="))
    bekannt = clean_device({"platform": "Linux"}, user_agent=AGENT, accept_language=SPRACHE,
                           cookie=kennung)
    assert web.AUTH.seen_device_for_login("Terra@Example.org", bekannt)

    fremd = clean_device({"platform": "Linux"}, user_agent=AGENT, accept_language=SPRACHE,
                         cookie="")
    assert not web.AUTH.seen_device_for_login("terra@example.org", fremd)
    assert not web.AUTH.seen_device_for_login("niemand@example.org", bekannt)
    assert not web.AUTH.seen_device_for_login("kaputt", bekannt)

    mit = f"{cookie}; {DEVICE_COOKIE}={kennung}"
    body = {"email": "terra@example.org", "password": PASSWORT}
    for _ in range(6):
        assert _post(port, wie_die_app({**body, "password": "x"}), BROWSER, mit)[0] == 401
    assert _post(port, wie_die_app(body), BROWSER, mit)[0] == 200


def test_registering_is_not_asked(server: int) -> None:  # noqa: F811
    cookie = _zustimmung(server)
    status, _, daten = _anfrage(server, "POST", "/api/auth/register", {
        "email": "neu@example.org", "username": "Neu", "password": PASSWORT,
        "plan": "normal", "terms_accepted": True}, cookie)
    assert status == 200, daten



def test_the_page_solves_in_the_background_and_shows_the_slider() -> None:
    html = _ui()
    skript = html[html.index("const SHA_K = new Uint32Array(["):]
    skript = skript[: skript.index('$("#auth-form").addEventListener("submit"')]
    assert 'api("/api/auth/challenge", {quietErrors:true})' in skript
    assert "Math.clz32(sha256Kopf(vorn + zahl)) >= bits" in skript
    assert "setTimeout(happen, 0)" in skript, "in Happen, die Seite haengt nicht"
    boot = html[html.index("async function bootAuth(){"):]
    boot = boot[: boot.index("bootAuth();")]
    assert "neuerBesuchsNachweis();" in boot, "schon beim Besuch"
    absenden = html[html.index('$("#auth-form").addEventListener("submit"'):]
    absenden = absenden[: absenden.index("async function bootAuth(){")]
    assert "body.proof = await frischerBesuchsNachweis();" in absenden
    assert "body.webdriver = navigator.webdriver === true;" in absenden
    assert "res.status === 428 && data.challenge" in absenden
    assert 'data.code === "dropped"' in absenden
    formular = html[html.index('<form id="auth-form">'):html.index("</form>")]
    assert '<input type="range" id="human-slider"' in formular
    assert "Bestätige kurz, dass du ein Mensch bist" in formular


def test_the_javascript_hash_matches_python() -> None:
    import hashlib

    node = shutil.which("node")
    if not node:
        pytest.skip("node fehlt")
    html = _ui()
    teil = html[html.index("const SHA_K"):html.index("let besuchsNachweis")]
    texte = ["", "abc", "0123456789abcdef0123456789abcdef:123", "x" * 55, "y" * 56, "z" * 130]
    js = teil + (f"console.log(JSON.stringify({json.dumps(texte)}.map(t => "
                 "sha256Kopf(t).toString(16).padStart(8, '0'))));")
    aus = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30,
                         check=True).stdout
    assert json.loads(aus) == [hashlib.sha256(t.encode()).hexdigest()[:8] for t in texte]


def test_the_login_route_stays_on_this_server_and_needs_no_session() -> None:
    assert "/api/auth/challenge" in web.CLUSTER_LOCAL
    quelle = web.Path(web.__file__).read_text(encoding="utf-8")
    assert quelle.index("if not self._bot_gate(payload, geraet, neue_kennung):") \
        < quelle.index("account = AUTH.authenticate("), "vor dem Passwort"
    assert FETCH == {"Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "cors"}
