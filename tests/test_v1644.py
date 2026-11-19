"""16.4.4: Gefundene Fehler in Aquaticy Standard (100 Sprachen) und in der Oberflaeche."""

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from aquaticy import standard, weltsprachen

JETZT = datetime(2026, 11, 18, 10, 0, tzinfo=ZoneInfo("Europe/Berlin"))


def frag(text, holen=None, verlauf=None):
    abgerufen = []

    def h(url):
        abgerufen.append(url)
        return holen(url) if holen else None

    return standard.antwort(text, verlauf, holen=h, jetzt=JETZT), abgerufen


def texte(code):
    return weltsprachen.SPRACHEN[code].antworten


def test_nested_phrases_count_once():
    # "kumusta" und "kumusta ka" (Tagalog) zaehlten vorher zusaetzlich zu "kumusta ka diha".
    assert weltsprachen.sprache_von("kumusta ka diha") == "ceb"


@pytest.mark.parametrize("satz, code, art", [
    ("субҳ ба хайр", "tg", "intro"), ("шом ба хайр", "tg", "intro"),
    ("sağ ol görüşənədək", "az", "tschuess"),
])
def test_the_longest_small_talk_phrase_wins(satz, code, art):
    antwort, _ = frag(satz)
    assert antwort == texte(code)[art]


@pytest.mark.parametrize("satz, code", [
    ("mennyi az idő", "hu"), ("koje je vrijeme", "hr"), ("које је време", "sr"),
    ("cik ir laiks", "lv"), ("кое е времето", "mk"),
])
def test_time_questions_with_a_word_for_weather_and_time(satz, code):
    antwort, abgerufen = frag(satz)
    assert weltsprachen.sprache_von(satz) == code
    assert antwort == texte(code)["zeit"].format(zeit="10:00 (UTC+1)")
    assert abgerufen == []


@pytest.mark.parametrize("satz", ["god morgen", "i morgen"])
def test_danish_good_morning_is_not_german(satz):
    assert weltsprachen.sprache_von(satz) == "da"


@pytest.mark.parametrize("satz", [
    "ubijem se", "želim da umrem", "میخواهم بمیرم", "می خواهم بمیرم", "می‌خواهم بمیرم",
])
def test_crisis_help_does_not_depend_on_the_script_or_zwnj(satz):
    antwort, abgerufen = frag(satz)
    assert "findahelpline.com" in antwort
    assert abgerufen == []


def test_serbian_in_latin_script_gets_an_answer():
    antwort, _ = frag("hvala puno")
    assert antwort == texte("bs")["danke"]
    assert not any(weltsprachen.schrift(x) == "latin"
                   for liste in weltsprachen.LISTEN if liste not in ("zeichen",)
                   for x in weltsprachen.SPRACHEN["sr"].listen[liste])


@pytest.mark.parametrize("satz", ["соат неча", "нима гап", "об-ҳаво"])
def test_uzbek_in_cyrillic_is_uzbek(satz):
    assert weltsprachen.sprache_von(satz) == "uz"


def test_a_name_with_rain_in_it_is_not_a_weather_question():
    _, abgerufen = frag("雨宮天とは何ですか")
    assert any("ja.wikipedia.org" in url for url in abgerufen)
    assert not any("open-meteo" in url for url in abgerufen)


@pytest.mark.parametrize("satz, code", [
    ("میں پاکستان سے ہوں", "ur"), ("Я з Києва", "uk"), ("پدرم کجاست", "fa"),
])
def test_typical_letters_decide_without_a_keyword(satz, code):
    assert weltsprachen.sprache_von(satz) == code


@pytest.mark.parametrize("kaputt", [
    {"daily": None}, {"daily": "x"}, {"daily": {"time": ["2026-11-18"], "weather_code": ["a"],
                                                "temperature_2m_max": ["warm"]}},
])
def test_broken_weather_data_does_not_crash(kaputt):
    def holen(url):
        if "geocoding" in url:
            return {"results": [{"name": None, "latitude": 52.5, "longitude": 13.4}]}
        return kaputt

    antwort = standard._antwort("Wie ist das Wetter in Berlin?", [], holen=holen, jetzt=JETZT)
    assert antwort and antwort != standard.FEHLER_TEXT


