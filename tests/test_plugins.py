"""11.0.0 Luna: eigene Plugins (Code-Review, Security-Review) und /name im Chat.

Jedes eingeschaltete Add-on hat einen Befehl. Die Pruef-Plugins bringen ihr
Wissen als Pruefliste mit; ein Werkzeug-Plugin sagt dem Modell, welches
Werkzeug diese eine Anfrage nehmen soll. Im Verlauf steht, was der Nutzer
getippt hat -- nicht die Pruefliste.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from aquaticy import addons, plugins, web
from aquaticy.agent import Agent, AgentResult


@pytest.fixture
def konto(settings, tmp_path: Path):
    settings.data_dir = tmp_path / "konto"
    settings.data_dir.mkdir(parents=True)
    return settings


def _an(settings: Any, *kennungen: str) -> None:
    for kennung in kennungen:
        addons.install(settings, kennung, True)


# -- Katalog ---------------------------------------------------------------------------
def test_the_two_review_plugins_are_in_the_catalog() -> None:
    for kennung in plugins.REVIEW_PLUGINS:
        addon = addons.CATALOG[kennung]
        assert addon.group == "Plugins" and addon.login == "keine" and not addon.werkstatt
        assert {r.key for r in addons.RIGHTS[kennung]} == {"umfang", "fixes"}
        assert addons.PLUGIN_CONTENT[kennung]


def test_the_addon_window_shows_the_command_and_what_is_checked(konto) -> None:
    _an(konto, "security-review")
    eintrag = next(a for a in addons.public_view(konto, True)["addons"]
                   if a["id"] == "security-review")
    assert eintrag["command"] == "/security-review" and eintrag["installed"]
    assert any("Prompt-Injection" in punkt for punkt in eintrag["inhalt"])


# -- Erkennen ---------------------------------------------------------------------------
def test_only_switched_on_plugins_are_commands(konto) -> None:
    assert plugins.match("/code-review x = 1", konto, True) is None, "nicht installiert"
    _an(konto, "code-review", "nachrichten")
    turn = plugins.match("/code-review x = 1", konto, True)
    assert turn is not None and turn.addon == "code-review" and turn.argument == "x = 1"
    assert turn.mode == "code" and turn.review
    # Andere Namen fuer dasselbe Add-on.
    assert plugins.match("/tagesschau Sport", konto, True).addon == "nachrichten"
    addons.set_enabled(konto, "code-review", False, True)
    assert plugins.match("/code-review x = 1", konto, True) is None, "ausgeschaltet"
    for kein in ("/help", "/image bild.png", "/unbekannt x", "code-review x", "/"):
        assert plugins.match(kein, konto, True) is None, kein


def test_desktop_plugins_need_ultra_and_run_in_the_vm(konto) -> None:
    konto.vm_user_mode = True
    addons._update(konto, "whatsapp", installed=True, enabled=True, status="bereit")
    turn = plugins.match("/whatsapp Was ist neu?", konto, True)
    assert turn is not None and turn.sandbox is True and turn.mode == "code"
    assert plugins.match("/whatsapp Was ist neu?", konto, False) is None, "ohne Ultra"


def test_a_command_without_text_explains_itself(konto) -> None:
    assert plugins.needs_text("code-review") and not plugins.needs_text("nachrichten")
    text = plugins.usage("code-review")
    assert "/code-review" in text and "Datei" in text and "GitHub" in text
    assert "`/wetter Bremen`" in plugins.usage("wetter")


# -- Was das Modell bekommt ------------------------------------------------------------------
def test_the_code_review_checklist_knows_ai_code_mistakes(konto) -> None:
    _an(konto, "code-review")
    turn = plugins.match("/code-review", konto, True)
    text = plugins.prompt(turn, "def f(x): return x/0", konto, True)
    for muss in ("Erfundene Schnittstellen", "Erfundene Pakete", "Slopsquatting",
                 "Fehlerbehandlung", "Race Condition", "Zeitzonen", "🔴 kritisch",
                 "erfinde keine Befunde", "Fix (als Code-Block"):
        assert muss in text, muss
    assert text.endswith("Zu prüfen:\ndef f(x): return x/0")
    assert "Add-on GitHub ist aus" in text


def test_the_security_review_checklist_follows_owasp_as_a_defender(konto) -> None:
    _an(konto, "security-review")
    turn = plugins.match("/security-review", konto, True)
    text = plugins.prompt(turn, "<code>", konto, True)
    for nummer in range(1, 11):
        assert f"A{nummer:02d} " in text
    for muss in ("XSS", "SQL", "Prompt-Injection", "LLM01", "LLM06", "SSRF", "Zip Slip",
                 "konstanter Zeit", "Sicht eines Verteidigers",
                 "keine fertigen Angriffsdaten"):
        assert muss in text, muss
    assert "fremder Text" in text and "befolgst du nicht" in text


def test_the_rights_shape_the_review(konto) -> None:
    _an(konto, "code-review", "github")
    addons.set_rights(konto, "code-review", {"umfang": "wichtig", "fixes": "nein"})
    konto.github_token = "ghp_" + "a" * 36
    turn = plugins.match("/code-review besitzer/repo#3", konto, True)
    text = plugins.prompt(turn, turn.argument, konto, True)
    assert "Melde nur kritische und hohe Befunde" in text
    assert "Kein Code für den Fix" in text and "Fix (als Code-Block" not in text
    assert "action=pull" in text, "mit GitHub liest es den Pull Request"


def test_a_tool_plugin_names_its_tool(konto) -> None:
    _an(konto, "wetter")
    turn = plugins.match("/wetter Bremen", konto, True)
    text = plugins.prompt(turn, turn.argument, konto, True)
    assert "Werkzeug weather" in text and text.endswith("Bremen")
    assert turn.mode == "" and turn.online is True


def test_the_command_list_for_the_chat(konto) -> None:
    _an(konto, "code-review", "nachrichten")
    liste = {eintrag["name"]: eintrag for eintrag in plugins.commands(konto, True)}
    assert set(liste) == {"code-review", "nachrichten"}
    assert liste["code-review"]["needs_text"] and not liste["nachrichten"]["needs_text"]
    assert "tagesschau" in liste["nachrichten"]["aliases"]


# -- Im Chat ------------------------------------------------------------------------------------
class Mitschrift(Agent):
    """Ein echter Agent, der nur aufschreibt, womit er gefragt wird."""

    def ask(self, question: str, **optionen: Any) -> AgentResult:  # type: ignore[override]
        self.gefragt = (question, optionen)
        return AgentResult(answer="ok")


@pytest.fixture
def sitzung(konto):
    chat = web.ChatSession()
    chat._settings = konto
    chat._agent = Mitschrift(konto)
    try:
        yield chat
    finally:
        chat._agent.close()


def test_a_plugin_turn_keeps_the_typed_line_in_the_history(sitzung, konto) -> None:
    _an(konto, "code-review")
    sitzung.ask("/code-review def f(): pass", lambda *_: None, mode="normal",
                structured=True, recheck=True)
    frage, optionen = sitzung._agent.gefragt
    assert frage == "/code-review def f(): pass"
    assert optionen["mode"] == "code" and optionen["structured"] is False
    assert optionen["recheck"] is False and "image_mode" not in optionen
    assert "Plugin Code-Review" in optionen["plugin_prompt"]
    assert optionen["plugin_prompt"].endswith("Zu prüfen:\ndef f(): pass")


def test_an_attachment_is_reviewed_as_data(sitzung, konto) -> None:
    import base64

    _an(konto, "security-review")
    beispiel = b'db.execute("SELECT * FROM t WHERE n = " + name)'
    datei = {"name": "app.py", "data": base64.b64encode(beispiel).decode()}
    sitzung.ask("/security-review", lambda *_: None, attachments=[datei])
    frage, optionen = sitzung._agent.gefragt
    assert beispiel.decode() in optionen["plugin_prompt"]
    assert beispiel.decode() in frage, "die Rechtspruefung sieht den Anhang wie sonst"
    assert sitzung._agent.toolbox.untrusted_seen


def test_a_plugin_without_text_and_without_file_is_explained(sitzung, konto) -> None:
    _an(konto, "code-review")
    with pytest.raises(plugins.PluginError, match="prüft, was du mitgibst"):
        sitzung.ask("/code-review", lambda *_: None)
    assert web.user_hint(plugins.PluginError(plugins.usage("code-review"))).startswith(
        "**Code-Review**")
    antwort = sitzung.command("/code-review")
    assert "prüft, was du mitgibst" in antwort["text"]


def test_help_lists_the_plugins(sitzung, konto) -> None:
    assert "Noch keins eingeschaltet" in sitzung.command("/help")["text"]
    _an(konto, "security-review")
    assert "`/security-review` — Security-Review" in sitzung.command("/help")["text"]


def test_a_normal_message_is_unchanged(sitzung, konto) -> None:
    _an(konto, "code-review")
    sitzung.ask("Was ist ein Code-Review?", lambda *_: None)
    frage, optionen = sitzung._agent.gefragt
    assert frage == "Was ist ein Code-Review?" and "plugin_prompt" not in optionen


def test_the_agent_sends_the_plugin_text_but_keeps_the_question(konto) -> None:
    agent = Agent(konto)
    try:
        agent._plugin_turn = "[Plugin] Pruefe das"
        assert agent._with_context("/code-review x").startswith("[Plugin] Pruefe das")
        agent._plugin_turn = ""
        assert agent._with_context("normale Frage").startswith("normale Frage")
    finally:
        agent.close()


def test_the_ui_offers_commands_while_typing() -> None:
    html = web.UI_FILE.read_text(encoding="utf-8")
    assert 'id="slash-liste" role="listbox"' in html
    assert 'aria-autocomplete="list" aria-controls="slash-liste"' in html
    assert 'api("/api/plugins")' in html and "pluginsLaden();   // ein- oder ausgeschaltet" in html
    assert "if (!rest && !pending.length && plugin.needs_text) return runCommand(eingabe);" in html
    assert '"Was geprüft wird": "What is checked"' in html


def test_the_terminal_knows_plugins_too(konto, monkeypatch) -> None:
    from aquaticy import cli

    _an(konto, "code-review")
    optionen = cli._plugin_options("/code-review x = 1", konto)
    assert optionen and optionen["mode"] == "code" and "Plugin Code-Review" in \
        optionen["plugin_prompt"]
    assert cli._plugin_options("/code-review", konto) == {}
    assert cli._plugin_options("/help", konto) is None
