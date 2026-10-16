# Prüfbericht: 11.2.3 Luna

Stand: 2026-10-16. Grundlage: **11.2.2 Sol**, Commit `294b92f`, Branch `Aquaticy-ai`.
Der vorhandene Stand war sauber und wurde vollständig übernommen.

## Bestätigte Fehler und Korrekturen

1. **Coworker-Rechte während laufender Arbeit.** Eine Sitzung verwendete die Regeln vom
   Beginn des Arbeitsschritts. Jeder weitere Werkzeugaufruf liest jetzt den aktuellen
   Zustand: neue Sperren, Pausieren und Löschen werden berücksichtigt. Der Scheduler prüft
   Kontosperre, Tarif und Coworker-Zustand auch zwischen zwei Arbeitsschritten erneut.
2. **Abgelaufene Freigaben.** Ohne laufenden Scheduler konnten über eine Woche alte Anfragen
   noch bestätigt werden. Die Entscheidung prüft das Ablaufdatum jetzt in derselben
   Datenbanktransaktion. Eine bereits entschiedene Anfrage bleibt nicht erneut freigebbar.
3. **Beschädigte Aktionsparameter.** Lange Anfragen wurden mitten im JSON abgeschnitten und
   beim Lesen durch leere Parameter ersetzt. Zu große Anfragen bekommen jetzt eine klare
   Fehlermeldung; passende Anfragen bleiben vollständig erhalten. Beschädigte Altbestände
   werden bei der Ausführung abgewiesen, statt Werkzeug-Standardwerte zu verwenden.
4. **Löschen bei laufendem Modellaufruf.** Ein gelöschter Coworker konnte nach seiner Antwort
   erneut Protokolle, Freigaben und Chatmeldungen erzeugen. Neue Datensätze benötigen einen
   vorhandenen Coworker; ein verspätetes Modellergebnis nach dem Löschen wird verworfen.
   Bereits vorhandene Chats bleiben entsprechend der bisherigen Löschfunktion erhalten.
5. **ZIP-Verknüpfungen beim Installieren.** Die Prüfung normalisierte nur den geschriebenen
   Pfad. Verkettete Verknüpfungen konnten tatsächlich außerhalb des Zielordners landen.
   Jetzt werden die aufgelösten Pfade vor dem Schreiben und alle Verknüpfungen nach dem
   Anlegen geprüft. Legitime Verknüpfungen innerhalb des Archivs funktionieren weiterhin.
6. **HTTP-Komprimierung bei Programm-Downloads.** Die automatische Dekompression konnte
   bereits vor der Größenprüfung viel Speicher belegen. Downloads verlangen schon bisher
   `identity`; eine davon abweichende HTTP-Komprimierung wird jetzt vor dem Lesen abgewiesen.
   ZIP-/Tar-Archive als Datei bleiben unterstützt. HTTPS-Zielliste, Größen- und
   SHA-256-Prüfung bleiben erhalten. Der gemeinsame Downloadpfad schützt auch cloudflared.
7. **Website-Stopp während der Einrichtung.** Kam eine verzögerte Cloudflare-Einrichtung
   nach dem Stoppen zurück, startete sie den Tunnel erneut. Start und Stopp sind jetzt
   synchronisiert; nach dem Stoppen wird der Tunnel nicht wieder geöffnet. Ein zweiter
   Start erzeugt keinen zusätzlichen Website-Thread, solange der erste noch läuft.
8. **Parallele erste Datenbankzugriffe.** Im Browserlauf trat ein sporadischer HTTP-500-Fehler
   auf. Gleichzeitige Initialisierungen wurden danach separat mit echten SQLite-Verbindungen
   reproduziert: Der Wechsel zu WAL konnte sofort an einer Sperre scheitern, und zwei
   Auftragsinitialisierungen konnten dieselbe Spalte ergänzen. Cache, Coworker und Aufträge
   teilen jetzt die Initialisierungssperre je Datenbank. WAL-Sperrkonflikte werden höchstens
   zehn Sekunden lang erneut versucht; andere Datenbankfehler bleiben Fehler. Normale
   Abfragen behalten ihren bisherigen Timeout. Kein Test wurde dafür übersprungen.

