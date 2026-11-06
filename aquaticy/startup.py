"""Einmaliger Hintergrundbetrieb und Updates beim Programmstart."""

from __future__ import annotations

import ast
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPOSITORY = "https://github.com/Evodragon976/Aquaticy-Ai.git"
BRANCH = "Aquaticy-ai"


def background(arguments: list[str], directory: Path, console: Any) -> None:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    log = directory / "background.log"
    flags: dict[str, Any] = {}
    if os.name == "nt":
        flags["creationflags"] = 0x00000008 | 0x00000200
    else:
        flags["start_new_session"] = True
    env = dict(os.environ, AQUATICY_STARTUP_CHILD="1")
    descriptor = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND
                         | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "ab") as output:
        with contextlib.suppress(OSError):
            log.chmod(0o600)
        process = subprocess.Popen(
            [sys.executable, "-m", "aquaticy.cli", *arguments],
            stdin=subprocess.DEVNULL, stdout=output, stderr=output, env=env, **flags)
    console.print(f"Hintergrundprozess: {process.pid}. Protokoll: {log}", markup=False)
    console.print("Strg+C schließt nur diese Anzeige. Beenden: Prozess im System beenden.")
    console.print("Nach dem Herunterfahren startest du Aquaticy wieder selbst.")
    try:
        code = process.wait()
    except KeyboardInterrupt:
        console.print(f"Aquaticy läuft weiter (Prozess {process.pid}).", markup=False)
        return
    if code:
        raise RuntimeError(f"Hintergrundprozess beendet (Code {code}). Protokoll: {log}")


def update_at_start(console: Any) -> bool:
    from aquaticy import VERSION_LABEL

    if os.environ.get("AQUATICY_STARTUP_CHILD") == "1":
        return False
    git = shutil.which("git")
    if not git:
        console.print("Updateprüfung nicht möglich: Git fehlt. Aquaticy startet trotzdem.")
        return False
    root = Path(__file__).resolve().parent.parent
    if (root / ".git").exists():
        status = subprocess.run([git, "-C", str(root), "status", "--porcelain"],
                                capture_output=True, text=True, timeout=15, check=True)
        if status.stdout.strip():
            console.print("Lokale Codeänderungen vorhanden. Automatisches Update ausgelassen.")
            return False
    console.print("Prüfe Aquaticy auf Updates …")
    with tempfile.TemporaryDirectory(prefix="aquaticy-update-") as temp:
        checkout = Path(temp) / "source"
        subprocess.run([git, "clone", "--depth", "1", "--single-branch", "--branch", BRANCH,
                        REPOSITORY, str(checkout)], capture_output=True, timeout=90, check=True)
        values: dict[str, str] = {}
        for node in ast.parse((checkout / "aquaticy/__init__.py").read_text()).body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value.value, str):
                        values[target.id] = node.value.value
        remote = " ".join(t for t in (values.get("__version__", ""),
                                      values.get("__codename__", ""),
                                      values.get("__stage__", "")) if t)
        if remote == VERSION_LABEL:
            console.print("Aquaticy ist aktuell.")
            return False
        local_number = tuple(int(n) for n in VERSION_LABEL.split()[0].split("."))
        remote_number = tuple(int(n) for n in str(values.get("__version__", "")).split("."))
        if remote_number < local_number:
            console.print("Die lokale Version ist neuer als der Update-Branch.")
            return False
        uv = shutil.which("uv")
        if uv:
            command = [uv, "pip", "install", "--python", sys.executable, "--reinstall",
                       "-c", str(checkout / "constraints.txt"), str(checkout)]
        else:
            command = [sys.executable, "-m", "pip", "install", "--upgrade",
                       "--force-reinstall", "-c", str(checkout / "constraints.txt"), str(checkout)]
        console.print(f"Installiere Aquaticy {remote} …", markup=False)
        subprocess.run(command, capture_output=True, timeout=600, check=True)
    return True
