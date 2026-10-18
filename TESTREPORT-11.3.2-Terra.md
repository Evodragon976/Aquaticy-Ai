# Prüfbericht: 11.3.2 Terra

Stand: 2026-10-18. Grundlage: **11.3.2 Luna**, Commit `e484f8a`, Branch `Aquaticy-ai`.
Der Remote-Stand wurde frisch abgerufen. Es gab keine neueren Commits oder ungesicherten
lokalen Änderungen. Die Korrekturen aus Luna bleiben enthalten.

## Änderungen

- IPv6: Der Webserver wählt die passende Socket-Familie. Angezeigte URLs erhalten
  IPv6-Klammern. Bei Bindung an eine bestimmte IPv4-/IPv6-Schnittstelle wird kein
  ungebundener Loopback-Eingang mehr beworben oder im Browser geöffnet.
- Tailscale-Erkennung prüft vollständige gültige IP-Adressen und unterstützt zusätzlich
  den von Tailscale verwendeten IPv6-Bereich. Fehlerhafte Angaben wie `100.81.x.y` gelten
  nicht mehr als Tailscale-Adresse.
- Manuelle Einladungen unterstützen vollständige MagicDNS-Namen unter `*.ts.net`.
  Alle DNS-Antworten müssen im Tailscale-Bereich liegen. Vor dem Pairing wird einmal
  aufgelöst und die geprüfte IP gespeichert. Ein späterer DNS-Wechsel ändert weder
  Pairing noch RPC, Weiterleitung oder Modell-Tunnel. Die Adressfamilie muss zur lokalen
  Server-Bindung passen, damit auch die Rückverbindung funktioniert: IPv4 mit `--lan`,
  IPv6 bei expliziter IPv6-Bindung. Unpassende Ziele werden vor dem Pairing mit einem
  verständlichen Hinweis abgewiesen. Numerische LAN-Adressen bleiben unterstützt.
- Die Oberfläche erklärt die manuelle Tailscale-Verbindung und den benötigten Aquaticy-Port
  auf Deutsch und Englisch. Gleichzeitige Mehrfachklicks erzeugen keine zusätzlichen
  Einladungen. Statusabfragen pausieren im versteckten Tab und werden beim Zurückkehren
  nachgeholt. Bereits eingegebene Bestätigungscodes bleiben erhalten.
- README: Tailnet, Firewall/Zugriffsregeln, tatsächlicher TCP-Port, IPv6, Container und
  die Grenze der lokalen UDP-Suche beschrieben. Keine neuen Abhängigkeiten oder Threads.

## Prüfungen

- Fehler vor Korrektur reproduziert: unvollständige Tailscale-IP-Prüfung, IPv6-Bindung
  und URLs. Anschließend auch falsche Adressauswahl bei IPv6-Bindung sowie unpassende
  Rückwege vor dem Pairing reproduziert (3 fehlgeschlagene, 1 erfolgreicher Fall).
- **48 neue Regressionen** in `tests/test_v1132_terra.py`: MagicDNS mit beiden
  Adressfamilien, ungültige und gemischte DNS-Antworten, Auflösungsfehler, einmalige
  DNS-Prüfung mit IP-Bindung, Wechsel des DNS-Ziels während des Pairings, Zustimmung,
  falscher Code, Datenübernahme mit Backup, RPC, Wiederholungs-/Schlüsselprüfung,
  verschlüsselte Weiterleitung, Modell-Tunnel und echte IPv6-HTTP-Verbindungen.
- **Zwei zusätzliche Browserfälle** in `tests/test_cluster_http.py`: langsame Einladung
  mit Mehrfachklicks und gleichzeitigem Statusabruf; versteckter Tab mit Fortsetzen
  nach Rückkehr. Die bisherigen Fälle für Code-Eingabe, vorübergehenden Ausfall,
  ungültigen Port und verspätete Statusantworten bleiben erhalten.
- Gezielte Zwischenprüfung: alle fünf Schritte erfolgreich, **486 Tests bestanden**,
  keine übersprungenen oder fehlgeschlagenen Tests (355 Sekunden).
- Abschließende gezielte Prüfkette nach Korrektur der Adressfamilie: alle fünf Schritte
  erfolgreich, **51 Tests bestanden**, keine übersprungenen oder fehlgeschlagenen Tests.
- Die erste abgeschlossene Gesamtprüfung fand einen veralteten Übersetzungseintrag
  des ersetzten Adressfelds (5.126 bestanden, 12 übersprungen, 1 fehlgeschlagen).
  Der Eintrag wurde entfernt; die bestehende Prüfung blieb unverändert.
  Danach waren alle fünf Schritte der gezielten Prüfkette mit **85 Tests** für
  Übersetzungen, Oberfläche und Versionsangaben erfolgreich.
- Sicherheitsregeln, Abhängigkeiten und Bandit-Baseline unverändert. Die öffentliche
  Eingangssperre, Berechtigungen, Herkunftsprüfung, Größen-/Anfragegrenzen,
  Replay-Schutz, Schlüsselwechsel und verschlüsselten Tunnel werden weiter getestet.

Der abschließende Aufruf von `python tools/pruefung.py` endete mit **Rückgabewert 0**:

| Prüfung | Ergebnis |
|---|---|
| ruff | Keine Beanstandungen |
| mypy | Keine Fehler in 69 Modulen |
| Bandit mit unveränderter Baseline | Keine neuen Hinweise |
| JavaScript | Syntax erfolgreich geprüft |
| Gesamte Testsuite | **5.127 bestanden, 12 übersprungen, 0 fehlgeschlagen** (5.139 Tests) |
| Browser-Rundgang und verfügbare Docker-Livetests | Im Volllauf enthalten |
| Wheel und Quellpaket | Erfolgreich; alle 75 Laufzeitdateien bytegleich |
| Separate Wheel-Installation | CLI und Paket melden 11.3.2 Terra |

Die Testsuite benötigte **1.033 Sekunden**, rund 17 Minuten. Kein Prüfschritt wurde
übersprungen. Wie im Ausgangsstand fehlen für elf Desktop-/Add-on-Livetests die
entsprechenden Container-Abbilder; ein DNS-Rebinding-Kontrolltest wird durch den
Cloud-Proxy begrenzt. Die vorhandenen Testmarkierungen wurden nicht geändert.
Alle 50 neu hinzugekommenen Fälle sind im erfolgreichen Volllauf enthalten.
Das Quellpaket enthält die neuen Regressionen und diesen Prüfbericht.

## Grenzen

Diese Cloud-Umgebung ist mit keinem echten Tailnet verbunden. Die Tests prüfen die
Anwendungswege mit nachgebildeten Tailnet-Adressen und DNS-Antworten sowie echten lokalen
TCP-/HTTP-Verbindungen, einschließlich IPv6 und verschlüsseltem Modell-Tunnel.
Sie belegen keine reale Route oder passende Tailscale-Zugriffsregel auf den Nutzergeräten.
Die vorhandene X25519-/AES-GCM-Verschlüsselung, Zustimmung, Code-Prüfung, Wiederholungsschutz,
Ultra-Berechtigung und Sperre der Cluster-Endpunkte am öffentlichen Eingang bleiben erhalten.
