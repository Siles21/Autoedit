#!/usr/bin/env python3
"""export_cut_xml.py — FCP7 XML that is a PRE-CUT, EDITABLE sequence + animations.

Weg A (Simon, 2026-06-11): instead of razor-cutting a live sequence (AutoCut's
CEP/ExtendScript/QE route), we express the cut directly in an FCP7 xmeml that
Premiere imports. Each kept range from the auto-cut becomes its OWN clipitem on
V1 (video) + linked A1/A2 (audio) — so the cut points are real edit points the
user can still trim/nudge. Overlays sit on V2.. at their CUT-RELATIVE timecodes.

    export_cut_xml.py --video <source.mp4> --cuts <video>.cuts.json \
        [--overlays <overlays-manifest.json>] --out <dir> [--format 16x9] [--clip-fps 30]

cuts.json (from auto-cut-teleprompter) carries `ranges:[{start,end}]` in SOURCE
seconds. Overlay atSeconds must already be CUT-RELATIVE (author the plan on the
words.json that flatten_cut.py remapped onto the cut timeline).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from export_fcp7xml import _probe, _pathurl, _pack_tracks, _file_el, _clipitem


def _av_clip(idx: int, src_id: str, name: str, fps: int,
             tl_start: int, tl_end: int, in_f: int, out_f: int,
             src_file_el: str) -> tuple[str, str, str]:
    """One kept range as linked video + 2 audio clipitems (stereo). Returns
    (video_clipitem, audio1_clipitem, audio2_clipitem). The <link> blocks tie
    them so Premiere keeps them grouped and editable as one clip."""
    vid = f"v1_{idx}"; a1 = f"a1_{idx}"; a2 = f"a2_{idx}"
    dur = out_f - in_f
    links = (
        f'<link><linkclipref>{vid}</linkclipref><mediatype>video</mediatype>'
        f'<trackindex>1</trackindex><clipindex>{idx+1}</clipindex></link>'
        f'<link><linkclipref>{a1}</linkclipref><mediatype>audio</mediatype>'
        f'<trackindex>1</trackindex><clipindex>{idx+1}</clipindex></link>'
        f'<link><linkclipref>{a2}</linkclipref><mediatype>audio</mediatype>'
        f'<trackindex>2</trackindex><clipindex>{idx+1}</clipindex></link>')

    def clip(cid: str, mediatype: str, trackidx: int, file_el: str) -> str:
        st = (f'<sourcetrack><mediatype>{mediatype}</mediatype>'
              f'<trackindex>{trackidx}</trackindex></sourcetrack>') if mediatype == "audio" else ""
        return (
            f'<clipitem id="{cid}"><name>{escape(name)}</name><enabled>TRUE</enabled>'
            f'<duration>{dur}</duration><rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>'
            f'<start>{tl_start}</start><end>{tl_end}</end><in>{in_f}</in><out>{out_f}</out>'
            f'{file_el}{st}{links}</clipitem>')

    return (clip(vid, "video", 1, src_file_el),
            clip(a1, "audio", 1, f'<file id="{src_id}"/>'),
            clip(a2, "audio", 2, f'<file id="{src_id}"/>'))


def main() -> None:
    ap = argparse.ArgumentParser(description="FCP7 XML: editable pre-cut + animations")
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--cuts", type=Path, required=True, help="<video>.cuts.json (keep-ranges, source seconds)")
    ap.add_argument("--overlays", type=Path, default=None, help="overlays-manifest.json (cut-relative atSeconds)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--format", default="16x9")
    ap.add_argument("--clip-fps", type=int, default=30, help="fps the overlays were rendered at")
    args = ap.parse_args()

    w, h, seq_fps, vdur = _probe(args.video)
    cuts = json.loads(args.cuts.read_text(encoding="utf-8"))
    ranges = sorted(((float(r["start"]), float(r["end"])) for r in cuts["ranges"] if r["end"] > r["start"]))
    if not ranges:
        sys.exit("ERROR: no keep-ranges in cuts.json")

    defined: set = set()
    src_full = _file_el("src", args.video, args.video.name,
                        max(round(vdur * seq_fps), 1), seq_fps, w, h, defined)

    # V1 video + A1/A2 audio: kept ranges back-to-back on the cut timeline
    v_items, a1_items, a2_items = [], [], []
    tl = 0.0
    for i, (s, e) in enumerate(ranges):
        in_f = round(s * seq_fps); out_f = round(e * seq_fps)
        dur = out_f - in_f
        tl_start = round(tl * seq_fps); tl_end = tl_start + dur
        fel = src_full if i == 0 else f'<file id="src"/>'
        v, a1, a2 = _av_clip(i, "src", f"Cut {i+1}", seq_fps, tl_start, tl_end, in_f, out_f, fel)
        v_items.append(v); a1_items.append(a1); a2_items.append(a2)
        tl += (e - s)
    cut_frames = round(tl * seq_fps)

    # V2..: overlays at CUT-RELATIVE atSeconds
    ov_tracks_xml = ""
    n_ov = 0
    if args.overlays:
        man = json.loads(args.overlays.read_text(encoding="utf-8"))
        clips = []
        for ent in man["entries"]:
            f = (ent.get("files") or {}).get(args.format)
            if not f:
                continue
            at = float(ent["atSeconds"]); hold = float(ent["hold"])
            clips.append({"id": ent["id"], "path": Path(f), "hold": hold,
                          "start": round(at * seq_fps), "end": round((at + hold) * seq_fps)})
        n_ov = len(clips)
        for tr in _pack_tracks(clips):
            items = []
            for c in tr:
                cf = round(c["hold"] * args.clip_fps)
                fel = _file_el(c["id"], c["path"], c["path"].name, cf, args.clip_fps, w, h, defined)
                items.append(_clipitem(c["id"], c["id"], fel, args.clip_fps, c["start"], c["end"], 0, cf))
            ov_tracks_xml += "<track>" + "".join(items) + "</track>"

    video_xml = (f"<track>{''.join(v_items)}</track>" + ov_tracks_xml)
    audio_xml = (f"<track>{''.join(a1_items)}</track><track>{''.join(a2_items)}</track>")

    seq = (
        f'<sequence id="seq"><name>{escape(args.video.stem)} — Vorschnitt</name>'
        f'<duration>{cut_frames}</duration>'
        f'<rate><timebase>{seq_fps}</timebase><ntsc>FALSE</ntsc></rate>'
        '<media>'
        f'<video><format><samplecharacteristics><width>{w}</width><height>{h}</height>'
        f'<rate><timebase>{seq_fps}</timebase><ntsc>FALSE</ntsc></rate>'
        f'</samplecharacteristics></format>{video_xml}</video>'
        f'<audio>{audio_xml}</audio>'
        '</media></sequence>')

    top = (f'<bin><name>{escape(args.video.stem)} — Vorschnitt + Animationen</name>'
           f'<children>{seq}</children></bin>')
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">\n'
           + top + '\n</xmeml>\n')

    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / "vorschnitt.fcp7.xml"
    out.write_text(xml, encoding="utf-8")
    kept = sum(e - s for s, e in ranges)
    print(f"Cut-XML: {len(ranges)} Schnitte ({kept:.0f}s von {vdur:.0f}s) + {n_ov} Animationen "
          f"({w}x{h}@{seq_fps}fps) → {out}", file=sys.stderr)
    print(str(out))


if __name__ == "__main__":
    main()
