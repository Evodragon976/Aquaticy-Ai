"""12.1.1 Sol: Installation, persistenter Parallelbetrieb und sichere Prozessgrenzen."""

from __future__ import annotations

import os
import plistlib
import subprocess
from types import SimpleNamespace

import httpx
import pytest
from typer.testing import CliRunner

from aquaticy import cli
from aquaticy import local_model as lm
from aquaticy import ollama_setup as setup


def test_setup_checks_ollama_before_asking_for_models(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cli, "_ensure_ollama", lambda **kw: calls.append(kw) or False)
    result = CliRunner().invoke(cli.app, ["setup", "--yes", "--env-file", str(tmp_path / ".env")])
    assert result.exit_code == 1
    assert calls == [{"assume_yes": True}]
    assert "LLM-Anbieter" not in result.output
    assert not (tmp_path / ".env").exists()


@pytest.mark.parametrize("local", [False, True])
def test_complete_setup_reuses_ollama_and_persists_it(monkeypatch, tmp_path, local):
    calls = []
    monkeypatch.setattr(cli, "_ensure_ollama", lambda **kw: calls.append("ollama") or True)
    monkeypatch.setattr(cli, "_ask_website", lambda **kw: {})
    monkeypatch.setattr(cli, "_vm_beim_start", lambda settings: None)

    def model(**kwargs):
        assert kwargs == {"assume_yes": True, "ollama_ready": True}
        calls.append("model")
        return "ollama_chat/qwen3:8b"

    monkeypatch.setattr(cli, "_run_local_setup", model)
    target = tmp_path / ".env"
    result = CliRunner().invoke(
        cli.app, ["setup", "--yes", "--no-probe", "--env-file", str(target)],
        input=("3\n" if local else "1\n") + "1\n\ny\n\n\n\n",
    )
    assert result.exit_code == 0, result.output
    assert calls == (["ollama", "model"] if local else ["ollama"])
    assert "OLLAMA_NUM_PARALLEL=2" in target.read_text()
    if local:
        assert "AQUATICY_API_BASE=http://localhost:11434" in target.read_text()


