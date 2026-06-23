#!/bin/bash
# uxp-cli.sh — drive Adobe's UXP Developer CLI headlessly on Apple Silicon.
#
# The @adobe/uxp-devtools-cli native add-on (electron-napi.node) ships x86_64 only,
# so on arm64 Macs it must run under Rosetta with an x86_64 Node. This wrapper pins
# both. It enables Developer Mode (the switch that lets Premiere load unpacked
# plugins from .../UXP/Plugins/External/) and loads/reloads plugins into a RUNNING
# host app — no UXP Developer Tool GUI needed.
#
# One-time setup already done in ~/tmp:  x86_64 Node 24 + the CLI installed
# (npm i @adobe/uxp-devtools-cli, with `tar` added so the helper postinstall runs).
#
# Usage:
#   uxp-cli.sh service     # start the dev service (port 14001) in the foreground
#   uxp-cli.sh enable      # enable Developer Mode (needs sudo; persistent)
#   uxp-cli.sh apps        # list connected host apps (Premiere must be RESTARTED
#                          #   after enable so it connects to the service)
#   uxp-cli.sh load <manifest.json>    # load a plugin into the running app
#   uxp-cli.sh reload <manifest.json>  # hot-reload after editing the plugin
#   uxp-cli.sh raw <args...>           # pass anything straight to `uxp`
set -euo pipefail

XNODE="$HOME/tmp/node-x64/bin/node"
CLI_DIR="$HOME/tmp/uxp-cli"
UXP="$CLI_DIR/node_modules/.bin/uxp"

[ -x "$XNODE" ] || { echo "ERROR: x86_64 Node missing at $XNODE"; exit 1; }
[ -f "$UXP" ]   || { echo "ERROR: uxp CLI missing at $UXP (run the install)"; exit 1; }

run() { ( cd "$CLI_DIR" && arch -x86_64 "$XNODE" "$UXP" "$@" ); }

cmd="${1:-}"; shift || true
case "$cmd" in
  service) run service start ;;
  enable)  printf '\n\n' | run devtools enable ;;
  disable) run devtools disable ;;
  apps)    run apps list ;;
  load)    run plugin load --manifest "$1" ;;
  reload)  run plugin reload --manifest "$1" ;;
  raw)     run "$@" ;;
  *) echo "usage: uxp-cli.sh {service|enable|disable|apps|load <manifest>|reload <manifest>|raw ...}"; exit 1 ;;
esac
