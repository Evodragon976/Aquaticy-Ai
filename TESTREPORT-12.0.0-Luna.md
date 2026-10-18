# Prüfbericht: 12.0.0 Luna

Stand: 2026-10-18. Grundlage: **11.4.1 Luna**, Commit `0a6c850`, Branch `Aquaticy-ai`.

## Was neu ist

### Oberfläche

1. **Normal, Pro und Code stehen in der Seitenleiste**, unter dem Logo mit der Versionsnummer
   und über „Neuer Chat“ und den letzten Chats.
   - Am Handy liegt die Leiste hinter ☰ und geht nach der Wahl wieder zu.
   - Wechselt man die Arbeitsweise in einem Chat mit Inhalt, beginnt wie bisher ein neuer Chat.
2. **Die Eingabezeile:** 📎 Anhängen, gleich danach die Modellauswahl, rechts 🎤 Mikrofon und
   Senden. Das Modellmenü öffnet sich jetzt links am Modell-Knopf.
3. **Spracheingabe:** Tippen aufs Mikrofon, sprechen, und sobald man aufhört, geht das Gesagte
   als Frage los. Nochmal tippen beendet das Zuhören, Esc bricht ab.
   - Was schon im Feld steht, bleibt davor stehen und geht mit.
   - Während Aquaticy antwortet, ist das Mikrofon aus.
   - Beim Chatwechsel und wenn die Seite in den Hintergrund geht, wird abgebrochen.
   - Vor der ersten Nutzung erklärt ein Fenster, wer die Aufnahme bekommt (siehe
     „Datenschutz“). Die Bestätigung merkt sich das Konto.
4. **Auto-Scroll** unter Design: An (wie bisher) läuft der Chat beim Schreiben mit. Aus bleibt
   er stehen, wo man liest; nur die eigene Frage und der Anfang der Antwort kommen noch ins
   Bild. Gespeichert am Konto, „Standard“ stellt es wieder an.

### Modelle und Schlüssel

5. **Nur noch Mistral und NVIDIA NIM in der Cloud.**
   - Alles andere muss auf dem Server laufen: Ollama, LM Studio, vLLM, llama.cpp/llamafile oder
     ein Server mit OpenAI-Schnittstelle unter einer lokalen Adresse.
   - Claude, ChatGPT und Gemini sind weg, ebenso Umwege wie Vertex, Azure, Bedrock, OpenRouter
     und andere Anbieter wie Groq.
   - Geprüft wird an drei Stellen: beim Speichern der Einstellungen, beim Wechseln (`/model`)
     und vor **jedem** Modellaufruf (`aquaticy/llmcall.py`; die zwei Aufrufe, die bisher daran
     vorbeiliefen, gehen jetzt hindurch).
   - Die Modellauswahl zeigt nichts anderes mehr.
   - Ein Tippfehler im Kürzel bekommt weiter seinen Vorschlag („Meintest du: nvidia_nim/…“).
6. **„Lokal“ heißt:** localhost, Heimnetz (private Adressen, auch Tailscale), Namen auf `.local`,
   `.lan`, `.internal`, `.home.arpa`, oder ein Name, dessen Adressen alle nicht öffentlich sind
   (fünf Minuten gemerkt). Ollama-Modelle mit `-cloud`, die Ollama an ollama.com weiterreicht,
   zählen nicht als lokal.
7. **NVIDIA NIM und Mistral sind Add-ons**, ganz oben in der Liste, NVIDIA NIM zuerst.
   - Erst „Installieren“, dann erscheinen die Anmelde-Knöpfe und das Feld für den Schlüssel.
   - Die Knöpfe öffnen die Anmeldeseite des Anbieters: Mistral mit Google, Apple, Microsoft
     oder E-Mail; NVIDIA mit Google oder E-Mail. Anmelden tut man sich selbst.
   - Gespeichert wird erst, wenn der Anbieter den Schlüssel annimmt. Danach stehen Modelle und,
     wenn der Anbieter sie nennt, freie Tokens in der Karte.
   - Ein NVIDIA-Schlüssel im Mistral-Add-on wird erkannt und abgelehnt.
   - Kein Schalter, kein Chat-Befehl, keine Rechte: Die beiden sind keine Werkzeuge.
     Deinstallieren löscht den Schlüssel.
