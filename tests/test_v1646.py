"""16.4.6: Sicherheitsupdate soupsieve, Fehlalarme im Code-Review, Wochentag der Feiertage."""

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from aquaticy import review_scan, standard

JETZT = datetime(2026, 11, 19, 14, 30, tzinfo=ZoneInfo("Europe/Berlin"))
REPO = Path(__file__).resolve().parent.parent


def frag(text: str) -> str:
    return standard._antwort(text, [], holen=lambda url: None, jetzt=JETZT)


def test_soupsieve_is_pinned_past_the_known_vulnerability():
    # CVE-2026-126190 (GHSA-mmhr-3c5m-f64f): behoben ab soupsieve 4.0.0. pip-audit in der CI
    # schlug mit 3.0.4 fehl.
    treffer = re.search(r"^soupsieve==(\d+)\.(\d+)(?:\.(\d+))?$",
                        (REPO / "constraints.txt").read_text(encoding="utf-8"), re.M)
    assert treffer
    assert int(treffer.group(1)) >= 4


@pytest.mark.parametrize("code", [
    'headers = {"Authorization": f"Bearer {token}"}',
    'GITHUB_TOKEN_KEY = "AQUATICY_GITHUB_TOKEN"',
    '"AQUATICY_CONTEXT_TOKENS": "context_tokens",',
    'TOKEN_LIMIT_STATE = "Kontingent erreicht"',
    '"AQUATICY_GITHUB_TOKEN": "mit welchem Zugang ich GitHub lese",',
    'kopf = b"X-Salt: " + base64.b64encode(salz) + b"\\r\\n"',
])
def test_review_does_not_report_templates_names_or_text_as_secrets(code):
    assert "CWE-798" not in [h.rule for h in review_scan.scan_file("x.py", code)]


@pytest.mark.parametrize("code", [
    'password = "hunter2hunter2"',
    'password = "Long phrase with spaces 73!"',
    'token = "correct horse battery staple"',
    'headers = {"Authorization": "Bearer Abc12345xyz"}',
])
def test_review_still_reports_real_looking_secrets(code):
    assert "CWE-798" in [h.rule for h in review_scan.scan_file("x.py", code)]


def test_masking_stays_as_strict_as_before():
    # Verdecken und Blockieren (github_write) haengen an _secret_value_ok -- unveraendert.
    for code in ('headers = {"Authorization": f"Bearer {token}"}',
                 'TOKEN_LIMIT_STATE = "Kontingent erreicht"'):
        assert review_scan.mask_secrets(code) != code


@pytest.mark.parametrize("code, gemeldet", [
    ("import xml.etree.ElementTree as ET", False),
    ("from xml.dom import minidom", False),
    ("xml.sax.parseString(data, handler)", False),
    ("from lxml import etree", True),
    ("etree.XMLParser(resolve_entities=True)", True),
    ("parser.setFeature(feature_external_ges, True)", True),
    ("DocumentBuilderFactory.newInstance()", True),
])
def test_xml_rule_only_reports_parsers_with_external_entities(code, gemeldet):
    assert ("CWE-611" in [h.rule for h in review_scan.scan_file("x.py", code)]) is gemeldet


@pytest.mark.parametrize("frage, erwartet", [
    ("Welcher Wochentag ist Pfingstmontag?", "Pfingstmontag ist am **Montag, 17.05.2027**."),
    ("Welcher Wochentag ist Ostermontag?", "Ostermontag ist am **Montag, 29.03.2027**."),
    ("Welcher Tag ist der Tag der Arbeit?", "Tag der Arbeit ist am **Samstag, 01.05.2027**."),
    ("Welcher Tag ist Christi Himmelfahrt?",
     "Christi Himmelfahrt ist am **Donnerstag, 06.05.2027**."),
    ("Welcher Wochentag ist Karfreitag 2027?", "Karfreitag ist 2027 am **Freitag, 26.03.2027**."),
])
def test_weekday_of_public_holidays(frage, erwartet):
    assert frag(frage) == erwartet
