#!/usr/bin/env python3
"""folders.py — Datei-Events zu Ordner-Jobs bündeln und auf "fertig synct" prüfen.

Ein Upload ist nie eine Datei, sondern ein Ordner: Video + evtl. Skript (Text/PDF)
+ evtl. Transkript. Dieses Modul gruppiert die Dropbox-Einträge zu *Jobs*
(= ein Dreh/Reel), bestimmt den Berater, und gibt einen Job erst frei, wenn im
Ordner seit `quiet_seconds` nichts mehr passiert ist ("Ordner ist durchsynct").

Reine Funktionen, keine Deps, kein Netz.

    python3 folders.py --selftest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
from datetime import datetime, timedelta, timezone

try:  # als Paket (python3 -m lib.folders) oder direkt (python3 lib/folders.py)
    from .classify import classify_file, resolve_consultant, script_confidence, slug
except ImportError:  # pragma: no cover
    from classify import classify_file, resolve_consultant, script_confidence, slug  # type: ignore

JOB_SCHEMA = "autoedit.dropbox.job/1"

# Kinds, die als Asset in den Job wandern (ignore fliegt raus).
ASSET_BUCKETS = ("transcript", "script", "pdf", "text", "audio", "image", "project", "other")


# --- Zeit-Helfer ------------------------------------------------------------

def parse_ts(value) -> datetime:
    """Dropbox-Zeitstempel ('2026-10-13T10:00:00Z') -> aware datetime (UTC)."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = (value or "").strip()
    if not text:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Gruppierung ------------------------------------------------------------

def rel_segments(path: str, root: str) -> list[str]:
    """Pfadsegmente relativ zum Watch-Root."""
    p = (path or "").rstrip("/")
    r = (root or "").rstrip("/")
    low_p, low_r = p.lower(), r.lower()
    if low_r and low_p.startswith(low_r + "/"):
        p = p[len(r) + 1:]
    elif low_r and low_p == low_r:
        p = ""
    return [s for s in p.split("/") if s]


def job_folder_for(path: str, root: str, job_depth: int = 2) -> str:
    """Zu welchem Job-Ordner gehört diese Datei?

    `job_depth` = wie viele Ebenen unter dem Root der Job-Ordner liegt.
    Default 2 passt auf `/<Root>/<Berater>/<Projekt>/dateien…` — tiefere
    Unterordner (z. B. `…/Projekt/Footage/a.mp4`) rollen auf `Projekt` hoch.
    Liegt die Datei flacher, gilt ihr eigener Ordner; liegt sie direkt im Root,
    ist der Job die Datei selbst (Rückgabe = Root, Caller splittet per Datei).
    """
    segs = rel_segments(posixpath.dirname(path or ""), root)
    keep = segs[:max(0, job_depth)]
    base = (root or "").rstrip("/")
    return base + ("/" + "/".join(keep) if keep else "")


def group_jobs(entries: list[dict], root: str, job_depth: int = 2) -> dict[str, list[dict]]:
    """Dropbox-Dateieinträge -> {job_key: [entries]}.

    Einträge mit kind == "ignore" werden verworfen. Dateien direkt im Root
    bekommen je Datei einen eigenen Job-Key (Root ist kein Sammel-Job).
    """
    out: dict[str, list[dict]] = {}
    base = (root or "").rstrip("/")
    for e in entries:
        name = e.get("name") or posixpath.basename(e.get("path", ""))
        kind = e.get("kind") or classify_file(name)
        if kind == "ignore":
            continue
        folder = job_folder_for(e.get("path", ""), base, job_depth)
        key = folder if folder != base else f"{base}/{posixpath.splitext(name)[0]}"
        out.setdefault(key, []).append({**e, "name": name, "kind": kind})
    return out