8. **Es gibt keinen anderen Weg mehr, einen API-Schlüssel einzutragen.**
   - Den Bereich „API-Schlüssel“ in den Einstellungen gibt es nicht mehr, ebenso wenig seine
     Route `/api/keys` und das Sammelfeld oben in den Add-ons.
   - Das Einstellungsformular und der Verbindungstest nehmen keine Schlüssel mehr an.
   - `aquaticy setup` fragt nicht mehr nach dem Schlüssel und verweist auf die Add-ons.
   - Im Schlüsselbund gibt es nur noch die zwei Plätze. Gespeicherte Schlüssel für Claude,
     ChatGPT, Gemini, Brave, Tavily und den allgemeinen Platz werden beim nächsten Öffnen
     gelöscht.
   - Ein Mistral- oder NVIDIA-Schlüssel von vor 12.0.0 bleibt: Sein Add-on gilt dafür als
     installiert.
9. **AI Council** arbeitet jetzt mit NVIDIA NIM und Mistral: einer löst, der andere prüft,
   Aquaticy richtet.

## Was bleibt (bewusst)

- **Schlüssel des Betreibers** in der `.env` (`MISTRAL_API_KEY`, `NVIDIA_NIM_API_KEY`) gelten
  weiter. Ohne Konten schreibt das Add-on selbst dorthin. Mit Konten gilt ein Eintrag dort als
  „gestellt“ für alle; die Karte sagt das dann.
- **Brave und Tavily** gehen nur noch mit einem Schlüssel, den der Betreiber in der `.env`
  hinterlegt. Eintragen lässt sich keiner mehr.
- `AQUATICY_API_KEY` (nur `.env`) bleibt als Zugangsschlüssel für einen lokalen Server (vLLM,
  Proxy), der einen verlangt. Einen Cloud-Anbieter erreicht er nicht mehr.
- **Erwähnungen ohne Verbindung** bleiben: die Antwort auf „Bist du ChatGPT?“, das Vorbild der
  Coworker, Kommentare.

## Datenschutz

- **Spracheingabe:** Die Sprache erkennt der Browser, nicht Aquaticy.
  - Chrome schickt die Aufnahme dafür an Google, Edge an Microsoft, Safari an Apple.
  - Kann der Browser die Sprache auf dem Gerät erkennen (`processLocally`), nutzt Aquaticy das.
  - Aquaticy bekommt nur den erkannten Text, wie eine getippte Frage. Eine Aufnahme erreicht den
    Server nie.
  - Das steht vor der ersten Nutzung im Fenster und in der Datenschutzerklärung.
  - Die Fassung der Rechtstexte (`LEGAL_VERSION`) ist unverändert: Eine neue Fassung hätte die
    Zustimmungen zum gemeinsamen Lernen zurückgesetzt, und um die geht es hier nicht.
- Die Anmeldewege der Anbieter ließen sich aus dem Container nicht live prüfen; sie stammen aus
  deren Anleitungen. Die Knöpfe öffnen ohnehin die Anmeldeseite des Anbieters, wo man selbst
  wählt.

## Sicherheit

- **Mikrofon:** Die Kopfzeile `Permissions-Policy` erlaubt es jetzt der eigenen Seite
  (`microphone=(self)`), nie einer eingebetteten fremden. Kamera und Standort bleiben ganz
  gesperrt. `X-Frame-Options: DENY` und `frame-ancestors 'none'` bleiben.
- **Schlüssel:**
  - Sie gehen nur an `api.mistral.ai` bzw. `integrate.api.nvidia.com` und nie zurück an den
    Browser. Zitiert ein Anbieter den Schlüssel in einer Fehlermeldung, wird er entfernt
    (Test).
  - Prüfungen sind je Konto begrenzt (10 je Minute).
  - Gespeichert wird nur nach Installation des Add-ons und nach Annahme durch den Anbieter.
