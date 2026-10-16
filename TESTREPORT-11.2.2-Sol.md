# Prüfbericht: 11.2.2 Sol

Stand: 2026-10-15. Grundlage: **11.2.2 Terra**, Commit `ba22a61`, Branch `Aquaticy-ai`.

## Die gemeldeten Fehler

1. **Die virtual machine wurde im Code-Modus nicht genutzt.** Obwohl sie an war, schrieb
   Aquaticy Code, ohne ihn auszuführen. Auf Nachfrage sagte es, es könne keine virtual machine
   benutzen.
2. **Englisch war nicht überall Englisch.** Beim Schreiben einer Nachricht standen „Modell
   laden“, „Agenten arbeiten“ und die Zeilen darunter auf Deutsch, dazu viele Meldungen und
   Fenster.

**Ursachen zu 1.** Zwei Wege führten zum Ergebnis:
- Fehlte Podman oder Docker auf dem Rechner, bekam das Modell die Werkzeuge der virtual machine
  trotzdem. Jeder Aufruf scheiterte, und das Modell sagte nur „ich kann keine virtual machine
  benutzen“. Der Nutzer erfuhr nicht, woran es lag.
- Kleinere Modelle überlasen die Anleitung im Systemtext und antworteten gleich mit Code.

**Ursache zu 2.** Die Ablaufanzeige, viele Meldungen mit Zahlen oder Namen darin und alles,
was der Server schickt (Add-on-Katalog, Rechtsrahmen, Kopfzeile, Hinweise), hatten keine
englische Fassung. Einige englische Einträge passten nicht mehr zum geänderten deutschen Text.

## Was sich ändert

1. **Die virtual machine wird benutzt.**
   - An jeder Frage steht ein kurzer Hinweis, dass die virtual machine an ist.
   - Kommt Code zurück, der kein einziges Mal lief, schickt Aquaticy die Antwort einmal zurück:
     erst anlegen, ausführen, Ausgabe prüfen, dann antworten.
   - Fehlt Podman oder Docker, bekommt das Modell keine VM-Werkzeuge. Es sagt ehrlich, dass der
     Code ungetestet ist. Im Chat steht der Grund.
   - Ob Podman oder Docker da ist, merkt sich Aquaticy eine Minute. Jede Laufzeit wird nur noch
     einmal gefragt (vorher zweimal, bei hängendem Dienst je 8 Sekunden).
2. **Internet für die virtual machine** direkt im Code-Modus: Unter „Code wirklich
   ausprobieren“ erscheint, sobald man die virtual machine einschaltet, der Schalter „Internet
   für die virtual machine“. Nur Ultra kann ihn umlegen, geprüft am Server. Andere Konten sehen
   ihn mit 🔒 und eine kurze Erklärung. Fehlt Podman oder Docker, steht das darunter.
3. **Der Text am VM-Schalter stimmt wieder.** Er versprach Internet, das Normal- und Pro-Konten
   gar nicht haben.
4. **Englisch überall.**
   - Ablaufanzeige: alle Phasen („Loading model“, „Agents at work“, „Thought“ …), alle
     Marken („[Search]“, „[Map]“ …) und alle Zeilen darunter.
   - Rund 250 neue englische Einträge, dazu eine kleine Musterliste für Sätze mit Zahlen oder
     Namen („3 Dateien“ → „3 files“, „Chat öffnen: …“).
   - Was der Server schickt: Hinweise im Chat, Add-on-Katalog samt Rechten, Rechtsrahmen,
     Kopfzeile, Modellauswahl, Fehlermeldungen.
   - Der Sprachwähler nennt jede Sprache weiter in ihrer eigenen Sprache („Deutsch“).
   - Acht englische Einträge gehörten zu Texten, die es nicht mehr gibt; sie sind weg.
5. **Begrüßungen.**
   - Etwa jede zweite Begrüßung kommt ohne Namen („Womit fangen wir an?“).
   - Die mit Namen bleiben.
   - Neue Sätze je Modus: Normal 74, Pro 74, Code 75. Auf Englisch je Modus über 20 ganze
     Sätze statt vier Satzenden.
6. **Kleinere Fehler.**
   - Ein „$“ im Nutzernamen (erlaubt) verdarb die Begrüßung: Aus „Jo$&nas“ wurde
     „Jo{name}nas“.
   - Sichtbare Texte mit „ae“ statt Umlaut („läuft“, „aufgeräumt“).
   - Ein Erklärtext (Auto-Upgrading) war länger als die geprüfte Grenze von 340 Zeichen. Er ist
     gekürzt, alle Angaben zum Datenschutz stehen weiter drin.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | alle fünf Schritte ohne Beanstandung (Rückgabewert 0) |