def fingerprint(entries: list[dict]) -> str:
    """Stabiler Hash über (Pfad, rev) — ändert sich bei jeder neuen/geänderten Datei."""
    parts = sorted(f"{(e.get('path') or '').lower()}:{e.get('rev') or e.get('size')}" for e in entries)
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def job_id_for(job_key: str) -> str:
    """Lesbare, stabile Job-ID: slug + Hash (Hash gegen Kollisionen/Umbenennungen)."""
    h = hashlib.sha1(job_key.lower().encode("utf-8")).hexdigest()[:8]
    return f"{slug(posixpath.basename(job_key)) or 'job'}-{h}"


# --- Reifeprüfung -----------------------------------------------------------

def readiness(entries: list[dict], now: datetime, quiet_seconds: int) -> dict:
    """Ist der Ordner durchsynct? -> {"ready", "newest", "quiet_for", "wait_for"}.

    Dropbox listet nur vollständig hochgeladene Dateien (Teil-Uploads sind über
    die API unsichtbar) — eine sichtbare Datei ist also komplett. Offen bleibt
    nur, ob *weitere* Dateien desselben Uploads noch kommen. Dafür die
    Ruhephase: seit `quiet_seconds` keine neue/geänderte Datei im Ordner.
    """
    if not entries:
        return {"ready": False, "newest": None, "quiet_for": 0, "wait_for": quiet_seconds}
    newest = max(parse_ts(e.get("server_modified")) for e in entries)
    quiet_for = max(0, int((now - newest).total_seconds()))
    wait_for = max(0, quiet_seconds - quiet_for)
    return {"ready": wait_for == 0, "newest": newest, "quiet_for": quiet_for, "wait_for": wait_for}


# --- Job-Objekt -------------------------------------------------------------

def build_job(job_key: str, entries: list[dict], cfg: dict, now: datetime,
              revision: int = 1, previous: dict | None = None) -> dict:
    """Ordner + Dateien -> Job-JSON (das Übergabeformat an Part 2 / ClickUp)."""
    root = (cfg.get("dropbox", {}).get("watch_path") or "").rstrip("/")
    quiet = int(cfg.get("watch", {}).get("quiet_seconds", 180))
    consultants = cfg.get("consultants") or []
    default_id = cfg.get("triage", {}).get("consultant_id", "_triage")

    items = [{**e, "kind": e.get("kind") or classify_file(e.get("name", ""))} for e in entries]
    items = [e for e in items if e["kind"] != "ignore"]
    videos = sorted((e for e in items if e["kind"] == "video"),
                    key=lambda e: (-int(e.get("size") or 0), e.get("name", "")))
    transcripts = [e for e in items if e["kind"] == "transcript"]

    assets = {bucket: [_slim(e) for e in items if e["kind"] == bucket] for bucket in ASSET_BUCKETS}
    conf = script_confidence([(e["kind"], e.get("name", "")) for e in items])
    state = readiness(items, now, quiet)
    consultant = resolve_consultant(job_key, consultants, default_id)

    if transcripts:
        transcript_status = "present"
    elif conf in ("high", "medium"):
        transcript_status = "script_only"   # Skript da, Transkript fehlt
    else:
        transcript_status = "missing"

    job = {
        "schema": JOB_SCHEMA,
        "job_id": job_id_for(job_key),
        "revision": revision,
        "status": "ready" if state["ready"] else "waiting_for_sync",
        "detected_at": iso(now),
        "source": "dropbox",
        "folder": {
            "path": job_key,
            "name": posixpath.basename(job_key) or "/",
            "relative": "/".join(rel_segments(job_key, root)),
            "root": root,
        },
        "consultant": {
            "id": consultant.get("id"),
            "name": consultant.get("name"),
            "matched_by": consultant.get("matched_by"),
            "matched_on": consultant.get("matched_on"),
            "clickup": consultant.get("clickup") or {},
            "needs_triage": consultant.get("matched_by") == "default",
        },
        "video": _slim(videos[0]) if videos else None,
        "videos": [_slim(v) for v in videos],
        "assets": assets,
        "analysis": {
            "video_count": len(videos),
            "transcript_status": transcript_status,
            "needs_transcription": bool(videos) and transcript_status != "present",
            "script_confidence": conf,
            "script_candidates": [e.get("name") for e in items if e["kind"] in ("script", "text", "pdf")],
        },
        "sync": {
            "quiet_seconds_required": quiet,
            "quiet_for_seconds": state["quiet_for"],
            "wait_for_seconds": state["wait_for"],
            "newest_server_modified": iso(state["newest"]) if state["newest"] else None,
        },
        "totals": {
            "files": len(items),
            "bytes": sum(int(e.get("size") or 0) for e in items),
            "video_bytes": sum(int(v.get("size") or 0) for v in videos),
        },
        "fingerprint": fingerprint(items),
        "next_step": "clickup_intake",
    }
    if previous:
        job["previous"] = {
            "revision": previous.get("revision"),
            "fingerprint": previous.get("fingerprint"),
            "emitted_at": previous.get("emitted_at"),
            "new_files": sorted(_new_paths(items, previous)),
        }
    return job


