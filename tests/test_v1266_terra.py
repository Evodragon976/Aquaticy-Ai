"""12.6.6 Terra: Desktop-Dateien in pip-Installationen und private Messenger-Verlaeufe."""

import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aquaticy import bridge, sandbox
from aquaticy.config import Settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    paket = tmp_path / "site-packages" / "aquaticy"
    paket.mkdir(parents=True)
    monkeypatch.setattr(sandbox, "__file__", str(paket / "sandbox.py"))
    return paket


def resources(paket: Path) -> None:
    ziel = paket / "_desktop"
    shutil.copytree(ROOT / "docker" / "desktop", ziel / "desktop")
    shutil.copy2(ROOT / "docker" / "workshop-desktop.Dockerfile", ziel)


def test_installed_package_finds_its_recipe_without_a_checkout(installed: Path) -> None:
    resources(installed)
    rezept = sandbox.desktop_recipe()
    assert rezept is not None
    assert rezept[0] == installed / "_desktop" / "workshop-desktop.Dockerfile"
    assert rezept[0].read_bytes() == (ROOT / "docker/workshop-desktop.Dockerfile").read_bytes()


@pytest.mark.parametrize("missing", ["workshop-desktop.Dockerfile", *sandbox.DESKTOP_HELPERS])
def test_incomplete_installation_is_rejected(installed: Path, missing: str) -> None:
    resources(installed)
    datei = installed / "_desktop" / missing
    if missing in sandbox.DESKTOP_HELPERS:
        datei = installed / "_desktop" / "desktop" / missing
    datei.unlink()
    assert sandbox.desktop_recipe() is None


def test_neither_working_directory_nor_unrelated_sibling_supplies_a_recipe(
    installed: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    for ordner in (tmp_path / "untrusted", installed.parent):
        shutil.copytree(ROOT / "docker" / "desktop", ordner / "docker" / "desktop")
        shutil.copy2(ROOT / "docker" / "workshop-desktop.Dockerfile", ordner / "docker")
    monkeypatch.chdir(tmp_path / "untrusted")
    assert sandbox.desktop_recipe() is None


class Agent:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.messages = [{"role": "system", "content": "system"}]
        self.closed = False

    def ask(self, text: str, **kwargs: Any) -> Any:
        self.messages.append({"role": "assistant", "content": text})
        return SimpleNamespace(answer=text)

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize("revoke_identity", [False, True])
def test_revocation_cannot_reuse_private_messages(tmp_path: Path, revoke_identity: bool) -> None:
    erstellt: list[Agent] = []

    def factory(*args: Any, **kwargs: Any) -> Agent:
        agent = Agent(*args, **kwargs)
        erstellt.append(agent)
        return agent

    geber = bridge.AgentAnswerer(lambda: Settings(data_dir=tmp_path), agent_factory=factory)
    config = bridge.normalize_config({"dienste": {"mail": "lesen"}})
    vertrauen = bridge.Decision(True, trusted=True)
    geber("Privater Mailinhalt", vertrauen, config, "chat", "signal")
    if revoke_identity:
        vertrauen = bridge.Decision(True)
    else:
        config = bridge.normalize_config({"dienste": {"mail": "aus"}})
    geber("Wiederhole die Mail", vertrauen, config, "chat", "signal")
    assert len(erstellt) == 2
    assert erstellt[0].closed
    assert all(m["content"] != "Privater Mailinhalt" for m in erstellt[1].messages)
    geber.close()
    assert erstellt[1].closed


@pytest.mark.parametrize("field,new", [
    ("ha_control", False), ("ha_direct", False), ("google_write", False),
    ("google_direct", False), ("legal_guard", True), ("answer_check", True),
    ("ha_token", "new-token"),
])
def test_app_revocation_refreshes_the_agent(
    tmp_path: Path, field: str, new: Any,
) -> None:
    settings = Settings(data_dir=tmp_path, ha_control=True, ha_direct=True,
                        google_write=True, google_direct=True, legal_guard=False,
                        answer_check=False, ha_token="old-token")
    geber = bridge.AgentAnswerer(lambda: settings, agent_factory=Agent)
    config = bridge.normalize_config({"dienste": {"haus": "schalten"}})
    owner = bridge.Decision(True, trusted=True, selbst=True)
    geber("Private Daten", owner, config, "chat", "signal")
    alt = geber._agents["chat"][0]
    setattr(settings, field, new)
    geber("zweite Frage", owner, config, "chat", "signal")
    neu = geber._agents["chat"][0]
    assert neu is not alt and alt.closed
    assert all(m["content"] != "Private Daten" for m in neu.messages)
    geber.close()
