# jobs.json — Batch-Schema (beide Formate gleichzeitig)

`jobs.json` ist eine **JSON-Liste** von Job-Objekten. Eine Liste mischt 16:9- und
9:16-Videos in einem Lauf; jedes Video bleibt einzeln justierbar und einzeln
re-runnbar (`--only`). `batch.py` mappt jeden Job-Key auf die exakten
`pipeline.py`-Flags und hält die Jobs unabhängig (eigener `out`-Ordner pro Job).

```
python3 scripts/batch.py --jobs jobs.json [--parallel N] [--strict] [--only name1,name2]
```

## Job-Schema

| Key | Pflicht | Typ / Default | Bedeutung → pipeline.py-Flag |
|-----|---------|---------------|------------------------------|
| `name` | ja | string, **eindeutig** | Job-Schlüssel; Ziel für `--only`, Key in `batch-status.json` |
| `plan` | ja | Pfad | autorierter `animation-plan.json` (mit `anchorPhrase`) → `--plan` |
| `out` | ja | Pfad | **eigener Ordner pro Job** (nie geteilt) → `--out` |
| `transcript` \| `words` \| `video` | **genau eines** | Pfad | Quelle der Timecodes → `--transcript`/`--words`/`--video`. `video` zusätzlich nötig für gesichts-bewusste Platzierung **und** Reel-Zoom |
| `format` | nein | `"16x9"` \| `"9x16"` (Default `16x9`) | → `--format` |
| `brand` | nein | string (Default `thorben`) | Brand-Preset → `--brand` |
| `fps` | nein | int (Default `30`) | 9:16-Reels meist 30, 16:9-Cuts oft 50 → `--fps` |
| `avoidStyle` | nein | `"conservative"` \| `"best"` (Default `conservative`) | Zonen-Strategie face_zones → `--avoid-style` |
| `noSfx` | nein | bool (Default `false`) | kein SFX backen → `--no-sfx` |
| `noFaceAware` | nein | bool (Default `false`) | keine sprecher-bewusste Platzierung → `--no-face-aware` |
| `reel` | nein | bool (Default = `format=="9x16"`) | Reel-Dynamik aktiv → `--reel` |
| `reelZoom` | nein | float (Default `0.05`) | Breathing-Amplitude → `--reel-zoom` |
| `reelPeriod` | nein | float (Default `16`) | In→Out-Zyklus in s → `--reel-period` |
| `reelJump` | nein | float (Default `12`) | s zwischen Jump-Cuts (0 = aus) → `--reel-jump` |
| `reelJumpAmt` | nein | float (Default `0.07`) | Sprung-Stärke je Jump-Cut → `--reel-jump-amt` |
| `music` | nein | Pfad (**OPT-IN**, sonst weglassen) | Musik-Bett unter die Stimme → `--music` |
| `musicGain` | nein | float (Default `-20`) | Musik-Pegel in dB → `--music-gain` |
| `deliver` | nein | `"premiere"` \| `"flat"` (Default `premiere` bei 16:9, `flat` bei 9:16) | Liefer-Weg → `--deliver` |

**Defaults nach Format:** Ein 9:16-Job ohne explizite Keys ist automatisch
`reel=true` + `deliver=flat`. Ein 16:9-Job ist `reel=false` + `deliver=premiere`.
Beide Defaults pro Video übersteuerbar.

## Liefer-Wege (`deliver`)

- **`premiere`** (Default 16:9): bestehender `integrate.py`-Weg — `placement.md` /
  `placement.csv` + `overlays.fcpxml`. Kein Flatten; Simon platziert/feintunt in
  Premiere (oder live via adb-mcp).
- **`flat`** (Default 9:16): nach Render + SFX läuft `flatten_final.py` und
  compositet die Overlays auf das (ggf. zoom-dynamische) Video → fertiges mp4.
  Liegt `music` an, läuft danach `add_music.py` auf dieses finale mp4.

## Reel-Reihenfolge in der Pipeline (wenn `reel` UND `video`)

1. `reel_dynamics.py` aufs `video` → ein "dynamic" mp4 im `out`-Ordner (Breathing-
   Zoom + Jump-Cuts; keine Frames entfernt → Audio bleibt synchron).
2. `face_zones.py` + Flatten-Delivery nutzen **dieses gezoomte** mp4 — so sitzt das
   Gesicht auf dem gezoomten Frame an der richtigen Stelle (Zone wird gegen das
   bewegte Bild bestimmt).
3. Overlays in 9:16 rendern.
4. Bei `deliver=flat`: `flatten_final.py` compositet drüber → finales mp4; bei
   `music` danach `add_music.py`.

## Selektiver Re-Run (per-Video justieren ohne alles neu zu fahren)

`--only name1,name2` fährt **nur** diese Jobs erneut. Das ist idempotent:
`render_overlays --skip-existing` hasht je Clip, also rendert nur das wirklich
Geänderte neu. So justierst du ein einzelnes Video (Text-Swap, Timecode-Nudge,
anderer `reelZoom`), ohne die anderen anzufassen.

## Status-Registry — `batch-status.json`

`batch.py` schreibt **neben** `--jobs` eine `batch-status.json`: pro Job
`{name, status: "ok"|"fail", format, out, deliverable}` (deliverable = Pfad des
finalen mp4 bei `flat`, sonst des Placement-Bundles, falls bekannt). Bei `--only`
werden nur die betroffenen Einträge aktualisiert, die übrigen bleiben stehen.

