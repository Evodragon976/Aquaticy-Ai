"""Direkte Kopplung (aquaticy/messenger_native.py): Nachrichten lesen, koppeln, senden.

Echtes WhatsApp oder Signal gibt es hier nicht. Geprüft wird mit echten Neonize-Nachrichten
(Protobuf, wenn neonize da ist), gestellten Clients und einem gestellten signal-cli.
"""

from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from aquaticy import messenger_native as nat
from aquaticy.messenger_native import (
    CONNECTED,
    FAILED,
    OFF,
    QR,
    STARTING,
    Incoming,
    NativeHub,
    NativeStore,
    SignalTransport,
    WhatsAppTransport,
    clean_number,
    parse_signal,
    parse_whatsapp,
    split_text,
)

ME = "4915100000000"
OTHER = "4915123456789"


def wait_for(bedingung, sekunden: float = 5.0) -> bool:
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.01)
    return bool(bedingung())


# -- WhatsApp: Nachrichten lesen -------------------------------------------------------
def jid(user: str, server: str = "s.whatsapp.net") -> Any:
    return SimpleNamespace(User=user, Server=server)


def wa_event(text: str = "Hallo", *, chat: Any = None, sender: Any = None, alt: Any = None,
             von_mir: bool = False, gruppe: bool = False, edit: bool = False,
             ext: str = "", id_: str = "ABC1", ts: int = 1_700_000_000) -> Any:
    quelle = SimpleNamespace(
        Chat=chat or jid(OTHER), Sender=sender or jid(OTHER), IsFromMe=von_mir, IsGroup=gruppe,
        SenderAlt=alt or jid("", ""))
    info = SimpleNamespace(MessageSource=quelle, ID=id_, Timestamp=ts, Pushname="Anna")
    nachricht = SimpleNamespace(conversation=text,
                                extendedTextMessage=SimpleNamespace(text=ext))
    return SimpleNamespace(Info=info, Message=nachricht, IsEdit=edit)


OWN = {ME, "99887766"}


def test_a_plain_message_from_another_person() -> None:
    nachricht = parse_whatsapp(wa_event("Wie spät ist es?"), OWN)
    assert nachricht == Incoming(
        messenger="whatsapp", chat=f"{OTHER}@s.whatsapp.net", text="Wie spät ist es?",
        id="ABC1", ts=1_700_000_000.0, sender=f"+{OTHER}", group=False, from_me=False,
        self_chat=False, name="Anna")


def test_the_text_may_sit_in_the_extended_message() -> None:
    assert parse_whatsapp(wa_event("", ext="mit Link"), OWN).text == "mit Link"


def test_the_own_chat_is_the_chat_with_oneself_and_nothing_else() -> None:
    eigener = parse_whatsapp(wa_event("an mich", chat=jid(ME), sender=jid(ME), von_mir=True), OWN)
    assert eigener.self_chat and eigener.from_me and eigener.sender == ""
    # Die eigene LID zählt auch.
    lid = parse_whatsapp(wa_event("an mich", chat=jid("99887766", "lid"), sender=jid(ME),
                                  von_mir=True), OWN)
    assert lid.self_chat
    # Vom Handy an eine andere Person: ist es nicht.
    anderer = parse_whatsapp(wa_event("hi Anna", chat=jid(OTHER), sender=jid(ME), von_mir=True),
                             OWN)
    assert not anderer.self_chat and anderer.from_me
    # Jemand schreibt MIR: nie der eigene Chat, auch wenn die Nummer gleich aussieht.
    fremd = parse_whatsapp(wa_event("hi", chat=jid(ME), sender=jid(OTHER), von_mir=False), OWN)
    assert not fremd.self_chat
    # Gruppe: nie.
    gruppe = parse_whatsapp(wa_event("hi", chat=jid(ME, "g.us"), sender=jid(ME), von_mir=True,
                                     gruppe=True), OWN)
    assert not gruppe.self_chat and gruppe.group


def test_a_group_message_carries_the_sender_number_not_the_group() -> None:
    nachricht = parse_whatsapp(wa_event("Aquaticy, Wetter", chat=jid("1203630", "g.us"),
                                        sender=jid(OTHER), gruppe=True), OWN)
    assert nachricht.group and nachricht.sender == f"+{OTHER}"
    assert nachricht.chat == "1203630@g.us"


def test_a_lid_sender_gets_its_number_from_the_alternative_address() -> None:
    nachricht = parse_whatsapp(wa_event("hi", chat=jid("555", "lid"), sender=jid("555", "lid"),
                                        alt=jid(OTHER)), OWN)
    assert nachricht.sender == f"+{OTHER}"
    ohne = parse_whatsapp(wa_event("hi", chat=jid("555", "lid"), sender=jid("555", "lid")), OWN)
    assert ohne.sender == "", "ohne Nummer gilt der Absender als unbekannt, nie als geraten"


@pytest.mark.parametrize("fall", [
    dict(text=""), dict(text="   "), dict(edit=True),
    dict(chat=jid("status", "broadcast")), dict(chat=jid("123", "newsletter")),
    dict(chat=jid("12 3;rm", "s.whatsapp.net")),
])
def test_what_is_not_a_question_is_dropped(fall: dict[str, Any]) -> None:
    kwargs = {"text": "Hallo", **fall}
    assert parse_whatsapp(wa_event(**kwargs), OWN) is None


def test_millisecond_timestamps_are_read_as_seconds() -> None:
    assert parse_whatsapp(wa_event(ts=1_700_000_000_000), OWN).ts == 1_700_000_000.0
    assert parse_whatsapp(wa_event(ts=0), OWN).ts == 0.0


