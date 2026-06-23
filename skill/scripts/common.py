#!/usr/bin/env python3
"""common.py — shared pure helpers for the premiere-sub-animations pipeline.

No AI, no heavy deps. Holds the anchor-matching, number detection, timecode and
plan-validation logic used by build_plan.py / integrate.py / qc.py.

The anchor/number logic mirrors neocore-reel-studio's reel_prepare.py, but works
directly in SECONDS — the Premiere cut is already final, so there is no
keep-range remap from source-time to output-time.

    python3 common.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re
from math import gcd
from pathlib import Path

# adb-mcp ticks-per-second (uxp/pr/commands/consts.js). 1 s == this many ticks.
TICKS_PER_SECOND = 254_016_000_000

# Output frame/size conventions for the two delivery formats.
FORMATS: dict[str, tuple[int, int]] = {
    "16x9": (1920, 1080),
    "9x16": (1080, 1920),
}

VALID_TYPES = {"stat", "enumeration", "reveal", "lowerthird", "sequence",
               "kpibig", "comparebars", "chart", "comparetable", "comparecards",
               "cta", "caption", "splitheadline", "fullcard", "accentbar", "lottie"}
SEQ_KINDS = {"label", "kpi", "text", "bullet"}
# Types with internal motion (count-up / staggered bars / staggered items) —
# exempt from the single-beat linger cap, may run up to MAX_HOLD like a sequence.
# caption: continuous word-by-word track, its own timing — exempt from hold caps.
ANIMATED_TYPES = {"sequence", "comparebars", "chart", "comparetable", "comparecards", "enumeration", "caption",
                  "fullcard", "splitheadline", "accentbar", "lottie"}
# Document-cutaway types whose rows reveal across a spoken passage (transcript-paced)
# may stay up much longer than a normal overlay — own higher hold cap.
LONG_HOLD_TYPES = {"comparetable", "caption"}
LONG_MAX_HOLD = 60.0
# Face-free zones written by face_zones.py into entry.placement.zone.
VALID_ZONES = {"bottom", "top", "left", "right", "bottom-left", "bottom-right",
               "top-left", "top-right", "center"}

# Animation timing rules (Simon, 2026-06-09):
#   - no animation longer than 10s
#   - a single-beat type must not linger (use a multi-step `sequence` if longer)
#   - inside a sequence: first beat near 0, a new event at least every 2s, and
#     the tail after the last beat stays short — so it is never static.
MAX_HOLD = 10.0
MAX_SINGLE_HOLD = 4.5
MAX_GAP = 2.0
MAX_TAIL = 2.5

_STRIP = ".,!?;:\"'»«()—-…"
_NUMERIC = re.compile(r"\d")

# Spoken unit words that belong to a preceding number ("4,2 prozent" → one card).
_UNIT_WORDS = {
    "prozent", "%", "euro", "€", "eur", "jahre", "jahren", "jahr", "monate",
    "monaten", "monat", "tage", "tagen", "tag", "millionen", "million", "mio",
    "milliarden", "milliarde", "tausend", "quadratmeter", "qm", "m²", "k",
}


# --------------------------------------------------------------------------- #
# Tokenisation + anchor matching (seconds-native)
# --------------------------------------------------------------------------- #

def norm_tokens(text: str) -> list[str]:
    """Lowercase, whitespace-split, strip surrounding punctuation.

    Keeps internal characters like the comma in "4,2" and German umlauts so a
    spoken-phrase anchor matches the transcript faithfully.
    """
    out: list[str] = []
    for raw in text.lower().split():
        t = raw.strip(_STRIP)
        if t:
            out.append(t)
    return out


def find_anchor_seconds(anchor: str, words: list[dict]) -> float | None:
    """Return the start time (seconds) where `anchor` (a spoken phrase) begins.

    `words` is [{text, start, end, ...}]. Matches a consecutive run of
    normalized tokens against the spoken word stream; returns None if not found.
    """
    atoks = norm_tokens(anchor)
    if not atoks:
        return None
    stream: list[tuple[str, float]] = []
    for w in words:
        for t in norm_tokens(w["text"]):
            stream.append((t, float(w["start"])))
    n = len(atoks)
    for i in range(len(stream) - n + 1):
        if [stream[i + j][0] for j in range(n)] == atoks:
            return stream[i][1]
    return None


def count_anchor_matches(anchor: str, words: list[dict]) -> int:
    """How many times `anchor` occurs in the transcript. >1 = ambiguous → the
    resolver picks the FIRST, which may mistime the animation. Pick a longer/
    more unique phrase (ideally the exact words at the key concept)."""
    atoks = norm_tokens(anchor)
    if not atoks:
        return 0
    stream = [t for w in words for t in norm_tokens(w["text"])]
    n = len(atoks)
    return sum(1 for i in range(len(stream) - n + 1)
               if stream[i:i + n] == atoks)


def _snippet(words: list[dict], idx: int, before: int = 2, after: int = 16) -> str:
    lo = max(0, idx - before)
    return " ".join(w["text"] for w in words[lo: idx + after]).strip()


# Cue words that signal an enumeration the speaker is making out loud.
_ORDINALS = {"erstens", "zweitens", "drittens", "viertens", "fünftens",
             "erstes", "zweites", "drittes", "erste", "zweite", "dritte"}
_COUNTS = {"zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6,
           "2": 2, "3": 3, "4": 4, "5": 5, "6": 6}
_LIST_NOUNS = {"dinge", "punkte", "gründe", "schritte", "vorteile", "faktoren",
               "aspekte", "säulen", "bausteine", "kriterien", "fragen", "ebenen",
               "bereiche", "möglichkeiten", "sachen", "themen", "merkmale", "stufen"}
_COMPARE_CUES = {"vorher", "nachher", "statt", "anstatt", "stattdessen",
                 "gegensatz", "vergleich", "während", "hingegen", "verdoppelt",
                 "verdreifacht", "vervielfacht", "mehr", "weniger"}


def detect_enumerations(words: list[dict]) -> list[dict]:
    """Find spots where the speaker enumerates — by cue words ('drei Dinge',
    'erstens…', 'zum einen…') and by spoken comma-lists ('A, B, C und D').
    Returns candidate {atSeconds, cue, snippet} for an enumeration/sequence."""
    out: list[dict] = []
    toks = [(w["text"].strip(_STRIP).lower(), float(w["start"]), i) for i, w in enumerate(words)]
    for k, (t, at, i) in enumerate(toks):
        nxt = toks[k + 1][0] if k + 1 < len(toks) else ""
        cue = None
        if t in _ORDINALS:
            cue = f"Ordinalzahl „{t}“"
        elif t in _COUNTS and nxt in _LIST_NOUNS:
            cue = f"„{t} {nxt}“"
        elif t == "zum" and nxt == "einen":
            cue = "„zum einen … zum anderen“"
        elif t in ("folgende", "folgendes", "folgenden"):
            cue = "„folgende(s)“"
        if cue:
            out.append({"atSeconds": round(at, 2), "cue": cue, "snippet": _snippet(words, i)})
    # spoken comma-lists: >=3 comma-ending words within a 16-word window
    comma_idx = [i for i, w in enumerate(words) if w["text"].rstrip().endswith(",")]
    j = 0
    while j < len(comma_idx):
        win = [c for c in comma_idx if comma_idx[j] <= c <= comma_idx[j] + 16]
        if len(win) >= 3:
            i0 = win[0]
            out.append({"atSeconds": round(float(words[i0]["start"]), 2),
                        "cue": "Komma-Liste (A, B, C und D)", "snippet": _snippet(words, i0)})
            j = len([c for c in comma_idx if c <= win[-1]])  # skip past this run
        else:
            j += 1
    out.sort(key=lambda x: x["atSeconds"])
    return out


def detect_comparisons(words: list[dict]) -> list[dict]:
    """Find before/after or X-vs-Y spots → comparebars candidates."""
    out: list[dict] = []
    for i, w in enumerate(words):
        t = w["text"].strip(_STRIP).lower()
        if t in _COMPARE_CUES:
            out.append({"atSeconds": round(float(w["start"]), 2),
                        "cue": f"„{t}“", "snippet": _snippet(words, i)})
    out.sort(key=lambda x: x["atSeconds"])
    return out


def anchor_phrase_at(words: list[dict], seconds: float, n: int = 5) -> str:
    """Derive a stable anchor phrase: the `n` spoken words starting nearest to
    `seconds`. Backfills anchorPhrase so a timecode-only plan becomes re-syncable
    (the phrase, not the absolute time, survives an edit). Longer n = more unique;
    find_anchor_seconds round-trips this back to ~the same time."""
    if not words:
        return ""
    idx = min(range(len(words)), key=lambda i: abs(float(words[i]["start"]) - seconds))
    return " ".join(w["text"] for w in words[idx: idx + n]).strip()


# --------------------------------------------------------------------------- #
# Lower-third hygiene — a lowerthird may ONLY introduce a PERSON
# --------------------------------------------------------------------------- #
# Simon's rule: lower-thirds that aren't names (keyword-pops, concept/CTA straps)
# don't help and must be left out. A valid person strap carries content.person==True
# (the speaker's name in `text`, role/place in `sublabel`). Everything else → drop.

def is_person_lowerthird(entry: dict) -> bool:
    """True only for a genuine person name-strap (content.person truthy)."""
    if entry.get("type") != "lowerthird":
        return True  # not a lowerthird → not our concern here
    return bool(entry.get("content", {}).get("person"))


def non_person_lowerthirds(plan: dict) -> list[str]:
    """ids of lower-thirds that don't introduce a person → should be removed."""
    return [e.get("id") for e in plan.get("animations", [])
            if e.get("type") == "lowerthird" and not is_person_lowerthird(e)]


