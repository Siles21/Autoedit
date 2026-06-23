#!/usr/bin/env python3
"""batch.py — unified batch-run of the per-video pipeline over many videos.

ONE jobs.json handles BOTH 16:9 cuts and 9:16 reels in one list. Each job is a
fully independent unit (own authored plan + own out dir), so jobs parallelise
cleanly AND stay individually adjustable: re-run a single video with --only
without redoing the rest. render_overlays.py hashes per clip (--skip-existing),
so a selective re-run is idempotent — only changed clips re-render.

    batch.py --jobs jobs.json [--only name1,name2] [--parallel 2] [--strict]

jobs.json = a JSON list of job objects (see SHARED CONTRACT below). Each job
maps every key to the matching pipeline.py flag; pipeline.py owns the actual
work (reel dynamics → face zones → render → sfx → integrate|flatten → music).

After the run, batch.py writes "batch-status.json" next to --jobs: a per-video
registry recording {name, status, format, out, deliverable} for every job that
ran this pass — so the next selective re-run / a downstream step knows what to
pick up.

jobs.json job object (keys, with defaults):
  name        str   unique, required
  plan        path  required (authored animation-plan.json)
  out         path  required (own dir per job)
  transcript|words|video  path  exactly one required
                        ("video" also needed for face-aware placement + reel zoom)
  format      "16x9" | "9x16"            (default "16x9")
  brand       str                        (default "default")
  fps         int                        (default 30)
  avoidStyle  "conservative" | "best"    (default "conservative")
  noSfx       bool                       (default false)
  noFaceAware bool                       (default false)
  reel        bool                       (default = (format == "9x16"))
  reelZoom    float (0.05)  reelPeriod float (16)
  reelJump    float (12)    reelJumpAmt float (0.07)
  music       path                       (optional, OPT-IN only)
  musicGain   float                      (default -20)
  deliver     "premiere" | "flat"        (default "premiere" 16:9 / "flat" 9:16)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _expand(p: str) -> str:
    return str(Path(p).expanduser())


def _truthy(job: dict, key: str, default: bool) -> bool:
    v = job.get(key, default)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


def build_cmd(job: dict, strict: bool) -> list[str]:
    """Map every jobs.json key to the exact pipeline.py flag."""
    fmt = job.get("format", "16x9")
    # reel defaults to true for 9:16, false otherwise
    reel = _truthy(job, "reel", fmt == "9x16")
    # deliver defaults: 9:16 reels are flattened, 16:9 cuts go to Premiere
    deliver = job.get("deliver", "flat" if fmt == "9x16" else "premiere")

    cmd = [sys.executable, str(HERE / "pipeline.py"),
           "--plan", _expand(job["plan"]),
           "--out", _expand(job["out"]),
           "--brand", job.get("brand", "thorben"),
           "--format", fmt,
           "--fps", str(job.get("fps", 30)),
           "--avoid-style", job.get("avoidStyle", "conservative"),
           "--deliver", deliver]

    # input source: exactly one of transcript | words | video
    for k in ("transcript", "words", "video"):
        if job.get(k):
            cmd += [f"--{k}", _expand(job[k])]

    if _truthy(job, "noSfx", False):
        cmd += ["--no-sfx"]
    if _truthy(job, "noFaceAware", False):
        cmd += ["--no-face-aware"]

    # reel dynamics (zoom/jump-cuts) — pipeline runs reel_dynamics.py first
    if reel:
        cmd += ["--reel",
                "--reel-zoom", str(job.get("reelZoom", 0.05)),
                "--reel-period", str(job.get("reelPeriod", 16)),
                "--reel-jump", str(job.get("reelJump", 12)),
                "--reel-jump-amt", str(job.get("reelJumpAmt", 0.07))]

    # music is OPT-IN only — passed solely when a job declares it
    if job.get("music"):
        cmd += ["--music", _expand(job["music"]),
                "--music-gain", str(job.get("musicGain", -20))]

    if strict:
        cmd += ["--strict"]
    return cmd


def _find_deliverable(out_dir: Path, deliver: str) -> str | None:
    """Best-effort: locate the deliverable pipeline.py produced for this job."""
    if not out_dir.exists():
        return None
    if deliver == "flat":
        # flatten_final.py / add_music.py emit a single final mp4 in out dir
        prefer = ["final_music.mp4", "final-music.mp4", "final_flat.mp4",
                  "final.mp4"]
        for n in prefer:
            p = out_dir / n
            if p.exists():
                return str(p)
        mp4s = sorted(out_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime,
                      reverse=True)
        return str(mp4s[0]) if mp4s else None
    # premiere delivery: integrate.py emits an FCPXML + overlays manifest
    for n in ("placement.fcpxml", "integrate.fcpxml"):
        p = out_dir / n
        if p.exists():
            return str(p)
    fcps = sorted(out_dir.glob("*.fcpxml"), key=lambda p: p.stat().st_mtime,
                  reverse=True)
    if fcps:
        return str(fcps[0])
    man = out_dir / "overlays" / "overlays-manifest.json"
    return str(man) if man.exists() else None


def run_job(job: dict, strict: bool) -> dict:
    name = job.get("name", job.get("plan", "?"))
    fmt = job.get("format", "16x9")
    deliver = job.get("deliver", "flat" if fmt == "9x16" else "premiere")
    out_dir = Path(_expand(job["out"]))
    cmd = build_cmd(job, strict)
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = r.returncode == 0
    return {
        "name": name,
        "rc": r.returncode,
        "status": "ok" if ok else "fail",
        "format": fmt,
        "out": str(out_dir),
        "deliverable": _find_deliverable(out_dir, deliver) if ok else None,
        "tail": (r.stderr or r.stdout).strip().splitlines()[-1:] or [""],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Unified batch-run (16:9 + 9:16)")
    ap.add_argument("--jobs", type=Path, required=True)
    ap.add_argument("--only", default=None,
                    help="comma-separated job names to (re-)run ONLY these videos")
    ap.add_argument("--parallel", type=int, default=1,
                    help="concurrent jobs (default 1 = sequential)")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
    if not isinstance(jobs, list) or not jobs:
        sys.exit("ERROR: jobs.json must be a non-empty list")
    for j in jobs:
        if "plan" not in j or "out" not in j:
            sys.exit(f"ERROR: job missing plan/out: {j}")
        if "name" not in j:
            sys.exit(f"ERROR: job missing name: {j}")
        if not any(j.get(k) for k in ("transcript", "words", "video")):
            sys.exit(f"ERROR: job '{j['name']}' needs one of transcript|words|video")
    names = [j["name"] for j in jobs]
    if len(set(names)) != len(names):
        sys.exit(f"ERROR: job names must be unique: {names}")

    # --only: selective per-video re-run (idempotent via render hash-skip)
    if args.only:
        want = [n.strip() for n in args.only.split(",") if n.strip()]
        unknown = [n for n in want if n not in names]
        if unknown:
            sys.exit(f"ERROR: --only names not in jobs.json: {unknown}")
        jobs = [j for j in jobs if j["name"] in want]

    print(f"batch: {len(jobs)} job(s), parallel={args.parallel}"
          f"{', only=' + args.only if args.only else ''}", file=sys.stderr)

    results: list[dict] = []
    if args.parallel <= 1:
        for j in jobs:
            print(f"\n=== {j['name']} ({j.get('format', '16x9')}) ===",
                  file=sys.stderr)
            results.append(run_job(j, args.strict))
    else:
        with ThreadPoolExecutor(max_workers=args.parallel) as ex:
            futs = {ex.submit(run_job, j, args.strict): j for j in jobs}
            for f in as_completed(futs):
                results.append(f.result())

    # per-video status registry next to --jobs. On a selective (--only) run we
    # MERGE into the existing registry so untouched jobs keep their last status.
    status_path = args.jobs.resolve().parent / "batch-status.json"
    registry: dict[str, dict] = {}
    if status_path.exists():
        try:
            prev = json.loads(status_path.read_text(encoding="utf-8"))
            for e in prev.get("jobs", []):
                if e.get("name"):
                    registry[e["name"]] = e
        except (ValueError, OSError):
            registry = {}
    for r in results:
        registry[r["name"]] = {
            "name": r["name"], "status": r["status"], "format": r["format"],
            "out": r["out"], "deliverable": r["deliverable"],
        }
    status_path.write_text(
        json.dumps({"jobs": list(registry.values())}, indent=2,
                   ensure_ascii=False), encoding="utf-8")

    print("\n===== BATCH SUMMARY =====")
    for r in sorted(results, key=lambda x: x["name"]):
        print(f"  [{'OK ' if r['rc'] == 0 else 'FAIL'}] "
              f"{r['name']} ({r['format']})  {r['tail'][0][:80]}")
    print(f"  status registry → {status_path}")
    failed = [r["name"] for r in results if r["rc"] != 0]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
