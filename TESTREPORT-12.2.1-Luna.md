# Prüfbericht 12.2.1 Luna

## Änderung

Aufträge werden in Coworker integriert. Eine transaktionale Migration übernimmt bestehende
Zeitpläne, Bilder und Chat-Verweise und entfernt danach die alte Tabelle. Es gibt einen
Taktgeber pro Konto und eine gemeinsame Sperre gegen doppelte Ausführung. Recherche,
Strukturieren, Kamera-, Preis- und Bildbeobachtung einschließlich Belegprüfungen bleiben erhalten.
Feste Zeitpläne sind weiterhin für normale Konten verfügbar. Die Migration wandelt
SQLite-Schalterwerte ausdrücklich in JSON-Booleans um, damit „Strukturieren“ eingeschaltet
oder ausgeschaltet bleibt. Beide Varianten sind im Altdaten-Test abgedeckt.

Coworker erhalten mehr Emojis, einstellbare Notizgrößen und zwei separate, standardmäßig
abgeschaltete Freigaben für relevante Auszüge aus Chats und anderen Coworker-Notizen desselben
Kontos. Notizen, Aufgaben, Verläufe und Aktionsdaten werden profilgebunden verschlüsselt;
Alttexte werden migriert und alte Datenbankseiten bereinigt.

Home-Assistant-Dauerfreigaben benötigen die ausdrückliche Bestätigung des Besitzers und gelten
nur für ein konkretes Gerät und turn_on/turn_off ohne Zusatzdaten. Geschützte Bereiche,
Zielgruppen und Platzhalter sind ausgeschlossen. Sperren, Ultra-Stufe, Verbindung und Token
werden geprüft. Die bestehenden Schutzprüfungen der Werkzeuge laufen weiterhin.

## Bestätigte Fehler und Schutz

Recherchehelfer konnten nicht angebotene Werkzeugnamen aufrufen. Eine Positivliste verhindert
dies jetzt im Code. Coworker-Daten lagen bisher im Klartext; die Migration schützt insbesondere
aus verschlüsselten Chats übernommene Informationen. Beendete Taktgeber brechen ihre Agenten ab;
ein alter CoworkerStore erzeugt eine gelöschte Datenbank nicht erneut. Freigegebene Aktionen
prüfen den aktuellen Tarif und Sperrstatus vor der Ausführung. Eine Einzelfreigabe ist auch
an die geprüfte Home-Assistant-Verbindung gebunden. Regeln, Kontextfreigaben und Bildnotizen
werden unter einer SQLite-Schreibtransaktion gelesen und gespeichert, damit paralleles
Speichern keine widerrufenen Rechte oder neueren Zeitpläne zurücksetzt. Eine Notizgeneration
verhindert, dass laufende Schritte zwischenzeitlich gelöschte Notizen wiederherstellen.

Die bisherigen Zeitplan-API- und Browserprüfungen werden auf die gemeinsame Coworker-Oberfläche
portiert. Die geprüften Funktionen und Sicherheitsgrenzen bleiben erhalten. Die beiden B608-
Markierungen betreffen ausschließlich feste Tabellen- und Spaltennamen aus einer lokalen
Konstantenliste; sämtliche Datenwerte werden als SQL-Parameter gebunden.

## Validierung

Stand: 19. Oktober 2026. Die vollständige Prüfkette endete mit Rückgabewert 0.

```bash
PYTEST_ADDOPTS="-n 2 --dist loadscope" .venv/bin/python tools/pruefung.py
```

Die gleiche gesamte Testsuite lief mit pytest-xdist in zwei Prozessen; keine Auswahl von
Testfällen oder neuen Überspringungen. Testumgebung: Python 3.12, Playwright und Chromium.

| Prüfung | Ergebnis |
| --- | --- |
| Ruff | Keine Beanstandung |
| Mypy | 73 Quelldateien ohne Fehler |
| Bandit | Keine neuen mittleren oder hohen Hinweise |
| JavaScript | Ein Skript ohne Syntaxfehler |
| Pytest | 5.398 bestanden, 12 bestehende bedingte Überspringungen, 0 Fehler |
| Browser | Vollständiger Rundgang samt mobiler Ansichten bestanden |

Zusätzlich bestanden die gezielten Migrations-, Coworker- und Zeitplantests sowie 82
Übersetzungsprüfungen. Die früheren Auftragspruefungen testen nun die entsprechenden
Coworker-Funktionen. Zeitberechnung, Preisvergleich, Angebotsnachweis und Bildlesen sind
im direkten AST-Vergleich mit dem bisherigen Zeitplan-Modul unverändert.

Die Tests stellen Modell-, Netzwerk- und Home-Assistant-Aufrufe nach. Eine echte
Home-Assistant-Installation ist in dieser Umgebung nicht verbunden; ein Schaltversuch
an realen Geräten wurde deshalb nicht durchgeführt.
