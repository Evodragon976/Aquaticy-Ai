"""Konten- und modellgebundene Schluessel fuer kurzlebige Sicherheitsurteile."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aquaticy.config import Settings


def cache_key(*parts: Any) -> str:
    # Struktur statt Trennzeichen: Nutzereingaben koennen jedes Zeichen enthalten.
    raw = json.dumps(parts, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def scope(settings: Settings, models: list[str]) -> str | None:
    try:
        # fast_kwargs_for prueft auch die AKTUELLE Modellfreigabe. Ein alter
        # Treffer darf weder eine entzogene Freigabe noch einen Schluesselwechsel
        # umgehen. Zugangsdaten verlassen diese Funktion nur als Hash.
        return cache_key(str(settings.data_dir.resolve()),
                         [(model, settings.fast_kwargs_for(model)) for model in models])
    except Exception:
        # Konfiguration/Endpunkt nicht verfuegbar: regulaer pruefen, nichts merken.
        return None
