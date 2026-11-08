"""Die Messenger-Bruecke ueber die direkte Kopplung (12.7.8 Terra).

Nachrichten kommen als Ereignisse an, mit der echten Nummer des Absenders. Die Regeln sind
dieselben wie bei der Bruecke ueber den Bildschirm (aquaticy/bridge.py): wer antworten darf,
welche Dienste Aquaticy nutzen darf, keine Rueckfragen, Antworten mit "[Aquaticy]", Grenze je
Stunde. Unterschiede: Ein Titel kann nichts mehr vortaeuschen, und es gibt kein Vision-Modell.
"""

from __future__ import annotations

import collections
import contextlib
import hashlib
import logging
import threading
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
    delivery_allowed,
    denial_text,
    is_own_text,
    load_config,
    parse_command,
    remember,
    replies_left,
    reply_limit,
    service_allowed,
    strip_trigger,
    to_chat_text,
)
from aquaticy.messenger_native import MAX_AGE_SECONDS, Incoming

LOG = logging.getLogger("aquaticy.bridge_native")

FAIL_TEXT = f"{SIGNATURE} Das hat gerade nicht geklappt. Versuch es gleich noch einmal."

#: Laengere Nachrichten werden abgeschnitten, bevor sie ein Modell sieht.
MAX_INPUT_CHARS = 4000
#: "schreibt ..." haelt nur kurz (WhatsApp, Signal ca. 10 bis 15 Sekunden): alle paar Sekunden neu.
TYPING_REFRESH_SECONDS = 6.0
TYPING_MAX_SECONDS = 600.0
ACKED_KEEP = 500


def message_fingerprint(msg: Incoming) -> str:
    roh = f"{msg.messenger}|{msg.chat}|{msg.id}|{msg.sender}|{msg.ts}"
    return hashlib.sha256(roh.encode()).hexdigest()[:16]


COWORKER_REPLY_CHARS = 3000
#: Titel, die nichts sagen: Sie stehen nicht noch einmal in der Nachricht.
PLAIN_TITLES = frozenset({"", "meldung", "antwort", "frage", "freigabe"})


def coworker_text(name: str, titel: str, text: str, *, frage: bool = False,
                  freigabe: bool = False, auftrag: str = "") -> str:
    """Die Nachricht eines Coworkers im Messenger: "[Aquaticy Coworker Ava]", der Auftrag, Text.

    Seit 14.4.4 steht der Name in der Kennung und darunter, was man ihm aufgetragen hat.

    Gleiche Regeln wie bei jeder Antwort: kein Markdown, keine Zahlungsdaten, hoechstens
    COWORKER_REPLY_CHARS Zeichen (weniger als eine Nachricht fasst, damit nichts geteilt wird).
    """
    from aquaticy.desktop import payment_data

    name = "".join(z for z in str(name or "") if z.isprintable() and z not in "[]\n")
    if payment_data(name):  # Auch der Name in der Kennung darf keine Zahlungsdaten tragen.
        return to_chat_text("Darin stehen Zahlungsdaten. Die sende ich nicht.", wide=True,
                            signature="[Aquaticy Coworker Coworker]")
    kennung = f"[Aquaticy Coworker {name.strip()[:40] or 'Coworker'}]"
    titel = " ".join(str(titel or "").split())[:80]
    kopf = titel if titel.lower() not in PLAIN_TITLES else ""
    auftrag = " ".join(str(auftrag or "").split())[:300]
    if freigabe:
        koerper = "Wartet auf deine Freigabe. Öffne die App."
    elif payment_data(str(text or "")):
        koerper = "Darin stehen Zahlungsdaten. Die sende ich nicht."
    else:
        koerper = str(text or "").strip()
        if frage:
            koerper += "\n\nAntworten kannst du in der App."
    zeilen = ([f"Auftrag: {auftrag}"] if auftrag else []) + ([kopf] if kopf else []) + [koerper]
    message = to_chat_text("\n".join(zeilen), wide=True,
                           limit=COWORKER_REPLY_CHARS - len(kennung), signature=kennung)
    if payment_data(message):
        return to_chat_text("Darin stehen Zahlungsdaten. Die sende ich nicht.", wide=True,
                            signature="[Aquaticy Coworker Coworker]")
    return message


