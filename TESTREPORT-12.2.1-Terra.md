# Prüfbericht 12.2.1 Terra

## Änderungen

„Erlauben“ steht direkt in der Coworker-Regel „Im Haus etwas schalten“. Der separate
Bereich „Home-Assistant-Dauerfreigaben“ entfällt. Die ausdrückliche Besitzerfreigabe gilt
nur für einzelne Lichter, Schalter, Lüfter, Eingabeschalter und Mediengeräte mit
`turn_on`/`turn_off`, ohne Zusatzdaten. Sie benötigt Ultra, eine konfigurierte Verbindung
und aktiviertes Schalten. Die gespeicherte Bindung an Adresse und Token wird vor jedem
Aufruf gegen die aktuellen Einstellungen geprüft. Ein Widerruf oder Tarifwechsel wird
auch in laufenden Sitzungen berücksichtigt. Geschützte Geräte, andere Dienste,
Gruppenziele und Zusatzdaten bleiben einzeln bestätigungspflichtig. Alle weiteren
Werkzeugprüfungen bleiben aktiv. Alte Einzelfreigaben werden entfernt und niemals
stillschweigend auf die gesamte Kategorie ausgeweitet; der Standard bleibt „Fragen“.

Unter „Aufgabe ändern“ lässt sich ein Rhythmus von 30 Sekunden, 1, 5, 10 oder 20 Minuten,
1 oder 4 Stunden oder einmal täglich speichern. Die Abstände gelten nach Abschluss des
letzten Laufs. Automatische Planung und die bisherigen festen Zeitpläne bleiben auswählbar.
Taktgeber, Sperre gegen doppelte Läufe, Kontingente und Tagespensum bleiben bestehen.
Häufige Recherchen verwenden denselben Chat, statt mit jedem Lauf einen neuen anzulegen.
Eine wartende oder lange laufende Aufgabe kann den tatsächlichen Start verzögern.

Der Merkzettel-Button über Einstellungen entfällt; `/notes` und bestehende Notizen bleiben
verfügbar. Dekorative Emojis außerhalb der Coworker-Funktion und der Handschlag vor dem
Coworker-Button entfallen. Add-on- und Befehlslisten zeigen keine Plugin-Emojis mehr.
Funktionale, einfarbige Bedienelemente bleiben sichtbar, einschließlich eines SVG-Symbols
zum Anhängen auf kleinen Bildschirmen. Deutsche und englische Texte wurden angepasst.

## Bestätigte Fehler und Sicherheitsprüfung

- Zeitplanänderungen konnten eine bestehende Kontingentpause aufheben. Sowohl feste
  Zeitplanänderungen als auch die neue Rhythmusauswahl erhalten die Sperrzeit.
- Ein laufender Schritt darf einen gerade geänderten Rhythmus nicht zurücksetzen.
  Eine Zeitplangeneration und eine atomare Lese-/Schreibtransaktion sichern das ab.
- Geplante Recherche bot `research_subtasks` an, blockierte aber den tatsächlichen
  Werkzeugaufruf. Die Ausnahme gilt jetzt ausschließlich für geplante Recherche;
  adaptive Coworker, Beobachtungen und nicht angebotene Schreibwerkzeuge bleiben gesperrt.
- Bei „Erlauben“ im Haus gibt es keinen allgemeinen Durchgriff auf geschützte Aktionen.
  Nur die enge Positivliste darf automatisch laufen. Alle anderen Aufrufe landen in der
  bestehenden Einzelfreigabe; „Sperren“ hat Vorrang.
- Kurze geplante Recherchen behalten Tagesgrenzen und machen bei ausgeschöpftem Kontingent,
  technischen Fehlern oder nicht erreichbarem Rechtsprüfer eine Pause.
- Die bisherigen Prüfungen für Kontentrennung, Verschlüsselung, Notizlöschung während
  laufender Schritte, Prompt-Injection, Authentifizierung, Ursprungskontrolle und
  Freigaben gegen die richtige Home-Assistant-Verbindung bleiben erhalten.

Die früheren Tests der entfernten Geräte-Freigabeoberfläche prüfen jetzt die ausdrücklich
gewünschte Regelzeile. Die erweiterte Erlaubnis für andere sichere Einzelgeräte und
`turn_off` ist absichtlich; geschützte und mehrdeutige Aufrufe werden weiter negativ geprüft.
Der bestehende Test der Ultra-Hinweise prüft die gleichen drei Hinweise ohne Schloss-Emoji.
Kein Sicherheitstest wurde entfernt oder übersprungen.

## Validierung

Stand: 20. Oktober 2026. Die vollständige Prüfkette endete mit Rückgabewert 0.

```bash
PYTEST_ADDOPTS="-n 2 --dist loadscope" .venv/bin/python tools/pruefung.py
```

Die gesamte Testsuite lief mit zwei pytest-xdist-Prozessen, ohne Testauswahl oder neue
Überspringungen. Testumgebung: Python 3.12, Playwright und Chromium.

| Prüfung | Ergebnis |
| --- | --- |
| Ruff | Keine Beanstandung |
| Mypy | 73 Quelldateien ohne Fehler |
| Bandit | Keine neuen Hinweise im konfigurierten Sicherheitsscan |
| JavaScript | Ein Skript ohne Syntaxfehler |
| Pytest | 5.436 bestanden, 12 bestehende bedingte Überspringungen, 0 Fehler |
| Browser | Vollständiger Rundgang samt mobiler Ansichten bestanden |

Der Pytest-Schritt dauerte 641,6 Sekunden. Alle 37 neuen Terra-Regressionen bestanden auch
in der vollständigen Suite. Zusätzlich bestanden 90 gezielte Abschlussprüfungen, sechs
Übersetzungsprüfungen und der fokussierte Browserrundgang mit 24 Prüfungen und leerer
Fehlerkonsole. Die ergänzten Übersetzungen wurden separat auf Verwendung und JavaScript-
Syntax geprüft und waren beim vollständigen Browserlauf bereits enthalten.

Modell-, Netzwerk- und Home-Assistant-Antworten werden in den Tests gestellt. In dieser
Umgebung ist keine echte Home-Assistant-Installation verbunden; reale Geräte wurden nicht
angesteuert. Die Abstände werden mit kontrollierten Zeitpunkten und echten Agentenläufen
gegen gestellte Modelle geprüft, ohne für jeden Tagesrhythmus einen Tag zu warten.
