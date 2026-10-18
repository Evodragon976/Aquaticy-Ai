# Prüfbericht: 11.3.2 Sol

Stand: 2026-10-18. Grundlage: **11.3.2 Terra**, Commit `ae166df`, Branch `Aquaticy-ai`.

## Der gemeldete Fehler: „No module named 'mcp'“

Nach einer frischen Installation (`uv tool install --force --reinstall .`) endete jede Frage
im Terminal mit `[Fehler] ModuleNotFoundError: No module named 'mcp'`.

**Ursache.** `pyproject.toml` erlaubte LiteLLM `>=1.100.0,<2`. Eine frische Installation
holte deshalb die neueste Fassung, **LiteLLM 1.106.0**. Die lädt bei jedem Aufruf mit
Werkzeugen ihre MCP-Gateway-Module (`litellm.responses.mcp` →
`litellm.proxy._experimental.mcp_server.catalog`), und die brauchen das Paket `mcp`. Das gehört
nicht zu den Abhängigkeiten von LiteLLM. Aquaticy schickt immer Werkzeuge mit, also traf es
jede Frage. Der Commit „11.3.2 Terra“ hat daran nichts geändert; der Fehler war noch da.

Nachgestellt in einer frischen Umgebung (Python 3.12, `uv pip install .`):

| LiteLLM | Aufruf mit Werkzeugen |
|---|---|
| 1.102.1 (constraints.txt), 1.103.5, 1.104.3, 1.105.1 | geht |
| **1.106.0** (frische Installation) | `ModuleNotFoundError: No module named 'mcp'` |

**Behoben auf zwei Wegen:**
1. `pyproject.toml` schließt die Fassung aus: `litellm>=1.100.0,!=1.106.0,<2`.
2. Neues Modul `aquaticy/llmcall.py`. Fehlt `mcp`, wiederholt es denselben Aufruf ohne den
   MCP-Umweg (`_skip_mcp_handler`) und merkt sich das. Aquaticy nutzt kein MCP-Gateway von
   LiteLLM. Der Fehler kommt, bevor etwas ans Netz geht: nichts wird doppelt geschickt oder
   gezählt. Andere Fehler bleiben Fehler. Darüber laufen der Agent, die gezählten Aufrufe
   (`metering`) und die Werkzeugprobe lokaler Modelle.

Gegenprobe mit dem echten LiteLLM 1.106.0 ohne `mcp`: Vorher scheiterte schon der erste Test
mit einem Modellaufruf. Danach liefen **375 Tests** der betroffenen Bereiche durch
(`test_agent`, `test_end_to_end`, `test_v1122`, `test_v1130`, `test_v1131`).

**Bei dir:** Neu holen und wie gewohnt installieren
(`uv tool install --force --reinstall .`). uv nimmt dann eine Fassung ohne den Fehler.

## Neu: Server-Verbund nach Stärke

1. **Jeder Server meldet seine Hardware** mit dem Lebenszeichen (alle 3 s): Kerne, Prozessor-
   und Arbeitsspeicherlast, Grafikkarte mit Speicher und Last, Zahl der Ollama-Modelle.
   Gemessen höchstens alle 10 Sekunden. Was von einem anderen Server kommt, wird geprüft:
   nur bekannte Felder, nur echte Zahlen in sinnvollen Grenzen (kein Text, kein NaN, nichts
   Negatives), Namen gekürzt.
2. **Der Master gibt jedem Server eine Rolle.**
   - **„Modelle und etwas Website“:** Ollama mit mindestens einem Modell, dazu eine
     Grafikkarte ab 4 GB oder ab 16 GB Arbeitsspeicher. Außerdem mindestens 40 % der
     Modell-Leistung des stärksten Servers.
   - **„Nur Website“:** alle anderen.
3. **Verteilung.**
   - Ein Konto mit lokalen Modellen (Haupt-, Code- oder Agenten-Modell bei Ollama oder im
     Verbund) kommt nur auf einen Modell-Server. Dort geht es hin, wo die Last im Verhältnis
     zur Modell-Leistung am kleinsten ist.
   - Sitzt ein solches Konto auf einem schwachen Server, zieht es um, sobald dort keine
     Antwort mehr läuft.
   - Alle anderen Konten sind Website-Arbeit: zuerst die schwachen Server, nach ihrer Stärke.
     Ein Modell-Server zählt dafür höchstens halb so stark wie der beste reine
     Website-Server. Er bekommt Website-Arbeit erst, wenn die anderen gut zu tun haben.
   - Kann kein Server lokale Modelle (oder melden ältere Fassungen keine Hardware), verteilt
     der Master wie bisher nach Last.
4. **Auslastung je Server.** Unter *Einstellungen → Auslastung* steht nach den eigenen
   Werten jeder Server des Verbunds: Name, Master/dieser Server, Rolle, Zahl der Konten,
   Prozessor, Arbeitsspeicher und Grafikkarte. Ein ausgefallener Server zeigt „nicht
   erreichbar“ statt alter Zahlen. In der Liste unter *Dev settings → Server-Verbund* steht
   die Rolle mit dabei. Wie bisher nur für Ultra.