class TypingIndicator:
    """Zeigt im Chat "schreibt ...", solange gearbeitet wird -- und nimmt es danach weg.

    Sendet alle paar Sekunden neu, hoert nach spaetestens TYPING_MAX_SECONDS auf und scheitert
    nie hoerbar: Die Antwort geht vor.
    """

    def __init__(self, transport: Any, msg: Incoming, *,
                 interval: float = TYPING_REFRESH_SECONDS,
                 limit: float = TYPING_MAX_SECONDS) -> None:
        self._transport = transport
        self._msg = msg
        self._interval = interval
        self._limit = limit
        self._halt = threading.Event()
        self._lock = threading.Lock()
        self._done = False
        self._thread: threading.Thread | None = None

    def _send(self, on: bool) -> None:
        with self._lock:
            if on and self._done:
                return
        # Ausserhalb der Sperre: Haengt die Verbindung, wartet die Antwort nicht darauf.
        with contextlib.suppress(Exception):
            self._transport.typing(self._msg, on)

    def _loop(self) -> None:
        ende = time.monotonic() + self._limit
        while not self._halt.wait(self._interval):
            if time.monotonic() >= ende:
                return
            self._send(True)

    def __enter__(self) -> TypingIndicator:
        self._send(True)
        self._thread = threading.Thread(target=self._loop, name="aquaticy-schreibt", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self._halt.set()
        with self._lock:
            self._done = True
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._send(False)


class NativeResponder:
    """Beantwortet eine Nachricht -- oder tut nichts. Gibt den Grund zurueck (fuer Tests)."""

    def __init__(self, settings_getter: Callable[[], Any], answerer: Callable[..., str], *,
                 paused: Callable[[], bool] | None = None,
                 clock: Callable[[], float] = time.time,
                 orders: Callable[[str], str | None] | None = None) -> None:
        self._settings = settings_getter
        self._answerer = answerer
        # Auftraege an Secure Pro und Coworker (14.4.4): nur im eigenen Chat des Besitzers.
        self._orders = orders
        self._paused = paused
        self._clock = clock
        self._acked: collections.OrderedDict[str, None] = collections.OrderedDict()
        self._acked_lock = threading.Lock()

    def _screen(self, msg: Incoming, config: dict[str, Any],
                dedupe: Callable[[], bool] | None) -> tuple[str, Any, str]:
        """Alle Pruefungen bis zur Entscheidung. Returns: (Grund, Entscheidung, Auftrag).

        Ein Grund heisst: nichts tun. Ohne *dedupe* hinterlaesst die Pruefung keine Spur.
        """
        if not config["an"]:
            return "aus", None, ""
        if self._paused is not None and self._paused():
            return "pausiert", None, ""
        text = (msg.text or "").strip()[:MAX_INPUT_CHARS]
        if not text or is_own_text(text):
            return "eigene", None, ""
        if msg.from_me and not msg.self_chat:
            return "eigene", None, ""  # der Besitzer schreibt anderen vom Handy aus
        if msg.ts and self._clock() - msg.ts > MAX_AGE_SECONDS:
            return "zu alt", None, ""  # nach einer Pause kommt Aelteres nach
        decision = decide_native(config, group=msg.group, self_chat=msg.self_chat,
                                 number=msg.sender)
        if not decision.allow:
            return f"abgelehnt: {decision.why}", None, ""
        if msg.audio is not None:
            from aquaticy import voice

            if not decision.trusted or decision.group or not voice.enabled():
                return "Sprachnachrichten nicht freigegeben", None, ""
        auftrag = strip_trigger(text, decision.group)
        if not auftrag:
            return "keine Aufgabe", None, ""
        if dedupe is not None and not dedupe():
            return "doppelt", None, ""
        return "", decision, auftrag

    def acknowledge(self, msg: Incoming, transport: Any) -> str:
        """Zeigt dem Absender "gelesen" -- sofort, auch wenn Aquaticy noch eine andere Nachricht
        beantwortet. Nur fuer Nachrichten, die Aquaticy auch beantwortet (kein Haken fuer
        Fremde, die abgelehnt werden: Sie sollen nicht merken, dass hier jemand mitliest).
        """
        settings = self._settings()
        config = load_config(settings)[msg.messenger]
        grund, _, _ = self._screen(msg, config, None)
        if grund:
            return grund
        if replies_left(StateStore(settings), msg.messenger, self._clock()) <= 0:
            return "grenze"
        self._mark_read(msg, transport)
        return "gelesen"

    def _mark_read(self, msg: Incoming, transport: Any) -> None:
        fp = message_fingerprint(msg)
        with self._acked_lock:
            if fp in self._acked:
                return
            self._acked[fp] = None
            while len(self._acked) > ACKED_KEEP:
                self._acked.popitem(last=False)
        try:
            transport.mark_read(msg)
        except Exception:
            with self._acked_lock:
                self._acked.pop(fp, None)

    def __call__(self, msg: Incoming, transport: Any) -> str:
        from aquaticy import voice

        settings = self._settings()
        config = load_config(settings)[msg.messenger]
        store = StateStore(settings)
        grund, decision, auftrag = self._screen(
            msg, config, lambda: self._first_time(store, msg))
        if grund:
            return grund
        if replies_left(store, msg.messenger, self._clock()) <= 0:
            return "grenze"
        key = chat_key(msg.messenger, msg.chat)
        self._mark_read(msg, transport)
        try:
            with TypingIndicator(transport, msg):
                antwort = self._reply(auftrag, decision, config, key, msg, transport)
                if antwort is None:
                    return "eigene"
        except Exception:
            LOG.exception("Die Antwort an einen %s-Chat ist fehlgeschlagen", msg.messenger)
            if decision.trusted and delivery_allowed(
                    self._settings, msg.messenger, config, self._paused):
                self._send(transport, msg, FAIL_TEXT)
                count_reply(store, msg.messenger, self._clock())
            return "fehler"
        if not delivery_allowed(self._settings, msg.messenger, config, self._paused):
            return "widerrufen"
        if not self._send(transport, msg, antwort, config=config,
                          audio=decision.trusted and (msg.audio is not None or
                          voice.requested(auftrag))):
            return "widerrufen"
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
               msg: Incoming, transport: Any = None) -> str | None:
        from aquaticy.ownservices import own_sources

        if msg.audio is not None:
            from aquaticy import voice

            data = transport.voice_download(msg)
            if (msg.from_me and hashlib.sha256(data).digest()
                    in getattr(transport, "_sent_audio", ())):
                return None
            auftrag = voice.transcribe(data)
            if not voice.enabled() or not delivery_allowed(
                    self._settings, msg.messenger, config, self._paused):
                raise ValueError("Freigabe geändert.")

        if self._orders is not None and decision.selbst and not decision.group:
            fertig = self._orders(auftrag)
            if fertig is not None:
                return fertig
        # Ein Befehl ("/code-review ...") hat eigene Regeln; Codeschnipsel sind keine Mailfrage.
        befehl = parse_command(auftrag) is not None
        fehlend = [] if befehl else [q for q in own_sources(auftrag) if not service_allowed(
            config, decision.trusted, SOURCE_SERVICE[q])]
        if fehlend:
            antwort = denial_text(msg.messenger, fehlend, decision.trusted)
        else:
            antwort = self._answerer(auftrag, decision, config, key, msg.messenger)
        text = to_chat_text(antwort, wide=True, limit=reply_limit(auftrag))
        from aquaticy.desktop import payment_data

        if payment_data(text):
            return f"{SIGNATURE} Darin stehen Zahlungsdaten. Die sende ich nicht."
        return text

    def _send(self, transport: Any, msg: Incoming, text: str, *,
              config: dict[str, Any] | None = None, audio: bool = False) -> bool:
        data = b""
        if audio:
            from aquaticy import voice

            if voice.enabled():
                try:
                    data = voice.synthesize(text)
                except Exception:
                    LOG.warning("Sprachausgabe fehlgeschlagen; sende Text.")
        if config is not None and not delivery_allowed(
                self._settings, msg.messenger, config, self._paused):
            return False
        transport.send(msg.chat, text)
        if data and config is not None and delivery_allowed(
                self._settings, msg.messenger, config, self._paused):
            from aquaticy import voice

            if not voice.enabled():
                return True
            try:
                transport.voice_send(msg.chat, data)
            except Exception:
                LOG.warning("Sprachnachricht konnte nicht gesendet werden; Text wurde gesendet.")
        return True
