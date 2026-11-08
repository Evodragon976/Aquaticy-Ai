"""15.5.7: Auch ein schlicht mit `aquaticy` gestarteter Server wird erkannt; Beenden ohne
Verwechslung (pidfd) und mit Protokoll. Pruefung eines Fremdberichts zu Prozess-Spoofing."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

import pytest

from aquaticy import old_server


@pytest.mark.parametrize(("befehl", "server"), [
    (["aquaticy"], False),
    (["/usr/bin/python3", "-m", "aquaticy.cli"], False),
    (["/usr/bin/python3", "-m", "aquaticy.cli", "web", "--lan"], True),
    (["/home/u/.local/bin/aquaticy", "web"], True),
    (["aquaticy", "stop"], False),
    (["aquaticy", "chat"], False),
    (["/usr/bin/python3", "-m", "aquaticy.cli", "chat"], False),
    (["vim", "aquaticy"], False),
    (["/usr/bin/python3", "aquaticy-fake.py"], False),
])
def test_servers_started_without_a_command_are_found(befehl: list[str], server: bool) -> None:
    assert old_server._ist_server(befehl) is server


def test_other_users_processes_are_never_touched(monkeypatch: pytest.MonkeyPatch) -> None:
    if not os.path.isdir("/proc"):
        pytest.skip("nur Linux")
    assert old_server.is_aquaticy(1) is False  # init/systemd: anderer Nutzer oder kein Aquaticy


def test_a_foreign_process_with_the_same_number_is_not_signalled(
        monkeypatch: pytest.MonkeyPatch) -> None:
    if not hasattr(os, "pidfd_open"):
        pytest.skip("pidfd fehlt")
    schlaefer = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert old_server.stop(schlaefer.pid, wait=0.5) is False  # kein Aquaticy-Server
        assert schlaefer.poll() is None
    finally:
        schlaefer.send_signal(signal.SIGKILL)
        schlaefer.wait()


def test_a_real_own_server_is_stopped_and_logged(monkeypatch: pytest.MonkeyPatch,
                                                 caplog: pytest.LogCaptureFixture) -> None:
    if not hasattr(os, "pidfd_open"):
        pytest.skip("pidfd fehlt")
    schlaefer = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    monkeypatch.setattr(old_server, "is_aquaticy", lambda pid: pid == schlaefer.pid)
    try:
        with caplog.at_level("WARNING"):
            assert old_server.stop(schlaefer.pid, wait=5)
        assert "[Sicherheit]" in caplog.text and str(schlaefer.pid) in caplog.text
    finally:
        if schlaefer.poll() is None:
            schlaefer.send_signal(signal.SIGKILL)
        schlaefer.wait()


def test_a_blocked_port_never_blocks_the_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fremdbericht "DoS durch Prozess-Spoofing": Aquaticy blockiert den Start nie."""
    from aquaticy import cli

    monkeypatch.setattr(old_server, "running_version", lambda port: "15.4.4")
    monkeypatch.setattr(old_server, "listener_pids", lambda port: [4242])
    monkeypatch.setattr(old_server, "is_aquaticy", lambda pid: True)
    monkeypatch.setattr(old_server, "stop", lambda pid: False)  # laesst sich nicht beenden
    start = time.monotonic()
    cli._altes_aquaticy(8765)  # kehrt zurueck, kein Abbruch, kein Warten
    assert time.monotonic() - start < 2
