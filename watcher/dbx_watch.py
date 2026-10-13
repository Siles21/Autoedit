#!/usr/bin/env python3
"""dbx_watch.py — Part 1 der Video-Automation: Dropbox-Überwacher.

Erkennt neue Uploads in Dropbox, bündelt sie zu **Job-Ordnern** (ein Dreh =
Video + evtl. Skript + evtl. Transkript), wartet bis der Ordner *durchsynct*
ist, ordnet den **Berater** aus der Ordnerstruktur zu und übergibt einen
fertigen Job an die nächste Stufe (Queue-Datei / Hook / Webhook → ClickUp).

Kommandos
---------
    python3 dbx_watch.py auth          # einmalig: Dropbox verbinden (PKCE)
    python3 dbx_watch.py doctor        # Config/Token/Pfad prüfen
    python3 dbx_watch.py scan          # Bestand einlesen + reife Jobs ausspielen
    python3 dbx_watch.py watch         # Dauerbetrieb (Longpoll, kein Polling)
    python3 dbx_watch.py status        # was wartet, was ist raus
    python3 dbx_watch.py simulate FIX  # Trockenlauf gegen eine Fixture-Datei
    python3 dbx_watch.py forget PATH   # Ordner vergessen -> wird neu ausgespielt
    python3 dbx_watch.py selftest      # komplette Logik offline testen

Globale Optionen: --config PFAD, --dry-run, --quiet-seconds N, --verbose
"""
from __future__ import annotations

import argparse
import json
import os
import posixpath
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import classify, dbx_api, emit, folders, state as state_mod  # noqa: E402

DEFAULT_CONFIG = HERE / "config.json"
EXAMPLE_CONFIG = HERE / "config.example.json"


# --- Config ----------------------------------------------------------------

