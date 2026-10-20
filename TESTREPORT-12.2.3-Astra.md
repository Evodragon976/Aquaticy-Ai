# Prüfbericht: 12.2.3 Astra

Stand: 2026-10-20. Grundlage: **12.2.2 Astra**, Commit `28dc5b3`, Branch `Aquaticy-ai`.

## Was gemeldet war

Mit 12.2.2 Astra zeigte die Absage zum ersten Mal die Ursache:

> `nvidia_nim/meta/llama-3.3-70b-instruct: … Error code: 410 - Gone … The model
> 'meta/llama-3.3-70b-instruct' has reached its end of life`

NVIDIA hat das Modell abgeschaltet. Laut mehreren Berichten traf es am 26.08.2026 auch
`meta/llama-3.1-8b-instruct`. Das waren genau die beiden Modelle, die Aquaticy für NVIDIA
vorschlug: das Hauptmodell und das schnelle Modell, mit dem auch die Rechtsprüfung zuerst
prüft. Fiel beides weg, kam nie ein Urteil, und es blieb bei der Absage.

Dazu der Wunsch: In der Modellwahl sollen nur Modelle stehen, die auch verfügbar sind, und
die Nemotron-Modelle von NVIDIA.

## Was neu ist

1. **Abgeschaltete Modelle kennt Aquaticy.**
   - Die beiden genannten stehen fest in einer Liste (`system.RETIRED_MODELS`).
   - Antwortet ein Anbieter auf irgendein Modell mit „410 Gone“ oder „end of life“, merkt sich
     Aquaticy das bis zum Neustart. Das gilt beim Chat, bei den Prüfungen und bei jedem anderen
     Aufruf.
   - Ein abgeschaltetes Modell gilt nicht mehr als nutzbar, auch mit Schlüssel.
2. **Die Modellwahl zeigt nur Verfügbares.**
   - Hat das Konto einen Anbieter über das Add-on eingerichtet, stehen dort nur die Modelle,
     die der Anbieter dabei genannt hat, ohne abgeschaltete, höchstens acht je Anbieter.
   - Bei NVIDIA kommen die Nemotron-Modelle zuerst.
   - Ohne eine solche Liste, etwa bei einem Schlüssel des Betreibers, gibt es wie bisher
     Arbeitspferd und schnelles Modell, aber nie ein abgeschaltetes.
3. **Neue NVIDIA-Standardmodelle:** `nvidia/llama-3.3-nemotron-super-49b-v1.5` als Hauptmodell,
   `nvidia/nvidia-nemotron-nano-9b-v2` als schnelles Modell. Auch Einrichtung, Hilfetexte und
   README nennen nicht mehr das abgeschaltete Modell.
4. **Ersatz statt Fehler.** Ist das gewählte Modell abgeschaltet, nehmen Chat und Prüfungen
   ein Modell desselben Anbieters aus dessen Liste.
   - Fürs Hauptmodell möglichst ein Nemotron, fürs schnelle ein kleines Modell.
   - Merkt der Chat das erst beim Aufruf, sagt er es: „… gibt es beim Anbieter nicht mehr –
     Aquaticy nimmt …“.
   - Ohne Liste wird nicht geraten. Dann bleibt es bei einer klaren Meldung.
5. **Klare Meldung:** Statt des rohen Fehlertexts steht in der Absage „… hat der Anbieter
   abgeschaltet (410, Ende der Laufzeit). Bitte im Chat ein anderes Modell wählen.“
6. **Beim Einrichten von NVIDIA** sortiert Aquaticy die Liste neu: Nemotron-Arbeitspferd und
   kleines Nemotron zuerst, dann die übrigen Nemotron-Modelle, dann der Rest.

7. **Kein sinnloser zweiter Versuch mehr:** Seit 12.2.2 Astra fragt die Prüfung ein Modell
   noch einmal ohne Schema, wenn der Anbieter es ablehnt. LiteLLM meldet aber manches unter
   einem allgemeinen Namen, etwa „InternalServerError: 403 Forbidden“ (im Rundgang gesehen).
   Jetzt entscheidet auch der HTTP-Status: Nur 400 und 422 deuten aufs Schema. Bei 401, 403,
   404, 410, 429 und 5xx wird nicht wiederholt.

