#!/usr/bin/env python3
"""qc_visual.py — QC-3 visual reviewer (deterministic) for an animation plan.

Catches the "looks bad / bug" cases that cause revisions, WITHOUT eyeballing
every clip:
  - COLLISIONS: two animations overlapping in TIME and in SCREEN POSITION
    (e.g. a keyword-pop and a lower-third both bottom-left at the same moment).
  - LONG-TEXT: display strings likely too long for their slot.
  - DENSITY: more than N overlays visible at once.

Position boxes per type are approximate screen rectangles (fractions 0..1)
matching the Remotion components. Time window = [atSeconds, atSeconds+hold].

    qc_visual.py <animation-plan.json> [--format 16x9] [--max-onscreen 3]
    qc_visual.py --selftest
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import load_plan, seconds_to_tc

# Approx screen rectangle (x1,y1,x2,y2 in 0..1) per type, per format. Derived
# from the component anchors in remotion/src/*.tsx.
_BOXES = {
    "16x9": {
        "lowerthird":  (0.06, 0.78, 0.52, 0.96),  # bottom-left band
        "stat":        (0.34, 0.78, 0.66, 0.98),  # bottom-center card
        "kpibig":      (0.18, 0.28, 0.82, 0.72),  # center hero
        "reveal":      (0.08, 0.36, 0.92, 0.64),  # center wide
        "comparebars": (0.28, 0.30, 0.72, 0.70),  # center panel
        "chart":       (0.30, 0.30, 0.70, 0.70),
        "sequence":    (0.08, 0.20, 0.62, 0.72),  # top-left tall
        "enumeration": (0.09, 0.30, 0.56, 0.72),  # left-center
    },
    "9x16": {
        "lowerthird":  (0.06, 0.78, 0.80, 0.92),
        "stat":        (0.10, 0.20, 0.90, 0.40),
        "kpibig":      (0.05, 0.30, 0.95, 0.70),
        "reveal":      (0.08, 0.36, 0.92, 0.64),
        "comparebars": (0.05, 0.26, 0.95, 0.66),
        "chart":       (0.05, 0.24, 0.95, 0.70),
        "sequence":    (0.07, 0.24, 0.93, 0.78),
        "enumeration": (0.08, 0.28, 0.92, 0.72),
    },
}


def _box(t: str, fmt: str):
    return _BOXES.get(fmt, _BOXES["16x9"]).get(t)


def _overlap_area(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy


def _summary(e: dict) -> str:
    c = e.get("content", {})
    return (c.get("value") or c.get("text") or c.get("label")
            or c.get("kicker") or (c.get("items", [None]) or [None])[0] or e["type"])


def review(plan: dict, fmt: str = "16x9", max_onscreen: int = 3,
           area_thresh: float = 0.02):
    """Return (collisions, long_texts, dense_moments)."""
    ents = sorted(plan.get("animations", []), key=lambda e: float(e["atSeconds"]))
    spans = []
    for e in ents:
        at = float(e["atSeconds"]); end = at + float(e["hold"])
        spans.append((e, at, end, _box(e["type"], fmt)))

    collisions = []
    for i in range(len(spans)):
        ei, ai, bi, boxi = spans[i]
        if boxi is None:
            continue
        for j in range(i + 1, len(spans)):
            ej, aj, bj, boxj = spans[j]
            if aj >= bi:  # sorted: no later start overlaps this end → stop
                break
            if boxj is None:
                continue
            t_ov = min(bi, bj) - max(ai, aj)
            area = _overlap_area(boxi, boxj)
            if t_ov > 0.15 and area > area_thresh:
                collisions.append({
                    "a": ei["id"], "b": ej["id"], "at": round(max(ai, aj), 2),
                    "t_overlap": round(t_ov, 2), "area": round(area, 3),
                    "atype": ei["type"], "btype": ej["type"]})

    long_texts = []
    for e in ents:
        c = e.get("content", {})
        for fld in ("text", "value", "label", "kicker", "sublabel"):
            s = c.get(fld)
            if isinstance(s, str) and len(s) > 64:
                long_texts.append({"id": e["id"], "field": fld, "len": len(s)})
        for it in c.get("items", []):
            if isinstance(it, str) and len(it) > 46:
                long_texts.append({"id": e["id"], "field": "item", "len": len(it), "text": it})
        for st in e.get("steps", []):
            for fld in ("text", "value", "sublabel"):
                s = st.get(fld)
                if isinstance(s, str) and len(s) > 46:
                    long_texts.append({"id": e["id"], "field": f"step.{fld}", "len": len(s)})

    # density: max simultaneous overlays
    events = []
    for e, at, end, _ in spans:
        events.append((at, 1)); events.append((end, -1))
    events.sort()
    cur = peak = 0
    for _, d in events:
        cur += d
        peak = max(peak, cur)
    dense = peak > max_onscreen
    return collisions, long_texts, {"peak_onscreen": peak, "over": dense, "limit": max_onscreen}


def _selftest() -> None:
    # two bottom-left items overlapping in time → collision
    plan = {"animations": [
        {"id": "lt1", "type": "lowerthird", "atSeconds": 10.0, "hold": 4.0, "content": {"text": "A"}},
        {"id": "pop1", "type": "lowerthird", "atSeconds": 12.0, "hold": 2.5, "content": {"text": "B"}},
        {"id": "kc", "type": "kpibig", "atSeconds": 12.0, "hold": 3.0, "content": {"value": "5 %"}},
        {"id": "far", "type": "lowerthird", "atSeconds": 60.0, "hold": 3.0, "content": {"text": "C"}},
    ]}
    col, lng, dens = review(plan, "16x9")
    ids = {tuple(sorted((c["a"], c["b"]))) for c in col}
    assert ("lt1", "pop1") in ids, col           # same bottom-left zone, time overlap
    assert ("kc", "lt1") not in ids and ("kc", "pop1") not in ids, col  # center vs BL: no collision
    assert ("far",) not in [tuple([c["a"]]) for c in col]
    # long text
    plan2 = {"animations": [{"id": "x", "type": "reveal", "atSeconds": 1, "hold": 3,
             "content": {"text": "x" * 80}}]}
    _, lng2, _ = review(plan2)
    assert lng2 and lng2[0]["id"] == "x"
    print("qc_visual selftest OK")


def main() -> None:
    ap = argparse.ArgumentParser(description="QC-3 deterministic visual reviewer")
    ap.add_argument("plan", nargs="?", type=Path)
    ap.add_argument("--format", default="16x9")
    ap.add_argument("--max-onscreen", type=int, default=3)
    ap.add_argument("--fps", type=float, default=50.0)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
        return
    if not args.plan:
        ap.error("plan required (or --selftest)")
    plan = load_plan(args.plan)
    by = {e["id"]: e for e in plan["animations"]}
    col, lng, dens = review(plan, args.format, args.max_onscreen)
    print(f"QC-3 visual review ({args.format}): {len(plan['animations'])} animations", file=sys.stderr)
    print(f"  COLLISIONS (time+position overlap): {len(col)}", file=sys.stderr)
    for c in col:
        print(f"    {seconds_to_tc(c['at'], args.fps)}  {c['a']}({c['atype']}) ✕ {c['b']}({c['btype']})"
              f"  {c['t_overlap']}s, area {c['area']}  | {_summary(by[c['a']])[:24]} / {_summary(by[c['b']])[:24]}",
              file=sys.stderr)
    print(f"  LONG TEXTS (maybe overflow): {len(lng)}", file=sys.stderr)
    for l in lng[:20]:
        print(f"    {l['id']}.{l['field']} len={l['len']}", file=sys.stderr)
    print(f"  PEAK simultaneous on-screen: {dens['peak_onscreen']} (limit {dens['limit']})"
          f"{'  ⚠ over' if dens['over'] else ''}", file=sys.stderr)
    sys.exit(1 if (col or dens["over"]) else 0)


if __name__ == "__main__":
    main()
