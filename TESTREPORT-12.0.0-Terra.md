# Prüfbericht: 12.0.0 Terra

Stand: 2026-10-19. Grundlage: **12.0.0 Luna**, Commit `423e492`, Branch `Aquaticy-ai`.

## Was neu ist: Anmeldeschutz gegen Bots

Jede Anmeldung bekommt vor dem Passwort eine Risikozahl aus drei Hinweisen
(`aquaticy/botguard.py`):

| Hinweis | gut | schlecht |
|---|---|---|
| Fingerabdruck des Clients | passt zur App (+0) | wie ein Skript (+40) |
| Fehlversuche dieses Clients (letzte Stunde) | keine (+0) | +4 je Versuch, höchstens +33 |
| dieses Gerät | schon bei dem Konto angemeldet (+0) | neu (+20) |

Dazu der Grundwert 6.

- **Unter 34:** durch, weiter zum Passwort.
- **34 bis 66:** Nachweis. In der Anmeldung erscheint „Bestätige kurz, dass du ein Mensch
  bist“ mit einem Regler, den man ganz nach rechts schiebt. Dazu löst die Seite im Hintergrund
  eine größere Rechenaufgabe.
- **Ab 67:** abgewiesen (429) ohne Passwortprüfung, also ohne Argon2id-Hash. Das Gerät ist
  15 Minuten gesperrt, die Adresse nur, wenn der Client wie ein Skript aussieht.

Die Gewichte geben genau die drei Beispiele der Vorlage:

| Fingerabdruck | Fehlversuche | Gerät | Zahl | Ergebnis |
|---|---|---|---|---|
| passt zur App | 0 | gesehen | 6 | durch |
| passt zur App | 6 | neu | 50 | Regler |
| wie ein Skript | 40 | neu | 99 | abgewiesen |

Ein Browser, dessen Fingerabdruck passt, kommt höchstens auf 59. Er wird nie abgewiesen,
schlimmstenfalls gefragt. Ein Skript muss schon ohne Fehlversuch den Regler bestehen (66) und
wird ab dem ersten Fehlversuch abgewiesen (70). So bleibt ihm ein Rateversuch je Viertelstunde
und Adresse.

### Der Fingerabdruck

Einen echten TLS-Fingerabdruck (JA3/JA4) sieht Aquaticy nicht. Hinter dem Cloudflare-Tunnel
endet die Verschlüsselung des Besuchers bei Cloudflare, der Server sieht nur `cloudflared`. Im
Heimnetz läuft http ohne TLS. Geprüft wird deshalb, was ein Skript ohne Browser nicht von selbst
mitbringt:

- **User-Agent:** ein Browser (`Mozilla/5.0`), kein bekanntes Werkzeug (curl,
  python-requests, Go, Headless-Chrome, Selenium, Playwright, Bots …).
- **Fetch-Metadaten:** `Sec-Fetch-Site: same-origin` und `Sec-Fetch-Mode: cors`.
  - Verlangt nur bei https (Tunnel) und localhost und nur von Chrome, Edge und Firefox, die sie
    seit Jahren schicken.
  - Im Heimnetz (http) schickt kein Browser sie. Ältere WebKit-Fenster (Desktop-App unter
    Linux) schicken sie nicht immer.
- **`Accept-Language`**.
- **Nachweis aus dem Hintergrund:** Beim Besuch holt die Seite eine Rechenaufgabe von
  `/api/auth/challenge` und löst sie, während man tippt.
  - Gesucht ist SHA-256 von „Samen:Zahl“ mit 14 Nullbits, im Mittel gut 16.000 Versuche.
  - Die Aufgabe ist mit einem Schlüssel des Servers signiert. Sie gilt einmal und
    15 Minuten; nach 12 Minuten holt die Seite eine neue.
  - Reines JavaScript statt `crypto.subtle`, das bei http im Heimnetz fehlt. Gerechnet wird in
    Happen, damit die Seite nicht hängt.
- **`navigator.webdriver`:** Ein ferngesteuerter Browser meldet sich so.

### Der Regler

- Die Aufgabe für den Nachweis hat 17 Nullbits (gut 130.000 Versuche) und gilt 5 Minuten und
  einmal.
- Mit der Lösung geht der Weg des Reglers mit: Zeit und Stelle, 6 bis 400 Punkte.
- Der Server verlangt:
  - Start links und Ende rechts;
  - eine Dauer von 0,25 s bis 2 Minuten;
  - eine vorwärts laufende Zeit;
  - wechselndes Tempo (Variationskoeffizient ≥ 0,05).
- Ein Ruck ans Ende oder eine Bewegung wie mit dem Lineal zählt nicht.
- Ein bestandener Regler ersetzt den Nachweis aus dem Hintergrund, der beim ersten Versuch schon
  verbraucht ist.

