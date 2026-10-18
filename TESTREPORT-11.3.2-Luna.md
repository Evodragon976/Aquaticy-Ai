# Prüfbericht: 11.3.2 Luna

Stand: 2026-10-18. Grundlage: **11.3.1 Luna**, Commit `42bed44`, Branch `Aquaticy-ai`.
Der Remote-Stand wurde frisch abgerufen; es gab keine neueren Commits oder ungesicherten
lokalen Änderungen. Funktionen und Sicherheitsprüfungen bleiben erhalten.

## Bestätigte Fehler und Korrekturen

1. **Google-Zugriff nach Trennen oder Kontowechsel.** Ein langlebiger Client behielt seine
   Tokens, obwohl ein anderer Client die Verbindung getrennt oder ein anderes Google-Konto
   verbunden hatte. Vor jedem Zugriff wird jetzt der aktuelle verschlüsselte Speicher
   gelesen. Der Verschlüsselungsbaustein wird weiterverwendet, um die Schlüsselableitung
   nicht bei jeder Abfrage zu wiederholen. Verspätete Token-Erneuerungen und Abfragen der
   Kontoadresse dürfen Trennen oder Neuverbinden nicht überschreiben. Gleichzeitige erfolgreiche
   Erneuerungen desselben Kontos werden berücksichtigt.
2. **API-Pfad durch Termin-/Mail-Kennungen veränderbar.** Eingaben mit `../`, Schrägstrichen,
   Escape-Sequenzen, Query, Fragment oder Steuerzeichen gelangten in die URL. Jetzt werden
   ausschließlich begrenzte, einzelne Kennungen zugelassen, auch bei Mail-Metadaten.
   Normale Kennungen und Wiederholungstermine bleiben nutzbar.
3. **Unzuverlässige Google-Token-Datei.** Ungültige Ablaufwerte lösten Abstürze aus oder
   galten trotz ungeeignetem Datentyp als verbunden. Der Leser prüft Typen, endliche
   Ablaufwerte, Größe und JSON-Tiefe. Beschädigte Daten gelten als nicht verbunden.
   Schreiben erfolgt in eine von Anfang an private temporäre Datei und anschließend per
   atomarem Austausch. Die explizite Windows-Rechteprüfung bleibt erhalten und schützt
   bereits die temporäre Datei, bevor Tokens hineingeschrieben werden.
   Ein fehlgeschlagener Austausch erhält die alte Datei; ein fehlgeschlagenes Löschen wird
   nicht mehr stillschweigend als Erfolg behandelt.
4. **Home-Assistant-Zwischenspeicher ohne Größenbegrenzung.** Alte Einträge enthielten
   Zugriffstokens im Klartext und blieben nach Ablauf der Nutzungsfrist liegen. Der Cache
   ist jetzt auf 128 Einträge begrenzt, verwendet Token-Hashes und getrennte Profilbereiche
   und räumt abgelaufene Einträge bei Zugriffen auf. Einstellungsänderungen, Schalten sowie
   Daten-/Kontolöschung verwerfen die betreffenden Zustände. Eine bereits laufende Abfrage
   darf einen verworfenen Cache nicht erneut füllen. Es entsteht kein zusätzlicher Thread.
5. **Fehlerhafte Home-Assistant-Attribute.** Ein einzelnes Gerät mit Text, Zahl oder Liste
   statt eines Attributobjekts brachte die gesamte Zustandsanzeige zum Absturz. Solche
   Attribute werden jetzt wie fehlende Angaben behandelt; die übrigen Geräte bleiben sichtbar.
6. **Markdown-Export durch Quellenadressen veränderbar.** Klammern, Leerzeichen und HTML
   in fremden Adressen konnten Links auftrennen, zusätzliche Links oder aktive HTML-Tags
   erzeugen und normale URLs beschädigen. Quellen-, Produkt- und Bildadressen werden jetzt
   für Markdown kodiert. Die Tests prüfen das Ergebnis mit einem echten Markdown-Parser.
7. **Zu weitgehende Beschreibung von Google-Rechten.** `gmail.compose` wird für Entwürfe
   benötigt, erlaubt bei Google aber auch Senden. Dokumentation und Codekommentare stellen
   jetzt klar, dass Aquaticy nur den Entwurfs-Endpunkt verwendet. Es werden keine neuen
   Rechte und keine Sende-/Löschwerkzeuge hinzugefügt.
8. **Unicode-Zugangscodes führten zu Serverfehlern.** Ein zulässiger Ultra-Code mit Umlaut
   konnte nicht verwendet werden; falsche Unicode-Eingaben für Pro und Ultra brachen
   ebenfalls ab. Im Server-Verbund umgingen nicht-ASCII-Ziffern außerdem die Zählung
   falscher Bestätigungscodes.
   Die Vergleiche bleiben zeitkonstant und verwenden jetzt Bytes. Falsche Codes werden
   abgewiesen und im Verbund wie vorgesehen gezählt; erlaubte Ultra-Codes bleiben nutzbar.