def test_real_neonize_messages_are_understood() -> None:
    """Mit echten Protobuf-Nachrichten, wie sie die Go-Bibliothek liefert."""
    pytest.importorskip("neonize.proto.Neonize_pb2")
    from neonize.proto.Neonize_pb2 import Message as MessageEv

    ev = MessageEv()
    ev.Info.MessageSource.Chat.User = ME
    ev.Info.MessageSource.Chat.Server = "s.whatsapp.net"
    ev.Info.MessageSource.Sender.User = ME
    ev.Info.MessageSource.Sender.Server = "s.whatsapp.net"
    ev.Info.MessageSource.IsFromMe = True
    ev.Info.ID = "XYZ"
    ev.Info.Timestamp = 1_700_000_000_000
    ev.Message.conversation = "Notiz an mich"
    nachricht = parse_whatsapp(ev, OWN)
    assert nachricht and nachricht.self_chat and nachricht.text == "Notiz an mich"
    assert nachricht.ts == 1_700_000_000.0

    ev2 = MessageEv()
    ev2.Info.MessageSource.Chat.User = "555"
    ev2.Info.MessageSource.Chat.Server = "lid"
    ev2.Info.MessageSource.Sender.User = "555"
    ev2.Info.MessageSource.Sender.Server = "lid"
    ev2.Info.MessageSource.SenderAlt.User = OTHER
    ev2.Info.MessageSource.SenderAlt.Server = "s.whatsapp.net"
    ev2.Message.extendedTextMessage.text = "Hallo"
    zwei = parse_whatsapp(ev2, OWN)
    assert zwei and zwei.sender == f"+{OTHER}" and not zwei.self_chat
    leer = MessageEv()
    leer.Info.MessageSource.Chat.User = OTHER
    leer.Info.MessageSource.Chat.Server = "s.whatsapp.net"
    assert parse_whatsapp(leer, OWN) is None


# -- Signal: Meldungen lesen --------------------------------------------------------------
def sig_data(text: str = "Hallo", quelle: str = "+4915123456789", **mehr: Any) -> dict[str, Any]:
    daten = {"message": text, **mehr}
    return {"envelope": {"sourceNumber": quelle, "timestamp": 1_700_000_000_000,
                         "sourceName": "Anna", "dataMessage": daten}}


MY_NUMBER = "+4915100000000"


def test_a_signal_message_from_another_person() -> None:
    nachricht = parse_signal(sig_data("Hi"), MY_NUMBER)
    assert nachricht.chat == "+4915123456789" and nachricht.sender == "+4915123456789"
    assert not nachricht.group and not nachricht.from_me and not nachricht.self_chat
    assert nachricht.ts == 1_700_000_000.0 and nachricht.name == "Anna"


def test_a_signal_group_message_uses_the_group_as_chat() -> None:
    nachricht = parse_signal(sig_data("Aquaticy, hi", groupInfo={"groupId": "abc+DEF/123="}),
                             MY_NUMBER)
    assert nachricht.group and nachricht.chat == "group:abc+DEF/123="
    assert nachricht.sender == "+4915123456789"


def test_note_to_self_is_a_sync_message_to_my_own_number() -> None:
    meldung = {"envelope": {"sourceNumber": MY_NUMBER, "timestamp": 1_700_000_000_000,
                            "syncMessage": {"sentMessage": {
                                "message": "Notiz", "destinationNumber": MY_NUMBER}}}}
    nachricht = parse_signal(meldung, MY_NUMBER)
    assert nachricht.self_chat and nachricht.from_me and nachricht.chat == "self"


def test_what_i_write_to_others_from_the_phone_is_no_note_to_self() -> None:
    meldung = {"envelope": {"sourceNumber": MY_NUMBER, "timestamp": 1,
                            "syncMessage": {"sentMessage": {
                                "message": "hi", "destinationNumber": "+4915123456789"}}}}
    nachricht = parse_signal(meldung, MY_NUMBER)
    assert nachricht.from_me and not nachricht.self_chat and nachricht.chat == "+4915123456789"


def test_a_group_never_counts_as_the_own_chat() -> None:
    meldung = {"envelope": {"sourceNumber": MY_NUMBER, "timestamp": 1,
                            "syncMessage": {"sentMessage": {
                                "message": "hi", "destinationNumber": MY_NUMBER,
                                "groupInfo": {"groupId": "abcdefgh12="}}}}}
    assert not parse_signal(meldung, MY_NUMBER).self_chat


@pytest.mark.parametrize("meldung", [
    None, [], {}, {"envelope": None}, {"envelope": {}},
    {"envelope": {"receiptMessage": {"when": 1}}},
    {"envelope": {"typingMessage": {"action": "STARTED"}}},
    sig_data(""), sig_data("  "),
    sig_data("hi", quelle="kein-Nummer"), sig_data("hi", quelle=""),
    sig_data("hi", groupInfo={"groupId": "a b;c"}),
])
def test_other_signal_events_are_dropped(meldung: Any) -> None:
    assert parse_signal(meldung, MY_NUMBER) is None


@pytest.mark.parametrize(("roh", "erwartet"), [
    ("+49 151 2345678", "+491512345678"), ("+4915123456789", "+4915123456789"),
    ("0151 2345678", ""), ("+12", ""), ("abc", ""), ("", ""), (None, ""),
    ("+49151234567890123456", ""),
])
def test_only_checked_international_numbers_are_numbers(roh: Any, erwartet: str) -> None:
    assert clean_number(roh) == erwartet


def test_long_texts_are_split_at_line_or_word_ends() -> None:
    text = ("Zeile eins\n" + "wort " * 400).strip()
    teile = split_text(text, 500)
    assert all(len(t) <= 500 for t in teile) and len(teile) >= 4
    assert " ".join("".join(teile).split()).replace(" ", "") == text.replace(" ", "").replace(
        "\n", "")
    assert split_text("kurz") == ["kurz"] and split_text("   ") == []
    glatt = split_text("x" * 1200, 500)
    assert [len(t) for t in glatt] == [500, 500, 200]


# -- Was gekoppelt ist -------------------------------------------------------------------------
def test_the_store_remembers_who_is_linked_without_secrets(tmp_path: Path) -> None:
    speicher = NativeStore(tmp_path / "messenger")
    assert not speicher.linked("whatsapp") and speicher.who("whatsapp") == ""
    speicher.set("whatsapp", "+4915100000000")
    assert speicher.linked("whatsapp") and speicher.who("whatsapp") == "+4915100000000"
    assert not speicher.linked("signal")
    inhalt = (tmp_path / "messenger" / "native.json").read_text(encoding="utf-8")
    assert set(json.loads(inhalt)["whatsapp"]) == {"who", "at"}
    assert oct((tmp_path / "messenger" / "native.json").stat().st_mode & 0o777) == "0o600"
    speicher.clear("whatsapp")
    assert not speicher.linked("whatsapp")
    (tmp_path / "messenger" / "native.json").write_text("kaputt", encoding="utf-8")
    assert speicher.who("whatsapp") == ""


