# Part 1 — Dropbox-Watcher

Erkennt neue Uploads in Dropbox, bündelt sie zu **Jobs** (ein Dreh = Video +
evtl. Skript + evtl. Transkript), wartet bis der Ordner **durchsynct** ist,
ordnet den **Berater** zu und übergibt den Job an die nächste Stufe.

Part 1 kennt ClickUp bewusst **nicht**. Er liefert ein stabiles Job-JSON ab —
Part 2 (ClickUp-Intake), Part 3 (Transkript), Part 4 (Vorschnitt) hängen sich
daran, ohne dass der Watcher sich ändert.

```
Dropbox ──longpoll──► dbx_watch.py ──► Job-JSON ──► queue/*.json
                                              ├──► Hook-Befehl   (Part 2)
                                              └──► Webhook-POST  (n8n/Make)
```

---

## 1. Warum Dropbox-API statt Ordner-Überwachung

| | lokaler Ordner (`fswatch`) | **Dropbox-API (hier gebaut)** |
|---|---|---|
| Rechner muss laufen | ja, mit Dropbox-App + Sync | nein (läuft auch auf Server/NAS) |
| Teil-Uploads | sichtbar (halbe Dateien) | **unsichtbar** — die API zeigt nur fertige Dateien |
| „ist alles synct?" | Heuristik auf Dateigröße | Ruhephase auf Server-Zeitstempel |
| Reaktion | sofort | Sekunden (Longpoll, kein Polling) |
| Dedupe nach Neustart | selbst bauen | `rev` + `content_hash` + Delta-Cursor |

Das ist der Hebel: **eine über die API sichtbare Datei ist garantiert komplett.**
Offen bleibt nur, ob noch *weitere* Dateien zum selben Upload kommen — dafür die
Ruhephase (`quiet_seconds`, Default 180s ohne Änderung im Ordner).

## 2. Voraussetzungen

Python ≥ 3.10. **Keine Pakete** — alles Stdlib (`urllib`). Kein `pip install`,
keine venv nötig.

## 3. Setup (5 Minuten)

```bash
cd watcher
cp config.example.json config.json
python3 dbx_watch.py auth        # führt durch App-Anlage + PKCE-Login
```

`auth` erklärt die Dropbox-App-Anlage Schritt für Schritt. Kurzfassung:

1. https://www.dropbox.com/developers/apps → **Create app**
2. *Scoped access* + **Full Dropbox** (oder *App folder*, dann liegt der
   Watch-Pfad in diesem App-Ordner)
3. Tab **Permissions** → `files.metadata.read`, `files.content.read` → *Submit*
4. Tab **Settings** → **App key** kopieren → in `auth` einfügen
5. Link öffnen, Zugriff erlauben, Code zurück in das Terminal

Der **Refresh-Token** landet in `config.json` (chmod 600, gitignored) und läuft
nicht ab. Alternativ per ENV: `DROPBOX_APP_KEY`, `DROPBOX_REFRESH_TOKEN`,
`DROPBOX_TEAM_MEMBER_ID`, `DROPBOX_PATH_ROOT` (ENV gewinnt gegen Config).

Dann `config.json` anpassen:

```jsonc
"dropbox": { "watch_path": "/Video Upload" },      // wo die Berater hochladen
"watch":   { "quiet_seconds": 180, "job_depth": 2 },
"consultants": [                                    // Berater -> ClickUp-Ziel
  { "id": "robert",       "name": "Robert",       "path": "/Video Upload/Robert" },
  { "id": "tom",          "name": "Tom",          "path": "/Video Upload/Tom" },
  { "id": "jonas-dorsch", "name": "Jonas Dorsch", "path": "/Video Upload/Jonas Dorsch",
    "aliases": ["Jonas", "Dorsch"],
    "clickup": { "space_id": "90124915942", "folder_id": "90127251518", "list_id": "" } }
]
```

Prüfen:

```bash
python3 dbx_watch.py doctor      # Token, Pfad, Dateien, Berater-Zuordnung
```

`doctor` listet auch alle Ordner **ohne** Berater-Treffer — damit ist die
Zuordnung vor dem ersten Lauf sauber.

## 4. Betrieb

```bash
python3 dbx_watch.py scan                 # Bestand einlesen, reife Jobs ausspielen
python3 dbx_watch.py scan --dry-run       # erst mal nur zeigen
python3 dbx_watch.py watch                # Dauerbetrieb (Longpoll)
python3 dbx_watch.py status               # was wartet, was ist raus
python3 dbx_watch.py forget "/Video Upload/Robert/Reel 014"   # neu ausspielen
python3 dbx_watch.py selftest             # komplette Logik offline (kein Netz)
```

