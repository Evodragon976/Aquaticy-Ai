# Prüfbericht: 12.2.2 Sol

Stand: 2026-10-20. Grundlage: **12.2.1 Sol**, Commit `27dfe2a`, Branch `Aquaticy-ai`.

## Was behoben ist: Die Prüfung lehnte bei Modellen über einen API-Schlüssel ab

Gemeldet: Mit einem Modell über NVIDIA NIM oder Mistral antwortete Aquaticy: „Ich konnte die
Anfrage gerade nicht gegen den Rechtsrahmen prüfen — das Modell für die Prüfung hat nicht
geantwortet.“

### Warum

Die Rechtsprüfung (`aquaticy/guardrails.py`) fragt das schnelle Modell und das Hauptmodell aus
den Einstellungen. Der Chat arbeitet aber oft mit einem anderen:

- im **Code-Modus** mit dem Code-Modell; die Modellwahl im Chat stellt dort das Code-Modell um,
  nicht das Hauptmodell;
- im **Pro-Modus** mit dem stärksten erreichbaren Modell;
- bei der **automatischen Modellwahl** mit dem gewählten Modell.

Waren schnelles und Hauptmodell lokal und Ollama lief nicht, antwortete keines davon. Die
Prüfung lehnte dann ab, obwohl das Modell, mit dem der Chat tatsächlich arbeitet (über den
API-Schlüssel), erreichbar war.

Ai-guard selbst hatte dasselbe Problem bei seiner Einschätzung von Nachrichten. Fiel das
schnelle Modell aus, blieb sie einfach aus. Gesperrt wurde dann nichts, geprüft aber auch
nichts.

### Was jetzt gilt

- **Rechtsprüfung:** Wie bisher zuerst das schnelle Modell, dann das Hauptmodell. Liefert keines
  von beiden ein Urteil, fragt sie das Modell, mit dem der Chat in diesem Durchlauf arbeitet,
  und im Code-Modus auch das Code-Modell. Das gilt für die Anfrage und für jeden geprüften
  Werkzeugaufruf.
- **Ai-guard:** Fällt das schnelle Modell aus, fragt es das Hauptmodell.

### Was sich nicht ändert (Sicherheit)

- **Nichts wird abgeschaltet oder übersprungen.** Kommt auch vom Modell des Chats kein Urteil,
  lehnt die Prüfung weiter ab, genau wie vorher. Das prüft ein Test.
- Ein Nein des Ersatzmodells gilt wie jedes andere.
- Als Ersatz kommt nur ein Modell in Frage, mit dem der Chat ohnehin arbeitet und das das Konto
  ohnehin nutzen darf. Eine eigene Verbindungsadresse gilt wie bisher nur für den Anbieter des
  Hauptmodells. Der Ersatz öffnet also keinen Weg zu einem selbst eingerichteten
  „Prüfserver“.
- Urteile des Ersatzmodells werden nicht gemerkt. Läuft Ollama wieder, prüft beim nächsten Mal
  wieder das eingestellte Modell.
- Das Ersatzmodell wird erst gefragt, wenn die beiden eingestellten Modelle ausfallen. Läuft
  alles, gibt es keinen zusätzlichen Aufruf.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | alle fünf Schritte ohne Beanstandung (Rückgabewert 0): **5433 bestanden, 31 übersprungen, keine Fehlschläge** (5464 Tests, Browser-Rundgang eingeschlossen) |
| Neue Tests (`tests/test_v1222_sol.py`) | 10, alle bestanden. Darunter der gemeldete Fall in Code- und Pro-Modus und die Gegenprobe ohne Ersatz, die genau die gemeldete Absage zeigt. |
| Rechtsprüfung, Ai-guard, eigene Schlüssel (`test_guardrails`, `test_aiguard`, `test_own_keys` u. a.) | unverändert bestanden |

## Geänderte Tests

- Keiner. `tests/test_version.py` trägt wie bei jeder Fassung die neue Nummer.

## Grenzen dieser Prüfung

- Kein echter Mistral- oder NVIDIA-Schlüssel, kein echtes Ollama. Die Modelle sind nachgestellt:
  lokale fallen aus, das API-Modell antwortet.
- Unterstützt ein Anbieter das erzwungene JSON-Format der Prüfung nicht und antwortet ohne
  lesbares Urteil, lehnt die Prüfung wie bisher ab („keine eindeutige Antwort“). Mit echten
  Schlüsseln habe ich das nicht prüfen können.
