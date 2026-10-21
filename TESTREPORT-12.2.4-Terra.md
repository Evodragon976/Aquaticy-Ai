# Prüfbericht: 12.2.4 Terra

Stand: 2026-10-21. Grundlage: **12.2.4 Luna**, Commit `32bc635`, Branch `Aquaticy-ai`.
Der Arbeitsbaum war zu Beginn sauber; es gab keine ausstehenden Änderungen zu übernehmen.

## Umfang

Der Ausgangsbestand umfasst rund 69.400 Zeilen in 73 Python- und HTML-Dateien.
Die automatischen Prüfungen erfassen das gesamte Python-Paket und das JavaScript der
Weboberfläche. Zusätzlich wurden sicherheitskritische Datenflüsse manuell untersucht:
Anmeldung und Kontolöschung, Kontentrennung und Schlüssel, HTTP/TLS und Verbund,
Netzschutz und externe Inhalte, Lernspeicher und Einwilligung, Sandbox und Archive,
Coworker-Berechtigungen sowie HTML-Ausgaben. Docker-Konfiguration und Installationshelfer
wurden ebenfalls auf auffällige Eingaben und Grenzen untersucht.

Das ist keine Garantie, jede Zeile manuell geprüft oder sämtliche möglichen Schwachstellen
gefunden zu haben. Bestätigte Fehler wurden vor der Korrektur mit Regressionstests
nachgestellt.

## Bestätigte Fehler und Änderungen

- **Veraltete Passwortfreigabe beim Löschen:** Zwischen Passwortprüfung und Löschung
  konnten laufende Arbeiten beendet und dabei ein paralleler Passwortwechsel abgeschlossen
  werden. Die alte Freigabe konnte danach trotzdem noch Daten oder das Konto löschen.
  Beide Löschwege vergleichen nun den an den Passwortstand gebundenen Nachweis innerhalb
  einer SQLite-Schreibtransaktion, bevor Metadaten, Schlüssel, Lernbeiträge oder Dateien
  gelöscht werden. Die Sperre bleibt bis zum Ende der Dateilöschung bestehen und schützt
  auch gegenüber einem anderen Prozess. Die Webroute verwendet den frisch geprüften
  Kontostand, damit die automatische Migration älterer Passwort-Hashes weiter funktioniert.
  Bei einem zwischenzeitlichen Passwortwechsel antwortet sie mit HTTP 409.
- **Unbegrenzte Verbindungsfäden:** Der Webserver erzeugte für jede TCP-Verbindung einen
  neuen Thread, bevor vollständige HTTP-Header und die vorhandenen Anfragegrenzen geprüft
  werden konnten. Jetzt sind pro Server höchstens 256 aktive Verbindungen zugelassen.
  Weitere HTTP-Verbindungen erhalten eine kurze Antwort mit 503 und `Retry-After`.
  Beim HTTPS-Eingang wird eine überzählige Verbindung vor dem TLS-Handschlag geschlossen;
  dort wird keine unverschlüsselte HTTP-Antwort gesendet. Beendete Verbindungen, Fehler
  im Handler, fehlgeschlagene Threadstarts und gescheiterte TLS-Handschläge geben ihre
  Plätze wieder frei. Parallele Chats und bisherige Lesezeitlimits bleiben erhalten.
- **Prüfurteil nach verdrängtem Modellwechsel:** Während einer Ai-guard-Prüfung konnte eine
  Abschaltungsbeobachtung bereits wieder aus dem begrenzten Speicher verdrängt werden.
  Dann sah der Bereich für den Zwischenspeicher vor und nach dem Aufruf gleich aus,
  obwohl ein Ersatzmodell geurteilt hatte. Ein Änderungszähler verhindert jetzt das
  Speichern dieses Urteils unter dem ursprünglichen Bereich. Das gilt für Nachrichten
  und Antworten. Bereits gespeicherte Urteile anderer Konten bleiben verwendbar;
  Modellfreigaben, getrennte Verbindungsbereiche und die ablehnende Rechtsprüfung bei
  Ausfall bleiben bestehen.
