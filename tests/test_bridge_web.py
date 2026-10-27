"""Messenger-Brücke im Web (aquaticy/web.py): Aktion, Ansicht, Start und Stopp."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aquaticy import addons, bridge, web


class FakeRunner:
    """Ersetzt den Hintergrundlauf: kein Thread, nur Buch über die Aufrufe."""

    def __init__(self) -> None:
        self.aufrufe: list[str] = []
        self.answerer = SimpleNamespace(close=lambda: self.aufrufe.append("close"))

    def ensure_running(self) -> bool:
        self.aufrufe.append("start")
        return True

    def wake(self) -> None:
        self.aufrufe.append("wake")

    def stop(self) -> None:
        self.aufrufe.append("stop")

    def wait_stopped(self, timeout: float = 60) -> None:
        self.aufrufe.append("wait")


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch) -> FakeRunner:
    echt = FakeRunner()
    monkeypatch.setattr(web, "_build_bridge_runner", lambda get_session, account: echt)
    monkeypatch.setattr(web, "USER_BRIDGES", {})
    monkeypatch.setattr(web, "BRIDGE_RUNNER", None)
    return echt


def sitzung(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plan: str = "ultra",
            bereit: bool = True) -> Any:
    konto = SimpleNamespace(id="u1", plan=plan, username="u")
    profil = tmp_path / f"konto-{plan}"
    profil.mkdir(exist_ok=True)
    zeilen = ["AQUATICY_VM_USER_MODE=true"]
    if bereit:
        zeilen.append("AQUATICY_VISION_MODEL=mistral/pixtral-large-latest")
    (profil / ".env").write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    eine = web.ChatSession(account=konto, profile=profil)
    monkeypatch.setattr(web, "SESSION", eine)
    return eine


def add_on_bereit(eine: Any) -> None:
    addons._update(eine.settings(), "whatsapp", installed=True, enabled=True,
                   login={"state": "angemeldet", "who": "laut dir", "at": 1},
                   rechte={"zugriff": "schreiben", "wo": "alle"})


def test_only_the_messenger_addons_carry_a_bridge_view(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: FakeRunner) -> None:
    eine = sitzung(tmp_path, monkeypatch)
    ansicht = web.addons_view(eine)
    mit = {a["id"] for a in ansicht["addons"] if "bruecke" in a}
    assert mit == {"whatsapp", "signal"}
    wa = next(a for a in ansicht["addons"] if a["id"] == "whatsapp")["bruecke"]
    assert wa["config"]["an"] is False and wa["config"]["wer"] == "selbst"
    assert wa["problem"], "ohne Add-on nennt die Ansicht den Grund"
    assert {"wer", "dienste", "takt"} <= set(wa["katalog"])


def test_switching_on_without_the_prerequisites_is_refused_with_the_reason(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: FakeRunner) -> None:
    eine = sitzung(tmp_path, monkeypatch)
    antwort, status = web.addon_action(
        {"action": "bridge", "id": "whatsapp", "bruecke": {"an": True}})
    assert status == 400 and "installier" in antwort["error"].lower()
    assert bridge.load_config(eine.settings())["whatsapp"]["an"] is False
    assert runner.aufrufe == []


def test_switching_on_saves_the_choices_and_wakes_the_runner(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: FakeRunner) -> None:
    eine = sitzung(tmp_path, monkeypatch)
    add_on_bereit(eine)
    antwort, status = web.addon_action({"action": "bridge", "id": "whatsapp", "bruecke": {
        "an": True, "wer": "nummern", "nummern": ["0151 2345678"], "takt": 120,
        "dienste": {"haus": "schalten", "mail": "lesen"}}})
    assert status == 200 and "bereit" in antwort["message"]
    konfig = bridge.load_config(eine.settings())["whatsapp"]
    assert konfig["an"] and konfig["wer"] == "nummern" and konfig["takt"] == 120
    assert konfig["dienste"]["haus"] == "schalten" and konfig["nummern"] == ["0151 2345678"]
    assert runner.aufrufe == ["start", "wake"]
    ansicht = next(a for a in antwort["addons"] if a["id"] == "whatsapp")["bruecke"]
    assert ansicht["config"]["an"] is True and ansicht["problem"] == ""


def test_editing_while_on_does_not_need_the_prerequisites_again(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: FakeRunner) -> None:
    eine = sitzung(tmp_path, monkeypatch)
    add_on_bereit(eine)
    web.addon_action({"action": "bridge", "id": "whatsapp", "bruecke": {"an": True}})
    addons._update(eine.settings(), "whatsapp", login={"state": "abgemeldet"})
    status = web.addon_action(
        {"action": "bridge", "id": "whatsapp", "bruecke": {"wer": "einzeln"}})[1]
    assert status == 200
    konfig = bridge.load_config(eine.settings())["whatsapp"]
    assert konfig["an"] is True and konfig["wer"] == "einzeln"


def test_switching_off_always_works(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: FakeRunner) -> None:
    eine = sitzung(tmp_path, monkeypatch)
    add_on_bereit(eine)
    web.addon_action({"action": "bridge", "id": "whatsapp", "bruecke": {"an": True}})
    antwort, status = web.addon_action(
        {"action": "bridge", "id": "whatsapp", "bruecke": {"an": False}})
    assert status == 200 and "aus" in antwort["message"]
    assert bridge.load_config(eine.settings())["whatsapp"]["an"] is False


def test_pro_accounts_cannot_switch_the_bridge_on(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: FakeRunner) -> None:
    eine = sitzung(tmp_path, monkeypatch, plan="pro")
    add_on_bereit(eine)
    antwort, status = web.addon_action(
        {"action": "bridge", "id": "whatsapp", "bruecke": {"an": True}})
    assert status == 400 and "Ultra" in antwort["error"]
    assert bridge.load_config(eine.settings())["whatsapp"]["an"] is False


@pytest.mark.parametrize("daten", [None, "an", ["an"], 5])
def test_garbage_in_the_payload_is_refused(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: FakeRunner, daten: Any) -> None:
    sitzung(tmp_path, monkeypatch)
    assert web.addon_action({"action": "bridge", "id": "whatsapp", "bruecke": daten})[1] == 400


@pytest.mark.parametrize("addon", ["wetter", "github", "telegram", "blender"])
def test_there_is_no_bridge_for_other_addons(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: FakeRunner, addon: str) -> None:
    sitzung(tmp_path, monkeypatch)
    antwort, status = web.addon_action(
        {"action": "bridge", "id": addon, "bruecke": {"an": True}})
    assert status == 400, antwort


def test_the_choices_are_cleaned_on_the_server_not_trusted_from_the_browser(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: FakeRunner) -> None:
    eine = sitzung(tmp_path, monkeypatch)
    add_on_bereit(eine)
    web.addon_action({"action": "bridge", "id": "whatsapp", "bruecke": {
        "an": True, "wer": "jeder", "takt": 1, "dienste": {"haus": "root", "x": "an"}}})
    konfig = bridge.load_config(eine.settings())["whatsapp"]
    assert konfig["wer"] == "selbst" and konfig["takt"] == bridge.DEFAULT_INTERVAL
    assert konfig["dienste"]["haus"] == "aus" and "x" not in konfig["dienste"]


@pytest.mark.parametrize("aktion", ["disable", "logout", "uninstall"])
def test_without_the_addon_the_bridge_goes_off(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: FakeRunner,
        aktion: str) -> None:
    eine = sitzung(tmp_path, monkeypatch)
    add_on_bereit(eine)
    web.addon_action({"action": "bridge", "id": "whatsapp", "bruecke": {"an": True}})
    monkeypatch.setattr(eine, "reload", lambda **kwargs: None)
    monkeypatch.setattr(addons, "logout", lambda *a, **k: None)
    monkeypatch.setattr(addons, "uninstall", lambda *a, **k: None)
    monkeypatch.setattr(addons, "set_enabled", lambda *a, **k: None)
    antwort, status = web.addon_action({"action": aktion, "id": "whatsapp"})
    assert status == 200, antwort
    assert bridge.load_config(eine.settings())["whatsapp"]["an"] is False


# -- Start und Stopp ---------------------------------------------------------------------------
def test_stopping_all_schedulers_stops_the_bridges(monkeypatch: pytest.MonkeyPatch) -> None:
    eins, zwei = FakeRunner(), FakeRunner()
    monkeypatch.setattr(web, "USER_BRIDGES", {"a": eins})
    monkeypatch.setattr(web, "BRIDGE_RUNNER", zwei)
    web._stop_schedulers()
    assert eins.aufrufe == ["stop", "wait", "close"] and zwei.aufrufe == ["stop", "wait", "close"]
    assert web.USER_BRIDGES == {} and web.BRIDGE_RUNNER is None


def test_forgetting_an_account_stops_its_bridge(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mein, fremd = FakeRunner(), FakeRunner()
    monkeypatch.setattr(web, "USER_BRIDGES", {"u1": mein, "u2": fremd})
    monkeypatch.setattr(web, "AUTH", None)
    web.forget_account_runtime(SimpleNamespace(id="u1"))
    assert mein.aufrufe == ["stop", "wait", "close"] and fremd.aufrufe == []
    assert list(web.USER_BRIDGES) == ["u2"]


def test_starting_an_account_builds_a_runner_only_when_a_bridge_is_on(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: FakeRunner) -> None:
    from aquaticy.config import Settings

    monkeypatch.setattr(web, "AUTH", SimpleNamespace(profile_dir=lambda konto_id: tmp_path))
    konto = SimpleNamespace(id="u1")
    web.start_user_bridge(konto)
    assert runner.aufrufe == [] and web.USER_BRIDGES == {}, "aus: kein Lauf, keine Einstellungen"
    bridge.set_config(Settings(data_dir=tmp_path, env_path=tmp_path / ".env"), "signal",
                      {"an": True})
    web.start_user_bridge(konto)
    web.start_user_bridge(konto)
    assert runner.aufrufe == ["start", "start"] and list(web.USER_BRIDGES) == ["u1"]


def test_starting_the_bridge_at_login_does_not_load_the_account_settings(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Die Einstellungen werden erst gebraucht, wenn jemand sie braucht -- nicht beim Login."""
    monkeypatch.setattr(web, "AUTH", SimpleNamespace(profile_dir=lambda konto_id: tmp_path))
    monkeypatch.setattr(web, "USER_BRIDGES", {})

    def verboten(account: Any) -> Any:
        raise AssertionError("Einstellungen beim Login geladen")

    monkeypatch.setattr(web.SESSIONS, "get", verboten)
    web.start_user_bridge(SimpleNamespace(id="u1"))


