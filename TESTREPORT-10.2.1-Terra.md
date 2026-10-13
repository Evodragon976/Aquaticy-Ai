# Prüfbericht: 10.2.1 Terra

Stand: 2026-10-13. Grundlage: **10.2.0 Luna**, Commit `47e1abb`, Branch
`Aquaticy-ai`. Die neue Umgebung enthielt zunächst einen sauberen älteren
Checkout. Der aktuelle Remote-Stand wurde übernommen. Ungespeicherte Änderungen
aus der vorherigen, ausgefallenen Umgebung waren nicht mehr vorhanden; die
dokumentierten Korrekturen wurden neu eingebaut und erneut geprüft.
Die neue README-Struktur und die Funktionen des Server-Verbunds bleiben erhalten.

## Bestätigte Fehler und Korrekturen

- **Sicherheitsurteile zwischen Konten und Modellen:** Rechtsprüfung, Eingabe-
  und Antwortprüfung verwendeten gemeinsame Caches ohne Konten-, Modell- oder
  Endpunktbindung. Die Schlüssel enthalten jetzt den kanonischen Profilpfad,
  die tatsächliche Modellkonfiguration, den Prüfmodus und strukturierte
  Eingaben. Zugangsdaten werden ausschließlich in den Hash einbezogen, nicht
  im Cache abgelegt. Die aktuelle Modellfreigabe wird vor einem Treffer geprüft.
  Trennzeichen in Nutzereingaben können keine unterschiedlichen Anfragen mehr
  auf denselben Schlüssel abbilden. Rechtsurteile verfallen nach fünf Minuten;
  die bestehenden Größenlimits und der Ai-guard-Zeitraum bleiben erhalten.
  Volle Ai-guard-Caches verdrängen den ältesten Treffer einzeln. Ausfälle
  werden nicht als wiederverwendbare Urteile gespeichert.
- **Lange Werkzeugargumente:** Die bisherige Kürzung auf Anfang und Ende ließ
  die Mitte von Skripten, Dateien und Bildbeschreibungen ungeprüft. Nun werden
  alle Argumente in überlappenden Abschnitten geprüft. Jeder Cache-Eintrag ist
  zusätzlich an den gesamten Werkzeugauftrag gebunden. Eine im Grundschutz
  irrelevante Absage überspringt weder spätere Abschnitte noch die Bestätigung
  durch das Hauptmodell. Lange harmlose Dateien bleiben möglich.
- **Unbestätigter Missbrauch bei Prüferausfall:** Meldete das schnelle Modell
  einen gefährlichen Werkzeugauftrag und fiel die Bestätigung aus, konnte
  dieser im Grundschutz trotzdem ausgeführt werden. Der Auftrag wird jetzt
  angehalten, ohne aus einem unbestätigten Verdacht einen Bann oder
  Missbrauchsvermerk abzuleiten. Eine ausdrückliche Entwarnung des Hauptmodells
  bleibt wirksam. Unvollständige oder widersprüchliche VM-Urteile sowie
  unbestimmte Bildabsagen gelten als unklare Prüfung.
- **Zu kleines lokales Prüffenster:** Die vollständigen Regeln und Argumente
  passten nicht in das pauschale 2.048-Token-Fenster. Lokale Sicherheitsaufrufe
  bemessen es nun konservativ anhand der tatsächlichen UTF-8-Eingabe, ihrer
  vorbereiteten Lernhinweise und der Antwortreserve. Kurze Prüfungen behalten
  das kleine Fenster. Anbieteraufrufe ohne lokales `num_ctx` bleiben unberührt.
- **Datenschutz bei Lernen und Löschung:** Der gewöhnliche Wissensabruf zählte
  Beiträge mit veralteter oder deaktivierter Zustimmung. Nun müssen sowohl
  unabhängige Bestätigungen als auch eigene Beiträge eine aktive Zustimmung
  zur aktuellen Datenschutzfassung haben. Lesen erteilt keine Zustimmung.
  Kontoleerung und Kontolöschung entfernen zusätzlich die kurzlebigen
  lokalen Sicherheitsurteile; bereits laufende Prüfungen dürfen den geleerten Cache
  nicht wieder befüllen. Verbrauch und gespeicherter Missbrauchsschutz werden
  weiterhin gemäß dem jeweiligen Löschweg behandelt.
- **Speicherverbrauch komprimierter Antworten:** Bei der LAN-Titelabfrage
  wurde ein Netzstück vollständig entpackt, bevor das Limit griff. Ein
  kontrollierter 16-MiB-Gzip-Fall belegte zuvor **47.609.545 Bytes** zusätzlichen
  Python-Speicher. Die Titelabfrage begrenzt jetzt bereits das Entpacken;
  der Regressionstest verlangt weniger als 4 MiB. Auch die neue Ollama-
  Modellsuche des Verbunds liest gestreamt mit Zeit-, Größen- und JSON-
  Tiefenlimit. Normale GGUF-Auswahl und Titel großer Seiten bleiben möglich.
- **Verbund beim Stoppen und Neustarten:** Nach `Manager.stop()` konnte ein
  weiterer wartender Takt neue Prozesse starten. Gestoppte Manager führen
  keinen Takt mehr aus. Nach einer langsamen Modellabfrage werden Abschalten,
  Masterwechsel, neuer Modellwunsch und Neustart erneut berücksichtigt.
  Tunnel schließen ihre Leser auch nach fehlgeschlagenem Handshake, wecken
  den blockierenden Listener beim Stoppen und weisen verspätete Verbindungen
  ab. Die lokale Annahme begrenzt parallele Tunnel auf das bestehende Limit.
