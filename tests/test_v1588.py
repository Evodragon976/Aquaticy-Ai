"""15.8.8: Vercel baut eine schlichte Startseite statt mit PYTHON_ENTRYPOINT_NOT_FOUND
abzubrechen -- ohne die App selbst ungeschuetzt ins Internet zu stellen."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path
from typing import Any

from aquaticy import vercel

ROOT = Path(__file__).resolve().parents[1]


def _rufe(methode: str = "GET", pfad: str = "/") -> tuple[str, dict[str, str], bytes]:
    gesehen: dict[str, Any] = {}

    def start(status: str, kopf: list[tuple[str, str]]) -> None:
        gesehen["status"], gesehen["kopf"] = status, dict(kopf)

    koerper = b"".join(vercel.app({"REQUEST_METHOD": methode, "PATH_INFO": pfad}, start))
    return gesehen["status"], gesehen["kopf"], koerper


def test_pyproject_names_the_vercel_entrypoint() -> None:
    daten = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert daten["tool"]["vercel"]["entrypoint"] == "aquaticy.vercel:app"


def test_the_start_page_is_served_with_strict_headers() -> None:
    status, kopf, koerper = _rufe()
    assert status.startswith("200") and b"Aquaticy AI" in koerper and b"English" in koerper
    assert "default-src 'none'" in kopf["Content-Security-Policy"]
    assert kopf["X-Content-Type-Options"] == "nosniff" and b"<script" not in koerper
    assert int(kopf["Content-Length"]) == len(koerper)


def test_nothing_else_is_reachable() -> None:
    assert _rufe(pfad="/api/chat")[0].startswith("404")
    assert _rufe(pfad="/api/config")[0].startswith("404")
    assert _rufe("POST", "/")[0].startswith("405")
    assert _rufe("HEAD", "/")[2] == b""


def test_the_entrypoint_imports_nothing_from_aquaticy() -> None:
    baum = ast.parse((ROOT / "aquaticy" / "vercel.py").read_text(encoding="utf-8"))
    module = {n.module or "" for n in ast.walk(baum) if isinstance(n, ast.ImportFrom)}
    module |= {a.name for n in ast.walk(baum) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m.startswith("aquaticy") for m in module)
    assert module <= {"__future__", "collections.abc", "typing"}


def test_every_extra_can_be_installed_with_pillow_13() -> None:
    """uv lock auf Vercel loest alle Extras auf: term-image (Pillow < 11) brach den Build ab."""
    daten = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert any(d.lower().startswith("pillow>=13") for d in daten["project"]["dependencies"])
    extras = daten["project"]["optional-dependencies"]
    assert not any(d.lower().startswith("term-image") for paket in extras.values() for d in paket)


def test_vercelignore_keeps_what_the_wheel_includes() -> None:
    """hatchling bricht ab, wenn eine force-include-Datei fehlt ("Forced include not found")."""
    import pathspec

    daten = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    fest = daten["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    regeln = (ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines()
    spec = pathspec.PathSpec.from_lines("gitwildmatch", regeln)
    assert fest and not [quelle for quelle in fest if spec.match_file(quelle)]


def test_the_readme_explains_vercel() -> None:
    assert "### Vercel" in (ROOT / "README.md").read_text(encoding="utf-8")
