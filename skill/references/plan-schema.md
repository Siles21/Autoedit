# animation-plan.json — Schema

Top level:
```json
{ "version": 1, "note": "...", "animations": [ <entry>, ... ] }
```

Each `<entry>`:

| Feld          | Pflicht | Typ     | Bedeutung |
|---------------|---------|---------|-----------|
| `id`          | ja      | string  | eindeutig, z. B. `n1`, `e1`, `r1`, `l1`, `seq1` |
| `type`        | ja      | enum    | `stat` · `enumeration` · `reveal` · `lowerthird` · `sequence` · `kpibig` · `comparebars` · `chart` · `comparetable` · `cta` · `caption` |
| `surface`     | optional | enum   | `solid` (Default) · `glass` (Footage schimmert durch) — für Panel-Typen (comparebars/chart/comparetable/kpibig) |
| `placement`   | auto    | object  | **maschinengeschrieben von `face_zones.py`** — sprecher-bewusste Zone, damit das Overlay NICHT übers Gesicht liegt. `{zone, faceBox{x,y,w,h}, confidence, constrained, split, cutAtSeconds, bypass}` (0..1). Zone ∈ bottom/top/left/right/4 Ecken/center. Nie von Hand setzen; nach Schnittänderung neu laufen lassen. Backdrop/caption → `bypass`. |
| `anchorPhrase`| empfohlen | string | gesprochene Phrase; `common.find_anchor_seconds` mappt sie auf `atSeconds`. **Pflicht für Re-Sync** (`resync.py`) — fehlt sie, `build_plan.py --backfill` füllt sie aus dem Transkript |
| `anchorOffset`| auto    | number  | von `--backfill` gesetzt: Offset (s) zwischen `atSeconds` und dem Ankerwort, damit Re-Sync die exakte relative Lage wiederherstellt |
| `atSeconds`   | ja      | number  | Startzeit auf der **finalen** Timeline (Sekunden, ≥ 0) |
| `hold`        | ja      | number  | Standzeit in Sekunden (> 0, **≤ 10**) |
| `content`     | ja*     | object  | typabhängig (bei `sequence` optional/leer — Inhalt steckt in `steps`) |
| `steps`       | ja bei `sequence` | array | die getakteten Beats, siehe unten |

## Timing-Regeln (vom Validator erzwungen)
- **Max. 10 s** pro Animation (`hold ≤ 10`). **Ausnahme:** `comparetable`/`caption` (`LONG_HOLD_TYPES`) bis **60 s** — Doku-Cutaway/Captions bauen sich über eine ganze gesprochene Passage auf.
- Einzel-Typen (`stat`/`reveal`/`lowerthird`/`enumeration`) dürfen **nicht > 4,5 s** stehen — wird es länger, als `sequence` bauen (Multi-Step).
- In einer `sequence`: erster Beat bei ~0 s, **zwischen Beats max. 2 s** (alle ≤ 2 s ein neues Ereignis), und der **Schwanz** nach dem letzten Beat ≤ 2,5 s (nie statisch).
- Übergeordnet (Schnitt-Ebene, [[feedback_video_event_cadence]]): im Gesamtvideo **alle ≤ 5 s** ein visuelles Ereignis (Cut **oder** Animation **oder** Einblendung) — Overlays füllen die Lücken, die der Schnitt nicht trägt.

`content` je Typ:

- **stat** — `value` (Pflicht, vorformatierter String, z. B. `"4,2 %"`, `"1.200 €"`), `label` (optional, Kontext), `sublabel` (optional). Count-up animiert die erste Zahl in `value` automatisch.
- **enumeration** — `items` (Pflicht, Liste ≥ 2 kurzer Punkte), `label` (optional, Überschrift). Punkte blenden gestaffelt ein.
- **reveal** — `text` (Pflicht, die Auflösung/Kernaussage), `teaser` (optional, gedämmte Andeutung darüber). Blur→Scharf-Reveal; 0,3–0,5 s **vor** den gesprochenen Payoff setzen.
- **lowerthird** — `text` (Pflicht, Titel/Begriff), `sublabel` (optional, Zusatzzeile). Slide-in unten.
- **sequence** — Multi-Step-Panel, das sich nach unten aufbaut. `steps` = Liste von Beats, je `{ at, kind, … }`:
  - `at` (Pflicht, Sekunden ab Animationsstart; aufsteigend, Abstand ≤ 2 s)
  - `kind` (Pflicht): `label` (kleine Akzent-Caps) · `kpi` (große Akzentzahl mit Count-up + optional `sublabel`) · `text` (Zeile, `emphasis:true` = Akzentfarbe) · `bullet` (Punkt mit Bullet)
  - `kpi` braucht `value` (vorformatiert, Count-up auf der ersten Zahl); `label`/`text`/`bullet` brauchen `text`.
  - Einsatz: schnelle Fakten-Folgen (Feature-Listen, Aufzählungen, Recaps, Zusammenfassungen). Für eine **einzelne** Zahl genau im Sprechmoment besser ein synchrones `stat`.
- **kpibig** — `value` (Pflicht, Hero-Zahl), `kicker` (optional, Akzent-Caps oben), `sublabel` (optional). Wipe-Reveal + Count-up + Settle-Glow. `content.backdrop:"black"` = Voll-Frame-Takeover für Hero-Momente.
- **comparebars** — Vorher/Nachher: `before`/`after` (je `{label, value}`, Pflicht), `kicker` (optional). Zwei wachsende Balken, `after` akzentuiert.
- **chart** — `series` (Pflicht, Liste ≥ 2 `{label, value}`), `kicker` (optional). Wachsende Balken, höchster akzentuiert.
- **comparetable** — native 2-Spalten-Vergleichstabelle. `columns` (Pflicht, 3: Label + 2 Datenspalten, z. B. `["Position","Bruttopolice","Nettopolice"]`), `rows` (Pflicht, ≥ 2, je `{label, values:[2], revealAt?, highlight?, advantage?}`), `kicker`/`note` (optional). **`revealAt`** = Sek ab Clip-Start → Zeile poppt im Sprech-Takt (auf gesprochene Zahl legen). `highlight:true` = Ergebniszeile (Akzent-BG), `advantage` = Pill (z. B. `"+11.260 €"`). Zahlen zählen hoch. `surface:"glass"`, `hold` lang (Doku-Cutaway). **Belege so NACHBAUEN, nie Screenshot.**
- **cta** — `text` (Pflicht, Button-Label, z. B. `"Bestandsrechner öffnen"`), `sublabel` (optional, Hinweis, z. B. `"Button unter dem Video"`). Gold-Button unten + pulsende Pfeile nach unten. Nur Sales/Webinar, nicht für organische Reels.

Regeln (NeoCore): **Du-Form**, **keine Emojis**, Werte nicht erfinden — bei NeoCore-Inhalten Remi als Quelle. `value`-Strings auf Deutsch formatieren (Komma-Dezimal, Punkt-Tausender).

Validieren: `python3 scripts/build_plan.py --validate animation-plan.json`
