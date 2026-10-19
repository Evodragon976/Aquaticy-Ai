# Prüfbericht: 12.0.0 Sol

Stand: 2026-10-19. Grundlage: **12.0.0 Terra**, Commit `5c5e6f7`, Branch `Aquaticy-ai`.

## Was neu ist

**Der Modell-Knopf endet hinter dem Pfeil.** Auf dem Handy zog sich der Knopf mit dem
Modellnamen bisher über die ganze Lücke bis zum Mikrofon. Wer daneben tippte, öffnete die
Modellauswahl.

- Jetzt ist der Knopf so breit wie Name und Pfeil.
- Die Lücke bis zum Mikrofon ist leer und kein Klickfeld mehr.
- Ein langer Name darf den Platz bis zum Mikrofon nehmen und kürzt sich dann mit „…“.
  Mikrofon und Senden rutschen nie aus der Zeile.
- Auf Tablet und Computer war der Knopf schon so schmal. Dort ändert sich nichts.
- Das Modellmenü richtet sich nur nach der linken Kante des Knopfs und öffnet sich wie bisher.

Gemessen im Browser (Chromium), Abstand vom Pfeil bis zum Knopfende:

| Breite | kurzer Name (`qwen3:14b`) | sehr langer Name |
|---|---|---|
| 412 px | 9 px, Knopf endet bei 163 px, Mikrofon ab 317 px | gekürzt, endet 10 px vor dem Mikrofon |
| 390 px | 9 px | gekürzt, endet 10 px vor dem Mikrofon |
| 360 px | 9 px | gekürzt, endet 10 px vor dem Mikrofon |
| 340 px | 9 px | gekürzt, endet 10 px vor dem Mikrofon |

Bei keiner Breite scrollt die Seite seitlich. Unter 340 px zeigt der Knopf wie bisher nur „✦“.

## Fehler- und Sicherheitsprüfung

- Neu ist nur CSS. Am Server und an den Sicherheitsregeln ändert sich nichts.
- Der Anmeldeschutz aus 12.0.0 Terra wurde noch einmal durchgesehen. Es gab keine neuen Funde,
  und alle seine Tests laufen in der Volllauf-Prüfung mit.
- bandit: keine neuen Hinweise.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | alle fünf Schritte ohne Beanstandung (Rückgabewert 0): **5228 bestanden, 31 übersprungen, keine Fehlschläge** (5259 Tests, Browser-Rundgang eingeschlossen) |
| Neue Tests (`tests/test_v1200_sol.py`) | 2, bestanden |
| Browser-Rundgang | neue Prüfung in den Abschnitten 19a–d: Der Modell-Knopf endet höchstens 16 px hinter dem Pfeil |

## Geänderte Tests

- Kein bestehender Test wurde geändert. `tests/test_version.py` trägt wie bei jeder Fassung den
  neuen Namen.

## Grenzen dieser Prüfung

- Gemessen in Chromium. Safari auf dem iPhone wurde nicht geprüft. Dort gilt dasselbe CSS
  (Flexbox).
