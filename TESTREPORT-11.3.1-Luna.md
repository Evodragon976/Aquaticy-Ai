# Prüfbericht: 11.3.1 Luna

Stand: 2026-10-16. Grundlage: **11.3.0 Luna**, Commit `c36f78d`, Branch `Aquaticy-ai`.
Die drei seit 11.2.3 Luna hinzugekommenen Commits wurden vollständig übernommen.

## Bestätigte Fehler und Korrekturen

1. **Kontextgrenzen wurden durch die Mindestgröße überschritten.** Ein Modell mit 512,
   1.024 oder 1.536 trainierten Tokens bekam trotzdem mindestens 2.048. Bei sehr großem
   Speicherbedarf je Token konnte auch die 5-GB-Grenze überschritten werden. Eine harte
   Obergrenze wird jetzt nie durch die Bedienungs-Mindestgröße vergrößert. Oberfläche und
   tatsächlicher Modellaufruf verwenden dieselbe Grenze. Passt nicht einmal ein Token in
   das Limit, wird der Aufruf abgewiesen statt mit einem großen Ersatzwert fortgesetzt.
2. **Unterschiedliche Schichten wurden zu klein berechnet.** Aus einer Liste verschiedener
   Kopfzahlen wurde die größte verwendet; daraus folgte eine zu kleine Schlüssellänge für
   andere Schichten. Die Rechnung erfolgt jetzt je Schicht. Unvollständige KV-Listen
   zählen fehlende Schichten nicht mehr als null, sondern werden konservativ behandelt.
3. **Falscher Ollama-Endpunkt.** Modellauswahl und Startmeldung verwendeten teilweise die
   Adresse des Cloud-Hauptmodells statt der konfigurierten Ollama-Route. Sie benutzen jetzt
   dieselbe Routingfunktion wie der Modellaufruf. Ein eigener `OLLAMA_API_BASE` wird beachtet.
4. **Unbegrenzte und unnötig private Modellantworten.** `/api/show` wurde vollständig
   eingelesen und im Prozess zwischengespeichert, einschließlich Systemtext und Modelfile.
   Die Antwort wird jetzt gestreamt: höchstens 8 MiB, begrenzte HTTP-Dekompression,
   JSON-Tiefe und Gesamtwartezeit. Gespeichert werden nur benötigte Zahlen und Fähigkeiten.
   Systemtexte, Modelfiles und Vorlagen bleiben aus diesem gemeinsamen Zwischenspeicher.
5. **Verspätete Kontextantworten überschrieben die Auswahl.** Bei schnellen Modellwechseln
   konnte eine ältere Anfrage zuletzt ankommen und den Regler für das falsche Modell
   setzen. Nur die neueste Anfrage eines offenen Menüs darf noch den Zustand ändern.
   Auch verspätete Speicherergebnisse verändern keinen inzwischen erneuerten Regler.
6. **Neue Podman-Maschine ohne vorherige Installationsrückfrage.** Der automatische Start
   rief auch `podman machine init` auf. Das kann ein Abbild herunterladen und Platz
   belegen, auch wenn Aquaticy ohne Terminal als Dienst startet. Dieser Weg prüft jetzt
   nur eine vorhandene Maschine und startet sie. Neue Maschinen entstehen weiterhin über
   die bestätigten Installationsschritte bzw. den ausdrücklich gewählten Schalter `--yes`.
7. **Ollama-Standard wurde als berechnetes Fenster angezeigt.** Der Expertenwert `0` lässt
   ausdrücklich Ollama entscheiden. Die Oberfläche zeigte trotzdem eine errechnete
   Größe samt RAM-Angabe. Jetzt steht dort „Ollama-Standard“; die unbekannte tatsächliche
   Größe wird nicht als Messwert ausgegeben. Die Funktion mit `0` bleibt erhalten.

Funktionen, Sicherheitsregeln und bestehende Tests wurden nicht entfernt oder abgeschwächt.
Neue sichtbare Meldungen und der Standardmodus sind deutsch und englisch vorhanden.

