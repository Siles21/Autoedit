#!/usr/bin/env python3
"""make_captions.py — words.json → word-by-word caption chunks (Editing-Standard).

Groups the transcript into short caption chunks (a few words each, broken at
pauses) and writes them as `type:"caption"` plan entries. Each entry's
content.words carry CLIP-RELATIVE times, so the Captions component highlights the
spoken word. Rendered like any overlay; placed on a caption track in Premiere.

    make_captions.py <words.json> --out captions-plan.json [--start S --end E]
        [--max-words 5] [--max-span 2.6] [--gap 0.45] [--lead 0.1]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def chunk_words(words, max_words, max_span, gap):
    chunks, cur = [], []
    for w in words:
        if cur:
            prev = cur[-1]
            span = w["end"] - cur[0]["start"]
            if (len(cur) >= max_words or (w["start"] - prev["end"]) > gap or span > max_span):
                chunks.append(cur); cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcript → caption chunks plan")
    ap.add_argument("words", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--start", type=float, default=None)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--max-words", type=int, default=5)
    ap.add_argument("--max-span", type=float, default=2.6)
    ap.add_argument("--gap", type=float, default=0.45)
    ap.add_argument("--lead", type=float, default=0.1, help="caption appears this much before its first word")
    ap.add_argument("--tail", type=float, default=0.25, help="caption lingers this long after its last word")
    args = ap.parse_args()

    words = json.loads(args.words.read_text(encoding="utf-8")).get("words", [])
    words = [{"text": w["text"].strip(), "start": float(w["start"]), "end": float(w["end"])}
             for w in words if w.get("text", "").strip()]
    if args.start is not None:
        words = [w for w in words if w["end"] >= args.start]
    if args.end is not None:
        words = [w for w in words if w["start"] <= args.end]
    if not words:
        sys.exit("ERROR: no words in range")

    chunks = chunk_words(words, args.max_words, args.max_span, args.gap)
    anims = []
    for i, ch in enumerate(chunks):
        c0 = ch[0]["start"] - args.lead
        at = max(0.0, c0)
        end = ch[-1]["end"] + args.tail
        hold = round(end - at, 3)
        rel = [{"text": w["text"], "start": round(w["start"] - at, 3), "end": round(w["end"] - at, 3)}
               for w in ch]
        anims.append({
            "id": f"cap{i:04d}",
            "type": "caption",
            "atSeconds": round(at, 2),
            "hold": hold,
            "anchorPhrase": " ".join(w["text"] for w in ch[:5]),
            "content": {"words": rel},
        })
    out = {"_captions": True, "animations": anims}
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(anims)} caption chunks ({len(words)} words) → {args.out}", file=sys.stderr)
    print(str(args.out))


if __name__ == "__main__":
    main()
