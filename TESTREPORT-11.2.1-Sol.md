# Prüfbericht: 11.2.1 Sol

Stand: 2026-10-14. Grundlage: **11.1.0 Luna**, Commit `5aa7e58`, Branch `Aquaticy-ai`.

## Was neu ist

- **Leichter.** Ein laufender Server ohne Benutzer braucht **67 MB statt 222 MB**
  Arbeitsspeicher. LiteLLM (rund 190 MB, 3,5 s Ladezeit) lädt erst, wenn jemand die
  Oberfläche öffnet. Die Modellprüfung kennt die üblichen Anbieter selbst und braucht
  LiteLLM dafür nicht. LiteLLM holt seine Preisliste nicht mehr bei jedem Start von GitHub.
  Höchstens drei Chromium laufen gleichzeitig (`AQUATICY_BROWSER_PARALLEL`), höchstens acht
  Werkzeugaufrufe einer Runde gleichzeitig.
- **Bessere Prüf-Plugins.** `/code-review` und `/security-review` bekommen eine
  Vorprüfung (`aquaticy/review_scan.py`): Rund 30 Regeln für bekannte Muster
  (SQL aus Text, Shell-Befehle, eval, unsichere Deserialisierung, abgeschaltete
  Zertifikatsprüfung, XSS, SSRF, Path Traversal, schwache Hashes, feste Geheimnisse,
  verschluckte Ausnahmen, fehlende Zeitlimits …) mit Datei und Zeile. Das Modell prüft
  jeden Treffer selbst und lässt Fehlalarme weg. Gefundene Geheimnisse erscheinen nur
  gekürzt, und die Antwort rät, sie zu widerrufen. Das Antwortformat nennt jetzt Stelle
  (Datei, Zeile), wie sicher ein Befund ist, und zählt die Befunde je Schwere.
- **Kürzere Erklärtexte.** 29 lange Erklärungen der Oberfläche (Deutsch und Englisch)
  sind im Schnitt 15 % kürzer. Texte zu Einwilligung, Datenschutz, Löschen und
  Rechtsprüfung behalten jede Aussage. Aquaticys Antworten sind nicht betroffen.
- **Stabiler.** Die Typprüfung (`mypy`) läuft jetzt über das ganze Paket ohne Fehler
  (vorher 75). Drei Hintergrund-Schleifen überleben jetzt einen unerwarteten Fehler.
- **Prüfbar für KI-Agenten.** `python tools/pruefung.py` prüft alles mit einem Befehl
  und gibt auf Wunsch einen JSON-Bericht aus. `AGENTS.md` beschreibt Prüfung, Aufbau und
  Regeln. Die Fassung steht in den Tests an einer Stelle (`tests/test_version.py`).

## Gefundene Fehler und ihre Ursache

1. **Hintergrund-Schleifen konnten still sterben.**
   - Auto-Upgrading: Ein kaputter Zeitstempel in der Zustandsdatei beendete den Takt für immer.
   - Verbund-Einladungen: Scheiterte eine Rückfrage im Terminal, kam keine weitere mehr.
   - Cloudflare-Tunnel: Nur zwei Fehlerarten wurden abgefangen. Jede andere beendete den
     Neustart-Takt.

   Alle drei fangen jetzt jeden Fehler ab und machen weiter.
2. **Wetter:** Ein unerwarteter Wettercode (etwa eine Liste) brach die Antwort mit
   `TypeError` ab. Jetzt heißt er „unbekannt“.
3. **Typfehler, die zur Laufzeit hätten knallen können**, unter anderem:
   - `remove_env_keys` bekam womöglich `None`.
   - Ein Konto konnte theoretisch `None` sein, bevor die Sitzung angelegt wurde.
   - Mehrere Variablen in der API wurden mit anderem Typ wiederverwendet.

   Die Schutzwirkung bleibt unverändert, die Fälle sind jetzt ausdrücklich behandelt.
4. **Bei der eigenen Prüfung gefunden (Vorprüfung):** Bestimmte Eingaben, etwa ein sehr
   langes Wort wie `password_password_…`, ließen die Geheimnis-Erkennung quadratisch
   langsam werden: rund 5 Sekunden je Zeile. Mit eingefügtem Code hätte das den Server
   minutenlang beschäftigt. Alle Muster haben jetzt feste Längengrenzen, und geprüft wird
   höchstens 1 MB. Dieselbe Eingabe braucht jetzt 0,04 s für 20 Zeilen, 1 MB im
   schlimmsten Fall unter 1 s.
