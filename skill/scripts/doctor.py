#!/usr/bin/env python3
"""doctor.py — environment self-check for the premiere-sub-animations kit.

Runs with the SYSTEM python3 (stdlib only, no venv needed) so it can report a
missing venv instead of crashing on it. Claude runs this FIRST in every session:
it says what is installed, what is missing and the exact command that fixes it.

    python3 doctor.py                # human-readable report
    python3 doctor.py --json         # machine-readable (for Claude)
    python3 doctor.py --kit <path>   # explicit kit root (default: ../.. of this file)

Exit code: 0 = pipeline can run, 1 = a blocking dependency is missing.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

OK, WARN, FAIL = "ok", "warn", "fail"


def kit_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    # scripts/ -> skill/ -> kit/
    return Path(__file__).resolve().parent.parent.parent


def run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    """Run a command, return (returncode, combined output). Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, "not found"
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except OSError as e:
        return 1, str(e)


def check(name: str, status: str, detail: str, fix: str = "") -> dict:
    return {"name": name, "status": status, "detail": detail, "fix": fix}


# ---------- individual checks ----------

def check_system_tools() -> list[dict]:
    out = []
    for tool, why, fix in (
        ("ffmpeg", "Audio/Video-Verarbeitung", "brew install ffmpeg"),
        ("ffprobe", "Video-Analyse", "brew install ffmpeg"),
        ("node", "Remotion-Render", "brew install node"),
        ("npm", "Remotion-Install", "brew install node"),
    ):
        path = shutil.which(tool)
        if not path:
            out.append(check(tool, FAIL, f"fehlt ({why})", fix))
            continue
        if tool == "node":
            _, ver = run([tool, "--version"])
            major = 0
            if ver.startswith("v") and ver[1:].split(".")[0].isdigit():
                major = int(ver[1:].split(".")[0])
            if major and major < 18:
                out.append(check(tool, FAIL, f"{ver} — zu alt (Remotion braucht >=18)", fix))
            else:
                out.append(check(tool, OK, ver or path))
        else:
            out.append(check(tool, OK, path))
    return out


def check_venv(kit: Path) -> list[dict]:
    py = kit / ".venv" / "bin" / "python"
    if not py.exists():
        return [check("python-venv", FAIL, f"keine venv unter {py}", f"{kit}/setup.sh")]
    out = [check("python-venv", OK, str(py))]
    rc, ver = run([str(py), "-c", "import sys;print('.'.join(map(str,sys.version_info[:3])))"])
    if rc == 0:
        parts = ver.split(".")
        too_old = len(parts) >= 2 and (int(parts[0]), int(parts[1])) < (3, 10)
        out.append(check("python-version", FAIL if too_old else OK, ver,
                         "Python >=3.10 installieren, dann setup.sh neu laufen lassen" if too_old else ""))
    deps = {"faster_whisper": "Whisper-Transkription", "cv2": "Gesichtserkennung",
            "numpy": "Audio-/Frame-Analyse"}
    for mod, why in deps.items():
        rc, msg = run([str(py), "-c", f"import {mod}"])
        out.append(check(f"py:{mod}", OK if rc == 0 else FAIL,
                         why if rc == 0 else msg.splitlines()[-1] if msg else "Import fehlgeschlagen",
                         "" if rc == 0 else f"{kit}/setup.sh"))
    return out


def check_remotion(kit: Path) -> list[dict]:
    rem = kit / "skill" / "remotion"
    nm = rem / "node_modules"
    if not nm.is_dir():
        return [check("remotion", FAIL, "node_modules fehlt", f"cd {rem} && npm install")]
    out = [check("remotion", OK, str(nm))]
    for pkg, why in (("@remotion/cli", "Render-CLI"), ("@remotion/lottie", "Lottie-Overlays")):
        out.append(check(f"remotion:{pkg}", OK if (nm / pkg).is_dir() else WARN,
                         why if (nm / pkg).is_dir() else "nicht installiert",
                         "" if (nm / pkg).is_dir() else f"cd {rem} && npm install"))
    return out