def strip_non_person_lowerthirds(plan: dict) -> list[str]:
    """Remove every non-person lowerthird from the plan in place. Returns ids removed."""
    drop = set(non_person_lowerthirds(plan))
    plan["animations"] = [e for e in plan.get("animations", []) if e.get("id") not in drop]
    return sorted(drop)


# --------------------------------------------------------------------------- #
# Number detection — pre-fill stat-card candidates
# --------------------------------------------------------------------------- #

def detect_numbers(words: list[dict]) -> list[dict]:
    """Find spoken numbers and emit stat-card candidate stubs.

    A numeric token ("4,2", "1.200") becomes one candidate; a following unit
    word ("prozent", "euro", "%") is folded into the value and the anchor so the
    card reads naturally. label/sublabel are left empty for Claude to fill from
    context (never invented here). Returns [{id,type,anchorPhrase,atSeconds,
    hold,content:{value,label}}].
    """
    cands: list[dict] = []
    n = 0
    i = 0
    flat: list[tuple[str, float]] = []
    for w in words:
        for t in norm_tokens(w["text"]):
            flat.append((t, float(w["start"])))
    while i < len(flat):
        tok, start = flat[i]
        if _NUMERIC.search(tok):
            value = tok
            phrase = tok
            # Fold a trailing unit word into the value/anchor.
            if i + 1 < len(flat) and flat[i + 1][0] in _UNIT_WORDS:
                unit = flat[i + 1][0]
                phrase = f"{tok} {unit}"
                value = f"{tok} {_pretty_unit(unit)}".strip()
                i += 1
            n += 1
            cands.append({
                "id": f"n{n}",
                "type": "stat",
                "anchorPhrase": phrase,
                "atSeconds": round(start, 2),
                "hold": 2.8,
                "content": {"value": value, "label": ""},
            })
        i += 1
    return cands