## Prüfungen

- Ausgangsstand: vollständige statische Prüfkette und **123 gezielte Tests** erfolgreich.
- Erste Fehlerreproduktion: **44 fehlgeschlagene und 2 bereits erfolgreiche Fälle**.
- Zusätzliche Reproduktion der Zugangscode-Fehler: **8 fehlgeschlagene Fälle**.
- Gezielte Prüfketten nach Korrekturen: alle fünf Schritte erfolgreich; **208 Tests**
  einschließlich Verbund sowie abschließend **170 Tests** der betroffenen Bereiche.
- **65 neue Regressionstests** in `tests/test_v1132.py`: unter anderem Kontowechsel,
  verspätete Antworten, atomare Schreibfehler, private Dateirechte, Profiltrennung,
  Löschung und Unicode-Codes. Alle 65 sind auch im abschließenden Volllauf erfolgreich.
- Zusätzlicher paralleler Dateitest: **640 Lese-/Schreiboperationen**, keine unvollständigen
  Daten und keine temporären Dateireste.
- Bandit zusätzlich ohne Baseline: die **24 bekannten Hinweise** anhand der Fundstellen
  nachgeprüft (u. a. parametrisierte SQL-Abfragen, bewusst gewählte Server-Eingänge,
  DTD-Abweisung vor XML-Verarbeitung und begrenzte LAN-Abfragen ohne Zugangsdaten).
- Suche nach typischen Schlüsselformaten in versionierten Dateien: ausschließlich
  vorgesehene Testwerte; keine Schlüsselwerte im Prüfprotokoll ausgegeben.
- Abhängigkeitsscan mit `pip-audit` gegen PyPI: keine bekannten Schwachstellen in den
  **95 festgeschriebenen Paketen**. Abhängigkeiten und Bandit-Baseline bleiben unverändert.

Der abschließende Aufruf von `python tools/pruefung.py` endete mit **Rückgabewert 0**:

| Prüfung | Ergebnis |
|---|---|
| ruff | Keine Beanstandungen |
| mypy | Keine Fehler in 69 Modulen |
| Bandit mit unveränderter Baseline | Keine neuen Hinweise |
| JavaScript | Syntax erfolgreich geprüft |
| Gesamte Testsuite | **5.077 bestanden, 12 übersprungen, 0 fehlgeschlagen** (5.089 Tests) |
| Browser-Rundgang und verfügbare Docker-Livetests | Im Volllauf erfolgreich enthalten |
| Wheel und Quellpaket | Erfolgreich; alle 75 Laufzeitdateien bytegleich |
| Installation und Versionsanzeige | Paketmetadaten und CLI melden 11.3.2 Luna |

Die Testsuite brauchte **953 Sekunden**, rund 16 Minuten. Kein Prüfschritt wurde
übersprungen. Die zwölf umgebungsbedingten Testausnahmen wurden anschließend mit `pytest -rs`
einzeln bestätigt: sechs Desktop- und fünf Add-on-Livetests benötigen das hier fehlende
Desktop-Abbild. Der DNS-Rebinding-Vergleich kann seine ungeschützte Kontrollanfrage wegen
des Cloud-Proxys nicht durchführen. Die vorhandenen Markierungen wurden nicht geändert.
Das Quellpaket enthält auch die neuen Regressionen und diesen Prüfbericht.

## Umfang und Grenzen

Die Prüfung umfasst Anmeldung und Sitzungen, Herkunfts- und Anfragegrenzen, Netzschutz,
Bestätigungen vor Aktionen, Verschlüsselung und Löschwege, Einwilligung und die beiden
Quellenspeicher, Google/Home Assistant, Exporte, Add-ons, Archive, Code-Umgebung,
Verbund/Tunnel, Modellkontext und Oberfläche. Automatische Tests ergänzen die manuelle
Prüfung dieser Sicherheitsgrenzen; sie beweisen keine allgemeine Fehlerfreiheit.

Google und Home Assistant werden nachgebildet; es wurden keine echten Konten oder Geräte
verändert. Eine bereits an Google gesendete Anfrage kann durch lokales Trennen nicht
rückwirkend abgebrochen werden. Abgelaufene Home-Assistant-Einträge werden bei der nächsten
Cache-Nutzung entfernt; während Leerlauf gibt es hierfür keinen eigenen Bereinigungsthread.
Der Cache ist unabhängig davon begrenzt und wird beim Löschen des Profils verworfen.
Windows-Rechte werden über den bestehenden Schutzbaustein geprüft; ein echter Windows-
Rechner gehört nicht zu dieser Linux-Umgebung. Die zusätzliche Regression sichert dessen
Aufruf bereits vor dem Schreiben der temporären Datei ab.
