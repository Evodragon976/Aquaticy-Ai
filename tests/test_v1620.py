"""16.2.0: Funktionen geprueft, Fehlerrate gesenkt, Sicherheit."""

from datetime import datetime

import pytest

from tests.test_v965 import parallel_site as parallel_site

# -- Aquaticy Standard: Fragen, die es koennen sollte, aber fallen liess ---------------------

JETZT = datetime(2026, 11, 17, 10, 0)
RUECKFALL = ("Da muss ich passen", "ohne Sprachmodell leider nicht",
             "Das übersteigt leider", "auf Wikipedia leider nichts")


def _std(frage, holen=None):
    from aquaticy import standard

    return standard.antwort(frage, holen=holen or (lambda url: None), jetzt=JETZT)


@pytest.mark.parametrize("frage, erwartet", [
    ("Wie viel ist ein Drittel von 90?", "**30**"),
    ("Was ist die Hälfte von 37?", "**18,5**"),
    ("drei Viertel von 200", "**150**"),
    ("Um wie viel Prozent ist 120 größer als 100?", "**20 %**"),
    ("Um wie viel Prozent ist 80 kleiner als 100?", "**20 %**"),
    ("Wie viel Prozent sind 30 von 120?", "**25 %**"),
    ("what is 45 times 12", "**540**"),
    ("what is 100 divided by 8", "**12.5**"),  # 16.4.5: englische Zahl
    ("Was ist 10 % Rabatt auf 59,99 €?", "**53,99"),
    ("Wie viele Gramm sind 2 Pfund?", "**1.000 Gramm"),
    ("Wie viele Minuten haben 3 Stunden?", "**180 Minuten"),
    ("How many km is 26 miles?", "**41.8429 km"),  # 16.4.5
    ("Welcher Wochentag ist heute?", "Dienstag"),
    ("Was ist heute für ein Tag?", "Dienstag"),
    ("what day is it today", "2026-11-17"),  # 16.4.2: Englisch antwortet englisch
    ("In wie vielen Tagen ist Silvester?", "**44 Tage"),
    ("Wie viele Tage hat der Februar 2027?", "**28 Tage**"),
    ("Wie viele Tage hat der Februar 2028?", "**29 Tage**"),
    ("Zähle die Wörter in: Das ist ein Test", "**4 Wörter**"),
    ("Schreib HALLO WELT klein", "hallo welt"),
    ("Schreib hallo welt groß", "HALLO WELT"),
])
def test_standard_answers_questions_it_used_to_drop(frage, erwartet):
    text = _std(frage)
    assert erwartet in text, text
    assert not any(r in text for r in RUECKFALL), text


@pytest.mark.parametrize("frage", [
    "Wettervorhersage für die nächsten Tage in Leipzig",
    "What's the weather in London?",
    "weather tomorrow in New York",
    "Wie viel Grad hat es in Dresden?",
    "Kann ich heute in Düsseldorf joggen gehen?",
])
def test_weather_questions_reach_the_weather_service(frage):
    abgerufen = []

    def holen(url):
        abgerufen.append(url)
        return None

    _std(frage, holen)
    assert any("open-meteo" in url for url in abgerufen), abgerufen


@pytest.mark.parametrize("frage, waehrungen", [
    ("Wechselkurs Euro Pfund", ("from=EUR", "to=GBP")),
    ("Was ist der Kurs vom Schweizer Franken?", ("from=EUR", "to=CHF")),
    ("Kurs Dollar", ("from=EUR", "to=USD")),
])
def test_exchange_rate_questions_without_in_still_find_the_currencies(frage, waehrungen):
    abgerufen = []

    def holen(url):
        abgerufen.append(url)
        return {"rates": {waehrungen[1][3:]: 0.9}, "date": "2026-11-16"}

    text = _std(frage, holen)
    assert any(all(w in url for w in waehrungen) for url in abgerufen), abgerufen
    assert "0,9" in text


def test_world_news_question_goes_to_the_news():
    abgerufen = []
    _std("Was ist heute in der Welt passiert?", lambda url: abgerufen.append(url))
    assert any("tagesschau" in url for url in abgerufen)


@pytest.mark.parametrize("frage, thema", [
    ("Wie hoch ist der Mount Everest?", "Mount%20Everest"),
    ("Wie lang ist der Rhein?", "Rhein"),
    ("Wie viele Einwohner hat Deutschland?", "Deutschland"),
    ("Wo liegt Neuseeland?", "Neuseeland"),
    ("Wann wurde Rom gegründet?", "Rom"),
    ("Wer hat das Telefon erfunden?", "Telefon"),
    ("Wikipedia Berlin", "Berlin"),
])
def test_fact_questions_look_up_the_topic_on_wikipedia(frage, thema):
    abgerufen = []

    def holen(url):
        abgerufen.append(url)
        return None

    _std(frage, holen)
    assert any("wikipedia" in url and thema in url for url in abgerufen), abgerufen


@pytest.mark.parametrize("text", ["Vielen Dank, das hilft mir sehr", "Danke, super!"])
def test_thanks_with_praise_is_small_talk(text):
    from aquaticy import smalltalk

    art = smalltalk.art_von(text)
    assert art is not None and art.name == "danke"


