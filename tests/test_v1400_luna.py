"""Lokale Sprache, Freigaben und defensive Secure-Pro-Meldungen."""

import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from aquaticy import bridge, lan, secure_pro, voice
from aquaticy.bridge_native import NativeResponder
from aquaticy.config import Settings
from aquaticy.messenger_native import Incoming, SignalTransport, Transport
from tests.test_v1289_terra import Transport as FakeTransport


@pytest.fixture
def speech(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "root", lambda: tmp_path)
    (tmp_path / "voice.json").write_text('{"enabled":true}')
    return tmp_path


@pytest.mark.parametrize("data", [b"", b"a" * (voice.MAX_BYTES + 1)])
def test_audio_limits_reject_before_running_any_decoder(speech, monkeypatch, data):
    monkeypatch.setattr(voice.subprocess, "run", lambda *a, **k: pytest.fail("decoder"))
    with pytest.raises(ValueError):
        voice.transcribe(data)


def test_transcriber_is_offline_bounded_and_deletes_its_input(speech, monkeypatch):
    inputs = []

    def run(args, **kwargs):
        source = Path(args[3])
        inputs.append(source)
        assert source.read_bytes() == b"audio"
        assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
        assert kwargs["timeout"] == 180
        return SimpleNamespace(stdout="Öffne meine Mails")

    monkeypatch.setattr(voice.subprocess, "run", run)
    assert voice.transcribe(b"audio") == "Öffne meine Mails"
    assert all(not path.exists() for path in inputs)


@pytest.mark.parametrize("trusted,enabled", [(False, True), (True, False)])
def test_voice_does_not_decode_without_permission(tmp_path, monkeypatch, trusted, enabled):
    settings = Settings(data_dir=tmp_path)
    bridge.set_config(settings, "signal", {"an": True, "wer": "einzeln",
                                           "nummern": ["+49123456789"] if trusted else []})
    monkeypatch.setattr(voice, "enabled", lambda: enabled)
    monkeypatch.setattr(voice, "transcribe", lambda data: pytest.fail("not authorized"))
    msg = Incoming("signal", "+49123456789", "[Sprachnachricht]", "id", time.time(),
                   sender="+49123456789", audio={"id": "audio"})
    responder = NativeResponder(lambda: settings, lambda *a: pytest.fail("model"))
    assert responder(msg, FakeTransport()) == "Sprachnachrichten nicht freigegeben"


def test_voice_uses_normal_agent_and_audio_reply(tmp_path, speech, monkeypatch):
    settings = Settings(data_dir=tmp_path)
    bridge.set_config(settings, "signal", {"an": True})
    monkeypatch.setattr(voice, "transcribe", lambda data: "Was sind die neuesten Nachrichten?")
    monkeypatch.setattr(voice, "synthesize", lambda text: b"reply-audio")
    seen = []

    def answer(text, *args):
        seen.append(text)
        return "Neuigkeiten mit Quellen"

    transport = FakeTransport()
    transport.voice_download = lambda msg: b"audio"
    sounds = []
    transport.voice_send = lambda chat, data: sounds.append(data)
    msg = Incoming("signal", "self", "[Sprachnachricht]", "id", time.time(),
                   self_chat=True, from_me=True, audio={"id": "audio"})
    assert NativeResponder(lambda: settings, answer)(msg, transport) == "beantwortet"
    assert seen == ["Was sind die neuesten Nachrichten?"]
    assert transport.sent == ["[Aquaticy] Neuigkeiten mit Quellen"]
    assert sounds == [b"reply-audio"]


def test_revoke_during_synthesis_prevents_text_and_audio(tmp_path, speech, monkeypatch):
    settings = Settings(data_dir=tmp_path)
    bridge.set_config(settings, "signal", {"an": True})

    def speak(text):
        bridge.set_config(settings, "signal", {"an": False})
        return b"private"

    monkeypatch.setattr(voice, "synthesize", speak)
    transport = FakeTransport()
    msg = Incoming("signal", "self", "Antworte als Sprachnachricht: Hallo", "id", time.time(),
                   self_chat=True, from_me=True)
    assert NativeResponder(lambda: settings, lambda *a: "privat")(msg, transport) == "widerrufen"
    assert transport.sent == []


