#!/bin/bash
# bridge-up.sh — EIN Befehl, der die adb-mcp Premiere-Live-Bridge komplett hochzieht.
#
# Idempotent + selbstheilend. Macht in einem Rutsch:
#   1) Socket-Proxy auf :3030          (MCP <-> Plugin Transport)
#   2) UXP-Dev-Service auf :14001       (headless Plugin-Loader)
#   3) lädt "Premiere MCP Agent" ins LAUFENDE Premiere (kein GUI/UDT nötig)
#   4) verifiziert die Bridge per premiere_drive.js info
#
# Damit ersetzt dieser Befehl das gesamte UXP-Developer-Tool-GUI-Geklicke.
# Voraussetzung (einmalig, bleibt persistent): Dev-Mode aktiviert
#   (./uxp-cli.sh enable  → danach Premiere EINMAL neu starten).
#
# Aufruf:  ./vendor/adb-mcp/bridge-up.sh
set -uo pipefail
ADB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="$ADB/uxp/pr/manifest.json"

up() { lsof -i :"$1" -sTCP:LISTEN >/dev/null 2>&1; }

# 1) Socket-Proxy (:3030)
if ! up 3030; then
  echo "→ starte Proxy (:3030)…"
  ( cd "$ADB/adb-proxy-socket" && nohup node proxy.js > "$ADB/proxy.log" 2>&1 & )
  sleep 2
fi
up 3030 && echo "✓ Proxy :3030" || { echo "✗ Proxy :3030 startet nicht — node proxy.js prüfen"; exit 1; }

# 2) UXP-Dev-Service (:14001)
if ! up 14001; then
  echo "→ starte UXP-Dev-Service (:14001)…"
  ( nohup "$ADB/uxp-cli.sh" service > "$ADB/uxp-service.log" 2>&1 & )
  sleep 3
fi
up 14001 && echo "✓ UXP-Service :14001" || { echo "✗ UXP-Service :14001 startet nicht"; exit 1; }

# 3) Premiere mit dem Service verbunden?
if ! "$ADB/uxp-cli.sh" apps 2>/dev/null | grep -q premierepro; then
  echo "✗ Premiere ist NICHT mit dem UXP-Service verbunden."
  echo "  → Premiere offen? Dev-Mode aktiv? Einmalig:  $ADB/uxp-cli.sh enable  und Premiere neu starten."
  exit 1
fi
echo "✓ Premiere am UXP-Service"

# 4) Plugin laden (absoluter Pfad — CLI löst relativ zu ihrem eigenen Ordner auf)
if "$ADB/uxp-cli.sh" load "$MANIFEST" 2>&1 | grep -qi "Load Successfull"; then
  echo "✓ Plugin geladen"
else
  echo "… Plugin-Load unklar (evtl. schon geladen) — verifiziere trotzdem"
fi
sleep 2

# 5) echte Bridge testen
if node "$ADB/premiere_drive.js" info >/dev/null 2>&1; then
  echo "✅ BRIDGE LIVE — premiere_drive.js info antwortet"
else
  echo "⚠️  Plugin geladen, aber info timeoutet — Panel einmal über Fenster ▸ UXP-Plug-ins ▸ Premiere MCP Agent öffnen"
  exit 2
fi
