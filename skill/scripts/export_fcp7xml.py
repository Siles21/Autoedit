#!/usr/bin/env python3
"""export_fcp7xml.py — write a Final Cut Pro 7 XML (xmeml) that Premiere imports.

Premiere Pro dropped .fcpxml import but still reads the legacy FCP7 'xmeml' .xml.
This builds a sequence: source video on V1, all overlays packed onto the fewest
graphics tracks (V2..Vk via greedy interval scheduling) at their timecodes. The
ProRes 4444 alpha composites over the video automatically.

    export_fcp7xml.py <animation-plan.json> --video <final.mp4> \
        --overlays <overlays-manifest.json> --out <dir> [--format 16x9] [--clip-fps 30]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape


def _probe(video: Path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,r_frame_rate,duration:format=duration",
                        "-of", "json", str(video)], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout); s = d["streams"][0]
    num, den = (s["r_frame_rate"].split("/") + ["1"])[:2]
    fps = round(int(num) / int(den))
    dur = float(s.get("duration") or d["format"]["duration"])
    return int(s["width"]), int(s["height"]), fps, dur


def _has_audio(p: Path) -> bool:
    """True if the file carries at least one audio stream (so we only emit audio
    clipitems for clips that actually have sound — VO footage + SFX overlays)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                        "-show_entries", "stream=index", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def _pathurl(p: Path) -> str:
    return "file://localhost" + quote(str(p.resolve()))


def _pack_tracks(clips: list[dict]) -> list[list[dict]]:
    """Greedy interval scheduling: each clip onto the lowest track whose last
    clip already ended. Minimises track count (== max simultaneous overlays)."""
    tracks: list[list[dict]] = []
    for c in sorted(clips, key=lambda x: x["start"]):
        placed = False
        for tr in tracks:
            if tr[-1]["end"] <= c["start"]:
                tr.append(c); placed = True; break
        if not placed:
            tracks.append([c])
    return tracks


def _file_el(fid: str, path: Path, name: str, frames: int, fps: int, w: int, h: int,
             defined: set, has_audio: bool = False) -> str:
    """A <file> element — full definition (video + optional audio media) on first
    use, ref afterwards."""
    if fid in defined:
        return f'<file id="{fid}"/>'
    defined.add(fid)
    audio_media = (
        '<audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate>'
        '</samplecharacteristics><channelcount>2</channelcount></audio>'
    ) if has_audio else ""
    return (
        f'<file id="{fid}"><name>{escape(name)}</name>'
        f'<pathurl>{escape(_pathurl(path))}</pathurl>'
        f'<rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>'
        f'<duration>{frames}</duration>'
        f'<media><video><samplecharacteristics><width>{w}</width><height>{h}</height>'
        f'</samplecharacteristics></video>{audio_media}</media></file>')


def _links(base: str, vti: int, ci: int, has_audio: bool) -> str:
    """<link> blocks pairing a clip's video + audio clipitems so Premiere treats
    them as ONE movable unit. trackindex/clipindex mirror across media types."""
    lk = (f'<link><linkclipref>{base}_v</linkclipref><mediatype>video</mediatype>'
          f'<trackindex>{vti}</trackindex><clipindex>{ci}</clipindex></link>')
    if has_audio:
        lk += (f'<link><linkclipref>{base}_a</linkclipref><mediatype>audio</mediatype>'
               f'<trackindex>{vti}</trackindex><clipindex>{ci}</clipindex></link>')
    return lk


def _clip_pair(base: str, name: str, file_def: str, fps: int, start: int, end: int,
               out_f: int, vti: int, ci: int, has_audio: bool):
    """Return (video_clipitem, audio_clipitem|"") for one clip. The video clipitem
    carries the full <file> definition; the audio clipitem references it by id and
    sources its audio via <sourcetrack>. Both share <link> blocks."""
    links = _links(base, vti, ci, has_audio)
    body = (f'<enabled>TRUE</enabled><duration>{out_f}</duration>'
            f'<rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>'
            f'<start>{start}</start><end>{end}</end><in>0</in><out>{out_f}</out>')
    vid = (f'<clipitem id="{base}_v"><name>{escape(name)}</name>{body}'
           f'{file_def}{links}</clipitem>')
    aud = ""
    if has_audio:
        aud = (f'<clipitem id="{base}_a"><name>{escape(name)}</name>{body}'
               f'<file id="{escape(base)}"/>'
               f'<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>'
               f'{links}</clipitem>')
    return vid, aud


