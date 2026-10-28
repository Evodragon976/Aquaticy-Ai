"""Die Messenger-Bruecke ueber die direkte Kopplung (12.7.8 Terra).

Nachrichten kommen als Ereignisse an, mit der echten Nummer des Absenders. Die Regeln sind
dieselben wie bei der Bruecke ueber den Bildschirm (aquaticy/bridge.py): wer antworten darf,
welche Dienste Aquaticy nutzen darf, keine Rueckfragen, Antworten mit "[Aquaticy]", Grenze je
Stunde. Unterschiede: Ein Titel kann nichts mehr vortaeuschen, und es gibt kein Vision-Modell.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from typing import Any

from aquaticy.bridge import (
    MAX_SEEN,
    SIGNATURE,
    SOURCE_SERVICE,
    StateStore,
    chat_key,
    count_reply,
    decide_native,
    denial_text,
    is_own_text,
    load_config,
    remember,
    replies_left,
    service_allowed,
    strip_trigger,
    to_chat_text,
)
from aquaticy.messenger_native import MAX_AGE_SECONDS, Incoming

LOG = logging.getLogger("aquaticy.bridge_native")

FAIL_TEXT = f"{SIGNATURE} Das hat gerade nicht geklappt. Versuch es gleich noch einmal."


def message_fingerprint(msg: Incoming) -> str:
    roh = f"{msg.messenger}|{msg.chat}|{msg.id}|{msg.sender}|{msg.ts}"
    return hashlib.sha256(roh.encode()).hexdigest()[:16]


class NativeResponder:
    """Beantwortet eine Nachricht -- oder tut nichts. Gibt den Grund zurueck (fuer Tests)."""

    def __init__(self, settings_getter: Callable[[], Any], answerer: Callable[..., str], *,
                 paused: Callable[[], bool] | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self._settings = settings_getter
        self._answerer = answerer
        self._paused = paused
        self._clock = clock

    def __call__(self, msg: Incoming, transport: Any) -> str:
        settings = self._settings()
        config = load_config(settings)[msg.messenger]
        if not config["an"]:
            return "aus"
        if self._paused is not None and self._paused():
            return "pausiert"
        text = (msg.text or "").strip()
        if not text or is_own_text(text):
            return "eigene"
        if msg.from_me and not msg.self_chat:
            return "eigene"  # der Besitzer schreibt anderen vom Handy aus -- das ist nicht fuer uns
        if msg.ts and self._clock() - msg.ts > MAX_AGE_SECONDS:
            return "zu alt"  # nach einer Pause kommt Aelteres nach: das beantwortet niemand mehr
        store = StateStore(settings)
        if not self._first_time(store, msg):
            return "doppelt"
        decision = decide_native(config, group=msg.group, self_chat=msg.self_chat,
                                 number=msg.sender)
        if not decision.allow:
            return f"abgelehnt: {decision.why}"
        auftrag = strip_trigger(text, decision.group)
        if not auftrag:
            return "keine Aufgabe"
        if replies_left(store, msg.messenger, self._clock()) <= 0:
            return "grenze"
        key = chat_key(msg.messenger, msg.chat)
        try:
            antwort = self._reply(auftrag, decision, config, key, msg)
        except Exception:
            LOG.exception("Die Antwort an einen %s-Chat ist fehlgeschlagen", msg.messenger)
            if decision.trusted:
                self._send(transport, msg, FAIL_TEXT)
            return "fehler"
        self._send(transport, msg, antwort)
        count_reply(store, msg.messenger, self._clock())
        return "beantwortet"

    def _first_time(self, store: StateStore, msg: Incoming) -> bool:
        fp = message_fingerprint(msg)
        neu: list[bool] = []

        def aendern(stand: dict[str, Any]) -> None:
            liste = [x for x in stand.get("native_gesehen", []) if isinstance(x, str)]
            neu.append(fp not in liste)
            remember(liste, fp)
            del liste[:-MAX_SEEN]
            stand["native_gesehen"] = liste

        store.update(msg.messenger, aendern)
        return bool(neu and neu[0])

    def _reply(self, auftrag: str, decision: Any, config: dict[str, Any], key: str,
               msg: Incoming) -> str:
        from aquaticy.ownservices import own_sources

        fehlend = [q for q in own_sources(auftrag) if not service_allowed(
            config, decision.trusted, SOURCE_SERVICE[q])]
        if fehlend:
            antwort = denial_text(msg.messenger, fehlend, decision.trusted)
        else:
            antwort = self._answerer(auftrag, decision, config, key, msg.messenger)
        text = to_chat_text(antwort, wide=True)
        from aquaticy.desktop import payment_data

        if payment_data(text):
            return f"{SIGNATURE} Darin stehen Zahlungsdaten. Die sende ich nicht."
        return text

    @staticmethod
    def _send(transport: Any, msg: Incoming, text: str) -> None:
        transport.send(msg.chat, text)
