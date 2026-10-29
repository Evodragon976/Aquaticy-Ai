"""Messenger-Modellwahl und Arbeitsmodi, ohne echte Konten oder Modellaufrufe."""


import pytest

from aquaticy import bridge, system
from aquaticy.config import Settings
from aquaticy.messenger_modes import switch_request
from tests.test_bridge import FakeAgent, cfg


@pytest.fixture
def mobile(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path, model="ollama_chat/qwen2.5:7b", max_subagents=12)
    models = [{"id": "ollama_chat/qwen2.5:7b", "label": "qwen2.5:7b"},
              {"id": "mistral/mistral-large-latest", "label": "Mistral Large"}]
    monkeypatch.setattr(system, "available_models", lambda s: models)
    answerer = bridge.AgentAnswerer(lambda: settings, agent_factory=FakeAgent)
    return settings, models, answerer


def ask(mobile, text, *, key="wa:me", trusted=True, owner=True, config=None):
    return mobile[2](text, bridge.Decision(True, trusted=trusted, selbst=owner),
                     config or cfg(), key, "whatsapp")


@pytest.mark.parametrize("text", ["wechsle bitte dein llm", "Wechsle dein Modell!",
                                  "bitte wechsle dein LLM", "wechsel bitte dein llm"])
def test_natural_switch_is_a_command(mobile, text):
    assert switch_request(text)
    assert "/switch ollama_chat/qwen2.5:7b" in ask(mobile, text)
    assert not mobile[2]._agents


def test_switch_is_allowlisted_and_chat_local(mobile):
    base, _, answerer = mobile
    assert "mistral/mistral-large-latest" in ask(mobile, "/switch Mistral Large")
    ask(mobile, "Hallo")
    settings = answerer._agents["wa:me"][0].settings
    assert settings.model == "mistral/mistral-large-latest" and not settings.auto_model
    ask(mobile, "Hallo", key="signal:me")
    assert answerer._agents["signal:me"][0].settings.model == base.model
    assert base.model == "ollama_chat/qwen2.5:7b"
    assert "nicht verfügbar" in ask(mobile, "/switch openai/not-owned")
    assert answerer._mobile["wa:me"]["model"] == settings.model


def test_qwen_alias_is_unique_or_refused(mobile):
    assert "für diesen Chat" in ask(mobile, "/switch Qwen 7b")
    mobile[1].append({"id": "ollama_chat/qwen3:7b", "label": "qwen3:7b"})
    assert "nicht eindeutig" in ask(mobile, "/switch Qwen 7b")


def test_normal_pro_and_reset_are_independent(mobile):
    base, _, answerer = mobile
    ask(mobile, "Hallo")
    agent = answerer._agents["wa:me"][0]
    assert agent.settings.max_subagents == 4
    assert agent.fragen[-1][1]["mode"] == "normal"
    assert not agent.fragen[-1][1]["structured"] and not agent.fragen[-1][1]["recheck"]
    assert "Pro-Modus" in ask(mobile, "/pro")
    ask(mobile, "Recherche")
    agent = answerer._agents["wa:me"][0]
    assert agent.settings.max_subagents == 12
    assert agent.fragen[-1][1]["mode"] == "pro"
    assert agent.fragen[-1][1]["structured"] and agent.fragen[-1][1]["recheck"]
    assert not agent.fragen[-1][1]["sandbox"]
    ask(mobile, "Andere Frage", key="signal:me")
    assert answerer._agents["signal:me"][0].fragen[-1][1]["mode"] == "normal"
    ask(mobile, "/pro aus")
    ask(mobile, "Zurück")
    assert answerer._agents["wa:me"][0].settings.max_subagents == 4
    assert base.max_subagents == 12


@pytest.mark.parametrize("command", ["/pro", "/switch", "/switch Qwen 7b", "/max Frage"])
def test_untrusted_cannot_change_model_or_pro(mobile, command):
    assert "freigegebene" in ask(mobile, command, owner=False, trusted=False)
    assert not mobile[2]._agents
    assert not mobile[2]._mobile


def test_pro_keeps_private_services_and_offline_restrictions(mobile):
    ask(mobile, "/pro")
    ask(mobile, "Hallo", config=cfg(dienste={"web": "aus"}))
    agent = mobile[2]._agents["wa:me"][0]
    assert agent.settings.max_subagents == 0
    assert "research_subtasks" not in agent.erlaubt
    assert "ha_call" not in agent.erlaubt and "mail_read" not in agent.erlaubt
    assert not agent.settings.memory_enabled and not agent.settings.lan_enabled


