#!/usr/bin/env python3
"""add_sfx.py — bake a per-type sound effect into each rendered overlay .mov.

Remotion ProRes renders carry a SILENT audio track. This replaces it with a
type-mapped SFX, normalised to a target peak (default -25 dB so it never
overpowers the voice), placed at the clip's entrance and padded with silence to
the clip length. Video stream is COPIED (no re-render); audio is replaced, so
re-running is idempotent (sfx is never stacked on sfx).

    add_sfx.py <overlays-manifest.json> --sfx <remotion/public/sfx> [--peak -25]
        [--format 16x9] [--only id1,id2] [--dry-run]

The .mov files are edited in place (via a temp file + atomic replace). The
Premiere XML keeps pointing at the same filenames, now with sound.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Which SFX each animation type gets. Files live in <sfx>/<name>.wav.
TYPE_SFX = {
    "kpibig": "pop",        # hero number — punch
    "stat": "soft",         # small stat — subtle
    "lowerthird": "soft",   # name/title strap — subtle (most common, must not nag)
    "reveal": "whoosh",     # something appears — movement
    "sequence": "tick",     # multi-step build — click
    "enumeration": "tick",  # list build — click
    "comparebars": "riser", # before/after — tension
    "chart": "riser",       # data grows — tension
    "comparetable": "tick", # table rows build one-by-one — click
    "comparecards": "riser",# two cards clash (vs) — tension
    "splitheadline": "whoosh", # hook headline swipes in
    "fullcard": "whoosh",   # full-frame card transition
    "accentbar": "pop",     # red accent block punches in
    "cta": "pop",           # button appears — punch
    # NOTE: unknown types fall back to "soft" (TYPE_SFX.get(t, "soft")) so a new
    # type is NEVER silent — but add its proper mapping here. Keep in sync with
    # remotion/src/types.ts OverlayType.
}


def _peak_db(path: Path) -> float:
    r = subprocess.run(["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "/dev/null"],
                       capture_output=True, text=True)
    m = re.search(r"max_volume:\s*(-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else -99.0


def normalise_sfx(sfx_dir: Path, peak: float) -> dict[str, Path]:
    """Make a copy of each SFX with its peak shifted to exactly `peak` dB.
    Cached under <sfx>/.norm-<peak>/ so we only compute the gain once."""
    cache = sfx_dir / f".norm{peak:g}"
    cache.mkdir(exist_ok=True)
    out: dict[str, Path] = {}
    for name in sorted(set(TYPE_SFX.values())):
        src = sfx_dir / f"{name}.wav"
        if not src.exists():
            sys.exit(f"ERROR: missing SFX {src}")
        dst = cache / f"{name}.wav"
        if not dst.exists():
            gain = peak - _peak_db(src)
            subprocess.run(["ffmpeg", "-y", "-i", str(src), "-af", f"volume={gain:.2f}dB",
                            "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(dst)],
                           capture_output=True, text=True, check=True)
            print(f"  normalised {name}: {gain:+.2f} dB → peak {peak:g} dB", file=sys.stderr)
        out[name] = dst
    return out


def mux_one(mov: Path, sfx: Path, hold: float) -> None:
    """Replace the .mov's audio with `sfx` at t=0, padded with silence to `hold`."""
    tmp = mov.with_suffix(".sfx.mov")
    cmd = ["ffmpeg", "-y", "-i", str(mov), "-i", str(sfx),
           "-filter_complex",
           f"[1:a]apad,atrim=0:{hold:.3f},aformat=sample_rates=48000:channel_layouts=stereo[a]",
           "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "pcm_s16le",
           "-shortest", str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        sys.exit(f"ERROR: ffmpeg mux failed for {mov.name}\n{r.stderr[-600:]}")
    tmp.replace(mov)


def main() -> None:
    ap = argparse.ArgumentParser(description="Bake per-type SFX into rendered overlays")
    ap.add_argument("manifest", type=Path, help="overlays-manifest.json")
    ap.add_argument("--sfx", type=Path, required=True, help="dir with pop/soft/whoosh/tick/riser .wav")
    ap.add_argument("--peak", type=float, default=-16.0, help="target peak dB (default -16 — audible under VO; -25 was inaudible)")
    ap.add_argument("--format", default="16x9")
    ap.add_argument("--only", default=None, help="comma-separated entry ids")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    man = json.loads(args.manifest.read_text(encoding="utf-8"))
    only = {x.strip() for x in args.only.split(",")} if args.only else None
    norm = normalise_sfx(args.sfx, args.peak) if not args.dry_run else {}

    done = skipped = 0
    for e in man["entries"]:
        if only and e["id"] not in only:
            continue
        f = (e.get("files") or {}).get(args.format)
        if not f or not Path(f).exists():
            print(f"  skip {e['id']}: no {args.format} file", file=sys.stderr)
            skipped += 1
            continue
        sfx_name = TYPE_SFX.get(e["type"], "soft")
        if args.dry_run:
            print(f"  {e['id']:28s} {e['type']:12s} → {sfx_name}", file=sys.stderr)
            done += 1
            continue
        mux_one(Path(f), norm[sfx_name], float(e["hold"]))
        done += 1
        if done % 25 == 0:
            print(f"  …{done} muxed", file=sys.stderr)

    print(f"SFX baked into {done} clip(s), skipped {skipped} "
          f"(peak {args.peak:g} dB) — format {args.format}", file=sys.stderr)


if __name__ == "__main__":
    main()
