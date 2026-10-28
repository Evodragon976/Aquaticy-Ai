"""12.7.8 Luna: Die Größe der virtual machine bleibt gespeichert, und Normal hat 3 GB."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from aquaticy import sandbox, web
from aquaticy.auth import Account
from aquaticy.config import Settings


def ultra_session(tmp_path: Path, env: str = "", plan: str = "ultra") -> web.ChatSession:
    profile = tmp_path / f"konto-{plan}"
    profile.mkdir(exist_ok=True)
    (profile / ".env").write_text(env, encoding="utf-8")
    return web.ChatSession(Account("u1", "a@example.org", plan, 0), profile)


# -- Plus bleibt gespeichert -------------------------------------------------------------
def test_an_ultra_account_keeps_the_plus_size_after_saving(tmp_path: Path) -> None:
    session = ultra_session(tmp_path, "AQUATICY_VM_SIZE=plus\n")
    settings = session.settings()
    assert settings.vm_size == "plus"
    plus = sandbox.VM_SIZES["plus"]
    assert (settings.vm_cpus, settings.vm_memory_mb, settings.vm_disk_gb) == (
        plus["cpus"], plus["memory_mb"], plus["disk_gb"])


def test_the_whole_way_save_then_reopen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Wie im Browser: Plus wählen, speichern, Fenster zu, wieder auf."""
    session = ultra_session(tmp_path)
    monkeypatch.setattr(web, "SESSION", session)
    assert session.settings().vm_size == "normal"
    web.save_values({"AQUATICY_VM_SIZE": "plus"})
    reopened = web.ChatSession(session.account, session.profile)
    assert reopened.settings().vm_size == "plus"
    assert reopened.settings().vm_memory_mb == sandbox.VM_SIZES["plus"]["memory_mb"]
    monkeypatch.setattr(web, "SESSION", reopened)
    assert web.current_values()["AQUATICY_VM_SIZE"] == "plus", "so zeigt es die Seite"
    web.save_values({"AQUATICY_VM_SIZE": "normal"})
    back = web.ChatSession(session.account, session.profile).settings()
    assert back.vm_size == "normal" and back.vm_memory_mb == sandbox.MEMORY_MB


@pytest.mark.parametrize("plan", ["normal", "pro"])
def test_other_plans_stay_on_normal_whatever_the_file_says(tmp_path: Path, plan: str) -> None:
    session = ultra_session(tmp_path, "AQUATICY_VM_SIZE=plus\n", plan)
    settings = session.settings()
    normal = sandbox.VM_SIZES["normal"]
    assert settings.vm_size == "normal"
    assert (settings.vm_cpus, settings.vm_memory_mb, settings.vm_disk_gb) == (
        normal["cpus"], normal["memory_mb"], normal["disk_gb"])


def test_an_unknown_size_in_the_file_falls_back_to_normal(tmp_path: Path) -> None:
    settings = ultra_session(tmp_path, "AQUATICY_VM_SIZE=riesig\n").settings()
    assert settings.vm_size == "normal"
    assert settings.vm_memory_mb == sandbox.MEMORY_MB


def test_explicit_numbers_in_the_file_win_over_the_size(tmp_path: Path) -> None:
    env = "AQUATICY_VM_SIZE=plus\nAQUATICY_VM_MEMORY_MB=8192\nAQUATICY_VM_CPUS=6\n"
    settings = ultra_session(tmp_path, env).settings()
    assert (settings.vm_size, settings.vm_memory_mb, settings.vm_cpus) == ("plus", 8192, 6)


def test_a_file_without_a_size_keeps_what_the_server_says(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQUATICY_VM_SIZE", "plus")
    settings = ultra_session(tmp_path, "").settings()
    assert settings.vm_size == "plus"
    assert settings.vm_memory_mb == sandbox.VM_SIZES["plus"]["memory_mb"]


# -- Normal hat 3 GB ---------------------------------------------------------------------
def test_the_normal_vm_has_two_cores_and_three_gigabytes_everywhere() -> None:
    assert sandbox.CPUS == 2 and sandbox.VM_SIZES["normal"]["cpus"] == 2
    assert Settings().vm_cpus == 2 and sandbox.Sandbox().cpus == 2
    assert sandbox.VM_SIZES["plus"]["cpus"] > sandbox.VM_SIZES["normal"]["cpus"]
    assert sandbox.MEMORY_MB == 3072
    assert sandbox.VM_SIZES["normal"]["memory_mb"] == 3072
    assert Settings().vm_memory_mb == 3072
    assert sandbox.Sandbox().memory_mb == 3072
    assert sandbox.VM_SIZES["plus"]["memory_mb"] > sandbox.VM_SIZES["normal"]["memory_mb"]


def test_the_container_gets_the_three_gigabytes() -> None:
    box = sandbox.Sandbox()
    box.runtime = sandbox.Runtime("docker", "docker", [])
    box._name, box._volume = "aquaticy-test", "aquaticy-test-vol"
    flags = box._run_flags()
    assert flags[flags.index("--memory") + 1] == "3072m"
    assert flags[flags.index("--memory-swap") + 1] == "3072m"
    assert flags[flags.index("--cpus") + 1] == "2"


def test_the_tool_text_names_the_real_limits() -> None:
    from aquaticy import tools

    text = tools.VM_RUN_SCHEMA["function"]["description"]
    assert "3072 MB" in text and "2 Prozessorkerne" in text
    schemas = tools.vm_schemas_for(SimpleNamespace(data_dir=None))
    assert "3072 MB" in next(s for s in schemas if s["function"]["name"] == "vm_run")[
        "function"]["description"]


def test_the_settings_page_and_the_readme_say_three_gigabytes() -> None:
    html = (Path(web.__file__).parent / "webui.html").read_text(encoding="utf-8")
    assert "Normal — 2 Kerne, 3 GB Arbeitsspeicher, 4 GB Speicher" in html
    assert "Normal — 2 cores, 3 GB RAM, 4 GB storage" in html
    assert "Normal — 1 Kern" not in html
    readme = (Path(web.__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    assert "| Normal | 2 | 3 GB | 4 GB |" in readme


def test_the_default_in_config_is_the_default_of_the_sandbox() -> None:
    assert Settings().vm_memory_mb == sandbox.MEMORY_MB
    assert Settings().vm_cpus == sandbox.CPUS and Settings().vm_disk_gb == sandbox.DISK_GB


def test_every_saved_setting_is_read_back_for_accounts() -> None:
    """Das war der Fehler: ein Schlüssel, der gespeichert, aber nie wieder gelesen wurde."""
    read = (set(web._STRING_SETTINGS) | set(web._BOOL_SETTINGS) | set(web._INT_SETTINGS))
    special = {"AQUATICY_VM_SIZE", "AQUATICY_LEGAL_GUARD"}  # eigene Zweige in _profile_settings
    assert set(web.SETTING_KEYS) - read == special
    assert "_apply_vm_size(settings, raw, plan)" in (
        Path(web.__file__).read_text(encoding="utf-8"))
