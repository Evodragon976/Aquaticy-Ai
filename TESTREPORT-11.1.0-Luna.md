# Prüfbericht: 11.1.0 Luna

Stand: 2026-10-13. Grundlage: **11.0.0 Luna**, Commit `460f76a`, Branch `Aquaticy-ai`.

## Was neu ist

- **Websites lesen sich wieder.** Drei Fehler machten viele normale Seiten unlesbar (siehe unten).
- **Karte.** Ist OpenStreetMap ausgelastet, gilt das nicht mehr als „hier gibt es nichts“.
- **Nachrichten.** „Was sind die neusten Nachrichten?“ bringt die Meldungen selbst, nicht eine
  Liste von Nachrichtenseiten.
- **Eigene Website mit Domain** (`aquaticy/website.py`): Cloudflare-Tunnel, Zertifikat von
  Let's Encrypt, `cloudflared` lädt sich selbst. Mit Domain ist `aquaticy web` im Heimnetz, über
  Tailscale und unter der Domain erreichbar.
- **Texte:** README neu, die längsten Texte der Oberfläche gekürzt, Terminal- und Browser-Meldungen
  mit echten Umlauten.

## Gefundene Fehler und ihre Ursache

**Websites**
1. Stand irgendwo im HTML „captcha“, galt die ganze Seite als Bot-Sperre. Ein reCAPTCHA im
   Kontaktformular reichte. Jetzt zählt eine Sperre nur, wenn die Seite kaum eigenen Text hat.
2. Die Cookie-Banner-Filter löschten manchmal den ganzen Inhalt: wenn `<body>` eine
   Cookie-Klasse trug („cookies-not-set“) oder die Seite aus Adobe-Bausteinen („cmp-…“) bestand.
   Seitenträger und große Textblöcke bleiben jetzt stehen, im Browser-Weg genauso.
3. Kurze Aussetzer (DNS, nicht erreichbare `robots.txt`, 429, 5xx) wurden 24 Stunden gemerkt.
   Die Seite blieb einen Tag „kaputt“. Jetzt werden Aussetzer gar nicht gemerkt, echte
   Fehlschläge höchstens eine Stunde.
4. Bei kaputtem IPv6 ging die ganze Wartezeit für den ersten Verbindungsversuch drauf, bevor
   IPv4 drankam. Jetzt wechseln sich IPv6 und IPv4 ab, und jeder Versuch außer dem letzten ist
   kurz (2,5 s).

**Karte**
5. Overpass meldet Überlast mit Status 200, einer leeren Liste und einem Hinweis („runtime
   error“). Das galt als leeres Ergebnis und blieb einen Tag gemerkt. Jetzt kommt der nächste
   Server dran. Ein leeres Ergebnis bleibt höchstens eine Stunde gemerkt.

**Nachrichten**
6. Im Standardmodus entscheidet das Modell, ob es sucht. Viele Modelle antworteten aus dem
   Gedächtnis mit Nachrichtenseiten. Jetzt holt Aquaticy bei solchen Fragen die Meldungen vorab
   selbst. Ohne Thema kommen die Schlagzeilen aus den Feeds großer Redaktionen.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Testsuite (`pytest`) | erster Lauf: 4718 bestanden, 27 übersprungen, 14 Fehlschläge – 13 davon prüften absichtlich geänderte Texte, einer fand eine echte Lücke (`aquaticy website` fehlte in der Terminal-Hilfe, behoben); Ergebnis des Laufs nach den Korrekturen folgt |
| Neue Tests: Websites und Karte / Nachrichten / Website mit Domain | 21 / 30 / 42, alle bestanden |
| Stilprüfung (`ruff check aquaticy tests`) | keine Beanstandung |
| Typprüfung (`mypy`) der neuen Module | keine Fehler |
| Sicherheitsscan (`bandit`) der neuen Module | nur erwartete Hinweise (`subprocess` mit festen Argumenten, ein Variablenname) |
| Overlay-Entfernung im echten Chromium | Inhalt bleibt, Overlay verschwindet |
| `aquaticy web` mit Domain, echter Start | Domain, Heimnetz und dieser Rechner werden angezeigt; Tunnel-Eingang antwortet per HTTPS; Cluster dort 404; Dateien nur für den Besitzer lesbar |
| JavaScript der Oberfläche (`node --check`) | ohne Fehler |

