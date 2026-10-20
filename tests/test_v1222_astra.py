"""12.2.2 Astra: Die Rechtspruefung mit Mistral und NVIDIA NIM -- zweiter Versuch und Ursache.

Gemeldet: Im Normal-Modus mit mistral-medium-latest kam nach einer Sekunde "das Modell fuer
die Pruefung hat nicht geantwortet". Der Aufruf beim Anbieter scheiterte, warum, verschluckte
die Pruefung. Jetzt: Lehnt der Anbieter das erzwungene JSON-Schema ab, fragt der Pruefer
dasselbe Modell noch einmal ohne Schema. Und die Absage nennt den Fehler -- ohne Schluessel
und ohne Adressen. Abgelehnt wird weiterhin, wenn gar kein Urteil kommt.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aquaticy import aiguard, guardrails, metering
from aquaticy.config import Settings

ERLAUBT = json.dumps({"zulaessig": True, "regel": "", "grund": "", "missbrauch": False,
                      "missbrauch_art": "", "missbrauch_schwere": 0})


class BadRequestError(Exception):
    """Wie litellm.BadRequestError: der Anbieter nimmt eine Angabe nicht an."""


class AuthenticationError(Exception):
    """Wie litellm.AuthenticationError."""


class APIConnectionError(Exception):
    """Wie litellm.APIConnectionError."""


def _mistral() -> Settings:
    return Settings(model="mistral/mistral-medium-latest", data_dir=Path(tempfile.mkdtemp()),
                    api_keys={"MISTRAL_API_KEY": "geheimer-mistral-schluessel"})


def _antwort(text: str) -> Any:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def _anbieter(monkeypatch: pytest.MonkeyPatch, fehler: Exception | None) -> list[dict[str, Any]]:
    """Ein nachgestellter Anbieter: mit Schema *fehler*, ohne Schema ein Urteil."""
    aufrufe: list[dict[str, Any]] = []

    def completion(settings: Any, *, enforce: bool = True, **kwargs: Any) -> Any:
        aufrufe.append(kwargs)
        if "response_format" in kwargs and fehler is not None:
            raise fehler
        return _antwort(ERLAUBT)

    monkeypatch.setattr(metering, "completion", completion)
    return aufrufe


@pytest.fixture(autouse=True)
def _echter_pruefer(monkeypatch: pytest.MonkeyPatch) -> None:
    """conftest stellt _ask_model; hier geht es um genau diese Funktion."""
    monkeypatch.setattr(guardrails, "_ask_model", ECHT)
    guardrails.forget_verdicts()


from tests.test_end_to_end import ECHTER_PRUEFER as ECHT  # noqa: E402


def test_a_rejected_schema_gets_a_second_try_without_it(monkeypatch) -> None:
    aufrufe = _anbieter(monkeypatch, BadRequestError("response_format json_schema invalid"))
    urteil = guardrails.judge("Wie viel Uhr ist es gerade in Berlin?", _mistral())
    assert urteil.allowed and urteil.source == "pruefer"
    assert [("response_format" in a) for a in aufrufe] == [True, False]
    assert {a["model"] for a in aufrufe} == {"mistral/mistral-small-latest"}


@pytest.mark.parametrize("fehler", [AuthenticationError("401"), APIConnectionError("weg"),
                                    TimeoutError("zu langsam")])
def test_no_second_try_where_it_cannot_help(monkeypatch, fehler: Exception) -> None:
    """Falscher Schluessel, kein Netz, abgelaufene Zeit: ohne Schema aendert das nichts."""
    aufrufe = _anbieter(monkeypatch, fehler)
    urteil = guardrails.judge("Wie viel Uhr ist es gerade in Berlin?", _mistral())
    assert not urteil.allowed and urteil.source == "ausfall"
    assert all("response_format" in a for a in aufrufe), "kein Versuch ohne Schema"
    assert len(aufrufe) == 2, "schnelles und Hauptmodell, je einmal"


def test_the_refusal_names_the_cause_without_secrets(monkeypatch) -> None:
    settings = _mistral()
    fehler = AuthenticationError(
        "Mistral: 401 Unauthorized for key geheimer-mistral-schluessel at "
        "https://api.mistral.ai/v1/chat/completions (Bearer abcdefgh12345) `x`")
    _anbieter(monkeypatch, fehler)
    urteil = guardrails.judge("Wie viel Uhr ist es gerade in Berlin?", settings)
    assert urteil.source == "ausfall"
    absage = guardrails.refusal_text(urteil)
    assert "nicht gegen den Rechtsrahmen prüfen" in absage, "die Absage bleibt"
    assert "Fehler: `mistral/mistral-medium-latest: AuthenticationError: Mistral: 401" in absage
    for geheim in ("geheimer-mistral-schluessel", "abcdefgh12345", "api.mistral.ai"):
        assert geheim not in absage
    assert "<Adresse>" in absage and absage.count("`") == 2
    assert guardrails.refusal_text(urteil, "en").startswith("I couldn't check")


def test_without_a_known_cause_the_old_text_stays() -> None:
    urteil = guardrails.Verdict(False, guardrails.GENERIC,
                                "Das Modell für die Prüfung hat nicht geantwortet.", "ausfall")
    assert "Fehler:" not in guardrails.refusal_text(urteil)


def test_a_garbled_answer_still_refuses(monkeypatch) -> None:
    """Abgeschwaecht wird nichts: ohne lesbares Urteil weiter die Absage."""
    monkeypatch.setattr(metering, "completion",
                        lambda settings, **kw: _antwort("Klar, mache ich!"))
    urteil = guardrails.judge("Wie viel Uhr ist es gerade in Berlin?", _mistral())
    assert not urteil.allowed and urteil.source == "unklar"


def test_error_text_is_short_and_clean() -> None:
    text = guardrails.error_text(ValueError("x " * 500 + "token=abc123 api_key: zzz"),
                                 _mistral(), "mistral/m")
    assert len(text) <= 240 and text.startswith("mistral/m: ValueError: ")
    voll = guardrails.error_text(ValueError("token=abc123 api_key: zzz"), _mistral(), "m")
    assert "abc123" not in voll and "zzz" not in voll
    assert guardrails.schema_retry_useful(BadRequestError("x"))
    assert not guardrails.schema_retry_useful(metering.QuotaExceeded("voll"))


def test_aiguard_retries_without_schema_too(monkeypatch) -> None:
    aufrufe = _anbieter(monkeypatch, BadRequestError("schema"))
    roh = aiguard._ask_one("Prüfe das", _mistral(), "mistral/mistral-small-latest")
    assert roh == ERLAUBT and [("response_format" in a) for a in aufrufe] == [True, False]
    _anbieter(monkeypatch, AuthenticationError("401"))
    with pytest.raises(AuthenticationError):
        aiguard._ask_one("Prüfe das", _mistral(), "mistral/mistral-small-latest")

