---
name: premiere-sub-animations
description: Erzeugt automatisch Sub-Animationen (Zahlen-Cards mit Count-up, Aufzählungs-Listen, Spannungs-/Reveal-Grafiken, Lower-Third-Bauchbinden) für bereits in Adobe Premiere geschnittene YouTube-Videos & Seminar-Aufzeichnungen und platziert sie frame-genau zurück in den Schnitt. Whisper liefert word-level Timecodes gegen den finalen Cut, Claude erstellt aus Transkript einen Animations-Plan (mit Freigabe-Gate), Remotion rendert transparente ProRes-4444-Overlays, Integration entweder live via adb-mcp (Port 3030) oder als Overlays + Platzierungs-Liste/FCP7-XML. IMMER nutzen wenn der User sagt "Sub-Animationen für mein Video", "Grafiken in mein geschnittenes Video", "Zahlen/Aufzählungen animieren", "Spannung mit Overlays aufbauen", "Animationen aus Transkript", "Premiere-Video mit Motion-Graphics anreichern", oder ein fertig geschnittenes Premiere-Projekt + Transkript hat und automatisch animierte Einblendungen will. NICHT für: Reel-Schnitt von 0, reines Reformatieren von Ad-Creatives, oder reine Skript-Erstellung.
---

# Premiere Sub-Animations

Automatisierter Workflow: **fertig geschnittenes Premiere-Video + Transkript → animierte Overlays, frame-genau platziert**. Whisper-Transkription, Remotion-Overlays und die `adb-mcp` Live-Premiere-Bridge sind in diesem Kit **mitgeliefert** — keine externen Skills nötig.

> ## Distributions-Hinweis (bitte zuerst lesen)
> Dies ist ein **eigenständiges Kit**. Setup-Anleitung: `../README.md` und `../docs/LIVE-PREMIERE-SETUP.md`.
> - **Setup zuerst:** `../setup.sh` einmal laufen lassen, dann `source ../.venv/bin/activate` (Python-Deps liegen in der venv). Erst danach `python3 scripts/...` aufrufen.
> - **Whisper** läuft über das mitgelieferte `scripts/_whisper.py` (kein Nachbar-Skill).
> - **Live-Premiere** läuft über `../vendor/adb-mcp/` (mitgeliefert).
> - **Branding/Farben** kommen ausschließlich aus `--brand <name>` → `remotion/brands/<name>.json`. Default-Preset ist `default`; lege dein eigenes an (siehe `remotion/brands/default.json`). Die Beispiel-Presets (`neocore`, `rpm`, `thorben`, `performance-investments`) sind nur Vorlagen.
> - Inline-Notizen wie „(Memory …)", „(Simon …)" oder „[[…]]" sind **interne Entwicklungs-Referenzen** und können ignoriert werden — sie verweisen auf nichts in diesem Kit. Die genannten Regeln (z. B. Du-Form, keine Emojis, Zahlen nie erfinden) sind sinnvolle Defaults; passe sie an deine Marke/Sprache an.

## Wann dieser Skill

Der User hat ein **bereits geschnittenes** Video (YouTube / Seminar) und will automatisch Sub-Animationen reinbekommen, die:
- relevante **Zahlen** als Count-up-Stat-Cards zeigen,
- wiederkehrende **Aufzählungen** Punkt für Punkt einblenden,
- an **Spannungspunkten** Reveal-Grafiken setzen,
- Kernbegriffe als **Lower-Third-Bauchbinde** zeigen.

Es wird NICHT neu geschnitten. Der Schnitt bleibt unangetastet; Overlays kommen auf eine Grafik-Spur darüber.

## Pipeline (6 Stufen)

```
[1 Align]   final video → words.json   (Whisper word-level, Timecodes = finaler Cut)
[2 Analyst] words.json + Transkript → animation-plan.json   (Claude: Zahlen/Aufzählungen/Spannung/Labels)
[3 GATE]    Simon reviewt/korrigiert animation-plan.json     ← einziger Pflicht-Stopp
[4 Render]  animation-plan.json → transparente ProRes-4444-Overlays (je Format ein .mov pro Eintrag)
[5 Place]   adb-mcp live auf Grafik-Spur  ODER  Overlays + placement.md / FCPXML
[6 QC]      Frames an Anker-Timecodes prüfen (Overlay sichtbar? Zahl korrekt? keine Kollision?)
```

Arbeitsordner pro Lauf (Versionierung, nie überschreiben — siehe Memory `feedback_ad_versioning`):
`~/Desktop/SubAnimations/<videoname>/vN/` mit `words.json`, `animation-plan.json`, `overlays/<format>/*.mov`, `placement.md`, `qc-checklist.md`.

---

### Stufe 1 — Align (`scripts/align_words.py`)

Whisper läuft auf dem **finalen** Video, damit die Timecodes exakt zur geschnittenen Timeline passen.

- Wenn adb-mcp live ist: zuerst die aktive Sequenz exportieren (`export_sequence`) und diesen Render als Quelle nehmen. Sonst fragt man Simon nach dem exportierten Video-Pfad (oder nimmt die Quelldatei, falls sie identisch zum Schnitt ist).
- `python3 scripts/align_words.py <final_video> --out <vN>/words.json`
- Reuse: `auto-cut-teleprompter/pipeline/{audio.probe, audio.extract_audio, transcribe.transcribe}` (faster-whisper, word-level, `language=de`).
- Output `words.json`: `{video, fps, fps_num, fps_den, width, height, duration, full_text, words:[{text,start,end,confidence}]}`.

Das mitgelieferte Transkript dient Claude in Stufe 2 als **Inhalts-/Schreibweise-Referenz** (saubere Begriffe, korrekte Zahlen). Die **Timecodes** sind immer die aus Whisper.

**Whisper-frei (schneller), wenn Premiere die Sequenz schon transkribiert hat** (Text-based Editing → Transkript als JSON exportieren): `python3 scripts/premiere_transcript.py <transcript.json> --out <vN>/words.json` — die word-level Timecodes stehen schon gegen den Schnitt, kein Whisper nötig.

**Anker setzen (Pflicht für Re-Sync):** jede Animation braucht eine `anchorPhrase` (die gesprochenen Worte, zu denen sie gehört). Fehlt sie, nachträglich auffüllen: `python3 scripts/build_plan.py <vN>/words.json --backfill <vN>/animation-plan.json` (speichert auch `anchorOffset` für exakte relative Lage).

