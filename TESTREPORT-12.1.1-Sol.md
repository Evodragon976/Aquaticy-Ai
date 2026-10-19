# Prüfbericht – 12.1.1 Sol

Stand: 19. Oktober 2026. Ausgangspunkt: `48c57a0` (12.1.1 Terra).

## Änderungen

- `aquaticy setup` prüft Ollama direkt zu Beginn, installiert es bei Bedarf und
  richtet Parallelbetrieb ein. Die lokale Modellauswahl verwendet dieses Ergebnis
  weiter, ohne einen zweiten Dienstneustart auszulösen. `install-model` verwendet
  denselben Ablauf. Reiner Cloudbetrieb bleibt mit `setup --no-ollama` möglich.
- Downloads und mögliche Dienstneustarts bleiben bestätigungspflichtig;
  `--yes` ist die ausdrückliche Vorabbestätigung. Der Python-Paketmanager führt
  keine privilegierten Installationshaken aus.
- Standard: zwei parallele Modellaufrufe, weitere Anfragen warten bei Ollama.
  Gültige größere Einstellungen bleiben erhalten. Die bisherigen
  Warteschlangen-, Konten-, Speicherbereinigungs- und Abbruchregeln bleiben bestehen.
- Linux: eigenes systemd-Drop-in, auch für Benutzerdienste, Neustart und Prüfung
  der wirksamen Umgebung. Keine Änderungen an anderen Dienstregeln oder Netzwerkfreigaben.
- macOS: persistente Änderung des Homebrew-LaunchAgents, bestehende Optionen bleiben
  erhalten. Eine unbekannte laufende native App wird nicht ungeprüft beendet.
- Windows: Benutzerumgebung dauerhaft speichern, Neustart nur für den eigenen
  nach Programmpfad geprüften Ollama-Prozess. Frisch per winget installierte
  Programme werden auch ohne neues Terminal gefunden.
- Eigene `ollama serve`-Starts bekommen die Parallelität bei jedem Start erneut.
  Auch der Terminal-Chat startet ein ruhendes lokales Ollama bei Bedarf.

## Bestätigte Fehler und Sicherheitsgrenzen

- Der Linux-Installer nutzte `curl | sh`: Ein fehlgeschlagener oder unvollständiger
  Download konnte bereits ausgeführt werden oder Erfolg melden. Jetzt wird erst
  vollständig per HTTPS heruntergeladen und nur bei Erfolg ausgeführt; temporäre
  Dateien werden entfernt. Fehlende Programme und Zeitüberschreitungen werden abgefangen.
- Eigene Serverstarts übernahmen `OLLAMA_HOST` ungeprüft. Jetzt wird der angefragte
  lokale Host und Port gesetzt; entfernte URLs, Zugangsdaten und URL-Pfade lösen
  keinen lokalen Serverstart aus. Bestehende fremde Dienste werden nicht umgestellt.
- Der Modell-Download konnte durch geerbtes `OLLAMA_HOST` einen anderen Server als
  die Einrichtung ansprechen. Sein Ziel wird jetzt ausdrücklich angegeben.
- Modellnamen mit führendem Minus oder Steuerzeichen werden vor dem Prozessstart
  abgelehnt; sie können keine zusätzlichen CLI-Optionen einschleusen.
- HTTP 200 allein galt als erreichbares Ollama. Jetzt muss auch die erwartete
  JSON-Modellliste vorhanden sein.
- Dienstfehler geben keine möglicherweise geheimen Dienstumgebungen aus. Befehle
  zur Konfiguration verwenden keine Shell. Windows erhält den Programmpfad als
  Daten statt als interpolierten PowerShell-Code. Benutzerdateien werden atomar
  mit Modus 0600 geschrieben; symbolischen Dateizielen wird nicht gefolgt.
- Nach einem fehlgeschlagenen verwalteten Dienststart wird kein zweiter Server
  gestartet. Überschreibende systemd-Regeln werden als Fehler gemeldet.

## Prüfung

- Neue Regressionen in `tests/test_v1211_sol.py`: 54 Testfälle zu Erkennung,
  Erstinstallation, vorhandener Installation, kompletter Einrichtung, Cloudbetrieb,
  Bestätigung, Dienstrechten, widersprechenden Einstellungen, Prozessgrenzen,
  Dateischutz und kontrollierten Fehlern.