@pytest.mark.parametrize("geo", [{"results": "x"}, {"results": [None]},
                                 {"results": [{"latitude": "a", "longitude": 1}]}])
def test_broken_place_data_does_not_crash(geo):
    antwort = standard._antwort("Wie ist das Wetter in Berlin?", [],
                                holen=lambda url: geo, jetzt=JETZT)
    assert antwort == standard.NICHT_ERREICHBAR


def test_a_broken_history_does_not_crash():
    antwort, _ = frag("Wie spät ist es?", verlauf=[None, "kaputt", {"role": "user"}])
    assert antwort != standard.FEHLER_TEXT


def test_hungarian_place_keeps_the_weather_phrase_whole():
    sprache = weltsprachen.SPRACHEN["hu"]
    assert weltsprachen.ort_aus("milyen az idő ma Berlinben", sprache) == "Berlin"


def test_chinese_place_is_cut_at_the_best_place():
    sprache = weltsprachen.SPRACHEN["zh"]
    assert weltsprachen.ort_aus("Berlin今天气温", sprache) == "Berlin"
    assert weltsprachen.ort_aus("北京今天天气怎么样", sprache) == "北京"


@pytest.mark.parametrize("satz, code, wiki", [
    ("Python是什么", "zh", "zh"), ("ChatGPT क्या है", "hi", "hi"),
    ("Who is Ada Lovelace", "en", "en"),
])
def test_a_latin_name_does_not_hide_the_language(satz, code, wiki):
    assert weltsprachen.sprache_von(satz) == code


@pytest.mark.parametrize("satz, code, thema", [
    ("co je to Paris", "cs", "paris"), ("ко је био Тесла", "sr", "тесла"),
    ("tko je bio Tesla", "hr", "tesla"), ("willaway Parismanta", "qu", "paris"),
])
def test_the_topic_is_found_with_the_longest_pattern(satz, code, thema):
    assert weltsprachen.thema(satz, weltsprachen.SPRACHEN[code]) == thema


def test_dutch_who_was_is_dutch():
    assert weltsprachen.sprache_von("Wie was Rembrandt?") == "nl"


@pytest.mark.parametrize("satz", ["Regen am Abend", "leichter Regen", "Morgen Schnee in Berlin?",
                                  "Gibt es morgen Regen in Köln?", "Wie lange kocht ein Ei?"])
def test_german_weather_words_stay_german(satz):
    assert weltsprachen.sprache_von(satz) in ("", "de")


def _en():
    seite = Path(standard.__file__).with_name("webui.html").read_text(encoding="utf-8")
    roh = re.search(r"const EN = (\{.*?\n\});", seite, re.S)
    assert roh
    return json.loads(roh.group(1))


@pytest.mark.parametrize("text", [
    "Die Herkunft der Anfrage stimmt nicht.", "Das Passwort stimmt nicht.",
    "Diesen Chat gibt es nicht mehr.", "Zu viele Anmeldeversuche. Bitte warte eine Minute.",
    "Noch nichts zu exportieren — stell erst eine Frage.",
])
def test_error_messages_of_the_server_have_english(text):
    assert _en()[text]


def test_every_error_the_web_server_sends_has_english():
    import ast

    from aquaticy import web

    deutsch = re.compile(r"[äöüßÄÖÜ]|\b(und|nicht|ist|mit|für|ein|eine|wird|noch|auf|dein|"
                         r"kein|keine|jetzt|nur|auch|wie|der|das|zum|zur|aus|kann)\b")
    en = _en()
    baum = ast.parse(Path(web.__file__).read_text(encoding="utf-8"))
    fehlt = []
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Dict):
            for k, v in zip(knoten.keys, knoten.values, strict=True):
                if (isinstance(k, ast.Constant) and k.value == "error"
                        and isinstance(v, ast.Constant) and isinstance(v.value, str)):
                    text = " ".join(v.value.split())
                    if deutsch.search(text) and text not in en:
                        fehlt.append(text)
    assert fehlt == []
