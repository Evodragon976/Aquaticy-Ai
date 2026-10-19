# Prüfbericht: 12.0.1 Nutshell

Stand: 2026-10-19. Grundlage: **12.0.0 Sol**, Commit `9bf9d46`, Branch `Aquaticy-ai`.

## Was neu ist: Rückfragen kommen wieder ins Fenster

Gemeldet: Bei „Was sind die neuesten Nachrichten in meinem Ort?“ fragte Aquaticy nach dem Ort im
Chat, nicht im Rückfrage-Fenster.

### Warum

Eine Antwort, die nur eine Rückfrage ist, schickt Aquaticy einmal mit der Bitte zurück, das
Fenster zu nutzen (`FORCE_ASK_PROMPT`). Dazu kam es selten, und es reichte nicht:

1. **Zu streng erkannt.** Als Rückfrage galt ein Text nur, wenn neben den Fragesätzen
   höchstens 40 Zeichen standen. „Gerne suche ich dir die neuesten Nachrichten heraus!“ ist
   schon länger. Außerdem musste der Text genau mit „?“ enden, also ohne Emoji und ohne Liste
   mit Vorschlägen darunter.
2. **Nach einer Suche nie.** Hatte das Modell schon ein Werkzeug benutzt, blieb die Frage
   stehen. Bei Nachrichten aus dem eigenen Ort sucht es oft zuerst und merkt dann, dass der Ort
   fehlt.
3. **Nur ein Versuch.** Schrieb das Modell die Frage nach dem Anstoß wieder in den Text, blieb
   sie dort.

### Was jetzt gilt

- **Erkennen** (`text_question` in `aquaticy/agent.py`):
  - Ein Vorsatz bis 220 Zeichen darf vor der Frage stehen.
  - Emoji, Klammern und Markdown am Ende stören nicht.
  - Steht eine Liste mit Vorschlägen darunter („- heute“, „1. morgen“), werden daraus bis zu
    vier Antwortknöpfe im Fenster.
- **Keine Rückfrage** und weiter Text sind:
  - Angebote am Ende einer Antwort („Soll ich auch …?“, „Möchtest du …?“, „Would you like …?“);
  - Antworten mit Link oder Code;
  - alles über 600 Zeichen.
- **Nach einer Suche** gilt die Regel jetzt auch. Erst wer schon eine Seite gelesen hat, darf
  im Text nachfragen. Das ist dann eine Anschlussfrage zu einer Antwort.
- **Selbst fragen:** Wie bisher geht die Frage einmal mit dem Anstoß an das Modell zurück.
  - Antwortet es dann, weil es die Angabe doch nicht braucht, bleibt die Antwort.
  - Schreibt es die Frage wieder in den Text, stellt Aquaticy sie selbst im Fenster, mit den
    Vorschlägen als Knöpfen.
  - Im Verlauf wird daraus ein echter Aufruf von `ask_user`. Das Modell arbeitet mit der Antwort
    weiter, und die Antwort wird für den Chat gemerkt wie jede andere Rückfrage.
- **Grenzen bleiben:**
  - höchstens zwei Rückfragen je Anfrage;
  - nur, wenn jemand antworten kann;
  - nicht im Code-Modus;
  - nie eine Schleife, denn sowohl der Anstoß als auch das selbst geöffnete Fenster gibt es
    höchstens einmal je Anfrage.

## Fehlersuche

- Gefunden und mit behoben: Die alte Bedingung „noch kein Werkzeug benutzt“ verhinderte genau
  den gemeldeten Fall (erst suchen, dann nach dem Ort fragen).
- Wird während der Rückfrage auf Stopp gedrückt, endet der Lauf sauber (`stopped`).
- Keine Sicherheitsregel berührt. bandit: keine neuen Hinweise.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | alle fünf Schritte ohne Beanstandung (Rückgabewert 0): **5247 bestanden, 31 übersprungen, keine Fehlschläge** (5278 Tests, Browser-Rundgang eingeschlossen) |
| Neue Tests (`tests/test_v1201.py`) | 19, alle bestanden; darunter der gemeldete Fall Wort für Wort |
| Bisherige Tests zu Rückfragen (`tests/test_agent.py`) | bestanden |

## Geänderte Tests

- **`test_agent::test_the_nudge_happens_at_most_once`:** Bis 12.0.0 blieb eine Frage im Text
  stehen, wenn das Modell sie nach dem Anstoß wiederholte. Genau das soll sich ändern. Der Test
  prüft weiter, dass es nur einen Anstoß und keine Schleife gibt. Er prüft jetzt außerdem, dass
  die wiederholte Frage im Fenster gestellt wird und die Antwort weiterverarbeitet wird.
- **`test_v1200::test_twelve_is_the_version`:** Er verlangte die Nummer 12.0.0. Er prüft jetzt,
  dass es Fassung 12 ist und die Rückfallangabe der Oberfläche zu Nummer und Name passt. Nummer
  und Name selbst prüft `tests/test_version.py`.

## Grenzen dieser Prüfung

- Geprüft mit gestellten Modellen (`ScriptedLLM`), nicht mit `qwen3:14b` selbst. Ob ein Modell
  eine Frage stellt, entscheidet es weiter selbst. Neu ist: Stellt es sie im Text, landet sie im
  Fenster.
- Eine Frage mit Vorschlägen in Klammern („Welcher Ort? (z. B. Bremen)“) gilt nicht als
  Rückfrage, weil der Text nicht mit „?“ endet.