---

## Worked Example — 6 Videos (16:9 + 9:16 gemischt)

Sechs Videos in einem Lauf: drei YouTube-Cuts (16:9, Premiere-Delivery, 50 fps) und
drei Reels (9:16, flat geliefert, 30 fps), zwei davon mit Musik-Bett. Jedes Video
hat seinen eigenen `out`-Ordner und bleibt einzeln re-runnbar.

```json
[
  {
    "name": "yt_steuer_haupt",
    "plan": "~/Desktop/SubAnimations/plans/steuer_haupt.plan.json",
    "out": "~/Desktop/SubAnimations/yt_steuer_haupt/v1",
    "transcript": "~/Desktop/SubAnimations/src/steuer_haupt.transcript.json",
    "format": "16x9",
    "brand": "thorben",
    "fps": 50,
    "deliver": "premiere"
  },
  {
    "name": "yt_portfolio_recap",
    "plan": "~/Desktop/SubAnimations/plans/portfolio_recap.plan.json",
    "out": "~/Desktop/SubAnimations/yt_portfolio_recap/v1",
    "video": "~/Desktop/SubAnimations/src/portfolio_recap_cut.mp4",
    "format": "16x9",
    "brand": "thorben",
    "fps": 50,
    "avoidStyle": "best",
    "deliver": "premiere"
  },
  {
    "name": "yt_seminar_q2",
    "plan": "~/Desktop/SubAnimations/plans/seminar_q2.plan.json",
    "out": "~/Desktop/SubAnimations/yt_seminar_q2/v1",
    "words": "~/Desktop/SubAnimations/src/seminar_q2.words.json",
    "format": "16x9",
    "fps": 50,
    "noSfx": true,
    "deliver": "premiere"
  },
  {
    "name": "reel_hook_steuer",
    "plan": "~/Desktop/SubAnimations/plans/reel_hook_steuer.plan.json",
    "out": "~/Desktop/SubAnimations/reel_hook_steuer/v1",
    "video": "~/Desktop/SubAnimations/src/reel_hook_steuer.mp4",
    "format": "9x16",
    "fps": 30
  },
  {
    "name": "reel_objekt_tour",
    "plan": "~/Desktop/SubAnimations/plans/reel_objekt_tour.plan.json",
    "out": "~/Desktop/SubAnimations/reel_objekt_tour/v1",
    "video": "~/Desktop/SubAnimations/src/reel_objekt_tour.mp4",
    "format": "9x16",
    "fps": 30,
    "reelZoom": 0.06,
    "reelPeriod": 14,
    "reelJump": 10,
    "reelJumpAmt": 0.08,
    "music": "~/Desktop/SubAnimations/music/soft_bed.mp3",
    "musicGain": -20
  },
  {
    "name": "reel_einwand",
    "plan": "~/Desktop/SubAnimations/plans/reel_einwand.plan.json",
    "out": "~/Desktop/SubAnimations/reel_einwand/v1",
    "video": "~/Desktop/SubAnimations/src/reel_einwand.mp4",
    "format": "9x16",
    "fps": 30,
    "reelJump": 0,
    "music": "~/Desktop/SubAnimations/music/calm_bed.mp3",
    "deliver": "flat"
  }
]
```

Was passiert pro Job:

- **yt_steuer_haupt / yt_seminar_q2** — 16:9 aus Transkript bzw. fertiger
  `words.json`; kein Reel, Premiere-Delivery (Placement + FCPXML). `yt_seminar_q2`
  ohne SFX (`noSfx`).
- **yt_portfolio_recap** — 16:9 mit `video` → gesichts-bewusste Platzierung im
  `best`-Stil; Premiere-Delivery.
- **reel_hook_steuer** — 9:16, nur Format gesetzt → Defaults greifen: `reel=true`,
  `deliver=flat`. reel_dynamics mit Standardwerten, dann flatten → finales mp4.
- **reel_objekt_tour** — 9:16 mit getunter Reel-Dynamik + Musik-Bett; flat geliefert
  (9:16-Default), nach Flatten läuft add_music.
- **reel_einwand** — 9:16, Jump-Cuts aus (`reelJump: 0`, nur Breathing), Musik mit
  Default-Gain, `deliver` explizit `flat`.

Lauf:

```
python3 scripts/batch.py --jobs jobs.json --parallel 3
```

Nur die zwei Reels mit Musik nachjustieren (z. B. anderes Bett), ohne die vier
anderen Videos neu zu fahren:

```
python3 scripts/batch.py --jobs jobs.json --only reel_objekt_tour,reel_einwand
```

Ergebnis-Registry liegt als `batch-status.json` neben `jobs.json`, z. B.:

```json
{
  "reel_objekt_tour": {
    "name": "reel_objekt_tour", "status": "ok", "format": "9x16",
    "out": "~/Desktop/SubAnimations/reel_objekt_tour/v1",
    "deliverable": "~/Desktop/SubAnimations/reel_objekt_tour/v1/reel_objekt_tour_final.mp4"
  },
  "yt_steuer_haupt": {
    "name": "yt_steuer_haupt", "status": "ok", "format": "16x9",
    "out": "~/Desktop/SubAnimations/yt_steuer_haupt/v1",
    "deliverable": "~/Desktop/SubAnimations/yt_steuer_haupt/v1/placement.md"
  }
}
```

Siehe `references/jobs.example.json` für eine minimale 2-Job-Vorlage zum Kopieren.
