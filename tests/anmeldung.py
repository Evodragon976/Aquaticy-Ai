"""Anmelden wie die App (12.0.0 Terra): Browser-Kopfzeilen und der Nachweis aus dem Hintergrund.

Seit dem Anmeldeschutz (aquaticy/botguard.py) wird ein Client, der wie ein Skript
aussieht, vor dem Passwort gefragt oder abgewiesen. Tests, die nur die Anmeldung
brauchen und nicht den Schutz selbst pruefen, melden sich hiermit so an, wie es die
Seite im Browser tut: mit einem Browser als User-Agent, den Fetch-Metadaten und
einer im Hintergrund geloesten Rechenaufgabe.
"""

from __future__ import annotations

import itertools
from typing import Any

from aquaticy import botguard

AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
         "Chrome/130.0.0.0 Safari/537.36")
SPRACHE = "de-DE"

FETCH: dict[str, str] = {"Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "cors"}
BROWSER: dict[str, str] = {"User-Agent": AGENT, "Accept-Language": SPRACHE, **FETCH}


def loese(aufgabe: dict[str, Any]) -> dict[str, str]:
    """Die Loesung zu einer Aufgabe aus :func:`botguard.issue` -- wie im Browser."""
    for zahl in itertools.count():
        if botguard.solves(aufgabe["seed"], str(zahl), int(aufgabe["bits"])):
            return {"token": aufgabe["token"], "nonce": str(zahl)}
    raise AssertionError("unerreichbar")


def wie_die_app(body: dict[str, Any], client: Any = None) -> dict[str, Any]:
    """*body* plus Nachweis, so wie die Seite ihn zum Anmelden schickt.

    Ohne *client* stellt der Test die Aufgabe selbst (Server im selben Prozess);
    mit einem httpx-Client holt er sie wie die Seite von ``/api/auth/challenge``.
    """
    aufgabe = (client.get("/api/auth/challenge").json() if client is not None
               else botguard.issue("visit"))
    return {**body, "proof": loese(aufgabe), "webdriver": False}


def mensch(aufgabe: dict[str, Any]) -> dict[str, Any]:
    """Der bestandene Regler zu einer Aufgabe aus einer 428-Antwort."""
    weg = [[0, 0.0], [90, 0.08], [170, 0.22], [260, 0.41], [330, 0.6], [420, 0.77],
           [500, 0.9], [560, 1.0]]
    return {**loese(aufgabe), "track": weg}
