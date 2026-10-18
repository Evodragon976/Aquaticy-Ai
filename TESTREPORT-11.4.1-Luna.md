# Prüfbericht: 11.4.1 Luna

Stand: 2026-10-18. Grundlage: **11.4.0 Terra**, Commit `ecdcfee`, Branch `Aquaticy-ai`.

Gesucht wurde vor allem in dem, was seit 11.3.2 neu ist: Antworten abholen, geklärte
Angaben, Rückfrage des Planers, Umgang mit Fehlerantworten, Server-Verbund.

## Gefundene Fehler

1. **Nach 16 ungesehenen Antworten keine neuen Chats mehr** (seit 11.4.0 Luna).
   - Pro Konto hält Aquaticy höchstens 16 Chats im Speicher und räumt alte ab, aber nie einen,
     dessen Antwort noch abholbar ist.
   - Seit diese Frist eine Woche beträgt, hielt jede ungesehene Antwort ihren Chat eine Woche
     fest. Wer oft weggeht, bevor die Antwort fertig ist (genau dafür ist 11.4.0 gemacht),
     bekam nach 16 solchen Chats „Zu viele offene Chats“.

   Jetzt halten nur noch laufende Antworten ihren Chat fest, und fertige, ungesehene höchstens
   15 Minuten. Abholbar bleiben sie trotzdem eine Woche; die Antwort steht ohnehin im
   gespeicherten Verlauf.
2. **Ein laufender Lauf konnte aus dem Laufbuch fallen.** Ein Chat merkt sich höchstens 8
   Läufe. Bei schnell hintereinander gestellten Fragen flog der älteste heraus, auch wenn er
   noch lief. Nach einem Neuladen war er dann nicht mehr aufzunehmen. Jetzt fallen zuerst
   fertige Läufe heraus. Damit das Laufbuch trotzdem begrenzt bleibt, hält es höchstens 32
   Läufe; erst darüber fällt auch ein laufender heraus.
3. **Lastangaben anderer Server ungeprüft.** `runs` und `cpu` aus dem Lebenszeichen eines
   anderen Servers wurden direkt mit `float()`/`int()` gelesen. Ein Text oder `NaN` (etwa
   von einer fehlerhaften Fassung) ließ die Zuteilung **aller** Konten und die
   Verbundansicht abstürzen. Jetzt werden sie geprüft wie seit 11.3.2 die Hardware: nur echte
   Zahlen in sinnvollen Grenzen, sonst 0.
4. **Fehlerantworten ohne Inhalt.** Die Oberfläche verpackt Fehlerantworten seit 11.4.0 neu.
   Bei 204/205/304 hätte das mit einem Skriptfehler geendet, denn diese dürfen keinen
   Inhalt haben. Jetzt abgesichert.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | erster Volllauf: ein Fehlschlag (`test_hardening`, siehe „Geänderte Tests“). Danach alle fünf Schritte ohne Beanstandung (Rückgabewert 0): **5167 bestanden, 31 übersprungen, keine Fehlschläge** (5198 Tests, Browser-Rundgang eingeschlossen) |
| Jede lesende API-Anfrage mit 400, 403, 429 oder `{}` beantwortet, dann alle Fenster der Oberfläche geöffnet (Browser) | kein Skriptfehler, kein Fehlerfenster. Bei einer HTML-Fehlerseite mit 502 erscheint wie vorgesehen das Fehlerfenster |
| Fuzzing aller API-Routen, nicht angemeldet | kein HTTP 500 |
| Fuzzing angemeldet (Ultra, im Browser) | kein HTTP 500, die Sitzung bleibt gültig |
| Python 3.14.8 (neue Tests seit 11.3.0 und `test_agent`) | 316 bestanden. Ein Fehlschlag kam von meiner Änderung in Punkt 4: Der Test prüfte den alten Wortlaut und ist angepasst |
| Rückfrage-Empfänger | nur Browser-Chat und Terminal; Aufträge und Coworker werden nie gefragt |
| Neue Tests in `tests/test_v1140_terra.py` | 4 für die Funde 1–3, alle bestanden; dazu die harte Grenze in `test_hardening` |

## Geänderte Tests

- `tests/test_v1140.py::test_the_page_waits_on_429_and_always_reads_error_bodies` prüfte den
  Wortlaut `return new Response(text`. Der ist wegen Fund 4 jetzt
  `return new Response(ohneKoerper ? null : text`. Nur der Text, nicht das Verhalten.
- `tests/test_hardening.py::test_every_run_is_found_by_its_id` startete 22 Läufe, beendete
  keinen und erwartete, dass der älteste herausfällt („alte fertige Läufe werden nicht ewig
  aufgehoben“). Genau das ist Fund 2: Ein laufender Lauf darf nicht herausfallen. Der Test
  beendet seine Läufe jetzt, wie seine eigene Meldung es meint, und prüft beide Aussagen
  unverändert. Dazu prüft er neu die harte Grenze von 32 Läufen auch für laufende.

## Sicherheit

- Fund 3 betraf Angaben von Verbund-Mitgliedern. Die sind angemeldet, aber nicht unfehlbar.
  Jetzt werden alle Zahlen aus dem Lebenszeichen geprüft.
- Keine Sicherheitsregel gelockert. bandit: keine neuen Hinweise.

## Grenzen dieser Prüfung

- Kein echtes Modell und kein echter zweiter Server, wie in den Berichten davor.