- **Bekannte Paketlücken:** Die Prüfung der 95 festgeschriebenen Pakete mit `pip-audit`
  meldete acht Sicherheitslücken in `aiohttp 3.14.3` und eine im Zertifikatsbestand von
  `certifi 2026.7.22`. Dazu gehören Cookie- und Ressourcenprobleme sowie weiterhin
  vertraute Wurzelzertifikate trotz kompromittierter Zwischenschlüssel. Die feste Liste
  verwendet jetzt `aiohttp 3.14.4` und `certifi 2026.10.19`. Entsprechende Mindestversionen
  in `pyproject.toml` gelten auch ohne die feste Liste. Das bestätigt verwundbare
  Paketversionen; nicht jede gemeldete Serverfunktion von aiohttp wird von Aquaticy genutzt.
  Bei bestehenden Installationen müssen auch die Abhängigkeiten aktualisiert und
  laufende Prozesse neu gestartet beziehungsweise Docker-Images neu gebaut werden.
  Quellen: [aiohttp 3.14.4](https://pypi.org/project/aiohttp/3.14.4/) und
  [certifi-Sicherheitsmeldung](https://github.com/advisories/GHSA-6q48-6c7w-9gw2).

## Prüfung

- Alle fünf neu hinzugefügten Reproduktionsfälle schlugen vor den Korrekturen wie erwartet
  fehl: zwei Löschwege, die Verbindungsgrenze und zwei Ai-guard-Prüfwege.
- Gezielte Prüfungen der ersten Korrekturen: **199 bestanden**, einschließlich zehn
  gleichzeitig chattender Konten mit getrennten Verläufen und Verbrauchswerten.
- Erweiterte Prüfungen von Konten, Datenschutz, Netzwerk und Löschung: **301 bestanden**.
- Release- und Versionsprüfungen nach den Paketupdates: **54 bestanden**, einschließlich
  eines echten lokalen TLS-Aufbaus mit geprüftem Zertifikat und Hostnamen.
- `pip-audit` nach den gezielten Paketupdates: **95 Pakete, keine bekannten Lücken**.
  `uv pip check`: alle installierten Pakete kompatibel. Auflösung der festen Liste
  für Python 3.11 erfolgreich. CLI-Anzeige: `aquaticy 12.2.4 Terra`.
- Syntax der beiden Desktop-Installationshelfer und aller drei Compose-Dateien geprüft.
- Endgültige vollständige Prüfkette mit `python tools/pruefung.py`: **alle fünf Schritte
  bestanden, Rückgabewert 0**. Ruff, mypy über alle 72 Python-Module, Bandit und
  JavaScript-Syntaxprüfung ohne neue Beanstandung. **5.537 Tests: 5.525 bestanden,
  zwölf bestehende bedingte Auslassungen, kein Fehlschlag**; pytest-Laufzeit 695,4 Sekunden.
  Der vollständige Browser-Rundgang bestand ebenfalls.

Der Gesamtlauf verwendete zwei Worker (`-n 2 --dist loadscope --no-loadscope-reorder`).
Eine Fortschrittsanzeige außerhalb des Repositories startete den Browser-Rundgang früh
parallel zu den Python-Prüfungen; sie änderte weder Tests noch deren Bedingungen.
Nach diesem Lauf wurde nur dieser Prüfbericht vervollständigt.

Die **19 neuen Regressionstests** in `tests/test_v1224_terra.py` ergänzen die vorhandenen
Tests und prüfen auch die Wiederverwendung von Verbindungsplätzen nach Erfolg und Fehlern
sowie den Erhalt der Urteile anderer Konten. Es wurden keine
bestehenden Tests gelöscht, ausgelassen oder abgeschwächt und keine Bandit-Baseline oder
Schutzschwelle gelockert. Die Paketnummer in `pyproject.toml` bleibt wie angefordert
`12.2.4`; der Codename und alle aktuellen Release-Anzeigen lauten nun `Terra`.

## Grenzen

Externe Modelle, Ollama und Anbieterfehler werden in der Testsuite nachgestellt.
Echte API-Schlüssel, ein produktiver Tailscale-Verbund oder produktive Home-Assistant-Geräte
sind nicht Teil dieser Prüfung. Eine Verbindungsgrenze begrenzt den Ressourcenverbrauch;
sie garantiert keine Erreichbarkeit bei einer gezielten Überlastung.
