"""Ollamas Parallelbetrieb am lokalen Rechner einrichten, nur aus dem Terminal.

Ein laufender Dienst erbt Aquaticys Umgebung nicht. Unter Linux bekommt er
deshalb ein eigenes systemd-Drop-in; unter macOS wird der Homebrew-LaunchAgent
angepasst. Windows speichert den Wert fuer den Benutzer und beendet nur dessen
nach Pfad geprueften Ollama-Prozess. Andere Einstellungen bleiben erhalten.
Downloads und Neustarts bestaetigt der Aufrufer vorher. Browserkonten erreichen
diese Funktionen nicht. Unbekannte laufende Dienste werden nicht beendet.
"""

from __future__ import annotations

import os
import platform
import plistlib
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

PARALLEL = 2
SERVICE_FILE = Path("/etc/systemd/system/ollama.service.d/90-aquaticy-parallel.conf")


class SetupError(RuntimeError):
    """Installation oder Dienstkonfiguration konnte nicht sicher abgeschlossen werden."""


def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(command, text=True, timeout=60, check=False, **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        raise SetupError("Ollama-Einrichtung: Befehl konnte nicht ausgeführt werden.") from exc
    if result.returncode:

        raise SetupError("Ollama-Einrichtung: Dienstbefehl fehlgeschlagen.")
    return result


def _parallel(value: str) -> bool:


    return (len(value) <= 19 and value.isascii() and value.isdecimal()
            and 2 <= int(value) <= 2 ** 63 - 1)


def _systemd() -> list[str] | None:
    if not shutil.which("systemctl"):
        return None
    for command in (["systemctl"], ["systemctl", "--user"]):
        try:
            state = _run([*command, "show", "ollama.service", "-p", "LoadState", "--value"],
                         capture_output=True)
        except SetupError:
            continue
        if state.stdout.strip() == "loaded":
            return command
    return None


def _linux(command: list[str]) -> None:
    environment = _run([*command, "show", "ollama.service", "-p", "Environment", "--value"],
                       capture_output=True).stdout
    try:
        values = dict(item.split("=", 1) for item in shlex.split(environment) if "=" in item)
    except ValueError as exc:
        raise SetupError("Die Umgebung des Ollama-Dienstes konnte nicht gelesen werden.") from exc

    count = values.get("OLLAMA_NUM_PARALLEL", "")
    count = count if _parallel(count) else str(PARALLEL)
    content = f'[Service]\nEnvironment="OLLAMA_NUM_PARALLEL={count}"\n'
    if "--user" in command:
        target = Path.home() / ".config/systemd/user/ollama.service.d/90-aquaticy-parallel.conf"
        _write(target, content.encode())
        prefix: list[str] = []
    else:
        root = getattr(os, "geteuid", lambda: -1)() == 0
        prefix = [] if root else ["sudo"]
        if prefix and not shutil.which("sudo"):
            raise SetupError("Für den Ollama-Dienst fehlen Verwalterrechte (sudo).")

        _run([*prefix, "mkdir", "-p", "--", str(SERVICE_FILE.parent)])
        _run([*prefix, "install", "-m", "0644", "/dev/stdin", str(SERVICE_FILE)],
             input=content)
    _run([*prefix, *command, "daemon-reload"])
    _run([*prefix, *command, "restart", "ollama.service"])
    effective = _run([*command, "show", "ollama.service", "-p", "Environment", "--value"],
                     capture_output=True).stdout
    try:
        current = dict(item.split("=", 1) for item in shlex.split(effective) if "=" in item)
    except ValueError as exc:
        raise SetupError("Die wirksame Ollama-Einstellung konnte nicht gelesen werden.") from exc
    if not _parallel(current.get("OLLAMA_NUM_PARALLEL", "")):
        raise SetupError("Eine andere Dienstregel überschreibt Ollamas Parallelbetrieb. "
                         "Bitte die systemd-Umgebung prüfen.")


def _write(target: Path, data: bytes) -> None:
    """Benutzerdateien atomar ersetzen; symbolischen Zielen nie folgen."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise SetupError("Eine symbolisch verknüpfte Dienstdatei wird nicht verändert.")
    descriptor, temporary = tempfile.mkstemp(prefix=".aquaticy-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _macos(*, running: bool) -> None:
    target = Path.home() / "Library/LaunchAgents/homebrew.mxcl.ollama.plist"
    if target.is_symlink():
        raise SetupError("Eine symbolisch verknüpfte Dienstdatei wird nicht verändert.")
    if not target.exists():
        if running or not shutil.which("brew"):
            raise SetupError("Ollama bitte beenden und die Einrichtung erneut starten; "
                             "die App wird nicht ungeprüft beendet.")
        _run(["brew", "services", "start", "ollama"], capture_output=True)
    if target.is_symlink():
        raise SetupError("Eine symbolisch verknüpfte Dienstdatei wird nicht verändert.")
    try:
        data = plistlib.loads(target.read_bytes())
        if not isinstance(data, dict) or data.get("Label") != "homebrew.mxcl.ollama":
            raise ValueError("Unbekannter Dienst")
        environment = data.setdefault("EnvironmentVariables", {})
        if not isinstance(environment, dict):
            raise ValueError("Ungueltige Umgebung")
        value = str(environment.get("OLLAMA_NUM_PARALLEL", ""))
        if not _parallel(value):
            environment["OLLAMA_NUM_PARALLEL"] = str(PARALLEL)
        content = plistlib.dumps(data)
    except (OSError, ValueError, TypeError, plistlib.InvalidFileException) as exc:
        raise SetupError("Der Homebrew-Dienst von Ollama konnte nicht gelesen werden.") from exc
    domain = f"gui/{os.getuid()}"

    try:
        _run(["launchctl", "print", f"{domain}/homebrew.mxcl.ollama"], capture_output=True)
    except SetupError:
        pass
    else:
        _run(["launchctl", "bootout", domain, str(target)], capture_output=True)
    _write(target, content)
    _run(["launchctl", "bootstrap", domain, str(target)], capture_output=True)




_WINDOWS = r"""
$ErrorActionPreference = 'Stop'
$binary = [IO.Path]::GetFullPath($env:AQUATICY_OLLAMA_SETUP_BINARY)
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$listeners = @(Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue)
$processes = @()
foreach ($id in @($listeners.OwningProcess | Select-Object -Unique)) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$id"
    $owner = Invoke-CimMethod -InputObject $process -MethodName GetOwnerSid
    if ($owner.Sid -ne $sid -or !$process.ExecutablePath -or
        [IO.Path]::GetFullPath($process.ExecutablePath) -ne $binary) {
        throw 'Der laufende Ollama-Dienst gehoert nicht diesem Benutzer oder Programm.'
    }
    $processes += $process
}
$value = [Environment]::GetEnvironmentVariable('OLLAMA_NUM_PARALLEL', 'User')
$parsed = [long]0
if ($value -notmatch '^[0-9]{1,19}$' -or
    ![long]::TryParse($value, [ref]$parsed) -or $parsed -lt 2) { $value = '2' }
