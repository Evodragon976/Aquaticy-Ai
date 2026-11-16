"""Reste von Auto-Upgrading (bis 15.8.11): gebaute Modellfassungen fuehren zum Ausgangsmodell.

Auto-Upgrading baute aus einem lokalen Ollama-Modell Fassungen mit eingebautem Wissen
(``aquaticy-<name>-<hash>:<fassung>``). Seit 16.0.0 gibt es das Feature nicht mehr -- Aquaticy
lernt ueber das Gedaechtnis jedes Kontos. Zwei Dinge bleiben zu tun:

* Wer in seinen Einstellungen noch eine gebaute Fassung stehen hat, bekommt das Ausgangsmodell.
* Die alte Zustandsdatei (``upgrading.json``: Schalter, gesehene Hinweise, festgelegte Fassungen
  je Konto) wird beim Start geloescht. Uebrig bleibt nur eine kleine Liste "gebaute Fassung ->
  Ausgangsmodell" ohne jede Angabe zu Konten.

Die gebauten Fassungen selbst loescht Aquaticy nicht aus Ollama. ``ollama rm <name>`` raeumt
sie weg.
"""

from __future__ import annotations

import contextlib
import json
import threading
from pathlib import Path
from typing import Any

#: So beginnen die Namen der gebauten Fassungen in Ollama.
PREFIX = "aquaticy-"
ALT_NAME = "upgrading.json"
LISTE_NAME = "altmodelle.json"
_LOCK = threading.Lock()
_LISTEN: dict[str, dict[str, str]] = {}


def gebaut(name: str) -> bool:
    """Ist das der Name einer von Auto-Upgrading gebauten Fassung?"""
    return _lokal(name).startswith(PREFIX)


def _lokal(model_id: str) -> str:
    """Der Name in Ollama -- ohne den Vorsatz des Anbieters."""
    text = str(model_id or "").strip()
    for vorsatz in ("ollama_chat/", "ollama/"):
        if text.startswith(vorsatz):
            return text[len(vorsatz):]
    return text


def _aus_zustand(zustand: Any) -> dict[str, str]:
    liste: dict[str, str] = {}
    straenge = zustand.get("tracks") if isinstance(zustand, dict) else None
    for basis, strang in (straenge.items() if isinstance(straenge, dict) else ()):
        if not isinstance(strang, dict) or not isinstance(basis, str) or gebaut(basis):
            continue
        namen = [v.get("model") for v in strang.get("versions") or [] if isinstance(v, dict)]
        namen += list(strang.get("retired_models") or [])
        kandidat = strang.get("candidate")
        if isinstance(kandidat, dict):
            namen.append(kandidat.get("model"))
        for name in namen:
            if isinstance(name, str) and gebaut(name):
                liste[name] = basis
    return liste


def aufraeumen(data_dir: Path) -> int:
    """Einmal beim Start: alte Zustandsdatei auswerten und loeschen. Returns: Zahl der Fassungen."""
    ordner = Path(data_dir)
    alt, ziel = ordner / ALT_NAME, ordner / LISTE_NAME
    with _LOCK:
        if not alt.is_file() or alt.is_symlink():
            return 0
        try:
            liste = _aus_zustand(json.loads(alt.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            liste = {}
        if liste:
            from aquaticy.memory import secure_file

            vorher: dict[str, str] = {}
            with contextlib.suppress(OSError, ValueError):
                gelesen = json.loads(ziel.read_text(encoding="utf-8"))
                if isinstance(gelesen, dict):
                    vorher = {str(k): str(v) for k, v in gelesen.items()}
            neu = ziel.with_name(ziel.name + ".tmp")
            neu.write_text(json.dumps({**vorher, **liste}, ensure_ascii=False, indent=1),
                           encoding="utf-8")
            secure_file(neu)
            neu.replace(ziel)
        alt.unlink(missing_ok=True)
        _LISTEN.pop(str(ordner), None)
    return len(liste)


def _liste(data_dir: Path) -> dict[str, str]:
    schluessel = str(Path(data_dir))
    with _LOCK:
        if schluessel not in _LISTEN:
            liste: dict[str, str] = {}
            with contextlib.suppress(OSError, ValueError):
                gelesen = json.loads((Path(data_dir) / LISTE_NAME).read_text(encoding="utf-8"))
                if isinstance(gelesen, dict):
                    liste = {str(k): str(v) for k, v in gelesen.items()
                             if gebaut(str(k)) and not gebaut(str(v))}
            _LISTEN[schluessel] = liste
        return _LISTEN[schluessel]


def ausgangsmodell(data_dir: Path | None, model_id: str) -> str:
    """Fuer eine gebaute Fassung: ihr Ausgangsmodell. Alles andere kommt unveraendert zurueck."""
    name = _lokal(model_id)
    if data_dir is None or not name.startswith(PREFIX):
        return model_id
    basis = _liste(data_dir).get(name, "")
    return f"ollama_chat/{basis}" if basis else model_id
