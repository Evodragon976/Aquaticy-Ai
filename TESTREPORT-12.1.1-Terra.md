# Prüfbericht: 12.1.1 Terra

Grundlage: 12.1.1 Luna, Commit `2ef91a6`, Branch `Aquaticy-ai`.
Stand: 2026-10-19.

## Mehrere Konten mit Ollama

Der Server verarbeitet Konten bereits in unabhängigen Sitzungen und Threads.
Ein neuer Ende-zu-Ende-Test prüft zehn Konten mit gleichzeitig offenen
Antwortstreams: echter Webserver, echte Authentifizierung der Sitzungen,
echtes LiteLLM und ein Ollama-Nachbau über HTTP. Auch der Rechtsprüfer
durchläuft seinen echten Modellweg. Nur die Modellausgaben sind gestellt.
Konten und Sitzungstokens legt der Test mit `AuthStore` an; jede HTTP-Anfrage
wird anschließend durch die reguläre Sitzungsprüfung authentifiziert.
Die bestehenden Grenzen für Registrierung und Anmeldung werden nicht verändert.

## Bestätigte und behobene Fehler

- Gleichzeitige Erstzugriffe konnten denselben Chat-Agenten mehrfach aufbauen
  oder einen unvollständig aufgebauten Agenten sehen. Initialisierung und
  Austausch sind jetzt je Chat gesperrt; andere Chats warten nicht mit.
- Das Laufbuch begrenzte nur seine Einträge: Bei mehr als 32 aktiven Anfragen
  verschwanden Kennungen, während die zugehörigen Threads weiterliefen.
  Volle Chats antworten jetzt vor dem Worker-Start mit HTTP 429 (`busy`).
  Bestehende Läufe bleiben abrufbar; andere Konten können weiterarbeiten.
- Die Speicherbereinigung nach einem Modellfehler traf immer das Standard-Ollama
  und konnte Modelle anderer laufender Chats entladen. Sie verwendet jetzt den
  ausgewählten Endpunkt, unterbleibt bei Cloudfehlern und schützt aktive Aufrufe
  einschließlich der vollständigen Antwortstreams. Erst wenn der Endpunkt frei
  ist, darf bereinigt werden. Die Kontextverkleinerung bleibt erhalten.
- Die Ladeanzeige fragt jetzt ebenfalls den ausgewählten Ollama-Endpunkt ab.
- Modellstreams werden bei Ende und Fehler geschlossen. Ein Stopp beendet ihre
  Verarbeitung beim nächsten empfangenen Teilstück.

## Prüfungen

- Neue Regressionen (`tests/test_v1211_terra.py`): 14 bestanden.
- Zehn Konten mit zehn gleichzeitig offenen Antwortstreams: einmal alle
  vollständig beantwortet, einmal mit Stopp nur des ersten Kontos.
- Getrennte Verläufe, Modellnachrichten, Profildatenbanken, Nutzungszähler und
  Kontingente. Ein ausgeschöpftes Konto sperrt kein anderes.
- Fremde Laufkennung: 404. Fremde Chatkennung: 400. Ohne Sitzung: 401.
  Schreiben mit fremdem Origin: 403.
- Eine vom Rechtsprüfer abgelehnte Anfrage erreicht auch unter paralleler
  Last nicht das Chatmodell; ein anderes Konto erhält seine Antwort.
- Gleichzeitiger Erstaufbau, atomare Warteschlangengrenze, Ablehnung vor dem
  Worker-Start, korrekter Ollama-Endpunkt und Schutz aktiver Modellaufrufe.
- Bereinigungsschutz wird nach Ende, Stopp und Fehlern wieder freigegeben;
  unabhängige Modellserver blockieren sich dabei nicht.
- Ein zusätzlicher Test mit echtem LiteLLM prüft die geschlossene HTTP-Verbindung
  hinter dessen synchronem Stream-Wrapper. Dieser bietet keinen direkten `close()`;
  der Adapter schließt deshalb auch die darin gebundene httpx-Antwort.
- Neue Regressionen und alle sechs Connect-Browserfälle zusammen: 20 bestanden.
- ruff, mypy, bandit und JavaScript-Prüfung: bestanden, keine neuen
  Sicherheitshinweise.

Abschließende vollständige Prüfkette (`python tools/pruefung.py`), Rückgabewert 0:

| Schritt | Ergebnis |
|---|---|
| ruff | keine Beanstandung |
| mypy | keine Fehler, 71 Module |
| bandit | keine neuen Hinweise; bestehende Baseline unverändert |
| JavaScript | keine Syntaxfehler |
| pytest, einschließlich Browser-Rundgang | **5.318 bestanden, 12 übersprungen, 0 fehlgeschlagen** (5.330 Tests, rund 18 Minuten) |

Kein Prüfschritt wurde ausgelassen. Die 12 bedingten Überspringungen stammen
aus bestehenden Tests. Alle 14 neuen Regressionen wurden ausgeführt.
Die Kommandozeile meldet ebenfalls `aquaticy 12.1.1 Terra`.

Im ersten Gesamtlauf: 5.311 bestanden, 12 übersprungen, sechs fehlgeschlagen.
Alle sechs Fehler betrafen denselben Aufbau der Connect-Browsertests:
Der HTTP-Client meldete sich seit 12.0.0 mit einem Browser-User-Agent an,
der Browser übernahm seinen Cookie aber unter einer anderen Kennung. Die
Sitzungsbindung wies das korrekt zurück. Nach Angleichung der Testkennung
laufen alle sechs unveränderten Funktionsprüfungen durch. Die Anwendung
akzeptiert weiterhin keine Sitzung mit fremder Browserkennung.

## Angepasste bestehende Tests

- `test_hardening::test_every_run_is_found_by_its_id` prüft zusätzlich die
  ausdrückliche Ablehnung bei vollem Laufbuch und den Erhalt aller aktiven
  Kennungen. Bisher prüfte er nur die Länge der Liste, nicht die weiterlaufenden
  Threads hinter gelöschten Kennungen.
- `test_agent::test_a_crashed_runner_frees_memory_and_retries` nutzt jetzt ein
  Ollama-Modell. Die automatische Speicherbereinigung soll nach lokalen
  Runnerfehlern weiterhin funktionieren; ein Cloudfehler darf kein lokales
  Modell entladen.
- `tests/test_version.py` nennt die neue Fassung. Kein Test wurde gelöscht oder
  mit einer neuen Skip-Markierung versehen; keine Sicherheitsprüfung wurde abgeschwächt.
- `test_cluster_http::test_connect_in_browser_preserves_code_during_polling`
  verwendet jetzt die Browserkennung und Sprache seines Anmelde-Clients.
  Sämtliche Prüfungen für Polling, Fehler, ungültige Ports, veraltete Antworten,
  Einladungen und versteckte Tabs bleiben erhalten.

## Grenzen

Echte Ollama-Inferenz mit GPU wurde in dieser Umgebung nicht geprüft.
Der Test belegt zehn gleichzeitig verarbeitete Konten und Antwortstreams in der
Anwendung; er misst keine Modellgeschwindigkeit oder GPU-Kapazität. Ollama kann
zusätzlich intern warten. Wirklich parallele Inferenz hängt von
`OLLAMA_NUM_PARALLEL`, Modellgröße, Kontext und verfügbarem Speicher ab.
Der Bereinigungsschutz koordiniert Modellaufrufe innerhalb dieses Aquaticy-Prozesses
je konfigurierter Ollama-Adresse.
Andere Programme, die denselben Ollama-Dienst verwenden, sind darin nicht erfasst.