def test_linked_reads_the_account_folder(tmp_path: Path) -> None:
    einstellungen = SimpleNamespace(data_dir=tmp_path)
    assert not nat.linked(einstellungen, "whatsapp")
    NativeStore(tmp_path / "messenger").set("whatsapp", "+4915100000000")
    assert nat.linked(einstellungen, "whatsapp") and not nat.linked(einstellungen, "signal")
    assert not nat.linked(einstellungen, "telegram")


# -- WhatsApp: die Verbindung mit gestelltem Client --------------------------------------------
class FakeClient:
    """Ein neonize-Client, der nichts verbindet, aber alles meldet."""

    instances: ClassVar[list[FakeClient]] = []

    def __init__(self, path: str, uuid: str = "") -> None:
        self.path = path
        self.uuid = uuid
        self.handlers: dict[Any, Any] = {}
        self.qr_handler: Any = None
        self.me = SimpleNamespace(JID=jid(ME), LID=jid("99887766", "lid"))
        self.sent: list[tuple[str, str]] = []
        self.logged_out = False
        self.stop = threading.Event()
        self.fail: Exception | None = None
        FakeClient.instances.append(self)

    def qr(self, funktion: Any) -> Any:
        self.qr_handler = funktion
        return funktion

    def event(self, klasse: Any) -> Any:
        def merken(funktion: Any) -> Any:
            self.handlers[klasse] = funktion
            return funktion
        return merken

    def connect(self) -> None:
        if self.fail:
            raise self.fail
        self.stop.wait(10)

    def disconnect(self) -> None:
        self.stop.set()

    def logout(self) -> None:
        self.logged_out = True

    def send_message(self, chat: str, text: str) -> None:
        self.sent.append((chat, text))


class Ev:
    ConnectedEv, LoggedOutEv, MessageEv, PairStatusEv = (
        type("ConnectedEv", (), {}), type("LoggedOutEv", (), {}),
        type("MessageEv", (), {}), type("PairStatusEv", (), {}))


@pytest.fixture
def whatsapp(tmp_path: Path):
    FakeClient.instances = []
    empfangen: list[Incoming] = []
    verbunden: list[int] = []
    eins = WhatsAppTransport(
        tmp_path / "messenger", empfangen.append, on_connected=lambda: verbunden.append(1),
        client_factory=FakeClient, events=Ev)
    yield eins, empfangen, verbunden
    eins.stop()


def test_whatsapp_shows_the_qr_then_connects_and_remembers_the_number(whatsapp, tmp_path) -> None:
    eins, _, verbunden = whatsapp
    assert eins.status().state == OFF
    eins.start()
    assert wait_for(lambda: FakeClient.instances and FakeClient.instances[0].handlers)
    client = FakeClient.instances[0]
    assert client.path.endswith("whatsapp/session.sqlite3")
    assert eins.status().state == STARTING
    client.qr_handler(client, b"2@abc,def,ghi,1")
    assert eins.status().state == QR and eins.status().qr == "2@abc,def,ghi,1"
    client.handlers[Ev.PairStatusEv](client, SimpleNamespace(
        Status=1, ID=SimpleNamespace(User=ME)))
    assert eins.store.who("whatsapp") == f"+{ME}"
    client.handlers[Ev.ConnectedEv](client, object())
    status = eins.status()
    assert status.state == CONNECTED and status.who == f"+{ME}" and status.qr == ""
    assert verbunden == [1]
    assert nat.linked(SimpleNamespace(data_dir=tmp_path), "whatsapp")


def test_a_failed_pairing_is_an_error_and_no_number_is_stored(whatsapp) -> None:
    eins, _, _ = whatsapp
    eins.start()
    assert wait_for(lambda: FakeClient.instances and FakeClient.instances[0].handlers)
    client = FakeClient.instances[0]
    client.handlers[Ev.PairStatusEv](client, SimpleNamespace(Status=0, ID=SimpleNamespace(User="")))
    assert eins.status().state == FAILED and not eins.store.linked("whatsapp")


def test_whatsapp_hands_parsed_messages_on(whatsapp) -> None:
    eins, empfangen, _ = whatsapp
    eins.start()
    assert wait_for(lambda: FakeClient.instances and FakeClient.instances[0].handlers)
    client = FakeClient.instances[0]
    client.handlers[Ev.MessageEv](client, wa_event("Hallo", chat=jid(ME), sender=jid(ME),
                                                   von_mir=True))
    client.handlers[Ev.MessageEv](client, wa_event("", chat=jid(ME)))
    assert [(m.text, m.self_chat) for m in empfangen] == [("Hallo", True)]


def test_whatsapp_sends_only_when_connected_and_only_to_valid_chats(whatsapp) -> None:
    eins, _, _ = whatsapp
    with pytest.raises(RuntimeError, match="nicht verbunden"):
        eins.send(f"{OTHER}@s.whatsapp.net", "hi")
    eins.start()
    assert wait_for(lambda: FakeClient.instances and FakeClient.instances[0].handlers)
    client = FakeClient.instances[0]
    client.handlers[Ev.ConnectedEv](client, object())
    eins.send(f"{OTHER}@s.whatsapp.net", "hi")
    eins.send("123@g.us", "wort " * 1500)
    assert client.sent[0] == (f"{OTHER}@s.whatsapp.net", "hi")
    assert len(client.sent) >= 3 and all(len(t) <= nat.MAX_SEND_CHARS for _, t in client.sent)
    for schlecht in ("nummer", "a@evil.example", "x;rm -rf@s.whatsapp.net", "", "@g.us"):
        with pytest.raises(ValueError):
            eins.send(schlecht, "hi")


