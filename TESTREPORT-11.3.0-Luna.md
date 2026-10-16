# Prüfbericht: 11.3.0 Luna

Stand: 2026-10-16. Grundlage: **11.2.3 Luna**, Commit `efe8a8e`, Branch `Aquaticy-ai`.

## Neu

1. **Kontextfenster in der Modellauswahl.** Ist ein lokales Modell gewählt, steht unter der
   Liste ein Regler. Er stellt ein, wie viel vom Gespräch das Modell auf einmal überblickt,
   und zeigt den Arbeitsspeicher dazu („16.384 Tokens · ≈ 3 GB RAM“).
   - **Höchstens 5 GB.** Aquaticy fragt Ollama nach dem Aufbau des Modells (Schichten,
     KV-Köpfe, Schlüssellänge) und rechnet: Schichten × KV-Köpfe × (Schlüssel + Wert) × 2 Byte
     je Token. Daraus folgt die Obergrenze, abgerundet auf 1024 und nie über der trainierten
     Länge. Beispiele: qwen2.5-coder:14b 26.624 Tokens (4,9 GB), qwen3:8b 35.840,
     gemma3:4b 37.888.
   - **Am Server erzwungen**, bei jedem Aufruf eines lokalen Modells – egal ob der Wert vom
     Regler, aus den Einstellungen oder aus der Umgebung kommt. Ein Wunsch von 2.000.000
     Tokens wird zu 26.624. Das Kürzen des Verlaufs rechnet mit demselben Fenster.
   - Nennt Ollama den Aufbau nicht, gilt der bisherige Standard (16.384).
   - Normale Konten bleiben zusätzlich bei ihrer Obergrenze. Bei Cloud-Modellen gibt es
     nichts zu stellen; der Regler ist dann nicht da.
2. **Nur Modelle, die wirklich antworten.** Die Modellauswahl (Normal, Pro, Code) zeigt
   - ein Cloud-Modell nur mit Schlüssel (eigener, gestellter, allgemeiner, verknüpftes Konto)
     oder eingetragener Adresse (LM Studio, Proxy),
   - ein lokales Modell nur, wenn es in Ollama installiert ist.

   Bis 11.2.3 stand das voreingestellte Mistral als „Aktuell eingestellt“ in der Liste, auch
   ohne Mistral-Schlüssel. Ebenso ein von Hand eingetragenes Code-Modell ohne Schlüssel und
   eine in Ollama gelöschte Auto-Upgrading-Fassung. Steht oben ein Cloud-Modell ohne
   Schlüssel, heißt es dort jetzt „Modell wählen“.
3. **Ollama bei jedem Start.** `aquaticy web` zeigt, welche Modelle Ollama gerade hat. Ist das
   eingestellte Modell lokal und Ollama installiert, aber aus, wird es gestartet (nur auf
   diesem Rechner). Fehlt das eingestellte Modell in Ollama, steht das da. Die Auswahl fragt
   Ollama außerdem bei jedem Öffnen neu: Ein eben mit `ollama pull` geholtes Modell steht
   sofort da.

## Gefundene Fehler

Gesucht wurde vor allem dort, wo Fehler eher entstehen: Eingaben von außen, Antworten
fremder Server, abgerissene Verbindungen, neue Python-Fassung, Texte zweier Sprachen.

1. **Abgerissene Verbindung = Traceback im Terminal.** Schloss ein Gerät die Verbindung
   (Handy schläft ein, Tailscale wechselt), schrieb der Server einen ganzen Traceback
   (`ConnectionResetError: [Errno 104]`). Jetzt: Abbrüche bleiben still, andere Fehler eine
   Zeile ohne Inhalt („[Verbindung] 10.0.0.7: RuntimeError“).
2. **Kaputte Adresse bei Home Assistant und Lagerverwaltung = HTTP 500.** Gefunden mit
   Fuzzing aller API-Routen: Eine Adresse wie `[1, 'a', None]`, mit Steuerzeichen oder einem
   Port außerhalb des Bereichs warf beim Testen der Verbindung eine Ausnahme. Jetzt eine klare
   Meldung („Die Adresse ist ungültig.“).
3. **Auto-Upgrading-Fassungen ohne Modell** standen in der Auswahl, auch wenn sie in Ollama
   gelöscht waren (siehe oben).
4. **Seltsame Antworten von Ollama.** JSON darf `NaN` und `Infinity` enthalten; daran wäre die
   neue Rechnung gescheitert. Negative Angaben hätten ein riesiges Fenster ergeben. Beides
   zählt jetzt als „unbekannt“.
