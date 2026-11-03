"""OpenSSH bleibt in der VM und braucht Netzfreigabe, Hostschluessel und Zustimmung."""

import base64
import json
import shlex
import struct
import subprocess
from types import SimpleNamespace

import pytest

from aquaticy import sandbox, vm_ssh
from aquaticy.agent import Agent
from aquaticy.coworker import FORBIDDEN
from aquaticy.guardrails import BASELINE_VM_TOOLS, SENSITIVE_TOOLS, Verdict
from aquaticy.injection import OUTBOUND
from aquaticy.tools import UNTRUSTED_SOURCES, Toolbox, vm_schemas_for

ALGORITHM = b"ssh-ed25519"
SERVER_KEY = "ssh-ed25519 " + base64.b64encode(
    struct.pack(">I", len(ALGORITHM)) + ALGORITHM + struct.pack(">I", 32) + b"k" * 32
).decode()


class Box:
    lan = True
    netz_offen = True
    name = "test-vm"
    alive = True

    def __init__(self):
        self.calls = []

    def ensure(self):
        return self.name

    def run(self, command, timeout):
        self.calls.append((command, timeout))
        return sandbox.RunResult(0, SERVER_KEY + "\n", "", .1)


@pytest.fixture
def ssh_box(settings):
    settings.vm_lan = True
    settings.lan_enabled = True
    toolbox = Toolbox(settings)
    box = Box()
    toolbox._sandbox_box = box
    toolbox.ssh_allowed = lambda: True
    try:
        yield toolbox, box
    finally:
        toolbox._sandbox_box = None
        toolbox.close()


def run_args():
    return {"action": "run", "host": "192.168.1.2", "user": "pi",
            "command": "uname -a", "server_key": SERVER_KEY}


@pytest.mark.parametrize("target", ["8.8.8.8", "127.0.0.1", "169.254.169.254", "::1",
                                    "example.org", "192.168.1.2;id", "-oProxyCommand=id"])
def test_ssh_refuses_public_loopback_metadata_and_shell_targets(target):
    with pytest.raises(ValueError):
        vm_ssh.prepare("inspect", host=target)


@pytest.mark.parametrize("changes", [
    {"port": 0}, {"port": 65536}, {"port": True}, {"port": 22.5},
    {"timeout": 121}, {"timeout": "oops"}, {"user": "-oProxyCommand=id"},
    {"key_file": "/home/host/.ssh/id_rsa"}, {"key_file": "/work/../../id_rsa"},
    {"command": "printf harmless\x1b[0m"}, {"server_key": "ssh-ed25519 junk"},
])
def test_ssh_refuses_unsafe_arguments(changes):
    with pytest.raises((ValueError, TypeError)):
        vm_ssh.prepare(**(run_args() | changes))


def test_shell_quoting_does_not_interpret_remote_command_on_host_or_vm_shell():
    command = "printf '%s' 'quoted'; echo $(whoami)"
    data = vm_ssh.prepare(**(run_args() | {"command": command}))
    args = shlex.split(vm_ssh.vm_command(data))
    assert args[:3] == ["python3", "-c", vm_ssh.HELPER]
    assert json.loads(args[3])["command"] == command
    compile(vm_ssh.HELPER, "vm-ssh-helper", "exec")


def test_host_key_fingerprint_and_untrusted_keyscan_parsing():
    key, fingerprint = vm_ssh.host_key(SERVER_KEY)
    assert key == SERVER_KEY and fingerprint.startswith("SHA256:")
    keys = vm_ssh.inspected_keys(f"# banner\n192.168.1.2 {SERVER_KEY}\n"
                                f"192.168.1.2 {SERVER_KEY}\nbad line\n")
    assert keys == [{"host_key": key, "fingerprint": fingerprint}]


@pytest.mark.parametrize("gate", ["vm_off", "lan_off", "vm_lan_off", "actual_vm_lan_off"])
def test_no_ssh_without_all_current_permissions(ssh_box, gate):
    toolbox, box = ssh_box
    if gate == "vm_off":
        toolbox.ssh_allowed = None
    elif gate == "lan_off":
        toolbox.settings.lan_enabled = False
    elif gate == "vm_lan_off":
        toolbox.settings.vm_lan = False
    else:
        box.lan = False
    assert "error" in toolbox.lan_ssh(action="key")
    assert box.calls == []


