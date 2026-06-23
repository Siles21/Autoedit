#!/usr/bin/env python3
"""reel_dynamics.py — give a (9:16) talking-head video the modern Reel motion:
continuous slow zoom IN/OUT (breathing) + occasional hard JUMP-CUTS, fully
automatic. No frames are removed → audio stays perfectly in sync.

The zoom is a per-frame crop+rescale, so it works on any clip without keyframing
in an editor. Jump-cuts are sudden zoom steps (the energetic "cut" feel) that
toggle every `--jump` seconds; the breathing is a slow sine over `--period`.

    reel_dynamics.py <video> --out <out.mp4>
        [--zoom 0.05]    # breathing amplitude (peak extra zoom)
        [--period 16]    # breathing in→out cycle seconds
        [--jump 12]      # seconds between jump-cuts (0 = no jump-cuts)
        [--jump-amt 0.07]# zoom step at each jump-cut
        [--base 1.04]    # constant minimum zoom (headroom for the crop)
        [--crf 18]

Pair with the 9:16 overlay render (face-aware placement) for the full Reel.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _probe(path: Path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,r_frame_rate",
                        "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    parts = [p for p in r.stdout.replace("\n", ",").split(",") if p]
    w, h = int(parts[0]), int(parts[1])
    fr = parts[2] if len(parts) > 2 else "30/1"
    fps = (float(fr.split("/")[0]) / float(fr.split("/")[1])) if "/" in fr else float(fr)
    dur = float(parts[3]) if len(parts) > 3 else 0.0
    return w, h, fps, dur


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--zoom", type=float, default=0.05, help="breathing amplitude")
    ap.add_argument("--period", type=float, default=16.0, help="in→out cycle seconds")
    ap.add_argument("--jump", type=float, default=12.0, help="seconds between jump-cuts (0=off)")
    ap.add_argument("--jump-amt", type=float, default=0.07, help="zoom step per jump-cut")
    ap.add_argument("--base", type=float, default=1.04, help="constant min zoom")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--has-audio", action="store_true", help="force copy audio")
    args = ap.parse_args()
    if not args.video.exists():
        sys.exit(f"reel_dynamics: not found: {args.video}")

    w, h, fps, _ = _probe(args.video)

    # Z(t): constant base + slow sine breathing (in/out) + a toggling jump step.
    # zoompan exposes the output frame index `on`, so time t = on/fps.
    pi2 = "6.28318530718"
    t = f"(on/{fps:.4f})"
    breath = f"{args.zoom}*sin({pi2}*{t}/{args.period})"
    jump = f"+{args.jump_amt}*mod(floor({t}/{args.jump})\\,2)" if args.jump > 0 else ""
    z = f"{args.base}+{args.zoom}+{breath}{jump}"   # always >= base >= 1.0

    # per-frame centred zoom via zoompan, output at the source size/fps.
    vf = (f"zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
          f"s={w}x{h}:fps={fps:.4f}")

    # detect audio for clean mapping
    ar = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                         "-show_entries", "stream=index", "-of", "csv=p=0", str(args.video)],
                        capture_output=True, text=True)
    has_a = bool(ar.stdout.strip())

    cmd = ["ffmpeg", "-y", "-i", str(args.video), "-vf", vf,
           "-c:v", "libx264", "-crf", str(args.crf), "-preset", "medium", "-pix_fmt", "yuv420p"]
    if has_a:
        cmd += ["-map", "0:v", "-map", "0:a", "-c:a", "copy"]
    else:
        cmd += ["-map", "0:v"]
    cmd.append(str(args.out))

    print(f"reel_dynamics: {w}x{h} zoom breathing ±{args.zoom} /{args.period}s"
          f"{f', jump-cut /{args.jump}s' if args.jump>0 else ', no jump-cuts'} → {args.out}",
          file=sys.stderr)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not args.out.exists():
        sys.exit("reel_dynamics: ffmpeg failed\n" + r.stderr[-1000:])
    print(f"reel_dynamics OK → {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