## Weitere Funde

1. **Einzelne Anfragen hingen 30 Sekunden und mehr.** Der Browser-Rundgang scheiterte am
   Ende in etwa drei von fünf Läufen: Eine neue Seite wurde nie „ruhig“, weil
   `/api/upgrades` nicht zurückkam. Das trat schon auf dem unveränderten Stand 11.3.2 Terra
   auf. Die Spur:
   - Die Anfrage kam nie beim Server an; kein Faden bearbeitete sie.
   - Ursache ist die Warteschlange für neue Verbindungen. Pythons `ThreadingHTTPServer` nimmt
     **5**. Eine Seite öffnet beim Laden aber zwölf Anfragen auf einmal.
   - Lief die Schlange über, verwarf der Kernel den Verbindungsaufbau. Der Browser wiederholte
     mit wachsenden Pausen (1, 3, 7, 15, 31 s).
   - Nachgemessen: Von 40 gleichzeitigen Verbindungen kamen mit 5 nur 6 sofort durch (17,9 s
     insgesamt), mit 128 alle in 0,5 s.

   Das traf auch echte Nutzer, besonders mit mehreren Tabs oder Konten gleichzeitig. Jetzt
   128 (`AquaticyServer.request_queue_size`), auch für den Eingang mit eigener Domain.
2. **Regler unter dem Minimum des Servers.** Bei sehr großen Modellen geht der Regler für
   das Kontextfenster unter 2000 Tokens, damit die 5 GB reichen. Der Server lehnte solche
   Werte ab. Untergrenze jetzt 256.
2. **Auslastung auf Englisch** zeigte „Prozessor“, „4 Kerne“, „von 16 GB“. Jetzt englisch.
3. **Zwei Tests setzten IPv6 voraus** (`tests/test_v1132_terra.py`, Bindung an `::1`). Auf
   Rechnern ohne IPv6 scheiterten sie mit „Address family not supported“, auch ohne jede
   Änderung. Sie prüfen jetzt vorher, ob sich `::1` binden lässt, und werden sonst mit Grund
   übersprungen, wie der Rundgang ohne Chromium. Mit IPv6 laufen sie unverändert.

## Geänderte Tests

- `tests/test_security.py::test_all_model_calls_go_through_the_meter` suchte nur nach
  `litellm.completion(`. Jetzt zählt `llmcall.completion(` genauso: Außerhalb von Agent,
  Zähler und Einrichtungsproben darf keiner von beiden vorkommen. Der Test ist damit strenger,
  nicht schwächer.
- `tests/test_v1132_terra.py`: siehe „Weitere Funde“, Punkt 3.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | alle fünf Schritte ohne Beanstandung (Rückgabewert 0) |
| Testsuite (`pytest`) | erster Volllauf: 2 Fehlschläge (Zähler-Test kannte `llmcall` nicht; Rundgang-Hänger, siehe „Weitere Funde“ 1). Danach: **5129 bestanden, 31 übersprungen, keine Fehlschläge** (5160 Tests, Rundgang vollständig) |
| LiteLLM 1.106.0 ohne `mcp` (frische Umgebung) | Fehler nachgestellt, nach dem Fix 375 Tests grün |
| LiteLLM 1.102.1 bis 1.105.1 | Aufruf mit Werkzeugen geht |
| Fuzzing aller API-Routen, nicht angemeldet | kein HTTP 500 |
| Fuzzing angemeldet (Ultra, im Browser) | kein HTTP 500, die Sitzung bleibt gültig (1531×200, 496×400, 40×403, 3087×404, 12×413) |
| Auslastung im Browser (schwacher Master, Gaming-PC mit RTX 4090) | Rollen, Konten und Balken je Server richtig, Deutsch und Englisch, Handy ohne Querscrollen |
| Neue Tests (`tests/test_v1132_sol.py`) | 21, alle bestanden |

## Sicherheit

- Die Hardware anderer Server ist **Eingabe von außen** und wird wie `_split_status` geprüft.
  In der Oberfläche geht alles maskiert hinein (Namen sind Text, kein HTML).
- `/api/system` mit den Werten aller Server bleibt **Ultra** vorbehalten.
- Die Rolle eines Kontos liest der Master aus der `.env` seines Profils. Die Kennung ist
  vorher geprüft (`^[A-Za-z0-9_-]{1,64}$`).
- `llmcall` fängt nur genau den fehlenden `mcp` ab. Jeder andere Fehler geht weiter wie bisher.
- Keine Sicherheitsregel gelockert. bandit: keine neuen Hinweise.

## Grenzen dieser Prüfung

- **Kein echter zweiter Server, keine echte Grafikkarte.** Die Verteilung ist mit zwei Servern
  in einem Prozess und gestellter Hardware geprüft (wie die übrigen Verbund-Tests).
- **Ein Konto rechnet auf seinem Heimserver.** Einzelne Modellanfragen eines Website-Servers
  gehen nicht an die Grafikkarte eines anderen. Getrennt wird über die Zuteilung der Konten.
  Ein Modell über mehrere Server verteilt nur „Serverlast aufteilen“.