- **Weniger Angriffsfläche:** Die Routen und Formularfelder für Schlüssel sind weg. Der
  Schlüsselbund hat zwei Plätze statt acht, Altlasten werden gelöscht.
- Keine Sicherheitsregel gelockert. bandit: keine neuen Hinweise.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | erster Volllauf: ein Fehlschlag in einem neuen Test (siehe unten). Danach alle fünf Schritte ohne Beanstandung (Rückgabewert 0): **5208 bestanden, 31 übersprungen, keine Fehlschläge** (5239 Tests, Browser-Rundgang eingeschlossen) |
| Neue Tests (`tests/test_v1200.py`) | 40, alle bestanden |
| KI-Konten und eigene Schlüssel (`test_linked`, `test_own_keys`) | 19 + 27 bestanden |
| Browser-Rundgang | bestanden: Schlüssel über das Add-on Mistral verknüpfen, entfernen, deinstallieren |
| Im Browser (Chromium, Spracherkennung simuliert) | Hinweis → „Verstanden, zuhören“ → Mikrofon rot, „Ich höre zu …“ → „Wie spät ist es in Tokio“ geht von selbst los; `voice_ok` und `autoscroll` am Konto gespeichert |
| Breiten 1340, 820, 390, 360 px | Eingabezeile in einer Reihe (Anhängen, Modell, Mikrofon, Senden), kein seitliches Scrollen; die Leiste zeigt die Arbeitsweise und schließt nach der Wahl |
| Modellmenü | öffnet links am Modell-Knopf |
| bandit, mypy, ruff | ohne Beanstandung |

## Geänderte Tests

Alle wegen der gewünschten Änderungen. Wo ein Test etwas anderes prüfte und nur zufällig ein
jetzt gesperrtes Modell benutzte, steht ein erlaubtes da; die Prüfung selbst ist gleich.

- **Neue Anordnung:** `test_web::test_the_composer_offers_all_three_modes` prüft jetzt die
  Arbeitsweise in der Seitenleiste und die Reihenfolge Anhängen, Modell, Mikrofon, Senden.
- **Texte:** Diese Tests prüfen nur geänderte Wortlaute:
  - `test_v962::test_new_texts_have_english` (Council-Hinweis);
  - `test_web::test_the_ui_shows_what_a_key_looks_like` (Hinweis auf das Add-on statt des
    Schlüsselnamens).
- **Nur noch über Add-ons:** In `test_own_keys` hinterlegen die Ende-zu-Ende-Tests ihren
  Schlüssel jetzt über Add-on und `/api/linked` statt über `/api/keys`. Alle Prüfungen danach
  sind gleich: nur dieses Konto, nur beim Anbieter, nie im Browser, nie im Klartext.
  - `the_key_area…` heißt jetzt `the_addon_says…`.
  - `a_key_typed_into_the_settings_form…` heißt jetzt `the_settings_form_takes_no_key_anymore`.
  - `key_tests_are_limited…` heißt jetzt `key_checks_are_limited…`.
  - `the_version_carries_its_name` legt einen NVIDIA- statt eines Tavily-Schlüssels an.
- **Entfallen, weil es die Funktion nicht mehr gibt:**
  - `test_the_summary_says_none_one_or_several`: Die Zusammenfassung gehörte zum Bereich
    „API-Schlüssel“. Ersetzt durch `test_only_nvidia_and_mistral_have_a_slot`.
  - `test_the_general_key_is_never_tested_against_the_operators_model`: Den allgemeinen Platz
    gibt es für Konten nicht mehr; dass er sich nicht speichern lässt, prüft derselbe neue Test.
- **`test_linked`:** neu geschrieben für Mistral und NVIDIA NIM, mit denselben Fragen wie vorher
  für Claude, ChatGPT und Gemini.
  - Abgedeckt sind Modelle, Grenzen, abgelehnter Schlüssel, Rollen im Council,
    Runden, Abbruch, Speichern erst nach Annahme, Erkennen am Schlüssel und Anmeldewege.
  - Neu: Verknüpfen geht erst nach dem Installieren, Deinstallieren löscht den Schlüssel.
  - Der Test zum direkten Weg verknüpfter OpenAI-Modelle prüft jetzt: LM Studio bleibt, OpenAI
    selbst ist gesperrt.
