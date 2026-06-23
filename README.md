# Premiere Sub-Animations — Kit

Aus einem **fertig geschnittenen Premiere-Video + Transkript** baut dieses Kit
automatisch **animierte Overlays** (Zahlen-Cards mit Count-up, Aufzählungen,
Reveal-Grafiken, Lower-Thirds, Vergleichstabellen, CTA-Buttons …) und platziert
sie **frame-genau** zurück in den Schnitt — entweder **live** in das offene
Premiere-Projekt oder als **FCP7-XML / Placement-Liste** zum manuellen Import.

Dieses Paket ist **eigenständig**: Whisper-Transkription, die Remotion-Render-Engine
und die komplette `adb-mcp` Live-Bridge sind enthalten. Es werden **keine weiteren
Skills** benötigt.

---

## 1. Voraussetzungen

| Tool | Zweck | Installation |
|------|-------|--------------|
| **Python ≥ 3.10** | Pipeline-Scripts | python.org / `brew install python` |
| **Node.js ≥ 18 + npm** | Remotion-Render + Live-Proxy | `brew install node` |
| **ffmpeg / ffprobe** | Audio/Video-Analyse | `brew install ffmpeg` (macOS), `apt install ffmpeg` (Linux) |
| **Adobe Premiere Pro** | nur für den **Live-Weg** | Creative Cloud |

> Für den reinen Render- + Export-Weg (ohne Live-Premiere) reichen Python, Node und ffmpeg.

## 2. Installation (ein Befehl)

```bash
./setup.sh            # alles inkl. Live-Bridge
./setup.sh --no-live  # ohne adb-mcp (nur Render + FCP7-XML-Export)
```

Das installiert die Python-Deps in eine **isolierte venv** (`./.venv`, funktioniert
auch mit Homebrew-Python / PEP 668), die Remotion-`node_modules`, und – beim
Live-Setup – die adb-mcp-Bridge. Danach laufen die Selbsttests.

> **Nach dem Setup die venv aktivieren**, bevor du die Scripts startest:
> ```bash
> source .venv/bin/activate
> ```
> (oder die Scripts ohne Aktivieren direkt mit `.venv/bin/python …` aufrufen.)

Manuell ginge es so:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd skill/remotion && npm install
```

## 3. Schnellstart (Render + Export-Weg)

```bash
source .venv/bin/activate   # einmal pro Shell
cd skill
# 1) Whisper-Timecodes gegen den finalen Cut
python3 scripts/align_words.py /pfad/zum/final.mp4 --out work/v1/words.json
# 2) Plan-Entwurf erzeugen → dann von Claude/dir vervollständigen (siehe SKILL.md, Stufe 2)
python3 scripts/build_plan.py work/v1/words.json --out work/v1/animation-plan.json
# 3) transparente Overlays rendern (eigene Marke via --brand)
python3 scripts/render_overlays.py work/v1/animation-plan.json \
    --remotion remotion --formats 16x9 --out work/v1/overlays --brand default
# 4) Deliverables für den manuellen Import (FCP7-XML + placement.md)
python3 scripts/export_fcp7xml.py work/v1/animation-plan.json \
    --video /pfad/zum/final.mp4 --overlays work/v1/overlays/overlays-manifest.json \
    --out work/v1 --format 16x9
```

Die **vollständige Anleitung** (alle 9 Stufen, Plan-Schema, QC-Gates, Reel-Modus,
Batch) steht in **`skill/SKILL.md`**. Wenn du Claude Code nutzt, liest Claude diese
Datei und fährt die Pipeline für dich.

## 4. Live-Premiere (optional, mächtiger)

Overlays direkt in das **offene** Premiere-Projekt setzen. Einmaliges Setup
(UXP-Plugin sideloaden) → danach ein Befehl pro Session:
**→ siehe `docs/LIVE-PREMIERE-SETUP.md`.**

## 5. Eigene Marke (Branding)

Farben/Schrift kommen aus `skill/remotion/brands/<name>.json` und werden per
`--brand <name>` gewählt. Lege deine eigene Marke an:

```bash
cp skill/remotion/brands/default.json skill/remotion/brands/meinebrand.json
# colors.primary / accent / … anpassen, font aus der Registry (Montserrat, Poppins,
# Inter, Manrope, Sora, Playfair Display) in skill/remotion/src/font.ts wählen
python3 scripts/render_overlays.py … --brand meinebrand
```
Die mitgelieferten Presets (`neocore`, `rpm`, `thorben`, `performance-investments`)
sind nur **Vorlagen** — gern löschen oder als Beispiel behalten.

## 6. Als Claude-Code-Skill installieren (optional)

Damit Claude den Workflow automatisch erkennt, den `skill/`-Ordner als Skill
verlinken:
```bash
ln -s "$(pwd)/skill" ~/.claude/Skills/premiere-sub-animations
```
(oder kopieren). Claude triggert dann auf „Sub-Animationen für mein Video" etc.

## 7. Ordnerstruktur

```
premiere-sub-animations-kit/
├── README.md                  ← du bist hier
├── setup.sh                   ← One-Shot-Installer
├── requirements.txt           ← Python-Deps des Skills
├── docs/LIVE-PREMIERE-SETUP.md← adb-mcp Live-Bridge einrichten
├── skill/                     ← der eigentliche Skill
│   ├── SKILL.md               ← die komplette Workflow-Anleitung
│   ├── scripts/               ← Pipeline (inkl. self-contained _whisper.py)
│   ├── remotion/              ← Overlay-Render-Engine + brands/
│   ├── references/ examples/
└── vendor/
    └── adb-mcp/               ← Live-Premiere-Bridge (Drittsoftware, MIT)
```

## Lizenz / Drittsoftware

`vendor/adb-mcp/` ist Drittsoftware von Mike Chambers
(https://github.com/mikechambers/adb-mcp, MIT — siehe `vendor/adb-mcp/LICENSE.md`).
Der `premiere_drive.js`-Treiber und die Pipeline-Scripts gehören zum Kit.
