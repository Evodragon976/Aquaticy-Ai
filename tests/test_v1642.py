"""16.4.2: Aquaticy Standard in den 100 meistgesprochenen Sprachen."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from aquaticy import standard, weltsprachen

JETZT = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Europe/Berlin"))
ANDERE = [c for c in weltsprachen.SPRACHEN if c != "de"]
#: Nah verwandte Sprachen teilen Woerter -- dann antwortet die groessere (verstaendlich).
VERWANDT = [{"hr", "bs", "sr"}, {"ms", "id", "su", "jv"}, {"xh", "zu"},
            {"hi", "mr", "ne", "bho", "mai"}, {"zh", "yue"}, {"nl", "af", "de"},
            {"no", "da", "sv", "fi"}, {"es", "ca"}, {"en", "pcm"}, {"sr", "mk", "bg", "sl"},
            {"ur", "sd", "fa", "ps"}, {"tr", "az", "tk"}, {"uz", "tg", "ky", "kk"},
            {"lv", "lt"}, {"ro", "fr", "tr", "pl"}, {"bn", "as"}, {"sk", "cs"},
            {"tl", "ceb"}, {"ru", "uk", "be"}, {"mn"}, {"ku", "sw"}]


def verwandt(a: str, b: str) -> bool:
    return a == b or any(a in g and b in g for g in VERWANDT)


def frag(text, holen=None, verlauf=None):
    abgerufen = []

    def h(url):
        abgerufen.append(url)
        return holen(url) if holen else None

    return standard.antwort(text, verlauf, holen=h, jetzt=JETZT), abgerufen


def test_there_are_100_languages_and_each_is_complete():
    assert len(weltsprachen.SPRACHEN) == 100
    for code in ANDERE:
        sprache = weltsprachen.SPRACHEN[code]
        for liste in ("hallo", "info", "danke", "tschuess", "wiegehts", "wetter", "zeit",
                      "datum", "heute", "morgen", "wiki", "krise"):
            assert sprache.listen[liste], (code, liste)
        assert set(sprache.antworten) == set(weltsprachen.ANTWORTEN), code
        assert "{zeit}" in sprache.antworten["zeit"]
        assert "{datum}" in sprache.antworten["datum"]
        assert "{x}" in sprache.antworten["nichts"]
        assert "findahelpline.com" in sprache.antworten["krise"]
        assert all("{x}" in muster for muster in sprache.listen["wiki"]), code


def test_the_data_file_keeps_the_line_length():
    datei = Path(weltsprachen.__file__).with_name("weltsprachen_daten.py")
    assert max(len(z) for z in datei.read_text(encoding="utf-8").splitlines()) <= 100


@pytest.mark.parametrize("code", ANDERE)
def test_a_greeting_is_answered_in_the_same_language(code):
    sprache = weltsprachen.SPRACHEN[code]
    gefunden = weltsprachen.sprache_von(sprache.listen["hallo"][0])
    assert verwandt(code, gefunden), (code, gefunden)
    if gefunden not in ("de", "en"):
        antwort, _ = frag(sprache.listen["hallo"][0])
        texte = weltsprachen.SPRACHEN[gefunden].antworten
        assert antwort in (texte["intro"], texte["wiegehts"])


@pytest.mark.parametrize("code", ANDERE)
def test_the_time_is_told_in_every_language(code):
    sprache = weltsprachen.SPRACHEN[code]
    antwort, _ = frag(sprache.listen["zeit"][0])
    gefunden = weltsprachen.sprache_von(sprache.listen["zeit"][0])
    assert verwandt(code, gefunden)
    assert antwort == weltsprachen.SPRACHEN[gefunden].antworten["zeit"].format(
        zeit="10:00 (UTC+1)")


@pytest.mark.parametrize("code", ANDERE)
def test_weather_without_a_place_asks_for_it_in_the_language(code):
    sprache = weltsprachen.SPRACHEN[code]
    frage = sprache.listen["wetter"][0] + " " + sprache.listen["heute"][0]
    gefunden = weltsprachen.sprache_von(frage)
    antwort, _ = frag(frage)
    assert verwandt(code, gefunden)
    assert antwort == weltsprachen.SPRACHEN[gefunden].antworten["ort"]


@pytest.mark.parametrize("code", [c for c in ANDERE
                                  if weltsprachen.SPRACHEN[c].schriften[0] == "latin"])
def test_weather_with_a_place_asks_open_meteo_for_that_place(code):
    sprache = weltsprachen.SPRACHEN[code]
    _, abgerufen = frag(sprache.listen["wetter"][0] + " Berlin")
    assert any("geocoding" in url and "Berlin" in url for url in abgerufen), abgerufen


@pytest.mark.parametrize("code", ANDERE)
def test_knowledge_questions_go_to_the_wikipedia_of_the_language(code):
    sprache = weltsprachen.SPRACHEN[code]
    frage = sprache.listen["wiki"][0].replace("{x}", sprache.name.split()[0])
    gefunden = weltsprachen.sprache_von(frage)
    _, abgerufen = frag(frage)
    wiki = weltsprachen.SPRACHEN[gefunden].wiki
    assert verwandt(code, gefunden)
    assert any(f"https://{wiki}.wikipedia.org/" in url for url in abgerufen), abgerufen


@pytest.mark.parametrize("code", ANDERE)
def test_crisis_words_bring_help_in_every_language(code):
    antwort, abgerufen = frag(weltsprachen.SPRACHEN[code].listen["krise"][0])
    assert "findahelpline.com" in antwort or "112" in antwort or "988" in antwort, antwort
    assert abgerufen == []


@pytest.mark.parametrize("satz, code", [
    ("¿Qué tiempo hace en Madrid mañana?", "es"), ("Quelle heure est-il ?", "fr"),
    ("Привет, как дела?", "ru"), ("Привіт! Як справи?", "uk"), ("北京今天天气怎么样", "zh"),
    ("東京の天気はどうですか", "ja"), ("서울 날씨 어때요", "ko"), ("मुंबई का मौसम कैसा है", "hi"),
    ("كم الساعة الآن", "ar"), ("Merhaba, nasılsın?", "tr"), ("Xin chào, bạn khỏe không?", "vi"),
    ("Habari yako?", "sw"), ("Obrigado pela ajuda", "pt"), ("Dzień dobry, jak się masz?", "pl"),
    ("Hoe laat is het?", "nl"), ("Hur mår du?", "sv"), ("Mitä kuuluu?", "fi"),
    ("Γεια σου, τι κάνεις;", "el"), ("שלום, מה שלומך?", "he"), ("สวัสดีครับ", "th"),
    ("Ce mai faci?", "ro"), ("Jak se máš?", "cs"), ("Hogy vagy?", "hu"),
    ("Salamu, apa kabar?", "id"), ("hewa çawa ye li Amedê", "ku"), ("Kako si?", "hr"),
    ("Как си?", "bg"), ("Бүгін ауа райы", "kk"),
    ("Wie ist das Wetter in Berlin?", "de"), ("What's the weather like in London?", "en"),
])
def test_everyday_sentences_are_recognised(satz, code):
    assert weltsprachen.sprache_von(satz) == code


def test_german_and_english_keep_their_bigger_path():
    antwort, _ = frag("How many km is 26 miles?")
    assert "41.8429" in antwort  # 16.4.5: englische Frage, englische Zahl
    antwort, _ = frag("Wie viel ist ein Drittel von 90?")
    assert "**30**" in antwort
    antwort, _ = frag("what day is it today")
    assert antwort == "Today is 2026-11-18."


def test_a_place_after_the_place_question_is_used_in_that_language():
    frage = weltsprachen.SPRACHEN["es"].antworten["ort"]
    verlauf = [{"role": "user", "content": "¿Qué tiempo hace?"},
               {"role": "assistant", "content": frage}]
    _, abgerufen = frag("Madrid", verlauf=verlauf)
    assert any("geocoding" in url and "Madrid" in url for url in abgerufen)


def test_weather_is_shown_with_numbers_every_language_can_read():
    def holen(url):
        if "geocoding" in url:
            return {"results": [{"name": "Madrid", "latitude": 40.4, "longitude": -3.7}]}
        return {"daily": {"time": ["2026-11-18", "2026-11-19"], "weather_code": [0, 61],
                          "temperature_2m_max": [18, 15], "temperature_2m_min": [7, 9],
                          "precipitation_probability_max": [5, 80]}}

    antwort, _ = frag("¿Qué tiempo hace en Madrid mañana?", holen)
    assert "**Madrid** · mañana" in antwort and "9 – 15 °C" in antwort and "80 %" in antwort


def test_only_the_fixed_wikipedia_hosts_are_allowed():
    assert "es.wikipedia.org" in standard.ERLAUBTE_HOSTS
    assert "zh-yue.wikipedia.org" in standard.ERLAUBTE_HOSTS
    assert all(h.endswith(".wikipedia.org") or h in (
        "api.open-meteo.com", "geocoding-api.open-meteo.com", "api.frankfurter.app",
        "www.tagesschau.de") for h in standard.ERLAUBTE_HOSTS)
    assert standard.holen_json("https://evil.wikipedia.org.example.com/x") is None


def test_with_aquaticy_standard_small_talk_in_another_language_is_left_to_standard():
    from aquaticy import agent as agent_mod

    class Fake:
        _plugin_turn = False
        secure_pro = False

        def _standard_model(self):
            return True

    assert agent_mod.smalltalk_fuer(Fake(), "hola") == ""
    assert agent_mod.smalltalk_fuer(Fake(), "Merci beaucoup") == ""
    assert agent_mod.smalltalk_fuer(Fake(), "Hallo") != ""
    Fake._standard_model = lambda self: False
    assert agent_mod.smalltalk_fuer(Fake(), "Thanks") != ""


@pytest.mark.parametrize("satz", [
    "Gibt es morgen Regen in Köln?", "Wie lange kocht ein Ei?", "Wo gibt es Crêpes?", "Hi",
    "Was ist ein Kolibri?", "Erzähl mir einen Witz", "Wie spät ist es in Tokio?",
    "Mach das Licht im Wohnzimmer an", "Ich habe Hunger", "Hallo, wie geht es dir?",
])
def test_german_sentences_stay_german(satz):
    assert weltsprachen.sprache_von(satz) in ("", "de"), satz


@pytest.mark.parametrize("satz", [
    "What does a spider bite look like?", "What time is it in Tokyo?", "Thanks a lot",
    "How long do I boil an egg?", "Tell me a joke about cats", "Is it going to rain tomorrow?",
])
def test_english_sentences_stay_english(satz):
    assert weltsprachen.sprache_von(satz) in ("", "en"), satz


def test_crisis_help_always_carries_the_english_text_too():
    antwort = standard.welt_krise(weltsprachen.SPRACHEN["sw"].listen["krise"][0])
    assert "findahelpline.com" in antwort
    englisch = weltsprachen.SPRACHEN["en"].antworten["krise"]
    assert englisch in antwort


def test_the_local_time_of_a_place_uses_its_time_zone():
    def holen(url):
        if "geocoding" in url:
            return {"results": [{"name": "Tokio", "latitude": 35.7, "longitude": 139.7,
                                 "timezone": "Asia/Tokyo"}]}
        return None

    antwort, abgerufen = frag("¿Qué hora es en Tokio?", holen)
    assert any("geocoding" in url for url in abgerufen)
    assert "18:00" in antwort and "Tokio" in antwort
