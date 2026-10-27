#!/usr/bin/env python3
"""Die ganze Pruefkette in einem Befehl -- fuer Menschen und KI-Agenten (11.2.1 Sol).

    python tools/pruefung.py                      # alles
    python tools/pruefung.py --schnell            # ohne Testsuite (rund eine Minute)
    python tools/pruefung.py --nur ruff,mypy      # nur diese Schritte
    python tools/pruefung.py --tests tests/test_plugins.py tests/test_v1121.py
    python tools/pruefung.py --json bericht.json  # Ergebnis zusaetzlich als JSON

Schritte:

* ``ruff``    -- Stil und typische Fehler (``ruff check aquaticy tests tools``)
* ``mypy``    -- Typen im ganzen Paket (Einstellungen in ``pyproject.toml``)
* ``bandit``  -- Sicherheitsscan. Bekannte, gepruefte Hinweise stehen in
  ``tools/bandit-baseline.json``; nur NEUE zaehlen als Fehler.
* ``ui-js``   -- das JavaScript der Oberflaeche (``node --check``)
* ``pytest``  -- die Testsuite, einschliesslich Rundgang im Browser

Kein Schritt braucht Netz, Modell oder Schluessel. Fehlt ein Werkzeug, wird
der Schritt uebersprungen und das im Bericht genannt.

Rueckgabewert: 0, wenn kein Schritt fehlschlug, sonst die Zahl der
fehlgeschlagenen Schritte. Der JSON-Bericht nennt je Schritt Status, Dauer,
Befehl und -- bei pytest -- jeden fehlgeschlagenen Test mit seiner Meldung.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET  # nosec B405
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCHRITTE = ("ruff", "mypy", "bandit", "ui-js", "pytest")

AUSZUG = 40


@dataclass
class Ergebnis:
    """Was ein Schritt ergeben hat."""

    schritt: str
    status: str
    dauer_s: float = 0.0
    befehl: str = ""
    zusammenfassung: str = ""
    auszug: list[str] = field(default_factory=list)
    fehlschlaege: list[dict[str, str]] = field(default_factory=list)


def _werkzeug(name: str) -> list[str] | None:
    """Wie *name* aufgerufen wird: als Modul dieses Pythons oder als Programm."""
    modul = {"ruff": "ruff", "mypy": "mypy", "bandit": "bandit"}.get(name)
    if modul:
        geprueft = subprocess.run([sys.executable, "-m", modul, "--version"],
                                  capture_output=True, text=True, check=False)
        if geprueft.returncode == 0:
            return [sys.executable, "-m", modul]
    pfad = shutil.which(name)
    return [pfad] if pfad else None


def _lauf(schritt: str, befehl: list[str], timeout: float = 3600) -> tuple[int, str, float]:
    start = time.monotonic()
    try:
        fertig = subprocess.run(befehl, cwd=REPO, capture_output=True, text=True,
                                timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        ausgabe = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        return 124, ausgabe + f"\n[{schritt}: Zeitlimit von {timeout:.0f} s überschritten]", \
            time.monotonic() - start
    return fertig.returncode, (fertig.stdout or "") + (fertig.stderr or ""), \
        time.monotonic() - start


def _auszug(text: str) -> list[str]:
    zeilen = [z for z in text.splitlines() if z.strip()]
    return zeilen[-AUSZUG:]


def ruff() -> Ergebnis:
    aufruf = _werkzeug("ruff")
    if aufruf is None:
        return Ergebnis("ruff", "uebersprungen", zusammenfassung="ruff ist nicht installiert")
    befehl = [*aufruf, "check", "aquaticy", "tests", "tools", "--output-format", "concise"]
    code, text, dauer = _lauf("ruff", befehl)
    fehler = [z for z in text.splitlines() if re.match(r"^\S+\.py:\d+:\d+: ", z)]
    return Ergebnis("ruff", "ok" if code == 0 else "fehler", round(dauer, 1), " ".join(befehl),
                    "keine Beanstandung" if code == 0 else f"{len(fehler)} Beanstandungen",
                    [] if code == 0 else _auszug(text))


def mypy() -> Ergebnis:
    aufruf = _werkzeug("mypy")
    if aufruf is None:
        return Ergebnis("mypy", "uebersprungen", zusammenfassung="mypy ist nicht installiert")
    befehl = [*aufruf, "--python-executable", sys.executable]
    code, text, dauer = _lauf("mypy", befehl)
    letzte = text.strip().splitlines()[-1] if text.strip() else ""
    return Ergebnis("mypy", "ok" if code == 0 else "fehler", round(dauer, 1), " ".join(befehl),
                    letzte, [] if code == 0 else _auszug(text))


def bandit() -> Ergebnis:
    aufruf = _werkzeug("bandit")
    if aufruf is None:
        return Ergebnis("bandit", "uebersprungen", zusammenfassung="bandit ist nicht installiert")
    basis = REPO / "tools" / "bandit-baseline.json"
    befehl = [*aufruf, "-q", "-r", "aquaticy", "-ll", "-ii", "-f", "json"]
    if basis.exists():
        befehl += ["-b", str(basis.relative_to(REPO))]
    _, text, dauer = _lauf("bandit", befehl)
    try:
        start = text.index("{")
        daten = json.loads(text[start:text.rindex("}") + 1])
        neu = [{"stelle": f"{r['filename']}:{r['line_number']}", "regel": r["test_id"],
                "meldung": r["issue_text"]} for r in daten.get("results", [])]
    except (ValueError, KeyError):
        return Ergebnis("bandit", "fehler", round(dauer, 1), " ".join(befehl),
                        "Ausgabe von bandit nicht lesbar", _auszug(text))
    if neu:
        return Ergebnis("bandit", "fehler", round(dauer, 1), " ".join(befehl),
                        f"{len(neu)} neue Hinweise (mittel oder hoch)",
                        [f"{n['stelle']} {n['regel']}: {n['meldung']}" for n in neu][:AUSZUG])
    return Ergebnis("bandit", "ok", round(dauer, 1), " ".join(befehl),
                    "keine neuen Hinweise (bekannte stehen in tools/bandit-baseline.json)")


def ui_js() -> Ergebnis:
    node = shutil.which("node")
    if node is None:
        return Ergebnis("ui-js", "uebersprungen", zusammenfassung="node ist nicht installiert")
    html = (REPO / "aquaticy" / "webui.html").read_text(encoding="utf-8")
    skripte = re.findall(r"<script\b[^>]*>(.*?)</script>", html, re.S)
    with tempfile.TemporaryDirectory() as ordner:
        datei = Path(ordner) / "webui.js"
        datei.write_text("\n;\n".join(skripte), encoding="utf-8")
        code, text, dauer = _lauf("ui-js", [node, "--check", str(datei)])
    return Ergebnis("ui-js", "ok" if code == 0 else "fehler", round(dauer, 1),
                    "node --check <Skripte aus aquaticy/webui.html>",
                    f"Skripte ({len(skripte)}) ohne Syntaxfehler" if code == 0
                    else "Syntaxfehler im JavaScript", [] if code == 0 else _auszug(text))


def _junit(pfad: Path) -> tuple[dict[str, int], list[dict[str, str]]]:
    zahlen = {"tests": 0, "fehlschlaege": 0, "fehler": 0, "uebersprungen": 0}
    liste: list[dict[str, str]] = []
    if not pfad.exists():
        return zahlen, liste
    wurzel = ET.parse(pfad).getroot()  # nosec B314
    for fall in wurzel.iter("testcase"):
        zahlen["tests"] += 1
        for art, schluessel in (("failure", "fehlschlaege"), ("error", "fehler"),
                                ("skipped", "uebersprungen")):
            knoten = fall.find(art)
            if knoten is None:
                continue
            zahlen[schluessel] += 1
            if art != "skipped":
                modul = (fall.get("classname") or "").replace(".", "/")
                liste.append({
                    "test": f"{modul}.py::{fall.get('name')}",
                    "art": "Fehlschlag" if art == "failure" else "Fehler",
                    "meldung": (knoten.get("message") or "").strip()[:500],
                })
    return zahlen, liste


def pytest(tests: list[str]) -> Ergebnis:
    with tempfile.TemporaryDirectory() as ordner:
        junit = Path(ordner) / "junit.xml"
        befehl = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                  f"--junitxml={junit}", *tests]
        code, text, dauer = _lauf("pytest", befehl, timeout=5400)
        zahlen, liste = _junit(junit)
    rot = zahlen["fehlschlaege"] + zahlen["fehler"]
    gruen = zahlen["tests"] - rot - zahlen["uebersprungen"]
    kurz = (f"{zahlen['tests']} Tests: {gruen} bestanden, {zahlen['uebersprungen']} "
            f"übersprungen, {rot} fehlgeschlagen")
    ok = code == 0
    if code == 5:
        ok, kurz = False, "keine Tests gefunden"
    befehl_text = " ".join(befehl).replace(f"--junitxml={junit}", "--junitxml=<temp>")
    return Ergebnis("pytest", "ok" if ok else "fehler", round(dauer, 1), befehl_text, kurz,
                    [] if ok else _auszug(text), liste)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schnell", action="store_true", help="ohne Testsuite")
    parser.add_argument("--nur", default="", help="Komma-Liste der Schritte: "
                        + ",".join(SCHRITTE))
    parser.add_argument("--tests", nargs="*", default=[], help="nur diese Tests (pytest)")
    parser.add_argument("--json", default="", help="Bericht zusätzlich als JSON hierhin")
    args = parser.parse_args(argv)

    gewaehlt = [s.strip() for s in args.nur.split(",") if s.strip()] or list(SCHRITTE)
    unbekannt = [s for s in gewaehlt if s not in SCHRITTE]
    if unbekannt:
        parser.error(f"unbekannte Schritte: {', '.join(unbekannt)}")
    if args.schnell and not args.tests:
        gewaehlt = [s for s in gewaehlt if s != "pytest"]

    ergebnisse: list[Ergebnis] = []
    for schritt in gewaehlt:
        print(f"→ {schritt} …", flush=True)
        if schritt == "pytest":
            ergebnis = pytest(args.tests)
        else:
            ergebnis = {"ruff": ruff, "mypy": mypy, "bandit": bandit, "ui-js": ui_js}[schritt]()
        ergebnisse.append(ergebnis)
        zeichen = {"ok": "✓", "fehler": "✗", "uebersprungen": "–"}[ergebnis.status]
        print(f"  {zeichen} {schritt}: {ergebnis.zusammenfassung} ({ergebnis.dauer_s} s)")
        for zeile in ergebnis.auszug[-15:]:
            print(f"      {zeile}")
        for fall in ergebnis.fehlschlaege[:30]:
            print(f"      {fall['art']}: {fall['test']}\n        {fall['meldung'][:200]}")

    fehler = sum(1 for e in ergebnisse if e.status == "fehler")
    bericht = {
        "ok": fehler == 0,
        "fehlgeschlagene_schritte": fehler,
        "uebersprungene_schritte": [e.schritt for e in ergebnisse if e.status == "uebersprungen"],
        "schritte": [asdict(e) for e in ergebnisse],
    }
    if args.json:
        Path(args.json).write_text(json.dumps(bericht, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    print("\nErgebnis:",
          "alles in Ordnung" if fehler == 0 else f"{fehler} Schritt(e) fehlgeschlagen")
    return fehler


if __name__ == "__main__":
    sys.exit(main())
