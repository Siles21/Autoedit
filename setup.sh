#!/usr/bin/env bash
# setup.sh — one-shot installer for the Premiere Sub-Animations kit.
# Installs every dependency so the pipeline runs 1:1. Idempotent — re-run anytime.
#
#   ./setup.sh            # full install (skill + live bridge)
#   ./setup.sh --no-live  # skip the adb-mcp live-Premiere bridge
set -uo pipefail
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WITH_LIVE=1
[ "${1:-}" = "--no-live" ] && WITH_LIVE=0

ok()   { printf "\033[32m✓\033[0m %s\n" "$1"; }
warn() { printf "\033[33m!\033[0m %s\n" "$1"; }
die()  { printf "\033[31m✗ %s\033[0m\n" "$1"; exit 1; }

echo "== Premiere Sub-Animations — setup =="
echo "Kit: $KIT"

# ---------- 0. prerequisites ----------
command -v python3 >/dev/null || die "python3 not found (need >=3.10). Install Python 3."
command -v node    >/dev/null || die "node not found (need >=18). Install Node.js (e.g. brew install node)."
command -v npm     >/dev/null || die "npm not found. Install Node.js."
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  die "ffmpeg/ffprobe not found. Install:  brew install ffmpeg   (macOS)  /  apt install ffmpeg (Linux)"
fi
ok "python3 / node / npm / ffmpeg present"

# ---------- 1. python deps (skill) in an isolated venv ----------
# A venv works everywhere — incl. PEP 668 "externally-managed" Homebrew Python,
# where a plain `pip install` is blocked.
VENV="$KIT/.venv"
PY="$VENV/bin/python"
echo "→ creating venv + installing Python deps (faster-whisper, opencv, numpy)…"
python3 -m venv "$VENV" || die "could not create venv at $VENV"
"$PY" -m pip install -q --upgrade pip || warn "pip self-upgrade failed (continuing)"
"$PY" -m pip install -q -r "$KIT/requirements.txt" || die "pip install failed (requirements.txt)"
ok "Python deps installed into .venv"

# ---------- 2. remotion (skill) ----------
# Use a kit-local npm cache to sidestep any broken/root-owned global ~/.npm cache.
NPM_CACHE="$KIT/.npm-cache"
NPMI="npm install --no-audit --no-fund --cache $NPM_CACHE"
echo "→ installing Remotion node_modules…"
( cd "$KIT/skill/remotion" && $NPMI ) || die "npm install failed (skill/remotion)"
ok "Remotion installed"

# ---------- 3. self-checks ----------
echo "→ running self-tests…"
( cd "$KIT/skill/scripts" && "$PY" common.py --selftest && "$PY" build_plan.py --selftest ) \
  && ok "Python self-tests pass" || warn "self-tests reported issues (see above)"
# verify the heavy deps actually import in the venv
"$PY" -c "import faster_whisper, cv2, numpy; print('  faster-whisper/opencv/numpy import OK')" \
  && ok "Python deps importable" || warn "deps import check failed"
( cd "$KIT/skill/remotion" && npx --no-install tsc --noEmit ) \
  && ok "Remotion typecheck pass" || warn "Remotion typecheck reported issues"

# ---------- 4. live bridge (adb-mcp) ----------
if [ "$WITH_LIVE" = "1" ]; then
  echo "→ installing the adb-mcp live-Premiere bridge…"
  ADB="$KIT/vendor/adb-mcp"
  ( cd "$ADB/adb-proxy-socket" && $NPMI ) || warn "proxy npm install failed"
  # python MCP server deps in an isolated venv
  if [ -d "$ADB/mcp" ]; then
    python3 -m venv "$ADB/mcp/.venv" 2>/dev/null || true
    "$ADB/mcp/.venv/bin/python" -m pip install -q --upgrade pip 2>/dev/null || true
    if [ -f "$ADB/mcp/requirements.txt" ]; then
      "$ADB/mcp/.venv/bin/python" -m pip install -q -r "$ADB/mcp/requirements.txt" \
        && ok "adb-mcp python server installed (venv)" || warn "adb-mcp python deps failed"
    fi
  fi
  chmod +x "$ADB/bridge-up.sh" "$ADB/uxp-cli.sh" 2>/dev/null || true
  ok "Live bridge installed. NEXT: see docs/LIVE-PREMIERE-SETUP.md (one-time UXP sideload), then ./vendor/adb-mcp/bridge-up.sh"
else
  warn "skipped live bridge (--no-live). Fallback path (FCP7-XML/placement.md) still works."
fi

echo
ok "Setup done."
echo
echo "WICHTIG: aktiviere die venv, bevor du die Scripts startest:"
echo "    source .venv/bin/activate        # danach 'python3 scripts/...' wie in SKILL.md"
echo "  (oder ohne Aktivieren direkt:  .venv/bin/python scripts/...)"
echo
echo "Try:  source .venv/bin/activate && cd skill && python3 scripts/build_plan.py --selftest"
echo "Docs: README.md  ·  docs/LIVE-PREMIERE-SETUP.md  ·  skill/SKILL.md"
