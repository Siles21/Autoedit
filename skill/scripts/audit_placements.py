#!/usr/bin/env python3
"""audit_placements.py — single source of truth for WHERE every animation sits.

Builds/refreshes a persistent **placement registry** and audits every clip's
live position against the time its anchor phrase is actually spoken. Run it after
EVERY place/move/remove/relink and on demand ("check every animation"), so drift
is caught instead of silently accumulating.

    audit_placements.py --info <premiere_info.json> --words <words.json> \
        --plans plan1.json,plan2.json,... --out <registry.json> [--lead 0.4] [--tol 3]

`--info` = the JSON from `node premiere_drive.js info` (the live sequence state).
`--words` = the transcript. `--plans` = all animation-plan files (for anchor+type).

Writes `<registry.json>` (the ledger) and prints a status report. Statuses:
  ok        within --tol of the anchor (spoken-correct)
  DRIFTED   |actual - expected| > tol  (eindeutiger Anker) → needs retime
  AMBIGUOUS anchor occurs >1× → can't auto-verify, check by hand
  NO-ANCHOR placed but no anchor in any plan (screenshots/foilen) → info only
  MISSING   in a plan with anchor but NOT on the timeline (deleted/never placed)
Exit 1 if any DRIFTED or MISSING (so it can gate a pipeline).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402

TICKS = 254_016_000_000


def _norm_words(raw):
    out = []
    for t in raw:
        out.append({
            "text": t.get("word") or t.get("text") or t.get("w") or "",
            "start": float(t.get("start") or t.get("t") or t.get("s") or 0),
            "end": float(t.get("end") or 0),
        })
    return out


def _tc(x):
    return f"{int(x // 60):02d}:{x % 60:04.1f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--info", type=Path, required=True, help="`premiere_drive.js info` JSON")
    ap.add_argument("--words", type=Path, required=True)
    ap.add_argument("--plans", required=True, help="comma list of animation-plan*.json")
    ap.add_argument("--out", type=Path, required=True, help="registry JSON to write")
    ap.add_argument("--media-dir", default=None, help="permanent overlay folder (for file paths)")
    ap.add_argument("--lead", type=float, default=0.4)
    ap.add_argument("--tol", type=float, default=3.0)
    args = ap.parse_args()

    # 1) anchors + meta from all plans
    meta = {}
    for p in args.plans.split(","):
        p = p.strip()
        if not p:
            continue
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            continue
        for e in d.get("animations", []):
            meta.setdefault(e["id"], {
                "type": e.get("type"), "anchorPhrase": e.get("anchorPhrase"),
                "hold": e.get("hold"),
            })

    words = _norm_words(json.loads(args.words.read_text(encoding="utf-8")).get("words", []))

    # 2) live positions from info
    info = json.loads(args.info.read_text(encoding="utf-8"))
    seqs = info.get("sequences", [])
    seq = next((x for x in seqs if x.get("isActive")), seqs[0] if seqs else None)
    if not seq:
        sys.exit("audit: no sequence in --info")
    placed = {}
    for vt in seq["videoTracks"]:
        for c in vt["tracks"]:
            if "__" not in c["name"] and c["name"] not in meta:
                continue
            pid = c["name"].split("__")[0]
            placed.setdefault(pid, {
                "track": f"V{vt['index'] + 1}",
                "atSeconds": round(float(c["startTimeTicks"]) / TICKS, 2),
                "durationSeconds": round(float(c["durationSeconds"]), 2),
                "clipName": c["name"],
            })

    # 3) reconcile → registry
    reg = []
    drifted = missing = ambiguous = ok = noanchor = 0
    for pid in sorted(set(list(meta) + list(placed))):
        m = meta.get(pid, {})
        pl = placed.get(pid)
        anchor = m.get("anchorPhrase")
        exp = common.find_anchor_seconds(anchor, words) if anchor else None
        n = common.count_anchor_matches(anchor, words) if anchor else 0
        entry = {
            "id": pid, "type": m.get("type"), "anchorPhrase": anchor,
            "expectedSeconds": round(exp - args.lead, 2) if exp is not None else None,
            "atSeconds": pl["atSeconds"] if pl else None,
            "track": pl["track"] if pl else None,
            "durationSeconds": pl["durationSeconds"] if pl else None,
            "file": (str(Path(args.media_dir) / pl["clipName"]) if (args.media_dir and pl) else None),
        }
        if pl is None:
            if anchor:
                entry["status"] = "MISSING"; missing += 1
            else:
                continue  # plan-only, no anchor, not placed → ignore
        elif anchor is None:
            entry["status"] = "NO-ANCHOR"; noanchor += 1
        elif exp is None:
            entry["status"] = "ANCHOR-NOT-FOUND"; ambiguous += 1
        elif n > 1:
            entry["status"] = "AMBIGUOUS"; entry["anchorMatches"] = n; ambiguous += 1
        else:
            delta = pl["atSeconds"] - (exp - args.lead)
            entry["deltaSeconds"] = round(delta, 2)
            if abs(delta) > args.tol:
                entry["status"] = "DRIFTED"; drifted += 1
            else:
                entry["status"] = "ok"; ok += 1
        reg.append(entry)

    args.out.write_text(json.dumps({"entries": reg}, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"REGISTRY → {args.out}  ({len(reg)} animations)", file=sys.stderr)
    print(f"  ok {ok} · DRIFTED {drifted} · MISSING {missing} · "
          f"AMBIGUOUS/notfound {ambiguous} · no-anchor {noanchor}", file=sys.stderr)
    for e in sorted([r for r in reg if r["status"] == "DRIFTED"],
                    key=lambda r: -abs(r.get("deltaSeconds", 0))):
        print(f"  DRIFTED {e['id']:22} {_tc(e['atSeconds'])} → soll {_tc(e['expectedSeconds'])} "
              f"({e['deltaSeconds']:+.0f}s) {e['track']}", file=sys.stderr)
    for e in [r for r in reg if r["status"] == "MISSING"]:
        print(f"  MISSING {e['id']:22} (Anker da, nicht platziert)", file=sys.stderr)

    sys.exit(1 if (drifted or missing) else 0)


if __name__ == "__main__":
    main()
