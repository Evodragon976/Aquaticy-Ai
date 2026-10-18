# Aquaticy AI 12.0.0 Luna

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

- [Was Aquaticy kann](#was-aquaticy-kann)
- [Quickstart](#quickstart)
- [Installation im Detail](#installation-im-detail)
- [Benutzung im Terminal](#benutzung-im-terminal)
- [Die Weboberfläche](#die-weboberfläche)
- [Eigene Website mit Domain](#eigene-website-mit-domain)
- [Konten: Normal, Pro und Ultra](#konten-normal-pro-und-ultra)
- [Add-ons](#add-ons)
- [Virtual machine und User mode](#virtual-machine-und-user-mode)
- [Speicher und Aufträge](#speicher-und-aufträge)
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
- **Coworker** (Pro und Ultra): arbeiten dauerhaft an einer Aufgabe. Sie lesen Gmail, Kalender
  und GitHub, melden Ergebnisse und fragen, bevor sie etwas ändern.
- **Add-ons:** **NVIDIA NIM** und **Mistral** (die einzigen Modelle mit API-Schlüssel), GitHub,
  Wetter, RSS-Feeds, Tagesschau, Wikipedia, Währungsrechner, Feiertage, WhatsApp Web, Signal,
  Telegram Web, Blender. Dazu die Plugins **Code-Review** und **Security-Review**. Die Dienste
  und Plugins haben im Chat einen Befehl: `/code-review`, `/github`, `/wetter` …
- **Speicher:** merkt sich, was länger gilt. Verschlüsselt und jederzeit einsehbar.
- **Aufträge:** regelmäßig recherchieren, Preise oder Webcams beobachten.
- **Gmail und Kalender:** lesen, Termine anlegen, Entwürfe schreiben. Verschickt wird nichts.
- **Zuhause** (Ultra): Heimnetz, Home Assistant, Lagerverwaltung.
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
aquaticy --version            # 12.0.0 Luna

# 2. Einrichten: Modell, Suche, auf Wunsch eine eigene Domain
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
| KI-Anbieter | Mistral oder NVIDIA NIM (den Schlüssel verknüpfst du danach in der Weboberfläche unter Add-ons) · oder lokal mit [Ollama](https://ollama.com), ohne Schlüssel | ja |
| Suchmaschine | nichts – die offene Suche braucht keinen Schlüssel | nein |
| Eigene Domain | eine Domain bei Cloudflare und ein API-Token ([so geht's](#eigene-website-mit-domain)) | nein |

Aquaticy testet alles, bevor es speichert. Die Einstellungen liegen in
`~/.config/aquaticy/.env` und sind nur für dich lesbar.

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

Der Befehl sucht Ollama und fragt, bevor er etwas installiert. Er schlägt ein Modell vor, das
zu Arbeitsspeicher und Grafikkarte passt, lädt es und testet, ob es Werkzeuge bedienen kann.
Nur ein Modell, das den Test besteht, wird eingetragen. Auf Wunsch kommt ein Bildmodell dazu.

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
aquaticy install-browser        # echter Browser für schwierige Seiten
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
- **🎨 Bilderstellung:** Aquaticy nimmt ein Modell, das Bilder kann (NVIDIA FLUX oder Mistral).
- **⚡ Aufwand:** Denktiefe Low, Medium oder High und die Zahl der Helfer (Normal und Code
  1–12, Pro 1–50).
- **⚙ Weitere Einstellungen:** Websuche, Webcams und Satellitenbilder, Denken, Strukturieren,
  Gegenprüfen. Im Code-Modus: Code in der virtual machine ausprobieren, darunter (Ultra) ob sie
  Internet hat.

**Einstellungen** speichern sich selbst. Schalter sofort, Textfelder beim Verlassen. Was nur
Ultra darf, trägt ein 🔒.
- **Konto:** Name, E-Mail, Kontotyp, Nutzung, Abmelden. **Sicherheit** mit deinen Geräten,
  Passwort ändern, überall sonst abmelden. **Daten und Konto löschen**.
- Dazu: Gemeinsames Lernen, Modell, Eigene Modelle, virtual machine, Speicher, Mitlesen,
  Auslastung (Ultra), Nutzung, Aufträge, Gmail & Kalender, Zuhause & Netz (Ultra), Suche,
  Ort & Sprache, Helfer & Grenzen, **Dev settings** (Ultra).

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

Wer die Weboberfläche öffnet, legt zuerst ein Konto an. Jedes Konto hat eigene Chats,
Einstellungen, Speicher und Schlüssel.

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

*Einstellungen → Modell oder virtual machine → 🧩 Add-ons.* Jedes Add-on lässt sich
installieren, an- und ausschalten und entfernen. Aus dem Chat heraus geht das nicht. Anmelden musst du dich selbst –
Aquaticy kennt keine Passwörter. Unter **Rechte** stellst du ein, was Aquaticy damit darf.

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
| 💬 WhatsApp Web | Chats lesen, Antworten vorbereiten. Senden nur nach deinem Ja | QR-Code |
| 🔵 Signal | wie WhatsApp, mit Signal Desktop | QR-Code |
| ✈️ Telegram Web | Kanäle und Gruppen lesen, Antworten vorbereiten | QR-Code |
| 🧊 Blender | 3D-Modelle bauen und rendern in der virtual machine | keine |
| 🔍 Code-Review | prüft Code auf typische Fehler, gerade bei KI-Code | keine |
| 🛡️ Security-Review | sucht Sicherheitslücken nach OWASP und zeigt die Lösung | keine |

WhatsApp, Signal, Telegram und Blender laufen in der virtual machine und brauchen den User mode
(Ultra). Die Tagesschau ist nur für den privaten Gebrauch. Aquaticy hält die erlaubten 60
Abrufe pro Stunde ein.

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
| Normal | 1 | 1 GB | 4 GB |
| Plus (Ultra) | 4 | 6 GB | 20 GB |

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

## Speicher und Aufträge

**Speicher.** Aquaticy merkt sich, was länger gilt: Wohnort, Vorlieben, laufende Vorhaben. Nur
Text, verschlüsselt, höchstens 400 MB je Konto. Unter **„Was weißt du über mich?“** siehst du
jeden Eintrag und löschst ihn einzeln oder alle.

**Aufträge** (*Einstellungen → Aufträge*). Aquaticy bleibt dran:

- **regelmäßig recherchieren** – stündlich, täglich, wöchentlich;
- **Kamera, Satellit oder Straße beobachten** – z. B. „ein oranges Flugzeug ist sichtbar“;
- **Preis beobachten**;
- **Bild hochladen und danach suchen**, bis ein Angebot auftaucht.

Tritt ein, worauf du wartest, bekommst du einen neuen Chat mit Bild und Uhrzeit. Nur
öffentliche Quellen, keine privaten Kameras, keine Anmeldungen.

---

## Coworker

*Seitenleiste → 🤝 Coworker* (Pro und Ultra). Ein Auftrag stellt eine feste Frage in festem
Takt. Ein **Coworker** übernimmt eine *Aufgabe* und bleibt dran, solange sie dauert. Das
Vorbild ist „dots“ in ChatGPT. Beispiele: „Sag mir jeden Morgen, welche Mails wichtig sind“
oder „Behalte meine GitHub-Repos im Blick“.

- **Er arbeitet in Schritten, die ganze Zeit.** Nach jedem Schritt entscheidet er, wann er
  wieder aufwacht. Mitten in der Arbeit nach wenigen Minuten, beim Warten erst morgen. Schreibst
  du ihm, wacht er sofort auf.
- **Er hat ein Gedächtnis.** Seine Notizen kannst du jederzeit lesen.
- **Er nutzt deine Verbindungen.** Gmail, Kalender, GitHub und die anderen Add-ons, mit
  denselben Rechten wie im Chat.
- **Er meldet sich.** Ergebnisse und Fragen stehen in der Übersicht und als eigener Chat. Das
  Abzeichen zeigt, was neu ist.
- **Er fragt, bevor er etwas ändert.** Für jede Art Aktion stellst du eine **Regel** ein:
  *Erlauben*, *Fragen* oder *Sperren*. Das gilt für Termine, Mail-Entwürfe, Speicher und (Ultra)
  Lager, Home Assistant und Heimnetz. Bei „Fragen“ siehst du genau, was passieren würde.
  Ausgeführt wird genau das, vom Code und nicht noch einmal vom Modell. Hat er Webseiten oder
  Mails gelesen, fragt er auch bei „Erlauben“. So kann ihn ein fremder Text zu nichts
  überreden.
- **Ultra: eigener Rechner.** Jeder Coworker bekommt eine eigene virtual machine ohne Desktop.

| | Pro | Ultra |
|---|---|---|
| Coworker | bis zu 2 | bis zu 5 |
| Frühestens wieder wach nach | 15 Minuten | 5 Minuten |
| Arbeitsschritte je Coworker und Tag | 48 | 288 |
| Eigene virtual machine | – | ✔ (mit Docker oder Podman) |

Coworker zählen ins Kontingent. Ist es leer, macht der Coworker weiter, sobald es sich
zurücksetzt. Im Server-Verbund arbeitet er nur auf dem Heimserver seines Kontos.

---

## Gmail und Kalender

Aquaticy liest Termine und Mails. Mit „Ändern erlaubt“ legt es auch Termine an und schreibt
Mail-**Entwürfe**. **Verschickt und gelöscht wird nichts.** Aquaticy bietet dafür keine
Werkzeuge an und verwendet feste API-Pfade. Googles Recht `gmail.compose` wird für Entwürfe
benötigt und erlaubt technisch auch Senden; die Begrenzung auf Entwürfe liegt daher im Code.

**Einrichten (einmal, etwa fünf Minuten):**

1. Auf [console.cloud.google.com](https://console.cloud.google.com/) ein Projekt anlegen.
2. **APIs und Dienste → Bibliothek:** „Gmail API“ und „Google Calendar API“ aktivieren.
3. **OAuth-Zustimmungsbildschirm:** Nutzertyp „Extern“, dich als Testnutzer eintragen.
4. **Anmeldedaten → OAuth-Client-ID**, Typ **Desktop-App**, Weiterleitung
   `http://localhost:8765/google`.
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
- **Lagerverwaltung:** Räume → Möbel → Artikel. Aquaticy sagt, wo etwas liegt und wie viel da
  ist. Mit „Lesen und schreiben“ legt es auch an. Gelöscht wird nie.

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
- **Antworten werden mitgeprüft.** Eine unangemessene Antwort wird zurückgezogen.
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
| Recherche und Antwort | `mistral-large-latest` | `meta/llama-3.3-70b-instruct` |
| Helfer, Planung | `mistral-small-latest` | `meta/llama-3.1-8b-instruct` |
| Code-Modus | `codestral-latest` | `qwen/qwen2.5-coder-32b-instruct` |

```bash
aquaticy --model mistral/mistral-large-latest
aquaticy --model nvidia_nim/meta/llama-3.3-70b-instruct
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
| `AQUATICY_VM_IMAGE` | Abbild der virtual machine | `python:3.12-slim` |
| `AQUATICY_VM_USER_MODE` | User mode (Ultra) | `false` |
| `AQUATICY_VM_INTERNET` | Internet für die virtual machine (Ultra) | `false` |
| `AQUATICY_VM_LAN` | virtual machine auch ins lokale Netz (Ultra) | `false` |
| `AQUATICY_VM_DESKTOP_IMAGE` | Abbild für den User mode | `aquaticy-werkstatt-desktop:local` |
| `AQUATICY_VM_IDLE_MINUTES` | virtual machine löschen nach Minuten Ruhe | `20` |
| `AQUATICY_ANSWER_CHECK` | Ai-guard prüft auch Antworten | `true` |
| `AQUATICY_GITHUB_TOKEN` | Token des GitHub-Add-ons | – |
| `AQUATICY_GOOGLE` / `AQUATICY_GOOGLE_WRITE` | Gmail und Kalender lesen / ändern | `false` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | eigene Google-Anwendung | – |
| `AQUATICY_HA_URL` / `AQUATICY_HA_CONTROL` | Home Assistant / schalten erlaubt (Ultra) | – / `false` |
| `AQUATICY_LAN_ENABLED` / `AQUATICY_LAN_SUBNET` | Heimnetz ansehen (Ultra) | `true` / automatisch |
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

Was zuletzt geprüft wurde und wo die Grenzen liegen, steht im
[Prüfbericht](TESTREPORT-12.0.0-Luna.md).

---

## Lizenz

MIT. Der volle Text steht in [`LICENSE`](LICENSE).
