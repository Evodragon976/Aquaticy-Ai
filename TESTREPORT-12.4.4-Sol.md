# Prüfbericht: 12.4.4 Sol

Stand: 2026-10-24. Grundlage: **12.2.4 Terra**, Commit `bd4e780`, Branch `Aquaticy-ai`.

## Worum es geht

Alle Texte der Oberfläche sind jetzt in **einfacher Sprache** geschrieben, auf Deutsch und
auf Englisch. Ziel: Auch wer sich mit Technik nicht auskennt, versteht sofort, was gemeint
ist. Die Texte sollen dabei kurz bleiben.

### Regeln (aus der Recherche)

Eine verbindliche Norm für einfache Sprache gibt es nicht. DIN 8581-1 und ISO 24495-1
beschreiben allgemein verständliche Sprache. Die Hinweise der folgenden Quellen stimmen in
den Kernpunkten überein:

- kurze Sätze, höchstens 15 bis 20 Wörter; lange Sätze teilen
- aktiv schreiben und die Person mit „du“ ansprechen
- bekannte Wörter statt Fachwörter; ein nötiges Fachwort kurz erklären
- das Wichtigste zuerst
- für eine Sache immer denselben Begriff (z. B. „Heimnetz“)
- freundlich; in Knöpfen und Hinweisen kein „bitte“

Quellen: Kanton Zürich, „Regeln für Leichte Sprache“; BUND, Handout „Einfache Sprache“;
Haufe Akademie, „Einfache Sprache“; Grafana Writers' Toolkit; Maersk Design System,
„Writing“; Uxcel, „Microcopy“. Die Regel steht jetzt auch in `AGENTS.md`.

### Umfang

- 213 Texte neu geschrieben, jeweils Deutsch und Englisch. Betroffen sind
  `aquaticy/webui.html` und Meldungen des Servers in `addons.py`, `cluster.py`,
  `config.py`, `coworker.py`, `google.py`, `linked.py`, `llamacpp.py`,
  `local_model.py`, `web.py`, `webview.py` und `render.py`.
- Hinweise zu Einwilligung, Datenschutz und Löschen behalten jede Tatsache. Sie sind nur in
  kürzere Sätze geteilt (z. B. Auto-Upgrading, Spracheingabe, Konto leeren).
- Der Hinweis „Die Texte hier schreibt eine KI“ bleibt unten im Chat sichtbar.
- Texte, die nur Teil eines Satzes um einen Link oder Code sind, blieben unverändert.

## Angepasste Tests

Die Texte haben sich absichtlich geändert. Die folgenden Tests prüfen den neuen Wortlaut;
das geprüfte Verhalten ist gleich geblieben:

- `test_addons`, `test_aiguard`, `test_linked` (2), `test_llamacpp`, `test_v1122` (2),
  `test_v1132_terra`, `test_v1200`, `test_v1211_terra`, `test_v1221_sol`, `test_v961`,
  `test_v962`, `test_web` (5) und der Rundgang (`tools/rundgang.py`, KI-Hinweis).
- `test_v1121.test_ui_explanations_stay_short` blieb unverändert: Ein Regeltext war zuerst
  zu lang (355 statt höchstens 340 Zeichen) und wurde gekürzt.

## Prüfung

`python tools/pruefung.py`: ruff, mypy, bandit (keine neuen Hinweise), JavaScript der
Oberfläche und die ganze Testsuite einschließlich Rundgang im Browser.

Zusätzlich wurde geprüft, dass kein alter Text irgendwo im Code übrig ist (auch nicht in
Code, der Meldungen vergleicht), dass jeder englische Schlüssel benutzt wird und dass keine
Zeile länger als 100 Zeichen geworden ist.

### Fehler- und Sicherheitsprüfung

Diese Fassung ändert nur Texte, kein Verhalten. Geprüft wurde deshalb vor allem, ob ein
geänderter Text an anderer Stelle gebraucht wird:

- Kein Code vergleicht mehr einen alten Wortlaut. Ein Rest wurde gefunden und angeglichen:
  die Planungszeile der Kommandozeile (`render.py`, „lese die Anfrage …“).
- Meldungen des Servers (Fehler, Grenzen, Verbund) sind in Oberfläche, Englisch-Wörterbuch
  und Tests gleich.
- bandit meldet nichts Neues; die Sicherheitsregeln (netguard, injection, aiguard,
  guardrails, auth, sandbox) sind unverändert.
- Der Rundgang im Browser schlug einmal fehl, als nebenher weitere Browser liefen
  (Messung der Höhe unter Last). Allein und im zweiten Gesamtlauf ohne Nebenlast:
  440 Prüfungen, nichts beanstandet.

## Grenzen

Einfache Sprache ist eine Abwägung: Manche Fachwörter (virtual machine, Token, MagicDNS)
bleiben, weil die Person sie auf anderen Seiten genau so wiederfindet.
