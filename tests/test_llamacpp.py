"""11.0.0 Luna: llama.cpp installiert sich fuer "Serverlast aufteilen" selbst.

Statt GitHub antwortet ein gestellter Server (httpx.MockTransport): er liefert
die Liste einer Veroeffentlichung und Archive mit kleinen gestellten Programmen.
So laesst sich alles pruefen, was beim Laden schiefgehen kann -- falsche
Pruefsumme, fremde Umleitung, boese Pfade im Archiv -- und der ganze Weg bis
zum verteilten Modell, ohne dass irgendwo llama.cpp installiert sein muss.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import sys
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pytest

from aquaticy import llamacpp, sharding, web
from tests.test_cluster import _warte, verbund  # noqa: F401
from tests.test_sharding import FAKE_LLAMA, FAKE_RPC, paar  # noqa: F401

TAG = "b7000"
API = llamacpp.REPO_API
DOWNLOAD = "https://github.com/ggml-org/llama.cpp/releases/download"
CDN = "https://release-assets.githubusercontent.com/github-production-release-asset"

#: Ein gestellter llama-server, der auch "--version" und "--list-devices" kennt.
FAKE_SERVER = (
    'import sys\n'
    'if "--version" in sys.argv:\n'
    '    print("version: 7000 (gestellt)")\n'
    '    sys.exit(0)\n'
    'if "--list-devices" in sys.argv:\n'
    '    print("Available devices:\\n  CPU: gestellt")\n'
    '    sys.exit(0)\n'
)
#: Eine Grafik-Ausgabe, die auf diesem Rechner keine Karte findet.
FAKE_SERVER_OHNE_KARTE = (
    'import sys\n'
    'print("ggml_vulkan: No devices found.", file=sys.stderr)\n'
    'sys.exit(1)\n'
)


def _skript(code: str) -> bytes:
    return f"#!{sys.executable}\n{code}".encode()


def _zip(dateien: dict[str, bytes], links: dict[str, str] | None = None) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as zf:
        for name, inhalt in dateien.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFREG | 0o755) << 16
            zf.writestr(info, inhalt)
        for name, ziel in (links or {}).items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, ziel)
    return puffer.getvalue()


def _tar(dateien: dict[str, bytes], links: dict[str, str] | None = None) -> bytes:
    puffer = io.BytesIO()
    with tarfile.open(fileobj=puffer, mode="w:gz") as tf:
        for name, inhalt in dateien.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(inhalt), 0o755
            tf.addfile(info, io.BytesIO(inhalt))
        for name, ziel in (links or {}).items():
            info = tarfile.TarInfo(name)
            info.type, info.linkname = tarfile.SYMTYPE, ziel
            tf.addfile(info)
    return puffer.getvalue()


def _programme(server: str = FAKE_SERVER, rpc: str = FAKE_RPC,
               ordner: str = "build/bin/") -> dict[str, bytes]:
    return {f"{ordner}llama-server": _skript(server + FAKE_LLAMA),
            f"{ordner}rpc-server": _skript(rpc), f"{ordner}LICENSE": b"MIT"}


class GitHub:
    """Ein gestellter GitHub: Veroeffentlichungen, Umleitung und Download."""

    def __init__(self) -> None:
        self.latest = TAG
        self.archive: dict[str, bytes] = {}
        self.digest: dict[str, str] = {}
        self.redirect: dict[str, str] = {}
        self.calls: list[str] = []

    def add(self, plattform: str, daten: bytes, *, tag: str = TAG, art: str = "zip",
            digest: str | None = None) -> str:
        name = f"llama-{tag}-bin-{plattform}.{art}"
        self.archive[name] = daten
        self.digest[name] = (digest if digest is not None
                             else "sha256:" + hashlib.sha256(daten).hexdigest())
        return name

    def release(self, tag: str) -> dict[str, Any]:
        assets = [{"name": name, "size": len(daten),
                   "browser_download_url": f"{DOWNLOAD}/{tag}/{name}",
                   **({"digest": self.digest[name]} if self.digest[name] else {})}
                  for name, daten in self.archive.items() if f"-{tag}-" in name]
        assets.append({"name": f"llama-{tag}-xcframework.zip", "size": 10,
                       "browser_download_url": f"{DOWNLOAD}/{tag}/x.zip"})
        return {"tag_name": tag, "assets": assets}

    def __call__(self, anfrage: httpx.Request) -> httpx.Response:
        url = str(anfrage.url)
        self.calls.append(url)
        if url == f"{API}/releases/latest":
            return httpx.Response(200, json=self.release(self.latest))
        if url.startswith(f"{API}/releases/tags/"):
            tag = url.rsplit("/", 1)[1]
            if not any(f"-{tag}-" in name for name in self.archive):
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json=self.release(tag))
        if url.startswith(DOWNLOAD):
            name = url.rsplit("/", 1)[1]
            ziel = self.redirect.get(name, f"{CDN}/{name}?sig=gestellt")
            return httpx.Response(302, headers={"location": ziel})
        if url.startswith(CDN):
            name = url.rsplit("/", 1)[1].split("?", 1)[0]
            return httpx.Response(200, content=self.archive[name])
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self), follow_redirects=False)


@pytest.fixture
def github(monkeypatch) -> GitHub:
    fake = GitHub()
    monkeypatch.setattr(llamacpp, "client", fake.client)
    monkeypatch.setattr(llamacpp, "SYSTEM_DIR", Path("/gibt-es-nicht/llama.cpp"))
    monkeypatch.delenv(llamacpp.DIR_ENV, raising=False)
    monkeypatch.delenv(llamacpp.TAG_ENV, raising=False)
    return fake


def _installer(root: Path, namen: list[str]) -> llamacpp.Installer:
    installer = llamacpp.Installer(root)
    installer._namen = list(namen)  # sonst haengt es am Rechner, auf dem der Test laeuft
    return installer


def _fertig(installer: llamacpp.Installer, tag: str = TAG) -> llamacpp.Install | None:
    if installer.ensure(tag) is None:
        installer.wait(60)
    return installer.installed(tag)


# -- Welche Ausgabe ---------------------------------------------------------------------
def test_each_system_gets_its_own_edition() -> None:
    namen = llamacpp.platform_names
    assert namen("Darwin", "arm64") == ["macos-arm64"]
    assert namen("Darwin", "x86_64") == ["macos-x64"]
    assert namen("Linux", "x86_64") == ["ubuntu-x64"]
    assert namen("Linux", "x86_64", gpu=True, vulkan=True) == ["ubuntu-vulkan-x64", "ubuntu-x64"]
    # Ohne Vulkan-Lader startet die Grafik-Ausgabe nicht -- dann gleich die fuer den Prozessor.
    assert namen("Linux", "x86_64", gpu=True, vulkan=False) == ["ubuntu-x64"]
    assert namen("Linux", "aarch64") == ["ubuntu-arm64"]
    assert namen("Windows", "AMD64", gpu=True) == ["win-vulkan-x64", "win-cpu-x64"]
    assert namen("Windows", "ARM64") == ["win-cpu-arm64"]
    assert namen("FreeBSD", "amd64") == []
    assert {"macos-arm64", "ubuntu-vulkan-x64", "win-vulkan-x64"} <= llamacpp.ACCELERATED
    assert "ubuntu-x64" not in llamacpp.ACCELERATED


def test_the_right_asset_is_picked() -> None:
    daten = {"tag_name": TAG, "assets": [
        {"name": f"llama-{TAG}-bin-ubuntu-vulkan-x64.zip"},
        {"name": f"llama-{TAG}-bin-ubuntu-x64.tar.gz"},
        {"name": "llama-b6999-bin-ubuntu-x64.zip"},  # fremde Fassung
        {"name": f"llama-{TAG}-bin-win-cuda-12.4-x64.zip"},
        {"name": "cudart-llama-bin-win-cuda-12.4-x64.zip"},
        "kaputt",
    ]}
    assert llamacpp.pick_asset(daten, ["ubuntu-x64"])["name"].endswith("ubuntu-x64.tar.gz")
    assert llamacpp.pick_asset(daten, ["macos-arm64", "ubuntu-vulkan-x64"])["plattform"] \
        == "ubuntu-vulkan-x64"
    assert llamacpp.pick_asset(daten, ["win-cuda-12.4-x64"]) is not None
    assert llamacpp.pick_asset(daten, ["macos-arm64"]) is None


# -- Installieren ---------------------------------------------------------------------------
def test_llama_cpp_installs_itself_checked_and_once(github: GitHub, tmp_path: Path) -> None:
    github.add("ubuntu-x64", _zip(_programme(), links={"build/bin/libggml.so": "LICENSE"}))
    installer = _installer(tmp_path / "llama.cpp", ["ubuntu-x64"])
    eintrag = _fertig(installer)
    assert eintrag is not None, installer.message
    assert eintrag.tag == TAG and eintrag.plattform == "ubuntu-x64" and not eintrag.accelerated
    assert eintrag.folder == (tmp_path / "llama.cpp" / f"{TAG}-ubuntu-x64").resolve()
    for programm in (eintrag.rpc_server, eintrag.llama_server):
        assert programm.is_file() and os.access(programm, os.X_OK)
        assert programm.is_relative_to(eintrag.folder)
    # Verknuepfungen innerhalb des Ordners bleiben Verknuepfungen.
    link = eintrag.folder / "build" / "bin" / "libggml.so"
    assert link.is_symlink() and os.readlink(link) == "LICENSE"
    merkzettel = json.loads((eintrag.folder / llamacpp.MARKER).read_text())
    assert merkzettel["sha256"] == hashlib.sha256(
        github.archive[f"llama-{TAG}-bin-ubuntu-x64.zip"]).hexdigest()
    assert installer.status()["phase"] == "bereit" and eintrag.label() == \
        f"llama.cpp {TAG} (Prozessor)"
    # Ueber die Umleitung zu GitHubs Download-Server -- und kein Rest im Ordner.
    assert any(url.startswith(CDN) for url in github.calls)
    assert [p.name for p in (tmp_path / "llama.cpp").iterdir()] == [f"{TAG}-ubuntu-x64"]
    # Schon da: kein zweiter Download.
    vorher = len(github.calls)
    assert installer.ensure(TAG) == eintrag and len(github.calls) == vorher


def test_a_tar_edition_with_a_top_folder_installs_too(github: GitHub, tmp_path: Path) -> None:
    github.add("macos-arm64", _tar(_programme(ordner=f"llama-{TAG}/")), art="tar.gz")
    installer = _installer(tmp_path / "llama.cpp", ["macos-arm64"])
    eintrag = _fertig(installer)
    assert eintrag is not None and eintrag.accelerated
    assert eintrag.llama_server.parent.name == f"llama-{TAG}"
    assert eintrag.label() == f"llama.cpp {TAG} (Metal)"


def test_a_wrong_checksum_installs_nothing(github: GitHub, tmp_path: Path) -> None:
    github.add("ubuntu-x64", _zip(_programme()), digest="sha256:" + "0" * 64)
    installer = _installer(tmp_path / "llama.cpp", ["ubuntu-x64"])
    assert _fertig(installer) is None
    assert installer.phase == "fehler" and "Prüfsumme" in installer.message
    assert not any((tmp_path / "llama.cpp").iterdir()), "nichts bleibt liegen"


def test_without_a_published_checksum_nothing_is_installed(github: GitHub,
                                                            tmp_path: Path) -> None:
    github.add("ubuntu-x64", _zip(_programme()), digest="")
    installer = _installer(tmp_path / "llama.cpp", ["ubuntu-x64"])
    assert _fertig(installer) is None and "Prüfsumme" in installer.message


def test_downloads_only_come_from_github(github: GitHub, tmp_path: Path) -> None:
    name = github.add("ubuntu-x64", _zip(_programme()))
    for fremd in ("https://evil.example/llama.zip", "http://objects.githubusercontent.com/x",
                  "https://github.com.evil.example/x", "https://user@github.com/x"):
        github.redirect[name] = fremd
        installer = _installer(tmp_path / "llama.cpp", ["ubuntu-x64"])
        assert _fertig(installer) is None, fremd
        assert "Download-Servern von GitHub" in installer.message
    assert not any(url.startswith("https://evil") for url in github.calls)


def test_a_newer_version_replaces_the_old_one(github: GitHub, tmp_path: Path) -> None:
    github.add("ubuntu-x64", _zip(_programme()))
    github.add("ubuntu-x64", _zip(_programme()), tag="b7001")
    root = tmp_path / "llama.cpp"
    assert _fertig(_installer(root, ["ubuntu-x64"])) is not None
    assert _fertig(_installer(root, ["ubuntu-x64"]), "b7001") is not None
    assert sorted(p.name for p in root.iterdir()) == ["b7001-ubuntu-x64"]


def test_a_graphics_edition_without_a_card_falls_back_to_the_cpu(github: GitHub,
                                                               tmp_path: Path) -> None:
    github.add("ubuntu-vulkan-x64", _zip(_programme(server=FAKE_SERVER_OHNE_KARTE)))
    github.add("ubuntu-x64", _zip(_programme()))
    installer = _installer(tmp_path / "llama.cpp", ["ubuntu-vulkan-x64", "ubuntu-x64"])
    eintrag = _fertig(installer)
    assert eintrag is not None and eintrag.plattform == "ubuntu-x64"
    assert installer.names() == ["ubuntu-x64"]
    assert not (tmp_path / "llama.cpp" / f"{TAG}-ubuntu-vulkan-x64").exists()


def test_a_missing_graphics_edition_falls_back_too(github: GitHub, tmp_path: Path) -> None:
    github.add("ubuntu-x64", _zip(_programme()))
    installer = _installer(tmp_path / "llama.cpp", ["ubuntu-vulkan-x64", "ubuntu-x64"])
    eintrag = _fertig(installer)
    assert eintrag is not None and eintrag.plattform == "ubuntu-x64"


def test_an_edition_without_the_programs_is_refused(github: GitHub, tmp_path: Path) -> None:
    github.add("ubuntu-x64", _zip({"build/bin/llama-cli": _skript(FAKE_SERVER)}))
    installer = _installer(tmp_path / "llama.cpp", ["ubuntu-x64"])
    assert _fertig(installer) is None and "fehlt" in installer.message


# -- Boese Archive ----------------------------------------------------------------------------
@pytest.mark.parametrize("dateien,links", [
    ({"../ausserhalb": b"x"}, None),
    ({"/etc/ausserhalb": b"x"}, None),
    ({"build/../../ausserhalb": b"x"}, None),
    ({"C:/Windows/x": b"x"}, None),
    ({"ok": b"x"}, {"build/bin/weg": "../../../ausserhalb"}),
    ({"ok": b"x"}, {"build/bin/weg": "/etc/passwd"}),
])
def test_a_zip_never_writes_outside_its_folder(tmp_path: Path, dateien, links) -> None:
    archiv = tmp_path / "a.zip"
    archiv.write_bytes(_zip(dateien, links))
    ziel = tmp_path / "ziel"
    ziel.mkdir()
    with pytest.raises(llamacpp.LlamaError):
        llamacpp.unpack_zip(archiv, ziel)
    assert not (tmp_path / "ausserhalb").exists()


@pytest.mark.parametrize("dateien,links", [
    ({"../ausserhalb": b"x"}, None),
    ({"/tmp/ausserhalb-aquaticy": b"x"}, None),
    ({"ok": b"x"}, {"weg": "../../ausserhalb"}),
    ({"ok": b"x"}, {"weg": "/etc/passwd"}),
])
def test_a_tar_never_writes_outside_its_folder(tmp_path: Path, dateien, links) -> None:
    archiv = tmp_path / "a.tar.gz"
    archiv.write_bytes(_tar(dateien, links))
    ziel = tmp_path / "ziel"
    ziel.mkdir()
    with pytest.raises(llamacpp.LlamaError):
        llamacpp.unpack_tar(archiv, ziel)
    assert not (tmp_path / "ausserhalb").exists()
    assert not Path("/tmp/ausserhalb-aquaticy").exists()


def test_archive_limits_hold(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(llamacpp, "MAX_FILES", 3)
    archiv = tmp_path / "a.zip"
    archiv.write_bytes(_zip({f"d{i}": b"x" for i in range(5)}))
    ziel = tmp_path / "ziel"
    ziel.mkdir()
    with pytest.raises(llamacpp.LlamaError, match="zu viele"):
        llamacpp.unpack_zip(archiv, ziel)
    monkeypatch.setattr(llamacpp, "MAX_FILES", 4000)
    monkeypatch.setattr(llamacpp, "MAX_UNPACKED_BYTES", 100)
    archiv.write_bytes(_zip({"gross": bytes(1000)}))
    with pytest.raises(llamacpp.LlamaError, match="zu groß"):
        llamacpp.unpack_zip(archiv, ziel)


def test_a_foreign_marker_is_not_trusted(tmp_path: Path) -> None:
    ordner = tmp_path / f"{TAG}-ubuntu-x64"
    (ordner / "bin").mkdir(parents=True)
    (ordner / "bin" / "rpc-server").write_bytes(b"x")
    (ordner / "bin" / "llama-server").write_bytes(b"x")
    gut = {"tag": TAG, "plattform": "ubuntu-x64", "rpc_server": "bin/rpc-server",
           "llama_server": "bin/llama-server"}
    (ordner / llamacpp.MARKER).write_text(json.dumps(gut))
    assert llamacpp.read_install(ordner) is not None
    for kaputt in ({"tag": "b1"}, {"plattform": "win-cpu-x64"},
                   {"rpc_server": "../../etc/passwd"}, {"llama_server": "/bin/sh"},
                   {"rpc_server": "bin/llama-server"}):
        (ordner / llamacpp.MARKER).write_text(json.dumps({**gut, **kaputt}))
        assert llamacpp.read_install(ordner) is None, kaputt


# -- Welche Fassung -----------------------------------------------------------------------------
def test_the_master_picks_one_version_for_everyone(github: GitHub, tmp_path: Path,
                                                   monkeypatch) -> None:
    github.latest = "b7123"
    installer = _installer(tmp_path / "llama.cpp", ["ubuntu-x64"])
    assert installer.chosen() == "" or installer.chosen() == "b7123"
    installer.wait(30)
    assert installer.chosen() == "b7123"
    # Was schon installiert ist, bleibt die Fassung -- nicht jedes Mal die neueste.
    github.add("ubuntu-x64", _zip(_programme()))
    vorhanden = _installer(tmp_path / "zwei", ["ubuntu-x64"])
    assert _fertig(vorhanden) is not None
    neu = _installer(tmp_path / "zwei", ["ubuntu-x64"])
    assert neu.chosen() == TAG
    # Der Betreiber kann eine Fassung fest vorgeben.
    monkeypatch.setenv(llamacpp.TAG_ENV, "b6000")
    assert neu.chosen() == "b6000"


def test_a_preinstalled_version_is_used_without_download(github: GitHub, tmp_path: Path,
                                                         monkeypatch) -> None:
    github.add("ubuntu-x64", _zip(_programme()))
    mitgeliefert = tmp_path / "opt"
    assert _fertig(_installer(mitgeliefert, ["ubuntu-x64"])) is not None
    mitgeliefert.chmod(0o755)
    monkeypatch.setenv(llamacpp.DIR_ENV, str(mitgeliefert))
    github.calls.clear()
    installer = _installer(tmp_path / "eigen", ["ubuntu-x64"])
    eintrag = installer.ensure(TAG)
    assert eintrag is not None and eintrag.folder.is_relative_to(mitgeliefert.resolve())
    assert github.calls == []
    assert installer.chosen() == TAG
    # Ein Ordner, in den jeder schreiben darf, zaehlt nicht.
    mitgeliefert.chmod(0o777)
    try:
        assert _installer(tmp_path / "eigen", ["ubuntu-x64"]).installed(TAG) is None
    finally:
        mitgeliefert.chmod(0o755)


def test_failures_back_off_and_say_why(tmp_path: Path, monkeypatch) -> None:
    def kaputt() -> httpx.Client:
        def antwort(anfrage: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("keine Verbindung", request=anfrage)
        return httpx.Client(transport=httpx.MockTransport(antwort))

    installer = llamacpp.Installer(tmp_path, http=kaputt)
    installer._namen = ["ubuntu-x64"]
    assert installer.ensure(TAG) is None
    installer.wait(30)
    assert installer.phase == "fehler" and "GitHub ist nicht erreichbar" in installer.message
    # Gleich noch einmal: es wird nicht sofort wieder geladen.
    assert installer.ensure(TAG) is None and installer._thread is not None
    assert not installer._thread.is_alive() and installer._naechster > time.monotonic()


def test_a_rate_limit_is_not_a_refusal() -> None:
    def antwort(kopf: dict[str, str]) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(
            lambda anfrage: httpx.Response(403, headers=kopf, json={"message": "x"})))

    with pytest.raises(llamacpp.LlamaError, match="bremst"):
        llamacpp.release(http=antwort({"x-ratelimit-remaining": "0"}))
    with pytest.raises(llamacpp.LlamaError, match="verweigert den Zugriff"):
        llamacpp.release(http=antwort({}))


# -- Im Verbund ------------------------------------------------------------------------------
def test_split_mode_installs_llama_cpp_on_every_server(paar, github: GitHub,  # noqa: F811
                                                       tmp_path: Path, monkeypatch) -> None:
    """Niemand installiert etwas: einschalten, und das Modell laeuft verteilt."""
    a, b = paar
    for env in (sharding.RPC_ENV, sharding.SERVER_ENV):
        monkeypatch.delenv(env, raising=False)
    # Kein llama.cpp im Suchpfad -- alles kommt von "GitHub".
    monkeypatch.setattr(sharding, "find_binary", lambda env, namen: "")
    monkeypatch.setenv("FAKE_LLAMA_RECORD", str(tmp_path / "llama.json"))
    monkeypatch.setattr(sharding, "nvidia_card", lambda: False)
    monkeypatch.setattr(sharding, "has_own_accelerator", lambda: False)
    monkeypatch.setattr(llamacpp, "platform_names", lambda **_: ["ubuntu-x64"])
    sharding._RPC_CACHE.clear()
    github.add("ubuntu-x64", _zip(_programme()))
    modell = tmp_path / "modell.gguf"
    modell.write_bytes(b"GGUF" + bytes(2048))
    monkeypatch.setattr(sharding, "ollama_gguf", lambda name, url: modell)
    mgr_a = sharding.Manager(a, lambda: "http://127.0.0.1:9")
    mgr_b = sharding.Manager(b, lambda: "http://127.0.0.1:9")
    b.hooks.load = lambda: {"split": mgr_b.worker_status()}
    monkeypatch.setattr(web, "SHARDING", mgr_b)
    try:
        a.set_split(True, "testmodell")
        # Der Master waehlt die Fassung und schickt sie an alle.
        _warte(lambda: (mgr_a.tick(), a.split().get("llama"))[1] == TAG, 30)
        assert b.split().get("llama") == TAG, "die Fassung kommt mit der Mitgliederliste"
        _warte(lambda: (mgr_b.tick(), mgr_b.worker.ready)[1], 60)
        assert Path(mgr_b.worker._proc.args[0]).resolve().is_relative_to(
            (b.dir.parent / "llama.cpp").resolve())

        def bereit() -> bool:
            a.sync_once(full=False)
            mgr_a.tick()
            return mgr_a.ready()

        _warte(bereit, 60)
        aufzeichnung = json.loads((tmp_path / "llama.json").read_text())
        assert len(aufzeichnung["args"][aufzeichnung["args"].index("--rpc") + 1]
                   .split(",")) == 2
        ansicht = mgr_a.view()
        assert ansicht["llama"]["fassung"] == TAG
        assert ansicht["llama"]["label"] == f"llama.cpp {TAG} (Prozessor)"
        assert ansicht["server_binary"] and ansicht["auto_install"]
        # Der Download lief je Server einmal -- beide holen dieselbe Fassung.
        geladen = [u for u in github.calls if u.startswith(CDN)]
        assert len(geladen) == 2
    finally:
        mgr_a.stop()
        mgr_b.stop()


def test_a_member_shows_the_download_as_a_note_not_an_error() -> None:
    from aquaticy.cluster import _split_status

    status = _split_status({"ready": False, "error": "", "note": "Lädt llama.cpp b7000 … 40 %",
                            "mem_gb": 8})
    assert status["note"].startswith("Lädt llama.cpp") and not status["error"]
    assert len(_split_status({"note": "x" * 999})["note"]) == 200


def test_the_ui_says_that_llama_cpp_installs_itself() -> None:
    html = web.UI_FILE.read_text(encoding="utf-8")
    assert "llama.cpp installiert Aquaticy dafür selbst" in html
    assert "if (s.note) return ` · ${s.note}`;" in html
    assert "Braucht llama.cpp auf jedem Server." not in html