def _pretty_unit(unit: str) -> str:
    table = {
        "prozent": "%", "%": "%", "euro": "€", "€": "€", "eur": "€",
        "qm": "m²", "m²": "m²", "quadratmeter": "m²",
    }
    return table.get(unit, unit)


# --------------------------------------------------------------------------- #
# Timecode helpers
# --------------------------------------------------------------------------- #

def seconds_to_tc(seconds: float, fps: float) -> str:
    """Whole-frame HH:MM:SS:FF (non-drop). For human-readable placement lists."""
    fps_i = max(1, round(fps))
    frames_total = round(seconds * fps_i)
    ff = frames_total % fps_i
    secs_total = frames_total // fps_i
    hh = secs_total // 3600
    mm = (secs_total % 3600) // 60
    ss = secs_total % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def seconds_to_ticks(seconds: float) -> int:
    """adb-mcp insertion_time_ticks for a clip start at `seconds`."""
    return round(seconds * TICKS_PER_SECOND)


def rational(seconds: float, fps_num: int, fps_den: int) -> str:
    """FCPXML rational time (mirrors auto-cut fcpxml._rational): snap to frame."""
    if seconds <= 0:
        return "0s"
    frames = round(seconds * fps_num / fps_den)
    num = frames * fps_den
    den = fps_num
    g = gcd(num, den)
    num //= g
    den //= g
    return f"{num}s" if den == 1 else f"{num}/{den}s"


