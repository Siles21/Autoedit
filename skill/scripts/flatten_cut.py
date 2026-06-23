#!/usr/bin/env python3
"""flatten_cut.py — turn an auto-cut result into a FLAT cut video + cut-relative
word timecodes. This is the missing handoff between the cut stage and sub-animations.

auto-cut-teleprompter writes `<video>.cuts.json` (keep-ranges in SOURCE time) and
caches `<video>.transcript.txt` (every word with source timecodes). This script:
  1. concatenates the kept ranges with ffmpeg → `final_cut.mp4` (the edited video)
  2. remaps every surviving word's timecode onto the CUT timeline → `words.json`
     (exactly the {words:[{text,start,end}]} shape build_plan.py/render expect)

So after a re-cut, the sub-animations pipeline runs against the real edit with
frame-accurate anchors — no Premiere, no manual transcript.

    flatten_cut.py --cuts <video>.cuts.json [--transcript <video>.transcript.txt] \
        --out <dir> [--crf 16] [--name final_cut]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _read_ranges(cuts: dict) -> list[tuple[float, float]]:
    rs = [(float(r["start"]), float(r["end"])) for r in cuts["ranges"] if r["end"] > r["start"]]
    rs.sort()
    return rs


def _read_words(transcript: Path) -> list[dict]:
    """Parse `<video>.transcript.txt` lines: '  start    end  text'."""
    words = []
    for line in transcript.read_text(encoding="utf-8").splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) < 3:
            continue
        try:
            s, e = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        words.append({"text": parts[2], "start": s, "end": e})
    return words


def _remap_words(words: list[dict], ranges: list[tuple[float, float]]) -> list[dict]:
    """Map each word that falls inside a kept range onto the cut timeline.
    A word's new time = kept-duration before its range + offset within the range.
    Words removed by the cut are dropped."""
    # cumulative kept duration before each range start
    cum = []
    acc = 0.0
    for (s, e) in ranges:
        cum.append(acc)
        acc += (e - s)
    out = []
    for w in words:
        ws, we = w["start"], w["end"]
        mid = (ws + we) / 2.0  # assign by word midpoint → robust to pad edges
        for i, (s, e) in enumerate(ranges):
            if s <= mid <= e:
                ns = cum[i] + max(0.0, ws - s)
                ne = cum[i] + min(e - s, we - s)
                out.append({"text": w["text"], "start": round(ns, 3), "end": round(max(ns, ne), 3)})
                break
    return out


def _build_cut_video(video: Path, ranges: list[tuple[float, float]], out: Path, crf: int) -> None:
    """Frame-accurate trim+concat of the kept ranges via one ffmpeg filter_complex."""
    parts = []
    labels = []
    for i, (s, e) in enumerate(ranges):
        parts.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    parts.append("".join(labels) + f"concat=n={len(ranges)}:v=1:a=1[v][a]")
    cmd = ["ffmpeg", "-y", "-i", str(video), "-filter_complex", ";".join(parts),
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", str(crf),
           "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k",
           "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(f"ERROR: ffmpeg cut/concat failed (exit {r.returncode})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Cut → flat video + cut-relative words.json")
    ap.add_argument("--cuts", type=Path, required=True, help="<video>.cuts.json from auto-cut")
    ap.add_argument("--transcript", type=Path, default=None,
                    help="<video>.transcript.txt (default: sibling of the video in cuts.json)")
    ap.add_argument("--out", type=Path, required=True, help="output dir")
    ap.add_argument("--name", default="final_cut", help="basename for outputs (default final_cut)")
    ap.add_argument("--crf", type=int, default=16, help="x264 quality for the cut video")
    ap.add_argument("--no-video", action="store_true", help="only write words.json (skip ffmpeg)")
    args = ap.parse_args()

    cuts = json.loads(args.cuts.read_text(encoding="utf-8"))
    video = Path(cuts["video"])
    if not video.exists():
        sys.exit(f"ERROR: source video not found: {video}")
    ranges = _read_ranges(cuts)
    if not ranges:
        sys.exit("ERROR: no keep-ranges in cuts.json")
    args.out.mkdir(parents=True, exist_ok=True)

    kept = sum(e - s for s, e in ranges)
    print(f"{len(ranges)} keep-range(s), {kept:.1f}s kept of {cuts.get('duration_in', 0):.1f}s", file=sys.stderr)

    # words.json (cut-relative)
    transcript = args.transcript or video.with_suffix(".transcript.txt")
    words_out = args.out / "words.json"
    if transcript.exists():
        words = _remap_words(_read_words(transcript), ranges)
        words_out.write_text(json.dumps({"words": words}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"remapped {len(words)} word(s) onto cut timeline → {words_out}", file=sys.stderr)
    else:
        print(f"WARN: no transcript at {transcript} — skipping words.json", file=sys.stderr)

    # final_cut.mp4
    if not args.no_video:
        vout = args.out / f"{args.name}.mp4"
        print(f"building cut video → {vout}", file=sys.stderr)
        _build_cut_video(video, ranges, vout, args.crf)
        print(str(vout))


if __name__ == "__main__":
    main()