def load_config(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise SystemExit(
            f"Keine Config unter {p}.\n"
            f"  cp {EXAMPLE_CONFIG.relative_to(HERE.parent)} {p.name if p.parent == HERE else p}\n"
            f"  dann watch_path + consultants eintragen und `dbx_watch.py auth` laufen lassen."
        )
    cfg = json.loads(p.read_text("utf-8"))
    cfg.setdefault("dropbox", {})
    cfg.setdefault("watch", {})
    cfg.setdefault("output", {})
    cfg.setdefault("consultants", [])
    cfg.setdefault("triage", {"consultant_id": "_triage"})
    out = cfg["output"]
    base = Path(out.get("dir") or HERE)
    out["dir"] = str(base)
    out.setdefault("queue_dir", str(base / "queue"))
    out.setdefault("event_log", str(base / "events.jsonl"))
    out.setdefault("state_file", str(base / "state.json"))
    cfg["_config_path"] = str(p)
    return cfg


def save_config(cfg: dict) -> None:
    p = Path(cfg["_config_path"])
    clean = {k: v for k, v in cfg.items() if not k.startswith("_")}
    p.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(p, 0o600)        # enthält den Refresh-Token


def log(msg: str, *, verbose_only: bool = False, verbose: bool = False) -> None:
    if verbose_only and not verbose:
        return
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


# --- Kern: Jobs bewerten ---------------------------------------------------

def is_ignored_path(path: str, cfg: dict) -> bool:
    low = (path or "").lower()
    for pattern in cfg.get("watch", {}).get("ignore_paths") or []:
        pat = (pattern or "").lower().rstrip("/")
        if pat and (low == pat or low.startswith(pat + "/")):
            return True
    return False


def evaluate(items: list[dict], cfg: dict, st: state_mod.WatchState, *,
             now: datetime | None = None, dry_run: bool = False,
             verbose: bool = False) -> dict:
    """Items -> Jobs gruppieren, reife Jobs ausspielen.

    Rückgabe: {"emitted": [...], "waiting": [...], "skipped": [...]}
    """
    now = now or datetime.now(timezone.utc)
    root = (cfg["dropbox"].get("watch_path") or "").rstrip("/")
    depth = int(cfg["watch"].get("job_depth", 2))
    groups = folders.group_jobs(items, root, depth)
    result: dict[str, list] = {"emitted": [], "waiting": [], "skipped": []}
    limit = int(cfg["watch"].get("max_jobs_per_cycle", 100))

    for job_key in sorted(groups):
        if is_ignored_path(job_key, cfg):
            result["skipped"].append({"folder": job_key, "reason": "ignore_paths"})
            continue
        entries = groups[job_key]
        previous = st.folder(job_key)
        revision = st.next_revision(job_key)
        job = folders.build_job(job_key, entries, cfg, now, revision=revision,
                                previous=previous or None)

        if not folders.job_has_work(job, cfg):
            result["skipped"].append({"folder": job_key, "reason": "kein Video im Ordner"})
            continue

        wanted, reason = st.needs_emit(job_key, job)
        if not wanted:
            result["skipped"].append({"folder": job_key, "reason": "bereits ausgespielt"})
            continue

        if job["status"] != "ready":
            st.note_seen(job_key, job)
            result["waiting"].append({"folder": job_key, "job_id": job["job_id"],
                                      "wait_for_seconds": job["sync"]["wait_for_seconds"],
                                      "files": job["totals"]["files"]})
            log(f"wartet  {job_key} — noch {job['sync']['wait_for_seconds']}s Ruhe nötig",
                verbose_only=True, verbose=verbose)
            continue

        if len(result["emitted"]) >= limit:
            st.note_seen(job_key, job)
            result["waiting"].append({"folder": job_key, "job_id": job["job_id"],
                                      "wait_for_seconds": 0, "reason": "max_jobs_per_cycle"})
            continue

        report = emit.dispatch(job, cfg, reason=reason, dry_run=dry_run)
        if not dry_run:
            st.note_emitted(job_key, job, report.get("queue_file", ""))
        result["emitted"].append({**report, "job": job})
        flags = []
        if job["analysis"]["needs_transcription"]:
            flags.append("Transkript fehlt")
        if job["analysis"]["script_confidence"] in ("high", "medium"):
            flags.append(f"Skript {job['analysis']['script_confidence']}")
        if job["consultant"]["needs_triage"]:
            flags.append("BERATER UNKLAR -> Triage")
        log(f"JOB {'(dry)' if dry_run else '->'} {job['job_id']} r{job['revision']} "
            f"[{job['consultant']['id']}] {job_key} "
            f"({job['analysis']['video_count']} Video(s)"
            + (", " + ", ".join(flags) if flags else "") + ")")
        hook = report.get("hook")
        if hook and not hook.get("ok") and not hook.get("skipped"):
            log(f"  ! Hook-Fehler ({hook.get('code')}): {hook.get('stderr', '')[:300]}")
        wh = report.get("webhook")
        if wh and not wh.get("ok") and not wh.get("skipped"):
            log(f"  ! Webhook-Fehler ({wh.get('status')}): {wh.get('error', '')[:200]}")
    return result


def fetch_folder_items(client, folder_path: str, verbose: bool = False) -> list[dict]:
    """Alle Dateien eines Job-Ordners frisch holen (Geschwister inklusive)."""
    try:
        entries, _ = client.list_folder(folder_path, recursive=True)
        return [dbx_api.entry_to_item(e) for e in entries]
    except dbx_api.DropboxError as exc:
        if exc.status in (409,) and "not_found" in (exc.body or ""):
            log(f"  Ordner verschwunden (gelöscht/umbenannt): {folder_path}",
                verbose_only=True, verbose=verbose)
            return []
        raise


def touched_job_folders(items: list[dict], cfg: dict) -> list[str]:
    root = (cfg["dropbox"].get("watch_path") or "").rstrip("/")
    depth = int(cfg["watch"].get("job_depth", 2))
    seen: list[str] = []
    for key in folders.group_jobs(items, root, depth):
        if key not in seen:
            seen.append(key)
    return seen


def fetch_job_items(client, job_key: str, cfg: dict, verbose: bool = False) -> list[dict]:
    """Vollständigen Dateistand eines Job-Ordners holen.

    Job-Keys sind meist echte Ordner. Für Einzeldateien direkt im Watch-Root ist
    der Key dagegen `<root>/<dateistamm>` — kein Ordner. Darum: Key listen, und
    wenn das nichts liefert, den Elternordner nehmen (dort liegt die Datei).
    """
    root = (cfg["dropbox"].get("watch_path") or "").rstrip("/")
    key = (job_key or root).rstrip("/")
    items = fetch_folder_items(client, key, verbose=verbose)
    if items or key.lower() == root.lower():
        return items
    parent = posixpath.dirname(key)
    if parent.lower() == root.lower():
        return fetch_folder_items(client, parent, verbose=verbose)
    return []        # Ordner gelöscht/umbenannt — nichts nachzuladen


def refresh_items(client, cfg: dict, job_keys: list[str], verbose: bool = False) -> list[dict]:
    """Für die betroffenen Job-Ordner den vollständigen Dateistand holen."""
    uniq: dict[str, dict] = {}
    for key in job_keys:
        for it in fetch_job_items(client, key, cfg, verbose=verbose):
            uniq[(it.get("path") or "").lower()] = it      # Duplikate rauswerfen
    return list(uniq.values())


# --- Kommandos -------------------------------------------------------------

def cmd_auth(args) -> int:
    cfg_path = Path(args.config)
    if not cfg_path.exists():
        if not EXAMPLE_CONFIG.exists():
            raise SystemExit("config.example.json fehlt.")
        cfg_path.write_text(EXAMPLE_CONFIG.read_text("utf-8"), encoding="utf-8")
        print(f"Config aus Vorlage erstellt: {cfg_path}")
    cfg = load_config(cfg_path)
    app_key = args.app_key or cfg["dropbox"].get("app_key") or ""
    if not app_key:
        print("Noch keine App. In 2 Minuten erledigt:")
        print("  1. https://www.dropbox.com/developers/apps -> 'Create app'")
        print("  2. 'Scoped access' + 'Full Dropbox' (oder 'App folder', dann liegt")
        print("     der Watch-Pfad in diesem App-Ordner)")
        print("  3. Tab 'Permissions': files.metadata.read, files.content.read ankreuzen -> Submit")
        print("  4. Tab 'Settings': 'App key' kopieren")
        app_key = input("App key: ").strip()
    if not app_key:
        raise SystemExit("Ohne App key geht nichts.")

    verifier, challenge = dbx_api.pkce_pair()
    url = dbx_api.authorize_url(app_key, challenge)
    print("\nDiesen Link im Browser öffnen, Zugriff erlauben, Code kopieren:\n")
    print(f"  {url}\n")
    code = (args.code or input("Code aus dem Browser: ")).strip()
    if not code:
        raise SystemExit("Kein Code eingegeben.")
    tok = dbx_api.exchange_code(app_key, code, verifier)
    cfg["dropbox"]["app_key"] = app_key
    cfg["dropbox"]["refresh_token"] = tok["refresh_token"]
    cfg["dropbox"].setdefault("account_id", tok.get("account_id", ""))
    save_config(cfg)
    print(f"\nRefresh-Token gespeichert in {cfg_path} (chmod 600).")
    print("Weiter mit:  python3 dbx_watch.py doctor")
    return 0


def cmd_doctor(args) -> int:
    cfg = load_config(args.config)
    problems: list[str] = []
    d = cfg["dropbox"]
    print(f"Config          : {cfg['_config_path']}")
    print(f"Watch-Pfad      : {d.get('watch_path') or '(leer!)'}")
    print(f"Ruhephase       : {cfg['watch'].get('quiet_seconds', 180)}s")
    print(f"Job-Tiefe       : {cfg['watch'].get('job_depth', 2)} Ebene(n) unter dem Watch-Pfad")
    print(f"Berater         : {len(cfg['consultants'])} konfiguriert")
    print(f"Queue           : {cfg['output']['queue_dir']}")
    print(f"Hook            : {cfg['output'].get('hook_command') or '(keiner)'}")
    print(f"Webhook         : {cfg['output'].get('webhook_url') or '(keiner)'}")
    if not d.get("watch_path"):
        problems.append("watch_path fehlt in der Config.")
    if not cfg["consultants"]:
        problems.append("Keine consultants konfiguriert — alles landet im Triage-Ordner.")

    try:
        client = dbx_api.client_from_config(cfg)
        acc = client.account()
        name = (acc.get("name") or {}).get("display_name", "?")
        print(f"\nAccount         : {name} <{acc.get('email', '?')}> "
              f"({(acc.get('account_type') or {}).get('.tag', '?')})")
        if acc.get("team") and not d.get("team_member_id"):
            print("  Hinweis: Business-Account. Für den Team-Space ggf. team_member_id/path_root setzen.")
        entries, _ = client.list_folder(d.get("watch_path", ""), recursive=True)
        items = [dbx_api.entry_to_item(e) for e in entries]
        groups = folders.group_jobs(items, (d.get("watch_path") or "").rstrip("/"),
                                    int(cfg["watch"].get("job_depth", 2)))
        videos = sum(1 for i in items if classify.classify_file(i["name"]) == "video")
        print(f"Dateien im Pfad : {len(items)} ({videos} Video(s)), {len(groups)} Job-Ordner")
        unassigned = [k for k in groups
                      if classify.resolve_consultant(k, cfg["consultants"],
                                                     cfg["triage"].get("consultant_id", "_triage")
                                                     )["matched_by"] == "default"]
        if unassigned:
            print(f"Ohne Berater    : {len(unassigned)} Ordner -> Triage")
            for k in unassigned[:10]:
                print(f"  - {k}")
    except dbx_api.DropboxError as exc:
        problems.append(str(exc))

    print()
    for p in problems:
        print(f"PROBLEM: {p}")
    print("doctor: " + ("alles grün" if not problems else f"{len(problems)} Problem(e)"))
    return 1 if problems else 0


def cmd_scan(args) -> int:
    cfg = load_config(args.config)
    _apply_overrides(cfg, args)
    st = state_mod.WatchState(cfg["output"]["state_file"])
    if args.reset_cursor:
        st.reset_cursor()
    client = dbx_api.client_from_config(cfg)
    st.bump_run()
    first_run = not st.data["folders"] and not st.cursor

    entries, cursor = client.list_folder(cfg["dropbox"].get("watch_path", ""), recursive=True)
    items = [dbx_api.entry_to_item(e) for e in entries]
    log(f"Bestand: {len(items)} Datei(en) unter {cfg['dropbox'].get('watch_path')}")

    if first_run and not cfg["watch"].get("backfill_on_first_run", True):
        # Nur Baseline merken, nichts ausspielen (für Starts mit großem Altbestand).
        now = datetime.now(timezone.utc)
        root = (cfg["dropbox"].get("watch_path") or "").rstrip("/")
        for key, group in folders.group_jobs(items, root, int(cfg["watch"].get("job_depth", 2))).items():
            job = folders.build_job(key, group, cfg, now, revision=1)
            if folders.job_has_work(job, cfg):
                st.note_emitted(key, job, "(baseline)")
        st.cursor = cursor
        st.save()
        log(f"Baseline gesetzt ({len(st.data['folders'])} Ordner als bekannt markiert), nichts ausgespielt.")
        return 0

    res = evaluate(items, cfg, st, dry_run=args.dry_run, verbose=args.verbose)
    st.cursor = cursor
    if not args.dry_run:
        st.save()
    _summary(res, args.dry_run)
    return 0


def cmd_watch(args) -> int:
    cfg = load_config(args.config)
    _apply_overrides(cfg, args)
    st = state_mod.WatchState(cfg["output"]["state_file"])
    client = dbx_api.client_from_config(cfg)
    watch_path = cfg["dropbox"].get("watch_path", "")
    poll_timeout = int(cfg["watch"].get("longpoll_timeout", 180))
    recheck = int(cfg["watch"].get("recheck_seconds", 60))

    log(f"Watcher startet auf {watch_path} "
        f"(Ruhephase {cfg['watch'].get('quiet_seconds', 180)}s, Longpoll {poll_timeout}s)")
    if not st.cursor:
        cmd_scan(argparse.Namespace(**{**vars(args), "reset_cursor": False}))
        st = state_mod.WatchState(cfg["output"]["state_file"])
        if not st.cursor:
            entries, st.cursor = client.list_folder(watch_path, recursive=True)

    idle_cycles = 0
    while True:
        try:
            pending = st.pending()
            timeout = min(poll_timeout, recheck) if pending else poll_timeout
            res = client.longpoll(st.cursor, timeout=timeout)
            if res.get("backoff"):
                log(f"Dropbox bittet um {res['backoff']}s Pause", verbose_only=True, verbose=args.verbose)
                time.sleep(res["backoff"])

            items: list[dict] = []
            if res["changes"]:
                changed, cursor = client.list_folder_continue(st.cursor)
                st.cursor = cursor
                changed_items = [dbx_api.entry_to_item(e) for e in changed]
                log(f"{len(changed_items)} Änderung(en) gemeldet", verbose_only=True, verbose=args.verbose)
                keys = touched_job_folders(changed_items, cfg)
                items += refresh_items(client, cfg, keys, verbose=args.verbose)
                idle_cycles = 0

            # Wartende Ordner erneut prüfen — ihre Ruhephase läuft auch ohne neue Events ab.
            for rec in list(st.pending()):
                got = fetch_job_items(client, rec.get("path", ""), cfg, verbose=args.verbose)
                if not got:
                    # Ordner gelöscht/umbenannt: aus der Warteliste nehmen, sonst
                    # fragen wir ihn bis zum Sankt-Nimmerleins-Tag ab.
                    log(f"Ordner verschwunden, vergesse {rec.get('path')}")
                    st.forget(rec.get("path", ""))
                    continue
                items += got

            if items:
                uniq = {(i.get("path") or "").lower(): i for i in items}
                out = evaluate(list(uniq.values()), cfg, st, dry_run=args.dry_run, verbose=args.verbose)
                if out["emitted"]:
                    idle_cycles = 0
            st.bump_run()
            if not args.dry_run:
                st.save()
            if not res["changes"] and not items:
                idle_cycles += 1
                log(f"ruhig ({idle_cycles})", verbose_only=True, verbose=args.verbose)
        except dbx_api.DropboxError as exc:
            if exc.status == 400 and "reset" in (exc.body or ""):
                log("Cursor ungültig — baue Bestand neu auf")
                st.reset_cursor()
                st.save()
                cmd_scan(argparse.Namespace(**{**vars(args), "reset_cursor": True}))
                st = state_mod.WatchState(cfg["output"]["state_file"])
                continue
            log(f"Dropbox-Fehler: {exc} — 60s Pause")
            time.sleep(60)
        except KeyboardInterrupt:
            log("Beendet (Ctrl-C). State ist gesichert.")
            st.save()
            return 0


def cmd_status(args) -> int:
    cfg = load_config(args.config)
    st = state_mod.WatchState(cfg["output"]["state_file"])
    folders_ = st.data.get("folders", {})
    emitted = [r for r in folders_.values() if r.get("status") == "emitted"]
    pending = st.pending()
    print(f"State           : {cfg['output']['state_file']}")
    print(f"Cursor          : {'gesetzt' if st.cursor else '(leer — noch kein scan)'}")
    print(f"Läufe           : {st.data['stats'].get('runs', 0)}, "
          f"letzter: {st.data['stats'].get('last_run', '-')}")
    print(f"Jobs ausgespielt: {st.data['stats'].get('jobs_emitted', 0)}")
    print(f"Ordner bekannt  : {len(folders_)} ({len(emitted)} raus, {len(pending)} wartend)\n")
    if pending:
        print("Wartend (Ruhephase läuft / kein Video / Limit):")
        for r in sorted(pending, key=lambda r: r.get("last_seen", ""))[:20]:
            print(f"  - {r.get('path')}  [{r.get('files', '?')} Datei(en), "
                  f"zuletzt gesehen {r.get('last_seen', '?')}]")
        print()
    if emitted:
        print("Zuletzt ausgespielt:")
        for r in sorted(emitted, key=lambda r: r.get("emitted_at", ""), reverse=True)[:10]:
            print(f"  - {r.get('emitted_at')}  r{r.get('revision')}  "
                  f"[{r.get('consultant_id')}]  {r.get('path')}")
    qd = Path(cfg["output"]["queue_dir"])
    if qd.exists():
        jobs = sorted(qd.glob("*.json"))
        print(f"\nQueue           : {len(jobs)} Job-Datei(en) in {qd}")
    return 0


def cmd_simulate(args) -> int:
    """Trockenlauf gegen eine Fixture-Datei — kein Dropbox, kein Netz.

    Fixture = JSON-Liste von {path, size, server_modified[, rev]} oder das
    Rohformat von `files/list_folder` ({"entries": [...]}).
    """
    cfg = load_config(args.config)
    _apply_overrides(cfg, args)
    raw = json.loads(Path(args.fixture).read_text("utf-8"))
    entries = raw.get("entries", raw) if isinstance(raw, dict) else raw
    items = []
    for e in entries:
        if ".tag" in e or "path_display" in e or "path_lower" in e:
            if e.get(".tag", "file") != "file":
                continue
            items.append(dbx_api.entry_to_item(e))
        else:
            items.append({"path": e["path"], "name": Path(e["path"]).name,
                          "size": int(e.get("size") or 0),
                          "server_modified": e.get("server_modified", ""),
                          "rev": e.get("rev", "r1"), "id": e.get("id", ""),
                          "content_hash": e.get("content_hash", "")})
    state_path = args.state or (Path(cfg["output"]["dir"]) / "state.simulate.json")
    st = state_mod.WatchState(state_path)
    now = folders.parse_ts(args.now) if args.now else datetime.now(timezone.utc)
    res = evaluate(items, cfg, st, now=now, dry_run=not args.write, verbose=True)
    if args.write:
        st.save()
    _summary(res, dry_run=not args.write)
    if args.print_job and res["emitted"]:
        print(json.dumps(res["emitted"][0]["job"], indent=2, ensure_ascii=False))
    return 0


def cmd_forget(args) -> int:
    cfg = load_config(args.config)
    st = state_mod.WatchState(cfg["output"]["state_file"])
    if args.all:
        count = len(st.data["folders"])
        st.data["folders"] = {}
        st.save()
        print(f"{count} Ordner vergessen — der nächste `scan` spielt sie neu aus.")
        return 0
    if not args.folder:
        raise SystemExit("Entweder --all oder einen Ordnerpfad angeben.")
    for f in args.folder:
        st.forget(f)
        print(f"vergessen: {f}")
    st.save()
    return 0


def cmd_selftest(args) -> int:
    rc = 0
    for mod in (classify, folders, state_mod, dbx_api, emit):
        rc |= mod._selftest()
    rc |= _integration_selftest()
    print("\nSELFTEST: " + ("alles grün" if rc == 0 else "FEHLER"))
    return rc


def _integration_selftest() -> int:
    """Ende-zu-Ende ohne Netz: Fixture -> Jobs -> Queue-Dateien."""
    import shutil
    import tempfile
    fails: list[str] = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r}, want {want!r}")

    tmp = Path(tempfile.mkdtemp(prefix="watchint-"))
    try:
        cfg = {
            "dropbox": {"watch_path": "/Video Upload"},
            "watch": {"quiet_seconds": 180, "job_depth": 2,
                      "ignore_paths": ["/Video Upload/_Archiv"]},
            "consultants": [{"id": "thorben", "name": "Thorben", "path": "/Video Upload/Thorben",
                             "clickup": {"list_id": "111"}}],
            "triage": {"consultant_id": "_triage"},
            "output": {"dir": str(tmp), "queue_dir": str(tmp / "queue"),
                       "event_log": str(tmp / "events.jsonl"),
                       "state_file": str(tmp / "state.json")},
            "_config_path": str(tmp / "config.json"),
        }
        now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)
        old_ts, fresh = "2026-10-13T11:00:00Z", "2026-10-13T11:59:30Z"
        items = [
            {"path": "/Video Upload/Thorben/Reel 01/Reel 01.mp4", "name": "Reel 01.mp4",
             "size": 9, "server_modified": old_ts, "rev": "a"},
            {"path": "/Video Upload/Thorben/Reel 01/Reel 01.pdf", "name": "Reel 01.pdf",
             "size": 2, "server_modified": old_ts, "rev": "b"},
            {"path": "/Video Upload/Thorben/Reel 01/Reel 01.txt", "name": "Reel 01.txt",
             "size": 1, "server_modified": old_ts, "rev": "c"},
            {"path": "/Video Upload/Nina/Reel 09/take.mp4", "name": "take.mp4",
             "size": 5, "server_modified": fresh, "rev": "d"},
            {"path": "/Video Upload/_Archiv/alt/alt.mp4", "name": "alt.mp4",
             "size": 5, "server_modified": old_ts, "rev": "e"},
            {"path": "/Video Upload/Thorben/Reel 01/.DS_Store", "name": ".DS_Store",
             "size": 1, "server_modified": old_ts, "rev": "f"},
        ]
        st = state_mod.WatchState(cfg["output"]["state_file"])
        res = evaluate(items, cfg, st, now=now)
        eq(len(res["emitted"]), 1, "one ready job")
        eq(len(res["waiting"]), 1, "fresh upload waits")
        eq([s["reason"] for s in res["skipped"]], ["ignore_paths"], "archive ignored")
        job = res["emitted"][0]["job"]
        eq(job["consultant"]["id"], "thorben", "consultant resolved")
        eq(job["analysis"]["script_confidence"], "high", "script detected")
        eq(job["analysis"]["needs_transcription"], True, "transcription needed")
        eq(Path(res["emitted"][0]["queue_file"]).exists(), True, "queue file written")

        res2 = evaluate(items, cfg, st, now=now)
        eq(len(res2["emitted"]), 0, "no duplicate emit")

        later = datetime(2026, 10, 13, 12, 5, 0, tzinfo=timezone.utc)
        res3 = evaluate(items, cfg, st, now=later)
        eq(len(res3["emitted"]), 1, "waiting job emitted after quiet period")
        eq(res3["emitted"][0]["job"]["consultant"]["needs_triage"], True, "nina -> triage")

        items2 = items + [{"path": "/Video Upload/Thorben/Reel 01/Reel 01.srt",
                           "name": "Reel 01.srt", "size": 1,
                           "server_modified": "2026-10-13T12:00:00Z", "rev": "g"}]
        res4 = evaluate(items2, cfg, st, now=datetime(2026, 10, 13, 12, 10, 0, tzinfo=timezone.utc))
        eq(len(res4["emitted"]), 1, "new file -> revision 2")
        eq(res4["emitted"][0]["job"]["revision"], 2, "revision bumped")
        eq(res4["emitted"][0]["reason"], "changed", "reason changed")
        eq(res4["emitted"][0]["job"]["analysis"]["needs_transcription"], False, "srt satisfies transcript")
        eq(res4["emitted"][0]["job"]["previous"]["new_files"],
           ["/Video Upload/Thorben/Reel 01/Reel 01.srt"], "new file listed")

        lines = (tmp / "events.jsonl").read_text().strip().splitlines()
        eq(len(lines), 3, "three events logged")
        eq(len(list((tmp / "queue").glob("*.json"))), 3, "three queue files")

        # Watch-Loop-Teil: Dateistand je Job-Ordner nachladen (Fake-Client, kein Netz).
        class _Fake:
            """Minimal-Client: kennt nur zwei Ordner, alles andere ist not_found."""

            tree = {
                "/video upload": [{"path_display": "/Video Upload/lose.mp4", "name": "lose.mp4",
                                   "size": 5, "rev": "z", "server_modified": old_ts}],
                "/video upload/thorben/reel 01": [
                    {"path_display": "/Video Upload/Thorben/Reel 01/Reel 01.mp4",
                     "name": "Reel 01.mp4", "size": 9, "rev": "a", "server_modified": old_ts}],
            }

            def list_folder(self, path, recursive=True):
                key = (path or "").rstrip("/").lower()
                if key not in self.tree:
                    raise dbx_api.DropboxError("not found", 409,
                                               '{"error_summary":"path/not_found/."}')
                return [{**e, ".tag": "file"} for e in self.tree[key]], "cur"

        fake = _Fake()
        got = fetch_job_items(fake, "/Video Upload/Thorben/Reel 01", cfg)
        eq([i["name"] for i in got], ["Reel 01.mp4"], "job folder listed")
        # Einzeldatei im Root: Key ist "<root>/<stamm>" -> Fallback auf den Root-Ordner
        got = fetch_job_items(fake, "/Video Upload/lose", cfg)
        eq([i["name"] for i in got], ["lose.mp4"], "root single file falls back to parent")
        eq(fetch_job_items(fake, "/Video Upload/Thorben/Weg", cfg), [], "vanished folder -> empty")
        # Root-Ebene ist nicht unterscheidbar (Key koennte eine Einzeldatei sein) -> Root listen
        eq([i["name"] for i in fetch_job_items(fake, "/Video Upload/Weg", cfg)],
           ["lose.mp4"], "root-level key falls back to root listing")
        eq(len(refresh_items(fake, cfg, ["/Video Upload/Thorben/Reel 01",
                                         "/Video Upload/Thorben/Reel 01"])), 1, "refresh dedupes")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for f in fails:
        print("FAIL", f)
    print(f"integration selftest: {'OK' if not fails else str(len(fails)) + ' failures'}")
    return 1 if fails else 0


