"""Der Zustand der Oberflaeche -- auf dem Server, nicht im Browser.

Bis hierher lagen Erscheinungsbild, Arbeitsweise und die Schalter der
Modellauswahl im ``localStorage``. Das hatte drei Nachteile, und alle drei
faellt man erst spaeter auf die Fuesse:

* **Jedes Geraet wusste etwas anderes.** Am Rechner dunkel, am Handy hell;
  am Rechner Code-Modus, am Handy nicht. Es ist dieselbe Person und dasselbe
  Aquaticy -- es sollte auch derselbe Zustand sein.
* **Der Browser entschied.** Was er schickte, wurde geglaubt. Ein Tippfehler
  im Skript, ein alter Tab, ein zurechtgebogener Aufruf: alles kam bis zum
  Modell durch. Der Server hatte keine eigene Wahrheit, gegen die er haette
  pruefen koennen.
* **Es blinkte.** Die Seite kam hell an und wurde erst dunkel, nachdem das
  Skript gelaufen war.

Hier liegt jetzt die Wahrheit. Der Browser darf sie **vorschlagen**; was
gilt, entscheidet diese Datei -- jeder Wert gegen eine Liste erlaubter
Werte, alles andere faellt auf den Standard zurueck. Beim Ausliefern der
Seite wird der Zustand gleich mitgegeben, deshalb blinkt auch nichts mehr.

Abgelegt wird als eine einzige Zeile in derselben Datenbank wie der Rest.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

PALETTES = (
    "",
    "mono",
    "custom",
)


DESIGN_KEYS = ("accent", "bg", "sidebar")


DEFAULT_DESIGN: dict[str, str] = {key: "" for key in DESIGN_KEYS}



_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def clean_design(value: Any) -> dict[str, str]:
    """Macht aus dem Vorschlag ein sauberes Design: nur bekannte Farbwerte."""
    design = dict(DEFAULT_DESIGN)
    if not isinstance(value, dict):
        return design
    for key in DESIGN_KEYS:
        farbe = str(value.get(key) or "").strip().lower()
        if _HEX.fullmatch(farbe):
            design[key] = farbe
    return design


LANGUAGES = ("de", "en")


THEMES = ("light", "dark", "system")


FONT_SIZES = ("normal", "small", "large")



MODES = ("normal", "code", "pro")


EFFORTS = ("low", "medium", "high")



AGENT_COUNTS = range(1, 51)



FIELDS: dict[str, tuple[Any, Any]] = {
    "theme": ("system", THEMES),
    "palette": ("", PALETTES),
    "design": (DEFAULT_DESIGN, dict),
    "lang": ("de", LANGUAGES),
    "fontsize": ("normal", FONT_SIZES),
    "mode": ("normal", MODES),
    "effort": ("medium", EFFORTS),
    "structured": (False, bool),
    "recheck": (False, bool),
    "online": (True, bool),
    "sandbox": (False, bool),
    "denken": (False, bool),
    "tracing": (False, bool),
    "load": (False, bool),
    "agents": (12, AGENT_COUNTS),
    "visual_sources": (False, bool),


    "autoscroll": (True, bool),
    "voice_ok": (False, bool),
}





_YES = frozenset({True, "1", "true", "True", "on", "ja", "yes"})
_NO = frozenset({False, "0", "false", "False", "off", "nein", "no", "", None})

SCHEMA = """
CREATE TABLE IF NOT EXISTS uistate (
    id    INTEGER PRIMARY KEY CHECK (id = 1),
    state TEXT NOT NULL DEFAULT '{}'
);
"""


def defaults() -> dict[str, Any]:
    """Der Zustand, mit dem eine frische Oberflaeche startet."""
    return {
        name: (dict(standard) if isinstance(standard, dict) else standard)
        for name, (standard, _) in FIELDS.items()
    }


def clean_flag(value: Any, standard: bool) -> bool:
    """Macht aus dem, was der Browser schickt, einen Wahrheitswert.

    Was weder eindeutig ja noch eindeutig nein ist, bleibt beim Standard.
    Raten waere hier die schlechtere Wahl: ein falsch verstandenes "aus"
    schaltet eine Recherche an, die Minuten dauert.
    """
    if isinstance(value, str):
        value = value.strip()
    elif value is not None and not isinstance(value, (bool, int, float)):

        return standard
    if value in _YES:
        return True
    if value in _NO:
        return False
    return standard


def clean(raw: Any, *, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prueft einen Vorschlag aus dem Browser gegen die erlaubten Werte.

    Unbekannte Felder fallen weg, unerlaubte Werte fallen auf den bisherigen
    Stand zurueck. Es kommt immer ein vollstaendiger, gueltiger Zustand
    heraus -- nie ein halber.
    """
    stand = dict(defaults())
    if base:
        for name, wert in base.items():
            if name in FIELDS:
                stand[name] = wert
    if not isinstance(raw, dict):
        return stand
    for name, (standard, erlaubt) in FIELDS.items():
        if name not in raw:
            continue
        wert = raw[name]
        if erlaubt is bool:
            stand[name] = clean_flag(wert, bool(stand.get(name, standard)))
        elif erlaubt is dict:
            stand[name] = clean_design(wert)
        elif isinstance(erlaubt, range):
            try:
                zahl = int(wert)
            except (TypeError, ValueError, OverflowError):
                continue
            if zahl in erlaubt:
                stand[name] = zahl
        else:
            text = str(wert or "").strip()
            stand[name] = text if text in erlaubt else stand.get(name, standard)
    return stand





_SPERREN: dict[str, threading.Lock] = {}
_SPERREN_LOCK = threading.Lock()


def _sperre_fuer(pfad: Path) -> threading.Lock:
    schluessel = str(pfad.resolve())
    with _SPERREN_LOCK:
        return _SPERREN.setdefault(schluessel, threading.Lock())


class UIState:
    """Liest und schreibt den Zustand der Oberflaeche."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._lock = _sperre_fuer(self.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def read(self) -> dict[str, Any]:
        """Der gueltige Zustand. Faellt immer auf etwas Brauchbares zurueck."""
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT state FROM uistate WHERE id = 1").fetchone()
        except sqlite3.Error:
            return defaults()
        if not row:
            return defaults()
        try:
            gespeichert = json.loads(row["state"])
        except (TypeError, ValueError):
            return defaults()


        return clean(gespeichert)

    def write(self, raw: Any) -> dict[str, Any]:
        """Uebernimmt einen Vorschlag und gibt zurueck, was wirklich gilt."""
        with self._lock:
            neu = clean(raw, base=self.read())
            try:
                with self._connect() as conn:
                    conn.execute(
                        "INSERT INTO uistate (id, state) VALUES (1, ?) "
                        "ON CONFLICT(id) DO UPDATE SET state = excluded.state",
                        (json.dumps(neu, ensure_ascii=False),),
                    )
            except sqlite3.Error:


                pass
            return neu

    def reset(self) -> dict[str, Any]:
        """Zurueck auf Anfang."""
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM uistate")
        return defaults()