def test_model_pages_keep_switch_instructions(mobile):
    mobile[1][:] = [{"id": f"mistral/model-{n}", "label": "Modell " + str(n)}
                    for n in range(150)]
    text = ask(mobile, "/switch")
    assert "Seite 1/" in text and len(text) < 1700
    assert text.endswith("/switch Qwen 7b.")
    assert "Seite 2/" in ask(mobile, "/switch seite 2")


def test_export_and_quit_are_mobile_commands(mobile):
    ask(mobile, "Hallo")
    assert "user: Hallo" in ask(mobile, "/export")
    assert "eigenen Chat" in ask(mobile, "/export", owner=False)
    ask(mobile, "/pro")
    assert "Gespräch beendet" in ask(mobile, "/quit")
    assert mobile[2]._mobile["wa:me"] == {}
    assert len(mobile[2]._agents["wa:me"][0].messages) == 1


def test_help_marks_mobile_commands(mobile):
    text = ask(mobile, "/help")
    for command in ("/switch", "/pro", "/normal", "/max", "/export"):
        assert command in text
    assert "(mobile)" in text


def test_real_bridge_agent_keeps_tool_gate(mobile):
    settings = mobile[0]
    settings.max_subagents = 4
    agent = bridge.bridge_agent_class()(settings, frozenset({"calculate"}), "")
    try:
        assert agent.use_subagents
        assert agent._tor("mail_read", {})["skipped_reason"] == "bruecke"
        assert agent._tor("vm_run", {})["skipped_reason"] == "bruecke"
    finally:
        agent.close()


def test_model_alias_obeys_same_allowlist(mobile):
    assert "für diesen Chat" in ask(mobile, "/model Qwen 7b")
    previous = dict(mobile[2]._mobile["wa:me"])
    assert "nicht verfügbar" in ask(mobile, "/model evil/unknown")
    assert mobile[2]._mobile["wa:me"] == previous


def test_max_enters_pro_and_keeps_tool_restrictions(mobile):
    assert "Antwort auf" in ask(mobile, "/max Frage")
    agent = mobile[2]._agents["wa:me"][0]
    assert agent.fragen[-1][0] == "/max Frage"
    assert agent.fragen[-1][1]["mode"] == "pro"
    assert "vm_run" not in agent.erlaubt and "ha_call" not in agent.erlaubt


def test_export_html_stays_in_own_chat(mobile):
    ask(mobile, "Hallo")
    assert "user: Hallo" in ask(mobile, "/export html")
    assert "eigenen Chat" in ask(mobile, "/export html", owner=False)


def test_bad_model_discovery_never_changes_selection(mobile, monkeypatch):
    def failed(settings):
        raise RuntimeError("private credential must not appear")

    monkeypatch.setattr(system, "available_models", failed)
    text = ask(mobile, "/switch")
    assert "nicht erreichbar" in text and "credential" not in text
    assert not mobile[2]._mobile["wa:me"]


def test_actual_agent_normal_limit_and_subagent_dispatch(mobile, monkeypatch):
    import aquaticy.subagents

    settings = mobile[0]
    settings.max_subagents = 4
    calls = []

    def run(tasks, settings, **kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(aquaticy.subagents, "run_subagents", run)
    agent = bridge.bridge_agent_class()(settings, frozenset({"research_subtasks"}), "")
    try:
        agent.mode = "normal"
        assert agent.agent_limit == 4
        agent._run_subagents(["Frage"] * 20)
        assert calls[-1]["limit"] == 4 and calls[-1]["checkers"] == 0
        assert agent._tor("desktop_open", {})["skipped_reason"] == "bruecke"
    finally:
        agent.close()


def test_export_pages_are_complete_and_fit_messenger(mobile):
    from aquaticy.bridge import to_chat_text

    ask(mobile, "Start")
    agent = mobile[2]._agents["wa:me"][0]
    agent.messages.append({"role": "assistant", "content": "A" * 4000 + "ENDE"})
    first = ask(mobile, "/export")
    second = ask(mobile, "/export seite 2")
    last = ask(mobile, "/export seite 3")
    assert "Seite 1/3" in first and "Seite 2/3" in second
    assert "ENDE" in last and "Seite 3/3" in last
    assert all(len(t) < 1800 for t in (first, second, last))
    assert "/export seite 2" in to_chat_text(first)
