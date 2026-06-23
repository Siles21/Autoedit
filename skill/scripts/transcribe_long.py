#!/usr/bin/env python3
"""transcribe_long.py — resumable long-audio transcription → words.json.

For 20–40 min webinars where one Whisper pass exceeds a single run budget. Splits
the audio into short chunks, transcribes each with openai-whisper (word-level
timestamps), offsets + merges, and writes words.json AFTER EVERY CHUNK plus a
.state.json — so a killed run resumes from the next chunk on re-invocation.

    transcribe_long.py <audio> <out.words.json> [model] [chunk_s]
    # e.g. transcribe_long.py "Grundkonzept v1.mp3" updated.words.json small 180
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def _dur(p: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True)
    return float(r.stdout.strip())


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit("usage: transcribe_long.py <audio> <out.words.json> [model=small] [chunk_s=180]")
    audio = Path(sys.argv[1])
    out = Path(sys.argv[2])
    model_name = sys.argv[3] if len(sys.argv) > 3 else "small"
    chunk_s = int(sys.argv[4]) if len(sys.argv) > 4 else 180
    state_path = out.with_suffix(".state.json")

    import whisper
    import torch

    total = _dur(audio)
    nchunks = int(total // chunk_s) + 1
    st = json.loads(state_path.read_text()) if state_path.exists() else {"done": [], "words": []}

    device = "cpu"
    try:
        if torch.backends.mps.is_available():
            device = "mps"
    except Exception:
        pass
    print(f"device={device} model={model_name} chunks={nchunks} total={total:.0f}s "
          f"(done={len(st['done'])})", file=sys.stderr)
    model = whisper.load_model(model_name, device=device)

    tmp = Path(tempfile.mkdtemp())
    for i in range(nchunks):
        if i in st["done"]:
            continue
        start = i * chunk_s
        seg = tmp / f"c{i}.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(start), "-t", str(chunk_s), "-i", str(audio),
             "-ac", "1", "-ar", "16000", str(seg)], check=True, capture_output=True)
        try:
            res = model.transcribe(str(seg), language="de", word_timestamps=True, fp16=False)
        except Exception as exc:
            print(f"chunk {i} failed on {device} ({exc}); retrying on cpu", file=sys.stderr)
            model = whisper.load_model(model_name, device="cpu")
            device = "cpu"
            res = model.transcribe(str(seg), language="de", word_timestamps=True, fp16=False)
        for sgm in res.get("segments", []):
            for w in sgm.get("words", []):
                t = (w.get("word") or "").strip()
                if not t:
                    continue
                st["words"].append({
                    "text": t, "start": round(float(w["start"]) + start, 3),
                    "end": round(float(w["end"]) + start, 3),
                    "confidence": round(float(w.get("probability", 1.0)), 3)})
        st["done"].append(i)
        st["words"].sort(key=lambda x: x["start"])
        state_path.write_text(json.dumps(st))
        payload = {"video": str(audio), "fps": None,
                   "duration": round(max((w["end"] for w in st["words"]), default=0.0), 2),
                   "full_text": " ".join(w["text"] for w in st["words"]),
                   "words": st["words"]}
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
        print(f"chunk {i + 1}/{nchunks} done — {len(st['words'])} words total", file=sys.stderr)

    print(f"ALL DONE: {len(st['words'])} words → {out}")


if __name__ == "__main__":
    main()
