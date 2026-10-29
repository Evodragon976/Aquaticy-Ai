"""12.7.9 Sol: "gelesen" und "schreibt ..." im Messenger, Slash-Befehle im Messenger."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from aquaticy import addons, bridge
from aquaticy import messenger_native as nat
from aquaticy.bridge import AgentAnswerer, Decision, parse_command, reply_limit
from aquaticy.bridge_native import ACKED_KEEP, MAX_INPUT_CHARS, NativeResponder, TypingIndicator
from aquaticy.config import Settings
from aquaticy.messenger_native import (
    CONNECTED,
    STARTING,
    Incoming,
    NativeHub,
    SignalTransport,
    WhatsAppTransport,
    message_parts,
)
from tests.test_bridge_native import ANNA, ICH, Antworter, Werkstatt, eigene
from tests.test_coworker import _suche_ohne_netz as _suche_ohne_netz
from tests.test_coworker import store as store
from tests.test_messenger_native import (
    Ev,
    FakeClient,
    jid,
    sig_data,
    wait_for,
)
from tests.test_messenger_native import (
    signal as signal,
)

ANNA_CHAT = f"{ANNA[1:]}@s.whatsapp.net"


# -- WhatsApp: gelesen und "schreibt ..." ---------------------------------------------------------
class MarkClient(FakeClient):
    def __init__(self, path: str, uuid: str = "") -> None:
        super().__init__(path, uuid)
        self.reads: list[tuple[Any, ...]] = []
        self.presences: list[tuple[Any, ...]] = []
        self.explode = False

    def mark_read(self, *ids: str, chat: Any, sender: Any, receipt: Any) -> None:
        if self.explode:
            raise RuntimeError("Netz weg")
        self.reads.append((ids, chat.User, chat.Server, sender.User, sender.Server, receipt))

    def send_chat_presence(self, ziel: Any, zustand: Any, medium: Any) -> None:
        if self.explode:
            raise RuntimeError("Netz weg")
        self.presences.append((ziel.User, ziel.Server, zustand, medium))


class EvWeg(Ev):
    DisconnectedEv = type("DisconnectedEv", (), {})


@pytest.fixture
def wa(tmp_path: Path):
    pytest.importorskip("neonize.utils.jid")
    FakeClient.instances = []
    eins = WhatsAppTransport(tmp_path / "messenger", lambda m: None, client_factory=MarkClient,
                             events=EvWeg)
    eins.start()
    assert wait_for(lambda: FakeClient.instances and FakeClient.instances[0].handlers)
    client = FakeClient.instances[0]
    yield eins, client
    eins.stop()


def verbinde(client: Any) -> None:
    client.handlers[EvWeg.ConnectedEv](client, SimpleNamespace())


def fremde(**kwargs: Any) -> Incoming:
    werte: dict[str, Any] = dict(
        messenger="whatsapp", chat=ANNA_CHAT, text="Hallo", id="ABC123", ts=time.time(),
        sender=ANNA, sender_id=ANNA_CHAT)
    werte.update(kwargs)
    return Incoming(**werte)


def test_a_direct_message_is_marked_read_with_the_read_receipt(wa) -> None:
    from neonize.utils.enum import ReceiptType

    eins, client = wa
    verbinde(client)
    eins.mark_read(fremde())
    assert client.reads == [(("ABC123",), ANNA[1:], "s.whatsapp.net", ANNA[1:],
                             "s.whatsapp.net", ReceiptType.READ)]


def test_in_a_group_the_receipt_names_the_sender(wa) -> None:
    eins, client = wa
    verbinde(client)
    eins.mark_read(fremde(chat="120363000000000000@g.us", group=True,
                          sender_id="4915111111111@s.whatsapp.net"))
    (_, chat, server, absender, _, _), = client.reads
    assert (chat, server, absender) == ("120363000000000000", "g.us", "4915111111111")
    eins.mark_read(fremde(chat="120363000000000000@g.us", group=True, sender_id=""))
    assert len(client.reads) == 1, "ohne geprueften Absender gibt es keine Meldung"


@pytest.mark.parametrize("aenderung", [
    {"from_me": True}, {"id": "A B"}, {"id": "A"}, {"id": ""}, {"id": "AB;rm"},
    {"chat": "evil"}, {"chat": "x@evil.example"},
])
def test_nothing_unchecked_or_own_is_marked_read(wa, aenderung: dict[str, Any]) -> None:
    eins, client = wa
    verbinde(client)
    eins.mark_read(fremde(**aenderung))
    assert client.reads == []


@pytest.mark.parametrize("aenderung", [{"from_me": True}, {"chat": "evil"},
                                       {"chat": "x@evil.example"}])
def test_typing_is_never_shown_in_own_or_unchecked_chats(wa, aenderung: dict[str, Any]) -> None:
    eins, client = wa
    verbinde(client)
    eins.typing(fremde(**aenderung), True)
    assert client.presences == []


def test_without_a_connection_nothing_is_sent(wa) -> None:
    eins, client = wa
    eins.mark_read(fremde())
    eins.typing(fremde(), True)
    assert client.reads == [] and client.presences == []


def test_a_failing_receipt_never_raises(wa) -> None:
    eins, client = wa
    verbinde(client)
    client.explode = True
    eins.mark_read(fremde())
    eins.typing(fremde(), True)
    eins.typing(fremde(), False)


def test_typing_on_and_off_map_to_composing_and_paused(wa) -> None:
    from neonize.utils.enum import ChatPresence, ChatPresenceMedia

    eins, client = wa
    verbinde(client)
    eins.typing(fremde(), True)
    eins.typing(fremde(), False)
    assert [p[2] for p in client.presences] == [ChatPresence.CHAT_PRESENCE_COMPOSING,
                                                ChatPresence.CHAT_PRESENCE_PAUSED]
    assert {p[3] for p in client.presences} == {ChatPresenceMedia.CHAT_PRESENCE_MEDIA_TEXT}
    assert client.presences[0][:2] == (ANNA[1:], "s.whatsapp.net")


def test_a_lost_connection_is_no_longer_shown_as_connected(wa) -> None:
    eins, client = wa
    verbinde(client)
    assert eins.status().state == CONNECTED
    client.handlers[EvWeg.DisconnectedEv](client, SimpleNamespace())
    assert eins.status().state == STARTING
    verbinde(client)
    assert eins.status().state == CONNECTED
    eins.stop()
    client.handlers[EvWeg.DisconnectedEv](client, SimpleNamespace())
    assert eins.status().state == nat.OFF, "nach stop() bleibt es aus"


def test_the_message_ids_in_a_whatsapp_event_are_read_from_it() -> None:
    from tests.test_messenger_native import OWN, parse_whatsapp, wa_event

    nachricht = parse_whatsapp(wa_event("Hi", sender=jid("4915111111111"),
                                        chat=jid("120363000000000000", "g.us"), gruppe=True),
                               OWN)
    assert nachricht.sender_id == "4915111111111@s.whatsapp.net"
    assert nachricht == parse_whatsapp(wa_event("Hi", sender=jid("4915111111111"),
                                                chat=jid("120363000000000000", "g.us"),
                                                gruppe=True), OWN), "gleich trotz Zusatzfeldern"


# -- Signal: gelesen und "schreibt ..." -----------------------------------------------------------
def zeilen(proc: Any) -> list[dict[str, Any]]:
    return [json.loads(z) for z in proc.stdin.getvalue().splitlines()]


def test_signal_sends_receipts_and_typing(signal) -> None:
    eins, fake, empfangen = signal
    fake.rpc_zeilen = [json.dumps({"jsonrpc": "2.0", "method": "receive",
                                   "params": sig_data("Hi")})]
    eins.start()
    assert wait_for(lambda: len(empfangen) == 1)
    nachricht = empfangen[0]
    assert nachricht.stamp == 1_700_000_000_000
    eins.mark_read(nachricht)
    eins.typing(nachricht, True)
    eins.typing(nachricht, False)
    gruppe = Incoming("signal", "group:abcdefgh12=", "Hi", "1:x", time.time(), ANNA, group=True,
                      stamp=1_700_000_000_001)
    eins.typing(gruppe, True)
    anfragen = zeilen(fake.rpc[0])
    assert anfragen[0]["method"] == "sendReceipt" and anfragen[0]["params"] == {
        "recipient": ANNA, "type": "read", "targetTimestamp": [1_700_000_000_000]}
    assert anfragen[1]["method"] == "sendTyping" and anfragen[1]["params"] == {"recipient": [ANNA]}
    assert anfragen[2]["params"] == {"recipient": [ANNA], "stop": True}
    assert anfragen[3]["params"] == {"groupId": "abcdefgh12="}


@pytest.mark.parametrize("aenderung", [
    {"from_me": True}, {"sender": "+49 151"}, {"sender": ""}, {"stamp": 0}, {"stamp": -5},
])
def test_signal_sends_no_receipt_for_unchecked_messages(signal, aenderung: dict[str, Any]) -> None:
    eins, fake, empfangen = signal
    fake.rpc_zeilen = [json.dumps({"jsonrpc": "2.0", "method": "receive",
                                   "params": sig_data("Hi")})]
    eins.start()
    assert wait_for(lambda: len(empfangen) == 1)
    werte = dict(messenger="signal", chat=ANNA, text="Hi", id="1:x", ts=time.time(), sender=ANNA,
                 stamp=1_700_000_000_000)
    werte.update(aenderung)
    eins.mark_read(Incoming(**werte))
    assert zeilen(fake.rpc[0]) == []


def test_signal_receipts_without_a_connection_are_silent(tmp_path: Path) -> None:
    eins = SignalTransport(tmp_path / "messenger", lambda m: None, binary="signal-cli")
    eins.mark_read(Incoming("signal", ANNA, "Hi", "1:x", time.time(), ANNA, stamp=5))
    eins.typing(Incoming("signal", ANNA, "Hi", "1:x", time.time(), ANNA), True)


def test_the_signal_timestamp_comes_from_the_envelope_only() -> None:
    assert nat.parse_signal(sig_data("Hi"), ICH).stamp == 1_700_000_000_000
    kaputt = sig_data("Hi")
    kaputt["envelope"]["timestamp"] = "oops"
    assert nat.parse_signal(kaputt, ICH).stamp == 0
    kaputt["envelope"]["timestamp"] = True
    assert nat.parse_signal(kaputt, ICH).stamp == 0


# -- Die Bruecke: gelesen und "schreibt ..." zur richtigen Zeit -----------------------------------
class Spur:
    """Ein Messenger, der aufschreibt, was in welcher Reihenfolge ankommt."""

    def __init__(self) -> None:
        self.ereignisse: list[str] = []
        self.sent: list[tuple[str, str]] = []

    def mark_read(self, nachricht: Incoming) -> None:
        self.ereignisse.append("gelesen")

    def typing(self, nachricht: Incoming, on: bool) -> None:
        self.ereignisse.append("schreibt" if on else "pause")

    def send(self, chat: str, text: str) -> None:
        self.ereignisse.append("gesendet")
        self.sent.append((chat, text))


class SpurAntworter(Antworter):
    def __init__(self, spur: Spur, antwort: str = "Es ist zehn Uhr.") -> None:
        super().__init__(antwort)
        self.spur = spur

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        self.spur.ereignisse.append("denkt")
        return super().__call__(*args, **kwargs)


def werkstatt(tmp_path: Path, **konfig: Any) -> tuple[Werkstatt, Spur]:
    w = Werkstatt(tmp_path, **konfig)
    spur = Spur()
    w.transport = spur  # type: ignore[assignment]
    w.antworter = SpurAntworter(spur)
    w.antwort = NativeResponder(lambda: w.konto, w.antworter, paused=lambda: w.pausiert[0],
                                clock=lambda: w.zeit[0])
    return w, spur


def test_read_comes_first_then_typing_then_the_answer(tmp_path: Path) -> None:
    w, spur = werkstatt(tmp_path)
    assert w.schicke(**{"id": "e1", **eigene()}) == "beantwortet"
    assert spur.ereignisse == ["gelesen", "schreibt", "denkt", "pause", "gesendet"]


def test_a_refused_message_gets_no_receipt_and_no_typing(tmp_path: Path) -> None:
    """Wer abgelehnt wird, soll nicht merken, dass hier jemand mitliest."""
    w, spur = werkstatt(tmp_path, wer="selbst")
    assert w.schicke().startswith("abgelehnt")
    assert spur.ereignisse == []
    assert w.antwort.acknowledge(w.nachricht(), spur).startswith("abgelehnt")
    assert spur.ereignisse == []


def test_nothing_is_shown_when_the_limit_is_reached_or_the_bridge_is_off(tmp_path: Path) -> None:
    w, spur = werkstatt(tmp_path)
    for i in range(bridge.MAX_REPLIES_PER_HOUR):
        bridge.count_reply(bridge.StateStore(w.konto), "whatsapp", w.zeit[0])
        del i
    assert w.schicke(**{"id": "g1", **eigene()}) == "grenze"
    assert w.antwort.acknowledge(w.nachricht(**eigene(), id="g2"), spur) == "grenze"
    assert spur.ereignisse == []
    w2, spur2 = werkstatt(tmp_path / "zwei", an=False)
    assert w2.antwort.acknowledge(w2.nachricht(**eigene()), spur2) == "aus"
    assert spur2.ereignisse == []


def test_typing_is_taken_away_when_the_answer_fails(tmp_path: Path) -> None:
    w, spur = werkstatt(tmp_path)
    w.antworter.fehler = RuntimeError("Modell weg")
    assert w.schicke(**{"id": "f1", **eigene()}) == "fehler"
    assert spur.ereignisse == ["gelesen", "schreibt", "denkt", "pause", "gesendet"]
    assert spur.sent[0][1].endswith("nicht geklappt. Versuch es gleich noch einmal.")


def test_acknowledge_marks_once_even_when_the_answer_follows(tmp_path: Path) -> None:
    w, spur = werkstatt(tmp_path)
    nachricht = w.nachricht(**{"id": "z1", **eigene()})
    assert w.antwort.acknowledge(nachricht, spur) == "gelesen"
    assert w.antwort.acknowledge(nachricht, spur) == "gelesen"
    assert w.antwort(nachricht, spur) == "beantwortet"
    assert spur.ereignisse.count("gelesen") == 1


def test_acknowledge_leaves_no_trace_so_the_answer_is_not_a_duplicate(tmp_path: Path) -> None:
    w, spur = werkstatt(tmp_path)
    nachricht = w.nachricht(**{"id": "z2", **eigene()})
    w.antwort.acknowledge(nachricht, spur)
    assert w.antwort(nachricht, spur) == "beantwortet"
    assert w.antwort(nachricht, spur) == "doppelt"


def test_the_list_of_acknowledged_messages_stays_small(tmp_path: Path) -> None:
    w, spur = werkstatt(tmp_path)
    for i in range(ACKED_KEEP + 25):
        w.antwort.acknowledge(w.nachricht(**{"id": f"m{i}", **eigene()}), spur)
    assert len(w.antwort._acked) == ACKED_KEEP


def test_a_transport_without_these_methods_still_answers(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path)  # sein Messenger kennt weder gelesen noch "schreibt ..."
    assert w.schicke(**{"id": "k1", **eigene()}) == "beantwortet"


def test_a_failing_receipt_does_not_stop_the_answer(tmp_path: Path) -> None:
    w, spur = werkstatt(tmp_path)

    def kaputt(*_: Any) -> None:
        raise RuntimeError("Netz weg")

    spur.mark_read = kaputt  # type: ignore[method-assign]
    spur.typing = kaputt  # type: ignore[method-assign]
    assert w.schicke(**{"id": "k2", **eigene()}) == "beantwortet"


def test_typing_is_renewed_while_working_and_stops_for_good() -> None:
    spur = Spur()
    nachricht = fremde()
    with TypingIndicator(spur, nachricht, interval=0.03):
        time.sleep(0.2)
    zahl = spur.ereignisse.count("schreibt")
    assert zahl >= 3 and spur.ereignisse[-1] == "pause"
    time.sleep(0.15)
    assert spur.ereignisse.count("schreibt") == zahl, "nach dem Ende kommt nichts mehr"


def test_typing_gives_up_after_its_limit() -> None:
    spur = Spur()
    with TypingIndicator(spur, fremde(), interval=0.02, limit=0.1):
        time.sleep(0.4)
        ende = spur.ereignisse.count("schreibt")
        time.sleep(0.1)
        assert spur.ereignisse.count("schreibt") == ende
    assert spur.ereignisse[-1] == "pause"


def test_a_hanging_transport_does_not_hold_up_the_answer() -> None:
    frei = threading.Event()

    class Haengt(Spur):
        def typing(self, nachricht: Incoming, on: bool) -> None:
            if not on:
                frei.wait(0.3)

    start = time.monotonic()
    with TypingIndicator(Haengt(), fremde(), interval=0.05):
        pass
    assert time.monotonic() - start < 2.0
    frei.set()


def test_very_long_messages_are_cut_before_a_model_sees_them(tmp_path: Path) -> None:
    w, _ = werkstatt(tmp_path)
    assert w.schicke(**{"id": "l1", **eigene("x" * (MAX_INPUT_CHARS * 3))}) == "beantwortet"
    assert len(w.antworter.aufrufe[0][0]) == MAX_INPUT_CHARS


# -- Der Hub: "gelesen" geht sofort, auch wenn Aquaticy noch antwortet ----------------------------
def test_receipts_do_not_wait_for_a_long_answer(tmp_path: Path) -> None:
    blockiert, frei = threading.Event(), threading.Event()
    gelesen: list[str] = []
    beantwortet: list[str] = []

    class Gespraechig:
        def __call__(self, nachricht: Incoming, transport: Any) -> None:
            blockiert.set()
            frei.wait(5)
            beantwortet.append(nachricht.id)

        def acknowledge(self, nachricht: Incoming, transport: Any) -> str:
            gelesen.append(nachricht.id)
            return "gelesen"

    hub = NativeHub(tmp_path / "messenger", Gespraechig(), lambda name: True,
                    factories={"whatsapp": lambda *a, **k: SimpleNamespace(), })
    hub.transport = lambda messenger: SimpleNamespace()  # type: ignore[method-assign]
    hub._enqueue("whatsapp", fremde(id="ERSTE1"))
    assert blockiert.wait(3)
    hub._enqueue("whatsapp", fremde(id="ZWEITE"))
    assert wait_for(lambda: gelesen == ["ERSTE1", "ZWEITE"]), gelesen
    assert beantwortet == [], "die erste Antwort laeuft noch"
    frei.set()
    assert wait_for(lambda: beantwortet == ["ERSTE1", "ZWEITE"])
    hub.stop()


def test_a_stale_stop_marker_never_strands_a_message(tmp_path: Path) -> None:
    """stop() ohne laufenden Arbeiter liess ein None zurueck, das den naechsten sofort beendete."""
    gesehen: list[str] = []
    hub = NativeHub(tmp_path / "messenger", lambda n, t: gesehen.append(n.id), lambda name: True)
    hub.transport = lambda messenger: SimpleNamespace()  # type: ignore[method-assign]
    hub.stop()
    hub._enqueue("whatsapp", fremde(id="NACH11"))
    assert wait_for(lambda: gesehen == ["NACH11"])
    hub.stop()


def test_a_workers_exit_never_strands_a_message(tmp_path: Path) -> None:
    gesehen: list[str] = []

    class Einfach:
        def __call__(self, nachricht: Incoming, transport: Any) -> None:
            gesehen.append(nachricht.id)

    hub = NativeHub(tmp_path / "messenger", Einfach(), lambda name: True)
    hub.transport = lambda messenger: SimpleNamespace()  # type: ignore[method-assign]
    hub._enqueue("whatsapp", fremde(id="EINS11"))
    assert wait_for(lambda: gesehen == ["EINS11"])
    # Der Arbeiter geht in den Ruhestand -- und der naechste Auftrag weckt einen neuen.
    hub._queue.put(None)
    assert wait_for(lambda: hub._worker is None)
    hub._enqueue("whatsapp", fremde(id="ZWEI22"))
    assert wait_for(lambda: gesehen == ["EINS11", "ZWEI22"])
    hub.stop()


# -- Geteilte Antworten behalten die Kennung ------------------------------------------------------
def test_every_part_of_a_split_answer_carries_the_signature() -> None:
    teile = message_parts("wort " * 2000)
    assert len(teile) >= 3 and all(t.startswith(bridge.SIGNATURE) for t in teile[1:])
    assert not teile[0].startswith(bridge.SIGNATURE), "der erste Teil hat sie schon"
    assert nat.SIGNATURE == bridge.SIGNATURE
    assert all(bridge.is_own_text(t) for t in teile[1:])
    assert message_parts("kurz") == ["kurz"]


# -- Slash-Befehle im Messenger -------------------------------------------------------------------
@pytest.mark.parametrize(("text", "erwartet"), [
    ("/help", ("help", "")),
    ("  /Help ", ("help", "")),
    ("/code-review def f(): pass\nreturn 1", ("code-review", "def f(): pass\nreturn 1")),
    ("/location  Bremen ", ("location", "Bremen")),
    ("/äpfel 3", ("äpfel", "3")),
    ("/usr/bin/python", None),
    ("/ 5 geteilt durch 2", None),
    ("/", None),
    ("hallo /help", None),
    ("//help", None),
    ("", None),
])
def test_only_a_leading_word_after_the_slash_is_a_command(text: str,
                                                          erwartet: Any) -> None:
    assert parse_command(text) == erwartet


class FakeAgent:
    gebaut: ClassVar[list[FakeAgent]] = []

    def __init__(self, settings: Any, erlaubt: frozenset[str], zusatz: str,
                 on_event: Any = None) -> None:
        self.settings = settings
        self.erlaubt = erlaubt
        self.messages = [{"role": "system"}]
        self.fragen: list[str] = []
        self.geschlossen = False
        FakeAgent.gebaut.append(self)

    def ask(self, auftrag: str, **kwargs: Any) -> Any:
        self.fragen.append(auftrag)
        self.messages.append({"role": "user", "content": auftrag})
        return SimpleNamespace(answer=f"Antwort auf: {auftrag[:30]}")

    def close(self) -> None:
        self.geschlossen = True


class Befehle:
    """Ein Antwortgeber mit gestellten Agenten und einem gestellten Besitzer-Zugang."""

    def __init__(self, tmp_path: Path, **dienste: Any) -> None:
        FakeAgent.gebaut = []
        self.konto = Settings(data_dir=tmp_path, env_path=tmp_path / ".env", model="test/modell")
        self.aufrufe: list[tuple[str, str]] = []
        self.sitzung_antwort: Any = "Notizen: keine."
        self.antworter = AgentAnswerer(lambda: self.konto, agent_factory=FakeAgent,
                                       session_command=self._sitzung)
        self.config = bridge.normalize_config({"an": True, "dienste": {"web": "an", **dienste}})

    def _sitzung(self, name: str, argument: str) -> str:
        self.aufrufe.append((name, argument))
        if isinstance(self.sitzung_antwort, Exception):
            raise self.sitzung_antwort
        return str(self.sitzung_antwort)

    def aktiv(self, *namen: str) -> None:
        for name in namen:
            addons._update(self.konto, name, installed=True, enabled=True)

    def frage(self, text: str, *, selbst: bool = False, vertraut: bool = False,
              key: str = "whatsapp:anna") -> str:
        entscheidung = Decision(True, trusted=vertraut or selbst, selbst=selbst)
        return self.antworter(text, entscheidung, self.config, key, "whatsapp")


@pytest.fixture
def b(tmp_path: Path) -> Befehle:
    return Befehle(tmp_path)


def test_help_depends_on_who_asks(b: Befehle) -> None:
    fremd = b.frage("/help")
    assert "/help" in fremd and "/clear" in fremd and "/location" in fremd
    assert "/model" not in fremd and "/memory" not in fremd
    vertraut = b.frage("/help", vertraut=True)
    assert "/model" in vertraut and "/memory" not in vertraut
    selbst = b.frage("/help", selbst=True)
    assert "/model" in selbst and "/memory" in selbst and "/forget" in selbst
    assert "/image (mobile)" in selbst and not FakeAgent.gebaut, "ein Befehl fragt kein Modell"


def test_help_lists_only_plugins_that_are_on_and_allowed(tmp_path: Path) -> None:
    b = Befehle(tmp_path, github="lesen")
    b.aktiv("wetter", "github", "code-review")

    def namen(**wer: Any) -> set[str]:
        return {z.split(":")[0].removesuffix(" (mobile)")
                for z in b.frage("/help", **wer).splitlines()}

    assert {"/wetter", "/code-review"} <= namen() and "/github" not in namen()
    assert "/github" in namen(vertraut=True), "GitHub braucht einen vertrauten Chat"
    assert "/feeds" not in namen(vertraut=True), "ausgeschaltete Plugins stehen nicht da"


def test_clear_forgets_this_chat_only(b: Befehle) -> None:
    b.frage("Hallo", key="whatsapp:anna")
    b.frage("Hallo", key="whatsapp:bernd")
    anna, bernd = FakeAgent.gebaut
    assert b.frage("/clear", key="whatsapp:anna") == "Verlauf verworfen."
    assert anna.geschlossen and not bernd.geschlossen
    b.frage("Noch einmal", key="whatsapp:anna")
    assert len(FakeAgent.gebaut) == 3 and FakeAgent.gebaut[2].messages == [{"role": "system"}, {
        "role": "user", "content": "Noch einmal"}]


def test_location_belongs_to_one_chat_and_never_to_the_app(b: Befehle) -> None:
    assert b.frage("/location Bremen", key="whatsapp:anna") == "Ortsfilter: Bremen"
    b.frage("Wetter?", key="whatsapp:anna")
    b.frage("Wetter?", key="whatsapp:bernd")
    anna, bernd = FakeAgent.gebaut
    assert anna.settings.location == "Bremen" and bernd.settings.location != "Bremen"
    assert b.konto.location != "Bremen", "die Einstellungen der App bleiben, wie sie sind"
    assert b.frage("/location", key="whatsapp:anna") == "Ortsfilter aufgehoben."
    b.frage("Wetter?", key="whatsapp:anna")
    assert FakeAgent.gebaut[-1].settings.location != "Bremen"


def test_location_is_cleaned_and_bounded(b: Befehle) -> None:
    antwort = b.frage("/location Brem\x00en\x07 " + "x" * 500)
    assert "\x00" not in antwort and "\x07" not in antwort
    assert len(antwort) <= len("Ortsfilter: ") + bridge.LOCATION_CHARS
    for i in range(bridge.MAX_LOCATIONS + 20):
        b.frage(f"/location Ort{i}", key=f"whatsapp:{i}")
    assert len(b.antworter._locations) == bridge.MAX_LOCATIONS


def test_model_is_shown_to_trusted_chats_only_and_never_changed(b: Befehle) -> None:
    assert b.frage("/model") == "Das geht hier nicht."
    antwort = b.frage("/model", vertraut=True)
    assert "test/modell" in antwort and "/switch" in antwort
    assert b.konto.model == "test/modell"


@pytest.mark.parametrize("befehl", ["/image"])
def test_these_only_work_in_the_app(b: Befehle, befehl: str) -> None:
    assert b.frage(befehl, selbst=True) == "Das geht nur in der App."
    assert not FakeAgent.gebaut


@pytest.mark.parametrize("befehl", ["/memory", "/notes", "/notes delete 3", "/history",
                                    "/uploads clear", "/forget"])
def test_your_own_data_is_reachable_from_your_own_chat_only(b: Befehle, befehl: str) -> None:
    for wer in ({}, {"vertraut": True}):
        assert b.frage(befehl, **wer) == "Das geht nur in deinem eigenen Chat."
    assert b.aufrufe == [], "fuer andere wird gar nichts aufgerufen"
    assert b.frage(befehl, selbst=True) == "Notizen: keine."
    name, _, rest = befehl[1:].partition(" ")
    assert b.aufrufe == [(name, rest)]


def test_a_failing_data_command_gives_a_friendly_text(b: Befehle) -> None:
    b.sitzung_antwort = RuntimeError("Datenbank gesperrt: /home/x/secret.db")
    antwort = b.frage("/memory", selbst=True)
    assert "nicht geklappt" in antwort and "secret" not in antwort
    b.sitzung_antwort = ""
    assert b.frage("/memory", selbst=True) == "Fertig."


def test_data_commands_need_the_owner_hook() -> None:
    antworter = AgentAnswerer(lambda: Settings())
    entscheidung = Decision(True, trusted=True, selbst=True)
    config = bridge.normalize_config({"an": True})
    assert antworter("/memory", entscheidung, config, "k", "whatsapp") == "Das geht nur in der App."


def test_unknown_commands_are_named_and_cost_nothing(b: Befehle) -> None:
    antwort = b.frage("/gibtsnicht abc")
    assert antwort.startswith("Unbekannter Befehl /gibtsnicht") and "/help" in antwort
    assert len(b.frage("/" + "a" * 500)) < 100
    assert not FakeAgent.gebaut


def test_a_path_is_not_a_command(b: Befehle) -> None:
    assert b.frage("/usr/bin/python starten?").startswith("Antwort auf: /usr/bin/python")


def test_a_plugin_command_reaches_the_model_with_its_hint(b: Befehle) -> None:
    b.aktiv("wetter")
    antwort = b.frage("/wetter Bremen morgen")
    assert antwort.startswith("Antwort auf: [Plugin Wetter")
    frage = FakeAgent.gebaut[0].fragen[0]
    assert "Bremen morgen" in frage and "weather" in frage


def test_a_plugin_needs_its_tool_in_this_chat(tmp_path: Path) -> None:
    b = Befehle(tmp_path)
    b.config = bridge.normalize_config({"an": True, "dienste": {"web": "aus"}})
    b.aktiv("wetter")
    antwort = b.frage("/wetter Bremen")
    assert "darf ich" in antwort and "nicht" in antwort and not FakeAgent.gebaut


def test_a_plugin_that_is_off_is_not_a_command(b: Befehle) -> None:
    antwort = b.frage("/wetter Bremen")
    assert "aus" in antwort and "Add-ons" in antwort and not FakeAgent.gebaut


def test_a_plugin_without_text_explains_itself_or_uses_its_default(b: Befehle) -> None:
    b.aktiv("wetter", "nachrichten")
    assert "Wetter" in b.frage("/wetter") and not FakeAgent.gebaut
    b.frage("/nachrichten")
    assert "wichtigsten Meldungen" in FakeAgent.gebaut[0].fragen[0]


def test_github_is_for_trusted_chats_with_the_service_on(tmp_path: Path) -> None:
    b = Befehle(tmp_path, github="lesen")
    b.aktiv("github")
    assert "nicht" in b.frage("/github offene Pull Requests") and not FakeAgent.gebaut
    assert b.frage("/github offene Pull Requests", vertraut=True).startswith("Antwort auf")


def test_feeds_show_what_the_owner_reads_so_strangers_do_not_get_them(tmp_path: Path) -> None:
    config = bridge.normalize_config({"an": True, "dienste": {"web": "an"}})
    assert "read_feeds" not in bridge.allowed_tools(config, False)
    assert "read_feeds" in bridge.allowed_tools(config, True)
    b = Befehle(tmp_path)
    b.aktiv("feeds")
    assert "nicht" in b.frage("/feeds Was gibt es Neues?")
    assert b.frage("/feeds Was gibt es Neues?", vertraut=True).startswith("Antwort auf")


def test_reviews_are_text_work_with_more_room(b: Befehle) -> None:
    b.aktiv("code-review", "security-review")
    # Der Code hinter dem Befehl ist nur Text fuer ein gestelltes Modell -- er laeuft nie.
    b.frage("/code-review def f(x):\n    return eval(x)")
    frage = FakeAgent.gebaut[0].fragen[0]
    assert "Zu prüfen:" in frage and "return eval(x)" in frage and "2800 Zeichen" in frage
    b.frage("/security-review SELECT * FROM t WHERE id=' + user", key="whatsapp:b")
    assert "Zu prüfen:" in FakeAgent.gebaut[1].fragen[0]
    assert "Dateien lese ich hier nicht" in b.frage("/code-review")
    assert reply_limit("/code-review x") == bridge.REVIEW_REPLY_CHARS
    assert reply_limit("/Security-Review x") == bridge.REVIEW_REPLY_CHARS
    assert reply_limit("/wetter Bremen") == bridge.MAX_REPLY_CHARS
    assert reply_limit("Hallo") == bridge.MAX_REPLY_CHARS


def test_add_ons_without_a_messenger_command_go_to_the_app(b: Befehle) -> None:
    b.aktiv("blender", "whatsapp", "signal")
    for befehl in ("/blender Wuerfel", "/whatsapp Was ist neu?", "/signal hi"):
        assert b.frage(befehl, selbst=True) == "Das geht nur in der App.", befehl
    assert b.frage("/gibtsnicht", selbst=True).startswith("Unbekannter Befehl")
    assert not FakeAgent.gebaut


# -- Befehle ueber den ganzen Weg (Antwortgeber -> Text im Chat) ----------------------------------
def test_a_review_reply_may_be_longer_than_a_normal_one(tmp_path: Path) -> None:
    w, spur = werkstatt(tmp_path)
    w.antworter.antwort = "wort " * 600  # 3000 Zeichen
    w.schicke(**{"id": "r1", **eigene("Was gibt es Neues?")})
    normal = spur.sent[-1][1]
    w.schicke(**{"id": "r2", **eigene("/code-review def f(): pass")})
    review = spur.sent[-1][1]
    assert len(normal) < len(review) <= bridge.REVIEW_REPLY_CHARS + 60
    assert normal.endswith("(Mehr in der App.)") and len(normal) <= bridge.MAX_REPLY_CHARS + 60


def test_a_command_is_not_mistaken_for_a_question_to_your_mail(tmp_path: Path) -> None:
    w, _ = werkstatt(tmp_path)
    assert w.schicke(**{"id": "c1", **eigene("Zeig mir meine Mails")}) == "beantwortet"
    assert w.antworter.aufrufe == [], "Mail ist aus: die Bruecke antwortet selbst"
    assert w.schicke(**{"id": "c2", **eigene("/code-review # zeig meine Mails\nx = 1")}) \
        == "beantwortet"
    assert len(w.antworter.aufrufe) == 1, "ein Befehl geht an den Antwortgeber"


def test_the_commands_of_the_screen_bridge_use_the_same_answerer() -> None:
    import inspect

    quelle = inspect.getsource(bridge.Bridge)
    assert "self._answerer(auftrag, entscheidung, config, key, messenger)" in quelle


# -- Coworker-Meldungen im Messenger ------------------------------------------------------------
class EigenerChat(nat.Transport):
    """Ein Messenger, der aufschreibt, was er dem Besitzer schickt."""

    messenger = "whatsapp"

    def __init__(self, directory: Path, on_message: Any, on_connected: Any = None,
                 clock: Any = time.time, *, name: str = "whatsapp") -> None:
        super().__init__(directory, on_message, on_connected, clock)
        self.messenger = name
        self.sent: list[tuple[str, str]] = []
        self.fehler = False

    def available(self) -> tuple[bool, str]:
        return True, ""

    def own_chat(self) -> str:
        return "4915100000000@s.whatsapp.net" if self.messenger == "whatsapp" else "self"

    def send(self, chat: str, text: str) -> None:
        if self.fehler:
            raise RuntimeError("Netz weg")
        self.sent.append((chat, text))


def hub_fuer_meldungen(tmp_path: Path, *, gewollt: bool = True, ruht: bool = False,
                       uhr: Any = time.time) -> NativeHub:
    zustand = {"ruht": ruht}
    hub = NativeHub(
        tmp_path / "messenger", lambda m, t: None, lambda name: gewollt,
        factories={n: (lambda d, m, on_connected=None, clock=time.time, n=n: EigenerChat(
            d, m, on_connected, clock, name=n)) for n in nat.MESSENGERS},
        paused=lambda: zustand["ruht"], clock=uhr)
    hub.zustand = zustand  # type: ignore[attr-defined]
    return hub


def verbunden(hub: NativeHub, name: str = "whatsapp", nummer: str = "+4915100000000") -> Any:
    nat.NativeStore(hub.directory).set(name, nummer)
    eins = hub.transport(name)
    eins._set(CONNECTED, who=nummer)
    return eins


def test_the_message_names_the_coworker_and_then_comes_the_text() -> None:
    from aquaticy.bridge_native import coworker_text

    assert coworker_text("Ava", "Meldung", "Drei neue Mails.") == (
        "[Aquaticy] Coworker Ava\nDrei neue Mails.")
    assert coworker_text("Ava", "Antwort", "Ja.") == "[Aquaticy] Coworker Ava\nJa."
    assert coworker_text("Ava", "Wetter morgen", "Sonnig.") == (
        "[Aquaticy] Coworker Ava · Wetter morgen\nSonnig.")
    assert coworker_text("Ava", "", "**Fett** und [Link](https://a.example)").endswith(
        "Fett und Link (https://a.example)")


def test_a_question_says_where_to_answer_and_an_approval_says_to_open_the_app() -> None:
    from aquaticy.bridge_native import coworker_text

    frage = coworker_text("Ava", "Frage", "Soll ich den Termin verschieben?", frage=True)
    assert frage.startswith("[Aquaticy] Coworker Ava\nSoll ich") and frage.endswith(
        "Antworten kannst du in der App.")
    freigabe = coworker_text("Ava", "Freigabe", "geheimer Text", freigabe=True)
    assert freigabe == "[Aquaticy] Coworker Ava\nWartet auf deine Freigabe. Öffne die App."


def test_payment_data_never_leave_through_a_coworker_message() -> None:
    from aquaticy.bridge_native import coworker_text

    text = coworker_text("Ava", "Mail", "Bitte zahle auf DE89 3704 0044 0532 0130 00")
    assert "DE89" not in text and "Zahlungsdaten" in text and text.startswith("[Aquaticy] Coworker")


def test_the_name_and_length_of_a_message_are_bounded() -> None:
    from aquaticy.bridge_native import COWORKER_REPLY_CHARS, coworker_text

    lang = coworker_text("A\x00v\x07a" + "x" * 100, "T" * 500, "wort " * 5000)
    assert "\x00" not in lang and "\x07" not in lang
    assert len(lang) <= COWORKER_REPLY_CHARS + 60 < nat.MAX_SEND_CHARS
    assert coworker_text("", "", "Hallo").startswith("[Aquaticy] Coworker Coworker\n")
    assert bridge.is_own_text(lang), "kommt es als Echo zurueck, ist es keine Frage"


def test_the_owner_gets_the_message_in_the_own_chat_of_every_linked_messenger(
        tmp_path: Path) -> None:
    hub = hub_fuer_meldungen(tmp_path)
    wa, sg = verbunden(hub), verbunden(hub, "signal")
    assert hub.notify_owner("[Aquaticy] Coworker Ava\nHallo") == ["whatsapp", "signal"]
    assert wa.sent == [("4915100000000@s.whatsapp.net", "[Aquaticy] Coworker Ava\nHallo")]
    assert sg.sent == [("self", "[Aquaticy] Coworker Ava\nHallo")]


def test_nothing_goes_out_when_not_linked_not_switched_on_or_paused(tmp_path: Path) -> None:
    hub = hub_fuer_meldungen(tmp_path)
    hub.transport("whatsapp")._set(CONNECTED)
    assert hub.notify_owner("x") == [], "nicht gekoppelt"
    aus = hub_fuer_meldungen(tmp_path / "aus", gewollt=False)
    eins = verbunden(aus)
    assert aus.notify_owner("x") == [] and eins.sent == [], "die Bruecke ist aus"
    pause = hub_fuer_meldungen(tmp_path / "pause", ruht=True)
    eins = verbunden(pause)
    assert pause.notify_owner("x") == [] and eins.sent == [], "kein Ultra, gesperrt oder Verbund"


def test_a_failing_send_is_reported_as_not_sent_and_never_raises(tmp_path: Path) -> None:
    hub = hub_fuer_meldungen(tmp_path)
    eins = verbunden(hub)
    eins.fehler = True
    assert hub.notify_owner("x") == []


def test_a_message_waits_for_the_connection_and_goes_out_when_it_is_back(
        tmp_path: Path) -> None:
    hub = hub_fuer_meldungen(tmp_path)
    nat.NativeStore(hub.directory).set("whatsapp", "+4915100000000")
    eins = hub.transport("whatsapp")
    eins._set(STARTING)
    assert hub.notify_owner("erste") == [] and hub.notify_owner("zweite") == []
    eins._set(CONNECTED)  # meldet "verbunden": die wartenden gehen in einem eigenen Faden raus
    assert wait_for(lambda: [t for _, t in eins.sent] == ["erste", "zweite"])
    eins._set(CONNECTED)
    time.sleep(0.1)
    assert len(eins.sent) == 2, "jede Meldung geht nur einmal"


def test_waiting_messages_expire_and_stay_few(tmp_path: Path) -> None:
    jetzt = [1000.0]
    hub = hub_fuer_meldungen(tmp_path, uhr=lambda: jetzt[0])
    nat.NativeStore(hub.directory).set("whatsapp", "+4915100000000")
    eins = hub.transport("whatsapp")
    eins._set(STARTING)
    hub.notify_owner("uralt")
    jetzt[0] += nat.NOTIFY_KEEP_SECONDS + 1
    for i in range(nat.NOTIFY_QUEUE + 5):
        hub.notify_owner(f"neu{i}")
    assert len(hub._pending["whatsapp"]) == nat.NOTIFY_QUEUE
    eins._set(CONNECTED)
    assert wait_for(lambda: len(eins.sent) == nat.NOTIFY_QUEUE)
    assert "uralt" not in [t for _, t in eins.sent]
    assert [t for _, t in eins.sent][-1] == f"neu{nat.NOTIFY_QUEUE + 4}"


def test_a_waiting_message_is_dropped_when_the_bridge_was_switched_off_meanwhile(
        tmp_path: Path) -> None:
    an = {"an": True}
    hub = NativeHub(tmp_path / "messenger", lambda m, t: None, lambda name: an["an"],
                    factories={n: (lambda d, m, on_connected=None, clock=time.time, n=n:
                                   EigenerChat(d, m, on_connected, clock, name=n))
                               for n in nat.MESSENGERS})
    nat.NativeStore(hub.directory).set("whatsapp", "+4915100000000")
    eins = hub.transport("whatsapp")
    eins._set(STARTING)
    hub.notify_owner("wartet")
    an["an"] = False
    eins._set(CONNECTED)
    time.sleep(0.2)
    assert eins.sent == []


def test_at_most_so_many_messages_per_hour(tmp_path: Path) -> None:
    jetzt = [1000.0]
    hub = hub_fuer_meldungen(tmp_path, uhr=lambda: jetzt[0])
    eins = verbunden(hub)
    for i in range(nat.NOTIFY_PER_HOUR + 10):
        hub.notify_owner(f"m{i}")
    assert len(eins.sent) == nat.NOTIFY_PER_HOUR
    jetzt[0] += 3601
    assert hub.notify_owner("wieder") == ["whatsapp"]


def test_the_account_is_found_by_its_folder_and_forgotten_after_stop(tmp_path: Path) -> None:
    konto = Settings(data_dir=tmp_path / "konto", env_path=tmp_path / ".env")
    hub = hub_fuer_meldungen(tmp_path / "konto")
    eins = verbunden(hub)
    assert nat.notify_owner(konto, "Hallo") == ["whatsapp"] and eins.sent
    fremd = Settings(data_dir=tmp_path / "anderes", env_path=tmp_path / ".env")
    assert nat.notify_owner(fremd, "Hallo") == [], "ein anderes Konto hat andere Kopplungen"
    hub.stop()
    assert nat.notify_owner(konto, "Hallo") == []


def test_the_own_chat_comes_from_the_stored_number_only(tmp_path: Path) -> None:
    store = nat.NativeStore(tmp_path)
    wa = nat.WhatsAppTransport(tmp_path, lambda m: None)
    sg = nat.SignalTransport(tmp_path, lambda m: None, binary="x")
    assert wa.own_chat() == "" and sg.own_chat() == ""
    store.set("whatsapp", "+49 151 00000000")
    store.set("signal", "+4915100000000")
    assert wa.own_chat() == "4915100000000@s.whatsapp.net" and sg.own_chat() == "self"
    store.set("whatsapp", "0151 kaputt")
    assert wa.own_chat() == ""


# Der ganze Weg: ein Coworker-Schritt -> Nachricht im Messenger
def melden(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    gesendet: list[str] = []
    monkeypatch.setattr(nat, "notify_owner", lambda settings, text: gesendet.append(text) or [])
    return gesendet


def test_a_report_of_a_coworker_reaches_the_messenger(monkeypatch, settings, store) -> None:
    from tests.test_agent import _message, _tool_call
    from tests.test_coworker import _neu, _schritt

    gesendet = melden(monkeypatch)
    kollege = _neu(store, chat="chat-ava")
    store.add_log(kollege.id, "nachricht", "Gibt es schon etwas?")
    _schritt(monkeypatch, settings, store, kollege,
             _message(tool_calls=[_tool_call("coworker_report", {
                 "titel": "Erste Übersicht", "text": "**Drei** wichtige Mails."}, "c1")]),
             _message(content="Gemeldet."))
    assert gesendet == ["[Aquaticy] Coworker Ava · Erste Übersicht\nDrei wichtige Mails."]


def test_a_question_and_a_waiting_approval_reach_the_messenger(
        monkeypatch, settings, store) -> None:
    from tests.test_agent import _message, _tool_call
    from tests.test_coworker import _neu, _schritt

    gesendet = melden(monkeypatch)
    kollege = _neu(store)
    _schritt(monkeypatch, settings, store, kollege,
             _message(tool_calls=[_tool_call("coworker_report", {
                 "titel": "Frage", "text": "Termin verschieben?", "frage": True}, "c1")]),
             _message(content="Gefragt."))
    assert gesendet == ["[Aquaticy] Coworker Ava\nTermin verschieben?\n\n"
                        "Antworten kannst du in der App."]


def test_a_scheduled_coworker_sends_its_answer_every_time(monkeypatch, settings) -> None:
    from aquaticy import coworker as cw
    from tests.test_agent import ScriptedLLM, _message

    gesendet = melden(monkeypatch)
    store = cw.CoworkerStore(settings.db_path)
    kollege = store.add("Ava", "Was gibt es Neues beim Lastenrad?", plan="normal",
                        schedule={"kind": "research", "structured": False})
    llm = ScriptedLLM(_message(content="Neu: **Preis** gesunken."))
    monkeypatch.setattr("litellm.completion", llm)
    assert cw.run_scheduled(kollege, settings, "normal", store=store) == "fertig"
    assert gesendet == ["[Aquaticy] Coworker Ava\nNeu: Preis gesunken."]


def test_a_failing_messenger_never_breaks_a_coworker_step(monkeypatch, settings, store) -> None:
    from aquaticy import coworker as cwm
    from tests.test_agent import _message, _tool_call
    from tests.test_coworker import _neu, _schritt

    def kaputt(settings: Any, text: str) -> list[str]:
        raise RuntimeError("Hub kaputt")

    monkeypatch.setattr(nat, "notify_owner", kaputt)
    kollege = _neu(store)
    zustand, _ = _schritt(monkeypatch, settings, store, kollege,
                          _message(tool_calls=[_tool_call("coworker_report", {
                              "titel": "T", "text": "Text"}, "c1")]),
                          _message(content="Fertig."))
    assert zustand == "fertig" and store.log(kollege.id)[0]["kind"] in ("schritt", "meldung")
    cwm.push_to_messenger(settings, kollege, "T", "Text")  # wirft nicht
