#!/usr/bin/env python3
"""qc_transcript.py — QC-1 transcript-error gate.

Whisper garbles words (numbers, names, compounds). If a garble propagates into a
graphic — especially keyword-pops, which use the RAW transcript — you ship a
wrong/embarrassing on-screen claim. This scans words.json for suspicious tokens
and, when a plan is given, marks which suspicious tokens actually appear on
screen (= must-fix).

    qc_transcript.py <words.json> [--plan <animation-plan.json>] [--out report.md]
    qc_transcript.py --selftest
Exit code 1 if any suspicious token is USED in the plan (or, without a plan,
if any are found).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from common import plan_strings, norm_tokens
from qc_spell import token_flag

_STRIP = ".,!?;:\"'»«()—-…"


def suspicious_tokens(words: list[dict]) -> dict[str, dict]:
    """Map lowered-token -> {token, count, reason} for likely Whisper errors,
    using the shared token_flag heuristic (so QC-1 and QC-2 stay consistent)."""
    out: dict[str, dict] = {}
    for w in words:
        tok = (w.get("text") or "").strip(_STRIP)
        reason = token_flag(tok)
        if reason:
            rec = out.setdefault(tok.lower(), {"token": tok, "count": 0, "reason": reason})
            rec["count"] += 1
    return out


def used_in_plan(susp: dict[str, dict], plan: dict | None) -> set[str]:
    """Which suspicious tokens appear in any on-screen plan string."""
    if not plan:
        return set()
    shown = set()
    for _, _, text in plan_strings(plan):
        for t in norm_tokens(text):
            shown.add(t)
    return {k for k in susp if k in shown}


def _selftest() -> None:
    words = [{"text": "Rückhauswerte", "start": 1.0, "end": 1.3},
             {"text": "ProLiveGmbH", "start": 2.0, "end": 2.3},
             {"text": "Vermögensverwaltung", "start": 3.0, "end": 3.5},
             {"text": "Rendite", "start": 4.0, "end": 4.3}]
    s = suspicious_tokens(words)
    assert "rückhauswerte" in s and "prolivegmbh" in s, s
    assert "vermögensverwaltung" not in s and "rendite" not in s, s
    plan = {"animations": [{"id": "p", "type": "lowerthird", "atSeconds": 1, "hold": 3,
            "content": {"text": "Rückhauswerte"}}]}
    used = used_in_plan(s, plan)
    assert used == {"rückhauswerte"}, used
    print("qc_transcript selftest OK")


def main() -> None:
    ap = argparse.ArgumentParser(description="QC-1 transcript-error gate")
    ap.add_argument("words", nargs="?", type=Path)
    ap.add_argument("--plan", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
        return
    if not args.words:
        ap.error("words.json required (or --selftest)")
    import json
    words = json.loads(args.words.read_text(encoding="utf-8")).get("words", [])
    plan = json.loads(args.plan.read_text(encoding="utf-8")) if args.plan else None
    susp = suspicious_tokens(words)
    used = used_in_plan(susp, plan)

    lines = ["# QC-1 Transkript-Fehler-Report", "",
             f"{len(words)} Wörter · {len(susp)} verdächtige Tokens"
             + (f" · {len(used)} davon ON-SCREEN im Plan" if plan else ""), ""]
    if used:
        lines += ["## ⚠ MUST-FIX — verdächtig UND auf dem Bildschirm:", ""]
        for k in sorted(used):
            lines.append(f"- **{susp[k]['token']}** ({susp[k]['reason']}, {susp[k]['count']}×)")
        lines.append("")
    lines += ["## Weitere verdächtige Transkript-Tokens (nicht on-screen):", ""]
    for k in sorted(susp):
        if k not in used:
            lines.append(f"- {susp[k]['token']} ({susp[k]['reason']}, {susp[k]['count']}×)")
    out = args.out or args.words.with_suffix(".transcript-qc.md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"QC-1 transcript: {len(susp)} suspicious tokens"
          + (f", {len(used)} ON-SCREEN" if plan else "") + f" → {out}", file=sys.stderr)
    for k in sorted(used):
        print(f"  MUST-FIX (on-screen): {susp[k]['token']} — {susp[k]['reason']}", file=sys.stderr)
    sys.exit(1 if used or (plan is None and susp) else 0)


if __name__ == "__main__":
    main()
