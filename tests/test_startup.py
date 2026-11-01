"""Abgekoppelter Prozess und kontrollierte Updates ohne echte Installation."""

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aquaticy import VERSION_LABEL, startup


class Console:
    def __init__(self):
        self.lines = []

    def print(self, text, **kwargs):
        self.lines.append(text)


def test_background_survives_terminal_interrupt(tmp_path, monkeypatch):
    calls = []

    def interrupt():
        raise KeyboardInterrupt

    def spawn(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(pid=1234, wait=interrupt)

    monkeypatch.setattr(startup.subprocess, "Popen", spawn)
    console = Console()
    startup.background(["web", "--foreground"], tmp_path, console)
    args, options = calls[0]
    assert args[-1] == "--foreground"
    assert options["stdin"] == subprocess.DEVNULL
    assert options["env"]["AQUATICY_STARTUP_CHILD"] == "1"
    if os.name != "nt":
        assert options["start_new_session"] is True
        assert (tmp_path / "background.log").stat().st_mode & 0o777 == 0o600
    assert any("läuft weiter" in line for line in console.lines)


def test_background_reports_start_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(startup.subprocess, "Popen", lambda *a, **k:
                        SimpleNamespace(pid=1234, wait=lambda: 2))
    with pytest.raises(RuntimeError, match="Code 2"):
        startup.background(["web", "--foreground"], tmp_path, Console())


def test_background_does_not_follow_log_symlinks(tmp_path):
    if os.name == "nt":
        pytest.skip("O_NOFOLLOW ist eine POSIX-Grenze")
    target = tmp_path / "private"
    target.write_text("private")
    (tmp_path / "background.log").symlink_to(target)
    with pytest.raises(OSError):
        startup.background(["web"], tmp_path, Console())
    assert target.read_text() == "private"


@pytest.mark.parametrize("remote", [VERSION_LABEL, "99.0.0 Luna", "1.0.0 Old"])
def test_update_checks_fixed_branch_and_installs_only_new_release(tmp_path, monkeypatch, remote):
    monkeypatch.delenv("AQUATICY_STARTUP_CHILD", raising=False)
    monkeypatch.setattr(startup, "__file__", str(tmp_path / "pkg/startup.py"))
    monkeypatch.setattr(startup.shutil, "which", lambda name: "/bin/" + name)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if "clone" in args:
            root = Path(args[-1])
            (root / "aquaticy").mkdir(parents=True)
            version, name = remote.split()
            (root / "aquaticy/__init__.py").write_text(
                f'__version__ = "{version}"\n__codename__ = "{name}"\n')
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(startup.subprocess, "run", run)
    assert startup.update_at_start(Console()) == (remote == "99.0.0 Luna")
    assert startup.REPOSITORY in calls[0] and startup.BRANCH in calls[0]
    installs = [c for c in calls if "install" in c]
    assert bool(installs) == (remote == "99.0.0 Luna")
    if installs:
        assert "-c" in installs[0] and "--python" in installs[0]


def test_dirty_checkout_is_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.delenv("AQUATICY_STARTUP_CHILD", raising=False)
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(startup, "__file__", str(tmp_path / "aquaticy/startup.py"))
    monkeypatch.setattr(startup.shutil, "which", lambda name: "/bin/git")
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=" M aquaticy/agent.py\n")

    monkeypatch.setattr(startup.subprocess, "run", run)
    assert not startup.update_at_start(Console())
    assert len(calls) == 1 and "status" in calls[0]


def test_detached_child_does_not_update_again(monkeypatch):
    monkeypatch.setenv("AQUATICY_STARTUP_CHILD", "1")
    monkeypatch.setattr(startup.shutil, "which", lambda name: pytest.fail("recursive update"))
    assert not startup.update_at_start(Console())


def test_cli_background_passes_options_without_token_in_arguments(monkeypatch):
    from typer.testing import CliRunner

    from aquaticy import cli

    calls = []

    def launch(arguments, directory, console):
        calls.append((arguments, os.environ.get("AQUATICY_BACKGROUND_TOKEN")))

    monkeypatch.setattr(startup, "background", launch)
    result = CliRunner().invoke(cli.app, ["web", "--background", "--no-open",
                                          "--token", "private-token"])
    assert result.exit_code == 0, result.output
    assert "--foreground" in calls[0][0] and "--no-open" in calls[0][0]
    assert "private-token" not in calls[0][0]
    assert calls[0][1] == "private-token"
    assert "AQUATICY_BACKGROUND_TOKEN" not in os.environ


def test_foreground_overrides_saved_background_choice(monkeypatch):
    from typer.testing import CliRunner

    from aquaticy import cli

    monkeypatch.setenv("AQUATICY_BACKGROUND", "true")
    monkeypatch.setattr(startup, "background", lambda *args: pytest.fail("detached"))
    calls = []
    monkeypatch.setattr("aquaticy.web.serve", lambda **kwargs: calls.append(kwargs))
    result = CliRunner().invoke(cli.app, ["web", "--foreground", "--no-open"])
    assert result.exit_code == 0, result.output
    assert len(calls) == 1


def test_failed_update_still_starts_app(monkeypatch):
    from aquaticy import cli

    monkeypatch.delenv("AQUATICY_UPDATED", raising=False)
    monkeypatch.setattr(cli.sys, "argv", ["aquaticy", "web"])

    def fail(console):
        raise subprocess.TimeoutExpired("git", 90)

    monkeypatch.setattr(startup, "update_at_start", fail)
    calls = []
    monkeypatch.setattr(cli, "app", lambda: calls.append(True))
    cli.main()
    assert calls == [True]


@pytest.mark.parametrize("saved", [False, True])
def test_background_defaults_to_lan_and_shows_both_addresses(monkeypatch, saved):
    from typer.testing import CliRunner

    from aquaticy import cli

    monkeypatch.setattr("aquaticy.web.lan_address", lambda: "192.168.1.44")
    monkeypatch.setattr("aquaticy.web.tailscale_address", lambda: "100.81.120.100")
    monkeypatch.setenv("AQUATICY_BACKGROUND", "true" if saved else "false")
    calls = []
    monkeypatch.setattr(startup, "background", lambda args, *rest: calls.append(args))
    args = ["web", "--no-open"] + ([] if saved else ["--background"])
    result = CliRunner().invoke(cli.app, args)
    assert result.exit_code == 0, result.output
    assert calls[0][calls[0].index("--host") + 1] == "0.0.0.0"
    assert "--lan" in calls[0] and "--foreground" in calls[0]
    assert "http://192.168.1.44:8765/" in result.output
    assert "http://100.81.120.100:8765/" in result.output


def test_background_keeps_explicit_loopback_binding(monkeypatch):
    from typer.testing import CliRunner

    from aquaticy import cli

    calls = []
    monkeypatch.setattr(startup, "background", lambda args, *rest: calls.append(args))
    result = CliRunner().invoke(cli.app, ["web", "--background", "--host", "127.0.0.1",
                                          "--no-open"])
    assert result.exit_code == 0, result.output
    assert calls[0][calls[0].index("--host") + 1] == "127.0.0.1"
    assert "--lan" not in calls[0]