def main() -> None:
    ap = argparse.ArgumentParser(description="Export FCP7 XML (xmeml) for Premiere import")
    ap.add_argument("plan", type=Path)
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--overlays", type=Path, required=True, help="overlays-manifest.json")
    ap.add_argument("--out", type=Path, required=True, help="output dir")
    ap.add_argument("--format", default="16x9")
    ap.add_argument("--clip-fps", type=int, default=30, help="fps the overlays were rendered at")
    args = ap.parse_args()

    w, h, seq_fps, vdur = _probe(args.video)
    manifest = json.loads(args.overlays.read_text(encoding="utf-8"))
    fmt = args.format

    clips = []
    for e in manifest["entries"]:
        f = (e.get("files") or {}).get(fmt)
        if not f:
            continue
        at = float(e["atSeconds"]); hold = float(e["hold"])
        clips.append({"id": e["id"], "path": Path(f), "hold": hold,
                      "start": round(at * seq_fps), "end": round((at + hold) * seq_fps),
                      "audio": _has_audio(Path(f))})
    if not clips:
        sys.exit(f"ERROR: no overlay files for format {fmt}")

    tracks = _pack_tracks(clips)
    seq_frames = max(round(vdur * seq_fps), max(c["end"] for c in clips))
    defined: set = set()
    foot_audio = _has_audio(args.video)
    n_audio = 0

    # V1 + A1: source video (footage carries the voiceover)
    vend = round(vdur * seq_fps)
    vfile = _file_el("vid", args.video, args.video.name, seq_frames, seq_fps, w, h, defined, foot_audio)
    fv, fa = _clip_pair("vid", args.video.stem, vfile, seq_fps, 0, vend, vend, 1, 1, foot_audio)
    video_tracks = [f"<track>{fv}</track>"]
    audio_tracks = [f"<track>{fa}</track>"]
    if foot_audio:
        n_audio += 1

    # V2..Vk + A2..Ak: overlays (audio mirrors the video track packing)
    for ti, tr in enumerate(tracks):
        vti = ti + 2
        vitems, aitems = [], []
        for ci, c in enumerate(tr, start=1):
            cf = round(c["hold"] * args.clip_fps)  # clip-local out (source frames)
            fel = _file_el(c["id"], c["path"], c["path"].name, cf, args.clip_fps, w, h, defined, c["audio"])
            v, a = _clip_pair(c["id"], c["id"], fel, args.clip_fps, c["start"], c["end"], cf, vti, ci, c["audio"])
            vitems.append(v)
            if a:
                aitems.append(a); n_audio += 1
        video_tracks.append("<track>" + "".join(vitems) + "</track>")
        audio_tracks.append("<track>" + "".join(aitems) + "</track>")

    audio_section = (
        '<audio><numOutputChannels>2</numOutputChannels>'
        '<format><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate>'
        '</samplecharacteristics></format>'
        + "".join(audio_tracks) +
        '</audio>'
    )
    seq_xml = (
        f'<sequence id="seq"><name>{escape(args.video.stem)} + Grafiken</name>'
        f'<duration>{seq_frames}</duration>'
        f'<rate><timebase>{seq_fps}</timebase><ntsc>FALSE</ntsc></rate>'
        '<media><video>'
        f'<format><samplecharacteristics><width>{w}</width><height>{h}</height>'
        f'<rate><timebase>{seq_fps}</timebase><ntsc>FALSE</ntsc></rate>'
        '</samplecharacteristics></format>'
        + "".join(video_tracks) +
        '</video>' + audio_section + '</media></sequence>')

    # Master clips for the overlays, grouped in a sub-bin → on import everything
    # lands tidily in ONE folder instead of 175 loose items at the project root.
    # Files are already defined (first use) inside the sequence above; here we
    # only reference them by id.
    master = []
    for c in clips:
        cf = round(c["hold"] * args.clip_fps)
        master.append(
            f'<clip id="mc_{escape(c["id"])}"><name>{escape(c["id"])}</name>'
            f'<duration>{cf}</duration>'
            f'<rate><timebase>{args.clip_fps}</timebase><ntsc>FALSE</ntsc></rate>'
            f'<file id="{escape(c["id"])}"/></clip>')
    sub_bin = (f'<bin><name>Grafik-Overlays ({len(clips)})</name>'
               f'<children>{"".join(master)}</children></bin>')
    top_bin = (f'<bin><name>{escape(args.video.stem)} — Sub-Animationen</name>'
               f'<children>{seq_xml}{sub_bin}</children></bin>')

    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">\n'
           + top_bin + '\n</xmeml>\n')

    out = args.out / "overlays.fcp7.xml"
    out.write_text(xml, encoding="utf-8")
    print(f"FCP7 XML: {len(clips)} overlays on {len(tracks)} graphics track(s) "
          f"+ {n_audio} audio clip(s) (VO + SFX) "
          f"({w}x{h} @ {seq_fps}fps, {seq_frames} frames) → {out}", file=sys.stderr)
    print(str(out))


if __name__ == "__main__":
    main()