# -- Wann die Brücke wartet --------------------------------------------------------------------
def gebaut(monkeypatch: pytest.MonkeyPatch, konto: Any, laeuft: bool) -> Any:
    eine = SimpleNamespace(settings=lambda: SimpleNamespace(), has_running_chat=lambda: laeuft)
    runner = web._build_bridge_runner(lambda: eine, konto)
    return runner._bridge._paused


def test_the_bridge_waits_during_a_chat_a_ban_a_downgrade_and_away_from_home(
        monkeypatch: pytest.MonkeyPatch) -> None:
    konto = SimpleNamespace(id="u1", plan="ultra")
    monkeypatch.setattr(web, "_plan_of", lambda konto_id, fallback: "ultra")
    monkeypatch.setattr(web, "AIGUARD", None)
    monkeypatch.setattr(web, "CLUSTER", None)
    assert gebaut(monkeypatch, konto, False)() is False
    assert gebaut(monkeypatch, konto, True)() is True, "ein Chat läuft"
    monkeypatch.setattr(web, "_plan_of", lambda konto_id, fallback: "pro")
    assert gebaut(monkeypatch, konto, False)() is True, "herabgestuft"
    monkeypatch.setattr(web, "_plan_of", lambda konto_id, fallback: "ultra")
    monkeypatch.setattr(web, "AIGUARD", SimpleNamespace(is_banned=lambda user_id: "gesperrt"))
    assert gebaut(monkeypatch, konto, False)() is True, "Ai-guard-Sperre"
    monkeypatch.setattr(web, "AIGUARD", None)
    monkeypatch.setattr(web, "CLUSTER", SimpleNamespace(is_home=lambda konto_id: False))
    assert gebaut(monkeypatch, konto, False)() is True, "ein anderer Server ist zuhause"


