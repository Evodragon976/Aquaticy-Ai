"""Die angezeigte Version muss zu dem installierbaren Paket passen.

Seit 11.2.1 Sol steht die Fassung hier an genau einer Stelle (NUMMER, NAME).
Die anderen Tests lesen sie von hier; fuer eine neue Fassung aendert man nur
diese beiden Werte -- und dieser Test sagt, was sonst noch nachzuziehen ist.
"""

import tomllib
from pathlib import Path

import aquaticy

ROOT = Path(__file__).resolve().parents[1]
NUMMER = "12.1.1"
NAME = "Terra"
LABEL = f"{NUMMER} {NAME}"


def test_release_version_is_consistent() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    label = aquaticy.VERSION_LABEL

    assert metadata["project"]["version"] == aquaticy.__version__
    assert (ROOT / "README.md").read_text(encoding="utf-8").startswith(
        f"# Aquaticy AI {label}\n"
    )
    assert f'window.__AQUATICY_VERSION__ || "{label}"' in (
        ROOT / "aquaticy" / "webui.html"
    ).read_text(encoding="utf-8")


def test_package_is_this_release() -> None:
    assert aquaticy.__version__ == NUMMER
    assert aquaticy.__codename__ == NAME
    assert aquaticy.VERSION_LABEL == LABEL
    assert aquaticy.__stage__ == "" and not aquaticy.INTERNAL


def test_release_files_name_this_release() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"TESTREPORT-{NUMMER}-{NAME}.md" in readme
    assert (ROOT / f"TESTREPORT-{NUMMER}-{NAME}.md").exists()
    constraints = (ROOT / "constraints.txt").read_text(encoding="utf-8")
    assert constraints.startswith(f"# Aquaticy {LABEL} --")
