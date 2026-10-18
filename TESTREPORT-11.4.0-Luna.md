# Prüfbericht: 11.4.0 Luna

Stand: 2026-10-18. Grundlage: **11.3.2 Sol**, Commit `ef04922`, Branch `Aquaticy-ai`.

## Die gemeldeten Fehler

1. **Wer aus dem Browser oder der App ging, verlor die Antwort.** Nach z. B. zwei Stunden
   stand dort nichts oder „abgebrochen“.
2. **Gezielte Fragen bekamen keine gezielte Antwort.** „Was läuft im Kino?“ brachte Namen und
   Bewertungen der Kinos, aber keinen einzigen Film.
3. **Der Ort wurde im selben Chat erneut abgefragt.** Er war im Rückfrage-Fenster schon
   beantwortet, das Kontextfenster war groß genug.

## Ursachen und Korrekturen

### 1. Weg und wieder da

Die Anfrage lief schon immer auf dem Server weiter. Verloren ging sie auf dem Weg zurück:

- **15 Minuten.** Eine fertige, ungesehene Antwort wurde beim Zurückkommen nur 15 Minuten lang
  wieder angezeigt. Danach landete man auf der leeren Startseite, obwohl die Antwort fertig
  war. Jetzt **eine Woche**. Die Oberfläche öffnet dabei den Chat, zu dem die Antwort gehört
  (der Lauf kennt seinen Chat), und zeigt die ganze Antwort mit „Die Anfrage ist fertig
  geworden, während du weg warst.“ Danach gilt sie als gesehen und wird nicht noch einmal
  abgespielt.
- **Abbruch durch den Browser = Abbruch durch den Nutzer.** Kappte der Browser die Leitung
  selbst (App im Hintergrund, Seite aus dem Speicher geholt), zeigte die Seite „[Abgebrochen]“
  wie nach dem Stopp-Knopf und hängte sich nicht wieder an. Jetzt brechen nur Stopp und
  Chatwechsel ab; alles andere gilt als abgerissene Leitung.
- **Drei schnelle Versuche im Hintergrund.** Riss die Leitung ab, während die Seite im
  Hintergrund lag, versuchte sie es dreimal in wenigen Sekunden und gab auf. Jetzt wartet sie,
  bis man wieder da ist (ob nach einer Minute oder nach Stunden), und hängt sich dann an.
  Versuche im Hintergrund zählen nicht.

Hält die Server-Sitzung die Antwort nicht mehr (Neustart, älter als eine Woche), steht sie wie
bisher im Verlauf des Chats.

### 2. Gezielte Angaben

- **Neue Regel im Systemtext.** Fragt jemand nach einer bestimmten Angabe (welche Filme laufen,
  Speisekarte, Öffnungszeiten, Preise, Abfahrten, Termine, Programm), ist genau das die
  Antwort. Orte, Namen oder Bewertungen allein beantworten sie nicht. Aquaticy soll die
  Programm-, Speisekarten- oder Fahrplanseite der gefundenen Orte öffnen und die Angabe nennen,
  oder ehrlich sagen, dass sie nirgends lesbar steht, und die Seite verlinken.
- **Sicherheitsnetz.** Will die Frage so eine Angabe und kommt eine Antwort, ohne dass in
  diesem Turn eine einzige Seite gelesen wurde (weder vom Agenten noch von den Helfern), geht
  sie **einmal** zurück. Der Auftrag nennt die fehlende Angabe („welche Filme oder Stücke
  laufen, mit Uhrzeiten“). Wie beim bestehenden Nachfass für Rückfragen und Bilder: höchstens
  einmal je Frage, nicht im Code-Modus, nicht ohne Web.
- **Die Planung weiß es auch.** Im Denken- und Pro-Modus bekommt der Planer den Hinweis, welche
  Angabe gesucht ist. Die Teilfragen suchen dann die Filme, nicht nur die Kinos.
