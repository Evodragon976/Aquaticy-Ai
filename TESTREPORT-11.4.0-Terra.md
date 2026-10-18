# Prüfbericht: 11.4.0 Terra

Stand: 2026-10-18. Grundlage: **11.4.0 Luna**, Commit `6db8c1a`, Branch `Aquaticy-ai`.

## Der gemeldete Fehler

Seit 11.4.0 Luna fragte Aquaticy kaum noch nach, auch bei Fragen, die mehr Kontext
brauchen.

## Ursachen

1. **Der neue Nachfass für gezielte Angaben überstimmte die Rückfrage.** Ein Beispiel:
   „Was läuft heute im Kino?“ ohne Stadt.
   - Das Modell schrieb „Für welche Stadt soll ich suchen?“.
   - Darauf kam der Auftrag „Öffne jetzt die Programmseiten“.
   - Das Modell riet eine Stadt.

   Der Nachfass prüfte nur, ob eine Seite gelesen wurde, nicht, ob das Modell gerade
   nachfragte.
2. **Die neue Regel „Gezielte Angaben“** sagte „Finde die Orte, öffne die Seiten“, aber nicht,
   was gilt, wenn der Ort fehlt.
3. **Der Hinweis zu geklärten Angaben** endete mit „frag nicht noch einmal danach“. Manche
   Modelle lasen das als allgemeines Frageverbot.
4. **Im Denken- und Pro-Modus** recherchierten die Agenten, bevor das Hauptmodell überhaupt
   fragen konnte. Fehlte der Ort, suchten sie ins Blaue. Danach fragte das Modell nicht mehr,
   denn es hatte ja schon Ergebnisse. Das gab es schon vor 11.4.0.

## Was sich ändert

1. **Der Nachfass drückt nie über eine Frage hinweg.** Hat das Modell in diesem Turn
   nachgefragt (im Fenster oder im Text), kommt kein Auftrag zum Suchen. Der Auftrag selbst
   sagt jetzt: „Fehlt dir dafür etwas (der Ort, der Tag), dann frag jetzt mit `ask_user`
   nach, statt zu raten.“
2. **Die Regel „Gezielte Angaben“** beginnt mit: Fehlt der Ort oder der Tag, frag zuerst;
   rate nie eine Stadt.
3. **Geklärte Angaben** gelten weiter für den ganzen Chat, aber nur sie: „Fehlt für diese
   Frage etwas ANDERES, frag wie immer mit ask_user nach.“
4. **Der Planer fragt vor der Recherche.** Im Denken-Modus entscheidet der Planer ohnehin,
   ob recherchiert wird. Jetzt darf er zusätzlich eine kurze Rückfrage mit bis zu vier
   Antwortvorschlägen zurückgeben, wenn eine entscheidende Angabe fehlt und weder im
   Gespräch noch im Ortsfilter steht:
   - der Ort bei etwas Örtlichem,
   - der Zeitraum, wenn mehrere passen,
   - das Budget bei einer Auswahl,
   - welches von mehreren gleichnamigen Dingen gemeint ist.

   Die Frage geht ins Fenster. Mit der Antwort wird neu geplant, und die Agenten suchen
   dann gezielt. Im Pro-Modus fragt vor dem Master derselbe kleine Planer; das ist ein
   kurzer Aufruf, und nur dann, wenn jemand antworten kann. Ohne Gegenüber (Aufträge,
   Coworker) wird nie gefragt.
5. **Die Antwort zählt wie jede Rückfrage:** Sie steht an der Frage („[Rückfrage vor der
   Recherche: In welcher Stadt? → Bremen]“) und gilt für den ganzen Chat.

## Weiterer Fund

- **`own_words` kannte den Block mit geklärten Angaben nicht** (seit 11.4.0 Luna). Planer,
  Rechtsprüfung und Ai-guard sahen ihn als Worte des Nutzers. Jetzt werden alle Anhänge
  abgeschnitten: Ortsfilter, geklärte Angaben, Rückfrage vor der Recherche.

## Sicherheit

- Die Rückfrage des Planers formuliert ein Modell. Sein Kontext kann Text aus früheren
  Antworten enthalten, also auch Text von Webseiten. Deshalb:
  - nur als Text angezeigt, nie als HTML;
  - höchstens 200 Zeichen und vier Antwortvorschläge zu je 80 Zeichen;
  - eckige Klammern werden zu runden, damit kein Hinweisblock aufgebrochen wird;
  - höchstens so viele Rückfragen je Anfrage wie bisher (`MAX_QUESTIONS`).
- Ohne jemanden, der antworten kann, wird nicht gefragt. Ein Auftrag bleibt also nie an
  einer Frage hängen.
- Keine Sicherheitsregel gelockert. bandit: keine neuen Hinweise.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | alle fünf Schritte ohne Beanstandung (Rückgabewert 0): **5163 bestanden, 31 übersprungen, keine Fehlschläge** (5194 Tests, Browser-Rundgang eingeschlossen) |
| Neue Tests (`tests/test_v1140_terra.py`) | 8, alle bestanden |
| Agent-, Planer- und Sicherheitstests | 475 bestanden |
| „Was läuft heute im Kino?“, Modell fragt nach der Stadt | die Frage bleibt die Antwort, kein Nachfass (vorher: Auftrag zum Suchen) |
| Denken-Modus, Planer meldet „In welcher Stadt?“ | Fenster mit „Bremen“/„Hamburg“, dann neu geplant, Agenten suchen „… Bremen“ |
| Pro-Modus, Planer meldet „Welches Budget?“ | Frage vor dem Master, die Antwort steht in seinem Kontext |
| Ohne Gegenüber | keine Rückfrage |

## Grenzen dieser Prüfung

- **Kein echtes Modell.** Ob ein bestimmtes Modell im Standardmodus fragt, entscheidet das
  Modell anhand der Regeln. Geprüft ist, dass Aquaticy es nicht mehr davon abhält. Im
  Denken- und Pro-Modus fragt der Planer, sobald er eine fehlende Angabe meldet.