def test_a_connection_error_becomes_a_plain_sentence(whatsapp) -> None:
    eins, _, _ = whatsapp
    original = FakeClient.__init__

    def init(self: FakeClient, path: str, uuid: str = "") -> None:
        original(self, path, uuid)
        self.fail = RuntimeError('failed to dial: Get "https://web.whatsapp.com": Forbidden')

    FakeClient.__init__ = init  # type: ignore[method-assign]
    try:
        eins.start()
        assert wait_for(lambda: eins.status().state == FAILED)
    finally:
        FakeClient.__init__ = original  # type: ignore[method-assign]
    status = eins.status()
    assert "nicht erreichbar" in status.error and "Forbidden" not in status.error


def test_when_the_phone_removes_the_device_the_session_is_wiped(whatsapp, tmp_path) -> None:
    eins, _, _ = whatsapp
    eins.start()
    assert wait_for(lambda: FakeClient.instances and FakeClient.instances[0].handlers)
    client = FakeClient.instances[0]
    client.handlers[Ev.PairStatusEv](client, SimpleNamespace(Status=1, ID=SimpleNamespace(User=ME)))
    assert eins.store.linked("whatsapp")
    client.handlers[Ev.LoggedOutEv](client, object())
    assert not eins.store.linked("whatsapp")
    assert eins.status().state == FAILED and "abgemeldet" in eins.status().error
    assert not (tmp_path / "messenger" / "whatsapp").exists()


def test_unlinking_logs_out_and_deletes_the_session(whatsapp, tmp_path) -> None:
    eins, _, _ = whatsapp
    eins.start()
    assert wait_for(lambda: FakeClient.instances and FakeClient.instances[0].handlers)
    client = FakeClient.instances[0]
    client.handlers[Ev.PairStatusEv](client, SimpleNamespace(Status=1, ID=SimpleNamespace(User=ME)))
    (tmp_path / "messenger" / "whatsapp" / "session.sqlite3").write_text("x", encoding="utf-8")
    eins.unlink()
    assert client.logged_out and client.stop.is_set()
    assert not eins.store.linked("whatsapp") and eins.status().who == ""
    assert not (tmp_path / "messenger" / "whatsapp").exists()
    assert not eins.running


def test_every_connection_gets_its_own_client_id(whatsapp) -> None:
    """Ein alter Client ruft beim Aufräumen Stop(Kennung): gleiche Kennung stoppte den neuen."""
    eins, _, _ = whatsapp
    eins.start()
    assert wait_for(lambda: len(FakeClient.instances) == 1)
    eins.stop()
    eins.start()
    assert wait_for(lambda: len(FakeClient.instances) == 2)
    erste, zweite = FakeClient.instances
    assert erste.uuid.startswith("aquaticy-") and zweite.uuid.startswith("aquaticy-")
    assert erste.uuid != zweite.uuid


def test_starting_twice_runs_one_connection(whatsapp) -> None:
    eins, _, _ = whatsapp
    eins.start()
    eins.start()
    assert wait_for(lambda: FakeClient.instances)
    time.sleep(0.1)
    assert len(FakeClient.instances) == 1


