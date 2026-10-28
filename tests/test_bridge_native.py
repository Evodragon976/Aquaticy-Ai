"""Die Brücke über die direkte Kopplung (aquaticy/bridge_native.py): wer antwortet wem, mit was."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aquaticy import bridge
from aquaticy.bridge import decide_native, matches_exact_number, normalize_config, to_chat_text
from aquaticy.bridge_native import FAIL_TEXT, NativeResponder
from aquaticy.config import Settings
from aquaticy.messenger_native import MAX_AGE_SECONDS, Incoming

ICH = "+4915100000000"
ANNA = "+4915123456789"
BERND = "+4915199999999"


def cfg(**kwargs: Any) -> dict[str, Any]:
    dienste = kwargs.pop("dienste", {})
    return normalize_config({"an": True, **kwargs, "dienste": dienste})


# -- Nummern ----------------------------------------------------------------------------------
@pytest.mark.parametrize(("nummer", "eintrag", "erwartet"), [
    (ANNA, "+49 151 23456789", True),
    (ANNA, "+4915123456789", True),
    (ANNA, "0049 151 23456789", True),
    (ANNA, "0151 23456789", False),
    (ANNA, "151 23456789", False),
    ("+4415123456789", "0151 23456789", False),
    ("+4915123456780", "+49 151 23456789", False),
    ("+4915123456789", "+44 151 23456789", False),
    (ANNA, "Anna", False),
    (ANNA, "", False),
    ("", "+49 151 23456789", False),
    (ANNA, "+49 15", False),
    (ANNA, "+49 151 23456789; rm", False),
    (ANNA, "+49151234567890", False),
])
def test_real_numbers_match_exactly(nummer: str, eintrag: str, erwartet: bool) -> None:
    assert matches_exact_number(nummer, eintrag) is erwartet


def test_a_number_without_country_code_never_matches() -> None:
    """Dieselben Endziffern gibt es in anderen Ländern -- so käme ein Fremder an deine Dienste."""
    assert not matches_exact_number("+49151234567", "0151 234567")
    assert not matches_exact_number("+44151234567", "0151 234567")
    assert not matches_exact_number("+151234567", "0151 234567")


# -- Wer darf? ---------------------------------------------------------------------------------
@pytest.mark.parametrize(("wer", "kwargs", "erlaubt", "vertraut"), [
    ("selbst", dict(group=False, self_chat=True, number=""), True, True),
    ("selbst", dict(group=False, self_chat=False, number=ANNA), False, False),
    ("selbst", dict(group=True, self_chat=False, number=ANNA), False, False),
    ("nummern", dict(group=False, self_chat=False, number=ANNA), True, True),
    ("nummern", dict(group=False, self_chat=False, number=BERND), False, False),
    ("nummern", dict(group=False, self_chat=False, number=""), False, False),
    ("nummern", dict(group=True, self_chat=False, number=ANNA), False, False),
    ("einzeln", dict(group=False, self_chat=False, number=ANNA), True, True),
    ("einzeln", dict(group=False, self_chat=False, number=BERND), True, False),
    ("einzeln", dict(group=False, self_chat=False, number=""), True, False),
    ("einzeln", dict(group=True, self_chat=False, number=ANNA), False, False),
    ("gruppen", dict(group=True, self_chat=False, number=ANNA), True, False),
    ("gruppen", dict(group=False, self_chat=False, number=BERND), True, False),
])
def test_the_matrix_of_who_may_get_an_answer(wer: str, kwargs: dict[str, Any], erlaubt: bool,
                                             vertraut: bool) -> None:
    entscheidung = decide_native(cfg(wer=wer, nummern=["+49 151 23456789"]), **kwargs)
    assert (entscheidung.allow, entscheidung.trusted) == (erlaubt, vertraut), entscheidung.why


def test_the_own_chat_is_trusted_and_a_group_never_is() -> None:
    eigener = decide_native(cfg(), group=False, self_chat=True, number="")
    assert eigener.selbst and eigener.trusted
    gruppe = decide_native(cfg(wer="gruppen", nummern=["+49 151 23456789"]), group=True,
                           self_chat=False, number=ANNA)
    assert gruppe.group and gruppe.allow and not gruppe.trusted and not gruppe.selbst
    # Eine Gruppe kann nie "der eigene Chat" sein, auch wenn das Protokoll es so meldet.
    assert not decide_native(cfg(), group=True, self_chat=True, number="").allow


def test_the_list_is_ignored_when_only_my_own_chat_is_allowed() -> None:
    entscheidung = decide_native(cfg(wer="selbst", nummern=["+49 151 23456789"]), group=False,
                                 self_chat=False, number=ANNA)
    assert not entscheidung.allow


def test_names_in_the_list_never_match_a_real_number() -> None:
    entscheidung = decide_native(cfg(wer="nummern", nummern=["Anna", "anna"]), group=False,
                                 self_chat=False, number=ANNA)
    assert not entscheidung.allow


# -- Antworttext --------------------------------------------------------------------------------
def test_emoji_survive_over_the_direct_link_but_not_over_the_screen() -> None:
    assert "😀" in to_chat_text("Hallo 😀", wide=True)
    assert "😀" not in to_chat_text("Hallo 😀")
    assert to_chat_text("x", wide=True).startswith(bridge.SIGNATURE)


# -- Der Antwortgeber -----------------------------------------------------------------------------
class Transport:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail = False

    def send(self, chat: str, text: str) -> None:
        if self.fail:
            raise RuntimeError("nicht verbunden")
        self.sent.append((chat, text))


class Antworter:
    def __init__(self, antwort: str = "Es ist zehn Uhr.") -> None:
        self.antwort = antwort
        self.aufrufe: list[tuple[str, Any, str]] = []
        self.fehler: Exception | None = None

    def __call__(self, auftrag: str, decision: Any, config: dict[str, Any], key: str,
                 messenger: str) -> str:
        if self.fehler:
            raise self.fehler
        self.aufrufe.append((auftrag, decision, key))
        return self.antwort


class Werkstatt:
    def __init__(self, tmp_path: Path, **konfig: Any) -> None:
        self.konto = Settings(data_dir=tmp_path, env_path=tmp_path / ".env")
        self.zeit = [1_700_000_000.0]
        self.pausiert = [False]
        bridge.set_config(self.konto, "whatsapp", {"an": True, **konfig})
        self.antworter = Antworter()
        self.transport = Transport()
        self.antwort = NativeResponder(lambda: self.konto, self.antworter,
                                       paused=lambda: self.pausiert[0],
                                       clock=lambda: self.zeit[0])

    def nachricht(self, text: str = "Wie spät ist es?", **kwargs: Any) -> Incoming:
        werte: dict[str, Any] = dict(
            messenger="whatsapp", chat=f"{ANNA[1:]}@s.whatsapp.net", text=text,
            id=f"id{len(self.antworter.aufrufe)}{text[:5]}", ts=self.zeit[0] - 5, sender=ANNA,
            group=False, from_me=False, self_chat=False)
        werte.update(kwargs)
        return Incoming(**werte)

    def schicke(self, text: str = "Wie spät ist es?", **kwargs: Any) -> str:
        return self.antwort(self.nachricht(text, **kwargs), self.transport)


def eigene(text: str = "Wie spät ist es?", **kwargs: Any) -> dict[str, Any]:
    return dict(text=text, chat=f"{ICH[1:]}@s.whatsapp.net", sender="", from_me=True,
                self_chat=True, **kwargs)


def test_the_owner_writing_to_himself_gets_an_answer_with_the_signature(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path)
    assert w.schicke(**{"id": "e1", **eigene()}) == "beantwortet"
    assert w.transport.sent == [(f"{ICH[1:]}@s.whatsapp.net", "[Aquaticy] Es ist zehn Uhr.")]
    auftrag, entscheidung, _ = w.antworter.aufrufe[0]
    assert auftrag == "Wie spät ist es?" and entscheidung.selbst and entscheidung.trusted


def test_its_own_reply_coming_back_is_not_a_new_question(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path)
    assert w.schicke(**{"id": "e2", **eigene("[Aquaticy] Es ist zehn Uhr.")}) == "eigene"
    assert w.antworter.aufrufe == [] and w.transport.sent == []


def test_what_the_owner_writes_to_other_people_is_never_answered(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path, wer="gruppen")
    assert w.schicke(from_me=True, sender="") == "eigene"
    assert w.antworter.aufrufe == []


def test_a_message_is_never_answered_twice(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path)
    assert w.schicke(**{"id": "dup", **eigene()}) == "beantwortet"
    assert w.schicke(**{"id": "dup", **eigene()}) == "doppelt"
    assert len(w.transport.sent) == 1


def test_old_messages_after_a_pause_are_not_answered(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path)
    alt = w.zeit[0] - MAX_AGE_SECONDS - 1
    assert w.schicke(**{"id": "alt", "ts": alt, **eigene()}) == "zu alt"
    assert w.antworter.aufrufe == []
    assert w.schicke(**{"id": "neu", "ts": 0, **eigene()}) == "beantwortet"


def test_a_switched_off_bridge_and_a_pause_do_nothing(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path, an=False)
    assert w.schicke(**{"id": "a", **eigene()}) == "aus"
    bridge.set_config(w.konto, "whatsapp", {"an": True})
    w.pausiert[0] = True
    assert w.schicke(**{"id": "b", **eigene()}) == "pausiert"
    assert w.antworter.aufrufe == [] and w.transport.sent == []


def test_strangers_are_refused_when_only_the_own_chat_is_allowed(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path, wer="selbst")
    assert w.schicke("Hallo?").startswith("abgelehnt")
    assert w.antworter.aufrufe == [] and w.transport.sent == []


def test_a_listed_number_is_trusted_and_an_unlisted_one_is_not(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path, wer="einzeln", nummern=["+49 151 23456789"],
                  dienste={"haus": "lesen"})
    assert w.schicke("Wie ist das Wetter?", id="1") == "beantwortet"
    assert w.antworter.aufrufe[0][1].trusted
    assert w.schicke("Wie ist das Wetter?", id="2", sender=BERND) == "beantwortet"
    assert not w.antworter.aufrufe[1][1].trusted


def test_a_stranger_asking_for_my_mails_gets_a_refusal_and_no_agent(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path, wer="einzeln", dienste={"mail": "lesen"})
    assert w.schicke("Was sind meine neusten Mails?", sender=BERND) == "beantwortet"
    assert w.antworter.aufrufe == []
    assert "privat" in w.transport.sent[0][1].lower()


def test_the_owner_asking_for_a_switched_off_service_is_told_where_to_change_it(
        tmp_path: Path) -> None:
    w = Werkstatt(tmp_path, dienste={"haus": "aus"})
    assert w.schicke(**{"id": "h1", **eigene("Schalte meine Lichter an")}) == "beantwortet"
    assert w.antworter.aufrufe == []
    assert "Home Assistant" in w.transport.sent[0][1] and "Add-ons" in w.transport.sent[0][1]


def test_groups_need_the_keyword_and_are_never_trusted(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path, wer="gruppen", dienste={"mail": "lesen"})
    gruppe = dict(group=True, chat="1203630@g.us")
    assert w.schicke("Wer kommt heute?", id="g1", **gruppe) == "keine Aufgabe"
    assert w.schicke("Aquaticy, wie wird das Wetter?", id="g2", **gruppe) == "beantwortet"
    auftrag, entscheidung, _ = w.antworter.aufrufe[0]
    assert auftrag == "wie wird das Wetter?" and entscheidung.group and not entscheidung.trusted
    assert w.transport.sent[0][0] == "1203630@g.us"


def test_groups_are_refused_when_not_allowed(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path, wer="einzeln")
    assert w.schicke("Aquaticy, hi", group=True, chat="1@g.us").startswith("abgelehnt")


def test_the_hourly_limit_stops_the_replies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch
                                            ) -> None:
    monkeypatch.setattr(bridge, "MAX_REPLIES_PER_HOUR", 2)
    w = Werkstatt(tmp_path)
    ergebnisse = [w.schicke(**{"id": f"l{n}", **eigene(f"Frage {n}")}) for n in range(4)]
    assert ergebnisse == ["beantwortet", "beantwortet", "grenze", "grenze"]
    w.zeit[0] += 3600
    assert w.schicke(**{"id": "l9", **eigene("Frage 9")}) == "beantwortet"


def test_a_payment_number_in_the_answer_is_never_sent(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path)
    w.antworter.antwort = "Die Karte ist 4111 1111 1111 1111."
    w.schicke(**{"id": "p1", **eigene()})
    assert "4111" not in w.transport.sent[0][1] and "Zahlungsdaten" in w.transport.sent[0][1]


def test_an_error_in_the_agent_gets_a_short_note_for_the_owner_only(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path, wer="einzeln")
    w.antworter.fehler = RuntimeError("Modell kaputt")
    assert w.schicke(**{"id": "f1", **eigene()}) == "fehler"
    assert w.transport.sent == [(f"{ICH[1:]}@s.whatsapp.net", FAIL_TEXT)]
    assert w.schicke("Hallo?", id="f2", sender=BERND) == "fehler"
    assert len(w.transport.sent) == 1, "Fremde bekommen keine Fehlermeldung"


def test_a_failing_send_does_not_count_as_a_reply(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path)
    w.transport.fail = True
    with pytest.raises(RuntimeError):
        w.schicke(**{"id": "s1", **eigene()})
    from aquaticy.bridge import StateStore, replies_left

    assert replies_left(StateStore(w.konto), "whatsapp", w.zeit[0]) == bridge.MAX_REPLIES_PER_HOUR


def test_each_chat_has_its_own_conversation_key(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path, wer="einzeln")
    w.schicke("a", id="k1")
    w.schicke("b", id="k2", chat="4915100001111@s.whatsapp.net", sender=BERND)
    w.schicke("c", id="k3")
    keys = [aufruf[2] for aufruf in w.antworter.aufrufe]
    assert keys[0] == keys[2] != keys[1]


def test_no_message_text_is_stored_only_fingerprints(tmp_path: Path) -> None:
    w = Werkstatt(tmp_path)
    w.schicke(**{"id": "geheim1", **eigene("Mein Passwort ist Geheim123")})
    auf_platte = (tmp_path / bridge.STATE_FILE).read_text(encoding="utf-8")
    assert "Geheim123" not in auf_platte and "geheim1" not in auf_platte


# -- Wie die direkte Kopplung die anderen Wege verdrängt ------------------------------------
def test_a_directly_linked_messenger_is_ready_without_a_vm(tmp_path: Path) -> None:
    from aquaticy.messenger_native import NativeStore

    konto = SimpleNamespace(data_dir=tmp_path, vm_user_mode=False, vision_model="", model="x")
    assert "User mode" in bridge.ready_problem(konto, "whatsapp", pro=True)
    NativeStore(tmp_path / "messenger").set("whatsapp", ICH)
    assert bridge.ready_problem(konto, "whatsapp", pro=True) == ""
    assert "Ultra" in bridge.ready_problem(konto, "whatsapp", pro=False), "Ultra bleibt Pflicht"
    assert "User mode" in bridge.ready_problem(konto, "signal", pro=True)


def test_the_screen_bridge_leaves_a_directly_linked_messenger_alone(tmp_path: Path) -> None:
    from aquaticy.messenger_native import NativeStore

    konto = Settings(data_dir=tmp_path, env_path=tmp_path / ".env")
    bridge.set_config(konto, "whatsapp", {"an": True})
    NativeStore(tmp_path / "messenger").set("whatsapp", ICH)
    geoeffnet: list[str] = []
    drei = bridge.Bridge(lambda: konto, lambda name: geoeffnet.append(name), lambda *a: "")
    assert drei.run_once("whatsapp").state == "aus" and geoeffnet == []


def test_the_screen_runner_skips_a_directly_linked_messenger(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy.messenger_native import NativeStore

    monkeypatch.setattr(bridge.Runner, "TICK", 0.01)
    konto = Settings(data_dir=tmp_path, env_path=tmp_path / ".env")
    bridge.set_config(konto, "whatsapp", {"an": True})
    bridge.set_config(konto, "signal", {"an": True})
    NativeStore(tmp_path / "messenger").set("whatsapp", ICH)
    gerufen: list[str] = []

    class Falsch:
        def run_once(self, name: str) -> Any:
            gerufen.append(name)
            return SimpleNamespace(state="ok")

    lauf = bridge.Runner(Falsch(), lambda: konto)
    lauf.ensure_running()
    time.sleep(0.3)
    lauf.stop()
    lauf.wait_stopped(5)
    assert set(gerufen) == {"signal"}
