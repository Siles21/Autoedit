#!/usr/bin/env python3
"""integrate.py — Stage 5 fallback deliverables + adb-mcp availability probe.

The LIVE path (placing overlays into the open Premiere project) is done by Claude
via the adb-mcp MCP tools — MCP is not reachable from a plain subprocess. This
script handles:

  --probe-only   tell whether the adb-mcp proxy (port 3030) is reachable, so
                 Claude knows which path to take.

  default        generate the fallback bundle for manual import:
                   - placement.md / placement.csv  (frame-accurate HH:MM:SS:FF)
                   - overlays.fcpxml               (source on spine + overlays on
                                                    connected lanes, ready to use)

    python3 integrate.py --probe-only
    python3 integrate.py <animation-plan.json> --video <final_video> \
        --overlays <overlays-manifest.json> --out <out_dir> [--format auto]
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from common import (
    FORMATS, TICKS_PER_SECOND, rational, seconds_to_tc, seconds_to_ticks,
    validate_plan, load_plan,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _probe_3030(host: str = "127.0.0.1", port: int = 3030, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _probe_video(video: Path):
    """Bundled ffprobe wrapper for fps/size/duration."""
    from _whisper import probe  # noqa: E402
    return probe(video)


def _pick_format(width: int, height: int, requested: str) -> str:
    if requested != "auto":
        return requested
    return "16x9" if width >= height else "9x16"


def _summary(entry: dict) -> str:
    return entry.get("summary", "")


def write_placement(plan: dict, manifest: dict, fmt: str, fps: float, out_dir: Path) -> None:
    rows = []
    by_id = {e["id"]: e for e in manifest["entries"]}
    for a in plan["animations"]:
        m = by_id.get(a["id"], {})
        f = (m.get("files") or {}).get(fmt, "")
        rows.append({
            "id": a["id"],
            "tc": seconds_to_tc(a["atSeconds"], fps),
            "atSeconds": a["atSeconds"],
            "ticks": seconds_to_ticks(a["atSeconds"]),
            "type": a["type"],
            "hold": a["hold"],
            "summary": _summary(m) or a.get("anchorPhrase", ""),
            "file": f,
        })

    md = ["# Overlay-Platzierung", "",
          f"Format: **{fmt}**  ·  fps: **{fps:.3f}**  ·  Spur-Empfehlung: **V2** (über dem Schnitt)",
          "",
          "Ziehe jede `.mov` an den genannten Timecode auf eine Grafik-Spur. Timecode ist HH:MM:SS:FF (non-drop).",
          "",
          "| # | Timecode | Sek | Dauer | Typ | Inhalt | Datei |",
          "|---|----------|-----|-------|-----|--------|-------|"]
    for r in rows:
        md.append(
            f"| {r['id']} | `{r['tc']}` | {r['atSeconds']:.2f} | {r['hold']}s | "
            f"{r['type']} | {r['summary']} | `{Path(r['file']).name if r['file'] else '—'}` |"
        )
    (out_dir / "placement.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    csv = ["id,timecode,atSeconds,ticks,type,hold,summary,file"]
    for r in rows:
        s = r["summary"].replace('"', "'")
        csv.append(f'{r["id"]},{r["tc"]},{r["atSeconds"]},{r["ticks"]},{r["type"]},'
                   f'{r["hold"]},"{s}",{r["file"]}')
    (out_dir / "placement.csv").write_text("\n".join(csv) + "\n", encoding="utf-8")


def write_fcpxml(plan: dict, manifest: dict, video: Path, meta, fmt: str, out_dir: Path) -> None:
    """Source video on the spine + overlays as connected clips (lane=1)."""
    fps_num, fps_den = meta.fps_num, meta.fps_den
    frame_dur = f"{fps_den}/{fps_num}s"
    by_id = {e["id"]: e for e in manifest["entries"]}

    assets = [
        f'    <asset id="rVid" name="{escape(video.name)}" src="file://{escape(str(video.resolve()))}" '
        f'hasVideo="1" hasAudio="1" duration="{rational(meta.duration, fps_num, fps_den)}" format="r1"/>'
    ]
    connected = []
    for i, a in enumerate(plan["animations"], start=1):
        m = by_id.get(a["id"], {})
        f = (m.get("files") or {}).get(fmt)
        if not f:
            continue
        aid = f"ov{i}"
        dur = rational(float(a["hold"]), fps_num, fps_den)
        assets.append(
            f'    <asset id="{aid}" name="{escape(a["id"])}" src="file://{escape(str(Path(f).resolve()))}" '
            f'hasVideo="1" hasAudio="0" duration="{dur}" format="r1"/>'
        )
        connected.append(
            f'        <asset-clip ref="{aid}" lane="1" '
            f'offset="{rational(float(a["atSeconds"]), fps_num, fps_den)}" '
            f'name="{escape(a["id"])}" start="0s" duration="{dur}" tcFormat="NDF"/>'
        )

    vid_dur = rational(meta.duration, fps_num, fps_den)
    assets_xml = "\n".join(assets)
    connected_xml = "\n".join(connected)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.10">
  <resources>
    <format id="r1" name="FFVideoFormat" frameDuration="{frame_dur}" width="{meta.width}" height="{meta.height}"/>
{assets_xml}
  </resources>
  <library>
    <event name="sub-animations">
      <project name="{escape(video.stem)} + overlays">
        <sequence format="r1" duration="{vid_dur}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">
          <spine>
            <asset-clip ref="rVid" offset="0s" name="{escape(video.name)}" start="0s" duration="{vid_dur}" format="r1" tcFormat="NDF">
{connected_xml}
            </asset-clip>
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
"""
    (out_dir / "overlays.fcpxml").write_text(xml, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 5: probe adb-mcp / build fallback bundle")
    ap.add_argument("plan", nargs="?", type=Path, help="approved animation-plan.json")
    ap.add_argument("--video", type=Path, help="final video (the cut Premiere edited)")
    ap.add_argument("--overlays", type=Path, help="overlays-manifest.json from render_overlays.py")
    ap.add_argument("--out", type=Path, help="output dir for the fallback bundle")
    ap.add_argument("--format", default="auto", help="16x9 | 9x16 | auto (match source)")
    ap.add_argument("--probe-only", action="store_true", help="only report adb-mcp availability")
    args = ap.parse_args()

    live = _probe_3030()
    if args.probe_only:
        print(json.dumps({"adb_mcp_live": live, "port": 3030}))
        print(("adb-mcp proxy reachable on :3030 — LIVE placement possible."
               if live else
               "adb-mcp proxy NOT reachable — use the fallback bundle."), file=sys.stderr)
        return

    if not (args.plan and args.video and args.overlays and args.out):
        ap.error("plan, --video, --overlays and --out are required (or use --probe-only)")

    plan = load_plan(args.plan)
    errs = validate_plan(plan)
    if errs:
        sys.exit("ERROR: plan invalid: " + "; ".join(errs))
    manifest = json.loads(args.overlays.read_text(encoding="utf-8"))
    if not args.video.exists():
        sys.exit(f"ERROR: video not found: {args.video}")

    meta = _probe_video(args.video)
    fmt = _pick_format(meta.width, meta.height, args.format)
    if fmt not in FORMATS:
        sys.exit(f"ERROR: unknown format {fmt!r}")
    if fmt not in manifest.get("formats", []):
        sys.exit(f"ERROR: format {fmt!r} was not rendered (manifest has {manifest.get('formats')}).")

    args.out.mkdir(parents=True, exist_ok=True)
    write_placement(plan, manifest, fmt, meta.fps, args.out)
    # FCPXML disabled — Premiere kann die Datei nicht öffnen (Simon 2026-06-15).
    # Nie wieder generieren; Deliverable = .mov-Clips + placement.md (manuell ziehen)
    # oder Live-Platzierung via adb-mcp.

    print(f"adb-mcp live: {live}", file=sys.stderr)
    print(f"wrote fallback bundle ({fmt}) → {args.out}/placement.md, placement.csv",
          file=sys.stderr)
    if live:
        print("NOTE: proxy is up — Claude can also place overlays live via adb-mcp "
              "(insertion_time_ticks = atSeconds * %d)." % TICKS_PER_SECOND, file=sys.stderr)


if __name__ == "__main__":
    main()
