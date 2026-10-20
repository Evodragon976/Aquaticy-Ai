# Prüfbericht: 12.2.4 Luna

Stand: 2026-10-20. Grundlage: **12.2.3 Astra**, Commit `1d4999f`, Branch `Aquaticy-ai`.

## Bestätigte Fehler und Änderungen

- **Kontentrennung bei Modellabschaltungen:** Die globale Laufzeitliste konnte nach einem
  Fehler eines Kontos dasselbe Modell für andere Konten und andere Endpunkte sperren.
  Beobachtete Abschaltungen gelten jetzt nur für den gehashten Bereich aus Kontodatenpfad,
  Modell und aktuellen Aufrufargumenten einschließlich Schlüssel und Endpunkt. Geheimnisse
  liegen darin nicht im Klartext. Die feste Liste bekannter abgeschalteter NVIDIA-Modelle
  bleibt bestehen. Der Speicher für Laufzeitbeobachtungen ist auf 256 Modelle mit jeweils
  64 Verbindungen begrenzt; die ältesten Einträge werden bei Bedarf verdrängt.
- **Ersatz in allen Chat-Modi:** Automatische Wahl, Ausweichmodell und die gemerkte Wahl im
  Pro-/Code-Modus gingen am Ersatz vorbei. Jetzt prüfen alle Wege auf einen Ersatz beim
  selben Anbieter aus dessen bekannter Liste. Ein abgeschaltetes Code-Modell bevorzugt
  dabei ein verfügbares Code-Modell vor einem allgemeinen Hauptmodell.
- **Gleichzeitige Modellwechsel:** Ein laufender Aufruf behält sein Modell für Berechtigungen,
  Parameter und Abrechnung. Ein parallel erkanntes „410 Gone“ darf bei der Fehlerbehandlung
  nicht versehentlich das bereits gewählte gesunde Ersatzmodell sperren.
- **Leere Anbieterlisten:** Eine fehlende Liste wird von einer bekannten leeren oder
  unbrauchbaren Liste unterschieden. Die zweite führt weder zu unbestätigten Standardmodellen
  noch zum erneuten Einfügen eines aktuell eingestellten, darin nicht verfügbaren Modells.
  Die Auswahl bleibt auch mit einem weiter hinten gelisteten aktuellen Modell auf acht
  Einträge je Anbieter begrenzt. Das schnelle Modell wird je Anbieter einmal bestimmt,
  statt die Liste für jede Beschriftung erneut zu lesen.
- **Add-ons und AI Council:** Die vom API-Endpunkt zusätzlich angehängte Add-on-Liste konnte
  abgeschaltete Modelle und weitere Einträge über der Grenze wieder einfügen. Beide Listen
  verwenden jetzt dieselbe Auswahl. Der Council wählt seine Mitglieder aus den verbleibenden
  Modellen und kann bei einer gerade erkannten Abschaltung zum Ersatz übergehen.
- **Sicherheitsprüfungen:** Rechtsprüfung und Ai-guard berücksichtigen einen gerade erkannten
  Ersatz noch im selben Durchlauf. Der Ai-guard-Zwischenspeicher berücksichtigt auch Modell,
  Schlüssel, Freigabe und Endpunkt des möglichen Haupt-/Ersatzmodells.
  Ein Urteil nach einer frisch erkannten Abschaltung wird nicht unter dem ursprünglichen
  Modellbereich gespeichert. Ändert sich die Verbindung während einer Ai-guard-Prüfung,
  wird das Urteil ebenfalls nicht unter dem veralteten Bereich gemerkt. Das verhindert,
  dass ein Urteil nach Verdrängung einer Abschaltungsbeobachtung trotz inzwischen entzogener
  Modellfreigabe wiederverwendet wird; Anfragen und Antworten sind beide abgedeckt.
- **Fehlererkennung und Datenschutz:** Ein ausdrücklicher anderer HTTP-Status überstimmt
  Wörter wie „end of life“ im Fehlertext. Die Geheimnisfilterung entfernt längere Schlüssel
  vor deren kürzeren Präfixen und erkennt auch großgeschriebene HTTP(S)-Adressen.

## Sicherheitsgrenzen

Ohne eindeutiges Rechtsurteil bleibt eine Anfrage abgelehnt. Berechtigungen, Kontingente,
Netzschutz, Prompt-Injection-Abwehr, Sandbox und Bestätigungen folgenreicher Aktionen
bleiben bestehen. Es wird kein Feature entfernt und kein Anbieter ungefragt gewechselt.