# --------------------------------------------------------------------------- #
# Plan validation
# --------------------------------------------------------------------------- #

def validate_plan(plan: dict) -> list[str]:
    """Return a list of human-readable errors (empty == valid)."""
    errs: list[str] = []
    entries = plan.get("animations")
    if not isinstance(entries, list) or not entries:
        return ["plan.animations missing or empty (expected a non-empty list)"]
    seen_ids: set[str] = set()
    for idx, e in enumerate(entries):
        where = f"animations[{idx}]"
        eid = e.get("id")
        if not eid:
            errs.append(f"{where}: missing 'id'")
        elif eid in seen_ids:
            errs.append(f"{where}: duplicate id {eid!r}")
        else:
            seen_ids.add(eid)
        t = e.get("type")
        if t not in VALID_TYPES:
            errs.append(f"{where}: type {t!r} not in {sorted(VALID_TYPES)}")
        at = e.get("atSeconds")
        if not isinstance(at, (int, float)) or at < 0:
            errs.append(f"{where}: atSeconds must be a number >= 0")
        hold = e.get("hold")
        cap = LONG_MAX_HOLD if t in LONG_HOLD_TYPES else MAX_HOLD
        if not isinstance(hold, (int, float)) or hold <= 0:
            errs.append(f"{where}: hold must be a number > 0")
        elif hold > cap:
            errs.append(f"{where}: hold {hold}s exceeds the {cap}s maximum")
        elif t not in ANIMATED_TYPES and hold > MAX_SINGLE_HOLD:
            errs.append(
                f"{where}: {t} hold {hold}s > {MAX_SINGLE_HOLD}s — a single-beat "
                f"animation must not linger; use a multi-step 'sequence' instead")

        pl = e.get("placement")
        if pl is not None:
            if not isinstance(pl, dict):
                errs.append(f"{where}: placement must be an object")
            else:
                z = pl.get("zone")
                if z is not None and z not in VALID_ZONES:
                    errs.append(f"{where}: placement.zone {z!r} not in {sorted(VALID_ZONES)}")
                fb = pl.get("faceBox")
                if fb is not None:
                    if not isinstance(fb, dict) or any(
                            not isinstance(fb.get(k), (int, float)) or not (0 <= fb.get(k, -1) <= 1.5)
                            for k in ("x", "y", "w", "h")):
                        errs.append(f"{where}: placement.faceBox needs numeric x,y,w,h in 0..1")

        if t == "sequence":
            errs.extend(_validate_sequence(e, where, hold))
            continue

        c = e.get("content")
        if not isinstance(c, dict):
            errs.append(f"{where}: content must be an object")
            continue
        if t in ("stat", "kpibig"):
            if not str(c.get("value", "")).strip():
                errs.append(f"{where}: {t} needs content.value")
        elif t == "enumeration":
            items = c.get("items")
            if not isinstance(items, list) or len(items) < 2:
                errs.append(f"{where}: enumeration needs content.items (>=2)")
        elif t in ("reveal", "lowerthird", "cta", "accentbar"):
            if not str(c.get("text", "")).strip():
                errs.append(f"{where}: {t} needs content.text")
        elif t == "splitheadline":
            if not str(c.get("headLeft", "")).strip() and not str(c.get("headRight", "")).strip():
                errs.append(f"{where}: splitheadline needs content.headLeft and/or headRight")
        elif t == "fullcard":
            if c.get("variant") == "badge":
                if not str(c.get("icon", "")).strip():
                    errs.append(f"{where}: fullcard badge needs content.icon")
            elif not str(c.get("text", "")).strip():
                errs.append(f"{where}: fullcard text needs content.text")
        elif t == "lottie":
            if not str(c.get("src", "")).strip():
                errs.append(f"{where}: lottie needs content.src (a .json under public/lottie/ or an https URL)")
        elif t == "comparebars":
            for k in ("before", "after"):
                pair = c.get(k)
                if not isinstance(pair, dict) or not str(pair.get("value", "")).strip():
                    errs.append(f"{where}: comparebars needs content.{k} with a value")
        elif t == "chart":
            series = c.get("series")
            if not isinstance(series, list) or len(series) < 2:
                errs.append(f"{where}: chart needs content.series (>=2 points)")
            elif any(not str(p.get("value", "")).strip() for p in series if isinstance(p, dict)):
                errs.append(f"{where}: every chart series point needs a value")
        elif t == "comparetable":
            cols = c.get("columns")
            if not isinstance(cols, list) or len(cols) < 3:
                errs.append(f"{where}: comparetable needs content.columns (>=3: label + 2 data cols)")
            rows = c.get("rows")
            ndata = (len(cols) - 1) if isinstance(cols, list) else 2
            if not isinstance(rows, list) or len(rows) < 2:
                errs.append(f"{where}: comparetable needs content.rows (>=2)")
            else:
                for j, r in enumerate(rows):
                    if not isinstance(r, dict) or not str(r.get("label", "")).strip():
                        errs.append(f"{where}.rows[{j}]: needs a label")
                    vals = r.get("values") if isinstance(r, dict) else None
                    if not isinstance(vals, list) or len(vals) != ndata:
                        errs.append(f"{where}.rows[{j}]: needs values (one per data column, {ndata})")
        elif t == "comparecards":
            for side in ("left", "right"):
                pane = c.get(side)
                if not isinstance(pane, dict):
                    errs.append(f"{where}: comparecards needs content.{side} (an object)")
                    continue
                items = pane.get("items")
                if not isinstance(items, list) or len(items) < 1:
                    errs.append(f"{where}.{side}: needs items (>=1)")
                else:
                    for j, it in enumerate(items):
                        ok = isinstance(it, str) or (isinstance(it, dict) and str(it.get("text", "")).strip())
                        if not ok:
                            errs.append(f"{where}.{side}.items[{j}]: must be a string or {{text, icon}}")
    return errs


