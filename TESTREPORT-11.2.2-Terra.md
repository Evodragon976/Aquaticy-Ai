# Prüfbericht: 11.2.2 Terra

Stand: 2026-10-15. Grundlage: **11.2.2 Luna**, Commit `87830b1`, Branch `Aquaticy-ai`.

## Der gemeldete Fehler

Mit einem lokalen Modell (`ollama_chat/qwen2.5-coder:14b`) kam bei
„schreibe mir den code für eine website …“ nach „Agenten arbeiten“ nur „Da ist bei
Aquaticy etwas schiefgelaufen“ und keine Antwort. Im Normal- und im Pro-Modus.

**Ursache.** Aquaticy schickte jedem Ollama-Modell die Denktiefe mit (Standard „medium“).
LiteLLM macht daraus `think: true`. Ollama lehnt das bei Modellen ohne Denk-Modus mit
`"qwen2.5-coder:14b" does not support thinking` ab (HTTP 400). Planer, Agenten und Master
schalten das Denken ausdrücklich ab, deshalb liefen sie durch. Erst der erste Aufruf des
Hauptmodells danach scheiterte, genau an der Stelle, die die Meldung zeigte.

**Nachgestellt** mit einem nachgebauten Ollama (`tests/ollama_nachbau.py`), das `think`
und `tools` so ablehnt wie das echte, über den echten Weg Aquaticy → LiteLLM → HTTP. Vorher:
leere Antwort mit genau dieser Fehlermeldung. Nachher: Antwort.

## Was sich ändert

1. **Denktiefe nur an Modelle, die denken können.** Aquaticy fragt Ollama, was ein Modell
   kann (`/api/show`, zehn Minuten gemerkt). Sagt Ollama es nicht (ältere Fassung, nicht
   erreichbar), entscheidet der Name: qwen3, deepseek-r1, gpt-oss … ja, qwen2.5-coder, gemma,
   qwen3-coder nein.
2. **Aus der Ablehnung lernen.** Meldet ein Modell trotzdem „does not support thinking“
   oder „… tools“, merkt sich Aquaticy das und versucht es sofort ohne. Es bricht nicht mehr ab
   und versucht nicht dreimal dasselbe.
3. **Modelle ohne Werkzeuge** (gemma3 & Co.): Aquaticy bietet ihnen keine Werkzeuge an und
   startet keine Agenten, die an der ersten Suche scheitern würden. Das Modell antwortet aus
   dem, was im Gespräch steht. Im Chat steht ein kurzer Hinweis.
4. **Werkzeugaufrufe als Text.** qwen2.5-coder schreibt einen Aufruf über Ollama oft als JSON
   in die Antwort (`{"name": "web_search", "arguments": …}`, gern in ```json oder
   `<tool_call>`). Die Agenten hielten das für ihr Ergebnis und suchten nie. Der Master meldete
   dann „Lücken“. Besteht die Antwort nur aus solchen Aufrufen und passt jeder Name zu einem
   angebotenen Werkzeug, wird jetzt wirklich gesucht. Gilt im Hauptagenten (der schon
   gestreamte Text verschwindet wieder) und in den Agenten. Normale Antworten mit JSON darin
   bleiben Antworten.
5. **Zu wenig Speicher.** Ollamas Meldung „model requires more system memory (…) than is
   available“ wurde nicht als Speichermangel erkannt. Jetzt schon. Dann halbiert Aquaticy für
   dieses Modell den Kontext (16384 → 8192 …, nicht unter 4096) und kürzt den Verlauf passend,
   statt dreimal identisch zu scheitern.
6. **Der Grund steht im Terminal.** Nutzer sehen im Chat weiter nur den allgemeinen Satz.
   Der Betreiber sieht jetzt im Terminal des Servers, was wirklich schiefging, gekürzt und
   ohne Schlüssel. Vorher stand der Grund nirgends.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | alle fünf Schritte ohne Beanstandung (Rückgabewert 0) |
| Testsuite (`pytest`) | erster Lauf: 4865 bestanden, 27 übersprungen, 2 Fehlschläge – beide prüften den genauen Quelltext absichtlich geänderter Stellen (die Fehlermeldung im Chat geht jetzt über `oeffentlich = public_error(…)`, und es gibt eine dritte Zwischennachricht für gestreamte Text-Aufrufe); angepasst, ohne die Aussage zu ändern. Danach: **4867 bestanden, 27 übersprungen, keine Fehlschläge** (4894 Tests, 14 Minuten) |
| Neue Tests (`tests/test_v1122.py`, Terra-Teil) | 37, alle bestanden |
| Nachgestellter Fehler, Modell ohne Denk-Modus (qwen2.5-coder) | vorher: `does not support thinking`, leere Antwort; nachher: Antwort, kein `think` |
| Modell mit Denk-Modus (qwen3) | bekommt weiter die eingestellte Denktiefe |
| Modell ohne Werkzeuge (gemma3) | keine Werkzeuge, keine Agenten, Antwort |
| Älteres Ollama ohne `/api/show`-Fähigkeiten | lernt aus der Ablehnung, zweiter Aufruf gleich richtig |
| Speichermangel bei 16k Kontext | zweiter Versuch mit 8192, bleibt dabei, Antwort |
| Ganz durch: Browser → Server → Agent → LiteLLM → Ollama | Normal-, Pro- und Code-Modus ohne Fehler |
| Werkzeugaufruf als Text | 6 Formen erkannt, 8 normale Antworten nicht verwechselt; Hauptagent (mit und ohne Stream) und Agenten suchen wirklich |

## Sicherheit

- **Aus Text gelesene Werkzeugaufrufe** laufen durch dieselben Prüfungen wie echte: nur
  angebotene Werkzeuge, dieselbe Bestätigung vor folgenreichen Aktionen, dieselbe Vorsicht
  nach fremdem Inhalt. Das Modell konnte diese Werkzeuge vorher schon aufrufen, es kommt keine
  neue Fähigkeit dazu. Gelesen wird nur, wenn die ganze Antwort aus Aufrufen besteht,
  höchstens acht und höchstens 8000 Zeichen.
- **`/api/show`** geht an dieselbe Ollama-Adresse wie das Modell selbst und mit festem Pfad,
  ohne Proxy aus der Umgebung. Die Antwort wird nur nach Fähigkeiten durchsucht und nie
  angezeigt.
- **Terminal-Ausgabe** des Fehlers: Schlüssel und Passwörter werden vorher maskiert (dieselbe
  Funktion wie für den Browser), höchstens 300 Zeichen.
- Keine Sicherheitsregel gelockert.

## Grenzen dieser Prüfung

- **Kein echtes Ollama.** Die Umgebung sperrt den Download. Das Verhalten (Meldungen,
  Statuscodes, `/api/show`) ist dem echten Ollama 0.9+ nachgebaut. Der Weg durch LiteLLM ist
  echt.
- Ob ein bestimmtes lokales Modell gut antwortet, hängt vom Modell ab. Behoben ist, dass
  Aquaticy daran abbricht.