def test_signal_own_voice_echo_without_caption_never_reaches_model(tmp_path, speech, monkeypatch):
    import hashlib

    settings = Settings(data_dir=tmp_path)
    bridge.set_config(settings, "signal", {"an": True})
    monkeypatch.setattr(voice, "transcribe", lambda data: pytest.fail("own audio echo"))
    transport = FakeTransport()
    transport.voice_download = lambda msg: b"own audio"
    transport._sent_audio = [hashlib.sha256(b"own audio").digest()]
    msg = Incoming("signal", "self", "[Sprachnachricht]", "id", time.time(),
                   self_chat=True, from_me=True, audio={"id": "valid"})
    assert NativeResponder(lambda: settings, lambda *args: pytest.fail("model"))(
        msg, transport) == "eigene"
    assert transport.sent == []


def test_own_audio_echo_is_never_delivered(tmp_path):
    delivered = []
    transport = Transport(tmp_path, delivered.append)
    transport._sent_audio.append(b"hash")
    transport._deliver(Incoming("whatsapp", "self", "audio", "id", time.time(),
                                from_me=True, audio_hash=b"hash"))
    assert delivered == []


@pytest.mark.parametrize("name", ["../secret", "/etc/passwd", "a/b", ".."])
def test_signal_attachment_paths_are_not_supplied_by_a_message(tmp_path, name):
    transport = SignalTransport(tmp_path, lambda m: None)
    with pytest.raises(ValueError):
        transport.voice_download(Incoming("signal", "self", "audio", "id", time.time(),
                                           audio={"id": name}))


def test_signal_attachment_symlink_cannot_escape(tmp_path):
    transport = SignalTransport(tmp_path / "messenger", lambda m: None)
    folder = transport.directory_for_session / "attachments"
    folder.mkdir(parents=True)
    secret = tmp_path / "private"
    secret.write_text("private")
    (folder / "valid-id").symlink_to(secret)
    with pytest.raises(ValueError):
        transport.voice_download(Incoming("signal", "self", "audio", "id", time.time(),
                                           audio={"id": "valid-id"}))


def test_signal_audio_event_keeps_sender_permissions():
    from aquaticy.messenger_native import parse_signal
    from tests.test_messenger_native import MY_NUMBER, sig_data

    msg = parse_signal(sig_data("", attachments=[{"contentType": "audio/ogg",
                                                  "size": 20, "id": "valid-id"}]), MY_NUMBER)
    assert msg is not None and msg.audio["id"] == "valid-id"
    assert not msg.self_chat and not msg.from_me
    oversized = sig_data("", attachments=[{"contentType": "audio/ogg",
                                           "size": voice.MAX_BYTES + 1}])
    assert parse_signal(oversized, MY_NUMBER) is None


def test_whatsapp_audio_event_from_real_protobuf():
    MessageEv = pytest.importorskip("neonize.events").MessageEv

    from aquaticy.messenger_native import parse_whatsapp

    event = MessageEv()
    event.Info.MessageSource.Chat.User = "49123456789"
    event.Info.MessageSource.Chat.Server = "s.whatsapp.net"
    event.Info.MessageSource.IsFromMe = True
    event.Message.audioMessage.fileLength = 20
    event.Message.audioMessage.fileSHA256 = b"x" * 32
    msg = parse_whatsapp(event, {"49123456789"})
    assert msg is not None and msg.self_chat and msg.audio_hash == b"x" * 32


def test_signal_audio_file_stays_until_rpc_has_accepted_it(tmp_path, monkeypatch):
    transport = SignalTransport(tmp_path, lambda m: None)
    paths = []

    def rpc(method, params, **kwargs):
        path = Path(params["attachments"][0])
        paths.append(path)
        assert path.read_bytes() == b"audio"
        assert kwargs["wait"] and params["noteToSelf"]
        assert params["message"].startswith("[Aquaticy]") and params["voiceNote"] is True

    monkeypatch.setattr(transport, "_rpc", rpc)
    transport.voice_send("self", b"audio")
    assert all(not path.exists() for path in paths)


