#!/usr/bin/env python3
"""qc_spell.py — QC-2 spell / typo gate for an animation plan.

No German dictionary is installed and a plain dict would false-flag every brand
name / English term, so this is a TWO-LAYER gate:
  1. Deterministic flags (run in CI/batch): a blocklist of known Whisper
     artefacts + suspicious patterns (mid-word capitals like "ProLiveGmbH",
     very long garbled compounds, repeated letters). High-precision, catches the
     errors that actually slip in (esp. keyword-pops pulled from raw transcript).
  2. Review export: ALL unique display strings are written to <plan>.spellcheck.txt
     for a final human/LLM pass (handles nuance + proper nouns).

    qc_spell.py <animation-plan.json> [--out review.txt]
    qc_spell.py --selftest
Exit code 1 if deterministic flags found.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from common import load_plan, plan_strings

# Known Whisper-derived garbles seen in this content (extend as new ones appear).
BLOCKLIST = {
    "rückhauswerte", "prolivegmbh", "mundstänken", "anovalisierte",
    "aufgräufer", "provisionsaläuße", "finanzbausche", "investmentbelohnungen",
    "bergtagen", "beformt", "outbeformt", "essordallocation", "retteneintritt",
    "läger", "ruhestandsplauung", "verdreifahrung", "sternofreihe", "sternarfrei",
    "staunenfreien", "erbnisse", "polissen", "deuerliche", "heibklassischen",
}
# Legit brand/product/abbrev terms with mixed case — never flag.
ALLOWLIST = {
    "prolife", "gmbh", "ag", "kg", "ohg", "se", "iphone", "ipad", "neocore",
    "dsgvo", "etf", "nav", "performance", "investments",
}
_MIDCAP = re.compile(r"[a-zäöüß][A-ZÄÖÜ]")          # camelCase boundary
_REPEAT4 = re.compile(r"([a-zäöüß])\1\1\1")          # 4+ same letter (Kipppunkt has only 3 → ok)
_STRIP = ".,!?;:\"'»«()—-…%€"


def token_flag(tok: str) -> str | None:
    """Reason why a single token looks like a typo/garble, or None. Digits are
    skipped (numbers like 500.000 are handled by the value-formatting, not spell);
    allowlisted brand terms are never flagged; mid-word capitals only count as a
    garble when there are 2+ (a merge like 'ProLiveGmbH'), not 1 ('ProLife')."""
    if len(tok) < 4 or any(c.isdigit() for c in tok):
        return None
    low = tok.lower()
    if low in ALLOWLIST:
        return None
    if low in BLOCKLIST:
        return "blocklist (Whisper-Artefakt)"
    if not tok.isupper() and len(_MIDCAP.findall(tok)) >= 2:
        return "verschmolzene Wörter (mehrere Binnen-Großbuchstaben)"
    if _REPEAT4.search(low):
        return "4+ gleiche Buchstaben"
    if len(tok) > 24 and tok[0].islower():
        return "sehr langes Kleinwort (evtl. garbled)"
    return None


def flag_strings(strings: list[tuple[str, str, str]]) -> list[dict]:
    flags = []
    for eid, fld, text in strings:
        for raw in text.split():
            reason = token_flag(raw.strip(_STRIP))
            if reason:
                flags.append({"id": eid, "field": fld, "token": raw.strip(_STRIP), "reason": reason})
    return flags


def _selftest() -> None:
    plan = {"animations": [
        {"id": "a", "type": "lowerthird", "atSeconds": 1, "hold": 3,
         "content": {"text": "Rückhauswerte", "sublabel": "ProLiveGmbH"}},
        {"id": "b", "type": "reveal", "atSeconds": 2, "hold": 3,
         "content": {"text": "Alles korrekt und sauber geschrieben."}},
    ]}
    flags = flag_strings(plan_strings(plan))
    toks = {f["token"].lower() for f in flags}
    assert "rückhauswerte" in toks and "prolivegmbh" in toks, flags
    assert not any(f["id"] == "b" for f in flags), flags
    print("qc_spell selftest OK")


def main() -> None:
    ap = argparse.ArgumentParser(description="QC-2 spell/typo gate")
    ap.add_argument("plan", nargs="?", type=Path)
    ap.add_argument("--out", type=Path, default=None, help="review export (default <plan>.spellcheck.txt)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
        return
    if not args.plan:
        ap.error("plan required (or --selftest)")
    plan = load_plan(args.plan)
    strings = plan_strings(plan)
    flags = flag_strings(strings)

    # review export: unique strings, sorted
    uniq = sorted({t for _, _, t in strings})
    out = args.out or args.plan.with_suffix(".spellcheck.txt")
    out.write_text("\n".join(uniq) + "\n", encoding="utf-8")

    print(f"QC-2 spell: {len(strings)} strings ({len(uniq)} unique) → review export {out}",
          file=sys.stderr)
    print(f"  deterministic flags: {len(flags)}", file=sys.stderr)
    for f in flags:
        print(f"    {f['id']}.{f['field']}: {f['token']!r} — {f['reason']}", file=sys.stderr)
    if not flags:
        print("  (keine harten Treffer; trotzdem Review-Export für LLM/Mensch-Check)", file=sys.stderr)
    sys.exit(1 if flags else 0)


if __name__ == "__main__":
    main()