- **Formular und Verbindungstest nehmen keine Schlüssel mehr** (`test_web`). Diese Tests prüfen
  jetzt, dass nichts gespeichert oder benutzt wird:
  - `api_key_is_stored…` heißt jetzt `the_form_stores_no_api_key_anymore`;
  - `the_key_lands_under_the_corrected_provider`;
  - `the_search_engine_key_can_be_set…` heißt jetzt `…_comes_only_from_the_operator`;
  - `saving_stores_the_search_key…`;
  - `the_probe_endpoint_tests_the_form_values`;
  - `test_security::test_the_probe_never_hands_the_servers_key_to_a_typed_address`.
  - `empty_api_key…`, `empty_search_key…` und `open_metasearch…` sind unverändert und nutzen nur
    den Feldnamen direkt.
- **Erlaubte Modelle:**
  - `test_config::test_valid_models_pass` (Claude und GPT-4o liefern jetzt die Regel);
  - `test_v1130::test_what_counts_as_usable` (mit Schlüssel trotzdem nicht nutzbar);
  - `test_agent::test_a_hand_picked_code_model_wins` (eigenes NVIDIA-Modell; ein fremdes
    gewinnt nie);
  - `test_subagents::test_an_unknown_provider_keeps_the_main_model` (vLLM auf dem Server);
  - `test_web::test_save_values_writes_env_and_reloads` (NVIDIA statt Claude).
- **Platzhalter `"m"` → `"mistral/m"`** in den Zähltests (`test_quota`, `test_security`) und in
  `test_v1132_sol`. Ohne Kürzel ginge ein Modell in die Cloud und ist jetzt gesperrt.
  - In `test_v1132_sol::test_other_errors_are_not_hidden` hätte die Sperre (ein `ValueError`)
    den erwarteten `ValueError` sonst nur zufällig erfüllt.
- **Add-ons:**
  - `test_addons` kennt die Anmeldeart `apikey`;
  - `test_rights` nimmt die Modell-Add-ons aus, sie haben keine Rechte;
  - `test_v962::test_sign_in_buttons_and_quick_link` prüft, dass das Sammelfeld weg ist;
  - `test_v9532` löscht beim „Alle Daten löschen“ einen NVIDIA- statt eines Tavily-Schlüssels.
- **Rundgang** (`tools/rundgang.py`): Statt der Schlüsselzeile in den Einstellungen geht er
  jetzt den neuen Weg wie ein Mensch.

## Im ersten Volllauf gefunden

- `test_v1200::test_everything_else_is_refused[claude-3-5-sonnet-]`: Der neue Test erwartete
  für jedes abgelehnte Modell den Satz mit der Regel. Einen Namen ohne Kürzel ordnet LiteLLM
  aber keinem Anbieter zu; dann kommt der ältere, hier passendere Hinweis „braucht ein
  Anbieter-Präfix“ mit Beispielen. Gesperrt war das Modell trotzdem. Der Test erwartet jetzt
  je nach Fall den einen oder den anderen Satz.
- Dabei fiel auf, dass die neue Regel zuerst den Vorschlag bei Tippfehlern („Meintest du:
  nvidia_nim/…“) verdrängt hatte. `model_problem` prüft jetzt erst, ob es den Anbieter gibt,
  und dann, ob er erlaubt ist.

## Grenzen dieser Prüfung

- **Kein echtes Mikrofon und keine echte Spracherkennung.** Im Test-Browser ist die
  Erkennung nachgestellt. Geprüft sind Ablauf, Zustände und das automatische Senden, nicht die
  Erkennung selbst.
- **Kein echter Mistral- oder NVIDIA-Schlüssel.** Die Antworten der Anbieter sind nachgestellt
  (Modelllisten, Kopfzeilen mit Grenzen, 401).