5. **Bei der eigenen Prüfung gefunden (Prompt):** Die Code-Auszüge der Vorprüfung standen
   außerhalb des Bereichs, der fremde Inhalte kennzeichnet. Präparierter Code hätte so
   Text an eine wirksamere Stelle im Prompt bringen können. Auszüge und Dateinamen werden
   jetzt gesäubert (unsichtbare Zeichen, nachgemachte Chat-Steuerzeichen, Backticks),
   gekürzt und ausdrücklich als zitierter Code markiert.
6. **Während der Arbeit eingeschleppt und vor dem Commit gefunden:** Die neue
   Plattform-Weiche der Server-Sperre nutzte `sys`, ohne es zu importieren. Die neue
   Typprüfung über das ganze Paket hat das sofort gemeldet.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | alle fünf Schritte ohne Beanstandung (Rückgabewert 0) |
| Testsuite (`pytest`) | erster Lauf: 4808 bestanden, 27 übersprungen, 4 Fehlschläge – alle vier prüften absichtlich Geändertes (drei den alten Wortlaut gekürzter Texte, einer den alten Namen „Luna“); danach: **4823 bestanden, 27 übersprungen, keine Fehlschläge** (4850 Tests, 14 Minuten) |
| Neue Tests (`tests/test_v1121.py`) | 87, alle bestanden |
| Stilprüfung (`ruff check aquaticy tests tools`) | keine Beanstandung |
| Typprüfung (`mypy`, ganzes Paket, 68 Dateien) | keine Fehler (vorher 75) |
| Sicherheitsscan (`bandit -ll -ii`) | keine neuen Hinweise; 24 bekannte, geprüfte Fehlalarme in `tools/bandit-baseline.json` (SQL mit festen Spaltennamen, Bindung an alle Netzwerkkarten mit `--lan`, LAN-Gerätecheck ohne Zertifikat) |
| JavaScript der Oberfläche (`node --check`) | ohne Fehler |
| Rundgang durch die Oberfläche im Browser (`tests/test_rundgang.py`) | ohne Beanstandung, lief in der Testsuite mit |
| Speicher eines leeren Servers (`aquaticy web`, gemessen) | 67 MB statt 222 MB, 6 Threads, keine CPU im Leerlauf |
| Vorprüfung gegen feindliche Eingaben | jede Zeile < 0,01 s, 1 MB < 1 s |
| Vorprüfung gegen Aquaticys eigenen Code (55 000 Zeilen) | 2,7 s; nach den Fehlalarm-Filtern nur noch echte Stellen (f-SQL mit Tabellennamen, `verify=False` im LAN-Check, ein fester Salt) |
| Schneller Modellweg gegen LiteLLM | jeder bekannte Anbieter liefert dasselbe Ergebnis wie LiteLLM |

## Sicherheit

- **Keine Sicherheitsregel wurde gelockert.** netguard, Prompt-Injection-Schutz,
  Ai-guard, Rechtsprüfung, Kontenschutz und virtual machine sind unverändert.
- Die Prüf-Plugins bleiben rein verteidigend: finden, belegen, beheben. Die Vorprüfung
  erkennt nur Muster und erzeugt keine Angriffsdaten.
- Der Browser-Grenzwert ändert nichts daran, wohin Chromium darf. Jede Anfrage läuft
  weiter durch netguard.
- Die Fehlermeldung des Tunnels nennt bei unerwarteten Fehlern nur die Art, nie den Text.
  So kann kein Token in die Oberfläche gelangen.

## Grenzen dieser Prüfung

- **Kein echtes Netz und kein echtes Sprachmodell.** Die Plugins wurden mit dem
  zusammengesetzten Prompt geprüft, nicht mit Antworten eines echten Modells.
- **Speicher gemessen auf Linux** mit Python 3.11 und LiteLLM 1.102. Auf anderen Systemen
  weichen die Zahlen ab, das Verhältnis bleibt.
- **Die Vorprüfung ist ein Mustervergleich.** Sie findet nicht alles und meldet auch
  Fehlalarme. Das Modell entscheidet am Ende.