def test_abuse_in_the_bridge_goes_to_ai_guard_like_in_jobs(
        monkeypatch: pytest.MonkeyPatch) -> None:
    gemeldet: list[tuple[Any, ...]] = []

    class Waechter:
        def record_incident(self, *args: Any, **kwargs: Any) -> None:
            gemeldet.append((args, kwargs))

    monkeypatch.setattr(web, "AIGUARD", Waechter())
    konto = SimpleNamespace(id="u1", ultra=False)
    web.bridge_abuse(konto, {"art": "Beleidigung", "schwere": 2})
    (args, kwargs), = gemeldet
    assert args[0] == "u1" and kwargs["chat"] == "messenger" and kwargs["enforce"] is True
    monkeypatch.setattr(web, "AIGUARD", None)
    web.bridge_abuse(konto, {"art": "x"})  # ohne Wächter: nichts, kein Fehler


# -- Oberfläche -----------------------------------------------------------------------------------
def _ui_text() -> str:
    return web.UI_FILE.read_text(encoding="utf-8")


def _english() -> dict[str, str]:
    import json
    import re

    roh = re.search(r"const EN = (\{.*?\n\});", _ui_text(), re.S)
    assert roh
    return json.loads(roh.group(1))


def test_the_ui_has_the_bridge_section_and_sends_the_bridge_action() -> None:
    html = _ui_text()
    assert "function addonBruecke(a)" in html
    assert "if (a.installed && !laeuft && a.bruecke) karte.appendChild(addonBruecke(a));" in html
    assert 'action: "bridge"' in html
    # Der Entwurf geht nur über die eigene Karte, nie als Skript-Text in die Seite.
    abschnitt = html[html.index("function addonBruecke(a)"):html.index("function zeigeAddons()")]
    assert "innerHTML" not in abschnitt.replace('titel.innerHTML = "<b></b>"', "")


