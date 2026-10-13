#!/usr/bin/env python3
"""emit.py — Übergabe eines fertigen Jobs an die nächste Stufe (Part 2 / ClickUp).

Part 1 kennt ClickUp absichtlich **nicht**. Er legt den Job nur ab und ruft
optional einen Hook. Damit ist Part 2 austauschbar (Claude-Skill, n8n, Make,
eigenes Script) ohne dass der Watcher sich ändert.

Drei Senken, alle optional kombinierbar:
  1. **Queue-Datei** `queue/<ts>-<job_id>-r<rev>.json` (atomar, immer an)
  2. **Event-Log**  `events.jsonl` — eine Zeile pro Job, revisionssicher
  3. **Hook**       beliebiger Befehl; Job-JSON kommt per stdin *und* als $1,
                    plus ENV `AUTOEDIT_JOB_FILE`, `AUTOEDIT_JOB_ID`,
                    `AUTOEDIT_CONSULTANT_ID`
  4. **Webhook**    HTTP-POST des Job-JSON (z. B. n8n/Make-Trigger)

    python3 emit.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def write_job(job: dict, queue_dir: str | Path) -> Path:
    """Job atomar in die Queue schreiben. -> Pfad der Queue-Datei."""
    qd = Path(queue_dir)
    qd.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = qd / f"{ts}-{job['job_id']}-r{job.get('revision', 1)}.json"
    fd, tmp = tempfile.mkstemp(dir=str(qd), prefix=".job-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(job, fh, indent=2, ensure_ascii=False)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)
    return target


def append_event(job: dict, log_path: str | Path, queue_file: str = "", reason: str = "") -> None:
    """Eine Zeile JSONL — für Audit, Nachspielen und `status`."""
    lp = Path(log_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "job_id": job["job_id"],
        "revision": job.get("revision", 1),
        "reason": reason,
        "folder": job["folder"]["path"],
        "consultant": job["consultant"]["id"],
        "videos": job["analysis"]["video_count"],
        "transcript": job["analysis"]["transcript_status"],
        "needs_transcription": job["analysis"]["needs_transcription"],
        "script_confidence": job["analysis"]["script_confidence"],
        "bytes": job["totals"]["bytes"],
        "queue_file": str(queue_file),
    }
    with lp.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")


def run_hook(job: dict, queue_file: Path, command: str, timeout: int = 900) -> dict:
    """Hook-Befehl ausführen. -> {"ok","code","stdout","stderr"}."""
    if not command:
        return {"ok": True, "code": 0, "stdout": "", "stderr": "", "skipped": True}
    argv = shlex.split(command) + [str(queue_file)]
    env = {
        **os.environ,
        "AUTOEDIT_JOB_FILE": str(queue_file),
        "AUTOEDIT_JOB_ID": job["job_id"],
        "AUTOEDIT_JOB_REVISION": str(job.get("revision", 1)),
        "AUTOEDIT_CONSULTANT_ID": job["consultant"]["id"] or "",
        "AUTOEDIT_FOLDER": job["folder"]["path"],
    }
    try:
        proc = subprocess.run(argv, input=json.dumps(job, ensure_ascii=False),
                              capture_output=True, text=True, timeout=timeout, env=env)
        return {"ok": proc.returncode == 0, "code": proc.returncode,
                "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": -1, "stdout": "", "stderr": f"Hook-Timeout nach {timeout}s"}
    except (OSError, ValueError) as exc:
        return {"ok": False, "code": -1, "stdout": "", "stderr": f"Hook nicht ausführbar: {exc}"}


def post_webhook(job: dict, url: str, secret: str = "", timeout: int = 30) -> dict:
    """Job-JSON an eine URL posten (n8n/Make/eigener Endpoint)."""
    if not url:
        return {"ok": True, "status": 0, "skipped": True}
    headers = {"Content-Type": "application/json", "User-Agent": "autoedit-dropbox-watcher/1.0"}
    if secret:
        headers["X-Autoedit-Secret"] = secret
    req = urllib.request.Request(url, data=json.dumps(job, ensure_ascii=False).encode("utf-8"),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"ok": 200 <= resp.status < 300, "status": resp.status}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "error": exc.read().decode("utf-8", "replace")[:300]}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"ok": False, "status": 0, "error": str(exc)}


def dispatch(job: dict, cfg: dict, reason: str = "", dry_run: bool = False) -> dict:
    """Alle konfigurierten Senken bedienen. -> Report-Dict."""
    out = cfg.get("output", {})
    base = Path(out.get("dir") or "watcher")
    queue_dir = Path(out.get("queue_dir") or (base / "queue"))
    log_path = Path(out.get("event_log") or (base / "events.jsonl"))

    if dry_run:
        return {"dry_run": True, "job_id": job["job_id"], "revision": job.get("revision", 1),
                "folder": job["folder"]["path"], "reason": reason, "queue_file": None}

    queue_file = write_job(job, queue_dir)
    append_event(job, log_path, queue_file, reason)
    report = {"dry_run": False, "job_id": job["job_id"], "revision": job.get("revision", 1),
              "folder": job["folder"]["path"], "reason": reason, "queue_file": str(queue_file)}
    hook = out.get("hook_command", "")
    if hook:
        report["hook"] = run_hook(job, queue_file, hook, int(out.get("hook_timeout", 900)))
    webhook = out.get("webhook_url", "")
    if webhook:
        report["webhook"] = post_webhook(job, webhook, out.get("webhook_secret", ""))
    return report


# --- Selftest ---------------------------------------------------------------

def _selftest() -> int:
    import shutil
    fails: list[str] = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r}, want {want!r}")

    job = {
        "job_id": "reel-01-abc", "revision": 2,
        "folder": {"path": "/V/Thorben/Reel 01"},
        "consultant": {"id": "thorben"},
        "analysis": {"video_count": 1, "transcript_status": "script_only",
                     "needs_transcription": True, "script_confidence": "high"},
        "totals": {"bytes": 1234},
    }
    tmp = Path(tempfile.mkdtemp(prefix="watchemit-"))
    try:
        cfg = {"output": {"dir": str(tmp), "queue_dir": str(tmp / "queue"),
                          "event_log": str(tmp / "events.jsonl"),
                          "hook_command": f"{shlex.quote(sys.executable)} -c "
                                          f"\"import sys,json;d=json.load(sys.stdin);print(d['job_id'])\""}}
        rep = dispatch(job, cfg, reason="new")
        qf = Path(rep["queue_file"])
        eq(qf.exists(), True, "queue file written")
        eq(json.loads(qf.read_text())["job_id"], "reel-01-abc", "queue content")
        eq("-r2.json" in qf.name, True, "revision in filename")
        eq(rep["hook"]["ok"], True, f"hook ok ({rep['hook'].get('stderr','')[:120]})")
        eq(rep["hook"]["stdout"].strip(), "reel-01-abc", "hook got job on stdin")
        lines = (tmp / "events.jsonl").read_text().strip().splitlines()
        eq(len(lines), 1, "one event line")
        eq(json.loads(lines[0])["reason"], "new", "event reason")
        eq(json.loads(lines[0])["needs_transcription"], True, "event carries flags")

        dispatch(job, cfg, reason="changed")
        eq(len((tmp / "events.jsonl").read_text().strip().splitlines()), 2, "events append")

        dry = dispatch(job, {"output": {"dir": str(tmp)}}, reason="new", dry_run=True)
        eq(dry["queue_file"], None, "dry run writes nothing")

        bad = run_hook(job, qf, "/nonexistent/hook.sh")
        eq(bad["ok"], False, "missing hook reported, not raised")
        eq(run_hook(job, qf, "")["skipped"], True, "no hook configured")
        eq(post_webhook(job, "")["skipped"], True, "no webhook configured")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for f in fails:
        print("FAIL", f)
    print(f"emit selftest: {'OK' if not fails else str(len(fails)) + ' failures'}")
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    raise SystemExit(_selftest() if args.selftest else 0)