**Erster Lauf = Backfill.** `scan` spielt den gesamten Bestand einmal aus
(„erst alles synchronisieren, dann alles in ClickUp laden"). Bei sehr großem
Altbestand: `"backfill_on_first_run": false` → der Bestand wird nur als bekannt
markiert, ausgespielt wird erst, was danach neu kommt.

Dauerbetrieb als Hintergrunddienst: `install/` enthält Vorlagen für
**launchd** (macOS) und **systemd** (Linux/NAS) — siehe `install/README.md`.

## 5. Was ein Job enthält

Eine Datei pro Job in `queue/<ts>-<job_id>-r<rev>.json`, dazu eine Zeile in
`events.jsonl`. Schema `autoedit.dropbox.job/1`:

| Feld | Bedeutung für Part 2 |
|---|---|
| `job_id`, `revision` | stabile Idempotenz-Keys → ClickUp-Task finden statt doppelt anlegen |
| `folder.path` / `.relative` | Dropbox-Ordner = eine ClickUp-Task |
| `consultant.id` / `.clickup` | Ziel-Liste/Space; `needs_triage: true` → Zwischenordner |
| `video`, `videos` | Hauptvideo (größte Datei) + alle weiteren |
| `assets.{transcript,script,pdf,text,audio,image,project,other}` | alle Begleitdateien, klassifiziert |
| `analysis.transcript_status` | `present` / `script_only` / `missing` |
| `analysis.needs_transcription` | **true → Part 3 muss transkribieren** |
| `analysis.script_confidence` | `high` / `medium` / `low` / `none` (Text+PDF-Regel) |
| `sync.*` | Ruhephase, Server-Zeitstempel — Nachweis „Ordner war fertig" |
| `fingerprint` | Hash über (Pfad, rev) → ändert sich bei jeder neuen Datei |
| `previous.new_files` | bei `revision > 1`: was seit dem letzten Mal dazukam |

### Transkript- vs. Skript-Erkennung

- **Transkript** = `.srt` / `.vtt` / `words.json` oder Name enthält
  `transkript`/`transcript`/`untertitel`/… → `transcript_status: present`,
  Part 3 überspringt die Transkription.
- **Skript** (das gesprochene Wort): Regel aus dem Briefing — *Text + PDF im
  selben Ordner ⇒ sehr wahrscheinlich das Skript.* Gleicher Dateistamm oder
  explizit `Skript`/`Drehbuch` im Namen → `high`, nur Text+PDF ohne
  Namensgleichheit → `medium`.
- Ein Skript ersetzt **kein** Transkript (keine Timecodes), setzt aber
  `transcript_status: script_only` — Part 3 kann das Skript als
  Schreibweisen-Referenz für Whisper nutzen (siehe `skill/SKILL.md`, Stufe 1).

### Berater-Zuordnung

Reihenfolge: `path`-Prefix → exaktes Pfadsegment (Alias/Slug, umlaut- und
schreibweisentolerant) → Alias als **ganzes Wort** im Pfad → **Triage**. Kein
Treffer heißt nie „verworfen": der Job geht mit `needs_triage: true` an den
Zwischenordner.

Wortgrenzen sind bei kurzen Namen entscheidend: `Tom` trifft
`/Video Upload/Reels Tom Oktober/`, aber **nicht** `/Video Upload/Automation/`.
Dateistämme sind egal — zugeordnet wird immer über den Ordnerpfad.

## 6. Anschluss von Part 2

Drei Wege, beliebig kombinierbar:

```jsonc
"output": {
  "hook_command": "/usr/bin/python3 /pfad/clickup_intake.py",  // $1 = Job-Datei, Job auch auf stdin
  "webhook_url": "https://n8n.example.com/webhook/autoedit",   // POST des Job-JSON
  "webhook_secret": "..."                                      // Header X-Autoedit-Secret
}
```

Der Hook bekommt zusätzlich `AUTOEDIT_JOB_FILE`, `AUTOEDIT_JOB_ID`,
`AUTOEDIT_JOB_REVISION`, `AUTOEDIT_CONSULTANT_ID`, `AUTOEDIT_FOLDER` als ENV.
Ohne Hook bleibt die Queue liegen — Part 2 kann sie auch im Pull-Verfahren
abarbeiten (Dateien sind atomar geschrieben, also immer vollständig).

Exit-Code ≠ 0 des Hooks wird geloggt, der Job bleibt als ausgespielt vermerkt.
Zum Nachfahren: `dbx_watch.py forget <ordner>` und `scan`.

## 7. Testen ohne Dropbox

```bash
python3 dbx_watch.py selftest                       # 100+ Checks, kein Netz
python3 dbx_watch.py simulate examples/fixture.example.json --now 2026-10-13T12:00:00Z
python3 dbx_watch.py simulate examples/fixture.example.json --print-job
```

`simulate` nimmt eine Liste `{path, size, server_modified}` **oder** eine
rohe `files/list_folder`-Antwort. So lässt sich die eigene Ordnerstruktur
durchspielen, bevor echte Jobs entstehen: `--now` verschiebt die Uhr, mit
`--write` werden Queue/State wirklich geschrieben.

## 8. Aufbau

```
watcher/
├── dbx_watch.py       CLI: auth | doctor | scan | watch | status | simulate | forget | selftest
├── config.example.json
├── lib/
│   ├── classify.py    Dateityp + Berater-Zuordnung        (rein, --selftest)
│   ├── folders.py     Gruppierung, Reifeprüfung, Job-Bau  (rein, --selftest)
│   ├── state.py       Cursor + Ordner-Zustand, atomar     (--selftest)
│   ├── dbx_api.py     Dropbox-API v2 über urllib          (--selftest)
│   └── emit.py        Queue / Event-Log / Hook / Webhook  (--selftest)
├── examples/fixture.example.json
└── install/           launchd- + systemd-Vorlagen
```

## 9. Grenzen (bewusst Part 1)

- **Umbenannte Ordner** sehen wie ein neuer Job aus (neuer Pfad = neuer
  `job_id`). Part 2 kann über `video.content_hash` dedupen.
- **Gelöschte Dateien** lösen keinen Job aus; ein verschwundener Ordner wird
  beim nächsten Durchlauf übersprungen.
- Der Watcher **lädt nichts herunter**. Für Part 2/3 liefert
  `lib/dbx_api.py: temporary_link(path)` einen 4h-Direktlink.
- Nur `files.metadata.read` ist zwingend; `files.content.read` braucht erst
  Part 3 (Download zum Transkribieren).
