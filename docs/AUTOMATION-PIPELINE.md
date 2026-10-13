# Video-Automation — Gesamtbild (Part 1 … 5)

Ziel: Ein Berater lädt ein Video in Dropbox. Alles andere passiert von selbst —
bis zum fertig vorgeschnittenen Reel in Premiere, das nur noch abgenommen wird.

```
[1] Dropbox-Watcher      neu? Video? Ordner durchsynct? Welcher Berater?   ✅ gebaut
        │  Job-JSON (queue/*.json | Hook | Webhook)
[2] ClickUp-Intake       Task in der Berater-Liste, Assets verlinkt         ⬜ offen
        │  task_id + Status "Transkript"
[3] Transkript           nur wenn keins da ist (Whisper, word-level)        ⬜ offen
        │  words.json + Volltext in die Task
[4] Vorschnitt           Schnittplan aus Transkript (Hooks, Kürzungen)      ⬜ offen
        │  Freigabe-Gate in ClickUp
[5] Premiere             Reel-Workflow + Sub-Animationen frame-genau        🟡 vorhanden
                         (dieses Repo: skill/SKILL.md)
```

## Part 1 — Dropbox-Watcher (fertig)

→ `watcher/README.md`. Kurz:

- Dropbox-API v2 mit Longpoll statt Ordner-Überwachung — eine über die API
  sichtbare Datei ist **garantiert fertig hochgeladen**.
- Bündelt pro **Ordner** (= ein Dreh) statt pro Datei und gibt erst frei, wenn
  `quiet_seconds` keine Änderung mehr kam → „ganzer Ordner ist synchronisiert".
- Erkennt **Transkript** (`.srt`/`.vtt`/`*transkript*`) und **Skript**
  (Text + PDF im gleichen Ordner) und setzt `needs_transcription`.
- Ordnet den **Berater** aus dem Pfad zu; kein Treffer → `needs_triage: true`
  (Zwischenordner statt Datenverlust).
- Idempotent über `job_id` + `fingerprint` + `revision`: Neustart spielt nichts
  doppelt aus, eine nachgelieferte Datei erzeugt `revision: 2` mit
  `previous.new_files`.

Übergabeformat: `autoedit.dropbox.job/1` (Feldtabelle in `watcher/README.md`).

## Part 2 — ClickUp-Intake (nächster Schritt)

Verbraucht das Job-JSON, legt **eine Task pro Job-Ordner** an:

- Ziel-Liste aus `consultant.clickup.list_id`; bei `needs_triage` in die
  Triage-Liste (`triage.clickup.list_id`) mit Custom Field „Berater?".
- Idempotenz: Custom Field `autoedit_job_id` setzen und vorher danach suchen —
  bei `revision > 1` die bestehende Task updaten (Kommentar mit
  `previous.new_files`) statt eine zweite anzulegen.
- Anhänge/Links: `lib/dbx_api.py: temporary_link(path)` liefert 4h-Direktlinks;
  dauerhaft besser ein Dropbox-Shared-Link pro Datei im Task-Body.
- Status setzen: `needs_transcription: true` → „Transkript offen", sonst direkt
  „Vorschnitt offen".

Anschluss ohne Code-Änderung in Part 1:
`output.hook_command` = das Intake-Script, oder `output.webhook_url` = n8n/Make.

## Part 3 — Transkript

Nur wenn `analysis.transcript_status != "present"`. Whisper liegt in diesem Repo
bereits mit word-level Timecodes vor: `skill/scripts/align_words.py` →
`words.json`. Ein vorhandenes **Skript** (`script_confidence: high|medium`) ist
Schreibweisen-Referenz (Begriffe, Zahlen), **nicht** Timecode-Quelle.

## Part 4 — Vorschnitt

Transkript → Schnittvorschlag (Hook zuerst, Füllwörter/Wiederholungen raus,
Zielbogen der Reel-Strategie). Ergebnis als Freigabe-Gate in ClickUp, danach
Export als Schnittliste/XML.

## Part 5 — Premiere

Bereits im Repo: Reel-Workflow + Sub-Animationen, frame-genau zurück in den
Schnitt — live via `vendor/adb-mcp` oder als FCP7-XML. Siehe `skill/SKILL.md`.