# --- Plumbing --------------------------------------------------------------

def _apply_overrides(cfg: dict, args) -> None:
    if getattr(args, "quiet_seconds", None) is not None:
        cfg["watch"]["quiet_seconds"] = int(args.quiet_seconds)
    if getattr(args, "watch_path", None):
        cfg["dropbox"]["watch_path"] = args.watch_path
    if getattr(args, "no_hook", False):
        cfg["output"]["hook_command"] = ""
        cfg["output"]["webhook_url"] = ""


def _summary(res: dict, dry_run: bool) -> None:
    log(f"{'[dry-run] ' if dry_run else ''}"
        f"{len(res['emitted'])} Job(s) ausgespielt, {len(res['waiting'])} wartend, "
        f"{len(res['skipped'])} übersprungen")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--dry-run", action="store_true", help="nichts schreiben, nur zeigen")
    ap.add_argument("--quiet-seconds", type=int, help="Ruhephase überschreiben")
    ap.add_argument("--watch-path", help="Watch-Pfad überschreiben")
    ap.add_argument("--no-hook", action="store_true", help="Hook/Webhook für diesen Lauf aus")
    ap.add_argument("--verbose", "-v", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("auth", help="Dropbox verbinden (PKCE, einmalig)")
    p.add_argument("--app-key")
    p.add_argument("--code", help="Auth-Code non-interaktiv übergeben")
    p.set_defaults(fn=cmd_auth)

    sub.add_parser("doctor", help="Config/Token/Pfad prüfen").set_defaults(fn=cmd_doctor)

    p = sub.add_parser("scan", help="Bestand einlesen + reife Jobs ausspielen")
    p.add_argument("--reset-cursor", action="store_true")
    p.set_defaults(fn=cmd_scan)

    sub.add_parser("watch", help="Dauerbetrieb via Longpoll").set_defaults(fn=cmd_watch)
    sub.add_parser("status", help="Zustand anzeigen").set_defaults(fn=cmd_status)

    p = sub.add_parser("simulate", help="Trockenlauf gegen eine Fixture-Datei")
    p.add_argument("fixture")
    p.add_argument("--now", help="Zeitpunkt simulieren (ISO, z. B. 2026-10-13T12:00:00Z)")
    p.add_argument("--state", help="eigene State-Datei (default: state.simulate.json)")
    p.add_argument("--write", action="store_true", help="Queue/State wirklich schreiben")
    p.add_argument("--print-job", action="store_true", help="erstes Job-JSON ausgeben")
    p.set_defaults(fn=cmd_simulate)

    p = sub.add_parser("forget", help="Ordner vergessen -> wird neu ausgespielt")
    p.add_argument("folder", nargs="*")
    p.add_argument("--all", action="store_true")
    p.set_defaults(fn=cmd_forget)

    sub.add_parser("selftest", help="komplette Logik offline testen").set_defaults(fn=cmd_selftest)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except dbx_api.DropboxError as exc:
        print(f"Dropbox-Fehler: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