def test_with_aquaticy_standard_what_can_you_do_lists_what_standard_can_do():
    from aquaticy import agent as agent_mod

    class Fake:
        _plugin_turn = False
        secure_pro = False

        def _standard_model(self):
            return True

    assert agent_mod.smalltalk_fuer(Fake(), "Was kannst du?") == ""
    assert agent_mod.smalltalk_fuer(Fake(), "Hallo, was kannst du alles?") == ""
    assert agent_mod.smalltalk_fuer(Fake(), "Hallo") != ""
    Fake._standard_model = lambda self: False
    assert agent_mod.smalltalk_fuer(Fake(), "Was kannst du?") != ""


@pytest.mark.parametrize("frage, ort", [
    ("Wetter Hamburg", "Hamburg"),
    ("Hamburg Wetter", "Hamburg"),
    ("Wetterbericht Nürnberg", "N%C3%BCrnberg"),
    ("Wettervorhersage Bad Homburg", "Bad%20Homburg"),
])
def test_weather_with_a_bare_place_name_looks_up_that_place(frage, ort):
    abgerufen = []

    def holen(url):
        abgerufen.append(url)
        return None

    _std(frage, holen)
    assert any("geocoding" in url and ort in url for url in abgerufen), abgerufen


def test_weather_with_only_a_day_still_asks_for_the_place():
    assert "Für welchen Ort" in _std("Wetter morgen")


@pytest.mark.parametrize("frage, erwartet", [
    ("Wie viele Sekunden hat eine Stunde?", "**3.600 Sekunden"),
    ("how many grams is 1 pound", "**453.5924 grams"),  # 16.4.5
    ("convert 5 kilometers to miles", "**3.1069 miles"),  # 16.4.5
])
def test_more_unit_questions(frage, erwartet):
    text = _std(frage)
    assert erwartet in text, text


def test_a_greeting_or_thanks_in_front_of_a_question_is_ignored():
    abgerufen = []
    _std("Danke, und wie hoch ist der Eiffelturm?", lambda url: abgerufen.append(url))
    assert any("Eiffelturm" in url for url in abgerufen)
    assert "**56**" in _std("Hallo! Was ist 7 mal 8?")


@pytest.mark.parametrize("frage", ["Wo liegt mein Fehler im Code?", "Wie lang ist deine Antwort?"])
def test_questions_about_own_things_do_not_go_to_wikipedia(frage):
    abgerufen = []
    _std(frage, lambda url: abgerufen.append(url))
    assert not any("wikipedia" in url for url in abgerufen)


@pytest.mark.parametrize("text, art", [
    ("Vielen Dank für deine Hilfe", "danke"),
    ("Thank you so much", "danke"),
    ("Thanks a lot", "danke"),
    ("Gute Nacht und danke", "gute_nacht"),
    ("Good morning", "morgen"),
    ("Good night", "gute_nacht"),
    ("Who are you?", "identitaet"),
    ("What can you do?", "faehigkeiten"),
])
def test_more_everyday_small_talk_is_recognised(text, art):
    from aquaticy import smalltalk

    gefunden = smalltalk.art_von(text)
    assert gefunden is not None and gefunden.name == art


# -- Neuer Chat: schnell getippt geht nicht verloren -----------------------------------------

@pytest.mark.parametrize("wann", ["vor_der_antwort", "nach_der_antwort"])
def test_text_typed_while_a_new_chat_opens_is_sent_into_the_new_chat(
        parallel_site, monkeypatch, wann):
    import shutil
    import threading

    from aquaticy import web
    from tests.anmeldung import AGENT, SPRACHE

    playwright = pytest.importorskip("playwright.sync_api")
    executable = shutil.which("chromium")
    if not executable:
        pytest.skip("System-Chromium fehlt")
    client, _, _, _, _, url = parallel_site
    tor, scharf = threading.Event(), threading.Event()
    echt = web.ChatSession.switch_chat

    def langsam(self, chat_id=""):
        # Der Server antwortet auf "Neuer Chat" erst, wenn der Test es erlaubt.
        if scharf.is_set() and not chat_id:
            tor.wait(10)
        return echt(self, chat_id)

    monkeypatch.setattr(web.ChatSession, "switch_chat", langsam)
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=executable)
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 800},
                                          user_agent=AGENT,
                                          extra_http_headers={"Accept-Language": SPRACHE})
            context.add_cookies([{"name": name, "value": value, "url": url}
                                for name, value in client.cookies.items()])
            page = context.new_page()
            page.goto(url, wait_until="networkidle")
            page.locator("#auth-gate").wait_for(state="hidden")
            scharf.set()
            page.click("#btn-new")
            page.fill("#input", "Hallo Luna")
            if wann == "vor_der_antwort":
                page.click("#send")
                tor.set()
            else:
                with page.expect_response(lambda r: r.url.endswith("/api/clear")):
                    tor.set()
                page.wait_for_timeout(200)
                page.click("#send")
            playwright.expect(page.locator("#thread")).to_contain_text("Antwort auf Hallo Luna")
        finally:
            tor.set()
            browser.close()
