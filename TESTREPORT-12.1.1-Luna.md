# Prüfbericht: 12.1.1 Luna

Stand: 2026-10-19. Grundlage: **12.0.1 Nutshell**, Commit `f2ffc87`, Branch `Aquaticy-ai`.

## Was neu ist: mehrere Rückfragen hintereinander

Braucht Aquaticy mehr als eine Angabe, stellt es seine Fragen jetzt nacheinander im selben
Fenster, etwa „Wo wohnst du?“ als erste und „Was interessiert dich?“ als zweite. Oben rechts im
Fenster steht, wie viele es sind und bei welcher man ist: **1/3**, **2/3**, **3/3**.

- Jede Frage hat ihre eigenen Antwortknöpfe und das Feld zum Selberschreiben.
- Mit der Antwort kommt die nächste Frage. Das Fenster bleibt dabei offen und ist kurz
  ausgegraut. Nach der letzten geht es zu.
- Bei nur einer Frage gibt es keinen Zähler, und ihr Ereignis ist unverändert.
- „Überspringen“ und Esc überspringen die aktuelle Frage, nicht die ganze Reihe.
- Alle Fragen und Antworten bleiben im Verlauf stehen.
- Der Zähler ist für Screenreader beschriftet („Frage 2 von 3“, englisch „Question 2 of 3“).
- Auf dem Handy erscheint das Fenster wie bisher unten, der Zähler steht auch dort oben rechts.

### Wer die Reihe auslöst

1. **Das Modell** selbst: `ask_user` hat einen neuen Parameter `questions`, bis zu fünf, jede mit
   eigenen Vorschlägen. Der Systemtext erklärt das.
2. **Der Planer** bei eingeschaltetem „Strukturiert“ (Denken- und Pro-Modus): Er kann zur ersten
   Frage bis zu zwei weitere nennen (`weitere_fragen`).
3. **Aquaticy selbst:** Fehlt der Ort (seit 12.0.1) und der Planer will noch etwas wissen, steht
   „In welchem Ort soll ich nachsehen?“ als erste Frage vorn. Fragt der Planer selbst nach dem
   Ort, kommt keine zusätzliche.
4. **Fragen im Text:** Schreibt das Modell mehrere Fragen in die Antwort („Wo wohnst du? Und was
   interessiert dich?“), werden daraus einzelne Fragen im Fenster, nicht mehr eine lange.

### Grenzen

- Höchstens **fünf** Fragen je Reihe, und die ganze Reihe zählt als **eine** Rückfrage von
  höchstens zwei je Anfrage. Es gibt also weiter keine endlose Fragerei.
- Wer eine Frage überspringt, bekommt trotzdem die nächsten. Läuft die Wartezeit ab (nach 120 s
  ohne Antwort), endet die Reihe. Sonst müsste man bei jeder weiteren Frage 3 Minuten warten.
- Die Antworten gelten wie bisher für den ganzen Chat. Unbeantwortete Fragen nennt Aquaticy dem
  Modell, das dann eine Annahme trifft und sie nennt.
- Im Terminal (`aquaticy chat`) stellt Aquaticy die Fragen ebenfalls nacheinander, ohne Zähler.

## Im ersten Volllauf gefunden

- `test_tools::test_ask_user_emits_events`: Er erwartet für eine einzelne Frage das Ereignis
  ohne Zähler. Das war zu Recht so: Die Ereignisse einer einzelnen Frage haben sich nicht zu
  ändern, nur eine Reihe trägt `index` und `total`. Der Test blieb unverändert, die Änderung
  kam in den Code.

## Fehlersuche

- Gefunden und behoben: Stand eine Frage sowohl in `question` als auch in `questions`, gingen
  die Antwortknöpfe der ersten verloren. Jetzt gelten die aus `question`.
- Fällt das Fenster nach der ersten Antwort aus, bleiben die gegebenen Antworten erhalten.
- Das ausgegraute Fenster schließt nach 12 Sekunden, falls keine weitere Frage kommt (Abbruch,
  Beantwortung auf einem anderen Gerät). Es bleibt nie offen hängen.
- Keine Sicherheitsregel berührt. Jede Antwort läuft wie bisher durch `/api/answer` mit
  Ai-guard-Prüfung und Herkunftsprüfung. bandit: keine neuen Hinweise.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | erster Volllauf: ein Fehlschlag (siehe unten). Danach alle fünf Schritte ohne Beanstandung (Rückgabewert 0): **5285 bestanden, 31 übersprungen, keine Fehlschläge** (5316 Tests, Browser-Rundgang eingeschlossen) |
| Neue Tests (`tests/test_v1211.py`) | 18, alle bestanden |
| Ereignisse einer einzelnen Frage (`tests/test_tools.py`) | unverändert bestanden |
| Browser-Rundgang, Abschnitt 5 | Reihe 1/3 → 2/3 → 3/3 im echten Browser: Zähler oben rechts, Fenster bleibt zwischen den Fragen offen, dritte Frage ohne Vorschläge, danach zu, alle Fragen im Verlauf |
| Sichtprüfung (Chromium) | Computer (1340 px) und Handy (390 px), Zähler sitzt in beiden oben rechts |

## Geänderte Tests

- Keiner. `tests/test_version.py` trägt wie bei jeder Fassung die neue Nummer und den Namen.

## Grenzen dieser Prüfung

- Geprüft mit gestellten Modellen. Ob qwen3:14b zwei Angaben in einem Aufruf von `ask_user`
  stellt, entscheidet es selbst. Im Strukturiert-Modus kommt der Ort ohnehin von Aquaticy, und
  Fragen im Text werden ebenfalls zur Reihe.
- Ein Modell kann mehr Fragen stellen wollen als fünf. Die übrigen fallen weg.