- **Bedienung bei langsamen Prozessen:** Schalt- und Neustartaktionen stoßen
  die Arbeit im Hintergrund an. Ein Neustartwunsch wartet nicht mehr auf die
  Sperre eines laufenden Modellstarts. Modellvalidierung, Ultra-/Masterrechte,
  authentifizierte Kopplung, Verschlüsselung, Replay-Schutz und die
  Bindung der Modellprozesse an Loopback bleiben erhalten. Während des
  Anlaufens zeigt die Oberfläche einen Wartehinweis.

## Prüfungen

- **39 fehlgeschlagene Regressionen auf dem Ausgangsstand reproduziert**,
  ein zusätzlicher Test bewahrte bereits funktionierende Modellbestätigung.
  Die finalen **66 neuen Regressionen** decken die Korrekturen, positive
  Gegenfälle und den Schutzschalter im echten Chromium ab.
- Zwischenprüfung: **213 Tests bestanden** in 47,02 Sekunden. Zusätzlich
  **64 Tests bestanden** in 11,22 Sekunden (63 neue Regressionen und
  Versionsprüfung). Die abschließende Integrationsprüfung bestand mit
  **119 Tests** in 21,86 Sekunden, einschließlich dreier zusätzlicher Fälle
  für die Komprimierungsverhandlung der LAN-Abfrage. Diese Durchläufe
  überschneiden sich und sind nicht zu addieren.
- Live-Docker-Sandbox: **2 Tests bestanden** in 5,04 Sekunden; Schreiben im
  eigenen Arbeitsordner, gesperrtes Wurzeldateisystem, gesperrtes Netzwerk und
  Pfadgrenzen wurden mit `python:3.12-slim` geprüft.
- Gesamtsuite: **4.576 bestanden, 12 übersprungen, keine Fehler**, in
  **872,07 Sekunden**. Der vollständige Chromium-Rundgang ist enthalten.
  Elf Auslassungen betreffen fehlende Desktop-/Add-on-Abbilder; eine
  DNS-Rebinding-Kontrollanfrage wird schon vom Cloud-Proxy blockiert.
  Zwei bestehende Pydantic-Warnungen betreffen das `ReadOnly`-Feld einer
  Fremdbibliothek. Die abschließende LAN-Anpassung zur expliziten Aushandlung
  der Komprimierung und ihre drei zusätzlichen Fälle wurden separat im
  oben genannten finalen 119-Test-Lauf geprüft.
- Ruff, AST-/Bytecode-Prüfung und `git diff --check`: bestanden. Untersucht
  wurden **62 Python-Module mit 49.384 Quellzeilen**.
- Abhängigkeiten: **89 Fremdpakete, keine bekannten Schwachstellen** laut
  `pip-audit`; das lokale Projekt ist von der PyPI-Prüfung ausgenommen.
  `uv pip check`: **90 kompatible Pakete**. Keine neue Projektabhängigkeit.
- Installierte CLI: **10.2.1 Terra**; Paketmetadaten: **10.2.1**.
- Wheel und Quellarchiv: erfolgreich gebaut und gegen den Arbeitsstand
  geprüft. Alle **68 Programmdateien** stimmen bytegenau überein; beide
  Pakete tragen **10.2.1**. Das Quellarchiv enthält die README, Constraints,
  Regressionen und diesen abgeschlossenen Prüfbericht.

## Grenzen und verbleibende Hinweise

Bandit meldet wie im Ausgangsstand **122 Hinweise: 98 niedrig, 23 mittel,
einen hoch**. Der Vergleich nach Datei, Regel, Schwere und Befundtext zeigt
keine neuen Befundarten; es wurden keine Unterdrückungen hinzugefügt. Solche
Scannerhinweise wurden im Kontext geprüft, nicht pauschal als Lücken gewertet.

Der hohe Hinweis betrifft die bestehende LAN-Titelabfrage mit `verify=False`:
Sie erlaubt selbstsignierte Zertifikate ausschließlich für private IPv4-
Geräte, sendet keine Zugangsdaten, folgt keinen Weiterleitungen und nutzt
keinen Umgebungsproxy. Zeit- und Größenlimit bleiben wirksam. Ein gelesener
Gerätetitel ist kein Identitätsnachweis; diese Ausnahme wird nicht als
behobene TLS-Prüfung ausgegeben.

Modellantworten sind in den Regressionstests kontrolliert vorgegeben. Die Tests
prüfen die Durchsetzung der Schutzregeln, nicht die Zuverlässigkeit jedes
Sprachmodells bei der inhaltlichen Bewertung. Verbundtests verwenden echte
Sockets, HTTP, Verschlüsselung und kontrollierte Ersatzprozesse für llama.cpp;
eine verteilte Berechnung mit mehreren physischen GPUs wurde nicht ausgeführt.
Der Benutzer-Desktop und externe Konten werden nur soweit geprüft, wie es
die dokumentierten Testvoraussetzungen erlauben. Die Prüfung ist keine
Garantie vollständiger Fehler- oder Schwachstellenfreiheit.

Private Recherche bleibt kontoeigen und höchstens 48 Stunden nutzbar;
gemeinsame öffentliche Quellenauszüge bleiben höchstens 30 Tage nutzbar.
Die freiwillige Lernzustimmung `2026-10-07.1`, die Inhaltsfilter, Widerruf,
Quellenbindung und Löschwege bleiben erhalten. Es wurden keine Features
oder Sicherheitsprüfungen entfernt.
