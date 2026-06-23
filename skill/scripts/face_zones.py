#!/usr/bin/env python3
"""face_zones.py — speaker-aware overlay placement.

For every plan entry, sample frames of the FINAL video across the animation's
on-screen span, detect the speaker's face(s) with opencv, take the union envelope
(handles camera push-in/pan + multiple faces), and pick the best face-free zone
for that overlay type. Writes a normalized `placement` hint back into the plan so
the rendered overlay is positioned to NOT cover the face.

Runs AFTER anchor-resolve (entries carry atSeconds + hold), BEFORE render (the
overlay pixels are baked). Re-run after a cut change (resync.py).

    face_zones.py <plan.json> --video <final.mp4> [--format 16x9]
        [--style conservative|best] [--pad 0.06] [--cluster] [--debug-dir <dir>]
    face_zones.py --selftest      # pure zone-selection asserts, no video

Deterministic: same video + plan → same placement.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- #
# Zone model — normalized rectangles (x0,y0,x1,y1) = where the PANEL would sit.
# --------------------------------------------------------------------------- #
ZONES = {
    "bottom":       (0.05, 0.66, 0.95, 0.95),
    "top":          (0.05, 0.05, 0.95, 0.34),
    "left":         (0.03, 0.28, 0.42, 0.92),
    "right":        (0.58, 0.28, 0.97, 0.92),
    "bottom-left":  (0.03, 0.58, 0.49, 0.95),
    "bottom-right": (0.51, 0.58, 0.97, 0.95),
    "top-left":     (0.03, 0.05, 0.49, 0.42),
    "top-right":    (0.51, 0.05, 0.97, 0.42),
    "center":       (0.22, 0.30, 0.78, 0.70),
}

# Conventional preference per overlay type (first safe + big-enough wins).
PREF = {
    "lowerthird":   ["bottom-left", "bottom-right", "bottom", "top-left", "top-right"],
    "stat":         ["bottom", "top", "bottom-right", "bottom-left", "top-right", "top-left"],
    "kpibig":       ["bottom", "top", "bottom-right", "bottom-left", "top-right", "top-left"],
    "reveal":       ["bottom", "top", "bottom-right", "bottom-left", "top-right", "top-left"],
    "cta":          ["bottom", "top", "bottom-right", "bottom-left"],
    "comparebars":  ["bottom", "top", "right", "left", "bottom-right", "bottom-left", "top-right", "top-left"],
    "chart":        ["bottom", "top", "right", "left", "bottom-right", "bottom-left", "top-right", "top-left"],
    "comparetable": ["bottom", "top", "right", "left", "bottom-right", "bottom-left", "top-right", "top-left"],
    "comparecards": ["bottom", "top", "bottom-right", "bottom-left", "top-right", "top-left"],
    "sequence":     ["bottom", "top", "right", "left", "bottom-right", "bottom-left", "top-right", "top-left"],
    "enumeration":  ["bottom", "top", "right", "left", "bottom-right", "bottom-left", "top-right", "top-left"],
}
# types that never get avoidance (full-frame takeover / own continuous layer)
BYPASS_TYPES = {"caption"}
SAFE_EPS = 0.07   # max fraction of a zone covered by the face to still be "safe"


def _rect_area(r):
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _overlap_frac(zone, face):
    """Fraction of the zone rectangle covered by the face rectangle."""
    ix0, iy0 = max(zone[0], face[0]), max(zone[1], face[1])
    ix1, iy1 = min(zone[2], face[2]), min(zone[3], face[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    za = _rect_area(zone)
    return inter / za if za > 0 else 1.0


def pick_zone(face, otype, style="conservative"):
    """face = (x0,y0,x1,y1) padded envelope (0..1) or None. Returns (zone, constrained)."""
    pref = PREF.get(otype, PREF["stat"])
    if face is None:
        return (pref[0], False)  # no face → conventional default (bottom / strap)
    cands = pref
    if style == "best":  # order by largest free area instead of convention
        cands = sorted(pref, key=lambda z: _overlap_frac(ZONES[z], face))
    best, best_ov = None, 1e9
    for z in cands:
        ov = _overlap_frac(ZONES[z], face)
        if ov < best_ov:
            best, best_ov = z, ov
        if ov <= SAFE_EPS:
            return (z, False)
    return (best or pref[0], True)  # nothing clear → least-bad zone, constrained


# --------------------------------------------------------------------------- #
# Face detection (opencv DNN res10 → Haar fallback)
# --------------------------------------------------------------------------- #
_NET = None
_CASCADE = None
_DETECTOR = None


def _init_detector():
    global _NET, _CASCADE, _DETECTOR
    if _DETECTOR is not None:
        return _DETECTOR
    import cv2
    proto = HERE / "models" / "deploy.prototxt"
    model = HERE / "models" / "res10_300x300_ssd_iter_140000.caffemodel"
    if proto.exists() and model.exists():
        try:
            _NET = cv2.dnn.readNetFromCaffe(str(proto), str(model))
            _DETECTOR = "dnn"
            return _DETECTOR
        except Exception:
            pass
    _CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    _DETECTOR = "haar"
    return _DETECTOR


def detect_faces(img, conf=0.5):
    """Return list of (x0,y0,x1,y1) normalized 0..1 + the detection confidence."""
    import cv2
    det = _init_detector()
    h, w = img.shape[:2]
    out = []
    if det == "dnn":
        blob = cv2.dnn.blobFromImage(cv2.resize(img, (300, 300)), 1.0, (300, 300),
                                     (104.0, 177.0, 123.0))
        _NET.setInput(blob)
        d = _NET.forward()
        for i in range(d.shape[2]):
            c = float(d[0, 0, i, 2])
            if c < conf:
                continue
            x0, y0, x1, y1 = d[0, 0, i, 3:7]  # already normalized
            out.append(((float(max(0, x0)), float(max(0, y0)),
                         float(min(1, x1)), float(min(1, y1))), c))
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = _CASCADE.detectMultiScale(gray, 1.1, 5, minSize=(int(w * 0.04), int(h * 0.04)))
        for (x, y, fw, fh) in faces:
            out.append(((x / w, y / h, (x + fw) / w, (y + fh) / h), 0.8))
    return out


def _extract_frame(video, t, width=640):
    """Grab one BGR frame at time t (fast input-seek) via ffmpeg → opencv."""
    import numpy as np, cv2
    r = subprocess.run(
        ["ffmpeg", "-nostdin", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
         "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True)
    if not r.stdout:
        return None
    arr = np.frombuffer(r.stdout, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _sample_times(at, hold):
    n = max(3, math.ceil(hold / 0.5))
    n = min(n, 12)
    if n == 1:
        return [at + hold / 2]
    return [at + hold * i / (n - 1) for i in range(n)]


def analyze_entry(video, entry, pad=0.06, style="conservative"):
    """Sample → detect → envelope → zone. Returns the placement dict."""
    otype = entry.get("type")
    if otype in BYPASS_TYPES or (entry.get("content") or {}).get("backdrop"):
        return {"zone": "center", "bypass": True, "confidence": 1.0}
    at = float(entry["atSeconds"]); hold = float(entry["hold"])
    times = _sample_times(at, hold)
    all_boxes = []          # (box, conf)
    centers = []            # per-frame primary center for cut detection
    hits = 0
    for t in times:
        img = _extract_frame(video, t)
        if img is None:
            continue
        boxes = detect_faces(img)
        if boxes:
            hits += 1
            all_boxes.extend(boxes)
            # largest face center this frame
            bx = max(boxes, key=lambda b: _rect_area(b[0]))[0]
            centers.append(((bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2))
    if not all_boxes:
        return {"zone": PREF.get(otype, PREF["stat"])[0], "faceBox": None,
                "confidence": 0.0, "constrained": False}
    # union envelope + pad
    x0 = min(b[0][0] for b in all_boxes); y0 = min(b[0][1] for b in all_boxes)
    x1 = max(b[0][2] for b in all_boxes); y1 = max(b[0][3] for b in all_boxes)
    fx0, fy0 = max(0.0, x0 - pad), max(0.0, y0 - pad)
    fx1, fy1 = min(1.0, x1 + pad), min(1.0, y1 + pad)
    face = (fx0, fy0, fx1, fy1)
    conf = round(hits / max(1, len(times)) * (sum(b[1] for b in all_boxes) / len(all_boxes)), 3)
    # mid-clip cut: large center jump between consecutive samples
    split = False; cut_at = None
    for i in range(1, len(centers)):
        if (abs(centers[i][0] - centers[i - 1][0]) > 0.25 or
                abs(centers[i][1] - centers[i - 1][1]) > 0.25):
            split = True
            cut_at = round(times[i], 2)
            break
    zone, constrained = pick_zone(face, otype, style)
    return {"zone": zone,
            "faceBox": {"x": round(fx0, 3), "y": round(fy0, 3),
                        "w": round(fx1 - fx0, 3), "h": round(fy1 - fy0, 3)},
            "confidence": conf, "constrained": constrained,
            "split": split, "cutAtSeconds": cut_at}


def _cluster(entries):
    """Group entries with near-identical face envelopes → same zone (consistency)."""
    def sig(e):
        fb = (e.get("placement") or {}).get("faceBox")
        if not fb:
            return None
        return (round(fb["x"], 1), round(fb["y"], 1), round(fb["w"], 1), round(fb["h"], 1))
    groups = {}
    for e in entries:
        p = e.get("placement") or {}
        if p.get("bypass") or p.get("faceBox") is None:
            continue
        groups.setdefault((e.get("type"), sig(e)), []).append(e)
    for members in groups.values():
        if len(members) < 2:
            continue
        # representative = highest-confidence member's zone
        rep = max(members, key=lambda e: (e.get("placement") or {}).get("confidence", 0))
        z = rep["placement"]["zone"]
        for e in members:
            e["placement"]["zone"] = z
            e["placement"]["clustered"] = True


def run(plan_path, video, fmt, style, pad, cluster, debug_dir):
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    entries = plan.get("animations", [])
    flagged = []
    for i, e in enumerate(entries):
        e["placement"] = analyze_entry(video, e, pad=pad, style=style)
        p = e["placement"]
        if p.get("constrained") or p.get("split"):
            flagged.append((e.get("id"), "split" if p.get("split") else "constrained"))
        print(f"  [{i+1}/{len(entries)}] {e.get('id'):24} → {p['zone']:12} "
              f"conf={p.get('confidence',0):.2f}"
              f"{' SPLIT' if p.get('split') else ''}{' CONSTRAINED' if p.get('constrained') else ''}",
              file=sys.stderr)
    if cluster:
        _cluster(entries)
    Path(plan_path).write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    if debug_dir:
        Path(debug_dir).mkdir(parents=True, exist_ok=True)
        json.dump([{"id": e.get("id"), "placement": e.get("placement")} for e in entries],
                  open(Path(debug_dir) / "placement-debug.json", "w"), ensure_ascii=False, indent=1)
    print(f"face_zones: {len(entries)} entries via {_DETECTOR or 'haar'}; "
          f"flagged {len(flagged)} (split/constrained)", file=sys.stderr)
    for fid, why in flagged:
        print(f"  ⚠ {why}: {fid}", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- #
def _selftest():
    # face bottom-left → person strap should go bottom-right
    f = (0.02, 0.55, 0.42, 0.98)
    assert pick_zone(f, "lowerthird")[0] in ("bottom-right", "top-left", "top-right"), pick_zone(f, "lowerthird")
    # face centered-upper → stat goes bottom
    f = (0.30, 0.05, 0.70, 0.55)
    assert pick_zone(f, "stat")[0] == "bottom", pick_zone(f, "stat")
    # face low/centered → stat jumps to top
    f = (0.28, 0.50, 0.72, 0.99)
    assert pick_zone(f, "stat")[0] == "top", pick_zone(f, "stat")
    # face fills frame → constrained
    f = (0.02, 0.02, 0.98, 0.98)
    z, c = pick_zone(f, "stat"); assert c is True, (z, c)
    # no face → conventional default
    assert pick_zone(None, "lowerthird")[0] == "bottom-left"
    assert pick_zone(None, "stat")[0] == "bottom"
    # speaker center-frame → panel can go to a side column for chart
    f = (0.38, 0.18, 0.62, 0.92)
    assert pick_zone(f, "chart")[0] in ("bottom", "top", "left", "right"), pick_zone(f, "chart")
    print("face_zones selftest OK")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan", nargs="?", type=Path)
    ap.add_argument("--video", type=Path)
    ap.add_argument("--format", default="16x9")
    ap.add_argument("--style", default="conservative", choices=["conservative", "best"])
    ap.add_argument("--pad", type=float, default=0.06, help="safety margin around face (0..1)")
    ap.add_argument("--cluster", action="store_true", help="give identical shots identical zones")
    ap.add_argument("--debug-dir", default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(_selftest())
    if not args.plan or not args.video:
        sys.exit("usage: face_zones.py <plan.json> --video <final.mp4>  (or --selftest)")
    if not args.video.exists():
        sys.exit(f"face_zones: video not found: {args.video}")
    sys.exit(run(args.plan, args.video, args.format, args.style, args.pad, args.cluster, args.debug_dir))


if __name__ == "__main__":
    main()