### Stufe 2 — Analyst (Claude + `scripts/build_plan.py`)

`build_plan.py` erzeugt einen **Entwurf** mit allen automatisch erkannten Zahlen als `stat`-Einträge:

```
python3 scripts/build_plan.py <vN>/words.json --out <vN>/animation-plan.draft.json
```

Dann **liest Claude** `words.json` (+ das gelieferte Transkript) und vervollständigt den Plan:
- **Zahlen** (`stat`): Draft-Einträge kuratieren — irrelevante streichen, `label`/`sublabel`/`value` sauber formatieren. **Werte nicht erfinden** — bei NeoCore-Inhalten Remi als Quelle (Memory `feedback_remi_als_quelle`). `value` ist ein vorformatierter String, z. B. `"4,2 %"`, `"1.200 €"`.
- **Aufzählungen** (`enumeration`): Stellen finden, wo gezählt/aufgelistet wird ("erstens/zweitens", "drei Dinge", "zum einen … zum anderen"). `content.items` = die Listenpunkte (kurz, prägnant), `atSeconds` = Beginn der Aufzählung.
- **Spannungspunkte** (`reveal`): rhetorische Fragen, Cliffhanger, "pass auf", Payoff-Momente. Reveal **0,3–0,5 s vor** der Auflösung setzen. `content.text` = die Auflösung/Kernaussage, optional `content.teaser` = Andeutung.
- **Lower-Thirds** (`lowerthird`): **NUR für Personen** (Name + Rolle) — Simon-Regel, 2026-06-10. `content.text` = Name, `content.sublabel` = Rolle · Ort, und **`content.person: true`** (Pflicht, sonst flaggt `--lint-lt` den Eintrag). KEINE Keyword-Pops, KEINE Konzept-/CTA-/Kapitel-Straps als Lower-Third — die „helfen nicht" und sind verboten. Der frühere Keyword-Pop-Lückenfüller (`--fill-gaps`) ist stillgelegt; Dichte kommt aus echten Inhalten (`--coverage`/`--suggest`), nie aus Füllwörtern. QC-Gate `build_plan.py --lint-lt` (in `pipeline.py`) bricht bei Nicht-Personen-LTs ab; `--strip-lt` entfernt sie.
- **Multi-Step** (`sequence`): längere, aufbauende Animation für schnelle Fakten-Folgen (Feature-Listen, Recaps, Zusammenfassungen, Aufzählungen). `steps[]` mit Beats (`label`/`kpi`/`text`/`bullet`), die nacheinander einblenden.
- **Vergleichstabelle** (`comparetable`, NEU 2026-06-12): native 2-Spalten-Tabelle (z. B. Bruttopolice vs Nettopolice). `content.columns` (3: Label + 2 Datenspalten), `content.rows[]` mit `label`/`values[2]`/**`revealAt`** (Sek ab Clip-Start — Zeile poppt im Sprech-Takt)/`highlight` (Ergebniszeile, Akzent-BG) + `advantage` (Pill, z. B. „+11.260 €"). Zahlen zählen hoch. Eigene **lange Hold-Cap** (bis 60 s, `LONG_HOLD_TYPES` in common.py) — Doku-Cutaway baut sich über die ganze gesprochene Stelle auf. **Belege/Tabellen so NACHBAUEN, nie als Screenshot** (Simon-Regel, s. u.).
- **Call-to-Action** (`cta`, NEU 2026-06-12): Gold-Button unten-zentriert + pulsende SVG-Pfeile nach unten (z. B. „Bestandsrechner öffnen" + `content.sublabel` „Button unter dem Video"). `content.text` = Label. Für Sales-/Webinar-CTAs an Button-Verweisen — **NICHT für organische Reels** (Memory `feedback_reels_no_cta`).
- **Vergleichskarte** (`comparecards`, NEU 2026-06-13): zwei Konzept-Karten nebeneinander mit **VS-Badge** (z. B. Banken vs NeoCore Finance, Öffentlicher Markt vs Off-Market, Steuerberater vs NeoCore) — links rutscht von links, rechts von rechts, Items staggern. **Rein visueller Kontrast, KEINE Zahlen nötig** (anders als `comparebars`). `content.left`/`content.right` = je `{label, tone, icon, items[]}`; `tone:"bad"` = roter Wash + ✕-Default, `tone:"good"` = Akzent + ✓-Default; `content.kicker` = Überschrift. **Das visuelle Herzstück jedes Kontrast-Reels.**
- **1:1-Rebuild-Typen** (NEU 2026-06-15, um eine fertige Ad-Animation originalgetreu in einem anderen Format nachzubauen): **`splitheadline`** = weiße Zwei-Teil-Hook-Headline über dem Footage (`content.headLeft`/`headRight`, in 16:9 oben-links/oben-rechts, in 9:16 vertikal gestackt; `{geschweift}` = fett). **`fullcard`** = VOLLBILD-OPAKE Karte, die das Footage ersetzt (heller Verlauf weiß→Periwinkle #C9CFFD); `content.variant:"badge"` = Navy-Kreis #1F2747 + Icon (Marken-Bumper), `variant:"text"` = zentrierte Navy-Zeile #20294A, baut Wort-für-Wort auf, `{bold}`-Wörter #1B2A66. **`accentbar`** = oben weiße fette Headline mit rotem Akzent-Block #C62A1F, der von links einwischt (z. B. „Kein Steuertrick"). Alle drei haben in `Overlay.tsx` einen **Early-Return** (kein Scrim/zoneBox/LowerOffset, fullcard opak) — im Composite decken die fullcards Chris ab, der Rest liegt transparent drüber. `{bold}`-Parsing via `graphics/boldParse.ts`. **Workflow für „bau die Animationen 1:1 nach":** Original frame-genau katalogisieren (scene-cuts + Frame-Sheets), Farben sampeln (PIL-getpixel), Roh-Footage reframen, Plan mit diesen Typen an Original-Timings, rendern, `flatten_final` (opake Karten ersetzen Footage). Braucht das ROH-Footage ohne eingebrannte Grafik (fertige Ad → sonst doppeln sich die Animationen).
  - **`accentbar` Mehrzeilen-Alarm-Modus** (NEU 2026-06-22): neben `content.text` (einzeilig auf rotem Block) jetzt auch `content.lines` (weiße fette Zeilen oben) + `content.highlight` (die Phrase auf dem roten Wipe-in-Block) + dünner roter Alarm-Balken darüber → großer, knalliger Hook (z. B. lines `["MERZ WILL, DASS DU"]`, highlight `"BIS 70 ARBEITEST"`). `content.text` als Fallback weiter mitgeben (Validator verlangt es). Für laute Politik-/Schock-Hooks ab Sekunde 0.
- **`lottie` — Designer-Grade Animationen** (NEU 2026-06-22, „aufwendigere Animationen wie motion.so"): spielt einen After-Effects-/LottieFiles-/Rive-**Lottie-JSON-Export** frame-deterministisch über `@remotion/lottie` ab → jede beliebige komplexe Animation wird ein platzierbares Overlay in der normalen Pipeline (render → flatten/place). `content.src` = Dateiname unter `remotion/public/lottie/` (z. B. `"confetti.json"`; bare name → `lottie/<name>`, Pfad mit `/` as-is unter public/, oder eine `https`-URL). `content.loop` (Default false), `content.lottieSpeed` (Default 1), `content.fit` (`"contain"` Default = Letterbox auf File-Aspect, `"full"` = formatfüllend/crop). Early-Return in `Overlay.tsx` (transparent, kein Scrim); Komponente `LottieOverlay.tsx`. **Neue Animation hinzufügen:** Lottie-JSON exportieren (AE Bodymovin / LottieFiles-Download / Rive) → nach `remotion/public/lottie/` legen → `{"type":"lottie","atSeconds":…,"hold":…,"content":{"src":"<datei>.json","loop":true}}`. Deps: `lottie-web` 5.13 + `@remotion/lottie@4.0.467`. **WARUM Lottie statt Motion-Library (motion.dev):** Remotion rendert frame-deterministisch (`useCurrentFrame`), Motion animiert gegen die Echtzeit-Uhr → nicht reproduzierbar; Lottie + die installierten `@remotion/{paths,shapes,transitions,motion-blur,animation-utils}` decken das motion.so-Vokabular deterministisch ab.
- **Icons in Aufzählungen/Karten** (NEU 2026-06-13): `enumeration`-Items und `comparecards`-Items dürfen `{text, icon}` statt nur String sein → Zeilen-Icon aus `graphics/Icon.tsx` (built-in Line-Icon-Set: `check x clock bolt bank key lock link doc target arrow layers search users euro shield gears trend handshake`). Unbekannter Name → Punkt. Macht Listen visuell statt reiner Text-Bullets. `content.icon` setzt zusätzlich ein Leit-Icon auf `reveal`/`stat`. **Default-Regel: Aufzählungen/Reveals möglichst mit passenden Icons planen — „nicht nur Text-Animationen" (Simon 2026-06-13).**

**Timing-Regeln (Validator erzwingt sie — Memory `feedback_video_event_cadence`):** max **10 s** pro Animation; Einzel-Typen ≤ 4,5 s (länger → `sequence`); in einer `sequence` **alle ≤ 2 s** ein neuer Beat, kein statischer Schwanz. Übergeordnet: im Gesamtvideo **alle ≤ 5 s** ein visuelles Ereignis (Cut/Animation/Einblendung) — Overlays füllen die Lücken, die der Schnitt nicht trägt; beim Planen Lücken zwischen Ereignissen dicht halten. Synchrone Einzel-`stat`s an gesprochenen Zahlen, `sequence`s an schnellen Listen/Recaps.

Sprache: **Du-Form** (Memory `feedback_du_form`), **keine Emojis** (Memory `feedback_keine_emojis`). Anker via `anchorPhrase` (gesprochene Phrase) — `build_plan.py`/`common.py` matchen sie auf `atSeconds`.

**Timing-Vorlauf (gegen „zu spät", Simon-Regel 2026-06-10):** `--resolve` zieht jede Animation um `--lead` (Default **0,4 s**) VOR ihr Anker-Wort, damit die Einblendung sitzt, wenn das Wort fällt — nicht danach. Pro Eintrag per `content`-Nachbar `leadIn` übersteuerbar. Anker zudem auf die ersten Worte des gemeinten Begriffs setzen (nicht auf eine Phrase danach).

Schema pro Eintrag → siehe `references/plan-schema.md` und `examples/animation-plan.example.json`.

Validieren: `python3 scripts/build_plan.py --validate <vN>/animation-plan.json`

### Stufe 3 — Freigabe-Gate (Pflicht-Stopp)

Claude zeigt Simon den Plan als Tabelle: **Timecode · Typ · Inhalt · Dauer**. Simon kann behalten/löschen/Text ändern/Timecode nudgen. Korrekturen zurück in `animation-plan.json`, dann erneut `--validate`. Erst nach Simons „go" geht es weiter. (Wenn Simon „voll automatisch ohne Gate" will, überspringen — Default ist mit Gate.)

### Stufe 4 — Render (`scripts/render_overlays.py` + `remotion/`)

Pro Plan-Eintrag und Format ein **transparentes** ProRes-4444-Overlay:

```
cd remotion && npm install    # einmalig (oder einmal ../setup.sh laufen lassen)
python3 scripts/render_overlays.py <vN>/animation-plan.json \
    --remotion remotion --formats 16x9,9x16 --out <vN>/overlays --fps 30 --brand neocore
```

- **Branding (`--brand <name>`):** Farben + Schrift kommen aus einem benannten Preset in `remotion/brands/<name>.json`. Mitgeliefert: `neocore` (Default), `rpm` (Dubai, schwarz/Hermes-Orange/Creme, Poppins), `thorben` (dark/Bronze). Neues Branding = einfach `remotion/brands/<name>.json` anlegen (Schema: `name`, `font`, `colors{primary,primaryDark,accent,muted,white}`) und `--brand <name>` rendern. Verfügbare Fonts (Registry in `remotion/src/font.ts`): Montserrat, Poppins, Inter, Manrope, Sora, Playfair Display — weitere durch Import dort ergänzen. Borders/Glows leiten sich automatisch aus `accent` ab (`color.ts`).
- Eine Remotion-Composition `Overlay`, per `--props` je Eintrag parametrisiert (Typ, Format, Inhalt, `hold`, `brand`).
- Render: `--codec prores --prores-profile 4444 --pixel-format yuva444p10le` → echter Alpha-Kanal. **Kein** Quell-Video nötig (Hintergrund kommt in Premiere aus V1).
- Komponenten: `StatCard` (Count-up), `EnumerationList` (gestaffelt), `RevealGraphic` (Blur→Scharf-Reveal), `LowerThird` (Slide-in), `StepSequence`, `graphics/{KpiBig,CompareBars,Chart,CompareTable,CtaButton}`. NeoCore-Brand: Navy `#0E2146`, Akzent `#58A6FF`, Montserrat (Memory `reference_neocore_blau`).
- **Neue Komponente anlegen** (Muster aus 2026-06-12): `graphics/<Name>.tsx` modelliert nach `CompareBars.tsx` (reuse `panelStyle`/glass aus `surface.ts`, `enterExit`/`scaleFor` aus `anim.ts`, `countUp`/`parseNumber` aus `countup.ts`, `rgba` aus `color.ts`, `resolveFont`); pro-Zeile-Reveal per `frame - Math.round(revealAt*fps)` gaten (statt index·stagger). Registrieren in: `src/types.ts` (`OverlayType` + Content-Felder), `src/Overlay.tsx` (Routing + `SCRIM_BY_TYPE` + `LOWER_OFFSET`), `scripts/common.py` (`VALID_TYPES` + Validierung; lange Typen in `LONG_HOLD_TYPES`). **WICHTIG: Param-/Komponenten-Anzeigenamen sind in Premiere LOKALISIERT** — wenn du Lumetri/Motion/Audio über adb-mcp ansteuerst, IMMER über Match-Name + Param-INDEX (stabil), nie Anzeigename (s. `project_adb_mcp`).
- Output: `<vN>/overlays/16x9/<id>.mov`, `…/9x16/<id>.mov`, plus `overlays-manifest.json`.
- Vorschau im Studio: `cd remotion && npx remotion studio src/Root.tsx`.

### Stufe 5 — Integration (zwei Wege, Auto-Detect)

Erst prüfen, ob adb-mcp live ist:
```
python3 scripts/integrate.py --probe-only
```

**Weg A — Live via `premiere_drive.js`** (Standard 2026-06; Port 3030, Premiere offen, Plugin geladen). Der CLI-Treiber `../vendor/adb-mcp/premiere_drive.js` ist der produktive Weg (nicht die abstrakten MCP-Tools). Modi:
- `node premiere_drive.js info` → ganzer Sequenzstand (alle Spuren/Clips mit Name, Start-Ticks, Dauer; fps).
- `place <manifest.json> --seq <id> --vtrack 9 --atrack 9` → importiert + setzt jedes Overlay; **greedy Track-Packing** (überlappende Einträge auf eigene Spuren), Status-Check + Retry, meldet `failed[]`. Manifest = `{fps, formats:["16x9"], entries:[{id, atSeconds, hold, files:{"16x9":<mov>}}]}`. Ticks = `atSeconds·254016000000`.
- `cmd <action> '<json>'` → beliebiger Plugin-Befehl (57+, s. `PREMIERE_API_CAPABILITIES.html`); `label <farbe> <namen…>` → Clip-Label-Farbe (Review/Sortierung, „rot"/„gelb"/…); `remove <names.json> --seq <id>` → Clips per Id-Präfix löschen; `retime <corrections.json> --seq <id>` → Clips auf absolute Ziel-Zeiten ziehen (s. Stufe 9).
- `relink <map.json>` → `[{name,newPath}]` Medien auf dauerhafte Pfade umlinken (gegen `/tmp`-Offline). `reconcile <spec.json> --seq <id>` → **Reserved Tracks leeren + alle Grafiken aus dem Spec neu, kollisionsfrei verteilt platzieren** (idempotent, selbstheilend; Spec aus dem Registry/Audit-Planner: `[{itemName, atSeconds, vtrack, atrack}]`, round-robin über V10–V14). Der EINE Befehl, der einen verkorksten Grafik-Layer wieder in den Soll-Zustand bringt.
- Format passend zur Sequenz-Auflösung; bei 4K/50fps die Overlays mit `render_overlays --uhd --tc-fps 50` rendern.

**Platzierungs-Learnings (2026-06-12, wichtig):**
- **Vor jedem Remove/Place/Retime frisch `info` ziehen** — Simon editiert die Sequenz zwischen den Turns selbst (Clips fehlen evtl.). Fehlt Erwartetes → ihm sagen, nicht still annehmen (Memory `feedback_premiere_live_reverify`). Nach jedem Batch Overlay-Anzahl gegen erwartetes Delta verifizieren.
- **Nicht clobbern:** `place` nutzt Overwrite → auf eine **freie Spur** legen (Belegung der Ziel-Zeit per `info` prüfen). Voll-Frame-Cutaways (Doku-Belege, Folien-Decks) auf eine **eigene Spur OBEN** (z. B. V13 via `--vtrack 12`, auto-erzeugt) — überschreibt nichts, liegt über den Glas-Overlays.
- **`label`-Farbe zum Reviewen:** eingefügte Belege/Folien gelb markieren, damit Simon sie in der Timeline sofort findet und kuratiert.
- Reine Bild-Cutaways (fertige Chart-Folien, schon 4K/16:9) als Voll-Frame-ProRes mit sanftem Zoom + Whoosh bauen (ffmpeg `zoompan`) — **nicht** durch die Remotion-Pipeline.

**Weg B — Fallback** (kein Live-Plugin): `integrate.py` erzeugt Deliverables zum manuellen Import:
```
python3 scripts/integrate.py <vN>/animation-plan.json --video <final_video> \
    --overlays <vN>/overlays/overlays-manifest.json --out <vN>
```
- `placement.md` + `placement.csv`: pro Overlay **HH:MM:SS:FF** (frame-genau), Datei, empfohlene Spur — Simon zieht die .mov-Dateien an die gelisteten Timecodes.
- **Importierbare XML = FCP7-XML/xmeml** via `export_fcp7xml.py <plan> --video <footage> --overlays <manifest> --out <dir> --format 9x16 --clip-fps <render-fps>` → `overlays.fcp7.xml` (Footage auf V1 + jede Animation als eigener, verschiebbarer Clip auf Grafik-Spuren). **Trägt Audio** (Footage-Voiceover auf A1 + Overlay-SFX auf gespiegelten Audio-Spuren, `<media><audio>` + `<sourcetrack><mediatype>audio`), Video+Audio per `<link>` verbunden (zusammen verschiebbar). OHNE das kommen die Clips stumm rein (SFX/VO „weg" — 2026-06-15). **NIE FCPXML** (`.fcpxml`, FCPX-Format) — Premiere kann die nicht öffnen; `write_fcpxml` in `integrate.py` ist deaktiviert ([[feedback_no_fcpxml]]). Footage + `.mov`-Clips in DENSELBEN Ordner legen (XML referenziert per absolutem `pathurl`), mit `xmllint --noout` prüfen. Daneben bleibt `placement.md` (manuelles Ziehen) als Backup.

### Stufe 6 — QC (`scripts/qc.py` + Claude)

`python3 scripts/qc.py <vN>/animation-plan.json --fps 30 --out <vN>/qc-checklist.md`
erzeugt eine Checkliste mit Prüf-Timecode (`atSeconds + hold/2`) pro Eintrag.

**QC-3 Visual-Reviewer (deterministisch, `scripts/qc_visual.py`):** fängt „sieht-schlecht-aus/Bug"-Fälle vor der Auslieferung ab — `python3 scripts/qc_visual.py <plan> --format 16x9`:
- **Kollisionen:** zwei Animationen, die sich zeitlich UND örtlich überlappen (Box pro Typ; z. B. Keyword-Pop + Lower-Third gleichzeitig unten-links). Exit-Code 1 bei Treffern.
- **Lange Texte** (Überlauf-Verdacht; `reveal` umbricht und ist meist ok), **Peak gleichzeitig sichtbarer Overlays** (Default-Limit 3).
Produktions-Schleife: QC-3 findet → Plan fixen → `render_overlays --skip-existing` rendert dank Content-Hash nur die geänderten Clips → QC-3 bestätigt.

- **Live-Weg:** Claude exportiert je Eintrag `get_sequence_frame_image(atSeconds + hold/2)` und prüft per Vision: Overlay sichtbar? Zahl **exakt** wie im Plan (nicht verfälscht)? keine Kollision mit bestehenden Bauchbinden/Captions im Schnitt? Fehler → Timecode-/Spur-Korrektur vorschlagen und erneut platzieren.
- **Fallback-Weg:** `qc-checklist.md` als manuelle Sicht-Checkliste.

---

### Stufe 7 — Re-Sync (`scripts/resync.py`) — wenn sich der Schnitt nachträglich verschiebt
Absolute Timecodes brechen, wenn Material rein/raus kommt. Weil jede Animation an ihre **`anchorPhrase`** geankert ist (nicht an absolute Zeit), ist das reparierbar **ohne Neu-Rendern**:
- **B-Roll/Cutaways über bestehendem Ton** verschieben nichts (Ton = Anker bleibt) → nichts zu tun.
- **Ripple-Edits, die den Ton bewegen:** neue Sequenz exportieren → `premiere_transcript.py`/`align_words.py` → neue `words.json`, dann:
  ```
  python3 scripts/resync.py <vN>/animation-plan.json --words <new.words.json> \
      --overlays <vN>/overlays --fps 30
  ```
  Re-berechnet jeden `atSeconds` aus `anchorPhrase` (+ `anchorOffset`), **benennt die Overlay-`.mov` auf den neuen Timecode um**, baut das Manifest neu, schreibt `*.resynced.json`. Anker, deren Text rausgeschnitten wurde, werden als **LOST** gemeldet (bleiben liegen, nie still falsch platziert).
- **`--infer-shift`**: wenn die gefundenen Anker alle um ~denselben Betrag wandern (ein zusammenhängender Block wurde gleichmäßig verschoben), wird dieser Block-Versatz auf LOST/anchorlose Einträge angewandt (Status `inferred`). Rettet Treffer, die ein schnelles Whisper-Modell bei zahllastigen Phrasen verfehlt. Nur bei geringer Streuung der Treffer aktiv.
- Danach neu platzieren: live via adb-mcp (SUB-Spur leeren + an den neuen `ticks` neu einsetzen) oder `integrate.py` erneut laufen lassen.

### Stufe 8 — Nachträglicher Swap (Text/Animation austauschen)
Einzelne Elemente ändern, ohne alles neu zu rendern — automatisch über Content-Hash:
1. Im `animation-plan.json` den **Inhalt** des Eintrags ändern (Text/Wert/Typ/Steps). Bei NEUEN Einträgen Anker geben: `build_plan.py --backfill`/`--resolve`.
2. `python3 scripts/render_overlays.py <plan> … --skip-existing` → es rendert **nur die geänderten** Clips neu (Hash-Vergleich in `.render-hashes.json`); unveränderte werden übersprungen. `--force` = alles, `--only id1,id2` = gezielt.
3. Position unverändert (`atSeconds` gleich) → der Clip wird **dateigleich überschrieben**; in Premiere nur Medien aktualisieren/neu importieren. Position geändert → `resync.py` (Stufe 7) benennt um + re-platziert.
4. Platzierungs-Bundle neu: `integrate.py …` regeneriert `placement`/`fcpxml` aus dem frischen Manifest.
- **Live-Weg (adb-mcp) Vorsicht:** `add_media_to_sequence` ist additiv (`overwrite=false`) — beim Live-Tausch erst den alten Clip auf der SUB-Spur entfernen (deterministischer Name `sub__<id>`), dann neu setzen, sonst stapelt es. (Fallback fcpxml/placement ersetzt sauber.)

### Stufe 9 — Timing-Audit & Retime (PFLICHT nach Live-Platzierung, 2026-06-12)
Nach dem Platzieren prüfen, ob **jede Animation auf ihrer gesprochenen Stelle** sitzt — Ground Truth = `anchorPhrase`, nicht die geplante `atSeconds` (frühere Re-Syncs/Infer-Shift können ganze Blöcke um zig Sekunden verschieben; auch eigene atSeconds-Tippfehler).
1. **Audit:** für jeden platzierten Clip (Id aus Clip-Name) den Anker per `common.find_anchor_seconds(anchor, words)` auflösen, gegen die IST-Position aus `info` vergleichen. `count_anchor_matches>1` = **mehrdeutig** (nicht auto-verschieben, manuell prüfen); `None` = Anker getrimmt neu auflösen. Flaggen `|delta|>3 s`.
   - Echte Fälle: ein ganzer Sequenz-07-Block lag systematisch **−70 s** (Re-Sync-Versatz daneben) → im Audit als Cluster gleicher Deltas sofort sichtbar.
2. **Retime:** Korrektur-Liste `[{name, target}]` (target = Anker − 0,4 s Lead) → `node premiere_drive.js retime <corr.json> --seq <id>`. Der Treiber holt **vor jeder Bewegung frisch `info`** (Indizes verschieben sich nach jedem Move) und zieht den Clip per `moveClip`.
3. **Folgeschäden beachten:** In-Place-Moves auf einer **dichten** Timeline lösen **Collision-Bumps** aus (Premiere schiebt kollidierende Clips auf Nachbar-/Footage-Spuren → werden unsichtbar). Darum NACH dem Retime erneut:
   - **Kollisionen scannen** (gleiche Spur, zeitliche Überlappung) — die korrigierten Originale landen oft genau dort, wo man (in der Annahme einer Lücke) **innere Füll-Animationen** erstellt hatte → die **redundante entfernen** (`remove`).
   - **weggebumpte Clips** (auf falscher Spur/Zeit) **neu auf eine freie Spur platzieren** (`place`, kein In-Place-Move).
4. **Re-Audit + Kollisions-Scan**, bis: alle ≤3 s vom Anker, 0 Kollisionen. Einheit prüfen (Sekunden! 03:59 = 239 s, nicht 1439).

### Placement-Registry + Reserved Tracks + Reconcile (SYSTEM-DISZIPLIN, 2026-06-12)
Damit nichts mehr unkontrolliert wandert/vergraben wird, ist die **Grafik-Spur eine reproduzierbare Funktion der Registry** — nicht eine ad-hoc editierte Live-Spur. Drei Regeln:
1. **Registry = einzige Wahrheit** (`scripts/audit_placements.py` → `placement-registry.json` im Projektordner): pro Animation `id · typ · anchorPhrase · soll-Zeit · ist-Zeit · spur · datei · status`. Nach JEDER Operation (place/move/remove/relink) **neu schreiben**; sie ist der kanonische „welche Animation ist wo"-Stand. `ok/DRIFTED/MISSING/AMBIGUOUS/NO-ANCHOR`.
2. **Reserved Tracks (V10–V15 nur Grafiken), Footage NIE berühren.** Grafiken IMMER auf das hohe Band legen — nie auf V1–V9. Sonst bumpt eine Kollision die Grafik unter das Video (= unsichtbar/„kann ich nicht löschen"). Footage-Spuren idealerweise sperren. **Density spreizen** (nicht 124 Clips auf V10 — auf mehrere Reserved Tracks verteilen, sonst hauchdünn + Kollisions-Bumps).
3. **Reconcile statt In-Place-Editieren.** Bei Drift/Vergraben NICHT einzeln per `moveClip` herumschieben (bumpt Nachbarn). Stattdessen: Reserved Tracks leeren → **die ganze Grafik-Spur aus der Registry/dem Plan neu ableiten** (jede Animation an ihre Anker-Zeit, kollisionsfrei greedy über das Band verteilt, per `place`). **Idempotent + selbstheilend** — egal wie verkorkst der Live-Stand, ein Reconcile stellt den Soll-Zustand her. Danach Registry neu schreiben + Audit grün.
- **Medien permanent** (nie `/tmp` → s. Stolpersteine): Registry-`file` zeigt auf den dauerhaften Ordner; `relink` repariert Pfade. So bleiben Clips online (kein Offline-Flackern, das wie „Versatz" aussieht).

### Stufe 2c — Sprecher-bewusste Platzierung (`face_zones.py`, 2026-06-12)
Damit kein Overlay übers Gesicht liegt — auch bei Kamerafahrten/Multicam/wiederkehrenden Shots. Läuft NACH Anker-Resolve, VOR Render (Position wird gebacken). `face_zones.py <plan> --video <final> --format 16x9 --style conservative|best --cluster`: sampelt Frames über das Animations-Fenster, erkennt Gesichter (opencv DNN res10 → Haar-Fallback, Modelle in `scripts/models/`), bildet die **Union-Envelope** aller Boxen (deckt Bewegung + mehrere Gesichter), wählt die freie **Zone** (3×3-Raster, konventionelle Präferenz je Typ) und schreibt `entry.placement {zone,faceBox,confidence,constrained,split,bypass}`. Remotion: `Overlay.tsx` wrappt die Komponente in eine **positionierte Zonen-Box** (ihr `position:absolute` löst dann relativ zur Safe-Zone auf — KEIN Per-Komponente-Edit), Scrim folgt der Zone (`placement.ts`/`scrimForZone`). `render_overlays` reicht `placement` in die Props → im Content-Hash → Zonen-Änderung rendert genau 1 Clip neu. **In `pipeline.py` als Stufe 2c automatisch** (wenn `--video`); `constrained`/`split` werden geflaggt (Gesicht füllt Bild / Mid-Clip-Cut → Eintrag splitten). Kein Gesicht/B-Roll → konventioneller Bottom-Strap. Selftest: `face_zones.py --selftest`.

### TIMECODE-RECHECK = PFLICHT nach JEDER Änderung (Simon 2026-06-12)
**Nie darf eine Animation auf einem alten Timecode hängenbleiben.** Regel: Nach JEDER Änderung (Plan-Edit, Schnittänderung, Resync, Platzierung, Move, Remove, Reconcile, face_zones-Neulauf) **Timecodes neu aus `anchorPhrase` ableiten** (`build_plan --resolve`, macht `pipeline.py` jeden Lauf) UND **`audit_placements.py` neu laufen** (Registry → IST vs. gesprochener Anker; Drift/MISSING fangen) → bei Drift `reconcile`. Render baut nur aus frisch-resolved Timecodes; live wird nach jeder Operation auditiert (Stufe 9). So entstehen keine Grafiken aus veralteten Timecodes.

### Sound automatisch + Musik-Option (2026-06-12)
- **Sound ist jetzt Pipeline-Gate** (nicht mehr manuell): nach Render `add_sfx.py` (typ-gemappter SFX in jede `.mov`, **−16 dB** — −25 dB war unter dem ~−6 dB-Voiceover UNHÖRBAR, Simon 2026-06-15) → `qc_audio.py` (ffprobe je Clip: Audio-Stream da? Peak ≥ −45 dB? sonst exit 1) → keine stummen Grafiken mehr. `--no-sfx` schaltet ab. **WICHTIG: nach JEDEM Render `add_sfx` auf das GANZE Manifest laufen (nie `--only`)** — `render_overlays --only` filtert NICHT (rendert immer ALLE Overlays clean=ohne Audio neu), sonst landen die nicht-ge-sfx-ten Overlays stumm im Video. `qc_audio.py` als Gate fängt −inf-Clips. Sowohl `flatten_final` (amix, `normalize=0`) als auch die FCP7-XML tragen das Audio.
- **Musik (`add_music.py`, OPT-IN, nie Default):** backt ein geducktes Musik-Bett unter die Stimme eines FERTIGEN Videos — `add_music.py <video> --music <bed> --out <out> [--gain -20] [--duck 6] [--fade 2]` (Sidechain-Ducking: Musik fällt unter Sprache, hebt in Pausen, Loop+Fade). Läuft auf dem finalen Video (z. B. nach `flatten_final.py`), nicht im Overlay-Lauf.

### Reel-Modus (9:16, 2026-06-12)
Derselbe Skill macht auch **Reels**: Overlays in 9:16 (`--format 9x16`, alle Komponenten haben 9:16-Anker + die gesichts-bewusste Platzierung gilt auch hier) PLUS automatische **Video-Bewegung**: `scripts/reel_dynamics.py <video.9x16> --out <out>` legt einen kontinuierlichen langsamen **Zoom rein/raus** (Sinus-Breathing) + **ab und zu einen Jump-Cut** (harter Zoom-Sprung) aufs Footage — per `zoompan`, KEINE Frames entfernt → Audio bleibt synchron. Tunbar: `--zoom 0.05` (Breathing-Amplitude), `--period 16` (In→Out-Zyklus s), `--jump 12` (s zwischen Jump-Cuts, 0=aus), `--jump-amt 0.07` (Sprung-Stärke). **Empfohlene Reihenfolge:** reel_dynamics aufs Roh-9:16 → `face_zones.py` auf das GEZOOMTE Video (Gesicht sitzt dann an der richtigen Stelle) → Overlays rendern (9:16) → `flatten_final.py` compositet drüber → optional `add_music.py`. Yap-/Insta-Look beachten ([[feedback_yap_hookbar_lowercase]]); Captions nur wenn explizit gewünscht (Simon: meist KEINE, [[feedback_video_editing_standard]]).

## Planungs-Playbook (FESTE Reihenfolge — „viel steckt in der Planung")
So entstehen mehr und bessere Animationen, ohne dass etwas durchrutscht:
1. **Transkript** holen (`premiere_transcript.py` / `transcribe_long.py`) → words.json.
2. **Transkript-Kontrolle** (`qc_transcript.py words.json`): Whisper-Fehler erkennen, bevor sie sich fortpflanzen.
3. **Chancen extrahieren** (`build_plan.py words.json --suggest`): listet ALLE animierbaren Stellen (Zahlen, **Aufzählungen**, Vergleiche) mit Timecode + Kontext → `suggestions.md`. Das ist die Bau-Checkliste.
4. **Animationen herausschreiben** (Claude autoriert den Plan): pro starker Stelle ein Eintrag mit `anchorPhrase` + Inhalt; Typ passend (Zahl→stat/kpibig, Aufzählung→sequence/enumeration, Vergleich→comparebars, Schlüssel-Aussage→reveal, Name→lowerthird).
5. **Vollständigkeits-Kritik** (`build_plan.py words.json --coverage plan.json`): meldet erkannte Stellen — v. a. **Aufzählungen/Listen/Facts** — die der Plan NICHT abbildet. Exit 1 wenn Aufzählungen/Vergleiche fehlen → zurück zu Schritt 4, ergänzen. Schleife bis 0 starke Lücken.
6. **Rechtschreib-Check** (`qc_spell.py plan.json`): Namen/Begriffe korrekt? + Review-Export.
7. **Visual + Dichte** (`qc_visual.py`, `--gapcheck`): Kollisionen, Überlauf, 15-s-Regel.
8. **Erst dann erstellen:** `render_overlays.py --skip-existing` → `integrate.py`/`export_fcp7xml.py`.
`pipeline.py` fährt 2/5/6/7/8 automatisch; Schritte 4 (Autorieren) + die „sind es die besten?"-Beurteilung macht Claude.

## Produktion: QC-Gates + Orchestrator + Batch
Für „immer guter Output, keine unnötigen Revisionen" laufen drei QC-Wächter; der Orchestrator kettet alles.
- **QC-1 Transkript** (`qc_transcript.py <words.json> --plan <plan>`): markiert wahrscheinliche Whisper-Fehler (Blocklist + Muster) und ob sie **on-screen** im Plan landen (MUST-FIX).
- **QC-2 Rechtschreibung** (`qc_spell.py <plan>`): hart geflaggte Tokens (Whisper-Garbles, verschmolzene Wörter) + Review-Export aller Texte; Allowlist für Marken/Produkte (ProLife, iPhone, GmbH …). Zahlen werden nicht geflaggt.
- **QC-3 Visual** (`qc_visual.py <plan>`): Kollisionen (Zeit×Position), Überlauf-Verdacht, Peak-Dichte.
- **Gemeinsame Heuristik** in `qc_spell.token_flag` (Ziffern raus, 4+ statt 3+ Wiederholung, Binnen-Großbuchstabe erst ab 2). Neue Garbles in `BLOCKLIST`/`ALLOWLIST` ergänzen.

**Ein-Befehl-Lauf pro Video** (`pipeline.py`): words (premiere_transcript/transcribe_long) → `--resolve` Timecodes → QC-1/2/3 + gapcheck → `render_overlays --skip-existing` → `integrate`. `--strict` = Stopp bei QC-Verletzung. Creative-Plan-Authoring macht Claude vorab (Plan mit `anchorPhrase`), `--plan` übergeben.

**Mehrere Videos** (`batch.py --jobs jobs.json [--parallel N]`): fährt `pipeline.py` je Job (eigener Ordner) parallel/sequenziell, Status-Tabelle. Jeder Job: `{plan, out, transcript|words|video, brand, format, fps}`.

## Batch-Workflow (beide Formate gleichzeitig, je Video justierbar)
`jobs.json` mischt 16:9- und 9:16-Videos in EINER Liste — viele Videos auf einmal, jedes einzeln justierbar und re-runnbar. `batch.py` mappt jeden Job-Key auf `pipeline.py`-Flags und hält die Jobs unabhängig (eigener `out`-Ordner).

```
python3 scripts/batch.py --jobs jobs.json [--parallel N] [--strict] [--only name1,name2]
```

- **Format-Defaults:** 16:9 → `deliver=premiere` (Placement/FCPXML, kein Flatten). 9:16 → automatisch `reel=true` + `deliver=flat` (composited fertiges mp4). Beide pro Video übersteuerbar.
- **Reel-Reihenfolge** (wenn `reel` + `video`): `reel_dynamics.py` aufs Video → "dynamic" mp4; dann nutzen `face_zones.py` + Flatten DIESES gezoomte mp4 (Gesicht sitzt auf dem gezoomten Frame). Bei `deliver=flat`: nach Render + SFX `flatten_final.py` → finales mp4; bei `music` danach `add_music.py` (OPT-IN, nie Default).
- **Selektiver Re-Run:** `--only name1,name2` fährt nur diese Videos erneut — idempotent, weil `render_overlays --skip-existing` je Clip hasht. So justierst du ein einzelnes Video (Text-Swap, Timecode-Nudge, `reelZoom`) ohne die anderen anzufassen.
- **Status-Registry:** `batch.py` schreibt `batch-status.json` neben `--jobs` — pro Job `{name, status: ok|fail, format, out, deliverable}`.
- Vorhandene Scripts werden as-is wiederverwendet (`reel_dynamics.py`, `add_music.py`, `flatten_final.py`, `face_zones.py`, `render_overlays.py`, `integrate.py`) — nicht neu bauen.

Volles Job-Schema + 6-Video-Beispiel (16:9 + 9:16 gemischt): `references/batch-jobs.md`. Kopiervorlage (2 Jobs): `references/jobs.example.json`.

## Bausteine (alle im Kit enthalten)
- `scripts/_whisper.py` — Probe (ffprobe) + Whisper word-level (Stufe 1). Self-contained.
- `remotion/src/` — alle Overlay-Komponenten (Stufe 4).
- `../vendor/adb-mcp/` — Live-Premiere-Bridge: `premiere_drive.js` + UXP-Plugin + Socket-Proxy (Stufe 1/5/6).
- `scripts/common.py` — Anker-/Timecode-Logik **in Sekunden** (der Cut ist final, kein Keep-Range-Remap nötig).

## Selftests
```
python3 scripts/common.py --selftest
python3 scripts/build_plan.py --selftest
cd remotion && npx tsc --noEmit
```

## Bekannte Stolpersteine
- adb-mcp braucht einmaliges UXP-Plugin-Sideload in Premiere (siehe `../docs/LIVE-PREMIERE-SETUP.md`) → der Fallback-Weg (FCP7-XML/placement.md) ist gleichwertig und immer nutzbar, auch ohne Live-Plugin.
- ProRes 4444 ist groß; bei sehr vielen Overlays `render_overlays.py --png` (Alpha-PNG statt .mov) als leichtere Alternative.
- Remotion lädt beim ersten Render headless-Chromium von `storage.googleapis.com`. Wenn das blockt/hängt: `render_overlays.py --browser-executable <pfad>` auf eine vorhandene Shell zeigen, z. B. `~/.cache/puppeteer/chrome-headless-shell/mac_arm-*/chrome-headless-shell-mac-arm64/chrome-headless-shell` oder eine Playwright-Chromium (`~/Library/Caches/ms-playwright/chromium_headless_shell-*/…/chrome-headless-shell`).
- Whisper-`large-v3` braucht beim ersten Lauf Download/Zeit; `--model medium` für schnellere Drafts.
- **Mehrdeutige `anchorPhrase`** (>1× im Transkript) → `find_anchor_seconds` nimmt das ERSTE Vorkommen → falsch platziert. Anker lang + eindeutig genau am Schlüsselwort setzen; im Audit (Stufe 9) `count_anchor_matches>1` ist ein Warnsignal.
- **In-Place-Moves (`moveClip`/`retime`) bumpen auf dichter Timeline** kollidierende Nachbarn weg (auch auf Footage-Spuren = unsichtbar) → nach jedem Retime Kollisions-Scan + ggf. weggebumpte Clips neu platzieren (Stufe 9).
- **Doku-Belege (Policenvergleich, Tabellen) NIE als Screenshot/Bild-Zoom** einbauen — nativ als `comparetable` nachbauen, Zeilen am Transkript getaktet (`revealAt`), Werte 1:1 aus dem Beleg (Simon-Regel 2026-06-12). Fertige Chart-/Statistik-**Folien-Decks** (schon gebrandet, 4K) dürfen als Voll-Frame-Bild-Cutaway rein (eigene Spur oben, gelb labeln).
- **NIE Live-Clips aus `/tmp` sourcen** (2026-06-12, kostete Stunden): macOS leert `/tmp` → alle Clips werden „Media Offline" = flackern/verschwinden in der Timeline, je nach Zoom mal sichtbar mal nicht. Render-/Cutaway-Quellen IMMER in einen **dauerhaften Projekt-Ordner** (`~/Desktop/SubAnimations/<v>/overlays_final/`) legen ODER nach dem Platzieren dorthin kopieren + `node premiere_drive.js relink <map.json>` (ruft `relinkMedia`/`changeMediaFilePath` je Clip). Pfade per `cmd getProjectItemInfo` prüfen.
- **Nicht alles auf EINE Overlay-Spur packen:** 124 Clips auf V10 = bei den meisten Zoomstufen hauchdünn, kaum anklickbar/löschbar. Auf **mehrere Spuren verteilen** (z. B. je ~30–40), `label`-Farben zum Unterscheiden. Spur-Wechsel geht nur per `remove`+`place` (moveClip kann die Spur nicht ändern).
- **Re-Render-Swap = NEUE Dateinamen erzwingen** (2026-06-13, kostete eine Stunde): Wird ein Overlay neu gerendert und unter **demselben Pfad/Dateinamen** abgelegt, dann `clear`+`place`, reused Premiere das **alte gecachte Project-Item** (alter Inhalt + alte Dauer, z. B. 3,8 s statt 6 s) — der neue Clip erscheint gar nicht/falsch. Beim Ersetzen platzierter Overlays die neuen Medien in **eindeutig benannte/versionierte Dateien** kopieren (`<id>_vis.mov`, eigener `overlays_vis/`-Ordner) → frischer Import. Verifizieren: nach `place` `durationSeconds` je Clip gegen den Plan-`hold` prüfen (Feld heißt `startTimeTicks`/`durationSeconds`, NICHT `start`).
