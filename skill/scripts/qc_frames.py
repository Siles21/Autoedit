#!/usr/bin/env python3
"""qc_frames.py — VISUAL QC: render one representative frame of every overlay
composited over its ACTUAL video moment, tiled into a contact sheet for review.

This is what catches the bugs deterministic checks miss — an empty scrim with no
text, a strap pushed off the bottom edge, text over the face, low contrast on a
bright background, a blank/failed render. The reviewer (Claude / Simon) looks at
the sheet against references/qc-checklist.md before the video ships.

    qc_frames.py --video <final.mp4> --overlays <overlays-manifest.json> \
        --out <sheet.png> [--format 16x9] [--cols 4] [--thumb 520]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_FONTS = ["/System/Library/Fonts/Supplemental/Arial.ttf",
          "/System/Library/Fonts/Helvetica.ttc",
          "/Library/Fonts/Arial.ttf"]


def _font() -> str | None:
    for f in _FONTS:
        if Path(f).exists():
            return f
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Visual QC contact sheet")
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--overlays", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--format", default="16x9")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--thumb", type=int, default=520, help="thumb width px")
    args = ap.parse_args()

    man = json.loads(args.overlays.read_text(encoding="utf-8"))
    entries = [e for e in man["entries"] if (e.get("files") or {}).get(args.format)]
    entries.sort(key=lambda e: float(e["atSeconds"]))
    if not entries:
        sys.exit("ERROR: no overlays")

    tw = args.thumb; th = round(tw * 9 / 16) if args.format == "16x9" else round(tw * 16 / 9)
    font = _font()
    tmp = Path(tempfile.mkdtemp())
    thumbs = []

    for i, e in enumerate(entries):
        ov = Path(e["files"][args.format])
        hold = float(e["hold"]); at = float(e["atSeconds"])
        local = min(0.6 * hold, max(0.1, hold - 0.25))     # frame where content is up
        tvid = at + local
        out = tmp / f"{i:03d}.png"
        # grid order == the printed legend order (this ffmpeg has no drawtext filter)
        fc = (f"[0:v]scale={tw}:{th},setsar=1[bg];[1:v]scale={tw}:{th}[ov];"
              f"[bg][ov]overlay=format=auto[v]")
        r = subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{tvid:.3f}", "-i", str(args.video),
             "-ss", f"{local:.3f}", "-i", str(ov),
             "-filter_complex", fc, "-map", "[v]", "-frames:v", "1", str(out)],
            capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            print(f"  WARN thumb failed: {e['id']} — {r.stderr[-160:]}", file=sys.stderr)
            continue
        thumbs.append(out)

    if not thumbs:
        sys.exit("ERROR: no thumbs rendered")

    # renumber sequentially for the tile demuxer, then tile
    seq = Path(tempfile.mkdtemp())
    for j, t in enumerate(thumbs):
        (seq / f"{j:03d}.png").write_bytes(t.read_bytes())
    rows = (len(thumbs) + args.cols - 1) // args.cols
    args.out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["ffmpeg", "-y", "-framerate", "1", "-i", str(seq / "%03d.png"),
         "-frames:v", "1", "-vf", f"tile={args.cols}x{rows}:padding=6:color=0x222222",
         str(args.out)], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ERROR: tile failed — {r.stderr[-200:]}")
    print(f"contact sheet: {len(thumbs)} overlays over their real video moment → {args.out}", file=sys.stderr)
    print("LEGENDE (Index → id @Zeit):", file=sys.stderr)
    for i, e in enumerate(entries):
        at = float(e["atSeconds"])
        print(f"  {i:02d}  {e['id']:24s} @{int(at//60)}:{int(at%60):02d}  {e['type']}", file=sys.stderr)
    print("Review against references/qc-checklist.md (esp. [vis] items).", file=sys.stderr)
    print(str(args.out))


if __name__ == "__main__":
    main()