def test_the_choices_the_server_sends_have_english() -> None:
    en = _english()
    eigennamen = {"Home Assistant", "Gmail", "GitHub"}
    texte = [*bridge.SCOPE_LABELS.values(), *bridge.SERVICE_LABELS.values(),
             *bridge.LEVEL_LABELS.values()]
    fehlt = {t for t in texte if t not in en} - eigennamen
    assert fehlt == set()
    html = _ui_text()
    assert "^alle (\\d+) Sekunden$" in html and "^alle (\\d+) Minuten$" in html


def test_the_reasons_the_server_gives_have_english(tmp_path: Path) -> None:

    en = _english()
    html = _ui_text()
    ordner = tmp_path / "k"
    ordner.mkdir()
    from aquaticy.config import Settings

    konto = Settings(data_dir=ordner, env_path=ordner / ".env")
    assert bridge.ready_problem(konto, "whatsapp", pro=False) in en
    assert bridge.ready_problem(konto, "whatsapp", pro=True) in en
    # Die Sätze mit Namen laufen über Muster: jedes steht in der Seite -- und sein
    # deutscher Satz steht in bridge.py.
    quelle = Path(bridge.__file__).read_text(encoding="utf-8")
    for muster, satz in (
            (r"ist nicht installiert\. Installiere das Add-on zuerst\.$",
             "Installiere das Add-on zuerst."),
            (r"ist ausgeschaltet\. Schalte das Add-on zuerst ein\.$",
             "Schalte das Add-on zuerst ein."),
            (r"Melde dich zuerst bei (.+) an \(Add-on, QR-Code\)\.$", "(Add-on, QR-Code)."),
            (r"ist nicht angemeldet \(QR-Code zu sehen\)\. Melde dich im Add-on neu an\.$",
             "Melde dich im Add-on neu an."),
            (r"Der Bildschirm ließ sich nicht lesen: (.+)$",
             "Der Bildschirm ließ sich nicht lesen:"),
            (r"Der Chat ließ sich nicht bearbeiten: (.+)$",
             "Der Chat ließ sich nicht bearbeiten:"),
            (r"steht „Nur lesen“\\. Wähle dort „Lesen und schreiben“, ",
             "„Nur lesen“. Wähle dort „Lesen und schreiben“,")):
        assert muster in html, muster
        assert satz in quelle, satz
    assert "braucht ein Vision-Modell, um den Messenger zu sehen" in quelle
    assert "Aquaticy braucht ein Vision-Modell, um den Messenger zu sehen (Modelle und " \
        "Verbindungen → Vision-Modell)." in en
