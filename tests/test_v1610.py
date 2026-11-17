"""16.1.0: Sicherheitspruefung (15 Angriffe) und gefundene Fehler."""

import pytest

# -- Smalltalk: ein Gruss vor der eigentlichen Nachricht --------------------------------------

@pytest.mark.parametrize("text, art", [
    ("Hallo, wie geht es dir?", "wie_gehts"),
    ("Hallo! Wie geht es dir?", "wie_gehts"),
    ("hi, how are you?", "wie_gehts"),
    ("How are you doing?", "wie_gehts"),
    ("Guten Morgen, alles gut?", "wie_gehts"),
    ("Moin, wie läufts?", "wie_gehts"),
    ("Hallo, danke!", "danke"),
    ("Hallo, wer bist du?", "identitaet"),
    ("Guten Abend!", "abend"),
    ("Hallo, ok", "begruessung"),
])
def test_a_greeting_in_front_does_not_hide_the_small_talk(text, art):
    from aquaticy import smalltalk

    gefunden = smalltalk.art_von(text)
    assert gefunden is not None and gefunden.name == art
    assert smalltalk.antwort(text)


@pytest.mark.parametrize("text", [
    "Hallo, wie ist das Wetter in Berlin?",
    "Hallo, erklär mir bitte Quantencomputer",
    "Danke, und wie hoch ist der Eiffelturm?",
    "ok, wie spät ist es in Tokio?",
])
def test_a_real_question_after_a_greeting_still_goes_on(text):
    from aquaticy import smalltalk

    assert smalltalk.art_von(text) is None


@pytest.mark.parametrize("text", ["Hallo, alles klar", "Hallo, ok", "Guten Morgen, passt"])
def test_with_an_open_question_a_greeting_does_not_swallow_the_answer(text):
    from aquaticy import smalltalk

    assert smalltalk.art_von(text, frage_offen=True) is None


# -- DuckDuckGo-Ausweichsuche: nur Regionen, die es dort gibt -----------------------------------

@pytest.mark.parametrize("land, sprache, region", [
    ("de", "de", "de-de"),
    ("de", "ja", "de-de"),
    ("jp", "ja", "jp-jp"),
    ("us", "en", "us-en"),
    ("gb", "en", "uk-en"),
    ("ch", "fr", "ch-fr"),
    ("xx", "yy", "wt-wt"),
    ("", "", "de-de"),
])
def test_the_html_fallback_only_sends_regions_duckduckgo_knows(land, sprache, region):
    from aquaticy import search

    assert search._ddg_region(land, sprache) == region


# -- Ort und Sprache aus dem Chat: Namen mit Akzent, Zusatz und "in der Nähe von" -------------

@pytest.mark.parametrize("satz, ort", [
    ("Wetter morgen in São Paulo", "São Paulo"),
    ("Hotels in Málaga", "Málaga"),
    ("Wetter in St. Gallen", "St. Gallen"),
    ("Wetter in Frankfurt am Main", "Frankfurt am Main"),
    ("Kinos in der Nähe von Köln", "Köln"),
    ("Restaurants in New York", "New York"),
])
def test_place_names_with_accents_and_additions_are_found(satz, ort):
    from aquaticy import autoort

    assert autoort.orte_in(satz) == [ort]


@pytest.mark.parametrize("satz", [
    "Wetter in Berlin am Wochenende",
    "Hotels in Paris. Danke",
])
def test_a_place_does_not_swallow_the_rest_of_the_sentence(satz):
    from aquaticy import autoort

    assert autoort.orte_in(satz) in (["Berlin"], ["Paris"])


@pytest.mark.parametrize("satz, sprache", [
    ("Bonjour, comment ça va? Je cherche un hôtel à Lyon", "fr"),
    ("Hola, ¿qué tiempo hace hoy en Madrid? Busco un hotel", "es"),
    ("Wie ist das Wetter heute in Hamburg und was ziehe ich an?", "de"),
    ("What is the weather like today and what should I wear?", "en"),
])
def test_everyday_sentences_reveal_their_language(satz, sprache):
    from aquaticy import autoort

    assert autoort.erkenne_sprache(satz) == sprache