## Sicherheit

- Die Prüfungen bleiben an. Ein Ersatz kommt nur aus der Liste, die der Anbieter dem Konto
  genannt hat, also bei demselben Anbieter, mit demselben Schlüssel und denselben Grenzen. Nie
  wechselt Aquaticy ungefragt den Anbieter.
- Ohne Urteil lehnt die Prüfung weiter ab.
- bandit: keine neuen Hinweise.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | erster Volllauf: zwei Fehlschläge (siehe unten). Zweiter Volllauf: alle fünf Schritte ohne Beanstandung (Rückgabewert 0), **5454 bestanden, 31 übersprungen, keine Fehlschläge** (5485 Tests, Browser-Rundgang eingeschlossen) |
| Neue Tests (`tests/test_v1223_astra.py`) | 12, alle bestanden |
| Browser-Rundgang, einzeln | 440 Punkte geprüft, keine Beanstandung |

## Geänderte Tests

Alle wegen der gewollten Änderung. Sie erwarteten als NVIDIA-Standard die abgeschalteten
Modelle:

- `test_agent::test_the_agents_run_on_the_small_model` und
  `test_agent::test_the_coding_models_are_offered_for_code`: die neuen Nemotron-Standardmodelle.
- `test_luna::test_the_backup_model_follows_the_active_provider`: Das Ausweichmodell ist jetzt
  das kleine Nemotron.
- `test_own_keys` (`NVIDIA`): das Nemotron-Hauptmodell statt Llama 3.3 70B. Die Prüfungen, dass
  Schlüssel und Modelle nur dem eigenen Konto gehören, sind unverändert.
- `test_v1130::test_what_counts_as_usable`: Das Nemotron-Modell ist mit Schlüssel nutzbar, und
  neu wird geprüft, dass das abgeschaltete es nicht mehr ist.
- `test_web::test_the_ui_shows_what_a_key_looks_like`: Das Beispiel für einen NVIDIA-Schlüssel
  nennt jetzt das Nemotron-Modell.
- `test_linked::test_nvidia_checks_the_key_with_one_token_and_keeps_only_chat_models`: Die
  Liste enthält jetzt Nemotron-Modelle, und erwartet wird die neue Reihenfolge (Nemotron
  zuerst). Gefiltert wird weiter genauso.

## Im ersten Volllauf gefunden

- `test_web::test_the_ui_shows_what_a_key_looks_like` erwartete als Beispiel noch das
  abgeschaltete Modell. Es ist jetzt das Nemotron-Modell (gewollte Änderung).
- `test_rundgang`: Eine Höhenmessung im Browser („Schalterzeilen …px hoch“) schlug unter der
  Last des Volllaufs fehl. Einzeln lief der Rundgang ohne Beanstandung (440 Punkte). Diese
  Fassung ändert an der Oberfläche nichts. Im zweiten Volllauf lief er ohne Beanstandung.
- Dabei aufgefallen: der sinnlose zweite Versuch bei 403 (Punkt 7).

## Grenzen dieser Prüfung

- Kein Netzzugang zu NVIDIA. Die Namen der neuen Standardmodelle stammen aus Berichten nach der
  Abschaltung, nicht aus einer eigenen Abfrage. Deshalb gilt mit eingerichtetem Add-on nur, was
  NVIDIA dem Konto selbst nennt. Ist ein Standardname dort nicht dabei, nimmt Aquaticy ein
  Modell aus der Liste.
- Das Code-Modell für NVIDIA (`qwen/qwen2.5-coder-32b-instruct`) ist unverändert. Ob es noch
  läuft, konnte ich nicht prüfen. Wird es abgeschaltet, greift derselbe Ersatz.
- Die Liste stammt aus dem Moment der Einrichtung. Ist sie alt, hilft „Aktualisieren“ beim Add-on.
