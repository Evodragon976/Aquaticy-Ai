# Hinweise für KI-Agenten

Diese Datei richtet sich an Agenten (Claude Code, Codex & Co.) und an Menschen,
die an Aquaticy arbeiten. Sie sagt, wie man prüft, wo was liegt und was nie
geändert werden darf.

## Prüfen: ein Befehl

```bash
python tools/pruefung.py                     # alles, rund 15 Minuten
python tools/pruefung.py --schnell           # ohne Testsuite, rund 10 Sekunden
python tools/pruefung.py --tests tests/test_plugins.py tests/test_v1121.py
python tools/pruefung.py --nur ruff,mypy     # nur diese Schritte
python tools/pruefung.py --json bericht.json # Ergebnis als JSON
```

Rückgabewert 0 heißt: alles in Ordnung. Sonst ist es die Zahl der
fehlgeschlagenen Schritte. Der JSON-Bericht nennt je Schritt Status, Dauer,
Befehl, die letzten Zeilen der Ausgabe und bei pytest jeden fehlgeschlagenen
Test mit Meldung.

| Schritt | Was | Einzeln |
|---|---|---|
| `ruff` | Stil, Importe, typische Fehler | `ruff check aquaticy tests tools` |
| `mypy` | Typen im ganzen Paket | `mypy --python-executable "$(which python)"` |
| `bandit` | Sicherheitsscan, nur neue Hinweise zählen | `bandit -q -r aquaticy -ll -ii -b tools/bandit-baseline.json` |
| `ui-js` | JavaScript der Oberfläche | siehe `tools/pruefung.py` |
| `pytest` | alle Tests, auch der Rundgang im Browser | `python -m pytest -q` |

Kein Schritt braucht Netz, Modell oder API-Schlüssel. Die Tests arbeiten mit
gestellten Modellen (`tests/test_agent.py: ScriptedLLM`) und der Fixture
`settings` aus `tests/conftest.py`, die nichts außerhalb von `tmp_path`
anfasst. Der Rundgang (`tests/test_rundgang.py`) braucht Playwright und
Chromium und wird sonst übersprungen.

Vor jedem Commit: `python tools/pruefung.py` muss mit 0 enden.

## Aufbau

- `aquaticy/` – das Paket. Jedes Modul sagt in seiner ersten Zeile, wofür es da ist.
  - `agent.py` Schleife mit Werkzeugaufrufen, `tools.py` die Werkzeuge,
    `subagents.py`/`master.py` parallele Recherche, `ownservices.py` erkennt Fragen an
    Mails, Kalender, Home Assistant und Lager (dann ohne Websuche).
  - `web.py` Server und API, `webui.html` die ganze Oberfläche (HTML, CSS, JS).
  - `cli.py` Kommandozeile, `config.py` Einstellungen.
  - Sicherheit: `netguard.py` (nur öffentliche Ziele), `injection.py`
    (Prompt-Injection), `aiguard.py` (Missbrauch), `guardrails.py` (Recht),
    `auth.py` (Konten), `privacy.py`/`keyvault.py` (Verschlüsselung),
    `sandbox.py` (virtual machine).
  - Messenger: `bridge.py` (Chat mit Aquaticy per WhatsApp/Signal; Regeln für Absender und
    Werkzeuge stehen dort im Code), `messenger_native.py` (direkt koppeln ohne virtual machine:
    neonize und signal-cli), `bridge_native.py` (die Regeln dafür), `messenger_install.py`
    (richtet libmagic und signal-cli ein; Befehl `aquaticy install-messenger`),
    `addons.py` (Add-ons, Rechte).
  - Plugins: `plugins.py`, Vorprüfung für Code- und Security-Review in `review_scan.py`.
- `tests/` – je Fassung eine Datei (`test_v1122.py` für 11.2.2), dazu Dateien je Thema.
  `tests/ollama_nachbau.py` ist ein nachgebautes Ollama: Damit lassen sich lokale Modelle
  (ohne Denk-Modus, ohne Werkzeuge, zu wenig Speicher) ohne echtes Ollama prüfen.
- `tools/` – `pruefung.py` (Prüfkette), `rundgang.py` (Oberfläche im Browser),
  `bandit-baseline.json` (geprüfte, bekannte Hinweise), Benchmarks.

## Regeln

- **Sicherheitsregeln nie abschwächen.** Das betrifft netguard, injection,
  aiguard, guardrails, auth, sandbox und die Bestätigung vor folgenreichen
  Aktionen. Ein Feature, das daran vorbei müsste, wird nicht gebaut.
- **Tests nie abschwächen, überspringen oder löschen**, um grün zu werden.
  Ändert sich ein Text absichtlich, wird der Test an den neuen Text angepasst;
  ändert sich Verhalten, braucht es einen Grund im Commit.
- **Neue bandit-Hinweise** erst prüfen. Nur ein geprüfter Fehlalarm kommt in die
  Baseline: `bandit -q -r aquaticy -ll -ii -f json -o tools/bandit-baseline.json`
  (danach `metrics` und `generated_at` aus der Datei entfernen).
- **Texte der Oberfläche** stehen deutsch in `aquaticy/webui.html`. Die englische
  Fassung steht im selben File in `const EN = { "deutscher Text": "English" }`;
  der Schlüssel ist der deutsche Text mit zusammengefasstem Leerraum. Wer einen
  Text ändert, ändert beide. Erklärtexte kurz halten; Hinweise zu Einwilligung,
  Datenschutz und Löschen nur mit allen Fakten.
- **Einfache Sprache** (seit 12.4.4 Sol, beide Sprachen): kurze Sätze (höchstens
  15 bis 20 Wörter), aktiv und mit „du“, bekannte Wörter statt Fachwörter (sonst kurz
  erklären), das Wichtigste zuerst, ein Begriff für eine Sache (z. B. immer „Heimnetz“),
  freundlich, ohne „bitte“ in Knöpfen und Hinweisen.
- **Sichtbare Texte** mit echten Umlauten, Kommentare und Bezeichner im Code mit
  ae/oe/ue. Zeilen höchstens 100 Zeichen.
- **Neue Fassung:** `NUMMER` und `NAME` in `tests/test_version.py`, dazu
  `aquaticy/__init__.py`, `pyproject.toml`, `constraints.txt`, README-Titel,
  Rückfall in `webui.html`. Prüfberichte (`TESTREPORT-*.md`) gibt es seit 12.4.4 Sol
  nicht mehr im Repo. `tests/test_version.py` prüft, dass alles zusammenpasst.
- **Leicht bleiben:** Schwere Pakete (LiteLLM, Playwright) erst importieren, wenn
  sie gebraucht werden. Kein neuer Hintergrund-Thread ohne Grund; Abfragen der
  Oberfläche pausieren in versteckten Tabs.