## Prüfungen

Die erste Reproduktion bestätigte zehn fehlschlagende Fälle in Kontextrechnung,
Modellrouting und Metadatenverarbeitung. Vier weitere Fälle belegten das automatische
Anlegen einer Podman-Maschine unter macOS und Windows.

| Prüfung | Ergebnis |
|---|---|
| Ausgangsstand, gezielte Prüfkette | Alle fünf Schritte erfolgreich, 150 Tests bestanden |
| Korrekturen, erste gezielte Prüfkette | Alle fünf Schritte erfolgreich, 250 Tests bestanden |
| Erweiterte gezielte Tests einschließlich Versionsprüfung | 260 bestanden, keine übersprungen |
| Neue Regressionstests (`tests/test_v1131.py`) | **24 bestanden**, keine übersprungen |
| Prüfkette (`python tools/pruefung.py`) | Alle fünf Schritte erfolgreich, Rückgabewert 0 |
| Gesamte Testsuite | **5.012 bestanden, 12 übersprungen, keine Fehlschläge** (5.024 Tests) |
| Regler in Chromium | Speichern am Server, Deutsch, Englisch und Handy mit 390 px erfolgreich |
| Paketbau | Wheel und Quellpaket erfolgreich; alle 75 Laufzeitdateien bytegleich geprüft |

Der Netzwerk-Nachbau liefert auch komprimierte Übergrößen. Die Browserlogik wird mit
absichtlich vertauschter Antwortreihenfolge, geschlossenem Menü, Cloud-/lokalem Modell
und beiden Sprachen geprüft. Bestehende Tests für die bestätigte Podman-Installation
bleiben erhalten. Der bisherige Cache-Grenztest ersetzt lediglich seinen HTTP-Nachbau
für `post` durch den nun verwendeten `stream`-Aufruf; seine Prüfungen sind unverändert.
Der zusätzliche echte Browserlauf nutzt einen nachgebauten Ollama-Dienst und echte
Anmeldung, API, Konfigurationsspeicherung und Oberfläche. Es gab keine Skriptfehler.
Der abschließende Volllauf brauchte rund 15 Minuten. ruff meldete keine Beanstandung,
mypy keine Fehler in 69 Modulen, Bandit keine neuen Hinweise; die JavaScript-Syntax
und der vollständige Browser-Rundgang waren ebenfalls erfolgreich. Die Bandit-Baseline
wurde nicht verändert. Abhängigkeiten und feste Paketversionen sind gegenüber dem
bereits geprüften 11.2.3 Luna unverändert.

## Umfang und Grenzen

Geprüft wurden außerdem die neue Podman-Erkennung, Mount- und Proxy-Optionen,
Installation im Terminal, Modellfreigaben und ungültige Home-Assistant-/Lager-Adressen.
Die Korrekturen aus 11.2.3 Luna sind im übernommenen Stand enthalten.

Die 5 GB betreffen den aus bekannten Modellangaben berechneten Kontextspeicher, nicht die
Modellgewichte. Bei unbekanntem Aufbau gilt die bisherige Token-Ersatzgrenze; ihr
Speicherbedarf lässt sich nicht zuverlässig beziffern. `AQUATICY_CONTEXT_TOKENS=0` ist die
weiterhin unterstützte Ausnahme: Dann wählt Ollama sein Fenster ohne diese Begrenzung.
README und Oberfläche stellen diese Fälle ausdrücklich dar.

Externe Modellanbieter, Ollama und Podman auf macOS/Windows werden nachgebildet; es werden
keine echten Pakete auf dem Rechner installiert. Chromium und Docker für die Code-Umgebung
sind verfügbar. Die elf Desktop-/Add-on-Livetests benötigen ein hier fehlendes Zusatzabbild.
Der Cloud-Proxy blockiert außerdem die Kontrollanfrage des DNS-Rebinding-Vergleichs.
