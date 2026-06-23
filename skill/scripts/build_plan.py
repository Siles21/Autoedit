#!/usr/bin/env python3
"""build_plan.py — Stage 2 scaffold: draft an animation plan from words.json.

This pre-fills the deterministic part (every spoken number → a `stat` candidate
anchored to its timecode). Claude then reads words.json + the user's transcript
and enriches the plan with enumerations, reveals and lower-thirds, and curates
the stat candidates (labels, formatting, dropping noise). The plan is the gate
artefact reviewed by Simon before any rendering happens.

    python3 build_plan.py <words.json> [--out plan.draft.json]
    python3 build_plan.py --validate <plan.json>
    python3 build_plan.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import (detect_numbers, detect_enumerations, detect_comparisons,
                    validate_plan, load_plan, anchor_phrase_at,
                    find_anchor_seconds, gap_report, seconds_to_tc,
                    non_person_lowerthirds, strip_non_person_lowerthirds,
                    count_anchor_matches)


def draft_from_words(words: list[dict]) -> dict:
    """Build a draft plan: one stat candidate per spoken number."""
    stats = detect_numbers(words)
    return {
        "version": 1,
        "note": (
            "DRAFT — auto-detected numbers only. Claude: curate these stats "
            "(labels/formatting, drop noise) and ADD enumeration / reveal / "
            "lowerthird entries from the transcript. Then Simon approves."
        ),
        "animations": stats,
    }


_STOP = set(
    "und der die das ein eine einem einen dem den des von zu zur zum mit für auf ist sind "
    "war wird wie wir ihr sie ich du er es im in an am als auch noch sich dass oder aber bei "
    "nur sehr mehr hier heute dann also so um über unter durch nach vor aus dass man kann "
    "haben hat habe diese dieser dieses diesem genau schon".split())


def _keyword_at(words: list[dict], t: float, win: float = 4.0) -> str | None:
    """Pick the strongest CAPITALISED token (German noun) near t — the longest
    one. German nouns are upper-cased, so this surfaces the meaningful term
    (Vermögensverwaltung, Risikomanagement) and skips weak adjectives/verbs.
    Falls back to a wider window before giving up."""
    def pick(window: float) -> str:
        best = ""
        for w in words:
            if abs(float(w["start"]) - t) > window:
                continue
            tok = (w.get("text") or "").strip(".,!?;:\"'»«()—-…")
            if not tok or not tok[0].isupper():
                continue
            if tok.lower() in _STOP or any(c.isdigit() for c in tok):
                continue
            if len(tok) > len(best):
                best = tok
        return best
    return pick(win) or pick(win * 1.8) or None


def fill_gaps(plan: dict, words: list[dict], max_gap: float = 15.0) -> int:
    """DISABLED (Simon): keyword-pop lower-thirds don't help and clutter the cut.
    Density must come from SUBSTANTIVE graphics — real stats, enumerations,
    comparisons surfaced by --coverage / --suggest — not single-word pops. A gap
    is better left open than filled with junk. Kept as a no-op for back-compat."""
    return 0


def _legacy_fill_gaps(plan: dict, words: list[dict], max_gap: float = 15.0) -> int:
    """Old keyword-pop filler — retired. See fill_gaps() docstring."""
    ents = sorted(plan.get("animations", []), key=lambda e: float(e["atSeconds"]))
    inserted: list[dict] = []
    prev = 0.0
    n = 0
    boundaries = [float(e["atSeconds"]) for e in ents] + [float(plan.get("_videoEnd", ents[-1]["atSeconds"] + 1)) if ents else 0.0]
    for at in boundaries:
        gap = at - prev
        if gap > max_gap:
            steps = int(gap // max_gap)
            for k in range(1, steps + 1):
                t = round(prev + k * gap / (steps + 1), 2)
                kw = _keyword_at(words, t)
                if not kw:
                    continue
                anchor = anchor_phrase_at(words, t)
                resolved = find_anchor_seconds(anchor, words)
                off = round(t - resolved, 3) if resolved is not None else 0.0
                n += 1
                inserted.append({
                    "id": f"pop{n}", "type": "lowerthird", "atSeconds": t, "hold": 2.5,
                    "anchorPhrase": anchor, "anchorOffset": off,
                    "content": {"text": kw}})
        prev = at
    plan["animations"] = sorted(ents + inserted, key=lambda e: float(e["atSeconds"]))
    return len(inserted)


def backfill_anchors(plan: dict, words: list[dict], *, force: bool = False) -> int:
    """Fill anchorPhrase for entries that lack one (or all, if force) from the
    words spoken at their atSeconds → makes the plan re-syncable. Returns count."""
    n = 0
    for e in plan.get("animations", []):
        if force or not (e.get("anchorPhrase") or "").strip():
            at = float(e.get("atSeconds", 0.0))
            phrase = anchor_phrase_at(words, at)
            if phrase:
                e["anchorPhrase"] = phrase
                # Preserve the offset between the cue and the spoken anchor word so
                # re-sync restores the exact relative timing, not just the word start.
                resolved = find_anchor_seconds(phrase, words)
                if resolved is not None:
                    e["anchorOffset"] = round(at - resolved, 3)
                n += 1
    return n


def _selftest() -> None:
    words = [
        {"text": "wir", "start": 0.2, "end": 0.4},
        {"text": "haben", "start": 0.4, "end": 0.7},
        {"text": "12", "start": 0.8, "end": 1.1},
        {"text": "Prozent", "start": 1.1, "end": 1.6},
        {"text": "und", "start": 1.7, "end": 1.9},
        {"text": "3", "start": 2.0, "end": 2.2},
        {"text": "Standorte", "start": 2.3, "end": 2.9},
    ]
    draft = draft_from_words(words)
    assert draft["animations"][0]["content"]["value"] == "12 %", draft
    assert draft["animations"][1]["content"]["value"] == "3", draft
    assert draft["animations"][1]["anchorPhrase"] == "3", draft
    # the draft itself must validate (so the gate never rejects our own output)
    assert validate_plan(draft) == [], validate_plan(draft)

    # backfill: a timecode-only entry gets a phrase that round-trips to ~its time
    wlist = [{"text": "wir", "start": 0.2, "end": 0.4}, {"text": "haben", "start": 0.4, "end": 0.7},
             {"text": "heute", "start": 0.8, "end": 1.1}, {"text": "zwölf", "start": 1.2, "end": 1.5},
             {"text": "Prozent", "start": 1.5, "end": 1.9}, {"text": "Rendite", "start": 2.0, "end": 2.5}]
    p = {"animations": [{"id": "x", "type": "reveal", "atSeconds": 0.8, "hold": 3.0,
                         "content": {"text": "Y"}}]}
    assert backfill_anchors(p, wlist) == 1
    ph = p["animations"][0]["anchorPhrase"]
    assert ph.lower().startswith("heute zwölf"), ph
    assert abs((find_anchor_seconds(ph, wlist) or -1) - 0.8) < 0.001  # round-trips
    print("build_plan selftest OK")


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 2: draft / validate an animation plan")
    ap.add_argument("words", nargs="?", type=Path, help="words.json from Stage 1")
    ap.add_argument("--out", type=Path, default=None, help="output draft plan (default: <words>.plan.draft.json)")
    ap.add_argument("--validate", type=Path, default=None, metavar="PLAN",
                    help="validate an existing animation-plan.json and exit")
    ap.add_argument("--backfill", type=Path, default=None, metavar="PLAN",
                    help="fill missing anchorPhrase in PLAN from --words, then write it back")
    ap.add_argument("--resolve", type=Path, default=None, metavar="PLAN",
                    help="fill atSeconds in PLAN from each anchorPhrase using the positional words.json")
    ap.add_argument("--lead", type=float, default=0.4,
                    help="global lead-in (s): start each animation this much BEFORE its anchor word so the "
                         "entrance finishes as the word lands (fixes 'too late'). Per-entry override: leadIn.")
    ap.add_argument("--force", action="store_true", help="with --backfill: overwrite existing anchors too")
    ap.add_argument("--suggest", action="store_true",
                    help="scan words.json for ALL animatable moments (numbers, enumerations, comparisons) → suggestions.md")
    ap.add_argument("--coverage", type=Path, default=None, metavar="PLAN",
                    help="completeness critic: list detected moments (esp. enumerations) NOT covered by PLAN (uses positional words.json)")
    ap.add_argument("--window", type=float, default=6.0, help="coverage match window in seconds")
    ap.add_argument("--strip-lt", type=Path, default=None, metavar="PLAN",
                    help="remove every non-person lower-third (keyword-pops, concept/CTA straps) and write PLAN back")
    ap.add_argument("--lint-lt", type=Path, default=None, metavar="PLAN",
                    help="list non-person lower-thirds without changing PLAN; exit 1 if any exist")
    ap.add_argument("--gapcheck", type=Path, default=None, metavar="PLAN",
                    help="report start-to-start gaps; flag any > --max-gap")
    ap.add_argument("--fill-gaps", type=Path, default=None, metavar="PLAN",
                    help="insert keyword-pop lowerthirds (from positional words.json) so no gap > --max-gap")
    ap.add_argument("--max-gap", type=float, default=15.0)
    ap.add_argument("--video-end", type=float, default=None, help="video length (s) to check the trailing gap")
    ap.add_argument("--fps", type=float, default=50.0, help="fps for timecode display in --gapcheck")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return

    if args.backfill:
        if not args.words:
            ap.error("--backfill needs words.json as the positional argument: "
                     "build_plan.py <words.json> --backfill <plan.json>")
        plan = load_plan(args.backfill)
        words = json.loads(args.words.read_text(encoding="utf-8")).get("words", [])
        if not words:
            sys.exit("ERROR: --words has no 'words'.")
        n = backfill_anchors(plan, words, force=args.force)
        out = args.out or args.backfill
        out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"backfilled {n} anchorPhrase(s) → {out}", file=sys.stderr)
        print(str(out))
        return

    if args.coverage:
        if not args.words:
            ap.error("--coverage needs words.json as the positional argument")
        import bisect
        words = json.loads(args.words.read_text(encoding="utf-8")).get("words", [])
        plan = load_plan(args.coverage)
        times = sorted(float(e["atSeconds"]) for e in plan.get("animations", []))

        def covered(t: float) -> bool:
            i = bisect.bisect_left(times, t)
            return any(0 <= j < len(times) and abs(times[j] - t) <= args.window for j in (i - 1, i))

        enums = [e for e in detect_enumerations(words) if not covered(e["atSeconds"])]
        comps = [c for c in detect_comparisons(words) if not covered(c["atSeconds"])]
        nums = [n for n in detect_numbers(words) if not covered(n["atSeconds"])]
        lines = ["# Vollständigkeits-Kritik — animierbare Stellen OHNE Animation", "",
                 f"Plan: {len(times)} Animationen · Fenster ±{args.window}s", ""]
        lines.append(f"## Nicht abgebildete AUFZÄHLUNGEN ({len(enums)}) — hohe Priorität")
        for e in enums:
            lines.append(f"- `{seconds_to_tc(e['atSeconds'], 50)}` {e['cue']} — {e['snippet'][:90]}")
        lines.append(f"\n## Nicht abgebildete VERGLEICHE ({len(comps)})")
        for c in comps:
            lines.append(f"- `{seconds_to_tc(c['atSeconds'], 50)}` {c['cue']} — {c['snippet'][:90]}")
        lines.append(f"\n## Nicht abgebildete ZAHLEN ({len(nums)})")
        for n in nums:
            lines.append(f"- `{seconds_to_tc(n['atSeconds'], 50)}` {n['content']['value']} — {n['anchorPhrase']}")
        out = args.out or args.coverage.with_suffix(".coverage.md")
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"coverage critic: {len(enums)} Aufzählungen, {len(comps)} Vergleiche, "
              f"{len(nums)} Zahlen NICHT abgebildet → {out}", file=sys.stderr)
        for e in enums:
            print(f"  FEHLT (Aufzählung) {seconds_to_tc(e['atSeconds'], 50)}: {e['cue']} — {e['snippet'][:60]}",
                  file=sys.stderr)
        print(str(out))
        sys.exit(1 if (enums or comps) else 0)

    if args.suggest:
        if not args.words:
            ap.error("--suggest needs words.json as the positional argument")
        words = json.loads(args.words.read_text(encoding="utf-8")).get("words", [])
        nums = detect_numbers(words)
        enums = detect_enumerations(words)
        comps = detect_comparisons(words)
        rows = ([{"t": n["atSeconds"], "kind": "Zahl → stat/kpibig",
                  "cue": n["content"]["value"], "snip": n["anchorPhrase"]} for n in nums]
                + [{"t": e["atSeconds"], "kind": "AUFZÄHLUNG → sequence/enumeration",
                    "cue": e["cue"], "snip": e["snippet"]} for e in enums]
                + [{"t": c["atSeconds"], "kind": "Vergleich → comparebars",
                    "cue": c["cue"], "snip": c["snippet"]} for c in comps])
        rows.sort(key=lambda r: r["t"])
        md = ["# Animations-Chancen (automatisch erkannt)", "",
              f"{len(nums)} Zahlen · {len(enums)} Aufzählungen · {len(comps)} Vergleiche", "",
              "| TC | Typ-Vorschlag | Auslöser | Kontext |", "|---|---|---|---|"]
        for r in rows:
            md.append(f"| `{seconds_to_tc(r['t'], 50)}` | {r['kind']} | {r['cue']} | {r['snip'][:80]} |")
        out = args.out or args.words.with_suffix(".suggestions.md")
        out.write_text("\n".join(md) + "\n", encoding="utf-8")
        print(f"suggestions: {len(nums)} Zahlen, {len(enums)} Aufzählungen, {len(comps)} Vergleiche → {out}",
              file=sys.stderr)
        print(str(out))
        return

    if getattr(args, "fill_gaps", None):
        if not args.words:
            ap.error("--fill-gaps needs words.json as the positional argument")
        plan = load_plan(args.fill_gaps)
        words = json.loads(args.words.read_text(encoding="utf-8")).get("words", [])
        if args.video_end:
            plan["_videoEnd"] = args.video_end
        fill_gaps(plan, words, max_gap=args.max_gap)  # retired: keyword-pops disabled
        plan.pop("_videoEnd", None)
        print("--fill-gaps is RETIRED: keyword-pop lower-thirds don't help (Simon). "
              "Fill gaps with substantive graphics from --coverage / --suggest instead. "
              "Plan left unchanged.", file=sys.stderr)
        print(str(args.fill_gaps))
        return

    if args.lint_lt:
        plan = load_plan(args.lint_lt)
        bad = non_person_lowerthirds(plan)
        print(f"lint-lt: {len(bad)} non-person lower-third(s)"
              + (": " + ", ".join(bad) if bad else " — clean"), file=sys.stderr)
        sys.exit(1 if bad else 0)

    if args.strip_lt:
        plan = load_plan(args.strip_lt)
        removed = strip_non_person_lowerthirds(plan)
        out = args.out or args.strip_lt
        out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"stripped {len(removed)} non-person lower-third(s) → {out}", file=sys.stderr)
        if removed:
            print("  removed: " + ", ".join(removed), file=sys.stderr)
        print(str(out))
        return

    if args.gapcheck:
        plan = load_plan(args.gapcheck)
        rows, violations = gap_report(plan, max_gap=args.max_gap, video_end=args.video_end)
        maxgap = max((r["gap"] for r in rows), default=0.0)
        print(f"gapcheck: {len(plan.get('animations', []))} animations, max gap {maxgap:.1f}s, "
              f"{len(violations)} gap(s) > {args.max_gap}s", file=sys.stderr)
        for r in violations:
            print(f"  {r['gap']:5.1f}s  {seconds_to_tc(r['prev_at'], args.fps)}–"
                  f"{seconds_to_tc(r['at'], args.fps)}  ({r['prev']} → {r['next']})", file=sys.stderr)
        sys.exit(1 if violations else 0)

    if args.resolve:
        if not args.words:
            ap.error("--resolve needs words.json as the positional argument")
        plan = load_plan(args.resolve)
        words = json.loads(args.words.read_text(encoding="utf-8")).get("words", [])
        if not words:
            sys.exit("ERROR: words.json has no 'words'.")
        unresolved = []
        ambiguous = []  # anchors that occur >1× → resolver picks FIRST = timing risk
        for e in plan.get("animations", []):
            ph = (e.get("anchorPhrase") or "").strip()
            t = find_anchor_seconds(ph, words) if ph else None
            if t is None:
                unresolved.append(e.get("id"))
            else:
                n = count_anchor_matches(ph, words)
                if n > 1:
                    ambiguous.append((e.get("id"), n, round(t, 1)))
                lead = float(e["leadIn"]) if e.get("leadIn") is not None else args.lead
                at = float(t) + float(e.get("anchorOffset", 0.0)) - lead
                e["atSeconds"] = round(max(0.0, at), 2)
        out = args.out or args.resolve
        out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        ok = len(plan.get("animations", [])) - len(unresolved)
        print(f"resolved {ok} atSeconds; {len(unresolved)} unresolved; "
              f"{len(ambiguous)} ambiguous → {out}", file=sys.stderr)
        if unresolved:
            print("  UNRESOLVED (fix anchorPhrase to match the transcript): "
                  + ", ".join(unresolved), file=sys.stderr)
        if ambiguous:
            print("  AMBIGUOUS anchors (occur >1× → picks first @t, may mistime — "
                  "use a longer/unique phrase at the exact key word):", file=sys.stderr)
            for aid, n, t in ambiguous:
                print(f"    {aid}: {n}× matches (first @{t}s)", file=sys.stderr)
        print(str(out))
        return

    if args.validate:
        plan = load_plan(args.validate)
        errs = validate_plan(plan)
        if errs:
            print("INVALID:", file=sys.stderr)
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            sys.exit(1)
        n = len(plan.get("animations", []))
        print(f"valid — {n} animation(s)")
        return

    if not args.words:
        ap.error("words.json is required (or use --validate / --selftest)")

    data = json.loads(args.words.read_text(encoding="utf-8"))
    words = data.get("words", [])
    if not words:
        sys.exit("ERROR: words.json has no 'words' — run align_words.py first.")
    draft = draft_from_words(words)
    out = args.out or args.words.with_suffix(".plan.draft.json")
    out.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"drafted {len(draft['animations'])} stat candidate(s) → {out}", file=sys.stderr)
    print("Next: Claude curates + adds enumeration/reveal/lowerthird, then Simon approves.",
          file=sys.stderr)
    print(str(out))


if __name__ == "__main__":
    main()