def test_whatsapp_is_available_with_neonize_and_says_what_is_missing_without(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nat.neonize_available.cache_clear()
    monkeypatch.setitem(__import__("sys").modules, "neonize.client", None)
    ok, warum = WhatsAppTransport(tmp_path, lambda m: None).available()
    assert not ok and warum == nat.NEED_NEONIZE
    nat.neonize_available.cache_clear()


def test_a_missing_libmagic_is_named_on_its_own(tmp_path: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    """python-magic wirft "failed to find libmagic": dann hilft nur install-messenger."""
    import builtins

    echt = builtins.__import__

    def import_ohne_libmagic(name, *args, **kwargs):
        if name == "neonize.client":
            raise ImportError("failed to find libmagic.  Check your installation")
        return echt(name, *args, **kwargs)

    nat.neonize_available.cache_clear()
    monkeypatch.setattr(builtins, "__import__", import_ohne_libmagic)
    ok, warum = WhatsAppTransport(tmp_path, lambda m: None).available()
    monkeypatch.undo()
    nat.neonize_available.cache_clear()
    assert not ok and warum == nat.NEED_LIBMAGIC and "install-messenger" in warum


# -- Signal: die Verbindung mit gestelltem signal-cli ---------------------------------------------
class FakeProc:
    """Ein Prozess, dessen Ausgabe der Test vorgibt."""

    def __init__(self, args: list[str], zeilen: list[str], *, rc: int = 0,
                 bleibt: bool = False) -> None:
        self.args = args
        self.returncode: int | None = None
        self._rc = rc
        self._queue: list[str] = [z + "\n" for z in zeilen]
        self._bleibt = bleibt
        self._ende = threading.Event()
        self.stdout = self._lines()
        self.stdin = io.StringIO()
        self.terminated = False
        if not bleibt and not zeilen:
            self.returncode = rc

    def _lines(self):
        yield from self._queue
        if self._bleibt:
            self._ende.wait(20)
        self.returncode = self._rc

    def poll(self) -> int | None:
        return self.returncode if self._ende.is_set() or not self._bleibt else None

    def wait(self, timeout: float | None = None) -> int:
        self._ende.wait(timeout or 0.01)
        return self.returncode or 0

    def terminate(self) -> None:
        self.terminated = True
        self._ende.set()
        self.returncode = -15

    def kill(self) -> None:
        self.terminate()


class FakeSignal:
    """signal-cli: `link` zeigt eine Adresse, danach läuft `jsonRpc`."""

    def __init__(self, link_zeilen: list[str] | None = None, *, link_rc: int = 0,
                 rpc_zeilen: list[str] | None = None) -> None:
        self.link_zeilen = link_zeilen if link_zeilen is not None else [
            "sgnl://linkdevice?uuid=abc123def456&pub_key=XYZ789", "Associated with: +4915100000000"]
        self.link_rc = link_rc
        self.rpc_zeilen = rpc_zeilen or []
        self.aufrufe: list[list[str]] = []
        self.rpc: list[FakeProc] = []

    def __call__(self, args: list[str], **kwargs: Any) -> FakeProc:
        self.aufrufe.append(list(args))
        if "link" in args:
            return FakeProc(args, self.link_zeilen, rc=self.link_rc)
        proc = FakeProc(args, self.rpc_zeilen, bleibt=True)
        self.rpc.append(proc)
        return proc


@pytest.fixture
def signal(tmp_path: Path):
    empfangen: list[Incoming] = []
    fake = FakeSignal()
    eins = SignalTransport(tmp_path / "messenger", empfangen.append, binary="/usr/bin/signal-cli",
                           popen=fake)
    yield eins, fake, empfangen
    eins.stop()


def test_signal_links_shows_the_address_and_starts_receiving(signal, tmp_path) -> None:
    eins, fake, _ = signal
    eins.start()
    assert wait_for(lambda: eins.status().state == CONNECTED)
    assert eins.status().who == MY_NUMBER and eins.store.who("signal") == MY_NUMBER
    sitzung = str(tmp_path / "messenger" / "signal")
    assert fake.aufrufe[0] == ["/usr/bin/signal-cli", "--config", sitzung, "link", "-n",
                               "Aquaticy"]
    assert fake.aufrufe[1] == ["/usr/bin/signal-cli", "--config", sitzung, "-a", MY_NUMBER,
                               "jsonRpc"]


def test_the_signal_qr_is_the_link_address(tmp_path: Path) -> None:
    fake = FakeSignal(["Bitte warten", "sgnl://linkdevice?uuid=abc123def456&pub_key=XYZ789"],
                      link_rc=0)
    fake.link_zeilen.append("keine Nummer")
    eins = SignalTransport(tmp_path, lambda m: None, binary="signal-cli", popen=fake)
    eins.start()
    assert wait_for(lambda: eins.status().state in (QR, FAILED))
    zustand = eins.status()
    assert wait_for(lambda: eins.status().state == FAILED)
    assert eins.status().error, "ohne 'Associated with' ist das Koppeln gescheitert"
    assert zustand.state in (QR, FAILED)
    eins.stop()


def test_signal_keeps_the_address_while_waiting_for_the_phone(tmp_path: Path) -> None:
    class Wartet(FakeSignal):
        def __call__(self, args: list[str], **kwargs: Any) -> FakeProc:
            self.aufrufe.append(list(args))
            return FakeProc(args, ["sgnl://linkdevice?uuid=abc123def456&pub_key=XYZ789"],
                            bleibt=True)

    fake = Wartet()
    eins = SignalTransport(tmp_path, lambda m: None, binary="signal-cli", popen=fake)
    eins.start()
    assert wait_for(lambda: eins.status().state == QR)
    assert eins.status().qr.startswith("sgnl://linkdevice?uuid=")
    eins.stop()
    assert eins.status().state == OFF and not eins.store.linked("signal")


def test_a_wrong_address_line_never_becomes_a_qr(tmp_path: Path) -> None:
    class Boese(FakeSignal):
        def __call__(self, args: list[str], **kwargs: Any) -> FakeProc:
            return FakeProc(args, ["https://evil.example/x", "javascript:alert(1)",
                                   "sgnl://x"], bleibt=True)

    eins = SignalTransport(tmp_path, lambda m: None, binary="signal-cli", popen=Boese())
    eins.start()
    time.sleep(0.3)
    assert eins.status().state == STARTING and eins.status().qr == ""
    eins.stop()


def test_signal_delivers_received_messages_and_sends_json_rpc(signal) -> None:
    eins, fake, empfangen = signal
    fake.rpc_zeilen = [
        json.dumps({"jsonrpc": "2.0", "method": "receive", "params": sig_data("Hi")}),
        "kein json", json.dumps({"jsonrpc": "2.0", "method": "andere", "params": {}}),
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}),
    ]
    eins.start()
    assert wait_for(lambda: len(empfangen) == 1)
    assert empfangen[0].text == "Hi" and empfangen[0].messenger == "signal"
    proc = fake.rpc[0]
    eins.send("+4915123456789", "Antwort")
    eins.send("self", "Notiz")
    eins.send("group:abcdefgh12=", "Gruppe")
    zeilen = [json.loads(z) for z in proc.stdin.getvalue().splitlines()]
    assert zeilen[0]["method"] == "send" and zeilen[0]["params"] == {
        "recipient": ["+4915123456789"], "message": "Antwort"}
    assert zeilen[1]["params"] == {"noteToSelf": True, "message": "Notiz"}
    assert zeilen[2]["params"] == {"groupId": "abcdefgh12=", "message": "Gruppe"}
    assert [z["id"] for z in zeilen] == [1, 2, 3]


@pytest.mark.parametrize("ziel", ["", "49151", "+49 151", "group:", "group:a b", "evil;rm",
                                  "--config", "group:x"])
def test_signal_refuses_invalid_targets(signal, ziel: str) -> None:
    eins, _, _ = signal
    eins.start()
    assert wait_for(lambda: eins.status().state == CONNECTED)
    with pytest.raises(ValueError):
        eins.send(ziel, "hi")


def test_signal_does_not_send_when_not_connected(tmp_path: Path) -> None:
    eins = SignalTransport(tmp_path, lambda m: None, binary="signal-cli", popen=FakeSignal())
    with pytest.raises(RuntimeError, match="nicht verbunden"):
        eins.send("+4915123456789", "hi")


def test_a_bad_stored_number_is_never_passed_to_the_program(tmp_path: Path) -> None:
    fake = FakeSignal()
    NativeStore(tmp_path).set("signal", "+49; rm -rf /")
    eins = SignalTransport(tmp_path, lambda m: None, binary="signal-cli", popen=fake)
    eins.RESTARTS = 0
    eins.start()
    assert wait_for(lambda: eins.status().state == FAILED)
    assert not any("rm" in " ".join(a) for a in fake.aufrufe)
    eins.stop()


