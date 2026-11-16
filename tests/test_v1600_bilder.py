"""16.0.0: Webcam- und Satellitensuche -- welches Bild aus einer Seite genommen wird."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from aquaticy.fetch import Fetcher
from tests.test_fetch import _fetcher

SEITE = "https://stadt.example/webcam"


def lade(html: str, bilder: dict[str, tuple[int, bytes]] | None = None,
         monkeypatch: pytest.MonkeyPatch | None = None) -> tuple[Fetcher, list[str]]:
    """Ein Fetcher, dessen Seite *html* liefert. *bilder*: Pfad -> (Status, Inhalt)."""
    bilder = bilder or {}
    abgerufen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/webcam":
            return httpx.Response(200, text=html, headers={"content-type": "text/html"})
        abgerufen.append(request.url.path)
        status, inhalt = bilder.get(request.url.path, (404, b""))
        return httpx.Response(status, content=inhalt, headers={"content-type": "image/jpeg"})

    fetcher = _fetcher(handler, respect_robots=False)
    return fetcher, abgerufen


@pytest.fixture(autouse=True)
def _oeffentlich(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aquaticy.fetch.public_web_url", lambda url: True)


def hole(html: str, bilder: dict[str, tuple[int, bytes]]) -> tuple[str, list[str]]:
    fetcher, abgerufen = lade(html, bilder)
    with fetcher:
        visual, fehler = fetcher.load_public_visual(SEITE)
    assert visual is not None, fehler
    return visual.url, abgerufen


def test_the_camera_picture_beats_the_share_preview() -> None:
    """og:image ist oft das Vorschaubild der Seite fuer Netzwerke, nicht die Kamera."""
    html = ('<meta property="og:image" content="/img/teilen.jpg">'
            '<img class="webcam-bild" src="/cam/aktuell.jpg">')
    url, _ = hole(html, {"/img/teilen.jpg": (200, b"teilen"), "/cam/aktuell.jpg": (200, b"cam")})
    assert url.endswith("/cam/aktuell.jpg")


def test_the_next_candidate_is_tried_when_the_first_one_fails() -> None:
    html = ('<img class="webcam" src="/cam/tot.jpg"><img alt="Livebild" src="/cam/geht.jpg">')
    url, abgerufen = hole(html, {"/cam/geht.jpg": (200, b"ok")})
    assert url.endswith("/cam/geht.jpg") and abgerufen[0] == "/cam/tot.jpg"


def test_icons_banners_and_tiny_images_are_not_the_camera() -> None:
    html = ('<img src="/icons/sprite.png"><img src="/ads/banner.jpg">'
            '<img src="/user/avatar.jpg"><img src="/x.gif" width="1" height="1">'
            '<img src="/hafen/ansicht.jpg" width="640" height="480">')
    ok = (200, b"x")
    url, abgerufen = hole(html, {p: ok for p in
                                 ("/icons/sprite.png", "/ads/banner.jpg", "/user/avatar.jpg",
                                  "/x.gif", "/hafen/ansicht.jpg")})
    assert url.endswith("/hafen/ansicht.jpg") and abgerufen == ["/hafen/ansicht.jpg"]


def test_a_video_poster_counts_when_there_is_nothing_better() -> None:
    url, _ = hole('<video poster="/cam/poster.jpg" src="/s.m3u8"></video>',
                  {"/cam/poster.jpg": (200, b"poster")})
    assert url.endswith("/cam/poster.jpg")


def test_lazy_loaded_pictures_are_found() -> None:
    html = ('<img class="livecam" data-lazy-src="/cam/lazy.jpg">'
            '<img class="x" srcset="/cam/klein.jpg 320w, /cam/gross.jpg 1280w">')
    url, _ = hole(html, {"/cam/lazy.jpg": (200, b"lazy"), "/cam/gross.jpg": (200, b"gross")})
    assert url.endswith("/cam/lazy.jpg")
    url, _ = hole('<img srcset="/cam/klein.jpg 320w, /cam/gross.jpg 1280w">',
                  {"/cam/klein.jpg": (200, b"k"), "/cam/gross.jpg": (200, b"g")})
    assert url.endswith("/cam/gross.jpg"), "bei srcset zaehlt das groesste Bild"


@pytest.mark.parametrize("hinweis", ["kamera", "livebild", "wetterkamera", "panorama", "webcam"])
def test_german_camera_words_make_a_picture_the_first_choice(hinweis: str) -> None:
    html = f'<img src="/a/zufall.jpg"><img alt="{hinweis} Hafen" src="/b/echt.jpg">'
    ok = (200, b"x")
    url, abgerufen = hole(html, {"/a/zufall.jpg": ok, "/b/echt.jpg": ok})
    assert url.endswith("/b/echt.jpg") and abgerufen[0] == "/b/echt.jpg"


@pytest.mark.parametrize("zufall", ["alive", "scam", "deliver", "campaign", "cambridge"])
def test_words_that_only_contain_cam_or_live_are_no_hint(zufall: str) -> None:
    html = f'<img class="{zufall}" src="/a/{zufall}.jpg"><img class="webcam" src="/b/echt.jpg">'
    ok = (200, b"x")
    url, abgerufen = hole(html, {f"/a/{zufall}.jpg": ok, "/b/echt.jpg": ok})
    assert url.endswith("/b/echt.jpg") and abgerufen[0] == "/b/echt.jpg"


def test_nothing_usable_gives_a_clear_error() -> None:
    fetcher, _ = lade('<img class="webcam" src="/cam/tot.jpg">', {})
    with fetcher:
        visual, fehler = fetcher.load_public_visual(SEITE)
    assert visual is None and fehler


def test_candidates_are_ordered_by_what_looks_like_a_camera() -> None:
    from aquaticy.fetch import visual_score

    adressen = ["https://example.org/artikel/stadtgeschichte",
                "https://stadt.example/webcam/altstadt-live",
                "https://worldview.earthdata.nasa.gov/?v=1",
                "https://shop.example/kamera-kaufen"]
    bewertet = sorted(adressen, key=visual_score, reverse=True)
    assert bewertet[0] == "https://stadt.example/webcam/altstadt-live"
    assert bewertet[1] == "https://worldview.earthdata.nasa.gov/?v=1"
    assert bewertet[-1] == "https://example.org/artikel/stadtgeschichte" or bewertet[-2] == (
        "https://example.org/artikel/stadtgeschichte")


def test_the_agent_tries_camera_pages_before_other_sources() -> None:
    from aquaticy.agent import Agent
    from aquaticy.config import STANDARD_MODEL_ID, Settings

    agent = Agent(Settings(model=STANDARD_MODEL_ID, subagents_auto=False,
                           enable_playwright=False), cache=None)
    stats = agent.toolbox.stats
    stats.sources.extend([{"url": "https://zeitung.example/artikel"},
                          {"url": "https://stadt.example/livecam/hafen"}])
    antwort = "Siehe https://blog.example/reise und https://tourismus.example/webcam-altstadt."
    kandidaten = agent._visual_candidates(antwort)
    assert kandidaten[0] == "https://tourismus.example/webcam-altstadt"
    assert kandidaten.index("https://stadt.example/livecam/hafen") < kandidaten.index(
        "https://zeitung.example/artikel")


Handler = Callable[[httpx.Request], httpx.Response]


# -- Pro-Modus: dieselbe Seite in mehreren Schreibweisen ----------------------------------------


def treffer(url: str, titel: str = "T", snippet: str = "s") -> Any:
    from aquaticy.models import SearchResult

    return SearchResult(title=titel, url=url, snippet=snippet, rank=1, source_domain="")


@pytest.mark.parametrize(("a", "b"), [
    ("https://www.example.org/a/", "https://example.org/a"),
    ("http://example.org/a", "https://example.org/a"),
    ("https://example.org/a?utm_source=x&utm_medium=y", "https://example.org/a"),
    ("https://example.org/a#abschnitt", "https://example.org/a"),
    ("https://example.org:443/a?b=2&a=1", "https://example.org/a?a=1&b=2"),
    ("HTTPS://Example.ORG/a?fbclid=123", "https://example.org/a"),
])
def test_the_same_page_has_one_canonical_address(a: str, b: str) -> None:
    from aquaticy.models import canonical_url

    assert canonical_url(a) == canonical_url(b)


@pytest.mark.parametrize(("a", "b"), [
    ("https://example.org/a", "https://example.org/b"),
    ("https://example.org/a?id=1", "https://example.org/a?id=2"),
    ("https://example.org/A", "https://example.org/a"),
    ("https://example.org/a", "https://example.com/a"),
])
def test_different_pages_stay_different(a: str, b: str) -> None:
    from aquaticy.models import canonical_url

    assert canonical_url(a) != canonical_url(b)


def test_fusing_counts_spelling_variants_of_a_page_as_one_vote_each() -> None:
    """Drei Anfragen finden dieselbe Seite -- in drei Schreibweisen. Sie muss vorn stehen und
    nur einmal vorkommen, sonst zaehlt jede Schreibweise nur als eine einzelne Stimme.
    """
    from aquaticy.queries import fuse

    listen = [
        [treffer("https://a.example/x"), treffer("https://www.zeitung.example/artikel/")],
        [treffer("https://b.example/y"), treffer("https://zeitung.example/artikel?utm_source=n")],
        [treffer("https://c.example/z"), treffer("http://zeitung.example/artikel#oben")],
    ]
    fusioniert = fuse(listen, 5)
    adressen = [t.url for t in fusioniert]
    assert len(fusioniert) == 4
    assert "zeitung.example/artikel" in adressen[0]
    assert sum("zeitung.example" in a for a in adressen) == 1


def test_a_search_does_not_list_the_same_page_twice() -> None:
    from aquaticy.search import _dedupe

    roh = [treffer("https://www.example.org/a/"), treffer("https://example.org/a?utm_campaign=x"),
           treffer("https://example.org/b")]
    assert [t.url for t in _dedupe(roh, 10)] == ["https://www.example.org/a/",
                                                  "https://example.org/b"]


def test_keywords_drop_the_full_stop_that_ends_a_sentence() -> None:
    from aquaticy.queries import keywords

    assert keywords("Wo finde ich ein Lastenrad in Bremen.") == "Lastenrad Bremen"
    assert "e.V." in keywords("Der Verein Beispiel e.V. hat Mitglieder")
    assert "3.5" in keywords("Test mit 3.5 Litern Hubraum")