5. **Merkliste ohne Grenze.** Jeder Modellname aus einer Anfrage wäre ein Eintrag für immer
   geworden. Jetzt höchstens 256.
6. **Sichtbare Texte.** Beschreibungen lokaler Modelle mit „ae/oe/ue“ („Sehr zuverlaessig“),
   und die Modellauswahl hatte auf Englisch deutsche Beschreibungen. Rund 40 neue englische
   Einträge und Muster („12 GB auf deinem Rechner“ → „12 GB on your computer“). „All holes“
   heißt jetzt „All vulnerabilities“.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | alle fünf Schritte ohne Beanstandung (Rückgabewert 0) |
| Testsuite (`pytest`) | erster Volllauf: 1 Fehlschlag (alter Test erwartete 32.768 Tokens ohne Speicherprüfung, siehe „Geänderte Tests“). Danach: **4973 bestanden, 27 übersprungen, keine Fehlschläge** (5000 Tests, 17 Minuten) |
| Python 3.14.8 (ganze Testsuite) | 4937 bestanden, 27 übersprungen, 1 Fehlschlag – der kam vom Ändern einer Datei während des Laufs (`inspect.getsource`); einzeln unter 3.14.8 bestanden |
| Fuzzing aller API-Routen, nicht angemeldet | jede Route mit GET/POST/DELETE und kaputten Werten (leer, riesig, Steuerzeichen, Listen, Pfade): nach den Korrekturen kein HTTP 500 |
| Fuzzing angemeldet (Ultra, im Browser) | dasselbe mit Sitzung: kein HTTP 500, die Sitzung bleibt gültig |
| Abgerissene Verbindung (RST) | kein Traceback, keine Ausgabe |
| Regler im Browser (Deutsch, Englisch, Handy 390 px) | richtiger Wert, Grenze 26.624, Speicher daneben, Speichern mit Meldung, nichts ragt heraus |
| Neue Tests (`tests/test_v1130.py`) | 35, alle bestanden |

## Sicherheit

- **`/api/context`** liegt hinter Anmeldung wie alle `/api/`-Routen. Ein Modellname aus der
  Anfrage muss zu `^[A-Za-z0-9_.:/@+-]{1,200}$` passen, sonst gilt das eingestellte Modell.
  Gefragt wird nur das Ollama, das ohnehin zum Modell gehört; die Antwort nennt nur Zahlen.
- **Ollama starten** nur auf diesem Rechner (localhost), nie auf einem fremden.
- Das Kontextfenster kann nur kleiner werden, nie über die Grenze des Kontos.
- Keine Sicherheitsregel gelockert. bandit: keine neuen Hinweise.

## Geänderte Tests

- `tests/test_web.py::test_the_model_list_offers_what_actually_works` erwartete das
  voreingestellte Mistral ohne Schlüssel in der Liste. Genau das soll nicht mehr sein; der
  Test prüft jetzt beides: ohne Schlüssel nicht da, mit Schlüssel da.
- `tests/test_agent.py`: Die beiden Tests zum von Hand eingetragenen Modell bekommen einen
  Schlüssel dafür. Der erste prüft zusätzlich, dass es ohne Schlüssel nicht mehr gewinnt.
- `tests/test_config.py::test_context_tokens_is_configurable` setzte 32.768 Tokens für
  gemma4:12b ohne erreichbares Ollama. Ohne Angaben zum Aufbau gilt jetzt der Standard
  (16.384), denn 32.768 Tokens können bei diesem Modell rund 12 GB belegen. Der Test prüft
  32.768 mit einem Modell, dessen Aufbau bekannt ist und bei dem das unter 5 GB bleibt, und
  dazu die Begrenzung ohne Angaben.
- `tools/rundgang.py`: Der Fuß des Menüs wird genau gewählt (`#picker-models >
  .picker-foot`) – bei leerer Liste gibt es eine zweite Zeile mit derselben Klasse.

## Grenzen dieser Prüfung

- **Kein echtes Ollama.** Die Rechnung ist mit den Angaben geprüft, die Ollama für qwen2.5,
  qwen3 und gemma3 meldet (nachgebaut in `tests/ollama_nachbau.py`). Wie viel ein Modell
  insgesamt belegt, hängt zusätzlich von seinen Gewichten ab; die 5 GB gelten für das
  Kontextfenster.
