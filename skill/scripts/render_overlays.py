#!/usr/bin/env python3
"""render_overlays.py — Stage 4: render one transparent overlay per plan entry.

For each approved animation × requested format, render a ProRes 4444 .mov with a
real alpha channel (or a PNG sequence with --png). No source video is needed —
the overlay is transparent and composites over V1 in Premiere.

    python3 render_overlays.py <animation-plan.json> --remotion <remotion_dir> \
        --formats 16x9,9x16 --out <out_dir> [--fps 30] [--png]

Writes <out_dir>/<format>/<id>.mov and <out_dir>/overlays-manifest.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from common import FORMATS, validate_plan, load_plan, seconds_to_tc, find_anchor_seconds  # noqa: F401


def load_brand(remotion: Path, name: str) -> dict:
    """Load a named brand preset from <remotion>/brands/<name>.json."""
    brands_dir = remotion / "brands"
    path = brands_dir / f"{name}.json"
    if not path.exists():
        available = sorted(p.stem for p in brands_dir.glob("*.json")) if brands_dir.exists() else []
        sys.exit(f"ERROR: brand {name!r} not found. Available: {available or '(none)'}\n"
                 f"Add one as {brands_dir}/{name}.json (see brands/default.json).")
    brand = json.loads(path.read_text(encoding="utf-8"))
    for key in ("name", "font", "colors"):
        if key not in brand:
            sys.exit(f"ERROR: brand {name!r} is missing '{key}'.")
    for ck in ("primary", "primaryDark", "accent", "muted", "white"):
        if ck not in brand["colors"]:
            sys.exit(f"ERROR: brand {name!r} colors missing '{ck}'.")
    return brand


def _props_hash(props: dict) -> str:
    """Stable hash of everything that affects a clip's pixels (type, content,
    steps, surface, brand, size, fps). Lets the renderer detect a swapped text
    or animation and re-render ONLY that clip. atSeconds is intentionally NOT
    included — moving an element is re-placement (resync), not a re-render."""
    h = {k: props[k] for k in props if k != "atSeconds"}
    return hashlib.sha256(json.dumps(h, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _summary(entry: dict) -> str:
    c = entry.get("content", {})
    if entry["type"] == "stat":
        return " ".join(x for x in [c.get("value", ""), c.get("label", "")] if x).strip()
    if entry["type"] == "enumeration":
        return " · ".join(it if isinstance(it, str) else it.get("text", "")
                          for it in c.get("items", []))
    if entry["type"] == "comparecards":
        def _side(p):
            its = (p or {}).get("items", [])
            return ", ".join(it if isinstance(it, str) else it.get("text", "") for it in its)
        return f"{(c.get('left') or {}).get('label','')} vs {(c.get('right') or {}).get('label','')}"
    return c.get("text", "")


def render_one(remotion: Path, props: dict, out_path: Path, *, png: bool,
               browser_executable: str | None = None) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(props, tf, ensure_ascii=False)
        props_file = tf.name

    cmd = ["npx", "remotion", "render", "src/Root.tsx", "Overlay", str(out_path),
           f"--props={props_file}", "--bundle-cache=false", "--timeout=120000"]
    if browser_executable:
        # Reuse an existing Chrome/headless-shell instead of Remotion's download
        # (helpful on machines that can't reach storage.googleapis.com).
        cmd.append(f"--browser-executable={browser_executable}")
    if png:
        cmd += ["--sequence", "--image-format", "png"]
    else:
        # ProRes 4444 with alpha: Remotion requires the PNG image format for the
        # frame buffer so the alpha channel survives into the video.
        cmd += ["--codec", "prores", "--prores-profile", "4444",
                "--pixel-format", "yuva444p10le", "--image-format", "png"]

    print(f"  render → {out_path.name}", file=sys.stderr)
    res = subprocess.run(cmd, cwd=remotion)
    if res.returncode != 0:
        sys.exit(f"ERROR: remotion render failed for {out_path} (exit {res.returncode})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 4: render transparent overlays")
    ap.add_argument("plan", type=Path, help="approved animation-plan.json")
    ap.add_argument("--remotion", type=Path, required=True, help="Remotion project dir")
    ap.add_argument("--out", type=Path, required=True, help="output dir for overlays")
    ap.add_argument("--formats", default="16x9,9x16", help="comma list of formats (default both)")
    ap.add_argument("--fps", type=int, default=30, help="composition/render fps (default 30)")
    ap.add_argument("--tc-fps", type=float, default=None,
                    help="fps for the timecode in the FILENAME = your Premiere sequence fps (e.g. 50). Default = --fps")
    ap.add_argument("--brand", default="default",
                    help="brand preset name in <remotion>/brands/ (default 'default'; add your own)")
    ap.add_argument("--png", action="store_true", help="render PNG sequence instead of ProRes .mov")
    ap.add_argument("--browser-executable", default=None,
                    help="path to an existing Chrome/headless-shell (skip Remotion's download)")
    ap.add_argument("--skip-existing", action="store_true",
                    help="skip entries whose output exists AND content is unchanged (resumable + auto-swap)")
    ap.add_argument("--force", action="store_true", help="re-render everything, ignore existing/hashes")
    ap.add_argument("--only", default=None, help="comma-separated entry ids to (re-)render, others skipped")
    ap.add_argument("--prune", action="store_true",
                    help="delete rendered clips whose id is no longer in the plan (cleanup after removals)")
    ap.add_argument("--uhd", action="store_true",
                    help="render at 4K (16x9→3840x2160, 9x16→2160x3840); components scale by width")
    ap.add_argument("--no-validate", action="store_true",
                    help="skip plan validation (e.g. word-synced reveals whose beats are >2s apart by design)")
    args = ap.parse_args()

    plan = load_plan(args.plan)
    errs = [] if args.no_validate else validate_plan(plan)
    if errs:
        print("ERROR: plan is invalid — fix before rendering:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    for f in formats:
        if f not in FORMATS:
            sys.exit(f"ERROR: unknown format {f!r}; choose from {list(FORMATS)}")

    brand = load_brand(args.remotion, args.brand)
    print(f"brand: {brand['name']} (font {brand['font']})", file=sys.stderr)

    # Content-hash sidecar → re-render only entries whose pixels changed (auto-swap).
    hashes_path = args.out / ".render-hashes.json"
    hashes = json.loads(hashes_path.read_text()) if hashes_path.exists() else {}
    only_ids = {x.strip() for x in args.only.split(",")} if args.only else None
    n_rendered = n_skipped = 0

    manifest_entries = []
    for entry in plan["animations"]:
        files: dict[str, str] = {}
        for fmt in formats:
            w, h = FORMATS[fmt]
            if args.uhd:
                w, h = (3840, 2160) if fmt == "16x9" else (2160, 3840)
            props = {
                "type": entry["type"],
                "format": fmt,
                "fps": args.fps,
                "width": w,
                "height": h,
                "hold": float(entry["hold"]),
                "content": entry.get("content", {}),
                "steps": entry.get("steps", []),
                "surface": entry.get("surface", "solid"),
                "brand": brand,
                # face-aware zone (face_zones.py). In props → auto-part of the
                # content hash (which hashes everything but atSeconds) so a changed
                # zone re-renders exactly this one clip via --skip-existing.
                "placement": entry.get("placement"),
            }
            ext = "" if args.png else ".mov"
            # Timecode in the filename = position in the Premiere sequence (its fps),
            # NOT the render fps. Kept permanently correct: a skipped clip whose name
            # no longer matches its timecode is renamed.
            tc_fps = args.tc_fps if args.tc_fps else args.fps
            tc = seconds_to_tc(float(entry["atSeconds"]), tc_fps).replace(":", "-")
            out_path = args.out / fmt / f"{entry['id']}__{tc}{ext}"
            key = f"{entry['id']}__{fmt}"
            h_now = _props_hash(props)
            existing = list((args.out / fmt).glob(f"{entry['id']}__*{ext}"))
            limited_out = only_ids is not None and entry["id"] not in only_ids
            # Existing file with no recorded hash → adopt it as baseline (first run
            # after this feature). With a recorded hash → unchanged only if it matches.
            unchanged = bool(existing) and (key not in hashes or hashes[key] == h_now)
            if not args.force and (limited_out or (args.skip_existing and unchanged)):
                if existing:
                    cur = existing[0]
                    if cur.name != out_path.name:  # timecode drifted → rename to correct TC
                        cur.rename(out_path)
                        print(f"  renamed → {out_path.name}", file=sys.stderr)
                        cur = out_path
                    files[fmt] = str(cur.resolve())
                    hashes[key] = h_now  # record/refresh baseline
                n_skipped += 1
                continue
            # changed / new / forced → drop any stale clip(s) for this id, re-render
            for old in existing:
                if old != out_path:
                    old.unlink()
            render_one(args.remotion, props, out_path, png=args.png,
                       browser_executable=args.browser_executable)
            files[fmt] = str(out_path.resolve())
            hashes[key] = h_now
            n_rendered += 1
        manifest_entries.append({
            "id": entry["id"],
            "type": entry["type"],
            "atSeconds": entry["atSeconds"],
            "hold": entry["hold"],
            "anchorPhrase": entry.get("anchorPhrase", ""),
            "summary": _summary(entry),
            "files": files,
        })

    if args.prune:
        plan_ids = {e["id"] for e in plan["animations"]}
        pruned = 0
        for fmt in formats:
            for mov in (args.out / fmt).glob("*.mov"):
                if mov.stem.split("__")[0] not in plan_ids:
                    mov.unlink()
                    hashes.pop(f"{mov.stem.split('__')[0]}__{fmt}", None)
                    pruned += 1
        if pruned:
            print(f"pruned {pruned} orphan clip(s) no longer in the plan", file=sys.stderr)

    hashes_path.write_text(json.dumps(hashes, ensure_ascii=False, indent=1), encoding="utf-8")
    manifest = {"fps": args.fps, "formats": formats, "png": args.png,
                "brand": brand["name"], "entries": manifest_entries}
    man_path = args.out / "overlays-manifest.json"
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"rendered {n_rendered}, skipped {n_skipped} (unchanged) — "
          f"{len(manifest_entries)} entries × {len(formats)} format(s) → {args.out}",
          file=sys.stderr)
    print(str(man_path))


if __name__ == "__main__":
    main()
