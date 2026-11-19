"""Bound nesting before decoding JSON received over the network."""

from __future__ import annotations

import json
import math
import re
from typing import Any

MAX_DEPTH = 64
_STRUCTURE = re.compile(r'\\.|"|[\[\]{}]')


def _constant(value: str) -> Any:
    raise ValueError("JSON enthält keinen gültigen Zahlenwert: " + value)


def _number(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Die JSON-Zahl ist nicht darstellbar.")
    return result


_DECODER = json.JSONDecoder(parse_constant=_constant, parse_float=_number)


class JsonDepthError(ValueError):
    """A request exceeds the bounded JSON container depth."""


def loads(raw: bytes | str) -> Any:
    """Keep standard JSON syntax and encodings, with a fixed depth ceiling.

    Escaped quotes and brackets in strings are data. Check before decoding so
    neither Python's recursion limit nor a third-party change to it controls
    the amount of nesting a network peer can submit.
    """
    text = raw.decode(json.detect_encoding(raw), "surrogatepass") if isinstance(raw, bytes) else raw
    quoted = False
    depth = 0
    for match in _STRUCTURE.finditer(text):
        token = match.group()
        if token == '"':
            quoted = not quoted
        elif not quoted:
            if token in ("[", "{"):
                depth += 1
                if depth > MAX_DEPTH:
                    raise JsonDepthError("Die Anfrage ist zu stark verschachtelt.")
            elif token in ("]", "}"):
                depth -= 1
    return ohne_surrogate(json.loads(text, parse_constant=_constant, parse_float=_number))


_SURROGAT = re.compile("[\ud800-\udfff]")


def ohne_surrogate(wert: Any) -> Any:
    """Einzelne Surrogate ("\\ud800" im JSON) werden zu U+FFFD.

    Python liest sie als Text ein, kann sie aber nicht als UTF-8 schreiben: Vorher liess
    sich eine solche Nachricht weder im Verlauf speichern noch an den Browser senden.
    Paare ("\\ud83d\\ude00") setzt json.loads schon zu einem Zeichen zusammen (16.4.5).
    """
    if isinstance(wert, str):
        return _SURROGAT.sub("\ufffd", wert) if _SURROGAT.search(wert) else wert
    if isinstance(wert, list):
        return [ohne_surrogate(w) for w in wert]
    if isinstance(wert, dict):
        return {ohne_surrogate(k): ohne_surrogate(v) for k, v in wert.items()}
    return wert


def raw_decode(raw: str, index: int = 0) -> tuple[Any, int]:
    """Decode one bounded value, retaining concatenated tool-call support."""
    if raw[index:index + 1] not in ("[", "{"):
        return _DECODER.raw_decode(raw, index)
    quoted = False
    depth = 0
    for match in _STRUCTURE.finditer(raw, index):
        token = match.group()
        if token == '"':
            quoted = not quoted
        elif not quoted:
            if token in ("[", "{"):
                depth += 1
                if depth > MAX_DEPTH:
                    raise JsonDepthError("Die Anfrage ist zu stark verschachtelt.")
            elif token in ("]", "}"):
                depth -= 1
                if depth == 0:
                    end = match.end()
                    return loads(raw[index:end]), end

    return loads(raw[index:]), len(raw)