[Environment]::SetEnvironmentVariable('OLLAMA_NUM_PARALLEL', $value, 'User')
$trayPath = Join-Path (Split-Path $binary) 'ollama app.exe'
foreach ($tray in @(Get-CimInstance Win32_Process -Filter "Name='ollama app.exe'")) {
    $owner = Invoke-CimMethod -InputObject $tray -MethodName GetOwnerSid
    if ($owner.Sid -eq $sid -and $tray.ExecutablePath -eq $trayPath) {
        Stop-Process -Id $tray.ProcessId -ErrorAction Stop
    }
}
foreach ($process in $processes) {
    # Die Tray-App kann ihren Server beim Beenden schon mitgenommen haben.
    if (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) {
        Stop-Process -Id $process.ProcessId -ErrorAction Stop
    }
}
$deadline = [DateTime]::UtcNow.AddSeconds(10)
while (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue) {
    if ([DateTime]::UtcNow -ge $deadline) { throw 'Ollama hat den Port nicht freigegeben.' }
    Start-Sleep -Milliseconds 100
}
Write-Output $value
"""


def configure_parallel(*, running: bool) -> bool:
    """Persistenten lokalen Dienst konfigurieren; Fehler nie als Erfolg ausgeben.

    Der Aufrufer hat einen moeglichen Neustart bereits bestaetigen lassen.
    Ohne laufenden Dienst genuegt `start_server`: jeder eigene Start setzt
    die Parallelitaet erneut, auch nach einem Rechnerneustart.
    """
    from aquaticy import local_model as lm

    system = platform.system()
    if system == "Linux":
        command = _systemd()
        if command:
            _linux(command)
            return True
    elif system == "Darwin" and (running or shutil.which("brew")):
        _macos(running=running)
        return True
    elif system == "Windows":
        binary = lm.ollama_binary()
        if binary is None:
            raise SetupError("Ollama wurde nach der Installation nicht gefunden.")
        environment = dict(os.environ, AQUATICY_OLLAMA_SETUP_BINARY=binary)
        result = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _WINDOWS],
                      env=environment, capture_output=True)
        value = result.stdout.strip()
        if not _parallel(value):
            raise SetupError("Windows hat die Ollama-Einstellung nicht bestätigt.")
        os.environ["OLLAMA_NUM_PARALLEL"] = value
        return False
    if running:
        raise SetupError("Der laufende Ollama-Prozess kann nicht sicher neu gestartet werden. "
                         "Bitte Ollama beenden und aquaticy setup erneut ausführen. "
                         "Aquaticy startet ihn dann mit Parallelbetrieb.")
    return False
