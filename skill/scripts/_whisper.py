"""_whisper.py — self-contained ffprobe/ffmpeg + faster-whisper helpers.

Vendored so this skill has NO dependency on any sibling skill. Provides exactly
what Stage 1 (align_words.py) and the ffprobe wrapper in integrate.py need:

    probe(video)          -> VideoMeta(width, height, fps_num, fps_den, duration, fps)
    extract_audio(video)  -> Path to a mono 16 kHz WAV
    transcribe(wav, ...)  -> (list[Word], full_text)

Requires: ffmpeg + ffprobe on PATH (brew install ffmpeg) and faster-whisper
(pip install -r requirements.txt). The faster-whisper import is lazy so the
ffprobe-only callers (integrate.py) work without it installed.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class FFmpegMissing(RuntimeError):
    pass


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise FFmpegMissing(f"{tool} not found. Install with: brew install ffmpeg")
    return path


@dataclass(frozen=True)
class VideoMeta:
    duration: float
    width: int
    height: int
    fps_num: int
    fps_den: int

    @property
    def fps(self) -> float:
        return self.fps_num / self.fps_den


@dataclass(frozen=True)
class Word:
    """One word from the Whisper transcript."""
    text: str
    start: float
    end: float
    confidence: float = 1.0


def probe(video: Path) -> VideoMeta:
    """Read width/height/fps/duration via ffprobe."""
    ffprobe = _require("ffprobe")
    result = subprocess.run(
        [
            ffprobe, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,duration:format=duration",
            "-of", "json",
            str(video),
        ],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    width = int(stream["width"])
    height = int(stream["height"])
    fps_str = stream["r_frame_rate"]
    num_str, den_str = fps_str.split("/")
    fps_num, fps_den = int(num_str), int(den_str)
    duration = float(stream.get("duration") or data["format"]["duration"])
    return VideoMeta(duration=duration, width=width, height=height,
                     fps_num=fps_num, fps_den=fps_den)


def extract_audio(video: Path, out_dir: Path | None = None) -> Path:
    """Extract mono 16kHz WAV audio (whisper-friendly). Returns path."""
    ffmpeg = _require("ffmpeg")
    out_dir = out_dir or Path(tempfile.mkdtemp(prefix="sub-anim-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (video.stem + ".wav")
    subprocess.run(
        [
            ffmpeg, "-y", "-i", str(video),
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
            str(out),
        ],
        check=True, capture_output=True,
    )
    return out


def transcribe(
    audio: Path,
    *,
    model: str = "large-v3",
    language: str = "de",
    compute_type: str = "int8",
) -> tuple[list[Word], str]:
    """Run faster-whisper, return (words, full_text).

    `compute_type='int8'` runs well on Apple Silicon CPU — large-v3 stays
    under 4 GB RAM and gives word-level timestamps without a GPU.
    """
    from faster_whisper import WhisperModel  # local import — heavy dep

    whisper = WhisperModel(model, device="cpu", compute_type=compute_type)
    segments, _info = whisper.transcribe(
        str(audio),
        language=language,
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
    )

    words: list[Word] = []
    full_text_parts: list[str] = []
    for seg in segments:
        full_text_parts.append(seg.text.strip())
        if not seg.words:
            continue
        for w in seg.words:
            if w.start is None or w.end is None:
                continue
            words.append(Word(
                text=w.word.strip(),
                start=float(w.start),
                end=float(w.end),
                confidence=float(getattr(w, "probability", 1.0) or 1.0),
            ))
    return words, " ".join(full_text_parts)