def test_signal_restarts_the_program_a_few_times_then_gives_up(tmp_path: Path) -> None:
    class Stirbt(FakeSignal):
        def __call__(self, args: list[str], **kwargs: Any) -> FakeProc:
            self.aufrufe.append(list(args))
            return FakeProc(args, [], rc=1)

    fake = Stirbt()
    NativeStore(tmp_path).set("signal", MY_NUMBER)
    eins = SignalTransport(tmp_path, lambda m: None, binary="signal-cli", popen=fake)
    eins.RESTARTS = 1
    original = threading.Event.wait
    threading.Event.wait = lambda self, timeout=None: False  # type: ignore[method-assign]
    try:
        eins.start()
        assert wait_for(lambda: len(fake.aufrufe) >= 2 and not eins.running)
    finally:
        threading.Event.wait = original  # type: ignore[method-assign]
    assert eins.status().state == FAILED and "beendet" in eins.status().error


def test_signal_unlink_deletes_the_session(signal, tmp_path) -> None:
    eins, fake, _ = signal
    eins.start()
    assert wait_for(lambda: eins.status().state == CONNECTED)
    (tmp_path / "messenger" / "signal" / "daten").write_text("x", encoding="utf-8")
    eins.unlink()
    assert not (tmp_path / "messenger" / "signal").exists()
    assert not eins.store.linked("signal") and fake.rpc[0].terminated


