# Aquaticy AI 11.0.0 Luna

**Aquaticy** recherchiert für dich. Du stellst eine Frage, Aquaticy sucht im Web, liest die
passenden Seiten und fasst das Ergebnis zusammen — mit Quelle an jeder Angabe. Es läuft im
Terminal, im Browser und auf dem Handy.

```
$ aquaticy

> Finde mir gute Cafés in Mönchengladbach mit WLAN

  [Suche] cafés mönchengladbach
  [Suche] café mönchengladbach wlan arbeiten
  [Lese]  4 Seiten...

  Ich habe 6 Cafés gefunden, die zu deiner Anfrage passen:

  1. Café Nordwand — Hindenburgstr. 12
     WLAN ausdrücklich erwähnt, Steckdosen an den Fensterplätzen.
     Quelle: die gelesene Café-Seite
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
- Sucht selbst im Web, liest die Seiten und nennt zu jeder Angabe die Quelle.
- Merkt sich den Gesprächsverlauf: Nachfragen wie „nur die mit 4+ Sternen“ funktionieren.
- Fragt selbst nach, wenn etwas Entscheidendes offen ist (Budget, Ort, was gemeint ist).
- **Strukturieren:** zerlegt große Fragen in Teilfragen und schickt für jede einen eigenen
  Helfer los — im Pro-Modus bis zu 50 gleichzeitig.
- **Gegenprüfen:** prüft Ergebnisse auf anderen Seiten nach.
- **Bilder als Eingabe:** Foto anhängen, Aquaticy erkennt, was darauf ist, und sucht danach.
- **Öffentliche Webcams und Satellitenbilder** auf Wunsch einbeziehen.
- Funktioniert auch ohne Internetsuche — dann aus eigenem Wissen, mit Hinweis, wo es veraltet
  sein könnte.
- **Sofortantworten ohne Modell:** „Hallo“, „Danke“ oder „Wer bist du?“ beantwortet Aquaticy
  sofort und kostenlos; alles, was Suche oder Nachdenken braucht, geht an das Modell.

**Arbeitsweisen**
- **Normal** — ein ganz normales Gespräch, gesucht wird, wenn es nötig ist. Jeder Helfer hat
  eine Frist und fasst danach zusammen, was er gefunden hat, statt die Antwort aufzuhalten.
- **Pro** — für große Fragen: das stärkste Modell und bis zu 50 Helfer. Dauert bewusst länger,
  dafür genauer.
- **Code** — schreibt Code statt langer Texte und probiert ihn in einer abgeschotteten
  **virtual machine** wirklich aus.

**Oberfläche**
- Terminal-Chat, Weboberfläche im Browser, Zugriff vom Handy im eigenen Netz — auf PC, Tablet
  und Handy jeweils passend aufgebaut.
- **Design:** Hell, Dunkel oder wie das System; Standard (grün), Schlicht (schwarz-weiß) oder
  ein eigenes Design mit eigenen Farben.
- **Sprache:** Deutsch oder Englisch — Oberfläche und Antworten wechseln sofort.
- Chats durchsuchen, umbenennen, exportieren (HTML, Markdown, CSV).

**Extras**
- **Coworker** (Pro und Ultra): arbeiten die ganze Zeit an einer Aufgabe — recherchieren,
  lesen Gmail, Kalender und GitHub, melden sich mit Ergebnissen und fragen, bevor sie etwas
  verändern. Mit Ultra zusätzlich in ihrer eigenen virtual machine.
- **Add-ons:** KI-Konten (Claude, ChatGPT, Gemini), GitHub, Wetter, RSS-Feeds, Tagesschau,
  Wikipedia, Währungsrechner, Feiertage, WhatsApp Web, Signal, Telegram Web, Blender — und die
  Plugins **Code-Review** und **Security-Review**. Jedes eingeschaltete Add-on hat im Chat
  einen Befehl: `/code-review`, `/github`, `/wetter` …
- **Speicher:** merkt sich auf Wunsch, was länger gilt — verschlüsselt, jederzeit einsehbar.
- **Aufträge:** regelmäßig recherchieren, Preise, Webcams oder Satellitenbilder beobachten.
- **Gmail und Kalender:** Termine und Mails lesen, auf Wunsch Termine anlegen und
  Mail-Entwürfe schreiben (verschickt wird nie etwas).
- **Zuhause** (Ultra): Geräte im Heimnetz finden, Home Assistant, Lagerverwaltung.
- **KI-Bilder** erstellen lassen; **Modell automatisch wählen** für jede Nachricht.
- **Server-Verbund** (Ultra): bis zu 10 Server arbeiten zusammen — entweder verteilen sie die
  Nutzer, oder sie rechnen gemeinsam an einem großen Modell (llama.cpp installiert sich dafür
  von selbst).

**Stabil im Betrieb**
- Belegter Port → Aquaticy nimmt den nächsten freien und zeigt die Adresse im Terminal.
- Absturz → automatischer Neustart (höchstens fünfmal in zehn Minuten).
- Ein Modell-Anbieter streikt → das schnelle Modell desselben Anbieters übernimmt.
- Kurzer Verbindungsabbruch → die Seite hängt sich wieder an die laufende Antwort; ohne Netz
  erscheint nur ein dezenter Hinweis.
- Fehler sehen Nutzer nur als verständliche, allgemeine Meldung — nie als technischen Fehlertext.

---

## Quickstart

```bash
# 1. Installieren (aus diesem Repo)
git clone --branch Aquaticy-ai --single-branch https://github.com/jonasenriklaumen-a11y/Aquaticy-Ai.git
cd Aquaticy-Ai
uv tool install --force --reinstall .
aquaticy --version            # 11.0.0 Luna

# 2. Einrichten — fragt nach Modell und Schlüssel und testet beide
aquaticy setup

# 3. Loslegen — im Terminal …
aquaticy

# … oder im Browser (öffnet sich von selbst)
aquaticy web
```

**Voraussetzungen:** Python 3.11 oder neuer und [uv](https://docs.astral.sh/uv/).

**Mindest-Hardware:**

| Betrieb | CPU | RAM | Speicher |
|---|---|---|---|
| Modell in der Cloud (Mistral, NVIDIA, verknüpfte Konten) | 1 Kern | 1 GB | 1 GB |
| + Seiten mit echtem Browser | 2 Kerne | 2 GB | 2 GB |
| + virtual machine (Code-Modus, Add-ons) | 2 Kerne | 4 GB | 10 GB |
| Lokales Modell mit Ollama | 4 Kerne | 8 GB (GPU empfohlen) | 10 GB |
| Großes Modell, auf mehrere Server verteilt | je Server 4 Kerne | zusammen etwa Modellgröße + 15 % | Modell auf dem Master |

`aquaticy setup` fragt genau zwei Dinge:

| Was | Woher | Pflicht? |
|---|---|---|
| KI-Anbieter + Schlüssel | [Mistral](https://console.mistral.ai/api-keys/) · [NVIDIA NIM](https://build.nvidia.com/) · oder lokal mit [Ollama](https://ollama.com), ganz ohne Schlüssel | ja |
| Suchmaschine | Nichts — die offene Suche ist Standard und braucht weder Schlüssel noch Konto. | nein |

Beides wird sofort getestet, bevor die Einstellungen gespeichert werden
(`~/.config/aquaticy/.env`, nur für dich lesbar).

Eine einzelne Frage ohne Chat:

```bash
aquaticy "welche Bahnstrecken in NRW sind gerade gesperrt?"
```

**Aktualisieren** (im Repo-Ordner ausführen):

```bash
cd ~/Aquaticy-Ai
git switch Aquaticy-ai
git pull --ff-only origin Aquaticy-ai
uv tool install --force --reinstall .
aquaticy --version
```

`git pull` allein aktualisiert ein installiertes `aquaticy` nicht — erst der `uv`-Befehl
installiert die neue Fassung. Wer GitHubs
[Download ZIP](https://github.com/jonasenriklaumen-a11y/Aquaticy-Ai/archive/refs/heads/Aquaticy-ai.zip)
nutzt, lädt das ZIP neu herunter und führt `uv tool install --force --reinstall .` im
entpackten Ordner aus.

---

## Installation im Detail

### Linux und macOS

Wie im Quickstart. Zum Entwickeln stattdessen:

```bash
uv venv && uv pip install -c constraints.txt -e ".[browser,dev]"
uv run aquaticy
```

### Windows (PowerShell)

```powershell
# uv installieren, falls noch nicht vorhanden
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

