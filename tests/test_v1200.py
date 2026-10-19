"""12.0.0 Luna: Arbeitsweise in der Seitenleiste, Mikrofon, Auto-Scroll -- und Modelle nur
noch von Mistral, NVIDIA NIM oder vom Server selbst, Schluessel nur ueber Add-ons."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aquaticy import addons, config, keyvault, llmcall, uistate, web
from aquaticy.config import MODEL_RULE_TEXT, ModelNotAllowed, local_address, model_allowed
from tests.test_web import port, raw_request, session, web_settings  # noqa: F401


def _ui() -> str:
    return web.UI_FILE.read_text(encoding="utf-8")


# -- Oberflaeche ---------------------------------------------------------------------------
def test_the_modes_sit_in_the_sidebar_under_the_logo() -> None:
    html = _ui()
    leiste = html[html.index("<aside>"): html.index("</aside>")]
    assert leiste.index('class="brand"') < leiste.index('id="modes"') \
        < leiste.index('id="btn-new"') < leiste.index("Letzte Chats")
    fuss = html[html.index("<footer>"): html.index("</footer>")]
    assert 'id="modes"' not in fuss and 'data-mode=' not in fuss
    # Auf dem Handy liegt die Leiste ueber dem Chat: nach der Wahl geht sie zu.
    klick = html[html.index('document.querySelectorAll("#modes .mode").forEach(button =>\n'
                            '  button.addEventListener("click"'):]
    klick = klick[: klick.index("}));")]
    assert 'if (narrow()) document.body.classList.add("collapsed");' in klick


def test_the_composer_row_is_attach_model_microphone_send() -> None:
    html = _ui()
    reihe = html[html.index('<div class="crow">'):]
    reihe = reihe[: reihe.index("</div>")]
    stellen = [reihe.index(f'id="{teil}"') for teil in ("clip", "btn-model", "mic", "send")]
    assert stellen == sorted(stellen)
    assert 'aria-label="Spracheingabe"' in reihe and 'aria-pressed="false"' in reihe
    # Das Modellmenue oeffnet sich jetzt links am Knopf, nicht mehr rechts am Senden.
    assert 'const knopf = document.querySelector("#btn-model");' in html
    assert 'modelBox.style.right = "auto";' in html


def test_voice_input_explains_first_and_then_sends_by_itself() -> None:
    html = _ui()
    dialog = html[html.index('<div class="overlay" id="voicebox">'):]
    dialog = " ".join(dialog[: dialog.index('<div class="overlay" id="overlay">')].split())
    # Alle Fakten: wer die Aufnahme bekommt, was Aquaticy bekommt.
    for fakt in ("Chrome: Google", "Edge: Microsoft", "Safari: Apple", "auf dem Gerät",
                 "nur den erkannten Text", "nie die Aufnahme"):
        assert fakt in dialog, fakt
    skript = html[html.index("/* ---------- Spracheingabe (12.0.0 Luna) ----------"):]
    skript = skript[: skript.index("/* ---------- Seitenleiste ---------- */")]
    assert "window.SpeechRecognition || window.webkitSpeechRecognition" in skript
    assert "if (!stimmeOk){ openOverlay(voiceBox);" in skript, "erst der Hinweis"
    assert "merkeZustand({ voice_ok: true });" in skript
    assert "if (!busy) send.click();" in skript, "nach dem Sprechen geht es von selbst los"
    assert "window.isSecureContext" in skript
    assert 'document.addEventListener("visibilitychange"' in skript
    # Waehrend Aquaticy antwortet, hoert das Mikrofon nicht zu; Esc bricht ab.
    assert '$("#mic").disabled = on;' in html and "if (on) hoerenStoppen(false);" in html
    assert "if (hoeren) { hoerenStoppen(false); return; }" in html
    # Und die Datenschutzseite sagt dasselbe.
    from aquaticy.legal import legal_page

    roh = legal_page("/privacy")
    seite = " ".join((roh.decode("utf-8") if isinstance(roh, bytes) else str(roh)).split())
    assert "Spracheingabe" in seite and "Eine Aufnahme erreicht den Server nie" in seite


def test_the_microphone_is_allowed_for_the_own_page_only(port: int) -> None:  # noqa: F811
    status, kopf, _ = raw_request(port, "GET", "/")
    assert status == 200
    regel = kopf["Permissions-Policy"]
    assert "microphone=(self)" in regel and "camera=()" in regel and "geolocation=()" in regel
    assert kopf["X-Frame-Options"] == "DENY", "eingebettet wird die Seite weiterhin nie"


def test_auto_scroll_is_a_design_choice_kept_on_the_server() -> None:
    assert uistate.defaults()["autoscroll"] is True
    assert uistate.clean({"autoscroll": "false"})["autoscroll"] is False
    assert uistate.clean({"autoscroll": "vielleicht"})["autoscroll"] is True
    assert uistate.defaults()["voice_ok"] is False
    html = _ui()
    design = html[html.index('<div class="overlay" id="themebox">'):]
    design = design[: design.index('<div class="overlay"', 10)]
    assert 'id="autoscroll"' in design and 'data-scroll="on"' in design \
        and 'data-scroll="off"' in design
    assert "setAutoScroll(START.autoscroll !== false, { merken: false });" in html
    # Aus heisst: die neue Frage und der Anfang der Antwort kommen noch ins Bild ...
    assert "if (!immer && !autoScroll) return;" in html
    assert html.count("thread.appendChild(el); scroll(true);") == 2
    # ... und "Standard" stellt es wieder an.
    assert 'setSchrift("normal"); setAutoScroll(true);' in html


# -- Nur Mistral, NVIDIA NIM oder der Server selbst ----------------------------------------
@pytest.mark.parametrize("modell, adresse", [
    ("mistral/mistral-large-latest", ""),
    ("nvidia_nim/meta/llama-3.3-70b-instruct", ""),
    ("nvidia_nim/openai/gpt-oss-120b", ""),          # offenes Modell bei NVIDIA
    ("ollama_chat/qwen2.5:7b", ""),                   # Ollama auf dem Server
    ("ollama_chat/qwen2.5:7b", "http://127.0.0.1:11434"),
    ("openai/lokal", "http://192.168.1.20:1234/v1"),  # LM Studio im Heimnetz
    ("openai/lokal", "http://lmstudio.local:1234/v1"),
    ("hosted_vllm/qwen", "http://[::1]:8000/v1"),
    ("lm_studio/qwen", ""),
    (config.SPLIT_MODEL_ID, ""),
])
def test_allowed_models(modell: str, adresse: str, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OLLAMA_API_BASE", "LM_STUDIO_API_BASE", "OPENAI_API_BASE", "OPENAI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    assert model_allowed(modell, adresse)


@pytest.mark.parametrize("modell, adresse", [
    ("anthropic/claude-sonnet-4-5", ""),
    ("openai/gpt-4o", ""),                            # ohne Adresse: OpenAI selbst
    ("openai/gpt-4o", "https://api.openai.com/v1"),
    ("gemini/gemini-2.5-pro", ""),
    ("vertex_ai/gemini-2.5-pro", ""),
    ("azure/gpt-4o", "https://firma.openai.azure.com"),
    ("openrouter/anthropic/claude-3.5-sonnet", ""),
    ("bedrock/anthropic.claude-3-sonnet", ""),
    ("groq/llama-3.3-70b-versatile", ""),             # andere Cloud: auch nicht
    ("gpt-4o", ""), ("claude-3-5-sonnet", ""),        # ohne Kuerzel geht es in die Cloud
    ("ollama_chat/gpt-oss:120b-cloud", ""),           # Ollama reicht das an ollama.com weiter
    ("ollama_chat/qwen2.5:7b", "http://8.8.8.8:11434"),
    ("openai/lokal", "http://1.1.1.1:1234/v1"),       # oeffentliche Adresse ist kein Server hier
    ("hosted_vllm/qwen", ""),
])
def test_everything_else_is_refused(modell: str, adresse: str,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HOSTED_VLLM_API_BASE", "OPENAI_API_BASE", "OPENAI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    assert not model_allowed(modell, adresse)
    # Ein Anbieter, den LiteLLM kennt, bekommt die Regel. Ein Name, den es keinem
    # zuordnet ("claude-3-5-sonnet"), bekommt den Hinweis aufs fehlende Kuerzel.
    problem = config.model_problem(modell, adresse)
    if config.resolve_model(modell):
        assert problem == MODEL_RULE_TEXT
    else:
        assert "keinem Anbieter" in problem


def test_a_local_name_is_looked_up_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from aquaticy import netguard

    gefragt: list[str] = []

    def nachschlagen(host: str, anschluss: int | None) -> list[str]:
        gefragt.append(host)
        return {"gpu-server": ["10.0.0.7"], "ki.example.org": ["93.184.216.34"]}[host]

    monkeypatch.setattr(netguard, "resolve", nachschlagen)
    config._LOKAL_MERK.clear()
    assert local_address("http://gpu-server:8000/v1")
    assert local_address("http://gpu-server:8000/v1")
    assert not local_address("https://ki.example.org/v1")
    assert gefragt == ["gpu-server", "ki.example.org"], "fuenf Minuten gemerkt"
    assert local_address("http://localhost:1234") and local_address("http://box.lan")
    assert not local_address("") and not local_address("http://")


def test_no_call_leaves_for_a_refused_model(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    monkeypatch.setattr(litellm, "completion", lambda **k: pytest.fail("Anfrage geschickt"))
    for modell in ("anthropic/claude-sonnet-4-5", "openai/gpt-4o", "gemini/gemini-2.5-pro"):
        with pytest.raises(ModelNotAllowed, match="Mistral und NVIDIA NIM"):
            llmcall.completion(model=modell, messages=[{"role": "user", "content": "."}])


def test_settings_refuse_such_a_model(session: web.ChatSession) -> None:  # noqa: F811
    with pytest.raises(ValueError, match="Mistral und NVIDIA NIM"):
        web.save_values({"AQUATICY_MODEL": "anthropic/claude-sonnet-4-5"})
    with pytest.raises(ValueError, match="Mistral und NVIDIA NIM"):
        web.save_values({"AQUATICY_CODE_MODEL": "openai/gpt-4o"})
    antwort = session.command("/model gemini/gemini-2.5-pro")
    assert MODEL_RULE_TEXT in antwort["text"]


def test_the_picker_never_offers_a_refused_model(monkeypatch: pytest.MonkeyPatch,
                                                 tmp_path: Path) -> None:
    from aquaticy.config import Settings
    from aquaticy.system import model_usable

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-betreiber-1234")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-betreiber-1234")
    s = Settings(model="mistral/mistral-large-latest", data_dir=tmp_path)
    assert not model_usable(s, "anthropic/claude-sonnet-4-5", installed=[])
    assert not model_usable(s, "groq/llama-3.3-70b-versatile", installed=[])


# -- Schluessel nur ueber die Add-ons NVIDIA NIM und Mistral -------------------------------
def test_old_keys_are_deleted_from_the_vault(tmp_path: Path) -> None:
    geheim = b"s" * 32
    tresor = keyvault.KeyVault(tmp_path / "k.sqlite3", "konto-a", geheim)
    tresor.set("MISTRAL_API_KEY", "eigen-mistral-geheim-1111")
    tresor.set_secret("HA_TOKEN", "ha-token-1234567890")
    # So lagen sie bis 11.4.1 da -- Claude, Tavily, der allgemeine Platz.
    with sqlite3.connect(tmp_path / "k.sqlite3") as conn:
        for name in ("ANTHROPIC_API_KEY", "TAVILY_API_KEY", "AQUATICY_API_KEY"):
            conn.execute("INSERT INTO api_keys VALUES ('konto-a', ?, 'x', '', 1.0)", (name,))
        conn.execute("INSERT INTO api_keys VALUES ('konto-b', 'OPENAI_API_KEY', 'x', '', 1.0)")
    keyvault.KeyVault(tmp_path / "k.sqlite3", "konto-a", geheim)
    with sqlite3.connect(tmp_path / "k.sqlite3") as conn:
        namen = {(z[0], z[1]) for z in conn.execute("SELECT account_id, name FROM api_keys")}
    assert namen == {("konto-a", "MISTRAL_API_KEY"), ("konto-a", "HA_TOKEN"),
                     ("konto-b", "OPENAI_API_KEY")}, "nur im eigenen Konto aufgeraeumt"


def test_nvidia_and_mistral_are_the_first_addons_and_no_tools(tmp_path: Path) -> None:
    import types

    assert list(addons.CATALOG)[:2] == ["nvidia_nim", "mistral"]
    for kennung in ("nvidia_nim", "mistral"):
        addon = addons.CATALOG[kennung]
        assert addon.login == "apikey" and addon.group == "KI-Modelle" and not addon.werkstatt
    einstellungen = types.SimpleNamespace(data_dir=tmp_path)
    addons.install(einstellungen, "mistral", pro=False)
    assert addons.installed(einstellungen, "mistral")
    assert "mistral" not in addons.active_ids(einstellungen), "kein Befehl, kein Werkzeug"
    with pytest.raises(addons.AddOnError, match="keinen Schalter"):
        addons.set_enabled(einstellungen, "mistral", False, pro=False)
    karte = next(a for a in addons.public_view(einstellungen, False)["addons"]
                 if a["id"] == "mistral")
    assert karte["command"] == "" and karte["installed"]


def test_the_addon_cards_carry_the_key_entry_and_nothing_else_does() -> None:
    html = _ui()
    assert 'if (a.login_kind === "apikey") return addonKonto(a);' in html
    assert 'a.installed && a.login_kind !== "apikey"' in html, "kein Schalter"
    # Kein Sammelfeld oben, kein Bereich "API-Schluessel" in den Einstellungen.
    for weg in ('id="linked-quick-key"', 'id="keys"', 'id="keys-summary"', "/api/keys",
                "function zeichneKeys", "sk-ant-", "AIza"):
        assert weg not in html, weg
    # Aus Einstellungen -> Modell fuehrt ein Knopf zu den Add-ons.
    modell = html[html.index("<fieldset><legend>Modell</legend>"):]
    modell = modell[: modell.index("</fieldset>")]
    assert 'id="btn-addons-modell"' in modell


def test_the_server_takes_keys_only_through_the_addon() -> None:
    quelle = Path(web.__file__).read_text(encoding="utf-8")
    assert '"/api/keys"' not in quelle
    assert "API_KEY_FIELD" not in quelle and "SEARCH_KEY_FIELD" not in quelle
    assert 'f"Installiere zuerst das Add-on {d[\'label\']}."' in quelle


def test_the_setup_wizard_asks_for_no_key() -> None:
    from aquaticy import cli

    quelle = Path(cli.__file__).read_text(encoding="utf-8")
    assert 'typer.prompt(f"{key_name}"' not in quelle
    assert "unter Add-ons" in quelle


def test_twelve_is_the_version() -> None:
    import aquaticy

    # Nummer und Name stehen seit 12.0.1 Nutshell nur in tests/test_version.py --
    # hier: noch Fassung 12 und die Rueckfallangabe passt zu beidem.
    assert aquaticy.__version__.startswith("12.")
    label = f"{aquaticy.__version__} {aquaticy.__codename__}"
    assert f'window.__AQUATICY_VERSION__ || "{label}"' in _ui()