def _validate_sequence(e: dict, where: str, hold) -> list[str]:
    """Enforce the multi-step cadence: first beat near 0, new event every <=2s,
    short tail. Each beat carries its own content per kind."""
    errs: list[str] = []
    steps = e.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        return [f"{where}: sequence needs 'steps' (a list of >=2 beats)"]
    ats: list[float] = []
    for j, st in enumerate(steps):
        sw = f"{where}.steps[{j}]"
        if not isinstance(st, dict):
            errs.append(f"{sw}: step must be an object")
            continue
        at = st.get("at")
        if not isinstance(at, (int, float)) or at < 0:
            errs.append(f"{sw}: at must be a number >= 0")
        else:
            ats.append(float(at))
        kind = st.get("kind")
        if kind not in SEQ_KINDS:
            errs.append(f"{sw}: kind {kind!r} not in {sorted(SEQ_KINDS)}")
        elif kind == "kpi":
            if not str(st.get("value", "")).strip():
                errs.append(f"{sw}: kpi needs 'value'")
        elif not str(st.get("text", "")).strip():
            errs.append(f"{sw}: {kind} needs 'text'")
    if len(ats) == len(steps) and ats:
        ordered = sorted(ats)
        if ats != ordered:
            errs.append(f"{where}: steps must be ordered by 'at'")
        if ordered[0] > 0.5:
            errs.append(f"{where}: first beat must start near 0 (got {ordered[0]}s)")
        for a, b in zip(ordered, ordered[1:]):
            if b - a > MAX_GAP:
                errs.append(f"{where}: gap {b - a:.1f}s between beats exceeds {MAX_GAP}s "
                            f"(a new event is required at least every {MAX_GAP}s)")
        if isinstance(hold, (int, float)) and hold - ordered[-1] > MAX_TAIL:
            errs.append(f"{where}: last beat at {ordered[-1]}s leaves a {hold - ordered[-1]:.1f}s "
                        f"static tail before {hold}s end (max {MAX_TAIL}s)")
    return errs