## Prüfung

| Prüfung | Ergebnis |
|---|---|
| Release-, Cache- und Sicherheitsregressionen sowie Versionskonsistenz | 141 bestanden |
| Konten-, Add-on- und Council-Integration | 78 bestanden |
| Speichertests einschließlich Windows-Simulation | 20 bestanden |
| Ruff, mypy, Bandit, JavaScript | bestanden; keine neuen Bandit-Hinweise |
| Vollständige Prüfkette einschließlich Browser | alle fünf Schritte bestanden, Rückgabewert 0; 5518 Tests: **5506 bestanden, 12 bestehende bedingte Auslassungen, kein Fehlschlag** (699,2 s für pytest) |

33 neue Regressionstests in `tests/test_v1224_luna.py` und `tests/test_own_keys.py` decken
die behobenen Fälle einschließlich Konten-, Schlüssel- und
Endpunktwechsel, paralleler Abschaltung, aller Chat-Modi sowie weiterhin ablehnender
Sicherheitsprüfungen bei Ausfall aller Ersatzmodelle ab.

Die drei bestehenden Laufzeitbeobachtungstests in `tests/test_v1223_astra.py` verwenden nun
den Verbindungsbereich und die begrenzte Datenstruktur. Ihre bisherigen Aussagen zur
Erkennung, zum unmittelbaren Ersatz und zur Buchung bleiben erhalten; zusätzlich prüfen
die neuen Tests die Trennung zwischen Konten. Es wurden keine Tests gelöscht, keine
zusätzlichen Auslassungen eingeführt und keine Schutzschwellen verändert.

Der Testanbieter in `tests/test_own_keys.py` nennt seine verfügbaren Modelle nun ausdrücklich:
eine bekannte leere Liste bedeutet jetzt tatsächlich „keine Modelle“. Sämtliche bisherigen
Prüfungen der Kontentrennung und Schlüsselgeheimhaltung bleiben bestehen. Die Council-Tests
in `tests/test_linked.py` verwenden als verfügbaren NVIDIA-Prüfer das aktuelle Nemotron-Modell
anstelle des bereits bekannten abgeschalteten Modells; Runden, Rollen und Urteile werden
weiter vollständig geprüft. Ein neuer API-Test prüft, dass abgeschaltete Add-on-Modelle weder
in der normalen noch in der Pro-/Code-Auswahl wieder auftauchen.

Der erste Gesamtlauf wurde nach 4877 bestandenen Tests durch die zusätzliche, außerhalb
des Repositories liegende Fortschrittsanzeige abgebrochen: Während der Windows-Simulation
versuchte sie, eine `WindowsPath` auf Linux zu erzeugen. Die Anzeige verwendet jetzt einen
vorab bestimmten Dateipfad. Alle 20 Speichertests liefen damit durch. Anwendungscode und
bestehende Tests wurden für diesen Fehler der Messhilfe nicht geändert. Der Gesamtlauf
wurde vollständig wiederholt, nicht durch Teilergebnisse ersetzt.

Der darauffolgende Gesamtlauf bestand mit 5503 bestandenen Tests, 12 bestehenden bedingten
Auslassungen und ohne Fehlschlag einschließlich Browser-Rundgang. Die letzte Nachprüfung
ergab zusätzlich den oben beschriebenen Cache-Fall nach Entzug einer Modellfreigabe. Für
dessen Korrektur wurden drei weitere Tests ergänzt; die betroffenen 141 Tests und sämtliche
statischen Prüfungen bestanden. Die endgültige Fassung bestand den weiteren vollständigen
Gesamtlauf mit den oben genannten **5506 bestandenen Tests**, einschließlich aller 33 neuen
Regressionstests und des Browser-Rundgangs. Dabei begann der Browser-Rundgang parallel zu
den Python-Prüfungen; weder Testumfang noch Bedingungen oder Schutzschwellen wurden verändert.

## Grenzen

Anbieterfehler und Modellwechsel werden ohne echte Schlüssel nachgestellt. Eine Live-Abfrage
von NVIDIA oder Mistral ist nicht Teil dieser Prüfung. Anbieterlisten entsprechen weiterhin
dem zuletzt beim Einrichten beziehungsweise Aktualisieren abgerufenen Stand.
