#!/usr/bin/env python3
"""align_words.py — Stage 1: word-level timecodes against the FINAL cut.

Runs faster-whisper on the already-edited / exported video so the timestamps
match the final Premiere timeline exactly. Emits words.json that build_plan.py
consumes. Uses the bundled, self-contained _whisper.py (ffprobe + faster-whisper).

    python3 align_words.py <final_video> [--out words.json] [--model large-v3]
                          [--lang de]

The transcript the user already has is NOT needed for timecodes — Whisper is the
ground truth here. Hand that transcript to Claude in Stage 2 for clean spelling
and correct figures.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Self-contained Whisper helpers live next to this file (no sibling-skill dep).
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _load_pipeline():
    try:
        from _whisper import probe, extract_audio, transcribe  # noqa: E402
    except Exception as exc:  # pragma: no cover - env dependent
        sys.exit(
            f"ERROR: could not import the bundled Whisper helpers ({exc}).\n"
            "Ensure faster-whisper + ffmpeg are installed "
            "(pip install -r requirements.txt; brew install ffmpeg)."
        )
    return probe, extract_audio, transcribe


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 1: Whisper word timecodes on the final cut")
    ap.add_argument("video", type=Path, help="final / exported video (matches the Premiere cut)")
    ap.add_argument("--out", type=Path, default=None, help="output words.json (default: <video>.words.json)")
    ap.add_argument("--model", default="large-v3", help="faster-whisper model (default large-v3)")
    ap.add_argument("--lang", default="de", help="language (default de)")
    args = ap.parse_args()

    if not args.video.exists():
        sys.exit(f"ERROR: video not found: {args.video}")

    probe, extract_audio, transcribe = _load_pipeline()

    meta = probe(args.video)
    print(f"probed: {meta.width}x{meta.height} @ {meta.fps:.3f}fps, {meta.duration:.1f}s",
          file=sys.stderr)

    wav = extract_audio(args.video)
    print(f"transcribing with {args.model} ({args.lang}) — this can take a while…",
          file=sys.stderr)
    words, full_text = transcribe(wav, model=args.model, language=args.lang)

    out = args.out or args.video.with_suffix(".words.json")
    payload = {
        "video": str(args.video.resolve()),
        "fps": meta.fps,
        "fps_num": meta.fps_num,
        "fps_den": meta.fps_den,
        "width": meta.width,
        "height": meta.height,
        "duration": meta.duration,
        "full_text": full_text,
        "words": [
            {"text": w.text, "start": round(w.start, 3), "end": round(w.end, 3),
             "confidence": round(w.confidence, 3)}
            for w in words
        ],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(words)} words → {out}", file=sys.stderr)
    print(str(out))


if __name__ == "__main__":
    main()
