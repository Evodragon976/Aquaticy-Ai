# Änderungen

Was sich in den einzelnen Fassungen von Aquaticy geändert hat, die neueste zuerst.
Die aktuelle Fassung steht oben in der [README](README.md).

**Neu in 15.8.9:**

- **Aquaticy Standard:** ein neues Modell in der Modell-Auswahl. Es antwortet ohne Sprachmodell
  und ohne Schlüssel. Es rechnet (auch Prozente, Wurzeln, Einheiten), kennt Datum, Uhrzeit,
  Feiertage und besondere Tage und holt Wetter, Wechselkurse, Nachrichten und Wissen aus
  Wikipedia, jeweils mit Quelle. Es merkt sich im Gespräch den Ort: Nach „Für welchen Ort?“
  reicht „Erkelenz“, danach gehen „und morgen?“ und „was soll ich anziehen?“. Mehr dazu unter
  [Ganz ohne Modell: Aquaticy Standard](README.md#ganz-ohne-modell-aquaticy-standard).
- **Hallo, Danke und Co.** beantwortet Aquaticy wie bisher sofort selbst, mit jedem Modell.
- **Mitlesen entfernt:** Den Schalter „Aktionen mitlesen“ gibt es nicht mehr. Die Gedanken
  zeigt weiter „Denken“ in der Modell-Auswahl.
- **Links:** README, Paket und Kennung bei Abrufen zeigen jetzt einheitlich auf
  `Evodragon976/Aquaticy-Ai`.

**Neu in 15.8.8:**

- **Vercel baut wieder.** Der Build brach mit `PYTHON_ENTRYPOINT_NOT_FOUND` ab. Jetzt steht in
  `pyproject.toml` ein Einstieg für Vercel: eine schlichte Startseite mit Anleitung. Aquaticy
  selbst läuft dort nicht, siehe README, Abschnitt Vercel.

**Neu in 15.7.8:**

- **Modell für die Agenten selbst wählen.** In *Modelle und Verbindungen* gibt es eine Auswahl
  „Modell für die Agenten“ mit deinen lokalen Modellen (zum Beispiel aus Ollama). Die Agenten
  sind die Helfer, die parallel suchen und lesen. Steht sie auf „Automatisch“, bleibt alles wie
  bisher: Mit einem Cloud-Modell (Mistral, NVIDIA) nimmt Aquaticy ein schnelles Modell
  desselben Anbieters.
- **Aufgeräumte README.** Die Änderungen der früheren Fassungen stehen jetzt in
  [CHANGELOG.md](CHANGELOG.md).
- **Korrekturen:** Das Protokoll des Website-Tunnels wird mit Abstand gekürzt (vorher schrieb
  ab 5 MB jede neue Zeile die ganze Datei neu). Schlüsseldatenbank: relative und absolute
  Pfade teilen sich eine Sperre. HTTPS im Heimnetz nutzt nach einem Portwechsel den neuen
  Kontext. Tailscale-IPv6-Adressen mit Schnittstellenangabe werden erkannt.
- **Google:** Nach dem Trennen kann eine verspätete Anmeldung die Verbindung nicht mehr
  zurückholen, und eine ältere Anmeldung überschreibt keine neuere mehr.
- **Feeds:** Ungültige Adressen (zum Beispiel `https://@example.org/feed` oder mit Leer- und
  Steuerzeichen) werden abgelehnt; schon gespeicherte werden nicht mehr geladen.
- **Zertifikate der eigenen Domain:** Die Kette wird vollständig geprüft – Signierrecht,
  Pfadlänge und Namensbeschränkungen der Zwischenstellen, und das Serverzertifikat selbst
  darf keine Zertifizierungsstelle sein.

**Neu in 15.7.7:**

- **100 bestätigte Fehlerursachen behoben.** Gegenproben decken HTTPS, Messenger,
  Gedächtnis, GitHub, Google, Secure Pro, Speicher, Datenquellen und die Oberfläche ab.
  Mehrere Testfälle für dieselbe Ursache zählen dabei nur einmal.
- **Verbindungen und Freigaben bleiben unter Kontrolle.** Verspätete GitHub-Anmeldungen
  heben ein Abmelden nicht auf. Messenger prüfen Empfänger und Freigaben vor weiteren
  Nachrichten erneut. Fehlgeschlagene Zustellungen und Sicherheitswarnungen werden wiederholt.
- **HTTPS bleibt konsistent.** Zertifikate werden zusammen mit ihren Schlüsseln ersetzt.
  Beschädigte Paare, falsche Aussteller und abgelaufene Zwischenzertifikate werden erkannt.
  Gleichzeitiges Einrichten erzeugt keine widersprüchlichen Identitäten.
- **Weniger unnötige Arbeit.** Gleichzeitige Cache-, Home-Assistant- und Ollama-Abfragen
  teilen ihre laufende Arbeit. DNS-Abfragen und Netzwerkantworten haben feste Grenzen.
  Modellvorschläge berücksichtigen Speicher- und CPU-Grenzen des Containers.
- **Zuverlässigere Daten.** Deutsche Uhrzeiten, Gedächtniskorrekturen, PR-Basisänderungen,
  UTF-16/32-Quelldateien, Feed-Namensräume, Währungskurse und Mailtabellen sind korrigiert.
  Secure Pro unterscheidet zurückkehrende Geräte und neue Dienste von bestehenden.
- **Private Dateien und Bedienung.** Gleichzeitige Schreibvorgänge beachten den Speicherdeckel.
  Unterbrochene Schreibvorgänge erhalten die vorige Datei. Im geöffneten Dialog bleibt der
  Tastaturfokus im Dialog, auch auf dem Handy. Tunnel-Protokolle wachsen nicht unbegrenzt.
- **Server-Erkennung berichtigt.** `aquaticy` ohne Unterbefehl startet den Terminalchat.
  Nur ein ausdrücklicher `web`-Aufruf zählt als Webserver. Unter Linux bleibt der pidfd
  bis zum bestätigten Prozessende offen, damit eine wiederverwendete PID nichts verwechselt.

**Neu in 15.5.6:**

- **Meldungen auch an die eingetragenen Nummern.** Meldungen von Secure Pro (Angriffe,
  Schwachstellen) und von den Coworkern gehen jetzt auch an die Nummern, die du beim
  Messenger eingetragen hast. Das gilt, wenn dort „Mein Chat und diese Nummern“ (oder mehr)
  gewählt und der Messenger an ist. Es zählen nur Nummern mit Landesvorwahl
  (`+49 …` oder `0049 …`); Namen und Nummern wie `0151 …` bekommen nichts. Höchstens zehn
  Nummern, jede mit eigener Grenze pro Stunde. „Schreib mir das auf WhatsApp“ geht weiter
  nur an deinen eigenen Chat.
- **Website zeigt wieder die richtige Version.** Ein alter Aquaticy-Prozess hinter der
  Anmeldeseite wurde beim Start nicht erkannt (die Seite nennt keine Version). Die neue
  Version wich dann auf den nächsten Port aus, und unter der gewohnten Adresse lief die alte
  weiter. Jetzt erkennt Aquaticy den alten Prozess am Programm selbst und beendet ihn.

**Neu in 15.5.5:**

- **Google verbinden geht wieder.** Aquaticy öffnet sich unter `http://127.0.0.1:8765`, Google
  schickte aber nach `http://localhost:8765` zurück. Für den Browser sind das zwei Adressen:
  Anmeldung und Ablauf-Cookie fehlten, die Verbindung scheiterte. Jetzt nutzt der Rücksprung
  dieselbe Adresse wie dein Browser. Kommt er woanders an (anderes Gerät, andere Adresse),
  zeigt die Seite die Adresse zum Kopieren für die Einstellungen.
- **Erschlossenes Wissen merken.** Fragst du „Wie alt bin ich?“ und beantwortest die Rückfrage
  mit einer Rechnung (zum Beispiel über den Geburtstag deiner Mutter), merkt sich Aquaticy das
  Ergebnis. Gespeichert wird das Geburtsdatum, das Alter rechnet Aquaticy jeden Tag neu aus.
  „Ich bin am 15.03.2001 geboren“ erkennt es auch direkt.
- **Antworten als ganzer Satz.** „Wie heiße ich?“ beantwortet Aquaticy sofort mit „Du heißt
  Louis.“, ohne langes Nachdenken. Das gilt auch für Wohnort, Alter und Geburtstag. Steht die
  Angabe nicht im Gedächtnis, fragt Aquaticy nach.
- **„Schreib mir das auf WhatsApp/Signal“.** Aquaticy schickt die Nachricht selbst in deinen
  eigenen Chat. An andere Personen schickt es nichts. Hat Aquaticy vorher fremde Inhalte
  gelesen, fragt es erst nach.
- **Secure Pro meldet Angriffe und Schwachstellen wieder per WhatsApp/Signal.** Bisher zählte
  eine Meldung als zugestellt, sobald sie im Secure-Pro-Chat stand. Scheiterte der Messenger,
  kam sie dort nie an. Jetzt versucht Aquaticy es bei der nächsten Prüfung erneut. Warnungen
  gehen auch raus, wenn der Chat über den Messenger aus ist.
- **HTTPS im Heimnetz und über Tailscale.** Mit `--lan` oder im Hintergrund ist Aquaticy auch
  unter `https://aquaticy.local:8443` erreichbar und über Tailscale unter
  `https://<rechner>.<tailnet>.ts.net:8443`. Das Tailscale-Zertifikat ist echt (dafür im
  Tailnet „HTTPS Certificates“ einschalten). Fürs Heimnetz lädst du einmal je Gerät das
  Zertifikat unter `/zertifikat` herunter und vertraust ihm. Es gilt nur für Adressen im
  Heimnetz. `aquaticy.local` braucht mDNS (avahi oder `pip install zeroconf`). Abschalten mit
  `AQUATICY_HOME_HTTPS=false`, anderer Port mit `AQUATICY_HTTPS_PORT`.
- **Immer deutsche Zeit.** Aquaticy rechnet mit der Zeit in Deutschland, mit Sommer- und
  Winterzeit, egal wie die Uhr des Servers steht (im Container meist UTC). Das Modell kennt
  Datum und Uhrzeit. Coworker-Aufträge wie „jeden Tag um 8 Uhr“ laufen um 8 Uhr deutscher
  Zeit, im Sommer wie im Winter. Tageszähler, Exporte und Secure-Pro-Zeiten nutzen sie auch.
- **Aufgeräumt:** rund 2900 überflüssige Leerzeilen im Code entfernt, ohne Änderung am
  Programm (geprüft über den Syntaxbaum).

**Neu in 15.4.5: 66 weitere nachgewiesene Fehlerursachen korrigiert.**

Die Gegenproben für alle 66 Ursachen scheitern auf dem unveränderten Stand 15.4.4.
Varianten derselben Ursache zählen nur einmal. 200 unterschiedliche Fehler sind damit
nicht nachgewiesen; unbestätigte Vermutungen zählen nicht als Fehler.

- **Datenschutz und Coworker:** Persönliche Chatdaten brauchen auch beim Werkzeugzugriff
  eine Freigabe. Das Löschen persönlicher Notizen folgt der Speicherregel und wartet bei
  „Fragen“ auf Zustimmung. Zurückgezogene Freigaben verhindern neue Zugriffe und das spätere
  Übernehmen importierter Notizen. Änderungen an VM-Netzrechten gelten auch für Coworker.
- **Serververbund und Einstellungen:** Ungültige Profileinträge führen nicht zur Löschung
  lokaler Daten. Abgebrochene oder zu große Dateiübertragungen werden verworfen. Datei- und
  Ordnerwechsel funktionieren. Fehlgeschlagene Datenbankkopien erhalten die vorherige Kopie.
  Parallele Änderungen der Einstellungen bleiben erhalten; Geheimnisse verschwinden beim
  Umzug in den Tresor auch aus mehrzeiligen dotenv-Zuweisungen.
- **Exporte und Speicher:** Exporte eines befüllten Chats enthalten dessen eigene Beiträge
  und Produktdaten. Kopien überschreiben keine bestehenden Dateien. Private Dateien bekommen
  eingeschränkte Rechte. Spracherkennungsmodelle verbrauchen nicht das persönliche
  Notizkontingent. Ungültige Kennungen löschen oder genehmigen keine anderen Einträge.
- **Netz und Oberfläche:** Secure Pro beginnt nach dem Widerruf keine weiteren Scan-Anfragen.
  Die Gerätesuche nutzt bereits bestätigte Portantworten statt sie nochmals abzufragen.
  Proxyketten, fragmentierte Dienstantworten, SSH-Banner und nmap-Status werden genauer
  ausgewertet. Add-ons und Coworker erholen sich nach kurzen Verbindungsabbrüchen.
- **Lange Texte:** Die Sicherheitsprüfung wiederholt weniger Wortarbeit. Die Regeln und
  Zeitgrenzen bleiben erhalten. Zwischenergebnisse gelten nur für die aktuelle Nachricht.
- **Weitere Korrekturen:** Geheimnisse in Codeprüfungen werden vollständiger verdeckt.
  Home-Assistant- und Google-Schreibaufrufe prüfen Daten und Bestätigungen genauer.
  Preise, Nachrichten, Sprachausgabe, Zeitpläne und persönliche Löschwünsche werden
  verlässlicher verarbeitet. Bestehende Funktionen und Sicherheitsprüfungen bleiben erhalten.

Nachweise: [A](tests/test_v1545_a.py), [B](tests/test_v1545_b.py),
[C](tests/test_v1545_c.py), [D](tests/test_v1545_d.py), [E](tests/test_v1545_e.py),
[F](tests/test_v1545_f.py), [G](tests/test_v1545_g.py), [H](tests/test_v1545_h.py),
[I](tests/test_v1545_i.py).
Die Prüfung belegt keine vollständige Fehlerfreiheit. Echte Messenger-Verbindungen und
Container-Läufe benötigen weiterhin passende Laufzeiten und Zugangsdaten.

**Neu in 15.4.4: 39 nachgewiesene Fehlerursachen korrigiert.**

Die neuen Gegenproben scheitern auf dem unveränderten Stand 15.3.4 und bestehen nach den
Korrekturen. Mehrere Varianten derselben Ursache zählen nur einmal. Die angefragten
1.000 unterschiedlichen Fehler sind damit nicht nachgewiesen.

- **Gedächtnis und Datenschutz (25 Ursachen):** Fehlgeschlagene Änderungen erhalten alte
  Notizen. Gleichzeitiges Lernen erzeugt keine doppelten Einträge. Verspätete Modellantworten
  schreiben nach Löschen, Abschalten oder neuen Änderungen keine alten Fakten zurück.
  Vergessen findet auch ältere Einträge und unterscheidet ganze Wörter.
- Opt-out, Zitate und sensible Angaben werden verlässlicher erkannt. Das gilt auch für
  Speicherversuche des Hauptmodells. Gespeicherte Zugangsdaten bleiben aus automatischen
  Modellkontexten heraus. Erinnerungen stehen als gekennzeichnete Daten im Systemkontext.
  Automatische Cloud-Auswertung beachtet Kontolimits. Hintergrundarbeit hat feste Grenzen.
- Namen, Geburtstage, Wohnorte, Sprachen und Vorlieben werden genauer erkannt. Unicode-Namen
  und lange Werte behalten unterschiedliche Schlüssel. „Im Netz suchen“ auszuschalten lässt
  das eingeschaltete Gedächtnis weiter verfügbar.
- **Abbrechen (6 Ursachen):** Alte Hilfsarbeiten verwenden einen eigenen Zustand. Sie ändern
  nach dem Abbrechen keine neue Anfrage und senden keine verspäteten Ereignisse an sie.
  Wartende Modellaufrufe prüfen den Abbruch vor dem Start. Auch die Schlussantwort und
  vorab geladene Nachrichten lassen sich abbrechen. Verlassene Hilfsarbeiten sind begrenzt.
- **Prüf-VM (3 Ursachen):** Reviews verwenden eine eigene VM ohne Netz und Messenger-Volumes.
  Höchstens fünf Testläufe mit jeweils höchstens 20 Sekunden sind technisch erzwungen.
  JSON-Prüfungen lehnen auch die ungültigen Werte `NaN` und `Infinity` ab.
- **Weitere Funktionen (5 Ursachen):** Lageränderungen akzeptieren nur gültige ganze Zahlen
  und prüfen Schreibantworten. Private Bilder folgen keinen Verknüpfungen in andere Ordner.
  Der Modell-Routing-Cache bleibt begrenzt. Auch kurze Standardantworten übernehmen neu
  gewählte Chat- und Datenschutzeinstellungen.

Nachweise: [Gedächtnis](tests/test_v1544_memory.py),
[Abbrechen und Reviews](tests/test_v1544_cancel_review.py),
[weitere Funktionen](tests/test_v1544_integrations.py).
Vorhandene Funktionen und Sicherheitsprüfungen bleiben erhalten. Diese Prüfungen sind kein
Nachweis vollständiger Fehlerfreiheit; echte Messenger-Konten und Container-Läufe brauchen
zusätzlich die passende Laufzeit und Zugangsdaten.

**Neu in 15.3.4:**

- **Gedächtnis wie bei großen Chat-Apps.** Sagst du nebenbei „ich heiße Louis“, „ich wohne in
  Bremen“ oder „ich mag keine Pilze“, merkt Aquaticy sich das sofort, auch ohne „merk dir“.
  Schon die nächste Antwort nutzt es. Nach der Antwort sucht ein schnelles Cloud-Modell nach
  weiterem Beiläufigem (Hobbys, Familie, Geräte). Pro Sache gibt es einen Stand: „Ich bin
  nach Hamburg gezogen“ ersetzt Bremen, „mag keine Pilze“ hebt „mag Pilze“ auf. Doppeltes
  legt Aquaticy nicht ab.
- **Überall außer im Code-Modus.** Das Gedächtnis gilt im normalen Chat, in Pro, in Secure Pro
  und in WhatsApp/Signal, wenn du dir selbst schreibst. Andere Absender lesen und schreiben
  nichts davon. Im Code-Modus gibt es kein Gedächtnis: kein Lesen, kein Schreiben, auch keine
  Notizen aus normalen Chats.
- **Was nie von allein gespeichert wird:** Gesundheit, Religion, Politik, Sexualität,
  Passwörter, Konto- und Kartennummern. Das geht nur, wenn du ausdrücklich „merk dir“ sagst.
  „Merk dir das nicht“ in einer Nachricht verhindert das Merken. „Vergiss, dass ich Pilze
  mag“ löscht den Eintrag. Alles Gemerkte siehst und löschst du in den Einstellungen unter
  Speicher. Der Speicher bleibt verschlüsselt und lässt sich ganz abschalten.
- **Abbrechen wirkt sofort.** Drückst du „Abbrechen“, während Aquaticy denkt, sucht oder in
  der virtual machine arbeitet, endet die Anfrage gleich. Du kannst direkt die nächste Frage
  stellen und musst nicht warten.
- **Code-Review und Security-Review in der virtual machine.** Der Code liegt vor dem Start
  schon unter `/work/review/`. Aquaticy prüft Python und JSON selbst auf Syntaxfehler (nur
  lesen, nie ausführen) und gibt die Zeile an. Das Modell belegt wichtige Befunde mit kleinen
  Tests, höchstens fünf Läufe, ohne Netz, und schreibt dazu „in der VM belegt“ oder „durch
  Lesen“. Fix-Vorschläge werden nicht mehr zum Ausführen zurückgeschickt.

**Neu in 15.2.4: 121 nachgewiesene Fehlerursachen korrigiert.**

Jede gezählte Ursache wurde gegen den unveränderten Stand 15.2.3 nachgestellt.
Die zugehörigen Regressionstests scheitern dort und bestehen nach der Korrektur.
Die angefragten 200 unterschiedlichen Fehler sind damit noch nicht nachgewiesen.

- Modellaufrufe halten Parallel- und Zeitlimits ein. Auch unterbrochene Antworten werden
  bei der Verbrauchserfassung berücksichtigt. Kontolimits und abgelaufene Sitzungen sind strenger.
- Coworker behalten unbearbeitete Aufträge nach Fehlern und bei der Logrotation.
  Kontext und GitHub-Dateiausschnitte verbergen vertrauliche Zugangsdaten zuverlässiger.
- Signal wartet auf Sendebestätigungen. Lange Messenger-Texte behalten Einrückungen und
  gültige Nachrichtengrößen. Die lokale Einrichtung verwendet den eingestellten Ollama-Endpunkt.
- Kalenderfelder lassen sich ausdrücklich leeren. Google übernimmt rotierte Refresh-Tokens;
  gleichzeitige Erneuerungen desselben Kontos sind verriegelt.
- Feeds, Produktdaten, Wetter, Wechselkurse, Orte und Exporte verarbeiten weitere gültige Formate.
  Fremde Redirect-Ziele bleiben gesperrt. Der lokale Adresscache verdrängt nur alte Einträge.
- Secure Pro verarbeitet weitere Paketformate und nmap-Befunde. Freigaben, Zielgrenzen und
  Bestätigungen bleiben erhalten. Datenbankübertragungen bleiben bei paralleler Nutzung stabil;
  ein gescheiterter Cluster-Beitritt stellt die bisherigen Dateien wieder her.
- Zertifikate werden zusätzlich auf Schlüsselzugehörigkeit und Gültigkeitsbeginn geprüft.
  Installer halten Redirect- und Zeitgrenzen auch mit übergebenen HTTP-Clients ein.

Die nachgestellten Ursachen F001 bis F121 stehen in den Tests
[A](tests/test_v1524_a.py), [B](tests/test_v1524_b.py), [C](tests/test_v1524_c.py),
[D](tests/test_v1524_d.py), [E](tests/test_v1524_e.py), [F](tests/test_v1524_f.py)
und [externer Bericht](tests/test_v1524_external.py).
[Ergänzende Tests](tests/test_v1524_followups.py) prüfen Erfolgswege, Abbruch und parallele Nutzung.

### Prüfung des externen LLM-Berichts

Der eingereichte Bericht nennt 18 Punkte. Keine der als kritisch bezeichneten
Lücken ist in der beschriebenen Form nachweisbar. Mehrere zitierte Funktionen existieren nicht.
Punkt 7 beschreibt einen tatsächlichen Leistungsnachteil; dieser ist korrigiert.

| Punkte | Ergebnis |
|---|---|
| 1–2: DNS-Rebinding | Gesperrte DNS-Fehler; Verbindung ausschließlich zur geprüften IP. |
| 3: Shell-Injection | Argumentlisten und Prüfung der Ziele gegen die Netzfreigabe. |
| 4: Report-Pfad | Zitierte Funktion fehlt; der Bericht verwendet einen festen Namen. |
| 5: YAML | `safe_load` weist Python-Objekttags zurück. |
| 6: Modellname | API-Bezeichner; das Beispiel zeigt keinen Dateizugriff. |
| 7: Cache | Begrenzter Cache. Vollständiges Leeren durch LRU-Verdrängung ersetzt. |
| 8: Redirects | Netzschutz prüft jedes Weiterleitungsziel erneut. |
| 9–10: VM/Recherche | Zitierter Code fehlt. Der VM-Lebenszyklus besitzt eine Verriegelung. |
| 11: Größenlimits | Schutzgrenzen; fehlende Einstellmöglichkeiten belegen keinen DoS. |
| 12: API-Limits | Modellaufrufe begrenzt; kein universeller Begrenzer aller REST-APIs. |
| 13: Secret-Logs | Zitierte Anweisungen fehlen; keine Zusicherung für jede Fehlerausgabe. |
| 14: Suchanfragen | Datenfeld. Fremde Ergebnisse markiert; ausgehende private Angaben geprüft. |
| 15–16: Typen/Defaults | Mypy und einstellbare Modelle bestehen bereits. |
| 17: Tests | Sicherheitsprüfungen bereits vorhanden und um weitere Gegenproben ergänzt. |
| 18: Abhängigkeiten | Versionsgrenzen, feste Pins und Audit vorhanden; keine bekannte Lücke. |

Die Gegenproben ersetzen keine Live-Prüfung echter Messenger-Konten, physischer Heimnetze,
Windows-Systeme oder eines Container-Ausbruchs. Festgeschriebene Versionen besitzen noch keine
vollständige Liste von Download-Hashes. Keine dieser Prüfungen beweist allgemeine Fehlerfreiheit.

### Bisherige Korrekturen aus 15.2.3

**Neu in 15.2.3: Ollama-Auswahl repariert und 25 weitere Funktionsfehler behoben.**

Die lokale Modellliste, Fähigkeiten, Chat-Aufrufe und Modellverwaltung verwenden denselben
Ollama-Endpunkt. Ein abschließendes `/v1` wird für die native API entfernt, eigene Ports und
Proxy-Pfade bleiben erhalten. `ollama/` und `ollama_chat/` verwenden dieselbe Server-Route.
In Pro und Code bleiben neben den Empfehlungen alle verfügbaren lokalen Modelle auswählbar.
Die Wahl setzt weiterhin das Modell für Pro/Code; das normale Chat-Modell bleibt getrennt.
Kontenrechte, Modellfreigaben und feste Sicherheitsprüfungen gelten weiter.

Die Tests in `tests/test_v1523_models.py` prüfen die HTTP-Auswahl, den Browser in allen drei
Modi und eine echte Chat-Verbindung zum lokalen Ollama-Nachbau. Die 25 weiteren Ursachen
sind in `tests/test_v1523_functions.py` einzeln nachgestellt:

| Nr. | Bereich | Korrektur |
|---|---|---|
| 1 | Oberfläche | Die Agentenzahl wird bei Dezimalwerten oder Wahrheitswerten nicht stillschweigend geändert. |
| 2 | Einstellungen | Ein gescheitertes Speichern wird als Fehler gemeldet statt als Erfolg ausgegeben. |
| 3 | Karte | Koordinaten mit dem Wert null werden nicht durch die Mitte eines anderen Objekts ersetzt. |
| 4 | Ortssuche | Nicht endliche oder außerhalb der Erde liegende Koordinaten werden vor der Kartenabfrage verworfen. |
| 5 | Karte | „Werkstatt Fahrrad“ findet Fahrradwerkstätten statt Autowerkstätten. |
| 6 | Nachrichten | Bei gleichen Schlagzeilen bleibt die neueste Fassung erhalten. |
| 7 | Gmail | HTML-Zeilenumbrüche und Absätze bleiben im Nachrichtentext lesbar. |
| 8 | Kalender | Eine allein geänderte Ganztags-Endzeit bleibt ein Datum statt einer Uhrzeit. |
| 9 | Export | Karten im HTML-Export bleiben im dunklen Modus dunkel. |
| 10 | Export | Eine Produktquelle ohne Domain-Beschriftung erhält einen sichtbaren Linktext. |
| 11 | Modell-Router | Programmieraufträge für C++ und C# werden als Code erkannt. |
| 12 | Messenger | Modellnamen außerhalb des lateinischen Alphabets lassen sich eindeutig auswählen. |
| 13 | Messenger | Ein unvollständiger `/max`-Befehl aktiviert nicht nebenbei Pro. |
| 14 | Dateiliste | Ein unendlicher Größenwert bringt die Anzeige nicht zum Absturz. |
| 15 | Karte | Adressen mit `addr:place` erhalten ihren Ortsnamen, auch ohne Straße. |
| 16 | Kalender | Ein optionales Ende aus bloßen Leerzeichen nutzt die normale Standarddauer. |
| 17 | Produktdaten | Vollständige Schema.org-Adressen als Produkttyp werden erkannt. |
| 18 | Produktdaten | Produkte in JSON-LD-Listeneinträgen werden aus dem `item`-Objekt gelesen. |
| 19 | Produktdaten | Microdata-Felder mit mehreren Eigenschaftsnamen werden erkannt. |
| 20 | Suche | Doppelte Treffer einer einzelnen Suchliste zählen nicht als mehrere unabhängige Stimmen. |
| 21 | Suche | Das Zusammenführen verändert keine Trefferobjekte, die andere Suchläufe weiterverwenden. |
| 22 | Coworker | Minutenrhythmen warten bei der Zeitumstellung nicht versehentlich eine zusätzliche Stunde. |
| 23 | Preise | Ein ausdrücklicher Währungscode wie CAD hat Vorrang vor einem mehrdeutigen Dollarzeichen. |
| 24 | Gmail | Ein leerer Klartextteil verdeckt nicht mehr den vorhandenen HTML-Nachrichtentext. |
| 25 | Ollama | Die Größenberechnung erkennt auch den Modellnamen ohne den Standard-Tag `:latest`. |

**Neu in 15.2.2: 50 nachgestellte Fehlerursachen behoben.**

Funktionen und feste Sicherheitsgrenzen bleiben erhalten. Bestätigungen werden nicht entfernt.
Die Gegenproben stehen in `tests/test_v1522_data.py`, `tests/test_v1522_boundaries.py` und
`tests/test_v1522_runtime.py`. Mehrere Varianten einer Ursache zählen zusammen als ein Fund.

| Nr. | Bereich | Korrektur |
|---|---|---|
| 1 | Rechner | Kleine und große Ergebnisse werden bei der Anzeige nicht mehr zu anderen Zahlen gerundet. |
| 2 | Rechner | Überläufe und nicht darstellbare Rechenergebnisse liefern verständliche Fehler. |
| 3 | Produktdaten | Ein Preis von null bleibt als kostenloses Angebot erhalten. |
| 4 | Produktbilder | Nach einem unbrauchbaren Bild wird ein späteres gültiges Bild übernommen. |
| 5 | Produktbilder | Eine kaputte Bildadresse bricht das Lesen der Produktseite nicht ab. |
| 6 | Produktdaten | Microdata stammt vom Produkt statt vom vorher stehenden Shop-Namen. |
| 7 | Produktdaten | NaN und unendliche Bewertungen gelangen nicht mehr in die Ausgabe. |
| 8 | Kalender | Ungültige Ganztagsdaten werden vor dem Schreibzugriff abgelehnt. |
| 9 | Kalender | Das Ende eines Termins muss nach seinem Anfang liegen. |
| 10 | Kalender | Eine Änderung nur des Anfangs überschreibt nicht nebenbei das Ende. |
| 11 | Gmail | Der Text verwendet den Zeichensatz seines Mailteils, etwa ISO-8859-1. |
| 12 | Gmail | Textanhänge verdrängen nicht mehr den eigentlichen Nachrichtentext. |
| 13 | Home Assistant | Ein leerer Zielwert kann nicht versehentlich alle Geräte eines Bereichs schalten. |
| 14 | Verbindungen | Home-Assistant- und Lager-Adressen lehnen Zugangsdaten, Query und Fragment ab. |
| 15 | Heimnetz-Fragen | Ventilatoren und Staubsauger werden dem richtigen Gerätebereich zugeordnet. |
| 16 | Sprachnachrichten | Eine ausdrückliche Ablehnung wird nicht als Bitte um Audio gewertet. |
| 17 | Ortsfilter | Ein Stadtname mitten in einem anderen Wort hebt den Ortsfilter nicht auf. |
| 18 | SSH | Ein Hostschlüssel braucht tatsächliches Schlüsselmaterial statt nur des Typnamens. |
| 19 | Secure Pro | Eine ungültige Geräte-IP erweitert eine Aufgabe nicht stillschweigend auf das ganze Netz. |
| 20 | Export | Ein Weblink braucht auch einen gültigen Hostnamen. |
| 21 | Angebotsprüfung | Andere Hosts, Pfadschreibweisen und Reihenfolgen doppelter Parameter gelten nicht als gelesen. |
| 22 | GitHub | Auch das Löschen übergeordneter Workflow-Verzeichnisse wird abgefangen. |
| 23 | Modelle | Fehlende Fähigkeiten werden nach Endpunkt und Profil getrennt und nicht unbegrenzt gemerkt. |
| 24 | GitHub | Der Standard-Branch wird nach der Bestätigung und vor dem Push erneut geprüft. |
| 25 | GitHub | Die Bestätigung eines Pull Requests zeigt auch den zu veröffentlichenden Text. |
| 26 | GitHub | Checkout berücksichtigt den Branch aus der URL und verwirft unklare PR-Checkouts. |
| 27 | Geheimnisse | Auch Passwortwerte ohne Anführungszeichen aus einer .env-Datei werden vor dem Veröffentlichen erkannt. |
| 28 | Cache | Verschiedene Bestandteile können nicht denselben Schlüssel durch ein Trennzeichen erzeugen. |
| 29 | GitHub | Ungültige .lock-Bestandteile eines Branch-Namens werden früh abgelehnt. |
| 30 | GitHub | Absolute Dateipfade werden nicht ungefragt in andere relative Pfade umgeschrieben. |
| 31 | GitHub | Parallele Checkout-Einträge überschreiben sich nicht gegenseitig. |
| 32 | Secure Pro | UPnP-Einzelabfragen verlassen den ausdrücklich freigegebenen Netzbereich nicht. |
| 33 | Tailscale | Gerätenamen für freigegebene Tailscale-IP-Adressen bleiben gespeichert. |
| 34 | Chats | Das Löschen eines Chats entfernt kein Bild, das ein anderer Chat noch verwendet. |
| 35 | Oberfläche | Ungültige gespeicherte Zeitstempel bringen die Anzeige nicht zum Absturz. |
| 36 | Notizcache | Namenszusätze zur Unterscheidung gleichnamiger Personen bleiben bei der Zuordnung erhalten. |
| 37 | nmap | Abstände in „NOT VULNERABLE“ erzeugen keinen falschen Schwachstellenfund. |
| 38 | Paketprüfung | DNS-Metadaten brauchen eine tatsächlich vorhandene, vollständige Frage. |
| 39 | Updates | Dieselbe interne Versionsstufe wird nicht bei jedem Start erneut installiert. |
| 40 | Chatliste | „Gestern“ wird auch bei der Zeitumstellung nach dem örtlichen Kalender berechnet. |
| 41 | Coworker | Doppelte Namen führen nicht zu einem Auftrag an einen willkürlich gewählten Coworker. |
| 42 | Einstellungen | Dezimalwerte für ganzzahlige Einstellungen werden nicht stillschweigend abgeschnitten. |
| 43 | Coworker | Verschiedene Pfadschreibweisen derselben Datenbank umgehen die Ausführungssperre nicht. |
| 44 | Messenger | Die Textausgabe erhält Code-Operatoren, __init__ und vollständige URLs. |
| 45 | Messenger | Buchstaben in Telefonnummern werden nicht einfach gelöscht und als andere Nummer akzeptiert. |
| 46 | NVIDIA NIM | Ein gescheiterter Modelltest gilt nicht als erfolgreiche Verbindung; verfügbare Alternativen werden geprüft. |
| 47 | Google-Anmeldung | Ungültige Token-Antworten überschreiben keine funktionierende Verbindung. |
| 48 | Gmail | MIME-kodierte Betreffzeilen und Absender werden lesbar dargestellt. |
| 49 | Gmail | Große Mailtexte werden vor dem vollständigen Dekodieren begrenzt. |
| 50 | Kalender | „Heute und morgen“ und längere ausdrücklich genannte Zeiträume werden vollständig vorgeladen. |

Die Angebotsprüfung setzt verschiedene URL-Schreibweisen nicht mehr ohne Beleg gleich.
Eine gelesene Zieladresse muss tatsächlich als Quelle vorliegen; bekannte Tracking-Parameter
bleiben ausgenommen. UPnP verwendet Einzelabfragen an freigegebene Geräte. Geräte, die darauf
nicht antworten, werden dadurch nicht erkannt; eine ausbleibende Antwort ist kein Sicherheitsnachweis.

**Neu in 15.1.2: 15 nachgestellte Fehler behoben.**

1. Ein fremdes Programm wird nicht mehr als Aquaticy erkannt, nur weil ein Argument so heißt.
2. Bereits beendete Server zählen auch dann als beendet, wenn der Elternprozess sie noch nicht abgeholt hat.
3. GitHub-Schreibzugriffe verwenden nach einer Repo-Übertragung den aktuellen Repository-Namen.
4. Nach dem Laden privater Repos in die VM braucht öffentliche Recherche ebenfalls deine Bestätigung.
5. Entziehst du GitHub-Rechte, brechen die noch ausstehenden Abruf- und Schreibschritte ab.
   Bereits bei GitHub ausgeführte Teilschritte bleiben bestehen; Aquaticy meldet das.
6. GitHub-Antworten und Archive werden während des Empfangs begrenzt, auch bei Fehlermeldungen.
7. Repo-Archive haben auch beim Entpacken feste Grenzen: 32 MB je Datei, 128 MB insgesamt,
   höchstens 20.000 Einträge. Fehler räumen das unvollständige Verzeichnis wieder auf.
8. Die VM berechnet Datei-Prüfsummen in kleinen Blöcken statt mit der ganzen Datei im Speicher.
9. Änderst du Dateien während eines Pushs weiter, bleiben diese Änderungen für den nächsten Push sichtbar.
10. Auch UTF-16-/UTF-32-Dateien und eingebettete Schlüssel können die Geheimnisprüfung nicht umgehen.
11. Auch Commit-Nachrichten und Pull-Request-Titel werden vor dem Veröffentlichen auf Schlüssel geprüft.
12. UPnP-Befunde aus einem alten Netz erscheinen nach einem Netzwechsel nicht mehr als aktuelle Befunde.
13. Ausschalten von Secure Pro und Speichern seines Verlaufs greifen nicht mehr ineinander.
    Eine laufende Prüfung kann den gelöschten Verlauf nicht wieder anlegen.
14. Fehlerhafte Secure-Pro-Verlaufsdaten werden verworfen, damit sie weitere Prüfungen nicht abbrechen.
15. GitHub-Vergleiche zeigen auch Dateien nach der ersten Seite, obwohl GitHub sie nur dort liefert.

Funktionen, Kontenrechte, Bestätigungen, Schutz vor force-Pushes und die festen Werkzeuggrenzen bleiben erhalten.
Die Gegenproben stehen in `tests/test_v1512.py`.

**Neu in 15.1.1:**

- **NVIDIA NIM antwortet wieder.** Bei NVIDIA scheitern Werkzeugaufrufe im Stream bei manchen
  Modellen. Aquaticy fragt NVIDIA mit Werkzeugen deshalb ohne Stream: Die Antwort kommt am
  Stück. Klappt es trotzdem nicht, steht statt „Bei Aquaticy ist etwas schiefgelaufen“ ein
  klarer Satz da: Schlüssel abgelehnt, zu viele Anfragen, Modell weg, keine Antwort in der
  Zeit oder Anfrage abgelehnt. Die genaue Meldung steht im Terminal.
- **Ehrlichere GitHub-Prüfung.** Fehlt im Repo nur eine Datei, ein Branch oder eine Nummer,
  nennt Aquaticy genau das (zum Beispiel „die Datei „requirements.txt““) und sagt, dass der
  Zugriff passt. Die GitHub-Suche sagt jetzt dazu, dass sie nur Issues und Pull Requests
  findet, keinen Code. So meldet ein Modell keine erfundenen Mängel mehr, etwa „keine
  Sicherheitsprüfungen im Code“, nur weil die Suche nichts fand.
- **Sicherheitsprüfung auf GitHub:** `.github/workflows/security.yml` prüft bei jedem Push und
  jede Woche alle Abhängigkeiten aus `constraints.txt` auf bekannte Lücken (pip-audit) und den
  Code mit bandit. Die Abhängigkeiten stehen in `pyproject.toml`, fest gepinnt in
  `constraints.txt`. Eine eigene `requirements.txt` braucht es dafür nicht.
- **nmap und ClamAV einrichten:** steht jetzt unter „Zuhause: Heimnetz, Home Assistant, Lager“.

**Neu in 15.0.1:**

- **GitHub-Commits gehen wieder.** Aquaticy folgt Weiterleitungen von GitHub (umbenannte oder
  übertragene Repos) und liest öffentliche Repos notfalls ohne Token. Sieht dein Token ein Repo
  nicht, sagt Aquaticy jetzt genau warum. Der häufigste Grund: Ein Fine-grained-Token
  (github_pat_…) liest keine privaten Repos eines anderen Kontos, auch nicht als Mitarbeiter.
  Dann hilft ein klassisches Token (ghp_…) mit dem Recht „repo“, ein Token vom Besitzer oder
  das Übertragen des Repos. Ein Repo ohne Besitzer („Aquaticy-Ai“) sucht Aquaticy in deinen
  eigenen Repos.
- **`aquaticy stop`** beendet laufende Aquaticy-Server, auch den Hintergrundprozess.
  `aquaticy stop --port 8765` beendet nur den auf diesem Port.

**Neu in 15.0.0:**

- **Immer die neue Version im Browser.** Startest du Aquaticy und läuft auf dem Port noch ein
  anderer Aquaticy-Prozess (etwa der alte Hintergrundprozess nach einem Update), beendet
  Aquaticy ihn und startet neu. Beendet werden nur eigene Aquaticy-Prozesse, nie ein anderes
  Programm. Läuft im Browser noch eine ältere Version als installiert, steht das neben der
  Versionsnummer, mit dem Hinweis, Aquaticy neu zu starten.
- **GitHub wie Codex.** Aquaticy sieht Commits mit ihren Änderungen (`commit`), vergleicht
  Branches (`vergleich`) und filtert Commits nach Datei. Mit `github_write` holt es ein Repo in
  die VM (`checkout`, nur im Code-Chat), ändert und testet es dort und überträgt alles mit
  `push` als Commit auf einen eigenen Branch. Ohne VM geht `commit` mit Dateien direkt. Danach
  öffnet es einen Pull Request oder kommentiert. Jeder Schritt, der etwas bei GitHub ändert,
  braucht dein Ja. Aquaticy pusht nie mit force: Hat der Branch neue Commits, lehnt GitHub ab
  wie bei git. Den Standard-Branch, das Mergen und GitHub Actions fasst Aquaticy nie an. Das
  machst du auf GitHub. Dateien mit Schlüsseln oder Passwörtern überträgt es nicht. Der
  GitHub-Schlüssel bleibt auf diesem Rechner, auch wenn die VM das Repo bearbeitet. Das Recht
  dafür heißt im GitHub-Add-on **Dateien und Änderungen** (ab Werk: Lesen und ändern). Dein
  Token braucht dazu Contents: Read and write und Pull requests: Read and write.
- **Aufträge per WhatsApp/Signal.** Coworker haben einen Schalter **Aufträge per
  WhatsApp/Signal**. Dann schreibst du in deinem eigenen Chat „Coworker Ava: Schau nach neuen
  Mails“. Secure Pro hat denselben Schalter: „Secure Pro Status“, „Secure Pro prüfen“, „Secure
  Pro Wichtig“, „Secure Pro Tipps“, „Secure Pro Geräte“, „Secure Pro Aufgabe: Melde neue
  Geräte“. Antworten beginnen mit **[Aquaticy Secure Pro]** oder **[Aquaticy Coworker Ava]**,
  darunter steht der Auftrag. Fremde Nummern und Gruppen können das nicht.
- **Klartext statt Befehl im Messenger.** „Aquaticy, wechsel auf das Modell Qwen 3“, „wechsel
  in den Pro-Modus“, „setz den Ort auf Köln“ oder „zeig meine Notizen“ wirken wie /switch, /pro,
  /location und /notes. Löschen (/forget) geht nur als ausdrücklicher Befehl.
- **Der Chat richtet selbst ein.** Sagst du „Nenne mir jeden Morgen die neusten Nachrichten“,
  schlägt Aquaticy einen Coworker mit Zeitplan vor und legt ihn nach deinem Ja an. Braucht ein
  Auftrag eine Einstellung (Sprache, Suche, Modell …), stellt Aquaticy sie nach deinem Ja um und
  sagt, was jetzt gilt. Rechte wie Heimnetz, Mails, Haussteuerung, Gedächtnis oder die
  Rechts-Leitplanken schaltest weiter nur du in den Einstellungen.
- **Secure Pro erkennt Geräte.** Hersteller und Art (Router, Kamera, Smart-Home-Gerät, Drucker
  …) aus der Hardware-Adresse und den Diensten. Handys mit privater WLAN-Adresse werden als
  solche erkannt. Du kannst Geräte **benennen**. Benannte Geräte lösen keinen Hinweis „Neues
  Gerät“ mehr aus, fremde fallen dadurch sofort auf. Dazu kommen ein **Sicherheitswert** (0 bis
  100, Note A bis E, mit Trend), ein **Verlauf** der Befunde (lokal, wird beim Ausschalten
  gelöscht), mehr eigene Tipps (Kameras, Smart-Home, UPnP) und mit nmap eine **UPnP-Prüfung**
  am Router (höchstens einmal je Stunde).

**Neu in 14.3.4 Luna:** Die automatische Antwortprüfung beachtet jetzt den Rechts-Schalter
und dessen Änderung während einer laufenden Antwort. Bei aktiver Prüfung zählt auch der
ursprüngliche Auftrag. Eine Beanstandung durch das Prüfmodell wird vor dem Zurückziehen erneut
geprüft. Sachliche README-, Commit- und Sicherheitsbeschreibungen sind erlaubt; bloße
Schlagwörter sind kein Missbrauchsbeleg. Kontenrechte und feste Werkzeuggrenzen bleiben bestehen.

**Neu in 14.2.4 Luna:** GitHub liefert jetzt echte Prüfgrundlagen für Repository-Code.
Verbinde GitHub unter **Add-ons**, wähle die gewünschten Repos im Fine-grained-Token
und erlaube **Contents: Read-only**. Für Pull Requests brauchst du zusätzlich
**Pull requests: Read-only**. Unter den Aquaticy-Rechten muss **Auch Inhalte lesen** an sein.

Schreibe zum Beispiel **„Prüfe https://github.com/besitzer/repo auf Fehler“**.
Bei eingeschaltetem Code-Review- oder Security-Review-Add-on geht auch
`/code-review besitzer/repo` oder `/security-review https://github.com/besitzer/repo/pull/12`.
Aquaticy lädt bei eindeutigen Review-Aufträgen Codeauszüge vor dem Modellaufruf.
Das funktioniert auch mit Modellen ohne eigene Werkzeugaufrufe. Der AI Council übernimmt
diese Aufträge nicht. Das Modell erhält eine begrenzte, als fremde Daten markierte Prüfgrundlage.

Neue GitHub-Aktionen: **review** für bis zu sechs Dateiauszüge eines festen Commits,
**baum** für den Dateibaum und **branches** für Branches. Mit **page** liest Aquaticy weitere
Ergebnisse; **datei** unterstützt **start_line** und **max_lines** für späteren Code.
Pull Requests liefern auch Patches. Branch- und Datei-URLs sowie Unicode-Dateinamen werden
verstanden. Änderungen am PR-Kopf während des Abrufs verwerfen das gemischte Ergebnis.
Jede Antwort zeigt Grenzen und fehlenden Kontext. Eine Stichprobe ist keine vollständige Prüfung.

GitHub-Leseaktionen verwenden ausschließlich GET. Schreibaktionen benötigen eigene Rechte und dein Ja.
Netzwerkantworten und Modellkontext sind begrenzt;
Tokens werden nur an die feste GitHub-API geschickt, nie an Weiterleitungen oder Download-URLs.
„Nur Übersicht“ ruft keine Dateiinhalte ab. Die Beschränkung auf öffentliche Repos gilt auch
für Suchtreffer und Quell-Forks. Erkannte Zugangsdaten und private Schlüssel werden in
Codeauszügen verdeckt; die Vorprüfung meldet mögliche Fehler mit Zeilenangaben.
Ausgewählte Inhalte gehen an dein gewähltes Chat-Modell. Nach privaten Repo-Inhalten braucht
öffentliche Recherche eine persönliche Bestätigung. Entzogene Add-on-Rechte verwerfen laufende Abrufe.

**Neu in 14.1.4 Sol:** Freigaben für Secure-Pro-Abwehr werden nach einer Bestätigung
erneut gegen denselben Netzbereich und Router geprüft. Auch ein eigener SSH-Port bleibt
vor einer versehentlichen Sperre geschützt. Firewalld verändert bei einer Portsperre keine
vorhandenen Portfreigaben; UFW setzt die Sperre vor vorhandene Freigaben.
nmap und die Paketprüfung brechen bei Freigabeentzug ab. nmap-Ausgaben sind begrenzt,
und Ergebnisse fremder Ziele werden verworfen. Fehlerhafte IP-, TCP-, UDP- und ARP-Köpfe
gelten nicht mehr als gültige Beobachtungen. Die Paketprüfung übernimmt nur Metadaten
mit Bezug zum freigegebenen Netz. Lange Warnungen werden vollständig aufgeteilt versendet.
Tailscale-Netze gelten bei Aufgaben und nmap nach denselben Freigaberegeln wie im Netzscanner.
Die Datenschutztexte erklären, welche Befunde im Chat, Protokoll und Messenger erscheinen
und welche ein gewähltes Cloud-Modell erhält. Funktionen und Bestätigungen bleiben erhalten.

**Neu in 14.1.3 Terra:** Secure Pro steht jetzt als Unterpunkt unter **Einstellungen → Zuhause &
Netz**. Heimnetz, Home Assistant, Lager und Secure Pro sind ein Abschnitt.

- **Wie oft:** neu sind **die ganze Zeit**, **alle 30 Sekunden**, **jede Minute** und **alle 2
  Minuten**. „Die ganze Zeit“ startet nach jeder Prüfung mit 5 Sekunden Pause die nächste. Eine
  Prüfung des ganzen Netzes dauert oft länger als 30 Sekunden. Kurze Abstände belasten Heimnetz
  und Geräte stärker. Schlägt eine Prüfung dauerhaft fehl, kommt die Warnung nur einmal.
- **nmap für Schwachstellen nutzen** (aus ab Werk): nmap liest Dienste mit Versionen und führt
  nur Prüfskripte aus, die als sicher gelten (`vuln and safe`, ohne `external`, `intrusive`,
  `dos`, `brute` und `exploit`). Nichts davon geht ins Internet. Secure Pro prüft neue oder
  geänderte Geräte, sonst jedes Gerät einmal am Tag, höchstens vier je Prüfung. Gefundene
  Lücken melden sich wie andere wichtige Befunde. Im Secure-Pro-Chat kann das Modell mit
  `secure_nmap` ein Gerät gezielt prüfen (ganze Netze nur im Modus „dienste“). Der Befehl ist
  fest, Ziele liegen immer im freigegebenen Netz. `aquaticy secure-pro` bietet an, nmap zu
  installieren. Eine neue Aufgabe passt dazu: „Melde jede Sicherheitslücke.“
- **Tipps für dein Heimnetz:** Neben dem festen Wissen nennt Secure Pro Tipps für genau dein
  Netz: welches Gerät welchen riskanten Dienst offen hat und was du tun kannst, Updates bei
  nmap-Befunden, Weboberflächen ohne Verschlüsselung, SSH nur mit Schlüssel, den Router und was
  in Secure Pro noch aus ist. Die Tipps stehen in den Einstellungen und gehen an das Modell im
  Secure-Pro-Chat.

**Neu in 14.1.3 Luna:** Secure Pro überwacht dein Heimnetz wie ein Coworker.
Alles stellst du unter **Einstellungen → Zuhause & Netz → Secure Pro** ein, nachdem du dein Netz freigegeben hast:

- **Immer überwachen** und **Wie oft**: alle 5 Minuten bis täglich (ab Werk alle 15 Minuten).
  Aus heißt: Secure Pro prüft nur, wenn du „Prüfen“ drückst.
- **Nur Wichtiges meldet sich.** Malware-Verdacht, Angriffe und neu offene Risikodienste
  erscheinen im Secure-Pro-Chat und kommen per WhatsApp/Signal. Alles andere steht im Status,
  wenn du fragst.
- **Aufgaben** wie „Melde dich, wenn ein neues Gerät ins Netz kommt.“ oder „Sag Bescheid, wenn
  192.168.1.20 offline geht.“ Aquaticy wertet den Satz fest aus und zeigt, wie es ihn verstanden
  hat. Eine Aufgabe meldet nur. Sie schaltet und sperrt nichts.
- **Malware-Zeichen im Netz:** Secure Pro prüft auch bekannte Malware- und Hintertür-Ports
  (zum Beispiel 4444, 31337, Mining-Pools) und riskante Datenbanken und Docker-APIs.
- **Pakete prüfen** (aus ab Werk): Bei jeder Prüfung liest Secure Pro 15 Sekunden lang nur
  Kopfdaten: Adressen, Ports und DNS-Namen im freigegebenen Netz. Nachrichteninhalte werden
  nicht ausgewertet. Paketmitschnitte werden nicht gespeichert. Befunde mit Adressen oder
  auffälligen DNS-Namen können im Chat, Protokoll und Messenger stehen. Cloud-Modelle erhalten
  ausgewählte Befunde. So erkennt es
  Portscans, ARP-Spoofing, Passwort-Angriffe, Spam-Versand, Malware-Ports und zufällige
  DNS-Namen (DGA). Das braucht Linux und Root-Rechte oder `CAP_NET_RAW`. In einem Netz mit
  Switch sieht der Rechner nur seinen eigenen Verkehr und Rundrufe. Ein Treffer ist ein
  Verdacht, kein Beweis.
- **Mehr Wissen:** Das Modell schlägt im festen Sicherheitswissen nach (`secure_knowledge`):
  Malware-Ports, Malware-Familien wie Mirai, Emotet, Ransomware, Krypto-Miner und RATs,
  häufige Schwachstellen und was man dagegen tut.
- **Abwehr per SSH** (aus ab Werk): Mit **VM für Abwehr nutzen** darf Secure Pro über die VM
  Ports sperren, Geräte aus dem Heimnetz aussperren, Dienste stoppen und das wieder aufheben.
  Die Befehle kommen aus festen Vorlagen (ufw, firewalld, iptables oder Windows-Firewall).
  Jeder Befehl braucht dein Ja im Secure-Pro-Chat, mit Fingerabdruck des Geräts. Den Router,
  Aquaticy, das Gerät selbst und SSH (Port 22) sperrt Secure Pro nie. Die VM braucht dafür
  „Auch ins lokale Netz“ und „Ins eigene Netz sehen dürfen“. Ohne dein Ja handelt Secure Pro
  nie, auch nicht bei einem Angriff: Es meldet sich und schlägt die Abwehr vor.

Die Einstellungen sind aufgeräumt: Secure Pro und Messenger haben eigene Abschnitte, die
Rechts-Leitplanken stehen bei ihren Regeln, der echte Browser bei der Suche, der SSH-Hinweis bei
der VM. `aquaticy setup` fragt nicht mehr nach den Agenten: Sie sind an. Ausschalten kannst du
sie unter **Einstellungen → Helfer & Grenzen → Fragen automatisch aufteilen**.

**Neu in 14.0.3 Sol:** Secure Pro hat einen eigenen LLM-Chat mit defensiven Werkzeugen.
Die Einrichtung liegt unter **Einstellungen → Zuhause & Netz → Secure Pro** und erscheint nach dem Einschalten.
Router und Prüfbereich werden vorgeschlagen. Bestätige dort dein eigenes Netz, bevor die Prüfung startet.
Linux-Hostrouten mit `/32` verdrängen den Netzbereich nicht mehr. Alte Freigaben werden nicht still erweitert:
Wenn bisher nur eine Adresse erlaubt war, bestätigst du den größeren Vorschlag in den Einstellungen erneut.
Neben TCP-Antworten zeigt Secure Pro die lokale Nachbartabelle. Diese Einträge können veraltet sein;
Geräte ohne offene TCP-Ports gelten deshalb nicht automatisch als aktiv erreichbar.
Neue Dienste und geänderte Geräteadressen erscheinen als Hinweise mit ihren möglichen harmlosen Ursachen.

Öffne danach den **Secure-Pro-Chat** und nutze dein gewähltes Chat-Modell.
Es kann Status und Geräte lesen, einen freigegebenen Scan anfordern und einzelne Dienste lesend prüfen:
SSH-Banner ohne Anmeldung, HTTP-Header ohne Weiterleitung und TLS mit Zertifikatsprüfung.
Öffentliche Recherche zu Hersteller, Produkt, Firmware und CVE hilft bei bekannten Schwachstellen.
Die Recherchewerkzeuge nehmen keine lokalen IPs, MAC-Adressen oder E-Mail-Adressen als Suchanfrage an.
Seiten werden nur aus den zurückgegebenen Suchtreffern und mit den bestehenden Web-Sicherheitsprüfungen gelesen.
Das Modell erklärt Messwerte, Stärken, Grenzen und sichere Einstellungen im Gespräch.
Es hat dabei keine Shell, SSH-Anmeldung, Speicher- oder Einstellungsrechte und erweitert nie die Netzfreigabe.
Ungeprüfte Banner oder passende Ports bestätigen keine CVE. Produkt und betroffene Version müssen passen.

Malware lässt sich weiterhin nur mit ClamAV in ausdrücklich lokal freigegebenen Dateien prüfen.
Eine Prüfung aller Dateien anderer Geräte und eine Aufzeichnung des Netzwerkverkehrs findet nicht statt.
Verdächtige Beobachtungen sind keine bestätigte Infektion. Bei Cloud-Modellen gehen deine Nachrichten
und ausgewählte Befunde an den gewählten Modellanbieter. Für lokale Verarbeitung wähle ein lokales Modell.

**Neu in 14.0.2 Sol:** OpenSSH aus der aktivierten VM zu eigenen Geräten im Heimnetz.
Aktiviere im Code-Chat die VM und unter Einstellungen sowohl die Netzsuche als auch
**Auch ins lokale Netz** (Ultra). Aquaticy erhält dann das Werkzeug `lan_ssh`.
Mit `action=key` erstellt es ein Schlüsselpaar in der VM und zeigt nur den öffentlichen Teil.
Diesen gibst du am Zielgerät frei. Private Schlüssel oder Passwörter gehören nicht in den Chat.
`action=inspect` zeigt die öffentlichen Hostschlüssel des genannten Geräts, ohne Anmeldung.
Vergleiche den SHA256-Fingerabdruck direkt am Gerät, etwa mit
`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` auf dem Zielgerät.
`action=run` führt einen Befehl mit dem bestätigten Hostschlüssel und deiner Freigabe aus.
SSH-Ausgaben gelten als fremder Inhalt. Das SSH-Werkzeug nutzt keine Passwortversuche
oder automatische Weiterleitungen.
Ein Zeitlimit beendet die Verbindung; es macht bereits erfolgte Änderungen am Gerät nicht rückgängig.

Das Standardabbild bekommt `openssh-client` beim nächsten VM-Start automatisch.
Laufende VMs werden dafür nicht gelöscht. Eine alte VM ohne OpenSSH muss zuvor beendet werden.
Dabei und nach 20 Minuten Ruhe verschwinden ihre Dateien und Schlüssel wie bisher.
Für eigene Abbilder muss `openssh-client` selbst enthalten sein. Aquaticy startet keinen SSH-Server
und übernimmt keine Schlüssel oder SSH-Konfiguration vom Host. Coworker erhalten dieses Werkzeug nicht.
Die allgemeine VM-Netzfreigabe erlaubt weiterhin auch eigenen Programmen Zugriff auf das Heimnetz.

**Neu in 14.0.1 Sol:** Die Dateiprüfung meldet fehlendes ClamAV ausdrücklich.
Verschobene Ordner und nachträglich eingesetzte symbolische Verknüpfungen erweitern die Freigabe nicht.
Nach geänderter Freigabe zeigt Secure Pro erst wieder Ergebnisse aus der aktuellen Konfiguration.
Einstellungen und Prüfberichte werden vollständig und mit privaten Dateirechten ersetzt.
Ein Schreibfehler lässt den bisherigen Stand erhalten.
Unter Windows berücksichtigt die Router-Erkennung die Priorität der Standardrouten.
Fehler beim Zugriff auf Sprachmodelle legen die Einstellungen nicht mehr lahm.

**Neu in 14.0.1 Terra:** Secure Pro schlägt die Router-IP und einen privaten Prüfbereich vor.
Öffne den Secure-Pro-Chat, kontrolliere den Vorschlag und bestätige deine Berechtigung für dieses Netz.
Mit **Router testen und starten** prüfst du die Erreichbarkeit und startest die Überwachung.
Die Route stammt vom Aquaticy-Server; bei VPNs oder Containern kann es ein anderes Netz sein.
Du kannst Router-IP und Prüfbereich ändern oder das Netz weiterhin von Hand freigeben.
Die Anzeige aktualisiert sich während des geöffneten Chats und pausiert in versteckten Tabs.
Sie zeigt Fortschritt, letzte abgeschlossene Prüfung, Fehler, positive Beobachtungen und Prüfhinweise.
Keine Antwort bedeutet keinen Sicherheitsnachweis. Ein antwortender HTTPS-Port belegt
weder TLS noch gültige Zertifikate.
Secure Pro führt keine Anmeldung, Passwortversuche oder Angriffe durch.
Es verändert keine Router-Einstellungen.

**Neu in 14.0.1 Luna:** Der Besitzer findet Secure Pro und Sprachnachrichten unter
**Einstellungen → Dev settings**. Secure Pro öffnet einen eigenen, dauerhaft markierten Chat.
Dort bestätigst du dein privates Netz, startest Prüfungen und fragst den Status ab.
Die Überwachung lässt sich im Chat oder in den Einstellungen wieder ausschalten.
Nach einer Prüfung zeigt „Status“ die letzten Hinweise. Ein offener Port ist kein Infektionsnachweis.
Sprachnachrichten schaltest du dort an oder aus. Programme und Modell brauchen einmalig
`aquaticy voice` im Terminal; der Browser installiert keine Programme oder Modelle.
Diese hostweiten Funktionen verwaltet nur der angemeldete Besitzer im Einzelkonto-Modus.
Lokale Dateiordner für ClamAV werden weiterhin im Terminal freigegeben.

**Neu in 14.0.0 Luna:** lokale Sprachnachrichten und die freiwillige Netzprüfung Secure Pro.

`aquaticy setup --voice --secure-pro` richtet beide Funktionen ein.
Bestehende Installationen können `aquaticy voice` oder `aquaticy secure-pro` einzeln aufrufen.
Die erstmalige Programmeinrichtung erfolgt im Terminal, mit den Rechten des Betreibers.

**Sprachnachrichten:** Aktiviere die WhatsApp-/Signal-Brücke und gib nur vertrauenswürdige
Einzelkontakte frei. Eigener Chat und freigegebene Nummern dürfen Audios bis 90 Sekunden
und 12 MiB schicken. Gruppen und fremde Kontakte werden nicht transkribiert.
Antworten auf Audio kommen als kurze Sprachnachricht und zusätzlich als Text.
Bei Textfragen kannst du „Antworte als Sprachnachricht“ ergänzen.
Der vollständige Antworttext bleibt im Chat; Audioantworten sind auf 90 Sekunden begrenzt.
Alle Transkripte durchlaufen die normalen Werkzeugberechtigungen und Sicherheitsprüfungen.
Whisper verarbeitet eingehende Sprache lokal, eSpeak erzeugt die deutsche Stimme.
Die Einrichtung lädt einmalig das Whisper-Modell und bei Bedarf Python-Pakete herunter.
Unter Linux kann sie FFmpeg und eSpeak NG nach Bestätigung über apt installieren.
Andere Systeme benötigen FFmpeg und eSpeak NG im Programmpfad.
Während der Transkription werden keine Audios an einen Sprach-Cloudanbieter gesendet.
Der Antworttext geht wie bei normalen Chats an das gewählte Sprachmodell.
Temporäre Aquaticy-Audiodateien werden gelöscht; Transkripte gehören zum normalen Chatverlauf.
Signal-cli verwaltet empfangene Originalanhänge in seinem eigenen lokalen Speicher.
`aquaticy voice --disable` schaltet die Sprachverarbeitung aus.
Telefonate, Anrufannahme und automatisches Anrufen sind nicht enthalten.

**Secure Pro:** Du bestätigst ein eigenes privates Netz mit höchstens 256 Adressen.
Aquaticy prüft alle 15 Minuten erreichbare Geräte und ausgewählte offene Dienste.
Neue Geräte und riskante Dienste sind Prüfhinweise, keine nachgewiesenen CVEs oder Infektionen.
Es gibt keine Passwortversuche, Exploits, automatischen Reparaturen oder Löschungen.
Optional prüft ein installiertes ClamAV einen ausdrücklich ausgewählten lokalen Ordner.
Installiere dafür ClamAV und aktuelle Signaturen, etwa mit `sudo apt install clamav`
und `sudo freshclam`. Ohne diesen Schritt gibt es keine Malware-Prüfung von Dateien.
Andere Gerätefestplatten und verschlüsselter Netzwerkverkehr werden nicht untersucht.
Malwarefunde und Scannerfehler werden klar unterschieden; Fehler bedeuten kein sauberes Ergebnis.
Der lokale Bericht `secure-pro-report.json` liegt geschützt im Aquaticy-Datenordner.
Im Einzelkonto-Modus gehen Warnungen ausschließlich in den eigenen Chat des Besitzers.
Messenger müssen dafür gekoppelt und eingeschaltet sein. Im Mehrkonten-Modus erfolgt kein Versand.
Nicht zugestellte Hinweise werden beim nächsten Prüflauf erneut versucht.
Starte eine bereits laufende Weboberfläche nach dem Aktivieren neu.
`aquaticy secure-pro --disable` beendet weitere Prüfungen und Warnungen.
Beide Funktionen sind standardmäßig ausgeschaltet.

- [Was Aquaticy kann](#was-aquaticy-kann)
- [Quickstart](#quickstart)
- [Installation im Detail](#installation-im-detail)
- [Benutzung im Terminal](#benutzung-im-terminal)
- [Die Weboberfläche](#die-weboberfläche)
- [Eigene Website mit Domain](#eigene-website-mit-domain)
- [Konten: Normal, Pro und Ultra](#konten-normal-pro-und-ultra)
- [Add-ons](#add-ons)
- [Virtual machine und User mode](#virtual-machine-und-user-mode)
- [Speicher](#speicher)
- [Coworker](#coworker)
- [Gmail und Kalender](#gmail-und-kalender)
- [Zuhause: Heimnetz, Home Assistant, Lager](#zuhause-heimnetz-home-assistant-lager)
- [Gemeinsames Lernen und Auto-Upgrading](#gemeinsames-lernen-und-auto-upgrading)
- [Server-Verbund und Serverlast aufteilen](#server-verbund-und-serverlast-aufteilen)
- [Sicherheit, Rechts-Leitplanken und Ai-guard](#sicherheit-rechts-leitplanken-und-ai-guard)
- [Modelle und Anbieter](#modelle-und-anbieter)
- [Suche](#suche)
- [Im Container](#im-container)
- [Konfiguration](#konfiguration)
- [Konten verwalten (Betreiber)](#konten-verwalten-betreiber)
- [Entwicklung](#entwicklung)
- [Lizenz](#lizenz)
