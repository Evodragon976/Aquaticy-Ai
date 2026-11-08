"""15.2.2: Gegenproben fuer Laufzeit, Messenger und externe Kontodaten."""

import base64
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest

import aquaticy
from aquaticy import (
    bridge,
    coworker,
    google,
    linked,
    messenger_native,
    ownservices,
    preferences,
    startup,
    webview,
)


def test_f39_startup_does_not_reinstall_the_same_release_stage(monkeypatch):
    calls = []
    monkeypatch.delenv("AQUATICY_STARTUP_CHILD", raising=False)
    monkeypatch.setattr(aquaticy, "VERSION_LABEL", "15.2.1 Preview")
    monkeypatch.setattr(startup.shutil, "which", lambda name: name)

    def run(args, **kwargs):
        calls.append(args)
        if "clone" in args:
            target = Path(args[-1]) / "aquaticy"
            target.mkdir(parents=True)
            (target / "__init__.py").write_text(
                '__version__ = "15.2.1"\n__codename__ = ""\n__stage__ = "Preview"\n')
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(startup.subprocess, "run", run)
    assert not startup.update_at_start(SimpleNamespace(print=lambda *a, **kw: None))
    assert not any("install" in args for args in calls)


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="Zeitzonenwechsel braucht tzset")
@pytest.mark.parametrize("month,day,touched_month,touched_day,hour,expected", [
    (3, 30, 3, 28, 23, "Letzte 7 Tage"),
    (10, 26, 10, 25, 0, "Gestern"),
])
def test_f40_yesterday_uses_local_calendar_days_across_dst(
    month, day, touched_month, touched_day, hour, expected,
):
    old = os.environ.get("TZ")
    try:
        os.environ["TZ"] = "Europe/Berlin"
        time.tzset()
        tz = ZoneInfo("Europe/Berlin")
        now = datetime(2026, month, day, 12, tzinfo=tz).timestamp()
        touched = datetime(2026, touched_month, touched_day, hour, 30, tzinfo=tz).timestamp()
        assert webview.chat_group(touched, now) == expected
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


def test_f41_duplicate_coworker_names_cannot_select_an_arbitrary_recipient(settings):
    store = coworker.CoworkerStore(settings.db_path)
    store.add("Ava", "Observe the news")
    store.add("ava", "Observe the prices")
    with pytest.raises(ValueError):
        store.by_name("AVA")


def test_f42_integer_preferences_do_not_silently_truncate_fractional_values():
    preference = preferences.find("subagenten_anzahl")
    assert preference is not None
    with pytest.raises(preferences.BadValue):
        preferences.coerce(preference, "2.9")


def test_f43_aliases_of_the_same_database_share_the_same_coworker_claim(tmp_path):
    first = tmp_path / "cache.db"
    alias = tmp_path / "folder" / ".." / "cache.db"
    try:
        assert coworker.claim(first, 9)
        assert not coworker.claim(alias, 9)
    finally:
        coworker.release(first, 9)
        coworker.release(alias, 9)


def test_f44_plaintext_messenger_output_preserves_code_and_urls():
    result = bridge.to_chat_text('**Titel**\n```python\ndef __init__():\n    return 2**3\n```'
                                 '\nhttps://github.com/o/repo__name', wide=True)
    assert "def __init__():" in result and "return 2**3" in result
    assert "https://github.com/o/repo__name" in result
    assert "**Titel**" not in result and "```" not in result


def test_f45_phone_numbers_with_letters_are_not_guessed():
    assert messenger_native.clean_number("+49wrong1701234567") == ""
    assert messenger_native.clean_number("+49 (170) 123-45-67") == "+491701234567"


def test_f46_a_failed_nvidia_model_probe_is_not_a_successful_connection():
    def reply(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "meta/llama-3.1-8b-instruct"}]})
        return httpx.Response(404, json={"message": "Function not found for account"})

    with (httpx.Client(transport=httpx.MockTransport(reply)) as client,
          pytest.raises(linked.LinkError)):
        linked.inspect("nvidia_nim", "fake-key", client)


@pytest.mark.parametrize("payload", [{}, {"access_token": "", "expires_in": 3600},
                                      {"access_token": "new", "expires_in": float("nan")}])
def test_f47_invalid_token_responses_do_not_overwrite_a_working_connection(monkeypatch, payload):
    from contextlib import contextmanager

    @contextmanager
    def stream(*args, **kwargs):
        response = (httpx.Response(200, json=payload)
                    if payload.get("expires_in") == payload.get("expires_in") else
                    httpx.Response(200, text='{"access_token":"new","expires_in":NaN}'))
        try:
            yield response
        finally:
            response.close()

    monkeypatch.setattr(google.httpx, "stream", stream)
    tokens = google.Tokens(access_token="old", refresh_token="refresh", expires_at=1)
    with pytest.raises(google.GoogleError):
        google.refresh_tokens("client", "secret", tokens)
    assert tokens.access_token == "old" and tokens.expires_at == 1


@pytest.mark.parametrize("method", ["read_mail", "_headers"])
def test_f48_mime_encoded_headers_are_decoded_for_users(monkeypatch, method):
    client = object.__new__(google.Google)
    subject = "=?UTF-8?B?" + base64.b64encode("Grüße".encode()).decode() + "?="
    monkeypatch.setattr(client, "_get", lambda *a: {"payload": {"headers": [
        {"name": "Subject", "value": subject}]}})
    assert getattr(client, method)("message")["subject"] == "Grüße"


def test_f49_mail_decoding_is_bounded_before_building_the_full_decoded_text():
    payload = {"mimeType": "text/plain", "body": {"data": base64.urlsafe_b64encode(
        b"x" * (google.MAX_BODY_CHARS * 20)).decode()}}
    assert len(google._body_text(payload)) <= google.MAX_BODY_CHARS + 1


@pytest.mark.parametrize("question,days", [
    ("Welche Termine habe ich heute und morgen?", 2),
    ("Zeige mir heute den Kalender für diesen Monat", 31),
])
def test_f50_calendar_prefetch_covers_the_explicit_longer_period(question, days):
    assert ownservices.calendar_days(question) == days


def test_nvidia_connection_uses_a_working_alternative_when_the_probe_model_is_gone():
    attempts = []

    def reply(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "meta/llama-3.1-8b-instruct"}]})
        attempts.append(request)
        return httpx.Response(404 if len(attempts) == 1 else 200, json={})

    with httpx.Client(transport=httpx.MockTransport(reply)) as client:
        assert linked.inspect("nvidia_nim", "fake-key", client)["models"]
    assert len(attempts) == 2
