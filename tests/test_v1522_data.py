"""15.2.2: nachgestellte Fehler in Daten, Terminen, Quellen und lokalen Befehlen."""

import base64
import struct

import pytest
from selectolax.parser import HTMLParser

from aquaticy import (
    calc,
    export,
    extract,
    google,
    homeassistant,
    ownservices,
    queries,
    secure_tasks,
    storage,
    vm_ssh,
    voice,
)


def encoded(text, charset="utf-8"):
    return base64.urlsafe_b64encode(text.encode(charset)).decode()


@pytest.mark.parametrize("expression,expected", [("1e-7", 1e-7), ("1000000.5", 1000000.5)])
def test_f01_calculator_display_does_not_change_the_value(expression, expected):
    assert float(calc.calculate_pretty(expression)) == pytest.approx(expected, rel=1e-12, abs=0)


def test_f02_arithmetic_failures_are_reported_as_calc_errors():
    with pytest.raises(calc.CalcError):
        calc.calculate("1e-300 ** -12")


def test_f03_a_zero_jsonld_price_is_not_a_missing_price():
    price, currency, _ = extract._offer_fields({"offers": {"price": 0, "priceCurrency": "EUR"}})
    assert price == "0" and currency == "EUR"


def test_f04_a_later_valid_product_image_is_used():
    assert extract._first_image(["javascript:alert(1)", "https://img.example/a.png"],
                                "https://shop.example/") == "https://img.example/a.png"


def test_f05_a_broken_image_url_does_not_abort_product_extraction():
    assert extract._absolute("http://[broken", "https://shop.example/") is None



def test_f06_microdata_properties_belong_to_the_product_not_the_shop():
    tree = HTMLParser('<div itemscope itemtype="https://schema.org/Organization">'
                      '<span itemprop="name">Shop</span></div>'
                      '<div itemscope itemtype="https://schema.org/Product">'
                      '<span itemprop="name">Camera</span><meta itemprop="price" content="5">'
                      '</div>')
    result = extract.product_from_microdata(tree, "https://shop.example/")
    assert result is not None and result.name == "Camera"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_f07_nonfinite_ratings_never_reach_json_output(value):
    assert extract._as_float(value) is None


def test_f08_invalid_all_day_dates_are_rejected_before_google_is_called():
    with pytest.raises(google.GoogleError):
        google._times("2026-02-31", "", True)


@pytest.mark.parametrize("start,end,day", [
    ("2026-11-06T14:00:00+01:00", "2026-11-06T13:00:00+01:00", False),
    ("2026-11-06", "2026-11-06", True),
])
def test_f09_calendar_events_must_end_after_they_start(start, end, day):
    with pytest.raises(google.GoogleError):
        google._times(start, end, day)


def test_f10_changing_only_the_calendar_start_does_not_overwrite_the_end(monkeypatch):
    client = object.__new__(google.Google)
    sent = []
    monkeypatch.setattr(client, "_write", lambda method, url, payload: sent.append(payload) or
                        {"id": "event", "start": payload["start"], "end": {}})
    client.update_event("event", start="2026-11-06T10:00:00+01:00")
    assert "start" in sent[0] and "end" not in sent[0]


def test_f11_mail_parts_use_their_declared_character_encoding():
    payload = {"mimeType": "text/plain", "headers": [
        {"name": "Content-Type", "value": 'text/plain; charset="iso-8859-1"'}],
        "body": {"data": encoded("Grüße", "iso-8859-1")}}
    assert google._body_text(payload) == "Grüße"


def test_f12_plaintext_attachments_do_not_replace_the_mail_body():
    payload = {"mimeType": "multipart/mixed", "parts": [
        {"mimeType": "text/plain", "filename": "attachment.txt", "body": {
            "data": encoded("Attachment")}},
        {"mimeType": "text/html", "body": {"data": encoded("<p>Message</p>")}}]}
    assert google._body_text(payload) == "Message"


def test_f13_home_assistant_rejects_an_unintended_all_entities_call():
    with pytest.raises(homeassistant.HomeAssistantError):
        homeassistant.check_call("light", "turn_on")


@pytest.mark.parametrize("normalize", [homeassistant.normalize_url, storage.normalize_url])
@pytest.mark.parametrize("url", ["http://user:secret@home.local", "http://home.local?x=1",
                                  "http://home.local#fragment"])
def test_f14_service_urls_cannot_hide_api_paths_or_credentials(normalize, url):
    assert normalize(url) == ""


@pytest.mark.parametrize("question,domain", [("Wie steht der Ventilator?", "fan"),
                                             ("Kontrolliere den Staubsauger", "vacuum")])
def test_f15_home_queries_select_the_actual_device_domain(question, domain):
    assert ownservices.home_domain(question) == domain


def test_f16_an_explicit_voice_refusal_is_respected():
    assert not voice.requested("Schicke mir keine Sprachnachricht.")


def test_f17_a_city_inside_another_word_does_not_disable_the_location_filter():
    assert queries.with_place("Beste Orangenpressen", "Essen").endswith(" Essen")


def test_f18_a_host_key_requires_key_material_not_just_an_algorithm_name():
    name = b"ssh-ed25519"
    header_only = "ssh-ed25519 " + base64.b64encode(struct.pack(">I", len(name)) + name).decode()
    with pytest.raises(ValueError):
        vm_ssh.host_key(header_only)


def test_f19_a_malformed_task_ip_cannot_broaden_a_task_to_the_entire_network():
    with pytest.raises(ValueError):
        secure_tasks.parse("Melde neue Ports auf 999.1.1.1")


def test_f20_export_links_require_an_actual_host():
    assert export.safe_link("https://") == ""


def test_mail_html_boilerplate_does_not_hide_a_short_body():
    html = "<html><head><style>" + " " * 40000 + "</style></head><body>Message</body></html>"
    payload = {"mimeType": "text/html", "body": {"data": encoded(html)}}
    assert google._body_text(payload) == "Message"


def test_new_safety_checks_keep_valid_values_usable():
    assert homeassistant.check_call("light", "turn_on", "light.desk")["entity_id"] == "light.desk"
    assert homeassistant.normalize_url("http://home.local:8123/base") == "http://home.local:8123/base"
    assert google._times("2026-11-06", "", True) == (
        {"date": "2026-11-06"}, {"date": "2026-11-07"})
    assert voice.requested("Schicke mir eine Sprachnachricht.")
    assert export.safe_link("https://example.com/path") == "https://example.com/path"
