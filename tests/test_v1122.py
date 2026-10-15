"""11.2.2 Luna: Handy und Tablet -- und ein kleinerer Senden-Knopf.

Die Geometrie (Groesse, Trefferflaeche, Schatten, nichts steht ueber) misst
der Rundgang im echten Browser nach (tools/rundgang.py, Abschnitt 19). Hier
steht, was sich am Seitenquelltext pruefen laesst.
"""

from __future__ import annotations

import re

from aquaticy import web


def _ui() -> str:
    return web.UI_FILE.read_text(encoding="utf-8")


def _css() -> str:
    html = _ui()
    return html[html.index("<style"):html.index("</style>")]


def test_hover_effects_only_with_a_mouse() -> None:
    # Am Handy blieb nach dem Antippen von "+" ein grauer Kasten stehen.
    css = _css()
    assert "@media (hover:hover){.iconbtn:hover{" in css
    nackt = [z for z in css.splitlines()
             if re.match(r"^[^\s@][^{]*:hover[^{]*\{", z) and "@media (hover:hover)" not in z]
    # Uebrig bleiben nur Regeln, die zusaetzlich :focus oder einen Zustand abdecken.
    assert all(":focus" in z or "aria-selected" in z for z in nackt), nackt


def test_hover_only_controls_are_visible_on_touch() -> None:
    css = _css()
    block = css[css.index("@media (hover:none) and (pointer:coarse){"):]
    block = block[:block.index("}\n}") + 3]
    assert ".answer-tools,.recent .more{opacity:1}" in block
    assert ".tasten-hinweis{display:none}" in block
    assert 'class="hint tasten-hinweis">Enter senden' in _ui()


def test_collapsed_sidebar_casts_no_shadow_and_takes_no_focus() -> None:
    css = _css()
    assert "body.collapsed aside{box-shadow:none}" in css
    assert re.search(r"body\.collapsed aside\{visibility:hidden;", css)


def test_page_height_follows_the_visible_area() -> None:
    html = _ui()
    assert "interactive-widget=resizes-content" in html
    assert "html.vv,html.vv body{height:var(--app-h)}" in html
    assert 'vv.addEventListener("resize", planen)' in html
    assert "if (vv.scale > 1.01) return;" in html  # Zoomen laesst das Layout in Ruhe


def test_send_button_is_smaller_but_easy_to_hit() -> None:
    css = _css()
    assert re.search(r"\.send\{[^}]*width:30px;height:30px", css)
    assert ".send{width:34px;height:34px" in css
    assert ".send{width:44px;height:44px}" not in css
    # Unsichtbarer Rand: 44px hoch, nach rechts nicht ueber die Knopfzeile hinaus.
    assert '.send::after{content:"";position:absolute;inset:-7px 0 -7px -6px}' in css
    assert ".send::after{inset:-5px 0 -5px -5px}" in css


def test_phone_start_page_puts_the_input_at_the_bottom() -> None:
    css = _css()
    start = css.index("11.2.2 Luna: Handy und Tablet")
    block = css[start:]
    assert "body.start .pane{justify-content:flex-start}" in block
    assert "body.start .chips{order:-1" in block
    assert "body.start footer > *{width:100%;max-width:100%}" in block
    assert ".composer textarea:focus-visible{outline:none}" in block


def test_model_name_stays_visible_on_common_phones() -> None:
    # Vorher wich der Name schon bei 360px einem Sinnbild -- der haeufigsten
    # Android-Breite. Jetzt erst unter 340px.
    css = _css()
    assert "@media (max-width:339px){\n  .modelpick #model-name{display:none}" in css
    assert "@media (max-width:360px){\n  .modelpick #model-name" not in css
