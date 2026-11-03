"""Dateipruefungen, geschuetzte Einstellungen und Router-Auswahl bleiben korrekt."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from aquaticy import lan, network_router, private_json, secure_pro, voice, web
from tests.test_v1401 import owner  # noqa: F401


def prepare_folder(directory, monkeypatch):
    folder = directory / "files"
    folder.mkdir()
    monkeypatch.setattr(secure_pro.shutil, "which", lambda name: "/bin/clamscan")
    secure_pro.configure(directory, "192.168.1.0/24", str(folder))
    monkeypatch.setattr(lan, "scan", lambda *a, **kw: [lan.Device("192.168.1.1", ports=[443])])
    monkeypatch.setattr(secure_pro.subprocess, "run", lambda *a, **kw: SimpleNamespace(
        returncode=0, stdout=""))
    return folder


def test_missing_clamav_is_reported_instead_of_silently_skipped(tmp_path, monkeypatch):
    prepare_folder(tmp_path, monkeypatch)
    monkeypatch.setattr(secure_pro.shutil, "which", lambda name: None)
    watcher = secure_pro.Watcher(tmp_path, lambda text: True)
    watcher.tick()
    assert any("ClamAV" in text and "fehlt" in text for text in watcher.last_findings)
    assert not any("keinen Fund" in text for text in watcher.positives)


def test_new_folder_invalidates_old_clean_result(owner, monkeypatch):  # noqa: F811
    session, settings = owner
    prepare_folder(settings.data_dir, monkeypatch)
    watcher = secure_pro.Watcher(settings.data_dir, lambda text: True)
    monkeypatch.setattr(web, "SECURE_WATCHER", watcher)
    watcher.tick()
    assert web.feature_view(session)["checked"] > 0
    other = settings.data_dir / "other"
    other.mkdir()
    secure_pro.configure(settings.data_dir, "192.168.1.0/24", str(other))
    state = web.feature_view(session)
    assert state["checked"] == 0 and state["positives"] == []


def test_folder_replaced_by_symlink_does_not_expand_scan_scope(tmp_path, monkeypatch):
    folder = prepare_folder(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    folder.rmdir()
    folder.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(secure_pro.subprocess, "run", lambda *a, **kw: pytest.fail("outside scope"))
    watcher = secure_pro.Watcher(tmp_path, lambda text: True)
    watcher.tick()
    assert any("Dateiordner" in text for text in watcher.last_findings)
    assert not any("keinen Fund" in text for text in watcher.positives)


def test_windows_router_uses_lowest_route_metric(monkeypatch):
    monkeypatch.setattr(network_router.platform, "system", lambda: "Windows")
    monkeypatch.setattr(lan, "in_container", lambda: False)
    monkeypatch.setattr(network_router.subprocess, "run", lambda *a, **kw: SimpleNamespace(
        returncode=0, stdout="0.0.0.0  0.0.0.0  192.168.2.1  192.168.2.5  100\n"
                            "0.0.0.0  0.0.0.0  192.168.3.1  192.168.3.5  10\n"))
    assert network_router.detect()["router"] == "192.168.3.1"


def test_voice_model_access_failure_does_not_break_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(voice.shutil, "which", lambda name: "/bin/tool")
    monkeypatch.setattr(voice.importlib.util, "find_spec", lambda name: object())

    def denied():
        raise PermissionError("model cache unavailable")

    model = SimpleNamespace(is_file=lambda: True, stat=denied)
    monkeypatch.setattr(Path, "rglob", lambda *a: iter([model]))
    assert voice.ready(tmp_path) is False


def test_failed_settings_replace_preserves_previous_private_file(tmp_path, monkeypatch):
    target = tmp_path / "voice.json"
    private_json.write(target, {"enabled": True})

    def interrupted(*args):
        assert json.loads(target.read_text()) == {"enabled": True}
        raise OSError("disk unavailable")

    monkeypatch.setattr(private_json.os, "replace", interrupted)
    with pytest.raises(OSError):
        private_json.write(target, {"enabled": False})
    assert json.loads(target.read_text()) == {"enabled": True}
    assert list(tmp_path.iterdir()) == [target]


def test_private_settings_do_not_follow_links_or_keep_public_permissions(tmp_path):
    target, outside = tmp_path / "voice.json", tmp_path / "outside.json"
    outside.write_text("private external data")
    target.symlink_to(outside)
    with pytest.raises(OSError):
        private_json.write(target, {"enabled": False})
    assert outside.read_text() == "private external data"
    target.unlink()
    target.write_text('{"enabled":true}')
    target.chmod(0o644)
    private_json.write(target, {"enabled": False})
    assert json.loads(target.read_text()) == {"enabled": False}
    if private_json.os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o600


def test_private_settings_keep_umlauts_in_folder_paths(tmp_path, monkeypatch):
    folder = tmp_path / "Übungen"
    folder.mkdir()
    monkeypatch.setattr(secure_pro.shutil, "which", lambda name: "/bin/clamscan")
    secure_pro.configure(tmp_path, "192.168.1.0/24", str(folder))
    assert secure_pro.read(tmp_path)["folder"] == str(folder.resolve())


def test_scan_errors_for_a_new_config_do_not_reuse_old_results(owner, monkeypatch):  # noqa: F811
    session, settings = owner
    prepare_folder(settings.data_dir, monkeypatch)
    watcher = secure_pro.Watcher(settings.data_dir, lambda text: True)
    monkeypatch.setattr(web, "SECURE_WATCHER", watcher)
    watcher.tick()
    assert web.feature_view(session)["checked"] > 0
    other = settings.data_dir / "other"
    other.mkdir()
    secure_pro.configure(settings.data_dir, "192.168.1.0/24", str(other))

    def failed(*args, **kwargs):
        raise OSError("scanner unavailable")

    monkeypatch.setattr(lan, "scan", failed)
    with pytest.raises(OSError):
        watcher.tick()
    assert web.feature_view(session)["checked"] == 0
    assert web.feature_view(session)["positives"] == []


def test_notification_failure_preserves_scan_and_retries_unacknowledged_findings(
    tmp_path, monkeypatch,
):
    secure_pro.configure(tmp_path, "192.168.1.0/24")
    monkeypatch.setattr(lan, "scan", lambda *a, **kw: [lan.Device("192.168.1.1", ports=[23])])

    def unavailable(text):
        raise OSError("messenger unavailable")

    watcher = secure_pro.Watcher(tmp_path, unavailable)
    assert watcher.tick()
    assert watcher.last_checked > 0 and not watcher.error
    assert watcher.announced == set()
    notices = []
    watcher.notify = lambda text: notices.append(text) or True
    watcher.tick()
    assert len(notices) == 1 and "Telnet" in notices[0]
    assert watcher.announced
