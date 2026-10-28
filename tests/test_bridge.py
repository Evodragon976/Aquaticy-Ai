"""Messenger-Brücke (aquaticy/bridge.py): Regeln, Lesen, Antworten -- ohne Messenger.

Wer antworten darf, welche Werkzeuge der Agent bekommt und was nach einem Durchgang
passiert, ist Code und wird hier mit einem gestellten Treiber und einem gestellten
Antwortgeber geprüft. Der echte Bildschirm der virtual machine kommt nicht vor.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from aquaticy import bridge
from aquaticy.bridge import (
    Bridge,
    ChatEntry,
    Decision,
    Msg,
    Scan,
    Transcript,
    decide,
    effective_settings,
    normalize_config,
    parse_scan,
    parse_transcript,
    strip_trigger,
    to_chat_text,
)
from aquaticy.config import Settings


def cfg(**kwargs: Any) -> dict[str, Any]:
    """Eine gültige Einstellung -- mit den Abweichungen aus *kwargs*."""
    dienste = kwargs.pop("dienste", {})
    return normalize_config({"an": True, **kwargs, "dienste": dienste})


@pytest.fixture
def konto(tmp_path: Path) -> Settings:
    ordner = tmp_path / "konto"
    ordner.mkdir()
    return Settings(data_dir=ordner, env_path=ordner / ".env")



def test_defaults_are_the_narrowest_choice() -> None:
    vorgabe = normalize_config({})
    assert vorgabe["an"] is False and vorgabe["wer"] == "selbst" and vorgabe["nummern"] == []
    assert vorgabe["dienste"] == {"web": "an", "haus": "aus", "mail": "aus", "kalender": "aus",
                                  "github": "aus", "lager": "aus"}


def test_garbage_falls_back_to_the_default() -> None:
    kaputt = normalize_config({"wer": "alle", "takt": "schnell", "an": "vielleicht",
                               "dienste": {"haus": "alles", "mail": 5, "boese": "an"},
                               "nummern": 7})
    assert kaputt["wer"] == "selbst" and kaputt["takt"] == bridge.DEFAULT_INTERVAL
    assert kaputt["an"] is False and kaputt["nummern"] == []
    assert kaputt["dienste"]["haus"] == "aus" and "boese" not in kaputt["dienste"]


def test_numbers_are_cleaned_deduplicated_and_capped() -> None:
    roh = "+49 151 2345678\n 0151 2345678 ,Anna;anna;;ab\x00\x1b;" + ",".join(
        f"Name{i}" for i in range(40))
    nummern = normalize_config({"nummern": roh})["nummern"]
    assert nummern[:3] == ["+49 151 2345678", "0151 2345678", "Anna"]
    assert len(nummern) == bridge.MAX_NUMBERS and all(len(n) <= 40 for n in nummern)
    assert "ab" not in nummern, "zu kurz"


def test_a_mutated_state_never_widens(konto: Settings) -> None:
    bridge.set_config(konto, "whatsapp", {"wer": "nummern", "dienste": {"haus": "lesen"}})
    neu = bridge.set_config(konto, "whatsapp", {"takt": 120})
    assert neu["wer"] == "nummern" and neu["dienste"]["haus"] == "lesen" and neu["takt"] == 120


def test_switching_on_needs_the_prerequisites(konto: Settings) -> None:
    with pytest.raises(bridge.BridgeError, match="Add-on zuerst"):
        bridge.set_config(konto, "signal", {"an": True}, ready="Installiere das Add-on zuerst.")
    assert bridge.load_config(konto)["signal"]["an"] is False
    assert bridge.set_config(konto, "signal", {"an": False}, ready="egal")["an"] is False
    assert bridge.set_config(konto, "signal", {"an": True})["an"] is True
    assert bridge.enabled_messengers(konto) == ["signal"]


def test_there_is_no_bridge_for_other_messengers(konto: Settings) -> None:
    for name in ("telegram", "sms", ""):
        with pytest.raises(bridge.BridgeError, match="gibt es nicht"):
            bridge.set_config(konto, name, {})



@pytest.mark.parametrize(("titel", "eintrag", "erwartet"), [
    ("+49 151 23456789", "0151 23456789", False),  # ohne Landesvorwahl: nie (12.7.8 Terra)
    ("+44 151 23456789", "0151 23456789", False),
    ("+49 151 23456789", "0049 151 23456789", True),
    ("+49 151 23456789", "+49 151 23456789", True),
    ("+49 (151) 234-56789", "004915123456789", True),
    ("+49 151 23456780", "0151 23456789", False),
    ("Anna", "anna", True),
    ("Anna Schmidt", "Anna", False),
    ("+49 151 2345", "0151 2345", False),
    ("", "Anna", False),
    ("Anna", "", False),
])
def test_numbers_and_names_match_exactly(titel: str, eintrag: str, erwartet: bool) -> None:
    assert bridge.matches_number(titel, eintrag) is erwartet


SELBST = "Du (Nachricht an dich selbst)"


@pytest.mark.parametrize(("wer", "titel", "gruppe", "nur_ausgehend", "erlaubt", "vertraut"), [

    ("selbst", SELBST, False, True, True, True),
    ("selbst", "Notiz an mich", False, True, True, True),
    ("selbst", "Note to Self", False, True, True, True),
    ("selbst", "Anna (You)", False, True, True, True),
    ("selbst", SELBST, None, True, False, False),
    ("selbst", SELBST, True, True, False, False),
    ("selbst", SELBST, False, False, False, False),
    ("selbst", "~Nachricht an dich selbst", False, True, False, False),

    ("selbst", "Anna", False, False, False, False),
    ("selbst", "Familie", True, False, False, False),
    ("nummern", "Anna", False, False, False, False),
    ("nummern", "Gruppe", True, False, False, False),
    ("einzeln", "Anna", False, False, True, False),
    ("einzeln", "Anna", None, False, False, False),
    ("einzeln", "Familie", True, False, False, False),
    ("gruppen", "Anna", False, False, True, False),
    ("gruppen", "Familie", True, False, True, False),
    ("gruppen", "Familie", None, False, True, False),
    ("einzeln", "", False, False, False, False),
])
def test_who_may_get_an_answer(wer: str, titel: str, gruppe: bool | None, nur_ausgehend: bool,
                               erlaubt: bool, vertraut: bool) -> None:
    entscheidung = decide(cfg(wer=wer), titel, gruppe, nur_ausgehend)
    assert (entscheidung.allow, entscheidung.trusted) == (erlaubt, vertraut), entscheidung.why


def test_a_number_without_country_code_is_never_trusted() -> None:
    """Dieselben Endziffern gibt es in anderen Ländern: Wer sie hat, bekäme sonst deine Dienste."""
    konfig = cfg(wer="nummern", nummern=["0151 23456789"])
    assert not decide(konfig, "+49 151 23456789", False, False).allow
    assert not decide(konfig, "+44 151 23456789", False, False).allow


def test_listed_numbers_are_trusted_but_only_in_single_chats() -> None:
    konfig = cfg(wer="nummern", nummern=["+49 151 23456789", "Anna"])
    assert decide(konfig, "+49 151 23456789", False, False) == Decision(
        True, trusted=True, why="freigegebene Nummer")
    assert decide(konfig, "Anna", False, False).trusted
    assert not decide(konfig, "Anna", True, False).allow, "in einer Gruppe nie"
    assert not decide(konfig, "Anna", None, False).allow
    assert not decide(konfig, "Bernd", False, False).allow


def test_a_push_name_with_a_tilde_never_matches_a_listed_name() -> None:
    """WhatsApp zeigt Namen von Fremden mit "~": Wer sich "Anna" nennt, ist nicht Anna."""
    konfig = cfg(wer="nummern", nummern=["Anna"])
    assert not decide(konfig, "~Anna", False, False).allow
    assert not decide(konfig, "~ Anna", False, False).trusted
    assert decide(konfig, "Anna", False, False).trusted


def test_the_list_is_ignored_when_only_my_own_chat_is_allowed() -> None:
    konfig = cfg(wer="selbst", nummern=["Anna"])
    assert not decide(konfig, "Anna", False, False).allow


def test_everyone_else_in_single_chats_is_not_trusted() -> None:
    entscheidung = decide(cfg(wer="einzeln", nummern=["Anna"]), "Bernd", False, False)
    assert entscheidung.allow and not entscheidung.trusted
    assert decide(cfg(wer="einzeln", nummern=["Anna"]), "Anna", False, False).trusted


@pytest.mark.parametrize(("text", "gruppe", "erwartet"), [
    ("Wie spät ist es?", False, "Wie spät ist es?"),
    ("Aquaticy, wie spät ist es?", False, "wie spät ist es?"),
    ("Aquaticy: Wetter", True, "Wetter"),
    ("@aquaticy Wetter in Bremen", True, "Wetter in Bremen"),
    ("Wetter in Bremen", True, None),
    ("Hat jemand Aquaticy gesehen?", True, None),
    ("Aquaticy", True, None),
    ("", False, None),
])
def test_in_groups_only_the_keyword_counts(text: str, gruppe: bool, erwartet: str | None) -> None:
    assert strip_trigger(text, gruppe) == erwartet



def test_strangers_get_public_tools_only() -> None:
    voll = {"web": "an", "haus": "schalten", "mail": "aendern", "kalender": "aendern",
            "github": "lesen", "lager": "schreiben"}
    fremd = bridge.allowed_tools(cfg(dienste=voll), trusted=False)
    assert fremd == bridge.PUBLIC_TOOLS | bridge.ALWAYS_TOOLS
    assert not fremd & {"ha_call", "ha_states", "mail_search", "calendar_events", "github",
                        "storage_find"}


def test_trusted_chats_get_exactly_the_chosen_levels() -> None:
    erlaubt = bridge.allowed_tools(cfg(dienste={"haus": "lesen", "mail": "lesen",
                                                "kalender": "aendern"}), trusted=True)
    assert {"ha_states", "mail_search", "mail_read", "calendar_events", "calendar_add",
            "calendar_edit"} <= erlaubt
    assert not erlaubt & {"ha_call", "mail_draft", "github", "storage_find"}


def test_with_the_web_off_only_calculation_remains() -> None:
    assert bridge.allowed_tools(cfg(dienste={"web": "aus"}), trusted=False) == {"calculate"}


@pytest.mark.parametrize("name", [
    "ask_user", "remember", "save_memory", "recall_memory", "change_setting", "vm_run",
    "vm_write", "vm_read", "vm_files", "blender_run", "desktop_look", "desktop_click",
    "desktop_type", "desktop_key", "desktop_open", "lan_scan", "lan_check", "create_image",
    "research_subtasks", "find_profiles", "inspect_public_visual",
])
def test_these_tools_are_never_offered(name: str) -> None:
    voll = {"web": "an", "haus": "schalten", "mail": "aendern", "kalender": "aendern",
            "github": "lesen", "lager": "schreiben"}
    for vertraut in (True, False):
        assert name not in bridge.allowed_tools(cfg(dienste=voll), vertraut)


def _basis() -> Settings:
    return Settings(
        ha_url="http://ha.local:8123", ha_token="ha-token", ha_control=True, ha_direct=True,
        google_enabled=True, google_client_id="cid", google_write=True, google_direct=True,
        github_token="ghp_x", storage_url="http://lager", storage_access="write",
        memory_enabled=True, lan_enabled=True, vm_user_mode=True, legal_guard=False,
        max_subagents=4, subagents_auto=True)


def test_effective_settings_for_strangers_hold_no_private_credential() -> None:
    basis = _basis()
    s = effective_settings(basis, cfg(wer="einzeln"), Decision(True))
    assert (s.ha_url, s.ha_token, s.github_token, s.storage_url) == ("", "", "", "")
    assert not (s.ha_control or s.ha_direct or s.google_enabled or s.google_write
                or s.google_direct or s.memory_enabled or s.lan_enabled or s.vm_user_mode)
    assert s.storage_access == "off" and s.legal_guard is True and s.max_subagents == 0
    assert basis.ha_token == "ha-token", "die Einstellungen der App bleiben unberührt"


def test_effective_settings_follow_the_levels_for_the_owner() -> None:
    eigener = Decision(True, trusted=True, selbst=True)
    nur_lesen = effective_settings(
        _basis(), cfg(dienste={"haus": "lesen", "mail": "lesen", "lager": "lesen"}), eigener)
    assert nur_lesen.ha_url and not nur_lesen.ha_control and not nur_lesen.ha_direct
    assert nur_lesen.google_enabled and not nur_lesen.google_write
    assert nur_lesen.storage_access == "read" and nur_lesen.legal_guard is False
    assert nur_lesen.memory_enabled is False and nur_lesen.vm_user_mode is False
    voll = effective_settings(
        _basis(), cfg(dienste={"haus": "schalten", "kalender": "aendern", "lager": "schreiben",
                               "github": "lesen"}), eigener)
    assert voll.ha_control and voll.google_write and voll.storage_access == "write"
    assert voll.github_token == "ghp_x"
    aus = effective_settings(_basis(), cfg(), eigener)
    assert aus.ha_url == "" and aus.google_enabled is False and aus.github_token == ""
    assert aus.storage_url == ""


def test_the_bridge_never_widens_what_the_app_allows() -> None:
    basis = _basis()
    basis.ha_control, basis.google_write, basis.storage_access = False, False, "read"
    voll = effective_settings(
        basis, cfg(dienste={"haus": "schalten", "mail": "aendern", "lager": "schreiben"}),
        Decision(True, trusted=True, selbst=True))
    assert not voll.ha_control and not voll.google_write and voll.storage_access == "read"



def test_replies_are_plain_text_with_the_signature() -> None:
    antwort = ("## Wetter\n**Bremen** heute: 14 °C\n- Regen am Abend\n- [mehr](https://x.de/a)\n"
               "| Tag | Temp |\n|---|---|\n| Mo | 12 |\n```py\nprint(1)\n```")
    text = to_chat_text(antwort)
    assert text.startswith(bridge.SIGNATURE + " ")
    for weg in ("##", "**", "```", "|---|"):
        assert weg not in text
    assert "• Regen am Abend" in text and "mehr (https://x.de/a)" in text
    assert "Mo – 12" in text or "Mo  –  12" in text.replace("  ", " ")


def test_replies_drop_characters_the_machine_cannot_type() -> None:
    text = to_chat_text("Hallo 😀 Welt \u0007 ✓ ö")
    assert "😀" not in text and "\u0007" not in text and "ö" in text


def test_long_replies_are_cut_and_empty_ones_get_a_sentence() -> None:
    lang = to_chat_text("wort " * 2000)
    assert len(lang) <= bridge.MAX_REPLY_CHARS + 60 and lang.endswith("(Mehr in der App.)")
    assert "keine Antwort" in to_chat_text("   ")


def test_the_bridge_recognises_its_own_texts() -> None:
    assert bridge.is_own_text(to_chat_text("Hallo"))
    assert bridge.is_own_text("  Aquaticy] Hallo"), "das Vision-Modell kürzt gern vorn"
    assert not bridge.is_own_text("Hallo [Aquaticy]")



def test_scan_parsing_drops_everything_unusable() -> None:
    scan = parse_scan({"angemeldet": "false", "offen": "Anna\x00", "chats": [
        {"titel": "Anna", "gruppe": False, "ungelesen": True, "vorschau": "Hi", "x": 100,
         "y": 200},
        {"titel": "", "x": 1, "y": 1},
        {"titel": "Weit weg", "x": 5000, "y": 10},
        {"titel": "Kein Punkt", "x": "nan", "y": 3},
        "kein Objekt",
        {"titel": "Gruppe", "gruppe": "unklar", "x": 1, "y": 2},
    ] + [{"titel": f"C{i}", "x": 1, "y": 1} for i in range(30)]})
    assert scan.angemeldet is False and scan.offen == "Anna"
    assert [c.titel for c in scan.chats][:2] == ["Anna", "Gruppe"]
    assert scan.chats[0].ungelesen is True and scan.chats[1].gruppe is None
    assert len(scan.chats) <= 12


def test_an_empty_or_odd_answer_is_not_a_login_problem() -> None:
    assert parse_scan(None).angemeldet is True and parse_scan({}).chats == []
    assert parse_scan({"chats": "x"}).chats == []


def test_transcript_parsing() -> None:
    protokoll = parse_transcript({"titel": "Anna", "gruppe": False, "nachrichten": [
        {"von": "andere", "name": "", "text": "Hallo", "zeit": "10:01"},
        {"von": "Ich ", "text": "Hi", "zeit": "10:02"},
        {"von": "jemand", "text": "?"},
        {"von": "ich", "text": ""},
        {"von": "ich", "text": "x" * 5000},
    ], "eingabe": {"x": 640, "y": 760}})
    assert [m.von for m in protokoll.nachrichten] == ["andere", "ich", "ich"]
    assert len(protokoll.nachrichten[-1].text) == bridge.MAX_MESSAGE_CHARS
    assert protokoll.eingabe == (640, 760) and protokoll.gruppe is False
    assert parse_transcript({"eingabe": {"x": -5, "y": 1}}).eingabe is None
    assert parse_transcript(None).nachrichten == []


def test_group_or_single_chat_is_decided_by_the_open_chat() -> None:
    assert bridge.group_flag(True, False) is True, "die Liste darf widersprechen"
    assert bridge.group_flag(False, True) is True
    assert bridge.group_flag(None, False) is False
    assert bridge.group_flag(False, None) is None, "unsicher im Chat heißt Gruppe"
    assert bridge.group_flag(None, None) is None



class FakeDriver:
    """Ein Messenger, den der Test Schritt für Schritt umbaut."""

    def __init__(self) -> None:
        self.scan_result = Scan(chats=[])
        self.chats: dict[str, Transcript] = {}
        self.geklickt: list[str] = []
        self.gesendet: list[str] = []
        self.offen = ""
        self.problem = ""
        self.sicht_wechselt = False
        self.fehler: Exception | None = None

    def ensure_open(self) -> str:
        return self.problem

    def scan(self) -> Scan:
        if self.fehler is not None:
            raise self.fehler
        return self.scan_result

    def click(self, x: int, y: int) -> None:
        for eintrag in self.scan_result.chats:
            if (eintrag.x, eintrag.y) == (x, y):
                self.offen = eintrag.titel
                self.geklickt.append(eintrag.titel)

    def read(self) -> Transcript:
        return self.chats.get(self.offen, Transcript())

    def current_title(self) -> tuple[str, bool | None]:
        return ("anderer Chat" if self.sicht_wechselt else self.offen, False)

    def send(self, text: str, eingabe: tuple[int, int] | None) -> None:
        self.gesendet.append(text)


class Antworter:
    def __init__(self, antwort: str = "Es ist zehn Uhr.") -> None:
        self.antwort = antwort
        self.aufrufe: list[tuple[str, Decision]] = []

    def __call__(self, auftrag: str, decision: Decision, config: dict[str, Any], key: str,
                 messenger: str) -> str:
        self.aufrufe.append((auftrag, decision))
        return self.antwort


def eintrag(titel: str, vorschau: str, *, gruppe: bool | None = False, ungelesen: bool = False,
            y: int = 100) -> ChatEntry:
    return ChatEntry(titel=titel, gruppe=gruppe, ungelesen=ungelesen, vorschau=vorschau,
                     x=300, y=y)


def nachricht(von: str, text: str, zeit: str = "10:00", name: str = "") -> Msg:
    return Msg(von=von, name=name, text=text, zeit=zeit)


class Werkstatt:
    """Alles, was ein Durchgang braucht."""

    def __init__(self, konto: Settings, **konfig: Any) -> None:
        self.konto = konto
        self.treiber = FakeDriver()
        self.antworter = Antworter()
        self.zeit = [1_000_000.0]
        self.pausiert = [False]
        self.fehlt = ""
        bridge.set_config(konto, "whatsapp", {"an": True, **konfig})
        self.bruecke = Bridge(lambda: konto, lambda name: self.treiber, self.antworter,
                              paused=lambda: self.pausiert[0],
                              ready=lambda settings, name: self.fehlt,
                              clock=lambda: self.zeit[0], sleep=lambda s: None)

    def durchgang(self) -> bridge.Report:
        return self.bruecke.run_once("whatsapp")


def selbst_chat(werkstatt: Werkstatt, nachrichten: list[Msg], vorschau: str) -> None:
    werkstatt.treiber.scan_result = Scan(chats=[eintrag(SELBST, vorschau)])
    werkstatt.treiber.chats[SELBST] = Transcript(
        titel=SELBST, gruppe=False, nachrichten=nachrichten, eingabe=(640, 760))


def test_a_switched_off_bridge_does_nothing(konto: Settings) -> None:
    werkstatt = Werkstatt(konto, an=False)
    assert werkstatt.durchgang().state == "aus" and werkstatt.treiber.geklickt == []


def test_a_missing_prerequisite_stops_the_cycle_before_the_screen_is_touched(
        konto: Settings) -> None:
    werkstatt = Werkstatt(konto)
    werkstatt.fehlt = "Im Add-on steht „Nur lesen“."
    rep = werkstatt.durchgang()
    assert rep.state == "fehler" and "Nur lesen" in rep.fehler
    assert werkstatt.treiber.geklickt == [] and werkstatt.treiber.gesendet == []


def test_without_an_override_the_real_prerequisites_are_checked(konto: Settings) -> None:
    bridge.set_config(konto, "whatsapp", {"an": True})
    echte = Bridge(lambda: konto, lambda name: FakeDriver(), Antworter())
    assert "nicht installiert" in echte.run_once("whatsapp").fehler or "User mode" in (
        echte.run_once("whatsapp").fehler)


def test_a_busy_chat_pauses_the_bridge(konto: Settings) -> None:
    werkstatt = Werkstatt(konto)
    werkstatt.pausiert[0] = True
    assert werkstatt.durchgang().state == "pausiert" and werkstatt.treiber.geklickt == []


def test_the_first_look_only_remembers_and_the_next_message_is_answered(konto: Settings) -> None:
    werkstatt = Werkstatt(konto)
    selbst_chat(werkstatt, [nachricht("ich", "alt")], "alt")
    assert werkstatt.durchgang().beantwortet == 0, "frühere Nachrichten bleiben unbeantwortet"
    assert werkstatt.treiber.geklickt == [] and werkstatt.treiber.gesendet == []
    selbst_chat(werkstatt, [nachricht("ich", "alt"), nachricht("ich", "Wie spät ist es?",
                                                              "10:05")], "Wie spät ist es?")
    rep = werkstatt.durchgang()
    assert rep.beantwortet == 1 and rep.gelesen == 1
    assert werkstatt.antworter.aufrufe[0][0] == "Wie spät ist es?"
    assert werkstatt.antworter.aufrufe[0][1].selbst and werkstatt.antworter.aufrufe[0][1].trusted
    assert werkstatt.treiber.gesendet == ["[Aquaticy] Es ist zehn Uhr."]


def test_the_own_reply_is_not_a_new_command(konto: Settings) -> None:
    werkstatt = Werkstatt(konto)
    selbst_chat(werkstatt, [nachricht("ich", "alt")], "alt")
    werkstatt.durchgang()
    selbst_chat(werkstatt, [nachricht("ich", "Frage?", "10:05")], "Frage?")
    assert werkstatt.durchgang().beantwortet == 1

    selbst_chat(werkstatt, [nachricht("ich", "Frage?", "10:05"),
                            nachricht("ich", "[Aquaticy] Es ist zehn Uhr.", "10:06")],
                "[Aquaticy] Es ist zehn Uhr.")
    rep = werkstatt.durchgang()
    assert rep.gelesen == 0 and len(werkstatt.treiber.gesendet) == 1


def test_a_message_is_never_answered_twice(konto: Settings) -> None:
    werkstatt = Werkstatt(konto)
    selbst_chat(werkstatt, [nachricht("ich", "alt")], "alt")
    werkstatt.durchgang()
    frage = [nachricht("ich", "Frage?", "10:05")]
    selbst_chat(werkstatt, frage, "Frage?")
    werkstatt.durchgang()

    werkstatt.treiber.scan_result.chats[0].ungelesen = True
    assert werkstatt.durchgang().beantwortet == 0
    assert len(werkstatt.treiber.gesendet) == 1


def test_the_first_read_of_a_chat_answers_only_the_last_message(konto: Settings) -> None:
    werkstatt = Werkstatt(konto)
    selbst_chat(werkstatt, [nachricht("ich", "x")], "x")
    werkstatt.durchgang()
    selbst_chat(werkstatt, [nachricht("ich", "eins", "09:00"), nachricht("ich", "zwei", "09:01"),
                            nachricht("ich", "drei", "09:02")], "drei")
    werkstatt.treiber.chats[SELBST].nachrichten.insert(0, nachricht("ich", "uralt", "08:00"))
    werkstatt.durchgang()
    assert [a[0] for a in werkstatt.antworter.aufrufe] == ["drei"]


def test_foreign_chats_are_not_even_opened_when_only_my_own_is_allowed(konto: Settings) -> None:
    werkstatt = Werkstatt(konto, wer="selbst")
    werkstatt.treiber.scan_result = Scan(chats=[
        eintrag("Anna", "Hallo", ungelesen=True, y=100),
        eintrag("Familie", "Foto", gruppe=True, ungelesen=True, y=200)])
    werkstatt.durchgang()
    werkstatt.treiber.scan_result.chats[0].vorschau = "Hallo? Bist du da?"
    rep = werkstatt.durchgang()
    assert werkstatt.treiber.geklickt == [] and rep.gelesen == 0
    assert werkstatt.antworter.aufrufe == []


def test_single_chats_get_public_answers_when_allowed(konto: Settings) -> None:
    werkstatt = Werkstatt(konto, wer="einzeln", dienste={"mail": "lesen", "haus": "schalten"})
    anna = [nachricht("andere", "alt")]
    werkstatt.treiber.scan_result = Scan(chats=[eintrag("Anna", "alt")])
    werkstatt.treiber.chats["Anna"] = Transcript(titel="Anna", gruppe=False, nachrichten=anna)
    werkstatt.durchgang()
    anna.append(nachricht("andere", "Wie wird das Wetter?", "11:00"))
    werkstatt.treiber.scan_result = Scan(chats=[eintrag("Anna", "Wie wird das Wetter?",
                                                      ungelesen=True)])
    rep = werkstatt.durchgang()
    assert rep.beantwortet == 1
    entscheidung = werkstatt.antworter.aufrufe[0][1]
    assert entscheidung.allow and not entscheidung.trusted and not entscheidung.selbst


def test_a_stranger_asking_for_my_mails_gets_a_refusal_and_no_agent(konto: Settings) -> None:
    werkstatt = Werkstatt(konto, wer="einzeln", dienste={"mail": "lesen"})
    anna = [nachricht("andere", "alt")]
    werkstatt.treiber.scan_result = Scan(chats=[eintrag("Anna", "alt")])
    werkstatt.treiber.chats["Anna"] = Transcript(titel="Anna", gruppe=False, nachrichten=anna)
    werkstatt.durchgang()
    anna.append(nachricht("andere", "Was sind meine neusten Mails?", "11:00"))
    werkstatt.treiber.scan_result = Scan(chats=[eintrag("Anna", "Was sind meine neusten Mails?")])
    werkstatt.durchgang()
    assert werkstatt.antworter.aufrufe == []
    assert "private" in werkstatt.treiber.gesendet[0].lower()


def test_the_owner_asking_for_a_switched_off_service_is_told_where_to_change_it(
        konto: Settings) -> None:
    werkstatt = Werkstatt(konto, dienste={"haus": "aus"})
    selbst_chat(werkstatt, [nachricht("ich", "alt")], "alt")
    werkstatt.durchgang()
    selbst_chat(werkstatt, [nachricht("ich", "Schalte meine Lichter an", "10:05")],
                "Schalte meine Lichter an")
    werkstatt.durchgang()
    assert werkstatt.antworter.aufrufe == []
    gesendet = werkstatt.treiber.gesendet[0]
    assert "Home Assistant" in gesendet and "Add-ons" in gesendet and "WhatsApp" in gesendet


def test_the_owner_asking_for_a_permitted_service_reaches_the_agent(konto: Settings) -> None:
    werkstatt = Werkstatt(konto, dienste={"haus": "schalten"})
    selbst_chat(werkstatt, [nachricht("ich", "alt")], "alt")
    werkstatt.durchgang()
    selbst_chat(werkstatt, [nachricht("ich", "Schalte meine Lichter an", "10:05")],
                "Schalte meine Lichter an")
    werkstatt.durchgang()
    assert [a[0] for a in werkstatt.antworter.aufrufe] == ["Schalte meine Lichter an"]


def test_groups_need_the_keyword_and_are_never_trusted(konto: Settings) -> None:
    from aquaticy import addons

    addons._update(konto, "whatsapp", installed=True)
    addons.set_rights(konto, "whatsapp", {"wo": "alle"})
    werkstatt = Werkstatt(konto, wer="gruppen", dienste={"mail": "lesen"})
    familie = [nachricht("andere", "alt", name="Mama")]
    werkstatt.treiber.scan_result = Scan(chats=[eintrag("Familie", "alt", gruppe=True)])
    werkstatt.treiber.chats["Familie"] = Transcript(titel="Familie", gruppe=True,
                                                    nachrichten=familie)
    werkstatt.durchgang()
    familie.append(nachricht("andere", "Wer kommt heute?", "11:00", "Mama"))
    werkstatt.treiber.scan_result = Scan(chats=[eintrag("Familie", "Mama: Wer kommt heute?",
                                                      gruppe=True)])
    assert werkstatt.durchgang().beantwortet == 0, "ohne Stichwort bleibt Aquaticy still"
    familie.append(nachricht("andere", "Aquaticy, wie wird das Wetter?", "11:05", "Papa"))
    werkstatt.treiber.scan_result = Scan(chats=[eintrag("Familie", "Papa: Aquaticy, wie",
                                                      gruppe=True)])
    assert werkstatt.durchgang().beantwortet == 1
    auftrag, entscheidung = werkstatt.antworter.aufrufe[0]
    assert auftrag == "wie wird das Wetter?" and entscheidung.group and not entscheidung.trusted


def test_a_group_is_refused_when_the_open_chat_says_group_although_the_list_did_not(
        konto: Settings) -> None:
    werkstatt = Werkstatt(konto, wer="einzeln")
    liste = [nachricht("andere", "alt")]
    werkstatt.treiber.scan_result = Scan(chats=[eintrag("Skatrunde", "alt", gruppe=None)])
    werkstatt.treiber.chats["Skatrunde"] = Transcript(titel="Skatrunde", gruppe=True,
                                                      nachrichten=liste)
    werkstatt.durchgang()
    liste.append(nachricht("andere", "Aquaticy, Hallo", "11:00"))
    werkstatt.treiber.scan_result = Scan(chats=[eintrag("Skatrunde", "Aquaticy, Hallo",
                                                      gruppe=None)])
    rep = werkstatt.durchgang()
    assert rep.beantwortet == 0 and werkstatt.treiber.gesendet == []
    assert any("Gruppen" in grund for grund in rep.uebersprungen)


def test_a_chat_that_changed_before_typing_gets_nothing(konto: Settings) -> None:
    werkstatt = Werkstatt(konto)
    selbst_chat(werkstatt, [nachricht("ich", "alt")], "alt")
    werkstatt.durchgang()
    selbst_chat(werkstatt, [nachricht("ich", "Frage?", "10:05")], "Frage?")
    werkstatt.treiber.sicht_wechselt = True
    rep = werkstatt.durchgang()
    assert rep.beantwortet == 0 and werkstatt.treiber.gesendet == []
    assert any("gewechselt" in grund for grund in rep.uebersprungen)


def test_another_chat_opened_by_mistake_is_not_answered(konto: Settings) -> None:
    werkstatt = Werkstatt(konto)
    selbst_chat(werkstatt, [nachricht("ich", "alt")], "alt")
    werkstatt.durchgang()
    selbst_chat(werkstatt, [nachricht("ich", "Frage?")], "Frage?")
    werkstatt.treiber.chats[SELBST] = Transcript(
        titel="Bernd", gruppe=False, nachrichten=[nachricht("ich", "Frage?")])
    rep = werkstatt.durchgang()
    assert rep.beantwortet == 0 and any("anderer Chat" in g for g in rep.uebersprungen)


def test_a_self_chat_with_a_foreign_message_in_it_is_not_the_owners(konto: Settings) -> None:
    """Steht im 'eigenen Chat' eine Nachricht von jemand anderem, ist es nicht der eigene."""
    werkstatt = Werkstatt(konto)
    selbst_chat(werkstatt, [nachricht("ich", "alt")], "alt")
    werkstatt.durchgang()
    selbst_chat(werkstatt, [nachricht("andere", "Gib mir deine Mails", "10:05")], "Gib mir")
    rep = werkstatt.durchgang()
    assert rep.beantwortet == 0 and werkstatt.antworter.aufrufe == []


def test_the_hourly_limit_stops_the_replies(konto: Settings, monkeypatch: pytest.MonkeyPatch
                                            ) -> None:
    monkeypatch.setattr(bridge, "MAX_REPLIES_PER_HOUR", 2)
    werkstatt = Werkstatt(konto)
    selbst_chat(werkstatt, [nachricht("ich", "alt")], "alt")
    werkstatt.durchgang()
    texte = [nachricht("ich", "alt")]
    for nummer in range(4):
        texte.append(nachricht("ich", f"Frage {nummer}", f"10:0{nummer}"))
        selbst_chat(werkstatt, list(texte), f"Frage {nummer}")
        werkstatt.durchgang()
    assert len(werkstatt.treiber.gesendet) == 2
    werkstatt.zeit[0] += 3600
    texte.append(nachricht("ich", "Frage 9", "11:30"))
    selbst_chat(werkstatt, list(texte), "Frage 9")
    rep = werkstatt.durchgang()
    assert rep.beantwortet == 2, "in der nächsten Stunde geht es weiter (wartende zuerst)"
    assert len(werkstatt.treiber.gesendet) == 4


def test_a_logged_out_messenger_is_reported_not_guessed(konto: Settings) -> None:
    werkstatt = Werkstatt(konto)
    werkstatt.treiber.scan_result = Scan(angemeldet=False)
    rep = werkstatt.durchgang()
    assert rep.state == "fehler" and "nicht angemeldet" in rep.fehler
    status = bridge.public_view(konto, "whatsapp", pro=True)["status"]
    assert status["ok"] is False and "angemeldet" in status["fehler"]


def test_a_broken_screen_is_an_error_not_a_crash(konto: Settings) -> None:
    werkstatt = Werkstatt(konto)
    werkstatt.treiber.fehler = RuntimeError("kein Bild")
    assert werkstatt.durchgang().state == "fehler"
    werkstatt.treiber.fehler = None
    werkstatt.treiber.problem = "Das Fenster ging nicht auf."
    assert "nicht auf" in werkstatt.durchgang().fehler


def test_state_and_view_hold_no_message_text(konto: Settings) -> None:
    werkstatt = Werkstatt(konto)
    selbst_chat(werkstatt, [nachricht("ich", "alt")], "alt")
    werkstatt.durchgang()
    selbst_chat(werkstatt, [nachricht("ich", "mein Passwort ist Geheim123", "10:05")],
                "mein Passwort ist Geheim123")
    werkstatt.durchgang()
    auf_platte = (konto.data_dir / bridge.STATE_FILE).read_text(encoding="utf-8")
    assert "Geheim123" not in auf_platte, "gemerkt werden nur Fingerabdrücke"
    assert "Geheim123" not in json.dumps(bridge.public_view(konto, "whatsapp", pro=True))
    assert oct((konto.data_dir / bridge.STATE_FILE).stat().st_mode & 0o777) == "0o600"



def addon_bereit(konto: Settings, **felder: Any) -> None:
    from aquaticy import addons

    addons._update(konto, "whatsapp", installed=True, enabled=True,
                   login={"state": "angemeldet", "who": "laut dir", "at": 1},
                   rechte={"zugriff": "schreiben", "wo": "alle"}, **felder)
    konto.vm_user_mode = True
    konto.vision_model = "mistral/pixtral-large-latest"


def test_the_bridge_needs_everything_in_place(konto: Settings) -> None:
    assert "Ultra" in bridge.ready_problem(konto, "whatsapp", pro=False)
    assert "User mode" in bridge.ready_problem(konto, "whatsapp", pro=True)
    konto.vm_user_mode = True
    assert "nicht installiert" in bridge.ready_problem(konto, "whatsapp", pro=True)
    from aquaticy import addons

    addons._update(konto, "whatsapp", installed=True, enabled=False)
    assert "ausgeschaltet" in bridge.ready_problem(konto, "whatsapp", pro=True)
    addons._update(konto, "whatsapp", enabled=True)
    assert "Melde dich" in bridge.ready_problem(konto, "whatsapp", pro=True)
    addon_bereit(konto)
    assert bridge.ready_problem(konto, "whatsapp", pro=True) == ""
    konto.vision_model, konto.model = "", "mistral/mistral-small-latest"
    assert "Vision-Modell" in bridge.ready_problem(konto, "whatsapp", pro=True)


def test_read_only_in_the_addon_means_no_bridge(konto: Settings) -> None:
    addon_bereit(konto)
    from aquaticy import addons

    addons.set_rights(konto, "whatsapp", {"zugriff": "lesen"})
    assert "Nur lesen" in bridge.ready_problem(konto, "whatsapp", pro=True)


def test_groups_in_the_bridge_follow_the_addon_rights(konto: Settings) -> None:
    addon_bereit(konto)
    from aquaticy import addons

    voll = cfg(wer="gruppen")
    assert bridge.capped_config(konto, "whatsapp", voll)["wer"] == "gruppen"
    addons.set_rights(konto, "whatsapp", {"wo": "einzeln"})
    assert bridge.capped_config(konto, "whatsapp", voll)["wer"] == "einzeln"
    assert bridge.capped_config(konto, "whatsapp", cfg(wer="nummern"))["wer"] == "nummern"


def test_the_view_carries_the_choices_and_the_reason(konto: Settings) -> None:
    ansicht = bridge.public_view(konto, "signal", pro=True)
    assert ansicht["config"]["wer"] == "selbst" and ansicht["problem"]
    katalog = ansicht["katalog"]
    assert [w["value"] for w in katalog["wer"]] == list(bridge.SCOPES)
    assert {d["key"] for d in katalog["dienste"]} == set(bridge.SERVICES)
    assert [t["value"] for t in katalog["takt"]] == list(bridge.INTERVALS)



class FakeAgent:
    """Merkt sich, womit er gebaut wurde, und antwortet."""

    gebaut: ClassVar[list[FakeAgent]] = []

    def __init__(self, settings: Any, erlaubt: frozenset[str], zusatz: str,
                 on_event: Any = None) -> None:
        self.settings, self.erlaubt, self.zusatz = settings, erlaubt, zusatz
        self.on_event = on_event
        self.messages: list[dict[str, str]] = [{"role": "system", "content": "s"}]
        self.fragen: list[tuple[str, dict[str, Any]]] = []
        FakeAgent.gebaut.append(self)

    def ask(self, frage: str, **kwargs: Any) -> Any:
        self.fragen.append((frage, kwargs))
        self.messages.append({"role": "user", "content": frage})
        if frage == "Missbrauch":
            self.on_event("abuse", {"art": "Beleidigung", "schwere": 2})
        return SimpleNamespace(answer=f"Antwort auf {frage}")

    def close(self) -> None: ...


@pytest.fixture
def antwortgeber(konto: Settings):
    FakeAgent.gebaut = []
    meldungen: list[dict[str, Any]] = []
    uhr = [0.0]
    geber = bridge.AgentAnswerer(lambda: _basis(), on_abuse=meldungen.append,
                                 agent_factory=FakeAgent, clock=lambda: uhr[0])
    return geber, meldungen, uhr


EIGEN = Decision(True, trusted=True, selbst=True)


def test_the_agent_gets_the_levels_the_tools_and_no_questions(antwortgeber) -> None:
    geber, _, _ = antwortgeber
    konfig = cfg(dienste={"haus": "lesen"})
    assert geber("Hallo", EIGEN, konfig, "k1", "whatsapp") == "Antwort auf Hallo"
    agent = FakeAgent.gebaut[0]
    assert "ha_states" in agent.erlaubt and "ha_call" not in agent.erlaubt
    assert not agent.settings.ha_control and not agent.settings.memory_enabled
    _frage, kwargs = agent.fragen[0]
    assert kwargs["structured"] is False and kwargs["recheck"] is False
    assert kwargs["online"] is True and kwargs["sandbox"] is False and kwargs["stream"] is False
    assert "Messenger" in agent.zusatz and "Besitzer selbst" in agent.zusatz


def test_a_chat_keeps_its_agent_and_its_history(antwortgeber) -> None:
    geber, _, _ = antwortgeber
    geber("eins", EIGEN, cfg(), "k1", "whatsapp")
    geber("zwei", EIGEN, cfg(), "k1", "whatsapp")
    geber("drei", EIGEN, cfg(), "k2", "whatsapp")
    assert len(FakeAgent.gebaut) == 2 and len(FakeAgent.gebaut[0].fragen) == 2


def test_new_rights_build_a_new_agent_but_keep_the_history(antwortgeber) -> None:
    geber, _, _ = antwortgeber
    geber("eins", EIGEN, cfg(), "k1", "whatsapp")
    geber("zwei", EIGEN, cfg(dienste={"haus": "schalten"}), "k1", "whatsapp")
    alt, neu = FakeAgent.gebaut
    assert "ha_call" in neu.erlaubt and "ha_call" not in alt.erlaubt
    assert [m["content"] for m in neu.messages[1:]] == ["eins", "zwei"]


def test_idle_agents_are_dropped(antwortgeber) -> None:
    geber, _, uhr = antwortgeber
    geber("eins", EIGEN, cfg(), "k1", "whatsapp")
    uhr[0] += bridge.AgentAnswerer.IDLE_SECONDS + 1
    geber("zwei", EIGEN, cfg(), "k1", "whatsapp")
    assert len(FakeAgent.gebaut) == 2 and len(FakeAgent.gebaut[1].messages) == 2


def test_abuse_counts_for_the_owner_but_not_for_a_stranger(antwortgeber) -> None:
    geber, meldungen, _ = antwortgeber
    geber("Missbrauch", EIGEN, cfg(), "k1", "whatsapp")
    assert meldungen == [{"art": "Beleidigung", "schwere": 2}]
    geber("Missbrauch", Decision(True), cfg(wer="einzeln"), "k2", "whatsapp")
    assert len(meldungen) == 1, "ein Fremder darf dem Besitzer das Konto nicht sperren"


def test_web_off_means_an_offline_agent(antwortgeber) -> None:
    geber, _, _ = antwortgeber
    geber("Hallo", EIGEN, cfg(dienste={"web": "aus"}), "k1", "whatsapp")
    assert FakeAgent.gebaut[0].fragen[0][1]["online"] is False



def test_the_real_bridge_agent_offers_only_allowed_tools_and_blocks_the_rest(
        konto: Settings) -> None:
    konfig = cfg(dienste={"haus": "lesen"})
    basis = _basis()
    basis.data_dir, basis.env_path = konto.data_dir, konto.env_path
    settings = effective_settings(basis, konfig, EIGEN)
    erlaubt = bridge.allowed_tools(konfig, True)
    agent = bridge.bridge_agent_class()(settings, erlaubt, bridge.trust_note(EIGEN, konfig))
    angeboten = {t["function"]["name"] for t in agent.tools}
    assert angeboten <= erlaubt and "calculate" in angeboten
    assert not angeboten & {"ask_user", "ha_call", "vm_run", "desktop_look", "remember",
                            "change_setting"}
    assert agent.OWN_HINTS is False and agent.toolbox.ask_handler is None
    for name in ("ha_call", "vm_run", "desktop_type", "change_setting", "remember"):
        antwort = agent.toolbox.call(name, {"domain": "light", "service": "turn_on"})
        assert antwort["skipped_reason"] == "bruecke", name
    assert "Messenger" in agent._compose_system()
    agent.close()



class FakeDesktop:
    def __init__(self, fenster: list[dict[str, str]] | None = None) -> None:
        self.fenster = fenster or []
        self.aufrufe: list[tuple[Any, ...]] = []
        self.antworten: list[str] = []
        self.box = SimpleNamespace(screenshot=lambda grid=False: b"\xff\xd8bild")

    def windows(self) -> dict[str, Any]:
        return {"fenster": self.fenster}

    def focus(self, kennung: str) -> dict[str, Any]:
        self.aufrufe.append(("focus", kennung))
        return {}

    def open(self, app: str) -> dict[str, Any]:
        self.aufrufe.append(("open", app))
        return {"error": "weg"} if app == "kaputt" else {}

    def see(self, bild: bytes, prompt: str) -> str:
        self.aufrufe.append(("see", prompt[:20]))
        return self.antworten.pop(0)

    def run_helper(self, *args: str, stdin: bytes | None = None, timeout: float = 60) -> dict:
        self.aufrufe.append((*args, stdin.decode() if stdin else None))
        return {}


def test_the_driver_focuses_an_open_window_and_opens_a_missing_one() -> None:
    schlaf: list[float] = []
    offen = FakeDesktop([{"id": "0x1", "klasse": "Navigator.aquaticy-whatsapp",
                          "titel": "(2) WhatsApp"}])
    assert bridge.VisionDriver(offen, "whatsapp", schlaf.append).ensure_open() == ""
    assert offen.aufrufe == [("focus", "0x1")] and schlaf == []
    zu = FakeDesktop([{"id": "0x2", "klasse": "xterm.XTerm", "titel": "bash"}])
    assert bridge.VisionDriver(zu, "signal", schlaf.append).ensure_open() == ""
    assert zu.aufrufe == [("open", "signal")] and schlaf == [10]
    kaputt = bridge.VisionDriver(FakeDesktop(), "kaputt", schlaf.append)
    assert kaputt.ensure_open() == "weg"


def test_the_driver_types_line_by_line_and_sends() -> None:
    desktop = FakeDesktop()
    bridge.VisionDriver(desktop, "whatsapp", lambda s: None).send(
        "[Aquaticy] Zeile eins\n\nZeile drei", (640, 760))
    assert desktop.aufrufe == [
        ("click", "640", "760", None),
        ("type", "[Aquaticy] Zeile eins"),
        ("key", "shift+Return", None),
        ("key", "shift+Return", None),
        ("type", "Zeile drei"),
        ("key", "Return", None),
    ]


def test_the_driver_falls_back_to_the_bottom_of_the_screen_without_a_text_field() -> None:
    desktop = FakeDesktop()
    bridge.VisionDriver(desktop, "signal", lambda s: None).send("[Aquaticy] Hi", None)
    assert desktop.aufrufe[0][:3] == ("click", "768", "755")
    desktop = FakeDesktop()
    bridge.VisionDriver(desktop, "signal", lambda s: None).send("[Aquaticy] Hi", (100, 50))
    assert desktop.aufrufe[0][:3] == ("click", "768", "755"), "ein Feld oben ist keins"


def test_the_driver_reads_the_screen_through_the_vision_model() -> None:
    desktop = FakeDesktop()
    desktop.antworten = [
        json.dumps({"angemeldet": True, "offen": "", "chats": [
            {"titel": "Anna", "gruppe": False, "ungelesen": True, "vorschau": "Hi", "x": 10,
             "y": 20}]}),
        json.dumps({"titel": "Anna", "gruppe": False, "nachrichten": [
            {"von": "andere", "text": "Hi", "zeit": "10:00"}], "eingabe": {"x": 600, "y": 770}}),
        'Text davor {"chat": "Anna", "gruppe": false} danach',
    ]
    fahrer = bridge.VisionDriver(desktop, "whatsapp", lambda s: None)
    assert fahrer.scan().chats[0].titel == "Anna"
    assert fahrer.read().nachrichten[0].text == "Hi"
    assert fahrer.current_title() == ("Anna", False)
    assert [a[0] for a in desktop.aufrufe] == ["see", "see", "see"]



class FakeBridge:
    def __init__(self) -> None:
        self.aufrufe: list[str] = []
        self.ereignis = threading.Event()

    def run_once(self, name: str) -> Any:
        self.aufrufe.append(name)
        self.ereignis.set()
        return SimpleNamespace(state="ok")


def test_the_runner_starts_only_when_something_is_switched_on(
        konto: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge.Runner, "TICK", 0.01)
    falsch = FakeBridge()
    lauf = bridge.Runner(falsch, lambda: konto)
    assert lauf.ensure_running() is False and lauf._thread is None
    bridge.set_config(konto, "whatsapp", {"an": True})
    assert lauf.ensure_running() is True
    assert falsch.ereignis.wait(5) and falsch.aufrufe[0] == "whatsapp"
    lauf.stop()
    lauf.wait_stopped(5)
    assert lauf._thread is not None and not lauf._thread.is_alive()


def test_the_runner_waits_for_the_interval_and_slows_down_after_an_error(
        konto: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge.Runner, "TICK", 0.01)
    bridge.set_config(konto, "whatsapp", {"an": True, "takt": 30})
    zeit = [100.0]
    falsch = FakeBridge()
    lauf = bridge.Runner(falsch, lambda: konto, clock=lambda: zeit[0])
    lauf.ensure_running()
    assert falsch.ereignis.wait(5)
    time.sleep(0.1)
    assert falsch.aufrufe == ["whatsapp"], "nicht schon nach einem Augenblick wieder"
    assert lauf._due["whatsapp"] == 130.0
    zeit[0] = 131.0
    time.sleep(0.2)
    assert falsch.aufrufe.count("whatsapp") >= 2
    lauf.stop()
    lauf.wait_stopped(5)


def test_the_runner_survives_a_failing_cycle(konto: Settings, monkeypatch: pytest.MonkeyPatch
                                             ) -> None:
    monkeypatch.setattr(bridge.Runner, "TICK", 0.01)
    bridge.set_config(konto, "whatsapp", {"an": True})
    ereignis = threading.Event()

    class Kaputt:
        def run_once(self, name: str) -> Any:
            ereignis.set()
            raise RuntimeError("Absturz")

    lauf = bridge.Runner(Kaputt(), lambda: konto)
    lauf.ensure_running()
    assert ereignis.wait(5)
    time.sleep(0.05)
    assert lauf._thread is not None and lauf._thread.is_alive()
    lauf.stop()
    lauf.wait_stopped(5)
    assert lauf._due["whatsapp"] > 0
