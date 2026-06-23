#!/usr/bin/env python3
"""premiere_transcript.py — Premiere text-based-editing export → words.json.

A Whisper-free Stage-1 alternative: when Premiere has already transcribed the
SEQUENCE (Text-based Editing), its JSON export carries word-level start/duration
against the cut timeline — exactly what we need. Use this instead of
align_words.py when such a transcript exists.

    premiere_transcript.py <transcript.json> [--out words.json]
    premiere_transcript.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def to_words(data: dict) -> dict:
    """Flatten Premiere's {segments:[{words:[{text,start,duration,confidence}]}]}
    into our words.json shape. Word `start` is absolute on the sequence."""
    words: list[dict] = []
    for seg in data.get("segments", []):
        for w in seg.get("words", []):
            t = (w.get("text") or "").strip()
            if not t:
                continue
            try:
                st = float(w["start"])
            except (KeyError, TypeError, ValueError):
                continue
            du = float(w.get("duration", 0) or 0)
            words.append({
                "text": t, "start": round(st, 3), "end": round(st + du, 3),
                "confidence": round(float(w.get("confidence", 1) or 1), 3),
            })
    words.sort(key=lambda x: x["start"])
    full = " ".join(w["text"] for w in words)
    dur = round(max((w["end"] for w in words), default=0.0), 2)
    return {"video": None, "fps": None, "width": 1920, "height": 1080,
            "duration": dur, "full_text": full, "words": words}


def _selftest() -> None:
    sample = {"segments": [
        {"start": 0, "words": [
            {"text": "Die", "start": 0.0, "duration": 0.1, "confidence": 0.8},
            {"text": "Rendite", "start": 0.2, "duration": 0.5, "confidence": 1.0}]},
        {"start": 1.0, "words": [
            {"text": "4,2", "start": 1.0, "duration": 0.3, "confidence": 1.0},
            {"text": "Prozent", "start": 1.3, "duration": 0.4, "confidence": 1.0}]},
    ]}
    out = to_words(sample)
    assert [w["text"] for w in out["words"]] == ["Die", "Rendite", "4,2", "Prozent"], out
    assert out["words"][2]["start"] == 1.0 and out["words"][2]["end"] == 1.3
    assert out["duration"] == 1.7
    assert out["full_text"] == "Die Rendite 4,2 Prozent"
    print("premiere_transcript selftest OK")


def main() -> None:
    ap = argparse.ArgumentParser(description="Premiere transcript JSON → words.json")
    ap.add_argument("transcript", nargs="?", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
        return
    if not args.transcript:
        ap.error("transcript path required (or --selftest)")
    data = json.loads(args.transcript.read_text(encoding="utf-8"))
    payload = to_words(data)
    if not payload["words"]:
        sys.exit("ERROR: no words found in transcript")
    out = args.out or args.transcript.with_suffix(".words.json")
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(payload['words'])} words → {out}", file=sys.stderr)
    print(str(out))


if __name__ == "__main__":
    main()
