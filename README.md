# Aquaticy AI 15.5.6

**Aquaticy** recherchiert für dich. Du fragst, Aquaticy sucht im Web, liest die passenden
Seiten und fasst zusammen. Zu jeder Angabe steht die Quelle. Es läuft im Terminal, im Browser
und auf dem Handy – auf Wunsch auch unter deiner eigenen Domain.

```
$ aquaticy

> Finde mir gute Cafés in Mönchengladbach mit WLAN

  [Suche] cafés mönchengladbach
  [Suche] café mönchengladbach wlan arbeiten
  [Lese]  4 Seiten...

  Ich habe 6 Cafés gefunden, die passen:

  1. Café Nordwand — Hindenburgstr. 12
     WLAN steht auf der Website, Steckdosen an den Fensterplätzen.
     Quelle: die Seite des Cafés
  ...

> davon nur die, die sonntags offen haben
```

---

## Inhalt

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

---

## Was Aquaticy kann

**Recherche**
- Sucht im Web, liest die Seiten und nennt zu jeder Angabe die Quelle.
- Versteht Nachfragen wie „nur die mit 4+ Sternen“.
- Fragt nach, wenn etwas Wichtiges fehlt – Budget, Ort oder was genau gemeint ist.
- **Nachrichten:** „Was gibt's Neues?“ bringt die aktuellen Meldungen selbst, mit Quelle und
  Uhrzeit.
- **Karte:** findet kleine Läden, Werkstätten und Praxen über OpenStreetMap, auch ohne Website.
- **Strukturieren:** zerlegt große Fragen und schickt für jeden Teil einen Helfer los. Im
  Pro-Modus bis zu 50 gleichzeitig.
- **Gegenprüfen:** sucht Ergebnisse auf anderen Seiten nach.
- **Bilder:** Foto anhängen – Aquaticy erkennt, was darauf ist, und sucht danach.
- **Webcams und Satellitenbilder** auf Wunsch.
- Geht auch ohne Websuche. Dann antwortet Aquaticy aus eigenem Wissen und sagt, wo es veraltet
  sein kann.
- „Hallo“, „Danke“ oder „Wer bist du?“ beantwortet Aquaticy sofort, ohne Modell.

**Arbeitsweisen** (links in der Seitenleiste, unter dem Logo)
- **Normal:** ein Gespräch. Gesucht wird, wenn es nötig ist.
- **Pro:** für große Fragen. Das stärkste Modell, bis zu 50 Helfer. Dauert länger, ist genauer.
- **Code:** schreibt Code und probiert ihn in einer abgeschotteten **virtual machine** aus.

**Oberfläche**
- Terminal, Browser und Handy, jeweils passend aufgebaut.
- **Eigene Website:** mit deiner Domain über Cloudflare, mit Zertifikat. Am Router musst du
  nichts freigeben.
- **Design:** Hell, Dunkel oder wie das System. Standard (grün), Schlicht oder eigene Farben.
  Auto-Scroll beim Schreiben an oder aus.
- **Spracheingabe:** 🎤 neben dem Senden-Knopf. Sprechen, und das Gesagte geht als Frage los.
- **Sprache:** Deutsch oder Englisch.
- Chats durchsuchen, umbenennen und exportieren (HTML, Markdown, CSV).

**Extras**
- **Coworker:** feste Zeitpläne und Beobachtungen für alle, dauerhafte Aufgaben mit
  Pro und Ultra. Sie lesen Gmail, Kalender und GitHub, melden Ergebnisse und fragen, bevor sie etwas ändern.
- **Add-ons:** **NVIDIA NIM** und **Mistral** (die einzigen Modelle mit API-Schlüssel), GitHub,
  Wetter, RSS-Feeds, Tagesschau, Wikipedia, Währungsrechner, Feiertage, WhatsApp Web, Signal,
  Blender. Dazu die Plugins **Code-Review** und **Security-Review**. Die Dienste
  und Plugins haben im Chat einen Befehl: `/code-review`, `/github`, `/wetter` …
- **Speicher:** merkt sich, was länger gilt. Verschlüsselt und jederzeit einsehbar.
- **Zeitpläne und Beobachtungen:** direkt in Coworker, für alle Konten.
- **Gmail und Kalender:** lesen, Termine anlegen, Entwürfe schreiben. Verschickt wird nichts.
- **Zuhause** (Ultra): Heimnetz, Home Assistant, Lagerverwaltung.
- **Eigene Dienste zuerst:** Fragst du nach deinen Mails, Terminen, Lichtern oder deinem
  Lager, sieht Aquaticy dort nach und sucht nicht im Internet. Ist der Dienst nicht
  verbunden, sagt es dir, wo du ihn verbindest.
- **KI-Bilder** und **automatische Modellwahl**.
- **Server-Verbund** (Ultra): bis zu 10 Server. Sie teilen sich die Nutzer oder rechnen
  gemeinsam an einem großen Modell.

**Stabil im Betrieb**
- Port belegt? Aquaticy nimmt den nächsten freien.
- Absturz? Automatischer Neustart, höchstens fünfmal in zehn Minuten.
- Anbieter streikt? Das schnelle Modell desselben Anbieters springt ein.
- Verbindung kurz weg? Die Seite holt die laufende Antwort zurück.
- Fehler erscheinen als verständlicher Satz, nie als technischer Fehlertext.

---

## Quickstart

```bash
# 1. Installieren
git clone --branch Aquaticy-ai --single-branch https://github.com/jonasenriklaumen-a11y/Aquaticy-Ai.git
cd Aquaticy-Ai
uv tool install --force --reinstall .
aquaticy --version            # 15.5.6

# 2. Ollama automatisch prüfen/einrichten, dann Modell, Suche und Domain
aquaticy setup

# 3. Loslegen – im Terminal …
aquaticy

# … oder im Browser
aquaticy web
```

