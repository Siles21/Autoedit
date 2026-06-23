#!/usr/bin/env python3
"""add_music.py — bake an OPT-IN background music bed under a finished video.

NOT a default step. Mix a music track under the existing voice, automatically
DUCKED (sidechain compression) so it drops whenever someone speaks and lifts in
the gaps — the standard premium music-bed feel. Music is looped to the video
length, faded in/out, and held low (default -20 dB) so it never fights the voice.

    add_music.py <video> --music <bed.mp3> --out <out.mp4>
        [--gain -20] [--duck 6] [--fade 2.0] [--reencode-video]

Default copies the video stream (fast); --reencode-video re-encodes if needed.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _has_audio(path: Path) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                        "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--music", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--gain", type=float, default=-20.0, help="base music level dB (default -20)")
    ap.add_argument("--duck", type=float, default=6.0, help="ducking ratio under voice (default 6)")
    ap.add_argument("--fade", type=float, default=2.0, help="fade in/out seconds")
    ap.add_argument("--reencode-video", action="store_true")
    args = ap.parse_args()
    for p in (args.video, args.music):
        if not p.exists():
            sys.exit(f"add_music: not found: {p}")

    dur = _duration(args.video)
    fo = max(0.0, dur - args.fade)
    voiced = _has_audio(args.video)

    # music: loop to length, level, fade in/out
    music_chain = (f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                   f"volume={args.gain}dB,afade=t=in:st=0:d={args.fade},"
                   f"afade=t=out:st={fo:.2f}:d={args.fade}[m]")

    if voiced:
        # split the voice (used twice: as sidechain key AND in the final mix),
        # duck the music by the voice, then mix both.
        fc = (f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[v1][v2];" + music_chain +
              f";[m][v1]sidechaincompress=threshold=0.03:ratio={args.duck}:attack=20:release=400[md];"
              f"[md][v2]amix=inputs=2:duration=first:dropout_transition=0,"
              f"alimiter=limit=0.97[a]")
    else:
        fc = music_chain + ";[m]alimiter=limit=0.97[a]"

    cmd = ["ffmpeg", "-y", "-i", str(args.video), "-stream_loop", "-1", "-i", str(args.music),
           "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
           "-c:a", "aac", "-b:a", "320k", "-shortest"]
    cmd += (["-c:v", "libx264", "-crf", "18", "-preset", "medium"]
            if args.reencode_video else ["-c:v", "copy"])
    cmd.append(str(args.out))
    print(f"add_music: {args.music.name} under {'voice (ducked)' if voiced else 'silent video'} "
          f"@ {args.gain}dB → {args.out}", file=sys.stderr)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not args.out.exists():
        sys.exit("add_music: ffmpeg failed\n" + r.stderr[-800:])
    print(f"add_music OK → {args.out} ({_duration(args.out):.1f}s)", file=sys.stderr)


if __name__ == "__main__":
    main()
