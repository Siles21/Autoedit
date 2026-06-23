#!/usr/bin/env python3
"""pipeline.py — one-command run of the mechanical pipeline for ONE video.

Given a final video (or transcript) + an ALREADY-AUTHORED animation-plan.json
(entries carry anchorPhrase; the creative curation is Claude's job upstream),
this chains: words -> resolve timecodes -> QC gates (transcript/spell/visual/gap)
-> render (hash-skip) -> integrate (placement/FCPXML). Per-video, batch-friendly.

    pipeline.py --plan plan.json --out <vN> \
        [--transcript premiere.json | --words words.json | --video final.mp4] \
        [--brand thorben] [--format 16x9] [--fps 30] [--strict] \
        [--reel] [--reel-zoom 0.05] [--reel-period 16] [--reel-jump 12] [--reel-jump-amt 0.07] \
        [--music track.mp3] [--music-gain -20] [--deliver {premiere,flat}]

--strict: stop if any QC gate fails. Default: run QC, report, continue.
Creative plan authoring is NOT done here (needs Claude) — pass --plan.

Reel + delivery (9:16 Reels default to --reel and --deliver flat):
  --reel              give the (9:16) source the modern breathing-zoom + jump-cut
                      motion FIRST (reel_dynamics.py → <out>/dynamic.mp4). When
                      both --reel and --video are set, this zoomed clip becomes
                      the base for face-aware placement AND for delivery, so the
                      speaker stays correctly framed on the zoomed picture.
  --deliver flat      after render+SFX, composite overlays onto the (dynamic or
                      original) video → finished mp4 (flatten_final.py); if
                      --music is set, mix the music bed on top (add_music.py).
  --deliver premiere  keep the editable Premiere path (integrate.py → FCPXML).
                      Default for 16:9. --music only applies to flat delivery.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent


def _run(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], **kw)


def _find_browser() -> str | None:
    import glob
    hits = glob.glob(str(Path.home() / ".cache/puppeteer/chrome-headless-shell/*/"
                        "chrome-headless-shell-mac-arm64/chrome-headless-shell"))
    return hits[0] if hits else None


def main() -> None:
    ap = argparse.ArgumentParser(description="One-command per-video pipeline")
    ap.add_argument("--plan", type=Path, required=True, help="authored animation-plan.json (with anchorPhrase)")
    ap.add_argument("--out", type=Path, required=True, help="work dir for this video")
    ap.add_argument("--transcript", type=Path, default=None, help="Premiere transcript JSON")
    ap.add_argument("--words", type=Path, default=None, help="existing words.json")
    ap.add_argument("--video", type=Path, default=None, help="final video (for Whisper if no transcript/words)")
    ap.add_argument("--brand", default="default")
    ap.add_argument("--format", default="16x9")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--max-gap", type=float, default=15.0)
    ap.add_argument("--strict", action="store_true", help="fail on any QC gate violation")
    ap.add_argument("--no-face-aware", action="store_true",
                    help="skip speaker-aware placement (face_zones.py)")
    ap.add_argument("--avoid-style", default="conservative", choices=["conservative", "best"])
    ap.add_argument("--no-sfx", action="store_true", help="skip baking SFX into overlays")
    # reel motion (breathing zoom + jump-cuts via reel_dynamics.py)
    ap.add_argument("--reel", action="store_true", default=None,
                    help="add Reel motion (zoom/jump) to --video first; "
                         "default ON for --format 9x16")
    ap.add_argument("--reel-zoom", type=float, default=0.05, help="breathing amplitude")
    ap.add_argument("--reel-period", type=float, default=16.0, help="in→out cycle seconds")
    ap.add_argument("--reel-jump", type=float, default=12.0, help="seconds between jump-cuts (0=off)")
    ap.add_argument("--reel-jump-amt", type=float, default=0.07, help="zoom step per jump-cut")
    # music bed (OPT-IN, flat delivery only)
    ap.add_argument("--music", type=Path, default=None, help="music track to mix under the flat mp4 (opt-in)")
    ap.add_argument("--music-gain", type=float, default=-20.0, help="music level dB (default -20)")
    # delivery mode
    ap.add_argument("--deliver", default=None, choices=["premiere", "flat"],
                    help="premiere=editable FCPXML (integrate.py); flat=baked mp4 "
                         "(flatten_final.py). Default flat for 9x16, premiere for 16x9")
    args = ap.parse_args()

    # format-driven defaults: 9:16 jobs are Reels delivered as a finished flat mp4;
    # 16:9 jobs stay editable in Premiere. Explicit flags always win.
    is_vertical = args.format in ("9x16", "9:16")
    if args.reel is None:
        args.reel = is_vertical
    if args.deliver is None:
        args.deliver = "flat" if is_vertical else "premiere"

    args.out.mkdir(parents=True, exist_ok=True)

    # 0) Reel motion FIRST — when --reel and --video, give the source the
    # breathing-zoom + jump-cut motion → <out>/dynamic.mp4 and use THAT clip as
    # the base everywhere after (face_zones placement + flat delivery), so the
    # speaker's face is measured/avoided on the actually-zoomed picture. Words
    # come from the original audio (motion never touches audio), so we keep
    # args.video for transcription but flatten/place against base_video.
    base_video = args.video
    if args.reel and args.video:
        dynamic = args.out / "dynamic.mp4"
        print("→ reel_dynamics (breathing zoom + jump-cuts)", file=sys.stderr)
        _run([str(HERE / "reel_dynamics.py"), str(args.video), "--out", str(dynamic),
              "--zoom", str(args.reel_zoom), "--period", str(args.reel_period),
              "--jump", str(args.reel_jump), "--jump-amt", str(args.reel_jump_amt)],
             check=True)
        base_video = dynamic
    elif args.reel and not args.video:
        print("   (--reel needs --video → skipping reel motion)", file=sys.stderr)

    # 1) words.json
    words = args.out / "words.json"
    if args.words:
        words = args.words
    elif args.transcript:
        print("→ premiere_transcript", file=sys.stderr)
        _run([str(HERE / "premiere_transcript.py"), str(args.transcript), "--out", str(words)], check=True)
    elif args.video:
        print("→ transcribe (long, resumable)", file=sys.stderr)
        _run([str(HERE / "transcribe_long.py"), str(args.video), str(words), "small", "180"], check=True)
    else:
        sys.exit("ERROR: need --transcript, --words or --video")

    # 2) resolve timecodes from anchorPhrase (plan stays re-syncable)
    plan = args.out / "animation-plan.json"
    if args.plan.resolve() != plan.resolve():
        plan.write_text(args.plan.read_text(encoding="utf-8"), encoding="utf-8")
    print("→ resolve anchors → atSeconds", file=sys.stderr)
    _run([str(HERE / "build_plan.py"), str(words), "--resolve", str(plan)])
    _run([str(HERE / "build_plan.py"), "--validate", str(plan)], check=True)

    # 2b) opportunity scan (informational checklist for the author)
    _run([str(HERE / "build_plan.py"), str(words), "--suggest",
          "--out", str(args.out / "suggestions.md")])

    # 2c) speaker-aware placement — write a face-free `placement` zone per entry so
    # no overlay covers the speaker's face. Needs pixels (--video). Runs BEFORE
    # render (overlays are baked in their zone). Re-runs every pipeline pass, so a
    # changed cut never leaves an overlay on an old/wrong position.
    if args.video and not args.no_face_aware:
        print("→ speaker-aware placement (face_zones)", file=sys.stderr)
        # face_zones runs against base_video (the dynamic/zoomed clip when --reel),
        # so overlays avoid the face on the SAME frame the viewer ends up seeing.
        _run([str(HERE / "face_zones.py"), str(plan), "--video", str(base_video),
              "--format", args.format, "--style", args.avoid_style, "--cluster",
              "--debug-dir", str(args.out / "placement-debug")])
        _run([str(HERE / "build_plan.py"), "--validate", str(plan)], check=True)
    elif not args.video:
        print("   (no --video → overlays use default lower-third anchors)", file=sys.stderr)

    # 3) QC gates (non-fatal unless --strict)
    qc_fail = []
    for name, cmd in [
        ("transcript", [str(HERE / "qc_transcript.py"), str(words), "--plan", str(plan)]),
        ("lowerthird", [str(HERE / "build_plan.py"), "--lint-lt", str(plan)]),
        ("coverage", [str(HERE / "build_plan.py"), str(words), "--coverage", str(plan),
                      "--out", str(args.out / "coverage.md")]),
        ("spell", [str(HERE / "qc_spell.py"), str(plan)]),
        ("visual", [str(HERE / "qc_visual.py"), str(plan), "--format", args.format]),
        ("gap", [str(HERE / "build_plan.py"), "--gapcheck", str(plan), "--max-gap", str(args.max_gap)]),
    ]:
        rc = _run(cmd).returncode
        print(f"   QC[{name}]: {'OK' if rc == 0 else 'FLAGS'}", file=sys.stderr)
        if rc != 0:
            qc_fail.append(name)
    if qc_fail and args.strict:
        sys.exit(f"STRICT: QC gates failed: {qc_fail}. Fix the plan and re-run.")

    # 4) render (hash-skip → only changed clips re-render)
    print("→ render", file=sys.stderr)
    browser = _find_browser()
    rcmd = [str(HERE / "render_overlays.py"), str(plan), "--remotion", str(SKILL / "remotion"),
            "--formats", args.format, "--out", str(args.out / "overlays"),
            "--fps", str(args.fps), "--brand", args.brand, "--skip-existing"]
    if browser:
        rcmd += [f"--browser-executable={browser}"]
    _run(rcmd, check=True)

    manifest = args.out / "overlays" / "overlays-manifest.json"
    sfx_dir = SKILL / "remotion" / "public" / "sfx"

    # 4b) bake per-type SFX into each overlay (NO default-silent graphics) + verify
    if not args.no_sfx:
        print("→ add_sfx (bake per-type sound)", file=sys.stderr)
        _run([str(HERE / "add_sfx.py"), str(manifest), "--sfx", str(sfx_dir),
              "--format", args.format])
        rc = _run([str(HERE / "qc_audio.py"), str(manifest), "--format", args.format]).returncode
        print(f"   QC[audio]: {'OK' if rc == 0 else 'SILENT CLIPS'}", file=sys.stderr)
        if rc != 0:
            qc_fail.append("audio")
            if args.strict:
                sys.exit("STRICT: silent overlays — add_sfx failed. Fix and re-run.")

    # 5) delivery — two mutually-exclusive paths.
    deliverable = None
    if args.deliver == "flat":
        # 5a) FLAT: composite overlays onto the (dynamic/zoomed or original) base
        # video → one finished mp4. This is the 9:16 Reel default. Needs pixels.
        if not base_video:
            sys.exit("ERROR: --deliver flat needs --video (base to composite onto)")
        final_mp4 = args.out / "final.mp4"
        print("→ flatten_final (composite overlays → finished mp4)", file=sys.stderr)
        _run([str(HERE / "flatten_final.py"),
              "--video", str(base_video),
              "--overlays", str(manifest),
              "--out", str(final_mp4),
              "--format", args.format], check=True)
        deliverable = final_mp4

        # 5b) optional music bed (OPT-IN) — mix under the flattened mp4.
        if args.music:
            scored = args.out / "final_music.mp4"
            print("→ add_music (mix bed under finished mp4)", file=sys.stderr)
            _run([str(HERE / "add_music.py"), str(final_mp4),
                  "--music", str(args.music), "--out", str(scored),
                  "--gain", str(args.music_gain)], check=True)
            deliverable = scored
    else:
        # 5) PREMIERE: keep the editable path (placement list + FCPXML). 16:9 default.
        print("→ integrate", file=sys.stderr)
        icmd = [str(HERE / "integrate.py"), str(plan),
                "--overlays", str(manifest),
                "--out", str(args.out), "--format", args.format]
        if base_video:
            icmd += ["--video", str(base_video)]
        _run(icmd)

    print(f"\nDONE → {args.out}  (deliver={args.deliver}, QC issues: {qc_fail or 'none'})")
    if deliverable:
        print(f"DELIVERABLE → {deliverable}", file=sys.stderr)
    print(str(args.out))


if __name__ == "__main__":
    main()