- **Erkennung** (geprüft): Kinoprogramm, „was läuft“, Spielplan, Vorstellungen, „what's on“;
  Speisekarte/Menü; Öffnungszeiten, „wann hat … offen“; Fahrplan, Abfahrt, nächster
  Bus/Zug; Konzerte, Veranstaltungen, Line-up, „was ist los“; Preise, „was kostet“, Eintritt.
  Nicht erkannt werden absichtlich allgemeine Fragen wie „Event-Loop in JavaScript“,
  „Nobelpreis“, „Wetter“ oder „how much RAM“.

### 3. Geklärtes gilt im ganzen Chat

**Ursache.** Die Antwort aus dem Rückfrage-Fenster stand nur als Werkzeug-Ausgabe im Verlauf.
Ältere Werkzeug-Ausgaben ersetzt Aquaticy aber immer durch einen Platzhalter, egal wie groß
das Kontextfenster ist. Nach ein paar Suchen war „Bremen“ also weg. Zusätzlich:
- Beim Wiederöffnen eines Chats wurden nur Fragen und Antworten wiederhergestellt.
- Der Planer sah keine Werkzeug-Ausgaben.

**Jetzt:**
- Antworten aus dem Rückfrage-Fenster werden **nie gekürzt**.
- Sie stehen als „Im Gespräch schon geklärt: Für welchen Ort? → Bremen“ an jeder weiteren
  Frage dieses Chats und im Kontext des Planers.
- Sie werden mit dem Chat gespeichert und gelten nach dem Wiederöffnen, auf einem anderen
  Gerät und nach einem Neustart weiter.
- Eine neue Antwort auf dieselbe Rückfrage ersetzt die alte. Ein neuer Chat beginnt ohne sie.
- Höchstens 12 Angaben je Chat, je 200 Zeichen.

## Weitere Funde

1. **„Zu viele Anfragen“ brachte die Seite ins Stolpern.** Das war die eigentliche Ursache
   des wackeligen Browser-Rundgangs seit 11.3.2. Am Ende des langen Rundgangs erreichte das
   Testkonto das Limit (240 Anfragen je Minute und Konto). Die Seite bekam `429` und kam
   damit nicht zurecht:
   - **Seite wird nie „ruhig“.** `pruefeUpgrade` brach mit `if (!res.ok) return;` ab, ohne
     die Antwort zu lesen. Eine ungelesene Antwort bleibt im Browser eine offene Anfrage.
     Dass der Server gar keinen Faden mehr dafür hatte, lag daran, dass er längst
     geantwortet hatte. Die Vermutung aus 11.3.2 (Warteschlange) war nur ein Teil.
   - **Einstellungen gingen nicht auf.** Ein Skriptfehler („Cannot convert undefined or null
     to object“) öffnete das Fenster „Da ist etwas schiefgelaufen“.

   Jetzt:
   - Der Server schickt mit `429` ein `Retry-After` (Sekunden, bis wieder Platz ist).
   - Lesende Anfragen warten so lange (höchstens 10 s) und fragen bis zu dreimal neu.
     Schreibende nie, sonst wäre ein zweites Senden eine zweite Aktion.
   - Jede Fehlerantwort wird sofort ganz gelesen, egal was der Aufrufer damit tut.
   - Die Einstellungen zeigen bei einer Fehlerantwort einen Hinweis statt abzustürzen.

   Das Limit selbst bleibt unverändert.
2. **Rückfrage-Fenster aus abgespielten Läufen blieben offen.** Spielte die Seite einen Lauf
   ab, der eine Rückfrage enthielt (nach einem Verbindungsabbruch, jetzt auch nach Stunden),
   öffnete sie das Fenster neu. Geschlossen wurde es nie, denn das Ereignis „beantwortet“
   (`ask_done`) kannte die Oberfläche nicht. Jetzt schließt es bei „beantwortet“, auch wenn
   auf einem anderen Gerät geantwortet wurde, und spätestens am Ende des Laufs. Dabei geht
   keine zweite Antwort an den Server.