def check_assets(kit: Path) -> list[dict]:
    out = []
    models = kit / "skill" / "scripts" / "models"
    need = ["deploy.prototxt", "res10_300x300_ssd_iter_140000.caffemodel"]
    missing = [n for n in need if not (models / n).exists()]
    out.append(check("face-models", OK if not missing else WARN,
                     "DNN-Modelle vorhanden" if not missing else f"fehlt: {', '.join(missing)}",
                     "" if not missing else "ohne Modelle fällt face_zones.py auf Haar-Cascade zurück"))

    brands_dir = kit / "skill" / "remotion" / "brands"
    brands = sorted(p.stem for p in brands_dir.glob("*.json")) if brands_dir.is_dir() else []
    out.append(check("brands", OK if brands else FAIL,
                     ", ".join(brands) if brands else "keine Brand-Presets",
                     "" if brands else f"Preset anlegen: {brands_dir}/<name>.json"))

    sfx = kit / "skill" / "remotion" / "public" / "sfx"
    n_sfx = len(list(sfx.glob("*"))) if sfx.is_dir() else 0
    out.append(check("sfx", OK if n_sfx else WARN,
                     f"{n_sfx} Dateien" if n_sfx else "kein SFX-Ordner",
                     "" if n_sfx else "add_sfx.py bleibt ohne Sounds wirkungslos"))
    return out


def check_bridge(port: int = 3030) -> list[dict]:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return [check("live-bridge", OK, f"adb-mcp Proxy erreichbar (Port {port}) — Live-Platzierung möglich")]
    except OSError:
        return [check("live-bridge", WARN, f"Port {port} geschlossen — Fallback-Weg (FCPXML/placement.md)",
                      "Premiere öffnen + ./vendor/adb-mcp/bridge-up.sh (siehe docs/LIVE-PREMIERE-SETUP.md)")]


def check_skill_install(kit: Path) -> list[dict]:
    link = Path.home() / ".claude" / "skills" / "premiere-sub-animations"
    if not link.exists():
        return [check("skill-installed", WARN, f"{link} fehlt — Claude lädt den Skill nicht automatisch",
                      f"{kit}/setup.sh --install-skill")]
    target = link.resolve()
    expected = (kit / "skill").resolve()
    if target != expected:
        return [check("skill-installed", WARN, f"zeigt auf {target}, nicht auf {expected}",
                      f"{kit}/setup.sh --install-skill")]
    return [check("skill-installed", OK, str(link))]


def gather(kit: Path) -> dict:
    checks: list[dict] = []
    checks += [check("kit-root", OK if (kit / "skill" / "SKILL.md").exists() else FAIL, str(kit),
                     "" if (kit / "skill" / "SKILL.md").exists() else "--kit <pfad-zum-kit> angeben")]
    checks += check_system_tools()
    checks += check_venv(kit)
    checks += check_remotion(kit)
    checks += check_assets(kit)
    checks += check_bridge()
    checks += check_skill_install(kit)

    fails = [c for c in checks if c["status"] == FAIL]
    warns = [c for c in checks if c["status"] == WARN]
    return {
        "kit": str(kit),
        "python": str(kit / ".venv" / "bin" / "python"),
        "ready": not fails,
        "placement": "live" if any(c["name"] == "live-bridge" and c["status"] == OK for c in checks) else "fallback",
        "checks": checks,
        "blocking": [c["name"] for c in fails],
        "warnings": [c["name"] for c in warns],
    }


def report(res: dict) -> None:
    sym = {OK: "\033[32m✓\033[0m", WARN: "\033[33m!\033[0m", FAIL: "\033[31m✗\033[0m"}
    print(f"== Premiere Sub-Animations — doctor ==\nKit: {res['kit']}\n")
    for c in res["checks"]:
        print(f"{sym[c['status']]} {c['name']:<22} {c['detail']}")
        if c["fix"] and c["status"] != OK:
            print(f"    → {c['fix']}")
    print()
    if res["ready"]:
        print(f"\033[32m✓ Pipeline einsatzbereit.\033[0m Platzierung: {res['placement']}")
    else:
        print(f"\033[31m✗ Blockiert:\033[0m {', '.join(res['blocking'])} — siehe Fixes oben.")


def main() -> int:
    ap = argparse.ArgumentParser(description="environment self-check for the kit")
    ap.add_argument("--kit", help="kit root (default: derived from this file's location)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    kit = kit_root(args.kit)
    res = gather(kit)
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        report(res)
    return 0 if res["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