Neue Fehlermeldungen haben auch englische Fassungen. Keine Funktionen, Sicherheitsregeln,
bestehenden Tests oder Einwilligungsprüfungen wurden entfernt oder abgeschwächt.

## Prüfungen

Die erste Reproduktion zeigte **18 fehlgeschlagene Tests** auf dem unveränderten
Ausgangsstand. Nach den Korrekturen bestanden diese Fälle. Zusätzliche Tests prüfen
erlaubte Freigaben, Unicode-Parameter, erneute Rechtevergabe und gültige Archiv-Verknüpfungen.

| Prüfung | Ergebnis |
|---|---|
| Gezielte Prüfkette | Erste Korrekturen: **197 Tests bestanden**, keine übersprungen |
| Neue Regressionstests (`tests/test_v1123.py`) | **33 Fälle**, einschließlich erlaubter Abläufe |
| Prüfkette (`python tools/pruefung.py`) | Alle fünf Schritte erfolgreich, Rückgabewert 0 |
| Vollständige Testsuite | **4.941 bestanden, 12 übersprungen, keine Fehlschläge** (4.953 Tests) |
| Browser-Rundgang | Im Gesamtlauf erfolgreich; separat **412 Prüfungen ohne Beanstandung** |
| Abhängigkeiten (`pip-audit`) | **95 Fremdpakete geprüft, keine bekannten Schwachstellen** |
| Paketbau (`uv build`) | Wheel und Quellpaket, **74 Laufzeitdateien**, Paketversion 11.2.3 |
| Kommandozeile | `aquaticy --version` meldet **11.2.3 Luna** |
| Download-Speichertest | Vorher **48,06 MiB**, nachher **0,01 MiB** Python-Speicherspitze |

Der erste Volllauf meldete **4.933 bestanden, 12 übersprungen, einen Browser-Fehlschlag**.
Ein separater vollständiger Browserlauf bestand anschließend **412 Prüfungen**. Zur
Absicherung des sporadischen Datenbankfehlers kamen echte parallele Erstzugriffe sowie
Tests für erfolgreiche Wiederholung, begrenzte Wartezeit und unveränderte Fehlerbehandlung
hinzu. Zusätzlich bestanden **200 frische Datenbanken mit je acht parallelen Zugriffen**
den Stresstest. Nach allen Korrekturen lief die gesamte Prüfkette erfolgreich durch:
ruff ohne Beanstandung, mypy ohne Fehler in **68 Modulen**, Bandit ohne neue Hinweise,
JavaScript ohne Syntaxfehler und die vollständige Testsuite in rund **15 Minuten**.

Der Speichertest verwendet einen lokalen HTTP-Nachbau mit 16 MiB entpacktem Inhalt und
`tracemalloc`; er misst diesen Fehlerfall, keine allgemeine Beschleunigung. Die bestehende
Bandit-Baseline wurde nicht verändert. Das lokale Projekt selbst steht nicht in der
PyPI-Schwachstellendatenbank und wurde durch Codeprüfung und Tests geprüft. Paketarchive
enthalten keine lokale `.env`, Schlüsseldateien, `.git` oder `.venv`.

## Umfang und Grenzen

Geprüft wurden die neuen Coworker-, Download-, Website- und Plugin-Pfade sowie mit der
projektweiten Prüfkette alle Python-Module, das JavaScript und die bestehenden
Funktions-, Sicherheits-, Datenschutz- und Bedienungstests. Externe Dienste und
Sprachmodelle werden in den Tests nachgebildet; echte Konten, Nachrichten und
Cloudflare-Konfigurationen wurden nicht verändert. Eine Prüfung garantiert keine
vollständige Fehlerfreiheit.

Chromium und das Basisabbild der Code-Umgebung stehen zur Verfügung. Das zusätzliche
Desktop-Abbild fehlt: Die elf Desktop-/Add-on-Livetests können deshalb hier nicht laufen.
Beim DNS-Rebinding-Vergleich blockiert der Cloud-Proxy bereits die ungeschützte
Kontrollanfrage; dieser Test lässt sich hier ebenfalls nicht aussagekräftig ausführen.
Die übrigen Sicherheits- und Funktionstests dieser Bereiche bleiben Teil der Prüfkette.