### Fehlversuche, Gerät und Sperren

- **Gezählt** wird unter der Adresse und, wenn der Browser schon eine hat, unter der
  Geräte-Kennung aus dem Cookie (als Hash).
  - Bei IPv6 zählt das ganze /64-Netz. Ein Anschluss hat meist ein ganzes /64, und ein Bot
    könnte sonst für jeden Versuch eine neue Adresse nehmen.
  - Es gilt die höhere der Zahlen.
- **Ein Fehlversuch** ist ein falsches Passwort oder eine abgewiesene Anmeldung.
- **„Schon gesehen“** heißt: Die Geräte-Kennung aus dem Cookie hat sich schon bei diesem Konto
  angemeldet. Hardware- und Browserangaben zählen hier bewusst nicht, denn die meldet der Client
  selbst, und ein Bot könnte sie nachmachen.
  - Ohne Konto gilt jedes Gerät als neu. So verrät die Zahl nicht, ob es das Konto gibt.
- **Speicher:** Alles liegt nur im Arbeitsspeicher, je höchstens 50.000 Schlüssel. Fehlversuche
  gelten eine Stunde, Sperren 15 Minuten.
- **Reihenfolge beim Anmelden:**
  1. Zustimmung
  2. 8 Versuche je Minute und Adresse
  3. Anmeldeschutz
  4. 10 falsche Passwörter je Konto und Viertelstunde
  5. Passwort

  Die Grenzen 2 und 4 bleiben unverändert.
- **Registrieren** fragt der Schutz nicht. Dort greifen weiter Ai-guard und der Schutz vor
  Mehrfachkonten.

### Oberfläche

- Ein Mensch im Browser merkt in aller Regel nichts. Gefragt wird er erst nach mehreren
  falschen Passwörtern von einem neuen Gerät.
- Abgewiesen heißt die Meldung „Zu viele verdächtige Anmeldeversuche von hier. Bitte versuch es
  später noch einmal.“ Der Server nennt in `Retry-After` die Sekunden bis zum Ende der Sperre.
- Alle neuen Texte gibt es auch auf Englisch.

## Datenschutz

Die Datenschutzerklärung hat einen neuen Punkt „Schutz der Anmeldung vor Bots“. Er nennt:

- was geprüft wird;
- dass die Bewegung des Reglers nur geprüft und nicht gespeichert wird;
- dass Fehlversuche und Sperren nur im Arbeitsspeicher liegen, unter der Adresse oder dem Hash
  der Geräte-Kennung, und nach einer Stunde oder einem Neustart weg sind.

Die Fassung der Rechtstexte (`LEGAL_VERSION`) ist unverändert. Der Schutz braucht keine
Einwilligung. Eine neue Fassung hätte die Zustimmungen zum gemeinsamen Lernen zurückgesetzt.

## Sicherheit und Fehlersuche

- Bei der Arbeit gefunden und behoben:
  - **`Retry-After` aus einer früheren Anfrage:** Bei Keep-Alive lebt der Handler weiter. Ein
    späteres 429 konnte das `Retry-After` einer vorigen Anfrage tragen. Es wird jetzt je
    Anfrage zurückgesetzt.
  - **Bekanntes Gerät nur über das Cookie:** Hardware- und Browserangaben allein hätten ein
    Gerät „bekannt“ wirken lassen. Ein Bot kann sie nachmachen, die zufällige Kennung im Cookie
    nicht. Der Vergleich nutzt `hmac.compare_digest`.
  - **Aufgabe nicht angekommen:** Fehlte nach einem Netzaussetzer der Nachweis, hätte ein
    Mensch nach einem Tippfehler wie ein Skript ausgesehen und wäre abgewiesen worden. Die Seite
    holt dann vor dem Absenden einmal eine neue Aufgabe.
  - **Regler beim Wechsel zu „Registrieren“:** Er blieb stehen. Jetzt verschwindet er.
  - **Ältere Browser ohne `requestSubmit`:** Sie senden nach dem Regler über den Knopf.
  - **IPv6:** Wechselnde Adressen in einem /64-Netz umgingen die Zählung je Adresse. Gezählt
    wird jetzt je /64.
- Keine Sicherheitsregel gelockert. Die bisherigen Grenzen für Anmeldungen bleiben, der Schutz
  kommt davor.
- Die Aufgaben sind zustandslos signiert (HMAC-SHA256, Schlüssel je Prozess). Verbrauchte Samen
  werden begrenzt gemerkt. `/api/auth/challenge` legt also nichts an, was ein Angreifer
  aufblähen könnte.
- Die Prüfung der Aufgabe ist streng: Signatur, Art, Alter, Mindest-Nullbits und Länge von Samen
  und Lösung werden geprüft, bevor gerechnet wird.