def load_plan(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def plan_strings(plan: dict) -> list[tuple[str, str, str]]:
    """Every user-visible display string in a plan, as (id, field, text).
    Used by the spell-check QC. Covers content + sequence steps."""
    out: list[tuple[str, str, str]] = []
    for e in plan.get("animations", []):
        eid = e.get("id", "?")
        c = e.get("content", {})
        for fld in ("text", "value", "label", "kicker", "sublabel", "teaser", "unit"):
            v = c.get(fld)
            if isinstance(v, str) and v.strip():
                out.append((eid, fld, v))
        for i, it in enumerate(c.get("items", []) or []):
            if isinstance(it, str) and it.strip():
                out.append((eid, f"items[{i}]", it))
        for pair_key in ("before", "after"):
            pair = c.get(pair_key)
            if isinstance(pair, dict):
                for k in ("label", "value"):
                    if isinstance(pair.get(k), str) and pair[k].strip():
                        out.append((eid, f"{pair_key}.{k}", pair[k]))
        for j, st in enumerate(e.get("steps", []) or []):
            for fld in ("text", "value", "sublabel"):
                v = st.get(fld)
                if isinstance(v, str) and v.strip():
                    out.append((eid, f"steps[{j}].{fld}", v))
    return out


def gap_report(plan: dict, max_gap: float = 15.0, video_end: float | None = None):
    """Start-to-start gaps between consecutive animations (sorted by atSeconds).
    Enforces the "an animation at least every N seconds" rule. Returns
    (rows, violations); each row {prev, next, prev_at, at, gap}."""
    ents = sorted(plan.get("animations", []), key=lambda e: float(e["atSeconds"]))
    rows = []
    prev_at, prev_id = 0.0, "<start>"
    for e in ents:
        at = float(e["atSeconds"])
        rows.append({"prev": prev_id, "next": e["id"], "prev_at": round(prev_at, 2),
                     "at": round(at, 2), "gap": round(at - prev_at, 2)})
        prev_at, prev_id = at, e["id"]
    if video_end:
        rows.append({"prev": prev_id, "next": "<end>", "prev_at": round(prev_at, 2),
                     "at": round(video_end, 2), "gap": round(video_end - prev_at, 2)})
    violations = [r for r in rows if r["gap"] > max_gap]
    return rows, violations


# --------------------------------------------------------------------------- #
# Selftest
# --------------------------------------------------------------------------- #

def _selftest() -> None:
    words = [
        {"text": "heute", "start": 1.0, "end": 1.3, "confidence": 0.9},
        {"text": "4,2", "start": 1.4, "end": 1.7, "confidence": 0.9},
        {"text": "Prozent", "start": 1.7, "end": 2.1, "confidence": 0.9},
        {"text": "Rendite", "start": 2.2, "end": 2.8, "confidence": 0.9},
    ]
    # anchor matching in seconds
    assert find_anchor_seconds("4,2 prozent", words) == 1.4
    assert find_anchor_seconds("nicht da", words) is None

    # number detection folds the unit word
    cands = detect_numbers(words)
    assert len(cands) == 1, cands
    assert cands[0]["anchorPhrase"] == "4,2 prozent"
    assert cands[0]["content"]["value"] == "4,2 %", cands[0]
    assert cands[0]["atSeconds"] == 1.4

    # timecode
    assert seconds_to_tc(0.0, 25) == "00:00:00:00"
    assert seconds_to_tc(1.0, 25) == "00:00:01:00"
    assert seconds_to_tc(61.4, 25) == "00:01:01:10"  # 0.4s*25 = 10 frames
    assert seconds_to_ticks(1.0) == TICKS_PER_SECOND
    assert rational(1.0, 25, 1) == "1s"  # 25 frames @ 25fps == 1 second
    assert rational(0.4, 25, 1) == "2/5s"  # 10 frames / 25 fps

    # plan validation
    good = {"animations": [
        {"id": "n1", "type": "stat", "atSeconds": 1.4, "hold": 2.8,
         "content": {"value": "4,2 %", "label": "Rendite"}},
        {"id": "e1", "type": "enumeration", "atSeconds": 5.0, "hold": 4.0,
         "content": {"items": ["Lage", "Steuer", "Rendite"]}},
        {"id": "r1", "type": "reveal", "atSeconds": 9.0, "hold": 3.0,
         "content": {"text": "Und genau das ändert alles."}},
        {"id": "l1", "type": "lowerthird", "atSeconds": 12.0, "hold": 3.5,
         "content": {"text": "Sonderabschreibung §7b"}},
    ]}
    assert validate_plan(good) == [], validate_plan(good)
    bad = {"animations": [
        {"id": "x", "type": "stat", "atSeconds": -1, "hold": 0, "content": {}},
        {"id": "x", "type": "bogus", "atSeconds": 1, "hold": 1, "content": {"value": "1"}},
    ]}
    errs = validate_plan(bad)
    assert any("duplicate id" in e for e in errs), errs
    assert any("type" in e for e in errs), errs
    assert any("atSeconds" in e for e in errs), errs
    assert any("stat needs content.value" in e for e in errs), errs

    # --- timing rules ---
    # single-beat type that lingers too long must be rejected
    assert any("must not linger" in e for e in
               validate_plan({"animations": [
                   {"id": "s", "type": "stat", "atSeconds": 1, "hold": 8,
                    "content": {"value": "1"}}]}))
    # hold over the 10s cap
    assert any("maximum" in e for e in
               validate_plan({"animations": [
                   {"id": "q", "type": "sequence", "atSeconds": 1, "hold": 12,
                    "steps": [{"at": 0, "kind": "text", "text": "a"},
                              {"at": 2, "kind": "text", "text": "b"}]}]}))

    # a valid multi-step sequence: first beat at 0, gaps <=2s, short tail
    good_seq = {"animations": [{
        "id": "seq1", "type": "sequence", "atSeconds": 80, "hold": 9.0,
        "content": {},
        "steps": [
            {"at": 0.0, "kind": "label", "text": "Im Rechenbeispiel"},
            {"at": 1.8, "kind": "kpi", "value": "40.000 €", "sublabel": "Vorteil"},
            {"at": 3.6, "kind": "kpi", "value": "3.768 €", "sublabel": "an dich"},
            {"at": 5.4, "kind": "text", "text": "Bei identischer Rendite.", "emphasis": True},
            {"at": 7.0, "kind": "bullet", "text": "stornofrei ausgezahlt"},
        ],
    }]}
    assert validate_plan(good_seq) == [], validate_plan(good_seq)

    # gap > 2s between beats is rejected
    assert any("exceeds 2.0s" in e for e in
               validate_plan({"animations": [{
                   "id": "g", "type": "sequence", "atSeconds": 1, "hold": 6,
                   "steps": [{"at": 0, "kind": "text", "text": "a"},
                             {"at": 3, "kind": "text", "text": "b"}]}]}))
    # long static tail after the last beat is rejected
    assert any("static tail" in e for e in
               validate_plan({"animations": [{
                   "id": "tl", "type": "sequence", "atSeconds": 1, "hold": 10,
                   "steps": [{"at": 0, "kind": "text", "text": "a"},
                             {"at": 2, "kind": "text", "text": "b"}]}]}))
    print("common selftest OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="shared helpers / selftest")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
    else:
        ap.print_help()