## Sicherheit der Website mit Domain

- **Eigener Eingang für den Tunnel**, nur auf `127.0.0.1`, nur HTTPS. Alles, was dort ankommt,
  gilt als Internet:
  - Die Adresse des Besuchers kommt von Cloudflare (`CF-Connecting-IP`). Am normalen Eingang
    zählt diese Kopfzeile nicht – dort könnte sie jeder setzen.
  - Der Server-Verbund ist dort nicht erreichbar (404). Er vertraut dem eigenen Netz, und dazu
    gehört 127.0.0.1.
  - Cookies nur mit `Secure`, dazu HSTS.
- **Bei der eigenen Prüfung gefunden und behoben:** Mit Domain lauscht `aquaticy web` auf allen
  Netzwerkkarten. Auf einem Server mit öffentlicher Adresse (etwa einem gemieteten) wäre Port
  8765 damit unverschlüsselt aus dem Internet erreichbar gewesen. Jetzt nimmt dieser Eingang mit
  Domain nur Heimnetz, Tailscale und den Rechner selbst an. Alle anderen bekommen 403 mit dem
  Hinweis auf die Domain.
- **Bei der eigenen Prüfung gefunden und behoben:** Neue Konten von 127.0.0.1 sind von der
  Mehrfachkonto-Regel ausgenommen. Ohne die echte Besucheradresse hätte das für alle
  Internetbesucher gegolten.
- **cloudflared prüft das Zertifikat immer** gegen die Domain. Bis das von Let's Encrypt da ist,
  vertraut es genau dem selbst ausgestellten (`caPool`), nie „ungeprüft“ (`noTLSVerify`).
- **Tunnel-Token nie auf der Befehlszeile** (die liest jeder mit `ps`), sondern über die Umgebung.
  `cloudflared` bekommt nur die nötigen Umgebungsvariablen, nicht die API-Schlüssel von Aquaticy.
- **Dateien** (Tunnel-Token, Schlüssel, Zertifikate, Protokoll) nur für den Besitzer lesbar,
  atomar geschrieben. Das Cloudflare-Token steht in der `.env` (0600) und ist in der
  Weboberfläche weder sichtbar noch änderbar.
- **cloudflared** nur von GitHub, nur mit veröffentlichter SHA-256-Prüfsumme, sicher entpackt.
- **Fremde DNS-Einträge** bleiben stehen: Gibt es für die Domain schon einen A- oder
  CNAME-Eintrag, bricht die Einrichtung mit einer klaren Meldung ab.
- **Let's Encrypt:** Konto- und Zertifikatsschlüssel EC P-256; das Zertifikat wird nur
  gespeichert, wenn es zum Schlüssel und zur Domain passt. Der Prüfeintrag im DNS verschwindet
  danach wieder, auch bei einem Fehlschlag.

## Grenzen dieser Prüfung

- **Kein echtes Netz.** Aus dieser Umgebung waren Websites, OpenStreetMap, Cloudflare, Let's
  Encrypt und GitHub nicht erreichbar. Geprüft wurde gegen nachgebaute Dienste:
  - ein ACME-Server, der Signatur (ES256), Nonce, Adresse und den DNS-Prüfeintrag wirklich
    prüft und mit einer Test-CA ausstellt;
  - eine Cloudflare-API mit Zonen, Tunneln, Einträgen und Token;
  - Websites, Overpass und Nominatim.
  Die Cloudflare-Aufrufe (Tunnel anlegen, `configurations`, Token, DNS) wurden zusätzlich mit
  der aktuellen Dokumentation abgeglichen.
- **Ob eine bestimmte Website jetzt lesbar ist**, hängt von ihr ab. Seiten mit echter
  Bot-Sperre bleiben gesperrt – das umgeht Aquaticy nicht.
- **Die Feed-Adressen** der Nachrichtenseiten sind veröffentlichte RSS-Adressen. Fällt eine
  aus, nimmt Aquaticy die anderen und zuletzt die Nachrichtensuche.
- **Kein echtes Sprachmodell.** Der Vorabruf der Nachrichten wurde mit einem gestellten Modell
  geprüft.