- bandit: keine neuen Hinweise.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | erster Volllauf: ein Fehlschlag (siehe unten). Danach alle fünf Schritte ohne Beanstandung (Rückgabewert 0): **5226 bestanden, 31 übersprungen, keine Fehlschläge** (5257 Tests, Browser-Rundgang eingeschlossen) |
| Neue Tests (`tests/test_v1200_terra.py`) | 18, alle bestanden |
| Angepasste Anmeldetests (14 Aufrufe in 9 Dateien, siehe unten) | alle bestanden |
| Browser-Rundgang, neuer Abschnitt „20d. Anmeldeschutz“ | Ein normaler Browser meldet sich ohne Regler an (200). Ein ferngesteuerter (HeadlessChrome, `navigator.webdriver`) bekommt den Regler (428) und kommt nach dem Schieben mit der Maus herein (200). |
| SHA-256 in JavaScript gegen Python (node) | gleich, auch über mehrere Blöcke |
| bandit, mypy, ruff | ohne Beanstandung |

## Geänderte Tests

Alle wegen der gewünschten Änderung: Ein Client, der wie ein Skript aussieht, wird jetzt vor
dem Passwort gefragt. Die Tests meldeten sich bisher mit Kopfzeilen wie `User-Agent: E2E` und
ohne Nachweis an. Geprüft wird in ihnen weiter dasselbe.

- **Neuer Helfer `tests/anmeldung.py`:** Er meldet sich an wie die Seite im Browser, mit
  Browser-User-Agent, Sprache, Fetch-Metadaten und gelöster Rechenaufgabe.
  - Genutzt in `test_cluster_http`, `test_end_to_end`, `test_security`, `test_terra968`,
    `test_v1003`, `test_v9532`, `test_v965` und `test_v967`.
- **Gleicher User-Agent danach:** Die Sitzung hängt an User-Agent und Sprache. Deshalb schicken
  die Test-Clients durchgehend den Browser-User-Agent:
  - `_req` in `test_end_to_end` sowie `_anfrage` und `_mit_kopf` in `test_security` statt `E2E`
    bzw. `Sicherheitstest`;
  - der Client in `test_v965` und `test_cluster_http`;
  - die Browserfenster in `test_v965`, `test_v967`, `test_v1003` und `test_luna9610` statt
    `Parallel-Test`.
- **`test_security::test_one_account_cannot_be_brute_forced_from_many_addresses`:** Der Test
  kam bisher von einer Adresse, sein Name sagt „von vielen“. Jetzt kommt jeder Versuch
  tatsächlich von einer anderen Adresse. Sonst hätte schon der neue Schutz je Adresse
  nachgefragt, bevor die Grenze je Konto greift, um die es dem Test geht.
- **`tests/conftest.py`:** Die Zähler des Anmeldeschutzes werden je Test neu angelegt, wie die
  anderen Grenzen. Sonst trüge ein Test die Fehlversuche eines früheren eine Stunde lang weiter.
- **Rundgang** (`tools/rundgang.py`): neuer Abschnitt 20d (siehe oben).
- **`test_v1200::test_twelve_is_the_version`** verlangte fest den Namen „Luna“. Weil die Fassung
  jetzt absichtlich Terra heißt, prüft der Test die Nummer 12.0.0. Er prüft außerdem, dass die
  Rückfallangabe der Oberfläche zum aktuellen Namen passt. Den Namen selbst prüft
  `tests/test_version.py`.

## Im ersten Volllauf gefunden

- `test_v1200::test_twelve_is_the_version`: Er schlug wegen des neuen Namens fehl (siehe
  „Geänderte Tests“). Sonst lief alles durch: 5225 bestanden, 31 übersprungen.

## Grenzen dieser Prüfung

- **Kein echter TLS-Fingerabdruck.** Siehe oben: Hinter dem Tunnel endet TLS bei Cloudflare.
  Wer den echten JA3/JA4 nutzen will, kann ihn in Cloudflare (Bot Management) auswerten. Das
  ist ein kostenpflichtiger Dienst von Cloudflare und nicht Teil von Aquaticy.
- **Ein gut gebauter Bot kann jeden einzelnen Hinweis nachmachen:** Kopfzeilen, Rechenaufgabe,
  sogar den Regler. Der Schutz macht automatisches Raten teuer und langsam, unmöglich macht er
  es nicht. Dafür bleiben die Grenzen je Adresse und je Konto und Argon2id.
- **Bedienung nur mit der Tastatur:** Den Regler kann man mit den Pfeiltasten oder Bild-auf
  schieben. Ein Sprung mit „Ende“ zählt als Ruck. Gefragt wird ohnehin nur nach mehreren
  Fehlversuchen von einem neuen Gerät.
- Kein Test gegen den echten Cloudflare-Tunnel. Die Kopfzeilen dort sind wie bei https.
