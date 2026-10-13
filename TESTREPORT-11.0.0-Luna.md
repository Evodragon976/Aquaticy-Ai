# Prüfbericht: 11.0.0 Luna

Stand: 2026-10-13. Grundlage: **10.2.1 Terra**, Commit `0f8bb8e`, Branch `Aquaticy-ai`.

## Neu in dieser Fassung

- **Coworker** (`aquaticy/coworker.py`): Agenten, die die ganze Zeit an einer Aufgabe
  arbeiten — nach dem Vorbild von „dots“ in ChatGPT. Nur Pro (bis zu 2) und Ultra (bis zu 5,
  mit eigener virtual machine ohne Desktop).
- **Plugins** Code-Review und Security-Review (`aquaticy/plugins.py`) und `/name` im Chat für
  jedes eingeschaltete Add-on, mit Vorschlagsliste beim Tippen von „/“.
- **llama.cpp installiert sich selbst** für „Serverlast aufteilen“ (`aquaticy/llamacpp.py`).

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Testsuite (`pytest`) | 4635 bestanden, 27 übersprungen; 3 ältere Tests prüften wörtlich geänderte Texte und wurden angepasst, danach bestanden |
| Neue Tests: Coworker / Plugins / llama.cpp | 29 / 18 / 30, alle bestanden |
| Stilprüfung (`ruff check aquaticy tests`) | keine Beanstandung |
| Sicherheitsscan (`bandit`) der neuen Module | nur die erwarteten Hinweise zu `subprocess` (feste Argumente) |
| Typprüfung (`mypy`) der neuen Module | keine Fehler in den neuen Modulen |
| Rundgang durch die Weboberfläche (`tools/rundgang.py`, in `tests/test_rundgang.py`) | ohne Beanstandung |
| Bildschirmfotos PC und Handy (Coworker, „/“-Liste, Plugins) | keine JavaScript-Fehler, nichts ragt über den Rand |

## Sicherheit der neuen Teile

**Coworker.**
- Die Regeln (Erlauben, Fragen, Sperren) setzt der Werkzeugkasten im Code durch
  (`Toolbox.gate`), nicht der Prompt. Gesperrte Werkzeuge bekommt das Modell gar nicht erst.
- Nach fremdem Text (Webseite, Mail, Repo) wartet auch, was sonst erlaubt wäre, auf die
  Freigabe. Die eigene virtual machine ist davon ausgenommen; sie ist abgeschottet.
- **Bei der eigenen Prüfung gefunden und behoben:** Eine Webseite hätte über die Notizen des
  Coworkers den *nächsten* Arbeitsschritt beeinflussen können, der ohne fremden Text begann —
  dort wären erlaubte Aktionen ohne Rückfrage gelaufen. Notizen aus einem Schritt mit fremdem
  Text gelten jetzt als belastet; der nächste Schritt beginnt vorsichtig, bis der Nutzer sie
  löscht. Ein Regressionstest stellt den Weg nach.
- Freigegeben wird genau der gespeicherte Aufruf; ausgeführt wird er vom Code, nicht noch
  einmal vom Modell. Gilt die Einstellung dafür inzwischen nicht mehr (Google-Schreiben aus,
  kein Ultra), läuft er nicht. Eine Entscheidung zählt nur einmal.
- Nie für Coworker: Einstellungen ändern, Rückfragen, Bilder, Desktop (Messenger könnten
  senden), Blender, Merkzettel des Chats.
- Grenzen je Stufe (Anzahl, frühestes Wiederaufwachen, Arbeitsschritte je Tag), Kontingent,
  Ai-guard (Beleidigungen in Aufgabe und Nachrichten, Missbrauch in den Schritten), Sperre,
  Verbund (nur auf dem Heimserver). Bei herabgestuftem Konto ruhen die Coworker.
- Was der Coworker schreibt, zeigt die Oberfläche über dieselbe maskierende Markdown-Ausgabe
  wie Chat-Antworten; Nachrichten und Angaben als reinen Text.

**Plugins.** Die Prüflisten prüfen aus Sicht eines Verteidigers und verlangen ausdrücklich
keine Angriffsdaten. Angehängte Dateien bleiben als fremder Text markiert; danach brauchen
Werkzeuge mit Wirkung wie sonst eine Bestätigung. Ein Plugin gilt nur, wenn es installiert,
eingeschaltet und für das Konto nutzbar ist; Desktop-Plugins nur mit Ultra.

**llama.cpp.** Nur von GitHub (Umleitungen nur zu dessen Download-Servern, nur HTTPS), nur mit
veröffentlichter SHA-256-Prüfsumme, Größengrenzen beim Laden und Entpacken, keine Pfade oder
Verknüpfungen aus dem Zielordner heraus (Tests mit präparierten Zip- und Tar-Archiven),
mitgelieferte Ordner nur, wenn kein Fremder sie ändern kann.

## Weitere Funde der eigenen Prüfung (behoben)

- Die Beispiel-Aufgaben im Coworker-Fenster trugen die Klasse der Chat-Vorschläge und hätten
  beim Antippen zusätzlich das Eingabefeld des Chats befüllt (aufgefallen durch einen
  bestehenden Test). Sie haben jetzt eine eigene Klasse.
- Eine freigegebene Aktion, deren Ausführung unerwartet abbricht, blieb auf „erlaubt“ stehen;
  der Coworker hätte nie erfahren, wie es ausging. Sie endet jetzt immer als erledigt oder
  fehlgeschlagen.
- Beim Löschen eines Kontos hätte das Anhalten der Coworker-VMs die Einstellungen neu bauen
  und dabei Ordner wieder anlegen können.
- Namen von Coworkern ließen Steuerzeichen durch; sie werden jetzt bereinigt.
- Ein von GitHub verweigerter Zugriff (403) wurde als „zu viele Anfragen“ gemeldet.

## Grenzen dieser Prüfung

- Ein echtes Sprachmodell lief nicht: Coworker und Plugins wurden mit einem gestellten Modell
  geprüft, das echte Werkzeugaufrufe durch den echten Werkzeugkasten schickt. Wie gut ein
  bestimmtes Modell als Coworker arbeitet, hängt vom Modell ab.
- GitHub war aus dieser Umgebung nicht erreichbar. Der Download von llama.cpp wurde gegen einen
  gestellten GitHub-Server geprüft (Veröffentlichung, Umleitung, Prüfsumme, Archiv). Die
  Namen der fertigen Ausgaben (`llama-<Fassung>-bin-<System>.zip/.tar.gz`) entsprechen den
  Veröffentlichungen von llama.cpp; ändert das Projekt sie, meldet Aquaticy das verständlich
  und nimmt weiter ein selbst gebautes llama.cpp aus `AQUATICY_RPC_SERVER` und
  `AQUATICY_LLAMA_SERVER` oder aus dem Suchpfad.
- Die eigene virtual machine der Coworker wurde mit einer gestellten Laufzeit geprüft, nicht
  mit Docker oder Podman.
