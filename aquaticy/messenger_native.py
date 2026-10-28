"""WhatsApp und Signal direkt koppeln -- ohne virtual machine und ohne Browser (12.7.8 Terra).

Aquaticy wird wie das Handy-Programm ein "gekoppeltes Geraet": Es zeigt einen QR-Code, du
scannst ihn mit dem Handy, danach kommen Nachrichten als Ereignisse an. WhatsApp laeuft ueber
neonize (whatsmeow), Signal ueber das Programm signal-cli. Beides sind inoffizielle Wege.

Dieses Modul bewegt nur Nachrichten: koppeln, empfangen, senden. Wer antworten darf und was
Aquaticy dabei tun darf, entscheidet allein aquaticy/bridge_native.py.
"""

from __future__ import annotations

import collections
import contextlib
import functools
import importlib
import json
import logging
import os
import queue
import re
import secrets
import shutil
import subprocess  # nosec B404
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOG = logging.getLogger("aquaticy.messenger_native")

MESSENGERS = ("whatsapp", "signal")
NAMES = {"whatsapp": "WhatsApp", "signal": "Signal"}
DEVICE_NAME = "Aquaticy"

#: Zustaende der Verbindung.
OFF, STARTING, QR, CONNECTED, FAILED = "aus", "startet", "qr", "verbunden", "fehler"

MESSAGE_ID_RE = re.compile(r"[0-9A-Za-z_.-]{3,64}")
MAX_SEND_CHARS = 3800
QR_MAX_CHARS = 4096
LINK_TIMEOUT = 240.0
MAX_AGE_SECONDS = 300.0
QUEUE_SIZE = 20
SETTLE_SECONDS = 15.0
NOTIFY_PER_HOUR = 30
NOTIFY_QUEUE = 10
NOTIFY_KEEP_SECONDS = 3600.0

NUMBER_RE = re.compile(r"\+[0-9]{6,15}")
GROUP_ID_RE = re.compile(r"[A-Za-z0-9+/=_-]{8,120}")
JID_RE = re.compile(r"[0-9A-Za-z._:-]{1,64}@(?:s\.whatsapp\.net|g\.us|lid)")
SIGNAL_URI = re.compile(rf"^(?:sgnl|tsdevice):[^\s]{{10,{QR_MAX_CHARS}}}$")


# ---------------------------------------------------------------------------
# Daten
# ---------------------------------------------------------------------------
@dataclass
class Incoming:
    """Eine eingegangene Nachricht -- mit der echten Nummer, nicht mit einem Namen."""

    messenger: str
    chat: str  # womit geantwortet wird (WhatsApp: JID, Signal: Nummer, "self" oder "group:ID")
    text: str
    id: str
    ts: float
    sender: str = ""  # "+491512345678" oder "" (unbekannt, etwa eine WhatsApp-LID)
    group: bool = False
    from_me: bool = False
    self_chat: bool = False  # "Nachricht an dich selbst"
    name: str = ""
    #: Nur fuer "gelesen": WhatsApp-Kennung des Absenders (in Gruppen) und Signal-Zeitstempel.
    sender_id: str = field(default="", compare=False)
    stamp: int = field(default=0, compare=False)


@dataclass
class LinkStatus:
    """Wie weit die Kopplung ist."""

    state: str = OFF
    qr: str = ""
    who: str = ""
    error: str = ""
    since: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


def digits(text: Any) -> str:
    return re.sub(r"\D", "", str(text or ""))


def clean_number(text: Any) -> str:
    """Eine Telefonnummer als "+49..." -- oder "" (nur geprueft, nie geraten)."""
    roh = str(text or "").strip()
    nummer = "+" + digits(roh) if roh.startswith("+") else ""
    return nummer if NUMBER_RE.fullmatch(nummer) else ""


# ---------------------------------------------------------------------------
# Was gekoppelt ist: eine kleine Datei je Konto (keine Zugangsdaten darin)
# ---------------------------------------------------------------------------
_FILE_LOCK = threading.Lock()


