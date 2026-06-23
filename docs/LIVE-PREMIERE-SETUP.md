# Live-Premiere-Bridge (adb-mcp) einrichten

Der Live-Weg setzt die Overlays direkt in das **offene** Premiere-Projekt
(statt FCP7-XML-Export). Er nutzt die mitgelieferte `adb-mcp`-Bridge:

```
Pipeline / premiere_drive.js  ──socket:3030──►  Socket-Proxy  ──►  UXP-Plugin in Premiere
```

> Ohne diesen Schritt funktioniert das Kit trotzdem voll — über den Fallback
> (FCP7-XML / `placement.md` zum manuellen Import). Live ist nur komfortabler.

---

## Voraussetzungen
- **macOS** + **Adobe Premiere Pro** (aktuelle Version, UXP-fähig).
- `setup.sh` einmal gelaufen (installiert Proxy-`node_modules` + Python-venv der Bridge).
- Node.js + Python wie im README.

## Einmaliges Setup (pro Rechner)

1. **UXP-Developer-Mode aktivieren** und Premiere **einmal neu starten**:
   ```bash
   ./vendor/adb-mcp/uxp-cli.sh enable
   ```
   (Danach Premiere komplett schließen und neu öffnen.)

2. Premiere öffnen und **ein Projekt mit einer Sequenz** laden.

## Pro Session: Bridge hochziehen

```bash
./vendor/adb-mcp/bridge-up.sh
```
Das ist idempotent + selbstheilend und macht in einem Rutsch:
1. Socket-Proxy auf `:3030`
2. UXP-Dev-Service auf `:14001`
3. lädt das Plugin **„Premiere MCP Agent"** ins laufende Premiere
4. verifiziert die Bridge mit `premiere_drive.js info`

Erfolg sieht so aus: `✅ BRIDGE LIVE — premiere_drive.js info antwortet`.

Wenn die letzte Zeile timeoutet: in Premiere einmal
**Fenster ▸ UXP-Plug-ins ▸ Premiere MCP Agent** öffnen, dann erneut `bridge-up.sh`.

## Bridge testen / nutzen

```bash
# Sequenzstand auslesen (alle Spuren/Clips)
node vendor/adb-mcp/premiere_drive.js info

# Overlays platzieren (Manifest aus render_overlays.py)
node vendor/adb-mcp/premiere_drive.js place work/v1/overlays/overlays-manifest.json \
    --seq <sequenz-id> --vtrack 9 --atrack 9
```
Die genauen Modi (`place`, `remove`, `retime`, `reconcile`, `relink`, `label`, `seqs`,
`use`) und die Platzierungs-Disziplin (Reserved Tracks, Registry, Audit) stehen in
`skill/SKILL.md`, Stufen 5 + 9.

## Prüfen, ob die Bridge läuft

```bash
python3 skill/scripts/integrate.py --probe-only
# → {"adb_mcp_live": true, "port": 3030}
```

## Troubleshooting
- **`✗ Proxy :3030 startet nicht`** → `cd vendor/adb-mcp/adb-proxy-socket && npm install` erneut; Port 3030 frei? (`lsof -i :3030`).
- **`Premiere ist NICHT mit dem UXP-Service verbunden`** → Dev-Mode aktiviert (`uxp-cli.sh enable`) und Premiere neu gestartet? Premiere offen?
- **Plugin lädt nicht** → `vendor/adb-mcp/uxp/pr/manifest.json` vorhanden; Premiere-Version UXP-fähig.
- **Medien „Media Offline" / flackern** → Render-Quellen NIE aus `/tmp` (macOS leert es). Overlays in einen dauerhaften Ordner legen, dann `node premiere_drive.js relink <map.json>`.
- Drittsoftware-Doku: `vendor/adb-mcp/README.md` und `vendor/adb-mcp/PREMIERE_API_CAPABILITIES.html`.