@pytest.mark.parametrize("url", ["http://127.0.0.1/private", "file:///etc/passwd",
                                 "https://mmg.whatsapp.net.evil.example/file",
                                 "https://user@mmg.whatsapp.net/file"])
def test_whatsapp_media_cannot_be_used_to_fetch_arbitrary_urls(tmp_path, url):
    from aquaticy.messenger_native import WhatsAppTransport

    transport = WhatsAppTransport(tmp_path, lambda m: None)
    audio = SimpleNamespace(audioMessage=SimpleNamespace(seconds=10, URL=url, directPath=""))
    with pytest.raises(ValueError):
        transport.voice_download(Incoming("whatsapp", "self", "audio", "id", time.time(),
                                           audio=audio))


def test_revocation_during_secure_scan_discards_notice(tmp_path, monkeypatch):
    secure_pro.configure(tmp_path, "192.168.1.0/24")

    def scan(*args, **kwargs):
        (tmp_path / "secure-pro.json").unlink()
        return [lan.Device("192.168.1.2", ports=[23])]

    monkeypatch.setattr(lan, "scan", scan)
    messages = []
    secure_pro.Watcher(tmp_path, lambda text: messages.append(text) or True).tick()
    assert messages == []


@pytest.mark.parametrize("subnet", ["8.8.8.0/24", "192.168.0.0/16", "127.0.0.1/32"])
def test_secure_pro_cannot_enable_public_or_large_networks(tmp_path, subnet):
    with pytest.raises(ValueError):
        secure_pro.configure(tmp_path, subnet)
    assert not (tmp_path / "secure-pro.json").exists()


def test_secure_pro_is_off_by_default_and_does_not_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(lan, "scan", lambda *a, **kw: pytest.fail("not enabled"))
    watcher = secure_pro.Watcher(tmp_path, lambda text: True)
    watcher.start()
    assert watcher.thread is None
    assert watcher.tick() == []


def test_secure_pro_reports_changes_without_calling_them_malware(tmp_path, monkeypatch):
    secure_pro.configure(tmp_path, "192.168.1.0/24")
    devices = [lan.Device("192.168.1.2", ports=[23])]
    monkeypatch.setattr(lan, "scan", lambda *a, **kw: devices)
    messages = []
    watcher = secure_pro.Watcher(tmp_path, lambda text: messages.append(text) or True)
    watcher.tick()
    assert len(messages) == 1 and "Offen heißt nicht verwundbar" in messages[0]
    assert "Malwarefund" not in messages[0]
    watcher.tick()
    assert len(messages) == 1
    devices.append(lan.Device("192.168.1.3"))
    watcher.tick()
    assert "Neues Gerät: 192.168.1.3" in messages[-1]
    if os.name != "nt":
        assert (tmp_path / "secure-pro.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("status,word", [(0, ""), (1, "Malwarefund"), (2, "fehlgeschlagen")])
def test_clamav_findings_and_errors_are_distinct(tmp_path, monkeypatch, status, word):
    monkeypatch.setattr(secure_pro.shutil, "which", lambda name: "/bin/clamscan")
    secure_pro.configure(tmp_path, "192.168.1.0/24", str(tmp_path))
    monkeypatch.setattr(lan, "scan", lambda *a, **kw: [lan.Device("192.168.1.2", ports=[443])])
    commands = []

    def run(args, **kwargs):
        commands.append(args)
        assert kwargs["timeout"] == 120
        return SimpleNamespace(returncode=status, stdout="private.txt: Test-Signature FOUND")

    monkeypatch.setattr(secure_pro.subprocess, "run", run)
    messages = []
    secure_pro.Watcher(tmp_path, lambda text: messages.append(text) or True).tick()
    assert bool(messages) == bool(status)
    if status:
        assert word in messages[0] and "private.txt" not in messages[0]
    assert "--follow-file-symlinks=0" in commands[0]
    report = json.loads((tmp_path / "secure-pro-report.json").read_text())
    assert "Test-Signature" in report["findings"]
