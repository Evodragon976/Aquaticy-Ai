# Prüfbericht 12.2.1 Sol

## Änderungen

Die Bilderstellung wurde auf ausdrücklichen Wunsch vollständig entfernt: kein Menüeintrag,
kein aktivierbarer Chat-Modus, kein Anbieter-Modul, kein Werkzeug-Schema oder Dispatcher,
keine automatische Auswahl eines Bildgenerierungsanbieters und keine Erstellungs-Ereignisse.
Der alte API-Schalter kann die Funktion nicht zurückholen: aktive oder fehlerhafte Werte
werden vor dem Ändern der Chat-Einstellungen mit HTTP 400 abgewiesen. Der Agent bietet das
Werkzeug auch mit konfigurierten Anbieter-Schlüsseln in keinem Modus an; erfundene Aufrufe
werden abgewiesen. Bildanhänge, Vision, öffentliche Bildquellen und bestehende verschlüsselte
Medien bleiben erhalten. Historische KI-Bilder bleiben richtig gekennzeichnet und abrufbar;
es werden keine vorhandenen Nutzerdaten gelöscht. Die bisherigen Schutzregeln gegen
missbräuchliche oder veraltete Werkzeugaufrufe bleiben bestehen.

Die allgemeinen Einstellungen enthalten keine Modellwahl mehr. Haupt-, Vision-, Helfer-
und Code-Modell sowie die Modelladresse stehen im separaten Dialog „Modelle und
Verbindungen“, erreichbar ausschließlich aus dem Modellmenü im Chat. Das Formular speichert
nur seine fünf Modellfelder; die allgemeinen Einstellungen speichern diese nicht nebenbei.
API-Schlüssel bleiben im jeweiligen Add-on. Eigene Modelladressen bleiben für normale
Konten schreibgeschützt, einschließlich serverseitiger Tarifkontrolle.

Auf Handys unter 600 Pixel wird die Kopfzeile nach dem Senden mit einer kurzen Animation
kompakter. „Infos“ klappt Chat-Status und Ortsfilter auf. Im Browser gemessen: 79 auf 49 Pixel
Höhe. Menü, Infos und neuer Chat behalten mindestens 44 × 44 Pixel Trefferfläche. Ein neuer
Chat stellt die ursprüngliche Ansicht wieder her. Einstellungen und andere Chats bleiben
erreichbar; breite Ansichten behalten ihr bisheriges Layout. Reduzierte Bewegung schaltet
die Animation aus. Die englischen Texte und die Dokumentation wurden angepasst.

## Bestätigte Fehler und Schutz

- Ein fehlgeschlagener Modellwechsel konnte bereits den neuen Modellnamen anzeigen und
  einen unbehandelten Promise-Fehler auslösen. Die Anzeige ändert sich jetzt erst nach
  erfolgreichem Speichern, Fehler werden aufgefangen und die Taste wieder freigegeben.
- Die Modellkonfiguration zeigte Erfolg schon vor dem abschließenden Laden des tatsächlichen
  Serverstands. Fehler beim Nachladen wurden nicht aufgefangen. Nun werden Speichern und
  Nachladen getrennt bewertet; nach erfolgreichem Speichern wird ein späterer Ladefehler
  ausdrücklich als solcher angezeigt.
- Ein zusätzlicher Schutz verhindert überlappende Modellwechsel bzw. doppelte Speicherläufe
  aus derselben Oberfläche.
- Die Browserprüfungen verwenden für JavaScript-Prädikate Funktionen statt unter strenger CSP
  nicht erlaubter String-Auswertung. Die Content-Security-Policy bleibt unverändert.
- Der Browser-Testadapter stellte nach einem frühen Modellwechsel die bisherige
  Chat-Kennung nicht wieder her. Er übernimmt nun wie der echte Agent Chat-Kennung und
  Vertrauensgrenze; eine ausdrückliche Browserprüfung sichert die Kennung ab.
- Die Abschnittsnavigation der allgemeinen Einstellungen verwendet ausdrücklich ihre
  eigene Kopfzeile. Der zusätzliche Modell-Dialog kann so die Sprungpositionen nicht
  beeinflussen. Die Browserprüfung misst ebenfalls die richtige Kopfzeile.
- Die Farbprüfung wartet auf die tatsächlichen Zielwerte nach dem weichen Übergang,
  statt unter Last einen Zwischenwert zu prüfen; ihre exakten Farbwerte bleiben gleich.
- Die Anzeige beim Lesen vorhandener Bilder heißt „Bild ansehen“; die entfernte Erstellung
  wird weder als verfügbare Funktion noch als Laufphase angeboten.

Die Tests der ausdrücklich entfernten Anbieterfunktion wurden durch negative Import-,
Werkzeug-, Modus- und API-Regressionen ersetzt. Kontingentprüfungen testen weiterhin die
Abrechnung aktiver Modellaufrufe und Serverarbeit; ungenutzte Bildgenerierungsabrechnung
entfällt. Schutzprüfungen für bestehende Medien, Uploads, Authentifizierung, Herkunft,
Verschlüsselung, Prompt-Injection und andere sensible Werkzeuge bleiben erhalten. Die
bestehenden UI-Tests verwenden den neuen Ort der Modellkonfiguration.

## Validierung

Stand: 20. Oktober 2026. Die vollständige Prüfkette endete mit Rückgabewert 0.

```bash
PYTEST_ADDOPTS="-n 2 --dist loadscope" .venv/bin/python tools/pruefung.py
```

| Prüfung | Ergebnis |
| --- | --- |
| Ruff | Keine Beanstandung |
| Mypy | 72 Quelldateien ohne Fehler |
| Bandit | Keine neuen Hinweise im konfigurierten Sicherheitsscan |
| JavaScript | Ein Skript ohne Syntaxfehler |
| Pytest | 5.442 bestanden, 12 bestehende bedingte Überspringungen, 0 Fehler |
| Browser | Vollständiger Rundgang samt mobilen Ansichten bestanden |

Der abschließende Pytest-Schritt dauerte 661,6 Sekunden. Die gesamte Suite lief mit zwei
pytest-xdist-Prozessen, ohne Testauswahl und ohne zusätzliche manuelle Browserprozesse.
Die zwölf Überspringungen entsprechen genau dem vorherigen Terra-Lauf; es gibt keine neuen.
Die Laufzeitprüfung des Missbrauchsschutzes bestand mit ihrem unveränderten Grenzwert.

Zusätzlich bestanden 612 gezielte Unit- und Integrationstests, die Modellauswahl mit ihren
Fehlerfällen, 62 Geräteprüfungen, 68 kombinierte Modell-/Kontoprüfungen, 92 Prüfungen der
Chatfolge nach einem Modellwechsel sowie 46 Prüfungen für Einstellungen und Design.
Die neue Handyansicht wurde außerdem anhand von Screenshots geprüft. Die abschließende
vollständige Suite prüfte die korrigierte Navigation, den Modell-Dialog, normale Konten und
die mobilen Ansichten erneut.

Modelle und externe Dienste werden in den Tests nachgestellt. Die Browserläufe verwenden
die echte Oberfläche mit Playwright und Chromium; die Tests benötigen keine echten
Anbieter-Schlüssel oder externe Modellaufrufe.