**Du brauchst:** Python 3.11 oder neuer und [uv](https://docs.astral.sh/uv/).

**Mindest-Hardware:**

| Betrieb | CPU | RAM | Speicher |
|---|---|---|---|
| Modell in der Cloud (Mistral, NVIDIA NIM) | 1 Kern | 1 GB | 1 GB |
| + Seiten mit echtem Browser | 2 Kerne | 2 GB | 2 GB |
| + virtual machine (Code-Modus, Add-ons) | 2 Kerne | 4 GB | 10 GB |
| Lokales Modell mit Ollama | 4 Kerne | 8 GB (GPU empfohlen) | 10 GB |
| Großes Modell, auf mehrere Server verteilt | je Server 4 Kerne | zusammen etwa Modellgröße + 15 % | Modell auf dem Master |

`aquaticy setup` fragt:

| Was | Woher | Pflicht? |
|---|---|---|
| Ollama | Vorhandene Installation verwenden, sonst installieren; laufende Dienste bleiben unverändert | für lokale Modelle; Cloudbetrieb mit `--no-ollama` |
| KI-Anbieter | Mistral oder NVIDIA NIM (den Schlüssel verknüpfst du danach in der Weboberfläche unter Add-ons) · oder lokal mit [Ollama](https://ollama.com), ohne Schlüssel | ja |
| Suchmaschine | nichts – die offene Suche braucht keinen Schlüssel | nein |
| Eigene Domain | eine Domain bei Cloudflare und ein API-Token ([so geht's](#eigene-website-mit-domain)) | nein |

Aquaticy testet alles, bevor es speichert. Die Einstellungen liegen in
`~/.config/aquaticy/.env` und sind nur für dich lesbar.

Schon zu Beginn von `aquaticy setup` wird Ollama gesucht und bei Bedarf installiert.
Installationsschritte werden angezeigt und bestätigt; `aquaticy setup --yes`
bestätigt diese Schritte vorab und wählt bei lokalen Modellen die Empfehlung.
Die Fragen zu Anbieter, Suche und allgemeinen Einstellungen bleiben interaktiv.
`aquaticy setup --no-ollama` erhält die Einrichtung für reinen Cloudbetrieb.
Der Python-Paketmanager selbst startet keine Installation mit Verwalterrechten.

Eine einzelne Frage ohne Chat:

```bash
aquaticy "welche Bahnstrecken in NRW sind gerade gesperrt?"
```

**Aktualisieren** (im Repo-Ordner):

```bash
cd ~/Aquaticy-Ai
git switch Aquaticy-ai
git pull --ff-only origin Aquaticy-ai
uv tool install --force --reinstall .
aquaticy --version
```

`git pull` allein reicht nicht. Erst der `uv`-Befehl installiert die neue Fassung. Mit dem
[ZIP-Download](https://github.com/jonasenriklaumen-a11y/Aquaticy-Ai/archive/refs/heads/Aquaticy-ai.zip)
lädst du das ZIP neu und führst `uv tool install --force --reinstall .` im entpackten Ordner aus.

---

## Installation im Detail

### Linux und macOS

Wie im Quickstart. Zum Entwickeln:

```bash
uv venv && uv pip install -c constraints.txt -e ".[browser,dev]"
uv run aquaticy
```

### Windows (PowerShell)

```powershell
# uv installieren, falls es fehlt
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

git clone --branch Aquaticy-ai `
  https://github.com/jonasenriklaumen-a11y/Aquaticy-Ai.git
cd Aquaticy-Ai
uv tool install --force --reinstall .
uv tool update-shell        # danach PowerShell neu öffnen

aquaticy install-model      # holt Ollama per winget und lädt die Modelle
```

- Ohne winget: Installer von [ollama.com/download](https://ollama.com/download) laden, dann
  `aquaticy install-model` erneut starten.
- Pfade in Anführungszeichen: `aquaticy --image "C:\Users\du\Bilder\foto.jpg"`
- Pfeiltasten-Verlauf im Chat: `pip install pyreadline3`

### Ganz ohne Schlüssel: lokales Modell

```bash
aquaticy install-model
```

Der Befehl sucht Ollama, installiert es bei Bedarf und startet es, falls es noch nicht läuft.
Downloads werden vorher bestätigt. Er schlägt ein Modell vor, das
zu Arbeitsspeicher und Grafikkarte passt, lädt es und testet, ob es Werkzeuge bedienen kann.
Bei fehlgeschlagener Prüfung warnt Aquaticy; die Übernahme erfordert eine ausdrückliche
Bestätigung oder `--yes`. Auf Wunsch kommt ein Bildmodell dazu.

```bash
aquaticy install-model --model qwen2.5:14b                    # nur Text
aquaticy install-model --vision-model llava:7b                # Text + Bild
aquaticy install-model --vision-only --vision-model llava:7b  # nur Bild nachrüsten
aquaticy install-model --yes                                  # ohne Rückfragen
```

**Ein Modell für alles** (Suche und Bilder):

| Modell | ca. Größe | ab VRAM |
|---|---|---|
| `qwen3-vl:4b` | 3,3 GB | 6 GB |
| `gemma4:e4b` | 3,5 GB | 6 GB |
| `qwen3-vl:8b` | 6,1 GB | 12 GB |
| `gemma4:12b` | 6,6 GB | 10 GB |
| `gemma4:26b` | 16,0 GB | 24 GB |

**Nur Recherche:** `qwen2.5:3b`, `qwen2.5:7b`, `llama3.1:8b`, `qwen3:8b`, `qwen2.5:14b`.
**Nur Bilder:** `moondream`, `gemma3:4b`, `llava:7b`, `minicpm-v`, `gemma3:12b`.

> Das Kürzel muss `ollama_chat/` heißen, nicht `ollama/`. Nur so kommen Werkzeuge durch.
> `aquaticy install-model` schreibt es richtig.

Wird der Grafikspeicher knapp (`model runner has unexpectedly stopped`), bietet Aquaticy ein
kleineres Modell an. Von Hand: `ollama ps`, `ollama stop <modell>`. Ist ein Modell für einen
Rechner zu groß, verteilt es ein [Server-Verbund](#serverlast-aufteilen) auf mehrere.

### Seiten mit echtem Browser laden

Für Seiten, die ihren Inhalt erst per JavaScript laden:

```bash
aquaticy install-browser
```

---

## Benutzung im Terminal

### Slash-Befehle

| Befehl | Wirkung |
|---|---|
| `/max <frage>` | im Pro-Modus mit allen Helfern recherchieren |
| `/location <ort>` | Ortsfilter setzen (ohne Ort: aufheben) |
| `/model <name>` | Modell wechseln, z. B. `mistral/mistral-large-latest` |
| `/image <pfad>` | Bild beschreiben lassen und damit weitersuchen |
| `/export html\|md\|csv` | Recherche dieser Sitzung speichern |
| `/history` | frühere Recherchen |
| `/notes` | Merkzettel |
| `/notes delete <nr>` / `/notes clear` | eine oder alle Notizen löschen |
| `/clear` | Gespräch neu beginnen |
| `/memory` / `/forget` | Langzeitspeicher zeigen oder leeren |
| `/uploads` / `/uploads clear` | hochgeladene Dateien zeigen oder löschen |
| `/help` | Übersicht |
| `/<plugin> <text>` | ein eingeschaltetes Plugin nutzen, z. B. `/code-review`, `/github` |
| `/quit` / `/exit` / `/q` | beenden (auch <kbd>Strg</kbd>+<kbd>D</kbd>) |

### Optionen

```bash
aquaticy --location "Mönchengladbach" --lang de   # Ortsfilter
aquaticy --model mistral/mistral-large-latest     # Modell für diese Sitzung
aquaticy --image foto.jpg                         # Bild als Ausgangspunkt
aquaticy --max-calls 30                           # mehr Suchen je Frage
aquaticy --no-stream                              # Antwort am Stück
aquaticy --download-images                        # Bilder beim Export mitspeichern
```

### Alle Befehle

```bash
aquaticy setup                  # Ersteinrichtung
aquaticy config                 # aktive Einstellungen prüfen
aquaticy web                    # Weboberfläche starten
aquaticy web --lan              # ohne eigene Domain: auch im Heimnetz und über Tailscale
aquaticy website                # eigene Domain: Stand zeigen (setup, remove)
aquaticy search "cafés köln"    # nur suchen, ohne KI
aquaticy fetch https://…        # nur eine Seite lesen, ohne KI
aquaticy history                # frühere Recherchen
aquaticy export html -n 3       # letzte 3 Recherchen exportieren
aquaticy notes                  # Merkzettel (--delete N löscht)
aquaticy cache                  # Zwischenspeicher (--clear leert ihn)
aquaticy install-model          # lokales Modell einrichten
aquaticy install-vm             # Podman für die virtual machine einrichten
aquaticy install-messenger      # WhatsApp und Signal direkt verbinden (ohne virtual machine)
aquaticy install-browser        # echter Browser für schwierige Seiten
aquaticy account                # dein Konto (ohne Kontensystem): anlegen, Passwort neu setzen
aquaticy google                 # Gmail und Kalender verbinden (--aendern: auch schreiben)
aquaticy connect-ha             # Home Assistant verbinden
aquaticy lan                    # Geräte im eigenen Netz
aquaticy sandbox                # wie abgeschottet Aquaticy gerade läuft
aquaticy cluster                # Server-Verbund: Stand, Anfragen mit yes/no beantworten
aquaticy list                   # Konten mit Kürzel (#…), Geräten, Nutzung, Ai-guard
aquaticy remove "name"          # Konto samt Daten löschen (--yes ohne Rückfrage)
aquaticy ban "name"             # Konto, IP-Adresse oder Kürzel ("#1a2b3c4d") sperren
aquaticy unban "name"           # wieder freigeben
aquaticy aiguard "Satz"         # wie Ai-guard einen Satz einstuft (sperrt niemanden)
aquaticy pro-code               # Code für neue Pro-Konten
aquaticy ultra-code             # Code für neue Ultra-Konten
aquaticy version
```

---

## Die Weboberfläche

```bash
aquaticy web
```

Wo Aquaticy erreichbar ist, hängt davon ab, ob du eine eigene Domain eingerichtet hast:

| | ohne Domain | mit Domain |
|---|---|---|
| `aquaticy web` | nur auf diesem Rechner | Heimnetz, Tailscale **und** Domain |
| `aquaticy web --lan` | Heimnetz und Tailscale | wie oben |

Beim Start stehen alle Adressen im Terminal.

**Chat.** Links unter dem Logo Normal, Pro und Code, darunter die letzten Chats
(durchsuchbar). In der Mitte das Gespräch, unten die Eingabe: 📎 Anhängen, die Modellauswahl,
🎤 Mikrofon und Senden. Während einer Recherche kannst du in einen anderen Chat wechseln. Die
Recherche läuft weiter. Auf dem Handy liegt die Seitenleiste hinter ☰, Fenster füllen den
ganzen Bildschirm.

**Code-Chats für sich (seit 13.0.0 Luna).** Ein Chat ist entweder ein Code-Chat oder ein
Chat für Normal und Pro – wie bei Claude. Ein Klick auf **Code** zeigt links nur die
Code-Chats und beginnt einen neuen Code-Chat. Normal und Pro zeigen die anderen Chats; jeder
trägt ein Schild „Normal“ oder „Pro“. Zwischen Normal und Pro wechselst du im selben Chat.
Zwischen Code und Normal/Pro nicht: Dafür beginnt ein neuer Chat. Öffnest du einen Chat aus
der Liste, stellt sich der Modus darauf ein. Auch der Server mischt nichts: Eine Code-Frage in
einem Normal-Chat (oder umgekehrt) lehnt er ab.

**Spracheingabe.** Tipp auf 🎤 und sprich. Sobald du aufhörst, geht das Gesagte als Frage los;
nochmal tippen beendet das Zuhören, Esc bricht ab. Die Sprache erkennt dein Browser, nicht
Aquaticy: Die meisten Browser schicken die Aufnahme dafür an ihren Hersteller (Chrome: Google,
Edge: Microsoft, Safari: Apple); kann er es auf dem Gerät, nutzt Aquaticy das. Aquaticy bekommt
nur den erkannten Text. Vor der ersten Nutzung steht dieser Hinweis da. Geht nur über https oder
auf dem eigenen Rechner (localhost), nicht in Firefox.

**Weg und wieder da.** Eine Anfrage läuft auf dem Server, nicht im Browser. Du kannst die App
verlassen, das Handy sperren oder den Tab schließen. Kommst du zurück, hängt sich die Seite
wieder an. Ist die Antwort inzwischen fertig, öffnet sich ihr Chat mit der ganzen Antwort,
auch nach Stunden (bis zu einer Woche, solange der Server läuft). Abgebrochen wird nur mit
Stopp oder beim Wechsel in einen anderen Chat.

**Nachfragen statt raten.** Fehlt etwas, ohne das Aquaticy raten müsste (der Ort bei etwas
Örtlichem, der Zeitraum, das Budget, welches von mehreren gleichnamigen Dingen gemeint ist),
fragt es in einem Fenster nach. Im Denken- und Pro-Modus geschieht das vor der Recherche:
erst die Frage, dann suchen die Agenten mit deiner Antwort.

**Was du im Chat klärst, gilt im Chat.** Fragt Aquaticy nach (etwa nach dem Ort) und du
antwortest im Fenster, merkt es sich die Antwort für alle weiteren Fragen in diesem Chat,
auch nach dem Wiederöffnen. Ein neuer Chat beginnt ohne sie.

**Gezielte Fragen bekommen die gezielte Antwort.** Fragst du nach einer bestimmten Angabe
(welche Filme laufen, Speisekarte, Öffnungszeiten, Abfahrten, Preise, Konzerte), sucht
Aquaticy genau diese Angabe auf den Seiten der Orte. Nur Namen und Bewertungen reichen nicht:
Fehlt die Angabe und wurde keine Seite gelesen, geht die Antwort einmal zurück.

**Während Aquaticy arbeitet,** stehen nur wenige Zeilen da („Denken“, „Websuche“ …). Ein Klick
zeigt, was darin passiert ist. Fehler und Sperren bleiben sichtbar. „↻ Erneut versuchen“ stellt
die Frage noch einmal.

**Modellauswahl** (gleich nach 📎 Anhängen):
- **Modelle:** Mistral und NVIDIA NIM, lokal, verbesserte Fassungen aus dem Auto-Upgrading
  und das **Verbund-Modell**. Es steht nur da, was wirklich antwortet: ein Cloud-Modell nur mit
  Schlüssel, ein lokales nur, wenn es in Ollama installiert ist. Die Liste fragt Ollama bei jedem
  Öffnen neu; `aquaticy web` zeigt beim Start, welche Modelle Ollama hat, und startet Ollama,
  wenn das eingestellte Modell lokal ist.
- **Kontextfenster** (nur lokale Modelle): Ein Regler unter der Liste stellt ein, wie viel vom
  Gespräch das Modell auf einmal überblickt. Daneben steht, wie viel Arbeitsspeicher das kostet.
  Bei bekanntem Aufbau begrenzt Aquaticy ein eingestelltes Fenster auf höchstens 5 GB
  Kontextspeicher. Fehlen Modellangaben, gilt höchstens der Standard von 16.384 Tokens;
  der tatsächliche Speicherbedarf ist dann unbekannt. Der Expertenwert `0` überlässt das
  Fenster weiterhin Ollama und unterliegt dieser Begrenzung nicht. Die Auswahl zeigt das
  ausdrücklich als „Ollama-Standard“. Modellgewichte kommen zum Kontextspeicher hinzu.
- **Modelle und Verbindungen:** Die Modellauswahl gibt es ausschließlich im Chat. Über den
  gleichnamigen Knopf im Modellmenü richtest du Haupt-, Vision-, Helfer- und Code-Modell
  sowie die eigene Modelladresse ein. Anbieter-Schlüssel bleiben im jeweiligen Add-on.
- **⚡ Aufwand:** Denktiefe Low, Medium oder High und die Zahl der Helfer (Normal und Code
  1–12, Pro 1–50).
- **⚙ Weitere Einstellungen:** Websuche, Webcams und Satellitenbilder, Denken, Strukturieren,
  Gegenprüfen. Im Code-Modus: Code in der virtual machine ausprobieren, darunter (Ultra) ob sie
  Internet hat.

**Einstellungen** speichern sich selbst. Schalter sofort, Textfelder beim Verlassen. Was nur
Ultra darf, trägt ein 🔒.
- **Konto:** Name, E-Mail, Kontotyp, Nutzung, Abmelden. **Sicherheit** mit deinen Geräten,
  Passwort ändern, überall sonst abmelden. **Daten und Konto löschen**.
- Dazu: Gemeinsames Lernen, virtual machine, Speicher, Mitlesen,
  Auslastung (Ultra), Nutzung, Gmail & Kalender, Zuhause & Netz (Ultra), Suche,
  Ort & Sprache, Helfer & Grenzen, **Dev settings** (Ultra).

**Auf dem Handy** wird die Kopfzeile nach dem Senden mit einer kurzen Animation kompakter.
„Infos“ klappt Ortsfilter und Chat-Status wieder auf. Seitenleiste, Einstellungen und neuer
Chat bleiben erreichbar; die Tasten behalten ihre mindestens 44 Pixel große Trefferfläche.
Ein neuer Chat zeigt die volle Kopfzeile. Bei reduzierter Bewegung entfällt die Animation.

**Design** (links unten): Hell, Dunkel oder wie das System. Standard, Schlicht oder eigene
Farben. Dazu Schriftgröße, **Auto-Scroll** (an: der Chat läuft beim Schreiben mit, aus: er
bleibt stehen, wo du liest) und Sprache. Das gilt auf jedem Gerät.

**Merkzettel:** was Aquaticy über dich weiß. Jede Zeile lässt sich löschen.

---

## Eigene Website mit Domain

Mit eigener Domain wird Aquaticy eine richtige Website, zum Beispiel
`https://chat.example.de`. Die Verbindung läuft über einen **Cloudflare-Tunnel**. Er baut
sich von innen nach außen auf. Am Router gibst du nichts frei.

**Was du brauchst:**
1. Eine Domain, die bei Cloudflare liegt (die Nameserver zeigen auf Cloudflare).
2. Ein API-Token. Leg es an unter
   [dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens) mit
   diesen Rechten:
   - Zone → Zone → Lesen
   - Zone → DNS → Bearbeiten
   - Konto → Cloudflare Tunnel → Bearbeiten

**Einrichten:**

```bash
aquaticy setup            # Schritt 5 fragt nach Domain und Token
# oder nur die Website:
aquaticy website setup
```

Aquaticy erledigt den Rest:
- legt den Tunnel an und trägt die Domain dafür ein,
- holt ein **Zertifikat von Let's Encrypt** und erneuert es selbst,
- lädt `cloudflared` von GitHub, nur mit veröffentlichter Prüfsumme.

**Starten:** `aquaticy web`. Danach ist Aquaticy erreichbar
- unter deiner Domain,
- im Heimnetz (z. B. `http://192.168.1.20:8765`),
- über Tailscale (z. B. `http://100.81.120.100:8765`).

`aquaticy website` zeigt den Stand. `aquaticy website remove` löscht Tunnel und DNS-Eintrag bei
Cloudflare und trägt die Domain aus.

**Sicherheit:**
- Besucher aus dem Internet kommen über einen eigenen Eingang an. Er hört nur auf `127.0.0.1`.
- Dort zählt die echte Adresse des Besuchers (von Cloudflare). Grenzen für Anfragen und
  Anmeldeversuche greifen also auch hier.
- Der Server-Verbund ist von außen nicht erreichbar.
- Cookies gehen nur verschlüsselt raus (`Secure`, HSTS).
- `cloudflared` prüft das Zertifikat von Aquaticy immer gegen deine Domain.
- Das Tunnel-Token steht nie auf der Befehlszeile. Andere Nutzer des Rechners sehen es nicht.
- Token und Schlüssel liegen in Dateien, die nur du lesen kannst.

Ohne Domain bleibt alles wie bisher: `aquaticy web` läuft nur auf diesem Rechner, `--lan`
öffnet es fürs Heimnetz.

---

## Konten: Normal, Pro und Ultra

**Standard: ein Konto (seit 13.0.0 Luna).** Ohne Kontensystem gibt es auf deinem Rechner genau
ein Konto: deins, mit allen Rechten (Ultra). Du meldest dich mit **Nutzername und Passwort**
an – so kommt niemand sonst an deine Chats, auch nicht im Heimnetz. Eine E-Mail-Adresse
brauchst du nicht.

- **Anlegen:** am Ende von `aquaticy setup` im Terminal, mit `aquaticy account` oder beim
  ersten Öffnen im Browser. Im Browser brauchst du dafür den **Einrichtungscode**. Er steht im
  Terminal, in dem `aquaticy web` läuft, solange es noch kein Konto gibt. So kann niemand
  anderes im Netz dein Konto zuerst anlegen.
- **Passwort vergessen:** `aquaticy account` am Rechner setzt Nutzername und Passwort neu und
  meldet alle Geräte ab.
- **Kontensystem für mehrere Nutzer:** In `aquaticy setup` einschalten (Frage „Kontensystem
  für mehrere Nutzer einschalten?“, Standard: nein) oder `aquaticy setup --accounts`. Dann gilt
  alles unten: Registrieren mit E-Mail, Normal, Pro und Ultra. Gespeichert ist das als
  `AQUATICY_ACCOUNTS=true` in der `.env`.
- **Umstieg von früher:** Gab es schon mehrere Konten und das Kontensystem ist aus, gilt das
  älteste Ultra-Konto (sonst das älteste Konto, es wird Ultra). Ein anderes wählst du mit
  `aquaticy account --use NAME`. Die anderen Konten bleiben gespeichert, können sich aber
  nicht anmelden, bis das Kontensystem wieder an ist. Im Terminal steht beim Start, welches
  Konto gilt und wie viele andere es gibt. Löschst du das eine Konto, rückt kein anderes
  nach: Ein neues legst du mit dem Einrichtungscode oder `aquaticy account` an.

**Mit Kontensystem.** Wer die Weboberfläche öffnet, legt zuerst ein Konto an. Jedes Konto hat
eigene Chats, Einstellungen, Speicher und Schlüssel.

**Gleichzeitige Chats mit Ollama.** Verschiedene Konten können gleichzeitig Fragen stellen
und Antworten empfangen; im Test sind es zehn Konten mit zehn offenen Antwortstreams.
Ein Stopp gilt nur für den ausgewählten Chat. Weitere Fragen im selben Chat warten auf
dessen laufende Antwort. Bei 32 laufenden oder wartenden Anfragen in einem Chat kommt
eine Meldung statt weiterer Hintergrundarbeit. Andere Chats bleiben nutzbar.

Seit **12.9.9 Terra** ändern Setup und Modellinstallation keine laufenden Ollama-Dienste.
Die Frage zum Einrichten des Parallelbetriebs entfällt. Ein laufender Dienst wird weiterverwendet.
Wenn Aquaticy einen eigenen Ollama-Prozess startet, bleiben dessen lokale Adresse und
Parallelverarbeitung erhalten. Zusätzliche Anfragen warten in Ollamas Warteschlange.
Die tatsächliche Rechenleistung hängt von Modell, RAM und GPU ab.
Entfernte Modellserver werden nicht umkonfiguriert.

Schlägt Installation oder Start fehl, meldet Setup den Fehler und lädt kein Modell herunter.

| | Normal | Pro | Ultra |
|---|---|---|---|
| Recherche, Chat, Code-Modus, Add-ons ohne virtual machine | ✔ | ✔ | ✔ |
| Coworker | – | bis zu 2 | bis zu 5, mit eigener virtual machine |
| Nutzung je 5-Stunden-Sitzung | 300.000 Token | 533.333 Token | unbegrenzt |
| Nutzung je Woche | 2 Mio. Token | 4 Mio. Token | unbegrenzt |
| Auslastungsanzeige | – | – | ✔ |
| Heimnetz, Home Assistant, Lagerverwaltung | – | – | ✔ |
| User mode, virtual machine „Plus“, virtual-machine-Add-ons | – | – | ✔ |
| Internet für die virtual machine (Code-Modus) | – | – | ✔ |
| Eigene Adressen für Modell und Suche | – | – | ✔ |
| Rechts-Leitplanken abschaltbar (nur fürs eigene Konto) | – | – | ✔ |
| Auto-Upgrading und Server-Verbund steuern | – | – | ✔ |
| Ai-guard | sperrt | sperrt | warnt nur |
| Code zum Anlegen | – | 9 Zeichen | 14 Zeichen |

**Codes.** Beim ersten Start zeigt Aquaticy zwei geheime Codes im Terminal: den **Pro-Code**
(9 Zeichen) und den **Ultra-Code** (14 Zeichen). Später zeigen `aquaticy pro-code` und
`aquaticy ultra-code` sie wieder. Vorgeben kannst du sie mit `AQUATICY_PRO_CODE` und
`AQUATICY_ULTRA_CODE`.

**Nutzung.** Die Sitzung beginnt mit deiner ersten Nachricht und dauert fünf Stunden. Die Woche
beginnt zur Uhrzeit deiner Kontoerstellung. Beides steht in Prozent unter *Einstellungen →
Nutzung*. Gezählt wird auf dem Server. Wer Chats löscht, löscht nicht seinen Verbrauch.
Anfragen mit **eigenen Schlüsseln** zählen nicht.

**Mehrfachkonten.** Zwei Menschen im selben Haushalt teilen sich eine Adresse. Das allein
sperrt nicht. Aquaticy zählt Punkte gegen jedes vorhandene Konto. Ab **3 Punkten** gibt es kein
neues Konto.

| Anhaltspunkt | Punkte |
|---|---|
| dasselbe Gerät (zufällige Kennung im Cookie `aquaticy_device`) | 3 |
| gleiche Hardware **und** gleicher Browser | 1,5 |
| gleiche Hardware | 1 |
| gleicher Browser | 0,5 |
| dieselbe IP-Adresse (beim Anlegen oder zuletzt) | 1 |
| sehr ähnliche E-Mail-Adresse (`max.muster@…` / `maxmuster7@…`) | 1 |

Je Konto speichert Aquaticy höchstens 20 Geräte. Die Kennung nur als Hash, Hardware und Browser
verschlüsselt. Der Betreiber sieht nur die Zahl der Geräte und ein Kürzel der Adresse
(„#1a2b3c4d“). Kein Canvas- oder Audio-Fingerabdruck.

**Verschlüsselung.** Chats, Uploads, Bilder, IP-Adressen, Geräte und E-Mail-Adressen liegen
mit AES-256-GCM verschlüsselt. Jedes Konto hat einen eigenen Schlüssel, abgeleitet aus
`data.key`. Passwörter: Argon2id (64 MiB, 3 Durchläufe) mit Salz und geheimem Serverwert
(`auth.key`). Sichere `data.key` und `auth.key` nie zusammen mit den Daten. Ohne sie sind die
Daten nicht mehr lesbar. Der Server braucht den Schlüssel, um mit Chats zu arbeiten. Geschützt
ist gegen gestohlene Datenbanken und Sicherungen und gegen andere Konten.

---

## Add-ons

*Im Chat unter Modelle und Verbindungen → Add-ons oder unter Einstellungen → virtual machine → Add-ons.* Jedes Add-on lässt sich
installieren, an- und ausschalten und entfernen. Anbieter und Schlüssel verwaltest du im jeweiligen Add-on. Anmelden musst du dich selbst –
Aquaticy kennt keine Passwörter. Unter **Rechte** stellst du ein, was Aquaticy damit darf.

Für WhatsApp, Signal und Blender baut Aquaticy den Desktop beim ersten Installieren.
Die Bauvorlage und Hilfsprogramme sind auch im Python-Paket enthalten. Ein Git-Projektordner
ist dafür nicht nötig. Docker oder Podman und eine Internetverbindung werden benötigt.

**Empfohlen: ohne virtual machine.** In der Karte von WhatsApp Web und Signal steht **Ohne
virtual machine verbinden** (nur Ultra). Aquaticy wird wie ein weiteres Gerät an dein Handy
gekoppelt: ein Klick auf „Verbinden“, ein QR-Code im Fenster, scannen, fertig. Es läuft kein
Browser und keine virtual machine. Die Teile dafür richtet Aquaticy mit ein:

- **WhatsApp:** Das Paket neonize ist bei der Installation von Aquaticy schon dabei (Linux mit
  x86-64 oder ARM64, macOS, Windows). Auf Linux und macOS braucht es noch die Bibliothek
  `libmagic`.
- **Signal:** Das Programm [signal-cli](https://github.com/AsamK/signal-cli) lädt Aquaticy
  selbst von GitHub, nur mit der veröffentlichten SHA-256-Prüfsumme. Auf Linux mit x86-64 geht
  das ohne Java, sonst braucht signal-cli ein Java ab Version 21. Auf Windows richtest du es
  selbst ein (Pfad in `AQUATICY_SIGNAL_CLI`).
- **Wann das passiert:** Das Docker-Abbild bringt alles fertig mit. Sonst fragt
  `aquaticy setup` am Ende und `aquaticy web` beim Start einmal im Terminal. Du siehst jeden
  Befehl vorher. Nach einem Nein fragt Aquaticy nicht wieder. Jederzeit nachholen:
  `aquaticy install-messenger` (mit `--yes` ohne Rückfrage). Nur `libmagic` braucht
  Verwalterrechte (`sudo`). Aus dem Browser installiert Aquaticy nichts.

Beides sind inoffizielle Wege. Die Sitzungsdaten liegen unverschlüsselt im Ordner deines Kontos
(`messenger/`, nur für den Benutzer lesbar). „Trennen“ löscht sie. Entferne Aquaticy danach
am Handy unter „Verknüpfte Geräte“.

**Ältere Methode über die virtual machine:** Bei WhatsApp Web und Signal öffnet „Anmelden“ ein
eigenes Fenster mit dem QR-Code.
Scanne ihn mit der Handy-App und bestätige danach „Ich bin angemeldet“.
Der Code wird lokal erkannt, nicht an ein KI-Modell geschickt und nicht im Chat gespeichert.
Beim Schließen wird die Anzeige geleert. Die Anmeldung läuft nach zehn Minuten ab.
Aquaticy liest auch dichte Codes (WhatsApp) und zeichnet sie scharf neu. Zeigt das Fenster
keinen Code, steht dort der Grund: Fenster noch zu, ein anderes Fenster vorn oder noch kein
Code auf dem Bildschirm. Nach etwa zehn Sekunden ohne Code gibt es „Bildschirm selbst
bedienen“: Du siehst den Bildschirm der virtual machine und meldest dich dort selbst an.
Stürzt Firefox ab („Der Tab ist gerade abgestürzt“), startet Aquaticy ihn einmal neu. Die
virtual machine im User mode bekommt dafür mindestens 2 GB Speicher und 2 Kerne (mehr, wenn
du mehr eingestellt hast). Firefox schickt keine Absturzberichte an Mozilla.
Du musst die virtual machine dafür nicht selbst bedienen.
Aktuelle WhatsApp-Codes mit `wa.me/settings/linked_devices` werden ebenso erkannt wie ältere Codes.
Bei kurzen Verbindungsfehlern versucht das Anmeldefenster es automatisch erneut.

### KI-Modelle: NVIDIA NIM und Mistral

Die beiden stehen ganz oben unter Add-ons. Sie sind der **einzige Ort** in Aquaticy, an dem
sich ein API-Schlüssel eintragen lässt. In vier Schritten:

1. **„Installieren“** beim Add-on NVIDIA NIM oder Mistral.
2. **„Mit Google“, „Mit E-Mail“** (bei Mistral auch Apple und Microsoft) öffnet die Seite des
   Anbieters. Dort meldest du dich selbst an.
3. Einen **API-Schlüssel erstellen** und kopieren.
4. In Aquaticy **„Einfügen“** oder einfügen und **„Verknüpfen“**.

Aquaticy fragt den Anbieter, ob der Schlüssel stimmt, und speichert ihn erst dann. Danach liest
es aus, welche **Modelle** dein Konto hat; sie stehen in der Modellauswahl. Nennt der Anbieter
seine Grenzen, stehen die **freien Tokens** dabei. Der Schlüssel liegt verschlüsselt in deinem
Konto, geht nur an den Anbieter und nie zurück an den Browser. **Deinstallieren** löscht ihn.

Claude, ChatGPT, Gemini und andere Anbieter in der Cloud ruft Aquaticy nicht auf. Alles
andere läuft auf dem Server: Ollama, LM Studio, vLLM oder llama.cpp.

**AI Council** (*Dev settings*): Sind NVIDIA NIM und Mistral verknüpft, arbeiten die Modelle
zusammen. Eines löst die Aufgabe, das andere prüft auf Fehler. Aquaticy ist der **Richter**: Es
nimmt die Lösung an oder schickt sie zurück, bis zu drei Runden.

### Programme und Dienste

| Add-on | Was es kann | Anmeldung |
|---|---|---|
| 🐙 GitHub | Repos, Issues, Pull Requests und Dateien lesen (nie schreiben) | Token |
| 🌦️ Wetter | Wetter und 7-Tage-Vorhersage (Open-Meteo) | keine |
| 📰 RSS-Feeds | deine eigenen Nachrichtenquellen zusammenfassen | Feed-Adressen |
| 🗞️ Tagesschau | Meldungen nach Thema oder als Suche | keine |
| 📚 Wikipedia | Begriffe nachschlagen, mit Link (Deutsch/Englisch) | keine |
| 💱 Währungsrechner | Tageskurse der EZB für gut 30 Währungen | keine |
| 📅 Feiertage | gesetzliche Feiertage weltweit, auch je Bundesland | keine |
| 💬 WhatsApp Web | Chats lesen, Antworten vorbereiten. Senden nur nach deinem Ja. Dazu die [Messenger-Brücke](#mit-aquaticy-per-whatsapp-oder-signal-schreiben) | QR-Code |
| 🔵 Signal | wie WhatsApp, mit Signal Desktop | QR-Code |
| 🧊 Blender | 3D-Modelle bauen und rendern in der virtual machine | keine |
| 🔍 Code-Review | prüft Code auf typische Fehler, gerade bei KI-Code | keine |
| 🛡️ Security-Review | sucht Sicherheitslücken nach OWASP und zeigt die Lösung | keine |

WhatsApp, Signal und Blender laufen in der virtual machine und brauchen den User mode
(Ultra). Die Tagesschau ist nur für den privaten Gebrauch. Aquaticy hält die erlaubten 60
Abrufe pro Stunde ein.

### Mit Aquaticy per WhatsApp oder Signal schreiben

Die **Messenger-Brücke** (nur Ultra, `aquaticy/bridge.py`) lässt dich mit Aquaticy chatten wie
auf der Website. Du schreibst eine Nachricht, Aquaticy antwortet im selben Chat. Die Antwort
beginnt mit `[Aquaticy]`.

**Voraussetzungen, direkt gekoppelt (empfohlen):** nur die Kopplung (siehe oben) und Ultra.
Dann schaltest du unter dem Add-on **Mit Aquaticy schreiben** ein. Aquaticy antwortet sofort.
Die Nachrichten kommen mit der echten Nummer des Absenders an (`aquaticy/bridge_native.py`).
Freigegebene Nummern gelten deshalb nur mit Landesvorwahl (`+49 151 …`); Namen und Nummern wie
`0151 …` passen nie. Nachrichten, die älter als fünf Minuten sind, beantwortet Aquaticy nicht.

**Voraussetzungen, über den Bildschirm:** User mode an, Add-on installiert und angemeldet, im
Add-on „Lesen und schreiben“, ein Vision-Modell. Dann schaltest du unter dem Add-on **Mit
Aquaticy schreiben** ein. Schreib erst, wenn „Bereit“ dasteht: Beim ersten Blick merkt sich
Aquaticy nur, was schon im Chat steht.

Seit **12.8.9 Terra** prüft Aquaticy die Messenger-Freigabe direkt vor dem Versand erneut.
Bei geänderten Freigaben oder einer Kontosperre verwirft es die laufende Antwort.
Auch Fehlermeldungen zählen zur Antwortgrenze. Abgelehnte Befehle fremder Kontakte
verdrängen keine Modelleinstellungen anderer Chats.

Seit **12.8.9 So** prüft auch `/export` die aktuellen Rechte und die Ablaufzeit des Verlaufs.
Die Desktop-Brücke berücksichtigt Gruppenbeschränkungen auch direkt vor dem Versand.
Der Zahlungsdatenfilter prüft vollständige Coworker-Meldungen,
einschließlich Titel und aufbereiteter Texte.
Der PDF-Leser wurde gegen bekannte Endlosschleifen und übermäßigen Speicherverbrauch aktualisiert.

Seit **12.9.9 Luna** verlangen deutsche Antworten ausdrücklich echte Umlaute und ß.
Namen, Zitate, URLs und Code behalten ihre Schreibweise.

Im Setup kannst du den Hintergrundbetrieb der Weboberfläche wählen.
Wenn du zustimmst, startet die Weboberfläche nach der Einrichtung direkt.
Mit `aquaticy web --background` schaltest du ihn auch für einen einzelnen Start ein.
Der Hintergrundbetrieb nutzt automatisch Heimnetz und Tailscale wie `aquaticy web --lan`.
Beim Start werden die lokale IP-Adresse und die verfügbare Tailscale-Adresse angezeigt.
Tailscale muss dafür verbunden sein.
Mit `--host 127.0.0.1` beschränkst du den Zugriff auf diesen Rechner.
Strg+C schließt dann die Terminalanzeige. Aquaticy läuft als eigener Prozess weiter.
Die Prozessnummer und das private Protokoll werden beim Start angezeigt.
Beende diesen Prozess im Betriebssystem, um Aquaticy vollständig anzuhalten.
Nach dem Herunterfahren musst du Aquaticy selbst wieder starten.
`aquaticy web --foreground` startet ausdrücklich im Vordergrund.

Beim Start von Chat oder Weboberfläche prüft Aquaticy den Projekt-Branch auf Updates.
Neue Versionen werden automatisch installiert und anschließend gestartet.
Die Updateprüfung braucht Git und eine Internetverbindung.
Bei lokalen Codeänderungen wird das Update ausgelassen. Bei Fehlern startet die vorhandene Version.

**Messenger-Befehle (mobile):** `/switch` zeigt installierte Modelle und die Modelle der
verfügbaren API-Schlüssel. `/switch Modell` wählt eines nur für diesen Messenger-Chat.
Auch „wechsle bitte dein LLM“ öffnet die Auswahl. Mehrdeutige Namen werden nicht geraten.
Normal sind höchstens vier Rechercheagenten aktiv, ohne Strukturieren und Gegenprüfen.
`/pro` aktiviert Pro mit Mannschaft, Strukturieren und Gegenprüfen. `/normal` oder `/pro aus`
schaltet zurück. Website-Einstellungen ändern sich dadurch nicht. Modellwechsel und Pro
sind dem Besitzer und freigegebenen Nummern vorbehalten. `/help` kennzeichnet diese Befehle
mit „mobile“. `/export` gibt den Verlauf dieses Messenger-Chats als Text aus. Lange Verläufe haben Seiten
(`/export seite 2`).
Datei- und Desktop-Befehle behalten ihre Grenzen und verweisen bei Bedarf auf die App.

**Wer darf schreiben?**

| Auswahl | Aquaticy antwortet in … |
|---|---|
| Nur mein eigener Chat | deinem Chat „Nachricht an dich selbst“ (Standard) |
| Mein Chat und diese Nummern | zusätzlich bei den Nummern oder Namen, die du einträgst |
| Alle Einzelchats | jedem Einzelchat |
| Einzelchats und Gruppen | auch in Gruppen, dort nur bei „Aquaticy, …“ |

**Was darf Aquaticy nutzen?** Je Dienst eine Stufe: Web und Rechnen, Home Assistant (lesen oder
schalten), Gmail und Google Kalender (lesen oder ändern), GitHub (lesen), Lagerverwaltung
(lesen oder ändern). Das gilt nur für dich und die freigegebenen Nummern. Alle anderen
bekommen nur Web und Rechnen. Die Regeln stecken im Code, nicht im Prompt: Ein Werkzeug
außerhalb der Auswahl läuft nie. Die Brücke geht nie weiter, als die App es erlaubt.

**Wichtig zu wissen:**

- Über den Bildschirm sieht Aquaticy den Messenger in der virtual machine. Antworten brauchen
  dann 30 Sekunden bis 5 Minuten (einstellbar), und Aquaticy öffnet Chats. Andere sehen dann
  „gelesen“. Die direkte Kopplung braucht das nicht.
- **Gelesen und „schreibt …“ (direkt gekoppelt):** Sobald Aquaticy eine Nachricht annimmt, siehst
  du die blauen Haken (WhatsApp) oder „gelesen“ (Signal). Während Aquaticy lädt, denkt oder
  recherchiert, steht im Chat „schreibt …“. Das gilt nur für Nachrichten, auf die Aquaticy auch
  antwortet. Wer abgelehnt wird, merkt nichts davon.
- **Meldungen deiner Coworker (direkt gekoppelt):** Was ein Coworker meldet oder fragt, kommt
  auch in deinen eigenen Chat „Nachricht an dich selbst“: `[Aquaticy] Coworker Ava`, darunter
  die Nachricht. Bei Coworkern mit Zeitplan (etwa alle 2 Stunden) ist das jede Antwort. Auch
  eine wartende Freigabe wird gemeldet; freigeben kannst du nur in der App. Das gilt, solange
  die Brücke an ist. Höchstens 30 Meldungen je Stunde. Ist die Verbindung kurz weg, wartet die
  Meldung bis zu eine Stunde. Zahlungsdaten sendet Aquaticy nie. Bedenke: Was der Coworker
  meldet (etwa aus deinen Mails), geht so durch WhatsApp oder Signal.
- **Befehle mit `/`** gehen im Messenger auch (`/help` zeigt sie). Für alle erlaubten Chats:
  `/help`, `/clear` (Gespräch hier vergessen), `/location Ort` (Ortsfilter nur für diesen Chat)
  und die eingeschalteten Plugins: `/code-review`, `/security-review` (Code hinter den Befehl
  schreiben), `/wetter`, `/nachrichten`, `/wikipedia`, `/waehrung`, `/feiertage`. `/model` zeigt
  das Modell (nur dir und freigegebenen Nummern). `/feeds` und `/github` gehen nur dort, wo der
  Dienst freigegeben ist. `/memory`, `/notes`, `/history`, `/uploads` und `/forget` gehen nur in
  deinem eigenen Chat. `/export`, `/image`, `/max`, `/blender` und die Messenger-Add-ons gehen
  nur in der App. Ein Plugin muss in der App eingeschaltet sein.
- Rückfragen sind in Messengern nicht möglich. Was eine Bestätigung braucht, lehnt Aquaticy
  dort ab und verweist auf die App.
- Emojis kann die virtual machine nicht tippen. Sie fehlen in den Antworten.
- Messenger erlauben oft keine Programme, die für dich schreiben. Dein Konto könnte gesperrt
  werden.
- Über den Bildschirm ist eine Nummer sicherer als ein Name: Einen Namen kann sich bei Signal
  jeder geben. Ein Titel mit „~“ davor (WhatsApp-Name eines Fremden) passt nie zu einem Namen.
  Nummern zählen nur mit Landesvorwahl: Dieselben Endziffern gibt es in anderen Ländern.
- Pro Stunde gibt es höchstens 40 Antworten. Läuft gerade ein Chat in der App oder ist das
  Konto gesperrt, wartet die Brücke.
- Ohne Add-on, Anmeldung oder Schreibrecht geht sie von selbst aus.

### Plugins im Chat

Tipp `/` im Chat. Aquaticy zeigt die Befehle deiner Plugins zum Auswählen. Ein Befehl gilt für
genau eine Nachricht: `/wetter Bremen` nimmt das Wetter-Add-on, `/github offene Pull Requests
in besitzer/repo` das GitHub-Add-on.

**Code-Review** und **Security-Review** sind Wissen, kein Dienst. Hinter den Befehl kommt, was
geprüft werden soll: eingefügter Code, eine Datei oder ein GitHub-Repo (mit GitHub-Add-on).
Geprüft wird im Code-Modus mit dem stärksten Modell. Die Befunde kommen nach Schwere sortiert,
jeder mit Stelle, Beispiel und Korrektur.

- **Code-Review** kennt die typischen Fehler: Logik und Randfälle, Fehlerbehandlung,
  Ressourcen, Nebenläufigkeit, Zeitzonen. Dazu die Fehler von KI-Code: erfundene Funktionen
  und Pakete, Platzhalter, Tests nur für den Erfolgsfall, veraltete Bibliotheken.
- **Security-Review** prüft nach den OWASP Top 10:2025 und den OWASP Top 10 für
  LLM-Anwendungen: Zugriffskontrolle, Injection (SQL, Shell, XSS), Anmeldung, Lieferkette,
  Prompt-Injection, Datenabfluss, zu viel Freiheit für Agenten. Aus Sicht eines Verteidigers:
  finden, belegen, beheben.

Unter **Rechte** wählst du, ob alle Befunde kommen oder nur kritische und hohe. Und ob Aquaticy
die Korrektur gleich mitschreibt.

---

## Virtual machine und User mode

Die **virtual machine** ist ein abgeschotteter Rechner. Darin führt Aquaticy Code wirklich aus.

| Größe | Kerne | Arbeitsspeicher | Platte |
|---|---|---|---|
| Normal | 2 | 3 GB | 4 GB |
| Plus (Ultra) | 4 | 6 GB | 20 GB |

Die Größe wählst du unter Einstellungen → virtual machine. Sie bleibt gespeichert und gilt ab
der nächsten virtual machine.

- Kein root, die Platte ist begrenzt.
- **Netz:** Normal und Pro haben dort **kein Netz**. Rechnen und Dateien bearbeiten geht
  trotzdem. **Ultra** schaltet das Internet selbst frei. Heimnetz, Router und der eigene Rechner
  bleiben dann gesperrt – außer Ultra wählt **Auch ins lokale Netz**. Das Modell kann beides nicht
  umschalten.
- Ist sie an, führt Aquaticy Code dort aus, bevor es antwortet.
- **Podman wird mit eingerichtet.** Fehlt Podman oder Docker, bietet `aquaticy web` beim Start
  an, Podman zu installieren (Linux: Paketmanager mit sudo, macOS: Homebrew, Windows: winget;
  dazu die Podman-Maschine). Jeder Befehl wird vorher gezeigt. Nach einem Nein fragt es nicht
  wieder; `aquaticy install-vm` holt es jederzeit nach. Aus dem Browser lässt sich nichts
  installieren – das entscheidet, wer am Rechner sitzt.
- Angehängte Dateien liegen unter `eingang`. Alles Erstellte kannst du herunterladen.
- 20 Minuten nach der letzten Nachricht wird die virtual machine gelöscht.

Der **User mode** (Ultra) macht daraus einen kleinen Desktop mit Internet. Aquaticy sieht den
Bildschirm, klickt und tippt wie ein Mensch. Absenden, Kaufen und Löschen nur nach deinem Ja.
Passwörter, Zahlungsdaten, Captchas und „Alle akzeptieren“ fasst Aquaticy nie an. Einmal nötig
(Betreiber):

```bash
docker build -f docker/workshop-desktop.Dockerfile -t aquaticy-werkstatt-desktop:local .
```

---

## Speicher

**Speicher.** Aquaticy merkt sich, was länger gilt: Wohnort, Vorlieben, laufende Vorhaben. Nur
Text, verschlüsselt, höchstens 400 MB je Konto. Unter **„Was weißt du über mich?“** siehst du
jeden Eintrag und löschst ihn einzeln oder alle.

---

## Coworker

*Seitenleiste → 🤝 Coworker*. Hier stehen alle Aufgaben: mit festem Zeitplan, als
Beobachtung oder dauerhaft. Der bisherige separate Einstellungsbereich „Aufträge“ entfällt;
vorhandene Aufgaben, Bilder, Termine und Chat-Verweise werden automatisch übernommen.

**Feste Zeitpläne und Beobachtungen** gibt es für alle Konten (bis zu 20):

- regelmäßig recherchieren – stündlich, täglich, wöchentlich, mit optionalem Strukturieren;
- Kamera, Satellit oder Straße beobachten;
- Preise beobachten;
- ein Bild hochladen und nach einem Angebot dafür suchen, mit optionaler Quelladresse.

Beobachtungen können bis zu minütlich oder durchgehend prüfen. Nur bei einem belegten Treffer
erscheint ein neuer Chat mit Quelle und Prüfzeit; danach hält die Beobachtung an. Nur öffentliche
Quellen, keine privaten Kameras oder Anmeldungen. Alle Läufe zählen ins Kontingent.

**Dauerhafte Coworker** gibt es zusätzlich mit Pro (2) und Ultra (5). Sie übernehmen eine
Aufgabe und entscheiden selbst, wann sie daran weiterarbeiten:

- **Er arbeitet in Schritten, die ganze Zeit.** Nach jedem Schritt entscheidet er, wann er
  wieder aufwacht. Mitten in der Arbeit nach wenigen Minuten, beim Warten erst morgen. Schreibst
  du ihm, wacht er sofort auf.
- **Er hat ein Gedächtnis.** Notizen, Aufgaben, Verläufe und Aktionsdaten liegen verschlüsselt
  im Konto. Je Coworker sind 6.000, 12.000 oder 24.000 Zeichen einstellbar. Optional darf er
  passende Auszüge aus normalen Chats und/oder Notizen anderer Coworker desselben Kontos lesen
  und hilfreiche Fakten übernehmen. Beide Freigaben beginnen ausgeschaltet. Ausschalten beendet
  neue Übernahmen; vorhandene Notizen kannst du separat löschen. Andere Konten bleiben getrennt.
- **Mehr Emojis.** Bei der Erstellung stehen über 40 Bilder zur Auswahl.
- **Er nutzt deine Verbindungen.** Gmail, Kalender, GitHub und die anderen Add-ons, mit
  denselben Rechten wie im Chat.
- **Er meldet sich.** Ergebnisse und Fragen stehen in der Übersicht und als eigener Chat. Das
  Abzeichen zeigt, was neu ist.
- **Er fragt, bevor er etwas ändert.** Für jede Art Aktion stellst du eine **Regel** ein:
  *Erlauben*, *Fragen* oder *Sperren*. Das gilt für Termine, Mail-Entwürfe, Speicher und (Ultra)
  Lager, Home Assistant und Heimnetz. Bei „Fragen“ siehst du genau, was passieren würde.
  Ausgeführt wird genau das, vom Code und nicht noch einmal vom Modell. Hat er Webseiten oder
  Mails gelesen, fragt er vor Änderungen auch bei „Erlauben“; ausgenommen sind die begrenzten,
  ausdrücklich erlaubten Haus-Schaltaktionen.
- **„Im Haus etwas schalten“ (Ultra).** „Erlauben“ steht direkt in dieser Regelzeile.
  Es erlaubt `turn_on`/`turn_off` für einzelne Lichter, Schalter, Lüfter, Eingabeschalter und
  Mediengeräte, auch nach gelesenen Inhalten. Keine Gruppen, Platzhalter oder Zusatzdaten.
  Schlösser, Alarme, Garagentore, Skripte, Szenen und andere geschützte Aktionen brauchen
  weiterhin eine einzelne Bestätigung. Schalten muss in der Verbindung eingeschaltet sein;
  nach einem Token- oder Adresswechsel musst du erneut „Erlauben“ anklicken. „Fragen“ widerruft
  die automatische Freigabe, „Sperren“ blockiert die Kategorie. Der separate Bereich mit
  Geräte-Dauerfreigaben entfällt; alte Einzelfreigaben werden nicht automatisch ausgeweitet.
- **Rhythmus unter „Aufgabe ändern“.** Wähle 30 Sekunden, 1, 5, 10 oder 20 Minuten, 1 oder
  4 Stunden oder einmal täglich. Der Abstand zählt ab dem Ende des letzten Laufs; laufende
  Arbeit und Warteschlange können ihn verlängern. „Automatisch“ bzw. „Bisheriger Zeitplan“
  stellt die ursprüngliche Planung wieder her. Häufige Recherchen nutzen denselben Chat.
  Tagesgrenzen, Kontingentpausen und der Schutz vor doppelten Läufen gelten weiterhin.
- **Aufgeräumte Oberfläche.** Dekorative Emojis entfallen außerhalb von Coworkern; der
  Coworker-Button hat keinen Handschlag mehr. Merkzettel erreichst du weiter über `/notes`,
  der separate Button über Einstellungen entfällt.
- **Ultra: eigener Rechner.** Jeder Coworker bekommt eine eigene virtual machine ohne Desktop.

| | Pro | Ultra |
|---|---|---|
| Coworker | bis zu 2 | bis zu 5 |
| Frühestens automatisch wieder wach nach | 15 Minuten | 5 Minuten |
| Arbeitsschritte je Coworker und Tag | 48 | 288 |
| Eigene virtual machine | – | ✔ (mit Docker oder Podman) |

Coworker zählen ins Kontingent. Ist es leer, macht der Coworker weiter, sobald es sich
zurücksetzt. Im Server-Verbund arbeitet er nur auf dem Heimserver seines Kontos.

---

## Gmail und Kalender

Aquaticy liest Termine und Mails. Mit „Ändern erlaubt“ legt es auch Termine an und schreibt
Mail-**Entwürfe**.

**Ganze Mails lesen (seit 13.0.1 Luna).** Nach „Was sind meine neusten Mails?“ kannst du
nachfragen: „Sende mir den ganzen Text der Mail von Amazon“, „Lies mir die zweite vor“,
„Kannst du mir die Mail von der Bank zeigen?“. Aquaticy erkennt das als Frage an dein eigenes
Postfach, auch ohne „meine“. Der Rechtsprüfer erfährt das: Die eigene Post ganz zu lesen ist
erlaubt, auch Post von anderen Personen. Er prüft die Anfrage trotzdem selbst, etwa auf
Beleidigungen oder fremde Konten. Aquaticy liest eine Mail bis 6.000 Zeichen; was länger ist,
kommt gekürzt an. **Verschickt und gelöscht wird nichts.** Aquaticy bietet dafür keine
Werkzeuge an und verwendet feste API-Pfade. Googles Recht `gmail.compose` wird für Entwürfe
benötigt und erlaubt technisch auch Senden; die Begrenzung auf Entwürfe liegt daher im Code.

**Ändern klappt nur, wenn Google es erlaubt hat.** Bei der Zustimmung zeigt Google jedes Recht
einzeln, und du kannst Haken abwählen. Ein Haken fehlt? Dann steht unter „Gmail & Kalender“:
„Google hat das Ändern noch nicht erlaubt.“ Klick noch einmal auf „Verbinden“ und setz alle
Haken. Das gilt auch, wenn du „Ändern erlaubt“ erst nach dem Verbinden einschaltest.

**Ohne Rückfrage:** Mit **„Auf Befehl ohne Rückfrage ändern“** (`AQUATICY_GOOGLE_DIRECT`) trägt
Aquaticy Termine ein und legt Entwürfe an, sobald du darum bittest, auch als Coworker-Aufgabe.
Hat es Mails oder Webseiten gelesen, fragt es trotzdem. Dein eigener Kalender zählt dafür nicht.

**Einrichten (einmal, etwa fünf Minuten):**

1. Auf [console.cloud.google.com](https://console.cloud.google.com/) ein Projekt anlegen.
2. **APIs und Dienste → Bibliothek:** „Gmail API“ und „Google Calendar API“ aktivieren.
3. **OAuth-Zustimmungsbildschirm:** Nutzertyp „Extern“, dich als Testnutzer eintragen.
4. **Anmeldedaten → OAuth-Client-ID**, Typ **Desktop-App**. Eine Weiterleitung trägst du
   nicht ein: Aquaticy nutzt dieselbe Adresse wie dein Browser (`http://127.0.0.1:8765/google`
   oder `http://localhost:8765/google`). Landest du nach der Zustimmung auf einer Seite mit
   einer Adresse zum Kopieren, füge sie in den Einstellungen ein.
5. Client-ID und Client-Secret in *Einstellungen → Gmail & Kalender* eintragen (oder als
   `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`), dann **Verbinden**.

Im Terminal: `aquaticy google` (oder `aquaticy google --aendern`). Von einem anderen Gerät aus
kopierst du die Adresse, auf der Google endet, in das Feld in den Einstellungen. **Trennen**
löscht die Zugangsdaten.

---

## Zuhause: Heimnetz, Home Assistant, Lager

Nur mit **Ultra**.

- **Heimnetz:** „Welche Geräte sind in meinem WLAN?“ Aquaticy schaut nur, ob etwas antwortet,
  und nur in privaten Netzen (`10/8`, `172.16/12`, `192.168/16`, `100.64/10`). Im Terminal:
  `aquaticy lan`.
- **Home Assistant:** `aquaticy connect-ha` findet die Instanz. Aquaticy liest Zustände und
  schaltet, wenn du es erlaubst. Schlösser, Alarm, Tore und Heizung fragen immer nach.
  Mit **„Auf Befehl ohne Rückfrage schalten“** (`AQUATICY_HA_DIRECT`) schaltet Aquaticy Licht,
  Steckdosen, Ventilatoren und Mediaplayer sofort, wenn du darum bittest, und auch als
  Coworker-Aufgabe. Bei Lampen darf es Helligkeit und Farbe setzen. Das Modell kann den
  Schalter nicht selbst umlegen. Hat Aquaticy Webseiten oder Mails gelesen, fragt es trotzdem.
- **Lagerverwaltung:** Räume → Möbel → Artikel. Aquaticy sagt, wo etwas liegt und wie viel da
  ist. Mit „Lesen und schreiben“ legt es auch an. Gelöscht wird nie.

### nmap und ClamAV für Secure Pro einrichten

Beides ist freiwillig. Secure Pro läuft auch ohne, prüft dann aber weniger.

- **nmap** liest, welche Dienste ein Gerät im Heimnetz anbietet. `aquaticy secure-pro` bietet
  an, nmap zu installieren (Linux mit apt). Sonst: `sudo apt install nmap` oder
  `brew install nmap`. Danach schaltest du es ein: Einstellungen → Zuhause & Netz → Secure Pro.
  nmap prüft nur Ziele im freigegebenen Heimnetz, mit festen Befehlen.
- **ClamAV** sucht Malware, aber nur in einem Ordner, den du freigibst. Installiere es mit
  `sudo apt install clamav` (oder `brew install clamav`) und hole die Virendaten mit
  `sudo freshclam`. Den Ordner gibst du in `aquaticy secure-pro` an. Fehlt ClamAV, sagt Secure
  Pro das im Bericht.
- **Firewall:** Ohne `--lan` lauscht Aquaticy nur auf `127.0.0.1`. Mit `--lan` oder im
  Hintergrund ist es auch im Heimnetz erreichbar. Soll nur dein Heimnetz an den Port, hilft
  deine Firewall, zum Beispiel `sudo ufw allow from 192.168.0.0/16 to any port 8765`.
  Secure Pro ändert keine Firewall-Regeln von selbst. Abwehr-Befehle brauchen immer dein Ja.

---

## Gemeinsames Lernen und Auto-Upgrading

**Gemeinsames Lernen** (freiwillig, *Einstellungen → Gemeinsames Lernen*). Mit deiner Zustimmung
übernimmt Aquaticy kurze **Auszüge aus öffentlichen Sachartikeln**, die es für dich gelesen hat.
Zurzeit sind das Wikipedia-Artikel zu Mathematik, Naturwissenschaften und Informatik. Private
Chats werden nie geteilt.

- Andere Konten sehen einen Auszug erst, wenn **zwei Konten** ihn unabhängig gefunden haben.
- Alles ist verschlüsselt. Auszüge bleiben höchstens 30 Tage.
- Dazu ein persönlicher **Recherchecache**: kurze Stichpunkte mit Quelle, nur für dich,
  höchstens 48 Stunden.
- Widerruf und Löschen entfernen deine Beiträge und deinen Cache.

**Auto-Upgrading** (*Dev settings*, Ultra schaltet es für alle ein). Aquaticy baut lokale
Ollama-Modelle mit Wissen aus, das mehrere Konten bestätigt haben. Ein Wissenstest misst, wie
viel besser die neue Fassung ist.

- Ultra sieht jeden Fortschritt (z. B. +0,00000002 %) und kann den Kandidaten sofort nutzen.
- Ab **5 %** wird „Upgraden“ grün: aus `gemma3:4b` wird `gemma3:4b 1.1`. Ab **30 %** gibt es
  eine ganze Version (`gemma3:4b 2`).
- Ultra kann Versionen überspringen oder eine ältere zurückholen.
- Nach einer Freigabe sieht jedes Konto einmal **Ausprobieren** und **Zurück**. Beide Fassungen
  bleiben vier Tage wählbar.
- Die Gewichte bleiben gleich. Ein Upgrade ist ein lokales Modell mit eingebautem, geprüftem
  Wissen. Läuft das Wissen ab, wird die Fassung zurückgezogen.

---

## Server-Verbund und Serverlast aufteilen

*Einstellungen → Dev settings → Server-Verbund* (nur **Ultra**). Bis zu **10 Server**
arbeiten zusammen.

- **Eine Datenbank, auf jedem Server ganz.** Konten, Sitzungen und Ai-guard werden gespiegelt,
  die Profilordner auch. Anmelden geht an jedem Server.
- **Lastausgleich nach Nutzern.** Jedes Konto hat einen Heimserver. Kommt eine Anfrage
  woanders an, geht sie verschlüsselt zum Heimserver.
- **Arbeit nach Stärke.** Jeder Server meldet Kerne, Arbeitsspeicher, Grafikkarte und die
  Zahl seiner Ollama-Modelle. Daraus gibt der Master jedem eine Rolle:
  - **Modelle und etwas Website:** Grafikkarte ab 4 GB oder ab 16 GB Arbeitsspeicher, dazu
    Ollama mit mindestens einem Modell, und mindestens 40 % der Modell-Leistung des
    stärksten Servers.
  - **Nur Website:** alle anderen. Sie bekommen nie ein Konto mit lokalen Modellen.

  Ein Konto mit lokalen Modellen geht auf einen Modell-Server. Sitzt es auf einem schwachen,
  zieht es um, sobald dort nichts mehr läuft. Alle anderen Konten verteilt der Master nach
  Last im Verhältnis zur Stärke. Ein Modell-Server zählt dafür höchstens halb so stark wie
  der beste reine Website-Server.
- **Auslastung je Server:** Unter *Einstellungen → Auslastung* steht jeder Server mit
  Prozessor, Arbeitsspeicher, Grafikkarte, Rolle und Zahl der Konten (nur Ultra).
- **Master** ist der Server, der eingeladen hat. Fällt ein Server aus, übernimmt der Master
  dessen Konten per Knopf.

**Verbinden:** Auf allen Servern `aquaticy web --lan` starten (mit eigener Domain reicht
`aquaticy web`) und den Schalter einschalten. Im lokalen Netz erscheinen die anderen Server
in der Liste. Über Tailscale trägst du ihre 100.x-Adresse oder ihren vollständigen
MagicDNS-Gerätenamen (z. B. `server.tail123.ts.net`) und ihren Aquaticy-Port von Hand ein.
Dann **Verbinden**. Der andere Server fragt
im Terminal `Annehmen? [yes/no]` und zeigt bei `yes` einen sechsstelligen Code. Den gibst du
auf dem Master ein. Ohne Terminal: `docker compose exec aquaticy aquaticy cluster`.

**Gut zu wissen:** Der neue Server übernimmt die Daten des Verbunds und startet einmal neu.
Seine alten Daten bleiben unter `cluster/backup-<Zeit>`. Zwischen den Servern ist alles mit
AES-GCM verschlüsselt (Schlüsseltausch per X25519). Gefunden wird per UDP-Rundruf auf Port 8766
(`AQUATICY_CLUSTER_PORT`). Im Container dafür `compose.host.yaml` nutzen.

**Über Tailscale:** Alle Server müssen im selben Tailnet erreichbar sein. Für einen Verbund
über mehrere Standorte jeden Server über seine Tailscale-Adresse einladen; lokale LAN-Adressen
sind an anderen Standorten normalerweise nicht erreichbar. Die lokale Firewall und die
Tailscale-Zugriffsregeln müssen den tatsächlichen **Aquaticy-TCP-Port** (normalerweise 8765)
zwischen allen Mitgliedern erlauben. Ist der Wunschport belegt, den im Terminal angezeigten
Ersatzport eintragen. Eine Freigabe im Internet oder ein zusätzlicher RPC-Port ist nicht nötig.
Die UDP-Suche auf 8766 funktioniert nur im lokalen Netz und wird für Tailscale nicht gebraucht.
MagicDNS muss auf dem einladenden Rechner funktionieren; andernfalls die 100.x-IP verwenden.
Aquaticy löst nur vollständige `*.ts.net`-Namen auf, akzeptiert dabei ausschließlich
Tailscale-IP-Adressen und speichert die geprüfte IP für alle weiteren Verbindungen.

`aquaticy web --lan` bindet IPv4. Wer gezielt Tailscale-IPv6 verwendet, startet Aquaticy mit
`aquaticy web --host fd7a:115c:a1e0:… --no-open` (die eigene vollständige Tailscale-IPv6-Adresse
einsetzen). Dann muss diese Adressfamilie zwischen allen Mitgliedern erreichbar sein.
Im Container muss der Aquaticy-Port auch über die Tailscale-Schnittstelle des Hosts erreichbar
sein; bei Netzwerk-Isolation ist außerdem der Rückweg zu den anderen Mitgliedern nötig.
Tailscale ersetzt weder die Zustimmung auf dem eingeladenen Server noch den Bestätigungscode.

### Serverlast aufteilen

Ein Schalter im Server-Verbund, nur für den **Master**. Dann verteilt der Verbund nicht die
Nutzer, sondern das *Modell*. Seine Schichten liegen auf allen Servern, die gemeinsam rechnen.
So läuft auch ein Modell, das in keinen Server allein passt – etwa ein 70B-Modell auf drei
Rechnern mit je 24 GB.

| | Server-Verbund allein | mit „Serverlast aufteilen“ |
|---|---|---|
| Was wird verteilt? | die Nutzer | das Modell |
| Modell | auf jedem Server eines | eines für alle |
| Größtes Modell | was ein Server schafft | was alle zusammen schaffen |
| Wer bedient die Konten? | der Heimserver | der Master |

**Was es braucht:** nur **das Modell in Ollama auf dem Master** (`ollama pull llama3.3:70b`).
Laufen muss es dort nicht. Die anderen Server bekommen ihre Schichten beim Start.

**llama.cpp installiert sich selbst.** Sobald der Schalter an ist, lädt Aquaticy auf jedem
Server `rpc-server` und `llama-server` von [llama.cpp](https://github.com/ggml-org/llama.cpp):

- **Eine Fassung für alle.** Der Master wählt sie und schickt sie an alle Server.
- **Die passende Ausgabe je Server:** Metal auf dem Mac, Vulkan mit NVIDIA-Karte, sonst die
  für den Prozessor. Startet die Grafik-Ausgabe nicht, nimmt Aquaticy die für den Prozessor.
- **Geprüft:** nur von GitHub, nur mit veröffentlichter Prüfsumme (SHA-256), entpackt nur in
  den eigenen Ordner (`~/.aquaticy/llama.cpp`).
- **Im Container schon dabei.**

Wer llama.cpp selbst baut, gibt die Programme mit `AQUATICY_RPC_SERVER` und
`AQUATICY_LLAMA_SERVER` vor. `AQUATICY_LLAMA_TAG` legt eine Fassung fest. `aquaticy cluster`
zeigt, welche läuft.

**So geht es:** Auf dem Master das Modell wählen und **Serverlast aufteilen** einschalten.
Aquaticy lädt llama.cpp (beim ersten Mal ein paar Minuten), startet die Server, prüft, ob das
Modell in den gemeinsamen Speicher passt, und startet es. Danach steht es für alle Konten als
**„&lt;Modell&gt; · Verbund“** in der Auswahl. Klappt etwas nicht, steht der Grund im
Verbund-Bereich. Die Meldungen von llama.cpp liegen unter `~/.aquaticy/cluster/`.

**Sicherheit:** `rpc-server` und `llama-server` lauschen nur auf `127.0.0.1`. Der Master
erreicht die anderen nur durch einen verschlüsselten Tunnel über den Aquaticy-Port. Es wird kein
zusätzlicher Port geöffnet.

**Grenzen:** Jedes Wort wandert durch alle Server. Mit Kabel geht das gut, über WLAN langsamer.
Der erste Start überträgt das ganze Modell. Das verteilte Modell beantwortet eine Anfrage nach
der anderen.

---

## Sicherheit, Rechts-Leitplanken und Ai-guard

**Feste Grenzen** (immer, für jedes Konto):
- keine Bezahlschranken, Logins oder Captchas umgehen; `robots.txt` gilt (RFC 9309);
- ins Heimnetz nur private Adressen, Webseiten nie ins Heimnetz;
- im Haus nur nach Rückfrage schalten; bei Google nie senden, nie löschen;
- Zugangsdaten nie an den Browser und nie an das Modell;
- keine PHP- oder JSP-Dateien als Upload, und Bilder müssen echte Bilder sein.

**Schutz vor Prompt-Injection.** Webseiten, Mails, Feeds und Anhänge sind für Aquaticy
*Material*, nie ein Auftrag:
- unsichtbare Zeichen fliegen raus, falsche Chat-Steuerzeichen werden entschärft;
- stehen in fremdem Text Anweisungen an eine KI, erscheint **[Schutz]** im Verlauf;
- nach fremdem Inhalt geht nichts Privates ohne Rückfrage in eine Adresse oder einen Befehl.

**Website.** Anmelde-Cookie `HttpOnly` und `SameSite=Strict`, über HTTPS auch `Secure` mit
HSTS. Strenge Content-Security-Policy, Schreibzugriffe nur von der eigenen Seite, Grenzen für
Anfragen und falsche Passwörter.

**Anmeldeschutz gegen Bots.** Vor dem Passwort bekommt jede Anmeldung eine Risikozahl aus drei
Hinweisen:

| Hinweis | gut | schlecht |
|---|---|---|
| Fingerabdruck des Clients | passt zur App (+0) | wie ein Skript (+40) |
| Fehlversuche dieses Clients in der letzten Stunde | keine (+0) | +4 je Versuch, höchstens +33 |
| dieses Gerät | schon angemeldet (+0) | neu (+20) |

Dazu kommt ein Grundwert von 6. Unter 34 geht es weiter zum Passwort. Von 34 bis 66 kommt
„Bestätige kurz, dass du ein Mensch bist“, ein Regler, den man ganz nach rechts schiebt. Ab 67
wird abgewiesen, ohne Passwortprüfung, und die Adresse eines Skripts ist 15 Minuten gesperrt.
Beispiele: App, keine Fehlversuche, bekanntes Gerät = 6; App, 6 Fehlversuche, neues Gerät = 50;
Skript, 40 Fehlversuche, neues Gerät = 99. Ein Browser, dessen Fingerabdruck passt, kommt
höchstens auf 59 und wird nie abgewiesen.

Den echten TLS-Fingerabdruck (JA3/JA4) sieht Aquaticy nicht: Hinter dem Cloudflare-Tunnel endet
die Verschlüsselung bei Cloudflare, im Heimnetz gibt es keine. Als Fingerabdruck zählen deshalb
User-Agent, `Accept-Language`, die Fetch-Metadaten des Browsers (`Sec-Fetch-Site`),
`navigator.webdriver` und eine kleine Rechenaufgabe (SHA-256), die die Seite beim Besuch im
Hintergrund löst. Alles liegt nur im Arbeitsspeicher, siehe `aquaticy/botguard.py`.

**Rechts-Leitplanken.** Aquaticy prüft jede Frage gegen Grundgesetz und BGB – auch
Personensuchen, Kamerabilder und Mail-Entwürfe. Die Regeln stehen unter *Dev settings →
Welche Regeln gelten?*. Nach einer Person suchen ist erlaubt (öffentliche Angaben, Beruf).
Private Anschrift, Handynummer oder Aufenthaltsort auszuforschen ist es nicht.

- **Abgelehnt bleibt abgelehnt.** „Bitte“ oder Drängen ändern nichts. Eine neue Frage oder ein
  neuer Chat heben die Absage auf.
- **Abschalten** geht nur mit Ultra, nur in den Einstellungen und nur fürs eigene Konto.
- **Grundschutz bleibt immer:** keine Schadsoftware in der virtual machine, keine Bilder, die
  echte Menschen herabsetzen.

**Ai-guard** läuft auf jedem Konto und entscheidet nach **Art und Schwere**:

| Art | Was passiert |
|---|---|
| Beleidigung, leicht | nur **dieser Chat** wird gesperrt |
| Beleidigung, mittel bis schwer | Bann für 1 Tag, 7 Tage oder für immer |
| Schadsoftware bauen oder installieren | sofort Bann, 4 Tage bis für immer |
| Angriffshilfe, schwerer Rechtsverstoß, Schutzregeln aushebeln | ab dem **zweiten** Anhaltspunkt Bann |
| Bagatellen, Bildung, Verteidigung | nichts |

- **Beleidigungen** erkennt Aquaticy auch ohne Modell, auf Deutsch und Englisch. Gezählt wird
  nur, was **gegen jemanden** geht. Tarnungen wie Leetspeak oder Sternchen helfen nicht.
- **Zitieren ist frei.** Hilfe beim Mobben nicht.
- **Antworten werden mitgeprüft**, wenn Rechts-Leitplanken und `AQUATICY_ANSWER_CHECK` an sind.
  Der ursprüngliche Auftrag hilft bei der Einordnung. Sachliche Beschreibungen von Risiken
  bleiben erlaubt. Bei ausgeschalteten Rechts-Leitplanken entfällt diese automatische
  Rücknahme, auch für laufende Antworten. Anbieter können weiterhin eigene Grenzen anwenden.
- Ein gesperrtes Konto kann sich anmelden und seine Chats ansehen, sonst nichts. Oben links
  steht ein rotes **Info** mit Dauer und Grund. Ultra-Konten werden nur gewarnt.

```bash
aquaticy ban "name"            # Konto dauerhaft sperren
aquaticy ban "name" --tage 7   # für 7 Tage
aquaticy ban 203.0.113.7       # IP-Adresse sperren
aquaticy unban "name"          # wieder freigeben
aquaticy aiguard "du Idiot"    # Stufe eines Satzes testen, ohne Vermerk
aquaticy aiguard --konto "name"  # die letzten Vorfälle eines Kontos
```

---

## Modelle und Anbieter

Aquaticy nimmt **Mistral** und **NVIDIA NIM** in der Cloud und sonst nur, was **auf dem
Server** läuft: Ollama, LM Studio, vLLM, llama.cpp und das Verbund-Modell. Andere Anbieter
(Claude, ChatGPT, Gemini, Groq, OpenRouter …) ruft es nicht auf, auch nicht über eine
eingetragene Modell-ID.

| Anbieter | Kürzel | Schlüssel |
|---|---|---|
| [Mistral](https://console.mistral.ai/api-keys/) | `mistral/` | Add-on Mistral |
| [NVIDIA NIM](https://build.nvidia.com/) | `nvidia_nim/` | Add-on NVIDIA NIM |
| Ollama (lokal) | `ollama_chat/` | – |
| LM Studio, vLLM, llama.cpp auf dem Server | `lm_studio/`, `hosted_vllm/`, `openai/` + lokale Adresse | – |

Je Anbieter wählt Aquaticy das passende Modell:

| Aufgabe | Mistral | NVIDIA NIM |
|---|---|---|
| Recherche und Antwort | `mistral-large-latest` | `nvidia/llama-3.3-nemotron-super-49b-v1.5` |
| Helfer, Planung | `mistral-small-latest` | `nvidia/nvidia-nemotron-nano-9b-v2` |
| Code-Modus | `codestral-latest` | `qwen/qwen2.5-coder-32b-instruct` |

Hat ein Anbieter ein Modell abgeschaltet (Antwort „410 Gone“), merkt Aquaticy sich das. Die
Beobachtung gilt nur für das betroffene Konto mit seinem Schlüssel und Endpunkt; Fehler
eines Kontos sperren keine Modelle anderer Konten. Der Ersatz greift auch bei automatischer
Modellwahl sowie im Pro- und Code-Modus. Ist eine bekannte Anbieterliste leer oder enthält
sie keine verbleibenden nutzbaren Modelle, werden keine unbestätigten Standardmodelle ergänzt.
Die Modellwahl zeigt nur noch, was der Anbieter dem Konto beim Einrichten des Add-ons genannt
hat, bei NVIDIA die Nemotron-Modelle zuerst. Ein abgeschaltetes Modell ersetzt Aquaticy durch
eines aus dieser Liste. NVIDIA hat `meta/llama-3.3-70b-instruct` und `meta/llama-3.1-8b-instruct`
am 26.08.2026 abgeschaltet.

```bash
aquaticy --model mistral/mistral-large-latest
aquaticy --model nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1.5
aquaticy --model ollama_chat/qwen2.5:7b
```

- Das Modell muss **Werkzeuge aufrufen** können, sonst kann es nicht suchen.
- Fehlt das Kürzel, ergänzt Aquaticy es.
- Ein Server mit OpenAI-Schnittstelle zählt nur unter einer lokalen Adresse (localhost,
  Heimnetz, `.local`/`.lan`). Ohne Adresse ginge `openai/…` zu OpenAI und ist gesperrt.
- Aquaticy hält die Grenzen der Anbieter ein (NVIDIA 40/Minute, Mistral 240/Minute). Anpassbar
  mit `AQUATICY_RPM` und `AQUATICY_PARALLEL_CALLS`.
- Den Schlüssel für Mistral oder NVIDIA NIM verknüpft jedes Konto selbst unter Add-ons. Modelle
  mit eigenem Schlüssel zählen nicht gegen das Limit.

---

## Suche

Standard ist eine **offene Metasuche** über mehrere Suchdienste, ohne Schlüssel. Jede Frage
wird auf mehrere Arten gestellt (`AQUATICY_SEARCH_VARIANTS`).

| Suchmaschine | Einstellung | Schlüssel |
|---|---|---|
| Offene Suche | `duckduckgo` | – |
| Eigener [SearXNG](https://docs.searxng.org/)-Server | `searxng` + `AQUATICY_SEARXNG_URL` | – |
| [Brave Search](https://brave.com/search/api/) | `brave` | `BRAVE_API_KEY` (nur vom Betreiber in der `.env`) |
| [Tavily](https://tavily.com/) | `tavily` | `TAVILY_API_KEY` (nur vom Betreiber in der `.env`) |

**Seiten lesen.** Aquaticy liest Seiten selbst, mit ehrlicher Kennung und mit Rücksicht auf
`robots.txt`. Klappt ein Abruf nur kurz nicht (DNS, Zeitüberschreitung, Serverfehler), merkt
sich Aquaticy das nicht. Ein echter Fehlschlag bleibt höchstens eine Stunde gemerkt.

**Nachrichten.** Bei „Was sind die neusten Nachrichten?“ holt Aquaticy die Schlagzeilen selbst
aus den Feeds großer Redaktionen (Tagesschau, ZDF, Deutschlandfunk, Spiegel; in Österreich,
der Schweiz und auf Englisch passende andere). Mit Thema („Neues zu Tesla“) sucht es gezielt.

Alles auf dem eigenen Rechner – lokales Modell plus eigener Suchserver:

```bash
docker compose --profile searxng up -d searxng
echo 'AQUATICY_SEARCH_BACKEND=searxng' >> .env
```

Vorher in `docker/searxng/settings.yml` den `secret_key` ersetzen (`openssl rand -hex 32`).

---

## Im Container

```bash
./aquaticy-box --setup            # einmal: Modell und Schlüssel
./aquaticy-box                    # Chat
./aquaticy-box "deine Frage"      # einzelne Recherche
```

Oder mit Compose:

```bash
docker compose run --rm aquaticy
docker compose build aquaticy                                # mit Chromium (Standard)
AQUATICY_IMAGE_TARGET=slim docker compose build aquaticy     # ohne Chromium, ~700 MB kleiner
```

Nach einem `git pull` das Abbild neu bauen (`docker compose build aquaticy`). Ein laufender
Web-Container braucht danach `docker compose up -d --force-recreate aquaticy`.

Der Container trennt das Dateisystem vom Rechner. Noch strenger: `compose.sandbox.yaml`
(`aquaticy sandbox` zeigt, was offen ist). Das Abbild bringt llama.cpp und `cloudflared` schon
mit. Für die eigene Domain im Container setzt du `AQUATICY_DOMAIN` und
`AQUATICY_CLOUDFLARE_TOKEN`. Aquaticy richtet den Rest beim Start ein.

---

## Konfiguration

Alle Werte stehen in der `.env` (Vorlage: [`.env.example`](.env.example)). Die meisten stellst
du auch in der Weboberfläche ein.

| Variable | Bedeutung | Standard |
|---|---|---|
| `AQUATICY_MODEL` | Hauptmodell (`anbieter/name`) | `mistral/mistral-large-latest` |
| `AQUATICY_VISION_MODEL` | Modell für Bilder | wie `AQUATICY_MODEL` |
| `AQUATICY_SUBAGENT_MODEL` | Modell der Helfer | das kleine des Anbieters |
| `AQUATICY_CODE_MODEL` | Modell für den Code-Modus | das stärkste erreichbare |
| `AQUATICY_API_BASE` | eigene Adresse (Ollama, eigene NIM, Proxy) | – |
| `AQUATICY_API_KEY` | Zugangsschlüssel eines lokalen Servers (vLLM, Proxy), falls er einen verlangt | – |
| `AQUATICY_AUTO_MODEL` | Modell je Nachricht automatisch wählen | `false` |
| `AQUATICY_SEARCH_BACKEND` | `duckduckgo`, `searxng`, `brave`, `tavily` | `duckduckgo` |
| `AQUATICY_SEARCH_ENGINES` | Suchdienste der offenen Suche einschränken | alle |
| `AQUATICY_SEARCH_VARIANTS` | Formulierungen je Suche (`1` = aus) | `3` |
| `AQUATICY_SEARXNG_URL` | Adresse des SearXNG-Servers | – |
| `AQUATICY_LOCATION` | Standard-Ort | – |
| `AQUATICY_LANG` / `AQUATICY_COUNTRY` | Sprache / Land der Suche | `de` / `de` |
| `AQUATICY_MAX_TOOL_CALLS` | Suchen und Seitenaufrufe je Frage | `20` |
| `AQUATICY_SUBAGENTS_AUTO` | große Fragen automatisch aufteilen | `true` |
| `AQUATICY_SUBAGENT_BUDGET` | Suchen je Helfer | `6` |
| `AQUATICY_SUBAGENT_PARALLEL` | Helfer gleichzeitig (`0` = automatisch) | lokal `2` |
| `AQUATICY_PLANNER_TIMEOUT` | Zeit fürs Aufteilen einer Frage (s) | `20` |
| `AQUATICY_CONTEXT_TOKENS` | Lokales Kontextfenster; `0` = Ollama-Standard, sonst begrenzt | `16384` |
| `AQUATICY_RPM` | Anfragen pro Minute an den Anbieter | NVIDIA `40`, Mistral `240` |
| `AQUATICY_PARALLEL_CALLS` | gleichzeitige Anfragen | NVIDIA `4`, Mistral `8` |
| `AQUATICY_FETCH_TIMEOUT` | Wartezeit je Seite (s) | `15` |
| `AQUATICY_CACHE_TTL_HOURS` | Gültigkeit des Zwischenspeichers | `24` |
| `AQUATICY_ENABLE_PLAYWRIGHT` | echter Browser für schwierige Seiten | `true` |
| `AQUATICY_BROWSER_PARALLEL` | höchstens so viele Browser gleichzeitig | `3` |
| `AQUATICY_PROXY` | Proxy für Abrufe (`http://host:port` oder `env`) | direkt |
| `AQUATICY_MEMORY` | Speicher an | `true` |
| `AQUATICY_LEGAL_GUARD` | Rechts-Leitplanken (abschaltbar nur mit Ultra) | `true` |
| `AQUATICY_VM_SIZE` | virtual machine: `normal` oder `plus` (Ultra) | `normal` |
| `AQUATICY_VM_IMAGE` | Abbild der virtual machine | `docker.io/library/python:3.12-slim` |
| `AQUATICY_VM_USER_MODE` | User mode (Ultra) | `false` |
| `AQUATICY_VM_INTERNET` | Internet für die virtual machine (Ultra) | `false` |
| `AQUATICY_VM_LAN` | virtual machine auch ins lokale Netz (Ultra) | `false` |
| `AQUATICY_VM_DESKTOP_IMAGE` | Abbild für den User mode | `aquaticy-werkstatt-desktop:local` |
| `AQUATICY_VM_IDLE_MINUTES` | virtual machine löschen nach Minuten Ruhe | `20` |
| `AQUATICY_ANSWER_CHECK` | Ai-guard prüft Antworten bei aktiven Rechts-Leitplanken | `true` |
| `AQUATICY_GITHUB_TOKEN` | Token des GitHub-Add-ons | – |
| `AQUATICY_SIGNAL_CLI` | Pfad zu signal-cli (Signal direkt koppeln, ohne virtual machine) | im Suchpfad |
| `AQUATICY_GOOGLE` / `AQUATICY_GOOGLE_WRITE` | Gmail und Kalender lesen / ändern | `false` |
| `AQUATICY_GOOGLE_DIRECT` | auf Befehl ohne Rückfrage ändern, braucht `AQUATICY_GOOGLE_WRITE` | `false` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | eigene Google-Anwendung | – |
| `AQUATICY_HA_URL` / `AQUATICY_HA_CONTROL` | Home Assistant / schalten erlaubt (Ultra) | – / `false` |
| `AQUATICY_HA_DIRECT` | auf Befehl ohne Rückfrage schalten, braucht `AQUATICY_HA_CONTROL` (Ultra) | `false` |
| `AQUATICY_LAN_ENABLED` / `AQUATICY_LAN_SUBNET` | Heimnetz ansehen (Ultra) | `true` / automatisch |
| `AQUATICY_ACCOUNTS` | Kontensystem für mehrere Nutzer (sonst ein Konto, Ultra) | `false` |
| `AQUATICY_STORAGE_URL` / `AQUATICY_STORAGE_ACCESS` | Lagerverwaltung: Adresse / `off`, `read`, `write` (Ultra) | – / `read` |
| `AQUATICY_DOMAIN` | eigene Domain (siehe [Website](#eigene-website-mit-domain)) | – |
| `AQUATICY_CLOUDFLARE_TOKEN` | API-Token von Cloudflare für Tunnel, DNS und Zertifikat | – |
| `AQUATICY_PUBLIC_PORT` | Eingang für den Tunnel, nur `127.0.0.1` | `8443` |
| `AQUATICY_CLOUDFLARED` | eigener Pfad zu `cloudflared` | lädt Aquaticy selbst |
| `AQUATICY_ACME_STAGING` | Testzertifikate von Let's Encrypt (zum Ausprobieren) | `false` |
| `AQUATICY_CLUSTER_PORT` | UDP-Port zum Finden anderer Server | `8766` |
| `AQUATICY_RPC_SERVER` / `AQUATICY_LLAMA_SERVER` | eigener Pfad zu `rpc-server` / `llama-server` | lädt Aquaticy selbst |
| `AQUATICY_LLAMA_TAG` | feste Fassung von llama.cpp, z. B. `b7000` | der Master wählt |
| `AQUATICY_LLAMA_DIR` | Ordner mit einer mitgelieferten Fassung | `/opt/aquaticy/llama.cpp` |
| `AQUATICY_PRO_CODE` | Code für neue Pro-Konten | zufällig |
| `AQUATICY_ULTRA_CODE` | Code für neue Ultra-Konten (14 Zeichen) | zufällig |
| `MISTRAL_API_KEY`, `NVIDIA_NIM_API_KEY` | schreibt das Add-on (ohne Konten); mit Konten gilt ein Eintrag hier als gestellt | – |
| `BRAVE_API_KEY`, `TAVILY_API_KEY` | Schlüssel der Suchmaschine, nur vom Betreiber | – |

Daten liegen unter `~/.aquaticy/` (Konten in `accounts.sqlite3`, je Konto ein Ordner unter
`users/`, die Website unter `website/`). Die Einstellungen liegen in `~/.config/aquaticy/.env`.

---

## Konten verwalten (Betreiber)

```bash
aquaticy account               # ohne Kontensystem: dein Konto anlegen oder Passwort neu setzen
aquaticy list                  # alle Konten: Typ, Kürzel (#…), Geräte, Nutzung, Ai-guard
aquaticy pro-code              # Code für neue Pro-Konten
aquaticy ultra-code            # Code für neue Ultra-Konten
aquaticy ban "name"            # Konto sperren (auch per IP-Adresse)
aquaticy unban "name"          # Sperre aufheben
aquaticy remove "name"         # Konto samt Daten löschen
```

---

## Entwicklung

```bash
git clone --branch Aquaticy-ai --single-branch https://github.com/jonasenriklaumen-a11y/Aquaticy-Ai.git
cd Aquaticy-Ai
uv venv && uv pip install -c constraints.txt -e ".[browser,dev]"

uv run python tools/pruefung.py            # alles: ruff, mypy, bandit, JavaScript, Tests
uv run python tools/pruefung.py --schnell  # ohne Testsuite
uv run pytest                              # nur die Tests; Netz und Modelle sind gestellt

python tools/rundgang.py            # bedient die Weboberfläche wie ein Mensch
python tools/rundgang.py --bilder   # mit Bildschirmfotos
```

Wie KI-Agenten hier arbeiten und prüfen, steht in [`AGENTS.md`](AGENTS.md).

---

## Lizenz

MIT. Der volle Text steht in [`LICENSE`](LICENSE).
