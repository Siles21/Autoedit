#!/usr/bin/env python3
"""qc.py — Stage 6: build a per-overlay QC checklist.

Emits one row per animation with the frame to inspect (atSeconds + hold/2) and
the expected content, so the placement can be verified visually.

LIVE path: Claude exports each `check` timecode via adb-mcp
`get_sequence_frame_image(seconds)` and vision-checks the row.
FALLBACK path: Simon ticks the checklist by hand against the timeline.

    python3 qc.py <animation-plan.json> [--fps 30] [--out qc-checklist.md]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import seconds_to_tc, validate_plan, load_plan


def _expected(entry: dict) -> str:
    c = entry.get("content", {})
    if entry["type"] == "stat":
        return " · ".join(x for x in [c.get("value", ""), c.get("label", ""), c.get("sublabel", "")] if x)
    if entry["type"] == "enumeration":
        return " · ".join(c.get("items", []))
    return " · ".join(x for x in [c.get("teaser", ""), c.get("text", ""), c.get("sublabel", "")] if x)


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 6: QC checklist")
    ap.add_argument("plan", type=Path)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    plan = load_plan(args.plan)
    errs = validate_plan(plan)
    if errs:
        sys.exit("ERROR: plan invalid: " + "; ".join(errs))

    lines = ["# QC-Checkliste — Sub-Animationen", "",
             "Prüf-Timecode = Mitte des Overlays (`atSeconds + hold/2`). "
             "Live: `get_sequence_frame_image(sek)` exportieren und prüfen.", "",
             "| # | Typ | Prüf-TC | Sek | Erwarteter Inhalt | sichtbar | Wert korrekt | keine Kollision |",
             "|---|-----|---------|-----|-------------------|:--------:|:------------:|:---------------:|"]
    for a in plan["animations"]:
        check = a["atSeconds"] + a["hold"] / 2.0
        lines.append(
            f"| {a['id']} | {a['type']} | `{seconds_to_tc(check, args.fps)}` | {check:.2f} | "
            f"{_expected(a)} | ☐ | ☐ | ☐ |"
        )

    out = args.out or args.plan.with_name("qc-checklist.md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote QC checklist ({len(plan['animations'])} rows) → {out}", file=sys.stderr)
    print(str(out))


if __name__ == "__main__":
    main()
