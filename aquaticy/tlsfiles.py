"""Private TLS-Dateipaare gemeinsam sperren und mit Ruecknahme ersetzen."""

from __future__ import annotations

import os
import tempfile
import threading
import weakref
from pathlib import Path
from typing import Any

_LOCKS: weakref.WeakValueDictionary[str, Any] = weakref.WeakValueDictionary()
_LOCK_GUARD = threading.Lock()


def folder_lock(path: Path) -> Any:
    with _LOCK_GUARD:
        return _LOCKS.setdefault(str(path.resolve()), threading.RLock())


def _stage(path: Path, data: bytes) -> Path:
    from aquaticy.memory import secure_file

    descriptor, name = tempfile.mkstemp(prefix=".tls-", dir=path.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        secure_file(temporary)
        temporary.write_bytes(data)
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def replace_pair(cert: Path, key: Path, cert_data: bytes, key_data: bytes) -> None:
    previous = {path: path.read_bytes() if path.exists() else None for path in (cert, key)}
    staged: dict[Path, Path] = {}
    installed: list[Path] = []
    try:
        for path, data in ((cert, cert_data), (key, key_data)):
            staged[path] = _stage(path, data)
        for path in (cert, key):
            os.replace(staged[path], path)
            installed.append(path)
    except BaseException:
        for path in reversed(installed):
            old = previous[path]
            if old is None:
                path.unlink(missing_ok=True)
            else:
                write_private(path, old)
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def write_private(path: Path, data: bytes) -> None:
    """Private Dateien ohne vorhersagbare Zwischenpfade atomar ersetzen."""
    temporary = _stage(path, data)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
