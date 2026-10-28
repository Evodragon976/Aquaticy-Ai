"""12.6.8 Astra: Firefox stürzt in der virtual machine nicht mehr ab."""

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from aquaticy import sandbox, web
from tests.test_v1266_sol import login as login
from tests.test_v1267_astra import FrontBox

WEB = Path(web.__file__).parent


def flags_of(box: sandbox.Sandbox) -> list[str]:
    box.runtime = sandbox.Runtime("docker", "docker", [])
    box._name = "aquaticy-test"
    box._volume = "aquaticy-test-vol"
    return box._run_flags()


def pair(flags: list[str], name: str) -> str:
    return flags[flags.index(name) + 1]


def test_the_desktop_gets_enough_memory_and_cores_for_firefox() -> None:
    desktop = sandbox.Sandbox(user_mode=True)
    assert desktop.memory_mb == sandbox.DESKTOP_MIN_MEMORY_MB >= 2048
    assert desktop.cpus == sandbox.DESKTOP_MIN_CPUS >= 2
    flags = flags_of(desktop)
    assert pair(flags, "--memory") == pair(flags, "--memory-swap") == f"{desktop.memory_mb}m"
    assert pair(flags, "--cpus") == str(desktop.cpus)


def test_larger_choices_stay_and_the_plain_vm_is_unchanged() -> None:
    big = sandbox.Sandbox(user_mode=True, memory_mb=6144, cpus=4)
    assert (big.memory_mb, big.cpus) == (6144, 4)
    plain = sandbox.Sandbox()
    assert (plain.memory_mb, plain.cpus) == (sandbox.MEMORY_MB, sandbox.CPUS)
    internet = sandbox.Sandbox(internet=True, headless=True)
    assert internet.memory_mb == sandbox.MEMORY_MB


def test_the_shared_memory_fits_inside_the_memory_limit() -> None:
    flags = flags_of(sandbox.Sandbox(user_mode=True))
    shm = pair(flags, "--shm-size")
    assert shm == sandbox.DESKTOP_SHM and int(shm.rstrip("m")) >= 512
    assert int(shm.rstrip("m")) < sandbox.DESKTOP_MIN_MEMORY_MB


def test_firefox_sends_no_crash_report_to_mozilla() -> None:
    flags = flags_of(sandbox.Sandbox(user_mode=True))
    assert "MOZ_CRASHREPORTER_DISABLE=1" in flags
    assert "MOZ_CRASHREPORTER_NO_REPORT=1" in flags
    assert not any("MOZ_CRASHREPORTER" in f for f in flags_of(sandbox.Sandbox()))


def test_the_hardening_of_the_desktop_is_untouched() -> None:
    flags = flags_of(sandbox.Sandbox(user_mode=True))
    assert pair(flags, "--cap-drop") == "ALL" and "--read-only" in flags
    assert pair(flags, "--security-opt") == "no-new-privileges"
    assert pair(flags, "--user") == sandbox.RUN_AS
    assert pair(flags, "--pids-limit") == str(sandbox.DESKTOP_PID_LIMIT)
    assert not any(f.startswith("MOZ_DISABLE") for f in flags), "kein Sandkasten wird abgeschaltet"
    assert "--privileged" not in flags and "seccomp=unconfined" not in " ".join(flags)


@pytest.mark.parametrize(("title", "crashed"), [
    ("Absturzmelder für Tabs — Mozilla Firefox", True),
    ("Gah. Your tab just crashed. — Mozilla Firefox", True),
    ("Tab Crashed", True),
    ("WhatsApp Web — Mozilla Firefox", False),
    ("(2) WhatsApp", False),
    ("Signal", False),
    ("", False),
])
def test_the_crash_page_is_recognised(title: str, crashed: bool) -> None:
    assert web.browser_crashed({"titel": title}, {}) is crashed


