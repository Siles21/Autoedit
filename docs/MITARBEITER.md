# Sub-Animationen — Anleitung für Mitarbeiter

Du brauchst **keinen Befehl und keinen Code**. Du redest mit Claude, Claude macht den Rest.

---

## Einmalig einrichten (pro Rechner, ~15 Minuten)

1. **Programme installieren** (nur falls noch nicht da):
   - [Python 3](https://www.python.org/downloads/) (Version 3.10 oder neuer)
   - [Node.js](https://nodejs.org/) (Version 18 oder neuer)
   - ffmpeg — macOS: `brew install ffmpeg`
2. **Kit einrichten** — Terminal öffnen, in den Kit-Ordner wechseln, einmal ausführen:
   ```bash
   ./setup.sh
   ```
   Das installiert alles und meldet am Ende, ob es einsatzbereit ist. Der Skill wird dabei
   automatisch bei Claude registriert.
3. **Neue Claude-Session starten** — ab jetzt kennt Claude den Skill.
4. **Nur für den Live-Weg** (Animationen landen direkt in der offenen Premiere-Timeline):
   einmalig das Premiere-Plugin laden — siehe `LIVE-PREMIERE-SETUP.md`. Ohne diesen Schritt
   funktioniert alles trotzdem, du importierst die fertigen Dateien dann selbst in Premiere.

**Prüfen, ob alles steht:**
```bash
python3 skill/scripts/doctor.py
```
Steht am Ende „Pipeline einsatzbereit" — fertig. Steht dort ein Fix-Befehl, führe ihn aus
oder schicke die Ausgabe an Claude.

---

## Benutzen

**Voraussetzung:** Das Video ist in Premiere **fertig geschnitten**. Der Schnitt wird nicht
angetastet — die Animationen kommen auf eine Spur darüber.

### Schnellster Weg (empfohlen)

1. In Premiere: Sequenz transkribieren (**Text-basierte Bearbeitung**), dann das Transkript
   als **JSON exportieren**.
2. Zu Claude sagen:
   > Mach Sub-Animationen für dieses Video. Transkript: `/pfad/zum/transkript.json`

Damit entfällt die Whisper-Wartezeit, weil Premiere die Wort-Timecodes schon kennt.

### Alternativer Weg

1. Fertigen Schnitt als Video exportieren (z. B. `final.mp4`).
2. Zu Claude sagen:
   > Mach Sub-Animationen für dieses Video: `/pfad/zum/final.mp4`

Claude transkribiert dann selbst (dauert je nach Länge einige Minuten).

> **Pfad kopieren (macOS):** Datei im Finder anklicken → `⌥ + ⌘ + C` → im Chat einfügen.

---

## Was dann passiert

1. Claude prüft die Umgebung und liest das Transkript.
2. Claude schlägt die Animationen vor: **Timecode · Typ · Inhalt · Dauer** als Tabelle.
3. **Du gibst frei.** Hier entscheidest du: behalten, streichen, Text ändern, verschieben.
   Sag einfach, was weg soll („Nummer 3 und 7 raus, bei 5 muss es 4,2 % heißen").
4. Claude rendert die Overlays (transparent) und platziert sie — live in Premiere oder als
   Dateien plus Platzierungsliste zum Importieren.
5. Claude sagt dir am Ende, wie viele Animationen entstanden sind und wo die Dateien liegen.

---

## Was du Claude mitgeben kannst (optional)

- **Format:** „in 9:16" oder „beide Formate" (Default: 16:9)
- **Branding:** „nimm das Preset `neocore`" (Claude zeigt dir die verfügbaren Presets)
- **Ohne Freigabe-Gate:** „mach es voll automatisch ohne Gate" (Default: mit Gate)
- **Musik:** „leg Musik drunter: `/pfad/track.mp3`"

---

## Wenn etwas nicht klappt

| Problem | Lösung |
|---|---|
| Claude kennt den Skill nicht | `./setup.sh --install-skill`, dann **neue** Session starten |
| „Pipeline blockiert" / Fehler beim Start | `python3 skill/scripts/doctor.py` laufen lassen, Ausgabe an Claude schicken |
| Animationen landen nicht in Premiere | Premiere offen? Plugin geladen? Siehe `LIVE-PREMIERE-SETUP.md` — sonst nutzt Claude automatisch den Datei-Weg |
| Timecode sitzt nicht | Claude sagen: „Animation X um 0,5 Sekunden früher" — er zieht sie nach und platziert neu |
| Falsche Zahl in einer Grafik | Claude sagen, wie es richtig heißt. Er erfindet keine Zahlen — er nimmt nur, was gesprochen wird |

**Grundregel:** Bei Unklarheiten schick Claude die Fehlermeldung im Wortlaut. Er kennt die
Pipeline und die Fix-Befehle.
