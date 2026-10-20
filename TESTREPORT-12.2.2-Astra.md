# Prüfbericht: 12.2.2 Astra

Stand: 2026-10-20. Grundlage: **12.2.2 Sol**, Commit `82b59aa`, Branch `Aquaticy-ai`.

## Was gemeldet war

Nach 12.2.2 Sol, im Normal-Modus mit `mistral-medium-latest`: Auf „Wie viel Uhr ist es“ kam
nach einer Sekunde die Absage „Ich konnte die Anfrage gerade nicht gegen den Rechtsrahmen
prüfen — das Modell für die Prüfung hat nicht geantwortet.“

Das Ersatzmodell aus 12.2.2 Sol greift hier nicht: Im Normal-Modus ist Mistral selbst das
Hauptmodell, und der Aufruf bei Mistral scheitert. Warum, verschluckte die Prüfung bisher. Sie
kannte nur „hat nicht geantwortet“.

## Was ich prüfen konnte und was nicht

Nachgestellt und in Ordnung:

- Der Schlüssel aus dem Add-on kommt in die Einstellungen der Prüfung.
- Er geht an Mistral, als schnelles Modell an `mistral-small-latest`, als Hauptmodell an
  `mistral-medium-latest`. Eine Ollama-Adresse des Servers geht nicht mit.
- Die Anfrage geht durch die Modellsperre, das Kontingent und die Aufrufschicht.
- Gegen eine nachgestellte Mistral-Schnittstelle kommt ein Urteil.

Nicht prüfen konnte ich den echten Mistral-Aufruf. Hier gibt es keinen Schlüssel. Die
wahrscheinlichste Ursache ist der einzige Unterschied zum normalen Chat: Die Prüfung erzwingt
ein JSON-Schema (`response_format`). Lehnt Mistral es mit 400/422 ab, scheitert genau dieser
Aufruf, und zwar schnell, wie gemeldet.

## Was neu ist

1. **Zweiter Versuch ohne Schema.** Scheitert ein Prüfaufruf, fragt die Prüfung dasselbe Modell
   noch einmal ohne erzwungenes Schema. Der Prompt verlangt ohnehin reines JSON, und das Urteil
   wird genauso streng gelesen. Das gilt für die Rechtsprüfung und für Ai-guard.
   - Nicht wiederholt wird bei Fehlern, an denen das Schema nichts ändert: Zeit abgelaufen,
     keine Verbindung, Schlüssel abgelehnt (401/403), Grenze erreicht, Modell unbekannt,
     Kontingent. Dort gäbe es nur doppelte Wartezeit.
2. **Die Absage nennt die Ursache.** Unter dem gewohnten Satz steht jetzt zum Beispiel
   ``Fehler: `mistral/mistral-medium-latest: AuthenticationError: …` `` (gekürzt auf 240
   Zeichen). Dasselbe steht im Serverprotokoll (`aquaticy.guardrails`, `aquaticy.aiguard`).
   - Herausgefiltert werden alle Schlüssel des Kontos und des Servers, alles hinter „Bearer“,
     „key“, „api_key“ und „token“ sowie jede Adresse („<Adresse>“). Die Absage sieht jedes Konto,
     und Serveradressen gehen es nichts an.

Kommt die Absage weiter, steht damit da, was Mistral meldet. Daran lässt sich die Ursache
gezielt beheben.

## Sicherheit

- Nichts ist abgeschaltet oder übersprungen. Ohne lesbares Urteil lehnt die Prüfung weiter ab:
  „unklar“, wenn das Modell ohne Schema etwas anderes als das Urteil schreibt; „ausfall“, wenn
  kein Modell antwortet. Beides prüfen Tests.
- Die Fehlermeldung in der Absage enthält keine Schlüssel und keine Adressen (Test mit Schlüssel,
  Bearer-Token und Anbieteradresse im Fehlertext).
- bandit: keine neuen Hinweise.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | alle fünf Schritte ohne Beanstandung (Rückgabewert 0): **5442 bestanden, 31 übersprungen, keine Fehlschläge** (5473 Tests, Browser-Rundgang eingeschlossen) |
| Neue Tests (`tests/test_v1222_astra.py`) | 9, alle bestanden |
| Tests aus 12.2.2 Sol, Rechtsprüfung, Ai-guard | unverändert bestanden |

## Geänderte Tests

- Keiner. `tests/test_version.py` trägt wie bei jeder Fassung den neuen Namen.

## Grenzen dieser Prüfung

- Kein echter Mistral-Schlüssel. Ob das Schema die Ursache war, zeigt erst der nächste Versuch
  bei dir. Wenn nicht, steht die tatsächliche Ursache jetzt in der Absage.