class CrashBox(FrontBox):
    """Ein Fenster, das erst die Absturzseite zeigt und nach einem Neustart den Code."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.crashed = True

    @property
    def window_title(self) -> str:  # type: ignore[override]
        return "Absturzmelder für Tabs — Mozilla Firefox" if self.crashed else "Signal Messenger"

    def desktop(self, *args: str, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if args[0] in {"focus", "key", "open"}:
            self.calls.append(args)
            if args[0] == "open":
                self.crashed = False
            return subprocess.CompletedProcess(args, 0, b"{}", b"")
        data = {"fenster": [{"id": "0x123", "klasse": self.klass, "titel": self.window_title}],
                "aktiv": self.window_title, "aktiv_klasse": self.klass}
        return subprocess.CompletedProcess(args, 0, json.dumps(data).encode(), b"")


@pytest.fixture
def crash(login, monkeypatch):
    session, _, payload = login
    box = CrashBox()
    monkeypatch.setattr(sandbox, "shared", lambda settings: box)
    monkeypatch.setattr(web.time, "sleep", lambda seconds: None)
    return session, box, payload


def test_a_crashed_browser_is_restarted_once_and_then_the_code_comes(crash) -> None:
    session, box, payload = crash
    result = web.addon_qr(session, payload)[0]
    assert result == {"ok": True, "image": None, "reason": "neustart"}
    assert box.calls == [("focus", "0x123"), ("key", "ctrl+q"), ("open", "signal")]
    result = web.addon_qr(session, payload)[0]
    assert result["image"] and "reason" not in result
    assert [c[0] for c in box.calls].count("key") == 1, "kein weiterer Neustart"
    assert [c[0] for c in box.calls].count("open") == 1


def test_a_browser_that_keeps_crashing_is_not_restarted_forever(crash) -> None:
    session, box, payload = crash
    web.addon_qr(session, payload)
    box.crashed = True
    result = web.addon_qr(session, payload)[0]
    assert result == {"ok": True, "image": None, "reason": "abgestuerzt"}
    web.addon_qr(session, payload)
    assert sum(1 for c in box.calls if c[0] == "open") == web.MAX_BROWSER_RESTARTS == 1


def test_a_new_login_gets_a_new_restart(crash) -> None:
    session, box, payload = crash
    web.addon_qr(session, payload)
    result, status = web.addon_action({"action": "login", "id": "signal"})
    assert status == 200
    box.crashed = True
    fresh = {"id": "signal", "token": result["qr_token"]}
    assert web.addon_qr(session, fresh)[0]["reason"] == "neustart"


def test_the_restart_counter_does_not_grow_without_end(crash) -> None:
    session, _, payload = crash
    web.addon_qr(session, payload)
    owner = session._owner
    assert len(owner._qr_restarts) == 1
    web.addon_action({"action": "login", "id": "signal"})
    assert owner._qr_restarts == {}


def test_the_dialog_knows_both_crash_reasons_in_both_languages() -> None:
    html = (WEB / "webui.html").read_text(encoding="utf-8")
    start = html.index("const QR_GRUENDE = {")
    block = html[start:html.index("};", start)]
    texts = dict(re.findall(r'(\w+): "([^"]+)"', block))
    assert {"neustart", "abgestuerzt"} <= set(texts)
    english = json.loads(re.search(r"const EN = (\{.*?\n\});", html, re.S).group(1))
    assert texts["neustart"] in english and texts["abgestuerzt"] in english
    assert 'data.reason === "abgestuerzt"' in html, "der Ausweg kommt sofort"


def test_the_quit_key_never_goes_to_another_program(crash) -> None:
    """Strg+Q ginge sonst an das vordere Fenster -- etwa ein Dokument mit ungespeicherter Arbeit."""
    session, box, payload = crash
    original = box.desktop

    def other_in_front(*args: str, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if args[0] == "windows":
            data = {"fenster": [{"id": "0x123", "klasse": box.klass, "titel": box.window_title}],
                    "aktiv": "Dokument 1 - LibreOffice Writer",
                    "aktiv_klasse": "libreoffice.Soffice"}
            return subprocess.CompletedProcess(args, 0, json.dumps(data).encode(), b"")
        return original(*args, **kwargs)

    box.desktop = other_in_front
    result = web.addon_qr(session, payload)[0]
    assert result["reason"] == "nicht_vorn"
    assert not any(c[0] == "key" for c in box.calls)
    assert session._owner._qr_restarts == {}, "ein abgelehnter Versuch zaehlt nicht"
