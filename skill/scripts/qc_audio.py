#!/usr/bin/env python3
"""qc_audio.py — guard against SILENT overlay graphics before placement/delivery.

Every rendered overlay must carry an audible SFX baked in (see add_sfx.py). This
checker ffprobes each .mov and FAILS (exit 1) if any clip has:
  - no audio stream at all, or
  - a silent / near-silent audio track (peak below --min-peak, default -45 dB).

Catches both failure modes Simon hit: (a) graphic with NO sound effect, and
(b) sound effect present but effectively muted/silent. Run it AFTER add_sfx.py
and BEFORE integrate/placement.

    qc_audio.py <overlays_dir>            # globs *.mov recursively
    qc_audio.py <overlays-manifest.json> --format 16x9
    [--min-peak -45] [--target -25]      # silent threshold / expected peak

Exit 0 = all clips audible; exit 1 = at least one silent/missing → fix with
add_sfx.py and re-run.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def _has_audio(path: Path) -> bool:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True)
    return bool(r.stdout.strip())


def _peak_db(path: Path) -> float:
    r = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "/dev/null"],
        capture_output=True, text=True)
    m = re.search(r"max_volume:\s*(-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else -99.0


def _collect(target: Path, fmt: str) -> list[Path]:
    if target.is_dir():
        return sorted(target.rglob("*.mov"))
    # manifest.json → resolve each entry's file for the format
    man = json.loads(target.read_text(encoding="utf-8"))
    out = []
    for e in man.get("entries", man.get("animations", [])):
        f = (e.get("files") or {}).get(fmt)
        if f:
            out.append(Path(f))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", type=Path, help="overlays dir OR overlays-manifest.json")
    ap.add_argument("--format", default="16x9", help="format key when target is a manifest")
    ap.add_argument("--min-peak", type=float, default=-45.0,
                    help="peak below this dB counts as SILENT (default -45)")
    ap.add_argument("--target", type=float, default=-25.0,
                    help="expected SFX peak dB (clips far below get a soft warning)")
    args = ap.parse_args()

    clips = _collect(args.target, args.format)
    if not clips:
        sys.exit(f"qc_audio: no .mov found under {args.target}")

    silent, noaudio, quiet, ok = [], [], [], 0
    for p in clips:
        if not p.exists():
            noaudio.append((p.name, "FILE MISSING"))
            continue
        if not _has_audio(p):
            noaudio.append((p.name, "no audio stream"))
            continue
        peak = _peak_db(p)
        if peak < args.min_peak:
            silent.append((p.name, peak))
        else:
            ok += 1
            if peak < args.target - 12:  # well below the -25 target → likely wrong/quiet sfx
                quiet.append((p.name, peak))

    print(f"qc_audio: {len(clips)} clips — {ok} audible, "
          f"{len(silent)} SILENT, {len(noaudio)} no-audio, {len(quiet)} quiet-warn",
          file=sys.stderr)
    for n, why in noaudio:
        print(f"  ✗ NO AUDIO  {n}  ({why})", file=sys.stderr)
    for n, pk in silent:
        print(f"  ✗ SILENT    {n}  (peak {pk:.0f} dB)", file=sys.stderr)
    for n, pk in quiet:
        print(f"  ! quiet     {n}  (peak {pk:.0f} dB, expected ~{args.target:.0f})", file=sys.stderr)

    if silent or noaudio:
        print("\nFIX: run  add_sfx.py <manifest> --sfx remotion/public/sfx  "
              "(bakes the type-mapped SFX into every clip), then re-run qc_audio.",
              file=sys.stderr)
        sys.exit(1)
    print("qc_audio OK — every overlay carries audible sound.", file=sys.stderr)


if __name__ == "__main__":
    main()
