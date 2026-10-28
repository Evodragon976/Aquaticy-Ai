"""WhatsApp und Signal direkt koppeln -- ohne virtual machine und ohne Browser (12.7.8 Terra).

Aquaticy wird wie das Handy-Programm ein "gekoppeltes Geraet": Es zeigt einen QR-Code, du
scannst ihn mit dem Handy, danach kommen Nachrichten als Ereignisse an. WhatsApp laeuft ueber
neonize (whatsmeow), Signal ueber das Programm signal-cli. Beides sind inoffizielle Wege.

Dieses Modul bewegt nur Nachrichten: koppeln, empfangen, senden. Wer antworten darf und was
Aquaticy dabei tun darf, entscheidet allein aquaticy/bridge_native.py.
"""

from __future__ import annotations

import contextlib
import functools
import importlib
import json
import logging
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

MAX_SEND_CHARS = 3800
QR_MAX_CHARS = 4096
LINK_TIMEOUT = 240.0
MAX_AGE_SECONDS = 300.0
QUEUE_SIZE = 20
SETTLE_SECONDS = 15.0

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
        self_chat=eigener_chat, name=str(info.Pushname or "")[:60])


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
        self_chat=eigener, name=str(huelle.get("sourceName") or "")[:60])


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
            with contextlib.suppress(Exception):
                client.disconnect()
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
        for teil in split_text(text):
            client.send_message(chat, teil)


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

    def send(self, chat: str, text: str) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None or self.status().state != CONNECTED:
            raise RuntimeError("Signal ist nicht verbunden.")
        if chat == "self":
            ziel: dict[str, Any] = {"noteToSelf": True}
        elif chat.startswith("group:") and GROUP_ID_RE.fullmatch(chat[6:]):
            ziel = {"groupId": chat[6:]}
        elif NUMBER_RE.fullmatch(chat):
            ziel = {"recipient": [chat]}
        else:
            raise ValueError("Ungueltiger Chat.")
        for teil in split_text(text):
            with self._send_lock:
                self._next_id += 1
                anfrage = {"jsonrpc": "2.0", "method": "send", "id": self._next_id,
                           "params": {**ziel, "message": teil}}
                proc.stdin.write(json.dumps(anfrage) + "\n")
                proc.stdin.flush()


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
class NativeHub:
    """Haelt die Verbindungen eines Kontos und reicht Nachrichten der Reihe nach weiter."""

    def __init__(self, directory: Path, responder: Callable[[Incoming, Transport], Any],
                 wanted: Callable[[str], bool], *,
                 factories: dict[str, Callable[..., Transport]] | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.directory = Path(directory)
        self._responder = responder
        self._wanted = wanted
        self._factories = factories or {"whatsapp": WhatsAppTransport, "signal": SignalTransport}
        self._clock = clock
        self._transports: dict[str, Transport] = {}
        self._lock = threading.RLock()
        self._queue: queue.Queue[tuple[Incoming, Transport] | None] = queue.Queue(QUEUE_SIZE)
        self._worker: threading.Thread | None = None
        self._timers: dict[str, threading.Timer] = {}
        self.dropped = 0

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
        for name in list(self._timers):
            self._cancel_timer(name)
        with self._lock:
            eins_liste = list(self._transports.values())
        for eins in eins_liste:
            with contextlib.suppress(Exception):
                eins.stop()
        with contextlib.suppress(queue.Full):
            self._queue.put_nowait(None)

    # -- nach dem Koppeln --------------------------------------------------------
    def _settle(self, messenger: str) -> None:
        """Ist die Bruecke aus, trennt sich die frisch gekoppelte Verbindung nach kurzer Zeit."""
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
        try:
            self._queue.put_nowait((nachricht, self.transport(messenger)))
        except queue.Full:
            self.dropped += 1
            return
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._work, name="aquaticy-nachrichten",
                                                daemon=True)
                self._worker.start()

    def _work(self) -> None:
        while True:
            try:
                eintrag = self._queue.get(timeout=60)
            except queue.Empty:
                return
            if eintrag is None:
                return
            nachricht, eins = eintrag
            try:
                self._responder(nachricht, eins)
            except Exception:
                LOG.exception("Antwort auf eine %s-Nachricht ist fehlgeschlagen",
                              nachricht.messenger)
