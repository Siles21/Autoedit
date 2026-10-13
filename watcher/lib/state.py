#!/usr/bin/env python3
"""state.py — persistenter Zustand des Watchers (eine JSON-Datei, atomar geschrieben).

Gemerkt wird genau so viel, dass ein Neustart nichts doppelt und nichts verliert:

  * `cursor`        : Dropbox-Delta-Cursor (ab wo weiterhören)
  * `folders[key]`  : pro Job-Ordner — erster Kontakt, Fingerprint, Revision,
                      wann ausgespielt, wie viele Dateien
  * `stats`         : Lauf-Metriken fürs `status`-Kommando

    python3 state.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

STATE_SCHEMA = "autoedit.dropbox.state/1"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class WatchState:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data: dict = {"schema": STATE_SCHEMA, "cursor": "", "folders": {},
                           "stats": {"jobs_emitted": 0, "runs": 0}}
        self.load()

    # -- Persistenz
    def load(self) -> "WatchState":
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text("utf-8") or "{}")
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except json.JSONDecodeError:
                backup = self.path.with_suffix(".corrupt.json")
                self.path.replace(backup)
                print(f"[state] defekte Datei nach {backup} verschoben, starte frisch")
        self.data.setdefault("folders", {})
        self.data.setdefault("stats", {"jobs_emitted": 0, "runs": 0})
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data["updated_at"] = _now()
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".state-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)       # atomar: kein halb geschriebener State
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # -- Cursor
    @property
    def cursor(self) -> str:
        return self.data.get("cursor", "")

    @cursor.setter
    def cursor(self, value: str) -> None:
        self.data["cursor"] = value or ""

    def reset_cursor(self) -> None:
        self.data["cursor"] = ""

    # -- Ordner
    @staticmethod
    def key(job_key: str) -> str:
        return (job_key or "").lower()

    def folder(self, job_key: str) -> dict:
        return self.data["folders"].get(self.key(job_key), {})

    def note_seen(self, job_key: str, job: dict) -> dict:
        """Ordner als 'gesehen, wartet' vermerken (ohne Emit)."""
        rec = self.folder(job_key) or {}
        rec.setdefault("first_seen", _now())
        rec.update({
            "path": job["folder"]["path"],
            "job_id": job["job_id"],
            "fingerprint": job["fingerprint"],
            "files": job["totals"]["files"],
            "status": job["status"],
            "last_seen": _now(),
            "newest_server_modified": job["sync"]["newest_server_modified"],
            "consultant_id": job["consultant"]["id"],
        })
        rec.setdefault("revision", 0)
        rec.setdefault("emitted_fingerprint", "")
        self.data["folders"][self.key(job_key)] = rec
        return rec

    def note_emitted(self, job_key: str, job: dict, queue_file: str) -> dict:
        rec = self.note_seen(job_key, job)
        rec.update({
            "status": "emitted",
            "revision": job["revision"],
            "emitted_fingerprint": job["fingerprint"],
            "emitted_at": _now(),
            "queue_file": queue_file,
            "paths": sorted({*(a["path"] for a in job["videos"]),
                             *(a["path"] for bucket in job["assets"].values() for a in bucket)}),
        })
        self.data["stats"]["jobs_emitted"] = int(self.data["stats"].get("jobs_emitted", 0)) + 1
        self.data["folders"][self.key(job_key)] = rec
        return rec

    def needs_emit(self, job_key: str, job: dict) -> tuple[bool, str]:
        """Soll dieser Job (erneut) ausgespielt werden? -> (ja/nein, Grund)."""
        rec = self.folder(job_key)
        if not rec or rec.get("status") != "emitted":
            return True, "new"
        if rec.get("emitted_fingerprint") != job["fingerprint"]:
            return True, "changed"
        return False, "unchanged"

    def next_revision(self, job_key: str) -> int:
        return int(self.folder(job_key).get("revision", 0)) + 1

    def pending(self) -> list[dict]:
        """Ordner, die gesehen wurden aber noch nicht ausgespielt sind."""
        return [r for r in self.data["folders"].values() if r.get("status") != "emitted"]

    def bump_run(self) -> None:
        self.data["stats"]["runs"] = int(self.data["stats"].get("runs", 0)) + 1
        self.data["stats"]["last_run"] = _now()

    def forget(self, job_key: str) -> None:
        self.data["folders"].pop(self.key(job_key), None)


# --- Selftest ---------------------------------------------------------------

def _selftest() -> int:
    import shutil
    fails: list[str] = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r}, want {want!r}")

    tmp = Path(tempfile.mkdtemp(prefix="watchstate-"))
    try:
        sp = tmp / "state.json"
        st = WatchState(sp)
        job = {
            "job_id": "reel-01-abc", "revision": 1, "fingerprint": "f1", "status": "ready",
            "folder": {"path": "/V/Thorben/Reel 01"}, "totals": {"files": 3},
            "sync": {"newest_server_modified": "2026-10-13T10:00:00Z"},
            "consultant": {"id": "thorben"},
            "videos": [{"path": "/V/Thorben/Reel 01/a.mp4"}],
            "assets": {"text": [{"path": "/V/Thorben/Reel 01/a.txt"}], "pdf": []},
        }
        key = "/V/Thorben/Reel 01"
        eq(st.needs_emit(key, job), (True, "new"), "new folder needs emit")
        st.note_seen(key, job)
        eq(len(st.pending()), 1, "pending after seen")
        eq(st.next_revision(key), 1, "first revision")
        st.note_emitted(key, job, "queue/x.json")
        eq(st.needs_emit(key, job), (False, "unchanged"), "no double emit")
        eq(st.pending(), [], "nothing pending after emit")
        eq(st.folder(key)["paths"], ["/V/Thorben/Reel 01/a.mp4", "/V/Thorben/Reel 01/a.txt"], "paths recorded")

        job2 = {**job, "fingerprint": "f2"}
        eq(st.needs_emit(key, job2), (True, "changed"), "changed fingerprint re-emits")
        eq(st.next_revision(key), 2, "revision bump")

        st.cursor = "cur-1"
        st.save()
        again = WatchState(sp)
        eq(again.cursor, "cur-1", "cursor persisted")
        eq(again.needs_emit(key, job), (False, "unchanged"), "state persisted")
        eq(again.needs_emit("/v/thorben/reel 01", job), (False, "unchanged"), "key case-insensitive")
        eq(again.data["stats"]["jobs_emitted"], 1, "stats persisted")

        sp.write_text("{broken", encoding="utf-8")
        recovered = WatchState(sp)
        eq(recovered.cursor, "", "corrupt state recovered")
        eq((tmp / "state.corrupt.json").exists(), True, "corrupt backup kept")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for f in fails:
        print("FAIL", f)
    print(f"state selftest: {'OK' if not fails else str(len(fails)) + ' failures'}")
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    raise SystemExit(_selftest() if args.selftest else 0)