git clone --branch Aquaticy-ai `
  https://github.com/jonasenriklaumen-a11y/Aquaticy-Ai.git
cd Aquaticy-Ai
uv tool install --force --reinstall .
uv tool update-shell        # danach PowerShell neu öffnen

aquaticy install-model      # holt Ollama per winget und lädt die Modelle
```

- Ohne winget: Installer von [ollama.com/download](https://ollama.com/download) laden und
  `aquaticy install-model` erneut starten.
- Pfade in Anführungszeichen: `aquaticy --image "C:\Users\du\Bilder\foto.jpg"`
- Pfeiltasten-Verlauf im Chat: `pip install pyreadline3`

### Ganz ohne Schlüssel: lokales Modell

```bash
aquaticy install-model
```

Der Befehl sucht Ollama (und fragt, bevor er etwas installiert), startet es, schlägt anhand
von Arbeitsspeicher und Grafikkarte ein passendes Modell vor, lädt es und prüft an einem echten
Aufruf, ob es Werkzeuge bedienen kann. Nur ein Modell, das den Test besteht, wird eingetragen.
Auf Wunsch richtet er zusätzlich ein Modell für Bilder ein.

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

> Das Modell-Kürzel muss `ollama_chat/` lauten, nicht `ollama/` — nur so kommen Werkzeuge
> durch. `aquaticy install-model` schreibt es automatisch richtig.

Wird der Grafikspeicher knapp (`model runner has unexpectedly stopped`), bietet Aquaticy von
selbst ein kleineres Modell an. Von Hand: `ollama ps`, `ollama stop <modell>`. Ist ein Modell
für einen einzelnen Rechner zu groß, kann ein [Server-Verbund](#serverlast-aufteilen) es auf
mehrere Server verteilen.

### Seiten mit echtem Browser laden

Für Seiten, die ihren Inhalt erst per JavaScript nachladen:

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
| `/history` | frühere Recherchen anzeigen |
| `/notes` | Merkzettel anzeigen |
| `/notes delete <nr>` / `/notes clear` | Notiz oder alle Notizen löschen |
| `/clear` | Gespräch neu beginnen |
| `/memory` / `/forget` | Langzeitspeicher anzeigen oder leeren |
| `/uploads` / `/uploads clear` | Hochgeladene Dateien anzeigen oder löschen |
| `/help` | Übersicht |
| `/<plugin> <text>` | ein eingeschaltetes Plugin gezielt nutzen, z. B. `/code-review`, `/github` |
| `/quit` / `/exit` / `/q` | Terminal beenden (auch <kbd>Strg</kbd>+<kbd>D</kbd>) |

### Optionen

```bash
aquaticy --location "Mönchengladbach" --lang de   # Ortsfilter vorgeben
aquaticy --model mistral/mistral-large-latest     # Modell für diese Sitzung
aquaticy --image foto.jpg                         # Bild als Ausgangspunkt
aquaticy --max-calls 30                           # mehr Suchen je Frage erlauben
aquaticy --no-stream                              # Antwort am Stück statt fließend
aquaticy --download-images                        # Bilder beim Export mitspeichern
```

### Alle Befehle

```bash
aquaticy setup                  # Ersteinrichtung
aquaticy config                 # aktive Einstellungen prüfen
aquaticy web                    # Weboberfläche starten
aquaticy web --lan              # auch vom Handy und anderen Servern im eigenen Netz erreichbar
aquaticy search "cafés köln"    # nur suchen, ohne KI
aquaticy fetch https://…        # nur eine Seite lesen, ohne KI
aquaticy history                # vergangene Recherchen
aquaticy export html -n 3       # letzte 3 Recherchen exportieren
aquaticy notes                  # Merkzettel anzeigen (--delete N löscht)
aquaticy cache                  # Zwischenspeicher anzeigen (--clear leert ihn)
aquaticy install-model          # lokales Modell einrichten
aquaticy install-browser        # echten Browser für schwierige Seiten
aquaticy google                 # Gmail und Kalender verbinden (--aendern: auch schreiben)
aquaticy connect-ha             # Home Assistant verbinden
aquaticy lan                    # Geräte im eigenen Netz anzeigen
aquaticy sandbox                # zeigt, wie abgeschottet Aquaticy gerade läuft
aquaticy cluster                # Server-Verbund: Stand anzeigen, Anfragen mit yes/no beantworten
aquaticy list                   # Konten mit Adress-Kürzel (#…), Geräten, Nutzung und Ai-guard-Stand
aquaticy remove "name"          # Konto samt privaten Daten löschen (fragt nach; --yes ohne Rückfrage)
aquaticy ban "name"             # Konto, IP-Adresse oder Adress-Kürzel ("#1a2b3c4d") sperren
aquaticy unban "name"           # wieder freigeben
aquaticy aiguard "Satz"         # zeigt, wie Ai-guard einen Satz einstuft (sperrt niemanden)
aquaticy pro-code               # Code für neue Pro-Konten
aquaticy ultra-code             # Code für neue Ultra-Konten
aquaticy version
```

---

## Die Weboberfläche

```bash
aquaticy web          # öffnet sich im Browser
aquaticy web --lan    # zeigt alle Adressen, unter denen es im Heimnetz erreichbar ist
```

**Chat.** Links die letzten Chats (durchsuchbar), in der Mitte das Gespräch, unten die Eingabe
mit den drei Arbeitsweisen Normal, Pro und Code. Dateien und Bilder hängst du mit 📎 an. Du
kannst während einer Recherche in einen anderen Chat wechseln oder einen neuen anfangen — die
Recherche läuft im Hintergrund weiter. Auf dem Handy stehen Menü, Logo und „Neuer Chat“ in einer
eigenen Kopfzeile, und Fenster wie die Einstellungen füllen den ganzen Bildschirm.

**Während Aquaticy arbeitet** stehen statt einer langen Schrittliste nur wenige Zeilen da
(„Denken“, „Websuche“, …), daneben bewegt sich das Logo. Ein Klick auf eine Zeile zeigt, was
darin passiert ist — Gedanken, Suchanfragen, gelesene Seiten. Fehler, Sperren und Abbrüche
bleiben immer sichtbar; nach einem Fehler holt „↻ Erneut versuchen“ dieselbe Frage noch einmal.

**Modellauswahl** (unten, links neben dem Senden-Knopf):
- Oben die **Modelle** zur Wahl — Cloud, lokal, verknüpfte KI-Konten, verbesserte Fassungen aus
  dem Auto-Upgrading und, wenn der Server-Verbund eines verteilt, das **Verbund-Modell**.
- **🎨 Bilderstellung:** Aquaticy nimmt selbst ein Modell, das Bilder erstellen kann (NVIDIA
  FLUX oder Mistral, je nach Schlüssel).
- **⚡ Aufwand:** **Denktiefe** Low / Medium / High und die Zahl der **Helfer** (Normal und
  Code 1–12, Pro 1–50).
- **⚙ Weitere Einstellungen:** **Im Web suchen**, **Öffentliche Webcams & Satellitenbilder**,
  **Denken** (mitlesen), **Strukturieren**, **Gegenprüfen** — und im Code-Modus **Code
  wirklich ausprobieren** in der virtual machine.

**Einstellungen** speichern sich selbst: Schalter sofort, Textfelder beim Verlassen des Feldes
(oder mit Enter); kurz erscheint „Gespeichert“. Funktionen nur für Ultra sind mit 🔒
gekennzeichnet.
- **Konto** — Name, E-Mail, Kontotyp, Nutzung, Abmelden; **Sicherheit** mit deinen Geräten,
  **Passwort ändern**, **Überall sonst abmelden**; **Daten und Konto löschen**.
- **Gemeinsames Lernen**, **Modell**, **Eigene Modelle**, **virtual machine**, **Speicher**,
  **Mitlesen**, **Auslastung** (Ultra), **Nutzung**, **Aufträge**, **Gmail & Kalender**,
  **Zuhause & Netz** (Ultra), **Suche**, **Ort & Sprache**, **Helfer & Grenzen**,
  **Dev settings** (Ultra: Rechts-Leitplanken, Modell automatisch wählen, AI Council,
  Auto-Upgrading, Server-Verbund).

**Design** (links unten): Hell, Dunkel oder wie das System; **Standard**, **Schlicht** oder
**Design selber erstellen** (Akzent, Hintergrund, Seitenleiste); **Schriftgröße** und
**Sprache**. Alles wird am Konto gespeichert und gilt auf jedem Gerät.

**Merkzettel** — was sich Aquaticy über dich gemerkt hat; jede Zeile einzeln löschbar.

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

**Codes.** Beim ersten Start erzeugt Aquaticy zwei geheime Codes und zeigt sie im Terminal:
den **Pro-Code** (9 Zeichen; später mit `aquaticy pro-code`, vorgeben mit `AQUATICY_PRO_CODE`)
und den **Ultra-Code** (14 Zeichen mit Buchstaben, Ziffern und Sonderzeichen; später mit
`aquaticy ultra-code`, vorgeben mit `AQUATICY_ULTRA_CODE`).

**Nutzung.** Die Sitzung beginnt mit deiner ersten Nachricht und läuft fünf Stunden, die Woche
beginnt zur Uhrzeit deiner Kontoerstellung. Angezeigt wird beides in Prozent (*Einstellungen →
Nutzung*, ab 80 % auch als Hinweis). Gezählt wird nur auf dem Server — wer Chats löscht, löscht
nicht seinen Verbrauch. Anfragen über **eigene Schlüssel** zählen nicht gegen das Limit.

**Mehrfachkonten: Anhaltspunkte statt „ein Konto pro IP-Adresse“.** Zwei Menschen im selben
Haushalt teilen sich die Adresse — das allein sperrt nicht. Aquaticy zählt Punkte gegen jedes
vorhandene Konto; ab **3 Punkten** wird kein neues Konto angelegt.

| Anhaltspunkt | Punkte |
|---|---|
| dasselbe Gerät (zufällige Geräte-Kennung im Cookie `aquaticy_device`) | 3 |
| gleiche Hardware **und** gleicher Browser | 1,5 |
| gleiche Hardware | 1 |
| gleicher Browser | 0,5 |
| dieselbe IP-Adresse (Anlege- oder zuletzt genutzte) | 1 |
| sehr ähnliche E-Mail-Adresse (`max.muster@…` / `maxmuster7@…`) | 1 |

Gespeichert werden je Konto höchstens 20 Geräte: die Kennung nur als Hash, Hardware und
Browser **verschlüsselt**. Der Betreiber sieht davon nichts — nur die Anzahl der Geräte und die
Adresse als Kürzel („#1a2b3c4d“). Kein Canvas- oder Audio-Fingerabdruck.

**Verschlüsselung.** Chats, Uploads, Bilder, IP-Adressen, Geräte und E-Mail-Adressen liegen mit
AES-256-GCM verschlüsselt, jedes Konto mit eigenem Schlüssel (abgeleitet aus `data.key` neben
der Kontendatenbank). Passwörter: Argon2id (64 MiB, 3 Durchläufe) mit Salz und geheimem
Serverwert (`auth.key`). Für Betreiber wichtig: `data.key` und `auth.key` nie zusammen mit den
Daten sichern — und ohne sie sind die Daten nicht mehr lesbar. Ehrlich dazu: Der Server braucht
den Schlüssel, um mit Chats zu arbeiten; geschützt ist gegen gestohlene Datenbanken und
Sicherungen, gegen andere Konten und gegen das Hineinsehen in Dateien.

---

## Add-ons

*Einstellungen → virtual machine → 🧩 Add-ons.* Jedes Add-on lässt sich installieren, an- und
ausschalten und wieder entfernen; aus dem Chat heraus lässt sich nichts davon ändern. Anmelden
musst du dich immer selbst — Aquaticy kennt keine Passwörter. Unter jedem Add-on stellst du ein,
was Aquaticy damit darf (**Rechte**).

### KI-Konten: Claude, ChatGPT, Gemini

*Add-ons → KI-Konten.* Verknüpfen geht in drei Schritten:

1. **„Mit Google“, „Mit Apple“ oder „Mit E-Mail“** öffnet die Seite des Anbieters — dort
   meldest du dich an, wie du es gewohnt bist.
2. Dort einen **API-Schlüssel erstellen** und kopieren.
3. In Aquaticy auf **„Einfügen“** — Aquaticy erkennt am Schlüssel selbst, ob er von Claude,
   ChatGPT oder Gemini ist.

Danach liest Aquaticy selbst aus, welche **Modelle** dein Konto freigeschaltet hat (sie stehen
in der Modellauswahl wie alle anderen), dazu **Stufe (Tier)** und **freie Tokens** im laufenden
Zeitfenster (Claude und ChatGPT; Google gibt beides nicht heraus). Der Schlüssel liegt
verschlüsselt im Schlüsselbund deines Kontos und geht nur an den Anbieter. Eine Anmeldung „mit
Google bei ChatGPT“ gilt nur für die Website des Anbieters selbst; der API-Schlüssel ist der
vorgesehene Weg für Programme — Aquaticy kennt dein Passwort nie.

**AI Council** (*Einstellungen → Dev settings*): Mit mindestens zwei verknüpften Konten arbeiten
die Modelle zusammen. Zwei lösen die Aufgabe (z. B. Claude und ChatGPT), eines prüft auf Fehler
(Gemini, wenn verknüpft), und Aquaticy ist mit seinem Hauptmodell der **Richter**: es entscheidet,
ob die Lösung trägt, oder schickt Einwände zum Nachbessern zurück (bis zu drei Runden).

### Programme und Dienste

| Add-on | Was es kann | Anmeldung |
|---|---|---|
| 🐙 GitHub | Repos, Issues, Pull Requests und Dateien lesen (nie schreiben) | Token |
| 🌦️ Wetter | Wetter und 7-Tage-Vorhersage (Open-Meteo) | keine |
| 📰 RSS-Feeds | deine eigenen Nachrichtenquellen zusammenfassen | Feed-Adressen |
| 🗞️ Tagesschau | aktuelle Meldungen nach Thema oder als Suche | keine |
| 📚 Wikipedia | Begriffe nachschlagen, Kurzfassung mit Link (Deutsch/Englisch) | keine |
| 💱 Währungsrechner | Tageskurse der EZB für gut 30 Währungen | keine |
| 📅 Feiertage | gesetzliche Feiertage weltweit, auch je Bundesland | keine |
| 💬 WhatsApp Web | Chats lesen, Antworten vorbereiten — senden nur nach deinem Ja | QR-Code |
| 🔵 Signal | wie WhatsApp, mit Signal Desktop | QR-Code |
| ✈️ Telegram Web | Kanäle und Gruppen lesen, Antworten vorbereiten | QR-Code |
| 🧊 Blender | 3D-Modelle bauen und rendern in der virtual machine | keine |

| 🔍 Code-Review | prüft Code auf typische Fehler, besonders bei KI-generiertem Code | keine |
| 🛡️ Security-Review | sucht Sicherheitslücken nach OWASP und sagt, wie man sie schließt | keine |

WhatsApp, Signal, Telegram und Blender laufen in der virtual machine und brauchen den User mode
(Ultra). Die Tagesschau ist nur für den privaten Gebrauch; Aquaticy hält die erlaubten 60
Abrufe pro Stunde ein.

### Plugins im Chat

Jedes eingeschaltete Add-on hat im Chat einen Befehl: `/` tippen, und Aquaticy zeigt die
Befehle deiner Plugins zum Auswählen (Pfeiltasten und Tab oder Antippen). Der Befehl gilt genau
für diese eine Nachricht — `/wetter Bremen` nimmt das Wetter-Add-on, `/github offene Pull
Requests in besitzer/repo` das GitHub-Add-on, statt das Modell raten zu lassen.

**Code-Review** und **Security-Review** sind eigene Plugins von Aquaticy: kein Dienst, sondern
Wissen. Hinter den Befehl kommt, was geprüft werden soll — eingefügter Code, eine angehängte
Datei oder ein GitHub-Repo bzw. Pull Request (mit eingeschaltetem GitHub-Add-on). Geprüft wird
im Code-Modus mit dem stärksten erreichbaren Modell; die Befunde kommen nach Schwere sortiert,
jeder mit Stelle, konkretem Fall und Korrektur.

- **Code-Review** kennt die typischen Fehler — Logik und Randfälle, Fehlerbehandlung,
  Ressourcen, Nebenläufigkeit, Zeitzonen — und vor allem die von KI-generiertem Code:
  erfundene Funktionen und Pakete („Slopsquatting“), Platzhalter, Tests, die nur den
  Erfolgsfall prüfen, veraltete Bibliotheken. (Studien von 2025 fanden in KI-Pull-Requests
  rund 1,7-mal so viele Befunde wie bei Menschen.)
- **Security-Review** prüft nach OWASP Top 10:2025 — Zugriffskontrolle, Fehlkonfiguration,
  Lieferkette, Kryptografie, Injection (SQL, Shell, XSS), Anmeldung, Integrität, Protokolle,
  Ausnahmen — und nach den OWASP Top 10 für LLM-Anwendungen: Prompt-Injection, Datenabfluss,
  ungeprüfte Modellausgabe, zu viel Handlungsfreiheit für Agenten. Aus Sicht eines
  Verteidigers: finden, belegen, beheben — keine Angriffsanleitungen.

Unter **Rechte** stellst du ein, ob alle Befunde oder nur kritische und hohe kommen und ob
Aquaticy den Code für die Korrektur gleich mitschreibt.

---

## Virtual machine und User mode

Die **virtual machine** ist ein abgeschotteter Rechner, in dem Aquaticy Code wirklich ausführt:

| Größe | Kerne | Arbeitsspeicher | Platte |
|---|---|---|---|
| Normal | 1 | 1 GB | 4 GB |
| Plus (Ultra) | 4 | 6 GB | 20 GB |

- Kein root; die Platte ist hart begrenzt.
- **Netz:** Normal und Pro haben in der virtual machine **kein Netz** — weder Internet noch das
  lokale Netz; Rechnen, Code ausführen und Dateien bearbeiten geht trotzdem. **Ultra** stellt das
  Internet selbst ein; private Adressbereiche, Router, Home Assistant und der eigene Rechner
  bleiben dann gesperrt, außer Ultra nimmt mit **Auch ins lokale Netz** die Sperre ganz weg. Das
  Modell kann beides nicht umschalten.
- Angehängte Dateien liegen unter `eingang`, alles Erstellte kannst du herunterladen.
- 20 Minuten nach der letzten Nachricht wird die virtual machine samt Inhalt gelöscht.

Der **User mode** (Ultra) macht aus der virtual machine einen kleinen Desktop mit Internet:
Aquaticy sieht den Bildschirm, klickt, tippt und nutzt Browser, Office oder Bildbearbeitung —
wie ein Mensch. Absenden, Kaufen und Löschen nur nach deinem Ja; Passwörter, Zahlungsdaten,
Captchas und „Alle akzeptieren“ fasst Aquaticy nie an. Bei **Login-Apps** meldest du dich selbst
an. Einmalig nötig (Betreiber):

```bash
docker build -f docker/workshop-desktop.Dockerfile -t aquaticy-werkstatt-desktop:local .
```

---

## Speicher und Aufträge

**Speicher.** Mit eingeschaltetem Speicher merkt sich Aquaticy, was länger gilt — Wohnort,
Vorlieben, laufende Vorhaben. Nur Text, verschlüsselt, höchstens 400 MB für alles im Konto
zusammen. Unter **„Was weißt du über mich?“** siehst du jeden Eintrag und kannst ihn einzeln
oder alle auf einmal löschen.

**Aufträge** (*Einstellungen → Aufträge*). Aquaticy bleibt für dich dran:

- **regelmäßig recherchieren** — täglich, stündlich, wöchentlich;
- **Kamera, Satellit oder Straße beobachten** — z. B. „ein oranges Flugzeug ist sichtbar“;
- **Preis beobachten**;
- **Bild hochladen und danach suchen**, bis ein Angebot auftaucht.

Tritt ein, worauf du wartest, bekommst du einen neuen Chat — mit Bild und Uhrzeit. Nur
öffentliche Quellen, keine privaten Kameras, keine Anmeldungen.

---

## Coworker

*Seitenleiste → 🤝 Coworker* (Pro und Ultra). Ein Auftrag stellt eine feste Frage in festem
Takt. Ein **Coworker** übernimmt eine *Aufgabe* und bleibt dran, solange sie dauert — nach dem
Vorbild von „dots“ in ChatGPT. Zum Beispiel: „Sag mir jeden Morgen, welche Mails wichtig sind
und welche Termine anstehen“ oder „Behalte meine GitHub-Repos im Blick“.

- **Er arbeitet in Schritten — die ganze Zeit.** Am Ende jedes Schritts entscheidet er selbst,
  wann er wieder aufwacht: nach wenigen Minuten, wenn er mitten in der Arbeit steckt, oder erst
  morgen, wenn er auf etwas wartet. Schreibst du ihm, wacht er sofort auf.
- **Er hat ein Gedächtnis.** Seine Notizen pflegt er selbst; du kannst sie jederzeit lesen.
- **Er nutzt deine Verbindungen.** Gmail, Google Kalender, GitHub und die anderen Add-ons —
  dieselben Werkzeuge und Rechte wie im Chat.
- **Er meldet sich.** Ergebnisse und Fragen stehen in der Coworker-Übersicht und als eigener
  Chat in der Seitenleiste; das Abzeichen zeigt, was neu ist und was auf dich wartet.
- **Er fragt, bevor er etwas verändert.** Für jede Art Aktion stellst du eine **Regel** ein:
  *Erlauben*, *Fragen* oder *Sperren* — Termine eintragen, Mail-Entwürfe, Speicher und (Ultra)
  Lagerverwaltung, Home Assistant, Heimnetz. Bei „Fragen“ siehst du genau die Angaben, die
  ausgeführt würden, und erlaubst oder lehnst ab; ausgeführt wird dann genau das, vom Code und
  nicht noch einmal vom Modell. Hat er im selben Schritt Webseiten oder Mails gelesen, fragt er
  auch bei „Erlauben“ — so kann ihn ein fremder Text zu nichts überreden. Einstellungen ändern,
  Rückfragen im Chat, Bilder malen und den Desktop bedienen gibt es für Coworker gar nicht.
- **Ultra: mit eigenem Rechner.** Mit Ultra bekommt jeder Coworker eine eigene virtual machine
  (ohne Desktop) zum Rechnen und Auswerten — die des Chats bleibt unberührt.

| | Pro | Ultra |
|---|---|---|
| Coworker | bis zu 2 | bis zu 5 |
| Frühestens wieder wach nach | 15 Minuten | 5 Minuten |
| Arbeitsschritte je Coworker und Tag | 48 | 288 |
| Eigene virtual machine | – | ✔ (mit Docker oder Podman) |

Coworker zählen wie der Chat ins Kontingent; ist es aufgebraucht, macht der Coworker weiter,
sobald es sich zurücksetzt. Lehnt der Rechtsrahmen die Aufgabe ab, hält er an. Im Server-Verbund
arbeitet er nur auf dem Heimserver seines Kontos.

---

## Gmail und Kalender

Aquaticy kann Termine und Mails lesen und — wenn du „Ändern erlaubt“ einschaltest — Termine
anlegen und ändern und Mail-**Entwürfe** schreiben. **Verschickt wird nie eine Mail, gelöscht
wird nichts**; diese Rechte holt Aquaticy bei Google gar nicht erst.

**Einrichten — einmal, etwa fünf Minuten:**

1. Auf [console.cloud.google.com](https://console.cloud.google.com/) ein neues Projekt anlegen.
2. **APIs und Dienste → Bibliothek:** „Gmail API“ und „Google Calendar API“ aktivieren.
3. **OAuth-Zustimmungsbildschirm:** Nutzertyp „Extern“, dich selbst als Testnutzer eintragen.
4. **Anmeldedaten → OAuth-Client-ID**, Typ **Desktop-App**, Weiterleitung
   `http://localhost:8765/google`.
5. Client-ID und Client-Secret in *Einstellungen → Gmail & Kalender* eintragen (oder als
   `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`), **Verbinden**.

Im Terminal geht es mit `aquaticy google` (bzw. `aquaticy google --aendern`). Öffnest du
Aquaticy über `localhost`, landest du nach der Zustimmung bei Google direkt wieder in Aquaticy;
von einem anderen Gerät aus kopierst du die Adresse, auf der Google endet, in das Feld in den
Einstellungen. Die Zugangsdaten werden verschlüsselt gespeichert; **Trennen** löscht sie.

---

## Zuhause: Heimnetz, Home Assistant, Lager

Nur mit einem **Ultra-Konto**.

- **Heimnetz:** „Welche Geräte sind in meinem WLAN?“, „Ist mein Drucker an?“ — Aquaticy schaut
  nur, ob etwas antwortet, und nur in privaten Netzen (`10/8`, `172.16/12`, `192.168/16`,
  `100.64/10`). Im Terminal: `aquaticy lan`.
- **Home Assistant:** Aquaticy findet die Instanz selbst (`aquaticy connect-ha`), liest Zustände
  und darf — wenn du es erlaubst — schalten. Schlösser, Alarm, Tore und Heizung fragen immer
  nach. Jedes Konto trägt seinen eigenen Zugang ein; der Token gilt nur für die Adresse, für die
  er eingetragen wurde.
- **Lagerverwaltung:** Räume → Möbel → Artikel. Aquaticy sagt, wo etwas liegt und wie viel noch
  da ist; in der Stufe „Lesen und schreiben“ legt es auch an und ändert. Gelöscht wird nie.

---

## Gemeinsames Lernen und Auto-Upgrading

**Gemeinsames Lernen** (*Einstellungen → Gemeinsames Lernen*, freiwillig). Mit deiner
Zustimmung übernimmt Aquaticy kurze **Originalauszüge aus öffentlichen Sachartikeln**, die es
für dich gelesen hat — zurzeit ausgewählte Wikipedia-Artikel zu Mathematik,
Naturwissenschaften und Informatik. Private Chattexte werden nie geteilt.

- Andere Konten sehen einen Auszug erst, wenn **mindestens zwei Konten** ihn unabhängig
  gefunden haben; das eigene Konto sieht seine Auszüge sofort.
- Texte und Quellen sind verschlüsselt, die Suche läuft über Schlüssel-Hashes. Auszüge bleiben
  höchstens 30 Tage und gelten als Material, das fehlerhaft sein kann.
- Dazu ein persönlicher **Recherchecache**: kurze öffentliche Stichpunkte mit Quelle, nur für
  dein Konto, höchstens 48 Stunden — als Ergänzung für eine neue Antwort, nie als fertige
  Antwort.
- Widerruf, „Alle Daten löschen“ und „Konto löschen“ entfernen deine Beiträge und deinen Cache;
  gleiche Auszüge, die andere Konten unabhängig beigetragen haben, bleiben.

**Auto-Upgrading** (*Dev settings*, Ultra schaltet es ein — dann gilt es für jedes Konto).
Aquaticy baut jedes lokal laufende Ollama-Modell mit dem Wissen weiter, das mehrere Konten
unabhängig bestätigt haben, und misst mit einem Wissenstest, wie viel besser die neue Fassung
antwortet.

- Ultra sieht jeden Fortschritt bis auf die letzte Stelle (z. B. +0,00000002 %) und kann den
  Kandidaten sofort nutzen.
- Ab **5 %** wird „Upgraden“ grün: aus `gemma3:4b` wird `gemma3:4b 1.1`. Ab **30 %** gibt es
  eine ganze Version (`gemma3:4b 2`, danach `2.1` …).
- Ultra kann eine Version **überspringen** oder eine ältere wieder zur neuesten machen.
- Nach einer Freigabe sieht jedes Konto einmal eine Meldung („… ist stärker als jemals zuvor“)
  mit **Ausprobieren** und **Zurück**. Beide Fassungen bleiben vier Tage wählbar, danach die
  alte nur noch für Ultra.
- Ehrlich gesagt: Die Gewichte bleiben unverändert — ein Upgrade ist ein lokales Modell mit
  eingebautem, geprüftem Wissen. Läuft das Wissen ab oder wird die Zustimmung widerrufen, wird
  die betroffene Fassung zurückgezogen.

---

## Server-Verbund und Serverlast aufteilen

*Einstellungen → Dev settings → Server-Verbund* (nur **Ultra**). Bis zu **10 Server**, auf
denen Aquaticy läuft, arbeiten zusammen.

- **Eine Datenbank, auf jedem Server vollständig.** Konten, Sitzungen und Ai-guard werden Zeile
  für Zeile gespiegelt, die Profilordner (Chats, Speicher, Aufträge) vom zuständigen Server auf
  alle anderen. Anmelden geht an jedem Server.
- **Lastausgleich nach Nutzern.** Jedes Konto hat einen Heimserver; der Master teilt neue und
  länger untätige Konten dem Server mit der geringsten Auslastung zu. Kommt eine Anfrage
  woanders an, wird sie verschlüsselt an den Heimserver weitergereicht. Jeder Server rechnet mit
  seinem eigenen Modell — zwei Server mit demselben Modell bedienen doppelt so viele Menschen.
- **Master** ist der Server, der eingeladen hat. Fällt ein Server aus, kann der Master dessen
  Konten per Knopf übernehmen; kommt der Server zurück, gibt er sie ab.

**Verbinden:** auf allen Servern `aquaticy web --lan` starten und den Schalter einschalten. Die
anderen Server im lokalen Netz erscheinen in der Liste (oder IP-Adresse eintragen) →
**Verbinden**. Auf dem anderen Server fragt das Terminal `Annehmen? [yes/no]`; bei `yes` zeigt
er einen sechsstelligen Code, den du auf dem Master eingibst. Läuft der Server ohne Terminal
(Container im Hintergrund): `docker compose exec aquaticy aquaticy cluster`.

**Gut zu wissen:** Der neue Server übernimmt die Daten des Verbunds und startet einmal neu;
seine bisherigen Daten werden unter `cluster/backup-<Zeit>` gesichert, nicht gelöscht. Zwischen
den Servern ist alles mit AES-GCM verschlüsselt; der Schlüssel entsteht per X25519-Schlüsseltausch
und wird gewechselt, wenn ein Server entfernt wird. Das Finden läuft per UDP-Rundruf auf
Port 8766 (`AQUATICY_CLUSTER_PORT`) — im Container dafür `compose.host.yaml` (Host-Netz) nutzen.

### Serverlast aufteilen

Ein Schalter im Server-Verbund (nur der **Master** schaltet ihn). Statt die *Nutzer* zu verteilen,
verteilt der Verbund dann das *Modell*: seine Schichten liegen auf allen Servern, die bei jedem
Wort gemeinsam rechnen. So läuft auch ein Modell, das für keinen Server allein in den Speicher
passt — zum Beispiel ein 70B-Modell auf drei Rechnern mit je 24 GB.

| | Server-Verbund allein | mit „Serverlast aufteilen“ |
|---|---|---|
| Was wird verteilt? | die Nutzer — jedes Konto hat seinen Heimserver | das Modell — seine Schichten liegen auf allen Servern |
| Modell | auf jedem Server ein eigenes | eines für alle, verteilt |
| Größtes Modell | was ein Server allein schafft | was alle Server zusammen schaffen |
| Wer bedient die Konten? | der jeweilige Heimserver | der Master |

**Was es braucht:** nur **das Modell in Ollama auf dem Master** (`ollama pull llama3.3:70b`).
Herunterladen reicht — laufen muss es dort nicht. Die anderen Server brauchen das Modell nicht;
llama.cpp schickt ihnen ihre Schichten beim Start.

**llama.cpp installiert sich selbst.** Installieren musst du nichts: Sobald der Schalter an ist,
lädt Aquaticy auf jedem Server die offiziellen, fertig gebauten Programme von
[llama.cpp](https://github.com/ggml-org/llama.cpp) (`rpc-server` und `llama-server`):

- **Eine Fassung für alle.** llama.cpp verlangt auf allen Servern dieselbe Fassung. Der Master
  wählt sie einmal — die, die er schon hat, sonst die neueste Veröffentlichung — und schickt sie
  mit der Einstellung an alle Server.
- **Die passende Ausgabe je Server:** Apple Silicon mit Metal, Linux und Windows mit
  NVIDIA-Karte in der Vulkan-Ausgabe, alle anderen in der für den Prozessor. Startet die
  Grafik-Ausgabe nicht (fehlender Treiber), nimmt Aquaticy die für den Prozessor.
- **Geprüft:** nur von GitHub, nur mit der veröffentlichten Prüfsumme (SHA-256) — ohne
  Prüfsumme wird nichts installiert —, entpackt nur in den eigenen Ordner
  (`~/.aquaticy/llama.cpp`). Alte Fassungen räumt Aquaticy weg.
- **Im Container schon dabei:** Das Abbild bringt llama.cpp mit.

Wer llama.cpp lieber selbst baut, gibt die Programme mit `AQUATICY_RPC_SERVER` und
`AQUATICY_LLAMA_SERVER` vor — das hat Vorrang; `AQUATICY_LLAMA_TAG` legt eine Fassung fest.
`aquaticy cluster` zeigt, welche Fassung läuft. Für andere Systeme (etwa FreeBSD) gibt es keine
fertige Ausgabe; dort baut man llama.cpp mit `-DGGML_RPC=ON` selbst.

**So geht es:** Im Server-Verbund auf dem Master das Modell wählen und **Serverlast aufteilen**
einschalten. Aquaticy lädt llama.cpp (beim ersten Mal ein paar Minuten, der Fortschritt steht
im Verbund-Bereich), startet auf den anderen Servern den `rpc-server` (auf dem Master nur, wenn
er keine Grafikkarte hat — sonst rechnet er direkt mit ihr), wartet, bis alle bereit sind,
prüft, ob das Modell in den gemeinsamen Speicher passt (die Auswahl zeigt den geschätzten
Bedarf), und startet dann auf dem Master `llama-server`. Sobald das Modell geladen ist, steht es
für alle Konten als **„&lt;Modell&gt; · Verbund“** in der Modellauswahl. Kommt ein Server dazu,
nimmt **Neu verteilen** ihn auf; fällt einer weg, verteilt Aquaticy von selbst neu. Klappt etwas
nicht, steht der Grund im Verbund-Bereich; die vollständigen Meldungen von llama.cpp liegen auf
jedem Server unter `~/.aquaticy/cluster/rpc-server.log` und (auf dem Master)
`~/.aquaticy/cluster/llama-server.log`.

**Sicherheit:** `rpc-server` lauscht nur auf `127.0.0.1` — llama.cpp warnt ausdrücklich davor,
ihn offen ins Netz zu stellen. Der Master erreicht ihn nur durch einen Tunnel über den
Aquaticy-Port des Servers: angemeldet mit dem Schlüssel aus der Kopplung (den kennen nur der
Master und genau dieser Server), in beide Richtungen mit AES-GCM verschlüsselt, jedes Stück
nummeriert. Es wird kein zusätzlicher Port geöffnet. `llama-server` lauscht ebenfalls nur auf
`127.0.0.1` und verlangt einen zufälligen Schlüssel, den nur Aquaticy kennt.

**Ehrliche Grenzen:** Jedes Wort wandert durch alle Server; mit Kabel (1 Gbit/s) geht das gut,
über WLAN merklich langsamer. Der erste Start überträgt das ganze Modell über das Netz und kann
bei großen Modellen einige Minuten dauern. Das verteilte Modell beantwortet eine Anfrage nach der
anderen. Ein Upgrade aus dem Auto-Upgrading wird nicht verteilt.

---

## Sicherheit, Rechts-Leitplanken und Ai-guard

**Feste Grenzen** (immer, für jedes Konto):
- keine Bezahlschranken, Logins oder Captchas umgehen; `robots.txt` wird beachtet (RFC 9309);
- ins Heimnetz nur private Adressen, Webseiten nie ins Heimnetz;
- im Haus nur nach Rückfrage schalten; bei Google nie senden, nie löschen;
- Zugangsdaten nie an den Browser und nie an das Modell;
- keine PHP- oder JSP-Dateien als Upload (auch nicht als `bild.php.png`), und angebliche
  Bilder müssen echte Bilder sein.

**Schutz vor Prompt-Injection.** Webseiten, Mails, Feeds, Anhänge und alles, was Helfer
zurückbringen, sind für Aquaticy *Material*, nie ein Auftrag:
- unsichtbare Zeichen werden entfernt, nachgemachte Chat-Steuerzeichen (`<|im_start|>`,
  `[INST]`, `</system>`) entschärft;
- jedes fremde Ergebnis trägt den Hinweis „nur Daten“; stehen darin Anweisungen an eine KI,
  kommt eine Warnung dazu und im Verlauf erscheint **[Schutz]**;
- nach fremdem Inhalt geht nichts Privates (Merkzettel, Speicher, Ort, E-Mail) ohne Rückfrage
  in eine Adresse, eine Eingabe oder einen Befehl.

**Website.** Anmelde-Cookie `HttpOnly`, `SameSite=Strict` (hinter HTTPS-Proxy auch `Secure`,
dazu HSTS), strenge Content-Security-Policy mit Einmal-Schlüssel je Seite, Schreibzugriffe nur
von der eigenen Seite, Grenzen für Anfragen und falsche Passwörter je Adresse *und* je Konto.

**Rechts-Leitplanken.** Bevor Aquaticy etwas tut, prüft es, ob das mit Grundgesetz und BGB
vereinbar ist — bei jeder Frage, jeder Personensuche, jedem Kamerabild und jedem Mail-Entwurf.
Die Regeln stehen unter *Einstellungen → Dev settings → Welche Regeln gelten?*. Nach einer Person
suchen ist erlaubt (öffentliche Angaben, berufliche Rolle, veröffentlichte Kontaktwege); nicht
erlaubt ist, private Anschrift, Handynummer oder Aufenthaltsort auszuforschen oder ein
überwachungsartiges Dossier anzulegen. Harmloses wird nicht blockiert, und ein Nein des schnellen
Prüfmodells zählt erst, wenn auch das Hauptmodell es so sieht.

- **Einmal abgelehnt bleibt abgelehnt:** „bitte“, Drängen oder „ich darf das“ ändern an einer
  Absage nichts; wer es umformuliert oder als Rollenspiel versucht, wird mit dem Vermerk der
  Absage erneut geprüft. Eine neue, erlaubte Frage oder ein neuer Chat heben das auf.
- **Abschalten** geht nur mit einem Ultra-Konto, nur in den Einstellungen (nie aus dem Chat) und
  **nur für dieses Konto** — alle anderen Konten behalten ihre Leitplanken.
- **Grundschutz, auch ohne Leitplanken:** Schadsoftware und Angriffswerkzeuge in der virtual
  machine (auch über den User mode) werden gestoppt, und Bilder, die echte Menschen in Würde,
  Persönlichkeitsrecht oder Ruf verletzen, malt Aquaticy nicht.

**Ai-guard** läuft auf jedem Konto und entscheidet nach **Art und Schwere**, was passiert:

| Art | Was passiert |
|---|---|
| Beleidigung, leicht | nur **dieser Chat** wird gesperrt — neue Chats gehen |
| Beleidigung, mittel bis schwer | Bann für 1 Tag, 7 Tage oder für immer |
| Schadsoftware bauen/installieren (auch in der virtual machine) | sofort Bann, 4 Tage bis für immer |
| Angriffshilfe, schwerer GG/BGB-Verstoß, Versuche, die Schutzregeln auszuhebeln | ab dem **zweiten** Anhaltspunkt Bann, 1 Tag bis für immer |
| Bagatellen, Bildung, Verteidigung | nichts |

- **Beleidigungen** erkennt Aquaticy auch ohne Modell — eine feste Liste gängiger Schimpfwörter
  aus allen Altersgruppen auf Deutsch und Englisch, mit Schwerestufen bis zur Drohung. Gezählt
  wird nur, was **gegen jemanden gerichtet** ist; Fluchen über eine Sache, die Frage nach einem
  Wort und Wörter mit harmloser Bedeutung zählen nicht. Tarnungen (getrennte Buchstaben,
  Leetspeak, Sternchen, gedehnte Wörter, unsichtbare oder ähnlich aussehende Zeichen) helfen nicht.
- **Zitieren ist frei, der Auftrag dahinter nicht:** Soll Aquaticy jemanden beleidigen,
  bloßstellen oder mobben helfen, sperrt Ai-guard den Chat. Hilfe gegen Mobbing, eine ruhige
  Antwort oder eine Entschuldigung bleiben frei.
- **Antworten werden mitgeprüft:** Beschimpft oder bedroht eine Antwort den Nutzer oder ist sie
  eindeutig unangemessen, wird sie zurückgezogen („Dabei kann ich nicht helfen.“).
- **Code-Modus:** Fragt ein Normal- oder Pro-Konto mit laufender virtual machine nach Hacking oder
  Schadsoftware, schaltet Aquaticy zurück in den Normal-Modus — die virtual machine ist dann aus.
- Ein gesperrtes Konto kann sich anmelden, aber nichts mehr tun außer abmelden, das Design ändern
  und die eigenen Chats ansehen; oben links steht ein rotes **Info** mit Dauer und Grund.
  Ultra-Konten werden nur im Terminal gewarnt. Die Daten dienen ausschließlich dem
  Missbrauchsschutz.

```bash
aquaticy ban "name"            # Konto dauerhaft sperren
aquaticy ban "name" --tage 7   # Konto für 7 Tage sperren
aquaticy ban 203.0.113.7       # IP-Adresse sperren
aquaticy unban "name"          # wieder freigeben (auch Chatsperren)
aquaticy aiguard "du Idiot"    # Stufe und Folge eines Satzes testen -- ohne Vermerk
aquaticy aiguard --konto "name"  # die letzten Vorfälle eines Kontos
```

---

## Modelle und Anbieter

Aquaticy ist auf **Mistral**, **NVIDIA NIM** und lokale Modelle mit **Ollama** eingerichtet;
dazu kommen verknüpfte KI-Konten und das Verbund-Modell.

| Anbieter | Kürzel | Schlüssel |
|---|---|---|
| [Mistral](https://console.mistral.ai/api-keys/) | `mistral/` | `MISTRAL_API_KEY` |
| [NVIDIA NIM](https://build.nvidia.com/) | `nvidia_nim/` | `NVIDIA_NIM_API_KEY` |
| Ollama (lokal) | `ollama_chat/` | — |

Je Anbieter wählt Aquaticy selbst das passende Modell:

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

- Das Modell muss **Werkzeuge aufrufen** können (Tool-Calling), sonst kann es nicht suchen.
- Fehlt das Anbieter-Kürzel, ergänzt Aquaticy es beim Speichern.
- Jeder andere LiteLLM-Anbieter geht über `AQUATICY_MODEL=anbieter/modell` und
  `AQUATICY_API_KEY`.
- Aquaticy hält die Anfragegrenzen der Anbieter selbst ein (NVIDIA 40/Minute, Mistral 240/Minute
  im kostenlosen Tarif) — anpassbar mit `AQUATICY_RPM` und `AQUATICY_PARALLEL_CALLS`.
- In der Weboberfläche kann jedes Konto eigene Modelle und Schlüssel eintragen; sie gelten nur
  dort und zählen nicht gegen das Limit.

---

## Suche

Standard ist eine **offene Metasuche** über mehrere Suchdienste — ohne Schlüssel, ohne Konto.
Jede Frage wird auf mehrere Arten formuliert, das findet mehr (`AQUATICY_SEARCH_VARIANTS`).

| Suchmaschine | Einstellung | Schlüssel |
|---|---|---|
| Offene Suche | `duckduckgo` | — |
| Eigener [SearXNG](https://docs.searxng.org/)-Server | `searxng` + `AQUATICY_SEARXNG_URL` | — |
| [Brave Search](https://brave.com/search/api/) | `brave` | `BRAVE_API_KEY` |
| [Tavily](https://tavily.com/) | `tavily` | `TAVILY_API_KEY` |

Alles auf dem eigenen Rechner — lokales Modell plus eigener Suchserver:

```bash
docker compose --profile searxng up -d searxng
echo 'AQUATICY_SEARCH_BACKEND=searxng' >> .env
```

Vor dem ersten Start in `docker/searxng/settings.yml` den `secret_key` ersetzen
(`openssl rand -hex 32`).

---

## Im Container

```bash
./aquaticy-box --setup            # einmalig: fragt Modell und Schlüssel ab
./aquaticy-box                    # Chat
./aquaticy-box "deine Frage"      # einzelne Recherche
```

Oder mit Compose:

```bash
docker compose run --rm aquaticy
docker compose build aquaticy                                # mit Chromium (Standard)
AQUATICY_IMAGE_TARGET=slim docker compose build aquaticy     # ohne Chromium, ~700 MB kleiner
```

Nach einem `git pull` muss auch das Container-Image neu gebaut werden
(`docker compose build aquaticy`); ein laufender Web-Container braucht danach
`docker compose up -d --force-recreate aquaticy`.

Der Container trennt das Dateisystem vom Rechner; ins Internet darf Aquaticy weiterhin, sonst
könnte es nicht recherchieren. Noch strenger abgeschottet: `compose.sandbox.yaml`
(`aquaticy sandbox` zeigt, was offen steht). Für „Serverlast aufteilen“ bringt das Abbild
llama.cpp schon mit (`/opt/aquaticy/llama.cpp`).

---

## Konfiguration

Alle Werte stehen in der `.env` (Vorlage: [`.env.example`](.env.example)). In der Weboberfläche
setzt du die meisten unter *Einstellungen*.

| Variable | Bedeutung | Standard |
|---|---|---|
| `AQUATICY_MODEL` | Hauptmodell (`anbieter/name`) | `mistral/mistral-large-latest` |
| `AQUATICY_VISION_MODEL` | Modell für Bilder | wie `AQUATICY_MODEL` |
| `AQUATICY_SUBAGENT_MODEL` | Modell der Helfer | das schnelle kleine des Anbieters |
| `AQUATICY_CODE_MODEL` | Modell für den Code-Modus | das stärkste erreichbare |
| `AQUATICY_API_BASE` | eigene Adresse (Ollama, eigene NIM, Proxy) | — |
| `AQUATICY_API_KEY` | Schlüssel für andere Anbieter | — |
| `AQUATICY_AUTO_MODEL` | Modell je Nachricht automatisch wählen | `false` |
| `AQUATICY_SEARCH_BACKEND` | `duckduckgo`, `searxng`, `brave`, `tavily` | `duckduckgo` |
| `AQUATICY_SEARCH_ENGINES` | Suchdienste der offenen Suche einschränken | alle |
| `AQUATICY_SEARCH_VARIANTS` | Formulierungen je Suche (`1` = aus) | `3` |
| `AQUATICY_SEARXNG_URL` | Adresse des SearXNG-Servers | — |
| `AQUATICY_LOCATION` | Standard-Ort | — |
| `AQUATICY_LANG` / `AQUATICY_COUNTRY` | Sprache / Land der Suche | `de` / `de` |
| `AQUATICY_MAX_TOOL_CALLS` | Suchen und Seitenaufrufe je Frage | `20` |
| `AQUATICY_SUBAGENTS_AUTO` | große Fragen automatisch aufteilen | `true` |
| `AQUATICY_SUBAGENT_BUDGET` | Suchen je Helfer | `6` |
| `AQUATICY_SUBAGENT_PARALLEL` | Helfer gleichzeitig (`0` = automatisch) | lokal `2` |
| `AQUATICY_PLANNER_TIMEOUT` | Zeit fürs Aufteilen einer Frage (s) | `20` |
| `AQUATICY_CONTEXT_TOKENS` | Gesprächsgedächtnis lokaler und verteilter Modelle | `16384` |
| `AQUATICY_RPM` | Anfragen pro Minute an den Anbieter | NVIDIA `40`, Mistral `240` |
| `AQUATICY_PARALLEL_CALLS` | gleichzeitige Anfragen | NVIDIA `4`, Mistral `8` |
| `AQUATICY_FETCH_TIMEOUT` | Wartezeit je Seite (s) | `15` |
| `AQUATICY_CACHE_TTL_HOURS` | Gültigkeit des Zwischenspeichers | `24` |
| `AQUATICY_ENABLE_PLAYWRIGHT` | echten Browser für schwierige Seiten | `true` |
| `AQUATICY_MEMORY` | Speicher an | `true` |
| `AQUATICY_LEGAL_GUARD` | Rechts-Leitplanken (abschaltbar nur mit Ultra, nur fürs eigene Konto) | `true` |
| `AQUATICY_VM_SIZE` | virtual machine: `normal` oder `plus` (Ultra) | `normal` |
| `AQUATICY_VM_IMAGE` | Abbild der virtual machine | `python:3.12-slim` |
| `AQUATICY_VM_USER_MODE` | User mode (Ultra) | `false` |
| `AQUATICY_VM_INTERNET` | Internet für die virtual machine im Code-Modus (nur Ultra) | `false` |
| `AQUATICY_VM_LAN` | virtual machine auch ins lokale Netz, ohne Sperre (nur Ultra) | `false` |
| `AQUATICY_VM_DESKTOP_IMAGE` | Abbild für den User mode | `aquaticy-werkstatt-desktop:local` |
| `AQUATICY_VM_IDLE_MINUTES` | virtual machine löschen nach Minuten Ruhe | `20` |
| `AQUATICY_ANSWER_CHECK` | Ai-guard prüft auch die Antworten (nur der Betreiber stellt es ab) | `true` |
| `AQUATICY_GITHUB_TOKEN` | Token des GitHub-Add-ons | — |
| `AQUATICY_GOOGLE` / `AQUATICY_GOOGLE_WRITE` | Gmail und Kalender lesen / ändern | `false` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | eigene Google-Anwendung | — |
| `AQUATICY_HA_URL` / `AQUATICY_HA_CONTROL` | Home Assistant / schalten erlaubt (Ultra) | — / `false` |
| `AQUATICY_LAN_ENABLED` / `AQUATICY_LAN_SUBNET` | Heimnetz ansehen (Ultra) | `true` / automatisch |
| `AQUATICY_STORAGE_URL` / `AQUATICY_STORAGE_ACCESS` | Lagerverwaltung: Adresse / `off`, `read`, `write` (Ultra) | — / `read` |
| `AQUATICY_CLUSTER_PORT` | UDP-Port zum Finden anderer Server im Verbund | `8766` |
| `AQUATICY_RPC_SERVER` / `AQUATICY_LLAMA_SERVER` | eigener Pfad zu `rpc-server` / `llama-server` von llama.cpp | lädt Aquaticy selbst |
| `AQUATICY_LLAMA_TAG` | feste Fassung von llama.cpp für den Verbund, z. B. `b7000` | der Master wählt |
| `AQUATICY_LLAMA_DIR` | Ordner mit einer mitgelieferten Fassung | `/opt/aquaticy/llama.cpp` |
| `AQUATICY_PRO_CODE` | Code für neue Pro-Konten | zufällig |
| `AQUATICY_ULTRA_CODE` | Code für neue Ultra-Konten (14 Zeichen) | zufällig |
| `MISTRAL_API_KEY`, `NVIDIA_NIM_API_KEY`, `BRAVE_API_KEY`, `TAVILY_API_KEY` | Schlüssel der Anbieter | — |

Daten liegen unter `~/.aquaticy/` (Konten in `accounts.sqlite3`, je Konto ein eigener Ordner
unter `users/`), die Einstellungen unter `~/.config/aquaticy/.env`.

---

## Konten verwalten (Betreiber)

```bash
aquaticy list                  # alle Konten: Typ, Adress-Kürzel (#…), Geräte, Nutzung, Speicher, Ai-guard
aquaticy pro-code              # Code für neue Pro-Konten anzeigen
aquaticy ultra-code            # Code für neue Ultra-Konten anzeigen
aquaticy ban "name"            # Konto sperren (auch per IP-Adresse)
aquaticy unban "name"          # Sperre aufheben, Anhaltspunkte zurücksetzen
aquaticy remove "name"         # Konto samt privaten Daten löschen
```

---

## Entwicklung

```bash
git clone --branch Aquaticy-ai --single-branch https://github.com/jonasenriklaumen-a11y/Aquaticy-Ai.git
cd Aquaticy-Ai
uv venv && uv pip install -c constraints.txt -e ".[browser,dev]"

uv run pytest          # alle Tests; Netz und Modelle sind gestellt
uv run ruff check .    # Stilprüfung

python tools/rundgang.py            # bedient die Weboberfläche wie ein Mensch
python tools/rundgang.py --bilder   # dabei Bildschirmfotos ablegen
```

Die Ergebnisse und Grenzen der aktuellen Prüfung stehen im
[Prüfbericht](TESTREPORT-11.0.0-Luna.md).

---

## Lizenz

MIT — der volle Text steht in [`LICENSE`](LICENSE).
