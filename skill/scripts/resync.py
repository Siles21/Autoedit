#!/usr/bin/env python3
"""resync.py — re-anchor an animation plan to a CHANGED cut.

Every animation is anchored to its spoken `anchorPhrase`. When the edit shifts
the timeline (segments added/removed), this recomputes each `atSeconds` from the
NEW transcript, renames the rendered overlays to their new timecode, rebuilds the
overlays manifest and reports anchors that no longer exist (text was cut) — never
silently mis-placing anything. The graphics are NOT re-rendered.

    # 1) get new words from the re-exported/edited sequence:
    #    premiere_transcript.py new.json --out new.words.json   (or align_words.py)
    # 2) re-sync:
    resync.py <plan.json> --words <new.words.json> \
        [--overlays <overlays_dir>] [--fps 30] [--out <plan.resynced.json>]

Then re-place: live via adb-mcp (clear the SUB track, re-add at the new ticks —
see SKILL.md) or re-run integrate.py for a fresh FCPXML/placement bundle.

    resync.py --selftest
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from common import find_anchor_seconds, seconds_to_tc, validate_plan, load_plan


def reanchor(plan: dict, words: list[dict]) -> tuple[dict, list[dict]]:
    """Pure: recompute atSeconds per anchorPhrase against `words`.

    Returns (new_plan, report). Report rows: {id, old, new, delta, status} where
    status is moved | same | lost (anchor gone) | no-anchor (entry had none).
    The new_plan is a deep-ish copy with updated atSeconds for resolved anchors;
    lost/no-anchor entries keep their old atSeconds and are flagged.
    """
    new_plan = json.loads(json.dumps(plan))  # cheap deep copy
    report: list[dict] = []
    for e in new_plan.get("animations", []):
        old = float(e.get("atSeconds", 0.0))
        anchor = (e.get("anchorPhrase") or "").strip()
        if not anchor:
            report.append({"id": e.get("id"), "old": old, "new": old, "delta": 0.0,
                           "status": "no-anchor"})
            continue
        found = find_anchor_seconds(anchor, words)
        if found is None:
            report.append({"id": e.get("id"), "old": old, "new": old, "delta": 0.0,
                           "status": "lost"})
            continue
        # Re-apply the stored cue↔anchor offset (0 if none) for exact relative timing.
        new = round(float(found) + float(e.get("anchorOffset", 0.0)), 2)
        e["atSeconds"] = new
        report.append({"id": e.get("id"), "old": old, "new": new,
                       "delta": round(new - old, 2),
                       "status": "same" if abs(new - old) < 0.05 else "moved"})
    return new_plan, report


def infer_block_shift(plan: dict, report: list[dict], tol: float = 1.5) -> float | None:
    """When the matched anchors all moved by ~the same amount (a contiguous block
    shifted uniformly), recover the LOST / no-anchor entries by applying that
    shift. Returns the applied median shift, or None if the matched deltas are
    too inconsistent to trust (then nothing is inferred)."""
    deltas = [r["delta"] for r in report if r["status"] == "moved"]
    if len(deltas) < 2 or (max(deltas) - min(deltas)) > tol:
        return None
    shift = round(statistics.median(deltas), 2)
    by_id = {e["id"]: e for e in plan.get("animations", [])}
    for r in report:
        if r["status"] in ("lost", "no-anchor"):
            e = by_id.get(r["id"])
            if e is None:
                continue
            e["atSeconds"] = round(r["old"] + shift, 2)
            r["new"] = e["atSeconds"]
            r["delta"] = shift
            r["status"] = "inferred"
    return shift


def _rename_overlays(plan: dict, overlays_dir: Path, fps: float) -> list[str]:
    """Rename rendered <id>__*.mov to the new timecode; rebuild manifest. Returns
    log lines. Files are matched by id glob, so the stale TC in the name is fine."""
    log: list[str] = []
    by_id = {e["id"]: e for e in plan.get("animations", [])}
    fmt_dirs = [d for d in overlays_dir.iterdir() if d.is_dir() and d.name in ("16x9", "9x16")]
    manifest_entries: list[dict] = []
    for e in plan.get("animations", []):
        files: dict[str, str] = {}
        new_tc = seconds_to_tc(float(e["atSeconds"]), fps).replace(":", "-")
        for fd in fmt_dirs:
            matches = sorted(fd.glob(f"{e['id']}__*.mov"))
            if not matches:
                continue
            src = matches[0]
            dst = fd / f"{e['id']}__{new_tc}.mov"
            if src != dst:
                src.rename(dst)
                log.append(f"  {src.name} → {dst.name}")
            files[fd.name] = str(dst.resolve())
        if files:
            manifest_entries.append({
                "id": e["id"], "type": e["type"], "atSeconds": e["atSeconds"],
                "hold": e["hold"], "anchorPhrase": e.get("anchorPhrase", ""),
                "summary": _summary(e), "files": files,
            })
    if manifest_entries:
        fmts = sorted({fd.name for fd in fmt_dirs})
        (overlays_dir / "overlays-manifest.json").write_text(
            json.dumps({"fps": fps, "formats": fmts, "png": False,
                        "entries": manifest_entries}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        log.append(f"  rebuilt overlays-manifest.json ({len(manifest_entries)} entries)")
    return log


def _summary(e: dict) -> str:
    c = e.get("content", {})
    t = e["type"]
    if t in ("stat", "kpibig"):
        return " · ".join(x for x in [c.get("value", ""), c.get("label", "") or c.get("kicker", "")] if x)
    if t == "enumeration":
        return " · ".join(c.get("items", []))
    if t == "sequence":
        return " · ".join(s.get("text") or s.get("value", "") for s in e.get("steps", []))
    if t == "comparebars":
        return f"{(c.get('before') or {}).get('value','')} vs {(c.get('after') or {}).get('value','')}"
    if t == "chart":
        return " · ".join(p.get("value", "") for p in c.get("series", []))
    return c.get("text", "") or c.get("kicker", "")


def _print_report(report: list[dict], fps: float) -> None:
    n = lambda st: len([r for r in report if r["status"] == st])
    print(f"re-sync: {len(report)} entries — {n('moved')} moved, {n('same')} unchanged, "
          f"{n('inferred')} inferred, {n('lost')} LOST, {n('no-anchor')} without anchor",
          file=sys.stderr)
    for r in report:
        if r["status"] in ("moved", "inferred", "lost", "no-anchor"):
            tc = seconds_to_tc(r["new"], fps)
            tag = {"moved": f"{r['delta']:+.2f}s → {tc}",
                   "inferred": f"{r['delta']:+.2f}s → {tc}  (aus Block-Versatz abgeleitet)",
                   "lost": "ANCHOR LOST — kept old, fix manually",
                   "no-anchor": "no anchorPhrase — not re-syncable"}[r["status"]]
            print(f"  [{r['status']:9}] {r['id']:16} {tag}", file=sys.stderr)


def _selftest() -> None:
    plan = {"animations": [
        {"id": "a", "type": "stat", "anchorPhrase": "vier komma zwei prozent",
         "atSeconds": 1.4, "hold": 2.8, "content": {"value": "4,2 %"}},
        {"id": "d", "type": "lowerthird", "anchorPhrase": "heute schon",
         "atSeconds": 1.0, "hold": 3.0, "content": {"text": "Z"}},
        {"id": "b", "type": "lowerthird", "anchorPhrase": "gibt es nicht mehr",
         "atSeconds": 5.0, "hold": 3.0, "content": {"text": "X"}},
        {"id": "c", "type": "reveal", "atSeconds": 9.0, "hold": 3.0, "content": {"text": "Y"}},
    ]}
    # new words: "heute schon" + "vier komma zwei prozent" both occur +5s later;
    # "gibt es nicht mehr" was cut.
    words = [
        {"text": "heute", "start": 6.0, "end": 6.3},
        {"text": "schon", "start": 6.3, "end": 6.5},
        {"text": "vier", "start": 6.4, "end": 6.6},
        {"text": "Komma", "start": 6.6, "end": 6.8},
        {"text": "zwei", "start": 6.8, "end": 7.0},
        {"text": "Prozent", "start": 7.0, "end": 7.4},
    ]
    new_plan, report = reanchor(plan, words)
    by = {r["id"]: r for r in report}
    assert by["a"]["status"] == "moved" and abs(by["a"]["new"] - 6.4) < 0.001, by["a"]
    assert by["d"]["status"] == "moved" and abs(by["d"]["new"] - 6.0) < 0.001, by["d"]
    assert by["b"]["status"] == "lost"
    assert by["c"]["status"] == "no-anchor"

    # block-shift inference: a + d both moved +5s → infer b and c
    shift = infer_block_shift(new_plan, report)
    assert shift is not None and abs(shift - 5.0) < 0.001, shift
    by2 = {e["id"]: e for e in new_plan["animations"]}
    rep2 = {r["id"]: r for r in report}
    assert rep2["b"]["status"] == "inferred" and by2["b"]["atSeconds"] == 10.0, by2["b"]
    assert rep2["c"]["status"] == "inferred" and by2["c"]["atSeconds"] == 14.0, by2["c"]
    print("resync selftest OK")


def main() -> None:
    ap = argparse.ArgumentParser(description="Re-anchor a plan to a changed cut")
    ap.add_argument("plan", nargs="?", type=Path)
    ap.add_argument("--words", type=Path, help="new words.json (from premiere_transcript.py / align_words.py)")
    ap.add_argument("--overlays", type=Path, default=None, help="overlays dir to rename + rebuild manifest")
    ap.add_argument("--out", type=Path, default=None, help="output resynced plan (default <plan>.resynced.json)")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--infer-shift", action="store_true",
                    help="if matched anchors moved uniformly, apply that block-shift to LOST/no-anchor entries")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return
    if not args.plan or not args.words:
        ap.error("plan and --words are required (or --selftest)")

    plan = load_plan(args.plan)
    errs = validate_plan(plan)
    if errs:
        sys.exit("ERROR: plan invalid: " + "; ".join(errs))
    words = json.loads(args.words.read_text(encoding="utf-8")).get("words", [])
    if not words:
        sys.exit("ERROR: --words has no 'words'.")

    new_plan, report = reanchor(plan, words)
    if args.infer_shift:
        shift = infer_block_shift(new_plan, report)
        if shift is not None:
            print(f"block-shift inferred: {shift:+.2f}s applied to LOST/no-anchor entries",
                  file=sys.stderr)
        else:
            print("block-shift NOT applied (matched anchors too inconsistent)", file=sys.stderr)
    out = args.out or args.plan.with_suffix(".resynced.json")
    out.write_text(json.dumps(new_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_report(report, args.fps)

    if args.overlays:
        log = _rename_overlays(new_plan, args.overlays, args.fps)
        print("renamed overlays + manifest:", file=sys.stderr)
        for line in log:
            print(line, file=sys.stderr)

    print(f"\nresynced plan → {out}", file=sys.stderr)
    print("Next: re-place (live via adb-mcp clear+re-add SUB track, or rerun integrate.py).",
          file=sys.stderr)
    print(str(out))


if __name__ == "__main__":
    main()
