"""11.1.0: Websites, die faelschlich als unlesbar galten, und die Karte.

Alles ohne Netz. Gepruefte Funde:

* "captcha" irgendwo im HTML (reCAPTCHA im Kontaktformular) machte eine
  ganze Seite zur Bot-Sperre.
* Die Banner-Filter loeschten den ganzen Inhalt, wenn ``<body>`` eine
  Cookie-Klasse trug oder die Seite mit Adobe-Bausteinen ("cmp-...") gebaut war.
* Kurze Aussetzer (DNS, robots.txt, 429, 5xx) blieben 24 Stunden gemerkt.
* Ein IPv6-Weg ins Leere kostete die ganze Wartezeit, bevor IPv4 drankam.
* Overpass meldet Ueberlast mit Status 200 und leerer Liste -- das galt als
  "hier gibt es nichts" und blieb einen Tag gemerkt.
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import httpcore
import httpx
import pytest

from aquaticy import netguard
from aquaticy.config import Settings
from aquaticy.fetch import Fetcher, RobotsPolicy, classify_failure, extract_text
from aquaticy.places import PlacesError, find_places
from aquaticy.tools import FAILED_PAGE_SECONDS, Toolbox, page_cache_seconds

ARTIKEL = " ".join(
    f"Absatz {n}: Die Werkstatt in der Nebenstraße repariert Lastenräder aller Marken "
    "und hat montags bis freitags von neun bis achtzehn Uhr geöffnet." for n in range(30)
)


def _seite(body: str, kopf: str = "", body_attr: str = "") -> str:
    return (f"<!doctype html><html><head><title>Radwerk Nord</title>{kopf}</head>"
            f"<body{body_attr}>{body}</body></html>")


def _fetcher(handler) -> Fetcher:
    fetcher = Fetcher(user_agent="aquaticy-test/0.1", timeout=5, delay_seconds=0,
                      enable_browser=False)
    fetcher._client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    fetcher.robots = RobotsPolicy(fetcher._client, "aquaticy-test/0.1")
    return fetcher


# -- Bot-Sperre ---------------------------------------------------------------------------
def test_a_recaptcha_contact_form_is_not_a_bot_wall() -> None:
    html = _seite(
        f"<main><p>{ARTIKEL}</p><form><div class='g-recaptcha'></div></form></main>",
        kopf=("<script src='https://www.google.com/recaptcha/api.js'></script>"
              "<script src='https://js.datadome.co/tags.js'></script>"),
    )
    text = extract_text(html, "https://radwerk.example/")
    assert classify_failure(html, text) == ""


def test_an_article_about_access_denied_errors_is_readable() -> None:
    html = _seite(f"<main><h1>Was tun bei 'Access denied'?</h1><p>{ARTIKEL}</p></main>")
    assert classify_failure(html, extract_text(html, "https://hilfe.example/")) == ""


def test_a_cloudflare_challenge_is_still_a_bot_wall() -> None:
    html = ("<!doctype html><html><head><title>Just a moment...</title></head><body>"
            "<div id='challenge'><h1>radwerk.example</h1><p>Verifying you are human. This may "
            "take a few seconds.</p></div><script>window._cf_chl_opt={}</script></body></html>")
    assert classify_failure(html, extract_text(html, "https://radwerk.example/")) == \
        "blocked_bot_wall"


def test_a_datadome_block_page_is_a_bot_wall() -> None:
    html = _seite("<iframe src='https://geo.captcha-delivery.com/captcha/?initialCid=x'>"
                  "</iframe>")
    assert classify_failure(html, extract_text(html, "https://shop.example/")) == \
        "blocked_bot_wall"


# -- Banner-Filter ------------------------------------------------------------------------
def test_a_cookie_class_on_body_does_not_wipe_the_page() -> None:
    html = _seite(f"<div class='inhalt'><p>{ARTIKEL}</p></div>"
                  "<div class='cookie-notice'>Wir verwenden Cookies. Alle akzeptieren.</div>",
                  body_attr=" class='home cookies-not-set'")
    text = extract_text(html, "https://radwerk.example/")
    assert "Lastenräder" in text
    assert "Alle akzeptieren" not in text


def test_adobe_component_classes_keep_their_text() -> None:
    bausteine = "".join(
        f"<div class='cmp-container'><div class='cmp-text'><p>Absatz {n}: Die Werkstatt "
        "repariert Lastenräder aller Marken und hat werktags geöffnet.</p></div></div>"
        for n in range(60)
    )
    html = _seite(f"<div class='root responsivegrid'>{bausteine}</div>")
    text = extract_text(html, "https://konzern.example/")
    assert "Lastenräder" in text
    assert len(text) > 1000


def test_a_modal_wrapper_around_everything_is_kept() -> None:
    html = _seite(f"<div class='page modal-host'><main><p>{ARTIKEL}</p></main></div>")
    assert "Lastenräder" in extract_text(html, "https://radwerk.example/")


# -- Aussetzer werden nicht gemerkt -------------------------------------------------------
def test_a_dns_dropout_is_reported_as_such_and_not_cached(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, tmp_path: Path
) -> None:
    from aquaticy.cache import Cache

    versuche = {"n": 0}

    def aufloesen(host: str, port: int | None) -> list[str]:
        versuche["n"] += 1
        if versuche["n"] == 1:
            raise socket.gaierror(-3, "Temporary failure in name resolution")
        return ["93.184.215.14"]

    monkeypatch.setattr(netguard, "resolve", aufloesen)
    monkeypatch.setattr(netguard, "UNRESOLVED_TTL", 0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=_seite(f"<main><p>{ARTIKEL}</p></main>"),
                              headers={"content-type": "text/html"})

    box = Toolbox(settings, cache=Cache(tmp_path / "c.sqlite3"), fetcher=_fetcher(handler))
    erster = box.fetch_page("https://radwerk.example/")
    assert erster["skipped_reason"] == "dns_error"
    assert "DNS" in erster["note"]
    assert box.fetch_page("https://radwerk.example/")["ok"] is True


def test_an_unreachable_robots_txt_is_temporary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(503)
        raise AssertionError("ohne robots.txt wird nichts abgerufen")

    seite = _fetcher(handler).fetch("https://radwerk.example/seite")
    assert seite.skipped_reason == "robots_unavailable"
    assert page_cache_seconds(seite) == 0


def test_a_real_robots_ban_is_still_a_ban() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /")
        raise AssertionError("verboten")

    seite = _fetcher(handler).fetch("https://radwerk.example/seite")
    assert seite.skipped_reason == "robots_disallowed"
    assert page_cache_seconds(seite) == FAILED_PAGE_SECONDS


@pytest.mark.parametrize(("status", "erwartet"), [
    (429, 0), (503, 0), (403, FAILED_PAGE_SECONDS), (404, FAILED_PAGE_SECONDS),
])
def test_failures_are_kept_for_an_hour_at_most(status: int, erwartet: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(status, text="nein")

    seite = _fetcher(handler).fetch("https://radwerk.example/seite")
    assert not seite.ok
    assert page_cache_seconds(seite) == erwartet


def test_a_readable_page_keeps_the_normal_cache_time() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=_seite(f"<main><p>{ARTIKEL}</p></main>"),
                              headers={"content-type": "text/html"})

    seite = _fetcher(handler).fetch("https://radwerk.example/seite")
    assert seite.ok
    assert page_cache_seconds(seite) is None


# -- IPv6 ins Leere -----------------------------------------------------------------------
def test_ipv6_and_ipv4_take_turns() -> None:
    assert netguard.interleave(["2a00::1", "2a00::2", "1.2.3.4"]) == \
        ["2a00::1", "1.2.3.4", "2a00::2"]
    assert netguard.interleave(["1.2.3.4", "5.6.7.8"]) == ["1.2.3.4", "5.6.7.8"]


def test_a_dead_ipv6_path_only_costs_a_short_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(netguard, "resolve",
                        lambda host, port: ["2a00:1450::1", "2a00:1450::2", "93.184.215.14"])
    versuche: list[tuple[str, float | None]] = []

    def verbinden(self: Any, host: str, port: int, timeout: float | None = None,
                  local_address: str | None = None, socket_options: Any = None) -> Any:
        versuche.append((host, timeout))
        if ":" in host:
            raise httpcore.ConnectTimeout("ins Leere")
        return object()

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", verbinden)
    stream = netguard._GuardedBackend().connect_tcp("radwerk.example", 443, timeout=15.0)
    assert stream is not None
    assert [host for host, _ in versuche] == ["2a00:1450::1", "93.184.215.14"]
    assert versuche[0][1] == netguard.ATTEMPT_SECONDS


def test_the_last_address_gets_the_full_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(netguard, "resolve", lambda host, port: ["93.184.215.14"])
    zeiten: list[float | None] = []

    def verbinden(self: Any, host: str, port: int, timeout: float | None = None,
                  local_address: str | None = None, socket_options: Any = None) -> Any:
        zeiten.append(timeout)
        return object()

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", verbinden)
    netguard._GuardedBackend().connect_tcp("radwerk.example", 443, timeout=15.0)
    assert zeiten == [15.0]


# -- Karte --------------------------------------------------------------------------------
@pytest.fixture
def _ohne_takt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aquaticy.places.MIN_INTERVAL", 0.0)


def _karte(monkeypatch: pytest.MonkeyPatch, overpass) -> list[str]:
    gefragt: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "nominatim" in request.url.host:
            return httpx.Response(200, json=[{"lat": "53.07", "lon": "8.80",
                                              "display_name": "Bremen"}])
        gefragt.append(request.url.host)
        return overpass(request)

    def bauen(user_agent: str, timeout: float) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler), timeout=timeout)

    monkeypatch.setattr("aquaticy.places._client", bauen)
    return gefragt


@pytest.mark.usefixtures("_ohne_takt")
def test_an_overloaded_overpass_server_is_not_an_empty_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treffer = {"elements": [{"type": "node", "lat": 53.0, "lon": 8.8,
                             "tags": {"name": "Radladen Meier", "shop": "bicycle"}}]}

    def overpass(request: httpx.Request) -> httpx.Response:
        if request.url.host == "overpass-api.de":
            return httpx.Response(200, json={
                "elements": [],
                "remark": 'runtime error: Query timed out in "query" at line 1 after 11 seconds.',
            })
        return httpx.Response(200, json=treffer)

    gefragt = _karte(monkeypatch, overpass)
    orte, _ = find_places("Fahrrad", "Bremen", "aquaticy-test")
    assert [ort.name for ort in orte] == ["Radladen Meier"]
    assert gefragt[:2] == ["overpass-api.de", "overpass.kumi.systems"]


@pytest.mark.usefixtures("_ohne_takt")
def test_when_every_server_is_overloaded_it_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    _karte(monkeypatch, lambda request: httpx.Response(200, json={
        "elements": [], "remark": "runtime error: Query run out of memory."}))
    with pytest.raises(PlacesError):
        find_places("Fahrrad", "Bremen", "aquaticy-test")


@pytest.mark.usefixtures("_ohne_takt")
def test_an_empty_map_result_is_only_kept_for_an_hour(
    monkeypatch: pytest.MonkeyPatch, settings: Settings,
) -> None:
    _karte(monkeypatch, lambda request: httpx.Response(200, json={"elements": []}))
    gemerkt: list[Any] = []

    class Merker:
        def get(self, key: str) -> None:
            return None

        def set(self, key: str, value: Any, **kwargs: Any) -> None:
            gemerkt.append(kwargs.get("ttl"))

    box = Toolbox(settings, cache=Merker())  # type: ignore[arg-type]
    ergebnis = box.local_places("Fahrrad", "Bremen")
    assert ergebnis["results"] == []
    assert gemerkt == [FAILED_PAGE_SECONDS]
