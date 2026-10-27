"""12.0.0 Sol: Der Modell-Knopf ist auf dem Handy so breit wie sein Name.

Bis dahin zog er sich bis zum Mikrofon -- die ganze Luecke oeffnete die
Modellauswahl. Jetzt endet er hinter dem Pfeil; ein langer Name darf den Platz
bis zum Mikrofon nehmen und kuerzt sich dann mit "…". Gemessen wird das im
Browser-Rundgang (tools/rundgang.py, Abschnitte 19a-d).
"""

from __future__ import annotations

from aquaticy import web


def _handy_css() -> str:
    html = web.UI_FILE.read_text(encoding="utf-8")
    start = html.index(".crow{gap:5px}")
    return html[start: html.index("}", html.index(".modelpick{", start)) + 1]


def test_the_model_button_ends_behind_its_arrow_on_phones() -> None:
    css = _handy_css()
    assert ".modelpick{flex:0 1 auto;max-width:none}" in css
    assert "space-between" not in css and "flex:1 1 auto" not in css

    assert ".crow .spacer{display:block;flex:1 1 0;min-width:0}" in css


def test_a_long_name_still_shrinks_instead_of_pushing_the_send_button_out() -> None:
    html = web.UI_FILE.read_text(encoding="utf-8")
    assert "max-width:min(40vw,260px);min-width:0" in html
    assert ".modelpick #model-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" \
        in html
    assert ".mic,.send,.crow .tool{flex:0 0 auto}" in html
