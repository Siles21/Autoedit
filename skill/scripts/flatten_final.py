#!/usr/bin/env python3
"""flatten_final.py — composite the rendered alpha overlays onto the cut video and
write a FINISHED mp4 — fully headless, no Premiere, no plugin.

The overlays are ProRes 4444 with alpha + baked SFX. This delays each one to its
`atSeconds`, lays it over the base video (alpha-composited), mixes its SFX into the
base audio at the same time, and encodes one delivery mp4. This is the P0 step that
makes Premiere optional: the whole plugin/UDT path is bypassed for standard delivery.

    flatten_final.py --video final_cut.mp4 --overlays overlays-manifest.json \
        --out <name>_final.mp4 [--format 16x9] [--scale 1920] [--crf 18]
        [--start 0 --end 120]   # optional window (proof / chunking)

ffmpeg builds one filter_complex:
  video: [0:v] → chain overlay= per clip, each delayed via setpts, gated via enable
  audio: base [0:a] + each clip's audio adelay'd to atSeconds, amix (no re-normalise)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _probe_fps(video: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True, check=True)
    num, den = (r.stdout.strip().split("/") + ["1"])[:2]
    return int(num) / int(den)


def _probe(video: Path):
    """(width, height, fps, duration) of the base video — for push-in zoompan."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,r_frame_rate,duration:format=duration",
                        "-of", "json", str(video)], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout); s = d["streams"][0]
    num, den = (s["r_frame_rate"].split("/") + ["1"])[:2]
    dur = float(s.get("duration") or d["format"]["duration"])
    return int(s["width"]), int(s["height"]), int(num) / int(den), dur


def main() -> None:
    ap = argparse.ArgumentParser(description="Headless: composite overlays onto cut video → finished mp4")
    ap.add_argument("--video", type=Path, required=True, help="the cut/base video (final_cut.mp4)")
    ap.add_argument("--overlays", type=Path, required=True, help="overlays-manifest.json")
    ap.add_argument("--out", type=Path, required=True, help="output finished .mp4")
    ap.add_argument("--format", default="16x9")
    ap.add_argument("--scale", type=int, default=None, help="scale final WIDTH (e.g. 1920); default = source")
    ap.add_argument("--crf", type=int, default=18, help="x264 quality (lower=better, 18≈visually lossless)")
    ap.add_argument("--start", type=float, default=None, help="window start (s) — overlays rebased, base trimmed")
    ap.add_argument("--end", type=float, default=None, help="window end (s)")
    ap.add_argument("--no-audio-sfx", action="store_true", help="keep only base audio, skip overlay SFX mix")
    ap.add_argument("--max-duration", type=float, default=None, help="cap output length (s) — feasibility probe")
    ap.add_argument("--grade", action="store_true",
                    help="premium cinematic grade on the footage: cooler (~-10), +contrast (editing standard)")
    ap.add_argument("--push-in", type=float, default=0.0, metavar="AMT",
                    help="slow continuous Ken-Burns push-in on the footage (e.g. 0.08 = +8%% over the clip; 0=off). "
                         "Overlays stay pinned. 'Keine statischen Frames.'")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    man = json.loads(args.overlays.read_text(encoding="utf-8"))
    w0 = args.start or 0.0
    entries = []
    for e in man["entries"]:
        f = (e.get("files") or {}).get(args.format)
        if not f or not Path(f).exists():
            continue
        at = float(e["atSeconds"]); hold = float(e["hold"])
        if args.start is not None and at + hold < args.start:
            continue
        if args.end is not None and at > args.end:
            continue
        entries.append({"path": Path(f), "at": max(0.0, at - w0), "hold": hold, "id": e["id"]})
    if not entries:
        sys.exit("ERROR: no overlays in range")
    entries.sort(key=lambda x: x["at"])

    # ffmpeg inputs: base first, then each overlay
    cmd: list[str] = ["ffmpeg", "-y"]
    if args.start is not None:
        cmd += ["-ss", f"{args.start:.3f}"]
    if args.end is not None:
        cmd += ["-to", f"{args.end:.3f}"]
    cmd += ["-i", str(args.video)]
    for e in entries:
        cmd += ["-i", str(e["path"])]

    fc: list[str] = []
    # ---- base pre-filter: cinematic grade + slow push-in (overlays stay pinned) ----
    pre = []
    if args.grade:
        # cooler (~-10 temp) + lifted contrast — premium business look
        pre.append("eq=contrast=1.10:saturation=1.04:brightness=-0.012,"
                   "colorbalance=rm=-0.05:gm=-0.01:bm=0.06:rh=-0.03:bh=0.05")
    if args.push_in and args.push_in > 0:
        bw, bh, bfps, bdur = _probe(args.video)
        dur = (args.end if args.end is not None else bdur) - (args.start or 0.0)
        N = max(1, round(dur * bfps))
        amt = args.push_in
        pre.append(f"zoompan=z='min(1.0+{amt}*on/{N},{1.0 + amt:.4f})':"
                   f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={bw}x{bh}:fps={bfps:.4f}")
    prev = "0:v"
    if pre:
        fc.append(f"[0:v]{','.join(pre)}[base]")
        prev = "base"
    # ---- video chain ----
    for k, e in enumerate(entries, start=1):
        at = e["at"]; end = at + e["hold"]
        fc.append(f"[{k}:v]setpts=PTS-STARTPTS+{at:.3f}/TB[ov{k}]")
        outlbl = f"v{k}"
        fc.append(f"[{prev}][ov{k}]overlay=enable='between(t,{at:.3f},{end:.3f})':"
                  f"eof_action=pass:format=auto[{outlbl}]")
        prev = outlbl
    vlast = prev
    if args.scale:
        fc.append(f"[{vlast}]scale={args.scale}:-2[vout]")
        vlast = "vout"

    # ---- audio chain ----
    if args.no_audio_sfx:
        amap = ["-map", "0:a?"]
    else:
        amix_in = ["[0:a]"]
        for k, e in enumerate(entries, start=1):
            ms = int(e["at"] * 1000)
            fc.append(f"[{k}:a]adelay={ms}|{ms}[a{k}]")
            amix_in.append(f"[a{k}]")
        fc.append("".join(amix_in) + f"amix=inputs={len(amix_in)}:normalize=0:dropout_transition=0[aout]")
        amap = ["-map", "[aout]"]

    cmd += ["-filter_complex", ";".join(fc), "-map", f"[{vlast}]", *amap,
            "-c:v", "libx264", "-crf", str(args.crf), "-preset", "medium",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k",
            "-movflags", "+faststart"]
    if args.max_duration:
        cmd += ["-t", f"{args.max_duration:.3f}"]
    cmd += [str(args.out)]

    print(f"compositing {len(entries)} overlay(s) onto {args.video.name} → {args.out.name}", file=sys.stderr)
    if args.dry_run:
        print(" ".join(cmd[:25]) + f" ... ({len(cmd)} args)", file=sys.stderr)
        return
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(f"ERROR: ffmpeg failed (exit {r.returncode})")
    print(str(args.out))


if __name__ == "__main__":
    main()