def _slim(e: dict) -> dict:
    return {
        "name": e.get("name"),
        "path": e.get("path"),
        "kind": e.get("kind"),
        "size": int(e.get("size") or 0),
        "server_modified": e.get("server_modified"),
        "rev": e.get("rev"),
        "id": e.get("id"),
        "content_hash": e.get("content_hash"),
    }


def _new_paths(items: list[dict], previous: dict) -> set[str]:
    known = {p.lower() for p in (previous.get("paths") or [])}
    return {e.get("path") for e in items if (e.get("path") or "").lower() not in known} if known else set()


def job_has_work(job: dict, cfg: dict) -> bool:
    """Job nur ausspielen, wenn er für die Pipeline relevant ist (Video vorhanden)."""
    if job["analysis"]["video_count"] > 0:
        return True
    return bool(cfg.get("watch", {}).get("emit_without_video", False))


# --- Selftest ---------------------------------------------------------------

def _entry(path: str, size: int = 1000, minutes_ago: int = 60, rev: str = "r1") -> dict:
    now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)
    return {
        "path": path,
        "name": posixpath.basename(path),
        "size": size,
        "rev": rev,
        "id": "id:" + hashlib.sha1(path.encode()).hexdigest()[:10],
        "server_modified": iso(now - timedelta(minutes=minutes_ago)),
    }


def _cfg() -> dict:
    return {
        "dropbox": {"watch_path": "/Video Upload"},
        "watch": {"quiet_seconds": 180},
        "consultants": [
            {"id": "thorben", "name": "Thorben", "path": "/Video Upload/Thorben",
             "clickup": {"list_id": "111"}},
            {"id": "simon", "name": "Simon", "clickup": {"list_id": "222"}},
        ],
        "triage": {"consultant_id": "_triage"},
    }


