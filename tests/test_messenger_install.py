"""Die Einrichtung der Direktverbindung: libmagic, signal-cli und der Befehl dazu (Terra v2)."""

from __future__ import annotations

import hashlib
import io
import re
import tarfile
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from aquaticy import cli
from aquaticy import messenger_install as mi
from aquaticy import messenger_native as nat

ROOT = Path(__file__).resolve().parents[1]
TAG = "v0.13.12"
SKRIPT = b'#!/bin/sh\necho "signal-cli 0.13.12"\n'


@pytest.fixture(autouse=True)
def _ohne_eigene_dateien(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nichts liest den echten Datenordner oder einen echten Pfad zu signal-cli."""
    monkeypatch.setenv("AQUATICY_DATA_DIR", str(tmp_path / "daten"))
    monkeypatch.delenv(mi.SIGNAL_ENV, raising=False)
    monkeypatch.setattr(mi, "SYSTEM_SIGNAL_DIR", tmp_path / "kein-system-ordner")
    monkeypatch.setattr(mi.shutil, "which", lambda name: None)


def _tar(dateien: dict[str, bytes], *, ausfuehrbar: bool = True) -> bytes:
    roh = io.BytesIO()
    with tarfile.open(fileobj=roh, mode="w:gz") as tf:
        for name, inhalt in dateien.items():
            info = tarfile.TarInfo(name)
            info.size = len(inhalt)
            info.mode = 0o755 if ausfuehrbar else 0o644
            tf.addfile(info, io.BytesIO(inhalt))
    return roh.getvalue()


def _github(archive: dict[str, bytes], *, digest: str | None = "richtig",
            tag: str = TAG, status: int = 200) -> httpx.Client:
    """Ein GitHub, das genau diese Dateien kennt. Zaehlt die Abrufe in `.abrufe`."""
    abrufe: list[str] = []

    def antwort(request: httpx.Request) -> httpx.Response:
        abrufe.append(str(request.url))
        if request.url.host == "api.github.com":
            assert request.url.path == "/repos/AsamK/signal-cli/releases/latest"
            assets = []
            for name, inhalt in archive.items():
                eintrag: dict[str, Any] = {
                    "name": name, "size": len(inhalt),
                    "browser_download_url": f"https://github.com/AsamK/signal-cli/releases/"
                                            f"download/{tag}/{name}"}
                if digest == "richtig":
                    eintrag["digest"] = "sha256:" + hashlib.sha256(inhalt).hexdigest()
                elif digest:
                    eintrag["digest"] = digest
                assets.append(eintrag)
            return httpx.Response(status, json={"tag_name": tag, "assets": assets})
        name = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, content=archive[name])

    http = httpx.Client(transport=httpx.MockTransport(antwort), follow_redirects=False)
    http.abrufe = abrufe  # type: ignore[attr-defined]
    return http


def _auf(monkeypatch: pytest.MonkeyPatch, system: str, maschine: str) -> None:
    monkeypatch.setattr(mi.platform, "system", lambda: system)
    monkeypatch.setattr(mi, "_machine", lambda: maschine)


# -- signal-cli finden ---------------------------------------------------------------------------
def test_nothing_is_found_when_nothing_is_there(tmp_path: Path) -> None:
    assert mi.find_signal_cli(tmp_path / "daten") is None
    assert mi.status(tmp_path / "daten")["signal"] == nat.NEED_SIGNAL_CLI


def test_the_entered_path_wins_and_must_be_a_file(tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    eigenes = tmp_path / "eigen"
    eigenes.write_bytes(SKRIPT)
    managed = mi.managed_dir(tmp_path / "daten")
    managed.mkdir(parents=True)
    (managed / "signal-cli").write_bytes(SKRIPT)
    (managed / "signal-cli").chmod(0o755)
    monkeypatch.setenv(mi.SIGNAL_ENV, str(eigenes))
    assert mi.find_signal_cli(tmp_path / "daten") == eigenes
    monkeypatch.setenv(mi.SIGNAL_ENV, str(tmp_path / "gibt-es-nicht"))
    assert mi.find_signal_cli(tmp_path / "daten") is None, "ein falscher Pfad wird nicht ersetzt"


@pytest.mark.parametrize("unterpfad", [("signal-cli",), ("app", "bin", "signal-cli")])
def test_the_downloaded_program_is_found_in_both_layouts(tmp_path: Path,
                                                         unterpfad: tuple[str, ...]) -> None:
    ziel = mi.managed_dir(tmp_path / "daten").joinpath(*unterpfad)
    ziel.parent.mkdir(parents=True)
    ziel.write_bytes(SKRIPT)
    ziel.chmod(0o755)
    assert mi.find_signal_cli(tmp_path / "daten") == ziel


def test_a_program_that_cannot_run_is_not_found(tmp_path: Path) -> None:
    ziel = mi.managed_dir(tmp_path / "daten") / "signal-cli"
    ziel.parent.mkdir(parents=True)
    ziel.write_bytes(SKRIPT)
    ziel.chmod(0o644)
    assert mi.find_signal_cli(tmp_path / "daten") is None


def test_the_path_is_the_last_resort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mi.shutil, "which", lambda name: "/usr/bin/signal-cli")
    assert mi.find_signal_cli(tmp_path / "daten") == Path("/usr/bin/signal-cli")
    assert mi.status(tmp_path / "daten")["signal"] == ""


def test_the_transport_finds_the_downloaded_program_without_a_restart(
        tmp_path: Path) -> None:
    """SignalTransport fragt bei jedem Gebrauch neu: nach install-messenger geht es gleich."""
    transport = nat.SignalTransport(tmp_path / "konto", lambda m: None)
    assert transport.available() == (False, nat.NEED_SIGNAL_CLI)
    ziel = mi.managed_dir(tmp_path / "daten") / "signal-cli"
    ziel.parent.mkdir(parents=True)
    ziel.write_bytes(SKRIPT)
    ziel.chmod(0o755)
    assert transport.available() == (True, "")


# -- Welches Archiv? -----------------------------------------------------------------------------
def test_linux_x86_gets_the_native_build_without_java() -> None:
    assert mi.signal_asset_name(TAG, system="Linux", machine="x86_64", java=0) == (
        "signal-cli-0.13.12-Linux-native.tar.gz", "native")


@pytest.mark.parametrize(("system", "maschine"), [("linux", "aarch64"), ("darwin", "arm64"),
                                                  ("darwin", "x86_64")])
def test_other_systems_need_java_21(system: str, maschine: str) -> None:
    assert mi.signal_asset_name(TAG, system=system, machine=maschine, java=17) == ("", "")
    assert mi.signal_asset_name(TAG, system=system, machine=maschine, java=21) == (
        "signal-cli-0.13.12.tar.gz", "jvm")


def test_windows_and_odd_tags_get_nothing() -> None:
    assert mi.signal_asset_name(TAG, system="Windows", machine="x86_64", java=21) == ("", "")
    for tag in ("0.13.12", "v0.13", "v0.13.12/../x", "latest", ""):
        assert mi.signal_asset_name(tag, system="Linux", machine="x86_64", java=21) == ("", "")


@pytest.mark.parametrize(("ausgabe", "erwartet"), [
    ('openjdk version "21.0.2" 2024-01-16', 21),
    ('openjdk version "17.0.9" 2023-10-17', 17),
    ('java version "1.8.0_292"', 8),
    ("kein Java", 0),
])
def test_java_version_is_read_from_the_banner(ausgabe: str, erwartet: int,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mi.shutil, "which", lambda name: "/usr/bin/java")

    def run(*args: Any, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(stderr=ausgabe, stdout="", returncode=0)

    assert mi.java_major(run) == erwartet


def test_no_java_means_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    assert mi.java_major() == 0  # which liefert in diesen Tests nichts


# -- signal-cli laden ----------------------------------------------------------------------------
NATIVE = "signal-cli-0.13.12-Linux-native.tar.gz"


def test_the_native_build_is_downloaded_checked_and_started(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _auf(monkeypatch, "Linux", "x86_64")
    http = _github({NATIVE: _tar({"signal-cli": SKRIPT})})
    pfad = mi.install_signal_cli(tmp_path / "daten", http=http)
    assert pfad == mi.managed_dir(tmp_path / "daten") / "signal-cli"
    assert pfad.read_bytes() == SKRIPT and pfad.stat().st_mode & 0o111
    assert mi.find_signal_cli(tmp_path / "daten") == pfad
    assert not [p for p in (tmp_path / "daten").iterdir() if p.name.startswith(".neu")]
    assert all(url.startswith(("https://api.github.com/", "https://github.com/"))
               for url in http.abrufe)  # type: ignore[attr-defined]


def test_the_java_build_keeps_its_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _auf(monkeypatch, "Linux", "aarch64")
    archive = _tar({"signal-cli-0.13.12/bin/signal-cli": SKRIPT,
                    "signal-cli-0.13.12/lib/x.jar": b"jar"})
    http = _github({"signal-cli-0.13.12.tar.gz": archive})
    pfad = mi.install_signal_cli(tmp_path / "daten", http=http, java=21)
    assert pfad == mi.managed_dir(tmp_path / "daten") / "app" / "bin" / "signal-cli"
    assert (pfad.parent.parent / "lib" / "x.jar").read_bytes() == b"jar"


def test_a_new_download_replaces_the_old_one(tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    _auf(monkeypatch, "Linux", "x86_64")
    alt = mi.managed_dir(tmp_path / "daten")
    alt.mkdir(parents=True)
    (alt / "signal-cli").write_bytes(b"#!/bin/sh\necho alt\n")
    (alt / "signal-cli").chmod(0o755)
    (alt / "ueberbleibsel").write_text("weg")
    mi.install_signal_cli(tmp_path / "daten", http=_github({NATIVE: _tar({"signal-cli": SKRIPT})}))
    assert (alt / "signal-cli").read_bytes() == SKRIPT and not (alt / "ueberbleibsel").exists()


def _alt_bleibt(tmp_path: Path) -> Path:
    alt = mi.managed_dir(tmp_path / "daten")
    alt.mkdir(parents=True)
    (alt / "signal-cli").write_bytes(b"alt")
    return alt


def test_a_wrong_checksum_throws_the_file_away_and_keeps_the_old_program(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _auf(monkeypatch, "Linux", "x86_64")
    alt = _alt_bleibt(tmp_path)
    http = _github({NATIVE: _tar({"signal-cli": SKRIPT})}, digest="sha256:" + "0" * 64)
    with pytest.raises(mi.InstallError, match="Prüfsumme"):
        mi.install_signal_cli(tmp_path / "daten", http=http)
    assert (alt / "signal-cli").read_bytes() == b"alt"
    assert not [p for p in (tmp_path / "daten").iterdir() if p.name.startswith(".neu")]


def test_without_a_published_checksum_nothing_is_installed(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _auf(monkeypatch, "Linux", "x86_64")
    http = _github({NATIVE: _tar({"signal-cli": SKRIPT})}, digest=None)
    with pytest.raises(mi.InstallError, match="Prüfsumme"):
        mi.install_signal_cli(tmp_path / "daten", http=http)
    assert not mi.managed_dir(tmp_path / "daten").exists()


def test_a_program_that_does_not_start_is_not_installed(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _auf(monkeypatch, "Linux", "x86_64")
    kaputt = b"#!/bin/sh\nexit 3\n"
    http = _github({NATIVE: _tar({"signal-cli": kaputt})})
    with pytest.raises(mi.InstallError, match="startet auf diesem System nicht"):
        mi.install_signal_cli(tmp_path / "daten", http=http)
    assert not mi.managed_dir(tmp_path / "daten").exists()


def test_the_java_build_without_java_says_what_to_do(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _auf(monkeypatch, "Linux", "aarch64")
    http = _github({"signal-cli-0.13.12.tar.gz": _tar({"x/bin/signal-cli": SKRIPT})})
    with pytest.raises(mi.InstallError, match="Java ab Version 21"):
        mi.install_signal_cli(tmp_path / "daten", http=http, java=0)
    assert len(http.abrufe) == 1, "Das Archiv wird gar nicht erst geladen"  # type: ignore[attr-defined]


@pytest.mark.parametrize("fehler", ["weg", "html", "tag"])
def test_an_odd_github_answer_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                         fehler: str) -> None:
    _auf(monkeypatch, "Linux", "x86_64")

    def antwort(request: httpx.Request) -> httpx.Response:
        if fehler == "weg":
            return httpx.Response(404, json={})
        if fehler == "html":
            return httpx.Response(200, content=b"<html>")
        return httpx.Response(200, json={"tag_name": "v1.0.0/../../x", "assets": []})

    http = httpx.Client(transport=httpx.MockTransport(antwort))
    with pytest.raises(mi.InstallError, match="GitHub"):
        mi.install_signal_cli(tmp_path / "daten", http=http)


def test_a_download_url_off_github_is_refused(tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    _auf(monkeypatch, "Linux", "x86_64")
    archiv = _tar({"signal-cli": SKRIPT})

    def antwort(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.github.com":
            return httpx.Response(200, json={"tag_name": TAG, "assets": [{
                "name": NATIVE, "size": len(archiv),
                "digest": "sha256:" + hashlib.sha256(archiv).hexdigest(),
                "browser_download_url": f"https://boese.example/{NATIVE}"}]})
        raise AssertionError("Dorthin darf Aquaticy nicht gehen")

    with pytest.raises(mi.InstallError, match="GitHub"):
        mi.install_signal_cli(tmp_path / "daten", http=httpx.Client(
            transport=httpx.MockTransport(antwort)))


def test_an_archive_with_an_escaping_path_is_refused(tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    _auf(monkeypatch, "Linux", "x86_64")
    http = _github({NATIVE: _tar({"../draussen": b"x", "signal-cli": SKRIPT})})
    with pytest.raises(mi.InstallError, match="unsicher"):
        mi.install_signal_cli(tmp_path / "daten", http=http)
    assert not (tmp_path / "draussen").exists() and not (tmp_path / "daten" / "draussen").exists()


def test_the_module_can_install_into_a_folder_for_the_image(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    _auf(monkeypatch, "Linux", "x86_64")
    http = _github({NATIVE: _tar({"signal-cli": SKRIPT})})
    monkeypatch.setattr("aquaticy.llamacpp.client", lambda: http)
    ziel = tmp_path / "opt" / "signal-cli"
    assert mi.main(["signal-cli", "--dir", str(ziel)]) == 0
    assert (ziel / "signal-cli").is_file() and str(ziel) in capsys.readouterr().out
    monkeypatch.setattr("aquaticy.llamacpp.client", lambda: _github({}, status=500))
    assert mi.main(["signal-cli", "--dir", str(tmp_path / "zweiter")]) == 1
    assert "GitHub" in capsys.readouterr().out


# -- libmagic --------------------------------------------------------------------------------------
@pytest.mark.parametrize(("werkzeug", "paket"), [
    ("apt-get", "libmagic1"), ("dnf", "file-libs"), ("yum", "file-libs"), ("pacman", "file"),
    ("zypper", "libmagic1"), ("apk", "libmagic")])
def test_libmagic_comes_from_the_package_manager(werkzeug: str, paket: str,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    _auf(monkeypatch, "Linux", "x86_64")
    monkeypatch.setattr(mi.shutil, "which", lambda name: f"/usr/bin/{name}"
                        if name in (werkzeug, "sudo") else None)
    monkeypatch.setattr("aquaticy.vm_install._root", lambda: False)
    schritte = mi.libmagic_steps()
    assert schritte and all(s[0] == "sudo" for s in schritte)
    assert schritte[-1][-1] == paket
    monkeypatch.setattr("aquaticy.vm_install._root", lambda: True)
    assert all(s[0] == werkzeug for s in mi.libmagic_steps() or [])


def test_there_is_no_way_without_a_package_manager_or_sudo(
        monkeypatch: pytest.MonkeyPatch) -> None:
    _auf(monkeypatch, "Linux", "x86_64")
    assert mi.libmagic_steps() is None
    monkeypatch.setattr(mi.shutil, "which",
                        lambda n: "/usr/bin/apt-get" if n == "apt-get" else None)
    monkeypatch.setattr("aquaticy.vm_install._root", lambda: False)
    assert mi.libmagic_steps() is None, "ohne sudo und ohne Verwalter gibt es keinen Weg"
    _auf(monkeypatch, "Windows", "AMD64")
    assert mi.libmagic_steps() is None


def test_macos_uses_homebrew(monkeypatch: pytest.MonkeyPatch) -> None:
    _auf(monkeypatch, "Darwin", "arm64")
    assert mi.libmagic_steps() is None
    monkeypatch.setattr(mi.shutil, "which", lambda n: "/opt/homebrew/bin/brew")
    assert mi.libmagic_steps() == [["brew", "install", "libmagic"]]


def test_installing_libmagic_runs_the_steps_and_checks_neonize_again(
        monkeypatch: pytest.MonkeyPatch) -> None:
    _auf(monkeypatch, "Linux", "x86_64")
    monkeypatch.setattr(mi.shutil, "which", lambda n: f"/usr/bin/{n}" if n == "apk" else None)
    monkeypatch.setattr("aquaticy.vm_install._root", lambda: True)
    ran: list[list[str]] = []
    gezeigt: list[list[str]] = []
    pruefungen: list[int] = []
    monkeypatch.setattr(mi, "whatsapp_problem", lambda: pruefungen.append(1) or "")

    def run(befehl: list[str], **kwargs: Any) -> SimpleNamespace:
        ran.append(befehl)
        return SimpleNamespace(returncode=0)

    assert mi.install_libmagic(on_step=gezeigt.append, run=run)
    assert ran == gezeigt == [["apk", "add", "libmagic"]] and pruefungen


def test_a_failing_step_stops_and_reports_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _auf(monkeypatch, "Linux", "x86_64")
    monkeypatch.setattr(mi.shutil, "which", lambda n: f"/usr/bin/{n}" if n == "apt-get" else None)
    monkeypatch.setattr("aquaticy.vm_install._root", lambda: True)
    ran: list[list[str]] = []

    def run(befehl: list[str], **kwargs: Any) -> SimpleNamespace:
        ran.append(befehl)
        return SimpleNamespace(returncode=100)

    assert not mi.install_libmagic(run=run)
    assert len(ran) == 1, "nach dem ersten Fehler geht es nicht weiter"


def test_the_whatsapp_status_is_the_neonize_message(monkeypatch: pytest.MonkeyPatch) -> None:
    nat.neonize_available.cache_clear()
    monkeypatch.setattr(nat, "neonize_available", lambda: (False, nat.NEED_LIBMAGIC))
    assert mi.whatsapp_problem() == nat.NEED_LIBMAGIC
    assert mi.status()["whatsapp"] == nat.NEED_LIBMAGIC


# -- Der Befehl ------------------------------------------------------------------------------------
@pytest.fixture
def befehl(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Ein Aquaticy, in dem beides fehlt und nichts wirklich installiert wird."""
    stand: dict[str, Any] = {"libmagic": [], "signal": []}
    monkeypatch.setattr(mi, "whatsapp_problem", lambda: stand.get("whatsapp", nat.NEED_LIBMAGIC))
    monkeypatch.setattr(mi, "libmagic_steps", lambda: [["sudo", "apt-get", "install", "libmagic1"]])

    def libmagic(on_step=None, run=None) -> bool:
        stand["libmagic"].append(1)
        stand["whatsapp"] = ""
        return True

    def signal_cli(data_dir, **kwargs) -> Path:
        stand["signal"].append(Path(data_dir))
        ziel = mi.managed_dir(Path(data_dir)) / "signal-cli"
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(SKRIPT)
        ziel.chmod(0o755)
        return ziel

    monkeypatch.setattr(mi, "install_libmagic", libmagic)
    monkeypatch.setattr(mi, "install_signal_cli", signal_cli)
    monkeypatch.setattr(mi, "signal_asset_name", lambda tag, **k: ("x.tar.gz", "native"))
    return stand


def test_the_command_installs_both_with_yes(befehl: dict[str, Any], tmp_path: Path) -> None:
    ergebnis = CliRunner().invoke(cli.app, ["install-messenger", "--yes"])
    assert ergebnis.exit_code == 0, ergebnis.output
    assert befehl["libmagic"] == [1] and befehl["signal"] == [tmp_path / "daten"]
    assert "WhatsApp direkt: bereit" in ergebnis.output
    assert "Signal direkt: bereit" in ergebnis.output
    assert "sudo apt-get install libmagic1" in ergebnis.output, "Befehle werden vorher gezeigt"


def test_the_command_asks_and_a_no_installs_nothing(befehl: dict[str, Any]) -> None:
    ergebnis = CliRunner().invoke(cli.app, ["install-messenger"], input="n\nn\n")
    assert ergebnis.exit_code == 1
    assert befehl["libmagic"] == [] and befehl["signal"] == []
    assert "Abgebrochen" in ergebnis.output


def test_the_command_does_nothing_when_all_is_there(befehl: dict[str, Any], tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    befehl["whatsapp"] = ""
    monkeypatch.setattr(mi, "find_signal_cli", lambda data_dir=None: Path("/usr/bin/signal-cli"))
    ergebnis = CliRunner().invoke(cli.app, ["install-messenger"])
    assert ergebnis.exit_code == 0 and befehl["libmagic"] == [] and befehl["signal"] == []


def test_a_failed_download_is_reported_and_exits_with_one(
        befehl: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    def kaputt(data_dir, **kwargs):
        raise mi.InstallError("GitHub ist nicht erreichbar (ConnectError).")

    monkeypatch.setattr(mi, "install_signal_cli", kaputt)
    ergebnis = CliRunner().invoke(cli.app, ["install-messenger", "--yes"])
    assert ergebnis.exit_code == 1 and "GitHub ist nicht erreichbar" in ergebnis.output


def test_missing_neonize_is_not_fixed_by_libmagic(befehl: dict[str, Any]) -> None:
    befehl["whatsapp"] = nat.NEED_NEONIZE
    ergebnis = CliRunner().invoke(cli.app, ["install-messenger", "--yes"])
    assert befehl["libmagic"] == [] and "pip install neonize" in ergebnis.output
    assert ergebnis.exit_code == 1


def test_without_a_way_to_install_libmagic_the_hint_is_shown(
        befehl: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mi, "libmagic_steps", lambda: None)
    ergebnis = CliRunner().invoke(cli.app, ["install-messenger", "--yes"])
    assert ergebnis.exit_code == 1 and "libmagic" in ergebnis.output
    assert befehl["signal"], "Signal wird trotzdem eingerichtet"


def test_a_system_without_a_signal_build_gets_the_java_hint(
        befehl: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    befehl["whatsapp"] = ""
    monkeypatch.setattr(mi, "signal_asset_name", lambda tag, **k: ("", ""))
    ergebnis = CliRunner().invoke(cli.app, ["install-messenger", "--yes"])
    assert ergebnis.exit_code == 1 and befehl["signal"] == []
    assert "signal-cli" in ergebnis.output.replace("\n", " ")


# -- Beim Start ----------------------------------------------------------------------------
def _terminal(monkeypatch: pytest.MonkeyPatch, ja: bool) -> None:
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: ja)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: ja)


def test_the_start_without_a_terminal_only_points_to_the_command(
        befehl: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture) -> None:
    _terminal(monkeypatch, False)
    cli._messenger_beim_start(SimpleNamespace(data_dir=tmp_path / "daten"))
    assert befehl["libmagic"] == [] and befehl["signal"] == []
    assert "install-messenger" in capsys.readouterr().out


def test_the_start_asks_once_and_remembers_a_no(
        befehl: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _terminal(monkeypatch, True)
    antworten = iter([False, False])
    monkeypatch.setattr(cli.typer, "confirm", lambda *a, **k: next(antworten))
    einstellungen = SimpleNamespace(data_dir=tmp_path / "daten")
    cli._messenger_beim_start(einstellungen)
    assert (tmp_path / "daten" / mi.NEIN).exists() and befehl["signal"] == []
    cli._messenger_beim_start(einstellungen)  # fragt nicht wieder: confirm wuerde StopIteration
    assert befehl["libmagic"] == []


def test_the_start_installs_after_a_yes(befehl: dict[str, Any], tmp_path: Path,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    _terminal(monkeypatch, True)
    monkeypatch.setattr(cli.typer, "confirm", lambda *a, **k: True)
    cli._messenger_beim_start(SimpleNamespace(data_dir=tmp_path / "daten"))
    assert befehl["libmagic"] == [1] and befehl["signal"] == [tmp_path / "daten"]
    assert not (tmp_path / "daten" / mi.NEIN).exists()


def test_the_start_is_silent_when_all_is_there(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                               capsys: pytest.CaptureFixture) -> None:
    monkeypatch.setattr(mi, "status", lambda data_dir=None: {"whatsapp": "", "signal": ""})
    cli._messenger_beim_start(SimpleNamespace(data_dir=tmp_path / "daten"))
    assert capsys.readouterr().out == ""


def test_the_start_never_breaks_when_the_check_fails(tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    def kaputt(data_dir=None):
        raise OSError("kaputt")

    monkeypatch.setattr(mi, "status", kaputt)
    cli._messenger_beim_start(SimpleNamespace(data_dir=tmp_path))


def test_the_command_clears_an_earlier_no(befehl: dict[str, Any], tmp_path: Path) -> None:
    marker = tmp_path / "daten" / mi.NEIN
    marker.parent.mkdir(parents=True)
    marker.write_text("nein")
    CliRunner().invoke(cli.app, ["install-messenger", "--yes"])
    assert not marker.exists()


# -- Paket, Abbild, Doku ---------------------------------------------------------------------------
def test_neonize_is_installed_with_aquaticy_on_every_platform_that_has_wheels() -> None:
    from packaging.requirements import Requirement

    daten = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    neonize = [Requirement(z) for z in daten["dependencies"] if z.startswith("neonize")]
    assert len(neonize) == 1 and neonize[0].marker is not None
    for umgebung, erwartet in [
            ({"sys_platform": "linux", "platform_machine": "x86_64"}, True),
            ({"sys_platform": "linux", "platform_machine": "aarch64"}, True),
            ({"sys_platform": "darwin", "platform_machine": "arm64"}, True),
            ({"sys_platform": "win32", "platform_machine": "AMD64"}, True),
            ({"sys_platform": "linux", "platform_machine": "riscv64"}, False),
            ({"sys_platform": "freebsd13", "platform_machine": "amd64"}, False)]:
        assert neonize[0].marker.evaluate(umgebung) is erwartet, umgebung
    assert daten["optional-dependencies"]["messenger"] == [], "alter Name bleibt gueltig"
    constraints = (ROOT / "constraints.txt").read_text(encoding="utf-8")
    assert re.search(r"^neonize==", constraints, re.M)


def test_the_image_ships_libmagic_and_signal_cli() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "libmagic1" in dockerfile
    assert "aquaticy.messenger_install signal-cli --dir /opt/aquaticy/signal-cli" in dockerfile
    assert "[messenger]" not in dockerfile, "neonize kommt jetzt ohne Zusatz mit"


def test_the_docs_and_help_name_the_command() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.count("aquaticy install-messenger") >= 2
    assert "aquaticy[messenger]" not in readme
    hilfe = CliRunner().invoke(cli.app, ["--help"]).output
    assert "install-messenger" in hilfe


def test_the_default_hint_texts_are_plain_and_name_the_command() -> None:
    for text in (nat.NEED_LIBMAGIC, nat.NEED_SIGNAL_CLI):
        assert "aquaticy install-messenger" in text
        for satz in re.split(r"(?<=\.)\s+", text):
            assert len(satz.split()) <= 20, satz
    assert "pip install neonize" in nat.NEED_NEONIZE