@pytest.mark.parametrize("answer", [None, "nein", "", "maybe"])
def test_remote_commands_require_personal_confirmation_even_with_direct_rules(ssh_box, answer):
    toolbox, box = ssh_box
    toolbox.settings.google_direct = True
    toolbox.settings.google_write = True
    toolbox.coworker_write_ok = lambda tool: True
    toolbox.ask_handler = (lambda *a: answer) if answer is not None else None
    assert "error" in toolbox.lan_ssh(**run_args())
    assert box.calls == []


def test_remote_command_shows_full_command_and_fingerprint_then_runs_only_in_vm(ssh_box):
    toolbox, box = ssh_box
    prompts = []
    toolbox.ask_handler = lambda question, options: prompts.append(question) or "ja"
    result = toolbox.lan_ssh(**run_args())
    assert result["exit_code"] == 0 and len(box.calls) == 1
    assert "uname -a" in prompts[0] and "SHA256:" in prompts[0]
    assert "pi@192.168.1.2:22" in prompts[0]


def test_revoking_vm_during_confirmation_cancels_ssh(ssh_box):
    toolbox, box = ssh_box

    def revoke(*args):
        box.name = ""
        box.alive = False
        return "ja"

    toolbox.ask_handler = revoke
    assert "error" in toolbox.lan_ssh(**run_args())
    assert box.calls == []


def test_agent_offers_ssh_only_with_enabled_code_vm(settings, monkeypatch):
    settings.vm_lan = True
    settings.lan_enabled = True
    agent = Agent(settings)
    monkeypatch.setattr(agent, "_vm_can_start", lambda: True)
    monkeypatch.setattr(agent, "_model_can_use_tools", lambda *a: True)
    try:
        assert "lan_ssh" not in {s["function"]["name"] for s in agent.tools}
        agent.mode, agent.sandbox = "code", True
        assert "lan_ssh" in {s["function"]["name"] for s in agent.tools}
        assert agent.toolbox.ssh_allowed()
        agent.sandbox = False
        assert not agent.toolbox.ssh_allowed()
    finally:
        agent.close()


def test_ssh_keeps_abuse_privacy_and_coworker_gates(settings):
    assert "lan_ssh" in SENSITIVE_TOOLS and "lan_ssh" in BASELINE_VM_TOOLS
    assert OUTBOUND["lan_ssh"]["command"] == "code"
    assert "lan_ssh" in UNTRUSTED_SOURCES and "lan_ssh" in FORBIDDEN
    settings.vm_lan = False
    assert "lan_ssh" not in {s["function"]["name"] for s in vm_schemas_for(settings)}


def test_ssh_command_stopped_by_abuse_guard_never_reaches_vm(ssh_box):
    toolbox, box = ssh_box
    toolbox.guard = SimpleNamespace(check_call=lambda *a: Verdict(
        abuse=True, abuse_kind="angriff", abuse_severity=3, allowed=False))
    toolbox.ask_handler = lambda *a: "ja"
    result = toolbox.call("lan_ssh", run_args())
    assert result["skipped_reason"] == "aiguard_stop"
    assert box.calls == []


def test_standard_ssh_image_is_updated_once_without_host_ssh(monkeypatch):
    installed = False
    builds = []

    def inspect(binary, *args, **kwargs):
        assert args[:2] == ("image", "inspect")
        return subprocess.CompletedProcess([], 0, "1" if installed else "", "")

    def build(runtime):
        nonlocal installed
        builds.append(runtime)
        installed = True

    monkeypatch.setattr(sandbox, "_runs", inspect)
    monkeypatch.setattr(sandbox, "build_desktop_image", build)
    runtime = SimpleNamespace(binary="podman")
    sandbox.ensure_ssh_image(runtime)
    sandbox.ensure_ssh_image(runtime)
    assert builds == [runtime]