def _selftest() -> int:
    fails: list[str] = []
    now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r}, want {want!r}")

    root = "/Video Upload"
    eq(job_folder_for("/Video Upload/Thorben/Reel 01/a.mp4", root), "/Video Upload/Thorben/Reel 01", "depth 2")
    eq(job_folder_for("/Video Upload/Thorben/Reel 01/Footage/a.mp4", root),
       "/Video Upload/Thorben/Reel 01", "deep rolls up")
    eq(job_folder_for("/Video Upload/Thorben/a.mp4", root), "/Video Upload/Thorben", "depth 1")
    eq(job_folder_for("/Video Upload/a.mp4", root), "/Video Upload", "root file")

    entries = [
        _entry("/Video Upload/Thorben/Reel 01/Reel 01.mp4", size=500_000_000),
        _entry("/Video Upload/Thorben/Reel 01/Reel 01.txt", size=4_000),
        _entry("/Video Upload/Thorben/Reel 01/Reel 01.pdf", size=90_000),
        _entry("/Video Upload/Thorben/Reel 01/.DS_Store"),
        _entry("/Video Upload/Thorben/Reel 01/Footage/B-Roll.mov", size=200_000_000),
        _entry("/Video Upload/Simon/Reel 09/take.mp4", minutes_ago=0),
        _entry("/Video Upload/Fremd/x/doku.pdf"),
        _entry("/Video Upload/lose-datei.mp4"),
    ]
    groups = group_jobs(entries, root)
    eq(sorted(groups), ["/Video Upload/Fremd/x", "/Video Upload/Simon/Reel 09",
                        "/Video Upload/Thorben/Reel 01", "/Video Upload/lose-datei"], "grouping")
    eq(len(groups["/Video Upload/Thorben/Reel 01"]), 4, "ds_store dropped, footage rolled up")

    cfg = _cfg()
    job = build_job("/Video Upload/Thorben/Reel 01", groups["/Video Upload/Thorben/Reel 01"], cfg, now)
    eq(job["status"], "ready", "quiet folder ready")
    eq(job["consultant"]["id"], "thorben", "consultant")
    eq(job["consultant"]["clickup"]["list_id"], "111", "clickup passthrough")
    eq(job["video"]["name"], "Reel 01.mp4", "primary video = largest")
    eq(job["analysis"]["video_count"], 2, "two videos")
    eq(job["analysis"]["script_confidence"], "high", "txt+pdf same stem")
    eq(job["analysis"]["transcript_status"], "script_only", "script but no transcript")
    eq(job["analysis"]["needs_transcription"], True, "needs transcription")
    eq(job["totals"]["files"], 4, "file count")
    eq(job_has_work(job, cfg), True, "has work")

    fresh = build_job("/Video Upload/Simon/Reel 09", groups["/Video Upload/Simon/Reel 09"], cfg, now)
    eq(fresh["status"], "waiting_for_sync", "fresh upload waits")
    eq(fresh["sync"]["wait_for_seconds"], 180, "wait window")
    eq(fresh["consultant"]["matched_by"], "segment", "simon by segment")

    nocons = build_job("/Video Upload/Fremd/x", groups["/Video Upload/Fremd/x"], cfg, now)
    eq(nocons["consultant"]["id"], "_triage", "triage fallback")
    eq(nocons["consultant"]["needs_triage"], True, "needs triage flag")
    eq(job_has_work(nocons, cfg), False, "pdf-only job skipped")

    loose = build_job("/Video Upload/lose-datei", groups["/Video Upload/lose-datei"], cfg, now)
    eq(loose["analysis"]["video_count"], 1, "loose root file is its own job")
    eq(loose["analysis"]["transcript_status"], "missing", "no docs at all")

    with_srt = groups["/Video Upload/Simon/Reel 09"] + [_entry("/Video Upload/Simon/Reel 09/take.srt", 2000)]
    j2 = build_job("/Video Upload/Simon/Reel 09", with_srt, cfg, now)
    eq(j2["analysis"]["transcript_status"], "present", "srt present")
    eq(j2["analysis"]["needs_transcription"], False, "no transcription needed")

    a = fingerprint(groups["/Video Upload/Thorben/Reel 01"])
    b = fingerprint(groups["/Video Upload/Thorben/Reel 01"] + [_entry("/Video Upload/Thorben/Reel 01/neu.mp4")])
    eq(a == b, False, "fingerprint changes on new file")
    eq(job_id_for("/Video Upload/Thorben/Reel 01").startswith("reel-01-"), True, "job id readable")
    json.dumps(job)  # Job muss serialisierbar sein
    eq(readiness([], now, 180)["ready"], False, "empty folder not ready")

    for f in fails:
        print("FAIL", f)
    print(f"folders selftest: {'OK' if not fails else str(len(fails)) + ' failures'}")
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    raise SystemExit(_selftest() if args.selftest else 0)
