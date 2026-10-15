# Prüfbericht: 11.2.2 Luna

Stand: 2026-10-15. Grundlage: **11.2.1 Sol**, Commit `55f3b14`, Branch `Aquaticy-ai`.

## Was neu ist

- **Handy:** Die Eingabe steht auf der Startseite unten, wo der Daumen ist. Die Begrüßung
  steht in der Mitte darüber, die Vorschläge direkt über der Eingabe. Vorher stand alles in
  der Mitte, und das untere Drittel blieb leer.
- **Tablet hoch:** Begrüßung und Eingabe sitzen etwas über der Mitte. Unten bleibt Platz für
  die Tastatur.
- **Senden-Knopf kleiner:** am Handy sichtbar 34 statt 44 px, auf Tablet und Rechner 30 statt
  32 px. Zum Antippen bleibt er 44 px hoch, dafür sorgt ein unsichtbarer Rand.
- **Modellname:** Am Handy nimmt die Modellwahl den Rest der Zeile ein und zeigt mehr vom
  Namen („mistral-larg…“ statt „mistral-la…“). Bei 360 px, der häufigsten Android-Breite,
  steht wieder der Name statt nur eines Sinnbilds.

## Gefundene Fehler und ihre Ursache

Nachgestellt nach den Bildschirmfotos vom Handy (412 px breit, dunkel) im echten Chromium.

1. **Heller Strich am linken Rand.** Die eingeklappte Seitenleiste liegt außerhalb des
   Bildschirms, ihr Schatten aber nicht. Jetzt hat sie eingeklappt keinen Schatten. Außerdem
   ist sie dann unsichtbar für die Tab-Taste: Vorher konnte man per Tastatur in eine Leiste
   springen, die man nicht sieht.
2. **Begrüßung bei offener Tastatur verdeckt.** Die Seite war so hoch wie der Bildschirm ohne
   Tastatur. Öffnete sich die Tastatur, schob der Browser die ganze Seite nach oben, und die
   Kopfzeile lag über der Begrüßung. Jetzt folgt die Höhe dem sichtbaren Bereich
   (`visualViewport`, dazu `interactive-widget=resizes-content`). Die Seite selbst scrollt
   nicht mehr, nur der Chat darin. Beim Hineinzoomen bleibt das Layout ruhig.
3. **Grauer Kasten um „+“ nach dem Antippen.** Hover-Effekte blieben auf Touch-Geräten nach
   dem Tippen stehen. Alle 37 reinen Hover-Regeln gelten jetzt nur noch mit Maus
   (`@media (hover:hover)`).
4. **Doppelter grüner Rahmen um das Eingabefeld.** Der Rahmen der Eingabe zeigt den Fokus
   schon, dazu kam ein zweiter Ring um das Textfeld darin. Der zweite ist weg.
5. **Auf Touch-Geräten unerreichbar:** Die Knöpfe unter einer Antwort (Kopieren, Als Datei)
   und das „⋯“-Menü der Chats erschienen nur beim Darauffahren mit der Maus. Ohne Maus sind
   sie jetzt immer sichtbar.
6. **„Enter senden · Shift+Enter Zeilenumbruch“** stand auch auf Handy und Tablet, wo es
   keine Shift-Taste gibt. Ohne Maus und Tastatur ist der Hinweis jetzt aus.
7. **Bei der eigenen Prüfung gefunden:** In der neuen Anordnung schrumpfte die Eingabe am
   360-px-Handy auf Inhaltsbreite (ein `margin:auto` in einer Flex-Spalte). Und der
   unsichtbare Trefferrand des Senden-Knopfs ragte 5 px über die Knopfzeile hinaus (der
   Rundgang hat das gemeldet). Beides behoben.

## Was geprüft wurde

| Prüfung | Ergebnis |
|---|---|
| Vollständige Prüfkette (`python tools/pruefung.py`) | alle fünf Schritte ohne Beanstandung (Rückgabewert 0) |
| Testsuite (`pytest`) | **4830 bestanden, 27 übersprungen, keine Fehlschläge** (4857 Tests, 15 Minuten) |
| Neue Tests (`tests/test_v1122.py`) | 7, alle bestanden |
| Rundgang im Browser (`tools/rundgang.py`) | 412 Prüfungen, keine Beanstandung; neu: Senden-Knopf höchstens 36 px und trotzdem auf 44 px Höhe treffbar, kein Schatten der eingeklappten Leiste – auf Handy, Tablet hoch, Tablet quer und großem Schirm |
| Bildschirmfotos (dunkel), vorher und nachher | Handy 412 × 770, 360 × 700, 320 × 568; Tablet 820 × 1180, 744 × 1133, 1180 × 820; Rechner 1440 × 900. Jeweils Start, „+“ angetippt, Tastatur offen (Höhe 56 %), Chat. Nirgends steht etwas seitlich über, die Begrüßung liegt immer unter der Kopfzeile. |
| Rechner (1440 × 900) | sieht aus wie vorher, nur der Senden-Knopf ist 2 px kleiner |

## Sicherheit

- Am Server hat sich nichts geändert. Die Änderungen betreffen CSS, eine Zeile im
  `viewport`-Tag und ein kurzes Skript.
- Das Skript liest nur die Höhe des sichtbaren Bereichs und schreibt sie als Zahl in eine
  CSS-Variable. Es verarbeitet keine Eingaben und lädt nichts nach. Die Content-Security-Policy
  bleibt unverändert, die Konsole bleibt im Rundgang ohne Fehler.
- Die eingeklappte Seitenleiste ist jetzt `visibility:hidden` und damit für Tastatur und
  Screenreader nicht erreichbar, solange sie zu ist.

## Grenzen dieser Prüfung

- **Kein echtes Handy.** Geprüft wurde in Chromium mit Handy- und Tablet-Emulation (Touch,
  Pixeldichte 2 bis 3). Die Tastatur wurde als niedrigeres Fenster nachgestellt. Wie
  DuckDuckGo, Samsung Internet oder Safari die Tastatur im Einzelnen behandeln, ließ sich hier
  nicht prüfen. Das neue Verhalten folgt dem Standard (`visualViewport`), den alle drei kennen.
- Die Fotos stammen aus einer Testumgebung mit gestelltem Modell; Texte wie die Begrüßung
  wechseln zufällig.