3. **Der Rundgang räumt auf.** Er schloss für jedes Gerät nur die Seite, nicht den
   Browser-Kontext. Jetzt schließt er den ganzen Kontext.

## Sicherheit

- Der Text einer Rückfrage formuliert das Modell. Nach gelesenen Seiten könnte darin fremder
  Text stecken, und er gilt jetzt für den ganzen Chat. Deshalb:
  - gekürzt auf 200 Zeichen, eine Zeile;
  - eckige Klammern werden zu runden, damit der Text den Hinweisblock nicht schließen kann
    (Test);
  - er steht als Hinweis bei der Nutzerfrage, nicht im Systemtext.
- `/api/runstate` nennt zusätzlich den eigenen Chat des Laufs. Das Öffnen geht über
  `/api/open`; der Server prüft dort wie bisher, dass der Chat zum Konto gehört.
- Ein fertiger Lauf bleibt länger abholbar, aber nur im Speicher der eigenen Sitzung. Beim
  Löschen des Kontos geht er mit der Sitzung.
- Das Anfragen-Limit bleibt, wie es war; `Retry-After` verrät nur, wann wieder Platz ist.
- Keine Sicherheitsregel gelockert. bandit: keine neuen Hinweise.

## Geänderte Tests

- `tests/test_agent.py::test_the_second_round_searches_before_it_asks_the_model` fragte „Was
  kostet ein Lastenrad?“ und antwortete ohne gelesene Seite. Genau das schickt die neue
  Regel einmal zurück. Der Test prüft die Gegenprobe und fragt jetzt „Wie schwer ist ein
  Lastenrad?“. Die neue Regel selbst prüft `tests/test_v1140.py`.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | alle fünf Schritte ohne Beanstandung (Rückgabewert 0) |
| Testsuite (`pytest`) | erster Volllauf: Rundgang rot (siehe „Weitere Funde“ 1). Danach: **5155 bestanden, 31 übersprungen, keine Fehlschläge** (5186 Tests) |
| Browser-Rundgang, dreimal hintereinander | vorher etwa jeder zweite rot; jetzt 3 × 412 Prüfungen ohne Beanstandung |
| Neue Tests (`tests/test_v1140.py`) | 26, alle bestanden |
| Agent-Tests (`test_agent`, `test_end_to_end`, `test_subagents`, `test_master`, `test_security`, `test_v1122`, `test_feature_tour`) | 449 bestanden |
| Im Browser: Seite schließen, während die Antwort läuft, „zwei Stunden“ später wiederkommen | 11.3.2 Sol: leere Startseite (der gemeldete Fehler). 11.4.0: Der Chat öffnet sich mit der ganzen Antwort; beim nächsten Laden nicht noch einmal |
| Im Browser: App im Hintergrund, Netz weg, nach 9 s zurück | Antwort vollständig (auch in 11.3.2) |
| Ort im Fenster beantwortet, vier Suchen, zweite Frage | „Bremen“ steht in der zweiten Frage; nach dem Wiederöffnen ebenso |
| „Was läuft heute im Kino?“, Antwort nur mit Kinos | geht einmal zurück, die zweite Antwort nennt die Filme; mit gelesener Seite oder bei allgemeinen Fragen kein Nachfass |

## Grenzen dieser Prüfung

- **Kein echtes Handy.** Wie ein Handy eine Verbindung im Hintergrund kappt, lässt sich im
  Test-Browser nicht genau nachstellen. Der laufende Datenstrom riss in der Simulation nicht
  wirklich ab. Das Warten im Hintergrund ist durch Code und Test belegt, nicht durch ein
  Gerät.
- **Kein echtes Modell.** Ob ein bestimmtes Modell nach dem Nachfass die Kinoseiten wirklich
  findet, hängt vom Modell und von den Seiten ab. Geprüft ist, dass der Auftrag ankommt.
