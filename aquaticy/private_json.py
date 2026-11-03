"""Lokale JSON-Einstellungen privat und ohne halbfertige Dateien ersetzen."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write(path: Path, value: dict[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError("Einstellungen dürfen keine symbolische Verknüpfung sein.")
    descriptor, temporary = tempfile.mkstemp(prefix=".aquaticy-json-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
