"""12.6.6 Luna: Desktop-Abbild bauen, Telegram Web weg, Messenger-Brücke.

* Das Desktop-Abbild ``aquaticy-werkstatt-desktop:local`` gab es nur nach einem
  Befehl von Hand. Fehlte es, kam beim Installieren eines Add-ons Podmans
  "short-name ... did not resolve to an alias ..." -- ohne Hinweis, was fehlt.
  Jetzt baut die Installation das Abbild selbst, und alle anderen Wege nennen den
  Grund in einem Satz.
* Telegram Web ist kein Add-on mehr.
* Mit Aquaticy per WhatsApp oder Signal schreiben (aquaticy/bridge.py).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aquaticy import addons
from aquaticy import sandbox as werkstatt
from aquaticy.config import Settings
from aquaticy.sandbox import Runtime, SandboxUnavailable

#: Die Meldung von Podman, wie sie ein Nutzer gesehen hat.
PODMAN_SHORT_NAME = (
    'Error: short-name "aquaticy-werkstatt-desktop:local" did not resolve to an alias and no '
    'unqualified-search registries are defined in "/etc/containers/registries.conf"'
)
PODMAN = Runtime("podman", "podman", "Podman (ohne Wurzelrechte)")


class Laufzeit:
    """Ersetzt ``sandbox._runs``: schreibt mit, was gefragt wurde, und antwortet nach Regeln."""

    def __init__(self, abbild_da: bool = True, bauen_klappt: bool = True,
                 stderr_beim_bauen: str = "") -> None:
        self.aufrufe: list[tuple[str, ...]] = []
        self.abbild_da = abbild_da
        self.bauen_klappt = bauen_klappt
        self.stderr_beim_bauen = stderr_beim_bauen
        self.kontext: dict[str, bool] = {}

    def __call__(self, binary: str, *args: str, timeout: float = 8.0
                 ) -> subprocess.CompletedProcess[str]:
        self.aufrufe.append((binary, *args))
        if args[:2] == ("image", "inspect"):
            return subprocess.CompletedProcess(args, 0 if self.abbild_da else 125, "", "")
        if args[0] == "build":
            wurzel = Path(args[args.index("-f") + 1]).parents[1]
            self.kontext = {
                "rezept": (wurzel / "docker" / "workshop-desktop.Dockerfile").is_file(),
                **{name: (wurzel / "docker" / "desktop" / name).is_file()
                   for name in werkstatt.DESKTOP_HELPERS},
                "nur_das": sorted(p.name for p in (wurzel / "docker").iterdir()) == [
                    "desktop", "workshop-desktop.Dockerfile"],
            }
            if self.bauen_klappt:
                self.abbild_da = True
                return subprocess.CompletedProcess(args, 0, "gebaut", "")
            return subprocess.CompletedProcess(args, 1, "", self.stderr_beim_bauen)
        return subprocess.CompletedProcess(args, 0, "", "")


@pytest.fixture
def laufzeit(monkeypatch: pytest.MonkeyPatch):
    def stellen(**kwargs: Any) -> Laufzeit:
        gestellt = Laufzeit(**kwargs)
        monkeypatch.setattr(werkstatt, "_runs", gestellt)
        return gestellt

    return stellen


# -- Teil A: das Desktop-Abbild ------------------------------------------------------------
def test_the_podman_message_is_recognised() -> None:
    assert werkstatt.short_name_problem(PODMAN_SHORT_NAME)
    assert not werkstatt.short_name_problem("Error: no such container")
    assert not werkstatt.short_name_problem("")


def test_an_existing_image_is_left_alone(laufzeit) -> None:
    gestellt = laufzeit(abbild_da=True)
    werkstatt.ensure_image(PODMAN, werkstatt.DESKTOP_IMAGE, build=True)
    assert [a[1] for a in gestellt.aufrufe] == ["image"], "nur nachgesehen, nicht gebaut"


def test_a_missing_desktop_image_is_built_from_a_small_folder(laufzeit) -> None:
    gestellt = laufzeit(abbild_da=False)
    meldungen: list[str] = []
    werkstatt.ensure_image(PODMAN, werkstatt.DESKTOP_IMAGE, build=True, progress=meldungen.append)
    bau = next(a for a in gestellt.aufrufe if a[1] == "build")
    assert bau[bau.index("-t") + 1] == werkstatt.DESKTOP_IMAGE
    # Im Ordner lagen nur das Rezept und die drei Hilfsprogramme -- nicht das ganze Projekt.
    assert gestellt.kontext == {"rezept": True, "aquaticy-desktop": True, "aquaticy-netz": True,
                                "aquaticy-addons": True, "nur_das": True}
    assert meldungen and "Desktop-Abbild" in meldungen[0]
    assert not Path(bau[bau.index("-f") + 1]).exists(), "der Ordner wird danach gelöscht"


def test_without_build_permission_it_only_explains(laufzeit) -> None:
    gestellt = laufzeit(abbild_da=False)
    with pytest.raises(SandboxUnavailable) as fehler:
        werkstatt.ensure_image(PODMAN, werkstatt.DESKTOP_IMAGE)
    text = str(fehler.value)
    assert "gibt es auf diesem Rechner noch nicht" in text
    assert "podman build -f docker/workshop-desktop.Dockerfile" in text
    assert not any(a[1] == "build" for a in gestellt.aufrufe)


def test_only_the_desktop_image_is_ever_built(laufzeit) -> None:
    gestellt = laufzeit(abbild_da=False)
    with pytest.raises(SandboxUnavailable, match="podman pull"):
        werkstatt.ensure_image(PODMAN, "meins:1", build=True)
    assert not any(a[1] == "build" for a in gestellt.aufrufe)


def test_a_failed_build_says_why(laufzeit) -> None:
    laufzeit(abbild_da=False, bauen_klappt=False, stderr_beim_bauen=PODMAN_SHORT_NAME)
    with pytest.raises(SandboxUnavailable) as fehler:
        werkstatt.ensure_image(PODMAN, werkstatt.DESKTOP_IMAGE, build=True)
    assert "ließ sich nicht bauen" in str(fehler.value)
    assert "unqualified-search-registries" in str(fehler.value)


def test_without_the_recipe_the_error_says_how_to_build_by_hand(
        laufzeit, monkeypatch: pytest.MonkeyPatch) -> None:
    laufzeit(abbild_da=False)
    monkeypatch.setattr(werkstatt, "desktop_recipe", lambda: None)
    with pytest.raises(SandboxUnavailable, match="Bauvorlage"):
        werkstatt.ensure_image(PODMAN, werkstatt.DESKTOP_IMAGE, build=True)


def test_the_volume_error_names_the_missing_image_not_podmans_riddle(
        monkeypatch: pytest.MonkeyPatch) -> None:
    def runs(binary: str, *args: str, timeout: float = 8.0):
        if args[:2] == ("volume", "inspect"):
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 125, "", PODMAN_SHORT_NAME)

    monkeypatch.setattr(werkstatt, "_runs", runs)
    with pytest.raises(SandboxUnavailable) as fehler:
        werkstatt.ensure_addon_volume(PODMAN, "aquaticy-addon-0123456789ab-signal",
                                      werkstatt.DESKTOP_IMAGE)
    assert "short-name" not in str(fehler.value)
    assert "Desktop-Abbild" in str(fehler.value)


def test_base_images_carry_their_registry() -> None:
    """Podman ohne 'unqualified-search-registries' kennt 'ubuntu:24.04' nicht."""
    assert werkstatt.DEFAULT_IMAGE.startswith("docker.io/")
    wurzel = Path(werkstatt.__file__).resolve().parent.parent
    for datei in ("Dockerfile", "docker/workshop-desktop.Dockerfile",
                  "docker/workshop-blender.Dockerfile"):
        for zeile in (wurzel / datei).read_text(encoding="utf-8").splitlines():
            if zeile.startswith("FROM ") and zeile.split()[1] not in {"base", "browser", "slim"}:
                assert zeile.split()[1].startswith("docker.io/"), (datei, zeile)


def test_starting_the_machine_names_the_missing_image(monkeypatch: pytest.MonkeyPatch) -> None:
    box = werkstatt.Sandbox(image=werkstatt.DESKTOP_IMAGE, user_mode=True)
    box.runtime = PODMAN
    monkeypatch.setattr(
        werkstatt, "_runs",
        lambda binary, *a, **kw: subprocess.CompletedProcess(a, 125, "", PODMAN_SHORT_NAME))
    with pytest.raises(SandboxUnavailable) as fehler:
        box._start_container()
    text = str(fehler.value)
    assert "short-name" not in text and "podman build -f docker/workshop-desktop.Dockerfile" in text


def test_the_recipe_and_helpers_are_found_in_the_project() -> None:
    gefunden = werkstatt.desktop_recipe()
    assert gefunden is not None and gefunden[0].name == "workshop-desktop.Dockerfile"
    assert {p.name for p in gefunden[1].iterdir() if p.is_file()} >= set(
        werkstatt.DESKTOP_HELPERS)


# -- Die Installation eines Add-ons baut das Abbild ------------------------------------------
@pytest.fixture
def konto(tmp_path: Path) -> Settings:
    ordner = tmp_path / "konto"
    ordner.mkdir()
    return Settings(data_dir=ordner, env_path=ordner / ".env", vm_user_mode=True)


def test_installing_an_addon_builds_the_image_first(
        konto: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    reihenfolge: list[str] = []
    monkeypatch.setattr(werkstatt, "find_runtime", lambda: SimpleNamespace(binary="podman"))
    monkeypatch.setattr(
        werkstatt, "ensure_image",
        lambda runtime, image, **kw: (reihenfolge.append(f"abbild:{image}:{kw.get('build')}"),
                                      kw["progress"]("Baut das Desktop-Abbild …")))
    monkeypatch.setattr(werkstatt, "ensure_addon_volume",
                        lambda runtime, volume, image: reihenfolge.append("datentraeger"))

    class Kiste:
        def __init__(self, **kw: Any) -> None:
            reihenfolge.append("kiste")

        def ensure(self) -> str:
            return "box"

        def addon_helper(self, *args: str, timeout: int = 0):
            import json

            return subprocess.CompletedProcess(args, 0, json.dumps({"ok": True}), "")

        def stop(self, reason: str = "") -> None: ...

    monkeypatch.setattr(werkstatt, "Sandbox", Kiste)
    addons.install(konto, "signal", pro=True, wait=True)
    assert reihenfolge[0] == f"abbild:{werkstatt.DESKTOP_IMAGE}:True"
    assert reihenfolge.index("datentraeger") < reihenfolge.index("kiste")
    assert addons.load_state(konto)["signal"]["status"] == "bereit"


def test_a_failed_image_shows_up_as_the_add_on_status(
        konto: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(werkstatt, "find_runtime", lambda: SimpleNamespace(binary="podman"))

    def fehlt(runtime: Any, image: str, **kw: Any) -> None:
        raise SandboxUnavailable(werkstatt.missing_image_text(PODMAN, image))

    monkeypatch.setattr(werkstatt, "ensure_image", fehlt)
    addons.install(konto, "signal", pro=True, wait=True)
    eintrag = addons.load_state(konto)["signal"]
    assert eintrag["status"] == "fehler" and "Desktop-Abbild" in eintrag["message"]
    assert "short-name" not in eintrag["message"]


# -- Teil B: Telegram Web ist kein Add-on mehr --------------------------------------------
def test_telegram_is_gone_from_the_catalogue_the_ui_and_the_helper() -> None:
    wurzel = Path(werkstatt.__file__).resolve().parent.parent
    assert "telegram" not in addons.CATALOG
    html = (wurzel / "aquaticy" / "webui.html").read_text(encoding="utf-8")
    assert "Telegram" not in html
    assert '"telegram"' not in (wurzel / "docker" / "desktop" / "aquaticy-desktop").read_text(
        encoding="utf-8")
    from aquaticy import plugins

    assert "telegram" not in plugins.TOOL_HINTS and "telegram" not in plugins.DESKTOP_PLUGINS
    assert "telegram" not in plugins.ALIASES.values()


def test_a_telegram_window_in_the_ordinary_browser_stays_read_only() -> None:
    """Die Sperre bleibt: ohne Add-on gilt jedes Messenger-Fenster als 'Nur lesen'."""
    assert addons.messenger_of("Falkon Browser.Falkon", "Telegram Web - Falkon") == "telegram"
    assert addons.messenger_rights(SimpleNamespace(), "telegram") == addons.STRICTEST


def test_an_old_telegram_entry_is_cleaned_up_once(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    konto = tmp_path / "konto"
    konto.mkdir()
    einstellungen = Settings(data_dir=konto, env_path=konto / ".env")
    (konto / addons.STATE_FILE).write_text(json.dumps({"addons": {
        "telegram": {"installed": True, "enabled": True},
        "wetter": {"installed": True, "enabled": True}}}), encoding="utf-8")
    entfernt: list[str] = []
    monkeypatch.setattr(werkstatt, "find_runtime", lambda: SimpleNamespace(binary="podman"))
    monkeypatch.setattr(werkstatt, "remove_addon_volume",
                        lambda runtime, volume: entfernt.append(volume) or True)
    ansicht = addons.public_view(einstellungen, pro=True)
    assert "telegram" not in [a["id"] for a in ansicht["addons"]]
    assert entfernt == [addons.volume_name(einstellungen, "telegram")]
    roh = json.loads((konto / addons.STATE_FILE).read_text(encoding="utf-8"))
    assert set(roh["addons"]) == {"wetter"}
    entfernt.clear()
    addons.public_view(einstellungen, pro=True)
    assert entfernt == [], "beim zweiten Mal ist nichts mehr zu tun"


def test_an_old_telegram_entry_without_a_runtime_is_still_dropped(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    konto = tmp_path / "konto"
    konto.mkdir()
    einstellungen = Settings(data_dir=konto, env_path=konto / ".env")
    (konto / addons.STATE_FILE).write_text(
        json.dumps({"addons": {"telegram": {"installed": True}}}), encoding="utf-8")
    monkeypatch.setattr(werkstatt, "find_runtime", lambda: None)
    assert addons.retire_removed(einstellungen) == ["telegram"]
    assert json.loads((konto / addons.STATE_FILE).read_text(encoding="utf-8"))["addons"] == {}