| Testsuite (`pytest`) | erster Volllauf: 12 Fehlschläge. Gefunden: Die erste Fassung fragte `docker info` mitten in der Anfrage (Fund 9.5.18 verbietet das) – jetzt wird nie gewartet, gesucht wird im Hintergrund; englische Rollennamen lagen in der Seite statt beim Server – verlegt. Danach: **4887 bestanden, 27 übersprungen, keine Fehlschläge** (4914 Tests, 15 Minuten) |
| Neue Tests (`tests/test_v1122.py`, Sol-Teil) | 20, alle bestanden |
| VM an, Code kommt ohne einen Lauf zurück | geht einmal zurück, danach läuft er in der virtual machine; kein zweites Mal, und nicht nach einem Lauf |
| VM an, Podman/Docker fehlt | keine VM-Werkzeuge, ehrlicher Satz im Systemtext, Hinweis im Chat |
| Internet-Schalter im Browser | erscheint erst mit eingeschalteter virtual machine im Code-Modus, Ultra schaltet, Normal/Pro bekommt 🔒 und Erklärung, der Server lehnt Nicht-Ultra mit 400 ab |
| Englisch im Browser (Chats in Normal, Pro, Code, User mode, Bild, Rechtsrahmen; alle Fenster und Einstellungen) | kein deutscher Oberflächentext mehr; übrig sind nur Inhalte vom Modell und Ortsnamen |
| Statische Texte der Seite | jeder Text mit deutschen Wörtern hat eine englische Fassung (Test) |
| Jeder englische Eintrag | steht auch außerhalb des Wörterbuchs, also wird er gebraucht (Test) |
| Begrüßungen | rund 50 % mit Namen; alle Sätze in beiden Sprachen mit und ohne Namen sauber gesetzt (Test im Node) |

## Sicherheit

- **Internet für die virtual machine** bleibt Ultra vorbehalten. Der neue Schalter speichert
  über denselben Weg wie die Einstellungen; dort prüft der Server das Konto. Das Heimnetz bleibt
  gesperrt, solange nicht „Auch ins lokale Netz“ an ist. Eine laufende virtual machine wird
  dafür neu gebaut.
- **`/api/vm`** liegt hinter Zugangswort und Anmeldung wie alle anderen `/api/`-Routen. Es
  verrät nur vier Ja/Nein-Werte des eigenen Kontos.
- **Übersetzung:** Englische Texte werden nur als Text oder in die Attribute `placeholder`,
  `title` und `aria-label` gesetzt, nie als HTML. Was jemand im Chat schreibt, wird weiter nie
  übersetzt. Muster greifen nur bei kurzen Zeilen, damit lange Modellausgaben nicht bremsen.
- **Rechtsrahmen:** Die englische Fassung steht nur in der Anzeige. Geprüft wird weiter mit dem
  deutschen Regelwerk aus `aquaticy/guardrails.py`.
- Keine Sicherheitsregel gelockert. bandit: keine neuen Hinweise.

## Grenzen dieser Prüfung

- **Kein echtes Podman oder Docker.** Die Umgebung hat beides nicht. Dass die virtual machine
  benutzt wird, ist mit gestellten Werkzeugen geprüft; der Weg „Podman/Docker fehlt“ ist echt.
- **Inhalte vom Modell** (Teilfragen der Agenten, Lücken des Masters, Gedanken) schreibt das
  Modell selbst. Sie sind nicht Teil der Oberfläche und werden nicht übersetzt.

## Nachprüfung (2026-10-16)

Weiter gesucht, gefunden und behoben:

1. **Übersetzung traf fremden Text.** Die Muster für Sätze mit Zahlen oder Namen griffen
   auch in der Ablaufanzeige: Die Suche „Wie kann ich Cookies löschen?“ wurde zu „Delete Wie
   kann ich Cookies?“, „Sitzung Bundestag“ zu „Session Bundestag“. Wo Modell, Web oder Nutzer
   schreiben (Suchen, Gedanken, Agenten-Aufgaben, Rückfragen, Treffer, Aufträge, Coworker),
   gilt jetzt nur noch ein ganzer fester Oberflächentext. Im Browser bestätigt.
2. **Ai-guard sah den falschen Vorgänger.** „Die vorige Nachricht des Nutzers“ konnte ein
   interner Nachfass-Text sein (virtual machine, Bild, Rückfrage, Budget, Gegenprobe). Planer
   und Rechtsprüfer sahen dazu den VM-Hinweis. Eine gemeinsame Funktion (`own_words`) lässt
   nur die Frage selbst durch.
3. **Modell ohne Werkzeuge mit virtual machine.** Der Systemtext behauptete eine virtual
   machine, die das Modell gar nicht aufrufen kann. Jetzt: eigener Satz, eigener Hinweis
   („kann keine Werkzeuge benutzen“) statt „Podman oder Docker fehlt“.
4. **JSON als Antwort wurde ausgeführt.** Fragt der Nutzer selbst nach JSON, einem
   Werkzeugaufruf oder `web_search` & Co., bleibt ein JSON-Aufruf in der Antwort die Antwort
   (Terra-Umwandlung gilt sonst weiter, auch in den Agenten).
5. **Internet-Schalter zu früh geklickt:** Bevor der Stand geladen war, hieß es bei Ultra
   „nur mit Ultra“. Jetzt wird erst geladen.
6. **Laufzeit-Suche:** Konnte der Hintergrund-Faden nicht starten, wäre nie wieder gesucht
   worden. Abgefangen.
7. **Sichtbare Texte mit „ae/oe“:** „Gegenprüfung“, „Möbel“.

Prüfkette: Rückgabewert 0, **4893 bestanden, 27 übersprungen, keine Fehlschläge**
(4920 Tests). Neue Tests in `tests/test_v1122.py` für jeden Fund.