class NativeStore:
    """Merkt sich, mit wem gekoppelt ist. Die Sitzungsdaten selbst liegen in Unterordnern."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    @property
    def path(self) -> Path:
        return self.directory / "native.json"

    def _read(self) -> dict[str, Any]:
        try:
            wert = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return wert if isinstance(wert, dict) else {}

    def who(self, messenger: str) -> str:
        eintrag = self._read().get(messenger)
        return str(eintrag.get("who", "")) if isinstance(eintrag, dict) else ""

    def linked(self, messenger: str) -> bool:
        return bool(self.who(messenger))

    def set(self, messenger: str, who: str) -> None:
        with _FILE_LOCK:
            alle = self._read()
            alle[messenger] = {"who": str(who)[:40], "at": int(time.time())}
            self._write(alle)

    def clear(self, messenger: str) -> None:
        with _FILE_LOCK:
            alle = self._read()
            if alle.pop(messenger, None) is not None:
                self._write(alle)

    def _write(self, alle: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(alle, ensure_ascii=False, indent=1), encoding="utf-8")
        with contextlib.suppress(OSError):
            tmp.chmod(0o600)
        tmp.replace(self.path)


def native_dir(settings: Any) -> Path:
    """Wo ein Konto seine Kopplungen ablegt: <Datenordner>/messenger (nur fuer den Besitzer)."""
    ordner = Path(getattr(settings, "data_dir", None) or ".") / "messenger"
    ordner.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        ordner.chmod(0o700)
    return ordner


def linked(settings: Any, messenger: str) -> bool:
    """Ist dieses Konto direkt (ohne virtual machine) mit dem Messenger gekoppelt?"""
    if messenger not in MESSENGERS:
        return False
    return NativeStore(Path(getattr(settings, "data_dir", None) or ".") / "messenger").linked(
        messenger)


# ---------------------------------------------------------------------------
# Nachrichten lesen
# ---------------------------------------------------------------------------
def _seconds(stamp: Any) -> float:
    try:
        wert = float(stamp)
    except (TypeError, ValueError):
        return 0.0
    return wert / 1000.0 if wert > 1e11 else wert


def _jid_text(jid: Any) -> str:
    user, server = str(getattr(jid, "User", "") or ""), str(getattr(jid, "Server", "") or "")
    return f"{user}@{server}" if user and server else ""


def parse_whatsapp(event: Any, own: set[str]) -> Incoming | None:
    """Macht aus einem neonize-Ereignis eine Nachricht -- oder None, wenn es keine Frage ist.

    Args:
        own: Die eigenen Kennungen (Nummer und LID), nur Ziffern -- fuer "Nachricht an mich".
    """
    info = event.Info
    quelle = info.MessageSource
    chat, sender = quelle.Chat, quelle.Sender
    server = str(chat.Server or "")
    if server not in {"s.whatsapp.net", "g.us", "lid"}:
        return None  # Broadcast, Status, Newsletter: dort antwortet Aquaticy nie
    if getattr(event, "IsEdit", False):
        return None
    nachricht = event.Message
    text = str(nachricht.conversation or nachricht.extendedTextMessage.text or "")
    if not text.strip():
        return None
    gruppe = bool(quelle.IsGroup) or server == "g.us"
    von_mir = bool(quelle.IsFromMe)
    chat_id = _jid_text(chat)
    if not JID_RE.fullmatch(chat_id):
        return None
    sender_id = _jid_text(sender)
    eigener_chat = (not gruppe and von_mir and str(chat.User) in own)
    nummer = ""
    if not von_mir:
        alt = quelle.SenderAlt
        if str(alt.Server) == "s.whatsapp.net" and alt.User:
            nummer = "+" + digits(alt.User)
        elif str(sender.Server) == "s.whatsapp.net" and sender.User:
            nummer = "+" + digits(sender.User)
        if not NUMBER_RE.fullmatch(nummer):
            nummer = ""
    return Incoming(
        messenger="whatsapp", chat=chat_id, text=text, id=str(info.ID or ""),
        ts=_seconds(info.Timestamp), sender=nummer, group=gruppe, from_me=von_mir,
        self_chat=eigener_chat, name=str(info.Pushname or "")[:60],
        sender_id=sender_id if JID_RE.fullmatch(sender_id) else "")


def parse_signal(params: Any, own_number: str) -> Incoming | None:
    """Macht aus einer "receive"-Meldung von signal-cli eine Nachricht -- oder None."""
    if not isinstance(params, dict):
        return None
    huelle = params.get("envelope")
    if not isinstance(huelle, dict):
        return None
    zeit = huelle.get("timestamp")
    quelle = clean_number(huelle.get("sourceNumber") or huelle.get("source"))
    daten = huelle.get("dataMessage")
    sync = (huelle.get("syncMessage") or {}).get("sentMessage") if isinstance(
        huelle.get("syncMessage"), dict) else None
    von_mir = False
    if isinstance(daten, dict):
        inhalt = daten
    elif isinstance(sync, dict):
        inhalt, von_mir = sync, True
    else:
        return None
    text = str(inhalt.get("message") or "")
    if not text.strip():
        return None
    gruppe_info = inhalt.get("groupInfo")
    gruppe_id = str(gruppe_info.get("groupId") or "") if isinstance(gruppe_info, dict) else ""
    if gruppe_id and not GROUP_ID_RE.fullmatch(gruppe_id):
        return None
    if von_mir:
        ziel = clean_number(inhalt.get("destinationNumber") or inhalt.get("destination"))
        eigener = not gruppe_id and bool(ziel) and ziel == own_number
        chat = f"group:{gruppe_id}" if gruppe_id else ("self" if eigener else ziel)
        nummer = own_number
    else:
        eigener = False
        if not quelle:
            return None
        chat = f"group:{gruppe_id}" if gruppe_id else quelle
        nummer = quelle
    if not chat:
        return None
    return Incoming(
        messenger="signal", chat=chat, text=text, id=f"{zeit}:{nummer}",
        ts=_seconds(zeit), sender=nummer, group=bool(gruppe_id), from_me=von_mir,
        self_chat=eigener, name=str(huelle.get("sourceName") or "")[:60],
        stamp=zeit if isinstance(zeit, int) and not isinstance(zeit, bool) and zeit > 0 else 0)


#: Jeder Teil einer geteilten Antwort beginnt mit der Kennung (bridge.SIGNATURE). Sonst hielte
#: Aquaticy die weiteren Teile im eigenen Chat fuer Befehle des Besitzers und antwortete darauf.
SIGNATURE = "[Aquaticy]"


def message_parts(text: str) -> list[str]:
    teile = split_text(text)
    return [t if i == 0 else f"{SIGNATURE} {t}" for i, t in enumerate(teile)]


def split_text(text: str, limit: int = MAX_SEND_CHARS) -> list[str]:
    """Teilt einen langen Text an Zeilen- oder Wortgrenzen."""
    text = str(text or "").strip()
    teile: list[str] = []
    while len(text) > limit:
        schnitt = max(text.rfind("\n", 0, limit), text.rfind(" ", 0, limit))
        schnitt = schnitt if schnitt > limit // 2 else limit
        teile.append(text[:schnitt].rstrip())
        text = text[schnitt:].lstrip()
    if text:
        teile.append(text)
    return teile


# ---------------------------------------------------------------------------
# Die Verbindung
# ---------------------------------------------------------------------------
class Transport:
    """Gemeinsamer Teil: Zustand, Sperre, Nachrichtenweg."""

    messenger = ""

    def __init__(self, directory: Path, on_message: Callable[[Incoming], None],
                 on_connected: Callable[[], None] | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.directory = Path(directory)
        self.store = NativeStore(self.directory)
        self._on_message = on_message
        self._on_connected = on_connected
        self._clock = clock
        self._lock = threading.RLock()
        self._status = LinkStatus(since=clock())
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    # -- Zustand -----------------------------------------------------------
    def status(self) -> LinkStatus:
        with self._lock:
            s = self._status
            return LinkStatus(s.state, s.qr, s.who, s.error, s.since, dict(s.extra))

    def _set(self, state: str, *, qr: str = "", who: str | None = None, error: str = "") -> None:
        with self._lock:
            alt = self._status
            self._status = LinkStatus(
                state, qr[:QR_MAX_CHARS] if state == QR else "",
                alt.who if who is None else who, error[:300], self._clock(), alt.extra)
        if state == CONNECTED and self._on_connected is not None:
            with contextlib.suppress(Exception):
                self._on_connected()

    @property
    def running(self) -> bool:
        thread = self._thread
        return bool(thread is not None and thread.is_alive())

    def _finish_stale(self) -> None:
        """Wartet, bis ein angehaltener Lauf wirklich zu Ende ist (nicht unter der Sperre).

        Ohne das startet ein neuer Lauf nie: Der alte Faden gilt bis zu seinem Ende als laufend.
        """
        faden = self._thread
        if (faden is not None and faden is not threading.current_thread()
                and faden.is_alive() and self._stopping.is_set()):
            faden.join(timeout=10)

    @property
    def directory_for_session(self) -> Path:
        return self.directory / self.messenger

    def has_session(self) -> bool:
        return self.store.linked(self.messenger)

    # -- zu ueberschreiben ---------------------------------------------------
    def available(self) -> tuple[bool, str]:  # pragma: no cover - abstrakt
        raise NotImplementedError

    def start(self) -> None:  # pragma: no cover - abstrakt
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - abstrakt
        raise NotImplementedError

    def unlink(self) -> None:  # pragma: no cover - abstrakt
        raise NotImplementedError

    def send(self, chat: str, text: str) -> None:  # pragma: no cover - abstrakt
        raise NotImplementedError

    def own_chat(self) -> str:
        """Der eigene Chat des Besitzers ("Nachricht an dich selbst") -- oder "" (unbekannt)."""
        return ""

    def mark_read(self, nachricht: Incoming) -> None:
        """Zeigt dem Absender "gelesen" (die Haken). Nur ein Versuch, nie ein Fehler."""

    def typing(self, nachricht: Incoming, on: bool) -> None:
        """Zeigt dem Chat "schreibt ..." (an) oder nimmt es weg (aus). Nur ein Versuch."""

    def _deliver(self, nachricht: Incoming | None) -> None:
        if nachricht is not None:
            try:
                self._on_message(nachricht)
            except Exception:
                LOG.exception("%s: Nachricht konnte nicht verarbeitet werden", self.messenger)

    def _wipe_session(self) -> None:
        shutil.rmtree(self.directory_for_session, ignore_errors=True)
        self.store.clear(self.messenger)


NEED_LIBMAGIC = ("WhatsApp braucht noch die Bibliothek libmagic. Führe auf dem Rechner "
                 "„aquaticy install-messenger“ aus. Starte Aquaticy danach neu.")
NEED_NEONIZE = ("WhatsApp braucht noch das Paket neonize. Installiere Aquaticy neu oder führe "
                "„pip install neonize“ aus. Starte Aquaticy danach neu.")
NEED_SIGNAL_CLI = ("Signal braucht noch das Programm signal-cli. Führe auf dem Rechner "
                   "„aquaticy install-messenger“ aus.")


@functools.lru_cache(maxsize=1)
def neonize_available() -> tuple[bool, str]:
    """Ist neonize (samt libmagic) da? Das Ergebnis gilt, bis Aquaticy neu startet."""
    try:
        import neonize.client  # noqa: F401  # nosec B401
    except Exception as exc:  # fehlendes Paket oder fehlende Systembibliothek (libmagic)
        LOG.info("neonize nicht nutzbar: %s", exc)
        return False, NEED_LIBMAGIC if "magic" in str(exc).lower() else NEED_NEONIZE
    return True, ""


class WhatsAppTransport(Transport):
    """WhatsApp ueber neonize (whatsmeow). Das Paket wird erst beim Gebrauch importiert."""

    messenger = "whatsapp"

    def __init__(self, *args: Any, client_factory: Callable[[str, str], Any] | None = None,
                 events: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._factory = client_factory
        self._events = events  # Tests: eigene Ereignisklassen statt neonize.events
        self._client: Any = None

    def available(self) -> tuple[bool, str]:
        if self._factory is not None:
            return True, ""
        return neonize_available()

    def _make_client(self) -> Any:
        sitzung = self.directory_for_session
        sitzung.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            sitzung.chmod(0o700)
        ziel = str(sitzung / "session.sqlite3")
        # Jede Verbindung bekommt eine eigene Kennung: Beim Aufraeumen eines alten Clients
        # ruft neonize Stop(kennung) -- mit gleicher Kennung stoppte das den neuen.
        kennung = f"aquaticy-{secrets.token_hex(6)}"
        if self._factory is not None:
            return self._factory(ziel, kennung)
        from neonize.client import NewClient

        return NewClient(ziel, uuid=kennung)

    def start(self) -> None:
        self._finish_stale()
        with self._lock:
            if self.running:
                return
            self._stopping.clear()
            self._set(STARTING)
            self._thread = threading.Thread(target=self._run, name="aquaticy-whatsapp",
                                            daemon=True)
            self._thread.start()

    def _own(self, client: Any) -> set[str]:
        ich = getattr(client, "me", None)
        kennungen = set()
        for feld in ("JID", "LID"):
            jid: Any = getattr(ich, feld, None)
            benutzer = getattr(jid, "User", "") if jid is not None else ""
            if benutzer:
                kennungen.add(str(benutzer))
        return kennungen

    def _run(self) -> None:
        try:
            ereignisse = self._events
            if ereignisse is None:
                ereignisse = importlib.import_module("neonize.events")
            ConnectedEv, LoggedOutEv = ereignisse.ConnectedEv, ereignisse.LoggedOutEv
            MessageEv, PairStatusEv = ereignisse.MessageEv, ereignisse.PairStatusEv

            client = self._make_client()
            self._client = client

            @client.qr
            def _on_qr(_: Any, data: Any) -> None:
                text = data.decode("ascii", "replace") if isinstance(data, bytes) else str(data)
                self._set(QR, qr=text)

            @client.event(PairStatusEv)
            def _on_pair(_: Any, ereignis: Any) -> None:
                # SUCCESS steht im Ereignis selbst (neonize zaehlt ab 2, nicht ab 1).
                if getattr(ereignis, "Status", None) == getattr(ereignis, "SUCCESS", 1):
                    nummer = "+" + digits(getattr(ereignis.ID, "User", ""))
                    if NUMBER_RE.fullmatch(nummer):
                        self.store.set("whatsapp", nummer)
                        self._set(STARTING, who=nummer)
                else:
                    self._set(FAILED, error="Das Koppeln hat nicht geklappt. Versuch es erneut.")

            @client.event(ConnectedEv)
            def _on_connected(_: Any, __: Any) -> None:
                nummer = self.store.who("whatsapp")
                if not nummer:
                    ich = getattr(client, "me", None)
                    jid = getattr(ich, "JID", None)
                    nummer = "+" + digits(getattr(jid, "User", ""))
                    if NUMBER_RE.fullmatch(nummer):
                        self.store.set("whatsapp", nummer)
                    else:
                        nummer = ""
                self._set(CONNECTED, who=nummer)

            weg = getattr(ereignisse, "DisconnectedEv", None)
            if weg is not None:
                @client.event(weg)
                def _on_disconnected(_: Any, __: Any) -> None:
                    # whatsmeow verbindet selbst neu und meldet dann wieder "verbunden".
                    if not self._stopping.is_set() and self.status().state == CONNECTED:
                        self._set(STARTING)

            @client.event(LoggedOutEv)
            def _on_logged_out(_: Any, __: Any) -> None:
                self._wipe_session()
                self._set(FAILED, error="WhatsApp hat die Kopplung beendet (am Handy abgemeldet).")

            @client.event(MessageEv)
            def _on_message(_: Any, ereignis: Any) -> None:
                self._deliver(parse_whatsapp(ereignis, self._own(client)))

            client.connect()
            if not self._stopping.is_set() and self.status().state not in (FAILED,):
                self._set(OFF)
        except Exception as exc:
            if self._stopping.is_set():
                return
            LOG.warning("WhatsApp: %s", exc)
            self._set(FAILED, error=_plain_error(exc, "WhatsApp"))

    def stop(self) -> None:
        self._stopping.set()
        client = self._client
        if client is not None:
            # neonize: disconnect() trennt nur die Leitung. Erst stop() beendet den Aufruf
            # connect() -- sonst bleibt der Faden haengen und ein neuer Start tut nichts mehr.
            with contextlib.suppress(Exception):
                client.disconnect()
            with contextlib.suppress(Exception):
                client.stop()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=10)
        self._client = None
        self._set(OFF, who=self.store.who("whatsapp"))

    def unlink(self) -> None:
        client = self._client
        if client is not None:
            with contextlib.suppress(Exception):
                client.logout()
        self.stop()
        self._wipe_session()
        self._set(OFF, who="")

    def send(self, chat: str, text: str) -> None:
        if not JID_RE.fullmatch(str(chat)):
            raise ValueError("Ungueltiger Chat.")
        client = self._client
        if client is None or self.status().state != CONNECTED:
            raise RuntimeError("WhatsApp ist nicht verbunden.")
        for teil in message_parts(text):
            client.send_message(chat, teil)

    def own_chat(self) -> str:
        nummer = clean_number(self.store.who("whatsapp"))
        return f"{digits(nummer)}@s.whatsapp.net" if nummer else ""

    @staticmethod
    def _jid(text: str) -> Any:
        from neonize.utils.jid import build_jid

        benutzer, server = text.rsplit("@", 1)
        return build_jid(benutzer, server)

    def _ready_client(self) -> Any:
        return self._client if self.status().state == CONNECTED else None

    def mark_read(self, nachricht: Incoming) -> None:
        """Blaue Haken. Nur fuer fremde Nachrichten mit geprueften Kennungen."""
        client = self._ready_client()
        absender = nachricht.sender_id if nachricht.group else nachricht.chat
        if (client is None or nachricht.from_me or not MESSAGE_ID_RE.fullmatch(nachricht.id)
                or not JID_RE.fullmatch(nachricht.chat) or not JID_RE.fullmatch(absender)):
            return
        try:
            from neonize.utils.enum import ReceiptType

            client.mark_read(nachricht.id, chat=self._jid(nachricht.chat),
                             sender=self._jid(absender), receipt=ReceiptType.READ)
        except Exception as exc:  # die Antwort darf daran nie scheitern
            LOG.debug("WhatsApp: gelesen nicht gesendet: %s", exc)

    def typing(self, nachricht: Incoming, on: bool) -> None:
        client = self._ready_client()
        if client is None or nachricht.from_me or not JID_RE.fullmatch(nachricht.chat):
            return
        try:
            from neonize.utils.enum import ChatPresence, ChatPresenceMedia

            client.send_chat_presence(
                self._jid(nachricht.chat),
                ChatPresence.CHAT_PRESENCE_COMPOSING if on else ChatPresence.CHAT_PRESENCE_PAUSED,
                ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT)
        except Exception as exc:
            LOG.debug("WhatsApp: schreibt nicht gesendet: %s", exc)


class SignalTransport(Transport):
    """Signal ueber signal-cli: `link` zeigt den QR-Code, `jsonRpc` bringt und sendet."""

    messenger = "signal"
    RESTARTS = 3

    def __init__(self, *args: Any, binary: str = "",
                 popen: Callable[..., Any] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._binary = binary
        self._popen = popen or subprocess.Popen
        self._proc: Any = None
        self._next_id = 0
        self._send_lock = threading.Lock()

    def _program(self) -> str:
        if self._binary:
            return self._binary
        from aquaticy.messenger_install import find_signal_cli

        try:
            gefunden = find_signal_cli()
        except Exception:  # Einstellungen nicht lesbar: dann gibt es auch kein eigenes Programm
            gefunden = None
        return str(gefunden) if gefunden else ""

    def available(self) -> tuple[bool, str]:
        if self._program():
            return True, ""
        return False, NEED_SIGNAL_CLI

    def _config(self) -> list[str]:
        sitzung = self.directory_for_session
        sitzung.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            sitzung.chmod(0o700)
        return [self._program(), "--config", str(sitzung)]

    def start(self) -> None:
        self._finish_stale()
        with self._lock:
            if self.running:
                return
            self._stopping.clear()
            self._set(STARTING, who=self.store.who("signal"))
            self._thread = threading.Thread(target=self._run, name="aquaticy-signal",
                                            daemon=True)
            self._thread.start()

    def _run(self) -> None:
        try:
            nummer = self.store.who("signal")
            if not nummer:
                nummer = self._link()
                if not nummer:
                    return
            versuch = 0
            while not self._stopping.is_set() and versuch <= self.RESTARTS:
                ende = self._daemon(nummer)
                if self._stopping.is_set():
                    return
                versuch += 1
                self._set(FAILED, error=ende or "signal-cli wurde beendet.")
                if versuch > self.RESTARTS:
                    return
                if self._stopping.wait(5 * 3 ** (versuch - 1)):
                    return
                self._set(STARTING, who=nummer)
        except Exception as exc:
            if not self._stopping.is_set():
                LOG.warning("Signal: %s", exc)
                self._set(FAILED, error=_plain_error(exc, "Signal"))

    def _link(self) -> str:
        """Zeigt den QR-Code und wartet auf das Handy. Returns: die Nummer oder ""."""
        proc = self._popen(
            [*self._config(), "link", "-n", DEVICE_NAME], stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, bufsize=1)
        self._proc = proc
        nummer: list[str] = []
        letzte: list[str] = []

        def lesen() -> None:
            for zeile in proc.stdout or ():
                zeile = zeile.strip()
                if SIGNAL_URI.match(zeile):
                    self._set(QR, qr=zeile)
                elif "Associated with:" in zeile:
                    gefunden = clean_number(zeile.split("Associated with:", 1)[1].strip())
                    if gefunden:
                        nummer.append(gefunden)
                elif zeile:
                    letzte.append(zeile[:200])
                    del letzte[:-3]

        leser = threading.Thread(target=lesen, daemon=True)
        leser.start()
        ende = self._clock() + LINK_TIMEOUT
        while proc.poll() is None:
            if self._stopping.is_set():
                _kill(proc)
                return ""
            if self._clock() > ende:
                _kill(proc)
                self._set(FAILED, error="Der QR-Code ist abgelaufen. Verbinde noch einmal.")
                return ""
            time.sleep(0.2)
        leser.join(timeout=5)
        if proc.returncode != 0 or not nummer:
            self._set(FAILED, error=" ".join(letzte) or "Das Koppeln hat nicht geklappt.")
            return ""
        self.store.set("signal", nummer[0])
        return nummer[0]

    def _daemon(self, nummer: str) -> str:
        """Laeuft, solange signal-cli laeuft. Returns: der Grund fuers Ende."""
        if not NUMBER_RE.fullmatch(nummer):
            return "Die gespeicherte Nummer ist ungültig. Verbinde noch einmal."
        proc = self._popen(
            [*self._config(), "-a", nummer, "jsonRpc"], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, stdin=subprocess.PIPE, text=True, bufsize=1)
        self._proc = proc
        self._set(CONNECTED, who=nummer)
        for zeile in proc.stdout or ():
            try:
                meldung = json.loads(zeile)
            except ValueError:
                continue
            if isinstance(meldung, dict) and meldung.get("method") == "receive":
                self._deliver(parse_signal(meldung.get("params"), nummer))
        proc.wait()
        return "signal-cli wurde beendet." if not self._stopping.is_set() else ""

    def stop(self) -> None:
        self._stopping.set()
        proc = self._proc
        if proc is not None:
            _kill(proc)
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=10)
        self._proc = None
        self._set(OFF, who=self.store.who("signal"))

    def unlink(self) -> None:
        self.stop()
        self._wipe_session()
        self._set(OFF, who="")

    def own_chat(self) -> str:
        return "self" if clean_number(self.store.who("signal")) else ""

    def _rpc(self, methode: str, parameter: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None or self.status().state != CONNECTED:
            raise RuntimeError("Signal ist nicht verbunden.")
        with self._send_lock:
            self._next_id += 1
            anfrage = {"jsonrpc": "2.0", "method": methode, "id": self._next_id,
                       "params": parameter}
            proc.stdin.write(json.dumps(anfrage) + "\n")
            proc.stdin.flush()

    def send(self, chat: str, text: str) -> None:
        if chat == "self":
            ziel: dict[str, Any] = {"noteToSelf": True}
        elif chat.startswith("group:") and GROUP_ID_RE.fullmatch(chat[6:]):
            ziel = {"groupId": chat[6:]}
        elif NUMBER_RE.fullmatch(chat):
            ziel = {"recipient": [chat]}
        else:
            raise ValueError("Ungueltiger Chat.")
        for teil in message_parts(text):
            self._rpc("send", {**ziel, "message": teil})

    def mark_read(self, nachricht: Incoming) -> None:
        """Gelesen-Meldung an den Absender (signal-cli: sendReceipt)."""
        if nachricht.from_me or not NUMBER_RE.fullmatch(nachricht.sender) or nachricht.stamp <= 0:
            return
        try:
            self._rpc("sendReceipt", {"recipient": nachricht.sender, "type": "read",
                                      "targetTimestamp": [nachricht.stamp]})
        except Exception as exc:
            LOG.debug("Signal: gelesen nicht gesendet: %s", exc)

    def typing(self, nachricht: Incoming, on: bool) -> None:
        """"schreibt ..." (signal-cli: sendTyping)."""
        if nachricht.from_me:
            return
        if nachricht.chat.startswith("group:") and GROUP_ID_RE.fullmatch(nachricht.chat[6:]):
            ziel: dict[str, Any] = {"groupId": nachricht.chat[6:]}
        elif NUMBER_RE.fullmatch(nachricht.chat):
            ziel = {"recipient": [nachricht.chat]}
        else:
            return
        try:
            self._rpc("sendTyping", {**ziel, **({} if on else {"stop": True})})
        except Exception as exc:
            LOG.debug("Signal: schreibt nicht gesendet: %s", exc)


def _kill(proc: Any) -> None:
    with contextlib.suppress(Exception):
        proc.terminate()
    with contextlib.suppress(Exception):
        proc.wait(timeout=5)
    with contextlib.suppress(Exception):
        if proc.poll() is None:
            proc.kill()


def _plain_error(exc: Exception, name: str) -> str:
    text = str(exc)
    if "Forbidden" in text or "dial" in text or "connect" in text.lower():
        return f"{name} ist gerade nicht erreichbar. Prüfe die Internetverbindung."
    return f"{name}: {text[:160] or type(exc).__name__}"


# ---------------------------------------------------------------------------
# Alle Verbindungen eines Kontos
# ---------------------------------------------------------------------------
_HUBS: dict[str, NativeHub] = {}


def _hub_key(directory: Path | str) -> str:
    return os.path.abspath(str(directory))


def notify_owner(settings: Any, text: str) -> list[str]:
    """Meldet dem Besitzer etwas in seinem eigenen Chat -- ueber die Kopplungen seines Kontos.

    Returns: die Messenger, ueber die es ging (leer: keine Kopplung, Bruecke aus oder pausiert).
    """
    hub = _HUBS.get(_hub_key(Path(getattr(settings, "data_dir", None) or ".") / "messenger"))
    return hub.notify_owner(text) if hub is not None else []


class NativeHub:
    """Haelt die Verbindungen eines Kontos und reicht Nachrichten der Reihe nach weiter."""

    def __init__(self, directory: Path, responder: Callable[[Incoming, Transport], Any],
                 wanted: Callable[[str], bool], *,
                 factories: dict[str, Callable[..., Transport]] | None = None,
                 clock: Callable[[], float] = time.time,
                 paused: Callable[[], bool] | None = None) -> None:
        self.directory = Path(directory)
        self._paused = paused
        self._responder = responder
        self._wanted = wanted
        self._factories = factories or {"whatsapp": WhatsAppTransport, "signal": SignalTransport}
        self._clock = clock
        self._transports: dict[str, Transport] = {}
        self._lock = threading.RLock()
        self._queue: queue.Queue[tuple[Incoming, Transport] | None] = queue.Queue(QUEUE_SIZE)
        self._worker: threading.Thread | None = None
        # "gelesen" geht sofort, auch wenn der Arbeiter gerade eine lange Antwort schreibt.
        self._ack_queue: queue.Queue[tuple[Any, Incoming, Transport] | None] = queue.Queue(
            QUEUE_SIZE)
        self._ack_worker: threading.Thread | None = None
        self._timers: dict[str, threading.Timer] = {}
        self.dropped = 0
        # Meldungen an den Besitzer (Coworker): was gerade nicht ankommt, wartet kurz.
        self._pending: dict[str, list[tuple[float, str]]] = {}
        self._sent_at: dict[str, collections.deque[float]] = {}
        _HUBS[_hub_key(self.directory)] = self

    # -- Verbindungen --------------------------------------------------------
    def transport(self, messenger: str) -> Transport:
        if messenger not in MESSENGERS:
            raise ValueError("Diesen Messenger gibt es nicht.")
        with self._lock:
            eins = self._transports.get(messenger)
            if eins is None:
                eins = self._factories[messenger](
                    self.directory, lambda m, name=messenger: self._enqueue(name, m),
                    on_connected=lambda name=messenger: self._settle(name), clock=self._clock)
                self._transports[messenger] = eins
            return eins

    def available(self, messenger: str) -> tuple[bool, str]:
        return self.transport(messenger).available()

    def link(self, messenger: str) -> LinkStatus:
        """Startet das Koppeln: Danach liefert status() den QR-Code."""
        eins = self.transport(messenger)
        ok, warum = eins.available()
        if not ok:
            raise RuntimeError(warum)
        if eins.status().state == FAILED and eins.running is False:
            eins.stop()
        eins.start()
        return eins.status()

    def status(self, messenger: str) -> LinkStatus:
        eins = self.transport(messenger)
        status = eins.status()
        if status.state == OFF and not status.who:
            status.who = eins.store.who(messenger)
        return status

    def unlink(self, messenger: str) -> None:
        eins = self.transport(messenger)
        self._cancel_timer(messenger)
        eins.unlink()

    def cancel(self, messenger: str) -> None:
        """Bricht ein laufendes Koppeln ab (ohne eine bestehende Kopplung zu loeschen)."""
        eins = self.transport(messenger)
        if not eins.has_session():
            eins.stop()
            eins._wipe_session()

    def ensure_running(self) -> list[str]:
        """Startet, was gekoppelt ist und gebraucht wird; haelt an, was nicht gebraucht wird."""
        laufen: list[str] = []
        for name in MESSENGERS:
            eins = self.transport(name)
            if not eins.has_session():
                continue
            if self._wanted(name):
                ok, _ = eins.available()
                if ok:
                    eins.start()
                    laufen.append(name)
            elif eins.running and eins.status().state == CONNECTED:
                eins.stop()
        return laufen

    def stop(self) -> None:
        if _HUBS.get(_hub_key(self.directory)) is self:
            del _HUBS[_hub_key(self.directory)]
        for name in list(self._timers):
            self._cancel_timer(name)
        with self._lock:
            eins_liste = list(self._transports.values())
        for eins in eins_liste:
            with contextlib.suppress(Exception):
                eins.stop()
        for warteschlange in (self._queue, self._ack_queue):
            with contextlib.suppress(queue.Full):
                warteschlange.put_nowait(None)

    # -- Meldungen an den Besitzer (Coworker) -----------------------------------------------
    def notify_owner(self, text: str) -> list[str]:
        """Schickt dem Besitzer eine Nachricht in seinen eigenen Chat. Returns: wohin sie ging.

        Nur ueber Messenger, die gekoppelt sind und die der Besitzer eingeschaltet hat (Bruecke
        an). Steht die Verbindung gerade nicht, wartet die Nachricht bis zu NOTIFY_KEEP_SECONDS
        auf die naechste. Hoechstens NOTIFY_PER_HOUR je Messenger und Stunde.
        """
        if self._paused is not None and self._paused():
            return []
        gesendet: list[str] = []
        for name in MESSENGERS:
            eins = self.transport(name)
            if not eins.has_session() or not self._wanted(name) or not eins.own_chat():
                continue
            if eins.status().state == CONNECTED:
                if self._send_owner(name, eins, text):
                    gesendet.append(name)
            else:
                with self._lock:
                    warte = self._pending.setdefault(name, [])
                    warte.append((self._clock(), text))
                    del warte[:-NOTIFY_QUEUE]
        return gesendet

    def _send_owner(self, name: str, eins: Transport, text: str) -> bool:
        jetzt = self._clock()
        with self._lock:
            zeiten = self._sent_at.setdefault(name, collections.deque())
            while zeiten and jetzt - zeiten[0] > 3600:
                zeiten.popleft()
            if len(zeiten) >= NOTIFY_PER_HOUR:
                return False
            zeiten.append(jetzt)
        try:
            eins.send(eins.own_chat(), text)
        except Exception:
            LOG.warning("%s: Meldung an den Besitzer nicht gesendet", NAMES.get(name, name))
            return False
        return True

    def _flush(self, name: str) -> None:
        """Nach dem Verbinden: was gewartet hat, geht jetzt raus (wenn es nicht zu alt ist)."""
        with self._lock:
            warte = self._pending.pop(name, [])
        jetzt = self._clock()
        eins = self.transport(name)
        for zeit, text in warte:
            if jetzt - zeit <= NOTIFY_KEEP_SECONDS and (
                    self._paused is None or not self._paused()) and self._wanted(name):
                self._send_owner(name, eins, text)

    # -- nach dem Koppeln --------------------------------------------------------
    def _settle(self, messenger: str) -> None:
        """Ist die Bruecke aus, trennt sich die frisch gekoppelte Verbindung nach kurzer Zeit."""
        if self._pending.get(messenger):
            # Nicht im Rueckruf von neonize senden: ein eigener Faden.
            threading.Thread(target=self._flush, args=(messenger,), daemon=True,
                             name="aquaticy-meldungen").start()
        if self._wanted(messenger):
            return
        self._cancel_timer(messenger)

        def pruefen() -> None:
            eins = self.transport(messenger)
            if not self._wanted(messenger):
                eins.stop()

        zeitgeber = threading.Timer(SETTLE_SECONDS, pruefen)
        zeitgeber.daemon = True
        with self._lock:
            self._timers[messenger] = zeitgeber
        zeitgeber.start()

    def _cancel_timer(self, messenger: str) -> None:
        with self._lock:
            zeitgeber = self._timers.pop(messenger, None)
        if zeitgeber is not None:
            zeitgeber.cancel()

    # -- Nachrichten ------------------------------------------------------------------
    def _enqueue(self, messenger: str, nachricht: Incoming) -> None:
        eins = self.transport(messenger)
        try:
            self._queue.put_nowait((nachricht, eins))
        except queue.Full:
            self.dropped += 1
            return
        self._start_worker("_worker", self._work, "aquaticy-nachrichten")
        quittung = getattr(self._responder, "acknowledge", None)
        if quittung is not None:
            with contextlib.suppress(queue.Full):
                self._ack_queue.put_nowait((quittung, nachricht, eins))
                self._start_worker("_ack_worker", self._ack_work, "aquaticy-gelesen")

    def _start_worker(self, attribut: str, ziel: Callable[[], None], name: str) -> None:
        with self._lock:
            faden = getattr(self, attribut)
            if faden is None or not faden.is_alive():
                faden = threading.Thread(target=ziel, name=name, daemon=True)
                setattr(self, attribut, faden)
                faden.start()

    def _idle(self, attribut: str, warteschlange: queue.Queue[Any]) -> bool:
        """Ein Arbeiter geht nach einer Minute Ruhe -- aber nie, wenn gerade etwas kam."""
        with self._lock:
            if warteschlange.empty():
                setattr(self, attribut, None)
                return True
        return False

    def _work(self) -> None:
        while True:
            try:
                eintrag = self._queue.get(timeout=60)
            except queue.Empty:
                if self._idle("_worker", self._queue):
                    return
                continue
            if eintrag is None:  # "Anhalten" -- aber nie vor einer Nachricht, die schon wartet
                if self._idle("_worker", self._queue):
                    return
                continue
            nachricht, eins = eintrag
            try:
                self._responder(nachricht, eins)
            except Exception:
                LOG.exception("Antwort auf eine %s-Nachricht ist fehlgeschlagen",
                              nachricht.messenger)

    def _ack_work(self) -> None:
        while True:
            try:
                eintrag = self._ack_queue.get(timeout=60)
            except queue.Empty:
                if self._idle("_ack_worker", self._ack_queue):
                    return
                continue
            if eintrag is None:
                if self._idle("_ack_worker", self._ack_queue):
                    return
                continue
            quittung, nachricht, eins = eintrag
            try:
                quittung(nachricht, eins)
            except Exception:
                LOG.exception("Gelesen-Meldung fuer eine %s-Nachricht ist fehlgeschlagen",
                              nachricht.messenger)