def test_signal_needs_the_program(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQUATICY_DATA_DIR", str(tmp_path / "daten"))
    monkeypatch.delenv("AQUATICY_SIGNAL_CLI", raising=False)
    monkeypatch.setattr(nat.shutil, "which", lambda name: None)
    ok, warum = SignalTransport(tmp_path, lambda m: None).available()
    assert not ok and "signal-cli" in warum
    # Seit Terra v2 muss der eingetragene Pfad eine Datei sein (sonst gaebe es erst beim Start
    # einen Fehler); ein falscher Pfad zaehlt als "nicht da".
    monkeypatch.setenv("AQUATICY_SIGNAL_CLI", str(tmp_path / "gibt-es-nicht"))
    assert not SignalTransport(tmp_path, lambda m: None).available()[0]
    programm = tmp_path / "signal-cli"
    programm.write_text("#!/bin/sh\n")
    monkeypatch.setenv("AQUATICY_SIGNAL_CLI", str(programm))
    assert SignalTransport(tmp_path, lambda m: None).available() == (True, "")
    monkeypatch.delenv("AQUATICY_SIGNAL_CLI")
    monkeypatch.setattr(nat.shutil, "which", lambda name: "/usr/bin/signal-cli")
    assert SignalTransport(tmp_path, lambda m: None).available()[0]


# -- Der Hub ------------------------------------------------------------------------------------
class StubTransport(nat.Transport):
    messenger = "whatsapp"

    def __init__(self, directory: Path, on_message: Any, on_connected: Any = None,
                 clock: Any = time.time, *, ok: bool = True, name: str = "whatsapp") -> None:
        super().__init__(directory, on_message, on_connected, clock)
        self.messenger = name
        self.ok = ok
        self.started = 0
        self.stopped = 0
        self.sent: list[tuple[str, str]] = []

    def available(self) -> tuple[bool, str]:
        return (True, "") if self.ok else (False, "fehlt")

    def start(self) -> None:
        self.started += 1
        self._set(CONNECTED, who="+4915100000000")
        self._thread = threading.Thread(target=lambda: time.sleep(5), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.stopped += 1
        self._set(OFF)

    def unlink(self) -> None:
        self.stop()
        self._wipe_session()

    def send(self, chat: str, text: str) -> None:
        self.sent.append((chat, text))


def stub_factory(ok: bool = True, name: str = "whatsapp"):
    return lambda directory, on_message, on_connected=None, clock=time.time: StubTransport(
        directory, on_message, on_connected, clock, ok=ok, name=name)


def make_hub(tmp_path: Path, antworten: list[Any], wanted: bool = True,
             ok: bool = True) -> NativeHub:
    return NativeHub(
        tmp_path / "messenger", lambda m, t: antworten.append((m, t)), lambda name: wanted,
        factories={"whatsapp": stub_factory(ok), "signal": stub_factory(ok, "signal")})


def message(text: str = "hi") -> Incoming:
    return Incoming("whatsapp", f"{OTHER}@s.whatsapp.net", text, "id1", time.time(),
                    f"+{OTHER}")


def test_the_hub_refuses_unknown_messengers(tmp_path: Path) -> None:
    hub = make_hub(tmp_path, [])
    with pytest.raises(ValueError):
        hub.transport("telegram")


def test_linking_needs_the_library_and_says_so(tmp_path: Path) -> None:
    hub = make_hub(tmp_path, [], ok=False)
    with pytest.raises(RuntimeError, match="fehlt"):
        hub.link("whatsapp")
    assert hub.transport("whatsapp").started == 0
    assert hub.available("whatsapp") == (False, "fehlt")


def test_linking_starts_the_connection(tmp_path: Path) -> None:
    hub = make_hub(tmp_path, [])
    status = hub.link("whatsapp")
    assert hub.transport("whatsapp").started == 1 and status.state == CONNECTED
    hub.stop()


def test_messages_go_to_the_responder_one_after_the_other(tmp_path: Path) -> None:
    antworten: list[Any] = []
    hub = make_hub(tmp_path, antworten)
    transport = hub.transport("whatsapp")
    for n in range(3):
        transport._deliver(message(f"nr {n}"))
    assert wait_for(lambda: len(antworten) == 3)
    assert [m.text for m, _ in antworten] == ["nr 0", "nr 1", "nr 2"]
    assert all(t is transport for _, t in antworten)
    hub.stop()


def test_a_flood_is_dropped_not_queued_without_end(tmp_path: Path) -> None:
    release = threading.Event()
    gesehen: list[str] = []

    def langsam(m: Incoming, t: Any) -> None:
        release.wait(5)
        gesehen.append(m.text)

    hub = NativeHub(tmp_path / "messenger", langsam, lambda n: True,
                    factories={"whatsapp": stub_factory(), "signal": stub_factory(True, "signal")})
    transport = hub.transport("whatsapp")
    for n in range(nat.QUEUE_SIZE + 10):
        transport._deliver(message(f"nr {n}"))
    assert hub.dropped >= 5
    release.set()
    assert wait_for(lambda: len(gesehen) >= nat.QUEUE_SIZE)
    hub.stop()


def test_an_error_in_the_responder_does_not_stop_the_worker(tmp_path: Path) -> None:
    aufrufe: list[str] = []

    def antwort(m: Incoming, t: Any) -> None:
        aufrufe.append(m.text)
        if m.text == "boese":
            raise RuntimeError("kaputt")

    hub = NativeHub(tmp_path / "messenger", antwort, lambda n: True,
                    factories={"whatsapp": stub_factory(), "signal": stub_factory(True, "signal")})
    transport = hub.transport("whatsapp")
    transport._deliver(message("boese"))
    transport._deliver(message("gut"))
    assert wait_for(lambda: aufrufe == ["boese", "gut"])
    hub.stop()


def test_ensure_running_starts_what_is_linked_and_wanted(tmp_path: Path) -> None:
    hub = make_hub(tmp_path, [], wanted=True)
    assert hub.ensure_running() == []
    NativeStore(tmp_path / "messenger").set("whatsapp", "+4915100000000")
    assert hub.ensure_running() == ["whatsapp"]
    assert hub.transport("whatsapp").started == 1 and hub.transport("signal").started == 0
    hub.stop()


def test_ensure_running_stops_a_connection_nobody_wants(tmp_path: Path) -> None:
    antworten: list[Any] = []
    gewollt = {"an": True}
    hub = NativeHub(tmp_path / "messenger", lambda m, t: antworten.append(m),
                    lambda n: gewollt["an"],
                    factories={"whatsapp": stub_factory(), "signal": stub_factory(True, "signal")})
    NativeStore(tmp_path / "messenger").set("whatsapp", "+4915100000000")
    hub.ensure_running()
    transport = hub.transport("whatsapp")
    assert transport.status().state == CONNECTED
    gewollt["an"] = False
    assert hub.ensure_running() == [] and transport.stopped == 1
    hub.stop()


def test_ensure_running_skips_a_missing_library(tmp_path: Path) -> None:
    hub = make_hub(tmp_path, [], ok=False)
    NativeStore(tmp_path / "messenger").set("whatsapp", "+4915100000000")
    assert hub.ensure_running() == [] and hub.transport("whatsapp").started == 0


def test_after_linking_a_switched_off_bridge_disconnects_again(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nat, "SETTLE_SECONDS", 0.05)
    hub = make_hub(tmp_path, [], wanted=False)
    hub.link("whatsapp")
    assert wait_for(lambda: hub.transport("whatsapp").stopped >= 1)
    hub.stop()


def test_a_wanted_connection_stays_after_linking(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nat, "SETTLE_SECONDS", 0.05)
    hub = make_hub(tmp_path, [], wanted=True)
    hub.link("whatsapp")
    time.sleep(0.3)
    assert hub.transport("whatsapp").stopped == 0
    hub.stop()


def test_unlink_cancels_the_timer_and_wipes(tmp_path: Path) -> None:
    hub = make_hub(tmp_path, [])
    NativeStore(tmp_path / "messenger").set("whatsapp", "+4915100000000")
    hub.unlink("whatsapp")
    assert not NativeStore(tmp_path / "messenger").linked("whatsapp")


def test_cancel_removes_a_half_finished_link_but_keeps_a_real_one(tmp_path: Path) -> None:
    hub = make_hub(tmp_path, [])
    transport = hub.transport("whatsapp")
    sitzung = tmp_path / "messenger" / "whatsapp"
    sitzung.mkdir(parents=True)
    (sitzung / "session.sqlite3").write_text("halb", encoding="utf-8")
    hub.cancel("whatsapp")
    assert not sitzung.exists() and transport.stopped == 1
    NativeStore(tmp_path / "messenger").set("whatsapp", "+4915100000000")
    sitzung.mkdir(parents=True)
    hub.cancel("whatsapp")
    assert sitzung.exists() and NativeStore(tmp_path / "messenger").linked("whatsapp")


def test_the_status_of_an_idle_link_still_names_who_is_linked(tmp_path: Path) -> None:
    hub = make_hub(tmp_path, [])
    NativeStore(tmp_path / "messenger").set("signal", "+4915100000000")
    status = hub.status("signal")
    assert status.state == OFF and status.who == "+4915100000000"


# -- Der echte neonize-Client (nur, wenn installiert) ---------------------------------------
def test_the_real_neonize_client_accepts_our_handlers(tmp_path: Path) -> None:
    """Prüft die Schnittstelle gegen die installierte Fassung -- ohne Netz zu brauchen."""
    pytest.importorskip("neonize.client")
    from neonize.client import NewClient
    from neonize.events import ConnectedEv, LoggedOutEv, MessageEv, PairStatusEv

    client = NewClient(str(tmp_path / "session.sqlite3"), uuid="aquaticy")

    @client.qr
    def _qr(c: Any, data: bytes) -> None: ...

    for klasse in (ConnectedEv, LoggedOutEv, MessageEv, PairStatusEv):
        client.event(klasse)(lambda c, e: None)
    for name in ("connect", "disconnect", "logout", "send_message"):
        assert callable(getattr(client, name))
    assert nat.neonize_available() == (True, "")


def test_the_real_neonize_client_dispatches_events_into_our_handlers(tmp_path: Path) -> None:
    """Der echte Weg von der Go-Bibliothek: QR, Gerät, Koppeln, Verbinden, Nachricht, Abmelden.

    Nur das Netz fehlt: Der Test ruft die Rückruf-Stellen des echten Clients so auf, wie es die
    Go-Seite tut (Adresse und Größe eines serialisierten Protobuf).
    """
    pytest.importorskip("neonize.client")
    import ctypes

    from neonize.client import NewClient
    from neonize.proto.Neonize_pb2 import Connected, Device, LoggedOut, PairStatus
    from neonize.proto.Neonize_pb2 import Message as MessageEv

    class Offline(NewClient):
        def connect(self, proxy_settings: Any = None) -> None:
            self._halt = threading.Event()
            self._halt.wait(10)

        def disconnect(self) -> None:
            self._halt.set()

    empfangen: list[Incoming] = []
    eins = WhatsAppTransport(tmp_path / "messenger", empfangen.append,
                             client_factory=lambda pfad, kennung: Offline(pfad, uuid=kennung))
    try:
        eins.start()
        assert wait_for(lambda: eins._client is not None and eins._client.event.list_func)
        client = eins._client
        assert client.event.list_func, "unsere Handler sind beim echten Client angemeldet"

        def pflicht(feld: Any) -> bool:
            if hasattr(feld, "is_required"):
                return bool(feld.is_required)
            return bool(feld.label == feld.LABEL_REQUIRED)

        def mehrfach(feld: Any) -> bool:
            if hasattr(feld, "is_repeated"):
                return bool(feld.is_repeated)
            return bool(feld.label == feld.LABEL_REPEATED)

        def auffuellen(nachricht: Any) -> None:
            """Die Go-Seite setzt alle Pflichtfelder (proto2); der Test tut es ihr nach."""
            for feld in nachricht.DESCRIPTOR.fields:
                if mehrfach(feld):
                    continue
                if feld.type == feld.TYPE_MESSAGE:
                    if pflicht(feld) or nachricht.HasField(feld.name):
                        auffuellen(getattr(nachricht, feld.name))
                    continue
                if pflicht(feld) and not nachricht.HasField(feld.name):
                    setattr(nachricht, feld.name, feld.default_value)

        def gehe(code: int, nachricht: Any) -> None:
            auffuellen(nachricht)
            daten = nachricht.SerializeToString()
            puffer = ctypes.create_string_buffer(daten, len(daten))
            client.event.execute(0, ctypes.addressof(puffer), len(daten), code)

        # QR-Code: die Go-Seite ruft __onQr mit der Adresse eines C-Textes auf.
        text = ctypes.create_string_buffer(b"2@AbCdEf,GhIjKl=,MnOpQr=,1")
        client._NewClient__onQr(0, ctypes.addressof(text))
        assert eins.status().state == QR and eins.status().qr == "2@AbCdEf,GhIjKl=,MnOpQr=,1"

        geraet = Device()
        geraet.JID.User, geraet.JID.Server = ME, "s.whatsapp.net"
        geraet.LID.User, geraet.LID.Server = "99887766", "lid"
        gehe(0, geraet)
        gekoppelt = PairStatus(Status=PairStatus.SUCCESS)
        gekoppelt.ID.User, gekoppelt.ID.Server = ME, "s.whatsapp.net"
        gehe(2, gekoppelt)
        assert eins.store.who("whatsapp") == f"+{ME}"
        gehe(3, Connected())
        assert eins.status().state == CONNECTED and eins.status().who == f"+{ME}"

        ev = MessageEv()
        ev.Info.MessageSource.Chat.User, ev.Info.MessageSource.Chat.Server = ME, "s.whatsapp.net"
        ev.Info.MessageSource.Sender.User = ME
        ev.Info.MessageSource.Sender.Server = "s.whatsapp.net"
        ev.Info.MessageSource.IsFromMe = True
        ev.Info.ID, ev.Info.Timestamp = "REAL1", 1_700_000_000_000
        ev.Message.conversation = "Wie spät ist es?"
        gehe(17, ev)
        assert [(m.text, m.self_chat, m.id) for m in empfangen] == [
            ("Wie spät ist es?", True, "REAL1")], "eigene Nummer und LID aus dem Geräte-Ereignis"

        gehe(6, LoggedOut())
        assert eins.status().state == FAILED and not eins.store.linked("whatsapp")
    finally:
        eins.stop()


def test_signal_with_a_real_process_and_real_pipes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mit einem echten Programm statt gestellter Rohre: Zeilenpuffer, Eingabe, Beenden."""
    import os
    import stat
    import sys

    log = tmp_path / "eingang.log"
    monkeypatch.setenv("SIGNAL_LOG", str(log))
    programm = tmp_path / "signal-cli"
    programm.write_text(f'''#!{sys.executable}
import json, os, sys, time
args = sys.argv[1:]
if "link" in args:
    print("sgnl://linkdevice?uuid=abc123def456&pub_key=XYZ789", flush=True)
    time.sleep(0.4)
    print("Associated with: +4915100000000", flush=True)
    sys.exit(0)
if "jsonRpc" in args:
    print(json.dumps({{"jsonrpc": "2.0", "method": "receive", "params": {{"envelope": {{
        "sourceNumber": "+4915123456789", "timestamp": 1700000000000,
        "dataMessage": {{"message": "Hallo"}}}}}}}}), flush=True)
    for zeile in sys.stdin:
        with open(os.environ["SIGNAL_LOG"], "a", encoding="utf-8") as f:
            f.write(json.dumps(args) + "|" + zeile)
        print(json.dumps({{"jsonrpc": "2.0", "id": json.loads(zeile)["id"], "result": {{}}}}),
              flush=True)
''', encoding="utf-8")
    programm.chmod(programm.stat().st_mode | stat.S_IEXEC)
    empfangen: list[Incoming] = []
    eins = SignalTransport(tmp_path / "messenger", empfangen.append, binary=str(programm))
    try:
        eins.start()
        assert wait_for(lambda: eins.status().state == QR, 10) or eins.status().state == CONNECTED
        assert wait_for(lambda: eins.status().state == CONNECTED, 10)
        assert eins.status().who == "+4915100000000"
        assert wait_for(lambda: len(empfangen) == 1, 10) and empfangen[0].text == "Hallo"
        eins.send("+4915123456789", "Antwort")
        assert wait_for(lambda: log.exists() and "Antwort" in log.read_text(encoding="utf-8"), 10)
        zeile = log.read_text(encoding="utf-8").splitlines()[0]
        args, anfrage = zeile.split("|", 1)
        assert json.loads(args)[-3:] == ["-a", "+4915100000000", "jsonRpc"]
        assert json.loads(anfrage)["params"] == {"recipient": ["+4915123456789"],
                                                 "message": "Antwort"}
        prozess = eins._proc
    finally:
        eins.stop()
    assert prozess.poll() is not None, "das Programm läuft nach dem Beenden nicht weiter"
    assert os.path.exists(programm) and eins.status().state == OFF