def test_cloud_only_setup_keeps_the_existing_installation_optional(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_ensure_ollama", lambda **kw: pytest.fail("Kein Ollama angefordert"))
    monkeypatch.setattr(cli, "_ask_website", lambda **kw: {})
    monkeypatch.setattr(cli, "_vm_beim_start", lambda settings: None)
    target = tmp_path / ".env"
    result = CliRunner().invoke(
        cli.app, ["setup", "--no-ollama", "--no-probe", "--env-file", str(target)],
        input="1\n1\n\ny\n\n\n\n",
    )
    assert result.exit_code == 0, result.output
    assert "OLLAMA_NUM_PARALLEL" not in target.read_text()


@pytest.mark.parametrize("installed", [True, False])
def test_ensure_installs_only_if_missing_then_configures(monkeypatch, installed):
    calls = []
    state = {"installed": installed}
    monkeypatch.setattr(lm, "ollama_binary", lambda: "/ollama" if state["installed"] else None)
    monkeypatch.setattr(lm, "install_command", lambda: ["installer", "ollama"])

    def install():
        calls.append("install")
        state["installed"] = True
        return True

    monkeypatch.setattr(lm, "install_ollama", install)
    monkeypatch.setattr(cli, "_configure_ollama_parallel", lambda **kw: calls.append("parallel")
                        or True)
    monkeypatch.setattr(lm, "start_server", lambda: calls.append("start") or True)
    assert cli._ensure_ollama(assume_yes=True)
    assert calls == (["parallel", "start"] if installed else ["install", "parallel", "start"])


def test_restart_requires_confirmation_and_denial_does_not_mutate(monkeypatch):
    monkeypatch.setattr(cli.typer, "confirm", lambda *a, **kw: False)
    monkeypatch.setattr(setup, "configure_parallel", lambda **kw: pytest.fail("Nicht bestaetigt"))
    assert cli._configure_ollama_parallel() is False


@pytest.mark.parametrize("failure", ["install", "config", "ready"])
def test_failures_abort_before_model_download(monkeypatch, failure):
    monkeypatch.setattr(lm, "ollama_binary", lambda: None if failure == "install" else "/ollama")
    monkeypatch.setattr(lm, "install_command", lambda: ["installer", "ollama"])
    monkeypatch.setattr(lm, "install_ollama", lambda: False)
    monkeypatch.setattr(lm, "server_running", lambda: False)
    monkeypatch.setattr(lm, "wait_for_server", lambda: False)

    def configure(**kwargs):
        if failure == "config":
            raise setup.SetupError("Konfiguration fehlgeschlagen")
        return True

    monkeypatch.setattr(setup, "configure_parallel", configure)
    monkeypatch.setattr(lm, "start_server", lambda: pytest.fail("Keinen zweiten Dienst starten"))
    monkeypatch.setattr(lm, "pull_model", lambda *a, **kw: pytest.fail("Kein Modell laden"))
    assert cli._run_local_setup("qwen3:8b", assume_yes=True) == ""


@pytest.mark.parametrize("user", [False, True])
@pytest.mark.parametrize("existing,expected", [("1", "2"), ("8", "8"), ("128", "128")])
def test_linux_persists_only_parallel_setting_and_restarts(monkeypatch, tmp_path, user,
                                                          existing, expected):
    monkeypatch.setattr(setup.platform, "system", lambda: "Linux")
    monkeypatch.setattr(setup.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(setup.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(setup.shutil, "which", lambda name: f"/usr/bin/{name}")
    calls = []
    content = []
    restarted = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs["timeout"] == 60 and kwargs["check"] is False
        assert "shell" not in kwargs
        if "LoadState" in command:
            loaded = ("--user" in command) == user
            return subprocess.CompletedProcess(command, 0, "loaded\n" if loaded else "not-found\n")
        if "Environment" in command:
            count = expected if restarted else existing
            env = f'OLLAMA_NUM_PARALLEL={count} OLLAMA_HOST=localhost'
            return subprocess.CompletedProcess(command, 0, env)
        if command[1:2] == ["install"] and "/dev/stdin" in command:
            content.append(kwargs["input"])
        if "restart" in command:
            restarted.append(True)
        return subprocess.CompletedProcess(command, 0, "")

    monkeypatch.setattr(setup.subprocess, "run", run)
    assert setup.configure_parallel(running=True) is True
    if user:
        assert calls[-2] == ["systemctl", "--user", "restart", "ollama.service"]
        target = tmp_path / ".config/systemd/user/ollama.service.d/90-aquaticy-parallel.conf"
        content.append(target.read_text())
        assert target.stat().st_mode & 0o777 == 0o600
    else:
        assert calls[-2] == ["sudo", "systemctl", "restart", "ollama.service"]
        assert any(str(setup.SERVICE_FILE) in call for call in calls)
    assert content == [f'[Service]\nEnvironment="OLLAMA_NUM_PARALLEL={expected}"\n']
    assert not any("stop" in call or "kill" in call for call in calls)


def test_service_failure_does_not_leak_its_environment(monkeypatch):
    monkeypatch.setattr(setup.subprocess, "run", lambda command, **kw:
                        subprocess.CompletedProcess(command, 1, "SECRET_VALUE", "SECRET_VALUE"))
    with pytest.raises(setup.SetupError) as error:
        setup._run(["systemctl", "show"], capture_output=True)
    assert "SECRET_VALUE" not in str(error.value)


def test_overriding_service_rule_cannot_be_reported_as_success(monkeypatch, tmp_path):
    monkeypatch.setattr(setup.Path, "home", lambda: tmp_path)

    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "OLLAMA_NUM_PARALLEL=1")

    monkeypatch.setattr(setup.subprocess, "run", run)
    with pytest.raises(setup.SetupError, match="überschreibt"):
        setup._linux(["systemctl", "--user"])


def test_installer_success_without_a_binary_still_fails(monkeypatch):
    monkeypatch.setattr(lm, "ollama_binary", lambda: None)
    monkeypatch.setattr(lm, "install_command", lambda: ["installer", "ollama"])
    monkeypatch.setattr(lm, "install_ollama", lambda: True)
    monkeypatch.setattr(setup, "configure_parallel", lambda **kw: pytest.fail("Ollama fehlt"))
    assert cli._ensure_ollama(assume_yes=True) is False


@pytest.mark.parametrize("user", [False, True])
def test_service_permission_failure_cannot_start_a_second_server(monkeypatch, tmp_path, user):
    monkeypatch.setattr(setup.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(setup.platform, "system", lambda: "Linux")
    command = ["systemctl", "--user"] if user else ["systemctl"]
    monkeypatch.setattr(setup, "_systemd", lambda: command)
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(lm, "server_running", lambda *a, **kw: True)

    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1 if "restart" in command else 0, "")

    monkeypatch.setattr(setup.subprocess, "run", run)
    monkeypatch.setattr(lm, "start_server", lambda: pytest.fail("Kein zweiter Dienst"))
    assert cli._configure_ollama_parallel(assume_yes=True) is False


@pytest.mark.parametrize("running", [False, True])
def test_unmanaged_running_process_is_never_killed(monkeypatch, running):
    monkeypatch.setattr(setup.platform, "system", lambda: "Linux")
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    monkeypatch.setattr(setup.subprocess, "run", lambda *a, **kw: pytest.fail("Kein Dienst"))
    if running:
        with pytest.raises(setup.SetupError, match="beenden"):
            setup.configure_parallel(running=True)
    else:
        assert setup.configure_parallel(running=False) is False


@pytest.mark.parametrize("active", [False, True])
def test_homebrew_launchagent_keeps_existing_options(monkeypatch, tmp_path, active):
    monkeypatch.setattr(setup.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(setup.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(setup.os, "getuid", lambda: 123)
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/opt/homebrew/bin/brew")
    target = tmp_path / "Library/LaunchAgents/homebrew.mxcl.ollama.plist"
    target.parent.mkdir(parents=True)
    original = {"Label": "homebrew.mxcl.ollama", "ProgramArguments": ["/opt/ollama", "serve"],
                "RunAtLoad": True, "EnvironmentVariables": {"OLLAMA_MODELS": "/my/models"}}
    target.write_bytes(plistlib.dumps(original))
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1 if "print" in command and not active else 0,
                                           "")

    monkeypatch.setattr(setup.subprocess, "run", run)
    assert setup.configure_parallel(running=active) is True
    data = plistlib.loads(target.read_bytes())
    assert data == dict(original, EnvironmentVariables={"OLLAMA_MODELS": "/my/models",
                                                       "OLLAMA_NUM_PARALLEL": "2"})
    assert calls[-1] == ["launchctl", "bootstrap", "gui/123", str(target)]
    assert any("bootout" in call for call in calls) == active


def test_native_macos_app_is_not_mistaken_for_homebrew(monkeypatch, tmp_path):
    monkeypatch.setattr(setup.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(setup.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(setup.subprocess, "run", lambda *a, **kw: pytest.fail("Keine App beenden"))
    with pytest.raises(setup.SetupError, match="beenden"):
        setup.configure_parallel(running=True)


def test_service_symlink_is_rejected_without_writing_through(monkeypatch, tmp_path):
    target = tmp_path / "real"
    target.write_text("private")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(setup.SetupError, match="symbolisch"):
        setup._write(link, b"overwritten")
    assert target.read_text() == "private"


@pytest.mark.parametrize("value", ["8", "128"])
def test_windows_fixed_script_receives_path_as_data(monkeypatch, value):
    monkeypatch.setattr(setup.platform, "system", lambda: "Windows")
    binary = 'C:\\Users\\someone;$(throw "oops")\\ollama.exe'
    monkeypatch.setattr(lm, "ollama_binary", lambda: binary)
    captured = []

    def run(command, **kwargs):
        captured.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, value + "\n")

    monkeypatch.setattr(setup.subprocess, "run", run)
    assert setup.configure_parallel(running=True) is False
    command, kwargs = captured[0]
    assert command[:4] == ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"]
    assert command[4] == setup._WINDOWS and binary not in command[4]
    assert kwargs["env"]["AQUATICY_OLLAMA_SETUP_BINARY"] == binary
    assert os.environ["OLLAMA_NUM_PARALLEL"] == value
    assert "GetOwnerSid" in command[4] and "$process.ExecutablePath" in command[4]


def test_windows_new_binary_found_without_restarting_terminal(monkeypatch, tmp_path):
    monkeypatch.setattr(lm.platform, "system", lambda: "Windows")
    monkeypatch.setattr(lm.shutil, "which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    target = tmp_path / "Programs/Ollama/ollama.exe"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"test")
    assert lm.ollama_binary() == str(target)


@pytest.mark.parametrize("value,expected", [("", "2"), ("1", "2"), ("8", "8"), ("128", "128"),
                                          ("99999999999999999999", "2"), ("2\n", "2")])
def test_owned_server_gets_parallel_environment_and_only_local_host(monkeypatch, value, expected):
    captured = []
    monkeypatch.setenv("OLLAMA_HOST", "0.0.0.0:7777")
    monkeypatch.setenv("OLLAMA_NUM_PARALLEL", value)
    monkeypatch.setattr(lm, "ollama_binary", lambda: "/usr/bin/ollama")
    running = iter((False, True))
    monkeypatch.setattr(lm, "server_running", lambda *a, **kw: next(running))
    monkeypatch.setattr(lm.subprocess, "Popen", lambda *a, **kw: captured.append((a, kw)))
    assert lm.start_server("http://127.0.0.1:12345", wait_seconds=1)
    environment = captured[0][1]["env"]
    assert environment["OLLAMA_HOST"] == "127.0.0.1:12345"
    assert environment["OLLAMA_NUM_PARALLEL"] == expected
    assert os.environ["OLLAMA_HOST"] == "0.0.0.0:7777"


@pytest.mark.parametrize("url", ["http://remote.example:11434", "http://0.0.0.0:11434",
                                 "http://user:pass@localhost:11434", "https://localhost:11434",
                                 "http://localhost:11434/path", "http://localhost:invalid"])
def test_server_start_never_creates_unrequested_listeners(monkeypatch, url):
    monkeypatch.setattr(lm.subprocess, "Popen", lambda *a, **kw: pytest.fail("Nicht lokal"))
    assert lm.start_server(url) is False


@pytest.mark.parametrize("payload", [{}, [], "Ollama", {"models": {}}])
def test_http_success_alone_is_not_an_ollama_server(monkeypatch, payload):
    monkeypatch.setattr(lm.httpx, "get", lambda *a, **kw: httpx.Response(200, json=payload))
    assert not lm.server_running()


def test_pull_uses_the_server_that_was_set_up(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "https://different.example")
    captured = []
    monkeypatch.setattr(lm, "ollama_binary", lambda: "/ollama")
    monkeypatch.setattr(lm.subprocess, "Popen", lambda *a, **kw:
                        captured.append(kw) or SimpleNamespace(stdout=iter([]), wait=lambda: 0))
    assert list(lm.pull_model("qwen3:8b")) == []
    assert captured[0]["env"]["OLLAMA_HOST"] == lm.DEFAULT_OLLAMA_URL


@pytest.mark.parametrize("name", ["--help", "--insecure", "qwen3:8b\n", ""])
def test_model_names_cannot_inject_command_options(monkeypatch, name):
    monkeypatch.setattr(lm, "ollama_binary", lambda: "/ollama")
    monkeypatch.setattr(lm.subprocess, "Popen", lambda *a, **kw: pytest.fail("Ungueltiger Name"))
    with pytest.raises(lm.LocalModelError, match="Modellname"):
        list(lm.pull_model(name))


def test_linux_failed_download_is_never_executed(monkeypatch, tmp_path):
    monkeypatch.setattr(lm.platform, "system", lambda: "Linux")
    command = lm.install_command()
    curl = tmp_path / "curl"
    marker = tmp_path / "executed"

    curl.write_text('#!/bin/sh\nfor last do :; done\n'
                    f'echo "touch {marker}" > "$last"\nexit 22\n')
    curl.chmod(0o700)
    environment = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"])
    result = subprocess.run(command, env=environment, check=False, timeout=10)
    assert result.returncode != 0
    assert not marker.exists()


@pytest.mark.parametrize("error", [FileNotFoundError(), subprocess.TimeoutExpired("install", 1)])
def test_missing_installer_or_timeout_is_a_controlled_failure(monkeypatch, error):
    def run(*args, **kwargs):
        raise error

    monkeypatch.setattr(lm.subprocess, "run", run)
    assert lm._default_runner(["installer"]) == 1