- Gezielte vollständige Prüfkette: ruff, mypy, bandit, JavaScript und **246 Tests
  bestanden**, keine Überspringungen oder Fehler. Darin sind die zehn parallelen
  Konten aus `test_v1211_terra.py` und die bisherigen lokalen Modelltests enthalten.
- Die Fake-Ollama-Fixture in `tests/test_cli.py` stellt zusätzlich die neue externe
  Dienstkonfiguration nach. Sämtliche bisherigen Funktionsprüfungen bleiben erhalten;
  die Dienstkonfiguration wird separat mit ihren Erfolgs- und Fehlerpfaden geprüft.
- Keine Tests wurden gelöscht, abgeschwächt oder zusätzlich übersprungen.
  Die Sicherheitsbaseline bleibt unverändert.

Erster Gesamtlauf: 5.367 bestanden, 12 bestehende Überspringungen, ein Fehler
im Browser-Rundgang. Betroffen war ausschließlich die Positionsmessung des
Rückfragenzählers während der Öffnungsanimation: Zähler und Fenster wurden in
getrennten Browser-Aufrufen und damit möglicherweise in verschiedenen Frames
gemessen. Ein zusätzlicher kompletter Browser-Rundgang bestand alle 426 Prüfungen.

Der Messfehler wurde mit der echten CSS-Animation mit verlängerter Dauer und auseinanderliegenden
Messzeitpunkten gezielt nachgestellt: fünf von fünf getrennten Messungen meldeten
eine falsche Position, gemeinsame Messungen keinen Fehler. Der Rundgang wartet nun
auf das Animationsende und liest beide Kanten im selben Browser-Aufruf. Die
Positionsanforderung und ihr Abstand von 40 Pixeln bleiben unverändert; keine
Animation und kein Bedienungselement wurden entfernt.

Ein weiterer Gesamtlauf nach der Korrektur der Browsermessung bestand mit
5.368 erfolgreichen Tests und zwölf bestehenden Überspringungen.
Bei der Abschlusskontrolle wurde außerdem eine zunächst eingeführte Begrenzung
auf 64 parallele Aufrufe entfernt: vorhandene gültige größere Betreiberwerte,
etwa 128, bleiben erhalten. Vier zusätzliche Regressionen prüfen diesen Erhalt.
Die gezielte Prüfkette bestand danach mit allen 246 Tests.

Abschließender vollständiger Lauf für den letzten Stand
(`.venv/bin/python tools/pruefung.py`), Rückgabewert **0**:

| Schritt | Ergebnis |
|---|---|
| ruff | keine Beanstandung |
| mypy | keine Fehler in 72 Modulen |
| bandit | keine neuen Hinweise; Baseline unverändert |
| JavaScript | keine Syntaxfehler |
| pytest einschließlich Browser-Rundgang | **5.372 bestanden, 12 übersprungen, 0 fehlgeschlagen** (5.384 Tests, rund 18 Minuten) |

Alle fünf Prüfschritte wurden ausgeführt. Die zwölf bedingten Überspringungen
stammen aus bestehenden Tests. Alle 54 neuen Regressionen wurden ausgeführt.
Die Kommandozeile und die Oberfläche nennen `12.1.1 Sol`.


## Aussagegrenzen

Die Systemdienst-, Installer- und Windows/macOS-Abläufe werden mit nachgestellten
Systembefehlen geprüft; reale Verwalterrechte, UAC und Plattformdienste wurden
hier nicht verändert. Ein fehlgeschlagener HTTPS-Download wird zusätzlich mit
einem echten Shell-Prozess und einem gestellten curl geprüft.
Die vorhandenen Mehrnutzertests verwenden echtes HTTP, Konten und LiteLLM mit
einem nachgebauten Ollama. Ein reales Ollama-Modell oder eine GPU stehen hier
nicht für Durchsatzmessungen zur Verfügung. Zwei konfigurierte Plätze garantieren
keine feste Antwortgeschwindigkeit oder ausreichenden Speicher für jedes Modell.

Systemd-System- und Benutzerdienste, Homebrew und winget sind automatisierbar.
Für unbekannte laufende Dienste und macOS ohne Homebrew bleibt ein konkreter
Hinweis erforderlich. Sicherheits- und Betriebssystemgrenzen werden dafür nicht
abgeschaltet. Änderungen am Dienst erfordern weiterhin die Rechte des Betreibers.
